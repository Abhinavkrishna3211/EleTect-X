-- EleTect X — demo/field seed for the Phase 4b analytical views
-- (Replay, Corridor/Network intelligence, Learning). Run in the Supabase SQL
-- editor after schema.sql, as a privileged (service) role — inserts into `events`
-- are admin-only under RLS.
--
-- Idempotent: every row it writes is tagged media_url = 'seed4b' and cleared at
-- the top, so re-running refreshes the demo data without touching real rows.
-- Requires the corridor jsonb column from schema.sql.

begin;

delete from events where media_url = 'seed4b';

-- Sector-7 nodes along the Kothamangalam forest edge. Coordinates run SW (village
-- side) → NE (forest), so the safe-herding corridor reads as steering the herd up
-- and away from the settlements. Upserted so every view shares one node layout.
insert into nodes (id, name, lat, lng, kind, status, firmware, battery_pct, solar_w, last_seen) values
  ('S7-02', 'Boundary west',   10.0500, 76.6100, 'watch', 'online',      'v1.4.2', 88, 6.1, now() - interval '3 min'),
  ('S7-12', 'Paddy edge',      10.0470, 76.6180, 'guard', 'online',      'v1.4.2', 79, 5.4, now() - interval '2 min'),
  ('S7-06', 'Stream crossing', 10.0510, 76.6240, 'guard', 'online',      'v1.4.2', 71, 4.8, now() - interval '1 min'),
  ('S7-07', 'West flank',      10.0560, 76.6310, 'guard', 'online',      'v1.4.2', 83, 5.9, now() - interval '4 min'),
  ('S7-05', 'Ridge gap',       10.0610, 76.6380, 'guard', 'online',      'v1.4.2', 64, 4.2, now() - interval '2 min'),
  ('S7-04', 'East flank',      10.0670, 76.6460, 'guard', 'maintenance', 'v1.4.2', 47, 3.1, now() - interval '6 min'),
  ('S7-09', 'Forest mouth',    10.0730, 76.6540, 'watch', 'online',      'v1.4.2', 90, 6.4, now() - interval '1 min'),
  ('S7-11', 'Deep forest',     10.0790, 76.6620, 'watch', 'online',      'v1.4.2', 85, 6.0, now() - interval '5 min')
on conflict (id) do update
  set name = excluded.name, lat = excluded.lat, lng = excluded.lng,
      kind = excluded.kind, status = excluded.status, firmware = excluded.firmware,
      battery_pct = excluded.battery_pct, solar_w = excluded.solar_w, last_seen = excluded.last_seen;

-- Night elephant incursion, activation CA-2231. Six neighbour nodes hand the herd
-- off in sequence: detected on the village side, deterred behind it, escorted
-- quietly along the escape lane, confirmed clearing back into the forest. This one
-- coordinated activation drives both the Replay scrub and the Corridor handoff.
with t as (select now() - interval '15 hours' as base)
insert into events (node_id, ts, species, confidence, direction_deg, action, outcome, priority, media_url, corridor)
select * from (
  select 'S7-12', (select base from t) + interval '0 min',  'elephant', 0.82, 45, null,            null,        'high', 'seed4b',
         '{"activation":"CA-2231","seq":0,"role":"detect","heading_deg":45,"note":"Ground vibration caught the herd first; pre-armed the neighbours"}'::jsonb
  union all
  select 'S7-06', (select base from t) + interval '4 min',  'elephant', 0.91, 44, 'Strobe + horn', 'retreated', 'high', 'seed4b',
         '{"activation":"CA-2231","seq":1,"role":"deter","heading_deg":44,"note":"Low-frequency horn and strobe on the village side; herd turned"}'::jsonb
  union all
  select 'S7-07', (select base from t) + interval '9 min',  'elephant', 0.88, 41, 'Blue strobe',   'retreated', 'high', 'seed4b',
         '{"activation":"CA-2231","seq":2,"role":"deter","heading_deg":41,"note":"Blue strobe pulsed to hold the western flank"}'::jsonb
  union all
  select 'S7-05', (select base from t) + interval '13 min', 'elephant', 0.85, 39, null,            null,        'high', 'seed4b',
         '{"activation":"CA-2231","seq":3,"role":"escort","heading_deg":39,"note":"Kept quiet; escape lane held open toward the ridge gap"}'::jsonb
  union all
  select 'S7-04', (select base from t) + interval '18 min', 'elephant', 0.80, 36, null,            null,        'normal', 'seed4b',
         '{"activation":"CA-2231","seq":4,"role":"escort","heading_deg":36,"note":"Silent; the herd passed through the corridor unpressured"}'::jsonb
  union all
  select 'S7-09', (select base from t) + interval '22 min', 'elephant', 0.87, 34, null,            'retreated', 'normal', 'seed4b',
         '{"activation":"CA-2231","seq":5,"role":"detect","heading_deg":34,"note":"Confirmed the herd clearing back into the forest"}'::jsonb
) as s;

-- A second, smaller activation (CA-2188, boar, a few days earlier) so the Corridor
-- view's activation selector has more than one entry.
with t as (select now() - interval '4 days' as base)
insert into events (node_id, ts, species, confidence, direction_deg, action, outcome, priority, media_url, corridor)
select * from (
  select 'S7-02', (select base from t) + interval '0 min', 'boar', 0.74, 60, null,            null,        'normal', 'seed4b',
         '{"activation":"CA-2188","seq":0,"role":"detect","heading_deg":60,"note":"Footfall pattern flagged a boar group at the paddy edge"}'::jsonb
  union all
  select 'S7-06', (select base from t) + interval '3 min', 'boar', 0.79, 58, 'Bioacoustic',   'retreated', 'normal', 'seed4b',
         '{"activation":"CA-2188","seq":1,"role":"deter","heading_deg":58,"note":"Predator-call bioacoustic cue on the field side"}'::jsonb
  union all
  select 'S7-07', (select base from t) + interval '7 min', 'boar', 0.72, 55, null,            null,        'normal', 'seed4b',
         '{"activation":"CA-2188","seq":2,"role":"escort","heading_deg":55,"note":"Held quiet; group moved off along the tree line"}'::jsonb
) as s;

-- Learning history: ~6 weeks of scored deterrence outcomes across four patterns.
-- The retreated share rises week over week (base + slope * week) so the trend
-- chart shows the bandit converging on what works at this site. 8 encounters per
-- pattern per week, kept tight (minutes apart) so each week lands cleanly in one
-- trend bucket; node cycled across the sector.
insert into events (node_id, ts, species, confidence, action, outcome, priority, media_url)
select
  (array['S7-02','S7-06','S7-07','S7-05','S7-04','S7-09','S7-11','S7-12'])[1 + ((w.w * 8 + s.s) % 8)],
  now() - ((7 - w.w) * interval '7 days') + (s.s * interval '7 minutes'),
  'elephant',
  0.70 + 0.02 * s.s,
  p.action,
  case when s.s <= round((p.base + w.w * p.slope) * 8) then 'retreated' else 'no-response' end,
  'normal',
  'seed4b'
from generate_series(0, 6) as w(w)
cross join (values
  ('Blue strobe',   0.45, 0.050),
  ('Bioacoustic',   0.40, 0.055),
  ('Strobe + horn', 0.55, 0.045),
  ('Predator call', 0.35, 0.060)
) as p(action, base, slope)
cross join generate_series(1, 8) as s(s);

commit;
