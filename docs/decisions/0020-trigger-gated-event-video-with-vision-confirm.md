# ADR 0020: Trigger-gated event video, kept only on vision confirmation

- **Status:** proposed
- **Date:** 2026-09-02

## Context

User asked directly for footage of the full encounter story — elephant entering camera field, the
system detecting it, deterrence firing, the elephant retreating — as a real deliverable for both the DFO
trial and the Hackster contest submission the second is also being built for. Today's actual capture
(`reflex_loop.handle_footfall_event()`, `KNOWN_GAPS.md`'s 18 Aug entry) saves a 5-frame JPEG burst per
alert, camera opened on wake and closed ~2s after the IR pulse — not continuous video, and explicitly
**no rolling pre-event buffer**, a decision already made and documented as deliberate, not an oversight.

**Why a true always-on pre-buffer is rejected again here, for a harder reason than before.** `ADR 0008`
establishes the MPU sits in deep suspend between events specifically because its continuous draw
(~0.42-0.45W, ~10.8Wh/day) is already the binding constraint on the solar/battery budget during Kerala's
monsoon season, by the ADR's own text. **Qualified 2 Sept:** that figure is a third-party community
measurement and the suspend state it describes is not implemented — see ADR 0008's 2 Sept addendum, which
puts the likely as-built idle nearer ~3.3W. This **strengthens** the rejection below rather than weakening
it: a higher real baseline makes a continuously-running camera and encoder less affordable, not more. A rolling video pre-buffer needs the camera and encoder running
continuously, not the MPU's idle suspend draw — several watts sustained, not fractional-watt suspend, for
10 unattended field days. This isn't a complexity problem to engineer around, it risks draining the
battery mid-trial and getting **no** footage at all. Rejected as a design, not deferred as a nice-to-have.

**Why it's likely unnecessary anyway.** The geophone's field-validated detection range is 140-155m
(Wijayakulasooriya et al., already cited in ADR 0001/0008) — almost certainly farther than the camera can
actually resolve anything in forest foliage (a documented "camera-invisibility at foliage range" finding
already exists from bench testing). So at the moment a seismic/acoustic trigger fires and wakes the MPU,
the elephant is very likely **not yet in camera view** — still closing distance. A sufficiently long
*post*-trigger recording window should capture "entering camera field" naturally, without needing to look
backward in time. Real confirmation of this (a `trigger_to_first_frame_s` figure from a live-hardware
alert) doesn't exist yet — logged as a real follow-up, not assumed proven here.

**Storage is a real constraint that changes shape with video vs. the current JPEG burst.** The existing
sizing (`KNOWN_GAPS.md`) gives a 5-frame JPEG burst as ~1.5-2.5MB, yielding ~200-330 bursts before a
low-space warning and ~1400-2400 total on the ~3.6GB usable partition. A 60-90s H.264-encoded event video
is realistically 10-20MB — 5-10x heavier per event. That drops the realistic ceiling to roughly 25-50
confirmed events before the warning threshold, ~180-360 total. `KNOWN_GAPS.md` already flags "no automatic
pruning/rotation exists" as open and low-priority; with video instead of JPEG bursts, it stops being
low-priority.

**GStreamer is already installed and confirmed working on the board** (`KNOWN_GAPS.md`, 28 Aug entry) —
`gstreamer1.0-tools`, `-plugins-good`, `-base`, `-libcamera` are present and already used for the Edge
Impulse runner's live camera path. Real video encoding is buildable on what's already on the board, not a
new dependency.

**No path exists to get this footage off the board automatically.** LoRaWAN (ADR 0002) is an
alert-bandwidth link, nowhere near video-capable. Confirmed events stay on-device storage until a
physical USB/SD retrieval — this needs planning (mid-trial check-in vs. end-of-trial pull), not an
assumption that footage "just arrives."

## Decision

**A. Camera and vision model activate strictly on a qualifying MCU trigger, unchanged from today's
architecture** — this ADR does not change *when* the MPU wakes, only what it does once awake. No new
continuous/always-on capture path.

**B. On wake: record to a scratch file, run vision inference concurrently, decide keep-or-discard within
a short window — not the full duration for every trigger.**
1. Camera opens, video recording begins to a scratch/temp path (not the permanent capture directory).
2. Vision inference runs on the live/recording stream concurrently, not after the fact.
3. **If no elephant is confirmed within ~15-20s of wake**: stop recording, delete the scratch file,
   proceed to whatever non-alert path the fusion/decision layer already takes for a non-qualifying event.
   Bounds the cost of the common case (wind, other wildlife, false positives from geophone STA/LTA) to
   ~15-20s of camera+encode power, not the full event-window duration.
4. **If an elephant is confirmed within that window**: continue recording through the full deterrence
   sequence (actuators fire as today) plus a generous retreat tail — 30-60s total from confirmation,
   consistent with the existing `CAPTURE_POST_FIRE_TAIL_S` principle but sized for continuous video, not
   a 2s JPEG-burst tail. Stop, close, and move the file from scratch to the permanent capture directory
   as one continuous file covering approach-confirmation-through-retreat.

**C. Storage: no deletion, ever — monitor and alert instead, per explicit user instruction.** Confirmed-
event footage is exactly the deliverable this trial and the contest submission need; auto-deleting any of
it to make room is unacceptable regardless of how full storage gets. This is safe, not just accepted risk:
discarded (non-elephant) triggers already never persist past the scratch stage, so only real confirmed
events count against storage at all, and at ~10-20MB/event against ~180-360 total capacity, a single node
would need well over a hundred confirmed elephant encounters in 10 days to approach the ceiling - not a
realistic count. Keep `CAPTURE_LOW_DISK_HEADROOM_BYTES` as a **monitoring/alert threshold only** (log a
warning, do not act on it). If storage is ever genuinely exhausted regardless: new event saves fail and
log a warning (same existing principle as camera/storage failures already never blocking actuator
firing) - deterrence keeps working, every already-confirmed clip stays untouched, only a save past that
point could be missed. `KNOWN_GAPS.md`'s old "no pruning policy" item should be updated to reflect this
as the deliberate decision, not left reading as still-open.

**D. True pre-trigger buffer: still not built, explicitly deferred, not silently dropped.** Get a real
`trigger_to_first_frame_s` (or better, trigger-to-elephant-first-visible) figure from the first live
alert fire before deciding whether Decision B's "record from wake" design actually misses meaningful
approach footage. If it does, that's a real, separate, power-budget-aware follow-up decision — not
smuggled into this ADR on the strength of a plausible-but-unmeasured argument.

## Alternatives considered

- **Continuous always-on rolling buffer** (the original ask, "5-10s prior to detection" via a
  continuously-running capture loop). Rejected — real, likely-blocking conflict with the already-tight
  MPU-suspend-based power budget (ADR 0008), for a benefit (pre-trigger footage) that's probably not
  needed given the geophone-range-vs-camera-range reasoning above, unconfirmed either way.
- **Record the full window for every trigger, decide keep/discard only at the end.** Rejected — costs
  full recording duration in power/temp-I/O even for the common non-elephant case; the early-stop-at-15-20s
  design gets the same storage outcome at a fraction of the per-false-trigger cost.
- **Keep the current 5-frame JPEG burst, do nothing.** Rejected — doesn't serve the explicit ask (a
  continuous story of the encounter), and the contest-footage goal is a real, stated priority now, not a
  secondary nice-to-have.

## Consequences

+ Real, continuous "entering → detected → deterred → retreating" footage for confirmed events, serving
  both the DFO trial and the contest submission goal directly.
+ No new always-on power draw — stays within the existing wake/suspend architecture ADR 0008 already
  sized the budget around.
+ Bounds the cost of non-elephant triggers to ~15-20s instead of the full event window.
- Per-event storage is materially larger than the current JPEG-burst design — the existing "no pruning"
  gap must actually be closed as part of this work, not left open.
- Footage retrieval still needs a real plan (physical pull, mid-trial or end-of-trial) — not solved by
  this ADR, flagged so it isn't discovered as a surprise on day 10.
- The pre-trigger-buffer question remains genuinely open pending a real latency measurement — this ADR
  bets that post-trigger recording is sufficient, and says plainly that bet is unconfirmed.
- `perception/camera.py` currently has no video-recording capability at all (JPEG burst only via OpenCV)
  — this is new capability to build, not existing plumbing to wire through, a bigger lift than ADR
  0014/0015/0016/0017's changes were.
