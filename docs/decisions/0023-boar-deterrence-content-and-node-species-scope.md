# ADR 0023: Boar deterrence content, and a per-node species scope to act on it

- **Status:** proposed
- **Date:** 2026-09-03

## Context

Boar has been a detected class since the two-class ETX-V model shipped, and acted on by nothing. It is
in neither `DETERRENT_TARGET_LABELS` nor `EVENT_VIDEO_TARGET_LABELS` (`services/config.py`, both
`("Elephant",)`), so a boar box today produces a log line and stops there — no footage, no deterrent.
ADR 0022 Decision C already named "deter elephants, collect boar footage" as a one-line config change
and recommended it as the step before any horn fires at a boar at all.

Two facts, both established since ADR 0022 landed, change what "acting on Boar" can safely mean:

**A measured false-positive rate makes the naive version unsafe.** A 30 Aug 2-hour live run found
Boar boxes on 31.53% of frames with zero Elephant false positives (`ml/vision/README.md`). A companion
debounce (per-class consecutive-poll requirement, `VISION_SPECIES_CONSECUTIVE_POLLS`) suppresses this
for `watch.species` membership — but `_watch_for_vision()` returns immediately on the first
`check.confirmed`, and `check.confirmed` is computed straight off `DETERRENT_TARGET_LABELS`
intersection, unaffected by that debounce. The moment Boar enters `DETERRENT_TARGET_LABELS`, a single
spurious Boar box on a single poll confirms, exits the watch, feeds `fuse()` positive log-odds, and
fires the horn — the debounce bypassed entirely, on the modality with the worst measured false-positive
rate in the system. This ADR's confirmation-path fix (Decision B) closes that.

**The bandit's persistent policy has no species dimension.** `EXPERIENCE_DB_PATH` is one file per node,
survives redeploys, and the bandit's action values have no decay (`BANDIT_STEP_SIZE`, no forgetting
term). A node that spends two days deterring boar at a test site and is then redeployed to the field
opens the field trial running a policy shaped by boar encounters, silently. This ADR's DB-path
derivation (Decision D) makes reverting the scope also revert which policy the node reads.

The reason to want Boar acted on at all: the only real capture of boar-deterred behaviour comes from
a node with `NODE_HOUSEHOLD_PROXIMITY`-style commissioning already establishes as the shape for a
per-node site attribute — not sensed, not inferred, a fact the install team records. This ADR follows
that shape rather than inventing a second one.

## Decision A — `NODE_DETERRENCE_SCOPE`, a tri-state per-node attribute, ships flag-off

`services/config.py` gains

```python
NODE_DETERRENCE_SCOPE = os.environ.get("ELETECT_DETERRENCE_SCOPE", "elephant_only")
```

beside `NODE_HOUSEHOLD_PROXIMITY`, in the "Node site attributes" section — a commissioning-time fact,
not a label-tuple detail, even though the two label tuples are what it ultimately drives. Three states,
resolved by a pure function with no internal collapse to a boolean:

```python
def deterrence_scope_labels(scope: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    ...  # "elephant_only" -> (("Elephant",), ("Elephant",))
         # "boar_only"     -> (("Boar",), ("Boar",))
         # "both"          -> (("Elephant", "Boar"), ("Elephant", "Boar"))
         # anything else   -> warn, fall back to "elephant_only"
```

`DETERRENT_TARGET_LABELS, EVENT_VIDEO_TARGET_LABELS = deterrence_scope_labels(NODE_DETERRENCE_SCOPE)`
replace the two hand-set tuples. This rewrites those two lines but does not flip them: `elephant_only`
resolves to `("Elephant",)` for both, byte-for-byte today's shipped value, and `elephant_only` is the
committed default everywhere — config, `main.py`'s startup log, and every test default. Nothing in this
change enables `boar_only` or `both` on a live node.

An unrecognised value logs a warning and falls back to `elephant_only` rather than raising — a typo in
a per-node config file must not crash the reflex loop on a field node. `NODE_HOUSEHOLD_PROXIMITY` gets
the same env-first delivery (`ELETECT_HOUSEHOLD_PROXIMITY`), for the same reason and in the same
commit: it is the same kind of setting with the same commissioning gap (see Decision D's note on
delivery path), and fixing one without the other is how a second config mechanism gets invented by
accident later.

**One real loss of expressiveness, stated rather than hidden.** The three symmetric states do not
include the asymmetric "deter elephant, film boar" combination ADR 0022 named — that stays available as
a two-line hand edit of the two derived constants below the `deterrence_scope_labels()` call, now
reads as a deliberate override rather than the normal path, and is the honest next step for gathering
boar evidence before any horn fires at one.

## Decision B — the confirmation path must honor the same streak `species` does

Extending `target_labels` to admit Boar without this fix reopens exactly the bypass described in
Context. `_watch_for_vision()` now tracks per-label streak counters (Workstream 1's
`VISION_SPECIES_CONSECUTIVE_POLLS`) *before* the confirmation check, and gates the early-return
confirmation on the same counters `seen_species` uses — a poll's raw `check.confirmed` is accepted only
once at least one of its confirming labels has cleared its own required streak.

Elephant's required streak is 1, so it is unaffected: it still confirms and exits on the poll it first
appears, `confirmed_on_poll`, `elapsed_s`, `clock.sleeps` and the fired tier all bit-for-bit unchanged.

**The rejected poll downgrades, it does not simply not-confirm.** `_vision_check()` returns the
detector's own confidence as log-odds whenever a target label matched, confirmed or not. Carrying that
value forward as the poll's contribution to `fuse()` would let one spurious Boar frame push positive
evidence into the fused probability even though no deterrent fired — a quieter version of the same
bypass. A streak-rejected poll instead contributes the available-but-unconfirmed `BASELINE_VISION`
reading, identical to a poll that saw nothing. This is the subtlest part of the change and has its own
direct tests (`tests/test_reflex_loop.py`, "confirmation-path streak gate").

## Decision C — Boar horn content reuses Elephant's predator-growl tracks, no new sourcing

`cognition.config.resolve_tier_action(tier, rng, household_proximity, species="Elephant")` gains
`species`, defaulting to `"Elephant"` — every existing call site and test is unaffected, verified by a
regression test comparing implicit- and explicit-`"Elephant"` calls against identically-seeded RNGs.

For `species="Boar"` (only reachable once `NODE_DETERRENCE_SCOPE` admits Boar):

- **Tier 1 → lion roar** (`HORN_CONTENT_LIBRARY[HORN_CATEGORY_PREDATOR][1]`, Freesound 212764, CC-BY
  3.0), fixed, not drawn.
- **Tiers 2 and 3 → tiger roar** (`HORN_CONTENT_LIBRARY[HORN_CATEGORY_PREDATOR][0]`, Freesound 149190,
  CC-BY 4.0), fixed, not drawn. Tier 3's LED pattern still rotates
  (`rng.choice(TIER_3_LED_PATTERN_IDS)`) — the escalation axis that stays species-agnostic.

Both tracks are already provisioned on the DFPlayer's onboard flash for Elephant's own Tier 2/3
rotation (ADR 0015 Decision D, ADR 0016 Decision C), and both attribution obligations are already
carried by those ADRs. **No new audio, no `SCHEMA_VERSION` bump.**

Two content-axis reductions from Elephant's ladder, both deliberate:

- **No bee-swarm track on any Boar tier.** King et al. 2007's documented elephant aversion is bees
  stinging around the eyes and trunk specifically — there is no boar analogue, so Boar's Tier 1 gets
  the milder of the two predator-growl clips (lion) instead of a fabricated bee-response claim.
- **No firecracker/air-horn bang pool at Boar's Tier 3.** Every Boar tier stays inside the
  predator-growl category. This is also why the household-proximity gate (ADR 0016 Decision B: never a
  bang near a resident's home) is satisfied trivially for Boar rather than needing its own branch —
  there is no non-predator pool for it to gate in the first place. `household_proximity` still gates
  Boar's Tier 3 LED-pattern draw exactly as it does for Elephant.

**Evidence base, stated at the same standard the bee exclusion above is held to.** Widén et al. 2022
(*Agriculture, Ecosystems and Environment* 328:107853) found camera-trap-triggered predator-vocalization
playback reduced crop damage across five ungulate species including wild boar, in a field design
methodologically close to this device's own — real, relevant, and boar-specific. **But its stimuli were
wolf howl, dog bark and human voice, not tiger or lion.** Reusing Elephant's tracks 2/3 for Boar is not
a replication of that result — it rests on a separate, ecological argument: tiger and leopard are real
predators of *Sus scrofa* on the Indian subcontinent, so the playback is species-appropriate for this
site in a way a European wolf recording would not be. That argument is sound, but it is an inference
from local predator ecology layered on top of Widén's measured result, not the result itself. Applying
this standard in only one direction — citing Widén for the category and staying silent on the
species mismatch — would be exactly the failure the bee-exclusion reasoning two paragraphs up exists to
avoid.

**The light-vs-sound comparison, found and read this session — not the gap the brief expected.** A
direct boar-specific comparison exists and was located and read: Ani (2025) 15(7):1017, "Comparing
Durations of Different Countermeasure Efficacies Against Wild Boar (*Sus scrofa*) in Cornfields of
Hunchun, Jilin Province, China" (2016–2021, PMC11987724). It is also, independently, the second
predator-call-on-boar study named above — it tested Amur tiger call playback against real wild boar
directly, not just tiger/boar co-occurrence. Read plainly, its headline ranks auditory deterrents
(mean rank 72.6) below visual (118.3) and tactile/electric-fence (152.6), and its best single
treatment was red solar blinkers at ~32 days before efficacy declined, against ~26.5 days for
tiger-plus-boar-distress calls. **That is not read here as "light beats sound for this device."** The
paradigm is different in the one respect that matters: Hunchun's deterrents ran on *continuous,
unconditional* exposure across a field for weeks, the exact condition both this study and Widén et al.
2022 separately identify as the thing that drives habituation — Widén's own design (camera-trap-
triggered, sound only on a passing animal) exists specifically to avoid it, and ADR 0022's watch-gated,
fired-once-per-encounter horn is the same triggered paradigm, not Hunchun's continuous one. So the
Hunchun result is real evidence that continuous broadcast habituates auditory deterrents faster than
visual ones — a genuinely useful finding, folded into `docs/research/boar-deterrence-behavioral-
science.md` — but it does not transfer to a verdict on this device's triggered horn without that
caveat stated. LED patterns are reused on Boar tiers as-is, on the general triggered-flashing-light
footing already carried for Elephant (ADR 0014), not because Hunchun's continuous-exposure ranking was
treated as deciding it either way.

**The household Tier-3 gate transfers unchanged, on a caveat worth recording rather than smoothing
over.** The null result that motivates keeping the gate at all (Hedges & Gunaryadi 2010, sirens) is an
elephant study and does not transfer to boar in either direction. Keeping the gate identical for Boar
is the consistent choice across species, not an evidence-backed one for Boar specifically.

## Decision D — the experience DB path derives from scope, not an archive-at-ship step

`EXPERIENCE_DB_PATH` derives from `NODE_DETERRENCE_SCOPE`:

```python
EXPERIENCE_DB_PATH = DATA_DIR / experience_db_filename(NODE_DETERRENCE_SCOPE)
# "elephant_only" -> "experience.sqlite3" (today's file, unchanged)
# otherwise        -> f"experience-{scope}.sqlite3"
```

This is the stronger choice over archiving the DB at ship time, for a specific reason: it collapses two
things to remember into one. Reverting the scope flag — the step that has to happen anyway before a
trial, and the one whose omission is already visible in the startup banner below — *is* the step that
restores the trial's own DB. There is no separate archival action whose omission silently ships a
boar-shaped policy. It also keeps home-phase learning on disk as recoverable evidence rather than
deleting it.

Carrying forward the config-3 caveat already written at `services/config.py`'s label-derivation
section: the bandit learns one policy per node, and `HABITUATION_WINDOW_S` counts triggers species-
blind. Under `both`, a night of boar visits can walk a node to Tier 3 and leave a dawn elephant facing
an already-habituated response, even with the DB-path derivation above in place — the derivation
prevents *cross-phase* contamination (home-phase boar learning leaking into a later trial), not
*same-run* contamination between two species sharing one active scope. That is a real argument for
preferring a dedicated `boar_only` node over `both` whenever both species need separate evidence, not
a flaw the derivation was meant to fix.

Two consequences, named so they are handled rather than discovered:

- **The file is named by scope, not by phase.** `experience-both.sqlite3`, not
  `experience-home.sqlite3` — the mechanism keys on the flag value, and a phase-named file would
  actively mislead the first time `both` is set anywhere other than a home test.
- **A mid-trial flip is a real, invisible hazard.** If `both` is set at a field site — boar turn up,
  footage seems worth grabbing — the node silently abandons the trial's learned elephant policy and
  resumes whatever DB the scope now points at, mid-trial, with no error. `main.py` logs
  `NODE_DETERRENCE_SCOPE`, both derived label tuples, and the resolved `EXPERIENCE_DB_PATH` together,
  immediately beside the existing `SAFE_MODE` startup line, specifically so this is visible in the boot
  log rather than only in an unread config file. **This banner is the reason it is safe to ship the
  derivation at all** — without it, the derivation should not have shipped.

Neither this derivation nor an archive-at-ship alternative warms a trial's bandit with home-phase
learning; the trial always starts cold. That is the intended baseline, stated once so it is not assumed
otherwise.

## Alternatives rejected

**Archive the experience DB at ship time instead of deriving the path from scope.** Works, but adds a
manual step whose omission is exactly the failure mode being defended against, and deletes (or requires
separately preserving) the home-phase learning rather than keeping it on disk as evidence.

**A boolean flag (`boar_enabled`) instead of a tri-state scope.** Loses the ability to express
`boar_only`, which is the safer state for a dedicated boar-evidence node — deterring and filming boar
without also risking an elephant deterrent firing on a still-partially-tuned Boar-confirmation path
sharing a policy with elephant encounters.

**Fold Boar into `DETERRENT_TARGET_LABELS` without the confirmation-path fix (Decision B).** This is
what Workstream 1's debounce alone would have shipped under scope expansion. Rejected outright once the
bypass was found — see Context.

## Consequences

- `elephant_only` stays the committed default everywhere; nothing in this change is live on any node
  without an explicit, logged operator action.
- Turning on `boar_only` or `both` on a real node still requires the three preconditions this ADR does
  not itself satisfy: `ELETECT_SAFE_MODE=0` (never yet exercised on the board), `EVENT_VIDEO_ENABLED`
  set, and the vision runner supervised and up. Shipping this flag without those produces nothing
  observable.
- The deployment-day config-delivery gap this flag shares with `NODE_HOUSEHOLD_PROXIMITY` — no audited
  config interface exists yet (ADR 0021 is design-only) — is not solved here. The env-first delivery
  path is interim, for ADR 0021 to absorb.
- `FootfallOutcome`'s existing `vision_confirmed`/`vision_polls`/`suppressed_by_vision` fields now carry
  meaning for Boar too, with no shape change.

## Follow-ups

- ADR 0021's audited, retrievable config interface, which this flag's env-var delivery is explicitly
  interim for.
- A triggered-paradigm (not continuous-broadcast) boar-specific light-vs-sound comparison — Hunchun
  answers the continuous case, not this device's fired-once-per-encounter one, and that gap is now the
  precise thing left open rather than an unread study.
- Retire `experience-both.sqlite3` from disk once the home-phase evidence-gathering window closes, if
  it is not otherwise wanted — this ADR does not decide that; it only ensures the trial never
  accidentally reads it.
