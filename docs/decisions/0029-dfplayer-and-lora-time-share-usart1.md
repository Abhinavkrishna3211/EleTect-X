# ADR 0029: DFPlayer PRO and LoRa-E5 time-share USART1 through a 74HC4053

- **Status:** accepted
- **Date:** 2026-09-29
- **Supersedes:** ADR 0015 Decision A (DFPlayer on a D9/D10 software UART)
- **Amends:** ADR 0002 (the LoRa-E5's physical link)

## Context

The UNO Q's STM32 has exactly one application UART on a standard header: USART1 on D0 (PB7, RX) and
D1 (PB6, TX), which the Arduino core names `Serial1`. `Serial` is the RouterBridge monitor, `Serial2`
(LPUART1) is the Bridge link to Linux and must never be opened from the sketch, and `Serial3` (USART3,
nominally D21/D20) is not confirmed to reach the header — the official pinout shows those pads as
I2C2 only (see `hardware/references/UNO_Q_PINOUT_REFERENCE.md`).

Two modules need a UART:

- **DFPlayer PRO (DFR0768)** — driven with AT commands (`AT+VOL`, `AT+PLAYNUM`, `AT+PLAYFILE`) at
  115200. This is what lets the firmware choose the track and volume per deterrence tier, which the
  KEY pin cannot do.
- **Grove LoRa-E5** — the LoRaWAN alert path (ADR 0002), AT commands at 9600.

ADR 0015 Decision A planned the DFPlayer on a software UART on D9/D10. Zephyr has no
`SoftwareSerial`, so that was never buildable.

## Decision

Both modules share USART1 through a 74HC4053 (triple 2:1 analog switch). One select line, D4 (PA12),
routes both directions at once.

### A. Wiring

| 74HC4053 | Connects to |
|---|---|
| X (pin 14, common) | MCU TX, D1 |
| X0 (pin 12) | DFPlayer RX |
| X1 (pin 13) | LoRa-E5 RX |
| Y (pin 15, common) | MCU RX, D0 |
| Y0 (pin 2) | DFPlayer TX |
| Y1 (pin 1) | LoRa-E5 TX |
| A (pin 11) and B (pin 10), tied | D4 — LOW = DFPlayer, HIGH = LoRa-E5 |
| E̅ (pin 6), VEE (pin 7), GND (pin 8) | GND |
| VCC (pin 16) | 3.3 V, 100 nF to GND at the pin |
| C (pin 9), Z/Z0/Z1 (pins 4/5/3) | unused — tie to GND |

- **Idle levels.** A 10 kΩ pull-up to the module's own logic rail on each module's RX input, so the
  deselected module sees an idle-high line rather than a floating one it could read as a start bit.
- **Levels.** The switch runs at 3.3 V and must not see more than VCC on any channel. A module
  powered from 5 V whose TX swings to 5 V gets a divider (for example 10 kΩ / 20 kΩ) before Y0 or Y1.

### B. Arbitration: the horn always wins

Implemented in `device/mcu/src/uart_share.cpp`, called from `horn.cpp`, `fire_test.cpp` and `mac.cpp`.

1. `uart_share_acquire(owner)` is a no-op if `owner` already has the port. Otherwise it `flush()`es
   the outgoing module's last command, moves the select line, waits
   `UART_SHARE_SWITCH_SETTLE_MS` (2 ms), re-opens `Serial1` at the new owner's baud (115200 for the
   DFPlayer, 9600 for the E5 — every switch is a re-`begin()`, not just a re-route), and drops any
   bytes left in the RX buffer from the previous module.
2. **A horn fire takes the port immediately**, whatever LoRa is doing. `horn_fire_sequence()` acquires
   the DFPlayer right after the amp is enabled. There is no queueing and no waiting on the radio: a
   deterrent is never delayed by telemetry.
3. **LoRa acquires the port only in join states that talk to the E5.** `kJoined` and `kFailed` (the
   backoff wait) leave the port with the DFPlayer, which is also the boot owner, so a first fire never
   pays for a switch.
4. **An interrupted LoRa step restarts from the AT probe.** If the port was switched away while an AT
   command was outstanding, the reply went to a disconnected wire and whatever is in the buffer is
   not it. `lora_service()` notices the switch count moved and returns to `kIdle`, without charging a
   retry, so a busy horn cannot push the join into `kFailed`.

### C. Build flags

`LORA_ENABLED` defaults to 1 and `UART_SHARE_ENABLED` follows it. Setting it 0 (with `-D`, or in a
unit's gitignored `config_local.h`) builds a DFPlayer-only image: the select pin is never driven and
`uart_share_acquire(kLora)` refuses. PlatformIO runs every suite under both: `native` (shared port)
and `native_dfplayer_only`.

## Consequences

- LoRa uplink and horn playback never overlap. A horn fire mid-join costs the join one restarted
  step, not a failure. Uplinks during a live deterrence sequence wait until the sequence ends.
- Pin map: D0/D1 = switch commons, D4 = switch select, D11 = amp enable, A4/A5 = geophone (`Wire2`).
  D5, D9, D10, D20 and D21 are free.

## Checks at bring-up

1. **Re-`begin()` on `ZephyrSerial`.** The switch relies on `Serial1.begin()` reconfiguring the baud
   when called on an already-open port. Host tests prove the logic, not the Zephyr driver. Verify with
   a scope or a USB-UART on D1: 115200 → 9600 → 115200.
2. **`flush()` semantics.** It must block until the last byte has left the shift register, not just
   the software buffer, or the switch can cut the final stop bit. If the scope shows a clipped byte,
   raise `UART_SHARE_SWITCH_SETTLE_MS` or add a byte-time delay before the select write.
3. **Single baud alternative.** The E5 accepts `AT+UART=BR,115200`. Running both modules at 115200
   removes the re-`begin()` from the switch. Not adopted until the E5 is seen to keep the setting
   across a power cycle.
4. **Zephyr console on USART1.** The overlay assigns USART1 to `zephyr,console`. The linked
   application image contains none of the console path, so nothing prints there, but a bootloader
   stage was not inspected. Watch D1 across a reset.
5. **`Serial3` on D20/D21.** Those pads are free. If a loopback test (jumper D20↔D21, write and read
   on `Serial3`) passes, the E5 could have its own UART instead of sharing.

## Bring-up order

1. Fit the 74HC4053 with the pull-ups and any dividers; confirm nothing else is on D4.
2. Fire the horn alone and confirm it plays the right track at the right volume through the switch.
3. Watch D1 on a scope through one join: the baud change at each switch and no clipped bytes.
4. Fire the horn during a join and confirm the join restarts from the probe and completes afterwards.
5. OTAA join and a gateway uplink.
