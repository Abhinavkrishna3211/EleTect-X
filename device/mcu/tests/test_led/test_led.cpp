// ADR 0014 LED flash-pattern tests. drive_led() replaced its single
// analogWrite/delay/analogWrite with a per-pattern flash sequence that must
// still (a) total exactly the rule-gate-resolved duration - no extra
// blocking cost - and (b) leave the channel off on return. host_shim's
// delay() only advances a virtual millis() counter, so the whole sequence
// runs instantly; hostshim::pin_writes() records every analogWrite with its
// virtual timestamp so the *shape* of the sequence (edge count, inter-flash
// gaps) is observable here, which pin_state() alone - only the final value -
// is not.
//
// Per-channel cooldown state in led.cpp is file-static and persists across
// Unity tests, so each test fires at a now_ms 100 s past the previous one
// (LED_COOLDOWN_MS is 20 s) - well clear of the cooldown window.

#include <unity.h>

#include <vector>

#include "Arduino.h"
#include "config.h"
#include "led.h"

using hostshim::PinWrite;

static uint32_t g_now = 0;

void setUp() {
  hostshim::reset();
  led_init();
  hostshim::reset();  // drop led_init()'s digitalWrite(LOW) writes
  g_now += 100000UL;
}

void tearDown() {}

static std::vector<PinWrite> writes_for(int pin) {
  std::vector<PinWrite> out;
  for (const auto &w : hostshim::pin_writes()) {
    if (w.pin == pin) {
      out.push_back(w);
    }
  }
  return out;
}

// Count rising edges (a nonzero write immediately after a zero/none) on pin.
static int on_edge_count(int pin) {
  int edges = 0;
  int prev = 0;
  for (const auto &w : hostshim::pin_writes()) {
    if (w.pin != pin) {
      continue;
    }
    if (w.value != 0 && prev == 0) {
      ++edges;
    }
    prev = w.value;
  }
  return edges;
}

static void test_pattern_id_mapping(void) {
  TEST_ASSERT_TRUE(led_pattern_from_id(0) == led_pattern::kSteady);
  TEST_ASSERT_TRUE(led_pattern_from_id(1) == led_pattern::kSlowPulse);
  TEST_ASSERT_TRUE(led_pattern_from_id(2) == led_pattern::kFastStrobe);
  TEST_ASSERT_TRUE(led_pattern_from_id(3) == led_pattern::kRandomFlicker);
  TEST_ASSERT_TRUE(led_pattern_from_id(4) == led_pattern::kSweep);
  TEST_ASSERT_TRUE(led_pattern_from_id(5) == led_pattern::kPulseBothSync);
  TEST_ASSERT_TRUE(led_pattern_from_id(6) == led_pattern::kFlickerBothIndependent);
  TEST_ASSERT_TRUE_MESSAGE(led_pattern_from_id(7) == led_pattern::kSteady,
                            "an unknown pattern_id must fall back to kSteady");
  TEST_ASSERT_TRUE_MESSAGE(led_pattern_from_id(255) == led_pattern::kSteady,
                            "the max uint8_t pattern_id must also fall back to kSteady");
}

static void test_steady_is_one_flash_totalling_the_duration(void) {
  const led_request req = {led_channel::kWingLeft, led_pattern::kSteady, 1000, 80.0f};
  const unsigned long t0 = millis();
  const led_ack ack = drive_led(req, g_now);
  const unsigned long dt = millis() - t0;

  TEST_ASSERT_TRUE_MESSAGE(ack.allowed, "a first, in-bounds fire must be allowed");
  TEST_ASSERT_FALSE_MESSAGE(ack.clamped, "1000 ms / 80% is inside every cap");
  TEST_ASSERT_EQUAL_UINT16(1000, ack.duration_ms);
  TEST_ASSERT_EQUAL_FLOAT(80.0f, ack.gain_pct);
  TEST_ASSERT_EQUAL_INT_MESSAGE(1, on_edge_count(LED_WING_LEFT_PIN),
                                "steady is a single on/hold/off");
  TEST_ASSERT_EQUAL_INT_MESSAGE(0, writes_for(LED_WING_LEFT_PIN).back().value,
                                "channel must end off");
  TEST_ASSERT_TRUE_MESSAGE(dt >= 1000 && dt <= 1050,
                            "burst must total exactly the resolved duration");
}

static void test_slow_pulse_switches_on_once_per_cycle(void) {
  const led_request req = {led_channel::kWingLeft, led_pattern::kSlowPulse, 1000, 80.0f};
  const unsigned long t0 = millis();
  drive_led(req, g_now);
  const unsigned long dt = millis() - t0;

  TEST_ASSERT_EQUAL_INT_MESSAGE(LED_SLOW_PULSE_CYCLES, on_edge_count(LED_WING_LEFT_PIN),
                                "slow pulse must switch on once per configured cycle");
  TEST_ASSERT_EQUAL_INT_MESSAGE(0, writes_for(LED_WING_LEFT_PIN).back().value,
                                "channel must end off");
  TEST_ASSERT_TRUE_MESSAGE(dt >= 1000 && dt <= 1050,
                            "pattern must still total the resolved duration");
}

static void test_fast_strobe_flash_count_tracks_the_configured_rate(void) {
  const led_request req = {led_channel::kWingLeft, led_pattern::kFastStrobe, 1000, 80.0f};
  const unsigned long t0 = millis();
  drive_led(req, g_now);
  const unsigned long dt = millis() - t0;

  const int edges = on_edge_count(LED_WING_LEFT_PIN);
  // ~LED_FAST_STROBE_HZ flashes per 1000 ms, give or take one partial period.
  TEST_ASSERT_TRUE_MESSAGE(edges >= LED_FAST_STROBE_HZ - 1 && edges <= LED_FAST_STROBE_HZ + 1,
                            "fast strobe flash count must track LED_FAST_STROBE_HZ");
  TEST_ASSERT_EQUAL_INT_MESSAGE(0, writes_for(LED_WING_LEFT_PIN).back().value,
                                "channel must end off");
  TEST_ASSERT_TRUE_MESSAGE(dt >= 1000 && dt <= 1050,
                            "pattern must still total the resolved duration");
}

static void test_random_flicker_has_irregular_gaps(void) {
  const led_request req = {led_channel::kWingLeft, led_pattern::kRandomFlicker, 1000, 80.0f};
  const unsigned long t0 = millis();
  drive_led(req, g_now);
  const unsigned long dt = millis() - t0;

  std::vector<unsigned long> on_at;
  int prev = 0;
  for (const auto &w : hostshim::pin_writes()) {
    if (w.pin != LED_WING_LEFT_PIN) {
      continue;
    }
    if (w.value != 0 && prev == 0) {
      on_at.push_back(w.at_ms);
    }
    prev = w.value;
  }
  TEST_ASSERT_TRUE_MESSAGE(on_at.size() >= 3,
                            "flicker should fit several flashes into 1000 ms");

  std::vector<unsigned long> gaps;
  for (size_t i = 1; i < on_at.size(); ++i) {
    gaps.push_back(on_at[i] - on_at[i - 1]);
  }
  bool varied = false;
  for (size_t i = 1; i < gaps.size(); ++i) {
    if (gaps[i] != gaps[0]) {
      varied = true;
      break;
    }
  }
  TEST_ASSERT_TRUE_MESSAGE(varied, "inter-flash gaps must vary - this is the irregular strobe");
  TEST_ASSERT_EQUAL_INT_MESSAGE(0, writes_for(LED_WING_LEFT_PIN).back().value,
                                "channel must end off");
  TEST_ASSERT_TRUE_MESSAGE(dt >= 1000 && dt <= 1050,
                            "pattern must still total the resolved duration");
}

// --- Dual-wing patterns (ADR 0014 E) ------------------------------------
// channel kWingBoth drives both pins inside one drive_led() call. The tests
// below check the actual pin-toggle sequence on BOTH pins, plus the two
// properties the ADR calls out: the burst still totals exactly the resolved
// duration (no ~2D blocking cost), and a dual-wing fire gates on / updates
// both wings' cooldown counters.

// Walk every write in order; assert the two pins are never both lit at the
// same instant (antiphase). flash_pair() writes both pins with no delay
// between them, so within one flash_pair the two writes share a timestamp -
// checking after each individual write is the strict form of the assertion.
static void assert_never_both_lit(void) {
  int lv = 0;
  int rv = 0;
  for (const auto &w : hostshim::pin_writes()) {
    if (w.pin == LED_WING_LEFT_PIN) {
      lv = w.value;
    } else if (w.pin == LED_WING_RIGHT_PIN) {
      rv = w.value;
    }
    TEST_ASSERT_FALSE_MESSAGE(lv != 0 && rv != 0,
                              "sweep is antiphase - the two wings must never be lit together");
  }
}

static std::vector<unsigned long> rising_edge_times(int pin) {
  std::vector<unsigned long> out;
  int prev = 0;
  for (const auto &w : hostshim::pin_writes()) {
    if (w.pin != pin) {
      continue;
    }
    if (w.value != 0 && prev == 0) {
      out.push_back(w.at_ms);
    }
    prev = w.value;
  }
  return out;
}

static void test_sweep_drives_both_wings_antiphase_at_strobe_rate(void) {
  const led_request req = {led_channel::kWingBoth, led_pattern::kSweep, 1000, 80.0f};
  const unsigned long t0 = millis();
  const led_ack ack = drive_led(req, g_now);
  const unsigned long dt = millis() - t0;

  TEST_ASSERT_TRUE_MESSAGE(ack.allowed, "a first dual-wing fire must be allowed");

  const int le = on_edge_count(LED_WING_LEFT_PIN);
  const int re = on_edge_count(LED_WING_RIGHT_PIN);
  TEST_ASSERT_TRUE_MESSAGE(le >= LED_FAST_STROBE_HZ - 1 && le <= LED_FAST_STROBE_HZ + 1,
                            "left wing flash count must track LED_FAST_STROBE_HZ");
  TEST_ASSERT_TRUE_MESSAGE(re >= LED_FAST_STROBE_HZ - 1 && re <= LED_FAST_STROBE_HZ + 1,
                            "right wing flash count must track LED_FAST_STROBE_HZ");
  assert_never_both_lit();
  TEST_ASSERT_EQUAL_INT_MESSAGE(0, writes_for(LED_WING_LEFT_PIN).back().value,
                                "left wing must end off");
  TEST_ASSERT_EQUAL_INT_MESSAGE(0, writes_for(LED_WING_RIGHT_PIN).back().value,
                                "right wing must end off");
  TEST_ASSERT_TRUE_MESSAGE(dt >= 1000 && dt <= 1050,
                            "dual-wing burst must total exactly the resolved duration");
}

static void test_pulse_both_sync_fires_both_wings_in_phase(void) {
  const led_request req = {led_channel::kWingBoth, led_pattern::kPulseBothSync, 1000, 80.0f};
  const unsigned long t0 = millis();
  drive_led(req, g_now);
  const unsigned long dt = millis() - t0;

  const std::vector<unsigned long> l_on = rising_edge_times(LED_WING_LEFT_PIN);
  const std::vector<unsigned long> r_on = rising_edge_times(LED_WING_RIGHT_PIN);
  TEST_ASSERT_TRUE_MESSAGE(l_on.size() >= 3 && r_on.size() >= 3,
                            "both wings must strobe several times in 1000 ms");
  TEST_ASSERT_TRUE_MESSAGE(l_on == r_on,
                            "pulse-both-sync must raise both wings on the same timestamps");

  bool both_lit_somewhere = false;
  int lv = 0;
  int rv = 0;
  for (const auto &w : hostshim::pin_writes()) {
    if (w.pin == LED_WING_LEFT_PIN) {
      lv = w.value;
    } else if (w.pin == LED_WING_RIGHT_PIN) {
      rv = w.value;
    }
    if (lv != 0 && rv != 0) {
      both_lit_somewhere = true;
    }
  }
  TEST_ASSERT_TRUE_MESSAGE(both_lit_somewhere,
                            "pulse-both-sync must light both wings together at least once");
  TEST_ASSERT_EQUAL_INT_MESSAGE(0, writes_for(LED_WING_LEFT_PIN).back().value,
                                "left wing must end off");
  TEST_ASSERT_EQUAL_INT_MESSAGE(0, writes_for(LED_WING_RIGHT_PIN).back().value,
                                "right wing must end off");
  TEST_ASSERT_TRUE_MESSAGE(dt >= 1000 && dt <= 1050,
                            "dual-wing burst must total exactly the resolved duration");
}

static void test_pulse_both_sync_runs_at_the_top_tier_escalation_rate(void) {
  // ADR 0014 E.3: pulse_both_sync is a Tier 3 pattern and strobes at the
  // faster LED_STROBE_FAST_HZ, not the LED_FAST_STROBE_HZ the lower tiers
  // (single-wing strobe, sweep) use. The two rates must be far enough apart
  // that the flash count alone tells them apart in a 1000 ms window.
  const led_request req = {led_channel::kWingBoth, led_pattern::kPulseBothSync, 1000, 80.0f};
  const unsigned long t0 = millis();
  drive_led(req, g_now);
  const unsigned long dt = millis() - t0;

  const int le = on_edge_count(LED_WING_LEFT_PIN);
  const int re = on_edge_count(LED_WING_RIGHT_PIN);
  TEST_ASSERT_TRUE_MESSAGE(le >= LED_STROBE_FAST_HZ - 1 && le <= LED_STROBE_FAST_HZ + 1,
                            "left wing flash count must track LED_STROBE_FAST_HZ, not the slower rate");
  TEST_ASSERT_TRUE_MESSAGE(re >= LED_STROBE_FAST_HZ - 1 && re <= LED_STROBE_FAST_HZ + 1,
                            "right wing flash count must track LED_STROBE_FAST_HZ, not the slower rate");
  TEST_ASSERT_TRUE_MESSAGE(le > LED_FAST_STROBE_HZ + 1,
                            "the top-tier strobe must be visibly faster than the lower-tier rate");
  TEST_ASSERT_TRUE_MESSAGE(dt >= 1000 && dt <= 1050,
                            "pattern must still total the resolved duration");
}

static void test_flicker_both_independent_is_not_mirrored(void) {
  const led_request req = {led_channel::kWingBoth, led_pattern::kFlickerBothIndependent, 1000,
                            80.0f};
  const unsigned long t0 = millis();
  drive_led(req, g_now);
  const unsigned long dt = millis() - t0;

  const std::vector<unsigned long> l_on = rising_edge_times(LED_WING_LEFT_PIN);
  const std::vector<unsigned long> r_on = rising_edge_times(LED_WING_RIGHT_PIN);
  TEST_ASSERT_TRUE_MESSAGE(l_on.size() >= 3 && r_on.size() >= 3,
                            "both wings should fit several flashes into 1000 ms");
  // Same call seeds each wing's xorshift stream differently, so the two
  // schedules must diverge - this is the "two independent sources, not one
  // bigger light" property (ADR 0014 E.1).
  TEST_ASSERT_FALSE_MESSAGE(l_on == r_on,
                            "the two wings must not flicker in lockstep - they are independent");
  TEST_ASSERT_EQUAL_INT_MESSAGE(0, writes_for(LED_WING_LEFT_PIN).back().value,
                                "left wing must end off");
  TEST_ASSERT_EQUAL_INT_MESSAGE(0, writes_for(LED_WING_RIGHT_PIN).back().value,
                                "right wing must end off");
  TEST_ASSERT_TRUE_MESSAGE(dt >= 1000 && dt <= 1050,
                            "dual-wing burst must total exactly the resolved duration");
}

static void test_dual_wing_blocks_for_one_duration_not_two(void) {
  const led_request req = {led_channel::kWingBoth, led_pattern::kPulseBothSync, 1000, 80.0f};
  const unsigned long t0 = millis();
  const led_ack ack = drive_led(req, g_now);
  const unsigned long dt = millis() - t0;

  TEST_ASSERT_TRUE_MESSAGE(ack.allowed, "a first dual-wing fire must be allowed");
  TEST_ASSERT_EQUAL_UINT16(1000, ack.duration_ms);
  TEST_ASSERT_TRUE_MESSAGE(dt >= 1000 && dt <= 1050,
                            "a dual-wing burst of D must block for ~D, not ~2D (ADR 0014 E)");
}

static void test_dual_wing_fire_puts_both_wings_in_cooldown(void) {
  const led_request both = {led_channel::kWingBoth, led_pattern::kSweep, 1000, 80.0f};
  TEST_ASSERT_TRUE_MESSAGE(drive_led(both, g_now).allowed,
                            "first dual-wing fire must be allowed");

  hostshim::reset();
  const led_request left_only = {led_channel::kWingLeft, led_pattern::kFastStrobe, 1000, 80.0f};
  const led_ack refused = drive_led(left_only, g_now + 5);
  TEST_ASSERT_FALSE_MESSAGE(refused.allowed,
                            "left wing must be in cooldown after a dual-wing fire 5 ms earlier");
  TEST_ASSERT_TRUE_MESSAGE(writes_for(LED_WING_LEFT_PIN).empty(),
                            "a gated request must not touch the pin at all");
}

static void test_dual_wing_refused_whole_when_one_wing_still_cooling(void) {
  const led_request left_only = {led_channel::kWingLeft, led_pattern::kFastStrobe, 1000, 80.0f};
  TEST_ASSERT_TRUE_MESSAGE(drive_led(left_only, g_now).allowed,
                            "first single-wing fire must be allowed");

  hostshim::reset();
  const led_request both = {led_channel::kWingBoth, led_pattern::kPulseBothSync, 1000, 80.0f};
  const led_ack refused = drive_led(both, g_now + 5);
  TEST_ASSERT_FALSE_MESSAGE(refused.allowed,
                            "a dual-wing fire must be refused whole if EITHER wing is cooling");
  TEST_ASSERT_TRUE_MESSAGE(writes_for(LED_WING_LEFT_PIN).empty() &&
                               writes_for(LED_WING_RIGHT_PIN).empty(),
                            "a refused dual-wing fire must touch neither pin");
}

static void test_over_cap_gain_clamps_but_still_fires(void) {
  const led_request req = {led_channel::kWingLeft, led_pattern::kSteady, 1000, 150.0f};
  const led_ack ack = drive_led(req, g_now);

  TEST_ASSERT_TRUE_MESSAGE(ack.allowed, "an over-cap gain is clamped, not refused");
  TEST_ASSERT_TRUE_MESSAGE(ack.clamped, "150% is over LED_GAIN_MAX_PCT and must report clamped");
  TEST_ASSERT_EQUAL_FLOAT(LED_GAIN_MAX_PCT, ack.gain_pct);
  TEST_ASSERT_EQUAL_INT_MESSAGE(0, writes_for(LED_WING_LEFT_PIN).back().value,
                                "channel must still end off");
}

static void test_refire_inside_cooldown_is_refused_and_silent(void) {
  const led_request req = {led_channel::kWingRight, led_pattern::kFastStrobe, 1000, 80.0f};
  const led_ack first = drive_led(req, g_now);
  TEST_ASSERT_TRUE_MESSAGE(first.allowed, "first fire on this channel must be allowed");

  hostshim::reset();
  const led_ack second = drive_led(req, g_now + 5);
  TEST_ASSERT_FALSE_MESSAGE(second.allowed,
                            "a re-fire 5 ms later is inside LED_COOLDOWN_MS and must be refused");
  TEST_ASSERT_TRUE_MESSAGE(writes_for(LED_WING_RIGHT_PIN).empty(),
                            "a gated request must not touch the pin at all");
}

int main(int, char **) {
  UNITY_BEGIN();
  RUN_TEST(test_pattern_id_mapping);
  RUN_TEST(test_steady_is_one_flash_totalling_the_duration);
  RUN_TEST(test_slow_pulse_switches_on_once_per_cycle);
  RUN_TEST(test_fast_strobe_flash_count_tracks_the_configured_rate);
  RUN_TEST(test_random_flicker_has_irregular_gaps);
  RUN_TEST(test_sweep_drives_both_wings_antiphase_at_strobe_rate);
  RUN_TEST(test_pulse_both_sync_fires_both_wings_in_phase);
  RUN_TEST(test_pulse_both_sync_runs_at_the_top_tier_escalation_rate);
  RUN_TEST(test_flicker_both_independent_is_not_mirrored);
  RUN_TEST(test_dual_wing_blocks_for_one_duration_not_two);
  RUN_TEST(test_dual_wing_fire_puts_both_wings_in_cooldown);
  RUN_TEST(test_dual_wing_refused_whole_when_one_wing_still_cooling);
  RUN_TEST(test_over_cap_gain_clamps_but_still_fires);
  RUN_TEST(test_refire_inside_cooldown_is_refused_and_silent);
  return UNITY_END();
}
