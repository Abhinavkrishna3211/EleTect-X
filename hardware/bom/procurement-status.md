# EleTect X — Procurement Status (live tracker)

Supersedes the ✅/🛒 markers in `bom.md` for current status; `bom.md` stays the spec/pricing reference.
Snapshot taken **28 Jul 2026**. Update this file directly as orders land — don't let it go stale like the
old BOM markers did.

Legend: **H** = in hand · **O (date)** = ordered, expected that date · **T** = to order · **L** = to order,
local store only (not worth an online search, per prior sourcing attempts this session)

---

## 1. Compute, comms, core
| Item | Status | Note |
|---|---|---|
| Arduino UNO Q | **H** ×2 (2GB + 4GB) | Second unit = permanent bench/dev board — never touch the field-bound one once flashed. Genuinely useful given the Aug 8 freeze discipline. |
| Grove LoRa-E5 (IN865) | **H** | — |
| SenseCAP SX1302-4G gateway | **H** — ⚠️ **labeled EU868, architecture requires IN865** | See §Flags below — verify before relying on it. |
| XIAO ESP32S3 + Wio-SX1262 (Meshtastic kit), Wio Tracker L1 | **H**, not in current architecture | Meshtastic ≠ the frozen LoRaWAN IN865 design (ADR 0002). Keep as spares/future-pod hardware; don't let it scope-creep the build. |
| TPA3116D2 amp | **H** | — |
| INMP441 mic | **H** ×2-3 | — |
| INA333 | **H** | — |
| ADS1115 | **H** | Confirmed needed — bench ADC stand-in for the geophone front-end per the build schedule. |
| SM-24 geophone | **H** | — |
| USB hub | **H** | Bridges the IMX462's USB-A UVC connector to the UNO Q's single USB-C port for bench validation (build call 3's camera check). Not part of the final field enclosure — a compact USB-C-to-USB-A pigtail is the likely permanent fit once the camera path is proven. |
| Arducam IMX462 | **H** | No stand-in needed — real camera already in hand. |

## 2. Camera + IR
| Item | Status |
|---|---|
| 940nm IR illuminator board | **O — 5 Aug** |
| IR-gate MOSFET | **H** (IRLZ44N, consolidated — see §7) |
| Optical window (acrylic/PC 2-3mm) | **T** |

## 3. Geophone burial chain
| Item | Status |
|---|---|
| 2-core shielded cable | **O — 6 Aug** |
| PVC pipe 32mm + end caps | **T** — local |
| SS-304 bolt M10×100 (spike) | **T** — local |
| Araldite epoxy | **T** — local |
| HDPE conduit 20mm | **T** — local |
| MCP6002 (band-pass op-amp) | **O — 4 Aug** |
| PG7 gland (outdoor entry) | **H** ×5 |

## 4. Audio deterrence
| Item | Status |
|---|---|
| DFPlayer Mini | **H** — bench stand-in |
| DFPlayer PRO | **O — 4 Aug** |
| Ahuja SUH-15 horn | **O — ~30-31 Jul** (2-3 days out) |
| Speaker wire | **H** (silicone wire stock covers this) |

## 5. Visual deterrence (LED)
| Item | Status |
|---|---|
| Cool-white 3W LED star ×4 | **O — 5 Aug** |
| Royal-blue 3W LED star ×2 | **O — 2 Aug** |
| XL4015 buck driver ×2 (+1 spare) | **O — 30 Jul** |
| Heatsink puck ×6 | **O — 5 Aug** |
| Thermal adhesive tape | **O — 2 Aug** |
| Steko lens+holder | dropped — not needed |

## 6. Power system — **the one block still fully unordered**
| Item | Status |
|---|---|
| 4S LiFePO4 battery | **T** — buy a pack with **integrated BMS** (resolves the BMS line below in one purchase) |
| Separate BMS | not needed if battery has integrated BMS |
| MPPT solar controller (LiFePO4-aware) | **T** |
| 20W solar panel | **T** |
| Fuse + holder | **T** |
| Load-switch MOSFETs | **H** (IRLZ44N, see §7) |
| Supercap (optional) | skip for now — revisit only if bench testing shows a brownout on deterrence burst |
| VIN wiring (silicone wire + XT30) | **H** — XT30UD pair ×2 already in hand from the Robu order |

## 7. Passives & protection
| Item | Status |
|---|---|
| Resistor kit | **H** |
| Cap kit | **H** |
| 0.68µF film cap ×2 | **O — 30 Jul** |
| 1N4148 ×4 | **H** |
| P6KE18/24CA TVS ×2 | **O — 2 Aug** |
| P6KE6.8CA TVS ×3 | **L** — local store |
| SB5100 Schottky ×1 | **L** — local store |
| IRLZ44N MOSFET | **H** ×5-7 — need ~6-7 total (IR-gate ×1, LED-gate ×2, load-switch ×3-4); **tight, not slack** — see §Flags |
| LR7843 MOSFET control module | **H** ×1 | Pre-built module, screw terminals — fits the "no PCB fab" constraint better than a bare IRLZ44N for at least one load-switch position. See §Flags. |
| Status LEDs 3mm + 1kΩ | **H** ×2 |

## 8. Environmental sensors
| Item | Status |
|---|---|
| BME280 | **H** |
| MPU-6050 | **H** |
| Electret mic + MAX9814 | **dropped** — see §Flags |

## 9. Enclosure & mechanical
| Item | Status |
|---|---|
| PETG filament 1kg | **H** |
| Silicone O-ring cord | **T** |
| e-PTFE vent | **O — 4 Aug** |
| SS-304 bracket/U-bolt | **T** |
| PG7/PG9 glands | **H** ×5 each |
| Brass heat-set inserts (onlyscrews) | **T** |
| SS-304 screws (onlyscrews) | **T** |
| Desiccant packs | **O — 30 Jul** |

## Already in hand, off the original checklist (Robu wire/connector order)
16AWG silicone wire, 22AWG 2-core, 18AWG PTFE (red+black), 26AWG 4-core, 26AWG 3-core, 26AWG 2-core,
26AWG 5-colour kit, XT30UD pair ×2, JST XH 2/4/6-pin sets, WAGO lever splice connectors (2/3/5-way),
GRM155 0402 SMD 2.2µF cap ×3 (SMD — bench reference only, not usable given no-PCB-fab constraint, low
stakes either way), PG7/PG9 glands (additional stock), LR7843 module.

---

## Flags — need a decision, not just a status

1. **LoRa gateway region mismatch.** CONTEXT.md and the frozen architecture specify **IN865**
   (868MHz is illegal to transmit on in India). The SenseCAP gateway in hand is labeled **EU868**.
   IN865's channel plan (865.0625-867.9MHz) sits inside EU868's typical RF front-end passband
   (863-870MHz), so the hardware may well work once ChirpStack is configured with the IN865 region
   profile — SenseCAP's SX1302 gateways are often software-region-selectable within their filter's
   range — but "may well work" isn't good enough to discover on field-test day. **Action: power it up,
   set the ChirpStack region profile to IN865, and run a real join test with the Grove E5 this week** —
   this is cheap to check now and expensive to find out wrong on Aug 9-14.
2. **INMP441 vs. MAX9814 — good catch, dropping MAX9814.** They weren't redundant purchases of the same
   thing: INMP441 (I2S digital) is the architecture's one acoustic-corroboration sensor (CONTEXT.md §3);
   MAX9814 was listed as an *optional* second, analog, MCU-native mic for a lighter-weight always-on
   listen path. You already have 2-3 INMP441 units and it's marked optional in the original BOM for a
   reason — one sensor doing the job cleanly beats two doing it redundantly (CONTEXT.md §7, "reject
   gimmicks"). Dropped — removed from §8 above, no purchase needed.
3. **IRLZ44N quantity is tight (5-7 in hand vs. ~6-7 needed), not comfortably spare.** Two ways to close
   the gap without a new order: use the **LR7843 module** you already have for one of the load-switch
   positions (camera or IR rail — it's a pre-built screw-terminal switch module, which is a better fit
   for the "no PCB fab" constraint than hand-wiring another bare IRLZ44N with gate/pulldown resistors
   anyway), or add a couple more IRLZ44N to whatever's next Robu order to restore real spare margin.
4. **Battery purchase resolves two BOM lines at once** — buying a pack with integrated BMS (as already
   recommended earlier this session) means §6's "Separate BMS" line disappears entirely; don't shop for
   it separately.

## Priority order for what's still unordered

1. **Order the power system today.** Battery + MPPT + panel + fuse are the only block with zero orders
   placed, they're the longest remaining lead-time item, and Day "Mon 3 Aug" in `BUILD_BLUEPRINT_AUG8.md`
   already assumes power is in hand and wired by then. Ordering today gives ~5-6 days of shipping slack;
   waiting even a few more days starts eating into that.
2. **Order enclosure hardware this week** (O-ring cord, SS bracket/U-bolt, brass inserts + screws via
   onlyscrews) — needed for the Aug 4-5 enclosure-assembly stage, not urgent today but shouldn't slip
   past this week.
3. **Local-store run this week, no shipping risk either way:** PVC pipe/caps, SS-304 spike, Araldite,
   HDPE conduit, P6KE6.8CA, SB5100, acrylic window — cheap, fast, no reason to wait.

## What this changes about the build schedule

Nothing, structurally — it confirms it. Every item already ordered lands between **30 Jul and 6 Aug**,
which is exactly `BUILD_BLUEPRINT_AUG8.md`'s Stage 2 window ("real hardware lands," Sun 2 – Wed 5 Aug).
None of it blocks Stage 0/1 (today through Sat 1 Aug), since that stage runs entirely on bench stand-ins
you already have in hand: ADS1115+INA333 for the geophone, DFPlayer Mini for audio, and the **real**
IMX462 for vision (no stand-in even needed there — camera's already in hand). Power is the one gap that
needs to close today to keep Stage 2's Aug 3 power-validation task on schedule.
