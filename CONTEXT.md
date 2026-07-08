# EleTect X — Project Context (Single Source of Truth)

> Keep this file <200 lines. It is the canonical summary. Detailed docs live in `docs/`. When a decision changes, update this file **and** add an ADR in `docs/decisions/`.

## 1. Mission
Reduce Human–Elephant Conflict on Kerala forest edges with an autonomous, solar-powered node that **detects early, confirms, deters adaptively, alerts humans, and coordinates** with neighbours — day/night, offline-capable.
Targets: **Asian elephant (primary)**; boar, gaur, deer, monkey, leopard, tiger (secondary).

## 2. Goals (in priority order)
1. Win Arduino Physical AI Challenge India 2026 (**submit ≤ 23 Aug**).
2. Win Hackster "Invent the Future with UNO Q" (**submit ≤ 30 Aug**).
3. Field-deploy with Kerala Forest Department (Kothamangalam DFO approved) + capture real footage.
4. Scientifically rigorous, reliable, low-power, manufacturable, scalable product.

## 3. Node hardware (frozen)
- **Compute:** Arduino UNO Q (STM32U585 MCU + Qualcomm QRB2210 Linux MPU). Powered from **VIN 12.8 V** (USB-C free for camera). No carrier board (unavailable) → USB camera, top headers only.
- **Camera:** Arducam **IMX462** day/night USB (ASIN B0CQ4QDCXN), auto IR-cut + **940 nm** IR.
- **IR:** external **940 nm** illuminator, MOSFET-pulsed only during capture.
- **Seismic (primary):** SparkFun **SM-24** 10 Hz geophone → **INA333** + Sallen-Key band-pass 2–50 Hz → **STM32 internal ADC** (LPBAM). Buried, potted capsule + SS spike, ~400 mm, vertical.
- **Acoustic:** INMP441 (>60 Hz corroboration + anti-poaching gunshot/chainsaw). Not infrasound.
- **Audio deterrence:** STM32 → **DFPlayer-PRO** → **TPA3116D2 (PBTL)** → **8 Ω horn** (Ahuja SUH-15, external-mounted).
- **Visual deterrence:** front pods, **cool-white + royal-blue (~450 nm)** LEDs, irregular strobe, optically isolated from lens.
- **Comms:** Grove **LoRa-E5**, LoRaWAN **IN865**.
- **Power:** 4S **LiFePO4** 12.8 V + low-Iq MPPT + 15–20 W solar + supercap + surge/reverse-polarity protection.
- **Enclosure:** in-house **PETG** print (CR-M4 + Bambu A1), silicone-gasket seams, e-PTFE vent, external geophone, IP-by-design (gaskets/potting/paint, not the print).
- **Optional pods (future):** Environment+Fire-risk (RG-9 rain, soil moisture) via smart aviation-connector pod; anti-poaching mic array. EleTect 1.5 road-signage via LoRa.

## 4. Physical-AI architecture (frozen)
- **Reflex (STM32, always-on µA):** geophone STA/LTA + TinyML footfall; gunshot trigger; actuator timing; safety rule-gates; LoRa; power; watchdog.
- **Cognition (QRB2210, event-only):** vision INT8 detector (Adreno/OpenCL) → **weighted log-odds fusion** (availability-gated) → risk/RP → **contextual-bandit** deterrence (never-repeat, stop-on-retreat) → SQLite experience → coordination.
- **Fusion math:** `L = L_prior + Σ aᵢ wᵢ (ℓᵢ − ℓ₀ᵢ)`, `P = σ(L)`. Explainable; missing sensors drop out. No DST/POMDP.
- **Learning (safe/bounded on-device):** bandit action-values + thresholds + site-noise self-calibration. **Vision model fixed** (OTA-updated centrally).
- **Coordination:** LoRa **star** + neighbour pre-arm; movement from node-detection **sequence** (no TDOA); **safe herding corridors** (deter on the village side, keep a forest-side escape lane; never trap/herd toward settlements).
- **Autonomy:** all control is local; cloud is monitoring/analytics only.

## 5. Software split
- **STM32U585 (C/C++, Arduino Core on Zephyr):** sensors, actuators, LoRa MAC, power, safety gates.
- **QRB2210 (Debian, Python):** perception, fusion, bandit, SQLite, Bridge RPC, LoRa uplink.
- **Bridge (RPC):** MCU pushes features/events; MPU returns decisions. Send meaning, not raw data.
- **Gateway:** SenseCAP SX1302 (region **IN865**) → ChirpStack.
- **Backend:** Supabase (Postgres + auth + realtime + storage + edge functions); ChirpStack→MQTT→ingest.
- **Frontend:** React PWA (ranger dashboard + public marketing), hosted on Vercel.

## 6. Deployment
Nodes ~120–150 m along the boundary; GUARD (full) at crossings, WATCH (no heavy deterrence) elsewhere; gateway per 8–15 km. 3-person install <20 min; app stomp-test + site calibration.

## 7. Engineering principles
Measurable > vibes · explainable AI · low power · robustness · maintainability · scalability · manufacturability · cost-effectiveness · reliability · **simplicity over complexity**. Reject gimmicks. Justify every non-trivial choice (power/latency/cost/accuracy).

## 8. Key constraints / gotchas
- No carrier board → USB camera + top headers only.
- IR wavelength **must match** camera filter (IMX462 → 940 nm).
- LoRa **IN865** only (868 MHz is illegal in India).
- INMP441 can't hear infrasound (<60 Hz) — geophone owns low frequency.
- IP rating comes from gaskets/potting/paint, not FDM prints.
- Repo contains **no AI/assistant references** anywhere.

## 9. Current status
Architecture frozen. Hardware being sourced (BOM in `docs/hardware/`). Available now: UNO Q, Grove LoRa-E5, TPA3116, INMP441, INA333, ADS1115. Arriving: camera, geophone, speaker, LEDs, IR. Software/dashboard/AI can start immediately (see `docs/PROJECT_BLUEPRINT.md`).

## 10. Deadlines
Robu submission **23 Aug** · Hackster submission **30 Aug** · Field test **early–mid Aug** · Fable frontend build window **closes 12 Jul**.
