"""Orchestrates one acoustic check: capture -> health -> classify -> route.

This is the thin seam between the two new capture/inference modules
(perception/microphone.py, perception/acoustic_detector.py) and the
routing that already exists and is already tested
(services/reflex_loop.handle_acoustic_event, ADR 0007 5). It deliberately
contains no routing logic of its own: which class alerts, which class
fuses, and which fuses as unavailable is settled in reflex_loop and stays
settled there, so there is exactly one place that decides what an acoustic
class means.

It lives in its own module rather than inside reflex_loop.py because it
owns a failure mode reflex_loop has no concept of - a microphone that is
electrically fine and acoustically dead - and because the capture side is
worth testing without importing the whole reflex loop.

Why the acoustic path is separate from the footfall path
--------------------------------------------------------
It would be natural to fold an acoustic check into handle_footfall_event()
the way the vision check was folded in, so a seismic trigger wakes both
sensors. That is not done, and the reason is cost rather than taste:
Studio's own estimate for this impulse on the QRB2210 is 4,134 ms for the
classifier block alone (float32, unoptimised; the custom log-mel block is
unestimated because Studio cannot profile a custom block). The vision
watch loop polls the same four cores at roughly 138 ms a frame across a
window of up to 45 s. Dropping a four-second blocking classify into that
loop would punch a visible hole in exactly the watch window that ADR 0022
sized to catch an elephant walking 140 m. Until a quantised model brings
that figure down, an acoustic check runs on its own schedule and its
result reaches fusion as its own event.

What a broken microphone does
-----------------------------
Reports ACOUSTIC unavailable, and never classifies. A clip that fails
perception.microphone.assess_health is not handed to the model at all,
because the interesting failure - a dead LR44 in the BY-M1 - produces
frames that are well-formed and near-silent, which the model will happily
call `ambient` with high confidence. Fusion can drop a modality that says
"I am not here". It has no defence against one that says "there is
nothing here" when the truth is "I cannot tell".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from bridge.rpc import AcousticClass
from perception.acoustic_detector import (
    AcousticClassifyFn,
    AcousticDetectionError,
    AcousticResult,
)
from perception.microphone import AudioClip, MicrophoneError, assess_health
from services import config as services_config
from services.reflex_loop import (
    SAFE_MODE,
    AcousticOutcome,
    SendLoraAlertFn,
    StartVisionEventFn,
    handle_acoustic_event,
)

logger = logging.getLogger(__name__)

# handle_acoustic_event()'s `capture_ref` is documented as an index into
# the MCU's raw-window ring buffer, because when that signature was written
# the microphone was going to be on the MCU (ADR 0009). It is not - see
# ADR 0028 - and on this path there is no MCU ring buffer and no index into
# one. Rather than invent a plausible-looking integer, every MPU-originated
# event carries this sentinel, so a log line that shows capture_ref=-1 is
# saying something true ("captured on the Linux side") rather than
# something false ("MCU ring slot 0"). The parameter is kept rather than
# removed because the MCU path may yet return for the always-on gunshot
# detector (ADR 0009's analog -> ADC4 -> LPBAM route), which would
# genuinely have a ring index.
MPU_CAPTURE_REF = -1


class MicrophoneProtocol(Protocol):
    """Callable shape this module needs from a microphone.

    Structural rather than perception.microphone.Microphone itself,
    matching the convention every other injected dependency in
    services/reflex_loop.py follows - a test fake needs no ALSA device and
    no arecord.
    """

    def capture(self, duration_s: float) -> AudioClip:
        """Record `duration_s` of audio, or raise MicrophoneError."""
        ...


@dataclass(frozen=True)
class AcousticCheckOutcome:
    """What one run_acoustic_check() call established, including nothing.

    Returned rather than left as a log side effect for the same reason
    FootfallOutcome and AcousticOutcome are: the properties that matter
    here - that a failed health check never reaches the classifier, that a
    failed classify never reaches the router - should be provable from a
    returned value rather than inferred from log text.

    Attributes:
        available: Whether this check established anything at all about
            the acoustic environment. False means the caller must report
            ACOUSTIC unavailable to fuse(); it does NOT mean "nothing was
            heard", which is `available=True` with an ambient outcome.
        reason: Why `available` is False, None when it is True. Logged
            verbatim - it names the physical fault to go and check.
        clip: The captured audio, when capture itself succeeded. Present
            even for a clip that failed its health check, so the caller
            and the bench tooling can inspect the levels that failed.
        result: Every classified window, when classification ran.
        outcome: What handle_acoustic_event() routed, when routing ran.
            This carries the FusionResult (or the gunshot branch's direct
            alert) and is the value the rest of the system consumes. None
            with `available=True` means the check ran and the winning
            class did not clear services.config.ACOUSTIC_MIN_CONFIDENCE,
            so nothing was routed - `result` still holds every window.
    """

    available: bool
    reason: str | None
    clip: AudioClip | None = None
    result: AcousticResult | None = None
    outcome: AcousticOutcome | None = None


def _unavailable(reason: str, clip: AudioClip | None = None) -> AcousticCheckOutcome:
    """Build the "we could not tell" outcome and log why, once."""
    logger.warning("acoustic check unavailable: %s", reason)
    return AcousticCheckOutcome(available=False, reason=reason, clip=clip)


def _resolve_min_confidence(
    class_label: AcousticClass, override: float | None
) -> float:
    """The confidence floor that applies to one routed class.

    An explicit `override` wins outright, so the bench tooling can sweep a
    single floor across every class without having to reconstruct the
    per-class table. Otherwise the global floor applies unless
    ACOUSTIC_MIN_CONFIDENCE_BY_CLASS names this class.

    A key that is not a known AcousticClass value is ignored with a
    warning rather than raising, matching deterrence_scope_labels()'s
    handling of an unrecognized scope: a typo in per-node config must not
    be able to take the acoustic poll down on a field node.
    """
    if override is not None:
        return override
    by_class = services_config.ACOUSTIC_MIN_CONFIDENCE_BY_CLASS
    known = {member.value for member in AcousticClass}
    for key in by_class:
        if key not in known:
            logger.warning(
                "ACOUSTIC_MIN_CONFIDENCE_BY_CLASS names %r, which is not an "
                "AcousticClass value - ignored",
                key,
            )
    return by_class.get(class_label.value, services_config.ACOUSTIC_MIN_CONFIDENCE)


def run_acoustic_check(
    *,
    microphone: MicrophoneProtocol,
    classify: AcousticClassifyFn,
    send_lora_alert: SendLoraAlertFn,
    start_vision_event: StartVisionEventFn,
    capture_s: float,
    schema_version: int | None = None,
    safe_mode: bool = SAFE_MODE,
    min_rms: float | None = None,
    max_clipped_fraction: float | None = None,
    max_dc_offset: float | None = None,
    min_confidence: float | None = None,
) -> AcousticCheckOutcome:
    """Capture one clip, classify it, and route the result.

    Never raises for an expected failure. Every failure mode this path has
    - no capture device, a wedged arecord, a dead microphone, an
    unreachable runner, a model whose labels no longer match the wire enum
    - resolves to an AcousticCheckOutcome with available=False and a reason
    the operator can act on. That is the same "degrade loudly, never block"
    contract perception.camera.CameraError and
    perception.detector.DetectionError already get in reflex_loop: a broken
    sensor must never be able to suppress or delay the deterrence path.

    Args:
        microphone: Injected MicrophoneProtocol; main.py binds a real
            perception.microphone.Microphone.
        classify: Injected AcousticClassifyFn; main.py binds a real
            perception.acoustic_detector.HttpAcousticClassifier.
        send_lora_alert: Passed straight through to
            handle_acoustic_event() for the direct-alert branch (gunshot,
            chainsaw). Not called from this module.
        start_vision_event: Passed straight through to
            handle_acoustic_event() for the elephant_call branch, which
            runs a full vision-gated event (ADR 0033). Not called from
            this module. Required, not defaulted: the poll is the only
            thing that drives this path in the field, so an unbound
            binding here would mean every elephant call the node hears
            goes nowhere.
        capture_s: Seconds to record. Should come from
            HttpAcousticClassifier.required_capture_s() rather than a
            constant, so it tracks the deployed impulse's own window.
        schema_version: Echoed into handle_acoustic_event() for its
            mismatch check. Defaults to services.config.SCHEMA_VERSION -
            this path originates on the MPU, so there is no MCU-supplied
            version to carry and the check is trivially satisfied. It is
            still passed rather than bypassed so the two paths into the
            router stay identical in shape.
        safe_mode: Forwarded to handle_acoustic_event(), where it gates the
            gunshot branch's real LoRa send. Note this module still
            captures and still classifies under safe_mode - unlike the
            vision check, which reflex_loop suppresses entirely. Capture
            and inference actuate nothing, and a dry run that skipped them
            could not tell an operator whether the microphone works, which
            is most of what a dry run of this path is for.
        min_rms: Silence floor, normalised RMS. Defaults to
            services.config.ACOUSTIC_MIN_RMS; overridable so the bench
            tooling can sweep it against a real microphone.
        max_clipped_fraction: Distortion ceiling, as a fraction of samples
            at full scale. Defaults to
            services.config.ACOUSTIC_MAX_CLIPPED_FRACTION.
        max_dc_offset: Bias ceiling, normalised. Defaults to
            services.config.ACOUSTIC_MAX_DC_OFFSET.
        min_confidence: Floor a non-ambient class must clear before it
            is routed. Defaults to services.config's
            ACOUSTIC_MIN_CONFIDENCE, with a per-class override from
            ACOUSTIC_MIN_CONFIDENCE_BY_CLASS applied on top; passing a
            value here replaces both, so the bench tooling can sweep
            one floor across every class.

    Returns:
        An AcousticCheckOutcome. Check `available` before using
        `outcome`, and note that `available=True` with `outcome=None`
        is a real state: the check ran and nothing cleared the
        confidence floor.
    """
    if schema_version is None:
        schema_version = services_config.SCHEMA_VERSION
    if min_rms is None:
        min_rms = services_config.ACOUSTIC_MIN_RMS
    if max_clipped_fraction is None:
        max_clipped_fraction = services_config.ACOUSTIC_MAX_CLIPPED_FRACTION
    if max_dc_offset is None:
        max_dc_offset = services_config.ACOUSTIC_MAX_DC_OFFSET

    try:
        clip = microphone.capture(capture_s)
    except MicrophoneError as exc:
        return _unavailable(f"capture failed: {exc}")

    health = assess_health(
        clip,
        min_rms=min_rms,
        max_clipped_fraction=max_clipped_fraction,
        max_dc_offset=max_dc_offset,
    )
    if not health.ok:
        # Deliberately does not classify. See the module docstring: a
        # near-silent clip classifies as confident ambient, which is
        # indistinguishable from a quiet forest and would report a broken
        # microphone as working evidence of nothing happening.
        return _unavailable(f"microphone health: {health.reason}", clip=clip)

    try:
        result = classify(clip)
    except AcousticDetectionError as exc:
        return _unavailable(f"classification failed: {exc}", clip=clip)

    selected = result.selected
    if selected is None:
        return _unavailable(
            "no inference window could be classified from this clip", clip=clip
        )

    class_label = selected.to_acoustic_class()
    if class_label is None:
        # A label the deployed model emits that bridge/rpc.py's enum does
        # not define. Unroutable by construction, and silently treating it
        # as ambient would hide a divergent deploy behind a plausible
        # result. HttpAcousticClassifier.model_info() already logged the
        # full list at startup; this is the per-event consequence.
        return _unavailable(
            f"deployed model returned label {selected.label!r}, which "
            "bridge/rpc.py's AcousticClass does not define - this detection "
            "cannot be routed; reconcile the enum with the deployed impulse",
            clip=clip,
        )

    floor = _resolve_min_confidence(class_label, min_confidence)
    if class_label is not AcousticClass.AMBIENT and selected.confidence < floor:
        # Ran cleanly, heard something, not confidently enough to act on.
        # Deliberately NOT reported as ambient: the model did not say
        # ambient, and relabelling a weak gunshot as background would put
        # a false negative on record as a positive observation of quiet.
        # Deliberately NOT reported as unavailable either: the microphone
        # and the runner both worked, and available=False means go and
        # check the hardware. available=True with outcome=None is the
        # third state, and is_positive() reads it as not positive.
        logger.info(
            "acoustic check: %s at %.3f below the %.2f floor - not routed "
            "(%d window(s), device=%s)",
            class_label.value,
            selected.confidence,
            floor,
            len(result.windows),
            clip.device,
        )
        return AcousticCheckOutcome(
            available=True,
            reason=None,
            clip=clip,
            result=result,
            outcome=None,
        )
    outcome = handle_acoustic_event(
        schema_version,
        class_label,
        selected.confidence,
        MPU_CAPTURE_REF,
        send_lora_alert=send_lora_alert,
        start_vision_event=start_vision_event,
        safe_mode=safe_mode,
    )

    logger.info(
        "acoustic check: %s at %.3f from %.2fs clip (rms=%.5f, %d window(s), "
        "device=%s) -> direct_alert=%s",
        class_label.value,
        selected.confidence,
        clip.duration_s,
        clip.rms,
        len(result.windows),
        clip.device,
        outcome.direct_alert,
    )
    return AcousticCheckOutcome(
        available=True,
        reason=None,
        clip=clip,
        result=result,
        outcome=outcome,
    )


def is_positive(outcome: AcousticCheckOutcome) -> bool:
    """Whether this check heard something other than background.

    A small helper rather than a caller-side comparison because "positive"
    has to mean the same thing everywhere: available, routed, and not
    ambient. In particular an unavailable check is not positive and is also
    not negative - it is the absence of evidence, and a caller that treats
    `not is_positive(...)` as "nothing was heard" has silently converted a
    broken microphone into a clear one.

    Three states read as not positive, and they are not the same thing:
    an unavailable check (broken hardware, absence of evidence), an
    ambient result (the model's own answer that nothing is happening),
    and a sub-floor result (something was heard, too weakly to route).
    Only the first is a fault. A caller that needs to tell them apart
    reads `available`, `outcome` and `result` rather than this helper.
    """
    if not outcome.available or outcome.outcome is None:
        return False
    return outcome.outcome.class_label is not AcousticClass.AMBIENT
