"""Full-census audit, step 3: join the live raw-data manifest (what Edge
Impulse actually has, right now, with labels/boxes) to the on-disk hash maps
(where each piece of content actually sits on disk, and which source
directory it came from), by content hash. This settles - by direct evidence,
not inference from any script's current DATASETS list - exactly which raw/
source each live sample belongs to, and flags:

  - live samples with no on-disk match at all ("orphan-live": content that
    is live in the project but not found in any hashed local directory -
    would need to be pulled from Edge Impulse directly to audit by eye)
  - on-disk source directories with zero live matches ("dead-disk": staged
    content that never made it live, or was live once and was since deleted
    - board-captures-field1 is the known suspect here, since it has an
    upload-tracking file but was absent from a DATASETS grep)

Writes ml/vision/_audit_master_manifest.json: one row per live sample, with
its source directory, local path (if found), category, label and boxes -
the single input the contact-sheet renderer and progress tracker consume for
the rest of the census. Read-only against the project; only writes new files
under ml/vision/.
"""
import json
import os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
VISION = os.path.join(ROOT, "ml", "vision")
LIVE_PATH = os.path.join(VISION, "_audit_live_manifest.json")
DISK_PATH = os.path.join(VISION, "_audit_disk_hashes.json")
DISK_PSEUDO_PATH = os.path.join(VISION, "_audit_disk_hashes_pseudo_ir.json")
OUT_PATH = os.path.join(VISION, "_audit_master_manifest.json")


def main():
    with open(LIVE_PATH) as fh:
        live = json.load(fh)
    with open(DISK_PATH) as fh:
        disk = json.load(fh)
    by_hash = disk["by_hash"]
    disk_source_counts = dict(disk["per_source_count"])

    with open(DISK_PSEUDO_PATH) as fh:
        disk_pseudo = json.load(fh)
    for h, entries in disk_pseudo["by_hash"].items():
        by_hash.setdefault(h, []).extend(entries)
    disk_source_counts.update(disk_pseudo["per_source_count"])

    print(f"Live samples: {len(live)}")
    print(f"Distinct disk hashes: {len(by_hash)}")

    matched_source_counts = {}
    orphan_live = []
    rows = []
    for s in live:
        digest = s.get("sha256Hash")
        candidates = by_hash.get(digest) if digest else None
        if not candidates:
            orphan_live.append(s)
            source = None
            local_path = None
        else:
            # Prefer non-"-coco" / non-duplicate-looking dir names deterministically:
            # just take the first hashed hit; multiple hits (same content staged
            # under two source dirs, e.g. fox-xdf1l vs fox-xdf1l-v1) are recorded
            # in full so the join is auditable, not silently collapsed.
            source = candidates[0]["source"]
            local_path = candidates[0]["abs_path"]
        rows.append({
            "id": s["id"],
            "filename": s["filename"],
            "category": s["category"],
            "label": s["label"],
            "boundingBoxes": s["boundingBoxes"],
            "imageDimensions": s["imageDimensions"],
            "sha256Hash": digest,
            "source": source,
            "local_path": local_path,
            "disk_candidates": candidates,
        })
        if source:
            matched_source_counts[source] = matched_source_counts.get(source, 0) + 1

    print(f"\nOrphan live samples (no on-disk match found): {len(orphan_live)}")
    if orphan_live:
        by_label = {}
        for s in orphan_live:
            lbl = (s.get("label") or "-").split(",")[0].strip() or "-"
            by_label[lbl] = by_label.get(lbl, 0) + 1
        print("  by label:", by_label)
        print("  first 10 filenames:", [s["filename"] for s in orphan_live[:10]])

    print("\nLive sample count per matched source directory:")
    for src, n in sorted(matched_source_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {src}: {n}")

    print("\nDisk source directories with on-disk files but ZERO live matches (dead-disk):")
    for src, n in sorted(disk_source_counts.items()):
        if n > 0 and matched_source_counts.get(src, 0) == 0:
            print(f"  {src}: {n} files on disk, 0 live")

    with open(OUT_PATH, "w") as fh:
        json.dump(rows, fh)
    print(f"\nWrote {OUT_PATH} ({os.path.getsize(OUT_PATH) / 1e6:.1f} MB, {len(rows)} rows)")


if __name__ == "__main__":
    main()
