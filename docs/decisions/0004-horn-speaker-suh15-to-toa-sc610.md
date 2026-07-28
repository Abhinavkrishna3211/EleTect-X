# ADR 0004: Switch horn from Ahuja SUH-15 to TOA SC-610 — compactness overrides the earlier cost call

- **Status:** superseded by ADR-0005
- **Date:** 2026-07-28

## Context
ADR 0003 compared the Ahuja SUH-15 against the TOA SC-610/SC-615 on full specs, price, and stock, and
kept the SUH-15 on cost-effectiveness/scalability grounds — the TOA units were acknowledged as a real
compactness upgrade but rejected because "the TOA sensitivity advantage buys compactness only, not
additional deterrence effectiveness." That ADR explicitly flagged its own reversal condition: "revisit
only if enclosure layout proves the SUH-15's footprint a hard physical blocker once real dimensions are
in hand."

That condition has now been met. Real enclosure concept work (`hardware/cad/enclosure-design-concept.md`)
shows the SUH-15's 253×152×284mm footprint forces roughly a 300×220mm face and ~330mm depth — the horn
alone dictates an enclosure larger than every other component combined. The project owner has raised
wanting a genuinely compact, small, aesthetically refined product repeatedly across this build (most
recently: the SUH-15 "destroyed" the compact design vision). This isn't a new preference surfacing once —
it's the same concern recurring enough times that it should be treated as a real requirement, not noise.

## Decision
Switch to the **TOA SC-610** (172×161×188mm, 1.0kg, ~₹8,850, 110dB/1W/1m peak SPL, 315–12,500Hz response).
Its SPL clears the 105dB Thuppil & Coss field-validated reference with more margin per watt than the
SUH-15 did, so the ADR 0003 single-BTL-channel, no-new-amplifier, gain-limited approach carries over
unchanged — if anything, less amplifier headroom is needed, not more. Its smaller, more cube-like
footprint (versus the SUH-15's elongated horn shape) is what actually unlocks a compact enclosure design:
roughly a 200–220mm-class form instead of a ~330mm-deep one.

**On reversing the cost call specifically:** at the current single/few-node prototype and contest-
submission stage, the ~₹6,000–7,500 premium over the SUH-15 is a small fraction of total system cost, and
it buys a materially better product for both contests' Presentation/Creativity scoring as well as the
thing the project owner actually asked for. ADR 0003's cost-effectiveness-at-scale concern remains valid
for a future 100+ unit production run and should be revisited then, not now — by then, bulk TOA pricing
or a cheaper compact alternative may also exist. This is a scale-dependent call, not a permanent one.

## Alternatives considered
- **TOA SC-615:** rejected — larger, heavier, and pricier than the SC-610 for SPL headroom this
  deployment doesn't need, the same logic ADR 0003 used against the SUH-15's own excess margin.
- **Keep the Ahuja SUH-15:** rejected — technically fine (ADR 0003 already proved that), but directly
  conflicts with the compactness/aesthetic priority now stated clearly enough, and often enough, to treat
  as a real requirement rather than a nice-to-have.
- **Compact generic ABS PA horn (₹400–700):** still rejected, same reason ADR 0003 gave — its frequency
  response cuts into the validated deterrent content (tiger/leopard growl energy ~300–500Hz, disturbed-
  honeybee buzz 100–600Hz).

## Consequences
+ Enclosure envelope drops from ~330mm depth / ~300×220mm face to roughly a 200–220mm-class compact form.
+ Lighter (1.0kg vs 1.5kg) — less pole-mount cantilever stress on the front-face joint, less print
  material and time.
+ Higher per-watt sensitivity gives more SPL margin at the same low, gain-limited amplifier power from
  ADR 0003.
− ~₹6,000–7,500 more per unit at prototype scale than the SUH-15 — revisit if/when this reaches a
  production run.
− Re-verify current SC-610 stock, lead time, and genuine-seller pricing before ordering — ADR 0003
  sourced it via Fire Supplies; confirm that's still current before placing the order.
− `hardware/bom/bom.md` §4 and `hardware/cad/enclosure-design-concept.md` need updating to the new part
  and dimensions (done alongside this ADR).
