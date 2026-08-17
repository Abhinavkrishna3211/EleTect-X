"""Disposable capture-and-save check for the real Arducam IMX462.

Not an App Lab app - needs no Bridge, no app.yaml, nothing schema-shaped
(mirrors bench/ping's own "disposable and separate from the real EleTect-X
app" discipline, ENGINEERING_CONVENTIONS.md 1). Opens perception.camera's
real Camera against whatever device/backend is asked for, captures one
frame plus a short burst, saves them to disk, and prints what the device
actually negotiated - this is what closes the resolution/format/FPS
entries in docs/KNOWN_GAPS.md, not the product listing's numbers.

Runs in two places:
- The board, over SSH, forcing --backend v4l2 (or the --backend auto
  default, which resolves to v4l2 on Linux) - the actual target platform
  perception/camera.py is written for.
- A Windows/macOS dev host with `pip install opencv-python`, using
  --backend any (or the --backend auto default off-Linux) - the IMX462 is
  a UVC device, so it enumerates fine over DirectShow/AVFoundation too.
  This lets the real camera be sanity-checked before a board session is
  available; it exercises the same perception.camera.Camera class, just
  through a different OpenCV backend than production uses.

perception/camera.py itself stays strictly V4L2 (CAP_V4L2, forced
explicitly) - this script's cross-platform backend selection lives here,
not there, so the production module's one supported path stays simple.

Status: pending hardware (docs/KNOWN_GAPS.md) - written but not yet run
against the real IMX462 on the board or the dev host.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Puts device/mpu on sys.path so `from perception.camera import Camera`
# resolves the same way it does under pytest (pyproject.toml's
# pythonpath = ["."]), whether this script is run in place or copied to a
# board/App folder that mirrors this tree.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402 (after sys.path setup, deliberately) - board/host-only, never imported by pytest

from perception.camera import Camera, fourcc_to_int  # noqa: E402
from services import config  # noqa: E402

_DEFAULT_OUT_DIR = Path(__file__).resolve().parent / "output"


def _resolve_backend(name: str) -> int:
    """Map --backend's string choice to a cv2 VideoCapture apiPreference.

    Args:
        name: "v4l2" (force Video4Linux2), "any" (OS default backend), or
            "auto" (v4l2 on Linux, OS default elsewhere).

    Returns:
        A cv2.CAP_* constant.
    """
    if name == "v4l2":
        return cv2.CAP_V4L2
    if name == "any":
        return cv2.CAP_ANY
    # auto
    return cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY


def _normalize_device(device: str) -> int | str:
    """Turn an all-digit device string into a camera index, else leave it as a path.

    /dev/video0 stays a path; a bare "0" (the common Windows/macOS
    --backend any default) becomes the int index OpenCV's non-V4L2
    backends expect.
    """
    return int(device) if device.isdigit() else device


def _make_capture_factory(backend: int):
    """Build a Camera-compatible capture_factory bound to one backend preference.

    Mirrors perception.camera.open_v4l2_capture's shape exactly
    (device, width, height, fourcc) -> capture handle, so this script can
    drive the real Camera class instead of duplicating its open/warmup/
    capture logic.
    """

    def factory(device: str, width: int, height: int, fourcc: str):
        capture = cv2.VideoCapture(_normalize_device(device), backend)
        capture.set(cv2.CAP_PROP_FOURCC, fourcc_to_int(fourcc))
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        return capture

    return factory


def _probe(device: str) -> None:
    """Print what's actually on the bus, ahead of trying to open anything.

    Linux-only (v4l2-ctl is a V4L2 utility). Resolves the exact device-path
    and default-resolution/format gaps logged in docs/KNOWN_GAPS.md in one
    run, independent of whether Camera.open() itself succeeds.
    """
    if not sys.platform.startswith("linux"):
        print("--probe is Linux/V4L2-only; skipping on this platform.")
        return

    video_nodes = sorted(Path("/dev").glob("video*"))
    if video_nodes:
        print(f"Found {len(video_nodes)} /dev/video* node(s): {[str(p) for p in video_nodes]}")
    else:
        print("No /dev/video* nodes found. If the IMX462 is plugged in, this points at a USB "
              "host-mode question (does the UNO Q's USB-C port enumerate a host device at all "
              "while powered from VIN?), not a code bug - see docs/KNOWN_GAPS.md.")
        return

    v4l2_ctl = shutil.which("v4l2-ctl")
    if v4l2_ctl is None:
        print("v4l2-ctl not found on PATH - install v4l2-utils for a full format listing.")
        return

    result = subprocess.run(  # noqa: S603 (fixed args, no shell, board-only bench script)
        [v4l2_ctl, "--list-formats-ext", "-d", device],
        capture_output=True,
        text=True,
        check=False,
    )
    print(f"--- v4l2-ctl --list-formats-ext -d {device} ---")
    print(result.stdout or "(no stdout)")
    if result.returncode != 0:
        print(f"(v4l2-ctl exited {result.returncode}; stderr: {result.stderr.strip()})")


def _save_frame(frame, out_dir: Path, name: str) -> None:
    """Write one frame to disk and print its saved size - proof it's a real image, not empty."""
    path = out_dir / name
    ok = cv2.imwrite(str(path), frame.image)
    if not ok:
        print(f"  FAILED to write {path}")
        return
    size_bytes = path.stat().st_size
    print(f"  saved {path} ({size_bytes} bytes, index={frame.index}, t={frame.timestamp_s:.3f}s)")


def main() -> int:
    """Run the capture-and-save check. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--device", default=None, help="Device path or index (default: backend-appropriate)"
    )
    parser.add_argument(
        "--backend",
        choices=["auto", "v4l2", "any"],
        default="auto",
        help="auto=v4l2 on Linux/OS-default elsewhere, v4l2=force V4L2, any=force OS default",
    )
    parser.add_argument(
        "--frames", type=int, default=config.CAMERA_BURST_FRAMES, help="Burst frame count"
    )
    parser.add_argument(
        "--out-dir", default=str(_DEFAULT_OUT_DIR), help="Where to save captured images"
    )
    parser.add_argument("--width", type=int, default=config.CAMERA_FRAME_WIDTH)
    parser.add_argument("--height", type=int, default=config.CAMERA_FRAME_HEIGHT)
    parser.add_argument(
        "--format", default=config.CAMERA_PIXEL_FORMAT, help="4-char FourCC, e.g. MJPG"
    )
    parser.add_argument(
        "--probe", action="store_true", help="List /dev/video* and v4l2-ctl formats first"
    )
    args = parser.parse_args()

    backend = _resolve_backend(args.backend)
    device = args.device or (config.CAMERA_DEVICE if backend == cv2.CAP_V4L2 else "0")

    if args.probe:
        _probe(device)
        print()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    camera = Camera(
        device=device,
        width=args.width,
        height=args.height,
        pixel_format=args.format,
        capture_factory=_make_capture_factory(backend),
    )

    print(
        f"Opening {device!r} (backend={args.backend}, requested "
        f"{args.width}x{args.height} {args.format})..."
    )
    try:
        camera.open()
    except Exception as exc:  # noqa: BLE001 - top-level bench script, report and exit non-zero
        print(f"FAILED to open camera: {exc}")
        return 1

    info = camera.info
    print(
        f"Negotiated: device={info.device} {info.width}x{info.height} "
        f"fourcc={info.fourcc} fps={info.fps}"
    )

    print("\nSingle frame:")
    single = camera.capture_frame()
    if single is None:
        print("  FAILED to capture a single frame.")
        camera.close()
        return 1
    _save_frame(single, out_dir, "single.jpg")

    print(f"\nBurst ({args.frames} requested):")
    burst = camera.capture_burst(count=args.frames)
    if not burst:
        print("  FAILED - burst captured zero frames.")
        camera.close()
        return 1
    for frame in burst:
        _save_frame(frame, out_dir, f"burst_{frame.index:02d}.jpg")

    if len(burst) > 1:
        intervals = [
            b.timestamp_s - a.timestamp_s for a, b in zip(burst[:-1], burst[1:], strict=True)
        ]
        print(f"  inter-frame intervals (s): {[round(i, 4) for i in intervals]}")

    if len(burst) < args.frames:
        print(
            f"  NOTE: only {len(burst)}/{args.frames} burst frames captured - "
            "device stopped early."
        )

    camera.close()
    print(f"\nDone. {1 + len(burst)} frame(s) saved to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
