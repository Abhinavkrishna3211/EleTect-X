# ADR 0007: Acoustic subsystem architecture — sensing, MCU/MPU split, and Edge Impulse classification

- **Status:** proposed
- **Date:** 2026-07-28

## Note (added after ADR 0009, not a rewrite of this ADR)

ADR 0009 supersedes ADR 0006's comparator-gate capture mechanism with a continuous on-MCU LPBAM classifier
as the primary design (ADR 0006 remains the documented fallback). Everything below — the per-class
signature/range table, the MCU/MPU wake sequence, the power budget, and the fusion-vs-direct-alert routing
split in Decision §5 — is unaffected and stands as written; only the "Detection tier" column's assumption
that a comparator gate is the mechanism should be read as "whichever capture mechanism ADR 0009 resolves to."

## Addendum, 30 Jul 2026 — acoustic subsystem sequenced after the DFO field test

Everything below this line still stands unchanged. This addendum records a scheduling decision,
not an architecture change: acoustic hardware bring-up, dataset collection, and Edge Impulse model
training are deferred until after the ~9-14 Aug DFO field test, freed time going instead to vision
and seismic model work and camera/video capture setup ahead of the Aug 8 freeze.

This is a safe deferral, not a scope cut, for reasons already written into this ADR and ADR 0001:
acoustic corroboration was scoped as a "stretch" from the start (`BUILD_BLUEPRINT_AUG8.md` §1), and
of its two outputs, gunshot classification was already decided (Decision §5, above) to route to its
own direct anti-poaching alert, entirely outside the elephant-presence fusion sum — so it was never
part of the loop the field test needs to prove. The other three classes (chainsaw, vehicle, animal
call) *do* feed fusion, but ADR 0001's addendum already establishes that a missing modality is
excluded from the sum, not scored as negative evidence — the system is explicitly designed to
degrade gracefully with acoustic absent, not break.

**Hardware plan:** the field-bound UNO Q keeps running seismic + vision only through the field test.
The second unit (`hardware/bom/procurement-status.md`'s permanent bench/dev board) becomes the
dedicated acoustic development unit once freed up, so acoustic bring-up never touches the
already-validated field node.

**What's already done and doesn't need redoing:** the Bridge contract (`report_acoustic_event` in
`device/mpu/bridge/schema.md` and its stub in `device/mpu/bridge/rpc.py`) and this ADR's full
architecture already exist — the acoustic subsystem is designed and its function boundary is fixed,
only its hardware bring-up and trained model are deferred. Nothing needs to be un-built or removed.

**What's actually deferred:** INMP441 hardware integration, the ADR 0009 Rung 2 LPBAM dual-channel
concurrency bench test, gunshot/chainsaw dataset collection (`DEVICE_DEVELOPMENT_WORKFLOW.md` §4a),
and Edge Impulse acoustic model training. Targeted for the post-field-test window (15-30 Aug),
alongside the Robu/Hackster submission sprints.

## Context

ADR 0006 solved one piece of the acoustic subsystem (the gunshot wake-gate and its cold-start risk) in isolation. That left the full picture scattered across several conversations: what INMP441 can actually hear and how far, how each of CONTEXT.md §3's four target classes (gunshot, chainsaw/logging, illegal vehicle entry, animal sounds) differs physically and therefore needs a different detection treatment, where each processing stage actually lives (STM32 vs QRB2210), and how Edge Impulse fits given ADR 0001's "one toolchain" principle. This ADR is the single, unified reference for all of that — it does not re-decide anything ADR 0006 already settled (the gunshot gate and its pre-trigger-buffer fix stand as written), it assembles the surrounding architecture ADR 0006 depends on and was written without.

Two pieces of hardware-level science ground everything below. INMP441's own datasheet (TDK InvenSense): sensitivity −26dBFS at 94dB SPL/1kHz, SNR 61dBA, self-noise (EIN) 33dBA SPL, dynamic range 87dB, flat frequency response 60Hz–15kHz (−3dB point at 60Hz), 1.4mA active current at 1.8–3.3V. The 60Hz low-frequency rolloff is exactly why CONTEXT.md already assigns infrasound (elephant rumble, <60Hz) to the geophone and not INMP441 — that's a hardware limit, not a design choice, and this ADR doesn't touch it.

Real-world detection range is not something to assume — it was checked against two independent field precedents rather than derived from a datasheet in isolation. A published field study ("Deploying Acoustic Detection Algorithms on Low-Cost, Open-Source Acoustic Sensors for Environmental Monitoring," PMC6387379) fired gunshots at ranges up to 800m through dense broadleaf rainforest and had a low-cost acoustic sensor and detection algorithm respond correctly — a directly comparable environment to Kerala's forest-boundary terrain. The same paper is honest about the failure mode that matters here: nearby loud fauna (the paper's example is howler monkeys, but wind, rain, and insects apply equally) can mask or overpower a gunshot occurring far away — range is a best case, not a guarantee, and the classifier has to be trained against local ambient noise, not just clean recordings. Separately, Rainforest Connection's Guardian 3 — a real, deployed, solar-powered forest bioacoustic system already covering 750,000+ hectares — detects chainsaws, vehicle engines, hunting dogs, and gunshots from a 50m–1,500m radius depending on the specific source (louder, more impulsive sources like gunshots reach the far end of that range; quieter, more localized sources the near end), and reports 96% chainsaw-detection accuracy with up to five days of advance warning before logging starts. This is strong, independent validation that the general approach — solar-powered node, mic array, ML classification of exactly these classes — is not speculative; it's a proven category of system, not a novel one.

## Decision

### Per-class signature, sensing strategy, and range

| Class | Signature | Duration | Detection tier | Realistic range (grounded above) |
|---|---|---|---|---|
| Gunshot | Broadband impulsive transient, sharp attack, decaying tail | 2–7ms primary pulse + reverberant tail | Dedicated always-on analog comparator gate (ADR 0006) → INMP441 burst capture → classify | Up to ~800m demonstrated in comparable rainforest terrain (PMC6387379); RFCx's high end (1,500m) is the ceiling for a loud impulsive source, not a floor |
| Chainsaw / tree-cutting | Sustained quasi-periodic engine+blade buzz, ~100–300Hz fundamental + harmonics, seconds to minutes | Seconds+ | Geophone/periodic-wake-gated rolling-window capture → classify (ADR 0006 stage 1) | RFCx precedent: reliable well within their 50–1,500m band; sustained lower-frequency sources propagate through canopy better than a single transient, so this is comfortably inside gunshot's range, not a stretch beyond it |
| Illegal vehicle entry | Engine/tire rumble, RPM-linked harmonics, rising-then-falling amplitude as it passes | Seconds to tens of seconds | Same rolling-window path as chainsaw; corroborated by geophone (vehicles couple to the ground far more reliably at close range than gunfire does, unlike the gunshot-geophone question ADR 0006 left open) | Deployment already limits this: CONTEXT.md §6 places GUARD-tier nodes at crossings specifically, so the sensor only needs to reliably cover a road/track width plus margin — tens of meters, not hundreds. Range is not the binding constraint for this class. |
| Animal sounds (non-infrasonic) | Species-specific vocalizations, in-band above 60Hz | Variable | Same rolling-window path, different trained classes | Elephant rumble stays out of scope for INMP441 (below its 60Hz rolloff, per datasheet) — geophone's job, unchanged from CONTEXT.md. In-band calls (trumpets, other species) follow the same range logic as chainsaw. |

The shared conclusion: one microphone, one capture path, one Edge Impulse toolchain, four trained classes — not four different sensing schemes. This directly extends ADR 0001's "vision, seismic, and acoustic all train and deploy through Edge Impulse — one toolchain, one OTA path" to the acoustic side specifically, and matches what Forest Guard's own public writeup says about its (much simpler) system: retraining the same pipeline on new classes, not rebuilding hardware, is what makes this scale to new threats later.

### MCU/MPU split — who sleeps, who runs, in order

1. **Default state (>99% of the time).** STM32 reflex layer is in its normal µA-range STOP-mode-cycling pattern, running geophone STA/LTA sampling on its own existing duty cycle. The dedicated gunshot comparator (ADR 0006 §2) runs continuously in parallel — LM393's typical quiescent current is 0.4mA for both channels combined (only one channel is used here), a small, precisely bounded addition to the existing reflex-layer budget, not a new order-of-magnitude cost. INMP441/SAI sits clock-gated (or lightly circular-buffering, if ADR 0006's §2a.1 fix is validated on the bench) — no continuous digital audio pipeline running. **The QRB2210 MPU is fully suspended, not booted** — this is the expensive component power-wise, and CONTEXT.md's "cognition (QRB2210, event-only)" already establishes it doesn't run continuously; this ADR doesn't change that, it just confirms the acoustic subsystem doesn't either.

2. **Trigger fires** — any of: geophone STA/LTA crossing threshold, a periodic maintenance wake, or the gunshot comparator. STM32 wakes fully. For the gunshot path, if the pre-trigger buffer fix is in place, audio from just before the trigger is already available; for geophone/periodic triggers, INMP441/SAI cold-starts (acceptable here since chainsaw/vehicle/call events last seconds, so a few ms of cold-start latency is irrelevant — this is exactly why ADR 0006 treats gunshot as the special case, not the general one). STM32 extracts scalar features (RMS, crest factor, spectral centroid/flatness, zero-crossing rate) and, for gunshot specifically, does a first cheap impulsive-shape check itself before deciding whether to escalate.

3. **STM32 wakes the QRB2210.** The physical mechanism for this handoff isn't yet pinned down anywhere in CONTEXT.md or the existing ADRs — flagged here as an open item this ADR surfaces rather than resolves, since it affects every event-driven wake in the system, not just acoustic ones.

4. **QRB2210 awake, cognition layer active.** Boots/resumes, pulls the captured audio (features or raw window) from STM32 over Bridge/SPI, and classifies it. Important precision here: we are **not** using Arduino's stock `audio_classification` Brick's built-in input loop (it expects a USB mic on the Linux side, continuously listening — incompatible with this whole power argument, per ADR 0006). We **are** still using the same underlying Edge Impulse deployment artifact and Python runtime the Brick wraps — a model trained in Edge Impulse Studio, exported for the UNO Q/Linux aarch64 target, invoked directly against our own captured buffer instead of a live mic stream. Same toolchain, same `.eim`/SDK mechanics, custom input plumbing — consistent with how the vision model already works per ADR 0001, and with what the Brick's own `classify_from_file()` call does structurally.

5. **Result routing — this is a real distinction this ADR adds, not previously stated anywhere.** Not every acoustic classification result should feed CONTEXT.md §4's log-odds fusion formula. That formula (`L = L_prior + Σ aᵢwᵢ(ℓᵢ−ℓ₀ᵢ)`, `P = σ(L)`) is scoped around one question: is an elephant present. Chainsaw, vehicle, and animal-call classifications are legitimate evidence toward that question and should feed the fusion sum as weighted log-odds terms, same as vision and geophone. **Gunshot is not evidence toward "is an elephant present" — it's a categorically different alert (anti-poaching, human safety), and folding it into the elephant-presence fusion score would be a modeling error, not just an oversimplification.** A gunshot classification should trigger its own direct alert path (LoRa to forest officers) independent of the bandit/deterrence decision entirely — you don't deter a gunshot with LEDs and a horn, you alert rangers. This routing split needs to be reflected wherever the fusion/alert logic actually gets implemented; it isn't yet.

6. **MPU returns to suspend, STM32 returns to reflex-only sleep.** The comparator and geophone remain the only continuously-active elements, closing the loop back to state 1.

### Power budget

- Geophone STA/LTA: unchanged, already inside the existing always-on budget (ADR 0001).
- Gunshot comparator: +0.4mA typical (LM393, both channels; only one used) — small and precisely bounded, not a guess.
- INMP441: 1.4mA active current, but only during event windows (seconds), never continuous under this design — negligible contribution to the multi-day average regardless of which classifier class triggered the capture.
- QRB2210: the dominant power draw whenever it's awake, but this is an existing, already-accepted cost of the event-only cognition tier (ADR 0001) — the acoustic subsystem adds one more class of *trigger* for an MPU wake (alongside geophone and periodic wakes already planned), it does not add a new *always-on* MPU cost.

### Scalability

Because all four classes share one capture path and one Edge Impulse project, adding a new acoustic threat class later (a new poaching method, a new vehicle type, a new species call) is a retraining and redeployment exercise — new labeled data, retrain, redeploy the `.eim` to the QRB2210 — not a hardware or firmware redesign. This is the same OTA-updateable, single-toolchain property ADR 0001 already established for vision.

## Alternatives considered

- **Separate detection hardware/pipeline per class** (e.g. a dedicated chainsaw sensor, a dedicated vehicle sensor). Rejected — contradicts CONTEXT.md §7's "reject gimmicks" / "simplicity over complexity," and there is no physical reason to: all four classes are audible to the same microphone in the same frequency band (except elephant infrasound, already the geophone's job), so multiplying hardware would only multiply cost and failure modes without improving detection.
- **Route all acoustic classifications through the elephant-presence fusion formula uniformly.** Rejected in Decision §5 above — gunshot specifically is not elephant-presence evidence, and treating it as such would both weaken the fusion score's meaning and slow down what should be a direct, urgent alert.
- **Use Arduino's stock `audio_classification` Brick as-is.** Rejected per ADR 0006 — its continuous-MPU-listening assumption is incompatible with the power architecture.

## Consequences

- This ADR does not change ADR 0006's gunshot-gate design or its open bench-validation items — it sits alongside it as the full-system view.
- New open item this ADR surfaces: **the STM32→QRB2210 wake mechanism itself isn't specified anywhere yet.** This affects every event-driven wake (geophone, gunshot, periodic), not just acoustic, and should probably be its own ADR rather than settled as a side effect of this one.
- New open item: the fusion-vs-direct-alert routing split (Decision §5) needs to be reflected in whatever module actually implements fusion/alerting — currently undocumented outside this ADR.
- Range figures here (800m gunshot, 50–1,500m RFCx band) are strong field precedent, not a guarantee for this specific site — Kerala's canopy density, terrain, and node placement will all shift real numbers, and the PMC study's own caveat (nearby loud fauna can mask a distant gunshot) applies directly. Treat these as "this class of system is proven to work at these orders of magnitude," not as a committed spec.

## Evidence / sources

- INMP441 datasheet (TDK InvenSense) — sensitivity, SNR, self-noise, frequency response, current draw — https://www.digikey.com/htmldatasheets/production/1431884/0/0/1/inmp441-datasheet.html
- "Deploying Acoustic Detection Algorithms on Low-Cost, Open-Source Acoustic Sensors for Environmental Monitoring" (gunshot detection to 800m in dense rainforest) — https://pmc.ncbi.nlm.nih.gov/articles/PMC6387379/
- Rainforest Connection Guardian 3 — real deployed forest bioacoustic system, 50–1,500m detection radius, 96% chainsaw accuracy, 5-day advance warning — https://rfcx.org/guardian
- LM393 datasheet — 0.4mA typical quiescent current — https://www.onsemi.com/download/data-sheet/pdf/lm393-d.pdf
- ADR 0001 (fusion formula, one-toolchain principle); ADR 0006 (gunshot gate, mic capture feasibility, App Lab Brick incompatibility); CONTEXT.md §3/§4/§6
