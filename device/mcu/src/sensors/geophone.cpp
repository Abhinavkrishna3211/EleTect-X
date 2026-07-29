#include "geophone.h"

#include <string.h>

#include "Arduino.h"
#include "Wire.h"

namespace {

// Ring buffer of raw volts, most-recent-write tracked by write_index_. Sized
// to exactly one window, matching SEISMIC_WINDOW_SAMPLES.
float g_ring[SEISMIC_WINDOW_SAMPLES] = {};
size_t g_write_index = 0;
size_t g_samples_written = 0;  // saturates at SEISMIC_WINDOW_SAMPLES
uint32_t g_last_fill_ms = 0;   // millis() at last successful sample write
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
  g_last_fill_ms = millis();
  g_ok = ads1115_write_config(ADS1115_CONFIG_WORD);
}

void geophone_service() {
  int16_t raw = 0;
  if (!ads1115_read_conversion(&raw)) {
    // A single failed poll does not immediately fail the sensor - the
    // staleness check in read_seismic_window() is what actually decides
    // whether the buffer is too old to trust. This just skips the write.
    return;
  }

  const float volts = static_cast<float>(raw) * ADS1115_LSB_VOLTS;

  g_ring[g_write_index] = volts;
  g_write_index = (g_write_index + 1) % SEISMIC_WINDOW_SAMPLES;
  if (g_samples_written < SEISMIC_WINDOW_SAMPLES) {
    ++g_samples_written;
  }
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
