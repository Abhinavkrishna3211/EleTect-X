"""Full-census audit, step 2b: hash ml/datasets/vision/pseudo_ir/{boar,elephant}
the same way audit_hash_raw_disk.py hashes ml/datasets/vision/raw/. Pseudo-IR
synthetic images live in a sibling directory, not under raw/, so they need
their own pass; merged into the same by-hash join at audit stage 3.

Read-only. No data mutation.
"""
import hashlib
import json
import os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
PSEUDO_IR = os.path.join(ROOT, "ml", "datasets", "vision", "pseudo_ir")
OUT_PATH = os.path.join(ROOT, "ml", "vision", "_audit_disk_hashes_pseudo_ir.json")

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    by_hash = {}
    per_source_count = {}
    for sub in sorted(os.listdir(PSEUDO_IR)):
        sub_root = os.path.join(PSEUDO_IR, sub)
        if not os.path.isdir(sub_root):
            continue
        src_name = f"pseudo-ir-{sub}"
        count = 0
        for dirpath, _dirnames, filenames in os.walk(sub_root):
            for fn in filenames:
                if os.path.splitext(fn)[1].lower() not in IMAGE_EXT:
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, sub_root)
                digest = sha256_of(full)
                by_hash.setdefault(digest, []).append({"source": src_name, "rel_path": rel, "abs_path": full})
                count += 1
        per_source_count[src_name] = count
        print(f"{src_name}: {count} image files")

    with open(OUT_PATH, "w") as fh:
        json.dump({"by_hash": by_hash, "per_source_count": per_source_count}, fh)
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
