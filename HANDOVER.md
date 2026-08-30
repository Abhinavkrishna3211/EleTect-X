# EleTect X — Handover (last updated 30 Aug 2026 — see the new "RESUME HERE — 30 Aug (2-hour live-camera stress test: real 31.5% Boar false-positive rate found on outdoor foliage, correcting the earlier 0/123 claim; local `.eim` copies pulled; training-config tutorial delivered)" checkpoint just below for current state: a 2-hour, 40,422-frame continuous live-camera run on the real board (camera pointed at outdoor trees/leaves, no animals present, IR always-on) found a real 31.53% Boar false-positive rate — zero Elephant false positives — which materially corrects the prior night's "0/123, zero false positives" claim (that sample was only 21 seconds/123 frames, too small to be representative). The finding is currently contained: only an Elephant-label detection feeds the alert-fusion decision, so this does not create false elephant alerts today, but it matters for the still-open question of whether Boar detections should ever influence deterrence tier. Latency held steady at scale (137.25ms mean, 5.52 FPS over the full 2 hours, consistent with the smaller sample). Both `.eim` model files were also pulled locally to `device/mpu/models/vision/` (gitignored, byte-identical to the board), and a step-by-step tutorial on the exact training configuration behind the deployed checkpoint was delivered to the user. See that checkpoint for full detail, then the prior "RESUME HERE — 30 Aug (real on-device benchmark: CPU 138ms/~5.7fps measured, 3.9x faster than Studio's own estimate; GPU delegate builds but confirmed non-functional at runtime; functional correctness verified end-to-end via HttpVisionDetector against known-labeled images; EON Tuner still running, no improvement over champion yet)" checkpoint right below it for the prior round: that overnight autonomous session (user asleep, explicit "do everything autonomously... test in uno q... benchmark and compare in the hardware" instruction) exported the finalized `yolo-pro-medium-no_attn_relu` threshold-0.05 checkpoint as two fresh `.eim` builds (CPU `runner-linux-aarch64` and GPU `runner-linux-aarch64-gpu`) and benchmarked the CPU build against the board's real, live-connected camera (pointed out the window, IR always-on) — 123 real inference cycles, mean classification latency 138ms, ~5.7 FPS end-to-end, zero false positives on all 123 live frames. The GPU build compiles and links real GPU-delegate code in Edge Impulse's cloud but fails to launch on this board with `libtensorflowlite_gpu_delegate.so: cannot open shared object file` — confirmed via exhaustive filesystem search and apt-cache search that the library is genuinely absent and unobtainable here, consistent with and adding new detail to the 29 Aug sudo-backed root-cause finding below. Also drove the real production `HttpVisionDetector` client class (not a synthetic check) against the freshly-exported model over a port-forwarded HTTP server, feeding two known-labeled held-out images — both correctly classified (Elephant 0.557/0.334, Boar 0.520). Fixed two stale/inconsistent claims in `docs/KNOWN_GAPS.md` that said the vision detector "is not exported or wired into anything" — both superseded, following the file's own established convention, with pointers to the fresh evidence. Full writeup in `ml/vision/README.md`'s "29-30 Aug... on-device benchmark" section. EON Tuner job `53262078` checked again at session end: still `running`, 1 completed / 3 running / 1 pending trial, no material progress since the prior check — the one completed candidate (`rgb-fomo-275`, int8 accuracy 0.384) remains far below the champion's per-class recall and has not been allowed to finish. **The ≥92%-per-class recall bar is still not met** (Elephant 0.906 at threshold 0.05, 1.4 points short; Boar 0.852, 6.8 points short) — nothing this window changed the accuracy numbers, only confirmed them for real on hardware and closed out the latency/GPU/wiring caveats. Nothing committed to git this window (no explicit user request to commit). See that checkpoint for full detail, then the still-relevant prior "RESUME HERE — 29 Aug (retrain complete, 92% bar not met; Boar heuristic closed; three-source gap check clean; GPU delegate gap confirmed permanent)" checkpoint right below it for the prior round: the standing plan's dataset-verification precondition ("verify dataset before retraining") was closed out for real — the Boar domestic-pig heuristic sample finished (17 more confirmed-bad filenames, 10 deleted live), and the three sources that had never had even a spot-check (`asian-elephants-dataset-v1`, `swg-eurasian-wild-pig`, `swg-empty`) were sampled and found clean, closing out a false alarm (tree/water categories, already filtered by the real pipeline) and surfacing a real positive finding (this source already has real night/IR frames). Separately, root-caused the GPU delegate question left open since 23 Aug: with real sudo access on the board, confirmed no apt repo (Debian, Arduino, or the Qualcomm artifactory overlay) provides `libtensorflowlite_gpu_delegate.so` — this is now a **confirmed permanent hardware/software gap**, not an access limitation; `mesa-teflon-delegate` and ArmNN's GPU backend exist but are architecturally incompatible drop-in replacements. With the dataset verified, retrained `yolo-pro-nano-attn_silu` against the fully-cleaned 12,808-image corpus (9,775 train / 3,033 test, confirmed matching live) — real held-out numbers: **Elephant recall 0.781** (P 0.974, F1 0.727), **Boar recall 0.706** (P 0.987, F1 0.656), Background false-positive rate 0.028. Both real improvements over the 26 Aug FOMO baseline (Elephant +8.8 pts, Boar +4.0 pts) but **neither clears the ≥92%-recall bar** — precision is very high on both classes, so the gap is concentrated in silent misses (zero predictions on 11.1% of Elephant / 23.5% of Boar test images), which is exactly what a threshold sweep is meant to probe; that sweep was launched immediately after and its result is the next thing to check. See that checkpoint for full detail, then the still-relevant prior checkpoint right below it: a full 142-image visual audit of `elephant-detection-cxnt1-v2`'s bare-Roboflow-numbered filename bucket (a third naming shape none of the prior three data-quality passes had covered) found 61 confirmed-bad images (43%) across four defect types — 9 more African bush elephant, 4 not-an-elephant-at-all (masked-crowd photos), 4 wrong-domain (historical/studio), 19 watermarked stock, 25 captive/managed-care domain — fixed locally (two exclude-list constants in `scripts/edge_impulse_upload_vision.py`, `--dry-run`-verified exact 52/52 + 9 match) and live (all 61 already-uploaded samples matched by sha256 and deleted via the Edge Impulse `deleteSample` API, 0 failures). The prior "RESUME HERE — 29 Aug (degenerate-box filter + live correction, EON Tuner research)" checkpoint right below covers the still-relevant prior round: a `MIN_BOX_AREA_FRACTION` filter was added to drop boxes below 0.03% of frame area, verified against the full corpus (13 boxes across 4 sources, all 13 individually visually confirmed bad — not just small), and, because 7 of those 13 were already live in the project on images that keep other valid boxes (content-hash dedup means a plain re-upload can never fix an already-live sample's labels), corrected live via a direct `setSampleBoundingBoxes` API call — all 7 applied successfully. A backgrounded research agent also closed out the EON Tuner objective question (no native recall objective exists) and surfaced UNO Q/QRB2210 details worth folding into Phase 3/5. See that checkpoint for detail, then the "29 Aug (upload pipeline integrity)" checkpoint right after it for the still-relevant prior round: three silent pipeline bugs in `scripts/edge_impulse_upload_vision.py` (a `sample_by_group()` seeded-shuffle instability, and a filename-keyed resume ledger going stale against two regenerable sources) were found, root-caused with precise per-content-hash diffing, fixed, and verified for real against the live project — the reconciliation hard-fail gate now passes clean, `TOTAL training expected 9810 actual 9810`, `TOTAL testing expected 3069 actual 3069`, exit code 0. See that checkpoint for the full root-cause chain, then the "29 Aug" checkpoint right after it for the still-relevant prior round: a fourth data-quality pass found a wholesale new species-contamination population (233 `af_`-prefixed African-elephant filenames in `elephant-detection-cxnt1-v2`, 5x the previously-known 45), fixed and dry-run-verified locally; a second Boar visual-audit sample (n=24) added 11 more confirmed-contaminated filenames to the curated exclude list; a cross-source broadcast-clip leak (`wb_framesb`, `wb_framesa00001` — hunting-broadcast-show footage, not field photography) was found leaking into both Boar sources and filtered; and the user's standing decision on the 984-image "frame" clip (the viral RAJAMURUGAN video) was finally implemented — capped to 10 diverse representative frames via a new `cap_named_group()` mechanism. All four fixes are `--dry-run`-clean with no unexplained gap. All three live-cleanup deletes have since been run for real by the user (802 via `cleanup_broadcast_contamination_vision.py`, 13 via `cleanup_boar_visual_contamination_vision.py`, 1,008 via `cleanup_frame_clip_duplication_vision.py` across two runs after one transient network timeout) — project 1097972 is now 12,794 → 10,971 remote samples, all pending live cleanup complete. **Next: a retrain against the cleaned project is needed for honest new per-class recall numbers**, and the "source more IR/night data" thread is still open — see the checkpoint below for exact state. Earlier text retained verbatim below for continuity — see the new checkpoint first, then the "28 Aug (later still #3)" checkpoint immediately below it for the prior round's still-relevant detail: user sharpened priority to Elephant-first, urgently, target >92% recall including at night, plus an explicit audit-and-fix instruction on the existing corpus's annotation quality. Both flagged IR/night Roboflow candidates were vetted and rejected on real visual inspection (`elephant-thermal` not actually thermal; `detecting-elephants-at-night` has no downloadable export). `wcs-elephas-maximus` confirmed fully exploited (194/325, no headroom). A third data-quality audit pass found a wholesale non-field-photography batch in `elephant-detection-cxnt1-v2` — 164 filenames sharing a naming shape the existing TV-broadcast filter didn't reach, 16/16 visually sampled were not usable (Thai TV broadcast, stock photography, or wrong-species African elephant). Local filter fix implemented and verified clean via `--dry-run`. Live cleanup script written and dry-run-confirmed (165 live matches) but the actual delete was blocked by the environment's permission classifier as a live external-service action — **pending explicit user confirmation to execute**, see the new checkpoint. Earlier text retained verbatim below for continuity — see the new checkpoint first, then, unchanged from before: project 1097972's live/manifest mismatch (995 samples) was decomposed into three causes and remediated — 1,178 stale-named orphans deleted, 1,368 split-boundary-reshuffled samples moved non-destructively, 192 residual "missing" Boar samples confirmed as benign already-known duplicates and left alone; a follow-up automated fix for that residual 192/9 gap was caught in `--dry-run` before going live and reverted — it would have silently zeroed out three major sources' training data (see `ml/vision/README.md`'s "995-sample live/manifest mismatch" entry for the full story and why). EON Tuner confirmed unusable for this project (two independent live failures), deployed threshold set to 0.05 for the field test only (explicit user rationale, must revisit before real ranger alerts go live), architecture head-to-head run — YOLO-Pro-nano has real numbers (Elephant R 0.860 / Boar R 0.797 at threshold 0.05), MobileNetV2-SSD OOM-killed a second time on a platform-side batch-size limitation the API cannot override and was dropped; **honest verdict as of that pass: the ≥92%-per-class recall bar was not met by any architecture/threshold tried**, closest was 6.0 points short on Elephant and 12.3 short on Boar — this is exactly the gap the current Elephant-focused audit-and-fix pass is working against; a final retrain back to the winning YOLO-Pro-nano config was in progress as of that checkpoint. The "RESUME HERE — 28 Aug (late)" checkpoint below this one covers Track B (vision genuinely wired into the pre-decision fusion path) and remains accurate as its own current state — the two tracks are independent and both still open)

## RESUME HERE — 30 Aug, later (planning-session strategic redirect: STOP vision tuning, pivot everything to physical hardware bring-up — 2 Sept field deployment is ~3 days out and zero actuator-wiring progress has been reported since 26 Aug)

Written from the planning session after reviewing the full 26-30 Aug vision-model engagement (four
days of real, high-quality work — dataset forensics, architecture head-to-head, capacity ladder,
threshold sweep, real on-device benchmarking, and today's 2-hour foliage stress test). Five
decisions made here, each explained:

1. **Vision model tuning stops now — current checkpoint ships.** `yolo-pro-medium-no_attn_relu`,
   threshold 0.05: Elephant recall 0.906, Boar recall 0.852, 138ms real on-device latency (14x
   under the 2s budget), functional correctness verified against real hardware. Short of the
   internally-set ≥92%-per-class bar (Elephant by 1.4pts, Boar by 6.8pts), but every single-axis
   lever (architecture, capacity, threshold, dataset cleanup) has independently plateaued per the
   engagement's own record — the next real gain needs more domain-matched Elephant data, which is
   not in hand and not a 3-day task. This is the best model reached all engagement; ship it. Do not
   spend any more of the remaining ~3 days chasing the last few recall points.
2. **The 31.5% Boar false-positive rate on foliage is real but does not block deployment.** Confirmed
   in `ml/vision/README.md`: only Elephant-label detections feed the alert-fusion decision today, so
   this cannot cause a false deterrence firing in the field trial as currently wired. Ship as-is,
   with Boar detection logged-only (not alert-gating) — document this explicitly as a known,
   intentional limitation for this trial, not something to fix in the next 3 days.
3. **EON Tuner thread — close it out, don't dig further.** Job 53262078 completed (confirmed live);
   its search space never included YOLO-Pro to begin with (FOMO variants and SSD-MobileNetV2 only,
   per Edge Impulse's own documented search-space), and its one completed trial was far below the
   current champion. Nothing here can beat the manual search that already ran. Mark it closed in
   `HANDOVER.md`'s next update, don't spend more time retrieving trial-by-trial scores.
4. **Commit the vision work to git now, before anything else.** `git diff --stat` shows 12 modified
   + many new files, +18,636/-4,264 lines, uncommitted since 26 Aug — four days of real work sitting
   as working-tree-only state is a real loss-risk (one bad `git checkout`, disk issue, or session
   confusion away from losing it) and contradicts CLAUDE.md's own small-focused-commits discipline.
   Break it into logical commits (data pipeline fixes, dataset manifest, vision detector wiring,
   docs) rather than one giant commit — this is a 15-minute task, do it before touching anything else.
5. **Everything else stops. All remaining time goes to physical hardware bring-up.** Per the 26 Aug
   audit (still the last real check on this): horn, LED, and IR illuminator were all status **U**
   (unwired), nothing had ever physically fired, and `Bridge.provide()` registrations for
   `drive_horn`/`drive_led`/`pulse_ir` were all commented out — meaning the decision loop cannot
   actuate anything even once wiring exists. **Nothing in this entire 26-30 Aug window touched any
   of that** — it was 100% vision-model work. With the field trial ~3 days out, an excellent vision
   model on an unwired board does not produce a working field node. Bring-up order (unchanged from
   the 26 Aug plan, still correct): finish power bus → GPIO signal wiring → horn (wire, then
   fire-test watching/listening, not just checking the serial ack) → LED → IR (dark-room IR-cut
   filter test first) → register Bridge functions one at a time, never batched → one real filmed
   geophone-trigger-to-deterrence-response session, SAFE_MODE off. This is now the only thing that
   matters for 2 Sept.

**Key rotation note (carried forward, not resolved):** the live `EI_API_KEY` value appeared in a
command that was blocked by the permission classifier before it executed (not sent anywhere, not
printed since) — the second/third such exposure across this engagement per the standing record.
Rotating it is cheap and this session recommends it, but it remains the user's call, as previously.

## 30 Aug (2-hour live-camera stress test: real 31.5% Boar false-positive rate found on outdoor foliage, correcting the earlier 0/123 claim; local `.eim` copies pulled; training-config tutorial delivered) checkpoint (user directed a real-world stress test — "run the model on uno q for two hour and check for performance and false positive... check and doc evrey matrix" — then corrected mid-task that no animals were present and the camera was pointed at trees/leaves, reframing it as a pure false-positive stress test; user then left with explicit standing autonomy: "im going outside you do it autonomoulsy")

**Context**: after the 30 Aug on-device-benchmark checkpoint below (123-frame sample, 0 false
positives), the user asked for the exact training config behind the deployed model (delivered as a
step-by-step tutorial, sourced entirely from real job logs already in `ml/vision/README.md`), then
asked whether the model and documentation were saved anywhere — both `.eim` files (`etx_cpu_final_
0830.eim`, `etx_gpu_final_0830.eim`) were pulled from the board via `scp` into `device/mpu/models/
vision/` (already covered by the existing `.gitignore` pattern, confirmed byte-identical to the board
copies, nothing committed). The user then asked about untried Studio hyperparameters (learning rate,
batch size, freeze-backbone, augmentation, resolution) from two Studio screenshots — answered honestly
and, per the user's explicit choice ("Just document the gap"), recorded as a named-but-not-run gap in
`ml/vision/README.md` rather than acted on.

1. **Ran a real 2-hour continuous live-camera monitoring run on the board** — the user's explicit
   request, launched via the user's explicitly chosen method (foreground, 13 chunks, each under the
   Bash tool's 600s cap) after a first attempt (detached background + a literal API key in the
   command) was correctly blocked by the permission classifier. No workaround was attempted; the user
   was asked via AskUserQuestion and chose the chunked-foreground method. All 13 chunks ran clean, no
   gaps, appending to one log on the board (`monitor_2h_20260830.log`, 138.5 MB, 40,422 classify
   events, 2h02m01s wall clock, 06:53:49–08:55:50 IST). **A cached CLI login authenticates without
   `--api-key`, so no key appears in any of the 13 commands** — confirmed this before running any of
   them.
2. **Found a real, materially different false-positive rate than the earlier small sample.** 31.53%
   of frames (12,747/40,422) produced a `Boar` detection on pure outdoor foliage — zero `Elephant`
   false positives. This corrects (not merely supplements) the prior night's "0/123, zero false
   positives" claim, which was simply too small a sample (21s vs. 2 hours) to be representative. Even
   Studio's own default threshold of 0.5 does not fully clear it — 32 boxes survive at ≥0.5. Detection
   locations cluster into 4 fixed physical regions of the static frame (not noise spread evenly),
   consistent with specific leaf/branch features genuinely confusing the model, not a diffuse
   background hum. The per-chunk rate varied wildly and non-monotonically (1.2%–73.9%) across the
   dawn-to-daylight window this run spanned — flagged as most likely wind/moving-shadow driven, not
   confirmed (no wind/weather log was captured alongside the run). Full numbers (confidence histogram,
   threshold-survival table, bounding-box clustering, per-chunk table) in `ml/vision/README.md`'s
   "30 Aug — 2-hour continuous live-camera run" entry; both `ml/vision/README.md` and
   `docs/KNOWN_GAPS.md` updated with this correction, the latter noting the finding is currently
   **contained** — a Boar detection has no effect on the alert-fusion decision today (only `Elephant`
   feeds `fuse()`), so this does not create false elephant alerts, but it matters directly for the
   still-open question of whether Boar detections should ever influence deterrence tier.
3. **Latency held steady at scale**: mean 137.25ms (p50/p90/p95/p99 = 137/139/140/142ms) across
   40,227 usable samples — matches the smaller sample's 138ms almost exactly, and 5.52 FPS end-to-end
   over the full 2 hours is consistent with the earlier 5.7 FPS estimate. No degradation over a
   sustained run.
4. **What was not attempted, and why**: per-frame saving of detection events for visual
   cross-verification (the user's explicit request) was investigated (`--preview-port` probed, found
   non-functional on this CLI build; custom GStreamer pipeline overrides assessed as too risky to
   modify blind) and abandoned rather than silently dropped — reported honestly as a real limitation
   of this runner build, not solved this window. No new Edge Impulse training jobs were run this
   window, per the user's explicit "just document the gap" instruction on the untried-hyperparameter
   question.
5. **Bottom line**: the deployed 0.05 threshold has a real, hardware-confirmed nuisance-detection
   problem on at least one real outdoor scene (~31.5% of frames), concentrated entirely in the Boar
   label and currently non-actioning on the alert path. The two concrete next steps named in
   `ml/vision/README.md`: (a) an N≥2 consecutive-frame temporal-aggregation lever in the fusion layer
   to suppress single-frame flicker, and (b) capturing true-negative training data from this exact
   physical scene, the same domain-match approach that previously helped Boar recall generally. Not
   committed to git this window — no explicit user request to commit.

## RESUME HERE — 30 Aug (real on-device benchmark: CPU 138ms/~5.7fps measured, 3.9x faster than Studio's estimate; GPU delegate confirmed non-functional at runtime; functional correctness verified via HttpVisionDetector; EON Tuner still running) checkpoint (overnight autonomous session — user asleep, standing instruction: "do everything autonomously... test in uno q... benchmark and compare in the hardware and finetune... make me proud")

**Context**: user gave a standing overnight instruction before sleeping — full autonomous authority,
exhaustive tuning/config exploration, real on-device testing on the Arduino UNO Q (camera already
connected and pointed out the window, IR illuminator always-on), benchmark and compare against
Studio's estimates, fine-tune for the real deployment use case. No further user messages arrived this
window; everything below is autonomous continuation of the 29 Aug retrain's finalized checkpoint
(`yolo-pro-medium-no_attn_relu`, corrected corpus, threshold 0.05 — see checkpoint immediately below).

1. **Corrected the deploy-target identifier assumption from the original plan.** There is no runner
   target literally named `arduino-uno-q` — `--list-targets` against the real
   `edge-impulse-linux-runner` CLI shows the two targets that actually apply to this board are
   `runner-linux-aarch64` ("Linux (AARCH64)", CPU) and `runner-linux-aarch64-gpu` ("Qualcomm RB1
   (Adreno702 GPU)", BETA). A third target, `runner-linux-aarch64-qnn-ventuno-q`, is for the
   different Arduino VENTUNO Q board with a real QNN/NPU and does not apply here — our QRB2210 has no
   NPU, per ADR 0001.

2. **Exported and benchmarked the CPU build for real.** `edge-impulse-linux-runner --force-target
   runner-linux-aarch64 --force-engine tflite --force-variant int8 --download` produced
   `/home/arduino/etx_cpu_final_0830.eim` (cloud build job `53262453`, 32,445,248 bytes, no external
   dynamic-library dependencies beyond standard system libs). Ran it against the board's live,
   actually-connected camera (auto-selected — passing `--camera /dev/videoN` is rejected by this CLI
   version; it wants the camera's enumerated name, or nothing) with `--profiling --silent` for ~21s:
   **123 real inference cycles, mean classification latency 138ms (range 136-146ms), ~5.7 FPS
   end-to-end** including camera/JPEG/snapshot overhead on top of the 138ms NN inference itself. Every
   one of the 123 live out-the-window frames returned zero bounding boxes — a real, if single-session,
   0/123 false-positive data point at the deployed threshold (0.05) on genuine live footage, distinct
   from the held-out test-set FP numbers already recorded. **Studio's own Training-output page
   estimates 536ms (int8) for this exact checkpoint on the `arduino-unoq` latency-device profile — the
   real measured number is ~3.9x faster than Studio's estimate.** Real-time budget check:
   `device/mpu/services/config.py`'s `VISION_INFERENCE_TIMEOUT_S = 2.0` vs. measured 138ms — large
   headroom.

3. **Exported the GPU build and root-caused why it cannot run on this board — closing out the
   remaining half of the 29 Aug GPU-delegate finding with fresh, specific evidence.** `--force-target
   runner-linux-aarch64-gpu` built successfully (job produced `/home/arduino/etx_gpu_final_0830.eim`,
   30,928,096 bytes); the cloud build log genuinely shows `-DEI_CLASSIFIER_USE_GPU_DELEGATES=1` and
   links `-ltensorflowlite_gpu_delegate` — this is real compiled-in GPU-delegate code, not just a
   label. Launching it on the board fails immediately: `error while loading shared libraries:
   libtensorflowlite_gpu_delegate.so: cannot open shared object file: No such file or directory`.
   Confirmed via `find / -iname 'libtensorflowlite_gpu_delegate*'` and `ldconfig -p | grep tensorflow`
   that the library is absent everywhere on the board's filesystem, and `apt-cache search` turns up no
   matching package (only architecturally-incompatible alternatives like `mesa-teflon-delegate` and
   ArmNN, which the 29 Aug root-cause already ruled out as drop-ins). This matches and adds concrete
   runtime detail to the 29 Aug sudo-backed finding below — the GPU delegate target is real,
   selectable, and genuinely builds, but is currently **unrunnable on this board's stock Debian 13
   image** because the required shared library was never provisioned. Named as a v2 follow-up
   (sourcing/building a QRB2210-matched `libtensorflowlite_gpu_delegate.so`), not pursued further —
   does not block deployment since the CPU path alone comfortably clears real-time requirements.

4. **Verified functional correctness end-to-end through the real production client code**, not a
   synthetic check. Started the CPU `.eim` as an HTTP server on the board on port 1337 (the exact
   default in `device/mpu/services/config.py`'s `VISION_INFERENCE_URL`), confirmed via `/api/info`
   that it reports project 1097972, labels `["Boar","Elephant"]`, and `min_score: 0.05` — the deployed
   threshold, correctly baked in. Port-forwarded it locally and drove `device/mpu/perception/
   detector.py`'s real `HttpVisionDetector` class (a callable, `__call__(self, images) -> list
   [Detection]` — not a `.detect()` method) against two known-labeled held-out images loaded with
   `cv2.imread`: an Elephant test image correctly returned 2 Elephant detections (confidence 0.557,
   0.334); a Boar test image correctly returned 1 Boar detection (confidence 0.520). `main.py` was
   confirmed not currently running on the board, so the HTTP server was deliberately left running
   (PID 34343, `0.0.0.0:1337`) — any future `main.py` run on the board finds a live, correctly-
   thresholded, production-matching inference endpoint immediately.

5. **Fixed two stale claims in `docs/KNOWN_GAPS.md`** that said the trained vision detector "is not
   exported or wired into anything on this board" and that `cognition/fusion.py`'s VISION modality
   "stays permanently unpopulated" — both were already inaccurate as of 28 Aug and are now doubly so
   given this window's hardware verification. Followed the file's own established "superseded, left
   for traceability" convention rather than deleting the history; the entries now point to the
   already-closed 28 Aug wiring entry and this window's fresh benchmark evidence.

6. **EON Tuner job `53262078` checked twice this window, no material progress**: consistently 1
   completed / 3 running / 1 pending trial, `status: running`. The one completed candidate
   (`rgb-fomo-275`, a 96x96 FOMO MobileNetV2-a35 trial) scored int8 accuracy 0.384 — far below the
   champion's per-class recall, but this is an early/undertrained trial in a Bayesian search that
   still has SSD and stronger FOMO configs queued. Left running; not brought to completion this
   window — a multi-hour job, and blocking synchronously on it isn't appropriate outside a `/loop`.

**Bottom line, unchanged from the 29 Aug checkpoint**: the ≥92%-per-class recall bar is still not met
(Elephant 0.906 at threshold 0.05, 1.4 points short; Boar 0.852, 6.8 points short). Nothing this
window changed the accuracy numbers — the retrain and threshold sweep were already done and recorded
in the 29 Aug checkpoint below. What this window adds is real hardware confirmation that the deployed
checkpoint runs fast (3.9x faster than Studio's own estimate), is functionally correct end-to-end
through production code, produced zero false positives on real live footage, and that the GPU path,
while real and buildable, is not currently runnable on this specific board. **Next, if resumed**: let
the EON Tuner finish and re-rank any candidate that beats the champion by real per-class recall (not
its own objective, which is not confirmed to be recall — see the "3.2" note in the plan file); if
none beats it, the concrete lever still on the table is domain-matched Elephant data (the same kind of
source that closed most of the Boar gap via `swg-eurasian-wild-pig`) plus a combined architecture+data
search. No git commit made this window — awaiting explicit user request per standing CLAUDE.md rule.

## RESUME HERE — 29 Aug (retrain complete, 92% bar not met; Boar heuristic closed; three-source gap check clean; GPU delegate gap confirmed permanent) checkpoint (Track A: user woke and confirmed board reachability + sequencing — verify dataset fully before retraining)

**Context**: user woke, asked for a status/plan/time check-in, then confirmed the board is reachable
the same way as before and gave an explicit sequencing instruction — finish dataset/annotation
verification completely before starting any retrain. This checkpoint covers closing that
precondition, the retrain that followed, and a board-side investigation done in parallel.

1. **Boar domestic-pig heuristic sample closed out.** The remaining 64/120 unreviewed images from the
   28 Aug seed-20260828 sample were opened by eye. 17 more confirmed-contaminated filenames across
   defect sub-categories (domestic-breed coat/coloring, leash/tether, nursing-piglet farm scenes,
   wooden pallet/platform, warthog, hunting-trophy/posed photography, zoo/wildlife-park enclosures,
   apparent taxidermy) — including one full-resolution correction (`0241257f22543c1a`: thumbnail read
   as cattle, full-res confirmed spotted piebald domestic pigs). `--dry-run` verified an exact 20+20
   drop match, then applied live: **10/10 deleted, 0 failed** (the rest were already-excluded/not-live).
   Running total across every Boar visual-audit pass in this log: 144 distinct images opened by eye,
   40 confirmed contaminated (~28%) — explicitly a sample, not a full 10,758-image census, and not
   planned given scale. See `ml/vision/README.md`'s "29 Aug — Boar domestic-pig heuristic" entry.

2. **Final pre-retrain gap check: the three sources that had never had even a spot-check.**
   `asian-elephants-dataset-v1` (2,358 img), `swg-eurasian-wild-pig` (1,800 img), `swg-empty` (2,398
   img, background negatives) — seeded samples (seed 20260829, n=30/30/20), contact sheets, real
   stored boxes overlaid.
   - **False alarm caught and resolved, not a real defect**: the first-pass `asian-elephants-dataset-v1`
     sheet showed 8-16 overlapping boxes per image, initially read as possible tree-trunk mislabeling.
     Full-resolution check with category labels showed these were legitimate `tree`/`water` COCO
     categories the source ships alongside `elephant` — **the real upload pipeline already drops both**
     (`"drop": {"tree", "water"}`, confirmed in `DATASETS`, `scripts/edge_impulse_upload_vision.py`).
     The false alarm was in an ad-hoc throwaway verification script, not the shipped pipeline.
   - **Real positive finding**: a meaningful fraction of that same sample turned out to be genuine
     night/IR camera-trap frames (real Bushnell/ScoutGuard/XTBS trail-cam overlays) — this source
     already carries real night coverage beyond what the 28-29 Aug IR-sourcing entries credited it
     for. Worth folding into any future night-recall breakdown.
   - `swg-eurasian-wild-pig` and `swg-empty` both came back clean on full-resolution spot-checks of
     the visually ambiguous tiles (real Bushnell night frames, genuinely empty forest floor). Zero
     fixes, zero exclusions needed.
   - **Net: every distinct source in the corpus has now had a real eyes-on sample**, and every pass
     that found a real defect fixed it before this one — the honest basis for calling dataset
     verification complete enough to retrain against. See `ml/vision/README.md`'s "29 Aug — final
     pre-retrain gap check" entry.

3. **GPU delegate gap re-investigated with real root access on the board — confirmed permanent.**
   User supplied the board's sudo password live, in-chat, for one-time transient use only (never
   written to any file; used inline over SSH via `echo ... | sudo -S`; all temp probe scripts deleted
   from the board afterward). Searched all three configured apt repos (Debian trixie+backports+
   security, Arduino's own, and the genuine Qualcomm artifactory overlay) for
   `libtensorflowlite_gpu_delegate.so` — **no package anywhere provides it.** Two real alternatives
   exist (`mesa-teflon-delegate`, ships `libteflon.so`; ArmNN's GPU backend, ships
   `Arm_GpuAcc_backend.so`) but neither is a drop-in fix — differently-named libraries, different
   delegate ABIs, would require building a custom ArmNN-based runner to replace
   `edge-impulse-linux-runner` entirely. This closes the question three prior passes (23-28 Aug) left
   as "unresolved, needs a proprietary Qualcomm package this pass has no lead on" — now a confirmed
   hardware/software gap, not an access limitation. See `ml/vision/README.md`'s "29 Aug — GPU delegate
   gap re-investigated with root access" entry.

4. **Retrain executed against the fully-cleaned corpus.** `yolo-pro-nano-attn_silu`, 96×96 squash,
   100 cycles/early-stop-from-10, lr 0.001, pretrained weights, batch 16, low/low augmentation, auto
   class weights, INT8 profiling on. Corpus confirmed matching live before launch: Elephant 4,094 /
   Boar 6,083 / Background 2,631, 12,808 total (9,775 train / 3,033 test). All three jobs
   (`feature-generation`, `training`, `model-testing`) completed `successful=True` — feature gen 2.0
   min, training 30.4 min, held-out test 3.4 min. Full log:
   `ml/vision/_retrain_yolo_20260829_113403.log`.

   **Held-out per-class results** (centroid-in-box matching, grouped by ground truth, never averaged):

   | Class | Test images | Recall | Precision | F1 | Images w/ ≥1 prediction |
   |---|---|---|---|---|---|
   | Elephant | 844 | **0.781** | 0.974 | 0.727 | 750/844 |
   | Boar | 1,402 | **0.706** | 0.987 | 0.656 | 1,072/1,402 |
   | Background | 787 | — | — | — | 765/787 clean, FP rate 0.028 |

   **Neither class clears the ≥92%-recall bar.** Real improvement over the 26 Aug FOMO baseline
   (Elephant 0.693→0.781, +8.8 pts; Boar 0.666→0.706, +4.0 pts) from the corpus cleanup plus the
   FOMO→YOLO-Pro-nano architecture change, but both remain well short. Precision is very high on both
   (0.974, 0.987) — the gap is concentrated in **silent misses**: 94/844 Elephant (11.1%) and
   330/1,402 Boar (23.5%) test images got zero predictions at all at the Studio default threshold, not
   a wrong-box error. See `ml/vision/README.md`'s "29 Aug — YOLO-Pro-nano (attn_silu) retrain" entry
   for the full table and framing.

**Threshold sweep result (same day, immediately after)**: `{0.05, 0.1, 0.2, 0.3, 0.5}` against this
trained model, one classify job per point, all `successful=True`. Full log:
`ml/vision/_sweep_yolo_20260829.log`.

| Threshold | Elephant recall | Elephant precision | Boar recall | Boar precision | Background FP rate |
|---|---|---|---|---|---|
| 0.05 | **0.888** | 0.798 | **0.837** | 0.849 | 0.207 |
| 0.10 | 0.869 | 0.862 | 0.809 | 0.903 | 0.131 |
| 0.20 | 0.843 | 0.920 | 0.778 | 0.950 | 0.074 |
| 0.30 | 0.825 | 0.948 | 0.753 | 0.964 | 0.046 |
| 0.50 (Studio default) | 0.781 | 0.974 | 0.706 | 0.987 | 0.028 |

**No threshold on this grid clears 92% recall on either class.** Best case (0.05): Elephant 0.888
(3.2 pts short), Boar 0.837 (8.3 pts short) — but at the cost of a 0.207 background false-positive
rate (~1 in 5 empty scenes would false-alert), not a usable deployment operating point. Recall rises
smoothly and monotonically as threshold drops, no cliff — this is a well-behaved model whose recall
ceiling on this corpus/architecture tops out around 0.89/0.84, genuinely short of 0.92 on both classes
at every point tested. **This is not a threshold-selection problem** — closing the remaining gap needs
more/better training data (Boar trails Elephant at every threshold), a larger model than `nano`, or an
explicit tradeoff decision from the user on the bar itself. None of those is decided here.

**On-device CPU benchmark of this retrained model (same day, immediately after)**: exported v3
(job 53250199, INT8, `arduino-uno-q` CPU target) to the board over SSH, 15.6 MB `.eim`. Real,
measured: **~33.8 ms/inference, ~29.6 FPS** (`--fake-camera`, 72 frames post-warmup) — effectively
identical to the 28 Aug `yolo_bgexp` number on the same architecture/board, as expected since latency
is graph/resolution-driven, not weight-driven. Functional correctness confirmed on real content: a
real boxed Boar frame fired `{"label":"Boar","value":0.681}`, a real improvement over 28 Aug's 0.509
on a similar frame, consistent with this retrain's higher precision. RAM headroom unchanged (3.6 GiB
total / 3.0 GiB available). GPU path not re-attempted — already confirmed permanently unavailable
above. This closes the on-device half of Phase 5 for the retrained model.

**`docs/KNOWN_GAPS.md` updated twice this pass**: the GPU delegate entry moved from "open" to
"confirmed permanent hardware/software gap," and a new entry added — "Vision detector does not reach
the ≥92%-per-class-recall bar on either class, at any tested threshold" — stating the real numbers
plainly (best case Elephant 0.888 / Boar 0.837 at threshold 0.05, bought at a 0.207 background FP
rate) and naming what closing it would need (more/better data, especially Boar; a larger model size;
a different architecture; or an explicit bar relaxation decided by the user). Marked open, not blocking
the 2 Sept trial by itself since seismic/acoustic aren't gated on this number.

**Model-capacity trial (same day, after the user asked what else could close the gap)**: found live via
the API that the pipeline had been hardcoded to `sizing="nano"` (2.4M params) even though the model's
own default is `sizing="small"` (6.9M) — confirmed via `/transfer-learning-models` and
`/optimize/all-blocks`, full ladder pico(682K)<nano(2.4M)<small(6.9M)<medium(16.6M)<large(30M)<
xlarge(35M). Added a `--yolo-sizing` CLI flag to `scripts/edge_impulse_train_vision.py` (default
`nano`, backward-compatible) and retrained at `small`, identical config otherwise. Also hardened
`request()` with retry/backoff on transient connection errors after a live DNS blip killed the first
poll attempt mid-training-wait (job itself unaffected — it kept running server-side; resumed the wait
against the same job ID rather than resubmitting).

| | nano | small | medium | large |
|---|---|---|---|---|
| Boar recall | 0.706 | 0.730 | 0.770 | **0.762** ↓ |
| Elephant recall | 0.781 | 0.787 | 0.812 | **0.826** ↑ |
| Background FP rate | 0.028 | 0.017 | 0.027 | 0.024 |

Ran the full ladder through `large` (30M) — precision held flat throughout, so all of this is real
recall movement, not error-type trading. **`large` is the inflection point**: Boar recall regressed for
the first time (0.770 → 0.762) after climbing every prior step, while Elephant kept climbing (+1.4 pt,
its biggest single step). Training time kept rising too (medium 57.1 min → large 69.1 min). Gap
remaining at `large`: **Boar 15.8 pts short (worse than medium's 15.0), Elephant 9.4 pts short (best
yet)**. **Decision: stopped the ladder here, did not run `xlarge`** — Boar has shown no capacity
response for two consecutive steps while cost keeps rising, so it's no longer the highest-value next
experiment, especially for Boar specifically. Net across the sweep: capacity closed 5.6 pts on Boar and
4.5 pts on Elephant (nano→large) but doesn't reach 92% alone for either class. `medium` is the best
size/accuracy tradeoff found (real gains on both classes, no Boar regression, ~12 min cheaper than
`large`) — current best candidate for on-device benchmarking if a deployment decision is needed before
data-side work lands. See `ml/vision/README.md`'s "29 Aug — model-capacity trial" entries (four of them,
one per size) for full detail.

**Correction, this same pass**: the first version of this checkpoint's `small`-sizing writeup stated
"Boar 17.0 pts short" — an arithmetic error (92 − 73.0 = 19.0, not 17.0). Fixed here and in
`ml/vision/README.md` / `docs/KNOWN_GAPS.md`; flagging explicitly rather than letting a silently-fixed
number look like it was always right, per this project's standing honesty discipline.

**Next**: this is where autonomous dataset/retrain/benchmark work for this pass ends. Note for whoever
resumes: `device/mpu/services/reflex_loop.py`, its tests, `main.py`, and `config.py` already carry a
substantial uncommitted diff from a prior session (pulse_ir threaded concurrently with capture_burst,
matching the plan's Phase 6 recommendation) plus a new untracked `device/mpu/perception/detector.py` —
none of that was touched or re-verified this pass, it predates this window and is unrelated to the
vision work above; whoever picks this up next should check whether it's ready to commit or still
in-progress before assuming it's this session's output. Also already present but uncommitted:
`docs/decisions/0013-yolo-pro-nano-replaces-fomo-vision-detector.md`, satisfying the plan's Phase 7 ADR
requirement for the FOMO→YOLO-Pro architecture change. **From the standing vision plan specifically:
§3c-2 (Boar/Elephant domain-match Roboflow pulls) is now the clear next priority** — it targets exactly
the class (Boar) where capacity has stopped helping — with §3c-3 (pseudo-IR augmentation) as a smaller
supplementary lever for both classes. Neither was started this pass. Capacity-ladder work on this
architecture is done for now; the natural next experiment is data, not another model size.

## RESUME HERE — 29 Aug (bare-numeric-filename audit, 61 confirmed-bad images found and removed) checkpoint (Track A: overnight autonomous pass continues, user asleep, explicit full permission granted)

**Context**: the still-open Phase 1 "3a" species-verification task (30-image seeded sample of the
Elephant class) surfaced a real miss — `76_jpg.rf.48eb47f55e0de667157139bd0216f8d8.jpg`, a genuine
African bush elephant that none of the existing filters caught, because it belongs to a third,
disjoint filename shape (`<N>_jpg.rf.<hash>.jpg`, bare Roboflow auto-numbering, no place name, no
caption text) that none of the prior three data-quality passes in this source had ever scanned. One
real miss from a 30-image sample was reason enough to scan the whole shape rather than patch the one
filename and move on.

1. **142 filenames match this shape.** Unlike the `images<N>_` generic-scrape bucket (16/16 sampled
   unusable, justifying a blanket pattern filter), this bucket turned out to be a genuine mix of real
   Asian-elephant field photography and several distinct kinds of contamination — a pattern rule would
   have thrown away good data, so all 142 were opened by eye: six contact sheets (24/sheet, red box
   overlays + filename/index burned in via PIL), cross-referenced against a saved index-to-filename map.
2. **61 of 142 (43%) confirmed bad**, one explicit visually-audited list per defect type (same
   discipline `BOAR_VISUALLY_CONTAMINATED_FILENAMES` already established):
   - **9 African bush elephant** — folded into the existing `AFRICAN_ELEPHANT_VISUALLY_CONFIRMED_FILENAMES`
     (now 21 entries total). Unmistakable fan ears past the shoulder, tusked adults, savanna/waterhole
     habitat, several with a visible safari vehicle or multi-animal herd line.
   - **New `ELEPHANT_VISUALLY_CONTAMINATED_FILENAMES`** constant (52 entries), inserted before `DATASETS`
     so it's defined before first use (matching `BOAR_VISUALLY_CONTAMINATED_FILENAMES`'s own
     load-order discipline), wired into `elephant-detection-cxnt1-v2`'s `exclude_filenames`:
     - 4 **not an elephant at all** — masked-crowd/transit/airport photos, likely a mis-scraped
       pandemic-news batch that landed in this source by accident.
     - 4 **wrong domain, non-field** — a sepia Victorian mahout photo, three studio white-backdrop
       e-commerce cutouts.
     - 19 **watermarked stock photography** (Getty, iStock, Shutterstock, Alamy, BigStock, Minden
       Pictures, pixtastock, africanimagelibrary.com) — same defect class already excluded on Boar.
     - 25 **captive/managed-care domain** (zoo fencing/bars, hay bedding, a chain/rope on the animal, a
       bathing trough, a zoo logo/spectators, one ceremonial temple elephant). This is real Asian
       elephant, correctly boxed, just not field/camera-trap habitat — and it deliberately reverses the
       28 Aug `_is_named_african_elephant()` note that left one captive frame (`as_tr14`) unfiltered
       pending "a future pass, not excluded here" on one anecdote. 25 more in one 142-image bucket is
       enough evidence to act on now.
3. **`--dry-run` verified exact**: `dropped 52 (visually_contaminated)` for this source — every one of
   the 52 non-species filenames matched a real file, zero missed to a typo — alongside
   `species_contaminated` rising by the new 9. No unexplained gap.
4. **Live-side correction, same gap class as the earlier degenerate-box fix**: the local filter only
   stops future re-parsing; it doesn't touch what's already stored. Checked all 61 against the live
   project by sha256 content hash — **all 61/61 were live**, spread across both training and testing.
   Because this is whole-image contamination (wrong species/subject/domain), not a partial-box defect,
   the correct remedy is deleting the sample outright (`DELETE /api/{projectId}/raw-data/{sampleId}`,
   `deleteSample` — a different Edge Impulse endpoint than the prior `setSampleBoundingBoxes` fix used,
   confirmed via the cached OpenAPI spec), not editing `boundingBoxes`. Matched 61/61 by hash, dry-run
   printed each target sample id/category/box-count before anything was sent, then applied for real:
   **61 deleted, 0 failed.**
5. **`ml/vision/README.md` updated** — new "29 Aug — elephant-detection-cxnt1-v2: bare-numeric-filename
   gap closed, 61 confirmed-bad images removed" entry, inserted before the `<!-- LIVE_SYNC_PLACEHOLDER -->`
   marker, matching the file's existing dated-entry style. It also notes the original 27 Aug 3a
   30-image sample's Asian/African/indeterminate tally was never separately written down — the one
   number from that sample that mattered (`76_jpg`) is now fixed via this same mechanism; a standalone
   tally for that original 30 remains open but doesn't block anything.

**Next**: still open from the standing plan — the domestic-pig contamination heuristic for the two Boar
sources (deferred since before this window); a decision on whether other sources beyond this one bucket
warrant the same full-population audit rather than spot-sampling, given "no chance for errors"; an
assessment of whether more IR/night imagery is still needed for Elephant/Boar; and, ultimately, the
actual retrain against the now-further-cleaned project with real per-class precision/recall/F1 reported
against the ≥92%-Elephant-recall bar — nothing has been retrained against this latest cleanup yet.

## RESUME HERE — 29 Aug (degenerate-box filter + live correction, EON Tuner research) checkpoint (Track A: overnight autonomous pass, user asleep, explicit full permission granted)

**Context**: continuing the prior checkpoint's 262-extreme-area-box triage. The "tiny" bucket (area
< 0.0003 of frame) had 8 boxes visually confirmed bad by direct crop-and-inspect across 4 sources
(`swg-eurasian-wild-pig`, `elephant-detection-cxnt1-v2`, `wcs-sus-scrofa`, `pseudo-ir-elephant`) —
single-digit-pixel slivers on bare ground, or boxes sitting on empty road/ground beside a real animal
rather than on it, never a tight box around a genuinely tiny distant subject.

1. **Filter added**: `MIN_BOX_AREA_FRACTION = 0.0003` in `scripts/edge_impulse_upload_vision.py`,
   checked in `parse_coco()` right after the existing `zero_area` check, dropping into a new
   `degenerate_area` drops-dict key. Compiled clean.
2. **`--dry-run --limit 20` verified clean** (`EXIT=0`): the filter actually catches **13** boxes
   across the same 4 sources, not just the 8 originally sampled (elephant-cxnt1-v2: 8, wcs-sus-scrofa:
   1, swg-eurasian-wild-pig: 3, pseudo-ir-elephant: 1). The 5 not in the original sample were pulled
   out and individually crop-inspected the same way — 5/5 also confirmed genuinely degenerate (a
   red-dot-sized box floating in grass/mid-air near, not on, a real animal; two of the five turned out
   to be watermarked African-elephant stock photos, both already independently caught by the existing
   `_is_named_african_elephant` "africa"-substring marker via `species_contaminated`, confirming that
   filter is doing its job rather than exposing a new hole). **13/13 confirmed bad, not 8/8** — write
   this down as the real number if it's cited again.
3. **Live-correction gap found and closed.** The local parse_coco fix only stops these boxes from being
   *re-parsed*; it cannot fix a box already stored live, because Edge Impulse's `x-disallow-duplicates`
   content-hash dedup silently rejects a re-upload of identical image bytes without ever touching the
   stored labels. Checked all 13 against the live project: 6 were already excluded from upload entirely
   by pre-existing species/tv_broadcast/generic-scrape filters (never live to begin with, nothing to
   fix); the other **7 were live, each on a multi-box image (2–8 boxes) that keeps other legitimate
   boxes** — these needed a direct label correction, not just a future-proof filter. Wrote
   `fix_live_degenerate_boxes.py` (scratchpad) using the real `POST
   /{project}/raw-data/{sampleId}/bounding-boxes` (`setSampleBoundingBoxes`) endpoint — confirmed via
   the live OpenAPI spec, not assumed — dry-run matched all 7 target hashes to their live sample IDs
   and confirmed the exact bad-box geometry was present in each one's current `boundingBoxes` (no
   mismatches, no sample would be left at 0 boxes), then ran with `--apply`: **all 7 succeeded**
   (`{"success": true}` each), each losing exactly its one degenerate box and keeping every other box
   on that image untouched. This is real, verified, already-applied live-data cleanup — not a plan.
4. **EON Tuner + broader-resources research agent completed** (see its full report in-session; not
   re-copied here in full). Headline finding: **the EON Tuner has no native recall/precision/F1
   objective** — only `minimize validation loss / latency / RAM / ROM` are selectable run objectives;
   recall is a post-hoc results-sort only, confirmed via 5 independent sources (the live
   `edgeimpulse-api` PyPI package's Pydantic models, 3 live Studio Tuner UI fetches, official docs, and
   an Edge Impulse staff forum reply). This makes Phase 3.2's planned fallback ("rank Tuner candidates
   by our own held-out per-class recall") the *only* correct path, not a hedge. Also surfaced: the
   official `edgeimpulse` Python SDK already parses the ingestion API's per-file response body by
   default (`UploadSamplesResponse` with successes/fails) — the exact gap this project's own
   `upload_batch()` discards, corroborating the 3d root-cause theory independently; a live forum thread
   documents real UNO Q `edge-impulse-linux` friction (libcamera needs an explicit
   `--gst-launch-args` workaround, a `kvm`-group membership fix for DMA buffer errors) worth reading
   before the 2 Sept board session; and the QRB2210 datasheet's "AI Performance: Hexagon Processor" row
   is confirmed to be an always-on audio/sensor-fusion DSP, not a vision NPU — ADR 0001's CPU/GPU-only
   framing is correct, wording could be sharpened to preempt a future reviewer's question but the
   conclusion doesn't change.

**Next**: the Phase 1 "3a" species-verification task (deterministic 30-image seeded sample of the
Elephant class, Asian vs. African) is in progress — the sample itself has been drawn
(`random.Random(20260822).shuffle()` over all 4,220 boxed real Elephant images, first 30 taken), not
yet visually scored image-by-image. Continue there next, then work back through the rest of the
standing plan's pending tasks (domestic-pig heuristic for Boar, broader dataset-quality coverage
decision, IR/night sourcing sufficiency assessment, then the actual retrain).

---

## RESUME HERE — 29 Aug (upload pipeline integrity) checkpoint (Track A: three silent reconciliation bugs found and fixed in `edge_impulse_upload_vision.py`, gate now passes clean — dataset is trustworthy, ready for the next retrain)

**Context**: after the 29 Aug dataset-quality pass below wired in `night-ojblh-v1` and reconciled the
corpus, the upload script's own hard-fail reconciliation gate (project-level TOTAL training/testing,
compared against Edge Impulse's live counts) was still failing — actual short of expected. Per the
"no chance for errors" standard this could not be waved through; root-caused with precise per-hash
diffing rather than trusting aggregate counts, in three steps:

1. **Falsified two hypotheses first** (both real diagnostic scripts, both genuinely negative results,
   not skipped): `find_orphans.py` found 0 live content hashes with no matching local source (rules
   out stale/orphaned live content); `full_corpus_audit.py` found 0 cross-label content-hash conflicts
   despite `dedupe_by_content()`'s dedup being per-label not global (rules out cross-label duplicate
   uploads). Same run also flagged 262 extreme-bounding-box-area boxes as a real but separate,
   still-open finding — not yet triaged, see Next below.
2. **`sample_by_group()` had the same seeded-shuffle instability bug already fixed once in
   `split_by_group()`** — the only dataset using `sample_target` (`wild-boar-deterrent-pzq5t-v1`, cap
   1379) reshuffles which representative image per group gets picked whenever its growing
   `exclude_filenames` contamination list changes, silently dropping previously-uploaded groups from
   "expected" on every run. Fixed the same way `split_by_group` was: lock any group that already has a
   live-stored member before shuffling the rest. Verified correct (1774 live-locked groups found,
   matching genuine accumulated history) but this alone flipped the mismatch's sign rather than closing
   it — it correctly widened "expected" without a matching upload happening, exposing bug 3.
3. **`upload_dataset()`'s resume ledger is keyed by filename, and two sources rewrite different bytes
   under stable filenames across regenerations** (`swg-eurasian-wild-pig`, populated by
   `scripts/fetch_swg_camera_traps.py`; `pseudo-ir-elephant`/`pseudo-ir-boar`, populated by
   `scripts/make_pseudo_ir_vision.py`). The ledger's filename-keyed "done" claim silently outlived the
   actual live content, so genuinely-new images were skipped every run with 0 uploaded / 0 dupes and no
   visible error. Found via `find_exact_diff.py` (a precise hash-level diff replicating the real
   pipeline order), which named the exact gap: 227 hashes expected-but-not-live (192 Boar, 35
   Elephant), 0 hashes live-but-not-expected. Fixed by switching `upload_dataset()`'s pending-gate from
   filename-ledger membership to live-content-hash membership (`live_categories`, fetched fresh from
   Edge Impulse every run) — the local ledger is still written for a human glance but no longer trusted
   to gate uploads.

**Verified for real**, not just `--dry-run`: the live upload run after all three fixes uploaded exactly
192 Boar + 35 Elephant (227 total, matching the diff's prediction exactly) and the reconciliation gate
now prints `TOTAL training expected 9810 actual 9810`, `TOTAL testing expected 3069 actual 3069`,
exit code 0 — clean pass, no mismatch flag. Per-label lines still show apparent gaps (e.g. Elephant
training "expected 3063 actual 2589") but these are the reconciliation function's own documented-unreliable
per-label counts (Edge Impulse's label-filtered count structurally undercounts a class's own
zero-box background images) — the TOTAL line is the real gate and it passed.

**Next**: triage the 262 extreme-area boxes flagged above (real, secondary, not yet acted on). Build
and hand-validate the domestic-pig contamination heuristic for the two Boar sources (deferred behind
this integrity work). Hand-review a validation sample. Then the retrain the user asked for
("after fixing the dataset start training", target >92% recall per class, Elephant-first) — dataset is
now honestly reconciled and ready for it, but no retrain has been run yet against this corrected state.

## RESUME HERE — 29 Aug checkpoint (Track A: second real Elephant IR source found + wired, IR hardware bypass talked through, full dataset reverified clean)

**`night-ojblh-v1` — second real Elephant IR/thermal source, found and wired in.** User-supplied
Roboflow lead (`wild-boar-fmkcg/night-ojblh` v1, CC BY 4.0). Visually verified 12/12 sampled images by
eye before touching the pipeline: genuine low-res thermal-camera output (bright heat-signature
silhouette against a cooler dark background, authentic sensor noise), not RGB and not stock. ~6/12
unambiguous elephant, several with a farm/perimeter fence rail in frame — a strong domain match to
this project's own forest-farm-boundary deployment context. Added as a new `DATASETS` entry in
`scripts/edge_impulse_upload_vision.py`; the frozen v1 export carries 56 real Elephant boxes across 73
images (17 correctly dropped via `drop: {"wild-boar"}` — that class has zero labeled instances in this
version). Same page-vs-export box-count mismatch already seen twice before (page says 73, export says
56) — documented in the entry's own comment. `ml/vision/README.md`'s dated Elephant-IR section updated
to add this finding and correct its now-stale "only Elephant IR source" closing line — two real sources
now wired in (`wcs-elephas-maximus` 194 images + `night-ojblh-v1` 73 images/56 boxes).

**IR illuminator — permanently-on bypass talked through for tonight's manual capture, not yet done by
the user as of this checkpoint.** User has no time for MOSFET switch-stage wiring tonight. Confirmed
safe path from `hardware/WIRING_GUIDE.md` §5: the downstream IRLZ44N/LR7843 MOSFET is only an on/off
gate switching the ground return, doing zero voltage regulation — safe to skip entirely and wire the
XL4015 buck's output straight to the IR board, **as long as the buck itself stays in the circuit**
(never wire the IR board straight to the raw 12.8–14.6V battery rail, ~22% over its fixed-12V spec).
Buck output should be multimeter-verified at ~12V with no load before connecting, per the guide's own
first-power-on checklist. This produces real night/IR **background** frames (no wild elephant will pass
a residential window) for the true-negative gap — not a substitute for real Elephant-positive IR data.

**Full dataset reverified end-to-end via `--dry-run --limit 20`** (all 13 real + 2 synthetic
`DATASETS` entries): every source parses clean, no unexplained drops, reconciliation table balances.
Confirms `night-ojblh-v1` is wired correctly alongside everything from the prior data-quality pass with
no regression.

**Other leads chased and closed out, not integrated:** `elephant-detection-ccpkz/elephant-deetector`
(tourism/mahout photography, wrong domain — rejected), Aerial Elephant Dataset (African species +
aerial RGB + dot-annotations, triple-disqualified), iWildCam 2022 (confirmed a repackaging of WCS
Camera Traps already in use, no new content), Salakpra Sanctuary PMC paper and China's Xishuangbanna
Elephant Early-Warning System (both real IR camera-trap infrastructure, neither has a public
image/video dataset release). Two YouTube
links the user sent (a search-results page and a specific video) could not be retrieved — WebFetch hit
a Google CAPTCHA wall on the video both directly and via its resolved watch-page redirect. Told the
user honestly rather than guessing at content, and flagged that YouTube video content sits outside this
project's established CC-BY/CDLA-only sourcing discipline regardless (YouTube's ToS restricts
downloading independent of the uploader's stated license) — open to a specific channel with genuine
reuse terms if one turns up, not pursued as a general source.

**Next:** the board's own manual IR-illuminator night capture session (through the user's window) is
done — 207 clean frames banked across 4 sessions (29 Aug, see `ml/vision/README.md`), pending a
`board-captures-night1` `DATASETS` entry alongside `board-captures-day1`. `praveenmn75/elephant-thermal`
was followed up 29 Aug via the real export API and rejected outright, not just "needs filtering" — see
`ml/vision/README.md`'s "followed up 29 Aug" entry for the corrupted-classmap/wrong-label-ratio/
screen-recording-provenance findings. Not an open lead any more. Retrain against the now-further-expanded
corpus stays deferred per the user's earlier explicit choice (keep sourcing over retraining now) — do not
start one without an explicit user redirect.

## RESUME HERE — 28 Aug (later still #4) checkpoint (Track A: fourth data-quality pass — af_/as_ species contamination, boar broadcast-clip leak, frame-clip cap — all fixed, dry-run-clean, and all three live deletes now landed; retrain + IR/night sourcing next)

**Species contamination, 5x larger than previously known**: `diag_reconcile_vision.py`'s live/manifest
orphan report turned up 552 `elephant-detection-cxnt1-v2` filenames (233 `af_<id>`, 319 `as_<id>`) not
caught by any prior filter — a species-code naming convention from a different uploader batch than the
rest of the source. A seeded 10-per-prefix visual sample, boxes rendered, opened by eye: `af_` came back
**6/6 unmistakable African bush elephant** (fan ears past the shoulder, tusked, savanna habitat, concave
back); `as_` came back correct-species Asian elephant, left alone. Fixed by extending
`_is_named_african_elephant()` in `scripts/edge_impulse_upload_vision.py` to also match the `af_` prefix,
reusing the existing `species_contaminated` drop bucket. `--dry-run`: `dropped 278 (species_contaminated)`
for this source (was 45), Elephant real total 5,071 → 4,838. No unexplained gap.

**Boar visual audit, second pass**: a fresh n=24 sample (seed 20260822, 12 per Boar source) confirmed 11
more contaminated filenames (domestic pig, watermarked stock, captive/fenced enclosures, one more warthog)
— added to `BOAR_VISUALLY_CONTAMINATED_FILENAMES`. Consistent with the first pass's own stated caveat that
the true rate is higher than any one sample catches.

**Boar broadcast-clip cross-source leak**: `wb_framesb` and `wb_framesa00001` are genuine video-frame
sequences (group_key() already handles the naming) but visually confirmed hunting-broadcast-show footage —
baked-in channel bug and lower-third, the same defect `TV_BROADCAST_CLIP_PREFIXES` already exists to catch,
just not previously known to affect Boar. `wb_framesb` is confirmed only in `wild-boar-a1flm-v1`;
`wb_framesa00001` leaks into both `wild-boar-a1flm-v1` and `wild-boar-deterrent-pzq5t-v1`. Both prefixes
added to `TV_BROADCAST_CLIP_PREFIXES`, `exclude_broadcast_clips: True` turned on for all three Boar
`DATASETS` entries (both real sources plus `pseudo-ir-boar`, which previously carried no filter flags at
all). `--dry-run`: `wild-boar-a1flm-v1` drops 325 (tv_broadcast) + 13 (visually_contaminated, up from 9);
`wild-boar-deterrent-pzq5t-v1` drops 1,459 (tv_broadcast) + 10 (visually_contaminated, up from 3);
`pseudo-ir-boar` drops 50 (tv_broadcast). Full reconciliation table balances, no unexplained gap anywhere.

**Frame-clip subsampling — the user's still-standing decision, finally implemented**: the 984-image
"frame" clip in `elephant-detection-cxnt1-v2` (the viral RAJAMURUGAN "elephant reaching into a stopped
truck" video, baked-in "U TURN" overlay text — real elephant, documented artifact, not filtered) is cut
from 984 to **10** images via a new `cap_named_group()` function, evenly spread across the clip's numeric
frame range so the 10 kept actually span the scene's distinct beats rather than clustering. Wired via a
new per-dataset `group_caps` flag (`{"frame": 10}`), applied after the drop-count gap-check so it is
reported as its own `post-cap:` line, same convention `sample_target`/`post-sample:` already uses.
`--dry-run`: `elephant-detection-cxnt1-v2` goes from 2,286 to 1,312 parsed images; "frame" drops off the
largest-clips list entirely (now topped by `casino x103`). Full reconciliation clean.

**Three live-cleanup deletes — all run for real by the user (28 Aug), all landed clean:**

1. `python scripts/cleanup_broadcast_contamination_vision.py` — **802/802 deleted** (248
   species_contaminated + 554 tv_broadcast, the latter including the `wb_framesb`/`wb_framesa00001` boar
   matches). This script's predicate already covers everything `cleanup_species_contamination_vision.py`
   matches, so the narrower species-only script was correctly never run separately.
2. `python scripts/cleanup_boar_visual_contamination_vision.py` — **13/13 deleted** (the real live delta
   from the 11 newly-added filenames plus a couple of pseudo-IR derivatives).
3. `python scripts/cleanup_frame_clip_duplication_vision.py` — **1,008/1,008 deleted**, across two runs:
   the first hit a transient `TimeoutError` on one `DELETE` call partway through (598 landed before the
   crash); rerunning the identical command picked up cleanly because the script recomputes its drop set
   from a fresh live listing every run — it matched exactly the remaining 410 and deleted all of them.
   No data loss, no manual reconciliation needed; this pattern (rerun on transient network failure) is
   safe for all three scripts in this directory since none of them use a resume ledger.

Project 1097972 went from 12,794 → 10,971 remote samples across the three passes. All pending live
cleanup for this data-quality round is complete.

The PowerShell-native env loader that worked for the user (Windows PowerShell 5.1 has no `&&`/`source`):
```powershell
cd d:\projects\EleTect-X
Get-Content secrets\vision_pipeline.env | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq '' -or $line.StartsWith('#')) { return }
    $hashIdx = $line.IndexOf('#')
    if ($hashIdx -ge 0) { $line = $line.Substring(0, $hashIdx).Trim() }
    if ($line -eq '') { return }
    $parts = $line.Split('=', 2)
    if ($parts.Count -eq 2) {
        [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), 'Process')
    }
}
```

**Separately, not yet chased to a firm conclusion**: `cleanup_generic_scrape_contamination_vision.py
--dry-run` returned **0 matches** this pass (previously 165, documented in the prior checkpoint as
pending). Not documented anywhere as having been executed — plausibly swept up by the 995-sample
reconciliation remediation described in the "later still #2" checkpoint below, or some other intervening
action. Not re-chased since the much larger af_/as_ finding took priority; worth a one-line confirmation
in a future pass but not currently blocking anything.

**Not yet started**: with the three live deletes landed, a retrain is still needed for honest new
per-class numbers against the user's >92%-recall bar — nothing has been retrained against the cleaned
project yet. Deliberately deferred again this pass: the user chose "continue IR/night data sourcing"
over kicking off the retrain.

**"Source more good data, especially IR" — this thread's progress landed, not concluded**:
- Nkhotakota bbox-availability contradiction **resolved**: LILA's own page confirms 33,813 images do
  carry manually-drawn boxes, correcting `fetch_wcs_elephant.py`'s prior wrong claim (fixed in both its
  docstring and the `DATASETS` comment). Doesn't change the verdict — species mismatch alone already
  disqualified Nkhotakota for Elephant.
- WCS Camera Traps mined a second time for *sus scrofa* (Boar): 828 real, box-verified, species-correct
  Southeast Asian forest images (734 Indonesia + 94 Laos, 3 Bolivia outliers excluded). New
  `scripts/fetch_wcs_boar.py` ran clean — 828/828 downloaded and pixel-verified, zero failures. New
  `wcs-sus-scrofa` `DATASETS` entry, dry-run-clean (827 kept after 1 content-duplicate).
- New Roboflow source `pig-rinoz/wild-pig-at-night` (64 images) added — genuine grayscale IR trail-cam
  Boar footage, visually vetted (5-image sample, then a further 13-file investigation of two filename
  red flags — "warthog"/"domestic-pig" and a `maxresdefault*` cluster — that both cleared as real
  footage with misleading filenames, not contamination). New `wild-pig-at-night-v1` `DATASETS` entry,
  dry-run-clean (64/64, expect_images set to the real Roboflow page count).
- Full consolidated `--dry-run` across every `DATASETS` entry reconciles with no unexplained gap. Boar
  combined total: 4,935 → **5,762 images (5,562 real + 200 synthetic)**, all real gain, zero synthetic.
- `gri-public/camera-trap-data-v1` deprioritized (single generic "Animal" class, low value here) — not
  pursued further.
- Both new sources are wired in and dry-run-clean but **not yet uploaded to the live project** — that
  happens as part of the next real upload/retrain cycle. `ml/vision/README.md` now has a dated entry
  ("28 Aug — two new real Boar sources found and wired in, one Nkhotakota claim corrected") covering
  all of the above in full detail.

## RESUME HERE — 28 Aug (later still #3) checkpoint (Track A: Elephant-first data-quality audit, sharpened priority from the user)

**User's operative instruction this round** (verbatim, lightly cleaned up): focus mainly on Elephant now,
urgently — target recall above 92%, including at night. Boar is also needed but lower priority, best
effort. Re-verify and audit the elephant dataset and quality of annotations, fix what's found, with the
explicit goal that no elephant is left undetected. This supersedes the previous checkpoint's "add more
data for both classes" framing with a sharper order: Elephant first, audit-and-fix the *existing* corpus
before sourcing more.

**IR/night candidates vetted and rejected** (real visual inspection via Roboflow's public thumbnail URLs,
not trusting project names/descriptions):
- `elephant-thermal` — misleadingly named. Real sampled images are ordinary daylight color photos of a
  tiger; project classes are `{DEER, ELEPHANT, TIGER}` — a generic multi-species RGB wildlife-photo set,
  not thermal/IR imagery at all.
- `detecting-elephants-at-night` — no downloadable export (`versions: 0`, confirmed via a direct
  `1/coco` request returning 404), plus unlabeled numeric classes and a captive-enclosure domain mismatch
  visible in its own sample thumbnails.
- `wcs-elephas-maximus` (already in the corpus) confirmed **fully exploited**: 194 of 325 WCS-classified
  Indonesia frames carry a real bounding box, all 194 already in use, no headroom to top up without
  breaking the real-box-only quality discipline (`fetch_wcs_elephant.py`'s own design). SWG Camera Traps
  has no elephant category at all — corroborated independently via a fresh dataset-page search, matching
  what `fetch_swg_camera_traps.py`'s docstring already said.

**Audit finding — a real, previously-undocumented gap, third data-quality pass this session**: a seeded
visual sample of `elephant-detection-cxnt1-v2` turned up a Thai TV broadcast screenshot the existing
`TV_BROADCAST_CLIP_PREFIXES` filter didn't catch, because it uses a different naming convention
(`Image<N>_`/`images<N>_`, no hyphen) than the one that filter's hyphen-prefix matching was built for. A
full scan found **164 filenames** sharing that shape; a further 16-image visual sample of the 164 came
back **16/16 not usable** — not one uniform defect, three different ones: 10 Thai TV broadcast
screenshots (TNN, Thairath TV 32), 1 scanned stock-photo book cover, 1 watermarked Alamy stock photo, and
3 clean-looking but generic African-elephant safari stock photography (wrong species — the same problem
`AFRICAN_ELEPHANT_VISUALLY_CONFIRMED_FILENAMES` targets, just not filename-markable the same way). Full
write-up, including the secondary box-placement defect spotted in the same sample, in
`ml/vision/README.md`'s **"28 Aug — data-quality re-verification, third pass"** entry.

**Fix implemented and verified**: new `_is_generic_named_scrape()` predicate (regex-based, not a curated
list — the population is too uniform in cause to enumerate by hand) in
`scripts/edge_impulse_upload_vision.py`, gated behind a new `exclude_generic_named_scrape` flag scoped
to this one source. `--dry-run` after the change: `dropped 164 (generic_named_scrape)`, reconciliation
math balances (no `UNEXPLAINED GAP`), other sources' drop counts unchanged. New Elephant real-corpus
total after this lands: 5,071 (down from 5,235).

**Live cleanup — written, dry-run-confirmed, NOT yet executed.** All 164 were already uploaded to the
live project before this filter existed (confirmed via the per-source ledger), so this contamination has
been part of the corpus every model trained in 1097972 so far was trained on. New
`scripts/cleanup_generic_scrape_contamination_vision.py` (same structure as
`cleanup_broadcast_contamination_vision.py`) `--dry-run` against the live project found **165 matches**
(164 originals + 1 pseudo-IR frame derived from one of them) — consistent with the local filter. Running
it for real (no `--dry-run`) was **blocked by this environment's own permission classifier** as a live
external-service delete — correctly, since this is a hard-to-reverse outward-facing action. **Ask the
user to confirm before running `python scripts/cleanup_generic_scrape_contamination_vision.py` (no
flag) for real** — everything needed to do so safely (predicate reused directly from the upload script,
dry-run already matches the local fix's count) is already in place; this is the single next action.

**After the live delete lands**: a retrain is needed to get honest new per-class numbers against the
user's >92%-recall bar (explicitly including a night-subset breakdown if feasible with current data).
Boar: no new action this pass, per the user's explicit lower-priority/best-effort framing — the
previously-flagged `wild-pig-at-night`/`camera-trap-data-v1` Roboflow candidates are still unvetted and
still the natural next Boar step whenever that becomes the priority again.
actually trained and ran to completion this session against Edge Impulse project `1094260`
(`EleTect-X-Vision`): 3,280 Elephant + 1,901 Boar images from two real CC BY 4.0 Roboflow Universe
datasets, group-aware 80/20 split, held-out per-class F1 0.670 Elephant / 0.567 Boar — see the new
"23 Aug — vision classifier trained" entry near the top of "Where the project actually stands" below,
and `ml/vision/README.md`'s caveats before quoting either number anywhere (neither dataset is night-IR
footage, and nothing is exported/wired into the field path yet); separately, a code-complete acoustic
classifier upload/train pipeline was written for Edge Impulse project `1094275` (`EleTect-X-Acoustic`),
closing the training half of the "no acoustic classifier exists" gap the same way `ml/seismic/`'s model
closed it for seismic; see the "23 Aug — acoustic classifier pipeline written, not yet run" entry below
for the full state, including the hard blocker (a `FREESOUND_API_KEY` credential does not exist yet,
and neither script has run against a live project);
earlier entries below this line describe the 22 Aug late Cowork/Opus planning session hitting its usage
limit, resuming under a different account, limit resets Monday; that planning session did NOT touch
firmware/code that round, only the Robu.in report, wiring docs, and contest strategy — see the
"22 Aug late — Cowork planning session" entry further down for that state; entries below that describe
the prior software session: gunshot direct-alert path now has a real (still-not-live) transport scaffold — `send_lora_alert` added to `bridge/schema.md`/`rpc.py`, an MCU-side `bridge_send_lora_alert` stub that always acks `false`, and `reflex_loop.py`'s gunshot branch calling it for real outside `safe_mode` (`feat(mpu,mcu)` 67accdb, host-tested: pytest 224/224, `pio test -e native` 49/49); both new `Bridge.provide()` registrations stay commented out, same one-at-a-time discipline as the four pre-existing ones — the real send is still blocked on the Grove LoRa-E5 not joining, not on missing code; ADR 0007 5's acoustic fusion/direct-alert routing split now implemented and host-tested in `device/mpu/services/reflex_loop.py` (`feat(mpu)` 2183cf6), and a first seismic classifier trained on the real 14/15 Aug bench captures (Edge Impulse `1094084`, 9/9 held-out test windows, undeployed — read `ml/seismic/README.md`'s caveats before quoting that number); earlier 22 Aug live hardware session, bare board only, no actuators wired: clean field-build flash confirmed (silent console is correct/expected — flagged as a real gap below), fire-test harness fully re-verified live (all four commands + cooldown refusals), `FIRE_TEST_HARNESS` confirmed back to `0` and inert; App Lab GUI was unavailable this session — board driven entirely over SSH + `arduino-app-cli` + the board's own socat bridge, now confirmed bidirectional (`docs/eletect-x-applab-notes.md`); 20 Aug entries below — MPPT solar controller dropped for a manually-set XL4015 buck (ADR 0012, `docs(decisions)` 04d1398 + `docs(hardware)` c0ae7db), `state_machine.cpp` console prints gated off the shared LoRa wire (`fix(mcu)` b4087d1), login-page demo-account doc-drift closed with a regression test (`test(web)` 42ced90), `notify-officer-request`'s fan-out extracted and unit-tested to match `send-alert` (`test(backend)` a15ea23); 18 Aug entries below — LED/IR fire + deterrent-event footage capture wired into the MPU reflex loop; 17 Aug entries — camera path closed out on real hardware: `CAMERA_DEVICE` fixed to a udev by-id path and proven stable across a full reboot and a physical unplug/replug, `python3-opencv` installed, `capture_check.py` passing end-to-end, `Camera.open()` now retries with backoff; 15 Aug entries — multi-trial stomp validation closed on real hardware; fire-test harness software path verified on real hardware, physical actuators not yet wired — still current)

This file exists so work can continue with zero lost context if the planning session moves to a
different Claude account/session. Read this file, then `CONTEXT.md`, before doing anything else.
Nothing here should contradict `CONTEXT.md` — if it does, `CONTEXT.md` wins and this file is stale.

## Reading order for a fresh session

1. `CONTEXT.md` — frozen architecture, mission, deadlines. Read in full, it's short by design.
2. This file — current state, what's done, what's not, what to do next.
3. `docs/decisions/` — only the ADRs relevant to whatever you're about to touch (see "ADR trail" below).
4. `docs/KNOWN_GAPS.md` — the maintained list of unverified/placeholder items, organized by build call.
5. `hardware/bom/procurement-status.md` — live procurement tracker. Trust this over `bom.md`.
6. `docs/internal/CONTEST_WIN_PLAN.md` — **local-only, gitignored via `.git/info/exclude`'s
   `docs/internal/` pattern. Never reference its content or existence in any committed file, commit
   message, or the contest report itself** — it names and analyzes competing teams' real submissions,
   which must never appear in our own public repo or report. Read it for the full scoring-rubric
   breakdown and priority ordering; just don't let anything from it leak into tracked files.

## RESUME HERE — 28 Aug (later still #2) checkpoint (Track A follow-up: live/manifest reconciliation closed, data-sourcing task next)

Self-initiated diagnostic work, done while validating the prior contamination fixes (TV-broadcast +
African-elephant, see the Track A checkpoint below): the freshly-regenerated manifest and project
1097972's live raw-data counts disagreed by 995 samples, which `reconcile_project_counts()` correctly
hard-failed on. Full decomposition, remediation, and a caught-in-time near-miss are written up in
`ml/vision/README.md`'s **"28 Aug — 995-sample live/manifest mismatch"** entry — read that for the real
detail. Summary:

- **Root cause**: the 581-sample contamination cleanup shrank the candidate pool feeding
  `split_by_group()`'s seeded shuffle, which reshuffled the train/test boundary for still-live samples
  (the fourth time a filter/dedup change has done this — not a new bug, just what a seeded shuffle does
  over a resizing list).
- **Remediated live, with explicit user approval**: 1,178 stale `public__`-named orphan samples deleted;
  1,368 samples moved (non-destructively, via `POST /raw-data/{id}/move`) to the category the fresh
  manifest now expects. 1,178/1,178 and 1,368/1,368, 0 failures either pass.
- **192 residual "missing" Boar samples are not missing data** — confirmed already-known server-side
  duplicates under a sibling filename, correctly never (re-)sent. 9 small unexplained Boar orphans left
  untouched. Both are small, benign, and deliberately left unresolved this pass.
- **A fix attempted for that residual gap was caught in `--dry-run` and reverted before touching live
  data.** It would have silently zeroed `elephant-detection-cxnt1-v2`, `wild-boar-a1flm-v1`, and
  `wild-boar-deterrent-pzq5t-v1`'s contribution to the manifest — a persisted duplicates ledger, trusted
  by class label rather than verified live, turned out to carry historical self-match noise. Full
  post-mortem in the README entry; **do not re-attempt a ledger-based fix for this without diffing
  against live-fetched current state first**, the way `scripts/diag_reconcile_vision.py` already does.
- **Manifest is confirmed clean and correct as of this checkpoint** — a post-revert `--dry-run` shows all
  three affected sources back to their correct parsed/train/test counts.

**Next task, per explicit user instruction, not yet started**: "try to add more good valid data with
good bounding box for both classes and also try to make it the best by adding more ir visuals night" —
source more good-quality, well-boxed training data for both Elephant and Boar, prioritizing IR/night
visuals. Maps to the vision-model-rebuild plan's Phase 4 (§3c-2 domain-match Roboflow/LILA sources,
§3c-3 pseudo-IR synthetic augmentation) and revisits §3c-1 (real field IR footage, previously deferred
as opportunistic/tied to the 2 Sept trial — worth reconsidering now given this explicit ask). Two
Roboflow candidates were flagged earlier but never visually vetted: `elephant-thermal` and
`detecting-elephants-at-night`. Check the Roboflow `eletect` workspace's remaining credit balance
before any new pull (was 14/15 remaining as of 27 Aug, resets 1 Sept) and present a concrete sourcing
plan before spending it, per `CLAUDE.md`'s procurement-sourcing rule (resolve and confirm the direct
dataset/product page, never a bare search-query link). Once new data lands, expect this same
mismatch/remediation pattern a fifth time — the user has pre-approved handling it the same way
(diagnose specifically, then act) if the diagnosis is equally precise; do **not** reach for the
reverted ledger-based fix again for the accounting side of it.

## RESUME HERE — 28 Aug (late) checkpoint (Track B: vision genuinely wired into the pre-decision fusion path)

This is a separate track from the vision-model-rebuild checkpoint immediately below (Track A: dataset/
architecture work on the model itself). Track B is the architectural correction the user gave directly:
**"seismic awakes vision and vision detects elephant and then uses deterrent strategies"** — vision had
to move from a post-alert evidence-only capture into the live pre-decision path, genuinely gating what
`fuse()`/`decide()` see, not just recording frames after the alert already fired.

### What changed

`device/mpu/services/reflex_loop.py`'s `handle_footfall_event()` now, on every non-safe-mode footfall
event, opens the camera and runs a short vision-check burst through a real detector **before**
`fuse()`/`decide()` run — not only as post-alert evidence capture (which still also happens, reusing
the same already-open camera, on an actual alert). Specifically:

- New required keyword-only param `detect_vision: VisionDetectFn` (from the new
  `device/mpu/perception/detector.py`, see below).
- `trigger_monotonic` is now computed once at the top of the function and shared by both the
  pre-decision vision-check burst and the post-alert evidence burst, so `trigger_to_first_frame_s`
  stays meaningful regardless of which burst produced the first frame.
- The camera is opened once and closed once — never reopened between the pre-decision check and the
  post-alert evidence capture.
- A new `_vision_reading()` helper turns the vision-check burst into a `ModalityReading`: no frames ->
  unavailable; `detect_vision()` raising `DetectionError` -> unavailable, logged (same "degrade loudly,
  never block" discipline as a `CameraError`); a clean result with no `VISION_TARGET_LABEL` ("Elephant")
  match -> available at `cognition.config.BASELINE_VISION` (net-zero fusion contribution — the honest
  middle ground between ignoring a sub-threshold check and inventing an unsupported negative log-odds);
  a match -> available at `logit()` of the strongest match's confidence.
- `SAFE_MODE`'s existing contract is preserved exactly: the whole new camera-open + vision-check block
  is gated behind `not safe_mode`, so `SAFE_MODE` still suppresses the camera entirely, not just the
  actuators — at the documented cost that a `SAFE_MODE` dry-run log no longer previews exactly what a
  live run would decide (vision never runs in `SAFE_MODE`).
- `handle_acoustic_event()` is untouched — acoustic events do not wake vision, matching the directive's
  scoping to footfall events only. Its `VISION` reading stays hardcoded unavailable.

`device/mpu/perception/detector.py` is new: `HttpVisionDetector`, a stdlib-only (plus a function-local
`cv2` for JPEG encoding, matching `perception/camera.py`'s own documented departure) HTTP client for the
`edge-impulse-linux-runner --run-http-server` endpoint already confirmed live on the board 28 Aug
(`GET /api/info` -> labels `["Boar", "Elephant"]`, 96x96x3 input, `min_score 0.5`; a real Boar image
classified correctly at confidence 0.777 in ~20ms). Uses the runner's HTTP server rather than the
`edge_impulse_linux` Python SDK because that SDK needs `pip`/`ensurepip`, neither of which exists on the
board's Python 3.13.5 image and there is no sudo credential to install either — confirmed 28 Aug.

`device/mpu/main.py` now constructs one `HttpVisionDetector` at module scope (pointed at
`services/config.py`'s `VISION_INFERENCE_URL`, same "construct once, no I/O until called" pattern as
`_camera`) and passes it as `detect_vision=` into the real `handle_footfall_event()` call.

### Verification done

- Full `device/mpu` test suite: **229/229 passing**, including four new tests added specifically to
  prove the wiring is real and load-bearing, not cosmetic: `test_a_qualifying_vision_match_raises_the_
  fused_probability`, `test_a_non_target_label_detection_still_contributes_nothing`, `test_vision_
  detect_failure_is_logged_and_reported_unavailable`, `test_vision_check_runs_before_decide_even_
  without_an_alert`.
- `python -m ruff check .` (from `device/mpu`): all checks passed.
- `python -m py_compile` on every touched file: clean.
- `docs/KNOWN_GAPS.md` updated: the vision-detector entry marked **closed** (28 Aug) with the design
  rationale above, and the sensor-fusion-readings entry updated to point at it. Three new open
  sub-items recorded there: no production supervision/boot-persistence of the
  `edge-impulse-linux-runner` process yet (medium-high severity for the 2 Sept trial); the night/
  no-IR-before-decision limitation (deferred to ADR 0003); whether a Boar detection should ever affect
  the alert/tier (open question, not yet decided).
- `ml/vision/README.md`'s stale scope note (which said vision was "not yet wired into
  `cognition/fusion.py`'s live alert path") corrected to point at this closure.

### What is NOT yet done

- **Live verification over SSH on the real board has not happened.** This closure is code-complete and
  host-test-verified only. Before trusting it for the 2 Sept trial: start the
  `edge-impulse-linux-runner --run-http-server` process on the board, flip `ELETECT_SAFE_MODE=0` for a
  controlled test with a human present, trigger a real footfall event, and confirm the logs show a real
  `VISION` contribution (not just `available=False` from a runner that never started).
- **The runner process has no supervision** — nothing restarts it on crash or starts it on boot. If it
  is not already running when a footfall event fires, `detect_vision()` raises `DetectionError` and
  `VISION` silently degrades to unavailable — not a correctness bug (matches the "degrade loudly, never
  block" contract) but a real availability gap worth closing before the trial if there is time.
- **Nothing has been committed.** `git status` shows real, uncommitted changes across
  `device/mpu/services/reflex_loop.py` + its test, `device/mpu/main.py`, the new
  `device/mpu/perception/detector.py`, `docs/KNOWN_GAPS.md`, and `ml/vision/README.md`. Per
  `CLAUDE.md`, do not commit without the user's explicit ask — left staged-but-uncommitted pending
  review, same discipline the Track A checkpoint below already documents for its own changes.
- Track A's remaining items (Boar-contamination remediation, a final clean retrain, EON Tuner full
  custom search) are unaffected by this track and remain exactly as the checkpoint below describes.

## RESUME HERE — 28 Aug (later still) checkpoint (Track A: EON Tuner blocked, architecture head-to-head done, honest verdict on the ≥92% bar)

Direct continuation of the Track A checkpoint below, per the user's explicit push to maximize vision
accuracy before deployment. Full detail is in `ml/vision/README.md`'s three newest dated entries
("EON Tuner confirmed unusable...", "deployed threshold set to 0.05...", "architecture head-to-head:
YOLO-Pro-nano vs MobileNetV2-SSD..."); this is the short version for a fast resume.

- **EON Tuner is a dead end for this project, confirmed twice** — `POST optimize/config` with the
  YOLO-Pro search space fails `"YOLO-Pro block not found"` against both an untrained and a genuinely
  trained YOLO-Pro learn block. Do not retry this without new information from Edge Impulse support.
- **Deployed threshold is 0.05**, set live via `set-thresholds` on the project's learn block, per the
  user's explicit field-test-only rationale (no ranger alerts go out on vision during this trial, so
  the false-positive cost is free; missing an elephant is not). **Must be revisited before real ranger
  alerts go live** — the honest production range identified earlier is 0.1-0.2, not 0.05. Rebuilding
  the impulse (which the SSD attempt below did) wipes this threshold off the learn block; it must be
  re-applied to whichever block is actually live before export.
- **Architecture head-to-head**: YOLO-Pro-nano (attn_silu) has real numbers — Elephant R 0.702 / Boar R
  0.616 at default threshold 0.5, Elephant R 0.860 / Boar R 0.797 at threshold 0.05 (24.5% background
  FP rate at that point). **MobileNetV2-SSD does not** — OOM-killed a second time (exit 137) after 30
  minutes, root-caused to a hardcoded batch size in Edge Impulse's own SSD fine-tuning sub-stage that
  the API's `batchSize` field cannot override (checked the live OpenAPI schema directly — no such
  field exists). Not pursued further; the head-to-head concludes with YOLO-Pro-nano as the only
  architecture with a usable result.
- **Phase 4 data work (SWG top-up, Asian-elephant/WCS supplements, pseudo-IR augmentation) was already
  done before this window** — confirmed by re-reading the README's existing "SWG background top-up
  landed" entry, not re-run. The recall numbers above already reflect it.
- **Honest verdict, stated to the user directly and not softened**: the ≥92%-per-class recall bar is
  **not met** by any architecture or threshold actually tried. Best real result is YOLO-Pro-nano at
  threshold 0.05 — Elephant 6.0 points short, Boar 12.3 points short — traded against a 24.5%
  background false-positive rate. The remaining gap looks like a real ceiling on this corpus, most
  plausibly closed by real (not pseudo) IR/night footage and further Boar bounding-box cleanup (the
  contamination finding from the 28 Aug widened audit), neither of which this pass could manufacture.
- **In progress as of this entry**: retraining the impulse back to `yolo-pro-nano attn_silu` (96×96) —
  the SSD attempts left the project's live impulse rebuilt at SSD's 320×320 config with no trained
  weights, which is not deployable. This retrain (background task, log `/tmp/yolo_final_train.log`,
  ~38-40 min based on the earlier identical run's real timing) restores a trained, exportable model at
  the winning configuration. **Once it completes, the 0.05 threshold must be re-applied** to the new
  learn block ID before any hardware export.
- Nothing has been committed this window. `ml/vision/README.md` has three new dated entries; this file
  has this new checkpoint. No code changes — this window was entirely training-API/documentation work.

## RESUME HERE — 28 Aug checkpoint (vision-model rebuild, overnight autonomous run — Phases 1/2/6 closed, 3/4 substantially done, one action needs the user's hand)

User granted full autonomy overnight (27→28 Aug) to push the vision rebuild as far as possible toward
the ≥92%-per-class recall bar and went to sleep; this entry is written mid-run, for account/session
continuity, not at a natural stopping point.

**Resolved — cleanup, re-upload, and reconciliation all landed clean.**
`scripts/cleanup_thai_elephant_vision.py` deleted 1,315 sha256-matched `thai-elephant-dataset-v6`
samples from live project `1097972` (0 failures; the other 1,082 of the original 2,397 local files had
no remote match — most likely already removed by a first attempt that hit a 10-minute tool timeout
partway through, not a real discrepancy). Project raw-data total dropped 16,033 → 14,718, an exact
match to "1315 deleted." The follow-up live re-upload (`edge_impulse_upload_vision.py`, confirmed
`thai-elephant-dataset-v6` fully absent from `DATASETS` first via a clean `--dry-run`) applied the
split-leakage `group_key()` fix and hit its own project-level reconciliation hard-fail (986-image net
surplus vs. the manifest) — investigated fully rather than bypassed. Decomposed into: **1,140 images**
of harmless train/test category drift (fixed live via `moveSamples`, verified 0 remaining drift) and
**~1,178 images** that turned out to be a real, newly-found bug — `fetch_swg_camera_traps.py`
overwrites its annotation file instead of merging, which silently orphaned ~550 real Boar + ~628 real
Background images from an earlier fetch pass (still live and usable, just untracked; decided with the
user to leave them alone and document rather than delete or rush a merge fix). Full writeup:
`ml/vision/README.md`'s "28 Aug — `thai-elephant-dataset-v6` cleanup, re-upload, and a second real bug
found during reconciliation" entry. **One more retrain is still owed** to get a clean, uncontaminated
Elephant-class number — every accuracy number in this file and in `ml/vision/README.md` up to and
including the 28 Aug sweep entries was measured **with the contamination still present**. That retrain
is the next action, not yet started.

**Nothing is running right now.** `retrain_bg_expanded.sh` (background-expansion retrain +
threshold sweep) completed clean (exit=0 both stages). Result: the background-expansion hypothesis was
right — at threshold 0.05, recall held flat (Boar 0.760→0.764, Elephant 0.914→**0.918**, essentially at
the 92% bar) while Background false-positive rate roughly halved (38.0%→**17.9%**). Still short of
deployable: Boar recall plateaus at 0.764 across the whole sweep (doesn't climb further as threshold
drops — a data/capacity ceiling, not a threshold problem), and 17.9% FP is still too costly as-is. Full
numbers and the reasoning: `ml/vision/README.md`'s "28 Aug — SWG background top-up landed... and
pseudo-IR synthetic supplement confirmed live" entry (near the end of the file). **Next lever, not yet
started**: the Boar-side data-quality items below (contamination + duplicate-frame concerns) — Boar's
recall ceiling, not the threshold, is now the binding constraint on the 92% bar.

**Done and verified since the 27 Aug checkpoint below (which is otherwise still accurate for Phase 1):**

- **Bounding-box quality audit (explicit user ask: "verify how accurate the bounding boxes are").**
  Built a throwaway visual-QA tool, drew real stored boxes on real sampled images across every source
  in the project, found `thai-elephant-dataset-v6` (added specifically to fix Elephant species
  contamination) is itself ~50% African-elephant-contaminated on a 30-image sample with no cheap
  filename-based filter available — **dropped entirely**, cleanup script built (see above, not yet
  run). Two lower-severity findings (a domestic pig and an ad graphic boxed as "Boar" in two Roboflow
  Boar sources) and one open concern (`elephant-detection-cxnt1-v2` may have ~15/30-sample near-
  duplicate frames from one viral video, dedup not yet confirmed) flagged but not acted on — genuinely
  open items, not resolved. Full writeup: `ml/vision/README.md`'s "28 Aug — bounding-box quality audit".
- **WCS Asian elephant addition (194 real, species-verified, box-verified camera-trap images) —
  uploaded clean, 194/194, 0 duplicates.**
- **Project-level reconciliation hard-fail on that same upload run — investigated, resolved, no data
  lost.** Live `raw-data/count` queried directly and matched the run's own "actual" column exactly, so
  the mismatch was entirely in how `expected` gets computed, not in what's actually stored: (1) the
  reconciliation's `Background` query asks for a literal label that doesn't exist (Edge Impulse stores
  no-box samples as label `"-"`, not `"Background"` — a query bug, not missing data, and the real
  no-box count is *larger* than expected, not smaller); (2) `expected` is computed fresh from each
  run's own parse while `actual` is the project's cumulative total across every run this session —
  stale from when the reconciliation guard was written under a single-full-upload-into-empty-project
  assumption that this session's multiple incremental runs no longer satisfy. Not fixed in code (lower
  priority than the sweep and the 2 Sept timeline); tracked as a known gap on the reconciliation
  function itself rather than silently re-trusted next time. Full writeup: `ml/vision/README.md`'s
  "28 Aug — reconciliation hard-fail investigated" entry, directly below the bbox audit entry.
- **Phase 2 (true negatives) — done.** `swg-empty` (630 real forest camera-trap blanks, night-IR
  included, pixel-verified day/night split) and `board-captures-day1` (26 real board-captured frames)
  both uploaded as the Background class.
- **Phase 3 (architecture sweep) — substantially done, still short of the bar.** Full sweep across
  FOMO/YOLO-Pro/SSD variants ran; leader going into the 28 Aug incident-recovery pass was YOLO-Pro-nano
  attn_silu at default threshold, **0.855 Elephant / 0.761 Boar recall — still below 92% on both**. A
  real incident (two sweep stages colliding, DSP artifacts orphaned) hit and was recovered from — see
  the existing "28 Aug — incident recovery" entry. `recover.sh` (above) is the tail of that recovery,
  re-running the remaining stages (`yolo_attn2` onward) cleanly. Threshold sweep and EON Tuner run are
  part of the still-in-progress chain, not done yet.
- **Phase 4 (dataset work) — done.** WCS elephant addition and SWG boar/negative expansion (above) are
  the "domain match" half; `thai-elephant-dataset-v6` was meant to be the "species-correct Elephant
  supplement" half but was dropped for contamination (above) — `wcs-elephas-maximus` and
  `asian-elephants-dataset-v1` (audited clean) now carry that job alone. **SWG background expansion
  confirmed live and clean**: 630→2,398 real `swg-empty` images (656→2,424 combined with
  `board-captures-day1`), 0 server-side duplicates. **Pseudo-IR synthetic supplement confirmed live**:
  250 Elephant + 250 Boar generated by `make_pseudo_ir_vision.py` (CANDAR 2023 recipe), correctly
  tagged `[SYNTHETIC]` in every count, never blended into real-data totals.
- **Phase 6 — done, unchanged from the entry below** (MPU-side IR/capture concurrency fix). Re-verified
  this pass: `pytest device/mpu` **225/225** (was 224/224 pre-fix, +1 for the new overlap test),
  `ruff check` clean. No further action needed here.

**Boar bounding-box audit widened (n=9→40 per source) — the contamination is worse than first recorded,
and is now the leading suspect for the Boar recall ceiling, not lower priority any more.** Beyond the
single domestic pig originally flagged: `wild-boar-a1flm-v1` has at least 5–6 high-confidence
contamination hits (multiple domestic/captive pigs, the "swimming pigs of Exuma" photo, a warthog —
wrong species). `wild-boar-deterrent-pzq5t-v1` is worse — several boxes sit directly on black
redaction rectangles with no visible animal at all, plus captive-pen scenes, a wrong-species deer-like
hit, and a primate-like hit. `swg-eurasian-wild-pig` tight full-resolution crops (n=30) show ~27–30%
with no confidently identifiable animal, confirming the ambiguity is real, not a thumbnail artifact.
No cheap mechanical filter exists for any of this (unlike thai-elephant's content-hash approach) — full
writeup and reasoning in `ml/vision/README.md`'s "28 Aug — widened Boar bounding-box audit" entry
(last section before "Reproducing").

**Checked, and closed out: the redaction-box defect specifically is not mechanically filterable either,
and isn't the driver anyway.** Wrote a pixel-statistics scan (std-dev/mean brightness inside each stored
box) to test the one Boar defect that looked objectively checkable rather than a subjective species
call. Result: only 12 of 12,754 boxes flagged even at a relaxed threshold (~0.09%), and spot-checking
all 9 unique flags at full resolution showed only 3 are genuine redactions — the other 6 are legitimate
dark night/IR boar photos with the same low-brightness/low-variance signature as a real redaction
square. The filter is both unreliable and immaterial in scale, so it was not wired into `DATASETS`. Full
writeup in `ml/vision/README.md`'s "Checked whether the redaction-box defect specifically is
mechanically filterable" entry, right after the widened-audit section. **Net effect: no partial
automated fix exists for Boar at all — the only remaining lever is the full manual relabel, and that,
not the confidence threshold, is the recommended next step for Boar**, ahead of further
architecture/threshold tuning.

**Phase 5 (on-device benchmarking) — CPU half done for real, GPU half blocked by the board's software,
not by anything fixable from this session.** Exported `yolo_bgexp` as both target formats via
`edge-impulse-linux-runner --api-key ... --download`, non-interactively over SSH to the board at
`192.168.1.10` (reachable and controllable this whole pass). **CPU** (`arduino-uno-q`): real measured
~33.8 ms/inference, ~29.6 FPS on the board, plus a functional correctness check — a real boxed
`swg-eurasian-wild-pig` frame through the exported `.eim` correctly fired `Boar` at 0.509 confidence,
consistent with the low-threshold finding from Studio-side evaluation. **GPU** (`runner-linux-aarch64-gpu`,
BETA in Studio): exports and links cleanly, but fails to run — `libtensorflowlite_gpu_delegate.so` is
missing from the board entirely, confirmed absent both on the bare host and inside Arduino's own
official `ei-models-runner` container image. Fixing this needs a proprietary Qualcomm package this
session has no lead on, plus root (`sudo` here prompts for a password this session doesn't have) — a
genuine board-software gap, not a mistake in this pass. Full write-up:
`ml/vision/README.md`'s "28 Aug — on-device benchmarking" entry. **Practical effect: no GPU-vs-CPU
comparison exists, but the CPU number alone (~30 FPS) is already well clear of what a trigger-on-motion
camera-trap pipeline needs**, so this does not block a 2 Sept deployment decision.

Also blocked the same way, and worked around: **live camera capture via `edge-impulse-linux-runner`
needs `gst-launch-1.0`** (`gstreamer1.0-tools` package) — the board has every gstreamer *library*
installed but not that CLI-tools package, and again no passwordless sudo. Worked around with
`--fake-camera <file>` fed real board-captured/dataset frames (same decode→resize→infer path, minus the
V4L2 grab step), which is why the latency number above is trustworthy — but it means **no live day/IR-night
true-negative frames were captured this pass**; that still needs either the missing package installed by
someone with the board's actual sudo password, or a run through App Lab's own GUI.

**Not started yet**: Phase 7 (final report/ADR/close-out), and the actual remediation of the Boar
contamination above (audited, quantified, and now confirmed to have no automatable shortcut — a manual
per-image relabel of ~9,200 images is a multi-day task this close to the 2 Sept trial).

**Resolved this session**: the `elephant-detection-cxnt1-v2` duplicate-frame/split-leakage concern
flagged above turned out to be a real bug, now fixed. `group_key()` was silently failing to collapse
984 frames of one viral video (`frame0001.jpg`-style names, no separator before the counter — the
existing `_FRAME_TAIL` regex requires one), so `split_by_group()` scattered them randomly instead of
keeping the clip whole — confirmed directly against the live uploaded manifest (`frame4340` in
training, `frame4349` nine frames later in testing) and by eye (a contact sheet across the full
4339–5791 frame range is the same elephant-and-truck scene throughout). Fixed in
`scripts/edge_impulse_upload_vision.py` with a narrow fallback pattern, verified not to change grouping
for any other current dataset source. See `ml/vision/README.md`'s new 28 Aug entry for the full
write-up. Not yet applied to the live project 1097972 — the fix takes effect on the next full
re-upload, which is already pending on the `cleanup_thai_elephant_vision.py` approval below, so it
rides along with that instead of triggering a separate live-project category shuffle now.

**Nothing has been committed this session.** `git status` currently shows real, uncommitted changes
across `device/mpu/services/reflex_loop.py` + its test, `docs/KNOWN_GAPS.md`, `ml/vision/README.md`,
both `scripts/edge_impulse_*.py`, and several new untracked scripts (`cleanup_thai_elephant_vision.py`,
`edge_impulse_tuner_vision.py`, `fetch_swg_camera_traps.py`, `fetch_wcs_elephant.py`,
`make_pseudo_ir_vision.py`). Per `CLAUDE.md`, do not commit without the user's explicit ask — this is
deliberately left staged-but-uncommitted pending the user's review, not an oversight.

**Whoever picks this up next**: get the user's explicit go-ahead to run `cleanup_thai_elephant_vision.py`
(blocked by the auto-mode permission classifier, see above — a live bulk-delete against paid
infrastructure correctly needs a human, not an autonomous agent, to press go), do one final clean
retrain to get an honest Elephant number, and investigate the Boar data-quality items below (now the
actual bottleneck, not the threshold). Phase 5's CPU half is already done for real (see above) — what's
left there needs someone with the board's actual `sudo` password, physically or over SSH: install
`gstreamer1.0-tools` for live camera capture (to get real day/IR-night true-negative frames), and look
into whether a Qualcomm Adreno GPU-delegate package can be installed for the GPU latency comparison
(lower priority — the CPU number alone already clears what's needed for deployment).

## RESUME HERE — 27 Aug checkpoint (vision-model rebuild, Phase 1 closed, Phase 2/3 next)

Verified against the real repo state at time of writing. Executing the approved vision-rebuild plan
(§7 items 1–5, everything except 3c-1 real field IR footage) against the now-confirmed **Enterprise**
Edge Impulse project `1097972` (ETX-V) — a separate project from the legacy free-tier `1094260` this
file's older entries reference; do not confuse the two.

**Done and verified this session:**

- **3a species check — real contamination confirmed, not a rounding error.** The Elephant class
  (3,280 images from a Roboflow "Elephant" source with no stated sub-species) is contaminated with
  African bush elephant: 34/3,280 (1.0%) by filename alone, and 4/23 scoreable images (17.4%) in a
  seed-`20260822` visual sample scored on back-profile/forehead shape. Full writeup in
  `ml/vision/README.md`'s "27 Aug" entry. Not yet remediated — the fix (filter the 34 filename hits,
  fold in Roboflow's species-correct "Asian Elephants Dataset") is scoped to Phase 4, not done yet.
- **3d upload-gap fixes, `scripts/edge_impulse_upload_vision.py`.** The 26 Aug run under/reported
  6,489 of 6,560 expected images with "0 failures" — root cause was `upload_batch()` discarding the
  ingestion API's per-file accept/reject response body. Now parses it (duplicates tracked separately
  from real failures) and a new `reconcile_project_counts()` queries Edge Impulse's own
  `raw-data/count` endpoint post-upload and **hard-fails** on any expected-vs-actual mismatch —
  closes the exact blind spot that let "0 failures" hide a real 71-image gap. Also fixed: resume
  ledgers are now namespaced by project ID (`_ledger_path()`) so re-targeting the empty `1097972`
  doesn't silently no-op against ledgers recorded against `1094260`; a `--limit` dry-run no longer
  clobbers the committed `ml/vision/dataset_manifest.json` (caught this live — the prescribed
  verification command in the plan itself had this bug, fixed before it did real damage).
- **Live re-upload of all 6,560 images into `1097972` — DONE. Root-caused two rounds of bugs, then
  confirmed the true 71-image gap is real, structural, and does not block Phase 3.** Full detail in
  `ml/vision/README.md`'s "27 Aug — 3d upload-gap root cause" entry; summary here.
  - **Round 1 — the upload script itself.** The first run reported "0 uploaded" on every batch while
    `reconcile_project_counts()` simultaneously found the project already held a large nonzero sample
    count. Root cause: `_parse_ingest_response()` guessed the ingestion API's per-file response shape
    as `{"files": [{"file"/"name", "success", "error"}]}`; the real shape, confirmed by a live one-off
    probe request (undocumented), is **positional** — one entry per image in request order, no
    filename field of any kind: `{"success": true, "projectId", "sampleId", "fileName"}` on accept,
    `{"success": false, "error": "An item with this hash already exists (ids: ...)"}` on a duplicate.
    A second bug rode along: the duplicate-vs-real-failure classifier checked only for the substring
    `"duplicate"`, but the real rejection text says "already exists" and never that word. Both fixed
    in `_parse_ingest_response` (zips `sent_names` positionally against the response) and the
    classifier in `upload_dataset` (`edge_impulse_upload_vision.py`). Verified against real captured
    response bodies before re-running.
  - **Round 2 — the reconciliation query itself had a measurement bug.** After the Round 1 fix, the
    corrected re-upload sent all 6,560 names and every single one came back "already exists," which
    on its face looked like a ~627-image gap against the per-label counts `reconcile_project_counts()`
    was querying. Root cause: Edge Impulse's per-label `raw-data/count?labels=[...]` only counts
    samples carrying at least one box of that label — it is blind to background/zero-box images (the
    Elephant class alone has 552 of these), so a per-label comparison structurally undercounts.
    Rewrote `reconcile_project_counts()` to compare **total per-category counts, no label filter**
    against the **sum of expected counts across all classes** — this correctly reproduced the real
    gap: exactly **71 images (59 training + 12 testing), confined entirely to Boar**.
  - **Triple-confirmed the 71 is real, not a script artifact**: (1) the corrected upload script's own
    duplicate telemetry, (2) the corrected reconciliation query against the live API, (3) fully
    independent offline SHA1 hashing of the local file corpus (`hash_dupes.py`, both raw bytes and
    decoded pixels) — all three converge on exactly 71 Boar duplicate-content pairs and 0 Elephant.
    The number also exactly matches the original 26 Aug finding from the archived `1094260` project,
    strongly confirming this is a real, reproducible property of the source data (two Roboflow Boar
    exports overlapping under different `.rf.<hash>` filenames), not a fluke of this run.
  - **Verdict, recorded in `ml/vision/README.md`: training may proceed against `1097972` with this gap
    understood and documented; it does not block Phase 3.** Remediation (replacing the 71
    duplicate-collapsed Boar images with genuinely distinct ones) is deferred to Phase 4's already-
    planned Boar domain-match work (SWG Camera Traps pull), not a standalone fix — 71 of 6,560 (1.1%
    of the Boar class) is small enough to fold in rather than justify its own pass.
  - The throwaway diagnostic probe sample created while confirming the response schema (sampleId
    `3101025678`) was deleted from the live project with explicit user confirmation — nothing live
    left over from the investigation.
  - **Whoever picks this up next: Phase 1 §3d is fully closed. Proceed directly to retraining the FOMO
    control inside `1097972` (Phase 3 prerequisite) or Phase 2 (true negatives) — no further upload
    action or reconciliation work is needed first.**
- **Phase 6 (planned firmware fix, found while planning the above) — done, MPU-side.**
  `device/mpu/services/reflex_loop.py`'s `handle_footfall_event()` used to call `pulse_ir()` strictly
  after `camera.capture_burst()`; since the MCU's `pulse_ir()` blocks for the full pulse duration
  (`device/mcu/src/ir.cpp`), every night frame was captured after the illuminator had already gone
  dark. Fixed by starting `pulse_ir()` on a short-lived thread concurrent with the capture, joined
  before `drive_horn()` — proven with a real on/off-timestamp overlap test, not just a call-order
  assertion (`tests/test_reflex_loop.py::test_pulse_ir_overlaps_the_capture_window_not_after_it`).
  `pytest device/mpu` 225/225, `ruff check` clean. The correct long-term fix (non-blocking `pulse_ir()`
  MCU-side) is written up in `docs/KNOWN_GAPS.md`'s new 27 Aug entry, not implemented — six days out
  from the 2 Sept field trial is the wrong time to touch actuator-timing firmware.

**Not started yet**: Phase 2 (true negatives), Phase 3 (architecture comparison via EON Tuner —
`/api/1097972/optimize/*` confirmed reachable with the plain project key, org key not needed, see
`ml/vision/README.md`), Phase 4 (Boar domain-match + Elephant species supplement, structurally
addresses the 3a finding above, now also the natural home for backfilling the 71 duplicate-collapsed
Boar images), Phase 5 (on-device `.eim` benchmarking, board is physically connected), Phase 7 (final
report/ADR/HANDOVER close-out). Phase 1 (§3a species check, §3d upload gap) is now fully closed — the
upload/reconciliation work above is done and understood, so these can start without further
prerequisite work.

## RESUME HERE — 26 Aug checkpoint (planning/Cowork session, post-submission)

Verified against the real repo state at time of writing (not relayed from another session).
Robu.in Arduino Physical AI Challenge submission was filed 23 Aug (confirmed by the user directly).
Hackster "Invent the Future with UNO Q" submission is still open, due 30 Aug — see CONTEXT.md §10.

**Do this first, in this order:**

1. **Push `develop` to GitHub — the single highest-risk open item.** `git status` on the working
   tree is otherwise clean. `develop` is 11 commits ahead of `origin/develop` (same 11 commits as
   the 23 Aug checkpoint below — nothing has been pushed since). This planning session cannot push
   or even `git fetch` from its non-interactive shell — `fatal: could not read Username for
   'https://github.com': No such device or address`, meaning no credential helper is reachable
   there, and entering credentials on the user's behalf is out of scope regardless. **Action for the
   user:** run `git push origin develop` from a terminal that is already authenticated to GitHub —
   VS Code's integrated terminal on the same machine is the most likely place to have a working
   credential (Git Credential Manager / cached PAT). If that also prompts for a username, the
   underlying fix is `gh auth login` or a fresh PAT, not something to route around.
2. **Sync `main` to `develop` once the push lands.** `main` currently matches `origin/main` but is
   the same 11 commits behind `develop`. Since judges will most likely land on the default branch,
   either merge `develop` into `main` and push, or change the repo's default branch to `develop` in
   Settings → Branches — whichever the user prefers, but do it, since a stale `main` makes the
   submitted work look unfinished to anyone browsing the repo root.
3. **Repo visibility: staying Private for now, by explicit user decision (26 Aug).** Robu.in
   submission is done and doesn't need the repo public. Revisit before the Hackster submission
   (13 Sept), which does require judges to view the repo — flip Settings → General → Danger Zone →
   Change visibility → Public then, not before.
4. **Sanity-check judge visibility — deferred until the Public flip above happens, before 13 Sept.**
   Open the repo URL in a logged-out/incognito window to confirm it actually renders without auth —
   the real test, not just the toggle.
5. **Account-identity question is resolved, no action needed.** The user asked to get "my old
   github repo back in my git abhinav123krish@gmail.com" — checked: the repo's local git identity
   (`git config user.name` = `Abhinavkrishna3211`, `user.email` = `abhinav123krish@gmail.com`)
   already matches that account. There is no separate account and nothing to transfer; steps 1–4
   above are the entire remaining fix.
6. **Working-tree stragglers to clean up, low priority.** `EleTect-X_Arduino_Challenge_Report.pdf`
   and a `_to_delete/` folder are sitting untracked at the repo root (the PDF is the rendered copy
   from this session's QA pass; `_to_delete/` is leftover from an earlier device-side cleanup this
   session couldn't finish because `device_bash` can't delete files on a mounted folder). Either
   `.gitignore` the PDF (the source `.docx` is already the intentionally-uncommitted deliverable per
   the 23 Aug checkpoint below) or leave both alone — neither blocks anything, just don't let them
   get swept into an unrelated commit.
7. **Open, unresolved: Edge Impulse Enterprise account.** The user mentioned they now have an
   Enterprise-tier Edge Impulse account, with no explicit ask attached yet. Plausible reason this
   matters: the Hackster write-up (due 30 Aug) typically expects a public/shareable Edge Impulse
   project link for the vision (`1094260`) and/or seismic (`1094084`) models — worth asking the user
   directly whether the Enterprise account changes project visibility/sharing settings that need
   configuring before the Hackster submission, since that hasn't been specified yet.
8. **Priorities updated 26 Aug: field deployment complete by 2 Sept, Hackster submission by
   13 Sept (moved from 30 Aug — see CONTEXT.md §10, updated same day).** Field deployment is now the
   immediate blocker for everything else — it's real evidence for the Hackster write-up and the
   highest-leverage item outstanding per the 23 Aug checkpoint below (physical wiring, live
   fire-test, one real filmed detection→deterrence session still not confirmed done as of that
   checkpoint). Do not start the Hackster write-up pass (`edge-impulse-hackster-writeup` skill) until
   the field deployment is either done or far enough along to know what real footage/data it
   produced — writing the story before the trial happens risks the same "check whether it actually
   happened" pattern this file has had to catch repeatedly.

## Hardware bring-up test plan — 26 Aug audit, target complete by 2 Sept

User confirmed 26 Aug: no subsystem has actually been fired/tested as an assembled system yet.
Audited against `docs/KNOWN_GAPS.md`, `hardware/WIRING_GUIDE.md` §0, and this file's 20 Aug
"Where the project actually stands" section to get an honest per-subsystem baseline before bring-up
starts. Summary (see the sections named above for full detail, this is the condensed version):

- **Geophone/seismic — the one subsystem with real end-to-end field evidence.** Wired, bench
  stomp-tested 15 Aug (11/12 detected, 0 false triggers), STA/LTA constants validated against real
  data. Known open bug: actuator `delay()` calls block `loop()` up to ~3.15s during a horn fire,
  silently dropping geophone/LoRa reads during that window — unfixed, will matter once actuators
  are wired.
- **Camera/vision — partially verified.** Camera confirmed alive over USB-C/PD power (17 Aug).
  NOT yet confirmed working powered from VIN/battery instead of USB-C — real gap for the field
  power path. Whether the IR-cut filter blocks the 940nm illuminator (would blackout night
  captures) has never been tested — ~10 min bench test, high severity, do this before wiring IR.
- **Horn, LED, IR illuminator — status U (unwired), nothing has ever physically fired.** Firmware
  command-parse path is host-tested only (fire-test harness got correct acks over serial, no
  actuator was attached). `HORN_AMP_ENABLE_DELAY_MS=150` and the LED/IR burst-cap+cooldown values
  are all unmeasured engineering judgement, not bench data.
- **LoRa-E5 — physically wired but silent.** Zero response to AT probes across a full 90s capture,
  confirmed a real hardware issue (join state machine itself behaves correctly). Two untested
  hypotheses: 5V/3.3V logic mismatch, or module not in AT-command mode. Gateway is also still on
  EU868 and must be moved to IN865 before any join attempt (868 MHz is illegal in India per
  CONTEXT.md). Needs hands-on debugging, not more remote/SSH work.
- **Power/solar/battery — battery in hand, bus not finished.** Fuse + switch + full power bus per
  `hardware/WIRING_GUIDE.md` §1 checklist still needs finishing before it can feed the actuator bus.
- **MPU cognition/fusion — SAFE_MODE on by default, dry-run only.** `Bridge.provide()`
  registrations for `drive_horn`/`drive_led`/`pulse_ir`/`get_system_state` are all still commented
  out — this is the literal reason no actuator has ever been driven from the real decision loop, not
  just a wiring gap.

**Bring-up order (per `hardware/WIRING_GUIDE.md`'s own structure, one subsystem at a time, combine
last):**

1. Finish the power bus (`WIRING_GUIDE.md` §1) — nothing downstream is safe to test without this
   done and checked against the §6 "before first power-on" checklist.
2. GPIO control-signal wiring (§2).
3. Horn (§3) — wire, then re-run the fire-test harness actually watching/listening this time
   (previous runs only confirmed the serial ack, never the physical output).
4. LED deterrence (§4) — same pattern. Note the 4-channel redesign (white-L/R, blue-L/R, decided
   22 Aug) is NOT yet in firmware; either implement it first or wire the original 2-channel/6-LED
   fallback design if there's no time — both are valid per the 22 Aug decision.
5. IR illuminator (§5) — do the IR-cut-filter dark test *before* this step, not after; if the filter
   blocks 940nm the illuminator placement/approach may need to change, no point wiring first.
6. Register `Bridge.provide()` functions **one at a time, never batched** — a past batched
   registration broke every previously-working function, this is a real regression this project has
   already hit once.
7. Combine: one real filmed detection→deterrence session, geophone trigger through to an actual
   horn/LED/IR response, SAFE_MODE off. This is the single highest-leverage piece of evidence for
   both the field deployment sign-off and the Hackster write-up.

**In parallel, not blocking the above:** LoRa AT-probe silence (hands-on debug, see above) and the
IR-cut-filter dark test (do early, gates step 5's wiring decision either way).

## 23 Aug — account-switch checkpoint (planning/Cowork session, historical — superseded by 26 Aug below)

Everything in this checkpoint is real and verified against the actual repo state at the moment of
writing, not just relayed from another session's self-report. Read this block in full before doing
anything else — it supersedes any impression from the top-line summary above about what's most
urgent, since several sessions have layered updates on top of each other since 22 Aug.

**Do this first, before any new work, in this exact order:**

1. **Commit the untracked files — this is the single highest-risk open item.** `git status` shows
   all of the following as untracked, none committed, spanning real hours of work across three
   separate sessions: `hardware/WIRING_GUIDE.md`, `ml/vision/README.md`,
   `ml/vision/dataset_manifest.json`, `scripts/edge_impulse_upload_vision.py`,
   `scripts/edge_impulse_train_vision.py`, `ml/acoustic/README.md`,
   `scripts/edge_impulse_upload_acoustic.py`, `scripts/edge_impulse_train_acoustic.py` — plus
   `ml/vision/.gitkeep` deleted, and `HANDOVER.md`/`docs/KNOWN_GAPS.md`/
   `device/mcu/.vscode/extensions.json` modified. Stage and commit in small, logically-grouped,
   Conventional-Commits-style commits (e.g. one for the vision pipeline, one for the acoustic
   pipeline, one for the wiring-guide LED redesign) before touching any of these files further.
2. **Confirm the GitHub repo (`github.com/Abhinavkrishna3211/EleTect-X`) is Public.** Still
   unconfirmed as of this checkpoint — gates the Documentation portion of the contest score
   regardless of how good the code/docs are. Task #2 in the tracker, open since 22 Aug.
3. **Physical wiring, live fire-test, one real filmed detection→deterrence session — still the
   single highest-leverage item outstanding, and has not been confirmed done as of this
   checkpoint.** The contest's published rubric weighs Functionality & Execution at 40 of 100
   points, more than Documentation (20) and Presentation (15) combined. Everything below this list
   — vision/acoustic model improvement — is real and valuable but was always explicitly scoped as
   "only if there's time to spare after physical wiring is done and filmed" (see
   `docs/internal/CONTEST_WIN_PLAN.md`). If wiring/fire-test/filming hasn't happened yet, do that
   before resuming any ML work below.

**Real status snapshot, each independently verified this session, not just self-reported:**

- **Seismic model** — done, real, deployed-status honest (trained but not wired into MCU). Edge
  Impulse project `1094084`, 9/9 held-out windows, n=12 events. Nothing pending here.
- **Vision model (elephant/boar)** — trained, real numbers, underperforming: held-out F1 0.670
  Elephant / 0.567 Boar (project `1094260`). Diagnosed root cause: confusion matrix shows near-zero
  cross-species confusion but 39-43% of each animal class misclassified as background — a recall
  problem, not a discrimination problem — consistent with the actual impulse config
  (`fomo_mobilenet_v2_a35`, 96×96 input) being sized for microcontroller-grade resources when the
  real deployment target (QRB2210) has full Linux/multi-GB-RAM headroom. A detailed improvement
  prompt (increase input resolution/backbone capacity first since that's the most under-used lever,
  resolve the CONTEXT.md-vs-ADR-0001 Adreno/OpenCL-delegate inconsistency, check instance-level
  class balance, verify augmentation, consider EON Tuner or a non-FOMO architecture if capacity
  alone plateaus below ~90%) was handed to the execution session — **check whether that retrain has
  been run and report the real resulting numbers before assuming any improvement happened.**
- **Acoustic model (5-class)** — code-complete (`ml/acoustic/README.md`,
  `scripts/edge_impulse_upload_acoustic.py`, `scripts/edge_impulse_train_acoustic.py`), verified for
  real: `ruff check` clean, `pytest device/mpu` 224/224, real ESC-50 metadata fetched, 2 real clips
  downloaded/normalized byte-exact. **Blocked on two external, human-only actions, not code**: (a) a
  `FREESOUND_API_KEY` doesn't exist yet — create a free account at freesound.org/apiv2/apply/; (b)
  Mendeley's public API is behind a persistent Cloudflare bot-challenge (HTTP 403) — needs a manual
  browser visit to the dataset page to clear it. Neither script has produced a real training number
  yet; none is fabricated anywhere in the README.
- **LED subsystem redesign** — decided, documented in `hardware/WIRING_GUIDE.md` §4.0, **not yet in
  firmware**. Target: 10 LEDs (6 white + 4 blue) across 4 independent channels
  (white-left/white-right/blue-left/blue-right, D3/PB0 and D8/PB4 newly needed, both confirmed
  free), reasoned from real deterrent-effectiveness literature (unpredictable pattern beats raw
  brightness for resisting habituation) rather than enclosure space. Needs `config.h`/`led.h`/
  `led.cpp`/`bridge_handlers.cpp`/`schema.md` updated (task #11) plus a fuse-margin recheck against
  the higher LED peak power before it's wired live. The original 6-LED/2-channel plan remains a
  completely valid fallback if there's no time for the firmware change.
- **Contest report** — built and upgraded, `EleTect-X_Arduino_Challenge_Report.docx` at the repo
  root (deliberately not committed — large binary, belongs on the Robu.in portal). Real diagrams,
  real quantified testing table, real BOM. Still missing: project photos, demo video link, and a
  real circuit schematic image — all three need the physical build (item 3 above) to exist first.

Task tracker (Cowork task list, may not survive the account switch — this file is the durable
fallback) as of this checkpoint: #1 circuit schematic pending, #2 GitHub-public check pending, #10
commit untracked files pending, #11 LED firmware channels pending, #3-#9 completed.

## Goal, in priority order (per CONTEXT.md §2, reconfirmed 15 Aug)

1. **Win Arduino Physical AI Challenge India 2026** — submit ≤ 23 Aug.
2. **Win Hackster "Invent the Future with UNO Q"** — submit ≤ 30 Aug.
3. Field-deploy with Kerala Forest Department (Kothamangalam DFO approved), Aug 20, 10-day trial,
   capture real footage — this doubles as evidence for both contest submissions.
4. Scientifically rigorous, reliable, low-power, manufacturable, scalable product — not just a demo.

The Aug 20 field deployment and the two contest submissions are not separate tracks — the field
footage and real deployment story are the strongest material for both write-ups. Prioritize whatever
unblocks Aug 20 first; the contest submissions are largely a documentation/write-up pass on top of
what the field test produces (see `edge-impulse-hackster-writeup` skill when that pass starts).

## 23 Aug — vision classifier trained

`scripts/edge_impulse_upload_vision.py` and `scripts/edge_impulse_train_vision.py` both ran to
completion this session against Edge Impulse project **1094260** (`EleTect-X-Vision`). Full detail,
including both dataset citations, the exact split ledger, the impulse config, and every caveat, is
in `ml/vision/README.md`; short version:

- Two real, CC BY 4.0 Roboflow Universe datasets: `roboflow-universe-projects/elephant-detection-cxnt1`
  v2 (3,280 images, un-augmented — not v4, which is the same images 5× augmented by Roboflow itself)
  and `trackabox-4ejy9/wild-boar-a1flm` v1 (1,901 images, source class `Pig` relabeled to `Boar` —
  the dataset is titled "Wild Boar" and every filename confirms it, a source mislabel, not a judgement
  call made here).
- Group-aware 80/20 split (seed `20260822`, committed in `ml/vision/dataset_manifest.json`) so
  near-identical adjacent video frames never land on both sides of the boundary. 4,042 training /
  1,139 testing images uploaded, exact reconciliation against source counts printed and logged.
- Impulse: FOMO (`fomo_mobilenet_v2_a35`), 96×96 RGB input, `autoClassWeights` on for the 1.7:1
  Elephant:Boar imbalance, both float32 and int8 variants trained and profiled.
- **Held-out per-class F1 (real, computed from Edge Impulse's own `classify/all/result` grouped by
  each test image's ground-truth label, since that endpoint reports only a single aggregate
  pseudo-class for object-detection projects, not a per-label breakdown): Elephant 0.670 (649 test
  images), Boar 0.567 (418 test images).** Elephant outperforms Boar in both this and the separate
  training-time validation split, consistent with the 1.7:1 image-count gap — expected, not a
  surprise. **Read `ml/vision/README.md`'s six caveats before quoting either number**: neither
  dataset is night-IR camera-trap footage (both are daytime colour photography, while ADR 0001 puts
  >70% of raids at night), the background/negative sample is small and almost entirely from the
  Elephant side, and nothing is exported or wired into the field path yet.
- One real API bug found and fixed along the way, worth knowing if `edge_impulse_train_*.py` scripts
  are extended further: Edge Impulse's `POST /jobs/train/keras/{learnId}` — the call that actually
  starts a training job — silently rejects an empty JSON body with a 200-OK
  `{"success": false, "error": "Not updated configuration. No settable property found in body."}`
  rather than a normal training-job response; it has to receive the same training-parameter body used
  to configure the block, not just a bare `{}`. `edge_impulse_train_vision.py`'s `request()` helper
  now also raises on any `"success": false` response instead of surfacing a confusing `KeyError`
  further down the call site.
- `docs/KNOWN_GAPS.md` updated: the Edge Impulse project-ID gap now reads closed for seismic,
  acoustic, *and* vision; a new Build-call 3 entry tracks exporting this model to `.eim` and wiring
  it into `services/reflex_loop.py`/`cognition/fusion.py`'s `VISION` modality as separate, not-yet-
  attempted work. `ml/vision/.gitkeep` removed now that the directory holds real content.

## 23 Aug — acoustic classifier pipeline written, not yet run

**Read this bullet block first if you're resuming after this session.** `scripts/edge_impulse_upload_acoustic.py`
and `scripts/edge_impulse_train_acoustic.py` are written, complete, and mirror the style/honesty
discipline of the seismic and vision Edge Impulse scripts — but **neither has actually been executed**.
Full detail, including every source's verified license and the three originally-named sources that
turned out not to hold up under checking, is in `ml/acoustic/README.md`; short version:

- Project **1094275** (`EleTect-X-Acoustic`) will hold gunshot/chainsaw/vehicle/animal_call/ambient
  training data sourced from Mendeley `x48cwz364j` v3 (CC BY 4.0, gunshot + ambient), ESC-50's ESC-10
  chainsaw clips (CC BY), and Freesound.org text search filtered to CC0/CC BY only (vehicle + animal_call).
- **UrbanSound8K and the two originally-named elephant sources (Pardo's Zenodo/Dryad records, the
  HiruDewmi GitHub repo) were checked live and rejected** — UrbanSound8K has no per-clip license field
  and the whole distribution is CC BY-NC; neither Pardo record actually contains audio; HiruDewmi's
  repo has real audio but no declared license (`license: null` from GitHub's own API). Vehicle and
  animal_call were resourced to Freesound directly instead, decided during this session.
- **Hard blocker: `FREESOUND_API_KEY` does not exist yet.** It is a free credential, but a real one
  that has to be created by hand at <https://freesound.org/apiv2/apply/> — not something this session
  could generate. Without it, `edge_impulse_upload_acoustic.py` fails fast at its env-var check before
  touching Freesound at all; the Mendeley and ESC-50 halves of the script do not depend on it.
- Neither script has run against a live Edge Impulse project yet, but the acquisition logic *was*
  verified against real live sources from this machine, which does have real internet access: ESC-50's
  chainsaw metadata was fetched for real (40 clips, correct 32/8 fold split) and 2 real clips were
  downloaded and normalized end-to-end (8 kHz, exactly 4.0 s, byte-exact). **Mendeley's public-api
  endpoint, however, is currently answering with a persistent Cloudflare bot-challenge** (HTTP 403,
  `Cf-Mitigated: challenge`) rather than the dataset JSON — reproduced consistently across several
  attempts minutes apart, both via `requests` and (mostly) via `curl`, so this is a live external
  block on Mendeley's side right now, not a bug in the script. The upload script's `_get()` now
  detects and prints this specific case distinctly from an ordinary HTTP error, and its own comment
  records what has worked before in similar situations: opening the dataset page
  (<https://data.mendeley.com/datasets/x48cwz364j/3>) in a real browser once, then retrying shortly
  after. Freesound needs `FREESOUND_API_KEY`, unresolved for the separate reason above.
  **No training numbers exist yet; nothing in `ml/acoustic/README.md` is a fabricated result** — its
  Result section says plainly that training has not happened.
- `docs/KNOWN_GAPS.md` updated: the Edge Impulse project-ID gap now reads "closed for seismic and
  acoustic," the `report_acoustic_event` clause (d) records that a classifier now exists (in code) but
  nothing runs on the MCU, and a new entry tracks exporting/deploying this model as separate,
  not-yet-attempted work.
- Next session, once `FREESOUND_API_KEY` exists: run `edge_impulse_upload_acoustic.py`, then
  `edge_impulse_train_acoustic.py`, then transcribe the real per-class held-out numbers into
  `ml/acoustic/README.md` and `docs/KNOWN_GAPS.md` — reported per class, never averaged into one figure.

## 22 Aug late — Cowork planning session (report + contest strategy, no firmware touched)

**Read this bullet block first if you're a fresh Cowork/Opus session resuming after an account
switch.** Nothing below in this section describes code changes — the VS Code/Sonnet execution
session did no work this round; this was pure report-writing, documentation, and contest strategy
by the planning session itself.

1. **Robu.in contest report: built and upgraded, real content only.** Final file:
   `EleTect-X_Arduino_Challenge_Report.docx` at the repo root (deliberately **not** committed/tracked
   — added to `.git/info/exclude`, per the "no large binaries" rule; it's a submission artifact for
   the Robu.in portal, not repo content). Built with `python-docx` against the official contest
   template. Contains: cover/team tables filled with real registration data (`APC-2026-KL-44330`,
   track "Industrial & Sustainability AI"); a 23-row real BOM; three generated diagrams (system
   architecture, MCU pin-level wiring, code structure — all drawn from real `config.h` pin
   assignments, not invented); a quantified Testing & Results table using only real numbers already
   established elsewhere in this repo (11/12 stomp detection, 226.98Hz measured rate, camera
   reboot/replug robustness, pytest 224/224 + pio test 49/49, the real DFPlayer/linker bugs found
   and fixed). **Still genuinely missing, cannot be filled from a desk**: real project photos, a
   demo video link, and the actual circuit schematic image (task #1) — all three need the physical
   build to progress first. GitHub repo public/private status (task #2) is **still unconfirmed** —
   this is the single highest-leverage 5-minute check outstanding; it gates the Documentation score.
2. **Competitor research done — kept strictly out of git, by explicit instruction.** Reviewed two
   real competing submissions in detail (a Word report and a Hackster.io write-up) against the
   contest's actual published 100-point rubric (Functionality 40 / Innovation 25 / Documentation 20
   / Presentation 15). Full comparative analysis, priority-ordered action plan, and the ~24-hour
   schedule live in `docs/internal/CONTEST_WIN_PLAN.md` — **local-only, excluded via
   `.git/info/exclude`'s existing `docs/internal/` pattern, never to be committed or referenced by
   name/content in any committed file.** Bottom-line takeaway, safe to restate here since it names no
   competitor: documentation/diagrams are no longer the gap after item 1 above — the two things still
   worth real hours are (a) getting an actuator physically wired, fired, and filmed, and (b) the
   GitHub-public check in item 1. Read that file directly for the full reasoning; don't ask a fresh
   session to re-derive it.
3. **LED subsystem redesign, decided but NOT yet in firmware.** `hardware/WIRING_GUIDE.md` §4.0 has
   the full writeup — short version: real constraint is only 10 heatsink pucks in hand (against a
   much larger bare-LED stock), so the design target is now **10 LEDs total (6 cool-white + 4
   royal-blue), wired as 4 independent channels** (white-left/white-right/blue-left/blue-right,
   still only 2 bucks) instead of the original 2-channel/6-LED plan, so the firmware can alternate
   side and color across triggers rather than firing identically every time — reasoned from real
   deterrent-effectiveness literature (unpredictability beats raw brightness for resisting
   habituation), not from enclosure space. **Two things must happen before this is real**: (a)
   `config.h`/`led.h`/`led.cpp`/`bridge_handlers.cpp`/`schema.md` need the 2 new channels added
   (D3/PB0 and D8/PB4, both confirmed free — this is next-VS-Code-session firmware work, not done
   yet), and (b) the system's worst-case simultaneous power/current peak needs re-checking against
   the existing 6A fuse now that LED draw is higher (~22.4W vs ~13.4W at full simultaneous fire) —
   `WIRING_GUIDE.md` §4.0 has the exact numbers to redo that check against.
4. **Real risk found and flagged, not yet resolved: several genuinely valuable files are
   uncommitted.** `git status` at end of this session shows `hardware/WIRING_GUIDE.md` itself,
   `ml/vision/dataset_manifest.json`, `scripts/edge_impulse_train_vision.py`, and
   `scripts/edge_impulse_upload_vision.py` all untracked (`??`) — real work from earlier sessions
   that has never been committed. **First thing any resuming session should do is `git status` and
   get these committed** (small, focused, Conventional-Commits style, per `CLAUDE.md`) before
   anything else touches those files, so nothing is lost to a bad edit or a disk issue in the
   meantime.
5. **Net effect on priority order — unchanged from `docs/internal/CONTEST_WIN_PLAN.md`, restated
   here since that file may not survive an account switch as visibly as this one does:** (1) commit
   the untracked files above, (2) confirm GitHub repo is Public, (3) finish physical horn/LED/IR
   wiring per `WIRING_GUIDE.md` (LED section now reflects the 10-LED/4-channel target, but the
   original 6-LED/2-channel wiring is still a completely valid fallback if there's no time for the
   firmware channel-count change — don't let the redesign block getting *something* wired and
   fired), (4) live fire-test harness run, watched/filmed, (5) one real `SAFE_MODE=0` live
   detection→deterrence session, filmed, (6) time-boxed LoRa join attempt, (7) submit with margin
   before 23 Aug 11:59 PM IST.

## Where the project actually stands (20 Aug 2026)

**Completeness ranking:** `web/frontend` > `web/backend` / `web/ingest` (all essentially done) >>
`device/mcu` (real, in bench-validation) > `device/mpu` (fusion math built, integration loop missing)
>> `ml/` (`seismic/` holds a real dataset + a first trained model, 22 Aug; `vision/` holds a real
two-class dataset + a first trained FOMO model, 23 Aug; `acoustic/` holds a code-complete, not-yet-run
upload/train pipeline as of 23 Aug; `datasets/`/`evaluation/` are still `.gitkeep` placeholders).

- **`web/frontend`, `web/backend`, `web/ingest`** — built and real. Supabase schema + RLS + edge
  functions + migrations exist, MQTT→Supabase ingest bridge exists, full React PWA (public site +
  auth + ranger dashboard) exists with tests. Per `CLAUDE.md`'s deployment bar, production auth still
  needs a real transactional email provider before residents sign up with real contact info — check
  whether that's landed before treating auth as field-ready.
  - **20 Aug, doc-drift correction, not a real fix:** `docs/WEBAPP_COMPLETION_PLAN.md` still tracked
    the public login page (`src/pages/auth/Login.tsx`) as advertising a real `officer@eletect.in`
    account to anonymous visitors. That was already fixed on `develop` by an unrelated earlier commit
    (`71dacaa`, 12 Jul) whose message never mentioned the security angle, so the plan doc never got
    updated to match — the code was already safe going into this session. Closed the stale plan entry
    and added `src/pages/auth/Login.test.ts`, a source-scan regression test asserting the page never
    renders a real `@eletect.in` address, so this can't silently regress again (`test(web)` 42ced90).
  - **20 Aug:** `notify-officer-request`'s per-admin email fan-out was extracted into its own
    `fanout.ts` (`fanOut()`) with two Deno unit tests, mirroring `send-alert`'s existing
    `fanout.ts`/`fanout.test.ts` split — same reasoning: testable with a stub Supabase client, no live
    project or network needed. `index.ts` is now a thin HTTP entrypoint calling `fanOut()`; behavior
    (inputs/outputs) unchanged, confirmed via `deno check` against real `supabase-js` types
    (`test(backend)` a15ea23). Run tests from `web/backend/functions/notify-officer-request`:
    `deno test --no-check --allow-env fanout.test.ts` (`deno.exe` at `C:\Users\abhin\.deno\bin\deno.exe`
    if it's not on PATH). No `deno.json` and no Deno CI job exist in this repo — `.github/workflows/ci.yml`
    only runs `lint-python` and `web-frontend` (npm lint/build/test).
- **`device/mcu`** — real, flat `src/` layout (ADR 0010). Geophone STA/LTA, rule gate, state machine,
  horn/LED/IR drivers, LoRa AT (`mac.cpp`) all have code. **This evening's session (14 Aug, after this
  doc's last version) added a lot — read `docs/KNOWN_GAPS.md` in full, it's the accurate record, this
  bullet is just a pointer:**
  - `src/fire_test.h`/`.cpp` — manual serial-command fire-test harness (`docs/specs/mcu-fire-test-harness.md`),
    host-built and host-tested, gated behind `FIRE_TEST_HARNESS` (default 0). **Software path run on
    real hardware, 15 Aug:** flashed with the flag on, all four commands (`1`/`2`/`3`/`4`) produced the
    correct full `[firetest]` ack, and pressing `1` twice inside 30 s correctly refused the second
    attempt (`allowed=0`, cooldown gate working). **Physical activation not confirmed — horn, LED, and
    IR are not wired to the board yet**, so this only proves the command-parse/rule-gate/ack-print
    path, not that any actuator actually switches on. Flag reverted to `0` and re-flashed before ending
    the session, console confirmed silent. Re-run once wiring exists, watching/listening this time —
    see `docs/KNOWN_GAPS.md`'s fire-test-harness entry for the full detail.
  - `src/bridge_handlers.h`/`.cpp` — MCU-side Bridge adapters for `drive_horn`/`drive_led`/`pulse_ir`/
    `get_system_state`, written and host-tested. The four `Bridge.provide()` lines in `main.cpp` are
    written but commented out, one per line, explicitly pending a live one-at-a-time hardware
    registration session (a past registration attempt broke every working Bridge function on the same
    sketch — see `DEVICE_DEVELOPMENT_WORKFLOW.md` §3 — hence one-at-a-time, never a batch).
  - Geophone double-read/cadence bug — **fixed** (`millis()` cadence gate in `geophone_service()`),
    host-verified against 3 new Unity tests, but **only against the host `Wire` stub** — not yet proven
    against real ADS1115 timing on hardware.
  - `hostshim/Arduino_RouterBridge.h` — added (a real, durable fix, not a workaround) after discovering
    `SEISMIC_DEBUG_STREAM_RAW`'s committed default of `1` had been silently breaking every host
    `pio test`/`pio run` on this branch since the commit that added it. Host build is now clean again
    against the tree exactly as committed — confirmed by literally running it, not just reading the code.
  - **Completed 14 Aug, live hardware session:** the recheck task above finished. Findings:
    - `arduino-app-cli monitor` is **confirmed still silent** — two fresh tests (10s, 12s, debug log
      level) against a freshly-flashed, guaranteed-verbose build produced zero bytes. Not a stale
      finding — reproduced directly this session. New discovery: the underlying serial data is fine —
      a pre-existing root-owned `socat` daemon on the board bridges `/dev/ttyGS0` to
      `tcp:127.0.0.1:7500`, and that port delivers correct, well-formed, full-rate console output
      (confirmed via `ssh ... nc 127.0.0.1 7500`, captured and parsed 399 real lines). So the failure
      is specific to `arduino-app-cli monitor`'s own relay/display logic, not the firmware or the
      serial transport — App Lab's browser Serial Monitor (or the socat/nc bridge) remain the working
      alternatives.
    - **Wire vs Wire1: settled, `Wire` is correct.** Confirmed from the board's own generated
      devicetree, not inference: the `arduino:zephyr` core declares `Wire`/`Wire1`/... in the order
      listed by the board overlay's `zephyr,user { i2cs = <&i2c2>, <&i2c4>, <&i2c3>; }` — i2c2 is
      first, so it's `Wire`. The generated `.dts` shows i2c2's `pinctrl-0` is
      `i2c2_scl_pb10`/`i2c2_sda_pb11` and the node is aliased `arduino_i2c` (the default Arduino I2C
      header) — an exact match for `config.h`'s documented PB10/PB11 pins. `config.h`'s comment is
      updated with this and no longer says "unconfirmed."
    - **Cadence-gate fix: verified against the real ADS1115.** Captured 6s / 399 lines of real console
      output over the socat bridge; 369 raw-volts lines, 0 unparsed/garbled lines. Duplicate-adjacent
      pairs: 42/368 (~11.4%), max run length 4 — consistent with genuine sensor noise-floor repetition,
      not the old un-gated-polling bug (which would show much higher-frequency, longer runs). Also
      launched `scripts/live_seismic_plot.py` live against the real stream for direct visual
      confirmation.
    - **New finding, not previously measured:** the achieved raw-sample accept/print rate is only
      **~61.5 Hz**, well under the nominal 250 SPS the STA/LTA window sizing assumes — under this
      debug/bench build specifically (which carries `Bridge.update()` + `lora_service()` overhead not
      present in the field build), the 512-sample window spans ~8.3s of wall-clock time, not the
      assumed ~2.05s, and `STA_SAMPLES`/`LTA_SAMPLES` stretch proportionally. Root cause not yet
      profiled (plausibly per-`loop()`-iteration I2C + Serial + Bridge overhead exceeding the 4ms gate
      floor) — needs re-measuring on a field-flag build (`SEISMIC_DEBUG_STREAM_RAW=0`) before deciding
      whether STA/LTA sample counts need retuning, since the debug build's overhead may not reflect
      the real field rate.
  - **Real geophone bring-up finished, live hardware session, 14 Aug night — this is the actual
    "Rung 1" close-out.** Full derivation in `docs/KNOWN_GAPS.md`'s "STA/LTA field-flag rate
    re-measurement and real stomp-test calibration" entry; summary here:
    - **Real field-flag sample rate: 226.98 Hz**, measured on the actual lean field-deployment build
      (every `SEISMIC_DEBUG_*`/`FIRE_TEST_HARNESS`/`SEISMIC_DEMO_MODE` at 0) — confirms the earlier
      ~61.5 Hz figure was debug/Bridge overhead, not a hardware ceiling. At this real rate,
      `STA_SAMPLES=25`/`LTA_SAMPLES=250` work out to ~110 ms / ~1.10 s, both inside the literature
      targets (Wijayakulasooriya et al. arXiv:2406.05140; Trnkoczy/Güralp STA/LTA sizing guidance) —
      no retune needed, no change made to either constant.
    - **Real human stomp test: done.** Quiet floor ratio 1.03-1.13 across ~89 s (before and after,
      no false triggers); a real stomp produced `ratio=4.60` with a raw-volts CSV dump confirming a
      genuine ~65x amplitude transient. `STA_LTA_TRIGGER_RATIO=4.0` clears the floor by ~3.5x and the
      stomp clears the threshold by ~15% — kept unchanged, now validated rather than assumed.
    - **`STA_LTA_DETRIGGER_RATIO=1.5` confirmed dead code** on 14 Aug — `grep` showed it referenced
      nowhere outside its own `#define`; `state_machine.cpp`'s `kEvent` state only exits on
      `EVENT_MAX_MS` elapsed, no ratio-based detrigger logic existed anywhere. **Since removed
      outright, 15 Aug** — see below — rather than left as an indefinite unwired placeholder.
  - **`kSensing` efficiency fix, `GEOPHONE_WINDOW_STALE_MS` fix, `STA_LTA_DETRIGGER_RATIO` removal —
    15 Aug, geophone-only completion pass.** Full derivation in `docs/KNOWN_GAPS.md`'s "`kSensing`
    redundant STA/LTA re-run..." entry; summary here:
    - **Redundant STA/LTA re-run fixed.** `state_machine_tick()`'s `kSensing` case was re-running the
      full `read_seismic_window()` + `sta_lta_detect()` slide (~72k float ops) on every unthrottled
      `loop()` iteration, not just when a new sample had actually landed. `geophone.cpp`/`geophone.h`
      gained `geophone_sample_count()` (monotonic, non-saturating); `kSensing` now skips the
      read+detect entirely when it hasn't advanced since the last check — same trigger behavior and
      timing, just not recomputed redundantly. A correctness risk this created (`geophone_ok()`
      going stale forever if nothing calls `read_seismic_window()` on a dead sensor) was closed in the
      same pass by adding an unconditional proactive staleness check inside `geophone_service()`
      itself. Host-tested (`tests/test_geophone/`, 2 new cases); a real bug this surfaced —
      `geophone_init()` wasn't resetting the new counter — was fixed alongside. `pio run -e native` /
      `pio test -e native` green, 37/37 test cases.
    - **`GEOPHONE_WINDOW_STALE_MS` fixed to match its own documented formula.** Was `3072` ms (1.5x
      the *nominal* 250 Hz fill time), but the constant's own comment says 1.5x the real fill time —
      at the real measured 226.98 Hz rate that's `3384` ms. Updated the constant, not the comment,
      since the formula is deliberate real-hardware margin.
    - **`STA_LTA_DETRIGGER_RATIO` removed entirely** (both `SEISMIC_DEMO_MODE` branches in
      `config.h`, plus its comments). Decision: timeout-only exit from `kEvent` (`EVENT_MAX_MS`) is
      fine as the current design; a real ratio-based early-exit remains a legitimate future feature
      but only once real multi-event stomp data exists to set a threshold against — not before.
      `device/mcu/README.md` updated to match. **Hard boundary respected**: `git diff` on `config.h`
      touches zero characters of the `STA_LTA_TRIGGER_RATIO`/`STA_SAMPLES`/`LTA_SAMPLES` `#define`
      lines themselves.
    - **Real hardware flash + multi-trial stomp validation: done, 15 Aug.** Flashed and confirmed on a
      live console (board discovered at `192.168.1.10` — mDNS `eletect-x.local` doesn't resolve from
      Windows git-bash or WSL2; see `docs/eletect-x-applab-notes.md`). Quiet floor unchanged post-fix
      (1.09–1.15, matching the 14 Aug baseline). Ran the 12-stomp/60s-interval protocol against a
      lean-flag-toggle build: **11/12 detected** (mean trigger ratio 4.232, stdev 0.166; mean notify
      probability 0.8784, stdev 0.0105), one genuine sub-threshold miss (peak ratio 3.80, explained via
      the surrounding `[seismic]` lines, not dismissed), **zero false triggers** across a 688-sample
      quiet baseline (mean 1.149, stdev 0.031). MPU-side confirmed all **11/11** triggers produced a
      matching `report_footfall_event` with `alert=True` and `fused_P` 0.979–0.986 — required reading
      the board's raw Docker json-log directly (`docker run --rm -v /var/lib/docker/containers:/logs:ro
      alpine ...`, using the `arduino` user's `docker` group access) since `docker logs` itself fails on
      this container with a stream-corruption error and passwordless `sudo` isn't configured on the
      board. Full statistics and methodology in `docs/KNOWN_GAPS.md`'s 2026-08-15 multi-trial entry,
      now marked **closed**. Board left synced and re-flashed with `SEISMIC_DEBUG_VERBOSE=0` (lean field
      build), confirmed quiet before ending the session.
    - **Raw trigger data reaching the MPU: closed on the MCU/host side, later 14 Aug session.**
      `state_machine.cpp`'s `kSensing` case now calls a real
      `Bridge.notify("report_footfall_event", schema_version, probability, sta_lta_ratio,
      feature_vector)` on every STA/LTA trigger, right before the `kEvent` transition. `sta_lta_ratio`
      is the real `result.peak_ratio`; `feature_vector` is 8 real per-window statistics (`sta`, `lta`,
      `peak_ratio`, `trigger_index`, window min/max/mean/population stdev) computed by the new
      `footfall_features.cpp`/`.h`, host-tested (`tests/test_footfall_features/`, 6 known-answer
      tests). `probability` is a real, honestly-derived saturating function of `peak_ratio` — **not**
      the on-MCU TinyML model output the schema was originally written assuming, and the 22 Aug
      `ml/seismic/` model does not change that (it is off-device and undeployed), so this stays a
      documented placeholder, tracked as its own open gap in `KNOWN_GAPS.md` right next to the
      `ALERT_PROBABILITY_THRESHOLD` entry. Closing this also
      required making `Bridge.begin()`/`Bridge.update()` unconditional in `main.cpp` (previously
      gated behind the bench-only `SEISMIC_DEBUG_STREAM_RAW` flag, which would have silently kept the
      new notify from ever firing in the real field build) — confirmed safe on real hardware and the
      host build alike, full reasoning in `KNOWN_GAPS.md`'s dedicated entry for that decision.
      `pio run -e native` and `pio test -e native` are both green, 35/35 tests passing.
      **Real-hardware linker failure found and fixed, same night, before the live session below could
      run.** The original `probability` formula (`1 - exp(-k*(ratio-1))`) passed the host build cleanly
      but failed to link on the real board: `arm-zephyr-eabi-g++`/`ld` reported `undefined reference to
      '__errno'` from `libm_nano.a`'s `expf`. Root cause: the real UNO Q firmware build links
      `--specs=nano.specs --specs=nosys.specs -nostdlib` against a minimal picolibc-nano math library
      that doesn't provide `__errno`, which `expf` needs internally for domain/range error signaling —
      invisible to `pio test -e native` because the host build always has a full libc. Fixed by
      replacing the formula with `x^2/(x^2+c^2)` (`x = peak_ratio - 1`, `config.h`'s
      `FOOTFALL_PROBABILITY_SATURATION_C = 1.2f`), which needs only multiplication/division and calls no
      libm transcendental function — re-solved against the same two real anchors (quiet floor 1.13 ->
      ~0.012, real stomp 4.60 -> 0.9), re-verified host-green (35/35), then re-flashed and confirmed the
      real board links and boots clean. **Lesson for future MCU work:** a host-green build proves
      nothing about hardware-buildability for code calling a libm transcendental function (`exp`, `log`,
      `pow`, trig, ...) on this toolchain — `sqrt`/`sqrtf` (already used in `footfall_features.cpp` for
      the feature vector's stdev) does link fine, but that's only confirmed for the two functions
      actually used here, not the whole libm surface. Full derivation in `KNOWN_GAPS.md`.

      **Closed end to end, live hardware session, 14 Aug night.** With the fix above flashed, the
      MPU-side registration (`Bridge.provide("report_footfall_event", _on_footfall_event)` in `main.py`)
      was uncommented and pushed — `debug_stream_raw_seismic_sample` reconfirmed still running clean
      afterward (`app list` -> `running`, no crash loop), satisfying the one-at-a-time discipline. A real
      firm tap near the geophone then produced this real MPU-side log line:

      ```text
      INFO:services.reflex_loop:footfall event: mcu_probability=0.865 sta_lta_ratio=4.040 fused_P=0.980 alert=True used=['seismic'] dropped=['acoustic', 'vision'] feature_vector=[0.00387, 0.000958, 4.0397, 511.0, -0.0198, 0.0167, -0.000285, 0.00144]
      INFO:services.reflex_loop:[SAFE_MODE] would call drive_horn(schema_version=1, gain_pct=100.0, duration_ms=65535) - not calling (dry run)
      ```

      This is the first real trigger this project has gotten end to end from the geophone through
      STA/LTA, the notify, `handle_footfall_event`'s fusion/decision, and out the other side as a
      (dry-run, `SAFE_MODE`-gated) deterrence decision — real per-window `feature_vector`, not
      placeholders; `fused_P=0.980`/`alert=True` show `cognition.fusion`/`decision` consuming a real
      MCU-sourced reading for the first time; horn correctly not fired since `SAFE_MODE` was left on.
      Full writeup, including the exact linker error text, in `KNOWN_GAPS.md`'s "Raw seismic trigger
      data does not reach the MPU..." entry, now marked **closed** — both directions (MCU notify, MPU
      registration) proven on real hardware, not just host-tested.
- **`device/mpu`** — **no longer a bench-only stub.** `main.py` is now the real entry point:
  `cognition/decision.py` (pure `decide()`) and `services/reflex_loop.py` (the imperative shell —
  `handle_footfall_event`/`handle_acoustic_event`) implement the actual sense→fuse→decide→actuate loop,
  wired against the existing `cognition/fusion.py`. **`SAFE_MODE` defaults on** via the `ELETECT_SAFE_MODE`
  env var — `drive_horn` calls are dry-run logged, not real, until someone explicitly sets
  `ELETECT_SAFE_MODE=0` for a live session. Only seismic is fused end-to-end right now; acoustic is
  logged-only (no elephant-mapping exists yet); vision is always reported unavailable (no detector
  built). Two invented placeholders, both flagged in code and `KNOWN_GAPS.md`:
  `ALERT_PROBABILITY_THRESHOLD = 0.5` (uninformative midpoint, not tuned) and a horn-only "request
  protocol max, let the MCU clamp" deterrence policy standing in for the not-yet-built contextual
  bandit. The `Bridge.provide()` calls for `_on_footfall_event`/`_on_acoustic_event` are written but
  commented out, same one-at-a-time discipline as the MCU side. **123/123 pytest passing, `ruff check`
  clean** (re-verified 20 Aug — this file previously said 114/114, stale as of the 18 Aug commit below).
  - **18 Aug, `feat(mpu)` b612b39: `handle_footfall_event()` now fires LED/IR and captures
    deterrent-event footage, not just the horn.** `drive_led`/`pulse_ir` are injected the same
    Protocol-callable way `drive_horn` already was, same `safe_mode` dry-run gate. On a real alert:
    `camera.open()` → `capture_burst()` → horn → LED → IR → a short post-fire tail → `close()` →
    `save_frames()` — the camera opens before any actuator fires and stays open through the whole
    sequence so a saved clip has a chance of catching the retreat, not just the approach. Camera/storage
    faults are logged and never allowed to block or delay horn/LED/IR — deterrence is safety-critical,
    footage is secondary; covered by dedicated failure-path tests in `tests/test_reflex_loop.py`. New
    invented placeholders (`ALERT_LED_PATTERN_ID`, `ALERT_LED_DURATION_MS`, `ALERT_IR_DURATION_MS`,
    `CAPTURE_POST_FIRE_TAIL_S`, `CAPTURE_LOW_DISK_HEADROOM_BYTES`) follow the horn's existing
    "request the max, let the MCU clamp" policy — none tuned against real field data yet. Deliberately
    **no rolling pre-event buffer** (real complexity the Aug 20 deadline has no room to absorb
    untested) — `trigger_to_first_frame_s` latency is instrumented and logged instead, as the number
    that would justify one later. **Still open, not yet live-hardware-confirmed**: this is MPU-side
    only — the MCU-side `Bridge.provide("drive_led", ...)` / `Bridge.provide("pulse_ir", ...)`
    registrations in `main.cpp` remain commented out (same one-at-a-time discipline, see item 2 below),
    so nothing here has fired an actual LED/IR/camera together on real hardware yet. Full detail in
    `docs/KNOWN_GAPS.md`'s "Deterrent-event camera capture wired into `reflex_loop.py`..." entry (18 Aug).
- **`ml/`** — `seismic/` is real as of 22 Aug; `vision/` is real as of 23 Aug; `acoustic/` holds a
  code-complete, not-yet-run pipeline as of 23 Aug; `datasets/`, `evaluation/` are still untouched.
  Not blocking the Aug 20 trial (the field node uses a fixed pretrained detector per CONTEXT.md §4;
  the newly-trained model below is not exported or wired into anything), but relevant to the
  "scientifically rigorous" goal and the Hackster write-up's DSP/model section.
  - **23 Aug — two-class FOMO vision model, Edge Impulse project `1094260` (`EleTect-X-Vision`),
    trained and evaluated end to end.** `scripts/edge_impulse_upload_vision.py` sourced 3,280
    Elephant + 1,901 Boar images from two real CC BY 4.0 Roboflow Universe datasets and uploaded
    them with a group-aware 80/20 split (seed `20260822`); `scripts/edge_impulse_train_vision.py`
    built the FOMO impulse, trained it, and ran the held-out model test. Real result: per-class F1
    0.670 Elephant / 0.567 Boar — see `ml/vision/README.md` for the full derivation and required
    caveats (neither dataset is night-IR footage; nothing here is deployed).
  - **23 Aug — acoustic classifier pipeline, Edge Impulse project `1094275` (`EleTect-X-Acoustic`),
    written but not yet run.** `scripts/edge_impulse_upload_acoustic.py` sources gunshot + ambient
    from Mendeley `x48cwz364j` v3 (CC BY 4.0), chainsaw from ESC-50's ESC-10 subset (CC BY), and
    vehicle + animal_call from Freesound.org filtered to CC0/CC BY per clip;
    `scripts/edge_impulse_train_acoustic.py` builds an MFE + Keras classification impulse and reports
    real per-class held-out results once trained. **Blocked on a `FREESOUND_API_KEY` credential that
    does not exist yet** (free, but has to be created by hand) and on real internet access this
    session didn't have — neither script has actually run. UrbanSound8K and the two originally-named
    elephant sources (Pardo, HiruDewmi) were checked live and rejected for missing/absent licensing;
    see `ml/acoustic/README.md` for the full derivation. **Nothing on the MCU changed** —
    `bridge_handlers.cpp` still hardcodes `state.acoustic_ok = false`, and no acoustic capture
    hardware exists. Full detail in `docs/KNOWN_GAPS.md`'s updated `report_acoustic_event` entry and
    its new deployment-gap entry.
  - **22 Aug — first trained seismic model, Edge Impulse project `1094084` (`EleTect-X-Seismic`).**
    The 12 real 512-sample geophone windows from the 14/15 Aug bench stomp sessions were uploaded
    (24 samples: a 512 ms `quiet` segment and the 256 ms `footfall` transient from each event, split
    by event 9 training / 3 testing) and a spectral-analysis + Keras classifier trained on them.
    **Held-out test result: 9/9 windows correct, 100%, 0 uncertain.** Everything about how that
    number was derived, and the five caveats that must travel with it, is in `ml/seismic/README.md`
    — the short version: n=12 events, a 3-event test set, `quiet` and `footfall` drawn from the same
    recordings, one person on one bench, and classes so separable (quiet RMS 1.34e-4 V vs footfall
    2.93e-3 V, zero overlap) that a plain RMS threshold would score identically. **Nothing on the MCU
    uses it** — `footfall_features.cpp`'s placeholder probability is unchanged and no deployment path
    exists. Because `scripts/bench-logs/` is gitignored, the 12 windows are committed verbatim as
    `ml/seismic/bench_windows_20260814_15.json` and `scripts/edge_impulse_upload_seismic.py` falls
    back to that artifact, so the dataset is reproducible from a fresh clone. The API key is not in
    the repo — supply it via `EI_API_KEY`.
- **`hardware/` power system — MPPT dropped, 20 Aug (ADR 0012).** Every "smart" LiFePO4 MPPT
  controller checked (amiciSmart 10A, Sparkel SPSCC-1012LiMPPT) turned out disqualified on real
  verification (wrong chemistry default, unreachable config path, a reported no-auto-resume firmware
  bug) or over budget (Victron, ₹6,300+) — see the ADR for the full per-part rundown. Power system now
  uses a manually-set XL4015 buck (already the part `procurement-status.md` had listed) for charge
  regulation instead of true MPP tracking; documented as an accepted efficiency tradeoff, not a gap.
  Follow-on: `hardware/cad/enclosure-design-concept.md` and ADR 0011 still cited the old MPPT's
  138×79×38mm footprint — corrected to the XL4015's ~54×23×18mm (`docs(hardware)` c0ae7db). **The
  CadQuery script `hardware/cad/main_enclosure.py` (and its generated STEP files / `FINDINGS.md`) has
  not been re-run against this correction and should be treated as superseded, not current** — the
  enclosure is now a hand-built Fusion 360 model already in manufacturing
  (`hardware/cad/eletect_x_final.f3z` / `.step`, untracked working files as of this session, not yet
  committed). Don't use `main_enclosure.py`'s output for anything real; if CAD dimensions are needed,
  check the Fusion 360 files or `enclosure-design-concept.md`, not the CadQuery pass.

**Explicit reprioritization, decided 14 Aug evening, now fully satisfied:** finishing and hardening the
geophone subsystem was to come before flashing/firing the fire-test harness and before any live Bridge
registration. The geophone bring-up items (I2C bus confirmation, cadence-fix verified on real hardware,
real field-flag sample rate, real stomp test) and the raw-data-to-MPU gap (`report_footfall_event`,
including the one live Bridge registration it required) are all done and closed on real hardware as of
14 Aug night — see above. The fire-test harness (flash + fire on a real actuator) and the remaining
`drive_horn`/`drive_led`/`pulse_ir`/`get_system_state` Bridge registrations are next in this thread,
same one-at-a-time discipline.

`docs/ELETECT_X_PITCH.md` — a full project pitch/description doc was also written this session
(problem, solution, how it works, full tech stack, honest current status, contest tie-in). Useful if
anyone needs to explain the whole project from scratch, not required reading for continuing the build.

## ADR trail — read these together, not in isolation

12 ADRs in `docs/decisions/` (0000 is the template, ignore). **Numbering has one real duplicate**:
both `0001-usb-camera-imx462.md` and `0001-physical-ai-sensing-and-fusion-architecture.md` are "0001"
— don't rely on the number alone when searching.

The horn/acoustic story changed shape three times. Reading only one of these will give you a wrong
picture — read **0003 → 0005 → 0009 → 0011** in that order:

| ADR | Status | Decision |
|---|---|---|
| 0001 (camera) | accepted | Arducam IMX462 USB day/night camera |
| 0001 (fusion/sensing) | accepted | Drop ADS1115 for final node (STM32 internal ADC via LPBAM); FOMO primary vision, MDv6-compact documented fallback |
| 0002 | accepted | LoRaWAN star over Meshtastic mesh; Meshtastic hardware repurposed for field-team comms |
| 0003 | accepted | Single BTL channel, gain-limited; horn flush-mounted in main enclosure |
| 0004 | **superseded by 0005** | (briefly switched to TOA SC-610, reversed same day) |
| 0005 | accepted | Revert to Ahuja SUH-15; solve compactness via enclosure form, not a different part |
| 0006 | **superseded by 0009**, kept as fallback | Gunshot-dedicated comparator gate + pre-trigger DMA buffer |
| 0007 | proposed | Unified acoustic architecture, per-class signature table, gunshot bypasses fusion |
| 0008 | proposed, 2 bench measurements pending | MPU stays in deep suspend (not poweroff) between events, ~0.42-0.45W continuous |
| 0009 | proposed, gated on one bench test | Continuous on-MCU LPBAM classifier supersedes 0006's gate design |
| 0011 | proposed (13 Aug) | Horn driver moves to its own small IP66 housing, wired via speaker cable/gland — amends 0003/0005's flush-mount call |
| 0012 | accepted (20 Aug) | Drop the smart MPPT solar controller for a manually-set XL4015 buck — every checked MPPT unit failed real verification or was over budget |

`hardware/cad/enclosure-design-concept.md` (380 lines, last touched 14 Aug — after ADR 0011) should
already reflect the split-housing design; confirm this before assuming it's still pre-0011.

## Procurement — essentially done as of 15 Aug

`hardware/bom/procurement-status.md` is the only trustworthy procurement doc — `bom.md` is stale on
the power system, the LED driver part (says PT4115, actually XL4015), and doesn't reflect ADR 0011's
horn-housing split. Don't quote prices or parts from `bom.md` without cross-checking the tracker.

Everything sourceable online is ordered (battery, MOSFETs, TVS/Schottky diodes, brass inserts, SS-304
screws, standoffs, VHB tape, USB-C adapter, pole-mount clamps ×2 for main enclosure + horn housing).
What's left is a fixed, small, local-store-only list — no shipping risk, one trip:

1. Optical window — acrylic/PC 2-3mm
2. PVC pipe 32mm + end caps (geophone burial)
3. SS-304 bolt M10×100 (geophone spike) — confirmed not sold at Robu, Amazon, or onlyscrews at this
   length/material; onlyscrews tops out at M10×70mm Allen-head, not a true hex bolt
4. Araldite epoxy
5. HDPE conduit 20mm
6. Solar panel — 12V, 15-20W (a 20W WAAREE panel is already ordered but lands 24 Aug, too late — it
   becomes the Phase 2/permanent-build panel, not the trial panel)
7. Fuse + holder, 6A
8. Power switch — SPST, 2-position, ≥10A/12V DC

**Real open risk, not fixable by more ordering:** the battery (Robu order #3636219, placed 14 Aug)
quotes 5-7 working days — could land Aug 21-24, after the deployment date. Worth calling Robu
(1800 266 6123) to check on expediting.

## Known gaps, ranked by what actually blocks Aug 20 (updated 14 Aug evening)

Full list lives in `docs/KNOWN_GAPS.md`, organized by build call — it is the accurate, current record,
kept up to date live through tonight's session. Highest-priority items as of the account switch:

1. **Geophone hardware bring-up: closed, 14 Aug night.** I2C bus, cadence-fix, real field-flag sample
   rate (226.98 Hz), and the real human stomp test are all done and confirmed on hardware — see
   `device/mcu` section above and `docs/KNOWN_GAPS.md`'s "STA/LTA field-flag rate re-measurement and
   real stomp-test calibration" entry. `STA_LTA_TRIGGER_RATIO` is now validated (kept at 4.0), not
   assumed. **`report_footfall_event` is now closed end to end, real hardware, 14 Aug night** —
   `state_machine.cpp` calls `Bridge.notify()` with real `sta_lta_ratio`/`feature_vector` and a
   documented placeholder `probability` on every trigger, a real-hardware `expf`/`__errno` linker
   failure was found and fixed same night, the MPU-side registration was uncommented and pushed with no
   regression to `debug_stream_raw_seismic_sample`, and a real stomp produced a real captured MPU log
   line (`mcu_probability=0.865`, `fused_P=0.980`, `alert=True`). See `device/mcu` section above and
   `KNOWN_GAPS.md`'s "Raw seismic trigger data does not reach the MPU..." entry, now marked **closed**.
   `SAFE_MODE` is still on (code default) — the horn was correctly not fired. Remaining before the
   field trial itself: `ELETECT_SAFE_MODE=0` is an explicit live-session step, not yet done, and only
   for a session with a human present.
2. **The MPU integration loop is no longer missing** — it exists now (`device/mpu/main.py`,
   `services/reflex_loop.py`), dry-run by default via `SAFE_MODE`. `report_footfall_event`'s
   registration is now live and proven on hardware (item 1 above); `report_acoustic_event`'s
   registration is still written and commented out, same one-at-a-time discipline, deliberately out of
   scope for this pass. **18 Aug:** the reflex loop's alert path also now drives LED/IR and captures
   deterrent-event footage, not just the horn (see `device/mpu` section above) — but this is MPU-side
   wiring only; `main.cpp`'s `Bridge.provide("drive_led", ...)`/`Bridge.provide("pulse_ir", ...)` are
   still commented out (same one-at-a-time discipline as item 3 below), so no LED, IR, or camera has
   actually fired together from a real trigger on hardware yet.
3. **The fire-test harness's software path is verified on real hardware, re-confirmed 22 Aug.** Correct
   `[firetest]` acks and cooldown refusal for all four commands, this time driven entirely over SSH +
   `arduino-app-cli` + the board's socat bridge (App Lab GUI wasn't running) — see
   `docs/eletect-x-applab-notes.md`. LED cooldown confirmed genuinely per-channel on real hardware
   (white then blue back-to-back both fired). IR's cooldown gate needed a re-run with both presses in
   one burst — the first attempt's ~2-4s manual keystroke gap exceeded `IR_MIN_INTERVAL_MS` (5000ms)
   and the gate correctly allowed it; that was the gate working, not a miss. `FIRE_TEST_HARNESS`
   confirmed back to `0` and the reflashed field build proven inert (`1234?` sent, zero `[firetest]`
   output). **Physical activation is still not confirmed: horn, LED, and IR are not wired to the
   board.** Re-run once wiring exists.
   - **Same session, clean field-build flash also confirmed, with an honest gap surfaced.** `setup()`
     prints nothing in the current field build — no `_init()` function emits console output when
     `SEISMIC_DEBUG_VERBOSE`/`SEISMIC_TRIGGER_CONSOLE_LOG`/`SEISMIC_DEMO_MODE` are all `0`, so there is
     no boot banner to check against. Liveness was instead confirmed via `mac.cpp`'s LoRa join state
     machine printing `AT` on a steady ~7.5s cadence (`LORA_AT_TIMEOUT_MS`=2000 +
     `LORA_JOIN_BACKOFF_BASE_MS`=5000) — proves `loop()` is executing and timers are advancing, but
     only because the join probe happens to be console-visible. **Gap: a silent console makes a hung
     MCU and a healthy one look identical over serial in a field build.** Worth a one-line boot banner
     print at the top of `setup()` at some point — not done this session, logged here rather than
     `docs/KNOWN_GAPS.md` since it's a minor diagnosability nice-to-have, not a correctness risk.
   - **New finding, real race, currently benign — see `docs/eletect-x-applab-notes.md`'s LORA_SERIAL
     section for full detail.** `fire_test_service()` and `mac.cpp`'s response-read loop both drain the
     same `Serial` stream (`LORA_SERIAL Serial`) with no arbitration. Didn't bite this session (10/10
     then 13/13 injected fire-test bytes landed correctly) only because the E5 never actually responds
     with anything to steal. Stays benign only as long as `FIRE_TEST_HARNESS` is off outside bench
     sessions (already the default) — flagged so a future LoRa-join bench session doesn't lose time to
     an unexplained dropped byte if both are active at once.
4. **LoRa `Serial` vs `Serial1` conflict — closed, 18 Aug; module itself is now the open item.** Grove
   LoRa-E5 physically wired for the first time (D0/D1 = USART1). Confirmed `Serial` (not `Serial1`) is
   correct by reading the board's own devicetree overlay directly plus a live `journalctl -u
   arduino-router` cross-check (both no-sudo, over plain SSH) — `config.h` updated and committed
   (`47785ec`). But the real join test on the corrected wire got **zero response bytes from the module**
   across all 6 AT-probe retries (90 s capture, port-7500 console tap). So the "+JOIN: Done" AT-sequence
   fix in `mac.cpp` (already committed, `b69799f`) is still unproven on hardware — join never gets past
   the first "AT". Two untested candidate causes needing physical hands, not more SSH: a 5V-power/3.3V-MCU-TX
   logic-level mismatch on the module's RX line, or the module not being in AT-command mode out of the
   box. Full capture, wiring photo description, and a third possible cause in
   `docs/KNOWN_GAPS.md`'s 18 Aug entry. Wiring-status table in `UNO_Q_PINOUT_REFERENCE.md` stays
   at **P** (wired, not confirmed working) — not flipped to **W**.
   **The console/LoRa shared-wire risk flagged here is now also closed, 20 Aug (`fix(mcu)` b4087d1).**
   `state_machine.cpp`'s unconditional `[trigger]`/`[notify]` console prints — which physically reach
   the E5's RX pin over the same `Serial` wire and could have corrupted an in-flight join — are now
   gated behind a new `config.h` flag, `SEISMIC_TRIGGER_CONSOLE_LOG` (default `0`, same discipline as
   `SEISMIC_DEBUG_STREAM_RAW`/`FIRE_TEST_HARNESS` — must stay `0` before any field sync); the real
   `Bridge.notify("report_footfall_event", ...)` MPU report is untouched either way, only the redundant
   local console text is gated. New host coverage in `tests/test_state_machine/` asserts a genuine
   trigger still writes zero bytes to `Serial` at the default flag value; full `pio test -e native`
   suite green (8 suites / 45 cases). Flip the flag to `1` locally for bench visibility of `[trigger]`
   lines again (`device/mcu/README.md`'s stomp-test section documents this). This closes the
   wire-sharing risk, not the module-not-responding problem above — those are two separate LoRa issues,
   and only the first is done.
5. **USB-C host-mode-under-VIN-power is unverified.** If the camera doesn't enumerate under VIN power
   (not USB-C power), the whole vision pipeline architecture needs rework. Check this early, once past
   the geophone work. **Related (not a substitute) check done 17 Aug on USB-C/PD power, not VIN:**
   IMX462 → Portronics hub → UNO Q's USB-C port, board powered via the hub's PD passthrough from a 45W
   charger. Camera enumerated fine (`lsusb`, six `/dev/video*` nodes) — confirms the single USB-C port
   can be a PD sink and USB host simultaneously, which was itself unconfirmed, but says nothing about
   the VIN case, which still needs its own test.
   **Both real findings from that pass are now closed, same day (17 Aug), with the camera path proven
   robust, not just patched:**
   (a) `services/config.py`'s `CAMERA_DEVICE` no longer points at `/dev/video0` (the SoC's own
   `qcom-venus` hardware encoder, not the camera) or at any bare index at all — it now points at the
   udev `/dev/v4l/by-id/usb-Arducam_Technology_Co.__Ltd._USB_2.0_Camera_SN0001-video-index0` symlink,
   keyed on the camera's own USB serial rather than bus topology or enumeration order. This mattered
   more than expected: a full board reboot was tested and the raw `/dev/videoN` indices genuinely
   reshuffled underneath the camera (video1/2/4/5 before → video0/1/2/3 after, as the SoC codec and the
   UVC driver raced differently on the two boots) — a bare-index fix of any kind, including `/dev/video1`,
   would have broken again on the very next reboot. The by-id path survived both that reboot and a
   physical camera unplug/replug (board left powered) with zero code changes both times.
   (b) `python3-opencv` is now installed on the board (`4.10.0+dfsg-5`, confirmed via
   `python3 -c "import cv2"`).
   With both fixed, `bench/camera_check/capture_check.py --backend v4l2 --probe` — the real exit
   criterion, not the `v4l2-ctl` workaround — now runs end-to-end and was confirmed three times (fresh,
   post-reboot, post-replug): negotiates 1920x1080 MJPG @30fps as configured, saves real single+burst
   JPEG frames to `output/`. `dmesg` across both reboot and replug showed no USB errors beyond one
   benign recurring UVC audio-endpoint quirk (`cannot get freq at ep 0x84`) present on every
   enumeration including the very first cold boot; the replug's disconnect→reconnect gap was ~8.6s.
   Full verification detail: `docs/KNOWN_GAPS.md`'s "Camera device-path robustness" entry.
   **New from the same pass:** `perception/camera.py`'s `Camera.open()` had zero retry logic — fixed,
   now retries up to `CAMERA_OPEN_RETRIES` (3, 2.0s backoff, `services/config.py`) before raising, so a
   device that isn't there yet at startup can recover without code changes. `capture_frame()` /
   `capture_burst()` remain deliberately non-retrying (unchanged, already-documented honest-failure
   design). Still genuinely open, logged in `docs/KNOWN_GAPS.md` with a recommendation rather than
   decided here: there is no supervisory recovery yet for a camera that dies *mid-run* (no consuming
   loop exists — `main.py`/`reflex_loop.py` have no detector/camera integration at all yet), so that
   policy is deferred to whoever builds the vision detector/reflex-loop integration.
6. **SenseCAP gateway is still labeled EU868**, must be set to IN865 region profile in ChirpStack and
   join-tested before any real transmission — transmitting on 868MHz is illegal in India.
   **Research pass done (16 Aug, no hardware touched yet):** step-by-step console-access,
   channel-plan, and ChirpStack-registration procedure written up from Seeed's official wiki/PDF
   and two independent real IN865-in-India deployment write-ups — see
   `docs/research/sensecap_gateway_in865_chirpstack_setup.md`. One real open risk flagged there:
   Seeed only sells this gateway as separate EU868/US915/AU915/AS923 SKUs (no IN865 SKU listed),
   and neither real-world write-up explicitly confirms IN865 appears as a selectable entry in the
   `LoRa > Channel Plan` dropdown — both just proceeded from EU868-labeled hardware without
   reporting a wall. Strongly suggestive, not confirmed. First action on unboxing should be
   opening that dropdown and looking, before any ChirpStack wiring.
7. **`loop()` has no task/priority separation** — an actuator fire (horn especially, ~3.15s worst case)
   currently blocks geophone/LoRa servicing for that whole window. Logged, not scheduled before Aug 20,
   flagged so the trial's data gets read with that caveat.

## Git state (as of 20 Aug)

**Stale-as-of-this-refresh correction:** this section previously said branch `feat/mcu-seismic-debug`
with most of the tree "modified" and a list of untracked work product. That's no longer the state of
the repo — `feat/mcu-seismic-debug` was merged into `develop` by `merge` 283c748 ("bring in
device/mcu+mpu field-deployment work ahead of Aug 20 trial") before this session started, and every
file the old list named as untracked (`docs/decisions/0011-...`, `docs/eletect-x-applab-notes.md`,
`hardware/bom/eletect-x-power-budget.xlsx`, `hardware/references/uno-q-official/`) is committed now.
Don't trust that list going forward — it's corrected below, not carried forward.

Branch is now **`develop`**, 84 commits ahead of `origin/develop` (not yet pushed — that's a real,
growing gap between local and remote, worth pushing or at least being aware of before assuming
`origin/develop` reflects current state). Working tree is clean except for the user's own in-progress
CAD work, left untouched by every task this session (same practice as prior sessions — don't stage or
commit these without being asked):
- `hardware/cad/FINDINGS.md` — modified, not yet committed
- `hardware/cad/eletect_x_final.f3z`, `hardware/cad/eletect_x_final.step` — untracked; this is the
  real, current enclosure model (see the `hardware/cad` bullet above) — don't confuse with the
  superseded `main_enclosure.py` CadQuery pass, which *is* tracked/committed but stale
- `hardware/cad/imported_components/` — untracked

This session's five commits, in order, all on `develop`: `04d1398` (ADR 0012), `c0ae7db` (CAD-doc
MPPT→XL4015 citation fix), `b4087d1` (state_machine console-print gating), `42ced90` (login-page
demo-account doc-drift closure + regression test), `a15ea23` (notify-officer-request fan-out
extraction). None pushed to `origin/develop` yet, same as the rest of the 84-commit gap above.

## Other doc-currency notes

- `docs/BUILD_BLUEPRINT_AUG8.md` is fully superseded — its day-by-day schedule (through 8 Aug) is in
  the past and was not hit on schedule. **`docs/BUILD_BLUEPRINT_AUG20.md` (written 14 Aug) is the
  operative day-by-day plan to the deployment date — check it for the current action list.**
- `docs/PROJECT_BLUEPRINT.md` itself says it's superseded by `BUILD_BLUEPRINT_AUG8.md` for scheduling,
  but its architecture/workflow sections (§0-5) still stand.
- Root `README.md`'s status line ("Architecture frozen; implementation in progress") and its pointer to
  `PROJECT_BLUEPRINT.md` are generic — low priority to fix, doesn't block anything.

## Session-continuity protocol (unchanged, from CLAUDE.md)

This planning session (Opus/Cowork) stays long-lived across the whole engagement and does research,
docs, BOM/spreadsheet edits directly. A separate execution session (Sonnet, in VS Code/Claude Code)
does firmware/code changes on the physical board — new session per build call by default, same session
only for a small follow-up fix. If *this* planning session has to restart under a different account,
this file plus `CONTEXT.md` plus `docs/KNOWN_GAPS.md` should be sufficient to resume without re-deriving
anything above.
