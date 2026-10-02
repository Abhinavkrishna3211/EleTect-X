"""Embed every clip with an AudioSet-pretrained PANNs backbone.

Why this exists. ml/acoustic/README.md closed architecture search with "data
ceiling, not capacity ceiling" after a 2-conv net and a 3-conv net scored the
same. That conclusion is sound *for training from scratch on ~1.7k clips* - at
that size a bigger randomly-initialised net has nothing extra to learn from. It
is not evidence that the task is capped at ~58%.

The standard way past that ceiling is not a bigger from-scratch net, it is a
backbone that already learned general audio structure from a corpus this project
could never collect. PANNs is trained on AudioSet (~2M clips), whose ontology
contains `Chainsaw` (/m/01j4z9) and `Gunshot, gunfire` (/m/032s66) as labelled
classes - so the representation has already been taught to separate the two
classes this project scores worst on.

The README also records transfer learning as ruled out on a "hard platform
constraint": Edge Impulse's `keras-transfer-kws` block rejects any window over
1000 ms. That constraint is real but specific to that block, which exists for
single spoken keywords. It says nothing about general audio backbones, which are
normally run at 10 s. Running the backbone here - outside Edge Impulse - avoids
the block entirely.

Backbones (both MIT-licensed, both AudioSet-pretrained):
  cnn14  81M params, 2048-d  - establishes the accuracy ceiling
  cnn10   6M params, 512-d   - middle option
  cnn6    6M params, 512-d   - the size that could plausibly deploy on the QRB2210

Writes embeddings.npz: X (n, d) float32, plus label/group/split/source arrays.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SAMPLE_RATE = 32000  # PANNs is trained at 32 kHz; resampling is not optional.


# split.json stores clip paths relative to the repository root, but every other
# default in this harness is relative to the script. Running from the harness
# directory therefore resolved the split fine and then failed on the audio, so
# anchor the clip paths explicitly rather than depending on the caller's cwd.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))


def resolve_clip(path: str) -> str:
    """A clip path as given, or the same path anchored at the repository root."""
    if os.path.isabs(path) or os.path.exists(path):
        return path
    return os.path.join(REPO_ROOT, path)


def load_clip(path: str, seconds: float, crop: str = "head") -> np.ndarray:
    """`seconds` of audio from a clip.

    `crop="head"` takes the opening of the clip, which is what a fixed-window
    training set has always meant here. That is the wrong comparison for a
    shortened window: a gunshot four seconds into a ten-second clip is simply
    absent from the first three, so a short window looks far worse than it
    would on-device, where it slides over a continuous stream and cannot miss
    the event. `crop="peak"` centres the window on the loudest 100 ms instead,
    which is the closer stand-in for what a sliding detector actually sees.
    """
    import librosa

    want = int(SAMPLE_RATE * seconds)
    y, _ = librosa.load(resolve_clip(path), sr=SAMPLE_RATE, mono=True)
    if len(y) < want:
        y = np.pad(y, (0, want - len(y)))
    if crop == "peak" and len(y) > want:
        hop = SAMPLE_RATE // 10
        energy = np.convolve(y.astype(np.float64) ** 2, np.ones(hop), mode="same")
        start = int(np.clip(int(np.argmax(energy)) - want // 2, 0, len(y) - want))
        return y[start : start + want].astype(np.float32)
    return y[:want].astype(np.float32)


def build_model(arch: str, device: str):
    """Return (model, forward) where forward(batch)->(n, d) embeddings."""
    import torch
    from panns_inference.models import Cnn14
    from panns_inference.pytorch_utils import move_data_to_device

    # panns_inference bundles only Cnn14; the deployable-size backbones come from
    # panns_small, vendored from the reference implementation.
    from panns_small import Cnn6, Cnn10

    cls = {"cnn14": Cnn14, "cnn6": Cnn6, "cnn10": Cnn10}[arch]
    model = cls(
        sample_rate=SAMPLE_RATE,
        window_size=1024,
        hop_size=320,
        mel_bins=64,
        fmin=50,
        fmax=14000,
        classes_num=527,
    )
    ckpt_name = {
        "cnn14": "Cnn14_mAP=0.431.pth",
        "cnn6": "Cnn6_mAP=0.343.pth",
        "cnn10": "Cnn10_mAP=0.380.pth",
    }[arch]
    ckpt_path = os.path.join(os.path.expanduser("~"), "panns_data", ckpt_name)
    if not os.path.exists(ckpt_path):
        import urllib.request

        url = {
            "cnn14": "https://zenodo.org/record/3987831/files/Cnn14_mAP%3D0.431.pth?download=1",
            "cnn6": "https://zenodo.org/record/3960586/files/Cnn6_mAP%3D0.343.pth?download=1",
            "cnn10": "https://zenodo.org/record/3960586/files/Cnn10_mAP%3D0.380.pth?download=1",
        }[arch]
        os.makedirs(os.path.dirname(ckpt_path), exist_ok=True)
        print(f"downloading {ckpt_name} ...", flush=True)
        urllib.request.urlretrieve(url, ckpt_path)
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    model.load_state_dict(ckpt["model"])
    model.eval().to(device)

    @torch.no_grad()
    def forward(batch: np.ndarray) -> np.ndarray:
        x = move_data_to_device(torch.from_numpy(batch), device)
        return model(x, None)["embedding"].cpu().numpy()

    return model, forward


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default=os.path.join("ml", "acoustic", "harness", "split.json"))
    ap.add_argument("--arch", default="cnn14", choices=("cnn14", "cnn6", "cnn10"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--limit", type=int, default=0, help="debug: only embed N clips")
    ap.add_argument("--resume", action="store_true",
                    help="keep embeddings already in --out and only extract the clips it lacks")
    ap.add_argument("--crop", default="head", choices=("head", "peak"),
                    help="where a shortened window is taken from; see load_clip")
    ap.add_argument("--window", type=float, default=None,
                    help="seconds of audio per clip, overriding the split's window_s. "
                         "Compute is linear in this, and it is the only knob that shortens "
                         "the backbone without discarding the pretrained weights.")
    args = ap.parse_args()

    with open(args.split, encoding="utf-8") as fh:
        spec = json.load(fh)
    window = args.window if args.window is not None else spec["window_s"]
    # A shorter window is a different feature set, not a different view of the
    # same one, so it needs its own cache file - otherwise --resume would mix
    # windows silently, matching on filename alone.
    suffix = "" if args.crop == "head" else f"_{args.crop}"
    default_out = (f"embeddings_{args.arch}.npz" if args.window is None
                   else f"embeddings_{args.arch}_{window:g}s{suffix}.npz")
    out = args.out or os.path.join("ml", "acoustic", "harness", default_out)
    rows = spec["records"][: args.limit] if args.limit else spec["records"]
    print(f"{len(rows)} clips, arch={args.arch}, window={window}s, device={args.device}")
    print(f"  -> {out}")

    # A re-freeze of the split usually changes which clips are in it, not the
    # audio itself, so re-running the backbone over the unchanged majority is
    # pure waste. Carry those rows over and extract only what is new. The
    # embedding of a clip depends on the file and the backbone alone - never on
    # the split - so a carried-over row is identical to a recomputed one.
    prior: dict[str, np.ndarray] = {}
    if args.resume and os.path.exists(out):
        d = np.load(out, allow_pickle=True)
        prior = dict(zip(d["fname"].tolist(), d["X"], strict=True))
        rows = [r for r in rows if r["file"] not in prior]
        print(f"resume: {len(prior)} cached, {len(rows)} to extract")

    _, forward = build_model(args.arch, args.device)

    feats: list[np.ndarray] = []
    kept: list[dict] = []
    failed = 0
    t0 = time.time()
    for start in range(0, len(rows), args.batch):
        chunk = rows[start : start + args.batch]
        audio, ok = [], []
        for r in chunk:
            try:
                audio.append(load_clip(r["path"], window, args.crop))
                ok.append(r)
            except Exception as exc:  # noqa: BLE001 - a corrupt cache file must not stop the run
                failed += 1
                print(f"  skip {r['file']}: {exc}", file=sys.stderr)
        if not audio:
            continue
        feats.append(forward(np.stack(audio)))
        kept.extend(ok)

        done = start + len(chunk)
        if done % (args.batch * 25) == 0 or done >= len(rows):
            rate = done / max(time.time() - t0, 1e-9)
            eta = (len(rows) - done) / max(rate, 1e-9)
            print(f"  {done}/{len(rows)}  {rate:.1f} clips/s  eta {eta / 60:.1f} min", flush=True)

    if feats:
        X = np.concatenate(feats).astype(np.float32)
    else:
        X = np.zeros((0, len(next(iter(prior.values())))), dtype=np.float32)

    if prior:
        keep = [r for r in spec["records"] if r["file"] in prior or r["file"] in
                {k["file"] for k in kept}]
        by_new = {r["file"]: i for i, r in enumerate(kept)}
        X = np.stack([
            X[by_new[r["file"]]] if r["file"] in by_new else prior[r["file"]]
            for r in keep
        ]).astype(np.float32)
        kept = keep

    np.savez_compressed(
        out,
        X=X,
        label=np.array([r["label"] for r in kept]),
        group=np.array([r["group"] for r in kept]),
        split=np.array([r["split"] for r in kept]),
        source=np.array([r["source"] for r in kept]),
        # not `file=`: that is savez_compressed's own first parameter
        fname=np.array([r["file"] for r in kept]),
        # How these features were cut. export_panns.py compares its own
        # recomputed embeddings against this file, and that comparison is only
        # meaningful if it cuts the audio the same way, so the settings travel
        # with the cache rather than being assumed from the split.
        window_s=np.array(window),
        crop=np.array(args.crop),
    )
    print(f"\n{X.shape[0]} embeddings, dim {X.shape[1]}, {failed} failed -> {out}")
    print(f"elapsed {(time.time() - t0) / 60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
