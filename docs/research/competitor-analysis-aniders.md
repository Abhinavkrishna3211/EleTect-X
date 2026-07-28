# Competitor analysis: Kyari Innovations ANIDERS

- **Date:** 2026-07-28
- **Status:** living document — update as new data surfaces

## Summary

ANIDERS (Animal Intrusion Detection and Repellent System), made by Kyari Innovations Pvt.
Ltd. (Uttar Pradesh), is the closest existing commercial product to EleTect X — a solar-powered,
pole-mounted device that detects wildlife intrusion and repels it with light and sound. It has
real field deployment (20+ Indian states, WWF/Bhutan pilot sites, WWF India, IUCN, UNDP, WII,
Elephants Without Borders as named partners) and a patent. It is a legitimate competitor, not a
strawman, and an independent field study of its Bhutan deployment gives a rare, non-marketing
look at where it actually falls short. Everything below is sourced; assumptions are marked as
such.

## What ANIDERS actually is

- **Detection:** two sensor variants — PIR (passive infrared, motion-heat based) and AIR (active
  infrared, break-beam transmitter/receiver pair). No seismic, acoustic, or vision sensing.
- **Deterrence:** light + sound alarm only. Manufacturer states 40 different sound/light
  combinations to reduce habituation.
- **Power:** solar-charged, standalone, no grid dependency.
- **Communication:** optional GSM/mobile alerts on some models; no mesh/LoRa networking between
  nodes described anywhere in their material.
- **Intelligence:** no on-device classification or sensor fusion. Kyari's own site describes
  "camera trap and AI" as a *future* product direction, confirming the current shipping product
  has neither.
- **Physical form (estimated from installation photos, not a spec sheet):** ~25–30cm cube head
  unit, small solar canopy (~40–50cm) overhanging the box, mounted at ~2.3–2.8m on a wood,
  concrete, or painted-pipe post depending on installer. Metal enclosure with louvered vents for
  the sensor windows — not a sealed molded-plastic housing.
- No published dimensions, weight, or IP rating exist on Kyari's own site, their dealer pages, or
  their patent-branded microsite. This is itself worth noting: EleTect X publishing a real IP66+
  spec, weight, and dimensions in its own docs is a documentation advantage on day one.

## Pricing (from Kyari Innovation Pvt. Ltd., 2022, cited in the Bhutan field study — the only
sourced pricing found; no current Indian retail price was locatable on IndiaMART or GeM)

| Model | Price (USD) | Approx. ₹ (at ~₹83/$) |
|---|---|---|
| Basic PIR | $233 | ~₹19,300 |
| Advanced PIR | $340 | ~₹28,200 |
| Basic AIR | $625 | ~₹51,900 |
| Advanced AIR | $732 | ~₹60,800 |

EleTect X's remaining-to-buy BOM (excluding parts already owned) totals **≈₹18,000–20,000**
per `hardware/bom/bom.md`. That already-owned set (UNO Q, LoRa-E5, TPA3116, INMP441, INA333,
geophone) is non-trivial, so a fair full-unit comparison needs the complete BOM cost, not just
the remaining-purchase figure — flag this before quoting a cost claim publicly. Even so, a
basic ANIDERS PIR unit alone is priced close to or above EleTect X's *entire remaining spend*,
and it ships with a single detection modality versus EleTect X's seismic + acoustic + vision
fusion. That is a legitimate cost-per-capability claim once the full BOM number is confirmed.

## Claimed vs. measured performance — the important part

This is from an independent field study (Tashi Wangdi, Bhutan Ministry of Energy and Natural
Resources / WWF Bhutan / DFO Sarpang, published May 2023, "ANIDERS: Deterring Elephants in
three pilot sites under Sarpang, Bhutan"), not Kyari's own marketing. 30 PIR units and 2 AIR
sets were deployed for over a year across three real human-elephant-conflict hotspots.

- **Detection range:** manufacturer claims PIR range of 100 ft (~30m). Measured field
  performance: **~11m** — over 60% short of the claimed figure. This is a documented,
  independently-measured spec overstatement, not a EleTect X assumption.
- **Habituation:** elephants initially avoided the device, but effectiveness dropped over the
  observation year — elephants adapted to the alarm despite the 40-pattern randomization. This
  directly validates that static randomization is not sufficient for long-term habituation
  resistance.
- **AIR ineffective as a deterrent:** the long-range break-beam variant was found not to deter
  elephants at all — usable only as a tripwire alert, not a repellent, despite being the more
  expensive SKU ($625–732).
- **False positives:** small insects passing the PIR sensor and vehicles on a nearby highway
  both triggered false alarms, disturbing residents. This is the direct consequence of a
  single-modality (heat/motion) sensor with no cross-validation from a second, harder-to-spoof
  signal — exactly the gap EleTect X's seismic (ground vibration from actual animal mass) +
  acoustic + vision fusion is designed to close.
- **Operational trade-off caused by false positives:** to stop noise complaints from false
  alarms, operators switched some units from 24-hour to night-only mode. This blinded the
  system during evening hours — which the same study identifies as when most actual
  human-elephant conflict occurs. A reliability problem in one subsystem (false-positive rate)
  cascaded into a coverage gap.
- **Ineffective in thick bush:** line-of-sight sensors (PIR/AIR both) lose function in dense
  vegetation. Worth checking whether this is a real constraint for Kothamangalam terrain, since
  it's a fundamental limitation of the sensing modality, not a fixable bug.
- **Maintenance burden:** termite damage to the "soundbox," dust/leaf accumulation fouling the
  solar panel, LED replacement, and required monthly bush-clearing around each unit were all
  documented as necessary upkeep.
- **Physical survivability against elephants specifically:** across the three sites, elephants
  physically damaged the majority of deployed units — by the end of the study only 8 of 30 PIR
  units and 1 of 2 AIR sets remained functional. That is roughly a 70% device attrition rate
  over about a year, from the exact animal the device is meant to deter. This is arguably the
  single most important data point for EleTect X's own mechanical design: mounting height,
  enclosure material toughness, and trunk/tusk-reach clearance all need to be evaluated against
  this real failure mode, not just weatherproofing.
- **Provenance note:** the widely-quoted "86% success rate" (NDTV, 2021, citing WWF-India) is a
  media figure, not from this peer-reviewed field study — the two shouldn't be conflated when
  citing either number in EleTect X documentation.

## What this means for EleTect X, concretely

1. **Sensor fusion is a real, evidenced differentiator, not just an architecture preference.**
   The Bhutan study's false-positive and reliability problems trace directly to ANIDERS relying
   on a single infrared modality. EleTect X's seismic+acoustic+vision fusion (per CONTEXT.md) is
   positioned to solve a documented failure mode of the market leader, not a hypothetical one.
2. **Publish honest, tested detection-range numbers.** ANIDERS' own manufacturer figure was
   found to overstate real performance by ~3x in independent testing. Any range claim EleTect X
   makes in its docs should be field-verified, not just simulated/estimated — this is exactly
   the kind of claim a contest judge or a real DFO buyer could sanity-check against public data
   on the competition.
3. **Mechanical survivability against direct elephant contact deserves explicit design
   attention** — mounting height above trunk reach, enclosure impact resistance, and cable/gland
   robustness — since this was the dominant real-world failure mode for the closest competitor,
   not weather ingress.
4. **Habituation resistance needs to be adaptive, not just randomized.** ANIDERS' 40-pattern
   static randomization still saw effectiveness decay over a year. If the bandit-based deterrent
   selection in `device/mpu` is built to adapt based on real-time effectiveness feedback rather
   than blind rotation, that's a stronger, evidenced answer to the same problem — worth stating
   explicitly in documentation as a direct response to this known failure mode.
5. **Cost-per-capability, not just headline cost.** A basic ANIDERS PIR unit costs about as much
   as EleTect X's entire remaining BOM spend, for one detection modality and no networking. Once
   EleTect X's full BOM total (including already-owned parts) is confirmed, this is a strong,
   defensible cost/capability comparison for documentation — but don't publish it until that
   full number is nailed down, since the ₹18–20k figure quoted above is partial.
6. **No published dimensions/weight/IP rating from Kyari** — publishing real, verified numbers
   for EleTect X is a low-cost documentation win that a judge or buyer can't get from the
   incumbent.

## Open items / not yet verified

- EleTect X's own detection range has not been field-tested against the same rigor applied to
  ANIDERS in this analysis — do that before making a comparative range claim.
- Full EleTect X BOM total (including already-owned parts) needed for an honest per-unit cost
  comparison.
- Current (2026) Indian retail pricing for ANIDERS was not locatable — the $233–732 figures are
  from 2022 KIPL data cited secondhand in the Bhutan paper. Treat as directional, not current.
- No teardown or patent-drawing-level detail was found on ANIDERS' actual electronics — the
  patent exists but its content wasn't reviewed here.

## Sources

- Kyari Innovations official site: https://kyari.in/animal-intrusion-detection-repellent/
- ANIDERS product microsite: https://aniders.com/kyari/
- ADA Technologies (authorized dealer) spec page:
  https://www.adatech.co.in/products/kyari-smart-stick/kyari-aniders
- Wangdi, T. (2023). "ANIDERS: Deterring Elephants in three pilot sites under Sarpang, Bhutan."
  ResearchGate: https://www.researchgate.net/publication/370953839
- `hardware/bom/bom.md` (EleTect X remaining-purchase BOM total)
