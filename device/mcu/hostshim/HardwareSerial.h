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

  // Host-side inspection hooks for the USART1 share (uart_share.cpp): the
  // baud of the most recent begin(), and how many begin() calls there have
  // been, so a test can see the port re-opened at the right rate on a switch.
  unsigned long host_baud() const { return baud_; }
  size_t host_begin_count() const { return begin_count_; }
  void host_reset_begin_count() { begin_count_ = 0; }

  // Host-side inspection hook: everything written since the last
  // host_reset_tx(), NUL-terminated, so a test can assert on the exact AT
  // command a driver sent. Stops recording (silently) once full.
  const char *host_tx() const { return tx_; }
  void host_reset_tx() {
    tx_len_ = 0;
    tx_[0] = '\0';
  }

 private:
  static constexpr size_t kRxCapacity = 512;
  char rx_[kRxCapacity] = {};
  size_t rx_head_ = 0;
  size_t rx_tail_ = 0;
  size_t bytes_written_ = 0;
  unsigned long baud_ = 0;
  size_t begin_count_ = 0;
  static constexpr size_t kTxCapacity = 1024;
  char tx_[kTxCapacity] = {};
  size_t tx_len_ = 0;
};

extern HardwareSerial Serial;
extern HardwareSerial Serial1;

#endif  // HOSTSHIM_HARDWARESERIAL_H
