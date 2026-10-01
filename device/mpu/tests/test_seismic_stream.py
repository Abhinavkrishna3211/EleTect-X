"""perception/seismic_stream.py - reassembling the MCU's batched ground motion.

The thing under test is a record that a future species-specific footfall model
will be trained on, so the tests are weighted towards the failures that would
be invisible in the data rather than the ones that would raise: a hole silently
spliced shut, a hole silently filled with a previous minute's samples, a short
batch dragging its predecessor's tail along behind it. Each of those produces a
file that looks perfectly well-formed and teaches the model something false.
"""

from __future__ import annotations

import threading

import pytest

from perception.seismic_stream import _INDEX_MODULUS, SeismicGap, SeismicStream, _signed_offset
from services import config

BATCH = config.SEISMIC_CAPTURE_BATCH_SAMPLES


def _wire(values, length=BATCH):
    """The wire shape: a fixed-length array, zero-padded past `count`.

    The MCU always sends the full std::array - `count` is what says how much of
    it is real - so the tests feed the same shape rather than a trimmed list.
    """
    padded = list(values) + [0] * (length - len(values))
    return tuple(padded[:length])


def _ramp(first, count, base=1000):
    """Distinct per-index values, so a misplaced sample is identifiable."""
    return [base + first + i for i in range(count)]


def _push(stream, first, count=BATCH, *, ok=True, at=0.0, base=1000):
    stream.push(first, count, _wire(_ramp(first, count, base)), ok, at)


# -- stitching -------------------------------------------------------------


def test_consecutive_batches_stitch_into_one_continuous_record():
    """Three abutting batches read back as one unbroken waveform."""
    stream = SeismicStream(capacity=256)
    _push(stream, 0)
    _push(stream, BATCH)
    _push(stream, 2 * BATCH)

    got = stream.slice(0, 3 * BATCH)
    assert got is not None
    assert list(got.counts) == _ramp(0, 3 * BATCH)
    assert got.gaps == ()
    assert got.geophone_ok is True


def test_a_slice_can_start_part_way_into_a_batch():
    """The recorder asks for a vision poll's span, not for batch boundaries."""
    stream = SeismicStream(capacity=256)
    _push(stream, 0)
    _push(stream, BATCH)

    got = stream.slice(5, 10)
    assert got is not None
    assert got.first_sample_index == 5
    assert list(got.counts) == _ramp(5, 10)


def test_available_reports_nothing_before_the_first_batch():
    """An empty stream says so rather than returning an empty-looking record."""
    assert SeismicStream(capacity=256).available is None
    assert SeismicStream(capacity=256).slice(0, 8) is None
    assert SeismicStream(capacity=256).latest(8) is None


# -- gaps ------------------------------------------------------------------


def test_a_missing_batch_is_recorded_as_a_gap_of_exact_start_and_length():
    """A hole is named by index and length, not merely flagged."""
    stream = SeismicStream(capacity=256)
    _push(stream, 0)
    # The batch at BATCH never arrives.
    _push(stream, 2 * BATCH)

    got = stream.slice(0, 3 * BATCH)
    assert got is not None
    assert got.gaps == (SeismicGap(BATCH, BATCH),)
    assert got.missing_samples == BATCH
    assert stream.stats.gaps == 1
    assert stream.stats.missing_samples == BATCH


def test_a_gap_is_never_spliced_shut():
    """The failure this whole design exists to prevent.

    Concatenating across a hole would produce a record in which the animal
    appears to have taken its next step 128 ms early. Cadence is the strongest
    elephant/boar/fox discriminator, so a spliced record does not merely lose
    data - it manufactures a gait that was never walked.
    """
    stream = SeismicStream(capacity=256)
    _push(stream, 0)
    _push(stream, 2 * BATCH)

    got = stream.slice(0, 3 * BATCH)
    assert got is not None
    # The samples either side keep their true index positions ...
    assert got.counts[BATCH - 1] == 1000 + BATCH - 1
    assert got.counts[2 * BATCH] == 1000 + 2 * BATCH
    # ... and the hole between them is zero-filled, not closed up.
    assert set(got.counts[BATCH : 2 * BATCH]) == {0}


def test_a_gap_does_not_resurface_the_ring_s_previous_contents():
    """The non-obvious one: a hole's slots may still hold older real samples.

    Recording the gap in a side list is not enough - the ring slots the gap
    covers were last written one full wrap ago and are still flagged present.
    Left alone they would hand back minute-old ground motion wearing this
    minute's sample indices, which is strictly worse than a hole because
    nothing downstream can see it.
    """
    capacity = 64
    stream = SeismicStream(capacity=capacity, max_gap_samples=capacity)
    for first in range(0, capacity, BATCH):
        _push(stream, first)
    # Skip exactly one batch's worth so the hole lands on slots that currently
    # hold the samples from indices 0..BATCH-1.
    gap_start = capacity
    _push(stream, capacity + BATCH)

    got = stream.slice(gap_start, BATCH)
    assert got is not None
    assert got.gaps == (SeismicGap(gap_start, BATCH),)
    assert set(got.counts) == {0}, "a hole returned the ring's previous contents"


def test_a_slice_containing_a_gap_is_not_reported_healthy():
    """`geophone_ok` is a fitness-to-train flag, so a hole has to clear it."""
    stream = SeismicStream(capacity=256)
    _push(stream, 0)
    _push(stream, 2 * BATCH)

    spanning = stream.slice(0, 3 * BATCH)
    assert spanning is not None and spanning.geophone_ok is False
    # ... but a slice entirely clear of the hole still is.
    clean = stream.slice(0, BATCH)
    assert clean is not None and clean.geophone_ok is True
    assert clean.gaps == ()


def test_gaps_are_clipped_to_the_requested_slice():
    """A gap is reported in the slice's own coordinates, not the stream's."""
    stream = SeismicStream(capacity=256)
    _push(stream, 0)
    _push(stream, 3 * BATCH)

    # Ask for a window that covers only the second half of the hole.
    start = 2 * BATCH
    got = stream.slice(start, BATCH)
    assert got is not None
    assert got.gaps == (SeismicGap(start, BATCH),)
    assert got.missing_samples == BATCH


# -- counter wrap and restart ----------------------------------------------


def test_the_uint32_counter_wrapping_is_not_a_gap():
    """geophone_sample_count() never saturates, so it wraps."""
    stream = SeismicStream(capacity=256)
    first = (1 << 32) - BATCH
    stream.push(first, BATCH, _wire(_ramp(0, BATCH)), True, 0.0)
    stream.push(0, BATCH, _wire(_ramp(BATCH, BATCH)), True, 0.0)

    assert stream.stats.gaps == 0
    assert stream.stats.restarts == 0
    got = stream.slice(first, 2 * BATCH)
    assert got is not None
    assert list(got.counts) == _ramp(0, 2 * BATCH)


def test_an_mcu_restart_flushes_rather_than_recording_a_four_billion_gap():
    """The MCU's counter resets to 0 on boot; the buffer cannot bridge that."""
    stream = SeismicStream(capacity=256, max_gap_samples=256)
    _push(stream, 5000)
    _push(stream, 5000 + BATCH)
    # A reboot: the next batch claims index 0 again.
    _push(stream, 0, base=7000)

    assert stream.stats.restarts == 1
    assert stream.stats.gaps == 0, "a restart must not be filed as missing samples"
    assert stream.available == (0, BATCH)
    assert stream.slice(5000, BATCH) is None, "pre-restart samples must not survive"
    got = stream.slice(0, BATCH)
    assert got is not None
    assert list(got.counts) == _ramp(0, BATCH, base=7000)


def test_a_batch_that_claims_an_index_already_passed_is_treated_as_a_restart():
    """A counter that moves backwards is a reboot, not a late delivery.

    This is the branch the modular arithmetic actually earns its keep on. A
    plain subtraction makes a backwards jump negative, which falls through
    both the gap test and the restart test and gets written straight into
    the middle of the ring - overwriting samples already recorded under
    those indices with a different encounter's ground motion, and leaving
    nothing anywhere to say it happened. Modulo turns it into a jump larger
    than the buffer, which is exactly what it is.
    """
    stream = SeismicStream(capacity=256, max_gap_samples=256)
    _push(stream, 1000, base=1000)
    _push(stream, 1000 + BATCH, base=1000)
    # The MCU rebooted and its counter came back somewhere behind us.
    _push(stream, 500, base=9000)

    assert stream.stats.restarts == 1
    assert stream.stats.gaps == 0
    assert stream.available == (500, BATCH)
    got = stream.slice(500, BATCH)
    assert got is not None
    assert list(got.counts) == _ramp(500, BATCH, base=9000)


def test_a_silence_longer_than_the_buffer_is_a_restart_not_a_gap():
    """Nothing survives on both sides of it, so there is nothing to join."""
    stream = SeismicStream(capacity=128, max_gap_samples=128)
    _push(stream, 0)
    _push(stream, 10_000)

    assert stream.stats.restarts == 1
    assert stream.stats.gaps == 0
    assert stream.available == (10_000, BATCH)


# -- malformed input -------------------------------------------------------


def test_the_padded_tail_past_count_is_ignored():
    """A short batch must not drag the array's remaining slots in with it."""
    stream = SeismicStream(capacity=256)
    # Deliberately non-zero padding - the MCU zeroes it, but this side must not
    # depend on a firmware behaviour it cannot enforce.
    payload = tuple([11, 22, 33] + [999] * (BATCH - 3))
    stream.push(0, 3, payload, True, 0.0)

    assert stream.available == (0, 3)
    got = stream.slice(0, 3)
    assert got is not None
    assert list(got.counts) == [11, 22, 33]
    assert stream.slice(0, 4) is None


@pytest.mark.parametrize("count", [0, -1, BATCH + 1])
def test_a_malformed_batch_is_counted_and_dropped_never_raised(count):
    """push() runs on the Bridge's RPC thread, where raising drops a handler."""
    stream = SeismicStream(capacity=256)
    stream.push(0, count, _wire([1, 2, 3]), True, 0.0)

    assert stream.stats.rejected_batches == 1
    assert stream.stats.batches == 0
    assert stream.available is None


# -- health ----------------------------------------------------------------


def test_an_unhealthy_batch_condemns_only_the_slices_that_overlap_it():
    """Health is per-sample-range, so one bad batch does not void the night."""
    stream = SeismicStream(capacity=256)
    _push(stream, 0, ok=True)
    _push(stream, BATCH, ok=False)
    _push(stream, 2 * BATCH, ok=True)

    assert stream.stats.unhealthy_batches == 1
    bad = stream.slice(BATCH, BATCH)
    assert bad is not None and bad.geophone_ok is False
    good = stream.slice(2 * BATCH, BATCH)
    assert good is not None and good.geophone_ok is True
    spanning = stream.slice(0, 2 * BATCH)
    assert spanning is not None and spanning.geophone_ok is False


# -- eviction --------------------------------------------------------------


def test_the_ring_drops_the_oldest_samples_and_says_so():
    """Eviction is visible in `available`, never inferred from a short read."""
    capacity = 4 * BATCH
    stream = SeismicStream(capacity=capacity)
    for i in range(6):
        _push(stream, i * BATCH)

    first, held = stream.available
    assert held == capacity
    assert first == 2 * BATCH


def test_a_request_that_has_aged_out_returns_nothing_rather_than_a_shifted_slice():
    """Returning what is left would stamp surviving samples with wrong indices."""
    capacity = 4 * BATCH
    stream = SeismicStream(capacity=capacity)
    for i in range(6):
        _push(stream, i * BATCH)

    assert stream.slice(0, BATCH) is None
    assert stream.slice(BATCH, 2 * BATCH) is None, "a half-evicted span is still unusable"
    survivor = stream.slice(2 * BATCH, BATCH)
    assert survivor is not None
    assert list(survivor.counts) == _ramp(2 * BATCH, BATCH)


def test_a_gap_that_has_aged_out_stops_being_reported():
    """A hole outside the buffer is history, not a property of what is held."""
    capacity = 4 * BATCH
    stream = SeismicStream(capacity=capacity, max_gap_samples=capacity)
    _push(stream, 0)
    _push(stream, 2 * BATCH)  # gap at [BATCH, 2*BATCH)
    for i in range(3, 8):
        _push(stream, i * BATCH)

    got = stream.slice(*stream.available)
    assert got is not None
    assert got.gaps == ()
    # The running counters still remember it - they are the night's tally, not
    # a property of what the ring currently holds.
    assert stream.stats.gaps == 1


def test_the_bookkeeping_stays_bounded_over_a_long_run():
    """The reason _evict_locked() prunes, which no slice can show.

    Clipping already hides an aged-out gap from every slice, so correctness
    does not depend on pruning. What does depend on it is the node staying
    up: this runs at ~8 batches a second for as long as the node is
    powered, and a per-batch record that is appended and never dropped is
    an unbounded list on a device with no one watching it. The lists are
    read directly here because there is no other way to observe a leak -
    by the time it is visible from outside, it is a field failure.
    """
    capacity = 8 * BATCH
    stream = SeismicStream(capacity=capacity, max_gap_samples=capacity)
    index = 0
    for i in range(400):
        if i % 5 == 4:
            index += BATCH  # skip one, so gaps accumulate too
        _push(stream, index)
        index += BATCH

    ceiling = capacity // BATCH + 2
    assert len(stream._arrivals) <= ceiling, "arrival stamps are never dropped"
    assert len(stream._gaps) <= ceiling, "gap records are never dropped"
    assert len(stream._unhealthy) <= ceiling
    # ... and the counters still carry the night's totals, which is where
    # the history is supposed to live.
    assert stream.stats.batches == 400
    assert stream.stats.gaps == 80


def test_latest_returns_the_newest_span():
    """The recorder's common case: the last N samples, or nothing."""
    stream = SeismicStream(capacity=256)
    _push(stream, 0)
    _push(stream, BATCH)

    got = stream.latest(BATCH)
    assert got is not None
    assert got.first_sample_index == BATCH
    assert list(got.counts) == _ramp(BATCH, BATCH)
    assert stream.latest(3 * BATCH) is None


# -- units and clock -------------------------------------------------------


def test_the_slice_carries_the_scale_needed_to_read_it_back():
    """Counts plus their volts-per-LSB, so a stored record stays self-describing."""
    stream = SeismicStream(capacity=256)
    stream.push(0, 2, _wire([1000, -2000]), True, 0.0)

    got = stream.slice(0, 2)
    assert got is not None
    assert got.lsb_volts == config.SEISMIC_LSB_VOLTS
    assert got.volts == pytest.approx(
        (1000 * config.SEISMIC_LSB_VOLTS, -2000 * config.SEISMIC_LSB_VOLTS)
    )


def test_a_sample_index_maps_back_onto_the_monotonic_clock():
    """Interpolated backwards from the batch's arrival stamp."""
    stream = SeismicStream(capacity=256)
    arrived = 1234.5
    _push(stream, 0, at=arrived)

    period = 1.0 / config.SEISMIC_SAMPLE_RATE_HZ
    assert stream.monotonic_at(BATCH - 1) == pytest.approx(arrived - period)
    assert stream.monotonic_at(0) == pytest.approx(arrived - BATCH * period)
    assert stream.monotonic_at(BATCH) is None, "a sample nobody sent has no timestamp"


def test_relative_timing_comes_from_the_indices_not_the_arrival_clock():
    """Two batches that arrived late and bunched still read 128 ms apart.

    This is why gait cadence survives the unmeasured Bridge latency: the only
    thing it depends on is the sample index difference.
    """
    stream = SeismicStream(capacity=256)
    _push(stream, 0, at=100.0)
    _push(stream, BATCH, at=100.001)  # both arrived in the same breath

    got = stream.slice(0, 2 * BATCH)
    assert got is not None
    assert len(got) == 2 * BATCH
    assert got.gaps == ()


# -- concurrency -----------------------------------------------------------


def test_pushing_and_slicing_from_two_threads_does_not_corrupt_the_record():
    """push() is the Bridge's RPC thread; the readers are the vision watch's."""
    stream = SeismicStream(capacity=4096)
    total = 200
    errors: list[BaseException] = []

    def writer():
        try:
            for i in range(total):
                _push(stream, i * BATCH)
        except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
            errors.append(exc)

    def reader():
        try:
            for _ in range(total):
                span = stream.available
                if span is None:
                    continue
                got = stream.slice(*span)
                if got is not None:
                    assert len(got) == span[1]
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors
    assert stream.stats.batches == total
    assert stream.stats.gaps == 0


# -- placing the record on the clock ---------------------------------------
#
# span() is the recorder's only read (ADR 0035): it asks in monotonic seconds,
# because that is the clock the camera frames carry, and gets back samples. The
# failures worth testing are the quiet ones - a window that silently returns
# the wrong samples, or returns nothing where it should have clamped - because
# both produce a record whose waveform does not match its boxes and nothing
# downstream can tell.

RATE = config.SEISMIC_SAMPLE_RATE_HZ


def _timed(stream, first, at, count=BATCH):
    """Push a batch whose last sample was taken at `at`."""
    _push(stream, first, count, at=at)


def _three_batches(stream):
    """96 samples, indices 0-95, ending at monotonic 10.256."""
    period = BATCH / RATE
    for i in range(3):
        _timed(stream, i * BATCH, 10.0 + i * period)
    return 10.0 - period, 10.0 + 2 * period


def test_sample_index_at_inverts_monotonic_at_exactly():
    """The round trip has to be exact, or a box lands on the wrong footfall.

    Both directions share one nominal rate and one arrival stamp, so whatever
    the unmeasured transport latency turns out to be, it cancels: a frame
    placed at a sample and read back lands on the same sample.
    """
    stream = SeismicStream(capacity=256)
    _three_batches(stream)

    for index in range(96):
        when = stream.monotonic_at(index)
        assert when is not None
        assert stream.sample_index_at(when) == index


def test_sample_index_at_extrapolates_past_the_newest_batch():
    """Total by construction, because the recorder asks about `now`.

    span()'s end is time.monotonic() at the moment of the write, which is
    always after the last sample that arrived. Returning None there would
    throw away the whole record rather than clamping to what is held.
    """
    stream = SeismicStream(capacity=256)
    _three_batches(stream)

    assert stream.sample_index_at(10.256 + 1.0) == 96 + RATE


def test_sample_index_at_extrapolates_before_the_oldest_batch():
    """The pre-roll reaches back before anything the stream holds."""
    stream = SeismicStream(capacity=256)
    _three_batches(stream)

    assert stream.sample_index_at(10.0 - BATCH / RATE - 1.0) == (-RATE) % _INDEX_MODULUS


def test_sample_index_at_on_an_empty_stream_is_none():
    """Nothing has arrived, so there is no clock to place anything against."""
    assert SeismicStream(capacity=256).sample_index_at(10.0) is None


def test_span_returns_exactly_the_window_asked_for():
    """The ordinary case: a window wholly inside what is held."""
    stream = SeismicStream(capacity=256)
    _three_batches(stream)

    got = stream.span(stream.monotonic_at(10), stream.monotonic_at(20))
    assert got is not None
    assert got.first_sample_index == 10
    assert list(got.counts) == _ramp(10, 11)


def test_span_clamps_a_pre_roll_that_reaches_before_the_buffer():
    """A 5 s pre-roll against a 1 s buffer must return the 1 s, not nothing.

    This is the normal state early in a run and after a restart. Failing the
    read instead of clamping it would lose every record until the ring filled.
    """
    stream = SeismicStream(capacity=256)
    first_s, last_s = _three_batches(stream)

    got = stream.span(first_s - 5.0, last_s)
    assert got is not None
    assert got.first_sample_index == 0
    assert len(got) == 96


def test_span_clamps_an_end_that_runs_past_the_newest_sample():
    """time.monotonic() at write time is always after the last batch."""
    stream = SeismicStream(capacity=256)
    first_s, last_s = _three_batches(stream)

    got = stream.span(first_s, last_s + 5.0)
    assert got is not None
    assert len(got) == 96


def test_span_wholly_before_the_buffer_is_none_not_a_clamped_lie():
    """An empty intersection must read as empty.

    Clamping both ends of a window that ended before the first sample arrived
    would hand back the oldest samples held and date them to the request -
    a record whose waveform is minutes away from its own boxes.
    """
    stream = SeismicStream(capacity=256)
    _three_batches(stream)

    assert stream.span(1.0, 2.0) is None


def test_span_wholly_after_the_buffer_is_none():
    """The mirror case, which a naive modular comparison gets wrong."""
    stream = SeismicStream(capacity=256)
    _three_batches(stream)

    assert stream.span(30.0, 31.0) is None


def test_span_on_an_empty_stream_is_none():
    """No registration yet, or no geophone - the common state today."""
    assert SeismicStream(capacity=256).span(0.0, 100.0) is None


def test_span_survives_the_uint32_sample_counter_wrapping():
    """198 days of uptime must not cost a night's records.

    The counter wraps, so the oldest sample held can have a *higher* raw index
    than the newest. Comparing them unsigned turns a routine under-run into a
    four-billion-sample gap.
    """
    stream = SeismicStream(capacity=256)
    start = _INDEX_MODULUS - BATCH
    period = BATCH / RATE
    _timed(stream, start, 10.0)
    _timed(stream, 0, 10.0 + period)

    got = stream.span(10.0 - period, 10.0 + period)
    assert got is not None
    assert got.first_sample_index == start
    assert len(got) == 2 * BATCH
    assert got.gaps == ()


def test_signed_offset_reads_a_wrapped_index_as_a_small_negative():
    """The one line that makes the wrap case work, asserted on its own."""
    assert _signed_offset(5, 3) == 2
    assert _signed_offset(3, 5) == -2
    assert _signed_offset(_INDEX_MODULUS - 1, 1) == -2
    assert _signed_offset(1, _INDEX_MODULUS - 1) == 2
