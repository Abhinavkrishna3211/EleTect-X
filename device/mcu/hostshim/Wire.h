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
};

extern TwoWire Wire;
extern TwoWire Wire1;

#endif  // HOSTSHIM_WIRE_H
