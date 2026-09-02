# ADR 0019: External IR illuminator fires on a frame-derived night signal, not on the deterrence tier

- **Status:** proposed
- **Date:** 2026-09-02

## Context

ADR 0014 §E.3 ended with an explicit follow-up, quoted here so this ADR's scope is unambiguous:

> **IR is reclassified out of the deterrence ladder — as a follow-up, not in this amendment.** IR is
> a 940nm camera illuminator for night detection range, not a deterrence actuator; it emits nothing
> an elephant can see. Its correct behaviour is to fire at whatever drive/pulse config gives the
> vision model the cleanest night frame, gated by a day/night trigger, *independent of the
> deterrence tier*. That is a separate change with its own ADR — it needs the IR firing path moved
> out of `DeterrenceAction`/tier into the camera-capture path, a "when is it night" signal defined,
> and the empirical best-config result from the dark-hours IR characterization session.

This ADR is that change. Three things had to exist before it could be written, and now do:

1. **The IR firing path was already partly decoupled.** As of the 28 Aug work recorded in
   `docs/KNOWN_GAPS.md`, `reflex_loop.py` fires `pulse_ir()` on a short-lived thread concurrent with
   the evidence `capture_burst()`, joined before `drive_horn()` — it is on the camera-capture path,
   not called as an actuator after `decide()`. What remained coupled to the tier was the *decision
   to fire it at all*: `pulse_ir()` runs only when the selected tier's `DeterrenceAction.fire_ir` is
   true, which `cognition/config.py` sets for Tiers 2 and 3 and leaves false for Tier 1.

2. **A "when is it night" signal now has an empirical basis.** The dark-hours characterisation run
   (1–2 Sep 2026, Kothamangalam backyard — full writeup in
   `docs/qa/night-ir-led-characterisation.md`) measured, across three separate baselines and every
   horizontal band of the frame, that **mean HSV saturation is exactly 0.000 at night** and that a
   daylight colour frame from the same camera reads mean S above 30. The IMX462 (ADR 0001) carries a
   mechanical IR-cut filter it swaps on its own: in daylight the filter sits in front of the sensor
   and blocks the illuminator's near-IR before it reaches a pixel; once the scene is dark enough the
   filter swings out and the image goes genuinely monochrome. No API on this board reports the
   filter position, but the swap is a two-order-of-magnitude change in frame saturation with nothing
   in between.

3. **The illuminator's night benefit is now measured, so "fire it whenever it is night" is a
   defensible default rather than an assumption.** Same characterisation run, exposure locked to
   isolate the effect from AGC: a single 500 ms pulse lifts full-frame luma **+31% to +47%** on
   every range band, and roughly **doubles resolved detail (Laplacian variance) at the treeline**
   — +53.7 at exposure 100, +91.2 at exposure 156 — which is the vegetation edge where an animal
   first becomes visible. No clipping in any run. The honest bounds on that result (measured with
   exposure locked, not on the deployed AGC config; scene was empty so detection benefit as opposed
   to image-quality benefit is still unmeasured) are recorded in the findings doc and in
   `docs/KNOWN_GAPS.md`; they do not change the direction of the decision.

### Why the tier is the wrong thing to gate on

`fire_ir` being a per-tier flag conflates two unrelated questions:

- *Is this a serious enough encounter to escalate the deterrent?* — what the tier ladder is for.
- *Will firing the IR illuminator improve the frame the vision model and the evidence clip are
  built from?* — a pure day/night / camera-optics question with no bearing on deterrence severity.

Tying them together produces two wrong behaviours:

- **Daylight Tier 2/3 events fire the illuminator for nothing.** The IR-cut filter is in, the
  near-IR never reaches a pixel, and the pulse is spent IR-MOSFET duty budget and battery for zero
  image gain. On a solar-budgeted field unit that is a real, if small, recurring waste, and it adds
  avoidable thermal and duty load to the one actuator path (`IR_MIN_INTERVAL_MS`, `IR_PULSE_MAX_MS`)
  that is deliberately the most rate-limited.
- **A genuine night Tier 1 event gets an unlit evidence burst** even though the illuminator would
  help most exactly then. ADR 0014 §E.3 already calls the tier coupling out as the reason night
  captures would go dark if `fire_ir` were simply set false everywhere.

The characterisation run shows the illuminator's value is entirely a function of the camera's
optical state, which the frame reports directly. That is what the gate should read.

## Decision

**Add a second gate on `pulse_ir()`, on top of the tier's `fire_ir` flag: the illuminator fires
only when the pre-decision vision-check frames read as night. The tier ladder is otherwise
unchanged.**

Night is inferred from frame saturation, per the measurement in Context point 2 — not from a
wall-clock sunset table (wrong on heavy overcast, wrong near the solstices, needs a real-time
clock) and not from an added photocell (a part, a wire, a hole in the enclosure, and it would still
not track the camera's own filter switch). Keying off the frame means the gate is correct in
exactly the awkward cases — overcast noon, a yard light near the lens at 3 a.m., the minutes either
side of the filter's own swap — because it keys on the same optical state that decides whether IR
would help at all.

### A. New module `perception/night.py`

Two pure functions, no state:

- `frame_mean_saturation(image) -> float | None` — mean HSV S (0–255 scale) of one BGR frame.
  Returns `None`, never raises, when the frame cannot be measured: it was `None` (the camera fake
  hands those out; a real failed grab never reaches here), had no usable 3-channel shape, or cv2
  raised. A real monochrome night frame returns a small positive number, not `None`.
- `frames_are_night(images, saturation_threshold) -> bool | None` — `True` when the **median**
  measurable-frame saturation is below the threshold (filter out, fire IR), `False` at or above it
  (daylight, suppress), `None` when not one frame could be measured. Median, not mean, so a single
  odd frame — a headlight sweep, a compression artefact — cannot flip the verdict for a burst the
  filter is either fully in or fully out for.

cv2 is imported function-locally, exactly as `perception/camera.py` and `perception/detector.py`
already justify, so the module stays importable on a dev laptop with no OpenCV.

### B. New config constant `services/config.py NIGHT_SATURATION_THRESHOLD = 12.0`

Sits in the measured gap: night frames read 0.0, daylight colour frames read >30, 12 has margin on
both sides. It is **not a tuned figure beyond that separation** — there was no daylight/night
boundary sweep, and there does not need to be one given the size of the gap. Flagged as such in the
constant's own comment and in `docs/KNOWN_GAPS.md`; the overnight soak (Consequences) records the
real crossover value for the file.

### C. `reflex_loop.py` — inject the decision, gate the fire

- New `NightDecideFn` Protocol alongside the existing actuator-callable Protocols, and a new
  required keyword-only `is_night: NightDecideFn` parameter on `handle_footfall_event()` — same
  dependency-injection discipline every other side-effecting dependency in this module already
  follows (`drive_horn`, `pulse_ir`, `camera`, `detect_vision`, …): real wiring in `main.py`,
  recording fakes in tests.
- The bare `if action.fire_ir:` that guarded the IR thread becomes a resolved `fire_ir_now`:
  - `is_night()` is called on the **pre-decision vision-check frames** (`vision_frames`), which are
    already in hand at that point — the same short burst the vision detector just ran on. No extra
    capture.
  - `True` → fire, unchanged. `False` → suppress for this event, log
    `pulse_ir suppressed: … read as daylight …`, tier otherwise unchanged. `None` → suppress, log
    `pulse_ir suppressed: day/night undetermined …` — if not one vision-check frame could be
    measured, the evidence burst has nothing to illuminate either.
  - **An exception raised *inside* `is_night()` is caught, logged, and the pulse fires anyway**
    (`night = True`). This module's standing rule is that a perception failure never blocks an
    actuator; the IR illuminator is the most harmless thing on the bus to fire on a bad frame, and
    a night event losing its illumination to a saturation-measurement bug is the worse outcome.

`fire_ir` in `cognition/config.py` is left exactly as it is — Tier 1 `False`, Tiers 2/3 `True`. It
is now correctly read as *permission* (this tier is willing to spend an IR pulse) rather than
*guarantee*; the runtime night gate is the second condition. Tier 1 still never consults the gate,
because it never asks for IR in the first place.

### D. `main.py` wiring

```python
is_night=lambda frames: frames_are_night(
    [f.image for f in frames], config.NIGHT_SATURATION_THRESHOLD
),
```

`reflex_loop` imports nothing from `perception.night` — it only ever calls the injected callable.

### E. Tests

- `tests/test_night.py` (new, 12 cases): `frame_mean_saturation` degrade-to-`None` paths (None
  image, single-channel buffer, object without a shape, cv2 raising) and `frames_are_night`
  threshold / median / empty-burst / all-unmeasurable behaviour, with synthesised BGR frames,
  skipped where cv2/numpy are absent (same host-test caveat as `tests/test_camera.py`).
- `tests/test_reflex_loop.py` (5 new cases): daylight vision-check suppresses `pulse_ir` but still
  fires horn and LED; undetermined (`None`) state also suppresses; an `is_night()` exception never
  blocks deterrence and the pulse still fires; `is_night()` is handed exactly the pre-decision
  vision-check frames (`VISION_CHECK_FRAME_COUNT` of them, all `Frame`); Tier 1 never consults the
  gate. The module's other direct `handle_footfall_event()` call sites get an
  `is_night=lambda frames: True` default so their existing assertions are unchanged.
- `tests/test_cognition_config.py`: `test_only_the_lowest_tier_withholds_ir` keeps its assertions;
  its docstring now records that `fire_ir` is permission-not-guarantee and that the runtime gate is
  covered in `test_reflex_loop.py`.

Full MPU suite: **255 passed**, `ruff` clean.

### F. Pulse config (drive/duration) — deliberately not changed here

ADR 0014 §E.3's follow-up also asked for "whatever drive/pulse config gives the vision model the
cleanest night frame." The characterisation run answered the *gating* question conclusively but not
the *tuning* one: the large luma and sharpness gains were measured at a fixed 500 ms pulse with
exposure locked, and the run that would settle pulse length / drive current against the deployed
**auto-exposure** pipeline, with a real target in frame, has not happened (`docs/KNOWN_GAPS.md`).
`action.ir_duration_ms` therefore keeps its current value. This ADR changes *when* the pulse fires,
not *what* it is.

## Consequences

- **Daylight Tier 2/3 events no longer fire the IR illuminator.** Small recurring saving in
  IR-MOSFET duty budget, battery, and thermal load; no change to deterrence — the tier's light and
  sound are untouched, and the animal cannot see 940 nm anyway.
- **Night Tier 1 evidence bursts are still unlit.** This ADR does not change that — Tier 1 does not
  request IR. Whether the mildest tier *should* get an illuminated evidence clip at night is a
  separate question left open in ADR 0014 §E.3 and `docs/KNOWN_GAPS.md` (the "proactive
  illumination" redesign — firing IR before knowing whether it is even an elephant — against the
  battery/animal-welfare tradeoff). Not decided here.
- **The gate reads the pre-decision vision-check burst, which at night is already a dark frame.**
  `docs/KNOWN_GAPS.md` notes that this pre-decision check is effectively daylight/moonlight-only for
  *detection* because `pulse_ir()` (tiers 2/3, post-`decide()`) never illuminates it. That
  limitation is unchanged and unrelated: the night gate does not need the frame to be *good*, only
  to be *monochrome*, which a dark night frame reliably is.
- **`NIGHT_SATURATION_THRESHOLD` is separation-based, not swept.** If a future camera, lens, or
  firmware change narrows the 0-to-30 gap — a colour night mode, IR-cut disabled, a very different
  sensor — this constant needs re-measuring. The overnight soak
  (`nightchar/soak_20260901_185050/`, running as this ADR was written) samples saturation and
  wall-clock across a full night→day transition; its measured crossover value and timing append to
  `docs/qa/night-ir-led-characterisation.md` and should be checked against 12.0 before the field
  trial.
- **One more consumer of the injected-dependency pattern in `reflex_loop.py`.** `handle_footfall_event()`
  now takes ten-plus injected callables. This is the established shape of the module and the new
  parameter follows it exactly, but it is worth noting the signature is getting wide; a future
  refactor into a small `Dependencies` dataclass would be reasonable and is not blocked by anything
  here.
- **No firmware change, no reflash, no schema bump.** Entirely MPU-side Python. `pulse_ir`'s wire
  call is unchanged.

## Alternatives considered

- **Wall-clock / sunrise-sunset table.** Rejected: needs a reliable RTC (the board's time is not
  guaranteed in the field), is wrong under heavy overcast and near the solstices, and — the real
  disqualifier — does not track the camera's *own* IR-cut filter switch, which is the thing that
  actually decides whether IR reaches a pixel. The filter can swap before or after any fixed civil
  time depending on cloud and canopy.
- **Photocell / dedicated light sensor.** Rejected: an added part, a wire, and an enclosure
  penetration for information the camera already emits in every frame, and it *still* would not
  track the filter swap precisely.
- **Camera exposure / gain readback as the night signal.** Rejected: the container camera path
  cannot even set exposure (frozen at 156), let alone expose a trustworthy AE/AGC state, and the
  values that are readable are a poor proxy for the filter position. Saturation collapse is a direct
  optical consequence of the filter being out.
- **Set `fire_ir=False` on every tier and fire IR unconditionally from the capture path.** Rejected:
  that fires the illuminator in daylight too — the exact waste this ADR removes — and throws away
  the tier's already-correct "Tier 1 is a proportionate first response, leave the IR budget alone"
  reasoning from `cognition/config.py`.
- **Gate inside `cognition/decide()` instead of `reflex_loop`.** Rejected: `decide()` is the policy
  layer and has no camera frames; the night state is a property of the capture path, which is where
  the gate belongs. Keeping `decide()` free of I/O concerns is deliberate.
