"""Source acoustic training clips from AudioSet's human-labelled segments.

Why this source. Every non-field clip in this project's `chainsaw`, `gunshot`
and `ambient` classes currently comes from Freesound or ESC-50. ml/acoustic/
README.md caveat 4 states the problem plainly: Freesound relevance rests on
uploader tagging, not expert verification, and clips were never listened
through. The 2026-09-15 audit found that one query (`"power saw"`) had pulled
136 clips of synthesiser sawtooth demos and factory noise into `chainsaw`.

AudioSet segments are labelled by trained human raters against a published
ontology, and that ontology contains the two classes this project scores worst
on as first-class entries:

    /m/01j4z9  Chainsaw           1,667 segments (unbalanced train)
    /m/032s66  Gunshot, gunfire   3,869 segments

against the 227 and 577 clips those classes hold today.

Label purity. A rater labelling a 10 s YouTube segment marks every event it
contains, so the multi-label annotations let this script reject what tag search
cannot see: a "chainsaw" segment that is also labelled Music is a video with a
soundtrack, not clean chainsaw audio. `CONFLICTS` encodes those rejections, and
cross-class collisions (a segment labelled both Chainsaw and Gunshot) are
dropped from both.

Licensing - read before this feeds anything shipped. AudioSet's *annotations*
are CC BY 4.0 from Google, but the underlying audio is YouTube content under
YouTube's terms, and is not redistributable. Training on it is standard practice
in audio ML (YAMNet and PANNs are both AudioSet-trained and shipped widely), but
it is not the same licensing position as a CC0 Freesound clip. This sits in the
same bucket as the unlicensed HiruDewmi elephant corpus (caveat 1) and must be
resolved the same way before any commercial gate. Clips are cached locally and
`manifest` records the provenance per clip; nothing here redistributes audio.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import subprocess
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

AUDIOSET_DIR = os.path.join("ml", "datasets", "acoustic", "raw", "_audioset")
OUT_DIR = os.path.join("ml", "datasets", "acoustic", "raw", "_audioset_clips")
SPLIT_SEED = 20260923

# Target class -> AudioSet label mids that define it.
CLASS_MIDS = {
    # Chainsaw is a single, unambiguous ontology entry.
    "chainsaw": ["/m/01j4z9"],
    # Gunshot core only. Machine gun (/m/04zjc) and Artillery fire (/m/0_1c)
    # are deliberately excluded by default: a poacher's rifle or shotgun is
    # what this class must detect, and artillery in particular is acoustically
    # an explosion, which would broaden the class toward the Explosion label
    # rather than sharpen it. `--include-heavy-weapons` adds them back.
    "gunshot": ["/m/032s66", "/m/02z32qm"],
    # Forest background, assembled from the ontology's natural-ambience entries.
    "ambient": [
        "/m/03m9d0z",  # Wind
        "/t/dd00092",  # Wind noise (microphone)
        "/m/09t49",  # Rustling leaves
        "/m/06mb1",  # Rain
        "/m/07r10fb",  # Raindrop
        "/t/dd00038",  # Rain on surface
        "/m/0j6m2",  # Stream
        "/m/0j2kx",  # Waterfall
        "/m/03vt0",  # Insect
        "/m/09xqv",  # Cricket
        "/m/09ld4",  # Frog
        "/m/015p6",  # Bird
        "/m/020bb7",  # Bird vocalization, bird call, bird song
        "/m/09d5_",  # Owl
        "/m/0jb2l",  # Thunderstorm
        "/m/0ngt1",  # Thunder
    ],
}

HEAVY_WEAPON_MIDS = ["/m/04zjc", "/m/0_1c"]  # Machine gun, Artillery fire

# Labels that disqualify a segment from a class regardless of the target label.
MUSIC = "/m/04rlf"
SINGING = "/m/015lz1"
SPEECH = "/m/09x0r"
CONFLICTS = {
    # Music/singing in a chainsaw video is a soundtrack over the top of the
    # sound of interest. Speech is *kept*: illegal logging in the field really
    # does co-occur with voices, so that is in-domain, not contamination.
    "chainsaw": [MUSIC, SINGING],
    "gunshot": [MUSIC, SINGING],
    # Ambient must be background only - any foreground event disqualifies it,
    # including the other two target classes.
    "ambient": [MUSIC, SINGING, SPEECH, "/m/01j4z9", "/m/032s66", "/m/02z32qm",
                "/m/04zjc", "/m/0_1c", "/m/014zdl", "/m/02_41", "/m/0k4j"],
}

SAMPLE_RATE = 16000
TEST_FRACTION = 0.20


def load_segments(audioset_dir: str, files: list[str]) -> list[dict]:
    """Parse AudioSet csvs: YTID, start, end, "mid,mid,..."."""
    rows = []
    for name in files:
        path = os.path.join(audioset_dir, name)
        if not os.path.exists(path):
            print(f"  missing {name}, skipping", file=sys.stderr)
            continue
        with open(path, newline="") as fh:
            for line in fh:
                if line.startswith("#"):
                    continue
                parts = next(iter(csv.reader([line], skipinitialspace=True)))
                if len(parts) < 4:
                    continue
                rows.append(
                    {
                        "ytid": parts[0],
                        "start": float(parts[1]),
                        "end": float(parts[2]),
                        "mids": set(parts[3].split(",")),
                        "csv": name,
                    }
                )
    return rows


def select(rows: list[dict], class_mids: dict, per_class_cap: int) -> dict[str, list[dict]]:
    """Pick pure segments per class, rejecting conflicts and cross-class collisions."""
    stats = Counter()
    owners = defaultdict(set)  # ytid+start -> classes claiming it
    candidates: dict[str, list[dict]] = {c: [] for c in class_mids}

    for r in rows:
        for cls, mids in class_mids.items():
            if not (r["mids"] & set(mids)):
                continue
            if r["mids"] & set(CONFLICTS.get(cls, [])):
                stats[f"{cls}:conflict"] += 1
                continue
            key = f"{r['ytid']}@{r['start']}"
            owners[key].add(cls)
            candidates[cls].append({**r, "key": key})
            stats[f"{cls}:candidate"] += 1

    picked: dict[str, list[dict]] = {}
    rng = random.Random(SPLIT_SEED)
    for cls, items in candidates.items():
        # A segment claimed by two target classes is ambiguous for both.
        clean = [i for i in items if len(owners[i["key"]]) == 1]
        stats[f"{cls}:cross_class_drop"] += len(items) - len(clean)
        # Deduplicate by key, then cap with a seeded sample so reruns match.
        seen, uniq = set(), []
        for i in clean:
            if i["key"] not in seen:
                seen.add(i["key"])
                uniq.append(i)
        uniq.sort(key=lambda i: i["key"])
        if per_class_cap and len(uniq) > per_class_cap:
            uniq = rng.sample(uniq, per_class_cap)
            uniq.sort(key=lambda i: i["key"])
        picked[cls] = uniq
    return picked, stats


def download(item: dict, cls: str, out_dir: str, seconds: float, tag: str = "as") -> dict | None:
    """Fetch one 10 s segment as mono wav. Returns a manifest record or None.

    `tag` records which corpus selected the segment ("as" AudioSet, "vs"
    VGGSound). It is provenance only - the grouping key is the video id, so a
    video found by both corpora still counts as one recording.
    """
    name = f"{cls}_{tag}_{item['ytid']}_{int(item['start'])}"
    dest = os.path.join(out_dir, f"{name}.wav")
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        return {"name": name, "path": dest, "cached": True}

    url = f"https://www.youtube.com/watch?v={item['ytid']}"
    cmd = [
        "yt-dlp", "-f", "bestaudio", "--no-playlist", "--quiet", "--no-warnings",
        "--download-sections", f"*{item['start']}-{item['start'] + seconds}",
        "--force-keyframes-at-cuts",
        "-x", "--audio-format", "wav",
        "--postprocessor-args", f"ffmpeg:-ac 1 -ar {SAMPLE_RATE}",
        "-o", os.path.join(out_dir, f"{name}.%(ext)s"), url,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=180, check=False)
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode != 0 or not os.path.exists(dest):
        return None
    with open(dest, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    return {"name": name, "path": dest, "cached": False, "sha256": digest}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--audioset-dir", default=AUDIOSET_DIR)
    ap.add_argument("--out-dir", default=OUT_DIR)
    ap.add_argument("--classes", nargs="*", default=["chainsaw", "gunshot", "ambient"])
    ap.add_argument("--cap", type=int, default=800, help="max segments per class (0 = uncapped)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--include-heavy-weapons", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="plan only, download nothing")
    ap.add_argument("--csvs", nargs="*", default=["unbalanced_train_segments.csv",
                                                  "balanced_train_segments.csv",
                                                  "eval_segments.csv"])
    args = ap.parse_args()

    mids = {c: list(CLASS_MIDS[c]) for c in args.classes}
    if args.include_heavy_weapons and "gunshot" in mids:
        mids["gunshot"] += HEAVY_WEAPON_MIDS

    print("reading AudioSet segment lists...")
    rows = load_segments(args.audioset_dir, args.csvs)
    print(f"  {len(rows)} segments across {len(args.csvs)} files\n")

    picked, stats = select(rows, mids, args.cap)
    print(f"{'class':<12}{'candidates':>12}{'conflict':>11}{'cross-class':>13}{'selected':>10}")
    for cls in mids:
        print(f"{cls:<12}{stats[f'{cls}:candidate']:>12}{stats[f'{cls}:conflict']:>11}"
              f"{stats[f'{cls}:cross_class_drop']:>13}{len(picked[cls]):>10}")

    if args.dry_run:
        print("\ndry run - nothing downloaded")
        return 0

    os.makedirs(args.out_dir, exist_ok=True)
    manifest_path = os.path.join(args.out_dir, "manifest.json")
    if os.path.exists(manifest_path):
        with open(manifest_path) as fh:
            manifest = json.load(fh)
    else:
        manifest = {"clips": []}
    have = {c["name"] for c in manifest["clips"]}
    rng = random.Random(SPLIT_SEED)

    for cls, items in picked.items():
        todo = [i for i in items if f"{cls}_as_{i['ytid']}_{int(i['start'])}" not in have]
        print(f"\n=== {cls}: {len(todo)} to fetch ({len(items) - len(todo)} already cached) ===")
        ok = fail = 0
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(download, i, cls, args.out_dir, args.seconds): i for i in todo}
            for n, fut in enumerate(as_completed(futures), 1):
                item = futures[fut]
                rec = fut.result()
                if rec is None:
                    fail += 1
                else:
                    ok += 1
                    manifest["clips"].append(
                        {
                            "name": rec["name"],
                            "label": cls,
                            "ytid": item["ytid"],
                            "start_s": item["start"],
                            "mids": sorted(item["mids"]),
                            "source": "audioset",
                            "license": "annotations CC BY 4.0 (Google); audio is YouTube content, not redistributable",
                            "category": "testing" if rng.random() < TEST_FRACTION else "training",
                            "sha256": rec.get("sha256"),
                        }
                    )
                if n % 25 == 0 or n == len(todo):
                    print(f"  {n}/{len(todo)}  ok={ok} fail={fail}", flush=True)
                    with open(manifest_path, "w") as fh:
                        json.dump(manifest, fh, indent=1)
        with open(manifest_path, "w") as fh:
            json.dump(manifest, fh, indent=1)
        print(f"  {cls}: {ok} fetched, {fail} unavailable (deleted/private/region-locked)")

    got = Counter(c["label"] for c in manifest["clips"])
    print(f"\ncache now holds: {dict(got)}")
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
