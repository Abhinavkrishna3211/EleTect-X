#include "rule_gate.h"

#include <algorithm>

gate_result rule_gate_apply(gate_request req, const gate_limits &lim,
                            uint32_t last_fire_ms, uint32_t now_ms,
                            bool has_fired_before) {
  gate_result result{};

  if (has_fired_before) {
    // Unsigned subtraction is rollover-safe: this is correct even when now_ms
    // has wrapped past last_fire_ms, unlike a direct now_ms < last_fire_ms
    // comparison would be.
    const uint32_t elapsed_ms = now_ms - last_fire_ms;
    if (elapsed_ms < lim.cooldown_ms) {
      result.duration_ms = 0;
      result.gain_pct = 0.0f;
      result.clamped = false;
      result.allowed = false;
      return result;
    }
  }

  const uint16_t clamped_duration =
      std::min(req.duration_ms, lim.burst_max_ms);
  const float clamped_gain =
      std::min(std::max(req.gain_pct, 0.0f), lim.gain_max_pct);

  result.duration_ms = clamped_duration;
  result.gain_pct = clamped_gain;
  result.clamped =
      (clamped_duration != req.duration_ms) || (clamped_gain != req.gain_pct);
  result.allowed = true;
  return result;
}
