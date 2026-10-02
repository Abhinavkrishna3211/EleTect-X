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
  const posted = payload.record ?? payload;                    // DB webhook sends {record}

  // The id is the only thing taken from the request; the rest is read back from
  // the table. `verify_jwt = true` proves the caller holds a key, and the anon
  // key is published in the frontend bundle, so the posted body is public input
  // - and every field of it is pasted into an email to every admin. Re-reading
  // means an admin can trust that the name in front of them is a name somebody
  // actually signed up with.
  const requestId = Number(posted?.id);
  if (!Number.isInteger(requestId)) return new Response("no request id", { status: 400 });
  const { data: reqRow } = await db.from("officer_requests")
    .select("*").eq("id", requestId).maybeSingle();
  if (!reqRow) return new Response("no such request", { status: 404 });
  // Only a request still awaiting a decision is worth an admin's attention, and
  // this makes a replay of a real id a no-op once it has been acted on.
  if (reqRow.status !== "pending") return new Response("skipped (not pending)", { status: 200 });
  if (!reqRow.full_name) return new Response("no request", { status: 400 });

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
