# ADR 0024: Per-species acoustic classification deferred; `AcousticClass` stays generic for the September field build

- **Status:** superseded in part — see amendment below (2026-09-10, same day)
- **Date:** 2026-09-10

## Amendment (same day) — decision overridden

After reviewing the analysis below in full, the project owner decided to proceed with multi-species
acoustic classification now, ahead of the September field build, accepting the risks this ADR
identifies (production-code change to tested fusion logic close to a build date, live-trial risk,
uncertain boar-audio availability). That is the project owner's call to make with the risk disclosed —
the analysis below stands as the record of what was weighed, not as a decision that binds against an
informed override.

**Current direction (supersedes the "Decision" section below):** extend `AcousticClass` with real
per-species classes — `elephant_call` and `boar_call` as named targets (the two species this project
actually deters), with a generic `other_animal_call` catch-all for everything else in scope (gaur, deer,
monkey, leopard, tiger) rather than chasing individual classes for species with even less available data.
Source real, license-verified audio for every class — elephant and boar specifically, plus more volume for
the existing `gunshot`/`chainsaw`/`vehicle` classes — and train the best model the found data supports.
Where a class's real, verified data comes up short (most likely `boar_call`), report that honestly and
fold it into `other_animal_call` rather than fabricate or pad it, per this project's existing "no
fabricated numbers" discipline.

The architectural point (fusion only needs "an animal is present," not species identity) and the
practical risk (touching `reflex_loop.py`'s tested routing near a build date) are not wrong — they are
real, disclosed trade-offs, knowingly accepted in exchange for a more capable system. Regression-test
the full reflex loop against the existing gunshot/chainsaw fixtures before merging, since that is the
one place this reversal could cause a real safety regression if rushed.

---

## Original analysis (2026-09-10, morning)

## Context

New real audio arrived: 127 clips recorded on a XIAO ESP32S3 microphone (background/gunshot/chainsaw/
vehicle) plus an uploaded export claimed to contain elephant vocalizations and more background noise
(not yet verified in detail). This raised the question of whether the acoustic pipeline's `AcousticClass`
enum (`device/mpu/bridge/rpc.py`: `gunshot`, `chainsaw`, `vehicle`, `animal_call`, `ambient`) should be
extended to identify species from sound directly — at minimum elephant vs. everything else, ideally also
boar — rather than the current generic `animal_call`.

Three real constraints bear on this decision at once: the next field build is due 13 Sept 2026,
three days from this decision; EleTect X is mid a real, live field trial with the Kerala Forest
Department, not a demo-only project; and `AcousticClass` is consumed by `reflex_loop.py`'s tested
production fusion/routing logic, which also gates the gunshot/chainsaw anti-poaching alerting the
Forest Department operationally depends on.

Given the stakes of touching tested production fusion logic mid-trial, this was weighed from
several independent angles rather than settled in a single pass. Four of them point the same way:
redundancy with vision, data insufficiency, production-code risk, and the task sequencing simply not
fitting the time available. The one line of argument for proceeding — a parallel long-term
data-collection track — carries the same live-trial risk it claims to avoid.

## Decision

**`AcousticClass` and `reflex_loop.py`'s fusion/routing logic are frozen as-is through the
September field build.** That build ships with the existing 5-class scheme, `animal_call` staying
generic (not species-specific).

Two independent reasons support this, and both are recorded because they lead to different futures:

1. **Architectural: corroboration doesn't need species identity.** The acoustic channel's role per
   `/CONTEXT.md` is corroboration of vision plus independent anti-poaching detection — not a second
   species classifier. Fusion needs "an animal is present" to weight vision's confidence; it does not
   need acoustic to agree with vision on *which* species. Vision already performs per-species
   identification at real, trained recall (Elephant 0.906, Boar 0.852 @ threshold 0.05 — see
   `ml/vision/README.md`). A correctly-working per-species acoustic classifier would mostly agree with
   vision on the cases vision already gets right, and be least reliable on the ambiguous cases where a
   second opinion would matter most. This reasoning holds regardless of data quality or how much time is
   available — it means per-species acoustic classification may never be justified as a *fusion* input,
   independent of reason 2 below.
2. **Practical: the current data and timeline don't support it, and the risk is asymmetric.** The 127
   XIAO ESP32S3 clips were recorded on a different microphone than the deployed INMP441 (different
   frequency response, self-noise floor, and gain curve) and have not been verified to transfer to the
   field sensor. The uploaded elephant/background export has not been inspected for real content, label
   quality, or clip count. Boar vocalization audio may not exist in usable, licensed form anywhere.
   Asian elephant rumble content is substantially infrasonic and may sit below what a low-cost MEMS mic
   captures cleanly. Building a trainable per-species classifier requires verifying the new data, likely
   sourcing more of it, retraining, validating against a real holdout, then modifying a tested production
   enum, `reflex_loop.py`'s fusion/routing, and its existing test suite, then regression-testing the full
   reflex loop end-to-end — a multi-day sequence that does not fit inside the 3 days left before
   the field build. Given `reflex_loop.py` also gates the gunshot/chainsaw anti-poaching
   alerting the Forest Department depends on operationally, introducing an unvalidated change here during
   a live trial risks a false negative on a safety-relevant alert for a species-granularity feature with
   no confirmed stakeholder ask.

## Alternatives considered

- **Split `animal_call` into `elephant_call` / `other_animal_call` now, ship it in this build.** Rejected:
  fails on both reasons above — no confirmed capability gain over vision, and the data/timeline/production-
  risk case is not close.
- **Start a parallel, unscoped "research platform" track** — passively collect and auto-label field audio
  from the live trial for future bioacoustics work (elephant individual/herd identification, a
  boar-vocalization dataset with real scarcity value) — was raised and is not without merit as a future
  direction, but rejected for *now*: it proposes modifying data capture/logging on live field hardware
  during the same 3-day window as everything else, contradicts its own "zero engineering risk" framing,
  has no answer for who owns/maintains such a pipeline, and — critically — was never taken to the Forest
  Department for sign-off. Collecting additional field audio during an active DFO trial is a data-
  governance decision, not an engineering one, and must not be conflated with the build in progress.
  If pursued later, it needs an explicit DFO conversation and its own ADR.
- **Do nothing with the new audio at all.** Rejected: the new local data (127 clips) and the uploaded
  export are still useful — as generic `ambient`/`gunshot`/`chainsaw`/`vehicle`/`animal_call` training
  data for the existing 5-class model, and as material for the offline experiment described below.

## Consequences

- The September field build and the current field trial ship with acoustic corroboration unchanged:
  generic `animal_call`, no enum change, no `reflex_loop.py` change, no new test-suite risk
  introduced this close to a field build.
- **Before this is revisited**, run one cheap, non-production, fully offline experiment — decoupled from
  `AcousticClass`/`reflex_loop.py` and from the build schedule — to actually learn whether the premise is
  viable at all:
  1. Verify the uploaded export's real contents (file count, format, actual elephant/background split,
     label quality) rather than trusting its description.
  2. Quantify the XIAO ESP32S3 → INMP441 transfer gap directly: record even a small number of matched
     clips on both mics side by side, or at minimum compare their frequency response / self-noise specs,
     before assuming the 127 clips are usable field-mic-equivalent data at all.
  3. Only if both of the above hold up, prototype a species classifier in an Edge Impulse project or
     notebook against a real held-out set, entirely outside production code, and report real numbers
     before any decision to merge.
- **If a per-species acoustic track is pursued later, the realistic data bar is (not yet executed, no
  numbers exist to quote):**
  - **Clip/window length:** the existing 4.0 s window (shared with the current 5-class model) suits
    trumpet/roar calls and short interaction sounds, but Asian elephant rumbles are often longer,
    low-frequency, infrasound-adjacent events — a fixed 4.0 s window can truncate a rumble's structure.
    Any dedicated elephant-call class should be evaluated at both the existing 4.0 s window and a longer
    window (e.g. 8-10 s) before picking one, rather than inheriting the existing choice by default.
  - **Dataset size per class:** treat a few hundred clips per class (roughly 150-300, i.e. 10-20 minutes
    of audio at a 4 s window) as the bare floor below which a class is a toy, not a classifier — this is
    in line with Edge Impulse's own general audio-classification guidance and with the volume the
    existing 5-class model's `gunshot`/`ambient` classes already have. Treat 500+ clips (40-60+ minutes)
    per class as the realistic target for something field-trustworthy, matching the order of magnitude
    already achieved for `gunshot` (747 clips) in the existing pipeline. A class below the floor should be
    reported honestly as insufficient, not shipped at a misleading accuracy number.
  - **Sourcing, in priority order:** (1) real INMP441-native field recordings — including, once DFO has
    explicitly signed off, passively logged audio from the live trial itself, labeled against vision's
    real-time calls and treated as noisy/weak labels, not ground truth; (2) real, license-verified public
    bioacoustics sources surfaced while writing this, not yet vetted for download access or licence terms
    — Cornell's Elephant Listening Project "Congo Soundscapes" public database, ElephantVoices' Elephant
    Ethogram, Freesound.org (once `FREESOUND_API_KEY` exists), and WILDLABS.net's community-maintained
    labelled-terrestrial-acoustic-datasets list; (3) the existing Mendeley/ESC-50 pipeline already built
    for the generic classes, for `ambient`/`gunshot`/`chainsaw` volume, not for species-specific classes.
  - Boar vocalization audio should be assumed scarce until proven otherwise by (1) and (2) above; do not
    assume it is sourceable in any fixed timeframe.
  - **Recommended shape, if pursued: binary `elephant_call` vs. generic `other_animal_call`, not a full
    multi-species scheme.** This removes the worst data-scarcity blocker above (no dedicated boar-specific
    corpus is needed — "other" absorbs boar and every other secondary species as one bucket, which is
    already well-served by the existing generic-class sourcing) while still only being trainable if
    `elephant_call` itself clears the dataset-size floor above with real, verified, INMP441-transferable
    audio. This does **not** change the two reasons this is deferred (redundancy with vision's existing
    0.906 elephant recall, and the production-code risk of touching `reflex_loop.py`'s tested fusion
    mid-trial) — those hold regardless of class count. It only changes what the eventual experiment should
    target if and when reasons 1-2 are revisited.
- This ADR should be revisited only after real numbers exist from the offline experiment above — not
  re-opened by schedule pressure, new data arriving, or enthusiasm for the research angle without a DFO
  conversation first.
