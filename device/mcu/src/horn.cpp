// HORN_AMP_ENABLE_PIN (D4) sequencing and the DFPLAYER_SERIAL AT-command link.
//
// Control path (ADR 0015 Decision A/E): the DFPlayer PRO (DFR0768) is driven
// over a dedicated software UART on D9/D10 at 115200 baud, NOT the old
// AUDIO_TRIGGER_PIN GPIO pulse into its KEY button. The KEY button can only
// play/pause one fixed track at one fixed volume; the UART carries AT+PLAYNUM
// (which content) and AT+VOL (how loud), the two axes the tier ladder needs.
// AUDIO_TRIGGER_PIN is retained in config.h as a documented fallback only.
//
// fire:  AMP_ENABLE low  (TPA3116D2 held in shutdown)
//     -> send "AT+PLAYNUM=<track_id>\r\n"   (select + start the track)
//     -> send "AT+VOL=<n>\r\n"              (set absolute volume for this tier)
//     -> wait HORN_AMP_ENABLE_DELAY_MS      (AT processing + track seek)
//     -> AMP_ENABLE high (amp comes out of shutdown, audio already flowing)
//     -> delay(duration_ms)
//     -> AMP_ENABLE low
//
// Rationale unchanged from the KEY-pulse design: the amp stays in shutdown
// across the DFPlayer's command-processing and track-seek latency, so neither
// that transient nor the TPA3116's own un-mute step reaches the horn as an
// audible pop. The delay is spent on the clip's lead-in silence, not content.
// Tear-down kills the amp before anything else for the same reason.
//
// UNVERIFIED (config.h's DFPLAYER_SERIAL / DFPLAYER_UART_* caveats): whether
// this Zephyr-based Arduino Core supports a SoftwareSerial-style link on
// D9/D10 at all, and whether AT+PLAYNUM auto-starts playback or only cues it
// (docs/KNOWN_GAPS.md). Both are bring-up checks. The pure string/volume
// helpers below have no such dependency and are host-tested regardless.
//
// HORN_AMP_ENABLE_DELAY_MS is an invented placeholder, not a measured
// DFPlayer seek latency - see docs/KNOWN_GAPS.md.
//
// This file is the sole owner of HORN_AMP_ENABLE_PIN, AUDIO_TRIGGER_PIN, and
// DFPLAYER_SERIAL; no other translation unit may touch them.

#include "horn.h"

#include <cstdio>

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

// Longest AT string this file emits is "AT+PLAYNUM=255\r\n" = 16 chars + NUL.
constexpr size_t kAtCmdBufLen = 24;

void dfplayer_send(const char *cmd) {
  if (cmd == nullptr) {
    return;
  }
  DFPLAYER_SERIAL.print(cmd);
}

void horn_fire_sequence(uint16_t duration_ms, uint8_t track_id, float gain_pct) {
  digitalWrite(HORN_AMP_ENABLE_PIN, LOW);

  char cmd[kAtCmdBufLen];
  if (horn_at_playnum_command(track_id, cmd, sizeof(cmd))) {
    dfplayer_send(cmd);
  }
  if (horn_at_vol_command(horn_dfplayer_volume_from_gain_pct(gain_pct), cmd, sizeof(cmd))) {
    dfplayer_send(cmd);
  }

  delay(HORN_AMP_ENABLE_DELAY_MS);
  digitalWrite(HORN_AMP_ENABLE_PIN, HIGH);

  delay(duration_ms);

  digitalWrite(HORN_AMP_ENABLE_PIN, LOW);
}

}  // namespace

uint8_t horn_dfplayer_volume_from_gain_pct(float gain_pct) {
  const float clamped = (gain_pct < 0.0f) ? 0.0f : (gain_pct > 100.0f ? 100.0f : gain_pct);
  // Round half up without pulling in libm: (x*MAX + 50) / 100 on a
  // non-negative x. clamped <= 100 keeps the result <= DFPLAYER_VOL_MAX.
  return static_cast<uint8_t>((clamped * DFPLAYER_VOL_MAX + 50.0f) / 100.0f);
}

bool horn_at_vol_command(uint8_t dfplayer_vol, char *buf, size_t buf_len) {
  if (buf == nullptr || buf_len == 0) {
    return false;
  }
  const int n = snprintf(buf, buf_len, "AT+VOL=%u\r\n", static_cast<unsigned>(dfplayer_vol));
  if (n < 0 || static_cast<size_t>(n) >= buf_len) {
    buf[0] = '\0';
    return false;
  }
  return true;
}

bool horn_at_playnum_command(uint8_t track_id, char *buf, size_t buf_len) {
  if (buf == nullptr || buf_len == 0) {
    return false;
  }
  const int n = snprintf(buf, buf_len, "AT+PLAYNUM=%u\r\n", static_cast<unsigned>(track_id));
  if (n < 0 || static_cast<size_t>(n) >= buf_len) {
    buf[0] = '\0';
    return false;
  }
  return true;
}

void horn_init() {
  pinMode(AUDIO_TRIGGER_PIN, OUTPUT);
  pinMode(HORN_AMP_ENABLE_PIN, OUTPUT);
  digitalWrite(AUDIO_TRIGGER_PIN, HIGH);   // idle high - retired KEY-pin fallback rests unpressed
  digitalWrite(HORN_AMP_ENABLE_PIN, LOW);  // amp held in shutdown at boot
  DFPLAYER_SERIAL.begin(DFPLAYER_UART_BAUD);
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

  horn_fire_sequence(gate.duration_ms, req.track_id, gate.gain_pct);

  g_last_fire_ms = now_ms;
  g_has_fired_before = true;
  return ack;
}
