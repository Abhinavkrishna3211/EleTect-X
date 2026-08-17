"""Persists one deterrent-event frame burst to local disk (CONTEXT.md 4).

Companion to perception/camera.py, same importability discipline: this
module must stay importable with no OpenCV installed and no camera attached
(device/mpu/README.md's host-test harness) - `cv2` is imported only inside
`save_burst`, never at module scope. services/reflex_loop.py never calls
`save_burst` directly either; it takes a `save_frames`-shaped callable as an
injected dependency (same seam as `drive_horn`), so
tests/test_reflex_loop.py can assert a burst was "saved" via a recording
fake with no disk or cv2 involved. device/mpu/main.py is the only place that
wires this real implementation in.
"""

from __future__ import annotations

import logging
import shutil
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
        alert: Always True for a burst that reached save_burst() -
            carried through anyway so a saved capture's sidecar name is
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
