# Arduino UNO Q — pinout and hardware reference

Source of truth for every pin assignment in `device/mcu/src/config.h`. Extracted directly from
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

Snapshot: **31 Aug 2026.**

Legend: **W** = wired and confirmed on hardware · **P** = wiring in progress today · **U** = unwired ·
**X** = pin unusable, do not assign

| Pin(s) | MCU pin | Function | Status | Note |
|---|---|---|---|---|
| A4 / A5 | PC1 / PC0 | Geophone front-end, I2C3 (`Wire2`, ADS1115) | **W** | Corrected 29 Sept 2026 from the field board's `config.h` (`GEOPHONE_I2C_BUS Wire2`). Earlier revisions of this table put it on D20/D21 (I2C2); those pads are free. |
| D0 / D1 | PB7 / PB6 | USART1 (`Serial1`) through a 74HC4053: DFPlayer PRO (115200) and Grove LoRa-E5 (9600), both UART AT commands | **W** | Corrected 29 Sept 2026: the DFPlayer PRO is driven here and the horn has fired in two weeks of field testing. The LoRa-E5 shares the port through the 74HC4053, select on D4 (ADR 0029). The 18 Aug LoRa wiring and the `LORA_SERIAL = Serial` belief are history — see the UART inventory below. |
| D2 | PB3 | Retired DFPlayer KEY fallback (`AUDIO_TRIGGER_PIN`) | **U** | Driven idle-high at boot, not wired. Playback is UART AT commands on D0/D1. |
| D4 | PA12 | 74HC4053 select (`UART_SHARE_SELECT_PIN`): LOW = DFPlayer, HIGH = LoRa-E5 | — | Firmware in `uart_share.cpp`, host-tested under both PlatformIO envs; hardware checks in ADR 0029. Plain GPIO — the "USB D+" claim is withdrawn (see the UART inventory). The horn amp enable is on **D11 (PB15)**, not here. |
| D5 | PA11 | *free* (was LED left wing) | **U** | Free, usable, PWM-capable (TIM1_CH4). The "USB D−, silent no-op" diagnosis behind the 31 Aug move to D3 is withdrawn. |
| D3 | PB0 | LED left wing (`LED_WING_LEFT_PIN`, moved from D5) | **W** | Bench-confirmed 31 Aug 2026 — fired via the fire-test harness (`2`) and `drive_led` pattern 0 over the Bridge; wing physically lit then off. Clean PWM GPIO (TIM3_CH3). |
| D6 | PB1 | LED right wing (`LED_WING_RIGHT_PIN`) | **W** | Bench-confirmed 31 Aug 2026 — fired via the fire-test harness (`3`) and `drive_led` pattern 1 over the Bridge; wing physically lit then off. |
| D7 | PB2 | IR illuminator (`IR_ILLUMINATOR_PIN`) | **W** | Bench-confirmed 31 Aug 2026 — `pulse_ir` fired over the Bridge; IMX462 camera-diff showed +99.5 % mean scene luma during a 500 ms pulse. |
| D11 | PB15 | Horn amp enable (`HORN_AMP_ENABLE_PIN`, IRLZ44N on the XH-M543 VCC side, active-low) | **W** | From the field board's `config.h`; horn fires in field testing. |

The fire-test harness's software path (`docs/specs/mcu-fire-test-harness.md`) is verified end to end on
real firmware — see `docs/KNOWN_GAPS.md`'s 15 Aug entry. **LED wings (D3/D6) and IR (D7) are now
physically fired and confirmed (31 Aug 2026)** — see `HANDOVER.md` "RESUME HERE — 31 Aug, ~14:00".
The horn chain (DFPlayer on D0/D1, amp enable on D11) has been firing in field testing since mid-Sept.

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
| A0 (D14) | PA4 | **No** — never | DAC0 out, TIM2_CH1, ADC |
| A1 (D15) | PA5 | **No** — never | DAC1 out, TIM3_CH1, ADC |
| A2 (D16) | PA6 | Digital mode only | **OPAMP2_INPUT+**, TIM3_CH1, ADC |
| A3 (D17) | PA7 | Digital mode only | **OPAMP2_INPUT−**, TIM3_CH2, ADC |
| A4 (D18) | PC1 | Digital mode only | **I2C3_SDA**, LPTIM1_CH1, ADC |
| A5 (D19) | PC0 | Digital mode only | **I2C3_SCL**, LPTIM1_IN1, ADC |

**OPAMP2 correction, 29 Sept 2026:** this table previously put OPAMP2 INPUT+ on A3 and INPUT− on A5. Both
were one row off. The real mapping is **INPUT+ = PA6 (A2), INPUT− = PA7 (A3), OUTPUT = PB0 (~D3)** — read off
the pinout card directly and independently consistent with the datasheet's §9.6 entry giving OPAMP2_OUTPUT
on ~D3/PB0. Matters for the ADR 0009 direct-ADC geophone path if OPAMP2 is ever used as the PGA stage.

### 5V tolerance — the pinout card and the datasheet disagree; trust the datasheet

**[RESOLVED 29 Sept 2026 by reading both official documents side by side]**

Note the two documents' own dates before reading further: the **pinout card is stamped "Last update: 17 Feb
2026"**, the **datasheet "Modified: 17/07/2026"**. The datasheet is five months newer *and* more specific.
Where they conflict, it wins — which is the situation below.

The pinout card (`ABX00162-full-pinout.pdf`) carries a red warning box that says, verbatim:

> "All MCU GPIOs are 3.3 V logic and 5 V tolerant, except A0 and A1 (not 5 V tolerant)."

That is the sentence quoted in the earlier pass here, and it was quoted accurately. **It is also incomplete,
and the datasheet contradicts it in two places.** The datasheet is the more specific document — it names the
silicon I/O structure type rather than generalising — so it wins. There are **three** carve-outs, not one:

1. **A0 (PA4) and A1 (PA5) are never 5V-tolerant.** Datasheet §9.7: *"A0 (PA4) and A1 (PA5) are direct
   STM32U585 ADC inputs referenced to VREF+. They are not 5 V-tolerant... The absolute maximum at the pin is
   VDD + 0.3 V, approximately 3.6 V. Above this level, the MCU's internal protection diodes begin to
   conduct. ... Do not apply 5 V to A0 or A1."* This is the one the pinout card captures.
2. **Tolerance is a property of the pin's *mode*, not the pin.** Datasheet §9: *"Some STM32U585 pads are 5
   V-tolerant in digital mode, however when configured as ADC or any analog function (such as A0 through
   A5), they are not 5 V-tolerant and must not exceed VDD + 0.3 V."* So the moment A2–A5 are switched to ADC
   — which is exactly what we want them for — they stop being 5V-tolerant. Same paragraph: *"For A4/A5 when
   used as I2C3 (PC1/PC0), use pull-ups to 3.3 V only."*
3. **~D3 (PB0) is never 5V-tolerant, in any mode.** Datasheet §9 and again in the §9.6 JDIGITAL note: *"~D3
   (PB0) uses a TT-type I/O structure and is 3.6 V-tolerant, it is not 5 V-tolerant in any mode, including
   digital."* Every other JDIGITAL pin is FT-type and 5V-tolerant as an input. This one is invisible on the
   pinout card, which sweeps it under the blanket "all MCU GPIOs."

**Why #3 matters to us specifically:** `config.h:430` assigns **D3/PB0 as `LED_WING_LEFT_PIN`** — the single
pin on the whole digital header that cannot take 5V is the one driving a wing gate. It got there on 31 Aug
by moving off D5 (PA11 = USB D−), so the choice was made for an unrelated reason and this constraint was
never checked.

As an *output* into a logic-level MOSFET gate this is fine: PB0 drives 3.3V and the IRLZ44N switches there.
The hazard is anything that **pulls PB0 up** — a driver or buck module with a pull-up on its EN/PWM input, or
a 5V pull-up added during bench work. Through reset and early boot PB0 is high-Z, so such a pull-up sits on
the pin unopposed, above the 3.6V absolute maximum, conducting through the protection diodes. **Do not put a
pull-up above 3.3V on D3, and check the dedicated LED buck's dimming input for one before wiring it.**

**Relevance to the rest of the sensor wiring:** the geophone front-end (ADS1115+INA333 today, direct STM32
ADC via LPBAM later per ADR 0002/ADR 0009) and any electret/analog-mic ADC channel should still go on A2–A5
rather than A0/A1 — but the reason recorded earlier, *"keeps the 5V-tolerance margin available as a safety
net,"* does not survive carve-out #2. In ADC mode those pins have no margin either. The real reason to prefer
A2–A5 is simply that A0/A1 carry the DAC outputs and are worth leaving free. **Any analog front-end that
could swing above 3.3V needs a divider or buffer — on every analog pin, without exception.**

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

**Constraint not previously recorded — the two SPI headers are the same peripheral.** The pinout card's
legend states it outright: *"JSPI and JDIGITAL SPI share the SPI2 MCU peripheral (can not be used
simultaneously as SPI)."* So JSPI (PC2/PC3/PD1) and the JDIGITAL SPI pins (D13 = PB13 SCK, D12 = PB14 MISO,
~D11 = PB15 MOSI, ~D10 = PB9 SS) are **alternate pinouts of SPI2, not two independent buses.** Only one set
can be active. If an SPI peripheral is ever added, that is a single-bus budget shared with any second SPI
device, and it also means **~D10/PB9 is SPI2_SS** — relevant because `config.h` reserves that pin by name as
`DFPLAYER_UART_RX_PIN`. Also note the card's own wording: *"CIPO/COPI have previously been referred to as
MISO/MOSI"* — same signals, renamed.

The JSPI pins are FT-type: *"They are 5 V-tolerant as inputs or in open-drain, while outputs drive 3.3 V.
Add level shifting if a 5 V input threshold or 5 V bidirectional signaling is required."*

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

**JCTL**: bootloader-entry jumper, MPU-side (`GPIO_96`/VOL_UP, `GPIO_36`/VOL_DOWN), **1.8V logic only** (see
Power above). It also carries `PMIC_RESET`, `USB_BOOT` (`GPIO_95`), `VBUS_DISABLE`, and — worth naming,
because it is the **only other UART broken out to a header anywhere on this board** — `SOC_SE4_TX`
(`GPIO_12`, pin 4) and `SOC_SE4_RX` (`GPIO_13`, pin 6). The pinout card labels this pair *"Default Debugging
Shell Serial"*; the datasheet reserves it: *"SE4 UART is the system console (shell UART). It is separate from
application UARTs and should not be repurposed for user I/O. It operates in the MPU's 1.8 V I/O domain."*

So it is **not** a spare UART for a peripheral: 1.8V, MPU-side, and off-limits by Arduino's own rule. See the
UART inventory note below.

**JMISC and JMEDIA are explicitly marked by Arduino as "Advanced Section — for advanced use only and may
not be officially supported."** They are also, for us, **physically inaccessible right now**: both are
1.8V board-edge connectors at the bottom of the UNO Q meant to be broken out through a carrier board, and
we don't have one. Treat as a stretch-goal reference only, not a planning input for the current build — no
sensor/actuator in the current design should be assigned to either header:
**The contents of these two headers were swapped in the first pass here — corrected 29 Sept 2026 against
datasheet §9.1 (JMISC pin map) and §9.2 (JMEDIA pin map).** Audio is on JMISC; camera and display are on
JMEDIA. It was recorded the other way round.

- **JMISC** is the mixed-domain header: *"Mixed function header combining 3.3 V MCU signals and 1.8 V MPU
  signals."* It breaks out `MCU_PSSI_*` (parallel camera bus, MCU-side), SDMMC1 test pins, TRACE,
  `MCU_I2C4_SDA/SCL` (same bus as Qwiic), MCO/CRS_SYNC, `MCU_OPAMP1_*`, power rails (+3V3, +5V_USB, +1V8,
  VBAT, VCOIN) — and the **audio codec pins**: `MIC2_INP` / `MIC2_INM` / `MIC2_BIAS` (analog mic input, pins
  29/31/33), `EAR_P/M_R`, `LINEOUT_P/M`, `HPH_L/R/REF`, `HS_DET`.
- **JMEDIA** is *"four-lane camera and display signals in the 1.8 V domain (MIPI-CSI-2 and MIPI-DSI)"* — this
  is where the QRB2210's CSI camera interface is physically present, with no module to plug into it yet. Note
  the MIPI-DSI here is **multiplexed with the USB-C DisplayPort Alt-Mode output through the ANX7625, not
  independent**: only one display output can be active at a time.

**On MIC2 and the acoustic track:** the MIC2 input is real, and it is an analog mic input reaching Linux
through the PM4125's codec — i.e. it would appear as an ALSA capture device on the MPU with no USB dongle or
hub. That makes it worth knowing about for *bench validation* of the acoustic model. It does **not** change
ADR 0006/0009, which put the INMP441 on the STM32U585 precisely so the always-on listening cost lands on the
µA reflex layer; MIC2 is MPU-domain, and listening on it means keeping the MPU awake. Same conclusion as
before, but now for the right reason and against the right header.

**Arduino's reservation note, verbatim, worth honouring on both headers:** *"Do not use the Qualcomm
Dragonwing™ QRB2210 lines reserved for I²C, JMEDIA CCI (Camera Control Interface), or MI2S0 (I²S audio bus)
as general-purpose I/O. These signals are interface-dedicated, operate at 1.8 V, and are reserved in the
Linux device tree."*

## UART inventory — what is actually available **[CONFIRMED 29 Sept 2026 on the board: overlay + linker map]**

Collected here because it comes up repeatedly, the answer is narrower than it looks, and **the Arduino
`SerialN` numbering on this board is not what it looks like.** Everything below is read off the installed
core (`arduino:zephyr` 0.90.0) and the linked firmware image, not inferred.

**Why the numbering shifts.** The variant overlay declares `arduino,router-serial = <&lpuart1>`. In
`cores/arduino/zephyrSerial.h` that sets `ZARD_SKIP_FIRST_SERIAL`, which switches the naming macro from
`ZARD_SERIAL_STEM(i) = i` to `= i+1`. So the `serials = <&usart1>, <&lpuart1>, <&usart3>` array is **numbered
from 1, not 0**, and the bare name `Serial` is handed to the RouterBridge `Monitor` object instead. The
linker map of our own image proves it: `Serial` resolves to `0x9a2c` in **`.bss.Monitor`**, contributed by
`Arduino_RouterBridge/singletons.cpp.o` — the *same address* as `Monitor` — while `Serial1`/`Serial2`/
`Serial3` are `arduino::ZephyrSerial` objects from `core.a(zephyrSerial.cpp.o)`.

| Object | Peripheral | Where | Status |
|---|---|---|---|
| **`Serial`** | *not a UART* — RouterBridge `Monitor` | Over the internal bridge to Linux | Prints land in App Lab's Serial Monitor. **Nothing written here reaches a header pin.** |
| **`Serial1`** | **USART1** | **D0 = PB7 (RX), D1 = PB6 (TX)** on JDIGITAL, 3.3 V | The **only** confirmed application UART on a standard header. **Shared** — the DFPlayer PRO (115200) and the LoRa-E5 (9600) through a 74HC4053 (ADR 0029). |
| **`Serial2`** | **LPUART1** | Not broken out — internal trace only (`SOC_MCU_LPUART1_TX/RX/CTS/RTS`, schematic sheet 9 "UART To MCU") | The Bridge link itself, `/dev/ttyHS1` @ 115200 on the Linux side. Held by `arduino-router`; **must not be opened from app code.** |
| **`Serial3`** | **USART3** (`status = "okay"`, deferred-init, 115200) | **D21 = PB10 (TX), D20 = PB11 (RX)** | A real second hardware UART on paper. The pads are **free** — the geophone is on A4/A5 (`Wire2`), not I2C2 — but the official pinout card shows D20/D21 as I2C2 only, so whether USART3's pinctrl actually reaches them is **unverified**. A loopback test (jumper D20↔D21, write/read on `Serial3`) settles it. If it passes, LoRa gets its own UART and the 74HC4053 is unnecessary. |
| **SE4** | MPU | `SOC_SE4_TX`/`RX` on **JCTL pins 4/6**, 1.8 V | The Linux shell console. Arduino: *"should not be repurposed for user I/O."* |
| BT UART | MPU | Not broken out (`SOC_BT_UART_*` → WCBN3536A) | Dedicated to the radio module. |

**Net: one confirmed header UART, shared by the DFPlayer PRO and the LoRa-E5.** ADR 0015's *software* UART on D9/D10 for the
DFPlayer was never implemented (Zephyr has no `SoftwareSerial`), so the DFPlayer went on `Serial1` and the
LoRa-E5 time-shares it through a 74HC4053 (ADR 0029). `Serial3` on D20/D21 is the untested alternative —
the geophone does not use those pads — and a loopback test would show whether the E5 could have its own
UART.

**Two corrections this supersedes.** (1) PA11/PA12 (D5/D4) are **not** USB D−/D+ — the STM32 has no USB on
this board at all; they are FDCAN1, deferred-init, and the CAN driver is not linked. See
`hardware/PIN_MAP.md`. (2) `Serial` is **not** USART1/D0/D1. `config.h`'s `LORA_SERIAL` was pointed at
`Serial` on 18 Aug (commit `3ee3e7b`) on exactly that mistaken belief, which sends every AT command to the
Linux monitor instead of the radio — logged in `docs/KNOWN_GAPS.md` as high severity.

**Console noise on D0/D1 — checked, and it is not a problem.** The overlay keeps USART1 non-deferred with
the comment *"since it is assigned to `zephyr,console`"*, which raises the obvious worry that kernel output
collides with DFPlayer or LoRa AT traffic on the same wire. It does not: the image links **none** of the console path —
zero matches for `uart_console`, `printk`, `boot_banner`, `log_core`, `char_out` or `console_init` in
`sketch.ino.map`. Arduino-level prints go to `Serial` = `Monitor` = the bridge, a different transport
entirely. (Scope: the application image only — a bootloader stage was not inspected.)

## What this changes about current firmware planning

Nothing structurally — it sharpens two things already in progress: (1) A2–A5 are the right ADC channel
choices for the geophone/acoustic analog front-ends, not A0/A1, now confirmed rather than assumed; (2) RGB
LED 3 or 4 (MCU-owned) is the right choice for our own status signaling once that gets built, avoiding the
MPU-side LEDs' wake cost and LED 2's fixed system semantics.
