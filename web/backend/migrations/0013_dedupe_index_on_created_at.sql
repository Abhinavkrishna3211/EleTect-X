-- 0013: index the columns the duplicate-frame lookup actually filters on.
--
-- 0012 moved both dedupe windows off `ts` and onto `created_at`, because `ts`
-- is now backdated to when the node says the detection happened. The indexes
-- were not moved with them. Both tables carry `(node_id, ts desc)` and nothing
-- else, so the lookup in web/ingest/src/uplink.ts:126
--
--   select id from <table>
--    where node_id = $1 and <col>->>'frame' = $2 and created_at >= $3
--    limit 1
--
-- has no index that covers its range predicate and falls back to a scan.
--
-- This does not affect correctness and the tables are small today - a few
-- hundred events, a few thousand health rows - so the planner is right to scan
-- them and this changes nothing measurable yet. It is worth doing now because
-- the growth is structural rather than speculative: a node writes a status
-- frame every ten minutes, so `health` gains about 4,400 rows per node per
-- month whether or not anything is detected, and this query runs once per
-- uplink on the path that decides whether an alert is written. The cost of
-- being wrong about it later is a scan on every frame during the deployment
-- this is being handed over for.
--
-- `(node_id, created_at desc)` is the whole fix. The jsonb key is deliberately
-- not in the index: within one duplicate window a single node has only a
-- handful of rows, so the index does the selective work and the digest
-- comparison is a filter over almost nothing. An expression index on
-- `<col>->>'frame'` would be larger, would have to be written twice with a
-- different column name each time, and would buy nothing at this row count.
--
-- The existing `(node_id, ts desc)` indexes stay: the dashboard orders by `ts`,
-- which is the question a reader asks (when did this happen), while `created_at`
-- answers the bridge's question (when did we store it). Different clocks, two
-- indexes.

create index if not exists events_node_created_at_idx
  on events (node_id, created_at desc);

create index if not exists health_node_created_at_idx
  on health (node_id, created_at desc);

-- Verify:
--   select indexname from pg_indexes
--    where tablename in ('events','health') and indexname like '%created_at%';
--   -- expected: events_node_created_at_idx, health_node_created_at_idx
--
--   explain (costs off)
--   select id from health
--    where node_id = '2cf7f1205100a785'
--      and metrics->>'frame' = 'x'
--      and created_at >= now() - interval '15 minutes'
--    limit 1;
--   -- expected to reference health_node_created_at_idx once the table is large
--   -- enough for the planner to prefer it; on a small table a seq scan here is
--   -- the correct plan and not a failure of this migration.
