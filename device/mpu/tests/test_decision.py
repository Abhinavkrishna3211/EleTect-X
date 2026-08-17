"""Known-answer tests for cognition/decision.py.

Matches tests/test_fusion.py's pattern: hand-computed FusionResult fixtures,
exact assertions on the returned Decision, not just a pass/fail check.
"""

import pytest

from cognition.decision import decide
from cognition.fusion import FusionResult, Modality


def _fusion_result(probability: float) -> FusionResult:
    """Minimal FusionResult stand-in - decide() only reads .probability."""
    return FusionResult(
        log_odds=0.0,
        probability=probability,
        contributions={Modality.SEISMIC: 0.0},
        used=(Modality.SEISMIC,),
        dropped=(),
    )


def test_probability_above_threshold_alerts():
    """A fused probability clearing the threshold must alert."""
    decision = decide(_fusion_result(0.9), threshold=0.5)
    assert decision.alert is True
    assert decision.probability == pytest.approx(0.9)
    assert decision.threshold == pytest.approx(0.5)


def test_probability_below_threshold_does_not_alert():
    """A fused probability under the threshold must not alert."""
    decision = decide(_fusion_result(0.3), threshold=0.5)
    assert decision.alert is False


def test_probability_exactly_at_threshold_alerts():
    """decide() uses >=, biasing a boundary case toward acting, not away from it."""
    decision = decide(_fusion_result(0.5), threshold=0.5)
    assert decision.alert is True


@pytest.mark.parametrize("threshold", [-0.1, 1.1, float("nan")])
def test_threshold_outside_unit_interval_raises(threshold):
    """A threshold outside [0.0, 1.0] is a caller bug, not a value to clamp."""
    with pytest.raises(ValueError):
        decide(_fusion_result(0.5), threshold=threshold)


def test_threshold_boundary_values_are_accepted():
    """0.0 and 1.0 themselves are valid thresholds (always-alert / never-alert)."""
    assert decide(_fusion_result(0.5), threshold=0.0).alert is True
    assert decide(_fusion_result(0.5), threshold=1.0).alert is False
