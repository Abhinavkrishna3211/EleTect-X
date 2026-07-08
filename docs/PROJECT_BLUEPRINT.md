# EleTect X — Project Execution Blueprint

The plan we follow from today to contest submission. Read `CONTEXT.md` first. This document covers: repo architecture, documentation, software architecture, development workflow, backend/dashboard (incl. the time-boxed Fable build), VS Code, the Claude Code workflow, and the week-by-week roadmap.

---

## 0. First actions (do today)
1. **Create the private repo** and push this skeleton:
   ```bash
   gh repo create Abhinavkrishna3211/EleTect-X --private --source . --remote origin
   git init && git add . && git commit -m "chore: initialise project structure"
   git branch -M main && git push -u origin main
   git checkout -b develop && git push -u origin develop
   ```
2. **Protect `main`** (GitHub → Settings → Branches → require PR + CI).
3. **Start the Fable frontend build** (§5) — the Fable window closes **12 Jul**; this is the single most time-critical task.
4. Confirm hardware orders (camera B0CQ4QDCXN, geophone, speaker, LEDs, IR, power) per `docs/hardware/bom.md`.

---

## 1. Repository architecture
Polyglot monorepo (one repo = one product, atomic cross-cutting changes, one CI). Structure and rationale are in the tree + `docs/README.md`. Key choices:
- **Monorepo over many repos:** firmware ↔ linux ↔ cloud ↔ dashboard change together; a monorepo keeps them in lockstep and simplifies CI/onboarding.
- **`docs/` as first-class:** `CONTEXT.md` (canonical) + ADRs (the "why") prevent architecture drift.
- **Local dev-tool config git-ignored** (`CLAUDE.md`, `.claude/`) → the committed repo reads as pure human engineering.
- **Branch model:** trunk-based — `main` (protected, deployable) ← `develop` ← short-lived `feat/…`, `fix/…`. Conventional Commits → automated changelog/versioning.

## 2. Documentation
See `docs/README.md` for the hierarchy and the consolidation map (migrate the research .md files into one current doc per topic; archive the rest, dated, read-only). Maintenance rule: **one current doc per topic; `CONTEXT.md` wins conflicts; decisions get an ADR.**

## 3. Software architecture

| Layer | Runtime | Responsibilities | Interfaces |
|---|---|---|---|
| **STM32U585** | C/C++ (Arduino Core / Zephyr) | geophone ADC (LPBAM) + STA/LTA + TinyML footfall; gunshot trigger; actuator timing (horn/LED/IR); LoRa MAC (E5, AT); power/load-switch mgmt; **safety rule-gates**; watchdog | Bridge RPC ↔ MPU; GPIO/ADC/UART/I²C to peripherals |
| **QRB2210 (Linux)** | Python | vision capture (V4L2) + INT8 detector (Adreno/OpenCL); **log-odds fusion**; risk/RP; **contextual-bandit** deterrence; SQLite experience; movement prediction; coordination; LoRa uplink orchestration | Bridge RPC ↔ MCU; MQTT/LoRa to gateway |
| **Bridge (RPC)** | shared | MCU→MPU: features/events; MPU→MCU: decisions/commands. Send *meaning*, not raw frames/audio | serialized messages over the on-board link |
| **LoRa node** | Grove E5 | LoRaWAN IN865 Class A, OTAA/AES-128; TSV + health uplinks; pre-arm downlinks | to gateway |
| **Gateway** | SenseCAP SX1302 | region IN865 → ChirpStack; 4G backhaul | ChirpStack ↔ MQTT |
| **Backend** | Supabase | Postgres schema (nodes, events, health, alerts, users); Row-Level-Security auth; realtime; storage (thumbnails); edge functions (alert fan-out, OTA metadata) | REST/realtime to frontend; MQTT ingest bridge |
| **Ingest** | small service | ChirpStack MQTT → validate → Supabase | MQTT in, Supabase out |
| **Frontend** | React PWA (Vite + Tailwind + shadcn/ui) | ranger dashboard + public site; Leaflet map, Recharts, offline cache | Supabase client |

**Module map (create as work proceeds):** `linux/perception/{vision,audio}.py`, `linux/cognition/{fusion,bandit,risk,tracker}.py`, `linux/bridge/rpc.py`, `linux/comms/lora.py`, `firmware/stm32/src/{sensors,footfall,actuators,lora,power,state_machine}.c`, `cloud/backend/{migrations,functions}`, `cloud/ingest/`, `dashboard/src/{pages,components,lib}`.

**Interfaces are contracts** — define the RPC message schema and the Supabase table schema **first** (they let firmware, linux, and dashboard progress in parallel).

## 4. Development workflow — what to build before hardware arrives
Order work by the **critical path to a field-deployable node + a demo**, maximising parallelism.

**Buildable NOW (no missing hardware):**
- Backend schema + Supabase + ingest + **dashboard/marketing (Fable, §5)** — 100% now.
- LoRaWAN stack: ChirpStack + SenseCAP (IN865) + Grove E5 join/uplink (you have E5 + gateway).
- STM32 skeleton: state machine, power/load-switch control, LoRa uplink, Bridge RPC, actuator GPIO (drive LEDs/amp with what you have: TPA3116 + a test speaker/LED).
- Geophone front-end **on the bench** using the **ADS1115 + INA333 you already own** as a stand-in ADC to prototype STA/LTA + feature extraction, then port to the STM32 internal ADC when validated. *(ADS1115 stays a bench tool, not in the final node.)*
- Acoustic pipeline: INMP441 capture + gunshot/chainsaw feature prototype.
- Vision pipeline: develop capture + detector using **any USB webcam** as a stand-in until the IMX462 arrives.
- AI training: vision model on public elephant/wildlife datasets + night augmentation; seismic model bootstrapped on public/synthetic data (refine with real geophone data on arrival).

**Needs hardware (do on arrival):** final geophone coupling + calibration (SM-24), IMX462 night/IR tuning, horn SPL test, LED/IR optical isolation, full integration, power/solar validation, then the DFO field test.

**Critical path:** camera+geophone arrival → node integration → bench validation → field test → footage → submission. Everything off the critical path (backend, dashboard, AI training, firmware skeleton) runs in parallel now.

## 5. Backend, dashboard & the Fable build (time-critical — window closes 12 Jul)

**Stack (chosen for speed + professionalism + free hosting):** **Supabase** (auth + Postgres + realtime + storage + edge functions) + **React PWA** (Vite/Tailwind/shadcn) + **Vercel** hosting. Rationale: Supabase gives production-grade auth/DB/realtime with almost no backend code (fastest path to a functional, secure dashboard on a deadline); Vercel gives instant professional hosting + CI previews.

**Use Fable to generate the frontend before access expires.** Fable produces the polished React UI fast; you then wire it to Supabase and host on Vercel. Prompt Fable for a **single cohesive product**:

Pages to generate (give Fable this brief):
- **Public / marketing:** Home (hero: "Protecting farms, forests, and the future"), How It Works, Product / Technology, Impact & Achievements, Field Deployment, Contact, and a clean nav/footer. Modern, high-end, dark-forest palette, subtle motion, mobile-first.
- **Auth:** Login / role-based (Ranger, Officer, Admin).
- **Dashboard (ranger-first, dead simple):** Live **map** of nodes (status colours), **Alerts** feed (confirmed events, confidence, thumbnail, direction, acknowledge button), **Node detail** (battery/solar/last-seen/firmware), **Event replay** (timeline + media), **Analytics** (events by time/species/weather; hotspot heatmap), **Maintenance** queue (predictive), **Fleet health**, **Settings/OTA status**.
- **Design system:** one theme, large tap targets, offline-friendly, "reads like a funded product."

Fable workflow: (1) generate all pages with realistic placeholder data; (2) **export the React code into `dashboard/`**; (3) replace placeholders with the **Supabase client** (tables: `nodes`, `events`, `health`, `alerts`, `users`); (4) deploy to **Vercel**; (5) point a domain later. Do the *generation + export* before 12 Jul; the Supabase wiring can happen after.

**Backend build order:** Supabase project → schema + RLS → seed demo data (so the dashboard looks alive for the contest) → ingest bridge (ChirpStack MQTT → Supabase) → edge function for alert fan-out (WhatsApp/SMS) → OTA metadata table.

## 6. VS Code environment (isolated from your other projects)
- **Open via `EleTect-X.code-workspace`** (a multi-root workspace) — settings/extensions apply only to this workspace, never globally.
- **Recommended extensions** are pinned in `.vscode/extensions.json` (VS Code will prompt to install *for this workspace*): Python + Pylance + **Ruff**, C/C++ + **PlatformIO** (STM32), ESLint + **Prettier** + Tailwind (frontend), **GitLens**, **Error Lens**, Markdown All-in-One, YAML/TOML, Docker.
- **Formatters/linters:** Ruff (Python), Prettier+ESLint (web), clang-format (firmware). `format on save` is set per-language in `.vscode/settings.json` (workspace-scoped).
- **Testing:** pytest (linux/ai), Vitest (dashboard), PlatformIO unit tests (firmware).
- **Git/GitHub:** trunk-based + PR template + CI (`.github/workflows/ci.yml`) + branch protection.
- **CLI tools:** `gh` (GitHub), `supabase` CLI, `pio` (PlatformIO), `ruff`, `pnpm`/`npm`, `mosquitto_sub` (test MQTT).

## 7. Claude Code workflow (max quality, min tokens/limits)
**Context discipline (biggest token saver):**
- `CONTEXT.md` + `CLAUDE.md` are small and always loaded; **don't** paste large docs — reference paths.
- **Load only the module you're touching.** Use the **explorer subagent** (Haiku, read-only) for wide searches so file dumps never enter the main context.
- **`/compact` after each task; start a fresh session per feature.** Commit, then clear.
- Keep the working set small: one subsystem per session (firmware *or* linux *or* dashboard).

**Model & effort routing:**
| Task | Model | Reasoning effort |
|---|---|---|
| Boilerplate, tests, commit messages, formatting, log parsing | **Haiku 4.5** | low |
| ~90% of coding (Python modules, React components, firmware features, refactors) | **Sonnet 5** | medium |
| Architecture, cross-processor race conditions, hard debugging, AI methodology, fusion/bandit math | **Opus 4.8** | high/max |
| Marketing/website copy, documentation prose | **Fable 5** | low |

**Loops:**
- *Implementation:* state the task + acceptance criteria + the one file/module + "follow CONTEXT.md" → implement → run tests → `/compact` → commit.
- *Review:* run the **reviewer subagent** on the diff before merge (correctness, safety, power/latency, secrets).
- *Debugging:* reproduce → isolate (logs/tests) → hypothesis → fix → regression test. Escalate to Opus only when stuck.
- *Task decomposition:* break features into ≤½-day units with explicit acceptance criteria (mirror them as GitHub issues).

**Never** let the model reference itself/AI in code, comments, commits, or docs.

## 8. Week-by-week execution roadmap (today → 30 Aug)

| Window | Focus | Milestones / exit criteria |
|---|---|---|
| **Now – 12 Jul** | Repo + **Fable frontend** + backend start | Repo pushed & protected; Fable pages generated + **exported to `dashboard/`**; Supabase project + schema; hardware orders confirmed |
| **12 – 21 Jul** | Backend wiring + firmware skeleton + AI bootstrap | Dashboard live on Vercel with seeded data; Supabase auth + RLS; ChirpStack + Grove E5 join/uplink working; STM32 state machine + LoRa uplink + actuator control on bench; vision detector training on public data |
| **22 Jul – 1 Aug** | Integration as hardware lands | Geophone front-end (INA333→STM32 ADC) + STA/LTA + footfall model; IMX462 capture + IR + detector on device; DFPlayer→TPA3116→horn deterrence; log-odds fusion + bandit loop; end-to-end **detect→confirm→deter→learn** on the bench; **freeze MVP by ~1 Aug** |
| **1 – 6 Aug** | Hardening + power + enclosure | PETG enclosure assembled; power/solar + protection validated; conformal coat; reliability + power-meter capture; build a spare node |
| **6 – 14 Aug** | **DFO field test (Kothamangalam)** | Deploy at a crossing; detection+alert mode first, then capped deterrence; capture **night IR footage + power trace + learning curve**; iterate; get DFO sign-off/quote |
| **15 – 23 Aug** | **Robu submission** | Demo video (bench+field), story, complete BOM, schematic (KiCad/Fritzing), code repo, presentation → **submit ≤ 23 Aug** |
| **24 – 30 Aug** | **Hackster submission** | Expand docs with field results + PCB render + scale story → **submit ≤ 30 Aug** |

**Dependencies / critical path:** camera + geophone arrival → integration → bench validation → field test → footage → submissions. **Risk mitigation:** (a) do all hardware-independent work now (backend/dashboard/AI/firmware skeleton); (b) buy a spare camera; (c) run detection+alert mode before deterrence in the field; (d) freeze the MVP 1 Aug so the field test runs on stable code; (e) keep two submission drafts filling as you build (docs are 30% of Hackster's score).

---

## Engineering principles (apply to every decision)
Measurable improvement · explainable AI · low power · robustness · maintainability · scalability · manufacturability · cost-effectiveness · reliability · **simplicity over complexity**. Reject gimmicks. Every non-trivial choice carries a one-line justification (and an ADR if it's architectural). Build like a senior team shipping a product — not a prototype.
