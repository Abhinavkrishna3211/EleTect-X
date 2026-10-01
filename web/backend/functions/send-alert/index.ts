// EleTect X — alert fan-out (Supabase Edge Function, Deno)
// Trigger: Database Webhook on INSERT into `events` (or call directly with an event record).
// Sends to all officers + opted-in Public users near the node, and logs to `alerts`. Gunshot and
// chainsaw alerts go to officers only (message.ts decides wording and audience).
//
// This file is the thin HTTP entrypoint: payload/demo guards, the queries that gather recipients,
// then hand off to fanOut() in fanout.ts (channels + per-recipient delivery + audit). Everything
// that decides anything — who is near enough (withinRadius) and who is in the audience
// (message.ts) — lives outside this file so it can be unit-tested with no live project; what is
// left here is the parts that are only I/O.
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
import { type AlertMessage, fanOut, withinRadius } from "./fanout.ts";
import { alertText, audienceFor, isPaging } from "./message.ts";

const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SERVICE_ROLE_KEY")!);

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
  if (!isPaging(ev.priority)) return new Response("skipped (not paging)", { status: 200 });

  const { data: node } = await db.from("nodes").select("name,lat,lng").eq("id", ev.node_id).single();
  const msg: AlertMessage = alertText(ev, node?.name ?? ev.node_id);

  // No phone filter: with email primary, a recipient needs only *an* address, and
  // per-channel addressability is decided in deliver(). Public opt-in is alerts_enabled.
  const { data: staff } = await db.from("profiles").select("id,phone")
    .in("role", ["admin", "officer"]);
  // Residents are only queried for wildlife; a poaching alert never leaves staff.
  const { data: pub } = audienceFor(ev) === "staff_and_residents"
    ? await db.from("profiles").select("id,phone,lat,lng").eq("role", "public").eq("alerts_enabled", true)
    : { data: [] as { id: string; phone: string | null; lat: number | null; lng: number | null }[] };
  // withinRadius checks all four coordinates. The version here checked only the
  // two latitudes and asserted the longitudes away with `!`, so two half-placed
  // rows matched on latitude alone.
  const near = (pub ?? []).filter((p) => withinRadius(node, p));

  // Dedupe by profile id (a person is one recipient regardless of how they were matched); email is
  // resolved per recipient inside fanOut() from auth.users — profiles stores no email.
  const byId = new Map<string, { id: string; phone: string | null }>();
  for (const p of [...(staff ?? []), ...near]) byId.set(p.id, { id: p.id, phone: p.phone ?? null });

  // A 'critical' event goes out on every channel a recipient has rather than the first that
  // works - see deliver(). The dashboard's open-critical queue is the other half of this: the
  // email asks for a team, and acknowledge_event() records that one is coming.
  const critical = ev.priority === "critical";
  const { sent, byChannel } = await fanOut(db, [...byId.values()], msg, ev.id ?? null, critical);
  return new Response(JSON.stringify({ sent, total: byId.size, byChannel, critical }), {
    headers: { "Content-Type": "application/json" },
  });
});
