"""Turns the boxes and the waveform into range, gait and behaviour (ADR 0035).

The recorder next door stores what the sensors produced. This module is the
other half of D9: what can be *read off* that, so a future seismic model has
something to be trained against beyond a species name. Three questions, and
they are not equally answerable.

HOW FAR, AND THE HONEST VERSION OF THAT. A box's height in pixels and the
lens's focal length give `d = H x f / h`, which is a real distance only if H -
the animal's actual shoulder height - is known. It is not: the detector
reports "Elephant" for a calf and for a bull, and those differ by more than a
factor of two. So absolute range here is good for binning near/mid/far and for
anchoring a learned amplitude-range relation, and for nothing else. Nothing
user-facing may quote it in metres.

The *ratio* of two ranges is a different measurement entirely. `d2/d1 = h1/h2`,
and the unknown H cancels exactly - as does the focal length, which is why
the relative trajectory is correct even before the camera is calibrated. That
is why the direction of travel, the closing rate and the retreat verdict are
all built on the ratio and never on the absolute number. It is also why the
boxes are stored: anything here can be re-derived from them later, with a
calibrated focal length or a better body-plan table, without recapturing a
single encounter.

WHAT IT WAS DOING. A footfall is an impulse in the waveform, and the cadence
across several of them - the inter-impact interval and how regular it is - is
the strongest elephant/boar/fox discriminator seismic alone offers. One 2 s
window cannot see it; a stitched 45 s watch can. The detector here is
deliberately a plain robust-threshold peak picker rather than anything
learned, because the thing it feeds is the training set: a clever detector
would bake its own assumptions into the corpus that is supposed to test them.

Cadence x stride length and the rate of change of absolute range are two
independent estimates of the same speed, so they are compared, and a
disagreement is recorded rather than resolved. The records where two
measurements of one animal disagree are the ones worth a human's time.

NOTHING HERE DECIDES ANYTHING IN THE FIELD except one function:
retreat_verdict(), which item 10 uses to decide whether a top-tier fire
worked. That is deliberate - the alternative was a second implementation of
"is it still there", and two of those would drift. Everything else is
annotation, computed after the deterrents have fired, and every entry point
returns a None or an "unknown" instead of raising.
"""

from __future__ import annotations

import json
import logging
import math
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from perception.seismic_stream import SeismicSlice
from services import config

logger = logging.getLogger(__name__)

# Trajectory directions. "unknown" is a first-class answer here and is
# returned far more often than the other three - most watches confirm
# nothing, and a watch with two usable boxes has no trajectory.
APPROACHING = "approaching"
RECEDING = "receding"
STATIONARY = "stationary"
UNKNOWN = "unknown"

# Motion states.
WALKING = "walking"
RUNNING = "running"

# Why a box was not ranged. Counted rather than discarded silently: a watch
# where every box was truncated is a watch where the animal filled the
# frame, which is itself a reading.
EXCLUDED_TRUNCATED = "truncated"
EXCLUDED_FRAME_FILLING = "frame_filling"
EXCLUDED_TOO_SMALL = "too_small"
EXCLUDED_UNKNOWN_SPECIES = "unknown_species"


# ---------------------------------------------------------------------------
# Optics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Optics:
    """The focal length every absolute range is divided by, and its provenance.

    Attributes:
        focal_length_px: Pixels per radian at the image centre, for the
            frame width the detector reports boxes in.
        calibrated: False when this came from the lens's nominal field of
            view rather than from a measurement. Copied onto every record,
            so a corpus mixing the two can be separated afterwards.
        source: Where it came from - "nominal_fov" or the calibration
            file's path.
        rms_reprojection_px: The calibration's own fit error, if any. A
            calibration with a bad fit is worse than no calibration, and
            this is the number that says so.
    """

    focal_length_px: float
    calibrated: bool
    source: str
    rms_reprojection_px: float | None = None


def focal_length_px(fov_deg: float, width_px: int) -> float:
    """Pinhole focal length in pixels from a horizontal field of view.

    The standard half-angle relation, `f = (w/2) / tan(fov/2)`: at the
    repo's 95 degrees over 1920 px this is about 880 px. It is a
    specification and the caller is expected to treat it as one.

    Args:
        fov_deg: Horizontal field of view in degrees, 0 < fov < 180.
        width_px: Image width the boxes are measured in.

    Returns:
        Focal length in pixels, or 0.0 if the inputs cannot describe a lens.
    """
    if width_px <= 0 or not 0.0 < fov_deg < 180.0:
        return 0.0
    return (width_px / 2.0) / math.tan(math.radians(fov_deg) / 2.0)


NOMINAL_OPTICS = Optics(
    focal_length_px=focal_length_px(
        config.CAMERA_HORIZONTAL_FOV_DEG, config.CAMERA_FRAME_WIDTH
    ),
    calibrated=False,
    source="nominal_fov",
)


def load_optics(path: Path | None = None) -> Optics:
    """Read the calibration file if there is one; never raises.

    A missing file is the normal state, not a degraded one - the node ships
    uncalibrated and the records say so. A *present but unusable* file is
    different and is logged at warning, because somebody went to the
    trouble of running the calibration and the result is not being used.

    Args:
        path: The calibration JSON, defaulting to
            config.CAMERA_CALIBRATION_PATH. Written by
            scripts/calibrate_camera.py.

    Returns:
        The calibrated optics, or NOMINAL_OPTICS when there is nothing
        usable to read.
    """
    target = Path(config.CAMERA_CALIBRATION_PATH if path is None else path)
    try:
        if not target.is_file():
            return NOMINAL_OPTICS
        data = json.loads(target.read_text(encoding="utf-8"))
        fx = float(data["fx"])
        width = int(data.get("image_width", config.CAMERA_FRAME_WIDTH))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        logger.warning("camera calibration at %s is unusable (%s) - using the nominal "
                       "focal length and marking records uncalibrated", target, exc)
        return NOMINAL_OPTICS
    if fx <= 0:
        logger.warning("camera calibration at %s has a non-positive fx - ignoring", target)
        return NOMINAL_OPTICS
    # Rescale if the calibration was shot at a different resolution than the
    # detector reports boxes in. Focal length in pixels is proportional to
    # the pixel count across the same angle, so this is exact, and getting
    # it wrong silently would scale every range in the corpus.
    if width > 0 and width != config.CAMERA_FRAME_WIDTH:
        fx = fx * (config.CAMERA_FRAME_WIDTH / width)
    rms = data.get("rms_reprojection_px")
    return Optics(
        focal_length_px=fx,
        calibrated=True,
        source=str(target),
        rms_reprojection_px=None if rms is None else float(rms),
    )


# ---------------------------------------------------------------------------
# Ranging
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RangeSample:
    """One box turned into a distance, and the measurement it came from.

    `height_px` is kept beside `range_m` on purpose. It is the measurement;
    the distance is an interpretation of it through two numbers that may
    both be revised (the focal length, and the species' assumed height).
    """

    poll: int
    timestamp_s: float
    sample_index: int | None
    confidence: float
    height_px: float
    range_m: float
    relative_range: float


@dataclass(frozen=True)
class RangeTrack:
    """How one species' distance moved across one watch.

    Attributes:
        label: The species these boxes were labelled with.
        samples: Every rangeable box, in time order.
        excluded: Counts by reason for the boxes that were not rangeable.
        direction: APPROACHING, RECEDING, STATIONARY or UNKNOWN.
        fractional_rate_per_s: d(log range)/dt, fitted by least squares
            over the whole track. Negative is closing. The quantity the
            unknown animal height cancels out of, and so the only one here
            that is measured rather than estimated.
        relative_range: The last sample's distance over the first, from the
            box heights alone. Exact in the same sense - a 0.5 means it
            halved its distance, whatever its real size.
        speed_mps: |d(range)/dt| in metres per second, from the absolute
            ranges. Carries their full +-30-50% error band.
        median_range_m: Middle absolute range over the track.
        range_band: "near", "mid" or "far" from that median.
        span_s: Time between the first and last rangeable box.
    """

    label: str
    samples: tuple[RangeSample, ...]
    excluded: dict[str, int]
    direction: str
    fractional_rate_per_s: float | None
    relative_range: float | None
    speed_mps: float | None
    median_range_m: float | None
    range_band: str | None
    span_s: float


def box_exclusion(
    box,
    *,
    width_px: int = config.CAMERA_FRAME_WIDTH,
    height_px: int = config.CAMERA_FRAME_HEIGHT,
) -> str | None:
    """Why this box cannot be ranged, or None if it can.

    Three independent reasons, and all three matter in the field:

    - **Truncated.** A box touching any frame edge is of an animal partly
      outside the image, so its height is a lower bound and the range
      derived from it reads as too far. The failure is directional, which
      makes it worse than noise: an animal walking in from the edge would
      appear to approach faster than it does.
    - **Frame-filling.** The deployed detector has a documented degenerate
      mode where it stops localising and returns a box at the frame extent
      (services/config.py's HOME_TEST_MAX_BOX_AREA_FRACTION, 1,745 of them
      in four days). Such a box carries no localisation to range from.
    - **Too small.** Below RANGE_MIN_BOX_HEIGHT_PX a pixel of edge noise is
      percents of the height and therefore percents of the range, and the
      trajectory starts following the detector rather than the animal.

    Args:
        box: Anything with `.x`, `.y`, `.width` and `.height` in the
            detector's original-image pixel space.
        width_px: Frame width those coordinates are in.
        height_px: Frame height.

    Returns:
        One of the EXCLUDED_* constants, or None when the box is usable.
    """
    margin = config.RANGE_EDGE_MARGIN_PX
    if (
        box.x <= margin
        or box.y <= margin
        or box.x + box.width >= width_px - margin
        or box.y + box.height >= height_px - margin
    ):
        return EXCLUDED_TRUNCATED
    frame_area = float(width_px * height_px)
    box_area = float(box.width * box.height)
    if frame_area > 0 and box_area / frame_area >= config.RANGE_MAX_BOX_AREA_FRACTION:
        return EXCLUDED_FRAME_FILLING
    if box.height < config.RANGE_MIN_BOX_HEIGHT_PX:
        return EXCLUDED_TOO_SMALL
    return None


def range_m(height_px: float, label: str, optics: Optics = NOMINAL_OPTICS) -> float | None:
    """Approximate distance to an animal of `label` whose box is `height_px` tall.

    `d = H x f / h`. Approximate to +-30-50% because H is a nominal adult
    figure for the species and the animal in front of the lens is not
    guaranteed to be one. Useful for binning and for anchoring an
    amplitude-range relation; never for telling a ranger a number.

    Args:
        height_px: Bounding-box height in original-image pixels.
        label: Species label, looked up in config.SPECIES_REGISTRY.
        optics: Focal length to use.

    Returns:
        Metres, or None when the species is not in the registry, has no
        body plan, or the inputs cannot produce a distance.
    """
    species = config.SPECIES_REGISTRY.get(label)
    if species is None or species.shoulder_height_m <= 0:
        return None
    if height_px <= 0 or optics.focal_length_px <= 0:
        return None
    return species.shoulder_height_m * optics.focal_length_px / height_px


def _log_slope(times: Sequence[float], values: Sequence[float]) -> float | None:
    """Least-squares d(log value)/dt, or None if it is not determined.

    Log space rather than linear for two reasons that both matter here.
    The fitted slope is then a *fractional* rate, which is the quantity
    that does not depend on the animal's unknown size - the same fit over
    box heights and over derived ranges gives the same magnitude. And an
    approach is geometrically multiplicative rather than additive, so the
    residuals are better behaved over a 45 s watch that may cover a factor
    of three in distance.
    """
    n = len(times)
    if n < 2 or len(values) != n:
        return None
    logs = []
    for value in values:
        if value <= 0:
            return None
        logs.append(math.log(value))
    mean_t = sum(times) / n
    mean_y = sum(logs) / n
    numerator = sum((t - mean_t) * (y - mean_y) for t, y in zip(times, logs, strict=True))
    denominator = sum((t - mean_t) ** 2 for t in times)
    if denominator <= 0:
        return None
    return numerator / denominator


def _range_band(distance_m: float) -> str:
    """Which of near/mid/far a distance falls in."""
    near, mid = config.RANGE_BAND_EDGES_M
    if distance_m < near:
        return "near"
    if distance_m < mid:
        return "mid"
    return "far"


def range_track(
    frames: Iterable,
    label: str,
    optics: Optics = NOMINAL_OPTICS,
    *,
    since_monotonic_s: float | None = None,
) -> RangeTrack:
    """Build one species' distance trajectory from a watch's track frames.

    Args:
        frames: TrackFrame-shaped objects - `.poll`, `.timestamp_s`,
            `.sample_index` and `.boxes`, each box carrying `.label`,
            `.confidence`, `.x`, `.y`, `.width`, `.height`. Duck-typed
            rather than imported, because perception.seismic_dataset owns
            those types and imports this module.
        label: Which species' boxes to use. Boxes of other labels are
            ignored entirely rather than counted as exclusions.
        optics: Focal length for the absolute ranges.
        since_monotonic_s: Ignore frames stamped before this. What makes
            the retreat verdict a view of the same trajectory rather than
            a second implementation of it.

    Returns:
        A RangeTrack. Always returns one - a watch with no usable boxes
        comes back with no samples and direction UNKNOWN, which is a
        reading and not a failure.
    """
    samples: list[RangeSample] = []
    excluded: dict[str, int] = {}
    for frame in frames:
        if since_monotonic_s is not None and frame.timestamp_s < since_monotonic_s:
            continue
        # One box per frame per species: the tallest, which among boxes of
        # one label in one frame is the nearest animal. Averaging them
        # would track the centroid of a group, and a group's centroid can
        # recede while the nearest animal closes.
        best = None
        reason = None
        for box in frame.boxes:
            if box.label != label:
                continue
            why = box_exclusion(box)
            if why is not None:
                reason = why if reason is None else reason
                continue
            if best is None or box.height > best.height:
                best = box
        if best is None:
            if reason is not None:
                excluded[reason] = excluded.get(reason, 0) + 1
            continue
        distance = range_m(best.height, label, optics)
        if distance is None:
            excluded[EXCLUDED_UNKNOWN_SPECIES] = excluded.get(EXCLUDED_UNKNOWN_SPECIES, 0) + 1
            continue
        samples.append(
            RangeSample(
                poll=frame.poll,
                timestamp_s=frame.timestamp_s,
                sample_index=frame.sample_index,
                confidence=best.confidence,
                height_px=float(best.height),
                range_m=distance,
                relative_range=1.0,
            )
        )

    samples.sort(key=lambda s: s.timestamp_s)
    if samples:
        # Relative to the first sample, computed from the box heights so it
        # stays exact: every factor the absolute range carries - focal
        # length, assumed shoulder height - divides out of the ratio.
        first_height = samples[0].height_px
        samples = [
            RangeSample(
                poll=s.poll,
                timestamp_s=s.timestamp_s,
                sample_index=s.sample_index,
                confidence=s.confidence,
                height_px=s.height_px,
                range_m=s.range_m,
                relative_range=first_height / s.height_px,
            )
            for s in samples
        ]

    span_s = samples[-1].timestamp_s - samples[0].timestamp_s if len(samples) > 1 else 0.0
    direction = UNKNOWN
    rate = None
    speed = None
    relative = samples[-1].relative_range if samples else None
    median_range = statistics.median(s.range_m for s in samples) if samples else None

    if (
        len(samples) >= config.RANGE_MIN_TRAJECTORY_FRAMES
        and span_s >= config.RANGE_MIN_TRAJECTORY_SPAN_S
    ):
        rate = _log_slope([s.timestamp_s for s in samples], [s.range_m for s in samples])
        if rate is not None:
            if abs(rate) < config.BEHAVIOUR_STATIONARY_RATE_PER_S:
                direction = STATIONARY
            else:
                direction = APPROACHING if rate < 0 else RECEDING
            if median_range is not None:
                # Fractional rate x distance is the rate in metres per
                # second, and inherits that distance's error band whole.
                speed = abs(rate) * median_range

    return RangeTrack(
        label=label,
        samples=tuple(samples),
        excluded=excluded,
        direction=direction,
        fractional_rate_per_s=rate,
        relative_range=relative,
        speed_mps=speed,
        median_range_m=median_range,
        range_band=None if median_range is None else _range_band(median_range),
        span_s=span_s,
    )


def range_tracks(
    frames: Sequence,
    labels: Sequence[str],
    optics: Optics = NOMINAL_OPTICS,
) -> tuple[RangeTrack, ...]:
    """One RangeTrack per label, dropping the ones with no usable boxes at all."""
    out = []
    for label in labels:
        track = range_track(frames, label, optics)
        if track.samples or track.excluded:
            out.append(track)
    return tuple(out)


# ---------------------------------------------------------------------------
# Gait
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Impact:
    """One footfall: where it was in the record and how hard it hit."""

    sample_index: int
    offset: int
    time_s: float
    peak_counts: int
    duration_s: float


@dataclass(frozen=True)
class GaitSummary:
    """The impact train, and what the intervals between impacts look like.

    Attributes:
        impacts: Every impact found, in time order.
        interval_mean_s: Mean inter-impact interval over the intervals that
            fall inside [GAIT_MIN_INTERVAL_S, GAIT_MAX_INTERVAL_S].
        interval_stdev_s: Its sample standard deviation.
        interval_cv: stdev/mean - the regularity, and the part that is
            species-discriminating rather than just distance-dependent. A
            walking animal is metronomic; wind and rain are not.
        cadence_hz: 1/interval_mean_s. Steps per second, not strides.
        peak_mean_counts, peak_max_counts: Impact amplitude in raw ADC
            counts. Amplitude is a function of mass *and* distance, so it
            is stored and never interpreted here.
        analysed_from, analysed_count: The segment the detector actually
            ran over, as an offset and length into the slice. Less than
            the whole record whenever an actuator fired, and saying which
            part was used is the difference between a usable corpus row
            and one a reader has to guess about.
        excluded_actuator_samples: How many samples were kept out because
            an actuator was driving over them.
        noise_floor_counts, threshold_counts: What the detector decided
            quiet was, and the bar it used. Stored so a later reader can
            tell "no impacts" from "threshold set too high".
    """

    impacts: tuple[Impact, ...]
    interval_mean_s: float | None
    interval_stdev_s: float | None
    interval_cv: float | None
    cadence_hz: float | None
    peak_mean_counts: float | None
    peak_max_counts: int | None
    analysed_from: int
    analysed_count: int
    excluded_actuator_samples: int
    noise_floor_counts: float
    threshold_counts: float

    @property
    def impact_count(self) -> int:
        """How many footfalls were found."""
        return len(self.impacts)


def _clean_segment(slice_: SeismicSlice, actuators: Sequence) -> tuple[int, int, int]:
    """The run of samples to analyse: everything before the first actuator fired.

    Not "everything an actuator did not overlap". The horn is the loudest
    thing this structure will ever experience and it rings afterwards, so
    the samples after a fire are suspect even where no actuator was
    nominally on. The approach - which is the part with a gait in it - is
    before the fire by construction, because the deterrent is a response to
    having seen the animal.

    Returns:
        `(offset, count, excluded)` - where to start inside the slice, how
        many samples, and how many were given up to actuators.
    """
    total = len(slice_)
    starts = [
        a.start_index for a in actuators if getattr(a, "start_index", None) is not None
    ]
    if not starts:
        return 0, total, 0
    first = min(starts)
    cut = first - slice_.first_sample_index
    if cut <= 0:
        # The record starts after the fire began. Nothing clean to use.
        return 0, 0, total
    cut = min(cut, total)
    return 0, cut, total - cut


def _moving_mean_abs(values: Sequence[float], window: int) -> list[float]:
    """Envelope of |x| over a sliding window, by running sum - O(n), no numpy."""
    if window <= 1:
        return [abs(v) for v in values]
    out: list[float] = []
    running = 0.0
    for i, value in enumerate(values):
        running += abs(value)
        if i >= window:
            running -= abs(values[i - window])
        out.append(running / min(i + 1, window))
    return out


def gait_summary(
    slice_: SeismicSlice | None, actuators: Sequence = ()
) -> GaitSummary | None:
    """Find the footfalls in a record's waveform; never raises.

    The detector is a robust-threshold peak picker and is meant to stay
    one. Median and MAD give the noise floor, because the impacts are in
    the signal being measured and a mean-based floor rises with the thing
    it is trying to detect. Samples inside a recorded gap are left out of
    both the floor and the search: a gap is zero-filled, and zeros deflate
    the floor into finding a herd in the quantisation noise.

    Args:
        slice_: The record's ground motion, or None.
        actuators: ActuatorSpan-shaped objects, used to cut the analysis to
            the pre-deterrence segment.

    Returns:
        A GaitSummary, or None when there is no waveform to analyse. A
        summary with no impacts is a real result - the negative class is
        most of this corpus.
    """
    if slice_ is None or len(slice_) == 0:
        return None
    try:
        return _gait_summary(slice_, actuators)
    except Exception as exc:  # noqa: BLE001 - annotation must not cost the record
        logger.warning("seismic dataset: gait summary failed, storing none: %s", exc)
        return None


def _gait_summary(slice_: SeismicSlice, actuators: Sequence) -> GaitSummary:
    rate = float(config.SEISMIC_SAMPLE_RATE_HZ)
    offset, count, excluded = _clean_segment(slice_, actuators)
    counts = list(slice_.counts[offset : offset + count])

    # Samples the stream recorded as missing are zero-filled, so they look
    # like perfect quiet rather than like absence.
    gap_offsets: set[int] = set()
    for gap in slice_.gaps:
        start = gap.start_index - slice_.first_sample_index - offset
        for i in range(max(start, 0), min(start + gap.count, len(counts))):
            gap_offsets.add(i)

    usable = [v for i, v in enumerate(counts) if i not in gap_offsets]
    empty = GaitSummary(
        impacts=(),
        interval_mean_s=None,
        interval_stdev_s=None,
        interval_cv=None,
        cadence_hz=None,
        peak_mean_counts=None,
        peak_max_counts=None,
        analysed_from=offset,
        analysed_count=count,
        excluded_actuator_samples=excluded,
        noise_floor_counts=0.0,
        threshold_counts=0.0,
    )
    if len(usable) < 2:
        return empty

    # Remove DC with the median rather than the mean, for the same reason
    # the floor is a median: the impacts must not move the baseline.
    baseline = statistics.median(usable)
    centred = [v - baseline for v in counts]

    window = max(1, int(round(config.GAIT_ENVELOPE_WINDOW_S * rate)))
    envelope = _moving_mean_abs(centred, window)
    quiet = [e for i, e in enumerate(envelope) if i not in gap_offsets]
    floor = statistics.median(quiet)
    # 1.4826 x MAD is the normal-consistent robust standard deviation.
    mad = statistics.median([abs(e - floor) for e in quiet])
    threshold = max(
        floor + config.GAIT_IMPACT_SIGMA * 1.4826 * mad,
        floor + config.GAIT_MIN_IMPACT_COUNTS,
    )

    refractory = max(1, int(round(config.GAIT_REFRACTORY_S * rate)))
    impacts: list[Impact] = []
    i = 0
    n = len(envelope)
    while i < n:
        if i in gap_offsets or envelope[i] < threshold:
            i += 1
            continue
        run_start = i
        quiet_run = 0
        j = i
        last_above = i
        while j < n:
            if j not in gap_offsets and envelope[j] >= threshold:
                last_above = j
                quiet_run = 0
            else:
                quiet_run += 1
                # A footfall rings: the envelope dips below the threshold
                # and back within milliseconds. Only a quiet stretch longer
                # than the refractory period ends the impact.
                if quiet_run > refractory:
                    break
            j += 1
        peak_offset = run_start
        peak_value = 0.0
        for k in range(run_start, last_above + 1):
            if k in gap_offsets:
                continue
            if abs(centred[k]) > peak_value:
                peak_value = abs(centred[k])
                peak_offset = k
        impacts.append(
            Impact(
                sample_index=slice_.first_sample_index + offset + peak_offset,
                offset=offset + peak_offset,
                time_s=(offset + peak_offset) / rate,
                peak_counts=int(round(peak_value)),
                duration_s=(last_above - run_start + 1) / rate,
            )
        )
        i = last_above + 1

    intervals = [
        b.time_s - a.time_s
        for a, b in zip(impacts, impacts[1:], strict=False)
        if config.GAIT_MIN_INTERVAL_S <= b.time_s - a.time_s <= config.GAIT_MAX_INTERVAL_S
    ]
    mean = stdev = cv = cadence = None
    if len(impacts) >= config.GAIT_MIN_IMPACTS and len(intervals) >= 2:
        mean = statistics.fmean(intervals)
        stdev = statistics.stdev(intervals)
        if mean > 0:
            cv = stdev / mean
            cadence = 1.0 / mean

    peaks = [im.peak_counts for im in impacts]
    return GaitSummary(
        impacts=tuple(impacts),
        interval_mean_s=mean,
        interval_stdev_s=stdev,
        interval_cv=cv,
        cadence_hz=cadence,
        peak_mean_counts=statistics.fmean(peaks) if peaks else None,
        peak_max_counts=max(peaks) if peaks else None,
        analysed_from=offset,
        analysed_count=count,
        excluded_actuator_samples=excluded,
        noise_floor_counts=floor,
        threshold_counts=threshold,
    )


# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Behaviour:
    """What the animal was doing, from both sensors, with its own workings shown.

    Attributes:
        motion: STATIONARY, WALKING, RUNNING or UNKNOWN.
        direction: APPROACHING, RECEDING, STATIONARY or UNKNOWN.
        source: Which sensors contributed - "vision_and_seismic",
            "vision_only", "seismic_only" or "none".
        agreement: "agree", "disagree" or "unavailable", comparing the two
            independent speed estimates. A disagreement suppresses nothing;
            it marks the record for a human.
        vision_speed_mps: |d(range)/dt| from the boxes.
        seismic_speed_mps: cadence x the species' nominal stride.
        label: The species the two estimates are about, when there is one.
    """

    motion: str
    direction: str
    source: str
    agreement: str
    vision_speed_mps: float | None
    seismic_speed_mps: float | None
    label: str | None


def behaviour(
    track: RangeTrack | None, gait: GaitSummary | None, label: str | None = None
) -> Behaviour:
    """Combine the trajectory and the impact train into one state.

    The two sensors answer different halves. Only vision can say
    approaching or receding - the geophone has no bearing. Only the
    geophone can tell a standing animal from an absent one, because a watch
    with no boxes looks the same either way. Speed is the one thing both
    can estimate, which is why it is the cross-check rather than an input.

    Args:
        track: The species' range trajectory, or None.
        gait: The impact train, or None.
        label: Species label for the stride lookup, defaulting to the
            track's.

    Returns:
        A Behaviour. UNKNOWN in both fields is the common answer and an
        honest one.
    """
    species_label = label or (track.label if track is not None else None)
    species = config.SPECIES_REGISTRY.get(species_label) if species_label else None

    vision_speed = track.speed_mps if track is not None else None
    seismic_speed = None
    if gait is not None and gait.cadence_hz and species and species.stride_length_m > 0:
        seismic_speed = gait.cadence_hz * species.stride_length_m

    direction = track.direction if track is not None else UNKNOWN

    agreement = "unavailable"
    if vision_speed is not None and seismic_speed is not None:
        low, high = sorted((vision_speed, seismic_speed))
        if low <= 0:
            agreement = "disagree" if high > 0 else "agree"
        else:
            agreement = (
                "agree" if high / low <= config.BEHAVIOUR_SPEED_AGREEMENT_FACTOR else "disagree"
            )

    if vision_speed is not None and seismic_speed is not None:
        source = "vision_and_seismic"
    elif vision_speed is not None:
        source = "vision_only"
    elif seismic_speed is not None:
        source = "seismic_only"
    else:
        source = "none"

    motion = UNKNOWN
    if gait is not None and gait.impact_count == 0 and direction == STATIONARY:
        # Both sensors agreeing on nothing happening is the one case where
        # "stationary" is a measurement rather than an absence of one.
        motion = STATIONARY
    else:
        # The seismic estimate is preferred where it exists: a footfall rate
        # is a direct measurement of locomotion, while the vision speed is
        # a fractional rate multiplied by a distance that is itself
        # +-30-50%. Vision is the fallback, not the authority.
        speed = seismic_speed if seismic_speed is not None else vision_speed
        if speed is not None and species and species.walk_speed_max_mps > 0:
            motion = RUNNING if speed > species.walk_speed_max_mps else WALKING

    return Behaviour(
        motion=motion,
        direction=direction,
        source=source,
        agreement=agreement,
        vision_speed_mps=vision_speed,
        seismic_speed_mps=seismic_speed,
        label=species_label,
    )


# ---------------------------------------------------------------------------
# Retreat (shared with the no-retreat flag, plan item 10 / D8)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetreatVerdict:
    """Whether the animal left after the deterrent fired.

    Attributes:
        retreated: True if it withdrew, False if it is still there or
            closing, **None if the node could not tell**. None is not a
            weak False and must not be routed as one: FLAG_NO_RETREAT
            escalates an alert to `critical` and sends a human into a
            forest, so an undetermined verdict has to behave exactly like a
            normal deterred event.
        reason: Why, in a word a log can carry - "no_track",
            "too_few_frames", "receding", "closing", "holding".
        direction: The trajectory's own verdict over the post-fire window.
        relative_range: Last distance over first, from box heights alone,
            across that window. Exact up to the detector's box noise - no
            assumed animal size enters it.
        frames: How many rangeable boxes the window had.
    """

    retreated: bool | None
    reason: str
    direction: str
    relative_range: float | None
    frames: int


def retreat_verdict(
    frames: Sequence,
    label: str,
    since_monotonic_s: float,
    optics: Optics = NOMINAL_OPTICS,
) -> RetreatVerdict:
    """Did it leave after the fire at `since_monotonic_s`? Never raises.

    This is the one function here the field depends on: plan item 10 reads
    it to decide whether to set FLAG_NO_RETREAT, and the recorder stores
    the same verdict on the record. One implementation on purpose - two
    answers to "is it still there" would drift, and the one that drifted
    would be the one nobody tested.

    Built on the relative trajectory rather than the absolute range,
    because the question is directional and the ratio is the part that does
    not depend on how big the animal actually is.

    Args:
        frames: The watch's track frames, including the post-fire tail.
        label: The species the deterrent was fired at.
        since_monotonic_s: When the fire started. Frames before it are
            ignored.
        optics: Focal length, which cancels out of the ratio but is needed
            for the trajectory fit's absolute ranges.

    Returns:
        A RetreatVerdict, with `retreated=None` whenever the window did not
        contain enough usable boxes to say.
    """
    try:
        track = range_track(frames, label, optics, since_monotonic_s=since_monotonic_s)
    except Exception as exc:  # noqa: BLE001 - never cost the event
        logger.warning("retreat verdict failed, reporting undetermined: %s", exc)
        return RetreatVerdict(None, "error", UNKNOWN, None, 0)

    count = len(track.samples)
    if count == 0:
        # No boxes after the fire. Tempting to read as "it left", and
        # wrong: the overwhelmingly more common cause is that the camera
        # was closed, the night was dark, or the detector missed. The node
        # cannot distinguish those from an empty clearing, so it does not
        # claim to.
        return RetreatVerdict(None, "no_track", UNKNOWN, None, 0)
    if track.direction == UNKNOWN:
        return RetreatVerdict(None, "too_few_frames", UNKNOWN, track.relative_range, count)
    if track.direction == RECEDING:
        return RetreatVerdict(True, "receding", RECEDING, track.relative_range, count)
    reason = "closing" if track.direction == APPROACHING else "holding"
    return RetreatVerdict(False, reason, track.direction, track.relative_range, count)
