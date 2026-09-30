#include "uplink.h"

#include <cstring>

namespace {

uint8_t header(uint8_t type) {
  return static_cast<uint8_t>((UPLINK_FORMAT_VERSION << 4) | (type & 0x0F));
}

void put_u16(uint8_t *out, uint16_t v) {
  out[0] = static_cast<uint8_t>(v >> 8);
  out[1] = static_cast<uint8_t>(v);
}

void put_u32(uint8_t *out, uint32_t v) {
  out[0] = static_cast<uint8_t>(v >> 24);
  out[1] = static_cast<uint8_t>(v >> 16);
  out[2] = static_cast<uint8_t>(v >> 8);
  out[3] = static_cast<uint8_t>(v);
}

uint8_t confidence_pct(float confidence) {
  // NaN fails both comparisons and lands on 0.
  if (!(confidence > 0.0f)) return 0;
  if (confidence >= 1.0f) return 100;
  return static_cast<uint8_t>(confidence * 100.0f + 0.5f);
}

}  // namespace

size_t uplink_encode_event(const uplink_event &ev, uint8_t seq, uint8_t *out, size_t cap) {
  if (out == nullptr || cap < UPLINK_EVENT_LEN) return 0;
  out[0] = header(UPLINK_TYPE_EVENT);
  out[1] = seq;
  out[2] = ev.event_class <= UPLINK_EVENT_CLASS_MAX
               ? ev.event_class
               : static_cast<uint8_t>(uplink_event_class::kUnconfirmed);
  out[3] = confidence_pct(ev.confidence);
  out[4] = ev.tier > 3 ? 3 : ev.tier;
  out[5] = ev.flags;
  put_u32(&out[6], ev.capture_ref);
  return UPLINK_EVENT_LEN;
}

size_t uplink_encode_status(const uplink_status &st, uint8_t seq, uint8_t *out, size_t cap) {
  if (out == nullptr || cap < UPLINK_STATUS_LEN) return 0;
  out[0] = header(UPLINK_TYPE_STATUS);
  out[1] = seq;
  out[2] = st.flags;
  put_u16(&out[3], st.battery_mv);
  put_u32(&out[5], st.uptime_s);
  return UPLINK_STATUS_LEN;
}

bool uplink_at_command(const uint8_t *payload, size_t len, bool confirmed, char *out,
                       size_t cap) {
  if (out == nullptr || cap == 0) return false;
  out[0] = '\0';
  if (payload == nullptr || len == 0) return false;

  const char *prefix = confirmed ? "AT+CMSGHEX=\"" : "AT+MSGHEX=\"";
  const size_t prefix_len = std::strlen(prefix);
  // prefix + two hex digits per byte + closing quote + NUL
  if (prefix_len + 2 * len + 2 > cap) return false;

  static const char kHex[] = "0123456789ABCDEF";
  std::memcpy(out, prefix, prefix_len);
  size_t pos = prefix_len;
  for (size_t i = 0; i < len; ++i) {
    out[pos++] = kHex[payload[i] >> 4];
    out[pos++] = kHex[payload[i] & 0x0F];
  }
  out[pos++] = '"';
  out[pos] = '\0';
  return true;
}
