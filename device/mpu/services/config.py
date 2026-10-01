"""MPU-side configuration constants.

Single source of every Bridge timeout, retry policy, and filesystem path the
cognition layer depends on (ENGINEERING_CONVENTIONS.md 2), mirroring the
shape of device/mcu/include/config.h: one rationale comment per constant, no
magic numbers inline in logic files.

Two things this file deliberately does NOT hold:
- Actuator burst caps, cooldowns and gain ceilings. Those are enforced
  on-MCU (device/mcu/include/config.h) and the MPU only ever sees the
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
SCHEMA_VERSION = 4

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
            against the closed vocabulary the routing table uses; the
            backend does not consult this column yet, and wiring
            send-alert's audienceFor() to agree with it is what closes
            the loop.
    """

    label: str
    event_class: int
    bandit_policy: str = ""
    deterrence_content: str = ""
    alert_audience: str = "dashboard_only"

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
        ),
        Species(
            label="Boar",
            event_class=2,
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
# can ride out. INVENTED counts - no real-world open-failure-rate data
# backs these numbers yet.
CAMERA_OPEN_RETRIES = 3
CAMERA_OPEN_RETRY_BACKOFF_S = 2.0

# Default burst size and inter-frame spacing for capture_burst(). 0.0
# interval means "as fast as the device delivers," not a real-time target.
# Both INVENTED - no detector-side timing requirement drives these yet.
CAMERA_BURST_FRAMES = 5
CAMERA_BURST_INTERVAL_S = 0.0

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
VISION_INFERENCE_URL = "http://127.0.0.1:1337"

# Per-frame socket timeout for one detect call. Bench-measured
# classification time on the real board was ~20ms (28 Aug, real image over
# the LAN); 2.0s is a generous multiple of that, not a tuned figure -
# INVENTED, the same "bounded deliberately short so a hung call can't hang
# the whole event" reasoning as BRIDGE_CALL_TIMEOUT_S above, just guarding a
# different transport.
VISION_INFERENCE_TIMEOUT_S = 2.0

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
# The real board classifies at a measured 138ms mean per frame (~5.7 FPS
# end to end across 123 live frames, 29-30 Aug - ml/vision/README.md), so a
# VISION_CHECK_FRAME_COUNT=3 poll costs roughly 0.4s of inference and this
# leaves the rest of each second to the H.264 encoder sharing the same four
# A53 cores. Polling flat out instead would give about five times the
# attempts at a target that takes tens of seconds to cross a 95-degree
# field of view (hardware/cad/enclosure-design-concept.md) - very little
# extra recall for several times the CPU and the power behind it. INVENTED
# as a ratio; the 138ms it is sized against is measured.
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
VISION_SPECIES_CONSECUTIVE_POLLS: dict[str, int] = {"Boar": 2}

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
VISION_SPECIES_BURST_MAJORITY_LABELS: tuple[str, ...] = ("Boar",)

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
# logged and settled on seismic alone. There is no footfall uplink on this
# device yet to hold or release (the LoRa module is not joining -
# docs/KNOWN_GAPS.md), so "seismic warns, vision fires" is today only half
# implemented, and the implemented half is the fire gate.
#
# False restores the pre-ADR-0022 behaviour: fire whenever decide() says
# alert, whatever the camera saw.
DETERRENT_REQUIRES_VISION_CONFIRMATION = True

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
