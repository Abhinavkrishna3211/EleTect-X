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

-- Realtime for the dashboard
alter publication supabase_realtime add table nodes, events, alerts, health;
