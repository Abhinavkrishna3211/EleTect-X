"""Generate a pseudo-IR supplement from real daytime Elephant/Boar images already
cached by scripts/edge_impulse_upload_vision.py (Phase 4, plan item 3c-3).

CANDAR 2023 recipe: weighted-RGB grayscale -> mild gamma correction -> a synthetic
radial illumination-falloff mask (brighter center, darker corners, matching how a
lens-mounted IR emitter lights a scene). Upstream reports a modest, quantified
benefit (+3.79 AP) from this transform - it is a supplement, never a substitute
for real IR footage, and every image and count this script produces is tracked
and reported as SYNTHETIC, never folded into a "real data" total.

Source images are read directly from edge_impulse_upload_vision.py's own
CACHE_DIR (the already-extracted Roboflow exports for the Elephant/Boar classes -
local_root entries like the SWG pull or board captures are deliberately excluded:
some of those are already real IR, and running a fake-IR transform on a real-IR
frame is not a supplement, it's noise). This script does not re-fetch anything
from Roboflow itself - if a source isn't cached yet, run
edge_impulse_upload_vision.py (e.g. --dry-run) first, which is what populates that
cache.

Output lands in ml/datasets/vision/pseudo_ir/{elephant,boar}/, each with its own
_annotations.coco.json (bounding boxes copied verbatim from the source image - the
transform is a pixel/color operation only, geometry is untouched). Gitignored
(.gitignore).

Deliberate departure from this project's stdlib-only script convention: JPEG
decode and the array math for the grayscale/gamma/vignette transform are not
stdlib-possible. Pillow / numpy are already present on this machine, same
departure scripts/fetch_swg_camera_traps.py already carries for the same reason.

Usage:

    python scripts\\make_pseudo_ir_vision.py [--count-per-class N]
"""

import argparse
import json
import os
import random
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from edge_impulse_upload_vision import CACHE_DIR, DATASETS, parse_coco

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
OUT_ROOT = os.path.join(_ROOT, "ml", "datasets", "vision", "pseudo_ir")

# Same seed the rest of the vision pipeline uses (fetch_swg_camera_traps.py,
# dataset_manifest.json's split) - convention, not a correctness requirement.
SELECT_SEED = 20260822
# A modest supplement, not a dataset replacement - matches the plan's own framing
# of this item ("a subset of the existing daytime images").
COUNT_PER_CLASS = 250

# Rec. 601 luma weights - a named standard, not invented for this script.
GRAY_WEIGHTS = (0.299, 0.587, 0.114)
# The plan's recipe calls for gamma "~1.0" - read literally that is a no-op
# (I'/Imax = (I/Imax)^1 = I/Imax), so a deliberate small deviation above 1.0 is
# used instead: it brightens shadows/midtones on the (0,1) domain, which is the
# correct direction for an active-IR-illuminated scene (the emitter adds light
# the ambient scene didn't have), without the aggressive curve a much larger
# gamma would apply.
GAMMA = 1.15
# Corner brightness as a fraction of center brightness - a lens-mounted IR
# emitter falls off toward the frame edges; this is deliberately mild, not a
# hard vignette, since camera-trap subjects are rarely dead-center.
VIGNETTE_MIN = 0.55


def to_pseudo_ir(im):
    arr = np.asarray(im.convert("RGB"), dtype=np.float64)
    gray = arr[..., 0] * GRAY_WEIGHTS[0] + arr[..., 1] * GRAY_WEIGHTS[1] + arr[..., 2] * GRAY_WEIGHTS[2]
    imax = 255.0
    gray = imax * (gray / imax) ** (1.0 / GAMMA)

    h, w = gray.shape
    yy, xx = np.mgrid[0:h, 0:w]
    cy, cx = h / 2.0, w / 2.0
    max_r = np.sqrt(cy**2 + cx**2)
    r = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2) / max_r
    falloff = 1.0 - (1.0 - VIGNETTE_MIN) * np.clip(r, 0, 1)
    gray = np.clip(gray * falloff, 0, 255).astype(np.uint8)

    out = np.stack([gray, gray, gray], axis=-1)
    return Image.fromarray(out, mode="RGB")


def real_daytime_sources(label):
    """Real, cached, color catalog/camera-trap sources for one class.

    Excludes local_root entries on purpose - see module docstring: some of those
    (the SWG pull) are already real IR, and board-captures-day1 is a Background
    entry anyway (wrong label). Only the frozen Roboflow exports qualify.
    """
    return [d for d in DATASETS if d.get("label") == label and not d.get("local_root")]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--count-per-class", type=int, default=COUNT_PER_CLASS)
    args = ap.parse_args()

    rng = random.Random(SELECT_SEED)
    grand_total = 0
    for label in ("Elephant", "Boar"):
        pool = []
        for ds in real_daytime_sources(label):
            root = os.path.join(CACHE_DIR, ds["slug"])
            if not os.path.isdir(root):
                raise RuntimeError(
                    f"{ds['slug']}: not cached at {root} - run "
                    "edge_impulse_upload_vision.py first (e.g. --dry-run) to populate it"
                )
            records, _drops, _background = parse_coco(root, ds)
            # Only real animal frames - a background/negative frame has nothing
            # for a pseudo-IR augmentation to usefully do.
            pool.extend(r for r in records if r["boxes"])
        rng.shuffle(pool)
        chosen = pool[: args.count_per_class]

        out_dir = os.path.join(OUT_ROOT, label.lower())
        os.makedirs(out_dir, exist_ok=True)
        images_meta = []
        annotations = []
        ann_id = 1
        for i, rec in enumerate(chosen):
            with Image.open(rec["path"]) as im:
                pseudo = to_pseudo_ir(im)
            out_name = f"pseudoir_{i:04d}_{os.path.basename(rec['path'])}"
            pseudo.save(os.path.join(out_dir, out_name), quality=90)
            images_meta.append(
                {"id": i, "file_name": out_name, "width": pseudo.width, "height": pseudo.height}
            )
            for box in rec["boxes"]:
                annotations.append(
                    {
                        "id": ann_id,
                        "image_id": i,
                        "category_id": 1,
                        "bbox": [box["x"], box["y"], box["width"], box["height"]],
                    }
                )
                ann_id += 1

        coco = {
            "images": images_meta,
            "annotations": annotations,
            "categories": [{"id": 1, "name": label, "supercategory": "animal"}],
        }
        with open(os.path.join(out_dir, "_annotations.coco.json"), "w") as fh:
            json.dump(coco, fh)

        grand_total += len(chosen)
        print(
            f"{label}: {len(chosen)} SYNTHETIC pseudo-IR images written to {out_dir} "
            f"(sampled from a real pool of {len(pool)})"
        )

    print(f"\nTotal: {grand_total} SYNTHETIC images - never a substitute for real IR, report separately")


if __name__ == "__main__":
    main()
