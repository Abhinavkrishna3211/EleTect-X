# EleTect X - App Lab / Bridge field notes (verified on hardware)

Project-specific reference, not generic App Lab documentation. Records only what
THIS project has actually confirmed on its own board, so the next engineer
doesn't re-pay the discovery cost of the 2026-07-31 bench session. Anything not
covered here should be checked against `docs/KNOWN_GAPS.md` before being assumed.

Generic App Lab/Bricks/Edge Impulse/Flask patterns are not repeated here - this
file exists specifically to record where this project's own hardware diverges
from or hasn't yet confirmed that generic guidance.

## Syncing code to the board

- App Lab's "Run" does NOT read from this git repo. The board's `sketch/`+`python/`
  tree is a separate filesystem; `scripts/sync-to-board.sh` (rsync-based) is the
  only path from a git commit to the board.
- `rsync --delete` wipes anything on the board not tracked in git. This is exactly
  what deleted the board's own `python/main.py`, which had never been committed.
  Before syncing a board that's had ad hoc changes, check `git status` reflects
  everything worth keeping.
- rsync must be installed on both ends. Windows has no reliable native rsync/ssh
  tooling for this - route through WSL (`Ubuntu-24.04` distro) rather than trying
  to install rsync via chocolatey (fails without admin rights). Board-side:
  `sudo apt-get install -y rsync` (confirmed low-risk, standard package).
- WSL SSH setup: copy the private key into WSL's own `~/.ssh` and `chmod 600` it -
  `/mnt/c` DrvFs reports `0777`, which OpenSSH refuses outright. WSL can't resolve
  `.local` mDNS names - override with `BOARD_HOST=<board's LAN IP>` rather than the
  `.local` hostname `sync-to-board.sh` defaults to.
- Never pass a Windows path containing backslashes as an argument into
  `wsl.exe bash <path>` - the backslashes get silently stripped, producing "No
  such file or directory". Wrap the actual work in a `.sh` script and invoke that
  instead.

## app.yaml / main.py

- `arduino-app-cli` requires a `python/main.py` at the top level of the app folder
  to parse `app.yaml` at all - its absence fails the ENTIRE app
  (`main python file missing from app`, exit 7), including MCU-only changes with
  no Python involvement.
- App Lab's desktop "My Apps" list going empty is a downstream symptom of this same
  parse failure, not a separate GUI bug - diagnose via
  `arduino-app-cli app list --show-broken-apps` before chasing the GUI.
- `arduino-app-cli app restart <path>` needs the app's absolute path, not its app ID.
- `arduino-app-cli app restart <path>` is confirmed broken while the app is already running (22 Aug):
  fails `[ERROR] App "Eletect-X" Is Running`, exits 1, and leaves the app **stopped** — worse than a
  no-op. Use `arduino-app-cli app stop <path>` followed by `arduino-app-cli app start <path>` instead;
  confirmed working as the two-step replacement.

## Confirmed working / dead-end transports for reading board output

- `arduino-app-cli monitor` - confirmed broken on this board (returns zero bytes).
- Direct `cat /dev/ttyGS0` over SSH - confirmed zero bytes (times out silently, no
  error).
- Windows Device Manager's discovered `COM14` - opens fine via pyserial, zero
  errors, but receives zero bytes while App Lab's own Serial Monitor simultaneously
  shows live data. Almost certainly a different physical USB interface (e.g. the
  onboard debug probe), not the sketch's console. Not worth chasing further.
- App Lab's own browser-based Serial Monitor - the one reliably-confirmed-working
  read path for MCU `Serial.print` output.
- `docker logs -f <container>` (via SSH; container is `eletect-x-main-1`) - works
  for MPU-side (`device/mpu/main.py`) stdout, but replays the FULL history before
  reaching live output unless run with `--since <duration>` (e.g. `--since 2s`) -
  easy to mistake for a hang.
- `arduino-app-cli app logs <app_path> --all` - documented as a first-class
  alternative to `docker logs`. Not yet tried on this board - worth trying
  first next time before reaching for the docker/WSL route.
- **App Lab GUI unavailable fallback, confirmed working end-to-end, 22 Aug:** when App Lab isn't
  running on the PC (and `eletect-x.local` doesn't resolve, per the WSL mDNS note above), the board is
  still fully reachable: `ssh` to its LAN IP (`192.168.1.10`, hostname `EleTect-X`), drive builds via
  `arduino-app-cli` directly, and use the board's own pre-existing `socat` daemon
  (`/dev/ttyGS0` <-> `tcp:127.0.0.1:7500`, first documented 14 Aug as a read-only path) for console
  access. **New finding: this bridge is bidirectional, not read-only.** It accepts injected keystrokes
  as well as streaming console output — the 14 Aug write-up only ever exercised it with `nc`/nc-style
  read tools and documented App Lab's browser Serial Monitor as the sole confirmed path for anything
  requiring input (e.g. the fire-test harness's `1`/`2`/`3`/`4`/`?` commands). That's now superseded:
  the socat bridge alone is sufficient to both flash-verify a build and fully drive the fire-test
  harness without App Lab running at all. The previously-documented COM14 dead end (opens via pyserial,
  zero bytes) was independently reproduced again this session - still not worth chasing.

## Bridge (Arduino_RouterBridge v0.4.3, confirmed installed on this board 2026-07-31)

- Read directly from the real installed `bridge.h` on the board, not assumed:
  `Bridge.notify()` takes a write mutex and performs a one-way send - it never
  blocks waiting on an MPU reply. `Bridge.call()`'s `RpcCall::result()` DOES block
  on a reply. These are genuinely distinct code paths; a working `notify()` does
  not imply `call()` also works.
- `notify()` MCU->MPU direction: confirmed working end-to-end on real hardware
  2026-07-31 (`device/mcu/src/geophone.cpp`'s `SEISMIC_DEBUG_STREAM_RAW` relay to
  `device/mpu/main.py`'s `debug_stream_raw_seismic_sample` handler).
- `call()`'s synchronous reply path: still unverified. `device/mpu/bench/ping`
  exists to test it but has never been run against real hardware
  (`device/mpu/README.md`: "pending hardware").
- `Bridge.begin()` allocates two thread stacks and starts an update thread
  (confirmed from the real `bridge.h` source pasted in a 2026-02 Arduino Forum
  thread) - calling it repeatedly in a retry loop before Linux has booted has
  been reported to exhaust memory and hang the MCU. If a future build ever needs
  to call `Bridge.begin()` before confirming Linux is up, gate it with a bounded
  retry count, not an unbounded `while(!begin())` loop.
- Registering an additional `Bridge.provide()` function (specifically a
  float-argument one, per one documented live bug) has been observed to break
  every previously-working `provide()`'d function on the same sketch. Register
  and test Bridge functions one at a time on real hardware, never as a batch.

### LORA_SERIAL / Serial1 - resolved, 18 Aug

**Settled on real hardware, `HANDOVER.md`'s 18 Aug entry.** `Serial` (not `Serial1`) is the correct
binding, confirmed directly from the board's own generated devicetree overlay plus a live
`journalctl -u arduino-router` cross-check, both over plain SSH, no sudo. `config.h` was updated and
committed (`47785ec`). The investigative trail below is kept for the reasoning, not because the
question is still open. What remains open on the LoRa side is the module itself not responding past
the first `AT` probe (separate issue, `HANDOVER.md` item 4) - not this binding question.

**Related, new finding, 22 Aug - `Serial` is shared between two consumers, and that's a real race,
currently benign only because the E5 doesn't answer.** With `LORA_SERIAL Serial` and
`FIRE_TEST_HARNESS 1`, both `fire_test_service()` (device/mcu/src/fire_test.cpp) and `mac.cpp`'s
response-read loop (`LORA_SERIAL.available()`/`.read()`, `device/mcu/src/mac.cpp`) drain the same
`Serial` stream every `loop()` iteration, first-come-first-served, with no arbitration between them.
During the 22 Aug fire-test session all 13 injected fire-test keystrokes landed correctly (10/10 in
the individual-command pass, 3/3 in the IR-burst pass) - but that's because `mac.cpp`'s join state
machine is stuck retrying a dead `AT` probe and never actually produces bytes worth stealing. If the
E5 ever starts responding while `FIRE_TEST_HARNESS` is left on, a byte from one consumer's expected
input could be silently read by the other's loop iteration instead. `FIRE_TEST_HARNESS` already
defaults to `0` and must stay `0` outside a bench session, which keeps this from being a field risk -
noted here so a future LoRa-join bench session run with the harness still enabled doesn't lose time to
an intermittent, hard-to-explain dropped byte.

**Original investigative trail, kept for reasoning, not because the question is still open below:**

Earlier reasoning in this project (and in chat)
argued `config.h`'s `#define LORA_SERIAL Serial1` was probably safe because
`Bridge.begin()`/`Bridge.update()` and `LORA_SERIAL.begin(9600)` both ran in the
same 2026-07-31 build with clean `Bridge.notify()` traffic throughout. A deeper
pass across the official Arduino UNO Q datasheet, the `Arduino_RouterBridge`
GitHub README, and several Arduino Forum threads makes that reasoning less solid
than it looked:

- The official datasheet (`docs.arduino.cc/resources/datasheets/ABX00162-ABX00173-
  datasheet.pdf`) confirms the electrical facts our `config.h` already assumed:
  D0 = PB7 = `USART1_RX`, D1 = PB6 = `USART1_TX`. It does NOT document which
  Arduino Core object name (`Serial`, `Serial1`, ...) the `arduino:zephyr` core
  binds to that peripheral - that's a board-support-package detail outside a
  hardware datasheet's scope. It describes Bridge only abstractly, as an RPC
  layer that "accommodates multiple physical transports."
- The `Arduino_RouterBridge` README (github.com/arduino-libraries/
  Arduino_RouterBridge) says the Bridge object is "defined over an UART port
  routed by the zephyr core, falling back to `Serial1` if the core does not
  provide it" - implying the real transport is core-defined and board-specific,
  not necessarily literally `Serial1`.
- Multiple independent Arduino Forum posts (2026, UNO Q category) contradict
  that reading and are specific about names: `forum.arduino.cc/t/uno-q-how-to-
  achieve-manual-control-over-router-bridge-.../1426989` (user `customcontroller`:
  "the two CPUs are connected via UARTs running at 115200... on the STM32 side,
  the port is `Serial1`... App Lab uses these ports for RPC Bridge") and
  `forum.arduino.cc/t/title-arduino-uno-q-cannot-read-serial-monitor-output-via-
  cli-without-app-lab/1438432` (poster cites the official user manual directly:
  "`/dev/ttyHS1` and `Serial1` are reserved by `arduino-router`"; another reply,
  user `GolamMostafa`: "MCU uses LUART1 Port for the Router Bridge"). A third
  post in that same thread (user `qubits-us`) notes the D0/D1 <-> `Serial`/
  `Serial1` naming has reportedly **shifted across a past core update** ("was
  using Serial, now I think we have to use Serial1 - they just flipped things a
  bit there") - meaning the correct answer may be specific to the exact
  `arduino:zephyr` core version installed on this board, not fixed.
- If this community reading is right for our board's core version, `Serial1` is
  Bridge's own internal MPU-link object, and the Grove LoRa-E5 on D0/D1 should be
  reached through the plain `Serial` object instead - which would mean
  `config.h`'s `LORA_SERIAL Serial1` has likely never actually reached the
  physical LoRa module at all, independent of any Bridge conflict.
- The 2026-07-31 clean-`notify()`-alongside-`LORA_SERIAL.begin(9600)` observation
  is real but weaker evidence than it first looked: it only shows Bridge's own
  traffic wasn't visibly disrupted, not that `LORA_SERIAL` ever reached the E5
  module. Both a "different peripherals, no conflict" world and a "same
  peripheral, but LoRa's traffic silently goes nowhere the E5 can hear it" world
  are consistent with that observation.

**Do not guess further from documentation - settle this on the board.** The
cheap, definitive check (cheaper than any more forum reading): SSH in and `grep`
the real installed `arduino:zephyr` core's variant/pin-mapping source for this
board (same approach already used to read the real `bridge.h`) for how `Serial`
and `Serial1` are bound to peripherals. Failing that, tracked as open item #5:
run a real Grove LoRa-E5 AT command exchange on `Serial` (not just `Serial1`)
with `Bridge.begin()`/`Bridge.update()` simultaneously active, and watch for a
response. Do not consider LoRaWAN uplink field-ready until this is closed
either way - it's currently an open correctness question on the one subsystem
that gets alerts to the DFO, not a cosmetic one.

## Edge Impulse - two deployment paths, relevant to this project's layering

`docs.edgeimpulse.com/hardware/boards/arduino-uno-q` documents two genuinely
different ways to run a trained model on this board, worth keeping in mind
against this project's frozen MCU-reflex/MPU-cognition split (`CONTEXT.md`):

- **MCU-hosted** (Arduino library, deploy target "Arduino UNO Q" in Edge Impulse
  Studio's Deployment tab): the model runs directly on the STM32U585 - sub-10ms,
  deterministic latency, no dependency on the MPU being up. This is the same
  locality property the reflex layer already leans on for the hand-tuned STA/LTA
  footfall trigger.
- **MPU-hosted** (`.eim` + `edge-impulse-linux-runner` / `edge_impulse_linux`
  Python SDK, deploy target "Linux aarch64" or the GPU-accelerated variant):
  runs as a Linux process/container on the QRB2210, slower and non-deterministic,
  but zero recompile to update and where the vision/acoustic classifiers in
  `device/mpu/cognition`/`perception` already live per the frozen architecture.
- Not a call to make here - ADR 0001's STA/LTA choice is the frozen architecture
  for footfall detection today - but worth knowing as a real option if a trained
  seismic classifier is ever considered as a STA/LTA replacement or supplement:
  an MCU-hosted Edge Impulse model would preserve the reflex layer's
  doesn't-depend-on-the-MPU property in a way an MPU-hosted one would not.

## Standing rule

Board SSH/sudo credentials are typed directly into an interactive terminal only -
never pasted into a chat/tool session, piped through a script argument, or
otherwise handled non-interactively where they could be captured or logged.

## Diagnosing arduino-router directly (found 2026-08-03, not yet tried)

The official (Edge Impulse-maintained) `arduino-router-rpc` reference docs in
`github.com/edgeimpulse/agent-tools` document that `arduino-router` runs as a
`systemd` service and exposes verbose startup logging:

```
sudo systemctl edit arduino-router.service   # add --verbose to ExecStart
sudo systemctl daemon-reload && sudo systemctl restart arduino-router
journalctl -u arduino-router -f
```

This is a real, previously-unknown-to-this-project diagnostic path, separate from
everything in the transport section above. It likely prints which physical
UART/tty the router opens at startup, which would settle the `Serial`-vs-`Serial1`
question directly from the router's own mouth rather than from forum inference or
core source-diving. Worth trying before either of the two verification methods
already queued in task #5. Also documents `socat -v UNIX-LISTEN:...,fork
UNIX-CONNECT:/var/run/arduino-router.sock` for intercepting live RPC traffic, and
confirms the message-type model matches what `bridge.h` already showed us:
`0=REQUEST` (`call()`), `1=RESPONSE`, `2=NOTIFY` (`notify()`).

## Other Edge Impulse-maintained reference docs worth knowing about

`github.com/edgeimpulse/agent-tools` is the official documentation catalog,
separate from and better maintained than the community App Lab reference this
project has been using. Relevant entries:

- `build-arduino-uno-q-app-lab` (stable) - the official counterpart to the
  community reference already in use here; worth diffing for anything the
  community version got wrong or left out.
- `build-arduino-router-rpc` (experimental) - see above.
- `firmware-arduino` (stable) - Arduino sketch + Edge Impulse library
  integration; relevant once a seismic/acoustic classifier is actually exported.
- `build-custom-learning-blocks` / `build-custom-deployment-blocks`
  (experimental/stable) - relevant if a trained model ever needs a non-built-in
  training pipeline or packaging format.
- `firmware-stm32` (experimental) - STM32CubeIDE/FreeRTOS specific, does not
  apply here (this project builds through PlatformIO + the Arduino Zephyr core,
  not CubeIDE).

## Demo mode - STA/LTA trigger sensitivity (added 2026-08-12)

`device/mcu/src/config.h` now has `SEISMIC_DEMO_MODE` gating `STA_LTA_TRIGGER_RATIO` /
`STA_LTA_DETRIGGER_RATIO` - `1` drops the trigger ratio from 4.0 to 2.0 (detrigger
1.5 -> 1.2) so a light pen/finger tap near the geophone visibly triggers for a live
audience, instead of requiring stomp-strength force. Currently **ON** (`1`) for the
upcoming demo.

**Must be flipped back to `0` before any field-readiness or bench-calibration work** -
the demo ratios are tuned for visible drama, not for rejecting ambient field noise
(wind, vehicles, nearby-but-not-at-sensor footsteps), and neither the demo nor the
default ratios have real bench data behind them yet (see the WARNING comment
directly above the block in `config.h`, and KNOWN_GAPS). After the demo: set
`SEISMIC_DEMO_MODE 0`, re-run `scripts/sync-to-board.sh`, rebuild/flash from App Lab
or the Arduino App CLI, and confirm via `arduino-app-cli app list --show-broken-apps`
that the app is running clean before considering the board field-ready again.

## See also

- Generic App Lab/Bricks/Edge Impulse/Flask documentation - not board-specific,
  not repeated here.
- Edge Impulse Studio/Ingestion API docs - for driving an actual Edge Impulse
  project (upload data, train, export) once one exists for this project.
- `docs/KNOWN_GAPS.md` - the living source of truth; anything not in this file
  should be checked there first.
