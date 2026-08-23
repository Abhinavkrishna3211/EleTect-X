# Acoustic classifier — five-class model, real public data (not yet trained)

Edge Impulse project **1094275** (`EleTect-X-Acoustic`), separate from `EleTect-X-Seismic`
(1094084) and `EleTect-X-Vision` (1094260). Project ID only is recorded here; the API key is not
in the repo and must be supplied through `EI_API_KEY` at run time.

**Status: the upload and training scripts are written and code-complete, but neither has run against
a live Edge Impulse project yet.** Two of the four acquisition paths were verified for real against
their live sources: ESC-50's `meta/esc50.csv` was fetched for real (confirmed all 40 chainsaw clips,
correct 32/8 fold split) and 2 real chainsaw clips were downloaded and normalized end-to-end —
8 kHz, exactly 4.0 s, byte-exact. Mendeley's public-api endpoint, however, is currently answering
with a **persistent Cloudflare bot-challenge** (HTTP 403, `Cf-Mitigated: challenge`) instead of the
dataset JSON, reproduced across several attempts minutes apart — a live external block on Mendeley's
side right now, not a bug in this script (`scripts/edge_impulse_upload_acoustic.py`'s `_get()`
detects and reports this case distinctly from an ordinary HTTP error). Freesound's two classes need
a `FREESOUND_API_KEY` — a free credential that has to be created by hand at
<https://freesound.org/apiv2/apply/> — which does not exist yet. Nothing below is a fabricated
number: the Dataset section states real, verified counts and licenses pulled from each source's own
API or metadata file; the Result section says plainly that no training run has happened yet rather
than inventing one.

## Dataset

Four distinct public sources feed the five `AcousticClass` labels
(`device/mpu/bridge/rpc.py`):

| Class | Source | License (verified) | Count (planned) |
|---|---|---|---|
| `gunshot` | Mendeley Data `x48cwz364j` v3, "Tropical forest gunshot classification training audio dataset" (Katsis et al. 2022, DOI 10.17632/x48cwz364j.3) | **CC BY 4.0** — confirmed via the dataset's own `data_licence` field in its public API record, not assumed from Mendeley's common default | 747 (597 train / 150 test, the authors' own two folders) |
| `ambient` | same Mendeley dataset, background-noise folder | CC BY 4.0, same record | up to 150, seeded subsample of 7,040 available |
| `chainsaw` | ESC-50, ESC-10 subset (Piczak 2015, DOI 10.1145/2733373.2806390), `meta/esc50.csv` rows with `category == "chainsaw" and esc10 == True` | **CC BY** — the ESC-10 subset only; the rest of ESC-50 is CC BY-NC and is never touched | 40 (all of them; 32 train / 8 test by the dataset's own `fold` column) |
| `vehicle` | Freesound.org, text search `"engine idling"` | Per-clip CC0 or CC BY, recorded individually per clip | up to 150, seeded subsample |
| `animal_call` | Freesound.org, text search `"elephant"` | Per-clip CC0 or CC BY, recorded individually per clip | up to 150, seeded subsample |

### Gunshot and ambient — Mendeley `x48cwz364j` v3

The dataset's own description claims 749 gunshot files and "over 35,000" background files. The
public API's actual file listing (7,788 entries total) holds 747 gunshot files across two folders
(597 + 150 — 79.9% / 20.1%, matching the description's stated 80/20 split by count) and only 7,040
loose background WAVs plus one 1.3 GB `background.zip` holding the rest. The 2-file gunshot gap
against the stated 749 is a real discrepancy between the dataset's description and its own file
listing, not a bug in this project's tooling — it is logged by the upload script, not hidden.

All 747 available gunshot clips are used, uncapped. It is real, rare, transient positive-class data
and there is no principled reason to throw part of it away for a tidier class balance; Edge
Impulse's automatic class weighting compensates for the resulting imbalance against the other four
classes at training time instead.

`background.zip` is skipped entirely and never downloaded — at 1.3 GB it would imply roughly
28,000 more files than the 7,040 loose ones, meaning it is almost certainly the larger, 80% share of
the background set, and downloading it just to throw away all but a ~150-clip subsample is not
worth 1.3 GB of transfer. This means the ambient class draws from only one of the authors' two
background folders, not both — see Caveats.

The gunshot class uses the authors' own two folders as its train/test split (temporally distinct
collection sessions, per the dataset's description — a stronger split than a random one). Ambient
has no second folder to play that role, so this project draws its own seeded (`SPLIT_SEED = 20260823`)
subsample and its own chronological split (filenames are UNIX-hex timestamps, sorted before
splitting) from inside the single available folder instead.

### Chainsaw — ESC-50 ESC-10 subset

All 40 ESC-50 clips tagged `category == chainsaw` already carry `esc10 == True` — the entire
chainsaw category is inside the CC BY-licensed ESC-10 subset, none of it needs excluding. Split by
the dataset's own `fold` column (folds 1–4 training = 32 clips, fold 5 testing = 8 clips), which
already keeps clips sharing a `src_file` inside a single fold rather than this project having to
re-derive that grouping itself.

### Vehicle and animal_call — sourced from Freesound, not the originally named sources

Three sources named for this task were checked against their live pages/APIs before any data was
pulled, and none of them held up:

- **UrbanSound8K** — originally specified for `vehicle` (`engine_idling`), filtered per-clip to
  CC0/CC BY. Its own metadata CSV (`slice_file_name, fsID, start, end, salience, fold, classID,
  class`) carries **no license column at all**, and the dataset's Zenodo record (1203745) and
  README both declare the entire distribution **CC BY-NC 4.0**. There is no CC0/CC BY subset
  inside it to filter to — the per-clip filtering this task was originally scoped around cannot be
  executed against real metadata that doesn't exist, so UrbanSound8K is not used at all.
- **Michael Pardo's elephant-rumble records** — originally specified as an `animal_call` candidate.
  Zenodo record 10576772 is a single R script (LGPL license) whose own description states "the
  sound files ... are not included in this archive"; the paired Dryad record
  (doi:10.5061/dryad.hmgqnk9nj) is derived CSV/RDS acoustic-feature tables carrying the same
  disclaimer. Neither contains a single audio file.
- **`github.com/HiruDewmi/Audio-Classification-for-Elephant-Sounds`** — the other named
  `animal_call` candidate. Real, curated Rumble/Roar/Trumpet WAV files do exist in its `data/`
  tree, but the repository has no `LICENSE` file, no terms stated in its README, and no
  attribution for where the original recordings came from — GitHub's own repository API reports
  `license: null`. Real audio with no usable license is not usable audio for this project.

Both classes are instead pulled directly from Freesound.org's search API
(`/apiv2/search/text/`), filtered to Freesound's own license facets `"Creative Commons 0"` or
`"Attribution"` only — **CC BY-NC and every other Freesound license are excluded** — with each
selected clip's own id, uploader, license and URL recorded individually in
`dataset_manifest.json`, rather than a blanket license inherited from a dataset as a whole.
Freesound's `/download/` endpoint (the original uploaded file) requires OAuth2 (verified:
returns HTTP 401 with only a token); token authentication reaches the public 128 kbps MP3
preview instead, so vehicle and animal_call audio is transcoded from Freesound's lossy preview
file, not the original upload. Freesound relevance is **uploader tagging, not expert
verification** — see Caveats.

### Normalization (all four sources)

- **8000 Hz mono**, matching Mendeley's native rate — the lowest of the four sources, so every
  other source is downsampled and none is upsampled. Resampling uses
  `scipy.signal.resample_poly` (anti-aliased), not stdlib `audioop.ratecv`: `ratecv` has no real
  anti-alias filter, and decimating ESC-50/Freesound's 44.1 kHz at roughly 5.5:1 without one folds
  high-frequency energy back down into exactly the low mel bands the DSP block reads — that would
  corrupt every non-Mendeley class's frequency content, not just add broadband noise.
- **4.0 seconds per clip**, centre-cropped or zero-padded. Chosen because it sits just under
  Mendeley's native 4.09 s clip length, so gunshot — whose transient position inside its clip is
  not annotated anywhere in the dataset — is never cropped and can never have its transient cut
  off; every other, shorter or longer, source is trimmed or padded to meet that length instead.

## Impulse

- **Input** (block 1): time-series, 1 axis (`audio`), 8000 Hz declared, 4000 ms window, 4000 ms
  stride (no overlap — one window per clip, so no window can span two clips or mix a class label
  with padded-in silence from a shorter source clip), zero-pad on.
- **DSP** (block 2): **MFE** (mel-filterbank energy), not MFCC. MFCC's cepstral truncation is
  built for speech, where the fine spectral detail it discards is formant structure a listener
  doesn't need. Here that same detail is exactly what separates a gunshot's broadband transient
  shape from a chainsaw's harmonic engine whine — both classes need the full mel-band energy
  profile MFE keeps, not MFCC's compressed cepstral coefficients. Spectrogram was the fallback if
  MFE underperformed. Block parameters are read back live and printed by the training script
  rather than asserted from documentation; none are overridden from their defaults.
- **Learn** (block 3): Keras classification, five classes, automatic class weighting (gunshot's
  747 against chainsaw's 40 is a real, reported imbalance — see Caveats), INT8 quantization
  profiled (`profileInt8: True`) to match this project's Cortex-M33 deployment target.

## Result

**Not yet trained.** Running `scripts/edge_impulse_upload_acoustic.py` requires
`FREESOUND_API_KEY` (not yet created) in addition to `EI_API_KEY` / `EI_PROJECT_ID`, and both
scripts require real internet access to Mendeley, GitHub and Freesound that this pass did not
have. This README will be updated with the real per-class held-out numbers — reported separately,
never averaged into one figure, since gunshot / chainsaw / vehicle / animal_call / ambient come
from four different recording contexts and four different sets of equipment and are expected to
perform unevenly — once both scripts have actually been run against a live project.

## Caveats — required whenever any number from this project is quoted

1. **None of this audio was captured on this project's own INMP441, and none of it is from Kerala
   forest conditions.** Every class comes from other researchers' or other users' recordings —
   different locations, different equipment, different years. This closes *"a 5-class acoustic
   model exists and is trained on real, licensed data,"* **not** *"this model works on real field
   audio from this project's own microphones."* Those two claims travel separately, and only the
   first one is true after this work.
2. **The elephant-rumble low end is not actually captured.** Rumble fundamentals sit at roughly
   8–34 Hz, well under the 8 kHz sample rate's Nyquist limit — but Nyquist was never the binding
   constraint. An MFE block's lowest mel band sits far above 34 Hz, so the model sees rumble
   harmonics and overtones, never the fundamental. This is consistent with the project's
   architecture rather than a defect in this pass — `/CONTEXT.md` scopes the INMP441 to
   frequencies above 60 Hz and gives low-frequency detection to the geophone instead — but it
   means `animal_call` here is not infrasound detection, regardless of how well it scores.
3. **Freesound clip relevance rests on uploader tagging, not expert verification.** There is no
   guarantee every clip returned for the `animal_call` query is actually an elephant rather than
   an unrelated recording that happens to be tagged or titled that way; clips were filtered by
   license, tag and duration, not listened through individually.
4. **Chainsaw is n=40 against up to 150 for every other class.** Its per-class number has to be
   read against that sample size, not compared at face value to the larger classes'.
5. **Ambient's train/test split is weaker than gunshot's.** Gunshot's two folders are the authors'
   own temporally-distinct collection sessions. Ambient only has one usable folder (see Dataset
   above), so its split is this project's own seeded chronological cut inside that one folder —
   not two independently-collected sets the way gunshot's are.
6. **Vehicle and animal_call are transcoded from Freesound's lossy 128 kbps MP3 preview, not the
   original uploaded file** (the original requires OAuth2, which this script does not implement).
7. **Not deployed.** No acoustic inference runs on this project's hardware. This closes the
   training half of the gap `docs/KNOWN_GAPS.md` records, not the deployment half — see that
   file's separate entry for exporting this model and wiring it into
   `handle_acoustic_event()`.

## Reproducing

```
export EI_API_KEY=ei_...          # project 1094275 API key, not stored in this repo
export EI_PROJECT_ID=1094275
export FREESOUND_API_KEY=...      # create at https://freesound.org/apiv2/apply/
python scripts/edge_impulse_upload_acoustic.py
python scripts/edge_impulse_train_acoustic.py
```

`ml/datasets/acoustic/raw/` (gitignored) caches downloaded and normalized audio so a re-run does
not re-fetch or re-query Freesound; `dataset_manifest.json` in this directory is committed and
records the exact clip selection — source, license, split, sha256 of the normalized payload — so
the dataset behind any future reported number is reproducible from a fresh clone even though the
raw audio itself is not, and even though a live Freesound search could return different results on
a later run.
