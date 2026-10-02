"""End-to-end routing and failure containment in services.acoustic_watch."""

from __future__ import annotations

import array

from bridge.rpc import AcousticClass
from perception.acoustic_detector import (
    AcousticClassification,
    AcousticDetectionError,
    AcousticResult,
)
from perception.microphone import AudioClip, MicrophoneError
from services.acoustic_watch import (
    MPU_CAPTURE_REF,
    is_positive,
    run_acoustic_check,
)

FLOORS = {"min_rms": 0.001, "max_clipped_fraction": 0.01, "max_dc_offset": 0.05}


def _clip(*, rms: float = 0.05, dc_offset: float = 0.0, clipped: float = 0.0) -> AudioClip:
    return AudioClip(
        samples=array.array("h", [100] * 1000),
        sample_rate=8000,
        device="plughw:1,0",
        rms=rms,
        peak=0.2,
        clipped_fraction=clipped,
        dc_offset=dc_offset,
    )


class _Mic:
    def __init__(self, clip: AudioClip | None = None, error: Exception | None = None) -> None:
        self._clip = clip if clip is not None else _clip()
        self._error = error
        self.calls: list[float] = []

    def capture(self, duration_s: float) -> AudioClip:
        self.calls.append(duration_s)
        if self._error is not None:
            raise self._error
        return self._clip


def _result(label: str, confidence: float) -> AcousticResult:
    window = AcousticClassification(
        label=label, confidence=confidence, scores={label: confidence}, offset_samples=0
    )
    return AcousticResult(windows=[window], selected=window)


def _classifier(label: str = "ambient", confidence: float = 0.9, error=None):
    calls: list[AudioClip] = []

    def classify(clip: AudioClip) -> AcousticResult:
        calls.append(clip)
        if error is not None:
            raise error
        return _result(label, confidence)

    classify.calls = calls  # type: ignore[attr-defined]
    return classify


def _lora():
    calls: list[tuple] = []

    def send(
        schema_version: int, acoustic_class: str, confidence: float, capture_ref: int
    ) -> bool:
        calls.append((schema_version, acoustic_class, confidence, capture_ref))
        return True

    send.calls = calls  # type: ignore[attr-defined]
    return send


def _vision_event(outcome=None):
    """Stand-in for main.py's _start_vision_event binding.

    Returns None by default, which is what the real binding returns when
    another event already owned the camera - the poll must treat that as
    an ordinary outcome rather than an error.
    """
    calls: list[float] = []

    def start(confidence: float):
        calls.append(confidence)
        return outcome

    start.calls = calls  # type: ignore[attr-defined]
    return start


def _run(**overrides):
    kwargs = {
        "microphone": _Mic(),
        "classify": _classifier(),
        "send_lora_alert": _lora(),
        "start_vision_event": _vision_event(),
        "capture_s": 3.0,
        "safe_mode": True,
        **FLOORS,
    }
    kwargs.update(overrides)
    return run_acoustic_check(**kwargs), kwargs


# --------------------------------------------------------------------------
# The contract that matters most: a broken mic is never classified
# --------------------------------------------------------------------------


def test_a_silent_clip_is_never_handed_to_the_classifier() -> None:
    """The BY-M1's dead-cell failure mode must not become evidence.

    A near-silent clip classifies as confident `ambient`, which is
    indistinguishable from a quiet forest. Fusion can drop a modality that
    reports itself absent; it has no defence against one that reports
    "nothing here" when the truth is "I cannot tell". So the health gate
    has to sit BEFORE inference, not after it.
    """
    classify = _classifier()
    outcome, _ = _run(microphone=_Mic(_clip(rms=0.0)), classify=classify)

    assert not outcome.available
    assert "silent" in outcome.reason
    assert classify.calls == []
    assert outcome.outcome is None
    # The clip is still returned so the levels that failed can be inspected.
    assert outcome.clip is not None


def test_a_clipped_capture_is_not_classified() -> None:
    """Distortion is a capture fault, so it gates in the same place.

    A clipped waveform's harmonic content is an artifact of the ADC rather
    than of the source, which is exactly what the log-mel front end would
    go on to measure.
    """
    classify = _classifier()
    outcome, _ = _run(microphone=_Mic(_clip(clipped=0.5)), classify=classify)
    assert not outcome.available
    assert classify.calls == []


def test_a_capture_failure_reports_unavailable_rather_than_raising() -> None:
    """A broken sensor must never be able to block the deterrence path."""
    outcome, _ = _run(microphone=_Mic(error=MicrophoneError("arecord exited 1")))
    assert not outcome.available
    assert "capture failed" in outcome.reason
    assert outcome.clip is None


def test_an_inference_failure_reports_unavailable_rather_than_raising() -> None:
    """A runner that is down or wedged degrades the modality, not the loop."""
    outcome, _ = _run(classify=_classifier(error=AcousticDetectionError("runner down")))
    assert not outcome.available
    assert "classification failed" in outcome.reason


def test_an_unroutable_label_is_unavailable_not_ambient() -> None:
    """A divergent deploy must not be laundered into a benign result.

    `ambient` means the system listened and heard background. An unknown
    label means the deployed impulse and bridge/rpc.py's enum disagree,
    which an operator has to fix. Collapsing the second into the first
    would hide a broken deploy behind a plausible reading.
    """
    outcome, _ = _run(classify=_classifier("vehicle", 0.95))
    assert not outcome.available
    assert "vehicle" in outcome.reason
    assert outcome.outcome is None


# --------------------------------------------------------------------------
# Routing - delegated wholly to handle_acoustic_event (ADR 0007 5)
# --------------------------------------------------------------------------


def test_elephant_call_starts_a_vision_gated_event() -> None:
    """ADR 0033: direct evidence of an elephant, so it opens the camera.

    Asserted through run_acoustic_check rather than only against
    handle_acoustic_event, because the poll is the only thing that drives
    this path in the field (ADR 0028) - a start_vision_event that never
    reached the handler would mean every elephant call the node hears goes
    nowhere, and the handler's own tests could not see that.
    """
    vision = _vision_event()
    outcome, _ = _run(classify=_classifier("elephant_call", 0.8), start_vision_event=vision)

    assert outcome.available
    assert outcome.outcome.class_label is AcousticClass.ELEPHANT_CALL
    assert outcome.outcome.direct_alert is False
    assert vision.calls == [0.8]


def test_chainsaw_alerts_officers_directly() -> None:
    """ADR 0033: a chainsaw means people, so it skips fusion entirely.

    Asserted through run_acoustic_check rather than only against
    handle_acoustic_event, because this is the path the microphone actually
    takes (ADR 0028) and the one that would quietly keep fusing if the
    MPU-side watch grew its own routing.
    """
    outcome, kwargs = _run(classify=_classifier("chainsaw", 0.7), safe_mode=False)

    assert outcome.outcome.class_label is AcousticClass.CHAINSAW
    assert outcome.outcome.direct_alert is True
    assert outcome.outcome.footfall is None
    assert [call[1] for call in kwargs["send_lora_alert"].calls] == ["chainsaw"]


def test_ambient_routes_nowhere() -> None:
    """Background is a real reading, and acting on it is the wrong response.

    The poll still reports `available` - the microphone worked, which is
    what that field is about - while the routing produces nothing at all.
    """
    vision = _vision_event()
    outcome, kwargs = _run(classify=_classifier("ambient", 0.99), start_vision_event=vision)

    assert outcome.available
    assert outcome.outcome.class_label is AcousticClass.AMBIENT
    assert outcome.outcome.direct_alert is False
    assert outcome.outcome.footfall is None
    assert vision.calls == []
    assert kwargs["send_lora_alert"].calls == []


def test_gunshot_takes_the_direct_alert_path_and_never_fuses() -> None:
    """ADR 0007 5: a gunshot is an anti-poaching alert, not elephant evidence."""
    outcome, _ = _run(classify=_classifier("gunshot", 0.6), safe_mode=False)

    assert outcome.outcome.direct_alert is True
    assert outcome.outcome.footfall is None


def test_safe_mode_suppresses_the_gunshot_uplink_but_still_captures() -> None:
    """Unlike the vision check, a dry run still exercises the sensor.

    Capture and inference actuate nothing, and a dry run that skipped them
    could not tell an operator whether the microphone works - which is most
    of what a dry run of this path is for.
    """
    mic = _Mic()
    classify = _classifier("gunshot", 0.6)
    lora = _lora()
    outcome = run_acoustic_check(
        microphone=mic,
        classify=classify,
        send_lora_alert=lora,
        start_vision_event=_vision_event(),
        capture_s=3.0,
        safe_mode=True,
        **FLOORS,
    )

    assert lora.calls == []
    assert outcome.outcome.direct_alert is True
    assert mic.calls == [3.0]
    assert len(classify.calls) == 1


def test_the_gunshot_uplink_carries_the_mpu_capture_sentinel() -> None:
    """capture_ref's documented meaning (an MCU ring index) does not apply.

    The microphone moved to the MPU (ADR 0028), so there is no MCU ring
    buffer on this path. -1 is carried rather than a plausible-looking 0,
    so a log line showing capture_ref=-1 states something true instead of
    pointing at a ring slot that was never written.
    """
    lora = _lora()
    run_acoustic_check(
        microphone=_Mic(),
        classify=_classifier("gunshot", 0.6),
        send_lora_alert=lora,
        start_vision_event=_vision_event(),
        capture_s=3.0,
        safe_mode=False,
        **FLOORS,
    )
    assert lora.calls[0][3] == MPU_CAPTURE_REF == -1


def test_the_requested_capture_duration_is_passed_through() -> None:
    """Callers derive this from the deployed impulse, so it must not be clamped.

    required_capture_s() sizes the clip against the model's own window
    because POST /api/features rejects any other feature count; silently
    substituting a constant here would 400 on the next retrain.
    """
    mic = _Mic()
    _run(microphone=mic, capture_s=4.5)
    assert mic.calls == [4.5]


# --------------------------------------------------------------------------
# is_positive()
# --------------------------------------------------------------------------


def test_is_positive_is_true_only_for_a_routed_non_ambient_result() -> None:
    """Heard-something and heard-background are different answers."""
    assert is_positive(_run(classify=_classifier("elephant_call", 0.8))[0])
    assert not is_positive(_run(classify=_classifier("ambient", 0.9))[0])


def test_an_unavailable_check_is_not_positive() -> None:
    """And callers must not read that as "nothing was heard".

    Absence of evidence is not evidence of absence; the helper exists so
    that distinction is made in one place rather than at each call site.
    """
    outcome, _ = _run(microphone=_Mic(_clip(rms=0.0)))
    assert not is_positive(outcome)
    assert not outcome.available
