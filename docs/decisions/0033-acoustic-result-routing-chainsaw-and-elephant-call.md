# ADR 0033: Acoustic result routing — chainsaw leaves fusion, `elephant_call` becomes vision-gated

- **Status:** accepted
- **Date:** 2026-10-02
- **Amends:** ADR 0007 Decision §5 (which classes feed the elephant-presence fusion sum)
- **Relates to:** ADR 0027 (the four-class scheme being routed), ADR 0009 (where the classification
  happens), ADR 0022 (the vision watch this reuses), ADR 0031 (the frames these produce)

## Context

ADR 0007 §5 drew one line through the acoustic classes: gunshot is not evidence about elephants, so
it gets a direct officer alert; everything else is evidence and feeds the log-odds sum in
CONTEXT.md §4. That line was correct about gunshot and wrong about the other two, in opposite
directions, and both errors shipped.

**Chainsaw fused as elephant-presence evidence.** A chainsaw means *people are cutting trees*. It is
strong evidence of an illegal activity and close to no evidence that an elephant is nearby — if
anything it is weak evidence against, since elephants avoid active human noise. Feeding it into a
sum whose only question is "is an elephant present" is the same modelling error ADR 0007 §5
identified for gunshot, applied to a class that ADR 0007 §5 itself put on the fusion side. ADR 0027
deferred this explicitly rather than guessing: "deserves its own decision with field evidence."

Two recorded gaps follow directly from it. `docs/KNOWN_GAPS.md` had chainsaw and `elephant_call`
sharing a single `WEIGHT_ACOUSTIC`, with no principled way to split one weight between a human
activity and an animal call; and a chainsaw at 0.9 confidence could cross the alert threshold on
its own, producing an elephant alert from a sound that means the opposite.

**`elephant_call` had the reverse problem: it fused, and nothing ever acted on it.**
`handle_acoustic_event()` folded it into `fuse()` and returned the result to the Bridge poll loop,
which logged it and dropped it. `decide()` was never called. The best class in the acoustic model —
the one that detects the animal this whole system exists for — was structurally incapable of causing
anything to happen.

That matters more than it sounds. The buried geophone misses elephants on soft ground, on leaf
litter, and beyond its radius. Sound carries much further than ground motion through those same
conditions, so the microphone is precisely the sensor that covers the geophone's blind spots. A node
that hears an elephant, watches it approach on camera, and declines to act has failed at its one job.

## Decision

### 1. `chainsaw` joins `gunshot` on the direct-alert path

`_FUSING_ACOUSTIC_CLASSES` drops to `{ELEPHANT_CALL}`. `_DIRECT_ALERT_ACOUSTIC_CLASSES` becomes
`{GUNSHOT, CHAINSAW}`: no fusion, no `decide()`, no deterrence, straight to a LoRa frame addressed
to forest officers. `comms/lora_uplink.py`'s `direct_alert_event()` takes the class rather than
hardcoding gunshot, and each gets its own `EventClass` so an officer's notification says which sound
it was. `web/backend`'s `send-alert` already routed both to officers and to no residents (ADR 0031
§D), so nothing downstream changes.

The justification is ADR 0007 §5's own, applied consistently: you do not answer a chainsaw with a
horn and LEDs, and a chainsaw does not tell you an elephant is present. Both halves of that
sentence have to be true for a class to belong on the fusion side, and for chainsaw neither is.

### 2. `elephant_call` never alerts alone — it starts a vision watch, and then behaves exactly like a footfall elephant

An acoustic elephant call produces no alert by itself. It opens a vision watch; only a confirmed
sighting produces anything at all. Once the camera confirms, the node **fires the deterrent and then
alerts**, identically to a seismic-triggered elephant — not a notification-only path.

The deterrence-first ordering is not a new rule here, it is the existing one: the uplink is built
from the finished `FootfallOutcome`, so a frame describing this event cannot exist until the horn ack
has been read (ADR 0031 §A, and `device/mcu/src/main.cpp`'s single `loop()` makes it true at the
transport layer as well — `lora_service()` cannot run while `horn_fire_sequence()` is blocking).

Why gate on vision at all, when a gunshot does not have to be? Because the acoustic model's
false-positive profile for `elephant_call` is unlike its profile for gunshot. A distant chainsaw, a
vehicle, a bird, or wind over the microphone can land in the call class; the cost of being wrong is a
horn fired at nothing, repeatedly, at a site where habituation is the thing that destroys the
deterrent's value (ADR 0017). The camera settles it for free, because the camera is going to be
opened anyway.

### 3. It enters the pipeline that already exists, as a second trigger source

`handle_acoustic_event()` does not get its own decision path. An `elephant_call` calls
`handle_footfall_event()` with the seismic modality marked `available=False`, inheriting
`_watch_for_vision()`, the bandit, the IR gate (ADR 0036), the retreat tail (ADR 0035 D8), the event
video and `event_from_footfall()` unchanged.

`available=False` is load-bearing and is not the same as `probability=0.0`. It makes `fuse()` *drop*
the modality instead of scoring it as "the geophone confidently says no elephant", which would drag
the combined log-odds down and could suppress an alert the microphone and camera had already earned
between them. `_watch_length_s()` also reads it directly and grants the 45 s **extended** watch for
a trigger with no geophone reading behind it — the behaviour the `home_test` cold-trigger fix put
there. This path becomes its second caller rather than a special case.

A second decision path was the alternative, and it would have duplicated ADR 0022's
`_vision_could_see()` blindness logic — the part that distinguishes "looked and saw nothing" from
"could not look". Two copies of that is how an elephant heard at night, never seen because the
camera was dark, becomes a confident negative.

## Alternatives considered

- **Split `WEIGHT_ACOUSTIC` into per-class weights.** This was the standing plan for the recorded
  gap. Rejected because Decision 1 removes the reason for it: with chainsaw out of the sum, the only
  fusing acoustic class is `elephant_call`, and one class needs one weight. Splitting a weight to
  make a wrong input less wrong is worse than removing the input.
- **Let `elephant_call` alert on its own, without vision.** Rejected on the false-positive profile
  above. A microphone-only elephant alert is also something an officer cannot act on differently
  from a camera-confirmed one unless the frame says which it was — which is why `EventClass 5` exists
  as a distinct value and never carries `FLAG_VISION_CONFIRMED`.
- **Make `elephant_call` notification-only — alert, never deter.** Rejected. It inverts the risk: the
  cases this path exists to catch are exactly the ones the geophone missed, which means an elephant
  already past the sensor it was supposed to trip. Watching it approach a household and choosing not
  to fire is the failure mode the DFO deployment is meant to prevent.
- **Keep chainsaw fusing but clamp its weight low.** Rejected as the same modelling error with a
  smaller coefficient. A low weight still says "this is evidence about elephants", and the sum would
  still drift on a night of logging.

## Consequences

- `EventClass.ELEPHANT_CALL = 5` is appended across the four layers in lockstep
  (`device/mcu/src/uplink.h`, `comms/lora_uplink.py`, `web/ingest/src/payload.ts`,
  `send-alert/message.ts`), with the known-answer byte vectors in `device/mcu/tests/test_uplink/`
  and `payload.test.ts` updated together — those shared vectors are the only thing keeping the two
  decoders honest. **No database migration:** `events.species` and `events.priority` are plain `text`
  with no CHECK and no Postgres enum.
- Both recorded gaps close: the shared acoustic weight (nothing left to split) and the
  chainsaw-alone-past-threshold case (chainsaw no longer reaches the threshold at all).
- **`ELEPHANT_CALL` as a wire class describes the trigger, not the confirmation.** A confirmed
  encounter that started as a call goes out as `ELEPHANT` with `FLAG_VISION_CONFIRMED`, because by
  then the camera has named the species. `ELEPHANT_CALL` therefore reaches the dashboard only on a
  path that does not currently exist on the device — which is the next consequence.
- **Open: `EventClass.ELEPHANT_CALL = 5` has no device producer yet.** The vision-gated path emits
  `ELEPHANT`; nothing emits `5`. It is defined on all four layers so that a microphone-only uplink
  can be added without a wire change, and so the decoders agree in the meantime. Until something
  emits it, the value is contract, not traffic.
- **Open: `Bridge.provide("report_acoustic_event", ...)` is still commented out in `main.py`**, and
  `ACOUSTIC_ENABLED` is `False` pending the BY-M1 microphone and a `mic_check` health floor. Every
  decision here is exercised by tests and by the replay harness; none of it has run on a live
  microphone in the field.
- **Open: the single-camera event mutex is the real contention this introduces.** Two trigger sources
  can now want the camera and the actuators at the same time. An acoustic-initiated event that cannot
  take the mutex is dropped and logged, never queued — a queued event would fire a deterrent at an
  animal that left minutes ago.
