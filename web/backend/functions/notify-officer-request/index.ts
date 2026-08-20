// EleTect X — officer approval-queue notify (Supabase Edge Function, Deno)
// Trigger: Database Webhook on INSERT into `officer_requests`.
// Emails every admin the moment a Forest Officer signup is queued for review, so approval
// doesn't depend on an admin happening to open the OfficerApprovals dashboard page.
//
// This file is the thin HTTP entrypoint: payload guard, message build, then hand off to
// fanOut() in fanout.ts (per-admin lookup + send). Keeping the fan-out logic in fanout.ts lets
// it be unit-tested with a stub client (fanout.test.ts) with no live project — same extraction
// send-alert already went through, see its own fanout.ts.
//
// Reuses send-alert's secrets — no new ones needed:
//   SUPABASE_URL (platform-injected), SERVICE_ROLE_KEY, RESEND_API_KEY, ALERT_EMAIL_FROM

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { type AdminMessage, fanOut } from "./fanout.ts";

const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SERVICE_ROLE_KEY")!);

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
  const msg: AdminMessage = { subject, body };

  const { data: admins } = await db.from("profiles").select("id").eq("role", "admin");
  const { notified } = await fanOut(db, admins ?? [], msg);
  return new Response(JSON.stringify({ notified, total: (admins ?? []).length }), {
    headers: { "Content-Type": "application/json" },
  });
});
