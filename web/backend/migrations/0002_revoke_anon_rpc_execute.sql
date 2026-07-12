-- 0002 — Revoke anon/PUBLIC EXECUTE on the SECURITY DEFINER RPCs.
-- Applied to the production project on 12 Jul 2026.
--
-- Why: Supabase grants EXECUTE on public-schema functions to `anon` and
-- `authenticated` by default. schema.sql granted `authenticated` explicitly but
-- never revoked `anon`, so an anonymous caller could reach these function bodies
-- and was stopped only by the internal is_staff()/is_admin() guard.
--
-- This was NOT exploitable: every guard rejects anonymous callers, verified live
-- against the production project before and after this change. It closes the
-- missing second defense layer, so anon is now stopped at the grant
-- ("permission denied for function") rather than inside the function
-- ("not authorized").
--
-- CRITICAL: `authenticated` KEEPS execute on the four browser-called RPCs. Staff
-- run Demo Mode (run_demo_scenario / reset_demo_data) and admins work the officer
-- approval queue (approve/reject_officer_request) directly from the dashboard as
-- the `authenticated` role — revoking there would break both. Only PUBLIC and
-- `anon` come off. `service_role` is retained for the edge functions.
--
-- demo_touch_node is internal-only: it is invoked by the definer functions above,
-- which run as the function owner, so it needs no role grant at all. Its original
-- revoke named `public, authenticated` but missed `anon`; fixed here.

begin;

revoke execute on function public.run_demo_scenario(text, int)       from public, anon;
revoke execute on function public.reset_demo_data()                  from public, anon;
revoke execute on function public.approve_officer_request(bigint)    from public, anon;
revoke execute on function public.reject_officer_request(bigint)     from public, anon;
revoke execute on function public.demo_touch_node(text, node_status) from public, anon;

commit;

-- Expected resulting ACL on each of the four browser-called RPCs:
--   postgres=X/postgres | authenticated=X/postgres | service_role=X/postgres
-- and on demo_touch_node:
--   postgres=X/postgres | service_role=X/postgres
