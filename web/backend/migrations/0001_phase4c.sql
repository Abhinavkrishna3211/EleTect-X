-- EleTect X — Phase 4c delta: fleet maintenance provenance + Demo Mode RPCs.
-- Already folded into schema.sql; apply this file only to a project that was
-- provisioned before Phase 4c. Safe to re-run.
--
-- Adds nothing to is_staff()/is_admin() and changes no existing RLS policy.

begin;

-- ---------- maintenance provenance ----------
-- Distinguishes a flag raised by the fleet threshold rule from one written by a
-- Demo Mode scenario, so reset_demo_data() has a reliable predicate and the
-- fleet queue can label where a flag came from.
alter table maintenance add column if not exists source text;
comment on column maintenance.source is
  'Who raised this flag: ''rule'' (fleet threshold rule, staff-confirmed) or '
  '''demo'' (Demo Mode scenario, cleared by reset_demo_data). Null = legacy row.';

-- The fleet maintenance queue is actionable, so it has to update live the same
-- way the map does. Guarded: adding a table twice to a publication is an error.
do $$
begin
  alter publication supabase_realtime add table maintenance;
exception when duplicate_object then null;
end $$;

-- ---------- Demo Mode ----------
-- A Demo Mode scenario mutates node status so the map visibly reacts. Reset must
-- restore the node's *true* prior state, not guess at it: S7-04 is legitimately
-- 'maintenance' in the field seed, so a blanket "set everything online" would
-- silently corrupt real fleet state. Capture the row before the first demo write
-- touches it; reset replays it back and clears the table.
create table if not exists demo_node_snapshot (
  node_id     text primary key references nodes on delete cascade,
  status      node_status,
  battery_pct int,
  solar_w     real,
  last_seen   timestamptz,
  captured_at timestamptz not null default now()
);
alter table demo_node_snapshot enable row level security;
do $$
begin
  create policy dns_staff_read on demo_node_snapshot for select using (is_staff());
exception when duplicate_object then null;
end $$;
-- No insert/update/delete policy on purpose: only the SECURITY DEFINER functions
-- below ever write here, and they run as the function owner.

-- Snapshot-then-mutate, used by every scenario step that touches a node. Internal
-- to the demo RPCs; not part of the client-callable surface. The is_staff()
-- check is a second, independent barrier on top of the revoke below — a Day 3
-- adversarial pass found the revoke alone had drifted out of sync with the live
-- project at least once, so this function no longer depends on the grant being
-- correct as its only defense.
create or replace function demo_touch_node(p_node text, p_status node_status)
returns void language plpgsql security definer
set search_path = public as $$
begin
  if not is_staff() then
    raise exception 'not authorized';
  end if;

  insert into demo_node_snapshot (node_id, status, battery_pct, solar_w, last_seen)
    select id, status, battery_pct, solar_w, last_seen from public.nodes where id = p_node
    on conflict (node_id) do nothing;
  update public.nodes set status = p_status, last_seen = now() where id = p_node;
end; $$;
revoke execute on function demo_touch_node(text, node_status) from public, authenticated;

-- Runs one step of one demo scenario and returns the log lines it produced.
--
-- SECURITY DEFINER because `events` is admin-write under e_admin_all, and Demo
-- Mode has to be runnable by an officer. Two things keep that from turning this
-- into a general-purpose insert primitive for any authenticated user: the
-- is_staff() guard, and the fixed scenario whitelist below. Both are load-bearing.
--
-- Every row written is tagged so reset_demo_data() can find it again:
--   events.media_url = 'demo' · health.metrics->>'demo' = 'true'
--   maintenance.source = 'demo' · alerts.status = 'demo'
--
-- Every event is written priority = 'normal', never 'high'. This is a deliberate
-- safety barrier, not an oversight. The send-alert edge function fans SMS out to
-- officers and to opted-in residents within 3 km of any high-priority event, and
-- the public_area_risk view (public Stay Safe page) counts only high-priority
-- rows. Keeping demo events at 'normal' means a scenario can never page a village
-- or move the public risk figure, independently of send-alert's own demo guard.
--
-- Stepping is driven by the client between calls rather than by pg_sleep: a
-- SECURITY DEFINER function must not hold a connection open to pace an animation.
-- Each step is a real INSERT, so it reaches the dashboard over the same realtime
-- channel a live node would use.
create or replace function run_demo_scenario(p_scenario text, p_step int default 1)
returns jsonb language plpgsql security definer
set search_path = public as $$
declare
  v_total    int;
  v_log      jsonb := '[]'::jsonb;
  v_event_id bigint;
  v_hm       text := to_char(now() at time zone 'Asia/Kolkata', 'HH24:MI');
  -- log dot colours, matching the dashboard status palette
  c_gold  constant text := '#E2A13C';
  c_green constant text := '#5FA97C';
  c_red   constant text := '#E25B4A';
  c_amber constant text := '#D9B44A';
  c_mute  constant text := '#6B7A70';
begin
  if not is_staff() then
    raise exception 'not authorized';
  end if;

  v_total := case p_scenario
    when 'confirmed_elephant' then 3
    when 'sensor_dropout'     then 2
    when 'corridor_handoff'   then 5
    when 'declined_livestock' then 2
    when 'fleet_degradation'  then 3
    when 'poaching_acoustic'  then 3
    else null
  end;
  if v_total is null then
    raise exception 'unknown scenario %', p_scenario;
  end if;
  if p_step < 1 or p_step > v_total then
    raise exception 'step % out of range for scenario % (1..%)', p_step, p_scenario, v_total;
  end if;

  -- 1. Three-sensor confirmed elephant; deterrence fires and the herd retreats.
  if p_scenario = 'confirmed_elephant' then
    if p_step = 1 then
      perform demo_touch_node('S7-06', 'alert');
      v_log := jsonb_build_array(
        jsonb_build_object('time', v_hm, 'dot', c_gold,
          'text', 'S7-06 ground vibration trigger. Footfall signature at 22 Hz, neighbours pre-armed.'));

    elsif p_step = 2 then
      insert into events (node_id, species, confidence, direction_deg, media_url, action, priority, fusion)
      values ('S7-06', 'elephant', 0.9448, 45, 'demo', 'Strobe + horn', 'normal',
        '{"prior":-1.2,"logodds":2.84,"modalities":[
           {"kind":"seismic","available":true,"weight":1.0,"logodds":1.6,"baseline":0.2,"contribution":1.4,"confidence":0.8320},
           {"kind":"acoustic","available":true,"weight":0.8,"logodds":1.0,"baseline":0.1,"contribution":0.72,"confidence":0.7311},
           {"kind":"vision","available":true,"weight":1.2,"logodds":1.7,"baseline":0.1,"contribution":1.92,"confidence":0.8455}]}'::jsonb);
      v_log := jsonb_build_array(
        jsonb_build_object('time', v_hm, 'dot', c_gold,
          'text', 'Vision confirms Asian elephant. All three modalities reporting, fused confidence 94%.'),
        jsonb_build_object('time', v_hm, 'dot', c_gold,
          'text', 'Deterrent selected: strobe + horn. Pattern not used at this node recently.'));

    else
      select id into v_event_id from events
        where media_url = 'demo' and node_id = 'S7-06' order by id desc limit 1;
      update events set outcome = 'retreated' where id = v_event_id;
      insert into alerts (event_id, channel, recipient, status)
        values (v_event_id, 'sms', '+91 ***** 4821', 'demo');
      perform demo_touch_node('S7-06', 'online');
      v_log := jsonb_build_array(
        jsonb_build_object('time', v_hm, 'dot', c_green,
          'text', 'Herd retreated. Outcome verified, deterrent stopped on retreat rather than run to completion.'),
        jsonb_build_object('time', v_hm, 'dot', c_green,
          'text', 'Patrol notified. Demo channel, no message left the system.'));
    end if;

  -- 2. Vision drops out in rain. Availability-gated fusion falls below the gate,
  --    so nothing fires. A missing modality is absent, never scored as a zero.
  elsif p_scenario = 'sensor_dropout' then
    if p_step = 1 then
      perform demo_touch_node('S7-05', 'alert');
      v_log := jsonb_build_array(
        jsonb_build_object('time', v_hm, 'dot', c_amber,
          'text', 'Heavy rain at S7-05. Lens occluded, vision pipeline reports unavailable.'));

    else
      insert into events (node_id, species, confidence, direction_deg, media_url, action, priority, fusion)
      values ('S7-05', 'elephant', 0.6083, 38, 'demo', 'No deterrent - below threshold', 'normal',
        '{"prior":-1.2,"logodds":0.44,"modalities":[
           {"kind":"seismic","available":true,"weight":1.0,"logodds":1.6,"baseline":0.2,"contribution":1.4,"confidence":0.8320},
           {"kind":"acoustic","available":true,"weight":0.8,"logodds":0.4,"baseline":0.1,"contribution":0.24,"confidence":0.5987},
           {"kind":"vision","available":false,"weight":1.2,"logodds":null,"baseline":0.1,"contribution":0,"confidence":null}]}'::jsonb);
      perform demo_touch_node('S7-05', 'online');
      v_log := jsonb_build_array(
        jsonb_build_object('time', v_hm, 'dot', c_gold,
          'text', 'Fusing on seismic and audio alone. Vision drops out of the sum, it is not counted as evidence against.'),
        jsonb_build_object('time', v_hm, 'dot', c_amber,
          'text', 'Fused confidence 61%, under the deterrence gate. Same ground evidence, but without the camera it is not enough.'),
        jsonb_build_object('time', v_hm, 'dot', c_mute,
          'text', 'Holding. Node stays in watch and an officer is asked for eyes-on.'));
    end if;

  -- 3. Coordinated safe-herding corridor: detect on the village side, push from
  --    behind, keep the forest-side lane quiet so the herd always has an exit.
  elsif p_scenario = 'corridor_handoff' then
    if p_step = 1 then
      perform demo_touch_node('S7-12', 'alert');
      insert into events (node_id, species, confidence, direction_deg, media_url, priority, corridor)
      values ('S7-12', 'elephant', 0.84, 45, 'demo', 'normal',
        '{"activation":"CA-DEMO-1","seq":0,"role":"detect","heading_deg":45,"note":"Ground vibration caught the herd first; pre-armed the neighbours"}'::jsonb);
      v_log := jsonb_build_array(
        jsonb_build_object('time', v_hm, 'dot', c_gold,
          'text', 'S7-12 detects first. Activation CA-DEMO-1 opened, neighbours pre-armed.'));

    elsif p_step = 2 then
      perform demo_touch_node('S7-12', 'online');
      perform demo_touch_node('S7-06', 'alert');
      insert into events (node_id, species, confidence, direction_deg, media_url, action, outcome, priority, corridor, fusion)
      values ('S7-06', 'elephant', 0.9089, 44, 'demo', 'Strobe + horn', 'retreated', 'normal',
        '{"activation":"CA-DEMO-1","seq":1,"role":"deter","heading_deg":44,"note":"Low-frequency horn and strobe on the village side; herd turned"}'::jsonb,
        '{"prior":-1.2,"logodds":2.31,"modalities":[
           {"kind":"seismic","available":true,"weight":1.0,"logodds":1.5,"baseline":0.2,"contribution":1.3,"confidence":0.8176},
           {"kind":"acoustic","available":true,"weight":0.8,"logodds":0.9,"baseline":0.1,"contribution":0.64,"confidence":0.7109},
           {"kind":"vision","available":true,"weight":1.2,"logodds":1.5,"baseline":0.1,"contribution":1.68,"confidence":0.8176}]}'::jsonb);
      v_log := jsonb_build_array(
        jsonb_build_object('time', v_hm, 'dot', c_red,
          'text', 'S7-06 deters on the village side. Herd turns back toward the ridge.'));

    elsif p_step = 3 then
      perform demo_touch_node('S7-06', 'online');
      perform demo_touch_node('S7-07', 'alert');
      insert into events (node_id, species, confidence, direction_deg, media_url, action, outcome, priority, corridor)
      values ('S7-07', 'elephant', 0.88, 41, 'demo', 'Blue strobe', 'retreated', 'normal',
        '{"activation":"CA-DEMO-1","seq":2,"role":"deter","heading_deg":41,"note":"Blue strobe pulsed to hold the western flank"}'::jsonb);
      v_log := jsonb_build_array(
        jsonb_build_object('time', v_hm, 'dot', c_red,
          'text', 'S7-07 holds the western flank with a blue strobe.'));

    elsif p_step = 4 then
      perform demo_touch_node('S7-07', 'online');
      perform demo_touch_node('S7-05', 'alert');
      insert into events (node_id, species, confidence, direction_deg, media_url, priority, corridor)
      values ('S7-05', 'elephant', 0.85, 39, 'demo', 'normal',
        '{"activation":"CA-DEMO-1","seq":3,"role":"escort","heading_deg":39,"note":"Kept quiet; escape lane held open toward the ridge gap"}'::jsonb);
      v_log := jsonb_build_array(
        jsonb_build_object('time', v_hm, 'dot', c_green,
          'text', 'S7-05 stays silent on purpose. The escape lane to the ridge gap is the one direction never pressured.'));

    else
      perform demo_touch_node('S7-05', 'online');
      perform demo_touch_node('S7-09', 'alert');
      insert into events (node_id, species, confidence, direction_deg, media_url, outcome, priority, corridor)
      values ('S7-09', 'elephant', 0.87, 34, 'demo', 'retreated', 'normal',
        '{"activation":"CA-DEMO-1","seq":4,"role":"detect","heading_deg":34,"note":"Confirmed the herd clearing back into the forest"}'::jsonb);
      perform demo_touch_node('S7-09', 'online');
      v_log := jsonb_build_array(
        jsonb_build_object('time', v_hm, 'dot', c_green,
          'text', 'S7-09 confirms the herd clearing into the forest. Corridor closed, no node herded it toward a settlement.'));
    end if;

  -- 4. Explainability: strong footfall, but vision says cattle. The system shows
  --    its working for why it did NOT fire.
  elsif p_scenario = 'declined_livestock' then
    if p_step = 1 then
      perform demo_touch_node('S7-02', 'alert');
      v_log := jsonb_build_array(
        jsonb_build_object('time', v_hm, 'dot', c_gold,
          'text', 'Strong footfall at S7-02. Seismic alone puts elephant likelihood at 92%.'));

    else
      insert into events (node_id, species, confidence, direction_deg, media_url, action, priority, fusion)
      values ('S7-02', 'cattle', 0.3799, 62, 'demo', 'No deterrent - livestock signature', 'normal',
        '{"prior":-1.2,"logodds":-0.49,"modalities":[
           {"kind":"seismic","available":true,"weight":1.0,"logodds":2.4,"baseline":0.2,"contribution":2.2,"confidence":0.9168},
           {"kind":"acoustic","available":true,"weight":0.8,"logodds":0.6,"baseline":0.1,"contribution":0.4,"confidence":0.6457},
           {"kind":"vision","available":true,"weight":1.2,"logodds":-1.475,"baseline":0.1,"contribution":-1.89,"confidence":0.1863}]}'::jsonb);
      perform demo_touch_node('S7-02', 'online');
      v_log := jsonb_build_array(
        jsonb_build_object('time', v_hm, 'dot', c_gold,
          'text', 'Vision classifies domestic cattle. Elephant likelihood from the camera is 19%.'),
        jsonb_build_object('time', v_hm, 'dot', c_amber,
          'text', 'Vision contributes -1.89 log-odds and vetoes the seismic evidence. Fused confidence falls to 38%.'),
        jsonb_build_object('time', v_hm, 'dot', c_green,
          'text', 'Declined to act. No deterrent fired, no alert sent, and the reason is on the record.'));
    end if;

  -- 5. Predictive maintenance: the fleet pipeline, not the detection one.
  elsif p_scenario = 'fleet_degradation' then
    if p_step = 1 then
      insert into health (node_id, ts, battery_pct, solar_w, temp_c, metrics)
      values ('S7-11', now() - interval '4 hours', 84, 3.1, 29.4, '{"demo":true}'::jsonb),
             ('S7-11', now() - interval '2 hours', 82, 2.9, 30.1, '{"demo":true}'::jsonb),
             ('S7-11', now(),                      81, 2.9, 30.6, '{"demo":true}'::jsonb);
      v_log := jsonb_build_array(
        jsonb_build_object('time', v_hm, 'dot', c_amber,
          'text', 'S7-11 solar intake 2.9 W at solar noon. Expected 6.0 W for this panel and season.'));

    elsif p_step = 2 then
      perform demo_touch_node('S7-11', 'maintenance');
      v_log := jsonb_build_array(
        jsonb_build_object('time', v_hm, 'dot', c_amber,
          'text', 'S7-11 moved to ATTENTION. Detection stays live; only the heavy deterrent budget is held back.'));

    else
      insert into maintenance (node_id, flag, reason, source)
      values ('S7-11', 'solar_degraded',
        'Solar intake trending down 12% over 9 days. Panel cleaning recommended before the monsoon window.',
        'demo');
      v_log := jsonb_build_array(
        jsonb_build_object('time', v_hm, 'dot', c_gold,
          'text', 'Maintenance flag raised into the fleet queue. Predicted, not reactive: the node is still online.'));
    end if;

  -- 6. Anti-poaching. Acoustic-only path, and the correct action is silence: you
  --    do not strobe a poacher, you send people.
  else
    if p_step = 1 then
      perform demo_touch_node('S7-09', 'alert');
      v_log := jsonb_build_array(
        jsonb_build_object('time', v_hm, 'dot', c_red,
          'text', 'Acoustic transient at S7-09. Broadband, 0.9 ms rise time, no low-frequency precursor.'));

    elsif p_step = 2 then
      insert into events (node_id, species, confidence, direction_deg, media_url, action, priority, fusion)
      values ('S7-09', 'gunshot', 0.9340, 118, 'demo', 'Silent alert - deterrents held', 'normal',
        '{"prior":-3.5,"logodds":2.65,"modalities":[
           {"kind":"seismic","available":true,"weight":1.0,"logodds":0.2,"baseline":0.2,"contribution":0,"confidence":0.5498},
           {"kind":"acoustic","available":true,"weight":1.5,"logodds":4.2,"baseline":0.1,"contribution":6.15,"confidence":0.9852},
           {"kind":"vision","available":false,"weight":1.2,"logodds":null,"baseline":0.1,"contribution":0,"confidence":null}]}'::jsonb);
      v_log := jsonb_build_array(
        jsonb_build_object('time', v_hm, 'dot', c_red,
          'text', 'Gunshot signature, 93%. Carried entirely by audio: the geophone hears nothing below 60 Hz to contribute.'));

    else
      select id into v_event_id from events
        where media_url = 'demo' and node_id = 'S7-09' and species = 'gunshot' order by id desc limit 1;
      insert into alerts (event_id, channel, recipient, status)
        values (v_event_id, 'sms', '+91 ***** 7730', 'demo');
      perform demo_touch_node('S7-09', 'online');
      v_log := jsonb_build_array(
        jsonb_build_object('time', v_hm, 'dot', c_green,
          'text', 'Silent patrol alert dispatched. Every deterrent deliberately held: a strobe would only tell the shooter he was seen.'));
    end if;
  end if;

  return jsonb_build_object(
    'scenario', p_scenario,
    'step',     p_step,
    'total',    v_total,
    'done',     p_step >= v_total,
    'log',      v_log);
end; $$;
grant execute on function run_demo_scenario(text, int) to authenticated;

-- Clears only demo-tagged rows and puts every touched node back to the exact
-- state it held before the first scenario ran. Demo `alerts` rows need no
-- predicate of their own: alerts.event_id cascades on delete from events.
create or replace function reset_demo_data() returns jsonb
language plpgsql security definer
set search_path = public as $$
declare
  v_events int; v_health int; v_maint int; v_nodes int;
begin
  if not is_staff() then
    raise exception 'not authorized';
  end if;

  delete from events where media_url = 'demo';
  get diagnostics v_events = row_count;

  delete from health where metrics->>'demo' = 'true';
  get diagnostics v_health = row_count;

  delete from maintenance where source = 'demo';
  get diagnostics v_maint = row_count;

  update nodes n set
      status = s.status, battery_pct = s.battery_pct,
      solar_w = s.solar_w, last_seen = s.last_seen
    from demo_node_snapshot s where n.id = s.node_id;
  get diagnostics v_nodes = row_count;
  delete from demo_node_snapshot where true;

  return jsonb_build_object(
    'events', v_events, 'health', v_health,
    'maintenance', v_maint, 'nodes_restored', v_nodes);
end; $$;
grant execute on function reset_demo_data() to authenticated;

commit;
