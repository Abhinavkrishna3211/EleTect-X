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
| `wcs-sus-scrofa` | 827 (828 on disk — see note below) | CDLA-Permissive-1.0 | LILA WCS Camera Traps — real field camera-trap, Indonesia (734) + Laos (94); genuine wild population, species-correct | **22.5% night/IR** — seeded 40-image sample (`scripts/audit_night_ir_sample.py`, seed 202609042), 9/40 genuine night-flash or dark-scene frames, the rest clear daylight; mostly colour night-flash rather than grayscale IR, unlike the other two sources audited the same pass | `Measured`, n=40 of 828 |
| `pig-rinoz/wild-pig-at-night/1` | 64 | CC BY 4.0 | Real trail-cam, multiple camera brands visible in-frame (Bushnell, Moultrie, "JonahCam") | **Confirmed real night/IR** — grayscale near-IR, 5/5 visually verified, no staged or daytime-relabeled frames | `Measured`, n=5 of 64 |
| `swg-eurasian-wild-pig` | 1,800 (2,350 on disk — see note below) | CDLA-Permissive-2.0 | Real field camera-trap set (the SWG collection also used for Background negatives); domain-correct primary Boar source by volume | **60% night/IR** — seeded 40-image sample (`scripts/audit_night_ir_sample.py`, seed 202609041), 24/40 genuine night-flash or grayscale-IR frames (mix of colour night-flash and true grayscale IR, both public-dataset and SWG-tagged frames), the rest clear daylight | `Measured`, n=40 of 2,350 |
| `pseudo-ir-boar` (synthetic) | 200 | N/A — derived from the real sources above | Synthetic pseudo-IR augmentation, not camera output | By construction, all 200 are synthetic night/IR-styled | `Measured` (it is what it says it is; not real capture) |
| **Total** | **7,394** | | | | |

**Night/IR proportions above, and the on-disk count discrepancy, measured 4 Sept 2026 (Boar-gap
close-out session, Step 4.1) — closing the two `UNVERIFIED`-proportion rows this table carried since
the audit's first pass.** `swg-eurasian-wild-pig` resolves on disk to `swg-camera-traps/
eurasian_wild_pig/` (2,350 files) and `wcs-sus-scrofa` to `wcs-camera-traps/sus_scrofa/` (828 files) —
both counted directly by listing the species subdirectory, not re-derived from `dataset_manifest.json`
or README prose. The manifest's 1,800/827 figures were not re-investigated as part of this pass; they
may reflect an EI-project-side filter (dedup, a prior exclusion pass) rather than an error in either
number, but that reconciliation is out of scope here — flagged as a follow-up, not resolved. Both
proportions come from `scripts/audit_night_ir_sample.py`, a sibling of `audit_boar_sample.py` written
this session: seeded sample (`random.Random`, not corpus order), rendered as boxed/unboxed contact
sheets under `ml/datasets/vision/raw/_audit_tmp/`, each image opened and judged by eye — same
discipline as trail-camera-v2's original 14-image sample, not an automated grayscale-pixel heuristic.
"Night/IR" here means the visual bucket that matters for this project's actual domain gap (RGB-daylight
training data vs. the deployed camera's grayscale-IR night output): both true colour night-flash frames
and true grayscale IR frames count as night/IR regardless of the EXIF-adjacent on-image timestamp,
since a few frames in both samples carried a daylight-looking timestamp while displaying a clearly
grayscale or flash-lit visual (a per-camera clock or metadata issue, not a lighting-condition
misjudgment) — the visual bucket, not the printed clock, is what the deployed camera's exposure pipeline
actually sees.

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

**Quantified, 4 Sept 2026 (Boar-gap close-out session, Step 4.1) — the "meaningful fraction" above is
72.5%, not a minority.** A seeded 40-image sample across `asian-elephants-dataset-v1`'s three splits
(`scripts/audit_night_ir_sample.py`, seed 202609043, `parse()`/`contact_sheet()` reused from
`audit_boar_sample.py` since this source carries real COCO boxes) found **29/40 genuine night/IR
frames** — heavily grayscale, true-IR camera-trap output (Bushnell/ScoutGuard/XTBS overlays visible in
several), not the exception the "species-correct supplement" framing implied. This is Elephant's
largest single source (2,358 of 4,094 total, 58%) and the finding materially changes the Elephant side
of this document's cross-class comparison: the earlier 267/4,094 (6.5%) confirmed-real-IR figure only
credited `wcs-elephas-maximus` and the night-ojblh fold-in, and did not include
`asian-elephants-dataset-v1` at all pending this quantification. At 72.5% of 2,358, this single source
alone contributes on the order of 1,710 more real night/IR Elephant frames than the earlier confirmed
figure credited — meaning Elephant's true night/IR share of its own corpus is almost certainly well
above Boar's corrected ~11% estimate, not below it. This reframes an assumption this document was
carrying since its first pass: Elephant was never the class starved of real IR content: Boar was, and
still is, even after trail-camera-v2 and the corrections above.

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

**Correction, 4 Sept, found by the execution session while planning the next retrain — read this before
treating the 0.863 number above as a standalone, reproducible data lever.** The deployed checkpoint
(0.852 Boar / 0.906 Elephant / 0.166 background FP) was itself already trained on the
post-`trail-camera-v2` corpus — the 0.863-Boar run differs from the deployed one **only by
`architecture-type`** (`attn_silu` vs the deployed `no_attn_relu`), on the same data and a
near-identical test split (1505 vs 1503 Boar test images). It is not an independent confirmation that
adding `trail-camera-v2` helps by itself; it is really a data point about the `attn_silu` architecture
variant, already folded into a corpus the deployed model also trained on. Concretely, "reproduce the
0.863 win" reduces to "redeploy with `attn_silu`," which trades **−2.6 points Elephant recall and +0.7
points background FP** for the Boar gain — a real, known, already-measured tradeoff that fails this
plan's own adoption bar (beat all three numbers, not trade one for another). Treat trail-camera-v2's
inclusion as settled and already banked in the deployed checkpoint, not as an unexploited lever still
worth "extending" — the real untried levers remaining are freeze-backbone and augmentation-strength
(see below), not a trail-camera-v2 reproduction. Anyone reading only the paragraphs above this
correction will draw the wrong conclusion — this note exists specifically to stop that.

**Second correction, same session — the 1.1-point gap above (0.863 vs 0.852) is close to the measured
run-to-run noise floor, not clearly outside it.** Two runs of the identical config on the identical
corpus (`_retrain_yolo_medium_20260829.log` job 53251711 vs `_retrain_yolo_medium_ship_20260829.log`
job 53254690 — same `customParameters`, same test split 1402/844/787, both cached 0.3-min feature
generation) differ by **1.5 points of Boar recall at threshold 0.5** (0.770 vs 0.755) with no
architecture or data change between them at all. That pair is suggestive rather than certified — no
README entry exists for the "ship" run, so a silent corpus edit between the two can't be fully
excluded — but it means a 1.1-point gap should not be read as a confirmed win without a noise-floor
measurement alongside it. The Boar-gap close-out session reruns the exact deployed config once,
unchanged, specifically to measure this floor at threshold 0.05 (the deployed operating point, not
0.5) before judging any of the levers above against it.

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

**Status, updated 4 Sept: one of the two blocking checks now has a real answer, and it's a likely
disqualifier — not yet closed out either way.**

1. **Species-table check — resolved, direct from the paper (arXiv 2511.15622v2), and it changes the
   practical read.** "Wild boar" is confirmed as one of the 99 species categories (Fig. 5's per-species
   video-count chart, read directly off the figure, not inferred). But it's a rare long-tail category
   within SA-FARI itself: **approximately 14 videos total** (train+test combined, out of 11,609 videos
   in the whole dataset — roughly 0.12%), putting it in the same low-count band as "giant armadillo"
   and "woolly monkey," well below the top-3 (spider monkey, collared peccary, agouti, each 700+
   videos). African elephant is confirmed present too, at a similarly modest ~10 videos. This does not
   disqualify SA-FARI — 14 videos of real, likely-IR-inclusive camera-trap boar footage (the dataset's
   night subset is 598 of 11,609 videos overall, so a meaningful fraction of SA-FARI generally is
   night; whether these particular 14 boar videos fall in that subset is not yet known and needs
   checking against the per-video metadata once/if access is granted) would still be a genuine,
   domain-matched addition — but it reframes SA-FARI from "the fix for the Boar gap" to "a small,
   high-quality supplement," which matters for prioritization against the licence question below and
   against continuing to look for other candidates in parallel rather than treating SA-FARI as
   sufficient on its own.
2. **Licence check — resolved, and it's a real problem, not a formality.** The dataset card states
   plainly: **License: CC-BY-NC 4.0** (Creative Commons Attribution-NonCommercial). This is Meta's
   stated licence for the data itself, not a restriction this project is imposing — and it is a
   meaningfully different tier from every other source in this project's corpus, all of which are
   CC0, CC BY (fully commercial-permissive), or CDLA-Permissive. NC terms restrict use "primarily
   intended for or directed toward commercial advantage" — whether training a detector on SA-FARI
   images and shipping the resulting model weights inside a manufactured device for a DFO field trial
   crosses that line is a real legal question this document is not qualified to answer for the
   project (not a lawyer, not reading this off general CC-BY-NC boilerplate as a verdict) — it needs
   a human read of the exact clause against how this specific device is being distributed/funded
   before any SA-FARI-derived data or weights go anywhere near the shipped model. **Do not proceed on
   the assumption this clears the same rejection bar as the CC0/CC-BY/CDLA sources already in the
   corpus — it does not, until that question is actually answered.**

Given (2), the practical next step is no longer "confirm species then use it" — it's "get the NC
question answered first," since a "no" there makes the ~14-video species-table finding above moot for
this project's shipped model (SA-FARI could still be legitimate for internal research/benchmarking
use, which NC permits, even if not for the deployed device — worth keeping that distinction in mind
rather than discarding the source outright). And given the scale finding in (1), even a "yes" on the
licence question makes SA-FARI a small supplement worth pursuing alongside continued sourcing, not a
substitute for it.

**NC question answered, 4 Sept — by the project owner, not a legal conclusion this document derives.**
The project owner has determined CC-BY-NC 4.0 is compatible with this project's distribution and
funding model for the shipped device, clearing SA-FARI-derived data/weights past the point this
document flagged above. That determination is recorded here as an attributed decision, not as this
audit's own legal reasoning — the caveats above about NC's "commercial advantage" language remain
accurate background for why the question needed asking. Clearing the licence does not waive the rest
of the checklist: file integrity, label correctness by eye on all 14/14 boar videos (not a sample),
the real night/IR count specifically among those 14 (not SA-FARI's dataset-wide 598/11,609
proportion), mask-to-box tightness, and a train/test tracklet-leakage check all still gate any actual
training use, each with a written report before the data touches a training job.

**Six-point checklist, completed 4 Sept — first correction: the video count itself was wrong.**
The "~14 videos" figure above came from reading the paper's per-species chart (Fig. 5) by eye, hedged
as approximate at the time. Direct verification against the primary annotation data supersedes it.
`sa_fari_{train,test}_ext.json` (HF-gated, fetched with a granted-access token; the actual frames are
unauthenticated and served from the public GCS bucket `cxl-public-camera-trap` named in the dataset's
own README) carry a global, open-vocabulary noun-phrase category table shared across all three SA-FARI
domains. Two category ids both resolve to *Sus scrofa* in that table's own taxonomy fields: id 111
"pig" and id 43640 "wild boar". Counting `video_np_pairs` with `num_masklets > 0` for either id, across
both splits: **15 distinct videos, not 14** — 7 in test, 8 in train, no video-name overlap between the
two sets. Fourteen are annotated "wild boar", one ("sa_fari_009245", train) is annotated "pig" but is
visually the same species doing the same thing (see below) — correctly a different noun-phrasing of
the same animal, not a mislabel.

1. **File integrity — pass.** A seeded sample of 6 frames per video (90 total, every video represented,
   not a sub-sample of videos) fetched cleanly from the GCS bucket; no corrupt or missing JPEGs.
2. **Label correctness by eye on 15/15 boar videos (not a sample) — pass, with two flagged as marginal.**
   Boxes were rendered on the sampled frames (`scripts/audit_sa_fari_boar_sample.py`) and opened by eye,
   video by video. 13/15 show an unambiguous boar (clear body silhouette or, in five daylight videos,
   full-colour confirmation down to bristled coat and snout shape) with boxes that track the animal
   tightly, including through partial frame-edge occlusion. Two are genuinely marginal:
   `sa_fari_000820` (test) and `sa_fari_004160` (train) show only a faint, small dark shape at long IR
   range — consistent with a boar but not confidently distinguishable from any other dark shape at that
   resolution by eye alone. Both are flagged, not excluded; a training pass should weight or drop them
   rather than treat all 15 as equally strong labels.
3. **Real night/IR count among the 15 — measured, not the dataset-wide 598/11,609 figure.** 5/15 = 33%:
   `sa_fari_000066`, `sa_fari_000153`, `sa_fari_000820` (test), `sa_fari_004160`, `sa_fari_007410`
   (train). Three are clearly IR-lit (grayscale, visible flash falloff or eyeshine); the other two are
   the same pair flagged as visually marginal in point 2. The remaining 10/15 are full-colour daylight
   or dusk footage. 33% night/IR is a real, if small, improvement on this project's own corpus mix for
   Boar (60% for `swg-eurasian-wild-pig`, 22.5% for `wcs-sus-scrofa`, quantified above) only in the
   sense that it adds genuine IR frames outside those two sources' geography — it does not itself close
   the gap at n=5.
4. **Mask-to-box tightness — pass, quantified.** Comparing each frame's segmentation-mask area against
   its bounding-box area (`bboxes` width×height) across all 1,217 annotated frames in the 15 videos:
   median fill 0.69, mean 0.68, p10 0.57, p90 0.81, and — the check that actually matters for catching a
   broken converter — zero frames where mask area exceeds box area, and only 6 frames (0.5%) with fill
   below 0.15. That distribution is exactly what a tight box around an irregular quadruped silhouette
   should look like; nothing here suggests SA-FARI's boxes are loose or its masks malformed.
5. **Train/test tracklet-leakage check — pass, clean.** The 7 positive test videos come from locations
   `campo9`/`campo4`/`campo2`; the 8 positive train videos come from `campo3`/`campo5`. No location
   overlap at all between the two sets, so there is no case of one continuous boar encounter being cut
   across the train/test boundary the way this engagement has already found and fixed twice with other
   sources.
6. **This section is the written report**, filed before any SA-FARI frame has touched a training job,
   per the checklist's own requirement.

**Net read**: SA-FARI's boar data is real and reasonably clean — passes 5 of 6 checks outright, with
point 2 producing an honest caveat (2 of 15 videos are visually marginal) rather than a blanket pass.
At 15 videos it remains the "small supplement, not the fix" framing from point 1 above, now on a
verified rather than approximate count. Converting it into training-ready image+box pairs (frame
extraction from the sampled or full 180-frame tracklets, one image-space annotation per usable frame)
is a separate step this pass did not do — nothing from SA-FARI is in the training corpus yet.

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

**Correction, 4 Sept, execution session — the paragraph below is now stale on two counts and is kept
only so the historical reasoning is legible; read the bullets after it instead.** `augmentationPolicyImage`
being "hardcoded to `all` with no CLI override" is misleading, not wrong: that generic Keras field is
inert for YOLO-Pro, an org model that reads its own `spatial-augmentation`/`color-space-augmentation`
customParameters instead — both were sitting at `low` (the weakest setting) in every run this
engagement, never varied, which is the actual untried lever. And the "would need a new flag" framing
for freeze-backbone is now done: `--freeze-backbone`, `--spatial-augmentation`, and
`--color-space-augmentation` were added to `scripts/edge_impulse_train_vision.py` this session,
threaded into `select_model()`'s YOLO-Pro branch and validated against the model's own live
`customParameters` (not a hardcoded tuple), so a renamed level fails loudly rather than training
silently on an unintended value.

Confirmed live 4 Sept via `GET /transfer-learning-models` (project 1097972) — the real allowed values,
not assumed:

- **`freeze-backbone`** — a flag, `true`/`false`, model default `false` (matches every run to date;
  never flipped). Only applicable when `use-pretrained-weights` is `true`, which every YOLO-Pro run
  this engagement has used. **Low prior for a win**: freezing the backbone removes exactly the
  adaptation a heavily domain-shifted target (RGB daylight → grayscale IR) needs from pretrained
  ImageNet weights. Cheap to falsify — freezing most of the network trains faster — so worth running
  even at a low prior.
- **`spatial-augmentation`** — select, ladder `none` < `low` < `medium` (`+RandomRotation & RandomFlip`)
  < `high` (`+Mosaic`), model default and every run to date at `low`. Addresses scale/crop/framing
  variance, not the IR domain gap directly.
- **`color-space-augmentation`** — select, same `none`/`low`/`medium`/`high` ladder (increasing levels
  of RandAugment), model default and every run to date at `low`. **Highest prior of the three**: this
  is the knob that targets a colour/appearance domain shift specifically, and the deployment gap is
  exactly an RGB-daylight → grayscale-IR shift.

Both augmentation knobs and freeze-backbone are real candidates for whenever a retrain is next
authorised; naming them here does not authorise one on its own — see the Boar-gap close-out session's
own plan for the trial ordering and adoption bar.

## What this document is not

This is a characterization and sourcing plan, not a retrain, and not a claim that any number above
changes the currently deployed checkpoint's real, measured recall (0.852 Boar / 0.906 Elephant /
0.166 background FP rate, live-verified on hardware). The corrected ~11% night/IR estimate is itself
an extrapolation from a 14-image sample in one source, not a re-audit of the full 7,394-image corpus —
a genuine full audit, tagging every source against the proposed schema, is future work this document
recommends but does not attempt.
