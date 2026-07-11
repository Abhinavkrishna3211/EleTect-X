// EleTect X — officer approval-queue notify (Supabase Edge Function, Deno)
// Trigger: Database Webhook on INSERT into `officer_requests`.
// Emails every admin the moment a Forest Officer signup is queued for review, so approval
// doesn't depend on an admin happening to open the OfficerApprovals dashboard page.
//
// Reuses send-alert's secrets — no new ones needed:
//   SUPABASE_URL (platform-injected), SERVICE_ROLE_KEY, RESEND_API_KEY, ALERT_EMAIL_FROM

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SERVICE_ROLE_KEY")!);

async function sendEmail(to: string, subject: string, body: string): Promise<boolean> {
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

Deno.serve(async (req) => {
  const payload = await req.json().catch(() => null);
  if (payload === null) return new Response("unreadable payload", { status: 400 });
  const reqRow = payload.record ?? payload;                    // DB webhook sends {record}
  if (!reqRow?.full_name) return new Response("no request", { status: 400 });

  const body =
    `A Forest Officer account is pending review.\n\n` +
    `Name: ${reqRow.full_name}\nDepartment: ${reqRow.department}\n` +
    `Designation: ${reqRow.designation}\nOfficial email: ${reqRow.official_email}\n` +
    `Phone: ${reqRow.phone ?? "–"}\n\nReview it in the officer approval queue.`;
  const subject = `EleTect X — officer request pending: ${reqRow.full_name}`;

  const { data: admins } = await db.from("profiles").select("id").eq("role", "admin");
  let notified = 0;
  for (const a of admins ?? []) {
    const { data: u } = await db.auth.admin.getUserById(a.id);
    const email = u?.user?.email;
    if (!email) continue;
    if (await sendEmail(email, subject, body)) notified++;
  }
  return new Response(JSON.stringify({ notified, total: (admins ?? []).length }), {
    headers: { "Content-Type": "application/json" },
  });
});
