# EleTect X — Build Blueprint to Aug 8 (supersedes PROJECT_BLUEPRINT.md §6)

Read `CONTEXT.md` first. This document plans every remaining task from **today (Sun 26 Jul 2026)** to a
self-imposed **freeze on Sat 8 Aug**, ahead of the DFO field test and both contest deadlines. It replaces
the week-by-week table in `docs/PROJECT_BLUEPRINT.md` §6, which was written before this project's true
starting point was known. Everything else in `PROJECT_BLUEPRINT.md` (repo architecture, module map,
engineering principles) still stands.

## 0. Reality check — what's actually done vs. what's actually left

A repo scan, not a guess, is the basis for this plan:

**Done, and further along than the old roadmap assumed:**
`web/frontend` is a built, routed, RBAC'd React PWA — public marketing pages, auth (signup/officer-approval/
forgot-password), dashboard shell + modules (map, alerts, node detail, analytics, maintenance, fleet
health), admin user management, Demo Mode, CI (lint/typecheck/test), Vercel config, and four rounds of
QA screenshot passes already recorded under `docs/qa/`. `web/backend` has schema + RLS + three migrations
+ two edge functions (officer-request notification, alert fan-out with tests). `web/ingest` is a working
TypeScript service (MQTT → validate → Supabase) with a Dockerfile. `hardware/bom/bom.md` is a 178-line,
mostly-locked sourcing document. Four ADRs already exist recording real engineering decisions.

**Not started — this is the entire remaining critical path:**
`device/mcu`, `device/mpu`, and `ml` are empty except READMEs. Zero firmware, zero cognition code, zero
trained models. Robu's own rubric weights **Functionality & Execution at 40 of 100 points** — more than
Innovation, Documentation, and Presentation combined — and functionality lives entirely in these three
empty directories. **This is the headline fact driving this whole blueprint: the web app will not move
the needle further, the physical/firmware/ML stack is 100% of what's left to build, and it needs to go
from nothing to a bench-validated end-to-end loop in 13 days.**

## 1. Where Edge Impulse fits

Edge Impulse has confirmed, immediate support for the Arduino UNO Q, including its STM32U585 MCU side —
this is the direct mechanism for CONTEXT.md §4's "TinyML footfall" requirement. Use one Edge Impulse
project per on-device model, all under one account:

- **Seismic/footfall (STM32U585, primary):** feed it labeled STA/LTA feature windows from the geophone
  bench rig (ADS1115+INA333 stand-in, then real SM-24 once potted). Export as a C++ inference library,
  link into the Arduino-Core firmware. This is the lowest-risk, most spec-aligned use of EI.
- **Vision detector (QRB2210, secondary):** rather than hand-rolling a training pipeline in `ml/vision`
  from scratch under deadline pressure, use EI's transfer-learning object detection with INT8 quantization,
  trained on public wildlife/elephant datasets plus night-augmentation. Export a quantized TFLite model
  that runs on the QRB2210 (Adreno/OpenCL path if the runtime supports it, plain TFLite as fallback).
- **Acoustic corroboration (INMP441, stretch):** EI's audio classification block (MFCC + classifier) for
  the gunshot/chainsaw anti-poaching signal — same account, marginal extra setup cost once the pipeline
  exists for footfall.

One EI account training all three models for three different compute targets (MCU TinyML, Linux INT8
vision, Linux audio classifier) is also a genuine, honestly-earned "innovation" talking point for judging
— it's a real unified pipeline, not a gimmick bolted on for the story.

## 2. Where Arduino App Lab fits

App Lab is the pre-installed dev environment on UNO Q that combines an Arduino C++ sketch (STM32U585
side) with a Python app (QRB2210 Linux side) and a built-in inter-processor bridge. This is the concrete
implementation of CONTEXT.md §5's abstract "Bridge (RPC)" layer — use App Lab's native bridge primitive
instead of hand-rolling a UART/SPI framing protocol. Per `PROJECT_BLUEPRINT.md` §3 ("interfaces are
contracts"), define the RPC message schema first — MCU→MPU (features/events: footfall probability, ADC
features, gunshot flag) and MPU→MCU (decisions/commands: deterrence action, gain level, LED pattern) —
then implement both sides against that shared schema. Day 1 below includes a deliberate "hello world"
round-trip test through App Lab's bridge before any real content is built on top of it, specifically to
de-risk unfamiliar tooling early rather than discovering integration problems on day 10.

Using App Lab and Edge Impulse well also directly serves the Hackster contest's spirit — Arduino,
Qualcomm, and Edge Impulse are its three named sponsors, so a project that genuinely exercises all three
sponsor tools (not just the UNO Q board itself) reads as fuller use of what was provided.

## 3. Contest requirements, verified from primary sources (not search snippets)

**Robu / Arduino Physical AI Challenge India 2026** — confirmed live on the official contest page.
Deadline **23 Aug 2026**, registration by **15 Aug**, winners announced **31 Aug**. Team size 1–4, India
residents only, original/unpublished work. Judging (100 pts): Functionality & Execution **40**, Innovation
& Originality **25**, Technical Documentation **20**, Presentation & Creativity **15**. Submission needs: demo
video, GitHub source, project report PDF, mandatory UNO Q purchase proof.

**Hackster "Invent the Future with Arduino UNO Q and App Lab"** — confirmed from the official rules page.
Runs 3 Mar – **30 Aug 2026, 11:59 PM PT**, winners announced 25 Sep. Entries are single-Hackster-account
authored (not team-attributed on the platform itself). Judging (100 pts): Project Documentation/
Story-Instructions **30**, Complete BOM **20**, Schematics **15**, Code & Contribution **15**, Creativity **20**.
Submission needs project name, description, cover image, BOM, full instructions, images, and resource
files (schematics/code/CAD).

**One real content-policy risk to design the write-up around:** Hackster's rules explicitly bar content
involving "military, defense, autonomous weapons, harmful surveillance technologies." EleTect X's
anti-poaching gunshot/chainsaw corroboration (INMP441) is legitimate wildlife-conservation acoustic
classification, not surveillance of people, but the documentation must frame it that way explicitly —
"acoustic signature classification for a ranger alert," not "detecting humans" or "weapon detection." Bake
this framing into the project story from the first draft, not as a late edit.

## 4. Day-by-day schedule, Sun 26 Jul → Sat 8 Aug

| Date | Firmware (STM32U585) | Cognition (QRB2210) + ML | Hardware/integration | Exit criteria |
|---|---|---|---|---|
| **Sun 26 Jul** | Scaffold `device/mcu` (Arduino Core project, state-machine skeleton, power stub) | Define Bridge RPC schema (MCU→MPU features/events, MPU→MCU decisions); create 3 Edge Impulse projects (footfall, vision, acoustic) | — | Schema written down; EI projects exist; MCU project builds empty |
| **Mon 27 Jul** | Geophone ADC front-end (ADS1115+INA333 bench stand-in) + STA/LTA algorithm | Start collecting/labeling seismic training windows (bench stomp-tests + synthetic + public proxy data) | — | STA/LTA runs on bench data, logs trigger events |
| **Tue 28 Jul** | Actuator drivers (horn PWM gain-limited per ADR 0003, LED strobe, IR MOSFET pulse); LoRa MAC via Grove E5 | Scaffold `device/mpu` module tree; App Lab "hello world" round-trip MCU↔MPU | — | A dummy message survives a round trip through the real Bridge |
| **Wed 29 Jul** | Integrate EI footfall v1 model (C++ export) into STA/LTA pipeline; bench stomp-test | Vision capture (V4L2) skeleton on USB webcam stand-in; build EI vision dataset (public wildlife images + night augmentation) | — | Footfall model fires correctly on real stomp tests |
| **Thu 30 Jul** | Safety rule-gates: burst-duration cap + trigger cooldown (ADR 0003), unit-tested | Train EI vision v1 (INT8), export, run inference loop on QRB2210 against webcam stand-in | — | Vision detector returns confidence scores on stand-in feed |
| **Fri 31 Jul** | — | Implement log-odds fusion math (CONTEXT.md §4) fed by real STM32 features over the Bridge | — | Bench test: stomp + webcam trigger → fusion → risk score (detect+alert only, no deterrence yet) |
| **Sat 1 Aug** | Wire actuator commands from MPU decisions over the Bridge | Contextual bandit (never-repeat, stop-on-retreat) + SQLite experience store | — | **Milestone: full detect→confirm→deter→learn loop on bench with stand-ins (seismic + vision only — acoustic deferred, see ADR 0007 addendum)** |
| **Sun 2 Aug** | Swap in real actuators as parts arrive | Recalibrate thresholds on real sensor data | Real SM-24 geophone (potted capsule/spike — this is the scheduled Aug 2 reminder), real IMX462+940nm IR, real LEDs if arrived | Real-part swap validated against bench baseline |
| **Mon 3 Aug** | Power/load-switch management against real rail | — | 4S LiFePO4 + MPPT + solar + supercap + surge/reverse-polarity protection wired (scheduled Aug 3 reminder) | Power draw measured against µA-idle target |
| **Tue 4 Aug** | — | LoRa end-to-end: SenseCAP gateway (IN865 confirmed) → ChirpStack → `web/ingest` → Supabase → dashboard | Enclosure assembly starts: PETG print, gasket seams, e-PTFE vent, SUH-15 flush-mounted (ADR 0003), conformal coating | A real LoRa event shows up live on the already-built dashboard |
| **Wed 5 Aug** | — | — | Full closed-enclosure bench validation: sealed node, on battery/solar, triggers end-to-end | Sealed node runs unattended and reports correctly |
| **Thu 6 Aug** | Edge-case hardening: false-trigger rejection (wind/rain/vehicle), LoRa dropout/retry, battery-low safe state | Same hardening pass on cognition side | Multi-hour reliability soak test | No false triggers or crashes over the soak window |
| **Fri 7 Aug** | Flash/duplicate config for a spare node | — | Build the spare node (risk mitigation from the old plan) | Second unit flashable in minutes, not hours |
| **Sat 8 Aug** | **MVP freeze — bug fixes only past this point** | Final full-pipeline regression test | Tag a git release; node packed for transport | Node ready to leave for Kothamangalam |

Documentation runs in parallel throughout, not bolted on at the end: keep updating ADRs as decisions get
made, and start drafting the Robu project report and Hackster project story skeletons around **Aug 6–7**,
since documentation is worth 20–30% of either score and both docs benefit from being written while details
are fresh rather than reconstructed afterward.

## 5. After the freeze

- **~9–14 Aug — DFO field test (Kothamangalam):** deploy at a real crossing, detection+alert mode first,
  then capped deterrence per ADR 0003's cooldown/burst-cap safeguards. Capture night IR footage, power
  trace, and the bandit's learning curve. Iterate on anything the field exposes that the bench didn't. Get
  DFO sign-off/quote. **Single node, seismic + vision only** — acoustic is deferred (ADR 0007 addendum,
  30 Jul), so the field-bound unit isn't carrying that subsystem into this test.
- **~15 Aug onward — acoustic subsystem, on the second UNO Q unit:** INMP441 hardware bring-up, the
  ADR 0009 Rung 2 LPBAM dual-channel concurrency bench test, gunshot/chainsaw/vehicle/animal-call
  dataset collection (`DEVICE_DEVELOPMENT_WORKFLOW.md` §4a), and Edge Impulse acoustic model training —
  on the bench/dev unit, never touching the field-validated node. Runs alongside the submission sprints
  below, not blocking either.
- **15–23 Aug — Robu submission sprint:** register by 15 Aug. Cut the demo video (bench + field footage),
  finalize the GitHub repo (history already reads clean per the existing commit log), write the project
  report PDF mapped explicitly onto the four judged categories, attach UNO Q purchase proof, submit by 23
  Aug.
- **24–30 Aug — Hackster expansion sprint:** re-platform onto Hackster's project format under one
  authoring account. Add drawn/photographed schematics (15 pts — not yet started, needs its own time
  block). Adapt `hardware/bom/bom.md` into Hackster's BOM format (20 pts — mostly a repackaging job, not new
  work). Write the story/instructions to the "would a beginner reading this recreate it" bar (30 pts).
  Foreground genuinely creative technical choices for the Creativity score (20 pts): the felid-growl/
  bee-buzz deterrence research behind the audio design, the log-odds fusion math, the never-repeat bandit,
  and the one-account-three-targets Edge Impulse pipeline. Apply the conservation-not-surveillance framing
  from §3 throughout. Submit by 30 Aug.

## 6. Risk register

- **Hardware ordering closed 28 Jul.** Mechanical BOM, LED integration parts, and the power system
  (4S LiFePO4 pack w/ built-in BMS, LiFePO4-aware MPPT controller, 20 W panel) are all ordered; only the
  Steko lens (dropped, see §0 below) had a slow-shipping item. Remaining arrival risk is shipping time, not
  sourcing uncertainty — the geophone/camera/LED real-part swap dates in §4 may still slip a few days, but
  every software/ML task through 1 Aug already runs on bench stand-ins (ADS1115+INA333, USB webcam)
  validated as adequate, so the 8 Aug freeze doesn't depend on that slipping schedule resolving early.
- **Three trained models in ~10 days is genuinely aggressive**, vision especially. Mitigation: use existing
  public wildlife/camera-trap datasets rather than collecting original imagery, and keep the vision
  detector's scope narrow (elephant / not-elephant, plus a small number of secondary classes) rather than
  a broad multi-species classifier.
- **App Lab's Bridge is unfamiliar tooling.** Mitigation: Day 3's deliberate "hello world" round-trip test
  exists specifically to surface integration problems on day 3, not day 10.
- **The Resend transactional-email domain decision is still open** and matters for real residents signing
  up with real contact info, but it doesn't block either contest submission or the physical build — track
  it as a parallel item to close before real onboarding, not before 8 Aug.
- **Hackster's single-account-authorship rule** — confirm now which one account is the submitting author if
  more than one person is involved in the build, so this isn't a last-minute question on 29 Aug.

## 7. Division of labor

This Cowork session continues to plan, research, cross-check sourcing/specs, and verify (this document,
the ADRs, contest-rubric mapping). The local VS Code Claude Code session — with real repo/git/network/
Supabase/Vercel access — writes the actual firmware, Python cognition code, and Edge Impulse integration
day by day against this schedule; relay each day's prompt and status both ways. Physical work no agent can
perform — soldering, potting the geophone capsule, 3D-printing and gasketing the enclosure, the actual
field install — stays with you, along with the judgment calls on Edge Impulse dataset labeling that
benefit from a human in the loop.

## 8. Status as of 28 Jul — catch-up plan + the Opus/Sonnet handoff protocol

A repo scan run today confirms `device/mcu`, `device/mpu`, and `ml` are **still 100% `.gitkeep`/README
scaffolding** — none of Day 1 (Sun 26), Day 2 (Mon 27), or Day 3 (Tue 28)'s tasks have landed yet. That's
3 of 13 days gone with zero firmware/cognition code written. This isn't a reason to panic-replan; it's a
reason to compress the first three rows into one focused build pass, since nothing in those rows was
actually blocking on hardware or on each other — and to fix the process gap that let 3 days pass without
code: every session from here forward has a scoped, checkable exit condition (below), not an open-ended
"work on the firmware" prompt.

**Enclosure/LED decision closed since this doc was written:** the Steko lens+holder is dropped (ADR-worthy
— add one). The concept doc's own side-wing design never called for an optic; LEDs mount as bare
star-PCBs bonded via thermal adhesive straight into a printed heatsink-puck pocket in each wing. One fewer
part, one fewer slow-shipping dependency, and it better matches the wide-angle peripheral-deterrence intent
in `hardware/cad/enclosure-design-concept.md` than a focused 60° beam would have.

**All engineering conventions below are governed by `docs/ENGINEERING_CONVENTIONS.md`** — read it before
opening the first VS Code session. It fixes the layering, testing, and documentation bar; this section
only fixes *sequencing and session scoping*.

### Catch-up pass — today, compressed Day 1–3 scope in one sitting

Run as **one Opus planning call, then one or two Sonnet build calls**, not day-by-day:

1. **Opus (single call):** produce `device/mpu/bridge/schema.md` — the full Bridge RPC schema (MCU→MPU:
   footfall probability, raw ADC feature vector, gunshot flag; MPU→MCU: deterrence action, gain level, LED
   pattern), each field named/typed/ordered, version byte included (§6 of ENGINEERING_CONVENTIONS.md).
   Also produce the function-signature spec for the geophone bench front-end and the actuator drivers
   (`read_seismic_window()`, `read_acoustic_window()`, `drive_horn()`, `drive_led()`, `pulse_ir()`) — no
   implementation, just contracts + one-line pre/post/error behavior each. Output should be under two
   pages; if it's longer, it's drifted into implementation.
2. **Sonnet (build call 1 — `device/mcu`):** scaffold the Arduino Core project against the spec above:
   `config.h`, `state_machine.cpp` (skeleton), `sensors/geophone.cpp` (ADS1115+INA333 stand-in
   implementation of the contract), `footfall/sta_lta.cpp` (pure function, unit-tested with a synthetic
   trace — known-answer test per §4), `actuators/{horn,led,ir}.cpp`, `lora/mac.cpp` (Grove E5 AT join).
   **Exit condition:** `pio test` green on the STA/LTA unit test; `pio run` builds clean; a bench stomp-test
   produces a logged trigger event.
3. **Sonnet (build call 2 — `device/mpu` + Edge Impulse projects):** scaffold `device/mpu`'s module tree
   (`bridge/rpc.py` implementing the schema from step 1, `perception/`, `cognition/`, `services/config.py`),
   create the 3 Edge Impulse projects (footfall, vision, acoustic — empty/initialized, not trained yet), and
   run the App Lab "hello world" round-trip through the real Bridge. **Exit condition:** a dummy message
   sent from the MCU side is received and logged on the MPU side through App Lab's actual bridge, not a
   mock.

That closes Days 1–3's scope. Days 4 onward (Wed 29 Jul in §4's table — EI footfall model integration,
vision capture skeleton) resume the original day-by-day cadence from `BUILD_BLUEPRINT_AUG8.md` §4 as
written, one Sonnet session per row, each scoped to that row's exit criteria only.

### The standing protocol for every session after today

- **One Opus call per module boundary**, not per day: whenever a new interface needs defining (fusion's
  input/output contract, the bandit's state/action/reward shapes, the SQLite experience-store schema) —
  spec only, a page or less, no code.
- **One Sonnet call per schedule row**, scoped exactly to that row's "Exit criteria" cell in §4's table.
  Paste: `CONTEXT.md` relevant section, the specific Opus spec for the module in play, and the
  `ENGINEERING_CONVENTIONS.md` sections that apply (usually §2–4) — never the whole repo.
- **Every session ends with either a green test or an explicit blocker note in `KNOWN_GAPS.md`** — never a
  silent "mostly working." If a row's exit condition isn't met, the next session starts by fixing that row,
  not by moving to the next one.
- **You review the diff before it's committed**, every time — this is the one step no agent call replaces.
