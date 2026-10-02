"""Upload real public audio to Edge Impulse as acoustic training data (four-class scheme).

Builds the EleTect-X-Acoustic project's dataset for:

    gunshot  chainsaw  elephant_call  ambient

DROPPED FROM THE WIRE SCHEME - boar_call, predator_call: the original ADR 0024 amendment
scoped a seven-class scheme including these two. Both were sourced, uploaded and trained
through the full exploration (DSP A/B, EON Tuner, transfer learning, and a five-point
{3,4,6,8,10}s window-length sweep) and never rose meaningfully above the 14.3% (1/7)
chance floor in any configuration - predator_call held-out recall was 10.7%/0%/0%/0%/0%
and boar_call 2.6%/0%/untrained/0%/5.3% across the five window candidates. Per the project
owner's decision, both are dropped from the wire scheme entirely (not folded into
`ambient`, which means background/silence, not a mislabeled animal call). The device-side
`AcousticClass` enum change this implies is a separate, deferred Track B edit - this
script and edge_impulse_train_acoustic.py are the only files touched to apply the drop.
Their fetchers, queries and floor-handling special-cases have been removed rather than
left as dead code.

DROPPED FROM THE WIRE SCHEME (2026-09-14) - vehicle: added 2026-09-13 as one of the
original five classes, then dropped one day later once real field data made a pre-existing
weakness undeniable. `chainsaw`'s and `vehicle`'s Freesound-sourced audio - both sustained
mechanical/engine drones - already sat suspiciously close together in MFE feature space
(see ml/acoustic/README.md's "Reading these numbers honestly", written the day before this
drop). Adding 15 real chainsaw + 14 real vehicle clips (project owner's own laptop-mic +
phone-speaker recordings, ml/datasets/acoustic/manual_sources/laptop_phone_2026-09/) pushed
that latent collision into an outright collapse: chainsaw held-out recall fell to 0/79
(0.0%), and the *training-validation* confusion matrix (not just the held-out test) showed
33 of 60 chainsaw validation clips predicted vehicle - proof this was a real class-boundary
problem, not test-split noise. Retraining with vehicle removed recovered chainsaw to 44/79
(55.7%), by far its best score to date - see the Result section in ml/acoustic/README.md
for the full before/after. Given the field-build deadline,
vehicle is dropped rather than further investigated - not folded into `ambient` for the
same reason boar_call/predator_call were not: `ambient` means background/silence, not a
mislabeled vehicle. Its fetchers, queries and floor-handling special-cases are removed
below rather than left as dead code; the raw audio stays cached under
ml/datasets/acoustic/raw/ and the EI project's own vehicle samples were deleted from
1109511 via the Studio API so the trained impulse only ever sees four classes. Revisit
with better-differentiated vehicle sourcing (e.g. real idle/engine field recordings rather
than generic Freesound engine queries) after the field deployment milestone.

Routing context (see docs/decisions/0024-acoustic-species-classification-deferred.md's
amendment): `elephant_call` is the only remaining class that feeds the deterrence (bandit)
fusion; `gunshot` / `elephant_call` / `chainsaw` raise ranger alerts; `ambient` is
detection-only. `vehicle`'s alert-only routing is moot until the class is revived - see
the drop note above. This script only sources and uploads audio - it does not touch any of
that routing.

EXTENSIBILITY - each class is its own distinct label, deliberately NOT rolled into a
generic "other animal" bucket. The project scope includes detecting and logging further
species purely for research: to add one, append its name to CLASS_SCHEME and give it a
FREESOUND_QUERIES entry (and/or a dedicated fetcher). It then flows through download,
normalize, manifest and upload with no other change, and the device can log it as a
first-class detection. New species that never clear CLIP_FLOOR are still uploaded and
trained (their honest held-out numbers go in ml/acoustic/README.md) - the floor only
gates elephant_call's merge-readiness and prunes a species that cannot be sourced at all.

SOURCES, per class - each clip's own per-clip provenance (id / uploader / license / url)
is recorded in dataset_manifest.json, not a blanket license inherited from a dataset:

  - "gunshot" + "ambient": Mendeley Data x48cwz364j v3, "Tropical forest gunshot
    classification training audio dataset" (Katsis et al. 2022, DOI 10.17632/x48cwz364j.3),
    CC BY 4.0 - verified against the dataset's own public-api record. Real AudioMoth
    recordings from tropical forest sites in Belize. The dataset's "Training data" and
    "Validation data" gunshot folders are temporally distinct, so their split is used
    as-is. The 150-file authored test folder is kept whole (a full, comparable held-out
    set); the 597-file train folder is seed-subsampled to GUNSHOT_TRAIN_CAP (~200) so the
    easiest, largest class does not dominate the training gradient - it is roughly matched
    to elephant_call's train count. Because every Mendeley
    gunshot AND every Mendeley ambient clip
    comes from the same forest AudioMoth rig, a model trained on Mendeley alone cannot tell
    a gunshot from its background - it leans on the recording signature, then collapses
    gunshot into ambient on anything else. So gunshot is SUPPLEMENTED with a Freesound
    multi-query pull ("gunshot", "gunfire", "rifle shot", "shotgun blast", ...) that brings
    in unrelated rigs and forces the model onto the transient itself. "ambient" draws a
    seeded subsample (AMBIENT_CAP, now 200) from
    the one loose background folder (background.zip, ~1.3 GB, is never downloaded - the
    API listing caps at ~1000 records anyway), then SUPPLEMENTS it with ESC-50's nature
    categories (crickets, insects, chirping_birds, wind, frog, rain - full 40-clip sets,
    CC BY-NC, recorded per clip). All Mendeley ambient is one Belize AudioMoth deployment;
    the ESC-50 nature clips add genuinely different recording conditions so the negative
    class covers the birdsong / insect / rain / wind a naive detector false-alarms on.
    A large, varied ambient class is the main defence against field false positives.

  - "chainsaw": ESC-50 (Piczak 2015, DOI 10.1145/2733373.2806390) ESC-10 subset
    (category == "chainsaw" and esc10 == True - all 40 clips, CC BY), split by the
    dataset's own fold column (1-4 train, 5 test), SUPPLEMENTED with an 8-query Freesound
    pull ("chainsaw", "chainsaw cutting wood", "chainsaw idle", "chainsaw revving", "gas
    chainsaw", "power saw", "chainsaw forest", "logging chainsaw") - widened from the
    original 2-query pull specifically to improve held-out recall/diversity, not to clear
    the floor (chainsaw was never floor-gated).

  - "elephant_call": (1) HiruDewmi/Audio-Classification-for-Elephant-Sounds curated
    Rumble/Roar/Trumpet WAVs (GitHub, license:null - see LICENSING below), (2) Freesound
    12-query pull ("elephant rumble", "elephant trumpet", "elephant call", "elephant roar",
    "elephant bellow", "elephant vocalization", "elephant growl", "elephant scream", "wild
    elephant sound", "elephant herd", "baby elephant", "elephant infrasound") - widened
    2026-09-14 from the original 3-query pull to source more real data after the
    post-vehicle-drop retrain showed elephant_call as the model's weakest class, (3)
    xeno-canto "Elephas maximus" if that taxon is present. Whatever really arrives is what
    trains; the count is reported honestly.

    REJECTED - Cornell ELP "Congo Soundscapes" S3 (congo8khz-pnnn): the bucket's objects
    are 24-hour continuous recordings (~1.4 GB each at 8 kHz), not clips. Without the ELP
    Raven annotation tables (access-gated) there is no way to locate the actual elephant
    calls in them, so a centre-crop is almost always ambient forest, not elephant - a
    weak label so weak it is noise. It is also African forest elephant (Loxodonta
    cyclotis), not Asian. Dropped: it would degrade the class, not strengthen it.

  - DROPPED (see the module docstring's lede): "boar_call" (Freesound wild-pig query set
    + ESC-50 "pig") and "predator_call" (lion+leopard+tiger lumped; Freesound big-cat
    query set + xeno-canto "Panthera" + BBC Sound Effects). Both were sourced and trained
    through the full exploration and never cleared the 14.3% chance floor - removed from
    CLASS_SCHEME, FLOOR_TARGETS, and every fetcher/query table below rather than kept as
    dead code.

  - DROPPED (2026-09-14, see the module docstring's second drop note): "vehicle" (a
    10-query Freesound pull - "engine idling", "motorcycle passing", "truck engine",
    "engine revving", "car engine start", "diesel engine", "jeep engine", "tractor
    engine", "off-road vehicle", "car passing by" - SUPPLEMENTED with ESC-50's full
    "engine" category, 40 clips, CC BY-NC). Real field data exposed a pre-existing
    chainsaw/vehicle acoustic collision; removed from CLASS_SCHEME and every
    fetcher/query table below rather than kept as dead code.

  - XIAO manual captures (project-owned, local - fetch_xiao_manual_sources, skip with
    --no-xiao): datasets the owner recorded for this build, checked into
    ml/datasets/acoustic/manual_sources/. 16 kHz mono, 10 s/clip, XIAO ESP32S3 Sense
    onboard PDM MEMS mic. Contributes to gunshot / chainsaw (dir 1, ~30 clips each) and
    elephant_call / ambient (dir 1 "bg" + dir 2 "Elephant"/"Noice", an EI ingestion-JSON
    export with an authored train/test split); dir 1 also has vehicle-prefixed files that
    are no longer collected now that vehicle is dropped (see above). This is the only
    real-MEMS source and the closest to the deployment recording domain, so it adds the
    recording-condition diversity that stops the model keying on one rig's signature -
    the same reason gunshot is supplemented from Freesound. Two caveats, both in the
    README: (1) the XIAO PDM mic is NOT the deployment mic (INMP441 I2S) - a transfer
    gap; (2) every XIAO clip has a ~+0.16 DC offset, removed by normalize_clip (e2).

DATA FLOOR (classify_floor_and_prune): after every fetcher runs, elephant_call (the only
remaining FLOOR_TARGETS member) is checked against CLIP_FLOOR real clips. Below the floor
=> the per-species acoustic track is not merge-ready and the script says so in as many
words (it is still trained on what there is - there is no catch-all to fold into any
more). CLIP_TARGET is the "field-trustworthy" aspiration, not a gate. No class is ever
padded or fabricated to clear either line.

LICENSING: for this training experiment, audio is taken from the best available source
regardless of license, and each clip's license-as-found is recorded verbatim in the
manifest (including "unknown"/"none" for the GitHub elephant set). Production
license-clearing is a separate, later gate - it is not this script's job and not a
reason to skip a source here.

WINDOW LENGTH: the {3,4,6,8,10}s sweep's winner was 10.0s (priority_avg 50.9%, the best of
the four reliable candidates - 6.0s was an unreliable outlier and excluded). CLIP_SECONDS
is locked to 10.0 here and WINDOW_SIZE_MS/WINDOW_INCREASE_MS to 10000 in
scripts/edge_impulse_train_acoustic.py. --clip-seconds still overrides CLIP_SECONDS if a
future sweep is ever re-run.

Sample-rate / clip-length normalization, applied uniformly: mono, 8000 Hz (Mendeley's
native rate, the lowest source rate - every other source is downsampled, none upsampled),
anti-aliased via scipy.signal.resample_poly (stdlib audioop.ratecv has no anti-alias
filter and would fold HF energy into the low mel bands the DSP block reads). Every clip
is then fitted to exactly CLIP_SECONDS: a clip longer than the window is cropped to its
most energetic window (so a gunshot crack or chainsaw burst that sits off-centre is not
missed), and a shorter clip is looped to fill the window rather than zero-padded - the
DSP block's local normalization would otherwise amplify the padded silence into noise
and blur the event that defines the class. A final peak-normalization puts quiet
hobbyist uploads and loud studio SFX in the same amplitude range.

Dependencies (stated, not silent): numpy + scipy (anti-aliased resample) and soundfile
(Freesound previews are MP3; libsndfile decodes WAV+MP3, no ffmpeg needed). requests
throughout, as every sibling upload script under scripts/ (seismic excepted) already
assumes. No yt-dlp / ffmpeg anywhere in this script.

Downloaded audio caches under ml/datasets/acoustic/raw/ (.gitignore excludes
ml/datasets/**/raw/). dataset_manifest.json (committed) records the exact clip selection
- source, license, split, window length, floor status, sha256 of the normalized payload
- so the dataset behind any reported number is reproducible from a fresh clone.

Usage (run from a machine with normal internet access):

    set EI_API_KEY=ei_...
    set EI_PROJECT_ID=1110036
    set FREESOUND_API_KEY=...
    python scripts\\edge_impulse_upload_acoustic.py

    python scripts\\edge_impulse_upload_acoustic.py --dry-run
    python scripts\\edge_impulse_upload_acoustic.py --dry-run --clip-seconds 8.0
    python scripts\\edge_impulse_upload_acoustic.py --only elephant_call --dry-run
"""

import argparse
import hashlib
import io
import json
import os
import random
import re
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
GITHUB_API = "https://api.github.com"
XENOCANTO_API = "https://xeno-canto.org/api/2/recordings"

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
CACHE_DIR = os.path.join(_ROOT, "ml", "datasets", "acoustic", "raw")
MANIFEST = os.path.join(_ROOT, "ml", "acoustic", "dataset_manifest.json")

# Fixed so every seeded subsample / split is reproducible; recorded in the manifest.
SPLIT_SEED = 20260823
TEST_FRACTION = 0.20

SAMPLE_RATE_HZ = 8000
CLIP_SECONDS = 10.0  # window-sweep winner (priority_avg 50.9%); --clip-seconds overrides

# The four-class scheme. boar_call and predator_call were dropped after the full
# exploration (DSP A/B, EON Tuner, transfer learning, window sweep) never lifted either
# above the 14.3% chance floor; vehicle was dropped 2026-09-14 once real field data
# exposed a chainsaw/vehicle acoustic collision - see the module docstring's two drop
# notes. Appending a species here (plus a FREESOUND_QUERIES entry) is all it takes to
# detect and log another one for research; see the module docstring's EXTENSIBILITY note.
CLASS_SCHEME = (
    "gunshot",
    "chainsaw",
    "elephant_call",
    "ambient",
)
# Named per-species targets checked against the data floor.
FLOOR_TARGETS = ("elephant_call",)

CLIP_FLOOR = 150   # below this a named target is thin; see classify_floor_and_prune
CLIP_TARGET = 500  # "field-trustworthy" aspiration, reported against, never a gate

# Real, rare, transient positive-class data. The authors' 150-file test folder is kept
# whole - a full, comparable held-out set across the window sweep - but the 597-file
# train folder is seed-subsampled to GUNSHOT_TRAIN_CAP so gunshot does not dominate the
# training gradient and, more importantly, so the Freesound gunshot supplement (unrelated
# rigs - see FREESOUND_QUERIES["gunshot"]) is a real fraction of the class rather than a
# rounding error: ~200 Mendeley + ~100 Freesound (FREESOUND_CAP["gunshot"] = 130, less the
# test split) puts gunshot's TRAIN count level with elephant_call and keeps the Freesound
# fraction near a third - enough to break the single-rig monoculture that made the model
# read gunshot as ambient. Phase-2 measured 620 gunshot-train (uncapped Freesound) against
# ~158 boar-train and it collapsed boar/chainsaw to <5% recall; these caps are the fix.
GUNSHOT_TRAIN_FOLDER = "d21ad8ca-ca07-4a75-a852-29c2a505e62b"  # 597 files, ~80% by count
GUNSHOT_TEST_FOLDER = "83dd9428-6b72-4db7-90e8-70f84be9fa7d"  # 150 files, ~20% by count
GUNSHOT_DESCRIBED_TOTAL = 749  # what the dataset's own description claims
GUNSHOT_TRAIN_CAP = 200  # seeded subsample of the 597-file train folder; test folder untouched

AMBIENT_FOLDER = "86d76b5d-a89c-41c7-9bab-76b0c9de9e63"  # 7,040 loose files
AMBIENT_CAP = 200  # widened (150 -> 400 -> 700) then pulled back to 200 after Phase 2:
# at 700 Mendeley + ~240 ESC-50 + ~70 XIAO the ambient TRAIN split hit ~750, ~5x the
# thinnest classes, and with auto class weights off the model answered "ambient" for
# everything (boar/chainsaw held-out recall <5%). A big negative class is still the main
# defence against the first deployment's false-positive storm, but it has to stay within
# ~2x the trained species classes. The ESC-50 nature supplement below (genuinely different
# rigs - birdsong, insects, rain, wind, the exact sounds a naive detector fires on) is
# kept in full; the Mendeley single-rig share is what gets cut.
AMBIENT_ESC50_CATEGORIES = ("crickets", "insects", "chirping_birds", "wind", "frog", "rain")

FREESOUND_CAP_DEFAULT = 200  # per class (across all its sub-queries, after dedup)
FREESOUND_CAP = {"gunshot": 200, "chainsaw": 400, "ambient": 260}
FREESOUND_MIN_DURATION_S = 0.5
FREESOUND_MAX_DURATION_S = 30.0
# Every clip's own license is recorded per-clip; for this experiment nothing is excluded
# on license grounds (see the module docstring's LICENSING note).

# Per-class Freesound query sets. A single string still works; a list is searched
# per-query, concatenated, and de-duplicated on Freesound id before selection.
FREESOUND_QUERIES = {
    "gunshot": [
        "gunshot", "gun shot", "gunfire", "rifle shot", "rifle fire",
        "pistol shot", "shotgun blast", "shotgun fire", "gun shot outdoor",
        "single gunshot", "AK47 gunshot", "hunting rifle shot", "gun shot distant",
        "automatic gunfire", "poacher gunshot", "firearm discharge",
        "hunting shot forest", "field recording gunshot", "rifle report",
    ],
    "chainsaw": [
        "chainsaw", "chainsaw cutting wood", "chainsaw idle", "chainsaw revving",
        "gas chainsaw", "chainsaw forest", "logging chainsaw",
        "chainsaw distant", "chainsaw start", "electric chainsaw", "chainsaw cutting tree",
        "illegal logging chainsaw", "chainsaw motor running", "two stroke chainsaw",
        "chainsaw pull start", "chainsaw felling tree", "Stihl chainsaw",
        "Husqvarna chainsaw", "motosierra", "tronconneuse",
        # "power saw" DROPPED 2026-09-15 - a 2026-09-14 manual audit of all 136 clips it
        # pulled found the query matches synth "sawtooth waveform" content (the tool/
        # waveform ambiguity in "saw") and generic factory/impact SFX packs far more than
        # real chainsaws - see ml/acoustic/README.md's data-quality-audit caveat.
    ],
    "elephant_call": [
        "elephant rumble", "elephant trumpet", "elephant call", "elephant roar",
        "elephant bellow", "elephant vocalization", "elephant growl", "elephant scream",
        "wild elephant sound", "elephant herd", "baby elephant", "elephant infrasound",
        "asian elephant", "african elephant", "elephant sound effect", "elephant grumble",
        "elephant snort", "forest elephant",
    ],
    # NEW - "ambient" had no Freesound supplement at all before this widening; its
    # two sources (Mendeley single-rig background + ESC-50's isolated single-category
    # clips - crickets alone, birds alone) are both a poor match for what a field mic
    # actually hears (a mixed forest soundscape). This pulls in real recorded forest/
    # jungle background audio, the genuine negative-class domain, instead of more
    # single-species nature clips.
    "ambient": [
        "forest ambience", "jungle ambience", "rainforest ambience",
        "forest background noise", "tropical forest sounds", "jungle background",
        "nature ambience forest", "night forest ambience", "forest soundscape",
        "wind through trees forest", "rural background noise", "outdoor ambience quiet",
    ],
}

# xeno-canto is birds + a growing set of other taxa (grasshoppers, bats). elephant_call
# may simply not be present; the fetcher logs a zero yield rather than failing.
XENOCANTO_QUERIES = {
    "elephant_call": 'gen:Elephas',
}

# HiruDewmi/Audio-Classification-for-Elephant-Sounds - curated elephant WAVs, no LICENSE
# file (GitHub API reports license:null). Used here for the experiment; recorded as
# license "none (GitHub repo has no LICENSE file)" per clip.
HIRUDMI_REPO = "HiruDewmi/Audio-Classification-for-Elephant-Sounds"
HIRUDMI_AUDIO_EXT = (".wav", ".mp3", ".flac", ".ogg")

# Cornell ELP "Congo Soundscapes" S3 was evaluated and rejected as an elephant_call
# source - see the module docstring's "REJECTED" note (24-hour 1.4 GB objects, no usable
# labels without the access-gated Raven tables, African forest elephant).

# ---------------------------------------------------------------------------
# Manual field captures (project-owned)
# ---------------------------------------------------------------------------
# Datasets recorded by hand for this project, checked into
# ml/datasets/acoustic/manual_sources/. Two hardware domains so far - each
# source dict below carries its own "recorder"/"license"/"dataset" so the
# manifest records the true capture hardware per source, not a blanket XIAO
# label.
#
# dir 1/2 (xiao_esp32s3_*) - 16 kHz mono, 10 s per clip, captured on the XIAO
# ESP32S3 Sense onboard PDM MEMS mic (MSM261D3526H1CPM). This is the closest
# real-MEMS-microphone source to the deployment recording domain, so it is
# exactly the recording-condition diversity that breaks the Mendeley
# single-rig gunshot<->ambient confound (same rationale as the Freesound
# gunshot supplement). CAVEAT recorded in ml/acoustic/README.md: the XIAO PDM
# mic is NOT the deployment mic (INMP441 I2S) - there is a transfer gap.
# Every XIAO clip carries a ~+0.16 DC offset (a PDM-MEMS trait); normalize_clip's
# DC removal (revision e2) handles it.
#
# dir 1 - flat WAV, filename prefix is the class:
#   bg -> ambient   chain -> chainsaw   gun -> gunshot   vechicle -> vehicle  (sic,
#   DROPPED 2026-09-14 - the prefix map below no longer routes "vechicle" to a
#   class in CLASS_SCHEME, so those files are silently skipped, not deleted)
# dir 2 - Edge Impulse ingestion-JSON export (payload.values = raw int16 counts,
#   interval_ms 0.0625 = 16 kHz), already split into training/ and testing/:
#   Elephant -> elephant_call   Noice -> ambient
#
# dir 3 (laptop_phone_2026-09) - a THIRD, distinct recording domain: the
# project owner's laptop built-in mic recording reference sounds played back
# from a phone speaker (chainsaw/vehicle/elephant-call video/audio clips).
# UNO Q + INMP441 wiring was confirmed infeasible without the Media Carrier
# (see docs/research/platform), so this is the fallback real-audio path for
# the weakest classes. CAVEAT recorded in ml/acoustic/README.md: this is a
# THIRD acoustic domain on top of the XIAO-vs-INMP441 gap - laptop-mic
# frequency response + phone-speaker playback coloration is neither the XIAO
# PDM mic nor the deployment INMP441 I2S mic. 48 kHz mono WAV, variable length
# (normalize_clip crops/pads to the training window), filename prefix is the
# class: chain -> chainsaw   vehicle -> vehicle (DROPPED, see above - the
# "vehicle" prefix here no longer routes to a class in CLASS_SCHEME)
# elephant -> elephant_call
XIAO_MANUAL_ROOT = os.path.join(_ROOT, "ml", "datasets", "acoustic", "manual_sources")
XIAO_SOURCES = (
    {
        "subdir": "xiao_esp32s3_2026-09",
        "kind": "wav_flat",
        "prefix_label": {"bg": "ambient", "chain": "chainsaw",
                         "gun": "gunshot", "vechicle": "vehicle"},
        "capture_date": "2026-09",
    },
    {
        "subdir": "xiao_esp32s3_elephant_noise_2026-09",
        "kind": "ei_json_split",
        "prefix_label": {"Elephant": "elephant_call", "Noice": "ambient"},
        "capture_date": "2024-05-17",  # from the ingestion JSON `iat`
    },
    {
        "subdir": "laptop_phone_2026-09",
        "kind": "wav_flat",
        "prefix_label": {"chain": "chainsaw", "vehicle": "vehicle",
                         "elephant": "elephant_call"},
        "capture_date": "2026-09-14",
        "recorder": "laptop built-in mic (Audacity capture), source audio played back from phone speaker",
        "license": "project-owned (EleTect field capture, laptop mic + phone-played reference audio)",
        "dataset": "EleTect laptop/phone field capture (laptop_phone_2026-09)",
    },
)
XIAO_LICENSE = "project-owned (EleTect field capture, XIAO ESP32S3 Sense onboard PDM MEMS mic)"
XIAO_NATIVE_RATE_HZ = 16000

# Edge Impulse's files endpoint accepts up to 1000 files / 100 MB each per request.
BATCH_SIZE = 50
MAX_RETRIES = 4


def _clip_samples(clip_seconds):
    return int(SAMPLE_RATE_HZ * clip_seconds)


# A real browser UA clears Cloudflare's cheapest bot heuristic more often than the
# python-requests default does. Not a guarantee against a full JS challenge, but it
# measurably lifts the Mendeley public-api hit rate.
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class _ShimResponse:
    """Minimal requests.Response stand-in for the curl fallback path."""

    def __init__(self, status_code, content):
        self.status_code = status_code
        self.content = content
        self.headers = {}

    @property
    def text(self):
        return self.content.decode("utf-8", "replace")

    def json(self):
        return json.loads(self.content)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Client Error (curl) for url")


def _curl_get(url, params=None):
    """Fetch via the system curl binary.

    Cloudflare's managed challenge on data.mendeley.com fingerprints the TLS/HTTP2
    client, not the headers: python-requests (urllib3) is blocked on every attempt
    regardless of User-Agent/Accept-Language, while curl's handshake passes cleanly
    and repeatably. Everything Mendeley-hosted therefore goes through curl.
    """
    import subprocess
    from urllib.parse import urlencode

    if params:
        url = f"{url}?{urlencode(params)}"
    proc = subprocess.run(
        [
            "curl", "-sS", "-L", "--compressed", "--max-time", "180",
            "-A", _UA, "-H", "Accept-Language: en-US,en;q=0.9",
            "-w", "\n%{http_code}", url,
        ],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise OSError(f"curl exit {proc.returncode}: {proc.stderr.decode('utf-8', 'replace').strip()}")
    body, _, code = proc.stdout.rpartition(b"\n")
    return _ShimResponse(int(code or 0), body)


# Secret-bearing query parameters, masked before an exception becomes text.
# requests renders an HTTPError as "<status> ... for url: <url>" with the query
# string intact, so `print(f"{err}")` on a Freesound or xeno-canto call prints
# the API key - once per retry in _get(), and again in the traceback when the
# retries run out. Both APIs require the key as a query parameter (that is their
# documented scheme and not ours to change), so the masking belongs here, at the
# point the error turns into output, rather than at the call sites.
#
# The \b matters: it keeps "sort_key=" and similar from matching, because "_" is
# a word character and so there is no boundary in front of the "key" in it.
_SECRET_PARAM = re.compile(
    r"\b((?:api_?key|access_?token|token|key|password|secret)=)[^&\s'\"]+",
    re.IGNORECASE,
)


def _redact(value):
    """Stringify an exception with any API key in its URL masked out."""
    return _SECRET_PARAM.sub(r"\1***", str(value))


def _get(url, **kwargs):
    # An Accept-Language header is what actually clears the data.mendeley.com
    # Cloudflare bot-check: a browser UA alone still draws the JS challenge, but a
    # UA + Accept-Language pair passes the managed-challenge heuristic reliably.
    headers = {"User-Agent": _UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"}
    headers.update(kwargs.pop("headers", {}) or {})
    if "data.mendeley.com" in url:
        # requests is fingerprint-blocked here on every attempt; curl is not.
        for attempt in range(MAX_RETRIES):
            try:
                resp = _curl_get(url, kwargs.get("params"))
                resp.raise_for_status()
                return resp
            except (requests.HTTPError, OSError) as err:
                if attempt == MAX_RETRIES - 1:
                    raise
                wait = 5 * 2**attempt
                print(f"    {_redact(err)} - retrying in {wait}s")
                time.sleep(wait)
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=120, headers=headers, **kwargs)
            if resp.status_code == 403 and resp.headers.get("Cf-Mitigated") == "challenge":
                # data.mendeley.com sits behind Cloudflare and its public-api host
                # intermittently answers plain HTTP clients with a JS bot-challenge
                # rather than a JSON body. Backing off and retrying sometimes clears it;
                # if every retry fails, open
                # https://data.mendeley.com/datasets/x48cwz364j/3 in a real browser once
                # and re-run shortly after. The Mendeley fetch is wrapped in safe_fetch()
                # so a hard failure here does not sink the rest of the recon.
                print(f"    Cloudflare bot-challenge on {url} - not a normal HTTP error")
            resp.raise_for_status()
            return resp
        except requests.RequestException as err:
            if attempt == MAX_RETRIES - 1:
                raise
            wait = 5 * 2**attempt
            print(f"    {_redact(err)} - retrying in {wait}s")
            time.sleep(wait)


def _fit_to_window(data, clip_samples):
    """Fit a mono signal to exactly clip_samples.

    Longer than the window: return the most energetic clip_samples-long slice, so
    an event that sits away from the centre (common in Freesound uploads) is
    captured rather than cropped out. Shorter: loop the clip to fill the window
    instead of zero-padding - the DSP block's local normalization amplifies padded
    silence into noise and blurs the class-defining event.
    """
    n = len(data)
    if n == clip_samples:
        return data.astype(np.float32)
    if n > clip_samples:
        win = clip_samples
        csum = np.concatenate([[0.0], np.cumsum(data.astype(np.float64) ** 2)])
        starts = np.arange(0, n - win + 1)
        window_energy = csum[starts + win] - csum[starts]
        best = int(np.argmax(window_energy))
        return data[best : best + win].astype(np.float32)
    reps = int(np.ceil(clip_samples / n))
    return np.tile(data, reps)[:clip_samples].astype(np.float32)


def normalize_clip(raw_bytes, clip_seconds):
    """Decode arbitrary WAV/MP3/FLAC/OGG bytes into 8 kHz mono 16-bit PCM WAV, fixed length.

    Anti-aliased resample via scipy.signal.resample_poly, then fit to exactly
    _clip_samples(clip_seconds) via _fit_to_window (energy-aware crop / loop-fill),
    then peak-normalize so every source lands in the same amplitude range.
    """
    clip_samples = _clip_samples(clip_seconds)
    data, orig_rate = sf.read(io.BytesIO(raw_bytes), dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)

    # Remove any DC offset before anything else. A constant bias carries no spectral
    # information the MFE block can use, but it does two concrete harms: it wastes the
    # lowest mel bin, and - worse - it dominates the sum-of-squares in _fit_to_window
    # so the "most energetic window" crop degenerates to an almost arbitrary slice.
    # Clean studio/Freesound sources sit at ~1e-4 here (a no-op); the XIAO ESP32S3
    # PDM-MEMS captures in ml/datasets/acoustic/manual_sources/ sit at ~0.16.
    if data.size:
        data = data - float(np.mean(data))

    if orig_rate != SAMPLE_RATE_HZ:
        frac = Fraction(SAMPLE_RATE_HZ, orig_rate).limit_denominator(1000)
        data = resample_poly(data, frac.numerator, frac.denominator).astype(np.float32)

    data = _fit_to_window(data, clip_samples)

    peak = float(np.max(np.abs(data))) if data.size else 0.0
    if peak > 1e-6:
        data = data * (0.95 / peak)

    data = np.clip(data, -1.0, 1.0)
    out = io.BytesIO()
    sf.write(out, data, SAMPLE_RATE_HZ, subtype="PCM_16", format="WAV")
    return out.getvalue()


# ---------------------------------------------------------------------------
# Fetchers - each returns a list of record dicts (no audio bytes yet)
# ---------------------------------------------------------------------------


def _mendeley_folder_files(folder_id):
    """Every file record in one Mendeley public-api folder for dataset version 3.

    The public-api has no flat "all files" listing (a bare /files?version=3 is a
    400, and folder_id=root is empty because this dataset keeps everything in
    sub-folders). It is one request per folder, addressed by the folder UUID.
    The endpoint returns up to 1000 records per call with no usable paging cursor;
    the folders we read (597 + 150 gunshot, and an ambient pool we only sample
    400 from) all sit within that ceiling.
    """
    return _get(
        f"{MENDELEY_API}/files",
        params={"folder_id": folder_id, "version": 3},
    ).json()


def fetch_mendeley_gunshot_ambient():
    """Pull gunshot (capped train folder + full authored test folder) and a seeded ambient subsample."""
    print("Fetching Mendeley x48cwz364j v3 file listing...")
    files_by_folder = {
        fid: _mendeley_folder_files(fid)
        for fid in (GUNSHOT_TRAIN_FOLDER, GUNSHOT_TEST_FOLDER, AMBIENT_FOLDER)
    }

    gunshot_train = files_by_folder.get(GUNSHOT_TRAIN_FOLDER, [])
    gunshot_test = files_by_folder.get(GUNSHOT_TEST_FOLDER, [])
    gunshot_total = len(gunshot_train) + len(gunshot_test)
    print(f"  gunshot: {len(gunshot_train)} train + {len(gunshot_test)} test = {gunshot_total} available")
    if gunshot_total != GUNSHOT_DESCRIBED_TOTAL:
        print(
            f"    NOTE: dataset description claims {GUNSHOT_DESCRIBED_TOTAL} gunshot files; "
            f"v3's public-api listing actually holds {gunshot_total}. Using what is really there."
        )
    if len(gunshot_train) > GUNSHOT_TRAIN_CAP:
        gunshot_train = sorted(
            random.Random(SPLIT_SEED).sample(gunshot_train, GUNSHOT_TRAIN_CAP),
            key=lambda f: f["filename"],
        )
        print(
            f"    gunshot train capped to {GUNSHOT_TRAIN_CAP}/{len(files_by_folder[GUNSHOT_TRAIN_FOLDER])} "
            f"(seed {SPLIT_SEED}); the {len(gunshot_test)}-file authored test folder is kept whole"
        )

    ambient_pool = sorted(files_by_folder.get(AMBIENT_FOLDER, []), key=lambda f: f["filename"])
    print(f"  ambient: {len(ambient_pool)} files available in the one usable background folder")
    rng = random.Random(SPLIT_SEED)
    selected = ambient_pool if len(ambient_pool) <= AMBIENT_CAP else rng.sample(ambient_pool, AMBIENT_CAP)
    selected.sort(key=lambda f: f["filename"])  # hex-timestamp filenames sort in time order
    n_test = max(1, round(len(selected) * TEST_FRACTION))
    ambient_train, ambient_test = selected[:-n_test], selected[-n_test:]
    print(
        f"    subsampled {len(selected)}/{len(ambient_pool)} (seed {SPLIT_SEED}), "
        f"chronological split: {len(ambient_train)} train / {len(ambient_test)} test"
    )

    def to_records(entries, label, category):
        return [
            {
                "label": label,
                "category": category,
                "name": f["filename"],
                "url": f["content_details"]["download_url"],
                "source_id": f["id"],
                "license": "CC BY 4.0",
                "dataset": "Mendeley x48cwz364j v3 (Katsis et al. 2022)",
            }
            for f in entries
        ]

    return (
        to_records(gunshot_train, "gunshot", "training")
        + to_records(gunshot_test, "gunshot", "testing")
        + to_records(ambient_train, "ambient", "training")
        + to_records(ambient_test, "ambient", "testing")
    )


def fetch_esc50_category(category, label, license_str, esc10_only):
    """Pull one ESC-50 category, split by the dataset's own fold column (fold 5 = test).

    `esc10_only` keeps only the cleanly CC-BY ESC-10 subset (used for chainsaw); with it
    False the full 40-clip category is taken (used for the ambient nature-category
    supplement, whose licence is the wider CC BY-NC - recorded per clip).
    """
    print(f"Fetching ESC-50 meta/esc50.csv for {category!r}...")
    import csv

    text = _get(f"{ESC50_RAW}/meta/esc50.csv").text
    rows = list(csv.DictReader(io.StringIO(text)))
    picked = [
        r for r in rows
        if r["category"] == category and (r["esc10"] == "True" or not esc10_only)
    ]
    print(
        f"  {category} ({'esc10 subset' if esc10_only else 'full set'}, {license_str}): "
        f"{len(picked)} clips across folds {sorted({r['fold'] for r in picked})}"
    )
    if len(picked) != 40:
        print(f"    NOTE: expected 40 ESC-50 {category} clips, found {len(picked)}")

    return [
        {
            "label": label,
            "category": "testing" if r["fold"] == "5" else "training",
            "name": r["filename"],
            "url": f"{ESC50_RAW}/audio/{r['filename']}",
            "source_id": r["filename"],
            "license": license_str,
            "dataset": "ESC-50 (Piczak 2015)",
            "fold": r["fold"],
        }
        for r in picked
    ]


def _freesound_search_one(query, api_key):
    """One Freesound text search, all licenses, returning every hit with an HQ preview.

    Paged manually with an explicit `&page=N` rather than by following the response's
    `next` URL - token auth is a query param and Freesound's `next` URL drops it, so
    every page has to carry the token itself.
    """
    duration_filter = f"duration:[{FREESOUND_MIN_DURATION_S} TO {FREESOUND_MAX_DURATION_S}]"
    hits, page = [], 1
    while len(hits) < 500:  # 500 is a supply ceiling per query, not the selection cap
        resp = _get(
            f"{FREESOUND_API}/search/text/",
            params={
                "query": query,
                "filter": duration_filter,
                "fields": "id,name,license,username,url,previews,duration,tags",
                "page": page,
                "page_size": 150,
                "token": api_key,
            },
        ).json()
        results = resp.get("results", [])
        hits.extend(results)
        if not resp.get("next") or not results:
            break
        page += 1
    with_preview = [h for h in hits if (h.get("previews") or {}).get("preview-hq-mp3")]
    print(
        f"  Freesound '{query}': {len(with_preview)} hits with a downloadable HQ preview "
        f"({len(hits) - len(with_preview)} skipped, no preview)"
    )
    return with_preview


def fetch_freesound_class(label, queries, api_key):
    """Search Freesound for one class across one-or-more queries, dedup on id, seeded split.

    `queries` may be a single string or a list. Each sub-query is searched independently
    (Freesound relevance is uploader tagging, not expert verification - so widening the
    query set trades precision for the volume the named species classes need), the hit
    pools are concatenated and de-duplicated on Freesound id, then one seeded
    sample-to-cap + TEST_FRACTION split is taken over the deduped pool. The cap is
    FREESOUND_CAP[label] if the class has a dedicated entry (the thin species classes
    lift it past their real supply), else FREESOUND_CAP_DEFAULT.
    """
    if isinstance(queries, str):
        queries = [queries]
    by_id, first_query = {}, {}
    for q in queries:
        for h in _freesound_search_one(q, api_key):
            if h["id"] not in by_id:
                by_id[h["id"]] = h
                first_query[h["id"]] = q
    pool = sorted(by_id.values(), key=lambda h: h["id"])
    print(f"    '{label}': {len(pool)} unique clips across {len(queries)} queries")

    cap = FREESOUND_CAP.get(label, FREESOUND_CAP_DEFAULT)
    rng = random.Random(SPLIT_SEED)
    selected = pool if len(pool) <= cap else rng.sample(pool, cap)
    rng.shuffle(selected)
    n_test = max(1, round(len(selected) * TEST_FRACTION)) if selected else 0
    test, train = selected[:n_test], selected[n_test:]
    print(f"    selected {len(selected)}/{len(pool)}: {len(train)} train / {len(test)} test")

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
                    "dataset": f"Freesound.org (query {first_query[h['id']]!r})",
                    "uploader": h.get("username"),
                    "freesound_url": h.get("url"),
                    "query": first_query[h["id"]],
                }
            )
    return records


def fetch_hirudmi_elephant():
    """Curated elephant Rumble/Roar/Trumpet WAVs from a GitHub repo with no LICENSE file.

    Recorded per-clip as license "none (GitHub repo has no LICENSE file)". Used for this
    experiment only; production license-clearing is a separate gate.
    """
    print(f"Listing {HIRUDMI_REPO} default branch tree...")
    try:
        repo = _get(f"{GITHUB_API}/repos/{HIRUDMI_REPO}").json()
        branch = repo.get("default_branch", "main")
        tree = _get(
            f"{GITHUB_API}/repos/{HIRUDMI_REPO}/git/trees/{branch}?recursive=1"
        ).json()
    except requests.RequestException as err:
        print(f"  NOTICE: GitHub listing failed ({_redact(err)}) - contributing 0 elephant clips")
        return []

    audio = [
        n["path"]
        for n in tree.get("tree", [])
        if n["type"] == "blob" and n["path"].lower().endswith(HIRUDMI_AUDIO_EXT)
    ]
    print(f"  {len(audio)} audio files found in the repo tree")
    if not audio:
        return []

    rng = random.Random(SPLIT_SEED)
    audio = sorted(audio)
    rng.shuffle(audio)
    n_test = max(1, round(len(audio) * TEST_FRACTION))
    test, train = audio[:n_test], audio[n_test:]
    raw_base = f"https://raw.githubusercontent.com/{HIRUDMI_REPO}/{branch}/"

    records = []
    for category, paths in (("training", train), ("testing", test)):
        for p in paths:
            records.append(
                {
                    "label": "elephant_call",
                    "category": category,
                    "name": "hirudmi_" + p.replace("/", "_"),
                    "url": raw_base + requests.utils.quote(p),
                    "source_id": p,
                    "license": "none (GitHub repo has no LICENSE file)",
                    "dataset": f"github.com/{HIRUDMI_REPO}",
                }
            )
    return records


def fetch_xenocanto_class(label, query):
    """xeno-canto recordings for a taxon query. Yields 0 gracefully if the taxon is absent.

    xeno-canto retired the unauthenticated API v2 in 2025; API v3 requires a
    per-account key we do not hold. This source was only ever supplementary for
    elephant_call, so treat its absence as a clean zero rather than a hard
    failure. Set XENOCANTO_API_KEY in the environment to re-enable.
    """
    print(f"Querying xeno-canto for {label} ({query})...")
    api_key = os.environ.get("XENOCANTO_API_KEY", "").strip()
    if not api_key:
        print(
            "  NOTICE: xeno-canto API v2 is retired and v3 needs an account key "
            f"(XENOCANTO_API_KEY unset) - contributing 0 {label} clips"
        )
        return []
    try:
        doc = _get(
            "https://xeno-canto.org/api/3/recordings",
            params={"query": query, "key": api_key},
        ).json()
    except requests.RequestException as err:
        print(f"  NOTICE: xeno-canto query failed ({_redact(err)}) - contributing 0 {label} clips")
        return []

    recs = doc.get("recordings", []) or []
    print(f"  xeno-canto '{query}': {doc.get('numRecordings', len(recs))} recordings reported")
    if not recs:
        return []

    rng = random.Random(SPLIT_SEED)
    recs = sorted(recs, key=lambda r: r.get("id", ""))
    rng.shuffle(recs)
    n_test = max(1, round(len(recs) * TEST_FRACTION))
    test, train = recs[:n_test], recs[n_test:]

    records = []
    for category, entries in (("training", train), ("testing", test)):
        for r in entries:
            file_url = r.get("file") or ""
            if file_url.startswith("//"):
                file_url = "https:" + file_url
            if not file_url:
                continue
            records.append(
                {
                    "label": label,
                    "category": category,
                    "name": f"xc{r.get('id')}_{r.get('en', 'unknown').replace(' ', '_')}",
                    "url": file_url,
                    "source_id": r.get("id"),
                    "license": r.get("lic", "xeno-canto (see recording page)"),
                    "dataset": f"xeno-canto (query {query!r})",
                    "xenocanto_url": r.get("url"),
                }
            )
    return records


def _xiao_ei_json_to_wav_bytes(json_path):
    """One Edge Impulse ingestion-JSON file -> 16 kHz mono PCM_16 WAV bytes.

    `payload.values` is the raw int16 microphone counts; `interval_ms` 0.0625 means
    16 kHz. No processing here - normalize_clip does the DC removal, resample and
    window fit - this only lifts the samples out of the JSON container.
    """
    with open(json_path) as fh:
        payload = json.load(fh)["payload"]
    interval_ms = float(payload.get("interval_ms") or 0)
    rate = round(1000.0 / interval_ms) if interval_ms else XIAO_NATIVE_RATE_HZ
    vals = np.asarray(payload["values"], dtype=np.float32)
    if vals.size and float(np.max(np.abs(vals))) > 1.5:
        vals = vals / 32768.0
    out = io.BytesIO()
    sf.write(out, vals, rate, subtype="PCM_16", format="WAV")
    return out.getvalue()


def fetch_xiao_manual_sources(sought=None):
    """Project-owned XIAO ESP32S3 Sense field captures under ml/datasets/acoustic/manual_sources/.

    Local files only - no network. Each clip is handed to download_and_normalize via
    `local_path`, so it flows through the exact same normalize_clip (DC removal,
    anti-aliased 16->8 kHz resample, energy-aware window fit, peak-normalize) and
    manifest/upload path as every downloaded source. See XIAO_SOURCES for the
    directory layout and the prefix->label maps.

    Split: dir 2 is an Edge Impulse export that already carries training/ and
    testing/ folders - that authored split is kept as-is. dir 1 is flat, so it gets
    one seeded per-label TEST_FRACTION split (same SPLIT_SEED as every other source).
    """
    want = set(CLASS_SCHEME) if sought is None else set(sought)
    records = []

    for src in XIAO_SOURCES:
        base = os.path.join(XIAO_MANUAL_ROOT, src["subdir"])
        if not os.path.isdir(base):
            print(f"  NOTICE: {base} not found - contributing 0 XIAO clips from it")
            continue
        pmap = src["prefix_label"]

        if src["kind"] == "wav_flat":
            by_label = {}
            for fn in sorted(os.listdir(base)):
                if not fn.lower().endswith(".wav"):
                    continue
                prefix = fn.split(".")[0]
                label = pmap.get(prefix)
                if label is None or label not in want:
                    continue
                by_label.setdefault(label, []).append(fn)
            for label, files in sorted(by_label.items()):
                rng = random.Random(SPLIT_SEED)
                files = sorted(files)
                rng.shuffle(files)
                n_test = max(1, round(len(files) * TEST_FRACTION))
                split = {fn: ("testing" if i < n_test else "training")
                         for i, fn in enumerate(files)}
                for fn in sorted(files):
                    stem = os.path.splitext(fn)[0]
                    records.append({
                        "label": label,
                        "category": split[fn],
                        "name": f"{src['subdir']}_{stem}",
                        "url": "file://" + os.path.join(base, fn).replace("\\", "/"),
                        "local_path": os.path.join(base, fn),
                        "source_id": f"{src['subdir']}_{stem}",
                        "license": src.get("license", XIAO_LICENSE),
                        "dataset": src.get("dataset", f"EleTect XIAO field capture ({src['subdir']})"),
                        "recorder": src.get("recorder", "XIAO ESP32S3 Sense (onboard PDM MEMS mic)"),
                        "capture_date": src["capture_date"],
                    })
                print(f"  {src['subdir']}: {label:13s} {len(files):3d} clips "
                      f"({len(files) - n_test} train / {n_test} test)")

        elif src["kind"] == "ei_json_split":
            raw_out = os.path.join(CACHE_DIR, "_xiao_json_wav")
            os.makedirs(raw_out, exist_ok=True)
            per_class = {}
            for category in ("training", "testing"):
                cdir = os.path.join(base, category)
                if not os.path.isdir(cdir):
                    continue
                for fn in sorted(os.listdir(cdir)):
                    if not fn.endswith(".json"):
                        continue
                    prefix = fn.split(".")[0]
                    label = pmap.get(prefix)
                    if label is None or label not in want:
                        continue
                    stem = fn.split(".ingestion")[0].replace(".wav", "").replace(".", "_")
                    safe_id = f"{src['subdir']}_{stem}"
                    wav_path = os.path.join(raw_out, safe_id + ".wav")
                    try:
                        if not os.path.exists(wav_path):
                            with open(wav_path, "wb") as wf:
                                wf.write(_xiao_ei_json_to_wav_bytes(os.path.join(cdir, fn)))
                    except Exception as err:  # noqa: BLE001
                        print(f"  SKIP xiao json {fn}: {_redact(err)}")
                        continue
                    records.append({
                        "label": label,
                        "category": category,
                        "name": safe_id,
                        "url": "file://" + os.path.join(cdir, fn).replace("\\", "/"),
                        "local_path": wav_path,
                        "source_id": safe_id,
                        "license": src.get("license", XIAO_LICENSE),
                        "dataset": src.get("dataset", f"EleTect XIAO field capture ({src['subdir']})"),
                        "recorder": src.get("recorder", "XIAO ESP32S3 Sense (onboard PDM MEMS mic)"),
                        "capture_date": src["capture_date"],
                    })
                    per_class.setdefault(label, {"training": 0, "testing": 0})[category] += 1
            for label, c in sorted(per_class.items()):
                print(f"  {src['subdir']}: {label:13s} "
                      f"{c['training'] + c['testing']:3d} clips "
                      f"({c['training']} train / {c['testing']} test, authored split)")

    print(f"  Manual field-capture sources: {len(records)} clips total")
    return records


# ---------------------------------------------------------------------------
# Data floor
# ---------------------------------------------------------------------------


def classify_floor_and_prune(records, sought=None):
    """Tag each named target (now just elephant_call) against CLIP_FLOOR.

    elephant_call below the floor -> merge_ready = False (reported loudly); the clips
    are kept and still trained, since dropping the headline class helps nobody - the
    honest number goes in the README. Everything else is "trained". Returns (records,
    floor_report) where floor_report[label] = {"real_count": int, "status": str}.
    `sought` restricts the check to the classes this run actually tried to fetch.
    """
    targets = [c for c in FLOOR_TARGETS if sought is None or c in sought]
    counts = {}
    for r in records:
        counts[r["label"]] = counts.get(r["label"], 0) + 1

    floor_report = {}
    merge_ready = True
    for label in targets:
        n = counts.get(label, 0)
        clears = n >= CLIP_FLOOR
        against_target = "meets" if n >= CLIP_TARGET else "below"

        if label == "elephant_call" and not clears:
            merge_ready = False
            status = "trained_below_floor"
            print(
                f"  NOTICE: 'elephant_call' has {n} real clips, below the {CLIP_FLOOR} "
                f"floor - kept and trained, but the per-species track is not merge-ready."
            )
        elif not clears:
            status = "trained_below_floor"
            print(
                f"  NOTICE: '{label}' has {n} real clips, below the {CLIP_FLOOR} floor - "
                f"kept and trained; its held-out number is reported as-is."
            )
        else:
            status = "trained"
            print(
                f"  '{label}': {n} real clips - clears the {CLIP_FLOOR} floor "
                f"({against_target} the {CLIP_TARGET} target)."
            )
        floor_report[label] = {"real_count": n, "status": status}

    if not merge_ready:
        print(
            "\n  *** elephant_call did NOT clear the data floor. The per-species acoustic "
            "track is NOT merge-ready: do not wire the model into handle_acoustic_event(). "
            "Report this outcome in ml/acoustic/README.md and stop. ***"
        )
    floor_report["_elephant_merge_ready"] = merge_ready
    return records, floor_report


# ---------------------------------------------------------------------------
# Download / upload / manifest
# ---------------------------------------------------------------------------


def download_and_normalize(records, clip_seconds):
    """Download each record's raw audio, normalize it, attach normalized bytes + sha256.

    The cache key includes the clip length so the window-length sweep can re-crop the
    same downloads at each candidate length without collisions.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    # "eN" = normalize_clip revision. Bump it whenever normalize_clip changes so a
    # stale cache from an older revision is not silently reused.
    #   e1 -> e2: DC-offset removal added (harmless for clean sources; required for
    #             the XIAO ESP32S3 PDM-MEMS manual captures).
    tag = f"{clip_seconds:g}s.e2"
    kept = []
    for i, rec in enumerate(records, 1):
        safe_id = str(rec["source_id"]).replace("/", "_")[:120]
        cache_path = os.path.join(CACHE_DIR, f"{rec['label']}_{safe_id}.{tag}.norm.wav")
        raw_path = os.path.join(CACHE_DIR, f"_raw_{rec['label']}_{safe_id}")
        try:
            if os.path.exists(cache_path):
                with open(cache_path, "rb") as fh:
                    norm = fh.read()
            else:
                if rec.get("local_path"):
                    # A local manual-source clip (see fetch_xiao_manual_sources): the
                    # canonical WAV already sits on disk, so there is nothing to download.
                    with open(rec["local_path"], "rb") as fh:
                        raw = fh.read()
                elif os.path.exists(raw_path):
                    with open(raw_path, "rb") as fh:
                        raw = fh.read()
                else:
                    raw = _get(rec["url"]).content
                    with open(raw_path, "wb") as fh:
                        fh.write(raw)
                norm = normalize_clip(raw, clip_seconds)
                with open(cache_path, "wb") as fh:
                    fh.write(norm)
        except Exception as err:  # noqa: BLE001 - one bad clip must not sink the run
            print(f"  SKIP {rec['label']} {safe_id}: {_redact(err)}")
            continue
        rec["normalized_bytes"] = norm
        rec["sha256"] = hashlib.sha256(norm).hexdigest()
        kept.append(rec)
        if i % 100 == 0 or i == len(records):
            print(f"  normalized {i}/{len(records)} (kept {len(kept)})")
    return kept


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
            detail = err.response.text[:300] if err.response is not None else _redact(err)
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
                print(f"    {_redact(err)}, retrying in {wait}s")
                time.sleep(wait)
                continue
            return 0, _redact(err)
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
                print(f"  [{category}] {label:18s} batch of {len(batch):3d} -> FAILED {err[0]}")
                continue
            ok += len(batch)
            done.update(r["name"] for r in batch)
            with open(ledger, "w") as fh:
                json.dump(sorted(done), fh)
            print(f"  [{category}] {label:18s} batch of {len(batch):3d} -> uploaded ({ok} so far)")
    return ok, failed


def _floor_status(label, floor_report):
    if label in floor_report:
        return floor_report[label]["status"]
    return "trained"


def write_manifest(records, clip_seconds, floor_report):
    by_class = {}
    for r in records:
        cls = by_class.setdefault(
            r["label"],
            {"dataset": r["dataset"], "license": r["license"], "training": [], "testing": []},
        )
        entry = {k: r[k] for k in ("name", "source_id", "license", "sha256", "url") if k in r}
        for extra in ("uploader", "freesound_url", "xenocanto_url", "query", "fold",
                      "bbc_description", "recorder", "capture_date"):
            if extra in r:
                entry[extra] = r[extra]
        cls[r["category"]].append(entry)

    queries_used = {}
    for r in records:
        if r.get("query"):
            queries_used.setdefault(r["label"], set()).add(r["query"])

    for label, cls in by_class.items():
        cls["floor_status"] = _floor_status(label, floor_report)
        cls["train_count"] = len(cls["training"])
        cls["test_count"] = len(cls["testing"])
        if label in queries_used:
            cls["queries"] = sorted(queries_used[label])

    # A named target with zero real clips has no records, so add an explicit stub so the
    # manifest still carries every FLOOR_TARGETS member. "reserved_no_data" if nothing was
    # found at all; the floor_report status otherwise.
    for label in FLOOR_TARGETS:
        if label not in by_class:
            rep = floor_report.get(label, {})
            real = rep.get("real_count", 0)
            by_class[label] = {
                "dataset": "-",
                "license": "-",
                "training": [],
                "testing": [],
                "floor_status": rep.get(
                    "status", "reserved_no_data" if real == 0 else "reserved_insufficient_data"
                ),
                "real_count": real,
                "train_count": 0,
                "test_count": 0,
            }

    doc = {
        "schema": "eletect-x/acoustic-clip-manifest/3",
        "class_scheme": list(CLASS_SCHEME),
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "clip_seconds": clip_seconds,
        "window_seconds": clip_seconds,
        "clip_floor": CLIP_FLOOR,
        "clip_target": CLIP_TARGET,
        "split_seed": SPLIT_SEED,
        "test_fraction": TEST_FRACTION,
        "elephant_merge_ready": floor_report.get("_elephant_merge_ready", True),
        "floor_report": {
            k: v for k, v in floor_report.items() if not k.startswith("_")
        },
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
    ap.add_argument(
        "--clip-seconds",
        type=float,
        default=CLIP_SECONDS,
        help="clip / window length in seconds (default 4.0; used for the window-length sweep)",
    )
    ap.add_argument(
        "--only",
        action="append",
        metavar="LABEL",
        help="restrict to these classes (repeatable). Freesound-only classes still need the key.",
    )
    ap.add_argument(
        "--no-xiao",
        action="store_true",
        help="skip the project-owned XIAO ESP32S3 Sense manual captures "
             "(ml/datasets/acoustic/manual_sources/); used for the with/without A/B.",
    )
    args = ap.parse_args()
    clip_seconds = args.clip_seconds

    api_key = os.environ.get("EI_API_KEY")
    project_id = os.environ.get("EI_PROJECT_ID")
    fs_key = os.environ.get("FREESOUND_API_KEY")
    if not args.dry_run and (not api_key or not project_id):
        print("Set EI_API_KEY and EI_PROJECT_ID (or use --dry-run).", file=sys.stderr)
        sys.exit(1)
    if not fs_key:
        print(
            "WARNING: FREESOUND_API_KEY is not set - every Freesound-sourced class "
            "(chainsaw supplement, part of gunshot, part of elephant_call) will "
            "contribute 0 clips. Create one at https://freesound.org/apiv2/apply/ .",
            file=sys.stderr,
        )

    want = set(args.only) if args.only else set(CLASS_SCHEME)
    unknown = want - set(CLASS_SCHEME)
    if unknown:
        print(f"Unknown --only labels: {sorted(unknown)}", file=sys.stderr)
        sys.exit(1)

    records = []
    source_failures = []

    def safe_fetch(source_name, fn, *fn_args):
        """Run one fetcher; on any error log it, record it, and return [] so the rest of
        the reconciliation still completes. A dead source (e.g. Mendeley's intermittent
        Cloudflare bot-challenge) must not sink the whole recon run."""
        try:
            return fn(*fn_args)
        except Exception as err:  # noqa: BLE001 - deliberate: keep going, report at the end
            print(f"  SOURCE FAILED [{source_name}]: {_redact(err)}")
            source_failures.append((source_name, _redact(err)))
            return []

    if {"gunshot", "ambient"} & want:
        print("=== gunshot + ambient (Mendeley x48cwz364j v3, CC BY 4.0) ===")
        records += [
            r for r in safe_fetch("mendeley", fetch_mendeley_gunshot_ambient) if r["label"] in want
        ]

    if "gunshot" in want and fs_key:
        # Mendeley gunshot and Mendeley ambient are the same forest AudioMoth rig, so
        # the model learns "this rig's background = ambient" and reads the quieter
        # gunshot clips as ambient too. Pull gunshot from unrelated Freesound rigs to
        # force the decision onto the muzzle transient itself.
        print("\n=== gunshot supplement (Freesound multi-query, unrelated rigs) ===")
        records += safe_fetch(
            "freesound-gunshot", fetch_freesound_class, "gunshot",
            FREESOUND_QUERIES["gunshot"], fs_key,
        )

    if "ambient" in want:
        print("\n=== ambient supplement (ESC-50 nature categories, CC BY-NC) ===")
        for cat in AMBIENT_ESC50_CATEGORIES:
            records += safe_fetch(
                f"esc50-{cat}", fetch_esc50_category, cat, "ambient",
                "CC BY-NC 3.0 (ESC-50 full set)", False,
            )
        if fs_key:
            print("\n=== ambient supplement (Freesound multi-query, real forest/jungle soundscapes) ===")
            records += safe_fetch(
                "freesound-ambient", fetch_freesound_class, "ambient",
                FREESOUND_QUERIES["ambient"], fs_key,
            )

    if "chainsaw" in want:
        print("\n=== chainsaw (ESC-50 ESC-10 subset, CC BY) ===")
        records += safe_fetch(
            "esc50-chainsaw", fetch_esc50_category, "chainsaw", "chainsaw",
            "CC BY (ESC-10 subset)", True,
        )
        if fs_key:
            records += safe_fetch(
                "freesound-chainsaw", fetch_freesound_class, "chainsaw",
                FREESOUND_QUERIES["chainsaw"], fs_key,
            )

    if "elephant_call" in want:
        print("\n=== elephant_call (HiruDewmi GitHub + Freesound + xeno-canto) ===")
        records += safe_fetch("hirudmi-github", fetch_hirudmi_elephant)
        if fs_key:
            records += safe_fetch(
                "freesound-elephant", fetch_freesound_class, "elephant_call",
                FREESOUND_QUERIES["elephant_call"], fs_key,
            )
        records += safe_fetch(
            "xenocanto-elephant", fetch_xenocanto_class, "elephant_call",
            XENOCANTO_QUERIES["elephant_call"],
        )

    if not args.no_xiao:
        print("\n=== manual field captures: XIAO ESP32S3 Sense + laptop/phone (project-owned, local) ===")
        records += [
            r for r in safe_fetch("xiao-manual", fetch_xiao_manual_sources, want)
            if r["label"] in want
        ]

    if args.limit:
        by_label = {}
        for r in records:
            by_label.setdefault(r["label"], []).append(r)
        records = [r for group in by_label.values() for r in group[: args.limit]]
        print(f"\n--limit {args.limit}: truncated to {len(records)} clips total")

    print(
        f"\nDownloading and normalizing {len(records)} clips to {SAMPLE_RATE_HZ}Hz/"
        f"{clip_seconds:g}s mono WAV..."
    )
    records = download_and_normalize(records, clip_seconds)

    print(f"\nApplying the data floor (CLIP_FLOOR={CLIP_FLOOR}: elephant_call gates "
          "merge-readiness):")
    records, floor_report = classify_floor_and_prune(records, sought=want)

    write_manifest(records, clip_seconds, floor_report)

    print("\nReconciliation (label -> train/test/total vs floor/target):")
    by_label = {}
    for r in records:
        by_label.setdefault(r["label"], {"training": 0, "testing": 0})[r["category"]] += 1
    for label in CLASS_SCHEME:
        counts = by_label.get(label, {"training": 0, "testing": 0})
        total = counts["training"] + counts["testing"]
        status = floor_report.get(label, {}).get("status", "") if label in FLOOR_TARGETS else ""
        if label in FLOOR_TARGETS and total == 0 and not status:
            status = "RESERVED (no data, enum member kept)"
        floor = ""
        if label not in ("gunshot", "ambient") and total:
            floor = f"  [floor {CLIP_FLOOR} / target {CLIP_TARGET}]"
        print(
            f"  {label:18s} train={counts['training']:4d} test={counts['testing']:4d} "
            f"total={total:4d}{floor}  {status}"
        )
    if not floor_report.get("_elephant_merge_ready", True):
        print("\n  elephant_merge_ready = FALSE - see the NOTICE above.")

    if source_failures:
        print("\nSOURCES THAT FAILED THIS RUN (their classes are under-counted above):")
        for name, err in source_failures:
            print(f"  - {name}: {err[:160]}")
        print("  Re-run once these recover; the raw cache keeps whatever already downloaded.")

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
    print(
        f"\nCheck the result at "
        f"https://studio.edgeimpulse.com/studio/{project_id}/acquisition/training"
    )


if __name__ == "__main__":
    main()
