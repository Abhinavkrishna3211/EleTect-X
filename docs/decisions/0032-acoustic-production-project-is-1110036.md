# ADR 0032: The acoustic production project is 1110036 (`ETX-Test`), not 1109511 (`ETX-A`)

- **Status:** accepted
- **Date:** 2026-09-30
- **Amends:** ADR 0026 (which project must stay on `float32`), ADR 0030 (which project the int8
  question is asked about)

## Context

Two Edge Impulse projects carry acoustic work, and the one that was *designated* production is not
the one that *earned* it.

**1109511 (`ETX-A`)** was created on 2026-09-23 specifically to be production. It was rebuilt from
scratch from the frozen group-aware split by `scripts/edge_impulse_upload_from_split.py` — the
whole point being a clean lineage with no leaked split and no experiment residue in its history.
It was then deliberately kept off the sweep path.

It did not work well enough. Across six real training runs on the identical post-audit dataset
(four MFE, two MFCC), the 80%-per-class target was missed on every class, and `chainsaw` recall
sat consistently in the high single digits to mid-twenties. `ml/acoustic/ACOUSTIC_MODEL_REPORT.md`
diagnoses why in full: two Studio API behaviours silently discarded half of what the training
configuration asked for. Fixing those recovered real points but not enough of them — the MFE
front end on this corpus is the ceiling, not the bug.

**1110036 (`ETX-Test`)** was the scratch project for architecture, data, DSP and window sweeps.
The PANNs Cnn10 transfer impulse built there — a custom log-mel DSP block feeding a pretrained
audio backbone — cleared the bar the MFE lineage never reached.

## Decision

**Production is project 1110036, impulse 19, deploy v7.** 1109511 is dormant. It is not deleted,
because `ACOUSTIC_MODEL_REPORT.md` is the record of why the MFE route was abandoned and that
record should stay checkable, but nothing ships from it and no number from it is a production
number.

Measured over the 605-clip frozen split:

| class | recall | precision | support |
|---|---|---|---|
| ambient | 92.8% | 92.8% | 236 |
| chainsaw | 91.2% | 89.9% | 68 |
| elephant_call | 93.1% | 91.5% | 58 |
| gunshot | 92.6% | 93.4% | 243 |
| **overall** | **92.6%** | | **605** |

At Edge Impulse's own 0.6 reporting threshold this is 87.9%, and Studio reports 87.77% — the
difference is the threshold, not a different model. Full sweep and confusion matrix:
`ml/acoustic/harness/results_eim_impulse19.json`.

### Why this is a like-for-like comparison and not leakage

A scratch project outscoring a carefully-built one by thirty points is exactly the shape of a
split leak, so this was checked before the switch, not after.

1110036 was re-uploaded from the same frozen split that 1109511 used. All 4,293 clips were pushed
with label **and** train/test category read from `ml/acoustic/harness/split.json` rather than
computed, so Studio's own 80/20 never ran. Verified by API afterwards: training 3,688 and testing
605 are an exact filename-and-label match to the split file, 0 missing and 0 extra, and Studio's
own per-class window counts agree (`ambient 1343, chainsaw 463, elephant_call 627, gunshot 1255`).
Re-verified at scoring time against `ei_upload_ledger.json`: 605/605.

So both projects were scored over the same 605 held-out clips, and those clips are the same ones
the offline harness uses. The gap is the model, not the partition.

## Consequences

- **ADRs 0026 and 0030 need no amendment.** Both already have this right: 0026 is marked superseded
  and says outright that its measurements are of the 92 KB MFE model on 1109511 "which is no longer
  deployed", and 0030 states that the deployed impulse is the PANNs Cnn10 transfer on 1110036. This
  ADR records the *project* decision those two implied but never stated; the "Amends" line above is
  about making that explicit, not about correcting them. ADR 0026's `float32` obligation —
  `selectedModelType` must not be flipped to int8 — is one that now attaches to 1110036, and the
  `metadata.source: edgeimpulse` validator's hard `ei-model-type: float32` requirement makes it
  binding for the registered-model path regardless of what 0030 eventually concludes.
- **The production project is named `ETX-Test`.** This is a live footgun: the name invites someone
  to reset, clear or delete it, and the user has previously (and correctly, at the time) approved
  overwriting it as a throwaway. That approval no longer applies. Renaming it in Studio is the
  cheap fix and should be done.
- **The custom DSP block makes this project unbuildable for a device target in Studio**, which is
  why the `.eim` on the board was compiled locally from the C++ library export. That constraint
  travels with the decision; it is not new, but it is now production's constraint rather than a
  scratch project's.
- The outreach and publication drafts kept outside this repo still narrate `ETX-A` as the
  production project and `ETX-Test` as scratch. They need a pass before anything is published.

## Alternatives considered

**Rebuild the PANNs impulse inside 1109511 so the designated project keeps the role.** Rejected
for now. It buys a tidier name and nothing else: the artefact would be identical, the split is
already identical, and it costs a full re-upload and rebuild plus a re-verification of the
605-clip partition — with a real chance of introducing the duplicate-sample hazard that
`edge_impulse_upload_from_split.py` documents (the ingestion API does no content-hash dedup, so an
interrupted re-send creates duplicates rather than collapsing them). Renaming 1110036 achieves the
same clarity for free. If the projects are ever consolidated, this is the direction, and this ADR
is the thing to amend.
