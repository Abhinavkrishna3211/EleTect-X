#include "led.h"

#include "Arduino.h"
#include "rule_gate.h"
#include "config.h"

namespace {

const gate_limits kLedLimits = {
    /*burst_max_ms=*/LED_BURST_MAX_MS,
    /*cooldown_ms=*/LED_COOLDOWN_MS,
    /*gain_max_pct=*/LED_GAIN_MAX_PCT,
};

// Independent cooldown state per channel - left wing and right wing must
// not gate each other.
struct channel_state {
  int pin;
  uint32_t last_fire_ms;
  bool has_fired_before;
};

channel_state g_wing_left = {LED_WING_LEFT_PIN, 0, false};
channel_state g_wing_right = {LED_WING_RIGHT_PIN, 0, false};

channel_state &state_for(led_channel channel) {
  return (channel == led_channel::kWingLeft) ? g_wing_left : g_wing_right;
}

// gain_pct (0-100) -> analogWrite duty (0-255).
uint8_t gain_to_duty(float gain_pct) {
  const float clamped = (gain_pct < 0.0f) ? 0.0f : (gain_pct > 100.0f ? 100.0f : gain_pct);
  return static_cast<uint8_t>((clamped / 100.0f) * 255.0f);
}

// Self-contained PRNG for kRandomFlicker's irregular gaps. xorshift32: no
// <random>, no libm, no heap - the same "keep the reflex layer free of
// transcendental/allocating calls" constraint config.h's footfall-probability
// note documents. Seeded from micros() at call time so the flicker differs
// run to run without adding any wire field.
uint32_t xorshift32(uint32_t &s) {
  s ^= s << 13;
  s ^= s >> 17;
  s ^= s << 5;
  return s;
}

// Uniform in [lo, hi]. lo <= hi is guaranteed by the config.h constants.
uint32_t rand_range(uint32_t &s, uint32_t lo, uint32_t hi) {
  return lo + (xorshift32(s) % (hi - lo + 1));
}

void flash_on(int pin, uint8_t duty, uint32_t ms) {
  analogWrite(pin, duty);
  delay(ms);
}

void flash_off(int pin, uint32_t ms) {
  analogWrite(pin, 0);
  delay(ms);
}

// Dual-wing primitive (ADR 0014 E): set both pins, then ONE delay. The
// blocking window is shared between the two wings, so a dual-wing burst of
// duration D costs D of wall time, not 2D - the reason firmware-level
// dual-wing beats two back-to-back single-wing Bridge calls
// (docs/KNOWN_GAPS.md geophone/LoRa-starvation window).
void flash_pair(int pin_a, uint8_t duty_a, int pin_b, uint8_t duty_b, uint32_t ms) {
  analogWrite(pin_a, duty_a);
  analogWrite(pin_b, duty_b);
  delay(ms);
}

// Each pattern below drives `pin` for exactly total_ms of wall time and
// leaves it off on return - the blocking cost is identical to a kSteady
// burst regardless of pattern (ADR 0014).

void pattern_steady(int pin, uint8_t duty, uint32_t total_ms) {
  flash_on(pin, duty, total_ms);
  analogWrite(pin, 0);
}

void pattern_slow_pulse(int pin, uint8_t duty, uint32_t total_ms) {
  const uint32_t cycles = LED_SLOW_PULSE_CYCLES;
  uint32_t elapsed = 0;
  for (uint32_t i = 0; i < cycles; ++i) {
    // Divide the time still remaining evenly across the cycles still to
    // run, so integer-division remainder lands inside the final cycle
    // rather than being dropped - the burst still totals total_ms exactly.
    const uint32_t this_cycle = (total_ms - elapsed) / (cycles - i);
    const uint32_t on_ms = this_cycle / 2;
    flash_on(pin, duty, on_ms);
    flash_off(pin, this_cycle - on_ms);
    elapsed += this_cycle;
  }
  analogWrite(pin, 0);
}

void pattern_fast_strobe(int pin, uint8_t duty, uint32_t total_ms) {
  const uint32_t period = 1000UL / LED_FAST_STROBE_HZ;
  uint32_t elapsed = 0;
  while (total_ms - elapsed >= period) {
    const uint32_t on_ms = period / 2;
    flash_on(pin, duty, on_ms);
    flash_off(pin, period - on_ms);
    elapsed += period;
  }
  // Spend the sub-period remainder dark so the burst still totals total_ms.
  analogWrite(pin, 0);
  if (elapsed < total_ms) {
    delay(total_ms - elapsed);
  }
}

void pattern_random_flicker(int pin, uint8_t duty, uint32_t total_ms, uint32_t seed) {
  uint32_t s = (seed != 0) ? seed : 0xA5A5A5A5UL;  // xorshift32 must not seed 0
  uint32_t elapsed = 0;
  while (elapsed < total_ms) {
    uint32_t on_ms = rand_range(s, LED_RANDOM_FLICKER_MIN_ON_MS, LED_RANDOM_FLICKER_MAX_ON_MS);
    if (on_ms > total_ms - elapsed) {
      on_ms = total_ms - elapsed;
    }
    flash_on(pin, duty, on_ms);
    elapsed += on_ms;
    if (elapsed >= total_ms) {
      break;
    }

    uint32_t gap_ms = rand_range(s, LED_RANDOM_FLICKER_MIN_GAP_MS, LED_RANDOM_FLICKER_MAX_GAP_MS);
    if (gap_ms > total_ms - elapsed) {
      gap_ms = total_ms - elapsed;
    }
    flash_off(pin, gap_ms);
    elapsed += gap_ms;
  }
  analogWrite(pin, 0);
}

// --- Dual-wing patterns (ADR 0014 E) ------------------------------------
// Each drives BOTH pins for exactly total_ms of shared wall time and leaves
// both off on return, same "no extra blocking cost" contract as the
// single-wing patterns. sweep runs at LED_FAST_STROBE_HZ; pulse_both_sync
// runs at the faster LED_STROBE_FAST_HZ. Per ADR 0014 E.3 the ladder
// escalates on gain held at max, plus wing count, pattern character, and -
// at the top rung only - strobe rate; the honest-bound caveat there notes
// no data ranks one multi-light phase relationship or rate above another.

// Left and right in antiphase: while one wing is on, the other is off, then
// they swap, repeating at the fast-strobe period. An apparent-movement cue,
// not a claim of locomotion mimicry (ADR 0014 E.1).
void pattern_sweep(int pin_l, int pin_r, uint8_t duty, uint32_t total_ms) {
  const uint32_t period = 1000UL / LED_FAST_STROBE_HZ;
  uint32_t elapsed = 0;
  while (total_ms - elapsed >= period) {
    const uint32_t half = period / 2;
    // Break-before-make each swap: the wing going dark is written before the
    // wing coming on, so the two are never driven high in the same instant.
    flash_pair(pin_r, 0, pin_l, duty, half);
    flash_pair(pin_l, 0, pin_r, duty, period - half);
    elapsed += period;
  }
  analogWrite(pin_l, 0);
  analogWrite(pin_r, 0);
  if (elapsed < total_ms) {
    delay(total_ms - elapsed);
  }
}

// Both wings driven together, in phase, at LED_STROBE_FAST_HZ - the most
// literal "doubled strobe" reading of the DFO practitioner input, genuinely
// doubling light output over a single-wing fire at the same gain, and run
// at the faster top-tier escalation rate (ADR 0014 E.3).
void pattern_pulse_both_sync(int pin_l, int pin_r, uint8_t duty, uint32_t total_ms) {
  const uint32_t period = 1000UL / LED_STROBE_FAST_HZ;
  uint32_t elapsed = 0;
  while (total_ms - elapsed >= period) {
    const uint32_t on_ms = period / 2;
    flash_pair(pin_l, duty, pin_r, duty, on_ms);
    flash_pair(pin_l, 0, pin_r, 0, period - on_ms);
    elapsed += period;
  }
  analogWrite(pin_l, 0);
  analogWrite(pin_r, 0);
  if (elapsed < total_ms) {
    delay(total_ms - elapsed);
  }
}

// Both wings run pattern_random_flicker's irregular on/gap logic from their
// OWN xorshift32 stream, so the two are not mirrored - reads as two
// independent erratic sources rather than one bigger light (ADR 0014 E.1).
// Shared-clock event merge: the loop only ever delays to whichever wing
// flips next (clamped to total_ms), so total wall time stays exactly
// total_ms regardless of how the two schedules interleave.
void pattern_flicker_both_independent(int pin_l, int pin_r, uint8_t duty, uint32_t total_ms,
                                      uint32_t seed_l, uint32_t seed_r) {
  uint32_t s_l = (seed_l != 0) ? seed_l : 0xA5A5A5A5UL;  // xorshift32 must not seed 0
  uint32_t s_r = (seed_r != 0) ? seed_r : 0x5A5A5A5AUL;

  bool on_l = true;
  bool on_r = true;
  analogWrite(pin_l, duty);
  analogWrite(pin_r, duty);

  // Absolute elapsed-ms at which each wing next toggles. First ON span is
  // drawn from the same [MIN_ON, MAX_ON] envelope the single-wing flicker
  // uses; every span after that is ON- or GAP-length depending on the state
  // being entered. MIN_ON/MIN_GAP are both > 0 (config.h), so each draw
  // advances the wing's next-toggle time and the loop always terminates.
  uint32_t next_l = rand_range(s_l, LED_RANDOM_FLICKER_MIN_ON_MS, LED_RANDOM_FLICKER_MAX_ON_MS);
  uint32_t next_r = rand_range(s_r, LED_RANDOM_FLICKER_MIN_ON_MS, LED_RANDOM_FLICKER_MAX_ON_MS);

  uint32_t elapsed = 0;
  while (elapsed < total_ms) {
    uint32_t target = (next_l < next_r) ? next_l : next_r;
    if (target > total_ms) {
      target = total_ms;
    }
    if (target > elapsed) {
      delay(target - elapsed);
      elapsed = target;
    }
    if (elapsed >= total_ms) {
      break;
    }
    if (elapsed >= next_l) {
      on_l = !on_l;
      analogWrite(pin_l, on_l ? duty : 0);
      next_l = elapsed + (on_l ? rand_range(s_l, LED_RANDOM_FLICKER_MIN_ON_MS,
                                            LED_RANDOM_FLICKER_MAX_ON_MS)
                                : rand_range(s_l, LED_RANDOM_FLICKER_MIN_GAP_MS,
                                             LED_RANDOM_FLICKER_MAX_GAP_MS));
    }
    if (elapsed >= next_r) {
      on_r = !on_r;
      analogWrite(pin_r, on_r ? duty : 0);
      next_r = elapsed + (on_r ? rand_range(s_r, LED_RANDOM_FLICKER_MIN_ON_MS,
                                            LED_RANDOM_FLICKER_MAX_ON_MS)
                                : rand_range(s_r, LED_RANDOM_FLICKER_MIN_GAP_MS,
                                             LED_RANDOM_FLICKER_MAX_GAP_MS));
    }
  }
  analogWrite(pin_l, 0);
  analogWrite(pin_r, 0);
}

void run_pattern(int pin, led_pattern pattern, uint32_t total_ms, float gain_pct) {
  const uint8_t duty = gain_to_duty(gain_pct);
  switch (pattern) {
    case led_pattern::kSlowPulse:
      pattern_slow_pulse(pin, duty, total_ms);
      break;
    case led_pattern::kFastStrobe:
      pattern_fast_strobe(pin, duty, total_ms);
      break;
    case led_pattern::kRandomFlicker:
      pattern_random_flicker(pin, duty, total_ms, micros());
      break;
    case led_pattern::kSteady:
    default:
      pattern_steady(pin, duty, total_ms);
      break;
  }
}

void run_pattern_dual(int pin_l, int pin_r, led_pattern pattern, uint32_t total_ms,
                      float gain_pct) {
  const uint8_t duty = gain_to_duty(gain_pct);
  switch (pattern) {
    case led_pattern::kSweep:
      pattern_sweep(pin_l, pin_r, duty, total_ms);
      break;
    case led_pattern::kPulseBothSync:
      pattern_pulse_both_sync(pin_l, pin_r, duty, total_ms);
      break;
    case led_pattern::kFlickerBothIndependent: {
      // micros() barely advances between two reads on this MCU and not at
      // all on the host shim, so XOR the second seed with the golden-ratio
      // constant to guarantee the two wings run distinct xorshift streams.
      const uint32_t seed = micros();
      pattern_flicker_both_independent(pin_l, pin_r, duty, total_ms, seed,
                                       seed ^ 0x9E3779B9UL);
      break;
    }
    default:
      // A single-wing pattern addressed to both wings: a synchronized hold
      // on both pins for the window. Safe fallback, not the intended use -
      // the schema documents pattern_id 0-3 as single-wing.
      flash_pair(pin_l, duty, pin_r, duty, total_ms);
      analogWrite(pin_l, 0);
      analogWrite(pin_r, 0);
      break;
  }
}

}  // namespace

led_pattern led_pattern_from_id(uint8_t pattern_id) {
  // Unknown ids fall back to kSteady - a stale or garbled request still
  // fires the safe default rather than nothing (ADR 0014).
  switch (pattern_id) {
    case 1:
      return led_pattern::kSlowPulse;
    case 2:
      return led_pattern::kFastStrobe;
    case 3:
      return led_pattern::kRandomFlicker;
    case 4:
      return led_pattern::kSweep;
    case 5:
      return led_pattern::kPulseBothSync;
    case 6:
      return led_pattern::kFlickerBothIndependent;
    case 0:
    default:
      return led_pattern::kSteady;
  }
}

void led_init() {
  pinMode(LED_WING_LEFT_PIN, OUTPUT);
  pinMode(LED_WING_RIGHT_PIN, OUTPUT);
  digitalWrite(LED_WING_LEFT_PIN, LOW);
  digitalWrite(LED_WING_RIGHT_PIN, LOW);
}

namespace {

led_ack drive_led_single(const led_request &req, uint32_t now_ms) {
  channel_state &state = state_for(req.channel);

  const gate_request gate_req = {req.duration_ms, req.gain_pct};
  const gate_result gate = rule_gate_apply(gate_req, kLedLimits, state.last_fire_ms,
                                            now_ms, state.has_fired_before);

  led_ack ack{};
  ack.duration_ms = gate.duration_ms;
  ack.gain_pct = gate.gain_pct;
  ack.clamped = gate.clamped;
  ack.allowed = gate.allowed;

  if (!gate.allowed) {
    return ack;
  }

  // Pattern shapes the burst; rule_gate_apply() above already resolved how
  // long it runs and at what duty, and remains the sole authority on both.
  run_pattern(state.pin, req.pattern, gate.duration_ms, gate.gain_pct);

  state.last_fire_ms = now_ms;
  state.has_fired_before = true;
  return ack;
}

// Both wings in one call (ADR 0014 E). Gates each wing against its own
// independent cooldown counter; refuses the whole fire if EITHER is still
// cooling, since a one-wing render of a two-wing pattern is not the pattern
// asked for. When allowed, rule_gate_apply() resolves duration/gain purely
// from the request and the (shared) limits - identical for both wings - so
// the left wing's gate result describes the whole burst.
led_ack drive_led_both(const led_request &req, uint32_t now_ms) {
  const gate_request gate_req = {req.duration_ms, req.gain_pct};
  const gate_result gate_l = rule_gate_apply(gate_req, kLedLimits, g_wing_left.last_fire_ms,
                                              now_ms, g_wing_left.has_fired_before);
  const gate_result gate_r = rule_gate_apply(gate_req, kLedLimits, g_wing_right.last_fire_ms,
                                              now_ms, g_wing_right.has_fired_before);

  led_ack ack{};
  ack.duration_ms = gate_l.duration_ms;
  ack.gain_pct = gate_l.gain_pct;
  ack.clamped = gate_l.clamped || gate_r.clamped;
  ack.allowed = gate_l.allowed && gate_r.allowed;

  if (!ack.allowed) {
    return ack;
  }

  run_pattern_dual(g_wing_left.pin, g_wing_right.pin, req.pattern, gate_l.duration_ms,
                   gate_l.gain_pct);

  g_wing_left.last_fire_ms = now_ms;
  g_wing_left.has_fired_before = true;
  g_wing_right.last_fire_ms = now_ms;
  g_wing_right.has_fired_before = true;
  return ack;
}

}  // namespace

led_ack drive_led(led_request req, uint32_t now_ms) {
  if (req.channel == led_channel::kWingBoth) {
    return drive_led_both(req, now_ms);
  }
  return drive_led_single(req, now_ms);
}
