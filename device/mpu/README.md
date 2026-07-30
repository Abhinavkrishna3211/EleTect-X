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
  rpc.py         signatures + docstrings for all 7 schema.md functions, no Bridge wiring yet
perception/      vision detector (future build call)
cognition/       fusion + contextual bandit (future build call)
services/
  config.py      MPU-side tuning constants, one rationale each (mirrors device/mcu/include/config.h)
comms/           LoRa uplink (future build call)
models/          on-device vision model export, gitignored (*.tflite)
tests/           host-only contract + config tests, never synced to the board
bench/ping/      disposable hello-world Bridge round trip, see below
```

`bridge/rpc.py` ships as **signatures and docstrings only**, deliberately not wired up with
`Bridge.provide()` — `DEVICE_DEVELOPMENT_WORKFLOW.md` §3 documents a live, reproducible bug where
registering an extra `Bridge.provide()` function broke every previously-working function on the
same sketch. The practical discipline that earns: register one function at a time on real
hardware, testing between each addition, not a batch of seven from a host build with no board
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
   rsync -avz device/mpu/bench/ping/ arduino@<board-host>:/home/arduino/arduino_apps/ping-bench/
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
