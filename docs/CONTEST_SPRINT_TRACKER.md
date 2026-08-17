# EleTect X — Contest Sprint Tracker (planning-session doc, updated 17 Aug 2026)

Lives alongside `HANDOVER.md`/`docs/KNOWN_GAPS.md` (the technical source of truth — don't duplicate
their detail here) but tracks something they don't: the cross-session punch list toward the two near-term
goals below, kept current by the planning session (this one) as reports come back from the VS Code/Sonnet
session and from the user's own hands-on hardware work. If this doc and `HANDOVER.md` disagree on a
technical fact, `HANDOVER.md` wins — this file is priorities/status, not technical detail.

## The two goals, in order

1. **Contest-footage sprint (now → next few days, before 20 Aug):** get real footage of EleTect X
   detecting a trigger, firing its deterrents (horn/LED/IR), and — in the field — an elephant retreating
   safely. Node goes out, runs, gets physically retrieved, footage pulled off via laptop. This footage is
   the primary evidence for both contest submissions.
2. **Official field deployment (20 Aug, 10-day trial, DFO Kothamangalam-approved):** the real trial. VIN-only
   power test can only happen this day (confirmed by user). Everything the sprint above proves out de-risks
   this.

Contest deadlines: **Robu Arduino Physical AI Challenge India 2026 — 23 Aug**. **Hackster "Invent the Future
with Arduino UNO Q and App Lab" — 30 Aug, 11:59 PM PT**.

## Live punch list — what's actually urgent right now

Ordered by what blocks getting real footage. Owner column: **Sonnet** = VS Code/device code session,
**User** = needs your hands on the physical board/hardware, **Planning** = this session.

| # | Item | Owner | Status |
|---|---|---|---|
| 1 | Commit the large amount of real, verified, currently-uncommitted work sitting in the working tree (mac.cpp AT-command fix, bridge_handlers, fire_test harness, reflex_loop.py/decision.py, ADR 0011, docs) in clean logical chunks, before piling more changes on top | Sonnet | **Not started** — flagged 17 Aug, see inventory below |
| 2 | Wire the camera into `reflex_loop.handle_footfall_event()` — open on real trigger, capture a burst spanning pre-fire/fire/post-fire, save locally tagged with event metadata, close again; power-gated, not always-on | Sonnet | **Not started** — full prompt below |
| 3 | Extend `reflex_loop.py`'s actuate step to also drive LED + IR, not horn only — needed for footage of the *full* deterrent stack firing, not just audio | Sonnet | **Not started** — new scope, included in the prompt below |
| 4 | Confirm `SEISMIC_DEMO_MODE` is `0` (real stomp-validated thresholds, not tap-sensitive demo ratios) before any footage capture — demo mode risks false triggers on wind/rain in the forest and isn't representative for the contest | User + Sonnet | Currently **ON (1)** per `docs/eletect-x-applab-notes.md` — must flip before capture |
| 5 | Register `Bridge.provide("drive_horn", ...)` on real hardware — one line, flash, confirm everything else still works, commit | User + Sonnet, live session | Adapter code ready (`bridge_handlers.cpp`), registration commented out |
| 6 | Same, one at a time: `drive_led`, then `pulse_ir`, then `get_system_state` | User + Sonnet, live session | Same — code ready, not registered |
| 7 | Physically wire horn, LED, IR to the board | **User** (explicitly owned, "before deployment for sure") | Not done — your own task, not pushing instructions unless asked |
| 8 | `export ELETECT_SAFE_MODE=0` for the actual live-fire capture session (never a code default) | User | Not yet set — only matters at the moment of the real test |
| 9 | End-to-end bench rehearsal (stomp → camera starts → horn/LED/IR fire → footage saved → pulled off laptop, confirmed playable) before the forest trip | User + Sonnet | Blocked on 1-8 above |
| 10 | True VIN-only power test (board on 12.8V battery, no hub, no PD passthrough) | User | **Deferred to 20 Aug** by your own call — no action before then |

## Lower priority / explicitly deferred right now

- **LORA_SERIAL Serial-vs-Serial1 open risk** (`docs/eletect-x-applab-notes.md`) — does **not** block the
  footage sprint (footage is retrieved physically, not over LoRa). Must be resolved before the 20 Aug
  official deployment, since that one needs real DFO alerts over LoRa. Not urgent this week.
- **Enclosure/CAD, battery + solar procurement** — physical/hardware track, moving in parallel
  (`hardware/bom/procurement-status.md` is the live source of truth there — battery ordered 14 Aug with
  accepted delivery risk, solar panel plan is a local in-person buy this week). Not a Sonnet-prompt item.
- **Contest write-ups** — not started. Deliberately waiting on real footage before drafting, per
  `BUILD_BLUEPRINT_AUG20.md`'s own call ("start as soon as footage is in hand, not wait for the full
  10-day trial").

## Uncommitted work inventory (as of 17 Aug device check)

Real, substantive, currently sitting only in the working tree — not yet in git history. Not a criticism,
just a risk flag (this much uncommitted state is one bad `git checkout`/disk issue away from being lost):

- `device/mcu/src/mac.cpp`, `mac.h` — the LoRa-E5 AT-command manual-verification fix (real, already
  cross-checked against the actual PDF, "Network joined" → "+JOIN: Done" correction included)
- `device/mcu/src/ir.h`, `led.h` — blocking-call documentation additions
- `device/mcu/src/bridge_handlers.h/.cpp`, `fire_test.h/.cpp`, `main.cpp` wiring, `tests/test_bridge_handlers/`,
  `tests/test_fire_test/` — the Bridge RPC adapters + manual fire-test harness (written, host-tested, not
  yet registered on hardware)
- `device/mpu/services/reflex_loop.py`, `device/mpu/cognition/decision.py`, their tests — the real
  sense→fuse→decide→actuate loop (horn-only actuation currently)
- `docs/BUILD_BLUEPRINT_AUG20.md`, `docs/decisions/0011-horn-driver-split-to-separate-housing.md`,
  `docs/eletect-x-applab-notes.md`, `docs/specs/mcu-fire-test-harness.md`, `CONTEXT.md`,
  `docs/DEVICE_DEVELOPMENT_WORKFLOW.md` — planning/decision docs
- `hardware/bom/bom.md`, `procurement-status.md`, `hardware/cad/enclosure-design-concept.md`,
  `eletect-x-power-budget.xlsx`, CAD STEP/STL files, UNO Q reference PDFs — hardware/procurement track
- `scripts/live_seismic_plot.py`, `capture_geophone_console.py`, `correlate_geophone_excitation.py`,
  `geophone_excitation_stimulus.py`, `geophone_bench_excitation.html` — bench tooling
- `.gitignore`, `device/mpu/bench/camera_check/output/` (bench capture artifacts — likely belongs in
  `.gitignore`, not committed as binary output)

Full prompt to commit this cleanly (in logical chunks, not one giant commit) plus the camera/LED/IR
integration work is below — hand it to the VS Code/Sonnet session as-is.
