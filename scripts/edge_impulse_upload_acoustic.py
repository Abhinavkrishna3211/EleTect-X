"""Upload five real, licensed public audio sources to Edge Impulse as acoustic training data.

Builds the EleTect-X-Acoustic project's dataset (gunshot / chainsaw / vehicle / animal_call /
ambient - the five AcousticClass labels device/mpu/bridge/rpc.py already defines) from four
distinct public sources:

  - "gunshot" + "ambient": Mendeley Data x48cwz364j v3, "Tropical forest gunshot classification
    training audio dataset" (Katsis et al. 2022, DOI 10.17632/x48cwz364j.3), CC BY 4.0 - verified
    against the dataset's own public-api record, not assumed from Mendeley's common default.
    Real AudioMoth recordings from tropical forest sites in Belize. The dataset's "Training data"
    and "Validation data" folders are temporally distinct (the description's own words), so their
    split is used as-is rather than reshuffled: v3's public-api file listing shows two gunshot
    folders of 597 and 150 files (79.9% / 20.1% - matches the description's stated 80/20 split by
    count, since the API exposes no folder-name field to confirm which id is which folder by
    name). All 747 available gunshot clips are used, uncapped - it is real, rare positive-class
    transient data and there is no reason to discard it for a tidier class balance. The
    description claims 749 gunshot files; 747 are what v3's listing actually holds. That 2-file
    gap is logged, not hidden.

    For "ambient": the same v3 listing holds one 7,040-file loose background folder and one
    1.3 GB background.zip. 7,040 is ~20% of the description's "over 35,000 background files"
    claim, and the zip is far too large (implying ~28,000 more files) to be the 20% side - so the
    zip is skipped entirely and never downloaded. This means our ambient source is only the
    authors' one background folder, not both, and this script draws its own seeded train/test
    split from inside that single folder (chronologically, by the UNIX-hex timestamp in each
    filename) rather than getting a second, independently-collected background folder to test
    against. Caveat this in the README: unlike gunshot, ambient's train and test clips are not
    temporally distinct in the way the source dataset's own two folders are.

  - "chainsaw": ESC-50 (Piczak 2015, DOI 10.1145/2733373.2806390), filtered to
    meta/esc50.csv rows where category == "chainsaw" and esc10 == True - the CC BY-licensed
    ESC-10 subset. Verified: all 40 chainsaw clips in ESC-50 already carry esc10=True, 8 per
    fold. The non-ESC-10 portion of ESC-50 is CC BY-NC and is never touched. Split by the
    dataset's own fold column (1-4 training, 5 testing), which already keeps clips sharing a
    src_file inside one fold.

  - "vehicle" and "animal_call": UrbanSound8K and the two elephant-call sources originally
    proposed for this task were checked against their live pages/APIs and rejected before any
    data was pulled - see the REJECTED SOURCES note below. Both classes are instead pulled
    directly from Freesound.org's search API, filtered to license "Creative Commons 0" or
    "Attribution" only (CC BY-NC and all other Freesound licenses are excluded), and each
    clip's own id/uploader/license/url is recorded in the manifest - real per-clip provenance,
    not an inherited blanket license. Freesound relevance is uploader tagging, not expert
    verification: there is no guarantee every "elephant" hit is an actual elephant call rather
    than an unrelated recording that happens to be tagged or titled that way. Requires a
    Freesound API token (FREESOUND_API_KEY) - free, but a real account you create yourself at
    https://freesound.org/apiv2/apply/, verified here to be a hard requirement: unauthenticated
    search and the /download/ endpoint both return HTTP 401. Token auth reaches the public HQ
    preview (128 kbps MP3), not the original upload, which OAuth2 would be needed for - so
    vehicle/animal_call audio is transcoded from Freesound's lossy preview, not the source file.

REJECTED SOURCES - considered, checked against their live state, not used:
  - UrbanSound8K: its own CSV (slice_file_name, fsID, start, end, salience, fold, classID,
    class) carries no per-clip license field at all, and the dataset's Zenodo record (1203745)
    and README both declare the whole distribution CC BY-NC 4.0 - there is no CC0/CC BY subset
    inside it to filter to, so the per-clip filtering this task originally called for cannot be
    executed against real metadata.
  - Michael Pardo's elephant-rumble records: Zenodo 10576772 is one R script (LGPL) whose own
    description states "the sound files ... are not included in this archive"; Dryad
    doi:10.5061/dryad.hmgqnk9nj is derived CSV/RDS acoustic-feature tables with the same
    disclaimer. Neither contains a single audio file.
  - github.com/HiruDewmi/Audio-Classification-for-Elephant-Sounds: real curated Rumble/Roar/
    Trumpet WAVs exist in its data/ tree, but the repository has no LICENSE file and its README
    states no terms and no original-recording attribution - GitHub's own API reports
    license: null. Used as evidence Freesound would have permissive supply (it does), not as a
    data source.

Sample-rate and clip-length normalization, applied uniformly regardless of source:
  - Mono, resampled to 8000 Hz (matches Mendeley's native rate, the lowest of the four; the other
    three sources are all downsampled, none upsampled). scipy.signal.resample_poly is used rather
    than stdlib audioop.ratecv specifically because ratecv has no real anti-alias filter -
    decimating ESC-50/Freesound's 44.1 kHz at ~5.5:1 without one folds high-frequency energy back
    into the low mel bands the DSP block actually reads, which would corrupt every non-Mendeley
    class's frequency content, not just add noise.
  - Every clip is centre-cropped or zero-padded to exactly 4.0 seconds. 4.0 s is chosen because
    it sits just under Mendeley's native 4.09 s clip length, so gunshot - whose transient position
    inside its clip is not annotated anywhere in the dataset - is never cropped and can never have
    its transient cut off; every other, shorter or longer, source is trimmed or padded to meet
    that length instead.
  - This does not capture elephant rumble fundamentals (8-34 Hz): 8 kHz sampling is not the
    binding constraint there (well above Nyquist), an MFE/MFCC block's lowest mel band is. See
    ml/acoustic/README.md's caveats - this script does not claim infrasound detection.

Dependency deviation from scripts/edge_impulse_upload_seismic.py's "stdlib only" discipline,
stated plainly rather than silently added: this file needs numpy + scipy (already installed on
this machine; scripts/geophone_excitation_stimulus.py is existing precedent for numpy under
scripts/) for anti-aliased resampling, and soundfile (one extra `pip install soundfile`, no
ffmpeg needed - it bundles libsndfile >=1.2, which decodes both WAV and MP3) because Freesound's
previews are MP3 and this machine has no ffmpeg. requests is used throughout in place of
urllib, for the same reason: Freesound and Mendeley's APIs are easier to drive correctly with it
and every sibling upload script under scripts/ (seismic excepted) already treats it as available.

Downloaded audio is cached under ml/datasets/acoustic/raw/, which .gitignore already excludes
(ml/datasets/**/raw/). The exact clip selection - one entry per uploaded clip, its source,
license, split, and the sha256 of its normalized payload - is committed as
ml/acoustic/dataset_manifest.json, so the dataset behind any reported accuracy is reproducible
from a fresh clone even though the raw audio itself is not, and even though a live Freesound
search could return different results on a later run.

Usage (run from a machine with normal internet access, not a sandboxed one):

    set EI_API_KEY=ei_...
    set EI_PROJECT_ID=1094275
    set FREESOUND_API_KEY=...
    python scripts\\edge_impulse_upload_acoustic.py

    python scripts\\edge_impulse_upload_acoustic.py --dry-run --limit 10
"""

import argparse
import hashlib
import io
import json
import os
import random
import sys
import time
from fractions import Fraction

import numpy as np
import requests
import soundfile as sf
from scipy.signal import resample_poly

INGEST = "https://ingestion.edgeimpulse.com/api"
MENDELEY_API = "https://data.mendeley.com/public-api/datasets/x48cwz364j"
ESC50_RAW = "https://raw.githubusercontent.com/karolpiczak/ESC-50/master"
FREESOUND_API = "https://freesound.org/apiv2"

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
CACHE_DIR = os.path.join(_ROOT, "ml", "datasets", "acoustic", "raw")
MANIFEST = os.path.join(_ROOT, "ml", "acoustic", "dataset_manifest.json")

# Fixed so ambient's in-folder split and every Freesound selection are reproducible; recorded in
# the manifest and the README, same discipline as scripts/edge_impulse_upload_vision.py.
SPLIT_SEED = 20260823
TEST_FRACTION = 0.20

SAMPLE_RATE_HZ = 8000
CLIP_SECONDS = 4.0
CLIP_SAMPLES = int(SAMPLE_RATE_HZ * CLIP_SECONDS)

# Real, rare, transient positive-class data - use all of it, never subsampled.
GUNSHOT_TRAIN_FOLDER = "d21ad8ca-ca07-4a75-a852-29c2a505e62b"  # 597 files, ~80% by count
GUNSHOT_TEST_FOLDER = "83dd9428-6b72-4db7-90e8-70f84be9fa7d"  # 150 files, ~20% by count
GUNSHOT_DESCRIBED_TOTAL = 749  # what the dataset's own description claims

# The one background folder actually usable without a 1.3GB zip download (see module docstring).
AMBIENT_FOLDER = "86d76b5d-a89c-41c7-9bab-76b0c9de9e63"  # 7,040 loose files
AMBIENT_CAP = 150  # subsampled down from 7,040 - see module docstring for why this one is capped

FREESOUND_CAP = 150
FREESOUND_MIN_DURATION_S = 1.0
FREESOUND_MAX_DURATION_S = 30.0
# Freesound's own license facet strings, exactly as the API returns/accepts them.
FREESOUND_LICENSES = ("Creative Commons 0", "Attribution")

# Edge Impulse's files endpoint accepts up to 1000 files/100MB each per request; well under
# either limit while keeping the request count reasonable.
BATCH_SIZE = 50
MAX_RETRIES = 4


def _get(url, **kwargs):
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=120, **kwargs)
            if resp.status_code == 403 and resp.headers.get("Cf-Mitigated") == "challenge":
                # Verified against the live API: data.mendeley.com sits behind Cloudflare, and its
                # public-api host occasionally answers plain HTTP clients (both `requests` and, less
                # often, `curl`) with a JS bot-challenge rather than a JSON body - no request header
                # fixes this, since it isn't a header check. Backing off and retrying sometimes clears
                # it (observed inconsistently: same script, same machine, different outcomes minutes
                # apart) - if every retry here still fails, open the dataset page in a real browser
                # once (https://data.mendeley.com/datasets/x48cwz364j/3) and try again shortly after;
                # that has been enough to clear it in practice.
                print(f"    Cloudflare bot-challenge on {url} - this is not a normal HTTP error")
            resp.raise_for_status()
            return resp
        except requests.RequestException as err:
            if attempt == MAX_RETRIES - 1:
                raise
            wait = 5 * 2**attempt
            print(f"    {err} - retrying in {wait}s")
            time.sleep(wait)


def normalize_clip(raw_bytes):
    """Decode arbitrary WAV/MP3 bytes into an 8kHz mono 16-bit PCM WAV, fixed to CLIP_SAMPLES.

    Anti-aliased resampling via scipy.signal.resample_poly (see module docstring for why
    audioop.ratecv is not used), then centre-crop or zero-pad to exactly CLIP_SAMPLES so every
    class shares one clip length regardless of its source's native duration.
    """
    data, orig_rate = sf.read(io.BytesIO(raw_bytes), dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)

    if orig_rate != SAMPLE_RATE_HZ:
        frac = Fraction(SAMPLE_RATE_HZ, orig_rate).limit_denominator(1000)
        data = resample_poly(data, frac.numerator, frac.denominator).astype(np.float32)

    if len(data) >= CLIP_SAMPLES:
        start = (len(data) - CLIP_SAMPLES) // 2
        data = data[start : start + CLIP_SAMPLES]
    else:
        pad = CLIP_SAMPLES - len(data)
        data = np.pad(data, (pad // 2, pad - pad // 2))

    data = np.clip(data, -1.0, 1.0)
    out = io.BytesIO()
    sf.write(out, data, SAMPLE_RATE_HZ, subtype="PCM_16", format="WAV")
    return out.getvalue()


def fetch_mendeley_gunshot_ambient():
    """Pull gunshot (all 747, authors' own train/test folders) and a seeded ambient subsample."""
    print("Fetching Mendeley x48cwz364j v3 file listing...")
    doc = _get(MENDELEY_API).json()
    files_by_folder = {}
    for f in doc["files"]:
        files_by_folder.setdefault(f["folder_id"], []).append(f)

    gunshot_train = files_by_folder.get(GUNSHOT_TRAIN_FOLDER, [])
    gunshot_test = files_by_folder.get(GUNSHOT_TEST_FOLDER, [])
    gunshot_total = len(gunshot_train) + len(gunshot_test)
    print(f"  gunshot: {len(gunshot_train)} train + {len(gunshot_test)} test = {gunshot_total}")
    if gunshot_total != GUNSHOT_DESCRIBED_TOTAL:
        print(
            f"    NOTE: dataset description claims {GUNSHOT_DESCRIBED_TOTAL} gunshot files; "
            f"v3's public-api listing actually holds {gunshot_total}. Using what is really "
            f"there ({gunshot_total}), not the described figure."
        )

    ambient_pool = sorted(files_by_folder.get(AMBIENT_FOLDER, []), key=lambda f: f["filename"])
    print(f"  ambient: {len(ambient_pool)} files available in the one usable background folder")
    rng = random.Random(SPLIT_SEED)
    selected = ambient_pool if len(ambient_pool) <= AMBIENT_CAP else rng.sample(ambient_pool, AMBIENT_CAP)
    selected.sort(key=lambda f: f["filename"])  # chronological: hex-timestamp filenames sort in time order
    n_test = max(1, round(len(selected) * TEST_FRACTION))
    ambient_train, ambient_test = selected[:-n_test], selected[-n_test:]
    print(
        f"    subsampled {len(selected)}/{len(ambient_pool)} (seed {SPLIT_SEED}), "
        f"chronological split: {len(ambient_train)} train / {len(ambient_test)} test"
    )

    def to_records(entries, label, category):
        records = []
        for f in entries:
            records.append(
                {
                    "label": label,
                    "category": category,
                    "name": f["filename"],
                    "url": f["content_details"]["download_url"],
                    "source_id": f["id"],
                    "license": "CC BY 4.0",
                    "dataset": "Mendeley x48cwz364j v3 (Katsis et al. 2022)",
                }
            )
        return records

    return (
        to_records(gunshot_train, "gunshot", "training")
        + to_records(gunshot_test, "gunshot", "testing")
        + to_records(ambient_train, "ambient", "training")
        + to_records(ambient_test, "ambient", "testing")
    )


def fetch_esc50_chainsaw():
    """Pull the 40 ESC-10 chainsaw clips, split by the dataset's own fold column."""
    print("Fetching ESC-50 meta/esc50.csv...")
    import csv

    text = _get(f"{ESC50_RAW}/meta/esc50.csv").text
    rows = list(csv.DictReader(io.StringIO(text)))
    chainsaw = [r for r in rows if r["category"] == "chainsaw" and r["esc10"] == "True"]
    print(f"  chainsaw (esc10 subset, CC BY): {len(chainsaw)} clips across folds "
          f"{sorted({r['fold'] for r in chainsaw})}")
    if len(chainsaw) != 40:
        print(f"    NOTE: expected 40 ESC-10 chainsaw clips, found {len(chainsaw)}")

    records = []
    for r in chainsaw:
        category = "testing" if r["fold"] == "5" else "training"
        records.append(
            {
                "label": "chainsaw",
                "category": category,
                "name": r["filename"],
                "url": f"{ESC50_RAW}/audio/{r['filename']}",
                "source_id": r["filename"],
                "license": "CC BY (ESC-10 subset)",
                "dataset": "ESC-50 (Piczak 2015)",
                "fold": r["fold"],
            }
        )
    return records


def freesound_search(query, api_key, cap):
    """Search Freesound, filtered to CC0/CC BY only, and return up to `cap` seeded-random hits."""
    license_filter = " OR ".join(f'license:"{lic}"' for lic in FREESOUND_LICENSES)
    duration_filter = f"duration:[{FREESOUND_MIN_DURATION_S} TO {FREESOUND_MAX_DURATION_S}]"
    params = {
        "query": query,
        "filter": f"({license_filter}) {duration_filter}",
        "fields": "id,name,license,username,url,previews,duration,tags",
        "page_size": 150,
        "token": api_key,
    }
    hits = []
    url = f"{FREESOUND_API}/search/text/"
    while url and len(hits) < 500:  # 500 is a supply ceiling, not the selection cap
        resp = _get(url, params=params if url == f"{FREESOUND_API}/search/text/" else None).json()
        hits.extend(resp.get("results", []))
        url = resp.get("next")
        params = None  # "next" is already a fully-formed URL
    excluded_no_preview = [h for h in hits if not (h.get("previews") or {}).get("preview-hq-mp3")]
    hits = [h for h in hits if h not in excluded_no_preview]
    print(
        f"  Freesound '{query}': {len(hits)} CC0/CC BY hits with a downloadable preview "
        f"({len(excluded_no_preview)} excluded, no HQ preview available)"
    )
    rng = random.Random(SPLIT_SEED)
    selected = hits if len(hits) <= cap else rng.sample(hits, cap)
    rng.shuffle(selected)
    n_test = max(1, round(len(selected) * TEST_FRACTION))
    train, test = selected[n_test:], selected[:n_test]
    return train, test, len(hits)


def fetch_freesound_class(label, query, api_key):
    train, test, available = freesound_search(query, api_key, FREESOUND_CAP)
    print(f"    selected {len(train) + len(test)}/{available}: {len(train)} train / {len(test)} test")
    records = []
    for category, entries in (("training", train), ("testing", test)):
        for h in entries:
            records.append(
                {
                    "label": label,
                    "category": category,
                    "name": f"{h['id']}_{h['name']}",
                    "url": h["previews"]["preview-hq-mp3"],
                    "source_id": h["id"],
                    "license": h["license"],
                    "dataset": f"Freesound.org (query {query!r})",
                    "uploader": h.get("username"),
                    "freesound_url": h.get("url"),
                }
            )
    return records


def download_and_normalize(records):
    """Download each record's raw audio, normalize it, and attach the normalized bytes + sha256."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    for i, rec in enumerate(records, 1):
        cache_path = os.path.join(CACHE_DIR, f"{rec['label']}_{rec['source_id']}.norm.wav")
        if os.path.exists(cache_path):
            with open(cache_path, "rb") as fh:
                norm = fh.read()
        else:
            raw = _get(rec["url"]).content
            norm = normalize_clip(raw)
            with open(cache_path, "wb") as fh:
                fh.write(norm)
        rec["normalized_bytes"] = norm
        rec["sha256"] = hashlib.sha256(norm).hexdigest()
        if i % 100 == 0 or i == len(records):
            print(f"  normalized {i}/{len(records)}")
    return records


def _ledger_path():
    return os.path.join(CACHE_DIR, "uploaded.json")


def upload_batch(api_key, label, category, batch):
    boundary = f"----EleTectX{random.getrandbits(64):016x}"
    body = bytearray()
    for rec in batch:
        body += f"--{boundary}\r\n".encode()
        body += (
            f'Content-Disposition: form-data; name="data"; filename="{rec["name"]}.wav"\r\n'
        ).encode()
        body += b"Content-Type: audio/wav\r\n\r\n"
        body += rec["normalized_bytes"] + b"\r\n"
    body += f"--{boundary}--\r\n".encode()

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(
                f"{INGEST}/{category}/files",
                data=bytes(body),
                headers={
                    "x-api-key": api_key,
                    "x-label": label,
                    "x-disallow-duplicates": "1",
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                },
                timeout=600,
            )
            resp.raise_for_status()
            return None
        except requests.HTTPError as err:
            detail = err.response.text[:300] if err.response is not None else str(err)
            code = err.response.status_code if err.response is not None else 0
            if code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                wait = 5 * 2**attempt
                print(f"    HTTP {code}, retrying in {wait}s")
                time.sleep(wait)
                continue
            return code, detail
        except requests.RequestException as err:
            if attempt < MAX_RETRIES - 1:
                wait = 5 * 2**attempt
                print(f"    {err}, retrying in {wait}s")
                time.sleep(wait)
                continue
            return 0, str(err)
    return 0, "exhausted retries"


def upload_all(api_key, records):
    done = set()
    ledger = _ledger_path()
    if os.path.exists(ledger):
        with open(ledger) as fh:
            done = set(json.load(fh))
    pending = [r for r in records if r["name"] not in done]
    if done:
        print(f"resuming: {len(done)} already uploaded, {len(pending)} remaining")

    ok, failed = 0, []
    by_group = {}
    for r in pending:
        by_group.setdefault((r["label"], r["category"]), []).append(r)

    for (label, category), group in sorted(by_group.items()):
        for i in range(0, len(group), BATCH_SIZE):
            batch = group[i : i + BATCH_SIZE]
            err = upload_batch(api_key, label, category, batch)
            if err:
                failed.append((label, category, batch[0]["name"], err[0], err[1]))
                print(f"  [{category}] {label:12s} batch of {len(batch):3d} -> FAILED {err[0]}")
                continue
            ok += len(batch)
            done.update(r["name"] for r in batch)
            with open(ledger, "w") as fh:
                json.dump(sorted(done), fh)
            print(f"  [{category}] {label:12s} batch of {len(batch):3d} -> uploaded ({ok} so far)")
    return ok, failed


def write_manifest(records):
    by_class = {}
    for r in records:
        cls = by_class.setdefault(
            r["label"],
            {"dataset": r["dataset"], "license": r["license"], "training": [], "testing": []},
        )
        entry = {
            k: r[k]
            for k in ("name", "source_id", "license", "sha256", "url")
            if k in r
        }
        for extra in ("uploader", "freesound_url", "fold"):
            if extra in r:
                entry[extra] = r[extra]
        cls[r["category"]].append(entry)

    doc = {
        "schema": "eletect-x/acoustic-clip-manifest/1",
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "clip_seconds": CLIP_SECONDS,
        "split_seed": SPLIT_SEED,
        "test_fraction": TEST_FRACTION,
        "classes": by_class,
    }
    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
    with open(MANIFEST, "w") as fh:
        json.dump(doc, fh, indent=1)
        fh.write("\n")
    print(f"\nWrote manifest -> {MANIFEST}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="do everything except upload")
    ap.add_argument("--limit", type=int, help="use only the first N clips per class (debugging)")
    args = ap.parse_args()

    api_key = os.environ.get("EI_API_KEY")
    project_id = os.environ.get("EI_PROJECT_ID")
    fs_key = os.environ.get("FREESOUND_API_KEY")
    if not api_key or not project_id or not fs_key:
        print(
            "Set EI_API_KEY, EI_PROJECT_ID and FREESOUND_API_KEY environment variables first.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("=== gunshot + ambient (Mendeley x48cwz364j v3, CC BY 4.0) ===")
    records = fetch_mendeley_gunshot_ambient()

    print("\n=== chainsaw (ESC-50 ESC-10 subset, CC BY) ===")
    records += fetch_esc50_chainsaw()

    print("\n=== vehicle (Freesound, CC0/CC BY only) ===")
    records += fetch_freesound_class("vehicle", "engine idling", fs_key)

    print("\n=== animal_call (Freesound, CC0/CC BY only) ===")
    records += fetch_freesound_class("animal_call", "elephant", fs_key)

    if args.limit:
        by_label = {}
        for r in records:
            by_label.setdefault(r["label"], []).append(r)
        records = [r for group in by_label.values() for r in group[: args.limit]]
        print(f"\n--limit {args.limit}: truncated to {len(records)} clips total")

    print(f"\nDownloading and normalizing {len(records)} clips to {SAMPLE_RATE_HZ}Hz/"
          f"{CLIP_SECONDS}s mono WAV...")
    records = download_and_normalize(records)

    write_manifest(records)

    print("\nReconciliation (label -> train/test/total):")
    by_label = {}
    for r in records:
        by_label.setdefault(r["label"], {"training": 0, "testing": 0})[r["category"]] += 1
    for label, counts in sorted(by_label.items()):
        total = counts["training"] + counts["testing"]
        print(f"  {label:12s} train={counts['training']:4d} test={counts['testing']:4d} total={total:4d}")

    if args.dry_run:
        print("\n--dry-run: not uploading")
        return

    ok, failed = upload_all(api_key, records)
    print(f"\n{ok}/{len(records)} uploaded successfully.")
    if failed:
        print("Failures:")
        for f in failed:
            print(" ", f)
        sys.exit(1)
    print(f"\nCheck the result at https://studio.edgeimpulse.com/studio/{project_id}/acquisition/training")


if __name__ == "__main__":
    main()
