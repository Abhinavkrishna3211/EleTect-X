# Backend (Supabase)

Auth + Postgres + realtime + storage + edge functions. Roles: **admin · officer · public**.

## Setup
1. Create a free Supabase project → copy the Project URL + anon key + service-role key.
2. **SQL editor →** run `schema.sql` (tables, RLS, triggers, realtime, public view).
3. **Auth →** enable Email/Password. First user: sign up, then in SQL set your role:
   `update profiles set role='admin' where id='<your-uid>';`
4. **Storage →** create a public bucket `event-media` for detection thumbnails.
5. **Edge function →** deploy `functions/send-alert` (the CLI resolves it via
   `supabase/config.toml`'s entrypoint override — no need to move the file):
   `supabase functions deploy send-alert --project-ref <ref> --use-api --workdir web/backend`
6. **Database Webhook →** on `events` INSERT → call the `send-alert` function.
7. **Secrets:** `supabase secrets set SERVICE_ROLE_KEY=... RESEND_API_KEY=... ALERT_EMAIL_FROM='EleTect X <onboarding@resend.dev>' CHANNEL_SMS=off`
   (`SUPABASE_URL` is platform-injected, so it is not set here and won't appear in `secrets list`.)
   Then confirm presence — not just that deploy succeeded: `supabase secrets list` must show
   `SERVICE_ROLE_KEY`, `RESEND_API_KEY`, `ALERT_EMAIL_FROM`.

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
