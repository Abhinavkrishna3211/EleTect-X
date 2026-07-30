// Horn deterrence driver - sole owner of AUDIO_TRIGGER_PIN and
// HORN_AMP_ENABLE_PIN (config.h). No other file may touch either pin.
//
// See horn.cpp for the fire/stop pin-sequencing rationale (ADR 0003).

#ifndef ACTUATORS_HORN_H
#define ACTUATORS_HORN_H

#include <cstdint>

// Request to sound the horn for up to duration_ms at up to gain_pct of the
// channel's software-limited gain ceiling (HORN_GAIN_MAX_PCT).
struct horn_request {
  uint16_t duration_ms;
  float gain_pct;
};

// Ack, mirroring gate_result: the caller must inspect this rather than assume
// the request landed as sent. clamped means the values were reduced to fit
// ADR 0003's burst/gain caps and still executed; allowed=false means the
// horn is in cooldown and nothing fired.
struct horn_ack {
  uint16_t duration_ms;
  float gain_pct;
  bool clamped;
  bool allowed;
};

// One-time setup: configures AUDIO_TRIGGER_PIN and HORN_AMP_ENABLE_PIN as
// outputs, amp held in shutdown. Call once from setup().
void horn_init();

// Runs the fire/stop sequence documented at the top of horn.cpp, subject to
// rule_gate_apply()'s clamp-and-cooldown. Blocks for HORN_AMP_ENABLE_DELAY_MS
// (a bounded, documented delay - not an unbounded/hardware wait) plus the
// resolved duration; the reflex loop calling this must expect that.
horn_ack drive_horn(horn_request req, uint32_t now_ms);

#endif  // ACTUATORS_HORN_H
