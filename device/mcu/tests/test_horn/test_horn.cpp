// horn.cpp sequencing tests.
//
// ADR 0015 Decision E retired the AUDIO_TRIGGER_PIN GPIO pulse into the
// DFPlayer PRO's KEY input: horn control now goes over DFPLAYER_SERIAL as
// AT+PLAYNUM / AT+VOL commands (see test_horn_dfplayer for the pure
// command/volume core). AUDIO_TRIGGER_PIN survives only as a documented
// fallback (config.h), parked idle-high by horn_init() and never touched by
// a fire again - the "trigger pin untouched by a fire" test below is the
// regression guard for that retirement.
//
// host_shim's delay() only advances a virtual millis counter - it never
// blocks - so the whole fire sequence inside drive_horn() runs and settles
// before drive_horn() returns. What is observable is the resting pin state
// after init and after a completed fire: HORN_AMP_ENABLE_PIN must end back
// in shutdown (LOW), and AUDIO_TRIGGER_PIN must sit idle-high the whole
// time. The AT bytes written to DFPLAYER_SERIAL are deliberately not
// asserted here (ADR 0015 Decision F: the transport is not host-testable,
// only the pure string/volume helpers are).

#include <unity.h>

#include "Arduino.h"
#include "config.h"
#include "horn.h"

void setUp() { hostshim::reset(); }
void tearDown() {}

static void test_horn_init_parks_pins_safely(void) {
  horn_init();

  TEST_ASSERT_EQUAL_MESSAGE(
      HIGH, hostshim::pin_state(AUDIO_TRIGGER_PIN),
      "AUDIO_TRIGGER_PIN (retired KEY-pin fallback, ADR 0015 E) must idle "
      "high so the fallback button reads as unpressed for as long as the "
      "board is powered");
  TEST_ASSERT_EQUAL_MESSAGE(
      LOW, hostshim::pin_state(HORN_AMP_ENABLE_PIN),
      "HORN_AMP_ENABLE_PIN must boot LOW - the TPA3116D2 held in shutdown "
      "until a fire brings it out");
}

static void test_drive_horn_first_in_bounds_request_is_allowed(void) {
  horn_init();

  const horn_request req = {/*duration_ms=*/500, /*gain_pct=*/30.0f, /*track_id=*/2};
  const horn_ack ack = drive_horn(req, /*now_ms=*/0);

  TEST_ASSERT_TRUE_MESSAGE(ack.allowed,
                            "a first-ever, in-bounds request must be allowed");
}

static void test_drive_horn_does_not_touch_the_retired_trigger_pin(void) {
  horn_init();

  const horn_request req = {/*duration_ms=*/500, /*gain_pct=*/30.0f, /*track_id=*/2};
  drive_horn(req, /*now_ms=*/0);

  TEST_ASSERT_EQUAL_MESSAGE(
      HIGH, hostshim::pin_state(AUDIO_TRIGGER_PIN),
      "ADR 0015 E: the fire path drives the DFPlayer over DFPLAYER_SERIAL, "
      "not a KEY-pin pulse - AUDIO_TRIGGER_PIN must stay idle-high through a "
      "whole fire, never pulsed");
}

static void test_drive_horn_leaves_amp_enable_pin_disabled_after_fire(void) {
  horn_init();

  const horn_request req = {/*duration_ms=*/500, /*gain_pct=*/30.0f, /*track_id=*/2};
  drive_horn(req, /*now_ms=*/0);

  TEST_ASSERT_EQUAL_MESSAGE(
      LOW, hostshim::pin_state(HORN_AMP_ENABLE_PIN),
      "after a completed fire the amp must end back in shutdown (LOW)");
}

int main(int, char **) {
  UNITY_BEGIN();
  RUN_TEST(test_horn_init_parks_pins_safely);
  RUN_TEST(test_drive_horn_first_in_bounds_request_is_allowed);
  RUN_TEST(test_drive_horn_does_not_touch_the_retired_trigger_pin);
  RUN_TEST(test_drive_horn_leaves_amp_enable_pin_disabled_after_fire);
  return UNITY_END();
}
