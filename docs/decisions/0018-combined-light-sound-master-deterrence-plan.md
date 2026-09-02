# ADR 0018: Combined light + sound deterrence — master implementation plan

- **Status:** proposed
- **Date:** 2026-09-01

## Context

User asked directly, after ADR 0014 (LED)/0015+0016 (horn)/0017 (encounter window) were each written
separately: pull it into one plan — what frequency, what duration, what type, for both light and sound
together, mapped onto the real hardware, verified against the evidence. This ADR does not re-derive new
design (0014/0015/0016/0017 remain the source of truth for their own decisions) — it is the synthesis,
plus one real open question those four never resolved: **should LED and horn fire together, or is there
a reason not to.**

**The one real caution already on record that this ADR has to address, not just repeat**: `elephant-
deterrence-behavioral-science.md` §2 cites the Assam, India, 2006-2009 field practice
(conservationevidence.com/actions/2496) — combining a spotlight with noise reduced effectiveness relative
to the spotlight alone. Taken at face value this would argue against this device's whole design, which
fires LED+horn+IR together as one `DeterrenceAction` per tier. **Read closely, the analogy is weaker than
it looks**: the Assam practice was a *continuous, eye-aimed spotlight* plus *generic, unevidenced noise*.
This device's LED is a *strobe/pattern*, evidenced via a different mechanism (Adams et al. 2020's
multi-light "barrier reads as more threatening/human-patrol-like" finding, not "bright light overwhelms
the eyes"), and its audio is *evidenced predator-growl/bee-buzz content*, not generic noise. No elephant-
specific study tests "strobe + evidenced-content audio, combined" directly — so this ADR does not claim
the Assam caution is resolved, only that it does not clearly transfer to this specific combination either.
**Decision below: proceed with combined firing as already architected, treat the Assam caution as a real
open question worth watching during the actual field trial (a real data point this device can eventually
provide that the literature currently lacks), not a reason to redesign on speculation.**

## Decision — the concrete per-tier plan, light + sound + duration, mapped to real hardware

All durations below are already bounded by real firmware clamps in `device/mcu/src/config.h`:
`LED_BURST_MAX_MS=10000` / `LED_COOLDOWN_MS=20000`, `HORN_BURST_MAX_MS=3000` /
`HORN_COOLDOWN_MS=30000`, `IR_PULSE_MAX_MS=500` / `IR_MIN_INTERVAL_MS=5000`. Nothing below asks for a
number outside those clamps — the tier design works within hardware limits already in firmware, not
against them.

### Tier 1 — first/isolated trigger, proportionate response, preserve escalation headroom

| Actuator | Type | Frequency/detail | Duration | Gain |
|---|---|---|---|---|
| LED | `PATTERN_FAST_STROBE`, single wing (ADR 0014 §E.2, revised from slow-pulse — DFO practitioner-backed) | ~6-8 Hz | ~1.5-3s burst | Moderate (~50-60%) |
| Horn | Bee-swarm track (ADR 0016 Decision B) | Real recording, King et al. 2007-evidenced | ≤3s (`HORN_BURST_MAX_MS` clamp) | Moderate |
| IR | Pulsed, detection-only, not a deterrent (940nm, invisible to the animal — decoupled per the execution session's own overnight Item E work) | — | ≤500ms pulses | n/a |

Rationale: mildest real response with genuine evidence behind both modalities (Adams et al. pattern
principle for LED; King et al. 2007 for bee-buzz) — not a token first step, a real one.

### Tier 2 — repeat within the habituation window (now 60-90min per ADR 0017, not the old 10min)

| Actuator | Type | Frequency/detail | Duration | Gain |
|---|---|---|---|---|
| LED | `PATTERN_SWEEP`, both wings antiphase (ADR 0014 §E.1) | ~6-8 Hz per wing, alternating | ~3-5s | Higher (~75-85%) |
| Horn | Predator growl, rotating tiger/lion (ADR 0016 Decision B — best-evidenced category, Thuppil & Coss 2016, 65-100%) | Real recordings, two-track rotation | ≤3s | Higher |

First real use of dual-wing — adds the apparent-movement cue on top of DFO-validated strobe timing,
paired with the single best-evidenced audio category available.

### Tier 3 — persistent repeat / escalation floor forces top tier

**Household-proximity node** (`NODE_HOUSEHOLD_PROXIMITY` per ADR 0016 Decision A):

| Actuator | Type | Frequency/detail | Duration | Gain |
|---|---|---|---|---|
| LED | Rotate `PATTERN_PULSE_BOTH_SYNC` / `PATTERN_FLICKER_BOTH_INDEPENDENT`, both wings (ADR 0014 §E.2) | ~6-8 Hz sync, or irregular independent flicker | Up to 10s (`LED_BURST_MAX_MS`) | `LED_GAIN_MAX_PCT` (100%) |
| Horn | Predator growl again, max gain/duration — **never** siren/firecracker at a household node (ADR 0016 Decision B) | Same evidenced tracks, max intensity | ≤3s | Max within horn's own physical ceiling |

**Non-household node:**

| Actuator | Type | Frequency/detail | Duration | Gain |
|---|---|---|---|---|
| LED | Same rotation as above | Same | Up to 10s | 100% |
| Horn | Rotate siren/firecracker, **prefer firecracker over siren** (ADR 0016 Decision B — siren has an actual disconfirming field study, Hedges & Gunaryadi 2010; firecracker is merely unproven-as-recording, a weaker caution) | Real recordings | ≤3s | Max |

Both wings + max gain + the most varied pattern/content pool is reserved for the tier a returning,
un-deterred animal actually reaches — not fired on the first, possibly-borderline trigger — per the
bandit's own `escalation_floor()` design and Goodyear & Schulte 2015 / Khorozyan & Waltert 2019's
caution against front-loading maximum-intensity stimuli (both already cited, §3 above).

## Frequency content, stated plainly against what's actually evidenced (added from today's §2.1 research)

- **Elephants hear ~16 Hz - ~12 kHz, low-frequency specialists** (ElephantVoices, citing captive Asian
  elephant audiometry) — every sourced track should be checked for energy concentrated below ~12 kHz;
  not yet measured against ADR 0016's five actual tracks in this pass, a real, cheap follow-up
  (spectrogram check, no new sourcing needed).
- **No elephant-specific study validates a specific LED strobe Hz or horn siren frequency as an optimum.**
  `PATTERN_FAST_STROBE`'s ~6-8Hz is an engineering choice anchored on DFO practitioner testimony (real,
  locally-relevant, not a controlled trial), not a cited number. Say this plainly if asked externally —
  already the standing discipline in ADR 0014/the research doc, restated here because this ADR is the one
  most likely to get read as "the numbers," and the numbers above are evidence-and-practitioner-informed
  engineering choices, not proven optima.
- **Bee-buzz and predator-growl are the two strongest-evidenced audio categories**; siren has a real
  negative field result; firecracker-as-recording and elephant-vocalization-playback (the new fifth
  category found today, Wijayagunawardane 2016) are both real but unproven/habituation-prone by their own
  literature — reflected in the tier table above (predator/bee lead every tier; siren/firecracker only
  reached by non-household nodes at the top tier).

## Implementation mapping to real hardware — for the execution session, nothing new beyond what
0014/0015/0016/0017 already specify, restated together so it's one checklist

1. `drive_led(schema_version, channel, pattern_id, gain_pct, duration_ms)` — ADR 0014 Decision A schema;
   `channel` addresses "both" per whatever mechanism the execution session picks (ADR 0014 §E's
   "Implementation, for the execution session" note); `pattern_id` selects among the 7 total patterns
   (4 single-wing from Decision B, 3 dual-wing from §E.1).
2. `drive_horn(track_id, gain_pct, duration_ms)` — ADR 0015's wire change (real `AT+PLAYFILE`/`AT+VOL`
   control replacing the current fixed-content, unwired-gain behavior), `track_id` selects among the
   library in ADR 0016 Decision C, gated by `NODE_HOUSEHOLD_PROXIMITY` per Decision A/B.
3. `cognition/config.py`'s `DETERRENCE_TIERS` — one `DeterrenceAction` per tier per the tables above,
   already the existing architecture (`bandit.py`/`reflex_loop.py` fire LED+horn+IR together per action,
   consistent with "proceed with combined firing" above).
4. `HABITUATION_WINDOW_S`/`PROXY_REWARD_HORIZON_S` — ADR 0017's retuned pair, governs how long a repeat
   trigger still counts as the same encounter for `escalation_floor()`.
5. Host tests for all of the above already scoped in 0014/0015/0016/0017 individually — this ADR adds no
   new test surface, just confirms the combined tier tables are what the tests should assert against.
6. Reflash + physical bring-up: same hard safety rule as every other actuator change this whole
   engagement — user physically present, unchanged by this ADR.

## Alternatives considered

- **Offset LED and horn firing by a short delay instead of simultaneous**, to hedge against the Assam
  spotlight+noise caution. Rejected for this pass: no citation supports a specific offset value either,
  it would add real firmware/MPU sequencing complexity for a caution that may not even transfer to this
  device's actual stimulus types (see Context), and it changes the already-verified "one Bridge call,
  bounded blocking cost" property ADR 0014 Decision B relies on. Logged as a real option if field
  observation during the actual trial suggests combined firing underperforms single-modality — not
  adopted speculatively now.
- **Skip lower tiers, always fire tier-3-equivalent output.** Rejected — same escalation-floor and
  habituation-timeline reasoning as ADR 0014 §E.2; already the standing design logic, restated here for
  completeness rather than re-argued.

## Consequences

+ One place that states the full light+sound+duration+frequency plan together, with real hardware
  function-call mapping, instead of requiring four separate ADRs to be cross-referenced by hand.
+ The Assam combined-modality caution is now explicitly addressed rather than left as a dangling flag in
  ADR 0014's Consequences section — addressed honestly (not dismissed, not treated as blocking).
- Still no elephant-specific evidence for the exact strobe Hz, siren frequency, or simultaneous-vs-offset
  firing question — this ADR organizes and applies existing evidence, it does not manufacture new
  evidence these open questions still lack.
- Spectrogram-checking the five sourced audio tracks against the ~12kHz hearing ceiling is real, cheap,
  flagged, unscheduled follow-up work — not done in this pass.
