// Known-answer tests for the seismic batch accumulator (ADR 0035,
// ENGINEERING_CONVENTIONS.md 4). Every failure names the input that tripped
// it, not a bare assert.
//
// The accumulator is compiled unconditionally here even though
// SEISMIC_CAPTURE_ENABLED defaults to 0 in the field: the flag gates whether
// geophone.cpp *calls* this, not whether the logic is correct, and a core
// that is only ever built by a flag nobody sets is a core nobody tests.

#include <unity.h>

#include <cstddef>
#include <cstdint>

#include "seismic_capture.h"

static seismic_capture_state g_state;

void setUp() { seismic_capture_reset(&g_state); }
void tearDown() {}

// Fills one whole batch starting at `first`, returning it through `out`.
// Fails the test if the batch does not close on exactly the last sample.
static void fill_one_batch(uint32_t first, int16_t value, bool ok, seismic_batch *out) {
  for (size_t i = 0; i < SEISMIC_CAPTURE_BATCH_SAMPLES; ++i) {
    const bool closed =
        seismic_capture_push(&g_state, value, first + static_cast<uint32_t>(i), ok, out);
    if (i + 1 < SEISMIC_CAPTURE_BATCH_SAMPLES) {
      TEST_ASSERT_FALSE_MESSAGE(closed, "a batch closed before it was full");
    } else {
      TEST_ASSERT_TRUE_MESSAGE(closed, "a batch did not close on its last sample");
    }
  }
}

static void test_a_batch_closes_only_when_full(void) {
  seismic_batch batch;
  for (size_t i = 0; i + 1 < SEISMIC_CAPTURE_BATCH_SAMPLES; ++i) {
    TEST_ASSERT_FALSE_MESSAGE(
        seismic_capture_push(&g_state, 7, static_cast<uint32_t>(i), true, &batch),
        "a partially-filled batch must not be emitted - a short batch on the wire is "
        "indistinguishable from a gap");
  }
  TEST_ASSERT_TRUE(seismic_capture_push(
      &g_state, 7, static_cast<uint32_t>(SEISMIC_CAPTURE_BATCH_SAMPLES - 1), true, &batch));
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(SEISMIC_CAPTURE_BATCH_SAMPLES, batch.count,
                                  "a full batch must report its full length");
  TEST_ASSERT_EQUAL_UINT32_MESSAGE(0, batch.first_sample_index,
                                   "the batch must be stamped with its first sample's index, "
                                   "not its last");
}

// The property the whole dataset rests on: batch N+1 begins exactly where
// batch N ended, so concatenating them is lossless and a hole is arithmetic,
// not guesswork.
static void test_consecutive_batches_are_index_contiguous(void) {
  seismic_batch first;
  seismic_batch second;
  fill_one_batch(0, 11, true, &first);
  fill_one_batch(SEISMIC_CAPTURE_BATCH_SAMPLES, 22, true, &second);

  TEST_ASSERT_EQUAL_UINT32_MESSAGE(
      first.first_sample_index + first.count, second.first_sample_index,
      "consecutive batches must abut exactly - any other relationship means the MPU "
      "cannot tell a real gap from a counting error");
}

// A discontinuity must appear *between* two batches, never be swallowed
// inside one. Swallowing it is the specific failure the plan calls
// "papering over" a gap: the samples either side are real, the join is not.
static void test_an_out_of_sequence_sample_closes_the_batch_short(void) {
  seismic_batch batch;
  TEST_ASSERT_FALSE(seismic_capture_push(&g_state, 1, 100, true, &batch));
  TEST_ASSERT_FALSE(seismic_capture_push(&g_state, 2, 101, true, &batch));

  // 102 is expected; 500 means 398 samples were lost in transit or the
  // sampler stalled.
  TEST_ASSERT_TRUE_MESSAGE(
      seismic_capture_push(&g_state, 3, 500, true, &batch),
      "a sample that does not continue the batch must flush what came before it");
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(2, batch.count,
                                  "the flushed batch must hold only the contiguous run that "
                                  "preceded the discontinuity");
  TEST_ASSERT_EQUAL_UINT32_MESSAGE(100, batch.first_sample_index,
                                   "the flushed batch keeps its own start index");

  // And the sample that caused the flush is not lost - it opens the next
  // batch, whose index exposes the gap.
  seismic_batch next;
  for (size_t i = 1; i < SEISMIC_CAPTURE_BATCH_SAMPLES; ++i) {
    seismic_capture_push(&g_state, 3, 500 + static_cast<uint32_t>(i), true, &next);
  }
  TEST_ASSERT_EQUAL_UINT32_MESSAGE(500, next.first_sample_index,
                                   "the out-of-sequence sample must begin the next batch, not "
                                   "be dropped");
}

static void test_a_short_batch_has_no_stale_tail(void) {
  seismic_batch batch;
  seismic_capture_push(&g_state, 1234, 0, true, &batch);
  seismic_capture_push(&g_state, 5678, 1, true, &batch);
  TEST_ASSERT_TRUE(seismic_capture_push(&g_state, 9, 999, true, &batch));

  TEST_ASSERT_EQUAL_INT16(1234, batch.samples[0]);
  TEST_ASSERT_EQUAL_INT16(5678, batch.samples[1]);
  for (size_t i = batch.count; i < SEISMIC_CAPTURE_BATCH_SAMPLES; ++i) {
    TEST_ASSERT_EQUAL_INT16_MESSAGE(0, batch.samples[i],
                                    "the array is sent in full, so anything past `count` must "
                                    "be zeroed - otherwise a short batch ships the previous "
                                    "batch's ground motion as if it were its own");
  }
}

// Health is conservative on purpose: a batch is only trustworthy if the
// sensor was trustworthy throughout it. Partly-stale data labelled healthy
// is worse than data labelled unhealthy, because only one of those gets
// filtered out of a training set.
static void test_one_unhealthy_sample_condemns_the_whole_batch(void) {
  seismic_batch batch;
  for (size_t i = 0; i < SEISMIC_CAPTURE_BATCH_SAMPLES; ++i) {
    const bool ok = (i != 3);
    seismic_capture_push(&g_state, 5, static_cast<uint32_t>(i), ok, &batch);
  }
  TEST_ASSERT_FALSE_MESSAGE(batch.geophone_ok,
                            "a batch containing even one unhealthy sample must not report "
                            "healthy");
}

static void test_recovery_mid_batch_cannot_launder_the_samples_before_it(void) {
  seismic_batch batch;
  // Unhealthy for the first half, healthy for the second. The naive
  // implementation - storing the latest sample's health - reports true here.
  for (size_t i = 0; i < SEISMIC_CAPTURE_BATCH_SAMPLES; ++i) {
    const bool ok = (i >= SEISMIC_CAPTURE_BATCH_SAMPLES / 2);
    seismic_capture_push(&g_state, 5, static_cast<uint32_t>(i), ok, &batch);
  }
  TEST_ASSERT_FALSE_MESSAGE(batch.geophone_ok,
                            "a sensor that recovers part-way through a batch must not relabel "
                            "the stale samples in front of it as good");
}

// geophone_sample_count() is documented as never saturating, which means it
// wraps. The wrap must read as continuous - a false gap once every 4.3
// billion samples is still a corrupted record, and unsigned arithmetic makes
// handling it free.
static void test_the_sample_counter_wrapping_is_not_a_gap(void) {
  seismic_batch batch;
  const uint32_t near_end = 0xFFFFFFFFU;
  TEST_ASSERT_FALSE(seismic_capture_push(&g_state, 1, near_end, true, &batch));
  TEST_ASSERT_FALSE_MESSAGE(
      seismic_capture_push(&g_state, 2, 0, true, &batch),
      "0xFFFFFFFF followed by 0 is the counter wrapping, not 4 billion lost samples - "
      "it must not flush the batch");
}

// A runtime mirror of the header's static_assert. The static_assert is the
// real guard; this exists so the budget shows up as a named, readable test
// failure if someone raises the batch size, rather than as a compiler error
// in a header they were not editing.
static void test_a_full_batch_fits_one_bridge_message(void) {
  const size_t encoded = seismic_capture_encoded_bytes(SEISMIC_CAPTURE_BATCH_SAMPLES);
  TEST_ASSERT_TRUE_MESSAGE(encoded <= BRIDGE_MAX_MESSAGE_BYTES,
                           "a batch notify must fit the Bridge's 256-byte cap - an oversized "
                           "notify is dropped silently, so this cannot fail at runtime where "
                           "anyone would see it");
  TEST_ASSERT_TRUE_MESSAGE(encoded + 32U <= BRIDGE_MAX_MESSAGE_BYTES,
                           "the budget is computed, never measured - keep at least 32 bytes of "
                           "slack for envelope overhead this arithmetic may have missed");
}

static void test_the_batch_divides_a_window_evenly(void) {
  TEST_ASSERT_EQUAL_UINT_MESSAGE(
      0, SEISMIC_WINDOW_SAMPLES % SEISMIC_CAPTURE_BATCH_SAMPLES,
      "a batch must tile a window exactly, so a batch boundary never falls inside a "
      "window boundary on the MPU's side");
}

int main(int, char **) {
  UNITY_BEGIN();
  RUN_TEST(test_a_batch_closes_only_when_full);
  RUN_TEST(test_consecutive_batches_are_index_contiguous);
  RUN_TEST(test_an_out_of_sequence_sample_closes_the_batch_short);
  RUN_TEST(test_a_short_batch_has_no_stale_tail);
  RUN_TEST(test_one_unhealthy_sample_condemns_the_whole_batch);
  RUN_TEST(test_recovery_mid_batch_cannot_launder_the_samples_before_it);
  RUN_TEST(test_the_sample_counter_wrapping_is_not_a_gap);
  RUN_TEST(test_a_full_batch_fits_one_bridge_message);
  RUN_TEST(test_the_batch_divides_a_window_evenly);
  return UNITY_END();
}
