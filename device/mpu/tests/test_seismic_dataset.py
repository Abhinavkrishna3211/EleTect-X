"""perception/seismic_dataset.py - what the camera says a waveform contains.

The output of this module is training data, so the tests are weighted towards
the failures that produce a *plausible* corpus rather than the ones that raise.
Three of those matter more than the rest:

- a watch the camera could not see filed as `no_animal/`, which fills the
  negative class with unlabelled night elephants and teaches a future model
  that elephants only exist in daylight;
- two species in one watch filed under whichever one won the deterrence
  tie-break, which poisons that species' class with another's ground motion;
- a retention cap that evicts by age, which spends a scarce confirmed-elephant
  record to keep a hundred `unlabelled/` ones the camera never labelled.

None of those raises. Each is a silent, permanent loss of the only thing this
corpus exists to accumulate.
"""

from __future__ import annotations

import base64
import json
import math
import random
import struct

import pytest

from perception import kinematics
from perception import seismic_dataset as sd
from perception.seismic_stream import SeismicGap, SeismicSlice
from services import config


def _slice(counts=(1, -2, 3), first=100, gaps=(), ok=True):
    """A SeismicSlice with the shape the stream actually produces."""
    return SeismicSlice(first_sample_index=first, counts=tuple(counts), gaps=tuple(gaps),
                        geophone_ok=ok)


def _record(**overrides):
    """A complete record; every test overrides only the field it is about."""
    base = {
        "bucket": "elephant",
        "source": sd.SOURCE_CONFIRMED,
        "event_wall_s": 1_700_000_000.5,
        "event_monotonic_s": 42.0,
        "node_scope": "Elephant",
        "sta_lta_ratio": 6.25,
        "mcu_probability": 0.87,
        "feature_vector": (0.1,) * 8,
        "seismic_available": True,
        "seismic": _slice(),
    }
    base.update(overrides)
    return sd.SeismicRecord(**base)


class _Detection:
    """Detection-shaped, because track_frames() is duck-typed on purpose."""

    def __init__(self, label="Elephant", confidence=0.9, x=10, y=20, width=30, height=40):
        self.label = label
        self.confidence = confidence
        self.x = x
        self.y = y
        self.width = width
        self.height = height


class _Sample:
    """VisionTrackSample-shaped."""

    def __init__(self, poll=0, frame_index=0, timestamp_s=0.0, detections=()):
        self.poll = poll
        self.frame_index = frame_index
        self.timestamp_s = timestamp_s
        self.detections = tuple(detections)


# ---------------------------------------------------------------------------
# Buckets - the whole point of the module
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("confirming", "expected"),
    [
        (("Elephant",), "elephant"),
        (("Boar",), "boar"),
        (("Fox",), "fox"),
    ],
)
def test_one_confirmed_species_files_under_that_species(confirming, expected):
    """Each of the three deterrable species gets its own directory."""
    bucket, source = sd.bucket_for(confirming, could_see=True)
    assert bucket == expected
    assert source == sd.SOURCE_CONFIRMED


def test_camera_looked_and_saw_nothing_is_the_negative_class():
    """The free negative class: wind, rain and cattle, which is most triggers."""
    assert sd.bucket_for((), could_see=True) == (sd.NEGATIVE_BUCKET, sd.SOURCE_LOOKED)


def test_camera_could_not_look_is_unlabelled_and_never_the_negative_class():
    """The trap this module exists to avoid.

    "Saw nothing" and "could not see" produce an identical empty species list.
    Filing the second as no_animal/ is how a negative class quietly fills with
    night elephants the IR never lit, and nothing downstream could ever detect
    that it had happened.
    """
    bucket, source = sd.bucket_for((), could_see=False)
    assert bucket == sd.BLIND_BUCKET
    assert source == sd.SOURCE_BLIND
    assert bucket != sd.NEGATIVE_BUCKET


def test_two_species_in_one_watch_is_ambiguous_not_the_first_one():
    """A waveform holding an elephant *and* a boar belongs to neither class."""
    bucket, source = sd.bucket_for(("Elephant", "Boar"), could_see=True)
    assert bucket == sd.AMBIGUOUS_BUCKET
    assert source == sd.SOURCE_AMBIGUOUS


def test_ambiguous_wins_even_when_the_camera_was_blind():
    """Confirmations are evidence the camera saw, whatever could_see says."""
    assert sd.bucket_for(("Elephant", "Fox"), could_see=False)[0] == sd.AMBIGUOUS_BUCKET


def test_bucket_name_cannot_escape_the_dataset_directory():
    """The registry is a hand-edited table; a label is never a path fragment."""
    assert sd.bucket_for(("../../etc",), could_see=True)[0] == "etc"
    assert sd.bucket_for(("Wild Boar",), could_see=True)[0] == "wild_boar"
    assert sd.bucket_for(("///",), could_see=True)[0] == "unknown"


# ---------------------------------------------------------------------------
# The waveform survives the round trip
# ---------------------------------------------------------------------------


def test_samples_round_trip_through_base64_int16():
    """The waveform is the durable asset; it must come back bit-exact."""
    counts = (0, 1, -1, 32767, -32768, 1234)
    payload = _record(seismic=_slice(counts=counts)).to_dict()["seismic"]
    assert payload["encoding"] == "base64:int16le"
    raw = base64.b64decode(payload["samples"])
    assert struct.unpack(f"<{len(counts)}h", raw) == counts


def test_a_sample_the_adc_cannot_produce_is_clamped_not_dropped():
    """One impossible value must not cost the encounter, but must be loud."""
    decoded = struct.unpack("<3h", base64.b64decode(sd._encode_counts((70000, 5, -70000))))
    assert decoded == (32767, 5, -32768)


def test_the_slice_carries_its_own_scale_and_its_holes():
    """A corpus of raw counts with no scale or gap list beside it is unusable."""
    gaps = (SeismicGap(start_index=101, count=4),)
    payload = _record(seismic=_slice(counts=(1, 2, 3), gaps=gaps, ok=False)).to_dict()["seismic"]
    assert payload["first_sample_index"] == 100
    assert payload["sample_count"] == 3
    assert payload["lsb_volts"] == config.SEISMIC_LSB_VOLTS
    assert payload["sample_rate_hz_nominal"] == config.SEISMIC_SAMPLE_RATE_HZ
    assert payload["gaps"] == [{"start_index": 101, "count": 4}]
    assert payload["missing_samples"] == 4
    assert payload["geophone_ok"] is False


def test_no_stream_still_produces_a_record_with_its_vision_half():
    """The labelled half is the half that cannot be reconstructed afterwards."""
    track = (_Sample(detections=(_Detection(),)),)
    record = _record(seismic=None, track=sd.track_frames(track), could_see=True)
    data = record.to_dict()
    assert data["seismic"] is None
    assert record.sample_count == 0
    assert data["vision"]["track"][0]["boxes"][0]["label"] == "Elephant"


# ---------------------------------------------------------------------------
# Co-sampling - the reason this is one record and not two recordings
# ---------------------------------------------------------------------------


def test_track_frames_place_each_frame_on_the_sample_axis():
    """A reader must be able to scrub to a box and land on its ground motion."""
    samples = [_Sample(poll=i, frame_index=i, timestamp_s=float(i)) for i in range(3)]
    frames = sd.track_frames(samples, locate=lambda t: int(t * 100) + 500)
    assert [f.sample_index for f in frames] == [500, 600, 700]
    assert [f.poll for f in frames] == [0, 1, 2]


def test_track_frames_without_a_stream_keep_the_boxes_and_drop_only_the_index():
    """No waveform is no reason to throw away what the camera drew."""
    frames = sd.track_frames([_Sample(detections=(_Detection(),))], locate=None)
    assert frames[0].sample_index is None
    assert len(frames[0].boxes) == 1


def test_a_malformed_track_sample_is_skipped_rather_than_losing_the_record():
    """A detector that returned something unexpected must not cost the waveform."""
    frames = sd.track_frames([_Sample(poll=0), object(), _Sample(poll=2)])
    assert [f.poll for f in frames] == [0, 2]


def test_actuator_span_is_rounded_outward_onto_the_sample_axis():
    """Over-marking loses clean signal; under-marking leaks horn energy in."""
    span = sd.ActuatorSpan(actuator="horn", start_monotonic_s=10.0, end_monotonic_s=13.8)
    placed = sd.place_actuator(span, locate=lambda t: int(t * config.SEISMIC_SAMPLE_RATE_HZ))
    expected = int(3.8 * config.SEISMIC_SAMPLE_RATE_HZ) + 1
    assert placed.start_index == int(10.0 * config.SEISMIC_SAMPLE_RATE_HZ)
    assert placed.count >= expected
    assert placed.actuator == "horn"


def test_actuator_span_without_a_stream_keeps_its_monotonic_window():
    """The pair is kept so the range can be re-derived if the mapping changes."""
    span = sd.ActuatorSpan(actuator="led", start_monotonic_s=1.0, end_monotonic_s=2.0)
    placed = sd.place_actuator(span, locate=None)
    assert placed.start_index is None
    assert (placed.start_monotonic_s, placed.end_monotonic_s) == (1.0, 2.0)


# ---------------------------------------------------------------------------
# The writer
# ---------------------------------------------------------------------------


def test_write_puts_the_record_in_its_bucket_as_parseable_json(tmp_path):
    """One self-contained file per record - no waveform plus sidecar."""
    writer = sd.SeismicDatasetWriter(root=tmp_path)
    path = writer.write(_record(bucket="fox"))
    assert path is not None
    assert path.parent.name == "fox"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema"] == sd.SCHEMA
    assert data["label"]["bucket"] == "fox"


def test_the_filename_says_what_the_device_believed(tmp_path):
    """A corpus should be browsable without a parser, like the capture dir."""
    path = sd.SeismicDatasetWriter(root=tmp_path).write(_record())
    assert path.name.startswith("1700000000.500")
    assert "_sta6.25" in path.name
    assert "_p0.870" in path.name
    assert path.name.endswith("_n3.json")


def test_a_disabled_recorder_writes_nothing(tmp_path, monkeypatch):
    """The off switch is read per write, so it can be flipped without a restart."""
    monkeypatch.setattr(config, "SEISMIC_DATASET_ENABLED", False)
    writer = sd.SeismicDatasetWriter(root=tmp_path)
    assert writer.write(_record()) is None
    assert not list(tmp_path.rglob("*.json"))


def test_a_storage_failure_is_reported_as_none_and_never_raised(tmp_path, monkeypatch):
    """This is called mid-event, after the deterrents have fired."""
    monkeypatch.setattr(sd.storage, "atomic_write_bytes", lambda *_: False)
    assert sd.SeismicDatasetWriter(root=tmp_path).write(_record()) is None


def test_an_unserialisable_record_is_logged_rather_than_raised(tmp_path):
    """A record that cannot be turned into JSON must not reach the caller."""
    writer = sd.SeismicDatasetWriter(root=tmp_path)
    assert writer.write(_record(feature_vector=(object(),))) is None


# ---------------------------------------------------------------------------
# Retention - which records the node gives up when the disk fills
# ---------------------------------------------------------------------------


def _plant(root, bucket, name, size=1024, mtime=None):
    """Put a file of a known size and age in a bucket."""
    path = root / bucket / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    if mtime is not None:
        import os

        os.utime(path, (mtime, mtime))
    return path


def test_eviction_spends_unlabelled_before_anything_else(tmp_path):
    """Order is the policy: hardest to replace is given up last."""
    old_elephant = _plant(tmp_path, "elephant", "a.json", mtime=1000)
    new_unlabelled = _plant(tmp_path, "unlabelled", "b.json", mtime=9000)
    writer = sd.SeismicDatasetWriter(root=tmp_path, max_bytes=1024)
    assert writer.enforce_cap() == 1
    assert old_elephant.exists()
    assert not new_unlabelled.exists()


@pytest.mark.parametrize(
    ("cap", "gone"),
    [
        (3 * 1024, ("unlabelled",)),
        (2 * 1024, ("unlabelled", "ambiguous")),
        (1 * 1024, ("unlabelled", "ambiguous", "no_animal")),
    ],
)
def test_eviction_runs_unlabelled_then_ambiguous_then_no_animal(tmp_path, cap, gone):
    """The sequence, not just the set - each rank is exhausted before the next.

    Asserting only which files survive a full sweep cannot tell this order
    from its reverse, and the reverse spends the scarce records first. So
    the cap is tightened one record at a time and the order is read off.
    """
    planted = {
        bucket: _plant(tmp_path, bucket, "r.json")
        for bucket in ("unlabelled", "ambiguous", "no_animal", "elephant")
    }
    writer = sd.SeismicDatasetWriter(root=tmp_path, max_bytes=cap)

    assert writer.enforce_cap() == len(gone)
    for bucket, path in planted.items():
        assert path.exists() is (bucket not in gone)


def test_age_only_breaks_ties_inside_one_rank(tmp_path):
    """Within a bucket the oldest goes first - across buckets age is ignored."""
    oldest = _plant(tmp_path, "unlabelled", "old.json", mtime=1000)
    newest = _plant(tmp_path, "unlabelled", "new.json", mtime=9000)
    writer = sd.SeismicDatasetWriter(root=tmp_path, max_bytes=1024)
    assert writer.enforce_cap() == 1
    assert not oldest.exists()
    assert newest.exists()


def test_a_corpus_under_the_cap_is_left_alone(tmp_path):
    """Housekeeping that deletes anything it did not have to is a bug."""
    _plant(tmp_path, "elephant", "a.json", size=10)
    writer = sd.SeismicDatasetWriter(root=tmp_path, max_bytes=1024)
    assert writer.enforce_cap() == 0
    assert len(list(tmp_path.rglob("*.json"))) == 1


def test_enforce_cap_on_a_directory_that_does_not_exist_yet(tmp_path):
    """The first write creates the tree; the cap runs before that on a fresh node."""
    writer = sd.SeismicDatasetWriter(root=tmp_path / "never_created", max_bytes=0)
    assert writer.enforce_cap() == 0


def test_writing_over_the_cap_evicts_in_the_same_call(tmp_path):
    """End to end: the cap is enforced by the writer, not by a separate sweep."""
    victim = _plant(tmp_path, "unlabelled", "old.json", size=4096, mtime=1000)
    writer = sd.SeismicDatasetWriter(root=tmp_path, max_bytes=2048)
    kept = writer.write(_record(bucket="elephant"))
    assert not victim.exists()
    assert kept is not None and kept.exists()


# ---------------------------------------------------------------------------
# Startup cleanup
# ---------------------------------------------------------------------------


def test_clear_part_files_removes_only_partial_writes(tmp_path):
    """A .part file is a brown-out caught mid-write - incomplete by definition."""
    good = _plant(tmp_path, "elephant", "a.json")
    partial = _plant(tmp_path, "elephant", "b.json.part")
    assert sd.clear_part_files(tmp_path) == 1
    assert good.exists()
    assert not partial.exists()


def test_clear_part_files_on_a_missing_directory_is_a_no_op(tmp_path):
    """Called at process start, before the first event has created anything."""
    assert sd.clear_part_files(tmp_path / "absent") == 0


# -- derived fields (schema 2) ----------------------------------------------


def _box(label="Elephant", height=120, confidence=0.9):
    """A box well clear of every frame edge, so it is rangeable."""
    return sd.TrackBox(
        label=label,
        confidence=confidence,
        x=config.CAMERA_FRAME_WIDTH // 2 - 60,
        y=(config.CAMERA_FRAME_HEIGHT - height) // 2,
        width=120,
        height=height,
    )


def _approach(frames=8, label="Elephant", t0=100.0):
    """A track whose box heights grow - an animal walking in."""
    return tuple(
        sd.TrackFrame(poll=i, frame_index=i, timestamp_s=t0 + i, sample_index=i * 250,
                      boxes=(_box(label, 60 + 12 * i),))
        for i in range(frames)
    )


def _footfalls(duration_s=10.0, interval_s=0.8):
    """Quiet ground with a damped impulse every `interval_s`."""
    rng = random.Random(4242)
    counts = [int(rng.gauss(0, 3)) for _ in range(int(duration_s * 250))]
    t = 0.5
    while t < duration_s - 0.3:
        start = int(t * 250)
        for i in range(40):
            counts[start + i] += int(600 * math.exp(-i / 8.0) * math.sin(i * 0.9))
        t += interval_s
    return counts


def test_the_schema_bump_is_declared():
    """Derived fields changed the file format, so readers must be able to tell."""
    assert sd.SCHEMA == 2


def test_derived_ranges_appear_for_every_species_the_camera_drew():
    """A boar in frame during an elephant encounter is real data.

    Ranges are per label present in the track, not per confirmed species -
    the confirmation decides the bucket, not what was measurable.
    """
    track = tuple(
        sd.TrackFrame(poll=i, frame_index=i, timestamp_s=100.0 + i, sample_index=None,
                      boxes=(_box("Elephant", 60 + 12 * i), _box("Boar", 50)))
        for i in range(6)
    )
    derived = sd.with_derived(_record(track=track, species_seen=("Elephant",))).to_dict()
    labels = [r["label"] for r in derived["derived"]["ranges"]]
    assert labels == ["Boar", "Elephant"]


def test_an_unregistered_label_is_not_ranged():
    """Cattle have no body plan, and a made-up one would poison the corpus."""
    track = (sd.TrackFrame(0, 0, 100.0, None, (_box("Cattle", 200),)),)
    derived = sd.with_derived(_record(track=track)).to_dict()["derived"]
    assert derived["ranges"] == []


def test_the_derived_trajectory_says_which_way_it_was_going():
    """The reading D8 and the corpus both rest on."""
    record = sd.with_derived(_record(track=_approach(), species_seen=("Elephant",)))
    (elephant,) = record.to_dict()["derived"]["ranges"]
    assert elephant["direction"] == kinematics.APPROACHING
    assert elephant["relative_range"] < 1.0
    assert elephant["range_band"] in ("near", "mid", "far")
    assert len(elephant["samples"]) == 8


def test_each_derived_range_keeps_the_box_height_it_came_from():
    """The height is the measurement; the metres are an interpretation.

    Storing only the interpretation would make a later recalibration a
    guess rather than a recomputation.
    """
    record = sd.with_derived(_record(track=_approach()))
    sample = record.to_dict()["derived"]["ranges"][0]["samples"][0]
    assert sample["height_px"] == 60.0
    assert sample["range_m"] > 0


def test_derived_gait_reports_the_impact_train():
    """The cadence a future seismic model is meant to learn to hear."""
    record = sd.with_derived(_record(seismic=_slice(_footfalls(), first=0)))
    gait = record.to_dict()["derived"]["gait"]
    assert gait["impact_count"] == 12
    assert gait["cadence_hz"] == pytest.approx(1.25, rel=0.02)
    assert len(gait["impacts"]) == 12


def test_gait_analysis_is_cut_at_the_first_actuator():
    """The derived gait stops where the horn starts.

    Every elephant/ clip containing horn energy and no no_animal/ one is
    how a model learns to detect its own horn.
    """
    counts = _footfalls(12.0)
    fire = sd.ActuatorSpan("horn", 108.0, 111.8, start_index=8 * 250, count=950)
    record = sd.with_derived(_record(seismic=_slice(counts, first=0), actuators=(fire,)))
    gait = record.to_dict()["derived"]["gait"]
    assert gait["analysed_count"] == 8 * 250
    assert gait["excluded_actuator_samples"] == len(counts) - 8 * 250
    assert all(i["offset"] < 8 * 250 for i in gait["impacts"])


def test_a_record_with_no_waveform_still_derives_its_vision_half():
    """An acoustic-initiated event has boxes and no ground motion."""
    derived = sd.with_derived(
        _record(seismic=None, track=_approach(), species_seen=("Elephant",))
    ).to_dict()["derived"]
    assert derived["gait"] is None
    assert derived["ranges"]
    assert derived["behaviour"]["source"] == "vision_only"


def test_behaviour_is_only_derived_for_an_unambiguous_watch():
    """Two species confirmed means no behaviour state.

    With two animals there is nothing for "was it walking" to be about,
    and picking one is how a corpus acquires wrong labels that look right.
    """
    track = _approach()
    one = sd.with_derived(_record(track=track, species_seen=("Elephant",)))
    two = sd.with_derived(
        _record(bucket=sd.AMBIGUOUS_BUCKET, track=track, species_seen=("Elephant", "Boar"))
    )
    assert one.to_dict()["derived"]["behaviour"] is not None
    assert two.to_dict()["derived"]["behaviour"] is None
    assert two.to_dict()["derived"]["ranges"]  # the measurements survive


def test_the_retreat_verdict_is_only_derived_once_something_fired():
    """"Did it leave" is a question about a deterrent, not about a watch."""
    quiet = sd.with_derived(_record(track=_approach(), species_seen=("Elephant",)))
    assert quiet.to_dict()["derived"]["retreat"] is None
    # And the rest of the record derived normally. Without this the test
    # cannot tell "no deterrent fired, so no verdict" from "deriving the
    # verdict blew up and the whole annotation pass was abandoned".
    assert quiet.to_dict()["derived"]["behaviour"] is not None
    assert quiet.to_dict()["derived"]["ranges"]

    fire = sd.ActuatorSpan("horn", 100.0, 103.8, start_index=None, count=0)
    fired = sd.with_derived(
        _record(track=_approach(), species_seen=("Elephant",), actuators=(fire,))
    )
    assert fired.to_dict()["derived"]["retreat"]["retreated"] is False


def test_an_undetermined_retreat_is_stored_as_null_not_false():
    """Undetermined stays undetermined on disk.

    A null that round-trips as a false would escalate an alert and send a
    human into a forest on no evidence.
    """
    fire = sd.ActuatorSpan("horn", 500.0, 503.8, start_index=None, count=0)
    record = sd.with_derived(
        _record(track=_approach(), species_seen=("Elephant",), actuators=(fire,))
    )
    payload = json.loads(json.dumps(record.to_dict()))
    assert payload["derived"]["retreat"]["retreated"] is None
    assert payload["derived"]["retreat"]["reason"] == "no_track"


def test_with_derived_is_idempotent():
    """The export script re-runs it; running it twice must change nothing."""
    once = sd.with_derived(_record(track=_approach(), species_seen=("Elephant",)))
    twice = sd.with_derived(once)
    assert twice.to_dict() == once.to_dict()


def test_derivation_failure_leaves_the_raw_halves_intact(monkeypatch, caplog):
    """An annotation pass must never cost the measurements it annotates."""

    def boom(*_args, **_kwargs):
        raise RuntimeError("nope")

    monkeypatch.setattr(kinematics, "range_tracks", boom)
    record = _record(track=_approach())
    with caplog.at_level("WARNING"):
        out = sd.with_derived(record)
    assert out is record
    assert out.to_dict()["vision"]["track"]
    assert "cannot derive" in caplog.text


def test_the_writer_derives_on_the_way_to_disk(tmp_path):
    """Derivation happens in the writer, so no caller can forget it.

    The reflex loop builds the raw record; the derived half is this
    module's job.
    """
    writer = sd.SeismicDatasetWriter(root=tmp_path)
    path = writer.write(_record(track=_approach(), species_seen=("Elephant",)))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["derived"]["ranges"][0]["direction"] == kinematics.APPROACHING
    assert data["derived"]["behaviour"]["direction"] == kinematics.APPROACHING


def test_an_uncalibrated_node_stamps_every_record(tmp_path):
    """So a corpus mixing calibrated and nominal ranges can be separated."""
    writer = sd.SeismicDatasetWriter(root=tmp_path)
    data = json.loads(writer.write(_record(track=_approach())).read_text(encoding="utf-8"))
    assert data["label"]["calibrated"] is False


def test_a_calibrated_writer_marks_its_records(tmp_path):
    """And the ranges move, which is the point of calibrating."""
    optics = kinematics.Optics(focal_length_px=1000.0, calibrated=True, source="test")
    writer = sd.SeismicDatasetWriter(root=tmp_path, optics=optics)
    data = json.loads(
        writer.write(_record(track=_approach())).read_text(encoding="utf-8")
    )
    assert data["label"]["calibrated"] is True
    nominal = sd.with_derived(_record(track=_approach()))
    assert data["derived"]["ranges"][0]["samples"][0]["range_m"] > (
        nominal.to_dict()["derived"]["ranges"][0]["samples"][0]["range_m"]
    )
