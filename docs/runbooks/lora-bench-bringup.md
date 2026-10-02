# Runbook: LoRa bench bring-up (UNO Q + Grove LoRa-E5 + SenseCAP M2 + ChirpStack)

**Purpose.** A step-by-step path from a factory-fresh Arduino UNO Q, a Grove LoRa-E5 and a boxed
SenseCAP M2 gateway to a real LoRaWAN OTAA join and uplink on India's IN865 band, landing in a
local ChirpStack. Written 2026-10-01 while doing it for the first time on a second, bench-only
UNO Q (2 GB). Each step says what was actually observed.

**Status of each part (2026-10-01):**

| Part | State |
|---|---|
| UNO Q factory setup, update, app flashed | Done |
| Gateway on IN865, Packet Forwarder to the laptop | Done (settings saved) |
| ChirpStack running on the laptop | Done (`docker compose up -d`) |
| Gateway registered and online in ChirpStack | Done (stats arriving on `in865`) |
| Device profile + device registered | Profile and application done; device pending |
| E5 wired, OTAA join, first uplink | Wired; JoinRequests reach ChirpStack (device not yet registered) |

Related: `docs/research/sensecap_gateway_in865_chirpstack_setup.md` (August research pass),
ADR 0029 (USART1 shared between DFPlayer and LoRa-E5), `hardware/PIN_MAP.md`,
`docs/runbooks/mcu-flash-uno-q.md`.

---

## Part 1 — Factory UNO Q: first access, network, SSH

A factory UNO Q ships with SSH disabled, no SSH host keys and the `arduino` user's password
expired. The only way in is ADB over the USB-C cable.

1. **ADB.** Use the Android SDK platform-tools `adb` (on this laptop:
   `C:\Users\<user>\AppData\Local\Android\Sdk\platform-tools\adb.exe`; it is not on `PATH`).
   `adb devices` should list the board by serial.
2. **Set a password first**, before any long job: `adb shell`, then `passwd`. If ADB is the only
   way in and USB drops mid-job, the board is unreachable until a power cycle.
3. **Wi-Fi.** `nmcli` from an ADB shell. From Windows, two traps:
   - PowerShell 5.1 strips embedded double quotes from native-exe arguments, so SSIDs with
     spaces break. Push a small script and run it instead.
   - Piping stdin through `adb shell` does not work from Windows. Put the PSK in a temp file,
     push it, use it, delete it.
   - Git Bash rewrites `/tmp/...` into a Windows path on `adb push`; set `MSYS_NO_PATHCONV=1`.
   - A stale NetworkManager profile gives "key-mgmt property is missing". Delete old wireless
     profiles and create a fresh one with `wifi-sec.key-mgmt wpa-psk`.
   - Only 2.4 GHz networks were visible to the board.
4. **SSH.** `sshd` fails until host keys exist:
   `sudo dpkg-reconfigure openssh-server`, then enable and start `ssh`. Install your public key
   in `~/.ssh/authorized_keys` and verify the host fingerprint on first connect.
5. **Hostname.** `sudo hostnamectl set-hostname <name>` so the bench board is never confused
   with a deployed one.

From here on, use `ssh arduino@<board-ip>` rather than ADB.

## Part 2 — Update the Arduino stack

1. Run the Arduino-only update (much smaller than a full Debian upgrade):
   ```
   nohup arduino-app-cli system update --only-arduino --yes > ~/arduino-update.log 2>&1 &
   ```
   On the bench board this took 8 packages from factory to: `arduino-app-cli` 0.13.0,
   `arduino-app-lab` 0.10.0, `arduino-cli` 1.5.1, `arduino-router` 0.10.0, plus `adbd` and
   `android-lib*`. About 258 MB over 2.4 GHz Wi-Fi; allow most of an hour.
2. **The log ends in `signal: killed` / `Error running upgrade command`, followed by
   `Upgrade completed successfully`.** The packages were installed (`dpkg -l` shows the new
   versions, `dpkg --audit` is clean). What did *not* happen is the service restart.
3. **Restart the services yourself** — otherwise the old daemon keeps running from memory:
   ```
   sudo systemctl restart arduino-router arduino-app-cli
   arduino-app-cli version        # both lines must show the new version
   ```
   Symptom if skipped: `arduino-app-cli version` reports `daemon version: 0.6.6`, and the
   sketch build pulls `Arduino_RouterBridge` 0.2.2 and fails with
   `#error "Please update the Arduino_RouterBridge library..."` and
   `'Serial' was not declared in this scope`. After the restart the same unchanged sketch
   resolves `Arduino_RouterBridge` 0.4.3 and builds. Do not pin RouterBridge in `sketch.yaml`.

## Part 3 — Put the app on the board and flash the MCU

1. The app lives at `~/ArduinoApps/eletect-x/` with `app.yaml`, `sketch/` and `python/`.
   `sketch/secrets.h` holds the LoRaWAN keys: keep it `chmod 600` and out of git.
2. Build, flash and start in one step:
   ```
   arduino-app-cli app start user:eletect-x      # first time
   arduino-app-cli app restart user:eletect-x    # afterwards
   ```
   Success looks like `Sketch uses ... bytes`, OpenOCD's `flash size = 2048 KiB`, then
   `Progress[sketch updated]`. The Python side then pulls its container image.
3. If Wi-Fi drops during the image pull, the step fails with
   `Client.Timeout exceeded while awaiting headers` / `Exit Status 18`. The MCU is already
   flashed at that point; rerun the same command and downloaded layers are reused.
4. Flashing before the radio is wired is harmless: the firmware's AT probe times out, backs off
   and retries.

## Part 4 — Wire the Grove LoRa-E5

In the deployed node the E5 shares USART1 with the DFPlayer PRO through a 74HC4053, with D4 as
the select line (HIGH = LoRa), per ADR 0029. A bench board with no DFPlayer can wire the E5
straight to D0/D1; the firmware still drives D4 HIGH, with nothing attached.

**Power the board off before wiring. Fit the E5's antenna before it is ever powered.**

| Grove wire | E5 signal | UNO Q pin |
|---|---|---|
| Yellow | E5 TX | D0 (PB7, USART1 RX) |
| White | E5 RX | D1 (PB6, USART1 TX) |
| Red | VCC | 5V |
| Black | GND | GND |

- **Supply:** the Grove E5 accepts 3.3–5 V and regulates on board. 5 V matches `PIN_MAP.md` and
  keeps the E5's transmit current off the UNO Q 3.3 V rail.
- **Logic:** the E5's UART is 3.3 V even on a 5 V supply, and D0/D1 are 3.3 V pins (the
  datasheet's non-5 V-tolerant exceptions are A0, A1 and D3), so no level shifting is needed
  on the direct bench wiring.
- **Grove colours:** the Grove UART pin order is named from the host's side, so the yellow wire
  carries the module's TX. If the AT probe never gets `+AT: OK`, swap yellow and white first;
  it is the most common fault in forum threads. Also check the silkscreen on the E5 board.
- **Bench caveat:** without the 4053, any DFPlayer command the firmware sends (115200 baud)
  reaches the E5 as noise. Harmless, but avoid triggering deterrence during a LoRa test.

What the firmware does on its own (`device/mcu/src/mac.cpp`), at 9600 baud with `\r\n` line
endings: `AT` → `+AT: OK`; `AT+ID=DevEui`; `AT+MODE=LWOTAA`; `AT+DR=IN865`;
`AT+ID=AppEui,"..."`; `AT+KEY=APPKEY,"..."`; `AT+PORT=10`; `AT+JOIN` → `+JOIN: Done` or
`Join failed` (backoff and retry). After a join it queues a status uplink on FPort 10, then
repeats every 10 minutes.

**DevEUI comes from the module.** The firmware reads the E5's factory DevEUI and never sets
it, so each physical E5 has its own. AppEUI (JoinEUI) and AppKey come from `secrets.h`.

## Part 5 — SenseCAP M2 gateway: region and forwarding

The unit is a SenseCAP M2 Multi-Platform, model `M2-EU868-4G` (OpenWrt/LuCI console).

1. **Antenna on before power.** Connect Ethernet to the same router as the laptop.
2. **Find the console.** The configuration hotspot (`SenseCAP_XXXXXX`, button held 5 s) did not
   appear once Ethernet was up. Instead, find the gateway on the LAN: its MAC starts with
   `2C:F7:F1` (Seeed). A ping sweep plus `arp -a` found it; open `http://<gateway-ip>/`.
3. **Log in** with the username/password on the gateway's label.
4. The status page shows Model and **EUI** — note the EUI, ChirpStack needs it.
5. **LoRa → Channel Plan:** Region **IN865-867**, Frequency plan **India 865-867 MHz** →
   **Save & Apply**.
   *This closes the open question from the August research pass:* the EU868 SKU does offer
   IN865 as a selectable region. 868 MHz must not be used in India.
6. **LoRa → LoRa Network:**
   - Mode: **Packet Forwarder** (not SenseCAP, which sends to Seeed's cloud; not Basics
     Station; not Local Network Server).
   - Gateway EUI: auto-filled, leave it.
   - Server Address: the laptop's LAN IP (type it into the combo box; it defaults to
     `eu1.cloud.thethings.network`).
   - Server Port (Up) / (Down): **1700** / **1700**.
   - Leave Intervals, Beacon, GPS, Forward Rules and Packet Filter at defaults.
   - **Save & Apply**.

If the laptop's IP changes, update Server Address. To go back to Seeed's cloud, set Mode to
SenseCAP.

## Part 6 — ChirpStack on the laptop

The stack is the sibling repo `chirpstack-stack` (ChirpStack v4 docker-compose), already set to
IN865: `in865` is in `enabled_regions`, and the UDP gateway bridge publishes on the `in865/...`
topic prefix.

1. Start Docker Desktop, then in `chirpstack-stack`:
   ```
   docker compose up -d
   ```
   Mosquitto has no host port on purpose: it allows anonymous clients, so only the
   containers on the compose network reach it. To publish a test message:
   `docker compose exec mosquitto mosquitto_pub -t ... -m ...`. ChirpStack publishes
   application events at QoS 1 and Mosquitto persists its queue, so uplinks wait for the
   ingest bridge while it is restarting.
2. The gateway sends UDP to port 1700 on the laptop. Docker Desktop's firewall rule covered the
   network profile in use here; if the gateway never shows online, check Windows Firewall for
   inbound UDP 1700.
3. UI at `http://localhost:8080`. Default login `admin` / `admin` — change it.
4. **Gateways → Add gateway:** a name and the Gateway ID (the EUI from Part 5) — type it, do
   not press the regenerate button, which invents a random EUI. Stats interval stays 30.
   **Downlink priority must be at least 1**: the form pre-fills 0 and ChirpStack v4.19 rejects
   it with `downlink_priority must be > 0`. Within about a minute the gateway should show
   Online with a recent "Last seen". The gateway's 30-second stats can be seen arriving before
   it is even registered:
   ```
   docker compose logs -f chirpstack-gateway-bridge
   ```
5. **Tenant → Device Profiles → Add** (not the one under Network Server, which in v4.19 is the vendor device repository and only offers "Add vendor"): region IN865, MAC version **LoRaWAN 1.0.3**, regional parameters
   revision **A**, OTAA supported, Class A, default ADR algorithm, **no codec** (`web/ingest`
   decodes FPort 10 itself, ADR 0031).
6. **Applications → Add application → Add device:**
   - DevEUI: the E5's own (label/QR on the module). If it can't be read, power the node up and
     look for the JoinRequest under the gateway's **LoRaWAN frames** tab, which shows it.
   - JoinEUI: `LORA_APP_EUI` from `secrets.h`.
   - Then the device's **OTAA keys** tab: AppKey = `LORA_APP_KEY` from `secrets.h`.

## Part 7 — Join and first uplink

1. Power the board off, wire the E5 (Part 4), power on. **Then start the app**
   (`arduino-app-cli app start user:eletect-x`): unless the app is the board's default, the MCU
   sketch does not run after a power cycle, the router reports `method ... not available`, and
   nothing is sent over the air.
2. Node side: `arduino-app-cli app logs user:eletect-x` should show the AT probe answered,
   then `+JOIN: Done`.
3. ChirpStack: JoinRequest → JoinAccept in the gateway's LoRaWAN frames, device shows
   Activated, then an uplink on FPort 10.
4. End to end: the `eletect-ingest` service in `chirpstack-stack` (started by the
   `docker compose up -d` in Part 6) carries uplinks into Supabase. Watch for the node:
   ```
   docker compose logs -f eletect-ingest
   ```
   A status frame logs a `health` row every 10 minutes; an event frame logs its species and
   priority. A `high` or `critical` event pages real people on the project `web/ingest/.env`
   points at - test with boar (`normal`) unless an alert is the point.
5. Name and place the node: Fleet → click the node → **Name and location** (admin only). Until
   it has coordinates it is on no map and no resident within 3 km is matched to it.

## Troubleshooting quick list

| Symptom | Likely cause |
|---|---|
| No `+AT: OK` | TX/RX swapped, no common GND, or E5 not powered |
| `+JOIN: Join failed` repeatedly | DevEUI/AppKey mismatch in ChirpStack, gateway not online, or wrong region |
| Uplinks in ChirpStack but no rows in Supabase | `docker compose logs eletect-ingest`: retries mean Supabase is unreachable or paused; nothing at all means the service is down |
| Gateway never online in ChirpStack | Wrong Server Address, laptop IP changed, UDP 1700 blocked, Docker not running |
| Build `#error ... Arduino_RouterBridge` | Old app-cli daemon still running — restart services (Part 2) |
| `Exit Status 18` during app start | Network dropped during image pull — rerun |
| Board drops off USB but answers ping | Power-cycle before assuming a reflash is needed |
