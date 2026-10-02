# Edge Impulse custom blocks

Two custom blocks that reconstruct this project's acoustic classifier inside an
Edge Impulse project, so the Studio impulse is the same model as
[`../harness/`](../harness/) rather than an approximation of it.

| block | kind | what it does |
| --- | --- | --- |
| [`dsp-panns-logmel/`](dsp-panns-logmel/) | processing | log-mel in PANNs' exact convention |
| [`learn-panns-cnn10/`](learn-panns-cnn10/) | learning | frozen PANNs Cnn10 + a trained head, exported to ONNX |

The impulse is `time-series (audio) → PANNs log-mel → PANNs Cnn10 transfer`.

[`TUTORIAL_NOTES.md`](TUTORIAL_NOTES.md) is the build narrative behind these
blocks — the order things were built in, the platform constraints that shaped
them, and the failures that produced the checks below.

## Why custom blocks and not the stock ones

The classifier is an AudioSet-pretrained PANNs Cnn10 backbone with its released
weights frozen, and a small head trained on its 512-d embedding. Full rationale
and measurements are in [`../ACOUSTIC_MODEL_REPORT.md`](../ACOUSTIC_MODEL_REPORT.md);
the short version is that the project's ~1.7k-clip corpus is a data ceiling, not
a capacity ceiling, so the accuracy comes from the pretraining rather than from
the architecture. On the frozen 605-clip test split that is **91.9% overall**
against **~82%** for the MFE + Keras impulse it replaces, and the gap on chainsaw
recall is the largest single difference.

Both stock blocks are unusable for that model, for different reasons.

**MFE is a different front end.** Frozen pretrained convolutions cannot adapt to
a changed input distribution — that is the whole point of freezing them — so the
front end has to be the one the weights were trained on. MFE differs in three
ways that matter:

- it sets every bin below a configurable noise floor to zero, where PANNs applies
  no floor beyond `amin = 1e-10` and keeps large negative log values;
- it normalises per window, where PANNs folds input normalisation into the
  backbone's own `bn0` batch-norm layer;
- its default filterbank geometry is not PANNs' (64 Slaney-normalised filters,
  50–14000 Hz, over a **power** spectrum, 1024-point Hann STFT, 320-sample hop,
  at 32 kHz).

**`keras-transfer-kws` rejects the window.** It caps windows at 1000 ms because
it exists for single spoken keywords. General audio backbones are run at 10 s,
and this project's two evaluated configurations are 10 s and 3 s.

## Verification

Each block carries its own check, and both pass on the current tree. Run them
before pushing a block.

```
cd dsp-panns-logmel   && python parity_check.py
cd learn-panns-cnn10  && python vendor_check.py
```

`parity_check.py` is the load-bearing one. It runs the real torchlibrosa
`Spectrogram` + `LogmelFilterBank` modules — the same objects the backbone
instantiates — against `dsp.logmel` on real test-split clips, and asserts on two
quantities:

| quantity | measured | tolerance |
| --- | --- | --- |
| log-mel, cells within 80 dB of clip peak | 2.06e-04 dB | 1e-02 dB |
| Cnn10 embedding, relative to its own scale | 1.24e-05 | 1e-03 |

It deliberately does **not** assert on synthetic signals, and reports them
instead. The two implementations reach the same quantity by different numerical
routes — torchlibrosa computes the STFT as a conv1d against a DFT matrix and
projects with `matmul(spectrogram, melW)`; the block uses an FFT and
`melW @ power`. Both accumulate 513 float32 products per mel bin in different
orders. A pure 440 Hz tone leaves most bins pinned at the `amin` clamp floor
around −95 dB, where that rounding becomes a large *relative* error and dB
magnifies it to ~5e-2. On real audio, and on any cell carrying signal, the
disagreement is ~1e-4 dB. Asserting on the tone would be asserting on float32
noise.

`vendor_check.py` guards a duplicate. Edge Impulse uploads a block directory and
nothing outside it, so `panns_small.py` has to exist inside the learning block as
well as in the harness. The released checkpoints only load into the exact
architecture, so drift between the two copies surfaces as a `state_dict` key
mismatch partway through a Studio training run — a long way from the edit that
caused it. The check is a SHA-256 comparison; re-copy with
`cp ../../harness/panns_small.py .` if it fails.

## Pushing

Both blocks are Docker-based. The processing block runs on Edge Impulse
infrastructure for enterprise organisations; on a free or developer project it
runs locally behind an ngrok tunnel via `edge-impulse-blocks runner` and cannot
produce optimised native DSP code.

```
cd dsp-panns-logmel   && edge-impulse-blocks init && edge-impulse-blocks push
cd learn-panns-cnn10  && edge-impulse-blocks init && edge-impulse-blocks push
```

The learning block's image bakes both AudioSet checkpoints in at build time
(~70 MB combined) rather than fetching them per run, so a training run does not
depend on Zenodo being reachable and every run provably uses the same weights.

## Learning block contract

Edge Impulse writes into `--data-directory`:

| file | shape | contents |
| --- | --- | --- |
| `X_split_train.npy`, `X_split_test.npy` | `(n, frames × 64)` float32 | flattened processing-block output |
| `Y_split_train.npy`, `Y_split_test.npy` | `(n, classes)` int32 | one-hot, one column per class |

A classification job hands the block **one-hot** rows. The arrays the API
serves for the same data at `/dsp-data/{id}/y/...` are a different thing —
`label_index, sample_id, slice_start_ms, slice_end_ms` — and for a four-class
problem the two are both `(n, 4)` int32, so they cannot be told apart by shape.
`class_indices()` recognises the one-hot case by its contents. Reading column 0
unconditionally, as this block did until 29 Sept 2026, silently trains a binary
"class 0 vs everything else" model that reports a high accuracy against its own
wrong labels. [`TUTORIAL_NOTES.md`](TUTORIAL_NOTES.md) Part 7 has the full
diagnosis.

`train.py` reads class names from `--info-file`, refuses any feature width that
is not a multiple of 64 mel bins (which is what an MFE-backed impulse would
produce), embeds every window once through the frozen backbone, trains the head
over those embeddings, prints per-class recall and precision, and writes
`model.onnx` to `--out-directory`.

The exported graph takes the **flattened** log-mel window and reshapes inside
the graph, so it consumes Edge Impulse's feature vector directly with no
host-side reshape to get wrong. The `StandardScaler` is an affine map and is
folded into the first head layer rather than left as a preprocessing step
someone has to remember.

Verified on a 112-clip fixture at 3 s: `model.onnx` is 21.4 MB, **opset 17,
IR version 8**, input `features [1, 19264]`, output `probabilities [1, 4]`, and
its predictions match the trained PyTorch model exactly.

That opset is not automatic. `torch.onnx.export` has defaulted to the dynamo
exporter since torch 2.6, and that backend treats `opset_version` as advisory —
it emits opset 18 whatever the call asks for, silently. Under opset 18
`ReduceMean` and `ReduceMax` take their axes as a second input rather than an
attribute, which converters built against 17 reject outright; Edge Impulse's own
server-side ONNX to TensorFlow Lite step is one of them. This block passes
`dynamo=False` to pin the TorchScript exporter.
[`../harness/export_panns.py`](../harness/export_panns.py) was emitting opset 18
for the same reason and now does the same, and asserts on the emitted opset
afterwards so the substitution cannot come back unnoticed.

## Reproducing the published scores

The blocks reproduce the harness *method*, not its exact test split — Edge
Impulse owns the train/test division inside a project, while the harness scores
against a frozen 605-clip split with group-aware separation. Expect close
agreement, not identical numbers, and quote the harness figures as the
measured result.

Two settings must match the configuration being reproduced:

- **window length.** 10 s for the headline 91.9%; 3 s for the low-latency
  configuration (91.6% overall, and the best elephant-call recall at 96.6%).
- **peak crop.** The harness's 3 s numbers use `--crop peak`, which centres the
  window on the loudest 100 ms because a fixed head crop of a 10 s clip can miss
  a transient entirely and so understates what a sliding detector sees. The DSP
  block exposes this as *Centre on loudest 100 ms*, **off by default**. Leave it
  off for deployment: Edge Impulse already slides the window over the stream, so
  a transient cannot fall outside it, and re-centring on device would make the
  deployed features differ from the ones the impulse was tested on.

## Classes

`ambient`, `chainsaw`, `elephant_call`, `gunshot` — the four the wire protocol
carries, per [ADR 0027](../../docs/decisions/0027-acoustic-class-scheme-reconciled-to-trained-model.md).
`train.py` takes its class names and ordering from `--info-file`, so it does not
hard-code them, but an impulse trained on a different label set will not drop
into the device's `AcousticClass` enum without a matching ADR.
