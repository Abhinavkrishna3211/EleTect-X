# Elephant deterrence: vision, hearing, habituation — evidence base for LED/audio design

Written 2026-09-01 to close the citation gap `docs/decisions/0014-led-deterrence-pattern-and-intensity.md`
flags: `HANDOVER.md`/`README.md`/the pitch doc all repeat "habituation within days-to-weeks" and
"unpredictable patterns resist habituation" with no source anywhere in this repo. This document supplies
real citations, states confidence honestly per claim, and translates findings into concrete parameters for
ADR 0014's pattern set and `cognition/config.py`'s tier ladder. Research pass, not exhaustive — flag
anything below that turns out wrong on closer reading rather than trusting it blindly.

## 1. Vision

**Well-established, multi-source:** elephants are dichromatic — same functional photopigment set as human
deuteranopes (red-green colorblind). They discriminate blue/yellow well, red/green poorly.
(Yokoyama & Yokoyama, *J. Mol. Evol.*, ~2005; https://pubmed.ncbi.nlm.nih.gov/15781694/). This directly
supports `CONTEXT.md`'s existing choice of cool-white + royal-blue (~450nm) over red — that choice was
already right, now it has a citation.

**Plausible-by-analogy, not elephant-confirmed:** claims that elephants are especially sensitive to
blue/violet at night track general mammalian scotopic (rod-dominant, short-wavelength-shifted) vision, but
no elephant-specific retinal photoreceptor topography study was found. Don't upgrade this past "plausible."

**No elephant or megafauna-specific flash-frequency (Hz) data exists.** Do not cite a specific strobe Hz
as "proven effective for elephants" anywhere in contest/DFO materials — none of the literature supports a
number. ADR 0014's `PATTERN_FAST_STROBE` ~6-8Hz is an engineering choice (camera-frame-rate-relative,
mechanically reasonable), not a cited behavioral optimum — say so if asked.

## 2. Hearing and audio deterrents (relevant to the horn, and to any future combined LED+horn tier design)

Elephants hear into infrasound (~5-16 Hz) for long-range communication — well established
(Payne/Langbauer; https://www.elephantvoices.org/elephant-communication/acoustic-communication.html).

**Strongest real numbers, both peer-reviewed and elephant-specific:**
- **King, Douglas-Hamilton & Vollrath, 2007, *Current Biology* 17(19)** — playback of disturbed-bee
  buzzing to 18 elephant family groups: significant majority fled vs. ignoring a white-noise control.
  https://savetheelephants.org/research/research-library/african-elephants-run-from-the-sound-of-disturbed-bees-2007/
- **Thuppil & Coss, 2016, *Oryx* 50(2)**, southern India, infrared-triggered playback: tiger growls
  deterred 90-100% of raid attempts, leopard/lion growls 72.7-83.3%, human shouts 57.1%. **The authors
  directly observed reduced responsiveness over repeated exposures at the same location** — real,
  elephant-specific habituation evidence, though not quantified in days.
  https://www.cambridge.org/core/journals/oryx/article/playback-of-felid-growls-mitigates-cropraiding-by-elephants-elephas-maximus-in-southern-india/8DBE0715DD05C4B799A0227ADAB41F8B
- **Hedges & Gunaryadi, 2010, *Oryx* 44(1)**, Way Kambas NP, Indonesia — a real **null result**, useful
  for not overclaiming: chili-grease fences + electronic sirens showed no significant benefit over
  conventional guarding alone (91.2% vs 91.2% raids repelled).
  https://www.cambridge.org/core/journals/oryx/article/reducing-humanelephant-conflict-do-chillies-help-deter-elephants-from-entering-crop-fields/617300F03A583C9D58E81FC9A81373E5

**Implication for the horn**: EleTect X's horn plays a fixed generic tone/volume today (and per ADR 0014's
finding, gain isn't even wired to vary by tier). The literature says *content* matters — bee/predator
sounds substantially outperform generic noise. This is a real, evidenced improvement opportunity for the
horn subsystem specifically, worth its own follow-up (out of scope for ADR 0014, which is LED-only) —
logging it here so it isn't lost: **consider a bee-buzz or predator-growl sample set for `drive_horn`
instead of (or in rotation with) whatever the DFPlayer currently plays**, citing King et al. 2007 and
Thuppil & Coss 2016 directly.

## 2.1 Frequency range, siren-specific evidence, and one more real playback category — added 1 Sept,
prompted by a direct ask for more sound sourcing/frequency research beyond ADR 0016's four categories

**What elephants can actually hear, with real numbers this time (not assumed):** ElephantVoices
(elephantvoices.org, citing behavioral audiometry on a captive juvenile Asian elephant) reports airborne
hearing down to **16 Hz at 65 dB**, extending up to roughly **12 kHz**, and states plainly elephants are
"low-frequency specialists" — good sensitivity at the low end, comparatively poor at the high end. This is
consistent with (and likely draws on) Heffner & Heffner's classic 1982 audiometric study (*Science*
209:1104; *J. Acoust. Soc. Am.* 75), which this pass could not fetch directly (blocked by a CAPTCHA
redirect) — cited here via the secondary source, flagged as not independently re-verified against the
primary paper, not because there's reason to doubt it. **Actionable for the horn**: any deterrence content
mixed with substantial energy above ~12 kHz is spending output on a range this animal barely hears —
worth checking the sourced tracks' actual spectra aren't front-loaded there, though this hasn't been
measured for ADR 0016's five tracks in this pass.

**Siren, specifically: still one real study, still a null result, no dedicated frequency-optimization study
exists.** Targeted search this pass for elephant-specific siren/frequency-modulation studies came back
empty beyond Hedges & Gunaryadi 2010 (already cited, already the basis for ADR 0016's "prefer firecracker
over siren" ordering). No study found tests *which* siren frequency/modulation pattern might work better
than the one that failed — say plainly that "a different siren might work" is speculation, not a
evidenced alternative, if this comes up in DFO/contest conversation.

**A fifth real candidate category, found this pass, with an honest caveat attached: elephant-vocalization
playback.** Wijayagunawardane et al., 2016, *Wildlife Society Bulletin*, "The use of audio playback to
deter crop-raiding Asian elephants" (https://wildlife.onlinelibrary.wiley.com/doi/10.1002/wsb.652) tested
playback including elephant matriarchal-group vocalizations, not just predator/human sounds — real,
elephant-specific, short-distance repellent effect reported. **The caveat, from a synthesis review**:
Ferrão da Costa et al./the Frontiers 2018 review ("Human-Elephant Conflict: A Review of Current Management
Strategies," https://www.frontiersin.org/journals/ecology-and-evolution/articles/10.3389/fevo.2018.00235/full)
places this alongside wild-cat growls and human shouts as a class of "high-tech audio playback" that
elephants "quickly learn to tolerate... and return to raid crops," citing older field observations (Sikes
1971; Moss 1988) — the same habituation risk this project's whole tier-ladder design already exists to
manage, not a reason to exclude the category, but a reason not to treat it as a silver bullet either. The
same review reports Thuppil & Coss 2016's number as "65-100% effective in controlled tests" (a slightly
wider framing of the 72.7-100% range already cited from the primary paper) while flagging that field
effectiveness is less certain given habituation. **Not added to ADR 0016's shipped library this pass** —
logged as a real, sourceable fifth category (elephant distress/matriarchal-group calls) for a future
follow-up, same discipline as ADR 0016's own "more tracks per category" open item.

**Related, not directly a frequency finding but worth recording**: King, Douglas-Hamilton & Vollrath's
follow-up work (*PLOS ONE* 2010, "Bee Threat Elicits Alarm Call in African Elephants,"
https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0010346) found elephants' own
alarm-rumble response to bee playback has a measurably distinct acoustic signature — an upward second-
formant shift (~104-149 Hz in the study's own comparison stimuli) versus rumbles given to white noise or
no stimulus. This is evidence the bee-threat response is a real, acoustically distinguishable behavioral
category for elephants, not a general "loud noise" startle — support for bee-buzz as a genuinely
different stimulus class from siren/bang, not just anecdotally. It does **not** give a frequency for the
bee-buzz stimulus itself (that's the elephant's response, not the input sound) — don't conflate the two
numbers if this gets cited.

**Checked and not directly usable, for the record**: Earth Species Project's public tools (BirdCODE
zero-shot sound-event detection, the `alp-data` bioacoustic dataset-access library,
https://earthspecies.org/what-we-do/publications/) were reviewed on request. BirdCODE is bird-specific by
design, not applicable here. `alp-data` is a Python data-access layer over 35+ existing bioacoustic
datasets — no elephant-specific recordings confirmed present, and it's built for ML researchers, not for
sourcing a finished playback clip. Neither is a fit for ADR 0016's content-sourcing need; logged so this
doesn't get re-checked from scratch later.

## 3. Habituation timelines

**No elephant-specific field number for "days-to-weeks" exists.** The two closest real anchors:
- **Goodyear & Schulte, 2015, *Animal Behavior and Cognition* 2(4)** — 4 captive African elephants, sound
  playback: distress response dropped to baseline within **4-8 trials** (not calendar days) for a novel
  sound; a second novel sound habituated even faster (generalized habituation). Captive, small-n — a real
  number, not a field validation.
  https://www.animalbehaviorandcognition.org/uploads/journals/8/01.Goodyear_Schulte_Final_2.pdf
- **Khorozyan & Waltert, 2019, *Royal Society Open Science* 6** — cross-species systematic review (26
  cases): acoustic/light deterrents lose effectiveness "quite fast," within **1-5 months**, vs. electric
  fences staying near-100% for 3 months-3 years. Not elephant-specific; best available quantified
  cross-species figure. https://royalsocietypublishing.org/rsos/article/6/9/190826/

**Correction to make in `HANDOVER.md`/`README.md`/the pitch doc**: rephrase "habituation within
days-to-weeks" as "habituation typically within 4-8 exposures at a fixed location (Goodyear & Schulte
2015) to 1-5 months for field deterrent systems generally (Khorozyan & Waltert 2019) — no elephant-specific
field-deployment number exists" — narrower and defensible, not a downgrade of the underlying point.

## 3.1 Real crop-raid duration — direct evidence the current encounter-window constant was set without

Added 1 Sept, prompted by the user asking how long the device's deterrence response should stay
"active" once an elephant is detected — a real gap this device's own cognition layer already has a
constant for, just not one informed by field duration data until now.

- **Elephants in the neighborhood: patterns of crop-raiding by Asian elephants within a fragmented
  landscape of Eastern India** (PeerJ, 2020): "Elephants spent an average of 308 min i.e., 5 h (SE
  167 min) during crop-raiding range (15 min to 15 h)." Real, elephant-specific, field-measured raid
  duration — the most directly relevant number available for sizing any "how long is this still the
  same encounter" constant. https://peerj.com/articles/9399/

**What this means for `cognition/config.py`'s `HABITUATION_WINDOW_S`**: that constant is 600s (10 min)
today, and its own comment already discloses the reasoning behind that figure honestly — "20x the MCU's
longest actuator cooldown... long enough that an animal circling a node reads as one escalating
encounter" — a reasoned choice, not a blind guess, but one made **without** the raid-duration data
above. Against a real average raid of 308 minutes (range 15 min-15 h), a 10-minute memory window will
"forget" it's dealing with the same animal for most of a typical raid's length — an elephant standing
and feeding between footfall-triggering movements for more than 10 minutes resets the escalation context
to 0 (gentlest response) even mid-raid, undermining `escalation_floor()`'s own stated purpose ("an animal
that keeps returning... has demonstrably not been deterred... would repeat the ineffective response an
unbounded number of times first" — exactly the failure mode a too-short window reintroduces). See ADR
0017 for the actual retuning decision and its own honest caveats.

## 4. Light-based field deployments — the one citation to lead with

**Adams, Mwezi & Jordan, 2020/2021, *Oryx* 55(5), "Panic at the disco: solar-powered strobe light
barriers reduce field incursion by African elephants... in Chobe District, Botswana."** 18 farmers, 2 crop
seasons. Treatment fields: elephant entry **prevented in 75% of approaches vs. 30% for controls**; only 2
incursions crossed the barrier in the whole study. **Design detail that matters directly for ADR 0014**:
the array's color/pattern was **rotated weekly specifically to reduce habituation** — a real field
implementation of the exact "vary the pattern" principle ADR 0014 is built around, not just a design
guess. Authors are honest that long-term (multi-year) habituation durability wasn't established.
https://www.cambridge.org/core/journals/oryx/article/panic-at-the-disco-solarpowered-strobe-light-barriers-reduce-field-incursion-by-african-elephants-loxodonta-africana-in-chobe-district-botswana/2341B3ED382CE91DE519C609F2AC6965

**This is the strongest citation available for the whole visual-deterrence design** — elephant-specific,
peer-reviewed, real numbers, and directly validates pattern rotation. Use this, not the uncited "habituation
within days-to-weeks" line, as the lead citation in contest/DFO materials going forward.

Comparable-species-only (flag species gap if cited): Ohrens/Bonacic/Treves 2019 (*Frontiers in Ecology and
the Environment*) — FoxLights vs. pumas, Chile, zero kills in protected herds vs. 7 in unprotected over one
calving season. Real and peer-reviewed, but pumas not elephants.

## 5. Randomization vs. static pattern — the general claim

**Montgomery et al., 2021, *Ambio*** — systematic review of elephant crop-protection interventions,
explicitly recommends randomized responses to reduce habituation probability. This is the strongest
elephant-adjacent citation for "vary the pattern," but it's a review recommendation, not an isolated
controlled A/B experiment. Combined with Adams et al.'s real weekly-rotation implementation (§4), the claim
is **well-supported by field practice and expert recommendation, not by a dedicated controlled study
isolating randomization as the sole variable**. State it that way, not as settled fact.

## 6. Sudden light onset at night specifically

Weakest-evidenced item — no direct study. The only indirect support: **Barnes 2013 (*Gajah* 38)** notes
African elephants raid less on bright moonlit nights than dark ones, suggesting general light-driven
caution — but this is ambient gradual moonlight, not a startling abrupt flash, and Barnes explicitly flags
it as unconfirmed for Asian elephants. Treat as weak circumstantial support only.

## Concrete parameters for ADR 0014 / `cognition/config.py`, translated from the above

- **Color choice (cool-white + royal-blue) is now citation-backed** (Yokoyama & Yokoyama) — no change
  needed, just add the citation where `CONTEXT.md`/ADR 0014 state the choice.
- **Pattern rotation/variation is citation-backed as real field practice** (Adams et al. 2020) — ADR
  0014's four-pattern set + tier-based allocation is directionally correct and now has a real precedent to
  cite, not just an inference from `WIRING_GUIDE.md`.
- **No Hz number is defensible as "proven for elephants"** — keep `PATTERN_FAST_STROBE`'s ~6-8Hz framed
  internally as an engineering choice, not a cited optimum, in any doc that goes external (contest/DFO).
- **Escalation-floor policy (bandit.py) is well-matched to the Goodyear & Schulte 4-8-trial habituation
  window** — `habituation_window_s` and `tier_floor_by_context`'s bucket count should be sized with that
  real number in mind rather than picked blind; worth a follow-up check against current
  `cognition/config.py` values, not done in this pass.
- **Horn content, not just volume, is a real evidenced lever** (King et al. bee-buzz, Thuppil & Coss
  predator-growl) — logged as a real near-term opportunity, separate from ADR 0014's LED-only scope.
- **Public-facing claims should cite Adams et al. 2020 as the lead source**, not the currently-uncited
  "days-to-weeks" line — narrows the claim slightly but makes it defensible under scrutiny (a DFO review
  or contest judge could reasonably ask for a source).

## 7. Behavioural, psychological and biological synthesis — added 2 Sept, prompted by a direct ask for a deeper study of the animal and for the deterrence strategy to follow from it

Sections 1–6 above are organised by *deterrent channel* (vision, hearing, light, randomisation).
This section is organised the other way round — starting from **what kind of animal this is** and
deriving what a deterrence system should therefore do. It leans on the sensory facts already
established above and adds cognition, social structure, and the mechanism of habituation. Same
per-claim confidence discipline. Nothing here changes a shipped constant on its own; the
translation to parameters is collected in §7.7 and cross-referenced to the ADRs that would own each
change.

### 7.1 This is a large-brained, slow-reproducing generalist that learns as an individual and remembers places for years

**Well established.** The Asian elephant has the largest absolute brain of any land mammal, a
highly folded cortex, and a very large hippocampus relative to brain size — the structure most
associated with spatial memory. Life history is extreme-K: ~22-month gestation, calves dependent
for years, lifespans of 60+ years in the wild. The behavioural consequence that matters for this
project: elephants are **behaviourally flexible individual learners**, not instinct-bound
responders. Wild puzzle-box work (Asian elephants) documents individual variation in innovation,
persistence, exploratory diversity and neophilia, and explicitly links the bolder / more innovative
individuals to higher crop-raiding propensity (Jacobson et al., *Learning & Behavior* / *Animal
Behaviour*, 2020–2024; ScienceDaily 2021 summary). A recent review ("Do elephants really never
forget?", *Learning & Behavior* 2025) is candid that rigorous memory-capacity studies are thin —
so "never forgets" is folklore, not a measured constant — **but** spatial/resource memory
supporting multi-year return to remembered water and forage is well supported, and drought-survival
work shows older matriarchs carry decades of route and threat knowledge.

**Why this is the central fact for EleTect X.** A deterrent that produces a scare but no
consequence is, to an animal this cognitively capable, a solvable puzzle. It will be probed,
learned, and — once catalogued as harmless — ignored, and that learning is retained and can be
carried back on the next visit and (plausibly, via the matriarch/'"followers learn from leaders"
pattern) shared with the group. This is the mechanistic "why" behind every habituation number in
§3: it is not sensory fatigue, it is an intelligent animal correctly concluding the light and the
noise never actually hurt or blocked it. Design implication: the system's job is not to
out-startle the animal forever (impossible against this learner) but to **stay unpredictable long
enough, and escalate hard enough, that "just walk through it" never becomes the reliably-safe
learned answer** — buying the time and the deterrence probability that matter during the peak weeks
(activity-timing companion doc §3.2), while the real long-term fix (fencing, guarding, land-use)
does the rest.

### 7.2 The animal at a backyard fence at 2 a.m. is very probably a lone male

**Well established, and directly relevant.** Across Asian-elephant HEC studies, crop-raiding is
disproportionately done by **lone adult/sub-adult males or small male groups**, not by matriarchal
family units (PMC7335499 and many others). The behavioural-ecology explanation is a risk/reward
asymmetry: a bull's reproductive success scales with body condition, so the high-payoff,
high-risk strategy of raiding nutrient-dense crops pays off for males in a way it does not for a
matriarch responsible for calves, who keeps the group to lower-risk foraging. **Musth** sharpens
this — a musth bull is energetically stressed, hormonally aggressive, less deterrable, and more
dangerous to any human who responds to the alert in person.

**Design implications, several and concrete:**
- The device is usually facing a **bold individual pre-selected for willingness to tolerate risk**
  — the tail of the boldness distribution, not the average elephant. Deterrence effectiveness
  numbers measured on mixed populations (the 75%/30% in §4, the 57–100% in §2) are optimistic
  priors for this specific audience. State that when quoting them to DFO.
- **The human-safety framing on the web-app alert matters more, not less.** A late-night alert at a
  node in this region is more likely than base rate to be a lone bull, possibly in musth. Alert
  copy and RRT guidance should not imply the responder is dealing with a nervous herd that will
  move off easily. (Ties to the project deployment bar — "alerts must reach the right person".)
- **Individual-level response is expected.** Because raiders are individuals with personalities,
  two elephants at the same node on two nights can respond completely differently to the identical
  tier-2 pattern. This is not the device malfunctioning; it is the reason `cognition/bandit.py`
  learns per-context rather than assuming one fixed response curve, and it is an argument for
  keeping the bandit's exploration term alive in the field rather than freezing on an early
  "best" pattern.

### 7.3 Habituation, stated mechanistically: predictability is the enemy, not familiarity

**Well established (general learning neuroscience; the elephant-specific field numbers are in §3).**
Habituation is non-associative response decrement to repeated stimulation — specifically *not*
sensory adaptation or fatigue (Rankin et al.'s consensus criteria; *Neurobiology of Learning and
Memory* 2009; PMC3920081). Two features of it are load-bearing for this device:

- **Predictability accelerates it.** The current model (Sokolov-style comparator; recent
  formalisations e.g. PMC8168884, "How predictability affects habituation to novelty", 2021) is
  that repeated *predictable* onsets let an inhibitory/expectation mechanism get conditioned to the
  stimulus and pre-empt the response. A stimulus that is irregular in timing, character and
  location keeps violating the expectation and keeps evoking a response. **This is the precise
  mechanism that makes ADR 0014's unpredictability lever — and Adams et al.'s weekly rotation, and
  Montgomery et al.'s randomisation recommendation — actually work.** It also means a "random"
  pattern that is random-but-stationary (a fixed 40-pattern shuffle, as in the Wangdi 2023
  competitor result cited in ADR 0014) still becomes predictable at the distribution level and
  still decays. The bandit's *outcome-adaptive* change of behaviour is a stronger defence than any
  fixed randomisation because the distribution itself keeps moving.
- **Weak stimulus → habituation; strong stimulus → sensitisation.** Repeated *weak* stimuli
  habituate; repeated *strong* or aversive stimuli can instead **sensitise** (response grows), and
  a single aversive event gives only minutes of decrement while several in succession can build
  days-to-weeks of heightened reactivity (PMC3920081; ScienceDirect "Sensitization and habituation
  regulate reinforcer effectiveness"). **This is a real argument for ADR 0014 §E.3's "every
  deterrence tier fires the LED at max, escalate on pattern/wings/rate not brightness" decision** —
  a dim flash is a weak stimulus on the habituation side of that line; a bright, close,
  multi-source, irregular strobe plus horn is closer to the sensitising side. It is *not* a
  licence to fire max on the first trigger every time (that is the failure mode §3's Goodyear &
  Schulte and Khorozyan & Waltert both warn about, and it wastes the escalation headroom the
  matriarch-age/experience and boldness findings say you need for repeat individuals) — it is an
  argument for the escalation *ceiling* being genuinely aversive, which the bandit's
  `escalation_floor()` reserves for demonstrated repeat offenders.
- **Dishabituation is real and exploitable.** A strong or novel extra stimulus transiently
  restores a habituated response. A long stimulus-free gap also restores it. Both say the device
  should *change something* on re-encounter rather than repeat, and that a returning animal after a
  quiet period is (briefly) more deterrable than one being hit repeatedly in one session — a
  subtlety worth keeping in mind when ADR 0017 retunes the encounter window: the goal is to not
  *forget the encounter*, but the actual stimulus on re-engagement should still be varied, not a
  replay.

### 7.4 Three outcomes — flight, curiosity, tolerance — and what tips between them

A deterrence event ends in one of three states, and the design should be explicit about which it is
aiming for:

1. **Flight / avoidance** — the target outcome. Most likely when the stimulus is sudden, novel,
   multi-modal, and carries a plausible threat semantics (predator, humans, bees — §2), and when
   the animal has an unobstructed escape route back toward cover. Corollary often missed:
   **leave the animal a way out.** A deterrent that appears to corner an elephant, or that fires
   between it and the forest, risks converting flight into defensive aggression. For a fixed node
   at a yard edge this is mostly a siting concern (face the forest, don't bracket the animal), worth
   a line in the install guide.
2. **Curiosity / investigation** — the neophilia the puzzle-box work documents in exactly the bold
   individuals who raid. A weak, static, or slowly-onset novel stimulus can *attract* an
   exploratory bull rather than repel him. Argues against slow ramps and low intensities as a
   "gentle" first tier (another vote for §7.3's "make even tier 1 a real strobe, not a dim pulse")
   and against any steady always-on light as the primary deterrent.
3. **Tolerance / habituation** — §7.1/7.3. The default long-run outcome of any consequence-free
   deterrent against this learner.

The lever that most moves outcome 1 vs 3 over time is **unpredictability + escalation**; the lever
that most moves 1 vs 2 in a single encounter is **abrupt onset + intensity + threat-congruent
content**.

### 7.5 Stress physiology and the welfare bound — we are redirecting, not terrorising

**Well established.** Elephants mount measurable glucocorticoid stress responses to HEC pressure;
chronic conflict stress is a documented welfare and conservation problem, and this is an endangered
species with which the partnering forest department has a long-term coexistence mandate, not an
eradication one. This sets a real upper bound on the design that is easy to lose sight of when
optimising for deterrence probability:

- The aim is a **brief, effective aversive event that ends when the animal leaves** — not the
  maximum sustained punishment the hardware can deliver. This is already encoded in
  "stop-on-retreat" intent (`cognition/bandit.py`) and in bounded burst/cooldown limits; §7 is the
  behavioural-science justification for keeping those bounds even under pressure to "hit harder".
- **No physical-harm actuators.** Light and sound only; nothing that can injure eyes or ears at the
  ranges involved (the horn's hearing-safety cap in ADR 0016 is for *people and livestock*, but the
  principle of not causing tissue damage extends to the target animal).
- **Escalation must be able to top out and stay there without ramping indefinitely.** A device that
  keeps increasing intensity every few seconds an animal fails to leave will eventually either
  sensitise it into aggression or exceed a welfare line. The three-tier ceiling is correct; there
  should be no automatic tier 4.
- **This is a genuine tension, stated honestly:** the sensitisation argument in §7.3 ("strong
  aversive stimuli resist habituation better") and the welfare bound here pull in opposite
  directions. The resolution the architecture already picks — max intensity but *bounded duration*,
  *bounded repetition*, *reserved for demonstrated repeat offenders*, *stops when the animal
  leaves* — is a defensible middle, and should be described that way to DFO rather than as "we
  don't stress the animals" (we do, briefly, on purpose) or "we hit them as hard as possible" (we
  don't, and shouldn't).

### 7.6 Why the current architecture is right — and its one real weakness

Reading the biology back against `CONTEXT.md`'s frozen design and the ADR stack:

**Well matched to the evidence:**
- **Multi-modal (light + sound).** §2's null results (Hedges & Gunaryadi siren; the chili-fence
  null) and §4's successes track with "single weak channel fails, combined/threat-congruent
  channels do better". Multi-method is the consistent recommendation.
- **Escalating tiers with a repeat-offender floor.** Matches the boldness/individual-variation
  finding (§7.2) and the "reserve the strong stuff for animals that have shown they need it"
  reading of the habituation literature (§7.3).
- **Outcome-adaptive (contextual bandit), not fixed randomisation.** §7.3: a moving distribution
  beats a stationary shuffle against a comparator-style habituation mechanism, and there is direct
  competitor field evidence (Wangdi 2023, via ADR 0014) that stationary randomisation still decays.
- **Bounded, stop-on-retreat-intended.** Matches the welfare bound (§7.5) and avoids the
  sensitisation-into-aggression failure mode.
- **Colour choice (blue/cool-white).** §1 — already citation-backed, correct for a dichromat.

**The one real weakness, stated plainly (it is already in `bandit.py`'s own docstring and
`KNOWN_GAPS.md`, restated here as the behavioural conclusion):** the whole adaptive layer runs on a
**proxy** for deterrence outcome — time until the next trigger — because *there is no sensor that
tells the device the animal actually left, or in which direction, or whether it was deterred versus
leaving for unrelated reasons*. Everything §7.3–7.4 says about "escalate on failure, vary on
re-encounter, stop on retreat" depends on knowing success from failure, and the device currently
infers that from silence. An animal that stops triggering because it settled to feed just out of
PIR range (activity-timing doc §3.3) scores identically to one that fled. **This is the highest-value
place to improve the system's behavioural fidelity** — a presence/direction signal (a second PIR
zone, a low-rate vision presence check during and after a deterrence event now that §Finding 2 of
the night-IR characterisation shows the camera is not blinded by our own strobe, a cheap radar
module) would let the bandit learn against a real outcome instead of a proxy. Not a launch blocker;
the single biggest lever on making the "never let them habituate" claim honest rather than
aspirational.

### 7.7 Concrete strategy adjustments, cross-referenced

None of these are made unilaterally here; each names the ADR/file that would own it.

| # | Adjustment | Grounded in | Owner |
|---|---|---|---|
| 1 | Keep every deterrence tier's LED at max intensity; carry escalation on pattern / wing-count / strobe-rate, never on brightness. | §7.3 weak-stimulus-habituates / strong-stimulus-sensitises; §7.4 curiosity risk of dim slow stimuli | ADR 0014 §E.3 — **already decided**, §7 is its behavioural justification |
| 2 | Keep the bandit's exploration term live in the field; do not freeze on an early "best" pattern. | §7.2 individual variation — the "best" pattern for one bull is not the best for the next; §7.3 stationary randomisation still decays | `cognition/bandit.py`, `cognition/config.py` |
| 3 | Lengthen `HABITUATION_WINDOW_S` toward raid-duration scale (hours), so a mid-raid feeding lull does not reset escalation. | §3.1; activity-timing doc §1.3, §3.3 | ADR 0017 |
| 4 | On re-encounter after a quiet gap, vary the stimulus (don't replay) — dishabituation means the returning animal is briefly more deterrable and a repeat wastes that. | §7.3 dishabituation | `cognition/bandit.py` tier/pattern selection |
| 5 | Add horn *content* (bee-buzz / predator-growl / conspecific alarm), not just level, in rotation. | §2, §2.1 — threat-congruent content beats generic noise; §7.4 outcome-1 lever | ADR 0016 follow-up (already logged there) |
| 6 | Add a real presence/direction/outcome signal so the bandit learns against measured deterrence, not a silence proxy. | §7.6 | new ADR; `KNOWN_GAPS.md` — highest-value behavioural-fidelity item |
| 7 | Web-app alert copy + RRT guidance should assume a lone, possibly-musth bull at night, not a skittish herd. | §7.2 | web/frontend alert templates; project deployment bar |
| 8 | Install guidance: face the forest, don't site the node so it brackets an animal's escape route back to cover. | §7.4 flight-vs-defensive-aggression; §7.5 leave a way out | `hardware/WIRING_GUIDE.md` / install doc |
| 9 | Keep the three-tier ceiling; no automatic tier 4; escalation tops out and holds. | §7.5 welfare bound + sensitisation-into-aggression risk | `cognition/config.py` — already the case, keep it |
| 10 | Peak-season readiness: the anti-habituation machinery matters most May–Sep / Sep–Dec for this site; validate any tuning against an in-season night. | activity-timing doc §2.2, §3.2; §3 Goodyear & Schulte exposure-count window | test/tuning practice, not a constant |

### 7.8 What to say to DFO / contest, in one paragraph

EleTect X is designed around what elephants actually are: intelligent individual learners with
long spatial memories, of which the ones that raid are a bold, risk-tolerant, mostly-male subset.
Against that animal no fixed scare works for long — the published habituation evidence is
consistent on this — so the device does not rely on a fixed scare. It combines light and sound
(both more effective than either alone, and more effective still when the sound carries a threat
the animal recognises), it escalates only as far as a given animal's persistence requires, it
varies its response adaptively so the pattern never becomes predictable, and it is bounded: brief
events, hard ceiling, intended to stop when the animal leaves. It is one layer of a coexistence
strategy, not a fence — its honest claim is a raised probability of turning a given approach,
sustained across repeat visits for longer than a static deterrent would manage, with a full event
log so its real field effectiveness can be measured rather than assumed. Its main current
limitation is that it infers "did it work" from whether the animal comes back, not from a direct
measurement — closing that gap is the top development priority.

## 8. Sources added in §7

- [Do elephants really never forget? What we know about elephant memory and a call for further investigation — *Learning & Behavior*, 2025](https://link.springer.com/article/10.3758/s13420-024-00655-y)
- [Elephants solve problems with personality — ScienceDaily summary, 2021 (Jacobson et al.)](https://www.sciencedaily.com/releases/2021/06/210625190956.htm)
- [A "thinking animal" in conflict: studying wild elephant cognition in the shadow of anthropogenic change — *Current Opinion in Behavioral Sciences*](https://www.sciencedirect.com/science/article/abs/pii/S2352154622000547)
- [Insightful Problem Solving in an Asian Elephant — *PLoS ONE* / PMC3158079](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3158079/)
- [Leadership in elephants: the adaptive value of age — McComb et al., *Proc. R. Soc. B* (via ElephantVoices)](https://elephantvoices.org/latest-news-updates/publications/leadership-in-elephants-the-adaptive-value-of-age.html)
- [Reduced older male presence linked to increased rates of aggression to non-conspecific targets in male elephants — *Proc. R. Soc. B* 288:20211374](https://royalsocietypublishing.org/rspb/article/288/1965/20211374/79251/Reduced-older-male-presence-linked-to-increased)
- [Social Behavior and Group Formation in Male Asian Elephants: The Effects of Age and Musth — PMC9100748](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9100748/)
- [Musth — overview](https://en.wikipedia.org/wiki/Musth)
- [Habituation, sensitization, and Pavlovian conditioning — Thompson, *Neurobiology of Learning and Memory* / PMC3920081](https://pmc.ncbi.nlm.nih.gov/articles/PMC3920081/)
- [How predictability affects habituation to novelty — PMC8168884, 2021](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8168884/)
- [Sensitization and habituation regulate reinforcer effectiveness — *Neurobiology of Learning and Memory*](https://www.sciencedirect.com/science/article/abs/pii/S1074742708001184)
- [Human–Elephant Conflict Handbook — IIED, 2025](https://www.iied.org/sites/default/files/pdfs/2025-02/22606g.pdf)
