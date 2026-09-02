# When elephants actually come: diel and seasonal timing of crop-raiding, and what it means for EleTect X

Companion to `elephant-deterrence-behavioral-science.md` (sensory / habituation evidence base) and
to `elephant-deterrence-behavioral-science.md §7` (behavioural synthesis → strategy). This file
answers one narrower question the project owner asked directly: **at what times of day and year do
elephants approach, so the device can be tuned around that.**

Same evidentiary discipline as the sibling doc: every claim is tagged with how good the evidence is
and whether it is Asian-elephant-specific, Western-Ghats-specific, or borrowed from African work.

---

## 1. Time of day — the strong, consistent finding

### 1.1 Crop-raiding is overwhelmingly nocturnal, 22:00–06:00

**Strongest single number.** *Elephants in the neighbourhood: patterns of crop-raiding by Asian
elephants within a fragmented landscape of Eastern India* (PeerJ, 2020 / PMC7335499), a 2-year,
**N = 380** event dataset from North Bengal:

- Crop depredation showed a **distinct nocturnal pattern, 22:00–06:00.**
- The paper's own framing: elephants use a **risk-avoidance strategy** — they evade human
  settlements during daylight and raid at night specifically to avoid human contact while foraging.

This is Asian-elephant-specific, field-measured, recent, peer-reviewed, and from a
forest–agriculture matrix comparable in structure (fragmented, high edge density) to the
Kothamangalam deployment site. It is the anchor citation for the diel-timing claim.

The commonly-quoted split — **~89% of incidents 22:00–06:00, ~11% 14:00–22:00** — is the
finer-grained breakdown from this same body of North Bengal work. Treat the 89/11 figure as
"strongly indicative, one landscape" rather than a universal constant; the **direction** (deep night
dominates, afternoon is a minor secondary window, morning after ~06:00 is rare) is what is robust.

### 1.2 Movement peaks are crepuscular — dusk and dawn

Raiding happens in the deep-night window, but the **movement into and out of the raid area**
concentrates at dusk and dawn. GPS-collar work (forest elephants, Gabon, *PLOS ONE* 2018 —
African, so flagged as comparable-species): elephants moved **faster near dawn (06:00–08:00) and
dusk (17:00–20:00)** than at any other time — pronounced crepuscular movement peaks, with the
forest↔open transition happening in those windows. Asian-elephant satellite-collar work
(Xishuangbanna, Yunnan) similarly reports a **dual-peak (bimodal) daily activity rhythm.**

Practical reading for a fixed sensor at a yard edge: **expect first approach around/after dusk,
expect departure around/before dawn, expect the animal to be *present and feeding* — lower movement
rate, so fewer footfall triggers — through the middle of the night.** That middle-of-night
low-trigger period is the one §1.1's raid-duration data (below) says can last hours.

### 1.3 Raid duration — an elephant that arrives is not a brief visitor

From the same PeerJ 2020 study (already cited in the sibling doc §3.1, repeated here because it is a
timing fact): **mean time spent in the crop-raiding range was 308 min ≈ 5 h (SE 167 min), range
15 min to 15 h.**

So the realistic picture for one night at one node is: arrival near dusk, a multi-hour stay with
long stationary feeding bouts, departure near dawn — not a 5-minute drive-by. This is why
`cognition/config.py`'s `HABITUATION_WINDOW_S` (600 s) is too short to hold "same encounter" across
a real raid, and why ADR 0017 exists.

---

## 2. Time of year — real, but landscape-specific

Seasonality is genuinely predictive but the peak **month** depends on which crops are around, which
depends on the landscape. Two datasets, two different peaks, same underlying driver (crop
availability + phenology):

### 2.1 North Bengal / Eastern India — monsoon and post-monsoon

PeerJ 2020 / PMC7335499, same N = 380 dataset:

| Season | Share of incidents |
|---|---|
| Monsoon + post-monsoon combined (Jul–Feb) | ~88% |
| Winter (Nov–Feb) | ~45% |
| Monsoon (Jul–Oct) | ~43% |
| Summer (Mar–Jun) | ~12% |

### 2.2 Wayanad, Western Ghats, Kerala — jackfruit/mango season, then paddy

ATREE, *Elephants in the farm — changing temporal and seasonal patterns of human–elephant
interactions in a forest–agriculture matrix in the Western Ghats, India* (2023; Anoop N.R.,
Krishnan S., T. Ganesh; published via *Frontiers in Conservation Science* / ATREE):

- **Peak crop depredation: jackfruit and mango season, May–September**, followed by the **paddy
  season, September–December.**
- **Season and proximity to the forest boundary are the two major drivers** of conflict intensity.
- Farmers have responded by **removing fruiting trees** (jackfruit, mango) to stop attracting
  elephants — a strong signal of how tightly the timing tracks fruit availability.

This is the **most locally-relevant seasonality source** for the Kothamangalam trial: same state,
same mountain range, same forest–plantation matrix. The Idukki/Ernakulam plantation belt around
Kothamangalam is jackfruit-, mango-, banana-, and coconut-heavy, so the Wayanad pattern
(fruit-season-led, boundary-proximity-driven) is the better prior than the North Bengal
paddy/monsoon pattern — but note the older classic southern-India work (Sukumar, *Ecology of the
Asian elephant in southern India II*) put raiding pressure heaviest in the **wet season aligning
with finger-millet / ragi ripening (roughly Sep–Dec)** in the drier southern-India cultivation
systems, so a paddy/millet post-monsoon secondary peak is also plausible locally.

### 2.3 The honest bound on seasonality

There is **no published incident-timing dataset for the specific Kothamangalam / lower-Periyar
landscape** that this device is being trialled in. Kerala HEC is well documented in aggregate
(compensation-record appraisals; the region is historically a conflict hotspot alongside Wayanad
and Idukki), and the Forest Department runs a Rapid Response Team that repeatedly drives elephants
back with the animals "frequently returning" — consistent with the repeat-visit / habituation
picture the whole project is built around — but a node-level diel/seasonal histogram for this exact
site does not exist in the literature. **The device's own event log will be the first such
dataset**, which is itself a reason to make sure timestamps and event outcomes are recorded
cleanly from day one of the trial.

---

## 3. What this means for EleTect X — concrete

### 3.1 The device must be fully alive 20:00–07:00, every night, in season

Nothing here supports duty-cycling the sensing path down at night to save power — night **is** the
threat window. If anything the load profile is inverted from a typical daytime-security product:
the MCU reflex path, the geophone, and the camera + vision runner all need to be at full readiness
through the exact hours a consumer device would idle. Any future power-budget work should protect
night availability first and look for savings in the **daylight** hours (roughly 09:00–16:00),
where §1.1 says incursions are rare — and even that only in the off-season.

This directly reinforces **ADR 0019** (external IR gated on night): the illuminator's whole job is
in the hours the device is busiest, and the night gate is what stops it also firing across the
quiet daytime tier-2/3 events.

### 3.2 Seasonal readiness, not year-round identical operation

In-season (for this site, plan around **May–Sep fruit season and a Sep–Dec paddy/millet secondary
window**, adjusted once the device's own logs show the local pattern), expect near-nightly
activity. Off-season (roughly **Feb–Apr**), expect sparse events. This matters for:

- **Battery sizing / solar margin** — the worst-case sustained-load period is a run of consecutive
  in-season nights with multi-hour elephant presence and repeated tier escalation, not an average
  day. Size to that.
- **Habituation management** — near-nightly in-season contact is exactly the regime Goodyear &
  Schulte's 4–8-exposure habituation window (sibling doc §3) says will burn out a fixed response
  fastest. The bandit's escalation-floor and randomisation matter **most** in the peak weeks, and
  any pre-trial tuning of `HABITUATION_WINDOW_S` / floor-bucket counts should be validated against
  an in-season night, not a quiet one.
- **Alert triage on the web app** — an in-season 02:00 elephant alert is the product's core case
  and must page reliably (see the project deployment bar); an off-season midday detection is
  far more likely to be a boar false-positive (the ~31% Boar FP rate in `docs/KNOWN_GAPS.md`) or a
  person, and can reasonably be surfaced at lower urgency.

### 3.3 Encounter model: arrival burst → long quiet presence → departure burst

§1.2 + §1.3 say a real encounter looks like: a **cluster of footfall triggers near dusk** as the
animal moves in, then **hours of sparse triggers** while it stands and feeds (movement rate drops
during feeding bouts), then another **cluster near dawn** as it leaves. Design consequences:

- A quiet 30–90 min gap mid-encounter is **not** "the animal left" — it is the expected feeding
  lull. `HABITUATION_WINDOW_S` at 600 s treats that lull as a new encounter and resets escalation
  to the gentlest tier mid-raid. This is the §3.1 argument in the sibling doc, now with a timing
  mechanism attached: the resets happen because feeding suppresses the trigger rate, not because
  the elephant is gone. ADR 0017 is where the fix lands; this is corroborating evidence for
  lengthening the window substantially (toward the raid-duration scale, hours not minutes) rather
  than trimming it.
- The **dawn departure cluster** is a good, cheap validation signal for `proxy_reward()` /
  time-until-next-trigger: if triggers reliably stop for good shortly after first light regardless
  of what the device did, that is the natural-departure baseline the proxy reward has to be
  measured against, and the event log should make it easy to separate "stopped at dawn like every
  night" from "stopped at 01:30 right after a tier-3 fire."

### 3.4 Nothing here changes the actuator design

Timing tells us **when to be ready and how to model an encounter**, not what pattern to strobe or
what to play on the horn. Those stay as ADR 0014 / 0016 / 0018 have them. The one soft
cross-link: the crepuscular movement peaks (§1.2) mean the device will most often get its **first
clean look at a moving animal at low light around dusk and around dawn** — the exact conditions the
night-IR characterisation (`docs/qa/night-ir-led-characterisation.md`) and ADR 0019's night gate
are about — so getting the dusk/dawn transition handling right in `perception/night.py` (the
"minutes either side of the filter's own switch" case) is not an edge case, it is the modal case.

---

## Sources

- [Elephants in the neighbourhood: patterns of crop-raiding by Asian elephants within a fragmented landscape of Eastern India — PeerJ 2020 / PMC7335499](https://pmc.ncbi.nlm.nih.gov/articles/PMC7335499/)
- [Elephants in the farm – changing temporal and seasonal patterns of human–elephant interactions in a forest–agriculture matrix in the Western Ghats, India — ATREE, 2023](https://www.atree.org/publications/elephants-in-the-farm-changing-temporal-and-seasonal-patterns-of-human-elephant-interactions-in-a-forest-agriculture-matrix-in-the-western-ghats-india/)
- [Forest elephant movement and habitat use in a tropical forest-grassland mosaic in Gabon — PLOS ONE 2018 / PMC6040693](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6040693/)
- [Satellite collar data reveals dual-peak activity rhythm of Asian elephant (Elephas maximus)](https://www.sciengine.com/ATS/doi/10.16829/j.slxb.151015)
- [Ecology of the Asian elephant in southern India. II. Feeding habits and crop raiding patterns — Sukumar](https://www.academia.edu/5165355/Ecology_of_the_Asian_elephant_in_southern_India_II_Feeding_habits_and_crop_raiding_patterns)
- [Human–elephant conflict in Kerala — overview](https://en.wikipedia.org/wiki/Human-elephant_conflict_in_Kerala)
- [Human–Elephant Conflict in Kerala, India: a Rapid Appraisal Using Compensation Records](https://www.researchgate.net/publication/339319047_Human-Elephant_Conflict_in_Kerala_India_a_Rapid_Appraisal_Using_Compensation_Records)
