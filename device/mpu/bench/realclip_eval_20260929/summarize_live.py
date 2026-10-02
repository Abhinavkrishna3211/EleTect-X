"""Summarise live.jsonl from live_compare.sh: false-alarm rate per model at several cut-offs.

The scene is known-empty (plantation, no animals), so any box counts as a false alarm.
"Per-class" uses each candidate's tuned thresholds; the champion's live fire bar is 0.80.
"""
import json
import sys
from collections import defaultdict

PER_CLASS = {
    "champion": {"Boar": 0.05, "Elephant": 0.05},
    "runF": {"Boar": 0.18, "Elephant": 0.18, "Fox": 0.12},
    "runH": {"Boar": 0.15, "Elephant": 0.12, "Fox": 0.10},
    "runG": {"Boar": 0.18, "Elephant": 0.10, "Fox": 0.10},
}
CUTS = [0.3, 0.5, 0.7, 0.8]
MODELS = ["champion", "runF", "runH", "runG"]

rows = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8") if line.strip()]
since = sys.argv[2] if len(sys.argv) > 2 else ""
rows = [r for r in rows if r["ts"] >= since and r["boxes"] != "ERR"]
frames = defaultdict(dict)
ms = defaultdict(list)
for r in rows:
    frames[r["frame"]][r["model"]] = r["boxes"]
    ms[r["model"]].append(r["ms"])
minutes = sorted({r["ts"] for r in rows})
print(f"{len(frames)} frames over {len(minutes)} minutes ({minutes[0]} .. {minutes[-1]})")
print(f"{'model':9s} {'per-class':>10s} " + " ".join(f"{'>=' + str(c):>8s}" for c in CUTS)
      + f" {'max':>6s} {'ms':>5s}  labels@per-class")
for m in MODELS:
    fr = [b[m] for b in frames.values() if m in b]
    if not fr:
        continue

    def rate(pred, fr=fr):
        """Fraction of this model's frames holding a box that satisfies pred."""
        return sum(1 for boxes in fr if any(pred(x) for x in boxes)) / len(fr)

    pc = rate(lambda x, m=m: x["v"] >= PER_CLASS[m].get(x["l"], 1))
    cuts = [rate(lambda x, c=c: x["v"] >= c) for c in CUTS]
    mx = max((x["v"] for boxes in fr for x in boxes), default=0)
    labs = defaultdict(int)
    for boxes in fr:
        for lab in {x["l"] for x in boxes if x["v"] >= PER_CLASS[m].get(x["l"], 1)}:
            labs[lab] += 1
    print(f"{m:9s} {pc:10.1%} " + " ".join(f"{c:8.1%}" for c in cuts)
          + f" {mx:6.2f} {sum(ms[m]) / len(ms[m]):5.0f}  {dict(labs)}")

# Minutes in which a model would have alarmed on >=2 of the 5 frames (roughly the
# live 2-consecutive-poll fire rule) at its per-class thresholds and at 0.8.
print("minutes with >=2 alarming frames (per-class / >=0.8):")
by_min = defaultdict(lambda: defaultdict(list))
for r in rows:
    by_min[r["ts"]][r["model"]].append(r["boxes"])
for m in MODELS:
    a = sum(1 for t in by_min.values()
            if sum(any(x["v"] >= PER_CLASS[m].get(x["l"], 1) for x in b) for b in t[m]) >= 2)
    b8 = sum(1 for t in by_min.values() if sum(any(x["v"] >= 0.8 for x in b) for b in t[m]) >= 2)
    print(f"  {m:9s} {a}/{len(by_min)}  /  {b8}/{len(by_min)}")
