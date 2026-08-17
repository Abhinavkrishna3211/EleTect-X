"""The real sense -> fuse -> decide -> actuate loop (CONTEXT.md 4).

This is the wiring, not a stub: cognition.fusion.fuse() and
cognition.decision.decide() are both real, tested pure functions, and this
module is the imperative shell around them (ENGINEERING_CONVENTIONS.md 2) -
it owns logging and the real side effects (drive_horn/drive_led/pulse_ir
Bridge.call()s, plus an injected camera opened for the duration of the
deterrent sequence and a frame-storage callable). Every one of those is
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
drive_led() -> pulse_ir() -> a short post-fire tail sleep ->
camera.close() -> save_frames(). The camera opens before any actuator call
(footage should start as close to trigger as possible) and only closes once
the full deterrent sequence plus the tail has elapsed. A camera or storage
failure is logged and never allowed to suppress or delay the actuator calls
- deterrence is the safety-critical function here, footage is
important but secondary. See docs/KNOWN_GAPS.md.

Two of the three fusion modalities are not wired in yet, by design, not
oversight:

- **Vision**: no detector exists (perception/camera.py is capture-only, no
  pixel -> log-odds model - cognition/fusion.py's own module docstring
  names this a future build call). Always passed to fuse() as unavailable.
- **Acoustic**: report_acoustic_event's classifier output (gunshot/
  chainsaw/vehicle/animal_call/ambient) has no defined mapping onto
  elephant-presence log-odds, and ADR 0007 5 routes gunshot to a direct
  LoRa alert that bypasses fusion entirely - a routing path this repo has
  not built yet (comms/ is empty). handle_acoustic_event() logs the event
  for visibility only; it never reaches fuse(). See docs/KNOWN_GAPS.md.

Only seismic is wired end-to-end: the MCU's own on-board footfall model
already reports a probability (schema.md's report_footfall_event), and
converting that into fusion's log-odds input via cognition.fusion.logit()
is a direct, non-invented transformation - not a new detector this module
had to build.

SAFE_MODE (default on) is the dry-run gate: when true, an alert decision is
logged but drive_horn is never called. Read once at import time from the
ELETECT_SAFE_MODE environment variable, so flipping it for a live session is
an explicit, visible operational step (`export ELETECT_SAFE_MODE=0`), never
a silent code default change - this mirrors device/mcu/src/config.h's own
"gated behind a flag, defaults to the safe state" discipline for the
fire-test harness and seismic debug-stream flags.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Protocol

from bridge.rpc import AcousticClass
from cognition import config as cognition_config
from cognition.decision import Decision, decide
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
# Placeholder deterrence request - INVENTED, see docs/KNOWN_GAPS.md
# ---------------------------------------------------------------------------

# Which actuator(s) to fire and at what gain/duration is the contextual
# bandit's job once it exists (cognition/fusion.py module docstring); until
# then this loop drives the horn only (the primary audible deterrent) and
# requests the wire protocol's own maximum - 100.0 pct (schema.md's
# documented 0-100 gain_pct range) and 65535 ms (duration_ms's uint16
# ceiling) - rather than inventing a specific mid-range gain/duration
# figure. device/mcu/src/rule_gate.cpp already clamps any out-of-bounds
# request down to the MCU's real, separately-configured caps
# (HORN_GAIN_MAX_PCT / HORN_BURST_MAX_MS, device/mcu/src/config.h)
# regardless of what is asked for, and services/config.py's own docstring
# is explicit that those real caps deliberately do not get duplicated on
# the MPU side - so "ask for the protocol max, let the MCU clamp it" avoids
# inventing a second, unreviewed limit rather than just moving the
# invention somewhere else.
ALERT_HORN_GAIN_PCT = 100.0
ALERT_HORN_DURATION_MS = 65535

# LED/IR follow the exact same "ask for the protocol max, let the MCU
# clamp" policy as the horn above - device/mcu/src/bridge_handlers.cpp
# already resolves gain_pct to LED_GAIN_MAX_PCT/IR_GAIN_MAX_PCT MCU-side
# (schema.md's drive_led/pulse_ir rows carry no gain_pct field at all), so
# there is nothing to request here beyond duration_ms. pattern_id 0 selects
# led_channel_for_pattern_id()'s default (white) channel -
# device/mcu/src/bridge_handlers.h documents that mapping itself as an
# INVENTED placeholder pending real pattern design; this loop firing
# pattern_id 0 on every alert is the same "least presumptuous placeholder"
# choice, not a resolved deterrence-pattern decision. See docs/KNOWN_GAPS.md.
ALERT_LED_PATTERN_ID = 0
ALERT_LED_DURATION_MS = 65535
ALERT_IR_DURATION_MS = 65535

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


@dataclass(frozen=True)
class FootfallOutcome:
    """What one handle_footfall_event() call decided and did.

    Returned (rather than left as a side effect only) so tests can assert on
    it directly, matching tests/test_fusion.py's pattern of asserting on a
    returned result rather than on log output.

    Attributes:
        fusion: The FusionResult fuse() produced for this event.
        decision: The Decision decide() produced for this event.
        horn_ack: drive_horn's returned ack, or None if it was never called
            (no alert, or SAFE_MODE suppressed the call).
        led_ack: drive_led's returned ack, or None under the same conditions
            as horn_ack.
        ir_ack: pulse_ir's returned ack, or None under the same conditions
            as horn_ack.
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
    horn_ack: bool | None
    led_ack: bool | None
    ir_ack: bool | None
    capture_frame_count: int
    trigger_to_first_frame_s: float | None


def _seismic_log_odds(probability: float) -> float:
    """Convert the MCU's on-board footfall probability into fusion's log-odds input.

    logit() rejects the closed interval's endpoints (0.0 and 1.0) - both are
    representable float values report_footfall_event's wire probability
    could in principle carry, even though the MCU's own model realistically
    saturates just short of them. Clamping into an epsilon-narrowed open
    interval before calling logit() is a numerical safety guard here (same
    category as fusion.sigmoid()'s own two-branch overflow handling), not a
    policy choice - it changes nothing for any probability logit() would
    already have accepted unclamped.

    Args:
        probability: report_footfall_event's `probability` field, expected
            in [0.0, 1.0].

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
    safe_mode: bool = SAFE_MODE,
    threshold: float = ALERT_PROBABILITY_THRESHOLD,
    capture_post_fire_tail_s: float = CAPTURE_POST_FIRE_TAIL_S,
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
    camera.capture_burst() -> drive_horn() -> drive_led() -> pulse_ir() ->
    sleep(CAPTURE_POST_FIRE_TAIL_S) -> camera.close() -> save_frames(). The
    camera opens before any actuator call and only closes once the full
    deterrent sequence plus the tail has elapsed (module docstring). A
    camera or storage failure at any point is logged and never allowed to
    suppress or delay the actuator calls that follow it.

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
            All five above are injected so this function needs no board or
            camera attached to test - device/mpu/main.py wires the real
            Bridge.calls, Camera, and save_burst in; tests pass recording
            fakes.
        safe_mode: When true (the default, SAFE_MODE), an alert decision is
            logged but none of drive_horn/drive_led/pulse_ir/camera/
            save_frames are ever called.
        threshold: Passed to cognition.decision.decide(). Defaults to
            ALERT_PROBABILITY_THRESHOLD (see that constant's own comment).
        capture_post_fire_tail_s: Seconds to wait after pulse_ir() before
            closing the camera. Defaults to CAPTURE_POST_FIRE_TAIL_S;
            overridable so tests don't have to sleep for real.

    Returns:
        A FootfallOutcome carrying the fusion result, the decision, the
        three actuator acks, and this event's capture outcome.
    """
    if schema_version != services_config.SCHEMA_VERSION:
        logger.warning(
            "report_footfall_event: schema_version mismatch (got %d, expected %d)",
            schema_version,
            services_config.SCHEMA_VERSION,
        )

    readings = [
        ModalityReading(Modality.SEISMIC, _seismic_log_odds(probability), available=True),
        # Acoustic/vision: no wired detector yet - see module docstring.
        ModalityReading(Modality.ACOUSTIC, 0.0, available=False),
        ModalityReading(Modality.VISION, 0.0, available=False),
    ]
    fusion_result = fuse(readings, cognition_config.DEFAULT_FUSION_PARAMS)
    decision = decide(fusion_result, threshold)

    logger.info(
        "footfall event: mcu_probability=%.3f sta_lta_ratio=%.3f fused_P=%.3f "
        "alert=%s used=%s dropped=%s feature_vector=%s",
        probability,
        sta_lta_ratio,
        fusion_result.probability,
        decision.alert,
        [m.value for m in fusion_result.used],
        [m.value for m in fusion_result.dropped],
        feature_vector,
    )

    def _no_actuation_outcome() -> FootfallOutcome:
        return FootfallOutcome(
            fusion=fusion_result,
            decision=decision,
            horn_ack=None,
            led_ack=None,
            ir_ack=None,
            capture_frame_count=0,
            trigger_to_first_frame_s=None,
        )

    if not decision.alert:
        return _no_actuation_outcome()

    if safe_mode:
        logger.info(
            "[SAFE_MODE] would open camera, call drive_horn(schema_version=%d, "
            "gain_pct=%.1f, duration_ms=%d), drive_led(pattern_id=%d, duration_ms=%d), "
            "pulse_ir(duration_ms=%d) - not calling (dry run)",
            schema_version,
            ALERT_HORN_GAIN_PCT,
            ALERT_HORN_DURATION_MS,
            ALERT_LED_PATTERN_ID,
            ALERT_LED_DURATION_MS,
            ALERT_IR_DURATION_MS,
        )
        return _no_actuation_outcome()

    trigger_monotonic = time.monotonic()
    trigger_wall_s = time.time()

    camera_opened = _open_camera(camera)
    frames = _capture_burst(camera, trigger_monotonic) if camera_opened else []

    horn_ack = drive_horn(schema_version, ALERT_HORN_GAIN_PCT, ALERT_HORN_DURATION_MS)
    logger.info("drive_horn ack=%s", horn_ack)

    led_ack = drive_led(schema_version, ALERT_LED_PATTERN_ID, ALERT_LED_DURATION_MS)
    logger.info("drive_led ack=%s", led_ack)

    ir_ack = pulse_ir(schema_version, ALERT_IR_DURATION_MS)
    logger.info("pulse_ir ack=%s", ir_ack)

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
        horn_ack=horn_ack,
        led_ack=led_ack,
        ir_ack=ir_ack,
        capture_frame_count=len(frames),
        trigger_to_first_frame_s=trigger_to_first_frame_s,
    )


def handle_acoustic_event(
    schema_version: int,
    class_label: AcousticClass,
    confidence: float,
    capture_ref: int,
) -> None:
    """Log one report_acoustic_event notify. Does not reach fuse() - see module docstring.

    Precondition: none - schema_version mismatches are logged, not raised,
    same reasoning as handle_footfall_event(). Never blocks: logging only,
    no Bridge call on this path.

    Args:
        schema_version: As received from the MCU; logged if it does not
            match services.config.SCHEMA_VERSION.
        class_label: One of bridge.rpc.AcousticClass's values.
        confidence: Classifier confidence, 0-1.
        capture_ref: Index into the MCU's raw-window ring buffer.

    Returns:
        None - matches report_acoustic_event's own notify contract.
    """
    if schema_version != services_config.SCHEMA_VERSION:
        logger.warning(
            "report_acoustic_event: schema_version mismatch (got %d, expected %d)",
            schema_version,
            services_config.SCHEMA_VERSION,
        )
    logger.info(
        "acoustic event: class_label=%s confidence=%.3f capture_ref=%d "
        "(not fused - no elephant-relevant mapping defined yet, see docs/KNOWN_GAPS.md)",
        class_label.value,
        confidence,
        capture_ref,
    )
