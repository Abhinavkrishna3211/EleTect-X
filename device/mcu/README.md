# MCU — STM32U585 (real-time reflex)

Arduino Core on Zephyr, C/C++. Geophone ADC+STA/LTA+**seismic TinyML**, **acoustic anti-poaching
(Edge Impulse, gunshot/chainsaw)**, actuator timing (horn/LED/IR), LoRa MAC, power, safety
rule-gates, watchdog. On-device models live in `lib/` (Edge Impulse SDK export).

## Two build paths — read this before touching either

- **`pio run -e native` / `pio test -e native`** — host-only compile/test harness (ADR 0010).
  Proves the whole `src/` tree builds and links against a small Arduino API shim
  (`hostshim/`), and runs the Unity known-answer tests on the pure cores (`sta_lta.cpp`,
  `rule_gate.cpp`). **This never produces a flashable image.** `hostshim/` is never synced to the
  board.
- **App Lab (or the Arduino App CLI over SSH)** — the only path onto real hardware. Fed by
  `scripts/sync-to-board.sh`, which one-directionally mirrors `src/` and `include/config.h` +
  `include/secrets.h` into the board's App folder. Never hand-edit the board's copy — edit here,
  re-run the sync script, then build/flash from App Lab.

## Wiring — bench stand-in (ADS1115 + INA333)

The field geophone (SM-24) and its INA333 instrumentation amp connect to an ADS1115 breakout
today, standing in for the STM32's own internal ADC (ADR 0009 swaps this out via LPBAM once that
Rung lands). Plain jumper wires, not Qwiic — I2C2 is an independent bus from the Qwiic connector's
I2C4.

| Signal | ADS1115 pin | UNO Q pin | MCU pin |
| --- | --- | --- | --- |
| SDA | SDA | D20 | PB11 (I2C2_SDA) |
| SCL | SCL | D21 | PB10 (I2C2_SCL) |
| VCC | VDD | 3V3 | — |
| GND | GND | GND | — |
| Address select | ADDR | GND | — (fixes I2C address at `0x48`) |
| Differential input+ | AIN0 | — | INA333 `OUT` |
| Differential input− | AIN1 | — | INA333 `REF` |

Geophone signal path: SM-24 → INA333 (gain per its own datasheet resistor) → ADS1115 AIN0/AIN1
differential pair, rejecting the INA333's bias rail rather than reading it as signal.

**Damping resistor — required, not optional.** The SM-24's open-circuit damping is h=0.25
(datasheet), badly underdamped at its 10 Hz resonance: an unshunted coil rings for several cycles
after every footfall, smearing the STA/LTA envelope the trigger detector reads. Wire a **1 kΩ
resistor directly across the SM-24's own two leads**, before the burial cable (not at the INA333
end — cable resistance would otherwise shift the delivered damping away from this calculation).
1 kΩ gives h≈0.69, matching one of the datasheet's own plotted response curves, using
`R_shunt = RtBcfn / (fn × (h_target − h_open)) − Rc` with the SM-24's own
`RtBcfn=6000 Ω·Hz, fn=10 Hz, Rc=375 Ω` against a target h≈0.7. Any resistor from the existing kit
works — tolerance isn't critical here. See ADR 0001 addendum for the full derivation.

**Known open item (`docs/KNOWN_GAPS.md`):** whether `Wire` or `Wire1` is actually the Arduino Core
mapping for I2C2 (D20/D21) on this board has not been confirmed on hardware. `config.h` defaults to
`Wire`. If the geophone never reads (`geophone_ok()` stays false, or `report_system_status`'s
`geophone_ok` field never sets), try `Wire1` first.

## Build / test

```powershell
cd device\mcu
pio test -e native      # both Unity suites: test_sta_lta, test_rule_gate
pio run -e native       # whole src/ tree compiles + links against the host shim
```

## Sync to board

```bash
# from the repo root, once the board is reachable over SSH (Network Mode)
scripts/sync-to-board.sh
```

Requires `include/secrets.h` to exist locally first (copy `include/secrets.h.example`, fill in the
real per-device OTAA DevEUI/AppEUI/AppKey — never commit this file, it's gitignored).

## Bench stomp test (Rung 1 exit criterion)

Run this after wiring the table above and syncing/flashing:

1. Power the board, open the App Lab console (or `ssh` in and tail the sketch's stdout).
2. Let it idle ~30 s and confirm a quiet baseline: repeated STA/LTA sensing with no
   `[trigger]` lines, and (if logging is added later) a ratio staying comfortably under
   `STA_LTA_TRIGGER_RATIO` (4.0).
3. Stomp near the SM-24 geophone, firmly, a few times in a row.
4. Expect one line per crossing, in this exact format (emitted by `state_machine.cpp`):

   ```text
   [trigger] t=<ms> sta=<f> lta=<f> ratio=<f> idx=<n>
   ```

   `t` is `millis()` at detection, `sta`/`lta` are the mean-absolute-value short/long window
   values, `ratio` is `sta/lta`, `idx` is the sample index inside the window where the ratio
   peaked.
5. A failed sensor read looks like `geophone_ok()` reporting false (surfaced later via
   `report_system_status`) and an all-zero window — not a crash, per the schema's
   zero-fill-on-timeout contract. If every window reads as flat zero, check the `Wire`/`Wire1`
   question above before assuming the geophone itself is at fault.

**Status: pending hardware.** This procedure has not yet been run against real hardware — see
`docs/KNOWN_GAPS.md`.

## Layout

```text
include/         config.h (pin map + tuning constants), secrets.h.example
src/
  main.cpp                 setup()/loop() shell
  state_machine.{h,cpp}    idle -> sensing -> event -> cooldown
  sensors/geophone.{h,cpp} read_seismic_window() over the ADS1115 stand-in
  footfall/sta_lta.{h,cpp} pure STA/LTA core, zero hardware calls
  actuators/
    rule_gate.{h,cpp}      pure clamp/cooldown core, shared by horn/led/ir
    horn.{h,cpp}            owns AUDIO_TRIGGER_PIN + HORN_AMP_ENABLE_PIN
    led.{h,cpp}             white/blue deterrent LED pods
    ir.{h,cpp}              940nm illuminator for night-vision capture
  lora/mac.{h,cpp}          Grove E5 AT-command OTAA join (IN865 only)
hostshim/        HOST BUILD ONLY - never synced to the board (ADR 0010)
tests/           Unity known-answer suites (pure cores only)
```
