# ADR 0027: `AcousticClass` reconciled to the trained four-class model

- **Status:** accepted (2026-09-24)
- **Supersedes in part:** ADR 0024's amendment, which named a different class list
- **Relates to:** ADR 0007 §5 (acoustic routing), ADR 0009, ADR 0026

## Context

Three copies of the acoustic class scheme were live at once and none of them agreed.

| source | classes |
|---|---|
| `bridge/rpc.py`'s `AcousticClass` + `bridge/schema.md` | gunshot, chainsaw, vehicle, animal_call, ambient |
| ADR 0024's amendment | gunshot, chainsaw, vehicle, elephant_call, boar_call, other_animal_call, ambient |
| the model that was actually trained | gunshot, chainsaw, elephant_call, ambient |

The consequences were asymmetric and all silent:

- **`elephant_call` had no enum member**, so the best class in the trained model — 96.6% recall on
  the 3 s graph, and the only class that is direct evidence of an elephant rather than a correlate
  of one — could not cross the MCU→MPU wire at all. Inference could have been perfect and the
  result still could not have been reported.
- **`vehicle` and `animal_call` could never be emitted**, yet `reflex_loop.py` routed both as
  elephant-presence evidence. Two of the three branches in `_FUSING_ACOUSTIC_CLASSES` were dead
  code that read like working detection.

ADR 0024's amendment had already sanctioned adding `elephant_call`; that decision was simply never
carried into the code. Training then diverged from the amendment too, in two ways:

- **`boar_call` was dropped.** ADR 0024 predicted exactly this ("most likely `boar_call`") and
  pre-authorised the response: report the shortfall honestly rather than pad the data. No boar
  audio of verified provenance was found in sufficient volume. The amendment's fallback was to fold
  it into `other_animal_call`, but no `other_animal_call` data was assembled either, so there is
  nothing to fold into and no class to fold it to.
- **`vehicle` was dropped**, which ADR 0024 did *not* sanction — the amendment asked for more
  volume on the existing `vehicle` class. This was an unrecorded training decision, and this ADR is
  where it gets recorded rather than left implicit in a dataset manifest.

## Decision

**The wire enum states exactly what the trained classifier can emit: `gunshot`, `chainsaw`,
`elephant_call`, `ambient`.** `vehicle` and `animal_call` are removed. `boar_call` and
`other_animal_call` are not added.

Routing follows from that:

- **`gunshot`** — unchanged. Direct LoRa alert, never fused (ADR 0007 §5).
- **`elephant_call` and `chainsaw`** — fuse as the single ACOUSTIC modality, sharing
  `WEIGHT_ACOUSTIC`/`BASELINE_ACOUSTIC`.
- **`ambient`** — unchanged. Fuses as unavailable.

`bridge/schema.md`'s `class_label` cell moves with the enum, and
`tests/test_rpc_contract.py::test_acoustic_class_enum_matches_schema_md` now asserts the two are
identical, in order. That check is new and is the point of this ADR as much as the class list is:
the failure here was not a wrong decision, it was three copies of a decision with nothing
comparing them.

## Consequences

**A dead-weight enum member is not free.** The argument for keeping `vehicle` — harmless, might be
trained later — is what produced this defect. An unreachable member let `reflex_loop.py` carry
elephant-evidence routing for a class that could never arrive, and made the routing table look
more capable than it was. Re-adding a class is a small, testable change; a branch that has silently
never executed is not something a reviewer can see.

**`elephant_call` and `chainsaw` share one weight, and they are not equally informative.** An
elephant call is direct evidence; a chainsaw is evidence of people who often precede elephants.
ADR 0007 §5's one-modality treatment was written when the fusing set was three loosely-related
classes, and it is a worse fit now that the set is two classes of clearly different strength.
Splitting the weight is deliberately **not** decided here — `WEIGHT_ACOUSTIC` and
`BASELINE_ACOUSTIC` are still invented magnitudes (`docs/KNOWN_GAPS.md`), so splitting one invented
number into two invented numbers buys precision that is not real. Tracked as its own gap.

**Species deterrence is narrower than ADR 0024 intended.** The system can distinguish an elephant
call from ambient, but has no boar class and no generic animal class. Anything that is neither an
elephant, a chainsaw, nor a gunshot classifies as `ambient` and fuses as "nothing to say". For boar
specifically this is a real capability gap against the amendment's stated goal, not a
simplification — recorded here so it is not rediscovered as a surprise.

**This unblocks deployment of the trained model but does not constitute deployment.** No acoustic
inference runs on the device today; `reflex_loop.py` still deliberately leaves acoustic out of the
reflex path, and `bridge_handlers.cpp` hardcodes `state.acoustic_ok = false`. This change removes
the wire-layer blocker only. The model's accuracy figures are also x86-only so far — the on-target
benchmark is still outstanding.

## Verification

Full `device/mpu` suite before and after: **identical failure sets** (14 pre-existing failures in
boar-gate, `home_test`, night-exposure and schema-version tests; none acoustic). ADR 0024's
condition — "regression-test the full reflex loop against the existing gunshot/chainsaw fixtures
before merging" — is met: all 24 acoustic-routing tests pass, including the unchanged gunshot
direct-alert path and the chainsaw fusion fixture.

## Alternatives considered

- **Keep `vehicle`, add `elephant_call` alongside it.** Rejected: preserves exactly the dead-branch
  condition this ADR exists to remove, and there is no `vehicle` training data or timeline.
- **Add `boar_call` as an enum member ahead of the data.** Rejected: the same "declare it now, train
  it later" reasoning that produced the original defect. ADR 0024 pre-authorised reporting the
  shortfall instead.
- **Fold `chainsaw` out of the fusing set, leaving `elephant_call` alone.** Rejected as out of
  scope. It is a substantive change to ADR 0007 §5's fusion model and deserves its own decision with
  field evidence, not a rider on a wire-contract fix.
