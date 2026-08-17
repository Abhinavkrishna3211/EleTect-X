# Device Development Workflow — App Lab, the Bridge, Edge Impulse, and the build ladder

Read `CONTEXT.md`, `ENGINEERING_CONVENTIONS.md`, and `BUILD_BLUEPRINT_AUG8.md` first. Those fix *what* to
build, *when*, and the code-quality bar. This document fixes *how the toolchain actually works* and gives
the hardware-in-the-loop sequence. **Revised 28 Jul 2026 after a deep pass across Arduino's own docs, Edge
Impulse's own docs, the Arduino forum, and the Hackster contest page itself** — every claim below is
sourced, not assumed; unresolved items are marked as verification tasks, not facts.

## 1. Verified hardware capability map

**STM32U585 (MCU, reflex side):** Cortex-M33 up to 160MHz, 2MB flash, 786KB SRAM, FPU, runs Arduino
sketches on Zephyr RTOS. Confirmed interface list, from Arduino's own hardware table: **I2C/I3C, SPI, PWM,
CAN, UART, PSSI, GPIO, JTAG, ADC.** 14 digital I/O, Qwiic/STEMMA QT (3.3V I2C only — confirmed pin map:
pin1 GND, pin2 +3V3, pin3 SDA on PD13/I2C4_SDA, pin4 SCL on PD12/I2C4_SCL). ADC is 12-bit, 0–3.3V range.
**Corrected 29 Jul 2026 against the official pinout PDF (`docs.arduino.cc`, ABX00162, last updated 17 Feb
2026) — the 5V-tolerance claim below was overstated:** the PDF's own warning states **only A0 and A1 are
not 5V-tolerant** — every other MCU GPIO, including A2–A5, is 3.3V logic *and* 5V-tolerant. Full pin
reference now lives in `hardware/references/UNO_Q_PINOUT_REFERENCE.md` — read that before wiring anything
to a specific pin, not this summary.

**QRB2210 (MPU, cognition side):** quad-core Cortex-A53 @ 2.0GHz, Adreno 702 GPU, Debian Linux, dual ISP
(13MP+13MP or 25MP@30fps) — **no CSI camera module or carrier board exists to buy yet**, confirmed
independently, still the operative reason USB is the only currently *usable* path. Nuance added 29 Jul 2026
from the same official pinout PDF: the advanced `JMISC` header does physically break out **CSI0/CSI1 MIPI
camera lanes** (`CSI0_A0_CLK_M/P`, `CSI0_A1_LN1_M/P`, etc., plus `CCI_I2C_SCL0/SDA0` camera-control I2C) —
the silicon and pinout support a CSI camera, there's just no module to plug into it yet. Doesn't change the
frozen USB-camera decision (ADR 0001), just corrects "no CSI path exists" to "no CSI module exists to use
the path that does." Also newly noted: `JMEDIA` breaks out a second analog mic input (`MIC2_INP/INM/BIAS`)
wired to the MPU's own audio codec, not the MCU/ADC domain — a different mic path than ADR 0009's design,
which specifically needs an MCU-domain, STOP-mode-compatible channel; this MPU-side input can't substitute
for that, noted for completeness only.

**Resolved 28 Jul 2026 — checked against the actual UNO Q datasheet cross-reference and two live forum
threads on this exact question (not a guess).** The hardware answer is more nuanced than "no I2S":

- **The silicon and the pinout genuinely support it.** A knowledgeable forum member (`ptillisch`) cross-
  referenced the STM32U585 datasheet's Alternate Function tables (AF0–AF7, AF8–AF15) against the UNO Q's
  own pinout PDF and confirmed: several STM32U585 pins broken out to the UNO Q's headers — both the top
  Arduino-style headers and JMISC — do carry SAI (I2S-capable) alternate functions. This isn't a pinout gap.
- **The software path is the real blocker, and it's a current, open one, not solved.** As of a July 2026
  forum post: there is no Arduino Core library exposing SAI/I2S on the MCU side, and using it via raw
  Zephyr drivers requires device-tree overlays that **App Lab does not currently allow you to edit**. One
  forum member went further and tried enabling SAI1 directly via the STM32 HAL — result: *"I think the SAI1
  is locked… Probably in Trust Zone?"* — a plausible, unresolved report that the Cortex-M33's TrustZone
  security partitioning may be blocking direct SAI register access from ordinary sketch code, not just a
  missing-library inconvenience. **Arduino's own official Bricks module supports audio capture only via a
  USB mic through the MPU** — that's the vendor-supported path today, not MCU-side I2S.
- **Net call: don't build the critical path on MCU-side I2S.** Move acoustic classification to the
  MPU/Linux side via `edge-impulse-linux`'s native audio pipeline (§4 — the exact mechanism behind
  Arduino's own "Hey Arduino" demo, a first-class, vendor-supported path) with a **cheap USB mic**, not
  INMP441 directly — INMP441 has no easy path onto the Linux side either without an I2S-to-USB adapter, so
  it doesn't carry over as-is. Repurpose the INMP441 units already owned as a bench/reference mic for
  offline dataset collection (e.g. via a spare ESP32/RPi if one's on hand), not a field-deployed sensor;
  revisit MCU-side I2S later only as a stretch goal (the forum thread itself suggests writing a proper
  Arduino library for it would be "a significant contribution to the community" — true, but not on this
  timeline).
- **Revised again 28 Jul 2026 — a sharp catch changed the design.** The plan above ("coarse MCU trigger
  wakes the MPU, MPU listens and classifies") has a real flaw: a gunshot is a single transient, maybe
  100–500ms. If nothing is classifying *during* that window, waking a second system afterward to "go
  listen" is too late — the event is already over. This is the same reason the geophone design was never
  "wake something up when it gets loud" in the first place; it's "continuously buffer and classify a
  rolling window, and *that* classification is what wakes everything else." Acoustic needs the identical
  pattern, not a cheaper imitation of it.
- **The actual fix: run a tiny gunshot/chainsaw classifier directly on the MCU, continuously, against a
  circular buffer — not a threshold, a real classifier.** This is now de-risked by a real precedent, not a
  guess: Edge Impulse's own Expert Network has a published gunshot-classification project (Swapnil Verma,
  Arduino Nano BLE Sense + Portenta H7 — both *less* capable than the STM32U585) using MFCC preprocessing
  into a 3-layer 1D CNN (8/16/24 neurons) trained on public Kaggle audio (gunshot dataset + UrbanSound8K
  for "other"), reaching 94.5% training / 91.3% test accuracy, deployed as a small importable library. That
  model comfortably fits the STM32U585's 786KB SRAM/2MB flash. Study this project directly as the template
  — same public-dataset approach already planned for our vision model, same MFCC+small-CNN shape.
- **What decides the mic question is buffering compatibility, not "can it be wired at all."** Two real
  options, both requiring the mic's samples to feed a continuously-running circular buffer the on-MCU
  classifier evaluates in real time:
  1. **Analog electret/MAX9814-style mic on an ADC pin via LPBAM** — confirmed compatible with STOP-mode
     autonomous operation (same mechanism the geophone already uses), the lower-risk default. Needs a bench
     check that LPBAM can sustain ~8–16kHz continuous sampling (enough for useful MFCC features) alongside
     the geophone's own ADC/LPBAM channel running concurrently — a real Rung 2 test, not an assumption.
  2. **INMP441 via a bit-banged/SPI+timer I2S emulation** (ST's own AN5086 application note documents
     exactly this technique, SPI+timer faking the I2S clock relationship, sidestepping the SAI peripheral
     entirely — and this may well be how others have reported getting INMP441 samples off a UNO Q, since it
     doesn't touch the TrustZone-suspect SAI block at all). Real, but it only runs while the MCU is actively
     awake and executing that emulation loop — **not** compatible with STOP mode, so it can't be the
     continuously-buffered always-on layer by itself. It's viable only if paired with a duty-cycled
     wake (short, frequent active windows) rather than genuine µA sleep between them — a real power/fidelity
     trade against option 1, not a free upgrade.
  3. **INMP441's confirmed role either way:** bench/reference mic for building and validating the training
     dataset (better fidelity than an electret for labeling real gunshot/chainsaw/ambient recordings), and
     a candidate for option 2 if the power budget (measured, not assumed, per `ENGINEERING_CONVENTIONS.md`
     §7) turns out to tolerate the duty-cycled active-listening approach.
  Resolve which of 1/2 is the field design at Rung 2, on the bench, with a real power measurement — don't
  decide from this document alone.
- **This still reopens the MAX9814 drop-decision from earlier this session and needs an ADR** regardless of
  which mic wins — either as the option-1 sensor itself, or superseded by whichever choice Rung 2 lands on.
- **The MPU's role changes too:** once the MCU's on-device classifier confirms an event (or the geophone
  fires), the MPU wakes for fusion, LoRa alerting, dashboard logging, and — if useful — a second, higher-
  fidelity re-classification pass over a USB mic or the buffered segment sent over the Bridge, per the
  existing "send meaning, not raw data" principle (`CONTEXT.md` §5). The MPU is corroboration and action,
  not the first line of acoustic detection.

**Free UI/diagnostic hardware, already on the board:** 8×13 LED matrix, 4 RGB LEDs, 1 user button — zero
extra parts, genuinely useful for boot/trigger/LoRa-join/battery-low status on the bench and in the field
without opening the enclosure.

**Flashing:** JCTL jumper for bootloader mode. **The UNO Q does not support the `dfu-util` runner — always
use `openocd`.** Confirmed directly from Edge Impulse's own Zephyr deployment guide; this will silently
fail or mislead if assumed otherwise.

## 2. App Lab — how it actually behaves, confirmed setup sequence

**Structure:** an App is a folder — `sketch/` (C++), `python/` (Python), `assets/`, `app.yaml`, `README.md`.
**Bricks** are pre-built, attachable modules (Web Server, Camera, Object Detection, Climate/Modulino,
**and — critical for us — pre-built Edge Impulse demo bricks**, see §4).

**App files live on the board's own Linux filesystem** (`/home/arduino/ArduinoApps/<app>/` — CamelCase,
confirmed on real hardware 30 Jul 2026 via `arduino-app-cli config get`'s own "Apps Directory" field; an
earlier pass at this document had it as lowercase `arduino_apps`, which does not exist on the board), not
your PC — even in "PC mode" over USB. Consistent with Arduino's own setup docs, which
explicitly recommend **VS Code Remote-SSH** as a first-class way to work on the board — with one real
gotcha, straight from Arduino's own documentation: **disable GitHub Copilot and similar heavy extensions
when Remote-SSH'd into the board — they can cause memory issues on this low-RAM device.**

**Confirmed real setup sequence (from Arduino/Edge Impulse's own docs, not inferred):**
```bash
# Headless setup via ADB (Android SDK Platform-Tools)
adb devices                                   # confirm board is visible
adb shell                                     # log in over serial
sudo nmcli dev wifi connect <SSID> password <password>
hostname -I                                   # get the board's IP

# Start SSH once on the board (or via adb shell)
sudo apt install openssh-server -y
sudo systemctl enable ssh
sudo systemctl stop sshd
sudo ssh-keygen -A
sudo systemctl start sshd

# From your dev machine
ssh arduino@<board-ip>                        # factory default password: arduino
```
Factory-default Linux login is `arduino`/`arduino` — change it (`adb shell` → `sudo passwd arduino`)
before this node ever leaves the bench, this is a real production-auth item per the deployment bar in
`CLAUDE.md`. **Confirmed already done for the `EleTect-X` board** (Rung 0, §7 below) — `arduino`/`arduino`
no longer authenticates against it. The current password is intentionally not recorded in this repo
(no secrets in git, per `CLAUDE.md`); get it out-of-band from whoever ran Rung 0 if you need bench access.

**Simpler confirmed path, read directly from App Lab's own Learn pages (28 Jul 2026), supersedes the manual
adb dance above for day-to-day use once First Setup has run once:** App Lab's First Setup wizard (already
completed for our board, named `EleTect-X`) collects Wi-Fi credentials and a board password and **auto-
enables SSH as a side effect** — no manual `openssh-server`/`ssh-keygen` steps needed. After that, either
(a) relaunch App Lab and pick the board under **"Network"** instead of "USB" — full GUI access over the
local network, no cable, or (b) from a real terminal (not inside App Lab, which doesn't expose one for this):
`ssh arduino@<boardname>.local` — mDNS-resolved, no manual IP lookup via `hostname -I` needed. Confirmed
three distinct modes exist: **Desktop Mode** (USB, host computer drives App Lab), **Network Mode** (SSH over
local Wi-Fi, no cable, what the two paths above use), **Standalone/SBC Mode** (USB-C dongle + HDMI + kb/mouse,
board runs App Lab on itself — a bench-convenience mode with no role in a headless field node, and requires
its own 5V/3A supply for the dongle, separate from the board's own power). Network Mode requires the board
and dev machine on the same local network — real for bench/install-day work, not something the deployed node
relies on at runtime (LoRa is the uplink, not local Wi-Fi).

**App Lab's own editor is genuinely rough (confirmed independently, current as of recent releases):** no
find/replace, no autocomplete, no debugger. **Reconciling with "the git monorepo is the source of truth"
(`ENGINEERING_CONVENTIONS.md`):** edit `device/mcu`/`device/mpu` in VS Code in the repo → sync
one-directionally, repo → board (`rsync`/`scp`, or a VS Code Remote-SSH session against the board) →
build/run/watch console via App Lab or the **Arduino App CLI** (scriptable, fits a git-driven workflow far
better than a GUI) → never hand-edit the board's copy and call it done. Write `scripts/sync-to-board.sh`
at Rung 0 so this is a one-liner, not a manual step someone forgets.

**Security hardening for field deployment — confirmed 29 Jul 2026 against Arduino's own security-hardening
tutorial, directly relevant to `CLAUDE.md`'s "production auth" requirement.** Concrete, actionable items
before any node leaves the bench, beyond the already-known password change:
- **Disable ADB after flashing/debugging is done**: `sudo systemctl stop adbd && sudo systemctl disable
  adbd`. ADB-over-USB is on by default and is a physical-access risk on a field-deployed unit — anyone with
  a USB-C cable and physical access to the enclosure gets a shell otherwise.
- **No TCP ports are open by default** — good starting posture. If remote debugging access is ever needed
  post-deployment, the recommended pattern is `iptables INPUT DROP` + a local-only `ACCEPT` rule + SSH
  tunneling (`ssh -L`), not opening a port directly.
- **WebUI Brick supports HTTPS** via `WebUI(use_ssl=True)` with either `mkcert` (self-signed, fine for
  bench/LAN) or a real CA cert — relevant if any on-node web dashboard/config UI ships in the field build.
- **Encryption-at-rest** available via `ecryptfs-utils` for the `arduino` user's private directory — worth
  using if any locally-cached sensitive data (Wi-Fi credentials, future API tokens) needs it.
- **Monitoring**: rsyslog remote forwarding + Monit (disk/service alerts, email) — a real option for
  fleet-level health monitoring at scale, not needed for the bench build now, worth remembering for the
  multi-node deployment phase.

**AI-coding-agent guidance, confirmed from Arduino's own tutorial for this exact board:** Claude Code is
officially supported running directly on the board's Linux side (`curl -fsSL https://claude.ai/install.sh |
bash`, plus a `claude remote-control` mode) — not just from a host-machine VS Code session. We're not
switching to that workflow (host-side dev + `sync-to-board.sh` stays the plan, per §2 above), but two things
from that tutorial are worth carrying into our own security posture: **an agent running on the board has
full `arduino`-user permissions with no sandbox**, and **ADB-over-USB being on by default is flagged as a
real risk specifically in the context of an agent with shell access** — both are the same reasoning behind
"disable adb before field deployment" above, now confirmed from two independent official sources, not one.

## 3. The Bridge — real API, and a real, currently-reproducible bug pattern to design around

**API, confirmed from Arduino's own examples:** C++ side — `#include <Arduino_RouterBridge.h>`;
`Bridge.begin()`; `Bridge.provide("name", func)` (there's also `Bridge.provide_safe()` — a hardened
variant seen in active forum use, worth checking its docs before choosing between the two);
`Bridge.update()` in `loop()`. Python side — `from arduino.app_utils import Bridge` (or
`from arduino.app_utils import *`); `Bridge.call("name", args...)`, synchronous request/response.

**What's underneath, confirmed 29 Jul 2026 from Arduino's own RouterBridge multi-language docs — not needed
for anything we're building now, but worth knowing exists:** `Bridge.call`/`Bridge.notify` are a thin
sketch-level API over `arduino-router`, a systemd daemon speaking **MessagePack-RPC over a Unix socket**
(`/var/run/arduino-router.sock`), with REQUEST/RESPONSE/NOTIFY wire message types plus internal `$/register`
and `$/reset` control methods. A future service that needs Bridge access outside of a sketch (C++/Python/
Rust/Node/Go are all supported client languages) could talk to the router directly instead of going through
App Lab's sketch/Python split — not a need for the current schema (`device/mpu/bridge/schema.md`), noted for
whoever eventually needs it.

**A real, current, reproducible bug — worth designing the build process around, not just knowing about:**
multiple active forum threads (Bridge.provide() issues, "method not available", App Lab 0.7.0 breaking
existing apps) show a *specific* reproducible pattern: registering an additional `Bridge.provide()`
function — particularly one with a `float` argument in the observed report — broke every previously-working
provided function on the same sketch, including totally unrelated ones. This reproduced identically
whether using App Lab or VS Code + Remote-SSH (so it's a core library issue, not an App-Lab-GUI quirk), and
responses varied by App Lab/core version (some fixed by upgrading, some not). **Practical discipline this
earns a place in `ENGINEERING_CONVENTIONS.md` §8:** register Bridge functions **one at a time**, testing
each addition on real hardware before adding the next — never batch-register a set of new functions and
assume they'll all work. This directly reinforces Rung 0's "smallest possible test function" principle;
it's not paranoia, it's a documented current failure mode.

A long, active community thread — "Arduino UNO-Q example: reading GNSS NMEA data and displaying it in a
web dashboard" (161 replies) — is a real MCU-sensor→Bridge→MPU-dashboard pattern worth skimming if the
Bridge design hits friction; bookmark it in `KNOWN_GAPS.md` as a reference rather than reading it end to
end now.

**Design task (Opus, per `BUILD_BLUEPRINT_AUG8.md` §8):** a table of Bridge functions — name, provided-by,
called-by, args, return type, timeout/failure behavior — same shape as before, now informed by the real
bug pattern above (build and test it one row at a time).

## 4. Edge Impulse — fully confirmed deployment paths, and a major shortcut

**STM32U585 (Zephyr) side — confirmed exact CLI workflow, not a guess:**
```bash
mkdir ~/zephyrproject && cd ~/zephyrproject
west init -m https://github.com/edgeimpulse/example-standalone-inferencing-zephyr-module
cd example-standalone-inferencing-zephyr-module && west update
# In EI Studio: Deployment > Zephyr Module > Build > download the .zip
mkdir -p model && unzip ~/Downloads/my_model-zephyr.zip -d model
# Add to CMakeLists.txt: list(APPEND ZEPHYR_EXTRA_MODULES ${CMAKE_CURRENT_SOURCE_DIR}/model)
# Set board in .west/config: board = arduino_uno_q
west build -b arduino_uno_q --pristine
# Flash (two terminals):
#   T1: adb forward tcp:3333 tcp:3333 && adb shell arduino-debug
#   T2: west flash -r openocd        (openocd only — dfu-util unsupported)
```
**Real open question, flagged by Edge Impulse's own docs, not by us:** `west` support for the UNO Q is
explicitly called "still experimental," and `arduino_uno_q` is described as "a working target until
official uno_q Zephyr support is merged." **This means the EI-model firmware is a separate `west`/Zephyr
project, not something dropped into an App Lab sketch folder as a dependency** — verify at Rung 0/1 whether
the Zephyr module's `CMakeLists.txt` line can be vendored directly into an App Lab sketch (which is itself
a Zephyr/Arduino-Core project under the hood) or whether the footfall model genuinely needs its own
standalone `west` build+flash pipeline, separate from the App Lab-managed sketch that hosts the Bridge
code. This is a real fork in the implementation — resolve it as an explicit Rung 0/1 task, don't assume
either way.

**QRB2210 (Linux) side — confirmed exact CLI workflow:**
```bash
sudo apt update
curl -sL https://deb.nodesource.com/setup_20.x | sudo bash -
sudo apt install -y gcc g++ make build-essential nodejs sox \
  gstreamer1.0-tools gstreamer1.0-plugins-good gstreamer1.0-plugins-base gstreamer1.0-plugins-base-apps
sudo npm install edge-impulse-linux -g --unsafe-perm
edge-impulse-linux            # wizard: log in, pick project, connects camera/mic as a Studio device
edge-impulse-linux-runner     # deploys back, compiles with full hardware acceleration automatically
```
Hardware acceleration (Adreno GPU) is automatic through this runner — not something to hand-configure.
One real gotcha from EI's own troubleshooting: an `Unsupported architecture "aarch64"` error on `.eim`
deploy means a 32-bit OS is running on the 64-bit CPU — sanity-check the board's OS architecture during
Rung 0 setup, not after a confusing deploy failure.

**Major shortcut, confirmed and worth building the plan around: Edge Impulse ships pre-built, working demo
Bricks in App Lab already — a "Hey Arduino" keyword-spotting audio classifier and a face-detection computer
vision demo (USB webcam).** These aren't just "EI supports UNO Q" marketing — they're real, runnable
starting templates. **Recommended concrete approach, not building from scratch:** fork the keyword-spotting
Brick's project structure for the gunshot/chainsaw acoustic classifier (same MFCC audio-classification
pipeline in EI Studio, retrain on gunshot/chainsaw/forest-ambient classes instead of "hey arduino"); fork
the face-detection Brick's structure for the elephant/wildlife vision detector (same object-detection
pipeline, retrain on elephant/boar/deer classes). This meaningfully de-risks the ML timeline and gives a
strong, honest Hackster narrative — "built on Arduino's and Edge Impulse's own official reference Bricks,
retrained for wildlife deterrence," not "reinvented the pipeline under deadline pressure."

**Cascading models is still not needed** — three independent models (footfall/MCU, vision+acoustic/MPU)
feeding the hand-written log-odds fusion remains correct; a cascade adds a silent-failure mode for no real
gain at this scale.

**Reviewed in full (28 Jul 2026): the "Fan Vibration Monitoring" and "Real-time Accelerometer" example
Bricks, code and public Edge Impulse projects both.** Verdict, split cleanly in two: the *code shape* is a
genuinely good, official-Arduino-blessed precedent for our footfall pipeline —
`accumulate_samples()` into a `SlidingWindowBuffer` sized to the model's `input_features_count`,
`infer_from_features()`, threshold callback via `on_anomaly()` — structurally the same pattern our own
STA/LTA-into-classifier design already follows, just with Arduino's own naming for the pieces. But the
*power architecture* does not transfer and must not be copied: both examples have the MCU sketch calling
`Bridge.notify()` on every single sample at a fixed 10–16ms interval (62.5–100Hz), which means the MCU is
continuously awake and the MPU is continuously awake and listening — correct for a mains-powered fan
monitor, exactly the always-on-MPU cost ADR 0008 and ADR 0009 exist to avoid for a battery/solar field node.
Do not port the "MCU polls, Bridge every sample" pattern into the geophone reflex path; keep the
classification itself on-MCU per ADR 0009, and treat Bridge as the event-notification channel, not the
sample-transport channel.

One more distinction worth carrying forward correctly: "Fan Vibration Monitoring" uses Edge Impulse's
**anomaly detection** project type (train only on normal-running baseline, flag deviation) — appropriate for
a fan, where "normal" is well-defined and abnormal is open-ended. Our footfall problem is **classification**
(footfall vs. ambient, both sides labeled from bench stomp-tests), which is what ADR 0001's dataset plan
already assumes — no conflict, just confirms we want the classification project type in EI Studio, not the
anomaly-detection one, when the footfall project is created. The public EI Studio project links in both
example READMEs (`studio.edgeimpulse.com/public/497631` for motion classification,
`studio.edgeimpulse.com/public/774707` for vibration anomaly) are worth opening for DSP-block and
model-architecture reference regardless of the class-label mismatch.

## 4a. Dataset collection — parallelized across all three models, starting now

The firmware build ladder in §6 is sequential by necessity (each Rung depends on the toolchain proven at
the last one). Dataset collection has no such dependency — an Edge Impulse project can be populated with
labeled data whether or not `device/mcu`/`device/mpu` code exists yet. `BUILD_BLUEPRINT_AUG8.md`'s Day 1
already creates all 3 Edge Impulse projects (footfall, acoustic, vision) empty on Sun 26 Jul, ahead of any
firmware Rung — the intent was already parallel, this section makes the sourcing plan for each one
concrete, and flags which one is furthest ahead of where its Rung/day placement implies.

**The key correction to make explicitly: vision dataset work does not need to wait for Rung 6.** Rung 6
(camera) sits last in the firmware build ladder because that's when USB enumeration and the
`edge-impulse-linux` device connection get wired up — a real dependency on Rung 0's toolchain setup. But
per `hardware/bom/procurement-status.md` §1, the Arducam IMX462 is **already in hand, no stand-in needed**
— the only hardware-gated part of vision work is late; the dataset itself is not gated on anything and can
be built in parallel starting today, same as footfall and acoustic.

### Footfall / geophone model
- **Status:** furthest ahead — Rung 1's bench stand-in (ADS1115+INA333) is already in hand and is the
  actual sensor path Day "Wed 29 Jul" trains against, not a placeholder for something else.
- **Data sources:** bench stomp-tests (a person stomping near the buried/bench geophone at varying
  distances/gaits, labeled footfall vs. ambient — wind, rain, traffic microseism, other animals) are the
  primary near-term source, already planned per `BUILD_BLUEPRINT_AUG8.md` Wed 29 Jul. Synthetic traces
  matching the published elephant footfall frequency signature (ADR 0001's seismic band, ADR 0008's
  140–155m range study) with realistic noise layered in extend the bench data without needing a live
  elephant. Worth checking directly: whether the Wijayakulasooriya et al. paper family (ADR 0001/0008) has
  released any public geophone dataset alongside their published results — verify before assuming none
  exists.
- **A distinctive opportunity worth raising with DFO specifically:** the Kothamangalam field partnership
  opens a door most teams building this kind of system don't have — a supervised, permitted recording
  session with a captive elephant (temple or sanctuary settings exist across Kerala) would produce real
  labeled elephant-footfall seismic data, not a human-stomp proxy. This is worth a direct ask to DFO given
  the relationship already in place, and would be a genuinely distinctive dataset advantage to document.
- **Annotation:** Edge Impulse Studio's own data acquisition + labeling workflow is sufficient — no
  external tool needed for single-channel time-series data.

### Acoustic model
- **Status:** can start immediately, independent of ADR 0009's capture-mechanism bench test. Training data
  and the Edge Impulse project are a data/label question, not a firmware/deployment question — the same
  labeled audio trains the classifier regardless of whether LPBAM-continuous or SAI-event-triggered ends up
  as the field capture path.
- **Data sources:** public datasets are the primary, fastest source and the ones already named in this
  document's own precedent study — the Kaggle gunshot dataset + UrbanSound8K (for "other"/background),
  per the Verma Edge Impulse Expert Network project (§1). These give a working baseline immediately.
  Supplement, don't replace, with local recordings: INMP441 (confirmed bench/reference mic regardless of
  which capture path wins, §1/§6) recording actual Kerala forest ambient noise (monsoon, insects, birds) —
  this matters more than it sounds, since PMC6387379 (ADR 0007's own cited source) explicitly warns that
  local ambient fauna can mask or be confused with target classes, and UrbanSound8K's background clips are
  US-urban, not forest-ambient. Chainsaw and vehicle classes: local recordings where safely accessible, or
  public sources (forest-adjacent construction/logging audio, vehicle-pass-by recordings) if not.
- **Gunshot specifically — do not attempt to generate this class by firing real weapons.** Hackster's own
  contest rules exclude weapons-adjacent content, and there's no safe or legal way to generate this data
  ourselves regardless. The public Kaggle gunshot dataset is the right and only source for the transient
  signature itself; local recordings should stay confined to the ambient/background and other-class data
  where real safety and legality are not in question.
- **Annotation:** Edge Impulse Studio's upload + crop + split + label workflow (the same one the Verma
  project and the keyword-spotting Brick already use, §4) is the standard path — no separate tool needed.

### Vision model
- **Status:** hardware is not the blocker — the IMX462 is in hand. Dataset sourcing/annotation should start
  now, in parallel with the Rung 0–5 firmware work, not wait for Rung 6.
- **Data sources:** public wildlife/camera-trap datasets (already the plan per ADR 0001 and
  `BUILD_BLUEPRINT_AUG8.md` line 41 — public elephant/wildlife imagery plus night-augmentation) remain the
  fastest path to a working v1 model, scoped to ADR 0001's narrowed class set (elephant / wild boar /
  background) rather than the full CONTEXT.md species list. Real, own-captured footage with the actual
  IMX462 can supplement in parallel wherever accessible (test rig, yard, any safe setting) — useful for
  domain-matching the real sensor's actual image characteristics (lens, sensor noise, IR-cut behavior)
  even before elephant-specific footage is possible.
- **Another DFO-specific opportunity worth raising directly:** forest departments running existing
  camera-trap monitoring programs often already hold real, local camera-trap footage/imagery. Given the
  Kothamangalam partnership already in place, it's worth directly asking DFO whether any existing
  footage can be shared for training data — this would be real, local, Kerala-specific imagery, a
  meaningfully stronger dataset than public sources alone, and worth pursuing regardless of whether the
  captive-elephant seismic recording opportunity above also comes through.
- **Annotation:** Roboflow (already the plan per ADR 0001, used as a model-assisted labeling accelerator via
  MegaDetector run purely offline) for bounding-box annotation, then export into the Edge Impulse vision
  project — consistent with ADR 0001's existing decision, not a new tool choice.

### The one open procurement item this reopens
ADR 0009's primary design needs an analog electret/MAX9814-style mic on a dedicated ADC channel — the exact
part `procurement-status.md` Flag #2 dropped as redundant with INMP441 for corroboration/classification.
That reasoning still holds for classification; it doesn't hold for LPBAM's continuous-capture-channel role,
which is a different function. This needs explicit sign-off before `bom.md`/`procurement-status.md` are
touched, same condition ADR 0006 already named for the same part in its original (now-superseded) role.

**Confirmed 29 Jul 2026, directly in App Lab's Bricks catalog (not assumed): every AI-model Brick's "AI
models" tab has a "Train new AI model" button that opens Edge Impulse Studio directly (Arduino-account
login required), alongside whatever pre-trained model already ships with that Brick.** Checked concretely
on the Audio Classification Brick — which ships with exactly one pre-trained model ("Glass breaking
classifier," 13MB, Edge Impulse-sourced) — the same "Train new AI model" pattern is consistent across the
other AI-model Bricks (Image Classification, Keyword Spotting, Motion Detection, Object Detection, Visual
Anomaly Detection) per their shared "AI models" tab layout. This is the actual, confirmed deployment path
for our own trained models: train in Edge Impulse Studio (the same three projects already created per
`BUILD_BLUEPRINT_AUG8.md` Day 1), and the resulting model becomes selectable in the relevant Brick's AI
models list — not a separate, hand-built import mechanism. Also confirmed: the **Audio Classification**
Brick (`arduino.app_bricks.audio_classifier.AudioClassifier`, distinct from the narrower Keyword Spotting
Brick) needs a USB-C hub with USB-A or 3.5mm audio input — same MPU-side continuous-listening architecture
already correctly ruled out for our field design, consistent with everything else confirmed this session.

## 5. Contest intelligence — read this before writing the story, not after

**The "AI-Powered Wildlife Monitoring System" idea is not a leaked competitor project — it's literally one
of eighteen example prompts the Hackster/Arduino/Qualcomm/Edge Impulse contest page itself suggests**,
listed under "Social Impact" alongside a climate data logger and a water-quality monitor. This is good
news framed correctly: it confirms the *category* of idea is exactly what the sponsors are hoping to see,
and there's a dedicated **Best Social Impact prize ($3,000)** plus **Best in Show ($5,000 + a paid trip to
Maker Faire Rome)** to explicitly target. But the example prompt itself is passive — "detect and classify
species... track... prevent poaching." **EleTect X is materially more than that prompt, and the write-up
should say so explicitly, not just imply it:** active multi-modal deterrence (light + sound, not just
detection), real sensor fusion (seismic + acoustic + vision via log-odds fusion, not camera-only),
on-device contextual-bandit learning (never-repeat, stop-on-retreat), mesh coordination between nodes, and
— unlike almost any hackathon entry — a real forest-department field partnership with actual deployment
plans. Foreground that gap explicitly in the submission story; don't assume judges will infer it from a
feature list.

**Contest facts, confirmed from the live page (28 Jul 2026):** $20,000 total prize pool across 6 category
winners (Best in Show, Robotics, Industrial IoT, Gaming, Home Automation, Social Impact). 55 submissions
and 3,783 participants registered so far — a real field, not a niche one. Submissions close **30 Aug 2026,
11:59 PM PDT**; winners announced **25 Sep 2026**. Ecosystem partners beyond the three headline sponsors
include HuggingFace, Foundries, SparkFun, Seeed Studio, Farnell, and STMicroelectronics — a HuggingFace
model integration (even a small one, e.g. for a richer species classification label set) could be a
legitimate, low-cost way to touch a fourth named ecosystem partner in the write-up.

## 6. The hardware-in-the-loop build ladder

Runs *underneath* `BUILD_BLUEPRINT_AUG8.md`'s day-by-day schedule, sharpening what each row means. Every
rung: connect the real part → smallest possible Bridge-exposed test function, **added and tested one
function at a time per §3** → confirm a real reading/action, committed → only then fold into the real
pipeline.

- **Rung 0 — the toolchain itself.** **Confirmed 28 Jul 2026, on real hardware:** flash via the flasher
  CLI succeeded (partition-level log, board rebooted, LED matrix animation confirmed Linux boot), App Lab
  installed and paired the board (named `EleTect-X`, WiFi joined), Linux default password changed per §2's
  requirement, and — the part that actually mattered — a real Bridge round trip is proven working via the
  stock Blink LED example (Python on the MPU side toggling a GPIO the MCU sketch drives, confirmed running
  in the App Lab log). That de-risks the one open question this Rung existed to answer: the Bridge itself
  works end to end on this board, not just on paper.
  **Confirmed 28 Jul 2026: the 4GB unit was flashed and used for this exploratory Examples-browsing session**
  (Blink LED, plus a wider pass through App Lab's Examples catalog — QR/barcode scanner, object detection,
  accelerometer, "Hey Arduino" keyword spotting, and two directly relevant precedents worth a closer look
  later: **"Real-time Accelerometer"** and **"Fan Vibration Monitoring"**, both built on the Modulino
  Movement sensor — same anomaly-over-a-rolling-window shape as our own geophone STA/LTA pipeline, worth
  studying as a second reference alongside the "Hey Arduino" keyword-spotting Brick already named in §4).
  This kind of exploratory example-running on the bench unit is exactly what a bench/dev board is for, not a
  problem — the "never touch once flashed" caution in `procurement-status.md` is about not reflashing/
  reconfiguring the *field-bound* unit once it's in its final deployment state, not about avoiding all use
  early in development.
  **Still open before Rung 0 is fully closed:** (1) `procurement-status.md`'s "2GB + 4GB" line never actually
  specified which capacity is the bench unit and which is field-bound — worth deciding that explicitly now
  (before both boards accumulate enough divergent history to make it ambiguous) and physically labeling the
  two boards, since they're otherwise visually identical. (2) the
  update log shows a real `apt` fetch failure for `arduino-cli_1.5.1` (`Network is unreachable`) followed by
  a reported "successfully" — verify the actual installed version over SSH (`arduino-cli version`) rather
  than trust the wizard's success message. (3) create the `eletect` App skeleton (this Rung's Blink LED test
  ran from App Lab's stock Examples, not a project app yet), write `scripts/sync-to-board.sh`, confirm the
  board's OS is genuinely aarch64 (§4), and resolve the Zephyr-module-vs-App-Lab-sketch open question from
  §4 — it affects how Rung/Day tasks involving the footfall model get structured from this point forward.
- **Rung 1 — geophone (ADS1115+INA333 bench stand-in), Qwiic/I2C.** `test_geophone_read()`, confirm a real
  bench-stomp signal before writing STA/LTA against it. **Also the first half of ADR 0009's load-bearing
  concurrency test:** once this channel is running via LPBAM, it's the baseline the Rung 2 mic channel has
  to run alongside without contention.
- **Rung 2 — mic capture, per ADR 0009 (supersedes this rung's original I2S-first framing).** Primary path:
  wire an analog electret/MAX9814-style mic to a second ADC pin and confirm LPBAM can sustain it
  concurrently with Rung 1's geophone channel — same STOP-mode mechanism, two channels, one test
  (`test_acoustic_read()` running alongside `test_geophone_read()`, not standalone). This is the single
  bench result ADR 0009 is gated on. If concurrency holds, this is the field design — no I2S needed. If it
  doesn't (channel contention, sample rate, or power budget), fall back to ADR 0006's design as written:
  electret + LM393 comparator as an always-on wake gate, INMP441 via direct SAI register access
  (Rahul's proven method, §1) as an event-triggered burst capture. Either way, INMP441 stays useful as the
  bench/reference mic for dataset recording (§4a) regardless of which path wins.
- **Rung 3 — DFPlayer Mini + TPA3116D2 + bench speaker.** Confirm audible deterrent playback before the
  real SUH-15 horn lands.
- **Rung 4 — actuators (LED via IRLZ44N, IR MOSFET).** Confirm visible/measurable output before wiring into
  the deterrence state machine.
- **Rung 5 — LoRa via Grove E5.** Real OTAA join against the SenseCAP gateway — resolves the EU868/IN865
  region flag from `hardware/bom/procurement-status.md` for real.
- **Rung 6 — camera (IMX462, USB).** No CSI path exists; confirm USB enumeration and a real frame grab
  before writing detector code, then set up the `edge-impulse-linux` device connection and fork the
  face-detection Brick per §4.
- **Rung 7 — BME280 / MPU-6050 on Qwiic.** Trivial I2C reads, last, off the critical path.

## 7. Documentation structure — built as you go, for Hackster and Robu both

Robu weights Technical Documentation at 20/100; Hackster weights Documentation/Story at 30/100 plus
Schematics at 15/100 — judged on whether a stranger could rebuild the project from the write-up alone.
Structure every module the same way from Rung 0:

- One `README.md` per module folder — what it does, Bridge functions provided/called, real pin-to-pin
  wiring, a photo or console capture of that rung's test passing.
- `docs/architecture/wiring/` — one diagram per subsystem, built alongside its rung test.
- ADRs record *why* (already established, 5+ exist); READMEs record *how to rebuild it* — both needed.
- Given §5's framing point, explicitly draft the "why this is more than the example prompt" paragraph
  early — during Rung 4/5 when the deterrence+fusion loop is real and demonstrable — not as an afterthought
  during the Aug 15–23 submission sprint.

## Immediate next action

Rung 0, today, in this order: flash with `openocd` (not `dfu-util`) → SSH setup per §2's confirmed
commands, changing the default password → resolve the Zephyr-module-vs-App-Lab-sketch structural question
from §4 → write `scripts/sync-to-board.sh` → hello-world Bridge round trip with exactly one provided
function, tested before adding a second.
