-- 0006 — a critical event can be taken by an officer, and the alert audit
-- trail stops being writable by the people it audits.
--
-- 'critical' means the node fired its top tier and the animal stayed (ADR
-- 0034) — "send a person". Until now that arrived as one more paging email
-- among the 'high' ones, with nothing recording whether anybody acted on it,
-- so two officers could both drive out or neither could.
--
-- The acknowledgement goes on `events`, not on `alerts.acked_by`. The question
-- being answered is about the event — is someone going to this one — while an
-- `alerts` row is one delivery to one recipient. Stamping an officer's uuid
-- across the rows that recorded a resident's email would make the audit log
-- state something that did not happen. `alerts.acked_by` keeps its own meaning
-- and stays unused for now.
--
-- SECURITY DEFINER for the same reason approve_officer_request() is: RLS gives
-- officers select on events and write to admins only (e_staff_read /
-- e_admin_all), and widening that so an officer could acknowledge would also
-- let them edit species, confidence and priority on any event. The function is
-- the narrow hole: it sets three columns, on one row, for a caller it checks
-- itself.

begin;

alter table events add column if not exists acked_by uuid references profiles;
alter table events add column if not exists acked_at timestamptz;

-- Partial index: the open-critical queue is the only thing that reads these,
-- and it is a handful of rows against a table that grows with every detection.
create index if not exists events_unacked_critical_idx
  on events (ts desc) where priority = 'critical' and acked_at is null;

-- acked_by is always auth.uid(), never a parameter. An officer saying they are
-- going is only worth recording if it cannot be recorded on someone else's
-- behalf.
--
-- First ack wins: the `acked_at is null` guard makes a second caller a no-op
-- rather than overwriting the first responder's name. Two officers pressing it
-- at once is the expected case, not an edge case, and the useful record is who
-- committed first.
create or replace function acknowledge_event(p_event_id bigint) returns void
language plpgsql security definer
set search_path = public as $$
begin
  if not is_staff() then
    raise exception 'not authorized';
  end if;
  update events
     set acked_by = auth.uid(), acked_at = now()
   where id = p_event_id and acked_at is null;
end;
$$;

-- Per 0002: Supabase grants EXECUTE to anon and PUBLIC by default on
-- public-schema functions, and the is_staff() guard inside should be the
-- second line of defence, not the first.
revoke execute on function public.acknowledge_event(bigint) from public, anon;
grant  execute on function public.acknowledge_event(bigint) to authenticated;

-- ---------------------------------------------------------------------------
-- Security fix, same area: a_staff_ack was an unrestricted UPDATE on alerts.
--
-- `create policy a_staff_ack on alerts for update using (is_staff())` was
-- written for an acknowledgement feature that was never built. RLS chooses
-- ROWS; it does not choose columns, and no column grant narrowed this one the
-- way profiles' does. So any officer could rewrite `status`, `channel`,
-- `recipient` and `event_id` on any row of the delivery audit log — the record
-- of who was warned and whether it arrived — and could set `acked_by` to
-- another officer's uuid.
--
-- Nothing reads or writes alerts from the application, so dropping this breaks
-- no caller. Staff keep select (a_staff_read); admins keep full write
-- (a_admin_all); the edge function writes as service_role and is unaffected by
-- RLS entirely.
drop policy if exists a_staff_ack on alerts;

commit;
