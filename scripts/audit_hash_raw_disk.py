"""Full-census audit, step 2: walk every raw/ source directory on disk and
hash every image file (sha256, matching what Edge Impulse itself hashes on
ingestion), so each live sample from audit_fetch_live_manifest.py's manifest
can be joined back to its exact local file and source directory by content
hash - immune to filename drift (rename maps, roboflow re-exports) and to
which directories the current DATASETS list happens to reference right now.

Skips: *-coco.zip archives, uploaded-*.json / duplicates-*.json trackers,
_audit_tmp/ (our own prior audit renders, not source content), and known
zero-file *-meta/ directories.

Read-only. No data mutation.
"""
import hashlib
import json
import os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
RAW = os.path.join(ROOT, "ml", "datasets", "vision", "raw")
OUT_PATH = os.path.join(ROOT, "ml", "vision", "_audit_disk_hashes.json")

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SKIP_DIRS = {"_audit_tmp"}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    entries = os.listdir(RAW)
    source_dirs = sorted(
        d for d in entries
        if os.path.isdir(os.path.join(RAW, d)) and d not in SKIP_DIRS
    )
    print(f"Found {len(source_dirs)} top-level source directories to hash")

    by_hash = {}
    per_source_count = {}
    n_done = 0
    for src in source_dirs:
        src_root = os.path.join(RAW, src)
        count = 0
        for dirpath, _dirnames, filenames in os.walk(src_root):
            for fn in filenames:
                ext = os.path.splitext(fn)[1].lower()
                if ext not in IMAGE_EXT:
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, src_root)
                digest = sha256_of(full)
                by_hash.setdefault(digest, []).append({"source": src, "rel_path": rel, "abs_path": full})
                count += 1
                n_done += 1
                if n_done % 2000 == 0:
                    print(f"  hashed {n_done} files so far ({src}: {count})")
        per_source_count[src] = count
        print(f"{src}: {count} image files")

    print(f"\nTotal image files hashed: {n_done}")
    print(f"Distinct content hashes: {len(by_hash)}")
    dupes = {h: v for h, v in by_hash.items() if len(v) > 1}
    print(f"Hashes with >1 file (exact duplicates, incl. cross-source): {len(dupes)}")

    with open(OUT_PATH, "w") as fh:
        json.dump({"by_hash": by_hash, "per_source_count": per_source_count}, fh)
    print(f"Wrote {OUT_PATH} ({os.path.getsize(OUT_PATH) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
