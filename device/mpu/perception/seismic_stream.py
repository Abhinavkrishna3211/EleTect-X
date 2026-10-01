"""Reassembles the MCU's batched ground-motion stream into an addressable record.

The MCU pushes `report_seismic_batch` notifies (device/mcu/src/seismic_capture.h):
32 raw ADS1115 conversions plus the absolute index of the first one. This
module turns that sequence back into a continuous, index-addressable waveform
that the recorder can slice to match a vision watch, and that the camera can
label minutes later.

WHY PUSHED BATCHES AND NOT A BRIDGE CALL. The obvious design is for the MPU to
pull `read_seismic_window()` once per vision poll. It cannot: the Bridge caps a
message at 256 bytes and a 512-sample window is ~2.5 kB, so the call would
raise on this side before anything reached the wire. Chunking the pull into
256-byte replies would fit, but it puts a dozen blocking round trips per second
onto the same link that `drive_horn`/`drive_led` need an ack from mid-encounter.
A pushed `Bridge.notify()` never blocks the MCU's reflex loop at all, which is
the property that makes it safe to keep recording through a deterrence fire -
and recording through the fire is required, because actuator contamination can
be filtered out later while missing samples cannot be recovered.

WHAT THE SAMPLE INDEX BUYS. Every batch is stamped with its first sample's
position in `geophone_sample_count()`'s monotonic sequence, so joining two
batches is arithmetic rather than assumption. Where a batch never arrives, this
module records a `SeismicGap` naming exactly which samples are missing instead
of concatenating across the hole. That distinction is the whole point: a model
trained on a record that quietly spliced out 400 ms would learn a cadence the
animal never walked.

TIMING, HONESTLY. Each batch is stamped with `time.monotonic()` on arrival -
the same clock `perception/video.py` stamps frames with - so the waveform and
the video share one time base. What that base does not account for is the
Bridge's own transport latency: a batch covers 128 ms of ground motion and
arrives some unmeasured time after its last sample was taken. The bench harness
that would measure it has never been run against hardware, so `monotonic_at()`
states its error band rather than implying a precision nobody has established.
Relative timing *within* the record does not depend on the clock at all - it
comes from the sample indices - so gait cadence is exact regardless. It is only
waveform-to-video alignment that carries the unknown.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from dataclasses import dataclass

from services import config

logger = logging.getLogger(__name__)

# geophone_sample_count() is a uint32 and is documented as never saturating, so
# it wraps. Index arithmetic is modular for the same reason the MCU-side
# accumulator's is: a false four-billion-sample gap once every 198 days of
# uptime would corrupt a night's record for no reason.
_INDEX_MODULUS = 1 << 32


@dataclass(frozen=True)
class SeismicGap:
    """A run of samples that never arrived, named rather than smoothed over."""

    start_index: int
    count: int

    @property
    def end_index(self) -> int:
        """Exclusive."""
        return self.start_index + self.count


@dataclass(frozen=True)
class SeismicSlice:
    """A contiguous span of the record, with its holes declared.

    `counts` is zero-filled across any gap, because a record has to stay
    index-addressable to line up with the vision track. `gaps` is what stops a
    consumer reading those zeros as quiet ground - every one is listed, clipped
    to this slice's own bounds.
    """

    first_sample_index: int
    counts: tuple[int, ...]
    gaps: tuple[SeismicGap, ...]
    # False if any batch overlapping this slice reported an unhealthy geophone,
    # or if the slice contains a gap. Conservative on purpose: the only use for
    # this flag is deciding whether a record is fit to train on.
    geophone_ok: bool
    # Volts per LSB for `counts`. Carried on the slice rather than looked up by
    # the consumer, so a stored record stays self-describing - a corpus of raw
    # counts with no scale recorded beside it cannot be re-analysed later.
    lsb_volts: float = config.SEISMIC_LSB_VOLTS

    def __len__(self) -> int:
        """The number of samples, holes included - a slice stays index-addressable."""
        return len(self.counts)

    @property
    def volts(self) -> tuple[float, ...]:
        """The slice in volts. Derived, never stored - `counts` is the asset."""
        return tuple(c * self.lsb_volts for c in self.counts)

    @property
    def missing_samples(self) -> int:
        """How many of this slice's samples never arrived."""
        return sum(g.count for g in self.gaps)


@dataclass(frozen=True)
class _Arrival:
    """One batch, kept only so a sample index can be put back on the clock."""

    first_sample_index: int
    count: int
    received_monotonic: float


@dataclass
class SeismicStreamStats:
    """Counters worth logging at the end of a night. Never a control input."""

    batches: int = 0
    samples: int = 0
    gaps: int = 0
    missing_samples: int = 0
    restarts: int = 0
    unhealthy_batches: int = 0
    rejected_batches: int = 0


class SeismicStream:
    """Thread-safe ring buffer of the MCU's ground-motion stream.

    `push()` runs on the Bridge's RPC thread while the readers run on the
    vision watch's thread, so every public method takes the lock. The work
    under it is a bounded copy over at most `capacity` entries with no I/O,
    which is what keeps it inside the "handlers must stay short" constraint the
    Bridge documents for that thread.
    """

    def __init__(
        self,
        capacity: int = config.SEISMIC_STREAM_CAPACITY_SAMPLES,
        max_gap_samples: int = config.SEISMIC_STREAM_MAX_GAP_SAMPLES,
        lsb_volts: float = config.SEISMIC_LSB_VOLTS,
    ) -> None:
        """Defaults mirror device/mcu/src/config.h via services/config.py.

        The arguments exist so the tests can work at a ring size they can
        fill in a few lines; the field only ever uses the defaults.
        """
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self.max_gap_samples = max_gap_samples
        self.lsb_volts = lsb_volts
        self.stats = SeismicStreamStats()

        self._lock = threading.Lock()
        self._counts = [0] * capacity
        self._present = bytearray(capacity)
        self._arrivals: list[_Arrival] = []
        self._gaps: list[SeismicGap] = []
        self._unhealthy: list[SeismicGap] = []
        # None until the first batch lands. After that, [_start_index,
        # _end_index) is the half-open span of absolute sample indices held.
        self._start_index: int | None = None
        self._end_index: int | None = None

    # -- ingest ------------------------------------------------------------

    def push(
        self,
        first_sample_index: int,
        count: int,
        samples: Sequence[int],
        geophone_ok: bool,
        received_monotonic: float,
    ) -> None:
        """Accept one `report_seismic_batch` notify.

        `samples` is always the full fixed-length array the MCU sends; `count`
        says how many leading entries are real. The tail is zeroed on the MCU
        but is ignored here regardless, so a firmware that stopped zeroing it
        could not leak the previous batch's ground motion into this one.

        Never raises on a malformed batch. This runs on the Bridge's RPC
        thread, where an exception is not a test failure someone notices - it
        is a dropped handler on the thread the actuator acks share. A bad batch
        is counted and discarded.
        """
        if count <= 0 or count > len(samples):
            logger.warning(
                "seismic batch rejected: count=%d against %d samples", count, len(samples)
            )
            with self._lock:
                self.stats.rejected_batches += 1
            return

        first = first_sample_index % _INDEX_MODULUS
        payload = [int(s) for s in samples[:count]]

        with self._lock:
            if self._end_index is None:
                self._restart_locked(first)
            else:
                delta = (first - self._end_index) % _INDEX_MODULUS
                if delta > self.max_gap_samples:
                    # Not a gap - nothing survives on both sides of it to join.
                    # Either the MCU restarted (its counter resets to 0) or the
                    # stream was off for longer than the ring can span.
                    logger.info(
                        "seismic stream restart: expected index %d, got %d - dropping "
                        "%d buffered sample(s)",
                        self._end_index,
                        first,
                        self._buffered_locked(),
                    )
                    self.stats.restarts += 1
                    self._restart_locked(first)
                elif delta > 0:
                    self._open_gap_locked(self._end_index, delta)

            self._write_locked(first, payload)
            self._arrivals.append(_Arrival(first, count, received_monotonic))
            if not geophone_ok:
                self._unhealthy.append(SeismicGap(first, count))
                self.stats.unhealthy_batches += 1
            self.stats.batches += 1
            self.stats.samples += count
            self._evict_locked()

    def _restart_locked(self, first: int) -> None:
        self._counts = [0] * self.capacity
        self._present = bytearray(self.capacity)
        self._arrivals.clear()
        self._gaps.clear()
        self._unhealthy.clear()
        self._start_index = first
        self._end_index = first

    def _open_gap_locked(self, start: int, count: int) -> None:
        """Record missing samples, and punch the hole in the ring itself.

        Punching matters. The slots a gap covers may still hold real samples
        from the last time the ring wrapped past them, still flagged present.
        If the hole were only noted in `_gaps` and not cleared in the buffer, a
        slice across it would hand back minute-old ground motion wearing this
        minute's sample indices - worse than a hole, because a hole is visible.
        """
        self._gaps.append(SeismicGap(start, count))
        self.stats.gaps += 1
        self.stats.missing_samples += count
        logger.warning("seismic stream gap: %d sample(s) missing from index %d", count, start)
        for offset in range(min(count, self.capacity)):
            slot = (start + offset) % self.capacity
            self._counts[slot] = 0
            self._present[slot] = 0
        self._end_index = (start + count) % _INDEX_MODULUS

    def _write_locked(self, first: int, payload: list[int]) -> None:
        for offset, value in enumerate(payload):
            slot = (first + offset) % self.capacity
            self._counts[slot] = value
            self._present[slot] = 1
        self._end_index = (first + len(payload)) % _INDEX_MODULUS

    def _buffered_locked(self) -> int:
        if self._end_index is None or self._start_index is None:
            return 0
        return min(self.capacity, (self._end_index - self._start_index) % _INDEX_MODULUS)

    def _evict_locked(self) -> None:
        """Drop what has aged out of the ring, and the bookkeeping with it."""
        if self._end_index is None or self._start_index is None:
            return
        if (self._end_index - self._start_index) % _INDEX_MODULUS > self.capacity:
            self._start_index = (self._end_index - self.capacity) % _INDEX_MODULUS
        self._gaps = [g for g in self._gaps if self._contains_locked(g.end_index - 1)]
        self._unhealthy = [u for u in self._unhealthy if self._contains_locked(u.end_index - 1)]
        self._arrivals = [
            a for a in self._arrivals if self._contains_locked(a.first_sample_index + a.count - 1)
        ]

    def _contains_locked(self, index: int) -> bool:
        if self._start_index is None:
            return False
        return (index - self._start_index) % _INDEX_MODULUS < self._buffered_locked()

    # -- read --------------------------------------------------------------

    @property
    def available(self) -> tuple[int, int] | None:
        """`(first_index, count)` currently held, or None if nothing has arrived."""
        with self._lock:
            if self._start_index is None:
                return None
            return (self._start_index, self._buffered_locked())

    def slice(self, first_sample_index: int, count: int) -> SeismicSlice | None:
        """The record from `first_sample_index` for `count` samples.

        Returns None rather than a short or shifted slice when the request
        falls outside what the ring still holds. A recorder that silently got
        300 of the 512 samples it asked for, starting somewhere other than
        where it asked, would write a record whose index stamps were lies.
        """
        if count <= 0:
            return None
        with self._lock:
            if self._start_index is None:
                return None
            start_offset = (first_sample_index - self._start_index) % _INDEX_MODULUS
            if start_offset + count > self._buffered_locked():
                return None

            counts = []
            for i in range(count):
                slot = (first_sample_index + i) % self.capacity
                counts.append(self._counts[slot] if self._present[slot] else 0)

            end = first_sample_index + count
            gaps = tuple(
                clipped
                for g in self._gaps
                if (clipped := _clip(g, first_sample_index, end)) is not None
            )
            unhealthy = any(_clip(u, first_sample_index, end) is not None for u in self._unhealthy)
            return SeismicSlice(
                first_sample_index=first_sample_index,
                counts=tuple(counts),
                gaps=gaps,
                geophone_ok=not unhealthy and not gaps,
                lsb_volts=self.lsb_volts,
            )

    def latest(self, count: int) -> SeismicSlice | None:
        """The most recent `count` samples, or None if that many are not held."""
        with self._lock:
            if self._end_index is None or count <= 0 or count > self._buffered_locked():
                return None
            start = (self._end_index - count) % _INDEX_MODULUS
        return self.slice(start, count)

    def monotonic_at(self, sample_index: int) -> float | None:
        """Best estimate of when `sample_index` was taken, on time.monotonic().

        Interpolated backwards from the arrival stamp of the batch that carried
        it, at the nominal sample rate. Two error terms ride on this and
        neither has been measured: the Bridge's transport latency, and the
        drift between SEISMIC_SAMPLE_RATE_HZ's nominal 250 Hz and what the ADC
        actually achieves in the field. Treat it as good to about a batch
        period (~128 ms), not better.

        Timing *within* the record does not use this at all - it comes from the
        sample indices - so gait cadence is unaffected by either term.
        """
        with self._lock:
            for arrival in reversed(self._arrivals):
                offset = (sample_index - arrival.first_sample_index) % _INDEX_MODULUS
                if offset < arrival.count:
                    remaining = (arrival.count - offset) / config.SEISMIC_SAMPLE_RATE_HZ
                    return arrival.received_monotonic - remaining
        return None


def _clip(gap: SeismicGap, start: int, end: int) -> SeismicGap | None:
    """`gap` restricted to [start, end), or None if they do not overlap."""
    lo = max(gap.start_index, start)
    hi = min(gap.end_index, end)
    if hi <= lo:
        return None
    return SeismicGap(lo, hi - lo)
