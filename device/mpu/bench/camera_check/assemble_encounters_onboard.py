"""Assemble HOME_TEST_MODE encounter JPEG bursts into MP4 clips, on the board.

Board-side counterpart to scripts/assemble_encounter.py (that one is laptop-side
and needs the JPEGs copied off the board first, plus an `ffmpeg` binary on
PATH). This one runs where the frames already are - inside the running app
container, which already ships opencv (cv2) with its own bundled FFmpeg
codec support, so no extra install and no `ffmpeg` binary needed.

Two clips come out of each encounter, mirroring the laptop-side script's
convention: a clean clip (raw frames, no overlay - the one that goes in
front of anyone external) and an annotated clip (detection boxes + label +
confidence burned in, sourced from the run's own detections.jsonl - red at
or above the live fire threshold, amber down to 0.3, green below that - the
QA copy that visually proves the system saw what it fired on). The annotated
clip also carries a red DETERRENT FIRING banner across the frames where the
horn/LED actually fired, taken from a timestamped fire-events log (see
FIRE_LOG_PATH) - distinct from the red boxes, which only mean "would have
cleared the fire bar". Both overlays are best-effort and additive: a
missing/unreadable detections.jsonl skips the annotated clip, a missing
fire-events log just drops the banner, neither blocks the clean clip.

Deliberately a standalone script, not imported by main.py/reflex_loop.py/
home_test.py and not run inside the long-lived app process - it only ever
reads finished encounter directories and writes new clip files next to them.
It never touches the live detection/deterrence loop, never opens the camera,
and never restarts anything. Invoke via:

    docker exec eletect-x-main-1 python3 /app/bench/camera_check/assemble_encounters_onboard.py

Encounter frames are full 1080p, and a single encounter can be 500-2000+
frames (measured on this board: up to ~2300) - encoding all of them at full
resolution with an unconstrained bitrate produced ~130 KB/frame (measured
09 Sep), which would have blown the board's ~3 GB of free disk after a
handful of clips. RESIZE_WIDTH and FRAME_STRIDE below trade fidelity for
disk headroom: downscaling and subsampling both cut output size roughly
linearly, and combined keep a clip for even the largest observed encounter
under MAX_CLIP_MB. This is meant to produce a clip good enough to identify
species and confirm the deterrent fired, not an evidentiary-quality archive
- the original full-res JPEGs are left untouched in place for that.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("assemble_encounters_onboard")

ENCOUNTERS_DIR = Path("/app/python/data/home_test/encounters")
DETECTIONS_PATH = Path("/app/python/data/home_test/detections.jsonl")
# Timestamped capture of the app's own fire lines, kept on the bind mount by
# a host cron tap (`docker logs -t ... | grep >> this file`) so it survives
# container recreate and power cycles - the running app itself logs these to
# stdout only, with no timestamp, so `docker logs` is the only source and it
# has to be pinned to a file before it rotates or the container is replaced.
FIRE_LOG_PATH = Path("/app/python/data/home_test/fire_events.log")
CLIP_NAME = "clip.mp4"
CLIP_ANNOTATED_NAME = "clip_annotated.mp4"
FRAME_NAME_RE = re.compile(r"^(?P<wall_s>\d+\.\d+)_\d+\.jpg$")

# App log lines that mark a deterrent actually firing (not just a detection
# clearing the confidence bar). horn+LED+IR for one trigger are logged
# within ~1s of each other - see reflex_loop.handle_footfall_event's
# fire-and-join - and are collapsed to one instant below.
FIRE_EVENT_RE = re.compile(
    r"drive_horn ack=True|drive_led ack=True|pulse_ir ack=True"
    r"|home_test: encounter started|re-firing \(fire "
)
# `docker logs -t` prefixes each line with an RFC3339Nano UTC timestamp then
# a space. A line without one (a plain `docker logs` capture, no -t) can't
# be placed on the clip timeline and is skipped.
DOCKER_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)\s")
# Hold the red banner this long after each fire instant. The horn burst is
# ~2s (PROTOCOL_DURATION_MS_MAX); a little longer keeps it legible at the
# clip's reduced fps.
FIRE_BANNER_HOLD_S = 3.0
# Fire lines closer together than this are one trigger, one banner window.
FIRE_EVENT_CLUSTER_S = 3.0

# Mirrors services/config.py's HOME_TEST_FIRE_MIN_CONFIDENCE (confirmed live
# on this board 09 Sep) so the annotated clip's red boxes mean exactly "this
# detection would have cleared the fire bar" - not a separately-tuned number
# that could quietly drift from the real gate.
FIRE_THRESHOLD = 0.20
AMBER_THRESHOLD = 0.3
# Match a frame to detections within +/- this many seconds - the nearest
# poll(s), not the whole run. Mirrors scripts/assemble_encounter.py.
OVERLAY_WINDOW_S = 0.6

# Keep any one clip well under this so a handful of large encounters can
# never exhaust the board's disk between overnight runs of this script.
MAX_CLIP_MB = 40
RESIZE_WIDTH = 640
# A directory still receiving new frames must never be encoded mid-write -
# only touch one whose newest frame is at least this old.
MIN_QUIET_S = 30.0
# Free-space floor: refuse to start a new clip once headroom drops below
# this, rather than risk filling the rootfs the live app also writes to.
MIN_FREE_MB = 400


def _parse_wall_s(path: str) -> float | None:
    """Extract the leading wall-clock timestamp from a ring/encounter frame name."""
    match = FRAME_NAME_RE.match(os.path.basename(path))
    return float(match.group("wall_s")) if match else None


def _measure_fps(frame_paths: list[str]) -> float:
    """Mean fps implied by the span between the first and last frame's timestamps."""
    timestamps = sorted(t for t in (_parse_wall_s(p) for p in frame_paths) if t is not None)
    if len(timestamps) < 2:
        return 1.0
    span_s = timestamps[-1] - timestamps[0]
    if span_s <= 0:
        return 1.0
    return (len(timestamps) - 1) / span_s


def _free_mb(path: Path) -> float:
    """Free space on the filesystem holding path, in megabytes."""
    usage = shutil.disk_usage(path)
    return usage.free / (1024 * 1024)


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


def _rfc3339_to_epoch(ts: str) -> float:
    """'2026-09-13T04:32:11.123456789Z' -> epoch seconds (UTC).

    datetime.fromisoformat rejects a 9-digit fractional part on Python < 3.11
    and a bare trailing 'Z' on < 3.11, so both are normalised first. The
    board runs UTC (no RTC), which is the same clock the frame filenames'
    wall_s comes from, so this and _parse_wall_s land on one timeline.
    """
    ts = ts.rstrip("Z")
    if "." in ts:
        head, frac = ts.split(".", 1)
        ts = f"{head}.{frac[:6]}"
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc).timestamp()


def load_fire_events(fire_log_path: Path) -> list[float]:
    """Parse deterrent-fire instants (epoch seconds) from a `docker logs -t` capture.

    Only lines that both carry a leading RFC3339 timestamp and match
    FIRE_EVENT_RE count. Exact-duplicate lines (the host cron tap re-reads an
    overlapping `--since` window every run) are dropped, and events within
    FIRE_EVENT_CLUSTER_S of each other are collapsed to one instant so a
    single horn+LED+IR trigger draws one banner window, not three.
    """
    seen: set[str] = set()
    stamped: list[float] = []
    untimed = 0
    with fire_log_path.open("r", encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")
            if not FIRE_EVENT_RE.search(line):
                continue
            if line in seen:
                continue
            seen.add(line)
            match = DOCKER_TS_RE.match(line)
            if not match:
                untimed += 1
                continue
            try:
                stamped.append(_rfc3339_to_epoch(match.group(1)))
            except ValueError:
                untimed += 1
    if untimed:
        logger.warning(
            "%d fire-log line(s) had no usable leading timestamp (captured without "
            "`docker logs -t`?) - those cannot be placed on the clip timeline",
            untimed,
        )
    stamped.sort()
    clustered: list[float] = []
    for t in stamped:
        if not clustered or t - clustered[-1] > FIRE_EVENT_CLUSTER_S:
            clustered.append(t)
    return clustered


def _detections_for_span(detections: list[dict], start_s: float, end_s: float) -> list[dict]:
    """Slice detections.jsonl down to one encounter's frame timespan (+ overlay window)."""
    lo, hi = start_s - OVERLAY_WINDOW_S, end_s + OVERLAY_WINDOW_S
    return [d for d in detections if lo <= d["wall_s"] <= hi]


def boxes_for_frame(frame_wall_s: float, detections: list[dict]) -> list[dict]:
    """Detections within OVERLAY_WINDOW_S of frame_wall_s - the nearest poll(s)."""
    return [d for d in detections if abs(d["wall_s"] - frame_wall_s) <= OVERLAY_WINDOW_S]


def _draw_boxes(img, wall_s: float | None, detections: list[dict]) -> None:
    """Burn in detection boxes + label + confidence for one frame, in place.

    Colour matches scripts/assemble_encounter.py: red at/above FIRE_THRESHOLD
    (would fire), amber down to AMBER_THRESHOLD (seen, below the fire floor),
    green below that.
    """
    if wall_s is None:
        return
    for d in boxes_for_frame(wall_s, detections):
        x, y = int(d.get("x", 0)), int(d.get("y", 0))
        w, h = int(d.get("width", 0)), int(d.get("height", 0))
        conf = float(d.get("confidence", 0.0))
        label = d.get("label", "?")
        if conf >= FIRE_THRESHOLD:
            color = (0, 0, 255)
        elif conf >= AMBER_THRESHOLD:
            color = (0, 200, 255)
        else:
            color = (0, 200, 0)
        cv2.rectangle(img, (x, y), (x + w, y + h), color, 4)
        text = f"{label} {conf:.2f}"
        ty = max(20, y - 10)
        cv2.putText(img, text, (x + 4, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2, cv2.LINE_AA)


def _draw_fire_banner(img, wall_s: float | None, fire_times: list[float]) -> None:
    """Burn a red 'DETERRENT FIRING' bar across the top of the frame, in place.

    Only for frames whose timestamp is within FIRE_BANNER_HOLD_S after a
    logged fire instant, so the annotated clip shows the 'fires the
    deterrents' beat at the exact frames the horn/LED actually fired -
    distinct from the red detection boxes, which only mean 'would have
    cleared the fire bar'. Drawn at source resolution, before the resize in
    _encode_attempt, same as _draw_boxes.
    """
    if wall_s is None or not fire_times:
        return
    if not any(0.0 <= wall_s - ft <= FIRE_BANNER_HOLD_S for ft in fire_times):
        return
    h, w = img.shape[:2]
    bar_h = max(28, h // 12)
    cv2.rectangle(img, (0, 0), (w, bar_h), (0, 0, 255), -1)
    text = "DETERRENT FIRING"
    scale = max(0.6, w / 900.0)
    thick = max(2, int(round(scale * 2)))
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
    tx = max(8, (w - tw) // 2)
    ty = (bar_h + th) // 2
    cv2.putText(
        img, text, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), thick, cv2.LINE_AA
    )


# (width, stride) pairs tried in order until the encoded clip fits under
# MAX_CLIP_MB. Bitrate for mp4v without an explicit target varies a lot more
# with scene content than with frame count alone - measured 4 KB/frame on
# one busy night clip and 87 MB (way over cap) on the very first real
# directory tried, same RESIZE_WIDTH - so this checks the actual encoded
# size and retries smaller rather than trusting a single size estimate.
_ENCODE_ATTEMPTS = ((640, 1), (480, 1), (480, 2), (360, 2), (360, 4))

# mp4v (MPEG-4 Part 2, MPEG-4 container) written through OpenCV's bundled
# FFmpeg backend, which MUST be selected explicitly with the cv2.CAP_FFMPEG
# apiPreference below. Left to choose, this OpenCV build (4.13.0, both FFMPEG
# and GStreamer enabled) routes an .mp4/mp4v writer to GStreamer instead,
# and this container's GStreamer has no MPEG-4 encoder plugin - the writer
# still reports isOpened()==True, then every write() silently fails and a
# 0-byte file is produced (observed 10 Sep: "assembled clip.mp4 ... 0.0 MB").
# avc1/H.264 is worse still: it resolves to the SoC's single-instance
# hardware v4l2h264enc via GStreamer and deadlocks in pipeline teardown when
# driven from here while the live app holds the camera (a run wedged 28 min,
# all threads in futex_wait, blocking the systemd timer from re-firing).
# With CAP_FFMPEG forced, mp4v encodes 500+ 640px frames in a few seconds on
# the otherwise-idle CPU and every target player (VLC, the field laptop)
# reads it. If a true H.264 clip is ever needed, transcode off-board.
_FOURCC = "mp4v"

# A finished clip smaller than this is treated as a failed encode, not a
# success - see the 0-byte-file failure mode described above. Real clips at
# RESIZE_WIDTH run ~10-15 KB/frame; anything under this could not hold even
# a few seconds of real video.
_MIN_VALID_CLIP_BYTES = 64 * 1024


def _encode_attempt(
    frame_paths: list[str],
    tmp_path: Path,
    width: int,
    stride: int,
    fps: float,
    detections: list[dict] | None,
    fire_times: list[float] | None = None,
) -> int | None:
    """Encode frame_paths at the given width/stride into tmp_path; return byte size or None.

    Boxes (when detections is not None) and the DETERRENT FIRING banner (when
    fire_times is given) are drawn at full source resolution, before the
    resize below, so the burned-in coordinates from detections.jsonl
    (native-resolution pixels) land in the right place.
    """
    selected = frame_paths[::stride]
    effective_fps = max(fps / stride, 1.0)

    first_img = cv2.imread(selected[0])
    if first_img is None:
        return None
    src_h, src_w = first_img.shape[:2]
    scale = min(1.0, width / src_w)
    out_w = int(round(src_w * scale / 2) * 2)
    out_h = int(round(src_h * scale / 2) * 2)

    fourcc = cv2.VideoWriter_fourcc(*_FOURCC)
    writer = cv2.VideoWriter(str(tmp_path), cv2.CAP_FFMPEG, fourcc, effective_fps, (out_w, out_h))
    if not writer.isOpened():
        logger.warning("VideoWriter would not open (%dx%d @ %.2ffps)", out_w, out_h, effective_fps)
        return None

    written = 0
    for frame_path in selected:
        img = cv2.imread(frame_path)
        if img is None:
            continue
        if detections is not None:
            frame_wall_s = _parse_wall_s(frame_path)
            _draw_boxes(img, frame_wall_s, detections)
            if fire_times:
                _draw_fire_banner(img, frame_wall_s, fire_times)
        if (out_w, out_h) != (src_w, src_h):
            img = cv2.resize(img, (out_w, out_h), interpolation=cv2.INTER_AREA)
        writer.write(img)
        written += 1
    writer.release()

    if written == 0:
        tmp_path.unlink(missing_ok=True)
        return None

    size = tmp_path.stat().st_size if tmp_path.exists() else 0
    if size < _MIN_VALID_CLIP_BYTES:
        logger.warning(
            "encode produced only %d bytes for %d frames (%dx%d) - treating as a failed "
            "encode, not a clip", size, written, out_w, out_h,
        )
        tmp_path.unlink(missing_ok=True)
        return None
    if not _clip_reads_back(tmp_path, written):
        logger.warning("encoded file at %s does not read back as video - discarding", tmp_path)
        tmp_path.unlink(missing_ok=True)
        return None
    return size


def _clip_reads_back(path: Path, written: int) -> bool:
    """Re-open an encoded clip and confirm it decodes to a plausible frame count.

    Guards against a writer that accepted every frame without error but
    emitted an unplayable container (the silent-failure mode that shipped a
    0-byte clip.mp4 on 10 Sept). A lenient bar - half the frames handed in -
    is enough to tell "real video" from "broken muxer".
    """
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            return False
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        ok, _ = cap.read()
        return ok and count >= max(1, written // 2)
    finally:
        cap.release()


def _build_clip(
    encounter_dir: Path,
    clip_path: Path,
    frame_paths: list[str],
    fps: float,
    detections: list[dict] | None,
    fire_times: list[float] | None = None,
) -> bool:
    """Run the size-capped retry ladder for one clip (clean or annotated).

    A dedicated best_path holds the current best-so-far attempt across the
    retry loop, distinct from the per-attempt scratch tmp_path, so the
    smallest-seen attempt survives even when every width/stride combination
    stays over MAX_CLIP_MB.
    """
    # Both scratch names keep clip_path's real ".mp4" suffix. OpenCV's FFmpeg
    # backend picks the output muxer from the filename extension alone; a bare
    # ".part"/".best" tail makes cv2.VideoWriter fail to open (isOpened() is
    # False, no encode happens) - observed 10 Sept after CAP_FFMPEG was forced.
    tmp_path = clip_path.with_suffix(".part" + clip_path.suffix)
    best_path = clip_path.with_suffix(".best" + clip_path.suffix)
    max_bytes = MAX_CLIP_MB * 1024 * 1024
    best_size: int | None = None
    best_attempt: tuple[int, int] | None = None
    fit_under_cap = False

    for width, stride in _ENCODE_ATTEMPTS:
        if _free_mb(encounter_dir) < MIN_FREE_MB:
            logger.warning(
                "abort mid-attempt: free space below %d MB, %s", MIN_FREE_MB, clip_path
            )
            tmp_path.unlink(missing_ok=True)
            best_path.unlink(missing_ok=True)
            return False
        size = _encode_attempt(
            frame_paths, tmp_path, width, stride, fps, detections, fire_times
        )
        if size is None:
            continue
        if size <= max_bytes:
            best_size, best_attempt, fit_under_cap = size, (width, stride), True
            best_path.unlink(missing_ok=True)
            tmp_path.replace(best_path)
            break
        # Over budget: keep this attempt only if it's the smallest seen so
        # far, in case every width/stride combination stays over cap.
        if best_size is None or size < best_size:
            best_path.unlink(missing_ok=True)
            tmp_path.replace(best_path)
            best_size, best_attempt = size, (width, stride)
        else:
            tmp_path.unlink(missing_ok=True)

    if best_size is None:
        best_path.unlink(missing_ok=True)
        logger.warning("skip %s: no encode attempt produced output", clip_path)
        return False

    if not fit_under_cap:
        logger.warning(
            "%s exceeds MAX_CLIP_MB (%d MB) even at the smallest attempt %s - keeping it anyway",
            clip_path, MAX_CLIP_MB, best_attempt,
        )

    # replace(), not rename(): a --rebuild-annotated run has an existing
    # clip_path to overwrite, and rename() refuses that on some platforms.
    best_path.replace(clip_path)
    size_mb = best_size / (1024 * 1024)
    width, stride = best_attempt
    logger.info("assembled %s: width=%d stride=%d, %.1f MB", clip_path, width, stride, size_mb)
    return True


def _clip_present_and_sane(clip_path: Path) -> bool:
    """True only if the clip file exists and is at least _MIN_VALID_CLIP_BYTES.

    A 0-byte or truncated clip left by an earlier broken encode (see _FOURCC)
    must not count as "already done" - it has to be rebuilt.
    """
    try:
        return clip_path.stat().st_size >= _MIN_VALID_CLIP_BYTES
    except OSError:
        return False


def assemble_one(
    encounter_dir: Path,
    all_detections: list[dict] | None,
    fire_times: list[float] | None = None,
    rebuild_annotated: bool = False,
) -> bool:
    """Encode one encounter's JPEGs into a clean clip, plus an annotated one.

    The annotated clip (detection boxes/label/confidence burned in, plus a
    red DETERRENT FIRING banner at the frames fire_times marks) is only built
    when detections.jsonl is readable. rebuild_annotated forces the annotated
    clip to be re-encoded even if one is already present - used when a fresh
    fire-events log means an existing banner-less clip is now stale. Returns
    True if at least one clip was produced this call.
    """
    clip_path = encounter_dir / CLIP_NAME
    annotated_path = encounter_dir / CLIP_ANNOTATED_NAME
    need_clean = not _clip_present_and_sane(clip_path)
    need_annotated = all_detections is not None and (
        rebuild_annotated or not _clip_present_and_sane(annotated_path)
    )
    if not need_clean and not need_annotated:
        return False

    newest_mtime = max(
        (p.stat().st_mtime for p in encounter_dir.glob("*.jpg")), default=0.0
    )
    if time.time() - newest_mtime < MIN_QUIET_S:
        logger.info("skip %s: still receiving frames", encounter_dir.name)
        return False

    frame_paths = sorted(str(p) for p in encounter_dir.glob("*.jpg"))
    if not frame_paths:
        logger.info("skip %s: no frames", encounter_dir.name)
        return False

    if _free_mb(encounter_dir) < MIN_FREE_MB:
        logger.warning(
            "abort: free space below %d MB, not starting %s", MIN_FREE_MB, encounter_dir.name
        )
        return False

    fps = _measure_fps(frame_paths)
    produced = False

    if need_clean:
        if _build_clip(encounter_dir, clip_path, frame_paths, fps, detections=None):
            produced = True

    if need_annotated:
        if _free_mb(encounter_dir) < MIN_FREE_MB:
            logger.warning(
                "skip annotated clip for %s: free space below %d MB",
                encounter_dir.name, MIN_FREE_MB,
            )
        else:
            timestamps = [t for t in (_parse_wall_s(p) for p in frame_paths) if t is not None]
            dir_detections = (
                _detections_for_span(all_detections, min(timestamps), max(timestamps))
                if timestamps
                else []
            )
            dir_fire_times = (
                [
                    t
                    for t in (fire_times or [])
                    if min(timestamps) - FIRE_BANNER_HOLD_S <= t <= max(timestamps)
                ]
                if timestamps
                else []
            )
            if _build_clip(
                encounter_dir,
                annotated_path,
                frame_paths,
                fps,
                detections=dir_detections,
                fire_times=dir_fire_times,
            ):
                produced = True

    return produced


def main(argv: list[str] | None = None) -> int:
    """Assemble encounter directories missing either clip.

    --limit caps how many directories one invocation will touch, so a
    periodic timer (see the systemd unit deployed alongside this script) can
    pick up new encounters in small batches through the night rather than
    one process trying to walk the whole backlog in a single long-running
    call.
    """
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument(
        "--limit", type=int, default=None, help="stop after processing this many directories"
    )
    parser.add_argument(
        "--fire-log",
        default=str(FIRE_LOG_PATH),
        help="timestamped `docker logs -t` fire capture for the DETERRENT FIRING banner",
    )
    parser.add_argument(
        "--rebuild-annotated",
        action="store_true",
        help="re-encode the annotated clip even if one exists (picks up a fresh fire-log)",
    )
    args = parser.parse_args(argv)

    if not ENCOUNTERS_DIR.is_dir():
        logger.error("no encounters directory at %s", ENCOUNTERS_DIR)
        return 1

    all_detections: list[dict] | None = None
    if DETECTIONS_PATH.is_file():
        try:
            all_detections = load_detections(DETECTIONS_PATH)
        except OSError:
            logger.exception("failed to read %s - annotated clips will be skipped", DETECTIONS_PATH)
    else:
        logger.info("no detections file at %s - annotated clips will be skipped", DETECTIONS_PATH)

    fire_times: list[float] = []
    fire_log = Path(args.fire_log)
    if fire_log.is_file():
        try:
            fire_times = load_fire_events(fire_log)
            logger.info("fire-events log %s: %d fire instant(s) parsed", fire_log, len(fire_times))
        except OSError:
            logger.exception(
                "failed to read %s - annotated clips will have no DETERRENT FIRING banner", fire_log
            )
    else:
        logger.info(
            "no fire-events log at %s - annotated clips will show detection boxes but no "
            "DETERRENT FIRING banner (populate it with `docker logs -t`)",
            fire_log,
        )

    dirs = sorted(p for p in ENCOUNTERS_DIR.iterdir() if p.is_dir())
    pending = [
        d for d in dirs
        if not _clip_present_and_sane(d / CLIP_NAME)
        or (
            all_detections is not None
            and (args.rebuild_annotated or not _clip_present_and_sane(d / CLIP_ANNOTATED_NAME))
        )
    ]
    logger.info("%d encounter directories, %d with a clip still missing", len(dirs), len(pending))
    processed = 0
    for encounter_dir in pending:
        if args.limit is not None and processed >= args.limit:
            logger.info("limit of %d reached, stopping this run", args.limit)
            break
        try:
            assemble_one(
                encounter_dir, all_detections, fire_times, rebuild_annotated=args.rebuild_annotated
            )
        except Exception:
            logger.exception("failed to assemble %s", encounter_dir.name)
        processed += 1
    logger.info("done: %d director(y/ies) processed this run", processed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
