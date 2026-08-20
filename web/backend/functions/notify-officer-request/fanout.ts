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
      body: JSON.stringify({ from, to, subject, text: body, html: `<p>${body}</p>` }),
    });
    return r.ok;
  } catch (_e) {
    return false;
  }
}

// Email every admin in the list. A getUserById lookup that throws skips only that admin — it
// must not 500 the caller and drop everyone later in the batch (same guard as send-alert's
// fanOut, WEBAPP_COMPLETION_PLAN.md's Day 3 fix).
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
      email = u?.user?.email;
    } catch (_e) {
      continue;   // lookup failed for this admin only; don't 500 and drop the rest of the batch
    }
    if (!email) continue;
    if (await sendEmail(email, msg.subject, msg.body)) notified++;
  }
  return { notified };
}
