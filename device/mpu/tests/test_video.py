"""Tests for perception/video.py's event recorder (ADR 0020).

No GStreamer, no camera, no numpy. Every test drives EventVideoRecorder
through its `pipeline_factory` seam with a fake handle, which is the same
arrangement tests/test_camera.py uses against Camera's `capture_factory`
and exists for the same reason: the keep/discard and burst logic is what
has to be right, and none of it needs a device.

What these tests deliberately cannot cover, stated plainly so nobody reads
a green suite as more than it is: whether the real element chain
negotiates on the QRB2210 - in particular whether `v4l2h264enc` exposes a
working hardware encoder - and whether the camera enumerates at all under
VIN power, which is the field topology. Both are open, both are recorded
in perception/video.py's own UNVERIFIED note and docs/KNOWN_GAPS.md, and
both are why services.config.EVENT_VIDEO_ENABLED ships False.

The fake pipeline writes bytes to the scratch path the description names,
because a real filesink would - commit/discard are meaningless against a
file that never exists.
"""

import re

import pytest

from perception.camera import CameraError
from perception.storage import CaptureEventTag
from perception.video import APPSINK_NAME, EventVideoRecorder, build_pipeline_description

TAG = CaptureEventTag(
    event_timestamp_s=1725000000.5,
    sta_lta_ratio=6.25,
    fused_probability=0.812,
    alert=True,
)


def _location_from(description: str) -> str:
    """Pull the filesink path back out of a pipeline description."""
    match = re.search(r"filesink location=(\S+)", description)
    assert match, f"no filesink location in: {description}"
    return match.group(1)


class _FakePipeline:
    """Stands in for a running GStreamer pipeline.

    `frames` is how many pulls succeed before every later pull returns None
    - which is how a real appsink reports "nothing arrived in time", not an
    exception.
    """

    def __init__(self, path, frames=100, stop_raises=None):
        self.path = path
        self.remaining = frames
        self.stop_raises = stop_raises
        self.pulls = 0
        self.stopped = 0
        # A real filesink creates the file as soon as the pipeline plays.
        path.write_bytes(b"")

    def pull_frame(self, timeout_s):
        self.pulls += 1
        if self.remaining <= 0:
            return None
        self.remaining -= 1
        return [self.pulls]

    def stop(self, timeout_s):
        self.stopped += 1
        if self.stop_raises is not None:
            raise self.stop_raises
        # A real encoder has written the muxed clip out by now.
        self.path.write_bytes(b"fake matroska bytes")


class _FakeFactory:
    """Records what the recorder asked for, and hands back a _FakePipeline."""

    def __init__(self, frames=100, raises=None, stop_raises=None):
        self.frames = frames
        self.raises = raises
        self.stop_raises = stop_raises
        self.calls = []
        self.pipelines = []

    def __call__(self, description, appsink_name, startup_timeout_s):
        self.calls.append((description, appsink_name, startup_timeout_s))
        if self.raises is not None:
            raise self.raises
        from pathlib import Path

        pipeline = _FakePipeline(
            Path(_location_from(description)), self.frames, self.stop_raises
        )
        self.pipelines.append(pipeline)
        return pipeline


def _recorder(tmp_path, factory=None, **kwargs):
    """An EventVideoRecorder pointed entirely at tmp_path."""
    return EventVideoRecorder(
        scratch_dir=tmp_path / "captures" / ".scratch",
        capture_dir=tmp_path / "captures",
        pipeline_factory=factory if factory is not None else _FakeFactory(),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# build_pipeline_description
# ---------------------------------------------------------------------------


def test_description_tees_the_stream_to_both_an_encoder_and_an_appsink(tmp_path):
    """The whole design in one assertion: one camera, two consumers.

    A single V4L2 device cannot be opened twice, so the recording branch
    and the vision-check branch have to come off one tee. If either branch
    ever went missing this would still parse and still run - it would just
    silently stop producing either the file or the frames - so the shape
    is asserted here rather than left to a live run to discover.
    """
    description = build_pipeline_description(
        "/dev/video0", tmp_path / "e.mkv", width=1280, height=720, framerate=15,
        bitrate_bps=2_000_000,
    )

    assert description.count("tee name=") == 1
    assert description.count("etx_tee.") == 2
    assert "v4l2h264enc" in description
    assert f"appsink name={APPSINK_NAME}" in description


def test_description_muxes_to_matroska_not_mp4(tmp_path):
    """Container choice is a survivability decision, not a preference.

    MP4 writes its moov atom at close, so a brown-out mid-record leaves a
    file no player will open. Matroska stays playable up to the point the
    power went. On a board with a documented 5V brown-out history
    (docs/KNOWN_GAPS.md) that is the difference between footage and
    nothing.
    """
    description = build_pipeline_description(
        "/dev/video0", tmp_path / "e.mkv", width=1280, height=720, framerate=15,
        bitrate_bps=2_000_000,
    )

    assert "matroskamux" in description
    assert "mp4mux" not in description


def test_description_carries_the_configured_geometry_and_bitrate(tmp_path):
    """Config values must reach the pipeline, not just sit in the module."""
    description = build_pipeline_description(
        "/dev/video0", tmp_path / "e.mkv", width=640, height=480, framerate=10,
        bitrate_bps=750_000,
    )

    assert "width=640,height=480,framerate=10/1" in description
    assert "video_bitrate=750000" in description
    assert _location_from(description).endswith("e.mkv")


def test_appsink_branch_drops_frames_rather_than_stalling_the_encoder(tmp_path):
    """A slow vision check must never back-pressure the recording.

    The appsink branch feeds an HTTP inference call that can take up to
    VISION_INFERENCE_TIMEOUT_S. Without leaky queues and drop=true, that
    latency propagates back through the tee and stalls the encoder - the
    recording is the thing that must not be starved.
    """
    description = build_pipeline_description(
        "/dev/video0", tmp_path / "e.mkv", width=1280, height=720, framerate=15,
        bitrate_bps=2_000_000,
    )

    assert description.count("leaky=downstream") == 2
    assert "drop=true" in description


# ---------------------------------------------------------------------------
# open()
# ---------------------------------------------------------------------------


def test_construction_touches_nothing(tmp_path):
    """__init__ must do no I/O - main.py builds this at module scope.

    Same discipline as perception.camera.Camera: constructed before the
    Bridge or the hardware is confirmed ready, so it cannot assume a
    device, a directory, or a filesystem.
    """
    factory = _FakeFactory()
    recorder = _recorder(tmp_path, factory)

    assert factory.calls == []
    assert not (tmp_path / "captures").exists()
    assert recorder.recording is False


def test_open_starts_recording_and_pulls_warmup_frames(tmp_path):
    """Recording begins at open(), before anything is known about the event.

    That ordering is ADR 0020's actual mechanism - the clip covers the
    approach because it started at the trigger, not because anything is
    buffering continuously.
    """
    factory = _FakeFactory()
    recorder = _recorder(tmp_path, factory, warmup_frames=3)

    recorder.open()

    assert recorder.recording is True
    assert len(factory.calls) == 1
    description, appsink_name, _ = factory.calls[0]
    assert appsink_name == APPSINK_NAME
    scratch = tmp_path / "captures" / ".scratch"
    assert _location_from(description).startswith(scratch.as_posix())
    assert factory.pipelines[0].pulls == 3


def test_open_twice_without_a_close_is_refused(tmp_path):
    """Two overlapping opens would leak the first recording's scratch file."""
    recorder = _recorder(tmp_path)
    recorder.open()

    with pytest.raises(CameraError):
        recorder.open()


def test_open_that_cannot_start_the_pipeline_raises_camera_error(tmp_path):
    """Failure type matters more than the message here.

    services/reflex_loop.py catches CameraError around open() and degrades
    to "no camera this event", which lets the deterrence sequence run
    anyway. A different exception type would escape that handler and take
    the horn down with the camera - so the recorder raises the error type
    the loop already knows, rather than one of its own.
    """
    factory = _FakeFactory(raises=CameraError("no such element v4l2h264enc"))
    recorder = _recorder(tmp_path, factory)

    with pytest.raises(CameraError):
        recorder.open()
    assert recorder.recording is False


def test_open_abandons_and_cleans_up_when_warmup_produces_no_frames(tmp_path):
    """A pipeline that plays but yields nothing must leave no scratch file.

    Otherwise every failed event would deposit an orphan that only the
    next process start would clear - and a camera that is failing tends to
    fail repeatedly.
    """
    factory = _FakeFactory(frames=0)
    recorder = _recorder(tmp_path, factory, warmup_frames=2)

    with pytest.raises(CameraError):
        recorder.open()

    assert recorder.recording is False
    assert recorder.pending_path is None
    assert factory.pipelines[0].stopped == 1
    assert list((tmp_path / "captures" / ".scratch").iterdir()) == []


def test_open_raises_camera_error_when_the_scratch_dir_cannot_be_made(tmp_path):
    """The one raising function in perception/storage.py, translated into the loop's error type."""
    blocker = tmp_path / "blocked"
    blocker.write_bytes(b"")
    recorder = EventVideoRecorder(
        scratch_dir=blocker / "scratch",
        capture_dir=tmp_path / "captures",
        pipeline_factory=_FakeFactory(),
    )

    with pytest.raises(CameraError):
        recorder.open()


# ---------------------------------------------------------------------------
# capture_frame / capture_burst - the CameraProtocol contract
# ---------------------------------------------------------------------------


def test_capture_before_open_raises(tmp_path):
    """Using a closed recorder is a programming error, not a device failure."""
    recorder = _recorder(tmp_path)

    with pytest.raises(CameraError):
        recorder.capture_frame()
    with pytest.raises(CameraError):
        recorder.capture_burst(1)


def test_capture_frame_returns_none_when_no_frame_arrives(tmp_path):
    """A missed frame is None, never a raise and never a filler image.

    Identical to perception.camera.Camera.capture_frame()'s contract, and
    for the identical reason: a black filler frame is indistinguishable
    from a legitimate dark night frame, so None is the only truthful
    failure value.
    """
    recorder = _recorder(tmp_path, _FakeFactory(frames=0), warmup_frames=0)
    recorder.open()

    assert recorder.capture_frame() is None


def test_burst_indexes_frames_in_capture_order(tmp_path):
    """Downstream code sorts and names by index - it must start at 0 and step by 1."""
    recorder = _recorder(tmp_path, _FakeFactory(), warmup_frames=0)
    recorder.open()

    frames = recorder.capture_burst(4, 0.0)

    assert [f.index for f in frames] == [0, 1, 2, 3]
    assert all(f.timestamp_s > 0 for f in frames)


def test_burst_stops_early_and_returns_what_it_got(tmp_path):
    """A short burst is evidence, not a failure - the recording is unaffected.

    The reflex loop feeds whatever comes back to the vision check and
    carries on; losing two of five frames must not cost the event.
    """
    recorder = _recorder(tmp_path, _FakeFactory(frames=2), warmup_frames=0)
    recorder.open()

    frames = recorder.capture_burst(5, 0.0)

    assert len(frames) == 2
    assert recorder.recording is True


def test_burst_rejects_impossible_arguments(tmp_path):
    """Same ValueError guards as Camera.capture_burst, so the seam stays swappable."""
    recorder = _recorder(tmp_path, _FakeFactory(), warmup_frames=0)
    recorder.open()

    with pytest.raises(ValueError):
        recorder.capture_burst(0)
    with pytest.raises(ValueError):
        recorder.capture_burst(3, -0.1)


# ---------------------------------------------------------------------------
# close()
# ---------------------------------------------------------------------------


def test_close_is_idempotent_and_leaves_the_recording_undecided(tmp_path):
    """close() finishes the file; it must never imply keep or discard.

    The reflex loop closes the camera on paths that then commit and on
    paths that then discard, so close() deciding anything would make one
    of those two wrong.
    """
    factory = _FakeFactory()
    recorder = _recorder(tmp_path, factory, warmup_frames=0)
    recorder.open()

    recorder.close()
    recorder.close()

    assert recorder.recording is False
    assert factory.pipelines[0].stopped == 1
    assert recorder.pending_path is not None
    assert recorder.pending_path.exists()


def test_close_never_raises_when_teardown_fails(tmp_path):
    """The loop has already fired its actuators - teardown must not crash it."""
    factory = _FakeFactory(stop_raises=RuntimeError("EOS never arrived"))
    recorder = _recorder(tmp_path, factory, warmup_frames=0)
    recorder.open()

    recorder.close()

    assert recorder.recording is False


# ---------------------------------------------------------------------------
# commit() / discard()
# ---------------------------------------------------------------------------


def test_commit_moves_the_finished_recording_into_the_capture_dir(tmp_path):
    """The keep half of the gate, end to end through the real storage layer."""
    recorder = _recorder(tmp_path, _FakeFactory(), warmup_frames=0)
    recorder.open()
    recorder.close()

    committed = recorder.commit(TAG)

    assert committed is not None
    assert committed.parent == tmp_path / "captures"
    assert committed.name.endswith("_alert1.mkv")
    assert list((tmp_path / "captures" / ".scratch").iterdir()) == []


def test_commit_closes_a_still_running_pipeline_first(tmp_path):
    """Committing mid-record would file a truncated, unfinished clip."""
    factory = _FakeFactory()
    recorder = _recorder(tmp_path, factory, warmup_frames=0)
    recorder.open()

    committed = recorder.commit(TAG)

    assert factory.pipelines[0].stopped == 1
    assert committed is not None
    assert committed.read_bytes() == b"fake matroska bytes"


def test_discard_removes_the_recording_and_files_nothing(tmp_path):
    """The common case: a trigger that was neither confirmed nor alerted."""
    recorder = _recorder(tmp_path, _FakeFactory(), warmup_frames=0)
    recorder.open()
    recorder.close()

    recorder.discard()

    assert list((tmp_path / "captures" / ".scratch").iterdir()) == []
    assert not (tmp_path / "captures").exists() or [
        p for p in (tmp_path / "captures").iterdir() if p.is_file()
    ] == []


def test_commit_and_discard_are_safe_with_nothing_recorded(tmp_path):
    """Both are reachable on an event whose open() failed.

    services/reflex_loop.py calls exactly one of them at every exit,
    including exits reached because the camera never opened - so "nothing
    to do" has to be an ordinary return, not an error.
    """
    recorder = _recorder(tmp_path)

    assert recorder.commit(TAG) is None
    recorder.discard()


def test_a_second_commit_after_a_decision_does_nothing(tmp_path):
    """One recording, one decision - a repeat call must not re-file anything."""
    recorder = _recorder(tmp_path, _FakeFactory(), warmup_frames=0)
    recorder.open()
    recorder.close()

    assert recorder.commit(TAG) is not None
    assert recorder.commit(TAG) is None


def test_commit_never_raises_when_storage_fails(tmp_path, monkeypatch):
    """Evidence housekeeping must never cost the next event.

    perception/storage.py is written not to raise, so anything arriving
    here is unanticipated - which is exactly the case that must not
    propagate into a handler running on a field node nobody can reach.
    """
    import perception.video as video

    recorder = _recorder(tmp_path, _FakeFactory(), warmup_frames=0)
    recorder.open()
    recorder.close()
    monkeypatch.setattr(
        video.storage, "commit_video", lambda *a, **k: (_ for _ in ()).throw(OSError("disk gone"))
    )

    assert recorder.commit(TAG) is None


def test_discard_never_raises_when_storage_fails(tmp_path, monkeypatch):
    """Same contract as commit, on the branch that runs far more often."""
    import perception.video as video

    recorder = _recorder(tmp_path, _FakeFactory(), warmup_frames=0)
    recorder.open()
    recorder.close()
    monkeypatch.setattr(
        video.storage, "discard_video", lambda *a, **k: (_ for _ in ()).throw(OSError("read-only"))
    )

    recorder.discard()


def test_context_manager_stops_recording_without_deciding(tmp_path):
    """__exit__ closes, and deliberately neither commits nor discards.

    Silently discarding on the way out of a `with` block would throw away
    a confirmed event's footage on any exception - the decision belongs to
    the event, not to the block.
    """
    factory = _FakeFactory()
    recorder = _recorder(tmp_path, factory, warmup_frames=0)

    with recorder:
        assert recorder.recording is True

    assert recorder.recording is False
    assert recorder.pending_path is not None
    assert recorder.pending_path.exists()
