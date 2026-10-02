"""Export a PANNs backbone plus its trained head as one ONNX graph, and quantize it.

Why this file exists. The acoustic report's section 7.5 recommends a PANNs
backbone over the Edge Impulse MFE net on a measured 10-point overall gap and a
41-point chainsaw gap, but records that none of them has ever been exported or
benchmarked on the QRB2210. That is the open question this closes: it produces an
artifact that can be timed on the target, and it measures what int8 quantization
costs before anyone ships it.

Cnn6 (5.9M params, 9.9 GMAC at a 10 s window) and Cnn10 (6.3M, 13.0 GMAC) share
an identical eval-mode forward pass and differ only in the convolution block, so
both are exported by the same code path. Cnn14 is not offered: at 81M parameters
it is a ceiling measurement, not a deployment candidate.

Two deliberate boundaries.

  * The graph takes a **log-mel spectrogram**, not a waveform. Torchlibrosa
    implements the STFT as a conv1d against a DFT matrix, which costs roughly
    1 GMAC at a 10 s window - a tenth of the whole backbone - for a transform an
    FFT does in about 10 MMAC. Keeping the front end off the graph moves that
    work to an FFT on the host and confines the quantizable part to the
    convolution stack, which is where int8 actually buys something.

  * The head is refit here rather than loaded, because train_head.py reports
    scores and discards its models. It is refit with the same seed, the same
    oversampling and the same scaler, so the exported head is the one whose
    accuracy that script published rather than a retrained approximation. The
    embedding parity check against the cached features is what proves the
    backbone half of that claim.

Outputs land in ml/acoustic/harness/ and are gitignored, being model binaries.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SAMPLE_RATE = 32000
HOP = 320
N_FFT = 1024
MELS = 64


def frames_for(seconds: float) -> int:
    """Torchlibrosa pads with center=True, so a clip yields 1 + n//hop frames."""
    return 1 + int(SAMPLE_RATE * seconds) // HOP


CKPT = {"cnn6": "Cnn6_mAP=0.343.pth", "cnn10": "Cnn10_mAP=0.380.pth"}


def build_backbone(arch: str, device: str = "cpu"):
    """The named PANNs backbone with its released AudioSet weights, in eval mode."""
    import torch

    from panns_small import Cnn6, Cnn10

    cls = {"cnn6": Cnn6, "cnn10": Cnn10}[arch]
    m = cls(sample_rate=SAMPLE_RATE, window_size=N_FFT, hop_size=HOP, mel_bins=MELS,
            fmin=50, fmax=14000, classes_num=527)
    ckpt = os.path.join(os.path.expanduser("~"), "panns_data", CKPT[arch])
    m.load_state_dict(torch.load(ckpt, map_location=device, weights_only=False)["model"])
    return m.eval().to(device)


def logmel(model, wav: np.ndarray):
    """The exact front end the cached embeddings were built with, run standalone."""
    import torch

    with torch.no_grad():
        return model.logmel_extractor(model.spectrogram_extractor(torch.from_numpy(wav)))


def make_module(backbone, scaler, clf):
    """Fold scaler and sklearn MLP onto the backbone as one graph on log-mel input."""
    import torch
    from torch import nn

    class Exported(nn.Module):
        def __init__(self):
            super().__init__()
            self.bn0 = backbone.bn0
            self.cb1, self.cb2 = backbone.conv_block1, backbone.conv_block2
            self.cb3, self.cb4 = backbone.conv_block3, backbone.conv_block4
            self.fc1 = backbone.fc1
            # StandardScaler is an affine map, so it folds into the first head
            # layer rather than becoming two more ops on the graph.
            w0 = torch.tensor(clf.coefs_[0].T / scaler.scale_, dtype=torch.float32)
            b0 = torch.tensor(
                clf.intercepts_[0] - clf.coefs_[0].T @ (scaler.mean_ / scaler.scale_),
                dtype=torch.float32)
            self.h0 = nn.Linear(w0.shape[1], w0.shape[0])
            self.h0.weight.data, self.h0.bias.data = w0, b0
            self.rest = nn.ModuleList()
            for w, b in zip(clf.coefs_[1:], clf.intercepts_[1:], strict=True):
                lin = nn.Linear(w.shape[0], w.shape[1])
                lin.weight.data = torch.tensor(w.T, dtype=torch.float32)
                lin.bias.data = torch.tensor(b, dtype=torch.float32)
                self.rest.append(lin)

        def embed(self, mel):
            x = self.bn0(mel.transpose(1, 3)).transpose(1, 3)
            x = self.cb1(x, pool_size=(2, 2), pool_type="avg")
            x = self.cb2(x, pool_size=(2, 2), pool_type="avg")
            x = self.cb3(x, pool_size=(2, 2), pool_type="avg")
            x = self.cb4(x, pool_size=(2, 2), pool_type="avg")
            x = torch.mean(x, dim=3)
            x = torch.max(x, dim=2)[0] + torch.mean(x, dim=2)
            return torch.relu(self.fc1(x))

        def forward(self, mel):
            x = torch.relu(self.h0(self.embed(mel)))
            for i, lin in enumerate(self.rest):
                x = lin(x)
                if i < len(self.rest) - 1:
                    x = torch.relu(x)
            return torch.softmax(x, dim=1)

    return Exported().eval()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arch", default="cnn10", choices=("cnn6", "cnn10"))
    ap.add_argument("--emb", default=None, help="defaults to embeddings_<arch>_base.npz")
    ap.add_argument("--split", default=os.path.join(HERE, "split.json"))
    ap.add_argument("--window", type=float, default=10.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--calib", type=int, default=128,
                    help="training clips used to calibrate int8 activation ranges")
    ap.add_argument("--out-prefix", default=None)
    ap.add_argument("--quant-ops", default="Conv",
                    help="comma-separated op types to quantize; Conv alone carries "
                         "~99.9%% of the MACs and leaves the fragile ops in float")
    ap.add_argument("--no-per-channel", action="store_true")
    ap.add_argument("--calib-method", default="MinMax",
                    choices=("MinMax", "Entropy", "Percentile", "Distribution"),
                    help="MinMax lets one outlier set the scale for the whole tensor; "
                         "the log-mel input spans 131 dB with a hard floor, so the "
                         "alternatives usually matter here")
    ap.add_argument("--crop", default="head", choices=("head", "peak"),
                    help="must match the --crop the embeddings were extracted with, or the "
                         "head is fitted on one view of a clip and served another; the "
                         "parity check below will fail loudly if they disagree")
    ap.add_argument("--reduce-range", action="store_true",
                    help="quantize weights to 7 bits. On x86 without VNNI the u8s8 "
                         "kernel accumulates into int16 and saturates, which is "
                         "silent and costs tens of points of accuracy; 7-bit weights "
                         "are the documented mitigation. Cortex-A53 does not use "
                         "that kernel, so this trades a little precision for a "
                         "number that is trustworthy on the host as well.")
    ap.add_argument("--tag", default="", help="suffix distinguishing quantization variants")
    args = ap.parse_args()

    import torch

    from embed import load_clip
    from train_head import apply_split, balance_idx

    emb = args.emb or os.path.join(HERE, f"embeddings_{args.arch}_base.npz")
    prefix = args.out_prefix or os.path.join(HERE, f"{args.arch}_{args.window:g}s")
    with open(args.split, encoding="utf-8") as fh:
        spec = json.load(fh)
    rec = {r["file"]: r for r in spec["records"]}
    cached = np.load(emb, allow_pickle=True)
    d = cached
    # apply_split returns the authoritative split label per kept row, in the
    # frozen file's order - not the spec, and not the cache's stale labels.
    split, X, y, fname = apply_split(args.split, d["fname"], d["X"], d["label"], d["fname"])
    is_tr = split == "train"
    print(f"embeddings {X.shape}  train {is_tr.sum()}  test {(~is_tr).sum()}")

    # Head refit exactly as train_head.fit_once does for --head mlp --balanced.
    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import StandardScaler

    Xtr, ytr = X[is_tr], y[is_tr]
    sel = balance_idx(ytr, args.seed)
    Xtr, ytr = Xtr[sel], ytr[sel]
    scaler = StandardScaler().fit(Xtr)
    codes, enc = np.unique(ytr, return_inverse=True)
    clf = MLPClassifier(hidden_layer_sizes=(512, 256), alpha=1e-3, batch_size=128,
                        learning_rate_init=8e-4, max_iter=400, early_stopping=True,
                        n_iter_no_change=25, validation_fraction=0.12,
                        random_state=args.seed)
    clf.fit(scaler.transform(Xtr), enc)
    print(f"head fitted, classes {list(codes)}")

    backbone = build_backbone(args.arch)
    mod = make_module(backbone, scaler, clf)

    # Proof that the exported graph is the measured one: run the folded backbone
    # over real audio and compare against the cached embedding it was scored on.
    # The gate is the cache's own window and crop, not the split's. Gating on
    # the split disabled this check for every window except the split's own -
    # that is, for exactly the sweep where a mismatch is most likely.
    cache_window = float(cached["window_s"]) if "window_s" in cached else spec["window_s"]
    cache_crop = str(cached["crop"]) if "crop" in cached else "head"
    if abs(args.window - cache_window) < 1e-9 and args.crop == cache_crop:
        probe = [rec[f] for f in fname[:4]]
        wav = np.stack([load_clip(r["path"], args.window, args.crop) for r in probe])
        with torch.no_grad():
            got = mod.embed(logmel(backbone, wav)).numpy()
        err = float(np.abs(got - X[:4]).max())
        verdict = "OK" if err < 1e-3 else "MISMATCH"
        print(f"embedding parity vs cache: max abs err {err:.3e}  {verdict}")
        if verdict == "MISMATCH":
            raise SystemExit("exported backbone does not reproduce the cached embeddings")
    else:
        raise SystemExit(
            f"--window {args.window:g} --crop {args.crop} does not match the cache "
            f"({cache_window:g}s, {cache_crop}); the head would be fitted on one view "
            f"of each clip and served another. Re-extract with matching settings.")

    frames = frames_for(args.window)
    fp32 = prefix + "_fp32.onnx"
    # dynamo=False pins the TorchScript exporter. From torch 2.6 the dynamo
    # exporter is the default, and it treats opset_version as advisory: it
    # emits opset 18 regardless, where ReduceMean and ReduceMax take their axes
    # as a second input rather than an attribute. Converters built against
    # opset 17 reject those nodes outright ("input size 2 not in range
    # [min=1, max=1]"), which rules the graph out of several deployment paths
    # for no gain. The opset assertion below exists because that substitution
    # is silent - nothing warned that the requested version had been ignored.
    #
    # external_data is a dynamo-only argument. The TorchScript exporter keeps
    # weights inline anyway, which is what the quantizer needs: it reloads the
    # graph from a temp directory it copies only the .onnx into, so a sidecar
    # .onnx.data would be left behind and the reload would fail on a missing
    # tensor.
    torch.onnx.export(mod, torch.randn(1, 1, frames, MELS), fp32,
                      input_names=["mel"], output_names=["probs"], opset_version=17,
                      dynamo=False)

    import onnx

    emitted = {o.domain or "ai.onnx": o.version for o in onnx.load(fp32).opset_import}
    if emitted.get("ai.onnx") != 17:
        raise SystemExit(f"expected opset 17, exporter emitted {emitted}")
    print(f"wrote {os.path.basename(fp32)}  ({os.path.getsize(fp32) / 1e6:.1f} MB, "
          f"mel input 1x1x{frames}x{MELS})")

    from onnxruntime.quantization import (
        CalibrationDataReader,
        CalibrationMethod,
        QuantFormat,
        QuantType,
        quantize_static,
    )
    from onnxruntime.quantization.shape_inference import quant_pre_process

    rng = np.random.default_rng(args.seed)
    tr_names = fname[is_tr]
    pick = rng.choice(len(tr_names), min(args.calib, len(tr_names)), replace=False)
    cache = f"{prefix}_calib{args.calib}_s{args.seed}.npy"
    if os.path.exists(cache):
        mels = list(np.load(cache))
        print(f"reusing {len(mels)} cached calibration mels")
    else:
        print(f"computing {len(pick)} calibration mels ...", flush=True)
        mels = []
        for n, i in enumerate(pick):
            wav = load_clip(rec[tr_names[i]]["path"], args.window, args.crop)[None, :]
            mels.append(logmel(backbone, wav).numpy())
            if (n + 1) % 32 == 0:
                print(f"  {n + 1}/{len(pick)}", flush=True)
        np.save(cache, np.stack(mels))

    class Reader(CalibrationDataReader):
        def __init__(self, data):
            self.it = iter([{"mel": m} for m in data])

        def get_next(self):
            return next(self.it, None)

    # Quantizing the whole graph destroys it: bn0 normalises across mel bins and
    # its rank-1 weight cannot take a per-channel axis, and the head's Gemm and
    # Softmax carry the calibrated scores section 7.2's thresholds depend on.
    # Restricting to Conv keeps the arithmetic that matters in int8 and leaves
    # 394k MAC of head - 0.003% of the model - in float.
    ops = [o.strip() for o in args.quant_ops.split(",") if o.strip()]
    prepped = prefix + "_prep.onnx"
    quant_pre_process(fp32, prepped, skip_symbolic_shape=True)
    int8 = f"{prefix}_int8{args.tag}.onnx"
    quantize_static(prepped, int8, Reader(mels), quant_format=QuantFormat.QDQ,
                    activation_type=QuantType.QUInt8, weight_type=QuantType.QInt8,
                    per_channel=not args.no_per_channel, op_types_to_quantize=ops,
                    reduce_range=args.reduce_range,
                    calibrate_method=getattr(CalibrationMethod, args.calib_method))
    os.remove(prepped)
    print(f"quantized op types: {ops}  per_channel={not args.no_per_channel}  "
          f"calibration={args.calib_method}  reduce_range={args.reduce_range}")
    print(f"wrote {os.path.basename(int8)}  ({os.path.getsize(int8) / 1e6:.1f} MB)")

    meta = {"arch": args.arch, "quant_ops": ops, "calib_method": args.calib_method,
            "reduce_range": args.reduce_range,
            "window_s": args.window, "frames": frames, "mels": MELS, "hop": HOP,
            "n_fft": N_FFT, "sample_rate": SAMPLE_RATE, "classes": [str(c) for c in codes],
            "seed": args.seed, "fp32": os.path.basename(fp32), "int8": os.path.basename(int8)}
    with open(prefix + "_meta.json", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    print(f"wrote {os.path.basename(prefix)}_meta.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
