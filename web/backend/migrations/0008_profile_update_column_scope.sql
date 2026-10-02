-- 0008 — close the half of the profile escalation that 0007 assumed was
-- already closed.
--
-- 0007's header says: "the column grant below it (0001) was the guard that
-- `role` must stay out of reach: `revoke update on profiles from
-- authenticated` plus a grant on the five self-service columns." That guard is
-- real and it is correct — it is written at schema.sql:233-234. It is not in
-- 0001, and it is not in any other migration. `grant update (` appears exactly
-- once in the whole repository, in schema.sql.
--
-- That distinction decides whether a live project is exposed, because the two
-- files are not two views of one thing. README.md:7-9 is explicit that an
-- existing project is maintained by running migrations/ in order, and that
-- schema.sql is for standing a new project up from nothing. So a project that
-- has been carried forward through 0001..0007 — which is every project that
-- predates this file — has never executed the revoke, and `authenticated`
-- still holds table-wide UPDATE on profiles by the public-schema default.
--
-- With 0007 applied and the grant missing, the policy that admits the write is
-- 0007's own:
--
--   p_self_update on profiles for update using (id = auth.uid())
--                                     with check (id = auth.uid())
--
--   PATCH /rest/v1/profiles?id=eq.<me>   {"role":"admin"}
--
-- The row's id is auth.uid() going in and coming out, so USING and WITH CHECK
-- both pass; `role` is an ordinary column and nothing narrows the column list.
-- One request, an ordinary resident's own JWT, and is_admin() is true: write
-- access to every table, and admin_set_role() over everyone else. This is the
-- same outcome 0007 was written to prevent, reached through the one verb 0007
-- did not touch — it revoked INSERT and DELETE and split the policy, and left
-- UPDATE to a grant that was never shipped.
--
-- Why a column grant and not a policy: RLS chooses rows, not columns. A policy
-- cannot say "this row, but not this field" without a per-column comparison
-- against the old row, which is a trigger's job and not a policy's. The
-- privilege layer already has the exact primitive, so this stays where
-- schema.sql always said it was.
--
-- SECURITY DEFINER functions are unaffected: handle_new_user() sets the role
-- column at signup, and approve_officer_request()/admin_set_role() change it
-- afterwards. All of them run as the function owner, not as `authenticated`,
-- so the revoke does not reach them. That is what makes the admin path keep
-- working while the self-service path cannot touch role at all.
--
-- 0007's policy statements are re-asserted here guarded, which also fixes the
-- one way 0007 differs from every other migration in this set: its bare
-- `create policy` raises 42710 on a second run, and because it is wrapped in
-- begin/commit the revoke on its line 40 rolls back with it. A partially
-- applied security migration that reports an error is the bad failure mode, so
-- this file is written to be safe to run as many times as anyone needs to.

begin;

-- The missing guard. REVOKE then GRANT is already idempotent; no DO block
-- needed. Keep this list in step with schema.sql:234 — these five columns are
-- the whole of what a resident may set on themselves. Notably absent: role,
-- id, created_at.
revoke update on profiles from authenticated, anon;
grant update (full_name, phone, lat, lng, alerts_enabled) on profiles to authenticated;

-- Re-assert 0007's split policy, idempotently this time. Dropping by name
-- first is what 0001 does for its own objects; it is cheaper to read than an
-- exception block and has the same effect for a policy we fully own.
drop policy if exists p_self_rw     on profiles;
drop policy if exists p_self_read   on profiles;
drop policy if exists p_self_update on profiles;

create policy p_self_read   on profiles for select using (id = auth.uid());
create policy p_self_update on profiles for update using (id = auth.uid())
                                               with check (id = auth.uid());

-- Restated from 0007 so that a project which somehow applied 0008 without 0007
-- is still left in the intended state rather than a half of it.
revoke insert, delete on profiles from authenticated, anon;

commit;

-- Verify as an ordinary resident (not the service role, which bypasses all of
-- this). The fourth line is the one this migration exists for:
--
--   update profiles set full_name = 'x'    where id = auth.uid();  -- succeeds
--   update profiles set alerts_enabled = t where id = auth.uid();  -- succeeds
--   delete from profiles                   where id = auth.uid();  -- denied
--   update profiles set role = 'admin'     where id = auth.uid();  -- denied
--
-- And confirm the grant actually landed, since that is the thing that was
-- missing and the thing no policy listing would have shown:
--
--   select privilege_type, column_name from information_schema.column_privileges
--    where table_name = 'profiles' and grantee = 'authenticated';
--   -- expect UPDATE on exactly: full_name, phone, lat, lng, alerts_enabled
