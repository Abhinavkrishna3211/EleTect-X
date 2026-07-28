# EleTect X — Engineering Conventions

Read `CONTEXT.md`, then this file, before writing any code in `device/`, `ml/`, or touching the Bridge or
LoRa schemas. `PROJECT_BLUEPRINT.md` and `BUILD_BLUEPRINT_AUG8.md` say *what* to build and *when*. This
file says *how* — the bar every module in the remaining critical path (`device/mcu`, `device/mpu`, `ml`)
is held to, so the repo reads as one senior engineer's work, not an assembled pile of sessions.

## 1. Depend on interfaces, not implementations — applied honestly, not decoratively

This project has exactly one of each piece of hardware, forever. A full HAL with abstract factories for
sensors we'll never swap is ceremony, not engineering — skip it. The real, earned interface boundaries
in this codebase are the ones `BUILD_BLUEPRINT_AUG8.md` already identified because there's a genuine
swap in progress:

- Geophone front-end: bench stand-in (ADS1115+INA333) → real STM32 internal ADC (LPBAM). One function
  signature (`read_seismic_window() -> float[N]`) both sides satisfy; STA/LTA and the EI footfall model
  call that signature and never touch the ADC/I²C directly.
- Vision capture: USB webcam stand-in → IMX462. One `capture_frame()` contract; the detector never
  imports V4L2 or a camera driver directly.
- Bridge RPC: the MCU/MPU boundary is a real interface because it's the one seam two independently-built
  sides must agree on — see §6.

Everywhere else (LoRa via Grove E5's AT command set, the DFPlayer-PRO, the TPA3116D2 gain control) is a
single driver file with a small, direct function set. No factory, no plugin registry, no config-driven
backend selection. Judge every future "should this be an interface" question by the same test: is there
a second implementation coming, or a real reason to test without the part? If not, write the direct call.

## 2. Structure

- **One responsibility per file.** If a file's job needs "and" to describe, split it. `device/mcu/src/`
  gets `sensors/geophone.cpp`, `sensors/acoustic.cpp`, `footfall/sta_lta.cpp` (pure math, no ADC calls),
  `actuators/horn.cpp`, `actuators/led.cpp`, `actuators/ir.cpp`, `lora/mac.cpp`, `power/load_switch.cpp`,
  `state_machine.cpp`, `bridge/rpc.cpp` — not one `main.cpp` doing all of it.
- **Layer strictly:**
  1. Contracts — a struct/function signature, no hardware calls (`SeismicWindow read_seismic_window()`).
  2. Implementations — the actual ADC/I²C/driver code satisfying that contract.
  3. Orchestration — the state machine, STA/LTA trigger logic, fusion, bandit; calls contracts only.
  4. I/O edge — Bridge serialization, LoRa framing, SQLite writes.
- **Functional core, imperative shell — this is the highest-leverage rule for this specific project.**
  STA/LTA, the log-odds fusion (`L = L_prior + Σ aᵢwᵢ(ℓᵢ−ℓ₀ᵢ)`), the bandit's action-value update, and risk
  scoring are all pure math over plain arrays/floats. Write and test every one of them as a function that
  takes numbers and returns numbers — zero ADC calls, zero Bridge calls, zero SQLite inside the function
  body. The MCU main loop and the MPU service loop are the thin, mostly-untested shell that feeds real
  sensor data into these pure functions and routes the result to an actuator or the Bridge.
- **Single source of configuration.** `device/mcu/include/config.h` and `device/mpu/services/config.py`
  hold every threshold, pin assignment, gain, cooldown, and burst-cap — each with a one-line rationale
  comment (why this value, not just what it is). No magic numbers inline in logic files.
- **Consistent naming.** `snake_case` for C++ and Python functions/variables (matches Arduino Core and PEP
  8 respectively), one file-naming pattern per language, matching the module map already fixed in
  `PROJECT_BLUEPRINT.md` §3.

## 3. Documentation

- **ADRs stay the record of "why."** Five already exist (`docs/decisions/0001`–`0005`). Every non-obvious
  call in the remaining build — the RPC schema's wire format (§6), the EI-vs-hand-rolled-model decision
  (`BUILD_BLUEPRINT_AUG8.md` §1, already effectively an ADR-shaped argument — formalize it as one), the
  safety rule-gate thresholds — gets the same treatment: numbered, dated, alternatives listed, not edited
  after the fact but superseded.
- **`docs/KNOWN_GAPS.md`** — create this once `device/mcu` work starts. One line per open issue: what's
  deferred, severity, effort estimate, status. The µA-idle power estimate already flagged as unvalidated
  belongs here until a bench measurement closes it.
- **Comments explain why, not what.** `// 2 Hz high-pass corner: below this is wind/traffic microseism,
  not footfall` earns its place. `// increment counter` does not.
- **Every public function gets a one-line contract** in its docstring/header comment: preconditions,
  what it returns on failure, whether it blocks. `read_seismic_window()`: never blocks past one ADC
  conversion cycle; returns a zero-filled array (not a null/exception) if the ADC read times out, so a
  transient I²C glitch degrades a trigger window rather than crashing the state machine.
- **Generated artifacts carry a banner.** The EI-exported C++ inference library and quantized TFLite model
  files get `// GENERATED by Edge Impulse — do not hand-edit; re-export from project vX` at the top.

## 4. Testing — pyramid, matched to the actual toolchain

- **Unit tests are the majority, and only possible because of §2's pure-core split.** `pio test` for
  STA/LTA, safety rule-gates (burst-cap/cooldown), and the fusion/bandit math (via `pytest` on the MPU
  side) — all fed fixed arrays, no hardware, milliseconds each.
- **Known-answer tests specifically for the math that has a "right" numeric answer:** feed the fusion
  formula a fixed prior + fixed sensor log-likelihoods, assert the exact output probability, not just
  "returns a float between 0 and 1." Same for STA/LTA threshold crossings on a synthetic seismic trace.
- **Golden/reference captures for the vision detector:** save the INT8 model's output (boxes + confidence)
  on a fixed small image set once it's validated; future re-exports diff against that set to catch
  unintended regressions from a retrain, separate from intentional accuracy improvements.
- **Fewer integration tests at the real seams:** the App Lab Bridge round-trip (Day 3 in
  `BUILD_BLUEPRINT_AUG8.md`, deliberately scheduled early to de-risk unfamiliar tooling), the
  ADS1115-stand-in → STM32-ADC swap validation (Day-of-arrival task).
- **One end-to-end test, and it's the Aug 1 milestone already on the schedule:** stomp + webcam trigger →
  fusion → deterrence on the bench. Expensive, slow, run manually, not part of CI — but it's the one that
  actually proves the product works, so it's not optional.
- **Failures are specific.** A safety-gate test that fails says which threshold and which input tripped
  it, not just `assert False`.

## 5. Version control

- **One logical change per commit**, Conventional Commits (`feat(mcu): add STA/LTA trigger detection`,
  `fix(mpu): correct fusion log-odds sign`), matching the pattern already in this repo's own commit log —
  continue it into `device/` and `ml/` exactly as followed in `web/`.
- **No AI/assistant attribution anywhere** — commit messages, code comments, docstrings, PR descriptions,
  ADRs. This is a standing hard rule (`CLAUDE.md`), not new guidance; it applies identically to every
  Sonnet-authored commit from here forward.
- **Feature branches per module**, even solo: `feat/mcu-geophone-frontend`, `feat/mpu-fusion`,
  `feat/ml-footfall-model` — merge to `develop` per `PROJECT_BLUEPRINT.md`'s branch model, squashing any
  "wip"/"fix typo" commits first.
- **No dead code or commented-out blocks committed** — delete; git history remembers it if needed back.

## 6. Interfaces between systems — the Bridge and LoRa schemas specifically

**Corrected 28 Jul 2026 against the real Bridge API** — see `docs/DEVICE_DEVELOPMENT_WORKFLOW.md` §3 for
the verified details; this section only carries the durable rule, not the mechanics. The Bridge is not a
raw byte/struct link — it's `Arduino_RouterBridge.h`'s named `Bridge.provide("name", func)` /
`Bridge.call("name", args)` / `Bridge.notify("name", args)` API, confirmed directly against Arduino's own
reference Bricks (Blink LED, Fan Vibration Monitoring): `call` is synchronous request/response and blocks
the caller until a response or timeout; `notify` is fire-and-forget with no return value and never blocks
the caller. That changes the design task from "define a wire schema" to **naming and signing the function
boundary** (arguments, return value, which of the two call semantics applies, and — for `call` specifically
— an explicit timeout/failure behavior). The drift risk this
section originally worried about is still real (two independently-built sides must agree on every function
name and signature), it's just solved one level up from bytes:

- **One doc is still the source of truth** — `device/mpu/bridge/schema.md`, a table of every Bridge
  function: name, provided-by, called-by, args, return type, and timeout/failure behavior. Both sides are
  hand-written *against* this table, not against each other's code.
- **Fail predictably on every call**, per §7 below — a function that can't produce a real answer returns a
  documented fallback (zero-filled array, last-known-value-flagged-stale, safe-state ack) rather than
  hanging the caller, since `Bridge.call` is synchronous.
- **Validate at the boundary** still applies to the one place this project does have a real wire format —
  the LoRa uplink payload parsed by `web/ingest`, which already validates before writing to Supabase; hold
  that boundary to the same standard, unrelated to the Bridge's function-call shape.
- The **LoRaWAN OTAA/AES-128** link and **`web/ingest`→Supabase RLS** remain separate trust boundaries,
  already covered by existing backend ADRs — the Bridge itself is a physically-local, same-board link and
  doesn't need its own crypto, just the failure-behavior discipline above.
- **Authenticate what's claimed secure, completely.** LoRaWAN OTAA/AES-128 covers the node↔gateway hop;
  don't let that create a false sense that the whole chain is secured — `web/ingest`→Supabase and the
  dashboard's RLS are separate trust boundaries already covered by existing backend ADRs; the Bridge
  itself is a physically-local link (same board) and doesn't need its own crypto, just the framing/
  validation above.

## 7. General judgment

- **State assumptions in the code or the ADR, not just in your head.** The ~300–500 mW average-draw
  estimate and the resulting 10–17 day autonomy figure are *assumptions*, not measured facts — say so in
  `KNOWN_GAPS.md` until Day 3-Aug's bench power measurement replaces them with a real number.
- **Fail predictably, everywhere.** Battery-low → documented safe state (already scheduled, Day 6
  hardening). LoRa dropout → retry with backoff, not silent data loss. Sensor read failure → zero-filled
  window + logged event, not a crash. A field node that clearly reports "geophone read failing, running on
  acoustic only" is worth infinitely more than one that silently drops seismic detection.
- **Measure before claiming, in the docs that will be judged.** If the Robu/Hackster write-up says
  "reduces false triggers by Nx" or "Xdays of autonomy," that number must come from an actual bench log,
  not an estimate dressed as a result — judges and any Qualcomm/Edge Impulse/Arduino reviewer will read
  confident, unverified numbers as the first sign of a project that's more pitch than substance.
- **Don't hand-copy the same formula twice.** The fusion math and the bandit's reward function each exist
  in exactly one place (Python, on the MPU); if a simulator or test harness needs the same formula, import
  it, don't retype it.

## 8. Working an AI-assisted build session (Opus plans, Sonnet builds)

- **Every session opens by reading `CONTEXT.md` + this file** — never assume carry-over from a prior
  session; state size and cost make re-deriving context from scratch the correct default, not a shortcut
  taken under pressure.
- **Opus is for the boundary, not the loop.** Call it once per module boundary to produce a short spec —
  the RPC schema, a module's public function signatures, the test plan for one piece of pure-core math —
  not once per day and never to write implementation code. Its output is a page, not a PR.
- **Sonnet builds against that spec, one `BUILD_BLUEPRINT_AUG8.md` schedule row at a time.** Scope every
  session to the exit criteria already written in that table — never "build the whole firmware." Load only
  the module being touched; if a wider search across the repo is genuinely needed, that's what the Explore
  subagent is for, not pulling the whole tree into context.
- **Non-obvious decisions get written down, not just coded.** If a session makes a call that isn't a
  direct instruction from the spec (a threshold value, a library choice, a fallback behavior), it adds a
  line to the relevant ADR or `KNOWN_GAPS.md` before moving on — that's the check that the reasoning was
  sound, not just that it compiled.
- **No attribution, ever** — restated because it's the rule most likely to leak in by default from tooling,
  not because it's new: no assistant mentions in commits, comments, docstrings, or docs.
- **You review every diff before it's committed.** An agent session moving fast through a 13-day schedule
  is exactly when a giant file, a skipped layer, or an untested pure function creeps in — catching it at
  diff-review time is cheaper than catching it during the field test.
