# Boar representation audit and sourcing plan

**4 Sept 2026. Docs-only — no retrain, no new data pulled.** This closes out Workstream 2 of the
"close the Boar detection gap" plan, deliberately sequenced behind the ship-relevant work (the
per-poll Boar debounce and the exposure-lock fix) because it produces no field capability on its own.
It also respects a standing decision recorded earlier in this engagement to stop vision-tuning trials
and pivot to hardware bring-up — this document does not reopen that; it is characterization and
sourcing groundwork for whenever a retrain is next authorised, not a retrain.

Everything below is read from `ml/vision/dataset_manifest.json` (the source of truth for counts) plus
`scripts/edge_impulse_upload_vision.py`'s `DATASETS` entries and `ml/vision/README.md`'s dated
narrative (the only place per-source *condition* detail exists today, as prose). Confidence is stated
per claim — a lot of what follows is a small visually-verified sample extrapolated, not a census, and
that distinction is preserved rather than smoothed over.

## The blocking finding this audit exists to work around

**No source in this project carries structured condition metadata.** `dataset_manifest.json` records
per-source counts, licenses, and drop reasons — nothing else. `DATASETS` records the same, plus a free
-text comment where whoever added the source happened to write one. There is no `ir`, `lighting`,
`day_night`, `angle`, `distance`, or `occlusion` field anywhere in either place. Day/night provenance
today exists only as prose buried in README narrative and `DATASETS` comments, plus implicit filename
prefixes (`s1_`–`s4_` for the board's own captures, `af_`/`as_` for species-contamination flags) that
were never meant as a condition taxonomy. This audit is therefore a manual reconstruction from that
prose, not a query against real fields — and a proposed schema (below) is the deliverable meant to
close that gap for future sourcing passes.

## Corrected headline: the 0.87% figure undercounts real night/IR Boar imagery

`docs/KNOWN_GAPS.md` and this file's own `README.md` Dataset table currently state real night/IR Boar
imagery at **64 images — 0.87% of 7,394** (`pig-rinoz/wild-pig-at-night` only, the sole source with
"night" in its own name). That number is an honest read of the manifest's `real`/`synthetic` split —
but the manifest has no IR/lighting field, so it silently equates "the only source *named* for night"
with "the only source *containing* night imagery." It does not hold up against `DATASETS`' own
sourcing notes, and should be corrected:

- **`roboflow-100/trail-camera/2` (`trail-camera-v2`, 1,311 images) is documented, in its own
  `DATASETS` entry, as "real Cuddeback-brand US game-camera trail imagery, **day + IR-night**."** A
  seeded 14-image visual sample (seed 20260829, opened by eye with boxes rendered) found **8 of 14
  (57%) were real night/IR trigger frames, timestamps spanning 12:18 AM–11:07 PM.** This was never
  split into its own IR-labelled source or field — it rode in as part of the plain Boar count.
  Proportionally extrapolating that 57% sample rate across all 1,311 images gives a rough estimate of
  **~750 additional real night/IR images** — `UNVERIFIED, estimated from an n=14 sample, not a
  census`, but a real and documented finding, not a guess from nothing.
- **`swg-eurasian-wild-pig` (1,800 images)** — a 29 Aug 30-image spot-check (real, independent of the
  trail-camera-v2 finding above) explicitly found "genuine night/IR camera-trap frames... distant/
  low-contrast animals against dark IR backgrounds," naming one example as "a textbook Bushnell night
  frame of a wild pig at 3840×2880." The proportion was not quantified in that pass — recorded here as
  a real but uncounted additional night/IR contribution, not folded into the estimate below.
- **`wcs-sus-scrofa` (827 images)** — the same spot-check language ("close-range flash blowout, fog")
  is consistent with night-flash camera-trap capture but was not confirmed as IR either way. Flagged,
  not counted.

**Corrected estimate: real night/IR Boar imagery is closer to 64 + ~750 ≈ 814 images, roughly 11% of
7,394 — not 0.87%.** This is still a real minority, and the extrapolation itself rests on a 14-image
sample from one source, so 11% is better read as a floor than a precise figure — the two additional
uncounted sources above mean the true number is probably somewhat higher still. `docs/KNOWN_GAPS.md`
and `README.md`'s Dataset table are being corrected alongside this document; see their entries for the
in-place fix rather than duplicating it here.

**Why this matters and why it doesn't change the practical picture.** Even at the corrected ~11%,
night/IR Boar coverage remains far below proportional given the deployment target is a night-IR
camera. The corrected number changes the *scale* of the gap, not its *existence* — it is a smaller
problem than "64 images, essentially nothing" implied, but still a real and load-bearing one. It also
means the manifest-only method used to produce the original 0.87% figure is not a reliable audit tool
on its own; the proposed `conditions` schema below exists specifically to stop this kind of blind spot
recurring the next time someone asks "how much night/IR data do we actually have."

## Per-source Boar breakdown

All counts read directly from `dataset_manifest.json` (`classes.Boar.sources`), confirmed matching
`README.md`'s Dataset table. Condition columns are reconstructed from `DATASETS` comments and README
narrative; `Confidence` states what that characterization actually rests on.

| Source | Images | License | Domain | Day/night, IR | Confidence |
|---|---|---|---|---|---|
| `trackabox-4ejy9/wild-boar-a1flm/1` | 1,556 | CC BY 4.0 | Mixed — scraped/catalog Roboflow set, relabelled from "Pig"; documented contamination (domestic pig in a straw-lined pen, TV-broadcast clip frames both filtered) | Not characterized for day/night; no IR mention in any pass | `UNVERIFIED` — multiple visual-contamination passes exist (n≈40+9+17), none coded for lighting |
| `boarwatch/wild-boar-deterrent-pzq5t/1` | 1,636 | CC BY 4.0 | Catalog-style sequential-ID Roboflow set, relabelled from class `"0"`; documented contamination (black redaction rectangles, TV-broadcast clip frames, vegan-food-brand imagery both filtered) | Not characterized for day/night; no IR mention | `UNVERIFIED`, same basis as above |
| `roboflow-100/trail-camera/2` (`trail-camera-v2`) | 1,311 | CC BY 4.0 | Real US game-camera (Cuddeback), *Sus scrofa* under the "Hog" category — genuine field camera-trap domain, closest domain match to Kerala's deployment among all Boar sources | **Day + IR-night** per its own `DATASETS` entry; 8/14 (57%) of a real visual sample were night/IR trigger frames | `Measured`, n=14 visual sample, extrapolated for the corpus-wide estimate |
| `wcs-sus-scrofa` | 827 | CDLA-Permissive-1.0 | LILA WCS Camera Traps — real field camera-trap, Indonesia (734) + Laos (94); genuine wild population, species-correct | Not confirmed IR; "close-range flash blowout, fog" in a 10-image sample is consistent with but not proof of night-flash capture | `UNVERIFIED` for lighting; domain and species are `Measured` |
| `pig-rinoz/wild-pig-at-night/1` | 64 | CC BY 4.0 | Real trail-cam, multiple camera brands visible in-frame (Bushnell, Moultrie, "JonahCam") | **Confirmed real night/IR** — grayscale near-IR, 5/5 visually verified, no staged or daytime-relabeled frames | `Measured`, n=5 of 64 |
| `swg-eurasian-wild-pig` | 1,800 | CDLA-Permissive-2.0 | Real field camera-trap set (the SWG collection also used for Background negatives); domain-correct primary Boar source by volume | Real night/IR frames confirmed present in a 30-image spot-check (e.g. a 3840×2880 Bushnell night frame) but not quantified | `Measured` that it exists; proportion `UNVERIFIED` |
| `pseudo-ir-boar` (synthetic) | 200 | N/A — derived from the real sources above | Synthetic pseudo-IR augmentation, not camera output | By construction, all 200 are synthetic night/IR-styled | `Measured` (it is what it says it is; not real capture) |
| **Total** | **7,394** | | | | |

## Cross-class contrast with Elephant

Elephant's manifest total is 4,094 images across 5 sources — 1.8× smaller than Boar's 7,394. Its
documented real IR sources are `wcs-elephas-maximus` (194 images, "species-correct, box-verified,
genuine night-hour coverage") and `wild-boar-fmkcg/night-ojblh/1` (73 images, "genuine thermal
camera-trap output... farm-perimeter domain match" to this project's own deployment context, 12-image
sample confirmed by eye). That is 267 confirmed real night/IR images out of 4,094 (6.5%) — already
higher, on a confirmed basis, than Boar's *confirmed* 64/7,394 (0.87%), though not necessarily higher
than Boar's corrected estimate (~11%) once trail-camera-v2's undercounted content is folded in.

The same undercount risk applies to Elephant, not just Boar, and should be read as a limitation of
this whole audit method rather than a Boar-specific problem: a 29 Aug spot-check of
`asian-elephants-dataset-v1` (2,358 images, Elephant's largest single source) explicitly found "a
meaningful fraction... turned out to be genuine night/IR camera-trap frames (grayscale, IR
illumination, real Bushnell/ScoutGuard/XTBS trail-cam overlays)" that the source's original "species-
correct supplement" framing did not credit. Neither class's true night/IR fraction is fully known
today — both are undercounted by roughly the same mechanism (real IR content riding uncredited inside
a source labelled and budgeted as generic daytime photography), which is exactly the case the proposed
`conditions` schema below is meant to close for good, for both classes, not just Boar.

Background's own real-IR coverage is `board-captures-night1` — 207 real IR frames from the deployed
camera itself, four physically distinct framings, true negatives rather than positives. It is the only
source in the whole corpus captured on the project's own hardware rather than sourced externally.

## Why volume is the wrong lever

Boar already has 1.8× Elephant's image count and a *worse* held-out recall — 0.852 vs 0.906 at the
deployed threshold-0.05 checkpoint, 6.8 points short of the ≥92% bar against Elephant's 1.4. More
catalog-style Boar images would not close that gap; the engagement's own data already demonstrates
this two ways:

- **Domain-match data was tried once, and it worked — at the deployed operating point.** Folding in
  `trail-camera-v2` (the real, day+IR-night camera-trap source above) and retraining on `medium`
  sizing produced **0.863 Boar recall at threshold 0.05 — the best Boar recall of the whole
  engagement**, ahead of the eventual deployed checkpoint's 0.852. State the honest caveat alongside
  it: at the *fixed default* threshold of 0.5, the same before/after comparison read flat-to-slightly
  worse (0.770 → 0.762), most plausibly a test-set-composition confound (the held-out Boar test set
  grew from ~787 to 1,505 images the same pass) rather than the new data hurting — but that reading is
  the more charitable of two honest possibilities, not a confirmed one. At the deployed 0.05 threshold,
  the domain-match win is real and is the largest single Boar-recall gain in the whole 26 Aug–3 Sept
  record.
- **Capacity stopped helping for Boar two steps before it stopped helping for Elephant.** The
  `nano`→`large` capacity ladder closed 5.6 points on Boar and 4.5 on Elephant, but Boar plateaued at
  `medium`→`large` (0.762, marginally *worse* than `medium`'s 0.770) while Elephant kept improving
  (0.826, its best capacity-ladder result). More parameters were not the fix once tried.

Both results point the same direction: the lever that has already shown a real, measured gain for Boar
is domain-matched real camera-trap data (trail-camera-v2's 0.863), not more images of any kind or more
model capacity. This is the case for prioritising night/IR-heavy camera-trap sourcing over any
volume-only pull.

## Proposed `conditions` metadata schema

To stop future audits from repeating this document's own reconstruction-from-prose method, propose
adding a `conditions` block to each `DATASETS` entry and mirroring it into
`dataset_manifest.json`'s per-source records, populated going forward (not backfilled for existing
sources as part of this pass — that would itself be a data-quality project, not a schema change):

```python
"conditions": {
    "domain": "camera-trap",       # "camera-trap" | "staged-or-stock" | "own-capture" | "synthetic" | "mixed"
    "lighting": "ir-night",        # "daylight" | "ir-night" | "mixed" | "unknown"
    "ir_confirmed": True,          # bool — actually visually verified as IR, not inferred from a name
    "sample_verified_n": 14,       # size of the visual sample the lighting/domain call rests on
    "sample_verified_of": 1311,    # total images in the source, for computing coverage of the claim
    "angle": "ground-level",       # "ground-level" | "aerial" | "handheld" | "unknown"
    "distance": "near",            # "near" | "far" | "mixed" | "unknown"
    "occlusion": "low",            # "low" | "moderate" | "high" | "unknown"
}
```

`sample_verified_n`/`sample_verified_of` exist specifically so a future reader can see at a glance that
a "day + IR-night" tag rests on 14 of 1,311 images, not a census — the same distinction this document
had to reconstruct by hand from README prose. An `unknown` value is a legitimate, honest default; the
schema's job is to make gaps visible, not to force premature characterization.

## Sourcing plan: closing the real night/IR gap

**Lead candidate: SA-FARI** (Conservation X Labs × Meta, released Nov 2026, arXiv 2511.15622,
`conservationxlabs.com/sa-fari`). 11,609 real camera-trap videos, 741 locations, 2014–2024, 99
species, 942,702 boxes plus segmentation masks, 16,224 masklet identities. It is the best public match
to this specific gap for three reasons: it is camera-trap domain by construction, not stock imagery;
it explicitly includes IR night footage ("IR flash invisible to the species of interest") with a named
598-video night test subset — the exact modality where Boar is real-but-thin even after this audit's
correction; and one of its five contributing institutions is the Institute for Game and Wildlife
Research (IREC, Spain), whose camera-trap work centres on Eurasian wild boar. African elephant is
confirmed present (~3.3 masklets/video), so the same source could plausibly help close Elephant's own
undercounted night/IR gap too.

**Status: candidate, not sourced — two blocking checks remain open, both need a logged-in Hugging Face
session:**

1. The paper's 99-category species list does not name *Sus scrofa* anywhere reachable without
   authentication — confirm boar is actually in the species table before assuming it is usable at all.
2. Read the dataset's own licence terms directly off the page, the way ADR 0016 read each Freesound
   page rather than trusting a snippet — "no paywalls, no restrictions" is website copy, not a licence,
   and this project ships a manufactured device, so redistribution terms matter concretely.

Real conversion cost if it clears both checks: SA-FARI is a video dataset with masks and tracklets, not
static images — using it means frame extraction, mask-to-box conversion, and a sampling policy that
does not let near-identical consecutive frames of one animal land in both train and test (the same
class of leakage this engagement has already found and fixed twice with other sources). Its tracklets
are also, as a secondary benefit, the only public corpus that could test whether the Workstream 1
consecutive-poll debounce actually suppresses camera-trap false positives on *labelled* data, rather
than only against this project's own unlabelled 2-hour log.

**Same rejection bar as prior sourcing passes applies to any Boar candidate found next**: this
engagement rejected `praveenmn75/elephant-thermal` for a baked-in WhatsApp notification banner proving
it was a phone screen-recording of a forwarded video, not licensable original camera output. A Boar
source with an equivalent tell should be rejected the same way, not waved through because Boar's gap
is more acute.

## Untried levers — named as next trials, not work done

Neither lever below has been tried this engagement, and neither is reachable from
`scripts/edge_impulse_train_vision.py` today without adding a flag first — confirmed by reading the
script's own argument parser: it exposes `--family`, `--yolo-variant`, `--yolo-sizing`, `--image-size`,
and `--batch-size`, and `augmentationPolicyImage` is hardcoded to `"all"` with no CLI override; YOLO-Pro
reads its epoch count and learning rate from its own org-model `customParameters`, not from a script
flag either.

- **Freeze-backbone.** Untried. Would need a new flag threaded into `training_params()`'s
  `custom_params` dict for the YOLO-Pro family, and confirmation that the platform's transfer-learning
  API actually exposes a freeze knob for this model family before wiring it — not confirmed either way
  yet.
- **Augmentation strength.** Untried beyond the corpus-wide `"all"` default. Would need the same kind
  of flag, and a decision on whether to vary it per-class (Boar only) or globally — object-detection
  augmentation policy in this API is set once per training job, not per label, so a per-class version
  would need to run as two separate training passes on filtered corpora, not a single job.

Both are real candidates for whenever a retrain is next authorised; this document does not authorise
one on its own.

## What this document is not

This is a characterization and sourcing plan, not a retrain, and not a claim that any number above
changes the currently deployed checkpoint's real, measured recall (0.852 Boar / 0.906 Elephant /
0.166 background FP rate, live-verified on hardware). The corrected ~11% night/IR estimate is itself
an extrapolation from a 14-image sample in one source, not a re-audit of the full 7,394-image corpus —
a genuine full audit, tagging every source against the proposed schema, is future work this document
recommends but does not attempt.
