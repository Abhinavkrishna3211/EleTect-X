# ADR 0011: Split the passive horn driver into its own small housing, off the main enclosure

- **Status:** proposed
- **Date:** 2026-08-13

## Context

ADR 0003 flush-mounted the Ahuja SUH-15 (253×152×284mm, 1.5kg) into the main sealed enclosure, explicitly
rejecting a separate external speaker housing "for industrial design reasons (single unified visible
object) — no acoustic or cost difference, pure enclosure-layout decision." ADR 0005 reaffirmed that,
solving the enclosure's "generic box" look through form language (two-volume head/body split, contrasting
visor band, tapered horn cutout) applied to the SUH-15's real footprint, rather than by changing the part
or the layout.

Both of those ADRs were answering an aesthetic/industrial-design question — does the box look designed or
generic. Revisiting now for a different reason: the horn is, by the enclosure doc's own words, "bigger
than every other component combined, so it drives the whole enclosure's size." At 253×152×284mm and 1.5kg,
it forces a ~300×220×330mm main shell regardless of how small every other subsystem is — camera/IR window,
mic, LED cluster, UNO Q (68.85×53.34mm), DFPlayer PRO, Grove LoRa-E5, the geophone analog front end, the
6Ah battery pack, and the MPPT controller (138×79×38mm) are all individually modest. A single-node pole
install (CONTEXT.md §6: 3-person, <20 min) also gets measurably harder with a 1.5kg horn's weight and bulk
riding on the same rigid body as everything else, and wind-load on the pole scales with the enclosure's
frontal area — a real physical cost the earlier ADRs didn't weigh, since they were litigating appearance,
not install ergonomics or fleet-scale mounting practicality.

Separately, the enclosure doc's own "Cross-component interference review" already had to manage two real
problems created specifically by sharing one cavity with the horn: SPL/vibration fatiguing the INMP441 mic
(mitigated with a rubber grommet, off-axis mounting, and a firmware gate on the mic during deterrence
bursts), and the horn's magnet sitting close enough to the LoRa antenna to risk detuning it. Both are
mitigations for a problem that doesn't exist if the horn isn't sharing the box.

**Correction, 20 Aug 2026 (docs-currency, not a design change):** this ADR originally cited the amiciSmart
10A MPPT controller (138×79×38mm) among the parts staying in the main enclosure. ADR 0012 dropped that part
in favor of a manually-set XL4015 CC/CV buck module (real footprint ≈54×23×18mm) — the reference below is
updated to match; it doesn't change anything else this ADR decided.

## Decision

Move the **passive horn driver only** (the SUH-15 cone/body itself) into its own small IP66 housing,
connected to the main enclosure by ordinary 2-core speaker wire (already in the BOM, §4) through a gasketed
cable gland with a drip loop, matching the drip-loop practice already used for the geophone cable.

Everything else stays in the main enclosure: the TPA3116D2 amp, DFPlayer PRO, UNO Q, LoRa-E5, LED
deterrence, camera/IR, mic, geophone front end, battery, and MPPT controller. This is a deliberately
narrow cut — only the single bulky, purely mechanical/acoustic part moves, not the whole audio subsystem —
so it adds exactly one new sealed interface (the horn housing itself, plus one gland pass-through) rather
than re-litigating the whole electronics layout.

ADR 0003's electrical decision (single BTL channel, software gain-limited to ~6-8W, SUH-15 retained over
the TOA alternatives) is unchanged — this ADR only amends ADR 0003 point 4 ("flush-mounted into one face of
the single sealed enclosure") to "flush-mounted into its own small sealed housing, wired to the main
enclosure."

## Alternatives considered

- **Keep flush-mounted in the main shell (ADR 0003/0005, status quo):** rejected for this iteration — the
  bulk/weight/install-ergonomics cost is real and, on reflection, wasn't actually weighed by either earlier
  ADR, which were both answering a "does it look generic" question, not a "how heavy and awkward is this to
  mount" one.
- **Split all deterrence electronics (amp, DFPlayer, horn) into a second housing:** rejected — the horn body
  is the actual size driver; moving the amp and DFPlayer too would add sealed interfaces and wiring runs
  for parts that are already small, for no size benefit, and would complicate the noisy/quiet electrical
  zoning the enclosure doc already worked out for the tray.
- **Split the LEDs out as well:** not decided here — out of scope for this ADR, worth its own look once the
  main shell's new smaller footprint is actually drawn.

## Consequences

+ Main enclosure shrinks substantially — no longer sized around a 253×152×284mm/1.5kg part. Expect
  something closer to a compact camera-housing scale (rough order of magnitude, to be confirmed once
  drawn: 150-200mm class, not 300mm class), lighter, easier for a 3-person crew to mount within the
  CONTEXT.md §6 install-time target, and lower wind-load on the pole.
+ Removes the horn-vs-mic SPL/vibration interference problem structurally instead of managing it with a
  grommet and a firmware gate — one less thing that can degrade over a multi-year deployment.
+ Removes the horn-magnet-near-LoRa-antenna detuning risk from the main box.
- Adds one new sealed enclosure (small horn housing) and one new gasketed cable gland/drip-loop run —
  a real increase in the number of weatherproof interfaces to get right, each one a long-term moisture-
  ingress risk if done poorly.
- Adds field-install complexity: two housings to mount, aim, and keep aligned relative to each other
  instead of one rigid unit — a second thing that can loosen or shift over years on a forest-edge pole.
- Steps away from the "single unified visible object" industrial-design goal ADR 0003/0005 built around
  the Kyari ANIDERS precedent — a real cost for contest documentation/presentation scoring specifically,
  not for the actual DFO field deployment, which cares about reliability and install practicality, not
  silhouette.
- `hardware/cad/enclosure-design-concept.md` needs a real revision once this is drawn: new smaller main
  shell dimensions, a new small horn-housing design (its own gasket, mesh grille, cradle for the ~1.5kg
  driver), and the gland/drip-loop detail for the speaker-wire run.
- Speaker wire run length and gauge need picking once the physical layout (how far the horn housing sits
  from the main box) is actually decided — not yet specified.
