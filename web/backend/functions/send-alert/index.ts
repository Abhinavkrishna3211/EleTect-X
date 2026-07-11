// EleTect X — alert fan-out (Supabase Edge Function, Deno)
// Trigger: Database Webhook on INSERT into `events` (or call directly with an event record).
// Sends to all officers + opted-in Public users near the node, and logs to `alerts`.
//
// This file is the thin HTTP entrypoint: payload/demo guards, recipient selection, then hand off
// to fanOut() in fanout.ts (channels + per-recipient delivery + audit). Keeping the delivery logic
// in fanout.ts lets it be unit-tested with a stub client (fanout.test.ts) with no live project.
//
// Delivery is channel-pluggable (see fanout.ts). Email is the primary channel today; SMS is
// implemented but gated off pending TRAI DLT registration; WhatsApp is a registered stub.
//
// Secrets (supabase secrets set ...):
//   SUPABASE_URL (platform-injected), SERVICE_ROLE_KEY,
//   RESEND_API_KEY, ALERT_EMAIL_FROM         (email channel)
//   CHANNEL_EMAIL=off to disable email, CHANNEL_SMS=on to enable SMS, CHANNEL_WHATSAPP=on
//   SMS_PROVIDER (fast2sms|msg91|twilio), SMS_API_KEY, SMS_SENDER, SMS_TEMPLATE_ID,
//   TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM     (sms channel, twilio only)
// NOTE (India): SMS to Indian numbers requires TRAI **DLT registration** (approved sender ID +
//   template) via your provider. Until then keep CHANNEL_SMS off. See web/backend/README.md.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { type AlertMessage, fanOut } from "./fanout.ts";

const ALERT_RADIUS_KM = 3;
const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SERVICE_ROLE_KEY")!);

function kmBetween(a: number, b: number, c: number, d: number) {         // haversine
  const R = 6371, r = Math.PI / 180;
  const dLat = (c - a) * r, dLng = (d - b) * r;
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(a * r) * Math.cos(c * r) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(x));
}

Deno.serve(async (req) => {
  const payload = await req.json().catch(() => null);
  // Fail closed. This block is the first thing that runs, before any other
  // logic, on purpose: a Demo Mode scenario writes real `events` rows, and this
  // webhook would otherwise fan out to every officer and every opted-in resident
  // within 3 km. An unreadable payload, or any demo-tagged event, must never fan
  // out. (Demo events are also written priority='normal', so the check below is a
  // second, independent barrier — but this one is the guarantee.)
  if (payload === null) return new Response("unreadable payload", { status: 400 });
  const ev = payload.record ?? payload;                       // DB webhook sends {record}
  if (ev?.media_url === "demo") return new Response("skipped (demo)", { status: 200 });
  if (!ev?.node_id) return new Response("no event", { status: 400 });
  if ((ev.priority ?? "normal") !== "high") return new Response("skipped (not high)", { status: 200 });

  const { data: node } = await db.from("nodes").select("name,lat,lng").eq("id", ev.node_id).single();
  const body = `EleTect X: elephant detected near ${node?.name ?? ev.node_id} ` +
    `(${Math.round((ev.confidence ?? 0) * 100)}% confidence). Stay alert, avoid the area.`;
  const msg: AlertMessage = { subject: `EleTect X alert — ${node?.name ?? ev.node_id}`, body };

  // No phone filter: with email primary, a recipient needs only *an* address, and
  // per-channel addressability is decided in deliver(). Public opt-in is alerts_enabled.
  const { data: staff } = await db.from("profiles").select("id,phone")
    .in("role", ["admin", "officer"]);
  const { data: pub } = await db.from("profiles").select("id,phone,lat,lng")
    .eq("role", "public").eq("alerts_enabled", true);
  const near = (pub ?? []).filter((p) =>
    p.lat != null && node?.lat != null && kmBetween(node.lat, node.lng, p.lat!, p.lng!) <= ALERT_RADIUS_KM);

  // Dedupe by profile id (a person is one recipient regardless of how they were matched); email is
  // resolved per recipient inside fanOut() from auth.users — profiles stores no email.
  const byId = new Map<string, { id: string; phone: string | null }>();
  for (const p of [...(staff ?? []), ...near]) byId.set(p.id, { id: p.id, phone: p.phone ?? null });

  const { sent, byChannel } = await fanOut(db, [...byId.values()], msg, ev.id ?? null);
  return new Response(JSON.stringify({ sent, total: byId.size, byChannel }), {
    headers: { "Content-Type": "application/json" },
  });
});
