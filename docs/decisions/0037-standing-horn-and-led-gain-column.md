# ADR 0037: The reduced horn and LED gain column is the standing configuration

- **Status:** accepted
- **Date:** 2026-10-02
- **Supersedes:** ADR 0014's graded horn ramp (`TIER_1/2/3_GAIN_FRACTION` = 0.25 / 0.45 / 1.0) and
  ADR 0014 E.3's "every deterrence tier fires the LED at `LED_GAIN_MAX_PCT` (100%)"
- **Relates to:** ADR 0016 (household-proximity sound limits, which is the reason this is kept),
  ADR 0015 (the horn volume path, still UNVERIFIED on the MCU core), ADR 0019 (the power rails
  whose repair forced this decision)

## Context

On 2026-09-10, after field-trial run #1, both gain columns in `device/mpu/cognition/config.py` were
pinned low as a power mitigation. Run #1's dawn false-positive storm re-fired deterrence repeatedly
against a camera that could not see, and the peak actuator draw sagged the shared battery hard
enough to reset the USB link — which killed the camera, which sustained the loop. Horn went to
0.20 / 0.28 / 0.35 and LED to a flat 0.85, and both comments said in terms that they were temporary:
*"Until that rig is on a stiffer supply"* and *"Revert to 1.0 once the supply is stiffened."*

The supply has since been stiffened, twice. The UNO Q was moved onto VIN, which gives its onboard
regulator a 7–24 V input range instead of a bare 5 V rail, and the LED bank was moved onto its own
buck so an LED fire can no longer pull the camera and board supply down with it. Both stated expiry
conditions are therefore met, and the reductions could simply have been reverted.

That forces the question the 10 September change deferred: the numbers were introduced on power
grounds that no longer apply, so is there any other reason to keep them?

## Decision

Keep them. The reduced column is the committed configuration, not an override of one.

| Column | ADR 0014 | This ADR |
|---|---|---|
| `TIER_1/2/3_GAIN_FRACTION` | 0.25 / 0.45 / 1.0 | 0.20 / 0.28 / 0.35 |
| `LED_TIER_1/2/3_GAIN_FRACTION` | 1.0 / 1.0 / 1.0 | 0.85 / 0.85 / 0.85 |

### The horn, kept quiet on bystander grounds rather than power grounds

ADR 0016's household-proximity argument applies at every tier, not only at the top rung where it was
first made. This unit is sited near homes. `HORN_GAIN_MAX_PCT` is a hearing-safety cap for people and
livestock standing near the enclosure — a real physical-harm limit, not an output target — and for a
deployment a forest division operates on behalf of residents, the conservative side of a
bystander-harm limit is the correct side to sit on.

There is also no evidence to justify going back. ADR 0015 Decision A records that the DFPlayer volume
path, while now wired in firmware, is still UNVERIFIED on the Zephyr-based MCU core: until bring-up
confirms `AT+VOL` over that software UART, the gain column changes nothing audible at all. Reverting
to a ramp whose top rung is 1.0 would be restoring an untested louder setting on the strength of a
power fix, which is an argument about the supply and not about deterrence.

Escalation does not lose a rung. The three tiers were already distinguished by `track_id` — *what*
the horn plays — since ADR 0015, and by the LED column. They are now distinguished by those alone.

### The LED, kept at 0.85 because E.3 was never about the number

ADR 0014 E.3 retired **brightness as an escalation axis**. Its argument was that a dimmed strobe does
not read as a gentler warning, it reads as a weaker light, so the tiers should not differ in
brightness. All three tiers remain equal here, so E.3's rule holds exactly as written; what changes
is only the common value it holds them at.

Fifteen percent off peak wing-MOSFET current is cheap margin on the as-wired parallel LED string, and
nothing measured distinguishes 85% from 100% at the ranges that matter — the 31 August camera-diff
sweep found LED brightness already sitting below the threshold relative to ambient that has any
effect at foliage range, which is the same finding E.3 itself leaned on when it argued that wing
count is a larger real change than a gain step.

## Consequences

- `tests/test_cognition_config.py` loses the condition-gated `GAIN_OVERRIDE` xfail marker, which
  existed to suspend three assertions while the reductions were an override. With the reductions
  committed, that marker would have silently disabled all three forever. The three tests are
  rewritten to assert the invariant that now holds:
  - `test_the_top_tier_is_the_strongest_rung` — no lower tier may ask for more gain than Tier 3 on
    either actuator, and duration still runs to the protocol maximum. This replaces the old
    "Tier 3 equals `PROTOCOL_GAIN_PCT_MAX`" check, which was really a proxy for "the ladder is not
    inverted" and is now stated directly.
  - `test_every_led_tier_fires_at_the_same_gain` — the tiers must be equal, which is E.3's actual
    rule, rather than equal *to 100%*, which was E.3's value.
  - `test_no_led_tier_requests_more_than_the_mcu_led_clamp` — weakened from equality to "at or under
    the firmware cap". It still reads `LED_GAIN_MAX_PCT` out of `device/mcu/src/config.h` rather than
    hardcoding it, so it still fails loudly if the firmware cap moves, and it still catches the error
    it was built for: a request over the cap that the MCU would silently clamp.
- A dead `GAIN_OVERRIDE` definition in `tests/test_reflex_loop.py`, never applied to any test there,
  is removed with it.
- The horn column no longer has a loudness ramp at all. If `AT+VOL` is confirmed working at MCU
  bring-up and a graded ramp is wanted back, it should be re-derived against a measured SPL at a
  realistic bystander distance rather than restored from ADR 0014's fractions.

## Honest bound

This is a bystander-safety-weighted choice made without a deterrence-efficacy measurement. The device
has never run an A/B on horn gain, so there is no evidence that 35% deters an elephant as well as
100% would; the claim being made is only that the harm of the louder setting is concrete and
documented while its benefit is not, and that the volume path is unverified in any case.

One measurement would reopen the power half of this. The horn amplifier is wired directly to the
battery bus that also feeds UNO Q VIN, so a Tier 3 fire still loads the same bus the original
brown-out was on. The 7–24 V VIN range should absorb the dip comfortably, but that is an inference
from the wiring topology — nobody has put a scope on the bus under a fire since the rework.
