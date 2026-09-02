# Arduino UNO Q — power and unattended-operation notes

Scope: how to power an Arduino UNO Q (ABX00162: Qualcomm QRB2210 MPU + STM32U585 MCU, Debian
Trixie) for a multi-day unattended field deployment, and how to stop the recurring spontaneous
crash-reboots. Research date: 2 Sep 2026. Every claim is linked to its source; unverified items
are listed at the end.

---

## Summary — the fix, if there is one

The reboots are almost certainly **power-delivery collapse on the shared 5 V rail**, not a
software fault. The board draws ~0.65 A at idle and ~0.9 A with all four A53 cores loaded
(3.3–4.5 W at 5 V) *before* you add a camera, a USB-Ethernet adapter, or any actuator
([Tom's Hardware measurement](https://www.tomshardware.com/raspberry-pi/arduino-uno-q-review)).
Arduino's own spec says: *"Use a stable 5 V / 3 A source. If the supply current-limits during
peaks, voltage hang may cause resets"*
([power spec](https://docs.arduino.cc/tutorials/uno-q/power-specification/)). A passive USB-C
hub in the power path, fed from a charger it never PD-negotiates with, cannot hold 5 V through
load transients — so the rail browns out and the SoC drops with no panic/watchdog/OOM trace.
Arduino moderators give the same diagnosis on every "random reboot / green LED blinks off"
thread: the hub / upstream supply is the fault, capacitors do not fix it
([reboot thread](https://forum.arduino.cc/t/uno-q-keeps-rebooting-power-brownout/1438230),
[boot-fail thread](https://forum.arduino.cc/t/boot-fail-any-reason-for-this/1443623)).

Concrete actions, best first:

1. **Feed the board through the VIN pin from a regulated DC supply (7–24 V), not through the
   hub's 5 V pass-through.** VIN goes through the on-board LMR51440 buck straight onto 5V_SYS
   and completely sidesteps USB PD negotiation and the hub's sagging 5 V rail
   ([power spec](https://docs.arduino.cc/tutorials/uno-q/power-specification/)). Size the
   supply for the full 5 V load with margin and keep the VIN leads short and thick (Schottky
   OR drop ~0.37 V at 1.5 A per the
   [datasheet](https://docs.arduino.cc/resources/datasheets/ABX00162-ABX00173-datasheet.pdf)).
   Caveat: powering via VIN disables the USB-C VBUS output, so USB peripherals then need their
   own powered hub (see Q4).

2. **If staying on USB-C, drive the board's USB-C port directly from a genuine 5 V / 3 A (15 W+)
   supply with a good captive cable — no hub between charger and board.** Put the camera and
   USB-Ethernet on a *separately powered* hub downstream, so their inrush never touches the
   board's rail. Avoid generic unbranded bricks
   ([power spec](https://docs.arduino.cc/tutorials/uno-q/power-specification/),
   [hub/PSU thread](https://forum.arduino.cc/t/recommended-usb-c-hub-and-power-supply-for-arduino-uno-q/1421294)).

3. **Give every high-current peripheral (camera, IR/LED driver, actuator) its own supply or a
   powered hub.** The header 5 V pins are pass-through from the same input path and are shared
   with on-board loads — the spec explicitly says budget peripherals within that shared rail
   and expect available current to vary with board activity
   ([power spec](https://docs.arduino.cc/tutorials/uno-q/power-specification/)).

4. **Verify the rail is not sagging** with `journalctl -k` around a crash (look for silent
   drops vs. any regulator/undervoltage message), and check the Type-C contract as described
   in Q2. On this board a proper contract is *not required* to exceed 500 mA, but confirming it
   removes one variable.

There is **no documented Linux-side hardware watchdog** to lean on, and **no fitted RTC backup
cell**, so the clock loss across reboots is expected until the rail is fixed (Q3, Q5).

---

## Q1 — Power input options, real current need, charger vs PD vs hub

### Inputs (there is no barrel jack; no PoE)

| Input | Spec | Path onto 5V_SYS | Notes |
|---|---|---|---|
| USB-C VBUS (JUSB1) | 5 V, ≥ 3 A recommended, 4.5–5.5 V allowed | Schottky diode-OR | Also does USB 3.1 data + DisplayPort Alt-Mode; requests only a 5 V/3 A PD contract |
| VIN / DC_IN pin (on JMEDIA and JANALOG) | 7–24 V (7.0 min, 24.0 max), reverse-polarity protected to −24 V | LMR51440 buck → 5 V → Schottky diode-OR | No barrel connector — wire into the VIN header pin. Buck OR-drop ≈ 0.37 V @ 1.5 A |
| 5 V pin (JANALOG) | Regulated 5 V, ≥ 3 A | Schottky diode-OR | Direct onto 5V_SYS, bypasses the buck |

Sources: [power spec](https://docs.arduino.cc/tutorials/uno-q/power-specification/),
[datasheet](https://docs.arduino.cc/resources/datasheets/ABX00162-ABX00173-datasheet.pdf),
[VIN/USB forum thread](https://forum.arduino.cc/t/uno-q-whats-the-final-word-on-powering-via-vin-and-connecting-usb-devices-to-usb-c-port-with-a-hub/1447175).
(Note: some third-party guides call the VIN pin a "barrel jack" — the board has none;
[etechnophiles](https://www.etechnophiles.com/arduino-uno-q-pinout-guide/) is wrong on this
point, Arduino's docs and forum are explicit.)

USB-C VBUS and the buck output are **diode-OR'd** onto 5V_SYS; the two can be present at once
and the higher one wins. When VIN is applied the board **disables USB-C VBUS output**
(`usb_vbus: disabling` in the log) to avoid back-feeding 7–24 V into a host
([USB-power-disabled thread](https://forum.arduino.cc/t/uno-q-usb-power-disabled-if-using-vin-power-pin/1411831)).

### Power tree (for peripheral planning)

`5V_SYS` → TPS62A02A → `PWR_3P8V` 3.8 V (reserved / "future features", VBAT ties here) →
TPS62A02A → `PWR_3P3V` 3.3 V (main rail: STM32U585, ANX7625, level-shifter B-side, header 3.3 V,
QWIIC) ; `PM4125` PMIC LDO L15A → `VREG_L15A_1P8V` 1.8 V (QRB2210 I/O, Wi-Fi/BT I/O, JMISC/JCTL).
Source: [power spec](https://docs.arduino.cc/tutorials/uno-q/power-specification/).

### How much current it actually needs

| State | Power @ 5 V | Approx current | Source |
|---|---|---|---|
| Idle (Linux up) | ~3.3 W | ~0.66 A | [Tom's Hardware](https://www.tomshardware.com/raspberry-pi/arduino-uno-q-review) |
| 4× A53 at 100 % | ~4.5 W | ~0.90 A | Tom's Hardware |
| Sustained stress (~90 % load) | ~4.4 W | ~0.88 A | Tom's Hardware |
| Boot | not published — highest transient; boot takes ~34.6 s | — | Tom's Hardware |

Add camera + USB-Ethernet + IR/LED/actuator on top of that. Arduino specifies the input as
**5 V / 3 A** and repeatedly warns that Wi-Fi bursts and display bring-up cause peak draw that
a current-limiting supply cannot follow → "voltage hang may cause resets"
([power spec](https://docs.arduino.cc/tutorials/uno-q/power-specification/)). Community
guidance: 1 A / 2 A chargers "often lead to brownouts when Wi-Fi or the camera is active";
a Raspberry Pi 27 W USB-C PSU or a good modern 15 W+ USB-C charger is fine; avoid unbranded
bricks ([Pi Hut / help-centre style guidance surfaced in search](https://support.arduino.cc/hc/en-us/articles/360018922259-What-power-supply-can-I-use-with-my-Arduino-board)).

### Charger vs PD charger vs hub

- **Plain 5 V charger, direct to the board, that can actually source 3 A:** works. PD not needed
  (see Q2).
- **PD charger, direct to the board:** works; board just takes the 5 V/3 A fixed contract.
- **Any charger *through a passive/uncertified USB-C hub*:** this is the failure mode. Arduino
  moderators attribute the "random reboot", "green LED flickers off", "boot fail" reports to
  the hub not holding 5 V under load; the green LED is wired straight to 3.3 V with no software
  control, so if it drops "this means a failure of the power system … external to the board"
  ([boot-fail thread](https://forum.arduino.cc/t/boot-fail-any-reason-for-this/1443623),
  [reboot thread](https://forum.arduino.cc/t/uno-q-keeps-rebooting-power-brownout/1438230)).
  If a hub must be used it has to be a quality PD hub with 100 W pass-through, itself fed from
  a PD laptop-class brick (users report UGREEN Revodok 105/106, Anker 5-in-1, Hiearcool 8-in-1
  working; [hub/PSU thread](https://forum.arduino.cc/t/recommended-usb-c-hub-and-power-supply-for-arduino-uno-q/1421294)).

For a fixed field box, **VIN from a proper DC supply is the cleaner answer** — no hub, no PD,
no CC-pin lottery
([24/7-node thread](https://www.edaboard.com/threads/powering-the-arduino-uno-q-sbc-via-usb-c-vs-vin-%E2%80%93-stability-for-24-7-nodes.417491/)).

---

## Q2 — Does the UNO Q need PD to draw > 500 mA? `power_operation_mode` meaning, how to verify

**PD negotiation is not required for this board to exceed 500 mA.** Evidence:

- The board pulls ~0.66 A at idle from a source it has not PD-negotiated with, and runs for
  hours — it is clearly not being hard-limited to the 500 mA USB-default floor.
- Arduino's spec frames the requirement purely as "use a stable 5 V / 3 A source"; it never
  says "a PD contract is mandatory to pass 500 mA"
  ([power spec](https://docs.arduino.cc/tutorials/uno-q/power-specification/)).
- The board only ever *requests* a fixed **5 V / 3 A** contract and refuses higher-voltage PD
  profiles ([power spec](https://docs.arduino.cc/tutorials/uno-q/power-specification/),
  [datasheet](https://docs.arduino.cc/resources/datasheets/ABX00162-ABX00173-datasheet.pdf)).
  So even with perfect PD you get 5 V, not 9/15/20 V — VIN is the only way to bring in a
  higher voltage.

`power_operation_mode: default` vs `usb_pd` (Linux Type-C class, `/sys/class/typec/port0/`):

| Value | Meaning |
|---|---|
| `default` | Sink is running on plain USB current rules — 500 mA (USB2) / 900 mA (USB3) *advertised* budget. No explicit PD or Type-C current contract was established. |
| `1.5A` / `3.0A` | Type-C (Rp resistor) current advertisement seen on CC — 1.5 A or 3 A available without PD messaging. |
| `usb_pd` | A full USB-PD explicit contract was negotiated with a `port0-partner`. |

Your board reporting `default` with **no `port0-partner`** means the upstream (the Mport 51
hub) is presenting nothing on the CC pins — no Rp current advertisement and no PD. The board
then *assumes* only the USB-default budget is guaranteed, but in practice still pulls what it
needs from VBUS; the hub's 5 V rail simply can't supply the transient and it browns out. This
is a **downstream/hub quirk**, not a rule that the UNO Q enforces a 500 mA cap.

How to get / verify a real contract:

```bash
# Type-C / PD state
cat /sys/class/typec/port0/power_operation_mode      # default | 1.5A | 3.0A | usb_pd
ls  /sys/class/typec/port0/                          # look for port0-partner (a directory = partner detected)
cat /sys/class/typec/port0/port0-partner/usb_power_delivery/ -R 2>/dev/null

# PMIC / charger input side (Qualcomm SMB / QCOM PMIC power supply)
grep -H . /sys/class/power_supply/*/{online,type,input_current_limit,input_current_max,current_max,voltage_now} 2>/dev/null

# Kernel view of the Type-C / PD stack and any current-limit messages
journalctl -k -b | grep -iE 'typec|tcpm|pd_?contract|ucsi|usb_vbus|vbus|current limit|over-?current'
```

- To *force* a proper contract on USB-C: use a cable and source that actually implement
  Type-C current advertisement or PD, connected **directly to the board's USB-C port** (no
  hub). After plugging in, `power_operation_mode` should move to `3.0A` or `usb_pd` and a
  `port0-partner` should appear.
- To make the contract irrelevant: **power via VIN**. The buck feeds 5V_SYS regardless of
  anything on the CC pins.

Unverified: the exact `power_supply` node names and whether `input_current_limit` is writable
on this PMIC (not documented by Arduino — see open list).

---

## Q3 — Watchdog / brown-out detector: cause or cure for the reboots?

- **No Linux/SoC hardware watchdog is documented by Arduino** for the UNO Q. The power spec,
  datasheet extract, user manual and Debian guide contain no mention of a watchdog timer,
  `/dev/watchdog`, or `systemd` `WatchdogSec` guidance
  ([debian guide](https://docs.arduino.cc/tutorials/uno-q/debian-guide/),
  [power spec](https://docs.arduino.cc/tutorials/uno-q/power-specification/)). So a watchdog is
  **not** what is rebooting you, and there is no documented knob to disable one. (The QRB2210
  almost certainly has an internal PMIC/PS-HOLD watchdog, but Arduino exposes no interface or
  config for it — treat as unverified.)
- **No brown-out detector spec either.** Arduino describes reset risk only qualitatively:
  *"Brief dips can cause resets or link drops"* and *"voltage hang may cause resets"*
  ([power spec](https://docs.arduino.cc/tutorials/uno-q/power-specification/)). There is no
  published BOR threshold for the 5V_SYS / 3.3 V rails and no way to raise/lower it.
- The **STM32U585 MCU** has its own BOR and independent/window watchdogs (IWDG/WWDG,
  [ST datasheet](https://www.st.com/resource/en/datasheet/stm32u585ai.pdf),
  [stm32duino IWatchdog](https://github.com/stm32duino/Arduino_Core_STM32/blob/main/libraries/IWatchdog/README.md)).
  Those protect the reflex firmware only; an MCU BOR/watchdog reset does **not** reboot Linux,
  and the observed event is a full Linux + Docker restart, so the MCU watchdog is not involved.
  It is still worth enabling IWDG in the MCU firmware so the reflex layer self-recovers if the
  rail dips below the STM32's BOR but the SoC survives.
- Practical mitigation on the Linux side, since there is no board watchdog to rely on:
  - `Arduino App Lab` already runs on boot and the app container restarts automatically
    (your observed `RestartCount=0` recovery)
    ([single-board-computer](https://docs.arduino.cc/tutorials/uno-q/single-board-computer/)).
  - Add process supervision + alerting with **Monit** (Arduino's own hardening guide
    recommends it, with SMTP alerts and a dashboard on an SSH tunnel)
    ([security hardening guide](https://docs.arduino.cc/tutorials/uno-q/security-hardening-guide/)).
  - Consider enabling the kernel software watchdog (`systemd` `RuntimeWatchdogSec=` in
    `/etc/systemd/system.conf`) *only if* `/dev/watchdog` exists on your image — unverified,
    check with `ls -l /dev/watchdog*`.

Bottom line: the reboots are the rail collapsing, not a timer firing. Fix the rail (Q1/Q4).

---

## Q4 — Powering peripherals so they don't load the SoC rail

- The header **5 V pins are `5V_USB_VBUS` pass-through** from the input path and the VBUS
  back-drive switch — the *same* rail the SoC runs on, shared with on-board loads. Arduino says
  plan peripherals "within the same rail budget" and that available current "depends on the
  input source, the regulators and the board's own consumption at the time"
  ([power spec](https://docs.arduino.cc/tutorials/uno-q/power-specification/)). Do **not** hang
  a camera, USB-Ethernet, or an LED/IR driver off these.
- **Camera + USB devices:** put them on a **self-powered USB hub** with its own 5 V/3 A supply.
  This is mandatory if you power the board via VIN (VBUS output is then disabled), and strongly
  advisable even on USB-C so peripheral inrush never reaches the board rail
  ([VIN/USB thread](https://forum.arduino.cc/t/uno-q-whats-the-final-word-on-powering-via-vin-and-connecting-usb-devices-to-usb-c-port-with-a-hub/1447175),
  [USB-power-disabled thread](https://forum.arduino.cc/t/uno-q-usb-power-disabled-if-using-vin-power-pin/1411831)).
- **USB host mode when powering via VIN:** older OS images (pre–Nov 2025, no `/etc/buildinfo`)
  boot the USB controller in *device* mode if no USB-C cable is present at power-on, so a hub
  plugged in later is ignored. Workaround is a `systemd` unit that writes `host` to
  `/sys/kernel/debug/usb/4e00000.usb/mode` before Docker starts
  ([arduino-uno-q-usb-fix](https://github.com/Psalmustrack/arduino-uno-q-usb-fix)). Check your
  image: `cat /etc/buildinfo` — if present, Arduino has already fixed this upstream; updating
  is preferred but wipes the board.
- **Actuators / IR / high-power LEDs:** drive from their own supply, switched by a MOSFET/relay
  referenced to a shared ground. Bring only the logic/gate signal back to the board (3.3 V
  Maker I/O on JDIGITAL/JANALOG; 1.8 V on processor headers — never cross 3.3 V into a 1.8 V
  bank; abs-max 3.6 V / 2.1 V respectively)
  ([power spec](https://docs.arduino.cc/tutorials/uno-q/power-specification/)).
- Use several nearby **GND header pins** for the return path of any load current to cut
  IR-drop and noise ([power spec](https://docs.arduino.cc/tutorials/uno-q/power-specification/)).
- QWIIC / 3.3 V sensors on `PWR_3P3V` are fine for small loads; still budget for drop and add
  local decoupling on a carrier ([power spec](https://docs.arduino.cc/tutorials/uno-q/power-specification/)).

---

## Q5 — RTC / clock behaviour across reboot

- The PM4125 PMIC contains the real-time clock. Its backup rail is **`VCOIN`**, which
  *"powers only the real-time clock of the PMIC and does not power the Linux or MCU domains"*
  ([datasheet](https://docs.arduino.cc/resources/datasheets/ABX00162-ABX00173-datasheet.pdf)).
  `VBAT` is a *separate* pin tied to `PWR_3P8V`, "reserved for system design and future
  features" — not an RTC backup
  ([power spec](https://docs.arduino.cc/tutorials/uno-q/power-specification/)).
- The board tour in the user manual lists **no coin-cell holder and no battery connector**
  ([user manual](https://docs.arduino.cc/tutorials/uno-q/user-manual/)). So on a stock UNO Q
  `VCOIN` is effectively unpopulated: **once 5V_SYS actually collapses, the PMIC RTC loses
  time.** Arduino provides no timezone/NTP setup page; time comes back only after Wi-Fi + NTP
  resync ([debian guide](https://docs.arduino.cc/tutorials/uno-q/debian-guide/) — states there
  is *zero* RTC/NTP/timezone documentation).
- Implication for your symptom: the wall-clock jump on each crash is another sign the event is
  a **rail collapse deep enough to reset the PMIC**, not a clean SoC-only panic (a pure
  software reboot with 5V_SYS held would keep RTC time). Fixing the rail should also stop the
  clock jumps. Until then: run `systemd-timesyncd`/`chrony` and force an NTP sync at boot
  before any timestamped logging; if the deployment site has no reliable network, add an
  external I²C RTC (DS3231) on QWIIC and seed the system clock from it in a boot service —
  unverified that Arduino's image bundles `hwclock` wiring for this, treat as a custom add.

---

## Q6 — Headless / unattended operation

### Recommended field power for headless SBC use

Arduino's SBC guide states the external supply must provide **"at least +5 VDC at 3 A to
reliably power the dongle, the connected devices, and the UNO Q"**, and that **the UNO Q cannot
power the USB-C dongle itself** — power goes into the dongle/hub, which then powers the board
([single-board-computer](https://docs.arduino.cc/tutorials/uno-q/single-board-computer/)). For a
sealed field box prefer VIN + a quality DC supply (Q1) and a separately-powered hub for USB
peripherals (Q4). Use the **4 GB** RAM variant for headless
([single-board-computer](https://docs.arduino.cc/tutorials/uno-q/single-board-computer/)).

### Boot / auto-start

- Board **boots automatically on power** — no button press
  ([user manual](https://docs.arduino.cc/tutorials/uno-q/user-manual/)). Boot ~34.6 s
  ([Tom's Hardware](https://www.tomshardware.com/raspberry-pi/arduino-uno-q-review)).
- Arduino App Lab always runs on boot and auto-updates board + dependencies
  ([single-board-computer](https://docs.arduino.cc/tutorials/uno-q/single-board-computer/)).
- Set your app to launch at boot: in App Lab, dropdown next to Run → "Run at startup"; or CLI:
  ```bash
  arduino-app-cli properties set default user:<YOUR_APP_NAME>
  arduino-app-cli app list
  arduino-app-cli app start user:<YOUR_APP_NAME>
  arduino-app-cli app stop  user:<YOUR_APP_NAME>
  ```
  A built-in *Example* cannot be the startup app — copy it to a user app first
  ([user manual](https://docs.arduino.cc/tutorials/uno-q/user-manual/)).

### SSH

- Enabled automatically when Wi-Fi is set during first setup; otherwise via `adb`:
  `arduino-app-cli system network-mode enable`
  ([ssh](https://docs.arduino.cc/tutorials/uno-q/ssh/)).
- Default user **`arduino`**, password set at first setup. Connect `ssh arduino@<boardname>.local`
  (mDNS) or `ssh arduino@<ip>`. Find the IP with `hostname -I` over `adb shell`, or
  `arduino-cli board list`. `scp` / `scp -rp` work for file/folder transfer. On a re-flash with
  a reused IP, clear the stale key: `ssh-keygen -R <ip>`
  ([ssh](https://docs.arduino.cc/tutorials/uno-q/ssh/)).

### ADB

- USB-only. Install platform-tools (`winget install Google.PlatformTools` /
  `brew install android-platform-tools` / `apt-get install android-sdk-platform-tools`),
  then `adb devices` (can take ~1 min) → `adb shell`, password `arduino` if prompted
  ([adb](https://docs.arduino.cc/tutorials/uno-q/adb/)). Not useful for a remote field box
  (no physical USB host on site) — use it only for bring-up.

### Remote access (for a deployed box)

Arduino documents three methods
([remote access](https://docs.arduino.cc/tutorials/uno-q/remote-access/)):

| Method | Use |
|---|---|
| **Tailscale + SSH** | Best for field: VPN, SSH to the board's Tailscale IP from anywhere, no port-forwarding |
| **xrdp** | Graphical desktop over LAN / ADB port-forward / Tailscale; private D-Bus fix for black screen |
| **RustDesk** | Graphical, needs a dummy display driver + LightDM auto-login for headless |

Arduino Cloud connectivity is Python on the MPU via the Arduino Cloud Brick (needs
`DEVICE_ID` + `SECRET_KEY` from the Cloud wizard); Arduino's tutorial does **not** cover OTA,
reconnection, or keep-alive for unattended use
([arduino cloud](https://docs.arduino.cc/tutorials/uno-q/arduino-cloud/)).

### Hardening for an unattended deployment

From Arduino's [security hardening guide](https://docs.arduino.cc/tutorials/uno-q/security-hardening-guide/):

- Strong ≥12-char password for `arduino`; never reuse.
- `arduino-app-cli system update` regularly (signed, TLS).
- **Disable ADB** in production: `sudo systemctl stop adbd && sudo systemctl disable adbd`.
- Keep **SSH off by default**; enable only when needed, or expose it only through a Tailscale
  tunnel; firewall other ports (`iptables -A INPUT -p tcp --dport <n> -j DROP`).
- If the app serves a WebUI, force HTTPS (WebUI Brick auto-generates a self-signed cert; or
  supply your own in `certs/`).
- Encrypt secrets at rest: `ecryptfs-setup-private` → `~/Private` (note: under `adb shell` you
  must `sudo su -l arduino` to mount it; automatic over SSH).
- Central logging: forward `rsyslog` to a remote collector with disk-queue buffering so a crash
  doesn't lose the last lines before the drop.
- Install **Monit** for process monitoring + auto-restart + email alerts; reach its dashboard
  on port 2812 over an SSH tunnel.
- Audit logins/reboots with `last` (reads `/var/log/wtmp`) — useful to timestamp each
  crash-reboot.

### Clean shutdown vs. power loss

- `sudo shutdown now` / `sudo poweroff` on this board **reboots instead of powering off**; use
  **`sudo halt`**, wait for the LED to go out, then cut power
  ([shutdown thread](https://forum.arduino.cc/t/arduino-uno-q-shutdown/1418430)).
- Whether abrupt power removal is officially safe is **unanswered by Arduino** — a user asked
  for an official statement and got none
  ([abrupt-power thread](https://forum.arduino.cc/t/uno-q-is-abrupt-power-removal-officially-supported-or-is-clean-shutdown-required/1444069),
  page was CAPTCHA-gated at research time). For field use assume the eMMC can be corrupted by a
  hard drop: mount data partitions with journaling, keep the rootfs effectively read-only where
  possible, and `fsync` your own state files. The long-press power button (≥5 s) triggers a
  Linux reboot, not a clean shutdown
  ([user manual](https://docs.arduino.cc/tutorials/uno-q/user-manual/)).

---

## Debugging the next crash

1. `journalctl -k -b -1 --no-pager | tail -n 200` right after recovery — confirm the log just
   *stops* (rail collapse) rather than showing a panic/OOM/thermal trace.
2. `last -x | head` — timestamps of every reboot / runlevel change.
3. Log a rail proxy over time: cron `grep . /sys/class/power_supply/*/voltage_now
   /sys/class/typec/port0/power_operation_mode` into a file every 5 s; correlate a dip with the
   drop.
4. `journalctl -k -b | grep -iE 'thermal|throttl|hot'` — rule out thermal (ambient limit is
   60 °C air temperature, and near the limit "available output current" is reduced
   ([power spec](https://docs.arduino.cc/tutorials/uno-q/power-specification/))).
5. Swap in VIN power (or a direct 5 V/3 A supply, no hub) and see if the MTBF changes — this is
   the decisive test.

---

## Unverified / open

- **Whether the UNO Q firmware/PMIC actually enforces any input-current limit** when
  `power_operation_mode: default` (no partner). Evidence (idle draw > 500 mA, runs for hours)
  says it does not hard-limit, but Arduino publishes no statement and the PMIC
  `input_current_limit` sysfs behaviour is undocumented.
- **Exact `/sys/class/power_supply/*` node names** on the shipped image and whether
  `input_current_limit` / `current_max` are writable.
- **Any SoC/PMIC hardware watchdog** exposed to Linux (`/dev/watchdog`), and whether the stock
  `systemd` is configured with `RuntimeWatchdogSec`. Not documented; check on the device.
- **Published boot / peak inrush current** and the BOR threshold for 5V_SYS / 3.3 V. Not in any
  Arduino document found.
- **PMIC part number**: power-spec page and datasheet say **PM4125**; the user manual text says
  **PM4145** (also seen as "PM4125"). Likely a doc typo; the RTC-backup pin is `VCOIN` either
  way.
- **Whether a stock UNO Q has any `VCOIN` cell fitted.** Board tour shows no holder; assumed
  unpopulated → RTC does not survive full power loss. Not explicitly confirmed by Arduino.
- **Official position on abrupt power loss / eMMC safety.** Asked on the forum, unanswered.
- **element14 road-test** "Arduino UNO Q and USB3 adapter with USB-C PD" — relevant title, but
  the page would not render for extraction (Akamai/anti-bot). Worth a manual read:
  https://community.element14.com/products/roadtest/b/blog/posts/arduino-uno-q-and-usb3-adapter-with-usb-c-pd-87477727
- **The `power-specification` page** is JavaScript-rendered and returned empty on direct fetch;
  content above was extracted via a reader proxy and cross-checked against the datasheet PDF and
  forum threads. Re-read the live page to confirm exact wording before quoting externally:
  https://docs.arduino.cc/tutorials/uno-q/power-specification/
- **Zephyr board page** (https://docs.zephyrproject.org/latest/boards/arduino/uno_q/doc/index.html)
  not reviewed — may document MCU-side watchdog/BOR fuses if the reflex firmware moves to Zephyr.

---

## Source list

- Arduino UNO Q — Power Specifications: https://docs.arduino.cc/tutorials/uno-q/power-specification/
- Arduino UNO Q — hardware / product page: https://docs.arduino.cc/hardware/uno-q/
- Arduino UNO Q — User Manual: https://docs.arduino.cc/tutorials/uno-q/user-manual/
- Arduino UNO Q — Single-Board Computer: https://docs.arduino.cc/tutorials/uno-q/single-board-computer/
- Arduino UNO Q — SSH: https://docs.arduino.cc/tutorials/uno-q/ssh/
- Arduino UNO Q — ADB: https://docs.arduino.cc/tutorials/uno-q/adb/
- Arduino UNO Q — Remote Access: https://docs.arduino.cc/tutorials/uno-q/remote-access/
- Arduino UNO Q — Security Hardening Guide: https://docs.arduino.cc/tutorials/uno-q/security-hardening-guide/
- Arduino UNO Q — Debian Guide: https://docs.arduino.cc/tutorials/uno-q/debian-guide/
- Arduino UNO Q — Arduino Cloud: https://docs.arduino.cc/tutorials/uno-q/arduino-cloud/
- Arduino UNO Q datasheet (ABX00162 / ABX00173): https://docs.arduino.cc/resources/datasheets/ABX00162-ABX00173-datasheet.pdf
- Arduino UNO Q schematics: https://docs.arduino.cc/resources/schematics/ABX00162-schematics.pdf
- Forum — "Uno-q keeps rebooting. power brownout?": https://forum.arduino.cc/t/uno-q-keeps-rebooting-power-brownout/1438230
- Forum — "Boot fail - any reason for this": https://forum.arduino.cc/t/boot-fail-any-reason-for-this/1443623
- Forum — "final word on powering via VIN + USB devices via hub": https://forum.arduino.cc/t/uno-q-whats-the-final-word-on-powering-via-vin-and-connecting-usb-devices-to-usb-c-port-with-a-hub/1447175
- Forum — "USB Power disabled, if using VIN Power pin": https://forum.arduino.cc/t/uno-q-usb-power-disabled-if-using-vin-power-pin/1411831
- Forum — "Recommended USB-C hub and Power Supply for Arduino UNO Q": https://forum.arduino.cc/t/recommended-usb-c-hub-and-power-supply-for-arduino-uno-q/1421294
- Forum — "Arduino Uno Q shutdown": https://forum.arduino.cc/t/arduino-uno-q-shutdown/1418430
- Forum — "Is abrupt power removal officially supported": https://forum.arduino.cc/t/uno-q-is-abrupt-power-removal-officially-supported-or-is-clean-shutdown-required/1444069
- Forum — "Uno Q dead. Please help": https://forum.arduino.cc/t/uno-q-dead-please-help/1447017
- edaboard — "Powering the Arduino Uno Q (SBC) via USB-C vs VIN – 24/7 nodes": https://www.edaboard.com/threads/powering-the-arduino-uno-q-sbc-via-usb-c-vs-vin-%E2%80%93-stability-for-24-7-nodes.417491/
- GitHub — Psalmustrack/arduino-uno-q-usb-fix: https://github.com/Psalmustrack/arduino-uno-q-usb-fix
- Tom's Hardware — Arduino Uno Q review (power/thermal measurements): https://www.tomshardware.com/raspberry-pi/arduino-uno-q-review
- etechnophiles — UNO Q pinout guide (note: calls VIN a "barrel jack" — incorrect): https://www.etechnophiles.com/arduino-uno-q-pinout-guide/
- ST — STM32U585 datasheet (MCU BOR / IWDG / WWDG): https://www.st.com/resource/en/datasheet/stm32u585ai.pdf
- stm32duino — IWatchdog library: https://github.com/stm32duino/Arduino_Core_STM32/blob/main/libraries/IWatchdog/README.md
