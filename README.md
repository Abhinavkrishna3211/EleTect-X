# EleTect X

**Adaptive Physical-AI platform for Human–Elephant Conflict (HEC) mitigation.**

EleTect X is a rugged, solar-powered, autonomous forest-edge node built on the Arduino UNO Q. It detects elephants early through the ground (seismic), confirms with on-device vision, deters with an adaptive, non-habituating light + sound response, alerts rangers, and coordinates with neighbouring nodes to steer wildlife safely — day and night, without cloud dependence.

## Why it's different
- **Seismic-primary, multimodal** detection (all-weather, day/night) — not a camera trap.
- **Adaptive deterrence** that measures outcomes and learns (contextual bandit), avoiding habituation.
- **Distributed coordination** — nodes create safe herding corridors, not random noise.
- **Ultra-low-power** event-driven architecture; weeks of autonomy.
- **Extensible** — optional environmental / fire-risk / anti-poaching pods; road-signage integration.

## Repository layout
| Path | Contents |
|---|---|
| `docs/` | Architecture, hardware, decisions (ADRs), deployment, manufacturing |
| `firmware/stm32/` | STM32U585 real-time reflex firmware |
| `linux/` | QRB2210 (Debian) cognition: vision, fusion, deterrence, comms |
| `ai/` | Seismic TinyML + vision model training/eval |
| `hardware/` | PCB, CAD/enclosure, wiring |
| `cloud/` | Backend + gateway ingest |
| `dashboard/` | Ranger web/PWA + public site |
| `deployment/` | Field protocols, install guides, logs |
| `scripts/`, `tests/` | Utilities and tests |

## Getting started
See [`CONTEXT.md`](CONTEXT.md) for the project's single source of truth, then [`docs/PROJECT_BLUEPRINT.md`](docs/PROJECT_BLUEPRINT.md) for the execution plan.

## Status
Active development. Architecture frozen; implementation in progress.

## License
Proprietary — see [`LICENSE`](LICENSE).
