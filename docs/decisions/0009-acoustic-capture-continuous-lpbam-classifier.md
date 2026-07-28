# ADR 0009: Acoustic capture mechanism — continuous on-MCU LPBAM classifier supersedes the SAI/comparator-gate design

- **Status:** proposed — one bench test (Rung 2 LPBAM dual-channel concurrency) gates acceptance
- **Date:** 2026-07-28

## Context

ADR 0006 solved a real problem — a gunshot's 2–7ms primary pulse is too short for a cold-start wake-then-
listen design to reliably capture — with a dedicated always-on analog comparator gate plus a pre-trigger
DMA buffer (§2a), and flagged that buffer as a load-bearing, not-yet-bench-validated requirement. A separate
pass through the same problem, done directly against `DEVICE_DEVELOPMENT_WORKFLOW.md` §1's hardware-
capability findings (same day, after ADR 0006/0007 were written), landed on a sharper diagnosis: the
pre-trigger buffer is a patch on top of a wake gate, and the wake gate is the actual source of the risk.
Any design where something has to *wake up* in response to a transient this short is racing the transient,
no matter how good the pre-trigger buffering is. The geophone was never built this way — it continuously
buffers and classifies a rolling window, and *that* classification is what wakes everything else. There is
no principled reason the acoustic path should be architected differently just because INMP441's digital I2S
interface makes "continuous" harder to achieve than an analog sensor does.

Two facts, both already surfaced independently but not yet connected, make a continuous design achievable
without new always-on hardware:

1. **LPBAM (STM32's low-power background autonomous mode) already runs the geophone's own ADC channel
   continuously through STOP mode**, at µA draw, with no CPU wake required to keep sampling. This is
   existing, already-committed infrastructure, not a new subsystem.
2. **An analog electret/MAX9814-style mic can be sampled on a second ADC pin through the same LPBAM
   mechanism.** If LPBAM can drive two independent ADC channels concurrently at STOP-mode power — geophone
   on one, mic on the other — a continuously-running on-MCU classifier can evaluate a rolling audio buffer
   the same way it already evaluates the geophone's STA/LTA window, with no wake gate, no cold start, and
   no race against a short pulse.

This is de-risked by a real precedent for the classifier itself, not just the concurrency mechanism: Edge
Impulse's own Expert Network has a published gunshot-classification project (Swapnil Verma, Arduino Nano
BLE Sense + Portenta H7 — both *less* capable than the STM32U585) using MFCC preprocessing into a 3-layer
1D CNN (8/16/24 neurons), trained on public Kaggle audio (a gunshot dataset + UrbanSound8K for "other"),
reaching 94.5% training / 91.3% test accuracy, deployed as a small importable library that comfortably fits
the STM32U585's 786KB SRAM / 2MB flash. This is a template to study and adapt, not a novel model to invent.

INMP441 remains a real, working capture path (ADR 0006's register-level SAI finding — TrustZone blocks the
devicetree path, not raw register access — still stands, unretracted), but it is not STOP-mode compatible:
Rahul's reference implementation busy-waits near 100% CPU to keep the SAI FIFO from overrunning, which is
the exact power cost this whole architecture exists to avoid outside of short, deliberate event windows.
That doesn't disqualify INMP441 — it means INMP441's right role changed, not that it has none.

## Decision

**Primary design: one continuously-running on-MCU classifier, fed by an analog electret/MAX9814-style mic
sampled via LPBAM on its own ADC channel, running alongside — not instead of — the geophone's existing
LPBAM/ADC channel.** Same mechanism, two channels, one always-on reflex layer. The classifier evaluates a
rolling circular buffer in real time (MFCC features into a small 1D CNN, per the Verma precedent above) and
its output — not a separate comparator — is what fires the wake to STM32-full/QRB2210, exactly mirroring how
geophone STA/LTA already works. This applies to gunshot and to the sustained classes alike (chainsaw,
vehicle, non-infrasonic animal call): one capture path, one Edge Impulse acoustic project, multiple trained
output classes — which is what ADR 0007's Decision already argued for, this ADR just corrects which capture
mechanism delivers it.

**The single open item this hinges on, per `DEVICE_DEVELOPMENT_WORKFLOW.md` §1, is a Rung 2 bench test, not
an assumption:** can LPBAM sustain ~8–16kHz continuous sampling on the mic channel *concurrently* with the
geophone's own ADC/LPBAM channel, both feeding independent buffers, within STOP-mode power draw and without
DMA/channel contention? This is a sharper, single-test version of what ADR 0006's Consequences listed as
five separate open bench items (latency, circular DMA feasibility, reverberant-tail fallback, comparator
tuning, geophone-coupling-range) — this design collapses that whole list into one question, because there
is no comparator, no pre-trigger buffer, and no wake-latency race left to validate once concurrency holds.

**Documented fallback, only if the Rung 2 test fails (channel contention, insufficient sample rate, or power
budget blown): ADR 0006's comparator-gate + pre-trigger-buffer design becomes the field design, not
optional.** In that world, a continuously-running LPBAM mic channel isn't available, so an always-on analog
comparator (electret + LM393-class dual comparator) is the right way to catch a short transient without
paying SAI's near-100%-busy cost continuously — ADR 0006 §2/§2a's reasoning (why a cold-start pre-trigger
buffer is necessary, and the three fallback tiers within it: true circular DMA, gated-not-torn-down SAI, or
the reverberant tail) stands unchanged as the correct answer to that scenario. This is why ADR 0006 is
marked superseded rather than rewritten or deleted — its content is the fallback-path spec, live and
reusable the moment the Rung 2 concurrency test fails, not dead work.

**ADR 0007 is unaffected except for its capture-mechanism assumption.** Its per-class signature/range table,
MCU/MPU wake sequence, power budget, and the fusion-vs-direct-alert routing split (§5 — gunshot bypasses
elephant-presence fusion entirely) all reasoned about classification behavior and system architecture, not
about which physical mechanism captures the audio, and none of that needs to change. Only the "Detection
tier" column's assumption that a comparator gate is the mechanism needs a pointer to this ADR.

## Alternatives considered

- **Keep ADR 0006's comparator-gate + pre-trigger-buffer as the primary design.** Rejected as primary (kept
  as documented fallback) — it solves the same problem with a new analog component, comparator threshold
  tuning against real gunshot recordings, and an unproven circular-DMA pre-roll, when reusing LPBAM
  infrastructure already committed for the geophone avoids adding a subsystem at all, provided the
  concurrency test holds.
- **Drop the analog mic entirely; run INMP441 continuously via SAI.** Rejected, unchanged from ADR 0006 —
  Rahul's own reference implementation's near-100%-busy finding makes this incompatible with the µA-sleep
  reflex-layer budget regardless of which classifier consumes the samples.
- **Accept the cold-start risk and ship ADR 0006 as originally scoped, pre-trigger buffer unresolved.**
  Rejected — this is the exact flaw (racing a 2–7ms pulse with any wake-then-listen design) that prompted
  this reconciliation in the first place; shipping it unresolved would carry known, named risk forward
  without reason.

## Consequences

+ Removes a new always-on component (electret + LM393 comparator) from the committed BOM unless the Rung 2
  concurrency test fails — simpler bench build, one fewer procurement line to re-open, conditional rather
  than committed the way ADR 0006's Consequences framed it.
+ Resolves the cold-start-vs-2–7ms-pulse race by construction (nothing has to wake up in time) rather than
  by a pre-trigger-buffer patch that itself needed unproven circular-DMA validation.
+ Reuses LPBAM infrastructure already required for the geophone — one mechanism, two ADC channels, not two
  separately-engineered always-on subsystems.
+ Collapses ADR 0006's five-item open bench-validation list into one sharper, single load-bearing test.
− If the Rung 2 concurrency test fails, every one of ADR 0006's original open items reactivates at once as
  the fallback plan (latency measurement, circular-DMA feasibility, reverberant-tail viability, comparator
  tuning, geophone-coupling-range) — this design trades five smaller risks for one bigger one, not zero risk.
− Still needs a real MFCC + small-CNN classifier trained on captured audio; the Verma precedent's public
  Kaggle gunshot dataset + UrbanSound8K is a directly reusable starting point (already flagged in
  `DEVICE_DEVELOPMENT_WORKFLOW.md` §1), but local ambient noise (Kerala forest, not the dataset's original
  recording environment) still needs its own labeled recordings before this ships.
− ADR 0007's Decision table needs a follow-up pointer (not a rewrite) directing readers to this ADR for the
  gunshot/sustained-class capture mechanism specifically.

## Evidence / sources

- `DEVICE_DEVELOPMENT_WORKFLOW.md` §1 — LPBAM/STOP-mode concurrency finding, bit-banged I2S alternative,
  Verma gunshot-classification precedent, Rung 2 bench-test framing.
- Edge Impulse Expert Network — Swapnil Verma gunshot classification (MFCC + 3-layer 1D CNN, Kaggle gunshot
  dataset + UrbanSound8K, 94.5%/91.3% train/test accuracy).
- ST AN5086 (SPI+timer I2S emulation technique, referenced for the documented INMP441 alternative).
- ADR 0006 (comparator-gate + pre-trigger-buffer design — retained as the fallback-path spec, not deleted).
- ADR 0007 (per-class signature/range table, MCU/MPU split, power budget, fusion-vs-direct-alert routing —
  all unchanged by this ADR).
