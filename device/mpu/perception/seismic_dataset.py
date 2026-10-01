"""Writes the camera-labelled seismic corpus one encounter at a time (ADR 0035).

Species-specific footfall classification was dropped from the original design
for want of a dataset, and the dataset was never collected because labelling
ground motion by hand is impossible - a waveform does not look like anything.
This module closes that loop using what the node already does: the geophone
fires, the camera opens a second later and watches for up to 45 s, and by the
end of the watch something has either been identified or demonstrably has not.
That answer is the label, it costs nothing, and it is available for every
trigger the node has ever handled.

WHAT A RECORD IS. One self-contained JSON file per vision watch, holding the
raw waveform (base64 int16, little-endian, exactly the ADC's own conversions),
the sample indices it spans, the scale needed to turn counts back into volts,
what the MCU believed at trigger time, the bounding boxes the camera drew over
the same seconds, and the actuator-on windows. One file and not a waveform
beside a sidecar, because two files are two failure modes: an export that finds
an orphaned sidecar has to guess, and a retention cap that evicts half a pair
leaves something worse than nothing.

WHY THE RAW WAVEFORM AND NOT FEATURES. device/mcu's own 8-feature derivation
describes itself as an honest placeholder in two separate files. A corpus keyed
to a placeholder feature set cannot be re-featurised, which is the one thing a
corpus has to survive. The features, the STA/LTA ratio and the MCU's
probability are all stored *alongside* the samples, because they are free and
they let a later reader reproduce exactly what the device believed.

THE SIX BUCKETS, AND THE ONE THAT MATTERS. elephant/, boar/ and fox/ are the
confirmations. no_animal/ is the camera having looked properly and found
nothing - the free negative class, and what teaches a future model to ignore
wind, rain and cattle. ambiguous/ is two species confirmed at once.
unlabelled/ is the camera not having been *able* to look: a detector outage, a
camera fault, or night with the illuminator refused. That last split is the
whole reason this module takes a `could_see` flag rather than inferring one
from an empty species list. Filing "could not look" as "saw nothing" fills the
negative class with unlabelled night elephants and teaches a model that
elephants only exist in daylight - which is the exact opposite of the truth,
since nearly all raiding happens after dark.

ACTUATOR CONTAMINATION. The horn, the LEDs and the geophone share one
structure, so firing the deterrent injects vibration into the signal being
recorded. If every elephant/ record contains horn energy and every no_animal/
record does not, a model trained on the corpus learns to detect its own horn.
Recording continues through a fire anyway - marked data can be filtered later,
missing data cannot be recovered - and each record carries the sample ranges
the actuators were on for, so training can default to the pre-deterrence
segment. The IR illuminator is not marked: it is an LED driver with nothing
moving and no acoustic output, so unlike the horn it has no path into the
ground.

NOTHING HERE MAY RAISE INTO THE REFLEX LOOP. Every public entry point swallows
its own failures. This runs after the deterrents have fired, on a board where
the disk filling up is an ordinary Tuesday, and a dataset write losing an event
record is an acceptable outcome in a way that a dataset write losing the event
is not.
"""

from __future__ import annotations

import base64
import json
import logging
import math
import os
import struct
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from perception import storage
from perception.seismic_stream import SeismicSlice
from services import config

logger = logging.getLogger(__name__)

# Bumped whenever a stored field changes meaning. An export script reads this
# first and refuses a record it does not understand, rather than quietly
# misinterpreting one - the corpus will outlive several versions of this file.
SCHEMA = 1

# The two buckets that are not a species name.
NEGATIVE_BUCKET = "no_animal"
BLIND_BUCKET = "unlabelled"
AMBIGUOUS_BUCKET = "ambiguous"

# How a record's bucket was arrived at. Stored beside the bucket because the
# bucket alone cannot be audited later: "unlabelled" does not say whether the
# detector died or the night was simply too dark, and those call for different
# fixes.
SOURCE_CONFIRMED = "vision_confirmed"
SOURCE_AMBIGUOUS = "vision_multiple"
SOURCE_LOOKED = "vision_looked"
SOURCE_BLIND = "vision_blind"

_INT16_MIN = -(1 << 15)
_INT16_MAX = (1 << 15) - 1


def _slug(label: str) -> str:
    """A species label reduced to a safe single path segment.

    The bucket is a directory name built from SPECIES_REGISTRY, which is a
    source table a human edits. Lowercasing is cosmetic; collapsing
    everything that is not alphanumeric is not - it is what stops a label
    containing a separator or a parent reference from aiming a write
    outside the dataset directory.
    """
    cleaned = "".join(c if c.isalnum() else "_" for c in label.lower()).strip("_")
    return cleaned or "unknown"


def bucket_for(confirming: Sequence[str], could_see: bool) -> tuple[str, str]:
    """Which bucket this watch's record belongs in, and how that was decided.

    Args:
        confirming: Every species the watch actually *confirmed*, in
            registry order - not every label a box was drawn around.
            Empty when nothing confirmed. The caller passes the same
            resolution the deterrence decision used, so a record can never
            be filed under a species the horn was not fired at.
        could_see: ADR 0022's `_vision_could_see()` for this watch: whether
            the camera and detector both worked and the scene was one the
            model could have classified at all.

    Returns:
        `(bucket, source)` - the directory name, and one of the SOURCE_*
        constants recording how it was reached.
    """
    if len(confirming) > 1:
        return AMBIGUOUS_BUCKET, SOURCE_AMBIGUOUS
    if confirming:
        return _slug(confirming[0]), SOURCE_CONFIRMED
    # Nothing confirmed. The entire question is now whether the camera had
    # a real chance, and only the caller knows that - an empty species list
    # looks identical in both cases.
    if could_see:
        return NEGATIVE_BUCKET, SOURCE_LOOKED
    return BLIND_BUCKET, SOURCE_BLIND


@dataclass(frozen=True)
class TrackBox:
    """One detection, in the detector's original-image pixel space."""

    label: str
    confidence: float
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class TrackFrame:
    """One camera frame, placed on the waveform's own sample axis.

    `sample_index` is what makes this a *co-sampled* record rather than two
    recordings that happen to share a wall clock. It is the frame's monotonic
    stamp resolved through SeismicStream.sample_index_at(), so a reader can
    scrub to a box and land on the ground motion that box was drawn over.
    None when the stream could not place it - no batch had arrived yet, or the
    frame predates everything retained.
    """

    poll: int
    frame_index: int
    timestamp_s: float
    sample_index: int | None
    boxes: tuple[TrackBox, ...] = ()


@dataclass(frozen=True)
class ActuatorSpan:
    """When one actuator was driving, in both clocks.

    The sample range is the one training reads; the monotonic pair is kept
    so the range can be re-derived if the sample mapping is ever corrected.

    The range is deliberately an over-estimate. drive_horn() returns when
    the MCU acks, and the MCU acks after its fire sequence has finished
    blocking, so `end_monotonic_s` is at or after the last moment the horn
    was making noise. Over-marking costs a little clean signal at the edge;
    under-marking leaks horn energy into a sample a model will train on.
    """

    actuator: str
    start_monotonic_s: float
    end_monotonic_s: float
    start_index: int | None = None
    count: int = 0


@dataclass(frozen=True)
class SeismicRecord:
    """One encounter: the ground motion, the camera's answer, and the context."""

    bucket: str
    source: str
    event_wall_s: float
    event_monotonic_s: float
    node_scope: str
    sta_lta_ratio: float
    mcu_probability: float
    feature_vector: tuple[float, ...]
    seismic_available: bool
    seismic: SeismicSlice | None
    track: tuple[TrackFrame, ...] = ()
    actuators: tuple[ActuatorSpan, ...] = ()
    vision_polls: int = 0
    vision_watch_s: float = 0.0
    confirmed_on_poll: int | None = None
    species_seen: tuple[str, ...] = ()
    illuminated: bool = False
    could_see: bool = False
    # Every range derived from a box in `track` depends on a focal length
    # taken from the lens's nominal 95 degree field of view, which is a
    # specification and not a measurement. Stamped on every record so a
    # later calibration can re-derive ranges from the stored boxes instead
    # of invalidating everything collected before it.
    calibrated: bool = False
    schema: int = field(default=SCHEMA)

    @property
    def sample_count(self) -> int:
        """How many samples of ground motion this record carries."""
        return 0 if self.seismic is None else len(self.seismic)

    def to_dict(self) -> dict:
        """The record as the JSON object that goes on disk.

        Grouped by provenance rather than flattened: everything under
        `seismic` came off the geophone, everything under `vision` off the
        camera, and `label` is the join between them. An export script that
        wants only waveforms should not have to know which of thirty
        top-level keys belong to which sensor.
        """
        return {
            "schema": self.schema,
            "node_scope": self.node_scope,
            "label": {
                "bucket": self.bucket,
                "source": self.source,
                "calibrated": self.calibrated,
            },
            "event": {
                "wall_s": self.event_wall_s,
                "monotonic_s": self.event_monotonic_s,
                "sta_lta_ratio": self.sta_lta_ratio,
                "mcu_probability": self.mcu_probability,
                "feature_vector": list(self.feature_vector),
                "seismic_available": self.seismic_available,
            },
            "seismic": _seismic_dict(self.seismic),
            "vision": {
                "polls": self.vision_polls,
                "watch_s": self.vision_watch_s,
                "confirmed_on_poll": self.confirmed_on_poll,
                "species_seen": list(self.species_seen),
                "illuminated": self.illuminated,
                "could_see": self.could_see,
                "track": [
                    {
                        "poll": f.poll,
                        "frame_index": f.frame_index,
                        "timestamp_s": f.timestamp_s,
                        "sample_index": f.sample_index,
                        "boxes": [
                            {
                                "label": b.label,
                                "confidence": b.confidence,
                                "x": b.x,
                                "y": b.y,
                                "width": b.width,
                                "height": b.height,
                            }
                            for b in f.boxes
                        ],
                    }
                    for f in self.track
                ],
            },
            "actuators": [
                {
                    "actuator": a.actuator,
                    "start_monotonic_s": a.start_monotonic_s,
                    "end_monotonic_s": a.end_monotonic_s,
                    "start_index": a.start_index,
                    "count": a.count,
                }
                for a in self.actuators
            ],
        }


def _seismic_dict(slice_: SeismicSlice | None) -> dict | None:
    """The waveform half of a record, or None when no ground motion was held.

    None is a real and expected value, not a failure: an acoustic-initiated
    event has no geophone behind it, and a node whose report_seismic_batch
    registration is not up has no stream at all. The vision half of the
    record is still worth keeping in both cases - it is the labelled half.
    """
    if slice_ is None:
        return None
    return {
        "first_sample_index": slice_.first_sample_index,
        "sample_count": len(slice_),
        "sample_rate_hz_nominal": config.SEISMIC_SAMPLE_RATE_HZ,
        "lsb_volts": slice_.lsb_volts,
        # Named rather than implied. Counts are the asset and volts are
        # derived; a reader that guesses the width or the byte order gets
        # plausible-looking noise rather than an error.
        "encoding": "base64:int16le",
        "samples": _encode_counts(slice_.counts),
        "gaps": [{"start_index": g.start_index, "count": g.count} for g in slice_.gaps],
        "missing_samples": slice_.missing_samples,
        "geophone_ok": slice_.geophone_ok,
    }


def _encode_counts(counts: Sequence[int]) -> str:
    """Pack raw ADC counts into base64 little-endian int16.

    Base64 inside JSON rather than a list of integers, which would be four
    to six times the size for the same data and would make a 50 s record a
    150 kB file of decimal digits. A value outside int16 cannot have come
    off the ADS1115 and is clamped rather than allowed to fail the record -
    one impossible sample is not worth losing an encounter over, and the
    clamp is logged so it cannot pass unnoticed.
    """
    clamped = []
    out_of_range = 0
    for value in counts:
        if value < _INT16_MIN or value > _INT16_MAX:
            out_of_range += 1
            value = min(max(value, _INT16_MIN), _INT16_MAX)
        clamped.append(value)
    if out_of_range:
        logger.warning(
            "seismic dataset: clamped %d sample(s) outside int16 - the ADS1115 "
            "cannot produce these, so the stream or the wire format is wrong",
            out_of_range,
        )
    return base64.b64encode(struct.pack(f"<{len(clamped)}h", *clamped)).decode("ascii")


def track_frames(
    samples: Iterable, locate: Callable[[float], int | None] | None = None
) -> tuple[TrackFrame, ...]:
    """Convert the reflex loop's vision track into placed, serialisable frames.

    Deliberately duck-typed rather than importing
    services.reflex_loop.VisionTrackSample. The dependency has to run this
    way round - the reflex loop imports perception, not the other way - and
    the alternative, moving the track types down here, would drag the
    detector's Detection into a module about disk layout.

    Args:
        samples: VisionTrackSample-shaped objects: `.poll`, `.frame_index`,
            `.timestamp_s` and `.detections`, each detection carrying
            `.label`, `.confidence`, `.x`, `.y`, `.width` and `.height`.
        locate: SeismicStream.sample_index_at, or None when there is no
            stream. None leaves every `sample_index` unset, which is honest -
            the boxes are still worth keeping without a waveform to pin them
            to.

    Returns:
        One TrackFrame per sample, in the order given. Never raises: a
        malformed sample is skipped with a warning, because a detector that
        returned something unexpected must not also cost the waveform.
    """
    frames = []
    for sample in samples:
        try:
            index = None
            if locate is not None:
                index = locate(sample.timestamp_s)
            frames.append(
                TrackFrame(
                    poll=sample.poll,
                    frame_index=sample.frame_index,
                    timestamp_s=sample.timestamp_s,
                    sample_index=index,
                    boxes=tuple(
                        TrackBox(
                            label=d.label,
                            confidence=d.confidence,
                            x=d.x,
                            y=d.y,
                            width=d.width,
                            height=d.height,
                        )
                        for d in sample.detections
                    ),
                )
            )
        except Exception as exc:  # noqa: BLE001 - a bad sample must not lose the record
            logger.warning("seismic dataset: skipping malformed track sample: %s", exc)
    return tuple(frames)


def place_actuator(
    span: ActuatorSpan, locate: Callable[[float], int | None] | None
) -> ActuatorSpan:
    """Resolve an actuator's monotonic window onto the sample axis.

    Rounds outward - floor at the start, ceil at the end - for the reason
    ActuatorSpan's docstring gives: a marked sample that was actually clean
    costs nothing, and a clean-looking sample that actually contains horn
    energy is how a model learns to detect its own deterrent.
    """
    if locate is None:
        return span
    first = locate(span.start_monotonic_s)
    last = locate(span.end_monotonic_s)
    if first is None or last is None:
        return span
    duration = span.end_monotonic_s - span.start_monotonic_s
    count = max(last - first + 1, math.ceil(duration * config.SEISMIC_SAMPLE_RATE_HZ))
    return ActuatorSpan(
        actuator=span.actuator,
        start_monotonic_s=span.start_monotonic_s,
        end_monotonic_s=span.end_monotonic_s,
        start_index=first,
        count=max(count, 0),
    )


class SeismicDatasetWriter:
    """Puts records on disk under their bucket, and keeps the total bounded.

    One instance for the life of the process, held by device/mpu/main.py and
    handed to the reflex loop. Stateless apart from its paths - the cap is
    enforced by reading the directory, not by a running total, so a count
    cannot drift away from what is actually there across a restart.
    """

    def __init__(
        self,
        root: Path = config.SEISMIC_DATASET_DIR,
        max_bytes: int = config.SEISMIC_DATASET_MAX_BYTES,
        eviction_order: Sequence[str] = config.SEISMIC_DATASET_EVICTION_ORDER,
    ) -> None:
        """Defaults are the field configuration; the arguments exist for tests."""
        self.root = Path(root)
        self.max_bytes = max_bytes
        self.eviction_order = tuple(eviction_order)

    # -- write -------------------------------------------------------------

    def write(self, record: SeismicRecord) -> Path | None:
        """Write one record; never raises.

        Returns:
            The path written, or None if nothing was written - which covers
            a disabled recorder, a serialisation failure and a storage
            fault alike. Every one of those is logged; none of them is
            allowed to reach the caller, which is mid-event.
        """
        if not config.SEISMIC_DATASET_ENABLED:
            return None
        try:
            payload = json.dumps(record.to_dict(), separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError) as exc:
            logger.warning("seismic dataset: cannot serialise record: %s", exc)
            return None

        path = self.root / record.bucket / _record_name(record)
        if not storage.atomic_write_bytes(path, payload):
            return None

        logger.info(
            "seismic dataset: wrote %s (%d sample(s), %d track frame(s), %.1f kB)",
            path,
            record.sample_count,
            len(record.track),
            len(payload) / 1024,
        )
        # After, not before: the record just written is the newest thing in
        # the directory and so the last candidate for eviction anyway, and
        # enforcing first would leave the cap exceeded until the next event.
        self.enforce_cap()
        return path

    # -- retention ---------------------------------------------------------

    def enforce_cap(self) -> int:
        """Evict until the directory is under the cap; never raises.

        Returns:
            How many files were removed.
        """
        try:
            entries = self._entries()
        except OSError as exc:
            logger.warning("seismic dataset: cannot read %s to enforce the cap: %s", self.root, exc)
            return 0

        total = sum(size for _, _, size in entries)
        if total <= self.max_bytes:
            return 0

        removed = 0
        for path, _, size in self._eviction_candidates(entries):
            if total <= self.max_bytes:
                break
            try:
                path.unlink()
            except OSError as exc:
                logger.warning("seismic dataset: cannot evict %s: %s", path, exc)
                continue
            total -= size
            removed += 1
        if removed:
            logger.info(
                "seismic dataset: evicted %d record(s) to stay under %.0f MB (now %.1f MB)",
                removed,
                self.max_bytes / (1024 * 1024),
                total / (1024 * 1024),
            )
        elif total > self.max_bytes:
            logger.warning(
                "seismic dataset: %.1f MB over the %.0f MB cap and nothing could be "
                "evicted - the corpus is now growing unbounded",
                (total - self.max_bytes) / (1024 * 1024),
                self.max_bytes / (1024 * 1024),
            )
        return removed

    def _entries(self) -> list[tuple[Path, str, int]]:
        """Every record on disk as `(path, bucket, size_bytes)`."""
        entries: list[tuple[Path, str, int]] = []
        if not self.root.is_dir():
            return entries
        for bucket_dir in sorted(self.root.iterdir()):
            if not bucket_dir.is_dir():
                continue
            for path in bucket_dir.glob("*.json"):
                try:
                    entries.append((path, bucket_dir.name, path.stat().st_size))
                except OSError:
                    # Raced with another eviction, or vanished under us.
                    # Nothing to do but leave it out of the accounting.
                    continue
        return entries

    def _eviction_candidates(
        self, entries: Sequence[tuple[Path, str, int]]
    ) -> list[tuple[Path, str, int]]:
        """Records in the order they may be given up - cheapest loss first.

        Two keys, and the order of them is the policy. The bucket's rank in
        SEISMIC_DATASET_EVICTION_ORDER dominates, so every unlabelled record
        in the corpus goes before the first no_animal one and every one of
        those goes before the first confirmed species - a confirmed elephant
        on a geophone is the scarce thing this corpus exists to accumulate,
        and age is no reason to prefer losing one over a hundred records the
        camera could not label at all. Age only breaks ties inside a rank.
        """
        ranks = {bucket: i for i, bucket in enumerate(self.eviction_order)}
        # Anything not named - every species bucket - sorts last.
        unranked = len(ranks)

        def key(entry: tuple[Path, str, int]) -> tuple[int, float, str]:
            path, bucket, _ = entry
            try:
                age = path.stat().st_mtime
            except OSError:
                age = 0.0
            return (ranks.get(bucket, unranked), age, str(path))

        return sorted(entries, key=key)


def _record_name(record: SeismicRecord) -> str:
    """A sortable, self-describing, collision-resistant filename.

    Wall clock first so a directory listing is chronological, matching
    perception/storage.py's `_event_prefix`. The STA/LTA ratio and the MCU
    probability ride along for the same reason they do there: a filename
    that says what the device believed makes a corpus browsable without a
    parser.
    """
    return (
        f"{record.event_wall_s:.3f}"
        f"_sta{record.sta_lta_ratio:.2f}"
        f"_p{record.mcu_probability:.3f}"
        f"_n{record.sample_count}"
        f".json"
    )


def clear_part_files(root: Path = config.SEISMIC_DATASET_DIR) -> int:
    """Remove `.part` files left behind by a crash mid-write; never raises.

    Called once at process start, the same shape as
    perception/storage.py's clear_orphaned_scratch(). A `.part` file is a
    write that a brown-out caught between the write and the rename, so it
    is by definition incomplete - and on this board a brown-out mid-write is
    a documented, observed event.

    Returns:
        How many files were removed.
    """
    removed = 0
    try:
        if not Path(root).is_dir():
            return 0
        for path in Path(root).glob("*/*.json.part"):
            try:
                os.unlink(path)
            except OSError as exc:
                logger.warning("seismic dataset: cannot remove %s: %s", path, exc)
                continue
            removed += 1
    except OSError as exc:
        logger.warning("seismic dataset: cannot scan %s for partial writes: %s", root, exc)
        return removed
    if removed:
        logger.info("seismic dataset: removed %d partial write(s) left by a crash", removed)
    return removed
