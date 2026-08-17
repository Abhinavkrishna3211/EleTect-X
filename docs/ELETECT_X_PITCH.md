# EleTect X — Project Pitch

## The problem

Human-elephant conflict along Kerala's forest edges is not an abstract statistic — it's a recurring,
often fatal collision between people and wildlife that neither side can fully avoid. Elephants raid
crops and move through settlement-adjacent corridors at night; residents and farmers have no reliable
early warning before an animal is already at the fence line; forest departments are stretched thin
across enormous boundary lengths and can't station a ranger at every crossing point. The existing
tools — trip-wire alarms, occasional patrols, word-of-mouth — are either too crude to discriminate a
real elephant from a boar or a gust of wind, or too slow to give anyone useful lead time. People get
hurt, elephants get hurt or killed in retaliation, and crops get destroyed, in a cycle that repeats
every season. This isn't a hypothetical use case: the Kerala Forest Department's Kothamangalam
division has already approved a real field deployment, because this is a problem they live with daily
and existing options haven't solved it.

## The idea

EleTect X is an autonomous, solar-powered sensor node that sits on the forest boundary and does four
things no existing low-cost system does together: it detects an approaching elephant early — before
it's visible or audible to a person — confirms what it detected isn't a false alarm, deters it in a
way that doesn't stop working after the animal gets used to it, and does all of this without needing
a human in the loop or a network connection to function. A line of these nodes spaced along a
boundary, coordinating with each other over LoRa, turns a boundary that today has zero warning into
one with continuous, adaptive coverage.

## How it works

**Detection is seismic-first, not camera-first.** A buried geophone — the same class of sensor used
in seismology — picks up the ground vibration of footfalls before an elephant is close enough to see,
through vegetation, in the dark, in monsoon rain, none of which a camera or PIR sensor handles well.
An onboard STA/LTA algorithm (short-term/long-term average ratio, standard practice in seismic trigger
detection) flags a footfall-pattern event on the low-power microcontroller side of the board, drawing
microamps while idle. Acoustic sensing corroborates the seismic trigger and separately catches events
seismic can't — gunshots and chainsaws, giving the same node a secondary anti-poaching function.

**Confirmation is where vision comes in.** Only once the reflex layer has a real trigger does the
node wake its Linux-side processor and run a vision model against a day/night camera with IR
illumination, to confirm the trigger is actually an elephant and not a false positive. This
two-stage, event-only design is why the node can run for days on a modest battery and small solar
panel instead of needing constant camera power — the expensive compute only turns on when there's
already good reason to believe something's there.

**The two readings get combined with an explainable formula, not a black box.** A weighted log-odds
fusion (`L = L_prior + Σ aᵢwᵢ(ℓᵢ−ℓ₀ᵢ)`, probability via a sigmoid) combines whatever sensors are
actually available at the moment — if the camera fails or it's too dark even for IR, the seismic
reading alone still drives a decision, just with appropriately lower confidence. Nothing about the
decision is hidden inside a trained model that can't be inspected after the fact.

**Deterrence adapts instead of habituating.** The single biggest failure mode of existing deterrence
(a fixed siren, a fixed light) is that elephants — genuinely intelligent, fast-learning animals —
stop reacting to a stimulus that never changes. EleTect X drives its horn and strobe LEDs through a
contextual bandit that varies the response and stops escalating the moment the animal retreats, so
the deterrent stays effective instead of becoming background noise the herd learns to ignore.

**Coordination keeps the elephant safe, not just deterred.** Nodes talk to each other over a LoRaWAN
star network and pre-arm neighbouring nodes when one detects movement, inferring direction from the
sequence of nodes that trigger. Deterrence is deliberately asymmetric — push on the village side, keep
a forest-side escape route open — so the goal is genuinely to route the animal back to safety, not to
corner it.

**Everything above runs locally, with zero dependency on connectivity.** The node decides and acts on
its own; the cloud backend is for forest officers and residents to see what happened after the fact —
a live map, alert history, learning trends — never a control path the animal's safety depends on.

## The technology

Compute is a single Arduino UNO Q board, which is the enabling piece: it puts a real-time STM32
microcontroller (the "reflex" layer — sensors, actuators, safety gates, always-on) and a Linux-capable
Qualcomm Dragonwing processor (the "cognition" layer — vision, fusion, learning, event-only) on one
board, talking to each other over a documented RPC bridge, instead of needing two separate boards and
a fragile serial link between them.

Sensing: a SparkFun SM-24 geophone through an INA333 instrumentation amp and analog band-pass into the
STM32's internal ADC; an INMP441 digital MIC for acoustic corroboration and anti-poaching detection;
an Arducam IMX462 day/night USB camera with a 940nm IR illuminator for vision confirmation.

Deterrence: cool-white and royal-blue LED strobes, and an Ahuja SUH-15 horn driven through a
DFPlayer-PRO and TPA3116D2 amplifier — housed separately from the main electronics per a recent design
revision, so the horn's own housing doesn't force the whole enclosure to grow around it.

Comms: a Grove LoRa-E5 module on India's legal IN865 band, talking to a gateway that bridges to
ChirpStack and then to the backend over MQTT.

Power: a 4S LiFePO4 pack sized against a real measured power budget (not a guess) — continuous MPU
suspend draw around 0.42-0.45W, sized for 3-day no-sun autonomy at 85% depth of discharge — charged
by a 15-20W solar panel through a manually-set CC/CV buck regulator, deliberately simplified after
every "smart" LiFePO4 charge controller in the affordable price range turned out to have a real,
verified defect (wrong-chemistry defaults, unconfirmed firmware bugs, or misspecced protection).

Enclosure: in-house-designed PETG 3D print, engineered — not just modeled — with a real structural
split between the fixed pole-mount collar, the removable service hatch, and a slide-out electronics
tray, specifically so opening the unit for maintenance never re-torques a fastener that's also
carrying the enclosure's dead weight on a pole in monsoon wind.

Backend and dashboard: Supabase (Postgres, auth, realtime, row-level security, edge functions) behind
a React PWA built for two real audiences — forest officers who need a live map and alert triage, and
residents who need a simple opt-in alert channel — both already built and functioning, not a mockup.

## What makes this different, honestly stated

Most low-cost wildlife deterrence is vision-only or PIR-only, both of which fail exactly when it
matters most — at night, in dense vegetation, in rain. Seismic-primary detection sidesteps that
entire failure class. Most deterrence systems don't adapt, so animals habituate within days or weeks;
this one is designed around the assumption that a smart animal will learn, and builds the response to
keep up rather than pretending habituation won't happen. And most projects at this stage are demos —
this one has a forest department that has already committed to a real field trial with real footage,
which is the actual test of whether any of the above holds up outside a bench.

## Where it stands right now

Architecture is frozen and documented as a trail of dated, numbered decision records — eleven so far,
each with alternatives considered and consequences stated, not just a final answer with no reasoning
attached. Procurement is essentially complete. The web application (public site, resident and officer
dashboards, backend, ingest pipeline) is built and functioning. The device firmware is in active
bench-validation: individual sensor and actuator drivers are written, a manual hardware-verification
harness exists to confirm each actuator physically works before anything runs autonomously, and the
real sense-to-decision-to-action software loop has just been wired end to end in a deliberately
safe, dry-run-by-default mode pending a live hardware verification session.

## The goals this is aimed at

A field deployment with the Kerala Forest Department's Kothamangalam division on Aug 20, a 10-day
trial that produces the first real-world footage and data this project will have — and that footage
and deployment story is the core evidence for two competition submissions built directly on top of it:
the Arduino Physical AI Challenge India 2026 and Hackster's "Invent the Future with UNO Q." The field
trial isn't a side project alongside the contest push; it's the substance the contest write-ups are
built from.
