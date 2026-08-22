# MPU — QRB2210 (event cognition, Debian/Python)

Vision detector (Adreno/OpenCL), log-odds fusion, contextual-bandit deterrence, SQLite experience,
Bridge RPC, LoRa uplink. On-device vision model in `models/`. Bridge function signatures are
frozen against [bridge/schema.md](bridge/schema.md) — that file, not this README, is the source of
truth for what each function does; both sides (`device/mcu`, here) are hand-written against it
independently (`ENGINEERING_CONVENTIONS.md` §6).

## Two build paths — read this before touching either

- **`ruff check .` / `pytest -q`** — host-only lint/test harness. `pyproject.toml` has no runtime
  dependency on `arduino.app_utils` (the module that provides `Bridge`) — it only exists on the
  QRB2210's own Python install, so nothing under `bridge/`, `perception/`, `cognition/`, or
  `services/` may import it at module scope. This never produces a running App.
- **App Lab (or the Arduino App CLI over SSH)** — the only path onto real hardware. Fed by
  `scripts/sync-to-board.sh`, which one-directionally mirrors this tree (minus `tests/`, `bench/`,
  `pyproject.toml`, `__pycache__/`) into the board's App folder as `python/`. Never hand-edit the
  board's copy — edit here, re-run the sync script, then build/run from App Lab.

## Build / test

```powershell
cd device\mpu
ruff check .
pytest -q
```

## Sync to board

```bash
# from the repo root, once the board is reachable over SSH (Network Mode)
scripts/sync-to-board.sh
```

Syncs both `device/mcu` and `device/mpu` into the real `EleTect-X` App. The disposable ping bench
below is a separate App and is **not** covered by this script — see its own procedure.

## Layout

```text
bridge/
  schema.md      Bridge contract — source of truth for every function below
  rpc.py         signatures + docstrings for all 8 schema.md functions, no Bridge wiring yet
perception/
  camera.py      IMX462 V4L2 capture wrapper — open/capture/burst/release, no trigger/IR logic
  (vision INT8 detector itself: future build call)
cognition/
  fusion.py      weighted log-odds fusion (CONTEXT.md 4) — pure function, no Bridge/hardware
  decision.py    alert gate on the fused probability — pure function
  bandit.py      epsilon-greedy tier selection + habituation floor — pure, RNG injected
  experience.py  SQLite experience store (triggers/attempts/action values), the only I/O here
  config.py      fusion weights + bandit hyperparameters and tier ladder — one rationale each
services/
  config.py      MPU-side tuning constants, one rationale each (mirrors device/mcu/include/config.h)
comms/           LoRa uplink (future build call)
models/          on-device vision model export, gitignored (*.tflite)
tests/           host-only contract + config tests, never synced to the board
bench/ping/          disposable hello-world Bridge round trip, see below
bench/camera_check/  disposable camera capture-and-save check, see below
bench/demo_replay.py host-only replay of both reflex-loop entry points, see below
```

`bridge/rpc.py` ships as **signatures and docstrings only**, deliberately not wired up with
`Bridge.provide()` — `DEVICE_DEVELOPMENT_WORKFLOW.md` §3 documents a live, reproducible bug where
registering an extra `Bridge.provide()` function broke every previously-working function on the
same sketch. The practical discipline that earns: register one function at a time on real
hardware, testing between each addition, not a batch of eight from a host build with no board
attached. The MCU side observes the same caution (`device/mcu/src/main.cpp`).

## Ping bench — hello-world Bridge round trip (MCU → MPU direction)

Rung 0 proved a Bridge round trip **Python → MCU** (the stock Blink LED example — Python toggling
a GPIO the MCU sketch drives). Nothing has yet proven the reverse: **MCU → Python**, which is the
direction every MCU→MPU `notify` in `bridge/schema.md` needs (`report_footfall_event`,
`report_acoustic_event`, `report_system_status`). `bench/ping/` is a complete, disposable App Lab
app that exercises exactly that — one `Bridge.call("ping", token)` from the MCU sketch every 2 s,
answered by exactly one Python-provided function. It is deliberately separate from the real
`EleTect-X` App and from `bridge/rpc.py`'s schema stubs: nothing here is schema-shaped, and it must
never be merged into the real App.

**Why `call` and not `notify`, even though the real schema functions this direction use `notify`:**
`Bridge.call()` returns a verifiable `pong` reply, which is the better bench test — a `notify` firing
silently gives no positive confirmation it was received at all. See the precision note in
`docs/KNOWN_GAPS.md` about exactly what this bench does and does not prove.

### Prerequisites

- Board reachable over SSH in Network Mode (`DEVICE_DEVELOPMENT_WORKFLOW.md` §2).
- No other App using the same Bridge socket registered with a conflicting `ping` name.

### Running it

1. Push the bench app to the board (not covered by `scripts/sync-to-board.sh` — a plain one-liner,
   since this app is throwaway):

   ```bash
   rsync -avz device/mpu/bench/ping/ arduino@<board-host>:/home/arduino/ArduinoApps/ping-bench/
   ```

2. Open the app in App Lab (or `ssh` in and use the Arduino App CLI) and build/run it.
3. Watch the console. A successful round trip looks like this, repeating every 2 s:

   ```text
   MCU:  [ping] sent token=<n>
         [ping] reply=pong:<n> rtt=<ms>
   MPU:  [ping] token=<n> -> pong:<n>
   ```

   `<n>` matches on both lines for a given round trip; `rtt` is the MCU-observed round-trip time in
   milliseconds.

### If it doesn't build or the reply never arrives

Three details in `sketch/main.cpp`, `python/main.py`, and `app.yaml` are marked
`// UNVERIFIED` / `# UNVERIFIED` inline — written from `DEVICE_DEVELOPMENT_WORKFLOW.md` §3's
description of the Bridge API, not checked line-by-line against a real generated App. If the sketch
won't compile or the reply never arrives, diff against the stock Blink LED example (confirmed
working on this board at Rung 0) before assuming the Bridge itself is broken — it is more likely one
of these three unverified details than a fundamental Bridge failure.

**Status: pending hardware.** This procedure has not yet been run against real hardware — see
`docs/KNOWN_GAPS.md`.

## Camera bench check — capture-and-save against the real IMX462

`perception/camera.py` is a pure V4L2 capture wrapper (`ENGINEERING_CONVENTIONS.md` §1's earned
`capture_frame()` interface boundary) — fully unit-tested against a fake capture device
(`tests/test_camera.py`), but never yet run against the real Arducam IMX462 (ADR 0001).
`bench/camera_check/capture_check.py` is a disposable, non-App-Lab script (needs no Bridge, no
`app.yaml`) that opens the real camera, captures one frame plus a short burst, saves them to disk,
and prints exactly what the device negotiated — resolution, pixel format, and FPS — which is what
turns `docs/KNOWN_GAPS.md`'s IMX462-defaults entry from an assumption into a measured fact.

It runs in two places, both driving the same `perception.camera.Camera` class:

- **The board**, over SSH, the actual V4L2/target-platform path (`--backend v4l2`, or the
  `--backend auto` default, which resolves to V4L2 on Linux).
- **A Windows/macOS dev host** with `pip install opencv-python` (not a `pyproject.toml` dependency —
  see "Two build paths" above), using `--backend any` (or `auto`'s off-Linux default) — the IMX462
  is a UVC device, so DirectShow/AVFoundation see it too. Useful for confirming the physical camera
  works *before* a board session is available; the V4L2 path itself stays pending hardware either
  way.

### Camera check prerequisites

- **Board run:** board reachable over SSH in Network Mode; camera plugged into the board's USB-C
  port via the spare USB hub (`hardware/bom/procurement-status.md`) — the port can't be both a dev
  link and a camera host at the same time, so run this over Network Mode, not a USB dev cable; and
  `python3-opencv` present on the board's Debian image (unverified — `docs/KNOWN_GAPS.md`).
- **Host run:** `pip install opencv-python` and the IMX462 plugged into a USB port directly.

### Running the camera check

Board (not covered by `scripts/sync-to-board.sh` — a plain rsync one-liner, same as the ping
bench):

```bash
rsync -avz --exclude='__pycache__' device/mpu/ arduino@<board-host>:/home/arduino/camera-check/
ssh arduino@<board-host> "cd /home/arduino/camera-check && python3 bench/camera_check/capture_check.py --probe"
```

Dev host (from the repo root, camera plugged in):

```powershell
python device\mpu\bench\camera_check\capture_check.py --backend any --out-dir <scratch-dir>
```

### What a successful capture looks like

```text
Opening '/dev/video0' (backend=auto, requested 1920x1080 MJPG)...
Negotiated: device=/dev/video0 1920x1080 fourcc=MJPG fps=30.0

Single frame:
  saved output\single.jpg (187342 bytes, index=0, t=1.203s)

Burst (5 requested):
  saved output\burst_00.jpg (183210 bytes, index=0, t=1.245s)
  saved output\burst_01.jpg (185004 bytes, index=1, t=1.279s)
  saved output\burst_02.jpg (184556 bytes, index=2, t=1.312s)
  saved output\burst_03.jpg (186012 bytes, index=3, t=1.347s)
  saved output\burst_04.jpg (183890 bytes, index=4, t=1.381s)
  inter-frame intervals (s): [0.034, 0.033, 0.035, 0.034]

Done. 6 frame(s) saved to output
```

Non-trivial file sizes (tens to hundreds of KB, not near-zero) and a `Negotiated:` line matching
real numbers, not the requested ones, are the two signals that this is a real frame, not a
black/garbage capture. **Expected resolution/format is 1920×1080 MJPG — that is the product
listing's stated spec, not yet confirmed against this specific unit** (`docs/KNOWN_GAPS.md`).

### If no `/dev/video*` node shows up

Run `--probe` first — it lists `/dev/video*` nodes and, if `v4l2-ctl` is installed, the camera's
full format list. A completely empty listing with the camera physically plugged in points at a USB
host-mode question (does the UNO Q's USB-C port enumerate a host device at all while powered from
VIN?), not a bug in `capture_check.py` or `camera.py` — see `docs/KNOWN_GAPS.md`.

**Status: pending hardware.** Written and host-tested against a fake capture device; not yet run
against the real IMX462 on the board or the dev host.

## Demo replay — both reflex-loop entry points, no hardware

`bench/demo_replay.py` runs two passes against the real `services/reflex_loop.py` — no board,
camera, or Bridge involved either way.

**Pass 1 (seismic, real bench data)** feeds `handle_footfall_event()` — the actual sense → fuse →
decide pipeline, not a mock of it — the real STA/LTA ratios and fused probabilities
`docs/KNOWN_GAPS.md`'s "Multi-trial stomp validation protocol" entry captured on real hardware on
2026-08-15 (12 stomps, 11 detected, one genuine sub-threshold near-miss), and narrates each step to
the terminal. The actuator/camera callables passed in raise if ever called, since this always runs
`safe_mode=True`.

**Pass 2 (acoustic routing, illustrative)** calls the real `handle_acoustic_event()` once per
`AcousticClass` value, to make ADR 0007 §5's three-way routing split (landed alongside this pass)
watchable rather than just provable: gunshot bypasses `fuse()` entirely and prints the real
`[SAFE_MODE]` alert line the event actually logged (captured from the real logger, not re-typed);
chainsaw/vehicle/animal_call fuse as one shared ACOUSTIC modality and print the live `fused P`,
identical across the three; ambient fuses as unavailable, with `acoustic` visible in
`fusion.dropped`. Every input in this pass uses one fixed synthetic confidence, 0.87 — **this is not
captured bench data**, unlike pass 1: no acoustic classifier runs on the MCU yet, so there is nothing
real to replay. Only the inputs are synthetic; the routing, the fusion and every printed number come
from the real function call.

Built for the Robu bench demo, where the actuators aren't wired to the board yet.

### Running the demo replay

```powershell
cd device\mpu
python bench\demo_replay.py
```

`--interval <seconds>` controls the pause between events in both passes (default 1.5s, for demo
pacing — pass 0 to run flat out). `--no-color` disables ANSI styling for a plain terminal or a log
capture.

### What it proves

Every printed `fused P(elephant)` in pass 1 is computed live by the real `fuse()`/`decide()` call and
printed next to the real fused probability the board actually logged that day — they match to the
displayed precision, which is the script's own check that its replicated on-MCU probability formula
(`footfall_features.cpp`'s saturating fit) is right, not an assertion to take on faith. The closing
summary reproduces the real run's 11/12 detection rate and 11/11 alert rate. Each alert also prints
the tier the real bandit selected and the repeat count that drove it, so the escalation ladder is
visible on replayed data — the replay injects an in-memory experience store, so it never writes
learning state and never touches `data/experience.sqlite3`.

Pass 2 proves the routing split itself executes as ADR 0007 §5 describes it — three distinct routes,
one alert path that skips fusion, one shared modality for three classes, one dropout case — on live
calls, not on hand-typed numbers. It proves nothing about real-world acoustic classifier accuracy or
confidence calibration; the confidence value is fixed and synthetic.

**Status: closed.** Runs clean against the real `cognition`/`services` modules (`pytest -q`: 217
passed), no hardware required.
