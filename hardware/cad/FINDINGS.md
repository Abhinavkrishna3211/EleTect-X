> **Superseded, 20 Aug 2026.** This CadQuery pass was never the manufacturing source. The real
> enclosure was hand-modeled in Fusion 360 and is now in manufacturing — see
> `hardware/cad/eletect_x_final.f3z` (native Fusion archive) and `eletect_x_final.step` (neutral
> interchange export, timestamped 2026-08-20T15:38 by Autodesk's own translation framework). The
> files below (`main_enclosure.py`, `main_enclosure_*.step/.stl`, `reference_*.step`) are left as-is
> for historical reference — they still carry the old amiciSmart MPPT dimensions and should not be
> treated as current design geometry.

# Main enclosure — first-pass CAD block-out and a real tray-footprint finding

Generated 15/16 Aug (overnight, no hardware/user presence needed) from
`hardware/cad/enclosure-design-concept.md`'s own written dimensions and its "Suggested Fusion 360
modeling order." This is a geometric starting point built with CadQuery (parametric CAD-by-code,
exports real STEP files Fusion 360 opens natively) — not a finished design, not fit-checked against
physical parts.

## Files

- `main_enclosure_shell.step` / `.stl` — the structural shell only: rounded-tower block-out,
  camera/IR window cutout, rear-wall pole-mount bosses, hatch opening with a rabbet-step ledge,
  bottom-face vent + cable gland holes. Follows the design doc's own steps 1–7 modeling order.
- `main_enclosure_assembly.step` — the shell plus every reference solid below, as distinctly
  colored/named bodies in one file, positioned where each part would sit.
- `reference_mppt_controller.step`, `reference_battery_pack.step` — standalone reference solids.

## Dimension sourcing — what's real vs. estimated

Every dimension is labeled in `main_enclosure.py`'s own comments as one of:

- **REAL** — a number the design doc itself states (envelope, wall thickness, window size, UNO Q's
  68.85×53.34mm, MPPT's 138×79×38mm, battery's 75×70mm footprint).
- **EST** — a generic size for that part family, not the actual purchased unit's datasheet or a
  physical measurement (TPA3116D2 amp board, DFPlayer PRO, Grove LoRa-E5, the passives perfboard,
  and the height/thickness of several REAL-footprint parts the doc doesn't give a height for).
  Every EST value needs a real caliper measurement before anyone trusts fit against it.

## The actual finding: the tray, as specified, is tighter than the doc assumed

The design doc lists exactly five things for the electronics tray — UNO Q, TPA3116D2 amp board,
DFPlayer PRO, Grove LoRa-E5, and the passives perfboard — inside a stated "~150×100mm laid flat"
footprint. Nobody had actually laid all five out together before now; the doc's own step 1 only
calls for blocking out the two *largest* parts (MPPT, battery) as reference solids.

Doing a real (if simple — greedy row-packing, not a true optimizer) layout of all five parts with a
modest 6mm service/clearance gap between each:

| Part | Size | Source |
|---|---|---|
| UNO Q | 68.85×53.34mm | REAL |
| TPA3116D2 amp board | 68×55mm | EST |
| DFPlayer PRO | 48×40mm | EST |
| Grove LoRa-E5 | 45×25mm | EST |
| Passives perfboard (+ INA333/ADS1115) | 80×40mm | EST |

**Needs ≈143×147mm. The doc's stated allowance is 150×100mm.** Width fits with a little room;
the other axis is short by about 47mm (~47% over budget) once every part and a realistic gap
between them is actually accounted for, not just the two biggest pieces.

This is not proof the enclosure is broken — three of the five sizes are estimates, not measured
parts, and a real layout (not a greedy row-pack) could nest things more efficiently, especially if
the perfboard is split or some parts are allowed to overlap in height on a second small shelf. But
it's a real, code-verified signal that the tray's assumed footprint should be re-checked once real
part measurements exist, before committing PETG to it — exactly the kind of thing worth catching
before Fusion 360 time is spent on a footprint that turns out too small.

## Explicitly not modeled in this pass

Side wing LED modules and their sealed cavities, the eyebrow visor, mic port, IR/camera baffle,
tray rails and per-board standoffs, the hatch door's captive-screw bosses and alignment chamfer,
the horn housing (separate enclosure per ADR 0011 — the doc says model the main enclosure first),
and all surface/cosmetic treatment. The design doc's own modeling order covers these next.

## Recommended next steps

1. Get real caliper measurements for the four EST-labeled tray parts once they're in hand —
   this single step turns most of this file's uncertainty into fact.
2. Re-run the layout check (or do it directly in Fusion 360) with real numbers; if the ~47mm
   overage holds, the tray footprint (or the front-face envelope) needs to grow, or the perfboard
   needs to be split/stacked rather than laid flat as one piece.
3. Open `main_enclosure_shell.step` in Fusion 360 as the actual starting body for the modeling
   order's remaining steps (8–9: tray rails, vent/gland detailing) — it's real, editable geometry,
   not a picture of one.
