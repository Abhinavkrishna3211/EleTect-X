// HOST BUILD ONLY - see hostshim/Arduino.h.

#ifndef HOSTSHIM_HARDWARESERIAL_H
#define HOSTSHIM_HARDWARESERIAL_H

#include <cstddef>
#include <cstdint>

class HardwareSerial : public Stream {
 public:
  void begin(unsigned long baud);
  void end();

  size_t write(uint8_t value) override;
  using Print::write;

  int available() override;
  int read() override;
  int peek() override;
  void flush();

  explicit operator bool() const { return true; }

  // Host-side hook: preload bytes the firmware will then read back, so a
  // future test can drive the LoRa AT parser without a radio attached.
  void host_feed(const char *bytes);

  // Host-side inspection hook: total bytes written since the last reset, so
  // a test can assert a gated console print (SEISMIC_TRIGGER_CONSOLE_LOG,
  // config.h) genuinely emitted nothing, not just that no test happened to
  // check its output.
  size_t host_bytes_written() const { return bytes_written_; }
  void host_reset_bytes_written() { bytes_written_ = 0; }

 private:
  static constexpr size_t kRxCapacity = 512;
  char rx_[kRxCapacity] = {};
  size_t rx_head_ = 0;
  size_t rx_tail_ = 0;
  size_t bytes_written_ = 0;
};

extern HardwareSerial Serial;
extern HardwareSerial Serial1;

#endif  // HOSTSHIM_HARDWARESERIAL_H
