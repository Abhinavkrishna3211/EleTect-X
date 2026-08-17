# EleTect X — Build Blueprint to Aug 20 (supersedes BUILD_BLUEPRINT_AUG8.md)

Written 14 Aug, 6 days out from the DFO Kothamangalam field deployment. `BUILD_BLUEPRINT_AUG8.md`'s
schedule is stale (dates in the past, MVP freeze didn't hit on 8 Aug) — this is the operative plan.
Cross-check against `HANDOVER.md` and `docs/KNOWN_GAPS.md` before starting any item below; both are
kept current and take precedence if this doc drifts.

Two real long-pole items drive the whole schedule: **the enclosure has zero CAD progress** (only the
markdown design doc exists, no Fusion 360 model/STEP/STL — modeling + print time is the biggest
schedule risk), and **`device/mpu/main.py` has no real integration loop** (everything downstream of
"sensor event happened" is unbuilt). Both start Day 0.

## Day 0 — Thu 14 Aug (today, remainder of)

- Call Robu (1800 266 6123) — check battery expedite status, order #3636219.
- Local-store run: optical window, PVC pipe+caps, SS-304 M10×100 spike, Araldite, HDPE conduit,
  12V/15-20W solar panel, 6A fuse+holder, SPST power switch. All local-only, no shipping risk.
- Bench-verify SenseCAP gateway region: power up, set ChirpStack region profile to IN865, run a real
  join test with the Grove LoRa-E5. Cheap to check now, illegal to get wrong later (868MHz un-transmit-
  legal in India).
- Bench-verify USB-C host-mode-under-VIN: confirm the IMX462 enumerates when the board is powered via
  VIN, not USB-C. If this fails, the vision architecture needs rework — find out today, not day 4.
- Start Fusion 360 modeling on the enclosure (main housing + horn housing per ADR 0011's split). This
  is the longest lead-time item on the whole list — start it in parallel with everything else, don't
  sequence it after firmware.

## Day 1-2 — Fri 15 / Sat 16 Aug

- Enclosure: finish both housing models, slice, start PETG prints (CR-M4 + Bambu A1). Budget real
  print-queue time — two enclosures, gasket channels, bosses, don't assume one shot prints clean.
- Firmware: build the real `device/mpu/main.py` sense→fuse→decide→actuate loop — the single biggest
  remaining software task. Wire Bridge `provide()` handlers on the MCU side (`drive_horn`, `drive_led`,
  `pulse_ir`, `geophone_ok`) to match.
- Firmware: fix the geophone sampling-cadence bug (`geophone_service()` sampling at loop rate instead
  of gated cadence).
- Firmware: resolve the LoRa `Serial`/`Serial1` conflict with Bridge before any further LoRa work.

## Day 3 — Sun 17 Aug

- Assembly: heat-set inserts into printed parts, mount boards on standoffs, wire the power system
  (XL4015 buck set to 14.2V, current limit verified with a multimeter *before* connecting the battery).
- Mount battery once it lands (delivery-risk item from Day 0's Robu call).
- Run the geophone bench stomp test — never run yet, validates STA/LTA thresholds against real footfall
  instead of synthetic data.

## Day 4 — Mon 18 Aug

- Full system integration test, end to end: geophone → MCU → Bridge → MPU fusion → decision →
  horn/LED actuation → LoRa uplink → Supabase → dashboard. First time every link in the chain has
  been exercised together.
- Weatherproofing pass: gasket seams, glands, e-PTFE vent, desiccant packs.

## Day 5 — Tue 19 Aug (buffer)

- Field rehearsal: pole-mount both housings, time the 3-person install, check solar charging under
  real sun.
- Buffer for whatever Day 4's integration test surfaces — expect it to surface something.
- Git hygiene: commit the real untracked work (ADR 0011, power-budget spreadsheet, UNO Q reference
  PDFs), spot-check the wider working-tree diff before committing (much of it may be line-ending
  noise, not real changes — verify, don't assume). Tag a pre-deployment freeze point.

## Day 6 — Wed 20 Aug

- Deploy with DFO Kothamangalam. 10-day trial begins.

## What happens after Aug 20

Field footage and the real deployment story are the primary material for both contest submissions —
Robu Arduino Physical AI Challenge (23 Aug) and Hackster "Invent the Future with UNO Q" (30 Aug). The
write-up pass leans on `edge-impulse-hackster-writeup` and should start as soon as footage is in hand,
not wait for the full 10-day trial to finish if a submission-worthy clip lands earlier.
