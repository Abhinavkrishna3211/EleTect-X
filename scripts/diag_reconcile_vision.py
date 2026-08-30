"""One-off diagnostic (not part of the regular pipeline): find exactly which live
raw-data samples in project 1097972 do not belong to any class's expected
training/testing filename set in ml/vision/dataset_manifest.json, to explain the
995-sample HARD FAIL reconcile_project_counts() found on 28 Aug after the
broadcast/African-stock cleanup pass. Filename-based, not content-hash: remote
"filename" has its final extension stripped by Edge Impulse, so both sides are
compared with extensions removed.

28 Aug, second pass: also checks the CROSS-CATEGORY case (same normalized name
present live in one of training/testing but expected by the fresh manifest in
the other) - a train/test split reassignment would show up as an "orphan" in
one direction and "missing" in the other for the exact same file, which is a
very different (and much less alarming) finding than genuinely absent content.
"""
import json
import os
import re
import sys
import urllib.request

STUDIO = "https://studio.edgeimpulse.com/v1/api"
_EXT_SUFFIX = re.compile(r"\.(jpg|jpeg|png|bmp|webp)$", re.IGNORECASE)


def _request(url, api_key):
    req = urllib.request.Request(url, headers={"x-api-key": api_key})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def remote_samples(project_id, api_key):
    samples = []
    for category in ("training", "testing"):
        offset = 0
        limit = 1000
        while True:
            data = _request(
                f"{STUDIO}/{project_id}/raw-data?category={category}&limit={limit}&offset={offset}",
                api_key,
            )
            batch = data.get("samples", [])
            for s in batch:
                s["_category"] = category
            samples.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
    return samples


def main():
    api_key = os.environ["EI_API_KEY"]
    project_id = os.environ.get("EI_PROJECT_ID", "1097972")
    manifest = json.load(open(r"D:\projects\EleTect-X\ml\vision\dataset_manifest.json"))["classes"]

    expected = {"training": {}, "testing": {}}
    expected_any = {}
    for label, entry in manifest.items():
        for category in ("training", "testing"):
            for name in entry[category]:
                norm = _EXT_SUFFIX.sub("", name)
                expected[category][norm] = (label, name)
                expected_any.setdefault(norm, []).append((category, label, name))

    print("Fetching remote sample list...")
    remote = remote_samples(project_id, api_key)
    print(f"  {len(remote)} remote samples")
    remote_norm = {}
    for s in remote:
        norm = _EXT_SUFFIX.sub("", s["filename"])
        remote_norm.setdefault(norm, []).append(s)

    orphans = []
    for s in remote:
        cat = s["_category"]
        norm = _EXT_SUFFIX.sub("", s["filename"])
        if norm not in expected[cat]:
            orphans.append(s)
    print(f"\n{len(orphans)} live samples not in any expected training/testing filename set")

    same_cat_wrong = 0
    cross_cat = 0
    truly_gone = 0
    cross_examples = []
    for s in orphans:
        norm = _EXT_SUFFIX.sub("", s["filename"])
        hits = expected_any.get(norm)
        if not hits:
            truly_gone += 1
            continue
        # present in expected under some category - since it failed the per-category
        # check above, it must be a different category than s["_category"]
        cross_cat += 1
        if len(cross_examples) < 10:
            cross_examples.append((s["_category"], s["filename"], hits))

    print(f"\nOf the {len(orphans)} orphans:")
    print(f"  {cross_cat} ARE in the expected set, just under a different category (train/test reassignment)")
    print(f"  {truly_gone} are not in the expected set under EITHER category (genuinely gone)")
    print("\nCross-category examples:")
    for cat, fn, hits in cross_examples:
        print(f"  live in {cat}: {fn!r} -> expected in {hits}")

    from collections import Counter

    prefixes = Counter()
    for s in orphans:
        fn = s["filename"]
        prefixes[fn.split("-", 1)[0].split("_", 1)[0][:20]] += 1
    print("\nTop 25 orphan filename prefixes:")
    for prefix, n in prefixes.most_common(25):
        print(f"  {prefix!r}: {n}")

    # label breakdown of orphans
    label_counts = Counter(s.get("label") for s in orphans)
    print("\nOrphan label breakdown (top 15):")
    for label, n in label_counts.most_common(15):
        print(f"  {label!r}: {n}")

    print("\nSample of 15 orphan filenames:")
    for s in orphans[:15]:
        print(f"  [{s['_category']}] id={s['id']} label={s.get('label')!r} filename={s['filename']!r}")

    # reverse: expected but missing live (either category)
    missing = []
    for category in ("training", "testing"):
        for norm, (label, name) in expected[category].items():
            if norm not in remote_norm:
                missing.append((category, label, name))
            elif all(s["_category"] != category for s in remote_norm[norm]):
                pass  # already counted as cross-category above from the other side
    print(f"\n{len(missing)} expected samples with NO live sample at all under that name (either category)")
    label_counts2 = Counter(label for _, label, _ in missing)
    print("Missing label breakdown:")
    for label, n in label_counts2.most_common(15):
        print(f"  {label!r}: {n}")
    for category, label, name in missing[:15]:
        print(f"  [{category}] {label}: {name}")


if __name__ == "__main__":
    main()
