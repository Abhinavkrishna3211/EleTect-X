"""Behavioral tests for services/reflex_loop.py.

Exercises the real sense -> fuse -> decide -> select -> actuate wiring with
mocked sensor inputs and recording fakes in place of the real
Bridge.call-backed drive_horn/drive_led/pulse_ir, the real
perception.camera.Camera, and the real perception.storage.save_burst. The
experience store is real cognition.experience.ExperienceStore, backed by
SQLite's in-memory database - a recording fake there would let a broken
store satisfy every assertion below.

Every expected fused log-odds/probability below is hand-computed against the
real cognition.config.DEFAULT_FUSION_PARAMS values (not a test-local
fixture, unlike test_fusion.py) via cognition.fusion.logit/sigmoid directly
- never by calling fuse() or reflex_loop's own logic a second time - so
these tests cannot pass by tautology (ENGINEERING_CONVENTIONS.md 4).

capture_post_fire_tail_s is always overridden to 0.0 below so these tests
don't actually sleep for CAPTURE_POST_FIRE_TAIL_S real seconds each, and
video_retreat_tail_s likewise - it defaults to 45s, so a video test that
forgot to override it would stall the whole suite rather than fail.

Exploration is disabled (epsilon 0.0) in _fire()'s default params. The real
DEFAULT_BANDIT_PARAMS explores on roughly one event in seven, which would
make every actuator-argument assertion here fail intermittently for a reason
that has nothing to do with what it is testing. Exploration itself is
covered directly in tests/test_bandit.py and by the one test below that
turns it back on deliberately.
"""

import dataclasses
import math
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from bridge.rpc import AcousticClass
from cognition import config as cognition_config
from cognition.bandit import Tier
from cognition.experience import IN_MEMORY_PATH, ExperienceStore
from cognition.fusion import Modality, sigmoid
from perception.camera import CameraError, Frame
from perception.detector import Detection, DetectionError
from perception.storage import CaptureEventTag
from services import config as services_config
from services import reflex_loop

# Deployment overrides live in cognition/config.py and services/config.py,
# and the tests below assert the design each one suspends. Each override
# gets its own marker rather than sharing one: they are lifted
# independently, and a single combined condition keeps the mark applied
# after one is reverted, reporting the other's tests as failures.
# strict=True turns a suspended test back into a hard failure the moment
# its override is lifted and it starts passing again, so an override can
# never be left silently in place.
#
# The escalation ladder. Committed code carries (TIER_1, TIER_2, TIER_3);
# a node that needs a flat floor sets ELETECT_TIER_FLOOR instead. The
# marker is what lets that node still report honestly rather than failing
# a suite that is testing the shipped default.
_TIER_FLOOR_OVERRIDDEN = cognition_config.TIER_FLOOR_BY_CONTEXT != (
    Tier.TIER_1,
    Tier.TIER_2,
    Tier.TIER_3,
)
TIER_FLOOR_OVERRIDE = pytest.mark.xfail(
    _TIER_FLOOR_OVERRIDDEN,
    reason="suspended by an ELETECT_TIER_FLOOR override of the escalation ladder",
    strict=True,
)

# Horn and LED gain. Committed code fires every tier at full gain. A rig on
# a soft supply may pin the columns lower to buy sag headroom - the 10 Sept
# run #1 mitigation did, at horn 0.20/0.28/0.35 and LED 0.85. That is a
# power decision, separate from the ladder, so it gets its own marker.
_GAIN_OVERRIDDEN = (
    cognition_config.TIER_3_GAIN_FRACTION != 1.0 or cognition_config.LED_TIER_1_GAIN_FRACTION != 1.0
)
GAIN_OVERRIDE = pytest.mark.xfail(
    _GAIN_OVERRIDDEN,
    reason="suspended by the 10 Sept horn/LED gain reductions in cognition/config.py",
    strict=True,
)

# The two Boar vision gates: the consecutive-poll streak and the
# burst-majority requirement. Emptying either lets a fox - which this
# 2-class model labels "Boar" - admit and confirm on a single poll, which
# is what the open-ended 13 Sept relaxation does. The tests that assert the
# two-poll/majority design below are suspended rather than deleted, because
# that design is still the one to return to.
_FOX_GATE_RELAXED = (
    services_config.VISION_SPECIES_CONSECUTIVE_POLLS.get("Boar", 1) < 2
    or "Boar" not in services_config.VISION_SPECIES_BURST_MAJORITY_LABELS
)
FOX_GATE_RELAXATION = pytest.mark.xfail(
    _FOX_GATE_RELAXED,
    reason=(
        "suspended by the open-ended 13 Sept fox-gate relaxation "
        "(VISION_SPECIES_CONSECUTIVE_POLLS / "
        "VISION_SPECIES_BURST_MAJORITY_LABELS in services/config.py)"
    ),
    strict=True,
)

# The real tuning, minus the randomness - see the module docstring.
DETERMINISTIC_PARAMS = dataclasses.replace(cognition_config.DEFAULT_BANDIT_PARAMS, epsilon=0.0)

TIER_1 = cognition_config.DETERRENCE_TIERS[Tier.TIER_1]
TIER_2 = cognition_config.DETERRENCE_TIERS[Tier.TIER_2]
TIER_3 = cognition_config.DETERRENCE_TIERS[Tier.TIER_3]


class _FakeDriveHorn:
    """Recording stand-in for bridge.rpc.drive_horn, injected per call.

    Args:
        ack: What each call should return.
        call_log: Shared list this and other fakes append a tagged entry to
            - lets a test assert cross-fake call ORDER, not just each
            fake's own call count.
    """

    def __init__(self, ack: bool = True, call_log: list | None = None):
        self.ack = ack
        self.calls = []
        self.call_log = call_log if call_log is not None else []

    def __call__(self, schema_version, gain_pct, duration_ms, track_id):
        self.calls.append((schema_version, gain_pct, duration_ms, track_id))
        self.call_log.append("drive_horn")
        return self.ack


class _FakeDriveLed:
    """Recording stand-in for bridge.rpc.drive_led, injected per call."""

    def __init__(self, ack: bool = True, call_log: list | None = None):
        self.ack = ack
        self.calls = []
        self.call_log = call_log if call_log is not None else []

    def __call__(self, schema_version, channel, pattern_id, gain_pct, duration_ms):
        self.calls.append((schema_version, channel, pattern_id, gain_pct, duration_ms))
        self.call_log.append("drive_led")
        return self.ack


class _FakePulseIr:
    """Recording stand-in for bridge.rpc.pulse_ir, injected per call.

    Args:
        ack: What each call should return.
        hold_s: Simulates the MCU's blocking analogWrite/delay/analogWrite
            (device/mcu/src/ir.cpp) by sleeping this long before returning -
            0.0 unless a test needs to prove a concurrent capture actually
            overlaps the pulse.
        call_log: Shared cross-fake call-order log, see _FakeDriveHorn.
    """

    def __init__(self, ack: bool = True, hold_s: float = 0.0, call_log: list | None = None):
        self.ack = ack
        self.hold_s = hold_s
        self.calls = []
        self.call_log = call_log if call_log is not None else []
        self.on_at: float | None = None
        self.off_at: float | None = None

    def __call__(self, schema_version, duration_ms):
        self.on_at = time.monotonic()
        self.calls.append((schema_version, duration_ms))
        self.call_log.append("pulse_ir")
        if self.hold_s:
            time.sleep(self.hold_s)
        self.off_at = time.monotonic()
        return self.ack


class _FakeSendLoraAlert:
    """Recording stand-in for bridge.rpc.send_lora_alert, injected per call."""

    def __init__(self, ack: bool = False, call_log: list | None = None):
        self.ack = ack
        self.calls = []
        self.call_log = call_log if call_log is not None else []

    def __call__(self, schema_version, acoustic_class, confidence, capture_ref):
        self.calls.append((schema_version, acoustic_class, confidence, capture_ref))
        self.call_log.append("send_lora_alert")
        return self.ack


# A finished event, as handle_acoustic_event() sees one coming back out of
# the injected start_vision_event. Only the three fields the handler logs
# are present: a real FootfallOutcome here would say nothing extra and
# would have to be rebuilt every time the dataclass gains a field.
_FAKE_FOOTFALL = SimpleNamespace(vision_confirmed=True, species="Elephant", alerted=True)


class _FakeStartVisionEvent:
    """Recording stand-in for main.py's _start_vision_event binding.

    Returns None by default, which is what the real binding returns when
    another event already owned the camera and this one was dropped. Tests
    that care about what came back pass an outcome in.
    """

    def __init__(self, outcome=None):
        self.outcome = outcome
        self.calls: list[float] = []

    def __call__(self, confidence):
        self.calls.append(confidence)
        return self.outcome


class _FakeCamera:
    """Recording stand-in for perception.camera.Camera, injected per event.

    Builds real Frame objects with real time.monotonic() timestamps on
    capture_burst(), same as the real Camera, so trigger-to-first-frame
    latency assertions stay meaningful.

    Args:
        frame_count: How many frames capture_burst() should synthesize.
        fail_open: If True, open() raises CameraError instead of succeeding
            - exercises "a camera failure must never block actuator firing".
        fail_capture: Same, for capture_burst().
        call_log: Shared cross-fake call-order log, see _FakeDriveHorn.
        lock_exposure_result: What lock_night_exposure() returns. Not
            logged to the shared call_log - unlike open/capture_burst/
            close, its position relative to pulse_ir/drive_horn/drive_led
            is not part of any existing ordering assertion, and adding it
            there would shift every log[n] index those tests already
            check. Recorded on lock_night_exposure_calls instead, the same
            private-counter convention _FakeVisionDetect.calls uses for
            bookkeeping that doesn't need cross-fake interleaving proof.
    """

    def __init__(
        self,
        frame_count: int = 3,
        fail_open: bool = False,
        fail_capture: bool = False,
        call_log: list | None = None,
        lock_exposure_result: bool = True,
    ):
        self._frame_count = frame_count
        self._fail_open = fail_open
        self._fail_capture = fail_capture
        self.call_log = call_log if call_log is not None else []
        self.opened = False
        self.captured_frames: list[Frame] = []
        self._lock_exposure_result = lock_exposure_result
        self.lock_night_exposure_calls = 0

    def open(self):
        self.call_log.append("camera.open")
        if self._fail_open:
            raise CameraError("fake camera: open() failed")
        self.opened = True

    def capture_burst(self, count, interval_s):
        self.call_log.append("camera.capture_burst")
        if self._fail_capture:
            raise CameraError("fake camera: capture_burst() failed")
        self.captured_frames = [
            Frame(image=None, index=i, timestamp_s=time.monotonic())
            for i in range(self._frame_count)
        ]
        return self.captured_frames

    def lock_night_exposure(self):
        self.lock_night_exposure_calls += 1
        return self._lock_exposure_result

    def close(self):
        self.call_log.append("camera.close")
        self.opened = False


class _FakeVisionDetect:
    """Recording stand-in for perception.detector.VisionDetectFn, injected per event.

    Defaults to "camera saw frames, model found nothing" - the most common
    real case and the one that keeps every pre-existing fusion assertion
    numerically valid (an empty-detection reading still contributes exactly
    zero net evidence, cognition/config.py's BASELINE_VISION - see
    reflex_loop._vision_check()'s own docstring). Only affects the
    used/dropped/contributions bookkeeping, not any fused log-odds value.

    Args:
        detections: What every frame in every call should return - the same
            flat list broadcast to each image passed in, since no test here
            needs per-image differentiation. Implements VisionDetectFn's
            list[list[Detection]] shape by repeating this list once per
            image (list[Detection] appears on every frame -> qualifies
            under both the default one-frame-is-enough gate and any
            per-label majority gate alike, so this fake needs no change
            for either).
        raises: If set, __call__ raises this instead of returning.
    """

    def __init__(
        self,
        detections: list[Detection] | None = None,
        raises: Exception | None = None,
    ):
        self._detections = detections if detections is not None else []
        self._raises = raises
        self.calls: list[list] = []

    def __call__(self, images):
        self.calls.append(list(images))
        if self._raises is not None:
            raise self._raises
        return [list(self._detections) for _ in images]


class _FakeSaveFrames:
    """Recording stand-in for perception.storage.save_burst, injected per event."""

    def __init__(self, raises: Exception | None = None, call_log: list | None = None):
        self._raises = raises
        self.calls = []
        self.call_log = call_log if call_log is not None else []

    def __call__(self, frames, tag):
        self.call_log.append("save_frames")
        self.calls.append((frames, tag))
        if self._raises is not None:
            raise self._raises
        return []


def _expected_seismic_fusion(probability: float):
    """Hand-computed (L, P) for a footfall event with acoustic/vision unavailable.

    L = L_PRIOR + WEIGHT_SEISMIC * (logit(probability) - BASELINE_SEISMIC);
    acoustic/vision contribute nothing (dropped, not scored as 0).
    """
    log_odds_seismic = math.log(probability / (1.0 - probability))
    contribution = cognition_config.WEIGHT_SEISMIC * (
        log_odds_seismic - cognition_config.BASELINE_SEISMIC
    )
    fused_log_odds = cognition_config.L_PRIOR + contribution
    return fused_log_odds, sigmoid(fused_log_odds)


def _expected_acoustic_fusion(confidence: float):
    """Hand-computed (L, P) for an acoustic event with seismic/vision unavailable.

    L = L_PRIOR + WEIGHT_ACOUSTIC * (logit(confidence) - BASELINE_ACOUSTIC);
    seismic/vision contribute nothing (dropped, not scored as 0). Same
    anti-tautology discipline as _expected_seismic_fusion above - math.log
    directly, never logit() or fuse().
    """
    log_odds_acoustic = math.log(confidence / (1.0 - confidence))
    contribution = cognition_config.WEIGHT_ACOUSTIC * (
        log_odds_acoustic - cognition_config.BASELINE_ACOUSTIC
    )
    fused_log_odds = cognition_config.L_PRIOR + contribution
    return fused_log_odds, sigmoid(fused_log_odds)


def _expected_seismic_vision_fusion(probability: float, vision_confidence: float):
    """Hand-computed (L, P) for a footfall event with a qualifying vision match too.

    L = L_PRIOR + WEIGHT_SEISMIC*(logit(probability)-BASELINE_SEISMIC)
              + WEIGHT_VISION*(logit(vision_confidence)-BASELINE_VISION);
    acoustic still contributes nothing (dropped). Same anti-tautology
    discipline as _expected_seismic_fusion above - math.log directly, never
    logit() or fuse() or reflex_loop's own _confidence_log_odds().
    """
    log_odds_seismic = math.log(probability / (1.0 - probability))
    log_odds_vision = math.log(vision_confidence / (1.0 - vision_confidence))
    contribution = cognition_config.WEIGHT_SEISMIC * (
        log_odds_seismic - cognition_config.BASELINE_SEISMIC
    ) + cognition_config.WEIGHT_VISION * (log_odds_vision - cognition_config.BASELINE_VISION)
    fused_log_odds = cognition_config.L_PRIOR + contribution
    return fused_log_odds, sigmoid(fused_log_odds)


def _fire(probability=0.9, sta_lta_ratio=6.0, schema_version=1, call_log=None, **fakes):
    """Call handle_footfall_event with sensible defaults and a shared call_log.

    Any of drive_horn/drive_led/pulse_ir/is_night/camera/detect_vision/
    save_frames/experience can be overridden via **fakes; unspecified ones
    get a default fake sharing call_log, so a test only has to construct the
    fake(s) it cares about. detect_vision defaults to a fake that always
    finds nothing - see _FakeVisionDetect's own docstring for why that keeps
    the existing fusion-value assertions valid. is_night defaults to "always
    night", which with the zero-length watch below means every default event
    runs blind-at-night: one unlit poll, and no pulse, because the night
    read needs a frame before the next poll can be lit. Illumination is
    exercised against _watch_for_vision() directly instead.

    The default experience store is fresh and in-memory, so an unspecified
    one means a cold store: no repeats, no learned values, and therefore
    tier 1. A test that needs history across events constructs one store and
    passes it to several _fire() calls.

    One consequence of ADR 0022 Decision B worth stating, because it is not
    obvious and it is what keeps every actuation test in this file passing
    unchanged: the default detect_vision finds nothing, so a default event
    only fires at all because the default is_night says night, and night
    with no illuminator is *blindness* - vision could not have seen the
    animal, so the gate stands down and the seismic decision carries the
    event. Override is_night to daylight and the same default event is
    correctly held instead. Tests that want the confirmed path - which is
    the path the field will actually fire on - pass a detector that returns
    ELEPHANT.
    """
    log = call_log if call_log is not None else []
    kwargs = {
        "drive_horn": fakes.pop("drive_horn", _FakeDriveHorn(call_log=log)),
        "drive_led": fakes.pop("drive_led", _FakeDriveLed(call_log=log)),
        "pulse_ir": fakes.pop("pulse_ir", _FakePulseIr(call_log=log)),
        "is_night": fakes.pop("is_night", lambda frames: True),
        "camera": fakes.pop("camera", _FakeCamera(call_log=log)),
        "detect_vision": fakes.pop("detect_vision", _FakeVisionDetect()),
        "save_frames": fakes.pop("save_frames", _FakeSaveFrames(call_log=log)),
        "experience": fakes.pop("experience", ExperienceStore(IN_MEMORY_PATH)),
        "bandit_params": fakes.pop("bandit_params", DETERMINISTIC_PARAMS),
        # ADR 0022's watch, collapsed to its single-poll floor. Every test in
        # this file that is not *about* the watch wants exactly one detection
        # pass and no wall-clock sleeping, which is what a zero-length window
        # gives (the watch always runs one poll). Popped rather than passed
        # below so the watch-specific tests can override them like any other
        # injected default.
        "vision_watch_base_s": fakes.pop("vision_watch_base_s", 0.0),
        "vision_watch_extended_s": fakes.pop("vision_watch_extended_s", 0.0),
        "vision_watch_poll_interval_s": fakes.pop("vision_watch_poll_interval_s", 0.0),
    }
    kwargs.update(fakes)
    outcome = reflex_loop.handle_footfall_event(
        schema_version,
        probability,
        sta_lta_ratio=sta_lta_ratio,
        feature_vector=[0.0] * 8,
        safe_mode=False,
        capture_post_fire_tail_s=0.0,
        video_retreat_tail_s=0.0,
        **kwargs,
    )
    return outcome, kwargs, log


# ---------------------------------------------------------------------------
# handle_footfall_event() - fusion/decision/horn (pre-existing coverage)
# ---------------------------------------------------------------------------


@TIER_FLOOR_OVERRIDE
def test_high_probability_alerts_and_fires_the_selected_tier_outside_safe_mode():
    """A strong footfall fuses past the threshold and fires the tier the bandit picked.

    On a cold store that is tier 1: horn and LED at tier 1's own values, and
    no IR at all. The IR assertion is the one that changed when the bandit
    landed - every alert used to fire all three actuators unconditionally.

    The default vision-check fake finds nothing (_FakeVisionDetect's own
    docstring), so VISION reads as available at BASELINE_VISION -
    contributing exactly zero to the fused log-odds, but that means it now
    counts as "used", not "dropped" (reflex_loop._vision_check()'s own
    docstring on why an unconfirmed check is still an available reading).
    """
    expected_log_odds, expected_p = _expected_seismic_fusion(0.9)
    outcome, kwargs, _ = _fire(0.9)

    assert outcome.fusion.log_odds == pytest.approx(expected_log_odds)
    assert outcome.fusion.probability == pytest.approx(expected_p)
    assert outcome.fusion.used == (Modality.SEISMIC, Modality.VISION)
    assert outcome.fusion.dropped == (Modality.ACOUSTIC,)
    assert Modality.ACOUSTIC not in outcome.fusion.contributions
    assert outcome.fusion.contributions[Modality.VISION] == pytest.approx(0.0)

    assert outcome.decision.alert is True
    assert outcome.action is TIER_1
    assert outcome.context == 0
    assert outcome.repeat_count == 0
    assert outcome.exploring is False
    assert outcome.horn_ack is True
    assert outcome.led_ack is True
    assert outcome.ir_ack is None
    assert kwargs["drive_horn"].calls == [
        (1, TIER_1.horn_gain_pct, TIER_1.horn_duration_ms, TIER_1.horn_track_id)
    ]
    assert kwargs["drive_led"].calls == [
        (
            1,
            TIER_1.led_channel_id,
            TIER_1.led_pattern_id,
            TIER_1.led_gain_pct,
            TIER_1.led_duration_ms,
        )
    ]
    assert kwargs["pulse_ir"].calls == []


def test_safe_mode_suppresses_all_actuation_and_camera():
    """SAFE_MODE must log the intended calls, never place any of them - including the camera."""
    log: list = []
    drive_horn = _FakeDriveHorn(call_log=log)
    drive_led = _FakeDriveLed(call_log=log)
    pulse_ir = _FakePulseIr(call_log=log)
    camera = _FakeCamera(call_log=log)
    save_frames = _FakeSaveFrames(call_log=log)

    outcome = reflex_loop.handle_footfall_event(
        1,
        0.9,
        sta_lta_ratio=6.0,
        feature_vector=[0.0] * 8,
        drive_horn=drive_horn,
        drive_led=drive_led,
        pulse_ir=pulse_ir,
        camera=camera,
        detect_vision=_FakeVisionDetect(),
        is_night=lambda frames: True,
        save_frames=save_frames,
        experience=ExperienceStore(IN_MEMORY_PATH),
        bandit_params=DETERMINISTIC_PARAMS,
        safe_mode=True,
    )

    assert outcome.decision.alert is True
    assert outcome.horn_ack is None
    assert outcome.led_ack is None
    assert outcome.ir_ack is None
    assert outcome.capture_frame_count == 0
    assert outcome.trigger_to_first_frame_s is None
    assert drive_horn.calls == []
    assert drive_led.calls == []
    assert pulse_ir.calls == []
    assert log == []  # nothing in this event touched the camera or storage either


def test_a_trigger_with_no_geophone_drops_the_modality_rather_than_scoring_it():
    """probability=0.0 with no geophone must be excluded, not read as a denial.

    This is why the flag reaches fuse() and not only the watch.
    `probability` is zero on a trigger the geophone never saw, and zero is
    honest - but a zero *scored* as a real reading is a strong statement
    that the ground is quiet, which drags the combined log-odds down and
    could suppress an alert the other modalities had already earned.
    Dropped and scored-as-zero are only distinguishable from outside by
    exactly this comparison, which is why both events are run rather than
    one asserted against a hand-computed number.
    """
    dropped, _, _ = _fire(probability=0.0, seismic_available=False)
    scored, _, _ = _fire(probability=0.0)

    assert Modality.SEISMIC in dropped.fusion.dropped
    assert Modality.SEISMIC not in dropped.fusion.contributions
    assert Modality.SEISMIC in scored.fusion.used
    assert scored.fusion.contributions[Modality.SEISMIC] < 0.0
    assert dropped.fusion.log_odds > scored.fusion.log_odds


def test_low_probability_does_not_alert_and_never_calls_any_actuator():
    """A weak footfall probability must not clear the threshold or fire anything.

    The camera IS still touched - the pre-decision vision check runs before
    decide() on every non-safe-mode event, alert or not (module docstring's
    "seismic wakes vision" ordering) - but it opens, captures once, and
    closes without ever reaching an actuator call or save_frames(). Fusion
    stays numerically unaffected: the default vision fake finds nothing, so
    VISION contributes zero either way (see the high-probability test's own
    note on why).
    """
    expected_log_odds, expected_p = _expected_seismic_fusion(0.05)
    assert expected_p < reflex_loop.ALERT_PROBABILITY_THRESHOLD  # sanity on the fixture
    outcome, kwargs, log = _fire(0.05, sta_lta_ratio=3.0)

    assert outcome.fusion.log_odds == pytest.approx(expected_log_odds)
    assert outcome.decision.alert is False
    assert outcome.horn_ack is None
    assert outcome.led_ack is None
    assert outcome.ir_ack is None
    assert outcome.capture_frame_count == 3  # the vision-check burst only
    assert kwargs["drive_horn"].calls == []
    assert log == ["camera.open", "camera.capture_burst", "camera.close"]
    assert kwargs["save_frames"].calls == []


def test_probability_at_exactly_zero_or_one_does_not_crash():
    """logit() rejects 0.0/1.0 outright - the epsilon clamp is what protects this call.

    Real MCU output realistically never saturates exactly, but the wire
    field is a plain float with no protocol-level guard against it.
    """
    outcome_zero, _, _ = _fire(0.0, sta_lta_ratio=0.0)
    outcome_one, _, _ = _fire(1.0, sta_lta_ratio=10.0)

    assert outcome_zero.decision.alert is False
    assert outcome_one.decision.alert is True


def test_custom_threshold_overrides_the_default():
    """A caller-supplied threshold takes priority over ALERT_PROBABILITY_THRESHOLD."""
    # 0.9 clears the default threshold (0.5) but not an intentionally strict one.
    outcome, kwargs, _ = _fire(0.9, threshold=0.999)

    assert outcome.decision.alert is False
    assert kwargs["drive_horn"].calls == []


def test_schema_version_mismatch_is_logged_not_raised(caplog):
    """A wire schema mismatch must warn, not raise - this is a notify target."""
    with caplog.at_level("WARNING"):
        outcome, _, _ = _fire(0.05, sta_lta_ratio=3.0, schema_version=99)

    assert outcome is not None
    assert any("schema_version mismatch" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# handle_footfall_event() - camera/capture wiring
# ---------------------------------------------------------------------------


@TIER_FLOOR_OVERRIDE
def test_camera_opens_before_actuators_and_closes_after_them_with_frames_saved():
    """Event order: open -> capture(vision) -> capture(evidence) -> horn -> led -> close -> save.

    No pulse_ir entry: this is tier 1 on a cold store, which fires no IR.
    The tiers that do fire it are covered by
    test_escalated_tier_fires_ir_in_the_documented_position. Two
    capture_burst entries, not one: the pre-decision vision check and the
    post-alert evidence burst both draw from the same already-open camera
    (module docstring) - capture_frame_count reflects both bursts combined.
    """
    outcome, kwargs, log = _fire(0.9)

    assert log == [
        "camera.open",
        "camera.capture_burst",
        "camera.capture_burst",
        "drive_horn",
        "drive_led",
        "camera.close",
        "save_frames",
    ]
    assert outcome.capture_frame_count == 6
    assert kwargs["camera"].opened is False  # closed, not left dangling


def test_saved_frames_are_tagged_with_the_triggering_event_metadata():
    """save_frames must receive the actual frames plus timestamp/ratio/probability/decision."""
    outcome, kwargs, _ = _fire(0.9, sta_lta_ratio=6.0)

    save_frames = kwargs["save_frames"]
    assert len(save_frames.calls) == 1
    frames, tag = save_frames.calls[0]
    assert len(frames) == outcome.capture_frame_count == 6
    assert isinstance(tag, CaptureEventTag)
    assert tag.sta_lta_ratio == 6.0
    assert tag.fused_probability == pytest.approx(outcome.fusion.probability)
    assert tag.alert is True
    assert tag.event_timestamp_s == pytest.approx(time.time(), abs=5.0)


@TIER_FLOOR_OVERRIDE
def test_camera_open_failure_never_blocks_actuator_firing(caplog):
    """The core safety requirement: a camera that won't open must not delay/suppress deterrence."""
    log: list = []
    camera = _FakeCamera(fail_open=True, call_log=log)

    with caplog.at_level("WARNING"):
        outcome, kwargs, log = _fire(0.9, camera=camera, call_log=log)

    assert outcome.horn_ack is True
    assert outcome.led_ack is True
    assert outcome.capture_frame_count == 0
    assert outcome.trigger_to_first_frame_s is None
    assert log == ["camera.open", "drive_horn", "drive_led"]  # no capture, no close
    assert kwargs["save_frames"].calls == []
    assert any("camera open failed" in record.message for record in caplog.records)


@TIER_FLOOR_OVERRIDE
def test_camera_capture_failure_never_blocks_actuator_firing_and_camera_still_closes(caplog):
    """A camera that opens but fails to capture must still let deterrence fire, and still close.

    Two capture_burst attempts, not one - the vision check and the evidence
    burst are separate calls against the same opened camera (module
    docstring), and this fake fails both.
    """
    log: list = []
    camera = _FakeCamera(fail_capture=True, call_log=log)

    with caplog.at_level("WARNING"):
        outcome, kwargs, log = _fire(0.9, camera=camera, call_log=log)

    assert outcome.horn_ack is True
    assert outcome.led_ack is True
    assert outcome.capture_frame_count == 0
    assert log == [
        "camera.open",
        "camera.capture_burst",
        "camera.capture_burst",
        "drive_horn",
        "drive_led",
        "camera.close",
    ]
    assert kwargs["save_frames"].calls == []  # nothing to save
    assert any("camera capture failed" in record.message for record in caplog.records)


def test_empty_burst_does_not_call_save_frames_but_camera_still_closes():
    """capture_burst() legitimately returning [] (no exception) must skip save_frames, not crash."""
    log: list = []
    camera = _FakeCamera(frame_count=0, call_log=log)

    outcome, kwargs, log = _fire(0.9, camera=camera, call_log=log)

    assert outcome.capture_frame_count == 0
    assert outcome.trigger_to_first_frame_s is None
    assert "camera.close" in log
    assert kwargs["save_frames"].calls == []


def test_save_frames_failure_is_logged_not_raised(caplog):
    """A storage fault (e.g. a full disk) must never crash the event handler."""
    log: list = []
    save_frames = _FakeSaveFrames(raises=OSError("disk full"), call_log=log)

    with caplog.at_level("WARNING"):
        outcome, _, _ = _fire(0.9, save_frames=save_frames, call_log=log)

    assert outcome.horn_ack is True  # actuation already happened before this ever runs
    assert any("failed to save capture burst" in record.message for record in caplog.records)


def test_trigger_to_first_frame_latency_is_instrumented_and_logged(caplog):
    """capture_post_fire_tail_s=0 keeps this fast; latency must still be a small, real number."""
    with caplog.at_level("INFO"):
        outcome, _, _ = _fire(0.9)

    assert outcome.trigger_to_first_frame_s is not None
    assert 0.0 <= outcome.trigger_to_first_frame_s < 1.0
    assert any("trigger-to-first-frame latency" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# handle_footfall_event() - vision wiring (28 Aug: seismic wakes vision,
# vision confirms, only then does fuse()/decide() run)
# ---------------------------------------------------------------------------


def test_a_qualifying_vision_match_raises_the_fused_probability():
    """An Elephant detection genuinely moves the fused probability, not just a log line.

    This is the core assertion for the whole vision-wiring feature: a real
    detection must change fuse()'s own math, not merely appear in a log
    message. Compared against _expected_seismic_vision_fusion's independent
    hand computation, never against reflex_loop's own _confidence_log_odds()
    or fuse() a second time (ENGINEERING_CONVENTIONS.md 4).
    """
    detection = Detection(
        label=reflex_loop.VISION_TARGET_LABELS[0],
        confidence=0.93,
        x=10.0,
        y=10.0,
        width=50.0,
        height=50.0,
    )
    expected_log_odds, expected_p = _expected_seismic_vision_fusion(0.9, 0.93)

    outcome, kwargs, _ = _fire(0.9, detect_vision=_FakeVisionDetect(detections=[detection]))

    assert outcome.fusion.log_odds == pytest.approx(expected_log_odds)
    assert outcome.fusion.probability == pytest.approx(expected_p)
    assert outcome.fusion.used == (Modality.SEISMIC, Modality.VISION)
    assert outcome.fusion.contributions[Modality.VISION] > 0.0
    assert kwargs["detect_vision"].calls, "detect_vision must actually have been called"


def test_a_non_target_label_detection_still_contributes_nothing():
    """A Boar detection is real signal, but not for the VISION fusion modality.

    ETX-V is a two-class detector; only a VISION_TARGET_LABELS class ("Elephant")
    counts as elephant-presence evidence here (module docstring, and
    reflex_loop._vision_check()'s own docstring) - a Boar match must not
    move the fused probability at all, the same as finding nothing.
    """
    boar = Detection(label="Boar", confidence=0.99, x=0.0, y=0.0, width=20.0, height=20.0)
    expected_log_odds, expected_p = _expected_seismic_fusion(0.9)

    outcome, _, _ = _fire(0.9, detect_vision=_FakeVisionDetect(detections=[boar]))

    assert outcome.fusion.log_odds == pytest.approx(expected_log_odds)
    assert outcome.fusion.probability == pytest.approx(expected_p)
    assert outcome.fusion.contributions[Modality.VISION] == pytest.approx(0.0)


def test_vision_detect_failure_is_logged_and_reported_unavailable(caplog):
    """A detector-side failure (network/timeout/bad response) must degrade, never block.

    Treated identically to a camera failure - see
    perception.detector.DetectionError's own docstring and
    reflex_loop._vision_check()'s. The alert path itself must still run to
    completion on seismic alone.
    """
    expected_log_odds, expected_p = _expected_seismic_fusion(0.9)

    with caplog.at_level("WARNING"):
        outcome, _, _ = _fire(
            0.9, detect_vision=_FakeVisionDetect(raises=DetectionError("no runner listening"))
        )

    assert outcome.fusion.log_odds == pytest.approx(expected_log_odds)
    assert outcome.fusion.probability == pytest.approx(expected_p)
    assert Modality.VISION in outcome.fusion.dropped
    assert Modality.VISION not in outcome.fusion.contributions
    assert outcome.horn_ack is True  # a dark detector must not suppress deterrence
    assert any("vision detect failed" in record.message for record in caplog.records)


def test_vision_check_runs_before_decide_even_without_an_alert():
    """The vision check happens on every non-safe-mode event, alert or not.

    Proves the "seismic wakes vision" ordering directly: detect_vision is
    called on a sub-threshold event too, before decide() ever runs - not
    only as post-alert evidence capture. See
    test_low_probability_does_not_alert_and_never_calls_any_actuator for the
    camera-log side of the same behavior.
    """
    detect_vision = _FakeVisionDetect()

    outcome, _, _ = _fire(0.05, sta_lta_ratio=3.0, detect_vision=detect_vision)

    assert outcome.decision.alert is False
    assert detect_vision.calls, "vision must have been checked even though nothing alerted"


# ---------------------------------------------------------------------------
# handle_footfall_event() - bandit selection and habituation avoidance
# ---------------------------------------------------------------------------


@TIER_FLOOR_OVERRIDE
def test_repeat_triggers_close_together_escalate_the_tier():
    """The habituation-avoidance mechanism, end to end through the real loop.

    Three alerts against one shared store, all inside
    HABITUATION_WINDOW_S of each other: the escalation floor forces tier 1,
    then 2, then 3. Nothing here depends on what the bandit learned - the
    floor is deterministic precisely so a returning animal cannot receive
    the same response twice while the values are still settling.
    """
    experience = ExperienceStore(IN_MEMORY_PATH)
    tiers = []
    for _ in range(3):
        outcome, _, _ = _fire(0.9, experience=experience)
        assert outcome.action is not None
        tiers.append(outcome.action.tier)

    assert tiers == [Tier.TIER_1, Tier.TIER_2, Tier.TIER_3]
    experience.close()


def test_escalation_saturates_at_the_top_tier():
    """A fourth and fifth repeat stay at tier 3 - the ladder has a top."""
    experience = ExperienceStore(IN_MEMORY_PATH)
    tiers = []
    for _ in range(5):
        outcome, _, _ = _fire(0.9, experience=experience)
        assert outcome.action is not None
        tiers.append(outcome.action.tier)

    assert tiers[-2:] == [Tier.TIER_3, Tier.TIER_3]
    experience.close()


# ---------------------------------------------------------------------------
# handle_footfall_event() - the deterrence sequence does not touch IR
# ---------------------------------------------------------------------------
#
# These used to be twelve tests covering a tier-gated pulse_ir, its day/night
# gate and its exposure lock, all inside the deterrence sequence. IR is a
# camera light, not a deterrent, so all of that moved into the vision watch
# and is tested against _watch_for_vision() directly, further down this file
# under "vision-watch illumination". What is left here is the handler-level
# half: that the deterrence sequence really has stopped firing it, and that
# what the watch did still reaches the outcome.


@TIER_FLOOR_OVERRIDE
def test_an_escalated_tier_fires_two_actuators_and_not_a_third():
    """Tier 2 is a horn and an LED. There is no third actuator to escalate to.

    The ordering assertion is the point, not just the absence: the whole
    sequence is now deterministic, where it used to need a set() over
    positions 2-3 because pulse_ir raced the evidence burst on its own
    thread. Nothing in the deterrence path is concurrent with the capture
    any more.
    """
    experience = ExperienceStore(IN_MEMORY_PATH)
    _fire(0.9, experience=experience)

    log: list = []
    outcome, kwargs, log = _fire(0.9, experience=experience, call_log=log)

    assert outcome.action.tier is Tier.TIER_2
    assert kwargs["pulse_ir"].calls == []
    assert log == [
        "camera.open",
        "camera.capture_burst",  # the watch's single poll
        "camera.capture_burst",  # the evidence burst
        "drive_horn",
        "drive_led",
        "camera.close",
        "save_frames",
    ]
    experience.close()


@TIER_FLOOR_OVERRIDE
@pytest.mark.parametrize("tier_primer", [0, 1, 2])
def test_no_tier_illuminates_anything(tier_primer):
    """Walk the whole ladder and assert the illuminator never fires from it.

    Parametrised over the ladder rather than asserted on tier 2 alone,
    because the defect being guarded against is a partial revert - IR
    reinstated on the top tier only, say, where a casual reading of the
    deterrence tests would not notice it.
    """
    experience = ExperienceStore(IN_MEMORY_PATH)
    for _ in range(tier_primer):
        _fire(0.9, experience=experience)

    outcome, kwargs, _ = _fire(0.9, experience=experience)

    assert outcome.action is not None
    assert kwargs["pulse_ir"].calls == []
    assert outcome.ir_ack is None
    experience.close()


@TIER_FLOOR_OVERRIDE
def test_a_single_poll_watch_never_illuminates_even_at_night():
    """The documented cost of reading day/night off a frame: poll one is dark.

    Not a defect, and worth pinning so it is not "fixed" into one. The
    night read needs a frame to read, so the first poll is always unlit;
    illumination starts on the poll after night is established. A watch
    that confirms on its first poll therefore never lights anything - and
    it did not need to, because it confirmed.

    Every other test in this file runs on exactly this configuration
    (_fire() collapses the watch to its single-poll floor), which is why
    none of them see a pulse.
    """
    outcome, kwargs, _ = _fire(
        0.9,
        is_night=lambda frames: True,
        detect_vision=_FakeVisionDetect([ELEPHANT]),
    )

    assert outcome.species == "Elephant"
    assert kwargs["pulse_ir"].calls == []
    assert outcome.ir_ack is None


@TIER_FLOOR_OVERRIDE
def test_what_the_watch_illuminated_is_reported_on_the_outcome(caplog):
    """ir_ack survives from the watch to the outcome, and says so in the log.

    A night event's footage is only interpretable if you know whether the
    illuminator was actually on for it. The ack is the only evidence of
    that the node keeps - it does not go on the LoRa wire (ADR 0031 A),
    so if it is dropped here it is gone.
    """
    pulse_ir = _FakePulseIr()
    with caplog.at_level("INFO"):
        outcome, _, _ = _fire(
            0.9,
            pulse_ir=pulse_ir,
            is_night=lambda frames: True,
            vision_watch_base_s=3.0,
            vision_watch_poll_interval_s=1.0,
        )

    assert pulse_ir.calls, "a multi-poll night watch must have illuminated"
    assert outcome.ir_ack is True
    assert any("vision watch illuminated" in r.message for r in caplog.records)


@TIER_FLOOR_OVERRIDE
def test_sub_threshold_events_still_count_toward_habituation():
    """A non-alerting trigger must still escalate the next real alert.

    An animal circling a node while fusion stays just under the threshold is
    exactly the case the repeat count exists for - if only alerts were
    counted, the loop would keep answering a persistent visitor at tier 1.
    """
    experience = ExperienceStore(IN_MEMORY_PATH)
    quiet, _, _ = _fire(0.05, sta_lta_ratio=3.0, experience=experience)
    assert quiet.decision.alert is False
    assert quiet.action is None
    assert quiet.context is None

    loud, _, _ = _fire(0.9, experience=experience)
    assert loud.repeat_count == 1
    assert loud.action.tier is Tier.TIER_2
    experience.close()


@TIER_FLOOR_OVERRIDE
def test_a_fired_attempt_is_recorded_and_settled_by_the_next_event():
    """The full learning round trip: fire, come back, score, store the value.

    The gap between the two events here is milliseconds against the
    PROXY_REWARD_HORIZON_S, so the proxy reward is essentially zero - a
    returning animal is the failure case, and the value that lands in the
    store must reflect that. Asserting "a value now exists and it is near
    zero" is the honest assertion; asserting a specific figure would be
    asserting how long the test itself took to run.
    """
    experience = ExperienceStore(IN_MEMORY_PATH)
    _fire(0.9, experience=experience)
    assert experience.action_values() == {}

    second, _, _ = _fire(0.9, experience=experience)
    assert second.settled is not None
    assert second.settled.tier is Tier.TIER_1
    assert second.settled.context == 0
    assert second.settled.visits == 1
    assert second.settled.reward == pytest.approx(0.0, abs=0.01)

    assert (0, Tier.TIER_1) in experience.action_values()
    experience.close()


@TIER_FLOOR_OVERRIDE
def test_learning_survives_a_restart_through_the_real_loop(tmp_path):
    """Two runs against one on-disk database: the second sees the first's history.

    A real file, a real close(), and a second ExperienceStore constructed
    from scratch - the closest a host test gets to the MPU's own
    suspend/resume cycle. The escalation carrying across is the observable
    proof: run two starts at tier 2, which is only possible if run one's
    trigger persisted.
    """
    db_path = tmp_path / "data" / "experience.sqlite3"

    first = ExperienceStore(db_path)
    first_outcome, _, _ = _fire(0.9, experience=first)
    first.close()

    assert first_outcome.action is TIER_1

    second = ExperienceStore(db_path)
    second_outcome, _, _ = _fire(0.9, experience=second)
    second.close()

    assert second_outcome.repeat_count == 1
    assert second_outcome.action.tier is Tier.TIER_2
    assert second_outcome.settled is not None  # run one's attempt scored here


def test_a_refused_horn_records_no_attempt(caplog):
    """A false ack means nothing fired, so the tier must not be credited.

    rule_gate_apply() returns allowed=false only when it refuses a request
    inside HORN_COOLDOWN_MS - the horn stayed silent. Learning from that
    would attribute whatever the animal did next to a burst that never
    happened.
    """
    experience = ExperienceStore(IN_MEMORY_PATH)
    with caplog.at_level("INFO"):
        outcome, _, _ = _fire(
            0.9, experience=experience, drive_horn=_FakeDriveHorn(ack=False)
        )

    assert outcome.horn_ack is False
    _fire(0.9, experience=experience)
    assert experience.action_values() == {}
    assert any("recording no attempt" in record.message for record in caplog.records)
    experience.close()


@TIER_FLOOR_OVERRIDE
def test_safe_mode_selects_a_tier_but_records_no_attempt(caplog):
    """A dry run must still choose and log a tier, and must still learn nothing.

    Both halves matter. The selection has to be real or the SAFE_MODE log
    would not tell an operator what the device would actually have done; the
    attempt has to be absent because nothing fired, and a bandit credited
    for silence would learn from a deterrence that never occurred.
    """
    experience = ExperienceStore(IN_MEMORY_PATH)
    with caplog.at_level("INFO"):
        outcome = reflex_loop.handle_footfall_event(
            1,
            0.9,
            sta_lta_ratio=6.0,
            feature_vector=[0.0] * 8,
            drive_horn=_FakeDriveHorn(),
            drive_led=_FakeDriveLed(),
            pulse_ir=_FakePulseIr(),
            camera=_FakeCamera(),
            detect_vision=_FakeVisionDetect(),
            is_night=lambda frames: True,
            save_frames=_FakeSaveFrames(),
            experience=experience,
            bandit_params=DETERMINISTIC_PARAMS,
            safe_mode=True,
        )

    assert outcome.action is TIER_1
    assert outcome.exploring is False
    assert any("[SAFE_MODE]" in record.message for record in caplog.records)

    # A second event has nothing to settle, because the first recorded nothing.
    second = reflex_loop.handle_footfall_event(
        1,
        0.9,
        sta_lta_ratio=6.0,
        feature_vector=[0.0] * 8,
        drive_horn=_FakeDriveHorn(),
        drive_led=_FakeDriveLed(),
        pulse_ir=_FakePulseIr(),
        camera=_FakeCamera(),
        detect_vision=_FakeVisionDetect(),
        is_night=lambda frames: True,
        save_frames=_FakeSaveFrames(),
        experience=experience,
        bandit_params=DETERMINISTIC_PARAMS,
        safe_mode=True,
    )
    assert second.settled is None
    assert experience.action_values() == {}
    experience.close()


def test_safe_mode_still_records_the_trigger():
    """A dry run observes real events even though it does not respond to them.

    The repeat count is a property of what the node saw, not of what it
    fired, so suppressing it under SAFE_MODE would make a dry run report a
    context the device would never actually have been in.
    """
    experience = ExperienceStore(IN_MEMORY_PATH)
    for _ in range(2):
        reflex_loop.handle_footfall_event(
            1,
            0.9,
            sta_lta_ratio=6.0,
            feature_vector=[0.0] * 8,
            drive_horn=_FakeDriveHorn(),
            drive_led=_FakeDriveLed(),
            pulse_ir=_FakePulseIr(),
            camera=_FakeCamera(),
            detect_vision=_FakeVisionDetect(),
            is_night=lambda frames: True,
            save_frames=_FakeSaveFrames(),
            experience=experience,
            bandit_params=DETERMINISTIC_PARAMS,
            safe_mode=True,
        )

    third, _, _ = _fire(0.9, experience=experience)
    assert third.repeat_count == 2
    # Tier 3 rotates its LED pattern per fire (ADR 0014 E.2), so the action
    # is a fresh object, not the DETERRENCE_TIERS[TIER_3] singleton - assert
    # on the tier, not identity.
    assert third.action is not None
    assert third.action.tier is Tier.TIER_3
    experience.close()


def test_a_learned_preference_beats_the_default_tie_break():
    """Once a tier has earned value, greedy selection prefers it over tier 1.

    Seeded directly into the store rather than trained through the loop:
    training a preference in-process would take a real PROXY_REWARD_HORIZON_S
    worth of wall clock. What is under test is that the loop reads the stored
    values and acts on them, not that the update arithmetic works - that is
    tests/test_experience.py's job. The seeded attempt is dated well past
    that horizon so it settles at a saturated (full) proxy reward.
    """
    experience = ExperienceStore(IN_MEMORY_PATH)
    experience.record_attempt(time.time() - 15000.0, 0, Tier.TIER_3)
    experience.settle_pending(time.time(), DETERMINISTIC_PARAMS)

    outcome, kwargs, _ = _fire(0.9, experience=experience)

    # Tier 3's action is a fresh object per fire (ADR 0014 E.2 LED-pattern
    # rotation), so assert on the tier rather than identity.
    assert outcome.action is not None
    assert outcome.action.tier is Tier.TIER_3
    assert outcome.exploring is False
    experience.close()


@TIER_FLOOR_OVERRIDE
def test_exploration_is_reported_when_it_happens():
    """With epsilon 1.0 the outcome must say the tier came from exploration.

    Reported rather than inferred so a field log can distinguish "the bandit
    believes tier 3 is best here" from "the bandit rolled a die" - the two
    look identical in the actuator record otherwise.
    """
    experience = ExperienceStore(IN_MEMORY_PATH)
    always_explores = dataclasses.replace(cognition_config.DEFAULT_BANDIT_PARAMS, epsilon=1.0)

    outcome, _, _ = _fire(0.9, experience=experience, bandit_params=always_explores)

    assert outcome.exploring is True
    assert outcome.action is not None
    assert outcome.action.tier in (Tier.TIER_1, Tier.TIER_2, Tier.TIER_3)
    experience.close()


# ---------------------------------------------------------------------------
# handle_acoustic_event()
# ---------------------------------------------------------------------------


def _route(
    schema_version=1,
    class_label=AcousticClass.ELEPHANT_CALL,
    confidence=0.5,
    capture_ref=0,
    *,
    safe_mode=True,
    call_log=None,
    send_lora_alert=None,
    start_vision_event=None,
):
    log = call_log if call_log is not None else []
    fake = send_lora_alert if send_lora_alert is not None else _FakeSendLoraAlert(call_log=log)
    vision = start_vision_event if start_vision_event is not None else _FakeStartVisionEvent()
    outcome = reflex_loop.handle_acoustic_event(
        schema_version,
        class_label,
        confidence,
        capture_ref,
        safe_mode=safe_mode,
        send_lora_alert=fake,
        start_vision_event=vision,
    )
    return outcome, fake, log


def test_acoustic_event_is_logged_and_returns_its_outcome(caplog):
    """Every acoustic event is logged and reports which route ADR 0007 5 sent it down."""
    with caplog.at_level("INFO"):
        outcome, _, _ = _route(class_label=AcousticClass.GUNSHOT, confidence=0.87, capture_ref=42)

    assert outcome.class_label is AcousticClass.GUNSHOT
    assert outcome.direct_alert is True
    assert any("gunshot" in record.message for record in caplog.records)


def test_gunshot_never_reaches_the_elephant_path_and_logs_a_direct_alert(caplog):
    """ADR 0007 5's central rule, as a regression guard.

    The ADR is explicit that a gunshot is not evidence toward "is an elephant
    present", and that folding it into the elephant-presence score would be
    a modeling error. Two assertions say so from different directions:
    nothing fused (there is no probability anywhere in the log line), and
    nothing started an event, so the camera was never opened and the horn
    was never a possibility.
    """
    vision = _FakeStartVisionEvent()
    with caplog.at_level("INFO"):
        outcome, fake, _ = _route(
            class_label=AcousticClass.GUNSHOT,
            confidence=0.93,
            capture_ref=7,
            start_vision_event=vision,
        )

    assert outcome.footfall is None
    assert vision.calls == []
    assert outcome.direct_alert is True
    assert outcome.lora_ack is None
    assert fake.calls == []

    messages = [record.message for record in caplog.records]
    assert any(
        "[SAFE_MODE]" in m and "would send direct gunshot alert" in m for m in messages
    )
    # The would-send line carries the real confidence/capture_ref an actual
    # uplink would have to put on the wire, not a placeholder.
    assert any("confidence=0.930" in m and "capture_ref=7" in m for m in messages)
    # Nothing anywhere in this event claims a fused probability.
    assert not any("fused_P" in m for m in messages)


def test_gunshot_calls_send_lora_alert_outside_safe_mode(caplog):
    """Outside safe_mode, the gunshot branch calls the injected transport for real.

    ELETECT_SAFE_MODE=0 does not conjure a radio that is not joining - the
    ack send_lora_alert returns still only means "queued/logged on the MCU",
    never "delivered" - but the call itself is real, not logged-and-skipped.
    """
    with caplog.at_level("INFO"):
        outcome, fake, _ = _route(
            class_label=AcousticClass.GUNSHOT,
            confidence=0.93,
            capture_ref=7,
            safe_mode=False,
            send_lora_alert=_FakeSendLoraAlert(ack=True),
        )

    assert outcome.footfall is None
    assert outcome.direct_alert is True
    assert outcome.lora_ack is True
    # The class travels with the call: lora_uplink picks the EventClass from
    # it, and an officer reading GUNSHOT vs CHAINSAW is reading two
    # different emergencies.
    assert fake.calls == [(1, "gunshot", 0.93, 7)]

    messages = [record.message for record in caplog.records]
    assert any("send_lora_alert ack=True" in m and "confidence=0.930" in m for m in messages)


@pytest.mark.parametrize(
    "class_label",
    [
        AcousticClass.ELEPHANT_CALL,
        AcousticClass.AMBIENT,
    ],
)
def test_send_lora_alert_is_never_called_for_the_non_alerting_classes(class_label):
    """Only a direct-alert classification may touch send_lora_alert, safe_mode or not."""
    outcome, fake, _ = _route(
        class_label=class_label, confidence=0.8, capture_ref=9, safe_mode=False
    )

    assert outcome.direct_alert is False
    assert fake.calls == []


def test_an_elephant_call_starts_a_vision_gated_event_and_alerts_nothing_itself():
    """ADR 0033: the microphone opens the camera, it does not raise the alarm.

    Two failures are pinned here at once, and they pull in opposite
    directions. The first is the one this fixes: `elephant_call` used to
    fuse and return, which meant the best class in the trained model - the
    only one that is direct evidence of an elephant rather than a
    correlate - could not cause anything to happen. The second is the one
    that makes the fix dangerous if done carelessly: fuse() is stateless
    per event, so a single high-confidence acoustic reading with nothing
    to corroborate it crosses ALERT_PROBABILITY_THRESHOLD on its own, and
    letting this branch alert directly would turn the acoustic model into
    a standalone elephant detector - exactly the defect ADR 0033 removed
    from chainsaw. Starting a vision-gated event satisfies both: the
    confidence travels, and the camera decides.
    """
    vision = _FakeStartVisionEvent(outcome=_FAKE_FOOTFALL)

    outcome, fake, _ = _route(
        class_label=AcousticClass.ELEPHANT_CALL,
        confidence=0.8,
        capture_ref=5,
        safe_mode=False,
        start_vision_event=vision,
    )

    assert vision.calls == [0.8]
    assert outcome.footfall is _FAKE_FOOTFALL
    assert outcome.direct_alert is False
    assert outcome.lora_ack is None
    # Nothing on this branch touches the direct-alert transport, even
    # outside safe_mode. Whatever reaches the air comes out of the event
    # the camera confirmed, not out of the classification.
    assert fake.calls == []


def test_a_dropped_vision_event_is_reported_as_nothing_having_run():
    """The event mutex's refusal must not read as "looked and saw nothing".

    start_vision_event returns None when another event already owned the
    camera and the actuators. An AcousticOutcome that reported that the
    same way it reports an unconfirmed watch would tell a later reader the
    node looked at this call, which it did not.
    """
    vision = _FakeStartVisionEvent(outcome=None)

    outcome, _, _ = _route(
        class_label=AcousticClass.ELEPHANT_CALL,
        confidence=0.8,
        capture_ref=5,
        start_vision_event=vision,
    )

    assert vision.calls == [0.8]
    assert outcome.footfall is None
    assert outcome.direct_alert is False


def test_a_chainsaw_alerts_officers_directly_and_never_fuses():
    """ADR 0033's whole point, and the regression it exists to stop.

    A chainsaw means people, not an elephant. While it fused, two things
    were wrong at once: it carried the same WEIGHT_ACOUSTIC as an elephant
    call, which is not a defensible equivalence, and - because fuse() sees
    no seismic or vision reading on this path - a chainsaw at 0.9 crossed
    ALERT_PROBABILITY_THRESHOLD on its own, making the acoustic model a
    standalone elephant detector (docs/KNOWN_GAPS.md).

    A chainsaw must also not take elephant_call's new route: starting a
    vision watch and a deterrence decision over illegal felling would point
    the horn at the wrong problem and delay the alert that matters.
    """
    vision = _FakeStartVisionEvent()
    outcome, fake, _ = _route(
        class_label=AcousticClass.CHAINSAW,
        confidence=0.9,
        capture_ref=3,
        safe_mode=False,
        start_vision_event=vision,
    )

    assert outcome.direct_alert is True
    assert outcome.footfall is None
    assert vision.calls == []
    assert fake.calls == [(1, "chainsaw", 0.9, 3)]


def test_the_two_acoustic_routes_are_disjoint_and_cover_the_model():
    """No class may both start an event and alert, and none may fall off the end.

    The routing is three branches reading two frozensets, which is exactly
    the shape that rots silently when a class is added to the model: a 5th
    class in neither set would fall through to the ambient branch and be
    discarded with a log line, which is the quietest possible way for a
    detection to stop existing. Asserting against AcousticClass itself
    rather than against a hand-written list is what makes this test notice
    that.
    """
    vision_event = reflex_loop._VISION_EVENT_ACOUSTIC_CLASSES
    direct = reflex_loop._DIRECT_ALERT_ACOUSTIC_CLASSES

    assert vision_event.isdisjoint(direct)
    # AMBIENT is deliberately in neither: it is the one class whose correct
    # handling is to do nothing. Every other class the model can emit must
    # have been routed on purpose.
    assert set(AcousticClass) - vision_event - direct == {AcousticClass.AMBIENT}


def test_an_acoustic_elephant_call_fuses_through_the_one_acoustic_weight():
    """ADR 0033 reuses the existing pipeline, which means the existing weight.

    The point of routing an elephant call into handle_footfall_event()
    rather than building a second decision path is that it arrives as the
    ACOUSTIC modality, through the one WEIGHT_ACOUSTIC/BASELINE_ACOUSTIC
    pair ADR 0007 5 gave acoustic, and through ADR 0022's blindness logic -
    not through a parallel copy that can drift. Hand-computed against the
    real params rather than against fuse().

    Checked at two confidences deliberately: agreeing at one value could be
    coincidence, agreeing at two can only hold if the reading really is
    routed through that pair rather than through anything that happens to
    pass through the same point.

    The seismic modality must be *dropped* rather than scored. There is no
    geophone reading on this path, and probability=0.0 taken as a real
    reading would read as "the ground says no" and could suppress an alert
    the call had already earned.
    """
    for confidence in (0.62, 0.91):
        expected_log_odds, expected_p = _expected_acoustic_fusion(confidence)

        outcome, _, _ = _fire(
            probability=0.0,
            sta_lta_ratio=0.0,
            acoustic_confidence=confidence,
            seismic_available=False,
        )

        # VISION is present and at its baseline - _fire()'s default
        # detector finds nothing on a night event, which ADR 0022 scores as
        # blindness rather than as absence - so it contributes exactly
        # zero and _expected_acoustic_fusion() still describes the sum.
        assert outcome.fusion.used == (Modality.ACOUSTIC, Modality.VISION)
        assert outcome.fusion.contributions[Modality.VISION] == pytest.approx(0.0)
        assert Modality.SEISMIC in outcome.fusion.dropped
        assert Modality.SEISMIC not in outcome.fusion.contributions
        assert outcome.fusion.log_odds == pytest.approx(expected_log_odds)
        assert outcome.fusion.probability == pytest.approx(expected_p)


def test_ambient_routes_nowhere_at_all():
    """Ambient is the absence of something to act on, and now costs nothing.

    It used to go through fuse() so the result could honestly record
    "acoustic was present and had nothing to say". With chainsaw gone to
    the officers and elephant_call gone to the camera, that FusionResult
    had no second modality to combine with and no reader: it was the prior,
    every time, dressed up as a detection. What must not change is that
    ambient is still not negative evidence - it simply ends here, rather
    than being scored against an elephant somewhere else.
    """
    vision = _FakeStartVisionEvent(outcome=_FAKE_FOOTFALL)

    outcome, fake, _ = _route(
        class_label=AcousticClass.AMBIENT,
        confidence=0.99,
        capture_ref=5,
        safe_mode=False,
        start_vision_event=vision,
    )

    assert outcome.direct_alert is False
    assert outcome.footfall is None
    assert outcome.lora_ack is None
    assert vision.calls == []
    assert fake.calls == []


def test_the_acoustic_confidence_reaches_the_vision_event_unmodified():
    """handle_acoustic_event() no longer converts anything, including the endpoints.

    logit() rejects 0.0 and 1.0 outright, and both are representable values
    a wire float could carry. The clamp that protects it now lives in
    handle_footfall_event() alone - one clamp rather than two that can
    drift - so what this path owes is to hand the raw value across
    untouched. Both endpoints are exercised because a defensive clamp added
    here later would be invisible at any ordinary confidence.
    """
    zero = _FakeStartVisionEvent()
    one = _FakeStartVisionEvent()

    _route(
        class_label=AcousticClass.ELEPHANT_CALL,
        confidence=0.0,
        capture_ref=1,
        start_vision_event=zero,
    )
    _route(
        class_label=AcousticClass.ELEPHANT_CALL,
        confidence=1.0,
        capture_ref=2,
        start_vision_event=one,
    )

    assert zero.calls == [0.0]
    assert one.calls == [1.0]


def test_a_footfall_event_survives_an_acoustic_confidence_at_the_endpoints():
    """The clamp that moved still exists, on the side that now owns it.

    _confidence_log_odds() is shared with the seismic reading, but nothing
    exercised it through acoustic_confidence until this parameter existed.
    """
    low, _, _ = _fire(probability=0.0, acoustic_confidence=0.0, seismic_available=False)
    high, _, _ = _fire(probability=0.0, acoustic_confidence=1.0, seismic_available=False)

    assert math.isfinite(low.fusion.log_odds)
    assert math.isfinite(high.fusion.log_odds)
    assert low.fusion.probability < high.fusion.probability


def test_acoustic_schema_version_mismatch_is_logged_not_raised(caplog):
    """A mismatched schema_version is a warning, never an exception - and still routes."""
    with caplog.at_level("WARNING"):
        outcome, _, _ = _route(
            schema_version=99,
            class_label=AcousticClass.ELEPHANT_CALL,
            confidence=0.8,
            capture_ref=4,
            start_vision_event=_FakeStartVisionEvent(outcome=_FAKE_FOOTFALL),
        )

    assert outcome.footfall is _FAKE_FOOTFALL
    assert any(
        "schema_version mismatch" in record.message and record.levelname == "WARNING"
        for record in caplog.records
    )


# ---------------------------------------------------------------------------
# Trigger-gated event video (ADR 0020)
# ---------------------------------------------------------------------------


ELEPHANT = Detection(label="Elephant", confidence=0.9, x=0.0, y=0.0, width=40.0, height=30.0)
BOAR = Detection(label="Boar", confidence=0.99, x=0.0, y=0.0, width=20.0, height=20.0)
FOX = Detection(label="Fox", confidence=0.95, x=0.0, y=0.0, width=8.0, height=6.0)
# A low-confidence sighting: enough to confirm for the keep-gate, not enough
# to carry a weak seismic trigger past the alert threshold. That combination
# is the only way to reach the "confirmed but not alerted" branch, and it is
# a real one - a distant or partly-occluded animal on a soft trigger.
FAINT_ELEPHANT = Detection(
    label="Elephant", confidence=0.55, x=0.0, y=0.0, width=8.0, height=6.0
)


class _FakeEventVideo:
    """Recording stand-in for perception.video.EventVideoRecorder's decision half.

    Only commit()/discard() - the reflex loop never starts or stops a
    recording, because the recorder is the same object already injected as
    `camera`. Tests that care about the ordering between the camera and the
    decision pass the shared call_log.

    Args:
        raises: If set, both commit() and discard() raise it - exercises
            "evidence housekeeping must never crash the handler".
        call_log: Shared cross-fake call-order log, see _FakeDriveHorn.
    """

    def __init__(self, raises: Exception | None = None, call_log: list | None = None):
        self._raises = raises
        self.call_log = call_log if call_log is not None else []
        self.committed: list[CaptureEventTag] = []
        self.discarded = 0
        self.path = Path("committed.mkv")

    def commit(self, tag):
        self.call_log.append("video.commit")
        if self._raises is not None:
            raise self._raises
        self.committed.append(tag)
        return self.path

    def discard(self):
        self.call_log.append("video.discard")
        if self._raises is not None:
            raise self._raises
        self.discarded += 1


def test_event_video_is_committed_when_an_alert_fires():
    """Half of the keep-gate: a real deterrence event is always worth keeping.

    Whatever the camera resolved. An alert that fired without a vision
    confirmation is still a horn going off in a forest at night, and the
    footage is the only record of what it went off at.
    """
    video = _FakeEventVideo()

    outcome, _, _ = _fire(probability=0.9, event_video=video)

    assert outcome.decision.alert is True
    assert outcome.vision_confirmed is False
    assert video.discarded == 0
    assert len(video.committed) == 1
    assert video.committed[0].alert is True
    assert outcome.video_path == video.path


def test_event_video_is_committed_when_vision_confirms_without_an_alert():
    """The other half, and the one that only exists because of this ADR.

    A weak seismic trigger that the camera nonetheless confirms as an
    elephant produces no alert and, before ADR 0020, no evidence at all -
    the JPEG burst is alert-only. That is exactly the event worth
    reviewing: it is either a threshold that is set too high or a detector
    that is wrong, and the clip is the only way to tell which.
    """
    video = _FakeEventVideo()

    outcome, _, _ = _fire(
        probability=0.01,
        sta_lta_ratio=1.2,
        detect_vision=_FakeVisionDetect([FAINT_ELEPHANT]),
        event_video=video,
    )

    assert outcome.decision.alert is False
    assert outcome.vision_confirmed is True
    assert video.discarded == 0
    assert len(video.committed) == 1
    # Named for what actually happened, not for what a burst would imply.
    assert video.committed[0].alert is False
    assert outcome.video_path == video.path


def test_event_video_is_discarded_when_neither_gate_is_satisfied():
    """The common case, and the one that bounds the storage cost.

    Wind, a passing boar, an STA/LTA false positive: no alert, nothing
    confirmed, nothing kept. The recording never reaches the permanent
    capture directory at all.
    """
    video = _FakeEventVideo()

    outcome, _, _ = _fire(
        probability=0.05,
        sta_lta_ratio=1.2,
        detect_vision=_FakeVisionDetect([BOAR]),
        event_video=video,
    )

    assert outcome.decision.alert is False
    assert outcome.vision_confirmed is False
    assert video.committed == []
    assert video.discarded == 1
    assert outcome.video_path is None


def test_a_boar_detection_is_not_a_confirmation():
    """The two-class model's other label must not keep footage on its own.

    Same discipline the vision ModalityReading already follows: only
    VISION_TARGET_LABEL counts toward "elephant present". A Boar box is a
    real detection and still not this system's subject.
    """
    outcome, _, _ = _fire(
        probability=0.05,
        sta_lta_ratio=1.2,
        detect_vision=_FakeVisionDetect([BOAR, ELEPHANT]),
    )
    assert outcome.vision_confirmed is True

    outcome, _, _ = _fire(
        probability=0.05, sta_lta_ratio=1.2, detect_vision=_FakeVisionDetect([BOAR])
    )
    assert outcome.vision_confirmed is False


def test_a_failed_vision_check_is_not_a_confirmation():
    """A detector that raised saw nothing - it must not keep footage by default.

    DetectionError already degrades VISION to unavailable for fusion. The
    keep-gate has to degrade the same way, or an inference server that is
    down turns every trigger into a kept clip.
    """
    outcome, _, _ = _fire(
        probability=0.05,
        sta_lta_ratio=1.2,
        detect_vision=_FakeVisionDetect(raises=DetectionError("inference server down")),
    )

    assert outcome.vision_confirmed is False


def test_event_video_is_decided_only_after_every_actuator_has_fired():
    """The ordering ADR 0020 rests on: footage never delays deterrence.

    The whole reason this design records on trigger instead of maintaining
    a rolling pre-buffer is that neither the recording nor the
    keep-or-discard decision may sit between the MCU's notify and the
    horn. This asserts the call order directly rather than trusting the
    code to have kept it.
    """
    log = []
    video = _FakeEventVideo(call_log=log)

    _fire(probability=0.9, call_log=log, event_video=video)

    assert "drive_horn" in log
    assert log.index("drive_horn") < log.index("video.commit")
    assert log.index("camera.close") < log.index("video.commit")


def test_safe_mode_never_touches_the_event_video():
    """A dry run observes; it does not record, keep or delete anything.

    SAFE_MODE already gates the camera, so nothing was ever recorded -
    calling discard() here would be harmless but dishonest, implying a
    decision about a recording that does not exist.
    """
    video = _FakeEventVideo()

    outcome = reflex_loop.handle_footfall_event(
        1,
        0.9,
        sta_lta_ratio=6.0,
        feature_vector=[0.0] * 8,
        safe_mode=True,
        drive_horn=_FakeDriveHorn(),
        drive_led=_FakeDriveLed(),
        pulse_ir=_FakePulseIr(),
        is_night=lambda frames: True,
        camera=_FakeCamera(),
        detect_vision=_FakeVisionDetect(),
        save_frames=_FakeSaveFrames(),
        experience=ExperienceStore(IN_MEMORY_PATH),
        event_video=video,
    )

    assert video.committed == []
    assert video.discarded == 0
    assert outcome.video_path is None
    assert outcome.vision_confirmed is False


def test_an_alert_still_commits_when_the_camera_never_opened():
    """A camera failure must not leave the decision unmade.

    The recorder discards its own scratch file on a failed open(), so this
    commit is a no-op in production - but the loop must still reach a
    decision on every exit, because an exit that silently skips it is
    exactly how a scratch file leaks.
    """
    video = _FakeEventVideo()

    outcome, _, log = _fire(
        probability=0.9, camera=_FakeCamera(fail_open=True), event_video=video
    )

    assert outcome.decision.alert is True
    assert "drive_horn" in log
    assert len(video.committed) == 1


def test_a_commit_failure_never_crashes_the_handler():
    """Storage housekeeping must not cost the next event.

    perception/video.py's commit() is documented as never raising, so
    anything arriving here is unanticipated - and this node is in a forest
    where an unhandled exception in the event handler is not recoverable
    until someone walks to it.
    """
    outcome, _, _ = _fire(probability=0.9, event_video=_FakeEventVideo(raises=OSError("no disk")))

    assert outcome.decision.alert is True
    assert outcome.video_path is None


def test_a_discard_failure_never_crashes_the_handler():
    """Same contract on the branch that runs far more often than the alert one."""
    outcome, _, _ = _fire(
        probability=0.05,
        sta_lta_ratio=1.2,
        event_video=_FakeEventVideo(raises=OSError("read-only filesystem")),
    )

    assert outcome.decision.alert is False
    assert outcome.video_path is None


def test_the_retreat_tail_replaces_the_post_fire_tail_when_video_is_recording():
    """45s of retreat, not 2s of the horn firing - and one tail, never both.

    The tails are alternatives, not cumulative: EVENT_VIDEO_RETREAT_TAIL_S
    was chosen to cover the whole retreat, so adding the 2s burst tail on
    top would just be an unexplained 47s. Which tail the loop reaches for
    is a branch, and constants cannot catch a branch taken the wrong way,
    so the sleep itself is recorded - with two distinct sub-millisecond
    values standing in for 45s and 2s so the suite stays fast.
    """
    slept = []
    original_sleep = time.sleep

    def _record_sleep(seconds):
        slept.append(seconds)
        original_sleep(0)

    def _run(**extra):
        reflex_loop.time.sleep = _record_sleep
        try:
            reflex_loop.handle_footfall_event(
                1,
                0.9,
                sta_lta_ratio=6.0,
                feature_vector=[0.0] * 8,
                safe_mode=False,
                capture_post_fire_tail_s=0.001,
                video_retreat_tail_s=0.002,
                vision_watch_base_s=0.0,
                vision_watch_extended_s=0.0,
                vision_watch_poll_interval_s=0.0,
                drive_horn=_FakeDriveHorn(),
                drive_led=_FakeDriveLed(),
                pulse_ir=_FakePulseIr(),
                is_night=lambda frames: True,
                camera=_FakeCamera(),
                detect_vision=_FakeVisionDetect(),
                save_frames=_FakeSaveFrames(),
                experience=ExperienceStore(IN_MEMORY_PATH),
                bandit_params=DETERMINISTIC_PARAMS,
                **extra,
            )
        finally:
            reflex_loop.time.sleep = original_sleep
        return list(slept)

    with_video = _run(event_video=_FakeEventVideo())
    slept.clear()
    without_video = _run()

    assert with_video == [0.002], "recording must use the retreat tail, not the burst tail"
    assert without_video == [0.001], "the burst tail must be unchanged when video is off"


def test_the_jpeg_burst_is_still_saved_alongside_the_video():
    """Video adds a record; it does not replace the one that has run on hardware.

    The JPEG burst is the evidence path that has actually been exercised on
    this board. Until the GStreamer chain has been run on the real
    hardware, dropping the burst in favour of the clip would trade a
    working path for an unverified one.
    """
    save_frames = _FakeSaveFrames()
    video = _FakeEventVideo()

    outcome, _, _ = _fire(probability=0.9, save_frames=save_frames, event_video=video)

    assert len(save_frames.calls) == 1
    assert len(video.committed) == 1
    assert outcome.capture_frame_count > 0


def test_the_burst_and_the_clip_carry_the_same_event_tag():
    """Two records of one event must be findable together in the capture dir.

    Both names come from the same CaptureEventTag, so they sort adjacent -
    which is how anyone reviewing an incident in the field actually
    matches a clip to its stills.
    """
    save_frames = _FakeSaveFrames()
    video = _FakeEventVideo()

    _fire(probability=0.9, save_frames=save_frames, event_video=video)

    burst_tag = save_frames.calls[0][1]
    assert video.committed[0] == burst_tag


def test_no_event_video_leaves_the_loop_exactly_as_it_was():
    """The default path must be untouched by ADR 0020.

    EVENT_VIDEO_ENABLED ships False, so this is what runs in the field
    today. If the video wiring ever leaked into it, the flag would stop
    being a real off switch.
    """
    outcome, _, log = _fire(probability=0.9)

    assert outcome.video_path is None
    assert not any(entry.startswith("video.") for entry in log)


# ---------------------------------------------------------------------------
# ADR 0022 - the bounded vision watch window and the vision-gated deterrent
# ---------------------------------------------------------------------------


class _ScriptedVisionDetect:
    """A detector whose answer changes from one poll to the next.

    _FakeVisionDetect returns the same thing forever, which cannot express
    the case ADR 0022 exists for: the frame is empty when the geophone
    fires and the animal walks into it several seconds later. The script is
    indexed by call, and its last entry repeats once exhausted so a test
    only has to describe the interesting prefix.

    Args:
        script: Per-call results. Two shapes for a non-exception entry,
            chosen by what most tests need to say: a flat list of
            Detections (e.g. `[BOAR]`) is broadcast to every frame in that
            call - implements VisionDetectFn's list[list[Detection]] shape
            without every existing script needing to know frame counts,
            and is indistinguishable from "this label was on every frame"
            to any per-label burst gate. A list of lists (e.g.
            `[[BOAR], [], [BOAR]]`) is passed straight through, one entry
            per frame, for the tests that need to plant a label on only
            some of a burst's frames - the within-burst majority gate
            cannot be exercised any other way. An Exception instance is
            raised instead of either.
    """

    def __init__(self, script: list):
        self._script = list(script)
        self.calls = 0

    def __call__(self, images):
        self.calls += 1
        item = self._script[min(self.calls - 1, len(self._script) - 1)]
        if isinstance(item, Exception):
            raise item
        if item and isinstance(item[0], list):
            return item
        return [list(item) for _ in images]


class _Clock:
    """A monotonic clock that only moves when the code under test sleeps.

    Lets a 45-second watch window run to completion in microseconds and
    makes the pacing assertions exact rather than timing-dependent. Polls
    themselves take zero time, which is the useful simplification: any
    elapsed time in a watch is then attributable to the sleeps.
    """

    def __init__(self):
        self.t = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


def _watch(camera, detect, watch_s, **kw):
    """Run _watch_for_vision on a fake clock; returns (watch, clock)."""
    clock = _Clock()
    result = reflex_loop._watch_for_vision(
        camera,
        detect,
        trigger_monotonic=0.0,
        watch_s=watch_s,
        poll_interval_s=kw.pop("poll_interval_s", 1.0),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        **kw,
    )
    return result, clock


# --- _watch_length_s --------------------------------------------------------


def test_an_ordinary_trigger_gets_only_the_base_window():
    """No repeat and no standalone seismic alert is the wind-and-cattle case.

    It is also the overwhelming majority of triggers, so it is the one that
    has to stay cheap - a long camera window on every geophone twitch is
    exactly the always-on power draw ADR 0020 refused.
    """
    assert reflex_loop._watch_length_s(
        repeat_count=0, seismic_alone_alerts=False, base_s=8.0, extended_s=45.0
    ) == 8.0


def test_a_repeat_inside_the_habituation_window_earns_the_long_look():
    """A repeat is this device's only signal that the event is still happening.

    It is the same evidence escalation_floor() already trusts to raise the
    deterrence tier, so trusting it to buy more camera time is consistent
    rather than a new assumption.
    """
    assert reflex_loop._watch_length_s(
        repeat_count=1, seismic_alone_alerts=False, base_s=8.0, extended_s=45.0
    ) == 45.0


def test_seismic_that_would_alert_alone_earns_the_long_look():
    """If the event is firing regardless, the only question left is when.

    Firing with the animal in frame is both better deterrence and the only
    way the event produces footage, so this trigger buys the long window.
    """
    assert reflex_loop._watch_length_s(
        repeat_count=0, seismic_alone_alerts=True, base_s=8.0, extended_s=45.0
    ) == 45.0


def test_the_extended_window_can_never_be_shorter_than_the_base():
    """A misconfiguration must not make a stronger trigger look for less time.

    Nothing validates these two constants against each other at import, so
    the guard lives here rather than in a comment nobody executes.
    """
    assert reflex_loop._watch_length_s(
        repeat_count=5, seismic_alone_alerts=True, base_s=8.0, extended_s=2.0
    ) == 8.0


def test_a_trigger_with_no_geophone_at_all_earns_the_long_look():
    """An absent sensor is not a sensor that said no.

    seismic_alone_alerts is structurally always False with no geophone in
    the picture at all - there is no seismic evidence to alert on - which
    is a different thing from a real reading that came back weak. There is
    no false-positive-rate argument for economizing the watch against a
    sensor that was never asked, so a trigger with no geophone behind it
    earns the same long look a strong geophone reading would.

    Before this parameter existed such a trigger took the *short* window,
    which is backwards: it is the case with the least corroboration and so
    the most to gain from looking longer.
    """
    assert (
        reflex_loop._watch_length_s(
            repeat_count=0,
            seismic_alone_alerts=False,
            seismic_available=False,
            base_s=8.0,
            extended_s=45.0,
        )
        == 45.0
    )


def test_seismic_available_defaults_true_so_the_field_path_is_unaffected():
    """Every existing caller omits seismic_available; behaviour must not move.

    A real geophone notify always has a reading behind it, so this default
    keeps the field path exactly what it was before this parameter
    existed. Asserted rather than assumed because the whole value of a
    defaulted parameter is that no existing call site had to be touched -
    which also means no existing call site would notice if the default
    were wrong.
    """
    assert (
        reflex_loop._watch_length_s(
            repeat_count=0, seismic_alone_alerts=False, base_s=8.0, extended_s=45.0
        )
        == 8.0
    )


# --- _watch_for_vision ------------------------------------------------------


def test_a_zero_length_window_runs_exactly_one_poll():
    """watch_s=0.0 must reproduce the single burst this replaced, exactly.

    This is the escape hatch promised in services/config.py - set
    VISION_WATCH_BASE_S to 0.0 and the loop behaves as it did before ADR
    0022 - and it is what keeps most of this file's tests running in
    milliseconds. If the watch ever skipped its poll instead, vision would
    silently stop running at all.
    """
    camera = _FakeCamera()
    detect = _FakeVisionDetect()

    watch, clock = _watch(camera, detect, 0.0)

    assert watch.polls == 1
    assert detect.calls == [detect.calls[0]]
    assert clock.sleeps == []
    assert watch.confirmed_on_poll is None


def test_the_watch_keeps_polling_until_the_window_closes():
    """An empty frame is not an answer - it is the question restated.

    The geophone reaches 140m and the camera does not, so at the trigger the
    animal is usually outside the frame. Polling on is the entire point.
    """
    camera = _FakeCamera()
    detect = _FakeVisionDetect()

    watch, clock = _watch(camera, detect, 5.0, poll_interval_s=1.0)

    assert watch.polls == 6
    assert clock.sleeps == [1.0] * 5
    assert watch.elapsed_s == pytest.approx(5.0)


def test_a_confirmation_on_a_later_poll_ends_the_watch_immediately():
    """The moment the animal is in frame is the moment to fire.

    Sleeping out the rest of a 45s window after confirming would put the
    horn off well after the elephant had walked past, which is the failure
    this whole feature exists to prevent.
    """
    camera = _FakeCamera()
    detect = _ScriptedVisionDetect([[], [], [ELEPHANT], []])

    watch, clock = _watch(camera, detect, 45.0, poll_interval_s=1.0)

    assert watch.polls == 3
    assert watch.confirmed_on_poll == 3
    assert watch.check.confirmed is True
    assert watch.elapsed_s == pytest.approx(2.0)
    assert len(clock.sleeps) == 2


def test_a_boar_neither_confirms_nor_ends_the_watch():
    """Boar is real signal for a different question, and must not stop the look.

    Under the default configuration a boar cannot fire the horn; if it also
    ended the watch, an elephant arriving behind it would never be seen.
    """
    camera = _FakeCamera()
    detect = _ScriptedVisionDetect([[BOAR], [BOAR], [ELEPHANT]])

    watch, _ = _watch(camera, detect, 45.0, poll_interval_s=1.0)

    assert watch.polls == 3
    assert watch.confirmed_on_poll == 3
    assert "Boar" in watch.species
    assert "Elephant" in watch.species


def test_the_watch_keeps_the_first_burst_and_the_confirming_burst_only():
    """Two bursts are used; holding the rest would be hundreds of megabytes.

    A 45s watch at one poll per second is over a hundred 720p frames. The
    first burst dates the event and feeds the night decision, the confirming
    burst is the evidence - nothing in between is ever read.
    """
    camera = _FakeCamera(frame_count=3)
    detect = _ScriptedVisionDetect([[], [], [ELEPHANT]])

    watch, _ = _watch(camera, detect, 45.0)

    assert len(watch.frames) == 6
    # Identity, not value: two bursts of image=None frames can compare equal
    # if the clock did not tick between them, and the claim here is that both
    # bursts are present, not that they differ.
    assert len({id(f) for f in watch.frames}) == 6


def test_a_first_poll_confirmation_does_not_duplicate_its_own_frames():
    """The confirming burst *is* the first burst here; it must be kept once.

    This is the case that hid a real defect: the frames are compared to
    decide what to keep, and a value comparison on a Frame whose .image is
    a numpy array raises rather than returning a bool.
    """
    camera = _FakeCamera(frame_count=3)
    detect = _FakeVisionDetect([ELEPHANT])

    watch, _ = _watch(camera, detect, 45.0)

    assert watch.polls == 1
    assert len(watch.frames) == 3


def test_frames_are_compared_by_identity_not_equality():
    """A Frame carrying a real ndarray must not be value-compared.

    perception.camera.Frame is a frozen dataclass whose .image is a numpy
    array in production, so `f in frames` runs an elementwise compare and
    then calls bool() on the result - a ValueError raised at the exact
    instant vision confirms an elephant on a later poll. A fake image that
    raises on __eq__ reproduces that without depending on numpy.
    """

    class _Unequal:
        def __eq__(self, other):
            raise AssertionError("Frame.image must never be compared by value")

        __hash__ = None

    class _UnequalCamera(_FakeCamera):
        def capture_burst(self, count, interval_s):
            self.call_log.append("camera.capture_burst")
            return [Frame(image=_Unequal(), index=i, timestamp_s=0.0) for i in range(3)]

    detect = _ScriptedVisionDetect([[], [ELEPHANT]])

    watch, _ = _watch(_UnequalCamera(), detect, 45.0)

    assert watch.confirmed_on_poll == 2
    assert len(watch.frames) == 6


def test_an_unconfirmed_watch_returns_only_the_first_burst():
    """Nothing was confirmed, so there is no second burst worth carrying."""
    camera = _FakeCamera(frame_count=3)
    detect = _FakeVisionDetect()

    watch, _ = _watch(camera, detect, 3.0)

    assert watch.confirmed_on_poll is None
    assert len(watch.frames) == 3


def test_an_available_reading_beats_the_unavailable_one_it_started_with():
    """"Looked and saw nothing" is evidence; "could not look" is an outage.

    The distinction is what ADR 0022 Decision B's whole safety argument
    turns on, so the watch must not report a working camera as a failed one
    just because the last poll happened to come back empty.
    """
    camera = _FakeCamera()
    detect = _FakeVisionDetect()

    watch, _ = _watch(camera, detect, 2.0)

    assert watch.reading_available is True
    assert watch.check.confirmed is False


def test_the_watch_abandons_itself_after_repeated_empty_polls():
    """A camera that has stopped delivering must not hold the actuators.

    Waiting out a 45s window on a dead camera would delay the deterrent for
    no possible gain - there is nothing coming.
    """
    camera = _FakeCamera(frame_count=0)
    detect = _FakeVisionDetect()

    watch, clock = _watch(camera, detect, 45.0, max_empty_polls=3)

    assert watch.polls == 3
    assert watch.reading_available is False
    assert clock.t < 45.0


def test_one_empty_poll_does_not_end_the_watch():
    """A single dropped burst is a hiccup, not an outage."""
    camera = _FakeCamera(frame_count=0)
    detect = _FakeVisionDetect()

    watch, _ = _watch(camera, detect, 45.0, max_empty_polls=5)

    assert watch.polls == 5


def test_a_detector_failure_inside_the_watch_never_raises():
    """A perception failure must degrade the event, never crash it."""
    camera = _FakeCamera()
    detect = _ScriptedVisionDetect([DetectionError("inference server down")])

    watch, _ = _watch(camera, detect, 2.0)

    assert watch.reading_available is False
    assert watch.check.confirmed is False


def test_the_watch_never_sleeps_past_its_own_deadline():
    """The window is a budget the loop must not overrun.

    An overrun here is an actuator delay in the field, and the whole
    justification for delaying actuators at all is that the delay is
    bounded by ADR 0008's worst-case lead time.
    """
    camera = _FakeCamera()
    detect = _FakeVisionDetect()

    _, clock = _watch(camera, detect, 2.5, poll_interval_s=1.0)

    assert clock.t <= 2.5
    assert sum(clock.sleeps) == pytest.approx(2.5)


# --- vision-watch illumination (D11) ----------------------------------------
#
# IR is a camera light, not a deterrent. It fires here, inside the poll
# loop, on the night read and before any tier has been chosen - see
# _watch_for_vision()'s own Illumination note for why each of the three
# orderings below is the way it is. Driven against the function directly on
# the fake clock, because the properties worth pinning are about pacing
# across a 45s window and nothing handler-level can observe them.


class _LoggingCamera(_FakeCamera):
    """_FakeCamera that also records lock_night_exposure() in the shared log.

    The base fake deliberately keeps the lock off the call_log so it does
    not shift the log[n] indices the deterrence-ordering tests assert on.
    Here the lock's position relative to the first pulse is the entire
    claim, so this one subclass opts back in.
    """

    def lock_night_exposure(self):
        self.call_log.append("camera.lock_night_exposure")
        return super().lock_night_exposure()


def _lit_watch(watch_s, *, is_night=None, pulse_ir=None, camera=None, detect=None, **kw):
    """_watch() with illumination wired up; returns (watch, clock, pulse_ir, camera)."""
    pulse_ir = pulse_ir if pulse_ir is not None else _FakePulseIr()
    camera = camera if camera is not None else _FakeCamera()
    is_night = is_night if is_night is not None else (lambda frames: True)
    watch, clock = _watch(
        camera,
        detect if detect is not None else _FakeVisionDetect(),
        watch_s,
        pulse_ir=pulse_ir,
        is_night=is_night,
        **kw,
    )
    return watch, clock, pulse_ir, camera


def test_a_daylight_watch_never_illuminates():
    """The IR-cut filter is in, so every pulse would be spent on nothing.

    The IMX462 puts its IR-cut filter in front of the sensor in daylight;
    near-IR never reaches a pixel. Firing anyway would spend the MCU's duty
    budget and the battery once every few seconds for up to 45s per event,
    and buy no photons at all.
    """
    watch, _, pulse_ir, camera = _lit_watch(20.0, is_night=lambda frames: False)

    assert watch.polls == 21
    assert pulse_ir.calls == []
    assert watch.ir_pulses == 0
    assert watch.ir_ack is None
    assert camera.lock_night_exposure_calls == 0


def test_a_night_watch_illuminates_from_the_poll_after_the_night_read():
    """The first poll is dark, and every lit poll after it asks for the same pulse.

    Day and night are read off captured frames, so a frame has to exist
    before the question can be answered - poll one pays for that and no
    poll after it does. An unlit night frame is still enough to answer it:
    frames_are_night() measures colour saturation, which has already
    collapsed once the filter is out, however dark the scene.
    """
    watch, _, pulse_ir, _ = _lit_watch(20.0)

    assert watch.polls == 21
    assert watch.ir_pulses == len(pulse_ir.calls) > 0
    # The same request every time: the MPU paces the illuminator, it never
    # escalates it. The MCU clamps the length regardless (IR_PULSE_MAX_MS).
    assert set(pulse_ir.calls) == {
        (services_config.SCHEMA_VERSION, services_config.IR_WATCH_PULSE_MS)
    }
    assert watch.ir_ack is True


def test_the_night_question_is_asked_once_for_the_whole_watch():
    """Re-reading per poll would let one unmeasurable burst go dark mid-watch.

    A 45s window does not straddle dusk in any way that matters, and from
    the second poll on the scene is partly lit by the node itself - so a
    per-poll read would be reading the node's own illumination back and
    could talk itself out of continuing.
    """
    asked = []

    def _once(frames):
        asked.append(len(frames))
        return True

    watch, _, _, _ = _lit_watch(20.0, is_night=_once)

    assert len(asked) == 1
    assert asked[0] == services_config.VISION_CHECK_FRAME_COUNT
    assert watch.ir_pulses > 0


def test_exposure_is_locked_before_the_first_lit_burst_not_after_it():
    """Finding 4: auto-exposure hunting against an IR pulse is the false-positive mode.

    docs/qa/night-ir-led-characterisation.md Finding 4 traced every spurious
    Boar box in the overnight soak to auto-exposure chasing the illuminator.
    The lock is the fix, and it is only a fix if it lands first - a watch
    that lit frames before locking would reintroduce that mode on every
    night event, where it previously needed tier 2.
    """
    log = []
    camera = _LoggingCamera(call_log=log)
    watch, _, _, _ = _lit_watch(20.0, camera=camera, pulse_ir=_FakePulseIr(call_log=log))

    assert camera.lock_night_exposure_calls == 1
    assert "pulse_ir" in log
    assert log.index("camera.lock_night_exposure") < log.index("pulse_ir")
    # And after the burst it read night from, not before - there is nothing
    # to read day/night off until one poll has run.
    assert log.index("camera.capture_burst") < log.index("camera.lock_night_exposure")
    assert watch.ir_pulses > 0


def test_pulses_are_paced_to_the_duty_budget_not_to_the_poll_rate():
    """One pulse per poll would ask for 45 in a long watch and be refused for most.

    The watch polls every second; the MCU admits a pulse every
    IR_MIN_INTERVAL_MS. Pacing on the MPU side means the common case does
    not spend a Bridge round-trip to be told no, and a normal night does
    not fill the log with refusals that are really the budget working.

    Asserted as exact pulse times on the fake clock rather than as a count,
    because a count alone passes against an implementation that fires the
    right number of pulses back to back at the start of the window.
    """
    clock = _Clock()
    fired_at = []

    def _pulse(schema_version, duration_ms):
        fired_at.append(clock.t)
        return True

    watch = reflex_loop._watch_for_vision(
        _FakeCamera(),
        _FakeVisionDetect(),
        trigger_monotonic=0.0,
        watch_s=20.0,
        poll_interval_s=1.0,
        pulse_ir=_pulse,
        is_night=lambda frames: True,
        ir_min_interval_s=5.0,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    # Night is established on poll 1 (t=0), so the first pulse is poll 2
    # (t=1.0) and one every 5s of watch time after that.
    assert watch.polls == 21
    assert fired_at == [1.0, 6.0, 11.0, 16.0]
    assert watch.ir_pulses == 4


def test_a_different_duty_budget_produces_proportionally_different_pacing():
    """The interval is read, not hardcoded against the poll loop."""
    tight, _, tight_ir, _ = _lit_watch(20.0, poll_interval_s=1.0, ir_min_interval_s=2.0)
    loose, _, loose_ir, _ = _lit_watch(20.0, poll_interval_s=1.0, ir_min_interval_s=10.0)

    assert tight.ir_pulses == len(tight_ir.calls) == 10
    assert loose.ir_pulses == len(loose_ir.calls) == 2


def test_illumination_does_not_lengthen_the_watch():
    """A lit watch and a dark one must close on the same deadline.

    The pulse runs on its own thread, concurrent with the capture it
    illuminates, and is joined inside the same poll. If it ever cost the
    loop wall-clock time, a 45s window would quietly become longer than the
    one _watch_length_s() granted, and the deterrence sequence would fire
    that much later into an encounter.
    """
    _, dark_clock, _, _ = _lit_watch(20.0, is_night=lambda frames: False)
    lit, lit_clock, pulse_ir, _ = _lit_watch(20.0)

    assert pulse_ir.calls, "the lit run must actually have illuminated"
    assert lit_clock.sleeps == dark_clock.sleeps
    assert lit.elapsed_s == pytest.approx(20.0)


def test_a_refused_pulse_degrades_to_an_unlit_poll():
    """The MCU saying no is the duty budget working, not a failed event.

    pulse_ir returns False when the MCU's own IR_MIN_INTERVAL_MS or thermal
    budget declines the request. The watch must keep polling, keep asking on
    schedule, and report the refusal rather than treat it as an error.
    """
    pulse_ir = _FakePulseIr(ack=False)
    watch, _, _, _ = _lit_watch(20.0, pulse_ir=pulse_ir)

    assert watch.polls == 21
    assert watch.ir_pulses == len(pulse_ir.calls) == 4
    assert watch.ir_ack is False
    assert watch.check is not None


def test_a_raising_pulse_ir_is_caught_on_its_own_thread_and_logged(caplog):
    """A Bridge fault on the illuminator costs light, never the encounter.

    The surviving-the-watch half of this is free and worth being honest
    about: the pulse runs on its own thread, so an escaping exception
    could not fail the watch even if nothing caught it. A mutation that
    deletes the try/except passes every assertion about polls and acks.

    What the catch actually buys is the two things asserted here. The
    failure is logged *as part of this event*, where someone reviewing why
    a night clip is dark will find it - rather than arriving as a bare
    threading.excepthook traceback on stderr with no event context. And it
    does not surface as an unhandled thread exception, which pytest and
    any supervisor treat as a fault in its own right.
    """

    def _boom(schema_version, duration_ms):
        raise RuntimeError("bridge transport died")

    with caplog.at_level("ERROR"):
        watch, _, _, _ = _lit_watch(20.0, pulse_ir=_boom)

    assert watch.polls == 21
    assert watch.ir_pulses == 4
    # Attempted, but nothing ever acked - which is exactly what someone
    # reviewing the footage afterwards needs to know.
    assert watch.ir_ack is None
    raised = [r for r in caplog.records if "pulse_ir raised" in r.message]
    assert len(raised) == 4, "every failed pulse must be logged against this event"
    assert all(r.exc_info is not None for r in raised), (
        "logged without the traceback - a bare message does not say which "
        "Bridge call broke or why"
    )


def test_a_raising_night_read_leaves_the_watch_unlit():
    """A deliberate change of behaviour from the deterrence path, and why.

    The old tier-gated pulse forced night=True when is_night() raised, on
    the "a perception failure never blocks an actuator" rule. That was
    defensible there: one pulse, at the moment of a decision already made.

    Here it would be a pulse every few seconds for up to 45s, on every
    event, with no idea whether the IR-cut filter is even out. Unlit is the
    cheap answer and it costs exactly what a daylight watch costs. The horn
    and the LED are untouched by this - they are not on this path at all any
    more, which is the point of the move.
    """

    def _boom(frames):
        raise RuntimeError("saturation math blew up")

    watch, _, pulse_ir, camera = _lit_watch(20.0, is_night=_boom)

    assert watch.polls == 21
    assert pulse_ir.calls == []
    assert watch.ir_pulses == 0
    assert camera.lock_night_exposure_calls == 0


def test_an_unmeasurable_scene_is_asked_again_rather_than_written_off():
    """None is "no answer yet", not "no". It must not latch.

    frames_are_night() returns None for a burst it cannot measure. A watch
    that read the first such poll as daylight would stay dark for the rest
    of the window over one bad burst - and a burst is most likely to be
    unmeasurable exactly when the scene is darkest.
    """
    answers = [None, None, True]

    def _late(frames):
        return answers.pop(0) if answers else True

    watch, _, pulse_ir, _ = _lit_watch(20.0, is_night=_late)

    # Asked on polls 1, 2 and 3; night is established on poll 3 (t=2.0), so
    # the first pulse is poll 4 (t=3.0) and they run every 5s from there.
    assert answers == []
    assert watch.ir_pulses == len(pulse_ir.calls) == 4


def test_a_raising_exposure_lock_still_illuminates():
    """An unlocked capture is worse footage; an unlit one is no footage."""
    camera = _FakeCamera()

    def _boom():
        camera.lock_night_exposure_calls += 1
        raise RuntimeError("v4l2 control write failed")

    camera.lock_night_exposure = _boom
    watch, _, pulse_ir, _ = _lit_watch(20.0, camera=camera)

    assert camera.lock_night_exposure_calls == 1
    assert watch.ir_pulses == len(pulse_ir.calls) == 4


def test_a_watch_with_no_illuminator_behaves_exactly_as_it_did_before():
    """Both injection points default to None, and that path must be the old one.

    bench/demo_replay.py and every caller without an MCU rely on this.
    """
    camera = _FakeCamera()
    watch, _ = _watch(camera, _FakeVisionDetect(), 20.0, poll_interval_s=1.0)

    assert watch.polls == 21
    assert watch.ir_pulses == 0
    assert watch.ir_ack is None
    assert camera.lock_night_exposure_calls == 0


def test_a_night_reader_without_an_illuminator_lights_and_locks_nothing():
    """is_night alone is not illumination - pulse_ir is the half that lights anything.

    Asserted because the lock is free to run on the night read alone, and
    locking exposure for an unlit night scene is strictly worse than leaving
    it: there is no pulse coming for it to stop auto-exposure chasing.
    """
    camera = _FakeCamera()
    watch, _ = _watch(
        camera,
        _FakeVisionDetect(),
        20.0,
        poll_interval_s=1.0,
        is_night=lambda frames: True,
    )

    assert watch.ir_pulses == 0
    assert watch.ir_ack is None
    assert camera.lock_night_exposure_calls == 0


def test_what_was_illuminated_is_reported_on_the_confirming_exit_too():
    """The early return is the exit the field actually takes, so it must report too.

    A confirmation ends the watch immediately. If ir_pulses and ir_ack were
    only filled in on the window-closed path, every event that actually saw
    something - the ones whose footage matters - would lose the record of
    whether its frames were lit.
    """
    pulse_ir = _FakePulseIr()
    # Nothing for seven polls, then an elephant, so the watch exits early
    # and well after illumination has started.
    detect = _ScriptedVisionDetect([[], [], [], [], [], [], [], [ELEPHANT]])

    watch, _, _, _ = _lit_watch(
        20.0, poll_interval_s=1.0, pulse_ir=pulse_ir, detect=detect
    )

    assert watch.confirmed_on_poll == 8
    assert watch.polls == 8
    assert watch.ir_pulses == len(pulse_ir.calls) == 2
    assert watch.ir_ack is True


# --- VISION_SPECIES_CONSECUTIVE_POLLS debounce ------------------------------
#
# services/config.py's VISION_SPECIES_CONSECUTIVE_POLLS gates entry into
# watch.species per label, not confirmation - see that constant's own
# comment. Boar is 2 there; every label not listed, Elephant included,
# defaults to 1 (see _required_consecutive_polls()). These tests exercise
# the streak counters directly against the real configured value rather
# than monkeypatching a smaller one, because the whole point is proving
# what the shipped constant does.


@FOX_GATE_RELAXATION
def test_an_isolated_boar_poll_never_enters_species():
    """One spurious Boar box must not be enough - that is the entire fix.

    The 30 Aug 2-hour live run measured a 31.53% per-frame Boar
    false-positive rate; a single poll admitting Boar into species would
    carry that noise straight through to _worth_filming.
    """
    camera = _FakeCamera()
    detect = _ScriptedVisionDetect([[BOAR], [], []])

    watch, _ = _watch(camera, detect, 45.0, poll_interval_s=1.0)

    assert "Boar" not in watch.species


@FOX_GATE_RELAXATION
def test_two_consecutive_boar_polls_enter_species_from_the_second():
    """The streak has to actually reach 2, not merely accumulate 2 sightings.

    Distinguishes a real consecutive-poll gate from a simple seen-twice
    counter, which alternating or sparse sightings would also satisfy.
    """
    camera = _FakeCamera()

    watch_after_one, _ = _watch(camera, _ScriptedVisionDetect([[BOAR]]), 0.0)
    assert watch_after_one.polls == 1
    assert "Boar" not in watch_after_one.species

    watch, _ = _watch(
        camera, _ScriptedVisionDetect([[BOAR], [BOAR]]), 1.0, poll_interval_s=1.0
    )
    assert watch.polls == 2
    assert "Boar" in watch.species


@FOX_GATE_RELAXATION
def test_an_alternating_boar_streak_resets_and_never_admits():
    """A gap poll must zero the streak, not merely pause it.

    Boar / empty / Boar / empty never presents two polls in a row, so under
    a true consecutive-poll gate it must never qualify - only a (buggy)
    seen-twice-anywhere counter would let it through.
    """
    camera = _FakeCamera()
    detect = _ScriptedVisionDetect([[BOAR], [], [BOAR], [], [BOAR]])

    # watch_s=4.0 at a 1.0s poll interval runs exactly 5 polls - one per
    # scripted entry, so the script's own repeat-last-entry behaviour never
    # comes into play.
    watch, _ = _watch(camera, detect, 4.0, poll_interval_s=1.0)

    assert watch.polls == 5
    assert "Boar" not in watch.species


def test_a_sustained_boar_streak_is_admitted_exactly_once():
    """Once qualified, a label stays in species - it does not re-arm each poll.

    seen_species is a union over the whole window; nothing about a longer
    streak should change its membership, only how soon it was added.
    """
    camera = _FakeCamera()
    detect = _ScriptedVisionDetect([[BOAR], [BOAR], [BOAR], [BOAR]])

    # watch_s=3.0 at a 1.0s poll interval runs exactly 4 polls - one per
    # scripted entry.
    watch, _ = _watch(camera, detect, 3.0, poll_interval_s=1.0)

    assert watch.polls == 4
    assert "Boar" in watch.species


def test_elephant_still_enters_species_on_a_single_poll():
    """Elephant's default streak requirement is 1 - this debounce must cost it nothing.

    The regression guard for the whole feature: Boar getting a streak gate
    must not accidentally change Elephant's admission latency or
    confirm-and-exit semantics.
    """
    camera = _FakeCamera()
    detect = _ScriptedVisionDetect([[ELEPHANT]])

    watch, _ = _watch(camera, detect, 45.0, poll_interval_s=1.0)

    assert watch.polls == 1
    assert watch.confirmed_on_poll == 1
    assert "Elephant" in watch.species


def test_boar_and_elephant_streaks_are_tracked_independently():
    """Two labels in the same poll must not share or interfere with one counter.

    Elephant confirms and ends the watch on poll 2 here regardless of
    Boar's progress, but Boar's own streak must still have advanced
    correctly on both polls it appeared in.
    """
    camera = _FakeCamera()
    detect = _ScriptedVisionDetect([[BOAR], [BOAR, ELEPHANT]])

    watch, _ = _watch(camera, detect, 45.0, poll_interval_s=1.0)

    assert watch.polls == 2
    assert watch.confirmed_on_poll == 2
    assert "Elephant" in watch.species
    assert "Boar" in watch.species


# --- VISION_SPECIES_BURST_MAJORITY_LABELS gate ------------------------------
#
# services/config.py's VISION_SPECIES_BURST_MAJORITY_LABELS gates
# _vision_check()'s within-one-burst aggregation, a different axis from the
# across-polls streak counters just above: this decides whether a label
# needs to appear on more than half of a single poll's frames, or just one,
# before it counts at all - for species membership *and* confirmation.
# Boar is listed there; every other label, Elephant included, defaults to
# the original one-frame-is-enough (OR) behaviour. Exercised directly
# against _vision_check() rather than through _watch_for_vision(), because
# _watch_for_vision() has no target_labels override yet (Workstream 3) and
# Boar is not in the default VISION_TARGET_LABELS - so confirmation on Boar
# can only be observed by calling _vision_check() with an explicit
# target_labels that includes it, the same way a future confirmation-path
# caller would.


def _frames(count: int) -> list[Frame]:
    return [Frame(image=None, index=i, timestamp_s=0.0) for i in range(count)]


@FOX_GATE_RELAXATION
def test_boar_on_a_minority_of_the_burst_is_excluded_from_species_and_confirmation():
    """One spurious Boar box in a 3-frame burst must not count for anything.

    This is the failure mode the majority gate exists to fix: under the old
    flat-OR aggregation this single box would have both entered `species`
    and, had Boar been a target label, confirmed the watch.
    """
    detect = _ScriptedVisionDetect([[[BOAR], [], []]])

    check = reflex_loop._vision_check(detect, _frames(3), target_labels=("Boar",))

    assert "Boar" not in check.species
    assert check.confirmed is False


def test_boar_on_a_majority_of_the_burst_is_admitted_and_confirms():
    """Two of three frames is a real majority - the label must count.

    Same burst size as the minority case above, only the count differs,
    isolating the gate's own threshold rather than anything about the
    frames themselves.
    """
    detect = _ScriptedVisionDetect([[[BOAR], [BOAR], []]])

    check = reflex_loop._vision_check(detect, _frames(3), target_labels=("Boar",))

    assert "Boar" in check.species
    assert check.confirmed is True


def test_elephant_on_a_minority_of_the_burst_still_counts():
    """Elephant is not in VISION_SPECIES_BURST_MAJORITY_LABELS - one frame is enough.

    The regression guard for the whole feature: scoping the majority gate
    to Boar must not cost Elephant any sensitivity, since a missed real
    elephant, not a false one, is the safety-relevant failure for this
    class. Byte-for-byte the pre-3-Sept-2026 flat-OR behaviour for
    Elephant specifically.
    """
    detect = _ScriptedVisionDetect([[[ELEPHANT], [], []]])

    check = reflex_loop._vision_check(detect, _frames(3), target_labels=("Elephant",))

    assert "Elephant" in check.species
    assert check.confirmed is True


@FOX_GATE_RELAXATION
def test_a_majority_rejected_boar_reading_contributes_no_positive_evidence():
    """A rejected poll must fall back to BASELINE_VISION, not the detector's own confidence.

    Carrying the raw confidence forward here would let a single spurious
    Boar frame push positive log-odds into fuse() even though nothing was
    confirmed - the same trap Workstream 3's confirmation-path design
    calls out for the across-polls debounce, on the within-burst axis.
    """
    detect = _ScriptedVisionDetect([[[BOAR], [], []]])

    check = reflex_loop._vision_check(detect, _frames(3), target_labels=("Boar",))

    assert check.reading.log_odds == pytest.approx(cognition_config.BASELINE_VISION)


# --- confirmation-path streak gate (target_labels) --------------------------
#
# Workstream 3: _vision_check()'s per-poll check.confirmed is not enough on
# its own once a majority-gated label (Boar) sits on target_labels - the
# confirming label must also have cleared its own across-polls
# VISION_SPECIES_CONSECUTIVE_POLLS streak, or a single spurious poll would
# exit the watch early and feed fuse() positive log-odds off one burst.
# Exercised through _watch_for_vision()'s target_labels override directly,
# since Boar is not in the default VISION_TARGET_LABELS.


@FOX_GATE_RELAXATION
def test_a_single_spurious_boar_poll_does_not_confirm_even_with_boar_targeted():
    """One majority-qualifying Boar poll must not confirm on its own.

    Boar's within-burst majority gate is satisfied here (2 of 3 frames) -
    this isolates the second, across-polls gate Workstream 3 adds: even a
    burst-majority Boar reading needs VISION_SPECIES_CONSECUTIVE_POLLS
    consecutive polls before the watch may confirm on it.
    """
    camera = _FakeCamera()
    detect = _ScriptedVisionDetect([[[BOAR], [BOAR], []]])

    watch, _ = _watch(camera, detect, 0.0, target_labels=("Boar",))

    assert watch.polls == 1
    assert watch.confirmed_on_poll is None
    assert watch.check.confirmed is False


@FOX_GATE_RELAXATION
def test_a_streak_rejected_boar_confirmation_downgrades_to_baseline():
    """The rejected poll must contribute BASELINE_VISION, not the raw confidence.

    Carrying the detector's own confidence through here would let one
    spurious Boar poll push positive log-odds into fuse() even though the
    watch never actually confirmed - exactly the bypass this gate exists to
    close.
    """
    camera = _FakeCamera()
    detect = _ScriptedVisionDetect([[[BOAR], [BOAR], []]])

    watch, _ = _watch(camera, detect, 0.0, target_labels=("Boar",))

    assert watch.check.reading.available is True
    assert watch.check.reading.log_odds == pytest.approx(cognition_config.BASELINE_VISION)


@FOX_GATE_RELAXATION
def test_two_consecutive_majority_boar_polls_confirm_on_the_second():
    """Once Boar's own streak is met, confirmation fires exactly like any other label.

    Same script as the species-debounce streak test above, but with Boar on
    target_labels this time, so this exercises the confirm-and-exit path
    itself rather than only species membership.
    """
    camera = _FakeCamera()
    detect = _ScriptedVisionDetect([[[BOAR], [BOAR], []]])

    watch, _ = _watch(camera, detect, 1.0, poll_interval_s=1.0, target_labels=("Boar",))

    assert watch.polls == 2
    assert watch.confirmed_on_poll == 2
    assert watch.check.confirmed is True


def test_elephant_still_confirms_on_the_first_poll_when_boar_is_also_targeted():
    """The regression guard: adding Boar to target_labels must cost Elephant nothing.

    Elephant's required streak is 1, so under the "both" scope it must
    still confirm and exit on the very first poll, exactly as it does
    under the elephant_only default.
    """
    camera = _FakeCamera()
    detect = _ScriptedVisionDetect([[ELEPHANT]])

    watch, _ = _watch(
        camera, detect, 45.0, poll_interval_s=1.0, target_labels=("Elephant", "Boar")
    )

    assert watch.polls == 1
    assert watch.confirmed_on_poll == 1
    assert watch.check.confirmed is True


# --- _vision_could_see ------------------------------------------------------


def _watch_of(*, available: bool, frames: int, species=()):
    """Build a VisionWatch directly, for the blindness-gate tests."""
    reading = reflex_loop.ModalityReading(Modality.VISION, 0.0, available=available)
    return reflex_loop.VisionWatch(
        check=reflex_loop.VisionCheck(reading, False, tuple(species)),
        frames=tuple(Frame(image=None, index=i, timestamp_s=0.0) for i in range(frames)),
        polls=1,
        elapsed_s=0.0,
        confirmed_on_poll=None,
        species=tuple(species),
    )


def test_a_failed_camera_or_detector_counts_as_blind():
    """available=False is an outage, and an outage is not an absence.

    Nothing on this board supervises the inference server, so a dead
    detector is a real and symptomless failure. Reading it as "no elephant
    there" would turn a silent outage into a silent loss of deterrence.
    """
    assert reflex_loop._vision_could_see(
        _watch_of(available=False, frames=3), lambda: False
    ) is False


def test_no_frames_at_all_counts_as_blind():
    """The camera never opened; there is nothing to have seen an elephant in."""
    assert reflex_loop._vision_could_see(
        _watch_of(available=True, frames=0), lambda: False
    ) is False


def test_night_without_illumination_counts_as_blind():
    """The single most important case, and the easiest one to get wrong.

    At night the camera works and returns dark frames, so vision reports
    "I looked, nothing there" about an elephant it physically cannot see.
    pulse_ir() fires only for tiers 2 and 3, after decide() has already run,
    so the illuminator is off during every night watch. Read as absence
    rather than blindness, a confirmation-gated deterrent would go silent
    from dusk to dawn - which is when almost all raiding happens.
    """
    assert reflex_loop._vision_could_see(
        _watch_of(available=True, frames=3), lambda: True
    ) is False


def test_an_unmeasurable_scene_counts_as_blind():
    """frames_are_night() returning None resolves toward keeping the horn live.

    The conservative direction differs between the two consumers of this
    answer, deliberately: the IR gate suppresses the pulse rather than waste
    it, and this gate assumes blindness rather than go quiet.
    """
    assert reflex_loop._vision_could_see(
        _watch_of(available=True, frames=3), lambda: None
    ) is False


def test_a_raising_night_check_counts_as_blind():
    """A bug in the night heuristic must not silence the deterrent."""

    def _boom():
        raise RuntimeError("saturation math blew up")

    assert reflex_loop._vision_could_see(_watch_of(available=True, frames=3), _boom) is False


def test_a_lit_daylight_scene_is_the_one_case_vision_could_see():
    """Camera worked, detector worked, scene was classifiable - and it saw nothing.

    This is the only combination that justifies holding the horn.
    """
    assert reflex_loop._vision_could_see(
        _watch_of(available=True, frames=3), lambda: False
    ) is True


def test_illumination_makes_a_night_scene_visible_again():
    """The seam the proactive-IR work lands on, asserted so it cannot rot."""
    assert reflex_loop._vision_could_see(
        _watch_of(available=True, frames=3), lambda: True, illuminated=True
    ) is True


# --- _worth_filming ---------------------------------------------------------


def test_a_target_species_is_always_worth_filming():
    """Whatever else is configured, the animal that fires the horn is filmed."""
    assert reflex_loop._worth_filming(_watch_of(available=True, frames=3, species=["Elephant"]))


def test_a_video_only_species_is_worth_filming_without_being_a_target(monkeypatch):
    """"Record boar, deter elephants" has to be a config change, not a code one.

    A boar event never confirms and never alerts, so the no-actuation exit
    is the only place its footage still exists. If the keep-gate asked only
    about confirmation, the file would be discarded exactly there.
    """
    monkeypatch.setattr(reflex_loop, "VISION_VIDEO_LABELS", ("Elephant", "Boar"))

    assert reflex_loop._worth_filming(_watch_of(available=True, frames=3, species=["Boar"]))


def test_a_boar_is_not_worth_filming_under_the_shipped_configuration():
    """The default is elephant-only, for both deterrence and disk."""
    assert reflex_loop.VISION_VIDEO_LABELS == ("Elephant",)
    assert not reflex_loop._worth_filming(_watch_of(available=True, frames=3, species=["Boar"]))


def test_an_empty_scene_is_not_worth_filming():
    """The common case, and the one that keeps the card from filling up."""
    assert not reflex_loop._worth_filming(_watch_of(available=True, frames=3))


# --- handler-level ----------------------------------------------------------


def test_an_elephant_found_on_a_later_poll_still_fires_the_deterrent():
    """The end-to-end case ADR 0022 was written for.

    The frame is empty when the geophone fires and the animal walks into it
    a few polls later. Before the watch, this event decided on seismic alone
    and the camera's "no elephant" was an answer about an empty frame.
    """
    detect = _ScriptedVisionDetect([[], [], [ELEPHANT]])

    outcome, kwargs, _ = _fire(
        0.9,
        detect_vision=detect,
        vision_watch_base_s=0.05,
        vision_watch_extended_s=0.05,
        vision_watch_poll_interval_s=0.0,
    )

    assert outcome.vision_confirmed is True
    assert outcome.vision_polls >= 3
    assert kwargs["drive_horn"].calls != []


def test_a_repeat_trigger_is_granted_the_extended_window():
    """The handler has to pass repeat_count into the length decision.

    Asserted through the outcome rather than by patching, because the wiring
    between record_trigger() and _watch_length_s() is the part that breaks.
    """
    experience = ExperienceStore(IN_MEMORY_PATH)
    first, _, _ = _fire(0.05, sta_lta_ratio=3.0, experience=experience)
    assert first.vision_watch_s == 0.0

    second, _, _ = _fire(
        0.05,
        sta_lta_ratio=3.0,
        experience=experience,
        detect_vision=_FakeVisionDetect([ELEPHANT]),
        vision_watch_base_s=0.0,
        vision_watch_extended_s=0.02,
        vision_watch_poll_interval_s=0.0,
    )

    assert second.repeat_count == 1
    assert second.vision_watch_s == 0.02
    experience.close()


def test_safe_mode_does_no_watching_at_all():
    """SAFE_MODE's contract is that the camera never runs, watch or no watch."""
    camera = _FakeCamera()
    detect = _FakeVisionDetect()

    outcome = reflex_loop.handle_footfall_event(
        1,
        0.9,
        sta_lta_ratio=6.0,
        feature_vector=[0.0] * 8,
        safe_mode=True,
        capture_post_fire_tail_s=0.0,
        video_retreat_tail_s=0.0,
        vision_watch_base_s=45.0,
        vision_watch_extended_s=45.0,
        camera=camera,
        detect_vision=detect,
        drive_horn=_FakeDriveHorn(),
        drive_led=_FakeDriveLed(),
        pulse_ir=_FakePulseIr(),
        is_night=lambda frames: True,
        save_frames=_FakeSaveFrames(),
        experience=ExperienceStore(IN_MEMORY_PATH),
        bandit_params=DETERMINISTIC_PARAMS,
    )

    assert outcome.vision_watch_s == 0.0
    assert detect.calls == []
    assert camera.call_log == []


def test_a_daylight_event_that_saw_nothing_holds_the_deterrent(caplog):
    """ADR 0022 Decision B, in the one situation where it should engage.

    The seismic evidence cleared the threshold on its own, the camera looked
    in good light across the whole window, and there was no elephant. Firing
    here spends the horn on an animal that is either not there or still deep
    in the forest - and cognition/bandit.py's habituation model says that is
    exactly what teaches an elephant to ignore it.
    """
    with caplog.at_level("INFO"):
        outcome, kwargs, _ = _fire(0.9, is_night=lambda frames: False)

    assert outcome.decision.alert is True
    assert outcome.suppressed_by_vision is True
    assert outcome.action is None
    assert kwargs["drive_horn"].calls == []
    assert kwargs["drive_led"].calls == []
    assert any("deterrent held" in r.message for r in caplog.records)


def test_a_blind_event_falls_back_to_the_seismic_decision_and_fires():
    """The safety valve. A dead camera must not become a dead deterrent."""
    outcome, kwargs, _ = _fire(
        0.9, camera=_FakeCamera(fail_open=True), is_night=lambda frames: False
    )

    assert outcome.suppressed_by_vision is False
    assert kwargs["drive_horn"].calls != []


def test_a_night_event_still_fires_on_seismic_alone():
    """Today this is every night event, and it is why the gate is survivable.

    The illuminator does not fire until after decide(), so the watch runs in
    the dark on every nocturnal trigger - which is nearly all of them. Until
    proactive illumination is decided, night falls back to seismic.
    """
    outcome, kwargs, _ = _fire(0.9, is_night=lambda frames: True)

    assert outcome.suppressed_by_vision is False
    assert kwargs["drive_horn"].calls != []


def test_the_confirmation_requirement_can_be_turned_off():
    """The pre-ADR-0022 behaviour has to remain one flag away.

    If the gate ever proves wrong in the field, reverting it must not need a
    code change and a reflash.
    """
    outcome, kwargs, _ = _fire(
        0.9, is_night=lambda frames: False, require_vision_confirmation=False
    )

    assert outcome.suppressed_by_vision is False
    assert kwargs["drive_horn"].calls != []


@TIER_FLOOR_OVERRIDE
def test_a_held_event_still_records_its_trigger_for_habituation():
    """Holding the horn must not erase the encounter.

    The trigger is recorded before the watch, so a suppressed event still
    counts. Otherwise an animal circling a node in daylight would reset the
    node's memory of it on every pass.

    What that count now buys is narrower than it was, and the two
    assertions below are the whole of ADR 0034's split. A held daylight
    event is by definition one the camera looked at and could not name, so
    it stays UNATTRIBUTED: it keeps feeding the node-level count that
    _watch_length_s() reads - look longer, which is cheap and always safe -
    and it deliberately does not walk any named species' escalation floor,
    because walking it would mean guessing that the thing the camera failed
    to see was an elephant. The elephant below therefore meets tier 1, not
    tier 2, and that is the designed answer rather than a lost repeat.
    """
    experience = ExperienceStore(IN_MEMORY_PATH)
    held, _, _ = _fire(0.9, experience=experience, is_night=lambda frames: False)
    assert held.suppressed_by_vision is True

    later, _, _ = _fire(
        0.9,
        experience=experience,
        detect_vision=_FakeVisionDetect([ELEPHANT]),
        is_night=lambda frames: False,
    )

    # The encounter was not erased: the node-level window still has it.
    assert later.repeat_count == 1
    # ... and it is not charged to the elephant, which nothing identified.
    assert later.species_repeat_count == 0
    assert later.action.tier is Tier.TIER_1
    experience.close()


# --- one event at a time -----------------------------------------------------


class _BlockingVisionDetect:
    """Holds an event open inside handle_footfall_event until released.

    The only way to test the mutex is to have two events genuinely
    overlap, and the only way to do that deterministically is to park one
    of them somewhere in the middle. The vision check is the right place:
    it is where a real event spends most of its time, and it is already an
    injected dependency, so nothing in the module under test has to change
    shape to be tested.
    """

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()

    def __call__(self, images):
        self.entered.set()
        assert self.release.wait(timeout=5.0), "test deadlock: never released"
        return [[] for _ in images]


def test_a_second_event_is_dropped_rather_than_queued():
    """Two readers on one /dev/video node, which is the failure this prevents.

    Asserts the drop is total, not partial: the second event records no
    trigger, opens no camera and fires nothing. A half-run event would be
    worse than either outcome - it would move the habituation window for
    an encounter the node never actually responded to.
    """
    blocker = _BlockingVisionDetect()
    experience = ExperienceStore(IN_MEMORY_PATH)
    first: list = []

    def run_first() -> None:
        outcome, _, _ = _fire(0.9, experience=experience, detect_vision=blocker)
        first.append(outcome)

    worker = threading.Thread(target=run_first)
    worker.start()
    try:
        assert blocker.entered.wait(timeout=5.0)

        log: list = []
        second, _, _ = _fire(0.9, call_log=log, experience=experience)
    finally:
        blocker.release.set()
        worker.join(timeout=5.0)

    assert not worker.is_alive()
    assert second is None
    assert log == []
    # One trigger in the store, not two: the dropped event left no trace.
    assert first[0] is not None
    assert first[0].repeat_count == 0
    assert experience.repeat_count(time.time() + 1.0, 600.0, "") == 1
    experience.close()


def test_the_slot_is_released_when_an_event_raises():
    """A node that drops every event after one failure is worse than one that crashes.

    handle_footfall_event() swallows actuator and camera faults by design,
    but not a store fault - and whatever escapes, the next event has to be
    able to run.
    """

    class _ExplodingStore:
        def record_trigger(self, event_ts_s, window_s):
            raise RuntimeError("disk gone")

    with pytest.raises(RuntimeError):
        _fire(0.9, experience=_ExplodingStore())

    assert not reflex_loop.EVENT_LOCK.locked()
    # ... and the next event really does run, rather than only looking free.
    outcome, _, _ = _fire(0.9)
    assert outcome is not None


# --- per-species attribution (ADR 0034) --------------------------------------
#
# The two counts a footfall event now carries are easy to confuse, so the
# tests below pin each one at the place it is read: repeat_count is the
# species-blind window _watch_length_s() consumes, species_repeat_count is
# the partitioned window escalation_floor() consumes.


@TIER_FLOOR_OVERRIDE
def test_a_night_of_foxes_does_not_hand_a_dawn_elephant_a_habituated_floor():
    """The regression ADR 0022 C and ADR 0023 D both named and declined to fix.

    A node that spent the night chasing foxes used to greet the morning's
    first elephant with a floor those foxes had walked up - full gain, on an
    animal that had never heard the horn here. Welfare aside, it also
    destroys the learning: the elephant's tier-1 and tier-2 cells never get
    a visit, so their values stay at their priors forever.

    Both counts are asserted, because only the pair proves the partition
    rather than a lost trigger: the node remembers all three crossings, and
    the elephant is charged for none of them.
    """
    experience = ExperienceStore(IN_MEMORY_PATH)
    scope = ("Elephant", "Fox")
    for _ in range(2):
        _fire(
            0.9,
            experience=experience,
            detect_vision=_FakeVisionDetect([FOX]),
            target_labels=scope,
        )

    dawn, _, _ = _fire(
        0.9,
        experience=experience,
        detect_vision=_FakeVisionDetect([ELEPHANT]),
        target_labels=scope,
    )

    assert dawn.species == "Elephant"
    # The node saw three animals cross; it has not forgotten two of them.
    assert dawn.repeat_count == 2
    # The elephant is new here, and is met as a new animal.
    assert dawn.species_repeat_count == 0
    assert dawn.action.tier is Tier.TIER_1
    experience.close()


@TIER_FLOOR_OVERRIDE
def test_the_same_species_twice_does_escalate():
    """The other half: partitioning must not quietly disable habituation.

    Without this, the test above passes just as well against a build that
    never escalates at all.
    """
    experience = ExperienceStore(IN_MEMORY_PATH)
    first, _, _ = _fire(0.9, experience=experience, detect_vision=_FakeVisionDetect([ELEPHANT]))
    second, _, _ = _fire(0.9, experience=experience, detect_vision=_FakeVisionDetect([ELEPHANT]))

    assert first.species_repeat_count == 0
    assert first.action.tier is Tier.TIER_1
    assert second.species_repeat_count == 1
    assert second.action.tier is Tier.TIER_2
    experience.close()


def test_a_fox_and_an_elephant_keep_separate_action_values():
    """The reward goes to the cell the attempt named, not to the node's one cell.

    `settle_pending()` is species-blind by design (ADR 0034: the proxy
    measures quiet, which no camera labels), but it credits the species
    stored on the attempt - so two species firing at the same node must
    leave two distinct learned cells rather than one shared one.
    """
    experience = ExperienceStore(IN_MEMORY_PATH)
    scope = ("Elephant", "Fox")
    # Two of each, because an attempt only acquires a value when the *next*
    # event settles it - one fire per species would leave both pending and
    # the assertions below would pass against a store that learned nothing.
    for seen in (FOX, FOX, ELEPHANT, ELEPHANT):
        _fire(
            0.9,
            experience=experience,
            detect_vision=_FakeVisionDetect([seen]),
            target_labels=scope,
        )

    assert experience.action_values("Fox")
    assert experience.action_values("Elephant")
    # And nothing landed in the unattributed partition, because every one
    # of these events was named before its attempt was opened.
    assert experience.action_values() == {}
    experience.close()


def test_an_unconfirmed_trigger_stays_in_the_unattributed_partition():
    """The default path, pinned so the partition cannot silently become a guess.

    A night event that fires on blindness alone never saw anything. Its
    attempt belongs to no species, and must be visible to a later
    unattributed event rather than being filed under whatever the node
    happens to be scoped to.
    """
    experience = ExperienceStore(IN_MEMORY_PATH)
    first, _, _ = _fire(0.9, experience=experience)
    # The second fire is what settles the first one's attempt, which is the
    # only way a value reaches the table at all.
    second, _, _ = _fire(0.9, experience=experience)

    assert first.species is None and second.species is None
    assert second.species_repeat_count == 1
    assert experience.action_values()
    assert experience.action_values("Elephant") == {}
    experience.close()


def test_an_event_that_never_selects_a_tier_reports_no_species_count():
    """None, not 0: the count was never read, which is not the same as zero.

    A held event's `context` is None for exactly this reason, and the
    number that explains `context` has to be None in the same cases or a
    field log reads as though a floor was computed from an empty window.
    """
    outcome, _, _ = _fire(0.9, is_night=lambda frames: False)

    assert outcome.suppressed_by_vision is True
    assert outcome.context is None
    assert outcome.species_repeat_count is None


def test_a_boar_only_event_keeps_its_video_when_boar_is_configured(monkeypatch):
    """The whole point of the flag, asserted at the exit the file lives at.

    A boar on a quiet trigger never confirms and never alerts, so it leaves
    through the no-actuation exit. That is the only place its recording can
    be kept, and under the default configuration it correctly is not.

    Boar now needs VISION_SPECIES_CONSECUTIVE_POLLS["Boar"] = 2 consecutive
    polls before it is admitted into a watch's species set (see
    services/config.py), so the single-poll window _fire() defaults to
    (vision_watch_base_s=0.0) is no longer enough to reproduce the
    keeps-its-video behaviour this test exists to protect - that window
    always runs exactly one poll. Give it a real, if tiny, positive window
    with poll_interval_s=0.0 instead: interval 0 means the loop never
    sleeps between polls (see _watch_for_vision's start-to-start pacing),
    so it free-runs against the real monotonic clock until the window
    closes, easily completing many polls - and therefore Boar's 2-poll
    streak - inside a few milliseconds of wall time, against a fake
    detector and camera that both return instantly.
    """
    monkeypatch.setattr(reflex_loop, "VISION_VIDEO_LABELS", ("Elephant", "Boar"))
    video = _FakeEventVideo()

    outcome, _, _ = _fire(
        0.05,
        sta_lta_ratio=3.0,
        detect_vision=_FakeVisionDetect([BOAR]),
        event_video=video,
        vision_watch_base_s=0.05,
        vision_watch_poll_interval_s=0.0,
    )

    assert outcome.decision.alert is False
    assert video.committed != []


def test_a_boar_only_event_discards_its_video_by_default():
    """Elephant-only is what ships, and disk is finite."""
    video = _FakeEventVideo()

    outcome, _, _ = _fire(
        0.05,
        sta_lta_ratio=3.0,
        detect_vision=_FakeVisionDetect([BOAR]),
        event_video=video,
    )

    assert outcome.decision.alert is False
    assert video.committed == []


# --- end-to-end tri-state scope (ADR 0023, NODE_DETERRENCE_SCOPE) -----------
#
# The full pipeline, through _fire()/handle_footfall_event(), for each of the
# three states target_labels can express. probability=0.05, sta_lta_ratio=1.2
# is the same weak-seismic combination test_event_video_is_discarded_when_
# neither_gate_is_satisfied and test_a_boar_detection_is_not_a_confirmation
# already establish as insufficient to alert on its own - so any alert seen
# here is genuinely earned by a confirmed vision reading's own confidence
# (ELEPHANT and BOAR are both high-confidence fixtures, see their own
# comments above), not by seismic. That is what makes "no drive_horn call"
# and "drive_horn fires" meaningful assertions rather than foregone
# conclusions either way.


@FOX_GATE_RELAXATION
def test_a_single_spurious_boar_poll_fires_nothing_even_under_boar_only():
    """The bypass Workstream 3 exists to close, asserted at the actuator.

    One majority-qualifying Boar poll, then nothing - the script's last
    entry (empty) repeats for the rest of the free-running window, so the
    streak never reaches 2 and the watch never confirms. No horn, no LED,
    no kept video, and the fused decision itself carries no positive vision
    evidence - the streak-rejected poll was downgraded to BASELINE_VISION.
    """
    log: list = []
    video = _FakeEventVideo()
    detect = _ScriptedVisionDetect([[BOAR], []])

    outcome, _, log = _fire(
        probability=0.05,
        sta_lta_ratio=1.2,
        detect_vision=detect,
        target_labels=("Boar",),
        event_video=video,
        vision_watch_base_s=0.05,
        vision_watch_poll_interval_s=0.0,
        call_log=log,
    )

    assert outcome.vision_confirmed is False
    assert outcome.decision.alert is False
    assert "drive_horn" not in log
    assert "drive_led" not in log
    assert video.committed == []
    assert video.discarded == 1


def test_two_consecutive_boar_polls_fire_the_deterrent_and_keep_the_video():
    """Once Boar's own streak is met, it is treated exactly like any other confirmation.

    Same probability/sta_lta_ratio as the spurious-poll test above - the
    only difference is a detector that keeps finding Boar, so the streak
    clears on the second poll and the watch confirms and exits.
    """
    log: list = []
    video = _FakeEventVideo()

    outcome, _, log = _fire(
        probability=0.05,
        sta_lta_ratio=1.2,
        detect_vision=_FakeVisionDetect([BOAR]),
        target_labels=("Boar",),
        event_video=video,
        vision_watch_base_s=0.05,
        vision_watch_poll_interval_s=0.0,
        call_log=log,
    )

    assert outcome.vision_confirmed is True
    assert outcome.decision.alert is True
    assert "drive_horn" in log
    assert "drive_led" in log
    assert video.committed != []
    assert video.discarded == 0


def test_elephant_still_fires_on_the_first_poll_under_the_both_scope():
    """The regression guard: Boar sharing target_labels costs Elephant nothing.

    Elephant's required streak is 1, so under "both" it must still confirm
    and fire on the very first poll - the same single-poll window _fire()
    already defaults to for every non-watch-specific test in this file.
    """
    log: list = []

    outcome, _, log = _fire(
        probability=0.05,
        sta_lta_ratio=1.2,
        detect_vision=_FakeVisionDetect([ELEPHANT]),
        target_labels=("Elephant", "Boar"),
        call_log=log,
    )

    assert outcome.vision_confirmed is True
    assert outcome.vision_polls == 1
    assert outcome.decision.alert is True
    assert "drive_horn" in log


def test_the_outcome_reports_the_species_the_camera_confirmed():
    """The species travels from the watch to the uplink, not from the node config.

    comms/lora_uplink.py builds the frame's event class from this field
    alone, so a confirmation that does not reach it is a detection that
    reaches a ranger unnamed.
    """
    outcome, _, _ = _fire(
        probability=0.05,
        sta_lta_ratio=1.2,
        detect_vision=_FakeVisionDetect([BOAR]),
        target_labels=("Elephant", "Boar"),
        vision_watch_base_s=0.05,
        vision_watch_poll_interval_s=0.0,
    )

    assert outcome.vision_confirmed is True
    # A two-species node: the old config inference had no answer here.
    assert outcome.species == "Boar"


def test_a_seismic_only_alert_reports_no_species():
    """The fail-safe end of the same path: alert yes, species no."""
    outcome, _, _ = _fire(
        probability=0.95,
        sta_lta_ratio=9.0,
        detect_vision=_FakeVisionDetect([]),
    )

    assert outcome.decision.alert is True
    assert outcome.vision_confirmed is False
    assert outcome.species is None


def test_boar_fires_nothing_under_the_shipped_elephant_only_default_at_any_streak_length():
    """The default scope, checked at the actuator rather than only at the video.

    Two consecutive Boar polls satisfy Boar's own streak - the same script
    that fires everything in the boar_only test above - but target_labels
    stays the shipped ("Elephant",) default, so Boar can never be a
    confirming label regardless of how long it is sustained.
    """
    log: list = []
    video = _FakeEventVideo()

    outcome, _, log = _fire(
        probability=0.05,
        sta_lta_ratio=1.2,
        detect_vision=_FakeVisionDetect([BOAR]),
        event_video=video,
        vision_watch_base_s=0.05,
        vision_watch_poll_interval_s=0.0,
        call_log=log,
    )

    assert outcome.vision_confirmed is False
    assert outcome.decision.alert is False
    assert "drive_horn" not in log
    assert "drive_led" not in log
    assert video.committed == []


# --- _confirmed_species (ADR 0031 A as amended) -------------------------------
#
# Which species the camera actually confirmed, resolved once and read by
# the deterrence content, the bandit partition and the uplink alike. The
# distinction this block is here to pin is between *observed* and
# *configured*: nothing below passes a node scope that stands in for an
# answer the watch already has.


def _check(*, confirmed: bool, species: tuple[str, ...]) -> reflex_loop.VisionCheck:
    reading = reflex_loop.ModalityReading(Modality.VISION, 0.0, available=True)
    return reflex_loop.VisionCheck(reading, confirmed, species)


def test_an_unconfirmed_check_names_no_species():
    """None, not a guess - the whole point of the amendment to ADR 0031 A.

    A seismic-only alert is a real alert and still uplinks; it uplinks
    unnamed, because the geophone cannot tell one animal from another and
    a species on a ranger's screen has to be one the camera saw.
    """
    check = _check(confirmed=False, species=("Boar",))

    assert reflex_loop._confirmed_species(check, target_labels=("Boar",)) is None


def test_a_confirmed_label_outside_the_node_scope_names_no_species():
    """Unreachable from _vision_check(), which only confirms on a target match.

    Kept because this function's answer now reaches the wire: a label read
    back as confirming evidence for a scope that never targeted it would
    put a species in front of an officer that this node never agreed to
    look for.
    """
    check = _check(confirmed=True, species=("Boar",))

    assert reflex_loop._confirmed_species(check, target_labels=("Elephant",)) is None


def test_a_confirmed_fox_is_named_fox_not_its_content_species():
    """Fox and Boar share horn content; they must not share an identity on the wire."""
    check = _check(confirmed=True, species=("Fox",))

    assert reflex_loop._confirmed_species(check, target_labels=("Fox",)) == "Fox"
    # ... while the content it plays is still Boar's, per the registry.
    assert reflex_loop._deterrence_species(check, target_labels=("Fox",)) == "Boar"


def test_two_species_at_once_resolve_to_one_answer_in_registry_order():
    """Elephant wins the tie-break, and content and identity agree on it."""
    check = _check(confirmed=True, species=("Boar", "Elephant"))
    scope = ("Elephant", "Boar")

    assert reflex_loop._confirmed_species(check, target_labels=scope) == "Elephant"
    assert reflex_loop._deterrence_species(check, target_labels=scope) == "Elephant"


# --- _deterrence_species (ADR 0023) ------------------------------------------
#
# Which species cognition_config.resolve_tier_action() plays content for.
# Exercised directly against the pure function rather than through
# handle_footfall_event() - species selection only meaningfully diverges
# from "Elephant" once target_labels admits Boar (a NODE_DETERRENCE_SCOPE
# state), so the Boar-reachable cases pass an explicit target_labels
# argument, the same as any other _watch_for_vision()/handle_footfall_event()
# caller exercising a non-default scope would.


def test_an_unconfirmed_check_defaults_to_elephant():
    """No vision confirmation - seismic/acoustic alone - has no species evidence to use.

    The seismic/acoustic signature this device fuses on was built and tuned
    for elephant footfall, not boar, so there is nothing here that could
    say otherwise, whatever watch.species happens to carry.
    """
    check = _check(confirmed=False, species=("Boar",))

    assert reflex_loop._deterrence_species(check, target_labels=("Boar",)) == "Elephant"


def test_a_confirmed_elephant_check_selects_elephant():
    """The default, byte-for-byte-unchanged case: every node ships elephant_only."""
    check = _check(confirmed=True, species=("Elephant",))

    assert reflex_loop._deterrence_species(check) == "Elephant"


def test_a_confirmed_boar_check_selects_boar_once_boar_is_targeted():
    """Only reachable once NODE_DETERRENCE_SCOPE (boar_only or both) admits Boar."""
    check = _check(confirmed=True, species=("Boar",))

    assert (
        reflex_loop._deterrence_species(check, target_labels=("Elephant", "Boar"))
        == "Boar"
    )


def test_a_confirmed_boar_species_under_the_default_scope_still_falls_back_to_elephant():
    """Boar in .species without Boar in target_labels cannot happen from real code.

    _vision_check() output - confirmed=True there requires a target-label
    match - but the fallback must stay the safe default if it ever does.
    """
    check = _check(confirmed=True, species=("Boar",))

    assert reflex_loop._deterrence_species(check, target_labels=("Elephant",)) == "Elephant"


def test_both_species_confirmed_at_once_prefers_elephant():
    """Both animals genuinely in frame together, only reachable under "both".

    Elephant wins the tie-break: the deeper evidence base (Thuppil & Coss
    2016 vs. ADR 0023's ecological-inference argument for reusing tiger/lion
    on Boar) and the species this device exists for first.
    """
    check = _check(confirmed=True, species=("Boar", "Elephant"))

    assert (
        reflex_loop._deterrence_species(check, target_labels=("Elephant", "Boar"))
        == "Elephant"
    )


# ---------------------------------------------------------------------------
# The retained vision track (D9)
# ---------------------------------------------------------------------------
#
# The detector has always returned real bounding boxes and _vision_check()
# has always discarded them on the line that reduces them to a scalar. These
# assert the boxes now survive the reduction, and - the part that is easy to
# get subtly wrong - that "looked and saw nothing" stays distinguishable from
# "could not look" at every layer, because conflating those two is what fills
# a future model's negative class with unlabelled night elephants.


# A box on an untargeted, unconfigured class. Nothing in the deterrence path
# will ever read it; the record must keep it anyway.
CATTLE = Detection(label="Cattle", confidence=0.71, x=4.0, y=5.0, width=30.0, height=22.0)


def _stamped_frames(stamps: list[float]) -> list[Frame]:
    """Frames carrying the exact monotonic stamps a test wants to read back."""
    return [Frame(image=None, index=i, timestamp_s=t) for i, t in enumerate(stamps)]


def test_the_track_keeps_every_box_including_labels_nothing_is_configured_for():
    """The record is of what the camera saw, not of what this node deters.

    DETERRENT_TARGET_LABELS is deployment configuration and moves; a corpus
    filtered through one deployment's settings cannot be re-analysed under
    another's. Cattle is the case that matters in the field - it is the
    single most common thing a forest-edge geophone fires on, it is in
    neither the target labels nor the species gate, and it is exactly the
    negative evidence a future seismic model needs.
    """
    detect = _ScriptedVisionDetect([[[ELEPHANT, CATTLE], [CATTLE], [ELEPHANT]]])

    check = reflex_loop._vision_check(detect, _frames(3))

    assert [[d.label for d in s.detections] for s in check.track] == [
        ["Elephant", "Cattle"],
        ["Cattle"],
        ["Elephant"],
    ]
    # ...and the box itself survives intact, not just its label: the
    # geometry is the entire reason the track is worth keeping.
    cattle = check.track[0].detections[1]
    assert (cattle.x, cattle.y, cattle.width, cattle.height) == (4.0, 5.0, 30.0, 22.0)
    assert cattle.confidence == pytest.approx(0.71)


def test_a_frame_the_detector_found_nothing_in_is_a_sample_not_a_hole():
    """A frame that looked and saw nothing is an observation, not an absence.

    It is also the free negative class. The trap this pins: dropping empty
    frames would make a quiet frame indistinguishable from a frame that
    was never captured, and the difference between them is the difference
    between the no_animal and unlabelled buckets.
    """
    detect = _ScriptedVisionDetect([[[], [ELEPHANT], []]])

    check = reflex_loop._vision_check(detect, _frames(3))

    assert len(check.track) == 3
    assert check.track[0].detections == ()
    assert check.track[2].detections == ()
    assert [d.label for d in check.track[1].detections] == ["Elephant"]


def test_a_pass_with_no_frames_leaves_no_track_at_all():
    """No frames means the camera could not look - there is nothing to record.

    The companion to the test above: zero samples, not samples with zero
    detections.
    """
    check = reflex_loop._vision_check(_FakeVisionDetect([ELEPHANT]), [])

    assert check.track == ()
    assert check.reading.available is False


def test_a_detector_outage_leaves_no_track_rather_than_an_empty_one():
    """A failed detector saw nothing *and* observed nothing - same as no frames.

    The frames exist here, which is what makes this worth asserting
    separately: it would be easy to build the track from the frames alone
    and record three "saw nothing" samples for a pass where nothing was
    ever actually looked at.
    """
    detect = _ScriptedVisionDetect([DetectionError("fake: inference failed")])

    check = reflex_loop._vision_check(detect, _frames(3))

    assert check.track == ()
    assert check.reading.available is False


def test_a_sample_carries_its_own_frame_s_capture_stamp():
    """The timestamp has to be the camera's, or nothing aligns to anything.

    This is the number perception.video's footage and
    perception.seismic_stream's sample-to-clock mapping are both already
    on. A stamp taken when inference returned would carry the detector's
    latency - hundreds of milliseconds on this hardware - into every
    alignment, and the error would be invisible because the stamps would
    still look plausible.
    """
    stamps = [1000.25, 1000.50, 1000.75]
    detect = _ScriptedVisionDetect([[ELEPHANT]])

    check = reflex_loop._vision_check(detect, _stamped_frames(stamps))

    assert [s.timestamp_s for s in check.track] == stamps
    assert [s.frame_index for s in check.track] == [0, 1, 2]


def test_the_frame_index_is_the_frame_s_own_not_its_position_in_the_list():
    """Frame.index is the camera's numbering, and it is what has to be stored.

    They coincide in every ordinary burst, which is what makes enumerate()
    an easy and invisible substitution here. They stop coinciding the
    moment a capture drops a frame - perception.camera numbers what it
    received, so a burst missing its second frame is indices 0, 2, 3 - and
    a reader correlating a box back to the footage would then be off by
    one for the rest of the burst.
    """
    frames = [
        Frame(image=None, index=4, timestamp_s=1.0),
        Frame(image=None, index=7, timestamp_s=2.0),
    ]

    check = reflex_loop._vision_check(_FakeVisionDetect([ELEPHANT]), frames)

    assert [s.frame_index for s in check.track] == [4, 7]


def test_a_single_burst_pass_numbers_its_poll_one():
    """Callers outside a watch loop are poll 1, not poll 0.

    Matches VisionWatch.confirmed_on_poll's 1-based numbering, so the two
    can be compared without an off-by-one at the reader.
    """
    check = reflex_loop._vision_check(_FakeVisionDetect([ELEPHANT]), _frames(2))

    assert [s.poll for s in check.track] == [1, 1]


def test_a_short_detector_response_is_paired_by_index_and_never_raises(caplog):
    """A malformed response degrades the record; it must not fail the watch.

    An animal is in front of the camera at this instant. One result list
    for a three-frame burst is a detector bug, and the right response is a
    short track and a log line - a strict zip here would raise inside the
    watch loop and take the whole event with it.
    """
    detect = _ScriptedVisionDetect([[[ELEPHANT]]])

    with caplog.at_level("WARNING"):
        check = reflex_loop._vision_check(detect, _frames(3))

    assert len(check.track) == 1
    assert check.track[0].frame_index == 0
    assert check.confirmed is True
    assert "1 result lists for 3 frames" in caplog.text


def test_the_watch_keeps_the_boxes_from_every_poll_not_just_the_confirming_one():
    """The approach is the measurement; the arrival on its own is not.

    `frames` deliberately keeps only two bursts because frames are
    hundreds of megabytes. Boxes are not, and the polls in between are
    where a trajectory lives - an animal that crosses the frame over four
    polls has four range estimates, and keeping only the last one is
    keeping the one moment the trajectory cannot be computed from.
    """
    camera = _FakeCamera(frame_count=2)
    detect = _ScriptedVisionDetect([[], [CATTLE], [], [ELEPHANT]])

    watch, _ = _watch(camera, detect, 45.0)

    assert watch.confirmed_on_poll == 4
    # Two frames a poll, four polls, nothing dropped.
    assert len(watch.track) == 8
    assert [s.poll for s in watch.track] == [1, 1, 2, 2, 3, 3, 4, 4]
    assert [s.frame_index for s in watch.track] == [0, 1] * 4
    assert [d.label for d in watch.track[2].detections] == ["Cattle"]
    assert [d.label for d in watch.track[6].detections] == ["Elephant"]
    # And the frames really were discarded, which is what makes the track
    # the only surviving record of polls 2 and 3.
    assert len(watch.frames) == 4


def test_a_streak_rejected_poll_still_contributes_its_boxes(monkeypatch):
    """The debounce decides what a poll is worth to fuse(), not what was seen.

    The first Boar poll is downgraded to BASELINE_VISION because
    VISION_SPECIES_CONSECUTIVE_POLLS has not been met yet. It is still a
    boar in frame, and its box is the first half of the approach the poll
    that does confirm completes - so the rebuilt VisionCheck has to carry
    the track across, not reset it to empty along with the reading.

    The streak is set here rather than read from services/config.py: the
    13 Sept fox-gate relaxation currently leaves that mapping empty, so
    the live tuning cannot reach this branch at all, and the branch is
    what is under test. Patching the dict is also what keeps this honest
    if the relaxation is ever reverted.
    """
    monkeypatch.setitem(services_config.VISION_SPECIES_CONSECUTIVE_POLLS, "Boar", 2)
    camera = _FakeCamera(frame_count=1)
    detect = _ScriptedVisionDetect([[BOAR], [BOAR]])

    watch, _ = _watch(camera, detect, 45.0, target_labels=("Boar",))

    # Poll 1 was rejected by the streak gate, poll 2 confirmed.
    assert watch.confirmed_on_poll == 2
    assert [s.poll for s in watch.track] == [1, 2]
    assert [d.label for d in watch.track[0].detections] == ["Boar"]
    assert [d.label for d in watch.track[1].detections] == ["Boar"]


def test_the_rebuilt_check_from_a_rejected_poll_keeps_that_poll_s_boxes(monkeypatch):
    """The same claim on the other field the rebuild feeds: `watch.check`.

    The accumulator above reads the original check, so it cannot see
    whether the rebuilt one kept its track. `watch.check` can: a watch
    that only ever saw a streak-rejected poll returns that rebuilt check
    as its `best`, and that is the VisionCheck every downstream reader
    gets. A rebuild that dropped the track would hand them a check
    claiming the camera observed nothing, on a poll where it observed a
    boar.
    """
    monkeypatch.setitem(services_config.VISION_SPECIES_CONSECUTIVE_POLLS, "Boar", 2)
    camera = _FakeCamera(frame_count=1)
    # A single Boar poll, then nothing - the streak is never completed, so
    # the watch runs to its deadline unconfirmed on the rebuilt check.
    detect = _ScriptedVisionDetect([[BOAR], []])

    watch, _ = _watch(camera, detect, 2.0, target_labels=("Boar",))

    assert watch.confirmed_on_poll is None
    assert watch.check.confirmed is False
    assert watch.check.reading.log_odds == pytest.approx(cognition_config.BASELINE_VISION)
    assert [d.label for s in watch.check.track for d in s.detections] == ["Boar"]


def test_an_empty_poll_contributes_no_samples_to_the_watch_track():
    """A watch the camera never fed stays empty rather than looking quiet.

    At the watch layer this is the same distinction the per-pass tests
    make: a camera that returned nothing on every poll must not be
    recorded as a camera that watched and saw nothing, because the first
    is unlabelled and the second is a training negative.
    """
    camera = _FakeCamera(frame_count=0)

    watch, _ = _watch(camera, _FakeVisionDetect([ELEPHANT]), 45.0)

    assert watch.track == ()
    assert watch.check.reading.available is False


def test_an_unconfirmed_watch_still_returns_everything_it_saw():
    """Most watches never confirm, and those are most of the corpus.

    The confirming return is the easy one to remember to thread a new
    field through; the unconfirmed return is the one that runs on the
    overwhelming majority of triggers - wind, rain and cattle - and it is
    where the negative class comes from.
    """
    camera = _FakeCamera(frame_count=2)
    detect = _ScriptedVisionDetect([[CATTLE]])

    watch, _ = _watch(camera, detect, 2.0)

    assert watch.confirmed_on_poll is None
    assert watch.polls == 3
    assert len(watch.track) == 6
    assert all([d.label for d in s.detections] == ["Cattle"] for s in watch.track)


def test_the_track_is_ordered_by_poll_then_by_frame():
    """Readers slice it by time, so arrival order has to be capture order.

    Both consumers of this - aligning boxes to the seismic record, and
    differencing consecutive box heights for a relative range - read it as
    a time series and would silently produce a scrambled trajectory rather
    than an error if it were not sorted.
    """
    camera = _FakeCamera(frame_count=3)
    detect = _ScriptedVisionDetect([[], [], [ELEPHANT]])

    watch, _ = _watch(camera, detect, 45.0)

    keys = [(s.poll, s.frame_index) for s in watch.track]
    assert keys == sorted(keys)
    assert keys == [(p, f) for p in (1, 2, 3) for f in (0, 1, 2)]
    # Non-decreasing in wall-clock terms too, since every stamp is the
    # camera's own and the polls ran in order.
    stamps = [s.timestamp_s for s in watch.track]
    assert stamps == sorted(stamps)


def test_an_unconfirmed_watch_s_track_is_ordered_the_same_way():
    """Both returns, not just the confirming one.

    The two VisionWatch constructions are several hundred lines apart and
    have drifted from each other before. The unconfirmed one is also the
    one that runs on the overwhelming majority of triggers, so an
    ordering defect there would corrupt most of the corpus while every
    confirmed encounter looked fine.
    """
    camera = _FakeCamera(frame_count=2)
    detect = _ScriptedVisionDetect([[CATTLE]])

    watch, _ = _watch(camera, detect, 2.0)

    assert watch.confirmed_on_poll is None
    keys = [(s.poll, s.frame_index) for s in watch.track]
    assert keys == [(p, f) for p in (1, 2, 3) for f in (0, 1)]
    stamps = [s.timestamp_s for s in watch.track]
    assert stamps == sorted(stamps)
