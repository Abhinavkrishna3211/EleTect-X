// HOST BUILD ONLY - see hostshim/Arduino.h.
//
// No-op stand-in for the real Arduino_RouterBridge.h's `Bridge` object. The
// real Bridge talks to the on-board `arduino-router` daemon over a Unix
// socket (docs/DEVICE_DEVELOPMENT_WORKFLOW.md 3) - there is nothing for a
// host build to connect to, so every method here is a no-op that exists only
// to satisfy the compiler and let src/ link on a development machine.
//
// Covers begin()/update() (already called from main.cpp, gated behind
// SEISMIC_DEBUG_STREAM_RAW) and notify() (already called from
// geophone.cpp), plus provide() - nothing calls provide() yet, but
// docs/KNOWN_GAPS.md's Bridge-registration entries name it as the next
// hardware-session task, so it is added now rather than reopening this same
// "host build breaks the moment a bench flag pulls in this header" gap the
// first time provide() lands. Same discipline as Arduino.h: add a symbol
// only once firmware genuinely needs it, and match the real call shape (a
// name string plus forwarded args), not a real implementation - there is
// nothing behind this stub to actually deliver a message to.

#ifndef HOSTSHIM_ARDUINO_ROUTERBRIDGE_H
#define HOSTSHIM_ARDUINO_ROUTERBRIDGE_H

class BridgeClass {
 public:
  void begin();
  void update();

  // Fire-and-forget on real hardware (never blocks on a reply); a no-op here
  // is a faithful stand-in for that contract, not just a shortcut.
  template <typename... Args>
  void notify(const char *, const Args &...) {}

  // Registers a named handler on real hardware; nothing to register it with
  // on a host build, so the handler is accepted and discarded.
  template <typename Func>
  void provide(const char *, Func) {}
};

extern BridgeClass Bridge;

#endif  // HOSTSHIM_ARDUINO_ROUTERBRIDGE_H
