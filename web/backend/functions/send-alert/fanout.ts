// EleTect X — alert delivery machinery: pluggable channels + per-recipient fan-out.
// Extracted from index.ts so this logic is unit-testable (see fanout.test.ts) with a stub
// client, without standing up an HTTP server, reading secrets, or contacting the real DB.
// index.ts stays the thin Supabase Edge entrypoint and injects the live client here.
//
// The Supabase client is a TYPE-only import: nothing here runs at module load, so the module
// (and its test) load with no network and no env. Channels read env lazily inside their methods.

import type { SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";

// ---------------------------------------------------------------------------
// Recipient proximity
// ---------------------------------------------------------------------------

// How close an opted-in resident must be to the node that detected something.
export const ALERT_RADIUS_KM = 3;

export interface Located { lat: number | null; lng: number | null }

// Null when either point is not fully located, rather than a number that would
// be wrong. The caller has to decide what an unknown distance means, and this
// is a join across two tables that are each independently allowed to be
// incomplete: `nodes.lat/lng` is null until an admin commissions the node, and
// `profiles.lat/lng` is null until a resident sets their location, which is
// granted to `authenticated` one column at a time and so can be written half
// filled. Both are routine, neither is an error, and both must mean "cannot
// match" rather than "matches at longitude zero".
//
// Non-finite values are rejected for the same reason: `double precision`
// accepts NaN and Infinity, the column grant lets a client write them, and NaN
// propagating into a `<=` comparison would decide this silently.
export function kmBetween(a: Located | null | undefined, b: Located | null | undefined): number | null {
  if (!a || !b) return null;
  for (const v of [a.lat, a.lng, b.lat, b.lng]) {
    if (v == null || !Number.isFinite(v)) return null;
  }
  const R = 6371, r = Math.PI / 180;                                     // haversine
  const dLat = (b.lat! - a.lat!) * r, dLng = (b.lng! - a.lng!) * r;
  const x = Math.sin(dLat / 2) ** 2 +
    Math.cos(a.lat! * r) * Math.cos(b.lat! * r) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(x));
}

// An unknown distance is not a match. Failing the other way would page every
// resident whose location the system does not know, which on a fox-quiet night
// is the whole division; the resident dashboard tells them their location is
// missing instead.
export function withinRadius(
  node: Located | null | undefined,
  person: Located | null | undefined,
  radiusKm = ALERT_RADIUS_KM,
): boolean {
  const km = kmBetween(node, person);
  return km != null && km <= radiusKm;
}

// ---------------------------------------------------------------------------
// Delivery
// ---------------------------------------------------------------------------

// A recipient is a profile row; email is resolved from auth.users (profiles has no email column).
export interface Recipient { id: string; phone: string | null; email: string | null }
export interface AlertMessage { subject: string; body: string }
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

// Third: SMS. Fully implemented, but gated off until TRAI DLT registration clears (see index.ts).
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

// Deliver to one recipient. Normally this stops at the first enabled channel that accepts, and
// falls through to the next only on failure.
//
// `everyChannel` sends on all of them instead, for a 'critical' event — the node fired its top
// tier and the animal stayed, so someone has to physically go. The ordinary rule optimises for
// not sending the same thing twice, which is right for the alerts that arrive every night and
// wrong for the one that needs a person to look at their phone now. A duplicate is a far cheaper
// failure here than an unread email.
//
// It changes nothing today, and that is worth stating rather than discovering: email is the only
// enabled channel (WhatsApp is a stub, SMS waits on TRAI DLT registration), so every recipient
// has exactly one channel either way. It is the behaviour that should already be in place for
// when SMS clears, because that is the moment the distinction starts mattering and the worst
// time to be deciding it.
//
// Logs one `alerts` row per attempt (the existing audit behaviour). Returns the channel names
// that accepted, newest attempt last — empty if nothing delivered.
export async function deliver(
  db: SupabaseClient, to: Recipient, msg: AlertMessage, eventId: number | null,
  everyChannel = false,
): Promise<string[]> {
  const accepted: string[] = [];
  for (const ch of CHANNELS) {
    if (!ch.enabled()) continue;
    const addr = ch.address(to);
    if (!addr) continue;
    const ok = await ch.send(to, msg);
    await db.from("alerts").insert({
      event_id: eventId, channel: ch.name, recipient: addr, status: ok ? "sent" : "failed",
    });
    if (ok) {
      accepted.push(ch.name);
      if (!everyChannel) break;
    }
  }
  if (accepted.length) return accepted;
  // No enabled channel had a reachable address (or every attempt bounced). Record the
  // terminal outcome so a recipient who received nothing is queryable as `undeliverable`,
  // distinct from a single channel attempt that was logged `failed` above.
  await db.from("alerts").insert({
    event_id: eventId, channel: null, recipient: to.email ?? to.phone ?? to.id, status: "undeliverable",
  });
  return accepted;
}

// Fan out one message to a deduped recipient list. Each recipient's email is resolved from
// auth.users here (profiles stores no email). A lookup that throws skips only that recipient —
// it must not 500 the caller and drop everyone later in the batch.
export async function fanOut(
  db: SupabaseClient,
  people: { id: string; phone: string | null }[],
  msg: AlertMessage,
  eventId: number | null,
  everyChannel = false,
): Promise<{ sent: number; byChannel: Record<string, number> }> {
  let sent = 0;
  const byChannel: Record<string, number> = {};
  for (const p of people) {
    let email: string | null = null;
    try {
      const { data: u } = await db.auth.admin.getUserById(p.id);
      email = u?.user?.email ?? null;
    } catch (_e) {
      continue;   // lookup failed for this recipient only; don't 500 and drop the rest of the batch
    }
    const to: Recipient = { id: p.id, phone: p.phone, email };
    const via = await deliver(db, to, msg, eventId, everyChannel);
    // `sent` counts people reached, not messages sent - one recipient reached on two channels
    // is still one person warned, and a count that says otherwise would read as better coverage
    // than there is. byChannel counts attempts accepted, so the two differ under everyChannel.
    if (via.length) sent++;
    for (const ch of via) byChannel[ch] = (byChannel[ch] ?? 0) + 1;
  }
  return { sent, byChannel };
}
