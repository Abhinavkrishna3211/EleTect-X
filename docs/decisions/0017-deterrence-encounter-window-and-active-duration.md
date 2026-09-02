# ADR 0017: How long a deterrence response stays "active" per elephant encounter

- **Status:** proposed
- **Date:** 2026-09-01

## Context

User asked directly: how long should the deterrence stay active once an elephant is detected, and does
that belong in the same implementation pass as ADR 0014's dual-wing LED work. Two genuinely different
questions turned out to be bundled in that one ask, and this ADR separates them because they have very
different cost, risk, and evidence pictures.

**Question A — how long does the system keep treating repeated triggers as "the same encounter" for
escalation purposes.** This already has a real mechanism: `cognition/bandit.py`'s `escalation_floor()`,
keyed by `habituation_context()`'s repeat-count bucket, which only counts a prior trigger as a "repeat"
if it happened within `cognition/config.py`'s `HABITUATION_WINDOW_S` (600s / 10 min today). This
mechanism exists specifically so a persistent animal never gets the same gentle response twice — but its
10-minute memory was set, by its own honest in-repo comment, from an MCU-cooldown-multiple heuristic
("20x `HORN_COOLDOWN_MS`"), not from any data on how long a real encounter actually lasts.

**Real data found this pass, and it changes the picture**: Elephants in the neighborhood: patterns of
crop-raiding by Asian elephants within a fragmented landscape of Eastern India (PeerJ, 2020) measured
real Asian-elephant crop-raiding duration directly: mean 308 minutes (~5.1h, SE 167 min), range 15
minutes to 15 hours. https://peerj.com/articles/9399/ — see `docs/research/elephant-deterrence-
behavioral-science.md` §3.1 for the full note. Against that range, a 10-minute "still the same encounter"
memory will lapse repeatedly during a single realistic raid — an elephant investigating or feeding
between footfall-triggering movements for longer than 10 minutes resets the context bucket to 0 and gets
the gentlest tier again, exactly the failure mode `escalation_floor()`'s own docstring says it exists to
prevent.

**Question B — should the device proactively re-fire deterrence (LED/horn) on a timer while an animal is
believed to still be present, even without a new qualifying sensor trigger.** This has no existing
mechanism at all. Today's architecture is purely reactive: `services/reflex_loop.py` fires one
`DeterrenceAction` per qualifying MCU event (`report_footfall_event`/`report_acoustic_event` crossing
their confidence gates); there is no continuous "elephant still in range" signal anywhere in this
codebase to drive a proactive re-fire off of. `cognition/bandit.py`'s own module docstring already says
plainly: "stop-on-retreat is NOT implemented and is not implementable today - it needs a signal that the
animal actually left, and nothing on this device produces one." The same honest limit applies in the
other direction — nothing currently produces a "still here" signal either. The vision detector, the one
plausible source of a continuous presence signal, is capture-only today with no path into fusion/decision
(`docs/KNOWN_GAPS.md`, Build-call 4's vision-modality entries) — a separate, larger, already-tracked gap.

## Decision

**A. Retune `HABITUATION_WINDOW_S` using the real raid-duration data — small, safe, no reflash.**
Raise it substantially from 600s. Not to the sample mean (308 min) — that would mean almost every trigger
anywhere near a realistic raid gets treated as an unbroken single encounter, which stops being a useful
"is this a repeat" signal at all and starts just meaning "most of the night." A reasoned middle value,
still an engineering judgement and labelled as one: **somewhere in the 60-90 minute range** — long enough
to span realistic within-raid quiet gaps between footfall-generating movement (the original comment's own
"animal circling a node reads as one escalating encounter" intent, now sized against real data instead of
a cooldown multiple), short enough that a given night's herd is not conflated with a different visit many
hours later. The exact number inside that range is not prescribed here — pick one, document the real
citation behind it (replacing the old cooldown-multiple justification, which was reasonable before this
data existed but is now the weaker of the two available justifications), and keep the reasoning honest
about the fact that no citation validates the specific minute value chosen, only the order of magnitude.

**Required companion change, or the fix reintroduces the exact bug its own comment warns about**:
`PROXY_REWARD_HORIZON_S` (`config.py`, currently 1800s) is deliberately defined as **3x
`HABITUATION_WINDOW_S`** — the comment there is explicit about why: a gap long enough to score a full
reward must also be long enough that the next trigger starts a fresh context, or the reward and the
context bucket tell contradictory stories about the same event. Recompute `PROXY_REWARD_HORIZON_S` as
3x whatever new `HABITUATION_WINDOW_S` is chosen, don't leave it at 1800s.

**B. Do not build proactive timer-based re-firing in this pass — real option, real cost, needs its own
decision, not a default yes.** Two honest reasons, not "no time": (1) there is no presence signal to gate
it on today — firing on a bare timer whether or not the animal is still there is worse than the status
quo's "responds to real sensor evidence," not better, and would fire deterrence bursts into empty air on
a real fraction of triggers; (2) `docs/KNOWN_GAPS.md`'s already-open battery/solar-autonomy item (10 days
unattended, actuator duty cycle not yet confirmed against the ADR 0012 power budget) means adding
unconditional periodic re-fires has a real, currently-unquantified battery cost, not a hypothetical one.
The honest path to building this for real is wiring the vision detector into fusion first (already a
separate, tracked, larger gap) so a re-fire decision can be made on actual evidence of continued
presence, not a clock. Logged here as real future work, not silently dropped.

## Alternatives considered

- **Leave `HABITUATION_WINDOW_S` at 600s.** Rejected: now that real raid-duration data exists and
  contradicts the value's original justification, leaving it unchanged after finding that data would be
  ignoring evidence this repo's own discipline says to act on, not a neutral choice.
- **Set `HABITUATION_WINDOW_S` to the full sample mean (308 min) or max (15h).** Rejected: the point of
  the window is to distinguish "still the same encounter" from "a different visit," and a window that
  wide stops making that distinction for almost any trigger that happens the same night.
- **Build the proactive re-fire timer now, accept it fires blind.** Rejected for the reasons in Decision
  B — a real capability gap (no presence signal) and a real, already-flagged resource constraint (10-day
  unattended battery budget), not a schedule-driven deferral.

## Consequences

+ Closes a real, evidence-contradicted gap in the escalation-floor mechanism's own stated purpose, using
  the same discipline as every other constant correction in this project (cite the real number, don't
  invent one, say plainly what's still a judgement call).
+ No reflash required — pure MPU/Python config + host-test change, independent of ADR 0014's LED firmware
  work; can proceed on its own schedule.
- `PROXY_REWARD_HORIZON_S`'s dependent recomputation must not be missed, or the reward signal and the
  escalation context contradict each other again, quietly.
- Host tests that assume the current 600s/1800s values (if any hardcode them rather than importing the
  constants) need checking, not just the constants themselves.
- Question B stays open, honestly, as real future work gated on the vision-fusion gap and the
  battery-budget item — not resolved by this ADR, and should not be described as resolved.
