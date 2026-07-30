"""Known-answer tests for cognition/fusion.py.

Fixture FusionParams below uses round numbers (l_prior=0.0, integer
weights/baselines), not the real cognition.config values, so a future
retune of the actual fusion weights never breaks the math itself being
tested here (ENGINEERING_CONVENTIONS.md 4: "assert the exact output
probability, not just returns a float between 0 and 1").
"""

import math

import pytest

from cognition.fusion import (
    FusionParams,
    Modality,
    ModalityReading,
    fuse,
    logit,
    sigmoid,
)

# l_prior=0.0 keeps every hand-computed L equal to the sum of contributions
# alone, with no prior offset to carry through each expected value by hand.
PARAMS = FusionParams(
    l_prior=0.0,
    weights={
        Modality.SEISMIC: 2.0,
        Modality.ACOUSTIC: 1.0,
        Modality.VISION: 3.0,
    },
    baselines={
        Modality.SEISMIC: 0.5,
        Modality.ACOUSTIC: -0.5,
        Modality.VISION: 1.0,
    },
)


# ---------------------------------------------------------------------------
# fuse() - known-answer cases
# ---------------------------------------------------------------------------


def test_single_modality():
    """One available modality: L = w * (l - l0), hand-computed."""
    result = fuse(
        [ModalityReading(Modality.SEISMIC, log_odds=2.5, available=True)],
        PARAMS,
    )
    # 2.0 * (2.5 - 0.5) = 4.0
    assert result.log_odds == pytest.approx(4.0)
    assert result.probability == pytest.approx(sigmoid(4.0))
    assert result.used == (Modality.SEISMIC,)
    assert result.dropped == ()
    assert result.contributions == {Modality.SEISMIC: pytest.approx(4.0)}


def test_two_concurrent_modalities():
    """Two available modalities: L is the sum of both hand-computed terms."""
    result = fuse(
        [
            ModalityReading(Modality.SEISMIC, log_odds=1.5, available=True),
            ModalityReading(Modality.VISION, log_odds=2.0, available=True),
        ],
        PARAMS,
    )
    # seismic: 2.0 * (1.5 - 0.5) = 2.0
    # vision:  3.0 * (2.0 - 1.0) = 3.0
    assert result.log_odds == pytest.approx(5.0)
    assert result.probability == pytest.approx(sigmoid(5.0))
    assert set(result.used) == {Modality.SEISMIC, Modality.VISION}
    assert result.dropped == ()


def test_three_concurrent_modalities():
    """All three modalities available: L is the sum of all three terms."""
    result = fuse(
        [
            ModalityReading(Modality.SEISMIC, log_odds=1.5, available=True),
            ModalityReading(Modality.ACOUSTIC, log_odds=0.0, available=True),
            ModalityReading(Modality.VISION, log_odds=2.0, available=True),
        ],
        PARAMS,
    )
    # seismic:  2.0 * (1.5 - 0.5)  = 2.0
    # acoustic: 1.0 * (0.0 - -0.5) = 0.5
    # vision:   3.0 * (2.0 - 1.0)  = 3.0
    assert result.log_odds == pytest.approx(5.5)
    assert result.probability == pytest.approx(sigmoid(5.5))
    assert set(result.used) == {Modality.SEISMIC, Modality.ACOUSTIC, Modality.VISION}
    assert result.dropped == ()


def test_one_modality_unavailable_is_excluded_not_zeroed():
    """An unavailable modality contributes nothing - no key, not a 0.0 key."""
    result = fuse(
        [
            ModalityReading(Modality.SEISMIC, log_odds=1.5, available=True),
            ModalityReading(Modality.VISION, log_odds=999.0, available=False),
        ],
        PARAMS,
    )
    # Only seismic's term: 2.0 * (1.5 - 0.5) = 2.0. Vision's absurd log_odds
    # (999.0) must have zero effect - it's flagged unavailable.
    assert result.log_odds == pytest.approx(2.0)
    assert result.used == (Modality.SEISMIC,)
    assert result.dropped == (Modality.VISION,)
    assert Modality.VISION not in result.contributions
    assert result.contributions == {Modality.SEISMIC: pytest.approx(2.0)}


def test_two_modalities_unavailable_is_excluded_not_zeroed():
    """Two unavailable modalities: only the remaining one contributes."""
    result = fuse(
        [
            ModalityReading(Modality.SEISMIC, log_odds=-50.0, available=False),
            ModalityReading(Modality.ACOUSTIC, log_odds=50.0, available=False),
            ModalityReading(Modality.VISION, log_odds=2.0, available=True),
        ],
        PARAMS,
    )
    # Only vision's term: 3.0 * (2.0 - 1.0) = 3.0.
    assert result.log_odds == pytest.approx(3.0)
    assert result.used == (Modality.VISION,)
    assert set(result.dropped) == {Modality.SEISMIC, Modality.ACOUSTIC}
    assert set(result.contributions) == {Modality.VISION}


def test_all_unavailable_returns_prior_unchanged():
    """Every reading unavailable: L == l_prior exactly, nothing used."""
    result = fuse(
        [
            ModalityReading(Modality.SEISMIC, log_odds=10.0, available=False),
            ModalityReading(Modality.ACOUSTIC, log_odds=-10.0, available=False),
            ModalityReading(Modality.VISION, log_odds=10.0, available=False),
        ],
        PARAMS,
    )
    assert result.log_odds == PARAMS.l_prior
    assert result.probability == pytest.approx(sigmoid(PARAMS.l_prior))
    assert result.used == ()
    assert set(result.dropped) == {Modality.SEISMIC, Modality.ACOUSTIC, Modality.VISION}
    assert result.contributions == {}


def test_empty_readings_returns_prior_unchanged():
    """No readings at all is the same outcome as all-unavailable."""
    result = fuse([], PARAMS)
    assert result.log_odds == PARAMS.l_prior
    assert result.probability == pytest.approx(sigmoid(PARAMS.l_prior))
    assert result.used == ()
    assert result.dropped == ()
    assert result.contributions == {}


def test_nonzero_prior_offsets_every_case():
    """A nonzero l_prior shifts L by exactly l_prior, nothing more."""
    params = FusionParams(l_prior=-1.0, weights=PARAMS.weights, baselines=PARAMS.baselines)
    result = fuse(
        [ModalityReading(Modality.SEISMIC, log_odds=2.5, available=True)],
        params,
    )
    # -1.0 + 2.0 * (2.5 - 0.5) = -1.0 + 4.0 = 3.0
    assert result.log_odds == pytest.approx(3.0)


def test_unavailable_vs_genuine_zero_log_odds_give_different_results():
    """A missing modality must not read the same as that modality reporting 0.0.

    Same modality (vision), same nominal log_odds value (0.0) - the only
    difference is the availability flag. The unavailable case must fall
    back to l_prior; the available case must contribute a real, nonzero
    term because vision's baseline (1.0) is not itself 0.0.
    """
    unavailable = fuse(
        [ModalityReading(Modality.VISION, log_odds=0.0, available=False)],
        PARAMS,
    )
    genuine_zero = fuse(
        [ModalityReading(Modality.VISION, log_odds=0.0, available=True)],
        PARAMS,
    )

    assert unavailable.log_odds == pytest.approx(PARAMS.l_prior)
    assert unavailable.used == ()
    assert Modality.VISION not in unavailable.contributions

    # 3.0 * (0.0 - 1.0) = -3.0
    assert genuine_zero.log_odds == pytest.approx(-3.0)
    assert genuine_zero.used == (Modality.VISION,)
    assert genuine_zero.contributions[Modality.VISION] == pytest.approx(-3.0)

    assert unavailable.log_odds != pytest.approx(genuine_zero.log_odds)


def test_dropout_does_not_renormalise_surviving_weights():
    """Dropping one modality leaves the survivors' contributions unchanged.

    Fuses seismic+vision both available, then again with acoustic also
    present but unavailable - the seismic/vision contributions must be
    bit-for-bit the same in both, proving nothing redistributes acoustic's
    weight onto the survivors.
    """
    two_modality = fuse(
        [
            ModalityReading(Modality.SEISMIC, log_odds=1.5, available=True),
            ModalityReading(Modality.VISION, log_odds=2.0, available=True),
        ],
        PARAMS,
    )
    with_dropout = fuse(
        [
            ModalityReading(Modality.SEISMIC, log_odds=1.5, available=True),
            ModalityReading(Modality.ACOUSTIC, log_odds=0.0, available=False),
            ModalityReading(Modality.VISION, log_odds=2.0, available=True),
        ],
        PARAMS,
    )
    assert with_dropout.log_odds == two_modality.log_odds
    assert with_dropout.contributions == two_modality.contributions


# ---------------------------------------------------------------------------
# fuse() - error cases
# ---------------------------------------------------------------------------


def test_duplicate_modality_raises():
    """Two readings for the same modality is rejected, not silently summed."""
    with pytest.raises(ValueError, match="duplicate"):
        fuse(
            [
                ModalityReading(Modality.SEISMIC, log_odds=1.0, available=True),
                ModalityReading(Modality.SEISMIC, log_odds=2.0, available=True),
            ],
            PARAMS,
        )


def test_unconfigured_modality_raises():
    """A modality with no weight/baseline entry in params is rejected."""
    sparse_params = FusionParams(
        l_prior=0.0,
        weights={Modality.SEISMIC: 1.0},
        baselines={Modality.SEISMIC: 0.0},
    )
    with pytest.raises(ValueError, match="VISION|vision"):
        fuse(
            [ModalityReading(Modality.VISION, log_odds=1.0, available=True)],
            sparse_params,
        )


@pytest.mark.parametrize("bad_value", [math.nan, math.inf, -math.inf])
def test_nonfinite_log_odds_raises(bad_value):
    """NaN/inf log_odds is rejected outright, even when available=True."""
    with pytest.raises(ValueError, match="non-finite"):
        fuse(
            [ModalityReading(Modality.SEISMIC, log_odds=bad_value, available=True)],
            PARAMS,
        )


def test_nonfinite_log_odds_raises_even_when_unavailable():
    """A non-finite log_odds is rejected even on a dropped modality.

    available=False is the documented channel for "no evidence"; a caller
    should never reach for NaN/inf as an alternative way to say the same
    thing, so this must fail loudly rather than pass through unused.
    """
    with pytest.raises(ValueError, match="non-finite"):
        fuse(
            [ModalityReading(Modality.SEISMIC, log_odds=math.nan, available=False)],
            PARAMS,
        )


# ---------------------------------------------------------------------------
# sigmoid()
# ---------------------------------------------------------------------------


def test_sigmoid_at_zero_is_one_half():
    """sigmoid(0.0) must equal exactly 0.5 - the midpoint of the logistic curve."""
    assert sigmoid(0.0) == pytest.approx(0.5)


@pytest.mark.parametrize("l_value", [2.0, -2.0, 5.0, -5.0])
def test_sigmoid_symmetry(l_value):
    """sigmoid(-L) == 1 - sigmoid(L), the defining symmetry of the logistic curve."""
    assert sigmoid(-l_value) == pytest.approx(1.0 - sigmoid(l_value))


def test_sigmoid_known_value_at_two():
    """sigmoid(2.0) against a hand-computed reference value."""
    # sigmoid(2) = 1 / (1 + e^-2) ~= 0.8807970779778823
    assert sigmoid(2.0) == pytest.approx(0.8807970779778823)


def test_sigmoid_saturates_without_raising():
    """Large-magnitude L saturates toward 0.0/1.0 instead of overflowing."""
    assert sigmoid(1000.0) == pytest.approx(1.0)
    assert sigmoid(-1000.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# logit()
# ---------------------------------------------------------------------------


def test_logit_at_one_half_is_zero():
    """logit(0.5) must equal exactly 0.0 - the inverse of sigmoid's midpoint."""
    assert logit(0.5) == pytest.approx(0.0)


@pytest.mark.parametrize("p", [0.01, 0.1, 0.269, 0.5, 0.73, 0.9, 0.99])
def test_logit_sigmoid_round_trip(p):
    """sigmoid(logit(p)) must recover p - the two functions are exact inverses."""
    assert sigmoid(logit(p)) == pytest.approx(p)


@pytest.mark.parametrize("p", [0.0, 1.0, -0.1, 1.1])
def test_logit_rejects_outside_open_interval(p):
    """logit() rejects both closed-interval endpoints and out-of-range values."""
    with pytest.raises(ValueError):
        logit(p)
