# ADR 0025: Acoustic evaluation splits group by source recording, and field sessions count as one recording

- **Status:** accepted
- **Date:** 2026-09-23

## Context

`ml/acoustic/README.md` reported 58.0% accuracy for the four-class acoustic model and closed
architecture search with "data ceiling, not capacity ceiling." Both conclusions rested on a
held-out score, and that score was measured on a split that could not support it.

The acoustic corpus does not contain independent clips. It contains *recordings*, each of which
appears many times over:

- The preprocessing pipeline emits several windows and gain variants per source file
  (`.10s.e2.norm.wav` and siblings), so one recording yields several files.
- ESC-50 is cut from Freesound, so five chainsaw recordings are present under both corpora with
  different filenames and the same audio.
- Project-owned field captures are chunked. `..._bg.1` through `..._bg.35` are consecutive slices
  of one continuous recording session, not 35 separate captures.

Splitting such a corpus at the file level puts near-duplicates of the same audio on both sides of
the boundary. The held-out score then measures partial memorisation, and it does so unevenly across
classes, which makes per-class comparisons between models meaningless as well.

Three leaks were found and each was measured, not assumed:

1. **Variant-level.** File-level splitting leaked 25.4% of `elephant_call`.
2. **Cross-corpus.** Keying ESC-50 on its own filename rather than the Freesound id it embeds put
   one chainsaw recording on both sides at once.
3. **Session-level.** Keying field captures on the chunk index made 119 files look like 119
   independent recordings. Five chunks of one chainsaw session sat in train while 38 sat in test.

The third leak was the most damaging, because it was invisible in the summary table and actively
misleading in the per-class one. The field chainsaw slice scored a flawless 100%, which read as the
model's strongest result and was in fact the clearest symptom. Worse, the one ambient field session
was wholly in test, so the model had never heard that recorder's noise floor and labelled it
`chainsaw` at confidence 1.00 — pushing chainsaw precision down to 69.4% and pinning it there. A
threshold sweep across 0.30–0.95 could not move it, because a false positive at confidence 1.00 is
not reachable by any threshold. The apparent "chainsaw precision problem" was the split bug wearing
a disguise.

## Decision

Evaluation splits are grouped by **source recording**, and the grouping is part of the index, not
the split script:

- All windows and gain variants of one source file share its group.
- ESC-50 clips key on the Freesound id embedded in their filename, sharing the `fs:` namespace with
  Freesound so a recording held by both corpora resolves to one group.
- AudioSet and VGGSound segments key on the YouTube video id, so several segments cut from one video
  cannot straddle the boundary, and a video selected by both corpora resolves to one group.
- A trailing `.<n>` on a field capture is treated as a chunk index, so a recording session moves
  across the split as a single unit. Captures carrying a per-capture id
  (`..._Elephant_7_4tveetfu`) are genuinely distinct and are left alone.

`freeze_split.py` asserts that no recording appears on both sides and prints the count; a non-zero
count is a hard failure, not a warning. Feature caches are re-keyed against the frozen split file by
filename on load, and a split referencing a file the cache lacks is a hard error — a cache that
silently predates a re-freeze is the same bug in a new place.

Corpora added to improve a weak class are added to **train only**, and the augmentation script
refuses to write if the test set changed. Comparisons are otherwise not comparisons.

## Consequences

The honest field-test slice is very small: 39 ambient, 30 elephant_call, 2 chainsaw and 1 gunshot
recordings. This is not a regression introduced by the fix — it is the true size of the field corpus,
which the previous grouping inflated roughly thirtyfold by counting chunks. **Per-class field-slice
accuracy is no longer a reportable number for `chainsaw` or `gunshot`**, and should not be quoted
until more independent field sessions exist. Collecting them is the highest-value data work
available: sessions, not clips, are the unit that matters, so several short recordings on different
days and devices are worth far more than a longer one.

Fixing the leaks moved the headline in both directions, which is the point. Overall accuracy for the
PANNs Cnn14 backbone went from 90.6% on the leaky split to 92.8% on the session-safe one, because
the ambient session the model had never heard moved into train. Chainsaw recall fell from 89.2% to
77.9%, because its test set is now 66-of-68 public recordings with the memorised field session gone.
The previous number was higher and wrong; `chainsaw` is the weakest class and the 85% per-class bar
is not yet met for it.

Costs accepted: with group-aware splitting the test set is smaller and its composition is dictated by
which sessions land where, so a single seed's per-class figures carry real uncertainty. Per-class
recall is therefore reported with a 95% bootstrap CI over resampled test recordings rather than as a
point estimate, and seed-to-seed spread is not used as the uncertainty measure — deterministic heads
give identical scores across seeds and would understate it to zero.

## Amendment, 2026-09-23: a fourth leak, and integrity checks that are not about leakage

Three further defects were found by auditing the frozen split directly rather than by reasoning
about filenames. Each was invisible to every rule above, and two of them would have been reported
as an improvement.

**4. Content-identical payloads under different names.** Every grouping rule in this ADR infers the
recording from the *filename*, which is the only thing a name can tell you. It cannot see two names
holding the same audio. The HiruDewmi corpus ships `Roar35` and `Roar54` with identical payloads,
likewise `Trumpet08`/`Trumpet10`/`Trumpet14`, and two Mendeley gunshots carry distinct UUIDs over
one recording. Three such sets straddled the train/test boundary.

`build_index.py` now hashes the *decoded frames* of every file — not the file bytes, so a re-encode
or a header difference cannot hide a duplicate — and unions the group keys of any two files that
match. Identical audio is one recording by definition. 25 payloads proved to be held under more
than one group key; 41 records were re-keyed. This check is cheap to keep and subsumes all future
name-based surprises, so no further naming rules should be added in preference to it.

Three consequences follow that are not about leakage at all, and they are recorded here because the
same audit produced them and the same habit of mind prevents them.

**Contradictory labels are mislabels, not misgroupings.** Freesound id 410552 was present in the
corpus twice, once as `ambient` and once as `gunshot`, over identical audio. It is a rifle shot
recorded in forest at 15 m, which is why an ambient fetch query matched it. Unioning its groups
would have buried the contradiction inside a single recording claiming two classes; instead the
index reports such payloads and refuses to merge them. A gunshot sitting in the `ambient` class
teaches the model directly against the gunshot/ambient confusion it is being asked to resolve. The
clip is quarantined under `ml/datasets/acoustic/raw/_quarantine/`. A sweep of all 1 422 Freesound
ids in the cache found no other label collision.

**Normalisation can manufacture a per-source fingerprint.** The Zenodo ingest peak-normalised
without removing DC. Its source recordings sit at -0.007 to -0.016 DC, which is harmless, but the
windows are quiet forest, so peak normalisation multiplies by roughly 30 and carries the offset up
to a median of 0.32 against 0.000 for every other corpus in the cache. The offset was larger on the
chainsaw windows (0.36) than the ambient ones (0.20). A model could have separated the new corpus
from the rest on that constant alone without listening to the audio, and it would have appeared as
the chainsaw improvement the corpus was added to produce — the same failure as the earlier
`xiao_esp32s3` recorder-fingerprint artifact. Ingest scripts remove DC before normalising, and any
new corpus is compared against the per-source DC/RMS/clipping table before it is trained on.

**Caches keyed by filename must be invalidated explicitly when content changes.** Regenerating the
Zenodo windows left their names unchanged, so both the payload-hash cache and the embedding cache
would have served pre-fix values to a `--resume` run. Filename is an identity for a split, not for
content; the affected entries are dropped by hand when audio is regenerated.

`audit_dataset.py` runs these checks against a frozen split and exits non-zero on any of: a payload
spanning train and test, a group straddle, a missing file, format drift from 8 kHz/mono/16-bit/10 s,
or a label contradicting its own filename. It is run before any result is quoted, and the accuracies
in `ml/acoustic/README.md` dated 2026-09-22 or earlier were all measured before it existed.
