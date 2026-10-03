# Fox representation audit and sourcing plan

> **Outcome settled 29 Sept 2026 — Fox is a permanent class.** This document's conclusion, that no
> Fox checkpoint was good enough to promote, held only at 96–128 px. At 160 px with the node's own
> hard negatives in training, Run F cleared the bar and replaced the three-class champion. `Fox` is
> a live detection class on deployed nodes and is not under review: the sources below are
> load-bearing training data, not a research branch, and the label stays in the corpus, the impulse
> and the runtime. References below to `etx_cpu_final_0830.eim` as "the
> currently-deployed champion" describe 13 Sept, not today — the deployed artifact is
> `runF_res160_noattnrelu_int8.eim`. The sourcing analysis itself stands and is what the
> retrain drew on; see the last entry in [`README.md`](README.md). Body left unedited below.

**13 Sept 2026. Docs-only — no upload, no retrain, no EI project mutation.** This closes the
external-sourcing half of the Fox-class addition (own-capture half already built by
`scripts/build_fox_encounter1_vision.py`, see below). It mirrors `boar-representation-audit.md`'s
method exactly: read the Roboflow project metadata directly (not the export's post-augmentation
counts), draw a seeded by-eye sample, state confidence as `Measured (n=X of Y)` against
`UNVERIFIED`, and record negative results with the same rigor as positive ones.

## Why this class exists

`docs/KNOWN_GAPS.md` encounter `20260911T203127`: a fox or golden jackal, visually confirmed on
frame review (gait, build, snout shape), was labeled "Boar" by the currently-deployed
two-class model. The animal was real, present, and correctly localized by the detector's own
boxes — only the species label was wrong. That encounter is the sole own-capture Fox source
(`board-captures-fox-encounter1`, 13 frames, built and audited in a prior window; recap below) —
real signal, but nowhere near enough alone to teach a class. This document is the sourcing pass
that finds out whether openly-licensed external imagery can responsibly supplement it.

## Method

Four Roboflow Universe candidates were pulled (CC BY 4.0 throughout, matching the manifest's
license conventions): `mgr-l8rhf/fox-sldyl`, `testing-uutoy/fox-detector-dataset`,
`ml-dlq4x/fox-iav0z`, `deepnetworkdevelopment/fox-detection-7iqxq`. For each, a seeded sample was
drawn with `random.Random(SPLIT_SEED)` (`SPLIT_SEED = 20260822`, the same constant
`edge_impulse_upload_vision.py` uses for the train/test split, reused here only for a reproducible
non-cherry-picked sample list) over the set of distinct real source images — `group_key_exact()`
was used to collapse Roboflow's own `_jpg.rf.<hash>` export-augmentation duplicates back to one
entry per real photo before sampling, so an n below is a count of distinct real images, not export
files. Every sampled image was opened and read by eye; no automated classifier was used to vet
species. Counts below distinguish the Roboflow *project* image count (the real, pre-augmentation
source) from the *version export* count (post-augmentation, what a naive `images` field in an
API response would suggest) — the two differ by 3x-4x for two of the four sources because Roboflow
applies rotate/flip/grayscale/noise/blur augmentation at export time, and only the project count is
the meaningful "how many real photos exist" number.

## Per-source Fox breakdown

| Source | Project images (real) | Export images | License | Sample | Confidence |
|---|---|---|---|---|---|
| `deepnetworkdevelopment/fox-detection-7iqxq` | 100 | 100 (no augmentation) | CC BY 4.0 | 35/100 (35%) | `Measured` |
| `mgr-l8rhf/fox-sldyl` | 605 (36 unannotated; 567 distinct images physically found in the local export) | 1,501 (3x + grayscale/noise/flip/blur augmentation) | CC BY 4.0 | 70/605 (11.6%), two independent seeded draws | `Measured` |
| `testing-uutoy/fox-detector-dataset` | 584 | 584 (no augmentation) | CC BY 4.0 | 35/584 (6.0%) | `Measured` |
| `ml-dlq4x/fox-iav0z` | 152 | 456 (3x + rotate/saturation/flip augmentation) | CC BY 4.0 | 35/152 (23%) | `Measured` |

### `deepnetworkdevelopment/fox-detection-7iqxq` — by far the cleanest source found

**35/35 sampled, zero confirmed species contamination.** Every animal across the full sample is a
genuine red fox (*Vulpes vulpes*), including several individuals whose unusual coat color could
plausibly be second-guessed at a glance but are not a different species — a cross fox and a
cinnamon/near-white color morph, both still *V. vulpes*. This is the only one of the four sources
with a clean sample.

Two non-rejection caveats, stated plainly rather than smoothed over:

1. **One non-photographic image.** Filename `e22a47b26f9abbf36415f77d4546e381` is a realistic
   oil/digital painting of a fox at a water's edge — not a photograph. This is exactly the
   `tv_broadcast`/non-photographic contamination category the sourcing brief warned about, found
   once in this sample. **Excluded by filename** (see Disposition).
2. **Stock-photography / wildlife-photography domain, not camera-trap.** Multiple images carry
   named-photographer watermarks (Megan Lorenz, Bettina Mertens / CATERS NEWS, roeselienraimond.com,
   "Iza Łysoń Arts", "John D. Bruns © 2011") — species-correct throughout, but this is a
   professionally-photographed stock pool, not field camera-trap output. Domain mix within the
   sample: predominantly daytime and dusk/snow-daylight, one clear night-flash urban frame
   (`dd1dd77565db466b15b1265aba4d69df`, fox on paving stones at night — the only unambiguous
   night/IR-adjacent image in the sample, **1/35 = a floor estimate, not a census**), and two
   images that are legitimate species but non-wild-context: a fox on a kitchen counter
   (`b6a77cc72cb4d71811214aa532518565`, habituated/pet context) and a fox being hand-fed by a
   person. None of these are grounds for exclusion — they are real foxes — but they mean this
   source teaches "what a fox looks like" far better than "what a fox looks like on a night-IR
   trail camera," which is the deployment condition that actually matters.

**Disposition: ADOPT, excluding the one painting.** 99 of 100 real images. This is the strongest
single Fox source found — clean species labels are the one thing that cannot be recovered after
the fact, and no other candidate cleared even a third of this bar. The daytime/stock-domain skew is
a real, load-bearing gap this source does not close — carried forward explicitly below.

### `mgr-l8rhf/fox-sldyl` — genuine trail-camera/video provenance, best night/IR coverage, two confirmed contamination events plus a new shared-pool lead

**70/605 sampled across two independent seeded draws** (`SPLIT_SEED = 20260822` for the first
35-image draw; a deliberately different `random.Random(20260913)` for a second, disjoint 35-image
draw over the 533 images the first draw had not touched — a genuine follow-up sample, not a
reproduction). This is the only one of the four sources that reads as genuine field capture rather
than a stock-photo or catalog scrape: Bushnell and Browning trail-camera EXIF-style timestamp
overlays, a German-language camera-trap naming convention (`Cam1_Fuchs` through `Cam6_Fuchs` —
"Fuchs" = fox), at least four visually distinct branded-overlay camera-trap provenance clusters
(`KAROL01`/Browning, `GORDIEXD02`, `distianert`, unbranded `CAMERA1`-`CAMERA7` Browning-style
multi-camera deployment, plus a separate UK/Irish-style mountain-scree deployment with no brand
overlay), and video-frame extractions (`frame_NNN`/`frame_NNNNNN`, `frime-NNNN-`,
`vlcsnap-YYYY-MM-DD`, `WhatsApp-Video`, and — new in the second draw — one `yt-<11-char-ID>` frame
confirming at least one clip was re-uploaded from YouTube rather than captured directly).
Roughly a third of the combined 70-image sample are genuine night/IR captures — markedly higher
than any of the other three sources — though this is `Measured (n=70 of 605)`, not a census, and
should still be read as a floor.

**Two confirmed species-contamination findings, not one.**

1. **The `KAROL01` raccoon burst, now confirmed across seven frames, not three.** The first draw
   found three frames (`frame_1559`, `frame_1823`, `frame_914`) from one Browning camera scene —
   `KAROL01`, `03/12/2018 05:30AM` — showing two animals on a fallen log with stocky, ringed-tail
   bodies and behavior consistent with raccoons (*Procyon lotor*), not foxes and not even the same
   family (Procyonidae vs. Canidae). The second draw pulled four more frames of the *exact same*
   timestamped scene (`frime-155-`, `frime-1615-`, `frime-1634-`, `frime-1696-`): all four show the
   same log, the same two animals — a rounder, hunched-shaped animal on the left consistent with the
   confirmed raccoon, and a slimmer, pointed-eared animal on the right that reads as a genuine fox
   sharing the frame with it. A targeted adjacency check (5 frames read outward from the three
   original raccoon filenames — `frame_1545`, `frame_1815`, `frame_1816`, `frame_1837`,
   `frame_000928`) found no *further* spread: all five are clean, unambiguous red foxes. Read
   together, this is one substantial, well-bounded camera-trap event (at least 7 sampled frames, one
   fixed scene, one timestamp) rather than scattered contamination — but it is bigger than the first
   draw suggested, and it likely mixes a genuine fox frame with a raccoon frame at the same
   site, which matters for a per-image (not just per-event) exclude list. The same `KAROL01` camera
   also produced a clean, single-animal, unambiguous fox frame at a *different* time
   (`frime-1715-`, `03/09/2018 10:38AM` — 3 days earlier, broad daylight) — confirming the camera
   itself is a legitimate fox site, not a mislabeled non-fox deployment.
2. **A new, independently confirmed coyote, unrelated to the raccoon event.**
   `d1084d21b143e46d` (second draw) is a clear, unambiguous daylight photograph of a coyote
   (*Canis latrans*) beside a barbed-wire fence in open rangeland scrub — not IR, not motion-blurred,
   not a borderline call. This is the first *confirmed* (not merely suspect) contamination in this
   source that is not the raccoon event, and it carries a bare-16-lowercase-hex filename
   (`d1084d21b143e46d`) — the exact naming convention already confirmed to mark the shared, noisy
   scrape pool rejected under `testing-uutoy`/`ml-dlq4x` above (see the new shared-pool lead below).

**The coyote-like WhatsApp cluster is upgraded from `suspect, unresolved` to `likely coyote,
single event`.** The first draw sampled one frame from `WhatsApp-Video-2024-02-14-at-5_05_03-PM_mp4`
(`-0017`); the second draw pulled four more frames from the identical clip (`-0023`, `-0032`,
`-0042`, `-0109`). All five frames show the same individual animal on the same `GORDIEXD02`-branded
trail camera (`09/23/2019`, `75F`, consistent overlay across all five) — and across all five
independent views (side, front, three-quarter) the animal reads consistently coyote-like rather
than fox-like: grey-tan coat with no red-fox rust tone even accounting for IR/compression washout,
notably longer legs and leaner body than the stocky, short-legged build *V. vulpes* shows even at
this camera's distance, and ear/snout proportions closer to *Canis latrans* than *Vulpes vulpes*.
This is not a species ID pushed past what five consistent frames of one real event can support, but
it no longer reads as a coin-flip either — recorded as `likely coyote (n=5 frames, one event,
Measured)`, and excluded below on that basis. `201204_0636_Cam1_Fuchs`, `211227_0048_Cam5_Fuchs`,
`210125_1946_Cam6_Fuchs`, and `220307_0051_Cam4_Fuchs` (the four German-camera "Fuchs"-named files
sampled) remain `UNVERIFIED` rather than confirmed either way — all four are small-in-frame,
low-detail night captures where the animal's silhouette is consistent with a mid-size canid but not
diagnostic of species by eye; `220320_0252_Cam6_Fuchs`, by contrast, is a clear, close, unambiguous
fox.

**A new lead: this source is not fully independent of the rejected `testing-uutoy`/`ml-dlq4x`
scrape pool.** The second draw's random sample happened to include two bare-16-lowercase-hex-
character filenames — `1dfc09c5ba442f0c` and `d1084d21b143e46d` — the identical naming convention
already confirmed above to mark `testing-uutoy` and `ml-dlq4x`'s shared, contaminated upstream pool
(most likely Open Images V6's "Fox" class). Neither filename byte-matches a filename seen in this
session's `testing-uutoy`/`ml-dlq4x` samples, so this is not proof of an exact shared file, but the
naming convention itself is the signal that pool uses, not `mgr-l8rhf`'s own camera-trap/video
conventions. Of the two sampled, one (`1dfc09c5ba442f0c`) is a genuine fox and one
(`d1084d21b143e46d`) is the confirmed coyote above — `n=2, 50% contaminated`, far too small to set a
rate, but fully consistent with that pool's already-measured ~30-37% contamination band in the other
two sources. **This is the one open item this pass could not close**: how many bare-hex-named files
exist in the full 605-image corpus is unknown from a 70-image sample, and every one found should be
treated with the same suspicion as the rejected pool until individually reviewed or excluded by
filename pattern.

**A data-quality finding, distinct from species contamination: some frames appear to contain no
animal at all.** Three frames from a UK/Irish-style mountain-scree camera-trap deployment
(`frame_000303`, `frame_000466`, `frame_000535` — no brand overlay, timestamped `04/09/2020` /
`04/19/2020`) show only rock and hillside with nothing resembling an animal visible; a fourth
(`frame_001521`, same deployment, daylight) is likewise empty. A fifth (`frame_000800`) is
inconclusive — a reddish blur at the frame edge that may or may not be an animal leaving frame. This
matters independently of species correctness: if these frames carry an exported bounding box at all,
that box is a labeling defect (an empty-scene false detection baked into the source dataset), not a
wrong-species one, and needs the same per-image check before any of this deployment's frames are
wired in.

**A structural finding, not a contamination one: heavy within-sample duplication of single
events, now confirmed to span both draws.** The raccoon burst is one event sampled seven times
combined; the WhatsApp clip is one event sampled five times combined; a walking-away fox sequence
down a forest trail recurs across `frime-1646-`/`frime-1649-` and four `vlcsnap-2024-04-...`
timestamps within minutes of each other; the mountain-scree deployment's `frame_001270`/
`frame_001476`/`frame_001488` read as one continuous fox visit sampled three times. This means the
true count of *independent* scenes across the combined 70-image sample is meaningfully lower than
70 — a real consideration for training value, separate from species correctness. It also confirms
the `vlcsnap`/WhatsApp-screenshot/`yt-`-prefixed filenames are frame-grabs from downloaded or
re-shared video rather than original camera output — a provenance note worth carrying (not a
rejection reason on its own; the CC BY 4.0 license covers the Roboflow project as published,
regardless of the uploader's own capture chain).

**Disposition: ADOPT WITH EXCLUSIONS.** The wider pass this document's first version scoped as a
prerequisite is now done — 70 of 605 (11.6%) reviewed by eye across two independent draws — and it
reinforces rather than overturns the original read: contamination in this source clusters into a
small number of well-bounded bad *events* (the `KAROL01` raccoon scene, the `GORDIEXD02` coyote-like
WhatsApp clip, one confirmed catalog-hash coyote) rather than being scattered through the corpus the
way `testing-uutoy`'s and `ml-dlq4x`'s ~30-37% catalog contamination is. That remains a meaningfully
more tractable risk profile than the two rejected sources. A concrete per-file exclude list, to be
built into `BOAR_VISUALLY_CONTAMINATED_FILENAMES`'s Fox equivalent before wiring:

- Every frame confirmed or sharing the exact timestamp/scene of the `KAROL01` `03/12/2018 05:30AM`
  raccoon event (`frame_1559`, `frame_1823`, `frame_914`, `frime-155-`, `frime-1615-`,
  `frime-1634-`, `frime-1696-` — 7 confirmed so far; any further frame matching that camera ID and
  timestamp found later should be added, not assumed absent).
- Every frame of the `WhatsApp-Video-2024-02-14-at-5_05_03-PM_mp4` clip (`-0017`, `-0023`, `-0032`,
  `-0042`, `-0109` — 5 confirmed so far; treat the whole clip as one excluded event rather than
  cherry-picking frames, since all sampled frames are the same individual).
- `d1084d21b143e46d` (confirmed coyote).
- Any other bare-16-lowercase-hex-character filename found in this source, pending individual
  review — only `1dfc09c5ba442f0c` (fox, kept) and `d1084d21b143e46d` (coyote, excluded) have been
  checked; do not assume the rest of that naming pattern is clean.
- The empty/inconclusive mountain-scree frames (`frame_000303`, `frame_000466`, `frame_000535`,
  `frame_001521`, and `frame_000800` pending a closer look) should not be wired as positive Fox
  boxes without a per-image annotation check.

This exclude list is necessarily a floor, not a ceiling, at 11.6% sampled — the same caveat the Boar
audit carries for its own visually-contaminated-filename list. It is enough to wire this source in
responsibly; it is not a claim that every remaining un-sampled image is clean.

Also note for the eventual `DATASETS` entry: filenames include catalog-style sequential frame
numbers (`frame_NNNNNN`, `frame_NNN`, `frime-NNNN-`) from what look like several distinct video
sources sharing overlapping naming schemes, plus genuinely distinct `vlcsnap-<timestamp>` and
`yt-<ID>-` names. `group_key()`'s frame-tail-stripping would risk collapsing distinct clips that
happen to share a numeric tail range into one group (the exact `mgr-l8rhf`/`fox-sldyl` risk flagged
before this audit began, now sharpened by confirming at least two visually and numerically
overlapping `frame_NNN` schemes — a short unpadded one and a six-digit zero-padded one — belong to
different underlying cameras entirely) — the `frame_NNNNNN`/`frame_NNN`/`frime-NNNN-`-style entries
need a per-clip filename prefix applied at ingestion (mirroring how `board-captures-fox-encounter1`
uses one `fx1_burst_` prefix deliberately for its one real continuous encounter) so that
`split_by_group()` does not either over-merge unrelated clips into one train/test group or, worse,
silently split frames of the *same* clip across train and test.

### `testing-uutoy/fox-detector-dataset` — REJECT

**35/35 sampled** (in a prior window; re-confirmed in this pass by re-reading the full sample
list). Approximately **12-13 of 35 (~35-37%)** are species contamination: fennec fox (*Vulpes
zerda*), gray fox (*Urocyon cinereoargenteus*) ×2, black-backed jackal, gray wolf (*Canis lupus*),
maned wolf (*Chrysocyon brachyurus*) ×4, coyote (*Canis latrans*) ×2, a deer/fawn pair (wrong genus
entirely), and one hand-drawn illustration (non-photographic). This is a scraped/catalog-style
pool (sequential 16-hex-character filenames, e.g. `0016a719395bc945`, `36129f654de6062c` — not
camera-trap EXIF names), consistent with sourcing from a noisy public image aggregation rather than
a single deployment's own captures.

**Confirmed shared upstream pool with `ml-dlq4x/fox-iav0z`.** Two filenames are byte-identical
hash matches across both projects' exports — `36129f654de6062c` and `b8958f0a225e96eb` — meaning
both Roboflow projects were built by re-uploading the same underlying noisy public image
collection (most likely Open Images V6's "Fox" class, given the filename convention), not two
independent sourcing efforts. Adopting both would double-count near-identical imagery while also
double-counting the contamination baked into that shared pool.

**Disposition: REJECT.** A ~35% contamination rate mixed uniformly through a 584-image scraped
catalog, with no per-image species metadata to filter mechanically, mirrors the exact reasoning
`boar-representation-audit.md` used to reject Island Conservation Camera Traps: the cost of
exhaustively hand-reviewing the full corpus to pull a clean subset exceeds the value of doing so
when a genuinely cleaner alternative (`deepnetworkdevelopment`) already exists at a fraction of the
contamination rate. No corpus change made.

### `ml-dlq4x/fox-iav0z` — REJECT

**35/35 sampled.** Contamination rate and taxonomic spread mirror `testing-uutoy` closely:
fennec fox, gray fox, maned wolf, black-backed jackal, dhole (*Cuon alpinus*, Asian wild dog —
found in this pass, a genus-level mismatch not seen in any other source), and coyote confirmed
**twice** independently in the sample. That is roughly the same ~30% contamination band as
`testing-uutoy`, consistent with the shared-upstream-pool finding above — this is not an
independent second data point, it is very likely the same noisy pool re-sampled.

Two additional defects specific to this source:

1. **A structural rotation-augmentation artifact present on essentially every exported image** —
   every sampled frame shows a visibly skewed/rotated frame with black letterboxed borders. This
   is Roboflow's own `rotate: 20 degrees` augmentation baked into the export (confirmed in the
   project metadata: `"rotate":{"degrees":20,"enabled":true}` alongside 3x version multiplication
   and saturation/flip augmentation) — meaning even a filtered subset of this source would need its
   bounding boxes re-derived post-rotation before use, a nontrivial extra step for a source that is
   already contamination-heavy.
2. One stock-watermarked image (a "Wiley"-branded photograph) and one image that is a photograph
   of a printed poster rather than a natural scene, both found in the portion of the sample
   reviewed in the earlier pass, consistent with the same scraped-pool provenance.

**Disposition: REJECT.** Same contamination band as `testing-uutoy`, confirmed shared upstream
pool with it (do not treat as an independent source), plus a structural annotation-coordinate
defect specific to this export that would need fixing even for a clean subset. No corpus change
made.

## Own capture: `board-captures-fox-encounter1` — the anchor, not the volume

Built by `scripts/build_fox_encounter1_vision.py` from the real 11 Sept 2026 encounter
(`fox_encounter_20260911T203127`, 1,715 raw IR-night frames at ~11.5fps). The script re-derives the
frame↔detection pairing by nearest-timestamp match against the deployed model's own 36-record
detection track, keeps one representative frame per distinct match (**13 kept frames**, temporal
order: 11 frames spanning the main ~13s track, 2 frames from the fox's brief return ~31-34s later),
and relabels every kept box "Fox" — the deployed two-class model's own boxes correctly localized
the animal in every kept frame, confirmed by eye; only the species label was wrong, which is
exactly the gap this class exists to close. **One candidate frame was dropped**
(`00142500`, the JSONL's final record, reported confidence 0.52): nothing resembling an animal is
visible at the reported box in that exact frame, most likely because the true detection instant
falls in a gap between saved frames larger than the ~87ms average interval elsewhere in the track.

This is real, IR-night, on-the-actual-deployed-camera imagery of the exact false-positive class
this feature exists to fix — the single highest-value 13 images in the corpus, weighted by domain
match. It is also, by construction, one continuous sighting of one individual against one fixed
background: `group_key()` collapses the whole set into a single group via the shared
`fx1_burst_` prefix, deliberately, so the entire encounter lands on one side of the train/test
split rather than leaking the same scene across both. Box coordinates are the detector's own
reported boxes, by-eye confirmed to contain the animal but not hand-tightened — flagged here as
imprecise-but-present, the same caveat `board-captures-night1`/`day1` carry for their zero-box
convention, except these are real boxes.

**Disposition: ADOPT — already built, 13/13 frames.** No further vetting needed; the "evidence" for
this source is a real, previously-documented misdetection, not a scraped image.

## What this audit changes and what it does not

- **Combined recommended corpus:** 99 `deepnetworkdevelopment` images + 13 own-capture frames +
  `mgr-l8rhf`'s up-to-598 images (605 project images, minus the 7-frame `KAROL01` raccoon event,
  the 5-frame `GORDIEXD02` coyote-like WhatsApp clip, and the one confirmed catalog-hash coyote —
  **before** whatever the still-open bare-hex-filename check removes) = **on the order of 700-710
  images ready to wire into `DATASETS`**, `mgr-l8rhf` now cleared for adoption with the concrete
  exclude list above rather than gated on further sampling. `testing-uutoy` and `ml-dlq4x` are
  rejected outright — 0 images from either enters the corpus.
- **This is still a small Fox corpus relative to Elephant (thousands) or Boar (7,394).** Even with
  `mgr-l8rhf` fully wired, Fox tops out somewhere under 750 real images versus Boar's multi-
  thousand corpus — a genuinely thin class by comparison. That imbalance is a real constraint on
  how much Fox recall this pass can realistically buy, and should be stated plainly in the eventual
  README entry rather than implied away.
- **Domain skew is a real but now-improved open gap.** The one source clean enough to adopt
  outright with no exclusions (`deepnetworkdevelopment`) is predominantly daytime stock
  photography; `mgr-l8rhf` supplies the genuine night/IR camera-trap domain match (roughly a third
  of its sampled frames), and its contamination — now characterized across 70 sampled images
  instead of 35 — reads as a small number of well-bounded bad events with a concrete exclude list,
  not a pervasive scattered problem. One item stays open: the bare-16-hex-filename lead (shared
  naming convention with the rejected scrape pool, n=2 sampled, 1 contaminated) means an unknown
  number of not-yet-reviewed files in this source carry elevated risk until checked or filtered by
  filename pattern.
- **No upload, no EI project mutation, no retrain happened in this pass.** Nothing above changes
  the currently-deployed champion (`etx_cpu_final_0830.eim`) or its measured numbers. This document
  is the sourcing gate the retrain has to clear first.

## Recommended next steps, in order

1. Optional, small, bounded: identify every bare-16-lowercase-hex-character filename in
   `mgr-l8rhf`'s full 605-image corpus (the one open lead this pass could not close — n=2 sampled,
   1 contaminated) and either review each by eye or exclude the pattern wholesale. This does not
   need to block wiring the rest of the source, since it is a small, identifiable subset, not a
   corpus-wide characteristic.
2. Wire `deepnetworkdevelopment/fox-detection-7iqxq` (99 images, painting excluded by filename),
   `board-captures-fox-encounter1` (13 images, already built), and `mgr-l8rhf/fox-sldyl` (up to 598
   images, excluding the `KAROL01` raccoon event, the `GORDIEXD02` WhatsApp coyote-like clip, and
   `d1084d21b143e46d`, per the exclude list above) into `DATASETS` and `dataset_manifest.json`
   under a new Fox class key, applying a per-clip filename prefix to `mgr-l8rhf`'s
   `frame_NNN`/`frame_NNNNNN`/`frime-NNNN-` entries at ingestion so `group_key()` cannot collapse
   distinct clips into one train/test group.
3. Upload (`--dry-run` then real), confirm the group-aware split spreads each source across both
   train and test without collapsing `mgr-l8rhf`'s distinct clips into one group (per the
   `group_key()` risk noted above).
4. Retrain on the unchanged champion recipe (`--family yolo-pro --yolo-variant no_attn_relu
   --yolo-sizing medium`), full threshold sweep, per-class P/R for Elephant/Boar/Fox plus
   Background FP — logged to `_retrain_yolo_medium_fox_<date>.log` /
   `_sweep_yolo_medium_fox_<date>.log`.
5. Evaluate against the standing bar: no Elephant/Boar regression vs the current champion; Fox
   precision/recall reported with held-out n stated plainly; Fox performance specifically checked
   on its night/IR test subset; a direct re-run against the real 11 Sept encounter frames to see
   whether the retrained model now calls the tracked animal "Fox" instead of "Boar" at comparable
   confidence.
6. Only then: go/no-go on promoting the Fox-augmented model, decided from those numbers, not from
   this document — this document establishes what is safe to feed the retrain, not what the
   retrained model will do.

**Step 6 result (13 Sept 2026) — see `ml/vision/README.md`'s dated "Fox class added" entry for the
full numbers, job IDs, and dual-reference sweep tables. Verdict: no-go on promotion, go on keeping
this checkpoint as the working Fox baseline.**

- Elephant/Boar precision/recall hold within measured noise (≤1.1 pt) against the immediate
  ceteris-paribus pre-Fox corpus state at every threshold, and within ≤1.4 pt against the deployed
  30 Aug champion — no regression attributable to Fox.
- Fox recall is real but modest: 0.609 / precision 0.642 at threshold 0.05 (n=294 held-out), far
  short of the ≥92%-per-class aspirational bar Elephant/Boar are held to. Checked specifically on
  the night/IR-relevant subset per the standing bar: the real camera-trap source (`mgr-l8rhf`,
  ~1/3 genuinely night/IR per this document's own audit) recalls *worse* than the daytime-stock
  source (0.432 vs 0.571 at threshold 0.5) — a genuine open gap, not smoothed over.
- The real 11 Sept encounter frames were re-run against the retrained model: 4 of 13 frames
  detected, 100% of those correctly labeled "Fox" (never "Boar" — the exact mislabeling this class
  exists to fix), the other 9 a miss rather than a wrong-species alarm.
- **Not promoted to replace `etx_cpu_final_0830.eim`** — Fox recall is too far from a "never miss"
  bar to trust operationally, and the deployed 0.05 threshold's Background FP cost with Fox added
  has not yet been fully characterized per-source. Recommended next step is growing `mgr-l8rhf`'s
  real night/IR share specifically, since it is measurably the weaker of the two adopted sources
  despite being the domain-relevant one, before revisiting export/deployment.

**Second pass (13 Sept 2026) — see `ml/vision/README.md`'s dated "Fox night/IR data expanded"
entry for the full numbers. Verdict: still no-go on promotion; the recommended fix above was not
what was tried, and it did not close the gap.**

- No new `mgr-l8rhf` images existed to add, so this pass added a second, independent real night/IR
  source instead (`kawaharalabo/far-infrared-rays-animals` v5 — genuine far-infrared camera-trap
  footage, 113 images wired, 24 held out) rather than growing `mgr-l8rhf` itself. This is a
  materially different action from the one this document recommended, and should not be read as
  having tested that recommendation.
- **The night/IR-domain gap this document flagged is still open, now confirmed on a second real
  source rather than closed by it.** Per-source recall proxies at the impulse's live threshold
  (0.5): `deepnetworkdevelopment` (daytime stock) 9/21 = 0.429, `mgr-l8rhf` 120/273 = 0.440,
  `kawaharalabo` (new) 5/24 = 0.208. `mgr-l8rhf`'s own recall moved from 0.432 to 0.440 on an
  unchanged source — inside run-to-run noise, not a real improvement — and the newly added real
  night/IR source recalled worse than either existing source, on a small sample (n=24) not to be
  over-read. No source's held-out night/IR recall improved this pass.
- Elephant recall softened by −0.7 to −4.7 pt against both the deployed champion and the first Fox
  pass, one-directional across all five thresholds and both references though individually inside
  this project's measured noise band — flagged as a pattern worth investigating before another Fox
  pass, not yet diagnosed to a specific cause.
- **The one clear win:** the real 20260911T203127 encounter frames improved sharply, 4/13 → 11/13
  correctly labeled "Fox" at the same live threshold, the largest single change in either pass —
  but this is a 13-frame, single-encounter sample and does not by itself establish that the
  held-out night/IR gap has closed.
- **Still not promoted to replace `etx_cpu_final_0830.eim`.** Updated recommended next step: before
  sourcing a third Fox dataset, investigate the Elephant recall pattern directly (is it
  Fox-class-count-driven via `auto class weights on` reweighting on the shared backbone, or
  specific to these two added sources), and if more `mgr-l8rhf` volume becomes available, add that
  directly — the one lever this document originally recommended and that neither pass has yet
  tried.

## What this document is not

This is a sourcing characterization, not a retrain, and not a claim about how a Fox-augmented model
will perform. Nothing here changes the currently deployed checkpoint's measured Elephant/Boar
numbers. The `mgr-l8rhf` adoption is cleared with a concrete exclude list, not a claim that the
full 605-image corpus is clean — treat everything outside the 70 sampled images as
`UNVERIFIED at the full-corpus level`, and treat the bare-16-hex-filename subset in particular as
elevated-risk-until-checked. Every count in this document traces to either the Roboflow project's
own API metadata or a stated sample size; none of it is extrapolated past what the sample size
supports.

## 27 Sept 2026 — new real field fox encounters found (unannotated, not yet a Fox-class candidate)

Triage of the deployed camera's own detection-triggered clip archive (`device/mpu/bench/
camera_check/board_pull_20260924` through `board_pull_20260927`, 36 clips, 60-220s each,
640x360, one clip.mp4/clip_annotated.mp4 pair per detection trigger) turned up **6 candidate real
fox sightings across 3 separate nights (23, 24, 27 Sept), all at the same physical camera
location** (a banana-plantation trail spot), plus the 2 already-filed frames at
`board-captures-fox-encounter2` from the 23 Sept crop-log pull. All 36 clips were first triaged
by 4-way parallel by-eye review sampling 2-4 evenly-spaced frames per clip; the 6 flagged clips
were then re-sampled densely (1-2s step) around the flagged window and personally reviewed
(not subagent-delegated) before being trusted.

- **4 of the 6 candidates directly confirmed** by personal frame-by-frame review: clean,
  unambiguous canid body shape (pointed snout, erect ears, slim legs, visible tail), distinct from
  boar/elephant silhouette at any distance — `20260923T212018` (2 clean frames), `20260924T145407`
  (1 frame), `20260924T191104` (1 frame). Copied to
  `ml/datasets/vision/raw/board-captures-fox-encounter3/images/` at native 640x360 resolution:
  `fx3_night1a_001/002.jpg`, `fx3_night2_001.jpg`, `fx3_night3_001.jpg`.
- **1 of the 6 downgraded on closer review**: `20260927T004350`'s "possible fox" (a small pale
  low-lying shape) turned out to be a static object unchanged in position across a 90s span within
  the same clip — not an animal. Filed as background, not fox.
- **1 of the 6 not independently re-verified**: `20260923T212434` (the subagent's second same-night
  candidate) — dense re-sampling around its flagged window (48-97s) did not land on a clean frame
  of the animal in the ~4 frames checked; plausible given the same location/night as the two
  confirmed sightings 4 minutes prior and 90 minutes later, but treat as `UNVERIFIED`, not
  confirmed, until someone reviews the full clip.
- **None of the new frames are bounding-box annotated.** Like the `board-captures-fox-encounter2`
  frames before them, these are full-frame IR captures with no hand-drawn box, and — same as
  before — **not wired into the live Fox `DATASETS` entry**. Combined real-encounter inventory
  across both un-annotated batches is now 6 frames (2 + 4) spanning 4 distinct nights, still all
  from the same single camera location, so this does not change the location-diversity gap this
  document's earlier passes already flagged.
- Resolution note: these clip-derived frames (640x360) are lower resolution than the
  `board-captures-fox-encounter1`/`fox-representation-audit` sourced material and the
  `review_frames_full` 1920x1080 crop-log frames — a real quality difference for training use, not
  just a filing detail.

## 28 Sept 2026 — full-clip 1fps expansion, EI Studio upload, train/test split

Fox bounding boxes are annotated directly in Edge Impulse Studio's labeling queue rather than in
an external tool, so the raw frames are uploaded there and only labeling remains. Scope was then explicitly broadened from single confirmed frames to full-clip 1fps
coverage ("add all frame in that video so that we get more background and more fox"), for every
confirmed/candidate fox clip, one clip at a time:

| clip | duration | frames extracted (1fps) | EI filename prefix |
|---|---|---|---|
| `20260924T145407` | 105.7s | 106 | `fx3_night2_full_f###` |
| `20260924T191104` | 143.8s | 144 | `fx3_night3_full_f###` |
| `20260923T212018` | 105.9s | 106 | `fx3_n212018_full_f###` |
| `20260923T212434` | 121.8s | 122 | `fx3_n212434_full_f###` |
| `20260923T223648` | 153.6s | 154 | `fx3_n223648_full_f###` |

All 632 frames uploaded unlabeled via the EI ingestion API (`POST
ingestion.edgeimpulse.com/api/training/files`), landing in project 1097972's Labeling queue to be
boxed directly in Studio. Extraction was ffmpeg at 1 frame/sec (`-ss <t> -frames:v 1 -q:v 2`),
not literal per-codec-frame; a 1 Hz sample is sufficient here because the question is whether the
animal is in frame at all, not sub-second motion.

**Status update on the two previously-flagged clips above:**
- `20260923T212434` — confirmed on direct frame review to be a real fox, superseding the earlier `UNVERIFIED` status from the dense-resample check.
- `20260923T223648` — a fifth clip, not part of the original 6-candidate list surveyed in the 27
  Sept pass above (missed in that triage, surfaced independently afterwards). Confirmed
  by direct frame review (`f075.jpg`, clear canid body/gait at close range) before any
  upload action was taken.

**Train/test split.** Uploading raw frames from the same clip to both EI categories, or splitting
one clip's frames across train and test, would leak near-duplicate consecutive frames across the
split and inflate held-out metrics without proving real generalization — same clip-level grouping
concern already enforced locally for `board-captures-review-fp1`/`fp2` via the `revfp<burst>_<seq>`
naming scheme. Since none of the other 4 clips' frames were fully clean of prior single-frame
uploads (the 145407/191104/212018 clips each already had 1-2 curated singleton frames uploaded to
training earlier), `20260923T223648` — clean of any prior upload — was chosen as the sole held-out
clip. Its 154 samples were moved from training to testing category in place via the Studio
management API (`POST /v1/api/{projectId}/raw-data/{sampleId}/move`, body `{"newCategory":
"testing"}`), verified sample-count-exact (154/154) in the testing category afterward, rather than
re-uploaded (which would have left the frames unlabeled a second time under a fresh sample ID).
The other 4 clips (484 frames) remain entirely in training. This gives the eventual Fox class one
full, independent night/clip held out for evaluation once labeled, without fragmenting any single
clip across both splits.

No retrain was attempted against this new material — labeling in EI Studio (train side) and
labeling + eval (test side, once boxed) are still pending. The open question
remains annotation quality/coverage, not sourcing or split integrity, both of which are now
resolved for this batch.

### Same day — morning false-positive background clips added directly to EI

A separate review identified 6 more clips from `board_pull_20260924`/`board_pull_20260926` as
morning false-positive triggers with no animal present, and asked for them uploaded straight to
EI project 1097972 as Background, split by clip across train/test (never split within a clip, same
rule as above). Sampling rate was full 1fps for the first two clips, then explicitly capped at
10 evenly-spaced frames/clip for the remaining four, since a background clip contributes little
beyond its first few distinct views:

| clip | duration | frames | category | EI filename prefix |
|---|---|---|---|---|
| `20260924T034624` | 105.8s | 106 (1fps) | training | `bg_morn0624_f###` |
| `20260924T034801` | 216.6s | 216 (1fps) | testing | `bg_morn0801_f###` |
| `20260924T035338` | 220.9s | 10 | training | `bg_morn5338_f##` |
| `20260924T035904` | 2.2s | 10 | testing (assigned here; not specified) | `bg_morn5904_f##` |
| `20260924T042153` | 109.3s | 10 | training | `bg_morn2153_f##` |
| `20260926T005209` | 207.3s | 10 | training | `bg_0926_5209_f##` |

362 samples total. Unlike the fox frames above, these were uploaded straight to the correct
category via the ingestion API's separate `/api/testing/files` endpoint where destined for test,
rather than uploaded to training and moved after — no move-then-relabel round trip needed since the
target split was known before upload. Each sample was then explicitly marked as a labeled
zero-object sample via `POST /api/{projectId}/raw-data/{sampleId}/bounding-boxes` with
`{"boundingBoxes": []}`, so these count immediately as Background training/test data rather than
sitting unreviewed in the labeling queue like the unboxed fox frames. Verified 362/362 succeeded
on both the upload and the bounding-box calls.

Content was not independently frame-reviewed before upload — these clips were already identified
as morning false-positive triggers with no animal present, and were taken as Background on that
basis. `20260924T035904` is a 2.2s clip; its 10 "evenly spaced" frames
are ~0.2s apart and effectively near-duplicates of each other, which is immaterial for a
Background/negative sample (no leakage risk in the way it would matter for a positive class) but
worth noting if that clip's contribution to test diversity is ever assessed.

### Same day — fox-clip labeling queue resolved

Before this batch, project-wide label counts already showed **2,487 Fox / 8,071 Boar / 4,936
Elephant** in training and **626 Fox / 2,236 Boar / 1,402 Elephant** in testing — a much larger
pre-existing Fox pool than anything sourced in this pass, almost certainly a generic/stock source
predating this work rather than real field captures. The 632-frame field upload was meant to
supplement that generic pool with true camera/location-realistic examples.

Uploading unlabeled via the ingestion API does not put samples in EI Studio's Labeling Queue view
by itself — that requires an explicit `POST /api/{projectId}/raw-data/{sampleId}/to-labeling-queue`
call per sample, which was initially missed, leaving the queue showing (0) despite 371 pending
frames sitting in the plain dataset view with `label: "-"`. Fixed by finding all unlabeled `fx3_`
samples and routing them into the queue via that endpoint (371/371 succeeded).

The queue was then hand-reviewed directly in Studio. Result: 242 of the 632 frames genuinely
show the fox and already have real hand-drawn boxes (204 training / 38 testing, verified via the
API — real x/y/width/height coordinates, not placeholders). The remaining 370 are real frames from
the same fox-sighting clips where the animal simply isn't in frame at that timestamp (expected for
1fps sweeps of 100-220s clips where the animal is visible for only a few seconds) — confirmed
on review of the frames themselves. Marked as
labeled Background via `POST /api/{projectId}/raw-data/{sampleId}/bounding-boxes` with
`{"boundingBoxes": []}` (370/370 succeeded) rather than deleted, since they're still valid
real-field negative data. Split integrity is preserved — each clip's category (train vs test) was
fixed before any labeling happened, so labeling individual frames within a clip differently
(Fox vs Background) never moves anything across the train/test boundary.

Net effect on this pass's field-sourced material: 242 real Fox-boxed frames + 732 Background
frames (370 from fox clips + 362 from the dedicated false-positive clips above) now fully labeled
and training-ready, all traceable to specific clips/timestamps in this document. The project-wide
Fox label count (2,487/626) is unchanged by the 370 background relabels, as expected — only
real animal-present frames add to that count.

No retrain was attempted against this new material. The open question is annotation strategy, not
sourcing — flagged for an explicit decision rather than settled here, given the deployment stakes on
this project and this document's own standing caution against training on unverified material.
