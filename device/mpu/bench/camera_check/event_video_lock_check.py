"""Hardware check for EventVideoRecorder.lock_night_exposure() - does the baked-in control land?

Disposable bench script, same discipline as fps_probe.py and
exposure_autolock_soak.py beside it - no Bridge, no app.yaml, nothing
schema-shaped. Drives the real perception.video.EventVideoRecorder and its
real GStreamer pipeline_factory directly, so this measures the production
build-time exposure-lock path, not a parallel one.

Why this exists. perception/video.py's EventVideoRecorder.lock_night_exposure()
(closed 7 Sept 2026, alongside HOME_TEST_MODE's periodic exposure fix) bakes
manual exposure into `v4l2src`'s own `extra-controls` property at pipeline
build time, because this class has no persistent capture handle to
`cv2.VideoCapture.set()` the way perception.camera.Camera does. That path
has full host-test coverage against a fake pipeline_factory
(tests/test_video.py), but has never been driven against the real GStreamer
pipeline on real hardware. This script is that missing check.

Exercises the *documented* two-event shape, not a single open() - see
lock_night_exposure()'s own docstring for why: the flag armed on event N can
only affect event N+1's pipeline description, never the one already
running when it is called. So this script:

  1. Opens event 1 unlocked, confirms via v4l2-ctl it is on auto exposure,
     calls lock_night_exposure() *while still open* (arming it for the next
     open()), then closes and discards event 1.
  2. Opens event 2 - the pipeline description built for this open() should
     now carry the baked-in extra-controls - confirms via v4l2-ctl that the
     device is now on manual exposure at the locked value, then closes and
     discards event 2.

Cross-checks with `v4l2-ctl --get-ctrl` while each pipeline is actually
running, mirroring exposure_autolock_soak.py's `_v4l2_readback()` - the
thing this script exists to answer is whether the baked-in control actually
reaches the driver, not just whether build_pipeline_description() returns a
string containing the right substring (tests/test_video.py already proves
that).

Writes both events to an isolated scratch/capture directory under
--out-dir, never to config.CAPTURE_DIR/config.EVENT_VIDEO_SCRATCH_DIR - this
is a bench check, not a real encounter, and both recordings are discarded
(never committed) once the check is done. EVENT_VIDEO_ENABLED stays False in
config throughout; this script constructs EventVideoRecorder directly,
bypassing that switch entirely, exactly as the plan's Step 6 item 4
requires.

Status: written 7 Sept 2026, pending its first hardware run.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

# Puts device/mpu on sys.path so `from perception.video import ...` resolves
# the same way it does under pytest (pyproject.toml's pythonpath = ["."]).
# Same shim fps_probe.py and exposure_autolock_soak.py use.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from perception.camera import CameraError  # noqa: E402
from perception.video import EventVideoRecorder  # noqa: E402
from services import config  # noqa: E402

_DEFAULT_OUT_DIR = Path(__file__).resolve().parent / "output" / "event_video_lock_check"


def _v4l2_readback(device: str) -> str:
    """Cross-check the device's own reported exposure controls via v4l2-ctl.

    Independent of anything EventVideoRecorder itself reports - if v4l2-ctl
    disagrees with what the baked-in extra-controls string requested, that
    is exactly the kind of discrepancy this check exists to catch. Never
    raises: v4l2-ctl may not be on PATH in every environment this script
    gets copied to, and that must not abort the check.
    """
    try:
        result = subprocess.run(  # noqa: S603, S607 - fixed args, board-local diagnostic tool
            ["v4l2-ctl", "-d", device, "--get-ctrl=auto_exposure,exposure_time_absolute"],
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        return (result.stdout or result.stderr).strip().replace("\n", "; ")
    except Exception as exc:  # noqa: BLE001 - best-effort diagnostic only
        return f"v4l2-ctl unavailable: {exc}"


def _run_one_event(
    recorder: EventVideoRecorder,
    device: str,
    label: str,
    duration_s: float,
    arm_lock_before_close: bool,
) -> bool:
    """Open, record for duration_s while polling v4l2-ctl, close, discard. Returns success."""
    print(f"\n--- {label}: open() ---")
    try:
        recorder.open()
    except CameraError as exc:
        print(f"FAILED to open: {exc}")
        return False

    ok = True
    started = time.monotonic()
    while time.monotonic() - started < duration_s:
        frame = recorder.capture_frame()
        readback = _v4l2_readback(device)
        elapsed = time.monotonic() - started
        print(
            f"  [{elapsed:5.1f}s] frame={'yes' if frame is not None else 'NONE'}  "
            f"v4l2: {readback}"
        )
        time.sleep(0.5)

    if arm_lock_before_close:
        armed = recorder.lock_night_exposure()
        print(f"  lock_night_exposure() while still open -> {armed} (arms the *next* open())")

    print(f"--- {label}: close() + discard() ---")
    recorder.close()
    recorder.discard()
    return ok


def main() -> int:
    """Run the two-event check. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default=config.CAMERA_DEVICE)
    parser.add_argument("--width", type=int, default=config.EVENT_VIDEO_WIDTH)
    parser.add_argument("--height", type=int, default=config.EVENT_VIDEO_HEIGHT)
    parser.add_argument("--framerate", type=int, default=config.EVENT_VIDEO_FRAMERATE)
    parser.add_argument("--bitrate-bps", type=int, default=config.EVENT_VIDEO_BITRATE_BPS)
    parser.add_argument(
        "--duration-s",
        type=float,
        default=5.0,
        help=(
            "Seconds to record and poll v4l2-ctl for, per event "
            "(default matches the plan's Step 6 item 4)"
        ),
    )
    parser.add_argument("--out-dir", default=str(_DEFAULT_OUT_DIR))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    capture_dir = out_dir / "captures"
    scratch_dir = capture_dir / ".scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)

    print(f"Kill switch (NIGHT_EXPOSURE_LOCK_ENABLED): {config.NIGHT_EXPOSURE_LOCK_ENABLED}")
    print(f"Isolated capture_dir: {capture_dir}")
    print(f"Isolated scratch_dir: {scratch_dir}")
    print("Both events below are discarded, never committed - this is a bench check.\n")

    recorder = EventVideoRecorder(
        device=args.device,
        width=args.width,
        height=args.height,
        framerate=args.framerate,
        bitrate_bps=args.bitrate_bps,
        scratch_dir=scratch_dir,
        capture_dir=capture_dir,
        warmup_frames=config.CAMERA_WARMUP_FRAMES,
        frame_timeout_s=config.EVENT_VIDEO_FRAME_TIMEOUT_S,
        stop_timeout_s=config.EVENT_VIDEO_STOP_TIMEOUT_S,
    )

    try:
        # Event 1: unlocked. Confirms the baseline (auto exposure), then
        # arms lock_night_exposure() while still open, per its own
        # docstring - the flag can only affect the *next* open().
        ok1 = _run_one_event(
            recorder, args.device, "event 1 (unlocked)", args.duration_s,
            arm_lock_before_close=True,
        )

        # Event 2: the pipeline description built for this open() should
        # now carry the baked-in extra-controls, since event 1 armed the
        # flag before closing.
        ok2 = _run_one_event(
            recorder, args.device, "event 2 (locked, from event 1's arm)", args.duration_s,
            arm_lock_before_close=False,
        )
    finally:
        # Defensive: _run_one_event already closes+discards on the happy
        # path; this only matters if open()/capture_frame() raised
        # unexpectedly between the two events.
        if recorder.recording:
            recorder.close()
            recorder.discard()

    print("\n--- summary ---")
    print(f"event 1 (expected auto exposure throughout): {'ok' if ok1 else 'FAILED'}")
    print(f"event 2 (expected manual/locked exposure throughout): {'ok' if ok2 else 'FAILED'}")
    print(
        "Compare the v4l2 readback lines above by eye: event 1 should show "
        "'Auto Exposure Mode' (auto_exposure=3) throughout; event 2 should "
        f"show 'Manual Mode' (auto_exposure=1) and "
        f"exposure_time_absolute={config.NIGHT_LOCKED_EXPOSURE} throughout."
    )
    return 0 if (ok1 and ok2) else 1


if __name__ == "__main__":
    sys.exit(main())
