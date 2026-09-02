# Runbook: flashing the STM32U585 MCU on the Arduino UNO Q

**Purpose.** One place that records how the MCU sketch actually gets onto the board, so no
future session has to re-derive it. Written 2026-09-02 from a direct inspection of the deployed
board (`ssh arduino@192.168.1.10`) plus the Arduino / Edge Impulse App Lab documentation.

**One-line answer.** The MCU is flashed **by the board itself** over an on-chip SWD link. The
supported command is `arduino-app-cli app restart user:eletect-x`, which compiles the sketch and
uploads it to the STM32U585 as one step — the same thing App Lab's green *Deploy* button does.
Nothing runs on the Windows dev machine; no external probe; no `rsync`.

---

## What is on the board

All of this is present and self-contained on the UNO Q — the Windows side is not involved in a
flash at all:

| Tool | Path | Role |
|---|---|---|
| `arduino-cli` 1.5.1 | `/usr/bin/arduino-cli` | Compiles the sketch. Core `arduino:zephyr@0.90.0` installed. |
| `arduino-app-cli` | `/usr/bin/arduino-app-cli` | App Lab manager. Daemon: `arduino-app-cli.service`. |
| `arduino-flash` | `/usr/local/bin/arduino-flash` → `/opt/openocd/bin/arduino-flash.sh` | Runs the bundled OpenOCD to write the MCU flash. |
| bundled OpenOCD | `/opt/openocd/bin/openocd` | **Not on `PATH`** — `command -v openocd` returns nothing. A prior session read that as "no OpenOCD" and concluded there was no flash path. There is. |

There is **no** `stm32flash`, `dfu-util`, or system `openocd`.

FQBN: `arduino:zephyr:unoq`. The App Lab production build appends a profile flag:
`arduino:zephyr:unoq:wait_linux_boot=app`.

### How the flash physically happens

`/opt/openocd/openocd_gpiod.cfg`:

```
adapter driver linuxgpiod
adapter gpio srst 38 -chip 1
adapter gpio swclk 26 -chip 1
adapter gpio swdio 25 -chip 1
adapter gpio trst 38 -chip 1
transport select swd
source [find stm32u5x.cfg]
```

So it is **SWD bit-banged on the Linux SoC's own GPIO lines into the STM32U585** — an on-board
debug link. No JTAG/SWD probe, no USB-DFU, no bootloader button, no host tooling.

`arduino-flash.sh` takes `[zephyr.elf] <sketch.elf-zsk.bin>`:

- **1 argument (sketch only)** — OpenOCD runs
  `reset_config srst_only srst_push_pull; init; reset; halt; flash info 0;
  flash write_image erase <SKETCH> 0x80F0000 bin; reset; shutdown`.
  It prints `WARNING: Only flashing the sketch, not the Zephyr core` and **does not touch the
  Zephyr core partition**. This is the low-risk path.
- **2 arguments** — also `flash write_image erase <ZEPHYR>` first (rewrites the Zephyr core).

The sketch user partition is at flash `0x080F0000` (STM32U585 flash is `0x08000000`–`0x08200000`,
2 MB; the Zephyr core lives below the sketch).

### Risk profile

- An MCU flash or MCU reset does **not** change the Linux `boot_id` and does **not** reboot
  Linux. The project's "`boot_id` changed → stop all hardware work" tripwire is a *Linux-reboot*
  detector; a flash will not trip it.
- `arduino-flash` on its own does **not** restart the app container. `arduino-app-cli app
  restart` **does**.
- Sketch-only flash is **not hard-brickable**: worst case the sketch faults, the MCU still boots
  the Zephyr core, and it stays re-flashable over the same GPIO SWD. A hard brick needs the
  Zephyr core partition corrupted, which the 1-argument path never writes.
- During any flash the bridge socket (`/run/arduino-router.sock`) drops for a few seconds while
  the MCU resets — any in-flight bridge RPC from a running job (e.g. a `night_char.py` sweep)
  fails for that window.

---

## The procedure

### Supported path — one command

```bash
arduino-app-cli app restart user:eletect-x
```

Per the App Lab docs, `app start` / `app restart`:

1. detects `sketch/sketch.ino`
2. resolves and downloads the libraries pinned in `sketch/sketch.yaml`
3. compiles against `arduino:zephyr` (up to ~1 min)
4. **uploads the binary to the STM32U585** over the GPIO-SWD path above
5. starts the sketch on the MCU and (re)starts the Python app container

`arduino-app-cli app` has **no** separate `build` / `flash` / `upload` sub-command (its
sub-commands are `new / start / stop / restart / list / logs / import / export / destroy /
clean-cache`) — build+flash is folded into `start` / `restart`. This is the exact path a prior
session used successfully (HANDOVER, 1 Sept bring-up: *"STM32 flashed clean via OpenOCD …
`arduino-app-cli app restart user:eletect-x`"*).

### Manual fallback — compile and flash separately

Use when you want to compile without flashing, or flash a specific artifact:

```bash
# compile only -> produces .../sketch/sketch.ino.elf-zsk.bin
arduino-cli compile -b arduino:zephyr:unoq:wait_linux_boot=app --clean \
  --build-path /home/arduino/ArduinoApps/eletect-x/.cache/sketch \
  /home/arduino/ArduinoApps/eletect-x/sketch

# flash the sketch partition only (Zephyr core untouched)
arduino-flash /home/arduino/ArduinoApps/eletect-x/.cache/sketch/sketch.ino.elf-zsk.bin
```

`arduino-cli compile` also has `-u` (upload after compile) and `-P/--programmer`, but the tested
path on this board is `arduino-flash` after a compile, or `app restart`.

### Getting the working tree onto the board first

`rsync` is absent on the Windows dev machine, so `scripts/sync-to-board.sh` does not run here.
Prior sessions used **tar-over-ssh** into:

- `/home/arduino/ArduinoApps/eletect-x/sketch/` — the STM32 C++ (mirrors `device/mcu/src/`)
- `/home/arduino/ArduinoApps/eletect-x/python/` — the MPU code, bind-mounted into the container
  as `/app` (mirrors `device/mpu/`)

Always diff the board copy against the working tree before compiling — the board tree is not a
git checkout, so a partial sync silently compiles a mix of revisions.

### Verify after a flash

```bash
arduino-app-cli monitor user:eletect-x        # MCU serial; check boot banner / schema version
                                              # (serial attach may DTR-reset the MCU — expected)
docker inspect -f '{{.RestartCount}} {{.State.Running}}' eletect-x-main-1   # want: 0 true
docker logs eletect-x-main-1                   # with ELETECT_SAFE_MODE=0, look for a bridge
                                              # schema-mismatch / handshake error
```

---

## App layout on the board

- App id `user:eletect-x`; container `eletect-x-main-1`; image
  `ghcr.io/arduino/app-bricks/python-apps-base:0.12.0`.
- `/home/arduino/ArduinoApps/eletect-x/`
  - `sketch/` — STM32 C++ (`sketch.ino` is a near-empty stub; `setup()`/`loop()` live in
    `main.cpp`). `sketch.yaml`: `platforms: [arduino:zephyr]`, `default_profile: default`.
  - `python/` — MPU code → `/app` in the container.
  - `app.yaml` — name / icon / ports / bricks (bricks empty for this app).
  - `.cache/sketch/` — build output (`sketch.ino.elf-zsk.bin` is the artifact `arduino-flash`
    wants). `.cache/app-compose.yaml` — the generated Docker Compose.

---

## Current firmware state — assessment as of 2026-09-02 ~01:00 IST

Read this before assuming a flash is still owed.

- Board `sketch/` sources are **byte-identical to the local working tree**
  (`d:/projects/EleTect-X/device/mcu/src/`), verified by `diff` on `config.h`, `led.cpp`,
  `bridge_handlers.cpp`:
  - `BRIDGE_SCHEMA_VERSION 3`
  - `LED_WING_LEFT_PIN 3` (PB0 / TIM3_CH3), `LED_WING_RIGHT_PIN 6` (PB1 / TIM3_CH4)
  - ADR 0014 pattern constants present (`LED_SLOW_PULSE_CYCLES 2`, `LED_FAST_STROBE_HZ 7`,
    `LED_STROBE_FAST_HZ 11`, `LED_RANDOM_FLICKER_*`)
  - `FIRE_TEST_HARNESS 0`
- Board `python/services/config.py` **and the running container** both have `SCHEMA_VERSION = 3`.
- `.cache/sketch/sketch.ino.elf-zsk.bin` (109 280 B, `wait_linux_boot=app` build) is dated
  **2026-09-01 17:31**; sketch sources last edited 17:17 (`config.h`, `led.cpp`) / 15:11
  (`bridge_handlers.cpp`).
- Container `eletect-x-main-1` has been up ~3 h — i.e. it (re)started from that same 17:31 deploy.
- Container runs `SAFE_MODE=True` (dry-run). `export ELETECT_SAFE_MODE=0` for a live session.

**Assessment:** the current working tree — schema 3, explicit LEFT/RIGHT LED pins, ADR 0014
patterns — was **almost certainly flashed to the MCU on 1 Sept ~17:31** as part of the last
`arduino-app-cli app restart user:eletect-x`. The sketch tree, the production binary, and the
container restart all date to that moment. Any note that says schema v3 has *never run on
hardware* / *must be flashed after the power rewire* predates that deploy and is **likely stale**.

**Not yet confirmed** — needs a supervised check (serial attach risks a DTR reset, and it
collides with a running board job):

1. MCU serial banner actually reports schema 3.
2. Right wing on D6 / PB1 drives correctly with no latch-on. (Left wing D3 was hardware-verified
   1 Sept; the right wing was not.)
3. Bridge handshake is clean with `ELETECT_SAFE_MODE=0`.

---

## Board identity — canonical value

`boot_id` (Linux, changes only on a real Linux reboot):
**`6b2c727a-af0d-4517-a6c7-a8069da92a64`**

The value `6b2c727a-a0fa-4819-aaac-f645b8520155` that appears in some earlier notes is **wrong** —
it is stray identifier text spliced in by an old monitor-script bug. If a doc shows it, fix it.
