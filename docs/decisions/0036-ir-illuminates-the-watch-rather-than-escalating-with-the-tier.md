# ADR 0036: The IR illuminator lights the scene for the camera, not the tier

- **Status:** accepted
- **Date:** 2026-10-02
- **Resolves:** ADR 0022's open follow-up, "proactive illumination during the watch, which is what
  would make Decision B bite at night"
- **Amends:** ADR 0019 (external IR illuminator and night gating) — the *when*, not the hardware or
  the duty budget
- **Relates to:** ADR 0022 (the watch and its blindness gate), ADR 0014 (LED deterrence, which this
  separates IR from), ADR 0034 (the bandit, which was blind at night for the same reason),
  ADR 0035 (the dataset, which was daylight-only for the same reason)

## Context

The whole IR subsystem already existed and was characterised: the illuminator, `pulse_ir()` with an
MCU-side duty and thermal budget (`IR_MIN_INTERVAL_MS`, `IR_PULSE_MAX_MS`), `perception/night.py`'s
day/night classifier, and a night exposure lock tuned against a real overnight soak
(`docs/qa/night-ir-led-characterisation.md`). What was wrong was only *when* it fired — and that one
thing made the node close to useless at night.

**IR was modelled as a deterrent.** `fire_ir` and `ir_duration_ms` were fields on
`DeterrenceAction`, off on Tier 1 and on above it. So whether the camera got any light at night was a
consequence of how hard the node had already decided to push an animal.

That is a category error with a concrete cost. **The illuminator does not deter anything.** It is
invisible to the animal and pushes nothing anywhere; it lets the camera see. The horn and the LED are
the deterrents. Modelling a light source as an escalation step put it on the wrong side of the one
decision that needed it.

**And it created a closed loop.** `pulse_ir()` fired *after* `decide()` and `select_tier()` had
already committed. So a night event was always decided on frames nothing had lit — and ADR 0022's
blindness gate, reading those same unlit frames, then refused to let vision confirm anything. The
node could not see, so it could not confirm; it could not confirm, so it could not reach a tier that
would have turned the light on. `services/config.py`'s night block records the consequence as "every
night event".

Three separate problems were all this one loop:

- **The seismic dataset was daylight-only** (ADR 0035), and all three target species are largely
  nocturnal.
- **The per-species bandit was blind at night** (ADR 0034) for the same reason — an unattributed
  trigger cannot partition anything.
- **Night deterrence fired at an animal the node never actually saw**, which is the exact thing
  ADR 0022 Decision B was written to stop.

## Decision

### A. IR leaves `DeterrenceAction` entirely

`fire_ir` and `ir_duration_ms` come off the dataclass. The horn and the LED are the whole of it. IR
is not a tier, not an escalation step, and not something the bandit chooses — it is a property of
trying to see in the dark.

Nothing in the code, comments, docs or ADRs describes the illuminator as deterrence. It is
illumination for extended night-vision range, and it is active when the vision system is active.

### B. `pulse_ir()` fires inside the vision watch, before any tier exists

The call site moves into `_watch_for_vision()`'s poll loop, gated on `frames_are_night()` reading the
watch's own frames as night — `perception/night.py` measures colour saturation, so the gate reads the
actual scene rather than a clock, and a floodlit yard at 2 a.m. is correctly not night.

The watch may run 45 s and the illuminator must not be on for all of it, so illumination is **pulsed
per poll rather than held**. The camera's night exposure lock is applied idempotently alongside it.

### C. A refused pulse degrades to today's behaviour; it never fails the event

The MCU's existing duty and thermal budget stays authoritative and keeps clamping and reporting. Once
the budget is spent, `pulse_ir()` refuses, and the watch simply continues on unlit frames — exactly
what happened before this ADR. A light that cannot come on is a worse photograph, not a lost event,
and the blindness gate will correctly decline to confirm rather than guess.

The pulse also does not extend the watch. It runs concurrently with the capture it illuminates rather
than before it, because the MCU's `pulse_ir()` blocks for the full pulse — the same cooperative
single-threaded `loop()` that makes the horn and LED sequential. The correct long-term fix is a
non-blocking MCU-side pulse; until then, concurrency on the MPU side is what keeps the poll cadence
intact.

## Alternatives considered

- **Keep IR on the tier, and add a second early pulse for the camera.** Rejected: two call sites for
  one illuminator, two duty-budget consumers, and the tier copy still carries the false claim that
  light deters.
- **Hold the illuminator on for the whole watch** instead of pulsing per poll. Rejected on the
  thermal and duty budget ADR 0019 already established, and on power — 45 s of continuous
  illumination per night event is a real draw on a solar node.
- **Gate on a clock or a solar almanac** rather than on the frames. Rejected: `frames_are_night()`
  already exists, measures the thing that actually matters, and needs no time sync on a node that may
  be days from a technician.
- **Fire IR before the capture rather than concurrently**, for a cleanly lit frame. Rejected for now
  because the MCU pulse blocks: serialising them would add the full pulse duration to every poll and
  stretch a 45 s watch past its budget. Recorded as the reason the MCU-side change is worth doing.

## Consequences

- ADR 0022 Decision B now has effect at night, which is when it was most needed and least able to
  act.
- ADR 0035's corpus and ADR 0034's attribution both stop being daylight-only, which is why this
  landed *before* the dataset work rather than after it — every night the dataset ran without it was
  a night of unlabelled captures.
- **Open and required before field trust: the per-event power cost of illuminating a 45 s watch has
  not been measured.** It needs hardware, the number belongs in `docs/qa/`, and no test asserts
  anything about it. This is the one item here that cannot be closed by code.
- `_vision_could_see()`'s `illuminated` parameter is still passed `False` by the ADR 0022 gate, so the
  blindness logic does not yet know that the scene was lit. The light reaches the camera; the gate has
  not been told. That is a remaining inconsistency, not a safety problem — it makes the gate
  conservative rather than permissive.
