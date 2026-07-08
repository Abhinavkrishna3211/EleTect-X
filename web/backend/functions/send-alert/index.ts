// EleTect X — SMS alert fan-out (Supabase Edge Function, Deno)
// Trigger: Database Webhook on INSERT into `events` (or call directly with an event record).
// Sends SMS to all officers + opted-in Public users near the node, and logs to `alerts`.
//
// Secrets (supabase secrets set ...): SUPABASE_URL, SERVICE_ROLE_KEY,
//   SMS_PROVIDER (fast2sms|msg91|twilio), SMS_API_KEY, SMS_SENDER, SMS_TEMPLATE_ID,
//   TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM   (twilio only)
// NOTE (India): SMS to Indian numbers requires TRAI **DLT registration**
//   (approved sender ID + template) via your provider. See web/backend/README.md.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const ALERT_RADIUS_KM = 3;
const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SERVICE_ROLE_KEY")!);

function kmBetween(a: number, b: number, c: number, d: number) {         // haversine
  const R = 6371, r = Math.PI / 180;
  const dLat = (c - a) * r, dLng = (d - b) * r;
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(a * r) * Math.cos(c * r) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(x));
}

async function sendSms(to: string, body: string): Promise<boolean> {
  const provider = Deno.env.get("SMS_PROVIDER") ?? "fast2sms";
  try {
    if (provider === "twilio") {
      const sid = Deno.env.get("TWILIO_SID")!, tok = Deno.env.get("TWILIO_TOKEN")!;
      const r = await fetch(`https://api.twilio.com/2010-04-01/Accounts/${sid}/Messages.json`, {
        method: "POST",
        headers: { Authorization: "Basic " + btoa(`${sid}:${tok}`), "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ To: to, From: Deno.env.get("TWILIO_FROM")!, Body: body }),
      });
      return r.ok;
    }
    if (provider === "msg91") {
      const r = await fetch("https://control.msg91.com/api/v5/flow/", {
        method: "POST",
        headers: { authkey: Deno.env.get("SMS_API_KEY")!, "Content-Type": "application/json" },
        body: JSON.stringify({
          template_id: Deno.env.get("SMS_TEMPLATE_ID"), sender: Deno.env.get("SMS_SENDER"),
          recipients: [{ mobiles: to.replace("+", ""), var1: body }],
        }),
      });
      return r.ok;
    }
    // default: fast2sms (India, DLT route)
    const r = await fetch("https://www.fast2sms.com/dev/bulkV2", {
      method: "POST",
      headers: { authorization: Deno.env.get("SMS_API_KEY")!, "Content-Type": "application/json" },
      body: JSON.stringify({
        route: "dlt", sender_id: Deno.env.get("SMS_SENDER"),
        message: Deno.env.get("SMS_TEMPLATE_ID"), variables_values: body, numbers: to.replace("+91", ""),
      }),
    });
    return r.ok;
  } catch (_e) {
    return false;
  }
}

Deno.serve(async (req) => {
  const payload = await req.json().catch(() => ({}));
  const ev = payload.record ?? payload;                       // DB webhook sends {record}
  if (!ev?.node_id) return new Response("no event", { status: 400 });
  if ((ev.priority ?? "normal") !== "high") return new Response("skipped (not high)", { status: 200 });

  const { data: node } = await db.from("nodes").select("name,lat,lng").eq("id", ev.node_id).single();
  const msg = `EleTect X: elephant detected near ${node?.name ?? ev.node_id} ` +
    `(${Math.round((ev.confidence ?? 0) * 100)}% confidence). Stay alert, avoid the area.`;

  const { data: staff } = await db.from("profiles").select("phone")
    .in("role", ["admin", "officer"]).not("phone", "is", null);
  const { data: pub } = await db.from("profiles").select("phone,lat,lng")
    .eq("role", "public").eq("alerts_enabled", true).not("phone", "is", null);
  const near = (pub ?? []).filter((p) =>
    p.lat != null && node?.lat != null && kmBetween(node.lat, node.lng, p.lat!, p.lng!) <= ALERT_RADIUS_KM);
  const recipients = [...new Set([...(staff ?? []), ...near].map((r) => r.phone!).filter(Boolean))];

  let sent = 0;
  for (const to of recipients) {
    const ok = await sendSms(to, msg);
    await db.from("alerts").insert({ event_id: ev.id, channel: "sms", recipient: to, status: ok ? "sent" : "failed" });
    if (ok) sent++;
  }
  return new Response(JSON.stringify({ sent, total: recipients.length }), {
    headers: { "Content-Type": "application/json" },
  });
});
