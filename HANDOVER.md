# EleTect X — Handover (last updated 15 Aug 2026, night — multi-trial stomp validation closed on real hardware; fire-test harness software path verified on real hardware, physical actuators not yet wired)

This file exists so work can continue with zero lost context if the planning session moves to a
different Claude account/session. Read this file, then `CONTEXT.md`, before doing anything else.
Nothing here should contradict `CONTEXT.md` — if it does, `CONTEXT.md` wins and this file is stale.

## Reading order for a fresh session

1. `CONTEXT.md` — frozen architecture, mission, deadlines. Read in full, it's short by design.
2. This file — current state, what's done, what's not, what to do next.
3. `docs/decisions/` — only the ADRs relevant to whatever you're about to touch (see "ADR trail" below).
4. `docs/KNOWN_GAPS.md` — the maintained list of unverified/placeholder items, organized by build call.
5. `hardware/bom/procurement-status.md` — live procurement tracker. Trust this over `bom.md`.

## Goal, in priority order (per CONTEXT.md §2, reconfirmed 15 Aug)

1. **Win Arduino Physical AI Challenge India 2026** — submit ≤ 23 Aug.
2. **Win Hackster "Invent the Future with UNO Q"** — submit ≤ 30 Aug.
3. Field-deploy with Kerala Forest Department (Kothamangalam DFO approved), Aug 20, 10-day trial,
   capture real footage — this doubles as evidence for both contest submissions.
4. Scientifically rigorous, reliable, low-power, manufacturable, scalable product — not just a demo.

The Aug 20 field deployment and the two contest submissions are not separate tracks — the field
footage and real deployment story are the strongest material for both write-ups. Prioritize whatever
unblocks Aug 20 first; the contest submissions are largely a documentation/write-up pass on top of
what the field test produces (see `edge-impulse-hackster-writeup` skill when that pass starts).

## Where the project actually stands (15 Aug 2026)

**Completeness ranking:** `web/frontend` > `web/backend` / `web/ingest` (all essentially done) >>
`device/mcu` (real, in bench-validation) > `device/mpu` (fusion math built, integration loop missing)
>> `ml/` (still empty — `.gitkeep` placeholders only in acoustic/datasets/evaluation/seismic/vision).

- **`web/frontend`, `web/backend`, `web/ingest`** — built and real. Supabase schema + RLS + edge
  functions + migrations exist, MQTT→Supabase ingest bridge exists, full React PWA (public site +
  auth + ranger dashboard) exists with tests. Per `CLAUDE.md`'s deployment bar, production auth still
  needs a real transactional email provider before residents sign up with real contact info — check
  whether that's landed before treating auth as field-ready.
- **`device/mcu`** — real, flat `src/` layout (ADR 0010). Geophone STA/LTA, rule gate, state machine,
  horn/LED/IR drivers, LoRa AT (`mac.cpp`) all have code. **This evening's session (14 Aug, after this
  doc's last version) added a lot — read `docs/KNOWN_GAPS.md` in full, it's the accurate record, this
  bullet is just a pointer:**
  - `src/fire_test.h`/`.cpp` — manual serial-command fire-test harness (`docs/specs/mcu-fire-test-harness.md`),
    host-built and host-tested, gated behind `FIRE_TEST_HARNESS` (default 0). **Software path run on
    real hardware, 15 Aug:** flashed with the flag on, all four commands (`1`/`2`/`3`/`4`) produced the
    correct full `[firetest]` ack, and pressing `1` twice inside 30 s correctly refused the second
    attempt (`allowed=0`, cooldown gate working). **Physical activation not confirmed — horn, LED, and
    IR are not wired to the board yet**, so this only proves the command-parse/rule-gate/ack-print
    path, not that any actuator actually switches on. Flag reverted to `0` and re-flashed before ending
    the session, console confirmed silent. Re-run once wiring exists, watching/listening this time —
    see `docs/KNOWN_GAPS.md`'s fire-test-harness entry for the full detail.
  - `src/bridge_handlers.h`/`.cpp` — MCU-side Bridge adapters for `drive_horn`/`drive_led`/`pulse_ir`/
    `get_system_state`, written and host-tested. The four `Bridge.provide()` lines in `main.cpp` are
    written but commented out, one per line, explicitly pending a live one-at-a-time hardware
    registration session (a past registration attempt broke every working Bridge function on the same
    sketch — see `DEVICE_DEVELOPMENT_WORKFLOW.md` §3 — hence one-at-a-time, never a batch).
  - Geophone double-read/cadence bug — **fixed** (`millis()` cadence gate in `geophone_service()`),
    host-verified against 3 new Unity tests, but **only against the host `Wire` stub** — not yet proven
    against real ADS1115 timing on hardware.
  - `hostshim/Arduino_RouterBridge.h` — added (a real, durable fix, not a workaround) after discovering
    `SEISMIC_DEBUG_STREAM_RAW`'s committed default of `1` had been silently breaking every host
    `pio test`/`pio run` on this branch since the commit that added it. Host build is now clean again
    against the tree exactly as committed — confirmed by literally running it, not just reading the code.
  - **Completed 14 Aug, live hardware session:** the recheck task above finished. Findings:
    - `arduino-app-cli monitor` is **confirmed still silent** — two fresh tests (10s, 12s, debug log
      level) against a freshly-flashed, guaranteed-verbose build produced zero bytes. Not a stale
      finding — reproduced directly this session. New discovery: the underlying serial data is fine —
      a pre-existing root-owned `socat` daemon on the board bridges `/dev/ttyGS0` to
      `tcp:127.0.0.1:7500`, and that port delivers correct, well-formed, full-rate console output
      (confirmed via `ssh ... nc 127.0.0.1 7500`, captured and parsed 399 real lines). So the failure
      is specific to `arduino-app-cli monitor`'s own relay/display logic, not the firmware or the
      serial transport — App Lab's browser Serial Monitor (or the socat/nc bridge) remain the working
      alternatives.
    - **Wire vs Wire1: settled, `Wire` is correct.** Confirmed from the board's own generated
      devicetree, not inference: the `arduino:zephyr` core declares `Wire`/`Wire1`/... in the order
      listed by the board overlay's `zephyr,user { i2cs = <&i2c2>, <&i2c4>, <&i2c3>; }` — i2c2 is
      first, so it's `Wire`. The generated `.dts` shows i2c2's `pinctrl-0` is
      `i2c2_scl_pb10`/`i2c2_sda_pb11` and the node is aliased `arduino_i2c` (the default Arduino I2C
      header) — an exact match for `config.h`'s documented PB10/PB11 pins. `config.h`'s comment is
      updated with this and no longer says "unconfirmed."
    - **Cadence-gate fix: verified against the real ADS1115.** Captured 6s / 399 lines of real console
      output over the socat bridge; 369 raw-volts lines, 0 unparsed/garbled lines. Duplicate-adjacent
      pairs: 42/368 (~11.4%), max run length 4 — consistent with genuine sensor noise-floor repetition,
      not the old un-gated-polling bug (which would show much higher-frequency, longer runs). Also
      launched `scripts/live_seismic_plot.py` live against the real stream for direct visual
      confirmation.
    - **New finding, not previously measured:** the achieved raw-sample accept/print rate is only
      **~61.5 Hz**, well under the nominal 250 SPS the STA/LTA window sizing assumes — under this
      debug/bench build specifically (which carries `Bridge.update()` + `lora_service()` overhead not
      present in the field build), the 512-sample window spans ~8.3s of wall-clock time, not the
      assumed ~2.05s, and `STA_SAMPLES`/`LTA_SAMPLES` stretch proportionally. Root cause not yet
      profiled (plausibly per-`loop()`-iteration I2C + Serial + Bridge overhead exceeding the 4ms gate
      floor) — needs re-measuring on a field-flag build (`SEISMIC_DEBUG_STREAM_RAW=0`) before deciding
      whether STA/LTA sample counts need retuning, since the debug build's overhead may not reflect
      the real field rate.
  - **Real geophone bring-up finished, live hardware session, 14 Aug night — this is the actual
    "Rung 1" close-out.** Full derivation in `docs/KNOWN_GAPS.md`'s "STA/LTA field-flag rate
    re-measurement and real stomp-test calibration" entry; summary here:
    - **Real field-flag sample rate: 226.98 Hz**, measured on the actual lean field-deployment build
      (every `SEISMIC_DEBUG_*`/`FIRE_TEST_HARNESS`/`SEISMIC_DEMO_MODE` at 0) — confirms the earlier
      ~61.5 Hz figure was debug/Bridge overhead, not a hardware ceiling. At this real rate,
      `STA_SAMPLES=25`/`LTA_SAMPLES=250` work out to ~110 ms / ~1.10 s, both inside the literature
      targets (Wijayakulasooriya et al. arXiv:2406.05140; Trnkoczy/Güralp STA/LTA sizing guidance) —
      no retune needed, no change made to either constant.
    - **Real human stomp test: done.** Quiet floor ratio 1.03-1.13 across ~89 s (before and after,
      no false triggers); a real stomp produced `ratio=4.60` with a raw-volts CSV dump confirming a
      genuine ~65x amplitude transient. `STA_LTA_TRIGGER_RATIO=4.0` clears the floor by ~3.5x and the
      stomp clears the threshold by ~15% — kept unchanged, now validated rather than assumed.
    - **`STA_LTA_DETRIGGER_RATIO=1.5` confirmed dead code** on 14 Aug — `grep` showed it referenced
      nowhere outside its own `#define`; `state_machine.cpp`'s `kEvent` state only exits on
      `EVENT_MAX_MS` elapsed, no ratio-based detrigger logic existed anywhere. **Since removed
      outright, 15 Aug** — see below — rather than left as an indefinite unwired placeholder.
  - **`kSensing` efficiency fix, `GEOPHONE_WINDOW_STALE_MS` fix, `STA_LTA_DETRIGGER_RATIO` removal —
    15 Aug, geophone-only completion pass.** Full derivation in `docs/KNOWN_GAPS.md`'s "`kSensing`
    redundant STA/LTA re-run..." entry; summary here:
    - **Redundant STA/LTA re-run fixed.** `state_machine_tick()`'s `kSensing` case was re-running the
      full `read_seismic_window()` + `sta_lta_detect()` slide (~72k float ops) on every unthrottled
      `loop()` iteration, not just when a new sample had actually landed. `geophone.cpp`/`geophone.h`
      gained `geophone_sample_count()` (monotonic, non-saturating); `kSensing` now skips the
      read+detect entirely when it hasn't advanced since the last check — same trigger behavior and
      timing, just not recomputed redundantly. A correctness risk this created (`geophone_ok()`
      going stale forever if nothing calls `read_seismic_window()` on a dead sensor) was closed in the
      same pass by adding an unconditional proactive staleness check inside `geophone_service()`
      itself. Host-tested (`tests/test_geophone/`, 2 new cases); a real bug this surfaced —
      `geophone_init()` wasn't resetting the new counter — was fixed alongside. `pio run -e native` /
      `pio test -e native` green, 37/37 test cases.
    - **`GEOPHONE_WINDOW_STALE_MS` fixed to match its own documented formula.** Was `3072` ms (1.5x
      the *nominal* 250 Hz fill time), but the constant's own comment says 1.5x the real fill time —
      at the real measured 226.98 Hz rate that's `3384` ms. Updated the constant, not the comment,
      since the formula is deliberate real-hardware margin.
    - **`STA_LTA_DETRIGGER_RATIO` removed entirely** (both `SEISMIC_DEMO_MODE` branches in
      `config.h`, plus its comments). Decision: timeout-only exit from `kEvent` (`EVENT_MAX_MS`) is
      fine as the current design; a real ratio-based early-exit remains a legitimate future feature
      but only once real multi-event stomp data exists to set a threshold against — not before.
      `device/mcu/README.md` updated to match. **Hard boundary respected**: `git diff` on `config.h`
      touches zero characters of the `STA_LTA_TRIGGER_RATIO`/`STA_SAMPLES`/`LTA_SAMPLES` `#define`
      lines themselves.
    - **Real hardware flash + multi-trial stomp validation: done, 15 Aug.** Flashed and confirmed on a
      live console (board discovered at `192.168.1.10` — mDNS `eletect-x.local` doesn't resolve from
      Windows git-bash or WSL2; see `docs/eletect-x-applab-notes.md`). Quiet floor unchanged post-fix
      (1.09–1.15, matching the 14 Aug baseline). Ran the 12-stomp/60s-interval protocol against a
      lean-flag-toggle build: **11/12 detected** (mean trigger ratio 4.232, stdev 0.166; mean notify
      probability 0.8784, stdev 0.0105), one genuine sub-threshold miss (peak ratio 3.80, explained via
      the surrounding `[seismic]` lines, not dismissed), **zero false triggers** across a 688-sample
      quiet baseline (mean 1.149, stdev 0.031). MPU-side confirmed all **11/11** triggers produced a
      matching `report_footfall_event` with `alert=True` and `fused_P` 0.979–0.986 — required reading
      the board's raw Docker json-log directly (`docker run --rm -v /var/lib/docker/containers:/logs:ro
      alpine ...`, using the `arduino` user's `docker` group access) since `docker logs` itself fails on
      this container with a stream-corruption error and passwordless `sudo` isn't configured on the
      board. Full statistics and methodology in `docs/KNOWN_GAPS.md`'s 2026-08-15 multi-trial entry,
      now marked **closed**. Board left synced and re-flashed with `SEISMIC_DEBUG_VERBOSE=0` (lean field
      build), confirmed quiet before ending the session.
    - **Raw trigger data reaching the MPU: closed on the MCU/host side, later 14 Aug session.**
      `state_machine.cpp`'s `kSensing` case now calls a real
      `Bridge.notify("report_footfall_event", schema_version, probability, sta_lta_ratio,
      feature_vector)` on every STA/LTA trigger, right before the `kEvent` transition. `sta_lta_ratio`
      is the real `result.peak_ratio`; `feature_vector` is 8 real per-window statistics (`sta`, `lta`,
      `peak_ratio`, `trigger_index`, window min/max/mean/population stdev) computed by the new
      `footfall_features.cpp`/`.h`, host-tested (`tests/test_footfall_features/`, 6 known-answer
      tests). `probability` is a real, honestly-derived saturating function of `peak_ratio` — **not**
      the on-MCU TinyML model output the schema was originally written assuming; `ml/seismic/` is
      still empty, so this is a documented placeholder, tracked as its own open gap in
      `KNOWN_GAPS.md` right next to the `ALERT_PROBABILITY_THRESHOLD` entry. Closing this also
      required making `Bridge.begin()`/`Bridge.update()` unconditional in `main.cpp` (previously
      gated behind the bench-only `SEISMIC_DEBUG_STREAM_RAW` flag, which would have silently kept the
      new notify from ever firing in the real field build) — confirmed safe on real hardware and the
      host build alike, full reasoning in `KNOWN_GAPS.md`'s dedicated entry for that decision.
      `pio run -e native` and `pio test -e native` are both green, 35/35 tests passing.
      **Real-hardware linker failure found and fixed, same night, before the live session below could
      run.** The original `probability` formula (`1 - exp(-k*(ratio-1))`) passed the host build cleanly
      but failed to link on the real board: `arm-zephyr-eabi-g++`/`ld` reported `undefined reference to
      '__errno'` from `libm_nano.a`'s `expf`. Root cause: the real UNO Q firmware build links
      `--specs=nano.specs --specs=nosys.specs -nostdlib` against a minimal picolibc-nano math library
      that doesn't provide `__errno`, which `expf` needs internally for domain/range error signaling —
      invisible to `pio test -e native` because the host build always has a full libc. Fixed by
      replacing the formula with `x^2/(x^2+c^2)` (`x = peak_ratio - 1`, `config.h`'s
      `FOOTFALL_PROBABILITY_SATURATION_C = 1.2f`), which needs only multiplication/division and calls no
      libm transcendental function — re-solved against the same two real anchors (quiet floor 1.13 ->
      ~0.012, real stomp 4.60 -> 0.9), re-verified host-green (35/35), then re-flashed and confirmed the
      real board links and boots clean. **Lesson for future MCU work:** a host-green build proves
      nothing about hardware-buildability for code calling a libm transcendental function (`exp`, `log`,
      `pow`, trig, ...) on this toolchain — `sqrt`/`sqrtf` (already used in `footfall_features.cpp` for
      the feature vector's stdev) does link fine, but that's only confirmed for the two functions
      actually used here, not the whole libm surface. Full derivation in `KNOWN_GAPS.md`.

      **Closed end to end, live hardware session, 14 Aug night.** With the fix above flashed, the
      MPU-side registration (`Bridge.provide("report_footfall_event", _on_footfall_event)` in `main.py`)
      was uncommented and pushed — `debug_stream_raw_seismic_sample` reconfirmed still running clean
      afterward (`app list` -> `running`, no crash loop), satisfying the one-at-a-time discipline. A real
      firm tap near the geophone then produced this real MPU-side log line:

      ```text
      INFO:services.reflex_loop:footfall event: mcu_probability=0.865 sta_lta_ratio=4.040 fused_P=0.980 alert=True used=['seismic'] dropped=['acoustic', 'vision'] feature_vector=[0.00387, 0.000958, 4.0397, 511.0, -0.0198, 0.0167, -0.000285, 0.00144]
      INFO:services.reflex_loop:[SAFE_MODE] would call drive_horn(schema_version=1, gain_pct=100.0, duration_ms=65535) - not calling (dry run)
      ```

      This is the first real trigger this project has gotten end to end from the geophone through
      STA/LTA, the notify, `handle_footfall_event`'s fusion/decision, and out the other side as a
      (dry-run, `SAFE_MODE`-gated) deterrence decision — real per-window `feature_vector`, not
      placeholders; `fused_P=0.980`/`alert=True` show `cognition.fusion`/`decision` consuming a real
      MCU-sourced reading for the first time; horn correctly not fired since `SAFE_MODE` was left on.
      Full writeup, including the exact linker error text, in `KNOWN_GAPS.md`'s "Raw seismic trigger
      data does not reach the MPU..." entry, now marked **closed** — both directions (MCU notify, MPU
      registration) proven on real hardware, not just host-tested.
- **`device/mpu`** — **no longer a bench-only stub.** `main.py` is now the real entry point:
  `cognition/decision.py` (pure `decide()`) and `services/reflex_loop.py` (the imperative shell —
  `handle_footfall_event`/`handle_acoustic_event`) implement the actual sense→fuse→decide→actuate loop,
  wired against the existing `cognition/fusion.py`. **`SAFE_MODE` defaults on** via the `ELETECT_SAFE_MODE`
  env var — `drive_horn` calls are dry-run logged, not real, until someone explicitly sets
  `ELETECT_SAFE_MODE=0` for a live session. Only seismic is fused end-to-end right now; acoustic is
  logged-only (no elephant-mapping exists yet); vision is always reported unavailable (no detector
  built). Two invented placeholders, both flagged in code and `KNOWN_GAPS.md`:
  `ALERT_PROBABILITY_THRESHOLD = 0.5` (uninformative midpoint, not tuned) and a horn-only "request
  protocol max, let the MCU clamp" deterrence policy standing in for the not-yet-built contextual
  bandit. The `Bridge.provide()` calls for `_on_footfall_event`/`_on_acoustic_event` are written but
  commented out, same one-at-a-time discipline as the MCU side. 114/114 pytest passing, `ruff check`
  clean — verified directly, not just from the report.
- **`ml/`** — still untouched. No training data, no models, nothing. Not blocking the Aug 20 trial
  (vision uses a fixed pretrained detector per CONTEXT.md §4), but relevant to the "scientifically
  rigorous" goal and the Hackster write-up's DSP/model section.

**Explicit reprioritization, decided 14 Aug evening, now fully satisfied:** finishing and hardening the
geophone subsystem was to come before flashing/firing the fire-test harness and before any live Bridge
registration. The geophone bring-up items (I2C bus confirmation, cadence-fix verified on real hardware,
real field-flag sample rate, real stomp test) and the raw-data-to-MPU gap (`report_footfall_event`,
including the one live Bridge registration it required) are all done and closed on real hardware as of
14 Aug night — see above. The fire-test harness (flash + fire on a real actuator) and the remaining
`drive_horn`/`drive_led`/`pulse_ir`/`get_system_state` Bridge registrations are next in this thread,
same one-at-a-time discipline.

`docs/ELETECT_X_PITCH.md` — a full project pitch/description doc was also written this session
(problem, solution, how it works, full tech stack, honest current status, contest tie-in). Useful if
anyone needs to explain the whole project from scratch, not required reading for continuing the build.

## ADR trail — read these together, not in isolation

11 ADRs in `docs/decisions/` (0000 is the template, ignore). **Numbering has one real duplicate**:
both `0001-usb-camera-imx462.md` and `0001-physical-ai-sensing-and-fusion-architecture.md` are "0001"
— don't rely on the number alone when searching.

The horn/acoustic story changed shape three times. Reading only one of these will give you a wrong
picture — read **0003 → 0005 → 0009 → 0011** in that order:

| ADR | Status | Decision |
|---|---|---|
| 0001 (camera) | accepted | Arducam IMX462 USB day/night camera |
| 0001 (fusion/sensing) | accepted | Drop ADS1115 for final node (STM32 internal ADC via LPBAM); FOMO primary vision, MDv6-compact documented fallback |
| 0002 | accepted | LoRaWAN star over Meshtastic mesh; Meshtastic hardware repurposed for field-team comms |
| 0003 | accepted | Single BTL channel, gain-limited; horn flush-mounted in main enclosure |
| 0004 | **superseded by 0005** | (briefly switched to TOA SC-610, reversed same day) |
| 0005 | accepted | Revert to Ahuja SUH-15; solve compactness via enclosure form, not a different part |
| 0006 | **superseded by 0009**, kept as fallback | Gunshot-dedicated comparator gate + pre-trigger DMA buffer |
| 0007 | proposed | Unified acoustic architecture, per-class signature table, gunshot bypasses fusion |
| 0008 | proposed, 2 bench measurements pending | MPU stays in deep suspend (not poweroff) between events, ~0.42-0.45W continuous |
| 0009 | proposed, gated on one bench test | Continuous on-MCU LPBAM classifier supersedes 0006's gate design |
| 0011 | proposed (13 Aug) | Horn driver moves to its own small IP66 housing, wired via speaker cable/gland — amends 0003/0005's flush-mount call |

`hardware/cad/enclosure-design-concept.md` (380 lines, last touched 14 Aug — after ADR 0011) should
already reflect the split-housing design; confirm this before assuming it's still pre-0011.

## Procurement — essentially done as of 15 Aug

`hardware/bom/procurement-status.md` is the only trustworthy procurement doc — `bom.md` is stale on
the power system, the LED driver part (says PT4115, actually XL4015), and doesn't reflect ADR 0011's
horn-housing split. Don't quote prices or parts from `bom.md` without cross-checking the tracker.

Everything sourceable online is ordered (battery, MOSFETs, TVS/Schottky diodes, brass inserts, SS-304
screws, standoffs, VHB tape, USB-C adapter, pole-mount clamps ×2 for main enclosure + horn housing).
What's left is a fixed, small, local-store-only list — no shipping risk, one trip:

1. Optical window — acrylic/PC 2-3mm
2. PVC pipe 32mm + end caps (geophone burial)
3. SS-304 bolt M10×100 (geophone spike) — confirmed not sold at Robu, Amazon, or onlyscrews at this
   length/material; onlyscrews tops out at M10×70mm Allen-head, not a true hex bolt
4. Araldite epoxy
5. HDPE conduit 20mm
6. Solar panel — 12V, 15-20W (a 20W WAAREE panel is already ordered but lands 24 Aug, too late — it
   becomes the Phase 2/permanent-build panel, not the trial panel)
7. Fuse + holder, 6A
8. Power switch — SPST, 2-position, ≥10A/12V DC

**Real open risk, not fixable by more ordering:** the battery (Robu order #3636219, placed 14 Aug)
quotes 5-7 working days — could land Aug 21-24, after the deployment date. Worth calling Robu
(1800 266 6123) to check on expediting.

## Known gaps, ranked by what actually blocks Aug 20 (updated 14 Aug evening)

Full list lives in `docs/KNOWN_GAPS.md`, organized by build call — it is the accurate, current record,
kept up to date live through tonight's session. Highest-priority items as of the account switch:

1. **Geophone hardware bring-up: closed, 14 Aug night.** I2C bus, cadence-fix, real field-flag sample
   rate (226.98 Hz), and the real human stomp test are all done and confirmed on hardware — see
   `device/mcu` section above and `docs/KNOWN_GAPS.md`'s "STA/LTA field-flag rate re-measurement and
   real stomp-test calibration" entry. `STA_LTA_TRIGGER_RATIO` is now validated (kept at 4.0), not
   assumed. **`report_footfall_event` is now closed end to end, real hardware, 14 Aug night** —
   `state_machine.cpp` calls `Bridge.notify()` with real `sta_lta_ratio`/`feature_vector` and a
   documented placeholder `probability` on every trigger, a real-hardware `expf`/`__errno` linker
   failure was found and fixed same night, the MPU-side registration was uncommented and pushed with no
   regression to `debug_stream_raw_seismic_sample`, and a real stomp produced a real captured MPU log
   line (`mcu_probability=0.865`, `fused_P=0.980`, `alert=True`). See `device/mcu` section above and
   `KNOWN_GAPS.md`'s "Raw seismic trigger data does not reach the MPU..." entry, now marked **closed**.
   `SAFE_MODE` is still on (code default) — the horn was correctly not fired. Remaining before the
   field trial itself: `ELETECT_SAFE_MODE=0` is an explicit live-session step, not yet done, and only
   for a session with a human present.
2. **The MPU integration loop is no longer missing** — it exists now (`device/mpu/main.py`,
   `services/reflex_loop.py`), dry-run by default via `SAFE_MODE`. `report_footfall_event`'s
   registration is now live and proven on hardware (item 1 above); `report_acoustic_event`'s
   registration is still written and commented out, same one-at-a-time discipline, deliberately out of
   scope for this pass.
3. **The fire-test harness's software path is now verified on real hardware (15 Aug)** — correct
   `[firetest]` acks and cooldown refusal for all four commands. **Physical activation is not yet
   confirmed: horn, LED, and IR are not wired to the board.** Re-run once wiring exists.
4. **LoRa `Serial` vs `Serial1` conflict with Bridge — mostly resolved on paper, not yet on hardware.**
   A documentation pass (official datasheet + `Arduino_RouterBridge` README + Arduino Forum reports,
   citations in `docs/eletect-x-applab-notes.md`) found a real lean toward `Serial1` being Bridge's own
   internal link and `Serial` being what actually reaches the Grove LoRa-E5 — opposite of `config.h`'s
   current `LORA_SERIAL Serial1` default. Not confirmed on this board yet. Needs a live test: both
   objects active simultaneously, see which one the E5 actually answers on.
5. **USB-C host-mode-under-VIN-power is unverified.** If the camera doesn't enumerate under VIN power
   (not USB-C power), the whole vision pipeline architecture needs rework. Check this early, once past
   the geophone work.
6. **SenseCAP gateway is still labeled EU868**, must be set to IN865 region profile in ChirpStack and
   join-tested before any real transmission — transmitting on 868MHz is illegal in India.
7. **`loop()` has no task/priority separation** — an actuator fire (horn especially, ~3.15s worst case)
   currently blocks geophone/LoRa servicing for that whole window. Logged, not scheduled before Aug 20,
   flagged so the trial's data gets read with that caveat.

## Git state (as of 15 Aug)

Branch `feat/mcu-seismic-debug`. `git status` shows most of the tree as "modified" — spot-checked
`CONTEXT.md`'s diff before my edits today and it was a 1:1 line-ending/whitespace normalization, not
real content changes, but this was not verified file-by-file. **Run `git diff --stat` and spot-check
before committing or discarding anything** — don't assume it's all noise.

Untracked files that are real work product, not yet committed:
- `docs/decisions/0011-horn-driver-split-to-separate-housing.md`
- `docs/eletect-x-applab-notes.md`
- `hardware/bom/eletect-x-power-budget.xlsx` (referenced repeatedly by `procurement-status.md`)
- `hardware/references/uno-q-official/` (official Arduino datasheet/schematic/STEP files)
- `.agents/`
- `hardware/bom/.~lock.eletect-x-power-budget.xlsx#` — a LibreOffice/Excel lock file, likely just
  needs cleanup, not a real artifact

## Other doc-currency notes

- `docs/BUILD_BLUEPRINT_AUG8.md` is fully superseded — its day-by-day schedule (through 8 Aug) is in
  the past and was not hit on schedule. **`docs/BUILD_BLUEPRINT_AUG20.md` (written 14 Aug) is the
  operative day-by-day plan to the deployment date — check it for the current action list.**
- `docs/PROJECT_BLUEPRINT.md` itself says it's superseded by `BUILD_BLUEPRINT_AUG8.md` for scheduling,
  but its architecture/workflow sections (§0-5) still stand.
- Root `README.md`'s status line ("Architecture frozen; implementation in progress") and its pointer to
  `PROJECT_BLUEPRINT.md` are generic — low priority to fix, doesn't block anything.

## Session-continuity protocol (unchanged, from CLAUDE.md)

This planning session (Opus/Cowork) stays long-lived across the whole engagement and does research,
docs, BOM/spreadsheet edits directly. A separate execution session (Sonnet, in VS Code/Claude Code)
does firmware/code changes on the physical board — new session per build call by default, same session
only for a small follow-up fix. If *this* planning session has to restart under a different account,
this file plus `CONTEXT.md` plus `docs/KNOWN_GAPS.md` should be sufficient to resume without re-deriving
anything above.
