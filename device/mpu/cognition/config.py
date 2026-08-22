"""Cognition tuning constants: fusion weights, and the bandit's tier ladder.

Single source of every value the log-odds fusion formula
(`L = L_prior + sum(a_i * w_i * (l_i - l0_i))`, CONTEXT.md 4) and the
contextual-bandit deterrence policy need, mirroring the shape of
device/mcu/include/config.h and services/config.py: one rationale comment per
constant, no magic numbers inline in fusion.py or bandit.py
(ENGINEERING_CONVENTIONS.md 2).

This module deliberately holds nothing services/config.py's own docstring
already claims (Bridge timeouts, filesystem paths, camera settings) - the
boundary is that file's own, not repeated here. It equally holds no MCU
actuator cap: services/config.py states that boundary too ("the MPU only ever
sees the clamped ack, never a raw limit to duplicate here"), and it applies
with more force to the tier ladder below than anywhere else, because burst
duration and cooldown are ADR 0003's animal-welfare and battery-draw
safeguard. The ladder is expressed in wire-protocol terms only.

No alert/decision threshold on the fused probability P lives here. The
threshold that turns P into an alert is services/reflex_loop.py's
ALERT_PROBABILITY_THRESHOLD, which is where the whole imperative event path
already lives; ADR 0001's Consequences section is explicit that such a
threshold needs the real field-accuracy figures (seismic ~70-75%, vision
~70-85%) behind it, not an invented number picked before those exist.
Tracked in docs/KNOWN_GAPS.md instead of guessed here. What this module does
now hold is the policy that runs *after* that threshold: which of three
deterrence tiers to fire, and how hard repeat triggers escalate it.
"""

from cognition.bandit import BanditParams, DeterrenceAction, Tier
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

# ---------------------------------------------------------------------------
# Bandit hyperparameters
# ---------------------------------------------------------------------------

# Every constant in this section is INVENTED. Not one of them can be fitted
# today: fitting an exploration rate or a learning rate needs logged
# deterrence outcomes, and cognition/bandit.proxy_reward() is explicit that
# no real outcome signal exists on this device. They are chosen to be
# defensible and conservative, and they are expected to change once the DFO
# field test produces the first real event log. docs/KNOWN_GAPS.md carries
# them as open.

# Exploration rate for select_tier()'s epsilon-greedy branch: roughly one
# event in seven ignores the learned values and picks a random permitted
# tier.
#
# Bounded from below by the event rate, not by the usual RL intuition. A
# node that sees a handful of elephant events a week gathers data far too
# slowly for a textbook 0.01-0.05 to ever escape a bad initial estimate
# within a season. Bounded from above by the fact that exploration here is
# not free the way it is in a simulator - every exploratory pull is a real
# acoustic and light disturbance to a real animal, which ADR 0003's welfare
# framing does not let us treat as a cost of zero. 0.15 sits between those
# two pressures.
BANDIT_EPSILON = 0.15

# Constant learning rate alpha in updated_value(). 0.2 means one observed
# reward moves a stored value a fifth of the way toward it, and experience
# older than roughly a dozen events has almost no weight left.
#
# Deliberately fast for a bandit, because habituation is the entire premise:
# a value that was true a month ago is evidence about an animal that has
# since learned to ignore the response. The cost of a high alpha is noisy
# estimates from a noisy reward, which the proxy reward certainly is - so
# not higher than this.
BANDIT_STEP_SIZE = 0.2

# How far back a previous trigger still counts as a "repeat" for context
# purposes.
#
# 600 s (10 min) is the one constant here with a partly-empirical basis: it
# is 20x the MCU's longest actuator cooldown (HORN_COOLDOWN_MS, 30 s), so
# any two triggers that the MCU itself was willing to fire on separately are
# comfortably inside one window and read as the same visit. Long enough that
# an animal circling a node reads as one escalating encounter; short enough
# that this evening's herd is not conflated with last night's.
HABITUATION_WINDOW_S = 600.0

# How many context buckets habituation_context() maps repeat counts into.
# Three, matching the tier count, so each bucket can have a distinct floor
# and the top bucket saturates: a 3rd and a 9th repeat are the same context.
#
# Kept small on purpose. Action values are learned per (context, tier) cell,
# so every extra bucket divides an already-tiny real-world sample further -
# with single-digit events per node per week, more context resolution would
# mean less learning, not more.
HABITUATION_BUCKET_COUNT = 3

# The habituation-avoidance ladder itself: minimum tier permitted in each
# context. First trigger may use any tier; a second trigger inside the
# window may not go below tier 2; a third or later may not go below tier 3.
#
# A hard rule rather than something the bandit learns, because an animal
# that has come back has demonstrably not been deterred by whatever just
# fired, and waiting for epsilon-greedy to stumble onto a stronger response
# would repeat the ineffective one an unbounded number of times first. The
# bandit still chooses freely among the tiers at or above the floor.
TIER_FLOOR_BY_CONTEXT = (Tier.TIER_1, Tier.TIER_2, Tier.TIER_3)

# Quiet time at which proxy_reward() saturates to a full 1.0.
#
# 1800 s (30 min) is three times HABITUATION_WINDOW_S, which is the property
# that matters: a gap long enough to score full marks is necessarily long
# enough that the next trigger starts from context 0 again. Anything shorter
# would let an attempt earn a perfect reward while the animal is still
# inside the window that calls it a repeat - the reward and the context
# would then be telling contradictory stories about the same event.
PROXY_REWARD_HORIZON_S = 1800.0

# ---------------------------------------------------------------------------
# Deterrence tier ladder
# ---------------------------------------------------------------------------

# The two constants below are wire-protocol limits from bridge/schema.md
# (drive_horn's `gain_pct: float (0-100)` and the `uint16` on every
# duration_ms field), NOT MCU actuator caps. The distinction is the whole
# reason this ladder can live on the MPU at all: a protocol range is a fixed
# property of the message format both sides already agree on, whereas
# HORN_GAIN_MAX_PCT / HORN_BURST_MAX_MS are safety limits owned solely by
# device/mcu/src/rule_gate.cpp, and services/config.py rules out duplicating
# those here.
PROTOCOL_GAIN_PCT_MAX = 100.0
PROTOCOL_DURATION_MS_MAX = 65535

# Horn gain per tier, as fractions of the protocol range.
#
# Not even thirds. The MCU clamps gain to HORN_GAIN_MAX_PCT, currently
# around 60% of protocol scale, so a naive 33/66/100 split would put tiers 2
# and 3 both above the clamp and collapse them into physically identical
# output - three tiers on paper, two in the field. 0.25 and 0.45 land
# clearly below the currently-observed clamp; tier 3 requests the protocol
# max, which is exactly what every alert requested before this ladder
# existed.
#
# These fractions were chosen empirically against that currently-observed
# clamp and must be re-checked if it moves. That obligation is enforced in
# the test layer, not here: tests/test_cognition_config.py reads
# HORN_GAIN_MAX_PCT out of device/mcu/src/config.h and fails if tiers 1-2
# stop landing below it - the same cross-boundary drift check
# tests/test_config.py already does for BRIDGE_CALL_TIMEOUT_S. That keeps
# the MPU's production code free of the MCU's number while still failing
# loudly when the assumption behind these fractions expires.
#
# The honest reading of the whole gain column: it has no physical effect
# today. The DFPlayer volume path is unwired (docs/KNOWN_GAPS.md), so gain
# reaches the MCU and changes nothing audible. The tiers are currently
# distinguished by actuator count and LED channel, not loudness.
TIER_1_GAIN_FRACTION = 0.25
TIER_2_GAIN_FRACTION = 0.45
TIER_3_GAIN_FRACTION = 1.0

# Durations are identical across all three tiers, which is a real limitation
# stated plainly rather than a value nobody tuned. Duration is not usable as
# an MPU-side escalation axis under the no-cap-duplication rule: the MCU
# clamps to HORN_BURST_MAX_MS, so every fraction of the uint16 ceiling above
# a few percent produces the same physical burst, and choosing a fraction
# that did separate the tiers would require encoding the cap this module is
# not allowed to know. Requesting the protocol max preserves exactly the
# pre-ladder behaviour and leaves the clamp as the single authority.
TIER_DURATION_MS = PROTOCOL_DURATION_MS_MAX

# Tier 1 fires no IR at all. Defensible on two independent grounds, which is
# why it is the low tier's distinguishing feature rather than a quieter horn
# alone: least force first on a single unconfirmed trigger (ADR 0003), and
# the IR MOSFET's own thermal budget, whose IR_MIN_INTERVAL_MS exists to
# hold it near a 10% duty cycle - not spending that budget on the
# lowest-confidence event leaves it available for the escalated ones.
#
# LED channel: tier 2 switches to blue (pattern_id 1) purely because it is
# the only other channel the MCU maps today, giving the middle tier a
# visibly distinct response. Tier 3 returns to white (pattern_id 0) because
# tier 3 is defined as exactly the pre-ladder behaviour. Both pattern_id
# values are placeholders - device/mcu/src/bridge_handlers.h flags the
# whole mapping INVENTED pending real pattern design.
DETERRENCE_TIERS = {
    Tier.TIER_1: DeterrenceAction(
        tier=Tier.TIER_1,
        horn_gain_pct=PROTOCOL_GAIN_PCT_MAX * TIER_1_GAIN_FRACTION,
        horn_duration_ms=TIER_DURATION_MS,
        led_pattern_id=0,
        led_duration_ms=TIER_DURATION_MS,
        fire_ir=False,
        ir_duration_ms=TIER_DURATION_MS,
    ),
    Tier.TIER_2: DeterrenceAction(
        tier=Tier.TIER_2,
        horn_gain_pct=PROTOCOL_GAIN_PCT_MAX * TIER_2_GAIN_FRACTION,
        horn_duration_ms=TIER_DURATION_MS,
        led_pattern_id=1,
        led_duration_ms=TIER_DURATION_MS,
        fire_ir=True,
        ir_duration_ms=TIER_DURATION_MS,
    ),
    Tier.TIER_3: DeterrenceAction(
        tier=Tier.TIER_3,
        horn_gain_pct=PROTOCOL_GAIN_PCT_MAX * TIER_3_GAIN_FRACTION,
        horn_duration_ms=TIER_DURATION_MS,
        led_pattern_id=0,
        led_duration_ms=TIER_DURATION_MS,
        fire_ir=True,
        ir_duration_ms=TIER_DURATION_MS,
    ),
}

# Assembled here rather than defaulted inside bandit.py, for the same reason
# DEFAULT_FUSION_PARAMS is: bandit.py must not import this module (circular),
# and a hyperparameter buried as a function default would be a hyperparameter
# whose INVENTED status nothing documents.
DEFAULT_BANDIT_PARAMS = BanditParams(
    epsilon=BANDIT_EPSILON,
    step_size=BANDIT_STEP_SIZE,
    habituation_window_s=HABITUATION_WINDOW_S,
    tier_floor_by_context=TIER_FLOOR_BY_CONTEXT,
    reward_horizon_s=PROXY_REWARD_HORIZON_S,
)
