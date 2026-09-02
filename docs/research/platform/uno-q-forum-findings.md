# Arduino UNO Q — forum / GitHub findings for EleTect X platform problems

Scope: real-world reports and fixes for the problems we hit running Edge Impulse + Arduino
App Lab on the Arduino UNO Q (STM32U585 MCU + Qualcomm Dragonwing QRB2210 / QCM2290 Linux SoC,
Adreno 702 GPU, ~1.7 GB RAM). Collected Sept 2026 from the Edge Impulse forum, Arduino forum,
and Arduino/Edge Impulse GitHub. Each item notes source URL, visible date, and whether the
author is staff or community. Speculation is flagged inline.

---

## Most useful, actionable

1. **Reboots are as likely to be Linux-side OOM as electrical brownout.** Arduino's own
   "board software out of date" help article says the updated Linux image *enables ZRAM*
   specifically because "random restarts of the desktop environment or applications" are
   "typically caused by memory pressure" on the 1.7 GB board. First action: flash the latest
   Linux image, confirm ZRAM is on (`zramctl`), and cap our Python/EIM memory. (Arduino staff, help centre.)
2. **Power: the UNO Q only negotiates a 5 V/3 A USB-C PD contract — there is no higher-voltage
   PD fallback.** Use a charger + cable both rated 5 V/3 A so inrush peaks don't droop the rail.
   VIN (7–24 V) is the other legal input. (Arduino docs.)
3. **The 0.1"/header "5V" pins are `5V_USB_VBUS`, wired straight to the USB-C connector — an
   output, not an input.** Powering only through VIN leaves those pins dead *and* boots the
   USB port in device mode. Don't try to run a camera/hub off board 5 V. (Community, well-corroborated.)
4. **USB-C port is a PD sink only — it cannot power a camera.** Cameras/peripherals must hang
   off a *powered* USB-C hub. A Logitech C270 works this way. Older images boot the DWC3
   controller in "device" mode; newer firmware sets host mode automatically, or force it with a
   debugfs systemd service. (Community + moderator.)
5. **Clean shutdown: `sudo halt`, not `sudo shutdown now`** (the latter just reboots). The board
   cannot fully cut its own power; after the blue LED goes out there is a ~1–2 s window to pull
   power before it auto-reboots. eMMC has power-loss protection and "will likely recover", but
   don't rely on it. (Arduino staff ptillisch.)
6. **Edge Impulse GPU/NPU acceleration is effectively CPU-only on this SoC today.** The QNN /
   TFLite-delegate userland is *not* in the stock image (`ldconfig -p` finds no
   `qnn|tflite|delegate|fastrpc` libs); EI's validated Qualcomm QNN path targets Hexagon-NPU
   boards (QCS6490 / RB3 Gen 2 / RUBIK Pi 3), not the QRB2210. Plan for NEON-CPU inference
   timing. (Community thread; EI docs.)
7. **Camera into edge-impulse-linux: pass an explicit GStreamer pipeline.** The CLI wants V4L2;
   the UNO Q camera comes up under libcamera and isn't auto-detected. Use
   `edge-impulse-linux --gst-launch-args "libcamerasrc camera-name='<name>' ! video/x-raw,width=640,height=480 ! videoconvert ! jpegenc"`
   with the name from `gst-device-monitor-1.0`. (Edge Impulse staff mateusz.)
8. **`DmaBufAllocator … Could not open any dma-buf provider`** on camera start → add the user to
   the `kvm` group: `sudo usermod -a -G kvm arduino`. (Edge Impulse staff mateusz.)
9. **Flashing fails with a "firehose response" / XML parser error → swap to a USB-C-to-USB-C
   cable** (not USB-A-to-USB-C). On Linux hosts also blacklist `qcserial`. (Community.)
10. **RouterBridge `provide()` callbacks: never call `Bridge.call()` / `Monitor.print()` inside
    them (deadlock); call `Monitor.begin()` *after* `Bridge.begin()`; use `Bridge.notify()` for
    void calls.** (Arduino moderator ptillisch.)

---

## 1. Spontaneous reboots / brownout / power instability / undervoltage

- **"If your Arduino UNO Q board software is out of date" – Arduino Help Center**
  (support.arduino.cc/hc/en-us/articles/23170731875740; Arduino **staff**; page returns 403 to
  scrapers, content via search index). Takeaway: the updated Linux image **enables the ZRAM
  kernel module** to cope with only ~1.7 GB RAM, and states plainly that "random restarts of the
  desktop environment or applications" are "typically caused by memory pressure." Same image
  also fixes ADB-running-as-root and restores HDMI audio. **Recommended fix: flash the latest
  Linux image on the board.** — This is the single most direct statement that our unattended
  reboots may be OOM, not power.
- **"Uno-q keeps rebooting. power brownout?"**
  (forum.arduino.cc/t/uno-q-keeps-rebooting-power-brownout/1438230; all **community** —
  iplayfast, build_1971, sonofcy, KurtE; ~mid-2026). Board powered through a USB hub feeding
  several devices; reboots under load. Consensus: hub/supply underpowered; **a capacitor on
  5 V does not fix a brownout** ("a cap will smooth an overload over time … you should have a
  supply that can easily deliver what you need"). Advice: use a validated USB-C hub (Anker /
  Arduino Store) and a generous supply.
- **"Power supply problems"**
  (forum.arduino.cc/t/power-supply-problems/1415447; **community** — ludo_viero, sir_robert).
  Bench-PSU → VIN gave only ~4.7 V on the board and ~0.33 V to a downstream hub; PSU → hub →
  USB-C → UNO Q caused **boot-looping**. Key explanation (sir_robert): the JANALOG/JMISC "5V"
  pins are `5V_USB_VBUS` — 5 V straight off the USB-C connector, so with VIN-only power they
  output nothing, and the USB port defaults to **device** mode. Workaround that finally worked:
  back-feed regulated 5 V into the 5V pin (unsupported hack).
- **"UNO Q Power Specifications" – Arduino Documentation**
  (docs.arduino.cc/tutorials/uno-q/power-specification/; Arduino **staff**; page body didn't
  render for the fetcher, details via search). The board **negotiates only a 5 V PD contract and
  requests 5 V/3 A** — no higher-voltage PD fallback. Use a supply *and* cable rated 5 V/3 A so
  "short activity peaks do not cause connector droop." VIN accepts 7–24 V (buck to 5 V). Rails:
  5 V, 3.3 V, 1.8 V.
- **"UNO Q: Is abrupt power removal officially supported…?"**
  (forum.arduino.cc/t/uno-q-is-abrupt-power-removal-officially-supported-or-is-clean-shutdown-required/1444069;
  **Arduino staff** ptillisch; started 14 May 2026). Board cannot cut its own power. Staff:
  use `sudo halt`. Testers: even `halt`/`poweroff` often auto-reboot; practical method is
  `sudo halt`, then pull power in the 1–2 s after the blue LED goes dark. Docs now say eMMC has
  power-loss protection and "will likely recover on the next boot" — resilient, not guaranteed.
- **"Arduino Uno Q shutdown"**
  (forum.arduino.cc/t/arduino-uno-q-shutdown/1418430; **community** — danpeirce, maxgerhardt,
  GolamMostafa, papavask; 7 Dec 2025 → 9 Apr 2026; **no staff answer**). Same finding:
  `sudo shutdown now` reboots; `sudo halt` / `sudo shutdown -h now` work for some; hibernation
  fails (no swap). Users sync then pull power.
- **"Connecting USB Camera to Uno Q"** (see topic 4) — directly relevant: a camera on the
  USB-C port draws through the PD sink and is a plausible brownout/enumeration trigger; the fix
  is a powered hub.
- **"Power Outage during Board Update in UNO Q"**
  (forum.arduino.cc/t/power-outage-during-board-update-in-uno-q/1449390) — thread exists
  (returned 404 to the fetcher, likely moved/renamed); title alone confirms losing power during
  a board/image update is a known brick risk. Recovery = re-flash via `arduino-flasher-cli`
  (see topic 2). *Could not read full content.*
- **`power_operation_mode: default`** — searched Arduino docs, forum, GitHub: **nothing found**
  referencing that exact key. *Speculation:* it is likely a field in the App Lab / board
  config (e.g. `arduino-app-cli properties`) rather than anything forum users discuss; not
  corroborated.

## 2. STM32 / board flashing, headless deploy, recovery

- **"Arduino UNO Q flashing failure?"**
  (forum.arduino.cc/t/arduino-uno-q-flashing-failure/1412903; **community** — Fabri54, gameraa;
  7 Nov 2025 → 3 Feb 2026). `arduino-flasher-cli flash latest` (v0.4.0, QDL/firehose) fails with
  `parser error : Extra content at the end of the document … failed to parse firehose response`.
  **Fix: use a USB-C-to-USB-C cable instead of USB-A-to-USB-C.** Thread also references
  concurrent reports of bricked boards, "Waiting for EDL Device" timeouts, and Raspberry-Pi-host
  problems.
- **"arduino-flasher-cli could use a few improvements" — GitHub arduino/arduino-flasher-cli #20**
  (github.com/arduino/arduino-flasher-cli/issues/20; **community** reporter; 30 Oct 2025).
  Practical failure modes: host C:/disk space exhausted mid-download (no resume — see #28 for
  caching), Norton AV blocking the `qdl` binary, **Ubuntu 24.04 "unable to open USB device"
  needing a manual `qcserial` blacklist**, macOS needing ≥12.0. Success came from reusing a
  previously downloaded image. You can pass a local image path to the flasher.
- **"Migrating to Zephyr core 0.55.0 on UNO Q" – Arduino Help Center**
  (support.arduino.cc/hc/en-us/articles/27251870677916; Arduino **staff**). App Lab hard-codes
  FQBN `arduino:zephyr:unoq`; a manually-placed core **must** be named `zephyr` locally; the
  `flash_mode` board option was **removed** (this is the cause of the 0.7.0 `invalid option
  'flash_mode'` error — topic 5). MCU flashing is a two-step process, **openocd runner only**
  (no dfu-util). Restore the pre-installed loader:
  `adb shell arduino-cli burn-bootloader -b arduino:zephyr:unoq -P jlink`.
- **Zephyr / Arduino core**: github.com/arduino/ArduinoCore-zephyr and
  docs.zephyrproject.org/latest/boards/arduino/uno_q/ — upstream board support exists; debugging
  via `west debug` after starting a debug server. No "only the sketch flashed, not the Zephyr
  core" bug report found — *nothing found* on that exact phrasing.
- **"Debug an App-lab UNO Q crash?"** (see topic 5) — contains the most useful headless-flash
  detail: RAM-mode uploads (what `arduino-app-cli` uses) were broken in Zephyr core 0.53.0 for
  both static and dynamic link modes; forcing flash mode via `platform.local.txt` is the
  workaround.
- **General**: OpenOCD-GPIO / bit-banged SWD recovery of the STM32 — *nothing found* specific to
  the UNO Q. The board's supported recovery path is the Qualcomm QDL image flash plus
  `burn-bootloader`, not external SWD.

## 3. `libtensorflowlite_gpu_delegate.so: cannot open shared object file` / GPU / NPU / DSP acceleration

- **"Status of Qualcomm QNN / TFLite delegate / Edge Impulse QNN acceleration"**
  (forum.arduino.cc/t/status-of-qualcomm-qnn-tflite-delegate-edge-impulse-qnn-acceleration/1447565;
  **community** — "speccy"; 8 Jun 2026; **no staff reply captured**). Most on-point thread.
  Findings from the poster's own probing:
  - `/dev/fastrpc-adsp` exists, the `fastrpc` kernel module is loaded, ADSP firmware boots — so
    the DSP hardware path is *present*.
  - GPU compute works: Mesa / Turnip / Rusticl give working Vulkan **and** OpenCL on the
    Adreno 702.
  - **But `ldconfig -p | grep -Ei "qnn|tflite|delegate|fastrpc|adsprpc|cdsprpc"` returns
    nothing** — the QNN / TFLite-delegate userland libraries are simply **not installed** in the
    stock image. Open questions to Arduino/EI (unanswered in the captured thread): is
    `runner-linux-aarch64-qnn` supported on UNO Q, and what's the official way to install the
    Qualcomm QNN userland.
- **Edge Impulse docs — "Linux SDKs" / "Linux (AARCH64 with Qualcomm QNN)" deploy target**
  (docs.edgeimpulse.com/tools/libraries/sdks/inference/linux). QNN acceleration is real in EI,
  built with `USE_QUALCOMM_QNN=1`, **but the officially supported Qualcomm targets are
  Hexagon-NPU parts — Dragonwing QCS6490, RB3 Gen 2 Dev Kit, Thundercomm RUBIK Pi 3** — not the
  QRB2210/QCM2290 in the UNO Q. *Speculation:* the UNO Q QNN runner may work if the QNN `.so`
  set is side-loaded, but no one has reported doing it.
- **"Announcing Support for the Arduino UNO Q" — Edge Impulse blog**
  (edgeimpulse.com/blog/announcing-support-for-the-arduino-uno-q; **EI staff** David Tischler;
  7 Oct 2025). Names the Adreno GPU and dual ISPs; **no mention of NPU/DSP/QNN, no delegate
  details, no benchmarks.** Demos (keyword spotting, face detection) are implicitly CPU.
- **Edge Impulse UNO Q board doc**
  (docs.edgeimpulse.com/hardware/boards/arduino-uno-q; **EI staff**). Says
  `edge-impulse-linux-runner` "will automatically compile your model with full hardware
  acceleration" — **but gives no GPU/NPU specifics**, so read this as NEON-CPU. Warns about an
  "Unsupported architecture" error when an `.eim` is run under a 32-bit OS on a 64-bit CPU
  (must be a 64-bit OS). Also: keep heavy editor/IDE processes off the board to avoid memory issues.
- **`libtensorflowlite_gpu_delegate.so: cannot open shared object file` specifically** — **no
  UNO Q / QRB2210 forum or GitHub hit.** Nearest analogues:
  - EI docs "Flex delegates"
    (docs.edgeimpulse.com/tools/libraries/sdks/inference/linux/flex-delegates): the fix pattern
    for a missing EI delegate `.so` is to place the library in `/usr/lib` or `/usr/local/lib`.
  - TensorFlow issues #46498, #58497, #59794, #52155 (all **community**): cross-building
    `libtensorflowlite_gpu_delegate.so` for `aarch64` needs Bazel
    `--config=elinux_aarch64 -c opt --copt -DMESA_EGL_NO_X11_HEADERS --copt -DEGL_NO_X11
    --copt -DCL_DELEGATE_NO_GL …`; OpenCL 2.x builds succeed where 1.2 fails.
  - *Assessment (speculation):* the EI Linux runner tries to `dlopen` a GPU delegate and, when
    it's absent, logs the "cannot open shared object file" line and **silently falls back to
    CPU** — inference still runs, just unaccelerated. On the UNO Q the delegate/QNN libs aren't
    shipped, so CPU fallback is the expected steady state. Not a blocker, but budget latency
    for CPU.

## 4. Camera exposure / gain / auto-exposure / feeding own frames / V4L2

- **"Arduino UNO Q: Issues with running edge-impulse-linux" — Edge Impulse forum**
  (forum.edgeimpulse.com/t/arduino-uno-q-issues-with-running-edge-impulse-linux/16762;
  **EI staff** mateusz + community ventorono, Leszek, 9600/Andrew; 25 Oct → 16 Dec 2025). The
  central thread for camera-on-UNO-Q:
  - Symptom: `edge-impulse-linux` fails with **"Cannot find any webcams at initCamera"**
    (sensors-helper.js:73) even though `cheese` / GStreamer see the camera.
  - Cause (mateusz): the camera is served by the **libcamera** GStreamer plugin, which the EI
    CLI didn't support; it expects **V4L2**.
  - **Workaround (mateusz):** feed an explicit pipeline —
    `edge-impulse-linux --gst-launch-args "libcamerasrc camera-name='/base/soc@0/...:1.0-046d:0825' ! video/x-raw,width=640,height=480 ! videoconvert ! jpegenc"`.
    Get `camera-name` from `gst-device-monitor-1.0` (look for `class : Source/Video`). Run with
    `--verbose` to see the full pipeline the CLI builds.
  - **`ERROR DmaBufAllocator … Could not open any dma-buf provider`** → `sudo usermod -a -G kvm
    arduino`, then re-login (mateusz, 15 Dec). Fixed the dma-buf error.
  - **WebSocket drops during preview** ("WebSocket is not open: readyState 0",
    "Not received pong from server within six seconds") on high-res JPEG cameras — **unresolved**;
    mateusz's operational workaround is to capture frames locally with GStreamer and upload via
    the EI Ingestion API instead of live streaming. He also notes ~3 MB per JPEG at high res
    saturates the link.
  - Resolution guidance (mateusz): pick the smallest camera resolution that is ≥ the model
    input; e.g. don't run 3840×2160 into a 320×320 model.
- **Exposure / gain / auto-exposure control** — **nothing found** in an Edge Impulse or Arduino
  UNO Q context. The only exposure/gain material is Arducam IMX462 on Raspberry Pi
  (forum.arducam.com/t/adjusting-auto-exposure-and-gain-settings-arducam-imx462/3641 and the
  Arducam IMX462 wiki; **community/vendor**): the Pivariety IMX462 exposes standard **V4L2
  controls** through a hardware-ISP path; max analogue gain ~29.4 dB; setting analogue gain also
  nudges digital gain. *Speculation:* on the UNO Q, since frames arrive via `libcamsrc`,
  exposure/gain would be set through libcamera controls (or `v4l2-ctl` if a `/dev/videoN`
  V4L2 node is exposed) rather than anything Edge Impulse offers — untested, no report.
- **IMX462 / Arducam on UNO Q specifically** — **nothing found.** No thread shows an IMX462 or
  Arducam MIPI module running on the UNO Q. Reports that exist use USB webcams (Logitech C270,
  a 0ac8:3420 and a 046d:0825 device).
- **"Connecting USB Camera to Uno Q"**
  (forum.arduino.cc/t/connecting-usb-camera-to-uno-q/1412062; **community** manchuino,
  Grumpy_Mike, psalmustrack99, yokonav). USB-C port is a **PD sink only** — "it can't give
  power to devices"; connect the camera through a **powered USB-C hub**. Older images boot the
  DWC3 controller in **device** mode → camera never enumerates; temporary fix is a systemd
  service that forces host mode via debugfs; newer firmware does it automatically. C270 confirmed
  working via Cheese.

## 5. App Lab — CLI deploy, container, auto-start, RouterBridge / RPC, socket drops

- **"UNO Q: Since updated to App Lab 0.7.0 cannot Run any app"**
  (forum.arduino.cc/t/uno-q-since-updated-to-app-lab-0-7-0-cannot-run-any-app/1443594;
  **Arduino moderator** ptillisch + community KurtE, GolamMostafa; from 11 May 2026). After the
  0.7.0 update (RouterBridge bumped to 0.8.1) apps and examples stop running with:
  `Please update the Arduino_RouterBridge library to the latest version`,
  `Unknown FQBN: … invalid option 'flash_mode'`, `no colon in first item of depfile`.
  Fixes tried: **remove the duplicate `Arduino_RouterBridge` from the hardware/libraries
  folder** (it must not live there any more); reflash the board image as a last resort; the
  Arduino IDE 2.3.8 still uploads to the STM32 directly (bypasses Linux);
  `arduino-cli burn-bootloader -b arduino:zephyr:unoq -P jlink`. Others reported 0.7.0 fine, so
  it's environment-specific — stale library/core state.
- **"Error on App start after update: Arduino_RouterBridge.h: No such file or directory"**
  (forum.arduino.cc/t/error-on-app-start-after-update-arduino-routerbridge-h-no-such-file-or-directory/1437873;
  **community**). Same class of breakage one version earlier (App Lab 0.6.0): a project that
  built on 0.5.0 fails to compile because `Arduino_RouterBridge.h` isn't found. *Not fetched in
  full* — flagged for the pattern: App Lab minor upgrades repeatedly break RouterBridge include
  paths.
- **"Issues with Monitor and Bridge"**
  (forum.arduino.cc/t/issues-witho-monitor-and-bridge/1416857; **Arduino moderator** ptillisch +
  community elia_ster; 28 Nov → 3 Dec 2025). Concrete RouterBridge rules:
  - **Do not call `Bridge.call()` or `Monitor.print()` inside a `Bridge.provide()` callback** —
    starting a new RPC while answering one **deadlocks**. Set a flag and act in the main loop.
  - **Call `Monitor.begin()` *after* `Bridge.begin()`** (wrong order breaks Monitor output).
  - Use **`Bridge.notify()`** for calls that return nothing, not `Bridge.call()`.
  - With App Lab's **RAM flash mode** (`arduino:zephyr:unoq:flash_mode=ram`) the sketch hangs
    when both `Monitor.begin()` and `imu.begin()` (LSM6DSOX) are present; the same sketch is
    fine from the Arduino IDE (flash mode).
- **"Is it possible to debug an App-lab UNO Q crash?"**
  (forum.arduino.cc/t/is-it-possible-to-debug-an-app-lab-uno-q-crash/1429286; **community** KurtE
  + **moderator** ptillisch; from 5 Feb 2026). Crash visibility on the MCU side is *only* via a
  USB-serial adapter on pins 0/1 @ 115200. To get symbolicated crashes, enable **static
  linking** with `~/.arduino15/packages/arduino/hardware/zephyr/0.53.0/platform.local.txt`:
  ```
  build.link_mode=static
  upload.extension=bin-zsk.bin
  ```
  then map fault addresses against the `.map`. Caveat: **RAM-mode uploads (what `arduino-app-cli`
  uses) were broken in core 0.53.0** for static and dynamic; workaround adds
  `openocd_cfg=flash_sketch.cfg` to force flash mode. Core 0.52 stable, 0.53.0 regressed,
  0.53.1 in test. Tracking: `arduino-app-cli` issue #233 (expose link mode).
- **"Error running app on UNO Q from command line"**
  (forum.arduino.cc/t/error-running-app-on-uno-q-from-command-line/1412353; **moderator**
  manchuino + community sgmustadio; 5–25 Nov 2025). `arduino-app-cli app start …` prints
  `✓ App started successfully` but nothing runs. The log lines
  `ERRO Stopped decode loop: EOF discovery=builtin:serial-discovery` and `… file already closed`
  are **red herrings**. Real causes: (a) missing `App.run(user_loop=loop)` in the Python entry
  point; (b) a `.git` directory inside the project confusing the container mount — remove it.
- **"Improve and fix the service restart logic" — GitHub arduino/arduino-app-cli #521**
  (github.com/arduino/arduino-app-cli/issues/521; Arduino **staff** lucarin91, mirkoCrobu;
  10 Jul 2026). After an `apt`-driven self-update the services restart in the wrong order — the
  `arduino-app-cli` daemon restarts *before* `arduino-router`, which kills the daemon mid-update
  and leaves remaining services un-restarted; `needrestart` behaves inconsistently across Ubuntu
  builds. PRs #518 / #519 in flight. Implication for us: an auto-update can leave the bridge /
  app daemon down until a reboot.
- **"Impossible to use App Lab without access to Wi-Fi" — GitHub arduino/arduino-app-cli #101**
  (community). App Lab / CLI assumes connectivity for update checks; noted for headless/offline
  field use.
- **Auto-start on boot** (from Arduino docs, docs.arduino.cc/software/app-lab/cli/cli): set with
  App Lab's "Run at startup" (adds a DEFAULT badge) or
  `arduino-app-cli properties set default user:<APP_NAME>`. No forum report of the default app
  *failing* to start on boot beyond the update-ordering bug in #521.
- **RouterBridge socket drops / schema mismatch mid-run** — beyond the deadlock rule above,
  **nothing found** describing a running bridge socket dropping or an RPC schema-version
  mismatch at runtime. The RouterBridge failures in the wild are all build/upgrade-time
  (missing header, wrong library location, `flash_mode` option removed).

## 6. RTC / clock jumping on reboot

- **Nothing found** — no Arduino or Edge Impulse forum/GitHub thread about the UNO Q's clock
  jumping, resetting, or drifting across reboots.
- *Context / speculation (general Linux SBC behaviour, not UNO-Q-confirmed):* boards in this
  class ship **without a battery-backed RTC**, so on a cold boot with no network the system
  clock is restored from `fake-hwclock` / the last filesystem timestamp and only becomes
  correct once `systemd-timesyncd` reaches an NTP server. For unattended field use with
  intermittent connectivity, expect wrong wall-clock time until first sync; if we need reliable
  timestamps offline, add an external I²C RTC (DS3231) on the MCU side and have the MPU read it,
  or gate logging on `timedatectl` sync status. None of this is corroborated by a UNO Q report.

## 7. Watchdog / auto-recovery / systemd units to keep an App Lab app alive

- **Largely nothing found.** No forum thread or GitHub issue where someone adds a systemd
  watchdog / `Restart=always` unit to keep an App Lab app running, and no discussion of the
  STM32U585 hardware IWDG in an App Lab context.
- Closest material:
  - Apps run under a systemd-managed service via `arduino-app-cli`; the boot app is chosen with
    `arduino-app-cli properties set default user:<APP_NAME>` (Arduino docs). Whether that
    service has an automatic restart policy on app crash is **not documented and not stated in
    issue #521**, which only covers restart *ordering* after updates.
  - Issue #521 (topic 5) shows the current restart machinery is fragile — evidence that we
    should **not** assume the platform will resurrect a crashed app on its own; a project-owned
    watchdog (systemd unit with `Restart=on-failure`, or an MPU-side supervisor that pings the
    bridge and re-issues `arduino-app-cli app start`) is worth building.
  - The "board software out of date" article (topic 1) implies the platform's answer to app
    instability is memory-pressure mitigation (ZRAM) plus image updates, not a supervisor.
- *Speculation:* a straightforward field-hardening approach is a `systemd` service
  (`Restart=always`, `RestartSec`, `WatchdogSec` with `sd_notify` if we own the loop) wrapping
  `arduino-app-cli app start …`, plus enabling the STM32 IWDG in our MCU firmware so the reflex
  side self-recovers independently of Linux. No community precedent found to copy.

---

## Source index

Edge Impulse forum / docs / blog:
- forum.edgeimpulse.com/t/arduino-uno-q-issues-with-running-edge-impulse-linux/16762 (staff mateusz; Oct–Dec 2025)
- docs.edgeimpulse.com/hardware/boards/arduino-uno-q (staff)
- docs.edgeimpulse.com/tools/libraries/sdks/inference/linux + .../flex-delegates (staff)
- edgeimpulse.com/blog/announcing-support-for-the-arduino-uno-q (staff David Tischler, 7 Oct 2025)

Arduino forum:
- forum.arduino.cc/t/uno-q-keeps-rebooting-power-brownout/1438230 (community)
- forum.arduino.cc/t/power-supply-problems/1415447 (community)
- forum.arduino.cc/t/arduino-uno-q-shutdown/1418430 (community; Dec 2025–Apr 2026)
- forum.arduino.cc/t/uno-q-is-abrupt-power-removal-officially-supported-or-is-clean-shutdown-required/1444069 (staff ptillisch; May 2026)
- forum.arduino.cc/t/power-outage-during-board-update-in-uno-q/1449390 (404 to fetcher — title only)
- forum.arduino.cc/t/connecting-usb-camera-to-uno-q/1412062 (community + moderator)
- forum.arduino.cc/t/arduino-uno-q-flashing-failure/1412903 (community; Nov 2025–Feb 2026)
- forum.arduino.cc/t/status-of-qualcomm-qnn-tflite-delegate-edge-impulse-qnn-acceleration/1447565 (community "speccy"; 8 Jun 2026)
- forum.arduino.cc/t/uno-q-since-updated-to-app-lab-0-7-0-cannot-run-any-app/1443594 (moderator ptillisch; May 2026)
- forum.arduino.cc/t/error-on-app-start-after-update-arduino-routerbridge-h-no-such-file-or-directory/1437873 (community)
- forum.arduino.cc/t/issues-witho-monitor-and-bridge/1416857 (moderator ptillisch; Nov–Dec 2025)
- forum.arduino.cc/t/is-it-possible-to-debug-an-app-lab-uno-q-crash/1429286 (community KurtE + moderator; Feb 2026)
- forum.arduino.cc/t/error-running-app-on-uno-q-from-command-line/1412353 (moderator manchuino; Nov 2025)

Arduino Help Center / docs:
- support.arduino.cc/hc/en-us/articles/23170731875740 — board software out of date / ZRAM / memory pressure (staff)
- support.arduino.cc/hc/en-us/articles/27251870677916 — migrating to Zephyr core 0.55.0 (staff)
- docs.arduino.cc/tutorials/uno-q/power-specification/ (staff)
- docs.arduino.cc/software/app-lab/cli/cli (staff)

GitHub:
- github.com/arduino/arduino-flasher-cli/issues/20 (community; 30 Oct 2025)
- github.com/arduino/arduino-app-cli/issues/521 (staff lucarin91/mirkoCrobu; 10 Jul 2026)
- github.com/arduino/arduino-app-cli/issues/101 (community)
- github.com/arduino/ArduinoCore-zephyr ; docs.zephyrproject.org/latest/boards/arduino/uno_q/
- tensorflow/tensorflow issues #46498 / #58497 / #59794 / #52155 — aarch64 GPU-delegate cross-build (community)
