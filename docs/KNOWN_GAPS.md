# Known gaps

Deferred items surfaced while building `device/mcu` and `device/mpu` against
`device/mpu/bridge/schema.md` (`docs/BUILD_BLUEPRINT_AUG8.md` §8 build-calls 1–2). One line each:
what's deferred, severity, effort, status. Nothing here blocks either build call's own exit
criteria — see each entry's status.

- **No PlatformIO board support for the UNO Q; `pio` is host-only.** Medium severity, small effort
  to keep understood (banner comments already in place). See ADR 0010. Status: resolved by design,
  not a defect — flashing goes through App Lab + `scripts/sync-to-board.sh` only.
- **Bench stomp-test trigger log not yet captured.** High severity — this is Rung 1's actual proof
  criterion. Effort: one bench session (wiring already documented in `device/mcu/README.md`).
  Status: **pending hardware.** The procedure is shipped; it has not been run.
- **Whether `Wire` or `Wire1` maps to I2C2 (D20/D21) on this core is unverified on hardware.**
  `config.h`'s `GEOPHONE_I2C_BUS` defaults to `Wire` with a comment saying so. High severity (wrong
  bus means the geophone never reads), cheap to resolve at the same bench session as the stomp
  test. Status: open.
- **Whether USART1 (D0/D1) is free or claimed by the sketch console is unverified.** `config.h`'s
  `LORA_SERIAL` defaults to `Serial1` with a comment saying so. High severity (wrong port strands
  the LoRa join), same bench session to resolve. Status: open.
- **Horn/LED/IR burst-cap and cooldown values are provisional.** ADR 0003 mandates a cap and a
  cooldown but names no numbers; `HORN_BURST_MAX_MS`, `HORN_COOLDOWN_MS`, `HORN_GAIN_MAX_PCT`,
  `LED_BURST_MAX_MS`, `LED_COOLDOWN_MS`, `IR_PULSE_MAX_MS`, `IR_MIN_INTERVAL_MS` are this session's
  engineering judgement, not measured values. Medium severity. Status: open, pending field/bench
  tuning.
- **`STA_SAMPLES`, `STA_LTA_TRIGGER_RATIO`, `STA_LTA_DETRIGGER_RATIO` (`config.h`) are generic
  STA/LTA convention values**, carried over from standard seismic-trigger practice (25-sample
  short window, 250-sample long window, 4.0x trigger / 1.5x detrigger). They have **not** been
  validated against the elephant footfall-frequency research ADR 0001 cites, and no bench data
  backs them — in particular, whether a 0.1 s STA window actually resolves the cited footfall band
  has not been checked. High severity — these are the numbers that decide whether the node
  triggers at all. Effort: one calibration pass once real stomp-test traces exist. Status: open,
  blocks nothing in this build call but blocks trusting Rung 1's result once it lands.
- **`HORN_AMP_ENABLE_DELAY_MS = 150` (`config.h`) is invented — no measured DFPlayer Mini
  trigger-to-audio-seek latency backs it.** `horn.cpp`'s fire sequence depends on this value being
  long enough to cover DFPlayer seek (avoiding a pop) but not so long it clips the start of the
  deterrence clip. Medium severity. Effort: bench measurement with an oscilloscope or audio
  capture across a range of trigger-to-`AMP_ENABLE` delays. Status: open.
- **`drive_horn`'s `gain_pct` clamp is acknowledged but not yet wired to a physical volume
  control.** `horn.cpp` clamps and acks `gain_pct` via `rule_gate_apply()`, but nothing today
  actually varies DFPlayer output volume or amp gain by that percentage — the horn always plays at
  whatever level the DFPlayer's stored default is. Medium severity (an out-of-range gain is
  correctly rejected/clamped, but an in-range one has no real effect yet). Effort: needs a
  DFPlayer serial-command volume-set path (UART, not the GPIO trigger this session wired), or
  dropped from the contract if hardware can't support it. Status: open.
- **`drive_led`/`pulse_ir`'s internal `gain_pct` representation doesn't match the Bridge schema's
  wire args.** `schema.md` specifies `drive_led(pattern_id: uint8, duration_ms)` and
  `pulse_ir(duration_ms)` — neither carries a `gain_pct` field, but `led.cpp`/`ir.cpp` (this
  session's MCU-internal implementation) clamp and drive a `gain_pct`-shaped PWM duty cycle
  because `config.h`'s `LED_GAIN_MAX_PCT`/`IR_GAIN_MAX_PCT` already existed when those files were
  written. The Bridge wrapper (not built this session, see below) will need to either map
  `pattern_id` onto a fixed internal gain/channel choice, or the schema needs a documented default
  gain for these two calls. Medium severity — a real mismatch, not just an open question. Effort:
  small, needs a decision recorded (schema update or wrapper-side mapping) before Bridge wiring.
  Status: open.
- **AT command syntax and response strings in `lora/mac.cpp` are unverified against the source
  manual.** The file cites Seeed's *Grove LoRa-E5 AT Command Specification* but was written from
  memory of typical AT-command LoRaWAN modems, not checked line-by-line against it. Every command
  is marked `// UNVERIFIED against AT manual` inline. High severity — an unverified token fails
  the join silently on real hardware. Effort: one read-through of the manual against the file.
  Status: open, must be resolved before the first real join attempt.
- **LTA window length is bounded by the 2.048 s bench window (`SEISMIC_WINDOW_SAMPLES = 512` at
  250 SPS).** The LPBAM swap (ADR 0009) that replaces the ADS1115 stand-in should revisit whether
  a longer buffer is worth the SRAM cost once the internal-ADC path exists. Medium severity.
  Status: open, deferred to the LPBAM swap.
- **Bridge `provide()` registration is deliberately not wired up in this build call.**
  `DEVICE_DEVELOPMENT_WORKFLOW.md` §3 documents a live, reproducible bug where registering an
  extra `Bridge.provide()` function — a `float`-argument one specifically — broke every previously
  working function on the same sketch. `drive_horn`, `drive_led`, `pulse_ir`, and the cached
  state struct behind `get_system_state` exist as callable MCU-side functions with schema-matching
  shapes, but none are registered with `Bridge.provide()` yet. High severity by design — add one
  function at a time on real hardware, testing between each, not as a batch from a host build.
  Status: open, intentionally deferred to a hardware session.
- **Grove E5 join is untested; the SenseCAP gateway still ships EU868 and must be set to IN865
  first.** High severity (868 MHz is illegal to operate in India — CONTEXT.md §8). Status: open,
  tracked from ADR 0002.
- **ADR 0008's µA-idle / autonomy figures remain unmeasured assumptions**, not bench-verified
  power draws. Medium severity. Status: open.
- **GNSS → Bridge → dashboard forum thread** (`DEVICE_DEVELOPMENT_WORKFLOW.md` §3) — carried
  forward as a reference link, not yet acted on. Low severity. Status: open.
- **Geophone damping resistor (1 kΩ, ADR 0001 addendum) is calculated and documented but not yet
  wired or bench-verified.** Without it the SM-24's h=0.25 open-circuit damping will ring at its
  10 Hz resonance after every stomp, which could distort or duplicate `[trigger]` events during
  Rung 1. High severity — resolve in the same bench session as the stomp test, before trusting its
  results. Status: open, pending hardware.
- **INA333 (Rajiv Electronics module) `REF` pin bias is unconfirmed.** The board's own listed
  interfaces omit `REF`, though the INA333 IC always has one. If it's internally tied to GND
  rather than a mid-supply bias, the geophone's AC signal clips on its negative half. Check by
  shorting `IN+`/`IN-` and measuring `OUT` against `GND` — ~VCC/2 is correct, ~0V is not. High
  severity (silently corrupts every reading if wrong, no error, just a bad waveform). Status:
  open, pending hardware, resolve before trusting any bench signal from this front-end.
- **Lightning/ESD clamp protection for the geophone's buried cable run is deferred**, not decided.
  A small TVS/clamp across the INA333 differential input pair is worth adding before DFO field
  deployment; not required for bench testing. Low severity now, revisit before burial. Status: open.

## Build-call 2 (`device/mpu` scaffold)

- **Ping bench round trip written but not run.** `device/mpu/bench/ping/` (sketch + Python side) is
  complete and documented (`device/mpu/README.md`), but has not been pushed to or run on real
  hardware. High severity — this is the build call's own exit criterion for proving the MCU→MPU
  Bridge direction at all. Effort: one bench session (board reachable over SSH, `rsync` push,
  build/run from App Lab). Status: **pending hardware.**
- **MCU→Python Bridge `call()` direction is what ping proves, not the `notify()` direction the real
  schema functions use.** Rung 0 proved Python→MCU only (stock Blink LED). Ping deliberately uses
  `Bridge.call()` rather than `Bridge.notify()` — a `call` gets a verifiable `pong` reply, which is
  the better bench test than a fire-and-forget `notify` that gives no positive confirmation of
  receipt. `report_footfall_event`, `report_acoustic_event`, and `report_system_status` (the real
  MCU→MPU functions, all `notify` targets) plausibly share the same underlying
  registration/dispatch path as `call` targets, but that is an assumption ping does not prove
  outright. A green ping result should read as "MCU→MPU `call()` direction confirmed, `notify()`
  direction still inferred," not as "MCU→MPU closed." High severity — this distinction matters
  before trusting the real schema functions to work purely because ping worked. Status: open,
  pending a hardware session that specifically exercises `notify()`.
- **App Lab Python entrypoint idiom, `app.yaml`'s field names, and the C++ `Bridge.call()` result
  API are written from `DEVICE_DEVELOPMENT_WORKFLOW.md` §3's description, not checked line-by-line
  against a real App Lab-generated App.** Each is marked `// UNVERIFIED` / `# UNVERIFIED` inline in
  `device/mpu/bench/ping/`. High severity for the ping bench specifically (a wrong guess here fails
  the bench, not the real schema) but does not block anything else. Status: open, resolve at the
  same bench session as the ping run.
- **`ack: bool` on `drive_horn`/`drive_led`/`pulse_ir` is lossy for what the contextual bandit will
  need.** `bridge/schema.md` documents the ack as reporting whether the (possibly clamped) values
  actually fired, but types it `bool` — the bandit's never-repeat / stop-on-retreat logic
  (`cognition/`, not yet built) needs to know *which* clamped duration/gain actually fired, not just
  that something did. Medium severity — a real mismatch between the schema's stated intent and its
  wire type, not just an open question. Effort: small, needs a schema decision (richer return type,
  or a follow-up `get_system_state` read to recover the actual values) before `cognition/` lands.
  Status: open.
- **`MPU_WAKE_HOLD_S = 30.0` (`services/config.py`) is invented — no measured suspend/resume or
  fusion-latency data backs it.** ADR 0008's own open bench items don't cover this either. Medium
  severity. Effort: bench measurement of real MPU wake/suspend timing once ADR 0008's hardware
  lands. Status: open.
- **Board Python version is unverified; `pyproject.toml` targets `py311`** (assumed Debian 12
  bookworm, per the QRB2210's documented OS). If the board ships an older Python, `bridge/rpc.py`'s
  use of `enum.StrEnum` (3.11+) would need to fall back to `class AcousticClass(str, Enum)`. Medium
  severity, cheap to confirm (`python3 --version` over SSH). Status: open, resolve at the same bench
  session as the ping run.
- **`bridge/rpc.py` has no `Bridge.provide()`/`Bridge.call()` wiring, deliberately.** Mirrors the
  existing MCU-side entry point (`device/mcu/src/main.cpp`) — same `DEVICE_DEVELOPMENT_WORKFLOW.md`
  §3 registration bug is the reason on both sides. High severity by design — add one function at a
  time on real hardware, testing between each, not as a batch of seven from a host build. Status:
  open, intentionally deferred to a hardware session.
- **Edge Impulse projects (footfall, acoustic, vision) are created manually via Studio's own UI; no
  project IDs are recorded in-repo.** Not part of this build call's scope. Low severity. Status:
  open, tracked for a future session.

## Build-call 3 (`device/mpu/perception` vision capture)

- **Whether the UNO Q's USB-C port enumerates a USB host device at all while powered from VIN is
  unverified.** The whole camera path (ADR 0001, CONTEXT.md §3) rests on this and nothing in-repo
  confirms it; `hardware/references/UNO_Q_PINOUT_REFERENCE.md` only notes a `VBUS_DISABLE` signal on
  the USB-C connector, not host-mode behavior under VIN power. High severity — blocks the entire
  vision capture module if false. Effort: `lsusb` and `ls /dev/video*` over SSH with the camera (via
  the spare USB hub, `hardware/bom/procurement-status.md`) attached. Status: open, pending hardware.
- **Exact V4L2 device path is unverified.** `services/config.py`'s `CAMERA_DEVICE` defaults to
  `/dev/video0`, a guess — UVC devices commonly expose a second metadata-only node alongside the
  real capture node, and the index isn't guaranteed once a USB hub is in the path. Medium severity
  (wrong path fails `Camera.open()` loudly, not silently). Effort: resolved by
  `bench/camera_check/capture_check.py --probe`. Status: open, pending hardware.
- **IMX462 default resolution/pixel-format/FPS are unverified for this specific unit.**
  `services/config.py`'s `CAMERA_FRAME_WIDTH/HEIGHT` (1920x1080) and `CAMERA_PIXEL_FORMAT` (MJPG)
  are taken from the product listing (B0CQ4QDCXN) and general UVC-bandwidth reasoning, not a queried
  V4L2 format list. Medium severity. Effort: resolved by the same `--probe` run above. Status: open,
  pending hardware.
- **`python3-opencv` (or equivalent) presence on the board's Debian image is unverified.**
  `perception/camera.py`'s only real dependency; nothing in this build call confirms it ships on the
  QRB2210's default image. Medium severity — if absent, `Camera.open()` fails at import time on the
  board specifically. Effort: `python3 -c "import cv2"` over SSH. Status: open, pending hardware.
- **Night/IR performance is entirely unmeasured.** The IMX462's auto IR-cut switch behavior, actual
  exposure under 940 nm illumination, and whether `CAMERA_WARMUP_FRAMES` is enough for AE/AGC to
  settle in darkness are all unknown — this build call is daylight/bench capture only, no IR
  illuminator coordination (that needs `pulse_ir()`, not wired up; see below). High severity for
  CONTEXT.md's ">70% of raids are nocturnal" requirement, but explicitly out of this call's capture-
  only scope. Status: open, deferred to a later build call once `pulse_ir()` is registered.
- **`CAMERA_WARMUP_FRAMES`, `CAMERA_BURST_FRAMES`, and `CAMERA_BURST_INTERVAL_S`
  (`services/config.py`) are invented values**, not backed by measured AE-settle time or any
  detector-side timing requirement. Medium severity. Status: open, revisit once the vision detector
  (future build call) has a real inference-latency budget to size the burst against.
- **`bench/camera_check/capture_check.py` is written and host-tested against a fake capture device,
  but has not been run against the real IMX462** — neither on the board nor on a dev host with
  OpenCV installed. High severity — this is the build call's own exit criterion for proving real
  frames come off the real camera. Status: **pending hardware.**
- **Capture and IR illumination are not coordinated, by design.** `pulse_ir()` exists as an MCU-side
  Bridge stub (`device/mpu/bridge/rpc.py`) but is unregistered on both sides (same
  `Bridge.provide()` batch-registration caution as `bridge/rpc.py`'s other stubs). Night capture will
  eventually need capture windows aligned to an IR pulse, but `perception/camera.py` deliberately
  has no dependency on `Bridge` at all — wiring that coordination is later build-call scope, once the
  ping bench proves the Bridge round trip works at all. Medium severity. Status: open, deferred by
  design.

## Build-call 4 (`device/mpu/cognition` fusion math)

- **Fusion weights (`WEIGHT_SEISMIC`/`WEIGHT_ACOUSTIC`/`WEIGHT_VISION`, `cognition/config.py`) have
  a justified ordering but invented magnitudes.** The ordering (vision > seismic > acoustic) follows
  from ADR 0001's Consequences section (seismic-alone ~70–75%, vision-alone ~70–85% standalone field
  accuracy) and ADR 0007/0009 scoping acoustic as corroboration only, never standalone presence
  detection — but the actual numbers (1.5/1.2/0.6) are round values chosen to preserve that ordering,
  not a fit against real data. High severity — these set every fused probability. Effort: a
  calibration/fitting pass once a labelled multi-modal field dataset exists (ADR 0001 already lists
  this as a v2 item, not a launch requirement). Status: open.
- **Per-modality baselines (`BASELINE_SEISMIC`/`BASELINE_ACOUSTIC`/`BASELINE_VISION`,
  `cognition/config.py`) are uniform and invented.** All three are `logit(0.10)`, an assumed 10%
  background/false-positive rate with no per-modality measurement behind it — no bench or field data
  differentiates them yet. Medium severity. Status: open, pending real trigger-rate data per
  modality.
- **`L_PRIOR` (`cognition/config.py`, -1.0) is invented.** It is meant to be the log-odds of
  "elephant" conditioned on an MCU event having already fired, but no real trigger-to-elephant rate
  has ever been measured (no field deployment yet) — the value encodes an engineering judgement
  (most STA/LTA crossings are not elephants) documented in the constant's own rationale comment, not
  a derived number. Medium severity. Status: open.
- **The fused probability `P` is not a calibrated probability and must not be presented as one.**
  ADR 0001's 70–75%/70–85% figures are per-modality field-accuracy *expectations*, not inputs that
  have been formally propagated through this fusion formula — `P` should not be quoted as a
  calibrated confidence number in contest or DFO material until real labelled events validate it.
  Status: open, informational.
- **No decision/alert threshold on `P` exists yet, deliberately.** `cognition/config.py`'s own
  docstring states why: no consumer exists (the contextual bandit and alert-escalation logic are
  both future build calls), and any real threshold needs the field-accuracy figures above, not an
  invented cutoff picked before they exist. Status: open, scoped to a future build call.
- **Nothing yet converts a real sensor reading into the log-odds `fuse()` expects.** No code turns
  `report_footfall_event`'s `probability` field, `report_acoustic_event`'s `confidence` field, or a
  vision detector's output (not yet built) into a `ModalityReading`'s `log_odds`/`available` pair —
  `cognition/fusion.py`'s `logit()` is the intended conversion primitive, but nothing calls it yet.
  High severity — this is the actual integration gap between the Bridge and cognition layers.
  Status: open, scoped to the Bridge-wiring build call.
- **ADR 0001 §6's two fusion limitations are accepted approximations, not resolved.** Correlated
  noise across modalities (rain/fog degrading seismic SNR and vision IR contrast together) and the
  MCAR assumption behind availability-gated dropout (vision being unavailable due to fog is
  plausibly not independent of elephant activity) are both restated in `cognition/fusion.py`'s
  module docstring so a code reader sees them without opening the ADR — see ADR 0001 for the full
  reasoning. Status: open, tracked as future work, not a launch blocker per the ADR.
