"""Orig-vs-night-tone summary of the output of score_night_tone.py.

Same ground truth and clip rule as summarize_clips.py: fox-* and
manual-cat-trigger clips hold a real animal, every other category is a false
trigger, and a clip alarms at a cut-off when >= MIN_FRAMES of its frames carry
a box at or above it. Only the IR night frames are in the set.

Usage: python summarize_night_tone.py nighttone.jsonl
"""
import json
import sys
from collections import defaultdict
from statistics import mean

ANIMAL = ("fox-", "manual-cat")
CUTS = (0.5, 0.6, 0.7)
VARIANTS = ("orig", "tone")

# clip -> variant -> frame -> top score
clips = defaultdict(lambda: defaultdict(dict))
for line in open(sys.argv[1], encoding="utf-8"):
    r = json.loads(line)
    cat, ts, _ = r["frame"].split("__")
    clips[(cat, ts)][r["variant"]][r["frame"]] = max((b["v"] for b in r["boxes"]), default=0.0)

animal = sorted(k for k in clips if k[0].startswith(ANIMAL))
false = sorted(k for k in clips if not k[0].startswith(ANIMAL))


def hits(k, v, cut):
    """How many of clip `k`'s frames score at or above `cut` in variant `v`."""
    return sum(s >= cut for s in clips[k][v].values())


print(f"{len(animal)} animal clips, {len(false)} false-trigger clips (night frames only)")
for min_frames in (1, 2):
    print(f"\nclip alarms at >= {min_frames} frame(s)")
    print(
        f"{'cut':>5s} | {'animal orig':>11s} {'animal tone':>11s}"
        f" | {'FP orig':>7s} {'FP tone':>7s}"
    )
    for cut in CUTS:
        a = [sum(hits(k, v, cut) >= min_frames for k in animal) for v in VARIANTS]
        f = [sum(hits(k, v, cut) >= min_frames for k in false) for v in VARIANTS]
        print(f"{cut:5.2f} | {a[0]:>5d}/{len(animal):<5d} {a[1]:>5d}/{len(animal):<5d} | "
              f"{f[0]:>3d}/{len(false):<3d} {f[1]:>3d}/{len(false):<3d}")

print("\nper clip: frames, frames >=0.60 orig->tone, max orig->tone, mean top score orig->tone")
for k in animal + false:
    o, t = clips[k]["orig"], clips[k]["tone"]
    print(f"  {k[0]:22s} {k[1]} n={len(o):<3d} "
          f"{hits(k, 'orig', 0.6):>3d}->{hits(k, 'tone', 0.6):<3d} "
          f"{max(o.values()):.2f}->{max(t.values()):.2f}  "
          f"{mean(o.values()):.3f}->{mean(t.values()):.3f}")
