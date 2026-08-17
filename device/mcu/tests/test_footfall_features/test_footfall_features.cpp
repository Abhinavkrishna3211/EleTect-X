// Known-answer tests for the footfall probability/feature placeholder
// (ENGINEERING_CONVENTIONS.md 4). Every failure names the input that
// tripped it, not a bare assert.

#include <unity.h>

#include <cstddef>

#include "footfall_features.h"
#include "sta_lta.h"

void setUp() {}
void tearDown() {}

static void test_probability_at_or_below_unity_is_zero(void) {
  TEST_ASSERT_EQUAL_FLOAT_MESSAGE(
      0.0f, footfall_probability_from_ratio(1.0f),
      "peak_ratio == 1.0 (sta == lta, no signal) must map to exactly 0");
  TEST_ASSERT_EQUAL_FLOAT_MESSAGE(
      0.0f, footfall_probability_from_ratio(0.5f),
      "a below-unity ratio must never produce a negative probability");
}

// Anchor 1: the real bench stomp-test's quiet-floor ceiling
// (docs/KNOWN_GAPS.md, 2026-08-14) must map near 0.
static void test_probability_near_zero_at_quiet_floor(void) {
  const float probability = footfall_probability_from_ratio(1.13f);
  TEST_ASSERT_TRUE_MESSAGE(
      probability < 0.15f,
      "the real quiet-floor ceiling ratio (1.13) must map well under 0.5, "
      "not read as a plausible footfall");
}

// Anchor 2: the real bench stomp-test's own trigger ratio must map high.
static void test_probability_high_at_real_stomp_ratio(void) {
  const float probability = footfall_probability_from_ratio(4.60f);
  TEST_ASSERT_TRUE_MESSAGE(
      probability > 0.8f,
      "the real stomp-test ratio (4.60) must map to a high probability");
  TEST_ASSERT_TRUE_MESSAGE(
      probability < 1.0f,
      "the placeholder must saturate, not hard-clamp exactly at the one "
      "trial that anchored it");
}

static void test_probability_is_monotonic_in_ratio(void) {
  TEST_ASSERT_TRUE_MESSAGE(
      footfall_probability_from_ratio(2.0f) < footfall_probability_from_ratio(6.0f),
      "a higher STA/LTA ratio must never map to a lower probability");
}

// Hand-computable feature vector: a window whose values are known exactly,
// paired with a hand-built sta_lta_result so every one of the 8 slots has a
// provably correct expected value.
static void test_feature_vector_matches_hand_computed_stats(void) {
  const size_t n = 4;
  const float window[n] = {1.0f, 2.0f, 3.0f, 4.0f};  // mean 2.5, popstdev sqrt(1.25)

  sta_lta_result result{};
  result.sta = 9.0f;
  result.lta = 3.0f;
  result.peak_ratio = 3.0f;
  result.trigger_index = 42;
  result.triggered = true;

  float out[8];
  footfall_feature_vector(window, n, result, out);

  TEST_ASSERT_EQUAL_FLOAT_MESSAGE(9.0f, out[0], "out[0] must be result.sta");
  TEST_ASSERT_EQUAL_FLOAT_MESSAGE(3.0f, out[1], "out[1] must be result.lta");
  TEST_ASSERT_EQUAL_FLOAT_MESSAGE(3.0f, out[2], "out[2] must be result.peak_ratio");
  TEST_ASSERT_EQUAL_FLOAT_MESSAGE(42.0f, out[3], "out[3] must be result.trigger_index as float");
  TEST_ASSERT_EQUAL_FLOAT_MESSAGE(1.0f, out[4], "out[4] must be the window minimum");
  TEST_ASSERT_EQUAL_FLOAT_MESSAGE(4.0f, out[5], "out[5] must be the window maximum");
  TEST_ASSERT_EQUAL_FLOAT_MESSAGE(2.5f, out[6], "out[6] must be the window mean");
  TEST_ASSERT_FLOAT_WITHIN_MESSAGE(0.0001f, 1.118034f, out[7],
                                    "out[7] must be the population stdev, sqrt(1.25)");
}

// The read_seismic_window() timeout contract returns a zero-filled array -
// feeding n == 0 straight in must not read out of bounds.
static void test_feature_vector_empty_window_is_safe(void) {
  sta_lta_result result{};
  result.sta = 0.0f;
  result.lta = 0.0f;
  result.peak_ratio = 0.0f;
  result.trigger_index = 0;
  result.triggered = false;

  float out[8];
  footfall_feature_vector(nullptr, 0, result, out);

  TEST_ASSERT_EQUAL_FLOAT_MESSAGE(0.0f, out[4], "min must be 0.0 on an empty window, not garbage");
  TEST_ASSERT_EQUAL_FLOAT_MESSAGE(0.0f, out[5], "max must be 0.0 on an empty window, not garbage");
  TEST_ASSERT_EQUAL_FLOAT_MESSAGE(0.0f, out[6], "mean must be 0.0 on an empty window, not garbage");
  TEST_ASSERT_EQUAL_FLOAT_MESSAGE(0.0f, out[7], "stdev must be 0.0 on an empty window, not garbage");
}

int main(int, char **) {
  UNITY_BEGIN();
  RUN_TEST(test_probability_at_or_below_unity_is_zero);
  RUN_TEST(test_probability_near_zero_at_quiet_floor);
  RUN_TEST(test_probability_high_at_real_stomp_ratio);
  RUN_TEST(test_probability_is_monotonic_in_ratio);
  RUN_TEST(test_feature_vector_matches_hand_computed_stats);
  RUN_TEST(test_feature_vector_empty_window_is_safe);
  return UNITY_END();
}
