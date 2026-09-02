# UNO Q — headless build/flash/deploy and RouterBridge

Research notes for driving an Arduino UNO Q (STM32U585 MCU + Qualcomm QRB2210 Linux MPU) with no
GUI. Every non-obvious claim is linked to its source. Items that could not be confirmed from a
primary source are collected under "Unverified / open".

Primary sources used throughout:

- App Lab docs (source of record): <https://github.com/arduino/docs-content/tree/main/content/software/app-lab> ; rendered at <https://docs.arduino.cc/software/app-lab/>
- `arduino-app-cli` source: <https://github.com/arduino/arduino-app-cli>
- `arduino-router` source + protocol: <https://github.com/arduino/arduino-router>
- Bridge API reference: <https://github.com/arduino/docs-content/blob/main/content/software/app-lab/6.bridge/2.bridge-api/bridge-api.md>
- RouterBridge multi-language tutorial: <https://github.com/arduino/docs-content/blob/main/content/hardware/02.uno/boards/uno-q/tutorials/09.routerbridge-multilanguage/content.md>
- Linux-image flasher: <https://github.com/arduino/docs-content/blob/main/content/software/app-lab/2.configure/4.flash/flash.md>
- Edge Impulse on App Lab: <https://docs.edgeimpulse.com/hardware/deployments/run-arduino-app-lab>
- `edgeimpulse/agent-tools` UNO Q skill: <https://github.com/edgeimpulse/agent-tools/tree/main/skills/build-arduino-uno-q-app-lab>

---

## Summary — canonical headless deploy procedure

An App Lab "app" is a directory (default `/home/arduino/ArduinoApps/<name>/`) containing `app.yaml`,
`python/main.py` (+ optional `python/requirements.txt`), and an optional `sketch/sketch.ino` with a
mandatory `sketch/sketch.yaml`. There is **no separate build or flash verb**. The single deploy
action is `arduino-app-cli app start <app_path>` (or `app restart <app_path>`, which stops a running
instance first). That one command, in order:

1. Runs a one-time migration that strips `Arduino_RouterBridge` from `sketch.yaml` if the profile's
   `arduino:zephyr` platform entry has no pinned version (bundled in core ≥ 0.55).
2. Compiles the sketch **in-process** via the arduino-cli Go library (`srv.Compile`), FQBN
   `arduino:zephyr:unoq`, `--jobs 2`, build dir under the app's `.cache/`.
3. Uploads to the STM32 (`srv.Upload`). If the platform advertises the `wait_linux_boot` menu
   option it compiles/uploads with `arduino:zephyr:unoq:wait_linux_boot=app`. Otherwise (older
   core) it uploads to RAM with `:flash_mode=ram`; on failure it writes a 50-byte
   `empty.ino.elf-zsk.bin` with `:flash_mode=flash` to wipe a flash-resident sketch, then retries.
4. Provisions the Python side and runs `docker compose -f <app>/.../compose up -d --remove-orphans
   --pull missing` to start `main.py` in its container plus any brick sidecars.

Source: `arduino-app-cli` `internal/orchestrator/orchestrator.go` (`StartApp`, `compileUploadSketch`,
`migrateRemoveRouterBridgeIfNeeded`), `internal/orchestrator/sketch_flash.go`,
`internal/platform/platform.go`; and <https://github.com/arduino/docs-content/blob/main/content/software/app-lab/4.apps/6.run/run.md>
("compiles your project, transfers it to the board's active memory, and launches it").

Minimal headless flow over `adb` or `ssh` (board already set up, on network):

```sh
ssh arduino@<boardname>.local                       # or: adb shell
arduino-app-cli app new "eletect" --no-sketch       # optional; or push a prepared dir
# push files into /home/arduino/ArduinoApps/eletect (adb push / scp / git clone)
arduino-app-cli app start /home/arduino/ArduinoApps/eletect     # compile+flash+run
arduino-app-cli app logs /home/arduino/ArduinoApps/eletect --all --follow
arduino-app-cli app list                            # show status
arduino-app-cli properties set default /home/arduino/ArduinoApps/eletect   # run at boot
```

Shortcuts: `user:<name>` → `/home/arduino/ArduinoApps/<name>`, `examples:<name>` → bundled example.
Source: <https://github.com/arduino/docs-content/blob/main/content/software/app-lab/7.cli/1.cli/apps-lab-cli.md>.

**Confirming the STM32 was actually flashed.** App Lab has no explicit "verified" line; you infer it
from the App-launch log stream, which echoes the arduino-cli library output:

- `Sketch profile configured: Name="default", Port=...`
- `Board platform: arduino:zephyr (<ver>) in <dir>`
- `Used library <name> (<ver>) in <dir>` (one per library, so the sketch compiled)
- then the upload phase output from arduino-cli's `Upload` (the `arduino:zephyr` core's
  `arduino-flash` upload tool) with no error, followed by the CLI result line
  `✓ App "<name>" started successfully` / `restarted successfully`.
  Source: `internal/orchestrator/orchestrator.go` write() calls; `cmd/arduino-app-cli/app/start.go`,
  `restart.go`. The exact upload-tool log lines are not documented — see Unverified / open.

For a positive functional check, call an MCU-provided RPC method from Linux after start (e.g.
`Bridge.provide("ping", ...)` on the MCU, then call `ping` from Python / `socat`), or watch
`journalctl -u arduino-router -f` for the MCU registering its methods.

---

## Q1 — Canonical CLI-only deploy: exact commands and flash confirmation

**Commands** (from the documented command reference,
<https://github.com/arduino/docs-content/blob/main/content/software/app-lab/7.cli/2.commands/commands.md>):

| Command | What it does |
|---|---|
| `arduino-app-cli app new <name> [-b bricks] [-d desc] [-i icon] [--no-sketch] [--from-app <path>]` | Scaffolds `app.yaml`, `python/`, and (unless `--no-sketch`) `sketch/` under the apps dir. |
| `arduino-app-cli app start <app_path>` | The deploy action: migrate → compile sketch → upload to STM32 → provision Python → `docker compose up -d`. Accepts `user:<name>` / `examples:<name>`. |
| `arduino-app-cli app restart <app_path>` | Stops the app if it (and only it) is running, then `start`. "Restart or Start an Arduino App." |
| `arduino-app-cli app stop <app_path>` | Resets the MCU, then `docker compose stop`/`down`. |
| `arduino-app-cli app logs <app_path> [--all] [--follow] [--tail N]` | `--tail` default 100. `--all` adds brick/service logs. Output prefixed `[<name>] <line>`. |
| `arduino-app-cli app list [--show-broken-apps]` | Apps + example + status. |
| `arduino-app-cli app clean-cache <app_id> [--force]` | Deletes the app's `.cache/` (build artifacts). `--force` if running. |
| `arduino-app-cli app destroy <app_path>` | Deletes the app. |
| `arduino-app-cli app export <app_path> [out] [--include-data] [--overwrite]` / `app import <zip>` | Zip round-trip; `-` = stdout / stdin. |
| `arduino-app-cli properties set default <app_path>` (`none` unsets) / `properties get default` | The "run at startup" app. |
| `arduino-app-cli monitor` | Attaches to the MCU serial monitor. |

**Mechanism** (from `arduino-app-cli` source). `start`/`restart` call `orchestrator.StartApp`.
When the app has a `sketch/` it emits progress `"sketch compiling and uploading"`, runs
`migrateRemoveRouterBridgeIfNeeded`, then `compileUploadSketch`:

- `srv.LoadSketch` → requires a `default` profile in `sketch.yaml` (error `sketch %q has no default
  profile` otherwise).
- `srv.Init{SketchPath, Profile}` → log `Sketch profile configured: Name=..., Port=...`.
- `GetPlatformMenuOptions` calls `srv.BoardDetails`; if `wait_linux_boot` supports value `app`,
  the FQBN becomes `arduino:zephyr:unoq:wait_linux_boot=app`.
- `srv.Compile{Fqbn, BuildPath: <app>/.cache/..., Jobs: 2, Verbose}` → logs `Board platform: ...`
  and `Used library ...`.
- Upload: if `wait_linux_boot` is **not** present and the platform supports flash-to-RAM (unoq
  only) → `legacyUploadSketchInRam` (`:flash_mode=ram`); else `srv.Upload{Fqbn:
  arduino:zephyr:unoq, ImportDir: buildPath}`.

The build/flash is done by linking the arduino-cli command library into `arduino-app-cli`
(`commands.NewArduinoCoreServer()`), **not** by shelling out to `arduino-cli` or to a bundled
`arduino-flash` binary. `arduino-flash` is the upload tool the `arduino:zephyr` core invokes under
`srv.Upload`. Source: `internal/orchestrator/orchestrator.go` lines ~1054–1195,
`internal/orchestrator/sketch_flash.go`.

**Confirming the flash** — see the Summary section. There is no checksum/verify step surfaced by
App Lab; success = clean compile lines + clean upload phase + `✓ App "<name>" (re)started
successfully`. `app list` then shows the app `running`. The App Lab GUI equivalent turns the
"App launch" tab text green
(<https://github.com/arduino/docs-content/blob/main/content/software/app-lab/4.apps/6.run/run.md>).

---

## Q2 — `arduino-app-cli` command / flag reference

Global: `--format text|json` (default `text`), `--log-level debug|info|warn|error` (default
`error`). Binary refuses to run unless effective UID = 1000 (user `arduino`) unless
`ARDUINO_APP_CLI__ALLOW_ROOT` is set (source: `cmd/arduino-app-cli/main.go`).

Top-level subcommands (source:
<https://github.com/arduino/docs-content/blob/main/content/software/app-lab/7.cli/2.commands/commands.md>
and `cmd/arduino-app-cli/`):

- `app` — `new`, `start`, `restart`, `stop`, `list`, `logs`, `clean-cache`, `destroy`, `export`,
  `import` (see Q1 table for flags).
- `brick` — `list`; `details <brick_id>` (e.g. `arduino:video_object_detection`). No install/remove
  via CLI yet.
- `model` — `list [--exclude-builtin]` (columns ID / NAME / BUILTIN); `delete <model_id>
  [--force]` (`--force` = "Delete model in use").
- `system` — `update [--only-arduino] [--yes]` (interactive "Do you want to upgrade these
  packages? (yes/no)"); `cleanup` (prune unused app images); `network-mode <enable|disable|status>`
  (enable/disable prompt for the Linux password); `keyboard [layout]`; `set-name <name>` (takes
  effect after reboot). Note: older docs/skill text says `system network enable|disable` — the
  current verb is `network-mode`.
- `properties` — `get default`; `set default <app_path>` (`none` unsets).
- `config` — `get` (dump effective config).
- `monitor` — attach to MCU serial monitor.
- `daemon` — `--port` default `8080`, binds `127.0.0.1`, serves the REST API and auto-starts the
  default app. OpenAPI: `internal/api/docs/openapi.yaml` (title `Arduino-App-Cli`, base
  `/v1/...`: `/v1/apps`, `/v1/apps/{appID}/bricks`, tags Application/Brick/AIModels/System/
  Libraries). `version` subcommand's `--port` default is `8800`.
- `completion <bash|zsh|fish|powershell> [--no-descriptions]`.
- `version`.

Environment / paths (source: `arduino-app-cli` `README.md` + `docs/user-documentation.md`):
`ARDUINO_APP_CLI__APPS_DIR` (default `/home/arduino/ArduinoApps`),
`ARDUINO_APP_CLI__DATA_DIR` (default `/var/lib/arduino-app-cli`),
`ARDUINO_APP_BRICKS__CUSTOM_MODEL_DIR` (default `$HOME/.arduino-bricks/models`),
`ARDUINO_APP_CLI__REQUIRED_RUNTIMES` (default `arduino-router:arduino-router,arduino-cloud-connector`),
`DOCKER_REGISTRY_BASE` (default `ghcr.io/arduino/`),
`ARDUINO_DIRECTORIES_DATA`, `ARDUINO_BOARD_MANAGER_ADDITIONAL_URLS` (honoured by
`SetArduinoCliConfig`, which also sets `network.connection_timeout=600s`).

---

## Q3 — `arduino:zephyr:unoq` FQBN and menu options

FQBN: `arduino:zephyr:unoq` (VENTUNO Q: `arduino:zephyr:ventunoq`). Core index:
`https://downloads.arduino.cc/packages/package_zephyr_index.json`
(<https://github.com/arduino/docs-content/blob/main/content/hardware/02.uno/boards/uno-q/tutorials/01.user-manual/content.md>).
Board name in Boards Manager: "Arduino UNO Q Zephyr Core."

Menu options referenced by `arduino-app-cli` (source: `internal/orchestrator/sketch_flash.go`):

- **`wait_linux_boot`** — value used by App Lab is `app`, appended as
  `:wait_linux_boot=app`. Semantically: the sketch, once flashed, halts at boot and waits for a
  "app ready" signal from Linux before running, so the MCU does not free-run before the Python
  side / router is up. `stopAppWithCmd` notes that a "Wait for App"-compiled sketch halts on MCU
  reset, whereas other boot modes just restart. The human-readable names seen elsewhere are
  "Wait for App" / "Wait for Linux" / "Immediate". Exact value list and default: not documented —
  App Lab only ever probes for `wait_linux_boot=app` and enumerates the rest via
  `srv.BoardDetails` at runtime.
- **`flash_mode`** — `ram` | `flash`. `ram` (UNO Q only) loads the sketch into MCU SRAM for fast
  iteration without wearing the 2 MB flash; `flash` writes to flash. App Lab uses `:flash_mode=ram`
  on the legacy path and `:flash_mode=flash` only to push the 50-byte `empty.ino.elf-zsk.bin`
  stub that clears a flash-resident sketch before a RAM upload can succeed.

`internal/platform/platform.go`: unoq → `CompileJobs = 2`, `SupportFlashToRam() == true`,
MCU reset via Linux GPIO char device `gpiochip1` line 38 (ventunoq: `CompileJobs = 0`,
no flash-to-RAM, `gpiochip2` line 78). Reset = drive line low → 10 ms → high
(`internal/micro/micro_linux.go`, uses `go-gpiocdev`).

Any other `arduino:zephyr:unoq` menu items (clock, console, heap, upload speed, etc.) are defined
in the core's `boards.txt`, which was not retrieved — see Unverified / open.

---

## Q4 — RouterBridge / `arduino-router` spec

**Transport.** `arduino-router` is a systemd service on the MPU (`/usr/bin/arduino-router`,
units under `debian/arduino-router/usr/lib/systemd/system/`, board config
`var/lib/arduino-router/config/10-imola.conf` for unoq / `10-monza.conf` for ventunoq). Clients
connect to the Unix domain socket **`/var/run/arduino-router.sock`**. Star topology: the router is
the hub, remaps message IDs, and forwards between clients. The MCU link is `Serial1` on the STM32
side ↔ `/dev/ttyHS1` on Linux, **115200 bps**, and both endpoints are locked by the router — do not
open them from app code. Max message size **256 bytes** (`Bridge.notify` silently drops oversized
messages; `Bridge.call` / Python raises `ValueError`).
Sources: <https://github.com/arduino/arduino-router/blob/main/README.md>,
Bridge API reference, RouterBridge multi-language tutorial.

**Framing.** MessagePack-RPC (msgpack.org). Messages are top-level arrays:

| Type | Form | Meaning |
|---|---|---|
| `0` REQUEST | `[0, msgid, "method", [args...]]` | expects a response |
| `1` RESPONSE | `[1, msgid, error, result]` | `error` null on success, else string and `result` null |
| `2` NOTIFY | `[2, "method", [args...]]` | fire-and-forget, no `msgid` |

**Control methods implemented by the router** (README):

- `$/register` — `[0, msgid, "$/register", ["method_name"]]` → `true`, or error
  `route already exists: <name>`. Register once per method you expose.
- `$/reset` — `[0, msgid, "$/reset", []]` → `true`. Drops all methods registered by this
  connection. Disconnecting also drops them automatically.
- `$/serial/open`, `$/serial/close` — manage the router's physical serial connection.
- `$/setMaxMsgSize <bytes>` — cap pass-through message size.
- Calling an unregistered method returns error `method <name> not available`.

**MCU method registration.** In the sketch: `#include <Arduino_RouterBridge.h>`, then in
`setup()` call `Bridge.begin()` and `Bridge.provide("name", handler)` (or `Bridge.provide_safe`
for handlers that touch Arduino I/O such as `digitalWrite` — runs in `loop()` context instead of
the RPC thread). The library issues the `$/register` call for you. Do **not** call `Bridge.call()`,
`Serial.print()` or `Monitor.print()` inside a `provide` handler — that re-enters the RPC layer and
deadlocks. `Bridge.call("m", args).result(var)` for a synchronous call; `Bridge.notify("m", args)`
for fire-and-forget; call `Bridge.update()` in `loop()` to keep RPC responsive.
Source: Bridge API reference, RouterBridge multi-language tutorial.

**Python bindings.** App Lab apps: `from arduino.app_utils import App, Bridge` — `Bridge.call`,
`Bridge.notify`, `Bridge.provide("name", fn)`. (The skill REFERENCE.md also shows the older
`from arduino.bridge import Bridge` with decorators `@bridge.on_call` / `@bridge.on_notify`; treat
`arduino.app_utils` as current per the Bridge API reference.) Raw clients in any language: open
`AF_UNIX`/`SOCK_STREAM` to the socket and speak msgpack — full C++ (`libmsgpack-cxx-dev`,
`g++ -std=c++17 ... -pthread`) and standalone-Python (`pip3 install msgpack`) client
implementations are in the RouterBridge multi-language tutorial.

**Type mapping** (Bridge API reference): `bool`↔`bool`; `int`↔`int8..uint32`; `float`↔`float`/
`double`; `str`↔`char*`/`String`; `list`↔`std::vector`/`std::array`/`std::list`;
`dict`↔`std::map`; `bytes`↔`std::vector<uint8_t>` / `arduino::msgpack::arr_t<uint8_t>`;
`None`↔`void`.

**Versioning / schema.** No numbered protocol version is published; the message-type table above
is the contract. The one compatibility break is library packaging: **from `arduino:zephyr` core
0.55.0, `Arduino_RouterBridge` (and `Serial`) ship inside the platform** and must NOT be listed in
`sketch.yaml` — `arduino-app-cli` auto-removes it when the platform entry is unpinned.
Source: <https://support.arduino.cc/hc/en-us/articles/27251870677916-Migrating-to-Zephyr-core-0-55-0-on-UNO-Q>
and `internal/orchestrator/orchestrator.go` `migrateRemoveRouterBridgeIfNeeded`.

**Ops.** `systemctl status arduino-router`; `sudo systemctl restart arduino-router`;
`journalctl -u arduino-router -f`; verbose = `sudo systemctl edit arduino-router.service`, add
`--verbose` to `ExecStart`, `daemon-reload` + restart. Traffic sniff:
`socat -v UNIX-LISTEN:/tmp/debug.sock,fork UNIX-CONNECT:/var/run/arduino-router.sock` and point the
client at `/tmp/debug.sock`.

---

## Q5 — What the `edgeimpulse/agent-tools` UNO Q skill prescribes

Skill: `skills/build-arduino-uno-q-app-lab` (metadata version 1.0.1). `SKILL.md` is a router that
defers all specifics to `references/REFERENCE.md` and repeatedly warns that App Lab changes fast —
"Treat file paths and ports in the reference as defaults to verify, not universal facts." Workflow
it prescribes: inspect the existing project first; decide app vs brick vs sketch vs service;
confirm mutable details against live docs; keep real-time I/O on the MCU and networking/files/
web/ML on the MPU; reuse the project's existing manifest fields (don't invent); pin Python deps,
prefer Debian packages for native libs; do not commit `.eim` binaries unless asked; then validate
manifest → run → inspect logs → exercise the full MCU↔MPU / model→UI path.

Concrete build/flash/deploy steps from `REFERENCE.md`:

- **Deploy = `arduino-app-cli app start`.** "Sketch compilation occurs at launch (can take up to a
  minute)." Use `user:<app>` / `examples:<name>` shortcuts. Logs via `app logs <path> --all`.
- **`sketch.yaml` is mandatory when a sketch is present** and every library must carry an explicit
  version: `LibraryName (x.y.z)`, transitive ones prefixed `dependency:`. `platform:
  arduino:zephyr` — no `fqbn` line. `Arduino_LED_Matrix` is bundled (don't list it).
  (Note: the reference still lists `Arduino_RouterBridge (0.2.2)` explicitly — superseded by the
  core-0.55 bundling described in Q4; don't pin it on current cores.)
- **`app.yaml`:** `name`, `description`, `icon` (single emoji), `ports` (use `5001` for a Flask UI;
  `7000` is reserved for the App Lab IDE / `web_ui` brick), `bricks: []`.
- **One app runs at a time.** `App.run()` must be the last line of `main.py` when using bricks;
  code after it never runs.
- **Edge Impulse:** prefer an `.eim` model on the Linux MPU via a brick. Manual path (legacy):
  `scp model.eim arduino@<ip>:/home/arduino/.arduino-bricks/ei-models/` then
  `chmod +x /home/arduino/.arduino-bricks/ei-models/*.eim` (CRITICAL — a non-executable `.eim`
  fails silently), or app-local `models/*.eim`. Set `EI_OBJ_DETECTION_MODEL` (and siblings —
  `EI_CLASSIFICATION_MODEL`, `EI_KEYWORD_SPOTTING_MODEL`, `EI_AUDIO_CLASSIFICATION_MODEL`,
  `EI_MOTION_DETECTION_MODEL`, `EI_V_ANOMALY_DETECTION_MODEL`) in `app.yaml` brick variables.
  Direct SDK use: `from edge_impulse_linux.image import ImageImpulseRunner`.
- **Gotchas it calls out:** use `opencv-python-headless`, never `opencv-python`; pin
  `edge-impulse-linux==1.2.2`; add a `mock_dependencies.py` that stubs `six` / `pyaudio` before
  importing `edge_impulse_linux`; camera is usually `/dev/video2` with `cv2.CAP_V4L2`
  (`/dev/video0`/`1` are the Venus encoder/decoder, not cameras); `/home/arduino` is only ~3.6 GB
  so use `--no-cache-dir`, `arduino-app-cli system cleanup`, `docker system prune -a`, or build the
  venv on the root partition; bind Flask to `0.0.0.0:5001`.
- **Bridge:** `provide_safe()` for GPIO handlers; `notify()` for telemetry; check
  `call().result(var)` return; ~2–3 s settle time before the first call after boot; keep handlers
  non-blocking and call `Bridge.update()` each `loop()`.

---

## Q6 — Bundling an Edge Impulse model, and OTA / hot-swap

**How a model is bundled (current, EI docs "Current Version 0.5.0" flow,
<https://docs.edgeimpulse.com/hardware/deployments/run-arduino-app-lab>):** it is GUI-driven from
inside App Lab — open the AI brick's settings → **AI models** tab → **Download** the model →
**Brick Configuration** → select the custom model → **Save**. App Lab writes the selection into
`app.yaml` automatically; the `.eim` lands under `~/.arduino-bricks/` (docs say
`/home/arduino/.arduino-bricks/ei-models/`; `arduino-app-cli` uses
`ARDUINO_APP_BRICKS__CUSTOM_MODEL_DIR` = `$HOME/.arduino-bricks/models` with a `model.yaml` +
`.eim` per model). Deploy targets in EI Studio: **"Linux aarch64"** (CPU) or **"Linux Arduino
UNO Q (GPU)"** (Adreno 702). `arduino-app-cli` maps unoq → EI deploy params
`{float32, tflite, runner-linux-aarch64}` (ventunoq → `runner-linux-aarch64-qnn`); model type
FOMO MobileNetV2 0.35 in the reference designs. Legacy flow: drop the `.eim` in
`~/.arduino-bricks/ei-models/` and set `EI_OBJ_DETECTION_MODEL:
/home/arduino/.arduino-bricks/ei-models/<model>.eim` in `app.yaml`.

**CLI:** `arduino-app-cli model list [--exclude-builtin]` and `model delete <id> [--force]`
(source: command reference). There is no `model add` / `model install` CLI verb — installation is
the brick "Download" action or a manual file copy.

**OTA / update without full redeploy.** Not documented as a first-class feature. The EI docs state
hot-swap is "Not documented"; the legacy process is "manual file replacement and application
restart." Practically: the model file lives outside the app image, so replacing the `.eim` (or
pointing the env var at a new file) and running `arduino-app-cli app restart <path>` reloads the
model **without recompiling/reflashing the STM32 sketch** only if the sketch is byte-identical —
`compileUploadSketch` runs unconditionally on every `start`/`restart`, but an unchanged sketch
just recompiles and re-uploads quickly. A restart still cycles the Python/brick containers. There
is no mechanism to swap the model in a running container. For true "new model, no downtime" you
would need custom code (e.g. a brick that re-`init()`s an `ImageImpulseRunner` on a file-watch).
Flag: OTA is an open item — see below.

---

## Q7 — Recovery when the STM32 won't take a flash

Ordered from least to most invasive:

1. **Retry the deploy.** `arduino-app-cli app restart <path>`. On the legacy RAM path,
   `arduino-app-cli` already self-heals a stuck RAM upload: it writes a 50-byte
   `empty.ino.elf-zsk.bin` and uploads it with `arduino:zephyr:unoq:flash_mode=flash` to wipe any
   flash-resident sketch, then retries the RAM upload (`internal/orchestrator/sketch_flash.go`
   `configureMicroInRamMode`). Doing the same by hand: upload a trivial empty sketch with
   `:flash_mode=flash`.
2. **Reset the MCU and retry.** `arduino-app-cli app stop <path>` toggles the MCU reset line
   (`gpiochip1` line 38 on unoq) before retrying. A board power-cycle does the same.
3. **Re-install the Zephyr core + re-burn the MCU bootloader.** `arduino-app-cli system update`
   (optionally `--only-arduino --yes`) runs, in `internal/update/arduino/arduino.go`:
   `srv.PlatformInstall{PlatformPackage:"arduino", Architecture:"zephyr", Version:<target>}` then
   `srv.BurnBootloader{Fqbn:"arduino:zephyr:unoq", Programmer:"jlink"}`. The programmer is
   **`jlink`** — flashing/bootloader for the STM32 goes over the on-board debug path from Linux,
   not USB-DFU. A `bootloader_burned.flag` marker is kept in the data dir. This is the documented
   way to recover a bricked/mismatched MCU firmware state short of reflashing Linux.
4. **Reflash the Linux image** (does NOT by itself touch the STM32 sketch, but restores the whole
   toolchain + `arduino-router` + core). Two documented methods
   (<https://github.com/arduino/docs-content/blob/main/content/software/app-lab/2.configure/4.flash/flash.md>):
   - App Lab → Settings → Operating system → **Flash Board** (walks you through EDL mode; optional
     "Preserve user data" keeps the `/home/arduino` partition).
   - **Arduino Flasher CLI** (separate download from
     <https://www.arduino.cc/en/software/#flasher-tool>): short the two **EDL pins** *before*
     plugging USB-C, then `./arduino-flasher-cli flash latest` (`--preserve-user` to keep
     `/home/arduino`, `--temp-dir <path>` needs ~8 GB free). Windows:
     `arduino-flasher-cli.exe flash latest`. Troubleshooting: "Waiting for EDL device" = EDL not
     triggered or missing Linux `udev` rules for Qualcomm VID `05c6`; use a native USB port, not a
     hub.

No STM32 USB-DFU / mass-storage bootloader path is documented for the UNO Q; recovery is
`jlink` bootloader burn (step 3) or full EDL Linux reflash (step 4). A bare "Zephyr core"
reinstall without `arduino-app-cli` was not found documented.

---

## Unverified / open

- **Exact upload-phase log lines** that prove the STM32 was written (what the `arduino:zephyr`
  core's `arduino-flash` upload tool prints on success/failure). Not in docs; would need a live
  `app start` capture or the core's `platform.txt`.
- **Full `arduino:zephyr:unoq` menu-option catalogue and defaults** — only `wait_linux_boot` and
  `flash_mode` are referenced by `arduino-app-cli`. The core's `boards.txt` was not retrieved.
  `arduino-cli board details -b arduino:zephyr:unoq` on the board would list all `ConfigOptions`.
- **`wait_linux_boot` value set** beyond `app`, and which value is the default when App Lab does
  not append the option.
- **Whether `arduino-app-cli app start` ever skips recompile/re-upload for an unchanged sketch.**
  Source shows `compileUploadSketch` is called unconditionally whenever a `sketch/` exists; the
  cost of a no-op rebuild was not measured.
- **Model hot-swap / OTA.** No supported "update the model in a running app" path. Restart-based
  replacement works; live swap needs custom brick code. Behaviour of `arduino-app-cli model
  delete`/re-download while an app is running not verified.
- **`~/.arduino-bricks/ei-models/` vs `~/.arduino-bricks/models/`.** EI docs and the skill say
  `ei-models/`; `arduino-app-cli` env default is `models/` with `model.yaml`. Likely a version
  skew; confirm on the actual board (`ls ~/.arduino-bricks`).
- **`daemon` REST base URL/port.** OpenAPI file says `http://localhost:8800` and `version
  --port` defaults to `8800`, but `daemon --port` defaults to `8080`. Confirm against the running
  daemon.
- **`arduino-router` protocol version field** — none published; assumed stable via the message
  table.
- **docs.arduino.cc rendered URLs** for the App Lab pages are client-rendered and were not
  individually fetched; content here is from the `arduino/docs-content` markdown source, which is
  authoritative but path-versioned to `main`.

## Corrections to our current understanding

1. **No dedicated build/flash command.** `arduino-app-cli app start` / `app restart` is the whole
   deploy: it compiles the sketch and uploads it to the STM32 as launch phase 1, then brings up
   the Python container. There is no `arduino-app-cli flash` / `build` verb.
2. **Flashing is in-process, not a shell-out.** `arduino-app-cli` links the arduino-cli Go command
   library (`commands.NewArduinoCoreServer()` → `srv.Compile` / `srv.Upload`). It does not exec
   `arduino-cli` or a bundled `arduino-flash`; `arduino-flash` is the core's own upload tool called
   underneath `srv.Upload`.
3. **`arduino-flash` / "Arduino Flasher CLI" is for the *Linux image*, not the sketch.**
   `arduino-flasher-cli flash latest` reflashes Debian over EDL. Do not conflate it with the MCU
   sketch upload.
4. **MCU recovery uses the `jlink` programmer over the on-board debug link**, invoked by
   `arduino-app-cli system update` (`PlatformInstall` + `BurnBootloader{Programmer:"jlink"}`).
   There is no documented USB-DFU button/bootloader for the STM32 on UNO Q.
5. **Do not pin `Arduino_RouterBridge` in `sketch.yaml`.** From `arduino:zephyr` core 0.55.0 it
   (and `Serial`) are bundled in the platform; `arduino-app-cli` strips an unpinned reference
   automatically and a pinned one can break the build. Older skill/reference snippets that list
   `Arduino_RouterBridge (0.2.2)` are stale.
6. **Bridge transport specifics:** Linux side is `/dev/ttyHS1` (not a generic `ttyUSB`/`ttyACM`),
   MCU side `Serial1`, 115200 bps, 256-byte max message, socket `/var/run/arduino-router.sock`.
   Both serial endpoints are exclusively held by `arduino-router`.
7. **Python Bridge import is `from arduino.app_utils import App, Bridge`** per the current Bridge
   API reference (the `from arduino.bridge import Bridge` + decorator style in the skill reference
   is the older API).
8. **`system network enable|disable` is now `system network-mode <enable|disable|status>`.**
9. **Edge Impulse model install is GUI "Download" inside the brick's AI-models tab** (writes
   `app.yaml` for you), or a manual `.eim` copy + `chmod +x`. CLI only exposes `model list` /
   `model delete`, no install. GPU target is "Linux Arduino UNO Q (GPU)"; CPU target "Linux
   aarch64".
</content>
</invoke>
