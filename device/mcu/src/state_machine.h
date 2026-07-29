// Reflex loop shape: IDLE -> SENSING -> EVENT -> COOLDOWN -> IDLE.
//
// This build call wires only the geophone/STA-LTA reflex path end to end
// (enough to produce a logged trigger event on the bench) and leaves the
// EVENT state's actual deterrence policy - which actuator, what gain,
// bandit/fusion input - as a stub. No fusion, no bandit, no Bridge calls, no
// deterrence policy live here yet; those arrive in later build calls.

#ifndef STATE_MACHINE_H
#define STATE_MACHINE_H

#include <cstdint>

enum class reflex_state {
  kIdle,
  kSensing,
  kEvent,
  kCooldown,
};

// One-time setup. Call once from setup(), after the sensor/actuator/LoRa
// subsystems have already run their own _init().
void state_machine_init();

// Advances the reflex state machine by at most one step; call every loop()
// iteration. Never blocks - geophone_service()/lora_service() are serviced
// separately in main.cpp regardless of reflex state.
void state_machine_tick(uint32_t now_ms);

reflex_state state_machine_get_state();

#endif  // STATE_MACHINE_H
