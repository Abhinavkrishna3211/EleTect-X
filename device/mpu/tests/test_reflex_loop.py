"""Behavioral tests for services/reflex_loop.py.

Exercises the real sense -> fuse -> decide -> actuate wiring with mocked
sensor inputs and a recording fake in place of the real Bridge.call-backed
drive_horn.

Every expected fused log-odds/probability below is hand-computed against the
real cognition.config.DEFAULT_FUSION_PARAMS values (not a test-local
fixture, unlike test_fusion.py) via cognition.fusion.logit/sigmoid directly
- never by calling fuse() or reflex_loop's own logic a second time - so
these tests cannot pass by tautology (ENGINEERING_CONVENTIONS.md 4).
"""

import math

import pytest

from cognition import config as cognition_config
from cognition.fusion import Modality, sigmoid
from services import reflex_loop


class _FakeDriveHorn:
    """Recording stand-in for bridge.rpc.drive_horn, injected per call.

    Args:
        ack: What each call should return.
    """

    def __init__(self, ack: bool = True):
        self.ack = ack
        self.calls = []

    def __call__(self, schema_version, gain_pct, duration_ms):
        self.calls.append((schema_version, gain_pct, duration_ms))
        return self.ack


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


# ---------------------------------------------------------------------------
# handle_footfall_event()
# ---------------------------------------------------------------------------


def test_high_probability_alerts_and_drives_horn_outside_safe_mode():
    """A strong footfall probability fuses well past the threshold and fires the horn."""
    expected_log_odds, expected_p = _expected_seismic_fusion(0.9)
    drive_horn = _FakeDriveHorn(ack=True)

    outcome = reflex_loop.handle_footfall_event(
        1,
        0.9,
        sta_lta_ratio=6.0,
        feature_vector=[0.0] * 8,
        drive_horn=drive_horn,
        safe_mode=False,
    )

    assert outcome.fusion.log_odds == pytest.approx(expected_log_odds)
    assert outcome.fusion.probability == pytest.approx(expected_p)
    assert outcome.fusion.used == (Modality.SEISMIC,)
    assert set(outcome.fusion.dropped) == {Modality.ACOUSTIC, Modality.VISION}
    assert Modality.ACOUSTIC not in outcome.fusion.contributions
    assert Modality.VISION not in outcome.fusion.contributions

    assert outcome.decision.alert is True
    assert outcome.horn_ack is True
    assert drive_horn.calls == [
        (1, reflex_loop.ALERT_HORN_GAIN_PCT, reflex_loop.ALERT_HORN_DURATION_MS)
    ]


def test_safe_mode_suppresses_actuation_even_when_alert_fires():
    """SAFE_MODE must log the intended call, never place it."""
    drive_horn = _FakeDriveHorn()

    outcome = reflex_loop.handle_footfall_event(
        1,
        0.9,
        sta_lta_ratio=6.0,
        feature_vector=[0.0] * 8,
        drive_horn=drive_horn,
        safe_mode=True,
    )

    assert outcome.decision.alert is True
    assert outcome.horn_ack is None
    assert drive_horn.calls == []


def test_low_probability_does_not_alert_and_never_calls_drive_horn():
    """A weak footfall probability must not clear the threshold or fire the horn."""
    expected_log_odds, expected_p = _expected_seismic_fusion(0.05)
    assert expected_p < reflex_loop.ALERT_PROBABILITY_THRESHOLD  # sanity on the fixture
    drive_horn = _FakeDriveHorn()

    outcome = reflex_loop.handle_footfall_event(
        1,
        0.05,
        sta_lta_ratio=3.0,
        feature_vector=[0.0] * 8,
        drive_horn=drive_horn,
        safe_mode=False,
    )

    assert outcome.fusion.log_odds == pytest.approx(expected_log_odds)
    assert outcome.decision.alert is False
    assert outcome.horn_ack is None
    assert drive_horn.calls == []


def test_probability_at_exactly_zero_or_one_does_not_crash():
    """logit() rejects 0.0/1.0 outright - the epsilon clamp is what protects this call.

    Real MCU output realistically never saturates exactly, but the wire
    field is a plain float with no protocol-level guard against it.
    """
    drive_horn = _FakeDriveHorn()

    outcome_zero = reflex_loop.handle_footfall_event(
        1, 0.0, sta_lta_ratio=0.0, feature_vector=[0.0] * 8, drive_horn=drive_horn
    )
    outcome_one = reflex_loop.handle_footfall_event(
        1, 1.0, sta_lta_ratio=10.0, feature_vector=[0.0] * 8, drive_horn=drive_horn
    )

    assert outcome_zero.decision.alert is False
    assert outcome_one.decision.alert is True


def test_custom_threshold_overrides_the_default():
    """A caller-supplied threshold takes priority over ALERT_PROBABILITY_THRESHOLD."""
    drive_horn = _FakeDriveHorn()

    # 0.9 clears the default threshold (0.5) but not an intentionally strict one.
    outcome = reflex_loop.handle_footfall_event(
        1,
        0.9,
        sta_lta_ratio=6.0,
        feature_vector=[0.0] * 8,
        drive_horn=drive_horn,
        safe_mode=False,
        threshold=0.999,
    )

    assert outcome.decision.alert is False
    assert drive_horn.calls == []


def test_schema_version_mismatch_is_logged_not_raised(caplog):
    """A wire schema mismatch must warn, not raise - this is a notify target."""
    drive_horn = _FakeDriveHorn()

    with caplog.at_level("WARNING"):
        outcome = reflex_loop.handle_footfall_event(
            99,
            0.05,
            sta_lta_ratio=3.0,
            feature_vector=[0.0] * 8,
            drive_horn=drive_horn,
            safe_mode=False,
        )

    assert outcome is not None
    assert any("schema_version mismatch" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# handle_acoustic_event()
# ---------------------------------------------------------------------------


def test_acoustic_event_is_logged_and_returns_none(caplog):
    """Acoustic events are logged for visibility only - never fused, per module docstring."""
    from bridge.rpc import AcousticClass

    with caplog.at_level("INFO"):
        result = reflex_loop.handle_acoustic_event(1, AcousticClass.GUNSHOT, 0.87, 42)

    assert result is None
    assert any("gunshot" in record.message for record in caplog.records)
