-- 0003 — Admin panel: user / role management.
--
-- Deliberately NOT firmware/OTA: there is no real firmware pipeline on device/mcu
-- yet, and a mocked OTA panel would undercut the "real deployment" credibility the
-- rest of this system is built on. That screen lands when the firmware does.
--
-- Every action here is gated server-side by is_admin(). Hiding a button in React is
-- not access control: without these guards any authenticated user could call the
-- RPC directly with the anon key and their own JWT.
--
-- profiles has no email column (email lives in auth.users), so listing users needs a
-- SECURITY DEFINER function to join across — the same reason handle_new_user() is a
-- definer. Deactivation sets auth.users.banned_until, which GoTrue itself enforces at
-- sign-in: a deactivated account cannot obtain a session at all, rather than merely
-- being hidden by the app.

-- ---------- list ----------
create or replace function admin_list_users()
returns table (
  id uuid,
  email text,
  role user_role,
  full_name text,
  created_at timestamptz,
  deactivated boolean,
  is_self boolean
)
language sql security definer set search_path = public as $$
  select
    p.id,
    u.email::text,
    p.role,
    p.full_name,
    p.created_at,
    (u.banned_until is not null and u.banned_until > now()) as deactivated,
    (p.id = auth.uid()) as is_self
  from public.profiles p
  join auth.users u on u.id = p.id
  where is_admin()          -- no rows at all for a non-admin caller
  order by
    case p.role when 'admin' then 0 when 'officer' then 1 else 2 end,
    u.email;
$$;

-- ---------- change role ----------
create or replace function admin_set_role(p_user uuid, p_role user_role)
returns void language plpgsql security definer set search_path = public as $$
declare
  v_admins int;
begin
  if not is_admin() then
    raise exception 'not authorized';
  end if;

  -- An admin must not be able to lock themselves out of their own project.
  if p_user = auth.uid() then
    raise exception 'you cannot change your own role';
  end if;

  -- Never leave the project with no admin. Counted before the change, so demoting
  -- the only other admin while you are still one is fine; demoting the last one is not.
  if p_role <> 'admin' then
    select count(*) into v_admins from public.profiles where role = 'admin';
    if v_admins <= 1 and (select role from public.profiles where id = p_user) = 'admin' then
      raise exception 'cannot demote the last remaining admin';
    end if;
  end if;

  update public.profiles set role = p_role where id = p_user;
  if not found then
    raise exception 'no such user';
  end if;
end; $$;

-- ---------- deactivate / reactivate ----------
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
  -- blocks sign-in at the auth layer rather than only in the UI.
  update auth.users
     set banned_until = case when p_deactivated then 'infinity'::timestamptz else null end
   where id = p_user;
  if not found then
    raise exception 'no such user';
  end if;
end; $$;

-- Same grant posture as the other definer RPCs (see 0002): anon and PUBLIC are
-- revoked so an anonymous caller is stopped at the grant; `authenticated` keeps
-- EXECUTE because admins call these from the dashboard as that role, and the
-- is_admin() guard inside each one is what actually authorises the action.
revoke execute on function admin_list_users() from public, anon;
revoke execute on function admin_set_role(uuid, user_role) from public, anon;
revoke execute on function admin_set_deactivated(uuid, boolean) from public, anon;

grant execute on function admin_list_users() to authenticated;
grant execute on function admin_set_role(uuid, user_role) to authenticated;
grant execute on function admin_set_deactivated(uuid, boolean) to authenticated;
