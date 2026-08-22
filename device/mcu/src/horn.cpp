// AUDIO_TRIGGER_PIN (D2) and HORN_AMP_ENABLE_PIN (D4) sequencing.
//
// AUDIO_TRIGGER_PIN is active-low: the DFPlayer PRO's DF1101S chip pulls its
// KEY (ADKEY) input up to its own IO rail through a 22k resistor, idle high,
// and reads a direct short to ground as key K1 (Play & Pause). This MCU pin
// must therefore idle high and pulse low to register a press.
//
// fire:  AMP_ENABLE low  (TPA3116D2 held in shutdown)
//     -> pulse AUDIO_TRIGGER (DFPlayer starts seeking the track)
//     -> wait HORN_AMP_ENABLE_DELAY_MS
//     -> AMP_ENABLE high (amp comes out of shutdown, audio already flowing)
// stop:  AMP_ENABLE low first
//     -> then stop/idle the DFPlayer
//
// Rationale: the amp stays in shutdown across the DFPlayer's own trigger and
// track-seek latency, so neither the ADKEY switching transient nor the
// TPA3116's own un-mute step reaches the horn as an audible pop. The delay is
// sized to cover DFPlayer seek, so it costs lead-in silence, not clip
// content. Tear-down runs the reverse order for the same reason: killing the
// amp before the DFPlayer avoids a pop on the way down too.
//
// HORN_AMP_ENABLE_DELAY_MS is an invented placeholder, not a measured
// DFPlayer Mini seek latency - see docs/KNOWN_GAPS.md.
//
// This file is the sole owner of both pins; no other translation unit may
// call pinMode/digitalWrite on AUDIO_TRIGGER_PIN or HORN_AMP_ENABLE_PIN.

#include "horn.h"

#include "Arduino.h"
#include "rule_gate.h"
#include "config.h"

namespace {

uint32_t g_last_fire_ms = 0;
bool g_has_fired_before = false;

const gate_limits kHornLimits = {
    /*burst_max_ms=*/HORN_BURST_MAX_MS,
    /*cooldown_ms=*/HORN_COOLDOWN_MS,
    /*gain_max_pct=*/HORN_GAIN_MAX_PCT,
};

void horn_fire_sequence(uint16_t duration_ms) {
  digitalWrite(HORN_AMP_ENABLE_PIN, LOW);
  digitalWrite(AUDIO_TRIGGER_PIN, LOW);
  delay(AUDIO_TRIGGER_PULSE_MS);
  digitalWrite(AUDIO_TRIGGER_PIN, HIGH);

  delay(HORN_AMP_ENABLE_DELAY_MS);
  digitalWrite(HORN_AMP_ENABLE_PIN, HIGH);

  delay(duration_ms);

  digitalWrite(HORN_AMP_ENABLE_PIN, LOW);
}

}  // namespace

void horn_init() {
  pinMode(AUDIO_TRIGGER_PIN, OUTPUT);
  pinMode(HORN_AMP_ENABLE_PIN, OUTPUT);
  digitalWrite(AUDIO_TRIGGER_PIN, HIGH);  // idle high - DFPlayer KEY pull-up rests unpressed
  digitalWrite(HORN_AMP_ENABLE_PIN, LOW);  // amp held in shutdown at boot
}

horn_ack drive_horn(horn_request req, uint32_t now_ms) {
  const gate_request gate_req = {req.duration_ms, req.gain_pct};
  const gate_result gate = rule_gate_apply(gate_req, kHornLimits, g_last_fire_ms,
                                            now_ms, g_has_fired_before);

  horn_ack ack{};
  ack.duration_ms = gate.duration_ms;
  ack.gain_pct = gate.gain_pct;
  ack.clamped = gate.clamped;
  ack.allowed = gate.allowed;

  if (!gate.allowed) {
    return ack;
  }

  horn_fire_sequence(gate.duration_ms);

  g_last_fire_ms = now_ms;
  g_has_fired_before = true;
  return ack;
}
