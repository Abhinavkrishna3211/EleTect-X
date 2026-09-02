# EleTect X — vision model rebuild: prompt for VS Code Claude Code

Paste this whole document as your opening instruction. It supersedes nothing in `/CONTEXT.md`,
`/CLAUDE.md`, or `/HANDOVER.md` — read those three first, in that order, per `CLAUDE.md`'s own
instruction, before touching anything below. This document assumes you have Edge Impulse Enterprise
API/project credentials (project ID `1094260`, org "Edge Impulse Experts") supplied separately, and
that you have shell + git access to the real repo, not the read-only snapshot this plan was drafted
against.

## 0. Where this stands right now (ground truth, not to be re-derived)

The current model (`ml/vision/`, FOMO / MobileNetV2 α0.35 @ 96×96, INT8, cut at
`block_6_expand_relu`) was trained and evaluated on `2026-08-26`. Verified numbers, from
`ml/vision/README.md` and the actual job logs — do not recompute these from scratch, extend from
them:

| Class | F1 | Precision | Recall |
|---|---|---|---|
| Elephant | 0.692 | 0.749 | 0.693 |
| Boar | 0.618 | 0.629 | 0.666 |

Reported separately, never averaged — keep doing that; a blended number hides which class is
actually the risk.

Dataset: 3,280 Elephant images (`roboflow-universe-projects/elephant-detection-cxnt1`, v2,
daytime colour photography, general wildlife photography **not** camera-trap footage) + 3,280 Boar
images (two Roboflow sources, video-frame-burst + catalog photos). Both CC BY 4.0. **Zero night/IR
images. Zero true-negative (empty-scene) images.** Species of the Elephant class is unverified —
the Roboflow listing doesn't state continent, and nobody has actually looked at the images yet.

Enterprise account is confirmed live and gives you: unlimited compute per job (was 60 min — this is
why training has been stuck at 96×96/α0.35, re-test that constraint is actually gone before
architecture work), configurable compute memory (was 16 GB), **full custom EON Tuner search space**
(was default-params-only), EON Compiler RAM-optimized mode extended to BYOM models, full
organization API endpoints, unlimited impulse experiments (was 10/project), 120 min performance
calibration (was 30 min). Correction already on record: custom DSP/ML blocks were never
Developer-gated — don't re-litigate that.

Deadlines you're building against: field trial with DFO Kothamangalam **complete by 5 Sept 2026**
(moved from 2 Sept — user-confirmed 1 Sept);
Hackster "Invent the Future with UNO Q" submission **13 Sept 2026**. Vision is explicitly *not* a
blocker for the field trial under the frozen architecture (fusion degrades gracefully if vision
underperforms — geophone is primary, vision and acoustic corroborate), so don't let this work
starve the LoRa/actuator firmware blockers that *are* trial-critical. But the trial is also your
best and possibly only near-term source of real IR footage — treat it as a data-collection
opportunity, not just a demo.

## 0a. Credentials to paste in alongside this prompt

**Rotate before you do anything else.** Two keys tied to this project have already been exposed in
plaintext outside their intended one-time-reveal flow (shared in screenshots/chat during planning):
an Edge Impulse project API key named "Work" and a Roboflow full-access private key on the
`eletect` workspace. Values withheld here deliberately — this file is committed to the repo, and a
key belongs in `secrets/vision_pipeline.env` (gitignored), never in tracked prose. Treat both as
burned. Regenerate
both from their respective dashboards (Edge Impulse: project → Keys → the ⟳ icon on that row;
Roboflow: `app.roboflow.com/eletect/settings/api` → the ⟳ icon next to "Unnamed Key") before wiring
anything up, and this time the new values go straight into a local `.env` — never into a prompt,
chat message, or screenshot again.

**Confirmed, non-secret identifiers** (safe to put in the prompt/repo, unlike the keys themselves):
- Edge Impulse org: **"Edge Impulse Experts"**, Enterprise tier confirmed active.
- Edge Impulse project name: **`ETX-V`**. Project ID has a discrepancy worth resolving before
  relying on it: earlier project context recorded `1094260`, but the live Studio URL captured during
  this planning session reads `studio.edgeimpulse.com/studio/1097972`. Don't guess which is
  current — open the project in Studio and confirm the ID in the URL bar before it goes into any
  script or config, and note in the report if these turn out to be two different projects (e.g. an
  old one vs. this Enterprise one) rather than a typo.
- Deployment target is already set in Studio to **Arduino UNO Q** (visible in the top-right target
  selector) — confirms §2/§5's assumption that this is a literal selectable target, don't re-derive.
- Roboflow workspace ID: **`eletect`**. Workspace is currently on the free **"Public Plan"**, which
  per Roboflow's own pricing page means datasets/models on it are public on Roboflow Universe by
  plan design, not by a toggle — Core plan ($79/mo billed annually) is the minimum for private. If
  that's not already an intentional choice, flag it back rather than assuming it should change.

**Credentials live in `secrets/vision_pipeline.env`, not in this document.** A template already
exists at `secrets/vision_pipeline.env.example` (created this planning session) — copy it to
`secrets/vision_pipeline.env` and fill in the rotated values there. `secrets/` is already covered by
this repo's `.gitignore` (line 65, pre-existing convention — `device/mcu/src/secrets.h` uses the same
pattern), so this isn't a new exception, it's the project's established way of keeping credentials
out of commits. At the start of your session, load it (`set -a; source secrets/vision_pipeline.env;
set +a` or the Python-side equivalent) and confirm the keys loaded *without* printing their values —
e.g. `python -c "import os; print(bool(os.environ.get('EI_API_KEY')))"` — never echo a real key into
a terminal transcript, a commit, or back into this conversation, for the same reason the two burned
keys became a problem in the first place. The file holds:

```
EI_API_KEY=            # Edge Impulse project API key (rotated), scoped to ETX-V
EI_PROJECT_ID=         # confirmed project ID from the Studio URL, see above
EI_ORG_API_KEY=        # optional, only if org-level features (Data Campaigns/Upload Portals) are needed
RF_API_KEY=            # Roboflow private key (rotated), full-access, workspace "eletect"
RF_WORKSPACE_ID=eletect
```

**Not available right now: no Replicate account, no OpenAI account.** That takes the GenAI
synthetic-IR generation path (FLUX-pro, DALL·E, GPT-4o auto-labeling) off the table for this pass —
don't spend time wiring it up or leave a half-built integration waiting on keys that don't exist yet.
§3c-4 below is written up for completeness and as a documented future option (get one or both keys
later if the pseudo-IR augmentation route in §3c-3 turns out not to be enough), but the actual data
plan for this pass rests on §3c-1 (real IR footage), §3c-2 (public datasets, no paid key needed), and
§3c-3 (the pseudo-IR script — stdlib-only, no API key required at all, matches the project's existing
`scripts/edge_impulse_*` style). Treat §3c-4 as skipped, not as a blocker to report back on.

What each is for, and whether it's actually required:

1. **`EI_API_KEY`** — required, everything in §2–§4 depends on it. Project-scoped, which is what you
   want for training/upload/deploy automation (not an org-wide key).
2. **`EI_ORG_API_KEY`** — only needed for org-level Enterprise features directly (Data Campaigns,
   Upload Portals, org-shared custom blocks). Skip it while working inside `ETX-V` alone; add it
   later if §3's data-pipeline work grows into something that needs org-level tooling.
3. **`RF_API_KEY` / `RF_WORKSPACE_ID`** — needed to pull any *new* Roboflow sources named in §3c-2
   (the Asian Elephants Dataset, Thai Elephant Dataset) programmatically rather than by hand. The SWG
   Camera Traps dataset is hosted on LILA BC, not Roboflow — that's a direct public download, no key
   needed.
4. **Replicate API token — not available, skip.** Would only matter for the FLUX-pro synthetic-IR
   generation path in §3c-4, which is out of scope for this pass anyway (see above). Don't create a
   Replicate account or spend time on this path unless it's explicitly revisited later.
5. **OpenAI API key — not available, skip.** Same status as above — DALL·E and the GPT-4o
   auto-labeling pattern from §3c research are both off the table for this pass. Not required for the
   core plan.
6. **Arduino/App Lab access** — App Lab's Edge Impulse link-up is an interactive browser login
   (Arduino account credentials), not an API key/env var — flag this to the person actually sitting
   at the board when it's time to do §5's on-device work, don't expect it to be scriptable the same
   way as the rest.

Make sure whatever `.env`/config file holds these is `.gitignore`d before the first commit —
`CLAUDE.md`'s "no secrets... in commits" rule is absolute, and this is exactly the kind of file that
ends up committed by accident otherwise. If something in §2–§4 needs a credential not listed here,
that's a sign the step wandered outside this plan's actual scope — check back against the phase list
in §7 rather than improvising a new integration.

## 1. The actual bar, restated precisely

"No elephants should go undetected on our camera field" is a recall requirement on the **fused
system**, not a property any single 0.62–0.69 F1 vision model can promise alone — that's already
correctly stated in `ml/vision/README.md` §03 and is the frozen-architecture rationale (`CONTEXT.md`
§4: weighted log-odds fusion, availability-gated, so a weak/missing sensor doesn't sink the
decision). Your job here is to make the vision component as strong as it can be — high recall,
honestly measured, on the species/conditions that actually matter — not to over-promise what vision
alone will do. Every number you report back must be a number a real job actually printed. If
something is estimated or unverified, say so explicitly in the same style `ml/vision/README.md`
already uses (see its §04 and §05 — that honesty standard is now the house style, keep it).

## 1a. The explicit target: ≥92%, and what that number has to mean in practice

The stated bar is "more than 92% something" — treat that as ≥92%, and be precise about what it
measures, because "accuracy" is a misleading word for object detection and would let a model game
the number without actually being safer. A single blended "accuracy" figure can look high while
recall on the rarer or harder class is quietly bad — exactly the failure mode this project has
already been careful to avoid by reporting Elephant and Boar separately. Carry that discipline into
the target itself: the real requirement is **≥92% recall on each class individually, at whatever
confidence threshold is actually deployed**, not one number averaged across classes or across
recall+precision. Precision matters too — a model that hits 92% recall by firing on everything is
not useful in the field — but recall is the one the mission statement ("no elephants should go
undetected") makes non-negotiable, so if there's ever a tradeoff to report, report it as a tradeoff,
not a hidden one.

Be honest in the report about the size of this gap: the current model measures 0.693 recall on
Elephant and 0.666 on Boar, on daytime-only data with no true negatives. Getting from there to ≥92%
recall on both classes, in the field, at night, is a large jump — architecture search (§2) and the
cheap data fixes (§3a/3b) can move the number, but the research is consistent that the biggest lever
by far is real night/IR training and validation data (§3c), because a model can't be validated
against a bar it's never been tested on. If ≥92% isn't reached by the reporting checkpoint in §7,
say so plainly, show the real number, and say what specifically is still needed to close the
remaining gap — that is a more useful report than a threshold quietly tuned low enough to make 92%
appear on paper. A held-out set with no true negatives and no night images cannot honestly certify a
92%-in-the-field claim even if it prints a 92% number; make sure the held-out set that number comes
from actually reflects field conditions (see §4) before reporting it as met.

## 1b. Solar + forest power/reliability constraints — this is a deployment constraint on the model, not just the hardware

The node is solar-charged (`CONTEXT.md` §3: 4S LiFePO4 12.8V + low-Iq MPPT + 15–20W solar + supercap)
and runs unattended in forest terrain with no mains backup — every design choice in this pipeline
has to assume intermittent charge, no one nearby to reboot or reseat anything, and that a dead node
is a blind spot in the detection perimeter, not just an inconvenience. Concretely, this constrains
the model/pipeline choices already made in §2 and §5, not just the electrical design:
- Favor an architecture and input resolution that keeps inference **fast and low-power on the
  QRB2210's CPU/GPU**, not just accurate on held-out data — a heavier model that pushes power draw
  up during low-charge periods (cloudy days, monsoon-adjacent weather in Kerala) risks the node
  brownout-ing exactly when a real incursion happens. If a heavier architecture (larger YOLO-Pro
  tier, SSD) wins on recall, report its measured power/latency cost alongside the accuracy gain so
  the tradeoff is visible, not just the win.
- The wake/capture/infer duty-cycle pattern in §5 (illuminator on for the wake window, board sleeps
  between cycles) exists specifically to bound both power and thermal load — don't propose a
  continuous-inference or continuous-illumination design without weighing it against this.
- Whatever confidence threshold or true-negative strategy you land on, remember that in this
  environment a false negative from a starved/thermally-throttled node reads identically in the
  field to a false negative from a bad model — if power headroom is genuinely uncertain, that's
  worth flagging to `device/mcu`/power-budget owners even though it's outside this task's direct
  scope, not silently assumed away.

## 2. Architecture: don't assume FOMO is the right choice going forward

FOMO has two documented weaknesses that land directly on your two target classes:

- **Overlapping-object failure**: FOMO's output is a spatial grid where each cell is a single-label
  classifier — two object centroids in the same grid cell cannot both be detected. Boar move in
  sounders (multiple animals close together); this is a structural risk for undercounting/missing
  boar in a group, not just a training-data problem. (docs.edgeimpulse.com/studio/projects/learning-blocks/blocks/object-detection/fomo)
- **Scale-variance weakness**: FOMO "operates best when objects are all of a similar size."
  Elephants fill much of a frame at typical camera-trap range; boar are smaller and often more
  distant. One FOMO model covering both species scale ranges is fighting its own architecture.

Edge Impulse now ships **YOLO-Pro** — a from-scratch architecture (not repackaged Ultralytics YOLO,
no AGPL licensing issue), true bounding-box output, proper multi-object/overlap handling, six size
tiers from pico (682K params) to xlarge (35M), two variants ("Attention with SiLU" — higher
accuracy; "No Attention with ReLU" — built for hardware without efficient attention ops, likely the
better fit for QRB2210's Adreno GPU rather than an NPU). Critically: **Edge Impulse's own
first-party Arduino UNO Q tutorial uses YOLO-Pro-nano, not FOMO**, as the reference architecture for
this exact board (Studio → C++ Library → "Arduino UNO Q" is a literal named deployment-target
option — confirmed, not inferred). That's real precedent for your exact hardware, even though no
one has run it on elephant/boar specifically.

**What to actually do**, in order:

1. Keep the current FOMO model as the baseline — don't throw it away, it's your only calibrated
   reference point.
2. Run **EON Tuner with the full custom search space**, target device `Arduino UNO Q` explicitly
   (this is what makes the search hardware-aware — RAM/flash/latency for that literal board, not a
   generic estimate), across at least: FOMO (current family, as a control), YOLO-Pro-nano (both
   attention/no-attention variants), MobileNetV2 SSD FPN-lite. SSD's "objects should be large
   relative to frame" caveat and its "no MCU support" restriction don't apply to you — QRB2210 is a
   Linux CPU/GPU target, not an MCU, so SSD is a legitimate candidate, likely stronger for elephant
   than boar.
3. Before you trust EON Tuner's ranking, check whether it exposes recall/F1 (not just
   accuracy/latency/RAM) as a selectable run-objective in your Studio project — this was
   inconsistently documented (one forum thread references a beta "EON tuner for Object Detection"
   with possibly-different objectives than general docs describe). If recall isn't a selectable
   objective, don't just trust the Tuner's top pick — re-rank the candidates it produces by
   per-class recall on your own held-out set, same discipline as the existing F1 table.
4. If time allows past the two deadlines (explicitly a stretch, not a blocker for either): the most
   field-validated pattern found in the research is a **two-stage cascade** — a permissive Stage 1
   "is there an animal" localizer that doesn't trust its own species label, feeding crops to a
   Stage 2 species classifier. A directly analogous, real field-deployed system (Sensors
   26(4):1366, 2026, Raspberry Pi 5, motion-triggered camera, real noise) measured Stage-1-alone
   recall of 0.334 (bad) vs a combined cascade of precision 0.983 / recall 0.975. This is
   architecturally a bigger lift than swapping one Studio model for another — treat it as a v2
   direction to note in the report, not something to force into this pass.

## 3. Data: three concrete gaps, in priority order by effort-vs-value

### 3a. Verify the Elephant class is actually Asian elephant (do this first — ~10 minutes, changes everything downstream if wrong)

Open a random sample of ~30 images from the Elephant class in Studio (project `1094260`) and check
against these discriminators, most-to-least reliable in a low-res/silhouette view:

- **Back profile — most robust at any resolution.** Asian elephant: convex/humped back, highest
  point at head/shoulder. African elephant: concave/sway back, dips in the middle. This is the
  feature most likely to survive IR/night resolution loss later, so it's worth getting right now
  even on daytime images.
- **Head/forehead shape.** Asian: bilobed/twin-domed forehead with a visible central dip. African:
  single large rounded dome.
- **Ears.** Asian: markedly smaller, "crumpled"-looking, don't reach the shoulder. African: large,
  fan-shaped, extend past the neckline.
- **Tusks — do NOT use tusk absence as evidence against elephant.** Asian females are usually
  tuskless or have short tushes; many Asian males are tuskless too. A tuskless individual is
  *consistent with* Asian elephant, not evidence of a labeling error.
- Trunk finger-count (1 vs 2) is real but essentially never resolvable at camera-trap
  resolution — don't bother trying to use it, even on these daytime images.

If a meaningful fraction read as African savanna elephants (large fan ears, concave back, savanna
background), that's a real data-quality problem for a Kerala-specific deployment — filter them out
or flag the class as contaminated before spending more training time on it. If they read as Asian,
say so plainly in the report and move on — don't keep re-litigating it after one honest check.

### 3b. Add true negatives — currently zero, and this is a real blind spot

Every current training image contains its target class. FOMO/YOLO's only "background" signal is an
empty grid cell *inside* an image that already has an animal in it — that is not the same test as
"does this fire on wind-blown foliage at 2 a.m." Source empty-scene images — day and (as they
become available, see 3c) night/IR — of forest boundary terrain with no animal present, and add them
as true negatives so false-positive rate becomes a measured number in the report instead of an open
unknown. This is cheap (arguably the cheapest highest-value item on this whole list, along with 3a)
and should land before the Hackster write-up regardless of anything else.

### 3c. Night/IR data — the real gap, and the one with no shortcut

No public dataset combines Asian elephant + scale + night/IR-reflective imagery. Don't expect to
find one. Concrete paths, roughly in order of value:

1. **Real IR footage from the DFO Kothamangalam field relationship** is the highest-value source
   available to this project specifically — more valuable than anything below. If there's any
   opportunity to place the actual field camera (or a phone with an IR-pass filter, if nothing
   else) at the deployment site before or during the trial and capture even a modest number of
   night frames — including empty-scene negatives — prioritize that over more synthetic-data
   engineering. Real data collected through this relationship is also a stronger Hackster narrative
   than another Roboflow pull.
2. **Nearer-habitat public data as a stopgap, not a substitute**: the SWG (Saola Working Group)
   Camera Traps dataset (Vietnam/Laos, ~2M images, CDLA-Permissive) lists **"Eurasian Wild Pig" as
   one of its most common categories** — same species/subspecies as Kerala's *Sus scrofa*, and
   forest-habitat camera-trap imagery, a much closer domain match than the current catalog-photo
   Boar sources. Worth pulling for the Boar class specifically. Elephant presence in SWG is
   unconfirmed — check before assuming it helps that class.
   Roboflow's "Asian Elephants Dataset" (983 images, instance segmentation, CC BY 4.0) and "Thai
   Elephant Dataset" are small but at least species-correct — useful as a supplement, not a
   day/night fix, and worth folding in regardless of the night-data question since they help 3a's
   concern structurally rather than just spot-checking it.
3. **Pseudo-IR augmentation of the existing daytime images** — a concrete, reproducible recipe
   (CANDAR 2023 workshop paper), not a guess: grayscale conversion (weighted RGB average) → gamma
   correction (`I' = Imax·(I/Imax)^(1/γ)`, γ≈1.0 measured closest to real IR feature space via PCA
   against 211 real IR photos) → composite with a synthetic point-source IR-illumination falloff
   mask (radial brightness falloff from a simulated emitter position, multiply/screen blend).
   Quantified benefit in that paper: 74.89% → 78.68% AP (+3.79 points) — real but modest, a
   supplement to real data, not a replacement. Implement this as a scripted transformation (fits
   the project's existing `scripts/edge_impulse_*` stdlib-only style) applied to a subset of the
   current daytime Elephant/Boar images, uploaded as a clearly-labeled synthetic split — never
   merged into the same bucket as real IR data once you have any, and never presented as equivalent
   to it in the report, matching the honesty standard already set in `ml/vision/README.md`.
4. **GenAI synthetic generation (FLUX-pro via Replicate, Enterprise-available, $0.055/image, BYO API
   key) — SKIP for this pass, no Replicate or OpenAI account exists yet.** Documented here for
   completeness and as a future option, not as work to do now. Edge Impulse's own worked example is
   specifically a synthetic night-vision/security-camera-IR dataset. The load-bearing detail: naive
   prompts produce cartoonish, unusable output — the
   working prompt pattern hedges explicitly with words like "distant," "grainy," "realistic," "as
   if taken by a security camera with an infrared filter." Adapt that pattern for elephant/boar
   (e.g. *"A distant, grainy, realistic monochrome image of an Asian elephant at night in dense
   forest, as if captured by a security camera with an infrared filter"*), generate a modest batch
   (order of hundreds, not thousands — this is a supplement), and — same rule as 3c-3 — label it
   synthetic in the manifest and in the report, never blend it silently into "real data" counts.
   Tune Guidance (2–5, higher = more prompt-faithful) and Interval (1–4, lower = more consistent) if
   output quality is a problem.
5. If you want to multiply a scarce real-night-boar combination once you have even a little real
   night data: Edge Impulse's `example-transform-image-composites` block composites labeled
   foreground cutouts onto background images with configurable placement/rotation/blur, generating
   exact bounding-box ground truth for free. Only worth doing once 3c-1 or 3c-2 gives you real
   material to composite from.

### 3d. Fix the known data-integrity gap before adding anything new

`ml/vision/README.md` already flags a live discrepancy: 6,489 actual images vs. 6,560 expected per
the manifest, most likely `x-disallow-duplicates` silently no-op'ing on byte-identical images shared
between the two Boar sources without erroring, so the upload script's "0 failures" tally never
caught it. Root-cause this — add an explicit post-upload count reconciliation (expected-vs-actual,
hard-fail or loudly warn on mismatch) to `scripts/edge_impulse_upload_vision.py` before you run any
new uploads on top of it, so the same silent gap doesn't compound.

## 4. Training and evaluation discipline — keep the existing conventions, add these

- Keep per-class metrics, never averaged (already the convention — good one, don't regress it).
- Now that true negatives exist (3b), report **false-positive rate on empty scenes** as its own
  number, day and night separately once night negatives exist. This was structurally impossible to
  measure before 3b and is one of the three named reasons the report gave for "not yet
  field-ready" — closing it is a real, checkable milestone.
- Confidence threshold: this project's recall bar means the deployed threshold should sit well
  below the Studio default (0.5). Camera-trap practice for high-recall detectors commonly runs
  0.15–0.3, with some deployments going as low as ~0.02–0.05 when the detector is being used purely
  as a blank-frame filter ahead of a second confirmation stage. Pick a threshold empirically against
  your own held-out set (including the new true negatives) and report precision/recall *at that
  threshold*, not just at Studio's default — the threshold choice is a recall lever you control at
  deploy time, independent of which architecture wins in §2.
- If a two-frame/three-frame temporal aggregation rule (only fire the deterrence trigger after N≥2
  consecutive frame detections) is something `device/mpu`'s fusion layer already does or could
  cheaply do, note it in the report as a system-level recall/precision lever — it suppresses
  single-frame noise (insects near the IR illuminator, glare, foliage motion) without costing real
  detections, since a genuine incursion persists across frames and a spurious trigger typically
  doesn't. This is a fusion-layer design note, not something to implement inside the vision model
  itself — flag it, don't scope-creep into `device/mpu` work under this task unless it's trivial.

## 5. Deployment reality-check on the actual hardware

**Board status: fully connected as of this planning session** — Arduino UNO Q, Arducam B0490 attached
via a USB hub, currently pointed at a plain wall (a usable first true-negative capture, see §3b —
don't discard those first test frames, label and keep them). An empty App Lab project named
`EleTect-X` exists (no Bricks added yet) with the board recognized and selected as the target device.
Get real numbers for §1a/§6 now that this is possible — FPS, latency, whether "full hardware
acceleration" actually means a working GPU delegate on this chip — instead of leaving them estimated.
Do this early, not as the last step.

**Device login credentials**: a device password was shared during setup (verbally/in chat) — treat
that the same as the API keys in §0a: don't put it in this document, don't put it in any script or
commit, and don't paste it into a prompt again. If it needs to be used for SSH/App Lab pairing, enter
it directly at the login prompt or store it in the same local `.env` as the API keys, gitignored. If
it's simple/reused from other accounts, worth changing it once the board is actually racked in the
field — low urgency compared to the API keys (this one only matters if someone gets physical/network
access to the board), but not zero.

Camera confirmed against the actual purchased unit: [Arducam B0490, fabtolab.in listing](https://www.fabtolab.com/arducam-b0490-2mp-imx462-day-ir-night-vision-usb-camera-metal-case)
— IMX462 sensor, MJPEG up to 1920×1080 @30fps, six built-in 940nm IR LEDs (~3m range, this is the
on-board IR, separate from the external 48-LED illuminator board per `hardware/WIRING_GUIDE.md`),
automatic photoresistor-driven day/night switching, M12 lens, USB 2.0, 1.2W max draw, ₹5,452, in
stock. This matches the Arducam-direct spec sheet this section was drafted from on every point that
matters for the pipeline (sensor, resolution/FPS, auto IR-cut, USB/UVC output) — two cosmetic numbers differ
between the two listings (aperture F1.0 here vs F1.6 on Arducam's own page; focal length 3.9mm vs
4.3mm), which doesn't change anything below, but note it rather than silently picking one.

- Confirmed: QRB2210's realistic ML-acceleration path is the **Adreno 702 GPU (845 MHz, OpenCL
  2.0)** via a TFLite GPU delegate, reached through Edge Impulse's Linux/AARCH64 deployment target
  named literally "Arduino UNO Q." There is no documented general-purpose NPU on this chip — the
  dual-core Hexagon DSP exists but is not documented as a CNN-inference accelerator the way
  Hexagon HTP is on larger Dragonwing/Snapdragon parts (e.g. QCS6490, which this project does *not*
  use). Don't plan around QNN/HTP-class acceleration or expect QCS6490-class benchmark numbers to
  apply here.
- **No published FPS/latency benchmark exists for object detection on QRB2210/Adreno 702** —
  extrapolating from a Raspberry Pi 4 FOMO benchmark (60 fps @ 160×160, CPU-only) suggests a
  FOMO-class model in the 5–30+ fps range is a reasonable planning estimate, but this must be
  measured on real hardware, not assumed, before it goes in any report or the Hackster write-up.
  Use `edge-impulse-linux-runner --verbose` (or `ei.model.profile()` via the Python SDK) against the
  actual board and record real numbers.
- Camera: Arducam B0490 (IMX462) is UVC-standard, outputs MJPEG/YUY2/H.264 — not raw Bayer — and
  its day/night IR-cut switch is a **passive photoresistor trigger, not software-controllable**.
  Don't design any pipeline step that assumes you can command day/night mode.
- The IMX462 is a **rolling-shutter** sensor and the B0490 exposes no hardware strobe-sync line over
  USB. Do not pulse the external 48-LED 940 nm illuminator per-frame — that risks partial-illumination
  banding across a frame. The safer, also lower-power pattern for a duty-cycled wake/capture/infer
  design: illuminator on for the full wake window (covering several frames), capture from the middle
  of that window (skip the on/off transition frames), illuminator off between wake cycles. **Checked
  during this planning session, not still an open question**: `device/mcu/src/ir.cpp`'s `pulse_ir()`
  already fires the illuminator as a bounded burst — `IR_PULSE_MAX_MS = 500` (config.h:397) with a
  5000ms cooldown (`IR_MIN_INTERVAL_MS`, config.h:401) — 500ms comfortably spans many frames at the
  camera's up-to-30fps rate (33ms/frame), so the existing firmware pattern already aligns with this
  guidance rather than conflicting with it. What's still unverified: whether the frame actually
  captured/run through inference is deliberately taken from the middle of that 500ms window (skipping
  the on/off transition edges) or just whatever frame happens to be available when `pulse_ir()`
  returns — check the calling code in `device/mpu` (the bridge/perception layer that presumably
  triggers capture around this pulse) rather than assuming the timing coordination is already correct
  just because the burst duration is generous.
- Single USB-C port on the UNO Q: if the camera and anything else (network dongle, storage) both
  need USB, a hub is a real field-reliability dependency, not a minor detail — note this explicitly
  in the report if the deployment config requires one, since it's a single point of failure in a
  sealed enclosure.
- Arduino App Lab (the Brick-based low-code layer) has a documented, official Edge Impulse
  integration and is genuinely the fastest path to a working demo — but community reports flag real
  rough edges for anything latency-critical: a fixed debounce (~0.5s) between inferences by default,
  and WiFi-session reliability issues that some users resolved by switching to USB tethering. For
  the actual field-deployed pipeline (not the demo), evaluate calling `edge-impulse-linux-runner` /
  the Linux C++ or Python SDK directly rather than going through an App Lab Brick, if you need
  tighter control over inference timing or better unattended-operation reliability. App Lab is fine,
  maybe preferable, for the Hackster demo video itself, where a fast, working, showable pipeline
  matters more than field-grade robustness.
- **Two different agents, two different jobs — don't let App Lab's own "Agent Mode" absorb work that
  belongs in the full VS Code Claude Code session.** App Lab's built-in agent is scoped to that one
  App Lab project (Bricks, the on-device sketch, `app.yaml`) — it's the right place to build and
  iterate on the actual camera/inference Brick described above, once there's a trained model to point
  it at. It is not the right place for §2–§4's work (EON Tuner runs, dataset scripting, Roboflow/LILA
  pulls, the pseudo-IR augmentation script, git/ADR/README updates across the repo) — that needs
  shell, git, and repo-wide file access that a scoped App Lab agent isn't built for. Do the
  data/training/architecture work in the full VS Code Claude Code session per the rest of this
  document, and only bring App Lab (and its own agent, if useful) in for the on-device
  camera-pipeline assembly in this section, once a model actually exists to deploy.

## 6. Reporting requirements — match, don't dilute, the existing house style

Whatever you produce, report back in the same register `ml/vision/README.md` already uses: every
number traced to a real printed job log, unverified/estimated things labeled as such, no fudging a
threshold to make a headline number look better, disagreements or open questions stated as open
questions rather than resolved by assertion. Specifically include:

- Updated per-class precision/recall/F1 table, at the threshold you actually chose, with the
  threshold stated. State explicitly, per class, whether the ≥92% recall target from §1a was met —
  and if not, the real number and what's still needed to close the gap, not a threshold tuned to
  paper over it.
- False-positive rate on true negatives (day, and night once available) — first time this number
  will exist.
- Which architecture(s) you actually compared via EON Tuner, with real numbers per candidate
  (latency/RAM measured or Tuner-estimated — say which), and which you picked and why.
- Species-verification finding from 3a — a real answer, not "probably fine."
- Exact composition of any new data added (source, count, real vs. synthetic vs. augmented — never
  blended in the count without a label).
- Real on-device latency/FPS numbers actually measured on the UNO Q, or an explicit statement that
  hardware access wasn't available and the number is still an estimate.
- If the chosen architecture changed from FOMO to something else: that's a real architecture
  decision per `/CONTEXT.md`'s frozen-architecture rule — add an ADR in `docs/decisions/` per
  `CLAUDE.md`'s hard rule ("If a decision changes, add an ADR"), don't just silently swap it.
- Conventional Commits, no AI-assistance references anywhere (code, comments, commits, docs, PRs) —
  this is a hard rule in `CLAUDE.md`, not a suggestion.
- Update `HANDOVER.md` with the new state — this is called out in `CLAUDE.md` as something to do
  whenever project state materially changes, not just at handover time.

## 7. Sequencing given the actual deadlines

Do these in this order — earlier items are cheap and high-value, later ones are the real lift and
shouldn't block the earlier ones from landing:

1. 3a (species check) and 3d (fix the count-mismatch root cause) — same day, both cheap.
2. 3b (true negatives) — cheap, unlocks the false-positive measurement that's currently impossible.
3. §2 steps 1–3 (EON Tuner full search space, FOMO vs YOLO-Pro vs SSD comparison, targeted at
   `Arduino UNO Q`) — now that the compute ceiling is actually gone, this is the highest-leverage
   remaining lever on the F1 numbers themselves.
4. 3c-2/3c-3 (SWG boar data, Asian-elephant supplement sets, pseudo-IR augmentation) — in parallel
   with or right after step 3, since neither depends on real IR footage existing yet. 3c-4 (GenAI
   synthetic IR) stays skipped — no Replicate/OpenAI account exists (see §0a).
5. §5 (real hardware benchmarking, deployment target finalization) — **the board is already
   connected as of this planning session (bare UNO Q, camera not yet attached)**, so this doesn't
   need to wait — connect the Arducam B0490 now (USB 2.0/B4B-ZR into the board's USB-C, via a hub if
   anything else needs to share that single port — see §5's single-USB-C-port note) and get real
   on-device latency/FPS numbers early rather than treating them as a future/estimated step. Doing
   this now, even against the current baseline FOMO model before the architecture comparison in
   step 3 finishes, also gives you a real power/thermal data point to sanity-check §1b's solar
   constraint against, instead of leaving it purely theoretical.
6. 3c-1 (real IR footage via the DFO relationship) — opportunistic, tied to actual field-trial
   timing, likely the last piece to land and possibly not fully landed before Sept 2. That's fine —
   report it as in-progress rather than forcing a rushed, low-quality capture.
7. §2 step 4 (two-stage cascade) — explicitly out of scope for this pass unless everything above is
   done early and there's real time left before 13 Sept. Note it as a named v2 direction either way.

Report back when you have real numbers for at least items 1–3 — that's the point at which a
verification pass here is worth doing. Don't wait for everything on this list to be checked off
before reporting; partial, honest progress on the deadline-critical items beats a late, complete
report.
