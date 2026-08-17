"""V4L2 capture wrapper for the Arducam IMX462 day/night USB camera (ADR 0001).

Capture only. No trigger logic, no IR sync: `pulse_ir()` is an MCU-side
Bridge call not registered on either side yet (device/mpu/bridge/rpc.py),
and this module never imports `Bridge`. No pixel processing either - that
is the detector's job, once perception/ grows one. This is the one
`capture_frame()` contract ENGINEERING_CONVENTIONS.md 1 calls out as an
earned interface boundary ("the detector never imports V4L2 or a camera
driver directly"); this module is that contract's only implementation.

Backend: OpenCV (`cv2.VideoCapture`, `cv2.CAP_V4L2` passed explicitly so the
backend is never silently auto-selected). The alternative - raw V4L2 via
`ctypes`/`ioctl` - means hand-writing VIDIOC_QUERYCAP/S_FMT/REQBUFS/QBUF/
DQBUF/STREAMON plus mmap buffer-lifetime management: several hundred lines
of fragile struct packing, and it still hands back raw MJPEG bytes that need
a JPEG decoder afterward. OpenCV is already an unavoidable dependency one
layer up (the detector needs it for letterbox/resize into the INT8 model's
input, CONTEXT.md 4), so hand-rolled V4L2 would add a second capture stack
purely to avoid a dependency this project can't avoid anyway - the opposite
of CONTEXT.md 7's "simplicity over complexity."

This module must stay importable with no OpenCV installed and no camera
attached (device/mpu/README.md's host-test harness): `cv2` is imported only
inside `open_v4l2_capture`, never at module scope.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

from services import config

logger = logging.getLogger(__name__)

# cv2.VideoCapture's own property IDs (highgui/videoio public API) -
# hardcoded rather than read off `cv2.CAP_PROP_*` so that Camera.open()
# never needs to import cv2 even when a fake capture_factory is injected
# (tests/test_camera.py). These four have been stable across OpenCV's 3.x
# and 4.x lines; open_v4l2_capture (the real backend) still goes through
# cv2's own named constants for CAP_V4L2/CAP_PROP_FOURCC at the one call
# site that legitimately needs cv2 imported.
_CAP_PROP_FRAME_WIDTH = 3
_CAP_PROP_FRAME_HEIGHT = 4
_CAP_PROP_FPS = 5
_CAP_PROP_FOURCC = 6


class CameraError(RuntimeError):
    """Raised when the camera device cannot be opened, or used after close().

    Never raised by capture_frame()/capture_burst() for an ordinary failed
    grab - see their own docstrings for why that returns an empty result
    instead.
    """


@dataclass(frozen=True)
class Frame:
    """One captured frame.

    Attributes:
        image: BGR ndarray as OpenCV returns it (`Any` here deliberately -
            this module has no numpy/cv2 dependency at type-check time,
            and never reads pixel values itself; that is the detector's
            job once perception/ grows one).
        index: Position within the burst that produced this frame, 0 for a
            single capture_frame() call.
        timestamp_s: `time.monotonic()` at the moment this frame was
            received, not wall-clock - only relative spacing within one
            process's run matters here (recovering a burst's real
            inter-frame interval), never a cross-process timestamp.
    """

    image: Any
    index: int
    timestamp_s: float


@dataclass(frozen=True)
class CameraInfo:
    """What the device actually negotiated, not what was requested.

    open() reads these back from the capture handle after applying the
    requested format/resolution - a UVC device is free to round to the
    nearest mode it supports, so this is the only trustworthy source for
    "what resolution/format is this camera really running at"
    (docs/KNOWN_GAPS.md: IMX462 default resolution/format is unverified).
    """

    device: str
    width: int
    height: int
    fourcc: str
    fps: float


def fourcc_to_int(code: str) -> int:
    """Pack a 4-character FourCC code into the int V4L2/OpenCV expects.

    Pure function, no I/O - `cv2.VideoWriter_fourcc` does the identical
    packing but requires importing cv2 just for four `ord()` calls and a
    bit-shift, which this module otherwise avoids at import time.

    Args:
        code: Exactly 4 ASCII characters, e.g. "MJPG", "YUYV".

    Returns:
        The packed little-endian int OpenCV's `cv2.CAP_PROP_FOURCC` wants.

    Raises:
        ValueError: If `code` is not exactly 4 characters.
    """
    if len(code) != 4:
        raise ValueError(f"fourcc code must be exactly 4 characters, got {code!r}")
    return (
        ord(code[0])
        | (ord(code[1]) << 8)
        | (ord(code[2]) << 16)
        | (ord(code[3]) << 24)
    )


class _CaptureHandle(Protocol):
    """The subset of `cv2.VideoCapture`'s interface this module calls.

    Exists so tests can supply a fake without importing cv2 at all - see
    `Camera.__init__`'s `capture_factory` parameter.
    """

    def isOpened(self) -> bool: ...  # noqa: N802 (matches cv2's own naming)
    def set(self, prop_id: int, value: float) -> bool: ...
    def get(self, prop_id: int) -> float:
        ...

    def read(self) -> tuple[bool, Any]: ...
    def release(self) -> None: ...


def open_v4l2_capture(device: str, width: int, height: int, fourcc: str) -> _CaptureHandle:
    """Open a real `cv2.VideoCapture` against a V4L2 device and apply format.

    Default `capture_factory` for `Camera`. This is the only place in the
    module `cv2` is imported - function-local so `perception.camera` stays
    importable on a dev laptop with no OpenCV installed
    (device/mpu/README.md's host-test harness).

    Args:
        device: V4L2 device path, e.g. "/dev/video0".
        width: Requested frame width in pixels.
        height: Requested frame height in pixels.
        fourcc: 4-character pixel format code, e.g. "MJPG".

    Returns:
        An opened `cv2.VideoCapture`. Caller (`Camera.open`) is responsible
        for checking `isOpened()` - this function does not raise on a
        device that fails to open, it returns the handle as OpenCV gives
        it, so the caller can decide what CameraError message to raise.
    """
    import cv2  # noqa: PLC0415 (deliberately local, see module docstring)

    capture = cv2.VideoCapture(device, cv2.CAP_V4L2)
    capture.set(cv2.CAP_PROP_FOURCC, fourcc_to_int(fourcc))
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return capture


def _read_fourcc(capture: _CaptureHandle) -> str:
    """Decode the capture handle's negotiated FourCC back into 4 ASCII chars."""
    packed = int(capture.get(_CAP_PROP_FOURCC))
    chars = [chr((packed >> shift) & 0xFF) for shift in (0, 8, 16, 24)]
    return "".join(chars)


class Camera:
    """Capture-only wrapper around one V4L2 camera device.

    Pure capture contract: open, capture a single frame, capture a short
    burst, release. No trigger logic, no IR sync - see module docstring.
    Not thread-safe; one Camera instance per device, used from one thread.
    """

    def __init__(
        self,
        device: str = config.CAMERA_DEVICE,
        width: int = config.CAMERA_FRAME_WIDTH,
        height: int = config.CAMERA_FRAME_HEIGHT,
        pixel_format: str = config.CAMERA_PIXEL_FORMAT,
        warmup_frames: int = config.CAMERA_WARMUP_FRAMES,
        open_retries: int = config.CAMERA_OPEN_RETRIES,
        open_retry_backoff_s: float = config.CAMERA_OPEN_RETRY_BACKOFF_S,
        capture_factory: Any = open_v4l2_capture,
    ) -> None:
        """Configure a camera without opening it - open() does the I/O.

        Args:
            device: V4L2 device path.
            width: Requested frame width in pixels.
            height: Requested frame height in pixels.
            pixel_format: 4-character FourCC code to request.
            warmup_frames: Frames to grab and discard in open() before
                caching CameraInfo and returning - covers UVC AE/AGC
                settling (config.CAMERA_WARMUP_FRAMES's own rationale).
            open_retries: Attempts open() makes (factory call + isOpened()
                check + warmup) before raising CameraError. 1 means no
                retry. See config.CAMERA_OPEN_RETRIES's own rationale.
            open_retry_backoff_s: Seconds to sleep between failed open()
                attempts. Ignored when open_retries <= 1.
            capture_factory: Callable(device, width, height, fourcc) ->
                capture handle. Defaults to `open_v4l2_capture` (real
                OpenCV/V4L2). The one injection seam in this module, and it
                exists for the reason ENGINEERING_CONVENTIONS.md 1 permits
                one at all - a real need to test capture logic (warmup
                counting, burst accounting, failure handling) without a
                camera physically attached - not to support a second
                camera backend. Do not add a second production
                implementation behind this seam without a real second
                device to justify it.
        """
        self._device = device
        self._width = width
        self._height = height
        self._pixel_format = pixel_format
        self._warmup_frames = warmup_frames
        self._open_retries = open_retries
        self._open_retry_backoff_s = open_retry_backoff_s
        self._capture_factory = capture_factory
        self._capture: _CaptureHandle | None = None
        self._info: CameraInfo | None = None

    @property
    def info(self) -> CameraInfo:
        """Return what the device negotiated after open().

        Raises:
            CameraError: If called before open() or after close().
        """
        if self._info is None:
            raise CameraError("Camera.info read before open() or after close()")
        return self._info

    def open(self) -> None:
        """Open the device, apply format/resolution, and discard warmup frames.

        Retries up to `open_retries` times (config.CAMERA_OPEN_RETRIES),
        sleeping `open_retry_backoff_s` between attempts, before raising -
        a fresh capture handle is requested from `capture_factory` each
        attempt, since a device that failed to open or dropped mid-warmup
        needs a new handle, not a retried read() on the old one. A camera
        that still hasn't come up after all attempts is a real fault worth
        surfacing loudly - unlike capture_frame()'s per-grab failure
        handling, there is no "degraded but still running" state for a
        device that never came up at all.

        Raises:
            CameraError: If the device still fails to open, or fewer than
                `warmup_frames` frames can be grabbed during warmup, after
                `open_retries` attempts.
        """
        last_error = ""
        for attempt in range(1, self._open_retries + 1):
            capture = self._capture_factory(
                self._device, self._width, self._height, self._pixel_format
            )
            if not capture.isOpened():
                capture.release()
                last_error = f"failed to open camera device {self._device!r}"
            else:
                last_error = self._consume_warmup_frames(capture)
                if not last_error:
                    self._capture = capture
                    self._info = CameraInfo(
                        device=self._device,
                        width=int(capture.get(_CAP_PROP_FRAME_WIDTH)),
                        height=int(capture.get(_CAP_PROP_FRAME_HEIGHT)),
                        fourcc=_read_fourcc(capture),
                        fps=float(capture.get(_CAP_PROP_FPS)),
                    )
                    logger.info("camera opened: %s", self._info)
                    return

            if attempt < self._open_retries:
                logger.warning(
                    "camera %s: open attempt %d/%d failed (%s), retrying in %.1fs",
                    self._device,
                    attempt,
                    self._open_retries,
                    last_error,
                    self._open_retry_backoff_s,
                )
                time.sleep(self._open_retry_backoff_s)

        raise CameraError(f"{last_error} (after {self._open_retries} attempt(s))")

    def _consume_warmup_frames(self, capture: _CaptureHandle) -> str:
        """Grab and discard `warmup_frames` frames; release and return an error on failure.

        Returns:
            "" on success, else a message describing which warmup frame failed.
        """
        for i in range(self._warmup_frames):
            ok, _ = capture.read()
            if not ok:
                capture.release()
                return (
                    f"camera {self._device!r} failed during warmup "
                    f"(frame {i + 1}/{self._warmup_frames})"
                )
        return ""

    def capture_frame(self) -> Frame | None:
        """Capture a single frame.

        Returns:
            A Frame, or None if the grab failed. Deliberately never raises
            on a failed grab, and deliberately does not fall back to a
            zero-filled image the way read_seismic_window() zero-fills on
            an ADC timeout (ENGINEERING_CONVENTIONS.md 3) - a black filler
            frame is visually indistinguishable from a legitimate dark/
            night-IR frame, so a filler value here would be dishonest
            rather than degraded. None is the only truthful failure value;
            callers decide what "no frame" means for them.

        Raises:
            CameraError: If called before open() or after close().
        """
        capture = self._require_open()
        ok, image = capture.read()
        if not ok:
            logger.warning("camera %s: frame grab failed", self._device)
            return None
        return Frame(image=image, index=0, timestamp_s=time.monotonic())

    def capture_burst(
        self,
        count: int = config.CAMERA_BURST_FRAMES,
        interval_s: float = config.CAMERA_BURST_INTERVAL_S,
    ) -> list[Frame]:
        """Capture up to `count` frames, spaced at least `interval_s` apart.

        Stops early on the first failed grab rather than retrying - a short
        or empty result is a documented, honest outcome (mirrors
        capture_frame()'s None-on-failure choice), not an exception.

        Args:
            count: Number of frames to attempt. Must be >= 1.
            interval_s: Minimum seconds to sleep between grabs. 0.0 means
                "as fast as the device delivers," not a real-time
                guarantee. Must be >= 0.

        Returns:
            A list of 0 to `count` Frames, indexed 0..len-1 in capture
            order, each with its own timestamp_s. Length < count means the
            device stopped delivering partway through the burst.

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
                logger.warning(
                    "camera %s: burst stopped early at %d/%d frames",
                    self._device,
                    i,
                    count,
                )
                break
            frames.append(Frame(image=frame.image, index=i, timestamp_s=frame.timestamp_s))
        return frames

    def close(self) -> None:
        """Release the device. Idempotent - safe to call multiple times."""
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        self._info = None

    def _require_open(self) -> _CaptureHandle:
        if self._capture is None:
            raise CameraError(
                f"camera {self._device!r} used before open() or after close()"
            )
        return self._capture

    def __enter__(self) -> Camera:
        """Open the device and return self, for `with Camera(...) as cam:`."""
        self.open()
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Release the device unconditionally, including on an exception."""
        self.close()
