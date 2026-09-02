# Proposal: LED/horn per-fire burst length, cooldown, and encounter-aware cadence

- **Status:** proposal — not decided, needs a bench pass before any constant changes
- **Date:** 2026-09-02
- **Owns no code yet.** The eventual decision lands as an amendment to ADR 0014 (burst shape /
  duration) and as new companion values alongside ADR 0017 (encounter-window / cadence). This file
  does **not** modify ADR 0017 or 0014; it collects the open question and a test plan so the
  decision can be made on data.

## Why this exists

Three threads converge on one unresolved question — *how long should a single deterrence burst
run, how soon may the next one fire, and should that interval depend on where we are in an
encounter* — and none of them settles it:

1. **ADR 0014 §E.3** explicitly deferred it: *"LED and horn active fire-duration per detection …
   is likewise a separate follow-up. ADR 0017 … already covers the relevant part … Longer is not
   automatically better (habituation; battery/thermal cost; horn hearing-safety near homes)."*
2. **ADR 0017** retunes `HABITUATION_WINDOW_S` (the "same encounter" memory) but deliberately
   leaves Question B — proactive/again-firing cadence — open, gated on a presence signal the
   device does not have.
3. **The 1 Sept `KNOWN_GAPS.md` addendum** quantified that every live deterrence fire currently
   requests `PROTOCOL_DURATION_MS_MAX` and is clamped MCU-side to the burst cap, so in the field
   the LED runs a **full 10 s** per fire and the horn a **full 3 s**, blocking the MCU main loop
   (geophone + LoRa starved) for that whole time.

The behavioural synthesis added to `docs/research/elephant-deterrence-behavioral-science.md` §7
gives the missing half of the reasoning. This proposal joins them.

## Current values (all in `device/mcu/src/config.h` unless noted)

| Constant | Value | Effect in the field today |
|---|---|---|
| `LED_BURST_MAX_MS` | 10000 | Every wing fire runs a full **10 s** strobe (MPU requests max, MCU clamps) |
| `LED_COOLDOWN_MS` | 20000 | 20 s minimum between wing fires |
| `HORN_BURST_MAX_MS` | 3000 | Every horn fire runs a full **3 s** |
| `HORN_COOLDOWN_MS` | 30000 | 30 s minimum between horn fires |
| `IR_PULSE_MAX_MS` | 500 | IR pulse — not in scope here, already short and gated by ADR 0019 |
| `IR_MIN_INTERVAL_MS` | 5000 | — |
| `TIER_DURATION_MS` (`cognition/config.py`) | 65535 | The "ask for the max, let the MCU clamp" request value, identical for all three tiers |

`TIER_DURATION_MS` being a single max-value constant is why **no tier differs in burst length
today** — `cognition/config.py`'s own comment calls this out as a known limitation.

## The case for change

### Burst length — the 10 s LED strobe is too long, on four independent grounds

1. **Behavioural (habituation).** §7.3: a long, *predictable* stimulus onset is what a
   comparator-style habituation mechanism conditions to. A 10 s continuous strobe is a large,
   predictable block of "same thing happening"; the aversive/novel content is concentrated in the
   **onset** (§7.4 — abrupt onset drives the flight response, sustained presence drives
   tolerance/curiosity). Most of those 10 s are doing little deterrence work and some are actively
   teaching the animal the light is endurable.
2. **MCU real-time (the big one).** `KNOWN_GAPS.md`: the LED fire blocks `loop()` for the full
   clamped duration, so geophone samples and inbound LoRa frames are silently dropped for **10 s
   per wing fire** — "high severity if a real elephant event and a deterrence burst overlap in
   time, exactly the case that matters most." Cutting the burst to ~2.5 s cuts that starvation
   window by ~75% for free, ahead of the proper fix (non-blocking actuator state machine).
3. **Thermal.** The LED stars run at `LED_GAIN_MAX_PCT` = 100 % on every tier now (ADR 0014 §E.3).
   A 10 s max-duty burst puts materially more heat into the wing than a 2.5 s one, and the
   in-season encounter model (activity-timing doc §3.3: multi-hour presence, repeated triggers)
   means bursts stack over a night. Junction/heatsink temperature under that regime is unmeasured
   (see test plan).
4. **Battery.** ADR 0012's power budget vs. 10-day unattended autonomy is already an open
   `KNOWN_GAPS.md` item with "actuator duty cycle not yet confirmed." Burst length is a linear
   term in actuator energy per encounter.

**Nothing argues *for* keeping 10 s.** The one historical reason to run a long burst — "keep the
light on long enough to also grab camera evidence" — is dead: Finding 2 of
`docs/qa/night-ir-led-characterisation.md` shows our own strobe does not blind our own camera, so
evidence capture overlaps the burst regardless of its length.

### Horn length — 3 s is already short; leave it, or trim to ~2 s

The horn is bounded by ADR 0016's hearing-safety cap for people and livestock near the unit, and
3 s is already modest. A small trim to ~2 s would cut the ~3.15 s MCU stall and save energy with
negligible deterrence loss (the bee/predator-growl content that actually matters, §2, registers in
well under a second), but this is low-priority next to the LED change and should not be made
without the same bench check.

### Cooldown — 20 s / 30 s is too coarse for an active encounter

The project owner has green-lit reducing the cooldowns. The behavioural reason to: §7.3 #4 —
**dishabituation.** A returning trigger 20–40 s into an encounter is an opportunity to present a
*varied* stimulus while the animal is still reacting; a long fixed cooldown makes the device sit
mute through exactly that window. But a naive global reduction trades directly against thermal and
battery (above), so the proposal is not "make the number smaller" — it is:

### Encounter-aware cadence — make the minimum re-fire interval a function of encounter state

Keep the MCU hard cooldown as a **safety floor** (thermal/welfare — it must not depend on
MPU-side logic being correct), but lower it, and layer an **MPU-side adaptive interval** on top,
driven by the bandit's existing encounter context:

- **First contact / isolated trigger** (`habituation_context()` bucket 0): longer interval — the
  animal may simply leave; no need to hammer. Roughly today's behaviour.
- **Escalated repeat** (bucket ≥ 1, i.e. `escalation_floor()` already lifted): shorter interval,
  so a persistent animal gets a brisker, more varied sequence of escalating responses instead of
  20 s gaps of silence. This is the cadence analogue of what the tier ladder already does on
  intensity.
- **Never** a fixed timer with no trigger (that is ADR 0017 Question B, still correctly gated on a
  presence signal the device lacks — this proposal does not reopen it). Every fire here is still
  reactive to a real MCU event; only the *minimum spacing* between reactive fires changes.

This keeps the welfare ceiling (bounded bursts, hard cooldown floor, three-tier cap, stop-on-
retreat intent — §7.5) intact while making the cadence fit the encounter.

## Proposed values — provisional, pending the bench pass

Ranges, not numbers. The bench protocol picks the final value inside each range; the reasoning is
recorded so the choice is honest about what is data and what is judgement.

| Constant | Today | Proposed range | Basis |
|---|---|---|---|
| `LED_BURST_MAX_MS` | 10000 | **2000–3000** | onset-dominated deterrence (§7.4); 75 % cut to MCU starvation; thermal/battery headroom |
| `HORN_BURST_MAX_MS` | 3000 | **2000–3000** (likely unchanged) | already within ADR 0016 safety cap; content registers <1 s |
| `LED_COOLDOWN_MS` (hard floor) | 20000 | **6000–10000** | thermal recovery of the wing between max-duty bursts — *this is the number the bench pass most needs to set* |
| `HORN_COOLDOWN_MS` (hard floor) | 30000 | **10000–15000** | amp thermal + ADR 0016 nuisance-noise-near-homes judgement |
| MPU adaptive interval, first contact | n/a (fixed 20 s) | **~15–25 s** | ≈ status quo for the common case |
| MPU adaptive interval, escalated repeat | n/a | **~6–10 s** (≥ hard floor) | brisker escalation for demonstrated repeat offenders (§7.2, §7.3) |
| `TIER_DURATION_MS` | 65535 (all tiers) | keep as max-request, OR split per tier if bench shows tier-specific burst length matters | `cognition/config.py` limitation note |

## Bench thermal / battery-sag protocol — this is the deliverable that unblocks the decision

Attended bench session, device on the real battery + solar input, real LED wings and horn, ambient
logged. **No live animal, no field deployment.** Owner present (actuator change → same hard safety
rule as every reflash on this project).

### Equipment
- Thermocouple or IR thermometer on: each LED wing heatsink, the LED MOSFET(s), the horn amp.
- Battery pack voltage + current logged at ≥ 1 Hz (INA-class shunt or a bench DAQ).
- Ambient temperature + a fixed clock reference.
- The `night_char.py`-style harness extended with a `cadence` command, or an equivalent, that can
  fire `drive_led` / `drive_horn` at scripted burst lengths and intervals over the Bridge.

### Test matrix

**T1 — single-burst thermal step response.** From cold, fire one LED wing at max gain for
{2 s, 3 s, 5 s, 10 s}. Record peak heatsink/MOSFET temperature and time-to-return-to-ambient+2 °C.
Gives the thermal cost curve vs. burst length and the *natural* cooldown the hardware wants.

**T2 — sustained encounter simulation (the worst case that matters).** Using the activity-timing
numbers (in-season night, ~5 h presence, repeated triggers): script a 60–90 min run of
tier-2/tier-3 fires — both wings, max gain, proposed burst length — at the proposed escalated-repeat
cadence. Log wing/MOSFET/amp temperature throughout. **Pass:** steady-state temperature stays
inside the LED stars' and MOSFET's continuous-rating headroom with margin (define the °C number
against the actual parts before the run). **Fail:** temperature climbs monotonically or crosses the
margin → lengthen the hard cooldown floor and/or shorten the burst, re-run.

**T3 — battery sag.** During T2, track pack voltage and coulombs drawn. Extrapolate to a full
in-season night (worst plausible encounter count) and to the ADR 0012 10-day autonomy budget with
that per-night actuator load added. **Pass:** projected state-of-charge stays above the ADR 0012
reserve through the worst-case night with no solar. **Fail:** revisit burst length / cadence /
tier-3 frequency, or flag as a power-budget item for ADR 0012.

**T4 — cadence vs. MCU real-time.** With the shorter burst and shorter cooldown loaded, run a
concurrent geophone-active test: confirm the geophone/LoRa starvation window per fire has dropped
proportionally and that back-to-back fires at the new cadence do not stack into a longer effective
blackout than 10 s (they must not — that would be a regression).

### Outputs
- Final values for every row in the proposed-values table, each tagged data-backed or judgement.
- A written thermal margin statement for the LED wing at the chosen burst/cadence.
- A power-budget line for ADR 0012's open autonomy item.
- Whichever of these the data supports: an ADR 0014 amendment (burst length), a companion-constant
  note for ADR 0017 (cadence), and any `cognition/config.py` change to make `TIER_DURATION_MS`
  per-tier.

## Explicitly out of scope

- **Proactive timer-based re-firing with no trigger** — ADR 0017 Question B, still gated on a
  presence signal. Not reopened here.
- **Non-blocking actuator state machine** — the real fix for MCU starvation (`KNOWN_GAPS.md`).
  This proposal reduces the blocking window as a stopgap; it does not remove it.
- **Horn content** (bee-buzz / predator-growl / conspecific alarm) — ADR 0016 follow-up, tracked
  in the behavioural doc §7.7 #5.
- **Any change tonight.** Every value here needs the bench pass and a reflash with the owner
  present.
