# Boar detection gap — session notes (3 Sept 2026)

Running note for the "close the Boar detection gap" work
(`C:\Users\abhin\.claude\plans\task-close-the-boar-woolly-wadler.md`). Every real
number produced this session lives here first; findings are folded back into
`docs/KNOWN_GAPS.md`, `TRIAL_READINESS_PLAN.md` and `HANDOVER.md` separately —
this file is the source they cite, not a duplicate of them.

## Step 0 — vision runner supervision (closed)

- Runner was down at session start (board rebooted 07:04, runner is host-side
  and started by hand — the container restart policy fixed earlier does not
  reach it).
- Restarted by hand, confirmed `GET 127.0.0.1:1337/api/info` — project 1097972,
  labels `Boar`/`Elephant`, `min_score 0.05`, 96×96×3 input.
- Two-layer supervision added and verified on real hardware:
  - `eletect-x-vision-runner.service` (user systemd unit, `Restart=always`,
    `RestartSec=5`, `loginctl enable-linger arduino`) — killed the process,
    confirmed respawn and a 200 from `/api/info` after ~10s cold-load.
  - `scripts/eletect-x-watchdog.sh` gained a `check_vision_runner()` probe on
    port 1337, reusing the script's own grace-period/state-file machinery,
    independent of the existing container check. Forced a past-grace hang,
    confirmed the log lines and the actual `systemctl --user restart`.
- Committed in `bd24f87` (unit + installer + watchdog) and `522675e` (doc
  hygiene, below). `deployment/install/.gitkeep` removed (superseded).

## Doc hygiene (closed)

Committed in `522675e`:

- `device/mpu/perception/detector.py` — `min_score 0.5` → `0.05` in both
  places (module docstring, `Detection.confidence` field docstring), dated
  and cited against the live `/api/info` readback above.
- `scripts/edge_impulse_train_vision.py` — module docstring rewritten:
  three-class object-detection impulse (not two-class FOMO), project ID
  `1097972` (not `1094260`), real dataset counts (4,094 Elephant / 7,394
  Boar — the ratio has inverted since the docstring was written), real
  invocation flags (`--family yolo-pro --yolo-variant no_attn_relu
  --yolo-sizing medium`).
- `docs/KNOWN_GAPS.md` — dated append after the stale 29 Aug nano entry,
  recording the champion: Boar recall 0.852, Elephant recall 0.906,
  background FP 0.166, `no_attn_relu`/`medium`, threshold 0.05. Dated append
  closing the runner-supervision gap, describing both layers above.
- `ml/vision/README.md` — title and intro corrected to YOLO-Pro (not FOMO);
  project ID corrected; headline Dataset table replaced with a verified
  15-source breakdown pulled directly from `ml/vision/dataset_manifest.json`.
- `TRIAL_READINESS_PLAN.md` (local-only, not committed) — nano→medium
  correction; runner-supervision and `/api/info` items checked off.

## Workstream 1 — per-class consecutive-poll debounce

### The change

`device/mpu/services/config.py`: new `VISION_SPECIES_CONSECUTIVE_POLLS:
dict[str, int] = {"Boar": 2}`, default 1 (no-op) for any unlisted label —
Elephant included.

`device/mpu/services/reflex_loop.py`: `_watch_for_vision`'s loop now tracks
a per-label `species_streaks` counter, reset to 0 on any poll where the
label is absent, incremented on any poll where it's present; a label enters
`seen_species` (and stays there) only once its streak reaches
`_required_consecutive_polls(label)`. `check.confirmed` and the
early-return-on-confirmation path are untouched — this gates `species`
entry only, exactly as scoped.

### Test suite

Fixed the one pre-existing test whose premise the change invalidated
(`test_a_boar_only_event_keeps_its_video_when_boar_is_configured` —
single-poll `_fire()` default can never meet Boar's new N=2 requirement; gave
it a real multi-poll window via `vision_watch_base_s=0.05,
vision_watch_poll_interval_s=0.0`, which free-runs the loop against the real
clock with a fake detector/camera that both return instantly, so it clears
2 polls in a few milliseconds without needing a clock-injection hook that
`_fire()`/`handle_footfall_event` don't have).

Added 6 new tests against `_watch_for_vision` directly (`_ScriptedVisionDetect`
+ the existing `_watch()`/`_Clock` harness): isolated single Boar poll (not
admitted), two consecutive Boar polls (admitted from the 2nd), alternating
Boar/empty/Boar (streak resets, never admitted), sustained Boar (admitted
once, stays admitted), Elephant single-poll (admitted immediately,
`confirmed_on_poll` unchanged — the no-op regression guard), and interleaved
Boar/Elephant (independent per-label counters).

Full suite: **368 passed, 1 skipped** (pre-existing skip, unrelated).
`ruff check .`: clean. The existing watch-mechanics tests (`polls`,
`confirmed_on_poll`, `elapsed_s`, `clock.sleeps` assertions) needed **no**
edits — the proof that N=1 Elephant is genuinely a no-op.

### The real before/after number — `scripts/replay_boar_aggregation.py`

Written and run **on the board over SSH** against
`/home/arduino/monitor_2h_20260830.log` (138.5MB, 1,169,788 lines, 40,422
classified frames across 13 runner-restart chunks) — aggregated there, never
copied down. Runtime: 4.4s.

Three metrics, per the plan's methodology:

| Metric | Value |
|---|---|
| A. Frame baseline (any Boar box) — reproduces the published number | **12,747/40,422 = 31.53%** ✓ matches `ml/vision/README.md`'s 30 Aug entry exactly |
| B. Per-frame N≥2 (debounce applied to raw frames, not production's actual unit) | 11,031/40,422 = **27.29%** |
| C0. Production-faithful poll baseline — burst-OR across 3-frame polls, **before** the N≥2 gate | 2,942/6,742 = **43.64%** |
| C. Production-faithful N≥2 — **what `_watch_for_vision` actually produces** | 2,729/6,742 = **40.48%** |

Elephant no-op guard: **0% at every stage**, frame and poll, baseline and
debounced (0/40,422 and 0/6,742 throughout). Confirms the change costs
Elephant nothing, as designed.

**This is the honest, sobering result the plan flagged as a real
possibility and told me not to paper over.** Burst-OR *does* amplify the
positive rate exactly as warned (31.53% frame baseline → 43.64% poll
baseline, before any debounce is even applied) — not as badly as the
naive independence estimate (~68%, which assumed frame positives are
uncorrelated), consistent with real Boar false positives being spatially
clustered on fixed background anchors rather than independent per frame,
but still a large jump in the wrong direction. And the N≥2 poll debounce
this session implemented barely dents it: **43.64% → 40.48%**, a 3-point
drop, versus the frame-level metric's much larger 31.53% → 27.29% (a
4-point drop that undersells it — see below) or the *within-run* reduction
visible per chunk.

Per-chunk spread makes the mechanism visible. Low-baseline chunks benefit
a lot from N≥2 (chunk 1: baseline 5.37% → frame-N≥2 1.18%, a ~78% relative
cut; poll baseline 14.54% → poll-N≥2 6.29%, a ~57% cut). High-baseline
chunks benefit almost none (chunk 2: baseline 73.94% → frame-N≥2 68.15%;
poll baseline 93.22% → poll-N≥2 92.05% — essentially unchanged, because
when the underlying frame rate is that high, nearly every poll's 3-frame
burst is already positive, and consecutive positive polls are the norm,
not the exception). The overall aggregate is dominated by the chunks
where the FP rate is worst — exactly the chunks a debounce is supposed to
help — pulling the blended number down to a disappointing net result.

**Reading this straight, per the plan's own decision criterion:** N=2
consecutive-poll debounce, as implemented, does **not** materially fix
the Boar false-positive problem at the level that actually matters for
`species` admission in production (poll level, burst-OR'd). Full per-chunk
table and the script are checked in; rerun any time with
`python3 scripts/replay_boar_aggregation.py <log>` on the board.

**Follow-up measurement — the plan's named alternative.** Reran with
`--within-burst majority` logic added to the script (2-of-3 frames must be
positive, instead of any-of-3): **D0. majority-burst poll baseline
(no debounce at all) = 2,070/6,742 = 30.70%** — already lower than the
OR-based baseline (43.64%), and lower than OR-with-N≥2-debounce (40.48%).
**D. majority-burst + N≥2 poll debounce = 1,857/6,742 = 27.54%** — back in
line with the frame-level baseline (31.53%) and with Metric B's
frame-level N≥2 result (27.29%), rather than the inflated poll-level
numbers OR produces.

This confirms the plan's own hypothesis exactly: **OR-across-the-burst is
the mechanism doing the damage, not an absent poll debounce.** Switching
the burst aggregation from "any of 3" to "majority of 3" recovers most of
the loss on its own (43.64% → 30.70%, before any poll-level debounce at
all); adding the already-implemented N≥2 poll debounce on top of majority
gives a further, more modest cut (30.70% → 27.54%, roughly the same
~10-13% relative reduction N≥2 gives the frame-level baseline) rather than
the near-nothing it gives on top of OR (43.64% → 40.48%).

**This changes the shape of Workstream 3.** The plan's own text anticipated
exactly this outcome and left it undecided pending this number: *"If the
production-faithful number does not improve materially on 31.53%, the
finding is that burst-OR semantics is itself the problem and the fix needs
a within-burst requirement (e.g. majority of the 3 frames) rather than only
more polls."* That is what was measured.

### The implementation — per-label, not blanket

Decided: majority-of-3 within a burst, but scoped per label, mirroring
`VISION_SPECIES_CONSECUTIVE_POLLS`'s own shape rather than applied
uniformly. `device/mpu/services/config.py` gained
`VISION_SPECIES_BURST_MAJORITY_LABELS: tuple[str, ...] = ("Boar",)` —
default one-frame-is-enough (today's OR) for any unlisted label, Elephant
included.

The reasoning for scoping it, not applying it everywhere: Elephant's
measured recall (0.906) is already below the ≥92% field-readiness bar, and
majority-of-N trades recall for precision — the wrong direction for the
class where a missed real detection, not a false one, is the
safety-relevant failure. The same 2-hour run that found Boar's 31.53%
false-positive rate found *zero* Elephant false positives, so there is no
Elephant precision problem to trade against. Boar's problem is precision,
not recall, so gating only Boar is a clean win with no offsetting cost.

`device/mpu/perception/detector.py`'s `VisionDetectFn` Protocol changed
from `list[Detection]` to `list[list[Detection]]` — per-frame attribution,
which a within-burst gate cannot exist without. `HttpVisionDetector`
appends one entry per image (`[]` on a per-image failure, not a dropped
frame) instead of flattening every box into one list; `DetectionError` is
raised only when every image in a non-empty burst failed.

`device/mpu/services/reflex_loop.py`'s `_vision_check()` computes, per
poll, how many of the burst's frames carried each label, then gates each
label independently: a majority-listed label needs `count * 2 > burst_size`
(strict majority — a tie does not qualify); every other label needs
`count >= 1`, identical to the pre-existing flat-OR behaviour. This governs
`species` membership *and* `confirmed` *and* the fused reading alike — a
rejected label contributes no positive evidence, falling back to
`BASELINE_VISION` exactly as "no qualifying detection" already did.

Test suite: `_FakeVisionDetect` now broadcasts its detections to every
frame in the burst (`[self._detections] * len(images)`); `_ScriptedVisionDetect`
gained a dual mode — a flat list broadcasts to every frame in that call,
a list of lists is passed through as explicit per-frame data, for tests
that need a label on only some of a burst's frames. Four new tests added
directly against `_vision_check()` (Boar on 1-of-3 frames excluded from
both `species` and `confirmed`; Boar on 2-of-3 admitted and confirms;
Elephant on 1-of-3 still counts, the regression guard; a majority-rejected
Boar poll's reading falls back to `BASELINE_VISION`, not the detector's
raw confidence), on top of the six debounce tests already written. Full
suite: **372 passed, 1 skipped**, `ruff check .` clean.

**Elephant's poll-level numbers are unchanged, confirmed against the same
replay already run, not a new one.** `scripts/replay_boar_aggregation.py`
computes Elephant's A/B/C0/C metrics via plain OR
(`_poll_positives(c.elephant, stride)`, `majority=False`) unconditionally
— its Boar-only `--within-burst majority` alternative (D0/D) never touches
the Elephant computation, which is exactly the per-label split just built
into production. Elephant was 0% at every stage in both board runs already
recorded above (frame baseline, per-frame N≥1, poll baseline, poll N≥1) —
that is the real number for the shipped per-label implementation, not an
assumption extrapolated from a differently-scoped run.

This confirms the plan's own hypothesis exactly: **OR-across-the-burst is
the mechanism doing the damage, not an absent poll debounce.** Switching
Boar's burst aggregation from "any of 3" to "majority of 3" recovers most
of the loss on its own (43.64% → 30.70%, before any poll-level debounce at
all); adding the already-implemented N≥2 poll debounce on top of majority
gives a further, more modest cut (30.70% → 27.54%, roughly the same
~10-13% relative reduction N≥2 gives the frame-level baseline) rather than
the near-nothing it gives on top of OR (43.64% → 40.48%) — while Elephant
keeps its original OR sensitivity throughout, at zero measured cost.

Workstream 1 — the debounce and the majority gate together — is now
committed as the real fix; the code is correct, tested against the real
2-hour log, and scoped to the class that actually has the problem.

## Workstream 3 — per-node tri-state deterrence scope

Sequenced strictly after Workstream 1 landed (`596b432`), per the plan: the
confirmation path bypasses the debounce entirely until this workstream closes
that hole (see "the finding that makes the ordering non-negotiable" below).
Everything in this section is uncommitted at the time of writing — `config.py`,
`reflex_loop.py`, `cognition/config.py`, `main.py`, three test files, one new
ADR, one new research doc. Commit is the next step after this note.

### The confirmation-path bypass — why Workstream 1 alone was not enough

`_vision_check` computes `confirmed` by intersecting raw detections with
`DETERRENT_TARGET_LABELS`; `_watch_for_vision` returns immediately on the
first `check.confirmed`. Workstream 1 debounces `seen_species` only — the
confirm-and-exit path was, and had to stay, untouched for Elephant. So the
moment Boar enters `DETERRENT_TARGET_LABELS` (`boar_only` or `both`), a
single spurious Boar box on a single poll confirms, exits the watch, and
fires the horn — against a measured ~31-44% poll-level Boar FP rate
(Workstream 1's own numbers, above), not a corner case.

Fix: the streak gate now also gates confirmation. Each poll, after the
per-label streak counters update, the confirming labels are
`check.species` intersected with `target_labels`. The early return is taken
only once a confirming label has met its required streak (Elephant's is 1,
so it is unchanged - confirms on the poll it first appears,
`confirmed_on_poll`, `elapsed_s`, `clock.sleeps` and the fired tier all
bit-for-bit identical to before). A streak-rejected poll no longer
contributes `_confidence_log_odds(best_confidence)` to `fuse()` - it is
downgraded to the same `BASELINE_VISION` reading a poll that saw nothing
contributes. This was flagged in the plan as the part most likely to be got
wrong silently; it has its own direct test (prior segment) plus this
segment's end-to-end confirmation that no horn call, no kept video, and no
positive fusion evidence result from a single spurious poll (below).

### Config shape

`services/config.py`, in the "Node site attributes" section beside
`NODE_HOUSEHOLD_PROXIMITY` (ahead of `EXPERIENCE_DB_PATH`, which derives from
it):

```python
NODE_DETERRENCE_SCOPE = os.environ.get("ELETECT_DETERRENCE_SCOPE", "elephant_only")
```

`deterrence_scope_labels(scope) -> (deterrent, video)` resolves all three
states explicitly (`elephant_only` / `boar_only` / `both`); an unrecognised
value logs a warning and falls back to `elephant_only`, never raises.
`DETERRENT_TARGET_LABELS, EVENT_VIDEO_TARGET_LABELS =
deterrence_scope_labels(NODE_DETERRENCE_SCOPE)` - at the shipped default this
resolves byte-for-byte to `("Elephant",)` for both, same as before this
change; only the assignment is rewritten, not the value. `NODE_HOUSEHOLD_PROXIMITY`
got the identical env-first treatment (`ELETECT_HOUSEHOLD_PROXIMITY`) in the
same commit, for the same reason - it is the same class of setting with the
same deployment-day config-delivery gap (see fold-back below).

`EXPERIENCE_DB_PATH` now derives from scope: `experience.sqlite3` at
`elephant_only`, `experience-{scope}.sqlite3` otherwise (named by scope, not
by phase - `experience-both.sqlite3`, not `experience-home.sqlite3`) - so
reverting the flag is the same action that restores the trial's bandit DB,
with no separate archive step to forget. `main.py`'s startup banner now logs
`NODE_DETERRENCE_SCOPE`, both derived label tuples, and `EXPERIENCE_DB_PATH`
together, specifically so a mid-trial scope flip (which would silently swap
which learned policy the node is running) is visible in the boot log rather
than invisible.

### Boar horn content - `cognition/config.py`

`resolve_tier_action(tier, rng, household_proximity, species="Elephant")` -
every existing call site and test unaffected by the new default. Boar Tier 1
reuses the lion track (Freesound 212764, CC-BY 3.0, ADR 0016 Decision C),
Tiers 2/3 reuse the tiger track (Freesound 149190, CC-BY 4.0) - both already
provisioned on the DFPlayer's onboard flash, so no new sourcing, no
reprovisioning, no `SCHEMA_VERSION` bump. No bee track on any Boar tier
(King et al. 2007's aversion mechanism - stinging near eyes/trunk - has no
boar analogue), so Boar's tier ladder has one fewer content axis than
Elephant's, stated as such rather than smoothed over.

### Tests

7 direct unit tests on `deterrence_scope_labels`/DB-path derivation (prior
segment, `test_config.py`), 5 on `_deterrence_species` (prior segment,
`test_reflex_loop.py`), 7 on the Boar tier content / no-bee-track guarantee
(prior segment, `test_cognition_config.py`), plus one direct streak-downgrade
test (prior segment, `test_reflex_loop.py`).

This segment added the four end-to-end (`_fire()`-level) behavioural tests
the plan's Testing section named explicitly, under the
`# --- end-to-end tri-state scope (ADR 0023, NODE_DETERRENCE_SCOPE) ---`
heading in `test_reflex_loop.py`:

- `test_a_single_spurious_boar_poll_fires_nothing_even_under_boar_only` - one
  Boar poll followed by an empty streak (`_ScriptedVisionDetect([[BOAR], []])`
  under a free-running window) fires no `drive_horn`/`drive_led`, keeps no
  video, contributes no positive fusion evidence.
- `test_two_consecutive_boar_polls_fire_the_deterrent_and_keep_the_video` -
  two consecutive Boar polls do all three.
- `test_elephant_still_fires_on_the_first_poll_under_the_both_scope` -
  Elephant still confirms on poll 1 under `both`; the new confirm gate costs
  Elephant nothing.
- `test_boar_fires_nothing_under_the_shipped_elephant_only_default_at_any_streak_length` -
  Boar fires nothing under the shipped default regardless of streak length.

All four passed on the first run - the probability/sta_lta_ratio calibration
(weak seismic trigger, `probability=0.05, sta_lta_ratio=1.2`, insufficient
alone but carried past the 0.5 alert threshold by a genuine confirmation at
ELEPHANT/BOAR's fixture confidences of 0.9/0.99) was derived from reading
existing fixture comments rather than by trial-and-error.

Full-suite result after this segment's edits: **398 passed, 1 skipped** (399
collected). `python -m ruff check .`: **all checks passed.** (`ruff` alone
was not on PATH in this shell; `python -m ruff` was used instead - an
environment quirk, not a code finding.) Existing watch-mechanics tests
(exact `polls`/`confirmed_on_poll`/`elapsed_s`/`clock.sleeps` assertions)
needed no edits - the proof that Elephant's N=1 default really is a no-op
through both the debounce and the confirm-gate changes.

### ADR 0023 and the research doc

`docs/decisions/0023-boar-deterrence-content-and-node-species-scope.md` (new,
`proposed`) covers all four decisions: A (tri-state scope + env-first
delivery for both `NODE_DETERRENCE_SCOPE` and `NODE_HOUSEHOLD_PROXIMITY`), B
(the confirmation-path streak-gate fix, described as the non-negotiable
finding), C (Boar horn content, full evidence-tier honesty), D (experience-DB
path derivation and the mid-trial-flip hazard).

`docs/research/boar-deterrence-behavioral-science.md` (new) is the boar
counterpart to the existing elephant review - same confidence-labelling
convention. Covers Widen et al. 2022 (triggered predator-call playback
reducing boar crop damage, the primary evidence), tiger/leopard as real
Sus scrofa predators on the Indian subcontinent (Bardia NP Nepal, 6.98%
tiger / 15.72% leopard diet biomass; Nagarjunasagar Srisailam, boar the most
common prey item by scat analysis), what wild boar can hear (Heffner &
Heffner 1990, 42 Hz-40.5 kHz, best sensitivity 250 Hz-16 kHz - pig, not
wild-boar-measured directly) and see (Neitz & Jacobs 1989, dichromatic
439/556 nm - also pig, no implication for this design since Boar's LED
patterns are unchanged).

**A correction worth recording as its own finding.** The plan, and the first
draft of ADR 0023's Decision C, stated a direct boar-specific
light-vs-sound comparison - a Hunchun, China cornfield study - was
"inaccessible behind a paywall and bot-protection on every path tried, and
was not read." Per this project's own verify-before-declaring-blocked
discipline, that was re-attempted this segment rather than carried forward
as fact, and the study turned out to be freely readable via PMC (a redirect
from the `ncbi.nlm.nih.gov/pmc/articles/` URL form to
`pmc.ncbi.nlm.nih.gov/articles/PMC11987724/`): Ani (2025) 15(7):1017,
"Comparing Durations of Different Countermeasure Efficacies Against Wild
Boar (Sus scrofa) in Cornfields of Hunchun, Jilin Province, China," DOI
10.3390/ani15071017. Real numbers, not assumed: red solar blinkers lasted
32.25±4.22 days before efficacy declined (best single treatment); electric
fencing 29.67±0.58; Amur tiger calls + wild boar distress calls 26.50±2.38 -
category ranking tactile (152.56) > visual (118.29) > auditory (72.60).

That is genuine new information, but reading it as "light beats sound for
this device" would be a paradigm-mismatch error, and both the ADR and the
research doc say so explicitly: every Hunchun treatment ran as continuous,
unconditional exposure across weeks, which is exactly the condition Widen et
al. 2022's own triggered-camera-trap design exists to avoid, and exactly the
condition this device's own triggered-once-per-confirmed-encounter horn
(ADR 0022's watch window) is not. The honest reading is "continuous auditory
broadcast habituates faster than continuous visual broadcast in this
environment" - a finding about exposure schedule, not a verdict on triggered
predator-call playback, which Hunchun did not isolate as its own condition.
What the correction does add directly: a real, quantified, actual-Amur-
tiger-call-on-actual-wild-boar result (26.5 days measured efficacy) behind
ADR 0023's tiger track, stronger than the ecological-inference argument
(Section 2 of the research doc) alone. `cognition/config.py`'s Boar-content
rationale comment, the ADR's Decision C evidence paragraph, and the ADR's
Follow-ups list were all updated to reflect this rather than left carrying
the stale "unread" placeholder - the Follow-ups gap is now stated precisely
as "a triggered-paradigm boar-specific light-vs-sound comparison," since
Hunchun answers the continuous case, not this one.

### Ship-day state

`elephant_only` is the committed default everywhere this segment touched:
`services/config.py`'s constant, every test default, and (once `main.py`'s
banner is committed) the startup log. Nothing in this workstream enables
`boar_only` or `both` live. The three preconditions the plan named as
separate from the flag - `ELETECT_SAFE_MODE=0` (never yet done on the
board), `EVENT_VIDEO_ENABLED=True` (still `False` by default, plausibly
flippable now that `0094b91`/`aa41fb2` landed against real hardware in the
other session, not yet confirmed with them), and the runner up and
supervised (closed, Step 0 above) - remain the actual gate on getting real
boar-deterred footage, not this flag by itself.

## Exposure-lock write-up (closed) and Workstream 2 (still deferred)

**Exposure-lock finding, closed.** Cross-referenced into both places the
plan named, write-up only, no implementation (the camera-control code
belongs to the other session): `docs/KNOWN_GAPS.md`'s Boar false-positive
entry now has a dated append naming the auto-exposure/AGC finding from
`docs/qa/night-ir-led-characterisation.md` as a plausible contributor to
both the Boar FP rate and the 2-hour run's unexplained per-chunk swing, and
`ml/vision/README.md`'s 30 Aug 2-hour-run section got the matching append,
plus closing out its own two named next steps: (1) the N≥2 temporal-
aggregation lever - done, this is Workstream 1, real numbers above; (2)
true-negative training data from this scene - explicitly not done, folds
into the still-deferred Workstream 2 gap below. Both cross-references state
the real implementation blocker already on record on the other side: the
container's camera path doesn't accept exposure writes and sits frozen,
unlike the host V4L2 path.

**Workstream 2 — not started this session.** Docs-only (Boar representation
audit + sourcing plan, no retrain), explicitly sequenced behind the 5 Sept
ship date per the plan. `ml/vision/boar-representation-audit.md` does not
exist yet. The real gap it would characterize is already known and
quantified from the 30 Aug/2 Sept work referenced above and in
`ml/vision/README.md`: real night/IR Boar imagery is 64 images out of
7,394 (0.87%), the only genuinely IR-labelled source is
`pig-rinoz/wild-pig-at-night`, and Boar's weak recall (0.852 vs the ≥92%
bar) is a domain-match problem, not a volume problem — Boar already
outnumbers Elephant 7,394 to 4,094. SA-FARI (Conservation X Labs x Meta,
arXiv 2511.15622) remains the lead sourcing candidate, blocked on two
unchecked items: confirming *Sus scrofa* is actually in its 99-species
table, and reading its actual redistribution licence rather than trusting
site copy. Neither check was run this session.

## Exposure lock — implemented, not just written up (3 Sept, later)

The plan's own constraint above ("camera-control code belongs to the other
session") stopped holding: the other session was no longer active, and the
user explicitly authorized implementing the fix here, plus starting
Workstream 2 ahead of its planned post-ship sequencing. Both decisions are
the user's, not inferred. This section supersedes the "closed, write-up
only" framing above for the exposure-lock item specifically; the KNOWN_GAPS
and README cross-references were rewritten in place (dated-append
convention still followed — nothing above was deleted, only the live entry
was updated to its current state) rather than left contradicting this.

**Live re-test before writing any code.** Before touching `camera.py`,
re-ran the exact scenario `night-ir-led-characterisation.md` documents as
blocked ("the container's camera path does not accept exposure writes, and
sits frozen at 156") — same container, same device, `docker exec` as the
real `arduino` app user, no `-u` override. Result: `cv2.CAP_PROP_AUTO_EXPOSURE`
(1, Manual) and `cv2.CAP_PROP_EXPOSURE` (256) both `set()` successfully,
and read back as 1.0/256.0, with a subsequent frame read succeeding. This
does not reproduce the documented finding — recorded here as a re-test
correction, not a claim the original write-up was wrong when it was made.

**Unrelated live bug found and fixed during that same check.** The camera
was already sitting in Manual Mode at exposure 2000 — not the documented
auto default — almost certainly a leftover from the 1-2 Sept
`night_char.py` characterisation session that was never reset, and it had
survived an intervening reboot. Reset live to auto-exposure (`value=3`) via
the same `docker exec` path, verified two ways: the in-container read-back
(3.0) and an independent host-side `v4l2-ctl -d /dev/video0 --list-ctrls`
check (`auto_exposure ... value=3 (Aperture Priority Mode)`). This is
exactly the class of bug `_assert_auto_exposure()` (below) now prevents
from recurring silently.

**What was built.**

- `services/config.py`: `NIGHT_LOCKED_EXPOSURE = 256` (Finding 4's own
  ladder — treeline sharpness gain peaks here, zero clipping through the
  32-512 sweep) and `NIGHT_EXPOSURE_LOCK_ENABLED` (`ELETECT_NIGHT_EXPOSURE_LOCK`,
  default on) — an independent kill switch, since the only field
  verification is a static, empty scene; motion blur on a moving animal and
  daytime behaviour under a lock are both still unmeasured.
- `perception/camera.py`: `Camera._assert_auto_exposure()` runs at every
  `open()`, forcing the auto default before warmup — the direct fix for the
  stale-state bug just found. `Camera.lock_night_exposure(value=256)`
  switches to manual mode and verifies the write by read-back rather than
  trusting `set()`'s return value; never raises, returns `False` on a
  disabled flag, a write that didn't stick, or any error, and callers
  treat `False` as "continue on whatever exposure mode the camera already
  had."
- `services/reflex_loop.py`: `CameraProtocol` gained `lock_night_exposure()`.
  `handle_footfall_event`'s IR-pulse gate now calls
  `camera.lock_night_exposure()` right before the IR thread starts and
  before the evidence burst — the exact night+fire_ir combination Finding 4
  identifies as the false-positive source. `camera.open()` is guaranteed to
  have already succeeded whenever this runs.
- `perception/video.py`: `EventVideoRecorder.lock_night_exposure()` added
  to satisfy the same Protocol, but as an honest no-op — this class rebuilds
  its GStreamer pipeline fresh from a `Gst.parse_launch` string on every
  event, with no persistent capture handle a later `set()` could reach.
  A real fix would mean either baking exposure into `v4l2src`'s own
  `extra-controls` at pipeline-build time (locks the *whole* recording, not
  just the evidence burst — an unevaluated trade-off) or a live
  element-property change on an already-PLAYING pipeline (unverified on
  this hardware). Neither was attempted; both need their own hardware
  verification this session did not do. Harmless today since
  `EVENT_VIDEO_ENABLED` defaults `False` and nothing opens this class in
  production yet.

**Tests and regression bar.** `tests/test_camera.py`: extended `_FakeCapture`
with exposure/auto-exposure state (default auto=3/exposure=156, matching
this camera's real documented defaults), plus knobs for a write that
reports success but doesn't stick and a write that raises — 9 new tests
covering `_assert_auto_exposure` (asserted at open, and that a raising
write doesn't block open) and `lock_night_exposure` (success+readback,
config default, silent-failure readback, raising control, disabled via
kill switch, before-open/after-close). `tests/test_video.py`: 3 new tests
for `EventVideoRecorder.lock_night_exposure()` — always `False`, and the
same before-open/after-close contract as its other methods.
`tests/test_reflex_loop.py`: `_FakeCamera` gained `lock_night_exposure()`
(private call counter, not the shared `call_log` — its position isn't part
of any existing ordering assertion, and logging it there would have shifted
every `log[n]` index 14 existing tests already check); 5 new tests assert
the lock fires exactly on night+fire_ir (including the is_night()-raised
path, which forces night=True), and does not fire on daylight,
undetermined night, or tier 1 (no IR).

Full bar: `ruff check .` clean across `device/mpu`; `pytest` 415 passed, 1
skipped (same pre-existing skip as before this work) — the whole suite,
including every watch-mechanics/ordering test, needed zero edits beyond the
fake completing the Protocol contract, which is the same "no leaked
behaviour" signal Workstream 1's N=1 Elephant no-op provides.

**What this is not.** Implementing the mechanism is not the same as a fresh
measured field number: the "locked exposure suppresses Boar FPs" result
still rests on the original 1-2 Sept `night_char.py` battery, not a new run
against this code path. No live night characterisation battery was re-run
this session — the live camera checks above verified the V4L2 API surface
works, not the FP-suppression outcome. That remains true until someone
re-runs a battery like Finding 4's against production code with the lock
active.
