# EleTect X

**Adaptive Physical-AI platform for Human–Elephant Conflict (HEC) mitigation.**

EleTect X is a rugged, solar-powered, autonomous forest-edge node built on the Arduino UNO Q. It
detects elephants early through the ground (seismic), confirms with on-device vision, deters with
an adaptive, non-habituating light + sound response, alerts rangers and residents, and coordinates
with neighbouring nodes to steer wildlife safely — day and night, without cloud dependence in the
control loop.

## Why it's different

- **Seismic-primary, multimodal** detection (all-weather, day/night) — not a camera trap.
- **Adaptive deterrence** that measures outcomes and learns (contextual bandit), avoiding habituation.
- **Distributed coordination** — nodes create safe herding corridors, not random noise.
- **Ultra-low-power** event-driven architecture; weeks of autonomy on solar + LiFePO4.
- **Explainable fusion** — every alert traces back to which sensor said what, not a black box.
- **Extensible** — optional environmental / fire-risk / anti-poaching pods; road-signage integration.

## How it works

A node pairs an STM32U585 real-time microcontroller with a Qualcomm QRB2210 Linux computer on one
Arduino UNO Q board, split by responsibility rather than by chip:

```text
   Geophone / mic (always-on, µA)
            │
            ▼
   ┌────────────────────┐   footfall / acoustic events   ┌──────────────────────┐
   │  MCU — reflex       │ ───────────────────────────▶  │  MPU — cognition      │
   │  STM32U585          │  ◀───────────────────────────  │  QRB2210 (Linux)      │
   │  sensors, actuators,│      decisions (deter/alert)   │  vision, fusion,       │
   │  LoRa, power, safety│                                │  bandit, coordination  │
   └────────────────────┘                                └──────────────────────┘
            │                                                        │
            ▼                                                        ▼
   Horn / LED / IR deterrence                          LoRaWAN uplink → ranger dashboard
```

- **Reflex (MCU, always-on):** geophone STA/LTA trigger, acoustic gunshot/chainsaw gate, actuator
  timing, safety rule-gates, LoRa MAC, power management. Runs whether or not the MPU is awake.
- **Cognition (MPU, event-driven):** wakes on a reflex-layer event, runs an on-device vision
  detector, fuses every available sensor with a weighted log-odds model
  (`L = L_prior + Σ aᵢ wᵢ (ℓᵢ − ℓ₀ᵢ)`, explainable — missing sensors just drop out), then picks a
  deterrence action with a contextual bandit that never repeats the same tone and stops once the
  animal retreats, instead of blasting a fixed siren until it stops working.
- **Coordination:** nodes share detections over LoRa so a herd is steered along a forest-side
  escape lane, not trapped toward a village.
- **Autonomy:** all control decisions are made on the node. The cloud side is monitoring and
  analytics for rangers and residents, never in the detect→deter loop.

## Repository layout

| Path | Contents |
| --- | --- |
| [`app-lab/`](app-lab/) | Arduino App Lab package (manifest + assets) — the deployable app |
| [`device/mcu/`](device/mcu/) | STM32U585 real-time reflex firmware (C/C++, PlatformIO) |
| [`device/mpu/`](device/mpu/) | QRB2210 (Debian) cognition: vision, fusion, bandit, comms (Python) |
| [`ml/`](ml/) | Seismic/acoustic/vision model training + evaluation (off-device) |
| [`hardware/`](hardware/) | PCB (KiCad), enclosure CAD, wiring, bill of materials |
| [`web/backend/`](web/backend/) | Supabase schema, row-level security, edge functions |
| [`web/ingest/`](web/ingest/) | ChirpStack MQTT → Supabase bridge |
| [`web/frontend/`](web/frontend/) | Ranger/resident dashboard + public site (React PWA) |
| [`docs/decisions/`](docs/decisions/) | Architecture decision records — the "why" behind every non-trivial call |
| [`docs/research/`](docs/research/) | Background research (behavioral science, platform, competitors) |
| [`docs/runbooks/`](docs/runbooks/), [`docs/specs/`](docs/specs/) | Field procedures and hardware bring-up specs |
| [`deployment/`](deployment/) | Field install scripts and service units |
| `scripts/`, `tests/` | Cross-cutting utilities and tests |

Each top-level module also has its own README with the detail specific to it —
[`device/README.md`](device/README.md), [`web/README.md`](web/README.md),
[`ml/README.md`](ml/README.md), [`hardware/README.md`](hardware/README.md).

## Getting started

### Run the app on real hardware

The fastest path to a working node is [`app-lab/eletect-x/`](app-lab/eletect-x/) — a real Arduino
App Lab package. In short:

```bash
cp device/mcu/src/secrets.h.example device/mcu/src/secrets.h   # fill in your LoRaWAN credentials
BOARD_HOST=<your-board>.local scripts/sync-to-board.sh
```

then build/run the `eletect-x` app from App Lab or `arduino-app-cli`. See
[`app-lab/eletect-x/README.md`](app-lab/eletect-x/README.md) for the full sequence and
prerequisites.

### Build and test each piece independently

| Module | Command | Notes |
| --- | --- | --- |
| `device/mcu` | `pio run -e native` / `pio test -e native` | Host-only compile/test harness; never produces a flashable image ([details](device/mcu/README.md)) |
| `device/mpu` | `ruff check .` / `pytest -q` | Host-only lint/test; the real Bridge runtime only exists on the board ([details](device/mpu/README.md)) |
| `ml/` | see [`ml/README.md`](ml/README.md) | Training pipelines, run on a PC |
| `web/frontend` | `npm run dev` / `npm run build` | React PWA — dashboard + public site |
| `web/backend` | see [`web/backend/README.md`](web/backend/README.md) | Supabase schema + edge functions |

### Understand a design decision

Every non-trivial engineering call — why seismic over camera-only, why this horn, why this fusion
math — is recorded as an ADR in [`docs/decisions/`](docs/decisions/), numbered in the order they
were made. Start with `0001` for the core sensing/vision/fusion architecture.

## Status

Active development. Architecture frozen (see the ADRs); firmware and cognition layers are in
active bench validation, the web app is built, and field deployment with the Kerala Forest
Department is in progress.

## License

Proprietary — see [`LICENSE`](LICENSE).
