// Geophone front-end - read_seismic_window() contract.
//
// Backed today by an ADS1115 + INA333 bench stand-in over I2C2; the field
// design swaps this for the STM32's own internal ADC via LPBAM (ADR 0009).
// Both sides satisfy this one signature; sta_lta.cpp and everything above it
// never touches the ADC/I2C directly (ENGINEERING_CONVENTIONS.md 1).
//
// Contract (device/mpu/bridge/schema.md): never blocks past one ADC
// conversion cycle; returns a zero-filled array, not a null/exception, on an
// I2C/ADC timeout, so a transient glitch degrades one STA/LTA window rather
// than crashing the state machine.

#ifndef SENSORS_GEOPHONE_H
#define SENSORS_GEOPHONE_H

#include <cstddef>
#include <cstdint>

#include "config.h"

// One-time setup: configures the I2C bus and puts the ADS1115 into
// continuous-conversion mode. Call once from setup().
void geophone_init();

// Call every loop() iteration. Never blocks: returns immediately both when
// gated (see below) and when the I2C read itself fails or times out. This is
// what read_seismic_window() later snapshots; it is the only place that
// talks to the ADC.
//
// Internally rate-gated to one ADC poll per nominal sample period
// (1000/SEISMIC_SAMPLE_RATE_HZ ms) via millis(), not a hardware ready-bit -
// the ADS1115 runs in continuous-conversion mode with ALERT/RDY unused, so
// there is no ready signal to poll. This is what stops a fast loop() from
// reading and ring-buffering the same conversion register value twice
// (KNOWN_GAPS.md).
void geophone_service();

// Copies the most recent SEISMIC_WINDOW_SAMPLES samples into out. Never waits
// on the ADC - it only reads the ring buffer geophone_service() has already
// filled.
//
// On success: out holds SEISMIC_WINDOW_SAMPLES real samples in volts, and
// geophone_ok() reports true.
// On failure (an I2C transaction exceeded GEOPHONE_I2C_TIMEOUT_MS, or the
// buffer has not been refreshed within GEOPHONE_WINDOW_STALE_MS): out is
// zero-filled and geophone_ok() reports false, per the schema contract.
void read_seismic_window(float out[SEISMIC_WINDOW_SAMPLES]);

// Last-known health, published via report_system_status / get_system_state
// (device/mpu/bridge/schema.md) so a failing sensor is reported, not silently
// zeroed. Kept current even if nothing calls read_seismic_window(): geophone_
// service() also flips this false on its own once GEOPHONE_WINDOW_STALE_MS
// has passed since the last accepted sample.
bool geophone_ok();

// Monotonically increasing count of samples geophone_service() has accepted
// into the ring buffer since geophone_init(). Never saturates (unlike the
// ring-buffer-fullness tracking behind read_seismic_window()) - callers that
// only care whether a new sample has landed since they last checked (e.g.
// state_machine.cpp's kSensing case, to avoid re-running the STA/LTA slide
// on an unchanged window) just compare successive reads for inequality.
uint32_t geophone_sample_count();

#endif  // SENSORS_GEOPHONE_H
