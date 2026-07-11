# Backend (Supabase)

Auth + Postgres + realtime + storage + edge functions. Roles: **admin · officer · public**.

## Setup
1. Create a free Supabase project → copy the Project URL + anon key + service-role key.
2. **SQL editor →** run `schema.sql` (tables, RLS, triggers, realtime, public view).
3. **Auth →** enable Email/Password. First user: sign up, then in SQL set your role:
   `update profiles set role='admin' where id='<your-uid>';`
4. **Storage →** create a public bucket `event-media` for detection thumbnails.
5. **Edge functions →** deploy `functions/send-alert` and `functions/notify-officer-request`
   (the CLI resolves each via `supabase/config.toml`'s entrypoint override — no need to move the
   files): `supabase functions deploy send-alert --project-ref <ref> --use-api --workdir web/backend`
   and the same command with `notify-officer-request` in place of `send-alert`.
6. **Database Webhooks →** on `events` INSERT → call `send-alert`; on `officer_requests` INSERT →
   call `notify-officer-request`.
7. **Secrets:** `supabase secrets set SERVICE_ROLE_KEY=... RESEND_API_KEY=... ALERT_EMAIL_FROM='EleTect X <onboarding@resend.dev>' CHANNEL_SMS=off`
   (`SUPABASE_URL` is platform-injected, so it is not set here and won't appear in `secrets list`.)
   Then confirm presence — not just that deploy succeeded: `supabase secrets list` must show
   `SERVICE_ROLE_KEY`, `RESEND_API_KEY`, `ALERT_EMAIL_FROM`. `notify-officer-request` reuses these
   same secrets — nothing extra to set for it.

## Data flow (end to end)
Node → LoRa → gateway (ChirpStack) → `web/ingest` (MQTT→Supabase insert into `events`/`health`) → Database Webhook → `send-alert` edge function → **notification channels** (email now; SMS/WhatsApp when configured) to officers + opted-in nearby public → row in `alerts`. Dashboard reads via Supabase realtime.

## Notification channels (`send-alert`)
Delivery is pluggable. `send-alert` reaches each recipient over the **first enabled channel it has
an address for**, in priority order, and logs one `alerts` row per attempt (`channel` + `status`):

1. **Email (Resend) — primary, live now.** No DLT dependency. Set `RESEND_API_KEY` and
   `ALERT_EMAIL_FROM`. For testing, `onboarding@resend.dev` delivers only to your Resend account
   email until you verify a sending domain; swap to a verified-domain from-address for production.
   Disable with `CHANNEL_EMAIL=off`.
2. **WhatsApp — registered stub.** The channel slot exists (`CHANNEL_WHATSAPP=on`) but no provider
   is wired yet (Twilio or Meta Cloud API pending).
3. **SMS — implemented, gated off (`CHANNEL_SMS=on` to enable).** Kept off until DLT clears.

Recipient emails are resolved from `auth.users` at send time (the `profiles` table stores no email).

## Officer approval notify (`notify-officer-request`)
A Forest Officer signup queues a row in `officer_requests` (see `schema.sql`'s `handle_new_user()`)
but grants no access until an admin approves it via the `OfficerApprovals` dashboard page. This
function emails every `role='admin'` profile the moment that row is inserted, so approval doesn't
depend on an admin happening to check the page. Same Resend HTTP API as `send-alert`, same
`RESEND_API_KEY`/`ALERT_EMAIL_FROM` secrets — nothing new to configure. Wire the
`officer_requests` INSERT Database Webhook to this function (step 6 above).

## Auth transactional email (signup confirm / password reset / magic link)
Supabase Auth's own emails (not `send-alert`'s alert emails) still use Supabase's default sender,
which is rate-limited and unsuitable for production signups. Switching to Resend requires a
**verified sending domain** — unlike `send-alert`'s HTTP API, Resend's SMTP relay refuses to send
from an unverified domain at all (not just restricted delivery), so this stays unconfigured until
a domain is verified. **Do not run `supabase config push`** to set this — it pushes the entire
local `config.toml`, and this file has never captured the live project's `site_url`/redirect URLs/
other Auth settings, so a push would silently reset them. Configure Auth SMTP through the
**Dashboard only**, once a domain is verified:
1. Resend → verify a sending domain (add the DNS TXT/CNAME/MX records it gives you).
2. Supabase Dashboard → Project Settings → Authentication → SMTP Settings: host
   `smtp.resend.com`, port `587`, user `resend`, password = your `RESEND_API_KEY`, sender email
   `noreply@<verified-domain>`, sender name `EleTect X`.
3. Supabase Dashboard → Authentication → Rate Limits → raise "Emails sent" from the default
   2/hour (a guard specific to Supabase's shared sender) to ~30/hour now that a real SMTP relay
   is in place.
4. Re-run the live-proof: a real external address signs up, receives the confirmation email
   through the new sender, and can reset its password through it.

## Signup abuse checks
`web/frontend`'s signup form has a honeypot field (invisible to real users, off-screen not
`display:none`) that silently no-ops the submit if filled — catches generic bots that fill every
input they find. Layered under Supabase's own per-IP rate limit on sign-ups (30 per 5 minutes,
default, unchanged). Neither stops a targeted attacker calling `supabase.auth.signUp` directly;
closing that gap needs a CAPTCHA (`auth.captcha` + Cloudflare Turnstile), not done yet.

## SMS — India reality (important)
Sending SMS to Indian mobiles legally requires **TRAI DLT registration**: register an entity on a DLT portal, get an approved **sender ID (header)** and **message template**, then use an India provider (**Fast2SMS**, **MSG91**, or Twilio-India). Plan for a few days' lead time.
- **Auth uses email/password** (no SMS OTP) to avoid blocking on DLT.
- **Outbound alerts use email today** (the fallback below, made real); SMS is a drop-in third
  channel that becomes active the moment `CHANNEL_SMS=on` once DLT is approved — nothing
  architectural changes.
- **Fallback while DLT isn't ready (current state):** email via Resend proves the full pipeline.
  Once DLT clears, set the `SMS_*` secrets and `CHANNEL_SMS=on`; SMS then delivers alongside email.
  SMS secrets: `SMS_PROVIDER` (fast2sms|msg91|twilio), `SMS_API_KEY`, `SMS_SENDER`,
  `SMS_TEMPLATE_ID` (+ `TWILIO_SID`/`TWILIO_TOKEN`/`TWILIO_FROM` for the twilio provider).

## Env (frontend)
`web/frontend/.env` → `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`. Never commit `.env`.
