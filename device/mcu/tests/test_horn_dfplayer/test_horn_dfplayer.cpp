// Known-answer tests for horn.cpp's pure DFPlayer helpers (ADR 0015
// Decision F): the gain->AT+VOL mapping and the two AT command formatters.
// No Serial, no pin state - the host-testable core, mirroring
// tests/test_rule_gate and footfall_probability_from_ratio()'s precedent.
//
// Volume anchors come straight from ADR 0016 Decision C's tier table, after
// the MCU HORN_GAIN_MAX_PCT (60%) clamp that rule_gate_apply() applies
// before this function ever sees the value:
//   Tier 1  gain 25%  -> AT+VOL=8
//   Tier 2  gain 45%  -> AT+VOL=14
//   Tier 3  gain 60%  -> AT+VOL=18
// with DFPLAYER_VOL_MAX = 30 the full-scale reference.

#include <cstring>

#include <unity.h>

#include "config.h"
#include "horn.h"

void setUp() {}
void tearDown() {}

// --- horn_dfplayer_volume_from_gain_pct -------------------------------------

static void test_tier_gain_anchors_map_to_the_adr_0016_volumes(void) {
  TEST_ASSERT_EQUAL_UINT8(8, horn_dfplayer_volume_from_gain_pct(25.0f));
  TEST_ASSERT_EQUAL_UINT8(14, horn_dfplayer_volume_from_gain_pct(45.0f));
  TEST_ASSERT_EQUAL_UINT8(18, horn_dfplayer_volume_from_gain_pct(60.0f));
}

static void test_volume_endpoints_and_clamp(void) {
  TEST_ASSERT_EQUAL_UINT8(0, horn_dfplayer_volume_from_gain_pct(0.0f));
  TEST_ASSERT_EQUAL_UINT8(DFPLAYER_VOL_MAX,
                          horn_dfplayer_volume_from_gain_pct(100.0f));
  // Out-of-range gain is clamped to [0, 100] before scaling, never wraps.
  TEST_ASSERT_EQUAL_UINT8(0, horn_dfplayer_volume_from_gain_pct(-5.0f));
  TEST_ASSERT_EQUAL_UINT8(DFPLAYER_VOL_MAX,
                          horn_dfplayer_volume_from_gain_pct(250.0f));
}

static void test_volume_rounds_to_nearest_not_toward_zero(void) {
  // 5% of 30 = 1.5 -> must round up to 2, not truncate to 1.
  TEST_ASSERT_EQUAL_UINT8(2, horn_dfplayer_volume_from_gain_pct(5.0f));
  // 3% of 30 = 0.9 -> rounds up to 1.
  TEST_ASSERT_EQUAL_UINT8(1, horn_dfplayer_volume_from_gain_pct(3.0f));
  // 1% of 30 = 0.3 -> rounds down to 0.
  TEST_ASSERT_EQUAL_UINT8(0, horn_dfplayer_volume_from_gain_pct(1.0f));
}

// --- horn_at_vol_command --------------------------------------------------

static void test_at_vol_command_exact_string(void) {
  char buf[24];
  TEST_ASSERT_TRUE(horn_at_vol_command(8, buf, sizeof(buf)));
  TEST_ASSERT_EQUAL_STRING("AT+VOL=8\r\n", buf);

  TEST_ASSERT_TRUE(horn_at_vol_command(30, buf, sizeof(buf)));
  TEST_ASSERT_EQUAL_STRING("AT+VOL=30\r\n", buf);
}

static void test_at_vol_command_rejects_a_buffer_that_cannot_hold_it(void) {
  char buf[6] = {'x', 'x', 'x', 'x', 'x', 'x'};
  // "AT+VOL=8\r\n" + NUL needs 11 bytes; 6 is not enough.
  TEST_ASSERT_FALSE(horn_at_vol_command(8, buf, sizeof(buf)));
  TEST_ASSERT_EQUAL_CHAR('\0', buf[0]);
}

static void test_at_vol_command_rejects_null_or_zero_length(void) {
  char buf[24];
  TEST_ASSERT_FALSE(horn_at_vol_command(8, nullptr, sizeof(buf)));
  TEST_ASSERT_FALSE(horn_at_vol_command(8, buf, 0));
}

// --- horn_at_playnum_command --------------------------------------------

static void test_at_playnum_command_exact_string(void) {
  char buf[24];
  TEST_ASSERT_TRUE(horn_at_playnum_command(1, buf, sizeof(buf)));
  TEST_ASSERT_EQUAL_STRING("AT+PLAYNUM=1\r\n", buf);

  TEST_ASSERT_TRUE(horn_at_playnum_command(255, buf, sizeof(buf)));
  TEST_ASSERT_EQUAL_STRING("AT+PLAYNUM=255\r\n", buf);
}

static void test_at_playnum_command_rejects_a_buffer_that_cannot_hold_it(void) {
  char buf[8] = {'x', 'x', 'x', 'x', 'x', 'x', 'x', 'x'};
  // "AT+PLAYNUM=255\r\n" + NUL needs 17 bytes; 8 is not enough.
  TEST_ASSERT_FALSE(horn_at_playnum_command(255, buf, sizeof(buf)));
  TEST_ASSERT_EQUAL_CHAR('\0', buf[0]);
}

static void test_at_playnum_command_rejects_null_or_zero_length(void) {
  char buf[24];
  TEST_ASSERT_FALSE(horn_at_playnum_command(1, nullptr, sizeof(buf)));
  TEST_ASSERT_FALSE(horn_at_playnum_command(1, buf, 0));
}

int main(int, char **) {
  UNITY_BEGIN();
  RUN_TEST(test_tier_gain_anchors_map_to_the_adr_0016_volumes);
  RUN_TEST(test_volume_endpoints_and_clamp);
  RUN_TEST(test_volume_rounds_to_nearest_not_toward_zero);
  RUN_TEST(test_at_vol_command_exact_string);
  RUN_TEST(test_at_vol_command_rejects_a_buffer_that_cannot_hold_it);
  RUN_TEST(test_at_vol_command_rejects_null_or_zero_length);
  RUN_TEST(test_at_playnum_command_exact_string);
  RUN_TEST(test_at_playnum_command_rejects_a_buffer_that_cannot_hold_it);
  RUN_TEST(test_at_playnum_command_rejects_null_or_zero_length);
  return UNITY_END();
}
