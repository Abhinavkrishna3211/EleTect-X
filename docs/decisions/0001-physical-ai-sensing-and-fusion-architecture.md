# ADR 0001: Physical-AI sensing, vision pipeline, and fusion architecture

- **Status:** accepted
- **Date:** 2026-07-12

## Context

CONTEXT.md §4 freezes the reflex/cognition split and the log-odds fusion formula, but left three things underspecified enough to be risky for a real field deployment: (1) which ADC the geophone front-end actually uses in the final node, (2) what model architecture and tooling the vision stage runs, and (3) whether the fusion math's assumptions (independence across modalities, missing-sensor handling) are actually sound rather than just convenient. These matter because DFO Kothamangalam has approved a real field deployment — a wrong call here isn't a contest-scoring risk, it's a missed-elephant or false-alarm risk for people who will depend on this. This ADR was preceded by two independent research passes (general-purpose agents) covering (a) vision architecture options given QRB2210's actual hardware — quad Cortex-A53, Adreno 702 GPU, **no Hexagon NPU** — and (b) real-world HEC sensor-fusion precedent and the statistical soundness of the fusion design.

## Decision

**1. Geophone ADC:** drop the ADS1115 from the final node. SM-24 → INA333 → Sallen-Key band-pass 2–50 Hz → **STM32U585 internal ADC (LPBAM)**. ADS1115 stays a bench-only stand-in for early STA/LTA prototyping before the STM32 path is validated (already reflected in CONTEXT.md §3 and PROJECT_BLUEPRINT.md §4 — no further change needed there).

**2. Seismic target band:** keep the existing 2–50 Hz band-pass as-is. Research corrected an earlier internal assumption that elephant footfall centers around ~14 Hz — published seismology (O'Connell-Rodwell et al., 2000, JASA) puts footfall/stomp at **~24 Hz mean (±3)** and rumble-vocalization seismic coupling at ~20 Hz; embedded-systems HEC papers design around a 10–80 Hz window. The existing 2–50 Hz band already covers this correctly; nothing to change in hardware or firmware, but any STA/LTA or TinyML feature-extraction tuning should target ~20–24 Hz, not 14 Hz.

**3. Vision detector: FOMO (Edge Impulse) stays primary, with an explicit mitigation and a documented fallback.** Train and deploy an Edge Impulse FOMO detector (elephant / wild boar / background classes) on the QRB2210 via Edge Impulse's Linux/AARCH64 SDK, generic CPU/TFLite path (no QNN/Hexagon delegate available on this chip). Mitigate FOMO's known weakness — it predicts one centroid per grid cell and fails on overlapping objects or one large object dominating the frame — by increasing input resolution / heat-map grid density during training, and by treating FOMO's output strictly as "elephant present, approximate location," never as a herd count or size/distance estimate. This keeps vision on the same Edge Impulse platform as seismic and acoustic (one training/deployment toolchain, one team skill, one OTA update mechanism per CONTEXT.md §4's "vision model fixed, OTA-updated centrally") and fits inside the ~6-week runway to the Robu deadline.

**4. MegaDetector's role stays offline-only, but the reason changed.** Originally justified by MDv5's 121M parameters being too heavy for a no-NPU chip. Research found MDv6-compact is only **2.3M params** and has already been deployed on solar-powered edge hardware (Microsoft's SPARROW project) — so "too heavy" is no longer the correct justification. The actual reason to stay offline-only now: adopting MDv6-compact on-device would mean a two-stage detect-then-classify pipeline on a *different* toolchain (ONNX/PyTorch-Wildlife) than the rest of the sensor stack, adding integration surface and a second model to validate/maintain under a fixed deadline, for a benefit (real bounding boxes, no overlapping-centroid failure mode) that doesn't change the actual decision this system needs to make (present/not present, not count or precise scale). MegaDetector continues to be used purely offline, as a Roboflow model-assisted labeling accelerator when building the training dataset.

**5. Documented fallback, not pursued now:** if field testing during the August DFO test shows FOMO's overlapping-centroid failure meaningfully hurts real detection reliability (e.g., missed elephants in herds or at close range), the fallback is MDv6-compact (generic detector) + a small custom crop-classifier (elephant/boar/background), which is proven deployable on comparable solar-edge hardware. This is a v2 item, not a pre-launch requirement — evaluating it now would cost timeline for a failure mode that may not materialize in practice, since presence detection (not counting) is the actual requirement.

**6. Fusion stays log-odds, with two limitations now documented instead of assumed away.** `L = L_prior + Σ aᵢwᵢ(ℓᵢ−ℓ₀ᵢ)`, `P = σ(L)` is a legitimate, standard technique — it is Bayesian log-odds updating under conditional independence, the same math used in robotics occupancy-grid fusion, and it's computationally cheaper than Dempster-Shafer while being provably equivalent to it under uninformative priors. Two assumptions it relies on are not automatically true here and should be tracked as known limitations rather than presented as solved:
   - **Conditional independence across modalities** is violated when a shared confound (rain/fog) degrades seismic SNR and vision IR contrast simultaneously — the fusion formula would overstate confidence in that scenario. No fix planned for launch; flagged for future work (e.g., a shared "environmental degradation" state feeding an explicit weight adjustment).
   - **Availability-gated dropout** (a missing modality is excluded from the sum, not scored as negative evidence) is only statistically neutral if missingness is uncorrelated with the true event (MCAR). It plausibly is not: vision can be unavailable specifically due to fog/rain, and elephant activity is plausibly not independent of those same conditions. Kept as-is for launch (dropout is the simplest, most auditable behavior, and matches CONTEXT.md §7's "simplicity over complexity"), but documented here as an approximation, not a proven property, so it doesn't get treated as settled in a later design review.

## Alternatives considered

- **YOLO-nano-class (YOLOv8n/YOLO11n) TFLite on-device instead of FOMO** — real benchmark data on Cortex-A53 + Adreno 702 (same GPU class as QRB2210) shows ~360 ms per inference via GPU delegate, which comfortably fits this system's event-triggered latency budget (hundreds of ms to ~2 s). Rejected for now because it doesn't solve a problem FOMO actually has for this use case (presence detection, not counting/bbox precision) and it fragments tooling away from the Edge Impulse platform used for seismic/acoustic. Worth a bake-off later if FOMO's field recall disappoints.
- **MDv6-compact + custom classifier on-device now, instead of at launch** — rejected for timeline/toolchain-fragmentation reasons (see decision §5), not accuracy reasons; kept as the documented v2 fallback.
- **Dempster-Shafer evidence fusion instead of log-odds** — better at representing explicit ignorance and reconciling conflicting high-confidence sensors, but higher compute cost and conceptual overhead for a bounded MCU/MPU budget, and only diverges meaningfully from Bayesian log-odds when priors are informative in ways this system doesn't need yet. Rejected; revisit only if field data shows log-odds fusion is materially miscalibrated.
- **Learned meta-classifier / stacking for fusion weights** — empirically can outperform hand-set weights, but needs a labeled multi-modal field dataset that doesn't exist yet. Rejected for launch; realistic as a v2 upgrade once field events accumulate.

## Consequences

- Vision, seismic, and acoustic all train and deploy through Edge Impulse — one toolchain, one OTA path, matches the frozen "vision model fixed, OTA-updated centrally" design.
- Known, accepted risk: FOMO may under-detect herds or very-close-range elephants due to centroid overlap. Mitigated by resolution tuning and by not depending on count/size from vision alone; monitored explicitly during the August field test.
- Realistic accuracy expectations, to set correctly in DFO conversations and in contest documentation rather than overselling: seismic-alone field accuracy in natural/HEC habitat (not lab/zoo conditions) should be expected around **70–75%**, not the ~99% lab figure that sometimes gets quoted; vision-alone precision/recall at launch, given a contest-timeline dataset (likely 500–1,000+ images per class per lighting condition is the real target, not achievable in full for night conditions before the August field test), should be expected around **70–85%**. This is the actual quantitative case for why fusion — not any single modality — carries the reliability requirement, and it should inform alert-escalation and human-in-the-loop fallback thresholds, not just be a footnote.
- No published field precedent exists for a fused seismic+acoustic+vision elephant detector specifically — this project's fusion layer is genuinely novel, not a replication of a proven design. State this honestly in contest documentation rather than implying more precedent than exists.
- Two fusion-math limitations (correlated-noise confound, MCAR assumption in dropout) are now written down as known, accepted approximations rather than silently assumed — future work items, not blockers.

## Physical AI framing (addendum, not a separate decision)

Qualcomm's own "Brain + Nervous System" robotics reference architecture — the same vendor as QRB2210 — maps directly onto this project's reflex (STM32, always-on, real-time trigger) / cognition (QRB2210, event-driven perception+decision) split, which is a strong, specific precedent for calling this design "Physical AI" rather than just "embedded ML." Where the design is *not* the full closed-loop ideal some Physical AI literature describes: deterrence action itself (horn/LED trigger) is open-loop in the sense that it doesn't yet measure whether the elephant actually retreated and feed that back into perception thresholds. It's worth noting, though, that the frozen design already has real closed-loop adaptation on the *decision* side — the contextual bandit (CONTEXT.md §4: "never-repeat, stop-on-retreat," SQLite experience) already learns from deterrence outcomes and adapts action selection over time. So the honest scoping is: perception (fusion weights, thresholds) is fixed/centrally-updated, not self-adapting in the field; action selection (which deterrence to use, when to stop) already is. Contest and DFO documentation should describe it this way rather than either overclaiming full closed-loop autonomy or underselling the bandit's existing adaptation.

## Addendum, 29 Jul 2026 — geophone damping resistor

Decision #1 fixed the SM-24 → INA333 → Sallen-Key → STM32 ADC chain but left the geophone's own
electrical damping unaddressed. The SM-24's manufacturer datasheet (I/O Sensor Nederland, part
1004117) specifies open-circuit damping of only **h=0.25** at its 10 Hz natural frequency — badly
underdamped, meaning an unshunted coil rings for several cycles after any impulsive input rather
than producing a clean transient. Left unaddressed, this would corrupt the STA/LTA envelope shape
the footfall trigger depends on before any firmware or ML logic sees the signal.

**Decision:** wire a 1 kΩ shunt resistor directly across the SM-24's own two leads, upstream of the
burial cable, targeting h≈0.7 (the standard maximally-flat/minimal-overshoot damping target for
resolving a transient, as opposed to the flatter-passband target exploration seismology typically
uses). Derivation, using the datasheet's own transduction constant and its own worked example as a
check:

`R_shunt = RtBcfn / (fn × (h_target − h_open)) − Rc`

Datasheet values: `RtBcfn = 6,000 Ω·Hz`, `fn = 10 Hz`, `Rc = 375 Ω` (coil resistance),
`h_open = 0.25`. Formula check against the datasheet's own published calibration point
(1,339 Ω shunt → h=0.60): `6000/(10×0.35) − 375 = 1339.3 Ω` ✓. At the chosen `R_shunt = 1 kΩ`:
`h = 0.25 + 6000/(10×1375) = 0.686`, i.e. h≈0.69 — matching one of the two damping curves plotted
directly on the datasheet's own frequency-response and phase-lag graphs, not an extrapolation.
1 kΩ was chosen over the theoretically closer ~958 Ω because it is a standard value already in the
existing resistor kit (`hardware/bom/procurement-status.md`), and resistor tolerance is not
critical to this calculation — no new procurement needed.

**Placement matters:** the shunt must sit at the geophone end, not the amplifier end, so cable
resistance from the burial run doesn't add into the effective coil resistance and shift the
delivered damping away from this calculation. Reflected in `device/mcu/README.md`'s wiring table.

**Mechanical note, not electrical, but from the same datasheet:** all SM-24 parameters are
specified "in the vertical position," with a maximum 10° tilt for the rated 10 Hz Fn. Worth
carrying into the burial spike/pipe mounting geometry in `hardware/bom/procurement-status.md` §3,
not just the electrical design here.

**Deferred, not decided:** a small clamp/TVS across the differential pair for lightning/ESD
protection on the long buried cable run. Worth a field-hardening pass before the DFO deployment,
not a Rung 1 bench-test blocker — logged in `docs/KNOWN_GAPS.md`.

## Addendum, 30 Jul 2026 — INA333 input series resistors

A third-party SM-24+ADS1115 build (Core Electronics' Raspberry Pi geophone guide) wires two 1 kΩ
resistors in series between the sensor and the ADC's differential inputs, purely for ESD/transient
current-limiting — separate from that design's own damping resistor. Their topology has no
instrumentation amp, so the ADC is the first thing the buried-cable signal touches; ours interposes
the INA333, so the equivalent boundary in our chain is the INA333's own `IN+`/`IN-` pins, not the
ADS1115's `AIN0`/`AIN1` (which already sit downstream of the amp, inside the enclosure).

**Decision:** add a 1 kΩ resistor in series with each of the INA333's `IN+` and `IN-` leads,
between the damping-resistor node and the amp's inputs. Negligible effect on the signal — the
INA333's input impedance is high enough (typical CMOS instrumentation-amp input stage) that a 1 kΩ
series resistor forms an RC corner with parasitic input capacitance many orders of magnitude above
the 2–50 Hz seismic band — while giving the amp's internal input-ESD structures some current
limiting against a transient coupled onto the buried cable. Same 1 kΩ value as the damping
resistor and already in the kit; no new procurement.

**This is not a substitute for the deferred TVS/clamp above.** A resistor limits steady current; it
does not clamp voltage or absorb real transient energy the way a TVS diode or gas-discharge tube
would. A genuine lightning-induced surge on a long buried run could still exceed both the resistor's
rating and the INA333 input stage's clamp current despite this addition. Treat this as free, partial
insurance layered under the still-open TVS/clamp item, not a resolution of it — that gap stays open
in `docs/KNOWN_GAPS.md`.

Reflected in `device/mcu/README.md`'s wiring table.

## Evidence / sources

- O'Connell-Rodwell et al., "Seismic properties of Asian elephant vocalizations and locomotion" (JASA, 2000) — https://pubs.aip.org/asa/jasa/article/108/6/3066/554703/
- "Towards Long Range Detection of Elephants Using Seismic Signals" — https://arxiv.org/pdf/2406.05140
- "Event Detection and Classification for Long Range Sensing of Elephants Using Seismic Signals" — https://arxiv.org/pdf/2509.02920
- Edge Impulse, FOMO docs and limitations — https://docs.edgeimpulse.com/docs/edge-impulse-studio/learning-blocks/object-detection/fomo-object-detection-for-constrained-devices
- ultralytics/yolov5 issue #11487 (Cortex-A53 + Adreno 702 real latency numbers) — https://github.com/ultralytics/yolov5/issues/11487
- MegaDetector v5 vs v6 parameter counts and SPARROW edge deployment — https://www.animaldetect.com/blog/megadetector-v5-vs-v6 , https://zenodo.org/records/20348979
- Bayesian log-odds vs Dempster-Shafer equivalence/divergence — https://arxiv.org/pdf/2602.18872
- West Bengal AI-filtered camera-alert HEC deployment (field outcome data) — https://conbio.onlinelibrary.wiley.com/doi/abs/10.1111/csp2.70186
- Qualcomm "Brain + Nervous System" robotics/Physical-AI architecture — https://www.businesswire.com/news/home/20260104991116/en/
- I/O Sensor Nederland, SM-24 Geophone Element datasheet (P/N 1004117), damping/RtBcfn/coil
  resistance specifications — manufacturer PDF, 2006
- olewolf/geophone (Arduino SM-24 amplifier shield + frequency analyzer reference) —
  https://github.com/olewolf/geophone
- Core Electronics, "Set Up a Geophone with a Raspberry Pi and an ADC (ADS1115)" — SM-24+ADS1115
  reference build, source of the input series-resistor idea and independent 1 kΩ corroboration —
  https://core-electronics.com.au/guides/geophone-raspberry-pi/
