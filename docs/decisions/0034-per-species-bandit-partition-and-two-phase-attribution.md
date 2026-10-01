# ADR 0034: The deterrence bandit — per-species partition, two-phase attribution, and a node-level reward

- **Status:** accepted
- **Date:** 2026-10-02
- **Supersedes in part:** ADR 0023 Decision D's conclusion that a dedicated `boar_only` node is
  preferable to `both` whenever two species need separate evidence
- **Relates to:** ADR 0017 (habituation, the reason the ladder exists), ADR 0022 Decision C,
  ADR 0023 Decisions A and D, ADR 0031 §A as amended (the species on the frame)

## Context

The contextual bandit in `cognition/` has been the deterrence policy since before there was a second
species, and it has never had an ADR of its own — it arrived as implementation under ADR 0017's
habituation reasoning. Two species later, and now three, the thing it was never designed for is the
normal case.

**The harm was named twice and fixed neither time.** ADR 0022 Decision C and ADR 0023 Decision D both
state it plainly: the bandit learns one policy per node, and `HABITUATION_WINDOW_S` counts triggers
species-blind. Under a multi-species scope, a night of boar or fox visits walks the escalation floor
up and leaves a dawn elephant facing an already-habituated response — Tier 3 on first sighting, at
full gain, at an animal that has not been deterred by anything yet. ADR 0023 Decision D concluded
that this was "a real argument for preferring a dedicated `boar_only` node over `both`", which is a
deployment workaround for a software defect, and one the DFO deployment cannot use: the sites that
have elephants also have boar and fox, and there is one node per site.

**The structural obstacle is that the species is not known when the bandit needs the row.**
`record_trigger()` runs on the footfall notify. The confirming vision label arrives from
`_watch_for_vision()` up to 45 seconds later. So a partition keyed on species cannot simply be added
to the write — at write time there is nothing to key on.

**And the reward is species-blind by construction.** `proxy_reward()` measures the gap to the *next
seismic trigger*: a long gap means whatever fired worked. The geophone does not know what walked
past it. There is no species-aware version of that measurement available on this hardware.

Underneath all of it, the ladder had been flat since 7 September: a one-night field test set
`TIER_FLOOR_BY_CONTEXT = (TIER_3, TIER_3, TIER_3)` and that lived in the committed source for three
weeks. With one legal candidate at every context, `select_tier()` explores nothing, learns nothing,
and fires the loudest response the hardware permits on first sighting. Per-species habituation is
unobservable while that stands, and for a DFO deployment it is also the wrong default on welfare
grounds.

## Decision

### A. The floor is partitioned by species; the watch length is not

`action_values` is keyed `(species, context, tier)` — a composite primary key, not a species column
on a node-level table. `escalation_floor()` is fed a **species-scoped** repeat count computed at
selection time, so a fox's returns can only walk the fox ladder.

The watch length deliberately keeps the species-blind count. `_watch_length_s()` consumes
`repeat_count` *before* any species is knowable, and the asymmetry is the point: looking longer is
cheap and reversible, escalating is neither. A node that has seen a lot of activity should watch
harder regardless of what the activity was. Only the floor — the thing that fires a horn — is
partitioned.

### B. Attribution is two-phase, and an unattributed trigger is a first-class state

- `record_trigger()` writes the row with `species = UNATTRIBUTED` (the empty string, so it is a real
  key rather than a NULL that every query has to special-case).
- `attribute_trigger(event_ts_s, species)` names it once the watch resolves.
- A trigger that is never confirmed stays `UNATTRIBUTED` forever. That is not a failure — it is the
  honest record of a node that was woken by something it could not identify, and it is the majority
  of rows at a site with cattle, wind and rain.

`UNATTRIBUTED` is also the default argument everywhere (`record_attempt(..., species=UNATTRIBUTED)`,
`action_values(species=UNATTRIBUTED)`) rather than a required parameter. That keeps the existing call
sites and the existing 22 `test_experience.py` tests meaningful as *the unattributed partition*
instead of rewriting them to assert a new signature — the tests still test behaviour, and the
unattributed partition is behaviour that has to work.

### C. The reward stays node-level, and this is a documented limitation rather than a solved problem

`settle_pending()` keeps measuring the gap to the next seismic trigger, species-blind, and credits
the cell named by **the attempt's own stored species** — the attempt knows what it fired at, even
though the trigger that settles it does not.

Settling only against same-species triggers was the alternative, and it would nearly stop learning at
night, when most triggers are never attributed at all. A policy that learns slowly from a slightly
wrong signal beats one that learns from almost nothing: at a site with three species, the next
trigger after an elephant fire is often a boar, and discarding it would discard most of the evidence
there is.

The limitation this leaves, stated so it is not discovered later: **a fire at species X can be
credited or punished by a return of species Y.** The partition protects the *floor* — one species
cannot spend another's escalation ladder — but not the *action values*, which absorb some
cross-species noise. This is the honest boundary of what a single buried geophone can support, and
ADR 0035's species-labelled seismic corpus exists in part to remove it: a future footfall model that
names the species from ground motion alone would make the reward partitionable too.

### D. Fox gets its own ladder and borrows Boar's content

Fox has its own `bandit_policy` — the registry default, which is the label itself — so a night of
foxes cannot touch the elephant ladder. It borrows Boar's `deterrence_content`, because the horn
tracks and LED patterns were chosen for a mid-sized mammal and there is no fox-specific evidence to
choose differently; ADR 0023 Decision C makes the same ecological-inference argument for reusing
tiger and lion growls on Boar. There is a second, more concrete reason: until the vision model had a
Fox class it labelled foxes "Boar", so Boar's content is what those arms were actually learned on.

Separating the **policy** key from the **content** key in the species registry (ADR 0023 Decision A's
`NODE_DETERRENCE_SCOPE` shape, extended) is what makes that combination expressible at all, and the
default is identity: a new species gets its own bandit case automatically, and sharing another
species' ladder or content stays a visible, deliberate line in the table.

### E. The real ladder is committed; the flat override moves to the environment

`TIER_FLOOR_BY_CONTEXT = (TIER_1, TIER_2, TIER_3)` is what ships. The Tier-3 field-test override
becomes `ELETECT_TIER_FLOOR`, parsed by `parse_tier_floor()`, matching how `NODE_DETERRENCE_SCOPE`
already works — so an in-progress local test survives without living in a commit, and a malformed
value warns and keeps the built-in ladder rather than silently inventing one.

## Alternatives considered

- **A dedicated single-species node per species** (ADR 0023 Decision D's conclusion). Rejected now
  that the DFO deployment is real: the sites that have elephants also have boar and fox, there is one
  node per site, and the budget for a second node per site does not exist. Superseding this is the
  main reason this ADR exists.
- **One bandit, with species as an extra context dimension.** Rejected because context buckets are
  consumed by `habituation_context()`, which maps a repeat count onto a small fixed number of
  buckets. Multiplying buckets by species multiplies the data each cell needs by the same factor, on
  a device that sees a handful of encounters a night. A partition keeps each species' cells as dense
  as the single-species case was.
- **Species-aware reward, settling only on same-species triggers.** Rejected per Decision C — it
  would stop learning at night, which is when all three target species are most active.
- **Attributing at `record_trigger()` by waiting for the watch to finish first.** Rejected: the
  trigger row is what `repeat_count()` reads, and the habituation window has to include a trigger the
  moment it happens or a returning animal is invisible for the 45 s that matter most.
- **Leaving the floor species-blind and accepting the harm.** Rejected. "A dawn elephant meets a
  habituated response" is not a tuning imperfection — it is the deterrent failing at the exact
  encounter the system exists for, and ADR 0017 makes habituation the thing the whole ladder is
  built to avoid.

## Consequences

- `_migrate()` rebuilds `action_values` under the composite primary key. **Existing rows become
  `UNATTRIBUTED` and are never read again** once a node is attributing — deliberate, because a
  node-level policy learned across three species cannot be honestly assigned to any one of them.
  The rows are kept rather than dropped so the pre-partition history is still on disk as evidence.
- `settle_pending()`'s `ON CONFLICT` target moves to `(species, context, tier)` with the primary key;
  the old `(context, tier)` target raised `OperationalError` against the new schema.
- `ExperienceStoreProtocol` in `services/reflex_loop.py` carries the species-scoped signatures, so
  the reflex loop and the store cannot drift apart silently.
- `HomeTestSession`'s deterrence thread and the Bridge callback share one store over a connection
  opened with `check_same_thread=True` — a latent `sqlite3.ProgrammingError` that the partition work
  made easy to hit. A `threading.Lock` guards it, and the class docstring's "not thread-safe and not
  intended to be" is corrected rather than left as a trap.
- **The fox-then-elephant regression test is the one that matters.** A night of fox triggers followed
  by an elephant must hand the elephant `TIER_1`, not a habituated floor. It is written as a
  regression rather than a unit test because it is the specific harm ADR 0022 and ADR 0023 both named
  and declined to fix.
- **Unmeasured:** whether per-species learning converges at a real site's encounter rate. Partitioning
  divides the evidence three ways, and `docs/KNOWN_GAPS.md` already records that the bandit's
  convergence has never been observed in the field at all. This ADR makes the policy correct; it does
  not make the data sufficient.
