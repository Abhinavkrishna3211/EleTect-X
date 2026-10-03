-- 0012: health rows record when they were inserted, not only when they happened.
--
-- The uplink bridge drops a frame the node re-sent, and it finds the earlier
-- copy by looking for the same frame digest inside a 15-minute window. Until
-- now that window was measured against `ts`, which was always the moment the
-- row was written, so the two were the same clock and the query worked by
-- accident.
--
-- They are no longer the same clock. web/ingest now backdates `ts` to when the
-- node says the detection actually happened - ChirpStack's receive time, less
-- the transport delay the node reports in age_s - precisely so that a frame
-- delayed by a horn fire, a send retry or a broker backlog stops looking new.
-- A row backdated by more than the window falls outside a window measured from
-- the wall clock, the earlier copy is not found, and the duplicate is written
-- anyway. The dedupe would have quietly stopped working at exactly the moment
-- the delays it has to cope with got long enough to matter.
--
-- `events` already had created_at (0001). This gives `health` the same column
-- so both dedupe paths anchor on insertion time, which nothing backdates.
--
-- Backfill: existing rows get their ts, which for every row written before
-- this migration is the insertion time. That is not an approximation - it is
-- what the old code stored.

alter table health
  add column if not exists created_at timestamptz not null default now();

update health set created_at = ts where created_at is distinct from ts;

comment on column health.created_at is
  'When this row was inserted. ts is when the node says the reading was taken, '
  'and web/ingest backdates it; created_at is never backdated, so it is what '
  'the duplicate-frame window is measured against.';

-- Verify:
--   select count(*) filter (where created_at is null) as nulls,
--          count(*) filter (where created_at < ts)    as backdated
--     from health;
--   -- both expected 0
