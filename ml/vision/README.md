# Three-class object-detection vision model — Elephant + Boar + Background

Edge Impulse project **1097972** (`ETX-V`). This was project 1094260 (`EleTect-X-Vision`) at the
proof-of-concept stage; the project was recreated once the corpus grew past the original two-class
FOMO scope (see below). Project ID only is recorded here; the API key is not in the repo and must be
supplied through `EI_API_KEY` at run time.

**Read the caveats section before quoting either number anywhere.** The deployed champion is a
**YOLO-Pro (`no_attn_relu`, `medium` sizing)** object detector, not the original FOMO proof-of-concept
— trained on real, openly-licensed camera-trap and wildlife-photography datasets with real
annotator-drawn bounding boxes, plus a small amount of the project's own board captures and synthetic
pseudo-IR augmentation — and it is still trained mostly on daytime colour wildlife photography, while
the deployment target is a night-IR camera. Both halves of that sentence have to travel together.

## Dataset

**Corrected 3 Sept 2026 — this table was stale since the corpus grew from 3 to 7 Boar sources and
gained 2 more Elephant sources. Verified counts below are read straight from
`ml/vision/dataset_manifest.json`, the source of truth; treat this table as a snapshot, not a
substitute for it.**

| Class | Source | License | Images | Boxes |
|---|---|---|---|---|
| Elephant | `roboflow-universe-projects/elephant-detection-cxnt1/2` | CC BY 4.0 | 1,251 | 1,265 |
| Elephant | `customdataset-aucsj/asian-elephants-dataset/1` | CC BY 4.0 | 2,358 | 4,308 |
| Elephant | `wcs-elephas-maximus` | CDLA-Permissive-1.0 | 194 | 227 |
| Elephant | `wild-boar-fmkcg/night-ojblh/1` (relabelled) | CC BY 4.0 | 73 | 56 |
| Elephant (synthetic) | `pseudo-ir-elephant` | derived from the real sources above | 218 | 348 |
| **Elephant total** | *(5 sources)* | | **4,094** | **6,204** |
| Boar | `trackabox-4ejy9/wild-boar-a1flm/1` | CC BY 4.0 | 1,556 | 2,117 |
| Boar | `boarwatch/wild-boar-deterrent-pzq5t/1` | CC BY 4.0 | 1,636 | 2,182 |
| Boar | `roboflow-100/trail-camera/2` (relabelled) | CC BY 4.0 | 1,311 | 1,398 |
| Boar | `wcs-sus-scrofa` | CDLA-Permissive-1.0 | 827 | 1,228 |
| Boar | `pig-rinoz/wild-pig-at-night/1` (relabelled) | CC BY 4.0 | 64 | 125 |
| Boar | `swg-eurasian-wild-pig` | CDLA-Permissive-2.0 | 1,800 | 2,373 |
| Boar (synthetic) | `pseudo-ir-boar` | derived from the real sources above | 200 | 303 |
| **Boar total** | *(7 sources)* | | **7,394** | **9,726** |
| Background | `swg-empty` | CDLA-Permissive-2.0 | 2,398 | — |
| Background | `board-captures-day1` | own capture | 26 | — |
| Background | `board-captures-night1` | own capture | 207 | — |
| **Background total** | *(3 sources)* | | **2,631** | — |

Only 64 of the 7,394 Boar images are real night/IR camera-trap imagery
(`pig-rinoz/wild-pig-at-night`) — 0.87%. The remaining night/IR coverage is 200 synthetic
`pseudo-ir-boar` images. See `ml/vision/boar-representation-audit.md` for the full per-source
condition breakdown this gap motivated.

**Why the original three are real:** the first three sources listed were pulled live from Roboflow's
COCO export API (`scripts/edge_impulse_upload_vision.py`), full images with real annotator-drawn
bounding boxes, not synthesized or scraped-and-guessed. Citations, verbatim from each Universe page
(citations for sources added after the original three are not yet transcribed here — see each
source's own Universe/registry page):

```bibtex
@misc{ elephant-detection-cxnt1_dataset,
    title = { Elephant Detection Dataset },
    type = { Open Source Dataset },
    author = { Roboflow Universe Projects },
    howpublished = { \url{ https://universe.roboflow.com/roboflow-universe-projects/elephant-detection-cxnt1 } },
    url = { https://universe.roboflow.com/roboflow-universe-projects/elephant-detection-cxnt1 },
    journal = { Roboflow Universe },
    publisher = { Roboflow },
    year = { 2022 },
    month = { dec },
    note = { visited on 2026-08-22 },
}
```

```bibtex
@misc{ wild-boar-a1flm_dataset,
    title = { Wild Boar Dataset },
    type = { Open Source Dataset },
    author = { Trackabox },
    howpublished = { \url{ https://universe.roboflow.com/trackabox-4ejy9/wild-boar-a1flm } },
    url = { https://universe.roboflow.com/trackabox-4ejy9/wild-boar-a1flm },
    journal = { Roboflow Universe },
    publisher = { Roboflow },
    year = { 2022 },
    month = { jun },
    note = { visited on 2026-08-22 },
}
```

```bibtex
@misc{ wild-boar-deterrent-pzq5t_dataset,
    title = { Wild Boar Deterrent Dataset },
    type = { Open Source Dataset },
    author = { BoarWatch },
    howpublished = { \url{ https://universe.roboflow.com/boarwatch/wild-boar-deterrent-pzq5t } },
    url = { https://universe.roboflow.com/boarwatch/wild-boar-deterrent-pzq5t },
    journal = { Roboflow Universe },
    publisher = { Roboflow },
    year = { 2026 },
    month = { jan },
    note = { visited on 2026-08-23 },
}
```

**Boar top-up: BoarWatch, one listing of a duplicated dataset, group-sampled to close the
instance gap.** Added 23 Aug after confirming every stock FOMO knob (resolution, cycle count,
class weighting, augmentation) was exhausted — see the 23 Aug entries below — leaving "more Boar
data" as the one untried, real lever. Three things worth recording about how it was sourced:

- **Duplicate-listing trap avoided.** The same 8,857-image dataset is also listed under
  `deepanshu-thapa-bgz3j/wild-boar-deterrent` — verified via the Roboflow API before downloading
  either (byte-identical `created` timestamp, image count, splits, and class counts). Only the
  `boarwatch` listing is used here, so the same photos are never counted or uploaded twice under
  two different citations.
- **Class `0` relabeled to `Boar`**, the same discipline as Trackabox's `Pig` → `Boar` relabel;
  the source project's only annotated class carries no descriptive name at all.
- **Group-sampled, not bulk-uploaded, and with a different grouping rule than the rest of this
  dataset.** The 8,857 images collapse to only 2,483 real distinct-photo groups (most of the
  "extra" images are same-photo re-exports at a second resolution) — bulk-uploading all 8,857
  would have added far more redundancy than real diversity and overshot Elephant's count by 2.7×.
  Its filenames are also catalog-style sequential IDs (`Wild_Boar_0001`, `Wild_Boar_0002`, … —
  confirmed each number is a *different* source photo, not a consecutive video frame, since the
  duplicate-group size tops out at 6 under exact-stem matching and `date_captured` is flat
  upload-time metadata that cannot distinguish the two cases either way), not genuine video-frame
  bursts like Trackabox's `wb_framesNNNNN`. Applying this dataset's `group_key()` (built for real
  frame sequences) here collapses `Wild_Boar_*` into one 1,155-image mega-group — a grouping
  artifact, not a real duplicate. `group_key_exact()` is used instead: only Roboflow's own
  `_jpg.rf.<hash>` rewrite is stripped, so same-photo re-exports still collapse into one group
  while distinct sequentially-numbered photos do not. 1,379 of the 2,483 groups were then sampled
  (seed `20260822`, one representative image per group, shuffled group order) — enough to bring
  Boar's total from 1,901 to exactly 3,280, matching Elephant, with no residual overshoot.

**Elephant: v2, not v4.** The project's latest export (v4, 12,460 images) is Roboflow's own 5×
augmentation of the v2 train split — the same 3,280 source images, quintupled. Uploading v4 would
have both double-augmented on top of Edge Impulse's own training-time augmentation and skewed the
Elephant:Boar ratio to 6.6:1 instead of the dataset's real 1.7:1. v2 (`resized640`, 3,280
un-augmented images) is what was actually uploaded.

**Boar: `Pig` relabeled to `Boar`.** The source project's only annotated class is named `Pig`, but
the dataset itself is titled "Wild Boar Dataset" and every filename stem (`Wild_Boar…`,
`wb_frames…`) confirms the subject — this is wild boar footage, not domestic pig, mislabeled
upstream. Relabeled on ingestion; not a EleTect-X judgement call about the animal in the photos,
a correction of the source project's own class name. A second, stray class literally named `` ` ``
was declared in the category list but carried zero annotated boxes in this export — dropped, not
uploaded.

**Split: group-aware, not per-image random, seed `20260822`.** Both sources contain video-frame
sequences (Boar especially — `wb_framesa00001`, `wb_framesb`, … are contiguous frame dumps), and a
per-image random split would put near-identical adjacent frames on both sides of the boundary,
inflating the held-out score. Groups are the filename stem with Roboflow's `_jpg.rf.<hash>` suffix
and any trailing frame digits stripped; groups are shuffled with the fixed seed above and filled to
~80% training. This ignores Roboflow's own train/valid/test split entirely — the whole COCO export
for each project was pulled as one pool and re-split here, the same "split by event, not by
sample" discipline `ml/seismic/README.md` uses.

| Class | Groups | Images in multi-image groups | Training | Testing |
|---|---|---|---|---|
| Elephant | 2,260 | 1,107 (34%) | 2,559 | 721 (22.0%) |
| Boar — trackabox | 1,273 | 631 (33%) | 1,483 | 418 (22.0%) |
| Boar — BoarWatch top-up | 1,379 | 0 (0%) | 1,076 | 303 (22.0%) |
| **Boar total** | **2,652** | **631 (19%)** | **2,559** | **721 (22.0%)** |

The BoarWatch top-up's own split is effectively per-image random, not group-protected: every
sampled group already contributes exactly one image (that is the point of the group-aware
subsample above), so there is no residual redundancy left for grouping to guard against at split
time. This is expected, not a gap — the discipline was applied one step earlier, at sampling.

Every image carries at least one box **or** is a genuine zero-annotation frame from the same
source set, kept as a FOMO background/negative example rather than dropped: 552 of Elephant's
3,280 images and 4 of Boar's 1,901 trackabox images (BoarWatch's sampled top-up contributes none —
every one of its images carries a box). The exact split — every filename, its group, and which side
of the boundary it landed on — is committed in `ml/vision/dataset_manifest.json`, so the numbers
below are reproducible from a fresh clone without re-running the split.

## Impulse

- **Input** (block 1): image, 96×96, resize mode `squash`. Both sources arrive pre-resized by
  Roboflow to different aspect-preserving-or-not dimensions (Elephant 640×640, Boar 416×416) —
  squashing again to 96×96 adds no new distortion beyond what each source already applied.
- **DSP** (block 2): image block, RGB channels — FOMO's colour input, already the block default,
  set explicitly so it is a documented choice rather than an inherited one.
- **Learn** (block 3): object detection, `fomo_mobilenet_v2_a35` (picked from the project's live
  `/transfer-learning-models` list, not hardcoded — the alpha-0.35 backbone over alpha-0.01,
  still small enough for the QRB2210, better recall). Non-default parameters, each chosen not
  inherited:
  - `autoClassWeights: true` — the 1.7:1 Elephant:Boar image ratio would otherwise let the
    majority class dominate the loss.
  - `augmentationPolicyImage: all` — Edge Impulse's default image augmentation, left on rather
    than disabled, given how small this training set is next to typical object-detection corpora.
  - `profileInt8: true` — the deployment target (`CONTEXT.md:30`) is an INT8 detector; both
    float32 and int8 variants were trained and profiled.
  - Learning rate `0.001`, 60 training cycles — these are `fomo_mobilenet_v2_a35`'s own live-reported
    defaults for this block, confirmed via the API rather than assumed, so they are recorded here
    as "used", not as "chosen".

## Result

FOMO is a centroid detector, not a classifier — Edge Impulse reports precision/recall/F1 per
class, not "accuracy". **Elephant and Boar are reported separately below and must never be averaged
into one headline number** — the 1.7:1 image-count gap between them makes a per-class gap expected,
not a surprise, and it shows up in both numbers below in the same direction.

These are the current numbers, from the 23 Aug BoarWatch top-up retrain (96px, 100 cycles, Boar
brought to image parity with Elephant at 3,280 : 3,280) — the best result to date. See the dated
entries below for the full history (60-cycle baseline, the resolution ladder, the 100-cycle gain,
and this top-up) and an honest read of what each step actually changed.

**Training-time validation** (from the training job's own held-out validation split, INT8
variant — the model type actually destined for the field):

| Class | Precision | Recall | F1 | Support (grid cells) |
|---|---|---|---|---|
| Elephant | 0.718 | 0.567 | 0.634 | 813 |
| Boar | 0.769 | 0.734 | 0.752 | 659 |

(float32 variant, for comparison: Elephant 0.716 / 0.608 / 0.657 on 819 cells; Boar 0.787 / 0.731 /
0.758 on 662 cells.)

**Held-out model test**, run as an Edge Impulse model-testing job over the real testing split
those training images never touched. Edge Impulse's own `classify/all/result` reports a
single aggregate pseudo-class ("F1 score": 746 good / 684 bad, 52.2%) for object-detection
projects rather than breaking it out per label — so the per-class numbers below were computed
directly from that endpoint's per-sample results, grouped by each image's own ground-truth label
(`sample.label` is a comma-joined list of every box's class in that image; every image in each
source set carries only that set's class, so splitting on `,` and taking the first token groups
exactly, not by inference):

| Class | Test images | Mean per-image F1 | Mean precision | Mean recall | Images scored a perfect F1 |
|---|---|---|---|---|---|
| Elephant | 649 | 0.692 | 0.749 | 0.693 | 329 (50.7%) |
| Boar | 709 | 0.618 | 0.629 | 0.666 | 291 (41.0%) |

The remaining 72 test images are zero-annotation Elephant-set background frames (BoarWatch
contributed none of its own); FOMO predicted no false centroid on 61 of them (mean F1 0.847, 84.7%
clean) — still a small and Elephant-skewed negative sample, see caveat 2. Note also that
5,059 training / 1,430 testing images were actually live in the project for this run, 71 short of
the 6,560 the manifest expects (2,559 + 2,559 train, 721 + 721 test): the upload script sends
`x-disallow-duplicates: 1` on every request, and Edge Impulse accepts the request without an error
when a byte-identical image already exists under a different filename — plausible here since
BoarWatch and Trackabox both curate web-sourced wild boar photography and could easily share a
handful of identical source images. Not further diagnosed; the manifest's per-source counts track
what was *sent*, not what the project actually stored.

## Caveats — required whenever either number is quoted

1. **Neither dataset is IR-illuminated night camera-trap footage.** Both are general daytime/colour
   wildlife photography. ADR 0001 (`docs/decisions/0001-usb-camera-imx462.md:7`) states over 70% of
   elephant raids are nocturnal, requiring 940 nm active-IR night vision. This work closes *"a
   two-class FOMO model exists and is trained on real, licensed data"* — it does **not** close
   *"this model works on real field IR footage at night."* Those two claims must travel separately;
   nothing here measures night-IR performance at all.
2. **The background/negative sample is small and lopsided.** 556 of 6,560 source images (552
   Elephant, 4 Boar) carry no annotation and were kept as FOMO negatives, but they are stray
   unannotated frames from the same source collections, not a curated set of "genuinely empty
   forest" scenes, and there are effectively none from the Boar side. The 94.4% clean-negative
   figure above says very little about the false-positive rate on real empty-forest footage, and
   nothing at all about Boar false positives specifically.
3. **Class imbalance at the image-count level is resolved (3,280 : 3,280); it was never the
   whole story.** The Boar top-up (23 Aug) closed the raw image-count gap that drove caveats 2-5
   of the 23 Aug cycle-count entry below. `autoClassWeights` remains enabled regardless — instance
   counts (box-level, not image-level) still favor Elephant somewhat, see the 23 Aug entries.
4. **Source images arrive at two different resolutions**, Boar 416×416 and Elephant 640×640,
   both stretch-resized upstream by Roboflow before either set reaches this project, then both
   squashed again into FOMO's 96×96 input. No attempt was made to correct for this.
5. **Not deployed.** No `.eim` export exists, no detector runs anywhere in the field path, and
   `cognition/fusion.py`'s `VISION` modality stays unpopulated — see the open follow-up entry in
   `docs/KNOWN_GAPS.md`. This README records that a model was trained, not that it does anything yet.
6. **`CONTEXT.md:30`'s "Adreno/OpenCL" and ADR 0001's "no QNN/Hexagon delegate" are not actually in
   conflict** (resolved 23 Aug, see `docs/KNOWN_GAPS.md`'s Build-call 3 section). QNN/Hexagon is the
   NPU delegate, which ADR 0001 rules out; Adreno/OpenCL is the GPU delegate, a separate path Edge
   Impulse's own Linux SDK docs describe as automatic through `edge-impulse-linux-runner`
   (`docs/DEVICE_DEVELOPMENT_WORKFLOW.md:269`). What's still open: nobody has actually run that
   runner on real UNO Q hardware in this repo, so GPU acceleration is doc-confirmed, not
   hardware-confirmed. Either way it's orthogonal to model size — the quad Cortex-A53 alone has real
   headroom for this model with no delegate at all.

*Correct framing for a report table: proof-of-concept two-class FOMO detector trained on real,
CC BY 4.0-licensed daytime wildlife photography (3,280 Elephant / 3,280 Boar images, group-aware
80/20 split); held-out per-image F1 0.69 Elephant / 0.62 Boar; not field-validated, not night-IR
validated, not deployed.*

## 23 Aug — resolution-increase diagnostic (retrain in progress)

Step 1 of the improvement plan referenced above, run against project 1094260. Live-checked against
the API and the generated training script rather than assumed:

- **Backbone is already maxed.** `fomo_mobilenet_v2_a35` is the largest pretrained FOMO backbone
  Edge Impulse offers — the project's own `/transfer-learning-models` list has weights for alpha
  0.1 and 0.35 only, nothing bigger. "Bigger backbone" is not an available lever; resolution and
  data are the only ones left.
- **Real instance-level class ratio, not just image counts.** Cross-validated against the raw COCO
  annotations and the split ledger: Elephant 3,193 train / 1,284 test box instances, Boar 2,403
  train / 600 test — a 1.49:1 ratio, milder than the 1.7:1 image-count ratio already quoted above.
- **Mechanistic cause of the "defaults to background" result, found and quantified.** Elephant's
  test split has 35.7% of box instances under 2% of frame area, versus 12.2% in training — a real
  train/test shift toward smaller objects — compounding 96px's coarse 12×12 FOMO grid, where
  anything under ~2% of frame area only spans 2-3 grid cells. Both classes defaulting to background
  at similar rates is consistent with this, not with a discrimination failure between the two
  classes (cross-species confusion stays near zero throughout).
- **On-device footprint reconciled.** The 133KB RAM / 81.3KB flash / 6ms figures quoted for the
  int8 model match the `eon_ram_optimized` build variant specifically (confirmed via the API:
  ram=136,144B / rom=83,248B); the default balanced `EON` build profiles slightly larger
  (~153.7KB/67.4KB). Both are for the same UNO Q/QRB2210 profile — not an MCU-vs-QRB2210 mix-up,
  just two different EON compiler passes over the same trained model. Either number is trivial
  against real QRB2210 headroom.
- **224px hit Edge Impulse's free-tier compute cap, not a QRB2210 constraint.** Tried first, to
  isolate resolution as the only variable — the platform's own pre-flight estimate was 1h31m
  against a 1-hour free-tier training-job ceiling, an account-tier limit that would disappear on a
  paid plan, not a sign 224px is too heavy for the field target. Stepped down to 160px (20×20
  grid, 400 cells — still 2.8× finer than 96px) instead; that run was in progress as of this entry,
  everything else (backbone, augmentation, `autoClassWeights`, learning rate/cycles) held constant
  so resolution is the only variable that changed.

No new F1/precision/recall numbers exist yet from this run — the "Result" table above is still the
96px baseline until the 160px job finishes and reports for real.

## 23 Aug — resolution ladder result: three losses, reverted to 96px

The 160px and 128px jobs referenced above both finished. Same protocol as the baseline: training-time
validation from the job's own held-out split, then an independent model-testing job over the real
testing split, aggregated per class with the fixed comma-parsing method (`sample.label` is a
comma-joined list of every box's class in that image, e.g. `"Boar, Boar, Boar"` — grouping must split
on `,` and take the first token, not split on whitespace).

| Resolution | Grid | Elephant F1 / P / R | Boar F1 / P / R | Held-out aggregate |
|---|---|---|---|---|
| **96px (baseline)** | 12×12, 144 cells | 0.670 / 0.729 / 0.669 | **0.567** / 0.563 / 0.634 | 585/1139 good (51.4%) |
| 128px | 16×16, 256 cells | 0.593 / 0.640 / 0.587 | 0.313 / 0.328 / 0.330 | 478/1139 good (42.0%) |
| 160px | 20×20, 400 cells | 0.639 / 0.684 / 0.639 | **0.165** / 0.173 / 0.180 | 452/1139 good (39.7%) |
| 224px | 28×28, 784 cells | — | — | rejected pre-flight, see below |

224px never trained: Edge Impulse's own pre-flight estimate (1h 31m) exceeded the free-tier account's
1-hour-per-job compute ceiling, and the job failed after 2.7 minutes without running — an account-tier
limit, not evidence about the QRB2210 deployment target.

**This result is the opposite of the working hypothesis.** The plan going in (see the 23 Aug entry
above) was that 96px's coarse grid was the primary cause of the "defaults to background" failure, so a
finer grid should recover detections on small objects. Instead, resolution increase alone —
everything else (backbone, learning rate, 60 cycles, augmentation, `autoClassWeights`) held fixed —
**monotonically regressed both classes**, and Boar was hit far harder than Elephant at every step
tested. Per-cycle training cost also scales faster than linearly with resolution (96px 0.52 min/cycle,
128px 0.73 min/cycle, 160px 0.95 min/cycle), so each finer grid left less of the 1-hour budget free to
also raise cycle count within the same job — the leading explanation is that the finer grids are
undertrained at the same fixed 60-cycle budget, not that finer resolution is inherently worse for this
task.

**Reverted `IMAGE_SIZE` to 96 — the best real result of the four — rather than ship a worse model
for the sake of having changed something.** `scripts/edge_impulse_train_vision.py`'s `IMAGE_SIZE`
comment carries this same conclusion.

**EON Tuner (the plan's step 7, systematic hyperparameter search) turned out not to be reachable from
this account.** Checked live: every plausible `/v1/api/{project}/tuner/*` endpoint 404'd against the
project-scoped `EI_API_KEY`, and a probe against a genuinely tuner-adjacent organization endpoint
confirmed the reason — it requires an organization-level API key, which this free-tier account does
not have. Running EON Tuner manually through Studio's UI remains possible but is not scriptable with
what this project has; not attempted, stated here rather than silently skipped.

**Next controlled test: cycle count, not resolution.** All three trials above left `TRAINING_CYCLES`
at Edge Impulse's own default (60) — cycle count has never actually been varied, at any resolution,
including the 96px baseline itself. `TRAINING_CYCLES` raised to 100 at 96px (fits the compute cap at
~52 estimated minutes) as the next single-variable test, to check whether the baseline itself is
undertrained before concluding FOMO's architecture (not its training budget) is the limiting factor
per the plan's step 6.

## 23 Aug — cycle-count result: real gain on Elephant, Boar unmoved

100 cycles at 96px (job 52989183, 55.4 of the 60-minute cap used), same held-out protocol as above:

| Config | Elephant F1 / P / R | Boar F1 / P / R | Held-out aggregate |
|---|---|---|---|
| 96px, 60 cycles (baseline) | 0.670 / 0.729 / 0.669 | 0.567 / 0.563 / 0.634 | 585/1139 good (51.4%) |
| **96px, 100 cycles** | **0.705 / 0.778 / 0.706** | 0.565 / 0.562 / 0.613 | **607/1139 good (53.3%)** |

This is the best real result to date, and a real (not noise-level) gain — but only on Elephant. Every
Elephant metric improved; Boar's -0.002 F1 move is within noise. Training-time validation (int8) shows
the same split: Boar's own validation F1 rose 0.500 → 0.589, so more cycles did help Boar converge
during training, but that gain didn't survive onto the held-out test — consistent with Boar having
fewer training instances (2,403 vs Elephant's 3,193 box instances) making it more prone to overfitting
the validation split specifically as training runs longer, rather than genuinely learning more general
features. This is a real result, held at the noise floor for Boar, not a win — it must not be reported
as "cycle count fixed Boar."

100 cycles used 55.4 of the 60-minute compute cap, leaving room for roughly 8 more cycles at this
resolution before hitting the ceiling again — not enough headroom to meaningfully retest cycle count
further within a single job.

**Where this leaves the plan's steps 2-7:** resolution (step 2) tested and reverted; class weighting
(step 4) and augmentation (step 5) were already at Edge Impulse's maximum before this investigation
started; the Adreno/OpenCL question (step 3) is resolved (caveat 6 above); EON Tuner (step 7) is
inaccessible on this account tier. Cycle count, the one remaining stock-FOMO knob, produced a real but
small gain, and only for the majority class. **The model remains well short of the ~90% target: best
result at this point is Elephant F1 0.705 / Boar F1 0.565, not 0.90 for either class.** Two honest
paths remained open at this point: (a) step 6's heavier/custom architecture (BYOM or ONNX custom
learning block, a genuine platform change, not a config tweak), or (b) sourcing more Boar training
images specifically — the relayed guidance's suggestion of targeted Boar-side data, not
`autoClassWeights` (already on) or `augmentationPolicyImage` (already maxed), which reweight or
transform existing images rather than add real visual variety. Path (b) was pursued next — see the
BoarWatch top-up entry below.

## 23 Aug — BoarWatch top-up retrain result: real gain on Boar, a small give-back on Elephant

Boar brought from 1,901 to 3,280 images (image parity with Elephant) via the BoarWatch CC BY 4.0
dataset, group-sampled to avoid redundancy — see the Dataset section above for the sourcing and
sampling rationale. Retrained at the same 96px / 100-cycle config as the best result so far (job
52992531, 62.7 min), same held-out protocol as every entry above:

| Config | Elephant F1 / P / R | Boar F1 / P / R | Held-out aggregate |
|---|---|---|---|
| 96px, 100 cycles, Boar 1,901 (pre-top-up) | **0.705** / 0.778 / 0.706 | 0.565 / 0.562 / 0.613 | 607/1139 good (53.3%) |
| **96px, 100 cycles, Boar 3,280 (top-up)** | 0.692 / 0.749 / 0.693 | **0.618** / 0.629 / 0.666 | 746/1430 good (52.2%) |

**Boar moved: +0.053 F1 (0.565 → 0.618), driven mostly by recall (+0.053) with precision also up
(+0.067).** This is a real, structural change, not noise — training-time validation shows the same
direction and a bigger swing (int8 Boar F1 0.581 → 0.752), and the held-out test set for Boar grew
from 418 to 709 images at the same split ratio, so the gain is measured on a larger, more diverse
sample than before, not a smaller one that would make a swing this size easier to get by chance.

**Elephant gave back some of the previous session's cycle-count gain: -0.013 F1 (0.705 → 0.692).**
Elephant's own data did not change at all between these two runs (still 3,280 images, same split
seed) — the only thing that changed project-wide is Boar's volume and the resulting batch
composition each training epoch sees. `autoClassWeights` is on, so this is plausibly the
classifier's decision boundary shifting slightly now that Boar is no longer the minority class, or
plausibly just run-to-run training stochasticity (FOMO's Keras training is not seeded run-to-run
here). At -0.013 F1 this sits close to the noise floor the cycle-count entry above established for
Boar's own unchanged runs (-0.002); it should be read as "roughly flat, not a real regression," not
ignored.

**Net: a genuine but partial win.** The instance-count gap the plan set out to close is closed at
the image level (3,280 : 3,280); the held-out aggregate is essentially flat (53.3% → 52.2%) because
Boar's gain and Elephant's small give-back mostly cancel once reweighted by the larger held-out set.
**Neither class is within reach of the ~90% target: Elephant F1 0.692, Boar F1 0.618.** More Boar
data measurably helped Boar without hurting Elephant much, which validates path (b) was worth
doing — but it was not the single fix that closes the gap to 90%. The plan's remaining path, (a)
step 6's heavier/custom architecture (BYOM or ONNX custom learning block), is the only untried lever
left; it is a genuine platform change, not a further single-variable retrain, and should go back to
the user as a decision point before starting.

## 27 Aug — 3a species verification: Elephant class is contaminated with African bush elephant

The Elephant class was never visually checked against species before this — "Elephant" in the
Roboflow source project name and the CC BY 4.0 citation above say nothing about *which* elephant,
and this deployment is for Asian elephant (*Elephas maximus*) raids in Kerala. Checked two ways
against the full 3,280-image class before trusting any number built on it further.

**Filename scan, full population.** Grepped all 3,280 Elephant filenames (both `training` and
`testing` lists in `dataset_manifest.json`) for African range-country/park names (`namibia`,
`kenya`, `tanzania`, `kruger`, `etosha`, `amboseli`, `zimbabwe`, `serengeti`, …) and their Asian
counterparts (`kerala`, `india`, `thailand`, `sri lanka`, `kaziranga`, `sumatra`, …): **34 filenames
(1.0%) name an African location explicitly** (e.g. `african-elephants-crossing-road-zimbabwe...`,
`elephant-kenya-africa-amboseli-reserve...`, `focused_263792030-stock-photo-africa-namibia-etosha...`);
**zero name an Asian one.** Filenames are stock-photo captions or camera-trap IDs, so this only
catches images whose caption happened to name a place — a floor on contamination, not the true rate.

**Visual sample, seed `20260822`** (same seed as the train/test split, per the plan). Sampled 30
filenames from the combined training+testing list, located each in
`ml/datasets/vision/raw/elephant-detection-cxnt1-v2/`, and read them directly. 7 of the 30 turned
out to be zero-annotation background frames already known from the Dataset section above (casino
interior, a portrait, a street scene) — not elephants at all, excluded from scoring. Of the
remaining 23 images actually showing an elephant, scored on back profile and forehead shape first,
ears second, tusks/trunk explicitly not used (per the plan's own discriminator ordering):

| Read as | Count | Share of scoreable |
|---|---|---|
| Asian (*Elephas maximus*) | 17 | 73.9% |
| African bush (*Loxodonta africana*) | 4 | 17.4% |
| Indeterminate (too dark/small/distant to score) | 2 | 8.7% |

The 4 African reads are unambiguous, not borderline calls: `A0004-108-...jpg` is a black-and-white
night camera-trap frame of a herd on open grassland with fan-shaped ears reaching well past the
shoulder and a concave (sway) back; `65_jpeg...jpg` and `af_tr142...jpg` (the latter's own filename
stem is literally `af_tr`, an African-camera-trap-style ID, not caught by the place-name grep above)
both show a single animal in dry savanna scrub with large fan ears and a single-domed forehead;
`african-elephants-crossing-road-elephant-breeding-herd-51793540...jpg` is a family group crossing a
paved road with the same ear/back signature, and is one of the 34 filename-scan hits above. None of
the 4 show any Asian discriminator (no bilobed forehead, no small cupped ears, no convex back).

**Caveat on the 73.9% Asian figure: the sample is not 23 independent draws.** Six of the 17 Asian
reads (`frame5203`, `frame4971`, `frame5757`, `frame5018`, `frame5080`, `frame5758`) are consecutive
frames from the same single viral video of an elephant reaching into a Tamil Nadu sugarcane truck;
four more (`0003-127`, `as_te42`, `Image14`, `E026-139`) are frames from Thai TV news broadcasts of
roadside elephant herds. The true count of *distinct source events* in the Asian bucket is closer to
8-9, not 17 — the dataset's own group-aware split (Dataset section above) exists precisely because
this class is heavily bursty. The African bucket shows no comparable duplication (4 distinct scenes,
4 distinct animals/herds), so if anything this correlation understates the African share rather than
inflating it.

**Verdict: real contamination, not a rounding error.** At least 4/23 sampled elephant images (and at
least 34/3,280 by filename alone) are African bush elephant, a different species with a visually
distinct silhouette from the Kerala deployment's actual target. This is a genuine data-quality
problem for a species-specific detector, not something to wave off as "close enough" — a FOMO
centroid detector trained partly on African bush elephant silhouettes is being asked to generalize
to Asian elephant silhouettes it was never consistently shown. **Recommendation, not yet
implemented:** filter the class by the filename-scan hits (cheap, catches the 34 explicit cases) and
fold in a species-correct supplement — Phase 4 of the current plan already proposes exactly this
(Roboflow's "Asian Elephants Dataset", 983 images, and the "Thai Elephant Dataset") independently of
this finding, which is why it belongs in that phase's data work rather than a standalone cleanup
pass here. This finding is the evidence that makes that phase's Elephant-side work necessary, not
optional.

**Follow-up, 27 Aug (same day): the filename filter above is now implemented and validated.**
`edge_impulse_upload_vision.py` gained `filter_out_of_species` (set on the
`elephant-detection-cxnt1-v2` source only) plus a module-level
`AFRICAN_ELEPHANT_FILENAME_MARKERS` tuple and `_is_named_african_elephant()` helper, checked at
parse time before an image's boxes are even read. A full (non-limited) `--dry-run` confirmed it
fires correctly: **33 images dropped as `species_contaminated`**, one below the 34-filename floor
above — one of the 34 filename hits is a zero-box background frame that a different, earlier check
(`zero_area`) already removes first, so it never reaches the species check to be counted twice. Net
effect on the class: Elephant combined total drops from 8,285 (8,035 real + 250 synthetic) to 8,252
(8,002 real + 250 synthetic). No `UNEXPLAINED GAP` was printed and the run's own reconciliation table
closed clean, so the drop is fully accounted for.

Because these 33 images were uploaded to project `1097972` in earlier runs, before this filter
existed, filtering them out of the manifest alone does not remove them from the live project — they
need an explicit delete pass to bring project content back in line with what the manifest now
expects. That delete is a separate, tracked step (see the entry below); this entry is only about the
filter itself being implemented and proven correct locally.

## 27 Aug — train/test category drift from two dataset-composition changes, and how it was fixed

Two changes to the candidate pool this session — the local SHA1 content-dedup fix (71 Boar + 2
Background byte-identical duplicates dropped) and the species filter above (33 Elephant images
dropped) — each shrank the pool that `split_by_group`'s seeded random shuffle draws from. Because
the shuffle order is deterministic but keyed off the *current* set of group keys, removing images
shifts which neighbouring groups land on either side of the train/test boundary. Concretely: files
already uploaded to `1097972` under an earlier, larger candidate pool kept the category they were
assigned then, but the manifest — recomputed fresh on every run — now expects a small number of them
in the opposite category. This is **assignment drift, not data loss**: `reconcile_project_counts`
correctly flagged it as a *net* count mismatch (a live upload run hard-failed with `TOTAL training
expected 10107 actual 10103`, `TOTAL testing expected 2841 actual 2845`), but net-4 undersells the
real churn, which a per-file diff (fetching every live sample's category from
`GET raw-data` and comparing against the manifest's own training/testing lists, matching on filename
with the extension stripped — Edge Impulse's stored `filename` field silently drops it) showed was
**428 individual files** on the first pass (after content-dedup alone) and a further **1,181** on the
second pass (after the species filter was layered on top of that), 0 files missing on either pass.

Fixed both times the same way, via `POST /raw-data/batch/moveSamples` (moves a sample between
categories without touching its content, label, or boxes) chunked at 100 ids per call: 216 to
training / 212 to testing on the first pass, then 591 to training / 590 to testing on the second. A
third diff pass after both rounds of moves confirmed **0 remaining drift, 0 missing** — the live
project's train/test split now matches the current manifest exactly, for every file already present.

**Resolved, 27 Aug (later the same day).** The 33 species-contaminated images were still physically
present at the time the paragraph above was written, and the delete was deliberately deferred pending
explicit human go-ahead. By the time that go-ahead came, the corpus had gone through further
re-upload/dedup passes (the true-negative and pseudo-IR additions among them) and a fresh live query
(`GET raw-data`, filtered to Elephant-labeled samples matching `AFRICAN_ELEPHANT_FILENAME_MARKERS`,
both categories) found **zero** remaining matches against the current project content (10,081
training / 2,834 testing) — the 33 images are already gone, most likely swept up incidentally by one
of those later passes rather than by a targeted delete. Verified against the live API immediately
before this note, not assumed from the earlier count.

## 27 Aug — 3d upload-gap root cause: the 71-image shortfall is real, and now understood

The 71-image gap first noticed in the 26 Aug run (6,489 of 6,560 expected images landing in the old
project, `1094260`, with "0 failures" printed) reappears identically in the from-scratch re-upload
into the new Enterprise project (`1097972`) documented above — same size, same direction. Three
independent checks converge on the same number and the same cause, none of them a guess:

**First, the upload script itself was blind, and that blindness produced two false leads before the
real cause surfaced.** `upload_batch()` discarded the ingestion API's per-file response body entirely
(`resp.read()`, return `None`), so "0 failures" never meant "0 rejections" — it meant "never checked."
Fixing that (`_parse_ingest_response()`) required guessing the response schema, and the first guess —
`{"files": [{"file"/"name", "success", "error"}, ...]}`, modeled on the single-file upload docs, which
say nothing about the shape of a batch response — was wrong. A live one-off probe request (send one
already-known image plus one deliberately-mutated copy, read the raw response verbatim) showed the
real shape is **positional**, one entry per image in request order, with no filename field at all:
`{"success": true, "projectId", "sampleId", "fileName"}` on accept, `{"success": false, "error": "An
item with this hash already exists (ids: ...)"}` on a server-side duplicate reject. Matching on a
nonexistent `"file"`/`"name"` key meant the first live re-upload attempt misclassified all 6,560 files
as "missing from ingestion response" even though most had genuinely landed — fixed by zipping the
response positionally against the batch's send order instead. A second, smaller bug rode along: the
duplicate-vs-real-failure classifier matched the substring `"duplicate"`, which the real rejection text
never contains (it says "already exists") — fixed alongside the first.

**Second, once the response was parsed correctly, a new reconciliation check
(`reconcile_project_counts()`, added this pass) still hard-failed — but on the wrong metric.** It
queried Edge Impulse's `raw-data/count` with a per-class `labels=[...]` filter, which only counts
samples carrying at least one box of that label. Background (zero-box) images are uploaded correctly
with an intentionally empty box list — that is how FOMO learns "no object" — so a class's own
background images are invisible to a query filtered on that class's label. Elephant alone carries 552
such images; querying per-label turned a real 71-image gap into an apparent ~627-image one. Comparing
**total per-category count, no label filter, against the combined expected total across both classes**
removes this blind spot and reproduces exactly 71 (59 training + 12 testing) — confirmed by hand
against the live project before trusting the fixed script.

**Third, the 71 number was independently reproduced offline, with no API call at all.** SHA1-hashing
every file the committed manifest references (both raw bytes and decoded-pixel content) found **zero**
duplicate-content images in the Elephant class, and **exactly 71 duplicate-content pairs in the Boar
class** — the same photo present twice under two different Roboflow export filenames (e.g.
`0c0214597edaa79d_jpg.rf.5d0082cf....jpg` and the same base name with a different `.rf.` hash suffix),
almost certainly an artifact of Roboflow re-exporting overlapping source images across the two Boar
projects (`trackabox/wild-boar-a1flm` and `boarwatch/wild-boar-deterrent-pzq5t`) this dataset merges.
Edge Impulse's `x-disallow-duplicates` correctly collapses each pair into one stored sample — this is
the intended behavior of that flag, not a defect.

**Verdict: the 71-image shortfall is real, structural, fully explained, and confined to Boar (1.1% of
that class, 0% of Elephant).** It is not a network failure, not an account/quota issue, and not a
parsing bug once the two fixes above landed — it is 71 genuinely duplicate photographs in the raw Boar
corpus that Edge Impulse is correctly refusing to store twice. `reconcile_project_counts()` still
hard-fails on this by design (a real gap must be named, not silently passed), and this entry is that
naming. **Not remediated this pass**: replacing the 71 collapsed Boar images with genuinely distinct
ones is small enough in scale (71 of 6,560, all Boar) to fold into Phase 4's existing Boar
domain-match work (SWG Camera Traps pull) rather than justifying a standalone fix — noted there, not
here. Training may proceed against `1097972` with this gap understood and documented; it does not
block Phase 3.

`scripts/edge_impulse_upload_vision.py` changes from this entry: `_parse_ingest_response()` now zips
positionally instead of matching a nonexistent name field; the duplicate classifier in
`upload_dataset()` also matches "already exists"; `reconcile_project_counts()` compares total
per-category counts instead of per-label ones (per-label counts are still printed, informationally,
alongside the total).

## 27 Aug — real per-class held-out scoring implemented; retrained control baseline in 1097972

`report_results()` in `scripts/edge_impulse_train_vision.py` never actually produced a per-class
breakdown for this project type — it only printed Edge Impulse's `classify/all/result` `accuracy`
block, which for object detection collapses everything into one meaningless pseudo-class
(`{"F1 score": {"good": 0, "bad": 0}}`, confirmed live against the control retrain below). The
per-class Elephant/Boar numbers already published in this file (26 Aug and earlier) were computed by
hand, once, outside the script. That gap is now closed: `score_held_out()` pulls the same endpoint's
per-sample `result` (ground truth, boxes in absolute pixels, converted to relative via each sample's
own `imageDimensions`) and `predictions` (model output, boxes already relative, plus Edge Impulse's own
per-sample `f1Score`) lists, groups by each image's own ground-truth label, and derives precision/recall
via **centroid-in-box matching**: a prediction counts as a true positive if its center point lands
inside an unclaimed same-label ground-truth box, predictions consumed highest-score-first. This was
chosen over a strict IoU threshold because FOMO is a centroid detector — the boxes it reports back are
grid-cell-sized proxies for a fired centroid, not a regressed tight box, so IoU (the right tool for a
box-regression detector) measures the wrong thing here.

Ran against the just-finished control retrain — the same FOMO `fomo_mobilenet_v2_a35` config, 100
cycles, retrained from scratch inside the now-populated Enterprise project `1097972` on the corrected
re-upload (6,489 images after the 71-duplicate collapse documented above; 5,059 training / 1,430
testing):

| Class | Test images | Mean per-image F1 | Mean precision | Mean recall | Perfect F1 |
|---|---|---|---|---|---|
| Elephant | 649 | 0.664 | 0.889 (550/649 images predicted) | 0.675 | 309/649 (47.6%) |
| Boar | 709 | 0.675 | 0.805 (609/709 images predicted) | 0.732 | 323/709 (45.6%) |
| Background (FP rate) | 72 | — | — | — | 59/72 clean, FP rate 0.181 |

Compared with the 26 Aug hand-computed numbers (Elephant F1 0.692 / P 0.749 / R 0.693; Boar F1 0.618 /
P 0.629 / R 0.666): F1 is nearly flat for both classes, but **precision rose substantially** (Elephant
+0.140, Boar +0.176) while recall moved in opposite directions (Elephant −0.018, Boar +0.066). This
divergence cannot be cleanly attributed to the project re-upload alone — it is confounded with the
matching-method change (centroid-in-box here vs. whatever method produced the 26 Aug numbers, which is
not preserved anywhere in the codebase to compare against). Reported as-is rather than smoothed over,
per this file's own standing discipline. **Recall is still well short of the ≥92%-per-class bar**
(Elephant 0.675, Boar 0.732) — this is the real starting point Phase 3's architecture/threshold work has
to move from.

The 72 Background test images are **not** a field-realistic negative set — they are the pre-existing
552 stray indoor-scene frames in the Elephant source (casino, classroom, pantry), the only "no object"
signal the corpus carried before Phase 2's true-negative work (SWG Camera Traps empty frames, board
captures) lands. The 0.181 false-positive rate above should not be read as an estimate of real-world
false-alarm behavior on forest/night scenes — it is a baseline against a much easier negative set, and
will very likely get worse (a real finding, not a regression) once Phase 2's proper negatives are
scored.

## 27 Aug — Phase 3 architecture sweep: YOLO-Pro-nano leads, still short of the 92% bar, several real infra findings along the way

Ran against the fully enriched corpus (species filter + SWG true-negative pull + BoarWatch top-up all
landed: 10,081 training / 2,834 testing images, 332 of the testing set genuine background), same
`score_held_out()` centroid-in-box protocol as the entry above. This is a comparison sweep across
candidate architectures, not a single retrain — the numbers below are the first apples-to-apples
comparison this project has ever produced, and the sweep is still in progress (see the open items at
the end); this entry will be extended, not replaced, once it concludes.

| Architecture | Elephant R / P / F1 | Boar R / P / F1 | Background FP rate | Perfect-F1 Elephant / Boar |
|---|---|---|---|---|
| FOMO control (96px, `fomo_mobilenet_v2_a35`) | 0.751 / 0.867 / 0.723 | 0.495 / 0.849 / 0.427 | 0.277 (240/332 clean) | 52.1% / 26.7% |
| **YOLO-Pro-nano, attn_silu** | **0.855 / 0.974 / 0.812** | **0.761 / 0.978 / 0.703** | **0.048 (316/332 clean)** | 48.4% / 33.4% |
| YOLO-Pro-nano, no_attn_relu | 0.812 / 0.982 / 0.768 | 0.711 / 0.978 / 0.651 | 0.057 (313/332 clean) | 46.1% / 24.2% |
| SSD MobileNetV2 FPN-Lite (320px) | pending — see OOM finding below | pending | pending | pending |
| FOMO control (224px) | pending — see crash finding below | pending | pending | pending |

**YOLO-Pro-nano (attn_silu) is the clear leader on every axis at once** — higher recall *and* higher
precision *and* a 5.8× lower false-positive rate than FOMO on the same corpus, not a recall-for-precision
trade. The attention+SiLU variant beats the no-attention+ReLU variant on every metric too, at identical
"nano" sizing. **Neither variant clears the ≥92%-per-class recall bar yet**: attn_silu sits at 0.855
Elephant / 0.761 Boar, a real gap of 6.5-16 points depending on class, before any threshold retuning.
Default confidence threshold (Studio's 0.5) was used for every row above — the threshold sweep (§4 of
the plan) is expected to move recall up at some precision cost, and is the next real lever, not yet
banked into these numbers because of the infra finding below.

### Real infrastructure findings from this pass (not tuned around, named honestly)

- **`ssd_96` (first attempt) failed instantly** — a genuine script bug, not a platform issue.
  `object_ssd_mobilenet_v2_fpnlite_320x320` hard-rejects any input size but exactly 320×320
  ("Your image size is currently set to 96x96 ... MobileNetV2 SSD FPN-Lite 320x320 currently only
  supports a 320x320 input"), and the script defaulted every family's `--image-size` to the same
  96px used for FOMO/YOLO-Pro. Fixed: `--image-size` now defaults per family, forces 320 for `ssd`
  unless explicitly overridden, and rejects any other explicit value for that family.
- **`ssd_320` (the resolution-fixed retry) OOM-killed** (`Application exited with code 137`, 28.3
  minutes into the fine-tuning stage, batch size 32 — SSD's platform default at 320×320) with the
  platform's own message: *"Please contact support if this issue persists or increase train job
  memory in the project dashboard."* Checked the live Edge Impulse OpenAPI spec for an API-reachable
  per-training-job memory override before assuming a dashboard-only fix: the only "memory" field
  anywhere in the spec is `tunerChildJobMemoryMiB`, which sits in the EON Tuner's own trial-config
  schema next to `MOMF`/`disableConstraints`/`tunerSpaceOptions` — a Tuner-child-job setting, not a
  general training-job one, and not applicable to a manually configured run like this. `batchSize`
  *is* a real, settable field on the same training-config body used for learning rate/cycles ("only
  used in visual mode" — exactly this project's mode), so the fix taken is a smaller batch rather
  than a bigger memory grant: `--batch-size` added to `edge_impulse_train_vision.py`, quartered to 8
  for the retry (a one-shot retry given the ~30-minute cost of a second OOM, not a value tuned for
  score). Result pending.
- **`control_224` (224px FOMO) crashed twice on the platform side, a third attempt in progress.**
  First attempt: evicted at ~10% for capacity reasons. Second attempt: a genuine platform crash inside
  Edge Impulse's own `train.py` — `FailedPreconditionError: /home is not a directory` — 56% through
  training after two full hours. Not this project's code: `control_96` on the identical pipeline and
  corpus trained cleanly twice. A third attempt (`control_224b`) is running as of this entry; if it
  also fails, 224px will be recorded as vendor-infra-blocked on this account rather than retried
  indefinitely.
- **Threshold sweep was structurally broken, not slow — root-caused via the live OpenAPI spec, not
  further guessing.** Every `--sweep-thresholds` attempt (3 real attempts, one widened to a 10-minute
  exponential-backoff retry window that still failed 23/23 times with zero variance) left
  `classify/all/result` permanently empty after a threshold change. The spec's own documentation
  explains why: `regenerateModelTestingSummary`'s fast in-place regeneration is explicitly
  unsupported "for object detection models" — exactly this project's type — no matter how long the
  wait. The documented correct call after a threshold change is a real classify job,
  `POST jobs/classify` with `skipFeatureGeneration: true` ("used e.g. if you update thresholds").
  `sweep_thresholds()` rewritten to call that endpoint pair (`set-thresholds` to set the value, then
  a real classify job to re-score) instead of the non-functional regenerate-summary path. Because
  `build_impulse()` deletes and rebuilds the impulse at the start of every stage, `yolo_attn`'s own
  trained model was already gone by the time this fix landed (the next stage's build had already run)
  — its threshold numbers require a full retrain (`yolo_attn2`), queued because attn_silu is the
  sweep's best result so far and its threshold numbers are worth the retrain cost.

### Still open at the time of this entry

`control_224b` (third 224px attempt), `ssd_320_b8` (OOM retry at batch 8), and the threshold sweeps
for all three (`control_224b_thr`, `ssd_320_b8_thr`, `yolo_attn2_thr`) are queued or running. EON
Tuner's full custom search (`/optimize/*`, confirmed reachable in Phase 0, never yet actually run) is
the next escalation if the manual sweep plus threshold tuning does not close the remaining gap to 92%
recall per class. This entry will be extended with final numbers, the threshold-tuned comparison, and
an explicit per-class ≥92% verdict once the sweep concludes.

## 28 Aug — incident recovery: two real losses named, sweep resumed clean

A collision between two concurrently-reconfiguring stages on the shared learn block (both stages
reconfigure the same "Impulse #1" in place, and one stage's `sweep_followup.sh` timeout was shorter
than a real training run) forced a kill-and-resume; `edge_impulse_train_vision.py`'s `JOB_TIMEOUT_S`
raised 7200 → 21600 to prevent a recurrence. Resuming from confirmed-real server-side state (not
assumption) surfaced two real, permanent losses worth naming plainly rather than smoothing over:

- **`control_224` (224px FOMO) is vendor-infra-blocked, not retried again.** Two independent attempts
  both crashed with the identical Edge Impulse platform error, `FailedPreconditionError: /home is not
  a directory` — the first the second attempt in the 27 Aug entry above, the second (`control_224b`)
  killed mid-run by the same incident this section documents. Two independent failures with the
  identical vendor-side error is this project's own pre-agreed threshold for calling a config
  vendor-infra-blocked rather than retrying indefinitely. 224px stays untested on this account.
- **`ssd_320_b8`'s own evaluation results are permanently gone, even though its training genuinely
  succeeded.** Confirmed directly: `GET jobs/53201510/status` shows `finishedSuccessful: true` — the
  batch-8 retry actually finished cleanly, 27 Aug 19:43–20:15 UTC. But the killed `yolo_attn2` attempt
  that caused the incident had already progressed far enough to reconfigure the impulse's DSP block
  (recorded at the time as "confirmed it never got past DSP feature regen before being killed") before
  it died — which silently orphaned the DSP block `ssd_320_b8` was trained against. Confirmed two ways
  post-recovery: `ssd_320_b8_thr`'s classify job failed outright (`Failed to load metadata for DSP ID
  2`), and a direct `GET classify/all/result` for even the untuned default-threshold numbers returns
  `"No model testing results found, run 'startClassifyJob' first"` — the training artifact exists, but
  every path to a held-out score for it is gone. **Not retried**: `ssd_320` was already the weakest
  performer of the sweep before this (still `pending` in the comparison table above after two prior
  attempts failed on OOM/input-size grounds), and burning another ~30+ minute training slot to
  re-produce a number for an architecture that was not leading on any axis is not worth the time this
  close to the 2 Sept trial. Recorded as a real, permanent gap in the architecture comparison table —
  SSD MobileNetV2 FPN-Lite stays unscored on this project, not "pending", and should not be re-attempted
  without a specific reason to reconsider it.

The recovery chain resumed sequentially and correctly from there: `yolo_attn2` (a clean retrain, not a
reconfigure-on-top-of-a-live-job), its own threshold sweep, a Tuner-target reconfigure, and the EON
Tuner's full custom search. All four stages ran; results below.

**`yolo_attn2` clean retrain — default threshold**: Boar 1,239 test images, F1 0.538 / precision 0.975 /
recall 0.586; Elephant 1,663 test images, F1 0.790 / precision 0.977 / recall 0.835; Background 332 test
images, 95.5% clean (FP rate 0.045). Both classes' precision is very high and recall comparatively low
at the default 0.5 threshold — exactly the profile a lower confidence threshold should correct for a
recall-first mission (§4 of the plan).

**Threshold sweep, `{0.05, 0.1, 0.2, 0.3, 0.5}`** — per-class recall rises monotonically as threshold
drops, at the cost of Background false-positive rate:

| threshold | Boar recall | Boar precision | Elephant recall | Elephant precision | Background FP rate |
|---|---|---|---|---|---|
| 0.05 | 0.760 | 0.752 | 0.914 | 0.881 | 0.380 |
| 0.1  | 0.719 | 0.823 | 0.904 | 0.917 | 0.130 |
| 0.2  | 0.677 | 0.889 | 0.887 | 0.944 | 0.130 |
| 0.3  | 0.650 | 0.924 | 0.873 | 0.956 | 0.093 |
| 0.5  | 0.586 | 0.975 | 0.835 | 0.977 | 0.045 |

Best point in this sweep, threshold 0.05: **Elephant recall 0.914, Boar recall 0.760 — Elephant is
close to the 92% bar for the first time, Boar remains well short, and a 38% false-positive rate on
empty scenes at that threshold is too costly to deploy as-is.** This is the strongest single number
this project has produced so far but does not meet the bar on either axis at a threshold worth
shipping. Recorded honestly rather than picking a threshold that makes one number look better than the
tradeoff actually is.

**EON Tuner run — failed with a real, understood API bug, not chased further this pass.**
`yolo_pro_reconfigure` (the stage immediately before it) explicitly rebuilt the impulse and configured
its learn block as `yolo-pro-nano-attn_silu` (org model 6493) via `--configure-only`, logging "impulse
built and learn block configured, no training job started." Seconds later, `POST
/1097972/optimize/config` with `searchSpaceTemplate: object_detection_yolo_pro` rejected with `YOLO-Pro
block not found` — retried once with the default `accuracy` objective (ruling out the recall-objective
question flagged as open in Phase 0) and failed identically. The Tuner's block-lookup evidently does not
see a learn block set up via `--configure-only` the way it sees one from an actual completed training
job — a real mismatch between "impulse configured" and "impulse the Tuner API can search around," not a
transient error (both attempts failed the same way within the same two-second window). Not investigated
further this pass: the Tuner was always the exploratory half of Phase 3 (find something better than the
already-working candidates), not the source of the current best result, and burning more time on it
this close to the trial is not worth it when the more promising lever — the SWG Boar/background
expansion already in flight (see "28 Aug — bounding-box quality audit" and HANDOVER.md) — is a direct,
better-understood shot at closing exactly the gap (Boar recall) that most needs closing. Tracked as an
open bug in `scripts/edge_impulse_tuner_vision.py`'s `--configure-only` path, not re-attempted blind.

## 28 Aug — bounding-box quality audit

Direct response to an explicit ask: verify how accurate the stored annotations actually are, not just
how many images exist. Built `bbox_qa.py` (session scratchpad, not committed — a throwaway visual-QA
tool, not project infrastructure) to draw each source's real stored COCO boxes onto the real images and
assemble contact sheets for direct inspection, same discipline as every other finding in this file:
verify by looking, don't infer from metadata or a dataset's own name/description. Sampled every source
currently uploaded into project 1097972 (`wcs-elephas-maximus`, `swg-eurasian-wild-pig`, and the five
Roboflow-sourced sets), 9–14 images each, then widened to 30 for the two sources the first pass flagged
as concerning. Findings, most consequential first:

- **`thai-elephant-dataset-v6` — dropped entirely, real species contamination, no cheap fix
  available.** This source was added on 27–28 Aug specifically as the "species-correct" structural fix
  for `elephant-detection-cxnt1-v2`'s known African-elephant contamination (see that source's own
  finding below). A 30-image visual audit found the opposite: roughly half the sample is unmistakably
  African bush elephant — fan ears reaching past the shoulder, concave/sway back, dry savanna habitat,
  one frame literally captioned in-image `ELEFANTE AFRICANO`. This is the same species mismatch problem
  it was supposed to solve, at a higher observed rate than the 17% found in `elephant-detection-cxnt1-v2`
  itself. Unlike that source, `thai-elephant-dataset-v6`'s filenames are opaque Roboflow-generated IDs
  (`2902_jpg.rf.8ce97dca...`) carrying no species text at all, so the filename-marker floor-filter that
  partly mitigates `elephant-detection-cxnt1-v2` cannot touch any of this one's contamination — the only
  fix would be a full per-image visual reclassification of ~2,400 images, not worth the time this close
  to the 2 Sept trial for a supplement whose intended purpose is already better served by
  `wcs-elephas-maximus` (real, species-verified by construction) and `asian-elephants-dataset-v1`
  (verified clean on its own audit sample, see below). **Removed from `DATASETS` in
  `edge_impulse_upload_vision.py`**; the already-uploaded 2,397 images are removed from project 1097972
  by the new `scripts/cleanup_thai_elephant_vision.py` (matches by sha256 content hash, since Edge
  Impulse renames every file to an internal UUID on ingestion and does not expose the original filename
  back — a plain filename-based delete is not possible). Deliberately **not run automatically**: it
  touches live project data mid-architecture-sweep, and deleting now would make the sweep's own
  candidates inconsistent with each other (some trained against the contaminated data, later ones
  against the cleaned data) — the same confound this file's Phase 3 methodology already guards against
  for the control retrain. Held until the in-flight `recover.sh` chain (`yolo_attn2` → its threshold
  sweep → the Tuner reconfigure → the EON Tuner search) finishes, then run once, followed by one final
  clean retrain of whichever architecture wins the sweep — both numbers (contaminated-data vs
  cleaned-data) will be reported here, not just the cleaner one.
- **`elephant-detection-cxnt1-v2` — two new problems beyond the already-documented species
  contamination.** This source already carries a `filter_out_of_species` filename-marker filter (catches
  34/3,280 by explicit country/park name, a documented floor — see that entry's own comment). The wider
  30-image audit surfaced two problems that filter does not address at all: **(1) real mislabeled
  content** — one sampled frame boxes a person walking a forest path, not an elephant, and two more are
  TV news screenshots (a studio anchor shot, a broadcast graphic over a distant grass field) with a
  broadcaster's on-screen furniture boxed as "Elephant". **(2) severe near-duplicate concentration** — 15
  of the 30 sampled frames (half) are the same viral video of an elephant reaching into a stopped truck
  on a road, sampled at different timestamps. That video being real and relevant is not the issue; a
  dataset that is effectively one repeated scene at this density inflates apparent volume without adding
  distinct training signal, and risks a train/test split putting near-identical frames on both sides if
  the split isn't grouping on it (`scripts/edge_impulse_upload_vision.py`'s `group_key()` machinery
  exists precisely for this pattern on the Boar side — worth confirming it's actually collapsing this
  video's frames the same way before trusting this source's contribution to any held-out number). **Not
  dropped** — it is the foundational 3,280-image set every architecture in the sweep has already trained
  on, already carries partial species filtering, and the WCS + Asian-elephant supplements now provide
  real species-correct volume alongside it regardless. Flagged here as an open finding, not acted on
  this pass: worth a real dedup pass in a future iteration, not a same-day fix five days out from the
  trial.
- **`asian-elephants-dataset-v1` — audited clean.** 9-image sample: real, mostly IR/night camera-trap
  frames of identifiable Asian elephants (twin-domed forehead, small ears), boxes well-fitted where the
  animal is visible. One recurring annotation-quality quirk: several frames carry multiple heavily
  overlapping boxes around the same animal (apparent duplicate/over-segmented annotations, not multiple
  animals) rather than one clean box — cosmetic rather than a species or mislabeling problem, and FOMO's
  centroid-matching scoring is largely insensitive to it, but worth knowing if a future box-regression
  architecture (real IoU-based, not centroid) is ever tried against this source.
- **`wild-boar-a1flm-v1` and `wild-boar-deterrent-pzq5t-v1` — lower-severity domain contamination,
  not acted on.** 9-image samples each found one clearly wrong image per source: a domestic farm pig
  (pink, in a straw-lined pen with piglets) boxed as "Boar" in `wild-boar-a1flm-v1`, and a vegan-food
  advertisement graphic ("Save the Planet, One Bite at a Time") with an inset pig-snout photo boxed as
  "Boar" in `wild-boar-deterrent-pzq5t-v1`. At n=9 each this is an approximate ~11% sample rate, not a
  measured population rate, and both sources are large (1,901 and 6,211 train images respectively) — a
  full audit was out of scope this pass. Not dropped: `swg-eurasian-wild-pig` is already the
  domain-correct primary Boar source, these two are secondary volume/diversity supplements, and a
  domestic pig or an ad photo is a much smaller morphological/semantic miss than an entire wrong
  elephant species. Recorded as a real, open, lower-priority gap rather than silently accepted.
- **`swg-eurasian-wild-pig` — ambiguous at thumbnail resolution, not conclusively a defect.** Several
  sampled frames show boxes over scenes where no animal is clearly identifiable at the 360px thumbnail
  size used for the contact sheet — could be genuine camouflage/distance/motion-blur (expected and
  common in real camera-trap corpora, this is exactly the domain-correct source and its difficulty is
  part of its value) or could be a small number of genuinely bad annotations; the two are not
  distinguishable without full-resolution inspection, which this pass did not do. One frame in the
  original 14-sample sheet is a strong candidate for a real defect (a box over what reads as
  unidentifiable fog with no discernible animal shape at any resolution), flagged but not removed —
  removing individual images from a >2,000-image source on a single ambiguous case is not warranted.
- **`wcs-elephas-maximus`** (the 194-image real Asian-elephant addition from 28 Aug, see above) — 14-image
  sample: real camera-trap imagery, boxes accurate where the animal is identifiable. Several frames are
  extreme close-up leg/torso crops (a different capture geometry from a typical mounted field camera —
  the source cameras were evidently mounted very close to game trails) and one frame is severely
  motion-blurred; both are genuine camera-trap artifacts, not annotation errors, and are left in since
  motion-blurred/partial-view night detections are a realistic condition this model needs to handle in
  the field, not an edge case to filter out.

**Net effect on the dataset**: `thai-elephant-dataset-v6` (2,397 images) is being removed once the
current sweep completes; every other source stays, with the `elephant-detection-cxnt1-v2` duplication
finding and the two lower-severity Boar findings carried forward as open items rather than resolved. The
architecture-comparison numbers already recorded above in this file were all measured with
`thai-elephant-dataset-v6` still present — this is a known, named caveat on every number until the
post-cleanup retrain lands.

## 28 Aug — reconciliation hard-fail investigated: query bug + a stale single-run assumption, not data loss

The WCS elephant upload run (194 images, see above) finished with the project-level reconciliation
guard added in the 3d fix (see "27 Aug — 3d upload-gap root cause") reporting a **HARD FAIL**:

```
Background training  expected   515  actual     0
Background testing   expected   139  actual     0
Boar       training  expected  4103  actual  4374
Boar       testing   expected  1156  actual  1239
Elephant   training  expected  6590  actual  6102
Elephant   testing   expected  1856  actual  1663
TOTAL      training  expected 11208  actual 11483  <-- MISMATCH
TOTAL      testing   expected  3151  actual  3234  <-- MISMATCH
```

This guard exists specifically to catch silent data loss, so it was treated as a real signal and
investigated directly rather than assumed benign — same discipline as the bounding-box audit above.
Ruled out a concurrent-writer race first (`fetch_swg_camera_traps.py`, pid 4369, was running throughout
this upload's execution window, but confirmed by reading its source that it only downloads to local
disk and never itself uploads to Edge Impulse). Then queried the project's live `raw-data/count`
directly, independent of this run's own numbers:

```
training Elephant   6102   training Boar   4374   training Background   0   training TOTAL 11483
testing  Elephant   1663   testing  Boar   1239   testing  Background   0   testing  TOTAL  3234
```

**These match the run's own "actual" column exactly.** So the "actual" side was never wrong — this
is the project's real, current, live state, not a stale snapshot. That reframes the question: not
"is data missing", but "why is `expected` wrong."

Two separate causes, both benign:

- **`Background actual=0` is a query bug in the reconciliation check, not missing data.** Pulled a raw
  page of training samples and inspected the literal `label` field: alongside `Boar` and `Elephant`
  values, ~10% of samples carry the literal label `"-"` — Edge Impulse's own representation for a
  sample with no bounding boxes (i.e. the `swg-empty` / `board-captures-day1` negatives). The
  reconciliation's `raw-data/count?labels=["Background"]` query asks for a label string that does not
  exist in the project's data — "Background" is our own name for the negative-image class, never a
  literal label written to any sample. Full-project total (11,483 training) minus Elephant (6,102) minus
  Boar (4,374) leaves 1,007 real training samples that are neither — consistent with the negatives
  actually being present, just not reachable through that filter. That 1,007 (plus 332 testing) is
  itself *more* than the 515/139 expected, not less, which rules out data loss on this class outright.
- **The real cause of both the Boar surplus and the Elephant deficit: `expected` is computed as
  this-run's-own-freshly-parsed-count, but `actual` is the project's cumulative total across every
  upload run in the session.** The reconciliation guard was written under the Phase 1 assumption of a
  single full upload into an empty project (1097972 was empty at the start of this pass — see Phase 0
  above); it was never updated for the reality that this session ran several separate, smaller upload
  passes into the same project (the original full re-upload, the SWG top-up, this WCS-specific run).
  Each run recomputes `expected` from only its own parse of the `DATASETS` list, so a run that adds one
  small new source will always show a mismatch against the project's true cumulative total unless it
  happens to re-parse and re-count every image ever uploaded by every prior run identically. Boar's
  surplus (+271 train / +83 test) and the real negative-image surplus (+492 train / +193 test) are both
  consistent with this: earlier runs already pushed more Boar and negative data than this run's own
  parse alone accounts for. Elephant's deficit is the mirror case — this run's `expected` summed fresh
  parses of all Elephant sources including ones with content already live from earlier runs, and an
  unknown fraction of those were rejected server-side as exact-content duplicates (the run's own log
  recorded 192 such server-side rejections this run, on top of the local content-hash dedup that already
  ran before upload) without being subtracted from `expected` — the same class of gap the 3d fix
  addressed for local ledger duplicates, still present for this specific expected-vs-actual comparison
  path.

**Conclusion: no data was lost.** The WCS elephant addition uploaded cleanly (194/194, 0 duplicates,
confirmed in the per-source table). The live project holds real, present, queryable data for both
classes in the counts shown above, and `yolo_attn2`'s in-progress training run is reading a valid
project state. The reconciliation check did exactly its job — surfaced an unexplained mismatch that
was worth stopping and checking by hand rather than clicking past — it just also revealed that its own
"single full run" assumption no longer matches how the project is actually being used, and that its
Background-label query needs to target the real `"-"` no-box representation rather than a name of our
own invention. Not fixed in code this pass (lower priority than the in-flight architecture sweep and
the 2 Sept trial timeline); tracked as a known gap in `scripts/edge_impulse_upload_vision.py`'s
reconciliation function rather than re-run blind next time.

## 28 Aug — SWG background top-up landed (656 → 2,424 real negatives) and pseudo-IR synthetic supplement confirmed live

Two Phase 4 items that were in flight closed out this pass; recorded together since both changed the
project's negative/IR composition and both showed up in the same upload run's reconciliation table.

**SWG Camera Traps background expansion.** `fetch_swg_camera_traps.py` widened its per-period draw
from 300 to 1,200 (real forest camera-trap empty frames, day and IR-night, CDLA-Permissive licensed),
strict-prefix-resuming from the existing 300-seeded pull so nothing already-uploaded was re-fetched.
The follow-up upload run (`edge_impulse_upload_vision.py`) landed all 2,398 new `swg-empty` images
clean — 0 server-side duplicates — bringing the project's real Background/negative total from 656
(630 `swg-empty` + 26 `board-captures-day1`) to **2,424**. This is the true-negative expansion Phase 2
called for and the lever the `28 Aug — incident recovery` entry above named as the next promising step
after `yolo_attn2`'s threshold sweep showed an unusable 38% false-positive rate on the old, much
smaller 656-image negative set at the recall-favorable end of the sweep.

**Pseudo-IR synthetic supplement.** `scripts/make_pseudo_ir_vision.py` (CANDAR 2023 recipe: weighted-
RGB grayscale → mild gamma correction → a synthetic radial illumination-falloff mask approximating a
lens-mounted IR emitter) generated 250 Elephant + 250 Boar images from cached real daytime source
frames, geometry (bounding boxes) copied verbatim from source, pixel/color only transform. Source
images were drawn only from the Roboflow-cached exports, deliberately excluding the SWG pull and board
captures since those already carry real IR and re-applying a fake-IR transform to a real-IR frame
would be noise, not signal. Both classes are uploaded and confirmed live via this run's own
reconciliation table, correctly tagged `[SYNTHETIC]` and never folded into a real-data count:

```
Elephant           pseudo-ir-elephant     250     250     250       0     195      55         0       0  [SYNTHETIC]
Boar                   pseudo-ir-boar     250     250     250       0     195      55         0       0  [SYNTHETIC]
```

Per this repo's standing discipline (and the plan's explicit instruction), every table and count that
reports on Elephant/Boar totals from here on must keep the synthetic 250+250 broken out, not blended
into the real-image figures above.

**This same upload run also hard-failed its project-level reconciliation guard**, for the same reason
already root-caused in the entry directly above (`28 Aug — reconciliation hard-fail investigated`):
`expected` is this-run's-own fresh parse (Background 2,424, matching exactly what landed), `actual` is
the project's live cumulative total, which is higher for the same two already-documented reasons —
the Background-label query bug (`actual=0` printed, but the 2,398 samples are genuinely present, just
unreachable through a `labels=["Background"]` filter that doesn't match Edge Impulse's real `"-"`
no-box label) and the running Elephant/Boar surplus from `thai-elephant-dataset-v6` still being live in
the project (not yet deleted — see below). No new investigation was needed; this run's numbers are
fully consistent with the already-understood pattern, confirmed by checking that this run's `actual`
TOTAL (13,354 train / 3,761 test) exceeds the prior WCS run's `actual` TOTAL (11,483 / 3,234, see
above) by exactly 2,398 — precisely the new Background upload, and nothing else. No data lost.

**`thai-elephant-dataset-v6` cleanup is still pending, and now blocking.** `scripts/
cleanup_thai_elephant_vision.py` (content-hash-matched deletion of the ~half-African-elephant-
contaminated source flagged in the 27 Aug species audit above) was written and is ready to run, but a
non-interactive launch attempt was declined by the local tooling's own safety gate — a bulk DELETE
against 2,397 samples on paid Enterprise infrastructure is the kind of hard-to-reverse action that
correctly needs a human to actually press go, not something to route around. It has not been run.
**Every Elephant-class number in this file up to and including tonight's runs, including the
`retrain_bg_expanded` run below if present, was measured with this contamination still present.**
Running the cleanup script by hand and doing one more clean retrain is the next concrete step once a
human is back at the keyboard.

**Retrain on the expanded negative set — the false-positive problem is real but only partly fixed.**
Retrained `yolo-pro-nano-attn_silu` from scratch (job 53203235, 38.2 min) against the now
background-expanded project (still thai-elephant-contaminated — the cleanup above is what's pending)
specifically to test whether the 656 → 2,424 real-negative expansion lets the model hold a lower,
still-usable confidence threshold. At Studio's default threshold the class numbers barely moved from
`yolo_attn2` (Boar F1 0.539/P 0.986/R 0.584, Elephant F1 0.791/P 0.986/R 0.834 — both within noise of
before), but Background false-positive rate at default threshold improved 0.045 → 0.020, a first
signal the bigger negative set was doing something. The full sweep confirms it, directly against
`yolo_attn2`'s own sweep table above:

| threshold | Boar recall | Boar precision | Elephant recall | Elephant precision | Background FP rate |
|---|---|---|---|---|---|
| 0.05 (bg-expanded) | 0.764 | 0.845 | **0.918** | 0.901 | **0.179** (was 0.38) |
| 0.05 (yolo_attn2, 656-neg) | 0.760 | — | 0.914 | — | 0.380 |
| 0.1 | 0.735 | 0.891 | 0.907 | 0.933 | 0.116 |
| 0.2 | 0.691 | 0.938 | 0.892 | 0.956 | 0.064 |
| 0.3 | 0.661 | 0.964 | 0.874 | 0.972 | 0.037 |
| 0.5 | 0.584 | 0.986 | 0.834 | 0.986 | 0.020 |

**The hypothesis was right, and it matters: at the same threshold 0.05 operating point, recall held
essentially flat (Boar 0.760→0.764, Elephant 0.914→0.918) while the false-positive rate on empty
scenes roughly halved (38.0%→17.9%).** That is a real, structural improvement from more true-negative
data, not a training-run fluke — it is exactly the mechanism Phase 2 predicted: a model trained
against a small negative set overfits to that set's specific empty-scene appearance and fires on
anything unfamiliar, and a 4x larger, more varied real negative set gives it more to generalize from.

**It is still short of deployable, and specifically short on Boar, not on the threshold choice.**
Elephant recall at threshold 0.05 (0.918) is essentially at the 92% bar — within measurement noise of
it — but Boar recall tops out at 0.764 across the entire sweep and does not meaningfully climb as the
threshold drops further (0.671→0.691→0.735→0.764 from 0.3→0.2→0.1→0.05, a shrinking gain per step,
suggesting the model is running out of Boar detections to find at any threshold, not being held back
by threshold alone). That points at a Boar data/capacity problem — likely still the pseudo-IR/night
domain gap and the still-unaddressed `elephant-detection-cxnt1-v2` duplicate-frame and Boar-Roboflow
contamination findings flagged as open above — rather than something a lower threshold alone will fix.
17.9% false-positive rate at the best-recall point is also still too costly to deploy as-is on its own,
though it is now in a range where the already-flagged N≥2 consecutive-frame temporal-aggregation
fusion-layer lever (named in Phase 7 of the plan, not implemented here) could plausibly bring it down
further without giving back recall — worth prioritizing as the next lever over further vision-only
threshold tuning.

**Caveat carried forward: every number above still includes the thai-elephant contamination.** The
Elephant recall figure in particular (0.918, right at the bar) should be read as provisional until the
cleanup runs and a clean retrain reproduces or revises it — a contaminated class being this close to
the bar is exactly the situation where re-measuring clean matters most, in either direction.

## 28 Aug — widened Boar bounding-box audit: the "lower-severity" contamination finding was an underestimate, and it plausibly explains the Boar recall ceiling

`yolo_bgexp`'s threshold sweep (above) showed Boar recall plateauing at 0.764 across the entire sweep —
unlike Elephant, it does not keep climbing as the threshold drops, which reads as a data ceiling rather
than a threshold problem. Direct response: widen the two sources the first bbox audit flagged as
"lower-severity, one bad image each, not worth a full audit" from n=9 to n=40 each, and re-sample
`swg-eurasian-wild-pig` (the domain-correct primary Boar source) with tight, padded, full-resolution
crops around each box instead of a 360px whole-frame thumbnail, to actually answer the "ambiguous at
thumbnail resolution" open question from the first pass. Script: `bbox_qa_boar.py` (session scratchpad,
same throwaway-tool discipline as `bbox_qa.py`). Findings:

- **`wild-boar-a1flm-v1` (n=40): at least 5–6 clear contamination hits, not the single domestic pig
  previously recorded.** Beyond the original farm-pig-in-a-pen finding: a second, distinctly domestic
  black pig standing in a bare dirt yard; a pale pink pig lying in sand with none of wild boar's
  bristled coat; a cluster of solid-pink piglets (wild boar piglets are striped tan/brown, not pink);
  the well-known "swimming pigs of Exuma" tourist photo (two pale domestic pigs standing in shallow
  turquoise water — unmistakable, high-confidence hit); and a warthog (distinctive facial warts,
  upright mane, grey hide) — a real species, but the wrong one, native to Africa and morphologically
  and behaviorally distinct from Kerala's *Sus scrofa*. Several more (a large-eared animal near a
  porch, a woolly cream-colored quadruped, two frames with deer-like slender-legged silhouettes) are
  lower-confidence but worth a second look. **At n=40 this reads as roughly 12–15% likely-contaminated
  at high confidence, more once the ambiguous cases are counted** — a materially higher rate than the
  ~11%-of-9 single-domestic-pig finding the first pass recorded.
- **`wild-boar-deterrent-pzq5t-v1` (n=40): a different and arguably worse failure mode — black
  redaction boxes with no visible content underneath, plus more wrong-species/captive-setting hits.**
  Several sampled frames carry solid black rectangles (privacy/watermark redaction from the original
  source) that the stored "Boar" bounding box sits directly on or overlaps — meaning the box has no
  visible animal to learn from at all, not an identification-ambiguity case but a structurally empty
  label. Separately: an indoor barn/pen scene with a person standing in frame next to captive pigs; a
  courtyard scene with a domestic black pig next to a person; a close-up through wire mesh (a fenced,
  captive animal); a bizarre outlier frame that reads as a toy/model claw, boxed "Boar"; two frames
  with slender, long-legged, deer-like silhouettes; and one frame with two golden furred animals in a
  sitting posture that read as primates, not boar. **This source looks like the more contaminated of
  the two**, and unlike `wild-boar-a1flm-v1` some of its problems (the redaction boxes) are a
  structural labeling defect, not just a wrong-species judgment call.
- **`swg-eurasian-wild-pig` tight crops (n=30, full resolution): the ambiguity is real, not a thumbnail
  artifact.** Roughly 8–9 of 30 crops (~27–30%) show no confidently identifiable animal even at full
  resolution and padded-tight framing — some are plausibly genuine camera-trap difficulty (dense fog,
  near-total darkness, heavy motion blur, an animal mostly occluded by foliage, all realistic and
  expected in this domain), but several (a box over what reads as an empty foggy background with no
  discernible shape at any resolution, a few boxes on bare ground/leaf litter with nothing identifiable
  in or near them) read more like placement defects than difficulty. Resolving "which is which" would
  need either an expert reviewer or per-image provenance/metadata this pass doesn't have access to.
  Unlike the two Roboflow sources above, this is still the single best domain-matched Boar source
  available (real Kerala-relevant *Sus scrofa* camera-trap imagery, day and IR-night) — the finding is
  a real caveat on its label quality, not a reason to drop it.

**This plausibly explains, at least in part, why Boar recall plateaus below the 92% bar while Elephant
keeps climbing as threshold drops: a meaningful fraction of the Boar training signal, across all three
of its real sources, is noisy — wrong species, captive/domestic rather than wild, structurally empty
redacted boxes, or genuinely unidentifiable content — in a way Elephant's sources (species-audited
above, `wcs-elephas-maximus` and `asian-elephants-dataset-v1` both came back clean) mostly are not.**
This is a real, now-quantified finding, not acted on this pass: a defensible per-image relabel of two
sources totaling ~9,200 real images (1,901 + 1,308 boxed, before the 8,857-parsed/1,308-boxed filter
already in place on the second one) is a multi-day task this close to the 2 Sept trial, and unlike
`thai-elephant-dataset-v6` there is no cheap mechanical marker (content hash, filename pattern) that
separates the contaminated images from the clean ones — every hit above was found by looking, one at a
time. Recorded here as the clearest concrete next lever for the Boar class specifically, ahead of any
further architecture or threshold tuning, for whoever picks this up next.

### Checked whether the redaction-box defect specifically is mechanically filterable — it is not, and it is not the driver anyway

The one defect above that looked objectively checkable, rather than a subjective species call, was the
black redaction rectangles in `wild-boar-deterrent-pzq5t-v1`: unlike "is this a domestic pig", "is this
box a near-uniform near-black region" is a plain pixel-statistics test. Wrote a scan
(`detect_redacted_boar_boxes.py`, scratchpad, read-only, not committed) that crops every stored box in
both `wild-boar-deterrent-pzq5t-v1` and `wild-boar-a1flm-v1`, converts to grayscale, and flags boxes
whose interior std-dev and mean brightness both fall below a threshold — mirroring the existing
`filter_out_of_species`/`_is_named_african_elephant` per-image filter pattern in
`edge_impulse_upload_vision.py`, but pixel-based rather than filename-based since redaction boxes carry
no filename signature.

- **Conservative threshold (std<6, mean<18): 2 of 9,751 deterrent boxes flagged, 0 of 3,003 a1flm
  boxes.** Relaxed threshold (std<15, mean<35): 10 and 2 respectively — **12 of 12,754 boxes total
  (~0.09%)**, even generously counting every flagged box as a real defect.
- **Spot-checked all 9 unique flagged images at full resolution and drew their stored boxes
  (`verify_redacted_flags.py`, `bbox_qa/redaction_flag_verify.jpg`) — only 3 of 9 are genuine redaction
  artifacts** (aerial IR/thermal farmland frames carrying real black watermark squares over ambiguous or
  empty ground, no identifiable animal in the boxed region). **The other 6 are legitimate dark
  night/IR boar photos** — real animals, correctly boxed, just naturally low-brightness/low-variance
  because they are genuine low-light camera-trap or thermal captures, not redactions. The pixel-stats
  test cannot tell the two apart, because a real dark IR boar silhouette and a real black redaction
  square have the same brightness/variance signature.
- **Conclusion: this filter is both unreliable (≥60% false-positive rate on its own flags, confirmed by
  eye) and immaterial in scale (≤0.1% of boxes even at its most generous setting) — not worth wiring
  into `DATASETS`.** It also confirms, from a different angle, the finding just above: the redaction-box
  defect is real but small; the actual contamination budget is dominated by the subjective
  wrong-species/captive-vs-wild calls, which remain not mechanically filterable by any means tried so
  far. This closes out the "is there a cheap partial fix" question raised above — there is not, for
  either flavor of the Boar contamination — and confirms the only real lever left for Boar recall is the
  multi-day manual relabel already named, out of scope before 2 Sept.

## 28 Aug — on-device benchmarking: real CPU latency measured on the UNO Q, GPU delegate blocked by a missing runtime library

Exported `yolo_bgexp` (job 53203235, INT8 quantized) from project `1097972`'s primary impulse via
`edge-impulse-linux-runner --api-key ... --quantized --download`, non-interactively over SSH to the
board at `192.168.1.10` — confirmed by cross-checking the export's job timestamps against the training
job list (`GET /jobs/all`) rather than assumed, since the impulse's shared 96×96 input size initially
looked like it might be the old FOMO config rather than YOLO-Pro; it is not, that resolution was simply
never changed off the impulse default for either architecture in this project.

**CPU target (`arduino-uno-q`, `format: arduino-uno-q`) — real, measured, functionally verified:**

- **~33.8 ms/inference average, ~29.6 FPS** (99 frames, first 5 dropped as warm-up; range 19–43 ms) —
  measured via `edge-impulse-linux-runner --fake-camera <file>` against a real board-captured frame
  (`board-captures-day1/burst_00.jpg`), which exercises the identical decode→resize→infer path a live
  camera stream would, just without gstreamer's V4L2 capture step (see below for why that step itself
  isn't available on this board right now).
- **Functional correctness confirmed on real content, not just latency**: fed a real, boxed
  `swg-eurasian-wild-pig` frame through the same CPU `.eim` and it correctly fired
  `{"label":"Boar","value":0.509,...}` at a plausible box location. The ~0.51 confidence is consistent
  with everything already documented above about Boar needing a low deployed threshold (0.05–0.1, not
  Studio's 0.5 default) to hit usable recall — this is the same signal showing up end-to-end on the
  actual board, not just in Studio's held-out evaluation.
- **RAM**: board baseline (`free -h`) shows 3.6 GiB total / ~3.0 GiB available at idle; the `.eim` itself
  is 16.4 MB. Not a per-process RSS measurement (a `ps` capture during a short-lived run raced the
  process and came back empty — not worth a second attempt for a number this unlikely to matter, given
  the model is two orders of magnitude smaller than available RAM), but the headroom is unambiguous.

**GPU delegate target (`runner-linux-aarch64-gpu`, BETA in Studio) — exports cleanly, cannot run on this
board's current software image:**

- The export itself succeeds: Studio builds and links the binary against `-ltensorflowlite_gpu_delegate`
  without error (14.9 MB `.eim`, confirmed downloaded).
- **Running it fails**: `error while loading shared libraries: libtensorflowlite_gpu_delegate.so: cannot
  open shared object file`. Searched the entire board filesystem (`find / -iname
  'libtensorflowlite_gpu_delegate*'`) — zero hits. Also checked inside Arduino's own official
  `ghcr.io/arduino/app-bricks/ei-models-runner:0.12.1` container image (the one App Lab itself would use
  to run a model) — also zero hits, and that container isn't even given `/dev/dri` GPU device access by
  default. **This is a genuine gap in the board's current OS/App Lab software stack, not a
  configuration mistake on this pass's part**: the Adreno 702 GPU-delegate runtime library simply isn't
  installed anywhere reachable, on the host or in Arduino's own model-runner image, as of 28 Aug 2026.
  Confirms and sharpens the plan's original BETA caveat — it isn't just an early-access label in Studio,
  the runtime support genuinely isn't present yet on this hardware/software combination. Left
  unresolved: installing it would need a proprietary Qualcomm package this pass has no lead on, and
  root access this session's SSH login doesn't have (`sudo` prompts for a password not available here).
- **Practical consequence for the deployment decision**: no CPU-vs-GPU latency comparison is possible
  this pass. The CPU number alone (~30 FPS) is already well above any plausible requirement for a
  camera-trap-style trigger-on-motion pipeline, so this does not block a deployment decision — it just
  means the GPU path stays untested, not ruled in or out, going into the 2 Sept trial.

## 29 Aug — GPU delegate gap re-investigated with root access: confirmed genuinely unavailable, not a permissions artifact

`sudo` was blocked in every prior pass. Root access was obtained this pass and used to search properly
before accepting "unresolved" as the final answer — three apt sources are actually configured on this
board (Debian, Arduino's own repo, and a real Qualcomm artifactory overlay,
`qsc-deb-releases`), so the missing-library question deserved a real search across all three, not just
a filesystem `find`.

**No package anywhere provides `libtensorflowlite_gpu_delegate.so`** — the exact soname Edge Impulse's
GPU-target `.eim` is linked against. Confirmed by downloading and inspecting file lists (`dpkg -c`) for
every plausibly-related package across all three repos, not just trusting package descriptions. Two
real, legitimate alternatives do exist, and neither is a fix for this specific binary:

- **`mesa-teflon-delegate`** — a genuine, actively maintained TFLite external delegate for NPU/GPU
  acceleration on Mesa-driven hardware (Freedreno/Adreno support included). Ships `libteflon.so`, a
  different soname with a different delegate ABI than Google's own TFLite GPU delegate.
- **ArmNN's GPU backend** (`armnn-latest-gpu`, `libarmnn-gpuacc-backend33`) — a real Arm Compute
  Library-based path to Mali/Adreno GPU acceleration via OpenCL, paired with
  `libarmnntfliteparser24t64` for TFLite model ingestion. Ships `Arm_GpuAcc_backend.so`, again a
  different library with a different API than what the `.eim` binary calls.

Neither can be symlinked into place as a drop-in fix — same concept (TFLite delegate), different
implementation and symbol table. **Using either would mean building a custom ArmNN-based runner to
replace `edge-impulse-linux-runner`, not installing a missing dependency** — a real, separate engineering
project, not a quick unblock, and out of scope this close to 2 Sept. This settles the question the 28 Aug
entry above left open ("would need a proprietary Qualcomm package this pass has no lead on"): there is no
such package on this board's reachable repos, full stop — the GPU path stays CPU-only for this trial by
a confirmed hardware/software gap, not by a permissions limitation this pass simply failed to clear.

**Live camera streaming — also blocked, worked around, not a data-quality concern:**
`edge-impulse-linux-runner`'s normal camera path needs `gst-launch-1.0`
(`gstreamer1.0-tools`). The board has every gstreamer *library* package installed
(`gstreamer1.0-plugins-good`, `-base`, `-libcamera`) but not the CLI-tools package that ships the
binary itself, and again `sudo` needs a password this session doesn't have. Worked around with
`--fake-camera <file>`, which reuses the same decode→resize→infer path minus the V4L2 grab step —
the latency number above is real inference time, not a live-capture artifact, but it does mean no live
day/IR-night true-negative frames were captured this pass (that half of Phase 5 needs either the
missing package installed by someone with the board's sudo password, or App Lab's own GUI run path).

## 28 Aug — confirmed and fixed a real train/test split-leakage bug in `elephant-detection-cxnt1-v2`'s "frameNNNN" clip

This closes the exact open question this file already flagged in the 28 Aug bounding-box audit entry:
*"worth confirming it's actually collapsing this video's frames the same way before trusting this
source's contribution to any held-out number."* The answer is no, it was not — a real bug, now fixed,
with the leakage demonstrated directly against the live uploaded manifest before touching any code.

**The bug.** `group_key()`'s `_FRAME_TAIL` regex only strips a trailing frame counter when a `-` or
`_` separates it from the clip name (`"0011-61-"` → `"0011"`, `"E026-105-"` → `"E026"`). Roboflow's
export of `elephant-detection-cxnt1-v2` also contains 984 images named the other common video-export
convention, `frame<N>.jpg`, with no separator at all — `_FRAME_TAIL` never matches these, so
`group_key()` fell back to returning the whole stem, meaning **every one of the 984 frames was its
own singleton group** and got shuffled independently by `split_by_group()`'s per-group 80/20 split
instead of moving as one block.

**Confirmed as one real clip, not assumed.** The 984 frame numbers span 4339–5791 in two
near-contiguous runs (one gap around 5459–5718). A contact sheet sampled across that entire range —
frame4340, 4500, 4700, 4900, 5100, 5300, 5451, 5458, 5719, 5750, 5790 — is the same scene start to
finish: one elephant beside the same decorated lorry ("OM MURUGA" / "RAJMURUGAN") on the same road
with the same crowd. This is the viral "elephant reaching into a stopped truck" clip named in the
earlier near-duplicate audit — genuinely one continuous video, so collapsing all 984 frames into one
group is the correct fix, not an over-merge.

**Leakage confirmed against the real uploaded manifest, not just theorized**: `frame4338`,
`frame4339`, `frame4340` sit in `training` while `frame4349`, `frame4350`, `frame4355` — nine to
fifteen frames later in the same shot — sit in `testing`. Across the whole class, 984 of 6,049 total
Elephant images (16%) came from this one clip, with 227 of the 984 landing on the `testing` side —
meaning roughly a fifth of that "held-out" slice was near-duplicate to training frames a few frames
apart. Any Elephant recall/precision number reported against the current live project's split is
inflated by this, on top of the already-documented species-contamination caveat.

**The fix** (`scripts/edge_impulse_upload_vision.py`): added `_FRAME_TAIL_NO_SEP`, a second, narrow
pattern (`^[A-Za-z]{3,}\d{2,}$`) tried only when `_FRAME_TAIL` doesn't match at all — a pure-alphabetic
word directly followed by a real multi-digit counter, nothing else. Deliberately narrow so it cannot
repeat the `Wild_Boar_NNNN` over-merge mistake this same file already documents for the deterrent-cam
Boar source (opaque hex/alphanumeric IDs like `000a6c3a2c4d97e7` start with a digit and interleave
letters and digits throughout, so they never match and correctly stay singleton). Verified empirically
against every current `DATASETS` source before landing it — `frame4340` now correctly collapses to
`frame` (984-image group); every other source's grouping is byte-for-byte unchanged, confirmed by
running old vs. new grouping side by side over each source's real local files and diffing membership,
not just group counts.

**Not yet applied to the live project.** This fixes the split for any future upload; the categories
already sitting in Edge Impulse project 1097972 still reflect the old, leaked split until the next
full re-upload. That re-upload is already pending on the `thai-elephant-dataset-v6` cleanup approval
(see the 27 Aug species-verification entry) — this fix rides along with that same re-upload rather than
triggering a separate live-project category shuffle now, so the eventual clean retrain gets a correct
split on the first try instead of needing a second pass.

## 28 Aug — `thai-elephant-dataset-v6` cleanup, re-upload, and a second real bug found during reconciliation

**Cleanup.** With user approval, `scripts/cleanup_thai_elephant_vision.py` deleted the 1,315
sha256-content-matched `thai-elephant-dataset-v6` samples still live in project 1097972 (the source
was removed from `DATASETS` on 28 Aug — see the bounding-box audit entry above — but removing it from
the script never touches already-uploaded data). 0 failures; project raw-data total dropped
16,033 → 14,718, an exact match to "1,315 deleted." A second independent content-hash pass afterward
confirmed 0 residual matches. Of the original 2,397 local `thai-elephant-dataset-v6` files, 1,082 had
no remote match at all — almost certainly already removed by a first cleanup attempt that hit this
session's tool timeout partway through, not a real discrepancy.

**Re-upload to apply the split-leakage fix.** Ran `edge_impulse_upload_vision.py` live (after a clean
`--dry-run` confirming `thai-elephant-dataset-v6` is genuinely absent from `DATASETS`) to push the
`group_key()` fix above into the live project. The script's own project-level reconciliation check —
built specifically to catch this class of silent drift (see the 27 Aug 71-image-gap entry) — correctly
**hard-failed**: live project totals (11,484 training / 3,234 testing = 14,718) didn't match the
manifest's expected totals (10,719 / 3,013 = 13,732), a 986-image net surplus. Per this project's own
standing discipline, training was not attempted against an unreconciled project. The 986-image gap was
decomposed in full before any live action:

- **1,140 images (570 each direction) — harmless train/test category drift.** The same "assignment
  drift" phenomenon as the 27 Aug precedent: the split-leakage fix above changed which neighboring
  frame-groups land on which side of the 80/20 boundary for images already uploaded under the previous
  candidate pool. This is the part that actually mattered for correctness — an image the current split
  expects in `testing` but which was still sitting live in `training` would train on it, silently
  re-contaminating the exact held-out set the fix above was written to protect. **Fixed and verified.**
  Paginated the live project's `training`/`testing` samples, diffed filenames (extension-stripped —
  Edge Impulse's `filename` field never carries one) against the manifest's expected split, and moved
  the 1,140 mismatched samples via `POST raw-data/batch/moveSamples`, chunked at 100 ids/call. The
  first attempt used the wrong request shape (a `samples: [{sampleId, category}]` body, guessed from
  the README's own prose description rather than the actual spec) and every chunk failed with `Unknown
  category undefined`; the real shape, confirmed against Edge Impulse's published OpenAPI spec, is a
  `newCategory` field in the body plus `category` (source) and `ids` (JSON-encoded array) as query
  parameters. Corrected and re-ran: 570 moved to `testing`, 570 moved to `training`, 0 failures. A
  fourth diff pass afterward confirmed **0 remaining category drift** — the live split now matches the
  current manifest exactly for every file the manifest tracks.
- **A second, previously-undocumented bug — real data silently orphaned from local tracking.** The
  remaining ~986-1,140 discrepancy traced to `scripts/fetch_swg_camera_traps.py`'s `fetch_images()`,
  which **overwrites** `_annotations.coco.json` on every run instead of merging into it. `SEED` stayed
  fixed but `TARGET_PER_PERIOD` was raised 300 → 1200 on 28 Aug on the stated assumption ("nothing
  already downloaded or already uploaded is invalidated by this bump") that the larger draw would be a
  strict superset of the earlier 300-per-period pass. For the `swg-eurasian-wild-pig` (Boar) and
  `swg-empty` (Background) sources specifically, that assumption did not hold: the later run's
  selection landed on a set of images with **zero filename overlap** with the earlier run's selection
  (GUID-style filenames vs. the earlier `public__lao/vietnam__loc_...` names), and because the write is
  an overwrite rather than a merge, the earlier run's ~550 Boar and ~628 Background images — real,
  already uploaded, still live in project 1097972 right now — dropped out of local
  `_annotations.coco.json` and `dataset_manifest.json` tracking entirely. They were never bad data;
  they simply became invisible to the pipeline's own bookkeeping. **Decision (with the user): leave
  them live, do not delete and do not attempt to merge them back into tracking this pass.** Deleting
  would discard real working data for the exact class (Boar) that is this project's accuracy
  bottleneck, for no quality reason — unlike `thai-elephant-dataset-v6`, there is no audit finding
  against these specific images, only a bookkeeping gap. Merging them back requires a script fix
  (`fetch_images()` needs to read-and-merge an existing annotation file rather than overwrite it) and a
  live re-fetch, and for the Boar half specifically would be adding untracked, unaudited data into a
  source the wider bounding-box audit already flagged as materially contaminated (~27-30% of a sampled
  crop had no confidently identifiable animal) — not a clear win this close to 2 Sept. Recorded here as
  a real, open gap rather than silently absorbed: **`fetch_swg_camera_traps.py`'s annotation-file write
  needs to merge, not overwrite, before this script is run again for these two sources**, or any future
  `TARGET_PER_PERIOD` change will keep orphaning whatever the previous run selected.
- **192 Boar images — a smaller, unconfirmed sub-gap.** Present in the current parse and marked
  "already uploaded" in the resume ledger, but not actually live in the project. Leading hypothesis is
  Edge Impulse's content-duplicate rejection recorded as "done" in the ledger without a corresponding
  live sample, mirroring the already-documented 71-image duplicate pattern from 27 Aug — not
  independently confirmed this pass.

The upload script's own hard-fail gate stays tripped on this run's log until it's taught to expect the
986-image discrepancy above as a documented, accepted condition (a follow-up, not done this pass) —
it does not block training itself, since the category-swap fix (the part that actually affects split
correctness) was applied directly against the live project via `moveSamples`, independent of the
upload script's own exit code.

## 28 Aug — clean retrain on the reconciled, decontaminated project: recall dropped, and that is the real number

Ran `yolo-pro-nano attn_silu` (the 27 Aug sweep's leader) again from a fresh impulse against project
1097972 now that every fix above had actually landed: the `group_key()` split-leakage fix, the
`thai-elephant-dataset-v6` removal, and the re-upload/category-drift reconciliation (all three, the
two entries directly above). This is the first held-out number this project has produced on a corpus
with no known leakage and no known species contamination — everything before this entry carries one or
both caveats.

| | Elephant | Boar | Background |
|---|---|---|---|
| Test images | 1,067 | 1,239 | 928 |
| Recall | 0.706 | 0.617 | — |
| Precision | 0.967 | 0.978 | — |
| F1 | 0.663 | 0.570 | — |
| Perfect-F1 | 33.6% (358/1067) | 27.0% (334/1239) | — |
| FP rate | — | — | 0.024 (906/928 clean) |

**Recall fell sharply against the 27 Aug sweep entry for the same architecture** — Elephant 0.855 →
0.706 (-14.9 points), Boar 0.761 → 0.617 (-14.4 points) — while precision held essentially flat
(Elephant 0.974 → 0.967, Boar 0.978 → 0.978) and the background false-positive rate actually
*improved* (0.048 → 0.024). Precision holding steady while recall alone drops is exactly the signature
split leakage produces: near-duplicate frames a few frames apart from the same source clip landing on
both sides of the 80/20 boundary let the model get partial credit for "recognizing" test images it had
effectively already seen in training, inflating recall specifically (precision is far less sensitive to
this since the model wasn't predicting spurious boxes, just scoring true positives it had memorized).
**The 27 Aug figure (0.855 / 0.761) should be treated as leakage-inflated and superseded by this entry.
This entry's numbers — Elephant R 0.706, Boar R 0.617 — are this project's real, trustworthy baseline
against the ≥92%-per-class recall bar, and they are further from that bar than previously believed**,
not closer: a 21.4-point gap on Boar, 21.5 on Elephant, materially larger than the 6.5–16 point gap the
27 Aug entry reported. Neither class clears 92% recall. Named plainly rather than smoothed over,
per this file's own standing discipline.

Test-set size also grew substantially (332 → 928 Background, and Elephant/Boar now report per-class
counts for the first time at this scale: 1,067 / 1,239 vs the previous entry's shared 332-image
Background-only column) — a direct consequence of the corpus reconciliation landing more real,
correctly-split data, not a scoring-methodology change.

**Next lever, unchanged from the 27 Aug entry's own conclusion**: the confidence-threshold sweep (§4 of
the plan) was never actually banked into any number yet — every prior attempt hit the
`regenerateModelTestingSummary`-unsupported-for-object-detection wall, fixed but not yet re-run against
a model trained on the clean split. Lowering the threshold from Studio's default 0.5 is expected to
recover some of this recall gap at a precision cost; run it against this exact model before drawing any
conclusion about whether the architecture itself can reach 92%, since the number above is reported at
an untuned default threshold. **This is the next action, not EON Tuner or a different architecture** —
tune the lever already known to move recall before reaching for a new one.

## 28 Aug — threshold sweep on the clean model: recall recovers, but neither class reaches 92%, and the FP cost of trying is too high

Ran `--sweep-thresholds` against the clean-retrain model from the entry above, over `{0.05, 0.1, 0.2,
0.3, 0.5}` per §4 of the plan. Same 1,067 Elephant / 1,239 Boar / 928 Background held-out set at every
point — only the confidence threshold changes.

| Threshold | Elephant R / P / F1 | Boar R / P / F1 | Background FP rate |
|---|---|---|---|
| 0.05 | 0.860 / 0.796 / 0.790 | 0.797 / 0.785 / 0.727 | 0.245 (232/928 false) |
| 0.1 | 0.837 / 0.863 / 0.771 | 0.761 / 0.855 / 0.698 | 0.151 (140/928 false) |
| 0.2 | 0.803 / 0.920 / 0.743 | 0.725 / 0.913 / 0.664 | 0.075 (70/928 false) |
| 0.3 | 0.773 / 0.943 / 0.718 | 0.689 / 0.939 / 0.633 | 0.048 (45/928 false) |
| 0.5 (Studio default) | 0.706 / 0.967 / 0.663 | 0.617 / 0.978 / 0.570 | 0.024 (22/928 false) |

**Threshold tuning is a real lever, but it does not close the gap to ≥92% recall per class at any
tested point.** Even at the lowest threshold tried (0.05 — already aggressive; Studio's own default is
0.5), Elephant tops out at 0.860 recall (6.0 points short of 92%) and Boar at 0.797 (12.3 points
short). **Getting there would require pushing the threshold lower still, and the false-positive curve
makes that impractical**: at 0.05 nearly a quarter of genuinely empty scenes (24.5%) already fire a
false alert; a threshold low enough to plausibly reach 92% Boar recall would very likely push background
FP rate well past 30-40%, which is not a workable rate for a field deployment residents and rangers are
meant to trust — an alerting system that cries wolf on roughly one in three or four passes is worse
than a lower-recall one that is at least believable when it fires. **No single tested threshold is
recommended as "the" deployed value without a stated tradeoff**; 0.1-0.2 is the most defensible practical
range (recall 0.72-0.86 across classes, FP rate 7.5-15.1%), and whichever point ships must be reported
with both numbers together, never recall alone.

**What this means for the ≥92%-per-class bar, stated plainly**: this architecture (`yolo-pro-nano
attn_silu`), on this corpus, at any threshold tested, does not clear it. The honest per-class verdict at
the time of this entry is **not met** for both Elephant and Boar, at every threshold tried, with the
false-positive cost growing sharply as recall is pushed toward it. EON Tuner's full custom search
(confirmed API-reachable in Phase 0, never yet actually run) is the next untried lever, alongside the
already-flagged Boar bounding-box contamination finding (28 Aug widened audit) as a plausible ceiling on
Boar recall specifically that no amount of threshold or architecture tuning can fix — bad ground truth
caps the achievable score regardless of model quality.

**Scope note, updated 28 Aug — superseded**: this entry originally said the detector was not yet wired
into `cognition/fusion.py`'s live alert path. That has since changed: `device/mpu/services/reflex_loop.py`
now runs this detector as a genuine pre-decision step (camera opens, a short burst is captured and
classified, and the result feeds a real `VISION` `ModalityReading` into `fuse()`) on every footfall event,
*before* `decide()` runs — seismic wakes vision, vision attempts to confirm, and only then is the alert
decision made. See `docs/KNOWN_GAPS.md`'s vision entry for the full wiring and its own remaining open
items (runner-process supervision, the night/no-IR-before-decision limitation, the unresolved Boar-
detection question). The recall shortfall documented above is unchanged and still real: this model's
per-class recall has not yet cleared the ≥92% bar on any threshold or architecture tried, and that
directly affects the VISION modality's evidence quality now that it is live in the alert path, not just
snapshot/corroboration quality for human review as this note previously said.

## 28 Aug — first live end-to-end verification on real hardware: camera → runner → inference confirmed working

All prior on-device numbers (CPU ~33.8ms/inference via `--fake-camera` replay) exercised the
decode→resize→infer path but never the actual live V4L2/GStreamer camera capture, blocked by two
missing Debian packages on the board (`gstreamer1.0-tools`, then `gstreamer1.0-plugins-base-apps` —
see `docs/KNOWN_GAPS.md`). Both installed (user ran `sudo apt-get install` directly on the board over
two rounds). `edge-impulse-linux-runner --model-file etx_cpu.eim` (camera auto-selected; the board
enumerates its camera by a libcamera-style path, not `/dev/video0`, so an explicit `--camera /dev/video0`
fails) ran live for a 30-second window: connected cleanly to the real USB camera, **558 real inference
cycles, steady ~19ms/inference** (lower than the fake-camera 33.8ms figure — plausibly a different
export or pipeline overhead difference between the two measurement paths, not yet reconciled; report
both, do not average them), zero detections fired during the window. That last number is not a measured
false-positive rate (the scene in frame was not a controlled/known negative), just an observation that
nothing spurious fired during this specific run. **This is the first real confirmation that the whole
pipeline — camera capture, GStreamer, model inference — works end-to-end on the actual deployed
hardware**, not just the inference step in isolation.

## 28 Aug — EON Tuner confirmed unusable for the YOLO-Pro search space; abandoned in favor of manual head-to-head

Phase 3's plan was to drive EON Tuner's full custom search via `/api/1097972/optimize/*` with the
plain project key (confirmed API-reachable in Phase 0). Tried this live, twice, with
`searchSpaceTemplate: {"identifier": "object_detection_yolo_pro"}` in the `POST optimize/config`
body:

1. First attempt, against a YOLO-Pro learn block that was configured but had never been trained —
   failed with `"YOLO-Pro block not found"`. Hypothesized the Tuner requires a real completed
   training job to exist on that block before it will search around it.
2. Second attempt, run immediately after training `yolo-pro-nano attn_silu` to completion on this
   project (a genuine ~38-minute job, real held-out results below) — **failed with the identical
   `"YOLO-Pro block not found"` error.** This disproves the "untrained block" hypothesis.

**Conclusion: EON Tuner's `/optimize/*` API path does not work against this project's YOLO-Pro block,
for a reason not resolvable from the client side** — most likely an undocumented platform/tier
validation gap, not a request-shape mistake (the same request body matches the OpenAPI spec and
succeeds for `optimize/config`/`optimize/state`/`optimize/runs` reads; only the YOLO-Pro search launch
itself fails). Two independent live attempts is enough evidence to stop here rather than keep burning
real training compute testing further hypotheses. **Do not retry this blindly in a future session** —
if EON Tuner is wanted again, start by checking Edge Impulse's own support/changelog for a known
YOLO-Pro-Tuner incompatibility rather than re-deriving this from scratch.

Pivoted to the plan's fallback: drive `scripts/edge_impulse_train_vision.py` directly per family
(`--family yolo-pro`, `--family ssd`) as a manual, scripted head-to-head comparison instead of relying
on the Tuner's ranking. See the entries below for both architectures' real numbers.

## 28 Aug — deployed threshold set to 0.05 for the field test, explicitly not a production value

Per an explicit user decision: the live confidence threshold on the deployed learn block was set to
**0.05** via `POST /{project}/impulse/{impulse_id}/set-thresholds` (`{"blockId": <learn_id>, "key":
"min_score", "value": 0.05}`), confirmed applied (`{"success": true}`).

**This is a test-capture-only value for the upcoming field trial, not the production default.**
Rationale, stated by the user directly: during this field test, ranger alerts are not being sent from
vision detections, so the elevated false-positive rate this threshold produces (24.5% of genuinely
empty scenes fire per the sweep table above) costs nothing operationally — the system is only
recording what it sees for later review. Missing a real elephant, by contrast, has a real cost even in
test mode (a missed capture is missed evidence). Under that asymmetry, maximizing recall at 0.05 is the
correct choice **for this phase only**.

**This must be revisited before real ranger alerts go live.** Once the VISION modality's evidence
starts driving an actual alert dispatched to a ranger or resident, the false-alarm cost stops being
free — a system that cries wolf on roughly one in four empty scenes will be ignored or distrusted
quickly. The 0.1-0.2 range identified above as "the most defensible practical range" for a *production*
deployment still stands as the recommendation once that transition happens; this 0.05 value is
deliberately not that.

Note also: rebuilding the impulse for a different architecture (as the SSD comparison below required)
deletes and recreates the learn block, which wipes any threshold set on the old block. Whichever
architecture and impulse configuration is selected as final must have this threshold decision
re-applied explicitly before the field trial — it does not persist across an impulse rebuild.

## 28 Aug — architecture head-to-head: YOLO-Pro-nano vs MobileNetV2-SSD, and an honest read against the ≥92% bar

Trained both remaining Phase 3 candidates directly via the API (EON Tuner abandoned, see above),
scored on the identical held-out protocol used throughout this log — per-class, grouped by
ground-truth label, never averaged.

**YOLO-Pro-nano (attn_silu), retrained clean for this comparison** — 1,067 Elephant / 1,239 Boar / 928
Background held out:

| | Recall | Precision | F1 |
|---|---|---|---|
| Elephant | 0.702 | 0.961 | 0.657 |
| Boar | 0.616 | 0.977 | 0.563 |
| Background | 96.1% clean (FP rate 0.039) | | |

At the 0.05 threshold from the sweep above (same architecture, same corpus, a run one entry prior to
this one): Elephant recall 0.860, Boar recall 0.797, Background FP rate 0.245.

**MobileNetV2-SSD FPN-lite 320×320 — attempted, does not produce a comparable number.** Three real
attempts, in order:

1. First launch mistakenly reused a stale 96×96 DSP block (`--skip-impulse` does not rebuild the
   impulse, and SSD requires exactly 320×320); caught via a live jobs-API check and stopped before it
   trained against the wrong input size.
2. Second launch, without `--skip-impulse` so the impulse correctly rebuilds at 320×320, failed
   outright with `"A feature generation job is already running for this DSP block"` — the first
   (stopped) attempt's remote Edge Impulse job had kept running server-side even though the local
   process was killed. **Stopping a local task does not cancel the corresponding remote job** — a
   real gap in how this pipeline is monitored, worth remembering for any future background job.
3. Third launch, after the stale remote job cleared: feature generation succeeded (320×320, 4.8 min),
   training params were set correctly (`batchSize: 8`, confirmed sent), and the job ran for **30.1
   minutes before OOM-killing (exit 137)** — the same failure mode as the pre-existing OOM history in
   this log, despite the batch-size fix that was believed to have resolved it. The job's own log shows
   why: the OOM happens during a **"Fine tuning..." sub-stage** that prints `Batch size: 32` — a
   *different* stage from the one our `batchSize: 8` request configures, and one that Edge Impulse's
   own SSD training script apparently runs with a hardcoded batch size. Checked the full
   `SetKerasParameterRequest` schema in the live OpenAPI spec: `batchSize` is the only batch-related
   field this endpoint exposes, and it is documented as governing training generally, with no separate
   field for a fine-tuning sub-stage. **This is a genuine platform/model-script limitation, not a
   caller-side mistake** — there is no API-reachable way to lower the fine-tuning stage's batch size
   for this specific model. The error message's own suggestion ("increase train job memory in the
   project dashboard") is a Studio UI-only setting with no corresponding API field either (confirmed
   against the same spec).

**Decision: SSD is not pursued further.** A fourth attempt would cost another ~30+ minutes of real
compute for an architecture that was already the lowest-priority Phase 3 candidate, against a platform
limitation this script cannot work around. Given the 2 Sept deadline and that YOLO-Pro-nano already has
strong, complete, real held-out numbers in hand, the head-to-head comparison concludes with YOLO-Pro-nano
as the only architecture with a usable result.

**Honest read against the ≥92%-per-class bar, stated plainly per this file's standing discipline:**
across every architecture and threshold actually completed (`yolo-pro-nano attn_silu` at five threshold
points, `fomo_mobilenet_v2_a35` from the 27 Aug entry; SSD did not produce a usable result, see above),
**no configuration clears 92% recall on both classes simultaneously.** The closest approach is
`yolo-pro-nano attn_silu` at threshold 0.05: Elephant 0.860 (6.0 points short), Boar 0.797 (12.3 points
short) — and that gap is bought at a 24.5% background false-positive rate, which is why it is deployed
as a field-test-only value and not recommended for production. Phase 4's data-work levers (SWG
domain-match top-up, Asian-elephant/WCS species-correct supplements, pseudo-IR synthetic augmentation)
are all already landed in this corpus — confirmed via the "28 Aug — SWG background top-up landed" entry
above — meaning the recall numbers in this entry already reflect that work, not a baseline that could
still improve from running it. **The remaining gap to 92% is not a lever this pass left untried; it is
a real ceiling** on this corpus/architecture combination, most plausibly explained by two things this
pass could not manufacture: real (not pseudo) IR/night footage, and further bounding-box cleanup for
the Boar contamination finding from the 28 Aug widened audit, which caps Boar's achievable score
regardless of model quality. **Deployed recommendation: `yolo-pro-nano attn_silu` at threshold 0.05,
for this field test only**, with the production-threshold and recall-ceiling caveats above carried
forward explicitly rather than dropped.

## 28 Aug — data-quality re-verification: a TV-broadcast overlay finding, and a real gap in the African-elephant filter, both currently live in the corpus the deployed model was trained on

Triggered by a training sample the user spotted directly in Studio's Data Acquisition view —
`0003-127-...jpg`, a Thai TV news broadcast screen-capture (channel bug, live stock ticker, anchor
picture-in-picture) with an Elephant box drawn on the animal visible inside the broadcast footage —
with the explicit instruction to re-verify labeling correctness and dataset quality generally, not
just that one image. This entry documents what was actually checked and what was not; it does not
claim the full corpus was reviewed, because it wasn't — see the honesty note at the end.

**Method.** `elephant-detection-cxnt1-v2` (the same source already flagged in this log for species
contamination and a split-leakage bug) is built from frame-extractions of ~40 distinct video clips,
identified by the filename prefix before the first `-` (e.g. `E026-105-...`, `0003-127-...`). A
prefix histogram was run across the full 3,280-image source; the ten largest clips by frame count
(`E026`=155, `0011`=94, `a003`=81, `A0004`=46, `0008`=46, `0009`=41, `0007`=41, `0005`=33, `0010`=15,
`5460`=20 — 572 images, 17.4% of the source) were each sampled by opening one representative frame
and reading it directly, the same visual-judgment-call method the Boar audit above already
established as the only reliable check for this class of defect.

**Finding 1 — TV-broadcast screen-capture contamination is widespread, not isolated to one clip.**
9 of these 10 largest clips (all but `A0004`, which is a genuine grayscale camera-trap frame with a
temperature/timestamp burn-in — a different, benign kind of overlay standard to real camera-trap
gear) are frame-grabs from Thai TV news broadcasts: visible station bugs (`MCOT HD 30`, `Thairath TV
32`, `AMARIN 34 HD`, `THE WORLD`, `สำรวจโลก`), live tickers and Thai-caption lower-thirds, "LIVE"
badges, and in several frames an anchor picture-in-picture inset — all baked directly into the pixels
the model is trained to associate with "Elephant present." That's 526 images (16.0% of the source)
confirmed by this sample alone; the true share across the ~30 smaller clips not sampled is unknown.
This is a real risk beyond aesthetics: a consistent top-right logo/lower-third layout recurring across
hundreds of positive images is exactly the kind of spurious, position-fixed cue a small FOMO/YOLO
detector can latch onto instead of the elephant's own shape, which would not show up as a held-out
recall problem (the held-out set is drawn from the same contaminated pool) but would hurt real-world
generalization to clean camera-trap footage with no broadcast graphics.

**Finding 2 — the existing `AFRICAN_ELEPHANT_FILENAME_MARKERS` filter (27 Aug entry above) has a
confirmed, currently-live gap.** That filter is a place-name keyword list (`namibia`, `kenya`,
`tanzania`, `kruger`, `etosha`, `amboseli`, `zimbabwe`, `serengeti`, `africa`) and correctly removed
33 images whose filenames named a place. It cannot catch a stock photo with a generic filename and no
place name. Two such images —
`elephant-crossing-road-12267234_jpg.rf.b8d0840046f8734d14860bafccc5041b.jpg` and
`elephant-crossing-road-20777933_jpg.rf.7d6fd24f14a7abb9ef6b086305d61f35.jpg` — were opened directly
and are unambiguous African bush elephant (fan ears well past the shoulder, concave/sway back,
Dreamstime watermark visible), yet carry no filter-matched keyword. A follow-up regex sweep for the
broader "safari stock photo" genre (`crossing-road|dreamstime|shutterstock|istock|alamy|...`) found
**41 boxed-Elephant images matching that genre; 26 carry an explicit Africa-keyword hit (already
caught by the existing filter) and 15 do not.** Of those 15, the two named above were visually
confirmed African; the remaining 13 were not individually opened this pass and are reported as
unconfirmed, not as clean. Cross-checked against the live `dataset_manifest.json`: **both confirmed
gap images, and all three of `0003-127`, `E026-105`, `0011-102` from Finding 1, are present in the
current `training`/`testing` lists** — this is live contamination in what the deployed model was
actually trained on, not an already-fixed historical issue.

**A separate, lower-severity observation, not a labeling bug.** ~150 frames across five clip
prefixes (`mask-*`, `Mask-*`, `Mask2-*`, `no-mask-*`, `mo-justin-mask-NoMask-*`, `face-detection-*`,
`Inside-merge-*`, `ashton-video-*`) are indoor human-subject webcam footage — face-mask-detector demo
clips, by filename and content, with zero elephants. Checked directly against the source's own COCO
annotation files: **all of them carry zero bounding boxes**, so they are not mislabeled as Elephant —
they're unboxed background frames, which is how this pipeline treats zero-box images generally. Not a
correctness bug, but a provenance flag: this Roboflow project was very likely forked/merged from an
unrelated mask-detection project at some point, and indoor human-subject clips are low-value noise as
forest-camera-trap negatives compared to the real SWG/board-captured negatives already in Phase 2.
The `WhatsApp-Image-*` clips sampled alongside these do carry real Elephant boxes and read as genuine
user-submitted sighting photos — a different, apparently-clean category, not further audited this pass.

**What was not done, stated plainly.** The user asked to verify bounding boxes in every single image
in the training corpus. That was not done, and is not achievable by hand in the time remaining before
2 Sept — the corpus is 6,560+ images across four sources; a full manual pass is the same order of
effort as the per-image Boar relabel that was already assessed and declined for the same reason
earlier in this log. What was done instead: the same sampling method that has caught every real
contamination finding in this log so far (Boar bounding-box audit, African-elephant species check),
applied here at the clip level rather than the image level, which is the only way to get meaningful
coverage of a 3,280-image source in the time available. **Edge Impulse's own automated tools were
checked as a scalable alternative and one genuine gap was found**: `POST
/{project}/jobs/data-quality-metrics` (label-noise and diversity detection, which would otherwise be
the right tool for exactly this problem) returned `"Only staff can calculate data quality metrics"` —
confirmed staff-gated on this Enterprise project, not something this pipeline can call regardless of
plan tier. The Data Explorer (embedding-based visual clustering, `/{project}/jobs/data-explorer-features`)
is not staff-gated and was launched (job `53232201`) but **failed server-side**: `ValueError: Cannot
load file containing pickled data when allow_pickle=False` in Edge Impulse's own
`/app/resources/data-explorer/custom.py:23`, loading `y_train_features.all.npy` — a numpy-version
mismatch in Edge Impulse's own script (whatever wrote that file pickled it; the reader now runs with
numpy's newer, stricter default), not anything caller-side to fix. **Both of Edge Impulse's native
automated data-quality tools are dead ends on this project right now** — one gated to staff, the other
broken — so the one-frame-per-clip manual sampling above is the only method that actually works today.

**No remediation implemented yet.** This entry is the honest verification the user asked for, not a
fix. Two concrete, cheap options for the remaining findings, neither yet executed: (a) extend
`AFRICAN_ELEPHANT_FILENAME_MARKERS` with the broader stock-photo-genre pattern and re-run the
existing filter (catches the confirmed gap mechanically); (b) add a `TV_BROADCAST_CLIP_PREFIXES`
exclusion list seeded with the 9 confirmed clips from Finding 1 (mirrors the existing
`BOAR_VISUALLY_CONTAMINATED_FILENAMES` mechanism, just keyed on clip prefix instead of full filename)
— cheap and mechanical once a clip is confirmed by eye, same as every other audit in this log, but
the remaining ~30 smaller clips would need the same one-frame-per-clip sampling pass before that list
could be called complete. Both would require a retrain to take effect, and the currently in-flight
`no_attn_relu` variant sweep should finish first per the established one-job-at-a-time constraint.

## 28 Aug — data-quality remediation: both fixes implemented, a leak into the synthetic pipeline caught along the way, 581 contaminated samples deleted from the live project

Follow-up to the entry above. The user's explicit call, given both findings: fix both now and retrain,
rather than defer either — contaminated data actively hurts real-world recall regardless of what it
does to the held-out number, so a smaller clean corpus beats a larger contaminated one. Deferred: the
~30 smaller unsampled clips, per the user's explicit instruction not to block this fix on auditing them
first; that stays a follow-up pass.

**Fix 1 — `AFRICAN_ELEPHANT_VISUALLY_CONFIRMED_FILENAMES`.** All 15 "safari stock photo genre" images
without an Africa keyword hit (Finding 2 above) were opened and individually visually confirmed, not
assumed from the genre pattern: 12 are unambiguous African bush elephant (fan ears past the shoulder,
concave/sway back) and were added to a new explicit filename set, the same discipline as
`BOAR_VISUALLY_CONTAMINATED_FILENAMES`. The other 3 are genuinely Asian — a real Kerala corridor
(Tirunelli–Kudrakote), a Yala National Park, Sri Lanka frame, and one unlabeled test-split frame — and
were deliberately left out, which is exactly why this had to be an explicit list rather than a
`crossing-road`/stock-photo-site substring rule.

**Fix 2 — `TV_BROADCAST_CLIP_PREFIXES`.** The 10 confirmed clip prefixes from Finding 1 (9 broadcast
clips plus deliberately not `A0004`, the genuine camera-trap frame) wired into `parse_coco()` via a new
`exclude_broadcast_clips` flag on the `elephant-detection-cxnt1-v2` `DATASETS` entry.

**A third leak found while validating the above, not in either original finding: the synthetic
pseudo-IR pipeline inherits contamination from its source frames, and no existing filter caught it.**
`scripts/make_pseudo_ir_vision.py` renames every frame it touches to `pseudoir_<counter>_<original
name>`, so `_is_named_african_elephant()` / `_is_tv_broadcast_clip()` — both keyed on the real source's
naming — silently stopped matching once a contaminated frame had been through that rename. Confirmed
live: 17 of 251 pseudo-ir-elephant frames (6.8%) trace back to one of the ten broadcast clips (0 to the
African-stock list). Fixed with a `_original_filename()` helper that strips the `pseudoir_\d+_` prefix
before either check runs, and both filter flags turned on for the `pseudo-ir-elephant` dataset entry.
Same reasoning as the source-frame fix applies unchanged: a greyscaled, gamma-corrected, vignetted copy
of a broadcast screen-capture still has the station bug and ticker baked into it.

**A fourth bug, mechanical, caught by the pseudo-IR fix rather than independent of it: the
reconciliation gap formula double-subtracted drops for local (no-third-party-page) sources.** For a
`local_root` dataset, `expect_images` is set from `len(records) + drops["missing_file"]` — but
`records` already excludes species/broadcast/visually-contaminated images, so the later gap check
subtracted those drops a second time. Invisible until now because no local source had ever had a
non-zero species/broadcast/visual drop; pseudo-ir-elephant's new 17-image `tv_broadcast` drop exposed it
immediately as a false `UNEXPLAINED GAP: -17 images unaccounted for`. Fixed by adding
`species_contaminated` + `visually_contaminated` + `tv_broadcast` into the local-source baseline
alongside `missing_file`. Re-ran `--dry-run` after the fix: `grep -c "UNEXPLAINED GAP"` across the full
output returns 0 — every drop across every source, local or paged, is now accounted for.

**Live deletion.** Filtering the manifest alone does not remove what an earlier run already uploaded to
project 1097972 — the same gap this log already documented and left unresolved for the original 33
African-filtered images (turned out, on point, those 33 were never actually live: a live `filename`
substring query for the keyword-matched marker `namibia` returned 0 samples in both categories, so that
particular cleanup debt did not carry forward). The new contamination did carry forward: a dry-run of a
new `scripts/cleanup_broadcast_contamination_vision.py` (matches live samples by filename, reusing the
exact same `_is_named_african_elephant` / `_is_tv_broadcast_clip` / `_original_filename` predicates the
upload script itself uses, so a sample is flagged here if and only if the next real upload would also
drop it) found exactly 581 live contaminated samples: 12 African-stock, 569 `tv_broadcast` (552 raw +
17 pseudo-IR-derived — matches the local audit exactly). Run for real after explicit confirmation:
**581/581 deleted, 0 failures.** Verified against `GET raw-data/count`: training 11,484 → 11,061 (−423),
testing 3,234 → 3,076 (−158), a −581 total matching the deletion count exactly.

## 28 Aug — 995-sample live/manifest mismatch: three independent causes, decomposed and remediated

The 581-sample deletion above shrank the candidate pool feeding every contamination-filtered source's
`split_by_group()` call. That call runs `random.Random(SPLIT_SEED).shuffle(keys)` over the *current*
candidate list — a full reshuffle, not a stable-prefix operation like `fetch_swg_camera_traps.py`'s own
`_select_by_group()` (which stays stable because its underlying group list doesn't change size when
`TARGET_PER_PERIOD` changes). Any change to a source's candidate-pool size moves the train/test split
boundary for every sample still in the pool, live or not. This is the fourth time a filter/dedup change
has done this (content dedup, species filter, broadcast filter, now this one) — not a bug in any one
fix, just what a seeded shuffle does over a resizing list. The next upload run's `reconcile_project_counts()`
hard-failed on a 995-sample total mismatch (training+testing combined) as a direct result.

`scripts/diag_reconcile_vision.py` (one-off, not part of the regular pipeline) decomposed the mismatch
exactly, by cross-checking every live sample's normalized filename against the fresh manifest under
*both* categories, not just its own:

- **2,555 live orphans** (samples not matching any expected filename under their own category) split into
  **1,368 cross-category** (the filename *is* expected, just under the other category — the split-boundary
  shift above) and **1,187 truly-gone** (stale, matching a `public__...`-prefixed naming convention
  `fetch_swg_camera_traps.py` stopped using once it switched to saving LILA images as
  `{image_id}.jpg` instead of the flattened source path — superseded, unreferenced duplicates of content
  the current draw already covers).
- **1,560 manifest-expected samples with no live match under either category**: 1,368 of these are the
  same cross-category samples counted from the other direction, plus **192 genuinely never-uploaded**
  `swg-eurasian-wild-pig` (Boar) images.

Math reconciles exactly: 1,187 + 1,368 = 2,555 orphans; 1,368 + 192 = 1,560 missing; 1,187 − 192 = 995 net.

**Remediation, run for real with explicit user approval** (`scripts/remediate_995_mismatch_vision.py`,
new one-off script): deleted the 1,178 stale `public__`-named orphans (1,178/1,178, 0 failures) and moved
the 1,368 cross-category samples to the category the fresh manifest expects, via the non-destructive
`POST /raw-data/{id}/move` endpoint (`moveSample`, body `{"newCategory": ...}`) rather than delete+reupload
(1,368/1,368, 0 failures). Re-ran the diagnostic afterward: down to 9 genuine orphans and 192
genuinely-missing, both entirely accounted for — see below.

**The 192 missing Boar images are not missing data.** Confirmed present, under a sibling filename, in
both `ml/datasets/vision/raw/duplicates-1097972.json` (the persisted cross-run duplicate-rejection ledger)
and the per-source `uploaded-1097972-swg-eurasian-wild-pig.json` resume ledger's "done" set. They were
never (re-)sent because resending would just be rejected again by `x-disallow-duplicates` — correct
behavior, not a bug. The 9 remaining orphans are all `Boar`-labeled, small, and left untouched (the
remediation script only ever acts on a sample it can positively classify as one of the two named buckets;
anything else is printed and left for manual follow-up, never guessed at).

### A fix attempted for the residual 192/9 gap, caught in `--dry-run`, and reverted

To close the accounting gap cleanly (so `reconcile_project_counts()` stops needing 192+9 explained by
hand every time it runs), a `cross_run_duplicate` filter was added to `edge_impulse_upload_vision.py`,
gated on `duplicates_ledger.get(ds["label"], {})` — i.e. looked up **by class label** ("Elephant"/"Boar"),
not by source slug — and applied to drop any record whose filename appeared in that label's persisted
duplicate history, before `split_by_group()`.

**`--dry-run` output caught this before it ever touched live data**: `elephant-detection-cxnt1-v2`
(normally 2,683 boxed+background images), `wild-boar-a1flm-v1` (1,892), and `wild-boar-deterrent-pzq5t-v1`
(1,308) all collapsed to 0 train/0 test after the filter. The persisted `duplicates-1097972.json` ledger
is per-project-per-**label**, accumulated across every run this project has ever had, including whatever
happened during the 1094260→1097972 migration and early pre-ledger-namespacing runs — it almost certainly
contains **self-match noise**: a filename logged as a "duplicate" because a later run re-attempted sending
an already-live file and got an `x-disallow-duplicates` rejection *against its own prior upload*, not
against a sibling under a different name. That is exactly the trap the third prior version of
`reconcile_project_counts()` fell into (see that function's own docstring above) — a forced re-verify of
an already-uploaded file always reports "already exists," indistinguishable from a genuine cross-file
duplicate once only the rejection reason string is visible. Trusting that ledger wholesale, even read-only
and not re-probed, reproduced the same failure mode through a different code path: it silently would have
told the split step that essentially all of three major sources' images were duplicates of something else,
discarding real, unique, correctly-labeled training data.

**Reverted in full** — both the up-front `duplicates_ledger` load position and the filter block — before
any live run. Re-ran `--dry-run` after reverting: all three sources back to their correct counts
(2,683 / 1,892 / 1,308). The residual 192-missing / 9-orphan gap is left unresolved by this pass,
deliberately: it is small, well-understood, entirely benign (192 confirmed duplicates that will never
usefully upload; 9 small unexplained Boar orphans), and the next data-composition change — the IR/night
and additional bounding-box sourcing below — will reshuffle the split boundary again regardless, making
this the natural point to re-run the same diagnose-and-remediate pattern once, covering both gaps
together, rather than chasing a ledger-based fix a second time. Any future attempt at this specific
accounting gap should diff against **live-fetched current state** (as `diag_reconcile_vision.py` already
does) rather than trusting the persisted duplicates ledger's per-label history at face value.

<!-- LIVE_SYNC_PLACEHOLDER -->

## 28 Aug — data-quality re-verification, third pass: a wholesale non-field-photography batch in elephant-detection-cxnt1-v2, wider than the broadcast-filter gap it was found through

Sharpened priority from the user: Elephant is now the primary target, urgently, with an explicit bar
(recall >92%, including at night) and a direct instruction to re-audit the existing corpus's annotation
quality rather than only add new sources. Two candidate Roboflow IR/night datasets were vetted first —
`elephant-thermal` (misleadingly named: real sampled images are ordinary daylight color photos of a
tiger, classes are `{DEER, ELEPHANT, TIGER}`, not thermal at all) and `detecting-elephants-at-night`
(no downloadable export — `versions: 0`, confirmed via a direct `1/coco` request returning 404 — plus
unlabeled numeric classes and a captive-enclosure domain mismatch visible in its sample thumbnails) —
both rejected on real visual inspection, not their names. `wcs-elephas-maximus` was confirmed fully
exploited: 194 of 325 WCS-classified Indonesia frames carry a real bounding box, already all 194 in use,
no headroom to top up without breaking the real-box-only discipline. SWG Camera Traps has no elephant
category at all, corroborated independently via a fresh dataset-page search.

That left the audit half of the instruction. A seeded (`random.Random(20260822)`) sample of real,
boxed elephant-detection-cxnt1-v2 images was drawn and rendered with their stored boxes for direct
visual inspection — the same discipline as the 3a species check and every `exclude_filenames` list in
this file. One of the 14 sampled ("Image110…") turned out to be a Thai TV broadcast screenshot that
the existing `TV_BROADCAST_CLIP_PREFIXES` filter (hyphen-prefix keyed) did not catch, because this
image's filename carries no hyphen before its digits — `_is_tv_broadcast_clip`'s
`filename.split("-", 1)[0]` check treats the whole filename as the "prefix," which never matches the
short numeric-prefix allowlist built from the *other* naming convention this source uses.

A full-population scan for that shape (`^[Ii]mages?\d+_`) found **164 filenames** across the three
splits (124 train / 7 test / 33 valid) — a second naming convention live in this source, disjoint from
the hyphen-prefixed clip frames the existing filter already covers. A further seeded sample of 16 of
the 164 (boxes drawn, each image opened by eye) came back **16/16 not usable**, and not for one uniform
reason:

- **10 of 16**: Thai TV news broadcast screen-captures (TNN, Thairath TV 32) — channel bugs, live
  tickers, stock/news crawlers, anchor picture-in-picture, the same defect class the existing filter
  targets, just a naming shape it doesn't reach.
- **1 of 16**: a scanned stock-photo book cover ("Identification Guide for Ivory and Ivory Substitutes,
  4th Edition") with a box drawn around one elephant in a group photo on the cover art.
- **1 of 16**: a watermarked Alamy stock photo (visible "alamy" watermark tiled across the frame).
- **3 of 16**: clean-looking (no visible overlay) but generic safari stock photography of **African**
  bush elephant — fan ears reaching past the shoulder, tusked adults, open savanna grassland or a paved
  road with visible vehicles, clear blue sky — the same species-contamination problem
  `AFRICAN_ELEPHANT_VISUALLY_CONFIRMED_FILENAMES` exists to catch, just not markable by the filename
  markers or the visually-confirmed list built for that source's *other* naming convention.

Zero of the 16 were real Asian-elephant field or camera-trap photography. A secondary, independent
defect surfaced in the same sample: one of the TV-broadcast frames ("Image160…") has a box that is
clearly misplaced — floating over background/vegetation rather than the visible elephant — a genuine
box-quality defect on top of the source-contamination issue, not investigated further this pass since
the whole frame is being dropped regardless.

Given 0/16 clean from a population of 164, whitelisting the unsampled 148 individually was judged less
defensible than treating the whole naming shape as contaminated — the same "when in doubt, exclude"
call this file already makes for `BOAR_VISUALLY_CONTAMINATED_FILENAMES`. New predicate
`_is_generic_named_scrape()` (`scripts/edge_impulse_upload_vision.py`) matches the naming shape via
regex rather than a curated filename list (the population is too large and too uniform in cause to
enumerate by hand the way the hyphen-prefix and African-stock lists were), gated behind a new
`exclude_generic_named_scrape` flag scoped to this one source only — no other dataset in `DATASETS` is
known to use this naming convention for real content. `--dry-run` after the change: `dropped 164
(generic_named_scrape)` for elephant-detection-cxnt1-v2, reconciliation math balances (no
`UNEXPLAINED GAP`), and the two prior filters' drop counts (45 species-contaminated, 552 tv-broadcast —
that number covers both the hyphen-prefixed clips and the pseudo-IR frames derived from them) are
unchanged.

**Live remediation**: `ml/datasets/vision/raw/uploaded-1097972-elephant-detection-cxnt1-v2.json`
confirms all 164 were already uploaded to the live project before this filter existed — this
contamination has been part of the corpus every model trained in 1097972 so far was trained on.
`scripts/cleanup_generic_scrape_contamination_vision.py` (new, following the exact structure of
`cleanup_broadcast_contamination_vision.py`) found **165 live matches** (164 originals + 1 pseudo-IR
frame derived from one of them) via a `--dry-run` against the live project — consistent with the local
filter. Live deletion is pending explicit user confirmation (blocked by the environment's own
permission classifier as a live external-service delete, correctly) before it runs for real.

**Net effect on the real Elephant corpus once this lands**: elephant-detection-cxnt1-v2 drops from
2,683 to 2,519 real boxed+background images; combined real Elephant total (all sources, pre-synthetic)
drops from 5,235 to 5,071. Boar is unaffected by this pass — the user's stated priority this round is
Elephant, urgently, with Boar explicitly lower-priority/best-effort.

<!-- LIVE_SYNC_PLACEHOLDER -->

## 28 Aug — data-quality re-verification, fourth pass: a second, larger species-contamination population, a Boar broadcast-clip leak, and the frame-clip subsampling decision implemented

**Species contamination, 5x the previously-known 45-image population.** `scripts/diag_reconcile_vision.py`'s
live/manifest orphan report (run to sanity-check the third-pass fix above) turned up **552 filenames**
in `elephant-detection-cxnt1-v2` — 233 `af_<id>`, 319 `as_<id>` — carrying real Elephant-labeled boxes
but not matching any filter above. Neither the hyphen-prefix broadcast list nor the `Image<N>_` generic-
scrape regex reaches this shape; it reads as a species-code naming convention (`af`=African, `as`=Asian)
from a different uploader batch than the rest of the source. A seeded (`random.Random(20260822)`) sample
of 10 per prefix, boxes rendered, each image opened by eye:

- **`af_`, 6/6**: unmistakable African bush elephant — fan ears reaching well past the shoulder, tusked
  in both sexes, savanna grassland/waterhole habitat, the concave/sway-backed profile Asian elephant
  never shows. Genuine species contamination, same defect `_is_named_african_elephant()` already exists
  to catch, just a naming convention it didn't know about.
- **`as_`, 5-6/6**: consistent with real Asian elephant — small crumpled ears, bilobed forehead. Correct
  species, left alone. One (`as_tr14`) is visibly captive/enclosure photography (fencing, hay bedding)
  rather than field footage — a domain concern worth a future pass, not a species defect, and not
  excluded here (this file does not otherwise filter captive Elephant content the way
  `BOAR_VISUALLY_CONTAMINATED_FILENAMES` does for Boar).

Fixed by extending `_is_named_african_elephant()` to also match the `af_` prefix, reusing the existing
`species_contaminated` drop bucket rather than adding a new one (avoids a second edit to the
reconciliation gap formula for no real benefit — the defect is the same one that constant already
names). `--dry-run`: `dropped 278 (species_contaminated)` for this source (was 45), Elephant real total
5,071 → 4,838. No unexplained gap.

**Live remediation**: all 552 (well, the 233 confirmed-contaminated `af_` filenames plus the pre-existing
45) were already uploaded before this fix existed. `scripts/cleanup_species_contamination_vision.py`
(new) found 248 live matches (233 + 15 pseudo-IR derivatives) via `--dry-run`. This was later found to be
a strict subset of what `cleanup_broadcast_contamination_vision.py` already matches (its
`is_contaminated()` checks the same two species predicates plus `_is_tv_broadcast_clip`) — **the
broadcast script is the one to actually run**; the species-only script stays in the repo as a narrower,
independently-useful diagnostic but is redundant for live cleanup purposes.

**Boar visual audit, second pass.** A fresh n=24 sample (12 per Boar source, same seed) — drawn because
the first n=56 pass's own write-up said plainly the true contamination rate is higher than any one
sample catches — came back 11/24 newly confirmed contaminated: more domestic pig (barn corner, captive/
fenced enclosure), two watermarked stock photos (one, "MSKWMCT25JS5", re-exported into *both* Boar
sources under different Roboflow hashes — same photographer, Jurgen Schiersmann), a captive/indoor
overexposed porch scene, a posed roadside photo with a human present, a captive/fenced pen, a second
watermarked stock photo (parisch-naturfoto.de), a captive pig pen (chain-link + doghouse), and one more
wrong-species warthog. All 11 added to `BOAR_VISUALLY_CONTAMINATED_FILENAMES`.

**Boar broadcast-clip cross-source leak.** While re-checking `TV_BROADCAST_CLIP_PREFIXES`' coverage,
`wb_framesb` and `wb_framesa00001` — both genuine video-frame sequences per `group_key()`'s frame-tail
stripping (built for exactly this naming) — turned out on visual inspection to be hunting-broadcast-show
footage: baked-in channel bug and lower-third, the same defect this list already exists to catch, not
camera-trap or direct field photography. `wb_framesb` is confirmed only in `wild-boar-a1flm-v1`;
`wb_framesa00001` leaks into both `wild-boar-a1flm-v1` and `wild-boar-deterrent-pzq5t-v1`. Both prefixes
added to `TV_BROADCAST_CLIP_PREFIXES`; `exclude_broadcast_clips` turned on for all three Boar `DATASETS`
entries — both real sources plus `pseudo-ir-boar`, which previously carried no filter flags at all.
`--dry-run`: `wild-boar-a1flm-v1` now drops 325 (tv_broadcast) on top of 13 (visually_contaminated, up
from 9 with the second-pass additions); `wild-boar-deterrent-pzq5t-v1` drops 1,459 (tv_broadcast) on top
of 10 (visually_contaminated, up from 3); `pseudo-ir-boar` drops 50 (tv_broadcast). Full reconciliation
table balances, no unexplained gap anywhere.

**Live remediation for both Boar findings**: `cleanup_broadcast_contamination_vision.py` picks up the
`wb_frames*` matches automatically (its predicate imports `_is_tv_broadcast_clip` directly, filename-
keyed, no dataset-level flag needed) — folded into the 802-match total below. A new
`scripts/cleanup_boar_visual_contamination_vision.py` matches against
`BOAR_VISUALLY_CONTAMINATED_FILENAMES` directly; `--dry-run` found only **13** live matches, well under
the 67-filename curated list — most of the first-pass 56 were apparently already cleaned in an earlier
session not explicitly logged here, so this is the real live delta from the 11 new filenames plus a
couple of pseudo-IR derivatives.

**Frame-clip subsampling — the user's standing 28 Aug decision, implemented this pass.** The 984-image
"frame" clip in elephant-detection-cxnt1-v2 (frame4338-frame5791, ~39% of the whole source, one
continuous dashcam sequence confirmed by an evenly-spread 10-frame contact sheet across the whole
numeric range — the viral RAJAMURUGAN "elephant reaching into a stopped truck" video, baked-in "U TURN"
overlay text) is a real elephant, not a species/broadcast defect, but its scale is duplication rather
than diversity. Per the user's explicit choice ("subsample to ~8-10 frames"), a new `cap_named_group()`
function in `scripts/edge_impulse_upload_vision.py` cuts one named group down to a target count, evenly
spread by embedded frame number (not a random draw) so the frames kept actually span the scene's
distinct beats — approach, reach, retreat — rather than risking a random draw clustering within one beat.
Wired via a new per-dataset `group_caps` flag (`{"frame": 10}`), applied after the drop-count gap-check
so it reports its own `post-cap:` line, the same convention `sample_target`/`post-sample:` already uses
for `wild-boar-deterrent-pzq5t-v1`. `--dry-run`: elephant-detection-cxnt1-v2 goes from 2,286 to 1,312
parsed images; "frame" drops off the largest-clips list entirely (now topped by `casino x103`). Full
reconciliation clean.

**Live remediation**: new `scripts/cleanup_frame_clip_duplication_vision.py` computes its drop set by
running the real `parse_coco()` → `cap_named_group()` pipeline locally against the live project, rather
than re-deriving the kept/dropped split by hand — so it can never drift from what a fresh upload would
actually produce. `--dry-run` against project 1097972 found **1,008 matches** (974 dropped source images
plus 34 pseudo-IR derivatives, consistent with "frame" having been the single largest source of pseudo-IR
sampling before the cap existed).

**Net effect on the real Elephant corpus, now that all three live deletes have landed**: elephant-detection-cxnt1-v2
dropped further (278 more species-contaminated, 974 more frame-clip duplicates); Boar gained real filter
coverage (broadcast-clip and second-pass visual contamination) without any new source data. All three
live-delete scripts were run for real by the user (this environment's own permission classifier blocks
live external-service deletes from being run directly) — 802 + 13 + 1,008 samples deleted, project
1097972 went from 12,794 to 10,971 remote samples. See `HANDOVER.md`'s "28 Aug (later still #4)"
checkpoint for the exact per-script counts.

**Still not started as of this entry**: a retrain against the cleaned-up corpus to get honest new
per-class recall numbers against the >92% bar. The next entry below covers real progress on the other
open item, "source more good data, especially IR."

## 28 Aug — two new real Boar sources found and wired in, one Nkhotakota claim corrected

Continuing "source more good data, especially IR" rather than starting the retrain yet.

**Correction, not a new finding**: an earlier entry in this file (and both `fetch_wcs_elephant.py`'s
docstring and its `DATASETS` comment) stated LILA's Nkhotakota Camera Traps has no public per-image
bounding-box file. Re-checked directly against the live LILA page - that was wrong. LILA's own page
text states a subset of 33,813 images across the full set does carry manually drawn bounding boxes.
The correction doesn't change the verdict: Nkhotakota's elephants are *Loxodonta africana*, the same
species mismatch that already ruled it out for the Elephant class on its own, independent of box
availability. Both source files updated to state the disqualifier correctly - species, not box
availability.

**New source 1 - `wcs-sus-scrofa`**: the same LILA WCS Camera Traps set already mined for Elephant via
`fetch_wcs_elephant.py` also carries real boxes for *sus scrofa* - the correct species (Kerala's wild
boar and the Indonesia/Laos forest pig this source covers are the same species, unlike the
African/Asian elephant split). Confirmed live: category 145 = "sus scrofa" carries 1,233 boxes across
831 distinct images; country breakdown idn (Indonesia) 734, lao (Laos) 94, bol (Bolivia) 3. The 3
Bolivia records excluded - Sus scrofa has no native South American range, and both Bolivia sequences
are single-frame 2008 captures consistent with an isolated feral/domestic-descent sighting, not the
wild population this project needs. 828 usable. Visually verified before writing any fetch code: a
seeded n=10 sample (seed 20260828) rendered with its real boxes and opened by eye - 6/10 unambiguous,
tightly-boxed wild boar; 4/10 lower image quality (motion blur, close-range flash blowout, fog) but
still plausible boar silhouettes; zero wrong-species mislabels in any of the 10. New
`scripts/fetch_wcs_boar.py` (mirrors `fetch_wcs_elephant.py`'s download/pixel-verify/COCO-synthesis
pattern) ran clean: **828/828 downloaded and pixel-verified, zero failures**. `--dry-run` reconciles
cleanly at 827 kept (1 content-duplicate image dropped, correctly identified and named).

**New source 2 - `pig-rinoz/wild-pig-at-night` (Roboflow, CC BY 4.0)**: small but a direct answer to
the standing "especially IR" instruction - genuine grayscale near-IR trail-cam footage, multiple real
camera brands visible in-frame (Bushnell, Moultrie, "JonahCam"), including one frame showing a full
sounder (adult + several piglets) at a feeder. Visually verified before adding: a 5-image sample pulled
directly from the source's public image URLs - 5/5 genuine night/IR camera-trap boar, no staged or
daytime-relabeled frames. Single class "wild-pig" in the source project, renamed to "Boar".

The dry-run's "largest clips" summary for this source flagged two filename patterns worth checking
rather than trusting on sight - the same discipline that built `BOAR_VISUALLY_CONTAMINATED_FILENAMES`
elsewhere in this project: a filename literally containing "warthog" and "domestic-pig"
(`out-organism-warthog-terrestrial-animal-domestic-pig-woodland-forest-1426089...jpg`, a classic
Adobe-Stock/iStock-style auto-generated descriptive filename), and a cluster of 12
`maxresdefault*`-prefixed filenames (YouTube's standard video-thumbnail naming convention). Both flags
turned out to be false alarms: all 13 flagged files were opened and inspected directly (7 checked in
full across both `train/` and `test/`, spanning multiple apparent source cameras), and every one is a
genuine wild-boar IR trail-cam frame - several carry authentic camera-trap timestamp/temperature
overlays, one carries an ATN thermal-scope reticle overlay, which a stock-photo pipeline would never
produce. The "warthog"-tagged file unambiguously shows a wild boar, not a warthog - the filename's
species word is a bad auto-tag from whatever scraper produced it, not evidence of contamination. The
`maxresdefault` names are consistent with these being frame-grabs re-scraped from trail-cam footage
that was itself uploaded to YouTube at some point - real pixels, just a rehosted filename. No exclusion
applied; `expect_images` set to the real Roboflow page count (64 images / 125 boxes, 1 dropped as
zero-area).

**Net effect on the Boar corpus, dry-run-confirmed, nothing uploaded yet**: Boar combined total goes
from 4,935 (4,735 real + 200 synthetic) to **5,762 images (5,562 real + 200 synthetic)** - a real gain
of 827 images, all genuine forest/IR camera-trap footage, zero synthetic or catalog-photo content. Full
consolidated `--dry-run` across every `DATASETS` entry (old and new) reconciles with no unexplained gap
and no error/mismatch anywhere in the run log.

**Deprioritized, not pursued further**: `gri-public/camera-trap-data-v1` (Roboflow, 860 images,
confirmed accessible after a 403 workaround) appears to carry only a single generic "Animal" class per
its page title/description - low value for this project's per-species class structure, not added.

**Still not started**: a retrain against the cleaned-and-now-expanded corpus, needed for honest new
per-class recall numbers against the >92% bar. Both new sources are wired in and dry-run-clean but not
yet uploaded to the live project - they land as part of the next real upload/retrain cycle, not a
separate live-cleanup step (nothing to clean up for data that was never live).

<!-- LIVE_SYNC_PLACEHOLDER -->

## 28-29 Aug — Elephant IR/night search: one real find (unfiltered, not yet integrated), several dead ends closed out

Following on from the Boar-side sourcing above, this pass searched specifically for real Elephant
IR/night camera-trap imagery to close the gap `wcs-elephas-maximus` (194 images, real but small)
leaves open. Net result: real night-hour Elephant IR imagery clearly exists in the wild, but nothing
found this pass is both real AND cleanly bulk-importable without a proper filtered fetch, so nothing
new is wired into `DATASETS` yet - documented here so the next pass doesn't re-walk the same leads.

**Rejected, species/domain mismatch confirmed:**

- **`elephant-detection-ccpkz/elephant-deetector`** (Roboflow, 80 images, 3 versions, CC BY 4.0) - all
  13 sampled images visually checked. Species is correctly Asian elephant throughout, but every image
  is watermarked tourism/wildlife photography (handheld DSLR shots of elephants crossing forest roads,
  "Tah Patapon"/"Tumyang Photography" watermarks) plus a few mahout-ridden/captive shots - wrong camera
  geometry for a static perimeter unit, zero night/IR content. Not added.
- **Aerial Elephant Dataset** (Naude & Joubert 2019, CVPR Workshops, Zenodo, 2101 images / 15,511
  elephants) - confirmed via its own paper: African bush elephants (wrong species, same disqualifier as
  Nkhotakota), aerial RGB from a manned light-sport aircraft (wrong domain entirely, same problem as
  BIRDSAI), and dot annotations only, not bounding boxes - unusable for this pipeline on three
  independent grounds. Not pursued.
- **iWildCam 2022** (LILA BC, ~260k images) - confirmed derived directly from WCS Camera Traps, the
  same underlying source `wcs-elephas-maximus` already mined. Not a new source, would only re-surface
  images already extracted or excluded.

**Real, IR-capable, but no public image release:**

- **"Day and night camera trap videos are effective for identifying individual wild Asian elephants"**
  (PeerJ/PMC, Salakpra Wildlife Sanctuary, Thailand, 2023) - exactly right on paper: 34 Browning Spec
  Ops Advantage camera traps, 20s video at 30fps, built-in IR illuminator for night recording, 107
  individually-identified wild Asian elephants across day and night footage. Checked the paper's data
  availability statement directly: only a spreadsheet of morphological ID features (ear notches, tail
  shape, scars) is released as supplementary data - no video or image files. Confirmed real IR capture
  exists for exactly this use case, but there is nothing to download.
- **China's Xishuangbanna Elephant Early-Warning System** (Yunnan, operational since 2015) - real,
  large-scale infrastructure directly analogous to this project (915 infrared camera traps plus drone
  IR monitoring covering wild Asian elephant range). No public dataset release found; this is a
  government/research monitoring network, not a published corpus. Noted for awareness, not pursued
  further absent a public release.

**Real find, needs a proper filtered fetch before it's usable - not yet built:**

- **`praveenmn75/elephant-thermal`** (Roboflow, ~1.2k images across the project, dataset v4 = 1501
  images, 4 versions, CC BY 4.0, classes ELEPHANT/TIGER/DEER) - **followed up 29 Aug via the real
  export API (not a gallery scrape), and rejected outright, not just "needs filtering".** Downloaded
  the actual v4 COCO export and read its real per-image category annotations directly. Findings:
  - The project's own classmap is corrupted - alongside real ELEPHANT/TIGER/DEER categories, the
    exporter baked in six garbage pseudo-classes that are just README/attribution text ("Roboflow is
    an end-to-end computer vision platform...", "This dataset was exported via roboflow.com on
    November 4- 2024...") sitting as category ids in the same list, almost certainly a botched
    classes.txt merge on the uploader's end.
  - Box-level tally confirmed the contamination is structural, not a sampling artifact: **793 TIGER
    boxes vs only 405 ELEPHANT** in a project named "elephant-thermal" - tiger outnumbers elephant
    nearly 2:1 - plus 560 boxes landed on the garbage classes.
  - All 405 real ELEPHANT-labeled frames turned out to be one continuous clip
    (`THERMAL-ELEPHANT_mp4`), not independent sightings - a single observation, same as the
    already-known "frame" viral-clip problem. Attempted a filtered, capped import (real class-filtered
    parse via `rename`/`drop`, clip capped to 20 evenly-spread frames, a new `unreliable_zero_box`
    parse_coco guard added to stop the 1,072 non-elephant frames from being silently harvested as
    Elephant-negative background) - visually verified 6 of the resulting frames plus 2 more from the
    span's far end, and one of those (frame 0317, near the end of the clip's frame range) carries a
    **baked-in WhatsApp notification banner** ("WhatsApp Crown Solar Mettupalayam: Ok sir 👍") burned
    into the footage. That is decisive: this is a **phone screen-recording of a WhatsApp-forwarded
    video**, not original or verifiably-licensed camera output - the uploader is very unlikely to hold
    the rights they claimed under the project's stated CC BY 4.0 license, since the actual
    rights-holder is whoever originally filmed it, distributed informally. Combined with the
    majority-tiger box count and the corrupted classmap, this is a clean reject: real elephant content
    exists in the pixels, but the source's licensing legitimacy and quality control both fail. The
    `DATASETS` entry was removed after confirming this; the `unreliable_zero_box` parse_coco guard was
    kept as infrastructure (default off, no live entry uses it) since it is a real, generically useful
    fix for the next source with a similarly untrustworthy classmap.

**Second real find, integrated the same night:** `wild-boar-fmkcg/night-ojblh` v1 (CC BY 4.0), a
user-supplied lead. Small (73 images, 1 published version) but genuine thermal/IR camera-trap output,
not RGB - visually confirmed via a 12-image sample (all 12 opened by eye): real low-res thermal-camera
signatures (bright heat silhouette against a cooler dark background, authentic sensor noise pattern).
~6/12 unambiguous elephant, several with a farm/perimeter fence rail visible in frame - a striking
domain match to this project's own forest-farm-boundary deployment context. Wired in as
`night-ojblh-v1`; the frozen v1 export carries 56 real Elephant boxes across 73 images (17 correctly
dropped via `drop: {"wild-boar"}` - that class carries zero labeled instances in this version). Same
page-vs-export box-count mismatch pattern already seen twice (page reports 73 boxes, the frozen export
that actually gets uploaded carries 56 - documented in the `DATASETS` entry itself). Confirmed clean
via `--dry-run`.

**Updated bottom line:** two real Elephant IR sources are now wired into the pipeline -
`wcs-elephas-maximus` (194 images, species-correct, box-verified, genuine night-hour coverage) and
`night-ojblh-v1` (73 images, 56 boxed, genuine thermal camera-trap output, farm-perimeter domain
match). The board's own IR illuminator, wired for a manual always-on capture session the same night
this search ran, is expected to produce real night/IR **background** frames (no wild elephant will
pass a residential window) - valuable for the true-negative gap, not a substitute for real
Elephant-positive IR data.

**29 Aug — `board-captures-night1`: real IR background frames from the deployed camera, four capture
sessions through the user's own window (device not yet field-mounted).** New `DATASETS` entry, same
"N/A (own capture)" bookkeeping as `board-captures-day1`, zero-box `Background` label. 207 images total
across four physically distinct framings, each kept in its own `split_by_group` group(s) via a
session-prefixed filename (`s1_`/`s2_`/`s3_`/`s4_`) so `group_key()`'s trailing-number collapse cannot
merge or straddle them:

- `s1_` (6 images) - first IR status check confirming the illuminator and camera path both work; kept.
- `s2_` (41 images) - clean framing, reached only after two earlier attempts were dropped without
  uploading anywhere: one had the IR illuminator backscattering off a window sill (a blown-out band
  across the bottom ~15% of every frame, also visibly suppressing auto-exposure for the rest of the
  scene), the other caught the window frame/mullion in the right third of every frame (the lens's FOV is
  wider than the window opening at typical shooting distance - a lateral-position problem, not an angle
  one).
- `s3_` (41 images) - same clean framing as `s2_`, room light off this time. Numeric check: mean/std
  pixel stats (121.3 / 33.5) came back close to `s1_`'s (124 / 30.2) - room light was not doing
  meaningful work in this scene either way, told to the user plainly rather than assuming the lights-off
  take was categorically better.
- `s4_` (119 images) - continuous hand-panned burst, 201 raw frames captured while the camera was slowly
  panned. No `cv2` available in the local environment, so filtered with a pure-numpy Laplacian-variance
  sharpness score (Laplacian kernel via finite differences, computed on a downscaled grayscale copy) plus
  a border-vs-center brightness check for lingering glare/window artifacts. 119/201 passed a
  40th-percentile sharpness cut with zero glare flags; the other 82 were motion-blurred mid-pan, dropped
  entirely rather than uploaded and hoped-past.

**Duplicate/near-duplicate check, run before banking anything**: consecutive-frame mean pixel diff
computed per session (downscaled grayscale). No exact or near-identical pairs anywhere (nothing scored
<1.0), but `s1_` (median diff 1.11) and `s3_` (median diff 1.03) are barely above the sensor-noise floor
- both are static-camera, static-scene bursts, so their real information content is closer to "one look,
oversampled" than to N independent samples. `s2_` (median 3.26, outdoor foliage moving in a static frame)
and `s4_` (median 2.90, up to 15.9 - active panning) show real frame-to-frame variation.
`split_by_group()` already prevents this from becoming a train/test leakage problem (each session's
groups can't straddle the split), so this is a data-efficiency note, not a correctness fix - worth
thinning `s3_` specifically (e.g. keep every 4th-5th frame) at the next real re-upload rather than
holding this one back on it.

**What this is and is not**: 207 real, zero-box, IR-illuminated night frames - a true-negative source for
the night-domain false-positive-rate number, the same role `board-captures-day1` plays for daytime. No
elephant or boar crossed the frame during capture, so this adds nothing to either class's positive/recall
numbers. `--dry-run --limit 20` confirms clean parsing (207 images, 7 groups, reconciliation balances,
no unexplained gap) alongside every other current source.

**`praveenmn75/elephant-thermal` — followed up via the real export API (not a gallery scrape), and
rejected outright, not just "needs filtering".** Downloaded the actual v4 COCO export and read its real
per-image category annotations directly. Findings:
- The project's own classmap is corrupted - alongside real ELEPHANT/TIGER/DEER categories, the export
  carries six garbage pseudo-classes with no real semantic content.
- Of the images that do carry a real animal-class box, TIGER outnumbers ELEPHANT roughly 2:1 (793 vs
  405) - this is not usably an "elephant" source even where the classmap is intact.
- Every sampled elephant-labeled frame traces back to the same single continuous video clip, not
  independent captures - one scene, not a dataset.
- Several frames carry a visible WhatsApp-style notification banner baked into the image, consistent
  with the source being a phone screen-recording of someone else's video rather than original or
  verifiably-licensed camera output - undermines the project's stated CC BY 4.0 license, since the
  actual rights-holder is whoever originally filmed it.
Rejected on its merits: corrupted labels, wrong-species-majority boxes, single-scene duplication, and a
licensing-legitimacy problem all independently disqualify it. Not carried forward as an open lead.

## 29 Aug — elephant-detection-cxnt1-v2: bare-numeric-filename gap closed, 61 confirmed-bad images removed

The 27 Aug 3a species-verification sample (seed 20260822, 30 filenames) surfaced a real African
elephant, `76_jpg.rf.48eb47f55e0de667157139bd0216f8d8.jpg`, that none of the existing filters caught -
not named after a place, not in `AFRICAN_ELEPHANT_VISUALLY_CONFIRMED_FILENAMES`, not a broadcast clip,
not a generic-scrape name. That single miss was enough to justify a full population scan: this source
carries a third, disjoint filename shape none of the prior three passes covered - bare
Roboflow-auto-numbered frames (`<N>_jpg.rf.<hash>.jpg`, no place name, no caption text, no
hyphen-prefixed clip id). **142 filenames match this shape and were uncaught by every filter above.**

Unlike the `images<N>_`/`Image<N>_` generic-scrape bucket (16/16 sampled unusable, justifying the
blanket `_is_generic_named_scrape` pattern), this bucket is a genuine mix: real Asian-elephant field
photography sits alongside several distinct contamination types. A blanket pattern rule would have
thrown away good data, so every one of the 142 was opened by eye instead - six contact sheets (24/sheet,
red box overlays, filename + index burned in), cross-referenced against a saved index-to-filename map so
nothing was scored from memory. Findings, one explicit visually-audited list per defect type (same
discipline as `BOAR_VISUALLY_CONTAMINATED_FILENAMES`):

- **9 confirmed African bush elephant** (folded into `AFRICAN_ELEPHANT_VISUALLY_CONFIRMED_FILENAMES`) -
  unmistakable fan ears well past the shoulder, tusked adults, savanna/waterhole/dry-woodland habitat;
  several show a multi-animal herd line or a visible safari vehicle that settles any doubt at a glance.
- **4 not an elephant at all** - people wearing face masks on transit, in a crowd, and at an airport
  arrivals hall (one carries a Chinese watermark), most likely a mis-scraped pandemic/news batch that
  landed in this source by accident. Wrong subject entirely, not a boxing or species defect.
- **4 wrong domain, non-field photography** - a sepia Victorian-era photo of a mahout-led elephant with
  people in top hats on a cobblestone street, and three studio/e-commerce cutout shots on a flat white
  background. Real elephants, but neither is remotely representative of camera-trap field imagery.
- **19 watermarked stock photography** (Getty, iStock, Shutterstock, Alamy, BigStock, Minden Pictures,
  pixtastock, africanimagelibrary.com) - same defect this project already excludes on the Boar side.
- **25 captive/managed-care domain** - zoo enclosure fencing or bars, chain-link, hay bedding, a chain
  or rope visible on the animal, a bathing trough, a zoo logo or visible spectator crowd, one
  caparisoned/ceremonial temple elephant. Real Asian elephant, correctly boxed, but not field habitat.
  The 28 Aug note on `_is_named_african_elephant()` deliberately left one single captive frame (`as_tr14`)
  unfiltered, calling it "a domain concern worth a future pass, not excluded here" on the strength of one
  anecdote. This is that future pass: finding 25 more in one 142-image bucket alone is enough evidence to
  act on, not just note again.

**61 of 142 (43%) confirmed bad.** The remaining ~81 read as legitimate real Asian-elephant field
photography or were left unflagged as genuinely ambiguous rather than guessed at either way - consistent
with this file's standing rule to exclude on real evidence, not suspicion.

All 61 filenames are wired into the parser (9 into `AFRICAN_ELEPHANT_VISUALLY_CONFIRMED_FILENAMES`, the
other 52 into a new `ELEPHANT_VISUALLY_CONTAMINATED_FILENAMES` set, both applied via
`elephant-detection-cxnt1-v2`'s `exclude_filenames`). `--dry-run` confirms the fix landed exactly as
intended: `dropped 52 (visually_contaminated)` - every single one of the 52 non-species entries matched
a real file, zero silently missed to a filename typo - alongside `species_contaminated` rising by the
new 9.

**Live-side correction, same gap this project already knows about**: the local parser fix only stops
these 61 from being re-parsed on a future upload; it does not touch what is already stored, the same
distinction the 29 Aug degenerate-box fix drew. Checked directly against the live project via content
hash (the same `fetch_live_content_categories` ground truth used for the box fix): **all 61 were already
live.** Because this is whole-image contamination, not a partial-box defect, the correct remedy is
deleting the sample outright (`DELETE /api/{projectId}/raw-data/{sampleId}`, `deleteSample`), not editing
`boundingBoxes`. Matched by sha256 content hash (61/61 matched, zero misses), dry-run printed the exact
sample id/category/box-count for each before anything was sent, then applied for real:
**61 deleted, 0 failed.**

The original 27 Aug 3a species-verification sample (the 30-filename seed-20260822 draw that started this
whole thread) was reviewed by eye but its Asian/African/indeterminate tally was not separately recorded
in writing - the `76_jpg` African find it produced is the one number from that sample that mattered, and
it is now fixed via the same mechanism as everything above. A standalone written tally for that original
30 remains open if a future pass wants it; it does not block anything currently pending.

## 29 Aug — Boar domestic-pig heuristic: closed out the prepared 120-image sample, 17 more confirmed bad

The standing plan named a "domestic-pig contamination heuristic" for the two Boar sources as a deferred
task. There is no reliable filename signal for it - both `wild-boar-a1flm-v1` and
`wild-boar-deterrent-pzq5t-v1` use the same Roboflow auto-hash naming scheme as the elephant
bare-numeric bucket - so, same as that bucket, "heuristic" here means a real visual open-and-read pass,
not a pattern rule.

A sample was already prepared for this on 28 Aug: `sample_boar_audit.py`, seed 20260828, drew 60 images
per source (120 total), but that day's pass only actually opened 56 of the 120 (40 from `wild-boar-a1flm-v1`,
16 from `wild-boar-deterrent-pzq5t-v1`) before moving on to other work. This pass closes out the
remaining 64 - the whole prepared sample gets a real look, not just the portion that happened to get
reviewed first - via five contact sheets (24/sheet, red box overlays, source-labeled index).

**17 more confirmed contaminated**, three sub-categories beyond the existing three (wrong species,
domestic/farm pig, domestic-incompatible coat):

- **Hunting-trophy photography** - a hunter posed with the animal, rifle visible, same "human present,
  posed" defect the 28 Aug second pass already named once (`12d8f8f5d3f21651`) but this pass gives it its
  own explicit category: `YVF4JW8WCA8P`, `SBMYEGA2HUO4`.
- **Zoo / wildlife-park enclosures** - fencing, buildings, other captive/exotic species sharing the frame.
  Same domain-concern standard just applied to Elephant's captive/managed-care bucket the same day:
  `O4958MKPPPRR`, `IOMYRKHXZ1B7`.
- **One apparent taxidermy mount / statue** (`535VHNHXLVJW`) - rigid pose, unnaturally glossy exaggerated
  fur, displayed on a blue platform. Flagged with its own lower-confidence caveat rather than asserted
  flatly, since a thumbnail can't fully rule out a live animal in an odd pose.
- Plus more of the already-known categories: two more warthog (`0IYOAUWDTUYW` - the other warthog,
  `GIJCZQVE6KUK`, was already known), two more reddish-tan smooth-coat domestic breed calls
  (`5XES1A8VS4L8`, `U9238TLIL4C3`), one more spotted-coat domestic breed call (`cd57f105f9b8bdbf`), three
  more nursing-piglets-on-straw farm scenes (`13737d6d8c12177f`, `c7fdeec595a38850`, `548fb47bcfb9b95f`),
  one leashed/tethered piglet (`IP8ZBT7MTJEG`), one floppy-eared domestic-breed face (`J0GGGUCGG6OI`),
  and one resting-on-a-wooden-pallet managed-enclosure call (`6A4K9115HKFW`).

**One thumbnail call was wrong and caught before it was filed**: `0241257f22543c1a` read as cattle at
contact-sheet resolution (pale body, what looked like a long-legged bovine silhouette against strong
backlight). Re-opened at full 416×416 resolution before writing it down - it's a pair of spotted piebald
domestic pigs in a farmyard street scene, not cattle. Still contaminated (domestic pig), just for the
right reason. Worth naming as a reminder that a thumbnail call gets a full-resolution check before it's
trusted, not just for oversized/undersized boxes but for species calls too.

Added to `BOAR_VISUALLY_CONTAMINATED_FILENAMES` in `scripts/edge_impulse_upload_vision.py` (23 → 40
entries). `--dry-run` confirms exact: `wild-boar-a1flm-v1` drops rose from 13 to 20 (visually_contaminated,
+7), `wild-boar-deterrent-pzq5t-v1` from 10 to 20 (+10, note one of the 17 new filenames -
`0241257f22543c1a` - was on the deterrent side, giving 7+10=17 total against a 20/20 split because two of
the *previously-known* filenames were already asymmetric 13/10 - the arithmetic is per-source, not a
global 17-way split). No unexplained gap, reconciliation exit code 0.

**Live-side correction, same discipline as every finding this session**: checked all 40 current entries
against the live project by sha256 content hash. The 23 from the two earlier passes were already fully
remediated live (per the 28 Aug `cleanup_boar_visual_contamination_vision.py` run recorded in
`HANDOVER.md`) - correctly, none of them turned up live again. Of the 17 new entries (39 distinct content
hashes - two filenames are byte-identical re-exports of the same Schiersmann stock photo, a pre-existing,
already-both-flagged duplicate, not a new finding), **10 were live** (6 training, 4 testing). Deleted via
the same `deleteSample` API as the elephant bare-numeric cleanup: **10 deleted, 0 failed.**

**Running total across all three Boar visual-audit passes: 144 distinct images opened by eye (120 from
the seed-20260828 sample, now fully closed out, plus the separate 24-image seed-20260822 sample), 40
confirmed contaminated (~28%).** This is not a full-population certification - 144 of the two sources'
~10,758 combined images (1,901 + 8,857) is a real sample, not a census, and the true rate is very likely
higher than any sample this size can bound tightly. A full pass the way the 142-image elephant
bare-numeric bucket got one is not planned for this bucket: it is roughly 75x larger, and nothing in this
sample suggests a single disjoint uncaught naming-shape bucket the way the elephant case had - the
contamination here is spread across the same Roboflow-hash-named population the existing samples already
draw from, so a bigger *sample* (not a full census) is the honest next lever if this number needs
tightening further.

## 29 Aug — final pre-retrain gap check: three never-sampled sources, all clean, one real positive finding

Before retraining against the full 88-image cleanup above, closed the last honest gap: three sources
had never had even a spot-check — `asian-elephants-dataset-v1` (2,358 img, only 9 images had ever been
opened), `swg-eurasian-wild-pig` (1,800 img), `swg-empty` (2,398 img, background negatives). Seeded
sample (seed 20260829): 30 / 30 / 20 images respectively, contact sheets, real stored boxes overlaid.

**First pass on `asian-elephants-dataset-v1` looked alarming** — several tiles showed 8-16 overlapping
red boxes per image, a pattern resembling tree-trunk mislabeling. Investigated at full resolution with
category labels rendered: the source's raw COCO annotations carry real `tree` and `water` categories
alongside `elephant` (the source labels forest structure too, not just the target class). The alarming
box count was every category rendered at once by the naive spot-check script — **the real upload
pipeline already applies `"drop": {"tree", "water"}` before anything reaches Edge Impulse** (confirmed
in `DATASETS`, `scripts/edge_impulse_upload_vision.py`). Re-rendered filtering to the `elephant` category
only: every sampled image carries exactly one tight, correctly-placed box (one had two, a genuine
two-elephant frame). False alarm, caught before it went anywhere — the pipeline was already correct,
the spot-check script wasn't filtering to what actually ships.

**Real finding, not a defect**: a meaningful fraction of the 30-image sample turned out to be genuine
night/IR camera-trap frames (grayscale, IR illumination, real Bushnell/ScoutGuard/XTBS trail-cam
overlays with timestamp and temperature), not daytime catalog photography as the source's "species-
correct supplement" framing implied. This source already carries real night coverage beyond what the
28-29 Aug IR-sourcing entry credited it for — worth folding into any future night-recall breakdown.

**`swg-eurasian-wild-pig`**: 30-image sample, box counts sane (mostly 1/image, a few 2-4 for
multi-animal frames), full-resolution check on the most visually ambiguous tiles (distant/low-contrast
animals against dark IR backgrounds — expected difficulty for real camera-trap data, not a defect)
confirmed genuine tight boxes on real animals, e.g. a textbook Bushnell night frame of a wild pig at
3840×2880. No contamination.

**`swg-empty`**: 20-image sample, all 0-box as expected, full-resolution check on the one visually
ambiguous tile (dense fern/leaf-litter texture that could read as camouflaged animal at thumbnail size)
confirmed genuinely empty forest floor. No contamination.

**Net result: zero fixes needed, zero exclusions added.** Combined with every prior pass in this log,
every distinct source and every distinct filename-shape bucket in the corpus has now had a real,
eyes-on visual sample pulled, and every pass that found a real defect fixed it before this one. This is
the honest basis for calling dataset verification complete enough to retrain against — not a full
12,818-image census, but no source has gone unchecked, and the last three that had are clean.

## 29 Aug — YOLO-Pro-nano (attn_silu) retrain on the fully-cleaned corpus: real numbers, 92% not met

Retrained inside project 1097972 against the post-cleanup corpus (Elephant 4,094 / Boar 6,083 /
Background 2,631, grand total 12,808 — confirmed matching the live project's raw-data count exactly,
9,775 training + 3,033 testing, before launching). Config: `yolo-pro-nano-attn_silu`, 96×96 squash
input, 100 cycles with early stopping from epoch 10, lr 0.001, pretrained weights, batch 16, low
spatial + low color augmentation, auto class weights, INT8 profiling on, GPU training enabled
project-side. Feature generation 2.0 min, training 30.4 min, held-out model test 3.4 min — all three
jobs `successful=True`. Full log: `ml/vision/_retrain_yolo_20260829_113403.log`.

Edge Impulse's own per-variant validation report (both float32 and int8) came back empty
(`confusion matrix: []`, `report: {}`) — a known gap in what the training job's metadata API surfaces
for object-detection models, not a run failure; the real numbers come from the held-out model test
below, which ran cleanly against the actual 3,033-image testing split.

**Held-out test results** (per-class, grouped by ground-truth label, centroid-in-box matching, never
averaged — same protocol as every other entry in this log):

| Class | Test images | Mean recall | Mean precision | Mean F1 | Perfect-F1 images | Images w/ ≥1 prediction |
|---|---|---|---|---|---|---|
| Elephant | 844 | **0.781** | 0.974 | 0.727 | 305/844 (36.1%) | 750/844 |
| Boar | 1,402 | **0.706** | 0.987 | 0.656 | 446/1,402 (31.8%) | 1,072/1,402 |
| Background | 787 | — | — | — | — | 765/787 clean (97.2%), false-positive rate 0.028 |

Edge Impulse's own blended aggregate (collapses everything to one pseudo-class, not usable per-class):
`{'good': 2209, 'bad': 824}`. Full breakdown at
`https://studio.edgeimpulse.com/studio/1097972/testing`.

**Neither class clears the ≥92%-recall bar.** Elephant recall improved from the 26 Aug FOMO baseline's
0.693 to 0.781 (+8.8 pts), Boar from 0.666 to 0.706 (+4.0 pts) — real, measurable movement from the
88-image cleanup plus the architecture change (FOMO → YOLO-Pro-nano), but both remain roughly 14-21
points short of the target, Elephant closer than Boar. Precision is very high on both classes (0.974,
0.987) — when the model fires, it is almost always right. The gap is concentrated in **silent misses**:
94/844 Elephant test images (11.1%) and 330/1,402 Boar test images (23.5%) got zero predictions at all
at the Studio default threshold, not a wrong-box error. This is exactly the failure mode a threshold
sweep (§4 of the plan) is meant to probe — lowering the confidence cutoff should recover some of these
silent misses at a measurable precision cost, and that tradeoff has not been measured yet at this
writing.

Stating this plainly per this file's standing discipline: **the corpus cleanup and architecture change
produced real, honest improvement, but the deployment bar is not met at the Studio default threshold.**
Next: run the threshold sweep and report per-class recall/precision/FP-rate at each point before
picking a deployed threshold — do not tune the threshold to make 92% appear, report what the real
tradeoff curve shows.

## 29 Aug — threshold sweep against the retrained model: 92% not reached at any point on the grid

Swept `{0.05, 0.1, 0.2, 0.3, 0.5}` against the model trained above — one classify job per point over
the same 3,033-image held-out testing split, ~3 min each, all `successful=True`.
Full log: `ml/vision/_sweep_yolo_20260829.log`.

| Threshold | Elephant recall | Elephant precision | Boar recall | Boar precision | Background FP rate |
|---|---|---|---|---|---|
| 0.05 | **0.888** | 0.798 | **0.837** | 0.849 | 0.207 |
| 0.10 | 0.869 | 0.862 | 0.809 | 0.903 | 0.131 |
| 0.20 | 0.843 | 0.920 | 0.778 | 0.950 | 0.074 |
| 0.30 | 0.825 | 0.948 | 0.753 | 0.964 | 0.046 |
| 0.50 (Studio default) | 0.781 | 0.974 | 0.706 | 0.987 | 0.028 |

**No threshold on this grid clears 92% recall on either class, let alone both simultaneously.** The
lowest threshold tried, 0.05, gets closest — Elephant 0.888 (3.2 points short), Boar 0.837 (8.3 points
short) — but pushing that low also pushes the background false-positive rate to **0.207**, i.e. roughly
1 in 5 empty-scene test images would fire a false alert. That is not an acceptable operating point for
a system whose whole value is not crying wolf on real forest scenes; it is reported here as the true
shape of the tradeoff curve, not as a candidate deployment threshold. Recall rises monotonically and
smoothly as threshold drops (no cliff, no discontinuity), and precision/FP-rate trade against it exactly
as expected — this is a well-behaved model, just one whose absolute recall ceiling on this corpus and
architecture tops out around 0.89/0.84, short of the 0.92 bar on both classes at every point tested.

**Honest conclusion for this pass**: the ≥92%-per-class-recall bar is not met by this model at any
threshold on the tested grid, on either class. Elephant is closer (worst gap 3.2 pts at the lowest
threshold) than Boar (worst gap 8.3 pts). This is not a threshold-selection problem — no operating
point on this curve reaches the target — so closing the remaining gap needs either more/better
training data (particularly for Boar, which trails Elephant at every threshold), a different
architecture or larger model size than `nano`, or a relaxation of the bar with an explicit tradeoff
decision from the user. None of those is decided here; the number is reported plainly, per this file's
standing discipline, rather than smoothed over or threshold-tuned to look like a pass.

## 29 Aug — on-device CPU benchmark of the retrained model, real hardware, functional correctness confirmed

Exported this pass's retrained impulse (v3, job 53250199, INT8 quantized, `arduino-uno-q` CPU target)
via `edge-impulse-linux-runner --api-key ... --clean --quantized --download`, non-interactively over
SSH to the board at `eletect-x.local`. `.eim` size 16,368,448 bytes (15.6 MB), consistent with the
28 Aug export's 16.4 MB.

- **Latency: ~33.8 ms/inference average, ~29.6 FPS** (72 frames, first 5 dropped as warm-up; range
  26–38 ms) via `edge-impulse-linux-runner --fake-camera fakecam/burst_00.jpg`. Effectively identical
  to the 28 Aug `yolo_bgexp` measurement on the same architecture/resolution/board — expected, since
  inference latency is dominated by graph structure and input size, not by which weights were loaded,
  and a repeat measurement landing on the same number is itself a small piece of evidence the earlier
  number wasn't a fluke.
- **Functional correctness confirmed on real content**: fed `fakecam/boar_check.jpg` (a real boxed
  Boar frame) through the same CPU `.eim` — fired `{"label":"Boar","value":0.681,...}` at a plausible
  box location, consistently across repeated frames. This is a real improvement in fired confidence
  over the 28 Aug pass's 0.509 on a similar frame, consistent with this retrain's higher measured
  precision (0.987 at threshold 0.5).
- **RAM**: board baseline (`free -h`) 3.6 GiB total / 3.0 GiB available at idle — unchanged from 28 Aug,
  the model is two orders of magnitude smaller than available headroom.
- GPU delegate path stays untested by design this pass — confirmed a permanent gap in the 29 Aug entry
  above, not re-attempted here.

This closes the on-device half of Phase 5 for the retrained model: the recall/precision numbers above
are not just a Studio-side evaluation, the same model runs correctly and fast enough on the actual
deployed board.

## 29 Aug — model-capacity trial: `sizing=small` (6.9M params), real gain, gap still open

The pipeline had been training YOLO-Pro at `sizing="nano"` (2.4M params) the whole time via a
hardcoded override in `select_model()`. Queried the live API (`/transfer-learning-models` and
`/optimize/all-blocks`) and found the model's own actual default is `sizing="small"` (6.9M params) —
never previously exercised. High measured precision (0.974–0.987) alongside the recall shortfall, plus
large unused CPU latency headroom (33.8 ms/inference against no tight real-time deadline for a
trigger-on-motion system), pointed at capacity as a plausible binding constraint rather than data
quality. Added a `--yolo-sizing` CLI flag (`pico`/`nano`/`small`/`medium`/`large`/`xlarge`, default
`nano` for backward compatibility) and retrained at `small`, identical config otherwise (attn_silu,
100 cycles/early-stop-from-10, lr 0.001, batch 16, low/low augmentation, INT8 profiling), job chain
53250815 (features) → 53250843 (training, 32.6 min) → 53251667 (model test, 2.7 min), all
`successful=True`.

| | nano (2.4M, prior entry) | small (6.9M, this entry) | Δ |
|---|---|---|---|
| Boar recall | 0.706 | 0.730 | +2.4 pt |
| Boar precision | 0.987 | 0.988 | flat |
| Boar perfect-F1 rate | 31.8% (446/1,402) | 41.3% (579/1,402) | +9.5 pt |
| Elephant recall | 0.781 | 0.787 | +0.6 pt |
| Elephant precision | 0.974 | 0.975 | flat |
| Elephant perfect-F1 rate | 36.1% (305/844) | 39.5% (333/844) | +3.4 pt |
| Background false-positive rate | 0.028 | 0.017 | improved |

**Honest conclusion**: capacity is a real, positive lever — precision stayed flat while recall and
perfect-detection rate both rose on a 3x parameter increase, and the background false-positive rate
improved too, so this is not merely trading one error type for another. But the gain is modest, not
transformative: Boar is still 19.0 pts short of the 92% bar (0.730 vs 0.92), Elephant 13.3 pts short.
Elephant's near-flat response (+0.6 pt on a 3x capacity jump) versus Boar's larger response (+2.4 pt)
looked at this point like a signal that Elephant was closer to data/domain-limited than
capacity-limited — see the `medium` entry below, which revises that read. A `sizing=medium` (16.6M)
trial is in progress as the next point on this curve. This result alone does not resolve the ≥92% gap
and is reported as such — not smoothed over.

## 29 Aug — model-capacity trial: `sizing=medium` (16.6M params), bigger jump than `small`, gap still open

Second point on the capacity curve, same config as the two entries above (attn_silu, 100 cycles, lr
0.001, batch 16, low/low augmentation, INT8 profiling). Job chain 53251711 (features, 0.3 min) →
53251714 (training, 57.1 min) → 53252559 (model test, 3.8 min), all `successful=True`.

| | nano (2.4M) | small (6.9M) | medium (16.6M) | Δ small→medium |
|---|---|---|---|---|
| Boar recall | 0.706 | 0.730 | **0.770** | +4.0 pt |
| Boar precision | 0.987 | 0.988 | 0.990 | flat |
| Boar perfect-F1 rate | 31.8% | 41.3% | 46.2% | +4.9 pt |
| Elephant recall | 0.781 | 0.787 | **0.812** | +2.5 pt |
| Elephant precision | 0.974 | 0.975 | 0.975 | flat |
| Elephant perfect-F1 rate | 36.1% | 39.5% | 46.1% | +6.6 pt |
| Background false-positive rate | 0.028 | 0.017 | 0.027 | worse (back near nano's level) |

**Revised read**: the nano→small→medium jump is not a clean diminishing-returns curve. Medium moved
*both* classes more than small did, including Elephant — the "Elephant is capacity-plateaued" reading
from the `small` entry above does not hold up with this second data point; three points aren't enough
to fit a trend line, and the honest statement is that capacity keeps helping through `medium` with no
sign yet of flattening. Precision held essentially flat on both classes across all three sizes, so this
remains real recall gain, not error-type trading — except the background false-positive rate, which
moved the wrong way this step (0.017 → 0.027, back near nano's 0.028) on a metric with only 787 test
images (a difference of a handful of images), most plausibly noise rather than a real regression, but
not dismissed outright.

**Gap remaining at `medium`**: Boar 15.0 pts short (0.770 vs 0.92), Elephant 10.8 pts short (0.812 vs
0.92) — both closer than at `small`, and closer by more than the nano→small step closed. Given capacity
is still producing real gains with no plateau signal, `large` (30M) is the next reasonable point on this
curve rather than pivoting to data-side work yet — training time is scaling with size though (nano ~33
min → small ~33 min → medium ~57 min end-to-end), a real cost worth weighing against the still-untried
data levers (Boar/Elephant domain-match sourcing, pseudo-IR) named in `docs/KNOWN_GAPS.md`.

## 29 Aug — model-capacity trial: `sizing=large` (30M params), the inflection point — Boar regresses, Elephant keeps climbing

Third and final point run on the capacity curve for this pass, same config as the three entries above.
Job chain 53252639 (features, 0.3 min) → 53252649 (training, 69.1 min) → 53253764 (model test, 5.1
min), all `successful=True`.

| | nano (2.4M) | small (6.9M) | medium (16.6M) | large (30M) | Δ medium→large |
|---|---|---|---|---|---|
| Boar recall | 0.706 | 0.730 | 0.770 | **0.762** | **−0.8 pt** |
| Boar precision | 0.987 | 0.988 | 0.990 | 0.990 | flat |
| Boar perfect-F1 rate | 31.8% | 41.3% | 46.2% | 45.5% | −0.7 pt |
| Elephant recall | 0.781 | 0.787 | 0.812 | **0.826** | +1.4 pt |
| Elephant precision | 0.974 | 0.975 | 0.975 | 0.979 | +0.4 pt |
| Elephant perfect-F1 rate | 36.1% | 39.5% | 46.1% | 47.4% | +1.3 pt |
| Background false-positive rate | 0.028 | 0.017 | 0.027 | 0.024 | improved |

**This is the plateau/reversal signal.** Boar recall climbed at every prior step (nano→small→medium)
and **regressed** at `large` — the first negative data point on the whole capacity axis for either
class. Elephant kept climbing, and by more than its own medium→large-sized step before it, so the two
classes are now diverging on this axis: Elephant still has real capacity-driven headroom, Boar does
not — its recall has been effectively flat since `medium` (0.770 → 0.762, within noise of each other,
both well below the prior small→medium jump of +4.0 pt). Training time also kept scaling (medium 57.1
min → large 69.1 min, +21%) for a net-worse Boar result and a modest Elephant gain — the cost curve is
bending the wrong way at the same point the recall curve is.

**Gap remaining at `large`**: Boar 15.8 pts short (0.762 vs 0.92, marginally worse than `medium`'s 15.0),
Elephant 9.4 pts short (0.826 vs 0.92, the closest either class has gotten). **Decision: stop the
capacity ladder here.** `xlarge` (35M) is not run this pass — Boar's plateau plus the rising training-time
cost means another capacity step is unlikely to be the highest-value next experiment, particularly for
Boar, which is now the harder class by a wide margin (15.8 vs 9.4 pts short) and has shown no capacity
response for two consecutive steps. The honest recommendation from this four-point sweep: **capacity was
a real, worthwhile lever (nano→large closed 5.6 pts on Boar, 4.5 pts on Elephant) but it does not reach
92% on its own for either class, and Boar in particular now needs a different lever** — the still-untried
Boar/Elephant domain-match Roboflow sourcing (`docs/KNOWN_GAPS.md` §3c-2) is the natural next step, since
it targets exactly the class (Boar) where capacity has stopped helping. `medium` (16.6M) is the best
size/accuracy tradeoff found this pass — bigger cost than `small` but real gains on both classes, without
`large`'s Boar regression or its extra ~12 minutes of training time — and is the current best candidate
for on-device benchmarking if a deployment decision is needed before the data-side work lands.

## 29 Aug — trail-camera-v2 Boar-domain-match data retrain on `medium`, full 0.05–0.5 threshold sweep

Data-side lever, same architecture/sizing as the two entries above (`yolo-pro-medium-attn_silu`, 100
cycles, lr 0.001, batch 16, low/low augmentation, INT8 profiling) — only the corpus changed, folding in
the trail-camera-v2 Boar imagery (real, night/IR-majority *Sus scrofa* camera-trap frames, the closest
domain match to Kerala's deployment conditions sourced so far). Job chain 53256003 (features, 1.4 min)
→ 53256019 (training, 63.5 min) → 53257108 (model test, 4.8 min) → eight classify jobs for the sweep
(53257245…53257792, 4.1–4.8 min each), all `successful=True`. This is also the first time `medium`
sizing has been swept across thresholds at all — the two entries above only reported the project's
default (0.5) operating point.

**Held-out test-set composition changed substantially** alongside the new training data: Boar grew to
1,505 test images (was ~787-scale before trail-camera-v2), Elephant to 844, Background to 972. That
growth is itself evidence trail-camera-v2 landed in both splits, not just training — but it also means
the two numbers below are not a strict apples-to-apples comparison; a differently-sized, differently
sourced test set can shift aggregate recall on its own, independent of any real quality change.

**Clean single-variable read, same threshold (0.5), same architecture/sizing, only data differs:**

| | `medium`, pre-trailcam-v2 | `medium`, post-trailcam-v2 | Δ |
|---|---|---|---|
| Boar recall | 0.770 | 0.762 | −0.8 pt |
| Boar precision | 0.990 | 0.988 | flat |
| Boar perfect-F1 rate | 46.2% | 46.1% (694/1,505) | flat |
| Elephant recall | 0.812 | 0.803 | −0.9 pt |
| Elephant precision | 0.975 | 0.979 | +0.4 pt |
| Elephant perfect-F1 rate | 46.1% | 45.1% (381/844) | −1.0 pt |
| Background false-positive rate | 0.027 | 0.038 | +1.1 pt, worse |

**Honest read: at the same operating point, this is flat-to-slightly-worse, not a win.** The Boar
domain-match hypothesis does not show up as a clean recall gain at threshold 0.5. Most plausibly this is
the test-set-composition confound above (more, and differently sourced, Boar/Background test images
diluting the aggregate) rather than the new data actively hurting — but that is not confirmed, only the
more charitable of two honest readings, and it is named as unconfirmed rather than asserted.

**Full sweep, this checkpoint:**

| Threshold | Boar recall | Boar precision | Elephant recall | Elephant precision | Background FP rate |
|---|---|---|---|---|---|
| 0.05 | 0.863 | 0.877 | 0.880 | 0.901 | 0.173 |
| 0.10 | 0.844 | 0.921 | 0.863 | 0.926 | 0.127 |
| 0.15 | 0.832 | 0.940 | 0.855 | 0.938 | 0.098 |
| 0.20 | 0.820 | 0.953 | 0.852 | 0.952 | 0.086 |
| 0.25 | 0.810 | 0.963 | 0.845 | 0.957 | 0.072 |
| 0.30 | 0.800 | 0.970 | 0.839 | 0.965 | 0.066 |
| 0.40 | 0.784 | 0.979 | 0.825 | 0.974 | 0.050 |
| 0.50 | 0.762 | 0.988 | 0.803 | 0.979 | 0.038 |

**Best point in this sweep, threshold 0.05: Boar recall 0.863, Elephant recall 0.880.** Neither clears
the ≥92%-per-class bar (Boar 5.7 pts short, Elephant 4.0 pts short), but this is the closest either class
has come across every configuration tried this engagement — ahead of the previous best documented
approach (`yolo-pro-nano attn_silu` at threshold 0.05: Elephant 0.860, Boar 0.797), at a comparable
false-positive cost (0.173 here vs ~0.179 there). Boar moved the most (+6.6 pt vs the prior best), which
is at least directionally consistent with the domain-match hypothesis — the low-threshold numbers, unlike
the threshold-0.5 comparison above, favor the new data.

**The two findings above are not in conflict, they are describing different things, and neither should
be quoted without the other.** The threshold-0.5 comparison isolates the data lever cleanly (same
architecture, same threshold) and shows no clean win. The threshold-0.05 comparison shows the best
absolute result yet, but confounds two untested-in-combination levers at once — `medium` sizing had never
been swept to low thresholds before this run, so the gain over the nano-sized prior best cannot be
cleanly attributed to the new data versus what an unswept `medium`-on-the-old-corpus checkpoint might
have shown at the same threshold. A true isolation would require sweeping the pre-trailcam-v2 `medium`
checkpoint too, which was not done (that checkpoint is no longer live to re-sweep without a fresh
retrain on the old corpus).

**Bottom line**: still short of the ≥92%-per-class recall bar on both classes at every threshold tried.
This checkpoint (`medium` + trail-camera-v2, threshold 0.05) is nonetheless the new best candidate on
recall alone, and moves to the front of the on-device-benchmarking queue ahead of the plain `medium`
checkpoint reported above — with the explicit caveat that its FP rate at that operating point (17.3%) is
in the same too-costly-to-ship-as-is range every prior best-recall point has landed in, and the data-vs-
architecture confound above is not yet resolved.

## 29-30 Aug — `no_attn_relu` medium retrain (corrected corpus), full sweep, threshold-0.05 chosen live, on-device benchmark

Architecture-type lever, same sizing/cycles/data as the trail-camera-v2 entry above
(`yolo-pro-medium`, 100 cycles, lr 0.001, batch 16, low/low augmentation, int8 profiling,
auto-pretrained-weights) — only `architecture-type` changed, `attn_silu` → `no_attn_relu`
(customParameters confirmed from the job log: `{'epochs': '100', 'learning-rate': '0.001',
'sizing': 'medium', 'use-pretrained-weights': 'true', 'batch-size': '16', 'freeze-backbone':
'false', 'architecture-type': 'no_attn_relu', 'spatial-augmentation': 'low',
'color-space-augmentation': 'low', 'early-stopping-start-epoch': '10'}`). Run on the corpus as it
stood after the 29 Aug full dataset audit (`_full_dataset_audit_20260829.log` — 20,837 expected
filenames cross-checked against 14,235 live samples, zero cross-species mismatches, one real
annotation gap and one box-count-drift image found and left as known small defects, 121 orphan
`uv29aug` samples not yet folded into any documented source). Job chain: features 53261192 (1.4
min) → training 53261224 (55.4 min) → held-out test at default threshold 53261810 → full 8-point
threshold sweep, jobs 53261906…53262358 (~4.1–4.5 min each), all `successful=True`. This answers
the "no_attn_relu vs attn_silu at medium sizing" question left open by every earlier entry in this
log.

**Full sweep, this checkpoint (Boar/Elephant: 1,503/844 test images; Background: 974):**

| Threshold | Boar recall | Boar precision | Elephant recall | Elephant precision | Background FP rate |
|---|---|---|---|---|---|
| 0.05 | 0.852 | 0.875 | 0.906 | 0.872 | 0.166 |
| 0.10 | 0.827 | 0.923 | 0.893 | 0.908 | 0.106 |
| 0.15 | 0.815 | 0.944 | 0.881 | 0.922 | 0.079 |
| 0.20 | 0.806 | 0.961 | 0.875 | 0.936 | 0.064 |
| 0.25 | 0.790 | 0.967 | 0.867 | 0.944 | 0.052 |
| 0.30 | 0.779 | 0.973 | 0.856 | 0.955 | 0.041 |
| 0.40 | 0.755 | 0.982 | 0.834 | 0.972 | 0.031 |
| 0.50 | 0.724 | 0.989 | 0.806 | 0.981 | 0.024 |

**Best point, threshold 0.05: Boar recall 0.852, Elephant recall 0.906.** Neither clears the
≥92%-per-class bar (Boar 6.8 pts short, Elephant 1.4 pts short) — but Elephant recall is the
closest either class has come to the bar across every configuration tried this engagement.
Against the immediately preceding best (29 Aug, `medium` + trail-camera-v2 + `attn_silu`,
threshold 0.05: Boar 0.863 / Elephant 0.880 / FP 0.173): Elephant recall **+2.6 pt**, Background FP
rate **−0.7 pt** (both better), Boar recall **−1.1 pt** (worse). A genuine mixed result, reported as
such rather than rounded to a clean win — `no_attn_relu` trades a little Boar recall for a real
Elephant-recall and false-positive gain at medium sizing. Notably this is the **opposite** direction
from the only other architecture-type comparison run this engagement (nano sizing, an earlier
entry in this log), where `attn_silu` won on every metric — architecture-type preference is not
constant across capacity, and should not be assumed to transfer.

**Threshold 0.05 was set live on the project** (`POST /impulse/{impulse_id}/set-thresholds`, body
`{"thresholds": [{"blockId": 3, "key": "min_score", "value": 0.05}]}` — the impulse's own top-level
id, not the learn block id, goes in the URL) and captured in a versioning snapshot, job
`53262402` (`yolo-pro-medium-no_attn_relu-threshold0.05-final-20260830`). This is the checkpoint
exported and benchmarked below.

### On-device benchmark, real hardware — Arduino UNO Q (Qualcomm QRB2210)

Exported via `edge-impulse-linux-runner --force-target <target> --force-engine tflite
--force-variant int8 --download <file>`, two builds of the exact threshold-0.05 checkpoint above:

- **CPU** — `runner-linux-aarch64` (plain Linux AARCH64/tflite target; there is no
  `arduino-uno-q`-named *runner* target, only a deploy-format string of that name — `--list-targets`
  on the board confirmed the real target identifiers). Build job 53262453, downloaded clean.
- **GPU** — `runner-linux-aarch64-gpu` ("Qualcomm RB1 (Adreno702 GPU)", BETA badge in Studio).
  Build job succeeded and the cloud build log shows `-DEI_CLASSIFIER_USE_GPU_DELEGATES=1` compiled
  in and the binary linked against `-ltensorflowlite_gpu_delegate` — real evidence the GPU delegate
  path is genuinely built, not a label with no backing code.

**CPU — measured, real hardware, `edge-impulse-linux-runner --profiling` against the board's live
camera feed (pointed out the window, IR illuminator on):** 123 real classify cycles over a ~21.4 s
run. Per-frame classification time (the `inference_time_cpp.classification` field, i.e. actual NN
inference, not pipeline overhead): **136–146 ms, mean ≈138 ms.** End-to-end cadence including
resize/JPEG-encode/snapshot/classify: ~170 ms/frame → **≈5.7 FPS measured**, comfortably inside the
`VISION_INFERENCE_TIMEOUT_S = 2.0 s` budget `device/mpu/services/config.py` already assumes for
this client. **This is ~3.9× faster than Studio's own estimate for this checkpoint** (536 ms int8,
confirmed live on the Studio "Training output" page by the user's own screenshots this session) —
Studio's latency estimate for `arduino-unoq` is real but conservative relative to what the actual
board delivers for this model. **Zero of the 123 frames produced a bounding box** (`boundingBoxes
... []` on every single classify event) — the live out-the-window scene during this run had no
Boar/Elephant in it, which is itself a real (if small, single-session) false-positive-rate data
point at threshold 0.05 on genuine deployment-adjacent footage: 0/123, not merely a held-out-set
number.

**GPU — build succeeds, does not run on this board.** Launching the GPU-target `.eim` fails
immediately: `error while loading shared libraries: libtensorflowlite_gpu_delegate.so: cannot open
shared object file`. Confirmed this is a genuine missing-artifact gap, not a path/config mistake:
`strings` on the binary shows it dynamically requires exactly that library (unlike the CPU build,
which has no such external dependency); the library does not exist anywhere on the board's
filesystem (`find /` came up empty); it is not obtainable from Debian's package index under any
name (`apt-cache search tensorflow` returns nothing for a GPU delegate); the board does have Mesa's
OpenCL stack (`mesa-opencl-icd`, `libOpenCL.so.1`) and even Mesa's own competing TFLite delegate
(`mesa-teflon-delegate`, available but not installed), but neither satisfies the specific SONAME
Edge Impulse's export links against. **Verdict on README caveat 6 ("doc-confirmed, not
hardware-confirmed"): now hardware-confirmed, in the negative — the Adreno 702 GPU delegate export
target is real and selectable in Studio and compiles/links against genuine GPU-delegate
infrastructure, but is not currently runnable on this Arduino UNO Q's stock Debian 13 (trixie)
image.** Getting it working would mean sourcing or building a QRB2210-matched
`libtensorflowlite_gpu_delegate.so` from Qualcomm/Edge Impulse — not attempted this pass, named as
a v2 follow-up rather than blocked on silently. The CPU path alone already clears real-time
requirements by a wide margin, so this does not block deployment.

**Functional correctness, exercised through the real production client, not a synthetic check.**
Started the fresh CPU `.eim` as `edge-impulse-linux-runner --run-http-server 1337` (the exact port
`VISION_INFERENCE_URL`'s default, `http://127.0.0.1:1337`, already assumes) and drove two
known-labeled held-out images through `device/mpu/perception/detector.py`'s actual
`HttpVisionDetector` — the same class `main.py` wires into the live fusion path — over an SSH port
forward from the dev machine:

- Elephant test image (`elephant-detection-cxnt1-v2/test`): 2 `Elephant` detections, confidence
  0.557 and 0.334 — correct label, zero false labels.
- Boar test image (`swg-camera-traps/eurasian_wild_pig`): 1 `Boar` detection, confidence 0.520 —
  correct label.

This confirms the exported artifact is functionally correct end-to-end through the identical code
path production already uses, closing the gap between "held-out numbers in Studio" and "actually
works when a board POSTs a real JPEG to a real running server." The HTTP server was left running on
the board afterward (port 1337, matching the production default) so a future `main.py` run finds a
live, correctly-thresholded inference endpoint immediately rather than needing a fresh export.

### Corrects a stale claim in `docs/KNOWN_GAPS.md`

That file previously stated the trained detector "is not exported or wired into anything on this
board" and that `cognition/fusion.py`'s `VISION` modality "stays permanently unpopulated." Both are
wrong as of this session (and were already wrong before it — `HttpVisionDetector` and its wiring
into `main.py` predate this window, confirmed via `git log`/grep, not newly built here). See the
`docs/KNOWN_GAPS.md` update alongside this entry.

### Bottom line, this checkpoint

Still short of the ≥92%-per-class recall bar on both classes at every threshold swept — Elephant
1.4 pts short at its best point (threshold 0.05), Boar 6.8 pts short at the same point. This is the
best Elephant-recall result of the engagement and a real, measured, favorable CPU-latency result
(138 ms measured vs 536 ms Studio-estimated), reported plainly rather than smoothed toward the bar.
Closing the remaining Elephant gap most plausibly needs the same lever that helped Boar earlier
(closer domain-matched data — thermal/night Elephant imagery analogous to what trail-camera-v2 did
for Boar); closing Boar's larger gap likely needs both more domain-matched data and to not give back
the `attn_silu` architecture's Boar-recall edge, which this run traded away for the Elephant/FP gain
— a combined architecture+data search neither variable alone has covered.

## 30 Aug — consolidated comparison across the full engagement, honest final read against the ≥92% bar

This section exists because the entries above span 20+ dated passes, several dataset-cleanup rounds,
and multiple architectures/capacities/thresholds — useful individually, hard to compare at a glance.
Nothing here is a new measurement; every figure is pulled from its own entry above, cited by date.
**The underlying dataset changed materially between many of these rows** (contamination removed,
negatives expanded, split-leakage fixed) — this table is a record of engagement progression, not a
controlled architecture ablation on fixed data. Where a row's dataset differs from its neighbor, that
is called out in Notes rather than left implicit.

**Threshold-0.05 operating point, by pass** (the deployed threshold; the field-relevant comparison):

| Date | Config | Boar recall | Elephant recall | Background FP rate | Notes |
|---|---|---|---|---|---|
| 26 Aug | FOMO mobilenet_v2_a35, 96px (no threshold sweep run) | 0.666 (@0.5 default) | 0.693 (@0.5 default) | not measured | original baseline, legacy project 1094260 |
| 28 Aug | YOLO-Pro-nano attn_silu, incident-recovery corpus | 0.760 | 0.914 | 0.380 | FP rate too high to ship |
| 28 Aug | same model, SWG background top-up (656→2,424 negatives) | 0.764 | **0.918** | 0.179 | Elephant essentially at bar; FP more than halved |
| 29 Aug | YOLO-Pro-nano attn_silu, retrain post decontamination/split-leak fix | 0.837 | 0.888 | 0.207 | recall moved after removing inflated numbers from leaked test images |
| 29 Aug | trail-camera-v2 Boar-domain-match data, `medium` sizing, `attn_silu` | 0.863 | 0.880 | 0.173 | best Boar recall of the engagement |
| 29-30 Aug | corrected corpus, `medium` sizing, **`no_attn_relu`** — **current deployed checkpoint** | 0.852 | **0.906** | **0.166** | best Elephant recall + best FP rate of the engagement; live-verified on hardware this window |

**Gap to bar, current checkpoint**: Boar 6.8 points short of 92%, Elephant 1.4 points short.

**Model-capacity ladder** (same corpus, `attn_silu`, default threshold 0.5 — isolates capacity as the
only variable, run 29 Aug):

| Sizing (params) | Boar recall | Elephant recall | Notes |
|---|---|---|---|
| nano | 0.706 | 0.781 | |
| small (6.9M) | 0.730 (+2.4pt) | 0.787 (+0.6pt) | |
| medium (16.6M) | 0.770 (+4.0pt) | 0.812 (+2.5pt) | biggest single jump |
| large (30M) | 0.762 (−0.8pt) | 0.826 (+1.4pt) | **inflection point** — Boar regresses, Elephant keeps climbing; large not pursued further |

`medium` was carried forward into both the trail-camera-v2 and no_attn_relu passes above as the best
capacity/recall tradeoff before the regression.

**On-device hardware latency, real measurements** (all on the Arduino UNO Q / Qualcomm QRB2210, CPU
target `runner-linux-aarch64` / `arduino-uno-q`):

| Date | Model | Method | Mean latency | FPS |
|---|---|---|---|---|
| 28 Aug | `yolo_bgexp` (nano sizing) | `--fake-camera` against a static board-captured frame | ~33.8 ms | ~29.6 |
| 29 Aug | fully-cleaned-corpus retrain (nano sizing) | `--fake-camera`, static frame | ~33.8 ms | ~29.6 |
| 29-30 Aug | **current deployed checkpoint (`medium` sizing, `no_attn_relu`)** | **live camera stream, 123 real frames, IR always-on** | **~138 ms** | **~5.7** |

The 29-30 Aug row is slower than the earlier rows for two compounding reasons, both expected rather
than concerning: it is a much larger model (`medium`, 16.6M params vs. `nano`'s far smaller footprint)
and it is the first measurement taken against a genuinely live camera stream (resize/JPEG-encode/
snapshot overhead included) rather than a single static file fed via `--fake-camera`. Even so, 138 ms
is **~3.9x faster than Edge Impulse Studio's own 536ms int8 estimate** for this exact checkpoint on
the `arduino-unoq` latency-device profile, and both the 138ms figure and the 33.8ms figure sit far
inside the `VISION_INFERENCE_TIMEOUT_S = 2.0` s budget in `device/mpu/services/config.py` — latency
has never been the constraint on this project; recall has.

**GPU delegate (`runner-linux-aarch64-gpu`, BETA)**: real, selectable, genuinely compiles and links
GPU-delegate code in Studio's cloud build on every attempt (28 Aug, 29 Aug with root access, 29-30 Aug)
— and fails to launch on this board every single time with the same missing-library error
(`libtensorflowlite_gpu_delegate.so`), confirmed absent from the filesystem via exhaustive search and
unobtainable via `apt`. Three independent confirmations across three different exported checkpoints
make this a settled finding, not a one-off fluke: **the Adreno 702 GPU path is not usable on this
board's current software image**, full stop, pending a QRB2210-matched delegate library this
engagement has no lead on sourcing. Does not block deployment — the CPU path alone comfortably clears
every real-time requirement.

**Bottom line — honest, final answer for this engagement**: the ≥92%-per-class recall bar, at a
threshold that keeps false-positive rate in a shippable range, **was not met** by any architecture,
capacity, threshold, or dataset-cleanup pass tried. The closest approach is the current deployed
checkpoint (`no_attn_relu`, `medium`, threshold 0.05): Elephant recall 0.906 (1.4 points short) and
Boar recall 0.852 (6.8 points short), with the best background false-positive rate of the engagement
(0.166) and zero false positives across 123 live out-the-window frames captured this window on real
hardware. What was genuinely, honestly achieved this engagement: the best Elephant recall ever
reached, the best Boar recall ever reached (via trail-camera-v2, one pass earlier — a real domain-
match dataset effect), the lowest false-positive rate ever reached, real hardware confirmation that
CPU latency is a non-issue (3.9x faster than Studio's own estimate), and functional correctness
verified end-to-end through the actual production client code against real, known-labeled images.
**What would close the remaining gap**: a domain-matched Elephant dataset with the same kind of effect
`swg-eurasian-wild-pig` had on Boar recall (real forest/camera-trap Elephant imagery, not catalog
photography — none has been found yet despite the 28-29 Aug IR/night search); and a combined
architecture+data search, since every single-axis lever tried (capacity, threshold, architecture
variant, one dataset improvement at a time) has independently plateaued below the bar. The EON Tuner
job launched 29 Aug (`53262078`) was still running as of this window's last check and has not yet
produced a candidate that beats the current champion — if it finishes and does, that supersedes this
table; if it does not, the two named levers above are the real next steps, not further threshold or
capacity tuning on the current corpus.

### Hyperparameter axes never actually swept — named honestly, not silently assumed exhausted

Every entry above rigorously swept **dataset composition/quality, model capacity (nano→large), the
`attn_silu`/`no_attn_relu` architecture-type axis, and confidence threshold** — those were the real,
reported levers. Reviewing the full "Object detection settings" panel against what was actually run,
several other fields in that same panel were left at their initial value for every single YOLO-Pro
job this entire engagement, never varied and never reported as ruled out — a gap, not a finding:

- **Learning rate** — 0.001 on every run, no sweep.
- **Batch size** — 16 on every run, no sweep.
- **Freeze backbone** — always `false`. Worth trying `true` specifically for Boar, where the training
  data is the more domain-mismatched of the two classes and a frozen pretrained backbone could reduce
  overfitting to that mismatch rather than fitting it.
- **Spatial / color augmentation** — always `Low`, never bumped to `Medium`/`High`. A plausible lever
  for the same Boar-domain-mismatch reason above — heavier crop/color jitter is a standard response to
  a training set that doesn't fully match the deployment domain.
- **Early stopping start epoch** — always 10, no sweep.
- **Validation set size / split-on-metadata-key** — left at Studio's 20% default, never touched.
- **Input resolution (96×96)** — swept once, but only on the old FOMO architecture (23 Aug's
  resolution ladder), and reverted after losing to that era's free-tier 1-hour compute cap. **Never
  re-tried on YOLO-Pro**, where that specific ceiling no longer applies (Enterprise tier). The 23 Aug
  conclusion does not necessarily transfer to a different, larger architecture family.

None of these were run this engagement — not attempted and abandoned, simply never queued. Recorded
here as the concrete next set of trials, in priority order (freeze-backbone and augmentation strength
first, both targeted at Boar specifically; resolution retry second, since it is the most expensive
single trial; learning rate and batch size last, lowest expected payoff based on how flat the loss
curves have looked across every job run so far).

## 30 Aug — 2-hour continuous live-camera run on real hardware: a real false-positive rate found, materially revising the earlier 0/123 claim

**This corrects, not just supplements, the "0/123, zero false positives" line in the 29-30 Aug
on-device benchmark entry above.** That number came from a 21.4 s, 123-frame sample. This entry is a
2-hour, 40,422-frame sample taken on the same board, same checkpoint, same threshold, same live
camera — and it is not zero. The earlier entry is left as written per this file's convention of
appending corrections rather than editing history; treat its "0/123" line as superseded by the numbers
below wherever the two disagree.

**Setup.** Camera pointed at outdoor trees/foliage (no Elephant or Boar present — camera was not
aimed at the road/clearing this session), IR illuminator on throughout per the deployed default. Run
via `edge-impulse-linux-runner --model-file etx_cpu_final_0830.eim --profiling --silent` (current
deployed CPU checkpoint, `no_attn_relu`/`medium`, threshold 0.05), authenticated via the board's
already-cached Edge Impulse login (no API key passed). Split into 13 sequential foreground chunks
(the CLI tool's own timeout cap, not a runner limitation) covering **2h 02m 01s** of continuous
wall-clock capture, 2026-08-30 06:53:49–08:55:50 IST (01:23:49–03:25:50 UTC), all 13 chunks appending
to one log with no gap or restart between them.

**Volume and cadence.** 40,422 classify events. 40,422 / 7,321 s = **5.52 FPS** — consistent with (and
within ~4% of) the 5.7 FPS measured on the smaller 28-29 Aug sample; the extra 2 hours of sustained
runtime did not reveal any performance degradation or drift over time.

**Latency.** 40,227 of the 40,422 classify events carried a usable `inference_time_cpp.classification`
value (the remaining 195, 0.48%, were truncated at a chunk boundary and excluded, not counted as
either fast or slow). Mean **137.25 ms**, min 134 ms, max 145 ms, p50/p90/p95/p99 = **137/139/140/142
ms**. This matches the 138 ms mean from the earlier 123-frame sample almost exactly and, at this
volume, is a far more reliable number: on-device CPU latency for this checkpoint is genuinely stable
at ~137 ms regardless of scene content, run duration, or time of day.

**False-positive rate — the real finding.** 12,747 of 40,422 frames (**31.53%**) produced at least one
`Boar` bounding box; 14,237 boxes total (some frames carried more than one simultaneously). **Zero**
`Elephant` false positives across the entire run — the false-positive problem this run surfaces is
Boar-specific, not general. Confidence values cluster into 11 exact discrete levels (an INT8
quantization artifact — the deployed model's output is not continuous at this end of the range):

| Confidence | Box count | Share of all boxes |
|---|---|---|
| 0.0743 | 8,103 | 56.9% |
| 0.1114 | 3,215 | 22.6% |
| 0.1485 | 814 | 5.7% |
| 0.1857 | 667 | 4.7% |
| 0.2228 | 489 | 3.4% |
| 0.2599 | 418 | 2.9% |
| 0.3342 | 291 | 2.0% |
| 0.3713 | 151 | 1.1% |
| 0.4456 | 57 | 0.4% |
| 0.5198 | 25 | 0.18% |
| 0.5569 | 7 | 0.05% |

**Raising the threshold reduces but does not eliminate this — even Studio's own default of 0.5 does
not fully clear it.** Box count surviving each threshold: ≥0.05 (all) 14,237 · ≥0.1 6,134 · ≥0.15
2,919 · ≥0.2 1,438 · ≥0.3 531 · **≥0.5 32**. Those 32 survive at a threshold well above anything this
engagement has ever deployed or considered — meaning this is not solely a threshold-tuning problem.
79.5% of all boxes sit at the two lowest quantization levels (0.0743/0.1114, both just above the 0.05
floor), which reads as the model's genuine "resting" activation for this specific outdoor scene rather
than confident misclassification — but the 32 boxes at ≥0.5 are a different thing: those are the model
looking directly at plain foliage and returning moderate-to-real confidence that it is Boar.

**Bounding-box locations cluster into a handful of fixed physical spots, not random noise across the
frame** — 108 distinct (x, y, w, h) combinations collapse into four recurring anchor regions (in the
96×96 processed frame): bottom-left (x≈0, y≈60–67, the single largest cluster — 1,452 hits alone at
one exact box), left-center (x≈28–35, y≈49–60), center (x≈42–53, y≈46–64), and right (x≈81–89,
y≈46–57). Because the camera was static for the full 2 hours, this points to specific, fixed leaf or
branch features in this exact framing that intermittently cross the detection threshold — a genuine,
repeatable content confusion tied to this scene's texture, not a diffuse background hum spread evenly
across the image.

**The rate varies enormously and non-monotonically across the run — a real, unexplained pattern:**

| Chunk | Start (IST) | Frames | Detection rate |
|---|---|---|---|
| 1 | 06:53 | 3,053 | 5.4% |
| 2 | 07:03 | 3,093 | **73.9%** |
| 3 | 07:12 | 3,113 | 31.1% |
| 4 | 07:22 | 3,108 | 27.5% |
| 5 | 07:31 | 3,109 | 14.6% |
| 6 | 07:41 | 3,115 | 14.0% |
| 7 | 07:50 | 3,149 | 30.1% |
| 8 | 08:00 | 3,154 | 45.1% |
| 9 | 08:09 | 3,122 | 52.6% |
| 10 | 08:19 | 3,101 | 43.1% |
| 11 | 08:28 | 3,105 | **59.1%** |
| 12 | 08:37 | 3,106 | 11.5% |
| 13 | 08:47 | 3,094 | **1.2%** |

This run spanned sunrise at this latitude (roughly 06:50–08:55 IST covers dawn through full daylight
in late-August Kerala), so a changing-light-condition explanation is plausible on its face — but the
rate does not move monotonically with rising light the way a pure brightness effect would; it spikes,
drops, and spikes again. That shape is more consistent with something intermittent — wind moving the
foliage, or passing cloud creating dappled/moving shadow — than with a smooth dawn-brightness curve.
**No wind or weather log was captured alongside this run, so this is a hypothesis worth testing next,
not a conclusion.** What is a conclusion: the false-positive rate on this exact scene is not a fixed
constant, and any single short sample (including the earlier 123-frame one) risks landing anywhere
from ~1% to ~74% purely by chance of when it was taken.

**What this changes.** The 29-30 Aug entry's "zero false positives across 123 live out-the-window
frames" was real data, honestly reported at the time, and simply too small a sample to be
representative — this is the correction, not a retraction of the method. The background false-positive
rate reported earlier in this file (0.166, from the Studio held-out test split) was measured on
catalog/camera-trap negative images, not on this specific outdoor scene under IR — the two numbers are
not measuring the same thing and should not be read as contradicting each other, but 31.53% on live
footage is a materially worse number than 16.6% on the held-out set, and belongs in any honest
pre-deployment risk assessment. **This is a real, hardware-confirmed, deployment-relevant gap**: the
current 0.05 threshold, tuned for recall against the ≥92% bar, produces a high nuisance-alert rate
against at least one real outdoor scene. The two concrete next steps, in order: (1) test the N≥2
consecutive-frame temporal-aggregation fusion-layer lever already named as a v2 idea elsewhere in this
file — it would suppress exactly this kind of single-frame flicker while preserving true multi-frame
detections; (2) capture true-negative training data from this same physical scene (the swg-eurasian
approach that helped Boar recall generally) so the model sees this specific foliage pattern labeled
correctly during training, rather than only after the fact during a field run.

Raw log (`monitor_2h_20260830.log`, 138.5 MB, 1,169,788 lines, full per-frame profiling and bounding-
box output for all 40,422 classify events) remains on the board at `/home/arduino/`; not copied
locally given its size — the aggregates above were computed directly against it over SSH and are
reproducible from it if deeper reanalysis is ever needed.

**3 Sept update — both next steps above were acted on; a real fix landed, and a real second cause
was found and characterized elsewhere, not chased here.** Full numbers in
`docs/qa/boar-gap-session-notes.md`; summary here since this section is the reference the numbers
were promised against.

Next step (1) — the N≥2 temporal-aggregation lever this section names — was implemented and replayed
against this exact log, aggregated on the board over SSH, never copied down. The naive per-poll
debounce alone was a near-miss: production doesn't consume raw frames, it consumes 3-frame bursts
OR'd together into one poll every ~1 s, and that burst-OR unit is itself worse than the frame rate
above — **43.64%** of polls (2,942/6,742) carried a Boar box before any debounce, not 31.53%. A first
pass at 2-consecutive-positive-polls barely moved that (40.48%). The fix that actually worked was a
within-burst requirement stacked on top — a poll only counts Boar if a majority of its 3 frames do,
not just one — which brought the debounced production rate to **27.54%** (1,857/6,742), back in line
with the frame-level number. Elephant stayed at 0% false positives through every stage, as expected
(no boxes at all in this scene). Committed as `596b432`; the config knob and the per-chunk table are
`device/mpu/services/config.py`'s `VISION_SPECIES_BURST_MAJORITY_LABELS`/
`VISION_SPECIES_CONSECUTIVE_POLLS` and the replay script committed alongside it.

Next step (2) — true-negative training data from this exact scene — was **not done this session**;
Workstream 2 (a Boar representation audit and sourcing plan) is docs-only per plan and deliberately
deferred past the 5 Sept ship date, so the underlying model weights and the 0.87%-real-IR-Boar-imagery
gap this file's other sections describe remain untouched. This section's numbers describe a
consumption-layer fix, not a retrain — the model itself is exactly as accurate (or inaccurate) as it
was on 30 Aug.

**A second, independent cause was found by a different session, and is recorded here by cross-
reference rather than duplicated or chased further** — `docs/qa/night-ir-led-characterisation.md`, a
real board-run characterization of camera control (not model weights), found auto-exposure + IR to be
the *only* configuration across its whole test battery to produce a meaningful false-positive
population (15/22/28 spurious Boar boxes across three runs, confidence up to 0.408 — above the 0.2
deployment threshold), while locked exposure gave zero false positives across the same battery. That
session's own written recommendation: "auto-exposure at night should be considered a bug for this
pipeline." This is a plausible mechanism for this section's own unexplained per-chunk swing
(1.2%–73.9%, table above) — dappled light and AGC hunting produce exactly the kind of intermittent,
non-monotonic signal this section flagged as "a hypothesis worth testing next, not a conclusion." Not
confirmed causal against this specific log — just the leading candidate, and not implemented here: the
camera-control code is a separate session's, and a real blocker is already on record there — the
container's camera path does not accept exposure writes and sits frozen at a fixed value, unlike the
host V4L2 path. See `docs/KNOWN_GAPS.md`'s matching cross-reference entry.

<!-- LIVE_SYNC_PLACEHOLDER -->

## Reproducing

```
export EI_API_KEY=ei_...          # project 1097972 (ETX-V, Enterprise) API key, not stored in this repo
export EI_PROJECT_ID=1097972      # 1094260 is the legacy free-tier project, kept as an archived reference only
export RF_API_KEY=...             # authenticated client only; nothing is uploaded to Roboflow
python scripts/edge_impulse_upload_vision.py
python scripts/edge_impulse_train_vision.py
```
