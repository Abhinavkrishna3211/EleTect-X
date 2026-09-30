// LoRaWAN uplink payload format (ADR 0031). Pure encoders - no Serial, no
// radio, no clock - so the byte layout is pinned by host tests and the web
// ingest decoder (web/ingest/src/payload.ts) is tested against the same
// vectors.
//
// Every frame goes out on LORA_UPLINK_FPORT and starts with the same two
// bytes:
//
//   byte 0  (format << 4) | type     format = UPLINK_FORMAT_VERSION
//   byte 1  seq                      per-node counter, wraps at 256
//
// `seq` is assigned when a frame is queued, not when it is sent, so a frame
// re-sent after a horn fire cut its AT exchange short carries the same seq and
// the server can drop the duplicate. All multi-byte fields are big-endian.
//
// Event (type 2), 10 bytes:
//   2  event class (uplink_event_class)
//   3  confidence, 0-100 %
//   4  deterrence tier, 0 = none, 1-3
//   5  flags (UPLINK_EVENT_FLAG_*)
//   6-9 capture_ref
//
// Status (type 1), 9 bytes:
//   2  flags (UPLINK_STATUS_FLAG_*)
//   3-4 battery, mV; UPLINK_BATTERY_UNKNOWN when there is no reading
//   5-8 uptime, s

#ifndef UPLINK_H
#define UPLINK_H

#include <cstddef>
#include <cstdint>

#define UPLINK_FORMAT_VERSION 1

#define UPLINK_TYPE_STATUS 1
#define UPLINK_TYPE_EVENT 2

#define UPLINK_EVENT_LEN 10
#define UPLINK_STATUS_LEN 9

// What the node saw. Codes are wire values - append only, never renumber.
enum class uplink_event_class : uint8_t {
  kUnconfirmed = 0,  // seismic alert the camera did not confirm
  kElephant = 1,
  kBoar = 2,
  kGunshot = 3,
  kChainsaw = 4,
  kElephantCall = 5,  // heard, not seen - see the note below
  kFox = 6,
};

// kElephantCall is an acoustic detection, not a sighting. It is a separate
// code from kElephant on purpose: an officer reading "elephant" must be
// able to tell a camera confirmation from a microphone one, and the two
// have different false-positive profiles. When vision does confirm the
// same encounter the node sends kElephant with
// UPLINK_EVENT_FLAG_VISION_CONFIRMED, so the server sees both and can
// collapse them; it never sees kElephantCall carrying that flag.

// Highest valid uplink_event_class value; anything above it is sent as
// kUnconfirmed rather than as a code the server cannot name.
#define UPLINK_EVENT_CLASS_MAX 6

#define UPLINK_EVENT_FLAG_VISION_CONFIRMED 0x01
#define UPLINK_EVENT_FLAG_DETERRENT_FIRED 0x02
#define UPLINK_EVENT_FLAG_SAFE_MODE 0x04

// Set when the node fired its top tier and the animal was still there at
// the end of the retreat tail. It is the only thing in the protocol that
// says the node has run out of options and a person has to go, so the
// server raises it above a routine alert rather than adding one more line
// to a feed. Measured on the device (ADR 0034): inferring it in the cloud
// from a repeat trigger arrives minutes late, and never fires at all if
// the animal stays put without crossing the geophone gate again.
#define UPLINK_EVENT_FLAG_NO_RETREAT 0x08

#define UPLINK_STATUS_FLAG_GEOPHONE_OK 0x01
#define UPLINK_STATUS_FLAG_HOME_TEST 0x02

#define UPLINK_BATTERY_UNKNOWN 0xFFFFu

struct uplink_event {
  uint8_t event_class;  // uplink_event_class, as sent over the Bridge
  float confidence;     // 0-1
  uint8_t tier;         // 0-3
  uint8_t flags;
  uint32_t capture_ref;
};

struct uplink_status {
  uint8_t flags;
  uint16_t battery_mv;
  uint32_t uptime_s;
};

// Each returns the number of bytes written, or 0 if `out` is null or `cap`
// is too small. Out-of-range fields are clamped, never rejected: confidence
// to 0-100 %, tier to 0-3, an unknown class to kUnconfirmed.
size_t uplink_encode_event(const uplink_event &ev, uint8_t seq, uint8_t *out, size_t cap);
size_t uplink_encode_status(const uplink_status &st, uint8_t seq, uint8_t *out, size_t cap);

// Formats `AT+MSGHEX="<hex>"` (or `AT+CMSGHEX` when `confirmed`) without the
// line ending. Returns false, with `out` empty, if `out` cannot hold it or
// `len` is 0.
bool uplink_at_command(const uint8_t *payload, size_t len, bool confirmed, char *out,
                       size_t cap);

#endif  // UPLINK_H
