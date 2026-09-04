# Edge Impulse Studio — vision tuning for the EleTect X on-device detector

Scope: raising per-class recall on the UNO Q (QRB2210, CPU-only, ~138 ms/frame) Elephant/Boar
detector past the >=92% recall bar, day and IR night, without wrecking the already-high precision.
Every claim below is linked to its source. Items we could not confirm from published docs are in
the "Unverified / open" list at the end and must be checked directly in Studio.

---

## Top summary — highest-leverage moves

1. **Fix the data before the model.** The gap is silent misses (zero boxes on ~11% Elephant /
   ~23% Boar test images) with high precision — this is almost always a data-coverage or
   label-recall problem, not an architecture problem. Use the **Data Explorer** and
   **Model testing → per-sample drill-down / "show only missed objects"** to pull the exact
   miss images, cluster them (night? dawn auto-exposure? occluded? distant? rear-view?), and
   backfill those clusters with real or synthetic frames. Also audit labels: unlabelled true
   objects in training images teach the model to *suppress* detections. Edge Impulse's own
   guidance ranks "more data / more diverse data / move misclassified samples into training"
   as the first lever. Sources:
   [increasing-model-performance](https://docs.edgeimpulse.com/knowledge/guides/increasing-model-performance),
   [data-explorer](https://docs.edgeimpulse.com/studio/projects/data-acquisition/data-explorer),
   [live-classification](https://docs.edgeimpulse.com/studio/projects/live-classification),
   [model-testing](https://docs.edgeimpulse.com/studio/projects/model-testing).

2. **Stay on YOLO-Pro, but move up one size and turn off Mosaic.** YOLO-Pro is the only
   built-in bounding-box block that targets MCU *and* CPU; MobileNetV2-SSD-FPN is Linux/
   high-compute only and FOMO gives centroids not boxes and explicitly breaks on large animals
   filling the frame. Try **YOLO-Pro `small` or `medium`** (6.9 M / 16.6 M params) if the
   latency budget survives, keep **"Attention with SiLU"** (better accuracy; QRB2210 is a
   capable Cortex-A CPU, not a tiny MCU), enable **pre-trained weights**, do **not** freeze the
   backbone, and set spatial augmentation to **Medium** (crop + rotate + flip) rather than
   **High** — High adds Mosaic, which for a 2-class large-animal set tends to hurt more than
   help. Sources:
   [object-detection overview](https://docs.edgeimpulse.com/studio/projects/learning-blocks/blocks/object-detection),
   [yolo-pro](https://docs.edgeimpulse.com/studio/projects/learning-blocks/blocks/object-detection/yolo-pro),
   [fomo](https://docs.edgeimpulse.com/studio/projects/learning-blocks/blocks/object-detection/fomo),
   [mobilenetv2-ssd-fpn](https://docs.edgeimpulse.com/studio/projects/learning-blocks/blocks/object-detection/mobilenetv2-ssd-fpn).

3. **Weight the classes and the objective toward recall.** Boar is the worse class and the
   minority — enable **"Auto-weight classes"**, or in **Expert Mode** pass explicit
   `class_weight` (sklearn `compute_class_weight`) so Boar misses cost more. Expert Mode also
   lets you edit the loss directly (FOMO exposes an `object_weight`, default 100, raise to
   ~1000 for rare objects — the same idea applies if you drop to FOMO). Sources:
   [increasing-model-performance](https://docs.edgeimpulse.com/knowledge/guides/increasing-model-performance),
   [expert-mode](https://docs.edgeimpulse.com/studio/projects/learning-blocks/expert-mode),
   [fomo](https://docs.edgeimpulse.com/studio/projects/learning-blocks/blocks/object-detection/fomo).

4. **Separate the two thresholds: train/eval hot, deploy calibrated.** Keep sweeping the
   confidence threshold low (0.05) for the recall number, but cut the dawn false positives at
   deployment with **post-processing** — Studio's **object tracking** (tracking-by-detection +
   Kalman, with `Keep grace`, `Max. observations`, `Threshold`) suppresses one-frame
   low-confidence Boar boxes because a real animal persists across frames and a
   dawn-auto-exposure artefact does not. **Performance Calibration** tunes an averaging window
   / detection threshold / suppression period against a simulated stream and reports FAR/FRR.
   Per-class deploy threshold lives in `EI_CLASSIFIER_OBJECT_DETECTION_THRESHOLD`
   (Model testing → "Set confidence thresholds", written to `model_metadata.h`). Sources:
   [object-tracking](https://docs.edgeimpulse.com/studio/projects/post-processing/object-tracking),
   [performance-calibration](https://docs.edgeimpulse.com/studio/projects/performance-calibration),
   [model-testing](https://docs.edgeimpulse.com/studio/projects/model-testing).

---

## Q1 — YOLO-Pro: hyperparameters, knobs, and what helps recall

Source unless noted:
[yolo-pro doc](https://docs.edgeimpulse.com/studio/projects/learning-blocks/blocks/object-detection/yolo-pro),
[YOLO-Pro launch blog](https://www.edgeimpulse.com/blog/introducing-yolo-pro-object-detection-optimized-for-the-edge/).

### Size variants (parameter count)
| Variant | Params |
|---|---|
| pico | 682 K |
| nano | 2.4 M |
| small | 6.9 M |
| medium | 16.6 M |
| large | 30 M |
| xlarge | 35 M |

Bigger = higher capacity/accuracy, more latency and RAM/ROM. Current champion sizing is not
recorded here; the recall ceiling on a 12.8 k-image set is often capacity-bound, so testing one
size up is cheap signal.

### Architecture type (two options)
- **Attention with SiLU** (default): final backbone block uses partial self-attention; all conv
  blocks use SiLU. "More traditional" YOLO-like accuracy. Best when the target can run attention
  ops — a Cortex-A class CPU like QRB2210 generally can.
- **No Attention with ReLU**: Edge Impulse custom variant, no self-attention, ReLU everywhere,
  "for devices that struggle with attention layers or that run ReLU notably faster." Choose this
  only if profiling shows the attention block is the latency bottleneck; expect a small accuracy
  (hence recall) cost.

### Training settings
- **Pre-trained weights** — enable for almost all cases; "substantially reduce the amount of
  data and time required for training." Directly helps recall on a modest dataset.
- **Freeze backbone** — only available with pre-trained weights on. When on, backbone + FPN are
  frozen and only the box/class heads train. Faster, less overfitting, but **lower ceiling** —
  for a recall push you want this **off** so the backbone adapts to IR/night texture.
- **Number of training cycles (epochs)** — user-editable field with a default; more epochs can
  raise recall until it plateaus/overfits. Exact default not in the doc — read it in Studio.
  ([Peter Ing, "Beginners guide to Object Detection with Edge Impulse", Medium](https://peter-ing.medium.com/beginners-guide-to-object-detection-with-edge-impulse-c8ea95f844a0)
  confirms epochs + learning rate are the two main editable hyperparameters with defaults.)
- **Learning rate** — user-editable with a default; affects stability and final accuracy. Docs
  advise leaving epochs + LR at defaults "if in doubt." Exact default not published.
- **Early stopping start epoch** — sets how many epochs run before the early-stopping callback
  (validation-loss based) can fire, so the model can "settle in." Raise it if training stops too
  early and recall is still climbing.

### Augmentation (KerasCV-based; training-only, zero deploy cost)
Spatial presets:
| Preset | Transforms |
|---|---|
| No spatial augmentation | — |
| Low | RandomCropAndResize |
| Medium | RandomCropAndResize + RandomRotation + RandomFlip |
| High | RandomCropAndResize + RandomRotation + RandomFlip + **Mosaic** |

Color-space presets: Low / Medium / High, based on RandAugment
("RandAugment: Practical automated data augmentation with a reduced search space").

What this means for EleTect X:
- **RandomCropAndResize** helps recall on partially-visible / edge-of-frame / distant animals —
  keep it (Low or Medium).
- **Mosaic** (High preset) tiles 4 images; good for tiny-object COCO-style sets, frequently
  *counterproductive* for a 2-class set of large subjects and can inflate false positives.
  Prefer **Medium**.
- **Color-space augmentation** is the built-in lever for lighting robustness — pushing it to
  **Medium/High** simulates brightness/contrast/hue shifts and is the closest thing to
  "dawn auto-exposure" and "IR wash-out" simulation available without custom code. Try High
  color + Medium spatial as one experiment arm.
- Docs' universal caveat: train a no-augmentation baseline first, then A/B each augmentation
  change on the **test set** — augmentation gains are not guaranteed.
  ([data-augmentation](https://docs.edgeimpulse.com/knowledge/concepts/machine-learning/data-augmentation))

### Expert Mode on YOLO-Pro
Expert Mode exposes the full Keras training script: custom architecture, **custom loss**,
optimizers (e.g. VeLO), callbacks, epoch/early-stop control, and **class weighting**
(`compute_class_weight` → `class_weight=`). Network access is disabled inside training jobs, so
you cannot pull external weights. Documented object-detection example of the weighting knob is
FOMO's `object_weight` (default 100 → 1000 for rare objects). Use Expert Mode to: (a) add
Boar-favouring class weights, (b) lower the objectness/classification threshold used at eval,
(c) adjust the IoU/assignment used in loss, (d) extend training schedule.
Source: [expert-mode](https://docs.edgeimpulse.com/studio/projects/learning-blocks/expert-mode).

### What specifically reduces silent misses
- Pre-trained weights ON, backbone **not** frozen, one size larger.
- More epochs + higher `Early stopping start epoch` so training doesn't cut off while recall
  still rises.
- Class weighting toward Boar (auto-weight or Expert Mode).
- Spatial **Low/Medium** with RandomCropAndResize (occlusion/partial-view robustness); color
  **Medium/High** (lighting robustness). Avoid Mosaic.
- Higher input resolution if latency allows (see Q2 / Unverified).
- Lower the eval/deploy confidence threshold for recall, then recover precision with tracking
  (Q4) rather than by raising the threshold.

---

## Q2 — Which detection block for two medium-large animals on QRB2210 CPU

Sources:
[object-detection overview](https://docs.edgeimpulse.com/studio/projects/learning-blocks/blocks/object-detection),
[fomo](https://docs.edgeimpulse.com/studio/projects/learning-blocks/blocks/object-detection/fomo),
[mobilenetv2-ssd-fpn](https://docs.edgeimpulse.com/studio/projects/learning-blocks/blocks/object-detection/mobilenetv2-ssd-fpn),
[nvidia-tao](https://docs.edgeimpulse.com/studio/projects/learning-blocks/blocks/nvidia-tao),
[FOMO vs YOLOv5 forum](https://forum.edgeimpulse.com/t/use-fomo-or-yolov5-for-object-detection/7473).

| Block | Output | Runs on | Notes for our case |
|---|---|---|---|
| **YOLO-Pro** | Bounding boxes | MCU **and** CPU/GPU; input = multiples of 32, square | Only built-in box model that fits a CPU MPU target. "Stronger performance at int8 than float32." Six sizes to trade latency/recall. **Recommended.** |
| **FOMO** | Centroids only (no boxes) | MCU / very constrained | Explicitly weak when "objects fill most of the frame" (large animals close to camera) and when objects overlap — each heatmap cell is its own classifier so near/overlapping animals collide. 30x lighter than SSD/YOLOv5. Good for counting at fixed range, not for our occluded close-range night targets. Fallback only if YOLO-Pro can't hit latency. |
| **MobileNetV2-SSD-FPN** | Bounding boxes | "Available with Edge Impulse **for Linux**"; "uses high compute resources"; needs **large** objects; 320x320 | SSD "trades accuracy for speed" and "has issues with objects too close or too small"; FPN mitigates scale. Marked **not MCU**. Could run on the QRB2210 Linux side but it is the heavy option and tuning knobs are thin (LR start 0.15 documented, little else). Not the first choice. |
| **NVIDIA TAO** | Boxes | — | **Deprecated 28 Feb 2025**, cannot retrain. Do not use. |
| **YOLOv5 / YOLOX (custom learning block)** | Boxes | CPU/GPU | Available as community/custom ML blocks, not built-in. More knobs, more maintenance, no EON Tuner integration. Only if YOLO-Pro genuinely plateaus. |

Recommendation: **YOLO-Pro, "Attention with SiLU", size `small`/`medium`**, int8 deploy.
Occlusion / partial night targets are handled best by a real box model (YOLO-Pro) plus object
tracking to bridge frames where the animal is briefly hidden (`Keep grace`, Q4). FOMO's centroid
approach and "similar size / not too close / not too large" constraints make it a poor match for
elephants and boar at close IR range.

Latency: only the QRB2210 CPU figure (~138 ms/frame, ~7 fps) for the current model is known to
us; per-size YOLO-Pro latency on this SoC is **not published** — profile each candidate size in
Studio's on-device profiler / EON Tuner with the UNO Q selected as target.

---

## Q3 — Data augmentation for low-light / IR / noise / motion blur; synthetic data

### Built-in (Studio) augmentation
- **YOLO-Pro**: spatial presets (crop/rotate/flip/mosaic) + **color-space presets**
  (RandAugment: brightness, contrast, hue, saturation type shifts). Color presets are the
  built-in proxy for lighting/exposure variation. No dedicated "low-light", "IR", "Gaussian
  noise", or "motion blur" toggle is documented for the image path — those are **audio/
  spectrogram** options (SpecAugment, background-noise mix).
  ([data-augmentation](https://docs.edgeimpulse.com/knowledge/concepts/machine-learning/data-augmentation),
  [yolo-pro](https://docs.edgeimpulse.com/studio/projects/learning-blocks/blocks/object-detection/yolo-pro))
- The augmentation concept page lists, generically: rotation/scale/flip/crop, brightness/
  contrast/hue/saturation, **noise injection**, and CutMix/mixup — but states only that
  "settings are available in Studio while configuring your Learning block" without confirming
  which are exposed for images. Assume: spatial + color for YOLO-Pro, nothing more, unless
  Studio shows otherwise.

### Getting true low-light/IR/blur augmentation
- **Expert Mode**: add a custom KerasCV/tf.image augmentation layer to the YOLO-Pro training
  script — `RandomBrightness` (large negative range), `RandomContrast`, gamma down,
  `GaussianNoise`, a motion-blur conv kernel, and a grayscale/night-tint transform. This is the
  only in-platform way to simulate IR wash-out and dawn auto-exposure directly.
  ([expert-mode](https://docs.edgeimpulse.com/studio/projects/learning-blocks/expert-mode))
- **Offline augmentation** before upload: synthesize dark/blurred/noisy variants of existing
  Elephant/Boar frames (and low-light-simulation transforms from the CV literature) and upload
  them as normal training data with the original boxes. Cheapest reliable route.
- Prefer **collecting real IR-night footage** — Edge Impulse's guidance and the low-light-
  detection literature both note that enhancement/simulation tuned for human perception does not
  reliably transfer to detector recall; real target-domain frames do.
  ([increasing-model-performance](https://docs.edgeimpulse.com/knowledge/guides/increasing-model-performance))

### Synthetic data for the rare class (Boar)
- Studio's documented image generator is **DALL-E image generation** ("Generate image datasets
  using Dall-E"); it explicitly targets "uncommon or rare scenarios." There is also a
  **Custom synthetic data blocks** mechanism and an **NVIDIA Omniverse Replicator** integration
  referenced but not detailed on the concept page.
  ([synthetic-data](https://docs.edgeimpulse.com/knowledge/concepts/data-engineering/synthetic-data))
- Synthetic images arrive **unlabelled** — run them through **AI labeling** (below) or the
  bounding-box editor. Verify every synthetic label; a wrong/missing box on a synthetic Boar
  hurts recall.
- Caveats: generated wild-pig imagery skews toward daylight domestic pigs / stock-photo poses;
  it will not cover IR night texture or Indian forest context well. Use it to add *pose/
  occlusion* variety, not to fix the night gap.

---

## Q4 — Performance calibration + post-processing to cut dawn false positives without losing recall

### Object tracking (post-processing block)
Source: [object-tracking](https://docs.edgeimpulse.com/studio/projects/post-processing/object-tracking).
- Algorithm: **tracking-by-detection**, Kalman filter predicts each trace, new detections
  matched to traces per frame. Bounding-box models match by **IoU**; centroid models by
  Euclidean pixel distance.
- Parameters:
  - **Keep grace** — frames an object is retained after it disappears; tolerates brief
    occlusion (an animal moving behind a trunk). Raise it for night/occluded targets so a
    2–3 frame miss doesn't drop the track — this *recovers* recall at the event level.
  - **Max. observations** — how many past detections feed matching/stability.
  - **Threshold** — match criterion (IoU for boxes, pixel distance for centroids).
- Effect on dawn false positives: a one-frame low-confidence Boar box from auto-exposure never
  forms a persistent track, so a "require N consecutive/among-M frames" rule downstream (or the
  tracker's own stability requirement) drops it while a real animal — present for many frames —
  survives. Best fit for "linear, predictable motion"; less reliable for erratic movement.

### Performance Calibration
Source: [performance-calibration](https://docs.edgeimpulse.com/studio/projects/performance-calibration).
- Runs your impulse over a **continuous stream** (synthetic: test samples layered over noise,
  10–30 min on free tier; or your own labelled real recordings) at production latency, then
  tunes post-processing and reports metrics.
- Tunable: **Averaging window duration** (smooth scores over time), **Detection threshold**
  (min score for an event), **Suppression period** (block re-detections for N seconds after a
  hit).
- Metrics: **FAR (False Alarm Rate)**, **FRR (False Rejection Rate)**, plus TP/FP/TN/FN. Pick
  the operating point that meets FRR <= 8% per class (i.e. recall >= 92%) at the lowest FAR.
- Documented for audio/event models; whether the Studio UI runs it on an object-detection
  impulse is **not confirmed** — verify. If unavailable for OD, replicate the idea manually:
  run the low-threshold model over a held-out dawn video, then grid-search
  (confidence x consecutive-frame-count x tracker Keep-grace) offline for the FAR/recall knee.

### Confidence / deploy threshold
- **Model testing → "Set confidence thresholds"** sets
  `EI_CLASSIFIER_OBJECT_DETECTION_THRESHOLD` in `model_metadata.h`; can be set per deployment.
  ([model-testing](https://docs.edgeimpulse.com/studio/projects/model-testing), plus community
  reports of the metadata field.)
- Strategy: keep the **model** threshold low (0.05) so no true animal is discarded pre-tracker;
  push precision back up with **tracking + temporal voting + suppression**, not by raising the
  single-frame confidence threshold (which is exactly what re-introduces silent misses).
- Per-class thresholds: raising only Boar's single-frame threshold would trade away the recall
  you need — do the dawn-FP cleanup temporally instead. Whether Studio supports genuinely
  independent per-class OD thresholds is **not fully confirmed** in the docs (the UI presents a
  per-class list, but confirm it writes distinct values).

---

## Q5 — EON Tuner: search-space config, objectives, and why it may never beat the champion

Sources: [eon-tuner](https://docs.edgeimpulse.com/studio/projects/eon-tuner),
[eon-tuner/search-space](https://docs.edgeimpulse.com/studio/projects/eon-tuner/search-space).

### How it searches
- **Bayesian optimization** (upgraded from random search): builds a probabilistic model over the
  parameter space from prior trial results and your ranked objectives.
- Jointly varies **input block** (e.g. image size), **DSP/processing block**, **learning block**
  (architecture + hyperparameters), and **data augmentation**.
- **Hardware-aware**: accounts for RAM, flash, and inference time for the selected target
  device. Set the target to **Arduino UNO Q / the QRB2210 profile** or results won't reflect
  the real latency budget.

### Search-space template (JSON) — how to constrain it
- Template has **input blocks**, **DSP blocks**, **learning blocks**.
- Restrict architectures via `dimension` and `model` lists. Object detection is expressed as:
  - Bounding-box: `"model": ["object_ssd_mobilenet_v2_fpnlite_320x320"]`
  - Centroid/FOMO: `"model": ["fomo_mobilenet_v2_a01", "fomo_mobilenet_v2_a35"]`
- Hyperparameter ranges:
  - `"trainingCycles": [20, 30, 40]`
  - `"learningRate": [0.0005, 0.001]`
  - bounded floats: `"dropout": {"value_type":"float","bounds":[0.1,0.5],"log_scale":true}`
- Input size: `"dimension"` arrays of image sizes.
- Augmentation: `"augmentationPolicyImage": ["all", "none"]`.
- **Caveat for us**: the published search-space examples for OD list **SSD-MobileNet and FOMO**,
  not **YOLO-Pro**. Whether a `yolo_pro_*` model id is a valid search-space entry is
  **unverified** — check in Studio. If YOLO-Pro cannot be placed in the template, the Tuner
  cannot explore around your champion at all, which alone explains "never beats it."

### Objective
- You rank one or more **run objectives**; the Bayesian algo weights higher-ranked ones more.
  For this task rank: (1) recall / F1 (accuracy metric), (2) latency <= budget, (3) memory. Do
  **not** let latency/memory outrank accuracy or it will converge on a smaller, lower-recall
  model.
- Filter/sort trial results by processing block, model type, val vs test set.

### Why the Tuner may not beat a hand-tuned champion
- If YOLO-Pro isn't a selectable search-space model, the Tuner is optimizing a *different,
  weaker* family (SSD/FOMO) and structurally cannot win. **Most likely cause here.**
- Bayesian search over a broad space is sample-inefficient; a well-chosen champion already sits
  near a local optimum the Tuner needs many trials to rediscover. Docs acknowledge "an optimal
  configuration has been reached and running more trials would provide diminishing returns."
- Default search space is broad and generic; it won't try your specific winning combination
  (size, augmentation preset, class weighting, epoch count) unless you **narrow the template**
  to a tight neighbourhood around the champion and let it vary only 2–3 axes.
- The Tuner tunes architecture/DSP/augmentation/epochs/LR — it does **not** tune label quality,
  class weighting internals, post-processing/tracking, or add data. Your recall gap is mostly in
  those areas, which the Tuner can't touch.
- Objective misconfiguration: if latency or memory is ranked at/above accuracy, it optimizes for
  small+fast and reports "nothing beat the champion" on accuracy by design.

Actionable: build a **custom search-space template** pinned to YOLO-Pro (if supported) at
`small`/`medium`, `trainingCycles` [high values], `learningRate` a narrow band around the
default, `augmentationPolicyImage` varied, target = UNO Q, objective = recall first. If YOLO-Pro
is not a valid entry, treat the Tuner as irrelevant for the champion and tune YOLO-Pro by hand.

---

## Q6 — Finding the silent-miss images and label problems

### Model testing
Source: [model-testing](https://docs.edgeimpulse.com/studio/projects/model-testing).
- **Test all** on the chosen model version (float32 or int8) → overall accuracy + **confusion
  matrix** (per-class) + interactive feature explorer.
- Per sample: menu → **"Show classification"** shows expected vs predicted output (boxes,
  labels, scores) for that image — this is where you eyeball why a specific frame produced zero
  boxes.
- **Confidence threshold slider** on this page changes sensitivity for testing + live
  classification; sweep it here to see recall/precision move and to reproduce the 0.05 sweep.
- Samples "that do not match the known classes" are excluded from accuracy — make sure genuine
  hard negatives are labelled as such, not left unlabelled.

### Live classification
Source: [live-classification](https://docs.edgeimpulse.com/studio/projects/live-classification).
- For OD: **side-by-side** (image vs predicted boxes) and **overlay** views, plus a summary
  table with per-class detection counts, precision, mAP (and F1/precision/recall for FOMO).
- **Prediction filter: "show all / only correct / only missed objects"** — this is the direct
  tool for isolating silent misses. Run held-out night and dawn clips through it and export the
  "missed" set as the backfill target list.

### Data Explorer
Source: [data-explorer](https://docs.edgeimpulse.com/studio/projects/data-acquisition/data-explorer).
- 2D t-SNE embedding of the dataset (via pre-trained model, trained impulse, or DSP block) —
  surfaces outliers, mislabels, clusters, and **coverage gaps / class imbalance** ("if data is
  inseparable in the explorer, the network probably can't separate it either").
- **Important limitation**: the docs state Data Explorer supports "audio classification, image
  classification and regression projects **only**" — i.e. **not object-detection projects
  directly**. Workarounds: (a) generate the explorer from a **pre-trained image model** / DSP
  block over the raw frames, (b) spin up a throwaway **image-classification** project with the
  same frames tagged day/night/dawn and elephant/boar/empty to get the embedding view, then act
  on it in the OD project. Use it to confirm whether night frames form their own sparse cluster
  (they will if under-represented).

### AI labeling / label audit
Source: [ai-labeling](https://docs.edgeimpulse.com/studio/projects/data-acquisition/ai-labeling).
- Zero-shot box generation with **OWL-ViT** or **Google Gemini** (1.5 Pro … 2.5 Pro), optional
  **GPT-4o** pass to re-label / drop boxes. Prompt-driven ("elephant", "wild boar / wild pig").
- Use it to **re-scan existing training images for unlabelled animals** — the most common cause
  of a high-precision / low-recall detector is missing boxes in training data teaching
  suppression. Preview on a subset, tag auto-labelled items with metadata
  (`ai-labeled: true`) for tracking, then human-verify.
- The old cluster/SAM **auto-labeler** is **deprecated (18 Nov 2024)** — use AI labeling.
  ([auto-labeler](https://docs.edgeimpulse.com/studio/projects/data-acquisition/auto-labeler))

### Training graphs
Source: [training-graphs](https://docs.edgeimpulse.com/studio/projects/learning-blocks/training-graphs).
- Accuracy + loss curves post-training; flags overfitting / underfitting / unstable / non-
  converged. Detection-specific metric interpretation (precision/recall/mAP/COCO mAP curves) is
  **not detailed on this page** — use TensorBoard export for per-class/mAP curves. If train
  recall is high but test recall is low → overfit/coverage gap (add data/augmentation). If both
  are low → underfit (bigger model, more epochs, unfreeze backbone, check labels).

---

## Unverified / open — confirm in Studio before relying on these

1. **YOLO-Pro numeric defaults**: epochs, learning rate, batch size, default size variant,
   input-resolution options (doc only says "multiples of 32, square"), and whether a per-size
   on-device latency/RAM/ROM table is shown for the UNO Q target. The doc omits all of these;
   only that epochs + LR are editable fields with defaults is confirmed (Medium guide).
2. **YOLO-Pro int8 vs float32**: overview page says "stronger performance at int8 than float32"
   — no numbers published; measure on device.
3. **YOLO-Pro in the EON Tuner search space**: published templates show only
   `object_ssd_mobilenet_v2_fpnlite_320x320` and `fomo_*`. Whether a `yolo_pro_*` /
   `yolov5_*` model id is a valid `model` entry is unconfirmed — decisive for whether the
   Tuner can even try to beat the champion.
4. **Performance Calibration for object detection**: documented behaviour is audio/event-stream
   oriented (averaging window / detection threshold / suppression period, FAR/FRR). Confirm the
   Studio UI runs it on an OD impulse; if not, do the FAR/recall grid-search manually.
5. **Per-class confidence thresholds for OD**: `EI_CLASSIFIER_OBJECT_DETECTION_THRESHOLD` and
   the "Set confidence thresholds" UI are real; whether Studio writes genuinely independent
   per-class values for a YOLO-Pro deployment is unconfirmed.
6. **Object tracking parameter defaults**: `Keep grace`, `Max. observations`, `Threshold`
   exist; default values are not in the doc.
7. **Image processing block resize modes**: "Fit shortest axis / Fit longest axis / Squash"
   and the 320x320 recommendation come from tutorials/forum, not the processing-block page we
   fetched. Confirm current options; for full-frame animals, "Fit shortest axis" (crop) vs
   "Squash" (aspect distortion) is worth an A/B — squash can distort animal shape and hurt
   recall.
8. **Built-in image augmentation beyond YOLO-Pro's spatial/color presets**: no documented
   Studio toggle for Gaussian noise, motion blur, or explicit low-light simulation on the image
   path — assumed to require Expert Mode or offline pre-processing.
9. **"Auto-weight classes" availability on the YOLO-Pro block specifically**: the option is
   documented in the general performance guide; confirm it appears on the YOLO-Pro block UI (vs
   only on classification blocks) — otherwise use Expert Mode `class_weight`.
10. **Synthetic-data generators actually available to this account**: only DALL-E image
    generation is clearly documented; Omniverse Replicator and custom synthetic blocks are
    referenced but may be enterprise-gated.
11. **NVIDIA TAO** — deprecated 28 Feb 2025, cannot retrain. Do not plan around it.
12. **Data Explorer** — documented as image-classification/audio/regression only; not OD.
    Confirm whether a newer Studio build added OD support before relying on it in-project.

## 4 Sept — the three questions Step 6 of the Boar-gap close-out plan flagged as genuinely
unknown and load-bearing, closed out by fetching the live docs + OpenAPI spec directly

The plan's own Step 6 named three unknowns as decisive for whether future retrain sessions can stop
routing every job through the delete-and-recreate hazard the whole engagement has worked around
(`--skip-impulse` on every call, never calling `build_impulse()`). Answered here so a future session
doesn't re-derive them.

1. **Model-testing/threshold API surface — confirmed, and it validates the existing script design
    rather than exposing a shortcut.** `docs.edgeimpulse.com/studio/projects/model-testing` and a
    direct OpenAPI-spec search both come back with no endpoint that reads per-class
    precision/recall/F1 at an arbitrary confidence threshold from an already-computed test run — the
    UI's own "confidence threshold" slider on that page **re-triggers testing**, it does not filter a
    cached result. This means `scripts/edge_impulse_train_vision.py`'s `sweep_thresholds()`
    (classify-job-per-grid-point, `POST jobs/classify` with `skipFeatureGeneration: true`, one real
    job per threshold) is not a workaround for a missing shortcut — **it is confirmed as the correct
    approach**, matching the docstring's own claim that fast in-place re-scoring is unsupported for
    object-detection models. No script change is indicated by this finding.
2. **Experiments — a real Studio feature, but UI-only as far as this search could confirm; does not
    change what the automation script can safely do.** `docs.edgeimpulse.com/studio/projects/experiments`
    confirms multiple trained impulses genuinely coexist in one project and are independently
    trainable and comparable: *"Want to experiment with both FOMO and MobileNet SSD simultaneously on
    the same dataset? No problem! Add two impulses and use the dropdown impulse selector menu in the
    left navigation bar to switch between them."* That would, in principle, remove the
    delete-and-recreate hazard entirely — a candidate could live in impulse #2 while the deployed
    checkpoint stays in impulse #1, untouched. **But** two targeted searches of the live OpenAPI spec
    (`studio.edgeimpulse.com/openapi.yml`) for an impulse-creation endpoint (`addImpulse`,
    `cloneImpulse`, or similar) found none — the spec's impulse-shaped operations are all
    block-configuration calls on an *existing* impulse, not impulse lifecycle calls. Caveat: the
    OpenAPI file is large and `WebFetch`'s page-to-markdown conversion is not proven exhaustive over
    it, so this is a real but not fully certain negative result — worth a direct `grep` over a
    downloaded copy of the spec before treating it as final. As things stand: **Experiments is a
    UI-driven safety net for a human working in Studio, not a lever this project's API-only training
    script can currently reach for.** The script's `--skip-impulse` / never-call-`build_impulse()`
    discipline remains the correct approach for anything automated.
3. **Versioning/snapshot restore semantics — partially resolved, still needs a live discovery pass,
    not doc-reading.** `docs.edgeimpulse.com/studio/projects/versioning` states only that a version
    "captures the current state of your project, including data, configurations, models, and
    settings" and lets you "restore your project to a prior state if needed" — it does not say
    whether a trained impulse's weights are recoverable after that impulse is deleted, or whether
    restoration is all-or-nothing vs. selective. The OpenAPI spec search found real CRUD-shaped
    endpoints under `/api/{projectId}/versions` (`listVersions`, `updateVersion`, `deleteVersion`,
    `listPublicVersions`, `makeVersionPrivate`) but **no `createVersion` or `restoreVersion`
    operation** — yet this project's own history proves creation works in practice (job `53262402`,
    30 Aug, `yolo-pro-medium-no_attn_relu-threshold0.05-final-20260830`), so a create path
    definitely exists, just not as a plain REST verb on that resource — most likely a job type
    dispatched through the general `/jobs` endpoint, which was not searched. **This remains the one
    of the three genuinely open**, and per the plan's own framing needs empirical confirmation (list
    job types via the API, or trigger a version snapshot from the UI and capture the network call),
    not another documentation pass.

---

## Source list

- YOLO-Pro block: https://docs.edgeimpulse.com/studio/projects/learning-blocks/blocks/object-detection/yolo-pro
- YOLO-Pro launch blog: https://www.edgeimpulse.com/blog/introducing-yolo-pro-object-detection-optimized-for-the-edge/
- Object detection overview: https://docs.edgeimpulse.com/studio/projects/learning-blocks/blocks/object-detection
- FOMO: https://docs.edgeimpulse.com/studio/projects/learning-blocks/blocks/object-detection/fomo
- MobileNetV2 SSD FPN: https://docs.edgeimpulse.com/studio/projects/learning-blocks/blocks/object-detection/mobilenetv2-ssd-fpn
- NVIDIA TAO (deprecated): https://docs.edgeimpulse.com/studio/projects/learning-blocks/blocks/nvidia-tao
- Expert mode: https://docs.edgeimpulse.com/studio/projects/learning-blocks/expert-mode
- Training graphs: https://docs.edgeimpulse.com/studio/projects/learning-blocks/training-graphs
- EON Tuner: https://docs.edgeimpulse.com/studio/projects/eon-tuner
- EON Tuner search space: https://docs.edgeimpulse.com/studio/projects/eon-tuner/search-space
- Performance calibration: https://docs.edgeimpulse.com/studio/projects/performance-calibration
- Object tracking / post-processing: https://docs.edgeimpulse.com/studio/projects/post-processing/object-tracking
- Model testing: https://docs.edgeimpulse.com/studio/projects/model-testing
- Live classification: https://docs.edgeimpulse.com/studio/projects/live-classification
- Image processing block: https://docs.edgeimpulse.com/studio/projects/processing-blocks/blocks/image
- Data augmentation concept: https://docs.edgeimpulse.com/knowledge/concepts/machine-learning/data-augmentation
- Synthetic data concept: https://docs.edgeimpulse.com/knowledge/concepts/data-engineering/synthetic-data
- Increasing model performance guide: https://docs.edgeimpulse.com/knowledge/guides/increasing-model-performance
- Computer vision embedded ML course (index only, no substantive content retrieved): https://docs.edgeimpulse.com/knowledge/courses/computer-vision-embedded-ml
- Data explorer: https://docs.edgeimpulse.com/studio/projects/data-acquisition/data-explorer
- AI labeling: https://docs.edgeimpulse.com/studio/projects/data-acquisition/ai-labeling
- Auto-labeler (deprecated): https://docs.edgeimpulse.com/studio/projects/data-acquisition/auto-labeler
- Peter Ing, "Beginners guide to Object Detection with Edge Impulse" (Medium): https://peter-ing.medium.com/beginners-guide-to-object-detection-with-edge-impulse-c8ea95f844a0
- Forum, "Use FOMO or YOLOV5 for object detection": https://forum.edgeimpulse.com/t/use-fomo-or-yolov5-for-object-detection/7473
- Forum, "Resize (fit, squash...), interpolation and other doubts": https://forum.edgeimpulse.com/t/resize-fit-squash-interpolation-and-other-doubts/8333
