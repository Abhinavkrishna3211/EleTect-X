"""Persists one deterrent event's evidence to local disk (CONTEXT.md 4).

Two kinds of evidence, one naming scheme. `save_burst` writes the JPEG
frame burst that has existed since 18 Aug; `commit_video` / `discard_video`
/ `clear_orphaned_scratch` implement ADR 0020's event-video lifecycle,
where a recording is written to a scratch path first and only moved into
the permanent capture directory once the event is confirmed. Both use
`_event_prefix`, so a confirmed event's clip and its burst sort next to
each other in a directory listing without any sidecar index.

Companion to perception/camera.py, same importability discipline: this
module must stay importable with no OpenCV installed and no camera attached
(device/mpu/README.md's host-test harness) - `cv2` is imported only inside
`save_burst`, never at module scope. services/reflex_loop.py never calls
`save_burst` directly either; it takes a `save_frames`-shaped callable as an
injected dependency (same seam as `drive_horn`), so
tests/test_reflex_loop.py can assert a burst was "saved" via a recording
fake with no disk or cv2 involved. device/mpu/main.py is the only place that
wires this real implementation in.

**Nothing here ever deletes a committed capture.** ADR 0020 Decision C is
explicit: confirmed footage is the deliverable, and freeing space by
deleting any of it is not an option this module gets to take.
`CAPTURE_LOW_DISK_HEADROOM_BYTES` is a monitoring threshold that logs and
nothing more - `_warn_if_low_disk` has no branch that removes anything, and
must not grow one. The only deletions in this file are of scratch files
that never became a capture: a discarded (unconfirmed) recording, and
orphaned scratch left behind by a crash mid-record.
"""

from __future__ import annotations

import itertools
import logging
import os
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from perception.camera import Frame
from services import config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CaptureEventTag:
    """Identifying info for the event that triggered one saved frame burst.

    Attributes:
        event_timestamp_s: `time.time()` (wall clock) at the moment the
            triggering alert decision was made - used to build a
            filesystem-sortable, unique-per-event filename prefix.
            Deliberately wall clock, unlike Frame.timestamp_s's
            time.monotonic() - a saved filename needs to mean something
            outside this one process's uptime.
        sta_lta_ratio: The MCU-reported STA/LTA ratio at trigger.
        fused_probability: cognition.fusion.fuse()'s output probability for
            this event.
        alert: Whether cognition.decision.decide() raised an alert for
            this event. Always True for a burst that reached
            save_burst(), which only runs on the alert path - but not
            always True for commit_video(), whose keep-gate is "vision
            confirmed OR alert fired" (ADR 0020), so a clip named
            `..._alert0` is a real, expected case: the camera saw an
            elephant that fusion did not clear the threshold for. Carried
            in the filename either way so a saved capture is
            self-describing without cross-referencing the log line.
    """

    event_timestamp_s: float
    sta_lta_ratio: float
    fused_probability: float
    alert: bool


def _event_prefix(tag: CaptureEventTag) -> str:
    """Build a sortable, collision-resistant filename prefix from a tag."""
    return (
        f"{tag.event_timestamp_s:.3f}_sta{tag.sta_lta_ratio:.2f}"
        f"_p{tag.fused_probability:.3f}_alert{int(tag.alert)}"
    )


def _warn_if_low_disk(out_dir: Path) -> None:
    """Log a clear warning if free space at out_dir is running low.

    Never raises - a failed disk_usage() read (e.g. an exotic filesystem) is
    logged and treated as "couldn't check," not a save failure, matching
    this module's own "never fail silently, never block on a check" stance.
    """
    try:
        free_bytes = shutil.disk_usage(out_dir).free
    except OSError as exc:
        logger.warning("capture storage: could not check free space at %s: %s", out_dir, exc)
        return
    if free_bytes < config.CAPTURE_LOW_DISK_HEADROOM_BYTES:
        logger.warning(
            "capture storage LOW: %.1f MB free at %s (floor %.1f MB) - "
            "frames are still being written, but this needs attention soon",
            free_bytes / (1024 * 1024),
            out_dir,
            config.CAPTURE_LOW_DISK_HEADROOM_BYTES / (1024 * 1024),
        )


def save_burst(
    frames: list[Frame],
    tag: CaptureEventTag,
    out_dir: Path = config.CAPTURE_DIR,
) -> list[Path]:
    """Write one captured burst to disk as JPEGs, tagged with the triggering event.

    Never raises: a write failure (full disk, permission fault, encode
    failure) is logged and that frame is skipped, matching
    reflex_loop.py's requirement that a storage fault never crash the event
    handler - by the time this is called, the deterrents have already fired
    (services/reflex_loop.py's own sequencing), so nothing downstream is
    still waiting on this call to succeed.

    Args:
        frames: The burst to persist, in capture order (Frame.index 0..n-1).
        tag: Identifying info for the triggering event - see
            CaptureEventTag.
        out_dir: Directory to write into. Defaults to
            services.config.CAPTURE_DIR; created if missing.

    Returns:
        Paths actually written, in the same order as `frames`. Shorter than
        `frames` if any individual write failed.
    """
    import cv2  # noqa: PLC0415 (deliberately local, see module docstring)

    out_dir.mkdir(parents=True, exist_ok=True)
    _warn_if_low_disk(out_dir)

    prefix = _event_prefix(tag)
    written: list[Path] = []
    for frame in frames:
        path = out_dir / f"{prefix}_frame{frame.index:02d}.jpg"
        try:
            ok = cv2.imwrite(str(path), frame.image)
        except Exception as exc:  # noqa: BLE001 - see docstring: never raises
            logger.warning("capture storage: failed to write %s: %s", path, exc)
            continue
        if not ok:
            logger.warning("capture storage: cv2.imwrite reported failure for %s", path)
            continue
        written.append(path)

    logger.info("capture storage: wrote %d/%d frame(s) to %s", len(written), len(frames), out_dir)
    return written


# ---------------------------------------------------------------------------
# Event-video lifecycle (ADR 0020)
# ---------------------------------------------------------------------------
# A recording is written to EVENT_VIDEO_SCRATCH_DIR while the event is still
# undecided, then either committed into CAPTURE_DIR or deleted. The scratch
# directory is a subdirectory of CAPTURE_DIR on purpose - commit_video()
# finishes with os.replace(), which is only atomic within one filesystem
# (services/config.py's EVENT_VIDEO_SCRATCH_DIR comment has the full
# reasoning, including why the container's /tmp is the wrong choice here).
#
# These three functions are the only place in device/mpu that calls
# os.fsync/os.replace. The durability recipe is deliberate and worth stating
# once: fsync the finished file so its bytes are on the medium, rename it
# into place, then fsync the *directory* so the rename itself is on the
# medium too. Skipping the last step leaves a window where a power cut loses
# the directory entry and the clip becomes unreachable even though its data
# survived - and on this board a power cut is a documented, observed event
# (docs/KNOWN_GAPS.md's 2 Sept brown-out entry), not a theoretical one.


def _fsync_file(path: Path) -> None:
    """Force one finished file's bytes to the storage medium; never raises.

    Opened O_RDWR rather than O_RDONLY purely for portability: this
    function reads and writes nothing, but Windows' underlying _commit()
    requires a handle with write access, and the host-test harness runs
    there (device/mpu/README.md). A failure to fsync is logged and
    swallowed - the commit that follows is still worth attempting, since an
    un-fsynced file that survives is strictly better than no file at all.
    """
    try:
        fd = os.open(path, os.O_RDWR)
    except OSError as exc:
        logger.warning("capture storage: cannot open %s to fsync: %s", path, exc)
        return
    try:
        os.fsync(fd)
    except OSError as exc:
        logger.warning("capture storage: fsync of %s failed: %s", path, exc)
    finally:
        os.close(fd)


def _fsync_directory(path: Path) -> None:
    """Force a directory entry (a rename) to the storage medium; never raises.

    POSIX-only by nature: opening a directory as a file descriptor is not
    supported on Windows, where this is a logged no-op. Acceptable because
    the durability it buys is only needed where power can be cut mid-write,
    which is the board (Linux), never the dev host.
    """
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError as exc:
        logger.debug(
            "capture storage: directory fsync unsupported here for %s (%s) - "
            "expected on non-POSIX hosts, not on the board",
            path,
            exc,
        )
        return
    try:
        os.fsync(fd)
    except OSError as exc:
        logger.debug("capture storage: directory fsync of %s failed: %s", path, exc)
    finally:
        os.close(fd)


# Per-process sequence behind scratch_video_path()'s filenames. next() on
# an itertools.count is already atomic under CPython, but the lock is cheap
# and makes the guarantee explicit rather than dependent on an interpreter
# detail - this is the only thing standing between two overlapping events
# and one shared recording file.
_SCRATCH_SEQUENCE = itertools.count()
_SCRATCH_SEQUENCE_LOCK = threading.Lock()


def scratch_video_path(
    scratch_dir: Path = config.EVENT_VIDEO_SCRATCH_DIR,
    suffix: str = config.EVENT_VIDEO_SUFFIX,
) -> Path:
    """Reserve a unique scratch path for one in-progress recording.

    Creates `scratch_dir` if needed and returns a path inside it. The name
    carries the process id, a monotonic clock reading and a per-process
    sequence number rather than the event tag, because the tag's
    `fused_probability` and `alert` fields do not exist yet at the moment
    recording starts - the whole point of ADR 0020's design is that
    recording begins *before* the event is decided. The permanent,
    tag-derived name is applied later, by commit_video().

    The sequence number is what actually guarantees uniqueness, and the
    clock reading is only there to keep the names sortable and legible when
    a human is looking at leftovers after a crash. Relying on the clock
    alone is not safe: monotonic_ns() has ~15ms resolution on some hosts,
    and the existence check below cannot cover the gap because the returned
    path deliberately does not exist yet - the encoder creates it later. Two
    reservations taken inside one clock tick would otherwise be handed the
    same filename and the second recording would overwrite the first.

    Args:
        scratch_dir: Directory for in-progress recordings. Must be on the
            same filesystem as commit_video()'s `out_dir` - see this
            section's header comment.
        suffix: Container extension, carried through to the committed name.

    Returns:
        A path that does not currently exist, inside `scratch_dir`.

    Raises:
        OSError: If `scratch_dir` cannot be created. Deliberately not
            swallowed, unlike everything else in this module: a caller that
            cannot get a scratch path has nothing to record to, and should
            find that out here rather than at the first write.
    """
    scratch_dir.mkdir(parents=True, exist_ok=True)
    with _SCRATCH_SEQUENCE_LOCK:
        sequence = next(_SCRATCH_SEQUENCE)
    while True:
        candidate = (
            scratch_dir / f"event_{os.getpid()}_{time.monotonic_ns()}_{sequence}{suffix}"
        )
        if not candidate.exists():
            return candidate
        # Only reachable against a leftover from a previous run that happens
        # to collide on all three components. Take the next sequence number
        # rather than spinning on the clock.
        with _SCRATCH_SEQUENCE_LOCK:
            sequence = next(_SCRATCH_SEQUENCE)


def commit_video(
    scratch_path: Path,
    tag: CaptureEventTag,
    out_dir: Path = config.CAPTURE_DIR,
) -> Path | None:
    """Move a finished recording from scratch into the permanent capture dir.

    Never raises - by the time this is called the deterrents have already
    fired and the camera is already closed, so a storage fault here must be
    logged and survived, exactly as `save_burst`'s per-frame failures and
    services/reflex_loop.py's camera failures are.

    Args:
        scratch_path: The closed recording, as returned by
            scratch_video_path() and written by perception/video.py.
        tag: The decided event's metadata, used to build the permanent
            filename via the same `_event_prefix` `save_burst` uses.
        out_dir: Permanent capture directory. Must share a filesystem with
            `scratch_path`'s parent.

    Returns:
        The committed path, or None if there was nothing to commit or the
        move failed. None never means "deleted a confirmed capture" - the
        only thing this function can remove is a zero-byte scratch file,
        which is not footage.
    """
    if not scratch_path.exists():
        logger.warning(
            "capture storage: nothing to commit, scratch recording %s does not exist",
            scratch_path,
        )
        return None

    try:
        size_bytes = scratch_path.stat().st_size
    except OSError as exc:
        logger.warning(
            "capture storage: cannot stat scratch recording %s: %s", scratch_path, exc
        )
        return None

    if size_bytes == 0:
        # An empty container is not footage - the pipeline produced no
        # encoded bytes at all. Committing it would put a file no player
        # can open into the permanent directory and make the event look
        # captured when it was not. Removing it is not an ADR 0020
        # Decision C deletion: nothing was ever captured here to keep.
        logger.warning(
            "capture storage: scratch recording %s is empty, discarding rather than committing",
            scratch_path,
        )
        discard_video(scratch_path)
        return None

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("capture storage: cannot create capture dir %s: %s", out_dir, exc)
        return None

    _warn_if_low_disk(out_dir)

    destination = out_dir / f"{_event_prefix(tag)}{scratch_path.suffix}"
    _fsync_file(scratch_path)
    try:
        os.replace(scratch_path, destination)
    except OSError as exc:
        logger.warning(
            "capture storage: failed to commit %s to %s (left in scratch): %s",
            scratch_path,
            destination,
            exc,
        )
        return None
    _fsync_directory(out_dir)

    logger.info(
        "capture storage: committed event video %s (%.1f MB)",
        destination,
        size_bytes / (1024 * 1024),
    )
    return destination


def discard_video(scratch_path: Path) -> bool:
    """Delete an unconfirmed scratch recording; never raises.

    The common case, not the exceptional one: ADR 0020 bounds the cost of a
    non-elephant trigger (wind, other wildlife, an STA/LTA false positive)
    by throwing its recording away rather than keeping it. Only ever called
    with a scratch path - a committed capture has already left the scratch
    directory and this function has no way to reach it.

    Returns:
        True if the file is gone afterwards (including when it was already
        gone), False if it could not be removed.
    """
    try:
        scratch_path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning(
            "capture storage: failed to discard scratch recording %s: %s", scratch_path, exc
        )
        return False
    logger.info("capture storage: discarded unconfirmed recording %s", scratch_path)
    return True


def clear_orphaned_scratch(scratch_dir: Path = config.EVENT_VIDEO_SCRATCH_DIR) -> int:
    """Remove scratch recordings left behind by a crash mid-record; never raises.

    Called once at process start (device/mpu/main.py), never during an
    event. A file in the scratch directory at startup means a previous run
    died between "started recording" and "committed or discarded" - on this
    board the likeliest cause is the 5V brown-out documented in
    docs/KNOWN_GAPS.md. Those files are undecided by definition: nothing
    recorded which event they belong to, so there is no tag to commit them
    under, and left alone they accumulate silently against the same
    partition the confirmed captures need.

    This does not weaken ADR 0020 Decision C's no-deletion rule. It only
    ever touches `scratch_dir`, which by construction holds recordings that
    never became captures; a committed capture lives in CAPTURE_DIR itself
    and is not reachable from here.

    Returns:
        How many files were removed. 0 covers both "clean start" and
        "directory does not exist yet", which are the same thing to a
        caller.
    """
    if not scratch_dir.exists():
        return 0

    try:
        entries = sorted(scratch_dir.iterdir())
    except OSError as exc:
        logger.warning("capture storage: cannot list scratch dir %s: %s", scratch_dir, exc)
        return 0

    removed = 0
    for entry in entries:
        if not entry.is_file():
            continue
        try:
            entry.unlink()
        except OSError as exc:
            logger.warning(
                "capture storage: cannot remove orphaned scratch %s: %s", entry, exc
            )
            continue
        removed += 1

    if removed:
        logger.warning(
            "capture storage: removed %d orphaned scratch recording(s) from %s - a previous "
            "run died mid-record, most likely a power interruption",
            removed,
            scratch_dir,
        )
    return removed
