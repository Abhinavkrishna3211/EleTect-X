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

Alert-path event order (only when safe_mode is False and decide() returns
alert=True): camera.open() -> camera.capture_burst() -> drive_horn() ->
drive_led() -> pulse_ir() (tier 2 and 3 only) -> a short post-fire tail
sleep -> camera.close() -> save_frames(). The camera opens before any
actuator call (footage should start as close to trigger as possible) and
only closes once the full deterrent sequence plus the tail has elapsed. A
camera or storage failure is logged and never allowed to suppress or delay
the actuator calls - deterrence is the safety-critical function here,
footage is contest-critical but secondary. See docs/KNOWN_GAPS.md.

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

Two of the three fusion modalities are not wired in yet, by design, not
oversight:

- **Vision**: no detector exists (perception/camera.py is capture-only, no
  pixel -> log-odds model - cognition/fusion.py's own module docstring
  names this a future build call). Always passed to fuse() as unavailable.
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

Only seismic is wired end-to-end into the alert-and-actuate path: the MCU's
own on-board footfall model already reports a probability (schema.md's
report_footfall_event), and converting that into fusion's log-odds input via
cognition.fusion.logit() is a direct, non-invented transformation - not a new
detector this module had to build.

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
import time
from dataclasses import dataclass
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

    def __call__(self, schema_version: int, gain_pct: float, duration_ms: int) -> bool:
        """Request a horn burst; returns the ack drive_horn's own contract defines."""
        ...


class DriveLedFn(Protocol):
    """Callable shape matching bridge.rpc.drive_led's real signature."""

    def __call__(self, schema_version: int, pattern_id: int, duration_ms: int) -> bool:
        """Request an LED burst; returns the ack drive_led's own contract defines."""
        ...


class PulseIrFn(Protocol):
    """Callable shape matching bridge.rpc.pulse_ir's real signature."""

    def __call__(self, schema_version: int, duration_ms: int) -> bool:
        """Request an IR pulse; returns the ack pulse_ir's own contract defines."""
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
            event (0 if no alert, SAFE_MODE suppressed it, or the camera
            failed - see module docstring on camera failures never blocking
            actuation).
        trigger_to_first_frame_s: Seconds between entering the alert-actuate
            path and the first captured frame's own timestamp, or None if
            no frame was captured. Instrumentation only - see
            docs/KNOWN_GAPS.md on why this loop measures this instead of
            running a continuous rolling pre-event buffer.
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


def _capture_burst(camera: CameraProtocol, trigger_monotonic: float) -> list[Frame]:
    """Grab the pre-fire burst from an already-opened camera; never raises.

    Only called once _open_camera() has already succeeded - a
    capture_burst() failure here is logged the same way an open() failure
    is, and still leaves the caller responsible for closing the camera.

    Returns:
        The captured frames, or [] if capture_burst() failed.
    """
    try:
        frames = camera.capture_burst(
            services_config.CAMERA_BURST_FRAMES, services_config.CAMERA_BURST_INTERVAL_S
        )
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


def handle_footfall_event(
    schema_version: int,
    probability: float,
    sta_lta_ratio: float,
    feature_vector: list[float],
    *,
    drive_horn: DriveHornFn,
    drive_led: DriveLedFn,
    pulse_ir: PulseIrFn,
    camera: CameraProtocol,
    save_frames: SaveFramesFn,
    experience: ExperienceStoreProtocol,
    safe_mode: bool = SAFE_MODE,
    threshold: float = ALERT_PROBABILITY_THRESHOLD,
    capture_post_fire_tail_s: float = CAPTURE_POST_FIRE_TAIL_S,
    bandit_params: BanditParams = cognition_config.DEFAULT_BANDIT_PARAMS,
    rng: random.Random = _DEFAULT_RNG,
) -> FootfallOutcome:
    """Sense -> fuse -> decide -> actuate for one report_footfall_event notify.

    Precondition: none - schema_version mismatches are logged, not raised,
    matching report_footfall_event's own notify contract (bridge/rpc.py):
    the MCU never reads a return value from this path, so raising here would
    only crash the MPU's own event loop over a field it cannot act on
    anyway. Never blocks past the drive_horn/drive_led/pulse_ir
    Bridge.call()s (services.config.BRIDGE_CALL_TIMEOUT_S each, enforced
    inside the injected callables, not here) plus one capture burst and a
    fixed CAPTURE_POST_FIRE_TAIL_S tail, or not at all when safe_mode is
    true or no alert fires.

    On a real alert (safe_mode False), the event order is: camera.open() ->
    camera.capture_burst() -> drive_horn() -> drive_led() -> pulse_ir()
    (skipped entirely on tier 1) -> sleep(CAPTURE_POST_FIRE_TAIL_S) ->
    camera.close() -> save_frames(). The camera opens before any actuator
    call and only closes once the full deterrent sequence plus the tail has
    elapsed (module docstring). A camera or storage failure at any point is
    logged and never allowed to suppress or delay the actuator calls that
    follow it.

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
        camera: Object matching CameraProtocol (open/capture_burst/close).
            Opened and closed once per alert event, never across events.
        save_frames: Callable matching perception.storage.save_burst's
            signature. Called once per alert event with whatever frames
            were captured (skipped entirely if none were).
        experience: Object matching ExperienceStoreProtocol. Carries the
            bandit's learned values and trigger history across events and
            across restarts; the only cross-event state this loop has.
            All six above are injected so this function needs no board,
            camera or database attached to test - device/mpu/main.py wires
            the real Bridge.calls, Camera, save_burst and ExperienceStore
            in; tests pass recording fakes.
        safe_mode: When true (the default, SAFE_MODE), the decision and the
            selected tier are logged but none of drive_horn/drive_led/
            pulse_ir/camera/save_frames are ever called, and no attempt is
            recorded. The trigger itself is still recorded - a dry run
            observes real events, it just does not respond to them.
        threshold: Passed to cognition.decision.decide(). Defaults to
            ALERT_PROBABILITY_THRESHOLD (see that constant's own comment).
        capture_post_fire_tail_s: Seconds to wait after the actuator
            sequence before closing the camera. Defaults to
            CAPTURE_POST_FIRE_TAIL_S; overridable so tests don't have to
            sleep for real.
        bandit_params: Hyperparameters for selection and reward. Defaults to
            cognition.config.DEFAULT_BANDIT_PARAMS.
        rng: Source of the epsilon-greedy exploration draw. Defaults to a
            module-level random.Random; seed one and pass it for an exact,
            reproducible selection under test.

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

    readings = [
        ModalityReading(Modality.SEISMIC, _confidence_log_odds(probability), available=True),
        # Acoustic/vision: no reading in hand on this path. A footfall notify
        # carries neither, and nothing correlates an acoustic event with this
        # one across time yet - acoustic fuses only on its own event, in
        # handle_acoustic_event(). Vision has no detector at all. See module
        # docstring.
        ModalityReading(Modality.ACOUSTIC, 0.0, available=False),
        ModalityReading(Modality.VISION, 0.0, available=False),
    ]
    fusion_result = fuse(readings, cognition_config.DEFAULT_FUSION_PARAMS)
    decision = decide(fusion_result, threshold)

    # One wall-clock reading for the whole event, taken before any of the
    # store calls below. Wall clock rather than monotonic because it has to
    # stay comparable across the MPU suspend/resume cycles ADR 0008
    # describes, and a single reading rather than several so the trigger,
    # the settlement and any recorded attempt all agree on when this event
    # happened - the reward is a difference between two of these timestamps,
    # so drift between them would be drift in the reward itself.
    event_wall_s = time.time()
    repeat_count = experience.record_trigger(event_wall_s, bandit_params.habituation_window_s)
    settled = experience.settle_pending(event_wall_s, bandit_params)

    logger.info(
        "footfall event: mcu_probability=%.3f sta_lta_ratio=%.3f fused_P=%.3f "
        "alert=%s used=%s dropped=%s repeats_in_window=%d feature_vector=%s",
        probability,
        sta_lta_ratio,
        fusion_result.probability,
        decision.alert,
        [m.value for m in fusion_result.used],
        [m.value for m in fusion_result.dropped],
        repeat_count,
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
    ) -> FootfallOutcome:
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
            capture_frame_count=0,
            trigger_to_first_frame_s=None,
        )

    if not decision.alert:
        return _no_actuation_outcome()

    context = habituation_context(repeat_count, cognition_config.HABITUATION_BUCKET_COUNT)
    floor = escalation_floor(context, bandit_params)
    tier, exploring = select_tier(
        context, experience.action_values(), bandit_params, rng, floor
    )
    action = cognition_config.DETERRENCE_TIERS[tier]
    logger.info(
        "deterrence tier %d selected: context=%d floor=%d exploring=%s "
        "gain_pct=%.1f fire_ir=%s",
        int(tier),
        context,
        int(floor),
        exploring,
        action.horn_gain_pct,
        action.fire_ir,
    )

    if safe_mode:
        logger.info(
            "[SAFE_MODE] would open camera, call drive_horn(schema_version=%d, "
            "gain_pct=%.1f, duration_ms=%d), drive_led(pattern_id=%d, duration_ms=%d)"
            "%s - not calling (dry run), and recording no attempt",
            schema_version,
            action.horn_gain_pct,
            action.horn_duration_ms,
            action.led_pattern_id,
            action.led_duration_ms,
            f", pulse_ir(duration_ms={action.ir_duration_ms})" if action.fire_ir else "",
        )
        return _no_actuation_outcome(context=context, action=action, exploring=exploring)

    trigger_monotonic = time.monotonic()
    trigger_wall_s = event_wall_s

    camera_opened = _open_camera(camera)
    frames = _capture_burst(camera, trigger_monotonic) if camera_opened else []

    horn_ack = drive_horn(schema_version, action.horn_gain_pct, action.horn_duration_ms)
    logger.info("drive_horn ack=%s", horn_ack)

    led_ack = drive_led(schema_version, action.led_pattern_id, action.led_duration_ms)
    logger.info("drive_led ack=%s", led_ack)

    # Tier 1 skips pulse_ir entirely rather than requesting a zero duration:
    # a zero-length request would still consume the IR MOSFET's
    # IR_MIN_INTERVAL_MS duty budget MCU-side, which is one of the two
    # reasons the low tier leaves IR alone (cognition/config.py).
    ir_ack: bool | None = None
    if action.fire_ir:
        ir_ack = pulse_ir(schema_version, action.ir_duration_ms)
        logger.info("pulse_ir ack=%s", ir_ack)

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

    if camera_opened:
        time.sleep(capture_post_fire_tail_s)
        _close_camera(camera)
        if frames:
            tag = CaptureEventTag(
                event_timestamp_s=trigger_wall_s,
                sta_lta_ratio=sta_lta_ratio,
                fused_probability=fusion_result.probability,
                alert=decision.alert,
            )
            _save_captured_frames(save_frames, frames, tag)

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
