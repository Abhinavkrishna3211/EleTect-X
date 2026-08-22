# Seismic footfall classifier — first trained model (proof of concept)

Edge Impulse project **1094084** (`EleTect-X-Seismic`). Project ID only is recorded here; the API
key is not in the repo and must be supplied through `EI_API_KEY` at run time.

**Read the caveats section before quoting the accuracy number anywhere.** This is a genuine model
trained on genuine hardware captures, and it is also a 12-event proof of concept. Both halves of
that sentence have to travel together.

## Dataset

`bench_windows_20260814_15.json` holds the **12 real 512-sample geophone windows** captured during
the 14/15 Aug bench stomp sessions (SM-24 → INA333 → ADS1115, one person stomping near one geophone
on one bench). Values are raw volts, exactly as logged. Each event carries its source log, capture
timestamp, STA/LTA trigger ratio and trigger index, and a sha256 of its own values.

The raw session logs live in `scripts/bench-logs/`, which is **gitignored** — hence this artifact.
`scripts/edge_impulse_upload_seismic.py` reads the logs when present and falls back to this file
otherwise, and the two paths were verified to produce byte-identical samples, so the dataset behind
the number below is reproducible from a fresh clone.

Each event is split into two honestly-labeled segments, no synthesis anywhere:

| Label | Segment | Length | Why it is real |
|---|---|---|---|
| `quiet` | first 128 samples | 512 ms | Pre-event ambient. Every logged trigger has `idx=511`, so the transient is always at the last sample and never intrudes here. |
| `footfall` | last 64 samples up to the trigger | 256 ms | The actual captured stomp transient. |

24 samples total, split by event so no event appears on both sides: **9 events (18 samples)
training, 3 events (6 samples) testing.**

## Impulse

- **Input** (block 1): time-series, 1 axis `geophone_v`, 250 Hz declared, 256 ms window, 256 ms
  stride, zero-pad on. 256 ms is exactly the footfall segment length, so no positive example is
  padded; a non-overlapping stride splits each 512 ms quiet segment into two windows rather than
  inflating the count with overlapping ones. Yields **27 training windows** (9 footfall, 18 quiet)
  and **9 testing windows** (3 footfall, 6 quiet).
- **DSP** (block 2): spectral analysis. Two parameters were moved off their defaults, both
  disclosed here because they were chosen, not inherited:
  - `spectral-power-edges = 5, 10, 20, 40, 80` Hz. The stock `0.1–5` Hz edges are accelerometer
    defaults and put every bin below the SM-24's 10 Hz natural frequency; 80 Hz stays under the
    125 Hz Nyquist of the declared rate.
  - `scale-axes = 1000`, i.e. volts → millivolts. A pure unit change, not a tuning knob — see the
    convergence note below for why it was needed.
  - `filter-type = none`, `fft-length = 16` (defaults, unchanged).
- **Learn** (block 3): Keras classification over `quiet`/`footfall`. 200 training cycles, learning
  rate 0.005, 20% validation split, automatic class weights (the windowing leaves a 2:1
  quiet:footfall imbalance).

## Result

Held-out test set, run as an Edge Impulse model-testing job over the 3 testing events the model
never saw in any form:

**9 / 9 windows classified correctly — 100% accuracy, 0 uncertain.** Per-window confidence in the
true class ranged 0.9455 to 1.0000 against a 0.6 minimum-confidence threshold. Confusion matrix is
diagonal: footfall 3/3, quiet 6/6.

The classes turn out to be trivially separable at this scale, which is worth stating plainly rather
than dressing up: measured directly from the committed windows, quiet RMS averages 1.34e-4 V
(max 1.89e-4) and footfall RMS averages 2.93e-3 V (min 2.29e-3) — a 12× gap with **zero overlap**
between the two sets. A single RMS threshold would separate this dataset perfectly. The trained
model is not doing anything a judge should assume is subtle.

## Caveats — required whenever this number is quoted

1. **n = 12 events.** The test set is **3 events / 6 samples / 9 windows**. Accuracy off 9 windows
   has ~11% granularity: one misclassified window would read as 89%.
2. **Not independently sampled.** The `quiet` and `footfall` segments come from the *same* 12
   recordings, so the two classes share their recording conditions exactly.
3. **One person, one geophone, one bench, two sessions.** No elephants, no field conditions, no
   coupling variation, no negatives other than each recording's own pre-event ambient. Nothing here
   establishes behaviour against rain, vehicles, cattle, or distance.
4. **Sample rate is declared, not measured.** 250 Hz nominal was uploaded; `docs/KNOWN_GAPS.md`
   measured 226.98 Hz on a lean field-flag build. This scales the frequency axis of the DSP block
   only — it does not touch the sample values or the accuracy figure, but the spectral edges are
   nominal-Hz edges.
5. **Not deployed.** This model does not run on the MCU and does not replace
   `footfall_features.cpp`'s placeholder `x²/(x²+c²)` probability. Nothing in the field path uses it
   yet.

Correct framing for a report table: *proof-of-concept classifier trained on real bench-captured
geophone data, n=12 events, 100% on a 3-event held-out test set; not field-validated.*

## Convergence note

The first training run did **not** converge — loss sat at 0.6925 (= ln 2, the model emitting 50/50)
for all 100 epochs, with a meaningless `accuracy: 1.0000` beside it and an sklearn
`UndefinedMetricWarning: Only one class is present in y_true` from a validation split that happened
to land single-class. That was diagnosed rather than accepted: the local RMS measurement above
proved the data is perfectly separable, so the failure was numerical, not evidentiary — spectral
features of order 1e-4 give a dense network vanishing gradients. Rescaling volts to millivolts
(`scale-axes = 1000`) and retraining at lr 0.005 for 200 cycles produced a normal learning curve
(epoch 1 loss 3.97 / acc 0.43, converged by ~epoch 28).

## Reproducing

```
export EI_API_KEY=ei_...          # project 1094084 API key, not stored in this repo
export EI_PROJECT_ID=1094084
python scripts/edge_impulse_upload_seismic.py
```
