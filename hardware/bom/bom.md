# EleTect X — FINAL Hardware Sourcing (Freeze & Build) — Complete BOM

**All parts India-available (Amazon.in / Robu / local); no imports.** Legend: ✅ HAVE · 🛒 BUY · ⭐ decision note. Prices ≈ July 2026, confirm at cart.

---

## 0. Two decisions locked
- **Camera — LOCKED: `B0CQ4QDCXN` = Arducam IMX462 day/night, auto IR-cut + 940 nm IR, ₹8,680 (Amazon.in).** Only one of the three available that is a proper **active-IR** day/night camera with a top NIR sensor → correct for dark forest. ⚠️ NOT `B0829HZ3Q7` (₹5,932 = OV2710, weak night — budget fallback only, 850 nm). ⚠️ NOT Robu `B0576` IMX662 (₹6,699) — it's a low-light *color* cam with no IR-cut/IR LEDs listed → likely can't do active-IR night; skip unless Robu confirms NoIR. **External IR = 940 nm to match.**
- **Speaker — LOCKED per ADR 0003/0005: Ahuja SUH-15**, flush-mounted into the front face, ₹1,299–3,150. A TOA SC-610 detour (ADR 0004) was reverted (ADR 0005) — it solved the enclosure's "generic box" look with a 3–6x costlier part instead of a form-language fix, which contradicts the project's own cost-effectiveness/scalability principle and meaningfully raises real fleet cost at DFO deployment scale. Compactness/aesthetics are addressed in the enclosure design instead (sentinel two-volume form, visor band, tapered horn cutout).

---

## 1. Compute, comms, core (mostly HAVE)
| Item | Spec | Qty | Status | Source / ₹ |
|---|---|---|---|---|
| Arduino UNO Q | 2 GB | 1 | ✅ HAVE | — |
| LoRa radio | Grove LoRa-E5 (IN865) | 1 | ✅ HAVE | — |
| Amplifier | TPA3116D2 board | 1 | ✅ HAVE | — |
| Mic | INMP441 (I²S) | 1 | ✅ HAVE | — |
| Instrumentation amp | INA333 (module) | 1 | ✅ HAVE ("mic ina") — *confirm it's INA333* | — |
| Geophone | SM-24 10 Hz | 1 | ✅ arriving | — |
| USB hub | — | 1 | ✅ HAVE — **not needed** in frozen design (camera on USB-C direct, audio via DFPlayer). Keep as spare. | — |

---

## 2. Camera + IR subsystem 🛒
| Item | Spec | Qty | ₹ | Source |
|---|---|---|---|---|
| **USB camera** | Arducam **IMX462** day/night USB board — **ASIN B0CQ4QDCXN** (NOT B0829HZ3Q7=OV2710) | 1 (+1 spare rec.) | 6,000–8,680 | Amazon.in (search ASIN **B0CQ4QDCXN**) / Robu / metal-case B0490 |
| **940 nm IR illuminator** | 12 V board, ~45–60° beam, built-in driver (match camera's 940 nm) | 1 | 500–900 | Amazon.in "940nm IR illuminator board 12V" |
| IR-gate MOSFET | Logic-level N-MOSFET (AO3400 or IRLZ44N) module | 1 | 80 | Robu/Amazon.in |
| Optical window | Clear cast acrylic / PC 2–3 mm (cut to size) | 1 | 100–200 | local / Amazon.in |

---

## 3. Geophone burial chain 🛒 (see also passives §7)
| Item | Spec | Qty | ₹ | Source |
|---|---|---|---|---|
| Shielded cable | 2-core shielded (Polycab/Amazon) ~5 m | 1 | 150–400 | [Amazon.in](https://www.amazon.in/Shielded-Signal-transmission-protection-Length/dp/B07DWVY8FT) |
| Capsule | PVC pipe 32 mm + 2 end caps | 1 | 80–150 | local hardware |
| Spike | SS-304 bolt M10 × 100 mm | 1 | 80–150 | Amazon.in / hardware |
| Potting | Araldite Standard (resin+hardener) | 1 | 120–300 | [Amazon.in](https://www.amazon.in/Araldite-Standard-Epoxy-Adhesive-90gm/dp/B08FHBFY27) |
| Conduit | HDPE flexible 20 mm ~3 m | 1 | 100–200 | local / Amazon.in |
| Connector | M12 4-pin IP68 (panel + cable) | 1 | 300–600 | Amazon.in / Zbotic |
| Band-pass op-amp | MCP6002 (dual, low-power) | 1 | 40–90 | Robu/Amazon.in |

---

## 4. Audio deterrence 🛒
| Item | Spec | Qty | ₹ | Source |
|---|---|---|---|---|
| **Audio player** | **DFPlayer PRO** (onboard flash, no SD) | 1 | 500–700 | Robu/Amazon.in *(fallback: DFPlayer Mini + 8 GB microSD)* |
| Horn speaker | **Ahuja SUH-15**, 8 Ω, 15W RMS/23W Max, flush-mounted per ADR 0003 (ADR 0004 TOA SC-610 detour reverted, ADR 0005) | 1 | 1,299–3,150 | Moglix/Amazon.in, or Electrosolutions Trading LLP (Kondotty) |
| Speaker wire | 2-core, ~1 m | 1 | 30 | local |

---

## 5. Visual deterrence 🛒 (India-generic parts; see passives §7)
| Item | Spec | Qty | ₹ | Source |
|---|---|---|---|---|
| White LED | 3 W high-power **cool white** on 20 mm star | 4 | 40 ea | Robu/Amazon.in |
| Blue LED | 3 W **royal blue ~450 nm** on 20 mm star | 2 | 50 ea | Robu/Amazon.in (aquarium/grow LEDs) |
| LED CC driver | PT4115-based buck LED driver (350–700 mA), 12 V in | 2 | 60–120 ea | Robu/Amazon.in |
| LED optics | 20–30° lens + holder for 20 mm star | 6 | 20 ea | Amazon.in |
| LED-gate MOSFET | Logic-level N-MOSFET (AO3400/IRLZ44N) module | 2 | 80 | Robu |
| Small heatsink / Al plate | for LED stars | 1 | 100 | local |

---

## 6. Power system 🛒 (see protection passives §7)

**Pinned by a real daily-energy-budget calculation (12 Aug, revised same day to the smallest safe sizing) —
see `hardware/bom/eletect-x-power-budget.xlsx` for the live, editable model and sources.**

| Item | Spec | Qty | ₹ | Source |
|---|---|---|---|---|
| Battery | **4S LiFePO4 12.8 V, ~6 Ah**, integrated BMS (3-day autonomy, 85% DoD) | 1 | 1,799 | [Robu.in](https://robu.in/product/pro-range-ifr-32650-12-8v-6000mah-3c-4s1p-lifepo4-battery-pack/) — verify BMS/protection before ordering |
| BMS | not needed separately — covered by the battery's integrated BMS | — | — | — |
| Solar charge controller | **PWM/MPPT, explicit LiFePO4 profile**, ≥10 A | 1 | 1,949 | [amiciSmart 10A, Amazon.in](https://www.amazon.in/amiciSmart-Charger-Controller-Intelligent-Regulator/dp/B07T8LBN9J) — In Stock, selectable "b05: LiFePO4" mode confirmed. (Sparkel SPSCC-MPP1220Li was the better spec match but out of stock; Robu's ₹334 unit is lead-acid only — do not use.) |
| Solar panel | **12 V, 20 W** poly | 1 | 899 | [WAAREE, Amazon.in](https://www.amazon.in/WAAREE-polycrystalline-Performance-Warranty-Everyday/dp/B0DJJNS73C) — In Stock (Robu/Loom 20W options confirmed out of stock 13 Aug) |
| Reverse-polarity | Schottky diode **SB5100 (5 A)** *or* P-MOSFET ideal-diode | 1 | 20–60 | Robu |
| Fuse + holder | 5 A blade fuse + inline holder | 1 | 40 | Amazon.in |
| Load-switch MOSFETs | N-MOSFET modules (AO3400/IRLZ44N) for camera/IR/amp/LED rails | 3–4 | 80 ea | Robu |
| Supercap (optional) | 3× 10 F 2.7 V (series) for pulse buffer | 1 set | 200 | Robu *(optional for prototype)* |
| VIN wiring | connect 12.8 V → UNO Q **JANALOG VIN** (7–24 V); silicone wire + XT30/JST | — | 100 | local |

---

## 7. ⭐ PASSIVES & SEMICONDUCTORS — complete list (buy a resistor + cap kit, plus these specifics)

**Easiest: buy an assorted 1/4 W resistor kit + assorted ceramic + film cap kit (₹300–600 total) — it covers most values below.** Then buy these specific parts:

### Resistors (1/4 W, 1% where analog)
| Value | Qty | Use |
|---|---|---|
| 100 Ω | 4 | geophone series protection (×2), MOSFET gate (×2) |
| 1 kΩ | 2 | INA333 gain Rg (×100); spare |
| 3.3 kΩ | 1 | geophone damping (across coil) |
| 10 kΩ | 4 | Vref divider (×2), SDZ pull, spare |
| 33 kΩ | 2 | band-pass low-pass (50 Hz) |
| 100 kΩ | 4 | band-pass high-pass (2 Hz) ×2, MOSFET gate pulldown ×2 |
| 1 MΩ | 2 | geophone bias to Vref |
| 100 kΩ | 2 | (extra pulldowns) |

### Capacitors
| Value | Type | Qty | Use |
|---|---|---|---|
| 0.68 µF | film | 2 | band-pass high-pass (2 Hz) |
| 0.1 µF (100 nF) | film/ceramic | 2 | band-pass low-pass (50 Hz) |
| 100 nF | ceramic | 6 | decoupling (INA333, op-amp, MCUs) |
| 10 µF | electrolytic/ceramic | 4 | Vref filter, rail decoupling |
| 470 µF–1000 µF, 25 V | electrolytic | 2 | amp/LED rail bulk decoupling |

### Diodes / TVS / MOSFETs
| Part | Qty | Use |
|---|---|---|
| **Bidirectional TVS ~5–6 V** (e.g., SMAJ5.0CA / P6SMB6.8CA) | 3 | geophone input surge/ESD (2 to GND + 1 across) |
| **TVS ~18–24 V** (SMBJ18A/SMBJ24A) | 2 | solar + battery input surge |
| **Schottky SB5100 (5 A)** | 1 | reverse-polarity (or P-FET) |
| **AO3400 / IRLZ44N** logic-level N-MOSFET | 6–8 | IR gate, LED gate, load switches (buy a few spare) |
| 1N4148 signal diode | 4 | misc protection/flyback |
| Green/Red status LED (3 mm) + 1 kΩ | 2 | on-board diagnostics (optional) |

---

## 8. Environmental / sensors 🛒
| Item | Spec | Qty | ₹ | Source |
|---|---|---|---|---|
| BME280 | temp/humidity/pressure (I²C/Qwiic) | 1 | 250–400 | Robu/Amazon.in |
| IMU (tamper) | LSM6/ MPU-6050 (I²C) *(optional)* | 1 | 150–300 | Robu |
| Electret mic + preamp | MAX9814 module — MCU always-on gunshot *(optional)* | 1 | 150–250 | Robu |

---

## 9. Enclosure & mechanical 🛒 (print in-house PETG)
| Item | Spec | Qty | ₹ | Source |
|---|---|---|---|---|
| PETG filament | 1 kg (main body + modules) | 1 | 1,000–1,500 | Amazon.in |
| Silicone O-ring cord | 3 mm, ~2 m (gaskets) | 1 | 150 | Amazon.in |
| Pressure vent | e-PTFE / Gore-type vent (or PTFE membrane) | 1 | 150–400 | Amazon.in |
| Mounting bracket | SS-304 bracket / U-bolt (60–110 mm pole) | 1 | 300–600 | Amazon.in / hardware |
| Cable glands | PG7/PG9 IP68 | 4 | 30 ea | Amazon.in |
| Aviation connector | GX16 (expansion port) *(optional, for future pods)* | 1 | 150 | Amazon.in |
| Heat-set inserts | brass M3 ×10, M4 ×4 | 1 set | 200 | Amazon.in |
| Screws | SS-304 M3/M4 assortment + tamper bit | 1 set | 200 | Amazon.in |
| Stainless straps / ties | for pole + cable | few | 150 | local |
| Desiccant packs | silica gel | few | 50 | local |

---

## 10. Cost summary (one prototype node)
| Block | ~₹ |
|---|---|
| Camera + IR | 6,600 |
| Geophone chain | 1,300 |
| Audio deterrence | 1,300–2,300 (Ahuja SUH-15, ADR 0003/0005) |
| Visual deterrence | 900 |
| Power system | 4,500 |
| Passives/semis kit | 700 |
| Environmental | 500–900 |
| Enclosure/mech | 2,600 |
| **Total (already-owned excluded)** | **≈ ₹18,000–20,000** |
*(You already own UNO Q, LoRa, TPA3116, INMP441, INA333, geophone → those aren't re-counted.)*

---

## 11. Order-now checklist (freeze)
1. ☐ **Camera:** Arducam **IMX462 board — ASIN `B0CQ4QDCXN`** (NOT the ₹5,932 `B0829HZ3Q7`, which is OV2710). Try Amazon.in ASIN search → Robu → metal-case B0490 ₹8,680. Match IR to sensor (IMX462→940 nm). *(+1 spare if budget allows.)*
2. ☐ **940 nm IR illuminator board (12 V)** + N-MOSFET.
3. ☐ **DFPlayer PRO** + **8 Ω horn** (Ahuja SUH-15, flush-mount per ADR 0003 — see ADR 0005 for why the TOA SC-610 detour was reverted).
4. ☐ **LEDs:** 4× 3 W white + 2× 3 W royal-blue stars + 2× PT4115 drivers + 6× lenses + MOSFETs.
5. ☐ **Power:** 4S LiFePO4 pack + BMS + MPPT (LiFePO4) + 20 W panel + Schottky + fuse + load-switch MOSFETs.
6. ☐ **Geophone burial:** shielded cable + PVC pipe/caps + SS spike + Araldite + M12 + HDPE conduit + MCP6002.
7. ☐ **Passives:** resistor kit + cap kit + the specific R/C/TVS/MOSFET list in §7.
8. ☐ **Sensors:** BME280 (+ optional IMU, electret mic).
9. ☐ **Enclosure:** PETG + silicone cord + PTFE vent + SS bracket + glands + inserts + screws + acrylic window.
10. ☐ **Confirm** you have: UNO Q, Grove LoRa-E5, TPA3116, INMP441, **INA333** (verify), geophone.

**After these land → freeze the BOM and start building.** Everything is India-sourced, no imports, deadline-safe (camera ships now).

## Sources
[Arducam IMX462 day/night USB **board** B0CQ4QDCXN](https://www.amazon.com/Arducam-Computer-Automatic-Switching-All-Day/dp/B0CQ4QDCXN) · [same on Robu.in](https://robu.in/product/arducam-1080p-day-night-vision-usb-camera-2mp-infrared-webcam-with-automatic-ir-cut-switching-and-ir-leds/) · [Ahuja SUH-15 horn ₹1,299](https://www.moglix.com/ahuja-15w-horn-speaker-suh-15/mp/msnr50n423r251) · [Araldite (Amazon.in)](https://www.amazon.in/Araldite-Standard-Epoxy-Adhesive-90gm/dp/B08FHBFY27) · [shielded 2-core cable (Amazon.in)](https://www.amazon.in/Shielded-Signal-transmission-protection-Length/dp/B07DWVY8FT)
