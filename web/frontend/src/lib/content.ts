import { Award, BellRing, Eye, Medal, Network, Siren, Sprout, Sun, Waves } from 'lucide-react'

// Shared copy and image data for the public marketing site.
// Mirrors the structure of the design reference's renderVals() data block.

export const IMG = {
  hero: 'https://images.unsplash.com/photo-1608133013043-ec8c4965fa4d?auto=format&fit=crop&w=2000&q=80',
  interlude: 'https://images.unsplash.com/photo-1714281346649-3594296cc13f?auto=format&fit=crop&w=2000&q=80',
  techHero: 'https://images.unsplash.com/photo-1675956750740-c195299bafa1?auto=format&fit=crop&w=2000&q=80',
  elephant: 'https://images.unsplash.com/photo-1585970480901-90d6bb2a48b5?auto=format&fit=crop&w=1200&q=80',
  road: 'https://images.unsplash.com/photo-1660294534543-eb2bb92ed40f?auto=format&fit=crop&w=1200&q=80',
  rail: 'https://images.unsplash.com/photo-1685858874996-94c36ea9fb91?auto=format&fit=crop&w=1200&q=80',
  night: 'https://images.unsplash.com/photo-1500673922987-e212871fec22?auto=format&fit=crop&w=1200&q=80',
  fire: 'https://images.unsplash.com/photo-1536245344390-dbf1df63c30a?auto=format&fit=crop&w=1200&q=80',
  forest: 'https://images.unsplash.com/photo-1675956750740-c195299bafa1?auto=format&fit=crop&w=1200&q=80',
  canopy: 'https://images.unsplash.com/photo-1720086301592-c26d22710ef5?auto=format&fit=crop&w=1200&q=80',
  signage: '/assets/signage.jpg',
}

export const navLinks = [
  { label: 'Home', href: '/' },
  { label: 'Technology', href: '/technology' },
  { label: 'Solutions', href: '/solutions' },
  { label: 'Deployments', href: '/deployments' },
  { label: 'Research', href: '/research' },
  { label: 'About', href: '/about' },
  { label: 'Contact', href: '/contact' },
  { label: 'Stay Safe', href: '/stay-safe' },
]

export const stats = [
  {
    value: '~500',
    label: 'people killed every year in India in human-elephant conflict, 2,300+ deaths over 2019-2024',
  },
  {
    value: '~100',
    label: 'elephants die each year from conflict: electrocution, collisions, poisoning, retaliation',
  },
  {
    value: '56.6%',
    label: 'of households in Kerala hotspots lost more than half their seasonal crop',
  },
  {
    value: '26.7%',
    label: 'suffered total crop failure, plus property damage, livestock loss, and abandoned farmland',
  },
]

export const steps = [
  {
    n: '01',
    title: 'Sense',
    body: 'Feels the ground and listens to the forest, detecting animals in rain, fog, and total darkness, before they are visible.',
  },
  {
    n: '02',
    title: 'Confirm',
    body: 'Night-capable AI vision verifies the species, eliminating the false alarms that make farmers ignore sirens.',
  },
  {
    n: '03',
    title: 'Decide',
    body: 'Fuses ground, audio, and vision into one confidence score, and explains every decision it makes.',
  },
  {
    n: '04',
    title: 'Deter',
    body: 'Light and sound patterns that change every time and never repeat, so animals never habituate.',
  },
  {
    n: '05',
    title: 'Observe',
    body: 'Checks whether the animal actually left. If a pattern stops working, it stops using it.',
  },
  {
    n: '06',
    title: 'Learn',
    body: 'Builds a site-specific playbook of what works, per species, per season.',
  },
  {
    n: '07',
    title: 'Coordinate',
    body: 'Nodes work together to open a safe corridor back to the forest, steering herds away from villages, never trapping them.',
  },
]

export const compareRows = [
  { cap: 'Species-specific, low false alarms', us: '✓', alarm: '✗', fence: '–', cam: '✓' },
  { cap: 'Works at night, in fog and rain', us: '✓', alarm: '✗', fence: '✓', cam: '✗' },
  { cap: 'Animals never habituate', us: '✓', alarm: '✗', fence: '✗', cam: '–' },
  { cap: 'Warns people in seconds', us: '✓', alarm: '✗', fence: '✗', cam: '✗' },
  { cap: 'Coordinated across a whole boundary', us: '✓', alarm: '✗', fence: '–', cam: '✗' },
  { cap: 'Safe for all wildlife', us: '✓', alarm: '✓', fence: '✗', cam: '✓' },
  { cap: 'Cost per protected kilometre', us: '~1/10th', alarm: 'Low', fence: 'Lakhs/km', cam: 'Medium' },
]

export const solutionsData = [
  {
    title: 'Elephant-Conflict Mitigation',
    img: IMG.elephant,
    tease:
      'Crop-raid prevention first: detect herds before they reach the field, warn families in seconds, steer the herd home unharmed.',
    problem:
      'Roughly 500 people are killed every year in India in human-elephant conflict, mostly at night, when nobody sees the animal coming. In Kerala hotspots, 56.6% of farming households lost more than half a season’s crop to raids, and 26.7% lost the whole crop.',
    solution:
      'The network senses approaching elephants through ground and sound, confirms with night-capable vision, warns farmers, officers, and opted-in residents within seconds, and deters with ever-changing light and sound while opening a safe corridor back to the forest, no crop trampled, no elephant harmed.',
    why: 'Fixed sirens get ignored within weeks; fences cost lakhs per kilometre and harm other wildlife. EleTect adapts every encounter, protects the harvest, and costs roughly a tenth of fencing.',
  },
  {
    title: 'Road Safety',
    img: IMG.road,
    tease: 'Hold animals off the highway, and warn drivers before the bend.',
    problem:
      'Vehicle collisions are a leading cause of the ~100 elephant deaths every year in India, and they kill drivers too, especially on forest-edge highways like NH-766 and NH-85 at dawn and dusk.',
    solution:
      'Nodes along known crossing zones detect large animals approaching the verge, trigger roadside warnings and EleTect Signage displays, alert the control room, and steer animals toward safe passages.',
    why: 'Static signage is invisible at night and ignored by habit. EleTect warns only when an animal is actually there, so warnings keep their meaning.',
  },
  {
    title: 'Railway Safety',
    img: IMG.rail,
    tease: 'Early warning along track corridors where herds cross.',
    problem:
      'Train collisions are among the deadliest single events for elephants in India, a herd on the track at night gives a loco pilot no time to brake, a recurring risk on Kerala’s Ghat-adjacent rail corridors.',
    solution:
      'Detection nodes along vulnerable track sections identify herds approaching the corridor and push instant alerts to section control, giving time to caution trains through the block.',
    why: 'A networked early-warning line costs a fraction of elevated passages and works the day it’s installed, and it never dozes off.',
  },
  {
    title: 'Anti-Poaching & Illegal Logging',
    img: IMG.night,
    tease: 'The forest hears the gunshot and the chainsaw, and the patrol knows in seconds.',
    problem:
      'Poachers and illegal loggers work at night in remote terrain; by the time evidence is found, they are long gone.',
    solution:
      'Acoustic detection recognises gunshot-like transients and chainsaw signatures, triangulates across nodes, and silently alerts patrols, no local siren to tip anyone off.',
    why: 'Camera traps record what already happened. EleTect makes intervention possible while it’s happening, with audio archived as evidence.',
  },
  {
    title: 'Wildfire Early-Warning',
    img: IMG.fire,
    tease: 'Catch the smoulder before it becomes a front.',
    problem:
      'Forest fires in the Western Ghats often smoulder undetected for hours, by the time smoke is visible from a watchtower, containment is a battle.',
    solution:
      'Nodes sense smoke signatures and humidity shifts, triangulate across the network, and warn the Forest Department while the fire is still a patch of leaf litter.',
    why: 'A distributed sensing net covers valleys no watchtower can see, on solar, with no infrastructure to build.',
  },
  {
    title: 'Wildlife Analytics',
    img: IMG.canopy,
    tease: 'Every detection becomes long-term science.',
    problem:
      'Conservation decisions are made on sparse, seasonal survey data; corridors shift, and no one sees it until conflict spikes.',
    solution:
      'Every detection, movement, and deterrence outcome is logged into a structured behavioural record, movement corridors, activity rhythms, deterrence responses, for scientists and the Forest Department.',
    why: 'Camera-trap surveys sample weeks; EleTect observes continuously for years, day and night, in all weather.',
  },
]

export const solutionCards = solutionsData.map((s) => ({ title: s.title, tease: s.tease, img: s.img }))

export const otherWildlife = [
  {
    icon: '🐗',
    name: 'Wild boar',
    body: 'Rooting and crop damage in paddy and tapioca fields, deterred before the boar breaks the fence line.',
  },
  {
    icon: '🐃',
    name: 'Gaur (Indian bison)',
    body: 'Large, powerful, and unpredictable near settlements, given room and steered calmly away.',
  },
  {
    icon: '🦌',
    name: 'Sambar & spotted deer',
    body: 'Frequent grazing raids on young crops, deterred with gentle, non-lethal cues.',
  },
  {
    icon: '🐒',
    name: 'Monkey (macaque & langur)',
    body: 'Persistent raiders that habituate fast to static scares, the system’s ever-changing patterns keep working.',
  },
]

export const techPillars = [
  {
    icon: Waves,
    title: 'Senses through the ground and sound',
    body: 'Detection begins before the animal is visible, footfall vibration and acoustic signatures work in rain, fog, and total darkness.',
  },
  {
    icon: Eye,
    title: 'Night-capable AI vision',
    body: 'A second, independent confirmation step eliminates the false alarms that destroy trust in traditional systems.',
  },
  {
    icon: Siren,
    title: 'Adaptive, non-habituating deterrence',
    body: 'Light and sound patterns change every encounter and never repeat. The system verifies the animal actually left, and learns what works.',
  },
  {
    icon: Network,
    title: 'Networked intelligence',
    body: 'Nodes coordinate to open safe corridors and steer herds away from villages, shared awareness, not isolated gadgets.',
  },
  {
    icon: BellRing,
    title: 'Instant human early-warning',
    body: 'Officers and opted-in residents are alerted within seconds, SMS, WhatsApp, email, or push, chosen by configuration.',
  },
  {
    icon: Sun,
    title: 'Fully offline, solar-powered',
    body: 'Every node detects, decides, and deters with no internet at all. Connectivity adds coordination; it is never required to act.',
  },
]

export const products = [
  {
    id: 'x',
    name: 'EleTect X',
    tag: 'FIELD SENSOR NODE',
    img: IMG.forest,
    body: 'The core solar-powered detection node: ground vibration, acoustic, and night-capable vision fused on-device, deterrence built in.',
    specs: [
      'Solar + battery, fully offline',
      'Seismic + acoustic + vision fusion',
      'Adaptive light & sound deterrence',
      'Mesh-networked with neighbouring nodes',
    ],
  },
  {
    id: 'signage',
    name: 'EleTect Signage',
    tag: 'ROADSIDE WARNING DISPLAY',
    img: IMG.signage,
    body: 'A solar-powered digital sign that lights up only when EleTect X detects an animal nearby, so drivers trust it every time.',
    specs: [
      'Triggered live by nearby EleTect X nodes',
      'High-visibility solar e-ink / LED display',
      'Bilingual: English + Malayalam',
      'Solar-powered, no grid connection needed',
    ],
  },
  {
    id: 'future1',
    name: 'More products',
    tag: 'IN DEVELOPMENT',
    img: null,
    body: 'Additional hardware for farm boundaries, rail corridors, and community alerting is on our roadmap.',
    specs: [],
    placeholder: true,
  },
]

export const corridorSteps = [
  {
    node: 'S7-04 · CONTACT',
    action: 'First detection and deterrence, herd turned away from paddy boundary.',
  },
  {
    node: 'S7-05 · STEER',
    action: 'Gentle pressure from the south keeps the herd moving north-west.',
  },
  {
    node: 'S7-08 · GUIDE',
    action: 'Silent, leaves the corridor open. No deterrence in the escape path.',
  },
  {
    node: 'S7-11 · EXIT',
    action: 'Confirms forest re-entry, sends the all-clear, logs outcome for learning.',
  },
]

export const deployPhases = [
  {
    tag: 'ACTIVE',
    tagColor: '#5FA97C',
    bg: 'rgba(95,169,124,0.06)',
    title: 'Kerala Forest Department pilot',
    body: 'Field deployment in progress in conflict-hotspot sectors, live detection, deterrence, and officer alerting under real forest conditions.',
  },
  {
    tag: 'IN VALIDATION',
    tagColor: '#D9B44A',
    bg: 'rgba(217,180,74,0.05)',
    title: 'Effectiveness studies',
    body: 'Measuring deterrence outcomes, false-alarm rates, and habituation over full seasons with the department’s field staff.',
  },
  {
    tag: 'NEXT',
    tagColor: '#E2A13C',
    bg: 'rgba(226,161,60,0.05)',
    title: 'Scale to more ranges',
    body: 'The platform is designed to scale to thousands of nodes, road, rail, and farm-boundary deployments follow the pilot.',
  },
]

export const researchCards = [
  {
    title: 'Movement corridors',
    body: 'Continuous detection across the network reveals how herds actually move between forest blocks, season by season, year over year.',
  },
  {
    title: 'Behavioural response',
    body: 'Which deterrence patterns work, for which species, and for how long, measured against verified outcomes, not anecdote.',
  },
  {
    title: 'Conflict forecasting',
    body: 'Crop calendars, weather, and movement history combine into early risk signals for the sectors most likely to see conflict next.',
  },
  {
    title: 'Open collaboration',
    body: 'Anonymised, location-safe datasets available to research partners under Forest Department data governance.',
  },
]

export const team = [
  { initials: 'AK', name: 'Abhinav Krishna N', role: 'Co-founder' },
  { initials: 'AM', name: 'Amritha M', role: 'Co-founder' },
]

export const awards = [
  { icon: Award, label: 'IEEE IAS CMD Humanitarian Award 2025' },
  { icon: Medal, label: 'Amarnath Raja Humanitarian Technology Award 2025' },
  { icon: Sprout, label: 'Field deployment in progress, Kerala Forest Department' },
]
