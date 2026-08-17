"""
EleTect X - main enclosure, first-pass parametric block-out.

Generated from hardware/cad/enclosure-design-concept.md's own written dimensions and its
"Suggested Fusion 360 modeling order" (main enclosure, steps 1-7). This is a geometric starting
point, not a finished or fit-verified design.

DIMENSION SOURCING - every component dimension used below is labeled as one of:
  REAL  - a number the design doc itself states
  EST   - a generic/typical size for that part family, NOT taken from the actual purchased unit's
          datasheet or a physical measurement. Flagged explicitly wherever used. Treat every EST
          value as something to replace with a real caliper measurement before trusting fit.
This distinction matters most in the tray layout check below, which is the actual point of this
revision: does everything the doc lists for the electronics tray really fit in the footprint the
doc allows for it, once every part is accounted for (not just the two largest)?

Explicitly NOT modeled in this first pass:
  - Side wing LED modules and their own sealed cavities
  - Eyebrow visor, mic port, IR/camera internal baffle
  - Tray rails / per-board mounting standoffs / service-loop wiring
  - Captive-screw bosses / asymmetric alignment chamfer on the hatch door
  - The horn housing (separate enclosure, ADR 0011 - doc says model this second)
  - Surface/cosmetic treatment

Units: millimeters throughout, matching the design doc.
"""

import cadquery as cq

# ---------------------------------------------------------------------------
# Envelope + shell
# ---------------------------------------------------------------------------

# REAL - "front face ~=180x150mm, total depth ~=110-130mm" (doc's own words: "a working number to
# design toward, not a measured fact yet" - using the doc's own stated range midpoint for depth).
ENV_WIDTH = 180.0    # X - front face width
ENV_HEIGHT = 150.0   # Z - front face height
ENV_DEPTH = 120.0    # Y - front-to-back, doc's 110-130mm range midpoint

WALL_T = 3.5  # REAL - "shell (hollow) it to a 3-4mm wall thickness", doc's own range midpoint
EDGE_FILLET = 6.0  # NOT from the doc - a modest fillet chosen only to match the described
                    # "continuous rounded-square tower" silhouette language, flagged as the one
                    # cosmetic (non-functional-dimension) choice in this file.

WINDOW_W = 120.0  # REAL - "~120x80mm" shared camera/IR window
WINDOW_H = 80.0
WINDOW_Z_OFFSET = 30.0  # NOT from the doc (doc gives no exact offset, only "upper-center") -
                         # estimate to place it in the upper third; true up once the head/body
                         # split is actually drawn.

# ---------------------------------------------------------------------------
# Tray components - the doc's own explicit list (enclosure-design-concept.md line 144-145):
# "UNO Q (68.85x53.34mm), TPA3116D2 amp board, DFPlayer PRO, Grove LoRa-E5, and the passives
# perfboard, all on one removable tray". Only the UNO Q has a doc-given dimension; the other four
# are EST - generic sizes for that part family, not the actual purchased unit's datasheet.
# INA333/ADS1115 (geophone signal-conditioning) and any other small breakouts are treated as
# living on the "passives perfboard" line item, not as separate tray footprints, matching how the
# doc itself groups them (it names the perfboard, not the individual small ICs, as the tray item).
# ---------------------------------------------------------------------------

TRAY_PARTS = [
    # (name, width, depth, height, source)
    ("UNO Q", 68.85, 53.34, 15.0, "REAL (W,D) / EST (H, doc gives no board thickness)"),
    ("TPA3116D2 amp board", 68.0, 55.0, 15.0, "EST - generic TPA3116D2 breakout footprint class"),
    ("DFPlayer PRO", 48.0, 40.0, 12.0, "EST - generic DFPlayer Pro-class module footprint"),
    ("Grove LoRa-E5", 45.0, 25.0, 10.0, "EST - generic Grove-format module footprint"),
    (
        "Passives perfboard (incl. INA333/ADS1115/passives)",
        80.0,
        40.0,
        10.0,
        "EST - sized generously to also carry the geophone signal-conditioning ICs the doc "
        "doesn't list as separate tray items",
    ),
]

TRAY_STATED_FOOTPRINT = (150.0, 100.0)  # REAL - doc's own "~150x100mm laid flat" tray footprint

# Simple non-overlapping row layout with a modest service/clearance gap between parts - not a
# real optimizer, just enough to get an honest "does this actually fit" bounding-box answer rather
# than an eyeballed one. Rows sorted by depth (Y) so the layout reads front-to-back sensibly.
LAYOUT_GAP = 6.0  # mm between adjacent parts and between rows - screws/standoffs/wiring clearance

def layout_tray_parts(parts, gap):
    """Greedy row-packing: place parts left-to-right, wrap to a new row when the running row width
    would exceed the stated tray width. Returns (positions, overall_bbox)."""
    stated_w, _ = TRAY_STATED_FOOTPRINT
    positions = []
    row_x = 0.0
    row_y = 0.0
    row_depth = 0.0
    max_x = 0.0
    for name, w, d, h, source in parts:
        if row_x > 0.0 and (row_x + w) > stated_w:
            row_y += row_depth + gap
            row_x = 0.0
            row_depth = 0.0
        positions.append((name, row_x, row_y, w, d, h, source))
        row_x += w + gap
        row_depth = max(row_depth, d)
        max_x = max(max_x, row_x - gap)
    total_depth = row_y + row_depth
    return positions, (max_x, total_depth)


tray_positions, tray_bbox = layout_tray_parts(TRAY_PARTS, LAYOUT_GAP)

print("=" * 70)
print("TRAY LAYOUT CHECK - all 5 doc-listed components, real gaps between them")
print("=" * 70)
for name, x, y, w, d, h, source in tray_positions:
    print(f"  {name:<45s} {w:6.1f}x{d:5.1f}mm  @ ({x:6.1f},{y:6.1f})  [{source}]")
print(f"\n  Doc's stated tray footprint:  {TRAY_STATED_FOOTPRINT[0]:.0f} x {TRAY_STATED_FOOTPRINT[1]:.0f} mm")
print(f"  Actual footprint needed:      {tray_bbox[0]:.1f} x {tray_bbox[1]:.1f} mm")
fits = tray_bbox[0] <= TRAY_STATED_FOOTPRINT[0] and tray_bbox[1] <= TRAY_STATED_FOOTPRINT[1]
print(f"  Fits within doc's stated footprint: {'YES' if fits else 'NO - see note below'}")
print("=" * 70)

# ---------------------------------------------------------------------------
# Reference solids - MPPT + battery (doc's step 1: block these out first, they set the interior
# envelope), plus the tray parts laid out above, all as distinct reference bodies. None of these
# are cut into the shell - this pass blocks out where things go, it does not model mounting
# clips/standoffs.
# ---------------------------------------------------------------------------

MPPT_DIMS = (138.0, 79.0, 38.0)     # REAL - "MPPT controller (amiciSmart 10A, 138x79x38mm)"
BATTERY_DIMS = (75.0, 70.0, 38.0)   # REAL (W,D) / EST (H) - doc: "75x70mm footprint... typically
                                     # runs ~=35-40mm thick" - thickness explicitly unconfirmed in
                                     # the doc itself, using its own stated midpoint estimate.

# Depth-stack layering, doc's own numbers (front to back): standoff ~20-25mm, tray ~25-30mm,
# battery+MPPT layer ~35-40mm.
STANDOFF_DEPTH = 22.5
TRAY_DEPTH = 27.5
POWER_LAYER_DEPTH = 37.5

HATCH_W = 130.0
HATCH_H = 95.0
RABBET_STEP = 3.0
RABBET_WALL = 4.0

BOSS_DIAMETER = 14.0
BOSS_HEIGHT = 9.0
BOSS_X_OFFSET = 60.0
BOSS_Z_OFFSETS = (45.0, -45.0)

VENT_DIAMETER = 12.0
GLAND_DIAMETER = 14.0

half_w, half_h, half_d = ENV_WIDTH / 2, ENV_HEIGHT / 2, ENV_DEPTH / 2

# --- Shell ---
outer = cq.Workplane("XY").box(ENV_WIDTH, ENV_DEPTH, ENV_HEIGHT).edges("|Z").fillet(EDGE_FILLET)
shell = outer.shell(-WALL_T)

shell = (
    shell.faces("<Y")
    .workplane(centerOption="CenterOfBoundBox")
    .center(0, WINDOW_Z_OFFSET)
    .rect(WINDOW_W, WINDOW_H)
    .cutThruAll()
)

rear_face_y = half_d
boss_points = [(x, z) for x in (-BOSS_X_OFFSET, BOSS_X_OFFSET) for z in BOSS_Z_OFFSETS]
bosses = (
    cq.Workplane("XY").workplane(offset=rear_face_y).pushPoints(boss_points)
    .circle(BOSS_DIAMETER / 2).extrude(BOSS_HEIGHT)
)
shell = shell.union(bosses)

shell = shell.faces(">Y").workplane(centerOption="CenterOfBoundBox").rect(HATCH_W, HATCH_H).cutThruAll()
shell = (
    shell.faces(">Y").workplane(centerOption="CenterOfBoundBox")
    .rect(HATCH_W + 2 * RABBET_WALL, HATCH_H + 2 * RABBET_WALL).cutBlind(-RABBET_STEP)
)

shell = (
    shell.faces("<Z").workplane(centerOption="CenterOfBoundBox")
    .pushPoints([(-25.0, 20.0), (25.0, 20.0)]).hole(GLAND_DIAMETER)
)
shell = (
    shell.faces("<Z").workplane(centerOption="CenterOfBoundBox").center(0, -20.0).hole(VENT_DIAMETER)
)

# --- Power layer reference solids (MPPT + battery), stacked front-to-back per the doc ---
rear_wall_inner_y = half_d - WALL_T
power_layer_front_y = rear_wall_inner_y - POWER_LAYER_DEPTH

mppt_w, mppt_d, mppt_h = MPPT_DIMS
battery_w, battery_d, battery_h = BATTERY_DIMS

mppt_ref = (
    cq.Workplane("XY").box(mppt_w, mppt_d, mppt_h)
    .translate((0, power_layer_front_y + mppt_d / 2, -half_h + WALL_T + mppt_h / 2))
)
battery_ref = (
    cq.Workplane("XY").box(battery_w, battery_d, battery_h)
    .translate((0, power_layer_front_y + mppt_d + 5.0 + battery_d / 2, -half_h + WALL_T + battery_h / 2))
)

# --- Tray layer reference solids - placed using the real layout computed above, centered in the
# tray's own depth band (front of standoff layer, behind the window standoff) ---
tray_front_y = -half_d + WALL_T + STANDOFF_DEPTH
tray_x_origin = -tray_bbox[0] / 2  # center the packed layout on X
tray_y_origin = tray_front_y

tray_bodies = []
for name, x, y, w, d, h, source in tray_positions:
    body = (
        cq.Workplane("XY").box(w, d, h)
        .translate(
            (
                tray_x_origin + x + w / 2,
                tray_y_origin + y + d / 2,
                -half_h + WALL_T + h / 2,
            )
        )
    )
    tray_bodies.append((name, body))

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

out_dir = "/home/claude/enclosure_cad"
shell.val().exportStep(f"{out_dir}/main_enclosure_shell.step")
cq.exporters.export(shell, f"{out_dir}/main_enclosure_shell.stl")
mppt_ref.val().exportStep(f"{out_dir}/reference_mppt_controller.step")
battery_ref.val().exportStep(f"{out_dir}/reference_battery_pack.step")

assy = cq.Assembly()
assy.add(shell, name="main_enclosure_shell", color=cq.Color(0.25, 0.55, 0.35, 0.55))
assy.add(mppt_ref, name="reference_MPPT_controller", color=cq.Color(0.85, 0.25, 0.25, 1.0))
assy.add(battery_ref, name="reference_battery_pack", color=cq.Color(0.2, 0.35, 0.85, 1.0))
for name, body in tray_bodies:
    safe_name = name.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "-")
    assy.add(body, name=f"reference_{safe_name}", color=cq.Color(0.9, 0.65, 0.15, 1.0))

assy.save(f"{out_dir}/main_enclosure_assembly.step")

print("\nExport complete.")
print("Shell bounding box:", shell.val().BoundingBox())
