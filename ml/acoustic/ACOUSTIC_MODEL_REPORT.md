# Acoustic model — accuracy investigation and deployment decision

**2026-09-23 · project 1109511 · 4-class acoustic classifier (ambient / chainsaw /
elephant_call / gunshot)**

> **Superseded as the production story (30 Sept 2026).** This report is about project **1109511**
> (named `ETX-A` when this was written, `ETX-A-test` since the 2026-10-03 rename) and its MFE
> lineage. That lineage was abandoned: it never reached the 80%-per-class
> bar, and production is now project **1110036** (now named `ETX-A`), impulse 19 — the PANNs Cnn10
> transfer model at 92.6% over the same 605-clip frozen split
> (`harness/results_eim_impulse19.json`, [ADR 0032](../../docs/decisions/0032-acoustic-production-project-is-1110036.md)).
> Everything below stands as written and is still the reason the MFE route was dropped — read it
> as the diagnosis that motivated the switch, not as a description of what ships.

This report explains why the deployed acoustic model scored far below what the same data
supports, what was wrong, what was fixed, and what the shipping configuration should be. It
is written for engineers on this project; it assumes the impulse design in
[README.md](README.md) and does not restate it.

The short version: **the fielded model was trained by a configuration that silently ignored
half of what it was told to do.** Two separate Edge Impulse Studio API behaviours discard
submitted training code while returning HTTP 200, a third setting is accepted, stored, echoed
back on read and never applied, and a fourth makes Studio's own test view report a different
model from the one Deploy will build. Once those are worked around, the measured wins can
actually be put into the model that ships.

> **Read every number here with section 5's error bar attached.** Edge Impulse's training is
> bit-reproducible on a given worker machine and *not* across machines, so one unchanged script
> produces a small set of different models depending on which machine the job lands on — measured
> here as seven runs of the shipping architecture yielding exactly three models. Overall-accuracy
> differences under **1.5 points**, and chainsaw differences under **4.4 points**, are not
> resolved by this evidence and are reported as ties. Nothing in the API exposes or controls the
> assignment, and re-running an arm does not average it out.

---

## 1. The problem, stated precisely

Every number in this report is scored on the **same 605 held-out clips** — the project's
testing set — unless explicitly marked otherwise. That matters, because the first apparent
"gap" was partly an artefact of comparing two different evaluation sets.

| model | features | overall | macro recall |
|---|---|--:|--:|
| local harness | its own MFE | 83.6% | 82.9% |
| local harness | Edge Impulse's MFE | 73.8% | 71.4% |
| Edge Impulse, as configured and deployed | Edge Impulse's MFE | **62.0%** | **60.5%** |

The middle row is the one that isolates the problem. The top and bottom rows differ in both
the front end *and* the trainer, so the 21-point spread between them is not a single effect;
feeding Edge Impulse's own features to the local trainer separates the two. Roughly 10 points
are the front end (section 3.2) and roughly 12 are everything Edge Impulse does after it
(section 6).

Edge Impulse's confusion matrix on those 605 clips (actual → predicted):

| actual \ predicted | ambient | chainsaw | elephant_call | gunshot | recall |
|---|--:|--:|--:|--:|--:|
| **ambient** | 145 | 4 | 38 | 49 | 61.4% |
| **chainsaw** | 10 | 29 | 23 | 6 | 42.6% |
| **elephant_call** | 7 | 8 | 42 | 1 | 72.4% |
| **gunshot** | 68 | 5 | 11 | 159 | 65.4% |

Two failures matter operationally rather than statistically:

- **68 gunshots were called ambient.** A missed gunshot is a missed poaching event.
- **chainsaw is the weakest class at 42.6%**, and chainsaw is the illegal-logging alert.

> **On the provenance of this baseline.** For most of this investigation the deployed
> model was quoted at 63.3% / 60.3%. That number is wrong, and the way it was wrong is
> worth recording. It came from a model-testing job that ran while the project happened to
> hold a *different*, hand-written expert script — Edge Impulse stores exactly one model per
> learn block, so a test job scores whatever was trained last, not whatever you believe is
> configured. The deployed visual configuration had in fact never been scored on the 605 at
> all. The figures above come from an arm that reproduces the stored `visualLayers`
> (`reshape(40) → conv1d(16,k3) → conv1d(32,k3) → flatten → dense(24)`) exactly, and were
> confirmed identical across three separate training jobs. Every comparison below is against
> 62.0% / 60.5%.

Both are the kind of error that costs a real response, which is the standard this project is
held to — DFO Kothamangalam has approved a field deployment and forest staff will act on
these alerts.

---

## 2. Four Edge Impulse Studio behaviours that invalidate configuration or measurement

These were found while trying to run controlled experiments, and each one silently produced a
result that looked valid. They are reported first because they invalidate conclusions, not
just performance.

### 2.1 `POST /jobs/train/keras/{id}` discards `script`

Passing a custom Keras script in the body of the training-job call returns success and trains
the **previous** model. Three experiment arms were run and interpreted before this was
caught; all three were measuring the same unchanged network.

### 2.2 `POST /training/keras/{id}` discards `script` whenever any training parameter
accompanies it

This is the more dangerous of the two, because it is the documented way to set a script. A
body of `{"script": ..., "mode": "expert", "trainingCycles": 120}` returns HTTP 200, reports
no error, and stores a script **regenerated from `visualLayers`** — silently throwing away
the submitted code. Only a bare `{"script": ...}` with no other key persists.

Probed directly:

```
BEFORE                 mode=expert len=2136 dropout=False
  script_only          mode=expert  marker=True   dropout=True   len=1708
  mode_plus_script     mode=expert  marker=True   dropout=True   len=1713
  full_body            mode=expert  marker=False  dropout=False  len=2136
```

### 2.3 The visual-mode `dropoutRate` is inert

The locked learn block stores `dropout 0.25 / 0.25 / 0.4`. The Keras script Edge Impulse
generates from that config contains **no `Dropout` layer at all**. The value is accepted,
stored, and returned on read; it never reaches the model.

Measured by training two scripts that differ only in three `Dropout` layers:

| arm | int8 accuracy | macro F1 | ambient | chainsaw | elephant | gunshot |
|---|--:|--:|--:|--:|--:|--:|
| no dropout (byte-identical to what the visual config generates) | 61.25% | 0.579 | 61.2 | 36.1 | 75.0 | 63.2 |
| with dropout | 63.96% | 0.616 | 73.3 | 52.3 | 70.3 | 52.6 |

So **every visual-mode run in the project's history trained an unregularised network**,
whatever its stored configuration claims.

**But the bug turned out not to matter, and the table above is on the wrong evaluation set.**
Those figures are Edge Impulse's internal validation metrics, computed on a ~20% slice of the
*training* pool. Re-scored on the canonical 605 clips, dropout is worth nothing:

| arm | head | overall | macro | ambient | chainsaw | elephant | gunshot |
|---|---|--:|--:|--:|--:|--:|--:|
| deployed config, no dropout (F0) | Flatten | 62.0% | 60.5% | 61.4 | 42.6 | 72.4 | 65.4 |
| expert script, dropout (D3) | Flatten | 62.5% | 61.3% | 64.0 | 38.2 | 79.3 | 63.8 |
| expert script, dropout (X2) | Flatten | 63.3% | 60.3% | 75.4 | 47.1 | 62.1 | 56.4 |

Dropout on the stock `Flatten` head is worth between +0.5 and +1.3 points — but section 5.4
later measured a 1.5-point span across identical runs, so **this difference is inside the noise
and is not an established effect.** It is left in the table because the arms were run and the
numbers are real; the inference that dropout helps here is what does not survive. This corrects an earlier reading
of mine twice over: first the +2.7 figure, which was Edge Impulse's internal validation slice
rather than the 605, and then the claim that dropout was worth nothing, which compared
against the mis-attributed 63.3% baseline. Dropout matters much more once the head is also
fixed — see section 6.

### 2.4 Methodological consequence — marker verification

Because a clobbered script is indistinguishable from a successful one by inspection (Edge
Impulse's regenerated script also has no `Dropout`, so substring-checking for `Dropout` proves
nothing), every arm in this report embeds a unique marker comment and **verifies it twice** —
after the write, and again after the training job starts. Any arm whose marker is missing is
abandoned rather than reported. Findings produced before this check was in place were
discarded.

---

### 2.5 `POST /jobs/classify` ignores `selectedModelType`

`POST /{pid}/training/keras/{id}` with `{"selectedModelType": "float32"|"int8"}` is accepted and
read-back confirms the field changed. Model testing then ignores it. Selecting each precision in
turn and re-running `POST /{pid}/jobs/classify` against the same trained weights returns results
that are identical to the digit on every class:

| `selectedModelType` | overall | ambient | chainsaw | elephant_call | gunshot |
|---|--:|--:|--:|--:|--:|
| float32 | 79.8% | 77.5 | 57.4 | 86.2 | 86.8 |
| int8 | 79.8% | 77.5 | 57.4 | 86.2 | 86.8 |

Both jobs genuinely ran (distinct job ids, 2.0 min and 0.7 min). The same model's *internal
validation* differs by 11.0 points between the two precisions, so identical test scores are not a
property of the model.

**Which precision does it actually run?** An int8 model's softmax outputs are dequantised from a
uint8 tensor and therefore land on a grid of about 1/256. Across the 2,420 returned scores there
are **1,621 distinct values**, and only 16% sit on a 1/256 grid — which is roughly what the zeros
and saturated values alone account for. Values such as 0.89564 and 0.65516 are not reachable on
that grid. Model testing runs the **float32** model, always.

Two consequences, and they point in opposite directions:

- **Good:** every 605-clip number in this report is a float32 number, measured consistently. The
  leaderboard is internally sound and no arm ranking is a quantisation artefact.
- **Bad:** the report cannot measure int8 on the 605 at all, and Edge Impulse's UI presents these
  as the model's accuracy without saying which precision produced them. Anyone who reads 82.6% off
  the test view and then deploys int8 ships a model that Edge Impulse's own validation scores
  **11.0 points lower**. That is a trap in the tool, not in this project, and section 7 avoids it
  rather than solving it.

## 3. What the gap is actually made of

Each component was isolated with everything else held fixed.

### 3.1 Ruled out

| candidate | verdict |
|---|---|
| audio bytes differ | identical, correlation 1.000000 |
| dataset size or split differs | identical: 3,688 / 605, same per-class counts |
| classifier head (Flatten vs global average pooling) | ~~no effect~~ **overturned — worth +7.4 points on Edge Impulse; see section 6** |
| int8 quantization | ~~no effect~~ **overturned — the two scores were identical because model testing ignores the setting; see section 2.5** |
| evaluation-set confound | real but small: 63.96% internal vs 62.0% on the 605 |

The int8 result was originally stated here as the deployment decision. It was measured on
the wrong device, and the conclusion it supported does not survive being measured on the right
one. Both versions are kept below, because the mistake is instructive.

**What was measured (and quoted for most of this investigation):**

| build | flash | RAM | latency (Cortex-M4F @ 80 MHz) | accuracy |
|---|--:|--:|--:|--:|
| float32 | 387,164 B | 155,096 B | 605 ms | 0.6396 |
| int8 | 101,920 B | 41,624 B | 37 ms | 0.6396 |

That reads as an easy call — 3.8× smaller, 16× faster, no accuracy cost, ship int8.

**Why it is the wrong device.** Cortex-M4F @ 80 MHz is simply the first entry in Edge Impulse's
profile list; nothing selected it. ADR 0007 §4 puts acoustic classification on the **QRB2210
MPU**, running the Edge Impulse aarch64 artifact under Linux, with the STM32 only extracting
scalar features and deciding whether to escalate. (ADR 0009's "continuous on-MCU classifier"
concerns *capture*, not classification, and is still `proposed`.)

**Edge Impulse profiles the actual board.** `arduino-unoq` is in its target list and is this
project's default target (`isDefault: true`) — so the right numbers were available the whole
time and simply were not read. For the current best model:

| build | EON flash | EON RAM | latency (`arduino-unoq`) | latency (Cortex-M4F) |
|---|--:|--:|--:|--:|
| float32 | 62,880 B | 156,496 B | **1 ms** | 534 ms |
| int8 | 61,008 B | 43,608 B | **5 ms** | 237 ms |

On the target, **every argument for int8 evaporates.** Flash is within 3% (61 KB against 63 KB),
not 3.8× apart. Its RAM advantage — 44 KB against 156 KB — is real but meaningless on a Linux
MPU with gigabytes. And it is not faster; if anything it is slower, because an A53 with NEON
runs float32 well and int8 adds dequantisation work. Both sit in single-digit milliseconds
against a **10-second** analysis window, so latency does not discriminate between them at all.

Two cautions on those figures. They are integer-millisecond estimates in a range where integer
rounding is a large fraction of the value, so "1 ms against 5 ms" should be read as *both are
negligible*, not as a 5× speedup for float32. And they remain Edge Impulse's estimates:
**no on-device measurement has been taken**, because board access is closed. An on-target
benchmark is still outstanding before any latency claim is made in project docs — but it is
now outstanding for a device the model will actually run on.

The live consequence is that precision should be chosen on **accuracy alone**. The direct A/B this
paragraph once promised turned out not to be possible: section 2.5 shows model testing silently
ignores `selectedModelType` and always runs float32, which is also the real explanation for the
"float32 and int8 both 0.6396" row above — that was never evidence that quantisation is free.

What can be measured is Edge Impulse's internal validation, which reports the two precisions
separately on the same weights. On the current architecture the gap is large and one-directional:

| precision | internal val accuracy | validation loss | chainsaw precision | ambient recall |
|---|--:|--:|--:|--:|
| float32 | **85.5%** | 0.538 | **72.7** | **83.8** |
| int8 | 74.5% | 2.387 | 53.0 | 70.3 |

A 4.4× rise in validation loss is not rounding error. The likely cause is the
`LayerNormalization` layer added in section 6.2 — it computes a mean and a reciprocal square root,
which per-tensor quantisation handles badly. The fix that bought this model 7.4 points is the same
change that made it quantisation-sensitive, which is worth knowing but does not argue for reverting
it: on this deployment, nothing requires int8.

### 3.2 The MFE front end — ~6 points, and not removable

Edge Impulse's own computed feature matrix was downloaded and the identical network trained on
it versus on the local features, over the same rows and the same group-aware split (2,419
groups, 435 held out, **zero straddling**):

| features | class weights | overall | macro | ambient | chainsaw | elephant | gunshot |
|---|---|--:|--:|--:|--:|--:|--:|
| Edge Impulse MFE | on | 72.3% | 73.7% | 69.1 | 79.5 | 75.0 | 71.2 |
| Edge Impulse MFE | off | 75.1% | 73.3% | 75.3 | 60.5 | 77.7 | 79.8 |
| local, per-clip standardised | on | 78.4% | 79.0% | 71.2 | 81.1 | 78.1 | 85.7 |
| local, per-clip standardised | off | 79.7% | 76.5% | 82.4 | 53.7 | 84.4 | 85.5 |
| local, Edge Impulse-style normalisation | on | 79.8% | 81.1% | 69.9 | 76.3 | 93.8 | 84.3 |
| local, Edge Impulse-style normalisation | off | 80.4% | 79.4% | 73.0 | 60.5 | 94.9 | 89.0 |

Edge Impulse's front end costs roughly **6 points overall and 5 macro**. This is the one
component that cannot be swapped: the MFE block is what runs on the device, so whatever it
produces is what the fielded model is fed.

A caveat that corrects an earlier claim in this project's notes: the local
"Edge-Impulse-style" normalisation is **not** Edge Impulse's transform. Correlation between
the two feature sets is **0.174 mean / 0.145 median**. Any earlier result labelled as
reproducing Edge Impulse's front end was not doing so, and the comment in
[baseline_mfe.py](harness/baseline_mfe.py) has been corrected accordingly.

### 3.3 Class weights — the most robust finding

Turning class weights on is worth roughly **+19 points of chainsaw recall** for about 2.5–2.8
points of overall accuracy. This has now been measured **three independent times on three
different feature sets**, including on Edge Impulse's real features (chainsaw 60.5% → 79.5%).

Section 6.2 confirms this on Edge Impulse's own trainer once the architecture is fixed, and on
better terms than stated here: at `beta=0.5` the chainsaw gain is +17.6 and overall accuracy
*rises* by 1.5 rather than falling. The "2.5–2.8 points of overall accuracy" cost is specific to
full inverse-frequency weighting (`beta=1.0`), which section 6.2 measures at −2.8.

**The locked configuration has `autoClassWeights: False`.** For a deployment whose worst class
is the illegal-logging alert, that is the wrong default — overall accuracy is not the quantity
the field cares about.

---

## 4. Hypotheses that were wrong

Two are recorded in this section; a third — the `win_size` sliding-mean mechanism, the most
specific and most confidently argued of the three — is in section 6.6, where it sits next to the
evidence that killed it. All three were mine, all three were plausible, and each was falsified by
the experiment built to confirm it. They are recorded because the negative results narrowed the
search more than the positive ones did, and because a report that keeps only its successful
hypotheses gives the reader no way to judge how much the successful ones are worth.

### 4.1 "Edge Impulse's internal validation split leaks, and that corrupts checkpoint selection"

Edge Impulse carves its validation set out of the training pool at random, with no notion of
recording groups. This corpus has many near-duplicate slices per source recording, so the
carve genuinely does leak: measured directly, **280 of the groups had members on both sides**.
The hypothesis was that best-checkpoint restore would then select a checkpoint fitted to
material the model had effectively already seen.

Four arms, identical network, identical Edge Impulse features, all scored on the same
group-disjoint 674 clips:

| arm | n_train | overall | macro | groups shared with val | chosen epoch |
|---|--:|--:|--:|--:|--:|
| all_final — train on everything, keep final weights | 3014 | 72.3% | 73.7% | — | — |
| leaky_final — random 80%, final weights | 2411 | 69.3% | 72.0% | — | — |
| leaky_bestckpt — random 80%, best checkpoint on leaky val | 2411 | **72.8%** | 72.5% | 280 / 265 | 90 / 111 |
| clean_bestckpt — group-disjoint 80%, best checkpoint on clean val | 2449 | 72.3% | 71.8% | 0 / 0 | 55 / 77 |

Holding out 20% of the pool costs 3.0 points (`all_final` → `leaky_final`). Best-checkpoint
restore hands them back (`leaky_final` → `leaky_bestckpt`, +3.5). And selection on a *leaky*
validation set performs no worse than selection on a clean one — 72.8% versus 72.3%, inside
noise, despite 280 leaking groups.

**Net effect of Edge Impulse's entire train/validate/restore procedure: approximately zero.**
The leakage is real and would matter for reading its reported validation numbers, but it is
not costing the deployed model accuracy.

### 4.2 "Class weights are the most robust lever available"

> **Overturned by section 6.2.** This section's conclusion — that weighting does not transfer to
> Edge Impulse — was measured against the unnormalised `Flatten` head, which sections 6.1 and 6.2
> then showed to be the defect. Re-run on the fixed architecture, `beta=0.5` beats unweighted on
> *every* class, including the `ambient` degradation this section gives as the reason to reject
> it. The reasoning below is left in place because the mistake is the point: the arms were sound,
> the baseline they were compared against was not.

On the local harness this reproduced three times on three feature sets: roughly +19 points of
chainsaw recall for 2.5–2.8 points of overall accuracy, including on Edge Impulse's own
features (chainsaw 60.5% → 79.5%). The locked configuration has `autoClassWeights: False`, so
this looked like a clear, cheap win for the illegal-logging alert class.

**It did not transfer.** Trained through Edge Impulse's own trainer and scored on the 605:

| arm | weighting | head | overall | macro | ambient | chainsaw | elephant | gunshot |
|---|---|---|--:|--:|--:|--:|--:|--:|
| baseline (deployed) | none | Flatten | **63.3%** | 60.3% | 75.4 | 47.1 | 62.1 | 56.4 |
| D1 | full inverse-freq | Flatten | 57.5% | 59.2% | 58.1 | 60.3 | 63.8 | 54.7 |
| D2 | full inverse-freq | GAP | 56.9% | **62.7%** | 44.1 | 58.8 | 86.2 | 61.7 |
| E1 | inverse-freq^0.25 | Flatten | 61.0% | 62.4% | 52.5 | 44.1 | 84.5 | 68.3 |

Every weighted arm lands *below* the unweighted baseline on overall accuracy, and the cost
falls on `ambient` — the majority class, whose errors are exactly the ones that become **false
alarms in the field**. Macro recall does not price that in, which is why macro alone is the
wrong objective for this deployment: D2 has the best macro of any model tested and would fire
a spurious alert on 56% of ambient clips.

The last point stands and is worth keeping — macro alone remains the wrong objective. The
inference drawn from it did not: the `ambient` collapse was caused by the unregularised
92,000-parameter head these arms were built on, not by weighting. On the normalised pooled head,
`beta=0.5` costs no `ambient` accuracy at all (72.5 against 72.0 unweighted). Only `beta=1.0`
reproduces the trade this section describes, and even then at 62.7 rather than 44.1.


## 5. Edge Impulse's training is deterministic per machine, not per script

> **This section has now been wrong twice, and it is the most load-bearing section in the report.**
> The original claim was "training is deterministic, so every arm difference is signal". The first
> correction blamed dropout. **That correction was also wrong**, and it is left visible below in
> 5.3 because the way it failed is the useful part. The mechanism is now established from Edge
> Impulse's own training logs rather than inferred from scores: training is bit-reproducible on a
> given worker machine, and Edge Impulse schedules jobs across machines of different speeds.

Worth establishing before any of the above is believed, because it decides whether the
differences between arms are effects or noise.

The same expert script was trained three times. Each run was a separate training job and a
separate model-testing job:

| run | training job | overall | macro | ambient | chainsaw | elephant | gunshot |
|---|--:|--:|--:|--:|--:|--:|--:|
| V1 | 54059642 | 62.0% | 60.5% | 61.4 | 42.6 | 72.4 | 65.4 |
| V2 | 54059764 | 62.0% | 60.5% | 61.4 | 42.6 | 72.4 | 65.4 |
| V3 | 54059803 | 62.0% | 60.5% | 61.4 | 42.6 | 72.4 | 65.4 |

Identical to the last reported digit, on every class. That much is real and reproducible. The
conclusion drawn from it — "run-to-run variance is zero, so every arm difference in this report is
signal" — does not follow, and is false.

### 5.1 Seven runs of one script produced exactly three models

H2, the best arm in this report, was retrained seven times from a byte-identical script (only a
marker comment differs, and that marker is read back and verified before every job). The DSP
configuration was confirmed unchanged each time (`win_size` 101, `noise_floor_db` -52,
`frame_length` 0.02, `frame_stride` 0.020835, `num_filters` 40, `fft_length` 256), and the split
was confirmed unchanged at n=605 with per-class totals 236 / 68 / 58 / 243.

The outcomes are not a spread. They are three points, each hit repeatedly:

| H2 run | training job | median ms/step | epoch-120 loss | 605 overall | chainsaw |
|---|--:|--:|--:|--:|--:|
| round H (original) | — | — | — | **82.6%** | 44.1 |
| restore | — | — | — | 81.2% | 48.5 |
| variance 1 | 54065683 | 33 | 0.2542 | 82.0% | 47.1 |
| variance 2 | 54066399 | 18 | 0.2850 | 81.2% | 48.5 |
| variance 3 | 54066906 | 18 | 0.2850 | 81.2% | 48.5 |
| variance 4 | 54067320 | 19 | 0.2850 | 81.2% | 48.5 |
| variance 5 | 54067799 | 14 | 0.2659 | **82.6%** | 44.1 |

Seven runs, three distinct outcomes: 81.2% four times, 82.6% twice, 82.0% once. Runs that share an
outcome share it *exactly* — same overall, same macro, same four per-class recalls, and the same
confusion matrix cell for cell. Variance run 5 reproduced the original round-H model to every
digit, four rounds and several days later.

**And the median ms/step column predicts which model you get.** Three speed bands — 33, 18–19, and
14 ms/step — map one-to-one onto the three models. This is not a statistical correlation over many
points; it is an exact partition of seven runs into three groups by a variable that has nothing to
do with the model and everything to do with which machine Edge Impulse scheduled the job on.

### 5.2 The mechanism, read out of the training logs

Scores alone cannot distinguish "stochastic training" from "deterministic training on
non-identical machines", so the question was taken to the jobs' own stdout. Two things had to be
established first, because either would have invalidated the reading:

- **The scores are not cached.** Four identical results in a row is what a stale result cache looks
  like. It is not one: starting a training job *clears* the stored test result, and
  `/{pid}/classify/all/result` returns `No model testing results found, run 'startClassifyJob'
  first` while a training job is in flight. Every score therefore comes from a classify job run
  after that model was trained.
- **Edge Impulse returns job stdout newest-first.** A first pass at this analysis reported
  "final" validation accuracies near 0.44 for models that score 0.87 — those were epoch 1, read off
  the wrong end. The logs are reversed before use.

With that settled, the per-epoch trajectories answer the question outright:

| comparison | result |
|---|---|
| variance 2 vs variance 3 | **identical at all 120 epochs** — same loss, accuracy, val_loss, val_accuracy |
| variance 1 vs variance 2 | identical at epoch 1; **diverge at epoch 2** |

The epoch-2 divergence is `loss 1.0855` against `1.0856` — one unit in the fourth decimal, which is
simply the precision the log prints at. Over the following 118 epochs that difference compounds
into a different model and 1.4 points of test accuracy.

An identical epoch 1 is the decisive detail. If the random seed, the weight initialisation, the
data shuffle order, or **the dropout masks** differed between two runs, epoch 1 would already
differ. It does not. Edge Impulse seeds all of them. What differs is the arithmetic: the same
operations, reassociated differently by a machine with a different vector width or thread count,
give answers that agree to about four decimals and not beyond. That is ordinary floating-point
non-associativity, and no setting on this side prevents it.

The expert-script template makes Edge Impulse's own awareness of this explicit — it injects an
`args.ensure_determinism` flag that the template branches on:

```python
if not ENSURE_DETERMINISM:
    train_dataset = train_dataset.shuffle(buffer_size=BATCH_SIZE*4)
```

That flag is set by the job harness, not by anything this project can pass through the API.

### 5.3 Why "dropout" was the wrong answer, and why that matters

The first correction to this section blamed dropout: F0, the arm that produced three identical
runs, has no `Dropout` layers, while every architecture from section 6 onward has three of them.
The story was that dropout masks are drawn from an unseeded RNG, so F0 was reproducible and
everything after it was not.

It fitted every number available at the time and it was wrong. Variance runs 2, 3 and 4 are
bit-identical to each other *with all three dropout layers active*, which a stochastic mask cannot
produce. F0's three identical runs are explained by the same thing as theirs: they ran
back-to-back and landed on the same machine.

The error is worth naming because it is the third instance of one pattern in this report, after
section 4.2's wrong baseline and section 6.4's cross-freeze comparison: **an explanation was
adopted because it was consistent with the observations, without a test that could have
distinguished it from the alternatives.** "Dropout is unseeded" and "the machine changed" predict
the same scores. They predict completely different *training logs*, and the logs were available the
whole time.

### 5.4 What it costs, and how to read the leaderboard

A standard deviation is the wrong summary here and is not used. Seven runs gave a mean of 81.7%
and an SD of 0.7, but the underlying distribution is three discrete points, not a bell curve, and
the weighting between them depends on Edge Impulse's scheduler rather than on anything measurable.
Quoting 0.7 would imply a precision that does not exist.

The usable figure is the **observed span across identical runs**, and it differs sharply by metric:

| metric | span across 7 identical runs |
|---|--:|
| overall accuracy | **1.5 points** (81.2–82.6) |
| macro | 1.1 points (75.4–76.5) |
| ambient | 2.1 points |
| chainsaw | **4.4 points** (44.1–48.5) |
| elephant_call | 5.2 points |
| gunshot | 3.7 points |

Two consequences for reading sections 3 to 6:

- **Overall-accuracy gaps under about 1.5 points are not established differences.** H2's 2.6–2.8
  point margin over I2/I3 clears that bar, but only just, and the span above was measured on one
  arm — another arm could be wider.
- **Per-class claims need a much larger error bar than overall claims, and the chainsaw ones need
  the largest.** chainsaw recall moved 4.4 points between models trained from the same script.
  Most of the per-class chainsaw orderings in sections 6.2 and 6.5 sit inside that, and should be
  read as unresolved rather than as effects.

A practical note for anyone repeating this work: **re-running an arm is not an independent
sample.** Four of these seven runs returned the same model. Averaging repeats does not average out
the machine, because the repeats may all be on one machine, and nothing in the API lets you
request or even observe which one you got — the `ms/step` figure in the training log is the only
visible proxy, and it is only comparable between runs of the *same* architecture.

What survives unchanged is anything resting on large gaps or on non-Edge-Impulse evidence: the
Flatten-vs-pooling result (+7.4), the int8 quantisation gap (11.0 on internal validation), the
local `win_size` falsification in section 6.6 (run locally with fixed seeds), and section 6.4's
finding that the harness and Edge Impulse score the same on the canonical split — a 0.2-point
difference that was already being reported as a tie.

### 5.5 The baseline error, which still stands — on different reasoning

Determinism is also what exposed the baseline error described in section 1, and the chain is worth
following because the lesson survives even though its first link has broken twice.

The expert-mode reproduction of the deployed config scored 62.0% against a supposed 63.3%. The
original argument was: variance is zero, so 1.3 points cannot be noise, so one of the two numbers
is mislabelled. **That argument is no longer sound.** Three identical F0 runs show only that those
three runs shared a machine; they do not bound what F0 would score on a different one, and
section 5.1 has since measured a 1.5-point span for H2 across machines. 1.3 points is inside it.

The conclusion nevertheless stands, because it never depended on that argument once it was
checked. Two pieces of direct evidence settle it, both independent of variance:

- The job history places the 63.3% test job inside a window when an **unrelated expert script** was
  loaded in the learn block. Edge Impulse stores one model per block and a test job scores whatever
  was trained last, so that number was never measuring the deployed configuration.
- Reading the stored `visualLayers` back confirms F0 reproduces the deployed configuration exactly,
  which makes 62.0% the correct baseline for it.

The 1.3-point discrepancy was the *prompt* to look. It was not, and should not have been, the
proof.

My first explanation was wrong: I attributed it to the label-counting loop that the weighted
arms need, which iterates `train_dataset` before training and advances the input pipeline's RNG
state. That was testable, so it got tested — arm F0 removed the loop entirely and still returned
62.0%, to every digit. The explanation was dead.

The real cause was an ordering assumption. Edge Impulse stores one model per learn block, so a
model-testing job scores whatever was trained most recently, regardless of what the block's
stored configuration says. Checking the job history against the sequence of scripts written that
day placed the 63.3% test job inside the window when an unrelated expert script was loaded. The
deployed visual configuration had never been tested at all. Reading the stored `visualLayers`
back confirmed that F0 reproduces it exactly, which makes 62.0% the true baseline.

The general form of this, which applies to anyone automating against this API: **a result is
attributable only if you can prove what was in the block when the job ran.** Marker verification
(section 2.4) does that for training jobs. It needs to extend to testing jobs too.

## 6. Where the accuracy actually goes

The testing set's DSP features turned out to be downloadable after all —
`/dsp-data/{dsp}/x/testing` returns a `(605, 19120)` `.npy`. An earlier attempt to read it had
failed only because the response is binary and was being decoded as UTF-8, which is why the
front-end test in section 3.2 had to carve a holdout out of the training pool instead.

With those features, the comparison has no confound left: identical features, identical 3,688
training clips, identical 605 testing clips, only the trainer differs.

| trainer | overall | macro | ambient | chainsaw | elephant | gunshot |
|---|--:|--:|--:|--:|--:|--:|
| local harness (3 seeds) | **73.8%** (sd 3.9) | 71.4% | 78.2 | 41.2 | 92.0 | 74.3 |
| local harness, β=0.5 weighting | 74.3% (sd 4.4) | 71.9% | 80.2 | 45.6 | 88.5 | 73.3 |
| local harness, β=1.0 weighting | 71.6% (sd 3.8) | **72.5%** | 76.0 | 58.8 | 88.5 | 66.8 |
| Edge Impulse | 62.0% | 60.5% | 61.4 | 42.6 | 72.4 | 65.4 |

**~11.8 points are lost inside Edge Impulse's training, on identical inputs.** Section 4.1
already ruled out its split and checkpoint policy. What remains is the network Edge Impulse
generates from the visual config:

| | head | head parameters | regularisation |
|---|---|--:|---|
| Edge Impulse generated | `Flatten` → `Dense(24)` | ~92,000 | none (the `dropoutRate` setting is inert) |
| local harness | `GlobalAveragePooling1D` → `Dense(24)` | ~768 | dropout 0.25 / 0.25 / 0.4 |

Edge Impulse's default head carries roughly **120× the parameters** of the local one, on a
3,688-clip corpus, with no regularisation at all. That is a textbook overfitting
configuration.

### 6.1 The head, measured

Three arms, identical in every other respect, each an expert script trained through Edge
Impulse and scored on the 605:

| arm | head | dropout | overall | macro | ambient | chainsaw | elephant | gunshot |
|---|---|---|--:|--:|--:|--:|--:|--:|
| F0 — reproduces the deployed config | `Flatten` | no | 62.0% | 60.5% | 61.4 | 42.6 | 72.4 | 65.4 |
| F1 | `GlobalAveragePooling1D` | yes | 69.4% | 64.6% | 80.5 | 33.8 | 77.6 | 66.7 |
| **F2** | `GlobalAveragePooling1D` | no | **70.9%** | **66.4%** | 74.6 | 44.1 | 72.4 | 74.5 |

**Replacing the head is worth +8.9 points overall and +5.9 macro** — by a wide margin the
largest single effect found in this investigation, and it is a one-line change to the network.

Two things follow that were not obvious beforehand:

- **Dropout's sign flips with the head.** On the 92,000-parameter `Flatten` head dropout helps
  slightly (+0.5 to +1.3, section 2.3). On the 768-parameter pooled head it *hurts* by 1.5.
  The small head is already constrained; 0.25/0.25/0.4 on top of it over-regularises. So the
  inert-`dropoutRate` bug, which consumed a large share of this investigation, turns out to be
  the wrong thing to have been chasing — in the configuration that should actually ship, the
  setting Edge Impulse fails to apply is one you would not want applied.
- **Section 3.1's dismissal of the head was wrong.** That row recorded "no effect — 83.2 vs
  82.9 macro", measured on the local harness. It does not generalise: the local harness
  standardises its inputs, and on that footing the head genuinely does not matter much. On
  Edge Impulse's unstandardised features it matters enormously. A negative result measured in
  one pipeline was carried into another without re-testing, and it hid the main finding for
  most of a day.

### 6.2 Per-clip standardisation, and the weighting sweep redone

The head fix left the model still behind the local harness, and one difference remained: the
harness standardises every clip to zero mean and unit variance before training, while the
generated Edge Impulse script feeds raw MFE energies in. That matters more on this corpus than
it would on most. MFE output is a log energy, so a recording's gain appears as a near-constant
offset across all 40 x 478 bins, and class is correlated with source dataset here — the whole
reason ADR 0025 exists. Absolute level is therefore a shortcut that separates the training
classes and does not survive contact with the 605, which is drawn differently.

The normalisation goes *inside the model*, not into preprocessing. The deployable artifact is
whatever Edge Impulse converts, so a preprocessing step living in a training script would
simply not exist on the device and the model would be fed unnormalised features in the field.
As a graph layer it is part of the exported TFLite and runs on-device for free.

It has to be `LayerNormalization(axis=[1, 2], center=False, scale=False)`, not a `Lambda`. The
first attempt used a `Lambda` wrapping `tf.reduce_mean` and died in conversion with
`'dict' object has no attribute 'reduce_mean'`: Edge Impulse deserialises the model from its
config before converting it, and a `Lambda`'s closure over `tf` does not survive that round
trip. `LayerNormalization` is a first-class serialisable layer and is also a single fused op
for the converter rather than a six-op subgraph.

| arm | normalisation | head | dropout | weighting | overall | macro | ambient | chainsaw | elephant | gunshot |
|---|---|---|---|---|--:|--:|--:|--:|--:|--:|
| F0 — deployed baseline | — | `Flatten` | — | — | 62.0% | 60.5% | 61.4 | 42.6 | 72.4 | 65.4 |
| G2 | LN | `Flatten` | — | — | 67.8% | 58.2% | 77.1 | 36.8 | 46.6 | 72.4 |
| F2 | — | GAP | — | — | 70.9% | 66.4% | 74.6 | 44.1 | 72.4 | 74.5 |
| G0 | LN | GAP | — | — | 74.5% | 68.7% | 72.0 | 35.3 | 81.0 | 86.4 |
| G4 | LN | GAP | — | beta=1.0 | 73.2% | 71.5% | 62.7 | **63.2** | 74.1 | 86.0 |
| **G3** | LN | GAP | — | beta=0.5 | 76.0% | 71.5% | 72.5 | 52.9 | 74.1 | **86.4** |
| **G1** | LN | GAP | yes | — | **77.9%** | **72.4%** | 88.6 | 36.8 | 87.9 | 76.5 |

Read against F0, the effects decompose cleanly: normalisation alone **+5.8** (G2), the head
alone **+8.9** (F2), both together **+12.5** (G0), and dropout on top **+15.9** (G1). G1 at
77.9% is 4.1 points *above* the local harness's 73.8% on byte-identical features — the gap this
report set out to explain is not merely closed but reversed.

**Dropout has now changed sign twice.** It helped slightly on the 92,000-parameter `Flatten`
head (section 2.3), cost 1.5 points on the pooled head (F2 against F1), and is worth +3.4 once
normalisation is present (G1 against G0). The reading that fits all three: normalisation removes
a per-recording offset the network was otherwise free to memorise, which leaves more genuine
signal available to overfit, so regularisation starts paying again. The practical consequence is
that "dropout helps" is not a finding at all — only the interaction is.

**Section 4.2's rejection of class weighting was an artifact of the broken architecture.** That
section tested weighting on the unnormalised `Flatten` head, found every weighted arm below
baseline on overall accuracy, and concluded the lever did not transfer. Re-run on the fixed
architecture, beta=0.5 is simply free: it beats unweighted G0 on *every* class, including the
`ambient` majority class whose degradation was section 4.2's stated reason for rejecting it.
Only beta=1.0 shows the predicted trade, and it is a real one — another +10.3 chainsaw for 9.8
points of `ambient`, which is the class whose errors become false alarms.

### 6.3 Every lever in this report was first measured wrong

Three levers in this report were first measured wrong, in three different ways:

| lever | first measured | actually worth | why the first answer was wrong |
|---|---|---|---|
| classifier head | "no effect", 83.2 vs 82.9 macro | **+8.9 overall** | measured on the local harness, which standardises its inputs — on that footing the head genuinely does not matter |
| per-clip standardisation | +13.0 overall | **+3.6 to +7.0** | measured locally; transferred at roughly a third to a half of its local size |
| class weighting | "did not transfer", every arm below baseline | **+1.5 overall, +17.6 chainsaw** at beta=0.5 | measured on Edge Impulse, but against the broken unnormalised `Flatten` head |

Two of those were measured in the wrong *pipeline* and one in the wrong *configuration*, and
the errors run in both directions — the head was underestimated, standardisation overestimated,
weighting inverted. One caveat on the third row: class weighting's **+1.5 overall** sits exactly
at the span section 5.4 measures for a single arm, so that part of it is not an established
effect; its **+17.6 chainsaw** is well outside even the 4.4-point chainsaw span and is real.

The common cause is that every lever was evaluated against a baseline that was itself defective,
which makes each conclusion valid only relative to a configuration that no longer exists. This is
a different failure from section 5's: that one is a property of Edge Impulse's scheduler and
cannot be fixed from here, whereas this one was self-inflicted and is entirely avoidable.

The operational rule this produces, and the one thing in this report most worth carrying
forward: **a lever is only measured once it has been measured in the pipeline and the
configuration that will ship, and it must be re-measured whenever either of those changes.**
The prediction in section 6.2 was recorded before the arms ran precisely so it could be scored
honestly; it was wrong by 6 to 9 points, and that is the evidence for this rule rather than an
aside to it.

### 6.4 The ceiling of this front end, measured against this repository's own models

Everything above optimises one pipeline: Edge Impulse's MFE block feeding a small CNN. It is worth
asking what that pipeline is worth *as a pipeline*, and this repository can answer that, because
`ml/acoustic/harness/` evaluates other approaches on this same corpus.

**Split provenance has to be tracked per row, and it is the reason this table is smaller than it
could be.** `split.json` has been re-frozen more than once, and the harness result files disagree
about the test-set size: n=630, n=607 and n=605 all appear. That is not cosmetic. The MFE control
scores `chainsaw` at **51.3%** on the n=630 freeze and **77.9%** on the n=607 freeze — a 26-point
swing on the *same code*, because n≈70 is small enough that which recordings land in test dominates.
Any cross-model chainsaw claim that mixes freezes is measuring the freeze.

So only rows carrying n=605, the current freeze and the one every Edge Impulse number in this report
uses (ambient 236, chainsaw 68, elephant_call 58, gunshot 243; train 3,688), are comparable here:

| model | n | overall | chainsaw recall | chainsaw precision |
|---|--:|--:|--:|--:|
| Cnn14 + MLP (AudioSet-pretrained, 81M params), `results_base_corrected.json`, 5 seeds | 605 | **93.3%** | **86.5%** | 85.5% |
| MFE + small CNN, local harness (per-clip standardisation, β=1.0, 2 seeds) | 605 | 82.8% | 76.5% | — |
| **MFE + small CNN, Edge Impulse (best arm so far, H2)** | 605 | **82.6%** | 44.1% | — |
| MFE + small CNN, Edge Impulse (best chainsaw, H1) | 605 | 76.4% | **66.2%** | — |
| MFE + small CNN, Edge Impulse (as deployed, F0) | 605 | 62.0% | 42.6% | — |

For reference but **not** directly comparable, on the superseded n=607 freeze: Cnn6 + MLP 91.7%
overall with chainsaw 80.3% recall at 92.0% precision.

The local MFE control row is new, and it settles the comparison the rest of this section was built
on. Earlier drafts contrasted the harness's 80.6% (n=607) against Edge Impulse's 77.9% (n=605) and
read the difference as a pipeline gap. Re-run on the canonical 605 with only the normalisation
swapped, the harness scores **82.8%** against H2's **82.6%** — a 0.2-point difference, which is to
say none. **On overall accuracy the Edge Impulse pipeline and the local harness are the same
pipeline, and always were.** The apparent gap was a cross-freeze artefact, exactly the error the
provenance rule above exists to catch; it is recorded here because this report made it.

What survives is the single-class gap: chainsaw 76.5% against 44.1%. The harness applies
inverse-frequency weighting at β=1.0 unconditionally, and H2 is unweighted, so part of that is the
weighting difference already measured in section 6.5 rather than anything about the front end. It
does not account for all of it — Edge Impulse's own β=1.0 arm on the same trunk reaches only 57.4%
— and section 7.1 identifies what does.

The work in this report is real — it moved the Edge Impulse model from 62.0% to 82.6% overall, and
on a separate arm from 42.6% to 66.2% on chainsaw, every step reproducible. But the honest reading
of this table is that **a large part of it was spent climbing toward the ceiling of the wrong
pipeline.** An AudioSet-pretrained backbone already in this repository scores 10.7 points higher
overall on exactly these clips, and does it without needing any of the fixes in sections 3 to 6.

That reframes what sections 3 through 6 measured. The `Flatten` head, the missing standardisation
and the class weighting were all genuine defects and fixing them was worth 14.4 points — but the
remaining gap to 93.3% is not another defect of the same kind waiting to be found. It is the
representation. A 2-layer CNN trained from scratch on 3,688 clips cannot learn what 81M parameters
pretrained on AudioSet already know, and no amount of head tuning closes that.

Two things stop this from being a straightforward "ship the backbone instead":

- **Neither backbone has been exported or benchmarked on the QRB2210.** There is no `.eim`, no
  measured latency, no measured RAM. Cnn14 at 81M parameters is not a serious candidate (roughly
  324 MB in float32); Cnn6 at 5.9M is, and the README already identifies it as "the only one of the
  two that could plausibly run on the QRB2210" — but plausible is not measured.
- **Cnn6 trades the class this deployment most needs precision on.** Its `elephant_call` precision
  falls to 77.9% against Cnn14's 98.0%, and `elephant_call` is the only acoustic class that feeds
  the deterrence decision in `reflex_loop.py` — roughly one deterrent firing in five would be
  spurious. Its chainsaw *precision* is the best of any model measured (92.0%), which for the
  logging half of the system is the number that matters most.

So the Edge Impulse model is the **deployable** model today, and the backbone is the **better**
model. Those are different claims and section 7 keeps them apart.

### 6.5 Recall was the wrong column: what class weighting actually buys

Every table up to this point reports recall, because that is what Edge Impulse's model-testing view
reports. For a system that pages a forest officer, recall alone is the wrong objective — a detector
that fires constantly has excellent recall and is worthless. Recomputing precision from the stored
confusion matrices changes the ranking:

| arm | overall | chainsaw R / P / **F1** | gunshot R / P / F1 | elephant P | ambient P |
|---|--:|--:|--:|--:|--:|
| **H2** trunk 32/64, dropout, unweighted | **82.6%** | 44.1 / **81.1** / 57.1 | 90.5 / 88.7 / **89.6** | **68.1** | **80.9** |
| G1 trunk 16/32, dropout, unweighted | 77.9% | 36.8 / 67.6 / 47.6 | 76.5 / 92.1 / 83.6 | 58.0 | 75.2 |
| H1 trunk 16/32, dropout, beta=1.0 | 76.4% | **66.2** / 48.4 / 55.9 | 77.4 / 92.6 / 84.3 | 60.0 | 79.0 |
| G3 trunk 16/32, beta=0.5 | 76.0% | 52.9 / 64.3 / 58.1 | 86.4 / 84.3 / 85.4 | 49.4 | 80.3 |
| H0 trunk 16/32, dropout, beta=0.5 | 75.0% | 48.5 / 68.8 / 56.9 | 70.8 / 92.0 / 80.0 | 57.3 | 70.1 |
| G4 trunk 16/32, beta=1.0 | 73.2% | 63.2 / 55.1 / **58.9** | 86.0 / 81.3 / 83.6 | 47.3 | 82.7 |
| F0 *(as deployed)* | 62.0% | 42.6 / 63.0 / 50.9 | 65.4 / 74.0 / 69.4 | 36.8 | 63.0 |

**H1's chainsaw recall of 66.2% is bought at 48.4% precision.** More than half of every chainsaw
alert it raises would be wrong — 23 `ambient` clips and 17 `gunshot` clips get called chainsaw. The
README already names this failure mode as the worse one: *"for a system that pages a forest officer
on chainsaw detections, a precision collapse is a worse failure than the 13.5% of chainsaws
currently missed. It trades a detection gap for alert fatigue, which ends with the system ignored."*
On that standard H1 is not the better chainsaw arm, it is the louder one.

Two things follow, and they matter more than any single arm.

**Class weighting is largely redundant with a threshold.** Weighting moves the operating point along
a curve that per-class thresholds also move along — except that thresholds are set at deployment,
tuned per class against operational cost, and changed without retraining. Baking a prior into the
loss makes that choice once, globally, at training time. Given section 7 sets thresholds anyway,
training weighted spends the lever twice.

**Capacity, unlike weighting, moves the curve rather than sliding along it.** Weighting on the 16/32
trunk lifts chainsaw F1 from 47.6 (G1) to 55.9–56.9 (H0/H1), buying recall with precision. Widening
the trunk to 32/64 reaches **57.1 F1 with no weighting at all** (H2) — the same F1, arrived at from
the opposite end (81.1% precision at 44.1% recall), *and* 4.7 points more overall accuracy, *and* the
best gunshot F1 (89.6) and best elephant and ambient precision of any arm. The honest reading is that
**class weighting on the 16/32 trunk was partly compensating for an undersized feature extractor**,
which is why section 4.2's and section 6.2's readings of it kept inverting. Round I tests directly
whether capacity and weighting compose on F1 or merely overlap.

### 6.6 The `win_size` mechanism: predicted in detail, then falsified

`ml/acoustic/harness/baseline_mfe.py` carries a comment on its own standardisation line saying that
Edge Impulse "clamps at a -52 dB noise floor and then subtracts a 101-frame sliding local mean".
The noise floor was ruled out by direct measurement — only 0.2% of chainsaw values sit below 0.01,
so nothing is being mass-clipped. That left `win_size`, which Edge Impulse's own parameter help
calls "the size of sliding window for local normalization".

101 frames at the 0.020835 s stride is 2.10 s, and subtracting a 2.1 s sliding mean from a
spectrogram is a high-pass along time. That is class-selective in exactly the observed pattern: a
gunshot is a transient and survives a high-pass, an elephant call is amplitude-modulated and mostly
survives, and a chainsaw is defined by sustained stationary spectral energy — precisely what a
sliding-mean subtraction removes. The mechanism was specific, physically motivated, and explained
the one class that was failing.

It is also wrong, and the test was built to be able to say so. The harness's cached log-mel features
were held fixed and *only* the normalisation was swapped, with the harness's own architecture, split,
weighting and seeds, so any movement is the normalisation and nothing else. The prediction was
recorded in the script's docstring before it ran: **chainsaw lowest at win=51, rising monotonically
with the window, and the win=101 row landing in Edge Impulse's observed 35–53% band rather than near
the harness's own number.**

| normalisation | overall | macro | ambient | chainsaw | elephant_call | gunshot |
|---|--:|--:|--:|--:|--:|--:|
| per-clip standardise (harness baseline) | 82.8% | 82.6% | 78.6 | 76.5 | 87.9 | 87.4 |
| win=51 (~1.06 s) | **84.8%** | 83.9% | 82.2 | 71.3 | 93.1 | **89.1** |
| **win=101 (~2.10 s — what Edge Impulse runs)** | 79.6% | 83.6% | 72.9 | **85.3** | **95.7** | 80.7 |
| win=301 (~6.3 s) | 82.1% | **84.7%** | 73.9 | **89.0** | 89.7 | 86.2 |
| win=478 (full clip) | 79.8% | 83.4% | 70.8 | 85.3 | 94.0 | 83.7 |

The *ordering* held — chainsaw does rise from win=51 through win=101 to win=301, and gunshot moves
comparatively little, both as predicted. The *level* inverted the conclusion. At the window Edge
Impulse actually uses, chainsaw scores 85.3%, which is **8.8 points better** than per-clip
standardisation, not collapsed into the 35–53% band the mechanism required. Edge Impulse's local
normalisation is not damaging chainsaw; it is the best thing in the table for chainsaw.

This is why the falsification arm was in the design. "Chainsaw improves as the window widens" is
true, and a sweep that only ran win=301 and win=478 would have returned two green arms and looked
like confirmation. The claim that made it a test rather than a sweep was quantitative — where
win=101 lands — and that is the part that failed. **The planned Edge Impulse `win_size` sweep was
not run.** Spending Studio compute to confirm a theory whose own falsification criterion had just
been met would have produced a number, not evidence.

Two things survive the wreck. The first is the `standardise` row itself, which is the like-for-like
baseline section 6.4 had been missing and which dissolved the pipeline gap this report had assumed.
The second is a loose end honestly labelled as one: win=301 has the best macro (84.7%) and the best
chainsaw (89.0%) of any row here. That is a +1.1 macro and +3.7 chainsaw gain over the deployed
win=101, and it is not explained by the mechanism just falsified. It is also two seeds against a
run-to-run spread of 2.9 points at win=101, so it is a hint and not a result. It is recorded as an
open question in section 8 rather than acted on.

### 6.7 The model that ships is a checkpoint chosen by aggregate validation loss

Every arm in this report trains for a fixed 120 epochs, and it is natural to assume the model
that ships is the one standing at epoch 120. It is not. Edge Impulse's training log says so in
one line, present in every job checked:

```
Saving best performing model... (based on validation loss)
```

So the artefact is the **best-validation-loss checkpoint**, and the validation set is not a
passive measurement — it is the selector. Two consequences follow, and neither was accounted for
anywhere above.

**First, it explains section 5.2's amplification.** Two runs that differ by one unit in the fourth
decimal of the loss at epoch 2 should, by compounding alone, still land somewhere near each other
at epoch 120. What actually happens is sharper than compounding: a trajectory nudged by 1e-4 can
cross over and make a *different epoch* the minimum-validation-loss epoch, and checkpoint selection
then returns a genuinely different model rather than a slightly different one. That is a discrete
jump, not a drift, which is why a rounding difference produces a visible 1.5 points of accuracy.

**Second, it makes `trainTestSplit` a two-sided lever, and this resolves the sweep's puzzle.**
Lowering the fraction adds training data *and* shrinks the set that picks the checkpoint:

| `trainTestSplit` | trains on | selects on | approx. chainsaw clips in the selector |
|---|--:|--:|--:|
| 0.20 (default) | 2,950 | 738 | ~93 |
| 0.10 | 3,319 | 369 | ~46 |
| 0.05 | 3,503 | 185 | ~23 |

The two effects run in opposite directions, so the lever is not monotonic — and measurement
confirms it is not. 0.10 improved chainsaw markedly over 0.20; 0.05, with *more* training data
still, gave most of it back. A pure data-quantity story cannot produce that shape. A
data-quantity gain fighting a selection-quality loss produces exactly that shape.

**Third, and worst for this project's purpose: the selector is the aggregate loss, and chainsaw
barely appears in it.** The training pool is ambient 1,343, gunshot 1,255, elephant_call 627,
chainsaw 463. Ambient and gunshot are 70% of it; chainsaw is 12.6%. Checkpoint selection
therefore optimises a quantity in which the class this report most wants to fix carries about one
eighth of the vote — and at `trainTestSplit` 0.05 that vote is cast by roughly 23 clips. Section
6.5 already found that class weighting buys chainsaw a great deal; this is a second, independent
place where chainsaw is quietly outvoted, and it is one that class weighting does **not** reach,
because the weights change the training objective while the checkpoint is chosen on unweighted
validation loss.

Nothing in the API exposes the selection monitor, so this cannot be changed from here — it is a
constraint to design around, not a setting. The practical consequence for section 7 is that the
operating point must be set on the held-out 605 by thresholding (7.2), because the training
pipeline's own model selection is not optimising the thing the deployment cares about.

## 7. The shipping configuration

This section is the deliverable. Everything above is evidence for it.

### 7.1 The model

**Architecture — H2.** Expert mode, not visual, because visual mode cannot express the
`LayerNormalization` layer and its `dropoutRate` is inert (section 2.3):

```
Reshape((478, 40))
LayerNormalization(axis=[1,2], center=False, scale=False, epsilon=1e-6)
Conv1D(32, 3, padding=same, relu) -> MaxPooling1D(2) -> Dropout(0.25)
Conv1D(64, 3, padding=same, relu) -> MaxPooling1D(2) -> Dropout(0.25)
GlobalAveragePooling1D()
Dense(24, relu, activity_regularizer=l1(1e-5)) -> Dropout(0.4)
Dense(4, softmax)
```

Adam at 1e-3, batch 32, 120 epochs, **unweighted**. DSP unchanged from the current live MFE config
(`frame_length` 0.02, `frame_stride` 0.020835, `num_filters` 40, `fft_length` 256, `low_frequency` 0,
`win_size` 101, `noise_floor_db` -52).

Three things about this choice are worth stating plainly rather than implying:

- It is chosen over the 64/128 trunk on **cost, not accuracy**. Section 5.4 measures H2's span
  across identical runs at 1.5 points, and H2's advantage over I2/I3 is 2.6–2.8 points — outside
  that span, but not by much, and the span was measured on one arm. What is not in doubt is that
  64/128 costs 37% more flash and 50% more latency for no measured gain, so the smaller trunk wins
  even on a tie.
- It is chosen **unweighted** even though weighted arms score better on chainsaw recall, because
  section 6.5 showed weighting trades recall for precision at roughly 1:1 and is largely redundant
  with a deployment-time threshold — which section 7.2 sets explicitly. Doing it twice double-counts.
- Its headline number should be read as **roughly 81–83%**, not 82.6%. Seven runs of this exact
  script produced exactly three models — 81.2% four times, 82.6% twice, 82.0% once — selected by
  which machine Edge Impulse scheduled the job on (section 5.1). Which one a deployment gets is
  not under this project's control, so the range is the honest number. Note that the *chainsaw*
  recall differs by 4.4 points across those same three models, which matters more than the
  overall figure for the thresholds in section 7.2.

**Precision — float32, and this is not a close call.** Profiled on `arduino-unoq`, which is this
project's default target:

| build | internal val acc | val loss | latency | EON flash | EON RAM |
|---|--:|--:|--:|--:|--:|
| **float32** | **87.4%** | 0.557 | **1 ms** | 92,256 B | 156,496 B |
| int8 | 72.9% | 3.279 | 6 ms | 69,072 B | 44,312 B |

**The case rests on accuracy alone, and on that axis it is decisive: 14.5 points.** A 5.9× rise in
validation loss says the int8 model is not merely less accurate but badly miscalibrated, which
matters doubly because section 7.2 sets thresholds on the softmax output — thresholds tuned on
float32 would be meaningless on int8. The memory cost of float32 (23 KB flash, 112 KB RAM) is
irrelevant on a Linux MPU with gigabytes of both.

**The latency column above should not be used as an argument, and it contradicts this repository's
own platform research.** `docs/research/platform/edge-impulse-linux-inference.md` concludes "ship
the CPU int8 EON `.eim`" on the grounds that "int8 + XNNPACK on Cortex-A53 is markedly faster than
float32" — and that document is backed by a *measured* ~138 ms/frame on the actual UNO Q, while the
1 ms / 6 ms figures here are Edge Impulse's profiler estimates for a model roughly a thousand times
smaller. Two caveats apply and they point the same way: integer-millisecond estimates in the 1–6 ms
range are mostly rounding, and board access has been closed since 11 September so neither number has
been checked on hardware.

The disagreement does not need resolving to make this decision, because **both builds run in single-digit
milliseconds against a 10-second analysis window** — latency does not discriminate between them at
any plausible value. If the platform research is right and int8 is in fact the faster build here
too, float32 is still the correct choice, because it is being chosen for 14.5 points of accuracy and
paying a few milliseconds nobody will observe.

> **This departs from standing platform guidance and should be recorded as such.** The research
> document's "ship int8" conclusion was reached for the *vision* model, where int8 was measured
> faster and the accuracy cost was not the binding constraint. Applying it unexamined to acoustic
> would cost 14.5 points. An ADR narrowing that guidance to the vision track, and recording float32
> for acoustic with this evidence, is the right home for it: a changed decision gets an ADR
> rather than a footnote in a report.

> **The trap this walks past.** Model testing in Edge Impulse Studio always runs float32 and
> silently ignores `selectedModelType` (section 2.5). The test view therefore shows float32 accuracy
> whatever is selected, while Deploy honours the selection. Reading an accuracy off the Studio UI and
> then deploying int8 ships a model roughly 14 points worse than the number that justified it. The
> project has been left with `float32` selected.

### 7.2 The operating point: thresholds, not argmax

Every number in this report is argmax accuracy — the model is forced to name a class for all 605
clips, including ones it has no basis for. Edge Impulse's `min_confidence_rating` sits at 0.1, which
is why the `uncertain` column is all zeros in every confusion matrix here. A field deployment does
not have to do that and should not.

The costs are class-asymmetric, so the thresholds must be. Swept on the 605 (recall = caught / all of
that class; FA rate = clips of *other* classes firing this class):

| threshold | chainsaw R / FA | elephant R / FA | gunshot R / FA |
|--:|--:|--:|--:|
| 0.10 | 76.5 / 14.0% | 94.8 / 14.4% | 95.5 / 19.1% |
| 0.30 | 58.8 / 3.7% | 87.9 / 8.0% | 92.2 / 9.1% |
| 0.50 | 45.6 / 1.9% | 82.8 / 3.7% | 87.2 / 5.5% |
| 0.70 | 29.4 / 0.6% | 81.0 / 3.1% | 78.2 / 3.9% |
| 0.80 | 26.5 / 0.0% | 79.3 / 2.2% | 71.2 / 3.3% |
| 0.90 | 22.1 / 0.0% | 70.7 / 1.6% | 65.0 / 2.2% |

**The recommendation turns on a distinction the test set cannot show: event duration.** The 605 clips
are independent 10-second windows, but the field sees a continuous stream, and the three alert classes
behave completely differently in it.

- **chainsaw — threshold 0.30, with a 2-of-5 window persistence rule.** Felling a tree is a
  multi-minute event, so a real chainsaw presents as dozens of consecutive windows while a false
  positive is an isolated one. Requiring 2 hits in 5 windows turns 58.8% per-window recall into
  near-certain detection across a 50-second event, while driving the 3.7% per-window false-alarm rate
  down by roughly its square. Persistence is worth far more here than any threshold choice, and it is
  the only class where this report recommends buying recall with time rather than with a lower bar.
- **gunshot — threshold 0.30, no persistence available.** A gunshot is a single transient in a single
  window; there is no second window to corroborate it. That forecloses the chainsaw trick and forces
  the threshold itself to carry the recall: 0.30 holds 92.2%. The 9.1% false-alarm rate is the price,
  and it is the right price — a missed shot is a missed poaching event, and section 1's headline
  failure was 68 gunshots called ambient.
- **elephant_call — threshold 0.80.** This is the only acoustic class feeding the deterrence decision
  in `reflex_loop.py`, so a false positive fires a deterrent at nothing and, repeated, trains residents
  and officers to ignore the system. 0.80 holds 79.3% recall at a 2.2% false-alarm rate. It can afford
  the high bar precisely because ADR 0007 scopes acoustic as **corroboration, never standalone
  presence** — seismic and vision carry presence, and acoustic only has to agree.
- **ambient** needs no threshold; it is the null class and fires nothing.

**chainsaw is the one class that breaks ADR 0007's framing, and that should be explicit.** Nothing
else in the system detects a chainsaw — there is no seismic or visual corroboration to wait for — so
in practice chainsaw *is* standalone presence, on the weakest class in the model. The persistence rule
above is what substitutes for the corroboration ADR 0007 assumes, and it is a weaker substitute. This
is a design gap, not a tuning problem, and it belongs in front of whoever signs off the deployment.

### 7.3 A guard the test set cannot motivate

Per-clip standard deviation across the 605 has a minimum of 0.0084 — every clip carries real signal,
because every clip was recorded deliberately. A dead or disconnected microphone produces a near-silent
stream, and per-clip normalisation will amplify whatever numerical noise remains into something the
model will confidently classify. The model has never seen this input and cannot report it.

**Add an input-level variance floor of ~3×10⁻³ ahead of inference, and emit a sensor-fault status
rather than a classification when it trips.** It would never have fired on any clip in this corpus,
which is exactly why the corpus cannot justify it and why it still needs to exist.
`report_system_status` already carries an `acoustic_ok` boolean (`device/mpu/bridge/schema.md`), so
the wire contract for reporting it is in place.

### 7.4 What blocks deployment today

**~~The `AcousticClass` wire contract does not carry this model's output.~~ Fixed 24 Sept
(ADR 0027).** `device/mpu/bridge/rpc.py:35` enumerated `gunshot, chainsaw, vehicle, animal_call,
ambient` while the model emits `ambient, chainsaw, elephant_call, gunshot`. `elephant_call` — the
class that drives deterrence — had no enum member and could not cross the wire at all, while
`vehicle` and `animal_call` could never be emitted yet still had live routing branches in
`reflex_loop.py`. The enum and `bridge/schema.md` are now the trained four-class scheme,
`_FUSING_ACOUSTIC_CLASSES` is `{chainsaw, elephant_call}`, and a new contract test pins the enum to
schema.md so the two cannot drift apart again unseen. ADR 0024's required regression passed with an
identical failure set before and after. This no longer blocks deployment; the on-target benchmark
below is now the only thing that does.

**No on-device measurement exists.** Every latency and memory figure here is Edge Impulse's estimate
for `arduino-unoq`. Board access has been closed since 11 September, so nothing has been run on the
actual hardware. The estimates are single-digit milliseconds against a 10-second analysis window, so
the conclusion is robust to being wrong by a large factor — but it is still an estimate, and project
docs should say so until someone measures it.

### 7.5 The recommendation this report is obliged to make against itself

Section 6.4 measured the Cnn14 + MLP backbone already in this repository at **93.3%** on the identical
605 clips, against this model's ~82%. That gap is roughly seven times the run-to-run noise in section
5.4, so unlike most of the arm rankings here it is unambiguously real.

**Ship the Edge Impulse model now; treat the backbone as the roadmap.** Cnn14 at 81M parameters is not
a candidate for this device. The deployable-size backbones had never been scored on the canonical
freeze, so they were, and on the identical 605 clips (5 seeds, mean and span):

| backbone | params | overall | ambient | chainsaw | elephant_call | gunshot |
|---|--:|--:|--:|--:|--:|--:|
| Edge Impulse H2 (what section 7.1 ships) | ~15k | ~82% | — | 44.1% | — | — |
| Cnn6 + MLP | 5.92M | 91.9% (91.2–92.9) | 91.3 / 94.2 | 85.6 / 84.3 | 87.6 / 80.4 | 95.4 / 95.1 |
| **Cnn10 + MLP** | **6.30M** | **92.1% (90.7–93.2)** | 90.2 / 94.0 | **90.9 / 88.1** | **93.1 / 89.1** | 94.2 / 92.4 |
| Cnn14 + MLP (ceiling, not deployable) | 81M | 93.3% | — | 86.5% | 93.4 / 90.1 | — |

Cells are recall / precision. **Cnn10 is the ship candidate, not Cnn6.** It costs 31% more compute
than Cnn6 and buys back the two things Cnn6 gave up: `chainsaw` recall rises 5.3 points to 90.9%
— beating even the 81M-parameter Cnn14 — and `elephant_call` precision rises 8.7 points to 89.1%,
which is the class section 7.2's deterrence argument cannot afford to be loose on. Against the
shipping model that is **+10 points overall and +46.8 points on chainsaw**, the one class with no
corroborating modality.

**The pipeline change is the point, not the architecture.** Running outside Edge Impulse also
eliminates the worker lottery of section 5, the silently discarded `script` of sections 2.1–2.2,
the inert dropout of 2.3, and the float32-only test view of 2.5. There is no incumbent to stay
compatible with: `device/mpu/services/reflex_loop.py` states that acoustic is deliberately not
wired into the reflex path and no acoustic classifier runs on the device today.

**Export and quantisation are done and are lossless** (`export_panns.py`, `bench_onnx.py`). The
graph takes log-mel rather than waveform — torchlibrosa's STFT-as-conv1d costs ~1 GMAC against
~10 MMAC for a real FFT — and every export is checked against the cached embeddings, at
`max abs err 0.000e+00`, so the exported graph provably *is* the model that was measured. On the
frozen 605, single-threaded-x86 figures at 4 threads:

| graph | overall | chainsaw | elephant_call | size | ms/clip |
|---|--:|--:|--:|--:|--:|
| fp32 ONNX | 91.9% | 91.2 / 83.8 | 91.4 / 88.3 | 21.4 MB | 196 |
| int8, u8s8 default | 54.5% | 5.9 / 80.0 | 34.5 / 28.6 | 7.4 MB | 112 |
| **int8, 7-bit weights** | **91.7%** | 91.2 / 84.9 | 93.1 / 87.1 | **7.4 MB** | **114** |

The middle row is a **host artefact worth recording, because it is silent**. The default u8s8
kernel accumulates into int16, and on an x86 CPU without VNNI it saturates; nothing warns, and the
model simply gets 37 points worse. It is invisible to the obvious diagnostic, too: exposing
intermediate tensors to compare layer by layer *disables* the QDQ-to-QLinearConv fusion, so the
probe measures quantisation simulated in float and reports a final-probability error of 0.0147 —
a clean bill of health for a graph that is scoring 54.5%. Quantising the weights to 7 bits
(`--reduce-range`) is the documented mitigation and costs nothing measurable here. Cortex-A53 does
not use that kernel path, so the plain build may well be fine on the target; that is a question for
the board, not for argument.

The int8 row previously read 91.9% with a chainsaw precision of 86.1%, and that figure does not
reproduce. The difference is exactly one clip — a gunshot the int8 graph now calls chainsaw, which
moves overall from 556/605 to 555/605 and the predicted-chainsaw column from 72 to 73. Three
candidate causes were tested and all three are ruled out: re-exporting at opset 17 leaves the fp32
graph numerically identical (1.4e-07, 100% argmax), rebuilding the int8 graph from the retained
opset-18 fp32 with the same calibration cache reproduces the new matrix cell for cell, and scoring
through the block's FFT front end rather than torchlibrosa changes nothing. The fp32 row reproduces
exactly at 91.9%. The table now carries the reproducible measurement.

**The confusion matrices.** Overall accuracy and per-class recall hide which way the errors fall,
and for this application that is the part that matters — an elephant call scored as ambient is a
missed alert, while one scored as gunshot still raises an alarm. Rows are actual, columns predicted,
over the frozen 605.

*fp32, 10 s*

| actual \ predicted | ambient | chainsaw | elephant_call | gunshot | recall |
|---|--:|--:|--:|--:|--:|
| ambient | 215 | 3 | 3 | 15 | 91.1% |
| chainsaw | 2 | 62 | 2 | 2 | 91.2% |
| elephant_call | 3 | 2 | 53 | 0 | 91.4% |
| gunshot | 8 | 7 | 2 | 226 | 93.0% |
| **precision** | 94.3% | 83.8% | 88.3% | 93.0% | |

*int8 with 7-bit weights, 10 s*

| actual \ predicted | ambient | chainsaw | elephant_call | gunshot | recall |
|---|--:|--:|--:|--:|--:|
| ambient | 215 | 3 | 3 | 15 | 91.1% |
| chainsaw | 2 | 62 | 2 | 2 | 91.2% |
| elephant_call | 2 | 2 | 54 | 0 | 93.1% |
| gunshot | 10 | 6 | 3 | 224 | 92.2% |
| **precision** | 93.9% | 84.9% | 87.1% | 92.9% | |

*int8 with 7-bit weights, 3 s centred on the event*

| actual \ predicted | ambient | chainsaw | elephant_call | gunshot | recall |
|---|--:|--:|--:|--:|--:|
| ambient | 216 | 4 | 5 | 11 | 91.5% |
| chainsaw | 3 | 59 | 4 | 2 | 86.8% |
| elephant_call | 2 | 0 | 56 | 0 | 96.6% |
| gunshot | 11 | 9 | 0 | 223 | 91.8% |
| **precision** | 93.1% | 81.9% | 86.2% | 94.5% | |

Three things read out of these that the summary rows do not show.

**The dominant error is ambient/gunshot confusion in both directions**, 15 and 8 clips in the fp32
matrix — the largest off-diagonal cells by some margin, and between them roughly half of all errors.
That is a threshold question rather than a capacity one, and §7.2 is where it gets handled.

**Chainsaw precision is the weakest column in every graph** (83.8%, 84.9%, 81.9%), and the false
chainsaws come mostly from gunshot, not from ambient. Chainsaw recall is the metric §7.5 leans on
against the MFE net's 44.1%, so it is worth being explicit that the gain is in recall and that
precision is where this model is softest.

**The 3 s window is not a uniform downgrade.** It trades chainsaw badly — recall 91.2% to 86.8%,
precision 83.8% to 81.9% — while elephant_call recall rises to 96.6%, the best of any configuration
measured. Chainsaw is a sustained sound a shorter window samples less of; an elephant call is a
transient, and centring on it helps. If elephant detection is the priority the 3 s configuration is
defensible on more than latency, but not if chainsaw matters equally.

**Both graphs are portable.** All 83 nodes are standard `ai.onnx`; the `com.microsoft` entries in
the opset table are declarations the quantiser adds and leaves unused, so nothing ties the graph to
one runtime. The graphs are **opset 17, IR 8**.

An earlier revision of this section recorded them as opset 18 / IR 10 and raised a prerequisite of
`onnxruntime >= 1.18` on the board. That prerequisite was real but self-inflicted, and the cause is
worth recording because nothing in the export output pointed at it. `torch.onnx.export` has
defaulted to the dynamo exporter since torch 2.6, and that backend treats `opset_version` as
advisory: the call asked for 17, it emitted 18, and it issued no warning. Under opset 18
`ReduceMean` and `ReduceMax` take their axes as a second input rather than an attribute, which is
what actually raised the runtime floor. Pinning `dynamo=False` produces the requested opset, and
the exporter now checks the emitted version and fails loudly, so the substitution cannot recur
unnoticed. The re-exported graph is the same model: over 48 real calibration windows the opset-17
and opset-18 graphs agree to 1.4e-07 in probability, with identical argmax on every window.

**A 3-second window costs almost nothing and cuts compute 3.3x — but only if the window is placed
on the event.** Window length is the one knob that shortens the backbone without discarding the
pretrained weights, and compute is linear in it. Sweeping it the obvious way says it is unaffordable;
sweeping it correctly says the opposite:

| window | overall | ambient | chainsaw | elephant_call | gunshot |
|---|--:|--:|--:|--:|--:|
| 10 s | 92.1% (90.7–93.2) | 90.2 | 90.9 | 93.1 | 94.2 |
| 5 s, from the clip start | 87.9% (86.9–88.9) | 87.0 | 87.1 | 89.0 | 88.8 |
| 5 s, centred on the event | 91.8% (90.6–92.7) | 90.2 | 90.3 | 92.8 | 93.7 |
| 3 s, from the clip start | 72.8% (71.4–74.7) | 79.7 | 86.8 | 90.7 | **57.9** |
| **3 s, centred on the event** | **91.5% (90.9–91.9)** | 90.3 | 89.1 | 92.4 | **93.0** |

Recall only; 5 seeds. The first sweep took the opening N seconds of each clip, and read as a 19-point
collapse at 3 s. **The damage is almost entirely `gunshot`** — 57.9% against 94.2% — while `chainsaw`
loses 4 points and `elephant_call` does not move. That asymmetry is the tell: a gunshot is an
impulsive transient, so a shot four seconds into a ten-second clip is simply *absent* from the first
three, whereas a chainsaw or a call is sustained and survives any crop. It measured the cropping,
not the window.

That is the wrong experiment for this deployment, because a short window on-device **slides over a
continuous stream** and cannot miss an event the way a truncated clip can. Re-centring each window
on the loudest 100 ms recovers **+18.7 points at 3 s** and puts `gunshot` back to 93.0%. The
remaining 3 s-to-10 s difference is 0.6 points, with overlapping seed spans — not a resolved
difference — against **3.3x less compute**.

One caveat on that row: peak-centring uses oracle knowledge of where the loudest moment is. A
sliding detector does not have it, but it does cover every position and can take the best window, so
this is a fair proxy rather than a guarantee — and it assumes the loudest moment *is* the event,
which is safe for `gunshot` and `chainsaw` and less certain for a distant call in noise. **If the
on-target benchmark shows 10 s is too slow, 3 s is the lever, and it is nearly free.**

**The `elephant_call` operating point section 7.2 specifies is largely moot for this model, and the
reason is worth stating carefully.** Sweeping the `elephant_call` probability threshold on the int8
graph over the frozen 605:

| threshold | recall | precision | false positives (of 547 non-call clips) |
|---|--:|--:|--:|
| argmax | 93.1% | 87.1% | 8 |
| 0.30 (what section 7.2 sets) | 93.1% | 84.4% | 10 |
| **0.50** | **93.1%** | **88.5%** | **7** |
| 0.90 | 91.4% | 93.0% | 4 |

The whole 0.15-to-0.90 sweep moves recall by 3.4 points. **This is not evidence that the model is
well calibrated — it is the opposite.** Median confidence is 1.000 and 93.4% of clips are predicted
above 0.9: the softmax is saturated, as an MLP trained to convergence usually is, and thresholds are
weak here *because* the mass sits at the extremes, not because the scores are honest about
uncertainty. The four missed calls at 0.50 carry `elephant_call` probabilities of 0.002, 0.010,
0.011 and 0.24 — three of them confidently wrong, so no threshold recovers them. They are real
errors, not operating-point artefacts.

**Recommended: 0.50.** It matches argmax on recall, adds 1.4 points of precision, and leaves 7 false
positives in 547. Section 7.2's 2-of-5 persistence gate should stay — it is temporal, it costs
nothing, and it is doing more work than the threshold is. Two consequences worth carrying forward:
the 0.30 threshold section 7.2 sets is tuned for a much weaker model and is actively worse than 0.50
here, and **ADR 0026's float32 rationale partly rests on calibrated scores being load-bearing** — on
this model they are not, in either precision, so that argument should be re-examined rather than
inherited.

So the honest statement is: **the Edge Impulse model is the deployable model, and it is not the best
model this repository can build.** What remains before Cnn10 can displace it is **on-target
measurement**. Every latency figure above is x86 and does not transfer — ADR 0026 found int8
*slower* than float32 for the ~15k-parameter Edge Impulse model on this board, and while that
cache-residency argument should not carry to a 6.3M-parameter model, "should not" is not a
measurement. Accuracy will transfer; latency and memory will not.

### 7.6 Reproducing this model inside Edge Impulse

Everything above was measured outside Edge Impulse, in `ml/acoustic/harness/`, because neither
stock block can host this model: MFE is a different front end, and `keras-transfer-kws` caps the
window at 1000 ms. That left the Studio project carrying the ~82% MFE net while the report
recommended a 91.9% model that existed only as a local script — a gap that makes the project
un-reviewable by anyone who is handed the Studio link.

`ml/acoustic/ei_blocks/` closes it with two custom blocks, giving the impulse
`audio → PANNs log-mel → PANNs Cnn10 transfer`:

- **`dsp-panns-logmel/`** reimplements the torchlibrosa front end the released checkpoints were
  trained on: a 32 kHz *analysis* rate, 1024-point Hann STFT, 320-sample hop, 64 Slaney-normalised
  mel filters over 50–14000 Hz, power spectrum, `10*log10` with no noise-floor clipping and no
  `top_db` ceiling. The 32 kHz is the rate the filterbank is *defined* at, not the rate audio
  arrives at: this impulse's input is **8 kHz**, because the corpus is 8 kHz throughout, and the
  4x upsample to the PANNs rate happens inside the block on every window. The distinction is not
  pedantic — it is the single most confusing thing about this front end, it is what the first
  version of the C++ port got wrong (see below), and a reader who takes "32 kHz" as the input rate
  will build something that refuses the only rate it will ever be fed.
  The noise floor is the substantive difference from MFE — MFE zeroes every bin below it, and a
  frozen backbone has no opportunity to relearn around a shifted input distribution.
- **`learn-panns-cnn10/`** freezes the backbone, embeds each window once, trains the same
  two-layer head with the same oversampling as `harness/train_head.py`, and exports one ONNX graph
  covering backbone and head together.

The front-end claim is tested rather than asserted. `parity_check.py` runs the real torchlibrosa
`Spectrogram` and `LogmelFilterBank` modules against the block on real test-split clips:

| quantity | measured | tolerance |
| --- | --- | --- |
| log-mel, cells within 80 dB of clip peak | 2.06e-04 dB | 1e-02 dB |
| Cnn10 embedding, relative to its own scale | 1.24e-05 | 1e-03 |

Synthetic signals are reported but not asserted on, and the reason is worth recording because it
looks like a failure. The two implementations are different numerical routes to the same quantity
— torchlibrosa computes the STFT as a conv1d against a DFT matrix, the block uses an FFT — and both
accumulate 513 float32 products per mel bin in different orders. A pure tone leaves most bins pinned
at the `amin = 1e-10` clamp floor near −95 dB, where that rounding is a large *relative* error and dB
magnifies it to ~5e-2. On any cell carrying signal it is ~1e-4 dB. Asserting on the tone would be
asserting on float32 noise.

One incidental finding, which turned out to matter more than it first looked. Both this block and
`harness/export_panns.py` asked `torch.onnx.export` for opset 17; the block got it and the harness
did not. The difference is `dynamo=False`. Since torch 2.6 the dynamo exporter is the default and
treats `opset_version` as advisory, so the harness graph was opset 18 / IR 10 while its own call
said 17, and neither the export nor the load warned about it. §7.5 carries the correction.

**Bring-your-own-model, and what that opset actually cost.** Uploading the exported graph directly
to a Studio project is the fastest way to make the model visible there, ahead of the blocks, and
the first attempt failed. Edge Impulse converts an uploaded ONNX to TensorFlow Lite server-side and
tries two converters in turn. The first, `onnx2tf`, died inside its own convolution weight
handling; the second was unambiguous:

```
onnx.checker.ValidationError: Node (node_mean) has input size 2 not in range [min=1, max=1]
Context: Bad node spec for node. Name: node_mean OpType: ReduceMean
```

That is the opset-18 `ReduceMean` — axes as a second input — meeting a checker that only knows the
opset-17 form where axes is an attribute. With the exporter pinned to `dynamo=False`, the same
model converted on the first converter, profiled, and built a deployment library. The failure is
worth recording because it is the one place the silent opset substitution produced a hard stop
rather than a footnote about runtime versions.

The conversion transposes the input from NCHW to NHWC, so the graph presents as `(1, 1001, 64, 1)`.
The channel dimension is 1 and trailing, so a row-major flatten is still frames x mel bins — the
same ordering the processing block emits, and nothing downstream has to compensate for it.

One number from that path should not be quoted as a result. Edge Impulse's profiler estimates
**11315 ms** per inference on a Cortex-A72. That is a static estimate from the graph's MAC count
against a nominal clock, not a measurement, and the same graph runs in 199 ms on x86 with four
threads. The on-target QRB2210 benchmark §7.4 calls for is still outstanding, and this does not
substitute for it.

One limit on what this reproduces. On a non-enterprise project the processing block runs locally
behind an ngrok tunnel and cannot emit optimised native DSP code; enterprise organisations host it
on Edge Impulse infrastructure.

The other limit — that Edge Impulse owns the train/test division inside a project, so Studio
numbers could only agree closely rather than exactly — has since been removed. Uploading through
the ingestion API with the `training` and `testing` endpoints chosen per record from `split.json`
forces the project's division to be the frozen one. Verified by reading the project back: 3,688
training and 605 testing samples, an exact filename-and-label match to the split file, 0 missing
and 0 extra, and Studio's own window count agreeing class for class. Studio figures from this
project are therefore scored on the same clips as every other number in this report.

**The learning block, measured at full corpus scale on Edge Impulse's own contract.** The block was
run on genuine `X_split_train.npy (3688, 64064)` and `X_split_test.npy (605, 64064)` arrays built by
the processing block's own `generate_features`, fed int16-scale counts so the block's rescaling path
was the one under test, and invoked through the same `--info-file / --data-directory /
--out-directory` interface Studio uses. It scores **92.6% (560/605)**, against this report's 91.9%
for the harness at the same window. The head is refit on the block's own embeddings with its own
oversampling and seed, so the two are the same method rather than the same fitted model, and the
0.7 points between them are below the 1.5-point bar section 8 sets for treating an overall-accuracy
gap as resolved. This is the close agreement the block's README predicts, not an improvement.

| actual \ predicted | ambient | chainsaw | elephant_call | gunshot | recall |
|---|--:|--:|--:|--:|--:|
| ambient | 214 | 3 | 2 | 17 | 90.7% |
| chainsaw | 2 | 62 | 2 | 2 | 91.2% |
| elephant_call | 3 | 1 | 54 | 0 | 93.1% |
| gunshot | 7 | 5 | 1 | 230 | 94.7% |
| precision | 94.7% | 87.3% | 91.5% | 92.4% | **92.6%** |

**The stock MFE impulse, on the same 605 clips, in the same project.** A stock
`audio -> MFE -> Classification` impulse was trained in Studio on the identical split, with MFE
configured as favourably as the data allows: 64 filters to match the mel bin count, a 50 Hz floor
and a 4 kHz ceiling at the corpus's true Nyquist. Scored by argmax, it reaches **61.7% (373/605)**.

| actual \ predicted | ambient | chainsaw | elephant_call | gunshot | recall |
|---|--:|--:|--:|--:|--:|
| ambient | 168 | 5 | 45 | 18 | 71.2% |
| chainsaw | 17 | 6 | 40 | 5 | **8.8%** |
| elephant_call | 15 | 1 | 40 | 2 | 69.0% |
| gunshot | 59 | 7 | 18 | 159 | 65.4% |
| precision | 64.9% | 31.6% | 28.0% | 86.4% | **61.7%** |

Two things about that number. It is an **untuned** arm, and it lands within 0.3 points of the 62.0%
this report already records for Edge Impulse as configured and deployed — an independent
reproduction of that row on a split that is now provably the same one, not a new and worse result.
It is not the 82.6% H2 arm, which was tuned. And it is not what Studio shows: the argmax figure is
what compares like for like against the block, but Studio's own headline for this impulse is
**34.88%**.

The difference is entirely Edge Impulse's confidence gate, and it is worth showing as Studio shows
it, because this is the view a reviewer opening the project sees first. Any window whose top score
falls below `minimumConfidenceRating` — 0.6 by default — is scored as `uncertain` rather than as
its argmax class, and 336 of the 605 fall below it:

| actual \ predicted | ambient | chainsaw | elephant_call | gunshot | uncertain |
|---|--:|--:|--:|--:|--:|
| ambient | 28.4% | 0% | 1.3% | 4.2% | 66.1% |
| chainsaw | 2.9% | 0% | 4.4% | 4.4% | 88.2% |
| elephant_call | 1.7% | 0% | 12.1% | 3.4% | 82.8% |
| gunshot | 11.5% | 0.8% | 1.6% | 56.4% | 29.6% |
| F1 | 0.40 | **0.00** | 0.19 | 0.69 | |

That reconciles: 67 + 0 + 7 + 137 = 211 confident and correct, and 211/605 is the 34.88% headline.
The gated view is harsher than the argmax one on every class, but the chainsaw row is the one that
is qualitatively different — **F1 0.00**. Not one of the 68 chainsaw clips is confidently labelled
`chainsaw`: 60 fall below the gate and the remaining 8 clear it under a wrong label. The chainsaw
*column* is near-empty too — across all 605 clips the impulse emits a confident `chainsaw` twice,
both on gunshot clips, so its chainsaw precision is 0 as well. A deployment reading this impulse
the way the firmware reads a classifier detects chainsaws zero times.

The gate is not inventing that problem, only exposing it. Scored generously by argmax the same
class still reaches only **8.8% recall**, with 40 of 68 clips going to `elephant_call`, which is
the confusion section 7.5 already identifies. Section 7.5 puts
the processing block **+46.8 points on chainsaw** against the shipping model; against this untuned
stock arm the same block is +82.4. Both comparisons point the same way, and neither is the one to
quote on its own — 7.5's is against a tuned configuration and is the honest figure.

**A third reason the stock block cannot carry this model.** Beyond the front-end mismatch and
`keras-transfer-kws`'s 1000 ms window cap already recorded above, MFE hard-caps its output at 512
frames. A 10 s window at its default 10 ms stride needs 998 and fails outright:

```
ConfigurationError: Number of frames is larger than 512 (998),
increase your frame stride or decrease your input window size.
```

The impulse above only runs at all because the stride was widened to 20 ms, halving time resolution
to 498 frames — the project reports a feature count of 31,872, which is 498 x 64 — where the
processing block runs 1001 frames at PANNs' native 10 ms hop. This is the
most concrete of the three reasons, being a hard error rather than a distribution shift.

**The corpus is 8 kHz.** Confirmed directly with `soundfile` across the split, and Edge Impulse
reads it the same way — 80,000 values per 10 s sample. The PANNs front end resamples to 32 kHz and
builds its filterbank to `fmax = 14000`, so every mel bin above 4 kHz is empty by Nyquist and
roughly the upper half of the filterbank carries no information. This is not a defect introduced
here — `load_clip` has always resampled and every figure in this report was measured that way — but
it means the front end is running with headroom the corpus cannot fill, and a future capture at
32 kHz has that much unclaimed signal available to it.

**Pushing the blocks needs organization membership, not an organization API key.** Custom
processing and learning blocks are organization resources, created through
`/v1/api/organizations/{id}/dsp` and `.../transferLearning`, and calling those endpoints directly
with a project key is refused — *"The API key you provided is a project API Key. This endpoint
requires an organization API Key."* That refusal is easy to over-read. `edge-impulse-blocks push`
only authenticates that way when given `--api-key`; run without it, the CLI performs an ordinary
interactive login and acts with the signed-in user's own permissions, which is the documented
default flow. An organization key is therefore a convenience for CI, not a prerequisite.

The push itself tars the block directory, uploads it, and runs the container build as an
organization job on Edge Impulse infrastructure — there is no local `docker build` and no external
registry in the path, which is why the "Docker container" field in the Studio dialog for creating a
block by hand is the harder route rather than the easier one. Hosting a custom processing block on
Edge Impulse infrastructure is enterprise-only; a non-enterprise project can still attach one by
URL, self-hosted behind a tunnel, but no such escape hatch exists for custom learning blocks.

**A project with a custom DSP block cannot be cloud-built for any device target.** This is the
single most consequential fact in the whole deployment track, it is not signposted anywhere in the
Studio UI until you try, and everything below follows from it. Selecting the UNO Q target — or any
device target — fails in about fifteen seconds:

```
Cannot build for "arduino-uno-q" as your project contains custom DSP blocks
```

`runner-linux-aarch64` fails the same way and in the same time. `zip` — the plain C++ library —
builds in 47 s. Edge Impulse's documentation states the reason directly: for a custom block *"we
cannot automatically generate optimized native code for the block, like we do for built-in
processing blocks."* The cloud builder has the impulse, the learn block's weights and the block's
*parameters*, but the block's DSP itself is a container it can call during training and feature
generation — not something it can compile into an ARM binary.

The consequence is easy to under-read. It is not that the optimised path is unavailable and a
slower one substitutes. It is that **Studio's UNO Q deployment card, and the "Go to Arduino" action
that pushes a built model straight into App Lab's model list, are both unreachable for this
project.** The smooth path advertised for this exact board does not exist here.

**`cppType` is the sanctioned way through.** Edge Impulse's own answer is a field in the block's
`parameters.json`:

```json
{ "cppType": "panns_logmel" }
```

With it set, the C++ library export stops treating the block as a black box and instead emits, into
`model-parameters/model_variables.h`, a populated config struct and a **forward declaration** of a
function it does not define:

```c
ei_dsp_config_panns_logmel_t ei_dsp_config_1110036_95 = {
    95, 1, 1, 64, 1024, 320, 50, 14000, false
};

int extract_panns_logmel_features(signal_t *signal, matrix_t *output_matrix,
                                  void *config_ptr, const float frequency);
```

...and wires `&extract_panns_logmel_features` into the DSP block table the classifier dispatches
through. Studio has done everything it can: the impulse, the converted learn block, the parameter
values and the call site. Supplying the body is the integrator's job. The struct's fields are
generated one-for-one from the `param` entries in `parameters.json`, in order, behind three fixed
fields — so renaming a parameter in Studio renames a field in C++, and the port stops compiling.
That is the good failure; a rename that kept compiling would change the front end under a model
trained on the old one.

**The port.** `ml/acoustic/ei_blocks/dsp-panns-logmel/cpp/` supplies that body — `panns_logmel.cpp`
as the SDK-facing shim and `panns_logmel_core.hpp` as the dependency-free kernel, so the numerical
code can be compiled and tested on a host without the SDK present. Two details are worth recording
because both cost real time.

The shim deliberately does **not** include `model_variables.h`, although that is the file declaring
the function it defines. Two independent reasons, either sufficient. That header *defines* rather
than declares — the config instance, the label table and the DSP block array are all globals with
external linkage — so a second translation unit including it is a duplicate-definition link error;
the SDK includes it in exactly one place. It also does not stand alone: Studio writes the forward
declaration with unqualified `signal_t` and `matrix_t` at file scope, which parse only because
`ei_run_dsp.h` has already done `using namespace ei;`, a constraint the SDK states at
`ei_run_classifier.h:98`. Nothing is lost by omitting it — the declaration and the definition still
have to agree, and the linker is what enforces that, one stage later.

The resampler is the second. Because the impulse is 8 kHz and the filterbank is 32 kHz, every
window is upsampled 4x *inside the block*. `EI_CLASSIFIER_NN_INPUT_FRAME_SIZE 64064` is the
arithmetic made visible: 80,000 samples upsample to 320,000, divided by the 320-sample hop gives
1000 frames plus one, times 64 mel bins. The C++ resampler is tested against librosa's output by
`parity_resample.py` rather than assumed equivalent. Rates that are not integer divisors of 32 kHz
are refused outright instead of approximated — a rational resampler covering rates nobody feeds it
would be untested code on the one path that decides what the classifier sees.

**Building it.** The `.eim` is built locally from the plain C++ library export. The full recipe is
in `ei_blocks/dsp-panns-logmel/cpp/README.md`; four requirements in it are load-bearing and none
announce themselves:

| requirement | what happens without it |
| --- | --- |
| `USE_FULL_TFLITE=1` | the build targets TFLite-Micro with a statically sized arena, which 21.9 MB of float32 weights will not fit |
| `cp -r tensorflow-lite edge-impulse-sdk/tensorflow-lite` | the Makefile compiles with `-Iedge-impulse-sdk/tensorflow-lite`, but the headers ship at the repo root and the export does not carry them |
| a real cross toolchain | upstream's README builds aarch64 with plain `clang`, which only works on an aarch64 host |
| an LF checkout | a clone made by Windows git arrives with CRLF, and a Makefile with a trailing carriage return puts a control character inside every variable value |

One more that is pure trap: `CXXSOURCES` is an explicit list, not a glob over `source/`. Each app
variant adds only its own entry point, so the block must be named explicitly or it is silently not
compiled and the link fails on the function Studio declared.

**What the built `.eim` scores.** This is the check the parity harness cannot make: parity stops at
the features and says nothing about whether Studio's ONNX-to-TFLite conversion of the uploaded
PANNs Cnn10 weights survived, nor whether the runner wires the two together as the impulse
describes. Driving real clips through the finished binary covers all three at once.

(The learn *block* itself is stock — Studio reports impulse 19 as input `time-series` 94, DSP
`organization` "PANNs log-mel" 95, learn **`keras-transfer-kws`** "PANNs Cnn10 transfer" 96. It is
the **DSP** block that is the custom one. This distinction is laboured because an earlier version
of this report and of ADR 0030 had it backwards, and used "the learn block is custom" to explain
why Studio offers no int8 for this impulse — an explanation that does not hold. See
[ADR 0030](../../docs/decisions/0030-acoustic-int8-reopened-against-the-panns-model.md); that
question is reopened, not answered.)

| | accuracy, 605-clip test split |
| --- | --- |
| argmax, no threshold | **92.56%** (560/605) |
| at Edge Impulse's default 0.6 confidence gate | **87.93%** (532/605) |
| Studio's reported figure for the same impulse | 87.77% (531/605) |

The middle row is the one that matters, because it is scored the way Studio scores — the same
confidence gate documented earlier in this section. One clip apart over 605 is as close as two
different runtimes are going to get, and it validates the entire chain end to end: the hand-written
DSP block, the resampler, the converted learn block, and the runner.

That comparison is only meaningful because the two sides are scored on the same clips, which was
checked rather than assumed: all 605 harness-test clips are in Edge Impulse's `testing` partition
and none is in its training partition, verified against the upload ledger.

It also resolves an apparent discrepancy that had been recorded as one. The 91.9% elsewhere in this
report is an **argmax** figure; Studio's 87.77% is **gated**. Setting one against the other was
never like-for-like. Compared properly, over identical clips at argmax:

| | overall | ambient | chainsaw | elephant_call | gunshot |
| --- | --: | --: | --: | --: | --: |
| `cnn10_10s_fp32.onnx` (harness) | 91.90% | 0.911 | 0.912 | 0.914 | 0.930 |
| deployed `.eim` | **92.56%** | 0.928 | 0.912 | 0.931 | 0.926 |

(recall per class). The deployed model is ahead overall and on two classes, level on chainsaw, and
one clip behind on gunshot recall. **There is no accuracy cost to deploying this model through Edge
Impulse**, which is the claim the whole custom-block exercise exists to establish.

**The same answers on ARM.** A cross-built aarch64 binary was scored under `qemu-aarch64-static`
against the x86 run. Zero argmax disagreements; largest difference in any class score 3.6e-07,
which is float32 rounding, not divergence. The one misclassification in that subset is the same
clip on both architectures, so it is the model's error rather than the port's. This is the check
that would catch float-contraction, vectorisation or libm differences between two toolchains, and
it is the only one available before the model reaches the board.

**On-target latency, measured.** The board number §7.4 asks for is no longer outstanding. The
deployed `.eim` was cross-built, copied to the UNO Q, served by the Edge Impulse Node runner on the
port `services/config.py` already points at, and driven with sixteen stratified test clips. Two
runs:

| per 10 s window | run 1 | run 2 |
| --- | --: | --: |
| front end (DSP) | 662 ms | 646 ms |
| classifier | 3,647 ms | 3,491 ms |
| **total inference** | **4,310 ms** | **4,136 ms** |
| wall clock, incl. HTTP and JSON | 4,511 ms | 4,274 ms |
| agreement with ground truth | 15/16 | 15/16 |

Both runs ran with the production stack live — the application process at roughly 111% CPU and the
vision runner at 69%, load average 3.33 across four cores — because that is the contention a second
model would actually meet on this board. A quiescent figure would be lower and would also describe
a machine this one never is. The real-time factor is **0.41–0.43**, about 4.2 s of compute per 10 s
of audio, which is what makes the polled design in `services/acoustic_watch.py` viable at
`ACOUSTIC_POLL_INTERVAL_S = 30` and what would make a continuous listen impossible.

(A third run, on the rebuilt artefact that actually ships, is below under *The host is not the
target*. It lands at 0.392 and is read as no regression rather than a speed-up.)

Two things this measurement overturns, both of which were written here as reasoning from the
figures then available.

Studio's profiler reports **4,134 ms**, and this report previously said that figure excludes the
front end and is therefore an underestimate. That was wrong. 4,134 ms falls *inside* the measured
range of the **total** (4,136–4,310 ms) and sits well above the measured classifier alone
(3,491–3,647 ms). The reasoning behind the original claim was sound — Studio genuinely cannot
profile a custom DSP block, and leaves its latency column blank — but the conclusion drawn from it
does not survive contact with the board. Why the estimate should match the total is unexplained,
two runs are not enough to establish that it generalises, and coincidence is not excluded; the
figure still should not be quoted as authoritative. But it is not an underestimate.

The x86 host split was read here as evidence that the front end is "a substantial fraction of the
total". On the actual target it is **15–16%**, and the classifier is the other 84%. The host ratio
(278 ms against 465 ms, or 37%) did not transfer, which is a reminder that a split measured on a
different microarchitecture is not a preview of the target's. The practical consequence points the
same way as [ADR 0030](../../docs/decisions/0030-acoustic-int8-reopened-against-the-panns-model.md):
the expensive part is the part quantisation acts on.

**The host is not the target: a glibc gate the host cannot see.** The binary above runs correctly
when launched directly on the board. That is not sufficient to ship it as an App Lab **brick**,
and the gap is invisible from the host.

App Lab bricks are Docker Compose services. The audio classifier brick,
`arduino:audio_classification`, runs `ghcr.io/arduino/app-bricks/ei-models-runner:0.10.0` — an
**Ubuntu 20.04 image, glibc 2.31, libstdc++ 6.0.28 (GLIBCXX up to 3.4.28)**. The board's host
userland is Debian 13 with **glibc 2.41**. A `.eim` cross-built against the host toolchain links
fine, runs fine on the host, and then fails inside the brick container on symbol versions that
simply do not exist there. `ldd` of the first artefact inside that image reported **seven missing
symbol versions** (`GLIBC_2.32` … `GLIBC_2.38`, `GLIBCXX_3.4.29` … `GLIBCXX_3.4.32`). No amount of
testing on the board's host would have surfaced this.

The fix is not a linker flag. Two attempts failed before the real constraint was identified:

- `--sysroot` pointed at a 20.04 rootfs, plus `-static-libstdc++`, still emitted `GLIBCXX_3.4.32`.
  The Makefile passes an explicit `-lstdc++`, and `-static-libstdc++` only governs the libstdc++
  the driver adds itself; separately, the cross toolchain's own `/usr/aarch64-linux-gnu/lib` is
  not sysroot-relative, so its newer glibc kept winning the search order.
- Forcing the older runtime archives in by hand then failed to link outright:
  `undefined reference to '_dl_find_object'` and `'__libc_single_threaded'`. These are **GCC 13's
  own runtime** calling glibc 2.35 and 2.32 respectively. **GCC 13 cannot target glibc 2.31 at
  all**, whatever sysroot it is given. The compiler itself has to be older.

What works is to build in an environment that never knew about the newer symbols: an **Ubuntu
20.04 amd64 chroot** with `crossbuild-essential-arm64`, which is **GCC 9.4 built against glibc
2.31**. It cannot emit a reference the brick container lacks, because it has never heard of one.
The build stays native x86_64 — the chroot is amd64, only the *target* is aarch64 — so there is no
qemu in the build path and no slowdown.

```
APP_EIM=1 USE_FULL_TFLITE=1 TARGET_LINUX_AARCH64=1   CC=aarch64-linux-gnu-gcc CXX=aarch64-linux-gnu-g++ make -j$(nproc)
```

One trap worth recording, because it produced a confusing failure: `make clean` in this Makefile is
guarded by the same `$(error Missing application ...)` as the build, so `make clean` **without**
`APP_EIM=1` aborts and deletes nothing. A rebuild then silently relinks the previous toolchain's
394 stale object files, and the link fails on a glibc 2.38 symbol (`__isoc23_strtoull`) that the
new compiler never emitted. Delete the objects explicitly.

| | 24.04 build | Focal chroot build |
| --- | --- | --- |
| max `GLIBC_` required | 2.38 | **2.29** |
| max `GLIBCXX_` required | 3.4.32 | **3.4.26** |
| `ldd` inside `ei-models-runner:0.10.0` | 7 missing symbol versions | **all resolve** |
| size | 34,547,744 B | 35,918,456 B |

**The rebuild changed the binary, not the model.** This matters, because a new toolchain is exactly
the kind of change that can move numerics, and re-running the 605-clip evaluation on the board is
expensive. Both artefacts were driven over the same sixteen stratified clips: **zero prediction
disagreements**, the same single miss on the same clip, and a largest absolute confidence
difference of **0.000000**. The classifier is the same prebuilt TFLite static archive in both
builds, so this is the expected result rather than a lucky one — but it was measured, not assumed,
and it is what allows the **92.56% / 605** figure above to carry over to the shipped artefact
without a re-run.

A third latency run, this time inside the brick's own container image:

| per 10 s window | run 1 | run 2 | run 3 (Focal, brick image) |
| --- | --: | --: | --: |
| front end (DSP) | 662 ms | 646 ms | 650 ms |
| classifier | 3,647 ms | 3,491 ms | 3,265 ms |
| **total inference** | **4,310 ms** | **4,136 ms** | **3,915 ms** |
| real-time factor | 0.431 | 0.414 | **0.392** |
| agreement with ground truth | 15/16 | 15/16 | 15/16 |

Run 3 is read as **no regression**, not as a speed-up. The classifier is the same prebuilt archive,
the board was under the same live-stack contention, and three runs on a contended four-core board
do not separate a 5% difference from scheduling noise. The useful claim is that containerising the
model and rebuilding it against a six-year-older toolchain cost nothing measurable.

**Registering it without Edge Impulse's builders.** The official App Lab import route
(`PUT /v1/models/ei/projects/{id}` on the local daemon) cannot serve this model: it hardcodes
`{float32, tflite, runner-linux-aarch64}` for board `unoq`, and the hosted build it triggers is
refused outright — *"Cannot build for \"runner-linux-aarch64\" as your project contains custom DSP
blocks. Use the C++ library export option and build locally."* That refusal is permanent while the
impulse keeps an organisation DSP block.

A custom model needs far less than the importer. The models index scans the custom-model directory
for any subdirectory containing a `model.yaml`, so two files register the model:

```
/home/arduino/.arduino-bricks/models/<model-id>/
    model.eim      the blob
    model.yaml     the descriptor
```

`deployment/install/install-acoustic-brick.sh` writes exactly that, verifies the blob against its
recorded sha256, and — since 30 September — **hard-fails on an `ldd` check inside the runner image
before installing anything**, so the class of failure described above cannot reach the board again.

One descriptor detail that is easy to get wrong: `CUSTOM_MODEL_PATH` is bind-mounted into the
container at the *same* path it has on the host, so `EI_AUDIO_CLASSIFICATION_MODEL` must be a
**host** absolute path. The built-in models use `/models/ootb/...`, which comes from a different
mount and is not a pattern to copy.

<!-- SECTION:DEPLOY -->

---

## 8. Caveats and limits

- **Single-run arm comparisons carry an error bar that most of them cannot survive.** Section 5 is
  the governing caveat on this whole report: Edge Impulse training is bit-reproducible on a given
  worker machine and not across machines, so the same script yields a small set of different
  models depending on scheduling. Overall-accuracy gaps under **1.5 points**, and per-class
  chainsaw gaps under **4.4 points**, are not resolved by the evidence here. Re-running an arm does
  not fix this, because repeats may all land on the same machine.
- **The residual is attributed, not eliminated.** Section 4 accounts for the remainder; it
  does not make it disappear. The honest ceiling for this architecture on this data, through
  Edge Impulse's own front end, is what section 5 reports.
- **Edge Impulse's reported validation metrics are not test metrics.** They are computed on an
  internal ~20% slice of the *training* pool (738 samples), not on the 605-clip test set.
  Every headline figure in this report is on the 605.
- **`elephant_call` licensing is unresolved.** The HiruDewmi source carries no license. For a
  deployment involving a government forest department this needs settling before the model
  ships as-is.
- **`AcousticClass` could not represent `elephant_call`** on the wire. Closed on 24 Sept by
  [ADR 0027](../../docs/decisions/0027-acoustic-class-scheme-reconciled-to-trained-model.md),
  which reconciled the enum, `schema.md` and the fusion routing to the four classes this model
  actually emits, and added a parity test so the three cannot drift apart again.
- **chainsaw remains the weakest class** even after every fix here. The durable remedy is
  field-recorded chainsaw audio at realistic range, not more open-corpus clips.

### 8.1 Open questions, left open

These are loose ends this investigation found and deliberately did not pull, recorded so the next
person does not have to rediscover them.

- **`win_size` 301 may be worth ~1 macro point, for reasons now unknown.** Section 6.6 falsified
  the mechanism that predicted it, but the local measurement that falsified the mechanism also
  showed win=301 with the best macro (84.7%) and best chainsaw (89.0%) of any normalisation tested.
  With the theory dead, that is an unexplained empirical hint on two seeds against a 2.9-point
  spread — not enough to act on, not nothing either. Testing it properly means an Edge Impulse DSP
  sweep with several runs per arm, now that section 5.4 has shown single runs will not settle it
  — and, per the same section, runs spread over time rather than back to back, since consecutive
  runs tend to share a machine and therefore a model.
- **CLOSED — Edge Impulse's 20% internal validation split looked like it was costing chainsaw
  6 points. It is not.** The local measurement was real and did not transfer; the lever was then
  tested directly on Edge Impulse and is rejected. The local result first, because it is what made
  this worth testing — a stratified 20% of the training pool held out, re-scored on the canonical
  605, under both normalisations:

  | condition | n | overall | chainsaw | ambient | elephant | gunshot |
  |---|--:|--:|--:|--:|--:|--:|
  | standardise, full pool | 3,688 | 82.8% | 76.5 | 78.6 | 87.9 | 87.4 |
  | standardise, 80% | 2,950 | 83.8% | **70.6** | 82.6 | 91.4 | 86.8 |
  | win=101, full pool | 3,688 | 79.6% | 85.3 | 72.9 | 95.7 | 80.7 |
  | win=101, 80% | 2,950 | 83.4% | **79.4** | 78.8 | 98.3 | 85.4 |

  chainsaw loses **−5.9 points in both conditions** — the same number twice, under two different
  front ends — while every other class *gains* and overall accuracy rises. That looked like the
  signature of a data-quantity effect on one small class: Edge Impulse trains on 2,950 of 3,688
  clips, and the ~90 chainsaw clips it withholds would be the ones being felt.

  `trainTestSplit` turns out to be a **writable field** on the learn block — undocumented, found by
  dumping the block's own keys — so the prediction could be tested rather than argued. It was, and
  it failed twice over.

  **First failure: the mechanism is wrong.** Sweeping 0.10 and 0.05 (three runs each) gave chainsaw
  58.8 at 0.10 against a 44.1–48.5 baseline span — but 0.05 trains on *more* data still (3,503
  against 3,319) and scored 45.6–51.5. More data producing less chainsaw refutes a pure
  data-quantity story. Section 6.7 explains the real shape: the fraction is a two-sided lever,
  because the validation set does not only measure, it *selects the checkpoint*.

  **Second failure: the gain was a worker artefact.** All three 0.10 runs returned one identical
  model, so that arm was a single worker draw replicated three times, not three samples — and it
  ran in the 17–18 ms/step band. A paired A/B settled it: five 0.20/0.10 pairs run back to back so
  each pair shares a machine (section 5), order flipped on alternate pairs, and any pair whose
  halves landed in different speed bands *dropped* rather than averaged in. Four of five paired
  cleanly, and all four agreed exactly:

  | worker-matched pair | overall | chainsaw |
  |---|--:|--:|
  | split 0.20 | **82.6%** | 44.1 |
  | split 0.10 | 80.5% | **47.1** |

  With the machine held fixed, 0.10 buys **+2.9 chainsaw** — inside the 4.4-point chainsaw span, so
  not an established gain — and costs **−2.1 overall**, which is *outside* the 1.5-point overall
  span and is therefore a real regression. The 58.8 belonged to a worker, not to a setting.

  **The lead is closed and the split stays at 0.20.** It is worth stating plainly what nearly
  happened: the unpaired sweep would have supported writing a 10-point chainsaw improvement into
  this report, and it would have been fiction. The only thing that caught it was pairing runs so
  the scheduler was held fixed — which is section 6.3's rule applied to itself, one lever measured
  in the pipeline that will ship rather than in the one that was convenient.
- **The local-vs-Edge-Impulse chainsaw gap is now entirely unexplained.** The local harness at
  Edge Impulse's own normalisation scores chainsaw 85.3% against Edge Impulse's matching arm at
  66.2%. Until the bullet above was tested, 5.9 of those 19 points were credited to the validation
  split; on Edge Impulse that account came to **none**, so the full 19 points are open. Two things
  keep this from being alarming rather than merely unresolved: the gap sat inside what was assumed
  to be a deterministic measurement until section 5.1, and Edge Impulse's chainsaw recall alone
  spans 4.4 points across identical runs. It should be re-measured with several runs per side,
  spread over time so they do not all share a worker, before anyone concludes there is a front-end
  difference left to find.
- **No on-device measurement.** Covered in section 7.4; repeated here because it is the one
  outstanding item that no amount of further analysis can close.
