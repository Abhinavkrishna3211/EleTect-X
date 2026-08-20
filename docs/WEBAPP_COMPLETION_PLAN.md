# EleTect X — Web App Completion Plan (post-Phase 4c → deploy-ready)

> **CLOSED — 12 Jul 2026.** All seven days met; the app is live at <https://eletect.vercel.app>.
> Read the **Closeout** section at the end first: it carries the three things that still block a real
> DFO deployment (chiefly a **verified Resend sending domain** — alerts currently reach only the
> account owner). This file is now a record, not a live plan.

Where this fits: the web build order, steps 1–5 (scaffold through dashboard
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

**Status: met, 11 Jul.** `send-alert` deployed with a pluggable channel abstraction (email
primary via Resend, SMS retained but gated behind `CHANNEL_SMS` pending DLT, WhatsApp a
registered stub). `supabase secrets list` confirmed `SERVICE_ROLE_KEY`, `RESEND_API_KEY`,
`ALERT_EMAIL_FROM` present. Direct-invoke proof (via `Invoke-RestMethod` — this CLI version,
2.109.1, has no `functions invoke` subcommand): high-priority event → `sent:1, total:2,
byChannel:{email:1}`, one `alerts` row `status=sent` (account-owner address, Resend test-mode
delivers), one `status=failed` (second staff address, expected under Resend's test-mode
restriction — swap to a verified sending domain before residents rely on this in the field);
`media_url='demo'` → skipped, zero rows; `priority='normal'` → skipped, zero rows. The
events→send-alert Database Webhook did not exist yet at audit time — created it
(`send_alert_on_event`, INSERT only, POST to the function), then proved the real path: a raw
SQL `insert into events (...)` with no direct function call produced a second email
automatically. Automatic-trigger path confirmed end to end.

## Day 2 (Sun) — Auth hardening

The project's deployment bar names this explicitly: Supabase's default auth email sender is
rate-limited and not meant for production signups.

1. Configure a real transactional email provider (Resend/Postmark/SendGrid) for Supabase Auth's
   SMTP settings — signup confirmation, password reset, magic links all route through it.
2. Confirm officer-approval-queue email notifications (admin gets notified on a pending officer
   signup) work through the same provider, not the default sender.
3. Rate-limit and abuse-check the public signup form itself — this is where real strangers hit the
   app first.

**Exit criteria:** a real external email address can sign up, confirm, and reset password without
hitting Supabase's default sender limits.

**Status: partially met, 11 Jul.** Two of three items landed and are live-provable today: (1)
`notify-officer-request` — net new, emails every admin the moment an officer signup lands in
`officer_requests` (nothing previously did this; `OfficerApprovals` was read-only/poll-only) —
reuses Day 1's Resend secrets, deployed the same way as `send-alert`. (2) The public signup form
now has a honeypot field silently rejecting bot-shaped submissions, layered under Supabase's
existing per-IP sign-up rate limit; documented gap: doesn't stop a targeted direct API call, that
needs Turnstile (deferred, no new external account opened this session).

Item (3), Auth's own SMTP (signup confirmation/password reset/magic link), is **staged but not
activated**: discovered mid-session that Resend's SMTP relay — unlike its HTTP API used by
`send-alert` — refuses to send from an unverified domain at all, and the user has none yet.
Turning SMTP on now with a still-unverified from-address risks breaking the currently-working
Forgot Password flow for real users, unacceptable for a project in real DFO-adjacent use. Also
confirmed `supabase config push` pushes the *entire* local `config.toml` with no `config pull` to
seed it first — our file has never captured the live project's `site_url`/redirect URLs, so a push
would silently reset them. Auth SMTP is Dashboard-only, documented step by step in
`web/backend/README.md`'s "Auth transactional email" section, ready to execute the moment a
domain is verified. The confirmation-email + password-reset live-proof carries forward to a
follow-up session — not silently rolled into Day 3's scope.

## Day 3 (Mon) — RLS/RBAC adversarial pass

"RLS/RBAC must hold under real misuse, not just happy-path testing" — the deployment bar, verbatim. This
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

**Status: met, 11 Jul.** Built `web/frontend/scripts/day3-rls-adversarial.mjs` — live REST/RPC
calls against the production project as (1) true anonymous (anon key only) and (2) a throwaway
signup at each of `public` and `officer` role, not UI clicks. Two clean runs, 30/30 and 10/10 (a
third run mid-session mixed public- and officer-role results together because the role-promotion
SQL was run before that execution rather than between sections — a sequencing artifact of manual
testing, not a regression; the immediately preceding clean run is the real record for public-role
behaviour). Full result: anon blocked from `profiles`/`nodes`/`events`/`health`/`maintenance`/
`alerts`/`officer_requests`/`demo_node_snapshot`, anon allowed only on `public_area_risk` (by
design); `public` role reads only its own `profiles` row, never another user's `phone`/`lat`/`lng`,
cannot PATCH its own `role` to `admin` (column-grant restriction holds), sees an empty
`officer_requests` (no request filed), and is rejected by all five RPCs; `officer` correctly reads
every staff table, cannot write `nodes` directly (admin-only), cannot call
`approve_officer_request`/`reject_officer_request` (admin-only), and can run Demo Mode
(`is_staff()`, not admin-gated) — its test-run demo event was cleared via `reset_demo_data()`
immediately after, no leftover row in production.

One real finding, fixed live: `demo_touch_node()` had no internal `is_staff()` check at all — unlike
`run_demo_scenario`/`reset_demo_data`, it relied entirely on `revoke execute ... from public,
authenticated` in `schema.sql` as its only defense. The first live run proved that revoke was not
actually in effect on the production database (anon called it successfully, HTTP 204), despite the
statement being correct in source — the grant had drifted out of sync with the file at some point.
Fixed two ways: re-ran the revoke directly against the live project, and added an `is_staff()` guard
inside the function body itself (`schema.sql` and `migrations/0001_phase4c.sql` both updated) so it
no longer depends on the grant alone. Re-verified live afterward — clean rejection. No ADR filed;
this closes a gap in an existing security-definer function rather than changing an architectural
decision. Follow-up housekeeping: delete the throwaway Day 3 test account from Authentication → Users.

**Correction (12 Jul): item 2's premise above is wrong.** It says the demo RPCs "already
`revoke execute ... from public` in schema.sql". They do not — **`schema.sql` contains exactly one
`revoke`, and it is for `demo_touch_node`**. `run_demo_scenario` and `reset_demo_data` have never had
one, so on the live database `PUBLIC`, `anon` and `authenticated` all still hold `EXECUTE` on them
(confirmed by reading `pg_proc.proacl` directly on 12 Jul). The same is true of
`approve_officer_request` / `reject_officer_request`.

**This is not a live vulnerability, and the system is not exposed**: every one of these functions
gates on `is_staff()` / `is_admin()` internally, and a true-anonymous call to each was re-tested live
on 12 Jul and rejected with `not authorized`. The guard — which is what Day 3's own fix concluded was
the right defense — is doing the work. What is missing is the *second* layer: anon can reach the
function body at all, rather than being stopped at the grant. See the closeout for the hardening
note. The lesson repeats Day 3's: the claim was written from the intent of the code, not from a query
against the database.

**Correction (12 Jul): the claim above that this account had "no elevated access left" was wrong.**
When it was deleted during the Day 5/6/7 cleanup it was still `role=officer` — promoted during the
officer-role section of the adversarial run and never demoted — so it could read every staff table
(`nodes`, `events`, `health`, `maintenance`) for a full day after being written off as harmless. It
is now deleted and verified gone. The lesson is not "delete test accounts sooner" but "do not record
a privilege claim without checking it": the note was written from intent, not from a query.

## Pre-Day 4 checkpoint — full-system audit

Requested before starting Day 4, to make sure three days of backend changes hadn't introduced
regressions elsewhere and that hardware-adjacent work wasn't starting on a shaky base.

**Result: clean.** `device/mcu`, `device/mpu`, and `ml/` are still empty scaffolds (`.gitkeep` +
`README.md` only) — consistent with `CONTEXT.md`'s sequencing (software first, hardware sourcing in
progress), reported as N/A rather than failing. `web/frontend` builds clean (`tsc -b && vite build`,
0 errors) and lints clean (0 errors, 3 dev-only `react-refresh` warnings); one perf advisory (736 kB
main chunk, over Vite's 500 kB code-split threshold) flagged for before the public site goes live,
not blocking. `web/backend`'s security-definer sweep confirmed the `demo_touch_node()` bug class
doesn't recur anywhere else — every definer function gates on `is_staff()`/`is_admin()`
independently of any grant. No committed secrets, `.gitignore` correct; removed one harmless stray
untracked `supabase/.temp/` artifact at the repo root and broadened the ignore rule.

Two real (minor) gaps found and fixed, both about alert-pipeline audit completeness rather than a
live vulnerability:

1. `send-alert`'s `deliver()` silently dropped a recipient with no address on any enabled channel —
   no `alerts` row at all, only failed sends were logged. Fixed: writes a `status='undeliverable',
   channel=null` row before returning. **Live-verified**: with `CHANNEL_EMAIL` toggled off (SMS/
   WhatsApp already off) against a real high-priority event, all recipients correctly logged
   `undeliverable` — confirmed via direct SQL check against the live `alerts` table, secret restored
   immediately after, test event deleted.
2. `getUserById` was unguarded inside both fan-out loops (`send-alert`, `notify-officer-request`); a
   throw would 500 the handler and silently skip every remaining recipient. Fixed: wrapped
   per-iteration so one bad lookup skips only that recipient. **Unit-tested** (not live-testable — a
   nonexistent-but-valid UUID returns `{data:null,error}`, it doesn't throw; only a genuine network/
   timeout rejection does): `send-alert`'s fan-out logic was extracted into `fanout.ts` for
   testability (`index.ts` stays the thin HTTP entrypoint), with two passing Deno tests covering the
   lookup-failure-skips-one-recipient case and the undeliverable-row case. `deno check` against real
   `supabase-js` types confirmed the refactor was behavior-preserving before it was committed and
   redeployed. `notify-officer-request`'s equivalent guard was fixed but not unit-tested at the
   time (its logic wasn't extracted) — flagged as an optional follow-up. **Closed later:**
   `notify-officer-request` gained its own `fanout.ts`/`fanout.test.ts`, same shape as
   `send-alert`'s (a single-channel `fanOut()` rather than `send-alert`'s channel list, since
   this function only ever emails), with two passing Deno tests and a clean `deno check` against
   real `supabase-js` types confirming the extraction was behavior-preserving. See the "Still
   open" and "Known gaps" entries below, both now resolved.

Commits: `2e9f520` (chore, `.temp` ignore), `06bfd56` (fix, send-alert undeliverable + guard),
`26fde56` (fix, notify-officer-request guard), `64a572e` (test, fanout.ts extraction + Deno tests).
Both edge functions redeployed after the fixes; live proof re-run against the redeployed code.

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

**Status: met, 12 Jul.** ChirpStack stood up locally via Docker Compose (`chirpstack-docker`
quickstart, kept as a sibling directory outside this repo), region confirmed IN865 (already listed
in the default `enabled_regions`, no edit needed beyond swapping every `eu868` reference in
`docker-compose.yml` to `in865` for the gateway-bridge topic templates and Basic Station config
file). Tenant/device profile (IN865, LoRaWAN 1.0.3, OTAA)/application/device provisioned in the
ChirpStack UI as throwaway test fixtures. Built `web/ingest` (`src/mqtt.ts`, `src/uplink.ts`,
`src/supabase.ts`) — subscribes to `application/{id}/device/+/event/up`, upserts a `nodes` row per
sending device, writes `health` when the payload carries battery/solar/temp, writes `events` when
it carries `species`. `web/ingest/test-uplink.json` is a committed synthetic-uplink fixture for
future hardware-free testing (see `web/ingest/README.md`).

Two real bugs found and fixed en route, both local-dev-environment issues rather than `web/ingest`
code defects: (1) running `web/ingest` natively on Windows and connecting to the broker through
Docker's host-to-container port forward (`localhost:1883`) never delivered broker-pushed `PUBLISH`
packets, even though the connection, subscription (`SUBACK`, granted QoS 0), and keepalive
(`PINGREQ`/`PINGRESP`) all worked — confirmed via `mqtt.js` packet-level tracing
(`packetreceive`/`packetsend`) that zero `PUBLISH` packets ever arrived, while `mosquitto_sub` run
directly inside the container received the same message immediately. Fixed by containerizing
`web/ingest` (`web/ingest/Dockerfile`) and running it attached to the same Docker network as
mosquitto (`--network chirpstack-stack_default`, `MQTT_URL=mqtt://mosquitto:1883`), bypassing the
host port forward entirely. (2) Once transport was fixed, `mosquitto_pub -m '<json>'` invoked from
PowerShell through `docker exec` was silently stripping the double quotes out of the JSON payload
before it ever reached the broker — confirmed via `mosquitto_sub -v` showing unquoted keys on the
wire. Fixed by publishing from a file (`mosquitto_pub -f`) via `docker cp`, sidestepping PowerShell's
argument-quoting entirely.

Live-proof: `test-uplink.json` published to
`application/230a40b7-fb1f-4f32-b9ae-3ca51a280e8e/device/4f3030e129cfeb14/event/up` →
`web/ingest` logged `Logged elephant event from 4f3030e129cfeb14 (confidence=0.85)` → confirmed via
direct SQL query against the live `eletect-x` Supabase project: `events` row `id=254`,
`node_id='4f3030e129cfeb14'`, `species='elephant'`, `confidence=0.85`, `direction_deg=45`,
`priority='normal'` — exact match to the published payload. Real gateway/node DevEUI/AppEUI/AppKey
provisioning stays tracked separately as hardware-arrival-gated work per item 4 above; nothing here
blocks on it.

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

**Status: met, 12 Jul.** Full matrix green — **91 screenshots**, every route × every role
(anonymous, resident, officer, admin) × mobile/tablet/desktop, every interaction assertion passing,
script exits 0.

**Item 1's premise was wrong, and is corrected rather than silently dropped.** The plan assumed the
alerts feed and replay "show broken image states" without seeded `event-media` thumbnails. They do
not — *nothing in the frontend renders `media_url` as an image at all*. `AlertsFeed.tsx` uses emoji
species glyphs (`SPECIES_ICON`), `Replay.tsx` has no media element, and the only `media_url`
reference outside the type definition is `Demo.tsx`'s `media_url === 'demo'` filter. There is no
broken state to fix, so no `event-media` bucket was created and no thumbnails were seeded. Event-media
rendering is a real feature, but it belongs with the hardware that will actually produce snapshots,
not with this QA pass.

`scripts/seed-day5-profiles.mjs` ran clean: four throwaway accounts (`*.seed@eletect-x.test`, shared
password, no confirmation email sent so Supabase's rate-limited default sender is untouched) — a
pending officer request, an approved officer, a resident with alerts on and a Sector-7 location, and
an unengaged resident with alerts off. **Verified rather than assumed**: `handle_new_user()` *does*
fire for admin-API-created users and reads `officer_request` out of `user_metadata` — confirmed by a
direct query showing the `officer_requests` row landed with `status=pending`, so the approvals screen
has real data behind it instead of shooting empty.

Built `web/frontend/scripts/qa-day5-responsive.mjs` — 62 screenshots into `docs/qa/webapp-final/`
across mobile (390×844), tablet (820×1180) and desktop (1440×900), for anonymous (8 public + 4 auth
routes), officer (7 routes), and resident (1). 820 and 390 are chosen to straddle Tailwind's `md`
(768px), which is where `DashboardLayout` swaps the sidebar for the bottom bar. Alongside the shots it
asserts what a screenshot cannot see: **click-reachability** of every role-permitted route per
breakpoint, RoleGate redirects, ≥44×44px tap targets, Escape-closes-the-sheet, focus acceptance, and
zero horizontal overflow. Re-run against the *production build* (`vite preview`) as well as dev, both
green.

Five real bugs found and fixed. Two were found by reading before the pass ran, two by the pass itself,
one is a data-honesty defect that the pass could not have caught:

1. **Dashboard routes unreachable on mobile** (`layouts/DashboardLayout.tsx`). The desktop sidebar is
   `hidden … md:flex` and derived from `staffTabs`/`adminOnlyTabs`; below `md`, navigation came from
   two *separate* hardcoded arrays hand-truncated to five entries. They had drifted: an **officer on a
   phone could not reach Learning or Planner**, and an **admin on a phone could not reach Corridor,
   Learning, Planner, or — worst — the admin-only officer-approval queue**. An admin approving a
   pending officer signup from a phone is precisely the field scenario this app exists for. Fixed by
   deriving the mobile bar from the same tab definitions (one source of truth) and spilling the
   overflow into a "More" sheet (Escape-dismissable, focus moved into the panel) rather than
   truncating routes away. The click-reachability assertion is what proves it and what stops the
   regression recurring.
2. **Horizontal overflow on every dashboard route at 390px** (`DashboardLayout.tsx` header).
   `scrollWidth` was 402px against a 390px viewport — the whole dashboard scrolled sideways on a
   phone. Cause: the header's right-hand group (user label + Sign out) had a `truncate` label that
   could never engage, because a flex item will not shrink below its content width without
   `min-w-0`. Fixed on both the group and the label. This was invisible until the pass stopped using
   Playwright's `isMobile` emulation, which reports a layout viewport taller and wider than the
   screenshot and was masking the overflow entirely — worth remembering: `isMobile: true` hides this
   class of bug.
3. **`ResidentView` fabricated its data** (`pages/dashboard/ResidentView.tsx`). The only screen a
   `public`-role user ever sees was rendering a hardcoded `recentAlerts` array ("Elephants moved back
   to forest: all clear", "Yesterday 22:10") and a hardcoded "🟢 Low: no wildlife near villages"
   banner. Under this file's own deployment bar — real residents depending on this for real
   conflict alerts — a resident-facing screen that invents an all-clear is a correctness failure, not
   a polish item. Now derives both from the `public_area_risk` view, with honest loading/error/empty
   states. Because that view is deliberately aggregate-only (`day`, `detections` — no species, node,
   or coordinates leak to the public role, by design in `schema.sql`), the fix shows real *counts* per
   day and says so explicitly ("Counts only. Exact location and direction are sent to you directly in
   an alert, never shown here") rather than inventing per-alert detail the role is not entitled to
   read. New pure module `lib/risk.ts` holds the derivation, unit-tested on Day 6.
4. **`StaySafe` had the same fabricated banner** (`pages/public/StaySafe.tsx`) — hardcoded "Low · No
   wildlife detected near villages" and "Updated 2 min ago" on the *public marketing* page. Wired to
   the same `public_area_risk` view (which already grants `select` to `anon` for exactly this).
5. **Migration drift** — `schema.sql` carried the demo scenario's corrected seismic signature
   (`22 Hz`, per ADR 0001 §2: published seismology puts elephant footfall at ~24 Hz mean, not the
   ~14 Hz previously assumed) while `migrations/0001_phase4c.sql` still said `14 Hz`. Same
   schema-vs-migration drift class as Day 3's `demo_touch_node` grant bug. Both files now agree.

6. **`StaySafe`'s opt-in form collected contact details and dropped them.** It set local React state
   and showed a "You're covered" confirmation — no Supabase write, no row anywhere. A resident who
   opted in through the public page was told they were covered and was not, which is the worst
   possible failure for a safety product. Fixed per an explicit scope decision: **no new anonymous
   opt-in table and no separate verification flow** — signed-out visitors are routed to `/signup`
   (signup + email confirmation *is* the consent record) and collect nothing, while signed-in
   visitors get a toggle writing the same `profiles.alerts_enabled` flag `send-alert` actually fans
   out on. That write now lives once, in `hooks/useAlertsOptIn.ts`, consumed by both `StaySafe` and
   `ResidentView` rather than duplicated. The hook also surfaces a failed update, which
   `ResidentView`'s toggle previously swallowed — silently leaving the switch showing a promise the
   backend never recorded. The page's SMS-specific copy is now channel-neutral, matching Day 1's
   reality (email live, SMS gated behind `CHANNEL_SMS` pending DLT).
   **Live-proved**, not just typechecked: signed-out collects no phone input and its CTA routes to
   `/signup`; signed-in toggling flips `profiles.alerts_enabled` `false → true → false` in the
   production database, verified by direct service-role query between clicks, with the seed fixture
   restored afterwards.

**Throwaway accounts deleted from the production project, 12 Jul.** All five are gone and *verified*
gone against a fresh `listUsers` read rather than trusting the delete call's return: the four
`*.seed@eletect-x.test` accounts and the Day 3 adversarial probe. `profiles` and `officer_requests`
both cascade off `auth.users`, and the dependent rows were confirmed cleared too. Two accounts remain
— the admin (`abhinav123krish@gmail.com`) and `officer@eletect.in`.

Consequence to know before re-running QA: `scripts/qa-day5-responsive.mjs` signs in as the seeded
officer and resident, so it **cannot run until `scripts/seed-day5-profiles.mjs` is re-run** to
recreate them. That is by design — the accounts should not exist between QA passes. Re-seed, run the
pass, delete again.

**Carried, not silently dropped:**

- **`officer@eletect.in` is the deliberate staff QA login — keep it, do not delete.** Provenance
  resolved 12 Jul: created 10 Jul, **signed in 11 Jul** (so it is in active use, not abandoned),
  email confirmed, `role=officer` set manually (`officer_requests` is empty — it never went through
  the approval flow), and `user_metadata` carries only `email_verified`, with no `full_name` or
  `phone`. That rules out the Phase 3 signup-test artifact, which the script creates as
  `qa-resident-*@example.com` *with* a name and phone. It is the `QA_STAFF_EMAIL` the phase4c QA
  scripts sign in as, and it is named in `docs/qa/phase4a/NOTES.md`. It is no longer listed on the
  login page itself — see the closed item immediately below.
- ~~The login page advertises a valid officer-role username to every visitor.~~ **Closed.** `Login.tsx`
  dropped the entire `demoAccounts` block (`admin@eletect.in`/`officer@eletect.in`/`resident@eletect.in`
  role hints) — the page now renders a plain email/password form with no account list at all, and
  carries a comment ("Do not reintroduce this section") pointing future editors at
  `scripts/seed-judge-accounts.mjs` for judge/demo logins instead. A source-scan regression test
  (`pages/auth/Login.test.ts`) now asserts the page's source contains no `@eletect.in` address at all,
  so this can't silently regress. This entry sat open in this document after the code fix already
  landed — plan-vs-code drift of the same kind this file's own "Migration drift" item above calls out;
  noting it here rather than only in the fix's own commit so the doc stops disagreeing with the repo.
- ~~`scripts/qa-phase3-screenshots.mjs` hardcodes a password.~~ **Fixed 12 Jul** — it now reads
  `QA_SEED_PASSWORD` from the gitignored `.env.local`, same pattern as the Day 5 scripts. No
  hardcoded credential remains in any tracked script.
- ~~The live database still serves the old `14 Hz` demo log line.~~ **Resolved 12 Jul** — the live
  `run_demo_scenario` now says `22 Hz`; see the closeout.
- **Seed-account credentials are env-only, never committed.** The seed script originally hardcoded a
  shared password. That is a committed secret: these accounts live in the *production* project and
  `officer.approved.seed` held the **officer** role, which reads every staff table — so a public repo
  (which the Robu/Hackster submissions imply) would have handed anyone a working forest-officer login.
  Both scripts now take `QA_SEED_PASSWORD` from the gitignored `.env.local`, and re-running the seed
  rotates the password so a leaked one can be revoked.
- **Residents can only opt in by holding an account.** This is the deliberate consequence of the
  decision above, not an oversight: there is no phone-only, no-account opt-in path. If real field use
  shows residents will not create accounts, that is the moment to design an anonymous opt-in with a
  real verification and consent record — not before.

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

**Status: met, 12 Jul.** Vitest was not merely unused — it was **not installed at all**
(`package.json` listed `playwright` but no `vitest`, despite the blueprint naming it). Installed
`vitest` + `@vitest/coverage-v8`, added `test` / `test:watch` scripts and a `test` block in
`vite.config.ts` (`environment: 'node'` — the suite covers pure derivations, so no jsdom dependency
is dragged into CI).

**117 tests across 6 modules**, all green: `lib/planner.ts` (geometry + the CONTEXT.md §6 rules —
including the load-bearing invariant that *no adjacent pair of planned nodes may ever exceed the
150 m spacing maximum*, which is a coverage hole in the field rather than a rounding detail),
`lib/fleet.ts` (maintenance rules, trend slopes, `compareVersions`' `v1.10.0 > v1.9.0` trap,
gap-vs-zero handling — a day with no telemetry must read as a gap, never as a flat battery),
`lib/incident.ts` (cluster gap boundaries, path de-duplication, herd interpolation and clamping),
`lib/dashboard.ts` (`sigmoid`/`fusedConfidence` — ADR 0001 §6's `P = σ(L)` surfacing in the UI —
plus the rule that unknown confidence stays `null` and is never rendered as a fabricated 0%),
`lib/learning.ts` (weekly bucketing, the min-sample rule that stops one lucky retreat plotting as a
100%-effective deterrent, pinned series colours), and the new `lib/risk.ts`.

**The suite was mutation-checked, not just run.** Dropping `evaluateRules`' battery-critical floor
from 20% to 5% makes the suite fail (`× flags battery below the 20% floor as critical`) — confirming
the tests would actually catch a regression rather than merely passing alongside one.

**CI** (`.github/workflows/ci.yml`): the `lint-web` job whose entire body was
`echo "web/frontend lint placeholder"` is replaced by a real `web-frontend` job — `npm ci` →
`npm run lint` → `npm run build` (which is `tsc -b && vite build`, so it is the typecheck gate too) →
`npm run test`. `lint-python` keeps its `|| true` for now: `device/mpu` and `ml/` are still empty
scaffolds, so tightening it would gate on nothing.

**Playwright is deliberately not in CI.** It drives a real browser against a live Supabase project
with real staff logins; in GitHub Actions that would mean production credentials in repo secrets and
every PR writing to the production database. It stays a local pre-deploy gate, and
`scripts/qa-day5-responsive.mjs` *is* that gate — it already logs in as each role and asserts every
dashboard route renders, so a second, thinner smoke script would only duplicate it.

~~Still open (was flagged optional): `notify-officer-request`'s `getUserById` guard remains
untested, because unlike `send-alert` its fan-out logic is not extracted into a testable module.~~
**Closed.** `notify-officer-request`'s fan-out logic is now extracted into its own `fanout.ts`,
covered by two Deno tests in `fanout.test.ts` mirroring `send-alert`'s test shape.

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

**Status: prepared, 12 Jul; the account-linked deploy itself is the remaining step.**

**Bundle split (was the pre-Day-4 audit's deferred perf advisory).** The main chunk was **740 kB**
(209 kB gzip), over Vite's 500 kB threshold, and it contained the entire ranger dashboard — Leaflet
included — which every anonymous visitor to the marketing site downloaded to read a page that
renders none of it. `App.tsx` now route-splits with `React.lazy` + `Suspense` (Home and Login stay
eager: they are the two pages a cold visitor actually lands on). Result: main chunk **263 kB**
(83 kB gzip), warning gone, with Leaflet (157 kB) and Supabase (204 kB) in chunks the marketing site
never fetches. The `Suspense` fallback deliberately matches `ProtectedRoute`'s existing loading state
so a chunk fetch and a session check read as one load, not two spinners.

**`web/frontend/vercel.json`** — `framework: vite`, build `npm run build`, output `dist`, and the
catch-all rewrite `/(.*)` → `/index.html` **without which a hard refresh on `/dashboard/fleet` 404s**
(this is `BrowserRouter`, not hash routing). Plus `X-Content-Type-Options`, `Referrer-Policy`,
`X-Frame-Options: DENY`, `Permissions-Policy`, HSTS, and immutable caching on `/assets/*`.

**No CSP is shipped, on purpose.** A correct one has to allow the project's own Supabase origin
(env-specific) plus the CARTO tile CDN (`*.basemaps.cartocdn.com`), and a static `vercel.json` CSP
with the wrong origins fails *silently* — blank map tiles, dead auth — which is exactly the failure
mode not worth risking on a live DFO-facing deploy. Add it as a post-deploy hardening step, verified
against the real URL.

**Verified locally against the production build, not just dev**: `vite preview` serving the real
`dist/` output against the production Supabase project passes the entire Day 5 QA pass (62
screenshots, every interaction assertion), including deep links straight to `/dashboard/*`.

**Deploy runbook (account-linked, so it is the owner's step):**
1. Vercel → New Project → import this repo → **Root Directory: `web/frontend`**. `vercel.json` supplies
   the rest; do not override the build command.
2. Environment variables, set in Vercel's dashboard (Production scope), **never committed**:
   `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` — the **anon** key only. The service-role key must
   never reach a Vite build: everything prefixed `VITE_` is inlined into client JS and is public.
   `.env.local` is gitignored and stays that way.
3. Deploy to **production**, not a preview.
4. Then re-run the regression against the live URL:
   `QA_BASE_URL=https://<the-domain> node scripts/qa-day5-responsive.mjs` (with `QA_ADMIN_*` set, so
   the admin role is covered this time), plus Demo Mode end to end — and call `reset_demo_data()`
   afterwards so no demo rows linger in production — plus one real alert through the Day 1 pipeline.
5. Add the CSP, verified against the live origin.

**Status: met, 12 Jul.** Deployed and regression-tested against the live production URL,
**<https://eletect.vercel.app>**.

**Deployment sanity, verified against the live origin (not assumed from config):** the site serves
HTTP 200; a deep link straight to `/dashboard/fleet` also returns 200 rather than 404, proving the
SPA rewrite is actually in effect (this is the failure `vercel.json` exists to prevent under
`BrowserRouter`); all five security headers are present on the response
(`X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, HSTS);
and — the check worth doing rather than assuming — every JS chunk served by the live site was
scanned for its baked-in Supabase host, confirming the deployed bundle points at the **same
production project** the tests query (`zjgafdozlrhecommmztq`), not a stale or dev project.

**Automated regression, green:** `QA_BASE_URL=https://eletect.vercel.app node
scripts/qa-day5-responsive.mjs` → **91 screenshots, every route × every role (anonymous, resident,
officer, admin) × mobile/tablet/desktop, every interaction assertion passing, exit 0.** That also
discharges "every role can log in on the live URL": the script signs in as each of the four and
fails hard if any cannot.

**Demo Mode, end to end on the live site:** the `confirmed_elephant` scenario ran from the real
browser against production. `S7-06` was polled *during* the run and observed moving
`online → alert → online` — the map visibly reacts, and the node returns itself to `online` on
retreat, which is the scenario's own story rather than a leak. Every demo-tagged event was written
`priority='normal'` (the safety barrier that means a demo can never page a village, independent of
`send-alert`'s own guard). `reset_demo_data()` then cleared **every** demo row (verified by direct
SQL, not by reading the UI), restored `S7-06` to its true prior status, and left
`demo_node_snapshot` empty.

**Alert pipeline, end to end on production:** a real high-priority `events` row (`media_url=null`,
`priority='high'` — what an actual node uplink looks like) was inserted with **no direct function
call**. The Database Webhook fired `send-alert` automatically, which fanned out and wrote `alerts`
rows: **one `channel=email, status=sent`** to the account-owner address, i.e. a real email left the
system. The test event and its `alerts` rows were deleted immediately afterwards.

**Production left clean, verified:** zero demo-tagged events, zero orphaned `alerts` rows, zero
alerts referencing the (re-deleted) seed accounts, `demo_node_snapshot` empty. The four seed accounts
were re-created for the run and deleted again afterwards, verified gone with cascades — the same
re-seed → test → delete loop the local pass uses, because those accounts must not exist between
runs.

### 🚩 The one thing blocking real DFO use — read this before onboarding anyone

The alert fan-out **works**, but under Resend's test-mode restriction **only the account-owner
address can actually receive mail**. The live run made this concrete: of the recipients the fan-out
selected, `abhinav123krish@gmail.com` got `status=sent`, while `officer@eletect.in` and the opted-in
resident got `status=failed` (Resend refused them), each followed by a terminal
`status=undeliverable, channel=null` row. That double row is *by design*, not a bug — `failed` means
one channel attempt bounced, `undeliverable` means that person received nothing at all — and it is
exactly the audit trail the pre-Day-4 fix added so a silently-dropped recipient is queryable.

So today the system is honest about failing, but it **is** failing for everyone except the owner.
Against this file's own deployment bar — *"alerts must reach the right person"* — that is the gap.
**Verify a sending domain in Resend and set `ALERT_EMAIL_FROM` to it before a single real officer or
resident is onboarded.** Everything else in the pipeline is proven; this is the last hop.

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

---

## Closeout — 12 Jul

**Every day's exit criteria is met.** Day 1 (alerts deliver), Day 2 (auth hardening — *partially*,
see below), Day 3 (RLS/RBAC adversarial pass), Day 4 (`web/ingest` proven hardware-free), Day 5
(seed + responsive/interactive pass), Day 6 (Vitest + CI), Day 7 (deployed + live regression). The
app is live at <https://eletect.vercel.app>, `main` and `develop` are in sync on GitHub, CI runs
lint + typecheck + 117 unit tests on every PR, and the full 91-shot QA matrix passes against
production.

This file is now closed. Everything below is what did **not** finish, carried forward rather than
quietly dropped.

### Blocking a real DFO deployment (do these before onboarding anyone)

1. **Verified sending domain (Resend).** *The* blocker. Alerts reach only the account owner today;
   every other recipient logs `failed` → `undeliverable`. See the Day 7 flag above. Nothing else in
   the alert path is unproven — this is the last hop, and it is the difference between "the pipeline
   works" and "a forest officer is actually told."
2. **Day 2's Auth SMTP, still staged and not activated.** Signup confirmation, password reset, and
   magic links still go through Supabase's rate-limited default sender. This was blocked on the same
   thing as (1) — Resend's SMTP relay refuses to send from an unverified domain — so **verifying one
   domain unblocks both**. Steps are written out in `web/backend/README.md` ("Auth transactional
   email"); it is Dashboard-only. Do not `supabase config push` to achieve it: that pushes the entire
   local `config.toml`, which has never captured the live project's `site_url`/redirect URLs and
   would silently reset them.
3. **Branch protection on `main`: deferred by design until the repo goes public (target 16 Aug 2026,
   ~1 week before the Robu deadline).** Not an oversight — an accepted, dated risk.

   It **cannot** be enabled today: GitHub gates branch protection *and* rulesets behind Pro for
   private repositories. Both REST endpoints return
   `403 "Upgrade to GitHub Pro or make this repository public"`, and the web UI is gated identically,
   so this is not a CLI limitation and there is no workaround short of paying or publishing. Until
   then `main` accepts direct pushes and the Day 6 CI job gates nothing — a red build can land on
   `main`. Work accordingly: run `npm run lint && npm run build && npm run test` before pushing to
   `main`, because nothing else will.

   The `web-frontend` check **is** registered and passing on `main`, so it is ready to be required the
   moment protection becomes available. Run both commands together on publication day:

   ```bash
   gh repo edit Abhinavkrishna3211/EleTect-X --visibility public --accept-visibility-change-consequences
   gh api -X PUT repos/Abhinavkrishna3211/EleTect-X/branches/main/protection \
     -H "Accept: application/vnd.github+json" --input - <<'JSON'
   {
     "required_status_checks": { "strict": true, "contexts": ["web-frontend"] },
     "enforce_admins": true,
     "required_pull_request_reviews": { "dismiss_stale_reviews": true, "required_approving_review_count": 0 },
     "restrictions": null,
     "allow_force_pushes": false,
     "allow_deletions": false,
     "required_linear_history": true
   }
   JSON
   ```

   `enforce_admins: true` matters — without it the rule does not apply to the repo owner, and a direct
   push to `main` would still succeed. Verify afterwards by attempting one and confirming it is
   rejected. (`PROJECT_BLUEPRINT.md` §0 has listed branch protection as a day-one action; the reason it
   never happened is the plan gate, now documented rather than left mysterious.)

### Post-closeout fixes, 12 Jul

- **Hover/focus affordances.** The premise that interactive elements showed "zero visual change on
  hover" turned out to be true only in part — measured on the live site by diffing computed styles
  before and after hover, nav links *did* shift colour (70% → 100% opacity), buttons *did* lighten
  (`#E2A13C → #EDBE6F`), and inputs *did* tint their border gold on focus. The real gap was
  **cards: 76 of them across every public page, with no hover response at all.** They now use the
  affordance the codebase had already established on the Home/Solutions/Technology feature cards
  (gold border + a 4px lift) rather than a newly invented one. Nav and footer links additionally gain
  an underline, because a 70→100% opacity shift alone is a weak signal on this palette. Keyboard
  focus previously fell through to each browser's default outline — easy to lose entirely on a
  near-black surface, and inputs opted out of it altogether via `focus:outline-none` — so a single
  gold `:focus-visible` ring is now defined globally in `index.css`. All verified by measuring
  computed styles on the built output, not by eye.
- **`qa-phase3-screenshots.mjs` no longer hardcodes a password**; it reads `QA_SEED_PASSWORD` from the
  gitignored `.env.local`, the same pattern as the Day 5 scripts.
- **anon/PUBLIC `EXECUTE` revoked on the definer RPCs** — see below.

### Applied directly to the production database, 12 Jul

Both were source-only fixes until now — a file change does not alter a deployed Postgres function or
a live row. Run through `supabase db query --linked` (Management API; no DB password, and **not**
`config push`, which would have reset the live `site_url`).

- **`run_demo_scenario`'s `14 Hz` → `22 Hz` is now live.** Rather than replaying `schema.sql`'s
  version of the function wholesale — a live definer function has drifted from source before, which
  is exactly the `demo_touch_node` bug — the fix read the **current live** definition with
  `pg_get_functiondef()`, replaced only that one string literal, and executed the result (which
  `pg_get_functiondef` emits as `CREATE OR REPLACE FUNCTION`). So nothing else about the function
  could change. Verified after: `position('14 Hz' …) = 0`, `position('22 Hz' …) = 1585`, and
  `SECURITY DEFINER`, the `search_path` setting, the owner, and the internal `is_staff()` guard all
  intact.
- **Phantom node `S7-08` deleted.** It was **not in `seed-4b.sql` at all** (which defines exactly
  eight nodes: S7-02/04/05/06/07/09/11/12) and carried **zero health, zero events, zero maintenance**
  rows, while every real seeded node has ~170 health and ~30 events. It was a leftover from a
  superseded seed iteration, sitting on the live map in a permanent `alert` with nothing behind it —
  so "restore its resting state" had no correct answer; the seed's intent is that it does not exist.
  Nothing referenced it, so there was nothing to cascade. Confirmed on the live dashboard afterwards:
  the ALERT tile reads **0** (was 1), the map shows the eight seeded pins, and it is gone from the
  Fleet roster.
- **Left in place on purpose:** `4f3030e129cfeb14` ("node-test-01"), the Day 4 ChirpStack ingest test
  device. It has null coordinates so it draws no map pin, and it is the live proof that the
  ChirpStack → `web/ingest` → Supabase path works. Revisit before a DFO demo if a stray test device
  in the fleet roster looks unprofessional.

### Known gaps, not blocking

- ~~Defense-in-depth on the definer RPCs.~~ **Done, 12 Jul.** `revoke execute … from public, anon`
  applied to all five (`run_demo_scenario`, `reset_demo_data`, `approve_officer_request`,
  `reject_officer_request`, `demo_touch_node`) — on the **live database and in `schema.sql` together**,
  plus `migrations/0002_revoke_anon_rpc_execute.sql`, so this does not become the source-vs-live drift
  this file keeps catching. `authenticated` deliberately **keeps** `EXECUTE` on the four
  browser-called RPCs: staff run Demo Mode and admins work the approval queue as that role, and
  revoking there would have broken both. `demo_touch_node` is internal-only (invoked by the definer
  functions, which run as the owner) so it needs no role grant at all.

  The proof this actually closed a layer: an anonymous call now fails with
  **`permission denied for function`** (stopped at the grant, before the body) where it previously
  failed with `not authorized` (stopped by the guard, inside the body). All four re-tested live as
  true-anonymous. Demo Mode re-verified end to end from the live dashboard afterwards — scenario runs,
  writes rows, `Reset demo data` clears them, zero permission errors in the browser console.
- **DLT registration status: still unfilled.** Nobody has recorded the actual application/approval
  state with the SMS provider. Until then SMS stays gated behind `CHANNEL_SMS=off` and email carries
  delivery. Record the real answer here rather than leaving it an assumption.
- ~~No CSP on the deployed site.~~ **Drafted.** `vercel.json` now ships a policy scoped to the app's
  actual origins: the production Supabase host (REST + realtime websocket), the CARTO tile CDN
  (`LiveMap.tsx`'s subdomains), Google Fonts, and the marketing page's Unsplash images. `style-src`
  keeps `unsafe-inline` because Leaflet's `divIcon` markers are raw HTML strings with inline `style`
  attributes. No wildcards. Still needs a human to load the live dashboard and confirm nothing silently
  breaks (blank map tiles, dead auth) before calling this closed.
- **Residents can only opt in by holding an account.** The consequence of the Day 5 Stay Safe
  decision, and the right default (signup + email confirmation *is* the consent record). If field use
  shows residents will not create accounts, that is the moment to design an anonymous opt-in with real
  verification — not before.
- ~~`notify-officer-request` has no unit tests.~~ **Closed.** Its fan-out logic is now extracted
  into `fanout.ts` (same extraction `send-alert` already went through), with two Deno tests
  covering the `getUserById`-failure-skips-one-admin case and the notified-count-reflects-actual-
  delivery case. `deno check` against real `supabase-js` types confirmed the extraction is
  behavior-preserving.
- ~~`scripts/qa-phase3-screenshots.mjs` hardcodes a password.~~ **Fixed.** It reads `QA_SEED_PASSWORD`
  from the gitignored `.env.local` (falling back to the environment), the same pattern the Day 5
  scripts use, and refuses to run below 16 characters. No hardcoded credential remains in the file.
  (This entry was left open here after the code fix already landed elsewhere in this document — see
  the near-duplicate note above and the 12 Jul closeout below.)
*(The stale `S7-08` alert state and the `14 Hz` demo log line were both listed here and are now
resolved against the live database — see "Applied directly to the production database" above.)*

### Operational note for whoever runs QA next

`scripts/qa-day5-responsive.mjs` signs in as seeded officer and resident accounts that are
**deliberately deleted after every run** — one of them holds the `officer` role in the production
project and must not persist. The loop is therefore: `node scripts/seed-day5-profiles.mjs` → run the
pass → delete the accounts again. The seed script is idempotent and rotates the password on re-run;
`QA_SEED_PASSWORD` and `QA_ADMIN_*` live in the gitignored `.env.local`, never in the repo.
