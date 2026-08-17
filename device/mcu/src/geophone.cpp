#include "geophone.h"

#include <string.h>

#include "Arduino.h"
#include "Wire.h"

#if SEISMIC_DEBUG_STREAM_RAW
// Bench-only dependency, compiled out entirely at SEISMIC_DEBUG_STREAM_RAW=0
// - arduino-cli's library-discovery preprocess pass strips this #include
// along with everything else in this #if, so the field build never links
// Bridge code. See config.h for why this exists.
#include "Arduino_RouterBridge.h"
#endif

namespace {

// Ring buffer of raw volts, most-recent-write tracked by write_index_. Sized
// to exactly one window, matching SEISMIC_WINDOW_SAMPLES.
float g_ring[SEISMIC_WINDOW_SAMPLES] = {};
size_t g_write_index = 0;
size_t g_samples_written = 0;  // saturates at SEISMIC_WINDOW_SAMPLES
uint32_t g_last_fill_ms = 0;   // millis() at last successful sample write
uint32_t g_last_poll_ms = 0;   // millis() at last *accepted* ADC poll attempt
// Never saturates, unlike g_samples_written above - state_machine.cpp's
// kSensing case compares successive reads of this to know whether a new
// sample has landed since it last ran the STA/LTA slide, so it must keep
// counting past SEISMIC_WINDOW_SAMPLES for that comparison to keep working
// for the life of the device.
uint32_t g_sample_count = 0;
bool g_ok = false;

// Writes the ADS1115 config register, starting a continuous conversion at the
// settings config.h defines. Returns false if the I2C transaction did not
// complete within GEOPHONE_I2C_TIMEOUT_MS.
bool ads1115_write_config(uint16_t config_word) {
  const uint32_t start_ms = millis();

  GEOPHONE_I2C_BUS.beginTransmission(ADS1115_I2C_ADDRESS);
  GEOPHONE_I2C_BUS.write(ADS1115_REG_CONFIG);
  GEOPHONE_I2C_BUS.write(static_cast<uint8_t>(config_word >> 8));
  GEOPHONE_I2C_BUS.write(static_cast<uint8_t>(config_word & 0xFF));
  const uint8_t status = GEOPHONE_I2C_BUS.endTransmission();

  // millis() elapsed check is a defensive wrapper, not a substitute for the
  // Arduino core's own I2C timeout: it catches a call that returned late, not
  // one that never returns at all. A core-level Wire timeout is what actually
  // bounds a truly hung bus.
  const bool timed_out = (millis() - start_ms) > GEOPHONE_I2C_TIMEOUT_MS;
  return (status == 0) && !timed_out;
}

// Points the ADS1115 at its conversion register so a subsequent read pulls
// the latest sample, then reads it back. Returns false on any I2C failure or
// timeout.
bool ads1115_read_conversion(int16_t *out_raw) {
  const uint32_t start_ms = millis();

  GEOPHONE_I2C_BUS.beginTransmission(ADS1115_I2C_ADDRESS);
  GEOPHONE_I2C_BUS.write(ADS1115_REG_CONVERSION);
  if (GEOPHONE_I2C_BUS.endTransmission(false) != 0) {
    return false;
  }

  const uint8_t received =
      GEOPHONE_I2C_BUS.requestFrom(ADS1115_I2C_ADDRESS, static_cast<uint8_t>(2));
  if (received != 2) {
    return false;
  }

  const uint8_t high_byte = static_cast<uint8_t>(GEOPHONE_I2C_BUS.read());
  const uint8_t low_byte = static_cast<uint8_t>(GEOPHONE_I2C_BUS.read());
  *out_raw = static_cast<int16_t>((high_byte << 8) | low_byte);

  const bool timed_out = (millis() - start_ms) > GEOPHONE_I2C_TIMEOUT_MS;
  return !timed_out;
}

}  // namespace

void geophone_init() {
  GEOPHONE_I2C_BUS.begin();
  GEOPHONE_I2C_BUS.setClock(GEOPHONE_I2C_CLOCK_HZ);

  g_write_index = 0;
  g_samples_written = 0;
  g_sample_count = 0;
  g_last_fill_ms = millis();
  g_last_poll_ms = millis();
  g_ok = ads1115_write_config(ADS1115_CONFIG_WORD);
}

void geophone_service() {
  const uint32_t now_ms = millis();

  // Proactive staleness check, run every call regardless of the cadence gate
  // below. state_machine.cpp's kSensing case now only calls
  // read_seismic_window() when geophone_sample_count() has advanced (see its
  // own comment) - read_seismic_window() can no longer be relied on to keep
  // g_ok current in real time if the sensor stops producing samples
  // entirely, since nothing would call it again. Same formula
  // read_seismic_window() itself uses, just applied here too so a genuinely
  // dead sensor still flips geophone_ok() to false within
  // GEOPHONE_WINDOW_STALE_MS instead of being stuck at its last value
  // forever.
  if (g_ok && (now_ms - g_last_fill_ms) > GEOPHONE_WINDOW_STALE_MS) {
    g_ok = false;
  }

  // Cadence gate (KNOWN_GAPS.md: "ads1115_read_conversion never polls the
  // ready bit"). ADS1115_CFG_COMP_DISABLE leaves ALERT/RDY unused, and in
  // ADS1115_CFG_MODE_CONTINUOUS the config register's OS bit only reflects
  // conversion-in-progress in single-shot mode - it is not a usable
  // new-data-ready signal here, so a millis() gate at the nominal conversion
  // period is the fix, not an OS-bit poll. loop() (main.cpp) calls this every
  // iteration with no delay of its own, far faster than a new conversion
  // becomes available at ADS1115_CFG_DR_250SPS (4 ms); without this gate,
  // back-to-back calls read and ring-buffer the same conversion register
  // value more than once. Unsigned subtraction makes this rollover-safe
  // (same idiom as rule_gate_apply()). Gates the attempt itself, not just a
  // successful read, so a run of I2C failures cannot be retried faster than
  // real hardware would ever produce a new sample.
  if (now_ms - g_last_poll_ms < (1000 / SEISMIC_SAMPLE_RATE_HZ)) {
    return;
  }
  g_last_poll_ms = now_ms;

  int16_t raw = 0;
  if (!ads1115_read_conversion(&raw)) {
    // A single failed poll does not immediately fail the sensor - the
    // staleness check in read_seismic_window() is what actually decides
    // whether the buffer is too old to trust. This just skips the write.
    return;
  }

  const float volts = static_cast<float>(raw) * ADS1115_LSB_VOLTS;

#if SEISMIC_DEBUG_STREAM_RAW
  // Bench-only: one raw volts reading per line, for scripts/live_seismic_
  // plot.py's top panel - see SEISMIC_DEBUG_STREAM_RAW's own comment in
  // config.h for the wire-format contract. Gated to SEISMIC_SAMPLE_RATE_HZ
  // rather than SEISMIC_DEBUG_PRINT_INTERVAL_MS: geophone_service() runs
  // every loop() iteration with no ready-bit check on the ADS1115, so
  // back-to-back calls can return the same conversion (KNOWN_GAPS) - this
  // gate bounds the console to the nominal sample rate, it does not make
  // the samples themselves any fresher.
  static uint32_t s_last_stream_print_ms = 0;
  const uint32_t stream_now_ms = millis();
  if (stream_now_ms - s_last_stream_print_ms >= (1000 / SEISMIC_SAMPLE_RATE_HZ)) {
    s_last_stream_print_ms = stream_now_ms;
    Serial.println(volts, 6);
  }

  // Second delivery path, same samples: push every
  // SEISMIC_STREAM_BRIDGE_EVERY_N_SAMPLES-th sample to the MPU over
  // Bridge.notify() so `docker logs -f eletect-x-main-1` piped into
  // live_seismic_plot.py's stdin mode is a live alternative to the Serial
  // console - see config.h for the decimation rationale. notify() is
  // fire-and-forget (confirmed by reading Arduino_RouterBridge's bridge.h:
  // it takes a write mutex and returns after a one-way send, it does not
  // wait on an MPU reply the way Bridge.call() does), so this cannot stall
  // this loop on an MPU round trip. Counts every accepted sample, not every
  // loop() iteration, so the decimation is against real conversions.
  static uint32_t s_stream_sample_count = 0;
  ++s_stream_sample_count;
  if (s_stream_sample_count % SEISMIC_STREAM_BRIDGE_EVERY_N_SAMPLES == 0) {
    Bridge.notify("debug_stream_raw_seismic_sample", volts);
  }
#endif

#if GEOPHONE_DEBUG_SINGLE_ENDED_AIN0
  // Bench-only: prints what ADS1115_CONFIG_WORD is now sampling single-ended
  // against GND, per the flag's own rationale in config.h. Rate-limited with
  // a static millis()-gated timer - this function runs every loop()
  // iteration with no delay, so an ungated print would flood the console.
  static uint32_t s_last_bias_check_print_ms = 0;
  const uint32_t bias_check_now_ms = millis();
  if (bias_check_now_ms - s_last_bias_check_print_ms >= SEISMIC_DEBUG_PRINT_INTERVAL_MS) {
    s_last_bias_check_print_ms = bias_check_now_ms;
    Serial.print("[bias-check] raw=");
    Serial.print(raw);
    Serial.print(" volts=");
    Serial.println(volts, 6);
  }
#endif

  g_ring[g_write_index] = volts;
  g_write_index = (g_write_index + 1) % SEISMIC_WINDOW_SAMPLES;
  if (g_samples_written < SEISMIC_WINDOW_SAMPLES) {
    ++g_samples_written;
  }
  ++g_sample_count;
  g_last_fill_ms = millis();
  g_ok = true;
}

void read_seismic_window(float out[SEISMIC_WINDOW_SAMPLES]) {
  const bool buffer_full = g_samples_written >= SEISMIC_WINDOW_SAMPLES;
  const bool stale = (millis() - g_last_fill_ms) > GEOPHONE_WINDOW_STALE_MS;

  if (!buffer_full || stale || !g_ok) {
    memset(out, 0, SEISMIC_WINDOW_SAMPLES * sizeof(float));
    g_ok = false;
    return;
  }

  // g_write_index is the slot the *next* sample will land in, i.e. the
  // oldest sample in the ring right now - unwrap starting there so out[]
  // reads oldest-to-newest.
  for (size_t i = 0; i < SEISMIC_WINDOW_SAMPLES; ++i) {
    out[i] = g_ring[(g_write_index + i) % SEISMIC_WINDOW_SAMPLES];
  }
}

bool geophone_ok() { return g_ok; }

uint32_t geophone_sample_count() { return g_sample_count; }
