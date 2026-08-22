"""Contextual-bandit deterrence policy - pure functions over plain numbers.

CONTEXT.md 4 freezes "contextual-bandit deterrence (never-repeat,
stop-on-retreat) -> SQLite experience" as the policy layer above fusion.
This module is the "never-repeat" half of that: which deterrence tier to
fire, chosen epsilon-greedily from per-context action values, with repeat
triggers close together forcing escalation so a habituating animal does not
get the same response twice.

"stop-on-retreat" is NOT implemented and is not implementable today - it
needs a signal that the animal actually left, and nothing on this device
produces one (see proxy_reward()'s own docstring and docs/KNOWN_GAPS.md).

Zero SQLite, zero Bridge calls, zero logging inside any function body here,
matching the functional-core discipline ENGINEERING_CONVENTIONS.md 2 names
for this module specifically ("the bandit's action-value update ... write and
test every one of them as a function that takes numbers and returns
numbers"). Persistence is cognition/experience.py's job; the imperative
shell is services/reflex_loop.py. The RNG is injected rather than taken from
the module-level `random` singleton, for the same reason fuse() takes
FusionParams explicitly: a policy whose behaviour depends on hidden global
state cannot be tested for the exact selection it makes.

Like cognition/fusion.py, this module holds no tuning values. The tier
ladder and every hyperparameter live in cognition/config.py, which imports
this module for its types - never the reverse, which would be circular.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum


class Tier(IntEnum):
    """Escalation level of one deterrence response, lowest force first.

    IntEnum rather than Enum because the ordering is load-bearing: an
    escalation floor is expressed as "no tier below this one," which is a
    comparison, not a set membership test.
    """

    TIER_1 = 1
    TIER_2 = 2
    TIER_3 = 3


@dataclass(frozen=True)
class DeterrenceAction:
    """One fully-specified deterrence response, in Bridge wire terms.

    Every field is exactly what services/reflex_loop.py passes to
    drive_horn/drive_led/pulse_ir - no unit conversion or clamping happens
    between here and the wire. The MCU's rule_gate_apply() remains the sole
    authority on what actually fires (device/mcu/src/rule_gate.cpp); nothing
    in this dataclass is a safety limit and it must not be read as one.

    Attributes:
        tier: Which escalation level this action represents.
        horn_gain_pct: drive_horn's gain_pct, 0-100 on the wire.
        horn_duration_ms: drive_horn's duration_ms, uint16 on the wire.
        led_pattern_id: drive_led's pattern_id. 0 and 1 are the only values
            the MCU maps to distinct channels today (white/blue,
            device/mcu/src/bridge_handlers.cpp's
            led_channel_for_pattern_id), and that mapping is itself flagged
            INVENTED there.
        led_duration_ms: drive_led's duration_ms.
        fire_ir: Whether to call pulse_ir at all for this tier. False on the
            lowest tier - see cognition/config.py's ladder comment for the
            two independent reasons.
        ir_duration_ms: pulse_ir's duration_ms. Ignored when fire_ir is
            False; still carried so the dataclass describes one complete
            action rather than a partially-valid one.
    """

    tier: Tier
    horn_gain_pct: float
    horn_duration_ms: int
    led_pattern_id: int
    led_duration_ms: int
    fire_ir: bool
    ir_duration_ms: int


@dataclass(frozen=True)
class BanditParams:
    """Every tuning value select_tier/proxy_reward/updated_value need.

    Taken as a required argument with no default, exactly like
    cognition/fusion.FusionParams and for the same two reasons: a default
    here would need to import cognition/config.py (circular), and every one
    of these numbers is currently INVENTED, so burying one as a default
    would hide it from the one place that documents it as invented.

    Attributes:
        epsilon: Probability of exploring instead of taking the current
            best-valued tier. Must lie in [0.0, 1.0].
        step_size: Constant learning rate alpha in updated_value().
        habituation_window_s: How far back a trigger still counts as a
            "repeat" for context purposes. Consumed by the experience
            store's own trigger query, not by this module.
        tier_floor_by_context: Minimum tier per context bucket, indexed by
            context. This is the habituation-avoidance mechanism - see
            escalation_floor().
        reward_horizon_s: Quiet time at which proxy_reward() saturates to
            1.0.
    """

    epsilon: float
    step_size: float
    habituation_window_s: float
    tier_floor_by_context: tuple[Tier, ...]
    reward_horizon_s: float


def habituation_context(repeat_count: int, bucket_count: int) -> int:
    """Bucket a recent-repeat-trigger count into the bandit's context index.

    This bucket IS the "contextual" part of the contextual bandit: action
    values are learned per context, so "what worked on a first trigger" and
    "what worked on a third trigger in ten minutes" are separate estimates
    rather than one average that blurs them together.

    Repeat count is used rather than any of the richer signals available
    (time of day, battery, sta_lta_ratio, the 8-element feature_vector)
    because it is the only one this repo can currently justify: it is
    measured directly from real event arrivals, needs no threshold nobody
    has data for, and is exactly the "repeat-trigger history" gap
    docs/KNOWN_GAPS.md names. Adding unvalidated context dimensions would
    also split the experience table's counts across more cells than a
    single field trial could ever fill.

    Never blocks; pure integer arithmetic.

    Args:
        repeat_count: Triggers seen within habituation_window_s BEFORE this
            one. Negative values are treated as 0.
        bucket_count: How many context buckets exist. The top bucket
            saturates, so a 4th, 5th and 20th repeat all share it.

    Returns:
        A context index in [0, bucket_count - 1].

    Raises:
        ValueError: If bucket_count is below 1.
    """
    if bucket_count < 1:
        raise ValueError(f"bucket_count must be at least 1, got {bucket_count!r}")
    return min(max(repeat_count, 0), bucket_count - 1)


def escalation_floor(context: int, params: BanditParams) -> Tier:
    """Lowest tier the bandit is allowed to pick in this context.

    The habituation-avoidance mechanism, and deliberately a hard rule rather
    than something the bandit is left to learn. An animal that keeps
    returning within minutes has demonstrably not been deterred by whatever
    just fired; waiting for epsilon-greedy exploration to stumble onto a
    higher tier would repeat the ineffective response an unbounded number of
    times first. The floor makes escalation deterministic and testable, and
    leaves the bandit to learn only the part it can honestly learn - which
    tier to prefer among those still permitted.

    Escalation is one-directional by construction: the floor only ever
    raises the minimum. De-escalation happens naturally by the repeat count
    aging out of habituation_window_s, not by any separate decay rule.

    Never blocks; pure lookup.

    Args:
        context: Index from habituation_context().
        params: Supplies tier_floor_by_context.

    Returns:
        The minimum Tier permitted. Contexts past the end of the configured
        tuple saturate at its last entry.

    Raises:
        ValueError: If params.tier_floor_by_context is empty.
    """
    floors = params.tier_floor_by_context
    if not floors:
        raise ValueError("params.tier_floor_by_context must not be empty")
    return floors[min(max(context, 0), len(floors) - 1)]


def select_tier(
    context: int,
    action_values: Mapping[tuple[int, Tier], float],
    params: BanditParams,
    rng: random.Random,
    floor: Tier = Tier.TIER_1,
) -> tuple[Tier, bool]:
    """Pick a tier epsilon-greedily from the tiers at or above the floor.

    Ties go to the LOWEST tier, which is a deliberate policy rule and not
    incidental max() behaviour. It matters constantly rather than rarely:
    an unvisited (context, tier) pair has no stored value, so on a cold
    store every tier ties at 0.0 and this rule alone decides the first
    response. Least force first is the reading ADR 0003's animal-welfare
    framing supports, and it means the device's untrained behaviour is its
    gentlest, not its loudest.

    The cost of that choice, stated plainly: with all values equal the
    greedy branch never tries a higher tier on its own, so tiers 2 and 3 are
    reached only via the escalation floor or via epsilon exploration. That
    is the intended division of labour - the floor handles the case that
    actually matters (a returning animal), exploration handles the rest.

    Never blocks; draws at most two values from rng.

    Args:
        context: Index from habituation_context().
        action_values: Learned value per (context, tier). A missing key is
            an unvisited pair and reads as 0.0 - the same "no evidence"
            starting point every tier begins from, not an optimistic
            initialisation that would force exploration of every arm.
        params: Supplies epsilon.
        rng: Injected random.Random. Seed it in tests for exact selections.
        floor: Lowest permitted tier, from escalation_floor().

    Returns:
        (tier, exploring) - exploring is True only when the epsilon branch
        actually chose among two or more candidates, so a caller logging it
        never reports exploration that had no alternative to pick from.

    Raises:
        ValueError: If params.epsilon is outside [0.0, 1.0].
    """
    if not (0.0 <= params.epsilon <= 1.0):
        raise ValueError(f"epsilon must be within [0.0, 1.0], got {params.epsilon!r}")

    candidates = [tier for tier in Tier if tier >= floor]
    if len(candidates) == 1:
        return candidates[0], False

    if rng.random() < params.epsilon:
        return rng.choice(candidates), True

    best = candidates[0]
    best_value = action_values.get((context, best), 0.0)
    for tier in candidates[1:]:
        value = action_values.get((context, tier), 0.0)
        if value > best_value:
            best = tier
            best_value = value
    return best, False


def proxy_reward(gap_s: float, horizon_s: float) -> float:
    """Score a fired deterrence by how long it stayed quiet afterwards.

    **This is an unvalidated proxy, not a measured outcome.** It has never
    been checked against real elephant behaviour, because nothing on this
    device observes elephant behaviour: there is no retreat detector, no
    post-event tracking, and no field labels. What it actually measures is
    time until the next seismic trigger at this node - which is a weak and
    knowingly confounded stand-in for "the deterrence worked."

    The confounds are real and none of them are corrected for: an animal
    that leaves for its own reasons scores identically to one that was
    driven off; an animal driven onto a neighbouring node's ground scores as
    a success here while being a failure for the herd; and rain, wind or a
    quiet night all produce long silences with no deterrence involved at
    all. Treat a learned action value as "what preceded quiet at this node,"
    never as "what works on elephants." docs/KNOWN_GAPS.md carries this as
    an open item; closing it needs animal-outcome feedback this project does
    not have.

    Linear-to-saturation rather than anything smoother because there is no
    data to justify a curve shape - the same reasoning cognition/config.py
    uses for keeping its three baselines equal instead of inventing per-
    modality precision.

    Never blocks; pure arithmetic.

    Args:
        gap_s: Seconds between the fired deterrence and the next trigger.
            Zero or negative (a clock step, or two events sharing a
            timestamp) scores 0.0 rather than raising - this runs on the
            event path and must not crash it over a clock artifact.
        horizon_s: Quiet duration counted as a full success. Must be
            positive.

    Returns:
        A reward in [0.0, 1.0].

    Raises:
        ValueError: If horizon_s is not positive.
    """
    if not horizon_s > 0.0:
        raise ValueError(f"horizon_s must be positive, got {horizon_s!r}")
    if gap_s <= 0.0:
        return 0.0
    return min(gap_s, horizon_s) / horizon_s


def updated_value(old_value: float, reward: float, step_size: float) -> float:
    """Move a stored action value toward one observed reward.

    Constant-step incremental update `v + alpha * (r - v)`, deliberately not
    the sample average `v + (r - v) / n` that a stationary bandit would use.
    Habituation is precisely a non-stationary problem: the whole premise of
    this module is that what worked on an animal stops working on it. A
    sample average keeps weighting the first few events forever and would
    take longest to react exactly when reacting matters. A constant alpha
    keeps an exponentially-decaying window on recent experience instead.

    Never blocks; pure arithmetic.

    Args:
        old_value: Current stored value, or 0.0 for an unvisited pair.
        reward: Observed reward, from proxy_reward().
        step_size: Learning rate alpha, in (0.0, 1.0]. 1.0 means "trust only
            the most recent event."

    Returns:
        The updated value.

    Raises:
        ValueError: If step_size is outside (0.0, 1.0].
    """
    if not (0.0 < step_size <= 1.0):
        raise ValueError(f"step_size must be within (0.0, 1.0], got {step_size!r}")
    return old_value + step_size * (reward - old_value)
