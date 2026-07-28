# ADR 0010: PlatformIO is a host-only test/compile harness, not a flashing path

- **Status:** accepted
- **Date:** 2026-07-29

## Context
Scaffolding `device/mcu` against `device/mpu/bridge/schema.md` and `hardware/references/
UNO_Q_PINOUT_REFERENCE.md` surfaced a real toolchain contradiction. `docs/BUILD_BLUEPRINT_AUG8.md`
and prior planning assumed a conventional PlatformIO project — `pio run` to build, `pio run -t
upload` to flash. But `DEVICE_DEVELOPMENT_WORKFLOW.md` §1/§2/§4 establishes, from Arduino's own
documentation, that the UNO Q's Arduino Core runs on **Zephyr RTOS**, and the only confirmed paths
onto the board are **App Lab** (the on-board app GUI), **Arduino App CLI** over SSH, or a
standalone `west` + `openocd` build for the rare case of a bare Zephyr module outside an App Lab
sketch. PlatformIO has no board definition for the UNO Q and no Zephyr-Arduino-Core target that
matches this board's actual boot/flash chain (`JCTL` jumper + `openocd`, never `dfu-util`) — there
is no version of `pio run -t upload` that produces a flashable image here.

Simply dropping PlatformIO entirely was considered, but every prior decision in this repo has
assumed real compiler coverage before code reaches the board — `ENGINEERING_CONVENTIONS.md` §4
requires known-answer unit tests, and Rung 1 needs those tests running somewhere before any bench
stomp test is worth attempting. Zephyr's own build (`west build`) is heavyweight for what amounts
to testing a handful of pure functions (`sta_lta.cpp`, `rule_gate.cpp`), and does not exercise the
Arduino API surface (`digitalWrite`, `Wire`, `HardwareSerial`) the rest of `src/` is written
against.

## Decision
Keep PlatformIO, but scope it explicitly as a **host-only compile/test harness** — never the path
to a flashable image:

- A single `[env:native]` in `platformio.ini` builds the entire `src/` tree against a small
  hand-written Arduino API shim (`hostshim/` — stub `Arduino.h`, `Wire.h`, `HardwareSerial.h`, and
  their implementations). `pio run -e native` proves the whole tree compiles and links; a bounded
  smoke run in `hostshim/host_shim.cpp`'s `main()` calls `setup()`/`loop()` a fixed number of
  iterations against the stub peripherals, catching crashes the compiler alone wouldn't.
- `pio test -e native` runs Unity known-answer tests (`tests/test_sta_lta/`,
  `tests/test_rule_gate/`) against the pure cores only — zero hardware, zero shim dependency in
  those two files' own signatures.
- `hostshim/` carries a header banner stating it is never synced to the board and never flashed.
  `platformio.ini`'s own header comment states the same for anyone opening the file cold.
- **App Lab remains the only path to a flashable image**, fed by `scripts/sync-to-board.sh`
  (`DEVICE_DEVELOPMENT_WORKFLOW.md` §2's one-directional repo → board sync), building/running via
  App Lab's GUI or the Arduino App CLI, flashed with `openocd` per the board's confirmed chain.

Firmware source calls Arduino APIs directly with no HAL indirection layer of its own —
`ENGINEERING_CONVENTIONS.md` §1's "no unnecessary abstraction" is satisfied because the shim exists
only in the host build's dependency graph, not as a runtime abstraction the board-side build also
pays for.

## Alternatives considered
- **Drop PlatformIO, use `west build` for local compile checks:** rejected for this build call —
  real Zephyr module/App-Lab-sketch structural questions are still open
  (`DEVICE_DEVELOPMENT_WORKFLOW.md` §4), and standing up a full `west` workspace to test two pure
  functions is disproportionate. Revisit if/when the sketch-vs-Zephyr-module question resolves in
  favor of a standalone `west` target anyway.
- **No host build at all; test manually on the board only:** rejected — this repo's whole
  discipline (`ENGINEERING_CONVENTIONS.md` §4) is known-answer unit tests before hardware, not
  after. Testing only on hardware also reintroduces the exact Bridge `provide()` fragility this
  same doc warns about (§3) as a reason to change one thing at a time on the board.
- **Fork/vendor a UNO Q board definition into PlatformIO:** rejected — no upstream definition
  exists, Zephyr-Arduino-Core's actual flash chain isn't PlatformIO's `platform-*` model, and
  maintaining a private board definition is exactly the kind of unnecessary abstraction/maintenance
  burden `CLAUDE.md`'s "prefer simplicity" rule warns against for a two-person team on a deadline.

## Consequences
+ Every pure-function change gets a real compiler and a known-answer test before it ever reaches
  the board — the fast, cheap part of the feedback loop stays fast and cheap.
+ `hostshim/` is small (four files) and never a runtime dependency of the flashed firmware.
+ No one can mistake `pio run`'s success for "the board will run this" — the banner comments in
  `platformio.ini` and `hostshim/` say so at the point someone would make that mistake.
− Two build systems now exist for one codebase (`pio` for host tests, App Lab/Arduino App CLI for
  the board). `scripts/sync-to-board.sh` is what keeps them from drifting — if it's ever skipped,
  the board's copy silently goes stale.
− The host shim's stub peripherals (`Wire`, `HardwareSerial`) always report success/idle data —
  `pio run -e native`'s smoke run proves the wiring doesn't crash, it does not and cannot prove
  real I²C/UART behavior. The bench stomp test (`device/mcu/README.md`) remains the only thing
  that proves that.
