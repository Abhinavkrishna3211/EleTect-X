# EleTect X — MCU pin assignment map

Single reference table for every STM32U585 (reflex MCU) pin this project uses. Source of truth for
each row is `device/mcu/src/config.h` (assigned pins) and `hardware/references/UNO_Q_PINOUT_REFERENCE.md`
(the transcribed Arduino UNO Q pinout). See `hardware/eletect-x-full-system.kicad_sch` for the full
wiring diagram this table matches net-for-net.

> **Correction, 29 Sept 2026 — "PA11/PA12 are USB D−/D+" was wrong, and it is withdrawn.** This header
> previously stated that the Arduino core claims PA11/PA12 for a USB CDC, making `digitalWrite` on D5 a
> silent no-op; that was the stated reason for the 31 Aug D5→D3 wing move. **The STM32 on the UNO Q has no
> USB at all**, confirmed three independent ways on the board itself:
>
> 1. **Devicetree** — the variant overlay
>    (`.../zephyr/0.90.0/variants/arduino_uno_q_stm32u585xx/*.overlay`) contains no USB/OTG/UDC node of any
>    kind, and declares **both** pins as ordinary GPIO in `zephyr,user { digital-pin-gpios }`:
>    `<&gpioa 12 ...> /* D4 - PA12 */` and `<&gpioa 11 ...> /* D5 - PA11 */`.
> 2. **Kconfig** — the variant `.conf` has no `CONFIG_USB_*`, no CDC, no ACM.
> 3. **Schematic** — there is no `USB_DM`/`USB_DP` pair on the MCU anywhere in `ABX00162-schematics.pdf`;
>    PA11 and PA12 carry plain `MCU_PA11`/`MCU_PA12` nets straight to the header. The board's USB-C belongs
>    to the QRB2210 MPU (via the ANX7625), not to the STM32.
>
> The only peripheral that claims PA11/PA12 is **FDCAN1** (`pinctrl-0 = <&fdcan1_rx_pa11 &fdcan1_tx_pa12>`),
> and it is marked `zephyr,deferred-init` — one of 16 deferred devices, the same mechanism that keeps SPI2
> and I2C2 off their pins until `.begin()`. Pinctrl is applied at device init, so it never runs unless the
> sketch opens CAN. Our image does not: **zero** `fdcan`/`can_stm32` symbols appear in
> `sketch.ino.map`. **D4 and D5 are therefore plain, usable GPIO**, and D5 is additionally PWM-capable
> (`<&pwm1 4 ...> /* D5/PA11 → TIM1_CH4 */`); D4 is not in the `pwms` list, matching the absence of a `~`
> on the silkscreen.
>
> Core `arduino:zephyr` **0.90.0 is the only version ever installed** on this board (28 Jul 2026), so this
> was already true on 31 Aug. **The 31 Aug diagnosis was wrong when it was made, and the real cause of that
> wing failure is still unknown.** No action is required — D3 works and is bench-confirmed — but note the
> move landed the wing on the one digital pin that is *not* 5 V tolerant (below). If a wing gate ever needs
> relocating, **D5 is free, usable and PWM-capable.**

**Voltage caveat on D3, added 29 Sept 2026.** `~D3 (PB0)` is the one pin on the digital header that is
**not 5 V tolerant** — it uses a TT-type I/O structure with a 3.6 V absolute maximum, *"not 5 V-tolerant in
any mode, including digital"* (UNO Q datasheet §9 and §9.6). The pinout card's blanket warning — *"all MCU
GPIOs are 3.3 V logic and 5 V tolerant, except A0 and A1"* — misses this; the datasheet is newer and more
specific, so it governs. See `hardware/references/UNO_Q_PINOUT_REFERENCE.md` §"5V tolerance".

This landed on us by accident: D3 was chosen on 31 Aug only because D5 was unusable, so the constraint was
never checked. **Checked now, and D3 is safe as wired** — `hardware/pcb/led-ir-actuators.kicad_sch` puts a
270 R series gate resistor and a **10 k pulldown to GND** on the net, with no pull-up anywhere, and the
XL4015 bucks are fixed-output with no MCU-driven enable. The pulldown covers the high-Z reset/boot window.
**The rule still binds anything added later:** never put a pull-up above 3.3 V on D3.
Also: the analog pins **lose their 5 V tolerance whenever they are configured as ADC or analog**, so A2–A5
are not a safety margin either — any front-end that can swing above 3.3 V needs a divider or buffer.

| Arduino pin | MCU pin | `config.h` name | Drives | Wiring status |
|---|---|---|---|---|
| D0 | PB7 (USART1_RX) — `Serial1` | `LORA_UART_RX_PIN` (name kept; the port is `DFPLAYER_SERIAL` = `LORA_SERIAL` = `UART_SHARE_SERIAL`) | 74HC4053 Y common: Y0 ← DFPlayer PRO TX, Y1 ← LoRa-E5 TX | **W** — the field board's horn has fired over this port for two weeks of field testing (ADR 0029) |
| D1 | PB6 (USART1_TX) — `Serial1` | `LORA_UART_TX_PIN` (same note as D0) | 74HC4053 X common: X0 → DFPlayer PRO RX, X1 → LoRa-E5 RX | **W** — same as D0 |
| D2 | PB3 (TIM2_CH2) | `AUDIO_TRIGGER_PIN` | retired KEY-pin fallback — driven idle-high at boot, not wired to the DFPlayer; playback is UART AT commands on D0/D1 | **free in practice** — only an idle-high output |
| D3 | PB0 (OPAMP2 out, TIM3_CH3, PWM) — **TT-type I/O, 3.6 V max, NOT 5 V tolerant in any mode** | `LED_WING_LEFT_PIN` (moved from D5 on 31 Aug on a diagnosis since withdrawn — see header) | IRLZ44N gate, left wing (mixed white+blue LEDs, real 2-wing build) | **W** — bench-confirmed 31 Aug: fired both via harness (`2`) and `drive_led` pattern 0, wing lit |
| D4 | PA12 (FDCAN1_TX — deferred-init, CAN not linked; no PWM channel) | `UART_SHARE_SELECT_PIN` | 74HC4053 select (A and B, pins 11/10, tied together): LOW = DFPlayer, HIGH = LoRa-E5 | firmware in `uart_share.cpp`, host-tested under both PlatformIO envs; hardware checks in ADR 0029. Was `HORN_AMP_ENABLE_PIN` in older repo trees; the amp enable is D11 |
| D5 | PA11 (FDCAN1_RX — deferred-init, CAN not linked; **PWM via TIM1_CH4**) | *free* | — (was `LED_WING_LEFT_PIN`; moved to D3 on 31 Aug) | **free and usable** — the "USB D−, silent no-op" claim is withdrawn (see header). Declared in `digital-pin-gpios` *and* in `pwms`. Only avoid if CAN is ever adopted |
| D6 | PB1 (TIM3_CH4, PWM) | `LED_WING_RIGHT_PIN` (renamed 30 Aug, was `LED_BLUE_PIN`) | IRLZ44N gate, right wing (mixed white+blue LEDs, real 2-wing build) | **W** — bench-confirmed 31 Aug: fired both via harness (`3`) and `drive_led` pattern 1, wing lit |
| D7 | PB2 (TIM8_CH4N) | `IR_ILLUMINATOR_PIN` | IRLZ44N (or LR7843 module) gate, IR board | **W** — bench-confirmed 31 Aug: `pulse_ir` fired; IMX462 camera-diff showed +99.5 % scene luma on a 500 ms pulse |
| D8 | PB4 (JTAG NJTRST, TIM3_CH1, PWM) | *planned* `LED_BLUE_RIGHT_PIN` | IRLZ44N gate, blue LED branch, right wing | **U**, not in `config.h` yet — PB4 is also JTAG NJTRST, verify it's free before assigning |
| D9 | PB8 (TIM4_CH3) | *free* | — (the D9/D10 DFPlayer software-UART plan is withdrawn; the defines were removed) | **free** |
| D10 | PB9 (SPI2 SS) | *free* | — (same as D9) | **free** |
| D11 | PB15 (SPI2 MOSI) | `HORN_AMP_ENABLE_PIN` | IRLZ44N gate, XH-M543 amp VCC-side enable (active-low) | **W** — the field board's `config.h` uses D11, matching the gate-driver schematic note; horn fires in field testing |
| D20 | PB11 (I2C2_SDA) | *free* | — (the geophone ADS1115 is on A4/A5, `Wire2`; older docs put it here) | **free** |
| D21 | PB10 (I2C2_SCL) | *free* | — (same as D20) | **free** |
| A4 | PC1 (I2C3 SDA) | `GEOPHONE_I2C_BUS` = `Wire2` | ADS1115 SDA (geophone front-end) | **W** — the field board reads the geophone over `Wire2` |
| A5 | PC0 (I2C3 SCL) | `GEOPHONE_I2C_BUS` = `Wire2` | ADS1115 SCL | **W** — same as A4 |
| PH10/PH11/PH12 | on-board RGB LED 3 | `STATUS_LED_R/G/B_PIN` | unassigned — no pre-defined meaning | unused; pin exposure unconfirmed (KNOWN_GAPS) |

**Free/unused digital pins** (available for future use, none claimed by this design): D5 (PA11,
PWM), D9 (PB8), D10 (PB9), D12 (PB14, SPI2 MISO), D13 (PB13, SPI2 SCK), D20 (PB11), D21 (PB10).
D2 is driven idle-high at boot as a retired KEY fallback; free it in `horn.cpp` before reusing it.

**D0/D1 is the only header UART, and the DFPlayer PRO and LoRa-E5 share it.** `Serial` on this board is the
RouterBridge Monitor (no header pin), `Serial1` is USART1 on D0/D1, `Serial2` is the Bridge itself
and `Serial3` has no confirmed pins. Both modules talk UART AT commands (DFPlayer PRO at 115200,
LoRa-E5 at 9600), so they time-share USART1 through a 74HC4053 on D0/D1 with D4 as the select
line; the horn always wins the port — firmware in
`device/mcu/src/uart_share.cpp`, wiring and arbitration in
`docs/decisions/0029-dfplayer-and-lora-time-share-usart1.md`. The switch runs at 3.3 V, so a
DFPlayer TX that swings to 5 V needs a divider before the 4053; put a 10 k pull-up on each module's
RX so the deselected line idles high.
Qwiic connector I2C4 (PD12/PD13) is also free, reserved per `config.h`'s own comment for a future
BME280/MPU-6050.

**INMP441 acoustic mic is not in this table, and as of ADR 0028 it is not going into it.**

[ADR 0028](../docs/decisions/0028-acoustic-capture-moves-to-the-mpu-usb-microphone.md) (accepted
2026-09-29) moved acoustic capture off this MCU entirely, to a **USB microphone on the MPU**. No
STM32 pin assignment is needed, and none should be added on the strength of the analysis below.

The reason is worth stating precisely, because it is not the one this section used to give. The
obstacle was never pin contention. The UNO Q runs a **prebuilt loader whose devicetree is fixed
before the sketch exists**, and that devicetree has no `sai1_a` node — so SAI1 is never clocked, and
a peripheral that is never clocked cannot be reached by relocating it to different pins.
[ADR 0006](../docs/decisions/0006-acoustic-gunshot-gate-and-classifier-split.md)'s finding that
SAI1 is TrustZone-locked only for the devicetree path, not for raw register access, was **correct**
and is retained — it simply is not the binding constraint.

The pin analysis is kept below because it stays accurate for the deferred always-on path, which
would use an **analog** mic on an ADC channel rather than I2S, and therefore needs none of these
three pins.

The public STM32U585 reference implementation ADR 0006 reviewed drives SAI1_A over GPIO AF13 on
**PB9, PB10 and PC1**:

| Reference pin | Already used for | Status here |
|---|---|---|
| PB9 | nothing (D10) | free |
| PB10 | nothing (D21) | free — the geophone is on A4/A5, not D20/D21 |
| PC1 | I2C3/`Wire2` SDA (A4) on the geophone front-end | routed on `hardware/pcb/geophone-frontend.kicad_sch` |

Two of the three were free all along; only PC1 would have cost a PCB revision. That is a smaller
obstacle than this section once implied, and it was never the one that mattered.

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
left wing moved D5→D3, D3/D6/D7 wiring status confirmed W after the bench bring-up. Keep both in sync
with `config.h`; D2/D4 still to flip from U to W. Updated 29 Sept 2026 against the official Arduino
datasheet and pinout card plus the board's own devicetree, Kconfig and linker map: the "PA11/PA12 are
USB" claim **withdrawn** (D4/D5 are ordinary GPIO — see header), D3/PB0
3.6 V limit recorded above; D9/D10 clarified as name-only reservations (see below and
`docs/KNOWN_GAPS.md`).*

*Updated 29 Sept 2026 (late) against the field board's own `config.h`, which is the source of truth
for what is wired: DFPlayer on D0/D1 over `Serial1`, amp enable on D11, geophone on A4/A5 (`Wire2`),
D4 as the 74HC4053 select for the shared USART1, D9/D10/D20/D21 freed (ADR 0029).*
