# EleTect X — Build brief for Claude Code (web/frontend + backend wiring)

Read in this order before writing code: `/CONTEXT.md` (project source of truth) → `/CLAUDE.md` (hard rules — no AI references anywhere, Conventional Commits, small focused commits) → `docs/WEBAPP_EDITS_AND_PLAN.md` (the fix/feature punch list) → `docs/design-reference/` (the visual spec, exported from Claude Design).

## What's already here
- `docs/design-reference/EleTect Platform.dc.html` + `SectorMap.dc.html` — the finished design, pixel spec. Match it, don't reinterpret it.
- `docs/design-reference/assets/` — logo, product imagery already used in the design.
- `web/backend/schema.sql` — Supabase schema + RLS already written (profiles/nodes/events/alerts/health/maintenance, roles admin/officer/public). Use as-is unless a gap surfaces.
- `web/frontend/` — empty, this is what you're building into.

## Known gaps vs. the design (from WEBAPP_EDITS_AND_PLAN.md — confirm still outstanding, the design may have moved on since export)
Asian-elephant imagery throughout (not African), logo wired into nav/footer/login/dashboard, no em-dashes anywhere, Sign-up + officer-approval-queue flow, forgot-password, Malayalam/English toggle, Solutions section restructure (crop-raid lead, Other Wildlife, Anti-Poaching & Illegal Logging rename, Coordinated Intelligence block), per-product images for EleTect X / EleTect Signage.

## Build order (small, focused commits per step — per CLAUDE.md)
1. Scaffold: Vite + React + Tailwind + shadcn/ui in `web/frontend`. Routing for public site + `/dashboard`.
2. Public marketing pages matching the design, pixel-for-pixel: Home, Technology, Solutions, Deployments, Research, About, Contact, Stay Safe.
3. Auth: Supabase email+password, signup (role=public default), officer request-access → pending → admin approval queue, forgot-password. Wire `handle_new_user` trigger already in schema.
4. Dashboard shell + RBAC routing (admin / officer / public views).
5. Dashboard modules: live map (Leaflet+OSM), alerts feed, explainable-AI decision card, confidence radar, incident replay, corridor view, learning view, fleet health tiles, node detail, deployment planner, Demo Mode (6 scenarios).
6. Notification service: pluggable interface, Email + WhatsApp channels first (SMS needs India DLT registration — stub behind a flag, don't block on it).
7. Seed realistic demo data across all tables so every screen looks alive.
8. Deploy to Vercel; confirm env vars / Supabase keys are not committed.

## Verification (do this before calling any step done)
Screenshot every page, desktop + mobile. Test all three role logins + Demo Mode. Fix and re-verify. This mirrors what was already done once in Claude Design — the production app needs the same bar.

## Reminders
- No hardware/chip/part-number references in any public-facing copy (per CONTEXT.md positioning rule) — that constraint applies to the frontend copy too, not just marketing docs.
- Repo-wide: no AI/assistant references in code, comments, commits, or docs.
