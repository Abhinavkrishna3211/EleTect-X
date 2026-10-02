-- 0010: deactivation writes a finite far-future timestamp instead of 'infinity'.
--
-- Found during the production deploy rehearsal (docs/deployment/RUNBOOK.md step 9.5).
-- The test: deactivate an officer, fire a high-priority elephant event, assert the
-- officer receives nothing and no alerts row names them. The officer received
-- nothing -- but an `undeliverable` row appeared with their *uuid* as the
-- recipient, which is what deliver() writes when a person has no address at all.
-- The deactivation guard in send-alert/fanout.ts had not fired; the account had
-- instead degraded into "a user with no email".
--
-- The discriminating run, same node and same species, differing only in the ban
-- value:
--
--   banned_until = 'infinity'          -> one `undeliverable` row, recipient = uuid
--   banned_until = now() + '1 day'     -> no row of any kind
--
-- So isDeactivated() is correct and was never reached. GoTrue's admin API cannot
-- hand back a user row whose banned_until is a Postgres infinity -- the value has
-- no representation in the Go time type the row deserialises into -- so
-- getUserById returns an error rather than the user. fanOut() discarded that
-- error, which left a revoked account indistinguishable from an addressless one.
--
-- Nothing leaked, because an addressless recipient is also skipped. But it was
-- skipped by an unhandled error path and not by the defence that was built for
-- it, and the next recipient lookup that fails for an unrelated reason gets the
-- same silent treatment. The companion change in send-alert/fanout.ts and
-- notify-officer-request/fanout.ts makes a failed lookup fail closed explicitly.
--
-- 'infinity' was chosen originally because it reads as "no expiry", and every
-- SQL-side consumer handles it correctly: the `deactivated` column in
-- admin_list_users() and the last-active-admin guard both compare
-- `banned_until > now()`, which is true for infinity. The breakage is only at
-- the GoTrue boundary. A finite sentinel satisfies both: year 9999 is still
-- "never" for a forest-division deployment, and it round-trips through the
-- admin API.

create or replace function admin_set_deactivated(p_user uuid, p_deactivated boolean)
returns void language plpgsql security definer set search_path = public as $$
declare
  v_admins int;
begin
  if not is_admin() then
    raise exception 'not authorized';
  end if;

  if p_user = auth.uid() then
    raise exception 'you cannot deactivate your own account';
  end if;

  if p_deactivated then
    select count(*) into v_admins
      from public.profiles pr
      join auth.users au on au.id = pr.id
      where pr.role = 'admin' and (au.banned_until is null or au.banned_until <= now());
    if v_admins <= 1 and (select role from public.profiles where id = p_user) = 'admin' then
      raise exception 'cannot deactivate the last active admin';
    end if;
  end if;

  -- GoTrue refuses to issue a session while banned_until is in the future, so this
  -- blocks sign-in at the auth layer rather than only in the UI. The date is a
  -- sentinel for "no expiry" and must stay finite -- see the header: 'infinity'
  -- makes the row unreadable through the admin API, which is how the alert
  -- fan-out stopped being able to tell a revoked account from an addressless one.
  update auth.users
     set banned_until = case
                          when p_deactivated then timestamptz '9999-12-31 23:59:59+00'
                          else null
                        end
   where id = p_user;
  if not found then
    raise exception 'no such user';
  end if;
end; $$;

-- Any account deactivated before this migration still carries the unreadable
-- value. Rewritten in place: the comparison semantics are identical, so nothing
-- observable changes except that the admin API can read the row again.
update auth.users
   set banned_until = timestamptz '9999-12-31 23:59:59+00'
 where banned_until = 'infinity'::timestamptz;
