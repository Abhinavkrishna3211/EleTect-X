"""Invariant checks for cognition/config.py, not restatements of its values.

Each test asserts a relationship that has to hold for the constant's own
documented rationale to still be true - matching the style of
tests/test_config.py (services/config.py's own invariant tests).
"""

import math

import pytest

from cognition import config
from cognition.fusion import Modality, sigmoid


def test_all_weights_are_strictly_positive():
    """A negative weight would invert that modality's evidence direction.

    A negative w_i means stronger elephant-consistent evidence (l_i above
    baseline) would push L down, the opposite of what fusion is for.
    """
    for modality, weight in config.DEFAULT_WEIGHTS.items():
        assert weight > 0, f"{modality} weight must be positive, got {weight}"


def test_weight_ordering_matches_documented_rationale():
    """Vision > seismic > acoustic - the one ordering ADR 0001/0007 justify.

    config.py's own rationale comment derives this from ADR 0001's
    Consequences (vision ~70-85% vs seismic ~70-75% standalone accuracy) and
    ADR 0007/0009 scoping acoustic as corroboration only, never standalone
    presence detection.
    """
    assert config.WEIGHT_VISION > config.WEIGHT_SEISMIC > config.WEIGHT_ACOUSTIC


def test_all_baselines_are_nonzero():
    """A zero baseline would make availability-gated dropout indistinguishable.

    If l0_i == 0.0, a modality reporting a genuine 0.0 log-odds would
    contribute exactly 0.0 to L - numerically identical to that modality
    being dropped for unavailability. config.py's baselines must stay
    nonzero for test_fusion.py's unavailable-vs-genuine-zero distinction to
    mean anything for these real values, not just the test fixture's.
    """
    for modality, baseline in config.DEFAULT_BASELINES.items():
        assert baseline != 0.0, f"{modality} baseline must be nonzero, got {baseline}"


@pytest.mark.parametrize(
    "baseline_name,expected_p_background",
    [
        ("BASELINE_SEISMIC", 0.10),
        ("BASELINE_ACOUSTIC", 0.10),
        ("BASELINE_VISION", 0.10),
    ],
)
def test_baseline_matches_documented_p_background(baseline_name, expected_p_background):
    """Each baseline literal must round-trip to the p_background its comment states.

    config.py cannot import cognition.fusion.logit to compute these values
    at module load (fusion.py's Modality is what config.py imports from,
    and the reverse import would be circular) - so each baseline is a hand-
    computed float literal instead. This test is what keeps that literal
    honest against its own stated derivation (logit(0.10)).
    """
    value = getattr(config, baseline_name)
    assert sigmoid(value) == pytest.approx(expected_p_background, abs=1e-3)


def test_l_prior_is_skeptical_not_uninformative():
    """L_PRIOR must be negative - "no evidence" must not read as a coin flip.

    config.py's rationale is explicit that -1.0 (not the uninformative 0.0
    alternative it also documents) was chosen so a single weak modality
    cannot push a fused P past 0.5 unaided.
    """
    assert config.L_PRIOR < 0.0


def test_default_fusion_params_covers_every_modality():
    """No Modality can be added to the enum without a weight and a baseline.

    fuse() raises ValueError for a reading whose modality is missing from
    params.weights/baselines (fusion.py) - this test catches that gap at
    config load time instead of at a future fuse() call.
    """
    for modality in Modality:
        assert modality in config.DEFAULT_FUSION_PARAMS.weights, (
            f"{modality} has no entry in DEFAULT_FUSION_PARAMS.weights"
        )
        assert modality in config.DEFAULT_FUSION_PARAMS.baselines, (
            f"{modality} has no entry in DEFAULT_FUSION_PARAMS.baselines"
        )


def test_default_fusion_params_l_prior_matches_l_prior_constant():
    """DEFAULT_FUSION_PARAMS.l_prior must not silently drift from L_PRIOR."""
    assert config.DEFAULT_FUSION_PARAMS.l_prior == config.L_PRIOR


def test_default_fusion_params_values_are_finite():
    """Every assembled constant must be a real, finite float - not NaN/inf.

    fuse() rejects a non-finite log_odds on a reading (fusion.py), but
    nothing at the fuse() call site validates params itself - this is the
    config-side equivalent for the weights/baselines/prior.
    """
    assert math.isfinite(config.DEFAULT_FUSION_PARAMS.l_prior)
    for weight in config.DEFAULT_FUSION_PARAMS.weights.values():
        assert math.isfinite(weight)
    for baseline in config.DEFAULT_FUSION_PARAMS.baselines.values():
        assert math.isfinite(baseline)
