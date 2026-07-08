# Documentation

**Hierarchy (top → detail):** `CONTEXT.md` (canonical summary) → `docs/architecture/` + `docs/hardware/` (current design) → `docs/decisions/` (ADRs, the "why") → `docs/deployment/`, `docs/manufacturing/` (operational) → `docs/research/` (kept for reference) → `docs/archive/` (superseded, read-only).

**Rule:** exactly one current document per topic. If two disagree, `CONTEXT.md` wins; reconcile and archive the loser.

## Structure
| Folder | Holds | Status |
|---|---|---|
| `architecture/` | system, physical-AI, software, comms architecture | living |
| `hardware/` | BOM, camera, geophone, power, deterrence, enclosure specs | living |
| `decisions/` | ADRs (numbered), one per significant choice | append-only |
| `deployment/` | field-test protocol, KPIs, DFO, install guide | living |
| `manufacturing/` | DFM, in-house printing, assembly | living |
| `research/` | background studies still worth reading | frozen |
| `archive/` | obsolete / duplicated originals (dated) | read-only |

## Consolidation plan (migrate the existing research .md files)
The research phase produced many overlapping Markdown files. Consolidate as follows (one current doc per topic; everything else archived):

| Target (current) | Merge from |
|---|---|
| `CONTEXT.md` | Final Design Freeze + Pre-Build Optimization (decisions only) |
| `architecture/physical-ai.md` | Physical AI Architecture |
| `architecture/system.md` | Optimized Architecture + Rev B (UNO-Q-centric) + Rev B.1 (carrier-free) |
| `architecture/comms.md` | Connectivity Decision (LoRaWAN IN865) |
| `hardware/bom.md` | FINAL Freeze BOM |
| `hardware/camera.md` | Camera Shopping List + Comparison + IR-LED spec |
| `hardware/geophone.md` | Geophone Deployment Subsystem + Buy List |
| `hardware/deterrence.md` | Speaker Selection + Horn Analysis + Visual Deterrence Subsystem |
| `hardware/enclosure.md` | Concept Validation + Production Enclosure + In-House Manufacturing |
| `deployment/field-plan.md` | 45-Day Contest & Field Plan |
| `decisions/` (ADRs) | one ADR per frozen choice (camera, fusion, learning, comms, audio, geophone AFE) |
| `research/` | Ecological Framework, Confidence-Estimation study, Validation Report |
| `archive/` | all original Gemini deep-research drafts + any superseded review docs (prefix `YYYYMMDD-`) |

**Process:** (1) create the current docs above by lifting only the *decided* content; (2) move every original into `archive/` with a date prefix and a one-line "superseded by …" header; (3) never edit archived files. This yields a single source of truth that stays maintainable.
