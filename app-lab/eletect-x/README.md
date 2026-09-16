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
  app.yaml     App Lab manifest (name/description/version)
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
   SSH, and `arduino-app-cli` set up (`docs/DEVICE_DEVELOPMENT_WORKFLOW.md` §2 if
   you have it locally — it's a local working doc, not part of this public repo).
2. Copy `device/mcu/src/secrets.h.example` to `device/mcu/src/secrets.h` and fill in
   your own LoRaWAN OTAA credentials.
3. From the repo root, with the board reachable over SSH:

   ```bash
   BOARD_HOST=<your-board>.local scripts/sync-to-board.sh
   ```

   This pushes `app.yaml` and `assets/` from this folder, the MCU sketch, and the
   MPU program into `~/ArduinoApps/eletect-x/` on the board, creating the app if it
   doesn't exist yet.
4. Open App Lab (or `arduino-app-cli`) and build/run the `eletect-x` app like any
   other App Lab project.

See [`device/mcu/README.md`](../../device/mcu/README.md) and
[`device/mpu/README.md`](../../device/mpu/README.md) for what each side actually
does, and the root [`README.md`](../../README.md) for the full project layout.
