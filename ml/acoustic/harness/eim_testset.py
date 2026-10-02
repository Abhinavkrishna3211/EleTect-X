"""Score the frozen test split through a built .eim and report what it got.

This is the end-to-end check the parity harness cannot make. parity_cpp.py
and parity_resample.py compare the C++ front end against dsp.py and stop at
the features; they say nothing about whether Studio's ONNX-to-TFLite
conversion of the learn block survived, nor whether the runner wires the two
together the way the impulse describes. Running real clips through the .eim
covers all three at once, and the number it produces is directly comparable
to the accuracy Studio reports for the same impulse.

Audio is read at its native 8 kHz and handed over as int16 counts, which is
what Edge Impulse serves for audio data and what the block's rescale
heuristic expects to see. The 4x upsample to the PANNs filterbank happens
inside the block, on the deployed path, exactly as it will in the field.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

WINDOW_SAMPLES = 80000  # 10 s at 8 kHz, matching EI_CLASSIFIER_RAW_SAMPLE_COUNT


def load_clip(path: Path) -> list[int]:
    """One clip as int16 counts, head-cropped and zero-padded to the window.

    Head crop and zero pad are what harness/embed.py does, so a clip is
    presented to the .eim the same way it was presented during training and
    evaluation. Padding at 8 kHz rather than 32 kHz is equivalent: zeros
    upsample to zeros.
    """
    y, sr = sf.read(str(path), dtype="int16", always_2d=True)
    y = y[:, 0]
    if sr != 8000:
        raise SystemExit(f"{path}: expected 8000 Hz, got {sr}")
    if len(y) >= WINDOW_SAMPLES:
        y = y[:WINDOW_SAMPLES]
    else:
        y = np.pad(y, (0, WINDOW_SAMPLES - len(y)))
    return y.astype(np.int64).tolist()


class Runner:
    """A running .eim, talked to over its Unix socket with newline JSON."""

    def __init__(self, eim: Path, sock_path: Path, launcher: list[str] | None = None):
        self.sock_path = sock_path
        sock_path.unlink(missing_ok=True)
        self.proc = subprocess.Popen(
            [*(launcher or []), str(eim), str(sock_path)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        for _ in range(200):
            if sock_path.exists():
                break
            time.sleep(0.05)
        else:
            raise SystemExit("the .eim never created its socket")
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(str(sock_path))
        self.buf = b""
        hello = self._rpc({"id": 0, "hello": 1})
        if not hello.get("success", False):
            raise SystemExit(f"hello failed: {hello}")
        self.labels = hello["model_parameters"]["labels"]

    def _rpc(self, msg: dict) -> dict:
        self.sock.sendall((json.dumps(msg) + "\n").encode())
        while b"\n" not in self.buf:
            chunk = self.sock.recv(1 << 20)
            if not chunk:
                raise SystemExit("the .eim closed the connection")
            # The runner formats each response into a fixed-size static
            # buffer and writes the whole buffer, so what arrives is the
            # JSON, a newline, and then padding NULs. Left in place they
            # become the first bytes of the next response, where json's
            # encoding sniffer reads them as a UTF-16 BOM and the decode
            # fails several messages away from the actual cause.
            self.buf += chunk.replace(b"\x00", b"")
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line.decode("utf-8"))

    def classify(self, features: list[int], ix: int) -> dict:
        return self._rpc({"id": ix, "classify": features})

    def close(self) -> None:
        self.sock.close()
        self.proc.terminate()
        self.proc.wait(timeout=10)
        self.sock_path.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eim", required=True, type=Path)
    ap.add_argument("--split", required=True, type=Path)
    ap.add_argument("--repo-root", required=True, type=Path)
    ap.add_argument("--limit", type=int, default=0, help="0 = every test clip")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--launcher", default="",
                    help="command prefix, e.g. a qemu-user binary for a "
                         "cross-built .eim that cannot run natively")
    args = ap.parse_args()

    split = json.loads(args.split.read_text())
    records = [r for r in split["records"] if r.get("split") == "test"]
    if args.limit:
        # Take a stratified slice rather than the head of the list, so a
        # short run is not all one class.
        by_label: dict[str, list] = collections.defaultdict(list)
        for r in records:
            by_label[r["label"]].append(r)
        per = max(1, args.limit // len(by_label))
        records = [r for rs in by_label.values() for r in rs[:per]]

    print(f"clips: {len(records)}")
    runner = Runner(args.eim, Path(f"/tmp/eletect-eim-{os.getpid()}.sock"),
                    launcher=args.launcher.split() or None)
    print(f"labels: {runner.labels}")

    rows = []
    confusion: dict[tuple[str, str], int] = collections.Counter()
    correct = 0
    dsp_ms: list[float] = []
    cls_ms: list[float] = []
    t0 = time.time()

    for ix, rec in enumerate(records):
        clip = args.repo_root / rec["path"]
        if not clip.exists():
            raise SystemExit(f"missing clip: {clip}")
        resp = runner.classify(load_clip(clip), ix)
        if not resp.get("success", False):
            raise SystemExit(f"classify failed on {clip}: {resp}")
        scores = resp["result"]["classification"]
        pred = max(scores, key=scores.get)
        truth = rec["label"]
        correct += pred == truth
        confusion[(truth, pred)] += 1
        timing = resp.get("timing", {})
        dsp_ms.append(timing.get("dsp", 0))
        cls_ms.append(timing.get("classification", 0))
        rows.append({
            "path": rec["path"], "truth": truth, "pred": pred, "scores": scores,
        })
        if (ix + 1) % 25 == 0:
            rate = (ix + 1) / (time.time() - t0)
            print(f"  {ix + 1}/{len(records)}  acc so far "
                  f"{correct / (ix + 1):.4f}  ({rate:.1f} clips/s)")

    runner.close()

    n = len(records)
    print(f"\naccuracy: {correct}/{n} = {correct / n:.4%}")
    print(f"timing per clip: dsp {np.mean(dsp_ms):.1f} ms, "
          f"classify {np.mean(cls_ms):.1f} ms")

    labels = sorted({r["label"] for r in records})
    width = max(len(x) for x in labels) + 2
    print("\nconfusion (rows = truth, cols = predicted)")
    print(" " * width + "".join(f"{x[:10]:>12}" for x in labels))
    for t in labels:
        cells = "".join(f"{confusion[(t, p)]:>12}" for p in labels)
        print(f"{t:<{width}}{cells}")

    if args.out:
        args.out.write_text(json.dumps({
            "eim": str(args.eim),
            "n": n,
            "correct": correct,
            "accuracy": correct / n,
            "confusion": {f"{t}->{p}": c for (t, p), c in confusion.items()},
            "mean_dsp_ms": float(np.mean(dsp_ms)),
            "mean_classify_ms": float(np.mean(cls_ms)),
            "rows": rows,
        }, indent=2))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
