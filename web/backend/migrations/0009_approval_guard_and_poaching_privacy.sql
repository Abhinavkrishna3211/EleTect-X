-- 0009 — two independent holes that both come from a rule being stated in one
-- place and not in its neighbour.
--
-- ===========================================================================
-- A. approve_officer_request() can demote an admin, including the only one
-- ===========================================================================
--
-- admin_set_role() carries two guards, and the comments above them say exactly
-- why: "an admin must not be able to lock themselves out of their own project"
-- and "never leave the project with no admin". approve_officer_request()
-- writes the same column and carries neither:
--
--   update public.profiles set role = 'officer' where id = target_user;
--
-- The reachable path is in the project's own setup instructions. README.md
-- says the first user signs up, then is promoted by hand:
--
--   update profiles where id = '<your-uid>' set role = 'admin';
--
-- If that first person signed up through the Forest Officer form, then
-- handle_new_user() had already queued them an officer_requests row, and the
-- manual promotion does not close it. The row stays `pending`, so it is still
-- sitting in that admin's own approvals queue. They press Approve on it — the
-- obvious thing to do with a pending request that has their own name on it —
-- and the update above runs with target_user = themselves. The project now has
-- zero admins. admin_set_role() requires is_admin(), so nobody can undo it
-- from the application; recovery needs direct database access.
--
-- Two admins makes it quieter, not better: A approves B's stale request and
-- silently demotes B, and the last-admin guard never ran because this is not
-- the function that has one.
--
-- The fix is not to copy admin_set_role's two guards. Approval is a promotion
-- path — public becomes officer — and it has no business moving anyone
-- downward, so the whole class closes by refusing to write over a role that is
-- already higher. One predicate, and it covers self-approval, approving
-- another admin, and the last-admin case together.
--
-- The request is still marked approved, because it genuinely is: the applicant
-- has officer access or better. Only the role write is skipped.
--
-- ===========================================================================
-- B. public_area_risk tells an anonymous caller that a gunshot was heard
-- ===========================================================================
--
-- message.ts and ADR 0031 are deliberate that a gunshot or chainsaw pages
-- officers and never residents, because broadcasting it tells whoever fired
-- that they were detected. eventPriority() routes both to 'high'
-- unconditionally, and the public aggregate counts every 'high' and
-- 'critical':
--
--   create view public_area_risk ... from events where priority in ('high','critical')
--   grant select on public_area_risk to authenticated, anon;
--
-- anon is granted, and the anon key ships inside the frontend bundle because
-- that is what it is for. So the counter-intelligence the audience rules buy
-- is handed back over an unauthenticated endpoint: poll
-- GET /rest/v1/public_area_risk every thirty seconds, fire a shot, watch
-- today's `detections` increment within seconds, and you have learned that a
-- node registered it and that officers were paged.
--
-- The existing comment — "the exposure is bounded by the view's own column
-- list (day, count only) — no species, location, or node detail leaks
-- through" — is true about columns and beside the point. Nothing needed to
-- leak but the fact and the timing, and the count carries both.
--
-- Excluding poaching from this view is also the more honest aggregate on its
-- own terms. The view feeds a resident-facing wildlife risk banner; a gunshot
-- is not a wildlife risk to a resident, and counting it inflated the number
-- that decides whether someone avoids a boundary path after dark.
--
-- Events with a null species are kept. Those are real detections the camera
-- could not name, and they belong in a wildlife risk count.

begin;

-- A.
create or replace function approve_officer_request(req_id bigint) returns void
language plpgsql security definer
set search_path = public as $$
declare target_user uuid;
begin
  if not is_admin() then
    raise exception 'not authorized';
  end if;

  select user_id into target_user from public.officer_requests
    where id = req_id and status = 'pending';
  if target_user is null then
    raise exception 'no pending request %', req_id;
  end if;

  update public.officer_requests
    set status = 'approved', decided_by = auth.uid(), decided_at = now()
    where id = req_id;

  -- `and role <> 'admin'` is the whole guard. Approval only ever moves someone
  -- up to officer; an admin approving their own stale request, or another
  -- admin's, keeps the role they already have. Demotion belongs to
  -- admin_set_role(), which has the self-check and the last-admin count.
  update public.profiles set role = 'officer'
    where id = target_user and role <> 'admin';
end; $$;

-- B.
create or replace view public_area_risk with (security_invoker = false) as
  select date_trunc('day', ts) as day, count(*) as detections
  from events
  where priority in ('high', 'critical')
    and (species is null or species not in ('gunshot', 'chainsaw'))
  group by 1 order by 1 desc;

commit;

-- Verify:
--
-- A. As an admin, on a pending request belonging to another admin:
--      select approve_officer_request(<id>);
--      select role from profiles where id = '<that admin>';   -- still 'admin'
--      select status from officer_requests where id = <id>;   -- 'approved'
--    And on a pending request from an ordinary signup:
--      select role from profiles where id = '<applicant>';    -- 'officer'
--
-- B. With at least one 'high' gunshot row present:
--      select sum(detections) from public_area_risk;          -- excludes it
--      insert a 'high' elephant row, re-run                   -- count moves
