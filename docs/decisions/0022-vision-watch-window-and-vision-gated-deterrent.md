# ADR 0022: A bounded vision watch window, and a deterrent gated on what vision saw

- **Status:** proposed
- **Date:** 2026-09-03

## Context

`reflex_loop.handle_footfall_event()` ran exactly one vision pass per event: on the footfall notify it
opened the camera, captured a 5-frame burst, ran the detector once, folded the result into `fuse()` as
the VISION modality, and decided. That single burst lands roughly two seconds after the trigger.

Two facts already in the record make that one glance close to useless, and they were not put side by
side until now.

**The geophone sees far further than the camera.** ADR 0008 records the field-validated seismic
detection range as 140–155 m (Wijayakulasooriya et al.). The camera's usable range against an animal in
forest foliage is unmeasured but certainly a small fraction of that — the "camera-invisibility at
foliage range" finding from bench testing puts it nearer 25 m, and ADR 0020 already leans on the same
asymmetry to argue a rolling pre-buffer is unnecessary. ADR 0008's own worst-case lead time from first
seismic detection to arrival is **45–65 s**.

So the sequence for a genuine approach is: geophone fires at 140 m → camera looks at 2 s → the animal
is still 130 m away and outside the frame → vision reports "no elephant" → *the animal arrives forty
seconds later*. The single burst does not report that vision failed. It reports, with an available
reading and full confidence, that nothing is there. It is a correct answer to a question nobody asked.

**And vision is currently advisory.** A confirmation raises the fused probability, but an event that
clears the seismic threshold fires regardless of what the camera saw. That is the safe direction for a
missed elephant and the wrong direction for everything else: cattle, wind, a passing vehicle, and the
loose soil that ADR 0001 already flags as the dominant false-positive source all fire the horn at full
tier. `cognition/bandit.py`'s habituation model is explicit that this is how a deterrent stops working
— an elephant that hears the horn on nights when nothing happened learns the horn means nothing.

The two problems have to be solved together. Gating the deterrent on vision while vision only gets one
glance two seconds after the trigger would suppress most real elephants. Extending the look without
gating anything on it would only produce better logs.

## Decision A — replace the single burst with a bounded watch window

`_watch_for_vision()` polls the detector repeatedly from the trigger until one of three exits:

1. **A confirmation.** Returns immediately without sleeping out the remainder — the moment the animal
   is in frame is the moment to fire.
2. **The window closes.** `VISION_WATCH_BASE_S = 8.0` for an ordinary trigger;
   `VISION_WATCH_EXTENDED_S = 45.0` when the event is a repeat inside the habituation window or when
   the seismic evidence would alert on its own. 45 s is the *bottom* of ADR 0008's 45–65 s lead-time
   range, chosen deliberately: the cost of guessing long is a delayed horn, which is worse than the
   cost of guessing short.
3. **The camera stops delivering.** Three consecutive empty polls
   (`VISION_WATCH_MAX_EMPTY_POLLS = 3`) abandon the window. Waiting out 45 s on a dead camera delays
   the deterrent for no possible gain.

Polling is once per second (`VISION_WATCH_POLL_INTERVAL_S`). Only two bursts are retained — the first,
which dates the event and feeds the night decision, and the confirming one, which is the evidence. A
45 s window at one poll per second is over a hundred 720p frames and nothing in between is ever read.

**This reverses a decision in ADR 0020.** That ADR states actuators are never delayed behind the
confirm window. They now are, by up to 45 s. The reversal is deliberate and the justification is
Decision B: once the deterrent's firing depends on what vision saw, "fire immediately and look later"
is not an option that exists. The delay is bounded by a constant, and it collapses to zero the instant
vision confirms.

**Power.** The watch does not create a new always-on load. The camera is already open for this event;
the window extends how long it stays open on a *triggered* event only, and the base case is 8 s. This
is not the continuous camera-plus-encoder draw ADR 0020 rejected, and that rejection stands.

## Decision B — the deterrent fires only on vision confirmation, unless vision was blind

`DETERRENT_REQUIRES_VISION_CONFIRMATION = True`. An event whose fused probability clears the threshold
is held unless vision confirmed a target — **or unless vision could not have seen one.**

The entire safety argument is in that second clause, and it rests on a distinction the code has to
make honestly: *"I looked and saw nothing"* is evidence. *"I could not look"* is an outage. Only the
first is a reason not to fire. `_vision_could_see()` returns False — treat as blind, fall back to the
seismic decision, fire — for every one of:

- the camera failed to open or capture;
- the detector failed, or the inference server is not running;
- no frames were captured at all;
- **the scene is dark and the illuminator is off**;
- the night heuristic itself raised, or could not classify the scene.

The fourth is the one that matters most and is easiest to get wrong. At night the camera works fine and
returns dark frames, so vision reports `available=True, confirmed=False` about an elephant it is
physically incapable of seeing. `pulse_ir()` fires only for tiers 2 and 3, and only *after* `decide()`
— so the illuminator is off during every night watch. Read as absence rather than blindness, a
confirmation-gated deterrent would go silent from dusk to dawn, which is when nearly all raiding
happens. It would fail silently, in the field, in exactly the conditions it was built for.

The consequence, stated plainly: **today, every night event still fires on seismic alone.** Decision B
changes behaviour only in daylight. That is a smaller improvement than it first appears, and it is the
honest scope. Making it bite at night requires proactive illumination before the decision — firing IR
*during* the watch rather than after it — which is a real change to the power and habituation model and
is deliberately not decided here.

Note that `is_night()` returning `None` (unclassifiable) resolves in **opposite** directions for the
two things that consult it: the IR gate suppresses the pulse rather than waste it, and this gate
assumes blindness rather than go quiet. Both are the conservative reading of their own question. The
answer is computed lazily and memoized per event — a confirmed event short-circuits the gate and never
pays for the HSV pass.

## Decision C — the acted-on species are configuration, not code

`DETERRENT_TARGET_LABELS` and `EVENT_VIDEO_TARGET_LABELS` in `services/config.py` replace the single
hardcoded `"Elephant"`. ETX-V is a two-class detector; the two classes are wanted for different things.
A label in the first list counts as a vision confirmation and can release the horn. A label in only the
second is detected, logged and filmed but never fires an actuator. Both default to `("Elephant",)`.

This makes "deter elephants, collect boar footage" a one-line change — and that is the configuration
recommended before any horn fires at a boar, because it produces the evidence for whether boar
deterrence is worth building at all.

**Adding boar to the deterrent list carries a cost that adding it to the video list does not.** The
bandit learns one policy per node, not one per species, and the habituation window counts triggers
without asking what caused them. Deterring boar spends the same escalation ladder and the same
encounter memory that elephant deterrence depends on: a night of boar visits can walk a node up to
tier 3 and leave an elephant arriving at dawn facing an already-habituated response. Nothing in the
code prevents this. It is a trade to make knowingly.

## Alternatives rejected

**Leave vision advisory and lengthen the window only.** Better logs, same horn. Does nothing about the
false-positive load that habituation actually cares about.

**Gate the deterrent without lengthening the window.** Suppresses most real elephants, since at 2 s
after a 140 m trigger the frame is genuinely empty. This is the combination that would have looked
correct in review and failed in the field.

**Treat "dark scene, nothing detected" as a real negative.** Simpler, and silently disables the
deterrent overnight. Rejected outright.

**Keep the watch running until the animal arrives, unbounded.** No bound means no guarantee on
actuator latency and no bound on camera-on time. 45 s is arbitrary but it is a number, and it is
sourced from ADR 0008 rather than invented.

## Consequences

- Deterrent latency on a *confirmed* daylight event is unchanged in the good case and up to 45 s worse
  in the case where the animal is still approaching — which is the case where the old behaviour fired
  at nothing.
- Daylight false positives no longer fire the horn. Night false positives still do.
- `FootfallOutcome` gains `vision_polls`, `vision_watch_s` and `suppressed_by_vision` so the field log
  can answer whether the window length is earning its cost. There is no field data behind 8 s / 45 s
  yet; these fields are how that gets decided.
- A held event still records its trigger, so suppression does not erase the encounter from the
  habituation count.
- `DETERRENT_REQUIRES_VISION_CONFIRMATION = False` restores the previous behaviour without a code
  change, if the gate proves wrong in the field.

## Follow-ups

- Proactive illumination during the watch, which is what would make Decision B bite at night. Blocked
  on a power and habituation decision, not on code.
- A real `trigger_to_first_frame_s` and a measured camera range, both of which would replace the
  8 s / 45 s guesses with numbers.
- `KNOWN_GAPS.md`: record that the deterrent is now daylight-gated and night-ungated, and that the
  bandit/habituation model is species-blind.
