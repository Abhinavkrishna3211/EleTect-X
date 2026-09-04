# EleTect X — Handover (last updated 4 Sept 2026 — see the "RESUME HERE — 4 Sept (later) — Boar-gap close-out best-effort vision retrain complete: Step 2 baseline rerun established a ≤1pt noise floor, all three Step 3 platform trials (color-space-augmentation medium, spatial-augmentation medium, freeze-backbone true) tried and failed, deployed checkpoint (Boar 0.852/Elephant 0.906/FP 0.166 @0.05) stays exactly as found, no board interaction this segment" checkpoint at the very top; then the "RESUME HERE — 4 Sept — night exposure-lock implemented and host-tested for the active Camera path (not just written up), a live re-test corrected the earlier "frozen at 156" claim, an unrelated stale-exposure production bug found and fixed on the same path, EventVideoRecorder/GStreamer side still unimplemented; Workstream 2 (Boar representation audit) complete, correcting the real-night/IR-Boar-imagery figure from an assumed 0.87% to an estimated ~11%" checkpoint below it; then the "RESUME HERE — 3 Sept — Boar deterrence closed the loop: per-poll+per-burst debounce committed, tri-state node scope + confirmation-path streak gate + Boar horn content built and tested (uncommitted), ADR 0023 + boar research doc written, Hunchun light-vs-sound study found readable" checkpoint below it; then the "RESUME HERE — 3 Sept (later still) — H.264 bitrate root cause fixed and committed, ~3.8fps camera-throughput risk documented, in-process crash recovery closed (restart-policy fix + durable cron watchdog)" checkpoint below it; then the "RESUME HERE — 3 Sept (later) — ADR 0020 event-video pipeline fixed and verified on real hardware (muxing + framerate bugs), power-loss recovery confirmed empirically, bitrate control still open" checkpoint below it; then the "RESUME HERE — 3 Sept — onboard auto-IR/photoresistor diagnosed and bench-rig scope corrected to daylight-only; reboot-resilient overnight matrix run (cron + watchdog) completed cleanly and analysed (2,314 records, zero errors, domain-shift caveat on the rig's own accuracy numbers); ADR 0022 (vision watch window + vision-gated deterrent) committed" checkpoint at the very top; then the "RESUME HERE — 2 Sept (overnight) — night-IR characterisation doc + ADR 0019 + Item C proposal + activity-timing research + behavioural-synthesis append; overnight soak running on the board" checkpoint below it; then the "RESUME HERE — 1 Sept (evening) — ADR 0014 item A (max-gain LED + 11 Hz top tier) reflashed + hardware-verified; camera day/night solved via frame saturation" checkpoint at the top for current state: the recurring idle crash-reboot fault is now traced to a **power-delivery failure caused by the Portronics Mport 51 USB-C hub sitting in the board's power path** — the UNO Q's Type-C controller reports `power_operation_mode: default` with **no `port0-partner`** (it sees nothing on the CC pins), so it is locked at the USB-default floor of 5 V / 500 mA no matter that the charger is a 45 W PD unit; the camera + USB-Ethernet share that starved rail; every actuator/camera load transient browns it out; boot history shows this since the board's first-ever boot (28 May), including power-up retry bursts of 4–7 reboots within seconds — a pure power signature, with NO panic / watchdog / thermal / OOM trace anywhere. Fix (physical, pending, user present): remove the hub from the power path — 45 W PD charger straight into the UNO Q's sole USB-C port, camera onto a separately-powered hub — then re-check that `power_operation_mode` flips to `usb_pd`/`3.0` and `port0-partner` appears, then idle-soak. If it still shows `default` plugged straight into the charger → board USB-C CC pins / cable → swap cable, else RMA. Separately this session, ADR 0014 §E "real dual-wing LED" is implemented host-side and fully green (`pio test -e native` 63/63, `pio run -e native` clean, `ruff` clean, `pytest` 238 passed) but NOT reflashed and no actuator fired — reflash + physical dual-wing first-fires are deferred until after the power rewire, per the user's sequencing. Then see the "RESUME HERE — 1 Sept, hardware bring-up session (ADR 0014 reflash + 4 pattern first-fires + daylight vision matrix all DONE on hardware; then a recurring idle crash-reboot fault hit and was diagnosed; power-cycle + 30-min + 2-hour idle soaks recovered it, root cause UNRESOLVED)" checkpoint for the prior round: the ADR 0014 reflash landed on the board (device/mpu + sketch synced via tar-over-ssh since rsync is absent on Windows, `arduino-app-cli app restart user:eletect-x`, STM32 flashed clean via OpenOCD, container restarted rc=0); all four LED flash patterns (steady / slow-pulse / fast-strobe / random-flicker) were fired on the left wing at 50% gain and user-confirmed on hardware — measured latency = burst duration + ~15 ms with zero pattern-specific blocking cost, confirming ADR 0014's zero-new-blocking-cost claim; the D5→D3 left-wing pin fix is confirmed working; the 5-arg `Bridge.provide("drive_led", …)` arity binds on the real `Arduino_RouterBridge` (schema v2 accepted). The full daylight vision-model matrix then ran unattended (6 conditions: camera-only, pulsed-IR ×3, each of the 4 LED patterns firing next to the camera; results JSON + 12 sample frames preserved locally in the session scratchpad) — key findings: LED patterns firing next to the camera cause NO measurable daylight washout (within-condition lit-vs-unlit mean-luma delta <0.5, `frac>250` ≈ 0, no clipping — the 50% LED is swamped by ambient sun, the OPPOSITE of the night result); pulsed IR is only +1.6 % scene luma in daylight vs +99.5 % indoors at night (IR invisible against daylight — a real IR-throw characterization must be a night test); inference latency is a tight ~203–207 ms mean per frame across ALL conditions (vs the ~137 ms prior-night baseline — daylight frames carry more texture; LED pattern choice adds zero latency, matching the on-hardware first-fire finding); every spurious detection is a noise-floor "Elephant" ghost at confidence 0.074–0.111 (bench has no animals) — a deployment threshold of ~0.2 eliminates all of them, and `fast_strobe`/`random_flicker` conditions produced zero FPs. THEN the board rebooted while genuinely idle (boot_id changed ~1 h after all session activity had stopped, board doing only hourly cron + fwupd-refresh). Investigation via `last -x` / `journalctl --list-boots`: this is a RECURRING fault — every boot since 30 Aug ends in `- crash` (unclean, no shutdown record), 12 crash-reboots in ~3 days, intervals 9 min to 11 h; NOT thermal (all zones 40–42 °C), NOT caused by the session's workload (crash was long after the matrix finished and the SSH session closed), and it predates this session. The board's clock also appears to jump forward on reboot (dead RTC backup cell suspect — a second SoM smell). Per the session's failure clause the automated path was HALTED. User power-cycled the board; a 30-minute then a 2-hour idle soak BOTH PASSED (boot_id held `b08c69f1…`, container + EIM runner up at every check, zero SSH failures, ~2 h 40 m continuous idle-stable) — the power cycle most likely reseated a connector or cleared a latched PMIC state, but the ROOT CAUSE IS UNRESOLVED and this is not yet trustworthy for a 10-day unattended field deployment. The container `restart:` / auto-recovery gap (app came up dead after two crash-reboots) was fixed two ways without sudo: `arduino-app-cli properties set default user:eletect-x` (the default app was UNSET — that is why the daemon never restarted it on boot) plus `docker update --restart=unless-stopped eletect-x-main-1`; a durable systemd guard unit + timer is written out (in the checkpoint body) and waiting on the user's sudo to install (the `docker update` layer is lost whenever `arduino-app-cli app restart` recreates the container). Firmware is intact in STM32 flash and needs NO reflash. Nothing committed to git. Immediate next steps: an OVERNIGHT idle soak before trusting the board for the trial — if it crash-reboots again while idle, the board needs swapping, not more software work; install the systemd guard (2 sudo commands); the grey-card IR-throw test still needs a user-set-up night session with a physical 18 % card. Then see the "RESUME HERE — 1 Sept, later session (ADR 0014 LED patterns + gain wired end-to-end and host-tested; board NOT reflashed)" checkpoint below it for the code/host-test build call that preceded this one: the four ADR 0014 LED flash patterns (steady / slow-pulse / fast-strobe / random-flicker) are now implemented in `device/mcu/src/led.cpp` as timing logic inside `drive_led()`'s existing blocking window (zero new blocking cost — every pattern's on/off spans sum to exactly the resolved `duration_ms`), `drive_led`'s wire schema is bumped to `schema_version 2` with `channel` split out as its own field and a real `gain_pct` field added, the MPU tier ladder (`cognition/config.py`) now gives each tier a distinct pattern + wing + brightness, and the whole change is host-tested green (`pio test -e native` 56/56 incl. new `tests/test_led` 7/7, `pio run` clean, `ruff` clean, `pytest` 233/233); NOTHING has been reflashed and no actuator has fired — the reflash (carrying this + the D5→D3 pin fix + the reverted field-safety flags), the first physical fire of each pattern, verification that the new 5-arg `Bridge.provide("drive_led", …)` arity binds on real hardware, and the entire daylight vision-model test matrix are all deferred to a supervised daylight session per the project's Hard Safety Rule. The 3× board reboots + `eletect-x-main-1` `Exited (255)` seen last session are now diagnosed and cleared (1 Sept, SSH, no reflash): physical power interruptions during the 31 Aug wing-pin rewire, no OOM/thermal/undervoltage/watchdog/panic signature in any retained boot, board healthy — safe to proceed to the reflash; see the checkpoint body and `TRIAL_READINESS_PLAN.md`'s "Board-reboot / container-exit diagnosis" section. Then see the "RESUME HERE — 1 Sept, ~01:45 IST (steady-on actuation path re-verified for the trial; field-safety flags reverted in source, board NOT yet reflashed; overnight monitor was dusk-only; strobe deferred)" checkpoint below it for the prior round: the 2 Sept trial's actuation path (left wing / right wing / IR over the real Bridge RPC, per-channel LED cooldown, IR 5 s min-interval, silent over-cap clamp) was re-verified end-to-end; `FIRE_TEST_HARNESS` and `FIRE_TEST_LED_GAIN_PCT` were reverted in `device/mcu/src/config.h` but the board's flashed binary still has the harness compiled in — a reflash from the clean tree (which also carries the D5→D3 left-wing pin fix) is the next session's first action and is blocking for field deployment; a new quantified finding that every real actuator fire blocks the MCU loop for the full clamped burst (10 s for a wing) is recorded in `docs/KNOWN_GAPS.md`; the overnight monitor self-stopped at dusk on a `STOP_HOUR` bug (no dawn data); `main.py` is confirmed NOT restart-looping; strobe LED patterns are deferred as post-trial work and the trial ships steady-on wings only. Then see the "RESUME HERE — 31 Aug, ~15:40 (30-min actuator sweep: LED wings camera-invisible at foliage range, IR strong and repeatable; no vision model deployed on the board; overnight monitor started)" checkpoint below it for the prior round. Earlier context: the "RESUME HERE — 31 Aug, ~14:00 (all three reflex actuators physically confirmed — left wing D3, right wing D6, IR D7; LED_GATE_ACTIVE_LOW workaround reverted; drive_led + pulse_ir both registered)" checkpoint just below for current state. Earlier context: the "RESUME HERE — 30 Aug, later still (bring-up order finalized by the user: LED wing first, then IR, then horn/speaker, then combine — supersedes the earlier horn-first ordering)" checkpoint: the user explicitly reordered the physical bring-up sequence (LED before IR before horn, not horn-first as the 26 Aug audit and 30 Aug strategic-redirect checkpoints both had it) and a full 9-stage plan was written up with concrete per-stage pass/fail criteria, including flagging an unresolved LED firmware-design mismatch (`hardware/WIRING_GUIDE.md` §4.0 documents an unimplemented 4-channel/10-LED spec; the user's actual build is a simpler 2-wing/2-MOSFET design on the existing pins 5/6) that must be reconciled before the LED fire-test step. See that checkpoint for full detail, then the prior "RESUME HERE — 30 Aug (2-hour live-camera stress test: real 31.5% Boar false-positive rate found on outdoor foliage, correcting the earlier 0/123 claim; local `.eim` copies pulled; training-config tutorial delivered)" checkpoint just below for current state: a 2-hour, 40,422-frame continuous live-camera run on the real board (camera pointed at outdoor trees/leaves, no animals present, IR always-on) found a real 31.53% Boar false-positive rate — zero Elephant false positives — which materially corrects the prior night's "0/123, zero false positives" claim (that sample was only 21 seconds/123 frames, too small to be representative). The finding is currently contained: only an Elephant-label detection feeds the alert-fusion decision, so this does not create false elephant alerts today, but it matters for the still-open question of whether Boar detections should ever influence deterrence tier. Latency held steady at scale (137.25ms mean, 5.52 FPS over the full 2 hours, consistent with the smaller sample). Both `.eim` model files were also pulled locally to `device/mpu/models/vision/` (gitignored, byte-identical to the board), and a step-by-step tutorial on the exact training configuration behind the deployed checkpoint was delivered to the user. See that checkpoint for full detail, then the prior "RESUME HERE — 30 Aug (real on-device benchmark: CPU 138ms/~5.7fps measured, 3.9x faster than Studio's own estimate; GPU delegate builds but confirmed non-functional at runtime; functional correctness verified end-to-end via HttpVisionDetector against known-labeled images; EON Tuner still running, no improvement over champion yet)" checkpoint right below it for the prior round: that overnight autonomous session (user asleep, explicit "do everything autonomously... test in uno q... benchmark and compare in the hardware" instruction) exported the finalized `yolo-pro-medium-no_attn_relu` threshold-0.05 checkpoint as two fresh `.eim` builds (CPU `runner-linux-aarch64` and GPU `runner-linux-aarch64-gpu`) and benchmarked the CPU build against the board's real, live-connected camera (pointed out the window, IR always-on) — 123 real inference cycles, mean classification latency 138ms, ~5.7 FPS end-to-end, zero false positives on all 123 live frames. The GPU build compiles and links real GPU-delegate code in Edge Impulse's cloud but fails to launch on this board with `libtensorflowlite_gpu_delegate.so: cannot open shared object file` — confirmed via exhaustive filesystem search and apt-cache search that the library is genuinely absent and unobtainable here, consistent with and adding new detail to the 29 Aug sudo-backed root-cause finding below. Also drove the real production `HttpVisionDetector` client class (not a synthetic check) against the freshly-exported model over a port-forwarded HTTP server, feeding two known-labeled held-out images — both correctly classified (Elephant 0.557/0.334, Boar 0.520). Fixed two stale/inconsistent claims in `docs/KNOWN_GAPS.md` that said the vision detector "is not exported or wired into anything" — both superseded, following the file's own established convention, with pointers to the fresh evidence. Full writeup in `ml/vision/README.md`'s "29-30 Aug... on-device benchmark" section. EON Tuner job `53262078` checked again at session end: still `running`, 1 completed / 3 running / 1 pending trial, no material progress since the prior check — the one completed candidate (`rgb-fomo-275`, int8 accuracy 0.384) remains far below the champion's per-class recall and has not been allowed to finish. **The ≥92%-per-class recall bar is still not met** (Elephant 0.906 at threshold 0.05, 1.4 points short; Boar 0.852, 6.8 points short) — nothing this window changed the accuracy numbers, only confirmed them for real on hardware and closed out the latency/GPU/wiring caveats. Nothing committed to git this window (no explicit user request to commit). See that checkpoint for full detail, then the still-relevant prior "RESUME HERE — 29 Aug (retrain complete, 92% bar not met; Boar heuristic closed; three-source gap check clean; GPU delegate gap confirmed permanent)" checkpoint right below it for the prior round: the standing plan's dataset-verification precondition ("verify dataset before retraining") was closed out for real — the Boar domestic-pig heuristic sample finished (17 more confirmed-bad filenames, 10 deleted live), and the three sources that had never had even a spot-check (`asian-elephants-dataset-v1`, `swg-eurasian-wild-pig`, `swg-empty`) were sampled and found clean, closing out a false alarm (tree/water categories, already filtered by the real pipeline) and surfacing a real positive finding (this source already has real night/IR frames). Separately, root-caused the GPU delegate question left open since 23 Aug: with real sudo access on the board, confirmed no apt repo (Debian, Arduino, or the Qualcomm artifactory overlay) provides `libtensorflowlite_gpu_delegate.so` — this is now a **confirmed permanent hardware/software gap**, not an access limitation; `mesa-teflon-delegate` and ArmNN's GPU backend exist but are architecturally incompatible drop-in replacements. With the dataset verified, retrained `yolo-pro-nano-attn_silu` against the fully-cleaned 12,808-image corpus (9,775 train / 3,033 test, confirmed matching live) — real held-out numbers: **Elephant recall 0.781** (P 0.974, F1 0.727), **Boar recall 0.706** (P 0.987, F1 0.656), Background false-positive rate 0.028. Both real improvements over the 26 Aug FOMO baseline (Elephant +8.8 pts, Boar +4.0 pts) but **neither clears the ≥92%-recall bar** — precision is very high on both classes, so the gap is concentrated in silent misses (zero predictions on 11.1% of Elephant / 23.5% of Boar test images), which is exactly what a threshold sweep is meant to probe; that sweep was launched immediately after and its result is the next thing to check. See that checkpoint for full detail, then the still-relevant prior checkpoint right below it: a full 142-image visual audit of `elephant-detection-cxnt1-v2`'s bare-Roboflow-numbered filename bucket (a third naming shape none of the prior three data-quality passes had covered) found 61 confirmed-bad images (43%) across four defect types — 9 more African bush elephant, 4 not-an-elephant-at-all (masked-crowd photos), 4 wrong-domain (historical/studio), 19 watermarked stock, 25 captive/managed-care domain — fixed locally (two exclude-list constants in `scripts/edge_impulse_upload_vision.py`, `--dry-run`-verified exact 52/52 + 9 match) and live (all 61 already-uploaded samples matched by sha256 and deleted via the Edge Impulse `deleteSample` API, 0 failures). The prior "RESUME HERE — 29 Aug (degenerate-box filter + live correction, EON Tuner research)" checkpoint right below covers the still-relevant prior round: a `MIN_BOX_AREA_FRACTION` filter was added to drop boxes below 0.03% of frame area, verified against the full corpus (13 boxes across 4 sources, all 13 individually visually confirmed bad — not just small), and, because 7 of those 13 were already live in the project on images that keep other valid boxes (content-hash dedup means a plain re-upload can never fix an already-live sample's labels), corrected live via a direct `setSampleBoundingBoxes` API call — all 7 applied successfully. A backgrounded research agent also closed out the EON Tuner objective question (no native recall objective exists) and surfaced UNO Q/QRB2210 details worth folding into Phase 3/5. See that checkpoint for detail, then the "29 Aug (upload pipeline integrity)" checkpoint right after it for the still-relevant prior round: three silent pipeline bugs in `scripts/edge_impulse_upload_vision.py` (a `sample_by_group()` seeded-shuffle instability, and a filename-keyed resume ledger going stale against two regenerable sources) were found, root-caused with precise per-content-hash diffing, fixed, and verified for real against the live project — the reconciliation hard-fail gate now passes clean, `TOTAL training expected 9810 actual 9810`, `TOTAL testing expected 3069 actual 3069`, exit code 0. See that checkpoint for the full root-cause chain, then the "29 Aug" checkpoint right after it for the still-relevant prior round: a fourth data-quality pass found a wholesale new species-contamination population (233 `af_`-prefixed African-elephant filenames in `elephant-detection-cxnt1-v2`, 5x the previously-known 45), fixed and dry-run-verified locally; a second Boar visual-audit sample (n=24) added 11 more confirmed-contaminated filenames to the curated exclude list; a cross-source broadcast-clip leak (`wb_framesb`, `wb_framesa00001` — hunting-broadcast-show footage, not field photography) was found leaking into both Boar sources and filtered; and the user's standing decision on the 984-image "frame" clip (the viral RAJAMURUGAN video) was finally implemented — capped to 10 diverse representative frames via a new `cap_named_group()` mechanism. All four fixes are `--dry-run`-clean with no unexplained gap. All three live-cleanup deletes have since been run for real by the user (802 via `cleanup_broadcast_contamination_vision.py`, 13 via `cleanup_boar_visual_contamination_vision.py`, 1,008 via `cleanup_frame_clip_duplication_vision.py` across two runs after one transient network timeout) — project 1097972 is now 12,794 → 10,971 remote samples, all pending live cleanup complete. **Next: a retrain against the cleaned project is needed for honest new per-class recall numbers**, and the "source more IR/night data" thread is still open — see the checkpoint below for exact state. Earlier text retained verbatim below for continuity — see the new checkpoint first, then the "28 Aug (later still #3)" checkpoint immediately below it for the prior round's still-relevant detail: user sharpened priority to Elephant-first, urgently, target >92% recall including at night, plus an explicit audit-and-fix instruction on the existing corpus's annotation quality. Both flagged IR/night Roboflow candidates were vetted and rejected on real visual inspection (`elephant-thermal` not actually thermal; `detecting-elephants-at-night` has no downloadable export). `wcs-elephas-maximus` confirmed fully exploited (194/325, no headroom). A third data-quality audit pass found a wholesale non-field-photography batch in `elephant-detection-cxnt1-v2` — 164 filenames sharing a naming shape the existing TV-broadcast filter didn't reach, 16/16 visually sampled were not usable (Thai TV broadcast, stock photography, or wrong-species African elephant). Local filter fix implemented and verified clean via `--dry-run`. Live cleanup script written and dry-run-confirmed (165 live matches) but the actual delete was blocked by the environment's permission classifier as a live external-service action — **pending explicit user confirmation to execute**, see the new checkpoint. Earlier text retained verbatim below for continuity — see the new checkpoint first, then, unchanged from before: project 1097972's live/manifest mismatch (995 samples) was decomposed into three causes and remediated — 1,178 stale-named orphans deleted, 1,368 split-boundary-reshuffled samples moved non-destructively, 192 residual "missing" Boar samples confirmed as benign already-known duplicates and left alone; a follow-up automated fix for that residual 192/9 gap was caught in `--dry-run` before going live and reverted — it would have silently zeroed out three major sources' training data (see `ml/vision/README.md`'s "995-sample live/manifest mismatch" entry for the full story and why). EON Tuner confirmed unusable for this project (two independent live failures), deployed threshold set to 0.05 for the field test only (explicit user rationale, must revisit before real ranger alerts go live), architecture head-to-head run — YOLO-Pro-nano has real numbers (Elephant R 0.860 / Boar R 0.797 at threshold 0.05), MobileNetV2-SSD OOM-killed a second time on a platform-side batch-size limitation the API cannot override and was dropped; **honest verdict as of that pass: the ≥92%-per-class recall bar was not met by any architecture/threshold tried**, closest was 6.0 points short on Elephant and 12.3 short on Boar — this is exactly the gap the current Elephant-focused audit-and-fix pass is working against; a final retrain back to the winning YOLO-Pro-nano config was in progress as of that checkpoint. The "RESUME HERE — 28 Aug (late)" checkpoint below this one covers Track B (vision genuinely wired into the pre-decision fusion path) and remains accurate as its own current state — the two tracks are independent and both still open)

## RESUME HERE — 4 Sept (later) — Boar-gap close-out best-effort vision retrain complete; no candidate cleared the adoption bar; deployed checkpoint untouched

Plan file: `prompt-for-the-compiled-stream.md` ("Boar-gap close-out — best-effort vision retrain"). This
session executed Step 2 and all of Step 3, reaching Step 5's conclusion. Step 1 (CLI flags for the three
untried levers) was already done in a prior session (`0cc4b16`). Step 4.1/4.2/4.3 (offline data-quality
work, SA-FARI checklist, Boar-representation audit corrections) were already complete from even earlier
sessions. Step 6 (the ~200-URL documentation sweep) remains explicitly deferred, unstarted, non-blocking.

**Baseline going in** (live-verified on real hardware, currently deployed, unchanged from before this
session): `yolo-pro`, `medium`, `no_attn_relu`, INT8, `min_score` 0.05 — Boar recall 0.852, Elephant
recall 0.906, background FP 0.166.

**Step 2 — baseline rerun (noise floor + corpus re-baseline).** Reran the identical deployed config
(`--family yolo-pro --yolo-variant no_attn_relu --yolo-sizing medium --skip-impulse`) against today's
corpus. Test split matched 30 Aug exactly (1503/844/974 images) despite the 121 orphan `uv29aug`
samples the audit had flagged — corpus has not drifted. Result @0.05: Boar 0.852 (exact match),
Elephant 0.905 (−0.001), background FP 0.160 (−0.006, better). **Noise floor established at ≤1 point**
on any of the three numbers — tighter than the plan's own prior ~1.5pt estimate from a mismatched-split
pair. Committed `5d0ac30`.

**Step 3 — the three named untried levers, all platform trials, single-variable, full threshold sweep
each, judged against baseline + noise floor:**

| Trial | Boar recall | Elephant recall | Background FP | Verdict |
|---|---|---|---|---|
| Step 2 rerun (same config) | 0.852 (exact) | 0.905 (−0.001) | 0.160 (−0.006) | noise floor ≤1pt |
| Trial 2 — color-space-augmentation medium | 0.834 (−1.8pt) | 0.889 (−1.7pt) | 0.134 (−3.2pt) | fails |
| Trial 3 — spatial-augmentation medium | 0.818 (−3.4pt) | 0.888 (−1.8pt) | 0.092 (−7.4pt) | fails, worse than Trial 2 |
| Trial 4 — freeze-backbone true | 0.731 (−12.1pt) | 0.800 (−10.6pt) | 0.219 (+5.3pt, worse) | fails decisively, all 3 numbers |

Trial 2 (highest prior — targets the RGB-daylight → grayscale-IR domain shift directly): real
regression on both recalls. Not adopted. Committed `49bda00`.

Trial 3 (addresses scale/crop/framing variance, less directly aimed at the Boar problem): larger
regression than Trial 2; a secondary "perfect F1" signal (exact ground-truth match, no partial credit)
collapsed 47.4%→20.5%, suggesting a localization-quality regression rather than pure confidence
recalibration. Not adopted. Committed `1bb2f01`.

Trial 4 (plan's own stated low prior — freezing the backbone removes exactly the adaptation a
heavily domain-shifted IR target needs, on top of `use-pretrained-weights: true`): confirmed
decisively. The only trial to regress all three numbers simultaneously, and by far the largest
margins. Training took only 50.2 min (fastest job this session, consistent with a frozen backbone
doing less work). Not adopted. Committed `0c02e49`.

**Step 3 is now fully closed** — all three named levers tried, full-swept, all regressed.

**Step 5 — adoption gate: never reached.** No candidate cleared Boar recall > 0.852 / Elephant recall
≥ 0.906 / background FP ≤ 0.166 by more than the noise floor, so **the deployed checkpoint stays
exactly as found** — Boar 0.852 / Elephant 0.906 / FP 0.166 @0.05, same `.eim` files, same impulse,
same threshold. No version snapshot, no export, no on-device benchmark was performed, since the gate
condition that would trigger them was never met. This is the plan's own explicitly-anticipated,
acceptable outcome ("A clean negative result with real numbers is the expected and acceptable outcome
here"). **No board interaction occurred this session at all** — every job this segment ran against
Edge Impulse Studio's cloud infrastructure (project `1097972`) via the API client script; the user was
told mid-session it was safe to fully disconnect the UNO Q hardware for parallel work, since nothing in
this Step 2/Step 3 sequence ever touches it.

Also committed this session, ahead of the retrain work: `a0ca100` — the carried-over "Sourcing pass
beyond SA-FARI" subsection of `boar-representation-audit.md` (Island Conservation Camera Traps flagged
as a candidate, SWG/WCS confirmed already fully tapped, Wildlife Insights flagged unexplored, two
Asian-elephant sourcing dead ends recorded).

**Seven commits this session, in order, all verified clean of any AI-authorship trailer** (the last
two written after this checkpoint's own first draft — updated in place rather than as a second
checkpoint, since nothing superseded it in between):
1. `a0ca100` — docs(vision): source additional IR candidates for Boar/Elephant, best-effort
2. `5d0ac30` — docs(vision): record Step 2 baseline rerun and noise floor for the Boar-gap close-out
3. `49bda00` — docs(vision): Trial 2 color-space-augmentation regresses both classes, not adopted
4. `1bb2f01` — docs(vision): Trial 3 spatial-augmentation regresses further, not adopted
5. `0c02e49` — docs(vision): Trial 4 freeze-backbone fails decisively, Step 3 closed, no adoption
6. `adcac70` — docs: checkpoint the Boar-gap close-out — no candidate cleared the bar (this
   checkpoint's own first commit)
7. `ce223ef` — docs(research): close two of Step 6's three load-bearing API unknowns

All seven pushed to `origin/develop` (`7c57d08..ce223ef`); nothing left unpushed.

Full detail (full sweep tables at every threshold, not just @0.05) is in `ml/vision/README.md`'s four
new dated sections between the 30 Aug entries and `## Reproducing`, and in `docs/KNOWN_GAPS.md`'s
"Vision detector does not reach the ≥92%-per-class-recall bar" section, which now has six consecutive
"4 Sept update, continued a [Nth] time" paragraphs (two from the exposure-lock/audit session, four from
this one). `ruff check .` (20 pre-existing errors, unchanged) and `pytest` (444 passed, 1 skipped,
unchanged from before this session's edits) verified clean before every commit.

**Resolved**: the eight `.log` files this session's background training/sweep jobs wrote under
`ml/vision/` are correctly gitignored (`.gitignore:49`, pattern `ml/vision/_*.log`) — not an
oversight, no action needed.

**Step 6 (documentation sweep) — partially done, not a full re-run.** The general ~200-URL sweep
itself turned out to already be comprehensive (5 files under `docs/research/platform/`, compiled
2 Sept, predating this session) — re-running it in full would have been redundant. What was actually
missing were the three specific questions Step 6's own text called out as "genuinely unknown and
load-bearing": fetched the live Edge Impulse docs + OpenAPI spec directly for those three (not a
doc-sweep agent fan-out) and closed two of them —
[edge-impulse-studio-vision-tuning.md](docs/research/platform/edge-impulse-studio-vision-tuning.md)'s
4 Sept addendum (items 1-3 there): the model-testing/threshold API surface is confirmed to have no
shortcut (the script's classify-job-per-threshold sweep is the correct approach, no change indicated);
Experiments is a real Studio UI feature (impulses genuinely coexist) but is not reachable from the
API-only training script (no impulse-creation endpoint found in the OpenAPI spec); versioning/restore
semantics remain genuinely open — the OpenAPI spec has version list/update/delete/make-private verbs
but no create/restore verb, even though this project has created snapshots in practice, so creation is
most likely a job type dispatched through `/jobs`, unconfirmed — needs a live API discovery pass, not
more doc-reading, if it's ever needed for real.

**Next step**: nothing plan-mandated remains. The one still-open item (versioning/restore API
mechanics) is only worth chasing if a future session actually needs to snapshot-and-restore
programmatically — not urgent on its own. Otherwise the next real lever for the Boar gap (if one is
ever needed) is new *data*, not more platform-config trials on the same corpus — all three plausible
untried config levers are now falsified.

**Session-continuity note, per `CLAUDE.md`'s protocol**: this session completed a full, coherent unit
of work (Step 2 + all of Step 3 reaching Step 5's conclusion, plus closing out Step 6's load-bearing
unknowns) with nothing mid-flight and nothing unpushed. Default applies — start a fresh session for
whatever comes next; continue in this session only for a small immediate follow-up fix to something
that just ran here.

## RESUME HERE — 4 Sept — night exposure-lock implemented and host-tested for the active Camera path (not just written up); EventVideoRecorder/GStreamer side still unimplemented; Workstream 2 (Boar representation audit) complete

A separate, parallel session from the one that produced the "3 Sept — Boar deterrence closed the
loop" checkpoint immediately below. That checkpoint's Workstream 1 (burst-majority debounce) and
Workstream 3 (tri-state node scope) are its own and are untouched here — do not conflate the two.
This session owned only two items carved off the same "close the Boar detection gap" plan: the
exposure-lock fix (originally written up only, "the camera code is the other session's" — the user
explicitly lifted that constraint this session because the other session was reported no longer
active) and Workstream 2 (the Boar representation audit, complete as of this checkpoint — see below).

**Exposure-lock: implemented, not just written up.** `docs/qa/night-ir-led-characterisation.md`'s
1–2 Sept finding stands (auto-exposure + IR was the only configuration producing meaningful Boar
false positives; locked exposure ≈256 gave zero). `perception/camera.py`'s `Camera` class (the
active default path — `EVENT_VIDEO_ENABLED` defaults `False`) now asserts manual auto-exposure mode
on `open()` (`_assert_auto_exposure()`, logs a warning but does not fail open if the assertion
doesn't hold) and exposes `lock_night_exposure(value=config.NIGHT_LOCKED_EXPOSURE)`, wired into
`reflex_loop.handle_footfall_event`'s IR-gating branch (`if night is True:`) so a real night
detection locks exposure before the evidence burst is captured. New config:
`services/config.py`'s `NIGHT_LOCKED_EXPOSURE = 256` and
`NIGHT_EXPOSURE_LOCK_ENABLED = os.environ.get("ELETECT_NIGHT_EXPOSURE_LOCK", "1") != "0"`.
`CameraProtocol` in `reflex_loop.py` gained `lock_night_exposure() -> bool` as a required method, so
every class satisfying it needs one.

**Live re-test correction, stated plainly rather than left standing.** The earlier write-up's claim
that the container's camera path "sits frozen at 156" and cannot accept exposure writes did **not**
reproduce on a live re-test this session — exposure writes now stick and read back correctly.
Recorded as a re-test correction, not a claim the original observation was wrong when it was made.

**A second, unrelated bug found and fixed on the same path, independently verified two ways:** the
camera was live-observed sitting in stale Manual/2000 exposure state on open in one verification
path, and confirmed via a second independent check — both are written up in `docs/KNOWN_GAPS.md`'s
rewritten exposure-lock entry, which is the fuller account; this checkpoint only summarizes.

**GStreamer/`EventVideoRecorder` path (`perception/video.py`) remains genuinely unimplemented.**
That class builds a fresh `Gst.parse_launch` pipeline per event with no persistent capture handle
analogous to `cv2.VideoCapture`, so there is no direct equivalent of a late `.set()`-style exposure
lock. Added `EventVideoRecorder.lock_night_exposure()` as an honest no-op — requires `open()`,
logs that it is not implemented on this path, always returns `False`, never raises — purely to
satisfy `CameraProtocol` so the app does not crash with `AttributeError` if this path is ever
enabled (it is inert today: `EVENT_VIDEO_ENABLED` defaults `False`). Two real-implementation paths
exist and were deliberately not attempted, unverified on hardware: baking exposure into `v4l2src`'s
own `extra-controls` at pipeline-build time (affects the whole recording, not just the evidence
burst — unevaluated trade-off), or a live GStreamer element-property change on an already-PLAYING
pipeline.

**Tests and regression bar.** 17 new tests across `tests/test_camera.py` (9, incl. the
`_assert_auto_exposure()` open()-time checks and the full `lock_night_exposure()` success/no-stick/
control-error/disabled/before-open/after-close matrix, using an extended `_FakeCapture` with
configurable exposure state and failure-injection knobs), `tests/test_video.py` (3, the
not-implemented-here contract), `tests/test_reflex_loop.py` (5, exercising the real call site:
night+firing locks before the burst, daylight/undetermined-night do not lock, Tier 1 never locks,
an `is_night` error still locks before the forced pulse — via a private counter on `_FakeCamera`,
deliberately not logged into the shared `call_log` so existing exact-order/exact-slice assertions
on that log stayed untouched). Full suite: 415 passed, 1 skipped (up from 398/1 pre-existing
baseline), `ruff check` clean.

**What this is not.** The FP-suppression outcome itself — whether locking exposure actually cuts
the Boar false-positive rate in production — has not been re-measured against this code path this
session. Only the original 1–2 Sept board battery in `night-ir-led-characterisation.md` supports
that claim; this session made the mechanism real and host-verified, it did not re-run the field
battery against it.

**Docs folded back:** `docs/KNOWN_GAPS.md` (exposure-lock bullet rewritten in place — implemented
and host-tested for `Camera`, open for `EventVideoRecorder`; cross-referenced into the adjacent
~3.8fps auto-exposure-throttle entry), `ml/vision/README.md` (Boar section's camera-control
paragraph updated from "not implemented, the other session's code" to implemented/corrected,
pointing at the KNOWN_GAPS entry), `docs/qa/boar-gap-session-notes.md` (new dated section appended,
the file's existing "write-up only" section from earlier left untouched per its append-only
convention).

**Exposure-lock work is committed**: `fa19eb5` (camera.py/video.py/config.py/reflex_loop.py + the
three test files) and `a6fe853` (the doc fold-back — KNOWN_GAPS.md, ml/vision/README.md,
boar-gap-session-notes.md, this HANDOVER.md checkpoint).

**Workstream 2 (`ml/vision/boar-representation-audit.md`) is also complete, docs-only, no retrain.**
Confirmed all 7 Boar-source counts against `dataset_manifest.json` directly. The real finding: the
plan's own headline number — real night/IR Boar imagery at 64/7,394 (0.87%) — did not survive a read
of `DATASETS`' own sourcing notes and needed correcting, not transcribing. `trail-camera-v2` (1,311
images) is documented in its own `DATASETS` entry as "day + IR-night," and a 14-image visual sample
found 57% were real night/IR trigger frames — extrapolated across the source, that gives a corrected
estimate of ~814 real night/IR images, ~11% of 7,394, not 0.87%. Two more sources
(`swg-eurasian-wild-pig`, `wcs-sus-scrofa`) show additional real but unquantified night/IR content in
their own prior spot-checks, so ~11% is a floor. Corrected in place in `docs/KNOWN_GAPS.md` and
`ml/vision/README.md`'s Dataset section, both of which previously stated 0.87% flatly (added by an
earlier doc-hygiene pass reading the manifest's real/synthetic split alone, which has no lighting/IR
field — an honest read of an incomplete proxy, not a fabricated number). The audit also surfaces that
Elephant's own largest source has the identical undercount problem, so this is a method blind spot,
not Boar-specific. Proposes a `conditions` metadata schema (domain / lighting / ir_confirmed /
sample_verified_n+of / angle / distance / occlusion) for `DATASETS`/`dataset_manifest.json`, not
backfilled this pass. Records SA-FARI (arXiv 2511.15622) as the lead sourcing candidate at
*candidate, not sourced* — both blocking checks (species-table confirmation, licence terms) still need
a logged-in Hugging Face session, not attempted. Names freeze-backbone and augmentation-strength as
untried next trials, confirmed unreachable from the training script's current CLI without adding a
flag first. Not yet committed as of this checkpoint — the next action.

## RESUME HERE — 3 Sept — Boar deterrence closed the loop: per-poll+per-burst debounce committed, tri-state node scope + confirmation-path streak gate + Boar horn content built and tested (uncommitted), ADR 0023 + boar research doc written, Hunchun light-vs-sound study found readable (correcting the earlier "paywalled" assumption)

Direct continuation of the "close the Boar detection gap" plan
(`C:\Users\abhin\.claude\plans\task-close-the-boar-woolly-wadler.md`), run in the parallel Boar-focused
session the checkpoint below explicitly deferred items 4/5 to. Running notes with every real number are
in `docs/qa/boar-gap-session-notes.md` — this block is the summary, that file is the source.

**Step 0 + doc hygiene — closed, committed `bd24f87`/`522675e`.** Vision runner was down since the
07:04 reboot (host-side process, started by hand, container restart-policy fix doesn't reach it) —
restarted, confirmed `/api/info` (project 1097972, `Boar`/`Elephant`, `min_score 0.05`), then given
two-layer supervision verified on real hardware: a user systemd unit (`Restart=always`) for process
death, plus a port-1337 liveness probe added to the existing `scripts/eletect-x-watchdog.sh` cron job
for the hung-but-alive case the unit alone can't see. Stale docs fixed alongside: `detector.py`'s
`min_score` docstring, `edge_impulse_train_vision.py`'s module docstring (three-class YOLO-Pro not
two-class FOMO, project 1097972 not 1094260, real 4,094/7,394 Elephant/Boar counts), `KNOWN_GAPS.md`'s
stale 29 Aug nano entry, `ml/vision/README.md`'s headline Dataset table.

**Workstream 1 — per-class consecutive-poll debounce — closed, committed `596b432`.** Real replay
against the 30 Aug 2-hour, 40,422-frame board log (`monitor_2h_20260830.log`, aggregated on-board over
SSH, never copied down): frame baseline 31.53% (matches the published number); production-faithful
poll baseline (burst-OR across the real 3-frame poll unit) is worse, **43.64%** — the plan's flagged
"burst-OR amplifies FPs" risk, confirmed real; a first pass at per-poll N≥2 barely dented it
(43.64% → 40.48%, a 3-point drop). Root cause: burst-OR lets one positive frame in three carry a whole
poll positive, so consecutive-poll counting doesn't touch same-poll noise. Fix: within-burst
majority-of-3 aggregation for Boar specifically
(`VISION_SPECIES_BURST_MAJORITY_LABELS = ("Boar",)`), stacked with the N≥2 poll debounce —
**30.70% burst-majority baseline, 27.54% with N≥2 on top**, back in line with the frame-level number.
Elephant stayed 0% false positives at every single stage throughout (unconditionally OR-based, never
subject to the majority gate) — the no-op guard held.

**Workstream 3 — tri-state node deterrence scope — built and tested, uncommitted, shipped flag-off.**
`NODE_DETERRENCE_SCOPE` (`elephant_only`/`boar_only`/`both`, env-first via `ELETECT_DETERRENCE_SCOPE`,
constant fallback, unknown value → warn + fall back to `elephant_only`, never raise) now gates whether
the horn/LED fire and whether video is kept on a Boar detection. `NODE_HOUSEHOLD_PROXIMITY` got the
identical env-first treatment in the same change (`ELETECT_HOUSEHOLD_PROXIMITY`) — same class of
setting, same deployment-day config-delivery gap, fixed together rather than only for the new flag.
The two derived label constants resolve byte-for-byte to `("Elephant",)` at the shipped default —
same value as before this workstream, only the assignment is rewritten. `EXPERIENCE_DB_PATH` now
derives from scope (`experience.sqlite3` at `elephant_only`, `experience-{scope}.sqlite3` otherwise) so
reverting the flag is the same action that restores the trial's bandit DB — no separate archive step
to forget, and `main.py`'s startup banner now logs the resolved scope + labels + DB path together so a
mid-trial scope flip (which would silently swap which learned policy the node is running) is visible
in the boot log.

**The finding that made Workstream 3 non-optional, not just nice-to-have:** the confirmation path
(`check.confirmed` → immediate return from `_watch_for_vision`) bypasses Workstream 1's debounce
entirely — the moment Boar enters `DETERRENT_TARGET_LABELS`, a single spurious poll would confirm and
fire the horn against a ~31-44% real FP rate. Fixed by extending the same streak gate to confirmation:
a label only confirms once its streak requirement is met (Elephant's is 1, unchanged, bit-for-bit
identical confirm-and-exit timing), and a streak-rejected poll is downgraded to `BASELINE_VISION`
rather than contributing positive log-odds to `fuse()`. Boar horn content (`cognition/config.py`,
`resolve_tier_action(..., species="Elephant")`): Tier 1 reuses the lion track, Tiers 2/3 the tiger
track — both already provisioned on the DFPlayer flash, no new sourcing, no `SCHEMA_VERSION` bump. No
bee track on any Boar tier (King et al. 2007's aversion mechanism has no boar analogue).

Four new end-to-end (`_fire()`-level) behavioural tests added this pass, all green on first run: a
single spurious Boar poll fires nothing under `boar_only`; two consecutive Boar polls fire the
deterrent and keep video; Elephant still confirms on poll 1 under `both`; Boar fires nothing under the
shipped `elephant_only` default at any streak length. Full suite: **398 passed, 1 skipped**. `ruff
check .`: clean. Existing watch-mechanics tests needed no edits — the proof N=1 Elephant stayed a
no-op through both the debounce and the confirm-gate changes. **Not yet committed** — next action.

**A correction worth its own line: the Hunchun light-vs-sound study is readable, not paywalled.** The
plan assumed a direct boar-specific light-vs-sound comparison (a Hunchun, China cornfield study) was
inaccessible and unread. Re-checked this session per the project's own verify-before-declaring-blocked
discipline and found it freely readable via PMC: Ani (2025) 15(7):1017, DOI 10.3390/ani15071017. Real
numbers: red solar blinkers 32.25±4.22 days before efficacy declined (best single treatment); Amur
tiger + wild boar distress calls 26.50±2.38 days; category ranking tactile > visual > auditory. Read
carefully rather than at face value: every Hunchun treatment ran as continuous, unconditional exposure
for weeks — exactly the condition this device's triggered-once-per-encounter horn (ADR 0022) and
Widén et al. 2022's own triggered-camera-trap design both exist to avoid — so the honest reading is
"continuous auditory broadcast habituates faster than continuous visual broadcast in this environment,"
not a verdict on triggered predator-call playback specifically. What it does add directly: a real,
quantified, actual-Amur-tiger-call-on-actual-wild-boar result (26.5 days measured efficacy) behind
ADR 0023's tiger-track choice — stronger than the ecological-inference argument alone. All three places
that had carried the old "unread, paywalled" placeholder (`cognition/config.py`'s comment, ADR 0023
Decision C, ADR 0023's Follow-ups) were corrected to reflect this.

New docs this session: `docs/decisions/0023-boar-deterrence-content-and-node-species-scope.md` (four
decisions: tri-state scope + env delivery, the confirmation streak-gate fix, Boar horn content, the
experience-DB path derivation + mid-trial-flip hazard) and
`docs/research/boar-deterrence-behavioral-science.md` (boar counterpart to the elephant behavioral
review, same confidence-tier convention).

**Immediate next, in order:** commit Workstream 3 as its own commit(s), separate from `596b432` —
`services/config.py`, `reflex_loop.py`, `cognition/config.py`, `main.py`, three test files, ADR 0023,
the research doc; re-verify full suite + ruff immediately before that commit; write the exposure-lock
cross-reference into `KNOWN_GAPS.md`/README (write-up only — the camera fix is the other session's
code, do not implement it here); Workstream 2 (Boar representation audit, docs-only) stays deferred
past the ship date per the plan. `TRIAL_READINESS_PLAN.md` §D already carries the ship-day checklist
line and the exact SSH flip commands for the scope flag; `docs/KNOWN_GAPS.md` still needs the shared
deployment-day config-delivery gap opened as its own dated entry (affects both `NODE_DETERRENCE_SCOPE`
and `NODE_HOUSEHOLD_PROXIMITY` — ADR 0021's audited config interface is design-only, unbuilt).

## RESUME HERE — 3 Sept (later still) — H.264 bitrate root cause fixed and committed; ~3.8fps camera-throughput risk documented; in-process crash recovery closed (restart-policy fix + durable cron watchdog)

Direct continuation of the prior checkpoint's two open items. Item 1 (bitrate control) and item 2
(in-process crash recovery) are both closed this pass. Item 3 (VIN power fix + camera-under-VIN
check) still needs the user physically present and was not touched. Items 4/5 (Boar temporal-
aggregation fusion fix and Boar recall/data-sourcing work) are confirmed by the user to be handled
in a separate, parallel session and were not started here.

**Item 1 — H.264 bitrate control, root-caused and fixed, committed.** `v4l2h264enc`'s
`extra-controls` needs both `video_bitrate_mode=1` (Constant Bitrate) and `video_bitrate={bps}` —
the driver's default `video_bitrate_mode=0` (Variable Bitrate) treats `video_bitrate` as only a
soft average, with the encoder's QP range actually governing output, explaining the previously
observed ~16x overshoot. Fixed in `device/mpu/perception/video.py` and `services/config.py`, test
added in `tests/test_video.py`. Full suite green (362 passed, 1 skipped), `ruff check` clean.
Committed as `aa41fb2` on `develop` — no AI-authorship references, per CLAUDE.md.

Same pass surfaced a second, separate, still-open finding, written up in both the module docstring
and `docs/KNOWN_GAPS.md` rather than chased further: real camera throughput measured at only ~3.8fps
against the 30fps this pipeline negotiates and the sensor advertises as its only mode at every
resolution tested. A 4-stage buffer probe found the same ~3.8fps at every pipeline stage alike,
ruling out decode/convert/encode cost — the bottleneck is the camera's own capture rate. Leading
hypothesis (unconfirmed): auto-exposure throttling frame rate in low ambient light. The decisive
test (force manual exposure, re-measure, restore) was not run — it changes live camera hardware
state on the production board and needs a human present first. Real consequence if true: raw H.264
has no per-frame timestamps, so a stretch of real time recorded at ~3.8fps plays back as a shorter
clip at nominal 30fps, not slow motion — event footage could represent far fewer real seconds than
its configured duration implies, worst-case exactly in the low-light conditions a night encounter
would have. Should be resolved, or at minimum exposure-locked per
`docs/qa/night-ir-led-characterisation.md`'s own Finding 4 recommendation, before
`EVENT_VIDEO_ENABLED` is ever flipped on for a live trial night.

**Item 2 — in-process crash recovery, closed, two layers, no sudo used anywhere.** Confirmed the
pre-fix state live on the board: `eletect-x-main-1`'s Docker restart policy was `no` (Docker's
default), meaning an unhandled exception in `main.py`'s PID 1 would exit the container and leave the
deterrence system dark until a manual restart or full reboot.

Layer 1, immediate, applied live: `docker update --restart=unless-stopped eletect-x-main-1` —
verified via `docker inspect`. Makes the Docker daemon bring the container straight back up on any
exit, no supervisor needed for this specific failure mode.

Layer 2, durable: that live fix alone is not persistent — the platform-generated
`~/ArduinoApps/eletect-x/.cache/app-compose.yaml` carries no `restart:` policy and is regenerated on
every App Lab redeploy, which would silently revert Layer 1. Wrote `scripts/eletect-x-watchdog.sh`
(repo-tracked), deployed it to the board at `~/bin/eletect-x-watchdog.sh`, and installed it via the
`arduino` user's own crontab (`*/5 * * * *` — the account already has `docker` group membership, no
sudo needed, and `crontab -l` was empty before this, so no conflict). The watchdog reads the app's
real status via `arduino-app-cli app list --format json` (not a hardcoded container name),
re-applies `unless-stopped` if the policy has drifted, and — only after seeing the app down for two
consecutive 5-minute ticks, so it doesn't race a legitimate in-progress redeploy — restarts it via
`arduino-app-cli app restart user:eletect-x`. Verified end-to-end on the real board: simulated a
policy drift (`docker update --restart=no`), ran the watchdog once by hand, confirmed it detected
the drift, re-applied `unless-stopped`, and logged the action to
`~/.local/state/eletect-x-watchdog/watchdog.log`.

Documented in `docs/KNOWN_GAPS.md`'s "Sudden power loss and in-process crash recovery, both
checked" entry (retitled from "...does not" to reflect the fix; status changed to **fixed**).

**Not yet done:** commit this window's `docs/KNOWN_GAPS.md` and `scripts/eletect-x-watchdog.sh`
changes to git (about to happen next). Deciding whether to flip `EVENT_VIDEO_ENABLED = True` still
waits on the VIN-power camera check and, now, on resolving the fps-throughput risk — both need the
board in front of a human.

## RESUME HERE — 3 Sept (later) — ADR 0020 event-video pipeline fixed and verified on real hardware; power-loss recovery confirmed empirically

Direct continuation of the LoRa-deprioritized "focus on getting the video" instruction. Two things
done: found and fixed why the event-video feature as coded would have failed on every real trigger,
and separately checked (because the user asked directly) whether this board recovers cleanly from
sudden power loss in the field.

**Event video.** Ran the actual GStreamer element chain from `perception/video.py` for real against
the production container (`eletect-x-main-1`) for the first time this project has tried it, and it
failed — `matroskamux` cannot be reached from `v4l2h264enc`'s output because the bridging element,
`h264parse`, lives in `gstreamer1.0-plugins-bad`, which is not installed in the container and can't
be (no apt candidate in the pinned snapshot repo, no root). Independently, `EVENT_VIDEO_FRAMERATE =
15` turned out to not exist as a real camera mode at any resolution — GStreamer's `v4l2src` requires
exact caps matches (unlike OpenCV's V4L2 backend used elsewhere here, which snaps to nearest); only
30fps links, confirmed by sweeping 5/10/15/20/25/30fps at several resolutions.

Fixed both: dropped the muxer, writing a raw H.264 Annex-B elementary stream straight to `filesink`
(arguably a stronger version of ADR 0020's own truncation-resilience argument than Matroska was —
no header/index to corrupt at all), and moved to 30fps. Validated with a real 6-second dual-branch
recording against the live camera (zero pipeline errors, 24.8MB file), then pulled the file to a
separate machine and decoded it frame-by-frame via OpenCV/FFmpeg — real, sharp, correctly-oriented
frames, the first end-to-end proof this encode chain works on real hardware. Landed in
`device/mpu/perception/video.py`, `device/mpu/services/config.py`, and
`device/mpu/tests/test_video.py`; host suite green (362 passed, 1 skipped), `ruff check` clean.
Full detail in `docs/KNOWN_GAPS.md`'s "ADR 0020's event-video pipeline..." entry (3 Sept).

**Still open, `EVENT_VIDEO_ENABLED` stays False until both close:** the H.264 encoder's bitrate
control looks like it's being silently ignored (observed ~16x over the configured 2 Mbps target —
real storage-budget consequence against the board's ~15GB free); and every check above ran on
USB-C/hub power, not VIN — the field build is VIN-powered and the camera has still never been
proven to enumerate under that topology.

**Power-loss recovery, checked because the user asked directly ("uno q gets sudden power off, it
should auto recover").** Good news, and not speculative — this board has already had four real
sudden-power-loss events in the 24 hours before this check (the documented brown-out fault), and
every single one recovered cleanly with no manual intervention: `docker.service` and
`arduino-app-cli.service` are both enabled at boot, `arduino-app-cli` itself relaunches the
`eletect-x-main-1` app container on daemon start (confirmed via `docker inspect` — `StartedAt`
lands ~40s after the daemon's own start, `RestartCount: 0`, a clean fresh start not a crash loop),
and `journalctl` on the two prior crash-boots shows both services starting with no errors beyond
benign Docker sandbox-cleanup noise. The camera device path already survives a reboot too — it's
resolved via the udev by-id symlink, not a raw `/dev/videoN` index, specifically because indices
are known to reshuffle across a reboot (verified 17 Aug). SQLite's default crash-safe rollback
journal covers `ExperienceStore` with no application code needed, and `main.py` already clears
orphaned video scratch files left by a run that died mid-recording on every startup.

**The gap that remains, distinct from power loss, and already named in this file's own 2 Sept
brown-out entry:** an in-process crash while the board stays powered has no recovery path at all.
`main.py` runs as PID 1 in the container, the container's Docker restart policy is `no`, and there
is no exception handling anywhere in `main.py`'s top-level code — an unhandled exception anywhere
in the wiring would exit the container and leave the deterrence system dark until the next reboot
or a manual restart. Not exercised live this session (killing PID 1 in the production container was
deliberately not done without asking first — the user's actual concern turned out to be the power-
loss case specifically, which is already confirmed working). The remedy already on record (a
`Restart=on-failure` supervisor, or Monit) is the concrete next step if this needs closing before
the trial. Full detail in `docs/KNOWN_GAPS.md`'s "Sudden power loss recovers cleanly today..."
entry (3 Sept).

**Not yet done, next concrete steps toward the contest video:** commit these code changes; decide
whether to flip `EVENT_VIDEO_ENABLED = True` once the bitrate control and VIN-power camera check are
closed (both need the board in front of a human — VIN fix is Step 0 of the still-paused MPU
power-baseline plan); if a crash-recovery supervisor is wanted before the trial, that is unscoped
work, not yet started.

## RESUME HERE — 3 Sept — onboard auto-IR/photoresistor diagnosed and self-corrected; bench-rig scope narrowed to daylight-only; reboot-resilient overnight matrix run (cron + watchdog) completed cleanly and analysed; ADR 0022 (vision watch window + vision-gated deterrent) committed to `develop`

Continuation of the screen-based bench-rig aiming work from the prior session. Two threads: diagnosing
a persistent bright-hotspot artifact in dark-room test frames, and running/analysing the overnight
vision-scoring matrix once the diagnosis cleared the rig for use. Separately, the already-written
ADR 0022 (vision watch window + vision-gated deterrent) was verified and committed.

**Root cause of the hotspot: the Arducam B0490's own onboard auto-IR illuminator, not auto-exposure.**
I had told the user earlier (prior session) that IR was "never in play" and the washout was purely an
auto-exposure metering artifact against a mostly-black frame. That was wrong, and I corrected it
plainly once the user's own questions ("maybe the IR is reflecting off the screen," "maybe the onboard
IR LED") pointed at the right mechanism. The B0490 (IMX462) has a built-in 940 nm IR illuminator with
automatic IR-cut-filter switching, driven by a **passive photoresistor on the camera module itself —
not software-controllable** (`docs/decisions/0001-usb-camera-imx462.md:10`,
`docs/VISION_MODEL_BUILD_PROMPT.md:400`). This is a different illuminator from the project's own
external 850 nm MOSFET-driven IR LED used for real field deterrence — that one is already cleanly
characterised at range with no clipping in any run (`docs/qa/night-ir-led-characterisation.md`) and is
unaffected by any of this. Diagnostic signature that nailed it down: zero saturation held constant
across a full exposure sweep (real monochrome illumination, not a clipping artifact) and the hotspot
invariant under camera tilt (the LEDs are coaxial with the lens, so tilting the camera doesn't change
their geometry relative to the scene — ruling out a reflection). Confirmed decisively by turning the
room light on and re-running the same exposure ladder: saturation jumped from ~0 to 215–248 across the
ladder and the hotspot vanished entirely.

**Consequence: the screen-based bench rig can only validate daylight-scope detection behaviour.**
Because the onboard IR fires automatically in genuine darkness and cannot be disabled in software, any
rig run with the room dark is contaminated by this washout regardless of exposure settings. Night-time
detection behaviour has to keep relying on the separate, already-completed physical night-IR
characterisation at real range (`docs/qa/night-ir-led-characterisation.md`), not this rig. This is a
scope narrowing, not a new gap — no code changed as a result, just how the rig's results going forward
should be read.

**Overnight matrix run: made reboot-resilient, completed cleanly, and analysed.** Before restarting,
killed a stale 6-hour leftover `exposure_ladder.py` process competing for the camera device, and
restored `white_balance_automatic`/`gain`/`backlight_compensation` to their defaults (the diagnostic
ladder's own cleanup only restores `auto_exposure`). Deliberately kept auto-exposure (`nc.open_camera(None)`)
for the real scoring run rather than carrying over the diagnostic ladder's locked-exposure path — the
manifest images span too wide a brightness range for one fixed exposure to expose most of them
correctly. Made the run reboot-proof: `etx_watchdog.sh` (checks the Edge Impulse runner via listening
socket, the matrix harness via a bracketed pgrep pattern to avoid self-matching) installed into a real
crontab (`* * * * *` plus `@reboot`) — the first install attempt was blocked outright by the Claude
Code auto-mode permission classifier as an unauthorised persistent/system-modifying action; it
succeeded only after the user's explicit "Ok do it" in direct response to my offer to retry.
User reported turning the room light off for about an hour partway through (~11:46 IST) — checked the
full run log for that window and found no evidence of contamination (luma stayed 103–134 throughout,
almost certainly because the monitor's own brightness kept the onboard photoresistor from tripping even
with the room light off), so nothing needed excluding from the analysis.

Stopped the run cleanly on the user's call ("stop now and analyse"): matrix, EI runner, supervisor
loop, cron entries and the laptop-side rig script all confirmed stopped independently (not just via a
single ambiguous combined-command exit code — see the ssh 255/pgrep note in KNOWN_GAPS if written up,
otherwise this paragraph is the record). Pulled and analysed `matrix.jsonl`: **2,314 records, 3.64 h
span, zero errors, single stable `boot_id` throughout (cron/watchdog reboot-resilience never actually
needed to prove itself, but stayed armed the whole time), latency mean 205.7 ms / median 204.2 ms
(daylight-frame range, consistent with the 30 Aug on-hardware benchmark)**.

**The rig's own detection-accuracy numbers from this run are not trustworthy as a model-quality
verdict, and must not be quoted as one.** Elephant hit-rate at threshold 0.5 came out low (~7.8%) with
mean confidence on true-Elephant frames lower than on true-non-Elephant frames — read in isolation this
looks like a badly broken model, but a screen-reshoot introduces real domain shift (moiré, glare,
colour-space differences, the whole IR/exposure saga just diagnosed above) that can drive a genuinely
decent model to near-random or inverted scores on rig data without reflecting anything about real-world
performance. Cross-checked against `ml/vision/README.md`'s actual held-out eval for the deployed
`yolo_attn2` checkpoint, which paints a materially different and healthier picture: precision ~97–98%
on both classes, recall 0.835 (Elephant) / 0.586–0.66 (Boar) — neither clears the ≥92%-per-class-recall
target, but that gap was already known and tracked before this session, not newly revealed by the rig.
Answered the user's direct question ("does that mean our model is performing bad?") honestly on this
basis: the rig result doesn't indict the model; the real, still-open work item is the pre-existing
recall gap, not something new from tonight.

**ADR 0022 verified and committed.** `docs/decisions/0022-vision-watch-window-and-vision-gated-deterrent.md`
plus its implementation (`device/mpu/services/config.py`, `device/mpu/services/reflex_loop.py`,
`device/mpu/tests/test_reflex_loop.py`) were written in the prior session; this session re-verified
both (full suite 362 passed / 1 skipped, `ruff check .` clean) and landed two commits on `develop`:
`0b228a1` `docs: add ADR 0022 (vision watch window and vision-gated deterrent)` and `42caab0`
`feat(mpu): implement bounded vision watch window and vision-gated deterrent`. Caught and fixed my own
process mistake here: the first commit went out with the harness's default AI-co-authorship trailer,
which directly violates CLAUDE.md's hard rule ("never reference AI assistance in... commits"); caught
it myself before the user had to flag it and fixed it via `git commit --amend`, then wrote the second
commit correctly from the start. Summary of what ADR 0022 actually does, for anyone resuming cold:
replaces the old single 2-second-post-trigger vision burst with a bounded polling watch window (8 s
base / 45 s extended, sourced from ADR 0008's 45–65 s worst-case seismic lead time) so vision gets a
real chance to see an animal that was still 130 m away at the moment of the seismic trigger; and gates
the deterrent on vision confirmation in daylight only — `_vision_could_see()` treats a dark scene with
the illuminator off as blindness rather than a real negative, so **every night event still fires on
seismic alone** (stated in the ADR as the honest, deliberate scope limit — proactive illumination
during the watch is the follow-up that would close it, and is explicitly not decided here).

**Not touched this session, deliberately:** the paused MPU power-baseline plan (Steps 0–2 need the user
physically present with a multimeter — see the standing plan file); ADR 0020 event-video work, paused
behind that same power question; the inference-latency figure reconciliation across 138 ms / 205–262 ms
/ today's 205.7 ms readings (a documentation note, not urgent); the "seismic-warns-everyone has no LoRa
transport" gap; and further model recall-improvement work (real, tracked, not started today).

## RESUME HERE — 2 Sept (overnight, later) — MCU flash-path settled + firmware-state corrected + new flash runbook; night camera/IR battery + dawn soak both DONE and analysed (ADR 0019 night gate validated on real sunrise); board rebooted spontaneously ~08:27 IST 2 Sept (64 s, self-recovered) → hardware work stopped for the session; platform-docs research consolidated into `docs/research/platform/` (power/reboot fix = VIN power; GPU accel confirmed impossible on QRB2210); still no git commit, no reflash

Autonomous continuation of the same overnight session (user asleep, explicit "look into the Arduino
UNO Q docs and find if there is actually a way to do this" + "update all findings and learnings so
we never get confused in another session" + "finish everything ... you have my full permission").
**No code changed. Nothing committed to git. No reflash. No power rewire. No actuator fired outside
the sanctioned `night_char.py` battery.** Board health held: `boot_id`
`6b2c727a-af0d-4517-a6c7-a8069da92a64` unchanged at every check, container `eletect-x-main-1`
`RestartCount=0` / running, thermal 41–46 °C throughout.

### The MCU flash question is settled — there IS a supported headless path

Earlier notes (and an earlier claim this session) said "no verified flash procedure exists on this
Windows machine." **That was wrong.** Direct inspection of the board plus the Arduino / Edge Impulse
App Lab docs confirms:

- `arduino-app-cli app restart user:eletect-x` compiles the sketch **and uploads it to the
  STM32U585 in one step** — the same operation as App Lab's green *Deploy* button. This is exactly
  what the 1 Sept bring-up used ("STM32 flashed clean via OpenOCD ... `arduino-app-cli app restart`").
- The flash is an **on-board SWD link** — the Qualcomm SoC bit-bangs SWD on its own GPIO
  (`/opt/openocd/openocd_gpiod.cfg`, bundled OpenOCD at `/opt/openocd/bin/openocd`, not on `PATH` —
  that absence is what misled the earlier check). **Nothing runs on the Windows machine. No probe.
  No `rsync`.**
- Low-level path: `arduino-cli compile -b arduino:zephyr:unoq:wait_linux_boot=app` then
  `arduino-flash <sketch.ino.elf-zsk.bin>`. The 1-arg `arduino-flash` writes **only the sketch
  partition** (`0x080F0000`), never the Zephyr core → not hard-brickable, always re-flashable over
  the same GPIO SWD.
- An MCU flash / MCU reset does **not** change the Linux `boot_id` and does **not** reboot Linux —
  the "`boot_id` changed → stop" tripwire is a Linux-reboot detector and a flash won't trip it.
  `arduino-flash` alone does not restart the container; `arduino-app-cli app restart` **does**.

Full procedure + toolchain facts + risk profile written up in the new
**`docs/runbooks/mcu-flash-uno-q.md`** — read that before any future flash instead of re-deriving.

### Corrected firmware-state understanding — the MCU is very probably ALREADY on schema 3

Board `/home/arduino/ArduinoApps/eletect-x/sketch/` was pulled and `diff`ed against the local
working tree (`device/mcu/src/`): **`config.h`, `led.cpp`, `bridge_handlers.cpp` are byte-identical**
— `BRIDGE_SCHEMA_VERSION 3`, `LED_WING_LEFT_PIN 3` / `LED_WING_RIGHT_PIN 6`, ADR 0014 pattern
constants, `FIRE_TEST_HARNESS 0`. The production binary `.cache/sketch/sketch.ino.elf-zsk.bin`
(109 280 B) and the container restart both date to **1 Sept 17:31**; board + container MPU both
report `SCHEMA_VERSION = 3`. So the current tree was almost certainly flashed as part of that
17:31 `app restart`. **The "schema v3 has never run on hardware / must be flashed after the power
rewire" framing in the checkpoints below is likely stale.** Not yet 100 % confirmed — needs the
supervised morning checks (serial banner, right-wing D6 drive, `SAFE_MODE=0` handshake); see
`KNOWN_GAPS.md` and the runbook's "Current firmware state" section.

### Night camera/IR characterisation battery — ran to completion

The sanctioned `night_char.py`-based battery (`/home/arduino/vdiff/night_battery.sh` +
`night_battery2.sh`, all within firmware limits: IR 500 ms / ≥5 s, no LED beyond the tiny budget,
`guard()` aborts on `boot_id` change / container `RestartCount≠0` / temp >62 °C) ran overnight:
Phase 1 (baseline, exposure ladder e32–e256 no-IR, auto-exposure IR sweep, locked-exposure IR
ladder e64–e384, 16-cycle pulse-landing) then Phase 2 (exposure ladder e320–e512 no-IR, IR clip
sweeps e448/e512, 24-cycle pulse-landing), then it relaunched `night_char.py soak --interval 120
--max-min 600` → **`/home/arduino/vdiff/soak_dawn.log`** for the dawn transition. Log:
`/home/arduino/vdiff/night_battery.log`.

**Battery: DONE and analysed.** `night_battery.log` (482 lines) is written up as **Finding 4** in
`docs/qa/night-ir-led-characterisation.md` — headline: **lock night exposure at ≈ 256 and keep the
500 ms IR pulse.** That maximises the pulse's treeline sharpness gain (+100 Laplacian, ~1.3–2.5×
the gain at other exposures), never clips (saturation 0.000 even at exp 512), keeps a usable
no-pulse baseline, and produced zero false positives. **Auto-exposure at night is harmful** — it
cuts the IR luma benefit to +5–7 % and is the sole source of spurious Boar boxes (`maxconf` to
0.408). Acting on this needs a night locked-exposure path in camera control (firmware/MPU) — new
open item. Board held `boot_id` + `RestartCount=0` + 39–44 °C flat across the ~1 h battery
(~2½ h continuous camera load total with no crash — a small positive on the SoM-reliability
question).

**Dawn soak: DONE and analysed** (`soak_dawn.log`, 184 samples, appended to the QA doc Appendix as
"Dawn transition — captured"). Headlines:

- **ADR 0019 night gate validated on real sky.** `sat` held flat `0.0` all night, then crossed
  `NIGHT_SATURATION_THRESHOLD = 12.0` at ≈ 06:15 IST — within minutes of local sunrise. `luma`
  barely moved (132 → 151) over the same span, confirming saturation (IR-cut filter re-engaging),
  not brightness, is the right night discriminator. Threshold sits on the knee with a whole night
  of headroom; no tuning needed.
- **Dawn AGC throws low-confidence `Boar` false positives.** Zero FPs for the whole night and first
  light (samples 0–144); then 26 samples (≈ 07:12–08:29 IST) each with a `Boar` box, `v` =
  0.074–0.223 (median ≈ 0.11), never `Elephant`, all on one fixed treeline feature, all with
  `EXPOSURE readback = 512` (AGC pinned at ceiling). Same failure mode Finding 4 isolates — argues
  for carrying the Finding 4 night locked-exposure across the dawn ramp, not snapping back to AGC
  at the `sat` crossover. All 26 are far below the 0.4 fusion threshold, so nothing would fire.
- **Board temperature flat** 40.0–42.8 °C across the ~4 h run, no daylight climb (bench rig,
  indoors — not a solar figure).

**Board rebooted spontaneously at ≈ 08:27 IST 2 Sept** — 64 s downtime (`journalctl --list-boots`:
boot `6b2c727a-…` ended 02:57:20 UTC, `2c601696-8ce6-463d-917b-6da275008c34` began 02:58:24 UTC),
full daylight so **not** thermal/dawn-linked, no shutdown or panic record → unclean drop consistent
with the Portronics-hub power-starvation fault. **Recovery was fully automatic**: Linux + Docker
bridge + container `eletect-x-main-1` (RC=0) all back in ~1 min — a genuine positive for unattended
field survivability. The `night_char.py soak` foreground process did not resume (not a service).
`--list-boots` still shows 3 further reboots on 1 Sept; the `6b2c727a` run that just ended (~10 h)
was the longest clean stretch in the list. Root cause (hub power path) unfixed, physical.

**Per the standing rule the `boot_id` change ends hardware work for the session** — everything since
is analysis of data already on disk. Live `boot_id` is now `2c601696-8ce6-463d-917b-6da275008c34`
(per-boot by nature; only a "did Linux reboot" tripwire).

**Still TODO:**

1. Daylight exposure ladder — the "day" half of "best footage night and day" still needs a
   daytime run. The dawn soak only caught the earliest AGC ramp before the reboot, not a settled
   mid-morning frame.
2. Re-launch a passive logger **as a restart-on-failure unit** (not a bare foreground process) if
   more unattended soak data is wanted — this reboot cost the tail of the run.

### Doc corrections made this session

- **`docs/qa/night-ir-led-characterisation.md`** — fixed a wrong `boot_id` (line 8 had
  `6b2c727a-a0fa-4819-...`, an old monitor-bug splice of stray identifier text) → canonical
  `6b2c727a-af0d-4517-a6c7-a8069da92a64`. Folded in three user corrections: the IR board's onboard
  CdS photocell is **not** in the control path (only the illuminator power pins are used, switched
  by the pin-7 MOSFET; one night gate = `perception/night.py` per ADR 0019) — resolved, not an open
  item; LED wings are wired **in parallel, not series** (so the field checklist item is a
  shorted-emitter / broken-common-lead check, not a series-dark-fail check); bench rig is PETG-HS
  but the field enclosure is ABS/ASA with more thermal headroom, so the thermal findings are a
  conservative bound.
- **`docs/runbooks/mcu-flash-uno-q.md`** — new file (new `docs/runbooks/` dir).
- **`docs/KNOWN_GAPS.md`** — the stale "reflash from clean tree required before field, should be
  that session's FIRST action" entry revised to reflect the byte-identical tree + likely-already-
  flashed state + the three supervised checks that remain; runbook pointer added.

### Morning supervised checklist — 2 of 3 DONE 2 Sept ≈ 11:10 IST

1. **OPEN** — `arduino-app-cli monitor user:eletect-x` → confirm the MCU boot banner reports schema
   3. (Serial attach DTR-resets the MCU.) Effectively a formality now: byte-identical tree + 1 Sept
   17:31 binary + MPU schema 3 + a clean schema-3 `drive_led` round-trip (step 2) with no mismatch
   warning in the container logs. Not yet done because a DTR reset is a hardware perturbation and
   the `boot_id`-change rule was in force.
2. **PASS** — with the user watching, two per-wing `drive_led` calls via `fire_client.py`
   (`[3,0,0,25.0,1000]` then `[3,1,0,25.0,1000]` — schema 3, channel, steady, 25 %, 1 s):
   **channel 0 → left wing only, channel 1 → right wing only, each off cleanly after ~1 s, no
   latch-on**, both acked `[1,1,null,true]`. D6 right-wing drive + channel mapping now verified on
   hardware (was the one unverified actuator). The harness's safety classifier blocked the fire
   from this session — the user ran the two SSH commands.
3. **PASS (subsumed)** — `fire_client.py` talks straight to `/run/arduino-router.sock`, so
   `SAFE_MODE` is not in that path; step 2's clean round-trip on the post-reboot boot is the bridge
   handshake check. A separate `ELETECT_SAFE_MODE=0` app-path check is only needed if the *main app*
   deterrence chain (perception → fusion → deterrence) is to be exercised, which is not on the
   critical path right now.

### Platform documentation research — 2 Sept (this session) — `docs/research/platform/`

Went wide through the Arduino UNO Q docs, Edge Impulse docs (Studio + Linux SDK), the
`edgeimpulse/agent-tools` App Lab skill, and the Arduino / Edge Impulse forums + GitHub issues, to
stop re-deriving platform facts and to pin down real fixes for the recurring blockers. Five source
files + an index, all linked to primary sources, all uncommitted:
`docs/research/platform/README.md` (index + consolidated fixes-by-problem),
`arduino-uno-q-power-and-ops.md`, `uno-q-forum-findings.md`, `app-lab-flash-and-routerbridge.md`,
`edge-impulse-linux-inference.md`, `edge-impulse-studio-vision-tuning.md`.

**Power / reboot fault — concrete fix path (physical, user-present, still pending):**

- The reboots are a **5 V rail brown-out**, corroborated from Arduino's own power spec, forum
  moderators, and Tom's Hardware current measurements: the board needs ~0.66 A idle / ~0.9 A
  all-cores *before* camera + USB-Ethernet + actuators, and a passive hub fed by a
  non-PD-negotiated charger cannot hold 5 V through transients. Caps on 5 V do not fix it.
- **Best fix is to power the board via the VIN pin (7–24 V) from a regulated DC supply** — through
  the on-board LMR51440 buck onto 5V_SYS, bypassing USB-C PD and the sagging hub rail entirely.
  Caveats: VIN **disables the USB-C VBUS output**, so the camera + USB-Ethernet then need their
  own self-powered hub; pre-Nov-2025 images (`cat /etc/buildinfo` absent) also need a systemd unit
  forcing USB `host` mode. If staying on USB-C: a genuine 5 V/3 A (15 W+) charger straight into the
  board's port, **no hub between charger and board**, peripherals on a separately-powered hub.
- **Correction to the earlier framing in this file:** `power_operation_mode: default` / no
  `port0-partner` is a hub CC-pin quirk, **not** a hard 500 mA cap. PD is not required on this
  board to exceed 500 mA — it draws more and runs for hours; the hub just can't hold the rail
  under load. So "locked at 5 V / 500 mA" overstates it — it is rail sag under transient.
- **Second plausible cause, do this too:** Linux-side memory pressure on the 1.7 GB board.
  Arduino's "board software out of date" article says the current image adds ZRAM *because*
  "random restarts … are typically caused by memory pressure." Flash the latest Linux image,
  confirm `zramctl`, cap the Python/EIM footprint.
- **Decisive test:** switch to VIN (or direct 5 V/3 A, no hub), watch MTBF; around each crash
  `journalctl -k -b -1 | tail -200`, `last -x`, and cron-log `voltage_now` +
  `power_operation_mode` every 5 s.
- **Survivability:** no documented Linux hardware watchdog — use Monit for app auto-restart +
  alerts; enable the STM32 IWDG in reflex firmware; any passive field logger must be a
  `Restart=on-failure` systemd unit (a bare foreground process does not survive a reboot, as the
  dawn soak proved); force NTP sync at boot before timestamped logging (RTC is on the unbacked
  `VCOIN` rail — the clock jump is extra evidence of a deep brown-out, not a clean panic).

**GPU delegate — settled, permanent:** no supported GPU/NPU/DSP acceleration on QRB2210. No NPU in
silicon; the GPU `.eim` needs `libtensorflowlite_gpu_delegate.so` (never shipped) *and* proprietary
Adreno OpenCL (image is Vulkan-only Mesa Turnip). The missing-`.so` line is a **silent CPU
fallback, not a hard failure**. CPU int8 + NEON + XNNPACK + EON is the ceiling; ~138 ms/frame is
normal. Cut latency by model shape, not hardware.

**Camera exposure lock:** no runner flag exists; the supported way (and it matches our V4L2 side
harness) is for our app to own the camera — V4L2 `/dev/video2`, `auto_exposure=1`,
`exposure_time_absolute ≈ 256`, fixed gain — and feed frames to the model via
`runner.get_features_from_image()` + `.classify()` or `edgeimpulsevideoinfer`.

**Vision recall bar:** the silent-miss gap is a data/label problem. Re-scan existing training
images with AI labeling for unlabelled animals (teaches suppression), stay on YOLO-Pro one size
up, class-weight toward Boar, keep threshold 0.05 and recover precision with the object-tracking
post-processing block. EON Tuner likely can't beat the champion because YOLO-Pro may not be a
valid search-space model id. Full detail in `edge-impulse-studio-vision-tuning.md`.

**App Lab / flash corrections:** `arduino-app-cli app start`/`restart` is the whole deploy (no
separate flash verb); do NOT pin `Arduino_RouterBridge` in `sketch.yaml` on core ≥ 0.55; MCU
recovery uses the `jlink` bootloader burn via `system update` (no USB-DFU); never call
`Bridge.call()`/`Monitor.print()` inside a `provide()` callback. See
`app-lab-flash-and-routerbridge.md` "Corrections to our current understanding".

### Constraints honoured (unchanged from the checkpoint below)

No git commit. No horn hardware work. No reflash / no power rewire (a safe path now exists and the
user pre-authorised a *supervised* reflash, but the "stay reachable 30 min" precondition is unmet
while asleep, and `app restart` would kill the running battery mid-run). `docs/decisions/0017-*.md`
untouched. Behavioural-science doc §3.1 untouched (append only). No AI-assistance references
anywhere. Raw `docker exec … < fire_client.py` fires stay classifier-blocked; `night_char.py` is
the permitted path. A `boot_id` change → stop all hardware work, finish on writing only.

## RESUME HERE — 2 Sept (overnight) — night-IR characterisation doc + ADR 0019 + Item C proposal + activity-timing research + behavioural-synthesis append; overnight soak running on the board

Autonomous overnight documentation session (user asleep, explicit "run a test till morning and see
how it performs in daylight and the night→day shift" + a batch of writing deliverables). **No code
changed this session** — Item B (external-IR night gating) code was already implemented and green
at the end of the 1 Sept evening session (255 pytest passed); everything below is docs, plus one
long-running board test. **Nothing committed to git.** Board health held throughout: `boot_id`
`6b2c727a-af0d-4517-a6c7-a8069da92a64` unchanged at every check, container `eletect-x-main-1`
`RestartCount=0` / running, thermal steady ~41–42 °C, frame saturation 0.0 (confirms night),
0 vision boxes.

### Overnight soak — RUNNING on the board, independent of any SSH session

- Launched detached on the board: `setsid nohup python3 /home/arduino/vdiff/night_char.py soak
  --interval 120 --max-min 480` (8 h run, sample every ~2 min).
- Output dir: `/home/arduino/vdiff/nightchar/soak_20260901_185050/` — `soak.jsonl` (one line per
  sample: per-band photometrics, vision box count, `tele` block with temp + boot_id + container
  state).
- **Board wall-clock runs ~4 h 40 m behind real IST** (known dead-RTC / clock-jump smell — see the
  SoM-fault checkpoints below). Soak dir/timestamps say "18:50 / 1 Sept"; real start was ~23:51 IST
  1 Sept. Run ends at board-time ~02:50 → **real IST ~07:40 2 Sept**.
- It is **not** tied to the SSH session — it survives disconnects. Poll it with short
  commands only (long ssh commands hit exit 255 on this link).

### Still TODO when the soak finishes (~07:40 IST 2 Sept)

Parse `soak.jsonl` and append results to the **"Appendix — overnight soak"** section of
`docs/qa/night-ir-led-characterisation.md` (currently a placeholder). Extract:

1. Night→day saturation crossover — wall-clock sample where `sat` rises off 0.0 and crosses
   `NIGHT_SATURATION_THRESHOLD = 12.0`; validate the threshold against the real transition.
2. Thermal trace across the whole night (min/max/mean `temp_max_c`), any climb.
3. Night false-positive count — any sample with `vision.n > 0` (bench has no animals → all are FPs).
4. Any `boot_id` change or container `RestartCount` increment (crash-reboot check — the open
   SoM-reliability question; a clean 8 h idle-plus-camera-load run is a data point toward trust).
5. Daylight photometrics once transitioned (luma/sharp/clip_hi per band) vs the night baseline.

### Documents written this session (all uncommitted, staged-ready)

- **`docs/qa/night-ir-led-characterisation.md`** — Item D findings doc. Establishes a `docs/qa/`
  text-doc convention. Writes up the external-IR night characterisation already captured on the
  board: IR sweep at exp=100 and exp=156 (full-frame luma +24.6/+29.1, treeline Laplacian sharpness
  +53.7/+91.2, no clipping, 0 animals in any frame); the LED-vs-camera interference table (all four
  night patterns: luma delta −0.28…−0.72 vs within-burst sd 0.35–0.49, `clip_hi` exactly 0.000 →
  our own strobe does **not** blind our own night camera, so detection and deterrence can overlap);
  baselines; method notes (exposure must be locked or AGC hides the IR delta; capture window must
  be ≫ the 500 ms pulse because `docker exec` cold-starts 1–3 s). Honest caveats: all measured with
  exposure locked while the deployed pipeline runs AGC; scene was empty so the detection benefit vs
  image-quality benefit is unmeasured; LED aim vs camera FOV still unverified (a perfectly flat
  interference result also means the wings may not be lighting the camera scene at all). Appendix
  reserved for the soak results (above).

- **`docs/decisions/0019-external-ir-illuminator-night-gating.md`** — ADR 0019, status **proposed**,
  dated 2026-09-02. Documents the already-implemented Item B change: external IR illuminator fires
  on a frame-derived night signal, not on the deterrence tier. Covers the new
  `device/mpu/perception/night.py` (`frame_mean_saturation`, `frames_are_night`),
  `NIGHT_SATURATION_THRESHOLD = 12.0` in `services/config.py` (separation-based, sits in the
  empirical gap between night sat 0.0 and daylight sat >30 — not tuned), the `reflex_loop.py`
  `NightDecideFn` Protocol + `is_night` required kwarg + `fire_ir_now` gate (True→fire,
  False/None→suppress+log, exception inside `is_night`→fire anyway), the `main.py` wiring, and the
  tests (`test_night.py` 12 cases + `test_reflex_loop.py` 5 new cases). Pulse drive/duration
  deliberately NOT changed here — that is the still-open auto-exposure tuning question. Alternatives
  considered (wall-clock, photocell, exposure readback, `fire_ir=False` everywhere, gate inside
  `decide()`) all listed with rejection reasons.

- **`docs/research/elephant-activity-timing-and-raid-patterns.md`** — Research F1 ("at what times
  do elephants come"). Diel: crop-raiding is overwhelmingly nocturnal 22:00–06:00 (PeerJ 2020 /
  PMC7335499, N=380, North Bengal, risk-avoidance strategy; ~89/11 night/afternoon split treated as
  "one landscape, indicative"); movement peaks are crepuscular (dusk arrival ~17:00–20:00, dawn
  departure ~06:00–08:00); raid duration mean 308 min (~5 h), range 15 min–15 h. Seasonal: North
  Bengal peaks monsoon+post-monsoon; **Wayanad/Western Ghats (ATREE 2023) is the better local prior
  — May–Sep fruit (jackfruit/mango) then Sep–Dec paddy, driven by crop phenology + forest-boundary
  proximity**; honest bound — no Kothamangalam-specific dataset exists, the device's own log will be
  the first. Consequences: device fully alive 20:00–07:00 nightly in season, look for power savings
  in daylight only, reinforces ADR 0019; encounter model = dusk arrival burst → hours of sparse
  feeding-lull triggers (NOT a departure) → dawn departure burst (corroborates ADR 0017 window
  lengthening); nothing changes actuator design.

- **`docs/research/elephant-deterrence-behavioral-science.md`** — Research F2, **appended §7 + §8
  only, all prior content including §3.1 preserved untouched** (single Edit anchored on the last
  existing bullet). §7 "Behavioural, psychological and biological synthesis": large-brained
  individual learner with multi-year spatial memory (so consequence-free deterrents decay); the
  animal at a 2 a.m. fence is very probably a lone male (risk/reward asymmetry, musth) → effect
  priors + web-app alert framing + per-individual bandit learning; habituation mechanism —
  *predictability* not familiarity is the enemy, weak stimulus habituates / strong sensitizes
  (supports max-intensity-every-tier), dishabituation is real and exploitable; three outcomes
  flight/curiosity/tolerance + "leave the animal a way out"; stress physiology + welfare bound
  (redirect not terrorise, no auto tier 4); why the current architecture is right + its one real
  weakness (proxy reward has no presence/departure signal); a 10-row concrete-adjustments table
  cross-referenced to ADRs/files; a one-paragraph DFO/contest framing. §8 adds the sources.

- **`docs/proposals/led-horn-fire-duration-burst-cooldown-and-cadence.md`** — Item C proposal
  (new `docs/proposals/` dir). Status: proposal, needs a bench pass before any constant changes.
  Owns no code; the eventual decision lands as an ADR 0014 amendment (burst shape) + companion
  values alongside ADR 0017 (cadence). **Explicitly does not modify ADR 0017 or ADR 0014.** Joins
  the ADR 0014 §E.3 deferral + ADR 0017 open Question B + the 1 Sept KNOWN_GAPS quantification (LED
  runs a full 10 s per fire, blocking the MCU loop). Case for cutting `LED_BURST_MAX_MS` 10000 →
  2000–3000 on four grounds (habituation, MCU real-time starvation, thermal, battery); horn 3 s
  already short; cooldowns → encounter-aware cadence (MCU hard floor lowered + kept as a safety
  floor, MPU adaptive interval keyed to the bandit `habituation_context()` bucket). Full bench
  thermal/battery-sag protocol (T1 single-burst step response, T2 60–90 min sustained-encounter
  sim, T3 battery sag vs ADR 0012 10-day autonomy, T4 cadence vs MCU real-time) with pass/fail
  criteria. Out of scope: proactive timer re-firing, non-blocking actuator state machine, horn
  content, any change tonight.

- **`OVERNIGHT_RESUME.md`** (repo root) — scratch continuity file for a fresh session if this one
  hit a limit. Delete once this batch is closed and the soak is analysed.

### Constraints honoured (standing, for whoever picks this up)

No git commit (not asked). No horn hardware work (horn not wired). No reflash, no power rewire.
`docs/decisions/0017-*.md` untouched. Behavioural-science doc §3.1 untouched (append only). No
AI-assistance references anywhere. Raw `docker exec … < fire_client.py` actuator fires stay blocked
by the classifier; the purpose-built `night_char.py` harness is the permitted path. A `boot_id`
change → stop all hardware work and finish on writing only.

## RESUME HERE — 1 Sept (evening) — ADR 0014 item A reflashed + hardware-verified (max-gain LED every tier, 11 Hz top-tier strobe); camera day/night solved; ADR 0014 §E.3 written checkpoint

Follow-on to the "§E dual-wing host implementation" checkpoint just below. This session took three
design decisions the user made about the LED deterrent, cut them to the one that was self-contained
(**item A**), implemented + reflashed + hardware-verified it, and characterised the actual camera.

### Item A — LED fires at max intensity on every tier; escalation moved onto pattern / wings / rate

User's field call, stated repeatedly: **there is no field use for a dimmed deterrence flash** — a
partially-lit strobe just reads as a weaker light, not "less threatening, saving headroom." So the
brightness axis is retired as an escalation lever.

- **`device/mpu/cognition/config.py`:** `LED_TIER_1_GAIN_FRACTION` and `LED_TIER_2_GAIN_FRACTION`
  → `1.0` (T3 already was). All three tiers now resolve `led_gain_pct = 100.0` — no change to the
  `DETERRENCE_TIERS` literal, the fractions feed it. Comment blocks rewritten.
- **`device/mcu/src/config.h`:** new `#define LED_STROBE_FAST_HZ 11` — the top-tier escalation
  strobe rate. `LED_FAST_STROBE_HZ 7` unchanged (Tiers 1-2 + `PATTERN_SWEEP` keep it).
- **`device/mcu/src/led.cpp`:** `pattern_pulse_both_sync` (pattern_id 5, a Tier 3 pattern) now
  strobes at `LED_STROBE_FAST_HZ`; `pattern_sweep` still at `LED_FAST_STROBE_HZ`. Block comments
  rewritten to E.3.
- **What now carries tier escalation:** wing count (T1 one wing → T2/T3 both) + pattern character
  (strobe → antiphase sweep → sync/independent) + strobe rate at the top rung only (7 → 11 Hz).
  Not brightness. The bandit's `escalation_floor()` still reserves the dual-wing patterns for
  repeat animals, so E.2's anti-habituation logic is intact — only the (never-strong) brightness
  lever changed.
- **Horn deliberately NOT changed to match:** `HORN_TIER_1/2/3_GAIN_FRACTION` stay 0.25 / 0.45 /
  1.0 because `HORN_GAIN_MAX_PCT` is a hearing-safety cap for people/livestock near the unit
  (ADR 0016) — a real physical-harm limit the LED does not have.
- **Tests, all green:** `pio test -e native` **64/64** (was 63; new
  `test_pulse_both_sync_runs_at_the_top_tier_escalation_rate` in `tests/test_led` asserts
  pattern 5 strobes at ~11 Hz, distinct from the 7 Hz rate). `pio run -e native` clean, `ruff`
  clean, `pytest` **238 passed** (two graded-gain tests in `test_cognition_config.py` replaced
  with "every tier requests exactly `LED_GAIN_MAX_PCT`").
- **ADR:** `docs/decisions/0014-led-deterrence-pattern-and-intensity.md` **§E.3 amendment** added
  (max intensity every tier, escalate on wings/pattern/rate, `LED_STROBE_FAST_HZ = 11` rationale
  plus honest bound — no citation ranks 11 over 7 Hz, only the 4-12 Hz aversive band and the
  ~15 Hz fusion ceiling; horn keeps its ramp; IR reclassified vision-only; duration → ADR 0017).
  Two Consequences bullets added.

### Reflash + supervised hardware verification — DONE, boot_id held throughout

- Sync (`device/mcu/src/` → `sketch/`, Python source dirs → `python/`, no `rm -rf`, so the `.eim`
  models and the real `secrets.h` are preserved) + `arduino-app-cli app restart user:eletect-x`
  → **rc=0, 1m49s**,
  sketch 13 % flash / 17 % RAM, STM32U585 flashed via OpenOCD SWD.
- **`boot_id` = `6b2c727a-af0d-4517-a6c7-a8069da92a64` — held before AND after the flash** (the
  heaviest CPU load in the exercise), and across both supervised LED fires. Same boot_id as the
  end of the prior session. Container `RestartCount=0`.
- **2× supervised fires** of `drive_led(sv=3, channel=2, pattern_id=5, gain_pct=100.0,
  duration_ms=4000)` (both wings, pattern 5, 100 %, ~11 Hz, `timeout=20`): both returned `True`,
  both blocked **4.023 s** for the 4000 ms request (dual-wing single-window confirmed again — D,
  not 2D), boot_id unchanged, thermal 38-40 °C flat. **User visually confirmed:** both wings in
  phase, full brightness, the ~11 Hz rate reads as clearly faster / harsher than the 7 Hz sweep
  from the earlier bring-up. Item A is verified on hardware.
- Manual `docker exec` `Bridge.call` needs `timeout=20` for a >10 s-blocking fire; the live
  reflex loop is unaffected (it uses the per-actuator `BRIDGE_LED_CALL_TIMEOUT_S` override).

### Camera characterised — it is an Arducam B0CQ4QDCXN (IMX462, auto IR-cut, onboard 940nm IR LEDs)

Confirmed from the product page + the repo's own `CAMERA_DEVICE` by-id string: **Arducam 1080P
Day & Night USB2.0, 2MP Sony IMX462 (STARVIS, strong NIR), automatic IR-cut switching triggered by
an onboard CDS light sensor, 3× built-in 940 nm IR LEDs.** Runs all-day autonomously; the host has
no control over the day/night switch.

- **Night frame measured** (board pointed out the window at the backyard, genuinely dark):
  mean luma **116** (well-exposed, NOT dark), mean HSV saturation **0.00**, R = G = B on every
  pixel. The camera has **already auto-switched to night mode** — IR-cut filter pulled, onboard
  IR LEDs on, output forced to grayscale — and the scene is properly lit on the onboard LEDs alone.
- **Day/night detection is SOLVED with zero new hardware:** the frame itself is the signal —
  `is_night = mean_saturation < ~2` (this unit reads a literal 0.00 at night; > 0 with real colour
  by day). Free — a warmup frame is already grabbed every capture. Astronomical dusk/dawn schedule
  is now only an optional sanity backstop, not needed for correctness.
- **V4L2 exposure/gain readback is DEAD on this unit** — re-probed day and night,
  `exposure_time_absolute` frozen at 156, `gain` at 0, byte-identical both times. The camera does
  not expose its AE state or day/night switch over UVC. (Corrects an earlier suggestion in this
  session to use that method.)
- **Implication for the project's external `IR_ILLUMINATOR_PIN` (940 nm) illuminator:** it is now
  understood as a **range extender only** — the camera self-illuminates the near field; the
  external unit is for the deterrence-zone distance. At night the vision model gets grayscale
  (R=G=B) frames — confirm the `.eim` behaves on that (a 3-channel array, should be fine).

### Deferred / follow-ups (NOT done this session)

- **Item B — decouple IR from the deterrence tiers:** move the IR firing path out of
  `DeterrenceAction`/tier into the camera-capture path, gate it on `is_night` (frame saturation),
  always fire at the best-for-vision config. Needs its own ADR + item D's result. `fire_ir`
  per-tier values (T1 False / T2 True / T3 True) left as-is for now — a half-migration that set
  them all false without the new path would leave night captures unlit. `test_reflex_loop.py` +
  `test_cognition_config.py::test_only_the_lowest_tier_withholds_ir` get rewritten at that time.
- **Item C — LED/horn active fire-duration per detection:** how long each should run to maximise
  the chance of blocking an approach. Separate written proposal; ADR 0017 already covers the
  relevant part (retune `HABITUATION_WINDOW_S` / `PROXY_REWARD_HORIZON_S`; do NOT build blind
  timer re-firing). Longer ≠ better — habituation, battery/thermal, horn hearing-safety near homes.
- **Item D — external IR illuminator night characterisation:** rig is already pointed at the
  backyard. Vary IR drive/pulse config, capture footage, evaluate which config gives the best
  detection-quality frames for the elephant/boar model at range, on top of what the onboard LEDs
  already provide. Needs a written test protocol. Feeds item B.
- **Power rewire (Mport 51 hub out of the power path) + 10-day idle soak:** STILL deferred. The
  hub is still in the path (`power_operation_mode: default`). It held clean through this ~1 h
  supervised session (uptime unbroken, boot_id held through the flash + 2 fires) but that does
  **not** clear the 10-day unattended-trial gate.
- Nothing committed to git this session. `docs/decisions/0017-*.md` and the §3.1 addition to
  `docs/research/elephant-deterrence-behavioral-science.md` are net-new from a parallel track —
  left untouched.

### DFO-facing language constraint (unchanged, restated)

Do not claim the LED deterrent "keeps elephants out" or any absolute exclusion language. Every real
number is a probability of deterring a given approach, not a guarantee. Describe it as: real,
evidence- and practitioner-informed dual-wing strobe deterrence with genuine per-tier escalation,
verified working on hardware — not a promise elephants won't enter.

## RESUME HERE — 1 Sept, POWER-DELIVERY ROOT CAUSE FOUND (idle crash-reboots = Portronics Mport 51 hub in the power path) + ADR 0014 §E dual-wing LED implemented host-side (all green, NOT reflashed) checkpoint

### Power-delivery root cause — the recurring idle crash-reboot fault is diagnosed

Read-only SSH forensics (board on WiFi, no reflash, no actuator fired) traced the fault the prior
checkpoint left "UNRESOLVED".

**What it is NOT** (all ruled out by direct evidence):
- Kernel panic / oops — journal stops mid-stream at every crash, no panic/oops/trace.
- SoC watchdog reset — `qcom_wdt` state `inactive`, `bootstatus=0`, `CARDRESET` boot-status `0`.
- Thermal — all 11 zones 37–43 °C throughout; no thermal-trip messages.
- OOM — 3 GB `MemAvailable`, no oom-killer.
- Periodic software trigger — crash intervals span **2 s to 13 h**; no cron/timer correlates.
- Subsystem/remoteproc crash — no EDAC/MCE/rproc errors.
- "Started 28/30 Aug" — **false.** `wtmpdb` shows the same `- crash` on **every boot since the
  board's first-ever record, 28 May 2026**. (The `- crash` label itself is a red herring: this
  image never records clean shutdowns, so literally every boot shows it. The real signal is the
  spontaneous idle reboots + the power-up retry bursts.)

**What it IS — power delivery, via the hub:**
- The board is powered **through a Portronics Mport 51** 5-in-1 bus-powered USB-C dock
  (RJ45 + HDMI + 2×USB-A + a "PD passthrough" USB-C port). The user's 45 W Robu Pro-Range PD
  charger + its 80 cm C-to-C cable feed the dock; the camera and the dock's RTL8152 USB-Ethernet
  hang off the dock; a single USB-C tether goes to the UNO Q's **only** USB-C port.
- On the board: `/sys/class/typec/port0` → `power_role: [sink]` ✓ but
  `power_operation_mode: default` and **`port0-partner` does not exist** — the PMIC Type-C
  controller (`pm4125_typec`, I²C TCPC at `1-0058`) **sees nothing on the CC pins.** VBUS 5 V is
  present (board runs) but CC is electrically absent, so the board can never advertise for more
  than the USB-default floor: **5 V / 500 mA.** The Mport 51's PD passthrough is built to charge a
  laptop-style host (a PD *sink*); the UNO Q is the USB *host* here, so the dock never presents a
  proper Type-C source contract up the tether.
- That 5 V / 0.5 A budget is shared by the SoM + WiFi + the dock's Ethernet + the USB camera
  (`bMaxPower 500 mA`). Every camera-frame burst / WiFi TX / (and any actuator fire) is a load
  transient the rail can't hold → brownout → reboot.
- Boot history confirms the electrical signature: power-up **retry bursts of 4–7 reboots within
  3–20 s** (30 Jul ×3 in 6 s, 31 Jul ×7 in 17 s, 12 Aug ×4 in 8 s, 28 May ×3). Software cannot
  reboot a machine that fast; only a sagging supply can.
- Fits the prior "power cycle helped for ~4 h then it crashed again (10:13→14:17 on 1 Sept)"
  observation — reseating the USB-C connector momentarily improved a marginal contact.

**Fix (physical, user present, DEFERRED per user's sequencing — do the LED/camera/horn work first):**
1. Remove the Mport 51 from the power path. 45 W PD charger → its C-to-C cable → **straight into
   the UNO Q's USB-C port**, nothing else on that connector, wall socket.
2. Re-read `/sys/class/typec/port0`: success = `power_operation_mode` → `usb_pd` or `3.0`, and a
   `port0-partner` dir with a PDO list appears.
3. Leave it idle, watch `boot_id` for several hours (it used to crash every few) → if it holds,
   root cause is nailed and it is NOT an RMA.
4. If it **still** shows `default` / no `port0-partner` plugged straight into the charger → the
   board's USB-C CC pins or the cable are bad → swap to a known-good e-marked C-to-C cable →
   RMA the board if a good cable doesn't restore negotiation.
5. Trial rig implication: single USB-C port + a camera means the camera must run off a
   **separately powered** hub (its own wall wart, zero draw from the board), or a proper powered
   USB-C dock with real PD-IN passthrough that is *verified on the board* to negotiate. A cheap
   bus-powered dock in the power path cannot go to a 10-day unattended trial.

### ADR 0014 §E — real dual-wing LED — implemented host-side this session (NOT on the board)

Host-only build call (schema bump + firmware + MPU + tests), per the ADR's §E / §E.1 / §E.2.
15 files touched, uncommitted. Summary:
- **Schema `2 → 3`:** `device/mcu/src/config.h` `BRIDGE_SCHEMA_VERSION`, `device/mpu/services/
  config.py` `SCHEMA_VERSION`, `bridge/schema.md` header + version history, `bridge/rpc.py`
  docstrings. `channel` wire value **2 now means "both wings"** (was "unrecognized → left"); this
  repurpose is the breaking change the bump records. `pattern_id` gains `4 = sweep`,
  `5 = pulse-both-sync`, `6 = flicker-both-independent`. No wire field added/removed.
- **`device/mcu/src/led.{h,cpp}`:** `led_channel::kWingBoth` (=2); patterns `kSweep=4`,
  `kPulseBothSync=5`, `kFlickerBothIndependent=6`. New `flash_pair()` dual-wing primitive (set
  both pins, then ONE `delay`), `pattern_sweep` (antiphase, break-before-make so the two wings are
  never lit together), `pattern_pulse_both_sync` (in phase), `pattern_flicker_both_independent`
  (two independent xorshift32 streams, seeds deliberately differentiated as `micros()` doesn't
  advance within a host call). `run_pattern_dual()` + `drive_led_both()`: gates BOTH wings against
  `g_wing_left` / `g_wing_right`, refuses the whole fire if EITHER wing is still in cooldown, uses
  the left wing's gate result for the ack (both resolve identically when allowed), updates both
  channel states, and runs the pattern in **one blocking window** — a dual-wing fire of duration D
  blocks for ~D, not ~2D (verified by test). All three new patterns anchored on
  `LED_FAST_STROBE_HZ` (7 Hz).
- **`device/mcu/src/bridge_handlers.{h,cpp}`:** `led_channel_from_wire(2) → kWingBoth`;
  unrecognized (3, 255) still → `kWingLeft`.
- **`device/mpu/cognition/config.py` `DETERRENCE_TIERS`** reallocated per §E.2: **T1** = single
  wing (ch 0) + `PATTERN_FAST_STROBE` (id 2) + 50 % gain (was slow-pulse); **T2** = `PATTERN_SWEEP`
  (id 4) + both wings (ch 2) + 75 %; **T3** = both wings (ch 2) + 100 % gain + **rotating** between
  id 5 and id 6 via new `resolve_tier_action(tier, rng)` (reuses the bandit's injected `rng`;
  returns the exact `DETERRENCE_TIERS` object unchanged for T1/T2, so identity-based tests barely
  move). `TIER_3_LED_PATTERN_IDS = (5, 6)`. `reflex_loop.py` call site switched to
  `resolve_tier_action`. `bench/demo_replay.py` labels extended.
- **Tests:** `tests/test_led/` (new dir this session) gains dual-wing timing cases — sweep
  antiphase at strobe rate, pulse-both-sync in-phase, flicker not mirrored, blocks-for-D-not-2D,
  dual-fire puts both wings in cooldown, dual fire refused whole when one wing still cooling.
  `test_bridge_handlers` channel-2 case. `test_cognition_config.py` widened allowlists (patterns
  0–6, channels 0–2) + T2/T3 dual-wing + `resolve_tier_action` rotation tests.
  `test_reflex_loop.py` two identity→`.tier` assertion adjustments.
- **Verification, all green:** `pio test -e native` **63/63**, `pio run -e native` clean link,
  `ruff check` clean, `pytest` **238 passed**. Nothing committed. Nothing reflashed. No actuator
  has fired with this code.

**Deferred (gated on the power rewire above + user physically present):** reflash carrying §E +
the earlier per-actuator `BRIDGE_*_CALL_TIMEOUT_S` fix + D5→D3 pin fix + reverted safety flags;
physical first-fire of `kSweep` / `kPulseBothSync` / `kFlickerBothIndependent` on both wings;
re-fire of the 3 field tiers with the new allocation; then the overnight idle soak on the
rewired power path.

**DFO-facing language constraint (for any future HANDOVER / DFO note about the LED deterrent):**
do not claim it "keeps elephants out" or any absolute exclusion language. Every real number this
repo has is a probability of deterring a given approach, not a guarantee. Describe it as: real,
evidence- and practitioner-informed dual-wing strobe deterrence with genuine per-tier escalation,
verified working on hardware — not a promise elephants won't enter.

## RESUME HERE — 1 Sept, hardware bring-up session (ADR 0014 reflash + 4 pattern first-fires + daylight vision matrix DONE; recurring idle crash-reboot fault hit, diagnosed, power-cycle + soaks recovered it, root cause UNRESOLVED) checkpoint

Task this session (user instruction, carried from the prior session): reflash carrying the D3 pin
fix + ADR 0014 pattern code + already-reverted safety flags together in one shot; pause only at the
four first-fire moments (D3 left wing, each pattern's first real hardware fire) for confirmation;
then run unattended through the daylight vision-model matrix and the grey-card IR-throw test. Added
watch item: if the board reboots again while genuinely idle and untouched, STOP and treat it as a
real power/connector fault. Also: add the container `restart:` policy fix to scope.

**DONE — reflash (supervised):**
- `device/mpu/` + `device/mcu/src/` synced to `~/ArduinoApps/eletect-x/{python,sketch}/` via
  tar-over-ssh (`scripts/sync-to-board.sh` uses `rsync --delete` — **rsync is not available in
  Windows Git Bash**; workaround: `ssh 'rm -rf <dir> && mkdir -p <dir>'` then
  `tar -C <src> -cf - . | ssh 'tar -C <dst> -xf -'`, python tree excluding
  `tests bench pyproject.toml __pycache__ *.pyc .pytest_cache .ruff_cache models/vision/*.eim`).
- `arduino-app-cli app restart user:eletect-x` → compiled sketch + flashed STM32U585 (OpenOCD
  clean, 13 % flash / 16 % RAM) + started the Python container together, rc=0, ~1m44s. Board did
  not reboot during the flash.

**DONE — 4 supervised first-fires (all user-confirmed):** each via
`Bridge.call("drive_led", 2, 0, <pattern_id>, 50.0, <ms>)` → returned `True`.
Order: `kSteady` (D3 left wing — fired twice, user asked for a repeat), then `kSlowPulse`, then
`kFastStrobe`, then `kRandomFlicker`. **Measured latency = burst duration + ~15 ms for every
pattern** → ADR 0014's "timing logic inside the existing blocking window, zero new blocking cost"
claim is confirmed on hardware. D3 left-wing pin fix confirmed. 5-arg `Bridge.provide` arity binds
on the real `Arduino_RouterBridge`; schema v2 accepted (mismatch only logs, doesn't reject).

**DONE — daylight vision-model matrix (ran unattended after the first-fires validated the patterns;
user had explicitly authorised continuing unattended through the matrix incl. LED fires near the
camera, at 50 % gain / short bursts / 20 s cooldown respected).** Architecture: EIM runner
(`edge-impulse-linux-runner --model-file /home/arduino/etx_cpu_final_0830.eim --run-http-server
1337`, ETX-V v4, labels `["Boar","Elephant"]`, `min_score 0.05`) + camera capture + inference all
run HOST-side (container is on a bridge net, can't reach host `127.0.0.1:1337`); only actuator fires
`docker exec` into the container. Fire/capture timing aligned via the fire subprocess's **stdout
pipe** (a reader thread timestamps flushed `START`/`END` lines) — an earlier file-marker approach
failed because the container FS is a separate namespace; frames hard-capped per condition to avoid a
buffered-frame flood. Results JSON + 12 sample JPEGs preserved in the session scratchpad
(`.../scratchpad/matrix_results.json`, `matrix_run.log`).

| condition | infer ms mean/max | luma lit vs unlit | clip (`frac>250`) | spurious dets (bench = no animals ⇒ all FP) |
|---|---|---|---|---|
| camera_only | 207 / 240 | — / 139.5 | ~0 | 8/20 frames — Elephant, conf 0.074–0.111 |
| pulsed_ir ×3 | 205 / 221 | — / 141.8 | ~0 | 28/42 — Elephant, conf pinned 0.111 |
| led_steady | 203 / 215 | 144.7 / 144.3 | ~0 | 5/44 — Elephant, 0.074 |
| led_slow_pulse | 205 / 213 | 149.0 / 148.5 | ~0 | 9/44 — Elephant, ≤0.111 |
| led_fast_strobe | 203 / 210 | 154.8 / 154.1 | ~0 | **0/44** |
| led_random_flicker | 204 / 215 | 146.4 / 146.8 | ~0 | **0/44** |

Day-vs-night read:
- **LED patterns firing next to the camera cause NO daylight washout.** Within every condition
  lit-frame vs unlit-frame mean luma differs by <0.5; the 139→155 drift across the ~4-min run is
  the sun moving, not the LED. No clipping. This is the OPPOSITE of the night result (single 500 ms
  IR pulse = +99.5 % luma indoors, 74→146) — in daylight the 50 %-gain LED is swamped by ambient.
- **Pulsed IR in daylight: +1.6 % luma** (141.8 vs 139.5) — negligible vs +99.5 % at night. IR
  illuminator is invisible against daylight. A real IR-throw characterization must be a **night**
  test with a physical 18 % grey card at measured distances.
- **Latency ~203–207 ms mean, every condition, tight spread** (min 196, max 240) — higher than the
  ~137 ms prior-night baseline (daylight frames carry more texture for the model). **LED pattern
  choice adds zero latency**, matching the first-fire finding.
- **Every false positive is a noise-floor "Elephant" ghost at conf 0.074–0.111** — barely over the
  0.05 deployment threshold, far below any usable operating threshold. The prior "Elephant FP 0 %"
  does NOT hold on the daytime bench. **A deployment threshold of ~0.2 eliminates every one.**
  `fast_strobe` and `random_flicker` had zero FPs (rolling-shutter banding / motion blur during
  those bursts may disrupt the low-level texture driving the ghost box — sample too small to claim
  causation).

**THEN — the board rebooted while idle. Automated path HALTED per the failure clause.**
- boot_id `f30eae1e…` → `b2c2d983…` (regenerated only on kernel boot). The matrix had finished
  cleanly (results written, SSH session closed) ~1 h before the crash; at crash time the board was
  doing only hourly cron + `fwupd-refresh`. Not caused by session workload.
- `last -x`: **every boot since 30 Aug ends in `- crash`** (unclean — no shutdown record). 12
  crash-reboots in ~3 days, intervals 9 min to 11 h. The prior session's checkpoint had attributed
  the earlier reboots to "physical power interruptions during the D5→D3 rewire" — **that
  explanation no longer holds**: this crash happened with nobody touching the board, days later,
  and the pattern is continuous.
- NOT thermal (all 10 thermal zones 40–42 °C). No `dmesg` hardware-reset cause readable (no
  passwordless sudo). Journal-stopping-mid-line + `- crash` + ~25-min-to-hours dead gap is the
  signature of a power/VBUS drop, an intermittent connector, a sub-threshold brownout, or a hard
  SoC lockup with watchdog reset. The board's RTC also appears to jump forward on reboot (dead
  backup cell — a second SoM hardware smell).
- Collateral: `eletect-x-main-1` came up `Exited (255)` and stayed dead after the crash-reboot (and
  again after the user's power cycle) — the app auto-recovery gap, now demonstrated for real.

**Recovery (user power-cycled the board, then asked to retry):**
- Post-power-cycle health check: boot_id `b08c69f1…`, router active, thermal 43 °C.
- **30-minute idle soak → PASS** (boot_id held, zero SSH failures).
- Brought the app container + EIM runner back up (`arduino-app-cli app start`; `main.py` running,
  `SAFE_MODE=True`). Bridge zero-light probe `drive_led(2,1,0,0.0,150)` → `True`, ~12 ms overhead
  → **firmware intact in STM32 flash, no reflash needed** (confirmed, not assumed).
- **2-hour idle soak → PASS** — boot_id held `b08c69f1…` across all 25 five-minute checks,
  container + EIM up at every check, zero SSH failures. ~2 h 40 m continuous idle-stable total.
- Verdict: the power cycle changed the board's behaviour (before, it couldn't get through a session
  without crash-rebooting; now rock-solid for 2.5 h+). Most likely a reseated connector or a
  cleared latched PMIC state. **Root cause still unknown — not yet trustworthy for a 10-day
  unattended deployment.**

**DONE — container auto-recovery fix (two layers, no sudo):**
- `arduino-app-cli properties set default user:eletect-x` — the default app was **unset** (`No
  default app set`), which is why the `arduino-app-cli` daemon never restarted it on boot. Now set.
- `docker update --restart=unless-stopped eletect-x-main-1` — policy was `no`, now `unless-stopped`.
  Caveat: this is wiped whenever `arduino-app-cli app restart` **recreates** the container.

**DONE — 2 Sept survivability layer (user present, MCU reflash + watchdog + exposure ladder):**
- **MCU reflash confirmed — 3/3 checks PASS.** Clean tree flashed via `arduino-app-cli app restart
  user:eletect-x`; 8/8 sketch source files hash-match `device/mcu/src/`; `FIRE_TEST_HARNESS 0`,
  `BRIDGE_SCHEMA_VERSION 3`, `Arduino_RouterBridge 0.4.3` not pinned. Confirmation harness
  `/home/arduino/vdiff/confirm_pass_v3.py` (schema-3 wire frames): 10/10 steps OK, zero schema
  mismatch. (a) schema-3 frames all round-trip; (b) D3 left + D6 right wings each drive over real
  Bridge RPC and self-extinguish — **no latch-on** (user visually verified); a 60000 ms request
  clamps to `LED_BURST_MAX_MS` = 10 s then OFF; per-channel cooldown proven independent; (c)
  transport clean through the full ~110 s sequence, boot_id held.
- **Hardware watchdog armed.** `/etc/systemd/system.conf.d/10-watchdog.conf` →
  `[Manager] RuntimeWatchdogSec=20s / RebootWatchdogSec=3min`; `sudo systemctl daemon-reexec`.
  Journal now: `Using hardware watchdog 'qcom_wdt' … device /dev/watchdog0` /
  `Watchdog running with a hardware timeout of 20s`. `wdctl` shows Timeout 20 s, Timeleft counting
  down (systemd is petting it). Kernel / PID 1 lockup → SoC hard-reset in ≤20 s; hung shutdown
  forced after 3 min. Supersedes the earlier "no documented Linux hardware watchdog" line and the
  proposed `eletect-x-guard` timer (not needed — `unless-stopped` + docker-at-boot + watchdog
  cover the same failures). Disable: `sudo rm /etc/systemd/system.conf.d/10-watchdog.conf &&
  sudo systemctl daemon-reexec`.
- **Daylight exposure ladder — running as a unit.**
  `~/.config/systemd/user/exposure-ladder.service` (`Restart=on-failure`, linger on → survives
  reboot) runs `/home/arduino/vdiff/exposure_ladder.py`: every 15 min it walks
  `exposure_time_absolute` = [1,2,3,4,6,8,16,32,64,125,250,500,1000,2000] on `/dev/video2`
  (auto_exposure=1, gain=0, AWB off), logs mean luma / clip% / crush% / Laplacian sharpness
  (full-frame + 4 far→near bands) + 1 JPEG per rung to `~/vdiff/explad/`, `ladder.jsonl`. 12 h cap,
  stop file `~/vdiff/explad/stop`. **First outdoor sweep → lock `exposure_time_absolute=4` for
  daytime** (mean luma 128, 0.58 % highlight clip, sharpness peak 1277); ≥16 washes out (luma
  218→242), ≤2 underexposes. Unit will show noon vs golden-hour drift.

**NOT DONE — grey-card IR-throw test.** Can't produce useful data in daylight without a physical
18 % grey card and controlled lighting — the matrix already showed pulsed IR is +1.6 % luma against
daylight (unmeasurable). Needs a **night session the user sets up** with the card at measured
distances. Not faked.

**Nothing committed to git.** Working tree unchanged from session start (the `M` files predate this
session — ADR 0014 code from the prior build call, still uncommitted).

**Immediate next steps:**
1. **Overnight idle soak** before trusting the board for the trial. If it crash-reboots again while
   idle → the board needs swapping/RMA, not more software work.
2. Install the systemd guard (2 sudo commands above).
3. Grey-card IR-throw test — night, physical card, user-set-up.
4. Raise the deployment detection threshold from 0.05 toward ~0.2 (kills all the daytime
   noise-floor Elephant FPs) — revisit before real ranger alerts, was always flagged as
   field-test-only.
5. Kill the host EIM runner when vision testing is fully done; clean `/home/arduino/etx_*` +
   `/tmp/etx_*.sh` scratch.

**Session-continuity call:** start a FRESH session. This one did its job (reflash ✓, 4 first-fires
✓, daylight matrix ✓, reboot diagnosis ✓, recovery + restart fix ✓). The overnight-soak result and
the next actions are self-contained above.

### Addendum — 1 Sept, LED tier verification pass (same board, later; supervised, via `Bridge.call`)

Purpose: bench-verify the 4 bare ADR 0014 patterns + the 3 field tiers **as implemented today**
(`cognition/config.py` `DETERRENCE_TIERS` — single wing per tier), one at a time with the user
watching every fire. `FIRE_TEST_HARNESS` was ruled out for this: it hardcodes `led_pattern::kSteady`,
one wing, fixed 50 % / 1000 ms — no pattern/gain/tier selection — and is `FIRE_TEST_HARNESS 0`
(needs a reflash) with no USB serial on this board. Path used instead:
`Bridge.call("drive_led", 2, <ch>, <pattern_id>, <gain_pct>, <ms>)` via `docker exec`, same as the
4 first-fires.

- **Fires 1–4 (bare patterns) — all user-confirmed on hardware.** Left wing (ch 0), 60 % gain,
  3000 ms each. `kSteady` = stable on; `kSlowPulse` = 2 slow on/off blinks; `kFastStrobe` = ~7 Hz
  strobe; `kRandomFlicker` = visibly irregular. Wall time = duration + 13–18 ms every pattern
  (matches the first-fire finding). boot_id `b08c69f1…` held throughout.
- **Fire 5 (Tier 1: slow-pulse / left ch 0 / 50 %) — hit a `TimeoutError`, diagnosed as a
  client-side bug. The LED fired correctly regardless** (user-confirmed: 2 slow pulses, left wing,
  ~10 s, ~50 %). boot_id held — **no reboot, no firmware/hardware fault.**
  - The auto-mode classifier blocked the literal `TIER_DURATION_MS` value `65535` as an unsafe
    long-drive request (it has no knowledge of the MCU clamp). Per the user's call, Fire 5 used the
    **post-clamp value 10000**, not the literal `DETERRENCE_TIERS` constant 65535. Physically
    identical — the MCU clamps 65535 → `LED_BURST_MAX_MS 10000` anyway.
  - `Bridge.call` raised `TimeoutError: Request 'drive_led' timed out after 10s`. Confirmed on the
    board: `Bridge.call(method_name: str, *params, timeout: int = 10)` — **default 10 s**. A clamped
    10 s burst doesn't ack until it finishes, so the client gives up ~15 ms before the ack arrives.
  - **Field impact (the real bug):** `main.py`'s `drive_horn` / `drive_led` / `pulse_ir` lambdas
    called `Bridge.call` with **no `timeout=`**, and `services/config.py`'s documented
    `BRIDGE_CALL_TIMEOUT_S = 12.0` was **never actually passed anywhere**. Since every tier commands
    `TIER_DURATION_MS = 65535` → clamp 10000, **every LED tier fire in the field would have raised
    `TimeoutError` in the reflex loop** — the deterrent still fires physically, but cognition sees an
    exception where the ack should be (bandit reward attribution, logging, any post-fire logic all
    sit downstream of that call). `drive_horn` was at the same risk margin.
- **FIX — done this session, host-tested, NOT yet on the board (uncommitted):**
  - `device/mpu/services/config.py`: single `BRIDGE_CALL_TIMEOUT_S` → per-actuator timeouts, each
    just above its own `device/mcu/src/config.h` cap + transport margin —
    `BRIDGE_HORN_CALL_TIMEOUT_S = 5.0` (cap 3000), `BRIDGE_LED_CALL_TIMEOUT_S = 12.0` (cap 10000),
    `BRIDGE_IR_CALL_TIMEOUT_S = 2.0` (cap 500). `BRIDGE_CALL_TIMEOUT_S` kept as an alias = the LED
    value for the non-actuator (`get_system_state`) path and `bridge/rpc.py`'s docstrings.
  - `device/mpu/main.py`: all three actuator lambdas now pass
    `timeout=config.BRIDGE_<ACTUATOR>_CALL_TIMEOUT_S`.
  - `device/mpu/tests/test_config.py`: the old single drift check split into
    `test_actuator_call_timeouts_each_exceed_their_mcu_cap` (per-actuator, reads the three caps from
    `config.h`) + `test_generic_bridge_call_timeout_still_covers_longest_burst`.
  - `ruff check` clean, `pytest` **234 passed**. `timeout=` kwarg confirmed accepted on the board
    (zero-light probe, gain 0.0, `ret=True`). `tests/test_reflex_loop.py` structurally can't cover
    this seam — it injects fake `drive_*` callables and `main.py` can't be imported host-side
    (module-scope `from arduino.app_utils import Bridge`, forbidden by `pyproject.toml`) — so the
    host guard is `test_config.py` + full-suite-green; the integration proof is the supervised
    hardware re-fire.
  - **Deploy:** the running container still has the old `main.py`; the fix goes live at the next
    `arduino-app-cli app restart` / reflash. Fires 5–7 tonight pass an explicit `timeout=` in the
    manual `docker exec` call, so they don't wait on the deploy.
- **ADR 0014 Part C — simultaneous dual-wing for Tier 2 / Tier 3 — is UNIMPLEMENTED, not just
  unverified.** MPU-side orchestration for it does not exist: `DETERRENCE_TIERS` drives exactly one
  wing per tier (T1 slow-pulse / left ch 0 / 50 %, T2 fast-strobe / **right ch 1** / 75 %, T3
  random-flicker / left ch 0 / 100 %). MCU `drive_led` also takes one channel per blocking call, so
  it can't do simultaneous dual-wing per call regardless. This is a real scope gap tracked as
  follow-up work (`cognition/config.py` ~L316–319 already flags it; the later checkpoint below at
  "T2 … Alternating both wings within one tier (ADR Part C …)" is the same item). Tonight's pass
  verifies the single-wing tiers only and is not expected to cover Part C.
- **Fires 6–7 (Tier 2 fast-strobe / right ch 1 / 75 %, Tier 3 random-flicker / left ch 0 / 100 %):**
  to be re-run with the explicit `timeout=` fix, user present.

## RESUME HERE — 1 Sept, later session (ADR 0014 LED patterns + gain wired end-to-end and host-tested; board NOT reflashed) checkpoint

Task this session (user instruction): implement all four ADR 0014 LED patterns in `led.cpp`, wire
them through the new `channel`/`gain_pct` schema, host-test — then (deferred) reflash with the D3
pin fix + safety flags, and run the full daylight vision-model test matrix. Only the code +
host-test half was in scope this session; the reflash and the entire vision matrix are hard-blocked
(see "Deferred" below).

**Done — MCU (`device/mcu/`):**
- `src/led.h` — new `enum class led_pattern : uint8_t { kSteady=0, kSlowPulse=1, kFastStrobe=2,
  kRandomFlicker=3 }`, `led_pattern_from_id()` (unknown id → `kSteady`), `led_request` gains
  `pattern` and `gain_pct` fields.
- `src/led.cpp` — the four patterns as timing logic **inside `drive_led()`'s existing blocking
  window** (replaces the single `delay(duration_ms)`): `kSteady` = on/hold/off; `kSlowPulse` =
  `LED_SLOW_PULSE_CYCLES` (2) even on/off cycles, remainder folded into the last cycle so the burst
  still totals `duration_ms` exactly; `kFastStrobe` = `LED_FAST_STROBE_HZ` (7) strobe, sub-period
  remainder spent dark; `kRandomFlicker` = xorshift32 (no `<random>`/libm/heap) irregular on/gap
  flashes seeded from `micros()` at call time. **Zero new blocking cost** — every pattern's on+off
  spans sum to exactly the rule-gate-resolved `duration_ms`; `rule_gate_apply()` stays the sole
  authority on duration and duty.
- `src/config.h` — `BRIDGE_SCHEMA_VERSION 1 → 2`; new `LED_SLOW_PULSE_CYCLES`, `LED_FAST_STROBE_HZ`,
  `LED_RANDOM_FLICKER_{MIN,MAX}_{ON,GAP}_MS` timing constants.
- `src/bridge_handlers.{h,cpp}` — `bridge_drive_led(schema_version, channel, pattern_id, gain_pct,
  duration_ms)` (was `(schema_version, pattern_id, duration_ms)`); `led_channel_for_pattern_id()`
  renamed `led_channel_from_wire()` (0 → left, 1 → right, else → left). `gain_pct` is no longer
  hardcoded to the config max.
- `src/fire_test.cpp` — the two `led_request` aggregate inits carry `led_pattern::kSteady` (bench
  harness verifies wiring/polarity, not pattern shape).
- `hostshim/` — new `hostshim::PinWrite{pin,value,at_ms}` event log + `pin_writes()` accessor;
  `digitalWrite`/`analogWrite` append to it, `reset()` clears it. Lets a host test assert on the
  *shape* of a blocking flash sequence (edge count, gaps, total elapsed) that `pin_state()` — only
  the final value — cannot see.
- `tests/test_led/test_led.cpp` — **new**, 7 cases: pattern-id mapping incl. fallback; each of the
  four patterns' edge count + "ends off" + "burst totals exactly `duration_ms`"; `kRandomFlicker`
  gaps are non-uniform; over-cap gain clamps but still fires; a re-fire inside `LED_COOLDOWN_MS` is
  refused and touches no pin.
- `tests/test_bridge_handlers/test_bridge_handlers.cpp` — rewritten for `led_channel_from_wire` +
  `schema_version 2`.

**Done — MPU (`device/mpu/`):**
- `services/config.py` `SCHEMA_VERSION 1 → 2`; `bridge/rpc.py` `drive_led(schema_version, channel,
  pattern_id, gain_pct, duration_ms)` + docstring; `main.py` lambda now 5-arg; `services/
  reflex_loop.py` `DriveLedFn` Protocol + call site + SAFE_MODE log line all updated.
- `cognition/bandit.py` `DeterrenceAction` gains `led_channel_id: int` and `led_gain_pct: float`;
  `led_pattern_id` now a real pattern selector (0–3), not a channel selector.
- `cognition/config.py` — new `LED_TIER_{1,2,3}_GAIN_FRACTION` (0.5 / 0.75 / 1.0); `DETERRENCE_TIERS`
  reallocated per ADR 0014 Part D: **T1** slow-pulse (1) / left wing (0) / 0.5 gain; **T2**
  fast-strobe (2) / right wing (1) / 0.75; **T3** random-flicker (3) / left wing (0) / full gain.
  Alternating *both* wings within one tier (ADR Part C — needs MPU-side dual `drive_led` calls) is
  left as a follow-up; each tier drives one wing today.
- `tests/test_cognition_config.py` — pattern-id check widened to 0–3, new channel-id / distinct-
  signature / LED-gain-monotonic / LED-clamp-drift checks; `tests/test_reflex_loop.py` `_FakeDriveLed`
  5-arg; `bench/demo_replay.py` LED print line updated (wing + pattern name + gain).
- `bridge/schema.md` — header `schema_version = 2` + version-history note; `drive_led` row rewritten;
  "Actuator gain defaults" section now covers only `pulse_ir` (LED has a real `gain_pct` field now).

**Verification (all green):** `pio test -e native` 56/56 (new `test_led` 7/7, `test_bridge_handlers`
4/4); `pio run -e native` clean link; `ruff check` clean; `pytest` 233/233. Nothing committed.

**Pre-existing breakage noticed, NOT fixed (out of scope):** `device/mpu/bench/demo_replay.py`
already fails before reaching any LED code — `handle_footfall_event() missing 1 required keyword-only
argument: 'detect_vision'` — this predates ADR 0014. Its LED print line was updated in place and
byte-compiles; the script's own missing-`detect_vision` bug is for whoever owns the bench.

**Docs updated:** `TRIAL_READINESS_PLAN.md` §E (implement + host-test marked done, reflash bullet now
lists the arity + reboot checks to do first), `docs/KNOWN_GAPS.md` (the `pattern_id → led_channel`
invented-mapping entry and the LED half of the `gain_pct` wire-mismatch entry both closed via ADR
0014, IR halves unchanged).

**Deferred to a supervised daylight session (hard-blocked, per project Hard Safety Rule + ADR 0014
Consequences + the failure clause):**
- Reflash from the clean tree carrying ADR 0014 patterns + the D5→D3 left-wing pin fix +
  `FIRE_TEST_HARNESS 0` + `FIRE_TEST_LED_GAIN_PCT 50.0f` — one reflash, confirm all together
  (`TRIAL_READINESS_PLAN.md` §H).
- First physical fire of each new pattern (pause points: D3 left wing, then each pattern's first
  real fire).
- Verify the new **5-arg `Bridge.provide("drive_led", bridge_drive_led)` arity** actually binds on
  the real `Arduino_RouterBridge` — this is exactly the case the one-at-a-time `provide()`
  discipline exists for.
- ~~Diagnose the 3× board reboots and the `eletect-x-main-1` `Exited (255)`~~ **DONE, 1 Sept**
  (SSH, actuators unpowered, no reflash). **Not a hardware fault — physical power interruptions
  during the 31 Aug D5→D3 wing-pin rewire.** `journalctl --list-boots` + a fault-signature sweep
  across all 7 retained boots: zero OOM / thermal-trip / undervoltage / brownout / watchdog /
  panic / RCU-stall signatures. Each of the 3 transitions = journal ending abruptly mid-routine-op,
  no `systemd` shutdown sequence, board off 6–10 min (a panic/watchdog recovers in seconds), RTC
  reset to 1970 on each recovery (full power loss, not a warm reset). `last`/wtmpdb marks *every*
  boot back to 27 Aug as `crash` — this board is habitually unplugged, not shut down. Container:
  `docker inspect` → `OOMKilled: false`, `Error: ""`, `RestartCount: 0`, `FinishedAt` one second
  after the current boot's kernel start — it died *with* the power cut; exit 255 is the generic
  containerd-shim "ungraceful stop", not an app error (logs at exit show only the `SAFE_MODE=True`
  startup banner, no traceback). It "did not auto-recover" because the platform-generated
  `app-compose.yaml` has no `restart:` policy (Docker default `no`) — added as a field-readiness fix
  to `TRIAL_READINESS_PLAN.md` §H. Board healthy now: 37–41 °C, 3 GB RAM free, uptime stable since
  the 01:24 UTC boot. **Safe to proceed to the reflash** (Hard Safety Rule unchanged). Caveat: a
  no-software-visible-fault verdict can't rule out a marginal USB-C cable/connector — if the board
  reboots again while genuinely idle and untouched, treat it as a real power-connector problem.
  Full write-up: `TRIAL_READINESS_PLAN.md` "Board-reboot / container-exit diagnosis" section.
- **Entire daylight vision-model test matrix** (part 2 of the user's request): stand up the EIM
  `:1337` runner + full `device/mpu` sync; capture daylight footage per condition (camera-only,
  pulsed-IR, each of the 4 LED patterns firing near the camera); run `HttpVisionDetector` per
  condition; report FP/FN/latency + exposure-washout / spurious-detection; compare against last
  night's camera-only and pulsed-IR numbers; write the day-vs-night per-pattern per-condition
  comparison into the report and update `TRIAL_READINESS_PLAN.md` + `HANDOVER.md`. Runs unattended
  once started except the four first-fire pauses.

**Session-continuity call:** start a FRESH session for the daylight reflash + bring-up + vision
matrix. This session was the code/host-test build call; per the project protocol it should not roll
straight into hardware work.

## RESUME HERE — 1 Sept, ~01:45 IST (steady-on actuation path re-verified for the trial; field-safety flags reverted in source, board NOT yet reflashed; overnight monitor was dusk-only; strobe deferred) checkpoint (same long session as the ~15:40 sweep below, continued)

Task this session: before ending, verify exactly what the 2 Sept DFO trial ships, lock the
field-safety state, pull the overnight data, and record tonight's real findings.

**Steady-on Bridge RPC path re-verified end-to-end — this is the trial's actuation path.** A
disposable host pass (`/home/arduino/vdiff/confirm_pass.py`) fired left wing / right wing / IR each
over the real `arduino-router` socket (`docker exec` → `fire_client.py` → `/run/arduino-router.sock`
→ MCU `bridge_drive_led`/`bridge_pulse_ir`, **not** the `FIRE_TEST_HARNESS` console path):

- Each wing fires (`ack=true`); each re-fire inside its 20 s window correctly refused (`ack=false`);
  right fires while left is still gated and vice-versa → `LED_COOLDOWN_MS` is genuinely per-channel.
- IR fires; `IR_MIN_INTERVAL_MS = 5000` gate holds — a tightened re-test (needed because the first
  pass's timing was loose) refused re-fires at +2.0 s and +3.4 s, allowed one at +10.6 s.
- Over-cap requests still `ack=true` — the rule-gate clamps silently, never rejects.

Two apparent mismatches in the first pass were both run-harness artifacts, cleared on re-test:
(a) an IR re-fire that acked `true` had actually landed ~6 s after the prior pulse, outside the 5 s
window; (b) `drive_led[1,1,60000]` returned no ack because it clamps to `LED_BURST_MAX_MS = 10 000`
and the MCU **blocks on `delay(10000)`** (`led.cpp:63`) longer than the test client's ~10 s socket
timeout. Neither is a firmware fault. Data pulled to
`device/mpu/bench/camera_check/output/confirm_2026-08-31/` (log.txt, 20 base/peak JPEGs,
tightened_recheck.txt).

**New quantified finding — every real actuator fire stalls the MCU control loop for the full clamped
burst.** The deployed MPU requests `TIER_DURATION_MS = PROTOCOL_DURATION_MS_MAX = 65535` on *every*
`drive_led`/`drive_horn`/`pulse_ir` (`device/mpu/cognition/config.py`, "ask for the max, let the MCU
clamp" policy). So per live alert the real stall is: **`drive_led` → 10 s** (`LED_BURST_MAX_MS`),
`drive_horn` → 3 s, `pulse_ir` → 500 ms — `led.cpp`/`horn.cpp` both do `HIGH → delay(clamped) → LOW`
inline. Reproduced live tonight. Production ack survives only because `services/config.py`
`BRIDGE_CALL_TIMEOUT_S = 12.0` is sized for exactly the 10 s LED clamp; a shorter-timeout client
loses it. Geophone/LoRa starvation during the burst is real and is now a 10 s window per wing fire,
not the ~3.15 s the old `loop()`-blocking gap quotes for the horn. Same root cause / same fix as the
27 Aug `pulse_ir()` blocking entry — recorded as a 1 Sept addendum on the `loop()`-blocking entry
near the top of `docs/KNOWN_GAPS.md`, plus a new "Steady-on actuation path re-verified" section at
the file's end. **Not touched before the trial** (would need a reflash of trial-critical firmware).

**Field-safety flags reverted in `device/mcu/src/config.h` — SOURCE ONLY:**
`FIRE_TEST_HARNESS 1 → 0`, `FIRE_TEST_LED_GAIN_PCT 100.0f → 50.0f`, both back to committed values.
`LED_GATE_ACTIVE_LOW` confirmed absent. The only remaining working-tree change in config.h is the
legitimate D5→D3 left-wing pin move. **The board's flashed binary still has the harness compiled in
and gain at 100** — it was built that way earlier in the bring-up. A reflash from this now-clean tree
is required before the node goes to the field, and that same reflash is what first carries the D3
left-wing pin fix onto the board (without it the left wing is driven on a dead USB pin). It should be
the **first action of the next session** (`scripts/sync-to-board.sh` → App Lab / `arduino-flash`),
before any IR-throw work. Deferred tonight per "no reflash hours before a live trial."

**Overnight monitor was dusk-only — `STOP_HOUR` bug.** `vdiff_overnight.py`'s stop check
(`datetime.now().hour >= STOP_HOUR` with `STOP_HOUR = 8`) is true all afternoon/evening too, so it
self-stopped at 16:43 board time after ~1 h instead of running to dawn. Got 61 luma samples / 6
frames / 3 IR pairs (IR deltas +26.1 / +24.3 / +27.1 %, consistent with the sweep). All pulled to
`device/mpu/bench/camera_check/output/overnight_2026-08-31/` (15 files). `mainpy_overnight.log` came
back **0 bytes** — the `docker logs -f` capture wrote nothing; not yet diagnosed. No dawn-transition
data exists; that still needs a real overnight run with the stop logic fixed.

**Correction to the ~15:40 checkpoint below:** `main.py` is **not** restart-looping. `docker inspect`
shows `RestartCount=0`, status running, started 13:30 UTC — up ~6 h. The repeated "App is starting"
banners in the log are the whole session history (09:58 / 10:09 / 10:30 / 13:30), not a loop. It is
quietly blocking-alive after registration, as designed. `SAFE_MODE=1` still confirmed (fires
nothing).

**Strobe LED patterns deferred — trial ships steady-on wings only.** An irregular/randomised strobe
(the deterrence literature's actual argument for light) needs `led.cpp` `pattern_id` timing, a host
test, a reflash, and re-verification of the one proven actuation path — not a change to make hours
before the trial. Recorded as named post-trial work in `docs/KNOWN_GAPS.md`. `led.cpp` untouched
this session.

**Live board state at checkpoint:** `run.py` streamer running on the board (:8090, 90-min self-cap),
SSH tunnel to `localhost:8090` still open, `docker logs -f` PID 43562 may still be running. Camera is
held by `run.py`. Two `confirm_*` dirs + one `overnight_*` dir + the disposable `.py` scripts remain
in `/home/arduino/vdiff/` for cleanup once vision work is done. Nothing committed to git (no explicit
ask). Working tree now has: `device/mcu/src/config.h` (D3 pin move only), `docs/KNOWN_GAPS.md`
(tonight's entries), `HANDOVER.md` (this checkpoint) — plus everything already modified before.

**Pending, in priority order:**

1. **Reflash the MCU from the clean tree** — first action next session. Carries the `FIRE_TEST_HARNESS
   0` / gain-50 reverts AND the D3 left-wing pin fix onto the board. Blocking for field deployment.
2. Daylight IR-throw characterization (grey card at 3/5/10/15/20 m on boresight, `pulse_ir`, log
   delta% at target region). Needs daylight + a helper. **Fresh session** — this one is very long.
   Full plan in the ~15:40 checkpoint below and in `docs/KNOWN_GAPS.md`.
3. Full `device/mpu` Python-tree sync (`sync-to-board.sh`) to bring `HttpVisionDetector` current on
   the board, then stand up the EIM `:1337` HTTP runner and re-run the vision-behaviour checks.
   `.eim` artifacts are already on the board at `/home/arduino/etx_*.eim`.
4. Fix `vdiff_overnight.py`'s `STOP_HOUR` logic and run one real dawn-transition monitor.
5. Confirm the D7 MOSFET actually switches the external IR board's ground return; ~300 mA when pulsed.
6. Cleanup: board `/home/arduino/vdiff/` scratch scripts + dirs, kill `docker logs -f` PID 43562 and
   the SSH tunnel, scratchpad JPEGs, `device/mpu/bench/drive_led_check/`.

## RESUME HERE — 31 Aug, ~15:40 (30-min actuator sweep: LED wings camera-invisible at foliage range, IR strong and repeatable; no vision model deployed on the board; overnight monitor started) checkpoint (live vision-diff bring-up session, following on directly from the ~14:00 actuator-confirmation checkpoint below)

Goal this session: with all three actuators already physically + Bridge-RPC confirmed (per the
~14:00 checkpoint), characterize whether each one produces a camera-detectable scene change at
realistic outdoor range — optical effect, not "does it fire." A 5-condition pilot, then a proper
30-minute automated sweep (9 conditions x 5 reps, interleaved round-robin, auto-verified against a
~10% threshold derived from tonight's own measured noise floor).

**Real, repeatable result — not a bug, not a fluke:** neither LED wing produces a camera-detectable
change at foliage range. 45/45 sweep trials, zero verdict inconsistencies across repeats: baseline
0.89%, left wing 1.57%, right wing 1.73% — both wings statistically indistinguishable from the
0.89% baseline noise floor. The pilot's earlier "left +14.9%" was a transient outlier that did not
reproduce once across 5 clean reps — the right wing was never broken either (the pilot's "right
+0.1%" was actually the *left* reading being anomalous that one time). **IR is the opposite story**:
+28.9% mean, tightly repeatable (+-1.5%), across every condition that includes it (IR-alone and
mixed both land there — the wings add nothing measurable on top of IR). Every one of the 70 live
fires acked; 10 within-cooldown re-fires correctly acked=false (20s per-channel gate, independently
verified for left and right). This is conclusively **not** a firmware/wiring fault — the same
Bridge -> MCU -> camera path that produces IR's clear signal carries the LED calls too. The wings
are simply not bright enough relative to the lit scene at this distance/exposure to register on
camera. Full data: `device/mpu/bench/camera_check/output/vision_diff_2026-08-31/` (pilot + sweep,
92 sweep files: t01-t45 JPEG pairs, log.csv, summary.txt) — board copy at
`/home/arduino/vdiff/shots/sweep_20260831_150907/`.

**Important scope correction, worth being explicit about:** `device/mpu/perception/` on the board
right now is camera.py + storage.py only — no detector. This means tonight's data (pilot, sweep,
and the overnight monitor below) is pure camera/luma characterization, **not** real vision-model
inference or false-positive data, despite earlier framing this session as being partly about "how
does the vision model react." This is not a regression or a forgotten deployment — it's the direct,
expected consequence of the planning session's own earlier decision this session to sync
**MCU sketch only** (not the full `device/mpu` Python tree) for the LED bring-up work, specifically
to isolate that test from 9 days of unrelated Python changes. `HttpVisionDetector`
(`device/mpu/perception/detector.py`) and its fusion-loop wiring are real, committed code
(commit `b5e139a`, `9 Aug 22` heading below) — just not yet synced to this board's running copy.
Folding the full Python sync in is a legitimate near-term follow-up, not urgent tonight.

**Overnight monitor started** (`vdiff_overnight.py`), `SAFE_MODE=1` confirmed already the running
state (main.py container dry-running, logs "[SAFE_MODE] would open camera..." and fires nothing).
Records: 60s luma samples, 10min full frames, 20min fixed-exposure IR on/off pairs with logged
delta% (first two: +26.1%, +24.33%, consistent with the sweep's IR numbers). Self-stops at local
hour 8 / a stop file / a 12h hard cap — **started 15:43 board time 31 Aug, so the 12h cap likely
already fired around 03:43 1 Sep; this run is probably complete but the data has not yet been
pulled to the laptop** — that pull is the one concrete immediate next step, doable in the current
session while the board's still reachable. Given the scope correction above, expect this to be a
luma/light-transition dataset, not a detection dataset — still valuable for the original dawn-light
question, just not for false-positive-rate.

**A second, real open question surfaced and partially investigated: IR throw/range.** The
"10-20m" figure the user has been operating on **appears nowhere in any project document** (BOM,
procurement notes, WIRING_GUIDE.md, KNOWN_GAPS.md, the enclosure CAD concept, the vision-model
prompt) — likely a misremembered listing figure or conflation with the design target. The one
documented range figure (~3m, `KNOWN_GAPS.md:1673`) is for the camera's own onboard 940nm LEDs,
explicitly *separate from* the external VISTORA 48-LED board's real-range extension. That external
board's throw **has never been characterized** — `enclosure-design-concept.md:467` already flagged
a "five-minute bench check" that was never done; everything "known" about its range is inference
from near-field foliage luma, which cannot answer a distance question. User confirmed mid-session
the external board is wired to 12V, ruling out under-drive as the explanation. Remaining candidates:
measurement artifact (most likely — no target-at-distance test has ever run), beam angle (a wide
90-120 flood from 48 small LEDs genuinely doesn't throw far; 940nm reads ~1/3 as bright to the
sensor as 850nm for the same power), aim/focus, or the D7 MOSFET not actually switching the
external board's ground return (worth a quick eyeball check). **Real verification plan, needs
daylight and a helper, not tonight:** inline/clamp meter on the board (confirm ~300mA when pulsed),
phone selfie-cam check (confirm LEDs visibly flash), a wall-circle beam-angle measurement, and the
test that actually settles it — a grey card at 3/5/10/15/20m on boresight, `pulse_ir`, log delta%
at the target region (not whole-frame) — wherever it drops under ~10% is the real usable throw.
Correct `enclosure-design-concept.md`'s "30-40m" claim and add the real number to
`docs/KNOWN_GAPS.md` once measured.

**Deterrence-efficacy question also addressed this session, worth recording plainly:** IR is not a
deterrent by design — 940nm was chosen in `CONTEXT.md` specifically because elephants can't see it
(camera illumination only, no startle). The white+blue strobe is the actual visual deterrent, but
per human-elephant-conflict literature, light-based deterrents are a low tier tool (flashing lights
work mainly by simulating human presence), habituation within days-to-weeks is the dominant failure
mode, and effect in daylight is near-zero. Strong evidence instead favors beehive fences, chilli,
and multi-modal unpredictable deterrents. This device's own design already treats light as the
junior partner (horn primary, LED supplementary, IR non-deterrent) for exactly this reason — the
bandit's never-repeat/stop-on-retreat logic and the unpredictable-pattern strobe exist precisely
because fixed deterrents stop working. Tonight's finding that the wings are camera-invisible at
range doesn't prove an elephant can't see them (different eye, no exposure lock like the camera
has) but isn't encouraging. **Efficacy on this hardware is completely unvalidated** — no
animal-outcome feedback exists anywhere, the bandit reward is an unvalidated proxy, `gain_pct` has
no physical effect yet. Contest/DFO material must say deterrence is *designed*, never *measured*.

**Other findings:** `main.py`'s container showed repeated "App is starting" banners — possibly
restart-looping, not run down this session (captured in `mainpy_overnight.log`). Nothing committed
to git this session (per instruction — no commit without explicit ask).

**Pending, in priority order:**
1. Pull the overnight monitor data (`overnight_20260831_154314/` + `mainpy_overnight.log`) from the
   board while still reachable — quick, low-risk, do this before ending tonight's session.
2. Update `docs/KNOWN_GAPS.md`: wings produce no camera-detectable change at foliage range; IR
   throw never measured; the "10-20m" figure has no documentary basis.
3. Daylight IR-throw characterization (grey-card-at-distance test) — needs daylight + a helper,
   explicitly deferred, not tonight. Recommended as a **fresh session** (this one is very long).
4. Confirm the D7 MOSFET actually switches the external IR board's ground return and it draws
   ~300mA when pulsed — quick multimeter check, anytime.
5. Before any field-bound sync: revert `FIRE_TEST_HARNESS` to 0 (still 1 from tonight's bench
   work) — not urgent to do as a standalone reflash right now (would disturb the still-possibly-
   running overnight monitor), fold it into whichever session next needs to touch the MCU sketch.
6. Cleanup once vision work is fully done: board `/home/arduino/vdiff/` scratch scripts,
   `camera_check_bench` dir, scratchpad JPEGs.
7. Fold the full `device/mpu` Python tree sync in eventually (brings `HttpVisionDetector` current
   on the board) — legitimate near-term work, not urgent tonight, do deliberately per the same
   isolate-the-variable discipline as everything else this engagement.

## 31 Aug, ~14:00 (all three reflex actuators physically confirmed — left wing D3, right wing D6, IR D7; LED_GATE_ACTIVE_LOW workaround reverted; drive_led + pulse_ir both registered)

The 31 Aug ~02:30 checkpoint's `LED_GATE_ACTIVE_LOW` firmware workaround was **reverted** — it was
the wrong direction. A new user observation settled the polarity question: with the board powered but
no code running, **both wings sit OFF**; they only latched ON once the renamed firmware ran. That is
normal active-high / fail-safe-off behaviour (`WIRING_GUIDE.md` §4 as written), so inverting in
firmware was backwards. The real fault: **D5 = PA11 = USB_OTG_FS D−** on the UNO Q. The Arduino core
claims PA11/PA12 for the USB CDC, so `digitalWrite(5, LOW)` in `led_init()` is a no-op and the left
wing gate latched high. Confirmed against the Zephyr board devicetree
(`boards/arduino/uno_q/arduino_r3_connector.dtsi`).

**Fix applied and verified:** left wing gate moved **D5 → D3 (PB0, TIM3_CH3)** — a clean PWM GPIO not
shared with any bus. User re-wired it physically. `config.h` now `LED_WING_LEFT_PIN 3` with a comment
recording why; right wing unchanged on D6 (PB1). `led.cpp` fully restored to the plain active-high
path — `gate_duty()` helper removed, `digitalWrite(LOW)` / plain `analogWrite` back; `git diff` on
`led.cpp` is now the 30 Aug rename only. `FIRE_TEST_LED_GAIN_PCT` bumped 50→100 for visual
confirmation (revert before field).

**All three reflex actuators physically confirmed this session** — harness path (App Lab serial
`2`/`3`/`4`) and Bridge RPC path (bench client `device/mpu/bench/drive_led_check/`) both:
- `drive_led` pattern 0 → **left wing (D3)** — lit then off, user-confirmed, `ack=True`
- `drive_led` pattern 1 → **right wing (D6)** — lit then off, user-confirmed, `ack=True`
- `pulse_ir` → **IR illuminator (D7)** — `ack=True`; camera-diff test on the real IMX462 (indoor
  room scene) showed a single 500 ms pulse **doubles mean scene luma (74 → 146, +99.5 %)** for
  ~480 ms then drops straight back. "Dim on a phone camera" was only the phone's IR-cut filter — the
  IMX462 (NIR-sensitive) sees it strongly. Real optical output still depends on the §5 dedicated
  12 V IR buck (on a bench rail now), a field-wiring item.
- `drive_led` still works after adding `Bridge.provide("pulse_ir", ...)` — the "new provide breaks
  the previously-working ones" regression did not occur.

**`main.cpp` now has BOTH `Bridge.provide("drive_led", ...)` and `Bridge.provide("pulse_ir", ...)`
uncommented.** One-at-a-time discipline was followed — `drive_led` first, confirmed end-to-end, then
`pulse_ir`. `drive_horn` / `get_system_state` / `send_lora_alert` still commented.

**State / holds:**

- `config.h`, `led.cpp`, `main.cpp` (+ the 30 Aug rename set) edited locally AND synced to the board
  sketch (tar-over-ssh, `secrets.h` preserved — Jul 28 mtime intact). App Lab flashed. Board sketch
  verified to match local.
- `device/mpu` tree on the board still stale (Aug 22) — deliberately not synced.
- `FIRE_TEST_HARNESS 1` still set; `FIRE_TEST_LED_GAIN_PCT 100.0f` — both must revert before any
  field-bound sync.
- `LED_GATE_ACTIVE_LOW` fully removed — do not reintroduce.
- `WIRING_GUIDE.md` §4 active-high / fail-safe-off gate stage (10 kΩ gate→source pulldown, series
  gate resistor) is still the mandatory pre-field wiring; the D5→D3 move is a firmware/pin fix, not a
  substitute. An ADR for the pin move + the bench/field wiring split is still worth writing.
- Next: "strategy 4" — autonomous vision-diff (baseline / LED / IR / mixed) + unattended overnight
  dawn-transition monitor.
- `device/mpu/bench/drive_led_check/` can be deleted now that both `drive_led` and `pulse_ir` are
  physically confirmed.

## 30 Aug, live bench session (LED_WHITE_PIN/LED_BLUE_PIN renamed to LED_WING_LEFT_PIN/LED_WING_RIGHT_PIN, code-side; live bring-up in progress with user at the bench)

User is actively wiring/testing LED wings + IR tonight (D5=left wing, D6=right wing, D7=IR, both
confirmed wired). Before the bench fire-test, the firmware naming mismatch flagged earlier this
session (task #21) was fixed for real: `LED_WHITE_PIN`/`LED_BLUE_PIN` -> `LED_WING_LEFT_PIN`/
`LED_WING_RIGHT_PIN` across `config.h`, `led.h`, `led.cpp`, `fire_test.h`/`.cpp`,
`bridge_handlers.cpp`, and both `test_fire_test.cpp`/`test_bridge_handlers.cpp` unit tests -
enum values (`kWhite`/`kBlue` -> `kWingLeft`/`kWingRight`), variable names, ack print labels
(`led_white`/`led_blue` -> `led_wing_left`/`led_wing_right`), the fire-test menu text, and test
names all updated consistently. Verified no residual old-name references remain outside stale
`.pio/build/` artifacts (regenerate on next build). `hardware/PIN_MAP.md` and
`hardware/WIRING_GUIDE.md` updated to match - both previously described the never-built 4-channel/
10-LED plan's naming as "planned"; now correctly show the real 2-wing/2-MOSFET build as done.
**Not yet done**: no compilation has been verified (no embedded toolchain available from this
session) - the sync-to-board.sh + App Lab flash the user is about to run is the first real
compile/flash check. If it fails to build, the rename is the first place to check.

Live bring-up sequence in progress, full detail in chat: Phase 1 manual fire-test via App Lab
(LED wings then IR, human-triggered and physically watched) -> Phase 2 Bridge.provide() 
registration for drive_led/pulse_ir one at a time, tested between each -> Phase 3 automated
vision-diff analysis (baseline/LED/IR/mixed, via Bridge once registered) -> Phase 4 unattended
overnight dawn-transition monitor. horn/geophone integration deferred to morning.

## RESUME HERE — 30 Aug, later still (bring-up order finalized by the user: LED wing first, then IR, then horn/speaker, then combine — supersedes the earlier horn-first ordering) checkpoint (user request: "generate a proper progress plan and plan forward, with led physical setup first and test, then ir, then speaker, then what plan")

The 26 Aug audit and the 30 Aug strategic-redirect checkpoint below both documented the bring-up
order as power bus → GPIO → **horn** → LED → IR → Bridge registration → filmed end-to-end test. The
user has now explicitly reordered this: **LED first, then IR, then horn/speaker**, then combine.
This checkpoint records the finalized order and the full plan through to field-deployment
readiness — treat this as superseding the actuator sequencing in every earlier checkpoint (the
non-sequencing content of those checkpoints, e.g. the known `delay()`-blocking bug, the
IR-cut-filter test requirement, and the Bridge-registration regression history, all still applies
unchanged).

**Stage 0 — Power bus finished and verified (prerequisite to every stage below, not skippable).**
Complete fuse + switch wiring per `hardware/WIRING_GUIDE.md` §1. Multimeter-verify every buck
output with **no load connected** — the 12V rail (horn + IR) and whichever rail feeds the LED wings
(user has floated 3.3V) — against their set points before anything downstream is connected. Only
then connect the real LiFePO4 pack, per ADR 0012's discipline (the pack's own BMS is the only
overvoltage backstop in this design, so a clean buck reading before connection is the whole safety
margin). This can happen in parallel with Stage 1's wiring prep, but no actuator gets bus power
until this stage reads clean.

**Stage 1 — LED wing, physical setup and test (first, per the user's reorder).**
Before wiring: resolve the still-open firmware/design mismatch — `WIRING_GUIDE.md` §4.0 documents a
4-channel/10-LED redesign (white-L/R, blue-L/R, decided 22 Aug) that was never implemented in
firmware; the user's actual build is the simpler 2-wing/2-MOSFET design (2 blue + 3 white LEDs in
parallel per wing) on the existing `LED_WHITE_PIN`(5)/`LED_BLUE_PIN`(6) pins. Firmware and docs
should reflect whichever one is actually being wired before the fire-test harness is trusted to
mean anything. Also still open: no series resistors on the parallel LEDs was flagged as a real
cascading-thermal-failure risk for a multi-day unattended trial — worth a final decision before
this stage, not after.
1. Wire one wing (one MOSFET, its 5 LEDs in parallel, gate resistor + pulldown per the project's
   standard IRLZ44N low-side pattern).
2. Flash with `FIRE_TEST_HARNESS 1`, trigger the LED command, and **physically watch it fire** —
   the harness has only ever confirmed a serial ack before, never a real actuator response.
3. Repeat for the second wing.
4. Fire both wings together once each is individually confirmed; check the shared buck doesn't sag
   under combined draw.

**Stage 2 — IR illuminator.**
Do the IR-cut-filter dark test *first*, before wiring anything — this has been an open, unconfirmed
item since the 26 Aug audit. If the camera's IR-cut filter blocks the 940nm illuminator, night
captures blackout and the illuminator's placement/approach needs rethinking before wiring commits to
a physical position. Then wire per §5 (dedicated 12V buck), same low-side IRLZ44N pattern on
`IR_ILLUMINATOR_PIN`(7). Fire-test with a phone camera pointed at the illuminator in a dark room —
940nm is invisible to the naked eye but visible to most phone camera sensors, so this is the actual
way to confirm it's firing, not just a multimeter continuity check.

**Stage 3 — Horn/speaker.**
Confirm the amp wiring matches the corrected understanding from earlier this window: the
`HORN_AMP_ENABLE_PIN`(4) MOSFET switches the XH-M543 amp module's **GND return path** (low-side),
not a logic enable pin (it doesn't have one) and not literally the VCC line as `WIRING_GUIDE.md` §3
item 4's current wording says — worth fixing that wording while this stage is being wired anyway.
Confirm the DFPlayer PRO has the actual deterrent audio file(s) loaded before the fire-test, then
flash and **physically listen** for the horn firing — same "don't trust the serial ack alone"
discipline as the other two stages. `HORN_AMP_ENABLE_DELAY_MS=150` is unmeasured engineering
judgement, not bench data — this is the first real chance to confirm the amp actually needs that
warm-up delay.

**Stage 4 — Combine all three actuators on the final power bus.**
Fire LED + IR + horn close together (horn is the highest single current draw) and watch for voltage
sag or brownout on the shared bus. Confirm total peak combined current still sits inside the
battery's 3C discharge rating and the revised 6A fuse's margin — this was checked on paper in the
solar/power review earlier this window, this stage is the first real measurement against a load
that actually exists.

**Stage 5 — Register `Bridge.provide()` functions one at a time, never batched.**
`drive_horn`, `drive_led`, `pulse_ir`, `get_system_state` are all still commented out — this is why
nothing has ever been actuated from the real decision loop, wiring aside. Register and test each
individually; a past batched registration broke every previously-working function, so this is a
known regression risk, not caution for its own sake. `SAFE_MODE` stays on through this stage.

**Stage 6 — Revisit the known `delay()`-blocking bug now that it's live, not theoretical.**
Actuator `delay()` calls block `loop()` for up to ~3.15s during a horn fire, silently dropping
geophone/LoRa reads during that window — documented since the 15 Aug geophone bring-up, unfixed
because nothing could trigger it for real until actuators exist. Decide fix-vs-accept for the field
trial once Stage 5 makes it observable.

**Stage 7 — One real filmed end-to-end test, `SAFE_MODE` off.**
Geophone trigger through the fusion decision to an actual horn/LED/IR response, filmed. Still the
single highest-leverage piece of evidence for both field-deployment sign-off and the Hackster
write-up — nothing before this stage substitutes for it.

**Stage 8 — Parallel-track items that don't gate Stages 1-7 but do gate an actual 10-day unattended
deployment:** LoRa hands-on debug (voltage logic-level mismatch or AT-mode hypothesis, plus the
gateway's still-unresolved EU868→IN865 band move — 868MHz is illegal in India per `CONTEXT.md`);
camera confirmed working from VIN/battery power, not just USB-C (never tested); enclosure sealing
physically confirmed, not just designed; solar panel bench-connected and load-tested if not already.

**Stage 9 — Go/no-go against the 2 Sept deadline**, using the gate criteria already given this
window (power bus verified live, all three actuators wired/fired/confirmed, one real filmed
trigger-to-deterrence cycle, LoRa working or a documented fallback decided, enclosure actually
sealed) — with the project's own documented partial-coverage fallback as the honest move if time
runs out, rather than deploying anything still untested on faith.

**Repo lineage note (new this checkpoint, correction added same session):** the user pasted
`github.com/Abhinavkrishna3211/EleTect` (no "-X") by mistake — the intended repo was, and always
is, `EleTect-X`. Kept below for the record since it is still real, useful background: it is a
separate, **public** repo, not the same repo under another name (`git ls-remote` succeeds with no auth; `EleTect-X` requires auth, consistent with its known
Private status). It is the **original EleTect submission**: built on Seeed Grove Vision AI V2 +
Xiao ESP32S3 Sense, a honeybee-buzzing-sound deterrent (not the current horn/LED/IR trio), 12
commits, and its README points directly at
`hackster.io/517317/eletect-mitigating-human-elephant-conflict-with-tinyml-31a66d`. This is very
likely the exact Hackster project page this project's "Hackster submission 13 Sept" deadline means
to **update**, not a fresh submission — worth confirming with the user before the Hackster-write-up
work starts, since an update vs. a new-project submission are different tasks. No action taken on
the old repo itself this checkpoint, informational only.

## 30 Aug, latest (git cleanup confirmed done and pushed; hyperparameter trials explicitly declined for now; physical hardware bring-up remains the sole priority)

Closing the loop on the strategic redirect above. The execution session completed exactly what was
asked, cleanly:

- **6 commits landed and pushed** (`b5e139a`..`38e909e`, `develop` now matches `origin/develop`,
  confirmed via `git rev-list --count origin/develop..develop` = 0). Push had been silently blocked
  by a `gh`/git-credential auth-context mismatch (wrong GitHub account active), not a repo problem
  — fixed with `gh auth switch`. Repo stayed Private throughout, as instructed.
- **A real secret leak was caught before it hit a commit** — `docs/VISION_MODEL_BUILD_PROMPT.md` had
  the live `EI_API_KEY` prefix and a full plaintext Roboflow key in prose. Redacted, verified clean
  with two grep sweeps. Worth remembering: this repo is Private-on-free-tier, so GitHub's own
  secret-scanning is not running — the manual grep step is the only backstop, keep doing it on every
  future commit into this repo, not just this one.
- **Repo health check, all clean**: Private confirmed, not archived/disabled, 0 open issues/PRs,
  collaborators = just the owner, CI green on the last 6 runs. `main` is 18 commits behind `develop`
  — real but explicitly not fixed this pass (not asked for, not urgent while the repo is Private and
  has no other viewers) — defer to right before the Hackster visibility flip.

**Explicit decision on the 6 untried hyperparameter axes (freeze-backbone, augmentation strength,
resolution retry on YOLO-Pro, LR/batch size, early-stopping epoch, validation split): declined for
now, not deferred-and-forgotten.** The execution session correctly did not treat "stop, this is
cleanup not new work" as license to launch these on its own, and asked explicitly. Answer: don't run
them. Every axis already tried has independently plateaued, the ≥92% bar likely needs more
domain-matched Elephant data rather than more tuning on the current corpus, and there are ~3 days
left before the 2 Sept trial with zero physical hardware wiring done. This stays a documented,
prioritized backlog item (see `ml/vision/README.md`'s "Hyperparameter axes never actually swept"
section for the priority order if it's ever picked back up) — not something to spend trial-prep time
on.

**`main` 18 commits behind `develop`: also declined for now**, same reasoning — cheap but not free
(context switch, another verification pass), not blocking anything while the repo is Private. Do
this right before flipping visibility to Public ahead of the Hackster submission, as one combined
step.

**The instruction stands unchanged a third time: all remaining time goes to physical hardware
bring-up**, per the order in the checkpoint immediately below. Vision-model work (tuning, dataset
work, git hygiene) is fully paused, not just deprioritized — nothing in that category should resume
before either the 2 Sept trial happens or someone explicitly reopens it.

## 30 Aug, later (planning-session strategic redirect: STOP vision tuning, pivot everything to physical hardware bring-up — 2 Sept field deployment is ~3 days out and zero actuator-wiring progress has been reported since 26 Aug)

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
   13 Sept (moved from 30 Aug — see CONTEXT.md §10, updated same day).** **Superseded 2 Sept: the
   field-deployment date is now 5 Sept** — user-confirmed 1 Sept, an instruction that never reached
   the written record until now. Hackster stays 13 Sept. The 26 Aug text above is left as written
   because it is a dated record; `CONTEXT.md` §10 is the live source of truth for deadlines. Field deployment is now the
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
| 0008 | proposed, **3** bench measurements pending | MPU stays in deep suspend (not poweroff) between events, ~0.42-0.45W continuous — **but suspend is not implemented and that figure is third-party; likely as-built idle ~3.3W, see the ADR's 2 Sept addendum** |
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
