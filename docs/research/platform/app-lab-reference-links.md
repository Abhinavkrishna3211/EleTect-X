# App Lab / UNO Q / Edge Impulse — reference link index

Canonical upstream documentation for the App Lab stack on the UNO Q. Kept here so
neither a session nor a person has to re-derive where the authoritative page lives.
Findings distilled from these pages go in `app-lab-bricks-and-custom-models.md`;
this file is only the index.

Captured 30 September 2026.

## Arduino App Lab

| Page | URL |
|---|---|
| App Lab home | https://docs.arduino.cc/software/app-lab/ |

### Setup

| Page | URL |
|---|---|
| Setup overview | https://docs.arduino.cc/software/app-lab/setup/overview |
| Windows | https://docs.arduino.cc/software/app-lab/setup/windows |
| macOS | https://docs.arduino.cc/software/app-lab/setup/macos |
| Linux | https://docs.arduino.cc/software/app-lab/setup/linux |
| Standalone (board-only, no host IDE) | https://docs.arduino.cc/software/app-lab/setup/standalone |

### Configure

| Page | URL |
|---|---|
| Config | https://docs.arduino.cc/software/app-lab/configure/config |
| Settings | https://docs.arduino.cc/software/app-lab/configure/settings |
| Network configuration | https://docs.arduino.cc/software/app-lab/configure/network-configuration |
| Flash | https://docs.arduino.cc/software/app-lab/configure/flash |

### Getting started

| Page | URL |
|---|---|
| Quickstart | https://docs.arduino.cc/software/app-lab/getting-started/quickstart/ |
| Examples | https://docs.arduino.cc/software/app-lab/getting-started/examples/ |
| Glossary | https://docs.arduino.cc/software/app-lab/getting-started/glossary |

### Apps

| Page | URL |
|---|---|
| About apps | https://docs.arduino.cc/software/app-lab/apps/about-apps |
| Manage apps | https://docs.arduino.cc/software/app-lab/apps/manage-apps |
| Develop apps | https://docs.arduino.cc/software/app-lab/apps/develop-apps |
| Run | https://docs.arduino.cc/software/app-lab/apps/run |

### Bricks

| Page | URL |
|---|---|
| About bricks | https://docs.arduino.cc/software/app-lab/bricks/about-bricks |
| Use bricks | https://docs.arduino.cc/software/app-lab/bricks/use-bricks |
| Custom bricks | https://docs.arduino.cc/software/app-lab/bricks/custom-bricks |
| Bricks reference | https://docs.arduino.cc/software/app-lab/bricks/bricks-reference |

### Bridge (MPU <-> MCU)

| Page | URL |
|---|---|
| Get started with Bridge | https://docs.arduino.cc/software/app-lab/bridge/get-started-with-bridge |
| Bridge API | https://docs.arduino.cc/software/app-lab/bridge/bridge-api |

### CLI

| Page | URL |
|---|---|
| CLI overview | https://docs.arduino.cc/software/app-lab/cli/cli |
| Commands | https://docs.arduino.cc/software/app-lab/cli/commands |

### Integrations

| Page | URL |
|---|---|
| Companion app | https://docs.arduino.cc/software/app-lab/integrations/companion-app |
| AI models | https://docs.arduino.cc/software/app-lab/integrations/ai-models |
| Models | https://docs.arduino.cc/software/app-lab/integrations/models |

### Release notes

| Release | URL |
|---|---|
| 0.10 | https://docs.arduino.cc/software/app-lab/release-notes/release-0-10/ |
| 0.9 | https://docs.arduino.cc/software/app-lab/release-notes/release-0-9/ |
| 0.8 | https://docs.arduino.cc/software/app-lab/release-notes/release-0-8 |
| 0.7 | https://docs.arduino.cc/software/app-lab/release-notes/release-0-7 |
| 0.6 | https://docs.arduino.cc/software/app-lab/release-notes/release-0-6 |
| 0.5 | https://docs.arduino.cc/software/app-lab/release-notes/release-0-5 |
| 0.4 | https://docs.arduino.cc/software/app-lab/release-notes/release-0-4 |

## Edge Impulse

| Page | URL |
|---|---|
| Announcing support for the Arduino UNO Q | https://www.edgeimpulse.com/blog/announcing-support-for-the-arduino-uno-q/ |
| UNO Q board docs | https://docs.edgeimpulse.com/hardware/boards/arduino-uno-q |
| Arduino integrations overview | https://www.edgeimpulse.com/arduino-integrations |
| Run Arduino App Lab (deployment) | https://docs.edgeimpulse.com/hardware/deployments/run-arduino-app-lab |

## Source repositories

| Repo | URL | Why it matters |
|---|---|---|
| `arduino/app-bricks-py` | https://github.com/arduino/app-bricks-py | Authoritative brick sources: `brick_config.yaml`, `brick_compose.yaml`, Python API |

## Community threads

| Thread | URL | Takeaway |
|---|---|---|
| Custom AI Model for Arduino UNO Q not Working | https://forum.arduino.cc/t/custom-ai-model-for-arduino-uno-q-not-working/1447504 | Custom EI model silently fell back to the built-in model; fixed in Arduino App CLI **0.11.1** — requires deleting and re-downloading the model |
| Edge Impulse failed to push the model to Arduino Uno Q via App Lab | https://forum.edgeimpulse.com/t/edge-impulse-failed-to-push-the-model-to-arduino-uno-q-via-app-lab/18577 | App Lab filters EI projects on impulse metadata; a non-standard impulse is not offered for download |

## Walkthroughs and other sources

| Resource | URL | Assessment |
|---|---|---|
| EI blog — Rock Paper Scissors on UNO Q | https://www.edgeimpulse.com/blog/how-to-build-a-rock-paper-scissors-app-for-the-arduino-uno-q/ | Route A walkthrough end to end (pair accounts → import app → Video Object Detection brick → AI models tab → pick model → Run). No `app.yaml`, no CLI, no latency figures. Confirms the UI flow; adds no technical detail |

## Notes on coverage

Every link above was read. The Arduino docs pages are JS-rendered and return no
usable content to a plain fetch — the text behind them is in `arduino/docs-content`
under `content/software/app-lab/`, which is what was actually read. The 0.13.0 and
0.14.0-rc release notes are not on the docs site; they are on
https://github.com/arduino/arduino-app-lab/releases.

The `setup/{windows,macos,linux,standalone}` and `configure/*` pages are largely
host-install and UI walkthrough. They were read in full anyway; what was load-bearing
out of them — the outbound domain whitelist, the port table, SSH-on-by-default, and the
captive-portal / WPA2-Enterprise limits — is in section 17 of
`app-lab-bricks-and-custom-models.md` rather than summarised here.
