// EleTect X — officer-request notify fan-out. Extracted from index.ts so this logic is
// unit-testable (see fanout.test.ts) with a stub client, without standing up an HTTP server,
// reading secrets, or contacting the real DB. index.ts stays the thin Supabase Edge entrypoint
// and injects the live client here. Mirrors send-alert/fanout.ts's extraction; this domain has
// only one channel (email, no retry/multi-channel), so there is no channel table to fan out over —
// just the same per-recipient getUserById guard.
//
// The Supabase client is a TYPE-only import: nothing here runs at module load, so the module
// (and its test) load with no network and no env. sendEmail reads secrets lazily inside itself.

import type { SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";

export interface AdminMessage { subject: string; body: string }

export async function sendEmail(to: string, subject: string, body: string): Promise<boolean> {
  const from = Deno.env.get("ALERT_EMAIL_FROM") ?? "EleTect X <onboarding@resend.dev>";
  try {
    const r = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${Deno.env.get("RESEND_API_KEY")!}`,
        "Content-Type": "application/json",
      },
      // Text only, deliberately. Every field of this body comes from
      // raw_user_meta_data at public signup, so an applicant could close the <p>
      // and write their own markup - a forged "APPROVED, no action needed" line
      // and a working link, delivered to every admin from the project's own
      // verified sending domain. Re-reading the row (which index.ts does) proves
      // somebody really signed up with these values; it does not make them safe
      // to interpolate. The html part was also wrapping a body full of \n in one
      // <p>, which collapsed it to a single run-on line.
      body: JSON.stringify({ from, to, subject, text: body }),
    });
    return r.ok;
  } catch (_e) {
    return false;
  }
}

// Email every admin in the list. A getUserById lookup that throws skips only that admin — it
// must not 500 the caller and drop everyone later in the batch (same guard as send-alert's
// fanOut, WEBAPP_COMPLETION_PLAN.md's Day 3 fix).
// admin_set_deactivated() blocks sign-in by writing auth.users.banned_until, and
// deliberately leaves profiles.role alone - the person is still an officer, they
// just cannot get in. Every recipient query here selects on role, so without this
// check a deactivated account keeps receiving node names, places, species and
// confidences at a personal mailbox indefinitely; for a deactivated admin that is
// every officer applicant's name, department, official email and phone. Revoking
// access covered the front door and not the mail.
//
// Checked here rather than in the recipient query because the admin API lookup
// below already has the user row in hand - auth.users is not reachable through
// PostgREST, so the alternative is a second round-trip per person for data we
// were handed anyway.
//
// 'infinity' is what admin_set_deactivated writes, and Date.parse cannot read it,
// so an unparseable value counts as banned. Failing closed here costs a
// deactivated account one missed email; failing open leaks to someone whose
// access was deliberately revoked.
function isDeactivated(bannedUntil: string | null | undefined): boolean {
  if (!bannedUntil) return false;
  const until = Date.parse(bannedUntil);
  return Number.isNaN(until) || until > Date.now();
}

export async function fanOut(
  db: SupabaseClient,
  admins: { id: string }[],
  msg: AdminMessage,
): Promise<{ notified: number }> {
  let notified = 0;
  for (const a of admins) {
    let email: string | undefined;
    try {
      const { data: u } = await db.auth.admin.getUserById(a.id);
      if (isDeactivated(u?.user?.banned_until)) continue;
      email = u?.user?.email;
    } catch (_e) {
      continue;   // lookup failed for this admin only; don't 500 and drop the rest of the batch
    }
    if (!email) continue;
    if (await sendEmail(email, msg.subject, msg.body)) notified++;
  }
  return { notified };
}
