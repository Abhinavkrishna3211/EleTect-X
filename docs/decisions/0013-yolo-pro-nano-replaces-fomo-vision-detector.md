# ADR 0013: Replace the FOMO vision detector with YOLO-Pro-nano (attention+SiLU)

- **Status:** accepted
- **Date:** 2026-08-28

## Context

The frozen architecture named FOMO (`fomo_mobilenet_v2_a35` @ 96×96, INT8) as the on-device vision
detector for the UNO Q + Arducam B0490. That baseline was trained 26 Aug on 3,280 Elephant + 3,280
Boar CC BY 4.0 Roboflow images under the free-tier Edge Impulse account, and its best held-out numbers
— Elephant F1 0.692 / recall 0.693, Boar F1 0.618 / recall 0.666 — were reached only after every stock
FOMO knob reachable on that account tier (resolution, cycle count, dataset top-up, class weighting) was
exhausted, documented as five separate single-variable trials in this file's iteration log. The
deployment bar is explicit: **≥92% recall per class individually**, not blended accuracy. The gap
between 0.693/0.666 and 0.92/0.92 was too large to close with further FOMO tuning alone.

Two things changed the available options after that baseline: Edge Impulse Enterprise went live on
this account (removing the 1-hour training-job cap that had pre-flight-blocked a 224px FOMO trial and
made EON Tuner moot), and the UNO Q + Arducam were physically connected, turning on-device latency from
an extrapolated estimate into a measurable number. Both unblocked a real architecture comparison for
the first time — the vision-rebuild plan's Phase 3 — rather than another FOMO-only tuning pass.

## Decision

Replace FOMO with **YOLO-Pro-nano, attention+SiLU variant** (Edge Impulse org model 6493,
`yolo-pro-nano-attn_silu`) as the vision detector for the UNO Q target.

Ran a same-corpus, same-protocol comparison (10,081 training / 2,834 testing images, identical
`score_held_out()` centroid-in-box scoring) across FOMO, both YOLO-Pro-nano variants, and SSD
MobileNetV2 FPN-Lite:

| Architecture | Elephant R / P / F1 | Boar R / P / F1 | Background FP rate |
|---|---|---|---|
| FOMO control (96px) | 0.751 / 0.867 / 0.723 | 0.495 / 0.849 / 0.427 | 0.277 |
| **YOLO-Pro-nano, attn_silu** | **0.855 / 0.974 / 0.812** | **0.761 / 0.978 / 0.703** | **0.048** |
| YOLO-Pro-nano, no_attn_relu | 0.812 / 0.982 / 0.768 | 0.711 / 0.978 / 0.651 | 0.057 |
| SSD MobileNetV2 FPN-Lite (320px) | unscored — see below | unscored | unscored |

attn_silu wins on every axis at once against FOMO — higher recall, higher precision, and a 5.8× lower
false-positive rate on background scenes, not a recall-for-precision trade — and also beats the
no-attention/ReLU variant of the same "nano" size class on every metric. After a confidence-threshold
sweep (`{0.05, 0.1, 0.2, 0.3, 0.5}`) on a clean retrain of the winning config, the best point (threshold
0.05) reached Elephant recall 0.914 / Boar recall 0.760 — Elephant close to the 92% bar for the first
time this project has produced, Boar still well short, at a Background false-positive rate (0.380) too
costly to ship as-is. **Neither class clears ≥92% recall at a threshold worth deploying yet** — this
ADR records the architecture decision, not a claim that the accuracy bar is met. The full sweep,
threshold table, and infrastructure findings live in `ml/vision/README.md`'s "27/28 Aug" entries; that
file is the source of truth for numbers and is expected to keep changing as data-quality work
continues, this ADR is not.

Real, measured on-device latency on the actual UNO Q (INT8-quantized CPU export,
`edge-impulse-linux-runner --fake-camera` against real board-captured frames): ~33.8 ms/inference
average, ~29.6 FPS — comfortably above what a trigger-on-motion camera-trap pipeline needs, so the
architecture change does not cost the field-deployment latency budget. The Adreno 702 GPU-delegate
export target was not benchmarkable this pass (see `docs/KNOWN_GAPS.md`'s "missing
`libtensorflowlite_gpu_delegate.so`" entry) — CPU alone already clears the requirement.

## Alternatives considered

- **Keep tuning FOMO.** Rejected — every stock knob reachable on the account this project has had
  access to (resolution ×3, cycle count, dataset top-up, class weighting) was already exhausted before
  this comparison ran, documented in the 23 Aug iteration-log entries. Continued tuning had no
  remaining lever left to pull.
- **YOLO-Pro-nano, no-attention+ReLU.** A real candidate, same model family and size class, plausibly a
  better fit for an Adreno GPU than an attention mechanism built with an NPU in mind. Rejected on
  measured numbers alone — it loses to attn_silu on every metric in the same comparison, not on a
  theoretical GPU-suitability argument that was never confirmed (the GPU delegate itself could not be
  benchmarked this pass, see above).
- **SSD MobileNetV2 FPN-Lite (320px).** Could not be scored. First attempt failed instantly on an input-
  size mismatch (a real script bug, fixed). The resolution-corrected retry OOM-killed once at the
  platform's default batch size; a batch-8 retry trained successfully but its evaluation artifacts were
  permanently lost in an unrelated infrastructure incident (a killed concurrent job orphaned the shared
  DSP block). Not re-attempted a third time — even before the loss, SSD was not leading the sweep on
  any axis, and burning another ~30-minute training slot this close to the 2 Sept trial for an
  architecture that was not competitive was not worth it. Recorded as a permanent, honest gap in the
  comparison table rather than a number quietly left as "pending."
- **EON Tuner's full custom search space.** The intended next escalation if the manual sweep plus
  threshold tuning did not close the gap to 92%. Failed with a real, understood API bug (`POST
  optimize/config` rejects `YOLO-Pro block not found` when the learn block was set up via
  `--configure-only` rather than an actual completed training job) and was not chased further — the
  Tuner was always the exploratory half of Phase 3, not the source of the current best result, and the
  better-understood remaining lever (Boar data-quality remediation — see the widened bounding-box audit
  in `ml/vision/README.md`) is a more direct shot at the actual gap.

## Consequences

+ Same-corpus comparison is real and reproducible — every number above is traced to a printed job log
  via `score_held_out()`, the same protocol used for every prior FOMO entry in the iteration log, so it
  is directly comparable rather than an architecture claim resting on a different dataset or scoring
  method.
+ Real, on-device-measured latency headroom (~30 FPS on CPU alone) means the architecture change costs
  nothing against the field-deployment latency/power budget this pass identified.
+ Materially better false-positive behavior on background scenes (0.048 vs 0.277 at default threshold)
  matters directly for an unattended forest deployment, where a lower nuisance-alert rate is itself a
  reliability property, not just an accuracy number.
- **Does not meet the ≥92%-per-class recall bar on its own.** Elephant reaches 0.914 at the most
  aggressive usable threshold tested; Boar reaches only 0.760. The remaining gap is understood to be
  primarily a data-quality problem, not an architecture problem — a widened bounding-box audit found
  material Boar-class contamination (domestic-pig misclassification, redaction-artifact boxes) whose
  only real remediation is a multi-day manual per-image relabel of ~9,200 images, out of scope before
  the 2 Sept trial. This ADR should not be read as "the model is ready" — see `ml/vision/README.md` and
  `HANDOVER.md` for the currently-open items gating that claim.
- SSD MobileNetV2 FPN-Lite and the EON Tuner search remain permanently unscored on this project absent
  a specific reason to revisit them — both are documented as deliberately not retried, not silently
  dropped.
- `device/mpu/perception`'s vision-capture path and `cognition/fusion.py`'s `VISION` modality are
  unaffected by this decision — the detector was benchmarked standalone, not wired into the live fusion
  path this pass (tracked separately in `docs/KNOWN_GAPS.md`).
