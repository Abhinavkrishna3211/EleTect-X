"""Alert decision - pure function turning a fused probability into an action.

`decide()` is the alert gate and nothing more: one probability threshold, no
learning, no per-actuator selection. That is now a deliberate division of
labour rather than a placeholder - cognition/bandit.py owns the rest of what
this docstring used to defer (which actuator(s) to fire, at what
gain/duration, learned from outcomes), and services/reflex_loop.py calls it
only once decide() has already said alert. Keeping the gate separate from
the selection keeps this function pure of any experience state and leaves
the threshold question (below) exactly where it was.

No default threshold lives in this module, for the same reason fuse() takes
FusionParams as a required argument with no default (cognition/fusion.py's
own docstring): cognition/config.py's own comment is explicit that the real
alert threshold needs field-accuracy figures (seismic ~70-75%, vision
~70-85%, ADR 0001's Consequences section) this project doesn't have yet.
Baking a default in here would bury that same invented number one layer
deeper instead of keeping it as one clearly-flagged constant at its one real
call site (services/reflex_loop.ALERT_PROBABILITY_THRESHOLD,
docs/KNOWN_GAPS.md).
"""

from __future__ import annotations

from dataclasses import dataclass

from cognition.fusion import FusionResult


@dataclass(frozen=True)
class Decision:
    """Output of one decide() call.

    Attributes:
        alert: Whether the fused probability cleared the threshold.
        probability: fusion_result.probability, carried through so a caller
            can log/act on it without re-reading the FusionResult.
        threshold: The threshold this decision was made against, carried
            through for the same explainability reason as probability.
    """

    alert: bool
    probability: float
    threshold: float


def decide(fusion_result: FusionResult, threshold: float) -> Decision:
    """Turn a fused probability into a binary alert decision.

    Deliberately the entire decision policy for now: alert if and only if
    fusion_result.probability >= threshold. Does not choose which
    actuator(s) to fire, at what gain, or for how long - that selection is
    the contextual bandit's job once it exists (cognition/fusion.py module
    docstring); services/reflex_loop.py's actuate step fills this gap today
    by driving the horn only and requesting the wire protocol's own maximum,
    trusting the MCU's rule_gate to clamp it, rather than this module
    inventing a second, unreviewed gain/duration policy.

    Args:
        fusion_result: Output of cognition.fusion.fuse().
        threshold: Probability at/above which to alert. No default - the
            caller must pass one explicitly (see module docstring for why).
            Must lie in [0.0, 1.0].

    Returns:
        A Decision carrying the alert flag plus the probability/threshold
        it was computed from.

    Raises:
        ValueError: If threshold is outside [0.0, 1.0].
    """
    if not (0.0 <= threshold <= 1.0):
        raise ValueError(f"threshold must be within [0.0, 1.0], got {threshold!r}")
    return Decision(
        alert=fusion_result.probability >= threshold,
        probability=fusion_result.probability,
        threshold=threshold,
    )
