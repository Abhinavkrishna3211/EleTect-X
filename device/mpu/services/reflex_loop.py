"""The real sense -> fuse -> decide -> select -> actuate loop (CONTEXT.md 4).

This is the wiring, not a stub: cognition.fusion.fuse(),
cognition.decision.decide() and cognition.bandit's selection functions are
all real, tested pure functions, and this module is the imperative shell
around them (ENGINEERING_CONVENTIONS.md 2) - it owns logging and the real
side effects (drive_horn/drive_led/pulse_ir Bridge.call()s, an injected
camera opened for the duration of the deterrent sequence, a frame-storage
callable, and an injected experience store). Every one of those is
injected as a callable/Protocol rather than imported directly, so this
module stays importable and testable on a dev laptop with no board or camera
attached - the same discipline perception/camera.py uses for cv2
(function-local import) and bridge/rpc.py uses for arduino.app_utils (never
imported at module scope there either). device/mpu/main.py is the only place
that wires the real Bridge.calls and the real Camera/save_burst in; tests
inject recording fakes instead (tests/test_reflex_loop.py, mirroring
tests/test_fusion.py's pattern of asserting on a returned result, not on log
output).

Event order for a real (non-safe_mode) footfall event: record the trigger
-> camera.open() -> a bounded vision *watch* (ADR 0022: repeated
capture_burst(VISION_CHECK_FRAME_COUNT) + detect_vision() passes, spaced
VISION_WATCH_POLL_INTERVAL_S apart, exiting the moment one confirms) ->
build the VISION reading -> fuse() -> decide().

The watch replaced a single burst because the two sensors do not see the
same distance. The geophone's field-validated footfall range is 140m (ADR
0008); the camera's is a small fraction of that. At the instant of the
trigger the animal is typically still far outside the frame, so one burst
taken two seconds later reports "no elephant" about an elephant that is
simply not there yet, and the event decides on seismic alone every time.
How long the watch runs is _watch_length_s()'s call: a short window for an
ordinary trigger, and ADR 0008's own worst-case lead time (45s) for one
that has either repeated inside the habituation window - this device's
closest available signal for "the footfall event is still happening" - or
already cleared the alert threshold on seismic evidence alone.

Acoustic is deliberately not wired into this path, and for the first field
trial is not wired at all: the trial runs seismic + vision only. A footfall
notify carries no acoustic reading, main.py does not register
report_acoustic_event, and handle_acoustic_event() below stays complete and
tested for when it is turned on. The footfall path reports ACOUSTIC
unavailable, which fuse() drops rather than scores - so the absent modality
costs nothing and biases nothing. Camera and vision now run before
the alert gate, not after it - this is the "seismic wakes vision" ordering
the field trial requires, and the reason a footfall event now opens the
camera at all when it does not end up alerting. If decide() says no alert,
the camera closes immediately and nothing else fires. If it says alert:
[pulse_ir() started on its own thread, concurrent with a second
capture_burst() for the illuminated evidence footage, tier 2 and 3 only] ->
drive_horn() -> drive_led() -> a short post-fire tail sleep -> camera.close()
-> save_frames() with both bursts combined. The camera, opened once at the
top of the event, is never reopened for the alert path - only closed, once,
at whichever of the three exits (no alert / safe_mode / end of alert
sequence) the event actually takes. A camera or vision-detection failure at
any point is logged and never allowed to suppress or delay the actuator
calls that follow it - deterrence is the safety-critical function here,
vision and footage are both important but neither may block it. See
docs/KNOWN_GAPS.md.

safe_mode=True is the one exception to "camera opens on every footfall
event": it suppresses the vision check too, not just the actuators, so a
dry run touches the camera not at all (matching this module's existing
"SAFE_MODE suppresses ... the camera" contract, and the earlier discipline
of never giving a real HTTP inference server real traffic during a dry
run). The honest cost of that choice: a SAFE_MODE log's decision can
under-state what a live run of the same event would have decided, since
vision stays reported unavailable rather than corroborating or
contradicting seismic. Operators using SAFE_MODE to preview deterrence
policy should read it as "what fires, given seismic alone" rather than a
literal preview of the fused decision a live run would reach. See
docs/KNOWN_GAPS.md.

pulse_ir() runs concurrently with the capture, not after it, because the
MCU's own pulse_ir() blocks for the full requested duration
(device/mcu/src/ir.cpp: analogWrite(HIGH) -> delay(duration_ms) ->
analogWrite(0)) - the RPC only returns once the illuminator is already
dark. Calling it after capture_burst() the way every other actuator fires
here would mean every night frame this system captures is unilluminated.
Starting it on a short-lived thread right after camera.open() and joining
it before drive_horn() is what actually lands the exposure window inside
the pulse (see docs/KNOWN_GAPS.md, 27 Aug entry, for the correct long-term
fix - making pulse_ir() non-blocking on the MCU side - and why it is not
done here, six days from the field trial).

pulse_ir() is gated twice: the selected tier must set fire_ir (tiers 2 and
3 do, tier 1 does not - cognition/config.py), and the pre-decision
vision-check burst must read as night. The IMX462's IR-cut filter is in
during daylight, so the illuminator's near-IR never reaches a pixel then -
firing it would spend MOSFET duty budget and battery for nothing.
is_night() infers the filter state from the vision-check frames' own colour
saturation (perception/night.py); in daylight, or when no frame could be
measured, the pulse is skipped for that event and only that - the horn and
LED still fire the tier as selected.

What fires is chosen per event rather than fixed. decide() remains the
alert gate on the fused probability and is unchanged; once it says alert,
cognition/bandit.py selects one of cognition/config.py's three deterrence
tiers epsilon-greedily from action values persisted in the injected
experience store, with a hard escalation floor driven by how many triggers
this node has seen inside HABITUATION_WINDOW_S. That floor is the
habituation-avoidance mechanism: an animal that comes straight back cannot
receive the same response twice.

Two ordering rules in that path are load-bearing rather than incidental:

- Every footfall event is recorded as a trigger and settles any pending
  attempt, **before** the alert gate. A repeated STA/LTA crossing is
  evidence about habituation whether or not fusion cleared the threshold,
  and an animal circling a node while staying just under it is exactly the
  case the context should notice.
- An attempt is recorded **only when the horn ack came back true**. SAFE_MODE
  fires nothing, and the MCU refuses a request inside its own cooldown
  (rule_gate_apply()'s allowed=false, which is what the ack carries) - in
  neither case did a deterrence happen, so in neither case may the bandit
  be credited for one.

One of the three fusion modalities is still not wired in, and one now is,
by design, not oversight:

- **Vision** is wired into handle_footfall_event(), the seismic-wake path,
  per the field directive that seismic waking vision (not the other way
  round) is what the trial needs: perception/detector.py's HttpVisionDetector
  posts a captured frame to the standing edge-impulse-linux-runner HTTP
  server and _vision_check() below converts its detections into a
  ModalityReading. Only detections labeled "Elephant" (VISION_TARGET_LABEL)
  count as evidence toward "elephant present" - a Boar detection from the
  same two-class model is not folded into this modality; see
  _vision_check()'s own docstring for the no-qualifying-detection case and
  docs/KNOWN_GAPS.md for whether a Boar detection should ever suppress an
  alert (an open question, not decided here). Vision is not wired into
  handle_acoustic_event() - that path has no camera open at the moment an
  acoustic notify arrives, and the field directive is specifically about the
  seismic-wake ordering; see that function's own docstring, unchanged.

  One real limitation worth naming plainly: the pre-decision vision check
  runs *before* any deterrence tier is chosen, so it never gets the IR
  illuminator (pulse_ir only fires once decide()+select_tier() have already
  run, and only for tiers 2/3). At night this vision check will usually see
  a dark, unilluminated frame and report no qualifying detection - which
  _vision_check() scores as neutral (BASELINE_VISION, zero net
  contribution), not as evidence against an elephant. This means fusion
  degrades gracefully at night (seismic still carries the decision, vision
  simply adds nothing) rather than actively working against a real
  nighttime event - but it also means vision's corroboration only reliably
  helps in daylight or moonlit conditions until a proactive-illumination
  design (firing IR before knowing whether this is an elephant, a real
  animal-welfare/battery tradeoff ADR 0003 has not signed off on) is built.
  See docs/KNOWN_GAPS.md.
- **Acoustic**: handle_acoustic_event() now implements ADR 0007 5's
  routing split, so acoustic does reach fuse() - but never on the footfall
  path above, which still passes it as unavailable because no acoustic
  reading is in hand at that moment. Chainsaw/vehicle/animal_call convert
  to log-odds and fuse as the single ACOUSTIC modality; gunshot never
  touches fuse() at all (it is an anti-poaching alert, not evidence that
  an elephant is present); ambient fuses as unavailable. The gunshot
  branch calls the injected send_lora_alert when safe_mode is False, and
  logs a dry-run line instead when it is True - the callable itself is a
  scaffolded Bridge.call stub with no real transport behind it yet, since
  comms/ is empty and the LoRa module is not joining, so its ack means
  "queued/logged", never "delivered" (see docs/KNOWN_GAPS.md). Two
  caveats stand: no acoustic classifier runs on the MCU yet, so nothing
  calls this path in the field, and fuse() is stateless per event, so an
  acoustic reading cannot actually corroborate a seismic one - which is
  why handle_acoustic_event() stops at fuse() and never calls decide().
  See docs/KNOWN_GAPS.md.

Seismic and vision are both wired end-to-end into the alert-and-actuate
path now: the MCU's own on-board footfall model already reports a
probability (schema.md's report_footfall_event), and converting that into
fusion's log-odds input via cognition.fusion.logit() is a direct,
non-invented transformation - not a new detector this module had to build.
Vision's own log-odds transformation is the same logit() call on a real
detector's reported confidence (perception/detector.py), not invented
either - what is a genuine judgment call, not a measured figure, is
_vision_check()'s choice of what to feed fuse() when the burst produced no
qualifying detection at all (see that function's own docstring).

Event video (ADR 0020) rides on that same camera session, behind
services.config.EVENT_VIDEO_ENABLED and off by default. When device/mpu/
main.py wires an `event_video` object in, the camera it injects is a
perception.video.EventVideoRecorder, which starts an H.264 recording the
moment camera.open() succeeds and serves the vision-check and evidence
bursts off that same running pipeline - this loop cannot tell it apart from
a perception.camera.Camera and does not try to. What this loop adds is the
keep-or-discard decision at each of the three exits:

- **Keep-gate: vision confirmed OR an alert fired.** Either alone is
  enough. A confirmed elephant that fusion did not clear the threshold for
  is exactly the footage that would explain why it did not, and an alert
  that fired without a vision confirmation is a real deterrence event
  whether or not the camera resolved anything in the foliage. Only an
  event that is neither has its recording thrown away.
- **Discarded recordings never reach the permanent capture directory at
  all** - they are written to a scratch path and deleted there
  (perception/storage.py), which is what bounds the storage and I/O cost of
  the common non-elephant trigger.
- **The retreat tail replaces the post-fire tail when video is recording**
  (services.config.EVENT_VIDEO_RETREAT_TAIL_S, 45s, against
  CAPTURE_POST_FIRE_TAIL_S's 2s): 2s of video would show the horn firing
  and nothing after it, and the retreat is the half of the encounter this
  footage exists to record. The honest cost is that this handler blocks for
  that whole tail, so a second footfall notify arriving inside it waits -
  one of the reasons EVENT_VIDEO_ENABLED defaults to False.

The JPEG evidence burst is unchanged and still saved on the alert path,
alongside the video rather than instead of it - two independent records of
the same event, and the burst is the one that has actually run on real
hardware. Nothing here builds a continuous rolling pre-event buffer: ADR
0020 rejects one on power-budget grounds, and there is no flag in this
module that would turn one on.

SAFE_MODE (default on) is the dry-run gate: when true, an alert decision and
the tier the bandit selected for it are logged, but drive_horn is never
called and no attempt is ever recorded. Read once at import time from the
ELETECT_SAFE_MODE environment variable, so flipping it for a live session is
an explicit, visible operational step (`export ELETECT_SAFE_MODE=0`), never
a silent code default change - this mirrors device/mcu/src/config.h's own
"gated behind a flag, defaults to the safe state" discipline for the
fire-test harness and seismic debug-stream flags.
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from bridge.rpc import AcousticClass
from cognition import config as cognition_config
from cognition.bandit import (
    BanditParams,
    DeterrenceAction,
    Tier,
    escalation_floor,
    habituation_context,
    select_tier,
)
from cognition.decision import Decision, decide
from cognition.experience import SettledAttempt
from cognition.fusion import FusionResult, Modality, ModalityReading, fuse, logit
from perception.camera import CameraError, Frame
from perception.detector import Detection, DetectionError, VisionDetectFn
from perception.storage import CaptureEventTag
from services import config as services_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Safety gate
# ---------------------------------------------------------------------------

# Default-on dry run: only an explicit ELETECT_SAFE_MODE=0 in the process
# environment disables it. Read once at import time, not per call, so one
# log line at startup (main.py) can honestly state which mode this run is
# in - a value that could change mid-run would make that line a lie.
SAFE_MODE = os.environ.get("ELETECT_SAFE_MODE", "1") != "0"

# ---------------------------------------------------------------------------
# Alert threshold - INVENTED, see docs/KNOWN_GAPS.md
# ---------------------------------------------------------------------------

# cognition/config.py deliberately holds no alert threshold: ADR 0001's
# Consequences section says that number needs real field-accuracy figures
# (seismic ~70-75%, vision ~70-85%) this project doesn't have yet, and
# services/config.py's own docstring carves out "risk thresholds" as
# something that belongs to cognition/, not to it either - so there is no
# existing config module willing to hold this constant honestly. It lives
# here, next to its one real caller, instead of hidden behind either of
# those disclaimers.
#
# 0.5 - the fused probability's own uninformative midpoint - was chosen as
# the least presumptuous placeholder available, not a tuned figure: it adds
# no additional skepticism or credulity beyond what L_PRIOR and the
# per-modality weights/baselines already encode. Logged as an open gap, not
# closed by adding this constant - see docs/KNOWN_GAPS.md.
ALERT_PROBABILITY_THRESHOLD = 0.5

# Which of the deployed model's classes count as target-presence evidence
# for the VISION modality, and which are merely worth filming. Both are
# tuples and both are configured in services/config.py, which carries the
# full rationale and the three field configurations; the aliases here exist
# so this module reads against one name rather than a dotted path repeated
# a dozen times.
#
# A detection whose label is in VISION_TARGET_LABELS feeds fuse() and can
# confirm an event. One whose label is only in VISION_VIDEO_LABELS is real
# signal that gets logged and filmed but never fires an actuator - which is
# exactly what "record boar, deter elephants" means in practice.
VISION_TARGET_LABELS = services_config.DETERRENT_TARGET_LABELS
VISION_VIDEO_LABELS = services_config.EVENT_VIDEO_TARGET_LABELS

# ---------------------------------------------------------------------------
# Deterrence action selection
# ---------------------------------------------------------------------------

# Which actuator(s) to fire and at what gain/duration is no longer decided
# here: cognition/bandit.py picks one of cognition/config.py's three
# DETERRENCE_TIERS per event, and this module only executes the choice. The
# previous fixed request - protocol-max gain on horn, LED and IR on every
# single alert - survives unchanged as tier 3, so nothing about the loudest
# response has been weakened; what changed is that it is now reserved for
# repeat triggers and for events the bandit has learned to prefer it on.
#
# The "ask for the protocol max, let the MCU clamp it" policy that comment
# block described still holds for every tier: device/mcu/src/rule_gate.cpp
# remains the sole authority on real limits, nothing here duplicates them,
# and cognition/config.py's ladder comments carry the full rationale for
# how the three tiers are separated (and, honestly, for how little of that
# separation is physically audible today).

# The bandit's exploration draw. Module-level rather than per-call so a
# process does not reseed on every event, and injectable so a test gets an
# exact, reproducible selection rather than a statistical one - the same
# reason cognition/bandit.select_tier() takes the RNG at all instead of
# reaching for the `random` module's global singleton.
_DEFAULT_RNG = random.Random()

# How long to keep the camera open (and capturing) after the actuator
# sequence completes before closing it - the "post-fire tail" the footage
# needs to have any chance of showing the elephant retreat, not just the
# approach. INVENTED - no real footage review backs this number yet; see
# docs/KNOWN_GAPS.md.
CAPTURE_POST_FIRE_TAIL_S = 2.0


class DriveHornFn(Protocol):
    """Callable shape matching bridge.rpc.drive_horn's real signature."""

    def __call__(
        self, schema_version: int, gain_pct: float, duration_ms: int, track_id: int
    ) -> bool:
        """Request a horn burst; returns the ack drive_horn's own contract defines."""
        ...


class DriveLedFn(Protocol):
    """Callable shape matching bridge.rpc.drive_led's real signature."""

    def __call__(
        self,
        schema_version: int,
        channel: int,
        pattern_id: int,
        gain_pct: float,
        duration_ms: int,
    ) -> bool:
        """Request an LED burst; returns the ack drive_led's own contract defines."""
        ...


class PulseIrFn(Protocol):
    """Callable shape matching bridge.rpc.pulse_ir's real signature."""

    def __call__(self, schema_version: int, duration_ms: int) -> bool:
        """Request an IR pulse; returns the ack pulse_ir's own contract defines."""
        ...


class NightDecideFn(Protocol):
    """Callable that decides night vs day from a burst of BGR frames.

    main.py binds this to perception.night.frames_are_night with the
    configured saturation threshold; tests pass a stub. Returns True for
    night (fire IR), False for day (suppress IR), None when no frame in the
    burst could be measured (treated as "do not fire" - see
    handle_footfall_event).
    """

    def __call__(self, frames: list[Frame]) -> bool | None:
        """Report whether `frames` were captured under night / IR-cut-open conditions."""
        ...


class SendLoraAlertFn(Protocol):
    """Callable shape matching bridge.rpc.send_lora_alert's real signature."""

    def __call__(self, schema_version: int, confidence: float, capture_ref: int) -> bool:
        """Request a direct gunshot alert uplink.

        ack means queued/logged on the MCU, not delivered - no real LoRa
        transport exists yet (module not joining, see docs/KNOWN_GAPS.md).
        """
        ...


class CameraProtocol(Protocol):
    """The subset of perception.camera.Camera's interface this loop calls.

    Structural, not perception.camera.Camera itself, so a test fake needs no
    cv2/V4L2 dependency - same reasoning DriveHornFn doesn't import
    bridge.rpc's real implementation.
    """

    def open(self) -> None:
        """Open the device - see perception.camera.Camera.open's own contract."""
        ...

    def capture_burst(self, count: int, interval_s: float) -> list[Frame]:
        """Capture up to count frames - see Camera.capture_burst's own contract."""
        ...

    def close(self) -> None:
        """Release the device - idempotent, see Camera.close's own contract."""
        ...


class SaveFramesFn(Protocol):
    """Callable shape matching perception.storage.save_burst's real signature."""

    def __call__(self, frames: list[Frame], tag: CaptureEventTag) -> list:
        """Persist a burst tagged with the triggering event; returns paths written."""
        ...


class EventVideoProtocol(Protocol):
    """The keep-or-discard half of perception.video.EventVideoRecorder (ADR 0020).

    Deliberately only two methods: this loop never starts or stops a
    recording directly. The recorder is the same object injected as
    `camera`, so camera.open() has already begun recording and
    camera.close() has already finished the file by the time either method
    below is called - which is what keeps this module's camera handling
    identical whether video is enabled or not. Structural, not the concrete
    class, for the same reason CameraProtocol is: a test fake needs no
    GStreamer.
    """

    def commit(self, tag: CaptureEventTag) -> Path | None:
        """Move this event's finished recording into the permanent capture dir."""
        ...

    def discard(self) -> None:
        """Delete this event's recording without ever persisting it."""
        ...


class ExperienceStoreProtocol(Protocol):
    """The subset of cognition.experience.ExperienceStore this loop calls.

    Structural, not the concrete class, for the same reason CameraProtocol
    is: a test (or bench/demo_replay.py) can substitute an in-memory or
    recording store without this module ever importing sqlite3. close() is
    deliberately absent - the store outlives any single event, so closing it
    is the process owner's job (device/mpu/main.py), never this function's.
    """

    def record_trigger(self, event_ts_s: float, window_s: float) -> int:
        """Log a trigger; returns the in-window repeat count before it."""
        ...

    def settle_pending(
        self, now_ts_s: float, params: BanditParams
    ) -> SettledAttempt | None:
        """Score the oldest unsettled attempt against the quiet since it fired."""
        ...

    def action_values(self) -> dict[tuple[int, Tier], float]:
        """Return every learned value, keyed by (context, tier)."""
        ...

    def record_attempt(self, event_ts_s: float, context: int, tier: Tier) -> None:
        """Open an unsettled attempt for a deterrence that actually fired."""
        ...


@dataclass(frozen=True)
class FootfallOutcome:
    """What one handle_footfall_event() call decided and did.

    Returned (rather than left as a side effect only) so tests can assert on
    it directly, matching tests/test_fusion.py's pattern of asserting on a
    returned result rather than on log output.

    Attributes:
        fusion: The FusionResult fuse() produced for this event.
        decision: The Decision decide() produced for this event.
        repeat_count: Triggers this node saw within HABITUATION_WINDOW_S
            before this one. Recorded for every event, alert or not.
        context: The bandit context repeat_count bucketed into, or None if
            no alert fired (no selection happened, so no context applied).
        action: The DeterrenceAction selected for this event, or None if no
            alert fired. Populated even under SAFE_MODE - the selection is
            real, only the firing is suppressed.
        exploring: True if the selected tier came from epsilon-greedy's
            exploration branch rather than from the learned values. None
            when no selection happened.
        settled: The SettledAttempt this event's arrival scored, or None if
            nothing was pending. Note this scores the *previous* attempt,
            not this one - the reward is quiet time, which cannot be known
            until the quiet ends.
        horn_ack: drive_horn's returned ack, or None if it was never called
            (no alert, or SAFE_MODE suppressed the call).
        led_ack: drive_led's returned ack, or None under the same conditions
            as horn_ack.
        ir_ack: pulse_ir's returned ack, or None under the same conditions
            as horn_ack - and also None on tier 1, which does not fire IR at
            all.
        capture_frame_count: Number of frames actually captured for this
            event - the pre-decision vision-check burst alone on a
            non-alert event, that burst plus the post-alert evidence burst
            on an alert event, or 0 if SAFE_MODE suppressed the camera
            entirely or it failed to open (see module docstring on camera
            failures never blocking actuation). Note this count can be
            nonzero even when no alert fired - the vision check runs before
            decide(), not after (module docstring's "seismic wakes vision"
            ordering) - but those frames are only ever saved via
            save_frames() on an alert.
        trigger_to_first_frame_s: Seconds between entering this event
            handler and the first captured frame's own timestamp, or None
            if no frame was captured. Instrumentation only - see
            docs/KNOWN_GAPS.md on why this loop measures this instead of
            running a continuous rolling pre-event buffer.
        suppressed_by_vision: True when decide() said alert and the
            deterrent was held anyway because the camera looked and found no
            elephant (ADR 0022 Decision B). Distinct from a plain no-alert
            event: the seismic evidence *was* sufficient, and vision
            overruled it. False whenever vision was blind - see
            _vision_could_see.
        vision_polls: How many detection passes the watch window ran
            (ADR 0022). 1 is the pre-watch behaviour and the safe_mode
            value; higher means the window actually kept looking.
        vision_watch_s: The window length _watch_length_s() granted this
            trigger, before any early exit. 0.0 under safe_mode. Reported
            so a field log can show which triggers earned the long look and
            whether the long look was what found the elephant.
        vision_confirmed: True only if the pre-decision vision check
            returned at least one detection labeled VISION_TARGET_LABEL.
            Distinct from `fusion` reporting VISION as used: a check that
            found nothing is still "used" (it scores at BASELINE_VISION and
            contributes zero net evidence) but is not a confirmation. Half
            of ADR 0020's keep-gate, and always False under safe_mode,
            which runs no vision check at all.
        video_path: Where this event's recording was committed, or None -
            which covers "no event_video was injected" (the default),
            "recorded but discarded as unconfirmed", and "the commit
            failed". Never a path to a file that was subsequently deleted:
            nothing in this loop or in perception/storage.py removes a
            committed capture (ADR 0020 Decision C).
    """

    fusion: FusionResult
    decision: Decision
    repeat_count: int
    context: int | None
    action: DeterrenceAction | None
    exploring: bool | None
    settled: SettledAttempt | None
    horn_ack: bool | None
    led_ack: bool | None
    ir_ack: bool | None
    capture_frame_count: int
    trigger_to_first_frame_s: float | None
    vision_confirmed: bool
    video_path: Path | None
    vision_polls: int = 1
    vision_watch_s: float = 0.0
    suppressed_by_vision: bool = False


@dataclass(frozen=True)
class AcousticOutcome:
    """What one handle_acoustic_event() call routed and computed.

    Returned (rather than left as a side effect only) so tests can assert on
    it directly, matching FootfallOutcome's own rationale above - and in
    particular so ADR 0007 5's rule that gunshot never reaches fuse() is
    provable from a returned value rather than inferred from log text.

    Attributes:
        class_label: The AcousticClass this event carried, echoed back so a
            caller can branch on which route was taken without re-deriving
            it from the input.
        fusion: The FusionResult fuse() produced for this event, or None on
            the gunshot branch, which never calls fuse() at all (ADR 0007
            5). None here means "never fused", never "fused to nothing" -
            an event that fused with the acoustic modality unavailable
            still carries a real FusionResult.
        direct_alert: True only for gunshot: this event took the direct
            anti-poaching alert path instead of the elephant-presence one.
            The alert is logged rather than sent - see
            handle_acoustic_event()'s docstring for why.
        lora_ack: send_lora_alert's returned ack, or None if it was never
            called (non-gunshot class, or safe_mode suppressed it). True
            today would still only mean "queued/logged on the MCU", never
            "delivered" - no real LoRa transport exists yet.
    """

    class_label: AcousticClass
    fusion: FusionResult | None
    direct_alert: bool
    lora_ack: bool | None


def _confidence_log_odds(probability: float) -> float:
    """Convert a detector's reported confidence into fusion's log-odds input.

    logit() rejects the closed interval's endpoints (0.0 and 1.0) - both are
    representable float values a wire probability could in principle carry,
    even though a real model realistically saturates just short of them.
    Clamping into an epsilon-narrowed open interval before calling logit()
    is a numerical safety guard here (same category as fusion.sigmoid()'s
    own two-branch overflow handling), not a policy choice - it changes
    nothing for any probability logit() would already have accepted
    unclamped.

    Shared by both wired modalities rather than duplicated per caller:
    report_footfall_event's `probability` and report_acoustic_event's
    `confidence` are the same kind of number arriving over the same Bridge,
    and the clamp is a property of logit(), not of either sensor.

    Args:
        probability: A detector's reported confidence, expected in
            [0.0, 1.0] - report_footfall_event's `probability` field or
            report_acoustic_event's `confidence` field.

    Returns:
        The log-odds logit() returns for the epsilon-clamped probability.
    """
    epsilon = 1e-9
    clamped = min(max(probability, epsilon), 1.0 - epsilon)
    return logit(clamped)


@dataclass(frozen=True)
class VisionCheck:
    """What one pre-decision vision pass produced.

    Two values rather than one because ADR 0020 needs a question fuse()
    never asked: not "how much evidence is this worth" but "did the camera
    actually see an elephant". The fused log-odds cannot answer that on its
    own - a no-qualifying-detection reading scores at BASELINE_VISION,
    which is a real, deliberate value, not a sentinel - so `confirmed` is
    carried separately instead of being reverse-engineered from `reading`.

    Attributes:
        reading: The VISION ModalityReading handed to fuse().
        confirmed: True only when the detector returned at least one
            detection whose label is in VISION_TARGET_LABELS. False covers
            all three of "no frames", "the detector failed", and "boxes
            found, none of them a target" - none of those is a
            confirmation.
        species: Every distinct label this pass saw, in first-seen order,
            whether or not it counts as a target. Carried because the
            question "should this event's video be kept" is not the same
            question as "should the horn fire" once boar is configured for
            one and not the other, and re-running the detector to answer
            the second one would be both slower and capable of
            disagreeing with the first.
    """

    reading: ModalityReading
    confirmed: bool
    species: tuple[str, ...] = ()


def _requires_burst_majority(label: str) -> bool:
    """Whether `label` needs a strict majority of a burst's frames, not just one.

    Thin wrapper around services_config.VISION_SPECIES_BURST_MAJORITY_LABELS,
    the sibling lookup to _required_consecutive_polls() just below -
    same reasoning, same per-label shape, different axis of the same
    problem (within one burst, rather than across polls).
    """
    return label in services_config.VISION_SPECIES_BURST_MAJORITY_LABELS


def _vision_check(
    detect_vision: VisionDetectFn,
    frames: list[Frame],
    target_labels: tuple[str, ...] = VISION_TARGET_LABELS,
) -> VisionCheck:
    """Convert a vision-check burst into one VISION ModalityReading; never raises.

    Three cases:

    - No frames to check (camera never opened, or capture failed/returned
      empty - _capture_burst() already logged why): available=False. This is
      the only "vision had nothing to say" case - matching
      perception.camera.CameraError's own "degrade loudly, don't block"
      discipline, not a policy choice about the model's evidence.
    - detect_vision() itself fails (network/timeout/bad response,
      perception.detector.DetectionError): logged and treated identically -
      available=False. A detector outage must not block or bias the alert
      decision any more than a dark lens would.
    - detect_vision() succeeds: whether a label counts for anything at all -
      species membership, confirmation, the fused reading - depends on
      services_config.VISION_SPECIES_BURST_MAJORITY_LABELS
      (_requires_burst_majority()). For a listed label, it must appear on
      **more than half** of this burst's frames; for every other label -
      the default, including Elephant - one frame is enough, exactly as
      before this gate existed. Only detections whose label both qualifies
      this way and is in target_labels count as a match. If at least one
      qualifies, log-odds is logit() of the *strongest* qualifying match's
      own reported confidence (the same direct, non-invented transformation
      _confidence_log_odds() already uses for seismic/acoustic). If none
      qualify - including the case where detect_vision() found real boxes,
      just none that were both target-labeled and qualified - the reading
      is still available=True, scored at cognition.config.BASELINE_VISION.

      The majority gate is not the original design; it was added on
      3 Sept 2026, scoped to Boar only, after a real 2-hour board run
      showed the previous flat OR-across-the-burst reading (any qualifying
      box on any one frame, for every label alike) actively amplifies
      Boar false positives rather than filtering them: a poll-level Boar
      false-positive rate of 43.64%, *worse* than the 31.53% raw-frame rate
      it was built from, because a single spurious box on one frame of a
      3-frame burst was scored identically to the same box appearing on
      all three. Requiring a majority recovered nearly all of that loss on
      its own (down to 30.70%), and combines with
      VISION_SPECIES_CONSECUTIVE_POLLS' poll-level debounce (which this
      function has no part in - that lives in _watch_for_vision) to reach
      27.54% - see docs/qa/boar-gap-session-notes.md for the full replay.
      This is a real, measured accuracy fix for Boar specifically, not a
      code-cleanliness one - a test that constructs a burst with "Boar" on
      only one of several frames must see it excluded from both species
      and confirmation.

      Elephant is deliberately left on the one-frame-is-enough default,
      not majority-gated too. Elephant's measured recall (0.906,
      docs/KNOWN_GAPS.md) is already below the field-readiness bar, the
      same run that found Boar's 31.53% false-positive rate found *zero*
      Elephant false positives, and a missed real elephant is the
      safety-relevant failure this system exists to avoid - so there is no
      precision problem on Elephant to trade recall against. A test that
      constructs a burst with "Elephant" on only one of several frames
      must still see it included, unchanged from every pre-3-Sept-2026
      test that already asserts this.

      That baseline choice is deliberate, not a default: Edge Impulse only
      ever reports a box once it already clears the deployed model's own
      confidence threshold (perception.detector.Detection's own docstring),
      so "no qualifying box" cannot be read back into a specific probability
      the model actually supports - there is no scalar here to convert.
      Scoring it at BASELINE_VISION - the same log-odds this formula already
      uses for "a quiescent background frame" - makes an unconfirmed vision
      check contribute *zero* net evidence to the fused probability
      (weight * (baseline - baseline) == 0), which is the honest middle
      ground between "ignore it" (available=False, the camera-failure case)
      and inventing a specific negative number this detector cannot back up.
      See cognition/config.py's own BASELINE_VISION comment.

    Args:
        detect_vision: Callable matching perception.detector.VisionDetectFn.
        frames: The vision-check burst - Frame objects, not raw images;
            this function extracts .image itself so callers never have to.
        target_labels: Which of the model's classes count as
            target-presence evidence. Defaults to VISION_TARGET_LABELS,
            i.e. services.config.DETERRENT_TARGET_LABELS.

    Returns:
        A VisionCheck carrying the ModalityReading for Modality.VISION and
        whether this pass counts as a confirmation for ADR 0020's
        keep-gate. The three "no qualifying detection" cases above all
        report confirmed=False, whatever their reading.
    """
    if not frames:
        return VisionCheck(ModalityReading(Modality.VISION, 0.0, available=False), False)

    try:
        detections_by_frame: list[list[Detection]] = detect_vision(
            [frame.image for frame in frames]
        )
    except DetectionError as exc:
        logger.warning("vision detect failed, continuing without vision evidence: %s", exc)
        return VisionCheck(ModalityReading(Modality.VISION, 0.0, available=False), False)

    # Per-label burst gate - see this function's own docstring for why.
    # A majority-gated label needs "more than half" ("half or more" is not
    # enough - a tie does not count); every other label needs only one
    # frame, exactly the flat-OR behaviour this function had before the
    # gate existed, byte-for-byte, including on a single-frame burst where
    # "more than half" and "at least one" are the same threshold anyway.
    burst_size = len(detections_by_frame)
    label_frame_counts: dict[str, int] = {}
    for frame_detections in detections_by_frame:
        for label in dict.fromkeys(d.label for d in frame_detections):
            label_frame_counts[label] = label_frame_counts.get(label, 0) + 1
    qualifying_labels = {
        label
        for label, count in label_frame_counts.items()
        if count >= (burst_size // 2 + 1 if _requires_burst_majority(label) else 1)
    }

    # Order-preserving dedupe: the log and the video gate both read this,
    # and a stable order makes two events with the same cast compare equal
    # in a field log instead of differing by detector ordering.
    species = tuple(
        dict.fromkeys(
            d.label
            for frame_detections in detections_by_frame
            for d in frame_detections
            if d.label in qualifying_labels
        )
    )

    matches = [
        d
        for frame_detections in detections_by_frame
        for d in frame_detections
        if d.label in target_labels and d.label in qualifying_labels
    ]
    if not matches:
        return VisionCheck(
            ModalityReading(Modality.VISION, cognition_config.BASELINE_VISION, available=True),
            False,
            species,
        )

    best_confidence = max(d.confidence for d in matches)
    return VisionCheck(
        ModalityReading(Modality.VISION, _confidence_log_odds(best_confidence), available=True),
        True,
        species,
    )


@dataclass(frozen=True)
class VisionWatch:
    """What one bounded watch window produced (ADR 0022).

    Attributes:
        check: The strongest VisionCheck any poll in the window produced -
            a confirmation if one ever happened, otherwise the best
            available reading, otherwise the unavailable one. This is the
            reading handed to fuse().
        frames: The frames worth keeping from the window - the first poll's
            burst (which dates the event and which the night decision
            reads) plus, when the watch confirmed, the burst that actually
            confirmed. Deliberately not every frame the window captured: a
            45s watch at one poll per second is over a hundred 720p frames,
            several hundred megabytes held live, when only two bursts of it
            are ever used.
        polls: How many detection passes ran. Always at least one, so a
            zero-length window behaves exactly like the single pre-ADR-0022
            burst.
        elapsed_s: Monotonic seconds from the first poll to the last.
        confirmed_on_poll: 1-based index of the poll that confirmed, or
            None if none did. Logged rather than acted on - it is the one
            number that says whether the window length is earning its cost,
            and there is no field data behind that length yet.
        species: Every distinct label seen across the *whole* window, in
            first-seen order - not just the labels on `check`. The union
            matters: a boar that walks through on poll 2 and is gone by the
            poll that ends the watch is still a boar this node saw, and
            under the "record boar, deter elephants" configuration that
            sighting is the entire reason the recording is worth keeping.
    """

    check: VisionCheck
    frames: tuple[Frame, ...]
    polls: int
    elapsed_s: float
    confirmed_on_poll: int | None
    species: tuple[str, ...] = ()

    @property
    def reading_available(self) -> bool:
        """Whether any poll produced a reading fuse() will actually score."""
        return self.check.reading.available


def _watch_length_s(
    *,
    repeat_count: int,
    seismic_alone_alerts: bool,
    base_s: float = services_config.VISION_WATCH_BASE_S,
    extended_s: float = services_config.VISION_WATCH_EXTENDED_S,
) -> float:
    """Decide how long this trigger has earned the camera for (ADR 0022).

    Two conditions extend the window, and both are values already computed
    for other reasons, so neither costs a sensor read:

    - `repeat_count > 0`: another qualifying trigger arrived at this node
      within HABITUATION_WINDOW_S. That is the closest thing this device
      has to "the footfall event is still happening" - the encounter is
      live, something is moving out there, and it is worth staying on the
      camera rather than glancing once and sleeping. It is the same signal
      escalation_floor() already trusts to raise the deterrence tier.
    - `seismic_alone_alerts`: the geophone evidence on its own already
      clears the alert threshold, so this event is going to fire whether or
      not vision ever confirms. Given that, the only question left is *when*
      to fire it, and firing with the animal in frame is both better
      deterrence (the horn goes off at boundary range rather than at the
      140m the geophone reaches) and the only way the event produces usable
      footage. See ADR 0022 - that is a real reversal of ADR 0020, not a
      refinement of it.

    Everything else - a lone, weak, unrepeated trigger - gets base_s. That
    is the wind-and-cattle case, and it is the one that has to stay cheap.

    Args:
        repeat_count: Triggers inside the habituation window before this
            one, as returned by ExperienceStore.record_trigger().
        seismic_alone_alerts: Whether decide() says alert on the seismic
            reading alone, with vision reported unavailable.
        base_s: Window for a trigger that qualifies for neither condition.
        extended_s: Window for one that qualifies for either.

    Returns:
        Seconds to watch. Never less than base_s.
    """
    if repeat_count > 0 or seismic_alone_alerts:
        return max(base_s, extended_s)
    return base_s


def _required_consecutive_polls(label: str) -> int:
    """Consecutive watch polls `label` must appear on before it is admitted.

    Thin wrapper around services_config.VISION_SPECIES_CONSECUTIVE_POLLS so
    the default (1 - admit on first sight) lives in one place rather than
    being repeated at every call site. See that constant's own comment for
    why this exists and what it does and does not gate.
    """
    return services_config.VISION_SPECIES_CONSECUTIVE_POLLS.get(label, 1)


def _watch_for_vision(
    camera: CameraProtocol,
    detect_vision: VisionDetectFn,
    *,
    trigger_monotonic: float,
    watch_s: float,
    poll_interval_s: float = services_config.VISION_WATCH_POLL_INTERVAL_S,
    frame_count: int = services_config.VISION_CHECK_FRAME_COUNT,
    max_empty_polls: int = services_config.VISION_WATCH_MAX_EMPTY_POLLS,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> VisionWatch:
    """Poll vision repeatedly until it confirms or the window closes; never raises.

    Replaces the single pre-decision burst. The reason is in
    services/config.py's VISION_WATCH_BASE_S comment and in ADR 0022: the
    geophone reaches 140m and the camera does not, so at the instant of the
    trigger the animal is usually nowhere near the frame, and one glance two
    seconds later answers a question nobody asked.

    Three ways out, in priority order:

    1. **A confirmation.** Returns immediately, without sleeping out the
       rest of the window. This is the case the function exists for: the
       caller fires the deterrence sequence at this moment, which is the
       moment the elephant is actually in frame.
    2. **The window closes.** Returns the strongest reading seen. The caller
       then decides on seismic alone, exactly as it did before this function
       existed - a watch that finds nothing costs time, never a changed
       decision.
    3. **`max_empty_polls` consecutive polls return no frames.** The camera
       has stopped delivering, and there is nothing to gain by holding the
       actuators behind it for the rest of the window. Logged, then treated
       as case 2 with whatever was seen before the failure.

    At least one poll always runs, whatever `watch_s` is, so `watch_s=0.0`
    reproduces the old single-burst behaviour rather than skipping vision.

    `monotonic` and `sleep` are injected for the same reason the RNG is: a
    test needs to drive a 45-second window deterministically in
    milliseconds, and patching the clock module-wide would be a worse seam.

    Args:
        camera: An already-opened CameraProtocol.
        detect_vision: Callable matching perception.detector.VisionDetectFn.
        trigger_monotonic: When this event's handling began - the reference
            point for the logged first-frame latency.
        watch_s: How long to keep polling, measured from the first poll.
        poll_interval_s: Start-to-start spacing between polls. A poll that
            overruns is not compensated for; the next simply starts late.
        frame_count: Frames per poll, handed to capture_burst().
        max_empty_polls: Consecutive empty polls that end the watch.
        monotonic: Clock source. Injected for tests.
        sleep: Sleep function. Injected for tests.

    Returns:
        A VisionWatch. `check` is never None - a window in which every poll
        failed still reports the unavailable reading _vision_check() builds
        for an empty burst, which fuse() drops rather than scores.
    """
    started = monotonic()
    deadline = started + max(watch_s, 0.0)

    first_frames: list[Frame] = []
    best = VisionCheck(ModalityReading(Modality.VISION, 0.0, available=False), False)
    polls = 0
    empty_polls = 0
    # dict rather than set: insertion-ordered, so the union stays in
    # first-seen order across polls the way one pass's own list does.
    #
    # A label enters seen_species only once it has been seen on
    # VISION_SPECIES_CONSECUTIVE_POLLS[label] (default 1) consecutive polls
    # - see _required_consecutive_polls(). species_streaks tracks the
    # running per-label consecutive count independently of seen_species so
    # a label can be dropped from a streak (a gap poll resets it to 0)
    # without ever being removed from seen_species once admitted: the
    # streak gate controls entry, not membership.
    seen_species: dict[str, None] = {}
    species_streaks: dict[str, int] = {}

    while True:
        poll_started = monotonic()
        polls += 1
        frames = _capture_burst(camera, trigger_monotonic, count=frame_count)

        if not frames:
            empty_polls += 1
            if empty_polls >= max_empty_polls:
                logger.warning(
                    "vision watch abandoned after %d consecutive empty polls "
                    "(%.1fs into a %.1fs window) - proceeding on seismic alone",
                    empty_polls,
                    poll_started - started,
                    watch_s,
                )
                break
        else:
            empty_polls = 0
            if not first_frames:
                first_frames = frames
            check = _vision_check(detect_vision, frames)
            for label in list(species_streaks):
                if label not in check.species:
                    species_streaks[label] = 0
            for label in check.species:
                species_streaks[label] = species_streaks.get(label, 0) + 1
                if species_streaks[label] >= _required_consecutive_polls(label):
                    seen_species.setdefault(label, None)
            if check.confirmed:
                logger.info(
                    "vision confirmed on poll %d, %.1fs into a %.1fs watch window",
                    polls,
                    monotonic() - started,
                    watch_s,
                )
                # Identity, never equality. Frame is a frozen dataclass
                # whose .image is a numpy ndarray in production, so
                # `f not in first_frames` would compare arrays elementwise
                # and then call bool() on the result - ValueError, raised
                # at the exact instant vision confirms an elephant. A
                # confirmation on the first poll happens to survive it
                # (list.__contains__ tries `is` before `==`); a
                # confirmation on any later poll, which is the case this
                # whole function exists for, would not.
                seen = {id(f) for f in first_frames}
                kept = first_frames + [f for f in frames if id(f) not in seen]
                return VisionWatch(
                    check=check,
                    frames=tuple(kept),
                    polls=polls,
                    elapsed_s=monotonic() - started,
                    confirmed_on_poll=polls,
                    species=tuple(seen_species),
                )
            # An available-but-unconfirmed reading beats the unavailable one
            # this started with: it means the camera and the detector both
            # worked and neither saw an elephant, which is real evidence
            # scored at BASELINE_VISION, not an outage fuse() should drop.
            if check.reading.available and not best.reading.available:
                best = check

        now = monotonic()
        if now >= deadline:
            break
        # Start-to-start pacing: a poll that overran its slot goes straight
        # into the next rather than adding its overrun to the window.
        remaining_to_next = poll_interval_s - (now - poll_started)
        if remaining_to_next > 0:
            sleep(min(remaining_to_next, deadline - now))

    elapsed_s = monotonic() - started
    if polls > 1:
        logger.info(
            "vision watch closed unconfirmed after %d polls over %.1fs (window %.1fs)",
            polls,
            elapsed_s,
            watch_s,
        )
    return VisionWatch(
        check=best,
        frames=tuple(first_frames),
        polls=polls,
        elapsed_s=elapsed_s,
        confirmed_on_poll=None,
        species=tuple(seen_species),
    )


def _worth_filming(watch: VisionWatch) -> bool:
    """Whether this event saw something services.config says to keep footage of.

    Separate from `confirmed` because the two lists are deliberately allowed
    to differ. Under the "record boar, deter elephants" configuration a boar
    sighting is not a confirmation - it must not fire the horn, must not
    feed fuse() as target evidence - but it is precisely the footage worth
    keeping, because it is the evidence for whether boar deterrence is worth
    building at all.

    Reads the watch's union rather than the winning check's own species, so
    an animal that appeared on one poll and was gone by the last still
    counts. See VisionWatch.species.

    Args:
        watch: The completed watch window.

    Returns:
        True if any label seen anywhere in the window is in
        VISION_VIDEO_LABELS.
    """
    return any(label in VISION_VIDEO_LABELS for label in watch.species)


def _vision_could_see(
    watch: VisionWatch,
    night_of_event: Callable[[], bool | None],
    *,
    illuminated: bool = False,
) -> bool:
    """Whether this event's vision had a real chance of seeing an elephant.

    The distinction ADR 0022 Decision B turns on, and the reason that
    decision is safe at all: "the camera looked and there was nothing there"
    and "the camera could not look" are opposite pieces of evidence, and
    only the first of them is a reason not to fire the deterrent.

    Three ways vision can be blind, all of which report False here and all
    of which hand the decision back to seismic alone:

    - **The camera or the detector failed.** _vision_check() already reports
      that as available=False, for both the no-frames case and the
      DetectionError case. Nothing on this board supervises the
      edge-impulse-linux-runner process (docs/KNOWN_GAPS.md), so a dead
      inference server is a real and currently symptomless failure - gating
      the horn on its output without this check would turn it into a silent
      total loss of deterrence.
    - **No frames at all.** Covered by the same available=False, but stated
      separately because it is the camera-never-opened case rather than a
      mid-event fault.
    - **Night, with the illuminator not yet fired.** This is the one that
      actually matters in the field and the one that is easiest to miss: at
      night the camera works perfectly and returns dark frames, so vision
      reports available=True and confirmed=False - "I looked, nothing
      there" - about an elephant it physically cannot see. pulse_ir() only
      fires for tiers 2 and 3, after decide() has already run
      (docs/KNOWN_GAPS.md, the 29-30 Aug entry), so during the watch the
      illuminator is off and this is every night event. Left unhandled, a
      confirmation-gated deterrent would go quiet from dusk to dawn, which
      is when almost all raiding happens. Treating it as blindness rather
      than as absence is what keeps ADR 0022 Decision B from silently
      disabling the system every night.

    frames_are_night() returning None - no frame in the burst could be
    measured - is treated as night here, not as day. The conservative
    direction for this particular question is the one that keeps the
    deterrent firing.

    Args:
        watch: The completed watch window.
        night_of_event: Zero-argument reader for this event's day/night
            answer. Zero-argument rather than the NightDecideFn itself so
            the caller owns both *when* the image work happens - this
            function is the last operand of a short-circuiting condition,
            and a confirmed event never pays for it - and the fact that it
            happens only once, shared with the pulse_ir gate that asks the
            same question about the same frames later in the event.
        illuminated: True if the IR illuminator was firing during the
            watch. Always False today; the parameter exists so the
            proactive-illumination work docs/KNOWN_GAPS.md tracks has an
            obvious place to land rather than having to re-derive this
            logic.

    Returns:
        True only if the camera and detector both worked and the scene was
        one the model could actually have classified.
    """
    if not watch.reading_available or not watch.frames:
        return False
    if illuminated:
        return True
    try:
        night = night_of_event()
    except Exception as exc:  # noqa: BLE001 - a night heuristic must not crash the event
        logger.warning("night check failed, treating vision as blind: %s", exc)
        return False
    return night is False


def _open_camera(camera: CameraProtocol) -> bool:
    """Open the camera; never raises.

    A camera failure here must never suppress or delay the actuator calls
    that follow it - see module docstring. Logged and treated as "no
    footage this event," not escalated.

    Returns:
        True if the camera opened and should later be closed, False if
        open() failed (nothing to close).
    """
    try:
        camera.open()
        return True
    except CameraError as exc:
        logger.warning("camera open failed, continuing without footage: %s", exc)
        return False


def _capture_burst(
    camera: CameraProtocol,
    trigger_monotonic: float,
    count: int = services_config.CAMERA_BURST_FRAMES,
) -> list[Frame]:
    """Grab a burst from an already-opened camera; never raises.

    Only called once _open_camera() has already succeeded - a
    capture_burst() failure here is logged the same way an open() failure
    is, and still leaves the caller responsible for closing the camera.
    Called twice per real alert event with two different counts - the
    pre-decision vision check (count=VISION_CHECK_FRAME_COUNT) and, only if
    the event goes on to alert, the illuminated evidence burst
    (count=CAMERA_BURST_FRAMES, the default) - each call logs its own
    trigger-to-first-frame latency independently.

    Args:
        camera: An already-opened CameraProtocol.
        trigger_monotonic: Reference point for the logged latency - the
            monotonic time this event's handling began, not the time of
            this particular call.
        count: Frames to request. Defaults to CAMERA_BURST_FRAMES (the
            evidence-burst size); the vision-check call overrides this to
            services_config.VISION_CHECK_FRAME_COUNT.

    Returns:
        The captured frames, or [] if capture_burst() failed.
    """
    try:
        frames = camera.capture_burst(count, services_config.CAMERA_BURST_INTERVAL_S)
    except CameraError as exc:
        logger.warning("camera capture failed, continuing without footage: %s", exc)
        return []

    if frames:
        latency_s = frames[0].timestamp_s - trigger_monotonic
        logger.info("trigger-to-first-frame latency: %.3fs", latency_s)
    return frames


def _close_camera(camera: CameraProtocol) -> None:
    """Close the camera after the deterrent sequence + tail; never raises."""
    try:
        camera.close()
    except CameraError as exc:
        logger.warning("camera close failed: %s", exc)


def _save_captured_frames(
    save_frames: SaveFramesFn, frames: list[Frame], tag: CaptureEventTag
) -> None:
    """Persist a burst; never raises - a storage fault must not crash the event handler.

    Deliberately broad except: by this point the deterrents have already
    fired (see the caller's sequencing), so nothing time-critical is still
    waiting on this call, and an unanticipated storage-layer exception
    (disk-full errno flavors vary by filesystem, permission faults, etc.)
    is exactly the kind of thing "log and continue" should cover, same as
    the camera-failure paths above.
    """
    if not frames:
        return
    try:
        save_frames(frames, tag)
    except Exception as exc:  # noqa: BLE001 - see docstring
        logger.warning("failed to save capture burst for this event: %s", exc)


def _finish_event_video(
    event_video: EventVideoProtocol | None, *, keep: bool, tag: CaptureEventTag
) -> Path | None:
    """Commit or discard this event's recording (ADR 0020); never raises.

    One function rather than two call sites per exit so the keep-gate is
    written once and every exit is forced to state its verdict explicitly -
    an exit that forgets to call this would silently leak a scratch file,
    and `keep` being a required keyword makes "I did not think about it"
    unrepresentable.

    Broad except for the same reason _save_captured_frames has one, and
    with more force: the deterrents have already fired, the camera is
    already closed, and perception/video.py's commit/discard are documented
    as never raising - so anything that arrives here is unanticipated, and
    crashing the event handler over evidence housekeeping would cost the
    next real event.

    Args:
        event_video: The recorder, or None when video is disabled (the
            default) - in which case this does nothing at all.
        keep: The already-evaluated keep-gate, "vision confirmed OR alert
            fired". False deletes the recording from scratch; it never
            touches anything already committed.
        tag: Event metadata, used only when keeping, to name the file.

    Returns:
        The committed path, or None - which covers "no recorder", "kept but
        the commit failed", and every discard.
    """
    if event_video is None:
        return None
    try:
        if keep:
            return event_video.commit(tag)
        event_video.discard()
    except Exception as exc:  # noqa: BLE001 - see docstring
        logger.warning(
            "event video %s failed for this event: %s", "commit" if keep else "discard", exc
        )
    return None


def handle_footfall_event(
    schema_version: int,
    probability: float,
    sta_lta_ratio: float,
    feature_vector: list[float],
    *,
    drive_horn: DriveHornFn,
    drive_led: DriveLedFn,
    pulse_ir: PulseIrFn,
    is_night: NightDecideFn,
    camera: CameraProtocol,
    detect_vision: VisionDetectFn,
    save_frames: SaveFramesFn,
    experience: ExperienceStoreProtocol,
    event_video: EventVideoProtocol | None = None,
    safe_mode: bool = SAFE_MODE,
    threshold: float = ALERT_PROBABILITY_THRESHOLD,
    capture_post_fire_tail_s: float = CAPTURE_POST_FIRE_TAIL_S,
    video_retreat_tail_s: float = services_config.EVENT_VIDEO_RETREAT_TAIL_S,
    vision_watch_base_s: float = services_config.VISION_WATCH_BASE_S,
    vision_watch_extended_s: float = services_config.VISION_WATCH_EXTENDED_S,
    vision_watch_poll_interval_s: float = services_config.VISION_WATCH_POLL_INTERVAL_S,
    require_vision_confirmation: bool = (
        services_config.DETERRENT_REQUIRES_VISION_CONFIRMATION
    ),
    bandit_params: BanditParams = cognition_config.DEFAULT_BANDIT_PARAMS,
    rng: random.Random = _DEFAULT_RNG,
    household_proximity: bool = services_config.NODE_HOUSEHOLD_PROXIMITY,
) -> FootfallOutcome:
    """Sense -> fuse -> decide -> actuate for one report_footfall_event notify.

    Precondition: none - schema_version mismatches are logged, not raised,
    matching report_footfall_event's own notify contract (bridge/rpc.py):
    the MCU never reads a return value from this path, so raising here would
    only crash the MPU's own event loop over a field it cannot act on
    anyway. Never blocks past the drive_horn/drive_led/pulse_ir
    Bridge.call()s (services.config.BRIDGE_CALL_TIMEOUT_S each, enforced
    inside the injected callables, not here) plus two capture bursts, one
    detect_vision() call and a fixed CAPTURE_POST_FIRE_TAIL_S tail, or not at
    all when safe_mode is true.

    Outside safe_mode, camera.open() and a bounded *watch* -
    _watch_for_vision(), repeated capture_burst() + detect_vision() passes
    rather than the single burst this handler ran before ADR 0022 - happen
    on every footfall event, alert or not. Vision runs *before*
    fuse()/decide(), not only after an alert already fired on other evidence
    (module docstring's "seismic wakes vision" ordering). The watch returns
    the instant vision confirms, so on a confirmed event the deterrence
    sequence fires with the animal actually in frame. If decide() says no
    alert, the camera closes immediately and nothing else happens. If it
    says alert: [pulse_ir() on its own thread, concurrent with a second
    capture_burst() for the illuminated evidence footage, skipped entirely
    on tier 1] -> drive_horn() -> drive_led() -> sleep(the tail) ->
    camera.close() -> save_frames() with both bursts combined. The camera
    opens once at the top of the event and is only ever closed, once,
    whichever exit the event takes (module docstring). safe_mode=True skips
    the camera and the watch entirely - see module docstring for the honest
    cost of that. A camera or vision-detection failure at any point is
    logged and never allowed to suppress the actuator calls that follow it.

    The one thing ADR 0022 does change about that guarantee is *delay*: a
    trigger whose seismic evidence would alert on its own now waits for the
    watch to confirm or expire before firing, up to vision_watch_extended_s.
    That is a deliberate reversal of ADR 0020's "actuators are never delayed
    behind the confirm window", argued in ADR 0022 and bounded by ADR 0008's
    own worst-case lead time so the expiry fire still beats a fast-moving
    animal to the boundary. A failure never delays anything: the watch
    abandons after VISION_WATCH_MAX_EMPTY_POLLS empty polls.

    Which tier fires is the bandit's choice, made after decide() and before
    any actuator call. The trigger is recorded and any pending attempt
    settled before the alert gate, so a sub-threshold event still counts
    toward habituation - see the module docstring for why both of those
    orderings matter.

    Args:
        schema_version: As received from the MCU; logged if it does not
            match services.config.SCHEMA_VERSION.
        probability: The on-MCU footfall model's confidence, 0-1.
        sta_lta_ratio: STA/LTA ratio at the moment of trigger - logged for
            explainability, not otherwise used (fuse() takes log-odds, not
            a raw ratio).
        feature_vector: The 8 features behind `probability` - logged for
            explainability only, same reason as sta_lta_ratio.
        drive_horn: Callable matching bridge.rpc.drive_horn's signature.
        drive_led: Callable matching bridge.rpc.drive_led's signature.
        pulse_ir: Callable matching bridge.rpc.pulse_ir's signature.
        is_night: Callable matching NightDecideFn. Given the pre-decision
            vision-check burst, returns True if those frames were captured
            with the camera's IR-cut filter open (night - the external
            illuminator will actually land on a sensitive sensor), False in
            daylight, None if not one frame could be measured. An escalated
            tier's pulse_ir() fires only on True; False and None both
            suppress it for the event (logged, nothing else about the tier
            changes). main.py binds perception.night.frames_are_night;
            tests pass a stub.
        camera: Object matching CameraProtocol (open/capture_burst/close).
            Opened once and closed once per event (outside safe_mode), never
            across events.
        detect_vision: Callable matching perception.detector.VisionDetectFn.
            Called once per event, against the pre-decision vision-check
            burst, outside safe_mode only. main.py binds this to a real
            perception.detector.HttpVisionDetector; tests pass a recording
            fake.
        save_frames: Callable matching perception.storage.save_burst's
            signature. Called once per alert event with whatever frames
            were captured across both bursts (skipped entirely if none
            were).
        experience: Object matching ExperienceStoreProtocol. Carries the
            bandit's learned values and trigger history across events and
            across restarts; the only cross-event state this loop has.
            All seven above are injected so this function needs no board,
            camera, HTTP inference server or database attached to test -
            device/mpu/main.py wires the real Bridge.calls, Camera,
            HttpVisionDetector, save_burst and ExperienceStore in; tests
            pass recording fakes.
        event_video: Optional object matching EventVideoProtocol - in
            practice the same perception.video.EventVideoRecorder instance
            passed as `camera`, since one V4L2 device cannot be held twice.
            None (the default) disables ADR 0020's event video entirely and
            leaves this function's behaviour byte-for-byte what it was
            before that ADR; device/mpu/main.py only wires one in when
            services.config.EVENT_VIDEO_ENABLED is true. Never opened,
            started or stopped here - only committed or discarded.
        safe_mode: When true (the default, SAFE_MODE), the decision and the
            selected tier are logged but none of drive_horn/drive_led/
            pulse_ir/camera/detect_vision/save_frames are ever called, and
            no attempt is recorded. event_video is not touched either:
            nothing opened the camera, so there is no recording to decide
            about. The trigger itself is still recorded - a
            dry run observes real events, it just does not respond to them.
        threshold: Passed to cognition.decision.decide(). Defaults to
            ALERT_PROBABILITY_THRESHOLD (see that constant's own comment).
        capture_post_fire_tail_s: Seconds to wait after the actuator
            sequence before closing the camera. Defaults to
            CAPTURE_POST_FIRE_TAIL_S; overridable so tests don't have to
            sleep for real. Ignored when `event_video` is set - see below.
        video_retreat_tail_s: Replaces capture_post_fire_tail_s when
            `event_video` is not None, so the recording runs long enough to
            show the animal leaving rather than stopping two seconds after
            the horn (services.config.EVENT_VIDEO_RETREAT_TAIL_S, 45s).
            Replaces rather than adds: one tail, one meaning. This handler
            genuinely blocks for the whole of it, which is stated plainly
            here because it is a real cost, not a footnote - a footfall
            notify arriving inside the tail waits. Overridable so tests
            don't have to sleep for real.
        vision_watch_base_s: How long the pre-decision vision watch runs for
            an ordinary trigger (ADR 0022,
            services.config.VISION_WATCH_BASE_S). 0.0 collapses the watch
            back to the single burst this handler did before that ADR - the
            watch always runs at least one poll - which is both the escape
            hatch and how most tests here keep running in milliseconds.
        vision_watch_extended_s: How long it runs for a trigger that earned
            a longer look - a repeat inside the habituation window, or
            seismic evidence that clears `threshold` on its own. See
            _watch_length_s.
        vision_watch_poll_interval_s: Start-to-start spacing between watch
            polls. See _watch_for_vision.
        require_vision_confirmation: ADR 0022 Decision B. When True (the
            default), a decide()-says-alert event still holds the horn and
            LEDs unless the watch confirmed an elephant *or* vision was
            blind (_vision_could_see). False restores the pre-ADR-0022
            behaviour of firing on the fused decision alone.
        bandit_params: Hyperparameters for selection and reward. Defaults to
            cognition.config.DEFAULT_BANDIT_PARAMS.
        rng: Source of the epsilon-greedy exploration draw. Defaults to a
            module-level random.Random; seed one and pass it for an exact,
            reproducible selection under test. Also feeds the per-fire horn
            track and Tier 3 LED pattern rotation (cognition.config.
            resolve_tier_action).
        household_proximity: This node's commissioning-time site attribute
            (services.config.NODE_HOUSEHOLD_PROXIMITY). True on nodes near
            homes; passed to cognition.config.resolve_tier_action so Tier 3
            plays a predator growl rather than a siren/firecracker near
            residents (ADR 0016 Decision B). Not sensed - injected here only
            so tests can exercise both site types.

    Returns:
        A FootfallOutcome carrying the fusion result, the decision, the
        selected action and its context, the three actuator acks, and this
        event's capture outcome.
    """
    if schema_version != services_config.SCHEMA_VERSION:
        logger.warning(
            "report_footfall_event: schema_version mismatch (got %d, expected %d)",
            schema_version,
            services_config.SCHEMA_VERSION,
        )

    # Shared reference point for both bursts this event may capture (the
    # pre-decision vision check below, and the post-alert evidence burst
    # further down) - taken once, up front, so trigger_to_first_frame_s stays
    # meaningful regardless of which burst actually produced the first frame.
    trigger_monotonic = time.monotonic()

    # One wall-clock reading for the whole event, taken up front. Wall clock
    # rather than monotonic because it has to stay comparable across the MPU
    # suspend/resume cycles ADR 0008 describes, and a single reading rather
    # than several so the trigger, the settlement and any recorded attempt
    # all agree on when this event happened - the reward is a difference
    # between two of these timestamps, so drift between them would be drift
    # in the reward itself.
    #
    # Taken *before* the vision watch, not after it as it was before ADR
    # 0022. Two reasons, both real: repeat_count is one of the two inputs to
    # how long this trigger gets watched, so it has to exist first; and the
    # event genuinely happened at the trigger, not up to
    # VISION_WATCH_EXTENDED_S later, so dating it here makes the habituation
    # window and the bandit's quiet-time reward more accurate rather than
    # less.
    event_wall_s = time.time()
    repeat_count = experience.record_trigger(event_wall_s, bandit_params.habituation_window_s)
    settled = experience.settle_pending(event_wall_s, bandit_params)

    seismic_reading = ModalityReading(
        Modality.SEISMIC, _confidence_log_odds(probability), available=True
    )
    # Acoustic: no reading in hand on this path. A footfall notify carries
    # none, and nothing correlates an acoustic event with this one across
    # time yet - acoustic fuses only on its own event, in
    # handle_acoustic_event(). Also deliberately not wired for the first
    # field trial at all, which is seismic + vision only (see module
    # docstring). See docs/KNOWN_GAPS.md.
    acoustic_reading = ModalityReading(Modality.ACOUSTIC, 0.0, available=False)

    # What this event decides on the geophone alone, computed before the
    # camera is even opened. Two pure function calls on readings that are
    # already built, so it costs nothing - and it answers the question
    # _watch_length_s() needs: is this trigger going to fire whatever vision
    # says? If it is, the only remaining question is *when*, and ADR 0022's
    # answer is "when the animal is in frame."
    seismic_alone = decide(
        fuse(
            [seismic_reading, acoustic_reading, ModalityReading(Modality.VISION, 0.0, False)],
            cognition_config.DEFAULT_FUSION_PARAMS,
        ),
        threshold,
    )

    # Seismic wakes vision, vision watches for the elephant across a bounded
    # window, and only then does the final fuse()/decide() run - the 28 Aug
    # "seismic wakes vision" ordering (module docstring), widened by ADR 0022
    # from one burst into a watch because the geophone reaches 140m and the
    # camera does not. Gated behind `not safe_mode` rather than running
    # unconditionally: SAFE_MODE's existing contract is that it suppresses
    # the camera entirely, not just the actuators
    # (test_safe_mode_suppresses_all_actuation_and_camera) - preserved here
    # at the documented cost that a SAFE_MODE log no longer previews exactly
    # what a live run of the same event would have decided (module
    # docstring).
    camera_opened = False
    watch_s = 0.0
    watch = VisionWatch(
        check=VisionCheck(ModalityReading(Modality.VISION, 0.0, available=False), False),
        frames=(),
        polls=1,
        elapsed_s=0.0,
        confirmed_on_poll=None,
        species=(),
    )
    if not safe_mode:
        camera_opened = _open_camera(camera)
        if camera_opened:
            watch_s = _watch_length_s(
                repeat_count=repeat_count,
                seismic_alone_alerts=seismic_alone.alert,
                base_s=vision_watch_base_s,
                extended_s=vision_watch_extended_s,
            )
            watch = _watch_for_vision(
                camera,
                detect_vision,
                trigger_monotonic=trigger_monotonic,
                watch_s=watch_s,
                poll_interval_s=vision_watch_poll_interval_s,
            )

    vision_check = watch.check
    vision_frames: list[Frame] = list(watch.frames)

    readings = [seismic_reading, acoustic_reading, vision_check.reading]
    fusion_result = fuse(readings, cognition_config.DEFAULT_FUSION_PARAMS)
    decision = decide(fusion_result, threshold)

    logger.info(
        "footfall event: mcu_probability=%.3f sta_lta_ratio=%.3f fused_P=%.3f "
        "alert=%s used=%s dropped=%s repeats_in_window=%d "
        "watch=%.1fs/%.1fs polls=%d confirmed_on=%s feature_vector=%s",
        probability,
        sta_lta_ratio,
        fusion_result.probability,
        decision.alert,
        [m.value for m in fusion_result.used],
        [m.value for m in fusion_result.dropped],
        repeat_count,
        watch.elapsed_s,
        watch_s,
        watch.polls,
        watch.confirmed_on_poll,
        feature_vector,
    )
    if settled is not None:
        logger.info(
            "settled previous attempt: context=%d tier=%d quiet=%.1fs "
            "proxy_reward=%.3f value=%.3f visits=%d (proxy is unvalidated - "
            "see cognition/bandit.proxy_reward)",
            settled.context,
            int(settled.tier),
            settled.gap_s,
            settled.reward,
            settled.value,
            settled.visits,
        )

    def _no_actuation_outcome(
        context: int | None = None,
        action: DeterrenceAction | None = None,
        exploring: bool | None = None,
        frames: tuple[Frame, ...] = (),
        video_path: Path | None = None,
    ) -> FootfallOutcome:
        trigger_to_first_frame_s = (
            frames[0].timestamp_s - trigger_monotonic if frames else None
        )
        return FootfallOutcome(
            fusion=fusion_result,
            decision=decision,
            repeat_count=repeat_count,
            context=context,
            action=action,
            exploring=exploring,
            settled=settled,
            horn_ack=None,
            led_ack=None,
            ir_ack=None,
            capture_frame_count=len(frames),
            trigger_to_first_frame_s=trigger_to_first_frame_s,
            vision_confirmed=vision_check.confirmed,
            video_path=video_path,
            vision_polls=watch.polls,
            vision_watch_s=watch_s,
            suppressed_by_vision=suppressed_by_vision,
        )

    # is_night() is a real image computation - an HSV conversion over the
    # whole burst (perception/night.py) - and ADR 0022 gave it a second
    # caller, the blindness gate immediately below, on top of the pulse_ir
    # gate much further down. Both ask the same question about the same
    # frames, so it runs at most once per event and both read that answer.
    #
    # Deliberately not caught in here: the two callers want *opposite*
    # conservative behaviour when the check fails - the blindness gate wants
    # "assume blind, let seismic fire", the IR gate wants "fire the
    # illuminator anyway" - so each handles its own failure and this only
    # guarantees the work is not repeated. Lazy for the same reason: an
    # event that vision confirmed short-circuits the gate below and never
    # touches this, which keeps the confirmed path (the common alert case
    # now) exactly as cheap as it was.
    _night_answer: list[bool | None] = []

    def _night_of_event() -> bool | None:
        if not _night_answer:
            _night_answer.append(is_night(vision_frames))
        return _night_answer[0]

    # ADR 0022 Decision B: seismic wakes and warns, vision fires.
    #
    # A geophone trigger means something heavy moved within 140m (ADR 0008).
    # It does not mean an elephant is at the boundary, or that it is even
    # coming this way. Firing the deterrent on that alone spends the horn on
    # an animal that is still deep in the forest and may never arrive - and
    # cognition/bandit.py's whole habituation model says the dominant
    # failure mode of a deterrent is firing where it achieves nothing, which
    # is exactly what teaches an elephant to ignore it. Holding the fire
    # until the camera has the animal in frame puts the burst at boundary
    # range, at something that is demonstrably there.
    #
    # The gate is deliberately narrow. It engages only when vision had a
    # real chance and took it - _vision_could_see() above is the whole
    # safety argument, and every one of its blind cases falls straight back
    # to the seismic decision rather than going quiet. What this does *not*
    # do is suppress anything else: the trigger is still recorded, the
    # bandit still settles, the event is still logged, and any uplink this
    # path grows should sit on the seismic decision, not behind this gate.
    # See docs/KNOWN_GAPS.md - there is no working footfall uplink today, so
    # "seismic warns" is a half this code cannot yet deliver.
    suppressed_by_vision = (
        require_vision_confirmation
        and decision.alert
        and not vision_check.confirmed
        and _vision_could_see(watch, _night_of_event)
    )
    if suppressed_by_vision:
        logger.info(
            "deterrent held: fused_P=%.3f cleared the threshold but %d vision "
            "poll(s) over %.1fs found no %s (saw %s) (ADR 0022 Decision B)",
            fusion_result.probability,
            watch.polls,
            watch.elapsed_s,
            "/".join(VISION_TARGET_LABELS),
            ", ".join(watch.species) or "nothing",
        )

    if not decision.alert or suppressed_by_vision:
        # No alert on this evidence: the vision-check burst (if any) is
        # never saved (storage discipline stays "only on alert" - module
        # docstring), but it did happen and did feed fusion, so it is
        # reported through capture_frame_count/trigger_to_first_frame_s the
        # same as an alert event's frames would be.
        # Closed first, deliberately: the recorder only has a finished,
        # muxed file to commit once close() has run the pipeline's EOS.
        if camera_opened:
            _close_camera(camera)
        # ADR 0020's keep-gate, on the branch where only half of it can be
        # true. No alert fired here by definition, so the recording
        # survives exactly when the camera actually confirmed an elephant -
        # a sub-threshold sighting is the footage that explains why fusion
        # did not clear the bar, which is worth more than the disk it costs.
        video_path = _finish_event_video(
            event_video,
            # Confirmed OR merely worth filming. The second half is what
            # makes "record boar, deter elephants" a config change rather
            # than a code change: a boar-only event takes exactly this
            # exit - it never confirmed, so it never alerted - and without
            # _worth_filming() its recording would be discarded here, which
            # is the one place the footage still exists.
            keep=vision_check.confirmed or _worth_filming(watch),
            tag=CaptureEventTag(
                event_timestamp_s=event_wall_s,
                sta_lta_ratio=sta_lta_ratio,
                fused_probability=fusion_result.probability,
                alert=decision.alert,
            ),
        )
        return _no_actuation_outcome(frames=tuple(vision_frames), video_path=video_path)

    context = habituation_context(repeat_count, cognition_config.HABITUATION_BUCKET_COUNT)
    floor = escalation_floor(context, bandit_params)
    tier, exploring = select_tier(
        context, experience.action_values(), bandit_params, rng, floor
    )
    action = cognition_config.resolve_tier_action(tier, rng, household_proximity)
    logger.info(
        "deterrence tier %d selected: context=%d floor=%d exploring=%s "
        "gain_pct=%.1f horn_track_id=%d fire_ir=%s",
        int(tier),
        context,
        int(floor),
        exploring,
        action.horn_gain_pct,
        action.horn_track_id,
        action.fire_ir,
    )

    if safe_mode:
        logger.info(
            "[SAFE_MODE] would open camera, call drive_horn(schema_version=%d, "
            "gain_pct=%.1f, duration_ms=%d, track_id=%d), drive_led(channel=%d, "
            "pattern_id=%d, gain_pct=%.1f, duration_ms=%d)%s - not calling (dry "
            "run), and recording no attempt",
            schema_version,
            action.horn_gain_pct,
            action.horn_duration_ms,
            action.horn_track_id,
            action.led_channel_id,
            action.led_pattern_id,
            action.led_gain_pct,
            action.led_duration_ms,
            f", pulse_ir(duration_ms={action.ir_duration_ms}) [only if the "
            f"vision-check burst reads as night]" if action.fire_ir else "",
        )
        # camera_opened/vision_frames are guaranteed empty here - the
        # pre-decision block above only runs when not safe_mode.
        return _no_actuation_outcome(context=context, action=action, exploring=exploring)

    trigger_wall_s = event_wall_s
    # camera_opened already reflects the pre-decision open attempt above -
    # not reopened here, the same camera session spans the vision check and
    # this evidence burst.

    # Tier 1 skips pulse_ir entirely rather than requesting a zero duration:
    # a zero-length request would still consume the IR MOSFET's
    # IR_MIN_INTERVAL_MS duty budget MCU-side, which is one of the two
    # reasons the low tier leaves IR alone (cognition/config.py).
    #
    # Started on its own thread here, immediately after camera.open(), and
    # joined below before drive_horn() - never called synchronously after
    # capture_burst() the way the other actuators fire. pulse_ir() blocks
    # MCU-side for the full duration (module docstring), so a synchronous
    # call after the capture would always return with the illuminator
    # already dark; this is what actually lands the exposure window inside
    # the pulse.
    #
    # Second gate, on top of the tier's fire_ir flag: the illuminator only
    # helps once the camera's IR-cut filter is out (night). is_night() reads
    # that off the vision-check burst already captured above - a mono /
    # IR-lit frame's colour saturation has collapsed, a daylight frame's has
    # not (perception/night.py). In daylight (False) or when not one frame
    # could be measured (None - and then the evidence burst has nothing to
    # illuminate either) the pulse is skipped for this event; the tier is
    # otherwise unchanged. An unexpected error inside is_night() itself must
    # not suppress deterrence - it is logged and the pulse fires, matching
    # the module's "a perception failure never blocks an actuator" rule.
    fire_ir_now = action.fire_ir
    if fire_ir_now:
        try:
            night = _night_of_event()
        except Exception:  # noqa: BLE001 - perception must never block actuation
            logger.exception("is_night() raised - firing pulse_ir anyway")
            night = True
        if night is True:
            pass
        elif night is False:
            logger.info(
                "pulse_ir suppressed: vision-check frames read as daylight "
                "(IR-cut filter engaged, illuminator would not reach the sensor) "
                "- tier %d otherwise unchanged",
                int(tier),
            )
            fire_ir_now = False
        else:  # None
            logger.info(
                "pulse_ir suppressed: day/night undetermined - no vision-check "
                "frame could be measured, so the evidence burst has nothing to "
                "illuminate either - tier %d otherwise unchanged",
                int(tier),
            )
            fire_ir_now = False

    ir_thread: threading.Thread | None = None
    ir_result: dict[str, bool] = {}
    if fire_ir_now:

        def _fire_ir() -> None:
            ir_result["ack"] = pulse_ir(schema_version, action.ir_duration_ms)

        ir_thread = threading.Thread(target=_fire_ir, daemon=True)
        ir_thread.start()

    evidence_frames = _capture_burst(camera, trigger_monotonic) if camera_opened else []
    frames = vision_frames + evidence_frames

    ir_ack: bool | None = None
    if ir_thread is not None:
        ir_thread.join()
        ir_ack = ir_result.get("ack")
        logger.info("pulse_ir ack=%s", ir_ack)

    horn_ack = drive_horn(
        schema_version,
        action.horn_gain_pct,
        action.horn_duration_ms,
        action.horn_track_id,
    )
    logger.info("drive_horn ack=%s", horn_ack)

    led_ack = drive_led(
        schema_version,
        action.led_channel_id,
        action.led_pattern_id,
        action.led_gain_pct,
        action.led_duration_ms,
    )
    logger.info("drive_led ack=%s", led_ack)

    # The bandit learns only from deterrence that actually happened. A false
    # ack means rule_gate_apply() refused the request inside HORN_COOLDOWN_MS
    # - nothing fired, so crediting this tier for whatever quiet follows
    # would attribute the animal's behaviour to a burst that never occurred.
    if horn_ack:
        experience.record_attempt(trigger_wall_s, context, tier)
    else:
        logger.info(
            "drive_horn refused (MCU cooldown) - recording no attempt, tier %d "
            "is not credited for this event",
            int(tier),
        )

    tag = CaptureEventTag(
        event_timestamp_s=trigger_wall_s,
        sta_lta_ratio=sta_lta_ratio,
        fused_probability=fusion_result.probability,
        alert=decision.alert,
    )

    if camera_opened:
        # The tail runs *after* every actuator call above has returned, so
        # nothing about event video - not the recording, not the longer
        # retreat tail - can delay the horn. That ordering is the whole
        # reason ADR 0020 records rather than pre-buffers.
        time.sleep(video_retreat_tail_s if event_video is not None else capture_post_fire_tail_s)
        _close_camera(camera)
        if frames:
            _save_captured_frames(save_frames, frames, tag)

    # Unconditional keep: reaching here means decision.alert is true, which
    # satisfies the keep-gate on its own whatever the vision check said.
    # Called even when the camera never opened, where it is a no-op - a
    # recorder that failed to open has already discarded its own scratch
    # file (perception/video.py), and commit() on nothing returns None.
    video_path = _finish_event_video(event_video, keep=True, tag=tag)

    trigger_to_first_frame_s = (
        frames[0].timestamp_s - trigger_monotonic if frames else None
    )

    return FootfallOutcome(
        fusion=fusion_result,
        decision=decision,
        repeat_count=repeat_count,
        context=context,
        action=action,
        exploring=exploring,
        settled=settled,
        horn_ack=horn_ack,
        led_ack=led_ack,
        ir_ack=ir_ack,
        capture_frame_count=len(frames),
        trigger_to_first_frame_s=trigger_to_first_frame_s,
        vision_confirmed=vision_check.confirmed,
        video_path=video_path,
        vision_polls=watch.polls,
        vision_watch_s=watch_s,
    )


# Which AcousticClass values are evidence toward "is an elephant present".
# ADR 0007 5 names exactly these three and treats them as one modality rather
# than three: they all feed the same WEIGHT_ACOUSTIC/BASELINE_ACOUSTIC pair in
# cognition/config.py. The other two classes are each excluded for their own
# distinct reason - see handle_acoustic_event().
_FUSING_ACOUSTIC_CLASSES = frozenset(
    {
        AcousticClass.CHAINSAW,
        AcousticClass.VEHICLE,
        AcousticClass.ANIMAL_CALL,
    }
)


def handle_acoustic_event(
    schema_version: int,
    class_label: AcousticClass,
    confidence: float,
    capture_ref: int,
    *,
    send_lora_alert: SendLoraAlertFn,
    safe_mode: bool = SAFE_MODE,
) -> AcousticOutcome:
    """Route one report_acoustic_event notify per ADR 0007 5's fusion/alert split.

    Which of three branches an event takes is the whole point of this
    function:

    - **gunshot** never reaches fuse(). ADR 0007 5 is explicit that a
      gunshot is not evidence toward "is an elephant present" - it is a
      categorically different alert (anti-poaching, human safety), and
      folding it into the elephant-presence score would be a modeling
      error, not just an oversimplification. It takes its own direct alert
      path to forest officers, independent of fusion and of the deterrence
      decision entirely: you do not deter a gunshot with a horn and LEDs.
    - **chainsaw/vehicle/animal_call** convert to log-odds via
      _confidence_log_odds() and fuse as the single ACOUSTIC modality. One
      modality for all three, per ADR 0007 - they share cognition/config.py's
      WEIGHT_ACOUSTIC and BASELINE_ACOUSTIC, whose magnitudes are themselves
      still invented (docs/KNOWN_GAPS.md).
    - **ambient** fuses as unavailable. INVENTED mapping: ADR 0007 names only
      four classes and never assigns ambient a route at all, but ADR 0001's
      addendum settles the shape - a modality with nothing to say is excluded
      from the sum, never scored as negative evidence. It still goes through
      fuse(), so the result honestly records "acoustic was present and had
      nothing to say" rather than "acoustic never reported".

    Two things this deliberately does not do:

    - **It never calls decide() and never actuates.** fuse() is stateless
      per event, so an acoustic classification arrives with no concurrent
      seismic or vision reading to corroborate. With both unavailable, a
      chainsaw at confidence 0.9 fuses on its own past
      ALERT_PROBABILITY_THRESHOLD - which would make acoustic a standalone
      elephant detector, exactly what ADR 0007/0009 scope it out of being.
      The missing piece is cross-modality temporal state, tracked as its own
      entry in docs/KNOWN_GAPS.md rather than papered over here with a
      threshold tweak.
    - **The gunshot alert it does send is not a real uplink.** send_lora_alert
      is a scaffolded Bridge.call stub (bridge/rpc.py) with no MCU-side
      transport behind it yet - comms/ is empty and the LoRa module is not
      answering AT probes (docs/KNOWN_GAPS.md, 18 Aug). Outside safe_mode
      this branch calls it for real and logs whatever ack comes back, same
      [SAFE_MODE]-adjacent discipline handle_footfall_event() uses above for
      actuators; under safe_mode it logs a dry-run line instead and never
      calls send_lora_alert at all.

    Precondition: none - schema_version mismatches are logged, not raised,
    same reasoning as handle_footfall_event(). Never blocks: no Bridge call
    and no sleep on any branch.

    Args:
        schema_version: As received from the MCU; logged if it does not
            match services.config.SCHEMA_VERSION.
        class_label: One of bridge.rpc.AcousticClass's values.
        confidence: Classifier confidence, 0-1. Epsilon-clamped before
            logit() on the fusing branch; unused on the other two beyond
            being logged.
        capture_ref: Index into the MCU's raw-window ring buffer.
        send_lora_alert: Injected callable matching SendLoraAlertFn, bound in
            main.py to a real Bridge.call. Only ever invoked on the gunshot
            branch, and only when safe_mode is False.
        safe_mode: When True (the default), the gunshot branch logs a
            dry-run line and never calls send_lora_alert. When False, it
            calls send_lora_alert for real and logs whatever ack comes back.

    Returns:
        An AcousticOutcome carrying the class, the FusionResult (None on the
        gunshot branch), and whether this event took the direct-alert path.
    """
    if schema_version != services_config.SCHEMA_VERSION:
        logger.warning(
            "report_acoustic_event: schema_version mismatch (got %d, expected %d)",
            schema_version,
            services_config.SCHEMA_VERSION,
        )

    if class_label is AcousticClass.GUNSHOT:
        if safe_mode:
            logger.info(
                "[SAFE_MODE] would send direct gunshot alert: confidence=%.3f "
                "capture_ref=%d - not calling send_lora_alert (dry run). "
                "Never fused: a gunshot is not elephant-presence evidence "
                "(ADR 0007 5)",
                confidence,
                capture_ref,
            )
            return AcousticOutcome(
                class_label=class_label, fusion=None, direct_alert=True, lora_ack=None
            )
        ack = send_lora_alert(schema_version, confidence, capture_ref)
        logger.info(
            "send_lora_alert ack=%s: confidence=%.3f capture_ref=%d - ack "
            "reflects queued/logged on the MCU, not delivered - no real "
            "LoRa transport exists yet (module not joining, see "
            "docs/KNOWN_GAPS.md). Never fused: a gunshot is not "
            "elephant-presence evidence (ADR 0007 5)",
            ack,
            confidence,
            capture_ref,
        )
        return AcousticOutcome(
            class_label=class_label, fusion=None, direct_alert=True, lora_ack=ack
        )

    fuses = class_label in _FUSING_ACOUSTIC_CLASSES
    readings = [
        ModalityReading(
            Modality.ACOUSTIC,
            _confidence_log_odds(confidence) if fuses else 0.0,
            available=fuses,
        ),
        # Seismic/vision: no reading in hand on this path. An acoustic notify
        # carries neither, and nothing correlates a footfall event with this
        # one across time yet - see this function's docstring on why that is
        # also the reason decide() is not called here.
        ModalityReading(Modality.SEISMIC, 0.0, available=False),
        ModalityReading(Modality.VISION, 0.0, available=False),
    ]
    fusion_result = fuse(readings, cognition_config.DEFAULT_FUSION_PARAMS)

    logger.info(
        "acoustic event: class_label=%s confidence=%.3f capture_ref=%d "
        "fused_P=%.3f used=%s dropped=%s (fusion only - no decide() or "
        "actuation on this path, acoustic is corroboration per ADR 0007/0009)",
        class_label.value,
        confidence,
        capture_ref,
        fusion_result.probability,
        [m.value for m in fusion_result.used],
        [m.value for m in fusion_result.dropped],
    )
    return AcousticOutcome(
        class_label=class_label, fusion=fusion_result, direct_alert=False, lora_ack=None
    )
