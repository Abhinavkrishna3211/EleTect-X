// Actuator safety rule-gate - pure function, no hardware calls.
//
// The burst-duration cap and cooldown clamp math ADR 0003 requires for every
// actuator, factored out of horn/led/ir so it is unit-testable on its own
// (ENGINEERING_CONVENTIONS.md 2/4). horn.cpp, led.cpp and ir.cpp are thin
// shells that call this, drive GPIO for the resolved duration, and return the
// ack - each with its own independent gate_state (device/mpu/bridge/schema.md:
// "independent counters per actuator").
//
// Clamp and ack, never silent-drop: an out-of-bounds request is clamped to the
// limit and reported as clamped, not rejected outright. A request inside
// cooldown is the one case that is refused - allowed = false - because there
// is no in-bounds duration/gain that would make firing again right now safe.

#ifndef ACTUATORS_RULE_GATE_H
#define ACTUATORS_RULE_GATE_H

#include <cstdint>

struct gate_request {
  uint16_t duration_ms;
  float gain_pct;  // 0-100
};

struct gate_limits {
  uint16_t burst_max_ms;
  uint16_t cooldown_ms;
  float gain_max_pct;
};

struct gate_result {
  uint16_t duration_ms;  // value actually to be used
  float gain_pct;         // value actually to be used
  bool clamped;           // true if duration or gain was reduced to fit limits
  bool allowed;           // false if still in cooldown - nothing should fire
};

// now_ms and last_fire_ms are both millis()-style monotonic counters, so this
// is rollover-safe via unsigned subtraction rather than a direct comparison:
// (now_ms - last_fire_ms) is correct across a wraparound, (now_ms >
// last_fire_ms) is not.
//
// last_fire_ms == 0 with now_ms == 0 (the state at boot, before anything has
// ever fired) is treated as "never fired" - never in cooldown.
gate_result rule_gate_apply(gate_request req, const gate_limits &lim,
                            uint32_t last_fire_ms, uint32_t now_ms,
                            bool has_fired_before);

#endif  // ACTUATORS_RULE_GATE_H
