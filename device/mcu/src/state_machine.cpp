#include "state_machine.h"

#include <array>

#include "Arduino.h"
#include "Arduino_RouterBridge.h"
#include "config.h"
#include "footfall_features.h"
#include "geophone.h"
#include "sta_lta.h"

namespace {

reflex_state g_state = reflex_state::kIdle;
uint32_t g_state_entered_ms = 0;

void enter(reflex_state next, uint32_t now_ms) {
  g_state = next;
  g_state_entered_ms = now_ms;
}

// rollover-safe, same pattern as rule_gate_apply().
uint32_t elapsed_since_entry(uint32_t now_ms) { return now_ms - g_state_entered_ms; }

void log_trigger(const sta_lta_result &result, uint32_t now_ms) {
  // Format fixed by device/mcu/README.md's bench stomp-test procedure - keep
  // this line and that doc in sync if either changes.
  Serial.print("[trigger] t=");
  Serial.print(now_ms);
  Serial.print(" sta=");
  Serial.print(result.sta);
  Serial.print(" lta=");
  Serial.print(result.lta);
  Serial.print(" ratio=");
  Serial.print(result.peak_ratio);
  Serial.print(" idx=");
  Serial.println(static_cast<unsigned long>(result.trigger_index));
}

// The real MCU->MPU notify for every trigger (device/mpu/bridge/schema.md:
// report_footfall_event) - the fix for docs/KNOWN_GAPS.md's high-severity
// "raw trigger data does not reach the MPU" gap (14 Aug). probability and
// feature_vector are footfall_features.cpp's honest placeholder derivation
// from this same result/window, not a real TinyML model output yet (see
// that file's own header). Bridge.notify() is fire-and-forget - confirmed
// by reading the real installed Arduino_RouterBridge bridge.h directly
// (docs/KNOWN_GAPS.md, Build-call 5): it takes a write mutex and returns
// after a one-way send, never blocking this loop on an MPU reply.
void notify_footfall_event(const float *window, const sta_lta_result &result, uint32_t now_ms) {
  const float probability = footfall_probability_from_ratio(result.peak_ratio);
  std::array<float, 8> feature_vector{};
  footfall_feature_vector(window, SEISMIC_WINDOW_SAMPLES, result, feature_vector.data());

  Bridge.notify("report_footfall_event", static_cast<uint8_t>(BRIDGE_SCHEMA_VERSION), probability,
                result.peak_ratio, feature_vector);

  Serial.print("[notify] t=");
  Serial.print(now_ms);
  Serial.print(" report_footfall_event probability=");
  Serial.print(probability, 4);
  Serial.print(" sta_lta_ratio=");
  Serial.println(result.peak_ratio);
}

#if SEISMIC_DEBUG_VERBOSE
// Bench-only: sta/lta/ratio on a fixed cadence, independent of whether a
// trigger fires - the [trigger] line above only exists at the moment of a
// crossing, which says nothing about where the ratio sits the rest of the
// time. Rate-limited the same way geophone.cpp's [bias-check] line is.
void log_verbose_ratio(const sta_lta_result &result, uint32_t now_ms) {
  static uint32_t s_last_verbose_print_ms = 0;
  if (now_ms - s_last_verbose_print_ms < SEISMIC_DEBUG_PRINT_INTERVAL_MS) {
    return;
  }
  s_last_verbose_print_ms = now_ms;
  Serial.print("[seismic] t=");
  Serial.print(now_ms);
  Serial.print(" sta=");
  Serial.print(result.sta);
  Serial.print(" lta=");
  Serial.print(result.lta);
  Serial.print(" ratio=");
  Serial.println(result.peak_ratio);
}

// Bench-only: the raw window as CSV volts, for scripts/plot_seismic_window.py
// to render - Part C2's sensitivity/waveform-characterization pass, not the
// REF-bias check. Fires alongside every existing [trigger] line, not on its
// own timer - a trigger is already the interesting moment to keep the trace
// for.
void log_window_csv(const float *window, size_t n, uint32_t now_ms) {
  Serial.print("[window] t=");
  Serial.print(now_ms);
  Serial.print(" n=");
  Serial.print(static_cast<unsigned long>(n));
  Serial.print(" rate_hz=");
  Serial.print(SEISMIC_SAMPLE_RATE_HZ);
  Serial.println(" unit=volts");
  for (size_t i = 0; i < n; ++i) {
    Serial.print(window[i], 6);
    if (i + 1 < n) {
      Serial.print(",");
    }
  }
  Serial.println();
}
#endif  // SEISMIC_DEBUG_VERBOSE

}  // namespace

void state_machine_init() { enter(reflex_state::kIdle, millis()); }

void state_machine_tick(uint32_t now_ms) {
  switch (g_state) {
    case reflex_state::kIdle:
      // Entry stub: later build calls gate this transition on fusion/bandit
      // policy (e.g. don't bother sensing if the MPU already reports no
      // elephant presence). For now, idle always proceeds straight to
      // sensing - there is no policy to defer to yet.
      enter(reflex_state::kSensing, now_ms);
      break;

    case reflex_state::kSensing: {
      float window[SEISMIC_WINDOW_SAMPLES];
      read_seismic_window(window);

      const sta_lta_result result =
          sta_lta_detect(window, SEISMIC_WINDOW_SAMPLES, STA_SAMPLES, LTA_SAMPLES,
                         STA_LTA_TRIGGER_RATIO);

#if SEISMIC_DEBUG_VERBOSE
      log_verbose_ratio(result, now_ms);
#endif

      // Exit condition: an STA/LTA threshold crossing moves to EVENT. A
      // zero-filled window (geophone timeout/staleness, see geophone.h)
      // never triggers - sta_lta_detect's own zero-guard handles that.
      if (result.triggered) {
        log_trigger(result, now_ms);
#if SEISMIC_DEBUG_VERBOSE
        log_window_csv(window, SEISMIC_WINDOW_SAMPLES, now_ms);
#endif
        notify_footfall_event(window, result, now_ms);
        enter(reflex_state::kEvent, now_ms);
      }
      // Otherwise: stay in kSensing and re-sample next tick.
      break;
    }

    case reflex_state::kEvent:
      // report_footfall_event already fired on the kSensing -> kEvent
      // transition above (notify_footfall_event), not here - the MPU needs
      // the triggering window/result, and kSensing is where those are still
      // in scope. Entry stub: this is where deterrence policy (which
      // actuator fires at what gain/duration) belongs once fusion/bandit
      // land. For now this state only bounds how long an event is
      // considered "active" before cooldown begins.
      if (elapsed_since_entry(now_ms) >= EVENT_MAX_MS) {
        enter(reflex_state::kCooldown, now_ms);
      }
      break;

    case reflex_state::kCooldown:
      // Exit condition: once COOLDOWN_MS has elapsed since cooldown began,
      // return to idle and allow a new detection cycle.
      if (elapsed_since_entry(now_ms) >= COOLDOWN_MS) {
        enter(reflex_state::kIdle, now_ms);
      }
      break;
  }
}

reflex_state state_machine_get_state() { return g_state; }
