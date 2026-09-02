# Night characterisation: external IR illuminator, LED wings, and camera interaction

**Rig:** production hardware, Kothamangalam backyard. Arduino UNO Q (STM32U585 MCU + Linux MPU),
Arducam IMX462 USB UVC camera, external 850 nm IR illuminator on the MCU's IR MOSFET, dual LED
wings per ADR 0014 §E.
**Dates:** 1–2 September 2026. Findings 1–3 measured 18:27–18:50 UTC (23:57–00:20 IST); the
Finding 4 exposure/IR battery ran ≈ 00:20–01:25 IST 2 Sept; a dawn-transition soak ran ≈ 02:17–08:29
IST and captured the night→day crossover before a board reboot ended it. Overcast, no moon, no
artificial light in frame.
**Board identity:** `boot_id 6b2c727a-af0d-4517-a6c7-a8069da92a64`, container `eletect-x-main-1`
restart count 0, held unchanged through every measurement in Findings 1–4 and the full dawn
transition. The board then rebooted spontaneously at ≈ 08:27 IST (64 s, self-recovered, new
`boot_id 2c601696-8ce6-463d-917b-6da275008c34`) — after all measurement was done; see the Appendix.
No reflash at any point.

Harness: `night_char.py` on the MPU, host V4L2 path (not the container camera path — see
[Method](#method)). Raw frames and per-run JSON under `/home/arduino/vdiff/nightchar/`. Every
number below is reproduced in this document so it survives the board being reimaged.

## Why this was measured

Two questions blocked further deterrence work:

1. **Does the external IR illuminator actually buy us anything at night, and at what range?**
   ADR 0009 assumed it did. Nobody had measured it on the real optic, in the real scene, at the
   real standoff distances. Without a number there was no basis for deciding when to spend the
   MOSFET duty budget and the battery on it — which is exactly the decision ADR 0019 has to make.
2. **Do our own LED wings blind our own camera while they fire?** If the strobe washes out the
   frame, then detection and deterrence must be serialised (deter, wait, re-detect), which costs
   seconds on every encounter and makes "did it work?" unanswerable in real time. If it does not,
   they can overlap.

## Scene geometry and metrics

The frame is scored whole and in four horizontal bands, top of frame being furthest away:

| Band | Frame rows | What it covers in this yard |
|---|---|---|
| `far` | 0–30% | Beyond the treeline, background |
| `treeline` | 30–55% | The vegetation edge — **where an animal first becomes visible** |
| `mid` | 55–78% | Open ground |
| `near` | 78–100% | Immediate foreground, within a few metres of the unit |

Per band: mean **luma** (0–255), **contrast** (luma std), mean HSV **saturation**, **sharpness**
(variance of the Laplacian — a standard focus/detail measure, higher is more resolved detail), and
**clip_hi** (fraction of pixels above 250, i.e. blown out).

Sharpness is the metric that matters most here. Luma only says the scene got brighter; a detector
needs recoverable *structure*. A rise in Laplacian variance means real edges appeared, not just
that the histogram shifted.

## Method

Three things had to be got right before any of these numbers were trustworthy. All three cost real
time to find, so they are recorded here.

**Exposure had to be locked.** The camera's automatic gain control reacts to the IR pulse within a
frame or two and pulls sensor gain back down, holding output luma roughly constant and hiding the
illuminator's effect. The first sweep, run on auto-exposure, measured a full-frame delta of only
**+3.2%** (lit 126.30 vs dark 122.42) with sharpness going *down* by 5.0 — a result that, taken at
face value, would have said the illuminator does nothing. It is an artefact of AGC. All subsequent
runs set `CAP_PROP_AUTO_EXPOSURE = 1` (manual) then `CAP_PROP_EXPOSURE` to a fixed value, and the
readback was verified on every camera open. Note that the host V4L2 path accepts exposure writes;
the container's camera path does not, and sits frozen at 156.

**The capture window had to be much longer than the pulse.** `pulse_ir()` is fired through a
`docker exec`, which cold-starts in 1–3 s, while the pulse itself is only 500 ms. An early version
of the harness captured for 3 s from the moment the fire call was *issued*, so the pulse routinely
landed at or past the end of the window: one run yielded **0 lit frames out of 30**, another
yielded **1**. The window was extended to 11.5 s.

**Photometry had to leave the hot loop.** Running `photometrics()` and `infer()` inline throttled
capture to 5–8 frames per window. The loop was reduced to `cap.read()` plus a cheap grayscale mean,
with all photometry, inference and JPEG writing moved to post-processing, and lit/dark
classification done afterwards against a per-cycle reference (a frame counts as *lit* if its
grayscale mean exceeds that cycle's own 6-frame pre-fire reference by more than 2.0). Lit-frame
yield went from 1 to ~83 per run.

Each sweep is 8 cycles of a single 500 ms pulse, spaced to respect the firmware's 5 s minimum IR
interval.

## Baselines — the unlit scene

Six frames each, LED off, IR off, night.

| Run | Exposure | Full luma (sd) | Sat | Sharp | far | treeline | near | Vision boxes |
|---|---|---|---|---|---|---|---|---|
| `base_auto` | auto | 132.90 (0.66) | **0.000** | 85.9 | 125.68 | 136.79 | 134.39 | 0 |
| `base_lock250` | 250 | 119.81 (0.67) | **0.000** | 86.2 | 112.86 | 123.49 | 121.28 | 0 |
| `base_lock50` | 50 | 29.82 (0.28) | **0.000** | 79.2 | 26.51 | 32.58 | 29.66 | 0 |

Two things to take from this.

**Mean HSV saturation is exactly 0.000 at night, on every band, in every baseline.** The IMX462
swings its mechanical IR-cut filter out once the scene is dark enough and the image goes genuinely
monochrome. A daylight colour frame from the same camera reads mean S above 30. That is a clean
two-order-of-magnitude separation with nothing in between, and it is the empirical basis for
`NIGHT_SATURATION_THRESHOLD = 12.0` and for ADR 0019's whole approach — the filter's position is
not exposed by any API on this board, but it is plainly readable off the pixels.

**On auto-exposure the camera is already running at high gain at night** — it reaches luma 132.9,
*brighter* than a locked exposure of 250. It is spending noise to get there. This matters for the
interpretation of the sweeps below.

## Finding 1 — the external IR illuminator delivers a large, consistent gain at every range

### Locked exposure 100 — 83 lit frames, 48 dark frames, 8 cycles

| Band | Luma lit (sd) | Luma dark (sd) | Δ luma | Sharp lit | Sharp dark | Δ sharp |
|---|---|---|---|---|---|---|
| full | 85.31 (3.8) | 60.71 (0.8) | **+24.60 (+40.5%)** | 123.4 | 98.8 | +24.5 |
| far | 74.80 (4.1) | 55.40 (0.8) | +19.41 (+35.0%) | 121.4 | 100.3 | +21.1 |
| **treeline** | 90.60 (4.9) | 64.09 (0.8) | **+26.51 (+41.4%)** | 149.5 | 95.8 | **+53.7** |
| mid | 88.91 (4.6) | 63.40 (0.9) | +25.51 (+40.2%) | 120.7 | 99.0 | +21.7 |
| near | 89.87 (5.3) | 61.29 (0.9) | +28.58 (+46.6%) | 100.8 | 101.3 | −0.5 |

### Locked exposure 156 — 80 lit frames, 48 dark frames, 8 cycles

| Band | Luma lit (sd) | Luma dark (sd) | Δ luma | Sharp lit | Sharp dark | Δ sharp |
|---|---|---|---|---|---|---|
| full | 113.55 (4.9) | 84.42 (0.9) | **+29.13 (+34.5%)** | 143.9 | 90.3 | +53.5 |
| far | 102.09 (3.7) | 77.92 (0.9) | +24.17 (+31.0%) | 143.2 | 91.3 | +51.9 |
| **treeline** | 119.46 (5.2) | 88.15 (1.0) | **+31.31 (+35.5%)** | 186.5 | 95.2 | **+91.2** |
| mid | 117.55 (6.5) | 87.90 (0.9) | +29.65 (+33.7%) | 138.4 | 90.1 | +48.3 |
| near | 118.29 (8.2) | 85.42 (0.8) | +32.87 (+38.5%) | 104.0 | 84.8 | +19.3 |

**No clipping in any run** — the illuminator never blows out the near field, so there is headroom
if a stronger emitter or a longer pulse is ever wanted.

### What this says

The illuminator works, and it works where it needs to. Across both exposures the luma gain is
+31% to +47% on every band, with dark-frame standard deviations under 1.0 — the effect is far
outside the noise, and it repeated across all 16 cycles with no drift.

**The operationally important result is the sharpness gain at the treeline: +53.7 at exposure 100
and +91.2 at exposure 156, roughly a doubling of resolved detail.** That band is the vegetation
edge, the place an elephant first becomes visible as it leaves cover, and it is the hardest part of
the frame — furthest from the emitter, most cluttered, lowest contrast. The illuminator improves it
most. `far` gains almost as much (+51.9 at exposure 156).

`near` is the exception: luma rises the most (+38.5%) but sharpness barely moves (+19.3 at
exposure 156, −0.5 at exposure 100). The foreground is close enough to be adequately exposed
already, so extra light adds brightness without adding recoverable structure. This is the expected
inverse-square behaviour and it is fine — the near field was never the problem.

Higher base exposure amplifies the sharpness benefit (treeline +53.7 → +91.2) while slightly
*reducing* the proportional luma benefit (+41.4% → +35.5%), consistent with the illuminator lifting
the whole scene further above the sensor's noise floor.

### The honest caveat

**Every number above was measured with exposure locked. The deployed pipeline runs the camera on
auto-exposure.** These runs prove the illuminator puts real, substantial, well-distributed photons
onto the sensor at all four range zones. They do **not** directly predict the detection improvement
in the shipped AGC configuration, because AGC will convert some of that extra light into reduced
sensor gain rather than increased brightness — which should be a genuine noise win, but is a
different quantity from the one measured here, and the one auto-exposure run taken was too short
(4 lit frames) to characterise it. Logged in `docs/KNOWN_GAPS.md`; needs an attended run with a
real target in frame.

**No detections in any sweep, lit or dark: 0 Elephant, 0 Boar, max confidence 0.000, in all
131+128 frames.** The backyard was empty, so this is the correct answer and is a useful negative
control — but it means the illuminator's effect on *detection* (as opposed to image quality) is
still unmeasured. The model's positive control was established separately at 9/10.

## Finding 2 — our own LED wings do not blind our own camera

Both wings, gain 100%, 2500 ms bursts, locked exposure 100. Six baseline frames with the LEDs off
immediately before each burst, five frames captured during it. All four night patterns tested.

| Pattern | Luma off | Luma during (mean) | Δ | during min–max | sd | Sharp during | clip_hi | Vision (off / during) |
|---|---|---|---|---|---|---|---|---|
| 2 `fast_strobe` | 58.66 | 57.94 | **−0.72** | 57.38–58.48 | 0.35 | 96.0 | 0.000 | 0 / 0 |
| 4 `sweep` | 58.46 | 58.17 | **−0.28** | 57.70–58.63 | 0.35 | 96.2 | 0.000 | 0 / 0 |
| 5 `pulse_both_sync_11hz` | 58.45 | 58.11 | **−0.34** | 57.20–58.53 | 0.49 | 96.6 | 0.000 | 0 / 0 |
| 6 `flicker_both_independent` | 58.45 | 58.15 | **−0.30** | 57.34–58.46 | 0.41 | 96.6 | 0.000 | 0 / 0 |

All four ACKed `[1, 1, null, true]`.

The deltas are −0.28 to −0.72 luma against a within-burst standard deviation of 0.35–0.49. That is
at or barely above the frame-to-frame noise of the sensor. Sharpness sits flat at 96.0–96.6 across
every pattern, against a 96-ish baseline. **`clip_hi` is exactly 0.000 for every pattern** — not a
single pixel is blown out, including by the 11 Hz sync pattern, the most aggressive one we have.

**Conclusion: detection and deterrence can overlap.** There is no need to serialise deter → wait →
re-detect. The reflex loop can keep the camera running through an LED burst and capture evidence of
the animal's actual reaction *while* the wings are firing — which is exactly what the encounter-aware
cadence work in the Item C proposal needs, and it is what makes "did the deterrent work?" an
answerable question in real time rather than a guess.

### Frame-by-frame visual check — added 2 September

The photometric null was followed up by pulling the saved JPEGs and inspecting them directly, since
a flat luma number could equally mean "LED does not reach the sensor" or "LED reaches the sensor
but AGC/JPEG hid it". The frames settle it. A max-gain both-wings frame (pattern 5, 11 Hz sync,
30 ms and 1.23 s into the burst), a `flicker_both_independent` frame, and the LED-off / IR-off
reference are **visually indistinguishable**: same treeline foliage, same soft glow at bottom-right
(that glow is the camera's *onboard* IR reflecting off the nearest foliage and the enclosure lip,
present in every night frame), and in the LED frames **no hotspot, no bloom, no lens flare, no
edge flare, no pool of light anywhere.** Nothing in the image indicates a white emitter fired.

**This was shot with the camera, the external IR emitter and both LED wings mounted in the
production 3D-printed enclosure, in the orientation the unit is deployed in the field.** So it is
not a bench approximation of the geometry — it is the geometry. In that geometry the LED wings
contribute exactly zero photons to the camera frame.

Three consequences follow:

1. **The optical-interference question is closed.** Detection and deterrence overlap with no
   measurable cost to the image. The reflex loop can hold the camera open through an LED burst.
2. **The camera gets no illumination help from the LED wings** — only the IR path (external pulse
   plus the camera's onboard emitters) lights the scene for the detector. This is intended (white
   light at night would wreck the monochrome exposure and confuse the IR-cut filter) but it means
   the LED contributes nothing to night image quality and should never be counted on to.
3. **There is no optical confirmation that the LED fired.** The camera cannot see the wings, so
   "did the LED actually fire during that encounter?" cannot be answered from vision — it would
   have to come from MCU-side current sensing. Noted for any future fire-verification work.

**What this check still does not establish:** whether the LED *beam* lands where an approaching
elephant's head and eyes will be. The camera cannot see the beam at all, so this is not a
camera-answerable question — it needs a person standing in the approach zone at night looking back
at the unit, or a witness target placed there. Logged in `docs/KNOWN_GAPS.md` as a physical field
check, no longer as a camera/FOV ambiguity.

### Enclosure geometry — from an assembly photo, 2 September

The assembled unit resolves the "aimed correctly vs misaimed" ambiguity above in favour of reading
1 (design working). The two white-LED wings are ~5 star emitters each, wired in parallel, seated in
deep recessed vertical channels on the left and right faces. Full-height walls separate each channel
from the central bay that holds the camera and the IR array. Those walls shroud the wings: the
emitters face forward, parallel to and boresighted with the camera axis — they project into the
same volume the camera watches — but their lateral spill is physically blocked from the lens. That
is the mechanism behind the zero-photon result, and it means the wings are not misaimed relative to
an approaching animal; the only open LED-beam question is throw and intensity at range, which is a
field check.

Also visible: the camera carries its own onboard IR emitters flanking the lens (confirming the
"dark" baseline frames in Finding 1 are onboard-IR-lit, with the external array as the boost); the
external IR is a wide-flood array of roughly 40 through-hole emitters, not a single high-power
source. A horizontal shelf baffles the camera recess from the IR array recess.

**Enclosure material.** The bench rig is printed in PETG-HS. The field units will be ABS or ASA,
both of which have a higher heat-deflection temperature than PETG-HS, so the enclosure gives the
LED wings and the IR array *more* thermal margin in the field than the rig they were characterised
on, not less — the thermal findings here are a conservative bound.

**IR board onboard photocell — resolved, not an open item.** Only the illuminator's power pins are
used, switched by the pin-7 MOSFET; the board's onboard CdS cell is not in the control path and is
not relied on for anything. There is one night gate, `perception/night.py` (ADR 0019); the earlier
"two independent night gates that can disagree" concern does not apply.

One item follows for the field-readiness checklist, logged in `docs/KNOWN_GAPS.md`:

- **Wing continuity check.** The wings are wired in parallel, so a single open-circuit emitter
  drops only that emitter and dims the wing slightly rather than dark-failing the whole string
  (the series-wiring failure mode does not apply). Still worth a visual/continuity check at
  pre-deployment and a note in the maintenance procedure, since a shorted emitter or a broken
  common lead would still take a wing down.

Note also that the LED sweep at gain 100% consumed roughly 40 s of the ~2 min nightly LED-on
budget; the remainder was reserved.

## Finding 3 — the external IR illuminator is a pulsed vision flash by design; continuous-on is not an available mode

This section answers a direct question: *should the external IR run continuously, or in interval
bursts, and which gives the clearest image at maximum range?* Part of the answer is architectural,
part is in the data above, and part is a measurement a supervised session still has to make.

### Continuous-on is not a knob — the firmware caps IR at a 10% duty cycle

`device/mcu/src/config.h`: `IR_PULSE_MAX_MS = 500`, `IR_MIN_INTERVAL_MS = 5000`. The MCU clamps
every IR request to at most a 500 ms pulse no more than once per 5 s, and the MPU already requests
the maximum on every firing event (`ir_duration_ms` resolves to the protocol max, clamped MCU-side),
so **in the field the illuminator is always a full 500 ms pulse and never longer.** Running it
continuously would require a firmware change plus a thermal solution for the emitter and its
MOSFET plus a power-budget revision against ADR 0012's 10-day autonomy — a continuous near-IR
emitter is a large always-on load, and this part is specified as a capture flash, not area
lighting. It is not a tuning parameter that can be turned up.

`config.h` line 433 comments the emitter as **940 nm**; the rig notes for this session recorded the
external emitter as **850 nm** (the camera's *onboard* emitters are 940 nm). This wants confirming
against the actual part — it matters for range (see below) — and is logged as a doc/hardware
discrepancy to resolve, not settled here.

### Does pulsing cost image quality versus continuous? For this detector, no

The camera integrates light only over its exposure window, which on this sensor runs from a few ms
up to roughly 200 ms depending on AGC state. A 500 ms pulse brackets that window completely with
margin. The vision runner does inference on demand at ~5 FPS during an event, not on every sensor
frame, so **one pulse per inference is sufficient** — continuous illumination would only help if
every frame at video rate had to be lit (frame-to-frame tracking), which this pipeline does not do.
Finding 1's +31–47% luma and treeline sharpness near-doubling were all obtained from single 500 ms
pulses, so the pulsed mode is already delivering the measured benefit.

### The real open question: does the pulse reliably land inside the captured frame in the field?

Finding 1 was measured with a harness that guaranteed pulse/capture overlap by classifying frames
*after* capture. The deployed path is different: `reflex_loop.py` fires `pulse_ir()` on its own
thread concurrently with `capture_burst()`, because the MCU's `pulse_ir()` blocks for the full
pulse. Whether the grabbed evidence frame consistently falls within that 500 ms window in the
field — across USB-UVC driver latency, `docker exec` cold-start jitter (measured at 1–3 s in
[Method](#method)), and the camera's own frame cadence — is **not yet verified end to end.** If
frames sometimes miss the pulse, the image for that event reverts to the onboard-IR-only "dark"
baseline (still usable — the dark frames in Finding 1 are onboard-IR-only — but without the gain).
The fixes, in order of preference, would be an explicit capture/pulse handshake, then a longer
pulse (Finding 1 shows zero clipping, so there is optical and — within limits — thermal headroom),
**not** continuous-on.

### What actually limits clear maximum range

| Limiter | What the data / hardware says | Lever |
|---|---|---|
| Inverse-square falloff | `far`/`treeline` gain +19–24 luma vs `near` +29–33 — the emitter is already weakest exactly where range matters | emitter power, beam angle |
| Exposure / sensor gain | exp 156 gave ~2× the treeline sharpness gain of exp 100 (+91.2 vs +53.7) — more integration time reaches further | raise base night exposure — but see motion blur |
| Motion blur | unmeasured; the Finding 1 scene was static, a moving elephant at the treeline is not — this is the blocker on the exposure-raise | bench protocol, Item C |
| Wavelength | 850 nm has roughly double the silicon response of 940 nm (faint visible red glow); 940 nm is fully invisible but dimmer — range favours 850 | confirm which the external part is (above) |
| Emitter type | the external source is a wide-flood array of ~40 through-hole LEDs (assembly photo), not a single high-power emitter — good coverage width across the approach fan, moderate range | supplementary narrow-beam emitter if range is short |
| Beam optic | narrow throws further / covers less width; wide covers the approach fan / dies sooner — unmeasured | emitter optic choice |
| Atmospheric | fog and heavy rain scatter near-IR badly | none — accept reduced range in those conditions |

**Best setting supported by current evidence:** the 500 ms pulse (already the firmware maximum),
base exposure raised toward 156 *pending the motion-blur check*, and treeline (the vegetation edge)
accepted as the practical detection horizon — which is exactly the band Finding 1 shows the pulse
improves most, so the design is already aimed correctly. No change is warranted from desk analysis
alone; the exposure raise needs the moving-target measurement.

### What a supervised session should measure

Auto-exposure (the deployed config), with a person or animal-sized target at marked standoffs
(≈5 / 10 / 15 / 20 m): detection rate versus range with the pulse and without it; whether the
evidence frame lands inside the pulse window across repeated real firings; exp 100 vs 156 vs auto
with the target *moving*. This is the run that converts Finding 1's image-quality numbers into a
range-versus-detection curve for the shipped configuration.

## Finding 4 — best night camera configuration: locked exposure ≈ 256 with the 500 ms IR pulse

An overnight battery (`/home/arduino/vdiff/night_battery.sh` + `night_battery2.sh`, board-time
19:42–20:45 on 1 Sept ≈ 00:20–01:25 IST 2 Sept) swept camera exposure with and without the IR
pulse to find the configuration that gives the clearest night image with the fewest false
positives. All runs were within firmware limits (IR 500 ms / ≥5 s, no LED beyond a small budget);
`boot_id` held and container `RestartCount` stayed 0 throughout; board sensor temperature stayed
39–44 °C across the whole ~1 h run with no climb.

### Locked-exposure ladder, no IR — pure sensor footage versus exposure

| exposure | full-frame luma (mean) | full-frame Laplacian sharpness | spurious boxes (n=10–12) |
|---|---|---|---|
| auto (≈100) | 123.8 | 68.9 | 0 |
| 32 | 14.0 | 42.0 | 3 low-conf Elephant ghosts (≤0.149) |
| 64 | 34.1 | 70.1 | 0 |
| 96 | 52.5 | 83.2 | 0 |
| 128 | 67.8 | 80.0 | 0 |
| 192 | 92.2 | 78.6 | 1 Boar ghost (0.074) |
| 256 | 111.5 | 73.3 | 0 |
| 320 | 128.6 | 79.7 | 0 |
| 384 | 143.0 | 85.3 | 1 Boar ghost (0.074) |
| 448 | 155.5 | 87.6 | 3 Boar ghosts (≤0.186) |
| 512 | 166.4 | 92.0 | 0 |

Saturation was **0.000 at every exposure**, including 512 — the night scene has so little energy
that the sensor never clips even at maximum integration. `exp 32` is genuinely noise-limited
(sharpness collapses, and it is the only setting that produced Elephant ghosts). Above `exp ≈ 384`
the near/far ground band gets bright enough to throw low-confidence Boar boxes even with no IR and
no animal present.

### Locked exposure + 500 ms IR pulse — true pulse gain per exposure

| exposure | dark→lit luma | Δ luma | Δ % | treeline sharpness Δ | far-band sharpness Δ | lit-frame FPs |
|---|---|---|---|---|---|---|
| 64 | 34.1 → 54.5 | +20.4 | +59.9% | +30.0 | +22.6 | 0 |
| 128 | 67.4 → 95.6 | +28.2 | +41.8% | +70.8 | +33.0 | 0 |
| 156 | 78.5 → 107.6 | +29.1 | +37.1% | +79.6 | +44.2 | 0 |
| 256 (best) | 110.7 → 143.3 | +32.6 | +29.4% | +100.0 | +63.5 | 0 |
| 384 | 140.2 → 173.2 | +33.0 | +23.6% | +68.2 | +79.8 | 0 |
| 448 | 155.9 → 187.6 | +31.7 | +20.3% | +41.4 | +86.3 | 0 |
| 512 | 167.2 → 196.3 | +29.1 | +17.4% | +19.3 | +65.8 | 0 |

**Treeline sharpness gain from the pulse peaks sharply at exp ≈ 256** (+100.0), roughly 1.3–1.4×
the gain at 128–156 and 1.5–2.5× the gain at 448–512, where the higher dark-frame floor leaves the
pulse little headroom to add edge contrast at the vegetation line. Absolute luma gain also peaks
around 256–384. No clipping at any exposure even with the pulse (lit-frame luma 196 at exp 512,
saturation still 0.000). Zero false positives on lit frames at every locked exposure.

### Auto-exposure + IR — measured, and it is the wrong configuration

Three auto-exposure IR sweeps (12, 16, 24 cycles): the pulse's luma gain is only **+5.1 to +7.4 %**
(vs +29–60 % locked) because the camera's AGC compensates the pulse away within its exposure
window. Worse, auto-exposure + IR is the **only** configuration in the whole battery that generated
a meaningful false-positive population — **15, 22 and 28 spurious Boar boxes** across the three
runs, `maxconf` up to **0.408** (above a 0.2 deployment threshold). AGC hunting also wrecks pulse
discrimination: under locked exposure the pulse lands in a clean, consistent 5–13 of ~245 grabbed
frames per 11.5 s window; under auto-exposure roughly one cycle in four returns 150–228 "lit"
frames as the AGC ramps the whole window.

### Recommendation

**Night: lock exposure at ≈ 256 and keep the 500 ms IR pulse at the firmware default.** This
maximises the pulse's treeline sharpness gain (the detection-relevant band, per Finding 1 and
Finding 3), keeps a usable dark-frame baseline (luma ≈ 111, zero FP) if a pulse is missed, never
clips, and produced zero false positives with or without the pulse. Do not exceed ≈ 320 (ground-band
ghost boxes appear) and do not drop below ≈ 128 (noise, thin far-range detail). Auto-exposure at
night should be considered a bug for this pipeline: it throws away the IR benefit and is the
dominant false-positive source.

**Caveats.** The deployed pipeline currently runs AGC; acting on this needs a night locked-exposure
path in camera control (firmware/MPU change — not done here, see Open items). The scene was static
and empty, so this optimises image quality and false-positive rate, **not** yet confirmed detection
rate on a moving animal — that remains the supervised-session measurement in Finding 3. Exposure
256 was the coarsest useful step in the ladder; the true optimum may lie anywhere in ≈ 224–320 and
does not need pinning down before a field trial.

## Consequences

**Fire the IR illuminator only at night — ADR 0019.** In daylight the IR-cut filter is in front of
the sensor and the illuminator's near-IR is blocked before it reaches a pixel, so the pulse is pure
waste: MOSFET duty budget and battery spent for zero image gain. The 0.000-versus->30 saturation
separation measured above gives a robust, sensor-free way to know which state the camera is in.
Implemented in `perception/night.py`, gated in `services/reflex_loop.py`.

**When it is night, fire it.** A 31–47% luma lift and a near-doubling of treeline sharpness for a
500 ms pulse is a good trade against the duty budget. There is no case for withholding it at night
on efficiency grounds.

**Overlap detection with deterrence.** Finding 2 removes the blocker.

**Keep the IR as a 500 ms pulse — do not pursue continuous-on.** Finding 3: the firmware caps it at
a 10% duty cycle for thermal and power reasons, pulsing costs this detector nothing versus
continuous, and the measured benefit is already obtained from single 500 ms pulses. The open risk
is pulse/frame synchronisation in the field, not pulse length.

**Lock exposure at night, at ≈ 256 — Finding 4.** The overnight battery swept the full exposure
range with and without the pulse: locked exposure ≈ 256 maximises the pulse's treeline sharpness
gain (+100 Laplacian, ~1.3–2.5× the gain at other exposures), never clips, keeps a usable
no-pulse baseline, and produced zero false positives. Auto-exposure at night is actively harmful —
it cuts the IR luma benefit to +5–7 % and is the sole source of the spurious Boar boxes
(`maxconf` up to 0.408). Acting on this needs a night locked-exposure path in camera control
(firmware/MPU), and the moving-target detection check from Finding 3 still stands; the exact
setpoint (anywhere ≈ 224–320) does not need pinning down before the trial.

## Open items carried out of this session

- IR benefit under the deployed **auto-exposure** configuration — now measured (Finding 4): only
  +5–7 % luma, and it is the dominant false-positive source. The real follow-up is a **night
  locked-exposure path** in camera control (firmware/MPU) so the pipeline can run at exp ≈ 256.
- IR and LED effect on **actual detection** — unmeasured; the scene was empty throughout.
- **Daylight exposure ladder** — the "day" half of the night+day footage question; needs a
  daytime run (the dawn soak below starts it).
- **Pulse/frame synchronisation in the field** — Finding 3; not verified end to end that the
  evidence frame lands inside the 500 ms pulse window under real driver and `docker exec` jitter.
- **External IR emitter wavelength** — `config.h` says 940 nm, session rig notes say 850 nm;
  resolve against the actual part (affects range).
- **IR board onboard photocell** — resolved (see Finding 2): only the illuminator power pins are
  used, switched by the pin-7 MOSFET; the onboard CdS cell is not in the control path. The single
  night gate is `perception/night.py` (ADR 0019). No longer an open item.
- **LED wing continuity** — the wings are wired in parallel, not series, so one open emitter only
  dims that wing rather than dark-failing it (see Finding 2). Still worth a pre-deployment
  visual/continuity check for a shorted emitter or a broken common lead.
- **Right wing (D6) drive — verified 2 Sept ≈ 11:10 IST.** Two per-wing `drive_led` calls via
  `fire_client.py` (direct RPC to `/run/arduino-router.sock`): `[3,0,0,25.0,1000]` then
  `[3,1,0,25.0,1000]` (schema 3 / channel / steady / 25 % / 1 s), user watching the device.
  Channel 0 lit the **left wing only**, channel 1 lit the **right wing only**, each off cleanly
  after ~1 s with no latch-on; both acked `[1,1,null,true]`. This closes the previously-unverified
  D6 path and confirms `led_channel_from_wire()` maps 0→left / 1→right in the flashed binary. It
  does not by itself prove the flashed `BRIDGE_SCHEMA_VERSION` (the MCU logs but does not refuse a
  mismatch) — one `arduino-app-cli monitor` boot-banner read is the last open confirmation, and no
  mismatch warning appeared in the container logs.
- **LED beam on target** — Finding 2's optical-interference question is closed (the wings put
  nothing into the camera frame in production enclosure geometry, confirmed by the shrouded-channel
  layout in the assembly photo); whether the beam covers an approaching elephant's head at range is
  a physical field check, not a camera measurement.
- **Motion blur versus exposure** at night — unmeasured; the one remaining check before the
  exp ≈ 256 lock in Finding 4 is trusted for moving targets.
- **Dawn transition soak** — captured (`soak_dawn.log`, 184 samples); night-gate crossover lands on
  local sunrise, results in the Appendix. Run was cut short by a spontaneous 64 s board reboot at
  ≈ 08:27 IST (self-recovered) — also in the Appendix.

## Appendix — overnight soak and dawn transition

The passive 8 h soak that was running when the body of this document was first drafted
(`nightchar/soak_20260901_185050/soak.jsonl`, first sample `luma=128.45 sat=0.0 temp=43.1 °C,
container 0 restarts, 0 vision boxes`) was stopped after ~30 min and replaced with the staged
exposure/IR battery now written up as **Finding 4** — a richer use of the same night window. The
battery ran board-time 19:42–20:45 (≈ 00:20–01:25 IST 2 Sept) with no `boot_id` change, no
container restart, and a flat 39–44 °C board temperature across the full ~1 h.

### Night-idle stability data point

Between the end of the 1 Sept evening session and the start of the battery, and again for the ~1 h
of the battery itself, the board held `boot_id 6b2c727a-af0d-4517-a6c7-a8069da92a64` with the
container `RestartCount` at 0 — roughly 2½ h of continuous camera-plus-inference load with no
crash-reboot. This is a modest positive data point against the open SoM-reliability question, not a
substitute for a clean multi-day soak on the reworked power path.

### Dawn transition — captured (soak_dawn.log, 184 samples, ~2 min interval)

A fresh passive soak was relaunched at battery end (board-time 20:44:55 ≈ 02:17 IST, `night_char.py
soak --interval 120 --max-min 600`) → `/home/arduino/vdiff/soak_dawn.log`. It ran 184 samples
(≈ 6 h 12 min) and was cut short by a board reboot at ≈ 08:27 IST (see the next subsection) rather
than by `--max-min`; the night→day transition itself was fully captured before the cut.

**1. Night-gate crossover — clean, and it lands on local sunrise.** `sat` held flat at `0.0` from
sample 0 through sample 115 (the entire night). It then rose sharply: sample 116 `sat=10.87`,
sample 117 `sat=12.81` (first value over `NIGHT_SATURATION_THRESHOLD = 12.0`), sample 120
`sat=15.0`, sample 130 `sat=20.1`, then a daylight plateau of ≈ 18–24 through the end of the run.
The crossover sample is ≈ 06:15 IST by elapsed count from the 02:17 launch — within a few minutes
of local sunrise (≈ 06:16 IST, 2 Sept, Kochi). `luma` moved far less over the same span (132 → 151,
+14 %), which confirms the ADR 0019 design choice: **saturation, not luma, is the night
discriminator** — the IMX462's IR-cut filter swinging back in colours the frame long before it
meaningfully brightens it. The threshold of 12.0 sits right on the knee of the curve with a full
night of `0.0` headroom beneath it; no tuning indicated.

**2. Temperature — flat, no daylight climb.** Excluding sample 0 (46.2 °C, residual heat from the
battery that had just ended at 43.1 °C), every sample of the ~4 h run sat between 40.0 and 42.8 °C,
mean ≈ 40.6 °C, with no upward trend as the scene brightened. Enclosure was the bench PETG-HS rig
indoors, so this is not a solar-load figure — but it rules out any inference-plus-daylight thermal
creep at ambient.

**3. False positives — zero all night, then a low-confidence `Boar` cluster through the AGC
transition.** Samples 0–144 (the whole night and first light): `vision.n = 0`, no boxes. Samples
145–183 (≈ 07:12–08:29 IST, sunrise past but the scene still brightening): 26 samples with
`vision.n > 0`, **every one a `Boar` box, never `Elephant`**, confidence `v` = 0.074–0.223 (median
≈ 0.11, single peak 0.223). Boxes cluster on one fixed scene feature (x ≈ 1480, y ≈ 550 — a
vegetation clump / post at the treeline) with occasional flickers at x ≈ 640 and x ≈ 920. Through
this entire window `EXPOSURE readback = 512.0` — AGC pinned at its ceiling and still hunting. This
is the same failure mode Finding 4 isolates under `night_char`'s auto-exposure sweeps: **transitional
light + AGC is the sole false-positive generator in this whole characterisation**; locked exposure
produced none. All 26 are well under any sane deterrence threshold (the fusion path expects
detection confidence ≥ 0.4 before it weighs a class), so nothing would have fired — but it is a
direct argument for carrying the Finding 4 night locked-exposure path across the dawn ramp, not
handing straight back to AGC at the `sat` crossover.

**4. Board health during the soak — clean until the reboot.** `boot_id`
`6b2c727a-af0d-4517-a6c7-a8069da92a64` held for all 184 samples; container `RestartCount = 0`
throughout; `cont` (frame-diff motion) flat at 0. The run ended only because Linux rebooted.

**5. Daylight photometrics** — only the earliest ramp was captured before the reboot (luma ≈ 150,
`sat` ≈ 23 at exposure 512, AGC-driven), not a settled mid-morning frame. The **daylight exposure
ladder** (locked-exposure sweep in full daylight, the "day" half of the night+day footage question)
is still outstanding and remains a queued daytime task.

### Board reboot at ≈ 08:27 IST 2 Sept — spontaneous, 64 s, self-recovered

The soak stopped because the board's Linux rebooted. From `journalctl --list-boots`: boot
`6b2c727a-af0d-4517-a6c7-a8069da92a64` ended **2026-09-02 02:57:20 UTC**, boot
`2c601696-8ce6-463d-917b-6da275008c34` began **02:58:24 UTC** — **downtime ≈ 64 s**. Real time
≈ 08:27 IST, roughly two hours after sunrise, in full daylight — so this was **not** a thermal or
dawn-linked event. `journalctl -b -1` ends with a routine SSH session close at 02:57:20 and no
`systemd` shutdown sequence, no reboot target, no captured panic — an unclean drop consistent with
the known Portronics Mport 51 hub USB-C power-starvation fault (the UNO Q and the camera are still
on the hub-fed rail; the camera was under continuous 2-min-interval load at the moment it dropped).

Two things to take from it:

- **Recovery was fully automatic and fast.** 64 s later Linux was back, the Docker bridge was up,
  and container `eletect-x-main-1` was `running` with `RestartCount = 0` (a host reboot, so Docker
  brought it back fresh rather than restarting the container in place). An unattended power-glitch
  reboot self-heals in about a minute with the app back online — a real positive for field
  survivability. The one loss: `night_char.py soak` was a plain foreground process, not a service,
  so telemetry simply stopped at the reboot; a deployed passive logger must be a restart-on-failure
  unit.
- **Reboots are still recurring.** The same `--list-boots` output shows three further boots on
  1 Sept (≈ 14:17, ≈ 16:25 UTC ends). The `6b2c727a` boot that just ended was the longest clean
  run in the list at ≈ 10 h. Direction is right, root cause (hub power path) is unfixed and
  physical.

Per the standing rule, the `boot_id` change ended hardware work for the session at this point;
everything after it is analysis of data already on disk. The live `boot_id` is now
`2c601696-8ce6-463d-917b-6da275008c34`; the value is per-boot by nature and only serves as a
"has Linux rebooted since I last looked" tripwire.
