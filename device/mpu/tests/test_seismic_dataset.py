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
import struct

import pytest

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
