# ADR 0035: Camera-labelled seismic capture, derived range and gait, and the on-device retreat measurement

- **Status:** accepted
- **Date:** 2026-10-02
- **Resolves:** ADR 0024's deferral of species-specific seismic classification, by building the
  dataset it was deferred for want of
- **Relates to:** ADR 0001 (geophone as the always-on tier), ADR 0013 (the detector whose boxes this
  reuses), ADR 0020 (event video, on the same clock), ADR 0022 (`_vision_could_see()`, the blindness
  distinction the label buckets rest on), ADR 0031 §A as amended (`FLAG_NO_RETREAT`), ADR 0034
  (the two-phase attribution this shares)

## Context

Footfall detection says only "something walked past". Species-specific seismic ML was dropped for
want of a dataset, and the raw window that would build one is computed on the MCU and discarded
(`state_machine.cpp`) — while the camera, seconds later, establishes exactly the ground truth those
recordings need. The node has been throwing away a labelled training pair on every encounter since
it was built.

Three things were already true and already being wasted:

- **The MPU receives the seismic feature data and logs it for explainability only.**
  `report_footfall_event` carries `probability`, `sta_lta_ratio` and `feature_vector: float[8]`.
- **The detector returns real bounding boxes in original-image pixel space**, and `VisionCheck`
  discarded them. The camera is 1920×1080 with a 95° FOV, and the watch already polls every second
  for up to 45 s. Everything ranging and gait need was being computed and dropped.
- **`read_seismic_window()` and a monotonic accepted-sample counter already exist** on the MCU. They
  were MCU-internal, not Bridge calls.

Separately, `FLAG_NO_RETREAT` — "this animal did not leave, send a person" — had no honest source.
The post-fire tail was a plain sleep, so there was no bounding box after the fire, and
`retreat_verdict()` answered `no_track` on every record ever written. The measurement was
structurally unavailable, not merely untuned.

## Decision

### A. Capture is piggybacked on the vision poll loop, and the two streams are co-sampled

One seismic window is pulled per vision poll. A window is 2.048 s and the poll interval is 1.0 s, so
consecutive pulls overlap about 2×: the stitched record is **gapless by construction**, with no extra
timer and no extra wake. Stitching dedupes the overlap using the MCU's monotonic accepted-sample
counter, so a real gap is recorded explicitly rather than papered over.

The reason this shape was chosen over a dedicated recorder is that it makes the waveform and the
bounding boxes **co-sampled on one clock** — the same `time.monotonic()` base `video.py` already
stamps every frame with. Waveform, video and boxes align exactly rather than by inference, which is
what makes scrubbing to a frame and landing on the right sample index possible at all.

`read_seismic_window()` becomes a Bridge call returning the window *and* the sample count, with
`BRIDGE_SCHEMA_VERSION` bumped and `bridge/schema.md` updated in the same commit — that file is the
contract, and it listed the function under "same-side function contracts", which stopped being true.

**Capture runs on every vision watch regardless of what started it**, and records the ground motion
even when it never crossed the STA/LTA threshold. This is the only way fox data exists at all: a fox
is 5–8 kg and may never trip a trigger tuned for elephants, so "present but sub-threshold" is itself
the training signal. It costs nothing, because the camera is already awake.

### B. Raw waveform is the durable asset; the 8 features ride along

`state_machine.cpp` and `footfall_features.h` both call the 8-feature derivation an "honest
placeholder". A corpus keyed to a placeholder feature set is a corpus you cannot re-featurise. The
waveform is stored; the feature vector, STA/LTA ratio and MCU probability are stored *alongside* it
because they are free and let you reproduce what the MCU believed at the time.

### C. Range: two different numbers, used honestly as two different things

- **Absolute range**, `d ≈ H_species · f_px / h_bbox_px` with `f_px ≈ 880` from the 95° FOV at
  1920 px. **Approximate, roughly ±30–50%**, because a species' real shoulder height varies
  enormously — an elephant calf against a bull differ by more than a factor of two and the detector
  reports one label for both — and a nominal FOV is not a calibration. Good enough to bin near, mid
  and far and to anchor a learned amplitude-range relation. **Not** good enough to quote metres to a
  ranger, and nothing user-facing does.
- **Relative range trajectory**, `d₂/d₁ = h₁/h₂`. **The unknown real height cancels entirely**, so
  the *shape* of the approach is measured precisely even where the absolute distance is not. This is
  what answers "approaching, receding, or stationary" and gives a normalised closing rate, and it is
  the only range number the retreat decision is allowed to rest on.

Boxes that touch a frame edge (truncated, so the height is not the animal's height) or span near the
full frame are excluded from ranging — the latter is already the known near-lens false-positive
signature, where a spider or a leaf on the lens classifies as an animal with real confidence.

### D. Gait and behaviour are derived from the raw measurements, and stored beside them

A single 2 s window catches the trigger impulse and perhaps one to three elephant steps. The
strongest elephant/boar/fox discriminator is **cadence across several steps** — inter-impact interval
and its regularity — plus per-impact spectral shape and decay. That is exactly what the continuous
stitched record provides and what a single window cannot.

Behaviour (`stationary`/`walking`/`running`, `approaching`/`receding`) is derived by combining the
relative-range trajectory with the seismic impact train, never hand-annotated. The two cross-check
each other: cadence × stride length is an independent speed estimate against the vision closing rate,
and a disagreement is itself a useful quality flag. Records store **the raw measurements plus** the
derived label, so every threshold here can be re-chosen later without recapturing anything.

### E. Label buckets rest on ADR 0022's blindness distinction, which is the whole trap

| Bucket | When |
|---|---|
| `elephant/`, `boar/`, `fox/` | the camera confirmed that species |
| `no_animal/` | the camera **looked properly and saw nothing** — the free negative class, and what teaches a future model to ignore wind, rain and cattle |
| `unlabelled/` | the camera **could not look** — detector outage, or dark with IR off. Kept, never trained on |
| `ambiguous/` | two species confirmed in one watch |

Filing "could not look" as "no animal" is the error this exists to prevent: it fills the negative
class with unlabelled night elephants and teaches a model that elephants only exist in daylight.
ADR 0022's `_vision_could_see()` already draws that line for the deterrent decision; this reuses it
rather than growing a second copy. Each record also stores *why* it landed in its bucket, because the
bucket name alone cannot be audited later.

### F. Actuator contamination is marked, not avoided

The horn, LEDs and IR illuminator sit on the same structure as the geophone, and firing them injects
vibration into the signal being recorded. If every `elephant/` clip contains horn energy and every
`no_animal/` clip does not, a future model learns to detect its own horn — a defect that would
validate beautifully offline and fail completely in the field.

Each record therefore carries the **actuator-on sample ranges**, and training defaults to the
pre-deterrence segment. Recording continues *through* a fire rather than pausing: marked data can be
filtered later, missing data cannot be recovered.

### G. `FLAG_NO_RETREAT` is measured on the device, by the same implementation

After a top-tier fire the node keeps the detector running through the retreat tail. If the relative
range is flat or still shrinking at the end of it, the uplink carries `FLAG_NO_RETREAT` and the
backend maps that to `priority = 'critical'`.

D8 and this ADR's trajectory work share **one** implementation, `kinematics.retreat_verdict()`, so
the frame an officer acts on and the corpus a future model trains on cannot drift apart on what
retreating looked like.

Three properties of the gate, each of which is a defect if taken the other way:

- **`retreated` is a tristate and `None` is not a weak `False`.** `None` means the node could not
  tell — a dark tail, a closed camera, too few boxes — and routing an undetermined verdict as "did
  not retreat" would page a forest team on an absence of evidence. The flag is a separate boolean
  precisely so nothing reads it off `retreated` directly.
- **The cut is the *first* actuator to start.** The horn blocks the MCU for the better part of four
  seconds and the LED runs after it, so cutting at the last start discards the seconds the animal
  spent reacting to the horn — on a real event, most of the evidence there is.
- **Top tier and an actuator that actually acked are both required.** Below the top tier the node
  still has somewhere to escalate to, and an animal that held its ground through a burst the rule
  gate refused to fire says nothing about deterrence.

The seismic record write is split around the tail: the waveform is snapshotted **before** it, because
the stream ring holds 60 s and the tail can run most of another minute, so the pre-roll would age out
on exactly the events that matter most; the record is written **after** it, because the post-fire
boxes do not exist until then.

### H. Transport is a site visit, and the retention cap drops the cheapest data first

About 2 KB per window, so a heavy night is single-digit megabytes — negligible beside video. LoRa
cannot carry it; it leaves the node on a site visit via `scripts/export_seismic_dataset.py`. The
dataset directory has a size cap whose eviction order drops `unlabelled/` first and the three species
buckets last, so a full disk costs the corpus the records that were never trainable before it costs
the ones that were.

## Alternatives considered

- **A dedicated seismic recorder on its own timer.** Rejected: it would need its own wake, and the
  waveform and the boxes would then be on two clocks with an unmeasured offset between them —
  destroying the co-sampling that makes the labels worth having.
- **Store the 8 features instead of the waveform.** Rejected per Decision B. The features are an
  acknowledged placeholder; a corpus built on them cannot be re-featurised when the placeholder is
  replaced.
- **Quote absolute range to officers.** Rejected per Decision C. Monocular bounding-box range against
  an unknown animal size is ±30–50%, and a distance on a ranger's screen would be read as a
  measurement. Stereo, a rangefinder and per-animal size estimation are all out of scope.
- **Lower the STA/LTA threshold so light animals trigger.** Rejected and deliberately deferred:
  capture-on-every-watch gets the fox data without altering the trigger behaviour of a node the DFO
  depends on.
- **Pause recording during a fire** to keep the corpus clean. Rejected per Decision F — marked
  contamination is recoverable, a hole is not.
- **Infer "did not retreat" in the cloud from a repeat trigger.** Rejected: it arrives minutes late,
  and it never fires at all if the elephant stays put without re-triggering the geophone — which is
  precisely the situation the flag exists to report.

## Consequences

- **Open: no real camera calibration has been shot through the enclosure window.**
  `device/mpu/data/camera_calibration.json` does not exist, so every record ships `calibrated: false`
  and the nominal focal length is used. A later calibration can re-derive every range from the stored
  boxes rather than invalidating the corpus — which is why the boxes are stored and not only the
  ranges. A 95° lens has plenty of barrel distortion near the edges, and that is uncorrected today.
- **Open: both halves of the seismic path are off.** `SEISMIC_CAPTURE_ENABLED = 0` on the MCU and
  `Bridge.provide("report_seismic_batch", ...)` is commented out on the MPU. They must come up in the
  same session, because either one alone proves nothing.
- **Open: the two timing error terms in `monotonic_at()` / `sample_index_at()` are unmeasured.** The
  alignment is correct by construction and has never been checked against a real encounter; the
  bring-up check is to scrub to a chosen video frame and confirm it lands on the expected sample
  index.
- **The residual risk is dataset volume, and no amount of design fixes it.** This collects clean,
  well-labelled data; it cannot guarantee enough encounters. Two things help and need planning
  separately: training on per-impact windows rather than per-encounter — one 45 s elephant record
  holds 30–60 footstep impacts, so an encounter yields dozens of samples — and deliberate staged
  collection rather than waiting on opportunistic visits.
- **This ADR collects the dataset. It does not build the model.** Training the species-specific
  footfall classifier remains out of scope and remains ADR 0024's deferral; what changes is that the
  reason for the deferral is now being removed.
