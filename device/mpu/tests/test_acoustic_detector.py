"""Windowing, selection and the /api/features contract in acoustic_detector."""

from __future__ import annotations

import array
import json
import urllib.error

import pytest

from bridge.rpc import AcousticClass
from perception import acoustic_detector as ad_mod
from perception.acoustic_detector import (
    AcousticClassification,
    AcousticDetectionError,
    AcousticModelInfo,
    HttpAcousticClassifier,
    _select,
)
from perception.microphone import AudioClip

# The deployed impulse: 8 kHz in, four classes, a window of 1000 samples.
# 8 kHz is the rate the impulse declares; its PANNs front end runs at
# 32 kHz and upsamples internally, which is not this module's concern.
# The real window is several seconds; a small one keeps the test clips
# small without changing any of the arithmetic under test.
WINDOW = 1000
INFO_PAYLOAD = {
    "project": {"owner": "Edge Impulse Experts", "name": "ETX-A"},
    "modelParameters": {
        "labels": ["ambient", "chainsaw", "elephant_call", "gunshot"],
        "frequency": 8000,
        "input_features_count": WINDOW,
        "axis_count": 1,
    },
}


class _Response:
    def __init__(self, payload: dict) -> None:
        self._raw = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _install(monkeypatch, handler) -> list:
    """Route urlopen to `handler(url, body)`; return the recorded calls."""
    calls: list = []

    def fake_urlopen(request, timeout=None):
        body = request.data
        calls.append((request.full_url, json.loads(body) if body else None, timeout))
        return handler(request.full_url, body)

    monkeypatch.setattr(ad_mod.urllib.request, "urlopen", fake_urlopen)
    return calls


def _scores(**kwargs) -> dict:
    return {"result": {"classification": dict(kwargs)}}


def _clip(samples: int, sample_rate: int = 8000) -> AudioClip:
    return AudioClip(
        samples=array.array("h", [100] * samples),
        sample_rate=sample_rate,
        device="plughw:1,0",
        rms=0.05,
        peak=0.1,
        clipped_fraction=0.0,
        dc_offset=0.0,
    )


def _classifier(**kwargs) -> HttpAcousticClassifier:
    return HttpAcousticClassifier("http://127.0.0.1:1338", 15.0, **kwargs)


# --------------------------------------------------------------------------
# model_info()
# --------------------------------------------------------------------------


def test_model_info_derives_the_window_length(monkeypatch) -> None:
    """The capture duration comes from the model, never from a constant.

    POST /api/features rejects any feature count that is not exactly
    input_features_count, so a hardcoded duration starts 400ing silently
    the day the impulse window changes.
    """
    _install(monkeypatch, lambda url, body: _Response(INFO_PAYLOAD))
    info = _classifier().model_info()

    assert info.labels == ["ambient", "chainsaw", "elephant_call", "gunshot"]
    assert info.input_features_count == WINDOW
    assert info.window_s == pytest.approx(WINDOW / 8000)


def test_model_info_is_fetched_once_and_cached(monkeypatch) -> None:
    """Every classify consults it, and the model cannot change under a runner."""
    calls = _install(monkeypatch, lambda url, body: _Response(INFO_PAYLOAD))
    clf = _classifier()
    clf.model_info()
    clf.model_info()
    assert len(calls) == 1


def test_model_info_flags_labels_the_wire_enum_cannot_route(monkeypatch, caplog) -> None:
    """A divergent deploy has to be loud, and must not be fatal.

    Refusing to start would take the whole acoustic modality down over a
    label rename; staying silent would let unroutable detections be
    discarded with no trace. So: logged at error, service continues.
    """
    payload = json.loads(json.dumps(INFO_PAYLOAD))
    payload["modelParameters"]["labels"] = ["ambient", "vehicle"]
    _install(monkeypatch, lambda url, body: _Response(payload))

    with caplog.at_level("ERROR"):
        info = _classifier().model_info()

    assert info.unknown_labels == ["vehicle"]
    assert "vehicle" in caplog.text


def test_model_info_raises_when_the_runner_is_unreachable(monkeypatch) -> None:
    """The standing runner is a separate process and can simply not be there."""

    def boom(request, timeout=None):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(ad_mod.urllib.request, "urlopen", boom)
    with pytest.raises(AcousticDetectionError, match="could not reach"):
        _classifier().model_info()


# --------------------------------------------------------------------------
# Pre-flight checks - fail with the physical cause, not an arithmetic one
# --------------------------------------------------------------------------


def test_a_rate_mismatch_is_rejected_before_the_post(monkeypatch) -> None:
    """The runner would answer 400 about feature counts; that hides the cause.

    Nothing on the board resamples, so a clip captured at the wrong rate
    is a real configuration fault and the error should say so.
    """
    calls = _install(monkeypatch, lambda url, body: _Response(INFO_PAYLOAD))
    with pytest.raises(AcousticDetectionError, match="48000 Hz"):
        _classifier()(_clip(WINDOW * 4, sample_rate=48000))
    # /api/info only - no features were ever posted.
    assert all("/api/features" not in url for url, _b, _t in calls)


def test_a_clip_shorter_than_one_window_is_rejected(monkeypatch) -> None:
    """Padding to length would feed the model silence it would score as real."""
    _install(monkeypatch, lambda url, body: _Response(INFO_PAYLOAD))
    with pytest.raises(AcousticDetectionError, match="shorter than"):
        _classifier()(_clip(WINDOW - 1))


# --------------------------------------------------------------------------
# Windowing
# --------------------------------------------------------------------------


def test_windows_overlap_by_the_configured_hop(monkeypatch) -> None:
    """50% overlap so a transient on a boundary lands whole in a neighbour.

    That matters most for gunshot, the one class that alerts on its own.
    """

    def handler(url, body):
        if url.endswith("/api/info"):
            return _Response(INFO_PAYLOAD)
        return _Response(_scores(ambient=0.9))

    calls = _install(monkeypatch, handler)
    result = _classifier(window_hop_fraction=0.5)(_clip(WINDOW * 2))

    assert [w.offset_samples for w in result.windows] == [0, 500, 1000]
    posts = [c for c in calls if "/api/features" in c[0]]
    # Every POST carries exactly input_features_count values - the runner
    # rejects anything else outright.
    assert all(len(c[1]["features"]) == WINDOW for c in posts)


def test_window_count_is_capped(monkeypatch) -> None:
    """Each window is 4+ seconds of inference; an unbounded count blocks.

    Windows past the cap are dropped from the END, so the earliest audio -
    nearest whatever triggered the capture - is what gets classified.
    """

    def handler(url, body):
        if url.endswith("/api/info"):
            return _Response(INFO_PAYLOAD)
        return _Response(_scores(ambient=0.9))

    _install(monkeypatch, handler)
    result = _classifier(max_windows=2)(_clip(WINDOW * 10))

    assert len(result.windows) == 2
    assert [w.offset_samples for w in result.windows] == [0, 500]


def test_features_are_raw_int16_not_normalised(monkeypatch) -> None:
    """dsp.py scales on evidence (`if max(abs(y)) > 1.0: y /= 32768`).

    Sending normalised floats would land under that branch and be treated
    as already-scaled audio 32768x too quiet.
    """

    def handler(url, body):
        if url.endswith("/api/info"):
            return _Response(INFO_PAYLOAD)
        return _Response(_scores(ambient=0.9))

    calls = _install(monkeypatch, handler)
    _classifier(max_windows=1)(_clip(WINDOW))

    post = next(c for c in calls if "/api/features" in c[0])
    assert post[1]["features"][0] == 100
    assert all(isinstance(v, int) for v in post[1]["features"][:10])


def test_required_capture_s_tracks_the_deployed_window(monkeypatch) -> None:
    """Capture length is derived from the model, never from a constant.

    POST /api/features hard-rejects any length other than
    input_features_count, with no padding or truncation server side, so a
    hardcoded duration would start failing the day the impulse window
    changes.
    """
    _install(monkeypatch, lambda url, body: _Response(INFO_PAYLOAD))
    clf = _classifier(window_hop_fraction=0.5)
    assert clf.required_capture_s(windows=1) == pytest.approx(WINDOW / 8000)
    assert clf.required_capture_s(windows=2) == pytest.approx(1.5 * WINDOW / 8000)


# --------------------------------------------------------------------------
# Failure handling
# --------------------------------------------------------------------------


def test_one_failed_window_does_not_lose_the_others(monkeypatch) -> None:
    """A transient on one POST must not discard a real detection on another."""
    state = {"n": 0}

    def handler(url, body):
        if url.endswith("/api/info"):
            return _Response(INFO_PAYLOAD)
        state["n"] += 1
        if state["n"] == 1:
            raise urllib.error.URLError("transient")
        return _Response(_scores(elephant_call=0.8))

    _install(monkeypatch, handler)
    result = _classifier(max_windows=3)(_clip(WINDOW * 2))

    assert len(result.windows) == 2
    assert result.selected.label == "elephant_call"


def test_every_window_failing_raises(monkeypatch) -> None:
    """Nothing at all could be established, which is not the same as ambient."""

    def handler(url, body):
        if url.endswith("/api/info"):
            return _Response(INFO_PAYLOAD)
        raise urllib.error.URLError("down")

    _install(monkeypatch, handler)
    with pytest.raises(AcousticDetectionError, match="all 3 window"):
        _classifier(max_windows=3)(_clip(WINDOW * 2))


class _Fp:
    """Minimal file-like for HTTPError's body, which urllib reads lazily."""

    def __init__(self, raw: bytes) -> None:
        self._raw = raw

    def read(self) -> bytes:
        return self._raw


def test_an_http_error_body_is_carried_into_the_log(monkeypatch, caplog) -> None:
    """The runner explains count mismatches in text/plain; losing it hurts.

    The detail lands on the per-window warning rather than on the raised
    exception: when every window fails, the raise is an aggregate ("all N
    failed") because the windows can fail for different reasons and only
    the log can carry all of them. A window-size bug is diagnosed from that
    warning, so the body has to survive into it.
    """

    def handler(url, body):
        if url.endswith("/api/info"):
            return _Response(INFO_PAYLOAD)
        raise urllib.error.HTTPError(
            url, 400, "Bad Request", {}, _Fp(b"Expected 1000 features, but received 3")
        )

    _install(monkeypatch, handler)
    with caplog.at_level("WARNING"):
        with pytest.raises(AcousticDetectionError, match="all 1 window"):
            _classifier(max_windows=1)(_clip(WINDOW))

    assert "HTTP 400" in caplog.text
    assert "but received 3" in caplog.text


def test_an_empty_classification_becomes_ambient_at_zero_confidence(
    monkeypatch,
) -> None:
    """The runner strips everything below the .eim's min_score.

    An empty map therefore means "nothing cleared threshold", a real
    outcome - so the window stays in the result set rather than being
    dropped, but no class is credited with evidence it did not earn.
    """

    def handler(url, body):
        if url.endswith("/api/info"):
            return _Response(INFO_PAYLOAD)
        return _Response(_scores())

    _install(monkeypatch, handler)
    result = _classifier(max_windows=1)(_clip(WINDOW))

    assert result.selected.label == AcousticClass.AMBIENT.value
    assert result.selected.confidence == 0.0


# --------------------------------------------------------------------------
# _select() - max-pooling over time
# --------------------------------------------------------------------------


def _c(label: str, confidence: float, offset: int = 0) -> AcousticClassification:
    return AcousticClassification(
        label=label, confidence=confidence, scores={label: confidence}, offset_samples=offset
    )


def test_select_prefers_a_non_ambient_window_over_a_louder_ambient_one() -> None:
    """A gunshot is ~200ms inside a window of seconds.

    Averaging or majority-voting across windows would dilute exactly the
    evidence the system exists to catch, so selection max-pools and a
    single non-ambient window carries the clip.
    """
    windows = [_c("ambient", 0.99, 0), _c("gunshot", 0.42, 500)]
    assert _select(windows).label == "gunshot"


def test_select_takes_the_most_confident_of_several_non_ambient() -> None:
    """Max-pooling applies within the non-ambient classes too."""
    windows = [_c("chainsaw", 0.4, 0), _c("elephant_call", 0.7, 500)]
    assert _select(windows).label == "elephant_call"


def test_select_falls_back_to_the_best_ambient_window() -> None:
    """All-quiet is still a reading, and must be reported as one."""
    windows = [_c("ambient", 0.3, 0), _c("ambient", 0.8, 500)]
    selected = _select(windows)
    assert selected.label == "ambient"
    assert selected.confidence == 0.8


def test_select_returns_none_for_no_windows() -> None:
    """Nothing classified is not the same as nothing heard."""
    assert _select([]) is None


# --------------------------------------------------------------------------
# to_acoustic_class()
# --------------------------------------------------------------------------


def test_known_labels_map_onto_the_wire_enum() -> None:
    """Iterates the enum so a new member cannot be added without a mapping."""
    for member in AcousticClass:
        assert _c(member.value, 0.5).to_acoustic_class() is member


def test_an_unknown_label_maps_to_none_not_ambient() -> None:
    """Collapsing an unroutable label into ambient would hide a broken deploy.

    Ambient is a real, common, benign result; an unknown label is an
    enum/deploy divergence an operator has to fix. They must not look the
    same downstream.
    """
    assert _c("vehicle", 0.9).to_acoustic_class() is None


def test_model_info_window_s_is_zero_for_a_degenerate_frequency() -> None:
    """A malformed /api/info must not become a divide-by-zero deep in capture."""
    info = AcousticModelInfo(labels=[], frequency=0.0, input_features_count=10, axis_count=1)
    assert info.window_s == 0.0
