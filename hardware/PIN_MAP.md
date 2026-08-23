# EleTect X — MCU pin assignment map

Single reference table for every STM32U585 (reflex MCU) pin this project uses. Source of truth for
each row is `device/mcu/src/config.h` (assigned pins) and `hardware/references/UNO_Q_PINOUT_REFERENCE.md`
(the transcribed Arduino UNO Q pinout). D3/D8 are the two new pins from the 22 Aug 4-channel LED
redesign (`hardware/WIRING_GUIDE.md` §4.0) — confirmed free and PWM-capable, not yet added to
`config.h`. See `hardware/eletect-x-full-system.kicad_sch` for the full wiring diagram this table
matches net-for-net.

| Arduino pin | MCU pin | `config.h` name | Drives | Wiring status |
|---|---|---|---|---|
| D0 | PB7 (USART1_RX) | `LORA_UART_RX_PIN` | Grove LoRa-E5 TX → D0 | **P** — wired 18 Aug, not yet answering AT probes |
| D1 | PB6 (USART1_TX) | `LORA_UART_TX_PIN` | Grove LoRa-E5 RX ← D1 | **P** — same as D0 |
| D2 | PB3 (TIM2_CH2) | `AUDIO_TRIGGER_PIN` | DFPlayer PRO `KEY` (active-low, direct jumper) | **U** |
| D3 | PB0 (OPAMP2 out, TIM3_CH3, PWM) | *planned* `LED_WHITE_RIGHT_PIN` | IRLZ44N gate, white LED branch, right wing | **U**, not in `config.h` yet |
| D4 | PA12 (FDCAN1_TX, TIM1_ETR) | `HORN_AMP_ENABLE_PIN` | IRLZ44N gate, XH-M543 amp VCC-side enable (active-low) | **U** |
| D5 | PA11 (FDCAN1_RX, TIM1_CH4, PWM) | `LED_WHITE_PIN` → planned `LED_WHITE_LEFT_PIN` | IRLZ44N gate, white LED branch, left wing | **U** |
| D6 | PB1 (TIM3_CH4, PWM) | `LED_BLUE_PIN` → planned `LED_BLUE_LEFT_PIN` | IRLZ44N gate, blue LED branch, left wing | **U** |
| D7 | PB2 (TIM8_CH4N) | `IR_ILLUMINATOR_PIN` | IRLZ44N (or LR7843 module) gate, IR board | **U** |
| D8 | PB4 (TIM3_CH1, PWM) | *planned* `LED_BLUE_RIGHT_PIN` | IRLZ44N gate, blue LED branch, right wing | **U**, not in `config.h` yet |
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
| `LEDBUS_WHITE` | XL4015 buck #1 output | White-left + white-right LED branches (parallel) |
| `LEDBUS_BLUE` | XL4015 buck #2 output | Blue-left + blue-right LED branches (parallel) |
| `IR_12V` | XL4015 buck #3 output, set ~12V | VISTORA 48-LED IR board (fixed 12V spec, no input tolerance margin) |

Full derivation, wire gauges, and connector choices: `hardware/WIRING_GUIDE.md` §1 and
`hardware/bom/procurement-status.md`.

*Generated 23 Aug 2026 alongside `hardware/eletect-x-full-system.kicad_sch` — keep both in sync with
`config.h` as the LED 4-channel firmware lands and D2/D4/D5/D6/D7 wiring status flips from U to W.*
