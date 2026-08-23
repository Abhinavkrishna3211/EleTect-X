# Two-class FOMO vision model — Elephant + Boar (proof of concept)

Edge Impulse project **1094260** (`EleTect-X-Vision`). Project ID only is recorded here; the API
key is not in the repo and must be supplied through `EI_API_KEY` at run time.

**Read the caveats section before quoting either number anywhere.** This is a genuine FOMO object
detector trained on two real, openly-licensed datasets with real bounding boxes — and it is also
trained entirely on daytime colour wildlife photography, while the deployment target is a
night-IR camera. Both halves of that sentence have to travel together.

## Dataset

| Class | Source | Version | License | Images | Boxes |
|---|---|---|---|---|---|
| Elephant | `roboflow-universe-projects/elephant-detection-cxnt1` | v2 (`resized640`) | CC BY 4.0 | 3,280 | 4,475 |
| Boar | `trackabox-4ejy9/wild-boar-a1flm` | v1 | CC BY 4.0 | 1,901 | 3,003 |

**Why it is real:** both pulled live from Roboflow's COCO export API
(`scripts/edge_impulse_upload_vision.py`), full images with real annotator-drawn bounding boxes,
not synthesized or scraped-and-guessed. Citations, verbatim from each Universe page:

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
| Boar | 1,273 | 631 (33%) | 1,483 | 418 (22.0%) |

Every image carries at least one box **or** is a genuine zero-annotation frame from the same
source set, kept as a FOMO background/negative example rather than dropped: 552 of Elephant's
3,280 images and 4 of Boar's 1,901. The exact split — every filename, its group, and which side of
the boundary it landed on — is committed in `ml/vision/dataset_manifest.json`, so the numbers below
are reproducible from a fresh clone without re-running the split.

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

**Training-time validation** (from the training job's own held-out validation split, INT8
variant — the model type actually destined for the field):

| Class | Precision | Recall | F1 | Support (grid cells) |
|---|---|---|---|---|
| Elephant | 0.860 | 0.609 | 0.713 | 676 |
| Boar | 0.590 | 0.572 | 0.581 | 523 |

(float32 variant, for comparison: Elephant 0.839 / 0.699 / 0.763 on 688 cells; Boar 0.642 / 0.554 /
0.595 on 525 cells.)

**Held-out model test**, run as an Edge Impulse model-testing job over the real testing split
those 4,042 training images never touched. Edge Impulse's own `classify/all/result` reports a
single aggregate pseudo-class ("F1 score": 585 good / 554 bad, 51.4%) for object-detection
projects rather than breaking it out per label — so the per-class numbers below were computed
directly from that endpoint's per-sample results, grouped by each image's own ground-truth label
(every image in each source set carries only that set's class, so this grouping is exact, not
inferred):

| Class | Test images | Mean per-image F1 | Mean precision | Mean recall | Images scored a perfect F1 |
|---|---|---|---|---|---|
| Elephant | 649 | 0.670 | 0.729 | 0.669 | 317 (48.8%) |
| Boar | 418 | 0.567 | 0.563 | 0.634 | 145 (34.7%) |

The remaining 72 Elephant-set test images are zero-annotation background frames (Boar contributed
essentially none of its own 4 to the test split at this split ratio); FOMO predicted no false
centroid on 68 of them (mean F1 0.944, 94.4% clean) — a genuine but very small and Elephant-skewed
negative sample, see caveat 2.

## Caveats — required whenever either number is quoted

1. **Neither dataset is IR-illuminated night camera-trap footage.** Both are general daytime/colour
   wildlife photography. ADR 0001 (`docs/decisions/0001-usb-camera-imx462.md:7`) states over 70% of
   elephant raids are nocturnal, requiring 940 nm active-IR night vision. This work closes *"a
   two-class FOMO model exists and is trained on real, licensed data"* — it does **not** close
   *"this model works on real field IR footage at night."* Those two claims must travel separately;
   nothing here measures night-IR performance at all.
2. **The background/negative sample is small and lopsided.** 556 of 5,181 source images (552
   Elephant, 4 Boar) carry no annotation and were kept as FOMO negatives, but they are stray
   unannotated frames from the same two collections, not a curated set of "genuinely empty forest"
   scenes, and there are effectively none from the Boar side. The 94.4% clean-negative figure above
   says very little about the false-positive rate on real empty-forest footage, and nothing at all
   about Boar false positives specifically.
3. **Class imbalance is real and shows up in the result.** 3,280 : 1,901 images (~1.7:1) going in;
   Elephant outperforms Boar on every metric above, in both the training-time validation and the
   independent held-out test. `autoClassWeights` was enabled to counter it during training, not
   to erase it from the result — the gap after weighting is the honest number.
4. **Source images arrive at two different resolutions**, Boar 416×416 and Elephant 640×640,
   both stretch-resized upstream by Roboflow before either set reaches this project, then both
   squashed again into FOMO's 96×96 input. No attempt was made to correct for this.
5. **Not deployed.** No `.eim` export exists, no detector runs anywhere in the field path, and
   `cognition/fusion.py`'s `VISION` modality stays unpopulated — see the open follow-up entry in
   `docs/KNOWN_GAPS.md`. This README records that a model was trained, not that it does anything yet.
6. **`CONTEXT.md:30` names the vision runtime "Adreno/OpenCL"; ADR 0001
   (`docs/decisions/0001-physical-ai-sensing-and-fusion-architecture.md:16`) specifies a "generic
   CPU/TFLite path (no QNN/Hexagon delegate available on this chip)."** The repo does not reconcile
   these two statements about the same QRB2210 runtime. INT8 quantization (this model was profiled
   both ways) is orthogonal to which of the two actually executes it — flagged here, not resolved.

*Correct framing for a report table: proof-of-concept two-class FOMO detector trained on real,
CC BY 4.0-licensed daytime wildlife photography (3,280 Elephant / 1,901 Boar images, group-aware
80/20 split); held-out per-image F1 0.67 Elephant / 0.57 Boar; not field-validated, not night-IR
validated, not deployed.*

## Reproducing

```
export EI_API_KEY=ei_...          # project 1094260 API key, not stored in this repo
export EI_PROJECT_ID=1094260
export ROBOFLOW_API_KEY=...       # authenticated client only; nothing is uploaded to Roboflow
python scripts/edge_impulse_upload_vision.py
python scripts/edge_impulse_train_vision.py
```
