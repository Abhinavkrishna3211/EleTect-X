// Behavioral test for state_machine.cpp's console-print gating
// (SEISMIC_TRIGGER_CONSOLE_LOG, config.h) - the fix for docs/KNOWN_GAPS.md's
// 18 Aug entry: state_machine.cpp's [trigger]/[notify] prints used to be
// unconditional and share LORA_SERIAL's physical wire with the E5 LoRa
// module, risking corruption of AT-command traffic mid-transaction.
//
// Drives a real STA/LTA trigger through the full geophone -> state_machine
// chain (Wire.host_feed_raw() injects a real quiet-then-transient waveform,
// hostshim::advance_millis() paces geophone_service()'s sample-rate gate,
// same idiom as test_geophone.cpp) so the "zero Serial bytes" assertion is
// meaningful - it proves the print path is gated, not that a trigger never
// happened to fire.

#include <unity.h>

#include "Arduino.h"
#include "Wire.h"
#include "config.h"
#include "geophone.h"
#include "state_machine.h"

namespace {

const uint32_t kPeriodMs = 1000 / SEISMIC_SAMPLE_RATE_HZ;

// One accepted geophone sample, paced at the nominal sample period, followed
// by the same state_machine_tick() call main.cpp's loop() makes every
// iteration.
void feed_and_tick(int16_t raw_value) {
  Wire.host_feed_raw(raw_value);
  hostshim::advance_millis(kPeriodMs);
  const uint32_t now_ms = millis();
  geophone_service();
  state_machine_tick(now_ms);
}

}  // namespace

void setUp() {
  hostshim::reset();
  geophone_init();
  state_machine_init();
  Serial.host_reset_bytes_written();
}

void tearDown() {}

static void test_quiet_baseline_never_triggers_and_stays_silent(void) {
  // A full window (plus margin) of low, constant-amplitude samples - real
  // sensor noise floor, never a footfall. The ratio never approaches
  // STA_LTA_TRIGGER_RATIO (4.0), so the state machine must stay in
  // kSensing and Serial must stay untouched either way.
  for (int i = 0; i < SEISMIC_WINDOW_SAMPLES + 10; ++i) {
    feed_and_tick(100);
  }

  TEST_ASSERT_TRUE_MESSAGE(
      state_machine_get_state() == reflex_state::kSensing,
      "a quiet, non-triggering window must leave the state machine in "
      "kSensing");
  TEST_ASSERT_EQUAL_MESSAGE(
      0, static_cast<int>(Serial.host_bytes_written()),
      "no Serial bytes should be written on a quiet pass with no trigger");
}

static void test_real_trigger_produces_zero_serial_bytes(void) {
  // Fill the window with a quiet baseline, then append a real transient at
  // the tail - mirrors an SM-24 footfall riding on top of the noise floor.
  // sta (last STA_SAMPLES) / lta (last LTA_SAMPLES, which still includes
  // the transient plus a majority of quiet samples) works out to ~6.9x
  // (225*100 + 25*2000)/250 = 290 lta, 2000 sta - comfortably past
  // STA_LTA_TRIGGER_RATIO (4.0), so this is a genuine crossing, not a
  // near-miss. The ratio math itself is exercised by test_sta_lta.cpp's
  // known-answer cases; this test only needs a reliable trigger to prove
  // the console stays silent through one.
  for (size_t i = 0; i < SEISMIC_WINDOW_SAMPLES; ++i) {
    feed_and_tick(100);
  }
  for (size_t i = 0; i < STA_SAMPLES; ++i) {
    feed_and_tick(2000);
  }

  TEST_ASSERT_TRUE_MESSAGE(
      state_machine_get_state() == reflex_state::kEvent,
      "the crafted quiet-then-transient window must cross "
      "STA_LTA_TRIGGER_RATIO and move the state machine to kEvent - "
      "otherwise the assertion below proves nothing about the gate");
  TEST_ASSERT_EQUAL_MESSAGE(
      0, static_cast<int>(Serial.host_bytes_written()),
      "SEISMIC_TRIGGER_CONSOLE_LOG defaults to 0 (config.h) - a real "
      "trigger must still write zero bytes to Serial, the wire LORA_SERIAL "
      "shares with the E5 (docs/KNOWN_GAPS.md, 18 Aug)");
}

int main(int, char **) {
  UNITY_BEGIN();
  RUN_TEST(test_quiet_baseline_never_triggers_and_stays_silent);
  RUN_TEST(test_real_trigger_produces_zero_serial_bytes);
  return UNITY_END();
}
