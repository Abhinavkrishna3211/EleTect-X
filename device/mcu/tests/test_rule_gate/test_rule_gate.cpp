// Known-answer tests for the actuator rule-gate pure core
// (ENGINEERING_CONVENTIONS.md 4). Covers clamp-and-ack, cooldown refusal, and
// millis() rollover safety.

#include <unity.h>

#include <cstdint>

#include "rule_gate.h"

void setUp() {}
void tearDown() {}

static const gate_limits kLimits = {
    /*burst_max_ms=*/3000,
    /*cooldown_ms=*/30000,
    /*gain_max_pct=*/60.0f,
};

static void test_over_duration_request_clamps_to_cap(void) {
  const gate_request req = {/*duration_ms=*/5000, /*gain_pct=*/40.0f};

  const gate_result result =
      rule_gate_apply(req, kLimits, 0, 0, /*has_fired_before=*/false);

  TEST_ASSERT_TRUE_MESSAGE(result.allowed, "first-ever request must be allowed");
  TEST_ASSERT_TRUE_MESSAGE(
      result.clamped, "a 5000ms request against a 3000ms cap must be clamped");
  TEST_ASSERT_EQUAL_UINT16_MESSAGE(
      3000, result.duration_ms,
      "clamped duration must equal burst_max_ms exactly, not just be <= it");
  TEST_ASSERT_EQUAL_FLOAT_MESSAGE(40.0f, result.gain_pct,
                                   "gain within its own limit must pass "
                                   "through unchanged");
}

static void test_over_gain_request_clamps_to_cap(void) {
  const gate_request req = {/*duration_ms=*/1000, /*gain_pct=*/95.0f};

  const gate_result result =
      rule_gate_apply(req, kLimits, 0, 0, /*has_fired_before=*/false);

  TEST_ASSERT_TRUE_MESSAGE(result.clamped,
                            "a 95% gain request against a 60% cap must clamp");
  TEST_ASSERT_EQUAL_FLOAT_MESSAGE(
      60.0f, result.gain_pct,
      "clamped gain must equal gain_max_pct exactly");
}

static void test_negative_gain_clamps_to_zero(void) {
  const gate_request req = {/*duration_ms=*/500, /*gain_pct=*/-10.0f};

  const gate_result result =
      rule_gate_apply(req, kLimits, 0, 0, /*has_fired_before=*/false);

  TEST_ASSERT_TRUE_MESSAGE(result.clamped, "negative gain must be clamped");
  TEST_ASSERT_EQUAL_FLOAT_MESSAGE(0.0f, result.gain_pct,
                                   "negative gain must clamp to 0, not pass "
                                   "through as a negative drive value");
}

static void test_in_bounds_request_is_not_clamped(void) {
  const gate_request req = {/*duration_ms=*/1500, /*gain_pct=*/50.0f};

  const gate_result result =
      rule_gate_apply(req, kLimits, 0, 0, /*has_fired_before=*/false);

  TEST_ASSERT_FALSE_MESSAGE(result.clamped,
                            "an in-bounds request must pass through unchanged");
  TEST_ASSERT_EQUAL_UINT16_MESSAGE(1500, result.duration_ms, "duration unchanged");
  TEST_ASSERT_EQUAL_FLOAT_MESSAGE(50.0f, result.gain_pct, "gain unchanged");
}

static void test_request_inside_cooldown_is_refused(void) {
  const gate_request req = {/*duration_ms=*/500, /*gain_pct=*/50.0f};
  const uint32_t last_fire_ms = 10000;
  const uint32_t now_ms = last_fire_ms + 5000;  // 5s into a 30s cooldown

  const gate_result result = rule_gate_apply(req, kLimits, last_fire_ms,
                                              now_ms, /*has_fired_before=*/true);

  TEST_ASSERT_FALSE_MESSAGE(
      result.allowed,
      "a request 5s into a 30s cooldown must be refused, not silently "
      "dropped-and-acked");
}

static void test_request_exactly_at_cooldown_boundary_is_allowed(void) {
  const gate_request req = {/*duration_ms=*/500, /*gain_pct=*/50.0f};
  const uint32_t last_fire_ms = 10000;
  const uint32_t now_ms = last_fire_ms + kLimits.cooldown_ms;

  const gate_result result = rule_gate_apply(req, kLimits, last_fire_ms,
                                              now_ms, /*has_fired_before=*/true);

  TEST_ASSERT_TRUE_MESSAGE(
      result.allowed,
      "a request exactly at the cooldown boundary must be allowed, not "
      "refused by an off-by-one");
}

static void test_request_just_after_cooldown_expiry_is_allowed(void) {
  const gate_request req = {/*duration_ms=*/500, /*gain_pct=*/50.0f};
  const uint32_t last_fire_ms = 10000;
  const uint32_t now_ms = last_fire_ms + kLimits.cooldown_ms + 1;

  const gate_result result = rule_gate_apply(req, kLimits, last_fire_ms,
                                              now_ms, /*has_fired_before=*/true);

  TEST_ASSERT_TRUE_MESSAGE(result.allowed,
                            "the first request after cooldown expiry must be "
                            "allowed");
}

static void test_first_ever_request_ignores_cooldown(void) {
  // last_fire_ms/now_ms both 0 - the boot-time state, before anything has
  // ever fired. has_fired_before=false must mean "never in cooldown"
  // regardless of the timestamp values.
  const gate_request req = {/*duration_ms=*/500, /*gain_pct=*/50.0f};

  const gate_result result =
      rule_gate_apply(req, kLimits, 0, 0, /*has_fired_before=*/false);

  TEST_ASSERT_TRUE_MESSAGE(
      result.allowed,
      "a request before anything has ever fired must not be treated as "
      "inside a cooldown from a same-valued last_fire_ms");
}

static void test_millis_rollover_does_not_wedge_the_gate(void) {
  // last_fire_ms just before a uint32_t wraparound, now_ms just after it.
  // Real elapsed time is small (well inside cooldown), and unsigned
  // subtraction must report that correctly rather than the huge value a
  // signed/naive comparison would produce.
  const uint32_t last_fire_ms = 0xFFFFFFF0u;  // 16ms before wraparound
  const uint32_t now_ms = 10u;                // 26ms after wraparound
  const gate_request req = {/*duration_ms=*/500, /*gain_pct=*/50.0f};

  const gate_result result = rule_gate_apply(req, kLimits, last_fire_ms,
                                              now_ms, /*has_fired_before=*/true);

  TEST_ASSERT_FALSE_MESSAGE(
      result.allowed,
      "26ms of real elapsed time across a millis() rollover must still read "
      "as inside a 30000ms cooldown, not as an enormous elapsed value that "
      "wrongly allows the request");
}

static void test_millis_rollover_allows_after_real_cooldown_elapses(void) {
  const uint32_t last_fire_ms = 0xFFFFFFF0u;
  const uint32_t now_ms =
      static_cast<uint32_t>(0xFFFFFFF0u + kLimits.cooldown_ms + 1);
  const gate_request req = {/*duration_ms=*/500, /*gain_pct=*/50.0f};

  const gate_result result = rule_gate_apply(req, kLimits, last_fire_ms,
                                              now_ms, /*has_fired_before=*/true);

  TEST_ASSERT_TRUE_MESSAGE(
      result.allowed,
      "once real elapsed time across a rollover exceeds the cooldown, the "
      "request must be allowed");
}

int main(int, char **) {
  UNITY_BEGIN();
  RUN_TEST(test_over_duration_request_clamps_to_cap);
  RUN_TEST(test_over_gain_request_clamps_to_cap);
  RUN_TEST(test_negative_gain_clamps_to_zero);
  RUN_TEST(test_in_bounds_request_is_not_clamped);
  RUN_TEST(test_request_inside_cooldown_is_refused);
  RUN_TEST(test_request_exactly_at_cooldown_boundary_is_allowed);
  RUN_TEST(test_request_just_after_cooldown_expiry_is_allowed);
  RUN_TEST(test_first_ever_request_ignores_cooldown);
  RUN_TEST(test_millis_rollover_does_not_wedge_the_gate);
  RUN_TEST(test_millis_rollover_allows_after_real_cooldown_elapses);
  return UNITY_END();
}
