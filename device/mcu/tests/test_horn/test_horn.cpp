// Polarity regression test for AUDIO_TRIGGER_PIN (horn.cpp) - covers the bug
// where the pin idled low and pulsed high, backwards against the DFPlayer
// PRO's real DF1101S ADKEY/KEY circuit (pull-up to its own IO rail, idle
// high, pressed by pulling low). See horn.cpp's top comment and config.h's
// AUDIO_TRIGGER_PIN comment for the datasheet-sourced rationale.
//
// host_shim's delay() only advances a virtual millis counter - it never
// blocks - so horn_fire_sequence()'s low pulse inside drive_horn() happens
// and reverts before drive_horn() returns; there is no hook here to observe
// that transient value mid-call. What is observable, and what actually
// distinguishes the fixed polarity from the original bug, is the pin's
// resting (idle) value: after horn_init() and after every completed fire,
// the pin must be back at its idle level. Under the original bug idle was
// LOW (both before and after a fire, since the buggy sequence pulsed
// high-then-low); under the fix idle is HIGH (matching the DFPlayer PRO's
// pull-up) both before and after a fire, since the fixed sequence pulses
// low-then-high.

#include <unity.h>

#include "Arduino.h"
#include "config.h"
#include "horn.h"

void setUp() { hostshim::reset(); }
void tearDown() {}

static void test_horn_init_idles_trigger_pin_high(void) {
  horn_init();

  TEST_ASSERT_EQUAL_MESSAGE(
      HIGH, hostshim::pin_state(AUDIO_TRIGGER_PIN),
      "AUDIO_TRIGGER_PIN must idle high at boot to match the DFPlayer PRO's "
      "pull-up-to-IO-rail ADKEY/KEY circuit - idling low holds K1 pressed "
      "for as long as the board is powered");
}

static void test_drive_horn_returns_trigger_pin_to_idle_high(void) {
  horn_init();

  const horn_request req = {/*duration_ms=*/500, /*gain_pct=*/30.0f};
  const horn_ack ack = drive_horn(req, /*now_ms=*/0);

  TEST_ASSERT_TRUE_MESSAGE(ack.allowed,
                            "a first-ever, in-bounds request must be allowed");
  TEST_ASSERT_EQUAL_MESSAGE(
      HIGH, hostshim::pin_state(AUDIO_TRIGGER_PIN),
      "after a completed fire, AUDIO_TRIGGER_PIN must be released back to "
      "idle high, not left low - the DFPlayer PRO reads a held-low line as "
      "a continued button press, not a completed trigger");
}

static void test_drive_horn_leaves_amp_enable_pin_disabled_after_fire(void) {
  horn_init();

  const horn_request req = {/*duration_ms=*/500, /*gain_pct=*/30.0f};
  drive_horn(req, /*now_ms=*/0);

  TEST_ASSERT_EQUAL_MESSAGE(
      LOW, hostshim::pin_state(HORN_AMP_ENABLE_PIN),
      "HORN_AMP_ENABLE_PIN sequencing is untouched by the AUDIO_TRIGGER_PIN "
      "polarity fix - the amp must still end back in shutdown");
}

int main(int, char **) {
  UNITY_BEGIN();
  RUN_TEST(test_horn_init_idles_trigger_pin_high);
  RUN_TEST(test_drive_horn_returns_trigger_pin_to_idle_high);
  RUN_TEST(test_drive_horn_leaves_amp_enable_pin_disabled_after_fire);
  return UNITY_END();
}
