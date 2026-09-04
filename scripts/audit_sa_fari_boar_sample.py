"""SA-FARI boar-video verification, Step 4.2 of the Boar-gap close-out plan
(4 Sep 2026): file integrity + label correctness by eye on every positive
boar/wild-boar video in the dataset, not a sample of videos - only the frames
within each video are sampled, the same convention as trail-camera-v2's
14-image pass.

Ground truth for "how many boar videos does SA-FARI actually contain" comes
from the annotation JSONs directly (facebook/SA-FARI, HF-gated, annotations
only - the actual frames live in the public GCS bucket cxl-public-camera-trap,
per the dataset README), not from the paper's approximate species-count table.
Two open-vocabulary noun-phrase category ids both resolve to Sus scrofa in the
dataset's own taxonomy fields: id 111 "pig" and id 43640 "wild boar". Counting
video_np_pairs with num_masklets > 0 for either id, across both train and test
splits, gives 15 distinct videos (7 test + 8 train, no name overlap) - not the
"approximately 14" figure boar-representation-audit.md carried from the paper's
species table. That table was always hedged ("approximately"); this script's
count is a direct read of the primary annotation data and supersedes it.

Requires a pre-built C{sa_fari_boar_positive_videos.json} scratch file (built
by hand this pass from sa_fari_{train,test}_ext.json - the ext files are ~55MB
/ ~880MB and are not fetched here to avoid pulling ~1GB every run). Frames
themselves are fetched from the public GCS bucket - no HF_TOKEN needed for
media, only for the gated annotation JSONs used to build the scratch file.
"""
import json
import os
import sys
import urllib.request

from audit_boar_sample import RAW, contact_sheet

OUT_DIR = os.path.join(RAW, "_audit_tmp")

GCS_BASE = "https://storage.googleapis.com/cxl-public-camera-trap/sa_fari"
SPLIT_DIR = {"test": "sa_fari_test", "train": "sa_fari_train"}

FRAMES_PER_VIDEO = 6


def fetch_frame(split, video_name, file_name, cache_dir):
    os.makedirs(cache_dir, exist_ok=True)
    local = os.path.join(cache_dir, file_name.replace("/", "_"))
    if not os.path.exists(local):
        url = f"{GCS_BASE}/{SPLIT_DIR[split]}/JPEGImages_6fps/{file_name}"
        urllib.request.urlretrieve(url, local)
    return local


def pick_indices(frames_with_box_idx, n):
    if len(frames_with_box_idx) <= n:
        return frames_with_box_idx
    step = (len(frames_with_box_idx) - 1) / (n - 1)
    return sorted({frames_with_box_idx[round(i * step)] for i in range(n)})


def main(manifest_path):
    with open(manifest_path) as fh:
        data = json.load(fh)

    os.makedirs(OUT_DIR, exist_ok=True)
    cache_dir = os.path.join(OUT_DIR, "sa_fari_frames_cache")

    for split in ("test", "train"):
        for entry in data[split]:
            video_name = entry["video_name"]
            file_names = entry["file_names"]
            anns = entry["annotations"]

            frames_with_box = sorted({
                idx for a in anns for idx, b in enumerate(a["bboxes"]) if b is not None
            })
            if not frames_with_box:
                print(f"WARNING: {video_name} has no non-null boxes at all")
                continue

            idxs = pick_indices(frames_with_box, FRAMES_PER_VIDEO)
            records = []
            for idx in idxs:
                boxes = [a["bboxes"][idx] for a in anns if a["bboxes"][idx] is not None]
                local = fetch_frame(split, video_name, file_names[idx], cache_dir)
                records.append({"name": f"{video_name}/{file_names[idx]}", "path": local, "boxes": boxes})

            sheet_path = os.path.join(OUT_DIR, f"safari_{split}_{video_name}.png")
            contact_sheet(records, sheet_path, cols=3, cell=340)
            print(f"{split} {video_name}: {len(records)} frames -> {sheet_path}")


if __name__ == "__main__":
    manifest = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.environ.get("TEMP", ""), "sa_fari_boar_positive_videos.json"
    )
    main(manifest)
