# Repository Structure (authoritative)

```
EleTect-X/
├─ device/                      # ON-NODE software (Arduino UNO Q) — fully autonomous, no cloud in the loop
│  ├─ mcu/                      # STM32U585 (real-time reflex, C/C++, Arduino Core on Zephyr)
│  │  ├─ src/ include/ tests/
│  │  └─ lib/                   #   on-device TinyML: seismic footfall + ACOUSTIC anti-poaching (Edge Impulse export)
│  └─ mpu/                      # QRB2210 (Debian/Python, event cognition)
│     ├─ perception/ cognition/ bridge/ comms/ services/ tests/
│     └─ models/                #   on-device vision model (INT8)
├─ ml/                          # OFF-DEVICE model training (runs on a PC, not the node)
│  ├─ seismic/ acoustic/ vision/  #   pipelines → export to device/mcu/lib and device/mpu/models
│  ├─ datasets/ evaluation/
├─ hardware/
│  ├─ bom/                      # single BOM home (bom.md)
│  ├─ pcb/ cad/ wiring/
├─ web/                         # OFF-DEVICE monitoring web app (renamed from "cloud" — NOT part of control)
│  ├─ frontend/                 #   React PWA: ranger dashboard + public marketing site
│  ├─ backend/                  #   Supabase: schema, RLS, edge functions
│  └─ ingest/                   #   ChirpStack MQTT → Supabase bridge
├─ docs/                        # CONTEXT.md (canonical) + architecture/hardware/decisions/deployment/…
├─ deployment/ scripts/ tests/
├─ README.md  CONTEXT.md  LICENSE  .vscode/  .github/  EleTect-X.code-workspace
└─ (local, git-ignored: editor/tool config + local working notes)
```

## Why these changes (per request)
- **`device/mcu` + `device/mpu`** — the Arduino UNO Q is a dual-brain board; splitting its code by processor mirrors reality (deterministic MCU firmware vs Linux MPU cognition) and keeps builds/flashing clean.
- **`cloud/` → `web/`** — the node is fully autonomous; "cloud" implied off-device control and caused confusion. `web/` is clearly just the monitoring web app (frontend + Supabase backend + ingest).
- **AI split: inference in `device/`, training in `ml/`** — models *run* where they execute (seismic + acoustic on the MCU, vision on the MPU), so inference code lives inside `device/`. Model *training* needs a PC + big datasets, so it lives in `ml/` and exports artifacts into the device folders. This keeps flashable device code lean and the training mess out of firmware.
- **Acoustic anti-poaching = Edge Impulse** — trained in `ml/acoustic/`, exported as a Cortex-M33 C++ library into `device/mcu/lib/` for always-on, low-power gunshot/chainsaw detection on the STM32.
- **`hardware/bom/`** — one home for the Bill of Materials.
