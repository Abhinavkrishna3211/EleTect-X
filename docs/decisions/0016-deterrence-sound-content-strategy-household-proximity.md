# ADR 0016: Deterrence sound content strategy — four categories, household-proximity-aware escalation

- **Status:** proposed
- **Date:** 2026-09-01

## Context

ADR 0015 designs *how* the horn plays different content per tier (real `AT+VOL`/`AT+PLAYFILE` control,
a `track_id` wire field, a 3-track starting library). This ADR is about *what* content and *when* —
scoped wider per explicit instruction: plan a sound strategy across four categories (tiger roar, bee
swarm, air horn/siren, firecracker/loud bang), for a system that will sit on a **forest boundary where
nearby households are a real possibility, not a hypothetical** — so the strategy has to serve two goals
at once, not just one: deter elephants effectively and durably, *and* not become a nuisance or a source
of complaints from the people living near a node. Those two goals pull in different directions on some
of the content choices below, so this ADR says so plainly rather than picking one and ignoring the
tension.

**This ADR is design only — no code.** It specifies content, tiering, and sourcing policy; the
firmware/MPU changes and the audio-file preparation are separate follow-up work.

### What the evidence base actually supports, category by category

`docs/research/elephant-deterrence-behavioral-science.md` is the underlying literature review; restating
the parts load-bearing for this ADR's tiering decision, including the parts that argue against simply
accepting all four proposed categories at equal weight:

- **Tiger/leopard/lion growl (Thuppil & Coss 2016, *Oryx*)** — the strongest number in the whole
  review: 90–100% raid-attempt deterrence for tiger growls, 72.7–83.3% for leopard/lion, field-tested on
  wild Asian elephants specifically. This is the single best-evidenced category available.
- **Disturbed-bee buzzing (King, Douglas-Hamilton & Vollrath 2007, *Current Biology*)** — a significant
  majority of 18 wild elephant family groups fled on playback, vs. ignoring a white-noise control.
  Elephant-specific, real field data.
- **Sirens — a real, already-cited null result, not a blank slate.** `elephant-deterrence-behavioral-
  science.md` §2 already flags Hedges & Gunaryadi (2010, *Oryx*): chili-grease fences plus **electronic
  sirens** showed **no significant benefit** over conventional guarding alone (91.2% vs 91.2% raids
  repelled) in a real field trial. This is a direct caution against treating "air horn/siren" as
  presumptively effective just because it is loud — the one dedicated field test of an electronic siren
  in this exact problem space found it added nothing.
- **Firecrackers/loud bangs — real-world precedent, but for a different physical stimulus than this
  device produces.** Bursting firecrackers are among the most common traditional elephant-deterrence
  tools across South/Southeast Asian human-elephant conflict zones — but that precedent is for **actual
  pyrotechnic charges**: a near-instantaneous, extremely broadband, very high-SPL pressure transient,
  nothing like what a 15W horn (275–7,000Hz response, ADR 0003) reproducing a *recording* of a bang can
  physically deliver. No literature reviewed supports "a played-back recording of a firecracker" as
  independently effective — this category is included on the strength of the real-firecracker precedent
  by analogy, not because a recorded version has been shown to work. Say this plainly rather than borrow
  the real firecracker's credibility for a recording of one.
- **Human shouts (Thuppil & Coss 2016)** — 57.1%, the weakest of that study's three conditions, included
  here only for completeness; not one of the four requested categories and not proposed for use.

Net: two of the four requested categories (predator growl, bee swarm) are strongly evidenced. The other
two (air horn/siren, firecracker) are weakly or negatively evidenced as *played-back audio* specifically,
independent of how effective the real physical phenomena are. This matters directly for tiering below —
it is not a reason to drop them (novelty and unpredictability have their own value per the anti-
habituation literature, Montgomery et al. 2021's randomization recommendation), but it is a reason not to
lead with them or treat them as the strongest tool in the kit.

### The household-proximity tension, stated directly

ADR 0003 already cites the WHO outdoor nighttime residential guideline (≤40–45 dB LAeq at a facade) as a
siting consideration, but only as a general standoff-distance note. This ADR treats it as a **content**
decision too, because the four categories are not equally likely to distress or anger a nearby household
even at the same measured dB level:

- **Bee swarm and predator growls are natural forest sounds.** Someone living near a forest boundary
  already hears animal sounds at night; even a loud one blends into an expected soundscape and is
  unlikely to be read as an emergency.
- **Air horn/siren and firecracker/bang are synthetic, alarm-associated sounds.** A siren specifically
  reads as an emergency-vehicle or public-alert signal; a sudden loud bang at night near a home can
  reasonably be mistaken for a gunshot or explosion by someone who does not know a deterrence node is
  nearby. Repeated at night near a household, either is a real path to noise complaints, community
  distrust of the project, or a frightened resident calling this in as an actual emergency — a real
  reputational and relationship cost for a project that depends on community/DFO goodwill to stay
  deployed at all, separate from and in addition to the WHO dB guideline.

This is not a reason to discard the air-horn/siren and firecracker categories — they have real novelty
value for anti-habituation and a plausible (if unproven-as-recording) deterrence rationale — but it is a
direct reason **not to fire them indiscriminately at every node regardless of what's nearby**.

## Decision

### A. Household-proximity is a new, explicit per-node configuration axis

Add a boolean (or, if useful later, a distance/category value) **site attribute set at commissioning
time**, e.g. `NODE_HOUSEHOLD_PROXIMITY: bool` — not sensed, not inferred, a fact the install team records
when they site each node (ADR 0003 already describes a multi-node fleet, boundary nodes every
120–150m — some will be near homes, some won't, and the install team already knows which is which when
they pick each pole). This is a new axis alongside `cognition/config.py`'s existing repeat-trigger
`habituation_context()` bucketing — orthogonal to it, not a replacement: repeat-count still governs *how
hard* to escalate; household proximity governs *which content categories are even eligible* regardless of
tier.

**Design intent, not yet reduced to code**: a household-proximity
node's tier ladder tops out at predator-growl content — it can still escalate *gain* and *duration* (ADR
0015's existing tier-fraction mechanism) at its highest tier, but never selects an air-horn/siren or
firecracker track. A non-household node's ladder can include all four categories at its top tier. This
keeps the strongest, human-safe categories (bee, predator growl) available everywhere, and reserves the
weakly-evidenced, alarm-associated categories for locations where there is no household soundscape to
disrupt.

### B. Revised tier-to-category mapping (supersedes ADR 0015 Decision D's tier table for nodes where
`NODE_HOUSEHOLD_PROXIMITY` is set)

| Tier | Household-proximity node | Non-household node | Rationale |
|---|---|---|---|
| 1 | Bee swarm | Bee swarm | Mildest, natural, real evidence (King et al. 2007) — unchanged from ADR 0015. |
| 2 | Predator growl (rotating tiger/lion) | Predator growl (rotating tiger/lion) | Best-evidenced category overall (Thuppil & Coss 2016) — unchanged from ADR 0015, now explicitly a *rotation* between two tracks instead of one fixed track, since two real tracks exist (Decision D). |
| 3 | Predator growl again, at max gain/duration — **not** air horn/siren or firecracker | Air horn/siren or firecracker/bang, rotating | The one real behavioral change from ADR 0015: household-proximity nodes never reach the two weakly-evidenced, alarm-associated categories. Non-household nodes get real category novelty at the top tier, where the anti-habituation value is highest and the evidence caveat (see Context) matters least — this is exactly the tier reserved for a persistent, already-escalated animal, where trying something different is worth more than a proven-but-repeated stimulus, and there is no household soundscape at risk. |

Within Tier 3 for non-household nodes, **prefer firecracker/bang content over siren when both are
available** — the null-result caution above applies specifically and only to siren (Hedges & Gunaryadi
tested an electronic siren, not a firecracker recording), so firecracker is the marginally better-
reasoned of the two weak categories, not because it's proven, but because siren has actual disconfirming
field evidence and firecracker only has "unproven as a recording," which is a weaker caution.

### C. Content library — real, license-checked, for all four categories

Extends ADR 0015 Decision D's table with the two new categories, same sourcing discipline (Freesound,
license verified by fetching each sound's own page, not assumed from a search snippet):

| Category | Track | Source | License |
|---|---|---|---|
| Bee swarm | "Intense Angry Bee Swarm (stereo)" | [Freesound 788025, RealSquink](https://freesound.org/people/RealSquink/sounds/788025/) | **CC0** |
| Predator growl | "tiger roar" | [Freesound 149190, videog](https://freesound.org/people/videog/sounds/149190/) | **CC-BY 4.0** — attribution required |
| Predator growl | "Lion Roar" | [Freesound 212764, qubodup / Iwan Gabovitch](https://freesound.org/people/qubodup/sounds/212764/) | **CC-BY 3.0** — attribution required |
| Air horn/siren | "airhorn.wav" | [Freesound 64476, guitarguy1985](https://freesound.org/people/guitarguy1985/sounds/64476/) | **CC0** |
| Firecracker/bang | "Firecracker_01.wav" | [Freesound 101130, CGEffex](https://freesound.org/people/CGEffex/sounds/101130/) | **CC-BY 4.0** — attribution required |

Five real, verified tracks across four categories — enough to implement Decision B's mapping today, but
**only enough for one track in three of the four categories**, meaning no true within-category rotation
yet outside predator growl. Sourcing 1–2 more per category (bee, air horn/siren, firecracker) is a real,
scoped follow-up, not silently deferred — same honesty ADR 0015 already applied to its own three-track
starting library.

Attribution obligations stack with ADR 0015's: three of these five tracks (tiger, lion, firecracker) are
CC-BY and need real credit somewhere in the project's public materials; bee and air-horn are CC0 and need
none.

### D. On the 30 YouTube links supplied — a real licensing caution, not a blanket rejection

The user supplied ~30 candidate YouTube videos across all four categories (tiger roar, bee swarm, air
horn/siren, firecracker). These were **not individually vetted for reuse rights in this pass** —
licensing checks on the small number attempted were blocked by YouTube rate-limiting the fetch tool
mid-session, and this session does not download or extract audio from video platforms regardless (that
would mean redistributing someone else's copyrighted upload inside a manufactured, publicly-documented
conservation device without a license — a real legal exposure, not a formality, and squarely out of
scope for what this session should do even if it were technically possible).

**What to do with the list, concretely:**

1. **Prefer the Decision C library (Freesound, license-verified) as the actual shipped content** — it's
   real, checked, and legally clean today.
2. **If specific clips from the YouTube list are wanted for their content quality or authenticity** (a
   real wild tiger roar vs. a sound-library one, for instance), the path is not to rip the audio: contact
   the channel/uploader for explicit permission, check whether the specific clip is itself drawn from a
   royalty-free library the uploader names in its description (some are), or — the cleanest option for a
   field-deployed conservation project — **record originals**: a real recording of an air horn, of
   firecrackers set off at a safe standoff distance, or (with appropriate expert help) real bee-swarm or
   captive/zoo predator audio the project has actual rights to. Original recordings sidestep the whole
   question and are arguably more authentic for this specific use than a repurposed video clip anyway.
3. **A rough signal, not a substitute for checking**: a channel or description explicitly using words
   like "royalty-free," "no copyright," "sound library," or "free to use" is worth a closer look for
   ADR 0015/0016's content library; a personal upload, wildlife-documentary clip, or news broadcast is
   very unlikely to carry reuse rights, however good the audio is. This project going into a public
   DFO/contest submission raises the stakes on getting this right, not lowers them.

## Alternatives considered

- **Treat all four categories as equally weighted, no household gating.** Rejected: ignores both the real
  null result on sirens specifically and the real, non-hypothetical human-nuisance cost of alarm-
  associated sounds near homes — a strategy this ADR was explicitly asked to account for.
- **Drop air horn/siren and firecracker entirely, evidence being weak/negative.** Rejected: the anti-
  habituation literature (Montgomery et al. 2021, Adams et al. 2020) values genuine novelty, and a
  persistent animal at the top tier of a non-household node is exactly the situation where an unproven
  but different stimulus is worth trying — the honest move is to gate and caveat these categories, not
  discard real deterrence tools the user specifically asked to plan for.
- **Use YouTube audio directly via a ripping tool.** Rejected outright — a real copyright/licensing
  exposure for a manufactured, publicly-documented device; not something this session will do or
  recommend as a shortcut.

## Consequences

+ A concrete, evidence-honest four-category strategy exists where none did before — directly answers
  "plan what sound to use" and "never let them habituate," tied to real citations rather than assumption.
+ The household-proximity gate is a real design improvement independent of this specific sound question —
  it is the first place this project's design acknowledges that not all nodes sit in the same acoustic
  context, which matters for community relations as much as for elephant behavior.
+ Five real, license-checked tracks exist across all four categories today — a legally clean starting
  library, not a placeholder.
- `NODE_HOUSEHOLD_PROXIMITY` and the household-gated tier table are **design only** — no code exists yet
  (`cognition/config.py`'s `DETERRENCE_TIERS`/`HORN_CONTENT_LIBRARY` from ADR 0015 does not yet have a
  per-node axis at all, only a single fixed tier ladder). Real follow-up work, layered on top of
  ADR 0015's already-pending draft code.
- Within-category rotation is real for predator growl only (two tracks); bee, air horn/siren, and
  firecracker each have exactly one sourced track — flagged, not silently short.
- The YouTube shortlist remains unvetted for licensing; nothing on it should be used without the user (or
  whoever owns that decision) personally checking reuse rights or pursuing an original recording instead.
- Firecracker-recording and siren-recording efficacy are both unproven as *played-back audio* specifically
  — this ADR's Tier-3-for-non-household design leans on their anti-habituation novelty value and real-
  world analogy, not on direct evidence, and says so rather than overclaiming.
