# EleTect X — MCU pin assignment map

Single reference table for every STM32U585 (reflex MCU) pin this project uses. Source of truth for
each row is `device/mcu/src/config.h` (assigned pins) and `hardware/references/UNO_Q_PINOUT_REFERENCE.md`
(the transcribed Arduino UNO Q pinout). **D5 (PA11) is USB_OTG_FS D− on the UNO Q** — the Arduino core
claims PA11/PA12 for the USB CDC, so `digitalWrite`/`analogWrite` on D5 is a silent no-op. The left
wing gate was moved **D5 → D3** on 31 Aug 2026 for this reason; see the `HANDOVER.md` "RESUME HERE —
31 Aug, ~14:00" checkpoint. See `hardware/eletect-x-full-system.kicad_sch` for the full wiring
diagram this table matches net-for-net.

| Arduino pin | MCU pin | `config.h` name | Drives | Wiring status |
|---|---|---|---|---|
| D0 | PB7 (USART1_RX) | `LORA_UART_RX_PIN` | Grove LoRa-E5 TX → D0 | **P** — wired 18 Aug, not yet answering AT probes |
| D1 | PB6 (USART1_TX) | `LORA_UART_TX_PIN` | Grove LoRa-E5 RX ← D1 | **P** — same as D0 |
| D2 | PB3 (TIM2_CH2) | `AUDIO_TRIGGER_PIN` | DFPlayer PRO `KEY` (active-low, direct jumper) | **U** |
| D3 | PB0 (OPAMP2 out, TIM3_CH3, PWM) | `LED_WING_LEFT_PIN` (moved from D5 on 31 Aug — D5 is USB D−) | IRLZ44N gate, left wing (mixed white+blue LEDs, real 2-wing build) | **W** — bench-confirmed 31 Aug: fired both via harness (`2`) and `drive_led` pattern 0, wing lit |
| D4 | PA12 (FDCAN1_TX, TIM1_ETR) | `HORN_AMP_ENABLE_PIN` | IRLZ44N gate, XH-M543 amp VCC-side enable (active-low) | **U** — note: PA12 is USB_OTG_FS D+, claimed by the USB CDC; horn enable pin likely needs relocating too |
| D5 | PA11 (USB_OTG_FS D−) | *unusable — do not assign* | — (was `LED_WING_LEFT_PIN`; moved to D3 on 31 Aug) | **X** — PA11 is the USB CDC D− line; `digitalWrite`/`analogWrite` here is a silent no-op |
| D6 | PB1 (TIM3_CH4, PWM) | `LED_WING_RIGHT_PIN` (renamed 30 Aug, was `LED_BLUE_PIN`) | IRLZ44N gate, right wing (mixed white+blue LEDs, real 2-wing build) | **W** — bench-confirmed 31 Aug: fired both via harness (`3`) and `drive_led` pattern 1, wing lit |
| D7 | PB2 (TIM8_CH4N) | `IR_ILLUMINATOR_PIN` | IRLZ44N (or LR7843 module) gate, IR board | **W** — bench-confirmed 31 Aug: `pulse_ir` fired; IMX462 camera-diff showed +99.5 % scene luma on a 500 ms pulse |
| D8 | PB4 (JTAG NJTRST, TIM3_CH1, PWM) | *planned* `LED_BLUE_RIGHT_PIN` | IRLZ44N gate, blue LED branch, right wing | **U**, not in `config.h` yet — PB4 is also JTAG NJTRST, verify it's free before assigning |
| D20 | PB11 (I2C2_SDA) | `GEOPHONE_I2C_SDA_PIN` | ADS1115 SDA (geophone front-end) | **W** — confirmed wired |
| D21 | PB10 (I2C2_SCL) | `GEOPHONE_I2C_SCL_PIN` | ADS1115 SCL | **W** — confirmed wired |
| PH10/PH11/PH12 | on-board RGB LED 3 | `STATUS_LED_R/G/B_PIN` | unassigned — no pre-defined meaning | unused; pin exposure unconfirmed (KNOWN_GAPS) |

**Free/unused digital pins** (available for future use, none claimed by this design): D9 (PB8,
TIM4_CH3), D10 (PB9, SPI2 SS), D11 (PB15, SPI2 MOSI), D12 (PB14, SPI2 MISO), D13 (PB13, SPI2 SCK).
Qwiic connector I2C4 (PD12/PD13) is also free, reserved per `config.h`'s own comment for a future
BME280/MPU-6050.

**INMP441 acoustic mic is not in this table.** It lives on the MPU (QRB2210) side's own
I2S/audio path per `CONTEXT.md`'s software split, not through this MCU GPIO header — no pin
assignment for it exists in `config.h` yet. Do not infer wiring for it from this document.

## Power rails (not MCU GPIO, included for completeness)

| Net | Source | Feeds |
|---|---|---|
| `BATBUS_12V8` | Battery+ → 6A blade fuse → SPST switch → WAGO 5-way splice | UNO Q VIN, TPA3116D2 XH-M543 VCC (direct), LED buck #1 in, LED buck #2 in, IR buck #3 in |
| `RAIL_5V` | UNO Q 5V pin | DFPlayer PRO VIN, Grove LoRa-E5 VCC — explicitly *not* on the 12.8V actuator bus |
| `LEDBUS_WHITE` | XL4015 buck #1 output | Documented for the never-built 4-channel/10-LED plan — **the real build shares one buck across both wings**, this row is stale, kept for history |
| `LEDBUS_BLUE` | XL4015 buck #2 output | Same as above — stale, real build uses a single shared LED buck |
| `IR_12V` | XL4015 buck #3 output, set ~12V | VISTORA 48-LED IR board (fixed 12V spec, no input tolerance margin) |

Full derivation, wire gauges, and connector choices: `hardware/WIRING_GUIDE.md` §1 and
`hardware/bom/procurement-status.md`.

*Generated 23 Aug 2026 alongside `hardware/eletect-x-full-system.kicad_sch`. Updated 31 Aug 2026:
left wing moved D5→D3 (D5 = USB D−), D3/D6/D7 wiring status confirmed W after the bench bring-up.
Keep both in sync with `config.h`; D2/D4 still to flip from U to W, and D4 (PA12 = USB D+) likely
needs relocating.*
