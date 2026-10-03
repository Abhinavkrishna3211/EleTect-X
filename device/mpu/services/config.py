"""MPU-side configuration constants.

Single source of every Bridge timeout, retry policy, and filesystem path the
cognition layer depends on (ENGINEERING_CONVENTIONS.md 2), mirroring the
shape of device/mcu/src/config.h: one rationale comment per constant, no
magic numbers inline in logic files.

Two things this file deliberately does NOT hold:
- Actuator burst caps, cooldowns and gain ceilings. Those are enforced
  on-MCU (device/mcu/src/config.h) and the MPU only ever sees the
  clamped ack, never a raw limit to duplicate here
  (device/mpu/bridge/schema.md).
- Fusion weights, bandit hyperparameters, and risk thresholds. Those live in
  cognition/config.py, not in this bridge-facing config.

Camera device path, resolution, and pixel format DO belong here even though
they're perception/-facing, not bridge-facing - they're device-configuration
constants in the same sense as the MCU's pin assignments (config.h), not
tuning knobs for cognition math.
"""

import dataclasses
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bridge RPC schema
# ---------------------------------------------------------------------------

# Every Bridge payload's first field (device/mpu/bridge/schema.md). Bump on
# any breaking field change; never reuse a version number.
#
# 1 -> 2 on 2026-09-01 (ADR 0014): drive_led's wire args changed from
# (pattern_id, duration_ms) to (channel, pattern_id, gain_pct, duration_ms) -
# `channel` split out as its own field, `gain_pct` added, `pattern_id`
# restored to meaning "which flash pattern".
#
# 2 -> 3 on 2026-09-01 (ADR 0014 E): drive_led's `channel` value 2 now means
# "both wings, driven together in one blocking call" (was "unrecognized ->
# left"), and `pattern_id` gains 4 = sweep, 5 = pulse both sync, 6 = flicker
# both independent. No field added or removed, but the changed meaning of an
# in-range value is a breaking change. Mirrors device/mcu/src/config.h's
# BRIDGE_SCHEMA_VERSION; both sides must bump together.
#
# 3 -> 4 on 2026-09-02 (ADR 0015): drive_horn gains a trailing `track_id`
# (uint8) field - the DFPlayer content index (AT+PLAYNUM) for this tier's
# sound category, so the horn escalates on *what* it plays, not only how
# loud. A real new wire field, so it bumps the version.
#
# 4 -> 128 on 2026-09-09: no wire-shape change, value change only. The
# on-device MsgPack library (0.4.2, Arduino_RPClite's Unpacker.h) mis-detects
# positive-fixint-encoded values (0-127) as the wrong type for a uint8_t
# parameter - schema_version was always sent in that range, so every
# actuator RPC call failed at deserialization regardless of everything else
# being correct (bench-verified: value 200 unpacked fine, 0 and 1 did not).
# 128 stays a valid uint8_t but forces the explicit uint8 msgpack format,
# which unpacks correctly on this library version. Mirrors
# device/mcu/src/config.h's BRIDGE_SCHEMA_VERSION; both sides must bump
# together.
SCHEMA_VERSION = 128

# ---------------------------------------------------------------------------
# Node site attributes (set at commissioning, not sensed)
# ---------------------------------------------------------------------------

# True if this node is sited close enough to permanently-occupied homes that
# the deterrence ladder must never play a siren or firecracker/bang track at
# it - those categories carry a real nuisance/startle cost to residents and,
# for the siren, a published null result against elephants anyway (Hedges &
# Gunaryadi 2010). ADR 0016 Decision A/B: household proximity is orthogonal
# to habituation context (repeat-count governs *how hard* to escalate; this
# governs *which* content categories are eligible). A household-proximity
# node's tier 3 escalates on volume, LED and predator-growl variety, not on
# a new "louder artificial bang" category.
#
# Per-node value: overridden per deployment at commissioning time. False here
# is the safe-for-elephants, worst-case-for-residents default - a node with
# this left at False near homes would be allowed to fire the firecracker
# track, so every real near-home node MUST have this set True during
# commissioning. Not auto-detected: nothing on the device knows where it is.
#
# Read from the environment first, same pattern as reflex_loop.py's
# SAFE_MODE and for the same reason: python/ is bind-mounted into the
# container as /app (HANDOVER.md), so ELETECT_HOUSEHOLD_PROXIMITY is not
# actually deliverable through App Lab's regenerated compose file today -
# this is an interim path for ADR 0021 to absorb, not the audited config
# interface it specifies. The proven one-minute flip on a live node is
# still editing this module constant directly and restarting the app.
NODE_HOUSEHOLD_PROXIMITY = os.environ.get("ELETECT_HOUSEHOLD_PROXIMITY", "0") != "0"

# Which species this node deters and films. Three states, no auto-detected
# fourth: "elephant_only" (the field-trial default), "boar_only", "both".
# A commissioning-time site attribute exactly like NODE_HOUSEHOLD_PROXIMITY
# just above, not sensed or inferred - see deterrence_scope_labels() below
# for what each state resolves to, and EXPERIENCE_DB_PATH just below for
# why this has to be defined up here rather than down with the label
# constants it derives.
#
# Same env-first, constant-second delivery path as NODE_HOUSEHOLD_PROXIMITY,
# for the same reason. The value is either an explicit label list -
# "Elephant,Boar,Fox" - or one of the legacy aliases; parse_scope_labels()
# below owns the vocabulary. Unrecognized values fall back to
# "elephant_only" and never raise, since a typo in a per-node environment
# variable must not crash the reflex loop on a field node.
#
# 8 Sept: briefly hardcoded to "boar_only" for one night's field test, then
# reverted to the container's own env once both species were wanted again.
# Recorded because the detour's premise was wrong and should not be retried:
# it was meant to exclude the honeybee track, which scope narrowing does not
# reach. That track is Tier-1-only for Elephant (DETERRENCE_TIERS /
# resolve_tier_action) and Boar's ladder never selects it either (ADR 0023),
# so the tier configuration is what governs it, not the deterrence scope.
NODE_DETERRENCE_SCOPE = os.environ.get("ELETECT_DETERRENCE_SCOPE", "elephant_only")

@dataclasses.dataclass(frozen=True)
class Species:
    """Everything the pipeline needs to know about one deterrable species.

    Attributes:
        label: The vision model's class name, and this species' identity
            everywhere else - scope strings, the detector, the experience
            store, the log.
        event_class: The LoRaWAN wire code, comms.lora_uplink.EventClass.
            Held as a plain int so this module stays import-free; the enum
            owns the number, and lora_uplink turns it back into an
            EventClass at import, which fails loudly if the two disagree.
        bandit_policy: Whose escalation ladder and action values this
            species spends. Defaults to `label` - its own - because a
            species that quietly shares another's ladder inherits its
            habituation, and that is the defect ADR 0034 exists to fix.
        deterrence_content: Whose horn track and LED pattern pool it
            fires. Separate from bandit_policy on purpose: what you play
            at an animal and what you learn from playing it are different
            questions, and Fox is the case that proves it.
        alert_audience: Who a confirmed detection reaches beyond the
            dashboard, which shows everything. Declarative only - the
            device never reads it, because the fan-out happens in
            web/backend. It lives here so that adding a species is one
            entry rather than one entry plus a cloud change nobody
            remembers. tests/test_species_registry.py checks the value
            against the closed vocabulary the routing table uses and
            against the audience map in send-alert's message.ts, so the
            two cannot disagree without a test failing. The backend keeps
            its own map rather than importing this one - it runs in Deno
            and cannot read Python - but it is no longer free to differ
            from it.
    """

    label: str
    event_class: int
    bandit_policy: str = ""
    deterrence_content: str = ""
    alert_audience: str = "dashboard_only"
    # -- body plan (ADR 0035, perception/kinematics.py) --------------------
    #
    # Nominal adult figures from the literature, not measurements of the
    # animals at this site, and the records say so: every derived range
    # carries `calibrated` and every derived behaviour carries the raw
    # measurement it came from, so all three of these can be re-chosen
    # later without recapturing anything.
    #
    # shoulder_height_m is the only one that scales absolute range, and it
    # is why absolute range is quoted at +-30-50%: an elephant calf and a
    # bull differ by more than a factor of two and the detector reports one
    # label for both. The *relative* range trajectory does not use it at
    # all - the unknown height cancels - which is why that is the number
    # the retreat decision is allowed to rest on.
    shoulder_height_m: float = 0.0
    # One stride, nose-to-tail gait cycle ignored: cadence x stride is the
    # seismic speed estimate that cross-checks the vision one.
    stride_length_m: float = 0.0
    # Above this the animal is running rather than walking. Deliberately
    # per species: 1.5 m/s is a brisk walk for an elephant and a sprint for
    # nothing else on this list.
    walk_speed_max_mps: float = 0.0

    def __post_init__(self) -> None:
        """Fill the alias keys a table entry left blank with the label."""
        # Identity defaults, applied here rather than at each call site so
        # a new entry gets its own bandit case automatically, and sharing
        # another species' ladder or content stays a visible, deliberate
        # line in the table below.
        if not self.bandit_policy:
            object.__setattr__(self, "bandit_policy", self.label)
        if not self.deterrence_content:
            object.__setattr__(self, "deterrence_content", self.label)


# Every species this hardware may be pointed at, and what each one implies.
# Adding a species is one entry here, plus its wire code in the three files
# that carry the byte format (device/mcu/src/uplink.h,
# device/mpu/comms/lora_uplink.py, web/ingest/src/payload.ts). Those stay a
# deliberate manual addition because a wire code must be appended in
# lockstep and never renumbered; tests/test_species_registry.py fails if
# this table and any of the three drift apart.
#
# This is also the safety bound on ELETECT_DETERRENCE_SCOPE, not a default:
# a scope naming a label that is not a key here has that label dropped with
# a warning. Commissioning a node stays an environment variable while "what
# may this hardware be pointed at" stays a reviewed source change - a typo,
# or a deployment recipe copied from a site with different species, must
# not be able to aim a horn at a class nobody decided to deter.
#
# Acoustic classes are deliberately absent and must stay absent. gunshot
# and chainsaw route straight to forest officers and are never answered
# with a horn (ADR 0007 5); elephant_call corroborates vision and does not
# actuate on its own. Deterrence is a vision-confirmed decision - see
# DETERRENT_REQUIRES_VISION_CONFIRMATION below.
SPECIES_REGISTRY: dict[str, Species] = {
    species.label: species
    for species in (
        Species(
            label="Elephant",
            event_class=1,
            alert_audience="residents",
            shoulder_height_m=2.7,
            stride_length_m=1.6,
            walk_speed_max_mps=1.8,
        ),
        Species(
            label="Boar",
            event_class=2,
            shoulder_height_m=0.8,
            stride_length_m=0.6,
            walk_speed_max_mps=1.2,
        ),
        # Fox keeps its own bandit_policy - the default - so that a night
        # of foxes cannot walk the elephant ladder up, which is the whole
        # point of partitioning it. It borrows Boar's content because the
        # horn tracks and LED patterns were chosen for a mid-sized mammal
        # and there is no fox-specific evidence to choose differently;
        # ADR 0023 makes the same ecological-inference argument for
        # reusing tiger/lion on Boar. Until the vision model had a Fox
        # class it labelled foxes "Boar", so this is also the content
        # those arms were actually learned on.
        Species(
            label="Fox",
            event_class=6,
            deterrence_content="Boar",
            shoulder_height_m=0.38,
            stride_length_m=0.4,
            walk_speed_max_mps=1.0,
        ),
    )
}

# Registry keys, in table order. Kept as its own name because it is the
# vocabulary every scope string is validated against, and it reads better
# at the call sites that only care about which labels exist.
DETERRABLE_LABELS = tuple(SPECIES_REGISTRY)


def bandit_policy_for(label: str) -> str:
    """Which species' escalation ladder and action values `label` spends.

    An unknown label returns itself rather than raising. A label that
    reached the bandit without being in the registry is already a bug
    upstream, and partitioning it under its own name at least keeps it
    from spending a real species' ladder while that bug is found.
    """
    species = SPECIES_REGISTRY.get(label)
    return species.bandit_policy if species is not None else label


def deterrence_content_for(label: str) -> str:
    """Whose horn track and LED pattern pool `label` fires.

    An unknown label falls back to "Elephant" - the only content set with
    a published evidence base behind it (Thuppil & Coss 2016), and this
    device's first purpose. Never raises, for the reason
    parse_scope_labels() gives: nothing on this path may crash a field
    node.
    """
    species = SPECIES_REGISTRY.get(label)
    return species.deterrence_content if species is not None else "Elephant"


def event_class_for(label: str) -> int:
    """`label`'s LoRaWAN wire code, or 0 (unconfirmed) if it has none.

    0 is the honest answer for a label this build cannot name: the
    detection still happened and still belongs on the dashboard, but
    reporting it as a species would put a name in front of a ranger that
    nothing on this node stands behind.
    """
    species = SPECIES_REGISTRY.get(label)
    return species.event_class if species is not None else 0


# Aliases for the three scope strings that predate free-form scopes. Kept so
# existing per-node configuration, the experience-DB filenames derived from
# it, and the tests that name these strings all keep resolving to exactly
# what they resolved to before. "all" is the whole registry, so a node
# commissioned for every species this build knows does not need its scope
# re-edited when the registry grows. New deployments should prefer the
# explicit label-list form, which says what it does without a lookup.
_SCOPE_ALIASES: dict[str, tuple[str, ...]] = {
    "none": (),
    "elephant_only": ("Elephant",),
    "boar_only": ("Boar",),
    "both": ("Elephant", "Boar"),
    "all": DETERRABLE_LABELS,
}


def parse_scope_labels(scope: str, *, what: str = "deterrence") -> tuple[str, ...]:
    """Resolve one scope string to a tuple of vision labels.

    Accepts either an alias from _SCOPE_ALIASES ("elephant_only", "both",
    "all", "none", ...) or an explicit comma-separated label list, so a new
    species can be commissioned onto a node - ELETECT_DETERRENCE_SCOPE=
    "Elephant,Boar,Fox" - without a source edit. Matching is
    case-insensitive and whitespace-tolerant, because this value is typed
    into a commissioning sheet or a compose file, not generated.

    Defined here, immediately below the registry it validates against and
    above experience_db_filename(), rather than beside
    deterrence_scope_labels() further down. EXPERIENCE_DB_PATH is evaluated
    at import time, and a label-list scope reaches this function through
    experience_db_filename(); defined any later, importing this module
    under exactly the configuration this function exists to support raises
    NameError.

    Never raises. Every rejection path degrades to something safe and says
    so in the log, for the reason the old three-state version gave: a typo
    in a per-node environment variable must not crash the reflex loop on a
    field node.

    - A label outside DETERRABLE_LABELS is dropped with a warning. The
      rest of the list still applies, because dropping one unrecognized
      species is a smaller surprise than silently ignoring an operator's
      whole intent.
    - A scope that resolves to nothing at all - empty, or every label
      dropped - falls back to "elephant_only" rather than to (), matching
      the previous behaviour. Note this is the one case where the safe
      direction is arguable: falling back to () would deter nothing, which
      is safer for the animals and useless for the residents this node
      exists to protect. Keeping the old fallback means a garbled scope
      behaves like a default node, not like a dead one.

    Args:
        scope: The raw scope string, straight off the environment.
        what: Names the scope in log lines, so an operator reading a
            warning can tell which of the two scopes they mistyped.

    Returns:
        The labels in DETERRABLE_LABELS order, deduplicated, so two scopes
        naming the same species in different orders produce the same tuple
        - which matters because this value keys the experience DB.
    """
    raw = scope.strip()
    alias = _SCOPE_ALIASES.get(raw.lower())
    if alias is not None:
        return alias

    by_lower = {label.lower(): label for label in DETERRABLE_LABELS}
    selected: set[str] = set()
    for token in raw.split(","):
        name = token.strip()
        if not name:
            continue
        canonical = by_lower.get(name.lower())
        if canonical is None:
            logger.warning(
                "%s scope names %r, which is not one of DETERRABLE_LABELS %s - dropped",
                what,
                name,
                list(DETERRABLE_LABELS),
            )
            continue
        selected.add(canonical)

    if not selected:
        logger.warning(
            "%s scope %r resolved to no usable label, falling back to 'elephant_only'",
            what,
            scope,
        )
        return _SCOPE_ALIASES["elephant_only"]

    return tuple(label for label in DETERRABLE_LABELS if label in selected)

# ---------------------------------------------------------------------------
# Bridge.call() timeout and retry policy
# ---------------------------------------------------------------------------
# Bridge.call() blocks the caller until a response or timeout
# (ENGINEERING_CONVENTIONS.md 6). These values only apply to the MPU-side
# wrappers (drive_horn, drive_led, pulse_ir, get_system_state) - MCU-side
# notify handlers never block and have no timeout to set.

# drive_* holds the caller for the whole commanded burst: the MCU does not
# ack until the burst finishes, and the deterrence ladder commands the
# uint16 protocol max on every tier (cognition/config.py TIER_DURATION_MS),
# which the MCU then clamps to its own per-actuator cap. So each wrapper
# needs its own timeout set just above *that* actuator's cap plus transport
# overhead - a single shared ceiling (the LED cap + margin) would make a
# hung horn or IR call block the reflex loop several seconds longer than
# that actuator can physically run. The caps are owned by
# device/mcu/src/config.h (HORN_BURST_MAX_MS 3000, LED_BURST_MAX_MS 12_500,
# IR_PULSE_MAX_MS 500); tests/test_config.py fails if any value here stops
# exceeding its cap.
#
# LED_BURST_MAX_MS was raised from 10_000 to 12_500 on 7 September without
# this value moving with it, which left a 12.0s timeout against a 12.5s cap.
# Any tier that clamps led_duration_ms to the full cap - the top tier always
# does - would have raised TimeoutError on a burst that completed normally.
# 14.5s restores the same ~2s transport-overhead margin the horn timeout
# already carries over its own cap.
BRIDGE_HORN_CALL_TIMEOUT_S = 5.0
BRIDGE_LED_CALL_TIMEOUT_S = 14.5
BRIDGE_IR_CALL_TIMEOUT_S = 2.0

# Generic ceiling for non-actuator calls (get_system_state), which read a
# cached struct and return at once. Kept under the historical name, equal to
# the longest actuator timeout, so bridge/rpc.py's docstrings and
# tests/test_config.py's drift check still resolve unchanged.
BRIDGE_CALL_TIMEOUT_S = BRIDGE_LED_CALL_TIMEOUT_S

# drive_horn/drive_led/pulse_ir are not idempotent: a call that times out
# may have already fired the actuator, so retrying risks doubling a burst
# and defeating the MCU's own cooldown gate. Never retried.
BRIDGE_ACTUATOR_CALL_RETRIES = 0

# get_system_state reads a cached struct (device/mpu/bridge/schema.md: "not
# a fresh sensor poll"), so it is idempotent and safe to retry on a
# transport-level timeout.
BRIDGE_STATE_CALL_RETRIES = 2

# ---------------------------------------------------------------------------
# MPU wake/suspend (ADR 0008)
# ---------------------------------------------------------------------------

# How long the MPU stays awake after the last MCU→MPU event notify before
# it is allowed to re-suspend. INVENTED - no measured suspend/resume
# latency or fusion/decision runtime backs this number yet; ADR 0008 lists
# both as open bench items (docs/KNOWN_GAPS.md).
MPU_WAKE_HOLD_S = 30.0

# ---------------------------------------------------------------------------
# Filesystem paths
# ---------------------------------------------------------------------------
# Resolved relative to this module so they land inside the App's own folder
# on the board (ArduinoApps/<app>/python/), not /tmp or a path that only
# exists on a dev laptop.

_MODULE_DIR = Path(__file__).resolve().parent.parent

# SQLite experience store backing the contextual bandit's never-repeat /
# stop-on-retreat learning (CONTEXT.md 4). Opened lazily by
# cognition/experience.py, which creates DATA_DIR on first write; only the
# path is fixed here. Tests and bench/demo_replay.py inject their own path
# (a tmp_path, or cognition.experience.IN_MEMORY_PATH) so neither ever
# writes real learning state.
DATA_DIR = _MODULE_DIR / "data"

# Filename derived from NODE_DETERRENCE_SCOPE, not a fixed name plus a
# separate archive-at-ship step. The bandit's learned action values
# (BANDIT_STEP_SIZE against experience.action_values()) are persisted with
# no decay, so two days of boar-driven fires under "both" durably move the
# tier a node prefers - reverting the scope flag alone would not revert
# what the node learned if the filename never changed. Keying the filename
# on the flag instead collapses that into one action: reverting the flag
# back to "elephant_only" IS what restores the trial's own DB, with no
# separate step whose omission would silently ship a boar-shaped policy
# into the field trial. Named by scope, not by phase ("experience-both",
# not "experience-home") - a name that said "home" would mislead the first
# time "both" got set anywhere else. See docs/qa/boar-gap-session-notes.md
# and TRIAL_READINESS_PLAN.md for the real hazard this still leaves open: a
# mid-trial flip to "both" silently resumes the home-phase DB instead of
# the trial's - main.py logs the resolved path at startup specifically so
# that is never silent.


def experience_db_filename(scope: str) -> str:
    """Resolve a NODE_DETERRENCE_SCOPE value to its experience-store filename.

    A pure function (not just the inline expression below) so the
    derivation is directly testable, the same reason
    deterrence_scope_labels() is its own function rather than inline
    tuples. Deliberately does not reject an unrecognized scope the way
    parse_scope_labels() does - a scope this build cannot resolve still
    gets its own qualified filename here rather than silently falling back
    to "experience.sqlite3", so a typo in NODE_DETERRENCE_SCOPE can never
    point a misconfigured node at the real trial's learned policy.

    Two spellings, deliberately:

    - An alias, or any single bare token, keeps its historical filename
      byte for byte. "both" stays experience-both.sqlite3, so no deployed
      node is repointed at a different - and therefore empty - database by
      scopes having become free-form.
    - A label list keys off the RESOLVED labels, not the raw string.
      "Elephant,Fox" and " fox , ELEPHANT " name the same scope and must
      not learn two separate policies: the whole point of keying the
      filename on the scope is that restoring a scope restores its
      matching DB, which fails if an equivalent spelling opens a different
      file.

    Note what a scope change still costs, because it is easy to read this
    as cost-free: widening "both" to "Elephant,Boar,Fox" opens
    experience-elephant-boar-fox.sqlite3, which is a new and empty
    database. The node keeps its old policy on disk and can get it back by
    restoring the old scope, but it starts the new one cold.
    """
    if scope == "elephant_only":
        return "experience.sqlite3"
    if scope.strip().lower() in _SCOPE_ALIASES or re.fullmatch(r"[A-Za-z0-9_.-]+", scope):
        return f"experience-{scope.strip()}.sqlite3"
    slug = "-".join(label.lower() for label in parse_scope_labels(scope))
    return f"experience-{slug or 'none'}.sqlite3"


EXPERIENCE_DB_PATH = DATA_DIR / experience_db_filename(NODE_DETERRENCE_SCOPE)

# On-device vision model artifacts (Edge Impulse export target).
MODELS_DIR = _MODULE_DIR / "models"

# ---------------------------------------------------------------------------
# Camera (perception/camera.py, IMX462 over USB-UVC)
# ---------------------------------------------------------------------------
# Capture-only constants. No trigger/IR-sync values here - pulse_ir() is an
# MCU-side Bridge call not registered on either side yet
# (device/mpu/bridge/rpc.py), and capture has no business calling it.

# Verified on real hardware 17 Aug 2026 (docs/KNOWN_GAPS.md): a bare index
# is not safe here. /dev/video0 - the previous default - turned out to be
# the QRB2210 SoC's own qcom-venus hardware encoder, not the camera at all;
# the IMX462 actually landed on /dev/video1 that run, but /dev/videoN
# indices reshuffle across reboots and hub reconnects/port changes, so even
# that number isn't trustworthy long-term. Using the udev-assigned by-id
# symlink instead - keyed on the camera's own USB serial (SN0001), not bus
# topology or enumeration order. Confirmed 17 Aug 2026: a full board reboot
# genuinely reshuffled the raw /dev/videoN indices under this camera (it
# held video1/2/4/5 before, video0/1/2/3 after - the SoC's own qcom-venus
# codec and the camera raced differently on the two boots), and a physical
# USB unplug/replug reassigned the bus device number too - the by-id path
# resolved correctly both times with zero code changes. See
# docs/KNOWN_GAPS.md for the full verification.
CAMERA_DEVICE = (
    "/dev/v4l/by-id/usb-Arducam_Technology_Co.__Ltd._USB_2.0_Camera_SN0001-video-index0"
)

# IMX462 is a 2MP sensor; 1920x1080 taken from the product listing
# (B0CQ4QDCXN), not from a queried V4L2 format list on this specific unit.
# UNVERIFIED - bench/camera_check's --probe flag closes this.
CAMERA_FRAME_WIDTH = 1920
CAMERA_FRAME_HEIGHT = 1080

# MJPG, not YUYV: most 1080p UVC webcams only sustain a useful frame rate
# over USB2/3 in MJPG - YUYV's uncompressed bandwidth typically caps near
# 5 fps at this resolution. UNVERIFIED for this specific unit (product
# listing doesn't state it) - bench/camera_check's --probe flag confirms
# which formats this camera actually offers.
CAMERA_PIXEL_FORMAT = "MJPG"

# UVC auto-exposure/AGC needs several frames after stream start before
# output is representative - the first few grabs after open() are commonly
# dark, over-bright, or otherwise unsettled. INVENTED - no AE-settle bench
# data backs this number yet; see docs/KNOWN_GAPS.md.
CAMERA_WARMUP_FRAMES = 3

# Camera.open() retry policy. A transient USB dropout at exactly the moment
# of open() (hub renegotiation, a jostled connector) shouldn't be a hard
# failure if the device comes back within a couple seconds - confirmed
# empirically 17 Aug 2026 that a real unplug/replug of this camera took
# ~8.6s to re-enumerate (dmesg: USB disconnect to new-device back-to-back),
# see docs/KNOWN_GAPS.md. Open (not capture_frame()/capture_burst(), which
# stay non-retrying by design - see their own docstrings) because a device
# that isn't there yet at startup is exactly the case a few spaced attempts
# can ride out.
#
# 20 x 2s (~38s of retry window) rather than a "few": on an unattended field
# deploy the board is cold-booted daily (mains switched off each morning,
# on each night) and the container starts before the USB stack has finished
# enumerating the camera - observed 10 Sept 2026, the container crash-looped
# through three restarts before the Arducam node appeared. A retry window
# that outlasts a cold-boot enumeration keeps that inside one open() call
# instead of costing a container bounce every power-on. INVENTED counts - no
# real-world open-failure-rate data backs these numbers yet.
CAMERA_OPEN_RETRIES = 20
CAMERA_OPEN_RETRY_BACKOFF_S = 2.0

# Default burst size and inter-frame spacing for capture_burst(). 0.0
# interval means "as fast as the device delivers," not a real-time target.
# Both INVENTED - no detector-side timing requirement drives these yet.
CAMERA_BURST_FRAMES = 5
CAMERA_BURST_INTERVAL_S = 0.0

# Extra evidence frames captured after drive_horn()/drive_led() have already
# returned and CAPTURE_POST_FIRE_TAIL_S has already elapsed - reflex_loop.py
# only reaches this capture after every actuator call is done, so widening
# it can never delay the horn (services/reflex_loop.py's own sequencing,
# same guarantee ADR 0020's video tail relies on). handle_footfall_event()
# itself defaults retreat_burst_frames to 0 (a no-op, byte-for-byte the
# pre-existing behaviour) - main.py's _footfall_kwargs is what opts
# production into these values, so every existing test is unaffected unless
# it explicitly asks for this. Deliberately reuses the same JPEG/cv2 path
# as CAMERA_BURST_FRAMES rather than ADR 0020's GStreamer video path - see
# docs/KNOWN_GAPS.md. INVENTED counts, not yet bench-verified against this
# board's real camera: chosen to roughly span an animal's retreat, same
# order of magnitude as EVENT_VIDEO_RETREAT_TAIL_S.
CAMERA_RETREAT_BURST_FRAMES = 45
CAMERA_RETREAT_BURST_INTERVAL_S = 1.0

# ---------------------------------------------------------------------------
# Vision inference (perception/detector.py)
# ---------------------------------------------------------------------------
# The trained .eim artifact runs out-of-process as a standing
# `edge-impulse-linux-runner --run-http-server <port>` HTTP server, not
# embedded via the edge_impulse_linux Python SDK - neither pip nor
# ensurepip exists on this board's Python 3.13.5 image and no sudo
# credential is available to install either (confirmed 28 Aug on the real
# board). See perception/detector.py's own module docstring for the full
# rationale and the live verification against a real image.

# 127.0.0.1, not the LAN address used during the 28 Aug bench verification -
# in production the runner is a same-host companion process to this loop,
# never reachable off-board. Starting/supervising that process
# (boot-persistent, restart-on-crash) is not yet built - tracked in
# docs/KNOWN_GAPS.md, not solved here; main.py assumes it is already
# running by the time an event needs it, and a detect() call against
# nothing listening degrades to VISION unavailable, same as a camera
# failure (perception/detector.py, services/reflex_loop.py).
#
# Env override exists because the App-Lab container runs on a bridge
# network, not the host network namespace: 127.0.0.1 inside the container
# is the container's own loopback, not the host's. The compose deployment
# points this at the docker0 gateway alias instead; bare-host runs (no
# container) keep the default.
VISION_INFERENCE_URL = os.environ.get(
    "ELETECT_VISION_INFERENCE_URL", "http://127.0.0.1:1337"
)

# Per-frame socket timeout for one detect call. Bench-measured
# classification time on the real board was ~20ms (28 Aug, real image over
# the LAN); 2.0s is a generous multiple of that, not a tuned figure -
# INVENTED, the same "bounded deliberately short so a hung call can't hang
# the whole event" reasoning as BRIDGE_CALL_TIMEOUT_S above, just guarding a
# different transport.
VISION_INFERENCE_TIMEOUT_S = 2.0

# Per-class score floor applied to the runner's boxes, on top of the single
# min_score baked into the .eim (perception/detector.py). Empty = every box
# the runner reports is kept, which is the deployed champion's behaviour.
# A candidate tuned with per-class cut-offs (e.g. the 29 Sept 160px run:
# Boar 0.18 / Elephant 0.18 / Fox 0.12, chosen for zero false alarms on the
# 340 field frames - see the 28 Sept vision model training log)
# sets them here when, and only when, that model is promoted.
VISION_MIN_CONFIDENCE_BY_LABEL: dict[str, float] = {}

# How many frames the pre-decision vision check captures, distinct from
# CAMERA_BURST_FRAMES (the larger, IR-lit evidence burst captured only once
# an alert actually fires). INVENTED - a small odd number chosen to give
# the detector more than one chance at a moving animal without adding much
# latency ahead of decide(); no real-world tuning data backs this count
# yet. See docs/KNOWN_GAPS.md.
VISION_CHECK_FRAME_COUNT = 3

# ---------------------------------------------------------------------------
# Vision watch window (ADR 0022, services/reflex_loop.py)
# ---------------------------------------------------------------------------
# A geophone trigger and an elephant in frame are not the same moment, and
# the gap between them is large. The field-validated footfall detection
# range is 140m in natural environments (ADR 0008, Wijayakulasooriya et
# al.), and at a normal walking pace of 1.1-1.7 m/s that leaves 80-140
# seconds between the trigger and the animal reaching the boundary - the
# same arithmetic ADR 0008 used to size the wake budget. The camera sees a
# small fraction of that 140m. So a single VISION_CHECK_FRAME_COUNT burst
# taken two or three seconds after the trigger is, in most of the cases
# that matter, looking at an empty frame and correctly reporting "no
# elephant" about an elephant that is simply still 100m away.
#
# The fix is to keep looking for a bounded window instead of glancing once.
# Two window lengths rather than one, because the cost of watching falls
# almost entirely on the triggers that turn out to be nothing - cattle,
# wind, a vehicle on a nearby track - and those should be paid for cheaply.

# What every trigger gets. Sized to be cheap rather than sufficient: at
# VISION_WATCH_POLL_INTERVAL_S this is roughly eight detection passes
# against the single pass the loop did before, which is a real improvement
# for an animal already inside camera range, without committing the battery
# to a long watch on evidence that has not earned one. INVENTED - no field
# trigger-rate data exists yet to size the false-alarm cost against. Set
# this to 0.0 to restore the pre-ADR-0022 behaviour exactly: the watch
# always runs at least one poll, so a zero window is the old single burst.
VISION_WATCH_BASE_S = 8.0

# What a trigger that has already earned a longer look gets - see
# reflex_loop._watch_length_s for the two qualifying conditions (a repeat
# within the habituation window, or seismic evidence strong enough to clear
# the alert threshold on its own).
#
# 45s is not a guess. ADR 0008 puts the *worst-case* lead time - the same
# 140m covered at an agitated 2.5-3+ m/s rather than a walking pace - at
# 45-65 seconds. Capping the watch at the bottom of that band means the
# fallback fire, the one that happens when the window expires without a
# vision confirmation, still lands before even a fast-moving animal could
# have crossed the geophone's own detection range. A longer window would
# buy more chances at a confirmation and start risking a horn that fires
# after the elephant is already past the thing it was protecting.
VISION_WATCH_EXTENDED_S = 45.0

# Interval between watch polls, measured start-of-poll to start-of-poll.
# Polling flat out instead would give several times the attempts at a target
# that takes tens of seconds to cross a 95-degree field of view
# (hardware/cad/enclosure-design-concept.md) - very little extra recall for
# several times the CPU and the power behind it. INVENTED as a ratio.
#
# The ratio no longer holds, and the number is kept deliberately. It was
# sized against the 30 Aug 96x96 champion's measured 138ms mean per frame,
# where a VISION_CHECK_FRAME_COUNT=3 poll cost ~0.4s and the rest of each
# second went to the H.264 encoder sharing the same four A53 cores. Run F
# (160px int8, deployed 29 Sept) classifies at a measured 374ms, so a 3-frame
# poll is ~1.12s and already overruns this interval: the watch loop is
# inference-bound, polls land every ~1.12s rather than every 1.0s, and the
# encoder no longer gets the slack this value was chosen to leave it. Raising
# it to ~1.5s would restore the original intent at the cost of ~25% fewer
# confirmation attempts per watch window. Not changed here because the trade
# wants a field decision, not an arithmetic one - see ml/vision/README.md's
# last entry.
VISION_WATCH_POLL_INTERVAL_S = 1.0

# Consecutive polls that return no frames at all before the watch gives up
# and lets the event proceed on seismic alone. A camera that has stopped
# delivering is not going to start again inside this window, and holding
# the deterrence sequence behind a dead device is exactly the failure the
# reflex loop's "vision must never block actuation" rule exists to prevent.
# One empty poll is tolerated because a single dropped frame grab is a
# normal USB event (perception/camera.py); three in a row is a fault.
VISION_WATCH_MAX_EMPTY_POLLS = 3

# Consecutive watch polls a species label must appear on, in a row, before
# it is admitted into a VisionWatch's `species` set. Per-label rather than
# global because only Boar has the problem this exists to fix: a live 2-hour
# board run measured a 31.53% per-frame Boar false-positive rate against
# zero Elephant false positives in the same run (ml/vision/README.md's
# "30 Aug - 2-hour live monitoring" entry) - single-poll admission for Boar
# means most of that noise would land in `species` were anything ever gated
# on it. Elephant is not listed and defaults to 1 (see required() in
# reflex_loop.py), so this is a no-op for Elephant: ADR 0022's
# confirm-and-exit latency and the existing watch-mechanics tests are
# unaffected.
#
# This gates entry into `species` only, not `VisionCheck.confirmed` - Boar
# is in neither DETERRENT_TARGET_LABELS nor EVENT_VIDEO_TARGET_LABELS today,
# so nothing currently reads `confirmed` for a Boar detection, and confirmed
# stays byte-for-byte what it always was. A species that later gains an
# entry in either of those two lists must extend the same streak gate to
# its confirmation path too, or a single spurious poll bypasses this
# constant entirely - see services/reflex_loop.py's _watch_for_vision().
#
# Costs +1 poll of latency (VISION_WATCH_POLL_INTERVAL_S, ~1.0s) before Boar
# enters `species`; Elephant costs +0. Measured, not assumed - the real
# before/after false-positive numbers this bought are in
# docs/qa/boar-gap-session-notes.md.
#
# RELAXED - 13 Sept 2026, alongside VISION_SPECIES_BURST_MAJORITY_LABELS
# below, same reason and same revert plan: empty so a fox - which the
# 2-class model of the time labelled "Boar" - admits on the first
# qualifying poll instead of waiting for a second consecutive one.
#
# The premise has since changed and the relaxation has not. The 3-class
# model labels a fox "Fox", so this no longer has anything to do with
# foxes: it is now simply a relaxed admission bar for Boar. That is worth
# knowing before reading the revert note below as still being about foxes.
# It is not a reason to revert.
#
# Originally written as a one-day override. It is not one any more: the
# relaxation is open-ended by the operator's decision and carries no expiry.
# REVERT to {"Boar": 2} only on an explicit request to do so - not because
# a date has passed, and not as tidy-up. Until then the Boar
# false-positive rate this gate was built to hold down (31.53% per-frame,
# measured) is knowingly being accepted.
VISION_SPECIES_CONSECUTIVE_POLLS: dict[str, int] = {}

# Labels that must appear on a strict majority of a burst's
# VISION_CHECK_FRAME_COUNT frames - not merely one of them - before
# _vision_check() (services/reflex_loop.py) admits them into `species` or
# lets them count toward `confirmed`. Per-label, the same shape as
# VISION_SPECIES_CONSECUTIVE_POLLS immediately above, and for the same
# reason: only Boar has the problem this exists to fix.
#
# The replay this constant is built on is in
# docs/qa/boar-gap-session-notes.md. The poll-level, production-faithful
# Boar false-positive rate was 43.64% under this module's original
# flatten-the-burst-and-OR aggregation (a single spurious box on one frame
# of three scored identically to the same box on all three) - *worse* than
# the 31.53% raw-frame rate it was built from, and the
# VISION_SPECIES_CONSECUTIVE_POLLS debounce above barely dented it
# (43.64% -> 40.48%). Requiring a majority within the burst fixed the
# actual mechanism (43.64% -> 30.70% alone, -> 27.54% combined with the
# poll debounce), because it is the OR itself, not an absent poll
# debounce, that was amplifying the noise.
#
# Elephant is deliberately left off this list, not merely defaulted onto it
# by omission. Elephant's measured recall (0.906, docs/KNOWN_GAPS.md) is
# already below the >=92% field-readiness bar, and majority-of-N trades
# recall for precision - the wrong direction for the one class where a
# missed real detection, not a false one, is the safety-relevant failure.
# Elephant had zero false positives in the same 2-hour run that measured
# Boar's problem, so there is no precision problem here to trade against.
# Boar's problem is precision, not recall, so this is a clean win scoped to
# the class that actually has it, leaving Elephant's OR-across-the-burst
# path - and ADR 0022's confirm-and-exit latency - untouched.
#
# RELAXED - 13 Sept 2026, at the operator's explicit request: left empty so a
# fox - which the 2-class model of the time could only label "Boar" -
# confirms on a single frame instead of needing a majority of the burst,
# matching Elephant's admission bar. This reopens the Boar false-positive
# problem the majority gate exists to fix.
#
# The premise has since changed and the relaxation has not. The 3-class
# model emits "Fox" as its own label, so foxes no longer arrive here as
# Boar and the "there is no way to separate them" argument that justified
# accepting the cost for real Boar sightings has expired with it. What
# remains is a relaxed bar for Boar alone, carrying Boar's false-positive
# rate with it. Stated so the trade is read accurately; it is not a reason
# to revert.
#
# Originally written as a one-day override. It is not one any more: the
# relaxation is open-ended by the operator's decision and carries no expiry.
# REVERT to ("Boar",) only on an explicit request to do so - not because a
# date has passed, and not as tidy-up.
VISION_SPECIES_BURST_MAJORITY_LABELS: tuple[str, ...] = ()

# ADR 0022 Decision B: the deterrent fires on a vision confirmation, not on
# the fused decision alone.
#
# A geophone trigger says something heavy moved within 140m. It does not say
# an elephant is at the boundary, nor that it is coming this way at all.
# Firing the horn on that alone spends the burst on an animal still deep in
# the forest, and cognition/bandit.py's habituation model is explicit that a
# deterrent firing where it achieves nothing is what teaches an animal to
# ignore it. Waiting for the camera puts the burst at boundary range, at
# something demonstrably there - and it is also the only way an event
# produces footage of anything.
#
# The gate is narrow by construction and only ever engages when vision
# actually had a chance: reflex_loop._vision_could_see() sends a failed
# camera, a dead inference server, and an unilluminated night frame all
# straight back to the seismic decision. That last case is not a corner -
# it is every night event until proactive IR illumination is decided
# (docs/KNOWN_GAPS.md), and without it this constant would silently switch
# the whole system off from dusk to dawn.
#
# What this does NOT gate is warning people. The trigger is still recorded,
# logged and settled on seismic alone, and the footfall uplink goes out on
# the seismic decision whether or not this gate held the fire - see
# comms/lora_uplink.py's event_from_footfall(), which for a while read the
# earlier version of this paragraph ("there is no footfall uplink yet")
# and suppressed the frame along with the horn. A suppressed event reaches
# the dashboard as UNCONFIRMED with no deterrent flag and pages nobody, so
# "seismic warns, vision fires" is now implemented in both halves.
#
# False restores the pre-ADR-0022 behaviour: fire whenever decide() says
# alert, whatever the camera saw.
DETERRENT_REQUIRES_VISION_CONFIRMATION = True

# ---------------------------------------------------------------------------
# Acoustic capture + inference (perception/microphone.py,
# perception/acoustic_detector.py, services/reflex_loop.py, ADR 0028)
# ---------------------------------------------------------------------------
# The acoustic modality moved from the MCU to the MPU. ADR 0009 put a
# digital MEMS mic on the STM32's SAI peripheral so the MCU could listen in
# its low-power domain; the Arduino core for this board ships a *prebuilt*
# Zephyr loader with a fixed devicetree, so a sketch cannot add SAI at all,
# and SAI sits outside the SmartRun domain regardless - meaning it could
# never have delivered the always-on listening that was the whole reason to
# prefer it. ADR 0028 has the full argument. What survives is event-gated
# capture on the Linux side: a USB microphone, recorded through arecord,
# classified once by a standing edge-impulse-linux-runner.
#
# Consequence worth stating plainly here because it is easy to miss: the
# MCU->MPU `report_acoustic_event` RPC (bridge/schema.md) now has no
# producer. handle_acoustic_event() is still the correct and only entry
# point - it is just called from this side now.
#
# Always-on gunshot detection is NOT what this provides and is still
# unbuilt. That remains ADR 0009's analog -> ADC4 -> LPBAM path, which
# needs a MAX9814 re-bought and a small MCU-side model (the PANNs arena
# cannot fit 786 kB of SRAM). See docs/KNOWN_GAPS.md.

# Master switch. Default False.
#
# The path itself is no longer unproven: on 30 Sept 2026 a full capture ->
# health-gate -> HTTP runner -> HttpAcousticClassifier run completed on the
# board against the deployed impulse (15.00 s capture for 2 windows, health
# PASS, 4.0-4.4 s inference per window, both windows `ambient` at 0.89-0.95
# in a quiet room). So this is not gated on "does it work" any more.
#
# It stays False because the three health floors below are still INVENTED
# for the mic that will actually be fielded. The 30 Sept run used the
# board's existing USB webcam mic (Microdia 0c45:6366), not the BOYA BY-M1,
# which is not procured yet. Calibrating the floors against the webcam and
# then fielding a different capture chain would be worse than leaving them
# uncalibrated, because it would look calibrated. Flip this to True once
# mic_check has been run against the BY-M1 on its own adapter and the
# floors below carry numbers from that run.
ACOUSTIC_ENABLED = False

# ALSA device string, e.g. "plughw:1,0". None means discover it by name at
# startup (perception/microphone.discover_capture_device), which is the
# right default: USB enumeration order on this board is not stable across
# reboots, and a hardcoded card index that drifts would silently record
# from an on-die codec - producing well-formed silence rather than an
# error. Set the env var only to pin a specific device for a bench run.
ACOUSTIC_CAPTURE_DEVICE = os.environ.get("ELETECT_ACOUSTIC_CAPTURE_DEVICE") or None

# Capture rate. This is the rate the *impulse* takes, which is not the rate
# its front end runs at, and the two being confused is what this comment
# exists to prevent.
#
# The deployed model declares EI_CLASSIFIER_FREQUENCY 8000 with
# RAW_SAMPLE_COUNT 80000, because the corpus is 8 kHz throughout
# (ml/acoustic/README.md:241). PANNs' filterbank is defined at 32 kHz, so a
# 4x upsample happens inside the DSP block - in training via librosa
# (dsp-panns-logmel/dsp.py:147), on-device via the C++ port
# (dsp-panns-logmel/cpp/panns_logmel_core.hpp). Feeding 32 kHz here would
# not skip that step, it would push a 4x-too-fast signal through it and
# land every frequency in the wrong mel bin, which a PANNs backbone reports
# as confident wrong labels rather than as an error.
#
# There is no decimation leg on this board to worry about. `plughw:` will
# resample in-kernel when a device needs it, but the capture device here
# does not: `arecord -D hw:1,0 --dump-hw-params` reports
# `RATE: [8000 48000]` and a direct `hw:1,0 -r 8000` capture prints
# `exact rate : 8000 (8000/1)`, so 8 kHz is taken natively and plughw
# passes it through untouched (measured 30 Sept 2026, Microdia 0c45:6366
# on card 1). That leaves the 8k->32k upsample inside the DSP block as the
# only resampling step on the path, and it is covered by
# dsp-panns-logmel/cpp/parity_resample.py.
#
# This is a property of the capture device, not of the board. The BY-M1
# fields through a different USB adapter, so re-run --dump-hw-params
# against that adapter before assuming the same holds; if it only
# advertises 44.1/48 kHz then plughw WILL decimate and that leg becomes
# untested.
ACOUSTIC_SAMPLE_RATE_HZ = 8000

# How many overlapping inference windows one capture should yield. The
# clip length is derived from this and the deployed model's own window
# (HttpAcousticClassifier.required_capture_s) rather than set directly,
# because POST /api/features rejects any feature count that is not exactly
# input_features_count - a hardcoded duration would start 400ing the day
# the impulse window changes.
#
# 2 is chosen against the inference cost, not against detection quality.
# Studio's performance estimate for this impulse on the QRB2210 is 4,134 ms
# for the classifier block alone, with the custom DSP block unestimated -
# so each extra window is over four seconds of blocked CPU on the same four
# cores the vision watch loop is using. INVENTED.
ACOUSTIC_CAPTURE_WINDOWS = 2

# Seconds between one acoustic check finishing and the next starting. The
# acoustic modality polls on its own schedule rather than being triggered
# by a seismic footfall, because a check costs roughly 4 s of inference
# per window (see ACOUSTIC_CAPTURE_WINDOWS) and folding that into
# handle_footfall_event() would punch a hole in the 45 s vision watch
# window ADR 0022 sized to catch an elephant walking 140 m.
#
# 30 s is a duty-cycle choice, not a detection-latency one. The capture is
# not a constant: acoustic_detector.required_capture_s() derives it from the
# deployed impulse, and at the current 10 s analysis window with
# ACOUSTIC_WINDOW_HOP_FRACTION = 0.5 and two windows it is 10 + 5 = 15 s. So
# a cycle is ~15 s of capture, ~8 s of inference and 30 s idle: roughly 23 s
# of every 53 s has the four cores busy, and about 28% of the timeline is
# actually listened to. (A "~3 s capture" stood here until 2 Oct, which
# understated the capture by 5x; the 8 s inference figure and the
# quarter-of-the-timeline coverage both survive the correction, the latter by
# coincidence rather than because the arithmetic was right.)
#
# It means a one-off transient - a single gunshot - is more likely to be
# missed than heard, which is the honest consequence of not having the
# always-on MCU path ADR 0009 specified and docs/KNOWN_GAPS.md still
# tracks. The 15 s capture is also why folding a check into
# handle_footfall_event() is worse than the paragraph above implies: it is
# ~23 s of hole in a 45 s vision watch, not ~8 s. Sustained sources (a
# chainsaw, a herd calling) are what this duty cycle actually catches.
# INVENTED.
ACOUSTIC_POLL_INTERVAL_S = 30.0

# Hop between consecutive inference windows, as a fraction of the window
# length. 0.5 = 50% overlap, so a transient landing on a window boundary
# still falls whole inside its neighbour - which matters most for exactly
# the class that alerts on its own (a gunshot is roughly 200 ms inside a
# window of several seconds). 1.0 would give contiguous, non-overlapping
# windows and half the compute. INVENTED.
ACOUSTIC_WINDOW_HOP_FRACTION = 0.5

# Hard ceiling on windows classified per clip, independent of clip length.
# At 4+ seconds each, an unbounded count over a long capture would block
# the caller for minutes. Windows past the cap are dropped from the end of
# the clip, so the earliest audio - nearest whatever triggered the capture
# - is always what gets classified.
ACOUSTIC_MAX_WINDOWS = 4

# Confidence a non-ambient window must reach before it is allowed to route.
# Below this the clip is reported as "ran, heard nothing actionable" -
# available=True with no routed outcome - which is distinct from both an
# ambient result and an unavailable check.
#
# This closes the asymmetry perception/acoustic_detector.py's _select()
# docstring names and then leaves open. _select() max-pools over time,
# which is the right shape for a 200 ms gunshot inside a 10 s window, but
# it means a single spurious window carries the whole clip - and for
# gunshot, the one class that alerts on its own by ADR 0007 5, that clip
# becomes an officer's pager. The docstring argues the cost is paid
# downstream by fusion; that argument does not cover gunshot, which never
# reaches fusion. This is the guard for the branch fusion cannot guard.
#
# 0.6 is not invented. ADR 0030 measured accuracy against threshold over
# the frozen 605-clip split with below-threshold windows counted as wrong:
# fp32 scores 91.90% at argmax and 91.74% at a 0.6 gate, so the floor costs
# 0.16 points - one clip in 605 - and 0.6 is also the gate Edge Impulse's
# own reporting for this impulse uses. int8 pays 0.50 points at the same
# gate, which stays inside the same budget if ADR 0030's int8 arm ships.
#
# Applies to every non-ambient class. Ambient is never gated: a
# low-confidence ambient window is still the honest answer "nothing to
# report", and gating it would turn a quiet forest into a routed event.
ACOUSTIC_MIN_CONFIDENCE = 0.6

# Per-class overrides of ACOUSTIC_MIN_CONFIDENCE, keyed by the
# bridge/rpc.py AcousticClass value ("gunshot", "chainsaw",
# "elephant_call"). Empty means every class uses the global floor. Same
# shape as VISION_MIN_CONFIDENCE_BY_LABEL, for the same reason: the two
# classes that only corroborate can afford a lower bar than the one that
# alerts alone, but nothing has measured what those bars should be, so
# raising or lowering one is a deliberate edit and not a default. An
# unrecognized key is ignored with a warning rather than raising - a typo
# here must not take the acoustic poll down on a field node.
ACOUSTIC_MIN_CONFIDENCE_BY_CLASS: dict[str, float] = {}

# Endpoint of the standing `edge-impulse-linux-runner --run-http-server`
# serving the acoustic .eim. Must be a different port from
# VISION_INFERENCE_URL: one runner process serves exactly one artifact, so
# the two models are two processes. Same env-override rationale as the
# vision URL above - inside the App-Lab container 127.0.0.1 is the
# container's own loopback, not the host's.
#
# 1338 is the host-side runner, which is what serves the model today and is
# the configuration every on-target latency number in
# ml/acoustic/ACOUSTIC_MODEL_REPORT.md was measured against.
#
# The model is ALSO registered as an App Lab custom model now
# (deployment/install/install-acoustic-brick.sh), and the
# arduino:audio_classification brick publishes host 1339 -> container 1337.
# That is deliberately NOT the default here, and the mismatch is not an
# oversight:
#
#   - Nothing binds the brick in app.yaml yet, so nothing listens on 1339.
#     Pointing the default there would break the working path to chase one
#     that is not wired up.
#   - When the brick IS bound, the right answer is not 1339 either. The
#     brick and the app share a Compose network, so the app should address
#     the brick by service name and never traverse the host at all - which
#     is exactly the problem that forced the vision runner host-side, since
#     the App-Lab container cannot reach host 127.0.0.1 over the bridge.
#
#     The service name is `ei-audio-classifier-runner` and the in-network
#     port is 1337, not the published 1339. That is not a guess: the brick's
#     own client resolves it the same way. arduino/app_internal/core/ei.py
#     `_get_ei_url()` loads the brick's compose file, takes the *first*
#     service key as the hostname, and returns f"http://{addr}:1337".
#     1339 exists only so a human on the board can curl it.
#
# So the switch is an env var at that point, not an edit here: set
# ELETECT_ACOUSTIC_INFERENCE_URL to http://ei-audio-classifier-runner:1337.
# It goes in the golden compose's `environment:` block alongside the other
# ELETECT_* vars, not in app.yaml - AppDescriptor has no app-level env key,
# and a brick's `variables` block can only carry variables that brick
# declares in its own brick_config.yaml. This constant stays pointed at the
# runner that is actually running.
#
# For the record, 1338 is not an arbitrary choice of ours that happens to
# collide - it is the port arduino:image_classification publishes. The
# host-side runner borrows a port from a brick we do not run. If that brick
# is ever added, this default has to move.
ACOUSTIC_INFERENCE_URL = os.environ.get(
    "ELETECT_ACOUSTIC_INFERENCE_URL", "http://127.0.0.1:1338"
)

# Per-window socket timeout. Deliberately an order of magnitude above
# VISION_INFERENCE_TIMEOUT_S's 2.0s, because the workload genuinely is
# that much heavier: Studio estimates 4,134 ms for the PANNs Cnn10
# transfer block alone on this silicon (float32, unoptimised), and the
# custom log-mel block on top of that is unestimated because Studio cannot
# profile a custom block. 15s leaves roughly 3x headroom over the known
# part of that figure. This is a ceiling for detecting a wedged runner, not
# a latency target - if real measurements come in near it, the answer is a
# quantised model, not a larger number here. INVENTED.
ACOUSTIC_INFERENCE_TIMEOUT_S = 15.0

# --- Microphone health floors (perception/microphone.assess_health) -------
# The field mic is a BOYA BY-M1: an electret lavalier powered by one LR44
# cell. Its failure mode is the dangerous kind - a dead cell does not stop
# the USB device enumerating or stop frames arriving, it just makes them
# near-silent, which classifies as confident `ambient` forever and is
# indistinguishable from a quiet forest. So level is checked on every clip
# and a clip that fails is reported to fuse() as ACOUSTIC *unavailable*,
# never classified. An absent modality fusion can drop; a lying one it
# cannot.
#
# ALL THREE NUMBERS BELOW ARE INVENTED and must be replaced with measured
# ones. device/mpu/bench/mic_check/mic_check.py prints exactly these three
# statistics for a real capture; run it against (a) the mic switched on
# with a fresh cell, (b) the mic switched off, and set the floor between
# the two. Until that is done ACOUSTIC_ENABLED stays False.
#
# What a real capture looks like, for scale. Four settled captures on the
# board 30 Sept 2026 (Microdia 0c45:6366, plughw:1,0, quiet indoor room,
# after Microphone.WARMUP_S is discarded) read:
#
#     rms      0.0057 - 0.0141
#     peak     0.023  - 0.056
#     clipped  0.000000 in all four
#     dc       +0.00059 - +0.00078
#
# Against that, every floor here is loose by one to two orders of
# magnitude: MIN_RMS 0.0003 is ~20x below a quiet room, MAX_CLIPPED 0.01
# is ~300x above what a clean capture produces, MAX_DC_OFFSET 0.05 is ~60x
# above the measured bias. A gate that far out is a gate that only catches
# a mic that has stopped existing. It did not, for instance, catch the
# capture warm-up transient documented at Microphone.WARMUP_S - a
# full-scale clipping artifact present on every single capture - because
# averaging it over a whole clip pulled all three statistics back inside
# these bounds. That defect is fixed by discarding the warm-up, not by
# these floors, and it is the concrete argument for tightening them rather
# than a hypothetical one.
#
# These are webcam-mic numbers. They say what order of magnitude to expect;
# they are not the BY-M1's numbers and must not be pasted in as the
# calibration.

# RMS below this, normalised to full scale, means "no working microphone".
# Set low on purpose: a genuinely quiet night must not be mistaken for a
# dead cell, so this errs toward accepting near-silence rather than
# rejecting it. That bias is the wrong way round for catching a slowly
# dying battery and is the main reason the measured calibration matters.
ACOUSTIC_MIN_RMS = 0.0003

# Fraction of samples at or beyond full scale above which the clip is
# treated as distorted. Clipping squares off the waveform and the harmonic
# content the log-mel front end then sees is an artifact of the ADC rather
# than of the source. 1% is a permissive gate aimed at a badly
# misconfigured capture gain (the adapter's "mic boost"), not at the odd
# transient peak of a genuinely loud event close to the mic.
ACOUSTIC_MAX_CLIPPED_FRACTION = 0.01

# Mean sample value, unsigned and normalised, above which a bias or
# coupling fault is assumed. Checked *before* the RMS floor, because a DC
# offset inflates RMS and can therefore mask exactly the near-silence the
# floor exists to catch - a dead mic with an offset passes a naive level
# check while carrying no signal at all.
ACOUSTIC_MAX_DC_OFFSET = 0.05

# ---------------------------------------------------------------------------
# External IR illuminator gating (perception/night.py, services/reflex_loop.py)
# ---------------------------------------------------------------------------
# pulse_ir() only helps when the IMX462's IR-cut filter is out (night): in
# daylight the filter blocks the illuminator's near-IR band before it
# reaches a pixel, so the pulse is spent MOSFET duty budget and battery for
# no image gain. perception/night.frames_are_night() infers the filter state
# from the pre-decision vision-check burst's own colour saturation - a
# mono / IR-cut-open frame reads near-zero mean HSV S, a daylight colour
# frame reads tens of units. A burst whose median mean-S is below this is
# treated as night and the IR pulse is allowed; at or above it, pulse_ir()
# is suppressed for the watch (logged; nothing else about the event
# changes).
#
# Measured on the real rig (Kothamangalam backyard, 1-2 Sep 2026): a
# genuine night frame read mean S = 0.0; a daylight colour frame read
# S > 30. 12 sits in that gap with margin on both sides. Not a tuned figure
# beyond that separation - see docs/KNOWN_GAPS.md.
NIGHT_SATURATION_THRESHOLD = 12.0

# How the vision watch illuminates. IR is a camera light, not a deterrent -
# it is what gives the detector something to see at night, so it fires
# during services/reflex_loop.py's _watch_for_vision() poll loop, on the
# night read, rather than from a chosen deterrence tier. The watch may run
# 45s (VISION_WATCH_BASE_S); the illuminator must not be on for all of it.
#
# Both values mirror device/mcu/src/config.h and tests/test_config.py fails
# if they drift apart, the same discipline the BRIDGE_*_CALL_TIMEOUT_S block
# above follows. The MCU stays authoritative either way: ir_pulse_request()
# clamps the duration to IR_PULSE_MAX_MS and refuses outright inside
# IR_MIN_INTERVAL_MS of the last pulse. These exist so the MPU does not
# spend a Bridge round-trip per poll earning four refusals out of five.
#
# Pulse length is the MCU's own maximum. There is no reason to ask for less
# - the cost is the duty budget, which is governed by the interval, not by
# shaving milliseconds off a pulse that has to outlast the exposure window
# it exists to cover.
IR_WATCH_PULSE_MS = 500

# Start-to-start spacing between watch pulses, equal to the MCU's
# IR_MIN_INTERVAL_MS. At VISION_WATCH_POLL_INTERVAL_S = 1.0s this means
# roughly one poll in five is illuminated, and a full 45s watch spends at
# most nine pulses. That ratio is the duty budget doing its job, not a
# shortfall to tune around: the unlit polls still run detection, and a
# night watch that confirms does so on one of the lit ones.
IR_WATCH_MIN_INTERVAL_S = 5.0

# ---------------------------------------------------------------------------
# Night exposure lock (perception/camera.py, services/reflex_loop.py)
# ---------------------------------------------------------------------------
# Auto-exposure hunts against the IR pulse: it reacts to the sudden light
# within a frame or two and pulls gain back down, both erasing most of the
# illuminator's benefit (+5-7% luma gained vs +29-60% locked) and, worse, is
# the dominant source of Boar false positives at night - three
# auto-exposure+IR sweeps threw 15/22/28 spurious Boar boxes, maxconf up to
# 0.408 (above the 0.2 deployment threshold), where every locked-exposure
# run in the same battery threw zero
# (docs/qa/night-ir-led-characterisation.md, Finding 4). Locking exposure
# right before the IR-lit evidence burst - the only capture this needs to
# protect; tier 1 never fires IR - removes the AGC hunting that causes both
# problems.
#
# Measured 1-2 Sept 2026, Kothamangalam backyard, real hardware: treeline
# sharpness gain from the pulse peaks at exposure ~256 (+100.0 Laplacian,
# roughly 1.3-2.5x the gain at other settings in the ladder), never clips
# (saturation stayed 0.000 through the whole 32-512 sweep), and produced
# zero false positives with or without the pulse. Do not exceed ~320
# (ground-band ghost boxes start appearing above ~384) or drop below ~128
# (the sensor is noise-limited by exposure 32). 256 is the coarsest useful
# step actually tested, not a pinned optimum - the true best setpoint may
# sit anywhere in ~224-320.
NIGHT_LOCKED_EXPOSURE = 256

# Independent kill switch for the whole feature - this changes camera
# behaviour for every species, and the only field verification so far is a
# static, empty scene (Finding 4's own caveat: motion blur on a moving
# animal at this exposure is unmeasured). If it ever needs pulling without
# a redeploy, this is the one flag that does it - same env-first idiom as
# SAFE_MODE (reflex_loop.py), read once so startup can honestly log which
# mode the run is in.
NIGHT_EXPOSURE_LOCK_ENABLED = os.environ.get("ELETECT_NIGHT_EXPOSURE_LOCK", "1") != "0"

# Mean frame brightness (luma, 0-255) at or above which a scene is treated
# as daylit even if its saturation still reads mono - the dawn override in
# perception/night.py's ExposureAutoLock. The IR-cut-open sensor produces a
# near-zero-saturation frame whatever the ambient light, so the
# saturation-only day/night classifier cannot see sunrise coming and holds
# the night exposure lock straight through it, over-exposing the sensor.
#
# Measured from the Kothamangalam field trial, dawn of 10 Sept 2026: a
# working night-locked frame ~05:34 IST read mean luma 138; the dawn
# over-exposure window (06:14-06:16 IST) read 190-198 and climbing; full
# daylight read 220+. 175 sits above the night frame with margin and below
# every over-exposed frame. Provisional - like HOME_TEST_EXPOSURE_FLIP_
# CONSECUTIVE it wants tightening against a clean ambient-brightness trace
# from the first supervised overnight soak (see docs/KNOWN_GAPS.md). The
# override can only release a lock, never impose one, so erring high is the
# safe direction.
NIGHT_BRIGHTNESS_DAY_THRESHOLD = 175.0

# Near-field clip trim (perception/night.py's ExposureAutoLock). NIGHT_LOCKED_
# EXPOSURE above was only ever measured against a static, empty, far-field
# scene - IR intensity falls off with distance^2, so the same fixed value can
# drive near-field foliage to solid-white clipping while a subject metres out
# stays correctly exposed. Seen live in the field 23 Sept 2026: a locked
# frame with near-field foliage blown to white and a near-black background -
# a case NIGHT_BRIGHTNESS_DAY_THRESHOLD's frame-wide mean cannot catch, since
# the frame's average stays low.
#
# All four values below are a first cut, not yet validated against a real
# overnight soak with the trim active - see docs/KNOWN_GAPS.md. Directional
# reasoning only: NIGHT_CLIP_VALUE=250 sits just under saturation (255) so it
# only counts pixels that are actually blown, not merely bright.
# NIGHT_CLIP_FRACTION_THRESHOLD=0.02 (2% of the frame) is meant to catch a
# real near-field patch while ignoring a handful of stray bright pixels.
# NIGHT_EXPOSURE_TRIM_STEP=32 matches the ladder granularity Finding 4's
# sweep actually tested. NIGHT_EXPOSURE_FLOOR=128 is Finding 4's own
# documented noise-limited floor - the trim must never cross it.
NIGHT_CLIP_VALUE = 250.0
NIGHT_CLIP_FRACTION_THRESHOLD = 0.02
NIGHT_EXPOSURE_TRIM_STEP = 32
NIGHT_EXPOSURE_FLOOR = 128

# ---------------------------------------------------------------------------
# Which species this node acts on (services/reflex_loop.py)
# ---------------------------------------------------------------------------
# ETX-V is a three-class detector - perception/detector.py's module
# docstring records the deployed model's labels - and the classes are
# wanted for different things at different times, so they get two separate
# lists rather than one switch.
#
# DETERRENT_TARGET_LABELS is the heavier of the two. A label in here counts
# as a vision confirmation, which means it feeds fuse() as positive
# evidence and, under ADR 0022 Decision B, is what releases the horn. A
# label NOT in here can still be detected, logged and filmed; it just
# cannot fire an actuator.
#
# EVENT_VIDEO_TARGET_LABELS only decides whether an event's recording is
# kept instead of discarded. Keeping footage costs disk and nothing else -
# no horn, no battery, no habituation - so it is the cheap list, and it is
# the right place to start with a new species.
#
# Both lists are *derived* from NODE_DETERRENCE_SCOPE rather than hand-set,
# via deterrence_scope_labels() below - a per-node commissioning attribute,
# same shape as NODE_HOUSEHOLD_PROXIMITY, rather than a source edit for a
# species change. The default "elephant_only" maps to ("Elephant",) for
# both, byte-for-byte the value these two constants have always had.
#
# A scope is any combination of the species registry's labels, named
# explicitly and in any order:
#
#     ELETECT_DETERRENCE_SCOPE=Elephant
#     ELETECT_DETERRENCE_SCOPE=Elephant,Fox
#     ELETECT_DETERRENCE_SCOPE=Elephant,Boar,Fox
#
# parse_scope_labels() resolves the string and DETERRABLE_LABELS - the
# registry's own keys - is both its vocabulary and its safety bound, so a
# scope can only ever name a species this build actually knows how to
# deter. Adding a species is one registry row; commissioning a node for it
# is one environment variable, with no source edit in between.
#
# That replaces a three-state switch - "elephant_only" / "boar_only" /
# "both" - which could not express a node that deters Elephant and Fox but
# not Boar, and which needed a new state hand-written into this file every
# time the registry grew. The three strings still resolve, byte for byte,
# as aliases; see _SCOPE_ALIASES for why they are kept rather than
# translated away.
#
# The asymmetric case - deter elephants, but collect boar and fox footage,
# the honest way to find out whether deterring a species is worth doing
# before any horn fires at one - is ELETECT_EVENT_VIDEO_SCOPE, set
# independently below. A second scope rather than a fourth state, because
# the two lists answer different questions and the cheap one should not
# need the expensive one's permission.
#
# A multi-species scope used to carry a caveat a single-species one did
# not, and it was not a style objection: the bandit learned one policy per
# node, so a night of boar visits could walk the node up to tier 3 and
# leave an elephant arriving at dawn facing an already-habituated
# response. ADR 0034 closed that - the escalation floor and the action
# values are partitioned per species, so one species can no longer spend
# another's ladder. What stays shared, deliberately, is the reward:
# proxy_reward() measures time to the next seismic trigger, which is
# species-blind by construction, and crediting only same-species triggers
# would nearly stop the node learning at night, when most triggers are
# never attributed to anything. That is a documented limitation in ADR
# 0034 rather than an open defect, and it is the one thing worth keeping
# in view when widening a scope.


def deterrence_scope_labels(scope: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Resolve a NODE_DETERRENCE_SCOPE value to (deterrent, video) label tuples.

    Pure function, same shape as cognition.config.resolve_tier_action -
    the imperative shell reads the site attribute, this turns it into the
    two lists everything else in the reflex loop actually consumes.

    Both lists default to the same scope: filming what you deter is the
    common case, and needing two environment variables to say so is a
    footgun. The asymmetric case the old three-state version could not
    express is ELETECT_EVENT_VIDEO_SCOPE, applied below.

    Kept as its own function, and kept returning a pair, so the call sites
    and tests that name the legacy scope strings keep working unchanged
    while parse_scope_labels() carries the behaviour.
    """
    labels = parse_scope_labels(scope)
    return labels, labels


DETERRENT_TARGET_LABELS, EVENT_VIDEO_TARGET_LABELS = deterrence_scope_labels(
    NODE_DETERRENCE_SCOPE
)

# Filming is the cheap list - it costs disk and nothing else, no horn, no
# battery, no habituation - so it is the right place to start with a new
# species. Unset, it follows the deterrence scope. Set, it replaces it
# outright, which is how a node collects the evidence for whether deterring
# a species is worth doing before any actuator fires at one:
#
#     ELETECT_DETERRENCE_SCOPE=Elephant
#     ELETECT_EVENT_VIDEO_SCOPE=Elephant,Boar,Fox
#
# Bounded by the same DETERRABLE_LABELS vocabulary. That is stricter than
# it needs to be - filming a species is harmless and the bound exists for
# actuators - but one vocabulary across both scopes means an operator
# learns it once, and widening it later is a smaller change than splitting
# it now.
_EVENT_VIDEO_SCOPE = os.environ.get("ELETECT_EVENT_VIDEO_SCOPE")
if _EVENT_VIDEO_SCOPE is not None:
    EVENT_VIDEO_TARGET_LABELS = parse_scope_labels(_EVENT_VIDEO_SCOPE, what="event-video")

# ---------------------------------------------------------------------------
# Deterrent-event capture storage (perception/storage.py)
# ---------------------------------------------------------------------------
# Where reflex_loop.py's alert-path frame burst gets written, tagged with the
# triggering event's own metadata. Module-relative like DATA_DIR/MODELS_DIR
# above, for the same reason - lands inside the App's own folder on the
# board, not /tmp.
CAPTURE_DIR = _MODULE_DIR / "data" / "captures"

# perception/storage.py logs a warning (never fails silently, per
# ENGINEERING_CONVENTIONS.md 3's zero-filled-read precedent for "degrade
# loudly, don't go silent") when free space at CAPTURE_DIR drops below this.
# INVENTED - no measured field JPEG-size/trigger-frequency data backs this
# number yet; picked as a conservative "still room for hundreds more bursts"
# floor against the real board's ~3.6GB usable /home/arduino partition
# (per Edge Impulse's App Lab reference), not
# a tuned figure. See docs/KNOWN_GAPS.md.
CAPTURE_LOW_DISK_HEADROOM_BYTES = 500 * 1024 * 1024  # 500 MB

# ---------------------------------------------------------------------------
# Trigger-gated event video (ADR 0020, perception/video.py)
# ---------------------------------------------------------------------------
# ADR 0020 records a real video per event to a scratch path, runs the vision
# check against that same live stream, and keeps the file only if the event
# is confirmed - discarded triggers never reach the permanent capture
# directory at all. Everything below sizes that one lifecycle.
#
# What this section deliberately does NOT configure: a continuous rolling
# pre-event buffer. ADR 0020 rejects one outright on power grounds (a
# permanently-running camera and encoder against a solar/battery budget that
# is already baseline-dominated), and that rejection got *stronger*, not
# weaker, when the board's real idle draw turned out to be far above the
# figure the budget was sized on (ADR 0008's 2 Sept addendum). There is no
# constant here to turn one on, by design.

# Master switch, default OFF. The GStreamer pipeline in perception/video.py
# has never been run against the real camera - no live-camera work has been
# done since this was written, and the field power topology it would run
# under (VIN rather than USB-C) has its own unresolved camera-enumeration
# question in docs/KNOWN_GAPS.md. Off means device/mpu/main.py wires the
# existing perception.camera.Camera and the JPEG-burst path exactly as
# before and nothing in perception/video.py is ever constructed, so this
# whole feature is inert until someone flips it with the board in front of
# them.
EVENT_VIDEO_ENABLED = False

# Scratch directory for in-progress recordings, deliberately a subdirectory
# of CAPTURE_DIR rather than /tmp or the container's own root overlay: the
# commit step is an os.replace() of the finished file into CAPTURE_DIR, and
# os.replace is only atomic within a single filesystem. On the board those
# are genuinely different filesystems (CAPTURE_DIR lives on the 18G
# /home/arduino mmcblk0p69; the container's /tmp is the ~1G root overlay),
# so a scratch path outside CAPTURE_DIR would silently degrade the commit
# into a copy-then-delete with a window where a brown-out leaves a
# half-written file in the permanent directory. Leading dot so a directory
# listing of captures shows finished footage only.
EVENT_VIDEO_SCRATCH_DIR = CAPTURE_DIR / ".scratch"

# A raw H.264 Annex-B elementary stream, not a Matroska or MP4 container.
# The original design called for Matroska specifically because an MP4's
# moov atom is written when the file is closed, so a recording cut short -
# which on this board means a 5V brown-out, a documented and observed
# failure (docs/KNOWN_GAPS.md, 2 Sept) - leaves a file no player will
# open. That reasoning turned out to prove too little: on real hardware,
# matroskamux can't be used at all. v4l2h264enc's src pad only ever emits
# byte-stream H.264; matroskamux's sink only accepts avc/avc3. Bridging
# the two needs h264parse, which lives in gstreamer1.0-plugins-bad -
# confirmed absent from the production container and uninstallable there
# (no installation candidate in the pinned Debian snapshot repo, and the
# container user has no root). jpegparse, upstream of the decode, is
# missing from the same package for the same reason, but turned out to be
# unnecessary: jpegdec accepts v4l2src's MJPEG buffers directly.
#
# Dropping the muxer is not a downgrade of the truncation-resilience
# argument, it's a stronger version of it: an elementary stream has no
# header or index to corrupt in the first place, so a brown-out mid-write
# leaves a valid, playable stream missing only its trailing frames -
# "playable up to the crash" without even needing incremental-write
# semantics from a container format to get there. Validated end-to-end on
# the real board (6s bench recording, decoded cleanly via OpenCV/FFmpeg on
# a separate machine) - on USB-C/hub power, not yet under VIN; see
# docs/KNOWN_GAPS.md for the still-open VIN-power camera question.
EVENT_VIDEO_SUFFIX = ".h264"

# Upper bound on how long a recording may run before the keep-or-discard
# decision has to have been made (ADR 0020 Decision B3's "~15-20s"). The
# as-built reflex loop is synchronous and reaches that decision far sooner
# than this - camera open, one VISION_CHECK_FRAME_COUNT burst, one
# detect_vision() call bounded by VISION_INFERENCE_TIMEOUT_S, then fuse()
# and decide(), which are pure functions - so this is not a timer the loop
# waits on. It is the budget those stages must stay inside, checked as an
# invariant in tests/test_config.py rather than enforced by a watchdog
# thread this loop does not need and would have to get right.
#
# Raised from 20.0 to cover ADR 0022's watch window: the loop now keeps
# looking for up to VISION_WATCH_EXTENDED_S before it decides, so the
# budget that decision has to fit inside had to grow with it. The margin
# above the watch length is the camera-open retries and the final
# inference call, which tests/test_config.py checks explicitly.
EVENT_VIDEO_CONFIRM_WINDOW_S = 60.0

# How long to keep recording after the actuator sequence completes on a
# confirmed event - the retreat tail, ADR 0020 Decision B4's "30-60s from
# confirmation". Replaces (does not add to) CAPTURE_POST_FIRE_TAIL_S's 2.0s
# when video recording is active: that 2s tail was sized for a JPEG burst,
# and 2s of video would show the horn firing and nothing after it.
#
# The honest cost, stated plainly because it is a real behaviour change:
# the reflex loop blocks for this whole tail, so a second footfall notify
# arriving during it is queued behind it rather than handled. That is
# already true of the 2s tail; 45s makes it matter. It is one of the
# reasons EVENT_VIDEO_ENABLED defaults to False. INVENTED - no footage
# review backs 45s over 30s or 60s, same as CAPTURE_POST_FIRE_TAIL_S.
EVENT_VIDEO_RETREAT_TAIL_S = 45.0

# Recording resolution and frame rate. 720p rather than the camera's
# CAMERA_FRAME_WIDTH/HEIGHT stills resolution, for the same reason as
# before: the recorder decodes MJPEG in software before encoding H.264,
# and 1080p decode-plus-encode on four A53 cores would compete with the
# vision inference running off the same pipeline. The framerate is not a
# design choice, though - it is measured. GStreamer's v4l2src negotiates
# exact discrete caps and rejects anything the sensor doesn't advertise
# (unlike OpenCV's V4L2 backend elsewhere in this codebase, which snaps
# silently to the nearest supported mode - the two are not interchangeable
# assumptions). Swept on the real board: at 1280x720, 5/10/15/20/25fps all
# fail not-negotiated; only 30fps links. A broader sweep across several
# resolutions found no combination that offers 15fps at all - 30fps is
# this sensor's only mode at any usable size, not a fallback from one.
# 720p30 therefore costs roughly double the software JPEG-decode work the
# original 720p15 figure assumed; no encode-load measurement on this
# board backs the resulting number, so headroom is unverified either way.
EVENT_VIDEO_WIDTH = 1280
EVENT_VIDEO_HEIGHT = 720
EVENT_VIDEO_FRAMERATE = 30

# H.264 target bitrate. ADR 0020 sizes a 60-90s event clip at 10-20MB;
# 2 Mbps lands a 60s clip at ~15MB, inside that range. Kept as an explicit
# constant rather than left to the encoder's default so the storage
# arithmetic in ADR 0020 stays traceable to a number in the code.
# ROOT-CAUSED 3 Sept: a 6s bench recording at this setting first produced
# a ~24.8MB file (~33 Mbps effective, ~16x over target). Not a wrong
# control name - enumerated /dev/video4's real V4L2 controls (raw ioctl,
# v4l2-ctl is not present in the container) and "video_bitrate" is exactly
# right by name. The driver's `video_bitrate_mode` control defaults to 0
# ("Variable Bitrate"), where this value is only a soft average and the
# encoder's QP range actually governs output instead. perception/video.py
# now also sets `video_bitrate_mode=1` ("Constant Bitrate") in
# extra-controls so this constant is enforced rather than advisory. Not
# yet re-verified with a real recording - do that before trusting the
# storage arithmetic below or EVENT_VIDEO_RETREAT_TAIL_S against this rate.
EVENT_VIDEO_BITRATE_BPS = 2_000_000

# How long to wait for the pipeline to flush and finish the file after
# end-of-stream is sent. The recording is a raw H.264 Annex-B elementary
# stream (see EVENT_VIDEO_SUFFIX above) with no container index to
# finalise, so a stuck EOS costs nothing beyond whatever the encoder
# itself has buffered - but a stuck pipeline still must not hold the
# reflex loop open indefinitely, so this timeout bounds the wait rather
# than trusting the encoder to always report done. INVENTED.
EVENT_VIDEO_STOP_TIMEOUT_S = 5.0

# How long a single frame pull off the recording pipeline may block. Sized
# generously against EVENT_VIDEO_FRAMERATE's ~33ms frame interval so a
# momentary encoder stall does not read as a dead camera, and bounded so a
# genuinely dead pipeline degrades to "no frames" (which the reflex loop
# already handles as vision-unavailable) instead of blocking the event.
# INVENTED.
EVENT_VIDEO_FRAME_TIMEOUT_S = 2.0

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

# INFO by default: quiet enough for continuous field operation, verbose
# enough to see wake/event/Bridge activity on the bench without extra
# configuration.
LOG_LEVEL = "INFO"

# ---------------------------------------------------------------------------
# HOME_TEST_MODE - backyard test build ONLY, never a field deployment
# ---------------------------------------------------------------------------
# Second operating mode for a supervised one-night backyard wild-boar test.
# Field mode's whole design point is low power: seismic-gated wake, camera
# opened only for an event, no continuous recording - ADR 0020 rejects
# always-on capture outright, on power grounds. A backyard test has mains
# power and no such constraint, so this mode trades that away for data:
# continuous capture, a rolling frame ring, an unconditional detection log,
# and one saved clip per encounter covering arrival through departure.
#
# The MCU half of this toggle is HOME_TEST_MODE in device/mcu/src/config.h.
# The two flags are deliberately INDEPENDENT - there is no cross-process
# command that syncs them, and there must not be one. A new Bridge message
# type invented under time pressure is a far bigger reliability risk than
# two flags that each print loudly at boot; main.py and the sketch's
# setup() both log which mode they came up in, so a board left in test mode
# announces itself on the console rather than silently under-reporting in
# the field.
#
# Env-first with a field-safe default, matching NODE_HOUSEHOLD_PROXIMITY and
# NODE_DETERRENCE_SCOPE above. This is deliberately NOT a source constant on
# the MPU side: the goal is that nobody ships to the field still in test
# mode, and a default-off environment variable achieves that better than a
# constant does - the field default is safe with nobody having to remember
# to flip anything back. The MCU has no environment to read, so it stays a
# #define there.
#
# What this flag does NOT change: the deterrence path. Fusion, the bandit,
# the rule gate and the actuator RPCs are shared and unforked between modes.
# Only sensing, logging and camera duty-cycle differ. A tier chosen here is
# chosen by exactly the code that would choose it in the field.
HOME_TEST_MODE = os.environ.get("ELETECT_HOME_TEST_MODE", "0") != "0"

# Fox used to be appended to both target lists here whenever HOME_TEST_MODE
# was set, because the backyard trial's real visitors are foxes and no
# deterrence scope could name them. A scope can now, so the operating mode
# no longer decides what the node deters:
#
#     ELETECT_DETERRENCE_SCOPE=Elephant,Boar,Fox
#
# Worth stating why the old form had to go rather than just being
# redundant. It appended Fox *after* deterrence_scope_labels() had already
# resolved, so the node deterred a species its own configuration did not
# name and no scope string could switch off; and it ran after
# EXPERIENCE_DB_PATH was derived, so the extra species learned its policy
# into the DB belonging to the narrower scope.
#
# The one thing it did that the scope does not: it took effect without
# anyone setting an environment variable. Any deployment relying on that -
# including the backyard node - must now carry the scope explicitly, or it
# will stop deterring foxes at the next deploy.

# Everything this mode writes lives under one directory, kept separate from
# CAPTURE_DIR so a test night is trivially separable from real event
# captures when copying data off the board.
HOME_TEST_DIR = _MODULE_DIR / "data" / "home_test"

# The rolling ring: every frame the capture thread grabs, as a JPEG, named
# by wall-clock timestamp. Frames older than HOME_TEST_PREROLL_S are deleted
# continuously while idle, so this directory's size is bounded by the
# pre-roll depth and never by the length of the night.
HOME_TEST_RING_DIR = HOME_TEST_DIR / "ring"

# One subdirectory per encounter, holding the protected frames. Permanent -
# nothing in here is ever auto-deleted.
HOME_TEST_ENCOUNTERS_DIR = HOME_TEST_DIR / "encounters"

# A detection that never clears HOME_TEST_FIRE_MIN_CONFIDENCE (or, for a
# VISION_SPECIES_BURST_MAJORITY_LABELS member, never wins its burst majority)
# opens no encounter, so its ring frames age out after HOME_TEST_PREROLL_S
# with zero image evidence kept - confirmed as a real gap the night of 10-11
# Sept 2026 when a Boar cluster peaked at 0.631 but never won its
# burst-majority vote: by the time the board was next reachable, every ring
# frame from that window was long gone, leaving only the detections.jsonl
# rows. This directory holds one representative still per such gap -
# permanent, small, and independent of the encounter/fire state machine, so
# it can never affect a firing decision.
HOME_TEST_REVIEW_DIR = HOME_TEST_DIR / "review_frames"

# Floor for a review still: above ambient noise, below the fire bar, so it
# catches exactly the marginal case above without saving every noise blip.
# 10-11 Sept's real cluster ran 0.52-0.63; the same session's daytime noise
# floor (post-restart Boar reads, same camera/scene) sat at 0.14-0.22.
#
# 23 Sept: cut 0.45 -> 0.25 alongside that night's HOME_TEST_FIRE_MIN_CONFIDENCE
# drop to 0.35 - left at 0.45 it would sit ABOVE the new fire bar, so nothing
# would ever land in the gap this exists to cover. 0.25 sits just above the
# 0.14-0.22 daytime noise floor and below the fire bar.
#
# The fire bar has since gone back up to 0.60, so the gap this floor covers
# is now the wide 0.25-0.60 band rather than the narrow 0.25-0.35 one it was
# sized against. That is the safe direction (more marginal evidence kept, and
# a review still can never affect a firing decision), so it is left at 0.25 -
# but the two constants are coupled and must be re-read together whenever
# either moves.
HOME_TEST_REVIEW_MIN_CONFIDENCE = 0.25

# Minimum spacing between saved review stills, per label, so one lingering
# animal writes a handful of stills rather than one per inference poll.
HOME_TEST_REVIEW_MIN_INTERVAL_S = 5.0

# Independent, small byte budget for review stills - separate from
# HOME_TEST_MAX_TOTAL_BYTES, which governs encounter video and is sized for
# that much larger job. Reaching this cap stops new stills; it never deletes
# existing ones and never touches the encounter/fire path.
HOME_TEST_REVIEW_MAX_TOTAL_BYTES = 200 * 1024 * 1024  # 200 MB

# Every detection the model returns, unconditionally, one JSON object per
# line. Deliberately NOT gated on confidence or on the encounter state
# machine: false positives are exactly as useful as true positives when the
# point of the night is a labelled dataset, and a log that only records what
# already passed a threshold cannot be used to re-tune that threshold later.
HOME_TEST_DETECTIONS_PATH = HOME_TEST_DIR / "detections.jsonl"

# Raw geophone samples relayed by the MCU's existing
# debug_stream_raw_seismic_sample notify, stamped with the MPU's own clock
# on receive. See main.py's handler for why MPU-receive time (rather than a
# new MCU-timestamp wire field) is what this records.
HOME_TEST_SEISMIC_CSV_PATH = HOME_TEST_DIR / "seismic_raw.csv"

# Ring capture resolution. Lower than CAMERA_FRAME_WIDTH/HEIGHT's 1920x1080
# on purpose: the ring writes every frame to disk, so per-frame bytes are
# the dominant storage term, and 720p is well above what the 320x320 model
# input needs while staying watchable as video. Inference runs on these same
# frames - there is no second, higher-resolution capture path.
HOME_TEST_RING_WIDTH = 1280
HOME_TEST_RING_HEIGHT = 720

# cv2.IMWRITE_JPEG_QUALITY for ring frames. 85 rather than the default 95:
# on a dark IR scene the visual difference is negligible and the file is
# roughly a third smaller, which is a third more encounters inside
# HOME_TEST_MAX_TOTAL_BYTES.
HOME_TEST_JPEG_QUALITY = 85

# How many recent frames the capture thread keeps in memory for the
# inference and deterrence threads to read. Memory-bounded, not time-bounded:
# at 720p a decoded BGR frame is ~2.7 MB, so 16 frames is ~44 MB, which is
# affordable next to the container's footprint and is comfortably more than
# CAMERA_BURST_FRAMES needs for one deterrence burst.
#
# This deque is the ONLY thing the inference and deterrence threads read
# frames from. Neither of them ever touches the camera. One USB video node
# opened once, by one thread, for the whole session.
HOME_TEST_FRAME_BUFFER_FRAMES = 16

# Frames per inference poll, and how long to wait between polls. The poll
# interval is a floor, not a schedule: if inference takes longer than this
# the next poll simply starts late, and - crucially - the capture thread is
# entirely unaffected either way. Capture rate and inference rate are
# independent by construction, which is the whole reason the ring produces
# smooth video even though the detector runs at ~5 fps.
HOME_TEST_INFERENCE_FRAME_COUNT = 3
HOME_TEST_INFERENCE_INTERVAL_S = 1.0

# ---------------------------------------------------------------------------
# HOME_TEST_MODE encounter state machine
# ---------------------------------------------------------------------------
# Start-here values, chosen to be defensible rather than tuned. Every one of
# them should be revisited against the first real encounter's footage.

# Ring depth, and therefore how much footage precedes the first detection in
# a saved encounter. The point of a pre-roll is to capture the approach -
# the part that happens before the model is confident enough to say
# anything - which is usually the most behaviourally interesting part of the
# clip and is unrecoverable if not already buffered.
HOME_TEST_PREROLL_S = 40.0

# How much to keep recording after the encounter ends, so the clip shows the
# animal actually leaving rather than cutting at the last detection.
HOME_TEST_POSTROLL_S = 20.0

# No qualifying detection for this long ends the encounter. Long enough to
# ride out an animal walking behind a bush or briefly out of frame - which
# would otherwise split one encounter into several - and short enough that
# an encounter closes and is written out while the night is still running.
HOME_TEST_DEPARTURE_TIMEOUT_S = 45.0

# Hard ceiling on a single encounter regardless of continuing detections.
# This is a containment bound, not a behavioural one: the deployed detector
# has a measured 27.54% poll-level Boar false-positive rate on foliage (see
# HOME_TEST_FIRE_MIN_CONFIDENCE below), so a windblown branch that keeps
# tripping the gate must not be able to protect frames all night and fill
# the disk. Whatever it is, three minutes of it is enough to diagnose it in
# the morning.
HOME_TEST_MAX_ENCOUNTER_S = 180.0

# 7 Sept, live in-person field test: HomeTestSession originally fired
# deterrence exactly once per encounter (on _start_encounter()) and then let
# the animal linger unopposed until it left on its own or departure timeout
# closed the clip - fine for capturing footage, not for actually moving a
# boar that doesn't scare off a single roar. While an encounter stays active
# and still qualifying, _advance_encounter() now re-fires every time this
# many seconds have passed since the encounter's last fire, for as long as
# HOME_TEST_MAX_ENCOUNTER_S allows. Set just above both MCU-side actuator
# cooldowns (HORN_COOLDOWN_MS=10000, LED_COOLDOWN_MS=8000, device/mcu/src/
# config.h) so every retrigger is a real fire rather than one the rule gate
# silently refuses.
HOME_TEST_REFIRE_INTERVAL_S = 12.0

# 2026-09-10 field-trial run #1 hardening: hard ceiling on how many times a
# single encounter may fire deterrence, regardless of how long it stays
# qualifying. Run #1's runaway kept one "encounter" (stale frames of a
# frozen animal after the camera browned out) re-firing every
# HOME_TEST_REFIRE_INTERVAL_S for the full HOME_TEST_MAX_ENCOUNTER_S window,
# ~15 fires, and the repeated peak actuator draw is what sustained the
# battery sag. A real animal not moved by four escalating blasts over ~48s
# will not be moved by a fifth; past this count the encounter keeps
# recording and tracking but stops firing. Belt-and-braces alongside the
# camera-blind guard below - either one alone breaks the loop.
HOME_TEST_MAX_FIRES_PER_ENCOUNTER = 4

# Session-wide ceiling on protected (encounter) bytes, against ~15 GB free
# on /home/arduino. On reaching it the session STOPS PROTECTING new frames
# but keeps logging detections and keeps the ring rotating - the dataset is
# the irreplaceable part and it costs almost nothing to keep, whereas video
# is large and the first several encounters are the ones worth having.
# perception/storage.py's _warn_if_low_disk already warns below 500 MB
# headroom but never deletes anything; this is the actual stop.
#
# This counter is in-memory and resets to 0 on every container restart, so
# it has no idea how much prior-session data already sits on disk. The
# board's rootfs is 9.8 GB total with old bench-test encounters routinely
# eating multiple GB (confirmed 9 Sept: 4.5 GB from six days of dev
# testing, against only 3.2 GB physically free at the time) - so 8 GB is
# not a safe budget for THIS partition regardless of what's already
# written. Capped well under actual free space instead, so a long
# unattended overnight run degrades to "stopped protecting new frames"
# long before the OS ever sees ENOSPC.
HOME_TEST_MAX_TOTAL_BYTES = 3 * 1024 * 1024 * 1024  # 3 GB

# ---------------------------------------------------------------------------
# HOME_TEST_MODE fire/protect gate - raised above field thresholds
# ---------------------------------------------------------------------------
# These gate ONLY the decision to start an encounter, protect video and fire
# a deterrent. Detection logging is never gated by them.
#
# Why they are higher than the field's: the deployed detector's measured
# Boar false-positive rate is 27.54% at poll level *after* the shipped
# debounce and burst-majority gates, on a two-hour outdoor foliage run with
# no animals present (docs/qa/boar-gap-session-notes.md). At field
# thresholds, pointing this camera at a backyard all night means near-
# continuous false encounters, each one protecting video and firing a horn
# next to a sleeping household. Raising the bar for the fire/protect
# decision while logging everything unconditionally gives both a clean
# dataset and a survivable night.
#
# This is the one place this mode is deliberately less sensitive than the
# field. It is a threshold change on a shared code path, not a forked
# decision path: the same fuse -> decide -> bandit -> rule-gate chain runs
# either way, and it runs on exactly the same inputs.
# 9 Sept, that night's field test only: cut from 0.60 to 0.35 at the operator's
# explicit request - the deployed detector was reading real Boar-shaped
# signal in the 0.07-0.37 range all night without ever clearing 0.60 (see
# that night's detections.jsonl), so nothing was firing at all. 0.35 sat just
# above the highest ambient/false reading seen in that log.
#
# Cut again same night, 0.35 -> 0.20, at the operator's explicit follow-up
# request to fire faster and not worry about false positives - the goal is
# footage of a real reaction that night, not a clean dataset. 0.20 sits
# below most of the observed 0.07-0.37 noise floor on purpose: ambient/
# false readings will cross it often and that is accepted.
#
# 9 Sept, mid-night: raised back 0.20 -> 0.35 at the operator's request once the
# 0.20 false-positive rate proved unusable in the field.
#
# 10 Sept: field trial over - REVERTED to 0.60. Even at 0.35 the dawn
# twilight (05:34-06:29 IST) drove the detector into a degenerate full-frame
# "Boar" box at a flat ~0.37 every poll: 44 deterrent fires in 15 minutes on
# an empty backyard, and the household powered the board off. 0.35 cleared
# the still-dark noise floor but not the dawn one. Back at the field default
# and its measured 27.54% poll-level Boar false-positive basis.
#
# 23 Sept, that night only: cut back to 0.35 at the operator's explicit request -
# priority is catching every real animal for footage, false positives
# accepted for that night's run. Deliberately NOT dropped to 0.20: that
# exact value was already tried on 9 Sept and rolled back same night as
# "unusable" (fired continuously on noise). 0.35 is the highest-risk value
# with a real precedent of working overnight - but that precedent is
# night-only. The 10 Sept dawn-twilight runaway (44 fires/15min, board
# powered off) happened at exactly this value, 05:34-06:29 IST. If a run
# is still going into that window, raise this back to 0.60 before
# then or expect the same runaway.
#
# 23 Sept, minutes later: cut further, 0.35 -> 0.30, at the operator's explicit
# request, run live as a timed 30-minute trial with the fire rate watched
# for false positives. No prior run has a direct data point at 0.30 -
# the two adjacent known points are 0.35 (worked overnight, failed at dawn
# twilight) and 0.20 (rolled back same night as unusable, fired on noise
# continuously). 0.30 is an interpolation, not a re-run of a known-good
# value. If the 30-minute trial shows a high false-fire rate, raise back
# toward 0.35 first before going all the way to 0.60.
#
# 24 Sept, morning: the 10 Sept dawn-twilight runaway repeated at this
# value, in the same window (encounters opened 00:43-01:14 UTC = 06:13-
# 06:44 IST, 7 separate encounters in ~31 minutes, user confirmed repeated
# real horn/LED misfires as the morning light came up) - the household's
# own pre-committed rule ("more than 3 false fires -> raise, but no higher
# than the previous value") is triggered here. Raised back 0.30 -> 0.35,
# the cap that rule allows; NOT reverted to 0.60, per that same rule. 0.35
# is still not dawn-twilight-safe on its own precedent (10 Sept: 44 fires/
# 15min at this exact value in this exact window) - if the household hits
# another dawn misfire storm at 0.35, the next lever is
# HOME_TEST_FIRE_CONSECUTIVE_POLLS or a scheduled window, not a further
# threshold cut, since 0.35 is the floor this rule permits.
# 24 Sept, later same morning: the backlight-compensation camera fix
# (perception/camera.py's _assert_auto_exposure now forces backlight
# compensation to max at every open()) landed and was confirmed live -
# confidence on the same daytime scene that was fusing 0.674-0.818 and
# re-firing every ~15-20s dropped to a flat 0.260 immediately after the
# fix-carrying restart, with no further fires observed. With the root
# cause (overexposed foliage misread as Boar/Elephant) addressed at the
# source, raised back to the pre-experiment ceiling, 0.60, at the operator's
# explicit instruction ("raise to .60") - no longer holding at the 0.35
# cap the earlier "no higher than previous" rule required while the
# camera fix was unverified.
#
# 24 Sept, evening (board local ~18:00+ IST, night-exposure lock already
# engaged): the backlight-compensation fix turned out NOT to be the reason
# fires stopped after 0.60 went in - direct before/after frame comparison
# showed it made no visible difference to the blown-out daytime image, and
# a follow-up manual-exposure experiment to actually fix it made the image
# worse and was reverted (see perception/camera.py). The real daytime
# overexposure problem is still open. At the operator's explicit request,
# reverted to 0.30 - the value actually active for the whole of 23 Sept
# night's run (cut down from 0.35 within minutes of starting; not
# 0.60, which is last week's standing daytime default and not what any of
# 23 Sept night's encounters, including the confirmed real animal at
# 21:20 IST, were captured under). Night-only precedent: 0.30 ran all of
# 23 Sept night without incident and only failed at dawn twilight
# (00:43-01:14 UTC / 06:13-06:44 IST, 7 encounters/~31min, see the 24 Sept
# morning note above). MUST be raised back toward 0.35/0.60 before that
# window recurs tomorrow, or expect the same runaway.
#
# 29 Sept: raised to 0.70 at the operator's explicit request, temporary, as an
# immediate stopgap against a fresh false-positive spike. Not a root-cause
# fix - the same day's full-history query of detections.jsonl (439,708
# Elephant rows) found confidence is quantized onto a fixed ladder of ~27
# rungs roughly 0.0371 apart, and 0.30 sat just under two of them (0.3342,
# 0.3713), so ordinary background noise landing on either rung alone was
# enough to fire (Elephant carries no burst-majority gate). 0.70 sits
# between rungs 0.6684 and 0.7426, so only detections clearing the 0.7426
# rung or above now qualify - this cuts off legitimate distant/partial
# detections that would have landed on the excluded lower rungs, trading
# recall for an immediate stop to the noise. MUST be revisited (see the
# quantization-ladder discussion, not yet written up in docs/KNOWN_GAPS.md)
# rather than left here as a permanent value.
#
# 29 Sept, same night: raised again to 0.80 at the operator's explicit request -
# 0.70 wasn't enough, still seeing false positives. 0.80 sits between rungs
# 0.7798 and 0.8912, so it now also excludes the 0.7426/0.7798 rungs that
# 0.70 had let through - only the 0.8912 and 0.9283 rungs (and anything
# above) still qualify. Still the same temporary stopgap, not a fix.
#
# 29 Sept, evening: 0.65 with the vision model swapped from the 30 Aug
# champion to the 29 Sept Run F build (160 px, Boar/Elephant/Fox). The rung
# numbers above belong to the old model and do not carry over. Chosen on the
# board: replaying the 55 hand-labelled encounter clips from 23-29 Sept, F at
# 0.65 caught all 7 real fox visits and alarmed on none of the 47 false
# triggers, while the champion at 0.80 caught none of the foxes. On 81
# minutes of the empty daytime plantation F never scored above 0.56. See
# the 28 Sept vision model training log, section 10f.
#
# 29 Sept, night: 0.60 for the first night on Run F, so a fox visit is not
# lost to the margin and the night yields a clip to compare against. The same
# replay caught 7/7 foxes with no false clips at 0.60 as well; the 0.56
# empty-scene ceiling above is the reason not to go lower.
HOME_TEST_FIRE_MIN_CONFIDENCE = 0.60

# Consecutive qualifying polls before an encounter starts, against
# VISION_SPECIES_CONSECUTIVE_POLLS' 2 for Boar in the field. Was 3; cut to 2
# on 7 Sept 2026 after bench/vision_latency/poll_latency.py measured the
# real cost against the actual edge-impulse-linux-runner and a genuine
# encounter's frames: per-poll latency (p50 700ms at frame_count=3, p50
# 228ms at frame_count=1) already sits under HOME_TEST_INFERENCE_INTERVAL_S's
# 1.0s floor either way, so the floor - not inference speed - was the
# binding cost, and every consecutive poll adds exactly one more 1.0s floor
# wait, not "about a second" as the old estimate here guessed. Dropping to 2
# saves that one full poll (~1.0s) off the animal-appears-to-deterrent-
# responds window; the pre-roll buffer still makes it invisible in the saved
# clip either way, since those frames are already buffered and get
# protected retroactively. Trades one poll's worth of debounce margin for
# that latency - see docs/KNOWN_GAPS.md's inference-latency entry for the
# full measurement and the frame-count half of the fix, deliberately left
# at 3 pending its own decision.
#
# 8 Sept, that night only: cut further to 1 at the operator's explicit request -
# fire on the very first qualifying poll (still gated by
# HOME_TEST_FIRE_MIN_CONFIDENCE above), false positives accepted, because
# that night's goal was footage of a real reaction, not a clean dataset.
# This trades away the one poll of debounce margin the 7 Sept cut already
# reduced from 3 to 2 - a lone windblown-branch poll can now open an
# encounter and fire a deterrent on its own.
#
# 10 Sept: field trial over - REVERTED to 2. With this at 1 the 10 Sept dawn
# false-positive storm (see the note above HOME_TEST_FIRE_MIN_CONFIDENCE)
# opened a fresh encounter on every single qualifying poll.
#
# 11 Sept: despite the name, _advance_encounter() no longer requires these
# to land back to back - see HOME_TEST_FIRE_WINDOW_POLLS below for why and
# _advance_encounter()'s own docstring for the mechanism. This is still the
# count of qualifying polls required; only the "consecutive" part moved.
HOME_TEST_FIRE_CONSECUTIVE_POLLS = 2

# Size of the sliding window HOME_TEST_FIRE_CONSECUTIVE_POLLS is counted
# within, in polls (HOME_TEST_INFERENCE_INTERVAL_S apart) - replaces a
# strict back-to-back streak. Added 11 Sept 2026 after the 10-11 Sept
# overnight run's real Boar cluster (22:41:55-22:43:33Z, soil-digging
# ground-truth confirmed the next morning) cleared HOME_TEST_FIRE_MIN_CONFIDENCE
# at :23/:28/:33 - 5s apart, 4 non-qualifying polls between each hit - and
# never opened an encounter, because the previous streak design zeroed on
# every single miss. 6 polls (6s at the 1.0s inference interval) covers
# that exact gap with one poll of margin, without touching either lever
# that measurably controls Boar's false-positive rate: the burst-majority
# gate (VISION_SPECIES_BURST_MAJORITY_LABELS) and HOME_TEST_FIRE_MIN_CONFIDENCE
# itself are both unchanged, and HOME_TEST_FIRE_CONSECUTIVE_POLLS still
# requires that many genuinely qualifying polls, just not adjacent ones -
# a single isolated qualifying poll surrounded by silence still cannot
# open an encounter on its own, exactly as before.
#
# 11 Sept, later same day: widened 6 -> 15 at the operator's explicit request.
# Priority shifted from "survive the one observed 5s gap" to "get the
# complete empty-frame -> approach -> fire -> retreat -> empty-frame arc on
# every real animal" - a missed encounter-open costs the whole clip, not
# just one fire, since HOME_TEST_PREROLL_S/POSTROLL_S/DEPARTURE_TIMEOUT_S
# below only start protecting footage once an encounter actually opens.
# 15s gives roughly 2.5x the observed gap's margin. This still does not
# touch either false-positive lever (the burst-majority gate or
# HOME_TEST_FIRE_MIN_CONFIDENCE) and still requires the same count of
# genuinely qualifying polls - it only extends how far apart two of them
# may land, so the residual added risk is limited to two independently
# noisy qualifying polls coincidentally landing within 15s of each other,
# not a lowered bar for what counts as qualifying in the first place.
HOME_TEST_FIRE_WINDOW_POLLS = 15

# A detection whose box covers at least this fraction of the frame is dropped
# from the fire/protect gate (detection logging still records it unchanged).
#
# 10 Sept, added after field-trial run #1: the deployed detector has a
# recurring degenerate mode where it stops localising and returns a box at
# or near the full frame extent (x:0 y:0 w:CAMERA_FRAME_WIDTH
# h:CAMERA_FRAME_HEIGHT). detections.jsonl carries 1,745 such boxes between
# 7 and 10 Sept, ~70% of them labelled "Elephant" at confidence up to 1.00 -
# including the 01:22-01:31 IST "Elephant" burst on an empty backyard that
# no confidence floor alone would have stopped. A box that fills the frame
# carries no localisation information and cannot correspond to the threat
# geometry this camera is placed for (an animal at deterrence distance
# occupies a fraction of the field of view), so it is treated as a detector
# artefact, not a target. Set at 0.85 rather than ~1.0 to catch the near-
# full-frame variants while leaving genuine close-range large-animal boxes
# (measured max 0.84 area fraction across every real bench encounter to
# date) untouched. Boxes below the floor are unaffected: only 5 of 498
# poll-level "Boar" detections above HOME_TEST_FIRE_MIN_CONFIDENCE clear
# this bar, versus 437 of 1,096 "Elephant".
HOME_TEST_MAX_BOX_AREA_FRACTION = 0.85

# Consecutive polls with a frame-filling detection (see
# HOME_TEST_MAX_BOX_AREA_FRACTION above) before home_test.py treats the
# camera as possibly obstructed rather than just discarding one more
# detector artefact. Added 11 Sept 2026 after a ~40 minute stretch where
# the lens itself was physically covered: every poll returned a frame-
# filling "Elephant" at a near-constant confidence (39 of 42 samples read
# exactly 0.928, a flat reading no moving animal produces), correctly
# excluded from the fire gate the whole time, but with nothing surfacing
# that the camera itself had effectively gone blind. This is purely
# observational - see HomeTestSession._update_camera_covered_state() - it
# never reads or writes _advance_encounter's state, HOME_TEST_FIRE_WINDOW_POLLS,
# or anything else the fire path touches, so the instant a frame stops
# filling (a real animal at deterrence distance, or the obstruction
# clearing) detection resumes exactly as if this had never tripped. 30
# polls (30s at the 1.0s inference interval) is long enough that a single
# transient large-object pass does not trip it, short enough that a
# genuine obstruction is flagged promptly.
HOME_TEST_CAMERA_COVERED_STREAK_POLLS = 30

# Same streak, fed by either signal: a frame-filling detection (above) OR
# a near-uniform frame (HOME_TEST_CAMERA_COVERED_LOW_TEXTURE_STD, added
# 11 Sept 2026 for the partial-covering case the frame-filling check alone
# does not catch). One counter, one log, two independent ways to trip it.

# Where HomeTestSession logs camera-possibly-covered/clear transitions, one
# JSON line per transition (not per poll) - mirrors HOME_TEST_EXPOSURE_LOG_PATH's
# pattern below. Added alongside HOME_TEST_CAMERA_COVERED_STREAK_POLLS above.
HOME_TEST_CAMERA_COVERED_LOG_PATH = HOME_TEST_DIR / "camera_covered.jsonl"

# Grayscale standard deviation below which a frame reads as near-uniform
# (flat), for the low-texture half of the camera-covered check
# (HomeTestSession._burst_low_texture). Found live, 11 Sept 2026: a
# *partial* lens covering (hand/cloth over part of the lens, not the whole
# frame) never triggers HOME_TEST_MAX_BOX_AREA_FRACTION's frame-filling-box
# check - it instead produces varying, low-confidence, sub-threshold boxes,
# because the detector is reading noise off a mostly-flat image rather than
# one dominant artefact. That flatness shows up directly in the frame's own
# pixel statistics regardless of what the detector makes of it. Every frame
# in a poll's burst must read below this to count, so one frame with real
# texture (a genuine animal, or a covering that only reached part of the
# burst) does not contribute.
#
# 10.0 is a provisional estimate, not a measured bench value: this board
# was powered down for a hardware change before a covered-lens sample's
# grayscale std could be captured and compared against normal daylight/IR
# bench frames. Same purely-observational contract as
# HOME_TEST_CAMERA_COVERED_STREAK_POLLS - reads only its own streak
# counter, never the fire path - so a wrong threshold here can misreport
# the camera-covered log but cannot suppress or delay a real detection.
# Recalibrate against real frame std distributions once the board is back
# up, the same way HOME_TEST_MAX_BOX_AREA_FRACTION was tuned against real
# bench encounters.
HOME_TEST_CAMERA_COVERED_LOW_TEXTURE_STD = 10.0

# ---------------------------------------------------------------------------
# HOME_TEST_MODE exposure auto-lock (services/home_test.py, perception/night.py)
# ---------------------------------------------------------------------------
# home_test.py used to lock NIGHT_LOCKED_EXPOSURE once at camera open and
# never revisit it - correct only for a session that starts and stays dark.
# Found 6-7 Sept 2026: indoors under room lighting this drove the sensor to
# near-white, and the only fix available that night was the whole-session
# ELETECT_NIGHT_EXPOSURE_LOCK=0 kill switch. perception.night.ExposureAutoLock
# re-answers the day/night question periodically from live frames instead,
# using the same is_night() callable and threshold the field path already
# trusts (services/reflex_loop.py's vision-watch illumination block).

# How often to re-evaluate, not how often to look at a frame: the session's
# own inference poll already samples the buffer every
# HOME_TEST_INFERENCE_INTERVAL_S (1.0s) - re-running frames_are_night() on
# every one of those would burn an extra HSV conversion per poll for no
# benefit, since the scene does not change fast enough for that resolution
# to matter. 30s is fast enough to catch someone flipping a light switch
# mid-session without being noticeably slower than a human would notice it
# themselves.
HOME_TEST_EXPOSURE_RECHECK_INTERVAL_S = 30.0

# Consecutive agreeing re-evaluations required before flipping lock state.
# Without this, a single ambiguous reading right at the IR-cut filter's own
# transition point (the "ten minutes either side of the filter's own
# switch" perception/night.py's own docstring calls out) could flap the
# lock back and forth. 2 is the same debounce shape as
# HOME_TEST_FIRE_CONSECUTIVE_POLLS uses for detections - cheap insurance,
# unmeasured against a real dawn/dusk transition until the first overnight
# soak (see docs/KNOWN_GAPS.md).
HOME_TEST_EXPOSURE_FLIP_CONSECUTIVE = 2

# Minimum wall-clock gap between two actual lock()/restore() calls, on top
# of interval_s * flip_consecutive. Found live, 11 Sept 2026, Kothamangalam
# bench (partially covered lens): the policy locked to a fixed dark exposure,
# which made the frame read dark (median brightness ~126) and confirmed a
# further lock next check, then the restore made the same scene read bright
# (median brightness ~138, saturation 0.0 -> 36.0), confirming a restore -
# a self-sustaining 60s lock/restore/lock cycle (exactly
# interval_s * flip_consecutive), because each action changes the very
# brightness/saturation signal the next debounce evaluates, so a fixed
# consecutive-count debounce is trivially satisfied every half-cycle
# regardless of its size. Raising flip_consecutive or interval_s alone
# cannot fix this - each dwell state is internally consistent for its own
# full duration. This is a separate cooldown, measured from the last actual
# action (not the last re-evaluation): once flip_consecutive agrees on a
# direction, ExposureAutoLock still withholds the call if less than this
# many seconds have passed since the previous lock()/restore(), holding
# instead and letting the streak keep re-confirming. A real dusk/dawn
# transition (the module docstring's own "ten minutes either side" of the
# IR-cut filter's mechanical swap) is far slower than this, so genuine
# transitions are unaffected; a self-induced 60s cycle is not.
HOME_TEST_EXPOSURE_MIN_DWELL_S = 300.0

# Where ExposureAutoLock's lock/unlock decisions are logged, one JSON line
# per decision (wall_s, saturation reading, night answer, action taken,
# whether the write verified) - the record a morning review needs to match
# what the classifier decided against what the scene actually was doing.
HOME_TEST_EXPOSURE_LOG_PATH = HOME_TEST_DIR / "exposure_decisions.jsonl"

# ---------------------------------------------------------------------------
# HOME_TEST_MODE telemetry + stall watchdog (services/home_test.py)
# ---------------------------------------------------------------------------
# 9 Sept 2026: for an unattended overnight run there is no one present to
# notice a thread that is technically alive (is_healthy()'s original check)
# but stuck - e.g. wedged on a hung read - and therefore never advancing.
# Each loop stamps a monotonic heartbeat at the top of every iteration;
# is_healthy() also fails if any heartbeat is older than this, which turns
# a silent stall into the same hard process exit _run_guarded already uses
# for a crash, so the container's restart policy recovers it either way.
# 90s is generously above every real per-iteration cost in this module
# (capture has none, inference is HOME_TEST_INFERENCE_INTERVAL_S, and
# HttpVisionDetector/handle_footfall_event's own Bridge calls already carry
# their own sub-15s timeouts) - this is a backstop for the unmeasured case,
# not a tight bound on the measured ones.
HOME_TEST_STALL_TIMEOUT_S = 90.0

# ---------------------------------------------------------------------------
# HOME_TEST_MODE camera-blindness guard + auto-recovery (services/home_test.py)
# ---------------------------------------------------------------------------
# 2026-09-10, field-trial run #1: a battery brown-out reset the USB link
# mid-encounter and the camera stopped delivering frames. The capture loop
# skipped the None grabs (correct) but the frame deque kept serving the
# handful of frames captured just before the failure; the inference loop
# kept "detecting" the animal on those frozen frames and _advance_encounter
# kept re-firing deterrence at a scene nothing could actually observe -
# which sagged the battery further and held the camera down. The stall
# watchdog could not see it because the capture thread was still ticking its
# heartbeat every iteration (a fast None grab is still an iteration).
#
# Guard: past HOME_TEST_CAMERA_STALE_S with no fresh frame, the buffer is
# treated as blind - no detection on it can qualify, nothing fires, and any
# open encounter is closed immediately. Set above one inference interval
# plus a few capture frames so a single slow poll never trips it.
HOME_TEST_CAMERA_STALE_S = 6.0

# No good frame for this long -> the capture loop attempts an in-place
# Camera.reopen() (release + re-open the V4L2 handle on the re-enumerated
# node). Recovers the common USB link-reset case with no process or board
# restart.
HOME_TEST_CAMERA_REOPEN_AFTER_S = 5.0

# Minimum gap between reopen attempts - a device mid-re-enumeration needs
# time to settle, not to be thrashed.
HOME_TEST_CAMERA_REOPEN_MIN_INTERVAL_S = 20.0

# Camera still not delivering this long after it first failed, despite the
# reopen attempts -> the capture loop drops a reboot-request sentinel file
# for the host-side watchdog cron to act on. The app container is
# unprivileged and cannot reboot the board itself. Long enough that an
# ordinary USB storm rides itself out first.
HOME_TEST_CAMERA_REBOOT_AFTER_S = 240.0

# Never request a second reboot within this window of the last one. The
# marker is written outside the container tmpfs (under HOME_TEST_DIR, a bind
# mount) so it survives the very reboot it triggers and cannot boot-loop
# the board.
HOME_TEST_CAMERA_REBOOT_MIN_INTERVAL_S = 1800.0

# Sentinel the capture loop writes to ask the host watchdog to reboot, and
# the persisted marker that rate-limits it. Plain files, JSON payload
# ({"wall_s": ..., "down_for_s": ...}); the watchdog also applies its own
# freshness + interval checks before acting.
HOME_TEST_CAMERA_REBOOT_REQUEST_PATH = HOME_TEST_DIR / "reboot-request"
HOME_TEST_CAMERA_REBOOT_MARKER_PATH = HOME_TEST_DIR / "last-reboot-request.json"

# Manual override: touching this file (a bind-mounted path, no docker exec
# or container restart needed) forces an immediate fire+record on the next
# inference poll, bypassing the vision/confidence gate entirely. Added
# 23 Sept 2026 after a live sighting (a cat) had no fast way to force a
# recorded deterrence fire - the only path until then was editing
# HOME_TEST_FIRE_MIN_CONFIDENCE live and restarting the container, far too
# slow for an animal that is only in frame for seconds. From the board:
#   touch python/data/home_test/manual-fire-request
# Consumed (deleted) the instant it is seen, so a stale touch can never
# cause a second unintended fire later. See
# HomeTestSession._check_manual_fire_trigger for the encounter-machine
# reuse this drives.
HOME_TEST_MANUAL_FIRE_TRIGGER_PATH = HOME_TEST_DIR / "manual-fire-request"

# One JSONL line per interval: model inference latency for the most recent
# poll plus a best-effort board-resource snapshot (CPU temp, available
# memory, load average, free disk). Read by nothing on-device - this is
# purely the performance record an overnight unattended run would otherwise
# have no evidence of afterward (model speed, thermal/memory headroom on
# the UNO Q across a full night), not a control input.
HOME_TEST_TELEMETRY_PATH = HOME_TEST_DIR / "telemetry.jsonl"
HOME_TEST_TELEMETRY_INTERVAL_S = 30.0


# ---------------------------------------------------------------------------
# Camera-labelled seismic capture (ADR 0035)
# ---------------------------------------------------------------------------
# Mirrors of device/mcu/src/config.h. Every one of these is read back out of
# that file by tests/test_config.py rather than trusted here - three of the
# four describe how bytes are laid out on the wire, and a silent divergence
# would not fail, it would decode garbage that looks like ground motion.

# device/mcu/src/config.h's SEISMIC_CAPTURE_BATCH_SAMPLES - how many samples
# arrive in one report_seismic_batch notify.
SEISMIC_CAPTURE_BATCH_SAMPLES = 32

# device/mcu/src/config.h's SEISMIC_SAMPLE_RATE_HZ. Nominal, not measured:
# GEOPHONE_WINDOW_STALE_MS is derived against a real 226.98 Hz field rate, so
# anything that needs true elapsed time must use the arrival timestamps this
# module records, never this number multiplied by a sample count.
SEISMIC_SAMPLE_RATE_HZ = 250

# device/mcu/src/config.h's SEISMIC_WINDOW_SAMPLES - the MCU's own STA/LTA
# window length, kept here because the recorder slices the stream into
# window-aligned records to match what the MCU believed at trigger time.
SEISMIC_WINDOW_SAMPLES = 512

# device/mcu/src/config.h's ADS1115_LSB_VOLTS. The batch carries the ADC's
# raw int16 conversions, so this is the only thing that turns them back into
# volts. Stored alongside every record for exactly that reason: a corpus of
# counts with no scale is not re-analysable later.
SEISMIC_LSB_VOLTS = 0.0000625

# How much ground motion the stream keeps in memory. 60 s at the nominal
# rate, which covers the 45 s extended vision watch
# (VISION_WATCH_EXTENDED_S) end to end with room for the recorder to drain
# it afterwards rather than racing the watch. At 2 bytes a sample this is
# ~30 kB - negligible next to one video frame.
SEISMIC_STREAM_RETAIN_S = 60.0
SEISMIC_STREAM_CAPACITY_SAMPLES = int(SEISMIC_STREAM_RETAIN_S * SEISMIC_SAMPLE_RATE_HZ)

# A forward jump larger than the buffer could ever hold is not a gap worth
# recording - there is nothing on either side of it to join. It is the MCU
# having restarted (its sample counter resets to 0) or the stream having
# been off for minutes. Either way the buffer is dropped and collection
# starts clean, because a "gap" of four billion samples in a record is
# noise, not provenance.
SEISMIC_STREAM_MAX_GAP_SAMPLES = SEISMIC_STREAM_CAPACITY_SAMPLES

# ---------------------------------------------------------------------------
# Camera-labelled seismic dataset (ADR 0035, perception/seismic_dataset.py)
# ---------------------------------------------------------------------------
# One JSON record per vision watch: the ground motion the geophone saw, the
# boxes the camera drew over the same seconds, and the bucket the camera's
# answer puts the record in. The whole point of the exercise is that the
# label is free - the camera is already open, already looking at the animal
# that made the ground motion, and already finished before the record is
# written.

# Written beside the captures rather than into them. Module-relative for the
# same reason CAPTURE_DIR is - it lands inside the App's own folder on the
# board, on the 18G /home/arduino partition, not on the ~1G root overlay -
# but a separate directory, because the retention rules are different: a
# capture is evidence about one event and a record is one row of a training
# corpus, and the first must never be evicted to make room for the second.
SEISMIC_DATASET_DIR = _MODULE_DIR / "data" / "seismic"

# Master switch. Default ON, unlike EVENT_VIDEO_ENABLED, because this path
# cannot affect an animal: it reads a buffer that is already in memory and
# writes a file after every actuator call has returned. The thing that
# actually decides whether records appear is whether report_seismic_batch is
# registered at all (device/mpu/main.py), and nothing is registered today -
# so with no stream the recorder writes nothing and logs that it had
# nothing, which is the honest state of the feature until the Bridge
# registration comes up on hardware.
SEISMIC_DATASET_ENABLED = True

# How far back before the trigger a record reaches. The STA/LTA detector
# fires *after* the onset it detected - that is what a short-term average
# crossing a long-term one means - so a record that started at the trigger
# would be missing the first footfall of the approach, and the first
# footfall is the cleanest impulse in the whole encounter. Five seconds at
# an elephant's walking cadence is several strides of lead-in.
SEISMIC_DATASET_PRE_ROLL_S = 5.0

# Total size the dataset directory may occupy before the writer starts
# evicting. INVENTED, like CAPTURE_LOW_DISK_HEADROOM_BYTES above and for the
# same reason - there is no measured encounter rate for a real site yet.
# Sized against what a record costs: 50 s of 250 Hz int16 is ~25 kB of
# samples, ~34 kB base64, call it 40 kB with the track and the metadata, so
# 256 MB is on the order of 6000 records. At even a hundred triggers a night
# that is two months of unattended collection, which is longer than the
# interval between site visits.
SEISMIC_DATASET_MAX_BYTES = 256 * 1024 * 1024  # 256 MB

# Which buckets are given up first when the cap is hit, hardest-to-replace
# last. `unlabelled` goes first because it is the one bucket that can never
# be trained on - the camera could not look, so nothing in it has a label to
# learn from. `ambiguous` next: two species in one frame is real data but
# needs hand-adjudication before it is worth anything. `no_animal` is a free
# negative that every quiet night regenerates. The species buckets are last
# and are evicted oldest-first among themselves, because a confirmed
# elephant on a geophone is the entire scarce resource this corpus exists to
# accumulate - see the plan's note that dataset volume, not dataset quality,
# is the residual risk.
SEISMIC_DATASET_EVICTION_ORDER = ("unlabelled", "ambiguous", "no_animal")


# ---------------------------------------------------------------------------
# Derived fields: range, gait and behaviour (ADR 0035, perception/kinematics.py)
# ---------------------------------------------------------------------------
# Everything below turns measurements the node already has - box heights
# across a watch, and the impact train in the waveform - into the three
# questions a future seismic model has to answer from ground motion alone:
# what animal, how far, doing what. Every one of these numbers is a
# threshold over a measurement that is itself stored in the record, so a
# later reader can re-derive all of it without recapturing anything. That
# is the whole reason the raw waveform and the raw boxes are kept.

# Horizontal field of view of the lens, in degrees, as the product listing
# states it. A specification, not a calibration - which is exactly why
# every range derived from it is stamped `calibrated: false` until
# CAMERA_CALIBRATION_PATH below exists.
CAMERA_HORIZONTAL_FOV_DEG = 95.0

# Written by scripts/calibrate_camera.py from a set of chessboard images
# taken through this enclosure's own window, and read once at writer
# construction. Absent is the normal state and not an error: the nominal
# focal length is used, `calibrated` stays false on every record, and a
# calibration done later can re-derive ranges from the stored boxes rather
# than invalidating the corpus collected before it.
CAMERA_CALIBRATION_PATH = _MODULE_DIR / "data" / "camera_calibration.json"

# A box within this many pixels of any frame edge is truncated - part of
# the animal is outside the image, so its height is a lower bound and the
# range derived from it would read as too far. Excluded from ranging and
# counted, rather than dropped silently: a watch where most frames are
# truncated is a watch where the animal was close, and that is worth
# knowing even when the numbers are not usable.
RANGE_EDGE_MARGIN_PX = 4

# A box covering at least this fraction of the frame is excluded from
# ranging too, for the reason HOME_TEST_MAX_BOX_AREA_FRACTION gives at
# length: the deployed detector has a degenerate mode where it stops
# localising and returns a frame-filling box, and a frame-filling box
# carries no localisation information to range from. Same value, chosen the
# same way, kept as its own name because the two gates are free to diverge
# - that one decides whether to fire a horn and this one decides whether a
# measurement is usable.
RANGE_MAX_BOX_AREA_FRACTION = 0.85

# Smallest box height worth ranging from, in pixels. Below this one pixel
# of box-edge noise is several percent of the height and therefore several
# percent of the range, and the trajectory fit starts following the
# detector rather than the animal.
RANGE_MIN_BOX_HEIGHT_PX = 24

# Fewest rangeable frames, and shortest span between the first and last of
# them, before a trajectory is called at all. Two boxes a tenth of a second
# apart can show any slope you like; these make "unknown" the honest answer
# instead of a confident one.
RANGE_MIN_TRAJECTORY_FRAMES = 3
RANGE_MIN_TRAJECTORY_SPAN_S = 2.0

# Below this the range is not changing fast enough to call, in fractional
# range change per second - so 0.02 is 2% of the current distance per
# second, which at 30 m is 0.6 m/s. Fractional rather than absolute because
# the fractional rate is the quantity the unknown animal height cancels
# out of, and so the only one measured rather than estimated.
BEHAVIOUR_STATIONARY_RATE_PER_S = 0.02

# Near/mid/far band edges in metres, applied to the median absolute range
# of a track. Bands and not metres anywhere user-facing: the underlying
# number is +-30-50%, which is good enough to say "close" and not good
# enough to say "22 m".
RANGE_BAND_EDGES_M = (15.0, 40.0)

# The two speed estimates - cadence x stride from the waveform, and the
# rate of change of absolute range from the boxes - are independent and
# both approximate. They are called in agreement when the larger is within
# this factor of the smaller. A disagreement is not an error and does not
# suppress anything; it is recorded as a quality flag, because the records
# where two independent measurements of the same animal disagree are
# exactly the ones worth looking at by hand.
BEHAVIOUR_SPEED_AGREEMENT_FACTOR = 2.5

# -- impact detection -------------------------------------------------------
#
# An impact is a footfall. Cadence across several of them is the strongest
# elephant/boar/fox discriminator available from seismic alone, and it is
# the thing a single 2 s window cannot see - which is why the recorder
# stitches the whole watch.

# Envelope window for the impact detector, in seconds. Long enough to
# smooth the carrier out of a footfall's ring-down, short enough that two
# steps a quarter-second apart stay two bumps.
GAIT_ENVELOPE_WINDOW_S = 0.02

# An impact is where the envelope crosses the noise floor by this many
# robust standard deviations. Median and MAD rather than mean and stdev
# because the impacts themselves are in the signal being measured, and a
# mean-based floor rises with the thing it is trying to detect.
GAIT_IMPACT_SIGMA = 6.0

# Absolute floor under the threshold above, in ADC counts. On genuinely
# quiet ground the MAD can collapse toward zero and six sigma becomes
# noise; this keeps quantisation from being read as a herd.
GAIT_MIN_IMPACT_COUNTS = 12.0

# Two threshold crossings closer together than this are one impact. A
# footfall rings and reflects, so the envelope can dip below the threshold
# and back within a few milliseconds; this is short enough to leave a
# running fox's real steps separate.
GAIT_REFRACTORY_S = 0.06

# Fewest impacts before a cadence is reported. Two impacts give one
# interval and no way to tell a gait from a coincidence, so the interval
# statistics need at least three.
GAIT_MIN_IMPACTS = 3

# Inter-impact intervals outside this range are not a gait: faster than the
# low end is ringing the refractory period missed, slower than the high end
# is two separate events that happen to be in one record.
GAIT_MIN_INTERVAL_S = 0.10
GAIT_MAX_INTERVAL_S = 3.0
