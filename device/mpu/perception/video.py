"""Trigger-gated event video recorder (ADR 0020).

One object, two jobs, because one USB camera cannot be opened twice. ADR
0020 wants a real H.264 recording of the whole encounter *and* live frames
for the vision check that decides whether to keep that recording - and
`v4l2src` and `cv2.VideoCapture` cannot both hold
`/dev/v4l/by-id/usb-Arducam_...` at the same time. So this module owns the
device for the duration of an event and serves both needs off one GStreamer
pipeline: a `tee` after the MJPEG decode feeds an H.264 encoder writing to a
scratch file on one branch, and an `appsink` handing BGR frames to
services/reflex_loop.py's existing vision check on the other.

`EventVideoRecorder` therefore satisfies services.reflex_loop.CameraProtocol
(open / capture_burst / close) exactly as perception.camera.Camera does, and
adds two methods that camera has no equivalent of - `commit()` and
`discard()`. device/mpu/main.py passes the same instance to both the
`camera=` and `event_video=` parameters of handle_footfall_event(); the
reflex loop never learns that they are one object, and its camera handling is
completely unchanged.

**This is not a rolling pre-event buffer, and there is no way to make it
one.** ADR 0020 rejects a continuous always-on capture path outright: it
needs the camera and encoder powered permanently, several watts sustained,
against a solar/battery budget that ADR 0008's 2 Sept addendum shows is
already over-committed at idle. Nothing here runs until a qualifying MCU
trigger calls `open()`, and `close()` releases the device at the end of the
event. A future pre-buffer would be a separate, power-budget-aware decision
(ADR 0020 Decision D), not a quiet extension of this module.

Failure discipline, inherited deliberately rather than reinvented: this
module raises perception.camera.CameraError - not an error type of its own -
for every device fault. services/reflex_loop.py's `_open_camera` and
`_capture_burst` catch exactly that type and degrade to "no footage this
event" without ever delaying an actuator; a parallel exception class here
would slip straight past those handlers and let a camera fault take down the
deterrence path, which is the one thing that must never happen. The
commit/discard side goes further and raises nothing at all - by the time it
runs, the horn has already fired.

Importability, same discipline as perception/camera.py: `gi` (PyGObject) and
`numpy` are imported only inside `launch_gst_pipeline` and the pipeline
handle it returns, never at module scope, so this file imports fine on a dev
laptop with no GStreamer, no PyGObject and no camera (device/mpu/README.md's
host-test harness). Every test in tests/test_video.py injects a fake
pipeline factory through the same seam perception/camera.py's
`capture_factory` provides.

**UNVERIFIED against real hardware, and that is why
services/config.py's EVENT_VIDEO_ENABLED defaults to False.** GStreamer
itself is confirmed present on the board (docs/KNOWN_GAPS.md, 28 Aug:
`gstreamer1.0-tools`, `-plugins-good`, `-base`, `-libcamera`, already
driving the Edge Impulse runner's live camera path), but the specific
element chain below - and in particular whether `v4l2h264enc` exposes the
QRB2210's Venus encoder to userspace here - has never been run. Neither has
the camera itself been proven to enumerate under the field build's VIN power
topology (docs/KNOWN_GAPS.md flags that as blocking the entire camera path).
Both are cheap live checks with the board in front of a human; neither has
been done, and nothing in this module should be read as evidence that it
works until they are.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Protocol

from perception import storage
from perception.camera import CameraError, Frame
from services import config

logger = logging.getLogger(__name__)

# Name given to the appsink element inside the pipeline description, used to
# look it up again on the built pipeline. Arbitrary but fixed - the lookup
# and the description have to agree, so it lives here rather than being
# spelled twice.
APPSINK_NAME = "etx_frames"

# The tee's element name, same reasoning: gst-launch syntax refers back to it
# by name to open the second branch.
_TEE_NAME = "etx_tee"


class PipelineHandle(Protocol):
    """The subset of a running GStreamer pipeline `EventVideoRecorder` uses.

    Exists so tests can supply a fake with no `gi` import at all - the same
    reason perception.camera._CaptureHandle exists for cv2.VideoCapture.
    """

    def pull_frame(self, timeout_s: float) -> Any | None:
        """Return the next BGR frame from the appsink branch, or None on timeout."""
        ...

    def stop(self, timeout_s: float) -> None:
        """Send end-of-stream, wait for the file to finish, and tear the pipeline down."""
        ...


def build_pipeline_description(
    device: str,
    scratch_path: Path,
    width: int = config.EVENT_VIDEO_WIDTH,
    height: int = config.EVENT_VIDEO_HEIGHT,
    framerate: int = config.EVENT_VIDEO_FRAMERATE,
    bitrate_bps: int = config.EVENT_VIDEO_BITRATE_BPS,
) -> str:
    """Build the gst-launch description for one event recording.

    A pure string builder, deliberately separated from anything that runs
    it, so the pipeline's shape is assertable in a host test with no
    GStreamer installed (tests/test_video.py) rather than only discoverable
    on the board.

    Shape, and why each part is there:

    - `v4l2src ! image/jpeg,...` - the camera is requested in MJPG for the
      same bandwidth reason services/config.py's CAMERA_PIXEL_FORMAT gives:
      a 1080p-class UVC sensor will not sustain a useful frame rate in
      uncompressed YUYV over USB2.
    - `jpegparse ! jpegdec` - decoded once, before the tee, so the two
      branches share the cost instead of each decoding the same frames.
      Software decode is a real CPU cost on four A53s, which is why
      EVENT_VIDEO_WIDTH/HEIGHT/FRAMERATE are set below the stills
      resolution.
    - `tee` - branch one encodes and writes the file; branch two hands BGR
      frames to the vision check. Both queues are `leaky=downstream`: if the
      reflex loop is slow to pull a frame, the pipeline must drop that frame
      and keep recording, never stall the encoder and corrupt the timeline.
    - `matroskamux` - not MP4, see services/config.py's EVENT_VIDEO_SUFFIX:
      a recording cut short by a brown-out stays playable.
    - `filesink sync=false` - write as fast as the encoder produces; there
      is no live playback to pace against.

    Args:
        device: V4L2 device path, normally services.config.CAMERA_DEVICE.
        scratch_path: Where the recording is written while undecided.
        width: Recording width requested from the camera.
        height: Recording height requested from the camera.
        framerate: Frames per second requested from the camera.
        bitrate_bps: H.264 target bitrate handed to the encoder.

    Returns:
        A description string suitable for `Gst.parse_launch`.
    """
    return (
        f"v4l2src device={device} io-mode=2"
        f" ! image/jpeg,width={width},height={height},framerate={framerate}/1"
        f" ! jpegparse ! jpegdec"
        f" ! tee name={_TEE_NAME}"
        f" {_TEE_NAME}. ! queue max-size-buffers=8 leaky=downstream"
        f" ! videoconvert ! video/x-raw,format=NV12"
        f' ! v4l2h264enc extra-controls="controls,video_bitrate={bitrate_bps}"'
        f" ! h264parse ! matroskamux"
        f" ! filesink location={scratch_path.as_posix()} sync=false"
        f" {_TEE_NAME}. ! queue max-size-buffers=2 leaky=downstream"
        f" ! videoconvert ! video/x-raw,format=BGR"
        f" ! appsink name={APPSINK_NAME} emit-signals=false sync=false"
        f" max-buffers=2 drop=true"
    )


class _GstPipeline:
    """PipelineHandle over a real `Gst.Pipeline`; constructed only by launch_gst_pipeline.

    Holds the `Gst` module and the `numpy` module it was handed rather than
    importing them itself, so the function-local-import discipline stays in
    exactly one place (`launch_gst_pipeline`) instead of being repeated at
    every call site that touches a buffer.
    """

    def __init__(self, pipeline: Any, appsink: Any, gst: Any, numpy: Any) -> None:
        """Wrap an already-PLAYING pipeline and its appsink element."""
        self._pipeline = pipeline
        self._appsink = appsink
        self._gst = gst
        self._numpy = numpy
        self._stopped = False

    def pull_frame(self, timeout_s: float) -> Any | None:
        """Pull one decoded BGR frame off the appsink branch.

        Returns:
            A BGR ndarray shaped (height, width, 3), or None if no sample
            arrived within `timeout_s`, the stream ended, or the buffer
            could not be mapped. None is the honest "no frame" value here
            for the same reason perception.camera.Camera.capture_frame()
            returns None rather than a zero-filled image - a black filler
            frame is indistinguishable from a real night frame.
        """
        gst = self._gst
        sample = self._appsink.emit("try-pull-sample", int(timeout_s * gst.SECOND))
        if sample is None:
            return None

        buffer = sample.get_buffer()
        structure = sample.get_caps().get_structure(0)
        width = structure.get_value("width")
        height = structure.get_value("height")

        ok, mapping = buffer.map(gst.MapFlags.READ)
        if not ok:
            logger.warning("event video: could not map a frame buffer, skipping it")
            return None
        try:
            # .copy() is load-bearing, not defensive style: the ndarray is a
            # view onto GStreamer's own buffer, which is unmapped and
            # recycled the moment this block exits.
            return (
                self._numpy.frombuffer(mapping.data, dtype=self._numpy.uint8)
                .reshape((height, width, 3))
                .copy()
            )
        finally:
            buffer.unmap(mapping)

    def stop(self, timeout_s: float) -> None:
        """Send EOS, wait up to `timeout_s` for the muxer to finish, then go to NULL.

        Idempotent. The wait is bounded rather than open-ended because a
        stuck encoder must not hold the reflex loop open indefinitely - and
        a Matroska file that never received its EOS is still playable
        (services/config.py's EVENT_VIDEO_SUFFIX), so timing out here
        costs the tail of a clip, not the clip.
        """
        if self._stopped:
            return
        self._stopped = True
        gst = self._gst
        try:
            self._pipeline.send_event(gst.Event.new_eos())
            bus = self._pipeline.get_bus()
            message = bus.timed_pop_filtered(
                int(timeout_s * gst.SECOND), gst.MessageType.EOS | gst.MessageType.ERROR
            )
            if message is None:
                logger.warning(
                    "event video: pipeline did not confirm end-of-stream within %.1fs - "
                    "the recording may be missing its tail",
                    timeout_s,
                )
            elif message.type == gst.MessageType.ERROR:
                error, debug = message.parse_error()
                logger.warning(
                    "event video: pipeline reported an error at stop: %s (%s)", error, debug
                )
        finally:
            self._pipeline.set_state(gst.State.NULL)


def launch_gst_pipeline(
    description: str,
    appsink_name: str = APPSINK_NAME,
    startup_timeout_s: float = config.EVENT_VIDEO_STOP_TIMEOUT_S,
) -> PipelineHandle:
    """Build and start a real GStreamer pipeline; the default pipeline_factory.

    The only place in this module `gi` and `numpy` are imported -
    function-local so `perception.video` stays importable with neither
    installed, exactly as perception/camera.py's `open_v4l2_capture` keeps
    `cv2` out of module scope.

    Args:
        description: A gst-launch description, from
            build_pipeline_description().
        appsink_name: Element name to look up for the frame branch.
        startup_timeout_s: How long to wait for the pipeline to actually
            reach PLAYING. A UVC device that is present but not yet
            streaming takes real time to negotiate.

    Returns:
        A started PipelineHandle, already in PLAYING.

    Raises:
        CameraError: If GStreamer is unavailable, the description does not
            parse, the named appsink is missing, or the pipeline does not
            reach PLAYING within `startup_timeout_s`. CameraError rather
            than a type of this module's own - see the module docstring.
    """
    try:
        import gi  # noqa: PLC0415 (deliberately local, see module docstring)

        gi.require_version("Gst", "1.0")

        import numpy  # noqa: PLC0415 (deliberately local)
        from gi.repository import Gst  # noqa: PLC0415 (local, and only valid after require_version)
    except (ImportError, ValueError) as exc:
        raise CameraError(f"GStreamer/PyGObject unavailable for event video: {exc}") from exc

    if not Gst.is_initialized():
        Gst.init(None)

    try:
        pipeline = Gst.parse_launch(description)
    except Exception as exc:  # noqa: BLE001 - GLib.Error, not an importable type here
        raise CameraError(f"event video pipeline failed to parse: {exc}") from exc

    appsink = pipeline.get_by_name(appsink_name)
    if appsink is None:
        pipeline.set_state(Gst.State.NULL)
        raise CameraError(f"event video pipeline has no element named {appsink_name!r}")

    if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
        pipeline.set_state(Gst.State.NULL)
        raise CameraError("event video pipeline refused to start")

    change, _state, _pending = pipeline.get_state(int(startup_timeout_s * Gst.SECOND))
    if change != Gst.StateChangeReturn.SUCCESS:
        pipeline.set_state(Gst.State.NULL)
        raise CameraError(
            f"event video pipeline did not reach PLAYING within {startup_timeout_s:.1f}s"
        )

    return _GstPipeline(pipeline, appsink, Gst, numpy)


class EventVideoRecorder:
    """Records one event to scratch while serving frames to the vision check.

    Satisfies services.reflex_loop.CameraProtocol, so it drops into the
    `camera=` seam unchanged, and adds `commit()`/`discard()` for the
    `event_video=` seam. Not thread-safe and not re-entrant: one recorder
    per device, one event at a time, opened and closed by the reflex loop
    around each event exactly as perception.camera.Camera is.

    Lifecycle, in the order the reflex loop drives it:
    `open()` (recording starts) -> `capture_burst()` (vision check, and
    again for the evidence burst on an alert) -> `close()` (recording stops,
    file finished) -> exactly one of `commit(tag)` or `discard()`.
    """

    def __init__(
        self,
        device: str = config.CAMERA_DEVICE,
        width: int = config.EVENT_VIDEO_WIDTH,
        height: int = config.EVENT_VIDEO_HEIGHT,
        framerate: int = config.EVENT_VIDEO_FRAMERATE,
        bitrate_bps: int = config.EVENT_VIDEO_BITRATE_BPS,
        scratch_dir: Path = config.EVENT_VIDEO_SCRATCH_DIR,
        suffix: str = config.EVENT_VIDEO_SUFFIX,
        capture_dir: Path = config.CAPTURE_DIR,
        warmup_frames: int = config.CAMERA_WARMUP_FRAMES,
        frame_timeout_s: float = config.EVENT_VIDEO_FRAME_TIMEOUT_S,
        stop_timeout_s: float = config.EVENT_VIDEO_STOP_TIMEOUT_S,
        pipeline_factory: Any = launch_gst_pipeline,
    ) -> None:
        """Configure a recorder without touching the device - open() does the I/O.

        Args:
            device: V4L2 device path.
            width: Recording width requested from the camera.
            height: Recording height requested from the camera.
            framerate: Frames per second requested from the camera.
            bitrate_bps: H.264 target bitrate.
            scratch_dir: Where in-progress recordings are written. Must
                share a filesystem with `capture_dir` - perception/storage.py
                commits with os.replace().
            suffix: Container extension for both scratch and committed names.
            capture_dir: Permanent capture directory, passed through to
                perception.storage.commit_video().
            warmup_frames: Frames pulled and discarded in open() before it
                returns, covering UVC AE/AGC settling - the same reason and
                the same constant perception.camera.Camera uses.
            frame_timeout_s: How long one capture may block waiting for a
                frame off the appsink branch.
            stop_timeout_s: How long close() waits for the file to finish.
            pipeline_factory: Callable(description, appsink_name,
                startup_timeout_s) -> PipelineHandle. Defaults to the real
                GStreamer backend. The one injection seam here, and it
                exists for the same reason perception.camera.Camera's
                `capture_factory` does - testing recording/keep/discard
                logic with no camera attached - not to support a second
                production backend.
        """
        self._device = device
        self._width = width
        self._height = height
        self._framerate = framerate
        self._bitrate_bps = bitrate_bps
        self._scratch_dir = scratch_dir
        self._suffix = suffix
        self._capture_dir = capture_dir
        self._warmup_frames = warmup_frames
        self._frame_timeout_s = frame_timeout_s
        self._stop_timeout_s = stop_timeout_s
        self._pipeline_factory = pipeline_factory
        self._pipeline: PipelineHandle | None = None
        self._scratch_path: Path | None = None
        self._recorded_path: Path | None = None

    @property
    def recording(self) -> bool:
        """True between a successful open() and the close() that ends it."""
        return self._pipeline is not None

    @property
    def pending_path(self) -> Path | None:
        """The scratch recording awaiting a commit/discard decision, if any."""
        return self._recorded_path

    def open(self) -> None:
        """Reserve a scratch path, start the pipeline, and discard warmup frames.

        Deliberately does not retry the way perception.camera.Camera.open()
        does. Camera's retry exists for a transient USB dropout at process
        start; this runs mid-event, after an MCU trigger, with the
        deterrence sequence waiting behind it - spending
        CAMERA_OPEN_RETRIES * CAMERA_OPEN_RETRY_BACKOFF_S here would delay
        the horn by seconds to rescue footage, and footage never gets to
        delay deterrence (services/reflex_loop.py's module docstring).

        A warmup that cannot produce frames is treated as a device failure,
        not as "record anyway": the recording would then be uncorroborated
        by any vision check, so the keep-gate would fall back to the alert
        decision alone. The pipeline is torn down and the scratch file
        removed before raising, so a failed open() leaves nothing behind.

        Raises:
            CameraError: If a scratch path cannot be created, the pipeline
                cannot be started, or warmup produces no frames.
        """
        if self._pipeline is not None:
            raise CameraError("event video recorder opened twice without an intervening close()")

        try:
            scratch_path = storage.scratch_video_path(self._scratch_dir, self._suffix)
        except OSError as exc:
            raise CameraError(f"cannot create event video scratch directory: {exc}") from exc

        description = build_pipeline_description(
            self._device,
            scratch_path,
            width=self._width,
            height=self._height,
            framerate=self._framerate,
            bitrate_bps=self._bitrate_bps,
        )
        self._scratch_path = scratch_path
        self._pipeline = self._pipeline_factory(description, APPSINK_NAME, self._stop_timeout_s)
        logger.info("event video: recording to %s", scratch_path)

        for i in range(self._warmup_frames):
            if self._pipeline.pull_frame(self._frame_timeout_s) is None:
                self._abandon(
                    f"event video pipeline produced no frame during warmup "
                    f"(frame {i + 1}/{self._warmup_frames})"
                )

    def _abandon(self, message: str) -> None:
        """Tear the pipeline down, delete the scratch file, and raise CameraError."""
        self.close()
        self.discard()
        raise CameraError(message)

    def capture_frame(self) -> Frame | None:
        """Pull one frame off the recording pipeline.

        Returns:
            A Frame, or None if no frame arrived within frame_timeout_s.
            Same never-raise-on-a-failed-grab contract, and the same reason
            for it, as perception.camera.Camera.capture_frame().

        Raises:
            CameraError: If called before open() or after close().
        """
        pipeline = self._require_open()
        image = pipeline.pull_frame(self._frame_timeout_s)
        if image is None:
            logger.warning("event video: no frame within %.1fs", self._frame_timeout_s)
            return None
        return Frame(image=image, index=0, timestamp_s=time.monotonic())

    def capture_burst(
        self,
        count: int = config.CAMERA_BURST_FRAMES,
        interval_s: float = config.CAMERA_BURST_INTERVAL_S,
    ) -> list[Frame]:
        """Pull up to `count` frames, spaced at least `interval_s` apart.

        Same contract as perception.camera.Camera.capture_burst(), so the
        reflex loop cannot tell the two apart: stops early on the first
        frame that does not arrive, returns 0 to `count` frames indexed in
        capture order, never raises for a short burst. Recording continues
        regardless - a slow or empty burst costs vision evidence, never the
        file.

        Args:
            count: Frames to attempt. Must be >= 1.
            interval_s: Minimum seconds between pulls. Must be >= 0.

        Returns:
            A list of 0 to `count` Frames.

        Raises:
            CameraError: If called before open() or after close().
            ValueError: If count < 1 or interval_s < 0.
        """
        if count < 1:
            raise ValueError(f"count must be >= 1, got {count}")
        if interval_s < 0:
            raise ValueError(f"interval_s must be >= 0, got {interval_s}")
        self._require_open()

        frames: list[Frame] = []
        for i in range(count):
            if i > 0 and interval_s > 0:
                time.sleep(interval_s)
            frame = self.capture_frame()
            if frame is None:
                logger.warning("event video: burst stopped early at %d/%d frames", i, count)
                break
            frames.append(Frame(image=frame.image, index=i, timestamp_s=frame.timestamp_s))
        return frames

    def close(self) -> None:
        """Stop recording and finish the file. Idempotent.

        Leaves the finished scratch recording on disk, undecided - the
        caller must follow with exactly one of commit() or discard().
        Never raises: a teardown fault must not propagate into a reflex
        loop that has already fired its actuators.
        """
        pipeline = self._pipeline
        self._pipeline = None
        if pipeline is None:
            return
        try:
            pipeline.stop(self._stop_timeout_s)
        except Exception as exc:  # noqa: BLE001 - see docstring: never raises
            logger.warning("event video: pipeline teardown failed: %s", exc)
        self._recorded_path = self._scratch_path
        self._scratch_path = None

    def commit(self, tag: storage.CaptureEventTag) -> Path | None:
        """Move this event's finished recording into the permanent capture dir.

        Closes the pipeline first if the caller has not - defensive, since
        committing a file the encoder is still writing would capture a
        truncated clip. Never raises.

        Args:
            tag: The decided event's metadata, which supplies the permanent
                filename. `tag.alert` may legitimately be False here: ADR
                0020's keep-gate is "vision confirmed OR alert fired".

        Returns:
            The committed path, or None if nothing was recorded or the move
            failed.
        """
        if self._pipeline is not None:
            logger.warning("event video: commit() called while still recording - closing first")
            self.close()

        recorded = self._recorded_path
        self._recorded_path = None
        if recorded is None:
            return None
        try:
            return storage.commit_video(recorded, tag, self._capture_dir)
        except Exception as exc:  # noqa: BLE001 - see docstring: never raises
            logger.warning("event video: commit failed for %s: %s", recorded, exc)
            return None

    def discard(self) -> None:
        """Delete this event's unconfirmed recording. Never raises.

        Closes the pipeline first if the caller has not, for the same
        reason commit() does - a file still being written cannot be
        removed cleanly. A no-op when nothing was recorded, so it is safe
        to call on an event whose open() failed.
        """
        if self._pipeline is not None:
            self.close()

        recorded = self._recorded_path
        self._recorded_path = None
        if recorded is None:
            return
        try:
            storage.discard_video(recorded)
        except Exception as exc:  # noqa: BLE001 - see docstring: never raises
            logger.warning("event video: discard failed for %s: %s", recorded, exc)

    def _require_open(self) -> PipelineHandle:
        if self._pipeline is None:
            raise CameraError("event video recorder used before open() or after close()")
        return self._pipeline

    def __enter__(self) -> EventVideoRecorder:
        """Start recording and return self, for `with EventVideoRecorder(...) as rec:`."""
        self.open()
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Stop recording unconditionally, including on an exception.

        Deliberately does not decide commit-or-discard - that is the
        event's call, not the context manager's, and silently discarding
        here would throw away footage on an unrelated exception.
        """
        self.close()
