# 0026 — The acoustic classifier ships float32; the int8 rule is vision-only

- Status: **superseded by [0030](0030-acoustic-int8-reopened-against-the-panns-model.md)**
- Date: 2026-09-23
- Supersedes: nothing
- Superseded by: [0030](0030-acoustic-int8-reopened-against-the-panns-model.md) — every
  measurement below is of the 92 KB MFE model on project 1109511, which is no longer
  deployed. Do not cite this ADR for the PANNs model.
- Narrows: `docs/research/platform/edge-impulse-linux-inference.md` ("Ship the CPU int8 EON `.eim`")

## Context

`docs/research/platform/edge-impulse-linux-inference.md` concludes with a repository-wide
instruction to ship the int8 EON `.eim`. That conclusion was reached on the **vision** track,
where the model is large, the frame budget is ~138 ms, and int8 plus XNNPACK on the Cortex-A53
is the difference between a usable frame rate and an unusable one.

The acoustic classifier is a different size class, and applying the same rule to it was never
separately justified. Edge Impulse profiles `arduino-unoq` directly — it is this project's
default target — so the comparison can be made on the real board rather than argued from
first principles.

For the shipping acoustic architecture (`ml/acoustic/ACOUSTIC_MODEL_REPORT.md` §7.1):

| build | validation accuracy | validation loss | latency (`arduino-unoq`) | EON flash | EON RAM |
|---|--:|--:|--:|--:|--:|
| **float32** | **87.4%** | 0.557 | **1 ms** | 92,256 B | 156,496 B |
| int8 | 72.9% | 3.279 | 6 ms | 69,072 B | 44,312 B |

Those validation figures are one training run. Edge Impulse's training is bit-reproducible
per worker machine and not across machines (acoustic report section 5), so they move between
runs; a second run of the same script measured 86.4%/0.554 float32 against 72.2%/2.895 int8.
**The decision does not rest on the exact figures.** What is stable across runs is the shape:
the float32-to-int8 accuracy drop is ~14 points either way, and the latency ordering (1 ms
against 6 ms) and the flash and RAM figures are identical in both runs, because those are
properties of the compiled graph rather than of the trained weights.

## Decision

**The acoustic classifier ships as float32.** The int8 guidance in the platform research note
applies to the vision track only, and that note should be read as vision-scoped from here on.

## Rationale

- **Quantisation costs roughly 14 points of accuracy on this model.** Validation loss moves 0.557 to
  3.279 in one run and 0.554 to 2.895 in another — a five- to sixfold increase either way, which
  is a collapse of calibration, not a rounding artefact. Section 7.2 of the acoustic report sets the operating point with *per-class
  probability thresholds* rather than argmax, so calibrated scores are load-bearing here in a
  way they are not for an argmax classifier. An int8 build would invalidate those thresholds.
- **int8 is not faster on this target.** It is *slower* — 6 ms against 1 ms — because the
  float32 graph is small enough to sit in cache while the int8 path pays quantise/dequantise
  overhead it cannot amortise. The int8 argument is a latency argument, and on this model the
  latency evidence runs the other way.
- **The resource savings buy nothing.** Flash differs by 23 KB on a Linux MPU with a filesystem.
  The RAM saving (44 KB against 156 KB) is real but immaterial against the QRB2210's budget;
  it would matter on the STM32 MCU, which does not run this model — ADR 0007 §4 places
  classification on the MPU.
- **Both builds are far inside budget.** At 1 ms and 6 ms against a duty-cycled acoustic
  window, precision is simply not the constraint. When a choice costs ~14 accuracy points and
  buys no headroom that is needed, it is not a trade-off.

## Consequences

- The acoustic `.eim` must be built and deployed with the float32 model variant explicitly
  selected. The runner's `--quantized` flag must **not** be passed for acoustic.
- `selectedModelType` must be left at `float32` on Edge Impulse project 1109511, and
  `ml/acoustic/README.md` records the standing obligation to leave that project on its
  best-known configuration.
- **A verification trap to be aware of:** `POST /jobs/classify` silently ignores
  `selectedModelType` and always scores float32 (acoustic report §2.5). Studio's test view
  therefore reports identical numbers for both precisions and **cannot** be used to confirm
  which variant is deployed. Confirm the shipped precision from the built `.eim` or the Deploy
  job's own output, never from the test view.
- The vision track is unaffected and continues to ship int8.

## Alternatives considered

- **Ship int8 for consistency across tracks.** Rejected: consistency is not a reason to give up
  ~14 accuracy points on a deployment where forest officers and residents depend on the
  alerts being right.
- **Quantisation-aware training to recover the int8 loss.** Deferred, not rejected. It could
  close some of the gap, but it only becomes worth the effort if a future target makes the RAM
  saving necessary. Nothing on the current bill of materials does.
