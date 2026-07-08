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
  created_at   timestamptz not null default now()
);
create index on events (node_id, ts desc);

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

-- 6. Maintenance queue (predictive)
create table maintenance (
  id       bigint generated always as identity primary key,
  node_id  text references nodes on delete cascade,
  flag     text, reason text, resolved boolean default false,
  created_at timestamptz not null default now()
);

-- Auto-create a profile on signup (default role: public)
create function handle_new_user() returns trigger language plpgsql security definer as $$
begin
  insert into profiles (id, full_name) values (new.id, new.raw_user_meta_data->>'full_name');
  return new;
end; $$;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function handle_new_user();

-- Helper: is the current user an officer or admin?
create function is_staff() returns boolean language sql stable as $$
  select exists(select 1 from profiles p where p.id = auth.uid() and p.role in ('admin','officer'));
$$;
create function is_admin() returns boolean language sql stable as $$
  select exists(select 1 from profiles p where p.id = auth.uid() and p.role = 'admin');
$$;

-- ---------- RLS ----------
alter table profiles    enable row level security;
alter table nodes       enable row level security;
alter table events      enable row level security;
alter table alerts      enable row level security;
alter table health      enable row level security;
alter table maintenance enable row level security;

-- Profiles: users manage their own; staff can read all; admin can write all
create policy p_self_rw on profiles for all using (id = auth.uid()) with check (id = auth.uid());
create policy p_staff_read on profiles for select using (is_staff());
create policy p_admin_all on profiles for all using (is_admin()) with check (is_admin());

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

-- Public-safe aggregate (no node internals). Readable by anyone authenticated.
create view public_area_risk as
  select date_trunc('day', ts) as day, count(*) as detections
  from events where priority = 'high' group by 1 order by 1 desc;
grant select on public_area_risk to authenticated, anon;

-- Realtime for the dashboard
alter publication supabase_realtime add table nodes, events, alerts, health;
