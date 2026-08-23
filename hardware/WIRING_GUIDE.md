# EleTect X — physical wiring guide (bench bring-up, pre-battery)

Written 22 Aug 2026. Covers everything except the battery pack (Robu order #3636219, not yet
landed — see `hardware/bom/procurement-status.md`). Geophone and LoRa are already wired; this
guide is for the five subsystems still at **U** (unwired) in
`hardware/references/UNO_Q_PINOUT_REFERENCE.md`'s wiring-status table: horn, LED white, LED blue,
IR illuminator, and the shared power bus that feeds them.

Every pin assignment and constant below is quoted directly from `device/mcu/src/config.h` (line
numbers as of this writing) and the cited ADRs/BOM — nothing here is invented. Re-check `config.h`
directly if you're reading this more than a session or two after 22 Aug in case a value changed.

## 0. What's already done — don't re-wire this

| Subsystem | Status | Reference |
|---|---|---|
| Geophone (SM-24 → 1kΩ damping → INA333 → ADS1115 → D20/D21 I2C2) | **W** | `device/mcu/README.md`'s wiring table |
| Grove LoRa-E5 (Yellow=TX→D0, White=RX→D1, Red=VCC→5V, Black=GND→GND) | **P** — physically wired, module not yet answering AT probes (separate open issue, not a wiring defect) | `docs/KNOWN_GAPS.md`'s 18 Aug entry |
| Camera (Arducam IMX462 → USB hub/adapter → UNO Q USB-C) | Bench-verified, no new wiring needed | `docs/KNOWN_GAPS.md`, build-call 3 |

## 1. Power bus — the part that doesn't need the battery to build

Wire the whole bus now; leave the battery-side leads unterminated (twist-capped or in a spare
WAGO port) until the pack lands. Everything downstream of the bus can be fully built and even
bench-powered from a substitute source today (§1c).

**Topology** (per `hardware/bom/procurement-status.md`'s own power-switch row, "battery+ → fuse →
switch → WAGO splice point → branches"):

```
Battery+ (4S LiFePO4, 12.8V nominal) → 6A blade fuse → SPST switch → WAGO 5-way splice → branches:
  1. UNO Q VIN (7-24VDC input, onboard LMR51440 bucks to 5V — confirmed via official Arduino
     power spec, procurement-status.md §Buck audit)
  2. TPA3116D2 amp DC input (XH-M543 board, rated 12-24VDC per its listing — wired straight to
     the bus, no buck needed, same audit)
  3. LED buck driver #1 input (→ cool-white LED string)
  4. LED buck driver #2 input (→ royal-blue LED string)
  5. IR illuminator's own XL4015 buck input (steps 12.8-14.6V down to the board's fixed 12V
     rating — required, see §4)
Battery− → common ground bus (WAGO or bus bar) → all of the above returns.
```

**Not on this bus: the DFPlayer PRO.** Per its own spec sheet it runs on 3.3-5V, not the 12.8V
actuator bus. Tap its VIN off the UNO Q's 5V pin instead (same rail the LoRa E5's VCC already
uses), GND to common ground. See §3 step 2.

**1a. Fuse and switch.** Both are local-store items per `procurement-status.md` — 6A blade fuse
(revised up from 5A on 14 Aug because 5A's margin over the 45.1W worst-case peak shrinks to 1.11x
at low battery voltage), SPST 2-position ON/OFF rated ≥10A/12V DC. Wire fuse and switch in series
on the **positive** leg only, between battery+ and the WAGO splice — never fuse/switch the ground
return.

**1b. Wire gauge for the bus.** System peak draw is already computed in `procurement-status.md`:
**3.52A at nominal 12.8V, rising to 4.51A at a depleted ~10V pack** (that 45.1W worst-case figure
divided by voltage). Sized against a real automotive 12V ampacity chart (2% voltage-drop
convention, [WiringProducts' automotive wire chart](https://wiringproducts.com/pages/wire-amperage-capacity-chart)):
16AWG carries 5A comfortably out to 11.5ft, 10A out to 5.8ft. Your run inside one small enclosure
is under 1ft in every case, so gauge choice here is about safety margin and connector fit, not
voltage drop.

Use what's already in hand (`procurement-status.md`'s "Already in hand" list) — no new wire
purchase needed:
- **16AWG silicone wire** — main bus: battery+ → fuse → switch → WAGO, and WAGO → each branch's
  first few inches before it steps down to a lighter gauge at the load itself. This is your
  heaviest stock and the right choice for the only run carrying the full system current.
- **18AWG PTFE (red+black)** — branch feeds to the TPA3116D2 amp's DC input and to each XL4015
  buck driver's input side (LED bucks, IR buck) — each of these branches carries at most ~1A,
  18AWG has enormous margin.
- **22AWG 2-core** — buck driver *output* → LED string, and IR buck output → IR board (each ≤0.3A,
  see §4/§5).
- **XT30UD pair** (2 in hand) — good fit for the battery-to-fuse or fuse-to-switch joint if you
  want a disconnectable bench connector there rather than a permanent solder/crimp joint;
  otherwise WAGO levers throughout are simpler and already specified.
- **WAGO lever splice connectors (2/3/5-way, in hand)** — use the 5-way at the main splice point
  exactly as `procurement-status.md` specifies.

**1c. Real battery in hand (22 Aug) — first-use checklist before it touches anything.** The Robu
Pro-Range IFR 32650 12.8V 6000mAh 4S1P LiFePO4 pack has arrived
(`hardware/bom/procurement-status.md`). Before it connects to the bus for the first time:

1. **Multimeter the resting voltage before touching anything else.** A healthy 4S LiFePO4 pack
   rests somewhere in the 12.8-13.6V range depending on state of charge — it should not read near
   0V (dead/miswired BMS) or above ~14.6V (over-charged, do not use). If it reads outside a sane
   range, stop and don't connect it.
2. **Confirm polarity at the XT30 connector before plugging in** — reversed polarity on a LiFePO4
   pack is a real fire risk, not just a "won't work" mistake. The XT30UD pairs already in hand are
   keyed, but verify with the multimeter anyway; don't trust the connector shape alone on a
   first-ever connection.
3. **No fuse/switch yet, and this is now the real pack, not a current-limited bench supply** — a
   short on this bus can deliver far more fault current than a wall adapter ever would, limited
   mainly by the BMS's own trip threshold and the battery's internal resistance, not by anything
   you've wired. Getting the ₹100-150 fuse+switch before this pack goes anywhere near the actuator
   bus is a stronger recommendation now than it was with a bench supply — if a local store is
   reachable before you wire further, that's the highest-leverage five minutes available tonight.
   If it genuinely isn't reachable in time: keep every connection brief and supervised, verify each
   new branch with the multimeter before power-on, disconnect the battery between stages rather
   than leaving it hot while you wire the next one, and never leave it connected unattended.
4. **Charging setup (XL4015 set to 14.2V CC/CV) is a separate task from tonight's bring-up** — the
   pack should already carry enough charge to bench-test the actuators directly off it; don't wire
   up the solar/charge path tonight unless you specifically want to. Keep that XL4015 distinct from
   the two load-side XL4015 bucks (LED, IR) — three total XL4015 modules in this system, easy to
   mix up.

Do **not** substitute the UNO Q's own USB-C port for the 12.8V actuator bus — USB-C powers the
board itself only (5V rail); it isn't wired to backfeed the actuator bus and isn't safe to attempt.

## 2. GPIO control-signal wiring (D2/D3/D4/D5/D6/D7/D8)

These are logic-level signal wires, not power — the UNO Q's own thin jumper wire or the 26AWG
stock in hand is correct here, not the heavier bus gauges above. All pins below are confirmed
5V-tolerant on input per `hardware/references/UNO_Q_PINOUT_REFERENCE.md`'s official warning
("all MCU GPIOs are 3.3V logic and 5V tolerant, except A0 and A1") — relevant below because the
IRLZ44N gate side taps in at 3.3V, not 5V.

| Pin | MCU pin | `config.h` name | Drives |
|---|---|---|---|
| D2 | PB3 | `AUDIO_TRIGGER_PIN` | DFPlayer IO/ADKEY input (§3) |
| D4 | PA12 | `HORN_AMP_ENABLE_PIN` | TPA3116D2 `SHUTDOWN` pin, active-low (§3) |
| D5 | PA11 | `LED_WHITE_PIN` (→ **planned rename `LED_WHITE_LEFT_PIN`**, §4) | IRLZ44N gate, white LED branch, left wing (§4) |
| D3 | PB0 | **planned `LED_WHITE_RIGHT_PIN`** — not yet in `config.h`, confirmed free/unused, PWM-capable (OPAMP2 output shares this pin but is unused in this design) | IRLZ44N gate, white LED branch, right wing (§4) |
| D6 | PB1 | `LED_BLUE_PIN` (→ **planned rename `LED_BLUE_LEFT_PIN`**, §4) | IRLZ44N gate, blue LED branch, left wing (§4) |
| D8 | PB4 | **planned `LED_BLUE_RIGHT_PIN`** — not yet in `config.h`, confirmed free/unused | IRLZ44N gate, blue LED branch, right wing (§4) |
| D7 | PB2 | `IR_ILLUMINATOR_PIN` | IRLZ44N (or LR7843 module) gate, IR board (§5) |

**D3/D8 are a planned addition, not yet in firmware — see §4.0.** Don't wire them expecting
`led.cpp` to already drive them; `config.h`/`led.cpp`/`led.h` need the corresponding update first
(next VS Code/Sonnet session), same one-at-a-time Bridge-registration discipline as every other
actuator pin in this repo.

## 3. Horn: DFPlayer PRO → TPA3116D2 (XH-M543) → Ahuja SUH-15

Per ADR 0003 (single BTL channel, not PBTL) and ADR 0011 (SUH-15 now lives in its own small IP66
housing, off the main enclosure, connected by 2-core speaker wire through a gasketed gland).
Revised 22 Aug against the real DFPlayer PRO (DFR0768) datasheet/schematic and the actual
techtonics XH-M543 board photos — three corrections from the original plan, all verified against
primary sources, not assumed:

1. **DFPlayer PRO power: VIN → UNO Q 5V, GND → common ground.** Its spec sheet states 3.3-5V —
   it does **not** go on the 12.8V actuator bus (see §1's new note). Confirm with a multimeter
   before connecting.
2. **D2 (`AUDIO_TRIGGER_PIN`, PB3) → DFPlayer PRO's `KEY` pin, active-low.** This is the DFR0768's
   real pin name — "IO/ADKEY" was the DFPlayer *Mini*'s naming, different hardware. The DF1101S
   chip inside the PRO pulls `KEY` up to its own IO rail through a 22kΩ resistor (idle **high**)
   and reads a direct short to ground as key K1 = Play & Pause (confirmed in the DF1101S
   datasheet §5 and cross-checked against a DFRobot reference schematic for a sibling board using
   the same chip). `horn.cpp` was fixed 22 Aug (commit `493f2fb`) to idle `AUDIO_TRIGGER_PIN` high
   and pulse it low — matches this circuit now. A direct jumper from D2 to `KEY` is correct, no
   resistor needed (K1's own series resistance is 0Ω).
3. **DFPlayer PRO's `DACL` pin → amp's `INL` terminal; DFPlayer `GND` → amp `GND`** (the 3-pin
   `VOL_L | INL GND INR | VOL_R` input block on the XH-M543 board). **Do not use the DFPlayer's
   `L+`/`L-`/`R+`/`R-` pins here** — those are its own built-in speaker-level BTL output, meant to
   drive a bare speaker directly, not to feed another amp's line input; wiring them into `INL`
   would mismatch both signal level and topology. `DACL` is the chip's actual line-level DAC
   output (1Vrms swing per the DF1101S datasheet §3.4) — the correct signal for this path.
4. **No hardware shutdown/mute pin exists on this board.** The techtonics XH-M543 listing (₹289,
   the one actually in hand) and its product photos confirm the only terminals are: power in
   (`VCC`/`GND`), the 3-pin audio input above, two speaker outputs (`L`, `R`), and two volume
   trimpots (`VOL_L`, `VOL_R`). `config.h`'s `HORN_AMP_ENABLE_PIN` comment assumed a `SHUTDOWN`
   pin that this specific board doesn't expose. **Fallback: D4 (`HORN_AMP_ENABLE_PIN`, PA12) →
   IRLZ44N gate (or the LR7843 module), switching the amp's `VCC` line** — same 220-330Ω series
   gate resistor + 10kΩ pulldown pattern as §4/§5's LED and IR MOSFETs. This is power-side
   enable/disable instead of an IC mute pin, but functionally the same gate that
   `HORN_AMP_ENABLE_DELAY_MS` (150ms, still an invented placeholder per `docs/KNOWN_GAPS.md`)
   times against.
5. **Amp output (`L+`/`L-` on the XH-M543, the channel wired to `INL`) → Ahuja SUH-15 (8Ω)**, via
   2-core speaker wire through the gasketed gland into the horn's separate housing (ADR 0011).
   16-18AWG stock in hand is fine for the ~1A the amp draws at its software-limited 6-8W output.
6. **Amp `VCC`/`GND` → the IRLZ44N switch from step 4 → power bus** (§1). No buck needed — this
   board's spec (12-24V range, 2×50W at 12V) covers the 12.8-14.6V range with margin.

**Volume control — better news than originally thought.** The XH-M543's `VOL_L` trimpot sits
*after* the DFPlayer in the signal chain, so it's a real physical gain stage independent of
whatever volume the DFPlayer itself is set to — unlike a pure DFPlayer-only setup, you're not
purely at the mercy of an unknown value baked into the module's flash. **Turn `VOL_L` fully
counterclockwise (minimum) before first power-on**, trigger a test play, and bring it up
gradually while listening, rather than assuming any starting position is safe.

## 4. LED deterrence: cool-white + royal-blue via IRLZ44N

**4.0 Redesign decided 22 Aug (Cowork planning session) — supersedes the ×4/×2, 2-channel plan
below wherever it conflicts. Not yet reflected in `config.h`/`led.cpp`/`led.h`.**

Real constraint discovered same night: only 10 heatsink pucks in hand, against a much larger bare-LED
stock. Decision, reasoned from deterrence effectiveness / practicality / power (not from enclosure
CAD, which is not fixed):

- **10 LEDs total, all heatsinked (never run a 3W star bare — real field-reliability risk over a
  multi-day trial): 6 cool-white + 4 royal-blue.** Ratio 1.5:1, not the original BOM's 2:1 — still
  white-leaning (cool-white's phosphor hump overlaps the ~496nm rod peak most large-mammal targets
  use at night better than narrow royal-blue does) while keeping blue meaningfully present (hedges
  the ~30% non-nocturnal encounters, and doubles as spectral-diversity insurance against exact
  photoreceptor-tuning uncertainty).
- **4 independent channels, not 2**: white-left / white-right / blue-left / blue-right. Each color
  still has exactly one buck (2 bucks total, unchanged from the original BOM, already in hand) —
  the buck output splits into two matched parallel branches (left wing, right wing), each gated by
  its own IRLZ44N. White = 3 branches of 2-LEDs-in-series (2 on one wing's switch, 1 on the
  other's — see below); blue = 2 branches of 2-LEDs-in-series (1 per wing). Branches within one
  color are always 2-in-series, sized against the buck's dropout margin at a depleted ~10V pack —
  do not run 3 in series per branch, that's the real ceiling, not an arbitrary one.
- **Why 4 channels, not 2:** the actual evidence-backed deterrence lever is unpredictability, not
  raw brightness — real field literature on flashing-light deterrents (coyote/sheep strobe-siren
  trials, FoxLights, and a directly-relevant finding that elk/deer habituate fast to *stationary*
  deterrents) says varying pattern and color prevents habituation; a static "both wings, both
  colors, every time" burst does not. 4 independent channels let `led.cpp`/the bandit layer
  actually alternate side and color across triggers instead of firing identically every time.
  `ALERT_LED_PATTERN_ID` (already a placeholder in the MPU cognition layer, currently unwired) is
  the natural hook for this — implementing real pattern logic there is higher-value than any
  further LED-count increase.
- **Power/fuse check, real and not yet done — do this before wiring 10 LEDs:** 10 LEDs at ~2.24W
  each (700mA × ~3.2V typical for a 3W star) is ~22.4W if every LED fired simultaneously, versus
  ~13.4W for the original 6-LED plan the existing 6A fuse was sized against
  (`hardware/bom/procurement-status.md`'s 45.1W worst-case-peak / 1.11x-margin calculation). That's
  roughly +9W on top of the system's worst-case simultaneous peak (horn + LED + IR all firing at
  the top deterrence tier). **Re-run that worst-case-peak arithmetic with 10 LEDs before wiring
  them** and confirm the 6A fuse still clears the project's own 1.25x safety convention at a
  depleted pack — if not, it's a cheap fuse-rating bump, not a redesign, but it must be checked,
  not assumed.
- **Firmware work needed before this is real** (next VS Code/Sonnet session, one-at-a-time Bridge
  discipline as always): add `LED_WHITE_RIGHT_PIN`/`LED_BLUE_RIGHT_PIN` to `config.h` (D3/D8, both
  confirmed free), extend `led_channel` in `led.h` from `{kWhite, kBlue}` to 4 values (or a
  color×side pair), extend `led.cpp`'s `channel_state` array from 2 to 4 instances, and update
  `bridge_handlers.cpp`/`schema.md`'s `drive_led` channel field to address 4 channels. None of this
  is wired live yet — same commented-out-`Bridge.provide()` discipline applies to any new
  registration.

Everything below (buck sizing, MOSFET gate pattern, wire gauge) is unchanged and still correct —
only the channel count and per-branch LED count change. Read it per-branch: wherever it says "the
LED string," that's now "one 2-LED-in-series branch," repeated 3× for white and 2× for blue.

**Per color channel** (repeat for white and blue, using D5/D6 respectively):

1. **XL4015 buck driver, battery bus → LED string.** Set the buck's output voltage/current to
   match the LED string's forward-voltage/current spec (wire the LEDs in the series/parallel
   configuration your buck driver's rated output current supports — a 3W LED typically runs
   ~700mA at ~3.2-3.4V forward voltage; check the actual star datasheet you received before
   setting the trimmer, since "3W" alone doesn't fix the exact Vf/If). Mount each LED star on a
   heatsink puck with thermal adhesive tape — these get genuinely warm at 700mA and the puck is
   there for a reason, don't skip it.
2. **IRLZ44N as a low-side switch between the LED string's return and ground.** IRLZ44N is a real
   logic-level MOSFET — datasheet-confirmed gate threshold `Vgs(th)` ≈1-2V, and it's specifically
   designed for direct low-voltage gate drive (down to and below 5V) rather than the ~10V a
   standard power MOSFET needs. At the UNO Q's 3.3V GPIO drive it's fully in logic-level territory
   and will switch cleanly at these LED currents (≤~1.4A per channel across 2 LEDs) — `Rds(on)`
   at 3.3-5V gate drive is in the tens-of-milliohms range per the datasheet, negligible heating at
   this current. ([IRLZ44N datasheet, thierry-lequeu.fr mirror](https://www.thierry-lequeu.fr/data/IRLZ44N.pdf))
   Wiring: LED string cathode → MOSFET drain; MOSFET source → ground bus; MOSFET gate ← D5 (or D6)
   through a **220-330Ω series gate resistor** (standard practice, limits inrush into the gate
   capacitance — not in the BOM by name but any resistor from the existing kit in that range
   works) and a **10kΩ pulldown resistor from gate to source** (holds the LED firmly off during
   MCU boot/reset, before `led_init()` has run — without this, an undriven gate can float and
   flicker the LED on briefly at power-up).
3. **Buck driver output → LED string**: 22AWG 2-core is right for this run (≤1.4A per channel,
   well inside 22AWG's margin over a short in-enclosure run).

## 5. IR illuminator: 940nm board via its own XL4015 buck

Per the BOM's flagged finding (`procurement-status.md` §6 Buck/regulation audit): the VISTORA
48-LED IR board (ASIN B0H2DQ9DVK) states a **single fixed Input Voltage: DC12V** (not a range),
drawing 300mA — the battery bus's 14.6V absorption peak exceeds this by ~22%, a real overvoltage
risk to a board with no stated input tolerance margin. This is why one of the spare XL4015 bucks
is earmarked specifically for this board, set to output ~12V.

1. **Battery bus → dedicated XL4015 buck (set to 12V output, verified by multimeter before
   connecting the IR board)** → IR board's 12V input.
2. **D7 (`IR_ILLUMINATOR_PIN`, PB2) → gate of an IRLZ44N low-side switch** on the IR board's
   ground return, same gate-resistor + pulldown pattern as §4 — or use the **LR7843 module**
   already in hand (pre-built screw-terminal MOSFET switch) here instead of a bare IRLZ44N, since
   `procurement-status.md`'s own Flag #3 suggests this exact position as the best fit for it (it's
   a better match for the "no PCB fab" constraint than hand-wiring another bare IRLZ44N).
3. `IR_PULSE_MAX_MS` is 500ms with a 5s minimum interval (config.h lines 394-398) — sized to keep
   duty under 10% at max pulse width specifically to stay inside the gate MOSFET's thermal limit,
   per the comment in config.h. Nothing to wire differently for this, just worth knowing why those
   numbers are what they are before you consider changing them.

## 6. Before first power-on — checklist

1. Multimeter-verify the XL4015 buck outputs (main charge-path buck if wired, LED bucks, IR buck)
   **with no load connected**, before connecting anything downstream — this is the same discipline
   `procurement-status.md` already specifies for the charge-side XL4015.
2. Confirm fuse and switch are both in the positive leg only, ground bus is common and unfused.
3. Turn the XH-M543's `VOL_L` trimpot to minimum before the amp's MOSFET enable (D4/IRLZ44N) is
   ever switched on (§3) — it's the one real physical volume control in this signal path.
4. Confirm every IRLZ44N (or LR7843) gate has its pulldown resistor before power-on — an
   undriven/floating gate on a logic-level MOSFET can partially turn on unpredictably. This now
   includes the horn's amp-enable MOSFET (§3 step 4), not just the LED/IR channels.
5. Once everything above is wired and the bench power source (§1c) is connected: flash with
   `FIRE_TEST_HARNESS 1` (same procedure as the 22 Aug bare-board session,
   `docs/eletect-x-applab-notes.md`) and test each actuator with the `1`/`2`/`3`/`4` console
   commands — this is the fastest path from "wired" to "confirmed working," no new firmware
   needed. Watch/listen for each fire this time, since last session only had the console ack to
   go on.
6. Update `hardware/references/UNO_Q_PINOUT_REFERENCE.md`'s wiring-status table (D2/D4/D5/D6/D7
   from **U** to **W**) as each one is confirmed — keep that table current, same discipline it
   already documents for itself.

Sources: [IRLZ44N datasheet (thierry-lequeu.fr mirror)](https://www.thierry-lequeu.fr/data/IRLZ44N.pdf), [Automotive wire amperage capacity chart, WiringProducts](https://wiringproducts.com/pages/wire-amperage-capacity-chart)
