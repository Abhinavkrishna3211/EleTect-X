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
// Event (type 2), 12 bytes:
//   2  event class (uplink_event_class)
//   3  confidence, 0-100 %
//   4  deterrence tier, 0 = none, 1-3
//   5  flags (UPLINK_EVENT_FLAG_*)
//   6-9 capture_ref
//   10-11 age, s: how long this frame waited between being queued and being
//        put on the air; UPLINK_AGE_UNKNOWN when the node cannot say
//
// age is the one field the encoder does not write, because it is not known
// until the frame is actually sent. uplink_encode_event() leaves it
// UPLINK_AGE_UNKNOWN and mac.cpp stamps it in start_send(), so a frame that
// sat out a horn fire, two send retries or a join backoff reports the wait it
// really had rather than a wait measured at encode time, which is always
// zero.
//
// Why it exists: without it the server has nothing but its own receive time,
// so a frame delayed by minutes is filed as having just happened. An alert
// that is half an hour stale then sorts above a fresh one, and the operator
// has no way to tell. The node has no RTC and no synchronised clock, so it
// cannot report an absolute time - but elapsed time needs no synchronisation
// and is exactly what the server is missing.
//
// It also means a re-sent frame is no longer byte-identical to its first
// attempt, which amends ADR 0031 B. The server's duplicate check excludes
// these two bytes for that reason (web/ingest/src/payload.ts,
// frameIdentityBytes) - the rest of the frame still identifies the event, and
// age describes the transmission, not the event.
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

#define UPLINK_EVENT_LEN 12
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

// Age the node could not determine, and the clamp for anything that would not
// fit. 0xFFFE is a real 18-hour age; nothing the queue can hold comes close,
// so saturating there rather than wrapping keeps a stuck frame honest.
#define UPLINK_AGE_UNKNOWN 0xFFFFu
#define UPLINK_AGE_MAX 0xFFFEu

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

// Stamps the age field of an already-encoded event frame, immediately before
// it goes on the air. `age_s` is clamped to UPLINK_AGE_MAX. Returns false, and
// changes nothing, for anything that is not a full-length event frame - a
// status frame has no age field, and neither does a short one.
bool uplink_set_event_age(uint8_t *frame, size_t len, uint32_t age_s);

// Formats `AT+MSGHEX="<hex>"` (or `AT+CMSGHEX` when `confirmed`) without the
// line ending. Returns false, with `out` empty, if `out` cannot hold it or
// `len` is 0.
bool uplink_at_command(const uint8_t *payload, size_t len, bool confirmed, char *out,
                       size_t cap);

#endif  // UPLINK_H
