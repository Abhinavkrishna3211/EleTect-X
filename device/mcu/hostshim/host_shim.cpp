// HOST BUILD ONLY - see hostshim/Arduino.h.

#include "Arduino.h"

#include <chrono>
#include <cstdio>
#include <cstring>

#include "Arduino_RouterBridge.h"
#include "Wire.h"

namespace {

constexpr int kMaxPins = 128;
int g_pin_state[kMaxPins] = {};
unsigned long g_millis_offset = 0;

unsigned long steady_millis() {
  using namespace std::chrono;
  static const auto start = steady_clock::now();
  return static_cast<unsigned long>(
      duration_cast<milliseconds>(steady_clock::now() - start).count());
}

}  // namespace

void pinMode(int, int) {}

void digitalWrite(int pin, int value) {
  if (pin >= 0 && pin < kMaxPins) {
    g_pin_state[pin] = value;
  }
}

int digitalRead(int pin) {
  return (pin >= 0 && pin < kMaxPins) ? g_pin_state[pin] : LOW;
}

void analogWrite(int pin, int value) {
  if (pin >= 0 && pin < kMaxPins) {
    g_pin_state[pin] = value;
  }
}

int analogRead(int) { return 0; }

unsigned long millis() { return steady_millis() + g_millis_offset; }

unsigned long micros() { return millis() * 1000UL; }

void delay(unsigned long ms) { g_millis_offset += ms; }

void delayMicroseconds(unsigned int us) { g_millis_offset += us / 1000UL; }

namespace hostshim {

int pin_state(int pin) { return digitalRead(pin); }

void advance_millis(unsigned long ms) { g_millis_offset += ms; }

void reset() {
  std::memset(g_pin_state, 0, sizeof(g_pin_state));
  g_millis_offset = 0;
}

}  // namespace hostshim

size_t Print::write(const uint8_t *buffer, size_t size) {
  size_t written = 0;
  for (size_t i = 0; i < size; ++i) {
    written += write(buffer[i]);
  }
  return written;
}

size_t Print::print(const char *value) {
  return write(reinterpret_cast<const uint8_t *>(value), std::strlen(value));
}

size_t Print::print(char value) { return write(static_cast<uint8_t>(value)); }

size_t Print::print(int value) { return print(static_cast<long>(value)); }

size_t Print::print(unsigned int value) {
  return print(static_cast<unsigned long>(value));
}

size_t Print::print(long value) {
  char buffer[32];
  std::snprintf(buffer, sizeof(buffer), "%ld", value);
  return print(buffer);
}

size_t Print::print(unsigned long value) {
  char buffer[32];
  std::snprintf(buffer, sizeof(buffer), "%lu", value);
  return print(buffer);
}

size_t Print::print(double value, int digits) {
  char buffer[64];
  std::snprintf(buffer, sizeof(buffer), "%.*f", digits, value);
  return print(buffer);
}

size_t Print::println() { return print("\n"); }

size_t Print::println(const char *value) { return print(value) + println(); }

size_t Print::println(char value) { return print(value) + println(); }

size_t Print::println(int value) { return print(value) + println(); }

size_t Print::println(unsigned int value) { return print(value) + println(); }

size_t Print::println(long value) { return print(value) + println(); }

size_t Print::println(unsigned long value) { return print(value) + println(); }

size_t Print::println(double value, int digits) {
  return print(value, digits) + println();
}

void HardwareSerial::begin(unsigned long) {}

void HardwareSerial::end() {}

size_t HardwareSerial::write(uint8_t value) {
  std::fputc(static_cast<int>(value), stdout);
  ++bytes_written_;
  return 1;
}

int HardwareSerial::available() {
  return static_cast<int>(rx_head_ - rx_tail_);
}

int HardwareSerial::read() {
  if (rx_tail_ >= rx_head_) {
    return -1;
  }
  return static_cast<unsigned char>(rx_[rx_tail_++ % kRxCapacity]);
}

int HardwareSerial::peek() {
  if (rx_tail_ >= rx_head_) {
    return -1;
  }
  return static_cast<unsigned char>(rx_[rx_tail_ % kRxCapacity]);
}

void HardwareSerial::flush() { std::fflush(stdout); }

void HardwareSerial::host_feed(const char *bytes) {
  for (const char *p = bytes; *p != '\0'; ++p) {
    rx_[rx_head_++ % kRxCapacity] = *p;
  }
}

HardwareSerial Serial;
HardwareSerial Serial1;

void TwoWire::begin() {}

void TwoWire::setClock(uint32_t) {}

void TwoWire::beginTransmission(uint8_t) {}

size_t TwoWire::write(uint8_t) { return 1; }

size_t TwoWire::write(const uint8_t *, size_t size) { return size; }

uint8_t TwoWire::endTransmission() { return 0; }

uint8_t TwoWire::endTransmission(bool) { return 0; }

uint8_t TwoWire::requestFrom(uint8_t, uint8_t quantity) { return quantity; }

int TwoWire::available() { return static_cast<int>(queue_head_ - queue_tail_); }

int TwoWire::read() {
  if (queue_tail_ >= queue_head_) {
    return 0;  // preserves the original always-0 default when nothing fed.
  }
  return queue_[queue_tail_++ % kQueueCapacity];
}

void TwoWire::host_feed_raw(int16_t raw_value) {
  const uint16_t bits = static_cast<uint16_t>(raw_value);
  queue_[queue_head_++ % kQueueCapacity] = static_cast<uint8_t>(bits >> 8);
  queue_[queue_head_++ % kQueueCapacity] = static_cast<uint8_t>(bits & 0xFF);
}

TwoWire Wire;
TwoWire Wire1;

void BridgeClass::begin() {}

void BridgeClass::update() {}

BridgeClass Bridge;

#ifndef PIO_UNIT_TESTING
// The firmware's entry points are setup()/loop(), which the Arduino Core
// calls on the board. This main() exists only so pio run -e native proves
// the whole src/ tree links and runs against the stub peripherals without
// crashing - the resulting binary is not a runnable node, does no real
// sensing, and is never flashed (see platformio.ini's header banner).
extern void setup();
extern void loop();

int main() {
  std::printf(
      "eletect-mcu host compile check - firmware entry points are "
      "setup()/loop(), built on the board by App Lab.\n");

  setup();
  constexpr int kSmokeIterations = 600;
  for (int i = 0; i < kSmokeIterations; ++i) {
    loop();
  }

  std::printf("host smoke run completed %d loop() iterations without crashing.\n",
              kSmokeIterations);
  return 0;
}
#endif
