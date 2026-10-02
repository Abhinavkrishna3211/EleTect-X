"""Full-census audit, step 1: pull the complete live raw-data listing for
project 1097972 - every sample actually stored in the project right now,
with its category, label, bounding boxes and content hash - and cache it to
disk. This is the audit's ground truth for "what exists and how is it
labeled": it comes straight from Edge Impulse itself, so it is immune to any
drift between the local DATASETS script, the on-disk raw/ cache, and what is
actually live (several staged raw/ sources - board-captures-field1,
board-captures-window1, user-videos-29aug - were found NOT wired into the
current DATASETS list despite having upload-tracking files on disk; this
listing settles by direct observation whether their content is still live).

Read-only. No data mutation, no board access.
"""
import json
import os
import urllib.parse
import urllib.request

STUDIO = "https://studio.edgeimpulse.com/v1/api"
OUT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir,
    "ml", "vision", "_audit_live_manifest.json",
)


def request(url, api_key):
    req = urllib.request.Request(url, headers={"x-api-key": api_key})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def fetch_all(project_id, api_key):
    samples = []
    offset = 0
    page_size = 1000
    while True:
        params = urllib.parse.urlencode({"limit": page_size, "offset": offset, "category": "all"})
        data = request(f"{STUDIO}/{project_id}/raw-data?{params}", api_key)
        batch = data.get("samples", [])
        if not batch:
            break
        for s in batch:
            samples.append({
                "id": s.get("id"),
                "filename": s.get("filename"),
                "category": s.get("category"),
                "label": s.get("label"),
                "boundingBoxes": s.get("boundingBoxes") or [],
                "imageDimensions": s.get("imageDimensions"),
                "sha256Hash": s.get("sha256Hash"),
            })
        print(f"  fetched {len(samples)} so far (offset {offset})")
        offset += len(batch)
        if len(batch) < page_size:
            break
    return samples


def main():
    api_key = os.environ["EI_API_KEY"]
    project_id = os.environ.get("EI_PROJECT_ID", "1097972")
    print(f"Fetching full live raw-data listing for project {project_id}...")
    samples = fetch_all(project_id, api_key)
    print(f"Total live samples: {len(samples)}")

    by_category = {}
    by_label = {}
    for s in samples:
        by_category[s["category"]] = by_category.get(s["category"], 0) + 1
        lbl = (s["label"] or "-").split(",")[0].strip() or "-"
        by_label[lbl] = by_label.get(lbl, 0) + 1
    print("By category:", by_category)
    print("By label (primary):", by_label)

    with open(OUT_PATH, "w") as fh:
        json.dump(samples, fh)
    print(f"Wrote {OUT_PATH} ({os.path.getsize(OUT_PATH) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
