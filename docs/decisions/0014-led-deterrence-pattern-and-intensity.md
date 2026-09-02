# ADR 0014: LED deterrence pattern + intensity axis, wired into the bandit escalation ladder

- **Status:** proposed
- **Date:** 2026-09-01

## Context

`CONTEXT.md` 3 freezes "irregular strobe" as the visual-deterrence design and `CONTEXT.md` 4 freezes
"contextual-bandit deterrence (never-repeat, stop-on-retreat)" as the policy layer above fusion. Neither
has ever been fully implemented on the LED side, and until tonight (31 Aug - 1 Sept build call) the gap
was not fully mapped. It now is:

1. **`led.cpp`'s `drive_led()` fires a single steady on/hold/off burst.** No flicker, no pattern, no
   timing variation exists in firmware today — confirmed by the 31 Aug camera-diff sweep, where every
   `drive_led` call was one continuous 1500 ms pulse.
2. **The wire schema's `pattern_id` (`schema.md`) was repurposed 30 Aug from an intended
   strobe-selector to a channel-selector** (0 = left wing, 1 = right wing), to match the simplified
   2-wing/2-MOSFET build that replaced the never-built 4-channel/10-LED design. `pattern_id`'s original
   meaning ("which strobe pattern to run") is now stale documentation, not implemented behavior.
3. **The escalation ladder (`cognition/config.py`'s `DETERRENCE_TIERS`) does not actually vary LED
   output at all between tiers** — `led_pattern_id` is hardcoded `0, 1, 0` across Tier 1/2/3 (channel
   only), and `drive_led`'s wire schema has no `gain_pct` field at all, unlike `drive_horn`. The MCU
   internally always requests `LED_GAIN_MAX_PCT` (100%) regardless of tier — confirmed in
   `bridge_handlers.cpp` and `schema.md`'s "Actuator gain defaults" section, which documents this as a
   deliberate but incomplete decision. **The horn has the identical problem**: `gain_pct` is on the wire
   and nominally varies 25/45/100% by tier, but `docs/KNOWN_GAPS.md` (line ~62) confirms it was never
   wired to a physical volume control — the DFPlayer always plays at its stored default level regardless
   of what's requested. Net effect: **today's 3-tier escalation produces zero physically-detectable
   difference on either LED or horn output** — the only thing that actually changes between tiers is
   which LED wing fires and whether IR fires (and IR is 940nm, non-deterrent by design — invisible to
   the animal). This was not previously documented as one finding; it is the real, combined gap this ADR
   addresses.
4. **`hardware/WIRING_GUIDE.md` §4.0 already names the right fix**, from the 22 Aug 4-channel LED
   redesign write-up (not yet built in firmware): *"the actual evidence-backed deterrence lever is
   unpredictability, not raw brightness... varying pattern and color prevents habituation...
   `ALERT_LED_PATTERN_ID` is the natural hook for this — implementing real pattern logic there is
   higher-value than any further LED-count increase."* This ADR is that implementation, scoped to the
   real 2-wing/2-MOSFET hardware in hand rather than the unbuilt 4-channel design.
5. **The anti-habituation *policy* layer already exists and is well-architected** — `cognition/bandit.py`
   implements epsilon-greedy tier selection with a deterministic escalation floor keyed to recent-repeat
   count (`habituation_context()`/`escalation_floor()`), so a returning animal is guaranteed a higher
   floor, not a repeat of an ineffective response. This is a real, evidenced design choice, not
   over-engineering: `docs/research/competitor-analysis-aniders.md` cites an independent field study
   (Wangdi 2023, Bhutan, 30 PIR + 2 AIR units, one year) where a competitor's **static** 40-pattern
   randomization still decayed in effectiveness over the trial — direct field evidence that
   unpredictability alone, without outcome-adaptive learning, is not sufficient. EleTect X's bandit
   already does the harder, adaptive thing. **What's missing is not the policy, it's the actuator having
   anything real to vary.** A perfect escalation policy choosing between three physically-identical LED
   outputs cannot produce anti-habituation behavior no matter how well it's tuned.
6. **Caution, stated plainly so it isn't oversold**: "never let them habituate" is not a claim this
   device can make honestly. `cognition/bandit.py`'s own docstring states stop-on-retreat "is NOT
   implemented and is not implementable today" — there is no sensor that tells the device an animal
   actually left. `proxy_reward()` (time-until-next-trigger) is an explicitly unvalidated proxy, not a
   measured deterrence outcome — an animal leaving for unrelated reasons scores identically to one
   actually deterred. And the specific "habituation within days-to-weeks" claim already circulating in
   `HANDOVER.md`/`README.md`/the pitch doc has no citation anywhere in this repo — unlike the seismic
   architecture's fully-cited literature review, this claim should not go into DFO or contest materials
   without a real source. This ADR closes the "the actuator can't even express a different response"
   gap; it does not and cannot close the "we've proven elephants don't habituate to this" gap — that
   needs field outcome data this device does not yet collect.

## Decision

Extend the LED actuation path with a real pattern axis and a real intensity axis, both driven by the
existing bandit tier ladder, using headroom that already exists in the current 2-wing hardware and
firmware — no new hardware, no new GPIOs, no change to `rule_gate.cpp`.

**A. Wire schema (`schema.md`, bump `SCHEMA_VERSION`):**
`drive_led(schema_version, channel: uint8, pattern_id: uint8, gain_pct: float, duration_ms: uint16) -> bool`
Splitting `channel` and `pattern_id` into two fields (rather than continuing to overload one byte)
removes the ambiguity the 30 Aug rename introduced, and adding `gain_pct` closes the intensity gap using
plumbing that **already exists and works** — `led.cpp`'s `led_request{channel, duration_ms, gain_pct}`
and `gain_to_duty()` already drive real `analogWrite` PWM duty; the only missing piece is the wire field
and `bridge_handlers.cpp` passing it through instead of hardcoding `LED_GAIN_MAX_PCT`. This is a small,
mechanical change, not new MCU driver logic.

**B. Pattern set (`led.h`/`led.cpp`), a deliberately small, named set — not an open-ended DSL:**
- `PATTERN_STEADY` (0) — today's behavior, on/hold/off. Default / fallback.
- `PATTERN_SLOW_PULSE` (1) — 2 on/off cycles spread across `duration_ms`, ~50% duty.
- `PATTERN_FAST_STROBE` (2) — rapid on/off within `duration_ms`, ~6-8 Hz.
- `PATTERN_RANDOM_FLICKER` (3) — irregular inter-flash gaps within `duration_ms`, seeded from
  `micros()` at call time (no new wire complexity — self-contained on the MCU). This is the literal
  "irregular strobe" `CONTEXT.md` already specifies.
Implemented as timing logic **inside** `drive_led()`'s existing blocking window (replacing the single
`delay(duration_ms)` with a flash-sequence loop that still totals `duration_ms`). Per the 1 Sept
`KNOWN_GAPS.md` finding, every LED fire already blocks the MCU's main loop for the full clamped duration
regardless of pattern — a strobe implemented this way adds **zero new blocking cost** beyond what already
exists today. It does not make the already-open geophone/LoRa-starvation gap worse; it does mean that gap
matters more, and whoever picks up "make actuator fires non-blocking" next should know a strobe
implementation is now riding on top of it.

**C. Channel diversity via MPU-side orchestration, no new MCU work needed:** left/right sequencing
(alternating "chase," simultaneous both-wings, staggered) is already exercisable today by `reflex_loop.py`
issuing two `drive_led` calls with different timing — the 31 Aug sweep's own `seq_LR`/`seq_RL`/`simul`
test conditions already prove this path works. Tier config should use this alongside the new
per-call pattern/gain axes, not instead of them.

**D. Tier ladder (`cognition/config.py`), give each tier a real, distinct signature:**
Example allocation (final numbers need a bench pass, not decided here): Tier 1 = `PATTERN_SLOW_PULSE`,
left wing only, moderate gain. Tier 2 = `PATTERN_FAST_STROBE`, alternating both wings (MPU-orchestrated),
higher gain. Tier 3 = `PATTERN_RANDOM_FLICKER`, simultaneous both wings, `LED_GAIN_MAX_PCT`. Horn's
already-flagged unwired gain issue (`KNOWN_GAPS.md` ~line 62) should get the equivalent fix in the same
pass, since it's the identical bug on the other actuator — tracked here as a companion item, not expanded
into its own ADR.

### E. Real dual-wing design, revisited 1 Sept — user request + evidence check against the ADR's own citation

User's ask, verbatim intent: use max brightness, fast strobe, and both wings working together in
different patterns/movements to "mimic movement and threat" and deter more effectively. Worth checking
against real evidence before designing to it, since the strongest citation this ADR already leans on
turns out to describe a different kind of device than what's being asked for.

**What the actual cited study did, read closely for the first time this pass:** Adams, Mwezi & Jordan
(2020, *Oryx*, "Panic at the disco") did not test one strobing device's brightness or strobe frequency —
it tested a **barrier of 6-13 separate solar LED units, spaced 10m apart along a field edge, each
flashing continuously in one fixed color, with color rotated weekly across the whole barrier** (not
per-unit, not pattern-shape rotation). Their own stated mechanism: the array "simulates torches," which
they hypothesize elephants associate with human patrol presence, and a multi-light barrier "appears more
threatening than a single directional spotlight." The real numbers (already cited correctly elsewhere in
this repo): 75% prevention in treatment fields vs. 30% in controls, *z*=4.59±1.66, p<0.05, out of 107
recorded elephant approaches. A second real citation, newly found this pass — Assam, India, 2006-2009
(via [conservationevidence.com](https://www.conservationevidence.com/actions/2496)): spotlights aimed at
elephants' eyes moderately reduced crop damage probability, **but combining the spotlight with noise
reduced its effectiveness relative to the spotlight alone** — a real caution for this device's own
escalation ladder, which already stacks LED + horn at higher tiers; not something to change tonight, but
worth a line in this ADR's Consequences so it isn't invisible.

**Honest gap, stated plainly rather than papered over**: neither of these citations, nor a targeted
search for elephant-specific flicker-fusion/temporal vision data (came back empty — a dedicated MDPI
review of elephant sensory perception explicitly scoped itself to olfactory/auditory and did not cover
visual flicker perception at all), supports "fast strobe frequency" or "phase-offset movement mimicry
between two lights" as an independently evidenced elephant deterrence mechanism. What *is* evidenced is
weaker but real: more flashing points, spread further apart, reads as more threatening than one — which
is a real point in favor of using **both** wings rather than one, but says nothing about strobe Hz or
choreographed phase relationships. The rest of this device's own anti-habituation reasoning
(Montgomery et al. 2021's randomization recommendation, already cited; Adams et al.'s own weekly color
rotation) supports **unpredictability** as the active ingredient, not any specific frequency or motion
pattern — so "vary pattern/timing/wing unpredictably" is well-grounded; "fast = more threatening" or
"this specific phase pattern reads as an approaching animal" is an engineering hypothesis this repo has
no citation for, and should not be written into contest/DFO materials as a proven mechanism, same
discipline as this ADR's existing habituation-claim caution above.

**Update, same day — real practitioner testimony changes the strobe-specific gap above.** The user
reports DFO (the Kothamangalam forest department this trial is fielded with) told them directly that
fast strobe lights are useful for elephant deterrence, and that DFO staff already carry strobe-capable
emergency lights/torches specifically for this purpose when entering the forest. **Recorded honestly as
what it is**: verbal field-practitioner testimony from the actual partnering forest department, dated
1 Sept 2026, relayed via the project owner — not a controlled study, no measured effectiveness number
attached to it (DFO's own torches are an operational field heuristic, not something they've published a
trial on either, same evidentiary category as the Assam spotlight practice above). But it is real,
directly relevant, and more locally specific than either paper-based citation above: it comes from the
exact department this device is being trialed with, in the exact forest system (Kerala), about the exact
technique (strobe) already in active field use by people who do this for a living. **This closes most of
the "fast strobe frequency" gap flagged above** — not with a controlled-trial number, but with the kind
of practitioner validation this repo already treats as real evidence elsewhere (e.g. the Assam spotlight
practice). What it does *not* validate: any particular phase relationship between two lights, or a
specific Hz — DFO's testimony is about strobe as a technique, not about `SWEEP` vs `PULSE_BOTH_SYNC`
timing specifics, so that part of the honest-gap caution above still stands.

**Design updated accordingly — `PATTERN_FAST_STROBE` becomes the anchor pattern across the ladder,
not `PATTERN_SLOW_PULSE`,** since strobe now has real, locally-relevant field backing that slow-pulse
never had. Escalation still comes from wing-count and gain, not from swapping to an unvalidated pattern
family, which is a better-grounded design than the original table below.

**"Max brightness" is already in use, not something being held back.** Tonight's real hardware pass
(7-fire verification, `HANDOVER.md`) confirmed Tier 3 already fires `RANDOM_FLICKER` at `LED_GAIN_MAX_PCT`
= 100% gain on one wing. There is no unused brightness headroom on a single LED channel today — going
brighter per-channel means pulsed overdrive above the stars' continuous rating, which this ADR's
Alternatives section already declined to adopt for lack of a real datasheet pulsed-current figure, and
that conclusion is unchanged by tonight's findings. **The actual lever still on the table is using the
second wing at the same time as the first — real additional light output, not a brightness trick.**

**Two designs, genuinely different in cost and risk — both real, only one is a same-day option:**

1. **Sequential both-wing tiers, MPU-orchestrated, no MCU/firmware change, no reflash.** Every tier fires
   *both* wings instead of one — `reflex_loop.py` issues two `drive_led` calls back to back (left then
   right, or an alternating repeated pair for a "sweep" feel), exactly the mechanism Decision C above
   already established works (31 Aug's `seq_LR`/`seq_RL` conditions). Bound by tonight's own measured
   per-call overhead (13-35ms) and the fact `drive_led` blocks per call — this is genuinely sequential,
   not simultaneous, and should be described that way, not oversold as "both wings flash together." Real
   Python change in `cognition/config.py`/`reflex_loop.py`, host-testable, zero new hardware risk.
   Directly addresses "both wings working together" and gives a real (if modest, sequential-not-
   simultaneous) spatial-movement cue consistent with the barrier-array logic in the actual citation.
2. **True single-call simultaneous dual-wing** (both `LED_WING_LEFT_PIN`/`LED_WING_RIGHT_PIN` toggled
   together inside one MCU-side blocking loop). This is real, bounded firmware work — `led.cpp`'s
   existing blocking pattern loop already does per-channel timing; extending it to drive a second pin in
   the same window is the same "zero *additional* blocking cost" principle Decision B already
   established, not a new architecture.

**Decision: build option 2 — real, firmware-level, simultaneous dual-wing.** User's explicit call, made
with the timeline deliberately set aside: design for actual field effectiveness in a forest deployment,
not for what fits in tonight's reflash window. Sequential (option 1) is a real fallback if bring-up runs
out of time, but it is not the target design — a second, real reason beyond perceptual effect: **two
sequential single-wing calls of duration D block the MCU for ~2D total (double the geophone/LoRa-
starvation window `KNOWN_GAPS.md` already flags), while one dual-wing call of duration D blocks for D**
— firmware-level is strictly better on this axis too, not just visually.

**E.1 Named dual-wing patterns (extends Decision B's set, same "small, named set, not a DSL" principle) —
revised to anchor on `PATTERN_FAST_STROBE`'s ~6-8Hz timing given the DFO practitioner input above, not
`PATTERN_SLOW_PULSE`'s:**
- `PATTERN_SWEEP` — the two pins driven in antiphase at `PATTERN_FAST_STROBE`'s rate (left on/right off,
  swap, repeating fast, not slow) — a real, if modest, apparent-movement cue on top of DFO-validated
  strobe timing, not a claim of realistic locomotion mimicry.
- `PATTERN_PULSE_BOTH_SYNC` — both pins driven together, in phase, at `PATTERN_FAST_STROBE`'s rate —
  genuinely doubles total light output over a single-wing fire at the same per-channel gain, the real
  "brighter" lever identified above, and the most literal doubled version of what DFO says already works.
- `PATTERN_FLICKER_BOTH_INDEPENDENT` — both pins run `PATTERN_RANDOM_FLICKER`'s irregular-gap logic with
  **independently seeded** flash timing (not mirrored) — reads as two independent erratic light sources
  rather than one bigger light, the closer analogue to the Adams et al. mechanism (multiple separate
  threats/torches). Kept irregular rather than strobe-anchored deliberately — this is the ladder's
  unpredictability lever (Montgomery et al. 2021), a different job than the other two.

**E.2 Revised tier ladder — balances "maximize effectiveness" against the device's own existing
anti-habituation design, not a naive "always fire everything at once":** the bandit's escalation-floor
logic (`cognition/bandit.py`'s `escalation_floor()`, already built) exists specifically to reserve the
strongest, most varied response for animals that keep coming back, rather than exhausting the full
repertoire on the very first, possibly-borderline trigger — collapsing every tier into "always max
dual-wing" would work against that design and risks faster habituation for repeat animals by removing
escalation headroom entirely (Goodyear & Schulte 2015, Khorozyan & Waltert 2019, both already cited in
`docs/research/elephant-deterrence-behavioral-science.md`, on how fast fixed max-intensity stimuli
habituate). Revised allocation:
- **Tier 1** (first/isolated trigger): single wing, **`PATTERN_FAST_STROBE`** (changed from
  `PATTERN_SLOW_PULSE` — strobe now has real DFO practitioner backing that slow-pulse never had, so it's
  the better-grounded default response even at the mildest tier), moderate gain. Proportionate first
  response, preserves headroom, keeps nuisance/household-proximity risk (ADR 0016) low for the common
  case.
- **Tier 2** (repeat within the habituation window): `PATTERN_SWEEP` (fast-strobe-rate antiphase), both
  wings, higher gain — first use of real dual-wing, adds the apparent-movement cue on top of DFO-validated
  strobe timing, still short of maximum.
- **Tier 3** (persistent repeat / escalation floor forces top tier): rotate between
  `PATTERN_PULSE_BOTH_SYNC` (doubled DFO-validated strobe, both wings synchronized, maximum literal
  interpretation of "what DFO says works") and `PATTERN_FLICKER_BOTH_INDEPENDENT` (maximum
  unpredictability, per Montgomery et al. 2021) — both at `LED_GAIN_MAX_PCT`, both wings. Execution
  session's call whether this rotation piggybacks on the bandit's existing exploration mechanism or is a
  simple alternation; either way, don't collapse Tier 3 to a single fixed pattern — the whole point of
  this slot is being the least predictable, highest-output response, and a single fixed "maximum" pattern
  fired identically every time is exactly the failure mode Montgomery et al. 2021 warns against.

This uses the full physical capability of the hardware at the point in the ladder where it earns its
real evidentiary support (more/varied light sources reading as more threatening) while keeping the
existing escalation structure's actual anti-habituation logic intact — serving "maximize deterrence" and
"never let them habituate" as one coherent design, not two competing asks.

**Honest bound, restated so it isn't lost in the pattern-design detail above**: DFO's testimony closes the
"is strobe a real technique" gap, not the "does this exact phase relationship work" gap — none of
`SWEEP`, `PULSE_BOTH_SYNC`, or `FLICKER_BOTH_INDEPENDENT`'s *specific* phase/timing choice is validated
by any citation, elephant-specific or practitioner. The evidence supports "strobe, and more/varied
flashing points, beat one steady light" in general; the exact three phase relationships above are a
reasoned engineering design built on that finding, not a proven mechanism. **And no combination of real
citations plus practitioner testimony adds up to "elephants will not enter this area" as a guarantee** —
every real number this repo has cited (75% vs 30%, Adams et al.; the Thuppil & Coss growl-playback range
57-100%; DFO's own torches presumably not formally measured at all) is a probability of deterring a given
approach, not a claim of total exclusion, and habituation risk is exactly why this device escalates
rather than fires one fixed maximal response forever. Say this plainly in any contest/DFO materials or
in response to a "will this keep elephants out entirely" question — overstating it is a real credibility
risk with the same DFO partner whose field expertise this design now leans on.

**Physical movement (literal, not phase-mimicked) is out of scope, noted rather than silently dropped**:
mounting the LED wings on an actuated/rotating fixture would be a more literal way to create real motion
parallax, but there is no motor/servo in this device's BOM or `hardware/` design — a hardware redesign,
not a firmware change, and not proposed here.

**Implementation, for the execution session**: schema bump (`drive_led` gains a way to address "both,"
either a `channel` enum value or a separate dual-wing entry point — execution session's call, not
prescribed here), `led.cpp`/`led.h` extended to drive two pins within the existing blocking window for
the three new pattern IDs, `bridge_handlers.cpp` pass-through, `cognition/config.py` tier reallocation
per E.2, new host tests (`tests/test_led`) for all three patterns' pin-toggle timing, then reflash +
supervised physical bring-up — same hard safety rule as every other actuator change on this project. Not
implemented in this planning session, per the project's own session-continuity protocol.

### E.3 Amendment, 1 Sept (later same day) — max intensity on every tier; escalate on pattern, wings, and rate, never on brightness

E.2 above still had Tier 1 at "moderate gain" and Tier 2 at "higher gain," carrying part of the
escalation on the intensity axis this ADR was originally built around. The project owner, after the
hardware bring-up in `HANDOVER.md`, made an explicit field call to drop that: **there is no field use
for a dimmed deterrence flash** — a partially-lit strobe aimed at a forest edge at night does not read
as "less threatening, saving headroom," it just reads as a weaker light. Every deterrence tier now
fires the LED at `LED_GAIN_MAX_PCT` (100%). This supersedes the per-tier gain language in E.2.

**What now carries escalation, with the headroom argument E.2 made still intact:**
- **Wing count** — Tier 1 one wing, Tiers 2-3 both wings. Doubling the number of active light sources is
  the lever with real (if modest) evidentiary support in this ADR — Adams et al.'s multi-unit barrier
  "appears more threatening than a single directional spotlight." It is also a larger real change in
  emitted light than 50%→100% gain on a single 3W star, which the 31 Aug camera-invisibility finding
  shows sits below the brightness-relative-to-ambient threshold that actually matters at foliage range.
- **Pattern character** — single-wing strobe → antiphase sweep → both-wings-synchronised /
  independently-flickering, per E.1/E.2. Unchanged.
- **Strobe rate, top rung only** — new constant `LED_STROBE_FAST_HZ = 11` (config.h), used by
  `PATTERN_PULSE_BOTH_SYNC` (pattern_id 5, a Tier 3 pattern). Lower tiers and `PATTERN_SWEEP` keep
  `LED_FAST_STROBE_HZ = 7`. From the owner's follow-up: *if elephants don't retreat, escalate to a
  faster, more unpleasant strobe.* 11 Hz is still inside the ~4-12 Hz band that reads as discrete
  aversive flashes; past ~15-20 Hz the flashes fuse toward a steady glow and the aversive effect
  inverts, so this is near the top of the usable range, not an open-ended "faster is better." Kept as a
  three-tier ladder — no new Tier 4.

E.2's anti-habituation reasoning (Goodyear & Schulte 2015, Khorozyan & Waltert 2019 — fast fixed
max-intensity stimuli habituate) is **not** violated by this change: the thing E.2 wanted to avoid was
firing an unvarying maximal response on every trigger, and the ladder still varies pattern, wing count,
and now rate across tiers, with the bandit's `escalation_floor()` still reserving the dual-wing patterns
for repeat animals. What changed is only that the *brightness* axis, which was never a strong perceptual
lever between tiers on this hardware, is now pinned at max instead of ramped.

**Honest bound, restated for the rate change specifically:** no citation — elephant-specific or
practitioner — ranks 11 Hz above 7 Hz as "more effective." DFO's testimony validates strobe as a
technique, not a frequency. All that supports 11 over 7 is the order of magnitude (still in the aversive
band) and the fusion ceiling (staying clear of it). A faster strobe is not a validated guarantee that a
non-retreating animal will then leave; it is the last visual lever this device has before the horn
carries the rest of the escalation.

**The horn is deliberately not changed to match.** Horn gain keeps its graded ramp
(`HORN_TIER_1/2/3_GAIN_FRACTION` = 0.25 / 0.45 / 1.0) because `HORN_GAIN_MAX_PCT` is a hearing-safety
cap for people and livestock near the unit (ADR 0016) — a real physical-harm limit. The LED has no such
limit at its own max, so "always max" is safe for the light and not for the horn.

**IR is reclassified out of the deterrence ladder — as a follow-up, not in this amendment.** IR is a
940nm camera illuminator for night detection range, not a deterrence actuator; it emits nothing an
elephant can see. Its correct behaviour is to fire at whatever drive/pulse config gives the vision model
the cleanest night frame, gated by a day/night trigger, *independent of the deterrence tier*. That is a
separate change with its own ADR — it needs the IR firing path moved out of `DeterrenceAction`/tier into
the camera-capture path, a "when is it night" signal defined, and the empirical best-config result from
the dark-hours IR characterization session. `fire_ir`'s per-tier values are left as they are for now
rather than half-migrated (setting them all false without the new path would leave night captures
unlit). Tracked, not done here.

**LED and horn active fire-duration per detection** — how long each should run to maximise the chance of
blocking an approach — is likewise a separate follow-up. ADR 0017 (encounter window and active
duration) already covers the relevant part: retune `HABITUATION_WINDOW_S` / `PROXY_REWARD_HORIZON_S`
against real raid-duration data, and do *not* build blind timer-based re-firing without a presence
signal. Longer is not automatically better (habituation; battery/thermal cost; horn hearing-safety near
homes).

**Implementation delta from E.2, for the execution session:** `cognition/config.py`
`LED_TIER_1/2_GAIN_FRACTION` → 1.0 (Tier 3 was already 1.0), which makes all three `led_gain_pct` resolve
to 100.0 with no change to the `DETERRENCE_TIERS` literal; `config.h` gains `LED_STROBE_FAST_HZ 11`;
`led.cpp` `pattern_pulse_both_sync` uses it in place of `LED_FAST_STROBE_HZ`; host tests updated
(`test_cognition_config.py` now asserts every tier requests exactly `LED_GAIN_MAX_PCT`;
`test_led.cpp` asserts pattern_id 5 strobes at `LED_STROBE_FAST_HZ`, distinct from the lower rate).
Reflash + supervised physical bring-up with the owner present — same hard safety rule as every other
actuator change.

## Alternatives considered

- **Do nothing until stop-on-retreat / real animal-outcome feedback exists.** Rejected: that's a
  multi-month sensing problem (needs a retreat signal this device has no path to acquiring), and shipping
  a ladder that cannot physically vary its own output in the meantime is strictly worse than shipping one
  that at least varies pattern/intensity/channel, even against an unvalidated proxy reward.
- **Pulsed LED overdrive for genuinely brighter momentary flashes** (raising peak current above the 3W
  stars' continuous rating for brief, low-duty pulses — the buck driver has real headroom, rated 5A vs.
  ~1.4A actual per-branch draw). Real lever, explicitly **not** adopted in this pass: no datasheet
  pulsed-current figure for the actual LED stars in hand exists anywhere in this repo, and the buck's
  CC trimmer is currently set for continuous duty, not tuned for pulsed operation. Needs the datasheet
  figure plus a supervised bench burn with thermal monitoring before it's trusted near a field unit.
  Logged as a real, future option — not scoped into this ADR's implementation.
- **Full 4-channel/10-LED rebuild** (`WIRING_GUIDE.md` §4.0's original plan). Rejected for this pass:
  needs two new GPIOs (one JTAG-shared, unverified) and a re-check of the 6A fuse against ~22.4W
  simultaneous draw (vs. ~13.4W it was sized for) — real hardware work, not justified when the 2-wing
  build already has an unexploited pattern+intensity+channel-sequencing axis to work with first.

## Consequences

- No new hardware, no new GPIOs, no `rule_gate.cpp` change. Real, measurable per-tier distinctiveness
  where there was none.
- Requires: a `SCHEMA_VERSION` bump (breaking wire change, both MCU and MPU sides must update together),
  `bridge_handlers.cpp`/`led.cpp`/`led.h` changes, `cognition/config.py` tier reallocation, host tests
  (`pio test -e native`, `pytest`) for all of the above — all doable without touching the board.
  **Reflash + physical bring-up + camera/eye verification is separate, later work** and should not happen
  in the current very-long session; do it in a fresh, daylight session per the project's own
  session-continuity discipline, same as the D3 pin fix already queued for that session.
- Camera-invisibility at foliage range (31 Aug finding) is a raw-brightness-relative-to-ambient problem
  that pattern/timing changes alone do not fix — re-verifying wing visibility after this change still
  needs the same daylight-plus-distance test already queued for the IR-throw characterization, not a
  repeat of last night's static camera-diff sweep.
- The "never habituate" framing should not appear in contest/DFO materials as a proven claim. This ADR
  closes the mechanism gap (the ladder can now actually vary its output); it does not manufacture field
  evidence that hasn't been collected.
- Per E.3: the LED brightness axis is retired as an escalation lever — every deterrence tier fires the
  light at 100%. Distinctiveness between tiers is now entirely wing count + pattern + (top rung) strobe
  rate. `LED_STROBE_FAST_HZ = 11` is a new firmware constant; it does not cross the schema boundary
  (MCU-only), so E.3 needs no further `SCHEMA_VERSION` bump beyond the one Decision E already required.
- Two follow-ups are logged by E.3 and not done here: (1) decouple IR from the deterrence tiers and
  drive it purely as a day/night-gated camera illuminator, its own ADR; (2) tune LED/horn active
  fire-duration per detection, tracked under ADR 0017.
