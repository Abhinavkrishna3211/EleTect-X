"""Tests for perception/kinematics.py - ranging, gait, behaviour, retreat."""

import json
import math
import random
from dataclasses import dataclass

import pytest

from perception import kinematics
from perception.seismic_stream import SeismicGap, SeismicSlice
from services import config

RATE = config.SEISMIC_SAMPLE_RATE_HZ


@dataclass(frozen=True)
class Box:
    """A detector box, duck-typed the way kinematics consumes it."""

    label: str
    confidence: float
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class Frame:
    """A TrackFrame, duck-typed."""

    poll: int
    frame_index: int
    timestamp_s: float
    sample_index: int | None
    boxes: tuple


@dataclass(frozen=True)
class Span:
    """An ActuatorSpan, duck-typed."""

    actuator: str
    start_monotonic_s: float
    end_monotonic_s: float
    start_index: int | None
    count: int


def centred_box(label: str, height: int, *, confidence: float = 0.8) -> Box:
    """A box of the given height, well clear of every frame edge."""
    return Box(
        label=label,
        confidence=confidence,
        x=config.CAMERA_FRAME_WIDTH // 2 - 60,
        y=max(config.RANGE_EDGE_MARGIN_PX + 10, (config.CAMERA_FRAME_HEIGHT - height) // 2),
        width=120,
        height=height,
    )


def height_for(distance_m: float, label: str = "Elephant") -> int:
    """The box height an animal of `label` would subtend at `distance_m`."""
    species = config.SPECIES_REGISTRY[label]
    return int(round(species.shoulder_height_m * kinematics.NOMINAL_OPTICS.focal_length_px
                     / distance_m))


def approach_track(
    start_m: float, end_m: float, frames: int, *, label: str = "Elephant", t0: float = 100.0
) -> list[Frame]:
    """A geometric approach from `start_m` to `end_m`, one frame per second."""
    out = []
    for i in range(frames):
        fraction = i / (frames - 1) if frames > 1 else 0.0
        distance = start_m * (end_m / start_m) ** fraction
        out.append(
            Frame(
                poll=i,
                frame_index=i,
                timestamp_s=t0 + i,
                sample_index=i * RATE,
                boxes=(centred_box(label, height_for(distance, label)),),
            )
        )
    return out


def impact_train(
    duration_s: float, interval_s: float, *, first_s: float = 0.5, amplitude: int = 600
) -> list[int]:
    """Quiet ground with a damped footfall impulse every `interval_s`."""
    rng = random.Random(1234)
    counts = [int(rng.gauss(0, 3)) for _ in range(int(duration_s * RATE))]
    t = first_s
    while t < duration_s - 0.3:
        start = int(t * RATE)
        for i in range(40):
            counts[start + i] += int(amplitude * math.exp(-i / 8.0) * math.sin(i * 0.9))
        t += interval_s
    return counts


def quiet_slice(counts, *, first_sample_index: int = 0, gaps=()) -> SeismicSlice:
    """Wrap raw counts in a slice."""
    return SeismicSlice(
        first_sample_index=first_sample_index,
        counts=tuple(counts),
        gaps=tuple(gaps),
        geophone_ok=True,
    )


# -- optics -----------------------------------------------------------------


def test_nominal_focal_length_matches_the_documented_figure():
    """D9 quotes ~880 px for a 95 degree lens at 1920 px; the code must agree."""
    assert kinematics.NOMINAL_OPTICS.focal_length_px == pytest.approx(880, abs=1.0)
    assert kinematics.NOMINAL_OPTICS.calibrated is False


def test_focal_length_rejects_impossible_lenses():
    """A zero or 180 degree field of view has no pinhole focal length."""
    assert kinematics.focal_length_px(0.0, 1920) == 0.0
    assert kinematics.focal_length_px(180.0, 1920) == 0.0
    assert kinematics.focal_length_px(95.0, 0) == 0.0


def test_missing_calibration_file_is_the_normal_state(tmp_path):
    """A node ships uncalibrated; that is not an error and not a warning."""
    optics = kinematics.load_optics(tmp_path / "nothing.json")
    assert optics is kinematics.NOMINAL_OPTICS


def test_malformed_calibration_falls_back_and_warns(tmp_path, caplog):
    """Somebody ran the calibration and it is not being used - say so."""
    path = tmp_path / "calib.json"
    path.write_text("{not json", encoding="utf-8")
    with caplog.at_level("WARNING"):
        optics = kinematics.load_optics(path)
    assert optics is kinematics.NOMINAL_OPTICS
    assert "unusable" in caplog.text


def test_non_positive_focal_length_is_refused(tmp_path, caplog):
    """A calibration that fitted a negative focal length is worse than none."""
    path = tmp_path / "calib.json"
    path.write_text(json.dumps({"fx": -10.0, "image_width": 1920}), encoding="utf-8")
    with caplog.at_level("WARNING"):
        assert kinematics.load_optics(path) is kinematics.NOMINAL_OPTICS


def test_calibration_is_read_and_marks_records_calibrated(tmp_path):
    """The whole point of running it: ranges stop being stamped uncalibrated."""
    path = tmp_path / "calib.json"
    path.write_text(
        json.dumps({"fx": 905.0, "image_width": 1920, "rms_reprojection_px": 0.31}),
        encoding="utf-8",
    )
    optics = kinematics.load_optics(path)
    assert optics.calibrated is True
    assert optics.focal_length_px == pytest.approx(905.0)
    assert optics.rms_reprojection_px == pytest.approx(0.31)


def test_calibration_shot_at_another_resolution_is_rescaled(tmp_path):
    """Focal length in pixels scales with the pixel count across the angle.

    Getting this wrong silently would scale every range in the corpus by
    the resolution ratio, which is exactly the kind of error a corpus
    carries forever.
    """
    path = tmp_path / "calib.json"
    path.write_text(json.dumps({"fx": 452.0, "image_width": 960}), encoding="utf-8")
    optics = kinematics.load_optics(path)
    assert optics.focal_length_px == pytest.approx(904.0)


# -- box eligibility --------------------------------------------------------


def test_centred_box_is_rangeable():
    """The ordinary case, so the exclusions below mean something."""
    assert kinematics.box_exclusion(centred_box("Elephant", 300)) is None


@pytest.mark.parametrize(
    "box",
    [
        Box("Elephant", 0.9, 0, 300, 200, 300),
        Box("Elephant", 0.9, 800, 0, 200, 300),
        Box("Elephant", 0.9, config.CAMERA_FRAME_WIDTH - 200, 300, 200, 300),
        Box("Elephant", 0.9, 800, config.CAMERA_FRAME_HEIGHT - 300, 200, 300),
    ],
    ids=["left", "top", "right", "bottom"],
)
def test_boxes_touching_any_edge_are_truncated(box):
    """Part of the animal is outside the image, so its height is a lower bound.

    The resulting range reads as too far, and it does so in a fixed
    direction - an animal walking in from the edge would appear to close
    faster than it does.
    """
    assert kinematics.box_exclusion(box) == kinematics.EXCLUDED_TRUNCATED


def test_frame_filling_box_is_excluded():
    """The detector's documented degenerate mode carries no localisation."""
    box = Box(
        "Elephant",
        0.9,
        config.RANGE_EDGE_MARGIN_PX + 1,
        config.RANGE_EDGE_MARGIN_PX + 1,
        config.CAMERA_FRAME_WIDTH - 2 * config.RANGE_EDGE_MARGIN_PX - 3,
        config.CAMERA_FRAME_HEIGHT - 2 * config.RANGE_EDGE_MARGIN_PX - 3,
    )
    assert kinematics.box_exclusion(box) == kinematics.EXCLUDED_FRAME_FILLING


def test_tiny_box_is_excluded():
    """Below the floor, a pixel of edge noise is percents of the range."""
    small = centred_box("Elephant", config.RANGE_MIN_BOX_HEIGHT_PX - 1)
    assert kinematics.box_exclusion(small) == kinematics.EXCLUDED_TOO_SMALL


def test_exclusions_are_counted_not_discarded():
    """A watch where every box was truncated is itself a reading."""
    frames = [
        Frame(0, 0, 1.0, None, (Box("Elephant", 0.9, 0, 10, 300, 400),)),
        Frame(1, 1, 2.0, None, (centred_box("Elephant", 10),)),
    ]
    track = kinematics.range_track(frames, "Elephant")
    assert track.samples == ()
    assert track.excluded == {
        kinematics.EXCLUDED_TRUNCATED: 1,
        kinematics.EXCLUDED_TOO_SMALL: 1,
    }


# -- absolute range ---------------------------------------------------------


def test_absolute_range_is_the_pinhole_relation():
    """Distance is H x f / h, and nothing cleverer."""
    species = config.SPECIES_REGISTRY["Elephant"]
    expected = species.shoulder_height_m * kinematics.NOMINAL_OPTICS.focal_length_px / 150
    assert kinematics.range_m(150, "Elephant") == pytest.approx(expected)


def test_range_needs_a_species_with_a_body_plan():
    """An unregistered label cannot be ranged, and says so rather than guessing."""
    assert kinematics.range_m(150, "Cattle") is None


def test_range_rejects_degenerate_inputs():
    """A zero-height box and a zero focal length both mean no distance."""
    assert kinematics.range_m(0, "Elephant") is None
    broken = kinematics.Optics(focal_length_px=0.0, calibrated=False, source="test")
    assert kinematics.range_m(150, "Elephant", broken) is None


# -- trajectory -------------------------------------------------------------


def test_relative_ratio_is_exact_while_absolute_range_carries_its_error_band():
    """The plan's central claim about ranging, asserted directly.

    The animal here is a 1.95 m elephant - a well-grown juvenile - against
    the registry's 2.7 m nominal adult. Every absolute range is therefore
    wrong by exactly the height ratio, 38%, squarely inside the stated
    +-30-50% and wrong in a consistent direction. The *relative*
    trajectory, which is what the retreat decision rests on, is
    unaffected: the unknown height cancels, so it recovers the true
    approach to within box quantisation.
    """
    real_height_m = 1.95
    nominal_height_m = config.SPECIES_REGISTRY["Elephant"].shoulder_height_m
    focal = kinematics.NOMINAL_OPTICS.focal_length_px
    distances = [40.0, 33.0, 26.0, 20.0, 15.0]
    frames = [
        Frame(i, i, 100.0 + i, None,
              (centred_box("Elephant", int(round(real_height_m * focal / d))),))
        for i, d in enumerate(distances)
    ]
    track = kinematics.range_track(frames, "Elephant")

    assert track.relative_range == pytest.approx(15.0 / 40.0, rel=0.02)
    for sample, truth in zip(track.samples, distances, strict=True):
        assert sample.range_m == pytest.approx(truth * nominal_height_m / real_height_m,
                                               rel=0.02)
        assert sample.range_m > truth  # the error is in a known direction
        assert 0.30 <= (sample.range_m - truth) / truth <= 0.50


def test_fractional_rate_is_independent_of_the_assumed_height():
    """Two species-height assumptions, one trajectory, one rate.

    This is why the direction of travel is trustworthy before the camera
    has ever been calibrated.
    """
    focal = kinematics.NOMINAL_OPTICS.focal_length_px
    heights = [int(round(2.0 * focal / d)) for d in (50.0, 40.0, 32.0, 26.0, 20.0)]
    elephant = kinematics.range_track(
        [Frame(i, i, 100.0 + i, None, (centred_box("Elephant", h),))
         for i, h in enumerate(heights)],
        "Elephant",
    )
    boar = kinematics.range_track(
        [Frame(i, i, 100.0 + i, None, (centred_box("Boar", h),))
         for i, h in enumerate(heights)],
        "Boar",
    )
    assert elephant.median_range_m != pytest.approx(boar.median_range_m)
    assert elephant.fractional_rate_per_s == pytest.approx(boar.fractional_rate_per_s)
    assert elephant.relative_range == pytest.approx(boar.relative_range)


def test_approaching_and_receding_are_distinguished():
    """The one thing only vision can answer."""
    closing = kinematics.range_track(approach_track(60.0, 20.0, 8), "Elephant")
    leaving = kinematics.range_track(approach_track(20.0, 60.0, 8), "Elephant")
    assert closing.direction == kinematics.APPROACHING
    assert closing.fractional_rate_per_s < 0
    assert leaving.direction == kinematics.RECEDING
    assert leaving.fractional_rate_per_s > 0


def test_a_standing_animal_reads_as_stationary():
    """Flat box heights must not be rounded into a direction."""
    frames = [
        Frame(i, i, 100.0 + i, None, (centred_box("Elephant", 120),)) for i in range(8)
    ]
    track = kinematics.range_track(frames, "Elephant")
    assert track.direction == kinematics.STATIONARY
    assert track.relative_range == pytest.approx(1.0)


def test_too_few_frames_is_unknown_not_a_guess():
    """Two boxes a moment apart can show any slope you like."""
    frames = approach_track(60.0, 20.0, config.RANGE_MIN_TRAJECTORY_FRAMES - 1)
    track = kinematics.range_track(frames, "Elephant")
    assert track.samples
    assert track.direction == kinematics.UNKNOWN
    assert track.fractional_rate_per_s is None


def test_too_short_a_span_is_unknown():
    """Enough frames, not enough time."""
    frames = [
        Frame(i, i, 100.0 + i * 0.1, None, (centred_box("Elephant", 100 + i * 20),))
        for i in range(6)
    ]
    track = kinematics.range_track(frames, "Elephant")
    assert track.span_s < config.RANGE_MIN_TRAJECTORY_SPAN_S
    assert track.direction == kinematics.UNKNOWN


def test_the_nearest_animal_is_tracked_not_the_group_centroid():
    """A herd's centroid can recede while the nearest animal closes.

    The nearest box is deliberately not the first one in either frame -
    taking whichever box the detector happened to list first would pass a
    test that only ever puts the tallest at the front.
    """
    frames = [
        Frame(0, 0, 100.0, None,
              (centred_box("Elephant", 60), centred_box("Elephant", 100))),
        Frame(1, 1, 103.0, None,
              (centred_box("Elephant", 50), centred_box("Elephant", 140))),
        Frame(2, 2, 106.0, None,
              (centred_box("Elephant", 30), centred_box("Elephant", 200))),
    ]
    track = kinematics.range_track(frames, "Elephant")
    assert [s.height_px for s in track.samples] == [100.0, 140.0, 200.0]
    assert track.direction == kinematics.APPROACHING


def test_other_species_boxes_are_ignored_not_excluded():
    """A boar in frame during an elephant encounter is not an elephant failure."""
    frames = [
        Frame(0, 0, 100.0, None, (centred_box("Boar", 90), centred_box("Elephant", 120))),
    ]
    track = kinematics.range_track(frames, "Elephant")
    assert len(track.samples) == 1
    assert track.excluded == {}


def test_range_bands_follow_the_configured_edges():
    """Bands, never metres, are what anything user-facing is allowed to see."""
    near, mid = config.RANGE_BAND_EDGES_M
    for distance, band in ((near / 2, "near"), ((near + mid) / 2, "mid"), (mid * 2, "far")):
        frames = approach_track(distance, distance, 5)
        assert kinematics.range_track(frames, "Elephant").range_band == band


def test_range_tracks_covers_each_label_once():
    """One track per species asked for, dropping the ones with nothing at all."""
    frames = [
        Frame(i, i, 100.0 + i, None,
              (centred_box("Elephant", 100 + 10 * i), centred_box("Boar", 50)))
        for i in range(5)
    ]
    tracks = kinematics.range_tracks(frames, ["Elephant", "Boar", "Fox"])
    assert [t.label for t in tracks] == ["Elephant", "Boar"]


def test_since_monotonic_s_restricts_the_window():
    """What makes the retreat verdict a view of this trajectory, not a second one."""
    frames = approach_track(60.0, 20.0, 11)
    track = kinematics.range_track(frames, "Elephant", since_monotonic_s=105.0)
    assert [s.poll for s in track.samples] == [5, 6, 7, 8, 9, 10]


# -- gait -------------------------------------------------------------------


def test_no_waveform_means_no_gait():
    """An acoustic-initiated event has no geophone behind it."""
    assert kinematics.gait_summary(None) is None
    assert kinematics.gait_summary(quiet_slice([])) is None


def test_a_known_impact_train_is_recovered():
    """Twelve footfalls 0.8 s apart; the cadence is the species discriminator."""
    gait = kinematics.gait_summary(quiet_slice(impact_train(10.0, 0.8)))
    assert gait.impact_count == 12
    assert gait.cadence_hz == pytest.approx(1.25, rel=0.02)
    assert gait.interval_mean_s == pytest.approx(0.8, rel=0.02)
    assert gait.interval_cv < 0.05  # a walking animal is metronomic
    assert gait.peak_max_counts > gait.threshold_counts


def test_impact_times_land_on_the_real_footfalls():
    """Within the envelope window, which is what the smoothing costs."""
    gait = kinematics.gait_summary(quiet_slice(impact_train(6.0, 0.8)))
    expected = [0.5 + 0.8 * i for i in range(gait.impact_count)]
    for impact, truth in zip(gait.impacts, expected, strict=True):
        assert impact.time_s == pytest.approx(truth, abs=3 * config.GAIT_ENVELOPE_WINDOW_S)


def test_impact_sample_indices_are_absolute():
    """A record's impacts must be addressable against the stored waveform."""
    gait = kinematics.gait_summary(quiet_slice(impact_train(6.0, 0.8),
                                               first_sample_index=50_000))
    assert all(i.sample_index == 50_000 + i.offset for i in gait.impacts)


def test_quiet_ground_yields_no_impacts_and_still_reports_its_floor():
    """The negative class is most of this corpus and must be legible.

    Without the floor and threshold stored, "no impacts" and "threshold
    set too high" are the same row.
    """
    rng = random.Random(99)
    gait = kinematics.gait_summary(quiet_slice([int(rng.gauss(0, 3)) for _ in range(RATE * 5)]))
    assert gait.impact_count == 0
    assert gait.cadence_hz is None
    assert gait.threshold_counts >= gait.noise_floor_counts + config.GAIT_MIN_IMPACT_COUNTS


def test_a_ringing_footfall_is_one_impact_not_several():
    """The envelope dips below the threshold mid-ring; the refractory holds it."""
    gait = kinematics.gait_summary(quiet_slice(impact_train(5.0, 1.0)))
    assert gait.impact_count == 5  # 0.5 s, 1.5 s, ... 4.5 s - one each, not one per ring
    # Each one is a bounded ring-down, not a run merged across two steps.
    assert all(i.duration_s < 0.25 for i in gait.impacts)


def test_zero_filled_gaps_do_not_deflate_the_noise_floor():
    """A gap is absence, not perfect quiet.

    Counting the zeros would pull the median and the MAD toward nothing,
    and six sigma of nothing finds a herd in the quantisation noise.
    """
    counts = impact_train(10.0, 0.8)
    # Most of the record is hole, so counting the zeros does not nudge the
    # median - it takes it over. A smaller gap lets a broken floor stay
    # inside any sane tolerance, which is how this test used to pass
    # against a detector that ignored the gap list entirely.
    gap_start, gap_len = 2 * RATE, 6 * RATE
    for i in range(gap_start, gap_start + gap_len):
        counts[i] = 0
    gapped = quiet_slice(counts, gaps=(SeismicGap(start_index=gap_start, count=gap_len),))
    clean = quiet_slice(impact_train(10.0, 0.8))

    gait = kinematics.gait_summary(gapped)
    assert gait.threshold_counts == pytest.approx(
        kinematics.gait_summary(clean).threshold_counts, rel=0.12
    )
    assert gait.noise_floor_counts > 0.0
    # No impact may be reported from inside the hole.
    assert all(not gap_start <= i.offset < gap_start + gap_len for i in gait.impacts)


def test_analysis_stops_where_the_first_actuator_started():
    """Not "skip the overlap" - everything after the fire is suspect.

    The horn is the loudest thing this structure will experience and it
    rings afterwards, so the clean segment is the approach, which is
    before the fire by construction.
    """
    counts = impact_train(12.0, 0.8)
    fire_at = 8 * RATE
    span = Span("horn", 108.0, 111.8, start_index=fire_at, count=int(3.8 * RATE))
    gait = kinematics.gait_summary(quiet_slice(counts), (span,))
    assert gait.analysed_from == 0
    assert gait.analysed_count == fire_at
    assert gait.excluded_actuator_samples == len(counts) - fire_at
    assert all(i.offset < fire_at for i in gait.impacts)


def test_a_record_that_starts_after_the_fire_has_no_clean_segment():
    """Better to report nothing than to report the horn as a gait."""
    counts = impact_train(6.0, 0.8)
    slice_ = quiet_slice(counts, first_sample_index=10_000)
    span = Span("horn", 1.0, 4.8, start_index=9_000, count=950)
    gait = kinematics.gait_summary(slice_, (span,))
    assert gait.analysed_count == 0
    assert gait.impacts == ()
    assert gait.excluded_actuator_samples == len(counts)


def test_actuator_spans_without_a_sample_index_are_ignored():
    """A span the stream could not place cannot cut the waveform."""
    counts = impact_train(10.0, 0.8)
    span = Span("horn", 108.0, 111.8, start_index=None, count=0)
    gait = kinematics.gait_summary(quiet_slice(counts), (span,))
    assert gait.analysed_count == len(counts)
    assert gait.excluded_actuator_samples == 0


def test_two_separate_events_in_one_record_are_not_one_gait():
    """Intervals past GAIT_MAX_INTERVAL_S are not a walk, they are a coincidence."""
    counts = [0] * (RATE * 12)
    for t in (1.0, 9.0):
        start = int(t * RATE)
        for i in range(40):
            counts[start + i] += int(600 * math.exp(-i / 8.0) * math.sin(i * 0.9))
    gait = kinematics.gait_summary(quiet_slice(counts))
    assert gait.impact_count == 2
    assert gait.cadence_hz is None


def test_gait_never_raises(caplog):
    """An annotation pass must not cost the record it annotates."""

    class Exploding:
        first_sample_index = 0
        gaps = ()

        def __len__(self):
            return 100

        @property
        def counts(self):
            raise RuntimeError("boom")

    with caplog.at_level("WARNING"):
        assert kinematics.gait_summary(Exploding()) is None
    assert "gait summary failed" in caplog.text


# -- behaviour --------------------------------------------------------------


def walking_gait(label: str) -> kinematics.GaitSummary:
    """A gait whose cadence puts `label` just inside its walking speed."""
    species = config.SPECIES_REGISTRY[label]
    cadence = (species.walk_speed_max_mps * 0.5) / species.stride_length_m
    return kinematics.GaitSummary(
        impacts=(), interval_mean_s=1 / cadence, interval_stdev_s=0.01,
        interval_cv=0.01, cadence_hz=cadence, peak_mean_counts=500.0,
        peak_max_counts=600, analysed_from=0, analysed_count=1000,
        excluded_actuator_samples=0, noise_floor_counts=2.0, threshold_counts=15.0,
    )


def test_behaviour_with_neither_sensor_is_unknown():
    """The honest answer, and a common one."""
    state = kinematics.behaviour(None, None, "Elephant")
    assert state.motion == kinematics.UNKNOWN
    assert state.direction == kinematics.UNKNOWN
    assert state.source == "none"
    assert state.agreement == "unavailable"


def test_seismic_alone_gives_motion_but_never_direction():
    """The geophone has no bearing; only vision can say approaching."""
    state = kinematics.behaviour(None, walking_gait("Elephant"), "Elephant")
    assert state.motion == kinematics.WALKING
    assert state.direction == kinematics.UNKNOWN
    assert state.source == "seismic_only"


def test_vision_alone_gives_direction_and_a_speed_estimate():
    """And is the fallback for motion, not the authority."""
    track = kinematics.range_track(approach_track(60.0, 20.0, 11), "Elephant")
    state = kinematics.behaviour(track, None)
    assert state.direction == kinematics.APPROACHING
    assert state.source == "vision_only"
    assert state.vision_speed_mps == pytest.approx(track.speed_mps)


def test_running_is_called_against_the_species_walking_ceiling():
    """1.5 m/s is a brisk walk for an elephant and a sprint for a fox."""
    species = config.SPECIES_REGISTRY["Fox"]
    fast = kinematics.GaitSummary(
        impacts=(), interval_mean_s=0.2, interval_stdev_s=0.01, interval_cv=0.05,
        cadence_hz=(species.walk_speed_max_mps * 2) / species.stride_length_m,
        peak_mean_counts=100.0, peak_max_counts=150, analysed_from=0, analysed_count=500,
        excluded_actuator_samples=0, noise_floor_counts=2.0, threshold_counts=15.0,
    )
    assert kinematics.behaviour(None, fast, "Fox").motion == kinematics.RUNNING


def test_two_sensors_agreeing_is_recorded_as_agreement():
    """The cross-check working, which is most records."""
    track = kinematics.range_track(approach_track(40.0, 30.0, 11), "Elephant")
    species = config.SPECIES_REGISTRY["Elephant"]
    matched = kinematics.GaitSummary(
        impacts=(), interval_mean_s=1.0, interval_stdev_s=0.01, interval_cv=0.01,
        cadence_hz=track.speed_mps / species.stride_length_m,
        peak_mean_counts=500.0, peak_max_counts=600, analysed_from=0, analysed_count=1000,
        excluded_actuator_samples=0, noise_floor_counts=2.0, threshold_counts=15.0,
    )
    state = kinematics.behaviour(track, matched)
    assert state.source == "vision_and_seismic"
    assert state.agreement == "agree"


def test_disagreement_is_flagged_and_suppresses_nothing():
    """A disagreement is a flag, not a veto.

    The records where two measurements of one animal disagree are the ones
    worth a human's time, so they are marked rather than dropped.
    """
    track = kinematics.range_track(approach_track(80.0, 20.0, 11), "Elephant")
    state = kinematics.behaviour(track, walking_gait("Elephant"))
    assert state.agreement == "disagree"
    assert state.motion != kinematics.UNKNOWN
    assert state.vision_speed_mps is not None
    assert state.seismic_speed_mps is not None


def test_both_sensors_quiet_is_a_measured_stationary():
    """Both sensors quiet is the one measured stationary.

    No footfalls and a flat trajectory is the only case where standing
    still is a measurement rather than an absence of one.
    """
    frames = [Frame(i, i, 100.0 + i, None, (centred_box("Elephant", 120),)) for i in range(8)]
    track = kinematics.range_track(frames, "Elephant")
    silent = kinematics.GaitSummary(
        impacts=(), interval_mean_s=None, interval_stdev_s=None, interval_cv=None,
        cadence_hz=None, peak_mean_counts=None, peak_max_counts=None,
        analysed_from=0, analysed_count=1000, excluded_actuator_samples=0,
        noise_floor_counts=2.0, threshold_counts=15.0,
    )
    assert kinematics.behaviour(track, silent).motion == kinematics.STATIONARY


def test_behaviour_without_a_body_plan_cannot_call_motion():
    """An unregistered species has no stride and no walking ceiling."""
    state = kinematics.behaviour(None, walking_gait("Elephant"), "Cattle")
    assert state.motion == kinematics.UNKNOWN
    assert state.seismic_speed_mps is None


# -- retreat ----------------------------------------------------------------


def test_receding_after_the_fire_is_a_retreat():
    """The deterrent worked, and nothing escalates."""
    verdict = kinematics.retreat_verdict(approach_track(20.0, 60.0, 11), "Elephant", 100.0)
    assert verdict.retreated is True
    assert verdict.reason == "receding"
    assert verdict.relative_range > 1.0


def test_still_closing_after_the_fire_is_not_a_retreat():
    """What FLAG_NO_RETREAT exists to carry."""
    verdict = kinematics.retreat_verdict(approach_track(60.0, 20.0, 11), "Elephant", 100.0)
    assert verdict.retreated is False
    assert verdict.reason == "closing"


def test_holding_station_after_the_fire_is_not_a_retreat():
    """Holding station is a failed deterrent too.

    An elephant that simply stands there is the case a cloud-side
    inference from a repeat trigger would miss entirely.
    """
    frames = [Frame(i, i, 100.0 + i, None, (centred_box("Elephant", 120),)) for i in range(8)]
    verdict = kinematics.retreat_verdict(frames, "Elephant", 100.0)
    assert verdict.retreated is False
    assert verdict.reason == "holding"


def test_no_boxes_after_the_fire_is_undetermined_and_not_a_retreat():
    """The trap, asserted directly.

    An empty post-fire window overwhelmingly means the camera was closed,
    the night was dark, or the detector missed - not that a three-tonne
    animal left. None must never be routed as a False.
    """
    verdict = kinematics.retreat_verdict(approach_track(60.0, 20.0, 11), "Elephant", 500.0)
    assert verdict.retreated is None
    assert verdict.reason == "no_track"
    assert verdict.frames == 0


def test_too_few_post_fire_frames_is_undetermined():
    """One box after the fire is not a trajectory."""
    frames = approach_track(60.0, 20.0, 11)
    verdict = kinematics.retreat_verdict(frames, "Elephant", 109.5)
    assert verdict.retreated is None
    assert verdict.reason == "too_few_frames"
    assert verdict.frames == 1


def test_retreat_never_raises(caplog):
    """It runs on the event path; item 10 reads it to decide an escalation."""

    class Exploding(list):
        def __iter__(self):
            raise RuntimeError("boom")

    with caplog.at_level("WARNING"):
        verdict = kinematics.retreat_verdict(Exploding(), "Elephant", 100.0)
    assert verdict.retreated is None
    assert verdict.reason == "error"


def test_retreat_and_the_trajectory_are_one_implementation():
    """D8 and D9 share a measurement rather than growing two.

    If this ever stops holding, the field and the corpus have begun to
    disagree about what retreating looks like, and the one that drifted
    would be the one nobody tested.
    """
    frames = approach_track(20.0, 60.0, 11)
    track = kinematics.range_track(frames, "Elephant", since_monotonic_s=103.0)
    verdict = kinematics.retreat_verdict(frames, "Elephant", 103.0)
    assert verdict.direction == track.direction
    assert verdict.relative_range == pytest.approx(track.relative_range)
    assert verdict.frames == len(track.samples)


# -- registry contract ------------------------------------------------------


@pytest.mark.parametrize("label", sorted(config.SPECIES_REGISTRY))
def test_every_species_carries_a_usable_body_plan(label):
    """D6's promise is that adding a species is one registry entry.

    A new entry with the fields left at their zero defaults would range as
    None and behave as unknown forever, silently - which is exactly the
    kind of omission that is only noticed when the corpus is being
    trained on months later.
    """
    species = config.SPECIES_REGISTRY[label]
    assert species.shoulder_height_m > 0
    assert species.stride_length_m > 0
    assert species.walk_speed_max_mps > 0


@pytest.mark.parametrize("label", sorted(config.SPECIES_REGISTRY))
def test_body_plans_are_physically_plausible(label):
    """A decimal-point slip here scales an entire species' corpus."""
    species = config.SPECIES_REGISTRY[label]
    assert 0.1 <= species.shoulder_height_m <= 4.0
    assert 0.1 <= species.stride_length_m <= 3.0
    assert 0.2 <= species.walk_speed_max_mps <= 5.0
    # A stride cannot plausibly exceed the animal's own height by much.
    assert species.stride_length_m <= species.shoulder_height_m * 1.5
