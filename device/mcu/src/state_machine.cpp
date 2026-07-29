#include "state_machine.h"

#include "Arduino.h"
#include "config.h"
#include "footfall/sta_lta.h"
#include "sensors/geophone.h"

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

      // Exit condition: an STA/LTA threshold crossing moves to EVENT. A
      // zero-filled window (geophone timeout/staleness, see geophone.h)
      // never triggers - sta_lta_detect's own zero-guard handles that.
      if (result.triggered) {
        log_trigger(result, now_ms);
        enter(reflex_state::kEvent, now_ms);
      }
      // Otherwise: stay in kSensing and re-sample next tick.
      break;
    }

    case reflex_state::kEvent:
      // Entry stub: this is where deterrence policy (report_footfall_event
      // notify, which actuator fires at what gain/duration) belongs once
      // fusion/bandit land. For now this state only bounds how long an
      // event is considered "active" before cooldown begins.
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
