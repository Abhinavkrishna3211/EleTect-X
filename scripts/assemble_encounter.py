#!/usr/bin/env python3
"""Assemble one HOME_TEST_MODE encounter directory into a playable MP4.

Offline, laptop-side - the board spends its CPU capturing during the test,
not encoding (device/mpu/services/home_test.py's own module docstring).
Input is one directory under device/mpu/services/data/home_test/encounters/
- a flat set of ring-frame JPEGs named "<wall_s:018.6f>_<index:08d>.jpg",
zero-padded so alphabetical order is chronological order, which is what lets
this script read them in the right sequence with no rename pass first. Frames
are fed to ffmpeg via a concat-demuxer file list (explicit paths, one
duration per frame) rather than "-pattern_type glob" - the glob input format
needs libavformat built with glob() support, which Windows ffmpeg builds
(e.g. the Gyan.FFmpeg winget package) do not have ("Function not
implemented"), and the concat list works identically everywhere.

fps is measured from the frames' own filenames (first-to-last wall_s span
divided by frame count), not assumed - device/mpu/bench/camera_check/
fps_probe.py already established that this camera's sustained fps is a real
open question, not a spec value, and an assembled clip's own playback speed
is the wrong place to relearn that. --fps overrides the measurement if a
run's own bench numbers are trusted more.

Two clips come out of one run: a clean one (raw frames, no overlay - this is
the one that goes in front of anyone external, since a mislabelled box baked
into the footage would undercut the exact clip meant to prove the system
works) and an annotated one (detection boxes + label + confidence burned in,
sourced from the run's own detections.jsonl - this is the QA copy, for
catching e.g. a Boar that got called "Elephant" before that clip is ever
shown to anyone). Annotation is best-effort and additive: it never blocks the
clean clip, and missing/unreadable detections just skips it with a warning.

Usage:
    python scripts/assemble_encounter.py \
        device/mpu/services/data/home_test/encounters/20260907T013000
    python scripts/assemble_encounter.py <dir> --fps 12 --output clip.mp4
    python scripts/assemble_encounter.py <dir> --no-annotated
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2

FRAME_NAME_RE = re.compile(r"^(?P<wall_s>\d+\.\d+)_\d+\.jpg$")

# Mirrors scratchpad/live_view_cv2_host.py's colour scheme so the annotated
# clip reads the same way the live monitor did during the test: red is "this
# would actually fire the deterrent", amber is "seen but below the fire
# floor", green is everything weaker still. Kept as a literal default here
# rather than re-parsed out of services/config.py (that trick exists in the
# live viewer because it polls a live, changing file every 200ms - a single
# offline run doesn't need that machinery, --fire-threshold covers it).
DEFAULT_FIRE_THRESHOLD = 0.20


def _parse_wall_s(path: Path) -> float | None:
    """Extract the leading wall-clock timestamp from a ring/encounter frame name."""
    match = FRAME_NAME_RE.match(path.name)
    return float(match.group("wall_s")) if match else None


def measure_fps(frame_paths: list[Path]) -> float:
    """Mean fps implied by the span between the first and last frame's timestamps.

    Falls back to 1.0 for a single-frame directory - there is no interval to
    measure, and ffmpeg refuses a framerate of 0.
    """
    timestamps = sorted(t for t in (_parse_wall_s(p) for p in frame_paths) if t is not None)
    if len(timestamps) < 2:
        return 1.0
    span_s = timestamps[-1] - timestamps[0]
    if span_s <= 0:
        return 1.0
    return (len(timestamps) - 1) / span_s


def _run_ffmpeg_concat(frame_paths: list[Path], output_path: Path, effective_fps: float) -> int:
    """Encode frame_paths (already in playback order) to output_path at effective_fps."""
    if shutil.which("ffmpeg") is None:
        print(
            "error: ffmpeg not found on PATH - install it before assembling clips",
            file=sys.stderr,
        )
        return 1

    def concat_file_line(frame_path: Path) -> str:
        # concat demuxer paths: forward slashes and escaped single quotes are
        # the portable form across ffmpeg's Windows and POSIX builds alike.
        escaped = frame_path.resolve().as_posix().replace("'", "'\\''")
        return f"file '{escaped}'"

    frame_duration_s = 1.0 / effective_fps
    concat_lines = []
    for frame_path in frame_paths:
        concat_lines.append(concat_file_line(frame_path))
        concat_lines.append(f"duration {frame_duration_s:.6f}")
    # The concat demuxer ignores the last entry's duration unless one more
    # entry follows it - repeat the final frame so the last image actually
    # holds for frame_duration_s instead of being dropped to zero length.
    concat_lines.append(concat_file_line(frame_paths[-1]))

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as list_file:
        list_file.write("\n".join(concat_lines) + "\n")
        list_path = Path(list_file.name)

    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-fps_mode",
            "vfr",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(output_path.resolve()),
        ]
        print("running:", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            print("ffmpeg failed:", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            return result.returncode
    finally:
        list_path.unlink(missing_ok=True)

    if output_path.exists():
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"done: {output_path} ({size_mb:.1f} MB)")
    return 0


def assemble(
    encounter_dir: Path,
    output_path: Path,
    fps: float | None,
    pattern: str,
) -> int:
    """Build the clean (no-overlay) clip for encounter_dir's frames."""
    frame_paths = sorted(encounter_dir.glob(pattern))
    if not frame_paths:
        print(f"error: no frames matching {pattern!r} in {encounter_dir}", file=sys.stderr)
        return 1

    measured_fps = measure_fps(frame_paths)
    effective_fps = fps if fps is not None else measured_fps
    first_ts = _parse_wall_s(frame_paths[0])
    last_ts = _parse_wall_s(frame_paths[-1])
    duration_s = (last_ts - first_ts) if (first_ts is not None and last_ts is not None) else None

    print(f"encounter dir:   {encounter_dir}")
    print(f"frames found:    {len(frame_paths)}")
    if duration_s is not None:
        print(f"wall-clock span: {duration_s:.1f}s")
    print(f"measured fps:    {measured_fps:.2f}")
    print(f"using fps:       {effective_fps:.2f}" + (" (override)" if fps is not None else ""))
    print(f"output:          {output_path}")

    return _run_ffmpeg_concat(frame_paths, output_path, effective_fps)


def load_detections(detections_path: Path) -> list[dict]:
    """Parse a detections.jsonl file, skipping lines that don't parse or lack wall_s."""
    detections: list[dict] = []
    with detections_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if "wall_s" in record:
                detections.append(record)
    return detections


def boxes_for_frame(frame_wall_s: float, detections: list[dict], window_s: float) -> list[dict]:
    """Detections within window_s of frame_wall_s - the nearest poll(s), not the whole run."""
    return [d for d in detections if abs(d["wall_s"] - frame_wall_s) <= window_s]


def annotate_frames(
    frame_paths: list[Path],
    detections: list[dict],
    dst_dir: Path,
    threshold: float,
    window_s: float,
) -> list[Path]:
    """Write a copy of each frame with matching detection boxes burned in; return the copies.

    Colour matches scratchpad/live_view_cv2_host.py: red at/above threshold (would fire),
    amber down to 0.3 (seen, below the fire floor), green below that.
    """
    annotated_paths: list[Path] = []
    for frame_path in frame_paths:
        wall_s = _parse_wall_s(frame_path)
        dst_path = dst_dir / frame_path.name
        img = cv2.imread(str(frame_path))
        if img is None or wall_s is None:
            shutil.copyfile(frame_path, dst_path)
            annotated_paths.append(dst_path)
            continue
        for d in boxes_for_frame(wall_s, detections, window_s):
            x, y = int(d.get("x", 0)), int(d.get("y", 0))
            w, h = int(d.get("width", 0)), int(d.get("height", 0))
            conf = float(d.get("confidence", 0.0))
            label = d.get("label", "?")
            if conf >= threshold:
                color = (0, 0, 255)
            elif conf >= 0.3:
                color = (0, 200, 255)
            else:
                color = (0, 200, 0)
            cv2.rectangle(img, (x, y), (x + w, y + h), color, 4)
            text = f"{label} {conf:.2f}"
            ty = max(20, y - 10)
            cv2.putText(img, text, (x + 4, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2, cv2.LINE_AA)
        cv2.imwrite(str(dst_path), img)
        annotated_paths.append(dst_path)
    return annotated_paths


def assemble_annotated(
    encounter_dir: Path,
    output_path: Path,
    fps: float | None,
    pattern: str,
    detections_path: Path,
    threshold: float,
    window_s: float,
) -> int:
    """Build the QA clip: same frames, with detection boxes burned in from detections_path."""
    frame_paths = sorted(encounter_dir.glob(pattern))
    if not frame_paths:
        print(f"error: no frames matching {pattern!r} in {encounter_dir}", file=sys.stderr)
        return 1

    detections = load_detections(detections_path)
    print(f"detections file: {detections_path} ({len(detections)} records)")
    print(f"fire threshold:  {threshold:.2f}  overlay window: +/-{window_s:.2f}s")

    measured_fps = measure_fps(frame_paths)
    effective_fps = fps if fps is not None else measured_fps
    print(f"output:          {output_path}")

    with tempfile.TemporaryDirectory(prefix="eletect_annotate_") as tmp:
        annotated_paths = annotate_frames(
            frame_paths, detections, Path(tmp), threshold, window_s
        )
        return _run_ffmpeg_concat(annotated_paths, output_path, effective_fps)


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("encounter_dir", type=Path, help="one encounter directory of ring JPEGs")
    parser.add_argument(
        "--fps",
        type=float,
        default=None,
        help="override the fps measured from frame timestamps",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="output MP4 path (default: <encounter_dir>/clip.mp4)",
    )
    parser.add_argument(
        "--pattern",
        default="*.jpg",
        help="glob pattern for frames within encounter_dir (default: *.jpg)",
    )
    parser.add_argument(
        "--no-annotated",
        action="store_true",
        help="skip the boxes-burned-in QA clip; produce only the clean one",
    )
    parser.add_argument(
        "--annotated-output",
        type=Path,
        default=None,
        help="annotated MP4 path (default: <encounter_dir>/clip_annotated.mp4)",
    )
    parser.add_argument(
        "--detections",
        type=Path,
        default=None,
        help=(
            "path to the run's detections.jsonl (default: auto-detected as "
            "<encounter_dir>/../../detections.jsonl, i.e. the home_test dir "
            "the encounters/ folder lives under)"
        ),
    )
    parser.add_argument(
        "--fire-threshold",
        type=float,
        default=DEFAULT_FIRE_THRESHOLD,
        help=f"confidence at/above which a box is drawn red (default: {DEFAULT_FIRE_THRESHOLD})",
    )
    parser.add_argument(
        "--overlay-window-s",
        type=float,
        default=0.6,
        help="match a frame to detections within +/- this many seconds (default: 0.6)",
    )
    args = parser.parse_args()

    if not args.encounter_dir.is_dir():
        print(f"error: not a directory: {args.encounter_dir}", file=sys.stderr)
        return 1

    output_path = args.output if args.output is not None else args.encounter_dir / "clip.mp4"
    clean_result = assemble(args.encounter_dir, output_path, args.fps, args.pattern)
    if clean_result != 0:
        return clean_result

    if args.no_annotated:
        return 0

    detections_path = args.detections
    if detections_path is None:
        detections_path = args.encounter_dir.parent.parent / "detections.jsonl"
    if not detections_path.is_file():
        print(
            f"note: no detections file at {detections_path} - skipping the annotated "
            "clip (pass --detections to point at one, or --no-annotated to silence this)",
            file=sys.stderr,
        )
        return 0

    annotated_output = (
        args.annotated_output
        if args.annotated_output is not None
        else args.encounter_dir / "clip_annotated.mp4"
    )
    print()
    return assemble_annotated(
        args.encounter_dir,
        annotated_output,
        args.fps,
        args.pattern,
        detections_path,
        args.fire_threshold,
        args.overlay_window_s,
    )


if __name__ == "__main__":
    raise SystemExit(main())
