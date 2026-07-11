-- EleTect X — health-history seed for the Phase 4c Fleet view.
--
-- seed-4b.sql seeds nodes + events but writes no `health` rows at all, so the
-- battery/solar sparklines and the predictive-maintenance rules have nothing to
-- work against. This fills 14 days of 2-hourly telemetry for the eight Sector-7
-- nodes (~1.3k rows) and nudges three nodes into genuine, rule-tripping states so
-- the Fleet maintenance queue surfaces real candidates, not a hardcoded list:
--
--   S7-11  solar intake decaying ~18% over the last 9 days   -> solar_degraded
--   S7-04  battery draining ~3 %/day over the last week       -> battery_low + battery_drain
--   S7-02  firmware a version behind the rest of the fleet     -> firmware_outdated
--
-- Run in the Supabase SQL editor after schema.sql and seed-4b.sql, as a
-- privileged role (health is admin-write under RLS). Idempotent: every row is
-- tagged metrics->>'seed' = '4c' and cleared at the top.

begin;

delete from health where metrics->>'seed' = '4c';

-- Align the three demo-condition nodes' *current* vitals with the trend below,
-- so the roster's headline number agrees with its sparkline. UPDATE (not upsert):
-- if seed-4b has not run these are no-ops rather than half-formed node rows.
update nodes set battery_pct = 34, solar_w = 3.0 where id = 'S7-04';
update nodes set solar_w = 2.9                     where id = 'S7-11';
update nodes set firmware = 'v1.4.1'               where id = 'S7-02';

-- Per-node baselines: solar peak (W at solar noon) and nominal battery centre.
-- Roughly track the instantaneous values seed-4b left on each node.
with params(id, solar_peak, batt_base) as (values
  ('S7-02', 6.1, 88),
  ('S7-12', 5.6, 79),
  ('S7-06', 5.0, 71),
  ('S7-07', 6.0, 83),
  ('S7-05', 4.4, 64),
  ('S7-04', 5.2, 55),
  ('S7-09', 6.4, 90),
  ('S7-11', 6.2, 85)
),
grid as (
  select gs as ts from generate_series(now() - interval '14 days', now(), interval '2 hours') gs
),
sample as (
  select
    p.id,
    g.ts,
    extract(epoch from (now() - g.ts)) / 86400.0                    as days_ago,
    greatest(0, sin(pi() * (extract(hour from g.ts at time zone 'Asia/Kolkata') - 6) / 12)) as daylight,
    p.solar_peak,
    p.batt_base
  from params p cross join grid g
)
insert into health (node_id, ts, battery_pct, solar_w, temp_c, metrics)
select
  id,
  ts,
  -- Battery: a diurnal swing about the node's centre, charging by day. S7-04
  -- overrides the centre with a steepening decline over the trailing week.
  least(100, greatest(15, round(
    (case
       when id = 'S7-04' then
         (case when days_ago <= 7 then 34 + (55 - 34) * days_ago / 7
               else 55 + (58 - 55) * (days_ago - 7) / 7 end)
       else batt_base
     end)
    + 4 * daylight - 2 + (random() - 0.5) * 2
  )))::int,
  -- Solar: peak * daylight, with S7-11 decaying over the last 9 days so its
  -- recent 3-day mean drops below 0.88x its 9-12-day-ago mean (solar_degraded).
  greatest(0, round((
    solar_peak * daylight
    * (case when id = 'S7-11' and days_ago <= 9 then 1 - 0.18 * (9 - days_ago) / 9 else 1 end)
    + (random() - 0.5) * 0.3 * daylight
  )::numeric, 1)),
  round((22 + 9 * daylight + (random() - 0.5) * 1.5)::numeric, 1),
  '{"seed":"4c"}'::jsonb
from sample;

commit;
