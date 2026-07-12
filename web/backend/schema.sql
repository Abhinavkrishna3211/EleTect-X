-- EleTect X — Supabase schema + Row-Level Security
-- Roles: admin | officer (rangers+officers merged) | public
-- Run in Supabase SQL editor (or via `supabase db push`).

create type user_role as enum ('admin', 'officer', 'public');
create type node_status as enum ('online', 'offline', 'alert', 'maintenance');

-- 1. Profiles (1:1 with auth.users). Public users may opt in to SMS alerts.
create table profiles (
  id            uuid primary key references auth.users on delete cascade,
  role          user_role   not null default 'public',
  full_name     text,
  phone         text,                 -- E.164, e.g. +9198...
  lat           double precision,     -- for proximity alerts (public opt-in)
  lng           double precision,
  alerts_enabled boolean    not null default false,
  created_at    timestamptz not null default now()
);

-- 2. Nodes
create table nodes (
  id         text primary key,        -- serial / DevEUI
  name       text,
  lat        double precision,
  lng        double precision,
  kind       text default 'guard',    -- guard | watch
  status     node_status default 'offline',
  firmware   text,
  battery_pct int,
  solar_w    real,
  last_seen  timestamptz,
  created_at timestamptz not null default now()
);

-- 3. Detection / deterrence events
create table events (
  id           bigint generated always as identity primary key,
  node_id      text references nodes on delete cascade,
  ts           timestamptz not null default now(),
  species      text,
  confidence   real,                  -- 0..1
  direction_deg int,
  media_url    text,
  action       text,                  -- deterrent chosen
  outcome      text,                  -- retreated / no-response / ...
  priority     text default 'normal', -- normal | high
  fusion       jsonb,                 -- per-modality log-odds breakdown (see comment)
  corridor     jsonb,                 -- coordinated-corridor activation breakdown (see comment)
  created_at   timestamptz not null default now()
);
create index on events (node_id, ts desc);

-- Explainable-AI breakdown behind `confidence`. CONTEXT.md §4 fuses the sensors
-- as L = L_prior + Σ aᵢ wᵢ (ℓᵢ − ℓ₀ᵢ), P = σ(L). `confidence` stays the scalar
-- fused P; `fusion` records how it was reached so the dashboard can show which
-- modalities contributed and by how much. Nullable — an event with no cognition
-- pass renders a reduced card. A modality that did not report is available=false
-- (dropped out), never 0. Shape (not DB-enforced, typed in the frontend):
--   { "prior": <log-odds>, "logodds": <fused L; σ(logodds)=confidence>,
--     "modalities": [ { "kind": "seismic|acoustic|vision", "available": bool,
--       "weight": w, "logodds": ℓ|null, "baseline": ℓ₀, "contribution": a·w·(ℓ−ℓ₀),
--       "confidence": σ(ℓ)|null } ] }
comment on column events.fusion is
  'Per-modality log-odds fusion breakdown behind confidence (CONTEXT.md §4). '
  'A modality that did not report is available=false (dropped out), never 0.';

-- Coordinated-corridor activation (CONTEXT.md §4: safe-herding corridors). Movement
-- is derived from the node-detection SEQUENCE (no TDOA): grouping neighbouring
-- events into one herd movement and recording each node's role in the handoff is
-- not derivable from ts alone, so it is stored here. Nullable — an ordinary,
-- uncoordinated detection leaves this null. Shape (not DB-enforced, typed in the
-- frontend):
--   { "activation": "CA-2231",       -- groups all events of one herd movement
--     "seq": 0,                        -- 0-based order in the handoff sequence
--     "role": "detect|deter|escort",   -- detect=first sense; deter=village-side
--                                       --   push; escort=forest-side lane kept quiet
--     "heading_deg": 42,               -- herd heading from node sequence (no TDOA)
--     "note": "pre-armed neighbours" } -- step-card action text
comment on column events.corridor is
  'Coordinated safe-herding corridor activation breakdown (CONTEXT.md §4). Groups '
  'neighbour events of one herd movement (activation) with each node''s handoff '
  'role (detect/deter/escort) and sequence order; null for uncoordinated events.';

-- 4. Alerts sent (audit)
create table alerts (
  id         bigint generated always as identity primary key,
  event_id   bigint references events on delete cascade,
  channel    text default 'sms',
  recipient  text,
  status     text default 'queued',   -- queued | sent | failed | acked
  acked_by   uuid references profiles,
  acked_at   timestamptz,
  created_at timestamptz not null default now()
);

-- 5. Health telemetry
create table health (
  id         bigint generated always as identity primary key,
  node_id    text references nodes on delete cascade,
  ts         timestamptz not null default now(),
  battery_pct int, solar_w real, temp_c real, metrics jsonb
);
create index on health (node_id, ts desc);

-- 6. Maintenance queue (predictive). `source` records who raised the flag:
-- 'rule' = the fleet threshold rule (staff-confirmed on the Fleet page), 'demo' =
-- a Demo Mode scenario (cleared by reset_demo_data). Null on legacy rows.
create table maintenance (
  id       bigint generated always as identity primary key,
  node_id  text references nodes on delete cascade,
  flag     text, reason text, resolved boolean default false,
  source   text,
  created_at timestamptz not null default now()
);

-- 7. Forest-officer access requests. A signup never grants the officer role
-- directly — it only queues a request here; an admin promotes profiles.role
-- via approve_officer_request() below.
create type officer_request_status as enum ('pending', 'approved', 'rejected');
create table officer_requests (
  id             bigint generated always as identity primary key,
  user_id        uuid not null references auth.users on delete cascade,
  full_name      text not null,
  department     text not null,
  designation    text not null,
  official_email text not null,
  phone          text,
  status         officer_request_status not null default 'pending',
  decided_by     uuid references profiles,
  decided_at     timestamptz,
  created_at     timestamptz not null default now()
);
-- One outstanding request per user at a time.
create unique index officer_requests_one_pending_per_user
  on officer_requests (user_id) where (status = 'pending');

-- Auto-create a profile on signup (default role: public). When signup
-- metadata marks this as an officer request, also queue a pending row in
-- officer_requests — the account stays role='public' until an admin approves
-- it. Runs as SECURITY DEFINER so it works regardless of RLS or whether
-- email confirmation is enabled (no client-side insert is ever needed).
-- search_path is explicit here: this trigger runs as the supabase_auth_admin
-- role when fired from auth.users, whose default search_path does not
-- include public, so unqualified table names would fail with
-- "relation ... does not exist" even though the tables exist.
create function handle_new_user() returns trigger language plpgsql security definer
set search_path = public as $$
begin
  insert into public.profiles (id, full_name, phone)
    values (new.id, new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'phone');

  if (new.raw_user_meta_data->>'officer_request')::boolean then
    insert into public.officer_requests (user_id, full_name, department, designation, official_email, phone)
      values (
        new.id,
        new.raw_user_meta_data->>'full_name',
        new.raw_user_meta_data->>'department',
        new.raw_user_meta_data->>'designation',
        new.raw_user_meta_data->>'official_email',
        new.raw_user_meta_data->>'phone'
      );
  end if;

  return new;
end; $$;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function handle_new_user();

-- Helper: is the current user an officer or admin? Schema-qualified for the
-- same reason as handle_new_user() below — don't rely on the caller's search_path.
-- SECURITY DEFINER is required, not optional: profiles' own RLS policies call
-- is_staff()/is_admin() to decide readability. If these ran as the invoking
-- role, their internal "select from profiles" would re-trigger profiles' RLS,
-- which calls is_staff()/is_admin() again — infinite recursion, surfaced by
-- Postgres as a stack-depth error (PostgREST reports it as a bare 500). Running
-- as definer lets the internal lookup bypass RLS entirely, which is safe here
-- because these functions only ever return a boolean, never raw row data.
create function is_staff() returns boolean language sql stable security definer
set search_path = public as $$
  select exists(select 1 from public.profiles p where p.id = auth.uid() and p.role in ('admin','officer'));
$$;
create function is_admin() returns boolean language sql stable security definer
set search_path = public as $$
  select exists(select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin');
$$;

-- ---------- RLS ----------
alter table profiles    enable row level security;
alter table nodes       enable row level security;
alter table events      enable row level security;
alter table alerts      enable row level security;
alter table health      enable row level security;
alter table maintenance enable row level security;
alter table officer_requests enable row level security;

-- Profiles: users manage their own; staff can read all; admin can write all
create policy p_self_rw on profiles for all using (id = auth.uid()) with check (id = auth.uid());
create policy p_staff_read on profiles for select using (is_staff());
create policy p_admin_all on profiles for all using (is_admin()) with check (is_admin());

-- Restrict self-service profile updates to non-privileged columns only.
-- RLS above controls which ROWS a user can touch; this controls which COLUMNS —
-- role, id, and created_at must stay out of user hands, or a public signup
-- could grant themselves admin via a direct PATCH request. SECURITY DEFINER
-- functions (handle_new_user, any future admin-approval function) run as the
-- function owner, not as `authenticated`, so they are unaffected by this revoke.
revoke update on profiles from authenticated;
grant update (full_name, phone, lat, lng, alerts_enabled) on profiles to authenticated;

-- Operational tables: staff read; admin full write. (Public gets aggregates via a view below.)
create policy n_staff_read on nodes for select using (is_staff());
create policy n_admin_all  on nodes for all using (is_admin()) with check (is_admin());
create policy e_staff_read on events for select using (is_staff());
create policy e_admin_all  on events for all using (is_admin()) with check (is_admin());
create policy a_staff_read on alerts for select using (is_staff());
create policy a_staff_ack  on alerts for update using (is_staff());
create policy a_admin_all  on alerts for all using (is_admin()) with check (is_admin());
create policy h_staff_read on health for select using (is_staff());
create policy h_admin_all  on health for all using (is_admin()) with check (is_admin());
create policy m_staff_rw   on maintenance for all using (is_staff()) with check (is_staff());

-- Officer requests: applicant can see their own request's status; admin sees
-- the full queue. No INSERT/UPDATE policy for authenticated — rows are only
-- ever written by handle_new_user() and the approve/reject functions below,
-- all SECURITY DEFINER, so a request can't be self-approved via a direct write.
create policy or_self_read  on officer_requests for select using (user_id = auth.uid());
create policy or_admin_all  on officer_requests for all using (is_admin()) with check (is_admin());

-- Admin-only approval actions. SECURITY DEFINER lets these update profiles.role
-- despite the column-grant restriction above; the is_admin() check inside
-- guards against a non-admin calling the RPC directly.
create function approve_officer_request(req_id bigint) returns void
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
  update public.profiles set role = 'officer' where id = target_user;
end; $$;
-- Supabase grants EXECUTE on public-schema functions to anon+authenticated by
-- default, so the grant below is not enough on its own: anon must be revoked
-- explicitly, or an anonymous caller reaches the function body and is stopped
-- only by the internal guard. `authenticated` KEEPS execute — staff call this
-- straight from the dashboard as that role.
revoke execute on function approve_officer_request(bigint) from public, anon;
grant execute on function approve_officer_request(bigint) to authenticated;

create function reject_officer_request(req_id bigint) returns void
language plpgsql security definer
set search_path = public as $$
begin
  if not is_admin() then
    raise exception 'not authorized';
  end if;

  update public.officer_requests
    set status = 'rejected', decided_by = auth.uid(), decided_at = now()
    where id = req_id and status = 'pending';
  if not found then
    raise exception 'no pending request %', req_id;
  end if;
end; $$;
revoke execute on function reject_officer_request(bigint) from public, anon;
grant execute on function reject_officer_request(bigint) to authenticated;

-- Public-safe aggregate (no node internals). Readable by anyone authenticated.
-- Deliberately security_invoker = false (the default): this view must bypass
-- events' staff-only RLS so public/anon users can see the day+count aggregate
-- on the Stay Safe page. The exposure is bounded by the view's own column
-- list (day, count only) — no species, location, or node detail leaks through.
-- Do not "fix" the Supabase Advisor's Security Definer View warning here by
-- setting security_invoker = true; that would make public users see zero rows.
create view public_area_risk with (security_invoker = false) as
  select date_trunc('day', ts) as day, count(*) as detections
  from events where priority = 'high' group by 1 order by 1 desc;
grant select on public_area_risk to authenticated, anon;

-- ---------- Demo Mode (Phase 4c) ----------
-- One-click scenarios that make the full system act for a judge with no live
-- hardware present. Each scenario writes real, tagged rows through the
-- SECURITY DEFINER RPC below, so it flows through the true realtime pipeline
-- onto Overview / Alerts rather than being a canned client-side animation.

-- A scenario mutates node status so the map visibly reacts. Reset must restore
-- the node's *true* prior state, not guess: S7-04 is legitimately 'maintenance'
-- in the field seed, so a blanket "set everything online" would silently corrupt
-- real fleet state. Capture the row before the first demo write touches it.
create table demo_node_snapshot (
  node_id     text primary key references nodes on delete cascade,
  status      node_status,
  battery_pct int,
  solar_w     real,
  last_seen   timestamptz,
  captured_at timestamptz not null default now()
);
alter table demo_node_snapshot enable row level security;
create policy dns_staff_read on demo_node_snapshot for select using (is_staff());
-- No insert/update/delete policy on purpose: only the SECURITY DEFINER functions
-- below ever write here, and they run as the function owner.

-- Snapshot-then-mutate, used by every scenario step that touches a node. Internal
-- to the demo RPCs; deliberately not granted to authenticated. The is_staff()
-- check below is a second, independent barrier on top of the revoke — a Day 3
-- adversarial pass found the revoke alone had drifted out of sync with the live
-- project at least once, so this function no longer depends on the grant being
-- correct as its only defense.
create function demo_touch_node(p_node text, p_status node_status)
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
-- Internal only: invoked by the SECURITY DEFINER scenarios below, which run as the
-- function owner, so no role needs a grant here. `anon` was missing from this list
-- and did still hold EXECUTE on the live database (found 12 Jul) — it is included now.
revoke execute on function demo_touch_node(text, node_status) from public, anon, authenticated;

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
-- safety barrier, not an oversight. send-alert fans SMS out to officers and to
-- opted-in residents within 3 km of any high-priority event, and the
-- public_area_risk view (public Stay Safe page) counts only high-priority rows.
-- Keeping demo events at 'normal' means a scenario can never page a village or
-- move the public risk figure, independently of send-alert's own demo guard.
--
-- Stepping is driven by the client between calls rather than pg_sleep: a
-- SECURITY DEFINER function must not hold a connection open to pace an animation.
-- Each step is a real INSERT, so it reaches the dashboard over the same realtime
-- channel a live node would use.
create function run_demo_scenario(p_scenario text, p_step int default 1)
returns jsonb language plpgsql security definer
set search_path = public as $$
declare
  v_total    int;
  v_log      jsonb := '[]'::jsonb;
  v_event_id bigint;
  v_hm       text := to_char(now() at time zone 'Asia/Kolkata', 'HH24:MI');
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
revoke execute on function run_demo_scenario(text, int) from public, anon;
grant execute on function run_demo_scenario(text, int) to authenticated;

-- Clears only demo-tagged rows and puts every touched node back to the exact
-- state it held before the first scenario ran. Demo `alerts` rows need no
-- predicate of their own: alerts.event_id cascades on delete from events.
create function reset_demo_data() returns jsonb
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
revoke execute on function reset_demo_data() from public, anon;
grant execute on function reset_demo_data() to authenticated;

-- Realtime for the dashboard. `maintenance` joins so the Fleet queue updates live.
alter publication supabase_realtime add table nodes, events, alerts, health, maintenance;

-- ---------- Admin panel: user / role management (migration 0003) ----------
-- Deliberately NOT firmware/OTA: no real firmware pipeline exists on device/mcu
-- yet, and mocked OTA data would undercut this system's credibility. Every action
-- is authorised server-side by is_admin() — hiding a button in React is not access
-- control.

-- ---------- list ----------
create or replace function admin_list_users()
returns table (
  id uuid,
  email text,
  role user_role,
  full_name text,
  created_at timestamptz,
  deactivated boolean,
  is_self boolean
)
language sql security definer set search_path = public as $$
  select
    p.id,
    u.email::text,
    p.role,
    p.full_name,
    p.created_at,
    (u.banned_until is not null and u.banned_until > now()) as deactivated,
    (p.id = auth.uid()) as is_self
  from public.profiles p
  join auth.users u on u.id = p.id
  where is_admin()          -- no rows at all for a non-admin caller
  order by
    case p.role when 'admin' then 0 when 'officer' then 1 else 2 end,
    u.email;
$$;

-- ---------- change role ----------
create or replace function admin_set_role(p_user uuid, p_role user_role)
returns void language plpgsql security definer set search_path = public as $$
declare
  v_admins int;
begin
  if not is_admin() then
    raise exception 'not authorized';
  end if;

  -- An admin must not be able to lock themselves out of their own project.
  if p_user = auth.uid() then
    raise exception 'you cannot change your own role';
  end if;

  -- Never leave the project with no admin. Counted before the change, so demoting
  -- the only other admin while you are still one is fine; demoting the last one is not.
  if p_role <> 'admin' then
    select count(*) into v_admins from public.profiles where role = 'admin';
    if v_admins <= 1 and (select role from public.profiles where id = p_user) = 'admin' then
      raise exception 'cannot demote the last remaining admin';
    end if;
  end if;

  update public.profiles set role = p_role where id = p_user;
  if not found then
    raise exception 'no such user';
  end if;
end; $$;

-- ---------- deactivate / reactivate ----------
create or replace function admin_set_deactivated(p_user uuid, p_deactivated boolean)
returns void language plpgsql security definer set search_path = public as $$
declare
  v_admins int;
begin
  if not is_admin() then
    raise exception 'not authorized';
  end if;

  if p_user = auth.uid() then
    raise exception 'you cannot deactivate your own account';
  end if;

  if p_deactivated then
    select count(*) into v_admins
      from public.profiles pr
      join auth.users au on au.id = pr.id
      where pr.role = 'admin' and (au.banned_until is null or au.banned_until <= now());
    if v_admins <= 1 and (select role from public.profiles where id = p_user) = 'admin' then
      raise exception 'cannot deactivate the last active admin';
    end if;
  end if;

  -- GoTrue refuses to issue a session while banned_until is in the future, so this
  -- blocks sign-in at the auth layer rather than only in the UI.
  update auth.users
     set banned_until = case when p_deactivated then 'infinity'::timestamptz else null end
   where id = p_user;
  if not found then
    raise exception 'no such user';
  end if;
end; $$;

-- Same grant posture as the other definer RPCs (see 0002): anon and PUBLIC are
-- revoked so an anonymous caller is stopped at the grant; `authenticated` keeps
-- EXECUTE because admins call these from the dashboard as that role, and the
-- is_admin() guard inside each one is what actually authorises the action.
revoke execute on function admin_list_users() from public, anon;
revoke execute on function admin_set_role(uuid, user_role) from public, anon;
revoke execute on function admin_set_deactivated(uuid, boolean) from public, anon;

grant execute on function admin_list_users() to authenticated;
grant execute on function admin_set_role(uuid, user_role) to authenticated;
grant execute on function admin_set_deactivated(uuid, boolean) to authenticated;
