// Ping bench - MCU (sketch) side of the hello-world Bridge round trip.
//
// Deliberately separate from device/mcu/src/main.cpp: this is a disposable
// App Lab app, not the real EleTect-X sketch, and registers nothing the
// real schema depends on. Exists to prove Bridge.call() works MCU -> MPU on
// this board at all - Rung 0's stock Blink LED example only proved the
// reverse direction (Python driving an MCU GPIO). See
// device/mpu/bridge/rpc.py's module docstring for why the real report_*
// functions (notify targets) are a different, still-unproven direction
// this bench does not close (docs/KNOWN_GAPS.md).
//
// UNVERIFIED against a real App Lab-generated sketch (docs/KNOWN_GAPS.md):
// the exact Bridge.call() result API - whether it returns a String
// directly, throws/blocks past BRIDGE_CALL_TIMEOUT_S on no reply, or needs
// a separate error check before reading the value. Written from
// DEVICE_DEVELOPMENT_WORKFLOW.md 3's example shape
// (`Bridge.call("name", args...)`), not a line-by-line API check. If this
// does not compile or behave as written, diff against the stock Blink LED
// example (confirmed working on this board at Rung 0) before assuming the
// Bridge itself is broken.

#include "Arduino.h"
#include "Arduino_RouterBridge.h"

namespace {

constexpr uint32_t kPingPeriodMs = 2000;
constexpr uint32_t kConsoleBaud = 115200;

uint32_t g_last_ping_ms = 0;
uint32_t g_token = 0;

}  // namespace

void setup() {
  Serial.begin(kConsoleBaud);
  Bridge.begin();
}

void loop() {
  Bridge.update();

  const uint32_t now_ms = millis();
  if (now_ms - g_last_ping_ms < kPingPeriodMs) {
    return;
  }
  g_last_ping_ms = now_ms;

  g_token++;
  Serial.print("[ping] sent token=");
  Serial.println(g_token);

  const uint32_t sent_ms = millis();
  // UNVERIFIED: return type/signature of Bridge.call() - assumed here to
  // return a String directly, matching the synchronous request/response
  // description in DEVICE_DEVELOPMENT_WORKFLOW.md 3.
  const String reply = Bridge.call("ping", String(g_token));
  const uint32_t rtt_ms = millis() - sent_ms;

  Serial.print("[ping] reply=");
  Serial.print(reply);
  Serial.print(" rtt=");
  Serial.println(rtt_ms);
}
