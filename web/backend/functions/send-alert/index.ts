// EleTect X — alert fan-out (Supabase Edge Function, Deno)
// Trigger: Database Webhook on INSERT into `events` (or call directly with an event record).
// Sends to all officers + opted-in Public users near the node, and logs to `alerts`.
//
// Delivery is channel-pluggable (see CHANNELS below). Email is the primary channel today;
// SMS is implemented but gated off pending TRAI DLT registration; WhatsApp is a registered
// stub. Each recipient is reached over the first enabled channel it has an address for.
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

const ALERT_RADIUS_KM = 3;
const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SERVICE_ROLE_KEY")!);

function kmBetween(a: number, b: number, c: number, d: number) {         // haversine
  const R = 6371, r = Math.PI / 180;
  const dLat = (c - a) * r, dLng = (d - b) * r;
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(a * r) * Math.cos(c * r) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(x));
}

// ---------- notification channels ----------
// A recipient is a profile row; email is resolved from auth.users (profiles has no email column).
interface Recipient { id: string; phone: string | null; email: string | null }
interface AlertMessage { subject: string; body: string }
interface Channel {
  name: string;                              // stored in alerts.channel
  enabled(): boolean;                        // gated by env flags / required secrets
  address(to: Recipient): string | null;     // null → recipient unreachable on this channel
  send(to: Recipient, msg: AlertMessage): Promise<boolean>;
}

// Primary: transactional email via Resend. Free tier, no DLT dependency.
const emailChannel: Channel = {
  name: "email",
  enabled: () => !!Deno.env.get("RESEND_API_KEY") && Deno.env.get("CHANNEL_EMAIL") !== "off",
  address: (to) => to.email,
  async send(to, msg) {
    const from = Deno.env.get("ALERT_EMAIL_FROM") ?? "EleTect X <onboarding@resend.dev>";
    try {
      const r = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${Deno.env.get("RESEND_API_KEY")!}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          from, to: to.email, subject: msg.subject,
          text: msg.body,
          html: `<p>${msg.body}</p>`,
        }),
      });
      return r.ok;
    } catch (_e) {
      return false;
    }
  },
};

// Second: WhatsApp. Registered stub — the pluggable slot exists so the abstraction is real,
// but no provider is wired yet (Twilio or Meta Cloud API pending). Off unless explicitly enabled.
const whatsappChannel: Channel = {
  name: "whatsapp",
  enabled: () => Deno.env.get("CHANNEL_WHATSAPP") === "on",
  address: (to) => to.phone,
  send: (_to, _msg) => Promise.resolve(false),
};

// Third: SMS. Fully implemented, but gated off until TRAI DLT registration clears (see header).
// Flip CHANNEL_SMS=on once an approved sender ID + template are live with the provider.
const smsChannel: Channel = {
  name: "sms",
  enabled: () => Deno.env.get("CHANNEL_SMS") === "on",
  address: (to) => to.phone,
  async send(to, msg) {
    const provider = Deno.env.get("SMS_PROVIDER") ?? "fast2sms";
    const num = to.phone!;
    try {
      if (provider === "twilio") {
        const sid = Deno.env.get("TWILIO_SID")!, tok = Deno.env.get("TWILIO_TOKEN")!;
        const r = await fetch(`https://api.twilio.com/2010-04-01/Accounts/${sid}/Messages.json`, {
          method: "POST",
          headers: { Authorization: "Basic " + btoa(`${sid}:${tok}`), "Content-Type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams({ To: num, From: Deno.env.get("TWILIO_FROM")!, Body: msg.body }),
        });
        return r.ok;
      }
      if (provider === "msg91") {
        const r = await fetch("https://control.msg91.com/api/v5/flow/", {
          method: "POST",
          headers: { authkey: Deno.env.get("SMS_API_KEY")!, "Content-Type": "application/json" },
          body: JSON.stringify({
            template_id: Deno.env.get("SMS_TEMPLATE_ID"), sender: Deno.env.get("SMS_SENDER"),
            recipients: [{ mobiles: num.replace("+", ""), var1: msg.body }],
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
          message: Deno.env.get("SMS_TEMPLATE_ID"), variables_values: msg.body, numbers: num.replace("+91", ""),
        }),
      });
      return r.ok;
    } catch (_e) {
      return false;
    }
  },
};

// Priority order: recipients are reached over the first enabled channel they have an address for.
const CHANNELS: Channel[] = [emailChannel, whatsappChannel, smsChannel];

// Deliver to one recipient over the first enabled+addressable channel; fall back to the next on
// failure. Logs one `alerts` row per attempt (the existing audit behaviour). Returns the channel
// name a message was accepted on, or null if none delivered.
async function deliver(to: Recipient, msg: AlertMessage, eventId: number | null): Promise<string | null> {
  for (const ch of CHANNELS) {
    if (!ch.enabled()) continue;
    const addr = ch.address(to);
    if (!addr) continue;
    const ok = await ch.send(to, msg);
    await db.from("alerts").insert({
      event_id: eventId, channel: ch.name, recipient: addr, status: ok ? "sent" : "failed",
    });
    if (ok) return ch.name;
  }
  // No enabled channel had a reachable address (or every attempt bounced). Record the
  // terminal outcome so a recipient who received nothing is queryable as `undeliverable`,
  // distinct from a single channel attempt that was logged `failed` above.
  await db.from("alerts").insert({
    event_id: eventId, channel: null, recipient: to.email ?? to.phone ?? to.id, status: "undeliverable",
  });
  return null;
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

  // Dedupe by profile id (a person is one recipient regardless of how they were matched), then
  // resolve each email from auth.users — profiles stores no email.
  const byId = new Map<string, { id: string; phone: string | null }>();
  for (const p of [...(staff ?? []), ...near]) byId.set(p.id, { id: p.id, phone: p.phone ?? null });

  let sent = 0;
  const byChannel: Record<string, number> = {};
  for (const p of byId.values()) {
    let email: string | null = null;
    try {
      const { data: u } = await db.auth.admin.getUserById(p.id);
      email = u?.user?.email ?? null;
    } catch (_e) {
      continue;   // lookup failed for this recipient only; don't 500 and drop the rest of the batch
    }
    const to: Recipient = { id: p.id, phone: p.phone, email };
    const via = await deliver(to, msg, ev.id ?? null);
    if (via) { sent++; byChannel[via] = (byChannel[via] ?? 0) + 1; }
  }
  return new Response(JSON.stringify({ sent, total: byId.size, byChannel }), {
    headers: { "Content-Type": "application/json" },
  });
});
