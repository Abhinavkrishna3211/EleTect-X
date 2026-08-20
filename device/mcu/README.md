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
  `scripts/sync-to-board.sh`, which one-directionally mirrors `src/` (config.h and secrets.h
  included — see the Layout section below on why they live in `src/`, not a separate `include/`)
  into the board's App folder as `sketch/`. Never hand-edit the board's copy — edit here, re-run
  the sync script, then build/flash from App Lab.

## Wiring — bench stand-in (ADS1115 + INA333)

The field geophone (SM-24) and its INA333 instrumentation amp connect to an ADS1115 breakout
today, standing in for the STM32's own internal ADC (ADR 0009 swaps this out via LPBAM once that
Rung lands). Plain jumper wires, not Qwiic — I2C2 is an independent bus from the Qwiic connector's
I2C4.

Pin names below match the actual silkscreen on the two breakout boards in use (INA333: `WCMCU-333`;
ADS1115: `HW-198`) — not the generic IC datasheet pin names, so this table can be followed directly
without translating labels at the bench.

**ADS1115 (`HW-198`) side:**

| Signal | ADS1115 pin (silkscreen) | UNO Q pin | MCU pin |
| --- | --- | --- | --- |
| SDA | `SDA` | D20 | PB11 (I2C2_SDA) |
| SCL | `SCL` | D21 | PB10 (I2C2_SCL) |
| Power | `VDD` | 3V3 | — |
| Ground | `GND` | GND | — |
| Address select | `ADDR` | GND | — (fixes I2C address at `0x48`) |
| Differential input+ | `A0` | — | INA333 `VOUT` |
| Differential input− | `A1` | — | INA333 `UREF` |

**INA333 (`WCMCU-333`) side:**

| Signal | INA333 pin (silkscreen) | Connects to |
| --- | --- | --- |
| Output | `VOUT` | ADS1115 `A0` |
| Reference | `UREF` | ADS1115 `A1` (same function as the datasheet's `REF` pin) |
| Power | `VCC` | 3V3 rail — use this pin, not the board's separate `3.3V` label (see note below) |
| Ground | `GND` | GND rail (either of the board's two `GND` pins) |
| Non-inverting input | `VIN+` | 1 kΩ series resistor → damping-resistor node → geophone lead |
| Inverting input | `VIN-` | 1 kΩ series resistor → damping-resistor node → geophone other lead |

**Unconfirmed:** this board breaks out both `VCC` and a separately labeled `3.3V` pin (also two `GND`
pins, one per edge). Most likely these are the same power/ground nets mirrored on both edges of the
board for breadboard convenience, not two distinct functions — but this is not verified against a
datasheet for this specific clone board. Wire `VCC` (the standard supply-pin name) to 3V3 and leave
the separate `3.3V` pin unconnected; only investigate further if the amp doesn't power up.

Geophone signal path: SM-24 → (1 kΩ damping resistor) → 1 kΩ series resistors → INA333 `VIN+`/
`VIN-` → INA333 → ADS1115 `A0`/`A1` differential pair, rejecting the INA333's bias rail (`UREF`)
rather than reading it as signal.

**Input protection — 1 kΩ in series with each INA333 input.** Between the damping-resistor node and
the INA333's `VIN+`/`VIN-` pins, add a 1 kΩ resistor in each leg. Negligible effect on the signal
(the INA333's input impedance is high enough that this forms an RC corner far above the 2-50 Hz
seismic band), but gives the amp's internal ESD structures some current limiting against a transient
on the buried cable run. Same 1 kΩ value as the damping resistor, already in the kit. This is a
cheap partial mitigation, not a substitute for the still-open TVS/clamp item in
`docs/KNOWN_GAPS.md` — see ADR 0001's 30 Jul addendum.

**Damping resistor — required, not optional.** The SM-24's open-circuit damping is h=0.25
(datasheet), badly underdamped at its 10 Hz resonance: an unshunted coil rings for several cycles
after every footfall, smearing the STA/LTA envelope the trigger detector reads. Wire a **1 kΩ
resistor directly across the SM-24's own two leads**, before the burial cable (not at the INA333
end — cable resistance would otherwise shift the delivered damping away from this calculation).
1 kΩ gives h≈0.69, matching one of the datasheet's own plotted response curves, using
`R_shunt = RtBcfn / (fn × (h_target − h_open)) − Rc` with the SM-24's own
`RtBcfn=6000 Ω·Hz, fn=10 Hz, Rc=375 Ω` against a target h≈0.7. Any resistor from the existing kit
works — tolerance isn't critical here. See ADR 0001 addendum for the full derivation.

**INA333 REF-bias check — do this before wiring the rest.** The geophone's output is a true AC
signal (swings both positive and negative). If the INA333's `UREF` pin is tied to GND instead of a
mid-supply bias (~VCC/2), the negative half of every waveform clips at the rail. Short `VIN+` to
`VIN-`, then run the check: set `GEOPHONE_DEBUG_SINGLE_ENDED_AIN0` to `1` in `src/config.h`,
sync, flash, and read the `[bias-check] raw=<int> volts=<float>` lines the board prints — ~1.65V
on a 3.3V rail means `UREF` is biased correctly and the wiring below is safe to use as-is; a
reading near 0V means it isn't, and needs an external fix before proceeding. Read the console via
**App Lab's own Serial Monitor (in a browser)** — `arduino-app-cli monitor` over SSH does not
deliver serial data on this board; see ADR 0010's 2026-07-30 addendum. Set the flag back to
`0` and re-sync before moving on — it must never read `1` on a node headed for the field
(`src/config.h`'s own bench-only-flags section says the same). Also check this board's `RG`
gain-setting pads (unlabeled in the photo reference for this specific board — look for a small
unpopulated 2-pad footprint near the INA333 chip itself, not on the main 8-pin header) — ~1 kΩ
gives a reasonable starting gain (G≈101) if bare.

**Result (2026-07-30):** `[bias-check] raw≈26890 volts≈1.6806V`, stable across multiple readings —
`UREF` is correctly mid-supply biased and the wiring above is safe to use as-is.

**Seismic waveform capture (Part C2 sensitivity pass).** Separate from the REF-bias check above:
set `SEISMIC_DEBUG_VERBOSE` to `1` to get a periodic `[seismic]` sta/lta/ratio line plus a
`[window]` CSV volts dump on every `[trigger]` event, then render the dumps with
`python scripts/plot_seismic_window.py <saved-console-log> --out-dir <dir>`. Same flag discipline
as above — back to `0` and re-sync once the capture session is done.

**Live seismic plot (pitch/demo tool, not the Part C2 pass above).** Set both
`SEISMIC_DEBUG_STREAM_RAW` and `SEISMIC_DEBUG_VERBOSE` to `1`, sync, flash, then run
`python scripts/live_seismic_plot.py --port <COM port>` (or `--file <log>` / `-` for stdin,
depending on which console transport is reachable — see the script's own docstring; only App
Lab's browser Serial Monitor is confirmed to deliver bytes at all, per ADR 0010's 2026-07-30
addendum) for a live two-panel view: raw geophone volts on top, STA/LTA ratio with the
`STA_LTA_TRIGGER_RATIO` (4.0) line on the bottom. The bottom panel does not advance for
`EVENT_MAX_MS` + `COOLDOWN_MS` (about 35 s today) after a trigger, since `[seismic]` only
prints while the state machine is in `kSensing` — time a recording around that gap rather than
expecting a continuous trace across an event. Same flag discipline as above — both flags back
to `0` and re-sync once the recording session is done.

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

Requires `src/secrets.h` to exist locally first (copy `src/secrets.h.example`, fill in the
real per-device OTAA DevEUI/AppEUI/AppKey — never commit this file, it's gitignored).

## Bench stomp test (Rung 1 exit criterion)

Run this after wiring the table above and syncing/flashing. **Set `SEISMIC_TRIGGER_CONSOLE_LOG` to
`1` in `src/config.h` first** — it defaults to `0` (`Serial` is shared with the E5 LoRa module now
that `LORA_SERIAL` is `Serial`; see `docs/KNOWN_GAPS.md`'s 18 Aug entry), so the `[trigger]` line
below stays silent unless this flag is on. Same discipline as `SEISMIC_DEBUG_VERBOSE`/
`SEISMIC_DEBUG_STREAM_RAW` above — flip it back to `0` and re-sync once the bench pass is done, it
must never read `1` on a node headed for the field.

1. Power the board and open App Lab's own Serial Monitor in a browser — `arduino-app-cli monitor`
   over SSH does not deliver serial data on this board (ADR 0010's 2026-07-30 addendum).
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

**Status: done, 2026-08-14.** Run against real hardware on a lean field-flag build
(`SEISMIC_DEBUG_VERBOSE` temporarily set to 1 for the pass to get quantified quiet-floor
numbers alongside the trigger, then reverted to 0 immediately after). Quiet floor held a
ratio of 1.03–1.13 across ~89 s (before and after the stomp, no false triggers); a firm
stomp near the geophone produced `ratio=4.60`, with the `[window]` CSV dump confirming a
real ~65x amplitude transient over the noise floor. `STA_LTA_TRIGGER_RATIO` (4.0) clears
the observed floor ceiling by ~3.5x and the stomp clears the threshold by ~15% — see
`docs/KNOWN_GAPS.md`'s 2026-08-14 entry for the full write-up. `STA_LTA_DETRIGGER_RATIO`
was never validated this way and was removed 2026-08-15 as dead code — `kEvent` only ever
exits on `EVENT_MAX_MS` elapsed, never a ratio; see `docs/KNOWN_GAPS.md`'s 2026-08-15 entry.

**Multi-trial follow-up: done, 2026-08-15.** 12 stomps at 60 s intervals against the same
lean-flag-toggle build; 11/12 detected (mean trigger ratio 4.232, stdev 0.166), one genuine
sub-threshold miss (peak ratio 3.80) explained rather than dismissed, zero false triggers
across a 688-sample quiet baseline (mean ratio 1.149). MPU-side `report_footfall_event` fired
for all 11/11 triggers with matching `sta_lta_ratio` and `fused_P` 0.979–0.986 — confirmed via
the board's raw Docker json-log (`docker logs` itself fails on this container with a stream
corruption error; see `docs/KNOWN_GAPS.md`'s 2026-08-15 multi-trial entry for the workaround
and full statistics).

## Layout

```text
src/                        flat - no subfolders (see rationale below)
  sketch.ino               required by arduino-cli's naming convention only - empty otherwise
  sketch.yaml              required by arduino-app-cli - board profile, not repo-specific
  config.h                 pin map + tuning constants
  secrets.h / secrets.h.example   per-device OTAA credentials (secrets.h gitignored)
  main.cpp                 setup()/loop() shell
  state_machine.{h,cpp}    idle -> sensing -> event -> cooldown
  geophone.{h,cpp}         read_seismic_window() over the ADS1115 stand-in
  sta_lta.{h,cpp}          pure STA/LTA core, zero hardware calls
  rule_gate.{h,cpp}        pure clamp/cooldown core, shared by horn/led/ir
  horn.{h,cpp}             owns AUDIO_TRIGGER_PIN + HORN_AMP_ENABLE_PIN
  led.{h,cpp}              white/blue deterrent LED pods
  ir.{h,cpp}               940nm illuminator for night-vision capture
  mac.{h,cpp}              Grove E5 AT-command OTAA join (IN865 only)
hostshim/        HOST BUILD ONLY - never synced to the board (ADR 0010)
tests/           Unity known-answer suites (pure cores only)
```

`src/` is deliberately flat — no `sensors/`/`actuators/`/`footfall/`/`lora/` subfolders, and
`config.h`/`secrets.h` live directly in it rather than a separate `include/`. This is load-bearing,
not stylistic (ADR 0010's addendum has the full story): `arduino-cli`'s sketch build only compiles
`.cpp` files that are direct children of the sketch root, and only puts the sketch root itself on
the include search path — subfolder `.cpp` files are silently skipped (the build reports zero
errors, then fails at the link step), and a subfolder file's bare `#include "config.h"` only ever
worked by accident under PlatformIO's now-removed `-I include` flag. App Lab's build has no
equivalent fallback for either case. Every file in `src/` therefore sits at the same depth and uses
a plain `#include "whatever.h"` — no relative `../` paths anywhere in this tree.

`sketch.ino` is a separate, unrelated requirement from the same tool: `arduino-cli` refuses to
compile a sketch at all unless it contains a file named exactly `<sketch-folder-name>.ino` — on the
board that folder is always `sketch/` (see `scripts/sync-to-board.sh`), so this file must be named
`sketch.ino` regardless of this repo's own directory name. It carries no logic; `setup()`/`loop()`
are ordinary functions in `main.cpp`, which the merged sketch links against normally. Do not delete
it — a manual `rm -rf` of the board's `sketch/` folder without this file present breaks the build
with `main file missing from sketch`, and it will not be restored by re-running
`scripts/sync-to-board.sh` unless it exists here in the repo first.

`sketch.yaml` is the same story from `arduino-app-cli` rather than `arduino-cli`: `app start`
refuses to run at all without it present (`sketch folder is incomplete: both sketch.ino and
sketch.yaml are required`), and it carries no repo-specific content — just the `arduino:zephyr`
platform profile every App Lab sketch uses. Like `sketch.ino`, it belongs here rather than only on
the board for the same `rsync --delete` reason.
