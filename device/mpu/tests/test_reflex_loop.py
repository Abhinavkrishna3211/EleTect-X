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
don't actually sleep for CAPTURE_POST_FIRE_TAIL_S real seconds each.

Exploration is disabled (epsilon 0.0) in _fire()'s default params. The real
DEFAULT_BANDIT_PARAMS explores on roughly one event in seven, which would
make every actuator-argument assertion here fail intermittently for a reason
that has nothing to do with what it is testing. Exploration itself is
covered directly in tests/test_bandit.py and by the one test below that
turns it back on deliberately.
"""

import dataclasses
import math
import time

import pytest

from bridge.rpc import AcousticClass
from cognition import config as cognition_config
from cognition.bandit import Tier
from cognition.experience import IN_MEMORY_PATH, ExperienceStore
from cognition.fusion import Modality, sigmoid
from perception.camera import CameraError, Frame
from perception.storage import CaptureEventTag
from services import reflex_loop

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

    def __call__(self, schema_version, gain_pct, duration_ms):
        self.calls.append((schema_version, gain_pct, duration_ms))
        self.call_log.append("drive_horn")
        return self.ack


class _FakeDriveLed:
    """Recording stand-in for bridge.rpc.drive_led, injected per call."""

    def __init__(self, ack: bool = True, call_log: list | None = None):
        self.ack = ack
        self.calls = []
        self.call_log = call_log if call_log is not None else []

    def __call__(self, schema_version, pattern_id, duration_ms):
        self.calls.append((schema_version, pattern_id, duration_ms))
        self.call_log.append("drive_led")
        return self.ack


class _FakePulseIr:
    """Recording stand-in for bridge.rpc.pulse_ir, injected per call."""

    def __init__(self, ack: bool = True, call_log: list | None = None):
        self.ack = ack
        self.calls = []
        self.call_log = call_log if call_log is not None else []

    def __call__(self, schema_version, duration_ms):
        self.calls.append((schema_version, duration_ms))
        self.call_log.append("pulse_ir")
        return self.ack


class _FakeSendLoraAlert:
    """Recording stand-in for bridge.rpc.send_lora_alert, injected per call."""

    def __init__(self, ack: bool = False, call_log: list | None = None):
        self.ack = ack
        self.calls = []
        self.call_log = call_log if call_log is not None else []

    def __call__(self, schema_version, confidence, capture_ref):
        self.calls.append((schema_version, confidence, capture_ref))
        self.call_log.append("send_lora_alert")
        return self.ack


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
    """

    def __init__(
        self,
        frame_count: int = 3,
        fail_open: bool = False,
        fail_capture: bool = False,
        call_log: list | None = None,
    ):
        self._frame_count = frame_count
        self._fail_open = fail_open
        self._fail_capture = fail_capture
        self.call_log = call_log if call_log is not None else []
        self.opened = False

    def open(self):
        self.call_log.append("camera.open")
        if self._fail_open:
            raise CameraError("fake camera: open() failed")
        self.opened = True

    def capture_burst(self, count, interval_s):
        self.call_log.append("camera.capture_burst")
        if self._fail_capture:
            raise CameraError("fake camera: capture_burst() failed")
        return [
            Frame(image=None, index=i, timestamp_s=time.monotonic())
            for i in range(self._frame_count)
        ]

    def close(self):
        self.call_log.append("camera.close")
        self.opened = False


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


def _fire(probability=0.9, sta_lta_ratio=6.0, schema_version=1, call_log=None, **fakes):
    """Call handle_footfall_event with sensible defaults and a shared call_log.

    Any of drive_horn/drive_led/pulse_ir/camera/save_frames/experience can be
    overridden via **fakes; unspecified ones get a default fake sharing
    call_log, so a test only has to construct the fake(s) it cares about.

    The default experience store is fresh and in-memory, so an unspecified
    one means a cold store: no repeats, no learned values, and therefore
    tier 1. A test that needs history across events constructs one store and
    passes it to several _fire() calls.
    """
    log = call_log if call_log is not None else []
    kwargs = {
        "drive_horn": fakes.pop("drive_horn", _FakeDriveHorn(call_log=log)),
        "drive_led": fakes.pop("drive_led", _FakeDriveLed(call_log=log)),
        "pulse_ir": fakes.pop("pulse_ir", _FakePulseIr(call_log=log)),
        "camera": fakes.pop("camera", _FakeCamera(call_log=log)),
        "save_frames": fakes.pop("save_frames", _FakeSaveFrames(call_log=log)),
        "experience": fakes.pop("experience", ExperienceStore(IN_MEMORY_PATH)),
        "bandit_params": fakes.pop("bandit_params", DETERMINISTIC_PARAMS),
    }
    kwargs.update(fakes)
    outcome = reflex_loop.handle_footfall_event(
        schema_version,
        probability,
        sta_lta_ratio=sta_lta_ratio,
        feature_vector=[0.0] * 8,
        safe_mode=False,
        capture_post_fire_tail_s=0.0,
        **kwargs,
    )
    return outcome, kwargs, log


# ---------------------------------------------------------------------------
# handle_footfall_event() - fusion/decision/horn (pre-existing coverage)
# ---------------------------------------------------------------------------


def test_high_probability_alerts_and_fires_the_selected_tier_outside_safe_mode():
    """A strong footfall fuses past the threshold and fires the tier the bandit picked.

    On a cold store that is tier 1: horn and LED at tier 1's own values, and
    no IR at all. The IR assertion is the one that changed when the bandit
    landed - every alert used to fire all three actuators unconditionally.
    """
    expected_log_odds, expected_p = _expected_seismic_fusion(0.9)
    outcome, kwargs, _ = _fire(0.9)

    assert outcome.fusion.log_odds == pytest.approx(expected_log_odds)
    assert outcome.fusion.probability == pytest.approx(expected_p)
    assert outcome.fusion.used == (Modality.SEISMIC,)
    assert set(outcome.fusion.dropped) == {Modality.ACOUSTIC, Modality.VISION}
    assert Modality.ACOUSTIC not in outcome.fusion.contributions
    assert Modality.VISION not in outcome.fusion.contributions

    assert outcome.decision.alert is True
    assert outcome.action is TIER_1
    assert outcome.context == 0
    assert outcome.repeat_count == 0
    assert outcome.exploring is False
    assert outcome.horn_ack is True
    assert outcome.led_ack is True
    assert outcome.ir_ack is None
    assert kwargs["drive_horn"].calls == [
        (1, TIER_1.horn_gain_pct, TIER_1.horn_duration_ms)
    ]
    assert kwargs["drive_led"].calls == [
        (1, TIER_1.led_pattern_id, TIER_1.led_duration_ms)
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


def test_low_probability_does_not_alert_and_never_calls_any_actuator_or_camera():
    """A weak footfall probability must not clear the threshold or fire anything."""
    expected_log_odds, expected_p = _expected_seismic_fusion(0.05)
    assert expected_p < reflex_loop.ALERT_PROBABILITY_THRESHOLD  # sanity on the fixture
    outcome, kwargs, log = _fire(0.05, sta_lta_ratio=3.0)

    assert outcome.fusion.log_odds == pytest.approx(expected_log_odds)
    assert outcome.decision.alert is False
    assert outcome.horn_ack is None
    assert outcome.led_ack is None
    assert outcome.ir_ack is None
    assert outcome.capture_frame_count == 0
    assert kwargs["drive_horn"].calls == []
    assert log == []


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


def test_camera_opens_before_actuators_and_closes_after_them_with_frames_saved():
    """Event order must be open -> capture -> horn -> led -> close -> save.

    No pulse_ir entry: this is tier 1 on a cold store, which fires no IR.
    The tiers that do fire it are covered by
    test_escalated_tier_fires_ir_in_the_documented_position.
    """
    outcome, kwargs, log = _fire(0.9)

    assert log == [
        "camera.open",
        "camera.capture_burst",
        "drive_horn",
        "drive_led",
        "camera.close",
        "save_frames",
    ]
    assert outcome.capture_frame_count == 3
    assert kwargs["camera"].opened is False  # closed, not left dangling


def test_saved_frames_are_tagged_with_the_triggering_event_metadata():
    """save_frames must receive the actual frames plus timestamp/ratio/probability/decision."""
    outcome, kwargs, _ = _fire(0.9, sta_lta_ratio=6.0)

    save_frames = kwargs["save_frames"]
    assert len(save_frames.calls) == 1
    frames, tag = save_frames.calls[0]
    assert len(frames) == outcome.capture_frame_count == 3
    assert isinstance(tag, CaptureEventTag)
    assert tag.sta_lta_ratio == 6.0
    assert tag.fused_probability == pytest.approx(outcome.fusion.probability)
    assert tag.alert is True
    assert tag.event_timestamp_s == pytest.approx(time.time(), abs=5.0)


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


def test_camera_capture_failure_never_blocks_actuator_firing_and_camera_still_closes(caplog):
    """A camera that opens but fails to capture must still let deterrence fire, and still close."""
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
# handle_footfall_event() - bandit selection and habituation avoidance
# ---------------------------------------------------------------------------


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


def test_escalated_tier_fires_ir_in_the_documented_position():
    """Tier 2 fires all three actuators, with pulse_ir after drive_led.

    The counterpart to the tier-1 ordering test above: the order the module
    docstring promises is unchanged, IR is simply present again once the
    tier calls for it.
    """
    experience = ExperienceStore(IN_MEMORY_PATH)
    _fire(0.9, experience=experience)

    log: list = []
    outcome, kwargs, log = _fire(0.9, experience=experience, call_log=log)

    assert outcome.action is TIER_2
    assert outcome.ir_ack is True
    assert kwargs["pulse_ir"].calls == [(1, TIER_2.ir_duration_ms)]
    assert log == [
        "camera.open",
        "camera.capture_burst",
        "drive_horn",
        "drive_led",
        "pulse_ir",
        "camera.close",
        "save_frames",
    ]
    experience.close()


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
    assert loud.action is TIER_2
    experience.close()


def test_a_fired_attempt_is_recorded_and_settled_by_the_next_event():
    """The full learning round trip: fire, come back, score, store the value.

    The gap between the two events here is milliseconds against a 1800s
    horizon, so the proxy reward is essentially zero - a returning animal is
    the failure case, and the value that lands in the store must reflect
    that. Asserting "a value now exists and it is near zero" is the honest
    assertion; asserting a specific figure would be asserting how long the
    test itself took to run.
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
    assert second_outcome.action is TIER_2
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
            save_frames=_FakeSaveFrames(),
            experience=experience,
            bandit_params=DETERMINISTIC_PARAMS,
            safe_mode=True,
        )

    third, _, _ = _fire(0.9, experience=experience)
    assert third.repeat_count == 2
    assert third.action is TIER_3
    experience.close()


def test_a_learned_preference_beats_the_default_tie_break():
    """Once a tier has earned value, greedy selection prefers it over tier 1.

    Seeded directly into the store rather than trained through the loop:
    training a preference in-process would take a real 1800s horizon's worth
    of wall clock. What is under test is that the loop reads the stored
    values and acts on them, not that the update arithmetic works - that is
    tests/test_experience.py's job.
    """
    experience = ExperienceStore(IN_MEMORY_PATH)
    experience.record_attempt(time.time() - 3600.0, 0, Tier.TIER_3)
    experience.settle_pending(time.time(), DETERMINISTIC_PARAMS)

    outcome, kwargs, _ = _fire(0.9, experience=experience)

    assert outcome.action is TIER_3
    assert outcome.exploring is False
    assert kwargs["pulse_ir"].calls == [(1, TIER_3.ir_duration_ms)]
    experience.close()


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
    class_label=AcousticClass.CHAINSAW,
    confidence=0.5,
    capture_ref=0,
    *,
    safe_mode=True,
    call_log=None,
    send_lora_alert=None,
):
    log = call_log if call_log is not None else []
    fake = send_lora_alert if send_lora_alert is not None else _FakeSendLoraAlert(call_log=log)
    outcome = reflex_loop.handle_acoustic_event(
        schema_version,
        class_label,
        confidence,
        capture_ref,
        safe_mode=safe_mode,
        send_lora_alert=fake,
    )
    return outcome, fake, log


def test_acoustic_event_is_logged_and_returns_its_outcome(caplog):
    """Every acoustic event is logged and reports which route ADR 0007 5 sent it down."""
    with caplog.at_level("INFO"):
        outcome, _, _ = _route(class_label=AcousticClass.GUNSHOT, confidence=0.87, capture_ref=42)

    assert outcome.class_label is AcousticClass.GUNSHOT
    assert outcome.direct_alert is True
    assert any("gunshot" in record.message for record in caplog.records)


def test_gunshot_never_reaches_fusion_and_logs_a_direct_alert(caplog):
    """ADR 0007 5's central rule, as a regression guard.

    The ADR is explicit that a gunshot is not evidence toward "is an elephant
    present", and that folding it into the elephant-presence fusion score
    would be a modeling error. A None fusion here means fuse() was never
    called at all - an event that fused with acoustic unavailable still
    carries a real FusionResult (see test_ambient_is_fused_as_unavailable
    below), so this assertion distinguishes the two.
    """
    with caplog.at_level("INFO"):
        outcome, fake, _ = _route(class_label=AcousticClass.GUNSHOT, confidence=0.93, capture_ref=7)

    assert outcome.fusion is None
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

    assert outcome.fusion is None
    assert outcome.direct_alert is True
    assert outcome.lora_ack is True
    assert fake.calls == [(1, 0.93, 7)]

    messages = [record.message for record in caplog.records]
    assert any("send_lora_alert ack=True" in m and "confidence=0.930" in m for m in messages)


@pytest.mark.parametrize(
    "class_label",
    [
        AcousticClass.CHAINSAW,
        AcousticClass.VEHICLE,
        AcousticClass.ANIMAL_CALL,
        AcousticClass.AMBIENT,
    ],
)
def test_send_lora_alert_is_never_called_for_non_gunshot_classes(class_label):
    """Only a gunshot classification may touch send_lora_alert, safe_mode or not."""
    outcome, fake, _ = _route(
        class_label=class_label, confidence=0.8, capture_ref=9, safe_mode=False
    )

    assert outcome.direct_alert is False
    assert fake.calls == []


def test_chainsaw_feeds_fusion_as_the_acoustic_modality():
    """A chainsaw is elephant-presence evidence and fuses at WEIGHT_ACOUSTIC."""
    expected_log_odds, expected_p = _expected_acoustic_fusion(0.8)

    outcome, _, _ = _route(class_label=AcousticClass.CHAINSAW, confidence=0.8, capture_ref=3)

    assert outcome.direct_alert is False
    assert outcome.fusion is not None
    assert outcome.fusion.log_odds == pytest.approx(expected_log_odds)
    assert outcome.fusion.probability == pytest.approx(expected_p)
    assert outcome.fusion.used == (Modality.ACOUSTIC,)
    assert set(outcome.fusion.dropped) == {Modality.SEISMIC, Modality.VISION}
    assert Modality.SEISMIC not in outcome.fusion.contributions
    assert Modality.VISION not in outcome.fusion.contributions


@pytest.mark.parametrize(
    "class_label, confidence",
    [
        (AcousticClass.CHAINSAW, 0.62),
        (AcousticClass.VEHICLE, 0.77),
        (AcousticClass.ANIMAL_CALL, 0.91),
    ],
)
def test_the_three_fusing_classes_share_one_acoustic_modality(class_label, confidence):
    """ADR 0007 treats chainsaw/vehicle/animal_call as one modality, not three.

    Each class is checked at a *different* confidence deliberately: agreeing
    on one shared input would not distinguish "all three use WEIGHT_ACOUSTIC"
    from "all three happen to coincide at this particular value". Matching
    the single-modality hand computation across three distinct inputs can
    only hold if each really is routed through the same weight and baseline.
    """
    expected_log_odds, expected_p = _expected_acoustic_fusion(confidence)

    outcome, _, _ = _route(class_label=class_label, confidence=confidence, capture_ref=11)

    assert outcome.class_label is class_label
    assert outcome.direct_alert is False
    assert outcome.fusion.log_odds == pytest.approx(expected_log_odds)
    assert outcome.fusion.probability == pytest.approx(expected_p)
    assert outcome.fusion.used == (Modality.ACOUSTIC,)


def test_ambient_is_fused_as_unavailable():
    """Ambient is "nothing to say", excluded from the sum - never negative evidence.

    INVENTED mapping: ADR 0007 names only four classes and never routes
    ambient. ADR 0001's addendum fixes the shape - a missing modality is
    excluded, not scored down - so the fused result must land exactly on the
    prior, with no acoustic contribution, even at a high confidence.
    """
    outcome, _, _ = _route(class_label=AcousticClass.AMBIENT, confidence=0.99, capture_ref=5)

    assert outcome.direct_alert is False
    assert outcome.fusion is not None
    assert outcome.fusion.used == ()
    assert set(outcome.fusion.dropped) == {
        Modality.ACOUSTIC,
        Modality.SEISMIC,
        Modality.VISION,
    }
    assert Modality.ACOUSTIC not in outcome.fusion.contributions
    assert outcome.fusion.log_odds == pytest.approx(cognition_config.L_PRIOR)
    assert outcome.fusion.probability == pytest.approx(sigmoid(cognition_config.L_PRIOR))


def test_acoustic_confidence_at_exactly_zero_or_one_does_not_crash():
    """logit() rejects 0.0/1.0 outright - the shared epsilon clamp protects this call too.

    Same guard as the footfall test above, exercised on the other caller of
    _confidence_log_odds(): the wire field is a plain float with no
    protocol-level bound either way.
    """
    outcome_zero, _, _ = _route(class_label=AcousticClass.VEHICLE, confidence=0.0, capture_ref=1)
    outcome_one, _, _ = _route(class_label=AcousticClass.VEHICLE, confidence=1.0, capture_ref=2)

    assert math.isfinite(outcome_zero.fusion.log_odds)
    assert math.isfinite(outcome_one.fusion.log_odds)
    assert outcome_zero.fusion.probability < outcome_one.fusion.probability


def test_acoustic_schema_version_mismatch_is_logged_not_raised(caplog):
    """A mismatched schema_version is a warning, never an exception - and still routes."""
    with caplog.at_level("WARNING"):
        outcome, _, _ = _route(
            schema_version=99, class_label=AcousticClass.CHAINSAW, confidence=0.8, capture_ref=4
        )

    assert outcome.fusion is not None
    assert any(
        "schema_version mismatch" in record.message and record.levelname == "WARNING"
        for record in caplog.records
    )
