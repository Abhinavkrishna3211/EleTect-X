# Acoustic classifier — four-class model, trained on real public + field-captured data

> **Looking for the walkthrough?** [`TUTORIAL.md`](TUTORIAL.md) is the step-by-step version —
> empty Edge Impulse project through to a model registered on the board, written for someone
> reproducing this from scratch. This file is the working record: what was tried, what was
> measured, and what was rejected. The tutorial is narrative; this is evidence.

## Which Edge Impulse project is production

**Production is project 1110036 (`ETX-Test`), impulse 19, deploy v7** — the PANNs Cnn10 transfer
model. Enterprise account; project ID only is recorded here, the API key is not in the repo and
must be supplied through `EI_API_KEY` at run time.

The name is misleading and the history is worth stating once, because two projects appear all over
this file and the older one is still named as production in places that have not caught up.

**1109511 (`ETX-A`)** was built on 2026-09-23 to *be* production: a clean rebuild from the frozen
group-aware split, deliberately kept off the experiment path so its history stayed clean. It did
not reach the bar. Its best MFE configuration missed the 80%-per-class target on every class, and
`chainsaw` sat in the high single digits to mid-twenties across six separate real training runs on
the identical post-audit dataset (four MFE, two MFCC) — see the 2026-09-22 and 2026-09-15 Result
sections below, and `ACOUSTIC_MODEL_REPORT.md` for why.

**1110036 (`ETX-Test`)** started as the scratch project for architecture/data/DSP/window sweeps.
The PANNs Cnn10 transfer impulse built there cleared the bar that 1109511 never did:

| | 1110036 impulse 19 |
|---|---|
| overall, 605 held-out clips | **92.6%** |
| ambient | 92.8% recall / 92.8% precision |
| chainsaw | 91.2% recall / 89.9% precision |
| elephant_call | 93.1% recall / 91.5% precision |
| gunshot | 92.6% recall / 93.4% precision |

So the roles swapped: the scratch project carries the model that works, and it is what ships. See
[ADR 0032](../../docs/decisions/0032-acoustic-production-project-is-1110036.md).

**The comparison is like-for-like, not a leakage artefact.** That is the first thing to check when
a scratch project outscores a carefully-built one by thirty points, and it was checked. 1110036 was
re-uploaded from the same frozen split: all 4,293 clips pushed with label **and** train/test
category driven by `harness/split.json` rather than by Studio's own 80/20, verified by API as an
exact filename-and-label match (training 3,688 / testing 605, 0 missing, 0 extra), and re-verified
against `ei_upload_ledger.json` at scoring time (605/605). The 92.6% above is measured over the
same 605 test clips the harness uses, so it is directly comparable to every other number in this
file. Full numbers: `harness/results_eim_impulse19.json`.

**Naming hazard:** the production project is literally called `ETX-Test`. Do not delete, reset or
overwrite it on the assumption that the name means what it says. `ETX-A` is the one that is now
dormant. Renaming 1110036 in Studio would make this safer and is worth doing.

(An earlier project, 1094275, was abandoned before any of this work and is never referenced again
in this document or in either script.)

**Status: trained, with real held-out numbers.** The numbers in the Result sections below are
copied verbatim from `edge_impulse_train_acoustic.py`'s `report_results()` output for each run —
nothing in this document is estimated, rounded from a different run, or averaged across classes.

Most of those sections predate the PANNs model and describe 1109511's MFE/MFCC lineage. They are
kept because they are the evidence for why that lineage was abandoned, **not** because they
describe what ships. In particular, the 2026-09-22 "Result — MFE vs MFCC x `autoClassWeights` on
the current dataset" section is 1109511's final trained state (Run E), and each of its four runs
left 1109511's live impulse in whatever state that run produced — Run E was a deliberate rebuild
back to the best-known config so the project was not left worse. That is now history: 1109511 is
not the deployed model and its numbers must not be quoted as production.

## Class scheme, and why it is four classes, not seven

The wire scheme is:

```
gunshot, chainsaw, elephant_call, ambient
```

`elephant_call` is the only one of these that feeds the deterrence (bandit) fusion decision
in `device/mpu/services/reflex_loop.py`; the rest are alert/detection-only. See
`docs/decisions/0024-acoustic-species-classification-deferred.md` and its same-day amendment
for the routing decision this model plugs into (Track B, a separate deferred change — this
document covers only the model).

### `boar_call` and `predator_call` were sourced, trained, and dropped

The amendment that authorized this work originally scoped **seven** classes, adding
`boar_call` and `predator_call` (lion + leopard + tiger lumped) to the five above. Both were
actually sourced (Freesound multi-query pulls, ESC-50 "pig" for boar, xeno-canto `Panthera`
and BBC Sound Effects for predator) and trained through the complete exploration described
below — data rebalancing, an `autoClassWeights` on/off A/B, a DSP A/B, an EON Tuner wide
search, a transfer-learning attempt, and the full `{3,4,6,8,10}` s window-length sweep. In
every one of those configurations, both classes stayed at or near the seven-class chance
floor (1/7 = 14.3%):

| window | `boar_call` recall | `predator_call` recall |
|---|--:|--:|
| 3.0 s | 2.6% | 10.7% |
| 4.0 s | 0.0% | 0.0% |
| 6.0 s | not trained — fell below the 150-clip data floor at this window length | 0.0% (n=3, test set collapsed) |
| 8.0 s | 0.0% | 0.0% |
| 10.0 s | 5.3% | 0.0% |

The EON Tuner's own best trial scored `boar_call` 18.4% and `predator_call` 0.0% across a
70-trial-budget search that explored MFE/MFCC/spectrogram DSP crossed with conv1d/conv2d
architectures — the platform's own automated search did no better. `autoClassWeights: True`
did lift both above chance on one dataset configuration (`boar_call` to 18.4%,
`predator_call` to 28.6%), but only by costing the two highest-stakes classes real recall
(`elephant_call` −16.5 points, `gunshot` −10.5 points) — see the `autoClassWeights` section
below for the full trade-off.

Per the project owner's explicit, pre-agreed fallback ("if boar and predator are working
very low, drop it after all possible fixes are explored"), both classes are **dropped from
the wire scheme entirely** — not folded into `ambient`, since `ambient` means background/
silence, not a mislabeled animal call, and folding would corrupt that class's meaning. The
device-side `AcousticClass` enum change this implies is a separate, deferred Track B edit;
this document and the two acoustic scripts are the only places the drop is applied. Every
fetcher, query table, and floor-handling special case for these two classes has been removed
from `scripts/edge_impulse_upload_acoustic.py` and `scripts/edge_impulse_train_acoustic.py`
rather than left in as dead code.

`boar_call`'s weak showing tracks a genuine data ceiling, not a code gap: its 12-query
Freesound search (`"wild boar"`, `"boar grunt"`, `"wild pig squeal"`, ...) against a 600-clip
cap only ever found 157 unique clips, plus 40 from ESC-50's "pig" category — 197 total,
nowhere near the other classes' final counts. `predator_call` never cleared the 150-clip
floor at all in the final configuration. xeno-canto was a hoped-for supplement for both but
returned zero clips — its v2 API is retired and v3 requires an account key this project does
not hold (confirmed live, not assumed).

### `vehicle` was retrained with real field data, then dropped (2026-09-14)

`vehicle` was part of the wire scheme from the start of this document and had its own
Freesound data widened on 2026-09-13 alongside `chainsaw` (see "Reading these numbers
honestly" below, in the pre-drop Result section this document used to lead with). At that
point `vehicle` looked like a genuine success story — held-out recall had jumped from 27.7%
to 55.6% — while `chainsaw` improved only modestly and the writeup at the time already
flagged, in prose, that "these two classes' Freesound-sourced audio — both sustained
mechanical/engine drones — sit close together in MFE feature space at this window length."

On 2026-09-14, 15 new real `chainsaw` clips and 10 new real `elephant_call` clips (laptop/
phone recordings, not Freesound) were added and the model retrained. `chainsaw` held-out
recall did not just fail to improve — it **collapsed to 0.0% (0/79)**. The training job's own
validation-time confusion matrix (not just the held-out split, which could in principle have
been an unlucky test draw) showed the same collapse during training: `chainsaw` recall was
1.7% (1/60) at validation time, with 33 of 60 `chainsaw` validation clips predicted `vehicle`.
Seeing the identical failure in both the training-time validation split and the independent
held-out test split is what confirmed this was a genuine, systematic class-boundary collision
between `chainsaw` and `vehicle` — not noise from one bad split. The new real clips did not
create this weakness; they pushed an already-documented latent one (see the prose warning
above, written the day before) into outright collapse. The bulk of both classes' data was,
and remained, Freesound-sourced sustained-engine-drone audio; the ~25 new laptop/phone clips
were a small fraction of either class's total.

Given the field-build deadline driving this work, the decision was to **drop `vehicle`
from the wire scheme rather than continue diagnosing the collision** — not fold it into
`ambient`, for the same reason `boar_call`/`predator_call` were not folded into `ambient`
above (`ambient` means background/silence, not a mislabeled vehicle). Dropping `vehicle` and
retraining recovered `chainsaw` to **55.7% (44/79) — its best score in this project's
history** (see the current Result section below for the full four-class numbers). All 517
`vehicle`-labeled samples (415 training + 102 testing) were deleted from Edge Impulse project
1109511 via the Studio API; the raw audio itself stays cached under
`ml/datasets/acoustic/raw/` (gitignored), so `vehicle` can be re-uploaded from cache without
re-fetching if the class is ever revived with a plan to actually separate it from `chainsaw`
(a different DSP/window, or audio sourced from something other than Freesound engine-drone
recordings). As with the boar/predator drop, every fetcher, query table, and constant
specific to `vehicle` has been removed from `scripts/edge_impulse_upload_acoustic.py` rather
than left in as dead code; `scripts/edge_impulse_train_acoustic.py` needed no functional
change since it already reads expected classes from the manifest rather than hard-coding
them.

## Dataset — the frozen split, as uploaded to project 1109511

> The dataset described here is the corpus both projects are trained and scored on. The
> *project* named below is 1109511, because this section was written when 1109511 was the
> designated production project; the same 3,688/605 split was later re-uploaded to 1110036
> by filename, which is what makes the two projects comparable. See ADR 0032.

Manifest schema `eletect-x/acoustic-clip-manifest/3`, `ml/acoustic/dataset_manifest.json`
(committed; records source, license, and sha256 for every clip the manifest currently
tracks — see the test-bucket note below for a case where this undercounts what is actually
in the project). Real counts, from that manifest, **after the 2026-09-15 chainsaw
data-quality audit and ambient-cap pullback** (see the two subsections immediately below —
this supersedes the 2026-09-14 all-four-classes-widening counts quoted in an earlier revision
of this table; see git history if those are needed):

| Class | Total | Train | Test | Primary sources (license as recorded per clip) |
|---|--:|--:|--:|---|
| `gunshot` | 577 | 382 | 195 | Mendeley `x48cwz364j` v3 + Freesound 19-query supplement, mostly CC0/CC BY |
| `ambient` | 762 | 610 | 152 | Mendeley `x48cwz364j` v3 background folder + ESC-50 nature categories (crickets/insects/chirping_birds/wind/frog/rain, CC BY-NC 3.0) + Freesound 11-query forest/jungle-ambience supplement |
| `chainsaw` | 227 | 178 | 49 | ESC-50 ESC-10 subset (CC BY) + Freesound 19-query supplement (`"power saw"` dropped 2026-09-15 — see below), mostly CC0 |
| `elephant_call` | 382 | 303 | 79 | `github.com/HiruDewmi/Audio-Classification-for-Elephant-Sounds` (**no license** — see Caveats) + Freesound 18-query supplement, mostly CC0/CC BY |

This table reports `dataset_manifest.json`'s own per-class counts, which — per the
"manifest is a floor, not the real count" note below — undercount what the live project
actually holds: the training runs in the Result section below report **1,775 training / 552
testing** clips read from project 1109511 at train time, larger than this table's 1,341/475
sum for the same reason documented since the first time this gap was noticed (the resumable
upload ledger accumulates clips across every historical run's differently-seeded sample; the
manifest keeps only the latest run's own selection). Field-captured XIAO and laptop/phone
clips from earlier revisions of this table are still present in the raw cache and in earlier
uploaded batches and contribute to that live-project total even though they no longer appear
in the manifest's latest per-class breakdown above. `vehicle` (dropped 2026-09-14, see the
class-scheme section above) stays out of the wire scheme. Every class clears the project's
own data floor (`CLIP_FLOOR = 150`) and is tagged `floor_status: trained` in the manifest.

**Superseded as of 2026-09-23: the live project now holds 3,688 training / 605 testing
clips.** The 1,775/552 figures below are accurate for the runs that recorded them and are
left as written, but they are no longer the current size of project 1109511. Every number in
the 2026-09-23 investigation is on the 3,688/605 data, and the 605 testing clips are the
canonical held-out set that all comparisons are scored against.

### Chainsaw data-quality audit — the `"power saw"` query dropped (2026-09-15)

The 2026-09-14 all-four-classes widening's own writeup (see the Result section below it, and
Caveat 5) flagged the `"power saw"` Freesound query — which alone contributed 138 of
`chainsaw`'s 321 Freesound clips at the time — as the leading, but unverified, suspect for
that widening's `chainsaw` collapse (55.7%→18.8%/13.9%). That audit was carried out: all 136
clips the query pulled were listened to. The finding is not what was guessed — the query does
not mostly return other power tools (circular saws, angle grinders); it mostly returns two
kinds of genuinely off-target audio that share the query term's ambiguity: synthesizer
"sawtooth waveform" demos (the tool/waveform sense of "saw") and generic factory/mechanical-
impact sound-effects-pack content, both cases where "power saw" over-matched Freesound's tag
search rather than the class label matching real chainsaw audio. `"power saw"` was removed
from `FREESOUND_QUERIES["chainsaw"]` and the remaining chainsaw query list widened from 13 to
19 real chainsaw-specific queries (`"chainsaw cutting wood"`, `"logging chainsaw"`, `"Stihl
chainsaw"`, `"Husqvarna chainsaw"`, `"motosierra"`, `"tronconneuse"`, and others) to replace
the lost volume with on-target audio instead. This is a genuine, verified data-quality fix,
not a guess carried forward unverified — see the Result section below for whether it actually
recovered `chainsaw`'s recall (it did not, cleanly — read that section before assuming this
fix worked).

### Ambient-cap pullback (2026-09-15)

The same all-four-classes widening grew `ambient` to 700 total clips specifically to test
whether more ambient volume would help (it did, but only under `autoClassWeights: False` —
see that Result section's honest read). Separately, `AMBIENT_CAP` had briefly been pushed
further, to 700 within the upload script's own per-run cap (not merely the manifest's `700`
row above), which combined with the ESC-50 nature supplement and the XIAO field clips to push
`ambient`'s live TRAIN split to roughly 750 — about 5x the thinnest trained class — at which
point, with `autoClassWeights` off, the model answered `ambient` for nearly every clip
regardless of true label. `AMBIENT_CAP` was pulled back to 200 (keeping the ESC-50 nature
supplement — genuinely different recording rigs — in full, cutting only the redundant
single-rig Mendeley share) so `ambient`'s volume advantage stays within roughly 2x the
trained species classes rather than 5x. A large negative class is still deliberately kept
as the main defence against a false-positive storm in the field; it just cannot be allowed to
dominate the softmax outright.

### `elephant_call` Freesound query widened 3→12, then retrained (2026-09-14)

After the `vehicle` drop retrain (below) showed `elephant_call` as the model's weakest class
at 37.0% held-out recall, `FREESOUND_QUERIES["elephant_call"]` in
`scripts/edge_impulse_upload_acoustic.py` was widened from 3 queries to 12 ("elephant rumble",
"elephant trumpet", "elephant call", "elephant roar", "elephant bellow", "elephant
vocalization", "elephant growl", "elephant scream", "wild elephant sound", "elephant herd",
"baby elephant", "elephant infrasound"). Real yield, per query, from a live Freesound search:
"elephant trumpet" (28 hits), "elephant roar" (11), "elephant growl" (9), "elephant scream"
(9), "elephant call" (6), "elephant rumble" (2), "elephant vocalization" (2), "wild elephant
sound" (3), "elephant bellow" (1); "elephant herd", "baby elephant", and "elephant infrasound"
returned 0 hits each. After deduping against the clips the original 3-query pull had already
found, this added **16 net-new clips** (49 unique Freesound clips total vs. 33 before) —
`elephant_call`'s total went from 394 to 410 (313→326 train, 81→84 test). xeno-canto still
contributes 0 clips (`gen:Elephas`, API v3 needs an account key that is not set). The retrain
against this larger pool did raise `elephant_call`'s held-out recall substantially (see the
Result section below), but total model accuracy barely moved and the gain traces mostly to
`ambient` and `chainsaw` losing votes to `elephant_call` rather than to a cleaner decision
boundary — read that section's honesty subsection before treating this as a fix.

### Why the manifest's per-class test count is a floor, not the real count

Because the resumable `uploaded.json` ledger only *adds* newly-selected clips and never
removes one a later run's reseeded sample no longer includes, a class's real EI-side train/
test bucket is the union of every historical run's selection, while the manifest only records
the *latest* run's sample. This has shown up repeatedly across this project's history at
varying scale — a 14-training/1-testing-clip gap before the 2026-09-13 chainsaw/vehicle
widening, a 10/32-clip gap for chainsaw/vehicle after it, a 1,487/476-vs-1,341/436 gap after
the 2026-09-14 `elephant_call` widening — and shows up again, largest yet, after the
2026-09-15 chainsaw audit and ambient-cap pullback: every training run in the current final
Result section below reports Edge Impulse reading **1,775 training / 552 testing** clips from
project 1109511, versus this section's own 1,341/475 manifest sum — a 434/117-clip gap. The
manifest's per-class counts are real and verified (they are exactly what the most recent
upload run selected and recorded), they simply undercount what the live project actually holds
after several historical runs' worth of accumulated clips. The Result sections below report
each `classify` job's own real per-class counts (which do match that run's own training-log
testing total), not the manifest's, since that is what the model was actually tested against.

### Normalization (all sources)

- **8000 Hz mono** — matches the INMP441 target rate and Mendeley's native rate (the lowest
  of all sources), so every other source is downsampled, never upsampled. Resampling uses
  `scipy.signal.resample_poly` (anti-aliased), not stdlib `audioop.ratecv` — `ratecv` has no
  real anti-alias filter, and decimating 44.1 kHz Freesound/ESC-50 audio at roughly 5.5:1
  without one folds high-frequency energy back down into exactly the low mel bands the MFE
  DSP block reads.
- **10.0 seconds per clip**, centre-cropped or zero-padded — the window-length sweep's
  winner; see that section below for why.
- XIAO ESP32S3 Sense field captures get an additional DC-offset removal step (the onboard
  PDM MEMS mic's raw output carries a DC bias that a plain resample does not fix).

## Impulse (locked configuration)

- **Input** (block 1): time-series, 1 axis, 8000 Hz, **10000 ms window, 10000 ms increase**
  (no overlap — one window per clip, so no window spans two clips or mixes a class label
  with padded-in silence from a shorter source clip).
- **DSP** (block 2): **MFE** (mel-filterbank energy), 40 filters / 256-point FFT — Edge
  Impulse's stock 8 kHz default, and separately measured against MFCC (see DSP A/B below).
  Frame length stays at the block default (0.02 s); frame stride is widened from the 0.01 s
  default to **0.020835 s** for this window length only, because Edge Impulse hard-caps
  feature generation at 500 frames per window and the 10 s window would otherwise compute
  ~499 frames (598 was measured to actually fail at 6 s) — `frame_stride_for_window()` in
  the training script widens the stride by the minimum amount needed, and only for windows
  that need it (3 s and 4 s keep the untouched 0.01 s default). This trades temporal
  resolution for headroom under the platform cap; it is a documented, deliberate
  trade-off, not a hidden one.
- **Learn** (block 3): Keras classification, from-scratch 2-layer 1D CNN —
  `conv1d(16) -> conv1d(32) -> dense(24)`, kernel size 3, 120 training cycles, learning rate
  0.001, batch size 32, **`autoClassWeights: False`**, spectrogram augmentation off,
  `minimumConfidenceRating: 0.1`, INT8 profiling on (`profileInt8: True`, matching the
  QRB2210 A53 Linux MPU deployment target).

  The block also carries `dropoutRate: 0.25/0.25/0.4`, and **that setting does nothing.**
  Dumping the Keras script Edge Impulse actually generates from this visual config shows no
  `Dropout` layer anywhere in it; the value is accepted by the API, echoed back on read, and
  never reaches the model. Confirmed by training two marker-verified expert-mode scripts that
  differ only in the presence of three `Dropout` layers. So every visual-mode run recorded
  below trained an unregularised network, whatever its stored config claims.

  **What the inert setting costs depends on the head, and is smaller than it first looked.**
  On Edge Impulse's internal validation slice the two scripts scored 61.25% / 0.579 macro F1
  without dropout and 63.96% / 0.616 with, which looked like a real +2.7. That slice is drawn
  from the training pool and is not group-aware, so it flatters regularisation; it is not a
  test set and should not be quoted as one. Re-scored on the canonical 605-clip test set,
  dropout on the stock `Flatten` head is worth +0.5 to +1.3 points — real, because Edge
  Impulse's training is deterministic and run-to-run variance is exactly zero, but minor.

  Once the head is replaced with global average pooling the sign reverses: 70.9% without
  dropout against 69.4% with. A 768-parameter head is already constrained enough that
  0.25/0.25/0.4 over-regularises it. The inert setting is a genuine Edge Impulse defect and it
  invalidated three experiment arms, but it was never the main cost — the `Flatten` head was.
  See [ACOUSTIC_MODEL_REPORT.md](ACOUSTIC_MODEL_REPORT.md) for the full accounting.

Every one of those choices was measured, not assumed — see Exploration history below.

## Exploration history (what was tried, what won, and why)

All of this ran against **1110036**, which was the scratch project at the time and is now
production (see "Which Edge Impulse project is production" at the top). So this history is the
deployed project's own history — the sweeps below are not a parallel track that was thrown away,
they are how the shipping model was arrived at. Every step is reproducible via the `--dsp`,
`--learn`, and `--clip-seconds` flags on `edge_impulse_train_acoustic.py`.

### Architecture search — closed, data-limited not capacity-limited

Three points were measured on the same (pre-final) dataset at a 4.0 s window:

| Architecture | Cycles | Held-out |
|---|--:|--:|
| 4-conv stack, dense-64 head, heavy spectrogram augmentation | — | ~26% argmax (near-random) — this was an earlier over-parameterized attempt that collapsed the majority class |
| 2-conv (16→32) + dense-24 | 120 | 46.4% (252/543) |
| 3-conv (24→48→64) + dense-32 | 250 | 45.2% (252/558) |

The larger net, wider head, and 2x training cycles bought nothing — the two curves sit on
top of each other and the train/held-out gap stayed ~4–5 points either way. That is a data
ceiling, not a capacity ceiling, so the smaller net was kept: identical accuracy, fewer INT8
parameters to profile and deploy. Architecture search closed here; every subsequent gain
came from the data, not the model.

### Data rebalancing — three iterations, real regressions along the way

Reported honestly because two of the three iterations were **regressions**, not just steps
toward the final config:

1. **Freesound gunshot supplement, no rebalancing** — added a 10-query Freesound pull for
   `gunshot` (Mendeley's own gunshot and ambient clips share one recording rig, so the model
   was keying on the rig's signature rather than the sound). Held-out total fell to 43.5%
   (269/618) — `gunshot` recall improved (+7 points) but `boar_call` and `chainsaw` collapsed
   to 2.6% and 4.4% because the uncapped `ambient` (940 clips) and `gunshot` (830 clips)
   swamped the thinner classes.
2. **Rebalance + XIAO field data folded in** (`GUNSHOT_TRAIN_CAP` 380→200,
   `FREESOUND_CAP["gunshot"]` 300→130, `AMBIENT_CAP` 700→200) — held-out total 41.3%
   (217/525), still below the original 46.4% baseline, but `elephant_call` jumped to 63.3%
   (real XIAO elephant-noise data helping directly) and `chainsaw`/`gunshot`/`vehicle` all
   improved. `boar_call` (2.6%) and `predator_call` (3.6%) stayed collapsed — this triggered
   the `autoClassWeights` A/B below.
3. This rebalanced-plus-XIAO configuration (with `autoClassWeights` locked `False`, see
   next section) is what carried forward into the DSP A/B, EON Tuner, transfer-learning
   attempt, and window sweep.

### `autoClassWeights` — measured both ways, locked OFF

Same uploaded data, same DSP/architecture, retrain-only comparison:

| Class | Weights OFF | Weights ON | Delta |
|---|--:|--:|--:|
| `elephant_call` | 63.3% | 46.8% | −16.5 |
| `gunshot` | 55.8% | 45.3% | −10.5 |
| `chainsaw` | 29.4% | 25.5% | −3.9 |
| `vehicle` | 38.3% | 36.2% | −2.1 |
| `ambient` | 30.7% | 29.7% | −1.0 |
| `boar_call` | 2.6% | 18.4% | +15.8 |
| `predator_call` | 3.6% | 28.6% | +25.0 |
| Total (micro) | 41.3% | 37.0% | −4.3 |

Turning class weighting on does lift `boar_call`/`predator_call` above the seven-class
chance floor — a real signal — but at the cost of the two highest-priority classes in the
deployed product: `gunshot` (P1 anti-poaching alert) loses 10.5 points and `elephant_call`
(alert **and** the sole acoustic input to the deterrence fusion decision) loses 16.5 points.
Weighted by the same elephant_call/gunshot/chainsaw priority average used for every other
decision in this document: 49.5% (weights off) vs. 39.2% (weights on). **Locked:
`autoClassWeights: False`.**

### DSP A/B — MFE vs MFCC, MFE wins decisively

`--dsp {mfe,mfcc}` on the identical rebalanced+XIAO dataset:

| Class | MFCC recall | MFE recall (locked) |
|---|--:|--:|
| `ambient` | 88.1% | 30.7% |
| `boar_call` | 0.0% | 2.6% |
| `chainsaw` | 11.8% | 29.4% |
| `elephant_call` | 55.7% | 63.3% |
| `gunshot` | 5.5% | 55.8% |
| `predator_call` | 0.0% | 3.6% |
| `vehicle` | 0.0% | 38.3% |
| **Total** | 28.4% (149/525) | 41.3% (217/525) |

Tie-breaker (elephant_call/gunshot/chainsaw weighted average): **MFCC 24.3% vs. MFE
49.5%** — more than 2x worse. The confusion matrix shows why: 164 of 181 `gunshot` clips
were predicted `ambient` under MFCC, which is also why `ambient`'s own recall looks inflated
(88.1%) — MFCC's cepstral truncation throws away exactly the transient/broadband energy
that separates a gunshot's percussive burst from background noise, which MFE's full
mel-band energy profile retains. This is expected: MFCC is a speech-tuned representation
(built to emphasize the smooth spectral-envelope shape that separates phonemes), applied
here to non-speech transient/impulsive sounds it was never designed for. **`--dsp` stays
defaulted to `mfe`.** Spectrogram was deliberately not added as a third variant — its
output bin count is not verified against the live API, and a wrong reshape-columns guess
risks a crash or silent misconfiguration for a block already expected to lose to MFE.

This comparison predates the chainsaw-audit/ambient-pullback dataset (project 1109511's current
1,775/552 4-class data) and was not re-verified against it until 2026-09-22 — see "Result — MFE
vs MFCC x `autoClassWeights` on the current dataset" below, which reconfirms the same verdict.

### EON Tuner — wide search, did not beat the hand-tuned config

Ran Edge Impulse's EON Tuner via its Enterprise API (`searchSpaceTemplate: audio_event`,
`targetDevice: arduino-unoq`, up to 70 trials across MFE/MFCC/spectrogram DSP crossed with
conv1d/conv2d architectures, INT8 optimization, 500 ms target latency). The search stopped
after 16 trials (the platform's own optimizer decided that was enough before entering full
optimization rounds). Best trial (`mfe-conv1d-934`): priority average 33.5%
(gunshot 52.5%, chainsaw 0.0%, vehicle 0.0%, elephant_call 48.1%, boar_call 18.4%,
predator_call 0.0%, ambient 8.9%) — well below the locked hand-tuned net's 49.5%. `chainsaw`
and `predator_call` scored exactly 0% in nearly every trial across the whole search space.
**Verdict: nothing to reproduce by hand — the locked from-scratch 2-conv net beat Edge
Impulse's own automated search.**

### EON Tuner — re-run on the current 4-class scheme (2026-09-15), still did not beat hand-tuning

The EON Tuner search above predates the `vehicle`/`boar_call`/`predator_call` drops and the
chainsaw data-quality audit, so it was re-run against project 1109511's current 4-class,
post-audit dataset (job `53782394`, `searchSpaceTemplate: audio_event`, `targetDevice:
arduino-unoq`) to check whether the narrower class scheme changed the conclusion. The search
ran 69.7 minutes and completed 10 trials, 5 of which returned metrics before the run stopped
itself. Best completed trial: int8 accuracy 56.52% (312/552 total), with `ambient` 52.6%,
`chainsaw` 2.1%, `elephant_call` 57.9%, `gunshot` 67.8%. This total is close to the range the
hand-tuned config's own runs land in (see the Result section below), but **the tuner's
`chainsaw` recall (2.1%) is far worse than any hand-tuned run achieves** — because, as
established in the earlier EON Tuner section above, **the tuner's search space varies only
the DSP block and the Keras architecture; it never varies `autoClassWeights`**, and every
trial in this run landed on the weights-off configuration this project already knows collapses
`chainsaw`. No trial was promoted with `set-tuner-primary-job` — nothing the tuner found beat
the manually-tuned, weights-on config on the metric this project actually cares about
(per-class recall on the minority classes, not total accuracy). **Verdict unchanged from the
7-class-era run: the tuner is not a substitute for hand-tuning `autoClassWeights` on this
dataset.**

### Transfer learning (`keras-transfer-kws`) — ruled out on a hard platform constraint

Attempted an A/B against all three confirmed-live pretrained KWS backbones
(`transfer_kws_mobilenetv1_a1_d100`, `transfer_kws_mobilenetv2_a35_d100`,
`transfer_kws_conv2d_tiny`; Syntiant NDP10x excluded — no hardware target for it). Every arm
was rejected identically: *"transfer learning for keyword spotting currently only works
with a window size of 1000ms"* — a hard, block-level Edge Impulse platform constraint, not
a per-backbone result. This project's window is far above 1000 ms because several classes
(a sustained chainsaw/engine whine, an elephant call, a running vehicle) need more than one
second of context to identify — they are not single-word "keyword" utterances the way KWS
transfer models assume. Forcing a 1 s window just to satisfy this block would have confounded
the comparison with an unrelated window-length change (1 s was never a window-sweep
candidate). **Not worked around — ruled out.** `TRANSFER_REQUIRED_WINDOW_MS` in the training
script fails this path fast, before wasting a feature-generation job, if anyone tries it
again at an incompatible window.

### Window-length sweep — all five candidates, no averaging

`{3.0, 4.0, 6.0, 8.0, 10.0}` seconds, each a full wipe → upload → train cycle against scratch
1110036 on the locked rebalanced+XIAO data, MFE DSP, `autoClassWeights` off, 2-conv net.
Picked by the elephant_call/gunshot/chainsaw priority average (the three highest-stakes
classes), never by raw total accuracy, since sample counts are not comparable across
candidates (re-cropping at a different window length changes how many non-overlapping
windows fit inside each raw source clip, so a class's real test-set size shifts with the
window — this is reported as observed below, not smoothed over).

| Window | Total good/bad | `ambient` | `boar_call` | `chainsaw` | `elephant_call` | `gunshot` | `predator_call` | `vehicle` | priority avg* |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|
| 3.0 s | 201/298 | 43.6% | 2.6% | 62.7% | 25.3% | 61.3% | 10.7% | 12.8% | **49.77%** |
| 4.0 s | 200/259 | 44.6% | 0.0% | 23.5% | 63.3% | 60.0% | 0.0% | 0.0% (n=7) | 48.93% |
| 6.0 s | 203/175 | 67.3% | not trained (below floor at this window) | 0.0% (n=14) | 55.6% | 52.5% | 0.0% (n=3) | 0.0% (n=7) | 36.03%† |
| 8.0 s | 233/292 | 46.5% | 0.0% | 39.2% | 39.2% | 67.4% | 0.0% | 27.7% | 48.60% |
| 10.0 s | 235/290 | 32.7% | 5.3% | 19.6% | 69.6% | 63.5% | 0.0% | 42.6% | **50.90%** |

\* elephant_call/gunshot/chainsaw simple average.
† 6.0 s excluded from serious contention: its `chainsaw` recall is measured on only 14 test
clips (vs. 51 at 3/4/8/10 s) and `boar_call` did not train at all at this window length —
longer windows mean fewer non-overlapping crops fit inside `boar_call`'s short raw source
clips, so the upload script's own data-floor logic pulled it below the training floor
entirely. This is a genuine, structural finding (window length and per-class data volume are
not independent), not an artifact of the frame-stride fix, but it makes 6.0 s unreliable to
compare against the other four.

**10.0 s wins** — highest priority average (50.90%) among the four reliable candidates, and
by a wide margin the best `elephant_call` recall (69.6%) of any window, which matters more
than raw total accuracy given `elephant_call`'s dual role (alert + fusion input). 3.0 s,
4.0 s, and 8.0 s all sit within about two points of each other and of 10.0 s on the priority
metric — this was not a landslide win, but it was the real winner by the metric this project
committed to before running the sweep. **Locked into `CLIP_SECONDS` (upload script) and
`DEFAULT_CLIP_SECONDS` (train script): 10.0 s.**

`boar_call` and `predator_call` recall across the five candidates
(3/4/6/8/10 s: boar 2.6%/0%/n·a/0%/5.3%, predator 10.7%/0%/0%/0%/0%) is the data referenced
in the class-scheme section above — at or near the chance floor in every reliable
configuration, which is what triggered the drop decision.

> **The Edge Impulse result sections below (every `## Result` heading dated 2026-09-22 or earlier)
> are superseded and their accuracies are withdrawn.** They were measured on a
> file-level split of a corpus of near-duplicates, which trained and tested on the same source
> recordings. They are kept as a record of what was tried and why, not as evidence of how well
> anything works. For held-out numbers, read
> *[Result — recording-level evaluation and an AudioSet-pretrained backbone](#result--recording-level-evaluation-and-an-audioset-pretrained-backbone-2026-09-23)*
> and the Caveats section, which explain the three leaks and quantify each one.

## Result — current production run (2026-09-14, 4-class, `vehicle` dropped)

This supersedes the 5-class result below. Same locked configuration (10.0 s window, MFE DSP,
2-conv architecture, `autoClassWeights: False`), run against project 1109511 after `vehicle`
was removed from the wire scheme and its samples deleted (see the class-scheme section
above), with the 15 new `chainsaw` and 10 new `elephant_call` laptop/phone clips already
folded in.

**Training job** (job 53749224, from Edge Impulse's own training-time validation split, 295
clips: ambient 77 / chainsaw 67 / elephant_call 63 / gunshot 88):

| Variant | Loss | Accuracy |
|---|--:|--:|
| float32 | 1.1112 | 51.2% |
| int8 | 1.2008 | 52.2% |

Training-time validation confusion matrix (float32; rows = true, columns = predicted, order
ambient/chainsaw/elephant_call/gunshot):

| True \ Predicted | `ambient` | `chainsaw` | `elephant_call` | `gunshot` |
|---|--:|--:|--:|--:|
| `ambient` | 33 | 22 | 5 | 17 |
| `chainsaw` | 16 | 36 | 8 | 7 |
| `elephant_call` | 9 | 19 | 29 | 6 |
| `gunshot` | 19 | 12 | 4 | 53 |

**Held-out model test** (job 53749250 — a real `classify` job over the actual test split, 473
clips, never seen during training; `minimumConfidenceRating: 0.1`, true argmax accuracy):

| Class | Good/Total | Recall | `floor_status` |
|---|--:|--:|---|
| `gunshot` | 148/212 | **69.8%** | trained |
| `chainsaw` | 44/79 | **55.7%** | trained |
| `ambient` | 44/101 | **43.6%** | trained |
| `elephant_call` | 30/81 | **37.0%** | trained |

**Total: 266/473 correct = 56.2%** (four-class chance floor = 25%).

**Confusion matrix** (rows = true label, columns = predicted; `uncertain` was 0 for every row
at `minimumConfidenceRating: 0.1`):

| True \ Predicted | `ambient` | `chainsaw` | `elephant_call` | `gunshot` |
|---|--:|--:|--:|--:|
| `ambient` | 44 | 29 | 4 | 24 |
| `chainsaw` | 17 | 44 | 7 | 11 |
| `elephant_call` | 24 | 24 | 30 | 3 |
| `gunshot` | 46 | 9 | 9 | 148 |

Full interactive results: <https://studio.edgeimpulse.com/studio/1109511/testing>

### Reading these numbers honestly

**`chainsaw` recovered to its best score in this project's history** (55.7%, up from 23.7% in
the last fully-documented 5-class run below, and up from 0.0% in the intervening run that
triggered the `vehicle` drop — see the class-scheme section above). Its confusion is now
spread across `ambient` (17/79) and `gunshot` (11/79) rather than concentrated in one
dominant confusable class, consistent with the vehicle-collision diagnosis: removing the one
class it was colliding with let its own decision boundary separate from the others again.

**`gunshot` improved too** (69.8%, above every gunshot number previously recorded for any
5-class configuration in this document, which ranged 55.8%–64.1%) and its confusion pattern
is unchanged in kind — still mostly `ambient` (46/212).

**`elephant_call` and `ambient` both regressed, and this is not yet fully explained.**
`ambient` fell to 43.6%, below every previously recorded 5-class number (55.4%–63.4%).
`elephant_call` fell to 37.0% (30/81) — below the 50.6% recorded for the 2026-09-13 widening
run, and further below the roughly 58.0% recall it scored in the run immediately preceding
the `vehicle` drop (training job 53748973 / classify job 53749012 — the same run whose
training-validation confusion matrix supplied the 33/60 chainsaw-to-vehicle misroute evidence
above). Its confusion is now split almost evenly between `chainsaw` (24/81) and `ambient`
(24/81). Two explanations are both consistent with what has been measured, and **no repeat
run was made to distinguish them**, given the build deadline:

1. **A genuine side effect of removing `vehicle`.** With `vehicle` gone, the softmax has one
   fewer place to route a misclassification — probability mass that a 5-class model might
   have (correctly or incorrectly) assigned to `vehicle` is now redistributed only among the
   remaining three off-target classes, and `chainsaw`/`ambient` may simply have picked up more
   of `elephant_call`'s spillover than `vehicle` used to.
2. **Ordinary run-to-run variance.** This project has already documented single-toggle swings
   of this general size — `autoClassWeights` alone moved `elephant_call` by 16.5 points and
   `vehicle` by up to 27.9 points in earlier A/Bs (see below) — so a ~13-21 point swing across
   a retrain that changed both the class roster *and* the training data is not unprecedented,
   even though it is on the larger end of what has been seen.

Total accuracy (56.2%) is reported for completeness only, per this document's standing
convention; it is not the metric this project optimizes for. The honest summary for this run
is: `chainsaw` is fixed, `gunshot` is fine, and `elephant_call` — the one class that also
feeds the deterrence fusion decision — is now this model's weakest point and the open
question for future work, not `chainsaw`.

## Result — retrain after widening `elephant_call` sourcing (2026-09-14, supersedes the run above)

Same locked configuration and class roster as the run above, retrained against project
1109511 after the Freesound query widening described in the Dataset section (+16 net-new
`elephant_call` clips, 394→410 total).

**Training job** (job 53749573, from Edge Impulse's own training-time validation split, 298
clips: ambient 77 / chainsaw 66 / elephant_call 69 / gunshot 86):

| Variant | Loss | Accuracy |
|---|--:|--:|
| float32 | 1.0383 | 54.7% |
| int8 | 1.0381 | 55.4% |

**Held-out model test** (job 53749601 — a real `classify` job over the actual test split, 476
clips, never seen during training; `minimumConfidenceRating: 0.1`, true argmax accuracy):

| Class | Good/Total | Recall | Prior run (394-clip `elephant_call`) | `floor_status` |
|---|--:|--:|--:|---|
| `gunshot` | 143/212 | **67.5%** | 69.8% | trained |
| `chainsaw` | 37/79 | **46.8%** | 55.7% | trained |
| `ambient` | 28/101 | **27.7%** | 43.6% | trained |
| `elephant_call` | 59/84 | **70.2%** | 37.0% | trained |

**Total: 267/476 correct = 56.1%** (four-class chance floor = 25%) — essentially unchanged
from the prior run's 56.2%.

**Confusion matrix** (rows = true label, columns = predicted; `uncertain` was 0 for every row):

| True \ Predicted | `ambient` | `chainsaw` | `elephant_call` | `gunshot` |
|---|--:|--:|--:|--:|
| `ambient` | 28 | 25 | 24 | 24 |
| `chainsaw` | 11 | 37 | 21 | 10 |
| `elephant_call` | 9 | 14 | 59 | 2 |
| `gunshot` | 44 | 8 | 17 | 143 |

Full interactive results: <https://studio.edgeimpulse.com/studio/1109511/testing>

### Reading these numbers honestly — this is not a clean win

`elephant_call` recall jumped 33.2 points (37.0%→70.2%), but **total accuracy barely moved**
(56.2%→56.1%), and the confusion matrix shows why this is not simply "more elephant data made
the model better": `ambient` collapsed by the same order of magnitude it gained (43.6%→27.7%),
and the votes `elephant_call` gained came substantially from `ambient` and `chainsaw` rather
than from resolving a genuine ambiguity. `ambient`→`elephant_call` misroutes rose from 4/101 to
24/101; `chainsaw`→`elephant_call` misroutes rose from 7/79 to 21/79; `chainsaw`'s own recall
fell in step (55.7%→46.8%). This reads as the three classes reshuffling which way their
confusion gets misrouted, not as the decision boundaries actually sharpening.

Sixteen additional clips (a 4% increase in `elephant_call`'s pool) is too small a change to
plausibly cause a swing this large through data volume alone. The far more likely explanation
is the same one flagged as unresolved after the `vehicle` drop above: this model's four
remaining classes have enough real overlap in the MFE feature space that which class "wins" a
given ambiguous clip is sensitive to small perturbations in training data and/or random
initialization — ordinary run-to-run variance, not a trend. **No repeat run was done to
separate signal from variance here either, given the build deadline.** Anyone using this
model's per-class numbers should treat a single run's `elephant_call`/`ambient`/`chainsaw`
figures as having roughly ±15-20 points of run-to-run noise until multiple repeated runs are
averaged (not blended into a single reported number — see this document's no-averaging rule —
but used to establish an honest confidence interval before the next real decision is made on
this model).

## Result — retrain after widening all four classes' sourcing (2026-09-14, supersedes the run above)

Following the `elephant_call`-only widening above, the Freesound query lists for **all four**
classes were widened (`gunshot` 10→15 queries, `chainsaw` 8→13, `elephant_call` 12→18, plus a
brand-new 12-query forest/jungle-ambience pull for `ambient`, which had none before), and the
per-class `FREESOUND_CAP` was raised (`gunshot`/`chainsaw` to 200/400, `ambient` capped at 260
for the new supplement). This was a direct response to the request to source more data and try
to reach 80% recall on every class. The resulting dataset (1,977 clips total — see the Dataset
table above) was uploaded to project 1109511 and retrained twice: once with this project's
long-standing `autoClassWeights: False` default, and once with it flipped on via the
`--class-weights` CLI override, to see whether `ambient`'s new 700-clip majority (it is now
larger than the other three classes combined) was distorting the un-weighted result.

**Project 1109511 data for both runs: 1,838 training / 587 testing clips.**

### Variant A — `autoClassWeights` off (the locked default)

**Training job** (job 53769500, Edge Impulse's own training-time validation split, 368 clips):

| Variant | Loss | Accuracy |
|---|--:|--:|
| float32 | 1.0822 | 57.1% |
| int8 | 1.0852 | 56.5% |

**Held-out model test** (job 53769558 — a real `classify` job over the actual 587-clip test
split, never seen during training; `minimumConfidenceRating: 0.1`, true argmax accuracy):

| Class | Good/Total | Recall | `floor_status` |
|---|--:|--:|---|
| `gunshot` | 165/249 | **66.3%** | trained |
| `chainsaw` | 19/101 | **18.8%** | trained |
| `elephant_call` | 30/84 | **35.7%** | trained |
| `ambient` | 106/153 | **69.3%** | trained |

**Total: 320/587 correct = 54.5%** (four-class chance floor = 25%).

**Confusion matrix** (rows = true label, columns = predicted; `uncertain` was 0 for every row):

| True \ Predicted | `ambient` | `chainsaw` | `elephant_call` | `gunshot` |
|---|--:|--:|--:|--:|
| `ambient` | 106 | 10 | 13 | 24 |
| `chainsaw` | 55 | 19 | 11 | 16 |
| `elephant_call` | 38 | 11 | 30 | 5 |
| `gunshot` | 72 | 3 | 9 | 165 |

### Variant B — `autoClassWeights` on (`--class-weights` override)

**Training job** (job 53769747, same 368-clip validation split):

| Variant | Loss | Accuracy |
|---|--:|--:|
| float32 | 1.1148 | 51.1% |
| int8 | 1.1139 | 52.2% |

**Held-out model test** (job 53769815, same 587-clip real test split):

| Class | Good/Total | Recall | `floor_status` |
|---|--:|--:|---|
| `gunshot` | 173/249 | **69.5%** | trained |
| `chainsaw` | 14/101 | **13.9%** | trained |
| `elephant_call` | 54/84 | **64.3%** | trained |
| `ambient` | 76/153 | **49.7%** | trained |

**Total: 317/587 correct = 54.0%.**

**Confusion matrix:**

| True \ Predicted | `ambient` | `chainsaw` | `elephant_call` | `gunshot` |
|---|--:|--:|--:|--:|
| `ambient` | 76 | 8 | 36 | 33 |
| `chainsaw` | 41 | 14 | 26 | 20 |
| `elephant_call` | 20 | 6 | 54 | 4 |
| `gunshot` | 53 | 4 | 19 | 173 |

Full interactive results: <https://studio.edgeimpulse.com/studio/1109511/testing>

### Reading these numbers honestly — 80% was not reached on any class, and this is a mixed result

Neither variant comes close to the 80%-per-class target. Total accuracy did not improve over
the prior `elephant_call`-only run (56.1% → 54.5% / 54.0%) despite nearly doubling the dataset
(1,251 → 1,977 clips). The two variants tell a clear, consistent story once read together
rather than in isolation:

- **`ambient` volume genuinely helped**, but only without class weighting. Growing `ambient`
  from 366 to 700 clips (now the largest class by a wide margin) pushed its own recall from
  27.7% to 69.3% under `autoClassWeights: False` — the biggest single-class swing seen in this
  project's history that is plausibly a real data effect rather than run-to-run noise, given the
  scale of the volume change. But `autoClassWeights: True` immediately gives most of that gain
  back (69.3%→49.7%), because reweighting explicitly discounts the now-dominant class in the
  loss function — confirming the gain is a volume/prior effect, not a sharper decision boundary.
- **Class weighting trades `ambient` for `gunshot` and `elephant_call`.** Turning weighting on
  recovers `elephant_call` from 35.7% to 64.3% and lifts `gunshot` from 66.3% to 69.5%, both by
  countering `ambient`'s now-oversized prior — consistent with how `autoClassWeights` is
  documented to work. This is the expected, mechanical effect of reweighting against a skewed
  class distribution, not a data-quality finding.
- **`chainsaw` is not fixed by weighting, and its confusion is not concentrated on the majority
  class.** `chainsaw` regressed in both variants (55.7% in the prior 5-class run → 18.8% off /
  13.9% on), and under weights-on its confusion matrix row spreads across all three other
  classes almost evenly (`ambient` 41, `elephant_call` 26, `gunshot` 20) rather than piling onto
  `ambient`, the way a pure imbalance artifact would. If `ambient`'s volume were the only cause,
  reweighting away from `ambient` should have recovered most of `chainsaw`'s recall the way it
  recovered `elephant_call`'s — it did not (13.9% is *worse* than the 18.8% weights-off number).
  This points to a genuine data-quality problem introduced by the widened `chainsaw` Freesound
  queries, not a class-imbalance artifact. The most likely single cause: the `"power saw"`
  query alone contributed 138 of `chainsaw`'s 321 Freesound-sourced clips (see the Dataset
  section above), and that query almost certainly pulls in non-chainsaw power-tool audio
  (circular saws, table saws, angle grinders) that shares spectral characteristics with a
  chainsaw's engine drone but is acoustically distinct enough to confuse the model rather than
  reinforce it. This has not been verified by manually auditing the "power saw" clips — that
  audit is flagged as follow-up work below, not done as part of this session, to avoid further
  blind retrain cycles.

**No further retrain was attempted after Variant B.** Two real, honestly-reported configurations
already establish the shape of the tradeoff (ambient-volume gain vs. weighting-driven
redistribution vs. an unresolved chainsaw data-quality regression); continuing to try
hyperparameter combinations in search of a better number would drift toward exactly the kind of
fishing-for-a-good-run this document's no-averaging/no-fabrication convention exists to prevent.
Which of Variant A or Variant B is left as the live model in project 1109511 depends on which
failure mode is more acceptable operationally: Variant A (weights off) favors `ambient`/`gunshot`
at the cost of `elephant_call` and `chainsaw`; Variant B (weights on) favors `gunshot`/
`elephant_call` — the class that also feeds the deterrence fusion decision — at the cost of
`ambient` and a further-regressed `chainsaw`. Given that `elephant_call` is the one acoustic
class this model feeds into the bandit/deterrence decision (see the class-scheme section above),
**Variant B (`autoClassWeights: True`) was left as the trained state of project 1109511** after
this session — this is a judgment call about which failure mode matters more for the deployment,
not a claim that Variant B is a better model in the aggregate; the total accuracy figures above
show it is not.

## Result — after the chainsaw data-quality audit and the ambient-cap pullback (2026-09-15, supersedes the run above)

Following the `"power saw"` audit and the `AMBIENT_CAP` pullback documented in the Dataset
section above, the dataset was re-uploaded to project 1109511 and retrained. **Project 1109511
data for every run below: 1,775 training / 552 testing clips**, MFE DSP, the locked impulse
(`--skip-impulse` reused the existing dsp/learn blocks for runs after the first). Four separate
real training runs were executed against this identical dataset — not two, as an earlier
internal note believed; the actual sequence, reconstructed from this project's own job history,
is reported below run by run, **with no averaging across runs and no cherry-picking the best
one as "the" result**.

### Run A — `autoClassWeights` on

Feature job `53779616` (5.5 min) → training job `53779914` (2.7 min) → held-out classify job
`53780104` (2.7 min).

| Class | Good/Total | Recall |
|---|--:|--:|
| `ambient` | 82/152 | **53.9%** |
| `chainsaw` | 12/48 | **25.0%** |
| `elephant_call` | 54/76 | **71.1%** |
| `gunshot` | 185/276 | **67.0%** |

**Total: 333/552 = 60.3%.**

### Run B — `autoClassWeights` off

Feature job `53780286` → training job `53780518` → held-out classify job `53780713` (2.7 min).

| Class | Good/Total | Recall |
|---|--:|--:|
| `ambient` | 117/152 | **77.0%** |
| `chainsaw` | 2/48 | **4.2%** |
| `elephant_call` | 29/76 | **38.2%** |
| `gunshot` | 167/276 | **60.5%** |

**Total: 315/552 = 57.1%.** This reconfirms the earlier weights-off finding: `ambient` recall
is the best of any run here, and `chainsaw` collapses almost to nothing (4.2%, worse than a
25% four-class chance floor's naive per-class baseline would suggest for a class this small).

### Run C — `autoClassWeights` on (repeat of Run A's exact configuration)

Feature job `53780862` → training job `53781206` → held-out classify job `53781440` (8.2 min).

| Class | Good/Total | Recall |
|---|--:|--:|
| `ambient` | 112/152 | **73.7%** |
| `chainsaw` | 9/48 | **18.8%** |
| `elephant_call` | 41/76 | **53.9%** |
| `gunshot` | 145/276 | **52.5%** |

**Total: 307/552 = 55.6%.**

*(Between Run C and Run D, the EON Tuner 4-class re-run above (job `53782394`) executed, and a
duplicate feature-generation job storm — jobs `53785901`/`53785905`/`53785906`, all finished
`successful=False` — had to be waited out and did not produce a usable result before Run D.)*

### Run D — `autoClassWeights` on (currently the live trained state of project 1109511)

Feature job `53785969` (5.1 min) → training job `53786057` (3.8 min) → held-out classify job
`53786113` (2.7 min).

| Class | Good/Total | Recall |
|---|--:|--:|
| `ambient` | 92/152 | **60.5%** |
| `chainsaw` | 9/48 | **18.8%** |
| `elephant_call` | 54/76 | **71.1%** |
| `gunshot` | 173/276 | **62.7%** |

**Total: 328/552 = 59.4%.**

Confusion matrix:

| True \ Predicted | `ambient` | `chainsaw` | `elephant_call` | `gunshot` |
|---|--:|--:|--:|--:|
| `ambient` | 92 | 6 | 28 | 26 |
| `chainsaw` | 23 | 9 | 13 | 3 |
| `elephant_call` | 15 | 4 | 54 | 3 |
| `gunshot` | 80 | 3 | 20 | 173 |

Full interactive results: <https://studio.edgeimpulse.com/studio/1109511/testing>

### Reading these numbers honestly — three identically-configured runs, one dataset, a wide spread

Runs A, C, and D all use the exact same `autoClassWeights: True` configuration against the
byte-identical 1,775/552 dataset, differing only in Edge Impulse's own training-run randomness
(weight initialization, minibatch order). Laid side by side, the spread is large enough that
**quoting any single one of these three runs as "the" chainsaw or ambient number would be
misleading**:

| | Run A | Run C | Run D | spread |
|---|--:|--:|--:|--:|
| `ambient` | 53.9% | 73.7% | 60.5% | **19.8 points** |
| `chainsaw` | 25.0% | 18.8% | 18.8% | 6.2 points |
| `elephant_call` | 71.1% | 53.9% | 71.1% | 17.2 points |
| `gunshot` | 67.0% | 52.5% | 62.7% | 14.5 points |
| total | 60.3% | 55.6% | 59.4% | 4.7 points |

This is a stronger, now-quantified version of the "±15-20 points of run-to-run noise" caveat
already carried in this document from the `elephant_call`-widening run — it is no longer an
estimate from two differently-configured runs, it is a measurement from three repeated runs on
one fixed dataset and one fixed configuration. Total accuracy is comparatively stable (55.6%–
60.3%, a 4.7-point spread); per-class recall is not, and `ambient` and `elephant_call` swing by
nearly 20 points each depending on nothing but which run you happen to look at.

`chainsaw` is the one class where this run-to-run noise does **not** rescue a hopeful reading:
its highest observed value across all four runs (A/B/C/D) and the EON Tuner's best trial is
25.0% (Run A), and its range (4.2%–25.0%) never approaches the 80% target from any angle tried.
The `"power saw"` audit's data-quality fix (see above) did not produce a clean recovery — Run D,
trained on the corrected dataset, still lands at 18.8%, statistically indistinguishable from
Run C's 18.8% on the pre-fix-adjacent dataset. Whatever is limiting `chainsaw` recall on this
device's fixed 8 kHz/10 s/MFE pipeline, it was not resolved by removing the one clearly
mislabeled query.

Run D used the same `autoClassWeights: True` judgment call documented in the prior Result section
(favoring `elephant_call`, the class that also feeds the deterrence fusion decision, over
`ambient`). It was not claimed to be the best of the four runs by any metric other than
recency — Run A's total (60.3%) and `chainsaw` recall (25.0%) were both marginally higher.
**Run D is no longer the live trained state of project 1109511** — see the MFE-vs-MFCC section
immediately below, whose final run (Run E) superseded it. **The honest conclusion, across every
configuration tried in this entire session — five hand-tuned MFE runs, the EON Tuner's automated
search, and two independent data-quality interventions — is that the 80%-per-class target was
not reached on any class, and `chainsaw` remains the persistent bottleneck, never exceeding 25%
recall under any real, verified condition.**

## Result — MFE vs MFCC x `autoClassWeights` on the current dataset (2026-09-22, supersedes Run D as the live state)

The DSP A/B section above (MFE vs MFCC) was measured on the older rebalanced+XIAO 7-class
dataset, not the current post-audit 1,775/552 4-class one — an earlier internal note believed a
comparison existed on the current dataset, but it did not until this run. All four runs below
share the identical 1,775/552 dataset; `--dsp mfcc` requires a full impulse rebuild (frame count
13 vs MFE's 40), so `--skip-impulse` was only used for the second run of each DSP-type pair.

### MFCC, `autoClassWeights` on

Feature job `54003784` (4.5 min) -> training job `54003892` (2.1 min) -> held-out classify job
`54003929` (2.4 min). (This exact configuration was run twice in immediate succession — an
earlier feature/train/classify triple, jobs `54003532`/`54003674`/`54003715`, produced numbers
identical to the digit, including training-time validation loss matching to 16 significant
figures. That is not plausible for two independently-initialized training runs and is most
likely Edge Impulse returning a cached/deduped result for the second invocation, consistent with
the duplicate-job behavior this project has seen before on this network. Only one data point is
counted here, not two.)

| Class | Good/Total | Recall |
|---|--:|--:|
| `ambient` | 107/152 | **70.4%** |
| `chainsaw` | 11/48 | **22.9%** |
| `elephant_call` | 42/76 | **55.3%** |
| `gunshot` | 146/276 | **52.9%** |

**Total: 306/552 = 55.4%.**

### MFCC, `autoClassWeights` off

Feature job `54013922` (0.3 min, reused MFCC impulse via `--skip-impulse`) -> training job
`54013926` (2.1 min) -> held-out classify job `54013978` (0.7 min).

| Class | Good/Total | Recall |
|---|--:|--:|
| `ambient` | 126/152 | **82.9%** |
| `chainsaw` | 2/48 | **4.2%** |
| `elephant_call` | 46/76 | **60.5%** |
| `gunshot` | 124/276 | **44.9%** |

**Total: 298/552 = 54.0%.**

### Run E — MFE, `autoClassWeights` on (rebuild; now the live trained state of project 1109511)

Feature job `54014006` (3.8 min) -> training job `54014102` (2.4 min) -> held-out classify job
`54014192` (2.1 min).

| Class | Good/Total | Recall |
|---|--:|--:|
| `ambient` | 90/152 | **59.2%** |
| `chainsaw` | 8/48 | **16.7%** |
| `elephant_call` | 54/76 | **71.1%** |
| `gunshot` | 168/276 | **60.9%** |

**Total: 320/552 = 58.0%.**

### The full grid, and why MFE stays the locked DSP block

| Config | `ambient` | `chainsaw` | `elephant_call` | `gunshot` | total |
|---|--:|--:|--:|--:|--:|
| MFE, weights on (Run D) | 60.5% | 18.8% | 71.1% | 62.7% | 59.4% |
| MFE, weights off (Run B) | 77.0% | 4.2% | 38.2% | 60.5% | 57.1% |
| MFCC, weights on | 70.4% | 22.9% | 55.3% | 52.9% | 55.4% |
| MFCC, weights off | 82.9% | 4.2% | 60.5% | 44.9% | 54.0% |
| MFE, weights on (Run E, live) | 59.2% | 16.7% | 71.1% | 60.9% | 58.0% |

MFCC's only advantage anywhere in this grid is `chainsaw`, and only against the weights-on MFE
runs (+4.1 points over Run D, +6.2 over Run E) — never against the weights-off MFE runs, where
MFCC and MFE tie at 4.2%. That small chainsaw gain costs `elephant_call` 15.8 points against
either weights-on MFE run (Run D and Run E tie at 71.1%), `gunshot` 8.0-9.8 points, and 2.6-4.0
points of total accuracy. Given `elephant_call`'s dual role (it also feeds the deterrence fusion
decision) and this project's stated priority — `elephant_call`/`gunshot`/`chainsaw` matter more
than raw total, but not in a way that justifies a 15.8-point `elephant_call` loss for a few
points of `chainsaw` — MFE remains the better DSP block, reconfirming the older DSP A/B
section's verdict on a dataset where it had never actually been tested. Project 1109511 was
rebuilt back onto MFE (Run E) so its live state reflects this conclusion rather than being left
on the worse MFCC config that happened to run last.

Run E's numbers track Run D's closely on `elephant_call` (71.1%, identical 54/76) and are within
a few points on `ambient`/`chainsaw`/`gunshot` — a fifth data point consistent with the
run-to-run-variance caveat below, not a contradiction of it.

## Result — historical: final 5-class run before the `vehicle` drop (superseded 2026-09-14)

This is the real, live run after the 2026-09-13 chainsaw/vehicle data widening: 5-class
scheme, 10.0 s window, the locked architecture and DSP above. Edge Impulse's own
training-run log reports **1,729 training / 536 testing** clips read for this job;
summing the per-class train/test counts in the Dataset table above gives 1,674 / 495
instead — a larger version of the same kind of discrepancy the pre-widening run already
had (there it was 14 training / 1 testing clip; see "Why the manifest's per-class test
count is a floor, not the real count" above for the now-identified mechanism — the ledger
accumulates clips across runs with different seeded samples, so the manifest's latest-run
counts undercount what is actually resident and being tested). The held-out numbers below
are Edge Impulse's own `classify` job output (536 real held-out clips, matching the
training log's testing count) and are internally consistent with each other; they are the
authoritative real-world test-set sizes, not the manifest's.

This run was reproduced twice with identical results (once as the direct widened-data
retrain, once again after repairing the manifest — see below), and a third variant with
`autoClassWeights: True` was also run as a genuine re-test (not previously tried on this
5-class roster) and discarded — see the addendum at the end of this section.

**Training job** (job 53728634, from Edge Impulse's own training-time validation split):

| Variant | Loss | Accuracy |
|---|--:|--:|
| float32 | 1.2211 | 52.0% |
| int8 | 1.3017 | 52.6% |

**Held-out model test** (job 53728654/53728766 — a real `classify` job run over the actual
test split, 536 clips, never seen during training; `minimumConfidenceRating: 0.1` so this
is true argmax accuracy, not Edge Impulse's confidence-bucketed number):

| Class | Good/Total | Recall | `floor_status` | vs. pre-widening |
|---|--:|--:|---|--:|
| `ambient` | 64/101 | **63.4%** | trained | +17.9 |
| `gunshot` | 110/181 | **60.8%** | trained | −3.8 |
| `elephant_call` | 40/79 | **50.6%** | trained | −15.2 |
| `vehicle` | 55/99 | **55.6%** | trained | **+27.9** |
| `chainsaw` | 18/76 | **23.7%** | trained | **+6.1** |

**Total: 287/536 correct = 53.5%** (five-class chance floor = 20%).

**Confusion matrix** (rows = true label, columns = predicted; `uncertain` was 0 for every
row at `minimumConfidenceRating: 0.1`):

| True \ Predicted | `ambient` | `chainsaw` | `elephant_call` | `gunshot` | `vehicle` |
|---|--:|--:|--:|--:|--:|
| `ambient` | 64 | 2 | 10 | 13 | 12 |
| `chainsaw` | 22 | 18 | 9 | 3 | 24 |
| `elephant_call` | 22 | 1 | 40 | 2 | 14 |
| `gunshot` | 51 | 4 | 15 | 110 | 1 |
| `vehicle` | 23 | 5 | 10 | 6 | 55 |

Full interactive results: <https://studio.edgeimpulse.com/studio/1109511/testing>

### Reading these numbers honestly (historical, pre-`vehicle`-drop)

This is the direct outcome of widening chainsaw's Freesound queries from 2 to 8 and
vehicle's from 4 to 10 (plus a new ESC-50 "engine" supplement for vehicle), specifically to
address these two classes being the model's weakest (see the prior Result numbers in the
"vs. pre-widening" column). **`vehicle` responded strongly** — 27.7% → 55.6%, a real
doubling, and the confusion matrix shows why: it's now most often confused with `ambient`
(23/99) rather than scattered everywhere, a single dominant confusable pair rather than a
diffuse failure. **`chainsaw` improved only modestly** — 17.6% → 23.7% — and its confusion
pattern changed shape rather than just shrinking: it is now concentrated in two confusable
pairs, `vehicle` (24/76, the single largest bucket) and `ambient` (22/76), together
accounting for 60% of its errors. That chainsaw's own widened data made it *more* likely to
be confused specifically with vehicle (whose data also grew this run) rather than less is a
real signal that these two classes' Freesound-sourced audio — both sustained
mechanical/engine drones — sit close together in MFE feature space at this window length;
more volume alone did not separate them. `elephant_call` and `ambient` moved too (−15.2 and
+17.9) despite their own data being unchanged in this run — a reminder that in a 5-class
softmax, any class's decision boundary can shift when another class's data changes, so a
per-class delta is never fully attributable to that class's own data alone. Total accuracy
(53.5%) is reported for completeness only; it is not the metric this project optimizes for
and should not be read as summarizing "the model got better" — chainsaw's continued weakness
is the operative fact for that class specifically.

### `autoClassWeights` re-test on the current roster (2026-09-13) — reconfirmed OFF

The original OFF-lock (see the section above) was measured with `boar_call`/`predator_call`
still in the roster; since both were later dropped entirely, that justification does not
automatically transfer to today's 5-class problem, so it was re-tested rather than assumed.
Same widened data, `--skip-impulse` (identical DSP features), retrain-only comparison:

| Class | Weights OFF (kept) | Weights ON | Delta |
|---|--:|--:|--:|
| `chainsaw` | 23.7% | 17.1% | −6.6 |
| `vehicle` | 55.6% | 48.5% | −7.1 |
| `gunshot` | 60.8% | 64.1% | +3.3 |
| `ambient` | 63.4% | 55.4% | −8.0 |
| `elephant_call` | 50.6% | 50.6% | 0.0 |

Weights ON costs both of this session's target classes (chainsaw, vehicle) real recall for a
small gunshot gain — the wrong trade for the work this session was doing. **Reconfirmed:
`autoClassWeights: False`.** The production model in 1109511 was retrained a final time with
weights off after this experiment, so the numbers in the Result section above (and the live
model in the project) reflect weights-off, not the experiment.

## Result — corrected corpus after a full integrity audit (2026-09-23, supersedes the section below)

The section that follows this one reported 92.8% overall and 77.9% chainsaw recall. Both figures
are withdrawn. Auditing the frozen split directly — rather than reasoning about filenames — turned
up three further defects, documented in the 2026-09-23 amendment to
`docs/decisions/0025-acoustic-recording-level-split-integrity.md`:

1. Three byte-identical audio payloads spanned train and test under different filenames, which no
   naming rule can see. `build_index.py` now hashes decoded frames and unions the group keys; 25
   payloads proved to be held under more than one key.
2. Freesound id 410552 was in the corpus as both `ambient` and `gunshot` over identical audio. It
   is a rifle shot recorded in forest at 15 m, confirmed from the uploader's description and
   independently from the waveform (two impulsive events over near-silence, frame-RMS max/median
   72:1). A gunshot inside the `ambient` class teaches directly against the gunshot/ambient
   confusion the model is being asked to resolve. It is quarantined.
3. The Zenodo ingest's peak normalisation amplified a small source DC offset into a median 0.32
   against 0.000 for every other corpus, and larger on chainsaw than ambient — a per-source
   constant a model could separate on without listening. Fixed by removing DC before normalising.

Both splits now pass `audit_dataset.py --full` with zero fatal issues.

| class | recall | 95% CI | precision | F1 | n |
|---|---|---|---|---|---|
| ambient | 95.2% | [93.6, 98.4] | 93.5% | 0.94 | 236 |
| chainsaw | 86.5% | [82.0, 96.4] | 85.5% | 0.86 | 68 |
| elephant_call | 93.4% | [88.6, 100.0] | 90.1% | 0.92 | 58 |
| gunshot | 93.4% | [88.9, 95.3] | 96.4% | 0.95 | 243 |
| **overall** | **93.3%** | | | | 605 |

Field slice: ambient 97.9% (n=39), elephant_call 95.9% (n=29). Chainsaw and gunshot field recall
are not reportable (n=2 and n=1).

**Chainsaw reads as 77.9% → 86.5%, and that is not a controlled comparison.** Quarantining 410552
and merging the duplicate groups changed group membership, so the seeded split redrew and chainsaw
is now measured on a different 68 recordings. The two intervals overlap substantially. Part of the
movement is likely real — removing a rifle shot from `ambient` should reduce chainsaw→gunshot
confusion, and it fell from 10.6% to 2.6% — but `elephant_call` and `gunshot` each dropped about
1.8 points in the same run, which is the signature of a changed test set rather than a systematic
gain. Quote 86.5% as the current figure, not as an improvement of 8.6 points.

### The long-range ARU corpus did not help, and the first attempt was actively harmful

Zenodo 5824433 (Stefanakis et al., EUSIPCO 2022) was added to attack the chainsaw shortfall: 8 kHz
native, SWIFT recorders in real forest, human-annotated, CC-BY-4.0. Added train-only against the
byte-identical 605-file test set, it produced this:

| | baseline | +Zenodo v1 (436 cs / 163 amb) | +Zenodo v2 (392 cs / 545 amb) |
|---|---|---|---|
| overall | **93.3%** | 90.8% | 90.9% |
| chainsaw recall | 86.5% | 87.6% | 87.4% |
| chainsaw precision | **85.5%** | 68.0% | 71.5% |
| ambient recall | **95.2%** | 88.3% | 89.3% |
| field ambient recall | **97.9%** | 57.9% | 68.7% |

The roughly one point of chainsaw recall is inside the confidence interval in both runs. The costs
are not.

The first hypothesis was internal imbalance. These are SWIFT units in one forest, so they share a
distinctive noise floor, and within it chainsaw outnumbered ambient 2.7:1 — apparently the model
learning the recorder rather than the saw. On the deployment noise floor, 42% of genuine forest
ambience came back as `chainsaw`.

So the ingest was rebalanced to 392 chainsaw against 545 ambient, inverting the ratio, and v2
tests that prediction. It moved in the predicted direction and nowhere near far enough: field
ambient recovered 10.8 points but remains 29 points below baseline, and chainsaw precision
recovered 3.5 points but remains 14 below. The imbalance was a contributing factor, not the cause.
What is left is a genuine domain shift — Mediterranean forest, 2016-18, autonomous units — that
survives rebalancing.

**Verdict: the corpus is not used.** Testing further variants against the same 605-file test set
would select for a lucky draw rather than measure anything, so two falsified attempts is where this
stops. `build_index.py` excludes `zenodo_aru` by default and `--include-source` re-admits it; the
audio stays on disk because the licence is clean and a future domain-adaptation attempt may want
it.

The reason this mattered enough to test twice: for a system that pages a forest officer on chainsaw
detections, a precision collapse is a worse failure than the 13.5% of chainsaws currently missed.
It trades a detection gap for alert fatigue, which ends with the system ignored. It is also the same
class of defect as the DC offset and the earlier `xiao_esp32s3` artifact — a per-source property
that correlates with a label — which is why a new corpus is now checked against the per-source
DC/RMS/clipping table and evaluated on the field slice before it is trusted.

## Result — recording-level evaluation and an AudioSet-pretrained backbone (2026-09-23)

Measured by `ml/acoustic/harness/`, outside Edge Impulse, on a split grouped by source recording
(607 held-out recordings; see `docs/decisions/0025-acoustic-recording-level-split-integrity.md`).
These are **not** comparable to the Edge Impulse numbers above, which used a file-level split.

The control is the production recipe itself — the locked MFE front end and
`conv1d(16) -> conv1d(32) -> dense(24)` — rebuilt and run on the same split, so the comparison
isolates the backbone rather than crediting it with the dataset rebuild.

| Class | MFE control (recall) | Cnn14 + MLP | Cnn6 + MLP | n |
|---|--:|--:|--:|--:|
| `ambient` | 72.9% | **94.2%** | 88.9% | 236 |
| `chainsaw` | 77.9% | **77.9%** | 80.3% | 68 |
| `elephant_call` | 86.1% | **95.3%** | 95.0% | 60 |
| `gunshot` | 87.4% | **95.1%** | 96.7% | 243 |
| **overall** | **80.6%** (78.3–84.2) | **92.8%** (92.3–93.1) | **91.7%** (90.9–92.6) | 607 |

Per-class recall with a 95% bootstrap CI over resampled test recordings, and precision, for
Cnn14 + MLP: `ambient` 94.2% [90.3, 96.6] / 92.8%; `chainsaw` 77.9% [69.4, 88.3] / 85.3%;
`elephant_call` 95.3% [91.7, 100] / 98.0%; `gunshot` 95.1% [92.1, 97.6] / 93.5%.

### `chainsaw` is the one place the "data ceiling" verdict holds

The Exploration History concluded "data ceiling, not capacity ceiling" from two small nets tying.
On a clean split that conclusion is wrong for three classes and right for one. An AudioSet-pretrained
backbone lifts `ambient` by 21.3 points, `elephant_call` by 9.2 and `gunshot` by 7.7 — those were
capacity ceilings, and the tie between two similar small nets could not have revealed it.

`chainsaw` does not move at all. An 81M-parameter backbone pretrained on a corpus whose ontology
contains `Chainsaw` (/m/01j4z9) scores 77.9%, exactly what the 2-conv net from scratch scores. Two
further probes agree: adding 254 AudioSet chainsaw recordings to training (nearly doubling the
class, test set held byte-identical) changed recall by −1.1 points, within noise; and no decision
threshold reaches 85% recall without giving up most of the precision headroom. The missed saws
split between `ambient` (11.5%) and `gunshot` (10.6%) — quiet or distant cutting, and impulsive
onsets.

That AudioSet augmentation failed is consistent rather than surprising: the backbone was pretrained
on AudioSet, so AudioSet chainsaw audio carries little the representation has not already seen.
What `chainsaw` needs is audio from a *different* distribution — real saws at real distances on the
deployment hardware — not more of the same corpus.

### Operating point is a deployment decision, not a modelling one

`chainsaw` at argmax gives 77.9% recall at 85.3% precision. Lowering its threshold to 0.10 reaches
**85.3% recall at 76.3% precision** — 18 false positives instead of 8, over 607 recordings. Which
of those is correct depends on whether a missed illegal-logging event or an unnecessary patrol is
the costlier error in Kothamangalam, which is the DFO's call to make and not a default this
repository should silently pick.

### Backbone choice

Cnn6 (5.9M params, 512-d) trails Cnn14 (81M, 2048-d) by 1.1 points overall and is the only one of
the two that could plausibly run on the QRB2210. It is also *better* on `chainsaw` (80.3% recall at
92.0% precision). It is worse where it matters most, though: `elephant_call` precision falls from
98.0% to 77.9%, and `elephant_call` is the only class that feeds the deterrence decision in
`device/mpu/services/reflex_loop.py`, so roughly one deterrent firing in five would be spurious.
Neither backbone has been exported or benchmarked on-device yet; latency, RAM and flash on the
QRB2210 are unmeasured, and no `.eim` exists.

## Caveats — required whenever any number from this project is quoted

> **Every Edge Impulse accuracy in this file was measured on a file-level split and is
> optimistic.** This corpus contains *recordings*, each present many times over: the
> preprocessing pipeline emits several windows and gain variants per source file, ESC-50 is cut
> from Freesound (so five chainsaw recordings appear under both corpora), and the project's own
> field captures are chunked — `..._bg.1` through `..._bg.35` are consecutive slices of one
> continuous session, not 35 captures. Splitting on the file therefore put near-duplicates of the
> same audio on both sides of the boundary: 25.4% of `elephant_call` leaked at the variant level,
> and five chunks of the one chainsaw field session sat in train while 38 sat in test, which is
> why its field slice read a flawless 100%.
>
> `ml/acoustic/harness/` re-runs the evaluation with splits grouped by source recording, and
> `freeze_split.py` fails hard if any recording appears on both sides. The numbers below are kept
> as the record of what the Edge Impulse project reported, not as held-out accuracy. See
> `docs/decisions/0025-acoustic-recording-level-split-integrity.md`.


1. **`elephant_call`'s largest source has no license.**
   `github.com/HiruDewmi/Audio-Classification-for-Elephant-Sounds` supplies 313 of
   `elephant_call`'s 410 clips; the repository has no `LICENSE` file and no terms stated in
   its README (GitHub's own repository API reports `license: null`). This is usable for the
   experiment described here, but is flagged in the manifest per-clip
   (`"license": "none (GitHub repo has no LICENSE file)"`) and must be resolved — cleared,
   replaced, or the class re-sourced — before any production/commercial licensing gate.
2. **Most of this audio was not captured on this project's own INMP441 in Kerala forest
   conditions.** Only the XIAO ESP32S3 field-capture clips (31–73 per class, see the
   Dataset table) are project-owned recordings, and even those come from a different
   microphone (XIAO's onboard PDM MEMS mic, not the INMP441) — a real domain-shift risk
   between this training data and the deployed hardware's actual audio characteristics.
   This closes *"a 4-class acoustic model exists, trained on a mix of real licensed public
   data and real field captures"*, not *"this model is proven on the deployed INMP441's own
   audio."* Those two claims travel separately.
3. **The elephant-rumble low end is not actually captured.** Rumble fundamentals sit at
   roughly 8–34 Hz; an MFE block's lowest mel band sits far above that, so the model sees
   rumble harmonics and overtones, never the fundamental. This is consistent with
   `/CONTEXT.md`'s architecture (the INMP441 is scoped to frequencies above 60 Hz; the
   geophone handles low-frequency/infrasound detection), not a defect introduced here — but
   it means `elephant_call` is not infrasound detection, regardless of how well it scores.
4. **Freesound clip relevance rests on uploader tagging, not expert verification**, across
   every class that draws from it (`gunshot`, `chainsaw`, `vehicle`, `elephant_call`). Clips
   were filtered by license, search query, and duration — not individually listened through.
5. **The `"power saw"` query was audited and dropped (2026-09-15); `chainsaw` still did not
   recover.** This caveat previously flagged `"power saw"` — which alone contributed 138 of
   `chainsaw`'s 321 Freesound clips at the time — as an unverified suspect for the collapse to
   18.8%/13.9% documented in the "Result — retrain after widening all four classes' sourcing"
   section. That audit has since been done: all 136 clips the query pulled were manually
   reviewed, and it was confirmed off-target — mostly synthesizer "sawtooth waveform" demos and
   generic factory/mechanical-impact sound-effects content, not other power tools as guessed,
   and not real chainsaw audio either way (see "Chainsaw data-quality audit" under the Dataset
   section above). The query was dropped and the remaining chainsaw query list widened from 13
   to 19 real chainsaw-specific queries. **This did not produce a clean recovery.** Across the
   four post-audit training runs in the current Result section, `chainsaw` recall ranges
   18.8%–25.0% — the same range as the pre-audit runs, and in two of the three
   `autoClassWeights`-on runs (Runs C and D) identical to 18.8% within measurement noise.
   Whatever limits `chainsaw` on this pipeline was not primarily the `"power saw"` contamination;
   see the new run-to-run-variance caveat below and this document's honest read that `chainsaw`
   has never exceeded 25% recall under any real, verified configuration tried.
6. **This model's per-class numbers swing by 15-33 points between consecutive retrains on
   nearly the same data, and the cause is not fully diagnosed.** The `vehicle`-drop retrain
   scored `elephant_call` at 37.0% (down from 50.6%-58.0% in the two runs immediately before
   the drop) while `ambient` scored 43.6%; widening `elephant_call`'s Freesound sourcing by
   just 4% (394→410 clips) and retraining then swung `elephant_call` to 70.2% while `ambient`
   fell to 27.7% and `chainsaw` fell from 55.7% to 46.8% — see both Result sections'
   "Reading these numbers honestly" subsections above for the full confusion-matrix evidence.
   Total accuracy barely moved across that second swing (56.2%→56.1%), which argues these are
   the same four classes reshuffling which way their mutual confusion gets routed, not a real
   change in model quality. **No repeat run was done at either point to separate signal from
   variance**, given the build deadline this work is under. Because `elephant_call`
   is the one class that also feeds the deterrence fusion decision, treat any single run's
   `elephant_call`/`ambient`/`chainsaw` numbers as having roughly ±15-20 points of run-to-run
   noise until repeated runs are done. `chainsaw` briefly recovered to 55.7% after the
   `vehicle` drop, then fell again to 46.8% after the `elephant_call`-only widening and further
   to 18.8%/13.9% after the all-four-classes widening — see the caveat above on that most
   recent drop, which (unlike the earlier swings in this item) has a specific diagnosed
   likely cause rather than being attributed to undifferentiated run-to-run variance.
7. **`boar_call` and `predator_call` were dropped from the wire scheme, not merely
   under-performing.** See the class-scheme section above for the full history and exact
   numbers. Any future attempt to revive either class should start from that section rather
   than re-running the same exploration from scratch.
8. **`vehicle` was dropped 2026-09-14 after real field data exposed a chainsaw/vehicle
   acoustic collision** (chainsaw held-out recall collapsed to 0.0%, corroborated by the
   training-time validation confusion matrix, not just the held-out split). See the
   class-scheme section above for the full history. The raw audio stays cached locally, so
   `vehicle` can be re-uploaded from cache if it is ever revived — but reviving it without
   also addressing the underlying MFE-feature-space overlap with `chainsaw` (a different DSP,
   window length, or non-Freesound audio source) would likely reproduce the same collision.
9. **`predator_call` (when it was still in scope) lumped lion, leopard, and tiger into one
   label** — a coarser distinction than a real predator-identification system would want,
   moot now that the class is dropped but worth remembering if it is ever revived.
10. **Window-length sweep candidates are not sample-for-sample comparable.** Test-set sizes
   for the same class shift across the five window candidates (e.g. `vehicle`'s test set
   was 47 clips at 3.0 s/10.0 s but only 7 at 4.0 s/6.0 s/8.0 s) because re-cropping at a
   different window length changes how many non-overlapping windows fit inside each raw
   source clip. Only per-class recall percentage is the fair comparison across candidates,
   never the raw good/total counts. (The sweep itself, and its `vehicle` numbers, predate
   the 2026-09-14 drop and are kept as-is — they were real measurements at the time.)
11. **Not deployed.** No acoustic inference runs on this project's hardware yet. This closes
    the training half of the gap `docs/KNOWN_GAPS.md` tracks, not the deployment half — see
    that file's entry for exporting this model and wiring it into `handle_acoustic_event()`
    (a separate, deferred Track B change).
12. **Performance Calibration was investigated and is not part of this pipeline.** Edge
    Impulse's own documentation confirms it is a Studio-UI-only feature — there is no REST
    API to trigger a calibration run, retrieve its synthetic continuous-audio results, or
    fetch the tuned post-processing parameters (detection threshold, averaging window,
    suppression period) programmatically. Both training scripts in this project are pure
    API automation (see Reproducing above), so this is out of reach for them by construction,
    not by omission. The feature's own docs also describe it as designed for detecting a
    specific event against a background/silence state (e.g. keyword spotting), "as opposed
    to classifying ambient conditions" — a partial but not exact fit for a five-way
    classifier where `ambient` is itself one of the trained classes rather than a generic
    background state. If a calibrated operating point is wanted, it would need to be run
    manually in the Edge Impulse Studio UI against project 1109511 and the result transcribed
    here by hand — not attempted as part of this session's work.
13. **Run-to-run variance on an identical dataset and configuration is now directly measured,
    not just inferred.** Caveat 6 above documents swings between *different* retrains (new
    data, different `autoClassWeights` setting). The four runs in the current "Result — after
    the chainsaw data-quality audit and the ambient-cap pullback" section include three
    (Runs A, C, D) that share the exact same 1,775/552 dataset and the exact same
    `autoClassWeights: True` configuration, differing only in Edge Impulse's own training
    randomness. Their spread: `ambient` 53.9%–73.7% (19.8 points), `elephant_call` 53.9%–71.1%
    (17.2 points), `gunshot` 52.5%–67.0% (14.5 points), `chainsaw` 18.8%–25.0% (6.2 points),
    total accuracy 55.6%–60.3% (4.7 points). **Any single run's per-class number should be read
    against this spread, not treated as a precise measurement of the model's true per-class
    recall.** Total accuracy is comparatively stable and is the more trustworthy number of the
    two; per-class recall is not, for every class except `chainsaw` (whose recall is
    consistently low rather than consistently variable). Run E (MFE, weights on — see the
    MFE-vs-MFCC section, now the live trained state of project 1109511) is a fifth data point in
    this same family: `elephant_call` lands exactly on Run D's 71.1%, and `ambient`/`chainsaw`/
    `gunshot` fall within a few points of Run D, inside the spread already documented here.
14. **A real MFE-vs-MFCC x `autoClassWeights` comparison on the current 4-class dataset was run
    2026-09-22** (see the Result section above) — the older DSP A/B section higher up this
    document predates the chainsaw-audit/ambient-pullback dataset and was never actually
    re-verified against it until this run. MFE remains superior on every class except `chainsaw`,
    where MFCC's edge (+4.1 to +6.2 points) does not offset its cost to `elephant_call` (-15.8
    points) and `gunshot` (-8.0 to -9.8 points). One of the two nominally-identical MFCC-weights-on
    training invocations in that section produced results matching the other to 16 significant
    figures of validation loss — almost certainly a cached/deduped job rather than an independent
    retrain, and is reported as one data point, not two.

## Reproducing

```
export EI_API_KEY=ei_...          # not stored in this repo
export EI_PROJECT_ID=1110036      # production (ADR 0032); use 1109511 only to reproduce the
                                  # historical MFE runs recorded in the Result sections above
export FREESOUND_API_KEY=...      # https://freesound.org/apiv2/apply/
python scripts/edge_impulse_upload_acoustic.py
python scripts/edge_impulse_train_acoustic.py
```

Both scripts accept `--clip-seconds <L>` to reproduce any window-sweep candidate against a
scratch project instead of production; `edge_impulse_train_acoustic.py` additionally accepts
`--dsp {mfe,mfcc}` and `--learn {scratch,transfer_kws_mobilenetv1_a1_d100,
transfer_kws_mobilenetv2_a35_d100,transfer_kws_conv2d_tiny}` to reproduce the DSP A/B and
transfer-learning attempts described above.

`ml/datasets/acoustic/raw/` (gitignored) caches downloaded and normalized audio so a re-run
does not re-fetch or re-query Freesound; `dataset_manifest.json` in this directory is
committed and records the exact clip selection — source, license, split, sha256 of the
normalized payload — so the dataset behind any reported number is reproducible from a fresh
clone even though the raw audio itself is not, and even though a live Freesound search could
return different results on a later run.

`edge_impulse_upload_acoustic.py --only <label>` (repeatable) restricts a run to specific
classes for a quick iteration — but it narrows the manifest write to only the touched
classes rather than merging into the prior manifest state, so a `--only`-restricted run
silently drops every other class's provenance tracking (see "Why the manifest's per-class
test count is a floor" above for how this actually played out). Run without `--only` before
trusting the manifest for anything beyond the classes you just touched.
`edge_impulse_train_acoustic.py --class-weights` overrides the locked `AUTO_CLASS_WEIGHTS =
False` default for a one-off re-test; `--skip-impulse` reuses the current impulse's
already-generated features instead of rebuilding the DSP block, useful for a training-only
A/B like the class-weights re-test above.
