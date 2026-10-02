"""Sustained-capture-rate probe: is ~3.8 fps the camera, or the exposure mode?

Disposable bench script, same discipline as capture_check.py beside it - no
Bridge, no app.yaml, nothing schema-shaped. Drives the real
perception.camera.Camera so it measures the production capture path, not a
parallel one.

Why this exists. perception/video.py's module docstring records a 4-stage
buffer-counting probe (3 Sept 2026) that measured ~3.8 fps of real
throughput at *every* stage alike - raw MJPEG straight off `v4l2src`,
after `jpegdec`, after `videoconvert`, and after the full hardware H.264
encode. Identical numbers at stage 1 and stage 4 rule out decode/convert/
encode cost: the bottleneck is the camera's own capture rate, not the
encoder. That leaves one leading hypothesis, recorded there as a
hypothesis and never tested - auto-exposure throttling the sensor's frame
interval in low ambient light - and one decisive test that was never run:
force manual exposure, re-measure, restore. This script is that test.

It matters because it decides whether continuous recording can produce
smooth video at all. A rolling frame ring saves what the camera delivers;
if the camera delivers 3.8 fps, no choice of container or codec changes
that. Better to know before a night test than after one.

Four measurements, in this order:

1. Sustained capture rate on auto-exposure (the mode Camera.open() asserts).
2. Sustained capture rate with Camera.lock_night_exposure() applied.
3. Sustained rate of capture *plus* `cv2.imwrite` - the real per-frame cost
   of a JPEG ring, since imwrite re-encodes the BGR frame that capture just
   decoded.
4. Mean JPEG size on disk, which is what turns a frame rate into a storage
   budget.

Run it at night, under the IR illuminator, pointed at the scene the real
test will watch. Daylight numbers answer a different question than the one
this is for. Restores auto-exposure before exiting, including on Ctrl-C -
the control lives on the device and survives process exit
(perception/camera.py's _assert_auto_exposure docstring documents a real
case of a stale manual lock persisting across a reboot).

Status: written 6 Sept 2026, pending its first hardware run.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

# Puts device/mpu on sys.path so `from perception.camera import Camera`
# resolves the same way it does under pytest (pyproject.toml's
# pythonpath = ["."]), whether this script is run in place or copied to a
# board/App folder that mirrors this tree. Same shim capture_check.py uses.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402 (after sys.path setup, deliberately) - board/host-only, never imported by pytest

from perception.camera import Camera, fourcc_to_int  # noqa: E402
from services import config  # noqa: E402

_DEFAULT_OUT_DIR = Path(__file__).resolve().parent / "output"

# Long enough to average out USB scheduling jitter and one auto-exposure
# settling excursion; short enough that all three passes plus warmup fit in
# a couple of minutes on a board someone is standing next to at night.
_DEFAULT_SECONDS = 20.0

# What counts as "the exposure lock made a real difference". Chosen well
# above measurement noise on a 20 s window rather than at it: a 10% swing
# between two 20 s passes is ordinary USB jitter, and calling that a
# confirmed root cause would be exactly the kind of unearned conclusion
# perception/video.py's own docstring was careful not to draw.
_MEANINGFUL_FPS_GAIN = 1.25


@dataclass(frozen=True)
class PassResult:
    """One timed capture pass.

    Attributes:
        label: Which pass this was, for the printed table and the JSON.
        frames: Frames successfully grabbed.
        failures: Grabs that returned None. A high count here means the
            fps number below is measuring a struggling device, not a slow
            one, and should not be read as a capture-rate ceiling.
        elapsed_s: Wall time the pass actually ran.
        fps: frames / elapsed_s.
        mean_jpeg_bytes: Mean size of the JPEGs written, or None for a pass
            that did not write any.
    """

    label: str
    frames: int
    failures: int
    elapsed_s: float
    fps: float
    mean_jpeg_bytes: float | None


def _make_capture_factory(backend: int):
    """Build a Camera-compatible capture_factory bound to one backend preference.

    Mirrors perception.camera.open_v4l2_capture's signature exactly so this
    script drives the real Camera class rather than duplicating its open/
    warmup/capture logic. Same helper, same reason, as capture_check.py's.
    """

    def factory(device: str, width: int, height: int, fourcc: str):
        normalized = int(device) if device.isdigit() else device
        capture = cv2.VideoCapture(normalized, backend)
        capture.set(cv2.CAP_PROP_FOURCC, fourcc_to_int(fourcc))
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        return capture

    return factory


def _timed_pass(
    camera: Camera,
    label: str,
    seconds: float,
    *,
    write_dir: Path | None = None,
    jpeg_quality: int = 90,
) -> PassResult:
    """Capture as fast as the device allows for `seconds`, optionally writing JPEGs.

    Deliberately has no sleep and no pacing: the whole point is to find the
    rate the device sustains when nothing downstream is throttling it.

    Args:
        camera: An already-opened Camera.
        label: Name for this pass, carried into the result.
        seconds: How long to keep capturing.
        write_dir: When given, every frame is written here as a JPEG and
            the mean file size is reported. Files are deleted as they go, so
            a long pass does not fill the eMMC - the size is what is wanted,
            not the images.
        jpeg_quality: cv2.IMWRITE_JPEG_QUALITY for the written frames.

    Returns:
        A PassResult.
    """
    frames = 0
    failures = 0
    sizes: list[int] = []
    started = time.monotonic()
    deadline = started + seconds

    while time.monotonic() < deadline:
        frame = camera.capture_frame()
        if frame is None:
            failures += 1
            continue
        frames += 1
        if write_dir is not None:
            path = write_dir / f"probe_{frames:06d}.jpg"
            if cv2.imwrite(str(path), frame.image, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]):
                sizes.append(path.stat().st_size)
                path.unlink(missing_ok=True)

    elapsed = time.monotonic() - started
    return PassResult(
        label=label,
        frames=frames,
        failures=failures,
        elapsed_s=elapsed,
        fps=(frames / elapsed) if elapsed > 0 else 0.0,
        mean_jpeg_bytes=statistics.fmean(sizes) if sizes else None,
    )


def _print_pass(result: PassResult) -> None:
    """Print one pass as a single aligned line."""
    size = (
        f"  mean_jpeg={result.mean_jpeg_bytes / 1024:.1f} KB"
        if result.mean_jpeg_bytes is not None
        else ""
    )
    failures = f"  failed_grabs={result.failures}" if result.failures else ""
    print(
        f"  {result.label:<28} {result.fps:6.2f} fps "
        f"({result.frames} frames / {result.elapsed_s:.1f}s){size}{failures}"
    )


def _storage_table(fps: float, mean_jpeg_bytes: float) -> str:
    """Turn a measured rate and frame size into the ring/encounter storage budget.

    The ring is constant - PREROLL_S worth of frames, nothing more - so the
    only figure that scales with the night is the per-encounter clip. This
    prints both, which is what makes the storage question "buffer + N
    encounters" rather than "a whole night of footage".
    """
    per_s = fps * mean_jpeg_bytes
    preroll = config.HOME_TEST_PREROLL_S * per_s
    two_min = 120 * per_s
    budget = config.HOME_TEST_MAX_TOTAL_BYTES
    encounters = int(budget // two_min) if two_min > 0 else 0
    return (
        f"  ring ({config.HOME_TEST_PREROLL_S:.0f}s pre-roll): {preroll / 1e6:6.1f} MB (constant)\n"
        f"  per 2-min encounter:      {two_min / 1e6:6.1f} MB\n"
        f"  encounters in the {budget / 1e9:.0f} GB session cap: ~{encounters}"
    )


def main() -> int:
    """Run the fps probe. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default=config.CAMERA_DEVICE)
    parser.add_argument(
        "--seconds", type=float, default=_DEFAULT_SECONDS, help="Duration of each pass"
    )
    parser.add_argument(
        "--width",
        type=int,
        default=config.HOME_TEST_RING_WIDTH,
        help="Capture width to probe (defaults to the ring's own resolution)",
    )
    parser.add_argument("--height", type=int, default=config.HOME_TEST_RING_HEIGHT)
    parser.add_argument("--format", default=config.CAMERA_PIXEL_FORMAT)
    parser.add_argument(
        "--jpeg-quality", type=int, default=config.HOME_TEST_JPEG_QUALITY
    )
    parser.add_argument("--out-dir", default=str(_DEFAULT_OUT_DIR))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    camera = Camera(
        device=args.device,
        width=args.width,
        height=args.height,
        pixel_format=args.format,
        capture_factory=_make_capture_factory(cv2.CAP_V4L2),
    )

    print(f"Opening {args.device!r} at {args.width}x{args.height} {args.format}...")
    try:
        camera.open()
    except Exception as exc:  # noqa: BLE001 - top-level bench script, report and exit non-zero
        print(f"FAILED to open camera: {exc}")
        return 1

    info = camera.info
    print(
        f"Negotiated: {info.width}x{info.height} fourcc={info.fourcc} "
        f"driver-reported fps={info.fps}\n"
    )

    results: list[PassResult] = []
    locked = False
    try:
        print(f"Measuring, {args.seconds:.0f}s per pass:")

        # Camera.open() has just asserted auto-exposure, so this pass runs
        # in exactly the mode production capture uses today.
        auto = _timed_pass(camera, "1. auto-exposure", args.seconds)
        results.append(auto)
        _print_pass(auto)

        locked = camera.lock_night_exposure()
        if not locked:
            print(
                "  NOTE: lock_night_exposure() returned False - the write did not take, or "
                "NIGHT_EXPOSURE_LOCK_ENABLED is off. Pass 2 below is therefore a repeat of "
                "pass 1, not a locked-exposure measurement, and must not be read as one."
            )
        manual = _timed_pass(
            camera, "2. locked exposure" if locked else "2. lock FAILED (still auto)", args.seconds
        )
        results.append(manual)
        _print_pass(manual)

        # Pass 3 stays on whatever pass 2 established, so its delta against
        # pass 2 isolates the imwrite cost alone rather than mixing it with
        # an exposure-mode change.
        ring = _timed_pass(
            camera,
            "3. + JPEG write (ring cost)",
            args.seconds,
            write_dir=out_dir,
            jpeg_quality=args.jpeg_quality,
        )
        results.append(ring)
        _print_pass(ring)
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        # Restore auto-exposure before releasing the device. The control
        # lives on the camera, not on this file handle, and a stale manual
        # lock left behind here would silently change every later capture
        # on this board - a failure this project has already had once
        # (perception/camera.py's _assert_auto_exposure docstring).
        if locked:
            try:
                camera._assert_auto_exposure(camera._require_open())  # noqa: SLF001
                print("\nRestored auto-exposure.")
            except Exception as exc:  # noqa: BLE001 - best-effort cleanup
                print(f"\nWARNING: could not restore auto-exposure: {exc}")
        camera.close()

    if len(results) < 3:
        return 1

    auto, manual, ring = results
    print("\nVerdict:")
    if not locked:
        print(
            "  Inconclusive - the exposure lock never took, so the auto-vs-manual comparison\n"
            "  this script exists for did not actually happen. Check "
            "NIGHT_EXPOSURE_LOCK_ENABLED and rerun."
        )
    elif manual.fps >= auto.fps * _MEANINGFUL_FPS_GAIN:
        print(
            f"  Auto-exposure throttling CONFIRMED: {auto.fps:.2f} -> {manual.fps:.2f} fps "
            f"({manual.fps / auto.fps:.2f}x) with exposure locked.\n"
            f"  perception/video.py's 3 Sept hypothesis holds. Run the night test with the\n"
            f"  exposure lock on and expect ~{ring.fps:.1f} fps of usable ring capture."
        )
    else:
        print(
            f"  Auto-exposure throttling NOT confirmed: {auto.fps:.2f} -> {manual.fps:.2f} fps, "
            f"within noise.\n"
            f"  ~{auto.fps:.1f} fps looks like this camera/board/USB combination's real ceiling,\n"
            f"  which means smooth continuous video is not achievable on this hardware at any\n"
            f"  format or codec. The ring still works - expect a ~{ring.fps:.1f} fps clip."
        )

    if ring.mean_jpeg_bytes is not None:
        print(f"\nStorage at the measured ring rate ({ring.fps:.2f} fps):")
        print(_storage_table(ring.fps, ring.mean_jpeg_bytes))

    sidecar = out_dir / "fps_probe.json"
    sidecar.write_text(
        json.dumps(
            {
                "device": args.device,
                "requested": {"width": args.width, "height": args.height, "format": args.format},
                "negotiated": {
                    "width": info.width,
                    "height": info.height,
                    "fourcc": info.fourcc,
                    "driver_fps": info.fps,
                },
                "seconds_per_pass": args.seconds,
                "jpeg_quality": args.jpeg_quality,
                "exposure_lock_took": locked,
                "passes": [asdict(r) for r in results],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nWrote {sidecar}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
