"""Invariant checks for cognition/config.py, not restatements of its values.

Each test asserts a relationship that has to hold for the constant's own
documented rationale to still be true - matching the style of
tests/test_config.py (services/config.py's own invariant tests).
"""

import math
import re
from pathlib import Path

import pytest

from cognition import config
from cognition.bandit import Tier
from cognition.fusion import Modality, sigmoid

MCU_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "mcu" / "src" / "config.h"


def _read_mcu_define(name: str) -> float:
    """Pull a #define's numeric value out of device/mcu/src/config.h.

    Same technique tests/test_config.py uses for LED_BURST_MAX_MS, and used
    here for the same reason: the relationship being checked spans the
    MPU/MCU boundary, and the MPU's production code is deliberately not
    allowed to hold the MCU's number.
    """
    text = MCU_CONFIG_PATH.read_text(encoding="utf-8")
    match = re.search(rf"#define\s+{name}\s+([0-9.]+)", text)
    assert match, f"Could not find #define {name} in {MCU_CONFIG_PATH}"
    return float(match.group(1))


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


# ---------------------------------------------------------------------------
# Bandit hyperparameters
# ---------------------------------------------------------------------------


def test_epsilon_is_a_probability_that_actually_explores():
    """Epsilon must be a real probability, and must not be zero.

    select_tier() rejects anything outside [0, 1] at call time; the extra
    condition here is that it is strictly positive, because an epsilon of
    0.0 turns the bandit into a lookup table that can never revise a bad
    early estimate - which is the failure mode a node seeing a handful of
    events a week is most exposed to.
    """
    assert 0.0 < config.BANDIT_EPSILON <= 1.0


def test_epsilon_leaves_most_events_on_the_learned_policy():
    """Exploration must stay a minority of events.

    Every exploratory pull is a real disturbance to a real animal (ADR
    0003), so an epsilon above 0.5 would mean the device mostly ignores what
    it has learned in order to experiment on wildlife.
    """
    assert config.BANDIT_EPSILON < 0.5


def test_step_size_is_within_the_range_updated_value_accepts():
    """Alpha in (0, 1]: zero never learns, above one overshoots the reward."""
    assert 0.0 < config.BANDIT_STEP_SIZE <= 1.0


def test_step_size_is_fast_enough_to_track_habituation():
    """A slow alpha would defeat the module's own premise.

    config.py's rationale is that the true value drifts as an animal
    habituates, so recent experience has to dominate. At alpha below 0.05,
    experience from fifty events ago still carries meaningful weight - which
    is a stationary-bandit assumption this problem does not satisfy.
    """
    assert config.BANDIT_STEP_SIZE >= 0.05


def test_reward_horizon_exceeds_the_habituation_window():
    """A full-reward gap must be long enough to leave the repeat window.

    Otherwise an attempt could score a perfect reward while the animal is
    still close enough in time to count as a repeat - the reward and the
    context would be describing the same event contradictorily.
    """
    assert config.PROXY_REWARD_HORIZON_S > config.HABITUATION_WINDOW_S


def test_habituation_window_covers_the_mcu_actuator_cooldowns():
    """Two triggers the MCU would fire on separately must read as one visit.

    HORN_COOLDOWN_MS is the longest interval the MCU enforces between
    bursts; a habituation window shorter than that could classify an
    animal's immediate return as a fresh first trigger.
    """
    horn_cooldown_s = _read_mcu_define("HORN_COOLDOWN_MS") / 1000.0
    assert config.HABITUATION_WINDOW_S > horn_cooldown_s


def test_bucket_count_matches_the_configured_floor_ladder():
    """Every context habituation_context() can produce must have a floor.

    A ladder shorter than the bucket count would silently saturate contexts
    onto the last entry; longer, and buckets exist that no context ever
    reaches. Either is a config mistake, not a design choice.
    """
    assert len(config.TIER_FLOOR_BY_CONTEXT) == config.HABITUATION_BUCKET_COUNT


def test_floors_never_step_back_down_as_repeats_accumulate():
    """Escalation is one-directional - a later repeat cannot mandate less force."""
    floors = list(config.TIER_FLOOR_BY_CONTEXT)
    assert floors == sorted(floors)


def test_the_first_context_permits_every_tier():
    """An isolated trigger must leave the bandit free to choose any response.

    If the lowest context already floored above tier 1, the gentlest
    response would be unreachable in the field and the ladder's bottom rung
    would be decorative.
    """
    assert config.TIER_FLOOR_BY_CONTEXT[0] is Tier.TIER_1


def test_the_top_context_mandates_the_strongest_tier():
    """A persistently returning animal must end up at the top of the ladder."""
    assert config.TIER_FLOOR_BY_CONTEXT[-1] is Tier.TIER_3


# ---------------------------------------------------------------------------
# Deterrence tier ladder
# ---------------------------------------------------------------------------


def test_every_tier_has_an_action_and_they_agree_on_their_own_tier():
    """The dict key and the action's own tier field must not drift apart."""
    for tier in Tier:
        assert tier in config.DETERRENCE_TIERS
        assert config.DETERRENCE_TIERS[tier].tier is tier


def test_horn_gain_increases_strictly_with_tier():
    """Escalation has to mean more requested intensity, monotonically."""
    gains = [config.DETERRENCE_TIERS[tier].horn_gain_pct for tier in Tier]
    assert gains == sorted(gains)
    assert len(set(gains)) == len(gains)


def test_every_requested_gain_stays_inside_the_wire_protocol_range():
    """schema.md's drive_horn gain_pct is 0-100; a request outside it is malformed."""
    for action in config.DETERRENCE_TIERS.values():
        assert 0.0 <= action.horn_gain_pct <= config.PROTOCOL_GAIN_PCT_MAX


def test_every_requested_duration_fits_in_the_wire_uint16():
    """duration_ms is uint16 on every actuator row in schema.md."""
    for action in config.DETERRENCE_TIERS.values():
        for duration in (
            action.horn_duration_ms,
            action.led_duration_ms,
            action.ir_duration_ms,
        ):
            assert 0 <= duration <= config.PROTOCOL_DURATION_MS_MAX


def test_the_top_tier_requests_the_protocol_maximum():
    """Tier 3 must stay exactly the pre-bandit behaviour.

    The ladder was added to make quieter responses possible, not to weaken
    the loudest one. If tier 3 ever asks for less than the protocol max,
    this change has silently reduced the device's strongest deterrence.
    """
    top = config.DETERRENCE_TIERS[Tier.TIER_3]
    assert top.horn_gain_pct == config.PROTOCOL_GAIN_PCT_MAX
    assert top.horn_duration_ms == config.PROTOCOL_DURATION_MS_MAX
    assert top.led_duration_ms == config.PROTOCOL_DURATION_MS_MAX
    assert top.ir_duration_ms == config.PROTOCOL_DURATION_MS_MAX


def test_lower_tiers_stay_below_the_mcu_horn_clamp():
    """The drift check config.py's gain-fraction comment defers to this file for.

    Tiers 1-2 were chosen as fractions that land under the MCU's real
    HORN_GAIN_MAX_PCT, so the three tiers produce three distinct requests
    rather than collapsing into one clamped value. The MPU's production code
    is deliberately not allowed to encode that cap (services/config.py's
    boundary), so the obligation to re-check it lives here: if the firmware
    cap moves down past these fractions, this fails and the fractions get
    revisited.
    """
    horn_gain_max_pct = _read_mcu_define("HORN_GAIN_MAX_PCT")
    for tier in (Tier.TIER_1, Tier.TIER_2):
        gain = config.DETERRENCE_TIERS[tier].horn_gain_pct
        assert gain < horn_gain_max_pct, (
            f"{tier.name} requests {gain}%, at or above the MCU's current "
            f"HORN_GAIN_MAX_PCT ({horn_gain_max_pct}%) - it would clamp to the "
            "same physical output as a higher tier. Re-pick the gain fractions "
            "in cognition/config.py."
        )


def test_only_the_lowest_tier_withholds_ir():
    """Tier 1 fires no IR; both escalated tiers do.

    This is the axis that actually distinguishes the tiers physically today
    (gain_pct has no audible effect yet - see docs/KNOWN_GAPS.md), so losing
    it would leave tier 1 and tier 2 indistinguishable in the field.
    """
    assert config.DETERRENCE_TIERS[Tier.TIER_1].fire_ir is False
    assert config.DETERRENCE_TIERS[Tier.TIER_2].fire_ir is True
    assert config.DETERRENCE_TIERS[Tier.TIER_3].fire_ir is True


def test_led_pattern_ids_are_ones_the_mcu_actually_maps():
    """0 and 1 are the only pattern_ids with distinct channels MCU-side.

    device/mcu/src/bridge_handlers.cpp maps 1 to blue and everything else to
    white, so requesting 2 would silently be white again and the tier would
    lose its visual distinction without any error anywhere.
    """
    for action in config.DETERRENCE_TIERS.values():
        assert action.led_pattern_id in (0, 1)


def test_default_bandit_params_do_not_drift_from_their_constants():
    """The assembled params must match the constants documented above them."""
    params = config.DEFAULT_BANDIT_PARAMS
    assert params.epsilon == config.BANDIT_EPSILON
    assert params.step_size == config.BANDIT_STEP_SIZE
    assert params.habituation_window_s == config.HABITUATION_WINDOW_S
    assert params.tier_floor_by_context == config.TIER_FLOOR_BY_CONTEXT
    assert params.reward_horizon_s == config.PROXY_REWARD_HORIZON_S
