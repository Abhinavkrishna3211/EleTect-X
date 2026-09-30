# 0030 — The acoustic int8 question is reopened; ADR 0026 was decided against a different model

- Status: accepted
- Date: 2026-09-30
- Supersedes: [0026](0026-acoustic-ships-float32-not-int8.md)
- Outcome for today: **still float32**, but for none of ADR 0026's reasons

## Context

ADR 0026 concluded that the acoustic classifier ships float32, and it argued the point well. Every
number in it was measured against the model that existed on 23 September 2026: the MFE/Keras
classifier on Edge Impulse project **1109511**, whose EON build was **92,256 B of flash and
156,496 B of RAM**, and which classified a window in **1 ms**.

That is not the model that ships now. ADR 0027 reconciled the class scheme to a trained PANNs
model, and the deployed impulse is now a PANNs Cnn10 transfer on project **1110036**, whose float32
graph is **21.4 MB** and whose `.eim` is **27 MB**, of which 21.9 MB is the linked float32
`.tflite`. The two models differ by a factor of roughly 230 in size.

ADR 0026 does not claim to cover a successor model — it is explicit that it is about "the shipping
acoustic architecture (§7.1)". But it is written unconditionally ("The acoustic classifier ships as
float32"), it is the ADR anyone searching for the int8 decision will find, and its reasoning has
since been cited against a model it never measured. That is the gap this ADR closes.

The quantisation *recipe* has also changed, and this matters more than it looks. ADR 0026's int8
arm quantised the whole graph. `harness/export_panns.py` does not: it restricts int8 to `Conv` op
types, per-channel, with `reduce_range` (7-bit), and deliberately leaves `bn0`, the head's `Gemm`
and the `Softmax` in float — `bn0` normalises across mel bins and its rank-1 weight cannot take a
per-channel axis, and the head carries the calibrated scores §7.2's thresholds depend on. The
naive whole-graph variant is still on record and still broken: `cnn10_10s_int8.onnx` scores
**15.4%**, with gunshot recall **0.0**. Comparing that to ADR 0026's ~14-point drop is comparing
two instances of the same mistake.

## What was measured

`harness/calibration_int8.py`, over the frozen 605-clip test split, scoring `cnn10_10s_fp32.onnx`
against `cnn10_10s_int8_conv_rr.onnx` through the identical mel front end, keeping the full
probability vector for every clip. Results in `harness/calibration_int8.json`.

| | fp32 | int8 (Conv, per-channel, 7-bit) |
|---|--:|--:|
| graph size | 21.4 MB | **7.4 MB** |
| accuracy, argmax | 91.90% | 91.74% |
| accuracy at the 0.6 gate | 91.74% | 91.24% |
| expected calibration error (10 bins) | 0.0633 | 0.0641 |
| mean top-1 confidence | 0.9823 | 0.9801 |

Accuracy against threshold, with below-threshold windows counted wrong:

| threshold | 0.00 | 0.50 | 0.55 | 0.60 | 0.65 | 0.70 | 0.80 | 0.90 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| fp32 | 91.90% | 91.90% | 91.90% | 91.74% | 91.57% | 91.40% | 90.41% | 88.93% |
| int8 | 91.74% | 91.57% | 91.40% | 91.24% | 91.24% | 91.07% | 89.92% | 88.60% |
| delta | −0.17 | −0.33 | −0.50 | −0.50 | −0.33 | −0.33 | −0.50 | −0.33 |

The two curves are parallel and never more than **0.5 points** apart. Argmax agreement is 98.68%
(8 clips of 605 differ). At the 0.6 gate, 601 clips clear it under fp32 and 599 under int8: 2
gained, 4 lost.

## Every one of ADR 0026's four rationale bullets is void or inverted

1. **"Quantisation costs roughly 14 points of accuracy on this model."** On this model it costs
   **0.17 points** — one clip. The 14-point figure measured whole-graph quantisation of a small
   MFE net, not Conv-restricted quantisation of a PANNs backbone.
2. **"A collapse of calibration, not a rounding artefact"** (loss 0.557 → 3.279). Measured directly
   here rather than inferred from a loss value: **ECE 0.0633 → 0.0641**, and the accuracy-vs-threshold
   curves lie within half a point of each other at every gate. §7.2's per-class thresholds are the
   reason this had to be measured rather than assumed, and they survive. This was ADR 0026's
   strongest argument and it does not transfer.
3. **"int8 is not faster on this target — it is slower, 6 ms against 1 ms, because the float32
   graph is small enough to sit in cache."** That premise is *inverted* at 21.4 MB. A graph that
   size does not sit in the QRB2210's cache, and the quantise/dequantise overhead that could not be
   amortised over 1 ms has three orders of magnitude more arithmetic to amortise over here. The
   float32 side is now measured on target: **4,136-4,310 ms per 10 s window**, of which the
   classifier is **3,491-3,647 ms (84%)** and the DSP front end only 15-16%
   (`harness/onboard_latency.json`). So the cost is concentrated exactly where quantisation acts.
   The int8 side is still **unmeasured on target** and this ADR does not claim a direction for it —
   but ADR 0026's reason for expecting it to be negative is gone, and the 1 ms budget that made
   dequantisation overhead decisive is off by three orders of magnitude here.
4. **"The resource savings buy nothing — flash differs by 23 KB."** The difference is now
   **14 MB** on the graph (21.4 → 7.4), and would take the `.eim` from 27 MB to roughly 13 MB. On a
   board that has already filled its disk once, 14 MB per deployed model is not nothing.

   > **Correction, 30 September 2026.** This bullet originally justified itself with "`home_test`
   > writes ~890 MB/h and the root cause is unfixed". That rate is wrong by roughly 18x — the
   > measured rate is **~50 MB/h** — and the 890 figure came from attributing a `df -h /` reading
   > to `home_test`, which writes to a different partition (`/home/arduino` = mmcblk0p69, not
   > `/` = mmcblk0p68). The disk-pressure argument survives on its own terms (a 14 MB saving per
   > deployed model is still real), but it is a weaker argument than it was written as, and it
   > should not be cited with the 890 number.

## Decision

1. **ADR 0026 is superseded.** Its conclusion must not be cited for the PANNs model. Its reasoning
   remains correct for the 92 KB MFE model it measured, which is no longer deployed.
2. **The acoustic classifier still ships float32 today** — but as a status quo pending measurement,
   not as a decided trade-off. The reason is deployment route, not accuracy: Studio's deployment
   panel offered **no int8 option** for this impulse.

   > **Correction, 30 September 2026.** This ADR originally explained that as "consistent with the
   > learn block being custom and shipping its own ONNX." **That explanation is wrong.** Studio's
   > own impulse description for project 1110036 impulse 19 is:
   >
   > | block | id | type |
   > |---|--:|---|
   > | input | 94 | `time-series` |
   > | DSP | 95 | `organization` — "PANNs log-mel" |
   > | learn | 96 | `keras-transfer-kws` — "PANNs Cnn10 transfer" |
   >
   > The learn block is **`keras-transfer-kws`, a stock Edge Impulse block**. It is the *DSP*
   > block that is custom. So the premise the int8 explanation rested on does not hold, and the
   > question of why no int8 is offered is reopened rather than answered. A plausible replacement
   > hypothesis — that the custom DSP block disables the quantisation and EON flows wholesale,
   > which would also explain `hasEonCompiler: false` on every target for this project — is
   > **unverified** and must not be cited until it is.

3. **int8 is now the preferred candidate**, and the burden of proof has flipped. Shipping float32
   beyond the point where int8 is deployable needs a reason recorded here.

## What must happen before int8 can ship

- **Confirm why Studio offers no int8 for this impulse.** The original guess (custom learn block)
  is disproven above, so this is still open. What *is* now established is that the custom DSP
  block blocks hosted builds outright, which bounds where an answer can come from:

  > **Ruled out, 30 September 2026: the App Lab import route.** While checking whether the model
  > could be registered as an App Lab brick, the board's `arduino-app-cli` daemon turned out to
  > expose `PUT 127.0.0.1:8800/v1/models/ei/projects/{projectID}`, which asks Studio to build and
  > then installs the result. It cannot serve this purpose, for two independent reasons. First,
  > the precision is not the caller's to choose — `platform.EIDeploymentParams()` hardcodes
  > `{float32, tflite, runner-linux-aarch64}` for board name `unoq`, so there is no int8 path
  > through it at all. Second, the build it would trigger fails anyway: requesting
  > `runner-linux-aarch64` directly (job 54315745, `modelType=float32`) returned
  > *"Cannot build for \"runner-linux-aarch64\" as your project contains custom DSP blocks. Use
  > the C++ library export option and build locally."* Any route that depends on Edge Impulse's
  > hosted builders is closed while the impulse keeps the organisation DSP block; only the local
  > C++ export path works, which is what `ml/acoustic/ei_blocks/dsp-panns-logmel/cpp/` already
  > does. An int8 `.eim` for this model would have to be produced through that local path.
  >
  > This does not mean the model cannot be an App Lab brick — it now is one. The custom-model
  > route sidesteps Edge Impulse's builders entirely: `deployment/install/install-acoustic-brick.sh`
  > writes `model.eim` and `model.yaml` into `~/.arduino-bricks/models/<id>/` and the daemon picks
  > it up. What that route does *not* sidestep is the hosted build, so it still cannot produce an
  > int8 artefact; int8 would have to come out of the local C++ export like float32 does. The
  > brick and the precision question are independent, and only the brick is settled.
  >
  > **What the brick work does change is the cost of trying.** Producing the float32 artefact the
  > brick actually loads turned out to need more than "build locally": the brick container is
  > Ubuntu 20.04 (glibc 2.31) while the board's host is Debian 13 (glibc 2.41), and GCC 13 cannot
  > target glibc 2.31 at all — its own runtime references `_dl_find_object` (2.35) and
  > `__libc_single_threaded` (2.32), so no sysroot flag rescues it. The working recipe is a Focal
  > amd64 chroot with GCC 9.4, written up in
  > `ml/acoustic/ei_blocks/dsp-panns-logmel/cpp/README.md`. That recipe is now proven and
  > repeatable, so the local path is no longer speculative work for an int8 attempt — the
  > remaining unknown is whether Studio will emit int8 artefacts for this impulse at all, which is
  > the open question at the top of this list, not the build mechanics.
  >
  > **Confirmed again, 30 September 2026, on the UI target.** The refusal is not specific to
  > `runner-linux-aarch64`. Building the deployment panel's own **Arduino UNO Q** target ("An EIM
  > binary for the Arduino UNO Q CPU that implements the Edge Impulse Linux protocol") from Studio
  > returned the identical error for `arduino-uno-q` — job **54329923**, scheduled 14:25:03 and
  > failed 14:25:07: *"Cannot build for \"arduino-uno-q\" as your project contains custom DSP
  > blocks. Use the C++ library export option and build locally."* Two different targets, one
  > requested over the API and one through the UI, refuse for the same stated reason, so the
  > constraint belongs to the impulse and is not an artefact of a hand-written target string.
  >
  > The same screen narrows the int8 question without settling it. **Model optimizations and
  > performance** offers exactly one row — *Unoptimized (float32)*, pre-selected, estimated at
  > 4,134 ms latency, 20.9 MB flash and 87.77% accuracy for the QRB2210 — and no int8 row is
  > present to select. That rules out the simplest explanation, that an int8 option exists and was
  > overlooked, and it is consistent with the unverified hypothesis above. It is not proof of the
  > mechanism: an absent row shows the option is not offered, not why it is not offered. Cite it
  > as evidence, not as the answer.

- **Measure int8 on the QRB2210.** The float32 baseline now exists (above, and §7.6 of the
  acoustic report); the int8 arm does not. Bullet 3 removes ADR 0026's reason to expect int8 to be
  slower, and the 84% of the budget sitting in the classifier says the lever is pointed the right
  way, but neither establishes that it is faster. Only the measurement does.
- **Re-run `calibration_int8.py` against whatever int8 artefact would actually ship**, not against
  the harness ONNX. The numbers above describe `cnn10_10s_int8_conv_rr.onnx` through onnxruntime.
  An Edge Impulse int8 `.eim` is a different artefact and inherits none of this evidence.

## Consequences

- ADR 0026's operational instructions stand until int8 actually ships: do not pass `--quantized`
  for acoustic, and leave `selectedModelType` at float32.
- ADR 0026's verification trap is worth restating because it is still live and still catches
  people: `POST /jobs/classify` silently ignores `selectedModelType` and always scores float32, so
  Studio's test view **cannot** confirm which precision is deployed. Confirm from the built `.eim`.
- `docs/research/platform/edge-impulse-linux-inference.md` concluded "ship the CPU int8 EON `.eim`"
  repository-wide. ADR 0026 narrowed that to vision-only. With this ADR the acoustic exception is
  provisional rather than principled, and that note is closer to right than ADR 0026 allowed.
- The vision track is unaffected.

## Alternatives considered

- **Leave ADR 0026 standing and note the model change elsewhere.** Rejected. The ADR is where
  someone looks for this decision, its conclusion is stated unconditionally, and its central
  evidence is a 14-point accuracy claim that is wrong by two orders of magnitude for the current
  model. Leaving that in place as accepted guidance is how a stale decision outlives its premise.
- **Decide to ship int8 now.** Rejected as premature: the deployment route does not exist yet, and
  the measurements above are of a harness ONNX rather than of a shippable artefact.
- **Quantisation-aware training.** Still deferred, and now clearly unnecessary — post-training
  Conv-restricted quantisation already costs 0.17 points. ADR 0026 deferred QAT against a 14-point
  gap that this recipe does not have.
