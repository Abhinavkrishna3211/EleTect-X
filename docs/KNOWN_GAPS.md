# Known gaps

Deferred items surfaced while building `device/mcu` and `device/mpu` against
`device/mpu/bridge/schema.md` (`docs/BUILD_BLUEPRINT_AUG8.md` §8 build-calls 1–2). One line each:
what's deferred, severity, effort, status. Nothing here blocks either build call's own exit
criteria — see each entry's status.

- **No PlatformIO board support for the UNO Q; `pio` is host-only.** Medium severity, small effort
  to keep understood (banner comments already in place). See ADR 0010. Status: resolved by design,
  not a defect — flashing goes through App Lab + `scripts/sync-to-board.sh` only.
- **Bench stomp-test trigger log — captured 2026-08-14.** Rung 1's actual proof criterion, run
  against real hardware on a lean field-flag build. Quiet floor held ratio 1.03-1.13 across ~89 s
  (before and after the stomp, no false triggers); a firm human stomp near the geophone produced
  `ratio=4.60`, with a `[window]` raw-volts CSV dump confirming a genuine ~65x amplitude transient
  over the noise floor. `STA_LTA_TRIGGER_RATIO` (4.0) clears the observed floor ceiling by ~3.5x and
  the stomp clears the threshold by ~15% margin. Full derivation, including the real sample-rate
  math and why `STA_LTA_DETRIGGER_RATIO` could not be validated the same way, is in this document's
  "STA/LTA field-flag rate re-measurement and real stomp-test calibration" entry near the end.
  Status: **closed.**
- **Whether `Wire` or `Wire1` maps to I2C2 (D20/D21) on this core — resolved 2026-08-14.** `Wire`
  is correct, confirmed from the board's own generated devicetree rather than inferred from
  behavior: the `arduino:zephyr` core declares `Wire`/`Wire1`/... in the order listed by the board
  overlay's `zephyr,user { i2cs = <&i2c2>, <&i2c4>, <&i2c3>; }`
  (`arduino_uno_q_stm32u585xx.overlay`) — i2c2 is first, so it's `Wire`, not `Wire1` (which binds to
  i2c4, the Qwiic connector). The generated `zephyr-arduino_uno_q_stm32u585xx.dts` shows i2c2's
  `pinctrl-0` is `i2c2_scl_pb10`/`i2c2_sda_pb11` and the node is aliased `arduino_i2c` — an exact
  match for `config.h`'s documented PB10/PB11 pins. `config.h`'s comment is updated. Status:
  **closed.**
- **Whether USART1 (D0/D1) is free or claimed by the sketch console is unverified.** `config.h`'s
  `LORA_SERIAL` defaults to `Serial1` with a comment saying so. High severity (wrong port strands
  the LoRa join), same bench session to resolve. Status: open.
- **Horn/LED/IR burst-cap and cooldown values are provisional.** ADR 0003 mandates a cap and a
  cooldown but names no numbers; `HORN_BURST_MAX_MS`, `HORN_COOLDOWN_MS`, `HORN_GAIN_MAX_PCT`,
  `LED_BURST_MAX_MS`, `LED_COOLDOWN_MS`, `IR_PULSE_MAX_MS`, `IR_MIN_INTERVAL_MS` are this session's
  engineering judgement, not measured values. Medium severity. Status: open, pending field/bench
  tuning.
- **`STA_SAMPLES`, `STA_LTA_TRIGGER_RATIO` (`config.h`) — checked against real hardware, 2026-08-14,
  values kept unchanged.** `STA_SAMPLES=25`/`LTA_SAMPLES=250` were sized assuming
  `SEISMIC_SAMPLE_RATE_HZ=250`; the real measured rate on a lean field-flag build is **226.98 Hz**
  (not the nominal 250), which puts the two windows at ~110 ms and ~1.10 s of real elapsed time —
  both still land inside the literature targets (STA ≈40-150 ms, LTA ≥0.5 s per Wijayakulasooriya et
  al. arXiv:2406.05140 and Trnkoczy/Güralp STA/LTA sizing guidance), so no retune was justified by
  this check. `STA_LTA_TRIGGER_RATIO=4.0` was then validated against a real human stomp test (see
  the "Bench stomp-test trigger log" entry above and the full derivation entry near the end of this
  document): quiet floor 1.03-1.13, real stomp 4.60, both constants left numerically unchanged
  because the real data confirmed rather than contradicted them. `STA_LTA_DETRIGGER_RATIO` was a
  separate item, confirmed by `grep` to be dead code (referenced nowhere outside its own `#define`;
  `state_machine.cpp`'s `kEvent` state only exits on `EVENT_MAX_MS` elapsed, no ratio-based detrigger
  check exists anywhere) — since removed entirely (15 Aug, see the "`kSensing` redundant STA/LTA
  re-run..." entry near the end of this document) rather than kept as an unwired placeholder. Status:
  **closed** for all three — `STA_SAMPLES`/`STA_LTA_TRIGGER_RATIO` validated and kept, `STA_LTA_
  DETRIGGER_RATIO` removed as dead code — see the "Literature review" section near the end of this
  document for the wider scientific grounding and the honest scope line between STA/LTA tuning and
  true multi-species classification.
- **`HORN_AMP_ENABLE_DELAY_MS = 150` (`config.h`) is invented — no measured DFPlayer Mini
  trigger-to-audio-seek latency backs it.** `horn.cpp`'s fire sequence depends on this value being
  long enough to cover DFPlayer seek (avoiding a pop) but not so long it clips the start of the
  deterrence clip. Medium severity. Effort: bench measurement with an oscilloscope or audio
  capture across a range of trigger-to-`AMP_ENABLE` delays. Confirmed 15 Aug: the horn is not yet
  wired to the board at all, so this cannot be bench-measured until wiring exists — the fire-test
  harness (see its own entry below) is ready to drive the measurement once it does. Status: open.
- **`drive_horn`'s `gain_pct` clamp is acknowledged but not yet wired to a physical volume
  control.** `horn.cpp` clamps and acks `gain_pct` via `rule_gate_apply()`, but nothing today
  actually varies DFPlayer output volume or amp gain by that percentage — the horn always plays at
  whatever level the DFPlayer's stored default is. Medium severity (an out-of-range gain is
  correctly rejected/clamped, but an in-range one has no real effect yet). Effort: needs a
  DFPlayer serial-command volume-set path (UART, not the GPIO trigger this session wired), or
  dropped from the contract if hardware can't support it. Status: open.
- **`drive_led`/`pulse_ir`'s internal `gain_pct` representation doesn't match the Bridge schema's
  wire args — resolved, decision recorded.** `schema.md` specifies `drive_led(pattern_id: uint8,
  duration_ms)` and `pulse_ir(duration_ms)` — neither carries a `gain_pct` field, but
  `led.cpp`/`ir.cpp` clamp and drive a `gain_pct`-shaped PWM duty cycle because `config.h`'s
  `LED_GAIN_MAX_PCT`/`IR_GAIN_MAX_PCT` already existed when those files were written. Decision:
  option (a) — `schema.md` now documents (see its "Actuator gain defaults" section) that both
  calls always drive at their `config.h` max internally; `pattern_id`/`duration_ms` stay the only
  wire args. Rejected option (b) (mapping `pattern_id` onto a fixed gain choice) because `pulse_ir`
  has no `pattern_id` to map from and would need an identical fixed default anyway, and because
  gain and channel are separate axes that don't belong conflated onto one field. Superseded by, and
  now consistent with, the Bridge wrapper's actual implementation — see the `bridge_handlers.h/.cpp`
  entry below, which already made this same call in code before it was written down here. Status:
  closed.
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
- **`loop()` has no task/priority separation, so an actuator fire stalls sensing.** `horn.cpp`'s
  fire sequence blocks on `delay()` for up to `HORN_BURST_MAX_MS` (3000 ms) plus the amp-enable
  delay; `led.cpp`/`ir.cpp` block for their own `duration_ms`. Because `main.cpp`'s `loop()` calls
  `geophone_service()` and `lora_service()` sequentially after the actuator call returns, both are
  starved for up to ~3.15 s during every horn fire — a geophone sample or an incoming LoRa frame in
  that window is silently missed, not queued. Not caused by this session's fire-test harness (see
  `docs/specs/mcu-fire-test-harness.md`), which surfaces the same pre-existing blocking behavior
  rather than introducing it. High severity if a real elephant event and a deterrence burst overlap
  in time — exactly the case that matters most. Effort: either move sensing to a higher-priority
  Zephyr thread (real RTOS tasks are available under Arduino Core on this board, just unused so far)
  or make the actuator fire non-blocking (state-machine-driven timing instead of `delay()`). Status:
  open, not scheduled before Aug 20 — flagged so the Aug-20 trial's data is read with this caveat,
  not treated as a silent gap.
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
- **Geophone damping resistor (1 kΩ, ADR 0001 addendum) — physically verified on hardware,
  2026-08-16, closed.** Without it the SM-24's h=0.25 open-circuit damping would ring at its 10 Hz
  resonance after every stomp, distorting or duplicating `[trigger]` events. Checked directly on
  the bench, not inferred: confirmed a 1 kΩ resistor wired directly across the SM-24's own two
  leads, before the burial cable, per `device/mcu/README.md`'s wiring section — plus the separate
  1 kΩ series input-protection resistors in each leg between the damping-resistor node and the
  INA333's `VIN+`/`VIN-` inputs, also present as documented. Corroborating, not primary, evidence:
  the 15 Aug 12-stomp protocol's trigger data was tight and single-peaked (mean ratio 4.232, stdev
  0.166, n=11 — see this document's "Multi-trial stomp validation protocol" entry) with no sign of
  the post-stomp ringing/envelope-smearing an undamped h=0.25 SM-24 would be expected to produce;
  the physical check above, not this data, is the primary evidence for closure. Status: **closed**.
- **INA333 (Rajiv Electronics module) `REF` pin bias — checked against real hardware, 2026-07-30,
  closed.** The board's own listed interfaces omit `REF`, though the INA333 IC always has one; had
  it been internally tied to GND rather than a mid-supply bias, the geophone's AC signal would clip
  on its negative half. Status: **closed** — see the "Build-call 5" section's first entry near the
  end of this document for the full derivation (`[bias-check] raw≈26890 volts≈1.6806V`, stable
  across multiple readings) and `device/mcu/README.md`'s "Result (2026-07-30)" line.
- **Lightning/ESD clamp protection for the geophone's buried cable run is deferred**, not decided.
  A small TVS/clamp across the INA333 differential input pair is worth adding before DFO field
  deployment; not required for bench testing. Low severity now, revisit before burial. Status: open.
  Partially, cheaply mitigated as of 30 Jul: 1 kΩ series resistors now sit between the damping-
  resistor node and the INA333's `IN+`/`IN-` inputs (ADR 0001 addendum, `device/mcu/README.md`) —
  current-limiting only, does not clamp voltage or absorb real surge energy, so this line item
  stays open until an actual TVS/clamp is added.

## Build-call 2 (`device/mpu` scaffold)

- **Ping bench round trip written but not run.** `device/mpu/bench/ping/` (sketch + Python side) is
  complete and documented (`device/mpu/README.md`), but has not been pushed to or run on real
  hardware. High severity — this is the build call's own exit criterion for proving the MCU→MPU
  Bridge direction at all. Effort: one bench session (board reachable over SSH, `rsync` push,
  build/run from App Lab). Status: **pending hardware.**
- **MCU→MPU Bridge `notify()` direction — the direction the real schema functions
  (`report_footfall_event`, `report_acoustic_event`, `report_system_status`) actually use — is now
  confirmed working on real hardware. `call()`'s synchronous-reply direction is not, and the two are
  not interchangeable evidence.** This flips the original framing of this entry: ping
  (`device/mpu/bench/ping`) was written to prove `call()` first, on the theory that a verifiable
  `pong` reply is a better bench test than a fire-and-forget `notify` — but ping has still never
  been run against hardware (see the bullet above, unchanged, still "pending hardware"). `notify()`
  ended up proven first instead, via an unrelated path: Build-call 5's `SEISMIC_DEBUG_STREAM_RAW`
  Bridge-relay work sent real `Bridge.notify()` calls from `device/mcu/src/geophone.cpp` to a
  `Bridge.provide()` handler in `device/mpu/main.py` and confirmed live samples arriving on
  2026-07-31 (see that section below for the full verification). Per `Arduino_RouterBridge`'s own
  `bridge.h`, `call()` and `notify()` are genuinely distinct code paths — `call()`'s `RpcCall::
  result()` blocks on a reply, `notify()`'s one-way `client->notify()` never does — so a confirmed
  `notify()` does not imply `call()` also works; the MPU→MCU actuator functions (`drive_horn`,
  `drive_led`, `pulse_ir`, `get_system_state`), all `call` targets, remain unproven. High severity —
  this is the first hardware-confirmed channel the fusion/cognition layer has to build real MCU
  reporting on, but it covers only the MCU→MPU direction. Status: `notify()` direction closed
  (2026-07-31); `call()` direction still open, pending the ping bench actually running.
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
  the spare USB hub, `hardware/bom/procurement-status.md`) attached. **Partial pre-check done, 16
  Aug — the camera itself confirmed alive, the actual question still open.** Ran
  `bench/camera_check/capture_check.py --backend any` against the real IMX462 plugged directly into
  the dev Windows machine (no board, no hub, no VIN power involved) — it opened, negotiated
  1920x1080@30fps as requested, and captured real sharp in-focus frames (confirmed by eye: room
  detail, a person reaching toward the lens, not the washed-out blur an earlier lens-cover mixup
  produced). This proves the IMX462 unit itself is a working UVC device — it does **not** touch the
  actual open question here, which is specifically about the UNO Q's USB-C port acting as USB host
  while powered from VIN rather than USB-C dev power. That test still needs the board, the spare USB
  hub, and VIN power, exactly as this entry always specified. Status: open, pending hardware.
  **Second pre-check done, 17 Aug — still not the VIN test, but a real second data point.** SSH'd into
  the board (IMX462 → Portronics hub USB 3.0 port → hub's USB-C → UNO Q's USB-C port, board powered
  via the hub's "PD 3.0 \| DATA" port from a 45W charger — USB-C/PD power, explicitly **not** VIN).
  `lsusb` showed the camera (`0c45:6366 Microdia Webcam Vitade AF`) alongside the hub's own
  `1a86:8095` and `0bda:8152` (RTL8152) devices; six `/dev/video*` nodes appeared. This does **not**
  close this entry — VIN power is still unverified — but it does newly confirm the UNO Q's single
  USB-C port can act as a PD power sink and a USB host for a downstream device at the same time,
  which was itself an open question. Status: still open, pending the real VIN/battery-only test.
- ~~**Exact V4L2 device path is unverified.**~~ **Resolved, 17 Aug, on the real board — and the
  guess was wrong.** `v4l2-ctl --info` against all six `/dev/video*` nodes (camera wired via the
  Portronics hub, board on USB-C/PD power) shows: `/dev/video0` and `/dev/video3` are the QRB2210
  SoC's own `qcom-venus` hardware M2M video encoder/decoder (H.264/HEVC/NV12 only, `Video
  Memory-to-Memory Multiplanar` capability) — **not the camera at all**; confirmed by attempting an
  MJPG capture against `/dev/video0`, which was rejected outright (`The pixelformat 'MJPG' is
  invalid`). The real IMX462 (`uvcvideo`, "USB 2.0 Camera: USB Camera") exposes four nodes:
  `/dev/video1` (real capture: MJPG 1920x1080/1280x720/640x480/320x240 + YUYV 640x480/320x240, all
  @30fps) with `/dev/video2` as its paired metadata-only node, and `/dev/video4` (a second capture
  interface, H.264-only, unused by production's forced-MJPG config) with `/dev/video5` as its
  paired metadata node. Streamed a real frame off `/dev/video1` directly via
  `v4l2-ctl --stream-mmap --stream-to=` (no OpenCV needed) — a genuine 158096-byte JPEG, SOF marker
  confirms 1920x1080. `services/config.py`'s old `CAMERA_DEVICE = "/dev/video0"` default was
  therefore actively wrong on this unit — it pointed at the SoC's own hardware encoder, which
  fails every open/format-negotiation attempt, not the camera.
  **Follow-up action item resolved, same day.** A bare index was never going to be safe here
  regardless of which one was picked — confirmed by the reboot test below, where the raw indices
  genuinely reshuffled. Fixed `CAMERA_DEVICE` to the udev `/dev/v4l/by-id/` symlink instead:
  `/dev/v4l/by-id/usb-Arducam_Technology_Co.__Ltd._USB_2.0_Camera_SN0001-video-index0` (found via
  `ls -la /dev/v4l/by-id/` and `readlink -f`, keyed on the camera's own USB serial `SN0001`, not
  bus topology or enumeration order). Verified this exact path resolves to the correct capture
  node and opens/negotiates/captures correctly (a) immediately, (b) after a full board reboot, and
  (c) after a physical camera unplug/replug with the board left powered — see the new "Camera
  device-path robustness" entry below for the full verification. Status: **closed**, fixed in
  code.
- ~~**IMX462 default resolution/pixel-format/FPS are unverified for this specific unit.**~~
  **Resolved, 17 Aug, on the real board, via real V4L2 (not the 16 Aug DirectShow proxy).**
  `v4l2-ctl --list-formats-ext -d /dev/video1` confirms MJPG 1920x1080 @30fps is genuinely
  advertised by this unit (not just requested), and `v4l2-ctl --get-parm` on the same node reports
  `30.000 (30/1)` fps actually negotiated. A real frame streamed off `/dev/video1` at that setting
  came back as a valid 158096-byte JPEG whose own SOF marker reports 1920x1080 — matches
  `services/config.py`'s `CAMERA_FRAME_WIDTH/HEIGHT`/`CAMERA_PIXEL_FORMAT` defaults exactly, this
  time on the real V4L2 backend production actually uses, not DirectShow. Status: **closed**.
- ~~**`python3-opencv` (or equivalent) presence on the board's Debian image is unverified.**~~
  **Resolved, 17 Aug, on the real board — and the answer is no, it's absent.**
  `python3 -c "import cv2"` over SSH: `ModuleNotFoundError: No module named 'cv2'`. Also notable:
  `pip3` itself isn't on `PATH` either (`bash: pip3: command not found`) — this board's Python
  environment has neither cv2 nor a usable pip to install it ad hoc. `apt-cache policy
  python3-opencv` does show a real candidate (`4.10.0+dfsg-5`) is reachable, so `sudo apt install
  python3-opencv` should resolve it, but that hasn't been run — `perception/camera.py` will fail at
  import time on this board as it stands today. Confirmed knock-on effect: running
  `bench/camera_check/capture_check.py --backend v4l2 --probe` directly on the board dies at its
  top-level `import cv2` (line 44) before even reaching the `--probe` device listing — the script
  itself is fine, this board's environment just isn't ready for it yet.
  **Follow-up action item resolved, same day.** Ran `sudo apt install -y python3-opencv` on the
  board (candidate `4.10.0+dfsg-5`, pulled in the full `libopencv-*410` package set). Confirmed
  `python3 -c "import cv2"` now prints `4.10.0` with no error. Status: **closed**, fixed on the
  board.
- **`bench/camera_check/capture_check.py` now runs successfully end-to-end against the real
  IMX462, on the real board, through the production V4L2 `Camera` class — this build call's actual
  exit criterion, closed 17 Aug 2026.** With `CAMERA_DEVICE` fixed to the by-id path and
  `python3-opencv` installed, `python3 bench/camera_check/capture_check.py --backend v4l2 --probe`
  ran clean: `--probe` listed all six `/dev/video*` nodes and the by-id path's real format list;
  `Camera.open()` printed `Negotiated: device=/dev/v4l/by-id/...-video-index0 1920x1080
  fourcc=MJPG fps=30.0` — an exact match to `services/config.py`'s defaults; a single frame and a
  5-frame burst (`--frames` default) all saved as real JPEGs (300-500KB each, not empty/corrupt)
  to `output/`, with inter-frame intervals of ~28-32ms (consistent with the negotiated 30fps).
  Re-ran the identical command with no path changes after a full board reboot and again after a
  physical camera unplug/replug (see the robustness entry directly below) — both times it
  succeeded identically. Status: **closed**.
- **Camera device-path robustness across reboot and physical replug — verified 17 Aug 2026, and
  it's a good thing the by-id fix above landed first.** Two tests, both against the by-id
  `CAMERA_DEVICE` path with no code changes between runs:
  1. **Full board reboot** (`sudo reboot`, waited ~35s for SSH to come back). The by-id symlink
     kept resolving and `capture_check.py` succeeded identically — but the raw `/dev/videoN`
     index underneath it genuinely changed: before reboot the IMX462 held `/dev/video1/2/4/5`
     (SoC `qcom-venus` codec on `/dev/video0/3`); after reboot the IMX462 held
     `/dev/video0/1/2/3` (codec moved to `/dev/video4/5`) — `v4l2-ctl --info` confirmed driver
     identity on every node both times. This is a real, reproducible race between the UVC and
     `qcom-venus` drivers during boot probe, not a fluke — exactly the failure mode the by-id fix
     was chosen to survive, and it did.
  2. **Physical unplug/replug** (camera's USB cable pulled from the Portronics hub and reinserted
     into the same port, board left powered throughout). The by-id symlink kept resolving (target
     index also changed underneath it, video0 both before and after by coincidence this time —
     not to be relied on) and `capture_check.py` succeeded identically again.
  **dmesg findings, both events:** no USB errors, retries, or enumeration failures beyond one
  recurring benign quirk also present on the very first cold boot — `usb 1-1.2: 4:1: cannot get
  freq at ep 0x84`, 3× per (re)enumeration. This is a UVC audio-class (UAC) endpoint frequency
  query failing on the camera's unused microphone interface, not the video path; harmless but
  logged here since a device needing *any* retries to enumerate cleanly is worth tracking. The
  physical replug's own timing: `USB disconnect, device number 3` at dmesg timestamp 235.08s,
  `new high-speed USB device number 5` at 243.75s — an ~8.6s gap, attributable to the time it
  took to physically unplug and reinsert the cable by hand, not a driver retry/backoff delay (the
  re-enumeration itself, disconnect-to-UVC-found, was clean and fast once the cable was back:
  ~170ms from new-device to `Found UVC 1.00 device`). `services/config.py`'s new
  `CAMERA_OPEN_RETRIES`/`CAMERA_OPEN_RETRY_BACKOFF_S` (3 attempts, 2.0s backoff = up to 6s of
  patience) were sized with this ~8.6s figure in mind, though a single retry pass doesn't fully
  cover the observed gap — worth revisiting once more replug data points exist. Status: **closed**
  — by-id path confirmed robust to both tested disruption modes; VIN-power boot (the still-open
  entry above) remains the one disruption mode not yet covered.
- **`Camera.open()`/`capture_frame()`/`capture_burst()` had no retry or reconnect logic at all —
  reviewed 17 Aug 2026, partially fixed.** `perception/camera.py` is not yet wired into any real
  capture loop (`device/mpu/main.py` and `services/reflex_loop.py` have no camera/detector
  integration yet — `reflex_loop.py`'s own module docstring says as much: "no detector exists
  (perception/camera.py is capture-only)"), so there is no consuming code to inspect for
  recovery behavior; the only real caller today is `bench/camera_check/capture_check.py`. Within
  `Camera` itself: **fixed** — `open()` now retries up to `CAMERA_OPEN_RETRIES` times (default 3,
  2.0s backoff between attempts, both in `services/config.py`) before raising, since a device that
  isn't there yet at startup (hub still renegotiating, connector freshly reseated) is exactly the
  case a few spaced attempts can ride out; verified against real hardware (see the two entries
  above) and against new host tests (`tests/test_camera.py`:
  `test_open_retries_and_succeeds_after_transient_failure`,
  `test_open_gives_up_after_exhausting_retries`). **Deliberately left unchanged, and flagged here
  instead of silently deciding either way:** `capture_frame()` still returns `None` on a failed
  grab and `capture_burst()` still stops early on the first failed grab, both with zero retry —
  this was already an intentional, documented design choice in both methods' own docstrings (an
  honest "no frame" result, not a fabricated one) and this build call isn't changing that. What
  *is* a genuinely open design question: **there is currently no supervisory layer anywhere that
  would notice a camera going permanently dead mid-run (USB drops and never comes back) and
  attempt a full `close()`+`open()` recovery** — today that would just mean every subsequent
  `capture_frame()` call returns `None`/every `capture_burst()` returns `[]` forever, silently,
  until someone physically intervenes. This is squarely the future detector/reflex-loop
  integration's call to make (how many consecutive failures before it's "dead," whether recovery
  belongs in `Camera` itself or one layer up in whatever owns the capture loop), not something to
  decide unilaterally while that loop doesn't exist yet. **Recommendation for whoever builds that
  integration:** treat N consecutive `None`/empty-burst results as a signal to `close()` the
  `Camera` and construct+`open()` a fresh one (mirrors what `open()`'s own new retry loop already
  does internally on a fresh handle per attempt), with the failure surfaced (log/status field) so
  a prolonged outage is visible in the field, not just silently degraded. High severity given this
  is the main way field evidence (detection/deterrence footage) gets captured — a camera that goes
  quietly dead mid-deployment and never recovers defeats the mission. Status: open, deferred to
  the vision detector/reflex-loop build call.
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
  but has not been run successfully against the real IMX462** — the 16 Aug Windows/DirectShow run
  above got a real capture but not through the production `Camera` class's V4L2 path; **the 17 Aug
  on-board run got further but still didn't complete**: synced to the board and ran with
  `--backend v4l2 --probe`, but it dies at the top-level `import cv2` (script line 44) before
  reaching `Camera.open()`, because `python3-opencv` isn't installed on the board (see that entry
  above). The `--probe` path and everything past it (negotiated-format printout, single-frame and
  burst capture through `perception.camera.Camera`) remains genuinely unexercised — the equivalent
  V4L2-level facts got established by hand instead (`v4l2-ctl` directly, see the device-path and
  resolution/format entries above), which is real evidence at the V4L2 layer but does **not**
  substitute for actually exercising `perception/camera.py`'s own `Camera` class end to end. High
  severity — this is still the build call's own exit criterion. Status: **pending hardware** — needs
  `sudo apt install python3-opencv` on the board, then a re-run.
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
  invented cutoff picked before they exist. Status: **superseded, not closed** — a consumer now
  exists (`device/mpu/services/reflex_loop.py`'s `handle_footfall_event()`, this build call), and it
  needs a threshold to call `cognition/decision.py`'s `decide()` with. Rather than leave that call
  site without one, `reflex_loop.py` defines `ALERT_PROBABILITY_THRESHOLD = 0.5` itself — the fused
  probability's own uninformative midpoint, adding no additional skepticism or credulity beyond what
  `L_PRIOR` and the per-modality weights/baselines already encode — deliberately outside
  `cognition/config.py`, so that module's own documented refusal to hold this number stays true.
  This is still an invented placeholder, not the field-accuracy-derived value `cognition/config.py`
  describes; it must be revisited once real labelled events exist. Status: open, now scoped to
  `services/reflex_loop.py`'s `ALERT_PROBABILITY_THRESHOLD` constant specifically.
- **`report_footfall_event`'s `probability` and `feature_vector` are an honest placeholder, not the
  on-MCU TinyML model `device/mpu/services/reflex_loop.py`'s module docstring assumes exists
  (`config.h`'s `FOOTFALL_PROBABILITY_SATURATION_C`, `state_machine.cpp`/`footfall_features.cpp`,
  2026-08-14).** `ml/seismic/` is empty — only STA/LTA exists on the MCU today, so there is no trained
  model to produce a real `probability` or a real 8-feature `feature_vector` behind it. Rather than
  invent an unrelated number, `footfall_features.cpp` derives `probability` from `peak_ratio` via a
  saturating function anchored on the two real bench data points this project has (the quiet-floor
  ceiling ratio 1.13 and the real stomp ratio 4.60, both from the bench stomp-test entry above).
  **Originally `1 - exp(-k*(ratio-1))`; changed same day to `x^2/(x^2+c^2)` (`x = peak_ratio - 1`,
  `c = FOOTFALL_PROBABILITY_SATURATION_C = 1.2`)** — the exponential form does not link on the real
  board (`expf`'s `undefined reference to '__errno'` against `libm_nano.a`; full derivation in the
  "Raw seismic trigger data..." entry above), a failure invisible to `pio test -e native`'s host libc.
  The replacement needs only multiplication/division, no libm transcendental call, so no toolchain
  errno dependency; re-solved from the same stomp anchor (`c` chosen so `x^2/(x^2+c^2) = 0.9` at
  `x=3.60`) and checked, not independently fit, against the quiet-floor anchor (maps to ~0.012, even
  tighter than the exponential's ~0.08). `feature_vector` is populated with eight real per-window
  statistics (`sta`, `lta`, `peak_ratio`, `trigger_index`, window min/max/mean/population stdev)
  rather than zeros. Both are documented in `footfall_features.h`/`.cpp` as stand-ins, same labeling
  discipline as the `ALERT_PROBABILITY_THRESHOLD` entry directly above this one. Medium-high severity:
  every `report_footfall_event` the field trial produces carries this placeholder, not a real model
  confidence — any fusion/decision output downstream of it inherits the same caveat. Confirmed working
  end to end on real hardware, 2026-08-14 (see the log capture above) — `mcu_probability=0.865` for a
  real `sta_lta_ratio=4.040` tap, consistent with this formula. Status: open, pending `ml/seismic`'s
  not-yet-started TinyML model; the saturating-function shape and the eight chosen features are this
  session's engineering judgement, not a validated feature design.
- **The horn-only "request the wire protocol's max, let the MCU clamp" deterrence policy
  (`services/reflex_loop.py`'s `ALERT_HORN_GAIN_PCT=100.0`/`ALERT_HORN_DURATION_MS=65535`) is an
  invented placeholder standing in for the contextual bandit that is supposed to pick which
  actuator(s) to fire and at what gain/duration.** No bandit exists yet (`cognition/fusion.py`'s own
  module docstring names it as future work); rather than invent a specific mid-range gain/duration
  figure to fill that gap, `reflex_loop.py` requests the protocol's own documented maximum
  (`schema.md`'s 0–100 `gain_pct` range, `duration_ms`'s uint16 ceiling) and relies on
  `device/mcu/src/rule_gate.cpp`'s existing clamp against the MCU's real, separately-configured caps
  (`HORN_GAIN_MAX_PCT`/`HORN_BURST_MAX_MS`, `config.h`) to bring it down to something safe — avoiding
  a second, unreviewed limit invented on the MPU side. LED and IR are not driven by this loop at all.
  Medium-high severity: until the bandit exists, every alert gets the same maximal horn burst
  regardless of context (time of day, distance, repeat-trigger history), which is a real deterrence-
  policy gap, not just a config placeholder. Status: open, blocked on the same future bandit build
  call `cognition/fusion.py` already names.
- **Nothing yet converts a real sensor reading into the log-odds `fuse()` expects.** No code turns
  `report_footfall_event`'s `probability` field, `report_acoustic_event`'s `confidence` field, or a
  vision detector's output (not yet built) into a `ModalityReading`'s `log_odds`/`available` pair —
  `cognition/fusion.py`'s `logit()` is the intended conversion primitive, but nothing calls it yet.
  High severity — this is the actual integration gap between the Bridge and cognition layers.
  Status: **closed for seismic** —
  `device/mpu/services/reflex_loop.py`'s `handle_footfall_event()` (added this build call) converts
  `report_footfall_event`'s `probability` via `logit()` (epsilon-clamped against the 0.0/1.0
  endpoints `logit()` rejects) into the `SEISMIC` reading it passes to `fuse()`, host-tested against
  hand-computed `cognition.config.DEFAULT_FUSION_PARAMS` values in
  `device/mpu/tests/test_reflex_loop.py`. Still **open for acoustic and vision** — no detector or
  classifier-to-elephant-log-odds mapping exists for either (see the two entries below); both are
  passed to `fuse()` as `available=False` for now, never scored.
- **`report_acoustic_event`'s classifier output has no defined mapping onto elephant-presence
  log-odds, and is not fed into `fuse()`.** `AcousticClass` (gunshot/chainsaw/vehicle/animal_call/
  ambient, `bridge/rpc.py`) is a threat/context classification, not an elephant-presence signal, and
  ADR 0007 §5 routes `gunshot` to a direct LoRa alert that bypasses fusion entirely — a routing path
  `comms/` does not implement yet. `device/mpu/services/reflex_loop.py`'s `handle_acoustic_event()`
  (added this build call) logs every event for visibility only. Medium severity: acoustic was always
  scoped as corroboration, never a standalone detector (ADR 0007/0009), so this does not block a
  seismic-only alert path, but the gunshot direct-alert routing is itself a real, undesigned gap.
  Status: open.
- **No vision detector exists, so the vision modality is always passed to `fuse()` as
  unavailable.** `perception/camera.py` is capture-only (no pixel → log-odds model);
  `cognition/fusion.py`'s own module docstring already named this a future build call. High
  severity — vision is the highest-weighted modality (`WEIGHT_VISION` = 1.5, the largest of the
  three), so every alert decision today runs on seismic evidence alone. Status: open.
- **ADR 0001 §6's two fusion limitations are accepted approximations, not resolved.** Correlated
  noise across modalities (rain/fog degrading seismic SNR and vision IR contrast together) and the
  MCAR assumption behind availability-gated dropout (vision being unavailable due to fog is
  plausibly not independent of elephant activity) are both restated in `cognition/fusion.py`'s
  module docstring so a code reader sees them without opening the ADR — see ADR 0001 for the full
  reasoning. Status: open, tracked as future work, not a launch blocker per the ADR.

## Build-call 5 (`device/mcu` seismic bench debug flags)

- **`GEOPHONE_DEBUG_SINGLE_ENDED_AIN0`, `SEISMIC_DEBUG_VERBOSE`, `SEISMIC_DEBUG_STREAM_RAW`, and
  `SEISMIC_DEBUG_PRINT_INTERVAL_MS` (`config.h`) are bench-only and invented.** All four exist
  solely to support the INA333 REF-bias check, the Part C2 sensitivity/waveform-characterization
  pass, and (for `SEISMIC_DEBUG_STREAM_RAW`) the `scripts/live_seismic_plot.py` pitch/demo tool;
  none has a role in field-deployed reflex behaviour, and `SEISMIC_DEBUG_PRINT_INTERVAL_MS`'s
  200 ms cadence is engineering judgement, not a bench-measured value. High severity if left
  non-zero: `GEOPHONE_DEBUG_SINGLE_ENDED_AIN0=1` samples the ADS1115 single-ended against GND
  instead of the field differential pair, silently corrupting every reading. All flags must be
  confirmed `0` before any `scripts/sync-to-board.sh` run against a node headed for the field.
  Status: **closed for the REF-bias check** — run on hardware 2026-07-30, `[bias-check]
  raw≈26890 volts≈1.6806V`, stable across multiple readings, confirming `UREF` is correctly
  mid-supply biased. `GEOPHONE_DEBUG_SINGLE_ENDED_AIN0` reset to `0` and re-synced afterward. Still
  open for Part C2 (`SEISMIC_DEBUG_VERBOSE`) and the live-plot tool (`SEISMIC_DEBUG_STREAM_RAW`) —
  no bench session has run either pass yet.
- **`geophone_service()` samples the ADS1115 at loop rate, not at a gated `SEISMIC_SAMPLE_RATE_HZ`
  cadence — the ring buffer likely holds repeated conversions, not 512 distinct samples.**
  Found while investigating where to hook `SEISMIC_DEBUG_STREAM_RAW`'s print
  (`device/mcu/src/geophone.cpp`): `ads1115_read_conversion()` never polls the ADS1115's OS/ready
  bit (`ADS1115_CFG_COMP_DISABLE` leaves ALERT/RDY unused), and `loop()`
  (`device/mcu/src/main.cpp`) calls `geophone_service()` on every iteration with no delay. At
  `ADS1115_CFG_DR_250SPS` a new conversion appears only every 4 ms, so back-to-back polls can — and
  on a fast host loop, likely do — return the same conversion register value more than once,
  meaning `SEISMIC_WINDOW_SAMPLES` (512) worth of ring writes do not necessarily span the assumed
  2.048 s at 250 SPS. This would skew the STA/LTA windowing (`STA_SAMPLES`/`LTA_SAMPLES` are
  defined in samples, not time) without crashing or zero-filling — no existing check would surface
  it. Not fixed as part of adding `SEISMIC_DEBUG_STREAM_RAW`: that flag's print is rate-gated to
  `SEISMIC_SAMPLE_RATE_HZ` to keep the console from flooding, which bounds the debug output but
  does not address the underlying sampling cadence. Medium-high severity — affects real STA/LTA
  timing accuracy, not just debug output.
  **Double-read bug fixed** — `geophone_service()` now gates the ADC poll itself with a `millis()`
  cadence timer at `1000 / SEISMIC_SAMPLE_RATE_HZ` (4 ms), tracked in a new `g_last_poll_ms` module
  variable reset by `geophone_init()`; a call inside that window returns immediately without
  touching the ring buffer, same rollover-safe unsigned-subtraction idiom as `rule_gate_apply()`'s
  cooldown check. An OS-bit poll was considered and rejected: with `ADS1115_CFG_MODE_CONTINUOUS`,
  the config register's OS bit only means "conversion in progress" in single-shot mode — in
  continuous mode there is no usable ready signal without rewiring ALERT/RDY for interrupt use, a
  much larger change than this bug warrants. Host-verified in
  `device/mcu/tests/test_geophone/test_geophone.cpp` (3 new Unity cases, using
  `hostshim::advance_millis()` to drive simulated time): 600 back-to-back calls with no simulated
  time elapsed leave the window unfilled (would have filled it pre-fix), 512 calls paced at exactly
  the sample period fill it, and a single call one millisecond short of the period is skipped
  without disturbing the gate's timer. `pio test -e native`: 26/26 passing (up from 23 — the 3 new
  cases). `pio run -e native`: clean link, same pre-existing unrelated `-Wunused-function` warning
  for `log_window_csv`. Status: **closed for the double-read bug itself.**

  **Real-hardware verification, 2026-08-14:** flashed with `SEISMIC_DEBUG_STREAM_RAW=1`, captured 6s
  / 399 lines of real console output against the actual ADS1115 (via the socat/TCP bridge described
  below, since `arduino-app-cli monitor` itself is dark). 369 raw-volts lines, 29 `[seismic]` lines,
  0 unparsed/garbled lines. Duplicate-adjacent-pair analysis: 42/368 (~11.4%), max run length 4 —
  consistent with genuine sensor noise-floor repetition, not the old un-gated-polling bug's
  signature (which would show much higher-frequency, longer duplicate runs, since a host-speed
  un-gated loop can out-pace a 4ms ADS1115 conversion period many times over). Also confirmed
  visually via `scripts/live_seismic_plot.py` run live against the real stream. Status: **closed —
  the cadence-gate fix is confirmed against real ADS1115 timing, not just the host stub.**

  **New finding from this same capture, not previously measured:** the achieved raw-sample
  accept/print rate is only **~61.5 Hz**, well under the nominal 250 SPS the STA/LTA window sizing
  assumes. Measured specifically under this debug/bench build (`SEISMIC_DEBUG_STREAM_RAW=1`, which
  adds `Bridge.update()` + `Bridge.notify()` overhead not present in the field build) — at 61.5 Hz
  the 512-sample window spans ~8.3s of wall-clock time, not the assumed ~2.05s, and
  `STA_SAMPLES`/`LTA_SAMPLES` stretch proportionally. Root cause not profiled — plausibly
  per-`loop()`-iteration I2C transaction + `Serial.println` + `Bridge.update()` + `lora_service()`
  overhead exceeding the 4ms cadence-gate floor. High severity for STA/LTA timing accuracy, low
  effort to re-check: re-measure the achieved rate on a field-flag build
  (`SEISMIC_DEBUG_STREAM_RAW=0`) before deciding whether `STA_SAMPLES`/`LTA_SAMPLES` need retuning —
  this debug build's overhead may not reflect the real field rate.

  **Re-measured on the real field-flag build, 2026-08-14:** with every `SEISMIC_DEBUG_*` flag and
  `FIRE_TEST_HARNESS` at 0 (the actual field-deployment configuration, no Bridge streaming, no debug
  prints), the achieved `geophone_service()` rate is **226.98 Hz** — much closer to the nominal
  250 SPS than the 61.5 Hz seen under the debug/Bridge-enabled build, confirming most of that earlier
  gap was debug/Bridge overhead as suspected, not a hardware ceiling. At 226.98 Hz,
  `STA_SAMPLES=25`/`LTA_SAMPLES=250` work out to ~110 ms / ~1.10 s of real elapsed time — both still
  inside the literature targets (STA ≈40-150 ms, LTA ≥0.5 s), so no retune is justified. Full
  derivation in the "STA/LTA field-flag rate re-measurement and real stomp-test calibration" entry
  near the end of this document. Status: **closed** — the field rate is now measured, not assumed,
  and the existing sample counts checked out against it.
- **`arduino-app-cli monitor` cannot read this board's live serial console — use App Lab's own
  Serial Monitor (in a browser) instead.** Confirmed on hardware while running the REF-bias check
  above: the CLI path connects to `arduino-router` without error but never delivers any bytes, in
  steady state, regardless of firmware content (tested against `eletect-x`, against `examples:blink`
  as a control case, and against a firmware build with a guaranteed periodic print). Root cause not fully
  isolated — see ADR 0010's 2026-07-30 addendum for the full investigation — but the workaround is
  simple and confirmed: App Lab's own web-UI console works. Medium severity: does not block any
  bench work, since the GUI path is confirmed to work, but wastes time for anyone who reaches for
  the CLI first. Status: open as a CLI limitation, closed as a practical blocker (workaround
  documented here and in the ADR).

  **Re-confirmed fresh, 2026-08-14** (not just recalled): flashed the current build, ran
  `arduino-app-cli monitor` twice (10s and 12s, debug log level, stdout/stderr separated) — zero
  bytes both times, against a build guaranteed to be printing continuously
  (`SEISMIC_DEBUG_STREAM_RAW=1`). New finding this session: the underlying serial data is fine — a
  pre-existing, previously-undocumented root-owned `socat` daemon on the board
  (`/usr/bin/socat file:/dev/ttyGS0,raw,echo=0,b9600,crtscts=0 tcp:127.0.0.1:7500`, running since
  before this session) bridges the raw USB-CDC serial gadget to local TCP port `127.0.0.1:7500`.
  That port is reachable via plain `nc`/netcat and delivers correct, well-formed, full-rate console
  output (confirmed by capturing and parsing 399 real lines from it — see the cadence-gate entry
  above). So the failure is specific to `arduino-app-cli monitor`'s own relay/display logic, not the
  firmware or the underlying serial transport. This bridge is a viable non-GUI workaround
  (`ssh <board> "nc 127.0.0.1 7500"`) alongside App Lab's browser Serial Monitor. Note: this bridge's
  socat invocation uses `tcp:127.0.0.1:7500` (normally socat's client-connect syntax, not a listener
  form) — how it actually ends up bound as a listener wasn't resolved (would need the board's sudo
  password to inspect via `ss`/`lsof`); not pursued further since the practical question (does the
  port deliver real data) was already answered directly.
- **`scripts/sync-to-board.sh` needs `rsync` present on the board itself, and the stock App Lab
  image does not ship it.** Found 2026-07-31 running the first real `sync-to-board.sh` push of
  this build-call's changes: `rsync` was missing on the Windows host (worked around locally) and,
  separately, missing on the board — `rsync: command not found` on the remote side, `code 12`
  protocol error on the sending end. rsync needs a matching binary on both ends; having one side
  covered isn't enough. Fixed for this board with `sudo apt-get install -y rsync` (Debian trixie,
  stock repo, no extra source needed) — but the `arduino` user's passwordless-sudo allowlist
  (`sudo -l`) only covers `apt-get update`, `apt-get install --only-upgrade`, and two named
  Arduino meta-packages, not arbitrary new installs, so this required an interactive password at
  a real terminal. Anyone re-imaging or replacing this board needs to install `rsync` (and confirm
  with `command -v rsync`, not just trust apt's own output) before `sync-to-board.sh` will get past
  its rsync step. Status: closed for this board, open as a re-imaging gotcha.

  **Correction, 2026-08-14:** the "worked around locally" claim above for the Windows host does not
  hold up — this session searched exhaustively (`/usr`, `/mingw64`, `/c/devtools`) and found `rsync`
  genuinely absent from this Git-Bash host, not just from the board. Worked around this session by
  manually replicating the script's clear-then-copy semantics with `ssh ... rm -rf` + `scp -r`
  instead of actually installing `rsync` locally. Anyone hitting this again should install `rsync`
  for Git Bash (e.g. via MSYS2's package manager) rather than assume a past session already solved
  the local side.
- **The real MPU Python entry point does not exist. `device/mpu/main.py` is a bench-only
  placeholder that only satisfies App Lab's `app.yaml` parser (`arduino-app-cli` requires a
  `main.py` at the root of `python/` by convention, not something `app.yaml` itself declares) — it
  imports the Bridge SDK and blocks forever (as of the entry below, it also registers one
  bench-only Bridge function, `debug_stream_raw_seismic_sample` — still nothing schema-shaped).**
  Found 2026-07-31: the
  `eletect-x` app turned up in `arduino-app-cli app list --show-broken-apps` as `unable to parse
  the app.yaml: main python file missing from app`. Root cause traced via `sync-to-board.sh`'s own
  rsync log (`deleting main.py`): a `main.py` existed on the board only, untracked, almost
  certainly a leftover from App Lab's original "New App" scaffolding wizard, and a legitimate
  `--delete` sync against a repo that never tracked one wiped it — the one-directional,
  repo-is-truth sync (`ENGINEERING_CONVENTIONS.md` §5) working exactly as designed is what broke
  the app. Wiring `bridge/`, `cognition/`, `perception/`, and `services/` together into the actual
  sense → fuse → decide → actuate loop has never been designed, let alone implemented — this stub
  deliberately does not import or call into any of them (`bridge/rpc.py`'s functions all
  `raise NotImplementedError`; nothing here should be read as a preview of the real design). High
  severity, launch blocker: no field deployment can ship without a real entry point wiring the
  actual MCU↔MPU RPC contract, the fusion logic, and the actuation calls. Status: **partially
  closed** — `device/mpu/main.py` now wires a real sense → fuse → decide → actuate loop (this build
  call): `cognition/fusion.py`'s `fuse()`, a new `cognition/decision.py::decide()`, and a new
  `services/reflex_loop.py` (the imperative shell owning logging and the one real side effect, a
  `drive_horn` `Bridge.call()`) are real, host-tested code, not a stub — `services/reflex_loop.py`'s
  own module docstring and `device/mpu/tests/test_reflex_loop.py`/`tests/test_decision.py` cover the
  design. `SAFE_MODE` (default on, `ELETECT_SAFE_MODE` env var) gates the `drive_horn` call behind a
  dry-run log. **Still open:** the two `Bridge.provide()` calls that would actually connect this
  loop to the MCU's real notifies (`report_footfall_event` → `_on_footfall_event`,
  `report_acoustic_event` → `_on_acoustic_event`) are written in `main.py` but deliberately left
  commented out, per the one-at-a-time `Bridge.provide()` registration discipline
  (`docs/DEVICE_DEVELOPMENT_WORKFLOW.md` §3, `ENGINEERING_CONVENTIONS.md` §8) — confirmed to apply on
  the MPU/Python side of `arduino-router` the same as the MCU/C++ side, not just the latter. Neither
  has been registered or run against real hardware; only `debug_stream_raw_seismic_sample` is live.
  Also still open: only the seismic modality is fused (acoustic/vision gaps above), the alert
  threshold and horn deterrence policy are both invented placeholders (entries above), and no launch
  can happen until a live session enables these registrations one at a time and bench-validates the
  real loop end to end. Status: open, now scoped to "register and hardware-verify
  `report_footfall_event`/`report_acoustic_event` one at a time," not "the loop does not exist."
- **`SEISMIC_DEBUG_STREAM_RAW` gained a second, bench-only delivery path (`Bridge.notify()`
  from `device/mcu/src/geophone.cpp` to a matching `Bridge.provide()` handler in
  `device/mpu/main.py`) so `scripts/live_seismic_plot.py` can read live via
  `docker logs -f eletect-x-main-1` instead of only the Serial console.** Two premises behind
  this task turned out to be false and are recorded here rather than silently dropped: no
  Bridge-round-trip RTT measurement exists anywhere (the ping bench, `device/mpu/bench/ping`,
  has never been run against real hardware — `device/mpu/README.md` still reads "pending
  hardware"), and no "Core Electronics 25/sec" throttle finding exists in this repo (the only
  Core Electronics reference is ADR 0001's unrelated SM-24 wiring guide). In place of a
  measured RTT, `Bridge.notify()` was confirmed structurally safe by reading the real installed
  `Arduino_RouterBridge` v0.4.3 `bridge.h` on the board directly: it takes a write mutex and
  performs a one-way send, never blocking on an MPU reply the way `Bridge.call()`'s
  `RpcCall::result()` does — so it cannot stall `geophone_service()` regardless of RTT.
  `SEISMIC_STREAM_BRIDGE_EVERY_N_SAMPLES` (`config.h`, default 10) is therefore an unmeasured,
  conservative default, not a tuned value. Implementing this also required the sketch's first
  ever `Bridge.begin()`/`Bridge.update()` calls (`device/mcu/src/main.cpp`) — gated behind
  `#if SEISMIC_DEBUG_STREAM_RAW` so they compile out of the field build entirely; the real
  schema handlers (`drive_horn`, `drive_led`, `pulse_ir`, `geophone_ok`) remain unregistered.
  Verified end-to-end on hardware 2026-07-31: rebuilt/restarted via `arduino-app-cli app
  restart`, then ran the real `docker logs -f eletect-x-main-1 | python
  scripts/live_seismic_plot.py -` pipeline and confirmed a live matplotlib window actively
  redrawing (rising CPU time) against real streamed samples, not just that the build succeeded.
  This is more than a demo win: it is the first time `Bridge.notify()` has been confirmed working
  on real hardware, MCU→MPU direction, at all, in this project's history — see the Build-call 2
  "MCU→MPU Bridge `notify()` direction" entry above, now closed on the strength of this session.
  `Bridge.call()`'s synchronous-reply direction is a distinct mechanism and stays open, unproven —
  not folded into this result. Status: closed for this bench tool; the missing ping-bench RTT,
  the still-unproven `call()` direction, and the never-registered production schema handlers
  remain open, tracked by their own existing entries above.
- **`config.h`'s `LORA_SERIAL Serial1` may be pointed at the wrong HardwareSerial object,
  independent of the Bridge-conflict question raised earlier tonight.** A documentation pass
  (Arduino UNO Q official datasheet, the `Arduino_RouterBridge` GitHub README, and several 2026
  Arduino Forum UNO Q threads — full citations in `docs/eletect-x-applab-notes.md`) found multiple
  independent community reports that `Serial1` is the name the `arduino:zephyr` core binds to
  Bridge's own internal MCU↔MPU link, and that the Grove LoRa-E5's D0/D1 pins are reached through
  the plain `Serial` object instead — with one report that this exact naming shifted across a past
  core update, meaning the true answer is specific to whichever core version this board is running,
  not fixed. This is not confirmed against this board and is one step short of proof (forum reports,
  not this project's own hardware test), but it is stronger and more specific than the earlier
  same-session reasoning that treated the pairing as low-risk. High severity: if correct, LoRaWAN
  uplink — the path that gets alerts to the DFO — has never had a working transport, independent of
  anything else about the join/AT-command logic in `mac.cpp`. Effort: cheap to close, two ways —
  grep the real installed core's variant/pin-mapping source on the board directly (same technique
  already used to read the real `bridge.h`), or bench-test a real LoRa AT command exchange on both
  `Serial` and `Serial1` with Bridge simultaneously active and see which one the E5 actually answers
  on. Status: open, tracked in Cowork's task list, priority re-check before any LoRa bench session.
  **Local-grep option checked and ruled out, 16 Aug:** searched this Windows dev machine for the
  installed `arduino:zephyr` core / UNO Q board-support source, the same way the real `bridge.h` was
  read earlier — `.platformio/packages` (only ESP32/Renesas/DFU-util packages present), Arduino15's
  `packages` dir (avr/esp32/esp8266/rp2040/Seeeduino/teensy only, no zephyr package), App Lab's
  `flasher_cache/*.tar.zst` (a raw QRB2210 flash image — GPT partitions and firmware blobs, not a
  browsable filesystem tree; `tar -tf` over the decompressed stream lists no `zephyr`/board-overlay/
  `bridge.h` entries because none of its members are individual rootfs files), the App Lab temp
  workspace (mirrors this repo's own sketch source only), and every `fqbn` this machine has ever
  locally compiled per `arduino-cli`'s `build.options.json` history and `arduino-cli.yaml`'s
  configured board-index URLs (AVR/ESP32/ESP8266/RP2040/Seeeduino/Renesas/Silabs/Teensy — no UNO Q /
  zephyr index configured at all). Conclusion: this core has never been cached or compiled on this
  machine — the earlier `bridge.h` read must have come from direct SSH access to the board's own
  Linux filesystem, done by hand per this project's standing SSH rule
  (`docs/eletect-x-applab-notes.md`), not from anything locally greppable. The local-grep path is a
  dead end here, not just unresolved; the live bench test (or a session where the SSH rule's human
  runs the same grep directly on the board) remains the only way to close this. `config.h`'s
  `LORA_SERIAL` default is left unchanged (`Serial1`) — nothing found here settles it either way, so
  flipping it would be a coin flip, not a fix.
- **The manual serial fire-test harness (`device/mcu/src/fire_test.*`,
  `docs/specs/mcu-fire-test-harness.md`) now exists as the intended mechanism to close two open
  items above rather than closing them itself.** It gives a human a one-keystroke way to call
  `drive_horn`/`drive_led`/`pulse_ir` directly and see the full ack (`allowed`/`duration_ms`/
  `gain_pct`/`clamped`) printed as `[firetest] ...` — the tool `HORN_AMP_ENABLE_DELAY_MS` (invented,
  see above) and the horn/LED/IR burst-cap and cooldown entries (also invented, see above) need for
  a real bench pass. Gated behind `FIRE_TEST_HARNESS` (`config.h`, default 0), same discipline as the
  seismic bench flags. **Software path run against real hardware, 15 Aug:** flashed with
  `FIRE_TEST_HARNESS=1`, all four commands (`1`/`2`/`3`/`4`) sent over the board's console bridge and
  each produced the expected full `[firetest]` ack (`allowed=1`, correct `duration_ms`/`gain_pct` per
  the bench defaults, `clamped=0`); pressing `1` a second time immediately after produced
  `allowed=0 duration_ms=0 gain_pct=0.00 clamped=0` — the `HORN_COOLDOWN_MS` gate refusing correctly,
  not a bug. **Physical activation NOT confirmed — horn, LED, and IR are not yet wired to the board**
  (confirmed with Abhinav before running the sequence), so this run only proves
  `fire_test_parse_command()`/`fire_test_service()`/`rule_gate_apply()`/the ack print path are wired
  correctly end to end on real firmware, not that the actuators themselves switch on. `config.h`
  reverted to `FIRE_TEST_HARNESS=0` and re-flashed immediately after; console confirmed silent (no
  `[firetest]` response to a test keystroke) before ending the session. Status: **open, narrower
  scope** — the software path is verified, but `HORN_AMP_ENABLE_DELAY_MS`'s real value and the
  burst-cap/cooldown constants' physical behavior still cannot be measured until the actuators are
  wired; re-run the same checklist once wiring exists, this time watching/listening for each fire.
- **`SEISMIC_DEBUG_STREAM_RAW`'s committed default (`config.h`, `1`) broke `pio test -e native` and
  `pio run -e native` outright, for the whole tree, not just the fire-test harness's own additions.**
  Found running that harness's verification checklist: at `=1`, `main.cpp` and `geophone.cpp` both
  `#include "Arduino_RouterBridge.h"` to reach `Bridge.begin()`/`Bridge.update()`/`Bridge.notify()`,
  but `hostshim/` (the host-only Arduino API stand-in `platformio.ini` documents as making `pio run`/
  `pio test` possible at all) had no stub for that header — it only exists as a real library on the
  board. Every host build and every `pio test` run failed with `fatal error: Arduino_RouterBridge.h:
  No such file or directory`, regardless of what any other file changed; the "23/23 pass" first
  reported for the fire-test harness was against a locally-flipped flag, not the tree as committed,
  and did not hold against real `HEAD`. High severity while open: the host build is the only
  pre-hardware compile/test signal this project has, and it had been silently broken since the commit
  that set this default. **Fixed**: added `hostshim/Arduino_RouterBridge.h`, a no-op `BridgeClass`
  stand-in exposing `begin()`/`update()`/`notify()`/`provide()` (the last two as variadic/generic
  templates that accept and discard any name+args shape, since nothing on a host build has an
  `arduino-router` socket to actually deliver a message to), wired into `hostshim/host_shim.cpp` the
  same way `Serial`/`Wire` already are (out-of-line non-template methods + a global instance). This is
  the durable fix, not a per-flag workaround: any future bench flag that pulls in a board-only header
  hits the same class of break, and a real stub in `hostshim/` (matching the pattern every other
  Arduino API surface there already follows) is what closes that class of gap, not a second
  `#if`/`#endif` around this one include. **Verified against the tree exactly as committed**
  (`SEISMIC_DEBUG_STREAM_RAW=1`, `FIRE_TEST_HARNESS=0`, no flags flipped for the run): `pio test -e
  native` → 23/23 test cases pass (`test_fire_test` 7, `test_rule_gate` 10, `test_sta_lta` 6); `pio
  run -e native` → links clean, and the resulting host smoke binary (`.pio/build/native/program.exe`)
  runs `setup()` + 600× `loop()` to completion without crashing, exercising the real
  `Bridge.notify()` call site in `geophone.cpp` through the new stub on every iteration. Status:
  closed.

## Build-call 6 (`device/mcu` Bridge.provide() adapters for the MPU→MCU actuator/status RPCs)

- **`drive_horn`, `drive_led`, `pulse_ir`, and `get_system_state` (`device/mpu/bridge/schema.md`'s
  MPU→MCU table) now have real MCU-side adapters (`device/mcu/src/bridge_handlers.h/.cpp`), but none
  is registered with `Bridge.provide()` — `main.cpp`'s four registration lines are written and
  commented out, one per line, matching the one-at-a-time discipline
  (`docs/DEVICE_DEVELOPMENT_WORKFLOW.md` §3, `ENGINEERING_CONVENTIONS.md` §8, and the identical
  treatment `device/mpu/main.py` already uses for `report_footfall_event`/`report_acoustic_event`).**
  Each adapter converts the flat scalar Bridge call signature schema.md defines into the existing,
  already-tested actuator/sensor calls (`horn.h`/`led.h`/`ir.h`/`geophone.h`) and back into the flat
  return shape schema.md specifies; named `bridge_*` rather than reusing the schema names directly,
  since `horn.h`/`led.h`/`ir.h` already define `drive_horn`/`drive_led`/`pulse_ir` as the real
  actuator-struct functions and `Bridge.provide()`'s registered name is a string, decoupled from the
  C++ symbol bound to it. A new `BRIDGE_SCHEMA_VERSION` constant (`config.h`, `1`) mirrors
  `device/mpu/services/config.py`'s `SCHEMA_VERSION`; a mismatch is logged via `Serial`, not
  rejected, matching `services/reflex_loop.py`'s "log, don't raise" handling for the MCU→MPU
  direction — this is a synchronous call the MPU is already blocked on, so it still gets a real ack
  either way. Host-tested (`device/mcu/tests/test_bridge_handlers`) for the one genuinely new piece
  of decision logic, `led_channel_for_pattern_id()` (see below); `pio test -e native` → 29/29 passing
  (up from 26); `pio run -e native` → clean link, same pre-existing unrelated `-Wunused-function`
  warning. **No line has been uncommented, no board has been flashed, and no actuator has fired** —
  this build call was host-build/host-test only throughout, per explicit instruction. Status: open,
  by design — closes one function at a time in a future hardware session, never as a batch.
- **`drive_led`'s adapter invents a `pattern_id → led_channel` mapping (0 → white, 1 → blue,
  anything else → white) that has no basis in schema.md or any design doc.** schema.md's `drive_led`
  row (`schema_version, pattern_id: uint8, duration_ms: uint16`) never defines what `pattern_id`
  values mean, and no LED strobe-pattern design exists anywhere in this repo. The separate question
  of *gain* is now settled (`schema.md`'s "Actuator gain defaults" section, and the closed entry
  above) — `LED_GAIN_MAX_PCT`/`IR_GAIN_MAX_PCT` are the deliberate, permanent internal defaults, not
  a placeholder pending a decision. What's still genuinely undesigned is `pattern_id` itself: whether
  channel selection (white/blue) is all it should ever mean, or whether a real LED deterrence pattern
  design (strobe timing, color sequencing) should exist and use more of the `uint8` range than two
  values. Medium severity: harmless until `drive_led` is actually registered and called. Status:
  open, blocked on an LED pattern design pass this build call did not attempt.
- **`get_system_state`'s adapter cannot honestly report `battery_v` or `acoustic_ok` — both are
  fixed placeholder values, not live readings.** No battery-monitor driver or ADC pin exists anywhere
  in `config.h`; `battery_v` always returns `0.0f`, chosen as an "unknown" sentinel rather than a
  fabricated voltage that could be mistaken for a real reading on a future dashboard. No acoustic
  subsystem exists on this MCU at all yet (no driver, no `config.h` entry, no acoustic ADC path) —
  `acoustic_ok` always returns `false`. `geophone_ok` (the field this task's request specifically
  named) is real: it calls the existing, already-tested `geophone_ok()` (`geophone.cpp`) directly.
  `uptime_s` is real too (`millis() / 1000`). High severity if this were registered and trusted
  today: a dashboard reading `battery_v=0.0` could misread as "battery dead" rather than "not wired
  yet," and `acoustic_ok=false` could misread as "acoustic sensor faulted" rather than "does not
  exist." Do not register `get_system_state` for real use until at minimum `battery_v` is backed by
  an actual ADC read, or the dashboard consumer is taught to treat `0.0`/`false` here as "unknown,"
  not "measured." Status: open.

## Build-call 7 (`device/mcu` automated geophone excitation self-test)

- **Automated desk-speaker excitation self-test built and run against real hardware, 2026-08-14 —
  a chain-health/repeatability check, explicitly NOT a substitute for the real human stomp test.**
  Three new bench-only scripts (`scripts/geophone_excitation_stimulus.py`,
  `scripts/capture_geophone_console.py`, `scripts/correlate_geophone_excitation.py`) make the
  existing manual `scripts/geophone_bench_excitation.html` tool's play → capture → correlate → report
  cycle fully scriptable: the stimulus script drives the laptop speaker (`sounddevice`/`numpy`,
  installed `--user` this session, bench-only, not a repo dependency; falls back to
  `winsound.Beep()` — a square wave, not a sine — if `sounddevice` is unavailable) through a fixed
  sequence and logs each event's real wall-clock start/stop to JSONL; the capture script wraps the
  same `ssh <board> "nc 127.0.0.1 7500"` bridge used for the cadence-gate check above (with
  `SEISMIC_DEBUG_VERBOSE=1`, already the working tree's default) and timestamps every console line
  by **host arrival time**, not the board's own `millis()`-based `t=` field — the two clocks have no
  cheap way to align after the fact, whereas host-arrival time compares directly against the
  stimulus log's own wall-clock timestamps; the correlate script pulls the `[seismic] sta=/lta=/
  ratio=` samples inside each stimulus window and reports the mean/max ratio and the delta against
  the combined quiet-baseline mean, flagging any window with no discernible response.

  **Pre-check, per this session's explicit instruction:** Nahimic (Lenovo Legion audio-enhancement
  suite) was found running (`NahimicService`, `Get-Service`) and had to be stopped before any
  playback — bass/enhancement processing would have distorted the frequency content the correlation
  depends on. The automation shell had no admin rights to stop the service itself
  (`net session` confirmed not elevated); stopped manually via an elevated `Stop-Service
  NahimicService -Force` and left stopped for the remainder of the session, not restarted
  automatically afterward. Default output device confirmed correct and functional independently of
  the low-frequency test content: `Speakers (Realtek(R) Audio)` at 100% volume, not muted
  (`pycaw`/`IAudioEndpointVolume`), and a 440 Hz confirmation tone was audibly confirmed. The bench
  stimulus tones themselves (10–50 Hz, plus the supplementary frequencies below) were reported
  inaudible or barely audible by ear — expected, not a fault: `geophone_bench_excitation.html`'s own
  warning notice already documents that small laptop speakers roll off hard below ~60–100 Hz, so
  most of what reaches the geophone at these frequencies is chassis/driver motion coupling into the
  desk, not true audible sound. Per this session's instruction, the room fan was off and no one
  walked near the desk during either run; the laptop's own load-driven fan (unavoidable, later
  switched to the laptop's quieter power profile) and, during the second run specifically,
  foot traffic in an adjacent room are noted as residual, uncontrolled noise sources — see the
  elevated second-run baseline below.

  **Two runs.** The first (`geophone_excitation_20260814_192430.{log,jsonl}`) covered the four
  spec'd frequencies (10/20/24/50 Hz), the 2→60 Hz sweep, and the impulse train, but the capture
  script's fixed duration was sized before accounting for the live diagnostic delay between starting
  the capture and starting playback, so it ran out mid-impulse-train — that window has only 2
  `[seismic]` samples for a 15 s span. This is a **test-harness timing bug in this session's own
  tooling, not a firmware finding** — confirmed by inspecting the raw capture directly: the console
  stream itself (all lines, not just `[seismic]`) simply stops the moment the capture's fixed
  duration elapses, mid-window. Fixed for the second run by starting the capture and the full
  stimulus sequence back-to-back in one shell invocation (no inter-step delay) with a capture budget
  (150 s) comfortably above the real stimulus length. The second run
  (`geophone_excitation_20260814_195937.{log,jsonl}`) is the complete dataset and also added five
  supplementary tone frequencies not in the original spec (5, 8, 15, 30, 100 Hz), to bracket the
  SM-24's documented ~10 Hz mechanical resonance (`geophone_bench_excitation.html`'s own "10 Hz
  (SM-24 resonance)" preset) more finely after the first run's result below. Both runs' raw logs are
  under `scripts/bench-logs/` (now `.gitignore`d — reproducible via these scripts, not source) and
  were not committed.

  **Real findings (second/complete run; cross-checked against the first run for repeatability):**
  - **10 Hz is the one frequency that produced an unambiguous, repeatable, above-noise-floor
    response in both independent runs, including a real STA/LTA `[trigger]` crossing each time.**
    Run 1: mean ratio 3.37 vs a 1.37 baseline (Δ+2.00), peak 5.06, one real `[trigger]`. Run 2: mean
    ratio 3.99 vs a 1.75 baseline (Δ+2.24), peak 4.79 (a separate 4.37-ratio trigger also fired
    inside this window). This is consistent with the SM-24's own known resonance amplifying even a
    weak, largely inaudible desk-coupled excitation — a credible, physically-explicable real
    response from the sensor chain, not noise.
  - **20/24/50 Hz, the 2→60 Hz sweep, the impulse train, and all five supplementary frequencies
    (5/8/15/30/100 Hz) showed no response distinguishable from the quiet-baseline noise floor** in
    the complete (second) run (deltas all within ~2 baseline standard deviations). Most plausible
    explanation is compounding, genuine, non-chain-defect factors, not a sensor-chain problem: (a)
    weak/near-inaudible speaker output at these frequencies and this session's 22.5% output gain
    outside the resonance peak, per the already-documented small-speaker rolloff above; (b) this
    run's own baseline was itself elevated by real ambient disturbance — its combined quiet-window
    mean/stdev (1.75/0.80) was higher than run 1's (1.37/0.81), and one `[trigger]` (ratio 2.94)
    fired inside a `baseline_quiet` window itself, coinciding with the adjacent-room foot traffic
    flagged during this run. Separately, the sweep's and impulse train's null results have their own
    physical explanation even setting noise aside: the linear sweep only dwells within roughly ±1 Hz
    of the 10 Hz peak for about 0.7 s of its full 20 s span (≈2.9 Hz/s sweep rate), diluted into one
    whole-window mean; the impulse train's 80 ms-on/920 ms-off duty cycle likely gives the
    resonance too little continuous energy per cycle to ring up detectably against STA/LTA's
    window-averaged ratio, unlike a sustained 5 s tone at the same frequency. None of this proves the
    chain would respond the same way to real footfall-band energy at real amplitude — only that this
    specific, weak, desk-speaker stimulus mostly didn't clear this specific, sometimes-noisy floor.
  - **`tone_24hz` and `tone_50hz` had far fewer `[seismic]` samples than expected in run 2** (3 and 7
    respectively, vs ~25 expected at the 200 ms print cadence over a ~5 s window). Traced to two real
    `[trigger]` events landing in the immediately preceding `quiet_gap` windows (ratios 2.18 and
    2.07 — both just over `SEISMIC_DEMO_MODE`'s lowered `STA_LTA_TRIGGER_RATIO=2.0`, the config
    currently active in this working tree's uncommitted `config.h`, not field's 4.0), whose
    `EVENT_MAX_MS`+`COOLDOWN_MS` cycle (2000+3000 ms in demo mode) bled into the start of the
    following tone window. This is real-hardware corroborating evidence for the already-open
    "`loop()` has no task/priority separation, so an actuator fire stalls sensing" entry above — not
    a new bug, and not addressed by this session (no threshold or blocking-behavior code was
    touched).

  **Hard boundary respected:** `STA_LTA_TRIGGER_RATIO`, `STA_LTA_DETRIGGER_RATIO`, `STA_SAMPLES`,
  and `LTA_SAMPLES` in `config.h` were not modified by this session — confirmed by this entry's own
  diff. `SEISMIC_DEMO_MODE`'s lowered trigger/detrigger ratios were already present, uncommitted, in
  the working tree before this session and are only referenced above as context for interpreting the
  observed `[trigger]` ratios, not something this session set or changed.

  **This is a desk-speaker-coupled excitation check — chain-health/repeatability only, not real
  footfall data.** Desk-speaker excitation has a different waveform shape, amplitude, and frequency
  content than an elephant footfall coupling through soil; the 10 Hz result above shows the sensor
  chain is alive, repeatable, and roughly the expected frequency-response shape, nothing more. **The
  real human stomp test — "Bench stomp-test trigger log not yet captured" near the top of this
  document — remains the only source for actual STA/LTA threshold calibration and is still the
  next/last remaining step**, unaffected by anything in this entry. Status: closed for this bench
  tool and this pass; the human stomp test stays open.

## Literature review — geophone species discrimination & scientific STA/LTA grounding (planning session, 14 Aug)

Written in direct response to the request to tune and validate the geophone chain "scientifically"
against real papers, and the follow-on scope: elephant, boar, human, and vehicle detection, in rain
and other field conditions. Fetched and read in full where access allowed; several relevant papers
exist but were not retrievable through the tools available to this session (403/429 on every
mirror tried) — listed below as unresolved, not silently dropped.

**What was actually retrieved and read:**

- Wijayakulasooriya et al., "Towards Long Range Detection of Elephants Using Seismic Signals"
  (arXiv:2406.05140 / IEEE Access, 2024) — the single most directly useful source found. Real field
  trial, validated detection range 155.6 m (controlled) / 140 m (natural), decision-tree classifier
  (not STA/LTA) on spectral features, 10–200 Hz analysis band. Predominant-frequency-by-source-class
  result: **elephant 26.13 ± 6.43 Hz, human 70.90 ± 12.52 Hz, motorcycle 115.76 ± 41.53 Hz.** This is
  a real, citable frequency-separation result and is consistent with ADR 0001's O'Connell-Rodwell
  et al. 2000 (JASA) figure of ~24 Hz mean elephant footfall frequency that this repo already cites.
- Trnkoczy, "Understanding and parameter setting of STA/LTA trigger algorithm" (GFZ Potsdam) — the
  original PDF 403'd on every attempt; read via a secondary source (Güralp's own STA/LTA
  documentation, which cites the same convention). Practical rule: **STA should be set to roughly
  the dominant period of the target event** (for a ~26 Hz elephant footfall, ≈ 1 period ≈ 38 ms);
  **LTA should be set longer than the period of the lowest frequency of interest** (for the existing
  2 Hz low edge of the analog band-pass, ≥ 0.5 s). Trigger/detrigger ratio has **no universal
  literature value** — every real source agrees it is set empirically against local noise and real
  target events, which is exactly why this repo's hard boundary (real threshold constants come only
  from the real human stomp test, never from bench-speaker data) is the scientifically correct
  position, not just a cautious one.
- A wavelet-packet-manifold seismic target classifier (PMC3758609, unattended-ground-sensor
  literature) — general corroboration, not elephant-specific: pedestrian energy concentrates
  0–112 Hz, vehicle/helicopter energy extends across the full measured band, and getting from
  "trigger" to "classify" required wavelet-domain features plus a trained classifier (KNN, 95%
  across 4 classes), not a single amplitude-ratio threshold.

**What this means for `config.h`'s numbers, concretely:** the existing `STA_SAMPLES=25` /
`LTA_SAMPLES=250` were sized assuming `SEISMIC_SAMPLE_RATE_HZ=250` maps to real elapsed seconds
(0.1 s / 1.0 s) — and land close to the Trnkoczy/Güralp guidance above almost by coincidence, since
generic seismic convention and the elephant-specific numbers happen to be in the same ballpark. But
this session's own prior hardware finding (~61.5 Hz actual loop-measured sample rate under the
current debug/Bridge-enabled build, not the nominal 250 SPS ADS1115 conversion rate) means those
"0.1 s"/"1.0 s" figures are **not currently true in real time on this board** — at ~61.5 Hz, 25
samples is ~0.41 s, not 0.1 s, four times longer than the literature target for resolving a single
elephant footfall impulse. This has to be re-measured on a lean, field-flag build (all
`SEISMIC_DEBUG_*`/`FIRE_TEST_HARNESS` flags at 0, no Bridge streaming) before any STA/LTA sample
count is retuned — the debug/Bridge overhead may be most or all of the gap between 61.5 Hz and
250 Hz, and tuning against the wrong real-time base would silently miscalibrate the detector no
matter how correct the literature-derived target duration is.

**Scope line — what STA/LTA can and cannot do, stated plainly:** a single-channel STA/LTA amplitude
trigger answers one question — "is there a ground disturbance bigger than the recent local noise
floor" — using the existing 2–50 Hz analog band-pass as its only frequency selectivity. That
band-pass is itself a real, literature-grounded discrimination step (it passes the ~26 Hz elephant
peak while attenuating most of the ~71 Hz human and ~116 Hz motorcycle predominant energy per
Wijayakulasooriya above) — a genuine scientific design win already built into the hardware, not
something that needs inventing. But STA/LTA cannot itself tell an elephant from a boar from a human
stomping directly on the sensor from a nearby vehicle; every real classification paper found here
(elephant, UGS pedestrian/vehicle, and others below) needed per-window spectral or ML features and a
trained classifier to get there. That is exactly what `CONTEXT.md` §4 already scopes as "TinyML
footfall" and what `ml/seismic/` (currently empty, `.gitkeep` only) is reserved for — it is real,
unbuilt, future work, not a `config.h` tuning pass. Trying to force elephant/boar/human/vehicle/rain
discrimination out of four STA/LTA constants before 20 Aug would be scientifically dishonest; the
honest near-term target is a well-calibrated single-class "large ground impact" trigger, validated by
the real stomp test, plus making sure every trigger's raw window is retained during the field trial
so the 10-day deployment doubles as the first labeled dataset for the future classifier.

**Gaps this review could not fill — stated honestly rather than papered over:**

- **Wild boar**: no seismic footfall/gait literature for boar (or any similar-mass quadruped) was
  found despite several targeted searches. The nearest published results are all human-pedestrian- or
  vehicle-focused. This is a genuine, currently-unfilled gap, not a retrieval failure to paper over —
  if boar discrimination becomes a real requirement, it will need either dedicated literature this
  session could not locate, or empirical data collected from an actual boar encounter during the
  field trial.
- **Rain/wind seismic noise**: two directly relevant papers were found by title (Rindraharisaona
  et al. 2022, AGU Earth and Space Science, "Seismic Signature of Rain and Wind Inferred From Seismic
  Data"; a second rain-seismic-signature abstract via AGU) but both 403'd on every fetch attempt — 
  content not retrievable through the tools available here. No specific numbers from those papers are
  reported below because they were never actually read. General seismological expectation (not a
  citation, background domain reasoning only) is that rain/wind tends to raise the ambient noise
  floor with broadband, continuous energy rather than producing discrete impulses — which would
  mainly threaten LTA/false-trigger behavior, not the STA impulse shape. This is a real prediction to
  test, not a validated fact; there is no substitute for capturing a real raw window during actual
  rain at this installation, which the 10-day field trial is the first real opportunity to do.
- **Two papers that looked like the best possible match for the full multi-species ask were found but
  not retrievable at all**, and are worth someone with institutional journal access chasing down
  directly rather than treating as closed: Steinmann et al. 2025, "Decoding the footsteps of the
  African savanna: Classifying wildlife using seismic signals and machine learning" (*Methods in
  Ecology and Evolution*, DOI 10.1111/2041-210X.70021) — a real multi-species savanna wildlife
  seismic classifier including elephants; and a TechRxiv preprint, "A Hybrid CNN-BiLSTM Model for
  Seismic Signal Based Wildlife Detection Nearby Railway Tracks" — both 403'd on every mirror tried
  (publisher direct, ResearchGate). Either would directly inform the `ml/seismic` TinyML design once
  it starts.

Status: open — this is a research/scoping entry, not a code change. (a) the field-flag real
sample-rate re-measurement and (b) the real human stomp test both landed 2026-08-14 — see the next
entry for the full derivation. Remains open on (c): a decision on whether/when `ml/seismic` TinyML
work starts for true multi-class discrimination, and on the boar/rain gaps stated above, neither of
which this session had literature or data to fill.

## STA/LTA field-flag rate re-measurement and real stomp-test calibration (14 Aug)

Closes the two open items the literature review above left outstanding. Referenced from
`config.h`'s STA/LTA block and `device/mcu/README.md`'s bench stomp-test section — this entry is the
full derivation both point to.

**Real sample rate, lean field-flag build:** measured `geophone_service()` at **226.98 Hz** with
every `SEISMIC_DEBUG_*` flag, `FIRE_TEST_HARNESS`, and `SEISMIC_DEMO_MODE` at 0 — the actual
field-deployment configuration, not the debug/Bridge-streaming build the earlier ~61.5 Hz figure
(see the sample-rate entry above) was measured under. Confirms that gap was overhead from
`SEISMIC_DEBUG_STREAM_RAW`'s `Bridge.update()`/`Bridge.notify()` path, not a hardware ceiling.

**STA/LTA window sizes in real elapsed time, vs. literature:** at 226.98 Hz, `STA_SAMPLES=25` is
~110 ms and `LTA_SAMPLES=250` is ~1.10 s. Literature targets (Wijayakulasooriya et al.,
arXiv:2406.05140, elephant footfall predominant frequency 26.13 ± 6.43 Hz → dominant period ≈38 ms;
Trnkoczy/Güralp STA/LTA sizing guidance, STA ≈ 1 dominant period, LTA ≥ period of the lowest
frequency of interest — here the analog band-pass's 2 Hz low edge, ≥0.5 s) put STA in a ≈40-150 ms
ballpark and LTA at ≥0.5 s. Both real-world window durations land inside their targets. **No change
made to `STA_SAMPLES` or `LTA_SAMPLES`** — per the hard boundary, these are set from real hardware
measurement plus literature comparison only, never retuned speculatively, and this check gave no
reason to retune them.

**Real human stomp test** (`device/mcu/README.md`'s "Bench stomp test" procedure, Rung 1's exit
criterion): run on real hardware, geophone ground-coupled, on the same lean field-flag build with
`SEISMIC_DEBUG_VERBOSE` temporarily set to 1 for one ~89 s capture to get quantified quiet-floor
numbers directly comparable to the trigger event, then reverted to 0 immediately after (raw log:
`scripts/bench-logs/stomp_test_20260814_verbose.log`; two earlier, less-controlled attempts —
`stomp_test_20260814.log`, `stomp_test_20260814_clean.log` — produced consistent-magnitude trigger
ratios of 4.02-4.53 but no quiet-floor baseline, and are kept only as corroborating evidence, not the
basis for any number below).

- **Quiet floor:** ratio held 1.03-1.13 across ~35 s before the stomp and ~46 s after it (no false
  triggers either side of the real event) — a stable, real-measured noise-floor ceiling.
- **Real stomp:** a firm stomp near the geophone produced `[trigger] ... ratio=4.60`, with the
  `[window]` raw-volts CSV dump on that trigger showing a genuine transient (peak samples around
  ±0.02 V against a ~0.0003-0.0004 V baseline, roughly a 65x amplitude jump) — real waveform proof,
  not just a ratio number.
- **Margin:** `STA_LTA_TRIGGER_RATIO=4.0` sits ~3.5x above the observed floor ceiling (1.13) and the
  real stomp clears it by ~15% (4.60 vs 4.00). **Value kept unchanged** — the real data confirmed the
  existing constant rather than calling for a retune.
- **`STA_LTA_DETRIGGER_RATIO=1.5` could not be validated the same way and stays open, as dead code,
  not as an unvalidated calibration.** Confirmed by `grep` that `DETRIGGER_RATIO` appears nowhere in
  the codebase outside its own `#define` — `state_machine.cpp`'s `kEvent` state has exactly one exit
  condition, `elapsed_since_entry(now_ms) >= EVENT_MAX_MS`, and no ratio-based detrigger check exists
  anywhere in `sta_lta.cpp` or `state_machine.cpp`. There is no live logic to point real data at, so
  the value is left untouched rather than set from data that can't actually exercise it. If a
  ratio-based detrigger is ever implemented, this constant needs a real validation pass of its own
  before being trusted. **Update, 15 Aug:** rather than stay open indefinitely, the constant was
  removed outright — see the "`kSensing` redundant STA/LTA re-run..." entry near the end of this
  document for the decision and rationale. This paragraph is kept as the historical record of why it
  was dead code in the first place.

**Secondary observation, not yet acted on:** `log_window_csv()`'s `[window]` CSV dump (bench-only,
`SEISMIC_DEBUG_VERBOSE && !SEISMIC_DEMO_MODE`) took roughly **6.7 s** of wall-clock time to complete
on this capture (host-arrival timestamp on the CSV line vs. the `[trigger]` line's own timestamp,
~6.7 s apart), during which the printed ratio was observed frozen at exactly `4.60` for ~8.5 s post
-trigger before returning to the quiet-floor range. `state_machine.cpp`'s own comment on this dump
describes the stall as "several hundred ms" — the real measurement is over an order of magnitude
longer than that comment claims. This only affects the bench-only verbose path (never compiled into
the field build), so it does not block the Aug 20 trial, but the comment itself is now known to be
wrong and should be corrected in a future bench-focused session. Not investigated further this
session (root cause not profiled — plausibly `Serial.print`'s blocking behavior over 512
comma-separated floats at whatever baud rate is configured).

Status: **closed** — real field-flag sample rate measured, STA/LTA window sizes checked against
literature and found adequate (unchanged), real stomp test run and `STA_LTA_TRIGGER_RATIO` validated
with margin (unchanged), `STA_LTA_DETRIGGER_RATIO` reclassified from "unvalidated" to "confirmed dead
code" here and later removed outright (15 Aug, see the "`kSensing` redundant STA/LTA re-run..." entry
near the end of this document). The `log_window_csv()` timing-comment discrepancy is noted as a loose
end for a future bench session, not reopened here.

## Raw seismic trigger data does not reach the MPU or survive anywhere in the real field build (14 Aug)

Checked as part of confirming the Aug 20 field trial will actually produce usable data for the
future `ml/seismic` classifier, per `CONTEXT.md`'s framing of the 10-day deployment as the first
labeled dataset opportunity. It will not, as the code stands today.

Every STA/LTA trigger's raw window or feature data is gated behind flags `config.h` itself documents
as "MUST be 0 before any field sync": `log_window_csv()` (the `[window]` CSV dump used in the bench
stomp test above) is compiled only under `#if SEISMIC_DEBUG_VERBOSE && !SEISMIC_DEMO_MODE`, and
`SEISMIC_DEBUG_STREAM_RAW`'s `Bridge.notify()` relay path is a separate bench-only flag with the same
discipline. Both are correctly off in the real field-flag build — that part is working as intended.

The problem is that the schema-documented *real* path never got built: `bridge/schema.md` defines
`report_footfall_event(schema_version, probability, sta_lta_ratio, feature_vector: float[8])` as the
notify that's supposed to carry every trigger's data to the MPU, and the MPU side is fully
implemented and tested — `device/mpu/main.py`'s `_on_footfall_event` and
`device/mpu/services/reflex_loop.py`'s `handle_footfall_event` exist, are unit-tested
(`device/mpu/tests/test_reflex_loop.py`), and are ready to receive real calls. But nothing on the MCU
side ever calls it: `state_machine.cpp`'s `kEvent` case (where the call belongs, right after a
trigger) is a comment-only stub — "Entry stub: this is where deterrence policy (report_footfall_event
notify, which actuator fires at what gain/duration) belongs once fusion/bandit land" — with no actual
`Bridge.notify()` call anywhere in the file. The MPU-side registration is also still commented out in
`main.py` ("NOT YET ENABLED — see module docstring's 'Registration state' paragraph"), consistent
with the Bridge `provide()` registration gap already tracked above, but that's a second, independent
blocker on top of the missing MCU-side call — enabling the registration alone would not fix this,
since there is still nothing on the MCU side to call it.

**Net effect for the Aug 20 field trial as the code stands today: every STA/LTA trigger produces a
bare timestamp in the console log and nothing else.** No raw window, no `sta_lta_ratio`, no feature
vector reaches the MPU, gets logged, or survives in any persistent store. Ten days of field data
would currently yield trigger *counts* only — not the labeled raw/feature dataset the future
classifier needs, and not recoverable retroactively once the trial window has passed.

High severity — this directly undercuts the stated purpose of the field trial as a data-collection
opportunity, not just a live-detection proof.

**Status: closed on the MCU/host side, 2026-08-14.** `state_machine.cpp`'s `kSensing` case now calls
a real `Bridge.notify("report_footfall_event", schema_version, probability, sta_lta_ratio,
feature_vector)` on every trigger, right before the `kEvent` transition (not from inside `kEvent` as
originally scoped above — `kSensing` is where the triggering window and `sta_lta_result` are still in
scope, and the notify needs both). `sta_lta_ratio` is the real `result.peak_ratio`; `feature_vector` is
no longer a zeroed placeholder — `footfall_features.cpp`'s `footfall_feature_vector()` computes eight
real per-window statistics (`sta`, `lta`, `peak_ratio`, `trigger_index`, window min/max/mean/population
stdev). `probability` is a real, honestly-derived saturating function of `peak_ratio`, not the model
output the schema was originally written assuming — see the new entry below for why that gap is
tracked separately rather than closed here. All of this is host-tested
(`tests/test_footfall_features/`) and `pio run -e native` / `pio test -e native` are green (35/35).

Resolving this also required making `Bridge.begin()`/`Bridge.update()` unconditional in `main.cpp`
rather than gated behind the bench-only `SEISMIC_DEBUG_STREAM_RAW` flag — see the dedicated entry
below.

**Real-hardware linker failure found and fixed, same day, before the live session below could run.**
`footfall_probability_from_ratio()`'s original formula (`1 - exp(-k*(ratio-1))`) passed `pio test -e
native` / `pio run -e native` cleanly but failed to link on the real board:
`arm-zephyr-eabi-g++`/`ld` reported `undefined reference to '__errno'` from `libm_nano.a`'s `expf`
(`wf_exp.c`). Root cause: the real UNO Q firmware build links `--specs=nano.specs --specs=nosys.specs
-nostdlib` against a minimal picolibc-nano math library that does not provide `__errno`, which `expf`
needs internally for domain/range error signaling — a full host libc (used by `pio test -e native`)
always provides `__errno`, so this class of failure is invisible to the host build entirely. Fixed by
replacing the formula with `x^2/(x^2+c^2)` (`x = peak_ratio - 1`, `config.h`'s
`FOOTFALL_PROBABILITY_SATURATION_C = 1.2f`), which needs only multiplication/division and pulls in no
libm transcendental call — re-solved against the same two real anchors (quiet floor 1.13 -> ~0.012,
real stomp 4.60 -> 0.9), re-verified `pio test -e native`/`pio run -e native` green (35/35), then
re-flashed and confirmed the real board links and boots clean. See the probability-placeholder entry
below for the updated formula documentation. **Lesson for future MCU work: a host-green build is
necessary but not sufficient proof of hardware-buildability for any code calling a libm transcendental
function (`exp`, `log`, `pow`, trig, ...) on this toolchain — `sqrt`/`sqrtf` did not hit this (already
in `footfall_features.cpp` for the feature vector's stdev, links fine), but that has not been checked
against every libm entry point, only confirmed empirically for the two actually used here.**

**Closed end to end, live hardware session, 2026-08-14.** With the fix above flashed, the MPU-side
registration (`main.py`'s `Bridge.provide("report_footfall_event", _on_footfall_event)`) was
uncommented and pushed — `debug_stream_raw_seismic_sample` (the previously-registered function)
reconfirmed still running clean afterward (app status `running`, no crash loop, per
`docs/DEVICE_DEVELOPMENT_WORKFLOW.md` §3's discipline). A real firm tap near the geophone then
produced this real MPU-side log line (`arduino-app-cli app logs user:eletect-x --follow`):

```text
INFO:services.reflex_loop:footfall event: mcu_probability=0.865 sta_lta_ratio=4.040 fused_P=0.980 alert=True used=['seismic'] dropped=['acoustic', 'vision'] feature_vector=[0.00387, 0.000958, 4.0397, 511.0, -0.0198, 0.0167, -0.000285, 0.00144]
INFO:services.reflex_loop:[SAFE_MODE] would call drive_horn(schema_version=1, gain_pct=100.0, duration_ms=65535) - not calling (dry run)
```

This is the first real trigger this project has ever gotten end to end from the geophone through
STA/LTA, the notify, `handle_footfall_event`'s fusion/decision, and out the other side as a (dry-run,
`SAFE_MODE`-gated) deterrence decision. `sta_lta_ratio=4.040` maps to `mcu_probability=0.865` under the
fixed formula, consistent with the anchors above; `trigger_index=511` and the other seven feature
values are real per-window statistics, not placeholders; `fused_P=0.980`/`alert=True` show
`cognition.fusion`/`decision` consuming a real MCU-sourced reading for the first time; the horn was
correctly not fired, since `SAFE_MODE` was left on (its code default) for this session. Status:
**closed** — both directions (MCU notify, MPU registration) are proven on real hardware, not just
host-tested.

## `Bridge.begin()`/`Bridge.update()` moved from bench-only to unconditional production infrastructure (14 Aug)

`main.cpp` previously ran `Bridge.begin()`/`Bridge.update()` (and included `Arduino_RouterBridge.h`)
gated behind `SEISMIC_DEBUG_STREAM_RAW` — a flag `config.h` itself documents as "MUST be 0 before any
field sync." `main.cpp`'s own comment had explicitly flagged this as an unresolved decision: reusing a
debug-only flag name to gate production Bridge wiring would be misleading once a real notify or
actuator RPC needed to go live. Closing the raw-seismic-trigger gap above forced the decision — with
the old gate left in place, `state_machine.cpp`'s new `Bridge.notify("report_footfall_event", ...)`
call could never fire in the real field-flag build, silently reintroducing the same gap it was meant
to close.

Resolution: `Bridge.begin()`/`Bridge.update()`/the `Arduino_RouterBridge.h` include are now
unconditional in `main.cpp`. `SEISMIC_DEBUG_STREAM_RAW` itself is untouched and still correctly gates
its own bench-only raw-sample relay in `geophone.cpp` — only the Bridge transport lifecycle moved.
Confirmed safe on both sides this change touches: on real hardware, `Arduino_RouterBridge.h` "only
exists as a real library on the board" (this document's UNO Q board-support entry above) — the old
`#if` was a compile-scope choice, not a hardware necessity, so Bridge is available regardless of any
flag. On the host build, `hostshim/host_shim.cpp` already declares `BridgeClass Bridge` and its
`begin()`/`update()` unconditionally (no `#if` guard), so `pio test -e native` needed no hostshim
changes. The still-commented `Bridge.provide()` actuator registrations in `main.cpp` are unaffected —
this change makes the *notify* direction reachable, it does not register a `provide()` handler or
change the one-at-a-time hardware-verification discipline those still require. Status: **closed** —
decision made and recorded; host build/test green.

## `kSensing` redundant STA/LTA re-run, `GEOPHONE_WINDOW_STALE_MS` drift, and `STA_LTA_DETRIGGER_RATIO` disposition (15 Aug)

**Redundant detector re-run — closed.** `state_machine_tick()`'s `kSensing` case called
`read_seismic_window()` + `sta_lta_detect()` (the ~72k-float-op STA/LTA slide) on every single
`loop()` iteration, unthrottled — `loop()` has no delay of its own, so this ran far more often than
`geophone_service()`'s own cadence gate actually admits new samples (once per
`1000/SEISMIC_SAMPLE_RATE_HZ` ms), recomputing an identical result against an unchanged window most
of the time. Fix: `geophone.cpp`/`geophone.h` gained `geophone_sample_count()`, a monotonically
increasing (non-saturating, unlike `g_samples_written`) count of samples `geophone_service()` has
actually accepted into the ring buffer. `kSensing` now compares successive reads of this against a
`static` local and skips the read+detect entirely when it has not advanced since the last check — same
samples, same STA/LTA logic, same trigger behavior and timing, just not recomputed on iterations where
nothing new arrived. The `static` sentinel (`0xFFFFFFFFu`) guarantees the very first `kSensing` tick
after boot always runs the detector, since `geophone_sample_count()` itself starts at 0 and can never
collide with the sentinel on a real first read.

One correctness risk this introduced and had to be closed in the same pass: `geophone_ok()`'s
liveness previously depended on something calling `read_seismic_window()` regularly enough to notice a
dead sensor via its own staleness check. With `kSensing` now skipping that call whenever the sample
count hasn't moved, a genuinely dead sensor (no new samples arriving at all) would never trip that
check again and `geophone_ok()` would stay stuck at its last value forever. Fix: `geophone_service()`
itself now runs the same `(now_ms - g_last_fill_ms) > GEOPHONE_WINDOW_STALE_MS` check unconditionally,
before its own cadence gate, every time `loop()` calls it (`loop()` still services the geophone every
iteration regardless of reflex state) — so a dead sensor is caught independently of whether anything
downstream is still asking for windows.

Host-tested in isolation (`tests/test_geophone/test_geophone.cpp`, same host-shim approach the
existing cadence-gate tests use): `geophone_sample_count()` advances only on accepted samples (not on
calls the cadence gate rejects), by exactly one per accepted sample, and keeps counting past
`SEISMIC_WINDOW_SAMPLES` rather than saturating. A companion test asserting the proactive staleness
check flips `geophone_ok()` false for a truly dead sensor was written but dropped — `hostshim/Wire.h`
is explicit that it "always succeeds" and is documented as deliberately not modeling real I2C failure
("only ever validated on the bench against a real ADS1115"), so a dead-sensor scenario cannot be
produced against the current host stub without extending that stub beyond this task's scope. `pio run
-e native` and `pio test -e native` both green (37/37 test cases) after this change; a fix discovered
in the same pass — `geophone_init()` was not resetting `g_sample_count`, leaking count state across a
re-init (surfaced immediately by the new tests running in the same binary) — is bundled in since it is
required for the new counter to behave correctly at all, not a separate gap.

**`GEOPHONE_WINDOW_STALE_MS` vs. the real measured field-flag rate — closed.** The constant's own
comment says it should be "1.5x the time [a full window] should take" to fill; it was `3072` ms, which
is 1.5x the *nominal* 250 Hz fill time (`512/250*1000=2048`, `*1.5=3072`), not the real measured
226.98 Hz rate `STA_SAMPLES`/`LTA_SAMPLES` are already grounded against elsewhere in the same file
(this document's "STA/LTA field-flag rate re-measurement" entry). At 226.98 Hz the same formula gives
`512/226.98*1000≈2256`, `*1.5≈3384` ms. Code and documented rationale disagreed — fixed by updating the
constant to `3384` (comment's formula honored, not weakened) rather than editing the comment to match
the stale value, since the formula is deliberately conservative real-hardware margin, not a number to
retune down to match convenience.

**`STA_LTA_DETRIGGER_RATIO` — closed, removed as dead code.** Previously carried as an unused
`#define` in both `SEISMIC_DEMO_MODE` branches of `config.h`, flagged dead since the "STA/LTA
field-flag rate re-measurement" entry above: `grep`ping `device/mcu` for `DETRIGGER_RATIO` found no
reference outside its own `#define`, and `state_machine.cpp`'s `kEvent` case only ever exits on
`EVENT_MAX_MS` elapsed, never a ratio — there was no detrigger logic to calibrate this value against.
Decision: remove the constant rather than either (a) invent real ratio-based detrigger logic in
`kEvent` with no data to validate a threshold against, which would violate the hard rule that these
constants are only set from real stomp data, or (b) leave an unwired placeholder indefinitely. Judged
that timeout-only exit from `kEvent` is fine as the current design — `EVENT_MAX_MS` already bounds how
long an event stays "active" before cooldown, which is the actual thing this state exists to bound.
A real ratio-based early-exit (saving `EVENT_MAX_MS`-minus-actual-decay-time of deterrence latency
per event) remains a legitimate future feature, but only alongside real multi-event stomp data
(see the "multi-trial stomp validation protocol" work this document/`HANDOVER.md` track separately) to
set a specific threshold against — not before. `device/mcu/README.md`'s bench stomp-test write-up
updated to match (previously described `STA_LTA_DETRIGGER_RATIO` as extant-but-dead-code; now
describes it as removed). Status: **closed** — decision made, documented, and reflected in code,
`config.h`'s comments, and `README.md`; nothing left `#define`d but uncalibrated.

All three items verified together: `pio run -e native` and `pio test -e native` both green (37/37 test
cases, including the 2 new `test_geophone` cases) after each change in this section, not just at the
end. Hard boundary respected — `git diff` on `config.h` touches zero characters of the
`STA_LTA_TRIGGER_RATIO`, `STA_SAMPLES`, or `LTA_SAMPLES` `#define` lines themselves (only comment text
mentioning their names by name, and the unrelated `GEOPHONE_WINDOW_STALE_MS`/`STA_LTA_DETRIGGER_RATIO`
lines above/below them).

**Multi-trial stomp validation protocol — run 15 Aug, real hardware.** The single-stomp bench test
above (14 Aug) validated `STA_LTA_TRIGGER_RATIO` against exactly one real stomp; it could not say
anything about trial-to-trial variance in a real human stomp's ratio, or about `report_footfall_event`
firing reliably across repeated triggers rather than once. Executed against real hardware (build
flashed via `arduino-app-cli app stop`/`app start` over SSH, board discovered at `192.168.1.10` since
mDNS resolution of `eletect-x.local` fails from both Windows git-bash and WSL2 — see
`docs/eletect-x-applab-notes.md`), field config (`SEISMIC_DEMO_MODE=0`,
`EVENT_MAX_MS=15000`/`COOLDOWN_MS=20000`), `SEISMIC_DEBUG_VERBOSE=1` temporarily during the run, 12
stomps at 60 s intervals, 60 s quiet baseline before the first stomp. Console captured via
`scripts/capture_geophone_console.py` over the board's existing socat/nc bridge
(`scripts/bench-logs/stomp_protocol_20260815.log`, gitignored, reproducible via the script).

**MCU-side results (from `[trigger]`/`[notify]` console lines):**

- **11/12 stomps detected (91.7%).** Trigger ratios: 4.18, 4.01, 4.20, 4.34, 4.05, 4.18, 4.32, 4.36,
  4.11, 4.60, 4.20 — mean **4.232**, stdev **0.166**, n=11.
- `[notify]` probabilities: mean **0.8784**, stdev **0.0105**, n=11.
- **One genuine near-miss** (stomp 4 of 12, between the t=313251 and t=432745 triggers): peak ratio
  **3.80**, just under the 4.0 threshold — confirmed via the surrounding `[seismic]` lines, not an
  unexplained gap. A real human stomp landed below threshold; not a bug.
- **Zero false triggers** across the full pre-stomp quiet baseline (n=688 samples, mean ratio
  **1.149**, stdev **0.031**, range 1.08–1.23).
- Post-trigger-12 tail: ratio decayed back to the quiet floor (~1.10–1.21) within ~9 s of the last
  trigger and stayed quiet through the rest of the capture. The capture window (`--duration 820`)
  ended at t=871966 ms, before the state machine's `EVENT_MAX_MS + COOLDOWN_MS` (35 s) dwell from the
  last trigger completed (would re-arm to `kSensing` at t≈888619 ms) — so this run captured a quiet
  *sensor reading* during the tail of `kCooldown`, not a full 60 s trailing baseline with the system
  back in armed `kSensing`. Not a gap in the result (the sensor's return to quiet floor is the thing
  being checked), just a scope note on what wasn't captured.

**MPU-side results (`report_footfall_event` → `reflex_loop.handle_footfall_event`):** confirmed via
the raw Docker json-log file on the board (`docker logs` itself fails on this container with
`invalid character '\x00' looking for beginning of value` — the log file has accumulated across
multiple days/restarts without rotation and its stream reader chokes partway through; worked around
by reading the file directly, `docker run --rm -v /var/lib/docker/containers:/logs:ro alpine grep/head/tail
...` using the `arduino` user's `docker` group membership, since passwordless `sudo` isn't configured
on the board). All **11/11** MCU-side triggers produced a matching MPU-side `footfall event` log line,
timestamps 18:09:11–18:20:13 UTC, all with `alert=True`:

- MPU-computed `sta_lta_ratio` matches the MCU's own value to logging precision (e.g. 4.182≈4.18,
  4.596≈4.60) — mean **4.234**, stdev **0.165**.
- `fused_P`: 0.982, 0.979, 0.982, 0.984, 0.980, 0.982, 0.983, 0.984, 0.981, 0.986, 0.982 — mean
  **0.9823**, stdev **0.00195**.
- Zero MPU-side false alerts logged outside these 11 events in the surrounding window.
- Each event followed by the expected `[SAFE_MODE] would call drive_horn(...) - not calling (dry run)`
  line — reflex loop is still in dry-run mode, horn actuator not actually driven (expected, unrelated
  to this validation).

Status: **closed** — 11/12 physical detection rate with the one miss explained by a genuine
sub-threshold stomp (not a system fault), zero false positives on either side of the Bridge, and
`report_footfall_event`/`fused_P`/`alert` confirmed end-to-end for every MCU trigger. Board re-synced
and re-flashed with `SEISMIC_DEBUG_VERBOSE` reverted to `0` after the run, confirmed quiet
(ratio 1.09–1.15) on the console before leaving it.


**Camera's IR-cut filter may be fixed/visible-light-only, not day/night switchable - urgent, unverified against the physical unit, flagged 17 Aug 2026.** The camera module in the BOM (Arducam IMX462, product B0496) has its own published datasheet stating "Integral IR-cut Filter, visible light only" (blog.arducam.com/downloads/datasheet/B0496_IMX462_USB3.0_Camera_Module_Datasheet.pdf), with no day/night ICR-switching mentioned - a fixed filter, not a switchable one. Arducam separately sells a distinct IMX462 SKU explicitly marketed as "Day and IR Night Vision" with automatic IR-cut switching and bundled 940nm LEDs - a different product from B0496. If the physical camera actually in hand is the fixed-filter B0496 variant, the filter blocks the 940nm band before it reaches the sensor: the IR illuminator already purchased (hardware/bom/procurement-status.md 2) would be producing light the camera cannot see, and night footage would be visible-light-only - effectively black in the field, since no visible illumination source is planned. Not caught in ~3 weeks of camera bring-up because every confirmed test so far (V4L2 device discovery, capture_check.py, MJPG/YUYV format confirmation) exercised daylight/visible capture only, never IR sensitivity specifically.

Cheap, decisive test, not yet run: in a dark room, power the real IR illuminator board next to the real camera and grab a frame via capture_check.py (or App Lab's live view). If the illuminated scene is visible in the capture, the sensor is IR-sensitive regardless of what the datasheet says for a differently-labeled SKU; if the frame is black, the filter is blocking it as the datasheet suggests. Severity: high if confirmed - directly threatens the stated contest-footage goal for any dusk/night elephant activity, and the field deployment's most likely detection windows. Effort: about 10 minutes of bench time to test; if confirmed bad, remediation (sourcing the actual day/night SKU, or a NoIR conversion) needs lead time against the 20 Aug deadline. Status: open, unverified - test before any further camera/IR window work this week.
