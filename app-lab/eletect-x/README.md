# EleTect-X — App Lab package

This folder is the deployable Arduino App Lab package for the real EleTect-X app —
the thing that actually runs on the UNO Q. It is **not** a copy of the source: the
MCU sketch lives in [`device/mcu/src/`](../../device/mcu/) and the MPU program lives
in [`device/mpu/`](../../device/mpu/); those two directories are the single source of
truth and have their own build/test tooling (PlatformIO, `ruff`/`pytest`). This folder
holds only what an App Lab app needs that isn't part of either source tree — the
manifest and any bundled assets — plus the one-command script that assembles the two
into a real app on your board.

## Layout

```text
app-lab/eletect-x/
  app.yaml     App Lab manifest (name, icon, ports, bricks)
  assets/      Static assets bundled with the app (currently empty)
  README.md    this file
```

At deploy time, `scripts/sync-to-board.sh` fills in the two directories App Lab
expects alongside `app.yaml` — `sketch/` from `device/mcu/src/` and `python/` from
`device/mpu/` — directly on the board. They are not created or committed here, so
there is exactly one place to edit MCU or MPU code, never two copies to keep in sync.

## Deploying — the fast path

1. Install [App Lab](https://docs.arduino.cc/software/app-lab/) and complete its
   First Setup wizard against your UNO Q at least once, so the board has Wi-Fi,
   SSH, and `arduino-app-cli` set up.
2. Copy `device/mcu/src/secrets.h.example` to `device/mcu/src/secrets.h` and fill in
   your own LoRaWAN OTAA credentials.
3. Put the vision checkpoint in place. Model binaries are not versioned in this
   repo, so `device/mpu/models/vision/` is empty in a fresh clone and the sync
   script aborts until you fill it. Export the deployed build —
   `runF_res160_noattnrelu_int8.eim`, YOLO-Pro 160 px int8 — from Edge Impulse
   project [1097972](https://studio.edgeimpulse.com/public/1097972/live) as a Linux
   (AARCH64) `.eim` and drop it there. [`ml/vision/README.md`](../../ml/vision/README.md)
   records the exact build and its `sha256` so you can confirm you have the right bytes.
4. From the repo root, with the board reachable over SSH:

   ```bash
   BOARD_HOST=<your-board>.local scripts/sync-to-board.sh
   ```

   This pushes `app.yaml` and `assets/` from this folder, the MCU sketch, the MPU
   program and the vision checkpoint into `~/ArduinoApps/eletect-x/` on the board,
   creating the app if it doesn't exist yet.
5. Install the vision runner, once per board:

   ```bash
   BOARD_HOST=<your-board>.local deployment/install/install-vision-runner.sh
   ```

   The Edge Impulse runner has to run host-side as the `arduino` user rather than
   inside the App Lab container — the container is on a bridge network and cannot
   reach the host's `127.0.0.1:1337`. The unit this installs loads the checkpoint
   synced in step 4 and serves inference on port 1337; the MPU program is a client
   of it.
6. Open App Lab (or `arduino-app-cli`) and build/run the `eletect-x` app like any
   other App Lab project.

See [`device/mcu/README.md`](../../device/mcu/README.md) and
[`device/mpu/README.md`](../../device/mpu/README.md) for what each side actually
does, and the root [`README.md`](../../README.md) for the full project layout.
