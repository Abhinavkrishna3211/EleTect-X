"""Fusion tuning constants: weights, per-modality baselines, and the prior.

Single source of every value the log-odds fusion formula
(`L = L_prior + sum(a_i * w_i * (l_i - l0_i))`, CONTEXT.md 4) needs, mirroring
the shape of device/mcu/include/config.h and services/config.py: one
rationale comment per constant, no magic numbers inline in fusion.py
(ENGINEERING_CONVENTIONS.md 2).

This module deliberately holds nothing services/config.py's own docstring
already claims (Bridge timeouts, filesystem paths, camera settings) - the
boundary is that file's own, not repeated here.

No alert/decision threshold on the fused probability P lives here. Nothing
in cognition/ consumes P into an action yet (the contextual bandit and alert
escalation are both future build calls), and ADR 0001's Consequences section
is explicit that such a threshold needs the real field-accuracy figures
(seismic ~70-75%, vision ~70-85%) behind it, not an invented number picked
before those exist. Tracked in docs/KNOWN_GAPS.md instead of guessed here.
"""

from cognition.fusion import FusionParams, Modality

# ---------------------------------------------------------------------------
# Prior
# ---------------------------------------------------------------------------

# L_prior is conditioned on cognition already having been woken by an MCU
# event (CONTEXT.md 4: cognition is event-only) - it is the log-odds of
# "elephant" given only "something crossed the on-MCU trigger gate," not the
# unconditional base rate of an elephant being present at any given moment.
#
# INVENTED - no measured trigger-to-elephant rate exists yet (nothing has
# been fielded). -1.0 (P = sigmoid(-1.0) ~= 0.269) encodes the honest
# expectation that most STA/LTA crossings at a forest edge are wind, cattle,
# or a passing vehicle, not an elephant - a single weak modality should not
# be able to push a fused P past 0.5 unaided. This is the concrete form of
# ADR 0001's own point that fusion, not any single modality, has to carry
# the reliability requirement.
#
# The documented alternative is 0.0 (P = 0.5, uninformative) - the condition
# under which ADR 0001 6 says this log-odds formula is provably equivalent
# to Dempster-Shafer. -1.0 was chosen over 0.0 because "no evidence at all"
# reading as a coin flip does not match the trigger-gate's real false-alarm
# rate, even unmeasured. FusionParams.l_prior stays a caller-settable field
# (not baked into fuse()'s signature) precisely so a test, or a future
# per-site self-calibration pass (CONTEXT.md 4's "site-noise
# self-calibration"), can override this default without editing this file.
L_PRIOR = -1.0

# ---------------------------------------------------------------------------
# Fusion weights (a_i)
# ---------------------------------------------------------------------------

# Ordering (vision > seismic > acoustic) is derivable from this repo, even
# though the magnitudes below are not:
# - ADR 0001's Consequences section: seismic-alone field accuracy ~70-75%,
#   vision-alone precision/recall ~70-85% - vision's expected standalone
#   reliability is the higher of the two primary modalities.
# - ADR 0007/0009 scope acoustic strictly as >60 Hz corroboration (gunshot/
#   chainsaw anti-poaching signal and a corroborating cue above the
#   geophone's own low-frequency band), never a standalone presence
#   detector, and the acoustic subsystem itself is sequenced after the DFO
#   field test (docs/decisions/0009 addendum) - the weakest, least-relied-on
#   evidence source of the three.
#
# Magnitudes themselves are INVENTED - no labelled multi-modal field dataset
# exists to fit them against (ADR 0001 Alternatives: "needs a labeled
# multi-modal field dataset that doesn't exist yet," listed as a v2 upgrade,
# not a launch requirement). Chosen as round numbers that preserve the
# justified ordering, not as a fitted result. See docs/KNOWN_GAPS.md.
WEIGHT_VISION = 1.5
WEIGHT_SEISMIC = 1.2
WEIGHT_ACOUSTIC = 0.6

# ---------------------------------------------------------------------------
# Per-modality baselines (l0_i)
# ---------------------------------------------------------------------------

# Each baseline is the modality's own log-odds on a quiescent/background
# observation - logit(p_background) - not the value it reports on an actual
# elephant. Deliberately equal across all three modalities and deliberately
# non-zero: no per-modality background false-positive rate has been measured
# (bench stomp-test data exists for seismic only, and even that has not been
# calibrated against this formula - docs/KNOWN_GAPS.md), so differentiating
# these three numbers would be false precision the data doesn't support. A
# non-zero baseline is also what makes "modality unavailable" (excluded from
# the sum entirely) and "modality reported a genuine 0.0 log-odds" (a real,
# scored contribution of w_i * (0 - l0_i)) numerically distinct outcomes at
# all - a 0.0 baseline would make that distinction vanish for exactly the
# zero-log-odds case, undermining the whole point of the explicit
# availability flag (ADR 0001 6's dropout addendum).
#
# INVENTED, p_background = 0.10 (BASELINE = logit(0.10) ~= -2.197) for all
# three - a low but non-negligible background rate, not a measured one.
# This module does not import cognition.fusion.logit to compute this value
# at runtime (fusion.py imports this module for its defaults; the reverse
# import would be circular) - the literal below is logit(0.10) computed by
# hand and stated as such. tests/test_cognition_config.py asserts
# sigmoid(BASELINE_*) reproduces 0.10, tying the literal back to this
# derivation without the circular import.
BASELINE_SEISMIC = -2.197
BASELINE_ACOUSTIC = -2.197
BASELINE_VISION = -2.197

# ---------------------------------------------------------------------------
# Assembled defaults
# ---------------------------------------------------------------------------

# Built here, not hand-duplicated in fusion.py, per
# ENGINEERING_CONVENTIONS.md 7 ("don't hand-copy the same formula/data
# twice"). fusion.fuse()'s own default argument imports this.
DEFAULT_WEIGHTS = {
    Modality.SEISMIC: WEIGHT_SEISMIC,
    Modality.ACOUSTIC: WEIGHT_ACOUSTIC,
    Modality.VISION: WEIGHT_VISION,
}

DEFAULT_BASELINES = {
    Modality.SEISMIC: BASELINE_SEISMIC,
    Modality.ACOUSTIC: BASELINE_ACOUSTIC,
    Modality.VISION: BASELINE_VISION,
}

# fusion.fuse() takes params as a required argument with no default
# (fusion.py's own docstring explains why: matching sta_lta.h's "caller
# passes thresholds in" discipline, and avoiding a circular import back into
# this module). This is what a caller passes when it wants the values
# documented above rather than a test fixture or a future per-site
# calibration override.
DEFAULT_FUSION_PARAMS = FusionParams(
    l_prior=L_PRIOR,
    weights=DEFAULT_WEIGHTS,
    baselines=DEFAULT_BASELINES,
)
