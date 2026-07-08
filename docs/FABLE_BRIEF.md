# EleTect X — Brief for Fable 5 (build the web app end-to-end)

**How to use this:** open **Design / Fable 5** in the Claude desktop app, paste the "Creative brief" below, and attach this whole file as the **factual content pack**. Give Fable 5 freedom on design, layout, motion, and copy polish — but keep all *facts* accurate to this pack (don't invent numbers). Tell it to **do wonders**, then **self-verify with screenshots and test every flow**.

---

## Creative brief (paste this)
> Build a **stunning, production-quality, startup-grade** web app for **EleTect X**, a solar-powered edge-AI system that protects Kerala's forests and farms from human–elephant conflict. You have full creative freedom over design, layout, animation, and copywriting — make it look like a funded climate-tech startup. Use the factual content pack provided (don't invent stats). Stack: **React + Tailwind + shadcn/ui**, structured to wire to **Supabase** (auth + Postgres + realtime) and deploy on **Vercel**. Palette: deep forest green + charcoal + warm accent; cinematic hero, subtle motion, mobile-first, fast, accessible. Use free imagery: **Unsplash/Pexels** (Asian elephants, Kerala forests, rangers, night forest, solar/tech) and AI-generated hero art where useful; mood reference: the shared Pinterest board. Two surfaces in one product:
> **(A) Public marketing site** and **(B) a role-based dashboard**. Build it, then **screenshot every page (desktop + mobile), click through all flows and all three logins, fix anything broken, and re-verify until perfect. Then deploy and give me the link.** Do wonders.

## Roles (simplified — 3)
- **Admin** — full control: node registration/management, **OTA updates**, user management, thresholds/config, audit log.
- **Forest Officer** (rangers + officers merged) — monitor everything: live map, alerts, node health, incident replay, analytics; **acknowledge** alerts.
- **Public** — basic info + **opt-in alerts**: can sign up, and *optionally* add **phone number + location** and **enable alerts** to receive an SMS when an elephant is detected near them. Public sees only safe, basic information.

Auth: email + password (Supabase Auth). Public alert delivery is **outbound SMS** to opted-in numbers (not used for login).

---

## FACTUAL CONTENT PACK (use verbatim facts; polish the wording freely)

**Name / tagline:** EleTect X — *Protecting farms, forests, and the future.*
**One-liner:** An autonomous, solar-powered edge-AI node that detects elephants early through the ground, confirms with night vision, deters them safely, and alerts people — day and night, without the internet.

**The problem (Kerala human–elephant conflict):**
- Elephants raid crops mostly at night (**>70% of raids are nocturnal**), when people can't see them coming.
- Kerala has lost hundreds of wild elephants to conflict in recent years, and people die in surprise night encounters and vehicle/train collisions.
- Existing tools fail: PIR alarms fire on everything and elephants **habituate** to fixed sirens; electric/rail fences are bypassed or cost lakhs per km and harm other wildlife.

**How it works (the loop):** Sense (seismic + audio) → Confirm (night-vision AI) → Decide → **Deter** (adaptive light + sound that never repeats) → **Observe** the outcome → **Learn** → **Coordinate** with neighbouring nodes to steer the herd safely back to the forest — never toward a village.

**What makes it different (say these):**
- **Seismic-first:** feels elephant footsteps through the ground — works in rain, fog, and pitch darkness, unlike cameras alone.
- **Adaptive, non-habituating deterrence** that measures whether the elephant actually left, and learns what works.
- **Safe herding corridors:** a network of nodes opens an escape route to the forest instead of trapping or panicking the animal.
- **Ultra-low power:** solar + battery, weeks of autonomy, fully offline (no cloud needed to act).
- **One platform, many jobs:** the same node also warns drivers of crossings (road/rail safety), flags wildfire danger, and can detect gunshots/chainsaws (anti-poaching).
- **Low cost & scalable:** roughly a tenth of the cost of fencing, designed for thousands of nodes.
- **Field-validated:** deployed for real testing with the Kerala Forest Department (Kothamangalam).

**Core technology:** Arduino UNO Q dual-brain edge computer (real-time + Linux AI), Sony IMX462 day/night camera with 940 nm IR, a geophone seismic sensor, LoRa mesh, solar power, and explainable on-device AI.

**Use cases / impact:** crop protection · human safety (early warning + alerts) · elephant safety (humane deterrence + safe corridors) · road & rail collision prevention · wildfire early-warning · anti-poaching acoustic detection · long-term wildlife-behaviour research data for scientists and the Forest Department.

**Achievements / milestones (fill/confirm real ones):** Arduino Physical AI Challenge India 2026 entrant · Hackster "Invent the Future with Arduino UNO Q" entrant · Kerala Forest Department field-deployment approval · builds on the earlier **EleTect 1.5** smart road-signage project.

**Team:** Abhinav Krishna (and team). *(Add member names/photos/roles.)*
**Contact:** a simple contact form + email; "For Forest Departments & partners."

## Dashboard content (Officer/Admin)
Live **map** of nodes (colour by status/battery/alert) using Leaflet + OpenStreetMap · **Alerts feed** (species, confidence %, thumbnail, direction, time, Acknowledge) · **Node detail** (battery, solar, firmware, last-seen, sensor health) · **Incident replay** (timeline + media) · **Analytics** (events by time/species/weather, hotspot heatmap, fire-danger map) with Recharts · **Maintenance** queue (predictive) · **Fleet health** · **OTA** (admin) · **Settings**. Ranger/officer view must be extremely simple, big tap targets, offline-capable (PWA). Populate with realistic placeholder data so every screen looks alive.

## Public page (logged-in Public)
A friendly "Stay Safe" page: current risk level in their area, how alerts work, a toggle to **enable SMS alerts**, and fields to add **phone number + location** (with consent copy). Only safe, basic info — no node internals.

## Tech + verification instructions for Fable 5
- React + Vite + Tailwind + shadcn/ui; Leaflet (OSM), Recharts; PWA; clean structure for Supabase wiring.
- Realistic seed/placeholder data everywhere.
- **After building:** screenshot every page (desktop + mobile), test all navigation + all three role logins + the alert opt-in flow, fix issues, re-verify, then **deploy and return the live link.**
