"""Host-only tests for perception/camera.py - no cv2, no camera attached.

Exercises Camera entirely through a fake capture_factory (_FakeCapture
below), which is the one injection seam camera.py exposes and exists for
exactly this reason (see Camera.__init__'s docstring). Nothing here imports
cv2, matching device/mpu/README.md's "importable with no board attached"
property.
"""

import pytest

from perception import camera as camera_module
from perception.camera import Camera, CameraError, fourcc_to_int
from services import config as services_config


class _FakeCapture:
    """Stand-in for cv2.VideoCapture, scripted via a list of read() results.

    Args:
        frames: Sequence of (ok, image) tuples returned by successive
            read() calls, one per call, in order. Once exhausted, read()
            keeps returning (False, None) - mirrors a device that has
            stopped delivering frames rather than raising.
        opened: What isOpened() reports.
        reported_width/height/fourcc/fps: What get() reports for the
            corresponding property id, independent of what set() was
            called with - lets tests assert Camera.info reflects the
            device's negotiated values, not the requested ones.
    """

    def __init__(
        self,
        frames,
        opened=True,
        reported_width=1920,
        reported_height=1080,
        reported_fourcc="MJPG",
        reported_fps=30.0,
        auto_exposure=3,
        exposure=156,
        ignore_exposure_writes=False,
        raise_on_set=None,
    ):
        self._frames = list(frames)
        self._opened = opened
        self._reported_width = reported_width
        self._reported_height = reported_height
        self._reported_fourcc_int = fourcc_to_int(reported_fourcc)
        self._reported_fps = reported_fps
        # auto_exposure/exposure default to this camera's real documented
        # defaults (UVC Aperture Priority Mode / exposure_time_absolute
        # 156) - see perception.camera's _UVC_EXPOSURE_MODE_* and
        # _CAP_PROP_* constants.
        self._auto_exposure = auto_exposure
        self._exposure = exposure
        # ignore_exposure_writes: set() records the call and reports
        # success but the underlying state does not move - models the
        # documented "a set() that reports success on a control the
        # device silently ignores" failure mode (Camera.lock_night_exposure's
        # own docstring), so lock_night_exposure()'s read-back check has
        # something real to catch.
        self._ignore_exposure_writes = ignore_exposure_writes
        # raise_on_set: {prop_id: Exception} - lets a test make exactly one
        # control write blow up without touching the others.
        self._raise_on_set = raise_on_set or {}
        self.set_calls = []
        self.released = False

    def isOpened(self):  # noqa: N802 (matches cv2's own naming)
        return self._opened

    def set(self, prop_id, value):
        self.set_calls.append((prop_id, value))
        if prop_id in self._raise_on_set:
            raise self._raise_on_set[prop_id]
        if self._ignore_exposure_writes and prop_id in (15, 21):
            return True
        if prop_id == 21:
            self._auto_exposure = value
        elif prop_id == 15:
            self._exposure = value
        return True

    def get(self, prop_id):
        # Matches the six hardcoded ids in perception.camera (3/4/5/6 plus
        # 15/21 for exposure control).
        return {
            3: self._reported_width,
            4: self._reported_height,
            5: self._reported_fps,
            6: self._reported_fourcc_int,
            15: self._exposure,
            21: self._auto_exposure,
        }[prop_id]

    def read(self):
        if not self._frames:
            return False, None
        return self._frames.pop(0)

    def release(self):
        self.released = True


def _factory(frames, **kwargs):
    """Build a capture_factory closure Camera can call with (device, w, h, fourcc)."""
    capture = _FakeCapture(frames, **kwargs)

    def factory(device, width, height, fourcc):
        return capture

    factory.capture = capture  # expose for assertions
    return factory


# ---------------------------------------------------------------------------
# fourcc_to_int - pure, known-answer
# ---------------------------------------------------------------------------


def test_fourcc_to_int_known_value():
    """MJPG packs to the same little-endian int OpenCV's own macro produces."""
    assert fourcc_to_int("MJPG") == 0x47504A4D


@pytest.mark.parametrize("bad", ["", "MJ", "TOOLONG", "M"])
def test_fourcc_to_int_rejects_wrong_length(bad):
    """Anything other than exactly 4 characters raises ValueError."""
    with pytest.raises(ValueError, match="4 characters"):
        fourcc_to_int(bad)


# ---------------------------------------------------------------------------
# open()
# ---------------------------------------------------------------------------


def test_open_discards_exactly_warmup_frames():
    """open() grabs and discards warmup_frames frames before returning."""
    frames = [(True, f"warmup-{i}") for i in range(3)] + [(True, "first-real")]
    factory = _factory(frames)
    camera = Camera(warmup_frames=3, capture_factory=factory)

    camera.open()

    # All 3 warmup frames consumed; "first-real" remains for the next
    # capture_frame() call.
    assert len(factory.capture._frames) == 1
    assert factory.capture._frames[0] == (True, "first-real")


def test_open_raises_when_device_not_opened():
    """A device that never reports isOpened() raises CameraError, not a silent no-op."""
    factory = _factory(frames=[], opened=False)
    camera = Camera(warmup_frames=0, open_retries=1, capture_factory=factory)

    with pytest.raises(CameraError, match="failed to open"):
        camera.open()


def test_open_raises_when_warmup_grab_fails():
    """A failed grab during warmup raises and releases the handle, not a partial open."""
    factory = _factory(frames=[(True, "ok"), (False, None)])
    camera = Camera(warmup_frames=2, open_retries=1, capture_factory=factory)

    with pytest.raises(CameraError, match="failed during warmup"):
        camera.open()
    assert factory.capture.released, "a failed warmup must still release the handle"


# ---------------------------------------------------------------------------
# open() retry policy
# ---------------------------------------------------------------------------


def _stateful_factory(captures):
    """Build a capture_factory that returns a new capture object per call, in order.

    Unlike `_factory()` (one fixed capture reused for the whole test), this
    models a real retry: each open() attempt gets a fresh handle from a
    fresh cv2.VideoCapture() call, which is what `open_v4l2_capture` (and
    the real cv2.VideoCapture constructor) actually does.
    """
    captures = list(captures)
    calls = []

    def factory(device, width, height, fourcc):
        calls.append((device, width, height, fourcc))
        return captures.pop(0)

    factory.calls = calls
    return factory


def test_open_retries_and_succeeds_after_transient_failure():
    """A device that isn't opened yet on attempt 1 but is by attempt 2 still succeeds."""
    captures = [
        _FakeCapture(frames=[], opened=False),
        _FakeCapture(frames=[(True, "ok")]),
    ]
    factory = _stateful_factory(captures)
    camera = Camera(
        warmup_frames=1, open_retries=3, open_retry_backoff_s=0.0, capture_factory=factory
    )

    camera.open()

    assert len(factory.calls) == 2
    assert captures[0].released, "the failed first attempt's handle must be released"


def test_open_gives_up_after_exhausting_retries():
    """A device that never opens raises after exactly open_retries attempts, not fewer or more."""
    captures = [_FakeCapture(frames=[], opened=False) for _ in range(3)]
    factory = _stateful_factory(captures)
    camera = Camera(
        warmup_frames=0, open_retries=3, open_retry_backoff_s=0.0, capture_factory=factory
    )

    with pytest.raises(CameraError, match="failed to open"):
        camera.open()

    assert len(factory.calls) == 3
    assert all(c.released for c in captures)


def test_open_caches_negotiated_info_not_requested_values():
    """CameraInfo reflects what get() reports, not the constructor args."""
    factory = _factory(
        frames=[],
        reported_width=640,
        reported_height=480,
        reported_fourcc="YUYV",
        reported_fps=15.0,
    )
    camera = Camera(
        width=1920, height=1080, pixel_format="MJPG", warmup_frames=0, capture_factory=factory
    )

    camera.open()

    assert camera.info.width == 640
    assert camera.info.height == 480
    assert camera.info.fourcc == "YUYV"
    assert camera.info.fps == 15.0


def test_info_before_open_raises():
    """Reading .info before open() (or after close()) raises, not None."""
    camera = Camera(capture_factory=_factory(frames=[]))
    with pytest.raises(CameraError):
        _ = camera.info


# ---------------------------------------------------------------------------
# open() - _assert_auto_exposure()
# ---------------------------------------------------------------------------


def test_open_asserts_auto_exposure_mode():
    """open() forces UVC Aperture Priority Mode, guarding against stale device state.

    docs/qa/night-ir-led-characterisation.md and the 3 Sept 2026 live
    remediation it prompted: a previous opener can leave the device in
    Manual Mode at a stale exposure, and that state survives close()/
    release() and even a reboot because it lives on the device, not the
    file handle. open() must write the auto default on every call, not
    just the first.
    """
    factory = _factory(frames=[], auto_exposure=1, exposure=2000)  # stale Manual/2000
    camera = Camera(warmup_frames=0, capture_factory=factory)

    camera.open()

    assert (21, 3) in factory.capture.set_calls
    assert factory.capture._auto_exposure == 3


def test_open_still_succeeds_when_auto_exposure_assertion_fails():
    """A device that rejects the auto-exposure write still opens - never blocks capture."""
    factory = _factory(frames=[(True, "ok")], raise_on_set={21: RuntimeError("control busy")})
    camera = Camera(warmup_frames=0, capture_factory=factory)

    camera.open()  # must not raise

    assert camera.capture_frame() is not None


# ---------------------------------------------------------------------------
# capture_frame()
# ---------------------------------------------------------------------------


def test_capture_frame_returns_none_on_failed_grab_without_raising():
    """A failed grab returns None - the documented honest failure value, not an exception."""
    factory = _factory(frames=[(False, None)])
    camera = Camera(warmup_frames=0, capture_factory=factory)
    camera.open()

    assert camera.capture_frame() is None


def test_capture_frame_returns_frame_on_success():
    """A successful grab returns a Frame carrying the raw image and index 0."""
    factory = _factory(frames=[(True, "image-bytes")])
    camera = Camera(warmup_frames=0, capture_factory=factory)
    camera.open()

    frame = camera.capture_frame()

    assert frame is not None
    assert frame.image == "image-bytes"
    assert frame.index == 0


def test_capture_frame_before_open_raises():
    """Capturing before open() raises CameraError, not a crash on a None handle."""
    camera = Camera(capture_factory=_factory(frames=[]))
    with pytest.raises(CameraError, match="before open"):
        camera.capture_frame()


def test_capture_frame_after_close_raises():
    """Capturing after close() raises CameraError - close() really releases the handle."""
    factory = _factory(frames=[])
    camera = Camera(warmup_frames=0, capture_factory=factory)
    camera.open()
    camera.close()

    with pytest.raises(CameraError, match="after close"):
        camera.capture_frame()


# ---------------------------------------------------------------------------
# capture_burst()
# ---------------------------------------------------------------------------


def test_capture_burst_returns_count_frames_with_increasing_index_and_timestamps():
    """A full-length burst returns count frames, indexed in order, non-decreasing timestamps."""
    factory = _factory(frames=[(True, f"f{i}") for i in range(5)])
    camera = Camera(warmup_frames=0, capture_factory=factory)
    camera.open()

    frames = camera.capture_burst(count=5, interval_s=0.0)

    assert len(frames) == 5
    assert [f.index for f in frames] == [0, 1, 2, 3, 4]
    assert [f.image for f in frames] == ["f0", "f1", "f2", "f3", "f4"]
    timestamps = [f.timestamp_s for f in frames]
    assert timestamps == sorted(timestamps)


def test_capture_burst_stops_early_and_returns_short_list_on_mid_burst_failure():
    """A grab failure partway through a burst returns what was captured, not an exception."""
    factory = _factory(frames=[(True, "f0"), (True, "f1"), (False, None)])
    camera = Camera(warmup_frames=0, capture_factory=factory)
    camera.open()

    frames = camera.capture_burst(count=5, interval_s=0.0)

    assert len(frames) == 2
    assert [f.image for f in frames] == ["f0", "f1"]


def test_capture_burst_returns_empty_list_when_first_grab_fails():
    """A burst that fails on its first frame returns [], not an exception."""
    factory = _factory(frames=[(False, None)])
    camera = Camera(warmup_frames=0, capture_factory=factory)
    camera.open()

    assert camera.capture_burst(count=3, interval_s=0.0) == []


@pytest.mark.parametrize("count", [0, -1])
def test_capture_burst_rejects_non_positive_count(count):
    """Count < 1 raises ValueError before any grab is attempted."""
    camera = Camera(warmup_frames=0, capture_factory=_factory(frames=[]))
    camera.open()
    with pytest.raises(ValueError, match="count"):
        camera.capture_burst(count=count)


def test_capture_burst_rejects_negative_interval():
    """interval_s < 0 raises ValueError before any grab is attempted."""
    camera = Camera(warmup_frames=0, capture_factory=_factory(frames=[]))
    camera.open()
    with pytest.raises(ValueError, match="interval_s"):
        camera.capture_burst(count=1, interval_s=-0.1)


# ---------------------------------------------------------------------------
# lock_night_exposure()
# ---------------------------------------------------------------------------


def test_lock_night_exposure_succeeds_and_verifies_readback():
    """A device that honours the writes locks manual mode at the requested value."""
    factory = _factory(frames=[])
    camera = Camera(warmup_frames=0, capture_factory=factory)
    camera.open()

    assert camera.lock_night_exposure(256) is True

    assert factory.capture._auto_exposure == 1  # Manual Mode
    assert factory.capture._exposure == 256
    assert (21, 1) in factory.capture.set_calls
    assert (15, 256) in factory.capture.set_calls


def test_lock_night_exposure_defaults_to_the_configured_value():
    """No argument locks at services.config.NIGHT_LOCKED_EXPOSURE, not a hardcoded number."""
    factory = _factory(frames=[])
    camera = Camera(warmup_frames=0, capture_factory=factory)
    camera.open()

    assert camera.lock_night_exposure() is True

    assert factory.capture._exposure == services_config.NIGHT_LOCKED_EXPOSURE


def test_lock_night_exposure_returns_false_when_the_write_does_not_stick():
    """A set() that reports success but leaves the device unchanged reads back False.

    The documented failure mode this read-back check exists to catch (see
    Camera.lock_night_exposure's own docstring) - success must be verified,
    not assumed from set() returning True.
    """
    factory = _factory(frames=[], ignore_exposure_writes=True)
    camera = Camera(warmup_frames=0, capture_factory=factory)
    camera.open()

    assert camera.lock_night_exposure(256) is False
    # Real Camera behaviour on a rejected lock: continue on whatever the
    # camera already had, not raise and not retry.
    assert factory.capture._auto_exposure == 3  # unchanged from the open()-time default


def test_lock_night_exposure_returns_false_and_does_not_raise_on_a_control_error():
    """A control write that raises is swallowed - a camera fault must never block capture."""
    factory = _factory(frames=[(True, "ok")], raise_on_set={15: RuntimeError("device busy")})
    camera = Camera(warmup_frames=0, capture_factory=factory)
    camera.open()

    assert camera.lock_night_exposure(256) is False  # must not raise
    assert camera.capture_frame() is not None  # capture still works afterward


def test_lock_night_exposure_returns_false_when_disabled_via_config(monkeypatch):
    """The NIGHT_EXPOSURE_LOCK_ENABLED kill switch skips the write entirely, not just the effect."""
    monkeypatch.setattr(camera_module.config, "NIGHT_EXPOSURE_LOCK_ENABLED", False)
    factory = _factory(frames=[])
    camera = Camera(warmup_frames=0, capture_factory=factory)
    camera.open()
    calls_before = list(factory.capture.set_calls)

    assert camera.lock_night_exposure(256) is False

    # No new exposure-control writes past whatever open() itself already made.
    assert factory.capture.set_calls == calls_before


def test_lock_night_exposure_before_open_raises():
    """Locking before open() raises CameraError, same contract as every other method."""
    camera = Camera(capture_factory=_factory(frames=[]))
    with pytest.raises(CameraError, match="before open"):
        camera.lock_night_exposure()


def test_lock_night_exposure_after_close_raises():
    """Locking after close() raises CameraError - the handle is really gone."""
    camera = Camera(warmup_frames=0, capture_factory=_factory(frames=[]))
    camera.open()
    camera.close()

    with pytest.raises(CameraError, match="after close"):
        camera.lock_night_exposure()


# ---------------------------------------------------------------------------
# close()
# ---------------------------------------------------------------------------


def test_close_is_idempotent():
    """Calling close() twice releases once and raises neither time."""
    factory = _factory(frames=[])
    camera = Camera(warmup_frames=0, capture_factory=factory)
    camera.open()

    camera.close()
    camera.close()  # must not raise

    assert factory.capture.released


def test_close_without_open_does_not_raise():
    """close() on a never-opened Camera is a no-op, not an error."""
    camera = Camera(capture_factory=_factory(frames=[]))
    camera.close()  # no-op, never opened


def test_context_manager_opens_and_closes():
    """`with Camera(...) as cam:` opens on entry and releases on exit."""
    factory = _factory(frames=[(True, "f0")])
    with Camera(warmup_frames=0, capture_factory=factory) as camera:
        assert camera.capture_frame() is not None

    assert factory.capture.released
