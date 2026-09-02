"""Frame-derived day/night classifier, used only to gate the IR illuminator.

The IMX462 day/night camera (ADR 0001) carries a mechanical IR-cut filter
it swaps on its own: in daylight the filter sits in front of the sensor
(colour image, the near-IR the external illuminator emits is blocked before
it reaches a pixel), and once the scene is dark enough the filter swings
out (monochrome image, sensor now IR-sensitive). Firing pulse_ir() while
the filter is in is pure waste - MOSFET duty budget and battery spent on
photons the sensor cannot see - so the reflex loop only fires it when the
filter is out.

Nothing on this board reports the filter position directly. But the swap is
plainly visible in the frame: a mono / IR-lit frame has almost no colour,
so its mean HSV saturation collapses to a handful of units (JPEG chroma
noise only), while any daylight frame - even a dull, overcast one - keeps
real chroma and reads tens of units. Keying "is it night?" off that
measured collapse, rather than a wall-clock sunset table or an added
photocell, means the gate is correct in exactly the awkward cases (heavy
overcast at noon, a yard light pointed near the lens at 3 a.m., the ten
minutes either side of the filter's own switch) because it keys on the same
optical state that decides whether IR would help at all.

Measured on the real rig, Kothamangalam backyard, 1-2 Sep 2026: a genuine
night frame read mean S = 0.0; a daylight colour frame read S > 30. The
threshold (services/config.py NIGHT_SATURATION_THRESHOLD) sits in that gap
with margin on both sides.

Deliberate cv2 dependency, function-local only, exactly as
perception/camera.py and perception/detector.py already justify it - this
module stays importable on a dev laptop with no OpenCV present, and only
the one function that actually reads pixels imports it.
"""
from __future__ import annotations

import logging
from statistics import median
from typing import Any

logger = logging.getLogger(__name__)


def frame_mean_saturation(image: Any) -> float | None:
    """Mean HSV saturation (0-255 scale) of one BGR frame, or None.

    None means the frame could not be measured at all: it was None (the
    camera fake hands those out, and a real failed grab never reaches
    here), had no usable shape, or cv2 raised on it. A real monochrome
    night frame returns a small positive number, not None.
    """
    if image is None:
        return None
    try:
        import cv2  # noqa: PLC0415 (deliberately local, see module docstring)

        shape = getattr(image, "shape", None)
        if not shape or len(shape) != 3 or shape[2] != 3:
            # Not a 3-channel BGR frame - a single-channel buffer carries no
            # chroma to measure, so "night" cannot be inferred from it here.
            return None
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        return float(hsv[:, :, 1].mean())
    except Exception as exc:  # noqa: BLE001 - a bad frame must never propagate
        logger.warning("frame_mean_saturation failed on a frame: %s", exc)
        return None


def frames_are_night(images: list[Any], saturation_threshold: float) -> bool | None:
    """Decide night vs day from a short burst of BGR frames.

    Args:
        images: Frame.image ndarrays (BGR), typically the pre-decision
            vision-check burst. Frames that cannot be measured are dropped.
        saturation_threshold: Mean HSV S below which a frame is read as a
            mono / IR-cut-open (night) frame. services/config.py's
            NIGHT_SATURATION_THRESHOLD is the real value.

    Returns:
        True  - the burst's median saturation is below the threshold: the
                IR-cut filter is out, the illuminator will land on a
                sensitive sensor, pulse_ir() is worth firing.
        False - median saturation is at or above the threshold: daylight /
                filter in, the illuminator would be invisible.
        None  - not one frame in the burst could be measured. The caller
                treats this the same as False for firing purposes (an
                unmeasurable vision-check burst means the evidence burst
                has nothing to illuminate either), but logs it distinctly.
    """
    sats = [s for s in (frame_mean_saturation(img) for img in images) if s is not None]
    if not sats:
        return None
    return median(sats) < saturation_threshold
