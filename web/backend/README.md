# Backend (Supabase)

Auth + Postgres + realtime + storage + edge functions. Roles: **admin · officer · public**.

## Setup
1. Create a free Supabase project → copy the Project URL + anon key + service-role key.
2. **SQL editor →** run `schema.sql` (tables, RLS, triggers, realtime, public view).
3. **Auth →** enable Email/Password. First user: sign up, then in SQL set your role:
   `update profiles set role='admin' where id='<your-uid>';`
4. **Storage →** create a public bucket `event-media` for detection thumbnails.
5. **Edge function →** deploy `functions/send-alert`:
   `supabase functions deploy send-alert`
6. **Database Webhook →** on `events` INSERT → call the `send-alert` function.
7. **Secrets:** `supabase secrets set SUPABASE_URL=... SERVICE_ROLE_KEY=... SMS_PROVIDER=fast2sms SMS_API_KEY=... SMS_SENDER=... SMS_TEMPLATE_ID=...`

## Data flow (end to end)
Node → LoRa → gateway (ChirpStack) → `web/ingest` (MQTT→Supabase insert into `events`/`health`) → Database Webhook → `send-alert` edge function → **SMS** to officers + opted-in nearby public → row in `alerts`. Dashboard reads via Supabase realtime.

## SMS — India reality (important)
Sending SMS to Indian mobiles legally requires **TRAI DLT registration**: register an entity on a DLT portal, get an approved **sender ID (header)** and **message template**, then use an India provider (**Fast2SMS**, **MSG91**, or Twilio-India). Plan for a few days' lead time.
- **Auth uses email/password** (no SMS OTP) to avoid blocking on DLT.
- **Outbound alerts use SMS** via the opted-in phone numbers once DLT is approved.
- **Contest/demo fallback if DLT isn't ready:** switch `SMS_PROVIDER` to Twilio trial (verified numbers only) or send **email** alerts (Supabase/Resend free) to prove the pipeline; swap to production SMS when DLT clears.

## Env (frontend)
`web/frontend/.env` → `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`. Never commit `.env`.
