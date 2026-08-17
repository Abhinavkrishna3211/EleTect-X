# Arduino UNO Q — pinout and hardware reference

Source of truth for every pin assignment in `device/mcu/include/config.h`. Extracted directly from
Arduino's own official pinout PDF and hardware page — not a third-party summary, not inferred.

**Primary sources (fetch these directly if anything below is ambiguous — the PDF is a visual diagram,
this document is a text reconstruction of it and carries residual transcription risk on a few items
flagged explicitly below):**
- Pinout (PDF): https://docs.arduino.cc/resources/pinouts/ABX00162-full-pinout.pdf (last updated 17 Feb 2026)
- Datasheet (PDF): https://docs.arduino.cc/resources/datasheets/ABX00162-ABX00173-datasheet.pdf
- Schematics (PDF): https://docs.arduino.cc/resources/schematics/ABX00162-schematics.pdf
- Hardware page: https://docs.arduino.cc/hardware/uno-q
- STM32U585 datasheet (ST, for AF tables beyond what's needed here): https://www.st.com/resource/en/datasheet/stm32u585ai.pdf

**Confidence note:** the original pass extracted this from the PDF's raw text layer via automated fetch,
which mis-ordered a few peripheral-function annotations (fixed 29 Jul 2026 after reading the actual
uploaded PDF/datasheet directly — see the corrections marked below). Every section is now either
**[HIGH CONFIDENCE]** (unambiguous from the start) or **[CONFIRMED]** (corrected against the real PDF).
No remaining `[VERIFY VISUALLY]` items.

## Wiring status — physical board, live tracker

This section tracks what is actually soldered/jumpered to the real board right now, as distinct from
the pin *assignments* in the tables below (which are just what `config.h` claims a pin is for). Same
discipline as `hardware/bom/procurement-status.md` tracking real-world part status separately from
`bom.md`'s static spec — **update this table directly as wiring changes; don't let it go stale.**

Snapshot: **18 Aug 2026.**

Legend: **W** = wired and confirmed on hardware · **P** = wiring in progress today · **U** = unwired

| Pin(s) | MCU pin | Function | Status | Note |
|---|---|---|---|---|
| D20 / D21 | PB11 / PB10 | Geophone front-end, I2C2 (ADS1115 bench stand-in) | **W** | Confirmed wired. |
| D0 / D1 | PB7 / PB6 | Grove LoRa-E5, USART1 | **P** | Physically wired 18 Aug (Yellow=module TX→D0, White=module RX→D1, Red=VCC→5V, Black=GND→GND). `LORA_SERIAL` confirmed to be `Serial` (not `Serial1`) via the board's own devicetree overlay + live `journalctl -u arduino-router` cross-check — `config.h` updated. Left at **P**, not **W**: live join test over the correct wire got zero response bytes from the module across 6 AT-probe retries — see `docs/KNOWN_GAPS.md`'s 18 Aug entry for the full capture and candidate causes (logic-level mismatch at 5V power vs 3.3V MCU TX, or module not in AT-command mode). Needs physical follow-up before this flips to **W**. |
| D2 | PB3 | Audio trigger — DFPlayer IO/ADKEY | **U** | Not wired. Last confirmed unwired 15 Aug (`docs/KNOWN_GAPS.md` fire-test-harness entry, confirmed with Abhinav); re-confirmed still unwired 18 Aug. |
| D4 | PA12 | Horn amp enable — TPA3116D2 shutdown | **U** | Not wired. Same 15/18 Aug confirmation as D2. |
| D5 | PA11 | LED white | **U** | Not wired. Same 15/18 Aug confirmation as D2. |
| D6 | PB1 | LED blue | **U** | Not wired. Same 15/18 Aug confirmation as D2. |
| D7 | PB2 | IR illuminator | **U** | Not wired. Same 15/18 Aug confirmation as D2. |

The fire-test harness's software path (`docs/specs/mcu-fire-test-harness.md`) is already verified end to
end on real firmware — see `docs/KNOWN_GAPS.md`'s 15 Aug entry — but physical activation of horn/LED/IR
cannot be confirmed until D2/D4/D5/D6/D7 above move to **W**. Re-run that checklist, this time
watching/listening for each fire, once they are.

## Top-level architecture

Two independent processors, one board, one USB-C port:
- **STM32U585** (MCU, "reflex" side, our code lives here for the always-on layer) — Cortex-M33 @ 160MHz,
  2MB flash, 786KB SRAM, FPU, runs Arduino sketches on Zephyr RTOS. 3.3V logic domain.
- **QRB2210** (MPU, "cognition" side) — quad-core Cortex-A53 @ 2.0GHz, Adreno GPU, dual ISP, runs Debian
  Linux. 1.8V logic domain internally, but the exposed advanced-header pins in its section are noted where
  relevant.
- **PM4125** — power management IC.
- **WCBN3536A** — WiFi 5 (2.4/5GHz) + Bluetooth 5.1 radio module.
- **ANX7625** — present on the MPU side (display/USB-C alt-mode bridge; not relevant to our sensor/actuator
  work, noted for completeness).

## Power **[HIGH CONFIDENCE]**

- **VIN**: +7–24 VDC input.
- **+5V USB**: available when powered via USB-C.
- **+3V3, +1V8**: regulated rails present on multiple headers (see JMEDIA/JMISC below for the 1.8V domain
  specifically).
- **JCTL (bootloader entry) pins are 1.8V logic only** — do not drive 3.3V into them. Confirms the existing
  "JCTL jumper for bootloader mode" note elsewhere in the docs, adds the voltage-level warning that wasn't
  previously captured.

## Digital pins D0–D13, D20–D21 **[CONFIRMED 29 Jul 2026 against the real PDF, not text-reconstructed]**

Pin identity (D21=PB10 … D0=PB7) was already correct. The peripheral-function annotations below were
wrong in the first pass (shifted ~2 rows during text reconstruction) — corrected here after reading the
actual uploaded PDF directly:

| Arduino pin | MCU pin | Notes |
|---|---|---|
| D21 | PB10 | I2C2 SCL (default) |
| D20 | PB11 | I2C2 SDA (default) |
| D13 | PB13 | SPI2 SCK (default) |
| D12 | PB14 | SPI2 MISO/CIPO (default) |
| ~D11 | PB15 | SPI2 MOSI/COPI (default); PWM-capable |
| ~D10 | PB9 | SPI2 SS (default); PWM-capable |
| ~D9 | PB8 | TIM4_CH3; PWM-capable — **no CAN here** (corrected) |
| D8 | PB4 | TIM3_CH1 — **no CAN here** (corrected) |
| D7 | PB2 | TIM8_CH4N — **no OPAMP2 here** (corrected) |
| ~D6 | PB1 | TIM3_CH4; PWM-capable — **no UART here** (corrected) |
| ~D5 | PA11 | **FDCAN1_RX**, TIM1_CH4; PWM-capable (corrected — CAN is here, not D8/D9) |
| D4 | PA12 | **FDCAN1_TX**, TIM1_ETR (corrected — CAN is here, not D8/D9) |
| ~D3 | PB0 | **OPAMP2 OUTPUT**, TIM3_CH3; PWM-capable (corrected — OPAMP2 is here, not D7) |
| D2 | PB3 | TIM2_CH2 |
| D1 | PB6 | **USART1_TX**, TIM4_CH1 (corrected — UART is here, not D6) |
| D0 | PB7 | **USART1_RX**, TIM4_CH2 (corrected — UART is here, not D5) |

`~` prefix (as printed on the pinout) marks PWM/timer-capable pins. **Net effect of the correction: CAN
(FDCAN1) is on D4/D5, not D8/D9; OPAMP2 output is on D3, not D7; UART (USART1) is on D0/D1, not D5/D6.**
None of our current sensor/actuator assignments (geophone/acoustic on A2–A5, horn/LED/IR on GPIO, LoRa on
UART) had been locked against the wrong version yet, so this correction has no rework cost — it landed
before `config.h` was written, not after.

## Analog pins A0–A5 **[HIGH CONFIDENCE]**

| Arduino pin | MCU pin | 5V-tolerant? | Other functions |
|---|---|---|---|
| A0 (D14) | PA4 | **No** | DAC0 output |
| A1 (D15) | PA5 | **No** | DAC1 output |
| A2 (D16) | PA6 | Yes | — |
| A3 (D17) | PA7 | Yes | OPAMP2 INPUT+ |
| A4 (D18) | PC1 | Yes | — |
| A5 (D19) | PC0 | Yes | OPAMP2 INPUT− |

**Official warning, verbatim: "All MCU GPIOs are 3.3V logic and 5V tolerant, except A0 and A1 (not 5V
tolerant)."** This applies board-wide, not just to the analog header — every digital pin in the table above
is also 5V-tolerant on input. Only A0/A1 are the exception. This corrects the earlier, broader "6 analog
inputs not 5V-tolerant" claim that had been in `DEVICE_DEVELOPMENT_WORKFLOW.md` §1.

**Relevance to our own sensor wiring:** the geophone front-end (ADS1115+INA333 today, direct STM32 ADC via
LPBAM later per ADR 0002/ADR 0009) and any electret/analog-mic ADC channel should be assigned to A2–A5
(PA6, PA7, PC1, or PC0) where possible, not A0/A1 — keeps the 5V-tolerance margin available as a safety net
against an unexpectedly hot sensor rail, even though our nominal signal levels are already within 3.3V.

## Qwiic / STEMMA QT connector **[HIGH CONFIDENCE]**

4-pin JST-SH, 3.3V I2C only:

| Pin | Signal | MCU pin |
|---|---|---|
| 1 | GND | — |
| 2 | +3V3 | — |
| 3 | SDA | PD13 (I2C4_SDA) |
| 4 | SCL | PD12 (I2C4_SCL) |

Matches prior research exactly — no change. This is the connector for BME280, MPU-6050, and any other
I2C breakout in the BOM.

**No Qwiic/JST-SH cable in hand — use the standard header instead, not a blocker.** The digital pin table
above already exposes a second, independent I2C bus on ordinary 0.1" header pins: **D21 = PB10 (I2C2 SCL),
D20 = PB11 (I2C2 SDA)**, both default-mapped, no jumper/config needed to enable them. Any breakout with a
plain pin header (ADS1115, INA333 module) wires there directly with standard male-female jumper wires —
SDA→D20, SCL→D21, plus VCC(3.3V)/GND from any of those rails on the board. This is I2C2, a different bus
from Qwiic's I2C4, but electrically and functionally equivalent for our purposes; `config.h` should target
I2C2/D20/D21 for the ADS1115 bench stand-in rather than assuming a Qwiic connection.

## 6-pin SPI header **[CONFIRMED 29 Jul 2026 against the real PDF and cross-checked in the datasheet text]**

MISO = PC2 (pin 1), SCK = PD1 (pin 3), MOSI = PC3 (pin 4); pins 2/5/6 are +5V/RESET/GND. Not currently
needed for any sensor in the BOM (Grove LoRa-E5 uses UART/AT commands, not SPI).

## RGB LEDs **[HIGH CONFIDENCE]**

Four RGB LEDs total, split across both processors — relevant for status signaling (CONTEXT.md's
"boot/trigger/LoRa-join/battery-low status" diagnostic use):

| LED | Owner | R / G / B pins | Pre-assigned meaning |
|---|---|---|---|
| RGB LED 1 | MPU | GPIO_41 / GPIO_42 / GPIO_60 | user / user / user (general purpose) |
| RGB LED 2 | MPU | GPIO_39 / GPIO_40 / GPIO_47 | panic / wlan / bt (system status, semantically fixed) |
| RGB LED 3 | MCU | PH10 / PH11 / PH12 | general purpose |
| RGB LED 4 | MCU | PH13 / PH14 / PH15 | general purpose |

**For our own status signaling (boot/trigger/LoRa-join/battery-low), use RGB LED 3 or 4 (MCU-owned,
unassigned)** — LED 1/2 are on the MPU (extra wake cost to drive from the reflex layer) and LED 2 already
has fixed system-status semantics (panic/wlan/bt) we shouldn't repurpose.

## LED matrix **[HIGH CONFIDENCE]**

8×13 (104-LED) matrix, individually addressed. Confirms the existing "free UI/diagnostic hardware" note —
no new information beyond confirming the exact 8×13/104-LED count.

## USB-C connector, JCTL, and advanced headers (JMISC, JMEDIA)

USB-C carries standard power/data plus board-internal signals (`VBUS_DISABLE`, `PMIC_RESET`, `USB_BOOT`,
`SOC_SE4_RX/TX`) — not something we wire to directly, noted for completeness only.

**JCTL**: bootloader-entry jumper, MPU-side (`GPIO_96`, `GPIO_36`), **1.8V logic only** (see Power above).

**JMISC and JMEDIA are explicitly marked by Arduino as "Advanced Section — for advanced use only and may
not be officially supported."** They are also, for us, **physically inaccessible right now**: both are
1.8V board-edge connectors at the bottom of the UNO Q meant to be broken out through a carrier board, and
we don't have one. Treat as a stretch-goal reference only, not a planning input for the current build — no
sensor/actuator in the current design should be assigned to either header:
- **JMISC** breaks out `MCU_PSSI_*` (parallel synchronous slave interface — camera-adjacent), MCU trace/
  debug pins, `MCU_I2C4_SDA/SCL` (same bus as Qwiic), `MCU_OPAMP1_*`, and — the notable one — **CSI0/CSI1
  MIPI camera lanes plus CCI camera-control I2C**, confirming the QRB2210's CSI camera interface is
  physically present on this board, just with no module to plug into it yet (see §1 correction above).
- **JMEDIA** breaks out audio-codec pins on the MPU side: `MIC2_INP/INM/BIAS` (a second analog mic input,
  MPU-domain), `EAR_P/M_R`, `LINEOUT_P/M`, `HPH_L/R`, `HS_DET` (headphone/headset jack signals), plus
  `SOC_GPIO_98–101`. The MIC2 input is real but lives on the MPU's codec, not the MCU/ADC domain ADR 0009
  needs — noted for completeness, doesn't change that design.

## What this changes about current firmware planning

Nothing structurally — it sharpens two things already in progress: (1) A2–A5 are the right ADC channel
choices for the geophone/acoustic analog front-ends, not A0/A1, now confirmed rather than assumed; (2) RGB
LED 3 or 4 (MCU-owned) is the right choice for our own status signaling once that gets built, avoiding the
MPU-side LEDs' wake cost and LED 2's fixed system semantics.
