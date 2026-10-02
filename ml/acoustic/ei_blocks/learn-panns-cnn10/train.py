"""Edge Impulse custom learning block: frozen PANNs Cnn10 + a trained head.

This is the Studio-side reconstruction of ml/acoustic/harness - the same
backbone, the same frozen weights, the same head geometry and the same class
balancing - so the Edge Impulse project reproduces the numbers in
../../ACOUSTIC_MODEL_REPORT.md rather than approximating them.

Input. Edge Impulse writes `X_split_train.npy` / `X_split_test.npy` as float32
arrays of flattened processing-block output, and `Y_split_*.npy` as int32 with
columns (label_index, sample_id, slice_start_ms, slice_end_ms). The X rows must
come from the PANNs log-mel block next door: the backbone is frozen, so it
cannot adapt to a different front end, and MFE output would quietly cost most of
the transfer.

Why the backbone is frozen. The corpus is ~1.7k clips. ml/acoustic/README.md
already established that a from-scratch net saturates here - the ceiling is
data, not capacity - and fine-tuning 6.3M parameters on this much audio moves
the representation away from the AudioSet one without anything to replace it.
Freezing also makes training cheap enough to run without a GPU: the embeddings
are computed once and every epoch after that is a two-layer MLP over 512 floats.

Output. `model.onnx` in the output directory, taking the flattened log-mel
window and returning class probabilities, so the graph the Studio profiles is
the whole classifier and not just the head.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

SAMPLE_RATE = 32000
HOP = 320
N_FFT = 1024
MEL_BINS = 64

CHECKPOINTS = {
    "cnn6": ("Cnn6_mAP=0.343.pth",
             "https://zenodo.org/record/3960586/files/Cnn6_mAP%3D0.343.pth?download=1"),
    "cnn10": ("Cnn10_mAP=0.380.pth",
              "https://zenodo.org/record/3960586/files/Cnn10_mAP%3D0.380.pth?download=1"),
}

# The Dockerfile bakes the checkpoint in at build time so training does not
# depend on Zenodo being reachable from a build runner. The download path stays
# as a fallback for running this script directly on a workstation.
CKPT_DIR = os.environ.get("PANNS_CKPT_DIR", os.path.join(os.path.expanduser("~"), "panns_data"))


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--info-file", type=str, required=False,
                    help="train_input.json, which carries the class names")
    ap.add_argument("--data-directory", type=str, required=True)
    ap.add_argument("--out-directory", type=str, required=True)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--learning-rate", type=float, default=8e-4)
    ap.add_argument("--backbone", type=str, default="cnn10", choices=("cnn10", "cnn6"))
    # Edge Impulse renders a boolean parameter as the strings "true"/"false".
    ap.add_argument("--balanced", type=str, default="true")
    ap.add_argument("--label-smoothing", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=0)
    return ap.parse_args()


def load_backbone(arch: str):
    """The named PANNs backbone with its released AudioSet weights, frozen."""
    import torch
    from panns_small import Cnn6, Cnn10

    name, url = CHECKPOINTS[arch]
    path = os.path.join(CKPT_DIR, name)
    if not os.path.exists(path):
        import urllib.request

        os.makedirs(CKPT_DIR, exist_ok=True)
        print(f"downloading {name} ...", flush=True)
        urllib.request.urlretrieve(url, path)

    model = {"cnn6": Cnn6, "cnn10": Cnn10}[arch](
        sample_rate=SAMPLE_RATE, window_size=N_FFT, hop_size=HOP,
        mel_bins=MEL_BINS, fmin=50, fmax=14000, classes_num=527,
    )
    model.load_state_dict(torch.load(path, map_location="cpu", weights_only=False)["model"])
    model.eval()
    for p in model.parameters():
        p.requires_grad_(False)
    return model


def bn0_affine(backbone, frames: int):
    """bn0's eval-mode transform, tiled across the flattened log-mel row.

    bn0 normalises per mel bin. The backbone is frozen and never leaves eval
    mode, so bn0 is a fixed affine map and folding it is exact. It is applied
    to the flat input rather than to the 4-d tensor because the flat form has
    no channel axis to disagree about - see backbone_forward.
    """
    import torch

    bn = backbone.bn0
    with torch.no_grad():
        inv = torch.rsqrt(bn.running_var + bn.eps)
        scale = (bn.weight * inv).numpy()
        shift = (bn.bias - bn.running_mean * bn.weight * inv).numpy()
    # Tiled in numpy and handed back as fresh tensors so the ONNX export sees
    # two initializers. Doing it with Tensor.repeat traces as Tile/Expand
    # instead, which is more graph for the converter to get wrong.
    return (torch.from_numpy(np.tile(scale, frames)),
            torch.from_numpy(np.tile(shift, frames)))


def backbone_forward(backbone, flat, frames: int):
    """Cnn10's 512-d embedding from flattened (batch, frames * mels) log-mel rows.

    The vendored `forward` runs its own STFT and its training-mode dropout, and
    returns AudioSet's 527 logits. None of that is wanted here, so the eval-mode
    convolution stack is spelled out. This matches export_panns.make_module,
    which is the graph the device runs.

    Every step is written so the exported graph carries no NCHW-authored axis
    argument. Studio converts ONNX to TFLite through onnx2tf, which relays 4-d
    tensors to NHWC and rewrites axis arguments to match; on this graph it did
    so wrongly and silently, turning a 91.9% model into a 5.1% one with no
    conversion error. So bn0 is folded into the flat input instead of being
    reached through a pair of transposes, and the mean-over-mel plus
    max-and-mean-over-time reduction is spelled as pooling, which carries its
    geometry in the kernel rather than in an axis index. Both rewrites are
    exact: they agree with the previous formulation to 2e-06 and score the same
    91.9% on the held-out split.
    """
    import torch
    import torch.nn.functional as F

    scale, shift = bn0_affine(backbone, frames)
    x = (flat * scale + shift).reshape(-1, 1, frames, MEL_BINS)
    for cb in (backbone.conv_block1, backbone.conv_block2,
               backbone.conv_block3, backbone.conv_block4):
        x = cb(x, pool_size=(2, 2), pool_type="avg")
    steps, bins = x.shape[2], x.shape[3]
    x = F.avg_pool2d(x, kernel_size=(1, bins))          # mean over mel
    x = (F.max_pool2d(x, kernel_size=(steps, 1))        # max over time
         + F.avg_pool2d(x, kernel_size=(steps, 1)))     # + mean over time
    return torch.relu(backbone.fc1(x.flatten(1)))


def embed_all(backbone, X: np.ndarray, frames: int, batch: int = 16) -> np.ndarray:
    """(n, 512) embeddings for flattened log-mel rows, computed once."""
    import torch

    out = []
    with torch.no_grad():
        for start in range(0, len(X), batch):
            chunk = X[start : start + batch]
            out.append(
                backbone_forward(backbone, torch.from_numpy(chunk), frames).numpy())
            done = min(start + batch, len(X))
            if (start // batch) % 20 == 0 or done == len(X):
                print(f"  embedded {done}/{len(X)}", flush=True)
    return np.concatenate(out).astype(np.float32)


def balance_idx(y: np.ndarray, seed: int) -> np.ndarray:
    """Oversample minority classes to the majority count.

    Kept identical to harness/train_head.py: the head is an MLP, which takes no
    sample weights, so imbalance is handled by resampling rather than by a
    class-weighted loss. Changing one and not the other would make the Studio
    project and the harness disagree for a reason nobody would look for.
    """
    rng = np.random.default_rng(seed)
    classes, counts = np.unique(y, return_counts=True)
    target = int(counts.max())
    idx = []
    for c in classes:
        where = np.flatnonzero(y == c)
        idx.append(where)
        if len(where) < target:
            idx.append(rng.choice(where, target - len(where), replace=True))
    return np.concatenate(idx)


class Head:
    """Two hidden layers over the embedding, matching the harness head."""

    def __init__(self, n_in: int, n_out: int, seed: int):
        import torch
        from torch import nn

        torch.manual_seed(seed)
        self.net = nn.Sequential(
            nn.Linear(n_in, 512), nn.ReLU(),
            nn.Linear(512, 256), nn.ReLU(),
            nn.Linear(256, n_out),
        )

    def fit(self, X, y, epochs: int, lr: float, seed: int,
            label_smoothing: float = 0.0) -> None:
        import torch
        from torch import nn

        # StandardScaler, computed here and folded into the exported graph later
        # so it never becomes a preprocessing step someone has to remember.
        self.mean = X.mean(axis=0)
        self.scale = np.where(X.std(axis=0) < 1e-8, 1.0, X.std(axis=0))
        Xs = torch.from_numpy(((X - self.mean) / self.scale).astype(np.float32))
        yt = torch.from_numpy(y.astype(np.int64))

        opt = torch.optim.Adam(self.net.parameters(), lr=lr, weight_decay=1e-3)
        loss_fn = nn.CrossEntropyLoss(label_smoothing=label_smoothing)
        gen = torch.Generator().manual_seed(seed)
        self.net.train()
        for epoch in range(epochs):
            perm = torch.randperm(len(Xs), generator=gen)
            total = 0.0
            for start in range(0, len(perm), 128):
                sel = perm[start : start + 128]
                opt.zero_grad()
                loss = loss_fn(self.net(Xs[sel]), yt[sel])
                loss.backward()
                opt.step()
                total += float(loss.detach()) * len(sel)
            if epoch % 10 == 0 or epoch == epochs - 1:
                print(f"  epoch {epoch + 1}/{epochs}  loss {total / len(perm):.4f}", flush=True)
        self.net.eval()

    def predict(self, X) -> np.ndarray:
        import torch

        with torch.no_grad():
            Xs = torch.from_numpy(((X - self.mean) / self.scale).astype(np.float32))
            return self.net(Xs).argmax(dim=1).numpy()


def class_indices(Y: np.ndarray) -> np.ndarray:
    """Class indices from the studio's label array.

    A classification job hands the block one-hot rows, one column per class.
    The arrays the API serves for the same data instead carry the label index in
    column 0 followed by sample metadata. Both turn up depending on where the
    data came from, and the two are indistinguishable by shape alone - a 4-class
    one-hot row and a metadata row are both four wide - so the one-hot case is
    recognised by its contents: every entry 0 or 1, exactly one set per row.
    """
    Y = np.asarray(Y)
    if Y.ndim == 1:
        return Y.astype(np.int64)
    one_hot = (Y.shape[1] > 1
               and np.array_equal(Y, Y.astype(bool).astype(Y.dtype))
               and np.array_equal(Y.sum(axis=1), np.ones(len(Y), dtype=Y.dtype)))
    return (Y.argmax(axis=1) if one_hot else Y[:, 0]).astype(np.int64)


def fingerprint(tag: str, X: np.ndarray, y: np.ndarray) -> None:
    """Enough of a summary to recognise whether two feature sets are the same data.

    Printed for both splits so a run's inputs can be compared against the arrays
    the studio stores, without having to trust that they are the same thing.
    """
    print(f"{tag}: shape {X.shape} {X.dtype}  min {X.min():.3f} max {X.max():.3f} "
          f"mean {X.mean():.3f} std {X.std():.3f} frac==min {float((X == X.min()).mean()):.4f}")
    print(f"{tag}: labels {np.bincount(y, minlength=int(y.max()) + 1).tolist()}  "
          f"row0 sum {float(X[0].sum()):.4f} row0[:6] {np.round(X[0][:6], 4).tolist()}",
          flush=True)


def verify_export(path: str, X: np.ndarray, y: np.ndarray, classes: list[str]) -> None:
    """Score the file that was just written, rather than the head still in memory.

    The block's own accuracy comes from the fitted head; the studio's comes from
    this file. If those two ever disagree the difference is in what serialisation
    produced, and this is the only place both are available to compare.
    """
    try:
        import onnxruntime as ort
    except ImportError:
        print("onnxruntime unavailable - skipping export verification", flush=True)
        return

    sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    name = sess.get_inputs()[0].name
    pred = np.concatenate(
        [sess.run(None, {name: X[i : i + 1]})[0] for i in range(len(X))]).argmax(1)
    print()
    print(f"exported file scores {100.0 * float((pred == y).mean()):.1f}% on the "
          f"same rows the head scored above")
    print(f"  predictions {np.bincount(pred, minlength=len(classes)).tolist()}  "
          f"labels {np.bincount(y, minlength=len(classes)).tolist()}", flush=True)


def export_onnx(backbone, head: Head, frames: int, out_path: str) -> None:
    """One graph: flat log-mel in, class probabilities out."""
    import torch
    from torch import nn

    class Classifier(nn.Module):
        def __init__(self):
            super().__init__()
            self.backbone = backbone
            # The scaler is an affine map, so it folds into the first head layer
            # rather than becoming two more ops on the graph.
            first = head.net[0]
            folded = nn.Linear(first.in_features, first.out_features)
            w = first.weight.detach().numpy() / head.scale[None, :]
            b = first.bias.detach().numpy() - (first.weight.detach().numpy()
                                               @ (head.mean / head.scale))
            folded.weight.data = torch.tensor(w, dtype=torch.float32)
            folded.bias.data = torch.tensor(b, dtype=torch.float32)
            self.head = nn.Sequential(folded, *list(head.net)[1:])

        def forward(self, x):
            emb = backbone_forward(self.backbone, x, frames)
            return torch.softmax(self.head(emb), dim=1)

    model = Classifier().eval()
    dummy = torch.zeros(1, frames * MEL_BINS, dtype=torch.float32)
    torch.onnx.export(
        model, dummy, out_path,
        input_names=["features"], output_names=["probabilities"],
        opset_version=17, do_constant_folding=True, dynamo=False,
    )
    print(f"wrote {out_path} ({os.path.getsize(out_path) / 1e6:.1f} MB)")


def report(y_true: np.ndarray, y_pred: np.ndarray, classes: list[str]) -> None:
    print(f"\noverall accuracy {100.0 * float((y_true == y_pred).mean()):.1f}%")
    print(f"{'class':<18}{'recall':>9}{'precision':>11}{'support':>9}")
    for i, name in enumerate(classes):
        actual, predicted = y_true == i, y_pred == i
        hit = int((actual & predicted).sum())
        recall = 100.0 * hit / max(int(actual.sum()), 1)
        precision = 100.0 * hit / max(int(predicted.sum()), 1)
        print(f"{name:<18}{recall:>8.1f}%{precision:>10.1f}%{int(actual.sum()):>9}")


def main() -> int:
    args = parse_args()
    balanced = str(args.balanced).lower() in ("true", "1", "yes")
    os.makedirs(args.out_directory, exist_ok=True)

    data = args.data_directory
    X_train = np.load(os.path.join(data, "X_split_train.npy")).astype(np.float32)
    Y_train = np.load(os.path.join(data, "Y_split_train.npy"))
    X_test = np.load(os.path.join(data, "X_split_test.npy")).astype(np.float32)
    Y_test = np.load(os.path.join(data, "Y_split_test.npy"))

    X_train = X_train.reshape(len(X_train), -1)
    X_test = X_test.reshape(len(X_test), -1)
    y_train = class_indices(Y_train)
    y_test = class_indices(Y_test)

    classes = [f"class_{i}" for i in range(int(max(y_train.max(), y_test.max())) + 1)]
    if args.info_file and os.path.exists(args.info_file):
        with open(args.info_file, encoding="utf-8") as fh:
            info = json.load(fh)
        named = info.get("classes") or info.get("labels")
        if named:
            classes = list(named)

    # A feature vector that is not a whole number of mel frames means the impulse
    # is wired to a different processing block. Failing here is far cheaper than
    # training for an hour on a silently mis-shaped tensor.
    if X_train.shape[1] % MEL_BINS:
        raise SystemExit(
            f"{X_train.shape[1]} features is not a multiple of {MEL_BINS} mel bins - "
            "this block expects the PANNs log-mel processing block, not MFE/MFCC"
        )
    frames = X_train.shape[1] // MEL_BINS
    seconds = (frames - 1) * HOP / SAMPLE_RATE
    print(f"{len(X_train)} train / {len(X_test)} test, {frames} frames x {MEL_BINS} mels "
          f"(~{seconds:.1f} s), {len(classes)} classes: {', '.join(classes)}")

    fingerprint("train", X_train, y_train)
    fingerprint("test ", X_test, y_test)

    backbone = load_backbone(args.backbone)
    print(f"\nembedding with frozen {args.backbone} ...", flush=True)
    E_train = embed_all(backbone, X_train, frames)
    E_test = embed_all(backbone, X_test, frames)

    fit_X, fit_y = E_train, y_train
    if balanced:
        idx = balance_idx(y_train, args.seed)
        fit_X, fit_y = E_train[idx], y_train[idx]
        print(f"balanced: {len(E_train)} -> {len(fit_X)} training rows")

    print("\ntraining head ...", flush=True)
    head = Head(E_train.shape[1], len(classes), args.seed)
    head.fit(fit_X, fit_y, args.epochs, args.learning_rate, args.seed,
             args.label_smoothing)

    report(y_test, head.predict(E_test), classes)

    print()
    onnx_path = os.path.join(args.out_directory, "model.onnx")
    export_onnx(backbone, head, frames, onnx_path)
    verify_export(onnx_path, X_test, y_test, classes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
