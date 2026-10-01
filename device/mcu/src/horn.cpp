// HORN_AMP_ENABLE_PIN (D11) sequencing and the DFPLAYER_SERIAL AT-command link.
//
// Control path (ADR 0015 Decision E, Decision A superseded): the DFPlayer PRO
// (DFR0768) is driven over USART1 (Serial1, D0/D1) at 115200 baud, NOT the
// old AUDIO_TRIGGER_PIN GPIO pulse into its KEY button. The KEY button can
// only play/pause one fixed track at one fixed volume; the UART carries
// AT+PLAYNUM (which content) and AT+VOL (how loud), the two axes the tier
// ladder needs. AUDIO_TRIGGER_PIN is retained in config.h as a documented
// fallback only. Decision A originally specified a software UART on D9/D10 -
// impossible on this part - and a later usart3/D20-D21 candidate was also
// ruled out, D20/D21 being I2C2-only on the official pinout with no UART
// function at all (see config.h's DFPLAYER_UART_BAUD comment). USART1/D0-D1
// is the only hardware UART this board exposes anywhere; it is shared with
// the LoRa-E5 through a 74HC4053 bus switch (uart_share.h, ADR 0029), and
// every fire claims it first - the horn always wins the port.
//
// fire:  AMP_ENABLE low  (TPA3116D2 held in shutdown)
//     -> "AT+PLAYMODE=<DFPLAYER_PLAYMODE_SINGLE>\r\n" then "AT+PROMPT=OFF\r\n"
//        (see per-fire config note below - resent every fire, not once)
//     -> send "AT+PLAYNUM=<track_id>\r\n"   (select + start the track)
//     -> send "AT+VOL=<n>\r\n"              (set absolute volume for this tier)
//     -> wait HORN_AMP_ENABLE_DELAY_MS      (AT processing + track seek)
//     -> AMP_ENABLE high (amp comes out of shutdown, audio already flowing)
//     -> delay(duration_ms)
//     -> AMP_ENABLE low
//
// Module config (AT+PLAYMODE, AT+PROMPT) is re-sent before every fire, not
// once per boot: it was originally a first-fire-only latch on the theory that
// horn_init() runs too soon after the DFR0768's own power-on for the module to
// answer, and a real footfall is always many seconds later so a first-fire
// send would land safely. Bench testing broke that assumption - a harness fire
// can land within seconds of a fresh reflash, before the module has settled,
// and dfplayer_send() never checks for an OK ack, so a dropped first send
// left the wrong playmode latched (as "configured") for the rest of the
// session. Observed on the bench as clips auto-advancing into each other
// (Stage C) instead of playing one and stopping. Sending both AT commands on
// every fire costs two more UART round-trips - 2 * DFPLAYER_AT_COMMAND_GAP_MS,
// added to the fire sequence rather than absorbed inside
// HORN_AMP_ENABLE_DELAY_MS, since dfplayer_send() settles before the
// amp-enable wait starts - and removes the fragile assumption entirely. 100 ms
// on a ~3.8 s worst-case fire. Play mode also
// does not reliably persist across a power cycle on its own (DFRobot forum
// "DFPlayer Pro Playmode Resets"), which is the other reason not to rely on a
// single send ever sticking.
//
// Rationale unchanged from the KEY-pulse design: the amp stays in shutdown
// across the DFPlayer's command-processing and track-seek latency, so neither
// that transient nor the TPA3116's own un-mute step reaches the horn as an
// audible pop. The delay is spent on the clip's lead-in silence, not content.
// Tear-down kills the amp before anything else for the same reason.
//
// KNOWN_GAPS: the TPA3116D2 has no exposed SD/MUTE pin on this board (D11
// switches its ground return, not a real shutdown pin - checked the
// silkscreen, nothing there), so its own soft-start produces an audible
// rising/falling sweep on every single fire, independent of track content -
// confirmed on the bench 6 Sept, identical on every track. A trial moving the
// amp-enable ahead of the AT commands (so the sweep would land on silence
// instead of overlapping the track's onset) made DFPlayer drop AT+PLAYNUM
// outright on at least one fire - a live, switching amp is a plausible noise
// source onto its own UART RX, and dfplayer_send() has no ack check to catch
// that. Reverted: an audible sweep on every fire is preferable to a horn that
// sometimes plays nothing. The sweep itself is unsolved.
//
// UNVERIFIED (docs/KNOWN_GAPS.md): whether AT+PLAYNUM auto-starts playback or
// only cues it, requiring a follow-up AT+PLAY=PP. A bring-up check. The pure
// string/volume helpers below have no such dependency and are host-tested
// regardless.
//
// AT+PLAYNUM=<n> selects the n-th file in the module's FAT directory order,
// which is the order the files were copied onto the DFR0768's 128 MB onboard
// flash over USB-C - NOT the numeric prefix in the filename. The tracks must
// be loaded one at a time, in the cognition/config.py order (1 bee, 2 tiger,
// 3 lion, 4 air horn, 5 firecracker), and the mapping re-checked at bring-up
// (docs/specs/mcu-fire-test-harness.md provisioning checklist).
//
// HORN_AMP_ENABLE_DELAY_MS is an invented placeholder, not a measured
// DFPlayer seek latency - see docs/KNOWN_GAPS.md.
//
// This file is the sole owner of HORN_AMP_ENABLE_PIN and AUDIO_TRIGGER_PIN,
// and the only writer of DFPLAYER_SERIAL; uart_share.cpp owns opening the
// port and routing it.

#include "horn.h"

#include <cstdio>

#include "Arduino.h"
#include "rule_gate.h"
#include "config.h"
#include "uart_share.h"

namespace {

uint32_t g_last_fire_ms = 0;
bool g_has_fired_before = false;

const gate_limits kHornLimits = {
    /*burst_max_ms=*/HORN_BURST_MAX_MS,
    /*cooldown_ms=*/HORN_COOLDOWN_MS,
    /*gain_max_pct=*/HORN_GAIN_MAX_PCT,
};

// Longest AT string this file emits is "AT+PLAYMODE=255\r\n" = 17 chars + NUL.
constexpr size_t kAtCmdBufLen = 24;

// AT+PLAYFILE's buffer needs to hold real content filenames, which run much
// longer than any other command here (Freesound source names have exceeded
// 60 chars) - matches FIRE_TEST_AT_LINE_MAX_LEN's margin (config.h), the only
// other place that has had to size a buffer for one of these names.
constexpr size_t kPlayfileCmdBufLen = 96;

void dfplayer_send(const char *cmd) {
  if (cmd == nullptr) {
    return;
  }
  DFPLAYER_SERIAL.print(cmd);
  // See DFPLAYER_AT_COMMAND_GAP_MS (config.h): back-to-back AT sends with no
  // settle gap have shown signs of the module dropping/misapplying one of
  // them. Every call site sends multiple commands in a row, so the gap lives
  // once here rather than being repeated at each call site.
  delay(DFPLAYER_AT_COMMAND_GAP_MS);
}

// Push the module settings horn_init() cannot safely send at boot, before
// every fire rather than once (see the per-fire config note at the top of
// this file). Caller supplies a scratch buffer so this shares the fire
// sequence's single stack allocation.
void dfplayer_apply_playback_config(char *cmd, size_t cmd_len) {
  if (horn_at_playmode_command(DFPLAYER_PLAYMODE_SINGLE, cmd, cmd_len)) {
    dfplayer_send(cmd);
  }
  if (horn_at_prompt_command(/*enabled=*/false, cmd, cmd_len)) {
    dfplayer_send(cmd);
  }
}

void horn_fire_sequence(uint16_t duration_ms, uint8_t track_id, float gain_pct) {
  // Amp stays in shutdown while every AT command goes out. Bench trial
  // (6 Sept) tried enabling the amp first instead, on the theory that its own
  // soft-start sweep should play into silence rather than the track's onset -
  // that trial produced a silent no-play instead: dfplayer_send() has no ack
  // check, and a live, actively-switching Class-D amp is a plausible noise
  // source onto the DFPlayer's own UART RX right as AT+PLAYNUM was sent,
  // dropping the command with no visible error. Reverted - a horn that
  // sometimes plays nothing is a worse failure than one with an audible
  // power-up sweep on every fire (KNOWN_GAPS: the sweep itself is unsolved).
  digitalWrite(HORN_AMP_ENABLE_PIN, LOW);
  uart_share_acquire(uart_owner::kDfplayer);

  char cmd[kAtCmdBufLen];
  dfplayer_apply_playback_config(cmd, sizeof(cmd));
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

bool horn_at_playfile_command(const char *filename, char *buf, size_t buf_len) {
  if (filename == nullptr || buf == nullptr || buf_len == 0) {
    return false;
  }
  const int n = snprintf(buf, buf_len, "AT+PLAYFILE=/%s\r\n", filename);
  if (n < 0 || static_cast<size_t>(n) >= buf_len) {
    buf[0] = '\0';
    return false;
  }
  return true;
}

bool horn_at_playmode_command(uint8_t mode, char *buf, size_t buf_len) {
  if (buf == nullptr || buf_len == 0) {
    return false;
  }
  const int n = snprintf(buf, buf_len, "AT+PLAYMODE=%u\r\n", static_cast<unsigned>(mode));
  if (n < 0 || static_cast<size_t>(n) >= buf_len) {
    buf[0] = '\0';
    return false;
  }
  return true;
}

bool horn_at_prompt_command(bool enabled, char *buf, size_t buf_len) {
  if (buf == nullptr || buf_len == 0) {
    return false;
  }
  const int n = snprintf(buf, buf_len, "AT+PROMPT=%s\r\n", enabled ? "ON" : "OFF");
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
  uart_share_init();
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

void horn_debug_listen(uint8_t track_id, float gain_pct, uint16_t duration_ms) {
  horn_fire_sequence(duration_ms, track_id, gain_pct);
}

void horn_debug_listen_file(const char *filename, float gain_pct, uint16_t duration_ms) {
  // See horn_fire_sequence()'s reverted ordering above - same reasoning.
  digitalWrite(HORN_AMP_ENABLE_PIN, LOW);
  uart_share_acquire(uart_owner::kDfplayer);

  char small_cmd[kAtCmdBufLen];
  dfplayer_apply_playback_config(small_cmd, sizeof(small_cmd));

  char file_cmd[kPlayfileCmdBufLen];
  if (horn_at_playfile_command(filename, file_cmd, sizeof(file_cmd))) {
    dfplayer_send(file_cmd);
  }
  if (horn_at_vol_command(horn_dfplayer_volume_from_gain_pct(gain_pct), small_cmd,
                           sizeof(small_cmd))) {
    dfplayer_send(small_cmd);
  }

  delay(HORN_AMP_ENABLE_DELAY_MS);
  digitalWrite(HORN_AMP_ENABLE_PIN, HIGH);

  delay(duration_ms);

  digitalWrite(HORN_AMP_ENABLE_PIN, LOW);
}
