# Arduino UNO Q + Edge Impulse — platform research

Compiled 2 Sept 2026 from the Arduino UNO Q docs, Edge Impulse docs (Studio + Linux SDK), the
`edgeimpulse/agent-tools` App Lab skill, and the Arduino / Edge Impulse forums + GitHub issues.
Purpose: stop re-deriving the same platform facts every session, and pin down real fixes for the
problems that keep blocking the device track — the recurring crash-reboots, the dead GPU delegate,
camera exposure at night, headless flash/deploy, and the vision recall bar.

Every claim in the files below is linked to its source. Anything not confirmed against a primary
source is called out in each file's "Unverified / open" section — check those before quoting a
number externally.

## Files

| File | Covers |
|---|---|
| [arduino-uno-q-power-and-ops.md](arduino-uno-q-power-and-ops.md) | Power inputs (USB-C vs VIN vs 5V pin), real current draw, PD / `power_operation_mode`, watchdog, RTC, headless ops, hardening, clean shutdown. **The reboot fix lives here.** |
| [uno-q-forum-findings.md](uno-q-forum-findings.md) | Real-world forum/GitHub reports and fixes across 7 topics: reboots (brownout **and** OOM), STM32 flashing, GPU delegate, camera, App Lab / RouterBridge breakage, RTC, watchdog. |
| [app-lab-flash-and-routerbridge.md](app-lab-flash-and-routerbridge.md) | Canonical headless build/flash/deploy via `arduino-app-cli`, FQBN menu options, RouterBridge msgpack-RPC protocol spec, MCU recovery ladder, EI model bundling. Includes corrections to our prior understanding. |
| [edge-impulse-linux-inference.md](edge-impulse-linux-inference.md) | Whether GPU/NPU/DSP acceleration is real on QRB2210 (it is not), Flex delegates, how the EI runner captures camera frames, locking exposure/gain/AGC, EON Compiler + no-retrain latency levers. |
| [edge-impulse-studio-vision-tuning.md](edge-impulse-studio-vision-tuning.md) | Raising Elephant/Boar per-class recall past 92% without wrecking precision: YOLO-Pro knobs, block choice, augmentation, class weighting, object-tracking post-processing, EON Tuner search space, finding silent-miss images. |
| [reference-links.md](reference-links.md) | Raw source link list (Edge Impulse docs sitemap + curated Arduino UNO Q / App Lab / integration set) the prose files above were distilled from. Not itself a findings doc. |

## The reliable fixes / methods, by problem

### 1. Recurring spontaneous crash-reboots (the top blocker)

Two independent causes are plausible and both have a concrete mitigation. Do both.

**A. 5V rail brown-out (most likely — matches our "no panic/watchdog/thermal/OOM trace, clock
jumps" signature).**

- The board draws ~0.66 A idle and ~0.9 A with all four A53 cores busy, *before* camera /
  USB-Ethernet / actuators. Arduino's own spec: *"Use a stable 5 V / 3 A source. If the supply
  current-limits during peaks, voltage hang may cause resets."* A passive USB-C hub fed from a
  charger it never PD-negotiates with cannot hold 5 V through load transients. Caps on 5 V do not
  fix a brown-out (Arduino moderators, repeatedly).
- **Best fix: power the board through the VIN pin (7–24 V) from a regulated DC supply.** VIN goes
  through the on-board LMR51440 buck straight onto 5V_SYS and bypasses USB-C PD negotiation and the
  hub's sagging 5 V rail entirely. Size the supply for the full 5 V load with margin; keep VIN
  leads short and thick.
  - Caveat: applying VIN **disables the USB-C VBUS output** (`usb_vbus: disabling`). USB
    peripherals (camera, USB-Ethernet) then need their own self-powered hub.
  - Caveat: on pre-Nov-2025 images (no `/etc/buildinfo`) the USB port also boots in *device* mode
    under VIN — needs a systemd unit writing `host` to
    `/sys/kernel/debug/usb/4e00000.usb/mode` before Docker starts
    (`github.com/Psalmustrack/arduino-uno-q-usb-fix`). Check `cat /etc/buildinfo` first; if
    present, Arduino already fixed this upstream.
- **If staying on USB-C:** genuine 5 V / 3 A (15 W+) brand-name charger driving the board's USB-C
  port **directly, no hub between charger and board**; camera + USB-Ethernet on a separately
  powered downstream hub so their inrush never touches the board rail.
- **`power_operation_mode: default` with no `port0-partner` is a hub quirk, not a hard 500 mA
  cap.** It means the upstream presents nothing on the CC pins (no PD, no Type-C current
  advertisement), so the board *assumes* only the USB-default budget is guaranteed — but it still
  pulls what it needs from VBUS; the hub just can't supply the transient. PD is **not** required
  on this board to exceed 500 mA (it draws more and runs for hours). To get a real contract, plug
  a PD / Type-C source **directly** into the board's USB-C port and check
  `cat /sys/class/typec/port0/power_operation_mode` (should become `3.0A` or `usb_pd`).
- **Never hang high-current peripherals off the header 5 V pins** — they are `5V_USB_VBUS`
  pass-through from the same rail the SoC runs on. IR/LED driver + actuators get their own supply,
  MOSFET-switched, common ground, only the logic/gate signal back to the board.

**B. Linux-side memory pressure / OOM (the 1.7 GB board).**

- Arduino's "board software out of date" help article states the updated Linux image enables ZRAM
  specifically because *"random restarts of the desktop environment or applications"* are
  *"typically caused by memory pressure."*
- **Fix: flash the latest Linux image** (App Lab → Settings → Operating system → Flash Board, or
  `arduino-flasher-cli flash latest --preserve-user`), confirm ZRAM is on (`zramctl`), cap the
  Python / EIM footprint, and keep anything heavy (an IDE and its background services) off the
  board.

**Decisive test + instrumentation.** Switch to VIN (or a direct 5 V/3 A supply, no hub) and watch
MTBF. Around each crash: `journalctl -k -b -1 --no-pager | tail -200` (expect an abrupt stop, no
trace), `last -x`, and a cron logging `/sys/class/power_supply/*/voltage_now` +
`/sys/class/typec/port0/power_operation_mode` every 5 s to catch the dip.

**Recovery / survivability.** There is **no documented Linux hardware watchdog** to lean on
(`ls -l /dev/watchdog*` on the device to check). Use **Monit** (Arduino's hardening guide
recommends it) for app auto-restart + alerts. Enable the **STM32 IWDG** in the reflex firmware so
the MCU self-recovers on a rail dip the SoC survives. A passive field logger must be a
`Restart=on-failure` systemd unit — a bare foreground process does not survive a reboot (as the
2 Sept dawn soak proved). `arduino-app-cli` service restart *ordering* after an apt self-update is
itself fragile (`arduino/arduino-app-cli#521`).

### 2. `libtensorflowlite_gpu_delegate.so: cannot open shared object file` (GPU/NPU acceleration)

**There is no supported GPU/NPU/DSP acceleration path on the UNO Q. Stop trying to make the GPU
`.eim` run. Ship the CPU int8 EON `.eim`.**

- QRB2210 has **no NPU / Hexagon Tensor Processor** — Qualcomm's own IoT selector guide lists NPU
  as N/A for this part. It has an Adreno 702 GPU and a low-power Hexagon DSP for audio/sensor
  fusion, not an ML tensor path.
- The EI "Linux Arduino UNO Q (GPU)" / `runner-linux-aarch64-gpu` target compiles in EI's cloud
  but needs `libtensorflowlite_gpu_delegate.so` (never shipped, not in any apt repo — our on-board
  search was correct) **and** a working Qualcomm OpenCL/GLES stack. The UNO Q image ships Mesa
  Turnip (Vulkan-only) with no proprietary Adreno OpenCL, so the delegate cannot initialise even
  if the `.so` were present. Forum users hit exactly this; no official fix as of mid-2026.
- The missing-`.so` line is a **silent CPU fallback, not a hard failure** — inference still runs.
- The QNN / Hexagon-HTP path (`USE_QUALCOMM_QNN`) is real but targets higher-tier Dragonwing parts
  (QRB6490 / Rubik Pi 3, QRB5165 / RB5). QRB2210 has no HTP; the QNN userland is not on the image.
- Flex delegates add operator coverage, run on CPU, and do **not** accelerate.
- **CPU (4× Cortex-A53 + NEON + XNNPACK, int8, EON) is the ceiling.** Our ~138 ms/frame is normal.
  Acceleration only becomes real if the project moves to VENTUNO Q / an HTP-equipped board.
- Cut latency by model shape instead: smallest input resolution that still separates the classes,
  grayscale if the detector tolerates it, lighter backbone alpha, confirm multi-thread XNNPACK,
  match capture resolution to model input.

### 3. Locking camera exposure / gain / AGC at night

- There is **no runner flag or env var** for exposure/gain/AGC.
- **Supported, portable way (matches our existing V4L2 side harness): our app owns the camera.**
  Open `/dev/video2` (`/dev/video0`/`1` are the Venus encoder/decoder, not the camera) with V4L2,
  set `auto_exposure=1` (manual), `exposure_time_absolute ≈ 256`, fixed gain tuned to the IR
  illuminator, then feed frames to the model via the Python SDK
  (`runner.get_features_from_image(img)` + `runner.classify(features)`) or the
  `edgeimpulsevideoinfer` GStreamer element. This bypasses the runner's camera code entirely.
- If keeping the CLI runner's camera: force the camera onto `v4l2src` and pass
  `extra-controls="c,auto_exposure=1,exposure_time_absolute=256,gain=<n>"` via `--gst-launch-args`;
  verify mid-stream with `v4l2-ctl --get-ctrl`. On the UNO Q the camera often comes up under
  `libcamerasrc`, which does not expose exposure/gain cleanly — prefer owning the camera.
- Known camera gotchas: `DmaBufAllocator … Could not open any dma-buf provider` →
  `sudo usermod -a -G kvm arduino`. `"Cannot find any webcams at initCamera"` → pass an explicit
  `libcamerasrc camera-name='<name>'` pipeline (name from `gst-device-monitor-1.0`). High-res JPEG
  streaming causes unresolved WebSocket drops — capture locally, don't live-stream.

### 4. Headless build / flash / deploy

- **One command does everything: `arduino-app-cli app start <path>` (or `app restart <path>`).**
  It compiles the sketch in-process (arduino-cli Go library, FQBN `arduino:zephyr:unoq`, appends
  `:wait_linux_boot=app`), uploads to the STM32 over the on-board debug link, then
  `docker compose up -d` for the Python side. There is no separate build or flash verb.
- **Flash confirmation** is inferred from the launch log
  (`Board platform: arduino:zephyr (<ver>)…` → `Used library …` → clean upload → `✓ App "<name>"
  started successfully`), then `app list` shows `running`. There is no checksum/verify line — for
  a real check, call an MCU `Bridge.provide` method from Linux or watch
  `journalctl -u arduino-router -f`.
- **Do NOT pin `Arduino_RouterBridge` in `sketch.yaml`** — bundled in `arduino:zephyr` core ≥ 0.55
  along with `Serial`; `arduino-app-cli` auto-removes an unpinned ref and a pinned one can break
  the build. This is the cause of most post-upgrade App Lab breakage (also: remove any duplicate
  `Arduino_RouterBridge` from `hardware/libraries`; the `flash_mode` board option was removed).
- **MCU recovery ladder:** retry `app restart` → `app stop` (toggles the reset GPIO) →
  `arduino-app-cli system update` (reinstalls the core + `BurnBootloader` with the **`jlink`**
  programmer — there is no USB-DFU bootloader for the STM32) → full EDL Linux reflash
  (`arduino-flasher-cli flash latest`, short the EDL pins before USB, `--preserve-user`).
  "Firehose response / XML parser error" when flashing the image → use a **USB-C-to-USB-C** cable,
  not USB-A-to-USB-C; on Linux hosts blacklist `qcserial`.
- Clean shutdown is **`sudo halt`** (not `sudo shutdown now`, which reboots), then pull power in
  the ~1–2 s after the blue LED goes dark.
- Run at boot: `arduino-app-cli properties set default user:<app>`. Remote field access:
  Tailscale + SSH; disable `adbd` in production.

### 5. RouterBridge runtime rules

- msgpack-RPC over `/var/run/arduino-router.sock`; MCU `Serial1` ↔ Linux `/dev/ttyHS1` @ 115200;
  **256-byte max message** (`Bridge.notify` silently drops oversized; `Bridge.call` raises).
- Frames: `[0,id,method,[args]]` request / `[1,id,err,res]` response / `[2,method,[args]]` notify.
- **Never call `Bridge.call()` / `Serial.print()` / `Monitor.print()` inside a `Bridge.provide()`
  callback** — it re-enters the RPC layer and deadlocks. Set a flag, act in `loop()`. Use
  `Bridge.provide_safe()` for handlers that touch Arduino I/O (`digitalWrite` etc.).
- Call `Monitor.begin()` *after* `Bridge.begin()`. Use `Bridge.notify()` for void calls. Call
  `Bridge.update()` each `loop()`. Allow ~2–3 s settle after boot before the first call.
- Python import is `from arduino.app_utils import App, Bridge` (the `arduino.bridge` +
  `@bridge.on_call` decorator style in older references is superseded).
- No numbered protocol-version field exists in RouterBridge itself — the message-type table is the
  contract. (Our project's own `BRIDGE_SCHEMA_VERSION` is an application-level field on top.)

### 6. Raising Elephant/Boar recall past the 92% bar

The gap is silent misses (zero boxes on ~11% Elephant / ~23% Boar test images) with high
precision — a **data/label problem**, not an architecture problem. Highest-leverage moves:

1. **Fix the data first.** Use Model testing per-sample drill-down + Live classification's
   "show only missed objects" filter on held-out night/dawn clips to export the exact miss set,
   cluster it (night / dawn AGC / occluded / distant), and backfill those clusters.
2. **Re-scan existing training images with AI labeling** (OWL-ViT / Gemini zero-shot + GPT-4o
   cleanup). Unlabelled animals in training data actively teach the detector to suppress
   detections — the classic cause of this exact symptom.
3. **Stay on YOLO-Pro** (only built-in bounding-box block for a CPU/MPU target; SSD-FPN is
   Linux/high-compute, FOMO is centroids and breaks on large animals filling the frame, TAO is
   deprecated). Move up one size (`small`/`medium`), keep "Attention with SiLU", pre-trained
   weights ON, backbone **not** frozen.
4. **Augmentation: spatial Medium** (crop + rotate + flip, **not** High — High adds Mosaic, which
   hurts a 2-class large-animal set). Push **color-space augmentation to Medium/High** as the
   built-in proxy for lighting/exposure variation. Real low-light/IR/blur/noise simulation needs
   Expert Mode custom layers or offline pre-augmented uploads.
5. **Class-weight toward Boar** ("Auto-weight classes" or Expert Mode `class_weight`); more
   epochs + a higher "Early stopping start epoch" so training doesn't cut off while recall is
   still climbing.
6. **Keep the model threshold low (0.05) for recall; recover precision temporally, not by raising
   it.** Add the object-tracking post-processing block (tracking-by-detection + Kalman; raise
   `Keep grace` to bridge brief occlusions — this recovers event-level recall) plus
   consecutive-frame voting to kill one-frame dawn false positives.
7. **EON Tuner probably can't beat the champion** because YOLO-Pro may not be a valid search-space
   `model` id (published templates show only SSD-MobileNet and FOMO) — verify in Studio; if
   unsupported, hand-tune. If supported, pin a narrow custom template to YOLO-Pro around the
   champion, target = UNO Q, objective ranked recall-first.

## What this research does NOT settle

- Whether the reboot fault is *actually* brown-out vs OOM on our specific board — needs the VIN
  swap + instrumentation run above. Physical, user-present.
- Exact `arduino:zephyr:unoq` menu-option catalogue and defaults — run
  `arduino-cli board details -b arduino:zephyr:unoq` on the board.
- YOLO-Pro numeric defaults (epochs / LR / batch / resolution) and per-size latency on QRB2210 —
  read them in Studio / the on-device profiler.
- Whether Performance Calibration and genuinely independent per-class thresholds work for object
  detection in the current Studio build.
- **How a project version snapshot is actually created and restored via the API** — the OpenAPI
  spec has `listVersions`/`updateVersion`/`deleteVersion`/`makeVersionPrivate` under
  `/api/{projectId}/versions` but no `createVersion`/`restoreVersion` verb, even though this
  project has created snapshots in practice (job `53262402`, 30 Aug) — creation is most likely
  dispatched as a job type through the general `/jobs` endpoint, not confirmed. Needs a live API
  discovery pass (list job types, or capture the network call the Studio UI makes), not more
  doc-reading. Full detail in
  [edge-impulse-studio-vision-tuning.md](edge-impulse-studio-vision-tuning.md)'s 4 Sept addendum.

Each file's own "Unverified / open" section has the full list. Two other questions Step 6 of the
Boar-gap close-out plan had flagged as open are now closed, not just unresolved-and-listed: the
model-testing/threshold API surface (confirmed no shortcut exists — the training script's
classify-job-per-threshold sweep is the correct approach, not a workaround) and Experiments
(confirmed real — multiple impulses coexist in Studio's UI — but confirmed *not* reachable from the
API-only training script, since no impulse-creation endpoint exists in the OpenAPI spec). See the
same addendum for both, with sourcing and caveats.
