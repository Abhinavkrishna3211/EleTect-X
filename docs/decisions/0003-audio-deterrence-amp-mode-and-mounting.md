# ADR 0003: Single BTL amplifier channel (not PBTL) and horn flush-mounted in the main enclosure

- **Status:** accepted
- **Date:** 2026-07-26

## Context
CONTEXT.md §3 specifies the audio deterrence chain as: `STM32 → DFPlayer-PRO → TPA3116D2 (PBTL)
→ 8Ω horn (Ahuja SUH-15, external-mounted)`. Two parts of that line needed re-checking once real
component numbers and a real target SPL were worked out, rather than carried forward unexamined:
the PBTL amplifier mode, and "external-mounted" as a separate box from the main enclosure.

**Target SPL.** The closest published, field-validated reference is Thuppil & Coss (*Oryx*,
2015/16): a playback deterrent system for wild Asian elephants (*Elephas maximus*) in southern
India, using a 10-channel MP3 player + 200 W amp + horn, delivering **105 dB peak SPL at 1 m**,
achieving 90-100% deterrence with tiger-growl playback. This is the number our own system needs
to clear, not an arbitrary target.

**Amplifier math.** TI's TPA3116D2 datasheet rates 2×30 W into 8Ω BTL, but at a **24 V** supply.
Our system runs off the 4S LiFePO4 rail at **12.8 V** nominal. Class-D output scales roughly with
V², so at 12.8 V a single BTL channel lands around 8–12 W into 8Ω — not 30 W. PBTL bridges both
channels into one load, roughly doubling effective drive voltage; at 12.8 V that pushes toward
25–30 W into 8Ω.

**Speaker rating.** Ahuja's own datasheet rates the SUH-15 at 8Ω: **15 W RMS / 23 W Max**, SPL
106 dB/1W/1m (118 dB/15W/1m), freq. response 275–7,000 Hz, IP66, 1.50 kg, 253×152×284mm (ABS horn
flare).

Putting these together: a single BTL channel (~8–12 W) into the SUH-15 already yields roughly
115–117 dB at 1 m — comfortably above the 105 dB proven-effective reference, with margin to
spare. PBTL (~25–30 W) would exceed the horn's own 23 W max rating, risking diaphragm damage
under a sustained deterrent burst, for SPL headroom the deterrence goal does not need.

**Alternative speakers evaluated.** Two TOA double re-entrant paging horns (SC-610, SC-615) were
sourced and compared in full against the SUH-15 — official datasheets, live stock, and price at
a verified Indian reseller (Fire Supplies):

| | Ahuja SUH-15 | TOA SC-610 | TOA SC-615 |
|---|---|---|---|
| Power | 15W/23W max | 10W | 15W |
| SPL | 106dB/1W/1m | 110dB/1W/1m peak | 112dB/1W/1m peak |
| Freq. response | 275–7,000Hz | 315–12,500Hz | 280–12,500Hz |
| IP rating | IP66 | IP65 | IP65 |
| Dimensions | 253×152×284mm | 172×161×188mm | 222×179×234mm |
| Weight | 1.50kg | 1.0kg | 1.1kg |
| Price (verified, Fire Supplies) | ₹1,450–3,150 | ₹8,850 | ₹9,676 |

Both TOA units are smaller, lighter, and more sensitive per watt. But neither closes a
requirement gap: the SUH-15 already exceeds the 105 dB proven-effective reference by 10dB+, so
the TOA sensitivity advantage buys compactness only, not additional deterrence effectiveness.
Given CONTEXT.md §7's explicit engineering principles (cost-effectiveness, manufacturability,
scalability, "reject gimmicks... justify every non-trivial choice") and that this is a real
multi-node forest-boundary deployment (§6: nodes every 120–150 m) rather than a single unit, a
3–6× per-speaker cost premium bought for a benefit already covered is not justified.

**Compactness, addressed separately from part choice.** A real commercial precedent exists for a
single, visually-unified enclosure housing both light and sound deterrent hardware: Kyari's
ANIDERS (1,250+ units deployed across 20+ Indian states, published field effectiveness 80% on
elephants). Its own product photography shows the horn/light modules built into one box face,
not a separate housing on a cable. This confirms the "one visible unit" goal is achievable through
enclosure design, without needing a smaller speaker part.

**Safety and nuisance, checked against real thresholds, not assumed.** Terrestrial-mammal
hearing-damage literature places permanent threshold shift onset around 130–140 dB SPL for brief
pulses; our system's ~115–117 dB at 1 m drops to roughly 85–95 dB at the 10–30 m range a node
actually triggers from, well under injury thresholds and in the same range as the ethically-used
Thuppil & Coss field system. Separately, WHO's outdoor nighttime residential guideline is ≤40–45
dB LAeq at a facade — a brief deterrent burst is not continuous exposure, but node siting must
still keep the horn face a reasonable standoff distance from the nearest home; this is a
deployment/siting guideline for the install team, not a hardware change.

## Decision
1. Drive the horn from a **single BTL channel** of the existing TPA3116D2 board, not PBTL. No new
   amplifier purchase is required — the existing board is retained, just used differently.
2. Software-limit amplifier gain to roughly **6–8 W** delivered, rather than the channel's full
   ~12 W. At this level the SUH-15 still produces ~117–119 dB at 1 m — well above the 105 dB
   reference — while running with real thermal headroom under its 23 W max rating, appropriate
   for a system expected to fire repeatedly over a multi-year field deployment.
3. **Retain the Ahuja SUH-15** (not the TOA SC-610/615) as the deterrence horn. The TOA
   comparison is documented above and rejected on cost-effectiveness/scalability grounds, not
   technical inadequacy — revisit only if enclosure layout proves the SUH-15's footprint a hard
   physical blocker once real dimensions are in hand.
4. Change "external-mounted" to **flush-mounted into one face of the single sealed enclosure**
   (gasketed at the horn-to-wall joint), rather than a separate box on a cable. This keeps full
   acoustic fidelity (no frequency-response compromise from a smaller driver) while achieving a
   single visually-unified unit, matching the precedent already proven by Kyari's ANIDERS.
5. Add a firmware-level cap on burst duration and a cooldown between triggers, both as an animal-
   welfare safeguard and to bound battery draw.

## Alternatives considered
- **PBTL bridging (frozen spec):** rejected. Exceeds the SUH-15's 23W max rating at our actual
  12.8V rail for no deterrence benefit — single BTL channel already clears the proven-effective
  SPL reference with margin.
- **TOA SC-610 / SC-615 double re-entrant horns:** rejected. Real, verified upgrade on
  sensitivity/size/weight, but the SPL/frequency gain is not needed (SUH-15 already exceeds the
  requirement), and the 3–6× cost premium works against this project's own cost-effectiveness
  and scalability principles at fleet scale. Documented for reconsideration if enclosure
  dimensions later force the issue.
- **Compact self-amplified horns (e.g. Speco ASPC20, 500Hz–5kHz response):** rejected. Frequency
  response starts too high, cutting most of the validated deterrent content (tiger/leopard growl
  energy ~300–500Hz, disturbed-honeybee buzz 100–600Hz) — would undermine the actual mechanism
  the deterrent depends on to save enclosure volume.
- **Separate external speaker housing (frozen spec's original intent):** rejected in favor of
  flush-mounting for industrial design reasons (single unified visible object) — no acoustic or
  cost difference, pure enclosure-layout decision.

## Consequences
+ No new amplifier purchase; existing TPA3116D2 board retained.
+ SUH-15 retained; cheaper and more scalable across a multi-node fleet than either TOA option.
+ Deterrence SPL (~117–119dB/1m at the software-limited gain) clears the only real published
  field-validated benchmark (105dB/1m, Thuppil & Coss) with comfortable margin.
+ Running below the horn's max rating improves long-term reliability across repeated field
  triggers over a multi-year deployment.
+ Single-enclosure industrial design achieved without an acoustic fidelity trade-off.
− Enclosure design must accommodate the SUH-15's footprint (253×152×284mm) flush-mounted into one
  face — larger than either TOA alternative would have required. Revisit ADR if this proves
  infeasible once real enclosure dimensions are drawn.
− Node siting (horn standoff distance from residences) needs to be documented as an install
  guideline, not just a hardware spec — follow-up for `docs/deployment/`.
− Firmware needs the gain-limit, burst-duration cap, and trigger cooldown implemented; not yet
  built.
