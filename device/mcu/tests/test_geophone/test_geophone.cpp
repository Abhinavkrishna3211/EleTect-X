// Behavioral tests for geophone.cpp's ADC sampling-cadence gate
// (ENGINEERING_CONVENTIONS.md 4) - covers the fix for "ads1115_read_
// conversion never polls the ready bit" (KNOWN_GAPS.md): geophone_service()
// must not read and ring-buffer the same ADS1115 conversion twice.
//
// geophone.cpp talks to real hardware (Wire), so this isn't a pure-core
// known-answer test - it uses the host Wire stub (always succeeds, raw=0)
// and hostshim::advance_millis() to drive simulated time deterministically,
// without a real ADS1115 or a wall-clock wait.

#include <unity.h>

#include "Arduino.h"
#include "config.h"
#include "geophone.h"

void setUp() {
  hostshim::reset();
  geophone_init();
}

void tearDown() {}

static void test_rapid_calls_at_frozen_time_do_not_fill_the_window(void) {
  // 600 back-to-back calls with no simulated time advance between them -
  // this executes in well under a millisecond on host, nowhere near the
  // 512 * 4ms = 2048ms the buffer would need to actually fill at the
  // nominal sample rate. Without the cadence gate, every one of these would
  // have counted as a distinct sample and filled the 512-sample buffer.
  for (int i = 0; i < 600; ++i) {
    geophone_service();
  }

  float window[SEISMIC_WINDOW_SAMPLES];
  read_seismic_window(window);

  TEST_ASSERT_FALSE_MESSAGE(
      geophone_ok(),
      "600 service() calls with no simulated time elapsed must not fill the "
      "window - the sampling-cadence gate must reject nearly all of them");
  for (size_t i = 0; i < SEISMIC_WINDOW_SAMPLES; ++i) {
    TEST_ASSERT_EQUAL_FLOAT_MESSAGE(
        0.0f, window[i],
        "an unfilled window must read back zero-filled, per "
        "read_seismic_window()'s documented failure contract");
  }
}

static void test_calls_paced_at_the_sample_period_fill_the_window(void) {
  // Mirrors real cadence: advance simulated time by exactly one sample
  // period before each call, same as an ADS1115 continuous conversion
  // becoming available every 1000/SEISMIC_SAMPLE_RATE_HZ ms. Also exercises
  // the gate's boundary-inclusive behavior (>= one period is accepted, same
  // convention as rule_gate_apply()'s cooldown boundary).
  const uint32_t period_ms = 1000 / SEISMIC_SAMPLE_RATE_HZ;
  for (size_t i = 0; i < SEISMIC_WINDOW_SAMPLES; ++i) {
    hostshim::advance_millis(period_ms);
    geophone_service();
  }

  // geophone_ok() only reflects "window full and fresh" once
  // read_seismic_window() has applied that check as a side effect - right
  // after geophone_init() it is already true (the host Wire stub's config
  // write always "succeeds"), so it is not itself proof of a full window.
  float window[SEISMIC_WINDOW_SAMPLES];
  read_seismic_window(window);

  TEST_ASSERT_TRUE_MESSAGE(
      geophone_ok(),
      "SEISMIC_WINDOW_SAMPLES calls paced at the nominal sample period must "
      "fill the window and report ok - the gate must not be so aggressive "
      "it blocks correctly-paced sampling");
}

static void test_call_before_the_sample_period_elapses_is_skipped(void) {
  const uint32_t period_ms = 1000 / SEISMIC_SAMPLE_RATE_HZ;
  float window[SEISMIC_WINDOW_SAMPLES];

  // Fill the window to exactly one sample short of full, correctly paced.
  for (size_t i = 0; i < SEISMIC_WINDOW_SAMPLES - 1; ++i) {
    hostshim::advance_millis(period_ms);
    geophone_service();
  }
  read_seismic_window(window);
  TEST_ASSERT_FALSE_MESSAGE(geophone_ok(),
                             "window must not report ok one sample short of full");

  // Too early: under one full period since the last *accepted* poll.
  hostshim::advance_millis(period_ms - 1);
  geophone_service();
  read_seismic_window(window);
  TEST_ASSERT_FALSE_MESSAGE(
      geophone_ok(),
      "a call before a full sample period has elapsed since the last "
      "accepted poll must be skipped, not counted toward the window");

  // Completes exactly one period since the last *accepted* poll - if a
  // rejected attempt wrongly reset the gate's timer, this would still be one
  // sample short and the window would stay unfilled.
  hostshim::advance_millis(1);
  geophone_service();
  read_seismic_window(window);
  TEST_ASSERT_TRUE_MESSAGE(
      geophone_ok(),
      "once a full period has elapsed since the last accepted poll, the "
      "window completes - a skipped attempt must not have consumed the gate");
}

static void test_sample_count_only_advances_on_accepted_samples(void) {
  // geophone_sample_count() is what state_machine.cpp's kSensing case polls
  // to decide whether a new window is worth re-running the STA/LTA slide
  // for - it must track *accepted* samples only, same population the ring
  // buffer/g_samples_written count, not every geophone_service() call.
  TEST_ASSERT_EQUAL_UINT32(0, geophone_sample_count());

  // Rejected by the cadence gate: no simulated time advance, so none of
  // these should move the counter.
  for (int i = 0; i < 50; ++i) {
    geophone_service();
  }
  TEST_ASSERT_EQUAL_UINT32_MESSAGE(
      0, geophone_sample_count(),
      "calls rejected by the cadence gate must not advance the sample count");

  const uint32_t period_ms = 1000 / SEISMIC_SAMPLE_RATE_HZ;
  for (uint32_t i = 1; i <= 10; ++i) {
    hostshim::advance_millis(period_ms);
    geophone_service();
    TEST_ASSERT_EQUAL_UINT32_MESSAGE(
        i, geophone_sample_count(),
        "each correctly-paced accepted sample must advance the count by "
        "exactly one");
  }
}

static void test_sample_count_keeps_advancing_past_window_fullness(void) {
  // Unlike g_samples_written (which saturates at SEISMIC_WINDOW_SAMPLES),
  // geophone_sample_count() must keep counting past a full window - the
  // kSensing gate compares successive reads for inequality for the life of
  // the device, not just until the ring buffer first fills.
  const uint32_t period_ms = 1000 / SEISMIC_SAMPLE_RATE_HZ;
  for (size_t i = 0; i < SEISMIC_WINDOW_SAMPLES + 5; ++i) {
    hostshim::advance_millis(period_ms);
    geophone_service();
  }
  TEST_ASSERT_EQUAL_UINT32(SEISMIC_WINDOW_SAMPLES + 5, geophone_sample_count());
}

int main(int, char **) {
  UNITY_BEGIN();
  RUN_TEST(test_rapid_calls_at_frozen_time_do_not_fill_the_window);
  RUN_TEST(test_calls_paced_at_the_sample_period_fill_the_window);
  RUN_TEST(test_call_before_the_sample_period_elapses_is_skipped);
  RUN_TEST(test_sample_count_only_advances_on_accepted_samples);
  RUN_TEST(test_sample_count_keeps_advancing_past_window_fullness);
  return UNITY_END();
}
