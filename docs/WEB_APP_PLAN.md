# EleTect X — Web App & Fable Build Plan

Goal: a **startup-grade** web presence — a marketing site that showcases the project + use cases, and a **dead-simple, powerful dashboard** for Forest officers/rangers (monitor nodes, get alerts, replay incidents), with **admin login** and **alerts to locals**. All on **free** resources; paid only if truly needed. Everything is documented as we build for the Hackster write-up at the end.

---

## 1. Which tool where (this answers "Cowork vs Claude Code vs Fable")
| Tool | Use it for | Why |
|---|---|---|
| **Fable** (trial → **expires 12 Jul**) | **Generate the whole frontend from scratch → self-verify (screenshots/tests) → host a first version.** Marketing site + dashboard UI. | It's an agentic web-app builder — fastest way to a polished, cohesive UI. Use its **own web interface**, not Cowork/Claude Code. Burn the trial on *generation*. |
| **Claude Cowork (here)** | Planning, the **Fable master prompt** (below), marketing copy, docs, reviewing Fable's output. | Best for thinking/writing, not for hosting a live app. |
| **Claude Code (VS Code)** | **Wire the exported frontend to Supabase**, backend/edge functions, on-device code, tests, repo integration, Vercel deploy. | The real engineering + integration lives in the repo. |
| **Supabase** (free) | Auth + Postgres + realtime + storage + edge functions (the backend). | Production-grade backend with almost no code; free tier is plenty for the pilot. |
| **Vercel** (free) | Host the React app (dashboard + site) with CI previews. | Instant professional hosting; free hobby tier. |

**Flow:** Cowork writes the brief → **Fable generates + hosts + self-tests** (before 12 Jul) → export code into `web/frontend/` → **Claude Code** wires Supabase + alerts + deploys to Vercel. Keep it free end-to-end.

## 2. Free resource stack (no paid unless noted)
- **Frontend build:** Fable (trial) → **export to `web/frontend/`**.
- **Hosting:** Vercel (free) — `eletectx.vercel.app`. *(Custom domain = optional paid later.)*
- **Backend/DB/Auth/Storage/Realtime:** Supabase (free tier).
- **Map:** Leaflet + OpenStreetMap tiles (free, no API key). *(Avoid Mapbox unless you need its styling.)*
- **Alerts to locals/rangers:** **Telegram Bot API (100% free, instant)** as primary; **WhatsApp Cloud API (Meta) free tier** for officers; email via Supabase/Resend free tier. SMS (Twilio) only if a specific ranger has no smartphone — trial credits, paid at scale.
- **Charts:** Recharts (free). **UI kit:** Tailwind + shadcn/ui (free).

## 3. Web app specification

### Public marketing site (impress + explain)
Home (hero: "Protecting farms, forests, and the future" + one-line pitch + CTA) · The Problem (Kerala HEC stats) · How It Works (sense → confirm → deter → learn → coordinate; the safe-herding corridor) · Technology / Product (UNO Q node, seismic-primary, adaptive deterrence, extensible pods) · Use Cases & Impact (HEC, road/rail-collision warning via EleTect 1.5, wildfire risk, anti-poaching, research) · Field Deployment (Kerala Forest Dept) · Achievements / Milestones · Team / About · Contact. Design: modern, high-end, **dark forest palette**, subtle motion, mobile-first, fast.

### Auth + roles (RBAC)
- **Admin** — full: node registration, user/role management, OTA push, thresholds/config, audit log.
- **Forest Officer** — fleet view, analytics, alerts, incident replay, reports.
- **Ranger** — simplest view: map + alerts + acknowledge + node status. Big tap targets, offline-friendly (PWA).

### Dashboard features
Live **map** (nodes, colour = status/battery/alert) · **Alerts feed** (confirmed events: species, confidence, thumbnail, direction, time, **Acknowledge**) · **Node detail** (battery, solar, firmware, last-seen, sensor health) · **Event replay** (timeline + media) · **Analytics** (events by time/species/weather; **hotspot heatmap**; **fire-danger map**) · **Maintenance queue** (predictive: solar/battery trends) · **Fleet health** · **OTA status** · **Settings**.

### Alerts to locals (life-safety)
On a confirmed high-priority event: fan-out via **Telegram/WhatsApp** to (1) control room + rapid-response team, (2) opted-in nearby volunteers/villagers; **acknowledge**; **escalate** if unacknowledged in N minutes; dedupe by event ID. Implemented as a **Supabase edge function** triggered on new `events` rows.

### Data model (Supabase tables)
`users`(role) · `nodes`(id, gps, status, firmware, battery, solar, last_seen) · `events`(node_id, ts, species, confidence, direction, media_url, action, outcome) · `alerts`(event_id, channel, recipients, acked_by, acked_at) · `health`(node_id, ts, metrics) · `maintenance`(node_id, flag, reason). Row-Level-Security per role.

## 4. Fable — step-by-step (from scratch to hosted)
1. **Before 12 Jul:** sign in to Fable; confirm free-tier limits + **how it exports** (GitHub connect or code download) and **hosting**.
2. **Paste the master prompt** (§5) — one cohesive product (site + dashboard), design system, all pages, realistic placeholder data, the 3 roles.
3. **Tell Fable to self-verify:** *"After building, take a screenshot of every page (desktop + mobile), click through all navigation and the login/role flows, list anything broken, and fix it. Re-screenshot until all pages render correctly and are responsive."*
4. **Iterate per page** with focused prompts (hero, dashboard map, alerts, analytics) until it looks funded-startup-grade.
5. **Host the Fable version** → save the share link (great for the contest demo + Hackster).
6. **Export the code → `web/frontend/`** (GitHub connect if available; else download + copy in), commit.
7. **In Claude Code (VS Code):** create the Supabase project + tables + RLS; replace placeholder data with the Supabase client; add the alert edge function (Telegram/WhatsApp); **deploy to Vercel**.
8. **Seed demo data** so the live dashboard looks alive for judges even before field data arrives.

## 5. Fable master prompt (paste this, then let it run free)
> Build a professional, production-quality web application called **EleTect X** — a solar-powered AI wildlife-protection system for Kerala forests. Two parts in one cohesive product with a shared design system (modern, premium, **dark forest green + charcoal**, subtle motion, mobile-first, fast, accessible):
>
> **A) Public marketing site** — pages: Home (hero + pitch + CTA), The Problem, How It Works, Technology, Use Cases & Impact (human-elephant conflict, road-collision warning, wildfire risk, anti-poaching, research), Field Deployment, Achievements, About/Team, Contact (form). Make it look like a funded climate-tech startup.
>
> **B) Ranger/Officer dashboard** (behind login, roles: Admin, Officer, Ranger): live map of nodes (status colours) using Leaflet + OpenStreetMap; alerts feed (species, confidence, thumbnail, direction, time, Acknowledge button); node detail (battery, solar, firmware, last-seen, sensor health); incident replay (timeline + media); analytics (events by time/species/weather, hotspot heatmap, fire-danger map) with Recharts; maintenance queue; fleet health; OTA status; settings. Ranger view must be extremely simple with large tap targets and work offline (PWA).
>
> Use React + Tailwind + shadcn/ui. Include realistic placeholder data so every screen looks alive. Structure the code cleanly for later wiring to a Supabase backend (auth, Postgres, realtime). After building, **take screenshots of every page on desktop and mobile, click through all flows, fix anything broken, and re-verify until everything works.** Then deploy/host it and give me the link.

## 6. Documentation for Hackster (keep on track, assemble at end)
As you build, drop artifacts into the repo continuously: screenshots → `docs/` , decisions → `docs/decisions/` (ADRs), field data → `deployment/field-logs/`, build photos/notes → `deployment/`. **At the end**, assemble the Hackster story from these (documentation is 30% of the Hackster score) — the trail makes the write-up fast and credible. Don't leave docs to the last day; capture as you go.

## 7. Open question (confirm so steps are exact)
How do you access **Fable** — (a) the fable.app agentic builder, (b) the **Claude Fable 5** model via Claude Code/Cowork, or (c) a Lovable/Bolt-style builder? The plan above works for any agentic builder; knowing which one lets me give exact export/hosting clicks.
