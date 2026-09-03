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

## Workstream 2, Workstream 3, exposure-lock write-up

Not started this session — sequenced after the burst-OR decision above,
per the plan's explicit ordering (Workstream 3 depends on Workstream 1
being both committed and *actually sufficient*, which this replay says it
is not, alone).
