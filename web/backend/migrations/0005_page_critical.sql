-- 0005 — no-retreat ('critical') events count as paging.
--
-- web/ingest writes priority = 'critical' when a node sets the no-retreat flag
-- (ADR 0034): it fired its top tier and the animal stayed. send-alert now fans
-- 'critical' out like 'high' (isPaging in functions/send-alert/message.ts);
-- this brings the public Stay Safe aggregate in line, so the one alert that
-- means "send a person" also moves the public risk figure.
--
-- Same view, same columns, same security_invoker = false as schema.sql - see
-- the comment there before changing either.

create or replace view public_area_risk with (security_invoker = false) as
  select date_trunc('day', ts) as day, count(*) as detections
  from events where priority in ('high', 'critical') group by 1 order by 1 desc;
grant select on public_area_risk to authenticated, anon;
