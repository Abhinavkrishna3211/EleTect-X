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
| Optical window (acrylic/PC 2-3mm) | **T** — local |

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

## 6. Power system — **revised 13 Aug against the Aug 20 deployment deadline**

Sized 12 Aug against a real daily energy budget (baseline-dominated by ADR 0008's measured 0.42-0.45W
MPU-suspend draw, ~13Wh/day, plus event-triggered deterrence load) and real Kerala monsoon-season solar
irradiance, not the annual average. Revised same day to the smallest sizing that's still safe (3-day no-sun
autonomy, 85% DoD). Full calculation, formulas, sensitivity table, and sources:
`hardware/bom/eletect-x-power-budget.xlsx`.

**13 Aug: dropped the "smart" solar charge controller category entirely.** Every purpose-built LiFePO4-aware
unit checked failed real verification: the amiciSmart 10A (₹1,949) has a self-contradicting listing (its own
"Product description" says lead-acid only, contradicting its "About this item" b05 claim), mixed real customer
reviews on 4S packs specifically ("unavailable to charge lifepo4 battery pack of 4S" — verified purchase), and
a separately reported firmware bug (won't auto-resume charging after a low-voltage shutdown — disqualifying
for unattended field hardware on its own). Sparkel's SPSCC-1012LiMPPT (₹2,450, genuinely well-engineered,
IP67, real redundant protection) ships factory-default to **Gel lead-acid**, not Lithium — the "S-Unit" remote
needed to reconfigure it isn't sold anywhere on Sparkel's own site. Victron's Bluetooth-programmable units are
the one category that passed every check but cost ₹6,300+, well outside budget.

**Replacement: XL4015 CC/CV buck module, already in hand (bought 28 Jul).** Set manually to 14.2V output
(conservative vs the 14.6V absorption max, for margin against trimmer-pot drift and less full-charge calendar
stress) with current limit set to ~1-2A, verified with a multimeter before connecting to the pack — fully
inspectable, no firmware to trust. Trade-off, accepted deliberately: no staged bulk/absorption/float charging
and no independent hardware overvoltage backstop from the charge side — the **battery's own BMS becomes the
load-bearing safety component**, see battery row below. This also drops ~₹1,900-2,450 from the original plan.

| Item | Status | Spec pinned by the calc | Real product / decision (13 Aug) |
|---|---|---|---|
| 4S LiFePO4 battery | **O — 14 Aug, ⚠️ delivery risk accepted** | **~6Ah** (design daily need ~19.5Wh incl. 25% margin, x3 days no-sun autonomy, 85% DoD → 5.4Ah, round up). | **[Robu.in Pro-Range IFR 32650 12.8V 6000mAh 3C 4S1P LiFePO4](https://robu.in/product/pro-range-ifr-32650-12-8v-6000mah-3c-4s1p-lifepo4-battery-pack/)**, ₹1,799 (₹1,699 with Robu Points). Ordered 14 Aug accepting the delivery risk (Robu's own checkout quotes **5-7 working days**, realistically Aug 21-24 from this date, worse with their 15-17 Aug "Freedom Sale" — genuinely may miss Aug 20). Picked over ELBOTICS (₹2,399, Prime-confirmed 16 Aug) deliberately: Robu's 75×70mm form factor fits directly inside the main enclosure as originally designed (ELBOTICS's 150×65×100mm brick would've forced a separate base-mounted battery box with its own gland/cable run — one more sealed interface and connector pair, undesirable given the horn already went external per ADR 0011). Also has real engineering advantages once landed: 3C discharge rating gives 5.1x margin over our 3.52A peak load vs. ELBOTICS's 1.7x, and it's the pack the permanent build was already sized around. **Action: call Robu support (1800 266 6123) — confirm the real BMS cutoff-voltage spec (their sheet only says "BMS: Y") and ask if expedited shipping is possible given the date.** If it doesn't land by Aug 19, fall back to deploying whatever's in hand or accept a late start within the 10-day window. |
| Solar charge regulation | **H** — already own one (28 Jul) | Set to CV 14.2V, current-limited ~1-2A, verified by multimeter before connecting battery | XL4015 CC/CV buck (see reasoning above). Buy 1-2 more as spares — [Robu.in LM2596S](https://robu.in/product/lm2596s-dc-dc-buck-converter-power-supply/)-class module or the [Robocraze XL4015 5A, Amazon.in](https://www.amazon.in/Robocraze-Lithium-Battery-Charging-Converter/dp/B07RKH7YVY), ₹259, Prime, 2-day delivery — cheap insurance, arrives well before the 20th. |
| **Solar panel** | **T — source locally this week** | 15W clears the monsoon-derated need theoretically; **20W is the realistic smallest buy** (~2.48x margin), 10W workable at tighter ~1.24x margin if that's what's available | No online 12V panel reliably lands by Aug 20 (10+ alternatives checked, earliest Fri-Sun 22-23 Aug). **Plan: buy a 12V/15-20W panel in person at an electronics/solar shop in Malappuram or Kochi this week** — sidesteps shipping lead time entirely, ~₹700-1,500. The [WAAREE 20W panel already ordered](https://www.amazon.in/WAAREE-polycrystalline-Performance-Warranty-Everyday/dp/B0DJJNS73C) (₹899, lands Mon 24 Aug) is too late for the trial — keep it, don't cancel, it becomes the Phase 2/permanent-build panel. |
| Fuse + holder | **T** — buy locally, not online | **Revised to 6A** (14 Aug) — 5A's margin over the worst-case peak (45.1W) shrinks to just 1.11x at low battery voltage (~10V, 4.51A), below the design's own 1.25x safety convention. 6A restores real margin across the full discharge range at no extra cost. | Every Amazon/Robu inline blade fuse holder checked quotes delivery Aug 21-23. Ubiquitous, cheap part (any electronics/automotive-spares shop) — **source locally**, ~₹100-150. |
| Power switch | **T** — buy locally, reverted 14 Aug (bad online listing spec) | SPST, simple 2-position ON/OFF (not ON-OFF-ON), rated ≥10A/12V DC, panel-mounted | The [Electronic Spices 5PCS rocker switch, Amazon.in](https://www.amazon.in/s?k=12V+DC+toggle+switch+SPST&rh=p_n_delivery_date%3A1) pick was checked against its real spec sheet and rejected: it's actually a **3-position ON-OFF-ON switch** (wrong type — wastes/misuses positions for a simple power cutoff), and its "10 Amps" rating is paired only with "250 Volts," reading as an AC rating with no stated 12V DC figure. **Source locally instead** — ask for a simple SPST toggle/rocker switch, 2-position ON/OFF, rated ≥10A at 12V DC (any electronics or automotive-spares shop stocks this, ~₹30-100). Lets you physically confirm position count and DC rating before buying, which online listing text has twice failed to state clearly. Panel-mount via a cut hole in the enclosure wall (rocker style) or drilled hole + nut (toggle style); seal with a thin bead of silicone around the mounting point either way. Wire: battery+ → fuse → switch → WAGO splice point → branches. |
| USB-C→USB-A adapter (camera) | **O — 15 Aug** | Passive adapter only — board sources camera power itself via VBUS back-drive, see Buck audit below | **[Amkette USB 3.0 Type-C Male to USB-A Female OTG Adapter, Amazon.in](https://www.amazon.in/s?k=USB+C+male+to+USB+A+female+OTG+adapter)** — ₹99, 4.4★ (773 reviews), 400+ bought in past month, delivers tomorrow (15 Aug). Picked over the AGARO/Portronics/Ambrane alternatives specifically because its title states the orientation unambiguously ("Type-C **Male** to USB-A **Female**") — most competing listings phrase this ambiguously ("Type C Female to USB Male"), which is backwards-sounding for our use case and risks ordering the wrong orientation. **For resilience: don't let it hang loose on the port** — zip-tie or hot-glue-dab the adapter body to a fixed point near the port so there's no cantilever stress on the connector under vibration. |
| VIN connection (board-side) | **T** — reverted 14 Aug on cost, jumper + hot glue instead of screw shield | VIN is a through-hole pin on the standard shield-style power header — don't solder wire directly to the board | **Female-to-female jumper wires (already have spare stock/cheap to add) + hot glue for strain relief**, not the ₹282 screw shield. Push the jumper socket fully onto the VIN and GND pins, verify a solid connection with a multimeter, then dab hot glue over the joint to lock it in place mechanically — prevents the connector working loose from vibration without paying for a dedicated part. Real trade-off, accepted for this trial: hot glue secures the wire's *position*, not the *contact quality* at the pin itself, the way a screw terminal's physical clamp does — genuinely fine for a 10-day run, worth upgrading to the screw shield for Phase 2's permanent build where the connection needs to survive years, not days. |
| Separate BMS | not needed — battery's BMS confirmed via label + listing | — | — |
| Load-switch MOSFETs | **H** (IRLZ44N, see §7) | — | — |
| Supercap (optional) | skip for now — revisit only if bench testing shows a brownout on deterrence burst | — | — |
| VIN wiring (silicone wire + XT30) | **H** — XT30UD pair ×2 already in hand from the Robu order | — | — |
| Buck converters (TPA3116D2/IR illuminator insurance) | **O — 14 Aug** — bundled into Robu order #3636219 with the battery | Only needed if either board's real input-voltage tolerance falls below the LiFePO4 pack's 14.6V absorption peak (open verification item, see below) | [Robocraze XL4015, Amazon.in](https://www.amazon.in/Robocraze-Lithium-Battery-Charging-Converter/dp/B07RKH7YVY), ₹259 each, Prime — same part as the solar-charging module, buy extras in one order. |
| Bench charger (optional, no longer required) | dropped — the XL4015 solar-charging path covers initial charge-up too | — | Robu's "Battery Charger 4S LiFePO4 -14.5V 1A" (₹700) is no longer needed unless a bench-only backup charge path is wanted. |

**Aug 20 deadline — decided 14 Aug.** This is a 10-day contest trial (deploy, retrieve, review footage), not
yet the permanent install, which changes the risk calculus on both remaining items:
1. **Battery: ordered from Robu 14 Aug, accepting the delivery-timing risk** (see row above) — chosen for the
   compact form factor and discharge margin over the delivery-certain but bulkier/tighter-margin ELBOTICS
   alternative. A 6Ah pack alone, no solar, covers ~3.3 days at the design 85% DoD (65.3Wh usable ÷ 19.47Wh/day
   design load) — not the full 10 days by itself, which is exactly why the panel below still matters.
2. **Solar panel: source locally in Malappuram/Kochi this week** — the actual fix for continuous 10-day
   coverage, since no online 12V panel option lands in time. This is now the primary plan, not a fallback.

**If either slips past Aug 19:** deploy on whatever's in hand and accept partial coverage (battery-only ≈3-4
days of the 10, or delayed start) rather than blocking the whole trial — no additional cost either way.

**Revised total, power block only:** ≈₹2,600-3,450 (battery ₹1,799 + local panel ₹700-1,500 + fuse/holder
~₹100-150 local), not counting the already-sunk WAAREE panel (₹899, held for Phase 2) or the optional spare
XL4015 bucks (₹259-518, only if the TPA3116D2/IR illuminator verification below calls for them) — the cheapest
version of this plan yet, versus the original ₹5,994.

**Buck/regulation audit (13 Aug), all subsystems:**
| Subsystem | Needs a buck? | Why |
|---|---|---|
| LEDs (cool-white/royal-blue) | No — already covered | XL4015 buck driver ×2 already sourced (§3, ordered 30 Jul) |
| UNO Q | No | Confirmed via official Arduino power spec — VIN accepts 7-24V DC, onboard LMR51440 bucks to 5V internally |
| Camera (Arducam IMX462) | No | Powered off USB-C, board-regulated |
| DFPlayer PRO, INA333, ADS1115, LoRa-E5, INMP441, BME280/MPU-6050 (if used) | No, presumed | All draw from the tray's own regulated rails off the UNO Q/perfboard, not directly off the raw battery bus — not yet re-verified against each individual datasheet's absolute max input, worth a quick pass once the tray is populated but not expected to be an issue |
| **TPA3116D2 amp (XH-M543 120W board)** | **Resolved 14 Aug — no buck needed** | Listing spec: Operating Voltage Range 12-24V DC, usage note tolerates DC12V-26V on the input terminal. 14.6V absorption peak sits comfortably inside this range (1.64x margin to the 24V rated max). Wire straight to the battery bus. |
| **940nm IR illuminator board (VISTORA 48-LED, ASIN B0H2DQ9DVK, already purchased 28 Jul)** | **Resolved 14 Aug — buck IS needed** | Listing states a single fixed **Input Voltage: DC12V** (not a range), 300mA draw. The 14.6V absorption peak exceeds this by ~22% — real overvoltage risk to a board with no stated input tolerance margin. **Use one spare XL4015 buck inline, set to ~12V**, ahead of this board specifically. |

Both open items now resolved with real listing data — one spare buck is genuinely needed (IR illuminator),
the amp is fine wired directly to the battery bus. Only need to buy 1 spare XL4015 (₹259), not 2.

## 7. Passives & protection
| Item | Status |
|---|---|
| Resistor kit | **H** |
| Cap kit | **H** |
| 0.68µF film cap ×2 | **O — 30 Jul** |
| 1N4148 ×4 | **H** |
| P6KE18/24CA TVS ×2 | **O — 2 Aug** |
| P6KE6.8CA TVS ×3 | **O — 15 Aug** — Robu, exact part match found, no longer local-only |
| SB5100 Schottky ×1 | **O — 15 Aug** — Robu, exact part match found, no longer local-only |
| IRLZ44N MOSFET | **H** ×5-7 + **O — 14 Aug** top-up bundled into Robu order #3636219 — margin restored, no longer tight |
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
| Silicone O-ring cord | **O — 15 Aug** — SOMA, onlyscrews |
| e-PTFE vent | **O — 4 Aug** |
| SS-304 bracket/U-bolt (main enclosure pole mount) | **O — 15 Aug** — Bectro pole clamp |
| SS-304 bracket/U-bolt (horn pole mount) | **O — 15 Aug** — second Bectro clamp, same part, reused per ADR 0011 horn split |
| PG7/PG9 glands | **H** ×5 each |
| Brass heat-set inserts (onlyscrews) | **O — 15 Aug** | M3-only, "3D Printing" slant-knurled line. Qty 10 each: [M3x4mm](https://onlyscrews.in/products/m3-x-4mm-3d-printing-brass-threaded-inserts-dia-3mm-length-4mm) ₹4.40, [M3x5mm](https://onlyscrews.in/products/m3-x-5mm-3d-printing-brass-threaded-inserts-dia-3mm-length-5mm) ₹4.60, [M3x6mm](https://onlyscrews.in/products/m3-x-6mm-3d-printing-brass-threaded-inserts-dia-3mm-length-6mm) ₹4.80 — ~₹138 for 30 pieces. |
| SS-304 screws (onlyscrews) | **O — 15 Aug** | 1x [M3 Allen Button Head SS304 Assorted Box](https://onlyscrews.in/products/m3-allen-button-head-ss304-assorted-box) (₹240) + individual top-up **M3×8/10/12mm ×15 each** (~₹96) — total ~₹336. |
| VHB double-sided mounting tape (onlyscrews) | **O — 15 Aug** | 3M VHB, transparent 4910 variant for clean bond line — mounts components without screws where a boss isn't practical. |
| M3 standoff spacers (Robu) | **O — 15 Aug** | M3×15mm nylon + M3×5mm brass hex — perfboard solder-joint clearance, camera/IR window offset, UNO Q underside clearance. |
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
