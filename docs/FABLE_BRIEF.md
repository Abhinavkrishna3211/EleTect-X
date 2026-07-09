# EleTect X — Brief for Claude Fable 5 (build the web platform)

**How to use:** open **Claude Design** → click **Prototype** (or blank project) → Model = **Claude Fable 5** → paste the "Creative brief" below and this whole file as the content pack. Give it full creative freedom on design/layout/motion/copy, but keep all *facts* accurate to this pack. Tell it to **do wonders**, then **self-verify (screenshots + test every flow)** and deploy.

> **Positioning:** EleTect is a **platform / ecosystem**, not a single gadget. Present it like a funded conservation-tech company. **Do NOT list internal hardware, chips, or part numbers anywhere** — market *capabilities, outcomes, and why we're better*. (Deep tech lives in private docs, not the public site.)

---

## Creative brief (paste this)

> Build a **stunning, production-quality web platform** for **EleTect** — an AI-powered wildlife-protection ecosystem for India's forests and farms. Full creative freedom on design, motion, and copy; make it look like a funded climate/conservation-tech startup (cinematic, premium, **deep forest green + charcoal + warm accent**, subtle motion, mobile-first, fast, accessible). Use the factual content pack (don't invent stats; don't reveal internal hardware). Stack: **React + Tailwind + shadcn/ui**, structured to wire to **Supabase** (auth + Postgres + realtime) and deploy on **Vercel**. Free imagery: **Unsplash/Pexels** (Asian elephants, Kerala forests, rangers, night forest, farmland) + AI-generated hero art; mood: the shared Pinterest board. It is ONE product with a public site **and** a role-based dashboard. Build it, then **screenshot every page (desktop + mobile), test all flows and all three logins + the Demo Mode, fix anything broken, re-verify, deploy, and return the live link.** Do wonders.

## Site map (public) + app

`Home · Technology · Solutions · Deployments · Research · About · Contact · [ Dashboard login ]`

- **Solutions (the platform story — one system, many jobs):** Elephant-Conflict Mitigation · Road Safety · Railway Safety · Anti-Poaching · Wildfire Early-Warning · Wildlife Analytics. Each: the problem → how EleTect solves it → why it's better. This makes it read as a platform, not a project.

## Roles (3)

- **Admin** — full control incl. node management + over-the-air updates + user management + config + audit log.
- **Forest Officer** (rangers + officers merged) — monitor everything, acknowledge alerts, run reports.
- **Public** — safe basic info + **opt-in alerts**: sign up, optionally add **phone + location**, toggle **SMS alerts** for detections near them. No internal/system details shown.

Auth: email + password (Supabase). Alerts are outbound only.

---

## FACTUAL CONTENT PACK

### Positioning

**EleTect — Protecting farms, forests, and the future.**
One-liner: *An autonomous, solar-powered AI system that detects wildlife early, warns people instantly, and deters animals safely — day and night, even without the internet.*

### The problem — Human–Wildlife Conflict in India (use these, they're impactful)

> *(Government/published figures — confirm exact citations before publishing; present as ranges where noted.)*

- **~500 people are killed every year in India** in human–elephant conflict (~2,300+ deaths over 2019–2024). Most fatal encounters happen **at night**, when people never see the animal coming.
- **~100 elephants die each year** in India from conflict — electrocution, train/vehicle collisions, poisoning, and retaliation.
- **Kerala declared human–wildlife conflict a state-specific disaster in 2024** — the scale is now officially a crisis.
- In Kerala's conflict hotspots, surveys found **56.6% of households lost more than half their seasonal crop**, and **26.7% suffered total crop failure**.
- Beyond crops: **house and property damage, livestock loss, abandoned farmland, lost school/work days, and deep economic and psychological toll** on farming families — and mounting losses to state agriculture and compensation budgets.
- Regional scale (context): Sri Lanka alone recorded **488 elephant and 187 human deaths in a single year (2023)**.
- **Existing tools fail:** motion alarms trigger on everything and animals **learn to ignore** fixed sirens; electric/rail fences are bypassed or cost lakhs per kilometre and harm other wildlife. The result is a cycle of damage, danger, and retaliation.

> Design idea: a bold **"By the numbers" statistics band** on Home (animated counters: ~500 human deaths/yr, ~100 elephant deaths/yr, 56.6% households losing >½ crop, etc.) — sourced, sober, powerful.

### The solution — how EleTect works (capabilities, not hardware)

A network of solar nodes that **sense → confirm → decide → deter → observe → learn → coordinate**:

- **Senses early through the ground and sound** — works in rain, fog, and total darkness, before the animal is even visible.
- **Confirms with night-capable AI vision** to eliminate false alarms.
- **Deters safely and adaptively** — light + sound patterns that **change every time and never repeat**, so animals don't get used to them; it **checks whether the animal actually left** and learns what works.
- **Coordinates across nodes** to open a safe path back to the forest — steering the herd **away from villages**, never trapping or panicking it.
- **Warns people instantly** — officers and opted-in residents get alerts in seconds.
- **Runs fully offline** on solar power; no internet needed to act.

### Why EleTect is better (comparison-worthy)

Species-specific and **low false alarms** · **works day, night, fog, rain** · **adaptive, non-habituating** deterrence · **networked** (coordinated, not isolated) · **instant human early-warning** · **~1/10th the cost of fencing** and scalable to thousands of nodes · **field-tested with the Kerala Forest Department**. (A clean comparison table vs traditional alarms / fences / camera-traps works well.)

### Use cases / impact

Crop protection · human safety (early warning + alerts) · humane animal safety (safe corridors) · road & rail collision prevention · wildfire early-warning · anti-poaching acoustic detection · long-term wildlife-behaviour analytics for scientists and the Forest Department.

### Achievements / recognition (only these for now)

- **IEEE IAS CMD Humanitarian Award 2025**
- **Amarnath Raja Humanitarian Technology Award 2025**
- Field deployment in progress with the **Kerala Forest Department**.

*(Keep the section; add contest results later once announced.)*

### Team

**Abhinav Krishna N** · **Amritha M**. *(Add roles/photos.)*

### Contact

Simple form + email; headline "For Forest Departments, researchers & partners."

---

## DASHBOARD (Officer / Admin) — make it feel like a real conservation ops platform

Keep the ranger view **extremely simple**; make the analytics feel **industrial**. Include (good ideas adopted):

- **Live map** — nodes as status-coloured pins (Leaflet + OpenStreetMap); click a node → detail.
- **Explainable-AI decision card** (this is the "Physical AI" wow) — per event, show the *reasoning by sensing modality*, then the decision:
  `Ground vibration ✔ heavy footstep · Audio ✔ elephant rumble · Vision ✔ elephant confirmed → Decision: deterrent activated · Outcome: herd retreated`
  *(Use these three modalities only — ground/seismic, audio, vision. There is no thermal sensor; do not show one.)*
- **Confidence radar** — a small radar chart over **Vision / Audio / Seismic** plus the fused overall %. (Not just a number.)
- **Incident Replay (time machine)** — a **timeline slider** to scrub an event minute-by-minute: herd position on the map, deterrent activating, alerts sent. (Tesla-Sentry feel — great for judges.)
- **Network Intelligence** — visualise the **safe-herding corridor**: Node → Node → … → Forest exit, showing which nodes activated and how the herd was steered home. (Shows *shared* intelligence, not a single node.)
- **AI Learning** — bar view of **deterrent effectiveness that improves over time** (e.g., bee-buzz 92%, tiger-growl, strobe pattern B, etc.) so you can *see* the node learning what works per site. (Values illustrative.)
- **Fleet Health (SCADA-style)** — big status tiles: *Healthy · Needs cleaning · Needs battery · Offline*, plus overall fleet %. Predictive maintenance from solar/battery trends.
- **Node detail ("digital twin")** — operational health only: battery, solar input, signal/last-seen, sensor health, uptime, last detection. *(Operational metrics only — no CPU/memory/chip internals.)*
- **Deployment Planner** — draw a forest/farm boundary on a map → the tool estimates **number of nodes, coverage, and likely blind spots** (great sales/planning tool for Forest Depts).
- **Demo Mode (very important — judges won't wait)** — one-click replay scenarios that animate end-to-end: *Night Elephant · Road Crossing · Wildfire Risk · Poaching Sound · Sensor Degraded · Heavy Rain.*
- **Alerts feed** — species, confidence, thumbnail, direction, time, **Acknowledge**; **Settings**; **OTA status** (admin).

**Mobile-first officer rule (state it to Fable):** *every ranger workflow must be doable one-thumb, standing in a forest at night, wearing gloves.* Big targets, high contrast, offline-capable (PWA).

## Public "Stay Safe" page

Current area risk level, how alerts work, a toggle to **enable SMS alerts**, and fields for **phone + location** with clear consent copy. Safe, basic info only.

## Alerts / notifications architecture (build generic)

Build a **Notification Service** with one interface and **pluggable channels chosen by config** — **SMS (Fast2SMS/MSG91/Twilio), WhatsApp, Email, Push.** Don't hard-wire SMS into app logic. *(India note: SMS to Indian numbers needs TRAI DLT registration — start it early; use Email/WhatsApp as the demo fallback until DLT clears.)*

## Build & verification instructions for Fable 5

React + Vite + Tailwind + shadcn/ui; Leaflet (OSM); Recharts; PWA; clean structure for Supabase wiring; realistic seed data everywhere so every screen looks alive. **After building: screenshot every page (desktop + mobile), test all navigation, all three logins, the alert opt-in, and Demo Mode; fix issues; re-verify; deploy; return the link.** Make it genuinely beautiful — iterate until it's striking.
