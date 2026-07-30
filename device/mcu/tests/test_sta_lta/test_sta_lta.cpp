// Known-answer tests for the STA/LTA pure core (ENGINEERING_CONVENTIONS.md 4).
// Every failure names the threshold and the input that tripped it, not a bare
// assert.

#include <unity.h>

#include <cstddef>
#include <cstdint>

#include "sta_lta.h"

void setUp() {}
void tearDown() {}

// A hand-constructed trace where the mean-abs ratio is exactly computable on
// paper: 250 quiet samples at amplitude 1.0, followed by 25 burst samples at
// amplitude 8.0. Once the windows have fully slid onto the burst tail,
// STA (25 samples, all 8.0) / LTA (250 samples, 225 at 1.0 + 25 at 8.0):
//   STA = 8.0
//   LTA = (225 * 1.0 + 25 * 8.0) / 250 = (225 + 200) / 250 = 1.7
//   ratio = 8.0 / 1.7 = 4.70588...
static void test_known_answer_ratio_at_full_overlap(void) {
  const size_t lta_n = 250;
  const size_t sta_n = 25;
  const size_t n = lta_n + sta_n;  // 275: burst fully inside both windows
  float trace[n];
  for (size_t i = 0; i < lta_n; ++i) {
    trace[i] = 1.0f;
  }
  for (size_t i = lta_n; i < n; ++i) {
    trace[i] = 8.0f;
  }

  const sta_lta_result result =
      sta_lta_detect(trace, n, sta_n, lta_n, 4.0f);

  TEST_ASSERT_TRUE_MESSAGE(result.triggered,
                            "expected trigger on 8x quiet-to-burst step");
  TEST_ASSERT_FLOAT_WITHIN_MESSAGE(
      0.001f, 4.70588f, result.peak_ratio,
      "STA/LTA ratio at full overlap must equal the hand-computed value");
  TEST_ASSERT_FLOAT_WITHIN_MESSAGE(0.001f, 8.0f, result.sta,
                                    "STA must equal the burst amplitude once "
                                    "the short window is fully inside it");
  TEST_ASSERT_FLOAT_WITHIN_MESSAGE(
      0.001f, 1.7f, result.lta,
      "LTA must equal the exact 225x1.0 + 25x8.0 blended mean");
}

// Deterministic synthetic trigger: low-amplitude noise-like trace (alternating
// +/-0.1, not a true RNG - the point is a known, reproducible non-constant
// baseline) with a sharp 10x-amplitude burst inserted at a known index.
static void test_synthetic_trigger_fires_near_burst_onset(void) {
  const size_t lta_n = 250;
  const size_t sta_n = 25;
  const size_t n = 512;
  const size_t burst_onset = 400;
  float trace[n];
  for (size_t i = 0; i < n; ++i) {
    trace[i] = (i % 2 == 0) ? 0.1f : -0.1f;
  }
  for (size_t i = burst_onset; i < burst_onset + sta_n && i < n; ++i) {
    trace[i] = (i % 2 == 0) ? 1.0f : -1.0f;
  }

  const sta_lta_result result =
      sta_lta_detect(trace, n, sta_n, lta_n, 4.0f);

  TEST_ASSERT_TRUE_MESSAGE(
      result.triggered, "expected trigger: 10x amplitude step over baseline");
  TEST_ASSERT_TRUE_MESSAGE(
      result.trigger_index >= burst_onset &&
          result.trigger_index <= burst_onset + sta_n + lta_n,
      "trigger_index must land at or after the burst onset, within one "
      "window's slide of it");
}

// Pure noise-like trace, no burst: must not trigger.
static void test_no_false_trigger_on_flat_amplitude(void) {
  const size_t lta_n = 250;
  const size_t sta_n = 25;
  const size_t n = 512;
  float trace[n];
  for (size_t i = 0; i < n; ++i) {
    trace[i] = (i % 3 == 0) ? 0.2f : -0.15f;
  }

  const sta_lta_result result =
      sta_lta_detect(trace, n, sta_n, lta_n, 4.0f);

  TEST_ASSERT_FALSE_MESSAGE(
      result.triggered,
      "flat-amplitude trace must not cross a 4.0x STA/LTA ratio");
}

// The read_seismic_window() timeout contract returns a zero-filled array.
// Feeding that straight in must report no trigger, not divide by zero.
static void test_zero_filled_window_does_not_trigger_or_crash(void) {
  const size_t lta_n = 250;
  const size_t sta_n = 25;
  const size_t n = 512;
  float trace[n] = {};  // zero-filled, matches the ADC-timeout contract

  const sta_lta_result result =
      sta_lta_detect(trace, n, sta_n, lta_n, 4.0f);

  TEST_ASSERT_FALSE_MESSAGE(
      result.triggered,
      "an all-zero (timed-out) window must never report a trigger");
  TEST_ASSERT_EQUAL_FLOAT_MESSAGE(
      0.0f, result.peak_ratio,
      "an all-zero window must report peak_ratio 0.0, not NaN/inf from a "
      "0/0 division");
}

// lta_n > n is a caller error (a shorter buffer than the long-term window
// needs); must fail safe, not read out of bounds.
static void test_lta_longer_than_buffer_is_safe(void) {
  const size_t n = 100;
  float trace[n];
  for (size_t i = 0; i < n; ++i) {
    trace[i] = 1.0f;
  }

  const sta_lta_result result = sta_lta_detect(trace, n, 25, 250, 4.0f);

  TEST_ASSERT_FALSE_MESSAGE(
      result.triggered,
      "lta_n > n must return triggered=false, not read past the buffer");
}

// n == 0 is the emptiest degenerate case.
static void test_empty_buffer_is_safe(void) {
  const sta_lta_result result = sta_lta_detect(nullptr, 0, 25, 250, 4.0f);

  TEST_ASSERT_FALSE_MESSAGE(result.triggered,
                            "an empty/null buffer must never trigger");
}

int main(int, char **) {
  UNITY_BEGIN();
  RUN_TEST(test_known_answer_ratio_at_full_overlap);
  RUN_TEST(test_synthetic_trigger_fires_near_burst_onset);
  RUN_TEST(test_no_false_trigger_on_flat_amplitude);
  RUN_TEST(test_zero_filled_window_does_not_trigger_or_crash);
  RUN_TEST(test_lta_longer_than_buffer_is_safe);
  RUN_TEST(test_empty_buffer_is_safe);
  return UNITY_END();
}
