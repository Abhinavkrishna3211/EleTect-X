"""On-target latency for the acoustic .eim, stdlib only (the board has no numpy).

Section 7.4 asks for the QRB2210 number, and every figure recorded so far is a
substitute for it. Studio's profiler cannot see a custom DSP block, so its
estimate omits the front end. The qemu timings are emulation artefacts. The x86
host split describes a different CPU entirely. This drives the deployed runner
over the same HTTP endpoint services/config.py points at, so what it times is
the path that actually runs in the field.

The runner reports its own dsp/classification split in the response and that is
the authoritative number; wall clock is recorded beside it to expose the HTTP
and JSON overhead the detector also pays, which the internal timing by
construction excludes.

Runs *on the board*, against a runner already serving:
    edge-impulse-linux-runner --model-file <acoustic.eim> --run-http-server 1338
    python3 onboard_latency.py
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
import urllib.request
import wave

URL = os.environ.get("EIM_URL", "http://127.0.0.1:1338")
HERE = os.path.dirname(os.path.abspath(__file__))
RAW_SAMPLE_COUNT = 80000
WARMUP = 2


def features(path: str) -> list[int]:
    """8 kHz mono 16-bit PCM -> the int16 list the runner expects."""
    with wave.open(path, "rb") as w:
        assert w.getnchannels() == 1, (path, w.getnchannels())
        assert w.getsampwidth() == 2, (path, w.getsampwidth())
        assert w.getframerate() == 8000, (path, w.getframerate())
        raw = w.readframes(w.getnframes())
    out = []
    for i in range(0, len(raw), 2):
        v = raw[i] | (raw[i + 1] << 8)
        out.append(v - 65536 if v >= 32768 else v)
    # The impulse declares RAW_SAMPLE_COUNT 80000. Pad or trim so a clip a few
    # samples short is not rejected for a reason unrelated to what is measured.
    return (out + [0] * RAW_SAMPLE_COUNT)[:RAW_SAMPLE_COUNT]


def classify(feat: list[int]) -> tuple[float, dict]:
    body = json.dumps({"features": feat}).encode()
    req = urllib.request.Request(f"{URL}/api/features", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=180) as r:
        payload = json.load(r)
    return (time.perf_counter() - t0) * 1000.0, payload


def summarise(name: str, v: list[float]) -> dict:
    if not v:
        return {}
    d = {"mean": round(statistics.mean(v), 1), "median": round(statistics.median(v), 1),
         "min": round(min(v), 1), "max": round(max(v), 1)}
    print(f"{name:<16} mean {d['mean']:8.1f}  median {d['median']:8.1f}  "
          f"min {d['min']:8.1f}  max {d['max']:8.1f}")
    return d


def main() -> int:
    with open(os.path.join(HERE, "manifest.json"), encoding="utf-8") as fh:
        man = json.load(fh)

    print(f"warming up ({WARMUP}) ...", flush=True)
    first = features(os.path.join(HERE, "clips", man[0]["f"]))
    for _ in range(WARMUP):
        classify(first)

    rows: list[dict] = []
    dsp: list[float] = []
    cls: list[float] = []
    wall: list[float] = []
    for i, m in enumerate(man):
        ms, p = classify(features(os.path.join(HERE, "clips", m["f"])))
        t = p.get("timing") or {}
        res = (p.get("result") or {}).get("classification") or {}
        top = max(res, key=res.get) if res else "?"
        rows.append({"file": m["f"], "truth": m["label"], "pred": top,
                     "score": res.get(top), "dsp_ms": t.get("dsp"),
                     "classification_ms": t.get("classification"),
                     "wall_ms": round(ms, 1), "scores": res})
        for lst, val in ((dsp, t.get("dsp")), (cls, t.get("classification")), (wall, ms)):
            if val is not None:
                lst.append(val)
        print(f"  {i + 1:2d}/{len(man)} {m['label']:<14} -> {top:<14} "
              f"{res.get(top, 0.0):5.2f}   dsp {t.get('dsp')}ms  "
              f"nn {t.get('classification')}ms  wall {ms:.0f}ms", flush=True)

    print("\n--- per 10 s window, on QRB2210 (ms) ---")
    out = {"url": URL, "n": len(rows), "warmup": WARMUP,
           "dsp_ms": summarise("dsp (front end)", dsp),
           "classification_ms": summarise("classifier", cls),
           "wall_ms": summarise("wall (HTTP)", wall)}
    if dsp and cls:
        total = [a + b for a, b in zip(dsp, cls, strict=True)]
        out["total_ms"] = summarise("total inference", total)
        out["realtime_factor"] = round(statistics.mean(total) / 10000.0, 4)
        print(f"\nreal-time factor: {out['realtime_factor']:.4f} of the 10 s window")

    out["correct"] = sum(1 for r in rows if r["pred"] == r["truth"])
    print(f"agreement on this subset: {out['correct']}/{len(rows)}")
    out["rows"] = rows

    dest = os.path.join(HERE, "onboard_latency.json")
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print(f"wrote {os.path.basename(dest)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
