# EleTect X — Web App Completion Plan (post-Phase 4c → deploy-ready)

Where this fits: `CLAUDE_CODE_BUILD_BRIEF.md`'s build order, steps 1–5 (scaffold through dashboard
modules) are done — that's Phase 2 through Phase 4c, each with a QA screenshot set under
`docs/qa/`. This document carries the remaining steps (6–8) plus the gaps a live-project audit
surfaced along the way, sequenced for a one-week push. `CONTEXT.md` and `PROJECT_BLUEPRINT.md`
still win on architecture; this is the execution punch list underneath them. Update this file as
scope moves — it replaces relying on chat history for the plan.

**Target:** web app solid enough to stand on its own — real alert delivery, hardened auth, RLS
proven against misuse, the ingest path ready to receive real node data the moment hardware lands,
every screen responsive and interactive at every breakpoint, and a live Vercel deployment.

**Starting state (confirmed by direct repo audit, 11 Jul):**
- `send-alert` edge function exists in source but is **not deployed** to the live project (404 on
  invocation). SMS-only, no Email/WhatsApp fallback — build-brief step 6 was never done.
- `web/ingest` (ChirpStack MQTT → Supabase bridge) **does not exist** — zero files.
- No Vercel config anywhere in the repo — step 8 not started.
- No test files anywhere in `web/frontend` — Vitest is named in the blueprint's tooling but unused.
- Demo/seed data covers Sector-7's 8 nodes across `events`/`health`/`maintenance`; `profiles` and
  storage (`event-media` thumbnails) are thin — step 7 partially done.
- TRAI DLT registration status: unconfirmed — treat as **not ready** and build the fallback path
  (this file assumes not-ready throughout; if it clears mid-week, SMS just becomes another
  configured channel, nothing architectural changes).

---

## Day 1 (Sat) — Alerts actually work

The core promise of the product is currently broken in production. Fix that before anything else.

1. Deploy `send-alert`; confirm `supabase secrets list` shows every required var, not just that
   deploy succeeded (a misconfigured function still "deploys" and still silently drops alerts).
2. Build the pluggable notification interface the build brief always specified — `send-alert`
   currently hardcodes SMS. Extract a `channel` abstraction (`sendEmail`, `sendWhatsApp`,
   `sendSms`) so SMS being blocked on DLT doesn't block delivery entirely.
3. Wire Email as the primary channel now (Resend or Supabase's transactional email, free tier) —
   this is the fallback the backend README already names. WhatsApp (Twilio or Meta Cloud API)
   second if time allows this week; SMS stays flagged off until DLT confirms.
4. Re-run the live-proof: trigger a high-priority event, confirm officers + opted-in nearby
   residents actually receive something, confirm the demo-mode guard still blocks fan-out for
   `media_url='demo'` rows (this barrier must survive the channel refactor untouched).

**Exit criteria:** a real detection event reaches a real inbox/WhatsApp in the live project,
end to end, with the demo guard proven intact.

## Day 2 (Sun) — Auth hardening

CLAUDE.md's deployment bar names this explicitly: Supabase's default auth email sender is
rate-limited and not meant for production signups.

1. Configure a real transactional email provider (Resend/Postmark/SendGrid) for Supabase Auth's
   SMTP settings — signup confirmation, password reset, magic links all route through it.
2. Confirm officer-approval-queue email notifications (admin gets notified on a pending officer
   signup) work through the same provider, not the default sender.
3. Rate-limit and abuse-check the public signup form itself — this is where real strangers hit the
   app first.

**Exit criteria:** a real external email address can sign up, confirm, and reset password without
hitting Supabase's default sender limits.

## Day 3 (Mon) — RLS/RBAC adversarial pass

"RLS/RBAC must hold under real misuse, not just happy-path testing" — CLAUDE.md, verbatim. This
hasn't had a dedicated adversarial pass yet; QA so far has been role-correct logins, not attempts
to break the policies.

1. For each table (`profiles`, `nodes`, `events`, `health`, `alerts`, `maintenance`,
   `demo_node_snapshot`), write out what a `public`-role JWT should and shouldn't be able to do,
   then test it directly — not through the UI, through raw REST/RPC calls with a public user's
   token.
2. Confirm `public` truly cannot read another user's `phone`/`lat`/`lng` in `profiles`, cannot
   read `events`/`health`/`maintenance` rows directly (only via the public-safe view), and cannot
   call any `security definer` RPC (`run_demo_scenario`, `reset_demo_data`,
   `demo_touch_node`) — these already `revoke execute ... from public` in schema.sql; confirm it
   holds against a live call, not just by reading the grant statement.
3. Confirm `officer` is properly bounded — can't do admin-only actions like the officer-approval
   queue itself.
4. Document findings as an ADR if anything changes; otherwise a short note in this file is enough.

**Exit criteria:** a documented, executed adversarial checklist per table/role, not just a read of
the policy definitions.

## Day 4 (Tue) — `web/ingest` + ChirpStack, proven without hardware

This is the piece that lets the web side be ready the moment a node ships its first uplink —
directly answers "pave the way to connect to the platform before hardware arrives."

1. Stand up a ChirpStack instance (Cloud or self-hosted) and set its region/channel plan to
   IN865 to match the node and gateway.
2. Build `web/ingest`: subscribe to ChirpStack's MQTT uplink topic, decode the payload, validate,
   insert into `events`/`health` matching `schema.sql`'s columns exactly.
3. Prove it without physical hardware: use ChirpStack's built-in device simulator (or a manual
   `mosquitto_pub` of a synthetic uplink JSON) to push a fake node payload through MQTT and confirm
   it lands correctly in Supabase and shows up live on the dashboard.
4. Note explicitly in this file once a real gateway/node is provisioned (DevEUI/AppEUI/AppKey) —
   that's tracked separately as hardware work, not blocking this step.

**Exit criteria:** a simulated LoRaWAN uplink travels ChirpStack → `web/ingest` → Supabase →
dashboard live update, with zero physical hardware involved.

## Day 5 (Wed) — Seed completeness + full responsive/interactive pass

1. Extend seed data to cover what's thin: `profiles` (a realistic mix of admin/officer/public
   rows, including a pending-approval officer for the approval-queue screen), and at least a
   couple of real thumbnail images in the `event-media` bucket so the alerts feed and replay don't
   show broken image states.
2. Screenshot every route — public + all three dashboard roles — at mobile, tablet, and desktop,
   the same way `docs/qa/phase*` already does. Diff against the design reference where one exists;
   where it doesn't (Fleet/Planner/Demo have no static mockup), judge by internal consistency.
3. Fix every responsive/interactive break found: overflow, tap-target size, modal/drawer behavior
   on mobile, keyboard navigation, focus states. This is the "pure responsive interactive" bar —
   treat it as a checklist, not a vibe check.

**Exit criteria:** a `docs/qa/webapp-final` screenshot set covering every route × every role ×
every breakpoint, with every visual/interaction bug found in that pass fixed and re-shot.

## Day 6 (Thu) — Automated tests

Zero test files exist today despite Vitest being the named tool. This is the gap between "works
when I click through it" and "solid."

1. Vitest unit tests for the pure logic modules — `lib/dashboard.ts`, `lib/fleet.ts`,
   `lib/planner.ts`, `lib/incident.ts`, `lib/learning.ts` — these are exactly the kind of
   deterministic, side-effect-free functions that are cheap to test and highest-value to protect
   (the trend-bucketing, corridor-path, and maintenance-rule logic are all real business logic,
   not boilerplate).
2. A Playwright smoke suite that logs in as each role and asserts each dashboard route renders
   without error — reuse the patterns already proven in the `qa-phase4c-modules-screenshots.mjs`
   script rather than starting from scratch.
3. Wire both into `.github/workflows/ci.yml` so they run on every PR, not just locally.

**Exit criteria:** `npm run test` passes locally and in CI; a broken `lib/` function or a
role-routing regression fails the build instead of surfacing in the field.

## Day 7 (Fri) — Deploy + final review

1. Vercel project, environment variables set through Vercel's dashboard (never committed —
   confirm `.env.local` stays gitignored), production build verified against the production
   Supabase project, not a dev one.
2. Full regression pass on the live Vercel URL: every role login, every dashboard module, Demo
   Mode end to end, the alert pipeline from Day 1 firing against production.
3. Close this file out: mark each day's exit criteria met/not met, carry over anything unfinished
   into a dated follow-up section rather than letting it silently drop.

**Exit criteria:** `eletect-x.vercel.app` (or the chosen domain) is the live, production app —
not a preview deploy — passing the same regression checklist as local dev.

---

## Explicit risks / things that can slip

- **DLT registration** is an external bureaucratic process with its own timeline, not something
  this week's work controls. The Day 1 email/WhatsApp fallback exists specifically so alert
  delivery doesn't wait on it — SMS becomes a drop-in third channel whenever DLT clears.
  Note the actual application/approval status here once known: _(unfilled — check with the SMS
  provider and record the answer, don't leave this as an assumption)_.
- **ChirpStack + real hardware join** (Day 4 covers the simulated path only) stays tracked
  separately — SIM sourcing, gateway IN865 configuration, and node DevEUI/AppEUI/AppKey
  provisioning are hardware-arrival-gated work, not web-app work, and shouldn't block this plan.
- If a day's exit criteria isn't met, don't silently roll it into the next day's scope — add a
  dated note here so slippage is visible instead of invisible.
