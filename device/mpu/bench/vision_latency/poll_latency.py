"""Measure HOME_TEST_MODE's real inference-poll latency, not guess it.

Disposable bench script, same discipline as bench/camera_check/*.py beside
it - no Bridge, no app.yaml, nothing schema-shaped. Drives the real
perception.detector.HttpVisionDetector against the real, already-running
edge-impulse-linux-runner (services/config.py's VISION_INFERENCE_URL,
normally http://127.0.0.1:1337) - the exact client class main.py
constructs, not a stand-in - so it measures the production inference path.

Why this exists. docs/KNOWN_GAPS.md's "HOME_TEST_MODE encounter latency is
dominated by serial inference calls, not the poll interval" entry (found 7
Sept, during the first real encounter test) observed that
HOME_TEST_INFERENCE_FRAME_COUNT=3 means three sequential HTTP round-trips
per poll, and HOME_TEST_FIRE_CONSECUTIVE_POLLS=3 stacks three such polls
before an encounter can fire - together stretching the animal-appears-to-
deterrent-responds window well past the nominal "3 polls x 1.0s interval"
the constants alone would suggest, since HttpVisionDetector's per-frame
loop (detector.py's `for image in images`) is serial, not concurrent. This
script measures that directly instead of estimating it, comparing today's
(frame_count=3, consecutive_polls=3) against the proposed (1, 2), and
reports numbers only - it deliberately does NOT change
HOME_TEST_INFERENCE_FRAME_COUNT or HOME_TEST_FIRE_CONSECUTIVE_POLLS in
services/config.py; that decision belongs to waking hours, not a bench
script (docs/KNOWN_GAPS.md's own framing).

Feeds real JPEGs read from an existing HOME_TEST_MODE encounter directory
(services/config.py's HOME_TEST_ENCOUNTERS_DIR), never the live camera -
this removes camera contention entirely and makes the two arms comparable
against identical input, exactly as the plan asked. Each JPEG is decoded
once via cv2.imread() into a BGR ndarray, the same shape
HttpVisionDetector.__call__() expects from a live Frame - it re-encodes to
JPEG internally before POSTing, same as it would for a frame straight off
the camera, so this measures the real client code path end to end, not a
shortcut around it.

Never touches the camera, GStreamer, Docker, or SAFE_MODE/HOME_TEST_MODE
env state - pure HTTP client timing plus local file reads. Runs on the bare
board host directly (confirmed importable there: perception/detector.py's
only non-stdlib import, cv2, is function-local, exactly like
perception/camera.py's own discipline).

Status: written 7 Sept 2026, pending its first hardware run.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

# Puts device/mpu on sys.path so `from perception.detector import ...`
# resolves the same way it does under pytest (pyproject.toml's
# pythonpath = ["."]). Same shim every other bench script here uses.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402 (after sys.path setup, deliberately) - board/host-only, never imported by pytest

from perception.detector import DetectionError, HttpVisionDetector  # noqa: E402
from services import config  # noqa: E402

_DEFAULT_OUT_DIR = Path(__file__).resolve().parent / "output" / "poll_latency"

# Comfortably above the plan's "≥30 polls per arm" floor while staying well
# under what a 150-frame real encounter directory can serve without reusing
# the same handful of frames too often.
_DEFAULT_POLLS_PER_ARM = 40


def _load_encounter_frames(encounter_dir: Path) -> list:
    """Decode every JPEG in one HOME_TEST_MODE encounter dir, sorted by name.

    Sorted by filename, which is itself timestamp-prefixed
    (services/home_test.py's ring-frame naming) - so frame order here
    matches capture order, in case that ever matters for a future variant
    of this script.
    """
    paths = sorted(encounter_dir.glob("*.jpg"))
    if not paths:
        raise SystemExit(f"no .jpg frames found under {encounter_dir}")
    frames = []
    for path in paths:
        image = cv2.imread(str(path))
        if image is None:
            continue  # corrupt/truncated frame - skip rather than abort a whole run
        frames.append(image)
    if not frames:
        raise SystemExit(f"found {len(paths)} .jpg files under {encounter_dir}, none decodable")
    return frames


def _run_arm(
    detector: HttpVisionDetector,
    frames: list,
    frame_count: int,
    num_polls: int,
) -> list[float]:
    """Time num_polls real detector() calls, each fed frame_count real frames.

    Cycles through the available frames rather than reusing the same
    handful repeatedly, so encode size/content varies poll to poll the same
    way it would against a real ring buffer. A poll whose detector() call
    raises (e.g. a transient runner hiccup) is logged and excluded from the
    latency sample rather than aborting the whole arm - matches
    HttpVisionDetector's own never-let-one-bad-frame-stop-everything
    discipline one level up.
    """
    latencies_s: list[float] = []
    cursor = 0
    for poll in range(num_polls):
        images = [frames[(cursor + k) % len(frames)] for k in range(frame_count)]
        cursor += frame_count
        started = time.perf_counter()
        try:
            detector(images)
        except DetectionError as exc:
            print(f"  poll {poll + 1}/{num_polls}: FAILED ({exc}) - excluded from sample")
            continue
        latencies_s.append(time.perf_counter() - started)
    return latencies_s


def _percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile - no numpy dependency for a 40-sample list."""
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


def main() -> int:
    """Run both arms, report per-poll latency and derived time-to-first-fire."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--encounter-dir",
        required=True,
        help=(
            "A real HOME_TEST_MODE encounter directory full of .jpg ring frames, "
            "e.g. .../data/home_test/encounters/20260906T204347"
        ),
    )
    parser.add_argument("--base-url", default=config.VISION_INFERENCE_URL)
    parser.add_argument("--timeout-s", type=float, default=config.VISION_INFERENCE_TIMEOUT_S)
    parser.add_argument("--polls-per-arm", type=int, default=_DEFAULT_POLLS_PER_ARM)
    parser.add_argument("--out-dir", default=str(_DEFAULT_OUT_DIR))
    args = parser.parse_args()

    encounter_dir = Path(args.encounter_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading real frames from {encounter_dir} ...")
    frames = _load_encounter_frames(encounter_dir)
    print(f"Decoded {len(frames)} usable frames.\n")

    detector = HttpVisionDetector(args.base_url, args.timeout_s)

    today_frame_count = config.HOME_TEST_INFERENCE_FRAME_COUNT
    today_consecutive = config.HOME_TEST_FIRE_CONSECUTIVE_POLLS
    proposed_frame_count = 1
    proposed_consecutive = 2

    results: dict[str, dict] = {}
    for label, frame_count in (
        (f"today (frame_count={today_frame_count})", today_frame_count),
        (f"proposed (frame_count={proposed_frame_count})", proposed_frame_count),
    ):
        print(f"--- {label}, {args.polls_per_arm} polls ---")
        latencies_s = _run_arm(detector, frames, frame_count, args.polls_per_arm)
        if not latencies_s:
            print("  every poll failed - skipping this arm's stats.\n")
            results[label] = {
                "frame_count": frame_count,
                "polls_ok": 0,
                "polls_failed": args.polls_per_arm,
            }
            continue
        p50 = _percentile(latencies_s, 50)
        p95 = _percentile(latencies_s, 95)
        mean = statistics.mean(latencies_s)
        print(
            f"  polls_ok={len(latencies_s)}/{args.polls_per_arm}  "
            f"mean={mean * 1000:.1f}ms  p50={p50 * 1000:.1f}ms  p95={p95 * 1000:.1f}ms\n"
        )
        results[label] = {
            "frame_count": frame_count,
            "polls_ok": len(latencies_s),
            "polls_failed": args.polls_per_arm - len(latencies_s),
            "mean_s": mean,
            "p50_s": p50,
            "p95_s": p95,
            "raw_s": latencies_s,
        }

    print("--- derived time-to-first-fire ---")
    today_key = f"today (frame_count={today_frame_count})"
    proposed_key = f"proposed (frame_count={proposed_frame_count})"
    interval_floor_s = config.HOME_TEST_INFERENCE_INTERVAL_S

    for key, consecutive, label in (
        (today_key, today_consecutive, "today (3, 3)"),
        (proposed_key, proposed_consecutive, "proposed (1, 2)"),
    ):
        arm = results.get(key)
        if not arm or "p50_s" not in arm:
            print(f"  {label}: no data (arm failed)")
            continue
        per_poll_p50 = max(interval_floor_s, arm["p50_s"])
        per_poll_p95 = max(interval_floor_s, arm["p95_s"])
        print(
            f"  {label}: {consecutive} polls x max(floor {interval_floor_s:.1f}s, "
            f"poll latency) -> p50 est. {consecutive * per_poll_p50:.2f}s, "
            f"p95 est. {consecutive * per_poll_p95:.2f}s"
        )
        arm["derived_time_to_first_fire_p50_s"] = consecutive * per_poll_p50
        arm["derived_time_to_first_fire_p95_s"] = consecutive * per_poll_p95
        arm["consecutive_polls"] = consecutive

    out_path = out_dir / f"poll_latency_{int(time.time())}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "encounter_dir": str(encounter_dir),
                "frames_used": len(frames),
                "base_url": args.base_url,
                "interval_floor_s": interval_floor_s,
                "results": results,
            },
            f,
            indent=2,
        )
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
