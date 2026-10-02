"""Build a leak-proof index of the local acoustic clip cache.

The Edge Impulse pipeline splits train/test at the *file* level. Several of the
upstream corpora ship multiple files that are the same underlying recording:

  * ESC-50 names clips `<fold>-<clipid>-<take>-<target>.wav`; takes A/B/C of one
    clip id are different 5 s excerpts of a single Freesound source.
  * The HiruDewmi elephant corpus ships its own train/test/validate folders that
    overlap - `Rumble09.wav` is present in all three - and additionally carries
    `_aug_N` copies produced by augmenting a clip *before* the split was drawn.
  * The cache keeps two normalisation variants of every clip (`.norm.wav` and
    `.e2.norm.wav`).

Splitting those at file level puts copies of one recording on both sides of the
train/test boundary, which inflates held-out recall. This module assigns every
file a `group` key identifying its source *recording*, so a split can be drawn
with all copies of a recording held on the same side.

Output: index.json - one record per usable file, with label, group, variant and
path. `freeze_split.py` consumes it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import wave
from collections import Counter, defaultdict

CACHE = os.path.join("ml", "datasets", "acoustic", "raw")
# AudioSet segments land here straight from yt-dlp, outside the cache's
# `.<window>s.norm.wav` convention, so they are scanned separately.
AUDIOSET_DIR = os.path.join(CACHE, "_audioset_clips")
VGGSOUND_DIR = os.path.join(CACHE, "_vggsound_clips")
YT_DIRS = (AUDIOSET_DIR, VGGSOUND_DIR)

# Wire scheme. `vehicle`/`boar`/`predator` stay cached but out of the scheme -
# see ml/acoustic/README.md's class-scheme section for why each was dropped.
CLASSES = ("ambient", "chainsaw", "elephant_call", "gunshot")

# Flipped by --audioset. Kept off by default so the frozen split stays
# reproducible while the download is still running.
INCLUDE_AUDIOSET = False

# Sources excluded unless `--include-source` names them.
#
# `zenodo_aru` is the long-range chainsaw ARU corpus. It is correctly ingested and
# correctly grouped, and it still must not reach a shipped model: trained in, it
# costs 14-17 points of chainsaw precision and drops recall on our own field
# ambient recordings from 97.9% to 68.7%, in exchange for about one point of
# chainsaw recall that sits inside the confidence interval. Two ingest ratios were
# tried (436:163 and 392:545 chainsaw:ambient) and both regressed. These are SWIFT
# units in Mediterranean forest and the domain shift survives rebalancing. The
# audio is kept on disk because the licence is clean and a future domain-adaptation
# attempt may want it; it is excluded here so no default run can pick it up by
# accident. See the 2026-09-23 result section in ml/acoustic/README.md.
DEFAULT_EXCLUDED_SOURCES = ("zenodo_aru",)

# Cache filenames prefix the label; elephant is stored as `elephant_call_...`.
PREFIX_TO_LABEL = {
    "ambient": "ambient",
    "chainsaw": "chainsaw",
    "elephant_call": "elephant_call",
    "gunshot": "gunshot",
}

# <label>_<fold>-<clipid>-<take>-<target>.wav  (ESC-50)
ESC50 = re.compile(r"^(?P<label>[a-z_]+)_(?P<fold>\d+)-(?P<clip>\d+)-(?P<take>[A-Z])-(?P<target>\d+)\.wav$")
# elephant_call_data_<split>_<category>_<name>[_aug_N].wav  (HiruDewmi)
HIRU = re.compile(r"^elephant_call_data_(?P<split>train|test|validate)_(?P<rest>.+?)(?:_aug_(?P<aug>\d+))?\.wav$")
# <label>_<numeric id>  (Freesound)
FREESOUND = re.compile(r"^(?P<label>[a-z_]+)_(?P<id>\d+)$")
# <label>_<uuid>  (Mendeley / ingestion exports)
UUID = re.compile(r"^(?P<label>[a-z_]+)_(?P<uuid>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")
# <label>_xiao_esp32s3_...  /  <label>_laptop_...  (project-owned field captures)
FIELD = re.compile(r"^(?P<label>[a-z_]+)_(?P<rest>(?:xiao|laptop)_.+)$")
# A trailing `.<n>` on a field capture is a chunk index, not a separate capture:
# `..._bg.1` through `..._bg.35` are consecutive slices of one continuous
# recording session. Keying on the chunk made 119 files look like 119
# independent recordings, which let slices of a single session fall on both
# sides of the split - the exact leak this index exists to prevent, and the
# reason the field chainsaw slice scored a perfect 100%. Collapse the index so
# a session moves as one unit. Captures named `..._Elephant_7_4tveetfu` carry a
# per-capture id instead and are genuinely distinct, so they are left alone.
FIELD_CHUNK = re.compile(r"^(?P<session>.+)\.\d+$")

# <label>_zen_<recording>_w<NNNN>  (Zenodo 5824433, long-range chainsaw ARU corpus)
# Windows are cut from continuous multi-hour recordings, so the recording - not
# the window - is the unit. This is the same shape as the field-capture chunk
# bug: hundreds of windows from one afternoon in one forest are one recording's
# worth of evidence, and splitting them apart would relearn that lesson.
ZENODO = re.compile(r"^(?P<label>ambient|chainsaw)_zen_(?P<rec>.+?)_w\d+$")

# <label>_<as|vs>_<youtube id>_<offset>.wav  (AudioSet / VGGSound segments)
# Several segments are cut from one video, so the video id - not the offset,
# and not which corpus selected it - is the recording. Both corpora index the
# same YouTube, so a video present in each would otherwise straddle the
# train/test boundary under two different keys and the held-out number would
# be fiction.
YOUTUBE = re.compile(r"^(?P<label>[a-z_]+)_(?P<corpus>as|vs)_(?P<vid>[\w-]{11})_(?P<off>[\d.]+)$")

# `<stem>.<window>s[.eN].norm.wav`
FILENAME = re.compile(r"^(?P<stem>.+?)\.(?P<window>\d+)s(?:\.(?P<enh>e\d+))?\.norm\.wav$")


def classify_stem(stem: str) -> tuple[str | None, str | None, str]:
    """Return (label, group, source) for a cache stem.

    `group` identifies the underlying *recording*, so every copy, take and
    augmentation of one recording shares it.
    """
    m = ZENODO.match(stem)
    if m:
        return m.group("label"), f"zen:{m.group('rec')}", "zenodo_aru"

    m = YOUTUBE.match(stem)
    if m:
        label = PREFIX_TO_LABEL.get(m.group("label"))
        source = "audioset" if m.group("corpus") == "as" else "vggsound"
        return label, f"yt:{m.group('vid')}", source

    m = ESC50.match(stem)
    if m:
        label = PREFIX_TO_LABEL.get(m.group("label"))
        # Take A/B/C of one clip id are excerpts of a single source recording.
        #
        # The clip id *is* the Freesound id - ESC-50 is cut from Freesound - so
        # this shares the `fs:` namespace deliberately. Five chainsaw recordings
        # are held under both corpora, and keying them apart put one of them on
        # both sides of the split at once.
        return label, f"fs:{m.group('clip')}", "esc50"

    m = HIRU.match(stem)
    if m:
        # Drop the corpus's own split folder and any `_aug_N` suffix: what is
        # left names the recording itself.
        return "elephant_call", f"hiru:{m.group('rest')}", "hiru_dewmi"

    m = FIELD.match(stem)
    if m:
        label = PREFIX_TO_LABEL.get(m.group("label"))
        rest = m.group("rest")
        chunk = FIELD_CHUNK.match(rest)
        return label, f"field:{chunk.group('session') if chunk else rest}", "field_capture"

    m = FREESOUND.match(stem)
    if m:
        label = PREFIX_TO_LABEL.get(m.group("label"))
        return label, f"fs:{m.group('id')}", "freesound"

    m = UUID.match(stem)
    if m:
        label = PREFIX_TO_LABEL.get(m.group("label"))
        return label, f"uu:{m.group('uuid')}", "mendeley_or_export"

    for prefix, label in PREFIX_TO_LABEL.items():
        if stem.startswith(prefix + "_"):
            return label, f"stem:{stem}", "unclassified"
    return None, None, "unknown"


def build_audioset(directory: str, records: list[dict], skipped: Counter) -> None:
    """Add AudioSet/VGGSound segments. These are raw yt-dlp cuts, not normalised
    renders, so they carry no `.norm` variant - every one is canonical."""
    if not os.path.isdir(directory):
        return
    with os.scandir(directory) as it:
        for entry in it:
            if not entry.is_file() or not entry.name.endswith(".wav"):
                continue
            stem = entry.name[: -len(".wav")]
            label, group, source = classify_stem(stem)
            if label is None or label not in CLASSES or source not in ("audioset", "vggsound"):
                skipped["audioset_unparsed"] += 1
                continue
            records.append(
                {
                    "path": entry.path.replace("\\", "/"),
                    "file": entry.name,
                    "stem": stem,
                    "label": label,
                    "group": group,
                    "source": source,
                    "variant": "base",
                }
            )


def build(cache: str, window: int) -> list[dict]:
    records = []
    skipped = Counter()
    with os.scandir(cache) as it:
        for entry in it:
            if not entry.is_file() or not entry.name.endswith(".wav"):
                continue
            fm = FILENAME.match(entry.name)
            if not fm:
                skipped["unparsed_filename"] += 1
                continue
            if int(fm.group("window")) != window:
                skipped["other_window"] += 1
                continue
            label, group, source = classify_stem(fm.group("stem"))
            if label is None or label not in CLASSES:
                skipped["out_of_scheme" if label is None else "dropped_class"] += 1
                continue
            records.append(
                {
                    "path": entry.path.replace("\\", "/"),
                    "file": entry.name,
                    "stem": fm.group("stem"),
                    "label": label,
                    "group": group,
                    "source": source,
                    # `.norm` is the canonical render; `.eN.norm` is an alternate
                    # normalisation of identical audio, usable as train-only data.
                    "variant": fm.group("enh") or "base",
                }
            )
    if INCLUDE_AUDIOSET:
        for d in YT_DIRS:
            build_audioset(d, records, skipped)
    return records, skipped


def merge_identical_payloads(records: list[dict], cache_path: str) -> None:
    """Union groups whose audio payloads are byte-identical.

    Every other rule in this module infers the recording from the *filename*,
    which is all a name can tell you. It cannot see two different names holding
    the same audio, and the corpus has exactly that: the HiruDewmi elephant set
    ships `Roar35` and `Roar54` with identical payloads, likewise `Trumpet08`,
    `Trumpet10` and `Trumpet14`, and two Mendeley gunshots carry distinct UUIDs
    over one recording. Three such pairs landed across the train/test boundary
    and were invisible to every name-based rule, including all three fixes ADR
    0025 describes.

    Hashing the decoded frames rather than the file means a re-encode or a
    header difference cannot hide a duplicate either. Identical audio is one
    recording by definition, so the groups are unioned and the split then moves
    them together.
    """
    cache: dict[str, str] = {}
    if cache_path and os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as fh:
            cache = json.load(fh)

    print(f"hashing {len(records)} payloads for duplicate detection ...")
    by_hash: dict[str, list[dict]] = defaultdict(list)
    fresh = 0
    unreadable: list[tuple[str, str]] = []
    for i, r in enumerate(records, 1):
        key = r["file"]
        h = cache.get(key)
        if h is None:
            try:
                with wave.open(r["path"], "rb") as w:
                    h = hashlib.sha256(w.readframes(w.getnframes())).hexdigest()
            except Exception as e:               # noqa: BLE001 - reported below, never silent
                # A file that cannot be hashed is a file whose duplicates this
                # pass cannot see, so it is named rather than skipped quietly.
                unreadable.append((r["file"], str(e)))
                continue
            cache[key] = h
            fresh += 1
        by_hash[h].append(r)
        if i % 2000 == 0:
            print(f"  {i}/{len(records)}")
    if cache_path and fresh:
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump(cache, fh)
    if unreadable:
        print(f"  !! {len(unreadable)} file(s) could not be hashed and were NOT checked for "
              f"duplicates:")
        for fn, err in unreadable[:10]:
            print(f"     {fn}: {err}")

    # Union-find over group keys.
    parent: dict[str, str] = {}

    def find(g: str) -> str:
        parent.setdefault(g, g)
        while parent[g] != g:
            parent[g] = parent[parent[g]]
            g = parent[g]
        return g

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    dup_sets = 0
    conflicts: list[tuple[str, list[str]]] = []
    for h, rs in by_hash.items():
        gs = {r["group"] for r in rs}
        labels = {r["label"] for r in rs}
        if len(labels) > 1:
            # One payload carrying two class labels is a mislabel, not a
            # grouping mistake, and merging the groups would bury it inside a
            # single recording that claims to be two classes at once. Report it
            # and leave the groups alone so the contradiction stays visible.
            conflicts.append((h[:12], sorted(r["file"] + ":" + r["label"] for r in rs)))
            continue
        if len(gs) > 1:
            dup_sets += 1
            it = iter(sorted(gs))
            first = next(it)
            for g in it:
                union(first, g)

    if conflicts:
        print(f"  !! {len(conflicts)} payload(s) carry CONTRADICTORY labels - these are "
              f"mislabelled, not misgrouped, and were left unmerged:")
        for h, files in conflicts[:10]:
            print(f"     {h}  {files}")

    if not dup_sets:
        print(f"  no cross-group duplicate payloads ({fresh} newly hashed)")
        return
    merged = 0
    for r in records:
        root = find(r["group"])
        if root != r["group"]:
            r["group"] = root
            merged += 1
    print(f"  {dup_sets} payload(s) held under more than one group key; "
          f"{merged} record(s) re-keyed so duplicates move as one recording")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", default=CACHE)
    ap.add_argument("--window", type=int, default=10, help="window length in seconds (default 10)")
    ap.add_argument("--audioset", action="store_true", help="also index AudioSet/VGGSound segments")
    ap.add_argument("--out", default=os.path.join("ml", "acoustic", "harness", "index.json"))
    ap.add_argument("--no-hash-merge", action="store_true",
                    help="skip content-hash duplicate merging (faster; leaves name-invisible duplicates split)")
    ap.add_argument("--hash-cache", default=os.path.join("ml", "acoustic", "harness", "payload_hashes.json"))
    ap.add_argument("--exclude-source", action="append", default=[], metavar="SOURCE",
                    help="drop a source from the index entirely. Used to hold a test set fixed "
                         "while a new corpus is added train-only, so an accuracy change has one "
                         "cause; repeatable.")
    ap.add_argument("--include-source", action="append", default=[], metavar="SOURCE",
                    help=f"re-admit a source excluded by default {DEFAULT_EXCLUDED_SOURCES}; "
                         f"repeatable. Only for deliberate experiments.")
    args = ap.parse_args()

    global INCLUDE_AUDIOSET
    INCLUDE_AUDIOSET = args.audioset

    if not os.path.isdir(args.cache):
        print(f"cache not found: {args.cache}", file=sys.stderr)
        return 1

    records, skipped = build(args.cache, args.window)
    drop = (set(DEFAULT_EXCLUDED_SOURCES) | set(args.exclude_source)) - set(args.include_source)
    if drop:
        before = len(records)
        records = [r for r in records if r["source"] not in drop]
        if before - len(records):
            print(f"excluded {before - len(records)} file(s) from source(s) {sorted(drop)}")
    if not records:
        print("no records built - check --cache and --window", file=sys.stderr)
        return 1

    if not args.no_hash_merge:
        merge_identical_payloads(records, args.hash_cache)

    by_label = Counter(r["label"] for r in records)
    groups = defaultdict(set)
    for r in records:
        groups[r["label"]].add(r["group"])
    src = Counter((r["label"], r["source"]) for r in records)

    print(f"window {args.window}s - {len(records)} files, {len({r['group'] for r in records})} recordings\n")
    print(f"{'class':<16}{'files':>8}{'recordings':>13}{'files/rec':>11}")
    for label in CLASSES:
        n, g = by_label[label], len(groups[label])
        print(f"{label:<16}{n:>8}{g:>13}{(n / g if g else 0):>11.2f}")

    print("\nper-source recording counts")
    for (label, source), _ in sorted(src.items()):
        recs = len({r["group"] for r in records if r["label"] == label and r["source"] == source})
        print(f"  {label:<16}{source:<20}{recs:>6}")

    # The collapse from files to recordings is exactly the leakage the
    # file-level split was exposed to.
    print("\nfile->recording collapse (leakage exposure if split at file level):")
    for label in CLASSES:
        n, g = by_label[label], len(groups[label])
        if n > g:
            print(f"  {label:<16}{n} files -> {g} recordings ({n - g} redundant copies)")

    if skipped:
        print("\nskipped:", dict(skipped))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"window_s": args.window, "classes": list(CLASSES), "records": records}, fh, indent=1)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
