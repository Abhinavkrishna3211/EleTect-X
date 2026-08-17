# SenseCAP M2 gateway: EU868 → IN865 + ChirpStack setup guide

- **Status:** research complete, hardware verification still needed
- **Date:** 2026-08-16
- **Author's note:** written from Seeed's official wiki/docs and two independent real-world
  IN865-in-India deployment write-ups (cited below), not from memory. One material gap remains
  open and is flagged clearly in §4 — do not skip it.

This closes the research portion of the open item in `HANDOVER.md` ("SenseCAP gateway is still
labeled EU868, must be set to IN865 region profile in ChirpStack and join-tested before any real
transmission") and the matching follow-up in ADR 0002 §Consequences. It does not close the item
outright — the actual gateway hasn't been touched yet, and §4 below is a real open question that
can only be resolved with the physical unit in hand.

## 1. Accessing the gateway's local console

Source: [Quick Start | Seeed Studio Wiki](https://wiki.seeedstudio.com/quick_start_with_M2_MP/),
confirmed by the official PDF
([Quick Start for SenseCAP M2 Gateway & Sensors](https://files.seeedstudio.com/products/SenseCAP/M2_Multi-Platform_Gateway/Quick%20Start%20for%20SenseCAP%20M2%20Gateway%20&%20Sensors.pdf)).

1. Power on: connect antenna + power adapter. Power LED is red at first, then the top indicator
   flashes green after ~15s once booted.
2. Enter configuration mode: press the physical button for 5 seconds until the blue indicator
   **flashes slowly**.
3. On your laptop/phone, join the Wi-Fi hotspot named **`SenseCAP_XXXXXX`** (XXXXXX = last 6
   hex digits of the device's MAC), password **`12345678`**.
4. Browse to **`192.168.168.1`**.
5. Log in with the username/password printed on the device's physical label (not a fixed
   default — check the label itself).

Alternative: connect the gateway to your router via Ethernet, find its DHCP-assigned IP on the
router's admin page, and browse to that IP instead of using the AP-hotspot method.

Gateway EUI: neither the Quick Start guide nor the Overview page states where it's displayed in
the local console UI. In practice it is almost always shown on the device's physical label and/or
under the same status/network page as the MAC address — confirm this once you're in the console;
you need it for step 2 of §3 below.

## 2. Setting the region/frequency plan to IN865

Source: [SenseCAP M2 MP Gateway LNS Configuration](https://wiki.seeedstudio.com/Network/SenseCAP_Network/SenseCAP_M2_Multi_Platform/SenseCAP_M2_MP_Gateway_LNS_Configuration/) and the
[ChirpStack tutorial](https://wiki.seeedstudio.com/Network/SenseCAP_Network/SenseCAP_M2_Multi_Platform/Tutorial/Connect-M2-Multi-Platform-Gateway-to-ChirpStack/) (both agree on this menu path).

1. In the local console, go to **`LoRa` → `Channel Plan`**.
2. "Select the Region and Frequency plan" (exact dropdown wording per the wiki) — pick the
   IN865 entry.
3. Click **`Save&Apply`**.

This is the one step ADR 0002 flags as required before any real transmission (868 MHz is illegal
to operate in India). **See §4 — whether IN865 actually appears in this dropdown on your specific
unit is not yet confirmed.**

## 3. Registering the gateway with ChirpStack

Source: [Connect M2 Multi-Platform Gateway to ChirpStack](https://wiki.seeedstudio.com/Network/SenseCAP_Network/SenseCAP_M2_Multi_Platform/Tutorial/Connect-M2-Multi-Platform-Gateway-to-ChirpStack/).

**On the ChirpStack side:**
1. Log into the ChirpStack web UI (default `admin`/`admin` if freshly installed — change this
   before going live).
2. **Gateways → Add gateway**: give it a name, enter the **Gateway EUI** (from the device label
   or local console, per §1).
3. **Device profile → Add device profile**: set Region to match IN865, **MAC version:
   LoRaWAN 1.0.3**, **Regional parameters revision: A**, **ADR algorithm: Default ADR algorithm
   (LoRa only)**.
4. **Application → Add Application** → Devices tab → **Add device**: enter device Name and
   **Device EUI** (from the device label or the SenseCAP Mate app), assign the device profile
   from step 3.

**On the gateway side**, in the local console:
1. Go to **`LoRa` → `LoRa Network`**.
2. Set **Mode: Packet Forward**.
3. **Gateway EUI** auto-populates.
4. **Server Address**: your ChirpStack server's address (LAN IP or hostname reachable from the
   gateway).
5. **Server Port (Up/Down): 1700** (standard Semtech UDP packet-forwarder port).
6. Click **`Save&Apply`**.

Note: the wiki's LNS-configuration page also documents a separate **`Mode: Local Network
Server`** option (MQTT broker fields — Broker Host/Port/User/Password) that runs a *local*
ChirpStack instance directly on the gateway itself. That's a different deployment model from
"gateway → Packet Forward → your own external ChirpStack server," which is what ADR 0002 already
specifies (§4/§5 of the ADR: "gateway is SenseCAP SX1302, region IN865, → ChirpStack" as a
separate LNS, not on-gateway). Use **Packet Forward mode** (steps above), not Local Network Server
mode, unless the architecture decision changes.

## 4. Open risk — not yet confirmed: does IN865 actually appear as a channel-plan option?

This is the one piece of real, previously-unflagged uncertainty this research surfaced, and it's
worth stating plainly rather than assuming the happy path:

- Seeed sells the SenseCAP M2 as **separate regional SKUs** — the product listing page shows
  a "Region" selector with **AU915, US915, AS923, AS923(Japan), EU868** as the purchasable
  variants ([Seeed product page](https://www.seeedstudio.com/SenseCAP-Multi-Platform-LoRaWAN-Indoor-Gateway-SX1302-EU868-p-5471.html)).
  **IN865 is not listed as a purchasable SKU.** The same page's spec sheet does say the radio
  "supports global LoRaWAN frequency plans from 865 MHz to 923 MHz," which technically covers
  865 MHz — but that's an RF-range claim, not a confirmation that "IN865" is a selectable
  named entry in the Channel Plan dropdown on an EU868-labeled unit.
- Two independent real-world write-ups exist of people deploying this exact gateway for IN865 in
  India, and **both started from EU868-labeled hardware, not an IN865 SKU**:
  - [SensCAP M2: IN865 LoRa Gateway, 4G-Ready Deployment (Hackster.io)](https://www.hackster.io/vinayyn/sensecap-m2-in865-lorawan-gateway-4g-ready-deployment-9f0da3)
  - [SenseCAP M2: IN865 LoRa Gateway Setup with 4G Backhaul (DFRobot community)](https://community.dfrobot.com/makelog-313793.html)
  
  Neither report describes hitting a wall where IN865 was missing from the Channel Plan
  dropdown, and neither reports a firmware swap or RMA to get IN865 working. That's a genuinely
  reassuring signal — it suggests the "EU868" in the product name is the as-shipped default
  channel plan, not a hard RF-hardware lock. But **neither write-up shows the actual dropdown
  contents or explicitly states "IN865 was there and I selected it"** — the ChirpStack
  tutorial's own instructions just say "select the Region and Frequency plan according to the
  actual choice" without listing the options. So this is corroborating evidence, not
  confirmation.

**Bottom line:** two real deployments strongly suggest this works, but nobody's write-up
explicitly confirms the dropdown contains an IN865 entry. The very first thing to do once the
gateway is powered on is open `LoRa → Channel Plan` and look — that single screenshot either
closes this gap for good or tells us early (before the contest/Aug 20 deadline, not after) that a
support ticket or firmware update is needed. Recommend this be the very first action on
unboxing, ahead of any ChirpStack wiring — it's a five-minute check that gates everything else
in this document.

## 5. Sources consulted

- [Quick Start | Seeed Studio Wiki](https://wiki.seeedstudio.com/quick_start_with_M2_MP/)
- [Quick Start for SenseCAP M2 Gateway & Sensors (PDF)](https://files.seeedstudio.com/products/SenseCAP/M2_Multi-Platform_Gateway/Quick%20Start%20for%20SenseCAP%20M2%20Gateway%20&%20Sensors.pdf)
- [SenseCAP M2 Multi-Platform Gateway Overview](https://wiki.seeedstudio.com/Network/SenseCAP_Network/SenseCAP_M2_Multi_Platform/SenseCAP_M2_Multi_Platform_Overview/)
- [SenseCAP M2 MP Gateway LNS Configuration](https://wiki.seeedstudio.com/Network/SenseCAP_Network/SenseCAP_M2_Multi_Platform/SenseCAP_M2_MP_Gateway_LNS_Configuration/)
- [Connect M2 Multi-Platform Gateway to ChirpStack](https://wiki.seeedstudio.com/Network/SenseCAP_Network/SenseCAP_M2_Multi_Platform/Tutorial/Connect-M2-Multi-Platform-Gateway-to-ChirpStack/)
- [traffic_saving_config (checked, not directly relevant — 4G data-usage feature, no region info)](https://wiki.seeedstudio.com/traffic_saving_config/)
- [Seeed product page: SenseCAP M2 SX1302 — EU868](https://www.seeedstudio.com/SenseCAP-Multi-Platform-LoRaWAN-Indoor-Gateway-SX1302-EU868-p-5471.html)
- [SenseCAP M2: IN865 LoRa Gateway, 4G-Ready Deployment (Hackster.io)](https://www.hackster.io/vinayyn/sensecap-m2-in865-lorawan-gateway-4g-ready-deployment-9f0da3)
- [SenseCAP M2: IN865 LoRa Gateway Setup with 4G Backhaul (DFRobot community)](https://community.dfrobot.com/makelog-313793.html)

Not used / not directly applicable to this frozen architecture (ADR 0002 names ChirpStack, not
these), but present in the URL list the user provided — noted here for completeness rather than
silently dropped:
- Connect M2 Multi-Platform Gateway to AWS IoT, to The Things Network — different LNS targets.
- Grove Wio-E5 TTN Demo, Helium Demo, Helium tinyML Demo, SenseCAP Cloud Demo, SenseCAP+XIAO
  ESP32S3 Demo — different network/cloud targets than this project's ChirpStack decision.
- Grove Wio-E5 P2P demo — useful in general (confirms `AT`/`+AT: OK`, `AT+MODE=TEST` command
  shape exists on this module family) but is raw point-to-point mode, not the OTAA/LoRaWAN join
  sequence `mac.cpp` needs — doesn't change anything in the pending mac.cpp fix prompt.
- Grove LoRa-E5 product page, `Grove_LoRa_E5_New_Version` wiki page — both explicitly defer to
  the official AT Command Specification PDF for exact command syntax rather than listing it
  inline; that PDF is the same one already fetched and used for the `mac.cpp` AT-command fix
  work in this session's earlier turn, so no new information here.
