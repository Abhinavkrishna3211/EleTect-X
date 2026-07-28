// HOST BUILD ONLY - never compiled into firmware, never synced to the board.
//
// A minimal stand-in for the subset of the Arduino API this firmware actually
// uses, so `pio run` and `pio test` can compile the whole src/ tree on a
// development machine. On the board, the real Arduino Core headers are used
// instead and this directory does not exist.
//
// Keep this file honest: add a symbol here only when firmware genuinely needs
// it, and match the real signature. A shim that drifts from the real API turns
// a green host build into a false negative.

#ifndef HOSTSHIM_ARDUINO_H
#define HOSTSHIM_ARDUINO_H

#include <cstddef>
#include <cstdint>

#define HIGH 1
#define LOW 0
#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2

#define DEC 10
#define HEX 16

void pinMode(int pin, int mode);
void digitalWrite(int pin, int value);
int digitalRead(int pin);
void analogWrite(int pin, int value);
int analogRead(int pin);

unsigned long millis();
unsigned long micros();
void delay(unsigned long ms);
void delayMicroseconds(unsigned int us);

// Host-side inspection hooks. Firmware never calls these; they exist so a
// future host test can assert on pin state without a board attached.
namespace hostshim {
int pin_state(int pin);
void advance_millis(unsigned long ms);
void reset();
}  // namespace hostshim

class Print {
 public:
  virtual ~Print() = default;
  virtual size_t write(uint8_t value) = 0;
  virtual size_t write(const uint8_t *buffer, size_t size);

  size_t print(const char *value);
  size_t print(char value);
  size_t print(int value);
  size_t print(unsigned int value);
  size_t print(long value);
  size_t print(unsigned long value);
  size_t print(double value, int digits = 2);

  size_t println();
  size_t println(const char *value);
  size_t println(char value);
  size_t println(int value);
  size_t println(unsigned int value);
  size_t println(long value);
  size_t println(unsigned long value);
  size_t println(double value, int digits = 2);
};

class Stream : public Print {
 public:
  virtual int available() = 0;
  virtual int read() = 0;
  virtual int peek() = 0;
};

#include "HardwareSerial.h"

#endif  // HOSTSHIM_ARDUINO_H
