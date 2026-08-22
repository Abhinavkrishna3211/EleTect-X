"""Tests for cognition/bandit.py's pure selection and update functions.

Every expected value here is computed by hand and written as a literal.
Nothing in this file re-derives an expectation by calling the function under
test, or by re-implementing its formula in the test body
(ENGINEERING_CONVENTIONS.md 4) - a test that computes
`old + step * (reward - old)` to check updated_value() would pass against
any consistent bug in either copy.

Selection is exercised with a seeded random.Random rather than statistically.
select_tier() takes its RNG as an argument precisely so a test can assert the
exact tier chosen on a given draw; asserting "roughly 15% of 10000 calls
explored" would be slower, flakier, and would not catch picking the wrong
tier inside the exploration branch.
"""

import random

import pytest

from cognition.bandit import (
    BanditParams,
    Tier,
    escalation_floor,
    habituation_context,
    proxy_reward,
    select_tier,
    updated_value,
)

# Distinct from cognition/config.py's real values on purpose: these tests are
# about the functions' behaviour, not about the tuning. A test that consumed
# DEFAULT_BANDIT_PARAMS would start failing the day someone retunes epsilon,
# which is a change these assertions have no opinion about.
PARAMS = BanditParams(
    epsilon=0.5,
    step_size=0.2,
    habituation_window_s=600.0,
    tier_floor_by_context=(Tier.TIER_1, Tier.TIER_2, Tier.TIER_3),
    reward_horizon_s=1000.0,
)

NEVER_EXPLORES = BanditParams(
    epsilon=0.0,
    step_size=PARAMS.step_size,
    habituation_window_s=PARAMS.habituation_window_s,
    tier_floor_by_context=PARAMS.tier_floor_by_context,
    reward_horizon_s=PARAMS.reward_horizon_s,
)

ALWAYS_EXPLORES = BanditParams(
    epsilon=1.0,
    step_size=PARAMS.step_size,
    habituation_window_s=PARAMS.habituation_window_s,
    tier_floor_by_context=PARAMS.tier_floor_by_context,
    reward_horizon_s=PARAMS.reward_horizon_s,
)


# ---------------------------------------------------------------------------
# habituation_context
# ---------------------------------------------------------------------------


def test_isolated_trigger_maps_to_the_lowest_context():
    """A first trigger (no repeats behind it) must land in context 0."""
    assert habituation_context(0, 3) == 0


def test_repeat_counts_map_one_to_one_below_the_top_bucket():
    """Below saturation the bucket is the repeat count itself, not a rescaling."""
    assert habituation_context(1, 3) == 1
    assert habituation_context(2, 3) == 2


def test_context_saturates_at_the_top_bucket():
    """A 3rd and a 30th repeat share the top bucket - the ladder has an end.

    Without saturation the context index would run off the end of
    tier_floor_by_context and select_tier would be handed a bucket no floor
    or action value exists for.
    """
    assert habituation_context(3, 3) == 2
    assert habituation_context(30, 3) == 2


def test_negative_repeat_count_is_treated_as_zero():
    """A negative count cannot index a bucket; it must floor to 0, not raise.

    This runs on the event path - a store returning something nonsensical
    should degrade to "treat it as a first trigger", not crash the handler.
    """
    assert habituation_context(-5, 3) == 0


def test_single_bucket_configuration_collapses_every_count_to_zero():
    """With one bucket the bandit is context-free, and every count maps to 0."""
    assert habituation_context(0, 1) == 0
    assert habituation_context(9, 1) == 0


def test_bucket_count_below_one_is_rejected():
    """bucket_count < 1 has no valid return value, so it must raise."""
    with pytest.raises(ValueError):
        habituation_context(0, 0)


# ---------------------------------------------------------------------------
# escalation_floor
# ---------------------------------------------------------------------------


def test_floor_rises_with_context():
    """The habituation mechanism itself: more repeats, higher minimum tier."""
    assert escalation_floor(0, PARAMS) is Tier.TIER_1
    assert escalation_floor(1, PARAMS) is Tier.TIER_2
    assert escalation_floor(2, PARAMS) is Tier.TIER_3


def test_floor_is_monotone_non_decreasing_across_configured_contexts():
    """Assert the ladder never steps back down as repeats accumulate.

    A configured tuple that dipped (say TIER_3 then TIER_2) would mean a
    third return got a weaker mandatory response than a second - the exact
    inversion of what habituation avoidance is for.
    """
    floors = [escalation_floor(i, PARAMS) for i in range(len(PARAMS.tier_floor_by_context))]
    assert floors == sorted(floors)


def test_floor_saturates_past_the_configured_contexts():
    """A context beyond the tuple clamps to its last entry rather than raising."""
    assert escalation_floor(99, PARAMS) is Tier.TIER_3


def test_empty_floor_configuration_is_rejected():
    """An empty ladder has no floor to return, so it must raise, not IndexError."""
    params = BanditParams(
        epsilon=0.0,
        step_size=0.2,
        habituation_window_s=600.0,
        tier_floor_by_context=(),
        reward_horizon_s=1000.0,
    )
    with pytest.raises(ValueError):
        escalation_floor(0, params)


# ---------------------------------------------------------------------------
# select_tier - greedy branch
# ---------------------------------------------------------------------------


def test_greedy_selection_takes_the_highest_valued_tier():
    """With epsilon 0 the best-valued tier wins outright."""
    values = {(0, Tier.TIER_1): 0.1, (0, Tier.TIER_2): 0.7, (0, Tier.TIER_3): 0.3}
    tier, exploring = select_tier(0, values, NEVER_EXPLORES, random.Random(0))
    assert tier is Tier.TIER_2
    assert exploring is False


def test_greedy_selection_reads_only_its_own_context():
    """A value learned in another context must not influence this one.

    This is the entire difference between a contextual bandit and a plain
    one: tier 3 is the best action in context 1 below and must still lose in
    context 0, where the evidence says otherwise.
    """
    values = {(0, Tier.TIER_2): 0.6, (1, Tier.TIER_3): 0.9}
    tier, _ = select_tier(0, values, NEVER_EXPLORES, random.Random(0))
    assert tier is Tier.TIER_2


def test_ties_break_to_the_lowest_permitted_tier():
    """Equal values must resolve to least force, not to whichever max() saw last."""
    values = {(0, Tier.TIER_1): 0.4, (0, Tier.TIER_2): 0.4, (0, Tier.TIER_3): 0.4}
    tier, _ = select_tier(0, values, NEVER_EXPLORES, random.Random(0))
    assert tier is Tier.TIER_1


def test_cold_store_selects_the_gentlest_tier():
    """With nothing learned yet the device's first response is its quietest.

    The cold-start case is not an edge case here - it is every node's first
    real event, so the tie-break rule above decides the device's untrained
    field behaviour.
    """
    tier, exploring = select_tier(0, {}, NEVER_EXPLORES, random.Random(0))
    assert tier is Tier.TIER_1
    assert exploring is False


def test_missing_values_are_treated_as_zero_not_as_disqualifying():
    """An unvisited tier competes at 0.0, so a negative-valued tier loses to it.

    Values can go negative only if a future reward can; today proxy_reward is
    non-negative, so this asserts the comparison rule rather than a reachable
    state - it is here so that changing the reward's range cannot silently
    change which arm an unvisited tier beats.
    """
    values = {(0, Tier.TIER_1): -0.5}
    tier, _ = select_tier(0, values, NEVER_EXPLORES, random.Random(0))
    assert tier is Tier.TIER_2


# ---------------------------------------------------------------------------
# select_tier - floor interaction
# ---------------------------------------------------------------------------


def test_floor_excludes_lower_tiers_even_when_they_are_best_valued():
    """The escalation floor overrides learned preference - that is its point.

    Tier 1 has the highest value here and is still not selectable, because
    the animal has already come back once and tier 1 demonstrably did not
    stop it.
    """
    values = {(1, Tier.TIER_1): 0.9, (1, Tier.TIER_2): 0.2, (1, Tier.TIER_3): 0.1}
    tier, _ = select_tier(1, values, NEVER_EXPLORES, random.Random(0), floor=Tier.TIER_2)
    assert tier is Tier.TIER_2


def test_top_floor_leaves_exactly_one_candidate_and_reports_no_exploration():
    """At the top floor there is nothing to explore, so exploring must be False.

    Reported honestly rather than left as whatever the epsilon draw said: a
    log line claiming exploration when only one action was permitted would
    misrepresent why the device fired what it fired.
    """
    tier, exploring = select_tier(
        2, {}, ALWAYS_EXPLORES, random.Random(0), floor=Tier.TIER_3
    )
    assert tier is Tier.TIER_3
    assert exploring is False


# ---------------------------------------------------------------------------
# select_tier - exploration branch
# ---------------------------------------------------------------------------


def test_exploration_can_choose_against_the_learned_best():
    """With epsilon 1.0 the chosen tier comes from the RNG, not from the values.

    Seed 1's first random() draw is below 1.0 (every draw is), so the
    exploration branch runs; the assertion is that the result is a genuine
    candidate and that the flag reports exploration, not that it equals one
    specific tier - which would encode CPython's Mersenne Twister stream
    into the test.
    """
    values = {(0, Tier.TIER_1): 0.99}
    tier, exploring = select_tier(0, values, ALWAYS_EXPLORES, random.Random(1))
    assert exploring is True
    assert tier in (Tier.TIER_1, Tier.TIER_2, Tier.TIER_3)


def test_exploration_never_selects_below_the_floor():
    """Exploration is bounded by the floor - habituation is not overridable by chance.

    Swept across many seeds because a single seed proves nothing about a
    branch whose whole job is to pick unpredictably.
    """
    for seed in range(200):
        tier, exploring = select_tier(
            1, {}, ALWAYS_EXPLORES, random.Random(seed), floor=Tier.TIER_2
        )
        assert exploring is True
        assert tier >= Tier.TIER_2


def test_exploration_actually_reaches_more_than_one_tier():
    """Assert the exploration branch is not degenerate.

    Without this, an implementation that always returned candidates[0] from
    the epsilon branch would satisfy every other exploration assertion here.
    """
    seen = {select_tier(0, {}, ALWAYS_EXPLORES, random.Random(seed))[0] for seed in range(50)}
    assert len(seen) > 1


def test_zero_epsilon_never_explores_across_many_seeds():
    """An epsilon of 0.0 must be deterministic regardless of the RNG's state."""
    for seed in range(50):
        _, exploring = select_tier(0, {}, NEVER_EXPLORES, random.Random(seed))
        assert exploring is False


def test_epsilon_outside_the_unit_interval_is_rejected():
    """An epsilon above 1.0 or below 0.0 is not a probability and must raise."""
    for bad in (-0.1, 1.1):
        params = BanditParams(
            epsilon=bad,
            step_size=0.2,
            habituation_window_s=600.0,
            tier_floor_by_context=(Tier.TIER_1,),
            reward_horizon_s=1000.0,
        )
        with pytest.raises(ValueError):
            select_tier(0, {}, params, random.Random(0))


# ---------------------------------------------------------------------------
# proxy_reward
# ---------------------------------------------------------------------------


def test_reward_is_the_fraction_of_the_horizon_that_stayed_quiet():
    """250s of quiet against a 1000s horizon is a quarter of a success."""
    assert proxy_reward(250.0, 1000.0) == pytest.approx(0.25)


def test_reward_saturates_at_the_horizon():
    """Quiet beyond the horizon earns 1.0, never more - the reward is bounded."""
    assert proxy_reward(1000.0, 1000.0) == pytest.approx(1.0)
    assert proxy_reward(9999.0, 1000.0) == pytest.approx(1.0)


def test_immediate_return_scores_zero():
    """An animal back instantly earned the response no credit at all."""
    assert proxy_reward(0.0, 1000.0) == 0.0


def test_negative_gap_scores_zero_rather_than_raising():
    """A backwards clock must score 0.0, not crash the event handler.

    Wall-clock timestamps can step backwards (NTP correction on a board that
    just regained connectivity), and the resulting negative gap is a clock
    artifact, not an event worth losing the handler over.
    """
    assert proxy_reward(-30.0, 1000.0) == 0.0


def test_non_positive_horizon_is_rejected():
    """A zero or negative horizon would divide by zero or invert the scale."""
    for bad in (0.0, -1.0):
        with pytest.raises(ValueError):
            proxy_reward(100.0, bad)


# ---------------------------------------------------------------------------
# updated_value
# ---------------------------------------------------------------------------


def test_update_moves_a_fraction_of_the_way_toward_the_reward():
    """From 0.0, a reward of 1.0 at alpha 0.2 lands on exactly 0.2."""
    assert updated_value(0.0, 1.0, 0.2) == pytest.approx(0.2)


def test_repeated_updates_converge_toward_the_reward():
    """A second identical reward takes 0.2 to 0.36, hand-computed.

    0.2 + 0.2 * (1.0 - 0.2) = 0.2 + 0.16 = 0.36. Asserting the sequence
    rather than one step is what shows the estimate converging on the reward
    instead of jumping to it or drifting past it.
    """
    first = updated_value(0.0, 1.0, 0.2)
    assert updated_value(first, 1.0, 0.2) == pytest.approx(0.36)


def test_update_moves_downward_on_a_poor_reward():
    """A zero reward pulls a learned value back down, not just up.

    0.5 + 0.2 * (0.0 - 0.5) = 0.4. This is habituation showing up in the
    numbers: a tier that used to buy quiet and no longer does must lose
    value.
    """
    assert updated_value(0.5, 0.0, 0.2) == pytest.approx(0.4)


def test_full_step_size_discards_all_prior_experience():
    """An alpha of 1.0 means the value becomes the latest reward exactly."""
    assert updated_value(0.9, 0.25, 1.0) == pytest.approx(0.25)


def test_update_is_a_no_op_when_the_reward_matches_the_stored_value():
    """No surprise, no movement - the error term is zero."""
    assert updated_value(0.42, 0.42, 0.2) == pytest.approx(0.42)


def test_step_size_outside_its_open_interval_is_rejected():
    """Alpha must be in (0.0, 1.0]: 0.0 never learns, above 1.0 overshoots."""
    for bad in (0.0, -0.1, 1.1):
        with pytest.raises(ValueError):
            updated_value(0.0, 1.0, bad)
