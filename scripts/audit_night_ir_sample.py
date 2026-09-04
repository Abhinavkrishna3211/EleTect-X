"""Night/IR proportion audit for three sources the Boar-gap close-out plan (4 Sep
2026, Step 4.1) named as never counted: swg-eurasian-wild-pig (2,350 imgs, not the
1,800 the plan estimated - counted here), wcs-sus-scrofa (828), and
asian-elephants-dataset-v1 (2,358, Elephant's largest source, same undercount
mechanism as Boar). Same discipline as audit_boar_sample.py's existing 30-per-source
contamination pass: seeded sample, contact sheet, opened by eye, report n checked and
the fraction night/IR. No spot-check-and-assume.

asian-elephants-dataset-v1 is COCO-annotated across train/test/valid splits and reuses
parse()/contact_sheet() from audit_boar_sample.py unchanged. swg-eurasian-wild-pig and
wcs-sus-scrofa are flat, un-annotated raw image pools - EI dataset names that resolve
to label-only species subdirectories under the raw swg-camera-traps/ and
wcs-camera-traps/ pools (confirmed 4 Sep by matching filenames listed in each source's
uploaded-1097972-<source>.json manifest against the on-disk species subdirectories:
swg-camera-traps/eurasian_wild_pig/ and wcs-camera-traps/sus_scrofa/). They have no
boxes to draw, so their records carry an empty "boxes" list - contact_sheet() already
no-ops the box-drawing loop on an empty list, so it is reused unchanged rather than
writing a second renderer.
"""
import json
import os
import random

from audit_boar_sample import RAW, contact_sheet, parse

FLAT_SOURCES = {
    "swg-eurasian-wild-pig": os.path.join(RAW, "swg-camera-traps", "eurasian_wild_pig"),
    "wcs-sus-scrofa": os.path.join(RAW, "wcs-camera-traps", "sus_scrofa"),
}

COCO_SOURCES = {
    "asian-elephants-dataset-v1": os.path.join(RAW, "asian-elephants-dataset-v1"),
}

SAMPLE_N = 40
CHUNK = 15
OUT_DIR = os.path.join(RAW, "_audit_tmp")
SEED_BASE = 202609041  # 4 Sep 2026, first night/IR proportion audit pass


def flat_records(dir_path):
    names = sorted(f for f in os.listdir(dir_path) if f.lower().endswith(".jpg"))
    return [{"name": n, "path": os.path.join(dir_path, n), "boxes": []} for n in names]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    pools = {}

    for i, (label, dir_path) in enumerate(FLAT_SOURCES.items()):
        pools[label] = flat_records(dir_path)

    for i, (label, dir_path) in enumerate(COCO_SOURCES.items()):
        pools[label] = parse(dir_path)

    manifest = {}
    for i, (label, pool) in enumerate(pools.items()):
        print(f"{label} pool: {len(pool)}")
        r = random.Random(SEED_BASE + i)
        sample = r.sample(pool, min(SAMPLE_N, len(pool)))
        manifest[label] = {"pool_size": len(pool), "sample_size": len(sample)}
        for j in range(0, len(sample), CHUNK):
            chunk = sample[j : j + CHUNK]
            sheet_path = os.path.join(OUT_DIR, f"nightir_{label}_{j:03d}.png")
            contact_sheet(chunk, sheet_path)
            with open(os.path.join(OUT_DIR, f"nightir_{label}_{j:03d}.json"), "w") as fh:
                json.dump([r_["name"] for r_ in chunk], fh, indent=2)

    with open(os.path.join(OUT_DIR, "nightir_manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"wrote {os.path.join(OUT_DIR, 'nightir_manifest.json')}")


if __name__ == "__main__":
    main()
