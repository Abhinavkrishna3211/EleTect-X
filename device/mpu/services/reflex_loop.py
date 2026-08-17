"""The real sense -> fuse -> decide -> actuate loop (CONTEXT.md 4).

This is the wiring, not a stub: cognition.fusion.fuse() and
cognition.decision.decide() are both real, tested pure functions, and this
module is the imperative shell around them (ENGINEERING_CONVENTIONS.md 2) -
it owns logging and the one real side effect (a drive_horn Bridge.call()).
The Bridge.call itself is injected as a callable rather than imported
directly, so this module stays importable and testable on a dev laptop with
no board attached - the same discipline perception/camera.py uses for cv2
(function-local import) and bridge/rpc.py uses for arduino.app_utils (never
imported at module scope there either). device/mpu/main.py is the only place
that wires the real Bridge.call in; tests inject a recording fake instead
(tests/test_reflex_loop.py, mirroring tests/test_fusion.py's pattern of
asserting on a returned result, not on log output).

Two of the three fusion modalities are not wired in yet, by design, not
oversight:

- **Vision**: no detector exists (perception/camera.py is capture-only, no
  pixel -> log-odds model - cognition/fusion.py's own module docstring
  names this a future build call). Always passed to fuse() as unavailable.
- **Acoustic**: report_acoustic_event's classifier output (gunshot/
  chainsaw/vehicle/animal_call/ambient) has no defined mapping onto
  elephant-presence log-odds, and ADR 0007 5 routes gunshot to a direct
  LoRa alert that bypasses fusion entirely - a routing path this repo has
  not built yet (comms/ is empty). handle_acoustic_event() logs the event
  for visibility only; it never reaches fuse(). See docs/KNOWN_GAPS.md.

Only seismic is wired end-to-end: the MCU's own on-board footfall model
already reports a probability (schema.md's report_footfall_event), and
converting that into fusion's log-odds input via cognition.fusion.logit()
is a direct, non-invented transformation - not a new detector this module
had to build.

SAFE_MODE (default on) is the dry-run gate: when true, an alert decision is
logged but drive_horn is never called. Read once at import time from the
ELETECT_SAFE_MODE environment variable, so flipping it for a live session is
an explicit, visible operational step (`export ELETECT_SAFE_MODE=0`), never
a silent code default change - this mirrors device/mcu/src/config.h's own
"gated behind a flag, defaults to the safe state" discipline for the
fire-test harness and seismic debug-stream flags.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Protocol

from bridge.rpc import AcousticClass
from cognition import config as cognition_config
from cognition.decision import Decision, decide
from cognition.fusion import FusionResult, Modality, ModalityReading, fuse, logit
from services import config as services_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Safety gate
# ---------------------------------------------------------------------------

# Default-on dry run: only an explicit ELETECT_SAFE_MODE=0 in the process
# environment disables it. Read once at import time, not per call, so one
# log line at startup (main.py) can honestly state which mode this run is
# in - a value that could change mid-run would make that line a lie.
SAFE_MODE = os.environ.get("ELETECT_SAFE_MODE", "1") != "0"

# ---------------------------------------------------------------------------
# Alert threshold - INVENTED, see docs/KNOWN_GAPS.md
# ---------------------------------------------------------------------------

# cognition/config.py deliberately holds no alert threshold: ADR 0001's
# Consequences section says that number needs real field-accuracy figures
# (seismic ~70-75%, vision ~70-85%) this project doesn't have yet, and
# services/config.py's own docstring carves out "risk thresholds" as
# something that belongs to cognition/, not to it either - so there is no
# existing config module willing to hold this constant honestly. It lives
# here, next to its one real caller, instead of hidden behind either of
# those disclaimers.
#
# 0.5 - the fused probability's own uninformative midpoint - was chosen as
# the least presumptuous placeholder available, not a tuned figure: it adds
# no additional skepticism or credulity beyond what L_PRIOR and the
# per-modality weights/baselines already encode. Logged as an open gap, not
# closed by adding this constant - see docs/KNOWN_GAPS.md.
ALERT_PROBABILITY_THRESHOLD = 0.5

# ---------------------------------------------------------------------------
# Placeholder deterrence request - INVENTED, see docs/KNOWN_GAPS.md
# ---------------------------------------------------------------------------

# Which actuator(s) to fire and at what gain/duration is the contextual
# bandit's job once it exists (cognition/fusion.py module docstring); until
# then this loop drives the horn only (the primary audible deterrent) and
# requests the wire protocol's own maximum - 100.0 pct (schema.md's
# documented 0-100 gain_pct range) and 65535 ms (duration_ms's uint16
# ceiling) - rather than inventing a specific mid-range gain/duration
# figure. device/mcu/src/rule_gate.cpp already clamps any out-of-bounds
# request down to the MCU's real, separately-configured caps
# (HORN_GAIN_MAX_PCT / HORN_BURST_MAX_MS, device/mcu/src/config.h)
# regardless of what is asked for, and services/config.py's own docstring
# is explicit that those real caps deliberately do not get duplicated on
# the MPU side - so "ask for the protocol max, let the MCU clamp it" avoids
# inventing a second, unreviewed limit rather than just moving the
# invention somewhere else. LED/IR are not driven at all yet - same gap.
ALERT_HORN_GAIN_PCT = 100.0
ALERT_HORN_DURATION_MS = 65535


class DriveHornFn(Protocol):
    """Callable shape matching bridge.rpc.drive_horn's real signature."""

    def __call__(self, schema_version: int, gain_pct: float, duration_ms: int) -> bool:
        """Request a horn burst; returns the ack drive_horn's own contract defines."""
        ...


@dataclass(frozen=True)
class FootfallOutcome:
    """What one handle_footfall_event() call decided and did.

    Returned (rather than left as a side effect only) so tests can assert on
    it directly, matching tests/test_fusion.py's pattern of asserting on a
    returned result rather than on log output.

    Attributes:
        fusion: The FusionResult fuse() produced for this event.
        decision: The Decision decide() produced for this event.
        horn_ack: drive_horn's returned ack, or None if it was never called
            (no alert, or SAFE_MODE suppressed the call).
    """

    fusion: FusionResult
    decision: Decision
    horn_ack: bool | None


def _seismic_log_odds(probability: float) -> float:
    """Convert the MCU's on-board footfall probability into fusion's log-odds input.

    logit() rejects the closed interval's endpoints (0.0 and 1.0) - both are
    representable float values report_footfall_event's wire probability
    could in principle carry, even though the MCU's own model realistically
    saturates just short of them. Clamping into an epsilon-narrowed open
    interval before calling logit() is a numerical safety guard here (same
    category as fusion.sigmoid()'s own two-branch overflow handling), not a
    policy choice - it changes nothing for any probability logit() would
    already have accepted unclamped.

    Args:
        probability: report_footfall_event's `probability` field, expected
            in [0.0, 1.0].

    Returns:
        The log-odds logit() returns for the epsilon-clamped probability.
    """
    epsilon = 1e-9
    clamped = min(max(probability, epsilon), 1.0 - epsilon)
    return logit(clamped)


def handle_footfall_event(
    schema_version: int,
    probability: float,
    sta_lta_ratio: float,
    feature_vector: list[float],
    *,
    drive_horn: DriveHornFn,
    safe_mode: bool = SAFE_MODE,
    threshold: float = ALERT_PROBABILITY_THRESHOLD,
) -> FootfallOutcome:
    """Sense -> fuse -> decide -> actuate for one report_footfall_event notify.

    Precondition: none - schema_version mismatches are logged, not raised,
    matching report_footfall_event's own notify contract (bridge/rpc.py):
    the MCU never reads a return value from this path, so raising here would
    only crash the MPU's own event loop over a field it cannot act on
    anyway. Never blocks past one drive_horn Bridge.call()
    (services.config.BRIDGE_CALL_TIMEOUT_S, enforced inside the injected
    drive_horn, not here), or not at all when safe_mode is true or no alert
    fires.

    Args:
        schema_version: As received from the MCU; logged if it does not
            match services.config.SCHEMA_VERSION.
        probability: The on-MCU footfall model's confidence, 0-1.
        sta_lta_ratio: STA/LTA ratio at the moment of trigger - logged for
            explainability, not otherwise used (fuse() takes log-odds, not
            a raw ratio).
        feature_vector: The 8 features behind `probability` - logged for
            explainability only, same reason as sta_lta_ratio.
        drive_horn: Callable matching bridge.rpc.drive_horn's signature.
            Injected so this function needs no board attached to test -
            device/mpu/main.py wires the real Bridge.call in; tests pass a
            recording fake.
        safe_mode: When true (the default, SAFE_MODE), an alert decision is
            logged but drive_horn is never called.
        threshold: Passed to cognition.decision.decide(). Defaults to
            ALERT_PROBABILITY_THRESHOLD (see that constant's own comment).

    Returns:
        A FootfallOutcome carrying the fusion result, the decision, and the
        horn ack (None if drive_horn was never called).
    """
    if schema_version != services_config.SCHEMA_VERSION:
        logger.warning(
            "report_footfall_event: schema_version mismatch (got %d, expected %d)",
            schema_version,
            services_config.SCHEMA_VERSION,
        )

    readings = [
        ModalityReading(Modality.SEISMIC, _seismic_log_odds(probability), available=True),
        # Acoustic/vision: no wired detector yet - see module docstring.
        ModalityReading(Modality.ACOUSTIC, 0.0, available=False),
        ModalityReading(Modality.VISION, 0.0, available=False),
    ]
    fusion_result = fuse(readings, cognition_config.DEFAULT_FUSION_PARAMS)
    decision = decide(fusion_result, threshold)

    logger.info(
        "footfall event: mcu_probability=%.3f sta_lta_ratio=%.3f fused_P=%.3f "
        "alert=%s used=%s dropped=%s feature_vector=%s",
        probability,
        sta_lta_ratio,
        fusion_result.probability,
        decision.alert,
        [m.value for m in fusion_result.used],
        [m.value for m in fusion_result.dropped],
        feature_vector,
    )

    if not decision.alert:
        return FootfallOutcome(fusion=fusion_result, decision=decision, horn_ack=None)

    if safe_mode:
        logger.info(
            "[SAFE_MODE] would call drive_horn(schema_version=%d, gain_pct=%.1f, "
            "duration_ms=%d) - not calling (dry run)",
            schema_version,
            ALERT_HORN_GAIN_PCT,
            ALERT_HORN_DURATION_MS,
        )
        return FootfallOutcome(fusion=fusion_result, decision=decision, horn_ack=None)

    ack = drive_horn(schema_version, ALERT_HORN_GAIN_PCT, ALERT_HORN_DURATION_MS)
    logger.info("drive_horn ack=%s", ack)
    return FootfallOutcome(fusion=fusion_result, decision=decision, horn_ack=ack)


def handle_acoustic_event(
    schema_version: int,
    class_label: AcousticClass,
    confidence: float,
    capture_ref: int,
) -> None:
    """Log one report_acoustic_event notify. Does not reach fuse() - see module docstring.

    Precondition: none - schema_version mismatches are logged, not raised,
    same reasoning as handle_footfall_event(). Never blocks: logging only,
    no Bridge call on this path.

    Args:
        schema_version: As received from the MCU; logged if it does not
            match services.config.SCHEMA_VERSION.
        class_label: One of bridge.rpc.AcousticClass's values.
        confidence: Classifier confidence, 0-1.
        capture_ref: Index into the MCU's raw-window ring buffer.

    Returns:
        None - matches report_acoustic_event's own notify contract.
    """
    if schema_version != services_config.SCHEMA_VERSION:
        logger.warning(
            "report_acoustic_event: schema_version mismatch (got %d, expected %d)",
            schema_version,
            services_config.SCHEMA_VERSION,
        )
    logger.info(
        "acoustic event: class_label=%s confidence=%.3f capture_ref=%d "
        "(not fused - no elephant-relevant mapping defined yet, see docs/KNOWN_GAPS.md)",
        class_label.value,
        confidence,
        capture_ref,
    )
