"""Hardware soak for ExposureAutoLock - does the real policy lock/restore correctly over time?

Disposable bench script, same discipline as fps_probe.py beside it - no
Bridge, no app.yaml, nothing schema-shaped. Drives the real
perception.camera.Camera and perception.night.ExposureAutoLock directly, so
it measures the production lock/restore path, not a parallel one.

Why this exists. perception/night.py's ExposureAutoLock (added 7 Sept 2026,
closing HOME_TEST_MODE's one-shot-lock-at-start() bug) has full host-test
coverage against fake is_night/lock/restore callables and an injected clock,
but has never been driven against the real camera, the real
frames_are_night() saturation check, or real wall-clock timing. This script
is that missing hardware check: open the real device, poll it on
HOME_TEST_EXPOSURE_RECHECK_INTERVAL_S's real cadence, and log every
decision - including the *read-back* result, not just "no exception" - so a
morning review can match logged decisions against what the lens actually
saw.

Deliberately does NOT run the ring writer or a real HomeTestSession: 1.1 GB
free on this board's rootfs cannot absorb a multi-hour capture buffer, and
this script only needs bursts of a few frames per poll, not continuous
video. Caps its own JSONL+JPEG output at --max-output-mb and aborts if free
disk drops below --min-free-mb, checked every poll.

Restores auto-exposure before exiting, including on Ctrl-C or a fatal
error - same discipline as fps_probe.py, for the same reason
(perception/camera.py's _assert_auto_exposure docstring documents a real
stale-manual-lock case surviving a reboot).

Status: written 7 Sept 2026, pending its first hardware run.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Puts device/mpu on sys.path so `from perception.camera import Camera`
# resolves the same way it does under pytest (pyproject.toml's
# pythonpath = ["."]), whether this script is run in place or copied to a
# board/App folder that mirrors this tree. Same shim fps_probe.py uses.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402 (after sys.path setup, deliberately) - board/host-only, never imported by pytest

from perception.camera import Camera, fourcc_to_int  # noqa: E402
from perception.night import ExposureAutoLock, frames_are_night  # noqa: E402
from services import config  # noqa: E402

_DEFAULT_OUT_DIR = Path(__file__).resolve().parent / "output" / "exposure_autolock_soak"

# A handful of frames is enough for frame_mean_saturation()'s median - this
# is a lock/restore soak, not a throughput probe, so it does not need
# fps_probe.py's sustained-capture-rate discipline.
_DEFAULT_BURST_FRAMES = 3

# Matched to fps_probe.py's own output-size discipline - keep a multi-hour
# unattended run from ever threatening the 1.1 GB free on this board's root.
_DEFAULT_MAX_OUTPUT_MB = 200
_DEFAULT_MIN_FREE_MB = 300

# One heartbeat line even when nothing changed, so a truncated log's last
# timestamp is informative rather than just "script died at some point
# before this".
_HEARTBEAT_EVERY_S = 300.0


def _real_is_night(frames: list) -> bool | None:
    """The same NightDecideFn shape main.py's _is_night() binds.

    Kept identical to main.py's own _is_night() and
    tests/test_home_test.py's _real_is_night() so this soak measures the
    exact function main.py wires into ExposureAutoLock in production, not
    a stand-in.
    """
    return frames_are_night([f.image for f in frames], config.NIGHT_SATURATION_THRESHOLD)


def _make_capture_factory(backend: int):
    """Build a Camera-compatible capture_factory bound to one backend preference.

    Mirrors perception.camera.open_v4l2_capture's signature exactly, same
    as fps_probe.py's own helper.
    """

    def factory(device: str, width: int, height: int, fourcc: str):
        normalized = int(device) if device.isdigit() else device
        capture = cv2.VideoCapture(normalized, backend)
        capture.set(cv2.CAP_PROP_FOURCC, fourcc_to_int(fourcc))
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        return capture

    return factory


def _v4l2_readback(device: str) -> str:
    """Cross-check the device's own reported exposure controls via v4l2-ctl.

    Independent of anything Camera itself reports - if v4l2-ctl disagrees
    with what lock_night_exposure()/restore_auto_exposure() verified, that
    is exactly the kind of discrepancy this soak exists to catch. Never
    raises: v4l2-ctl may not be on PATH in every environment this script
    gets copied to, and that must not abort the soak.
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


def _free_mb(path: Path) -> float:
    """Free space on `path`'s filesystem, in MB."""
    return shutil.disk_usage(path).free / 1e6


def _dir_size_mb(path: Path) -> float:
    """Total size of everything already written under `path`, in MB."""
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6


def main() -> int:
    """Run the soak. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default=config.CAMERA_DEVICE)
    parser.add_argument("--width", type=int, default=config.HOME_TEST_RING_WIDTH)
    parser.add_argument("--height", type=int, default=config.HOME_TEST_RING_HEIGHT)
    parser.add_argument("--format", default=config.CAMERA_PIXEL_FORMAT)
    parser.add_argument(
        "--duration-s",
        type=float,
        default=7200.0,
        help="Total soak duration in seconds (default 2h, per the plan's overnight target)",
    )
    parser.add_argument(
        "--poll-interval-s",
        type=float,
        default=config.HOME_TEST_EXPOSURE_RECHECK_INTERVAL_S,
        help="How often to pull a burst and call maybe_update() - defaults to the real config",
    )
    parser.add_argument("--burst-frames", type=int, default=_DEFAULT_BURST_FRAMES)
    parser.add_argument("--out-dir", default=str(_DEFAULT_OUT_DIR))
    parser.add_argument("--max-output-mb", type=float, default=_DEFAULT_MAX_OUTPUT_MB)
    parser.add_argument("--min-free-mb", type=float, default=_DEFAULT_MIN_FREE_MB)
    parser.add_argument(
        "--save-jpeg",
        action="store_true",
        help="Also save one JPEG per decision (counts against --max-output-mb)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "decisions.jsonl"

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
    print(f"Negotiated: {info.width}x{info.height} fourcc={info.fourcc}\n")
    print(f"Kill switch (NIGHT_EXPOSURE_LOCK_ENABLED): {config.NIGHT_EXPOSURE_LOCK_ENABLED}")
    print(
        f"interval_s={args.poll_interval_s}  "
        f"flip_consecutive={config.HOME_TEST_EXPOSURE_FLIP_CONSECUTIVE}"
    )
    print(f"Logging to {log_path}\n")

    policy = ExposureAutoLock(
        is_night=_real_is_night,
        lock=camera.lock_night_exposure,
        restore=camera.restore_auto_exposure,
        lock_at=camera.lock_night_exposure,
        interval_s=args.poll_interval_s,
    )

    started = time.monotonic()
    deadline = started + args.duration_s
    last_heartbeat = started
    decisions_logged = 0
    aborted_reason: str | None = None

    try:
        while time.monotonic() < deadline:
            free_mb = _free_mb(out_dir)
            if free_mb < args.min_free_mb:
                aborted_reason = (
                    f"free disk {free_mb:.0f} MB < --min-free-mb {args.min_free_mb:.0f}"
                )
                break
            written_mb = _dir_size_mb(out_dir)
            if written_mb > args.max_output_mb:
                aborted_reason = (
                    f"own output {written_mb:.0f} MB exceeded "
                    f"--max-output-mb {args.max_output_mb:.0f}"
                )
                break

            frames = []
            for _ in range(args.burst_frames):
                frame = camera.capture_frame()
                if frame is not None:
                    frames.append(frame)

            decision = policy.maybe_update(frames)
            now = time.monotonic()

            if decision is not None:
                readback = (
                    _v4l2_readback(args.device)
                    if decision.action != "hold" or decision.trim_applied
                    else ""
                )
                record = {
                    "wall_s": decision.wall_s,
                    "elapsed_s": round(now - started, 1),
                    "frames_captured": len(frames),
                    "saturations": decision.saturations,
                    "median_saturation": decision.median_saturation,
                    "night": decision.night,
                    "action": decision.action,
                    "applied": decision.applied,
                    "policy_locked": policy.locked,
                    "median_clip_fraction": decision.median_clip_fraction,
                    "exposure_value": decision.exposure_value,
                    "trim_applied": decision.trim_applied,
                    "v4l2_readback": readback,
                }
                with log_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record) + "\n")
                decisions_logged += 1
                print(
                    f"[{record['elapsed_s']:8.1f}s] action={decision.action:<8} "
                    f"night={decision.night} applied={decision.applied} "
                    f"median_sat={decision.median_saturation} "
                    f"clip={decision.median_clip_fraction} exposure={decision.exposure_value} "
                    f"locked={policy.locked}"
                    + (f"  v4l2: {readback}" if readback else "")
                )

                if args.save_jpeg and frames:
                    jpeg_path = out_dir / f"decision_{decisions_logged:05d}.jpg"
                    cv2.imwrite(str(jpeg_path), frames[-1].image)

            if now - last_heartbeat >= _HEARTBEAT_EVERY_S:
                elapsed_min = (now - started) / 60.0
                print(
                    f"  heartbeat: {elapsed_min:.1f} min elapsed, "
                    f"{decisions_logged} decisions logged, locked={policy.locked}"
                )
                last_heartbeat = now

            # No sleep beyond what capture_frame() itself costs: maybe_update()
            # self-rate-limits against poll_interval_s, so a tight loop here
            # just means capture_frame() is called more often between
            # evaluations, which is harmless and keeps the burst fresh.
            time.sleep(min(1.0, args.poll_interval_s / 4))
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        try:
            restored = camera.restore_auto_exposure()
            print(f"\nFinal restore_auto_exposure(): {restored}")
        except Exception as exc:  # noqa: BLE001 - best-effort cleanup
            print(f"\nWARNING: could not restore auto-exposure: {exc}")
        camera.close()

    if aborted_reason:
        print(f"\nABORTED: {aborted_reason}")

    total_min = (time.monotonic() - started) / 60
    print(f"\n{decisions_logged} decisions logged over {total_min:.1f} min.")
    print(f"Log: {log_path}")
    return 0 if not aborted_reason else 2


if __name__ == "__main__":
    sys.exit(main())
