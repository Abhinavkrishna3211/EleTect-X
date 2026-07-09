# EleTect — Web App: Edits + Master Plan (after Fable v1)

Fable v1 is excellent and on-brand (explainable-AI card, confidence radar, SCADA fleet tiles, "locations withheld" touch). Below: the fixes, the auth/officer flow, added functionality, hardware mapping, and the build path. **Fable's output is a prototype (`.dc.html`), not a React project** — so we finish the *design* in Fable, then **rebuild the production app in `web/frontend` (React + Supabase) with Claude Code, matching the Fable design pixel-for-pixel**. That gives real auth, signup, officer verification, and live hardware data.

## A. Design / content fixes (do in Fable, then carry to the React build)

1. **Asian elephant, not African.** Every elephant image shows an African elephant (huge ears). Replace with **Asian elephant** photos (smaller ears, twin-domed head, often a single tusker; Western-Ghats/Kerala context). Hero + Solutions + alert thumbnails.
2. **Fix weak/irrelevant images.** Anti-Poaching uses a galaxy/night-sky photo → use night-forest / ranger patrol / camera-trap imagery. Make road/rail/wildfire images **India-relevant** (Indian forest-edge roads, Indian railway through forest, Western-Ghats mist). Use high-quality Unsplash/Pexels or AI-generated; reject any generic stock that doesn't fit.
3. **Add the EleTect logo.** Upload `eletect logo.avif` and use it in the nav, footer, login, and dashboard header (replace the placeholder mark). Keep wordmark spelling consistent: **EleTect** (platform), **EleTect X** (the node), **EleTect Ops** (dashboard).
4. **Remove all em-dashes (—).** Replace with commas, periods, or colons throughout for a clean, professional tone.
5. **Product photos.** Give each product its own image: **EleTect X** node (render/prototype photo), **EleTect Signage** (the EleTect 1.5 road-warning unit), and placeholders for future products. Use real prototype photos as they're taken.
6. **Consistency polish:** unify heading style, spacing, and card treatments across pages; ensure mobile screenshots are checked for every page.

## B. Solutions / use-cases (enrich — you asked for these)

Keep the 6-card layout but make the platform story explicit:

- **Elephant-Conflict Mitigation** → lead with **crop-raid prevention** (paddy/plantation), plus human safety + safe corridors.
- **Other Wildlife** (new or a sub-section) → **wild boar, gaur, deer, monkey** deterrence (species-specific).
- **Anti-Poaching & Illegal Logging** → gunshot **and chainsaw/tree-cutting** acoustic detection, silent ranger alerts (rename the card to include logging).
- **Road Safety**, **Railway Safety**, **Wildfire Early-Warning**, **Wildlife Analytics** (keep).
- Add a highlighted **"Coordinated Intelligence / Physical AI"** block (on Technology or Home): the **shared-intelligence corridor** — nodes cooperating to steer a herd safely home (the Corridor visual from the dashboard, shown publicly at a concept level). This is the differentiator; feature it.

## C. Authentication + Forest-Officer verification (currently only a login exists)

Design the full flow:

- **Public — self sign-up** (email + password) → role `public` by default. Can add phone + location + enable SMS alerts (Stay Safe).
- **Forest Officer — verified onboarding (two options, support both):**
  1. **Admin invite** (preferred): Admin creates/invites officers by email → they set a password. Clean and secure.
  2. **Request access:** officer signs up, submits **department + designation + official email/ID**, lands in a **pending** state; Admin sees an **"Officer approval queue"** and approves/rejects → role becomes `officer`. Until approved, they see only the public view.
- **Admin** — seeded/fixed; manages users, approvals, nodes, OTA, config; **audit log**.
- Add **forgot-password**, email verification, and session handling (all native in Supabase Auth).
- Keep the **demo accounts** for judges, but behind a "Demo" label.

## D. Added functionality (top-deep-tech + usability, no gimmicks)

- **Malayalam language toggle** (English ⇄ മലയാളം) — huge usability win for Kerala officers and residents; a genuine differentiator, not a gimmick.
- **Notifications center** (in-app) + delivery status of SMS/WhatsApp/email/push.
- **Exportable reports** (PDF/CSV) — incident + monthly summaries for the Forest Department.
- **Make the dashboard tools functional:** Replay (time-slider), Corridor (network view), Learning (deterrent effectiveness), Planner (draw boundary → node estimate), **Demo Mode** (one-click scenarios) — wire to seeded data now, live later.
- **Accessibility + PWA install** (works one-thumb, gloves, offline) — already the goal; verify.
- **Audit log** (admin) for trust/governance.

## E. Map the web app to the hardware (the data contract)

The dashboard must render what the node/backend actually produce. Emit these into Supabase (see `web/backend/schema.sql`):

- **Node** → `nodes`: id, gps, status, firmware, **battery_pct, solar_w, last_seen** → feeds Fleet tiles + map pins.
- **Detection event** → `events`: node_id, ts, species, **per-modality confidences (seismic/audio/vision)**, fused confidence, direction, action, outcome, media_url → feeds Alerts + "Why the AI acted" card + radar.
- **Corridor activation** → an event field / table listing which neighbour nodes fired → feeds the Corridor view.
- **Deterrent outcome + reward** → feeds the Learning view.
- **Health telemetry** → `health` → predictive maintenance.

Path: **node → LoRa → ChirpStack gateway → `web/ingest` (MQTT→Supabase) → dashboard (realtime).** For the contest, **seed realistic demo data** so it looks live before field data flows; then switch to real ingest.

## F. Build path (finish design → production app → hardware)

1. **Iterate design in the SAME Fable project** (don't restart) using the prompts in §H until the visuals are final (Asian elephant, images, logo, no em-dashes, signup/officer screens, new sections).
2. **Rebuild the production app in `web/frontend`** with **Claude Code (Sonnet 5)**: point Claude Code at `EleTect Platform.dc.html` as the exact visual spec → build a real **React + Vite + Tailwind + shadcn** app that matches it, with routing + the three roles.
3. **Wire Supabase** (run `web/backend/schema.sql`; add signup + officer-approval; RLS; auth) and **deploy to Vercel** (free).
4. **Seed demo data**, then connect **`web/ingest`** for live node data.
5. **Hardware**: firmware/ingest emit the fields in §E → the dashboard goes live.

## G. Which chat / tool to use (your question)

- **Design edits:** stay in the **existing Fable project** (iterate; never restart — it holds the whole app).
- **Production build + backend + hardware wiring:** **Claude Code in VS Code** (this is code + repo work).
- **Planning/review:** **start a FRESH Cowork chat.** This conversation is very long, which wastes tokens on every turn. Open a new Cowork chat and paste/attach `CONTEXT.md` (+ this file) as the primer — you'll keep full context at a fraction of the token cost. Use Cowork for planning/review, Claude Code for building.

## H. Ready-to-paste Fable follow-up prompts

- "Replace every elephant image with an **Asian elephant** (smaller ears, twin-domed head, single tusker), Western-Ghats/Kerala setting. Swap the Anti-Poaching galaxy image for a night-forest ranger-patrol image. Make Road, Railway, and Wildfire images India-relevant and high quality."
- "Add our logo (attached) to the nav, footer, login, and dashboard header. Keep spelling **EleTect / EleTect X / EleTect Ops** consistent."
- "**Remove all em-dashes** across the site; use commas, periods, or colons instead."
- "Add a **Sign-up** page (public self-register) and an **officer onboarding** flow: officers submit department + designation + official email and enter a **Pending approval** state; add an **Admin → Officer approval queue** to approve/reject. Add forgot-password."
- "Add a **Malayalam ⇄ English** language toggle site-wide."
- "In Solutions, lead Elephant-Conflict with **crop-raid prevention**, add an **Other Wildlife** deterrence section (boar, gaur, deer, monkey), rename Anti-Poaching to **Anti-Poaching & Illegal Logging** (gunshot + chainsaw detection), and add a **Coordinated Intelligence / Physical AI** section showing nodes steering a herd through a safe corridor."
- "Give **EleTect X** and **EleTect Signage** their own product images/cards; add placeholders for future products."
- "After changes: screenshot every page desktop + mobile, test all flows + the new signup/approval, fix issues, re-verify, deploy, return the link."
