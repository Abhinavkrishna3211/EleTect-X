"""Clip-level summary of clips.jsonl from clip_eval.sh.

Ground truth is the 29 Sept manual review (camera_check/encounter_review_labels_29sept.md):
fox-* and manual-cat-trigger clips contain a real animal, every other category is a
false trigger. Animal clips were sampled at 1 fps, false-trigger clips at 0.25 fps.

A clip "alarms" at a cut-off when >= MIN_FRAMES of its frames carry a box at or above it
(any label - the question here is whether the node would react, not species accuracy).
False-trigger clips whose source clip fed the fp2 hard-negative set are reported
separately as "seen", since the candidates trained on frames from them.

Usage: python summarize_clips.py clips.jsonl [MIN_FRAMES]
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

PER_CLASS = {
    "champion": {"Boar": 0.05, "Elephant": 0.05},
    "runF": {"Boar": 0.18, "Elephant": 0.18, "Fox": 0.12},
    "runH": {"Boar": 0.15, "Elephant": 0.12, "Fox": 0.10},
    "runG": {"Boar": 0.18, "Elephant": 0.10, "Fox": 0.10},
}
MODELS = ["champion", "runF", "runH", "runG"]
CUTS = ["per-class", 0.3, 0.5, 0.7, 0.8]
ANIMAL = ("fox-", "manual-cat")
TRIAGE = Path(__file__).resolve().parents[4] / "ml" / "vision"

seen = set()
with open(TRIAGE / "board-pull-20260924-27-review-triage.csv", newline="", encoding="utf-8") as fh:
    seen |= {row["source_clip_ts"] for row in csv.DictReader(fh)}
# Whole clips uploaded to EI training at 1 fps (ml/vision/fox-representation-audit.md):
# four fox clips and four morning background clips. 20260923T223648 (fox) and
# 20260924T034801/035904 (morning) went to the test split instead - not trained on, but
# the test split is what the per-class thresholds were tuned against.
seen |= {"20260923T212434", "20260923T212018", "20260924T145407", "20260924T191104",
         "20260924T034624", "20260924T035338", "20260924T042153", "20260926T005209"}
TEST_SPLIT = {"20260923T223648", "20260924T034801", "20260924T035904"}

min_frames = int(sys.argv[2]) if len(sys.argv) > 2 else 2
# clip -> model -> list of per-frame box lists
clips = defaultdict(lambda: defaultdict(list))
for line in open(sys.argv[1], encoding="utf-8"):
    if not line.strip():
        continue
    r = json.loads(line)
    if r["boxes"] == "ERR":
        continue
    cat, ts, _ = r["frame"].split("__")
    clips[(cat, ts)][r["model"]].append(r["boxes"])


def hit(model, cut, box):
    """Whether one box clears this model's floor at `cut`."""
    floor = PER_CLASS[model].get(box["l"], 1) if cut == "per-class" else cut
    return box["v"] >= floor


def n_hits(model, cut, frames):
    """How many of `frames` hold at least one box clearing the floor."""
    return sum(any(hit(model, cut, b) for b in boxes) for boxes in frames)


animal = [k for k in clips if k[0].startswith(ANIMAL)]
fp_seen = [k for k in clips if not k[0].startswith(ANIMAL) and k[1] in seen]
fp_unseen = [k for k in clips if not k[0].startswith(ANIMAL) and k[1] not in seen]
print(f"{len(clips)} clips: {len(animal)} animal, {len(fp_seen)} false-trigger seen in "
      f"training, {len(fp_unseen)} unseen   (clip alarms at >= {min_frames} frames)")
print(f"{'model':9s} {'cut':>9s} | {'animal clips':>12s} {'animal frames':>13s} | "
      f"{'FP unseen':>9s} {'FP seen':>8s} {'FP frames':>9s}")
for m in MODELS:
    for cut in CUTS:
        a_clips = sum(n_hits(m, cut, clips[k][m]) >= min_frames for k in animal)
        a_fr = sum(n_hits(m, cut, clips[k][m]) for k in animal)
        a_tot = sum(len(clips[k][m]) for k in animal)
        fu = sum(n_hits(m, cut, clips[k][m]) >= min_frames for k in fp_unseen)
        fs = sum(n_hits(m, cut, clips[k][m]) >= min_frames for k in fp_seen)
        f_fr = sum(n_hits(m, cut, clips[k][m]) for k in fp_seen + fp_unseen)
        f_tot = sum(len(clips[k][m]) for k in fp_seen + fp_unseen)
        print(f"{m:9s} {str(cut):>9s} | {a_clips:>5d}/{len(animal):<6d} "
              f"{a_fr / max(a_tot, 1):13.1%} | {fu:>4d}/{len(fp_unseen):<4d} "
              f"{fs:>3d}/{len(fp_seen):<4d} {f_fr / max(f_tot, 1):9.1%}")
    print()

print("per animal clip: frames / frames with a box at per-class | >=0.5 | >=0.7, top label@max")
for k in sorted(animal):
    parts = []
    for m in MODELS:
        fr = clips[k][m]
        top = max((b for boxes in fr for b in boxes), key=lambda b: b["v"], default=None)
        tl = f"{top['l']}@{top['v']:.2f}" if top else "-"
        parts.append(f"{m} {n_hits(m, 'per-class', fr)}|{n_hits(m, 0.5, fr)}|"
                     f"{n_hits(m, 0.7, fr)} {tl}")
    split = "TRAIN" if k[1] in seen else "test" if k[1] in TEST_SPLIT else "clean"
    print(f"  {k[0]:14s} {k[1]} {split:5s} n={len(clips[k]['champion']):<3d} "
          + "  ".join(parts))
