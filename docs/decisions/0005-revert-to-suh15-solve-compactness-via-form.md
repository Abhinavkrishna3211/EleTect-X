# ADR 0005: Revert to Ahuja SUH-15 — solve compactness through form language, not a costlier part

- **Status:** accepted
- **Date:** 2026-07-28

## Context
ADR 0004 switched the horn from the Ahuja SUH-15 to the TOA SC-610 to unlock a smaller, more compact
enclosure, reasoning that the compactness priority raised repeatedly during design work outweighed the
cost premium at prototype scale. On reflection, prompted by a direct question about contest impact, that
trade was wrong for two reasons stronger than "does it cost contest points":

1. **Neither contest's verified rubric scores cost or scalability directly** (Robu: Functionality 40 /
   Innovation 25 / Documentation 20 / Presentation 15; Hackster: Documentation 30 / BOM 20 / Schematics 15
   / Code 15 / Creativity 20) — so the swap bought nothing on that axis. But Technical/Project
   Documentation together are worth up to 50 points combined, and CONTEXT.md §7 states cost-effectiveness
   and scalability as core engineering principles. An ADR justifying a 3–6x cost increase mainly for
   aesthetics, sitting next to that stated principle, is a self-inconsistency a careful judge could
   reasonably notice.
2. **This isn't just a contest artifact — it's the actual deployment model.** CONTEXT.md's own spacing is
   nodes every 120–150m along a forest boundary, and the mission's priority order puts real DFO field
   deployment above winning either contest. At even 50 nodes, the SC-610 swap is roughly ₹375,000 in extra
   fleet cost versus the SUH-15 — a real number for a forest department budget, not a documentation
   nicety.

The actual problem the SC-610 swap was trying to solve — the enclosure reading as a generic "dumb box" —
turned out to be a form-language problem, not a size problem, and was already fixed separately: splitting
the shell into a raised head volume with a contrasting visor band, plus a true tapered horn flare instead
of a flat mesh disc. Those fixes apply just as well to the SUH-15's real dimensions.

## Decision
Revert to the **Ahuja SUH-15** (253×152×284mm, 1.5kg, ₹1,299–3,150) as the audio deterrence horn. ADR
0003's original reasoning — single BTL channel, no new amplifier, software gain-limited to ~6–8W, SPL
comfortably clearing the 105dB Thuppil & Coss reference — stands unchanged, since it was written for the
SUH-15 in the first place. Re-apply the sentinel form language (two-volume head/body split, dark visor
band, true tapered horn cutout, chamfered facets) from the enclosure concept doc to the SUH-15's actual
footprint rather than the SC-610's. `hardware/bom/bom.md` and `hardware/cad/enclosure-design-concept.md`
revert their dimensions and part references accordingly.

## Alternatives considered
- **Keep the TOA SC-610 (ADR 0004):** rejected on reflection — solves a form-language problem with a
  parts-cost solution, undermines the project's own stated cost-effectiveness/scalability principle, and
  meaningfully raises real fleet cost for the actual DFO deployment, all to fix something that didn't
  need a part swap to fix.
- **Split the difference (TOA SC-610 for the contest/demo unit, SUH-15 documented as the production
  spec):** rejected — running two different BOMs for "what we show" versus "what we'd actually deploy"
  is exactly the kind of inconsistency that hurts documentation credibility worse than either choice
  alone would.

## Consequences
+ Enclosure envelope returns to the SUH-15's real ~300×220×330mm footprint — larger than the brief SC-610
  detour, but the sentinel form language (two-volume split, visor band, tapered horn) means it no longer
  needs to look like a generic box at that size.
+ BOM and cost-effectiveness story stay internally consistent with CONTEXT.md §7 and with the real DFO
  fleet-scale economics.
+ No new part to source, verify stock for, or budget around — the SUH-15 sourcing already done under ADR
  0003 stands.
− Enclosure is heavier (1.5kg vs 1.0kg) and deeper than the brief SC-610 version — cradle ribs supporting
  the horn's body weight (already planned in the enclosure doc) matter more, not less.
− `hardware/bom/bom.md` and `hardware/cad/enclosure-design-concept.md` need reverting to SUH-15
  dimensions (done alongside this ADR).
