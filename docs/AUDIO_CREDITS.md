# Audio credits

The deterrence horn plays short recorded tracks from the DFPlayer module's onboard flash rather
than a synthesised tone, because the published field evidence for elephant deterrence is about
*what the animal hears*, not about loudness alone (ADR 0015 Decision D, ADR 0016 Decision C).
Those recordings are third-party work, and three of them are licensed on condition that their
authors are credited wherever the work is distributed.

This file is that credit. It is the surface ADR 0015 said was needed and left undecided
("README, pitch deck, or a `docs/AUDIO_CREDITS.md` — not yet decided which"). It is linked from
the repository README so that a clone carries the attribution with the code, and it should be
reproduced in any public write-up, deck or deployment handover that ships or describes the audio.

## Attribution required

| Track | Author | Licence | Source |
|---|---|---|---|
| Tiger Roar | videog | [CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/) | [freesound.org/s/149190](https://freesound.org/people/videog/sounds/149190/) |
| Lion Roar | Iwan "qubodup" Gabovitch | [CC-BY 3.0](https://creativecommons.org/licenses/by/3.0/) | [freesound.org/s/212764](https://freesound.org/people/qubodup/sounds/212764/) |
| Firecracker_01.wav | CGEffex | [CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/) | [freesound.org/s/101130](https://freesound.org/people/CGEffex/sounds/101130/) |

Credit strings, for use verbatim in a deck, a caption or a spoken acknowledgement:

- Tiger Roar by videog, CC-BY 4.0, freesound.org/s/149190
- Lion Roar by Iwan 'qubodup' Gabovitch, CC-BY 3.0, freesound.org/s/212764
- Firecracker_01.wav by CGEffex, CC-BY 4.0, freesound.org/s/101130

All three are used in modified form: each was trimmed and level-normalised before being loaded onto
the module, because the raw files are longer than `HORN_BURST_MAX_MS` allows and are not mastered to
a consistent level. CC-BY permits modification and requires that it be stated, which is what this
paragraph does.

## No attribution required

Listed for completeness, so that a future reader can tell "cleared" from "not yet checked":

| Track | Author | Licence | Source |
|---|---|---|---|
| Intense Angry Bee Swarm (stereo) | RealSquink | CC0 | [freesound.org/s/788025](https://freesound.org/people/RealSquink/sounds/788025/) |
| airhorn.wav | guitarguy1985 | CC0 | [freesound.org/s/64476](https://freesound.org/people/guitarguy1985/sounds/64476/) |

## Scope

These five tracks are the provisioned library, not a final one. ADR 0016 Decision C records that
three of the four content categories currently hold a single track each, so there is no real
within-category rotation outside predator growl, and sourcing one or two more per category is an
open piece of work. Anything added to the module must have its licence verified from the sound's
own page — not from a search result — and must be added to the correct table above in the same
change that puts it on the flash. A track on the device and not in this file is a licence breach,
which is the failure this file exists to make visible.
