-- 0007 — a resident can no longer promote themselves to admin by deleting
-- their profile and inserting a new one.
--
-- `p_self_rw on profiles for all using (id = auth.uid()) with check (id =
-- auth.uid())` was written to mean "you manage your own profile", and the
-- column grant below it (0001) was the guard that `role` must stay out of
-- reach: `revoke update on profiles from authenticated` plus a grant on the
-- five self-service columns.
--
-- That closes UPDATE and nothing else. `for all` also covers INSERT and
-- DELETE, both of which `authenticated` holds by default in the public schema
-- — which is why the UPDATE revoke had to be written at all — and the policy's
-- WITH CHECK only ever looks at the id. So:
--
--   DELETE /rest/v1/profiles?id=eq.<me>
--   POST   /rest/v1/profiles  {"id":"<me>","role":"admin"}
--
-- is two requests with nothing but an ordinary resident's own JWT, and the
-- second one is admitted: the row's id is still auth.uid(), the column grant
-- does not apply to INSERT, and `role` is an ordinary column. The account comes
-- back as an admin, with is_admin() true, write access to every table and
-- admin_set_role() over every other user. Nothing is logged, and the deleted
-- row leaves no trace.
--
-- The fix is at the privilege layer rather than in the policy, because that is
-- what the layers are for: no role needs to create or destroy a profile
-- through PostgREST at all. Profiles are created by handle_new_user(), a
-- SECURITY DEFINER trigger on auth.users that runs as the function owner and
-- is unaffected by this; they are destroyed by `on delete cascade` from
-- auth.users, which runs with the referencing table's rights and not the
-- caller's, so deleting a user through the Auth admin API still cleans up.
-- Deactivation, not deletion, is how the admin panel removes someone
-- (admin_set_deactivated, migration 0003).
--
-- The policy is split in the same breath so the two mechanisms state the same
-- rule. `for all` reads as though self-insert were intended; it never was.

begin;

revoke insert, delete on profiles from authenticated, anon;

drop policy if exists p_self_rw on profiles;
create policy p_self_read   on profiles for select using (id = auth.uid());
create policy p_self_update on profiles for update using (id = auth.uid())
                                               with check (id = auth.uid());

commit;

-- Verify (as an ordinary resident, not as the service role):
--   delete from profiles where id = auth.uid();   -- must raise: permission denied
--   insert into profiles (id, role) values (auth.uid(), 'admin');  -- same
--   update profiles set full_name = 'x' where id = auth.uid();     -- must succeed
--   update profiles set role = 'admin' where id = auth.uid();      -- must raise
