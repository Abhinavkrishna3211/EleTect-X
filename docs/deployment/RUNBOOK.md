# Production deploy runbook — web backend

One ordered pass. Every step has a verification and a rollback. Do not skip a verification
because the command reported success: three of the defects this release fixes were deployed
successfully and were wrong anyway.

The project is a live deployment. Officers and residents receive what this backend sends.

---

## 0. Verified starting state

Confirmed by downloading the live function source, not inferred from git history:

| Thing | State |
|---|---|
| `send-alert` | deployed, **version 8** |
| `send-alert` → `audienceFor()` | `POACHING.has(species) ? "staff_only" : "staff_and_residents"` — **fails open** |
| `send-alert` → deactivation guard | **absent** (`banned_until` appears zero times) |
| `send-alert` → email body | contains an unescaped HTML part interpolating `nodes.name`, which arrives over MQTT |
| `notify-officer-request` | **never deployed** — no such function exists on the project |
| Migrations 0006–0009 | **applied state unverified** — see step 2 |

Consequences live right now: any species that is not gunshot or chainsaw pages every officer
*and* every opted-in resident within 3 km, so a fox pages a village; a deactivated officer still
receives every alert; and a node name chosen upstream lands unescaped in an email body.

Because `notify-officer-request` was never deployed, two things follow — admins have never been
emailed when an officer signs up, so approval has always depended on someone opening the
dashboard; and that function's own deactivated-admin PII leak was never live.

---

## 1. Prerequisite — verify a Resend sending domain

**Do this before anything else. Without it the release changes who is targeted but nobody
receives anything.**

`ALERT_EMAIL_FROM` is currently the Resend shared sandbox sender, which delivers **only to the
Resend account owner's address**. Email is the only live channel: WhatsApp is an unwired stub and
SMS is gated off pending TRAI DLT. So today every officer and resident alert silently goes
nowhere.

1. Resend → add a sending domain, create the DNS records it asks for (TXT/CNAME/MX), wait for
   verification.
2. Keep the verified from-address for step 4.

The same verified domain unblocks Auth transactional email (step 7), which is still on Supabase's
default sender at 2 emails/hour — unusable for resident signups.

**Verify:** the Resend dashboard shows the domain `verified`, not `pending`.

---

## 2. Establish which migrations are applied

`migrations/` is applied by hand in the SQL editor (`web/backend/README.md` step 2); there is no
CLI migration history for this project, so nothing records what has run. Check before applying,
because 0006 and 0007 are **not** idempotent — 0007's bare `create policy` raises 42710 on a
second run and, being inside a transaction, takes its own revoke down with it on rollback.

In the SQL editor:

```sql
-- 0006: partial index for the critical backlog query
select indexname from pg_indexes where tablename = 'events' and indexname like '%critical%';

-- 0007/0008: the self-write policies
select policyname, cmd from pg_policies where tablename = 'profiles' order by policyname;

-- 0008: the column grant — the thing whose absence is the escalation
select privilege_type, column_name from information_schema.column_privileges
 where table_name = 'profiles' and grantee = 'authenticated';

-- 0009A: the approval guard
select pg_get_functiondef('approve_officer_request(bigint)'::regprocedure)
       like '%role <> ''admin''%' as guard_present;

-- 0009B: the poaching filter
select definition like '%gunshot%' as filter_present
  from pg_views where viewname = 'public_area_risk';
```

Apply only the files these show are missing, **in ascending order**. 0008 and 0009 are written to
be safe to re-run as many times as needed; 0006 and 0007 are not.

---

## 3. Apply the migrations

SQL editor, in order, one at a time, reading the result of each before starting the next:

```
0006_acknowledge_critical.sql
0007_profile_self_write_scope.sql
0008_profile_update_column_scope.sql
0009_approval_guard_and_poaching_privacy.sql
```

**Verify 0008 as an ordinary resident JWT — not the service role, which bypasses all of it.**
The fourth line is the one the migration exists for:

```sql
update profiles set full_name = 'x'       where id = auth.uid();  -- succeeds
update profiles set alerts_enabled = true where id = auth.uid();  -- succeeds
delete from profiles                      where id = auth.uid();  -- denied
update profiles set role = 'admin'        where id = auth.uid();  -- denied
```

Then confirm the grant landed, since the missing grant is precisely what no policy listing would
have shown:

```sql
select privilege_type, column_name from information_schema.column_privileges
 where table_name = 'profiles' and grantee = 'authenticated';
-- expect UPDATE on exactly: full_name, phone, lat, lng, alerts_enabled
```

**Verify 0009A** — as an admin, approve a pending request belonging to another admin; that admin
must still be `admin` afterwards, and the request must read `approved`. On an ordinary applicant,
the role must become `officer`.

**Verify 0009B** — with at least one `high` gunshot row present, `select sum(detections) from
public_area_risk` must exclude it; inserting a `high` elephant row must move the count.

**Rollback:** each file is a single transaction, so a failure leaves nothing half-applied. 0008
and 0009 can simply be re-run.

---

## 4. Set the alert sender

```
supabase secrets set ALERT_EMAIL_FROM='EleTect X <alerts@YOUR-VERIFIED-DOMAIN>' --project-ref <ref>
```

**Verify presence, not deploy success:**

```
supabase secrets list --project-ref <ref>
```

must show `SERVICE_ROLE_KEY`, `RESEND_API_KEY` and `ALERT_EMAIL_FROM`. `SUPABASE_URL` is
platform-injected and will not appear — that is expected.

---

## 5. Deploy both edge functions

Take a rollback snapshot of the live version **before** deploying over it, every time:

```
supabase functions download send-alert --project-ref <ref>
```

Then:

```
supabase functions deploy send-alert             --project-ref <ref> --use-api --workdir web/backend
supabase functions deploy notify-officer-request --project-ref <ref> --use-api --workdir web/backend
```

`notify-officer-request` is a first deployment, not an update.

**Verify:**

```
supabase functions list --project-ref <ref>
```

`send-alert` must report version 9 or higher, and `notify-officer-request` must now appear.
Then confirm the deployed source is the intended one rather than trusting the version number —
download it again and check the three things that were wrong:

- `banned_until` appears in `send-alert/fanout.ts` (was absent)
- no `html:` part remains in `send-alert/fanout.ts` (was present)
- `audienceFor()` in `send-alert/message.ts` defaults to `staff_only` (was `staff_and_residents`)

**Rollback:** redeploy the snapshot taken above.

---

## 6. Wire the second webhook

`events` INSERT → `send-alert` already exists. Add, if absent:

**`officer_requests` INSERT → `notify-officer-request`.** Without it, the function deployed in
step 5 is never called and officer signups stay silent.

**Verify:** sign up a throwaway Forest Officer account; an admin must receive the email.

---

## 7. Auth transactional email

Still Supabase's default sender at 2 emails/hour. With the domain from step 1 verified:

**Dashboard only. Do not run `supabase config push`** — it pushes the entire local `config.toml`,
which has never captured this project's `site_url` or redirect URLs, and would silently reset
them.

1. Project Settings → Authentication → SMTP Settings: host `smtp.resend.com`, port `587`,
   user `resend`, password = the Resend API key, sender `noreply@<verified-domain>`, sender name
   `EleTect X`.
2. Authentication → Rate Limits → raise "Emails sent" from 2/hour to about 30/hour.

**Verify:** a real external address signs up, receives the confirmation, and can complete a
password reset through it.

---

## 8. Device side — before the node deploy

The node stops deterring foxes unless its scope names Fox. `HOME_TEST_MODE` used to append it
implicitly; scope is now the only thing that decides. The board currently reports
`NODE_DETERRENCE_SCOPE=both`, which resolves to `('Elephant', 'Boar')`.

Set in the container environment before deploying:

```
ELETECT_DETERRENCE_SCOPE=Elephant,Boar,Fox
```

**Verify:** the boot banner names all three.

---

## 9. Live proof

Not a unit test — the real chain, end to end.

1. A real detection, or an `events` insert at `priority='high'`, `species='elephant'`.
2. An officer receives the email, from the verified-domain sender.
3. An opted-in resident **within 3 km** receives it; one outside 3 km does **not**.
4. Insert the same event with `species='fox'` — officers get it, **no resident does**. This is the
   fail-open regression, and it is the one most likely to come back.
5. Deactivate a test officer, re-fire — they receive nothing, and no `alerts` row names them.
6. `select * from alerts order by ts desc limit 20` — one row per recipient per attempt, with
   `channel` and `status`.

---

## Seeding, afterwards

`seed-4b.sql` inserts its CA-2231 rows at `normal` and raises four of them to `high` in a separate
`UPDATE`, because the webhook fires on INSERT only. That is deliberate: the S7-* coordinates are
real Kothamangalam positions, and inserting at `high` would page officers and nearby residents
with a fake elephant. Do not fold that `UPDATE` back into the `INSERT`.
