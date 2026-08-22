"""Weighted log-odds sensor fusion - pure function, no hardware calls.

`L = L_prior + sum(a_i * w_i * (l_i - l0_i))`, `P = sigmoid(L)` (CONTEXT.md
4). Takes each modality's log-odds contribution and an explicit
availability flag per modality; returns the fused log-odds and probability.
Zero ADC calls, zero Bridge calls, zero SQLite, zero logging inside the
function body - matching the functional-core discipline already established
by device/mcu/src/footfall/sta_lta.cpp and device/mcu/src/actuators/
rule_gate.cpp (ENGINEERING_CONVENTIONS.md 2). The fused P now has a real
consumer - services/reflex_loop.py calls decide() on it and cognition/
bandit.py selects a deterrence tier once it alerts - but the inputs are
still partly synthetic: the vision detector, geophone feature extraction,
and acoustic classifier that would produce real l_i values, plus the Bridge
wiring that would deliver them here, remain future build calls
(device/mpu/README.md's Layout table).

Availability-gated dropout (docs/decisions/0001-physical-ai-sensing-and-
fusion-architecture.md 6, addendum): a modality with `available=False` is
excluded from the sum entirely - it contributes no term, not a zeroed one.
This is implemented literally as "skip this modality in the loop," never as
"treat its log-odds as 0.0," because 0.0 is itself a legitimate log-odds
value a modality can genuinely report (see test_fusion.py's
unavailable-vs-genuine-zero case). Dropout does not renormalise the
remaining weights - a two-of-three-modalities fusion is not rescaled to
behave as if the missing modality's weight were redistributed to the
survivors, since that would silently inflate confidence in whatever data
happens to still be available.

Two known limitations, carried here from ADR 0001 6 so a reader of this
module sees them without also opening the ADR:

- **Conditional independence across modalities is assumed, not verified.**
  This formula is Bayesian log-odds updating under the assumption that each
  modality's evidence is independent given the true state. That assumption
  breaks when a shared confound affects multiple modalities at once - heavy
  rain or fog degrading both seismic SNR (mud dampens ground coupling) and
  vision IR contrast simultaneously is the concrete case ADR 0001 names. In
  that scenario this formula overstates fused confidence, because it treats
  two degraded-but-correlated readings as if they were two independent
  pieces of evidence. No correction is implemented; this is a documented,
  accepted approximation for launch, not a solved problem.
- **Availability-gated dropout is only statistically neutral under MCAR**
  (missingness uncorrelated with the true event). That is a convenient
  assumption, not a proven one, here: vision can be specifically unavailable
  because of the same fog/rain that also plausibly correlates with elephant
  movement patterns. Dropout is kept anyway (CONTEXT.md 7: "simplicity over
  complexity," and it is the most auditable behaviour), but a caller must
  not treat "a modality dropped out" as evidence-neutral in every real
  scenario - it is neutral only under this unverified assumption.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum


class Modality(str, Enum):
    """Sensing modalities this fusion function knows about.

    str-Enum, not enum.StrEnum, matching bridge/rpc.py's AcousticClass -
    that choice was made there specifically to avoid a Python 3.11-only
    construct (device/mpu/pyproject.toml's own rationale), and this module
    inherits the same constraint since it must stay importable on the same
    unverified-version board Python (docs/KNOWN_GAPS.md).
    """

    SEISMIC = "seismic"
    ACOUSTIC = "acoustic"
    VISION = "vision"


@dataclass(frozen=True)
class ModalityReading:
    """One modality's evidence for a single fusion call.

    Attributes:
        modality: Which sensing modality this reading is from.
        log_odds: l_i, that modality's own log-odds contribution (e.g. logit
            of a classifier's reported confidence). Must be finite -
            NaN/inf is rejected by fuse(), see its own docstring for why.
            Ignored (but still validated as finite) when available=False.
        available: a_i. Explicit flag for whether this modality produced
            usable evidence for this event at all. Never inferred from
            log_odds == 0.0 - a modality can genuinely report zero log-odds
            (fusion.py module docstring); this flag is the only channel
            for "this sensor had nothing to say."
    """

    modality: Modality
    log_odds: float
    available: bool


@dataclass(frozen=True)
class FusionParams:
    """Tuning constants one fuse() call runs against.

    Attributes:
        l_prior: L_prior - fused log-odds when no modality contributes
            anything (all unavailable, or an empty reading list).
        weights: w_i per modality. Every Modality that could appear in a
            fuse() call's readings must have an entry here, or fuse()
            raises ValueError - a missing weight is a config bug, not a
            field condition to degrade gracefully around.
        baselines: l0_i per modality, same completeness requirement as
            weights.
    """

    l_prior: float
    weights: Mapping[Modality, float]
    baselines: Mapping[Modality, float]


@dataclass(frozen=True)
class FusionResult:
    """Output of one fuse() call.

    Attributes:
        log_odds: L, the fused log-odds.
        probability: P = sigmoid(L).
        contributions: a_i * w_i * (l_i - l0_i) for each modality that was
            available, keyed by Modality. A dropped modality has no key
            here at all - not a key mapped to 0.0 - so a caller can tell
            "contributed zero net evidence" (a real, present entry that
            happens to equal 0.0) apart from "was excluded" by checking key
            membership, not value. Exists for explainability (CONTEXT.md 4
            names this as fusion's advantage over an opaque combiner), not
            just as a debugging aid.
        used: Modalities that entered the sum, in the order given to
            fuse().
        dropped: Modalities excluded by the availability gate, in the order
            given to fuse().
    """

    log_odds: float
    probability: float
    contributions: Mapping[Modality, float]
    used: tuple[Modality, ...]
    dropped: tuple[Modality, ...]


def sigmoid(log_odds: float) -> float:
    """Convert log-odds to a probability via the logistic function.

    Two-branch form (rather than the textbook single-expression
    1 / (1 + exp(-x))) so a large-magnitude input saturates toward 0.0 or
    1.0 instead of overflowing exp() for very negative L - a fused L can in
    principle grow large if enough modalities agree strongly.

    Args:
        log_odds: L, any finite float.

    Returns:
        A probability in (0.0, 1.0), never exactly 0.0 or 1.0 for a finite
        input (only floating-point saturation at extreme magnitudes reaches
        those exact endpoints).
    """
    if log_odds >= 0:
        return 1.0 / (1.0 + math.exp(-log_odds))
    exp_l = math.exp(log_odds)
    return exp_l / (1.0 + exp_l)


def logit(probability: float) -> float:
    """Convert a probability to log-odds. Inverse of sigmoid().

    Args:
        probability: p, must lie strictly inside (0.0, 1.0).

    Returns:
        log(p / (1 - p)).

    Raises:
        ValueError: If probability is <= 0.0 or >= 1.0 - both endpoints map
            to infinite log-odds, which is not a value this module's
            log_odds fields can represent (fuse() rejects non-finite
            log_odds), so this is a hard reject rather than a saturating
            clamp.
    """
    if not (0.0 < probability < 1.0):
        raise ValueError(
            f"probability must be strictly between 0.0 and 1.0, got {probability!r}"
        )
    return math.log(probability / (1.0 - probability))


def fuse(
    readings: list[ModalityReading],
    params: FusionParams,
) -> FusionResult:
    """Fuse per-modality log-odds evidence into one probability.

    `L = L_prior + sum(a_i * w_i * (l_i - l0_i))`, `P = sigmoid(L)`
    (CONTEXT.md 4). Modalities with available=False are excluded from the
    sum entirely (module docstring's availability-gated dropout section) -
    never scored as l_i=0. An empty `readings` list, or one where every
    reading is unavailable, returns L == params.l_prior unchanged.

    `params` has no default value, deliberately, matching device/mcu/src/
    footfall/sta_lta.h's own stated discipline ("zero config.h dependency
    baked into the signature - the caller reads thresholds out of config.h
    and passes them in"). This keeps fusion.py free of any import of
    cognition/config.py - callers (tests, and the future service loop) pass
    `cognition.config.DEFAULT_FUSION_PARAMS` explicitly.

    Args:
        readings: One ModalityReading per modality with something to
            report this event. Must not contain two readings for the same
            Modality - fusing the same sensor's evidence twice would
            double-count it, which is exactly the independence violation
            ADR 0001 6 already flags as a risk, not something to add to
            deliberately.
        params: Weights, baselines, and prior to fuse against. Every
            Modality present in `readings` must have an entry in both
            params.weights and params.baselines.

    Returns:
        FusionResult with the fused log-odds, probability, and a
        per-modality breakdown of what was used and what was dropped.

    Raises:
        ValueError: If `readings` contains two entries for the same
            Modality; if any reading references a Modality missing from
            params.weights or params.baselines; or if any reading's
            log_odds is NaN or infinite (available or not - a broken
            feature extractor should surface as an exception at its own
            call site, not be silently absorbed here as if it were a
            deliberately-flagged dropout).
    """
    seen: set[Modality] = set()
    for reading in readings:
        if reading.modality in seen:
            raise ValueError(
                f"duplicate reading for modality {reading.modality!r} - "
                "fuse() takes at most one reading per modality"
            )
        seen.add(reading.modality)
        if not math.isfinite(reading.log_odds):
            raise ValueError(
                f"non-finite log_odds for modality {reading.modality!r}: "
                f"{reading.log_odds!r} - use available=False to signal "
                "missing evidence, not a non-finite log_odds"
            )
        if reading.modality not in params.weights or reading.modality not in params.baselines:
            raise ValueError(
                f"modality {reading.modality!r} has no configured weight/"
                "baseline in the given FusionParams"
            )

    log_odds = params.l_prior
    contributions: dict[Modality, float] = {}
    used: list[Modality] = []
    dropped: list[Modality] = []

    for reading in readings:
        if not reading.available:
            dropped.append(reading.modality)
            continue
        weight = params.weights[reading.modality]
        baseline = params.baselines[reading.modality]
        contribution = weight * (reading.log_odds - baseline)
        contributions[reading.modality] = contribution
        log_odds += contribution
        used.append(reading.modality)

    return FusionResult(
        log_odds=log_odds,
        probability=sigmoid(log_odds),
        contributions=contributions,
        used=tuple(used),
        dropped=tuple(dropped),
    )
