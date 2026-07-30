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

## Addendum (2026-07-30): arduino-cli's sketch build has no subfolder support at all

Getting the first real board build past `pio run -e native` (which had been passing all along)
surfaced three `arduino-cli` behaviors with no PlatformIO analogue, none discoverable except by
compiling on real hardware with `--verbose` — confirmed against the actual `eletect-x` app on
`arduino:zephyr:unoq`, core `arduino:zephyr` 0.90.0:

1. **Quoted includes never search the sketch root or any subfolder.** `#include "x.h"` resolves
   only to (a) the including file's own directory, or (b) an explicit `-I` flag. The only
   automatic `-I` entries `arduino-cli` adds beyond the core/toolchain are each *recognized
   library's* own `src/` directory (a folder containing `library.properties`) — a sketch's own
   subfolders, regardless of name or nesting depth, are never added, no matter how deeply the
   including file sits under the sketch root.
2. **Only `.cpp`/`.ino` files that are direct children of the sketch root are compiled.** Files in
   subfolders are silently invisible to the sketch build — not a compile error, a build that
   reports zero errors and then fails at the *link* step with `undefined reference` for every
   symbol only those files defined. This was the more expensive of the two to find: the include
   fix alone made the build look clean all the way through preprocessing, and the real cause only
   showed up by diffing a `--verbose` compile log's file list against the sketch tree.
3. **A sketch also requires a file named exactly `<sketch-folder-name>.ino` to physically exist**,
   or `arduino-cli compile` refuses to run at all (`main file missing from sketch`) before
   touching any `.cpp` file. On this board that folder is always `sketch/` (`scripts/
   sync-to-board.sh`'s `APP_ROOT/sketch`), so the file must be named `sketch.ino` regardless of
   this repo's own directory name — and because it isn't optional, it has to live in the repo
   (`device/mcu/src/sketch.ino`) like everything else the sync script mirrors, or a future
   `rsync --delete` run silently deletes it again.

None of this is `library.properties`-gated recognition failing to trigger — it's that a sketch
(as opposed to a library) has no recursive-subfolder concept in `arduino-cli` at all, for either
includes or compilation units. The one-line summary: **sketch convention is flat-root-only;
subfolder recursion is a library-only feature.**

Resulting decision: `device/mcu/src/` is now itself flat — `sensors/`, `actuators/`, `footfall/`,
and `lora/` were removed and their contents moved to sit directly beside `main.cpp`, alongside
`config.h`/`secrets.h` (moved here from a separate `include/` for the same reason, in an earlier
pass) and the required `sketch.ino` placeholder. This was not the first fix attempted — relative
`../config.h`-style includes were tried first, since that looked sufficient from finding (1) alone,
and only turned out to be incomplete once finding (2) surfaced on the very next clean board build.
Every file in `src/` now sits at the same depth and uses a plain `#include "whatever.h"`; see
`device/mcu/README.md`'s Layout section for the current file list and this same rationale restated
for anyone reading that file cold.

## Addendum (2026-07-30): `arduino-app-cli monitor` does not surface plain `Serial` output — use App Lab's own Serial Monitor instead

Running the INA333 REF-bias bench check (`device/mcu/README.md`) needs to read the
`[bias-check] raw=<int> volts=<float>` line the board prints. The obvious path over SSH —
`arduino-app-cli monitor` — connects without error but never delivers a single byte, under every
capture method tried (plain redirection, `timeout`, `ssh -tt`, and a `script`-emulated real pty),
including a debug-logged run and a control test against `examples:blink`. Root cause was narrowed,
not fully identified:

- `arduino-app-cli monitor` (confirmed via `--help`) attaches to the MCU serial line through
  `arduino-router`, a system daemon (`arduino-router.service`) — not a direct read of `/dev/ttyGS0`
  (the USB-gadget-serial device the MCU's UART is exposed as on the Linux side; owned by
  `arduino-router-serial.service`, which the CLI does not bypass).
- `journalctl` on the board shows `arduino-router` accepts the monitor client's connection cleanly
  every time (`Accepted monitor connection from=127.0.0.1:<port>`), and logs a burst of
  `invalid packet, expected array, got: int8` errors exactly once per MCU reset/reflash — consistent
  with raw boot-loader noise on the wire before the app's own code starts, not with the app's own
  prints. Critically, **no errors and no data appear in steady state**, even against a firmware build
  with an unconditional `Serial.print()` every 2 seconds (added and flashed purely to test this,
  then reverted) — so the gap is not "no evidence exists," it never leaves the board (or never
  leaves the MCU) at all in this daemon's data path.
- Adding a bare `Bridge.begin()` (zero `Bridge.provide()` handlers, gated behind `#ifdef ARDUINO`
  so the host build is unaffected) was tested as the leading hypothesis, since the one confirmed
  working comparison case (`examples:blink`) calls `Bridge.begin()` and `eletect-x`'s firmware does
  not. This made no difference — identical zero-byte result, identical reset-only error burst — so
  the gap is not simply "Bridge was never initialized." The change was reverted; `main.cpp` carries
  no Bridge dependency.

**What is confirmed to work**: App Lab's own web-UI Serial Monitor (opened directly in a browser
against the board, not through `arduino-app-cli`) shows the `[bias-check]` lines correctly and was
used to complete the actual bench check (see `device/mcu/README.md`'s REF-bias section for the
result). Whether the GUI shares `arduino-router`'s serial path was not independently confirmed — a
`curl` probe against the App Lab backend (`127.0.0.1:8800`, the same `arduino-app-cli` daemon
process that implements the CLI `monitor` subcommand) found no guessable REST/websocket route, and
reproducing the GUI's console requires a real browser session, which isn't reachable over SSH — but
regardless of *why* the GUI works and the CLI doesn't, the practical finding stands on its own:
**for any future bench session that needs to read this board's live serial console, use App Lab's
own Serial Monitor in a browser, not `arduino-app-cli monitor`.** No further investigation of the
CLI/router path is planned; it isn't blocking anything as long as the GUI path is used instead.
