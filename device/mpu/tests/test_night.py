"""perception/night.py - the frame-derived day/night classifier.

Covers frame_mean_saturation()'s degrade-to-None paths without cv2, and
frames_are_night()'s threshold/median/empty behaviour with synthesised BGR
frames (skipped where cv2/numpy are not installed - same host-test caveat
as tests/test_camera.py's own cv2 avoidance).
"""
from __future__ import annotations

import pytest

from perception.night import frame_mean_saturation, frames_are_night

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

THRESH = 12.0


def _gray_frame(value: int = 40):
    """A flat mid-grey BGR frame - equal channels, so HSV saturation is 0."""
    return np.full((16, 16, 3), value, dtype=np.uint8)


def _colour_frame(bgr: tuple[int, int, int] = (20, 90, 200)):
    """A flat saturated BGR frame - unequal channels, high HSV saturation."""
    frame = np.zeros((16, 16, 3), dtype=np.uint8)
    frame[:, :] = bgr
    return frame


# --------------------------------------------------------------- frame_mean_saturation


def test_none_image_measures_as_none():
    """The camera fake hands out image=None; it must not reach cv2."""
    assert frame_mean_saturation(None) is None


def test_non_bgr_buffer_measures_as_none():
    """A single-channel buffer carries no chroma to judge night from."""
    mono = np.full((16, 16), 30, dtype=np.uint8)
    assert frame_mean_saturation(mono) is None


def test_object_without_shape_measures_as_none():
    """A stray non-array object is tolerated, not an AttributeError."""
    assert frame_mean_saturation(object()) is None


def test_grey_frame_reads_near_zero_saturation():
    """A monochrome / IR-lit frame's saturation has collapsed to ~0."""
    s = frame_mean_saturation(_gray_frame())
    assert s is not None
    assert s < 1.0


def test_colour_frame_reads_high_saturation():
    """A daylight colour frame keeps real chroma - tens of units, not zero."""
    s = frame_mean_saturation(_colour_frame())
    assert s is not None
    assert s > 30.0


# --------------------------------------------------------------- frames_are_night


def test_all_grey_burst_is_night():
    """A burst of monochrome frames reads as night."""
    assert frames_are_night([_gray_frame(), _gray_frame(), _gray_frame()], THRESH) is True


def test_all_colour_burst_is_day():
    """A burst of colour frames reads as day."""
    assert frames_are_night([_colour_frame(), _colour_frame()], THRESH) is False


def test_empty_burst_is_none():
    """No frames at all is unknown, reported as None."""
    assert frames_are_night([], THRESH) is None


def test_burst_of_only_unmeasurable_frames_is_none():
    """No frame could be judged - reported as unknown, not silently as day."""
    assert frames_are_night([None, None], THRESH) is None


def test_median_not_mean_decides_a_mixed_burst():
    """One stray colour frame in an otherwise mono burst still reads as night.

    The IR-cut filter is either in or out for the whole burst; a single odd
    frame (a headlight sweep, a compression artefact) must not flip the
    verdict, which is why the decision is a median over the burst.
    """
    burst = [_gray_frame(), _gray_frame(), _colour_frame()]
    assert frames_are_night(burst, THRESH) is True


def test_unmeasurable_frames_are_dropped_before_the_median():
    """None-measuring frames are ignored, not treated as 0 saturation."""
    burst = [None, _colour_frame(), _colour_frame(), None]
    assert frames_are_night(burst, THRESH) is False


def test_threshold_is_a_strict_lower_bound():
    """A burst sitting exactly at the threshold is day; just below it is night."""
    s = frame_mean_saturation(_colour_frame((60, 90, 140)))
    assert s is not None
    assert frames_are_night([_colour_frame((60, 90, 140))], s) is False
    assert frames_are_night([_colour_frame((60, 90, 140))], s + 0.1) is True
