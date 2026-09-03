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

import dataclasses
import random

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
# purposes (ADR 0017 Decision A).
#
# 4500 s (75 min). The order of magnitude is set by real data: "Elephants in
# the neighborhood" (PeerJ, 2020, https://peerj.com/articles/9399/) measured
# Asian-elephant crop-raiding duration directly - mean 308 min, range 15 min
# to 15 h (docs/research/elephant-deterrence-behavioral-science.md 3.1). A
# raid lasts hours, and an elephant feeding or investigating between the
# movements that trip a footfall trigger is routinely quiet for longer than
# the old 600 s window, which then reset the repeat-count bucket to 0 mid-
# raid and handed the animal the gentlest tier again - the exact failure
# escalation_floor() exists to prevent.
#
# The specific minute value inside the reasoned 60-90 min band (ADR 0017) is
# an engineering judgement, not a cited figure: long enough to span the
# within-raid quiet gaps the 2020 data implies, short enough that a given
# night's herd is not conflated with a separate visit hours later. The old
# "20x HORN_COOLDOWN_MS" justification is kept alive only as a sanity floor -
# 75 min clears it by two orders of magnitude - not as the primary basis.
HABITUATION_WINDOW_S = 4500.0

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
# 13500 s (225 min) is three times HABITUATION_WINDOW_S, which is the
# property that matters: a gap long enough to score full marks is
# necessarily long enough that the next trigger starts from context 0
# again. Anything shorter would let an attempt earn a perfect reward while
# the animal is still inside the window that calls it a repeat - the reward
# and the context would then be telling contradictory stories about the
# same event. This value is not independently tuned; it is defined as
# 3x HABITUATION_WINDOW_S and must be recomputed whenever that changes
# (ADR 0017 Decision A, "Required companion change").
PROXY_REWARD_HORIZON_S = 13500.0

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
# The honest reading of the whole gain column as of ADR 0015: the DFPlayer
# volume path is now wired in firmware (horn.cpp maps gain_pct -> AT+VOL over
# a software UART), but that UART itself is UNVERIFIED on the Zephyr-based
# MCU core (docs/KNOWN_GAPS.md, ADR 0015 Decision A) - so until bring-up
# confirms it, gain still changes nothing audible in practice. What ADR 0015
# does change is that loudness is no longer the only horn escalation axis:
# the track_id column below makes *what* the horn plays a tier axis too.
TIER_1_GAIN_FRACTION = 0.25
TIER_2_GAIN_FRACTION = 0.45
TIER_3_GAIN_FRACTION = 1.0

# ---------------------------------------------------------------------------
# Horn content library (ADR 0016) - which sound category each tier plays
# ---------------------------------------------------------------------------

# ADR 0016's four deterrence-sound categories. The horn's deterrence value is
# in *what* it plays as much as how loud: a bee swarm and a tiger growl are
# different aversive stimuli, not two volumes of one. Each category name maps
# to the DFPlayer file indices (AT+PLAYNUM / drive_horn's track_id) that hold
# that content on the DFR0768's 128 MB onboard flash (no SD card - files are
# copied over its USB-C port).
HORN_CATEGORY_BEE = "bee_swarm"
HORN_CATEGORY_PREDATOR = "predator_growl"
HORN_CATEGORY_AIR_HORN = "air_horn"
HORN_CATEGORY_FIRECRACKER = "firecracker"

# DFPlayer file index per category. AT+PLAYNUM indexes files by the order they
# were copied onto the module's onboard flash, not by any number in the
# filename, so the tracks are loaded one at a time in this exact order at
# provisioning and the mapping is re-checked at bring-up (the MCU-side
# docs/specs/mcu-fire-test-harness.md owns that checklist). The indices here
# then cannot drift from the files on the module.
# Every track is sourced and license-verified in ADR 0016 Decision C:
#   1  bee swarm   "Intense Angry Bee Swarm"  (Freesound 788025, CC0)
#   2  tiger roar  "tiger roar"               (Freesound 149190, CC-BY 4.0)
#   3  lion roar   "Lion Roar"                (Freesound 212764, CC-BY 3.0)
#   4  air horn    "airhorn.wav"              (Freesound 64476,  CC0)
#   5  firecracker "Firecracker_01.wav"       (Freesound 101130, CC-BY 4.0)
# Attribution is required on any public / contest / DFO-facing material for
# the three CC-BY tracks (2, 3, 5) - see ADR 0016 Decision C and
# docs/research/elephant-deterrence-behavioral-science.md.
#
# The evidence is not equal across categories, and the ladder below reflects
# that: predator growl has the strongest published support (Thuppil & Coss
# 2016, tiger playback 90-100% retreat), bee swarm the next (King et al.
# 2007), firecracker/bang rests on live-pyrotechnic precedent (not
# recordings), and the air horn/siren has a published *null* result (Hedges &
# Gunaryadi 2010) - it stays in the library only as rotation variety at
# non-household sites, never as a primary choice.
HORN_CONTENT_LIBRARY = {
    HORN_CATEGORY_BEE: (1,),
    HORN_CATEGORY_PREDATOR: (2, 3),
    HORN_CATEGORY_AIR_HORN: (4,),
    HORN_CATEGORY_FIRECRACKER: (5,),
}

# Tier 3 at a NON-household site rotates the two "loud artificial bang"
# options so neither becomes predictable, weighted 2:1 toward the
# firecracker: ADR 0016 Decision B says prefer firecracker over the
# air horn/siren when both are eligible, because the siren has that null
# result and the firecracker at least has live-pyrotechnic precedent. The
# pool is drawn with rng.choice, so listing track 5 twice is the weighting.
# A household-proximity node NEVER reaches this pool - see
# resolve_tier_action().
TIER_3_NON_HOUSEHOLD_TRACK_POOL = (
    HORN_CONTENT_LIBRARY[HORN_CATEGORY_FIRECRACKER][0],
    HORN_CONTENT_LIBRARY[HORN_CATEGORY_FIRECRACKER][0],
    HORN_CONTENT_LIBRARY[HORN_CATEGORY_AIR_HORN][0],
)

# Durations are identical across all three tiers, which is a real limitation
# stated plainly rather than a value nobody tuned. Duration is not usable as
# an MPU-side escalation axis under the no-cap-duplication rule: the MCU
# clamps to HORN_BURST_MAX_MS, so every fraction of the uint16 ceiling above
# a few percent produces the same physical burst, and choosing a fraction
# that did separate the tiers would require encoding the cap this module is
# not allowed to know. Requesting the protocol max preserves exactly the
# pre-ladder behaviour and leaves the clamp as the single authority.
TIER_DURATION_MS = PROTOCOL_DURATION_MS_MAX

# LED gain per tier, as fractions of the protocol range (ADR 0014, revised
# by ADR 0014 E.3).
#
# Every tier fires the light at full output. The deterrence value of the
# strobe is in the flashing itself, not in a graded brightness ramp, and a
# dimmed strobe on an unconfirmed-but-real detection just wastes the one
# unambiguous signal the device has - by the time seismic/acoustic fusion
# has cleared the alert gate there is an animal there, and the light should
# be at the level that actually deters it. Escalation is carried entirely by
# wing count, pattern character, and (top rung only) strobe rate - see
# DETERRENCE_TIERS. This is the opposite of the horn column above, which
# keeps a graded ramp because HORN_GAIN_MAX_PCT is a hearing-safety cap and
# a full-volume horn on every trigger near homes is not defensible; the
# light has no equivalent bystander-harm ceiling.
#
# All three map through gain_to_duty() to full PWM duty on the wing MOSFET.
# LED_GAIN_MAX_PCT (device/mcu/src/config.h) is 100.0f, so the request is
# exactly the clamp, not over it - tests/test_cognition_config.py checks
# that equality holds on both sides.
LED_TIER_1_GAIN_FRACTION = 1.0
LED_TIER_2_GAIN_FRACTION = 1.0
LED_TIER_3_GAIN_FRACTION = 1.0

# Tier 1 fires no IR at all. Defensible on two independent grounds, which is
# why it is the low tier's distinguishing feature rather than a quieter horn
# alone: least force first on a single unconfirmed trigger (ADR 0003), and
# the IR MOSFET's own thermal budget, whose IR_MIN_INTERVAL_MS exists to
# hold it near a 10% duty cycle - not spending that budget on the
# lowest-confidence event leaves it available for the escalated ones.
#
# LED signature per tier (ADR 0014, revised by ADR 0014 E.2 for real
# dual-wing, then E.3 for max-gain-always). Gain is full on every tier;
# escalation runs on wing count, pattern character, and - top rung only -
# strobe rate. It does NOT run on brightness, and past Tier 2 it does not
# run on anything DFO testimony validates: practitioner input backs strobe
# as a technique, not any specific two-light phase relationship or the 7-vs
# -11 Hz choice (ADR 0014 E.3 "Honest bound"):
#
#   Tier 1 - fast strobe (pattern_id 2), single wing (channel 0), full gain,
#     LED_FAST_STROBE_HZ. One wing, no IR, quietest horn - the mildest
#     response is "one bright strobe," not "a dim one."
#   Tier 2 - sweep (pattern_id 4), BOTH wings (channel 2), full gain,
#     LED_FAST_STROBE_HZ. First real dual-wing: the two wings antiphase at
#     the base rate, adding an apparent-movement cue and doubling emitters.
#   Tier 3 - BOTH wings (channel 2), full gain, LED_STROBE_FAST_HZ, rotating
#     each fire between pulse-both-sync (pattern_id 5, doubled synchronized
#     strobe at the faster rate) and flicker-both-independent (pattern_id 6,
#     two independently-seeded erratic sources - the unpredictability lever,
#     Montgomery et al. 2021). The stored action carries pattern_id 5;
#     resolve_tier_action() picks 5 or 6 per fire so the top tier is never a
#     single fixed "maximum" pattern (ADR 0014 E.2 - a fixed max stimulus is
#     exactly the habituation failure mode the rotation exists to avoid).
#
# Horn content per tier (ADR 0016 Decision B), the axis ADR 0015 added on
# top of the gain column. Like the Tier 3 LED pattern, the stored track_id
# is only a default - resolve_tier_action() picks the live one per fire so
# the horn is never one fixed sound either:
#
#   Tier 1 - bee swarm (track 1). The single mildest aversive sound, no
#     rotation (the category has one track).
#   Tier 2 - predator growl, rotating tiger (2) / lion (3) each fire. The
#     strongest-evidence category (Thuppil & Coss 2016); rotation keeps a
#     persistent animal from learning the exact clip.
#   Tier 3, household-proximity node - predator growl again, same
#     tiger/lion rotation at max volume. NEVER a siren or firecracker near
#     homes (ADR 0016 Decision B): those categories carry a real
#     resident-nuisance cost and, for the siren, no elephant evidence.
#   Tier 3, non-household node - rotates the "loud artificial bang" pool
#     (TIER_3_NON_HOUSEHOLD_TRACK_POOL: firecracker 2:1 over air horn).
DETERRENCE_TIERS = {
    Tier.TIER_1: DeterrenceAction(
        tier=Tier.TIER_1,
        horn_gain_pct=PROTOCOL_GAIN_PCT_MAX * TIER_1_GAIN_FRACTION,
        horn_duration_ms=TIER_DURATION_MS,
        horn_track_id=HORN_CONTENT_LIBRARY[HORN_CATEGORY_BEE][0],
        led_channel_id=0,
        led_pattern_id=2,
        led_gain_pct=PROTOCOL_GAIN_PCT_MAX * LED_TIER_1_GAIN_FRACTION,
        led_duration_ms=TIER_DURATION_MS,
        fire_ir=False,
        ir_duration_ms=TIER_DURATION_MS,
    ),
    Tier.TIER_2: DeterrenceAction(
        tier=Tier.TIER_2,
        horn_gain_pct=PROTOCOL_GAIN_PCT_MAX * TIER_2_GAIN_FRACTION,
        horn_duration_ms=TIER_DURATION_MS,
        horn_track_id=HORN_CONTENT_LIBRARY[HORN_CATEGORY_PREDATOR][0],
        led_channel_id=2,
        led_pattern_id=4,
        led_gain_pct=PROTOCOL_GAIN_PCT_MAX * LED_TIER_2_GAIN_FRACTION,
        led_duration_ms=TIER_DURATION_MS,
        fire_ir=True,
        ir_duration_ms=TIER_DURATION_MS,
    ),
    Tier.TIER_3: DeterrenceAction(
        tier=Tier.TIER_3,
        horn_gain_pct=PROTOCOL_GAIN_PCT_MAX * TIER_3_GAIN_FRACTION,
        horn_duration_ms=TIER_DURATION_MS,
        # Stored default = predator primary (the household-safe choice).
        # resolve_tier_action() always replaces this for Tier 3, household
        # or not - same as it always replaces led_pattern_id here.
        horn_track_id=HORN_CONTENT_LIBRARY[HORN_CATEGORY_PREDATOR][0],
        led_channel_id=2,
        led_pattern_id=5,
        led_gain_pct=PROTOCOL_GAIN_PCT_MAX * LED_TIER_3_GAIN_FRACTION,
        led_duration_ms=TIER_DURATION_MS,
        fire_ir=True,
        ir_duration_ms=TIER_DURATION_MS,
    ),
}

# Tier 3 rotates its LED pattern every fire between these two, both at full
# gain on both wings (ADR 0014 E.2). 5 = pulse-both-sync (doubled
# synchronized strobe, the most literal reading of the DFO input); 6 =
# flicker-both-independent (two independently-seeded erratic sources, maximum
# unpredictability per Montgomery et al. 2021). The slot's whole purpose is
# being the least predictable, highest-output rung - firing one fixed pattern
# here every time is the fast-habituation failure mode Goodyear & Schulte
# 2015 / Khorozyan & Waltert 2019 describe, so this must not collapse to one.
TIER_3_LED_PATTERN_IDS = (5, 6)

# ---------------------------------------------------------------------------
# Boar horn content (ADR 0023) - reuses Elephant's predator-growl tracks
# ---------------------------------------------------------------------------
#
# No new audio, no SCHEMA_VERSION bump: both indices already exist in
# HORN_CONTENT_LIBRARY[HORN_CATEGORY_PREDATOR] and are already provisioned
# on the DFPlayer's onboard flash. Boar's ladder has one fewer content axis
# than Elephant's, deliberately, on two independent grounds:
#
#   - No bee-swarm track on any Boar tier. King et al. 2007's documented
#     aversion is bees stinging around the eyes and trunk - there is no
#     boar analogue, so Tier 1 cannot reuse Elephant's mildest track and
#     instead gets the milder of the two predator-growl clips.
#   - No firecracker/air-horn "bang" pool at Tier 3 either. Every Boar tier
#     stays inside the predator-growl category, which is also why the
#     household-proximity gate (never a bang near homes, ADR 0016 Decision
#     B) is satisfied trivially for Boar rather than needing its own
#     branch: there is no non-predator pool for it to gate.
#
# Fixed, not rotated, unlike Elephant's Tier 2/3 (which alternate tiger/lion
# specifically to keep a persistent animal from learning one clip): Boar's
# two tiers already carry the escalation on which track plays, lion at the
# lower tier and tiger at the higher ones, so collapsing that further into
# a per-fire draw would blur the one content axis this ladder has left.
#
# The evidence: Widen et al. 2022 (Agriculture, Ecosystems and Environment
# 328:107853) found camera-trap-triggered predator-vocalization playback
# reduced crop damage across five ungulate species including wild boar -
# but its stimuli were wolf howl, dog bark and human voice, not tiger or
# lion. Reusing Elephant's tracks 2/3 here rests partly on a separate,
# ecological argument (tiger/leopard are real Sus scrofa predators on the
# Indian subcontinent - multiple India/Nepal tiger-reserve diet studies put
# wild boar at 7-16% of tiger biomass intake) and partly on a second, more
# direct study found and read this session: Ani (2025) 15(7):1017 tested
# actual Amur tiger call playback against actual wild boar in Hunchun,
# China, and measured it working (~26.5 days before efficacy declined,
# combined with boar distress calls) - the ecological argument now has a
# real predator-call-on-boar number behind it, not just an inference. That
# same study is also the light-vs-sound comparison ADR 0023 discusses in
# full, including the paradigm mismatch that keeps it from being read as
# a simple "light beats sound" verdict for this device.
BOAR_TIER_1_TRACK_ID = HORN_CONTENT_LIBRARY[HORN_CATEGORY_PREDATOR][1]  # lion, track 3
BOAR_TIER_2_3_TRACK_ID = HORN_CONTENT_LIBRARY[HORN_CATEGORY_PREDATOR][0]  # tiger, track 2
BOAR_TIER_1_TRACK_ID = HORN_CONTENT_LIBRARY[HORN_CATEGORY_PREDATOR][1]  # lion, track 3
BOAR_TIER_2_3_TRACK_ID = HORN_CONTENT_LIBRARY[HORN_CATEGORY_PREDATOR][0]  # tiger, track 2


def resolve_tier_action(
    tier: Tier,
    rng: random.Random,
    household_proximity: bool = False,
    species: str = "Elephant",
) -> DeterrenceAction:
    """Return the DeterrenceAction to fire for `tier`.

    `species` defaults to "Elephant" - the byte-for-byte-unchanged default
    behaviour every call site had before ADR 0023, and the only species this
    system was designed for until then. For "Elephant" (or any other
    unrecognised value - never raises on a typo any more than
    services.config.deterrence_scope_labels() does), tier resolution is
    exactly what it always was:

    Tier 1 is fixed - this returns the exact DETERRENCE_TIERS object, so
    identity checks against it still hold. Tiers 2 and 3 return a fresh
    object every call because they rotate content per fire (ADR 0014 E.2 for
    the Tier 3 LED pattern, ADR 0016 Decision B for the horn track):

      Tier 2 - horn_track_id drawn from the predator-growl category
        (tiger/lion).
      Tier 3 - led_pattern_id drawn from TIER_3_LED_PATTERN_IDS, and
        horn_track_id drawn from the predator-growl category when
        `household_proximity` is True, or from
        TIER_3_NON_HOUSEHOLD_TRACK_POOL (firecracker-weighted bang) when it
        is False.

    For "Boar" (ADR 0023, only reachable once NODE_DETERRENCE_SCOPE admits
    Boar - see services.config.deterrence_scope_labels()): horn_track_id is
    BOAR_TIER_1_TRACK_ID (lion) at Tier 1, BOAR_TIER_2_3_TRACK_ID (tiger) at
    Tiers 2 and 3, fixed rather than drawn - see that constant's own
    comment for why. `household_proximity` still gates the Tier 3
    led_pattern_id draw exactly as it does for Elephant; it has no separate
    horn-pool branch for Boar because Boar never leaves the predator-growl
    category in the first place.

    Every draw is off the same RNG the bandit's exploration draw already
    uses, so no new seeding path is introduced. Everything else in each
    action (wings, gain, durations, IR) is unchanged, for either species.

    `household_proximity` defaults to False - the elephant-safe,
    resident-worst-case default, matching services.config.NODE_HOUSEHOLD_
    PROXIMITY's own default. The imperative shell (services/reflex_loop.py)
    passes the real per-node value; only Tier 3 reads it.
    """
    base = DETERRENCE_TIERS[tier]
    if species == "Boar":
        if tier is Tier.TIER_1:
            return dataclasses.replace(base, horn_track_id=BOAR_TIER_1_TRACK_ID)
        if tier is Tier.TIER_2:
            return dataclasses.replace(base, horn_track_id=BOAR_TIER_2_3_TRACK_ID)
        return dataclasses.replace(
            base,
            led_pattern_id=rng.choice(TIER_3_LED_PATTERN_IDS),
            horn_track_id=BOAR_TIER_2_3_TRACK_ID,
        )
    if tier is Tier.TIER_1:
        return base
    if tier is Tier.TIER_2:
        predator = HORN_CONTENT_LIBRARY[HORN_CATEGORY_PREDATOR]
        return dataclasses.replace(base, horn_track_id=rng.choice(predator))
    horn_pool = (
        HORN_CONTENT_LIBRARY[HORN_CATEGORY_PREDATOR]
        if household_proximity
        else TIER_3_NON_HOUSEHOLD_TRACK_POOL
    )
    return dataclasses.replace(
        base,
        led_pattern_id=rng.choice(TIER_3_LED_PATTERN_IDS),
        horn_track_id=rng.choice(horn_pool),
    )

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
