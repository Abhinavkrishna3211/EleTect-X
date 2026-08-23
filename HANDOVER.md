# EleTect X — Handover (last updated 23 Aug 2026 — the two-class FOMO vision model (Elephant + Boar)
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

## RESUME HERE — 23 Aug account-switch checkpoint (planning/Cowork session)

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
