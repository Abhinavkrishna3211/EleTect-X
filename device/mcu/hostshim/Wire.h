// HOST BUILD ONLY - see hostshim/Arduino.h.
//
// Stands in for the Arduino TwoWire API used by sensors/geophone.cpp. Reads
// return 0 and endTransmission() reports success, so the host build exercises
// the driver's control flow and signatures, not its I2C behaviour - that is
// only ever validated on the bench against a real ADS1115.

#ifndef HOSTSHIM_WIRE_H
#define HOSTSHIM_WIRE_H

#include <cstddef>
#include <cstdint>

class TwoWire {
 public:
  void begin();
  void setClock(uint32_t frequency);

  void beginTransmission(uint8_t address);
  size_t write(uint8_t value);
  size_t write(const uint8_t *buffer, size_t size);

  // Matches the Arduino contract: 0 on success, non-zero on error.
  uint8_t endTransmission();
  uint8_t endTransmission(bool send_stop);

  uint8_t requestFrom(uint8_t address, uint8_t quantity);
  int available();
  int read();

  // Host-side inspection hook: queues an ADS1115 conversion register value
  // (big-endian, matching geophone.cpp's ads1115_read_conversion()) so the
  // next two read() calls return it instead of the default 0/0. Lets a
  // future test drive a real waveform through geophone.cpp instead of the
  // constant-zero stub below. Firmware never calls this.
  void host_feed_raw(int16_t raw_value);

 private:
  static constexpr size_t kQueueCapacity = 4096;
  uint8_t queue_[kQueueCapacity] = {};
  size_t queue_head_ = 0;
  size_t queue_tail_ = 0;
};

extern TwoWire Wire;
extern TwoWire Wire1;

#endif  // HOSTSHIM_WIRE_H
