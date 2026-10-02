"""Per-class score floor in perception.detector.HttpVisionDetector."""

from __future__ import annotations

import json
import sys
import types

import pytest

from perception import detector as detector_mod
from perception.detector import HttpVisionDetector


class _Response:
    def __init__(self, payload: dict) -> None:
        self._raw = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _box(label: str, value: float) -> dict:
    return {"label": label, "value": value, "x": 1, "y": 2, "width": 3, "height": 4}


@pytest.fixture
def runner(monkeypatch: pytest.MonkeyPatch):
    """Fake cv2 + runner reply; returns a setter for the boxes to report."""

    class _Encoded:
        def tobytes(self) -> bytes:
            return b"jpg"

    fake_cv2 = types.SimpleNamespace(imencode=lambda ext, img: (True, _Encoded()))
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)
    boxes: list[dict] = []
    monkeypatch.setattr(
        detector_mod.urllib.request,
        "urlopen",
        lambda request, timeout: _Response({"result": {"bounding_boxes": boxes}}),
    )
    return boxes


def test_no_floor_keeps_every_box(runner: list) -> None:
    """No mapping: every box the runner reports survives, as before."""
    runner[:] = [_box("Boar", 0.06), _box("Fox", 0.07)]
    out = HttpVisionDetector("http://x", 1.0)([object()])
    assert [d.label for d in out[0]] == ["Boar", "Fox"]


def test_floor_drops_only_listed_labels_below_their_floor(runner: list) -> None:
    """Floors are inclusive and apply only to the labels they name."""
    runner[:] = [
        _box("Boar", 0.17),  # below 0.18 -> dropped
        _box("Boar", 0.18),  # at the floor -> kept
        _box("Fox", 0.11),  # below 0.12 -> dropped
        _box("Fox", 0.5),
        _box("Elephant", 0.06),  # not listed -> unchanged
    ]
    det = HttpVisionDetector("http://x", 1.0, {"Boar": 0.18, "Fox": 0.12})
    out = det([object()])
    assert [(d.label, d.confidence) for d in out[0]] == [
        ("Boar", 0.18),
        ("Fox", 0.5),
        ("Elephant", 0.06),
    ]


def test_all_filtered_is_an_empty_frame_not_an_error(runner: list) -> None:
    """A fully-filtered frame is an empty list, never a DetectionError."""
    runner[:] = [_box("Boar", 0.1)]
    out = HttpVisionDetector("http://x", 1.0, {"Boar": 0.18})([object(), object()])
    assert out == [[], []]
