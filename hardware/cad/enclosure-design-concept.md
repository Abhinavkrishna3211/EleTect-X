# Node enclosure — design concept for Fusion 360

A starting concept to model from, not a finished drawing. Diagrammed in chat alongside this doc (front
view + side cutaway) — this file is the buildable spec behind that picture. Update it as real dimensions
come in (measure the actual Ahuja SUH-15 once you have it — don't trust the datasheet blindly).

## The core idea (back to the Ahuja SUH-15 — ADR 0005)

**Revised again 28 Jul 2026.** A brief detour (ADR 0004) swapped the horn to the smaller TOA SC-610 to
unlock a more compact enclosure. Reverted (ADR 0005) — that traded a form-language problem for a 3–6x
parts-cost increase that contradicts the project's own cost-effectiveness/scalability principle and adds
real money at DFO fleet scale (nodes every 120–150m, per CONTEXT.md §6). Back to the **Ahuja SUH-15**
(253×152×284mm, 1.5kg), which is bigger than every other component combined, so it drives the whole
enclosure's size — the compactness problem gets solved through **form language** instead (two-volume
sentinel shape, contrasting visor band, true tapered horn cutout — see below), not by paying more for a
smaller part.

One sealed front-loaded shell: everything that needs to see, hear, or broadcast outward (camera, IR, horn,
LEDs, mic) sits on one front face; everything passive (compute, battery, wiring) lives behind/around the
horn's body in the depth it already needs. A rear hatch gives full service access without breaking the
front face's seal.

**Rough envelope:** front face ≈300×220mm, total depth ≈330mm (the horn's 284mm plus wall/gasket margin).
Confirm against the CR-M4's actual bed size before committing — this should fit in one print, with the
smaller detail parts (head module, mesh retainers, solar arm) on the A1.

## Form language, take three — one continuous tower, not assembled parts

The two-volume "sentinel" direction below was a mistake in the other direction: multiple distinct
bolted-together volumes (head, body, side wings) read as an assembly of parts, not a resolved product,
both to an image generator and honestly to the eye. The project's own earlier concept render (the
`EleTect X` infographic hero shot) already had the right answer and didn't need reinventing: **one
continuous rounded-square tower**, no hard seams between sub-volumes. Visual interest comes from surface
treatment, not from breaking the silhouette into separate stuck-on pieces:

- A domed cap at the top with a short antenna stub.
- A loose, slightly scattered constellation of small LEDs around the camera — not a neat symmetric row,
  which is part of what made earlier attempts feel generic.
- LED light strips running down both side edges, **embedded in the body's own rounded edge chamfer**, not
  separate screw-on wing modules — same wide-angle deterrence coverage benefit, achieved as a surface
  detail on one continuous shell instead of a bolted-on part.
- A large circular mesh grille flush in the lower front face for the horn, clean and integrated rather
  than a dramatic separate taper — a subtle embossed emblem at its center is a nice touch, costs nothing
  structurally.
- Matte charcoal-black or deep forest-green finish (both already in scope per the original color options),
  status LEDs and cable glands clustered at the bottom edge.

This keeps every real engineering requirement from the sections below (flush-mounted SUH-15 per ADR 0003,
shared camera/IR window, mic away from the horn, thermal stratification, weatherproofing) — it changes how
those pieces are expressed on the surface, not what they are or where they sit functionally. Note the
original render's 210mm width is narrower than the SUH-15 needs (253mm) — widen the tower slightly to fit
the real part; the form language holds at the corrected width.

## Form language, take two (superseded above) — breaking the generic-box look

A rounded slab with parts stuck to one flat face reads as generic no matter how the parts are arranged —
that's a form problem, not a placement problem, and no amount of prompt-tuning fixes it. Four real moves,
each doing actual work rather than decoration:

- **Two volumes, not one.** A raised "head" (camera, IR, mic — LEDs moved out, see below) sitting
  slightly forward of and above a "body" (horn, electronics, battery), with a visible waist between them.
  This matches the real internal architecture — sensor cluster up front, everything passive behind — so
  it's honest form, not styling for its own sake. Same move that makes Nest/Arlo-style cameras read as
  purposeful rather than generic: a distinct "eye" separated from the "body."
- **LED deterrence moves to screw-on side wing modules, not flush front pods.** This is the change that
  actually breaks the box silhouette — small LED circles on a flat front face are still a flat front face
  no matter how they're arranged; a protruding module on each side is genuinely different geometry, not a
  surface detail. Each wing is a slim vertical fin, swept slightly forward, mounted flush to the left and
  right faces of the body with **visible screws along its mounting edge** — real fasteners, not hidden,
  so the object honestly reads as serviceable rather than molded as one blob. Each wing carries a vertical
  row of alternating cool-white and royal-blue LEDs (matches the original 4 white + 2 blue count from the
  BOM, split across both wings) angled outward for peripheral coverage, not just straight ahead. This also
  frees the front face to stay clean — head above, horn below, nothing else competing for attention — and
  it's a genuine echo of the original concept's "side LED modules, independently swappable" idea, just
  scoped to two modules instead of five.
- **A dark visor band across the head**, not one flat green surface. Camera, IR, and mic sit inside one
  contrasting band; the horn's body stays forest-green below it. One material break is a high-leverage fix
  for looking designed instead of extruded, and it's genuinely easy to execute — either a two-color print
  (swap filament at the layer where the band starts) or a painted/vinyl-wrapped band on a single-color
  print.
- **A true tapered horn flare**, not a flat mesh disc. The mouth should visibly recede — a real cone, not
  a circle with a grille texture — since a flat disc reads as "generic speaker" while a tapered flare
  reads as "horn." This is also just physically correct: the SUH-15 *is* a tapered horn, the enclosure
  cutout should say so.

**Practical note on the side wings:** each one needs its own small sealed cavity (own gasket, own short
cable run back to the LED driver on the tray) since it's a separate screw-on part penetrating the main
shell's wall — one more sealed interface than the flush-front version had. Worth it for the silhouette,
but budget real time for getting that seal right, and test-print one wing standalone before committing
both to the full assembly.

## Front face layout (facing the crossing, mounted ~2.5–3m up a pole)

- **Camera + IR window**, upper-center: one shared rectangular window (~120×80mm), clear cast acrylic/PC
  2–3mm, behind which the Arducam IMX462 and the 940nm IR board both sit side by side. One window, not
  two — simpler gasket, and both need the same IR-transparent path anyway. Standoff the IR board and
  camera a few mm off the window's inner face — direct contact becomes a condensation nucleation point
  and a differential-thermal-expansion stress point over years of heat cycling.
- **Printed eyebrow visor** above the camera/IR window: a small overhanging brow, angled to shed rain
  sideways rather than down the glass and to cut direct high-sun glare on the lens — a flat unshaded
  window in Kerala's midday sun will wash out footage and fog on rapid cooling after a downpour.
- **Horn mouth**, lower-center, dominant: flush-mounted per ADR 0003, its flare forms most of the front
  face's visual footprint — worth leaning into with the tapered-cone treatment below rather than fighting
  it. Its ~284mm body extends straight back into the enclosure's depth.
- **Stainless mesh grille across the horn mouth**, flush with the flare opening — without it the cone is
  an open invitation to wasps, ants, geckos, and wind-driven rain. Fine enough to keep insects out,
  open enough not to measurably attenuate the SPL you already sized in ADR 0003.
- **LEDs are not on the front face** — moved to the side wing modules, see below. Keeps the front face to
  exactly two things: the head (camera/IR/mic) and the horn. Nothing competes for attention.
- **Mic port**, in the head's visor band alongside the camera/IR: behind a water-repellent, acoustically-
  open membrane (Gore-type, same family as the pressure vent — not bare stainless mesh, which lets
  wind-driven rain through under pressure), positioned away from the horn so repeated close-range SPL
  doesn't fatigue the membrane over years.

## Side wing modules (LED deterrence, screw-on)

- One wing per side, mounted flush to the body's left and right faces, each a slim vertical fin swept
  slightly forward. Left wing: 2 cool-white + 1 royal-blue. Right wing: 2 cool-white + 1 royal-blue —
  4 white + 2 blue total, matching the BOM count, just relocated.
- **Visible screws along each wing's mounting edge** (SS-304, tamper-resistant heads) — real, honest
  fasteners rather than a hidden snap-fit, both for the serviceability story and because it's the detail
  that makes the object read as engineered rather than molded as one piece.
- Each wing gets its own small sealed cavity — own gasket at the wing-to-body seam, own short cable run
  back through a small internal grommet to the LED driver on the electronics tray. This is a genuinely
  separate sealed interface from the flush-front version, budget real assembly/test time for it.
- LEDs angled outward within each wing (not just forward) for real peripheral deterrence coverage — an
  animal approaching off-axis from the side sees light before it's directly in front of the camera, which
  the old flush-front layout couldn't really do.
- Each star PCB still backs onto a small aluminum heat-spreader close to the wing's outer wall — same
  thermal reasoning as before, just relocated with the LEDs.

## Depth stack (rear cutaway) — and why it's arranged this way thermally

- **Horn body** occupies the front-to-mid depth, tapering from its flared mouth back to the compact
  driver — fixed geometry from the part itself. Flush-mounting (ADR 0003) already put the driver/
  terminals *inside* the sealed cavity, which is a real plus: the electrically live end of the horn never
  sees rain directly, only the mouth does, and that's now meshed.
- Add internal printed cradle ribs under the horn's body, not just the flare rim, so the horn's ~1.5kg
  mass is carried by the structure rather than cantilevered off the thin front-face wall alone — repeated
  years of the horn's own vibration plus wind-sway on the pole will fatigue a rim-only joint.
- **Electronics tray**, below/around the horn body: UNO Q, TPA3116D2 amp, DFPlayer PRO, Grove LoRa-E5,
  and the passives perfboard, all on one removable tray that slides out through the rear hatch. Keep the
  LoRa module and its antenna toward the top-rear, away from the horn driver's magnet and the battery
  pack — both are metal masses close enough to detune a compact antenna if it's tucked right next to them.
  Use screw-terminal or locking connectors for anything carrying actuator signals, not friction-fit
  headers — the horn's own acoustic output is real vibration at close range, repeated for years.
- **Battery + BMS** sits low and to the rear, deliberately the coolest point in the box: heat rises, and
  the amp/IR/LED loads that actually generate heat sit up front near the top, so the natural convection
  inside the sealed cavity carries warm air up and away from the pack rather than over it. This is the
  right arrangement already — don't invert it for layout convenience later. Leave a few mm air gap
  between the battery and the MPPT controller rather than stacking them flush; both generate some heat
  under charge.
- **Rear hatch**: a rabbet/step joint at the seam, not a flush butt joint — the O-ring sits in a groove
  that's recessed a step back from the outer face, so wind-driven monsoon rain hitting the seam at an
  angle never reaches the gasket line directly. Use a UV-stable silicone O-ring specifically (matches the
  UV-stabilized PETG choice already made for the shell) — generic rubber degrades faster under Kerala's
  UV load and the seal is exactly the wrong place to save on part cost. Closed with tamper-resistant
  screws into brass heat-set inserts.
- **e-PTFE vent**: bottom face, recessed under a small printed rain lip. Bottom placement is correct for
  both rain-shedding and staying well clear of any ground-level standing water, though at a 2.5–3m mount
  height that's not a binding constraint anyway.
- **Cable glands** (PG7/PG9): bottom-rear cluster, geophone cable and solar feed. Route both with a
  **drip loop** — the cable dips down before it reaches the gland, so water runs off the low point of the
  loop instead of wicking straight along the jacket into the gland by capillary action. Easy to miss,
  a classic outdoor-electronics failure mode if skipped.
- **SS-304 pole bracket**: rear exterior, printed bosses reinforced with heat-set inserts for the actual
  metal bracket/U-bolt — the bracket carries the mounting load, not the PETG.

## Solar panel as a dual-purpose sun/rain canopy

Mount the solar panel on its own standoff arm *above* the main enclosure rather than flush on its roof.
Tilted toward the sun for yield, it also then acts as a shade canopy over the sealed box below it — a
fully sealed box with no active cooling will run 15–25°C above ambient in direct tropical sun even in a
light matte color, and that heat load stresses the battery, the gaskets, and every seal over a multi-year
deployment. One part, two jobs: this is the single highest-leverage fix in this recheck, cheaper and more
reliable than trying to add active cooling to a box that specifically needs to stay sealed.

## Other weatherproofing/mounting notes

- No flat horizontal exterior surfaces anywhere — every top-facing face gets at least a few degrees of
  slope, so nothing pools rainwater and breeds mosquitoes or grows algae.
- Keep the pole mount simple for the 3-person/<20min install target (CONTEXT.md §6): a clamp/U-bolt plus
  two tamper-resistant but tool-accessible bolts, mounted at a height a ranger can reach without a ladder
  for routine checks, above elephant trunk-reach height.
- Forward-looking, not a redesign item now: a basic lightning/surge grounding path for the pole and solar
  feed is worth a follow-up note in `docs/deployment/` before real field install — forest-edge poles under
  or near canopy are a real strike risk over a multi-year deployment, separate from the surge/reverse-
  polarity protection already in the power BOM.

## Cross-component interference review

Every subsystem in this box eventually shares a chamber with every other one — worth a deliberate pass
checking what one part does to its neighbours, not just whether each part individually works.

**Horn vs mic — the real conflict.** The horn puts out ~117–119dB SPL at 1m (ADR 0003); the INMP441 sits
in the same sealed cavity listening for gunshot/chainsaw signatures down to well below that. Two separate
problems, not one: airborne SPL will saturate/clip the mic's ADC and can fatigue its diaphragm over
repeated bursts across a multi-year deployment, and structure-borne vibration from the horn's body can
couple into the mic's PCB mechanically even if the air-path SPL at the mic is reduced. Fixes: mount the
mic on a face off the horn's acoustic axis (already true in the current layout — top corner, horn
lower-center), add a soft rubber grommet at the mic's mount point specifically to decouple structural
vibration rather than just relying on distance, and — this is a firmware item, not an enclosure one — gate
the mic input during an active deterrence burst plus a short settling tail, so the horn's own sound
doesn't get misread as a new acoustic event or corrupt whatever confidence score the acoustic corroboration
feeds into fusion.

**IR + camera — reflection, not just wavelength.** Wavelength match (940nm) was already locked, but a
shared window creates a second problem: an IR emitter sitting close to the lens axis behind one window
commonly reflects straight back into the lens as a washout hotspot, a known failure mode in cheap CCTV
housings that use a single unbaffled window for both. Add a small internal partition/baffle inside the
shared window cavity, between the camera lens and the IR board, tall enough to block the direct
reflection path without blocking either one's outward view/throw. Finish that whole window cavity's
interior in matte black — bare printed PETG is reflective enough at a shallow angle to bounce stray IR or
visible LED light into the lens and show up as flare in footage.

**Visible LEDs vs camera.** LEDs are already angled outward off the lens axis, which helps, but the
strobe is bright enough at night to affect the camera's own day/night IR-cut auto-switching if it's ever
close enough to read as "daylight" — worth checking on the bench once real parts are in hand, since a
mistimed IR-cut switch mid-capture would lose exactly the footage (animal reacting to the deterrent) you
most want for the public writeup.

**Electrical noise zoning.** The TPA3116D2 amp, the MPPT solar controller, and the IR/LED MOSFET gate
drivers are all switching-noise sources (class-D switching, buck conversion, gate switching respectively).
The geophone's INA333 front-end is a µV-level analog signal and the most vulnerable thing in the box to
that noise; the LoRa radio is the second most vulnerable, both to this noise and separately to physical
proximity with the horn's magnet and the battery pack (both can detune a compact antenna). Zone the
electronics tray into a **noisy half** (amp, MPPT, MOSFET drivers) and a **quiet half** (INA333/geophone
ADC input, mic connector, LoRa-E5 + antenna), physically separated across the tray rather than
interleaved, with short, direct wiring runs on the noisy side so switching noise has less trace length to
radiate from. A thin grounded partition (copper tape on a printed rib is enough) between the two halves
is cheap insurance if bench testing shows crosstalk.

**Minor:** the e-PTFE vent shouldn't sit directly in line with the horn driver's rear backwave — most of
that energy is already contained by flush-mounting the driver internally (ADR 0003), but there's no
reason to place the pressure-equalization membrane where it takes repeated pressure pulses from every
deterrence burst over a multi-year deployment when it could just as easily sit elsewhere on the bottom
face.

## Suggested Fusion 360 modeling order

1. Block out the horn as a reference solid first (real measured dimensions, not datasheet numbers) —
   everything else is sketched around it, not the other way around.
2. Sketch the front face profile with margins for the horn cutout, camera/IR window, LED windows, mic
   port, and the eyebrow visor.
3. Extrude the front shell, then shell (hollow) it to a 3–4mm wall thickness.
4. Cut the window/port openings.
5. Add interior mounting bosses/standoffs for the tray rails, horn cradle ribs, battery clamp, and PCB
   standoffs.
6. Model the rear hatch as its own body matching the shell's rear opening, with a rabbet step and a swept
   O-ring gasket groove (~3.5mm wide) set back from the outer seam.
7. Model the electronics tray as a slide-in shelf sized to pass through the rear opening, with cutouts/
   standoffs for each board, LoRa module positioned top-rear away from the horn magnet and battery.
8. Add the vent boss (small recess + rain lip) on the bottom face, and the gland bosses (drilled to
   PG7/PG9 thread size, ~12.5–16mm) at the bottom-rear, with a drip-loop channel modeled into the cable
   run.
9. Model the solar standoff arm and panel bracket last, positioned to shade the front-top of the main
   shell.
10. Before committing filament to the full shell, print just the horn-cutout + camera-window corner as a
    small test patch to confirm the fit.

## Print split

- **Front shell** (the largest single piece, ~300×220×~200mm): CR-M4, which has the bed for it.
- **Rear hatch + electronics tray**: Bambu A1.
- **Head module, LED pods, mic port cover, horn mesh retainer, solar standoff arm**: A1, small parts,
  easy iteration if a fit needs adjusting.

## On the photorealistic render

No Gemini or other image-generation tool is connected in this session — I checked the connector registry
and nothing matched. Two real options once you're further along: Fusion 360's own Render workspace can
produce an accurate photoreal shot directly from the actual model (geometrically correct, not an AI guess
at proportions), or you can connect an image-gen MCP yourself later via connector settings if you want a
quick concept render before modeling is done. The diagram in chat is the accurate stand-in for now.
