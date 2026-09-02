# ADR 0015: Horn audio-content rotation and real per-tier volume escalation (anti-habituation, horn half)

- **Status:** proposed
- **Date:** 2026-09-01

## Context

ADR 0014 fixed the LED side of a problem this ADR closes out on the horn side. Restating the combined
finding precisely, because both ADRs now depend on it: **today's 3-tier escalation ladder
(`cognition/config.py`'s `DETERRENCE_TIERS`) produces zero physically-detectable difference in horn
output between tiers.** `docs/KNOWN_GAPS.md` (~line 62) and `cognition/config.py`'s own comment on
`TIER_1_GAIN_FRACTION`/`TIER_2_GAIN_FRACTION`/`TIER_3_GAIN_FRACTION` both say it plainly: "`gain_pct`
reaches the MCU and changes nothing audible... the DFPlayer always plays at its stored default level."
Separately, and never addressed anywhere in this repo before tonight: **the horn only has one axis at
all — loudness. It has no content axis.** Every tier, every trigger, every night of a 10-day unattended
field trial plays whatever single track sits at the DFPlayer's default index. `docs/research/
elephant-deterrence-behavioral-science.md` §2 (written earlier tonight) is direct on why that's a real
gap, not a nice-to-have: King, Douglas-Hamilton & Vollrath (2007, *Current Biology*) found disturbed-bee
playback drove a significant majority of 18 elephant family groups to flee, and Thuppil & Coss (2016,
*Oryx*) found tiger-growl playback deterred 90-100% of raid attempts in the field (leopard/lion
72.7-83.3%, human shouts 57.1%) — *content*, not just volume, is a real, evidenced deterrence lever this
device has never used.

**Real hardware for this chain is confirmed** (user-provided, cross-checked against `CONTEXT.md` §3 and
ADR 0003/0011, which already name all three parts):

- **DFRobot DFR0768 "DFPlayer Pro"** — the source module `CONTEXT.md`/ADR 0011 call "DFPlayer-PRO."
  3.3–5V, 128MB built-in storage (no SD card), UART with a documented AT-command protocol *in addition
  to* single-button (`KEY` pin) and ADKEY control modes.
  [wiki.dfrobot.com/dfr0768](https://wiki.dfrobot.com/dfr0768) ·
  [protocol reference](https://wiki.dfrobot.com/dfr0768/docs/20422) ·
  [reference library](https://github.com/DFRobot/DFRobot_DF1201S)
- **TPA3116D2 XH-M543** — the amp board ADR 0003 already specified (single BTL channel, software-limited
  ~6-8W of its ~12W headroom at the 12.8V rail). No digital gain interface on this board; gain is a
  physical trim pot set once at build time and out of scope for per-tier control, exactly as ADR 0003
  already assumed. [Product page](https://techtonics.in/product/tpa3116d2-xh-m543-120w-dual-channel-high-power-digital-power-amplifier-board/)
- **Ahuja SUH-15** — the horn ADR 0003/0004/0005 already selected and re-confirmed after the TOA
  comparison: 15W RMS/23W max, 8Ω, 275–7,000Hz, 106dB/1W/1m, IP66.
  [Verified spec sheet](https://www.industrybuying.com/pa-horn-ahuja-ITS.PAH.539225398)

None of this changes ADR 0003's amplifier/speaker decision. What changes is the **source module's
control path** — and a real constraint surfaced while checking it that the earlier ADKEY-pulse sketch
(mirroring the K1 GPIO-trigger pattern used elsewhere on this board) did not account for:

**`PIN_MAP.md` states "USART1 on D0/D1 is the only UART broken out to the top headers," and it is
already fully claimed by the Grove LoRa-E5** (`LORA_UART_RX_PIN`/`LORA_UART_TX_PIN`, `config.h`). A
DFR0768 UART link cannot reuse that pair without contending with LoRa. This ADR's design routes around
that constraint rather than ignoring it — see Decision A.

**`hardware/WIRING_GUIDE.md` is referenced throughout this repo (`PIN_MAP.md`, ADR 0014, `KNOWN_GAPS.md`)
but is not present in this session's working copy of the tree.** The pin-level wiring content this ADR
would normally add as its own numbered section lives in this document's Decision section instead —
**whoever has the canonical file needs to merge it in**, flagged here so it isn't silently lost the way
0014's own doc almost was (see the "Also landed tonight" note at the end of this ADR).

### Update, real datasheets reviewed: one correction, two confirmations

**⚠ Superseded below — see "Second correction" further down.** The "correction" in this subsection
(`AT+PLAYNUM` → `AT+PLAYFILE`) was itself wrong, made on the strength of a PDF that turned out to be for
the wrong sibling chip. Kept here unedited, as the honest record of what happened and why, rather than
quietly rewritten — the real board's own photo and its own DFRobot-hosted protocol page (further down)
settle it: **`AT+PLAYNUM` was correct in the original draft all along.**

The user supplied the actual DFPlayer-family datasheet/schematic and the official Arduino UNO Q full
pinout. Reviewing both against this ADR's draft surfaced one real bug and closed out two of the open
questions:

**Correction — the file-select command is `AT+PLAYFILE`, not `AT+PLAYNUM` as this draft originally had
it.** The datasheet supplied (uploaded as `DFR0768_dfplayerpro_datasheet_V1.0.pdf`, but its own title
page reads "DF1101S Datasheet," DFRobot, 2020.11.25 — see the product-identity caveat right below)
documents the AT
command set for the **DF1101S** chip — the same chip DFRobot's DFPlayer Pro family is built on — and its
command table is explicit: `AT+VOL=5\r\n` (0–30, `-n`/`+n`/`N`/`?` forms, matching this ADR's Decision C
exactly) and **`AT+PLAYFILE=5\r\n` — "Play the designated specific file," file number as the
parameter**. There is no `AT+PLAYNUM` command anywhere in this datasheet. Every occurrence in this
document has been corrected from `AT+PLAYNUM` to `AT+PLAYFILE` — the wiki page consulted during this
ADR's first pass evidently mis-transcribed it; the vendor PDF is the more
authoritative source and is what this correction is based on. **This also resolves the "does the file
selection call autoplay" open question in the affirmative** — the datasheet's own function description
is literally "Play the designated specific file," not "select" or "cue" — so Decision E's fire sequence
no longer needs a defensive follow-up `AT+PLAY=PP`. Downstream: the draft firmware code (`horn.cpp`)
still carries the old wrong name in its literal command strings — this is tracked in
`docs/KNOWN_GAPS.md`'s updated entry, not fixed here since code changes are out of scope for this doc.
**None of this paragraph held up — see "Second correction" below: the datasheet quoted here was for the
wrong chip (DF1101S, not the board's actual DF1201S), the draft's original `AT+PLAYNUM` string was never
wrong, and the autoplay question is open again.**

**Real product-identity caveat on that same datasheet, stated plainly rather than glossed over:** its
title page says "DF1101S Datasheet" and its schematic page's title block reads `Code: DFR0745`,
`Title: breakout:Voice Recorder` — this is DFRobot's **DF1101S chip-level datasheet**, packaged with a
schematic for a *different, sibling breakout board* (DFR0745, which drives a speaker directly off an
onboard HX8358 class-D amp via `SPK+`/`SPK-`), not the DFR0768 "DFPlayer Pro" board itself, which the
user's own product photos show has no onboard amp and instead breaks out raw `DACR`/`DACL`/`L+`/`L-`/
`R+`/`R-` for an external amp (matching this project's actual TPA3116D2-based design). Both boards are
built on the same DF1101S chip, so the **AT-command protocol content above is treated as authoritative
for DFR0768 too** (chip-level firmware, not breakout-specific) — but the **physical pin breakout differs
between the two boards**, and only the DFR0768-specific pinout (12 pads: `VIN GND RX TX DACR DACL L+ L-
R+ R- PLAY KEY`, per the user's own product photo) should be used for wiring, not DFR0745's `J1`/`J2`
header layout.

**That same DFR0745 schematic page 6 has real, useful data for Decision A's fallback path, with a real
correction to how this ADR described it**: the datasheet's ADKEY table (10 keys, K1–K10, each a distinct
resistance in series on a single analog pin wired to the chip's `PB4`) is genuine and detailed — but
**DFR0768's own physical breakout does not expose an `ADKEY` pad at all**, per the user's product photo
pinout table (12 pads listed: `VIN, GND, RX, TX, DACR, DACL, L+, L-, R+, R-, PLAY, KEY` — no `ADKEY`
row). DFR0768 instead exposes two separate discrete pads, `KEY` and `PLAY`, each presumably a single
direct-to-chip-pin button (not a resistance-ladder multi-key input). This ADR's fallback (originally
"the ADKEY/`KEY`-pin GPIO-pulse pattern... for coarse relative volume-up/down") **overstated what the
non-UART fallback can actually do**: without the resistor-ladder `ADKEY` pad, there is no confirmed GPIO
path to volume-up/down or next/last at all on DFR0768 specifically — only whatever `KEY` and `PLAY`
individually trigger (most likely play/pause-class functions, unconfirmed without a direct DFR0768 pin-
function reference, which was not supplied). **The fallback is downgraded accordingly** — see the revised
Decision A fallback list below.

**Confirmed independently by the official Arduino UNO Q pinout (`docs/decisions/0010`'s "advanced,
unofficial" caveat does not apply here — this is the vendor's own published, CC-BY-SA-licensed pinout
reference, dated 17 Feb 2026)**: the "Digital" pin table shows exactly one `UART/USART`-labeled pair on
the whole board — `D0`/`PB7`/`USART1_RX` and `D1`/`PB6`/`USART1_TX` — and no second USART/UART appears
anywhere else on the four-page pinout, including the two 60-pin advanced `JMISC`/`JMEDIA` connectors
(explicitly labeled "These pins can not be used as regular GPIOs" — camera/display/trace/PSSI signals,
not general-purpose peripheral pins). **This closes out Decision A's fallback option 1** ("a genuine
second hardware USART... reachable via an unpopulated test point") as a dead end on this board — there
is no second real UART to find. It also independently confirms `D9`/`PB8` and `D10`/`PB9` (this ADR's
chosen pins) as ordinary digital GPIOs with no default peripheral claim, exactly matching `PIN_MAP.md`'s
own "free" list. Net effect: **the `SoftwareSerial`-on-D9/D10 path is now confirmed as the only route to
real AT-command control on this board** — not merely preferred over alternatives, the only one that
exists — which raises the stakes on the still-open "does this Zephyr-based Arduino Core actually support
`SoftwareSerial`" question (unchanged, still unverified, still the single most important thing to check
first at bring-up).

**Purchase-source confirmation (2026-09-01, later same session):** the user provided the actual retail
listing this unit was bought from —
[robu.in: "DFRobot Fermion DFPlayer Pro — A Mini MP3 Player with On-board 128MB Storage (Breakout)"]
(https://robu.in/product/dfrobot-fermion-dfplayer-pro-a-mini-mp3-player-with-on-board-128mb-storage-breakout/).
The listing itself carries no pinout/protocol detail (checked directly — just the product name and the
128MB storage spec), but that name and storage figure match DFRobot's own DFR0768 "Fermion: DFPlayer
Pro" listing exactly, and 128MB-built-in (no SD card) is specifically the DFPlayer Pro family's
distinguishing spec versus DFR0745's SD-card-based "Voice Recorder" design. This is independent
confirmation — from the actual purchase record, not just the product photos — that the board in hand is
DFR0768 proper. **The chip-level claim in that paragraph ("AT-command protocol from the DF1101S datasheet
applies to DFR0768 too") is now retracted — see immediately below.**

**Second correction (2026-09-01, same session, closes out the first one): `AT+PLAYNUM` was right all
along — the chip on the user's actual board is DF1201S, not DF1101S, and DF1201S's own protocol page
documents `AT+PLAYNUM` as a real, distinct command.** The user photographed their physical board directly
(both a labeled pinout photo and a close-up of the chip package itself, ic marking legible: **`DF1201S`**
— not `DF1101S`). That single photographed part number is what finally resolves the product-identity
question this ADR has been circling since the first correction: the datasheet PDF the user uploaded
earlier was titled "DF1101S Datasheet" and packaged a `DFR0745`-coded schematic — genuinely the wrong
chip family, not just the wrong breakout board, contrary to what the first correction assumed ("both
boards are built on the same DF1101S chip" — that premise was itself false).

Fetched directly from DFRobot's own DFR0768 protocol reference page
([wiki.dfrobot.com/dfr0768/docs/20422](https://wiki.dfrobot.com/dfr0768/docs/20422) — already linked in
this ADR's Context section since the first draft, tonight is the first time its command list was checked
against the DF1101S PDF's), the two commands are real, distinct, and not interchangeable:

| Command | Syntax | Parameter | What it does |
|---|---|---|---|
| `AT+PLAYNUM` | `AT+PLAYNUM=5` | file **number** (sequential index; "Play the first file if there is no such file" on an out-of-range index) | "Play the file of the specified number" |
| `AT+PLAYFILE` | `AT+PLAYFILE=/DF_REC/test.MP3` | file **path** (string) | "Play the specific file" |

This project's `drive_horn(track_id: uint8)` wire field is a numeric index by design (schema.md,
`cognition.config.HORN_CONTENT_LIBRARY` maps small integers to content) — that is `AT+PLAYNUM`'s exact
parameter shape, not `AT+PLAYFILE`'s path-string shape. The original draft code's `AT+PLAYNUM=%u\r\n` was
correct for this design from the start; the sed-based "fix" earlier in this ADR was a real regression,
caught only because the user went one step further and photographed the actual chip marking rather than
trusting the uploaded PDF's cover page. **Every `AT+PLAYFILE` occurrence introduced by the first
correction, below and in Decisions E/F, Alternatives, and Consequences, is reverted back to
`AT+PLAYNUM` in this pass** — with the change now anchored to the correct board's own documentation, not
a mismatched-product PDF.

One consequence carries forward, not resolved: the DFR0768 protocol page **does not state** whether
`AT+PLAYNUM` autoplays or only cues the file pending a separate `AT+PLAY=PP` (confirmed by direct
re-check of that page's text) — so the "autoplay confirmed" claim the first correction made is *also*
retracted. This reopens `docs/KNOWN_GAPS.md`'s autoplay entry as UNVERIFIED, exactly as it was in the
original draft before tonight's PDF-driven detour.

**Third confirmation, strongest yet — the user photographed their own physical unit's top and bottom
silkscreen directly.** The back of the board prints **`DFR0768`** and **`DFPlayer PRO V1.0`** in plain
text, next to the DFRobot logo — first-party confirmation straight off the actual PCB, superseding every
inference made so far from product photos, the retail listing, or any datasheet. Product identity is now
settled beyond doubt: this is a DFR0768 DFPlayer PRO, hardware revision V1.0.

Both faces show all 12 pads with fully legible silkscreen labels, confirming the pinout already in use
throughout this ADR, with one small correction to the documented pad *order* (the pads themselves are
unchanged — each is individually labeled, so wiring is by name, not position, and nothing physical needs
to change): reading the photographed board, one edge carries `VIN GND RX TX DACR DACL` and the other
carries `KEY PLAY R- R+ L- L+` — i.e. `R-`/`R+` before `L-`/`L+`, not `L+ L- R+ R-` as earlier text in
this ADR had it. Cosmetic only.

**New finding, not previously known:** the back of the board also shows a second populated IC silkscreened
`PAM8403` (Diodes Inc., a real, well-known 3W stereo Class-D amplifier chip) next to a large multi-pin
package. This means the **DFR0768 does carry a small onboard amplifier after all** — contrary to this
ADR's earlier product-identity paragraph, which said DFR0768 (unlike DFR0745) "has no onboard amp." The
likely correct picture, matching a pattern also seen on the classic DFPlayer Mini (onboard amp *and*
separate line-level DAC pins, simultaneously): `L+`/`L-`/`R+`/`R-` are the `PAM8403`'s own amplified,
speaker-level output (good for a small direct-drive speaker, well under what the SUH-15 horn needs), while
`DACR`/`DACL` remain a separate, raw line-level output bypassing that onboard amp — which is exactly the
pair this ADR's design already wires to the external TPA3116D2. **No change to Decision A's wiring** —
DACL/DACR → TPA3116D2 is still correct, and now for a clearer reason (bypassing a too-small onboard amp
entirely, not just "avoiding speaker-level pins" as originally reasoned) — but the earlier "no onboard
amp" claim is retracted and should not be repeated. The main audio/UART decoder IC's own marking is not
legible in either of these two photos (different angle/lighting than the earlier chip-marking photo that
read `DF1201S`), so this doesn't independently re-confirm or contradict that reading — noted, not
resolved either way.

**Provenance closed out — retail packaging photographed too.** The original DFRobot retail box's own
label reads `DFROBOT / DFR0768 / DFPlayer PRO`, barcoded, "Made in China," with the same physical board
(same pinout, same `DFPlayer PRO V1.0` PCB print) still seated in its anti-static wrap alongside it. Adds
no new technical fact beyond the two confirmations directly above, but closes the identity question from
every independent angle available short of opening the main chip's datasheet by its exact part number:
retail listing, product photos, board silkscreen, and now factory packaging all agree. Nothing here
changes Decision A's wiring or either of the two still-open UNVERIFIED items (`SoftwareSerial` support,
`AT+PLAYNUM` autoplay).

## Decision

### A. New UART link on free pins, not the claimed LoRa pair

Add a second UART to the DFR0768, on two of `PIN_MAP.md`'s explicitly free pins: **D9 (PB8) as MCU
TX → DFPlayer RX, D10 (PB9) as MCU RX ← DFPlayer TX.** This is a bit-banged (`SoftwareSerial`-style)
link, at **115200 baud** — DFR0768's confirmed default and the exact baud DFRobot's own reference
sketch uses over a `SoftwareSerial` instance
([`DFRobot_DF1201S` example](https://github.com/DFRobot/DFRobot_DF1201S)), so this is not a novel
protocol guess, it is the vendor's own documented pattern applied to two different free pins.

**Flagged UNVERIFIED, matching this repo's own convention for exactly this kind of claim** (see
`LORA_SERIAL`'s "whether the Arduino Core also exposes ... unconfirmed" comment in `config.h` for
precedent): the Arduino UNO Q's MCU core runs on **Zephyr**, per `docs/decisions/0010-platformio-
host-harness-vs-app-lab-target.md`'s framing — a non-AVR target. Whether the Zephyr-based Arduino Core
this project builds against actually ships a working `SoftwareSerial` equivalent is **not confirmed**
and must be checked early in bring-up, before any firmware depending on it is trusted. Formerly two
fallbacks were named here; the official UNO Q pinout (see the "Update, real datasheets reviewed" note
above) has since closed one of them out:

1. ~~A genuine second hardware USART peripheral on the STM32U585, not broken out to the header~~ —
   **ruled out.** The official Arduino UNO Q full pinout (vendor-published, dated 17 Feb 2026) shows
   exactly one `UART/USART`-labeled pin pair on the entire board (`D0`/`D1`), including the advanced
   `JMISC`/`JMEDIA` connectors, which carry camera/display/trace signals only. There is no second
   hardware UART anywhere on this board to fall back to.
2. Fall back to `KEY`/`PLAY` GPIO pulses — **downgraded from the original plan, not a like-for-like
   substitute.** The DFR0768-specific product photo pinout (12 pads: `VIN GND RX TX DACR DACL L+ L- R+
   R- PLAY KEY`) has no `ADKEY` pad — that resistor-ladder multi-key input (K1–K10, real values in the
   DF1101S datasheet's §5) exists on the sibling DFR0745 breakout, not confirmed present on DFR0768's own
   exposed pads. Without it, the only fallback control is whatever `KEY` and `PLAY` individually trigger
   as discrete buttons — most likely play/pause-class functions, **not confirmed to include volume or
   track selection at all**. If `SoftwareSerial` fails at bring-up, this fallback may only recover "fire
   the horn at its last-set volume/track," not real per-tier control — say so plainly rather than assume
   it degrades gracefully to "coarse but functional."

Given fallback 1 is now closed and fallback 2 is weaker than originally described, **`SoftwareSerial`
support is the single highest-priority thing to confirm at bring-up** — if it fails, the realistic
options are exhausting DFR0768's actual `KEY`/`PLAY` behavior on a bench first (undocumented here, needs
a real module in hand) before concluding volume/content control isn't achievable without a hardware
change.

The pure logic in Decision B/C below (gain→volume mapping, command-string construction) does not depend
on which transport wins — it is plain string/integer functions with no `Serial` dependency, so nothing
here is wasted if the fallback is needed.

### A.1 Full signal chain, consolidated — UNO Q ↔ DFR0768 ↔ TPA3116D2 ↔ SUH-15

Every pin below is now confirmed against a real, vendor-published source (official UNO Q pinout, the
DF1101S/DFR0768-family datasheet, and the user's own product photos/pages for the amp and horn) rather
than inferred — collected here in one table since it was previously scattered across `PIN_MAP.md`,
Decision A, and ADR 0003/0011.

| From | Pin | To | Pin | Notes |
|---|---|---|---|---|
| Battery (LiFePO4, 12.8V nominal) | `BATBUS_12V8` (via fuse/switch/splice, `PIN_MAP.md`) | TPA3116D2 XH-M543 | `V6`/VCC `+` | Direct from the battery bus, **not** through the UNO Q — matches ADR 0003's existing power architecture. XH-M543's own spec range is 12–24V; 12.8V is within range but at the low end (50W/ch is the 12V figure, not the 120W/ch 24V headline number — irrelevant here, ADR 0003 already software-limits to ~6-8W of a much smaller headroom anyway). |
| Battery `-` / system ground | — | TPA3116D2 XH-M543 | `V6`/VCC `-` | Common ground across the whole chain (next four rows too) — a shared, low-impedance ground return matters for audio; a poorly grounded run is a classic source of hum/noise on a line-level signal this short. |
| UNO Q | `+5V` pin (`RAIL_5V`, `PIN_MAP.md`) | DFR0768 | `VIN` | DFPlayer runs off the UNO Q's regulated 5V rail, not the raw 12.8V battery bus — already established in `PIN_MAP.md`, restated here for one-place reference. |
| UNO Q | `GND` | DFR0768 | `GND` | |
| UNO Q | `D9` / `PB8` (new, this ADR) | DFR0768 | `RX` | MCU TX → DFPlayer RX (`SoftwareSerial`, 115200 baud, Decision A). |
| UNO Q | `D10` / `PB9` (new, this ADR) | DFR0768 | `TX` | MCU RX ← DFPlayer TX. |
| UNO Q | `D4` / `PA12` (`HORN_AMP_ENABLE_PIN`, existing) | IRLZ44N MOSFET gate | — | **Not a pin on the amp board itself** — this drives a MOSFET in series with the amp's 12.8V VCC feed, gating power to the whole TPA3116D2 board on/off (active-low = amp held in shutdown). Restating precisely because ADR 0003/`horn.cpp`'s comments call this "amp enable pin" in a way that could be misread as a control pin the XH-M543 board exposes — it does not; the board has no shutdown/enable pin in its own documented feature set, so gating its power rail is the only way to mute it in hardware. |
| DFR0768 | `DACL` | TPA3116D2 XH-M543 | 3P audio input, `INL` | **Use the single-ended `DACL`/`DACR` DAC pins, not `L+`/`L-`/`R+`/`R-`.** DFR0768 breaks out both: `DACL`/`DACR` are line-level DAC outputs meant for exactly this — feeding an external amp's line input. `L+`/`L-`/`R+`/`R-` are differential/BTL **speaker-level** outputs meant to drive a small passive speaker *directly, with no external amp* — feeding those into the XH-M543's line-level 3-pin input would be a level/impedance mismatch (amplified signal into a line input), a real wiring mistake to flag now rather than discover as distortion at bring-up. |
| — | — | TPA3116D2 XH-M543 | 3P audio input, `GND` (middle pin) | Ground reference for the line-level input — the 3-pin header is `Left / Ground / Right` per the product photo, a single-ended (not differential) input. |
| DFR0768 | `DACR` | TPA3116D2 XH-M543 | 3P audio input, `INR` | Only one of `INL`/`INR` is actually needed — ADR 0003 mandates a single BTL channel, not both bridged (PBTL) or both driven in stereo. Wire both DAC outputs for now (costs nothing) but only one XH-M543 output channel is used downstream. |
| TPA3116D2 XH-M543 | Left channel output `+`/`-` (whichever channel is actually used — pick one, ADR 0003) | Ahuja SUH-15 | `+`/`-` speaker terminals | Single BTL channel per ADR 0003 — do not also wire the Right channel output to the same or a second horn; that would be the PBTL-equivalent power level ADR 0003 explicitly rejected as exceeding the SUH-15's 23W rating. |
| — | `VOL_L` (or `VOL_R`, matching whichever channel is wired) trim pot | — | — | **Analog, physical, set once at build time** — confirms ADR 0003/0015's existing assumption that the amp's own gain is not digitally controllable. This pot sets the *ceiling*; per-tier loudness variation happens entirely upstream, at the DFR0768 via `AT+VOL` (Decision C) — set this pot once, near its own max within a safe margin under the SUH-15's rating, and never touch it again after commissioning. |

This table is what belongs in `hardware/WIRING_GUIDE.md`'s missing §3 (see the Context section's note that
the canonical file isn't in this working copy) — whoever has it should transcribe this table in, not
re-derive it from scratch.

### B. Wire schema change: `drive_horn` gains `track_id`

`bridge/schema.md`'s current contract: `drive_horn(schema_version, gain_pct: float (0–100), duration_ms:
uint16) -> ack: bool`. Bump `SCHEMA_VERSION` (same discipline ADR 0014 used for `drive_led`'s `gain_pct`
addition — a breaking wire change, MCU and MPU sides land together) and add `track_id: uint8`:

```
drive_horn(schema_version, gain_pct: float (0–100), duration_ms: uint16, track_id: uint8) -> ack: bool
```

`horn_request` (`horn.h`) gains the matching field. `horn_ack` does not need to echo `track_id` back —
unlike `gain_pct`/`duration_ms`, track selection is not subject to the MCU's own clamp, so there is
nothing for the ack to report that the caller doesn't already know it sent. (This is the same
`ack: bool`-is-lossy limitation `docs/KNOWN_GAPS.md` already flags for the other actuators — not made
worse here, just not fixed here either.)

### C. Gain mapping: wire `gain_pct` → real `AT+VOL`

DFR0768's confirmed protocol: `AT+VOL=<n>\r\n` sets absolute volume, range **0–30**
([protocol reference](https://wiki.dfrobot.com/dfr0768/docs/20422)). The wire's `gain_pct` (0–100,
already passed through `rule_gate_apply()`'s `HORN_GAIN_MAX_PCT` clamp before this conversion happens)
maps as:

```
dfplayer_vol = round(gain_pct / 100.0 * 30)   // clamped to [0, 30]
```

Applied to `cognition/config.py`'s existing tier fractions (`TIER_1_GAIN_FRACTION=0.25`,
`TIER_2_GAIN_FRACTION=0.45`, `TIER_3_GAIN_FRACTION=1.0`, the last clamped to `HORN_GAIN_MAX_PCT=60%` by
the MCU before this conversion sees it), the real numbers become:

| Tier | Wire `gain_pct` after MCU clamp | `AT+VOL=` |
|---|---|---|
| 1 | 25% | `AT+VOL=8` |
| 2 | 45% | `AT+VOL=14` |
| 3 | 60% (100% requested, clamped) | `AT+VOL=18` |

Three genuinely distinct volume levels — this is the exact "three tiers on paper, two in the field"
problem `cognition/config.py`'s own comment names, closed for real. `tests/test_horn_dfplayer` (added
in this ADR, see below) hard-codes 8/14/18 as anchor assertions and reads `HORN_GAIN_MAX_PCT` the same
cross-boundary-drift-check way `tests/test_cognition_config.py` already does for the LED/horn gain
ceiling, so this table silently goes stale-and-loud if either side's constants move without the other.

### D. Real, license-checked audio content — the actual "anti-habituation, horn half" of this ADR

Three tracks, sourced and license-verified tonight, forming the initial content library (DFPlayer file
numbers assigned arbitrarily here — final numbering is whatever `scripts/sync-to-board.sh`'s audio-load
step assigns when the files are actually copied onto the module's 128MB storage):

| File # | Content | Source | License | Cited effectiveness |
|---|---|---|---|---|
| 1 | Disturbed honeybee swarm | [Freesound 788025, RealSquink](https://freesound.org/people/RealSquink/sounds/788025/) | **CC0** — no attribution required | King et al. 2007: significant majority of 18 elephant family groups fled |
| 2 | Tiger roar/growl | [Freesound 149190, videog](https://freesound.org/people/videog/sounds/149190/) | **CC-BY 4.0** — attribution required | Thuppil & Coss 2016: 90–100% raid-attempt deterrence, the single best number in the literature |
| 3 | Lion roar/growl | [Freesound 212764, qubodup](https://freesound.org/people/qubodup/sounds/212764/) | **CC-BY 3.0** — attribution required | Thuppil & Coss 2016: lion/leopard growls, 72.7–83.3% |

**Attribution is a real, non-optional obligation for files 2 and 3** if this ships in a public/DFO
deliverable — carry "Tiger Roar by videog, CC-BY 4.0, freesound.org/s/149190" and "Lion Roar by Iwan
'qubodup' Gabovitch, CC-BY 3.0, freesound.org/s/212764" into whatever credits/acknowledgments surface
exists for this project (README, pitch deck, or a `docs/AUDIO_CREDITS.md` — not yet decided which, flag
for whoever owns that surface). File 1 (CC0) needs none. These three are a **starting set**, chosen for
being real, immediately verifiable, and license-clean tonight — not represented as an exhaustive or
final library. Each file is short (6–7s for the predator growls, well under `HORN_BURST_MAX_MS=3000ms`;
the bee track is 2:40 and needs trimming to a representative clip before loading) and will need real
trimming/normalization before going on the module, not used as downloaded.

**Tier-to-content mapping**, following Thuppil & Coss's own effectiveness ordering so escalation means
something on the content axis too, not just volume:

- **Tier 1** → file 1 (bee swarm) — mildest, matches Tier 1's existing "least force first" rationale
  (`cognition/config.py`'s IR-suppression comment already states this principle for the IR channel;
  applying the same logic to content is a natural, not novel, extension).
- **Tier 2** → file 3 (lion growl) — mid-tier predator content.
- **Tier 3** → file 2 (tiger growl) — the single best-evidenced deterrent in the literature, reserved
  for the tier that already fires everything else (IR, full LED, max horn gain).

`cognition/bandit.py`'s `DeterrenceAction` gains a `horn_track_id: int` field (paralleling
`led_pattern_id`); `cognition/config.py`'s `DETERRENCE_TIERS` sets it per the table above. This file's
Python-side changes are included in this ADR's diff but **could not be run against a real test suite in
this session** — `tests/test_cognition_config.py` (referenced by `cognition/config.py`'s own comments) is
not present in this working tree; whoever has the full repo should run it before trusting this merges
cleanly.

**Rotation, not just fixed per-tier assignment — stated as an extension by analogy, not as literature-
proven for audio:** `docs/research/elephant-deterrence-behavioral-science.md` §5 is explicit that
pattern/content rotation's evidence base is real field practice for **light** (Adams et al. 2020's
weekly color/pattern rotation) plus a general review recommendation (Montgomery et al. 2021), not a
dedicated audio-content-rotation study. Applying the same rotation principle to horn content — cycling
among multiple tracks *within* a tier's content pool across repeat triggers, rather than always playing
the same file for that tier — is a reasonable extension of a real principle, not an independently
evidenced one for sound specifically. With only one track currently sourced per tier, there is nothing
to rotate yet; this is scoped as a real near-term follow-up (source 2-3 tracks per tier, round-robin or
bandit-selected per repeat trigger) rather than built into this pass, matching the honest-scoping
discipline ADR 0014 itself models.

### E. Firmware sequencing change

`horn.cpp`'s existing fire sequence (`horn_fire_sequence()`) currently pulses `AUDIO_TRIGGER_PIN` — a
direct GPIO jumper into DFR0768's `KEY` pin — to start playback of whatever the module's default state
is. Per `PIN_MAP.md`, **this pin is marked "U" (unwired) — nothing physical has been built against it
yet**, which is exactly why this is the right time to change the approach rather than after real wiring
exists.

Proposed new sequence, replacing the `KEY`-pin trigger with the new UART link doing everything:

```
AMP_ENABLE low
  -> send "AT+PLAYNUM=<track_id>\r\n" over the new UART   (selects AND — believed, see caveat — starts playback)
  -> send "AT+VOL=<dfplayer_vol>\r\n" over the new UART
  -> wait HORN_AMP_ENABLE_DELAY_MS (retained, now covers AT-command processing + seek, not just seek)
  -> AMP_ENABLE high
  -> delay(duration_ms)
  -> AMP_ENABLE low
```

**Flagged UNVERIFIED rather than assumed**: whether `AT+PLAYNUM=<n>` auto-starts playback (matching the
DFRobot reference library's `playFileNum()` behavior, which the fetched library docs describe as playing
immediately) or only cues the file, requiring a separate `AT+PLAY=PP`, is not disambiguated by DFR0768's
own protocol reference page (confirmed by direct re-check — see "Second correction" above). This needs one
real check against the module before the firmware branches on an assumption — `docs/KNOWN_GAPS.md` keeps
this entry alongside the SoftwareSerial question, not silently assumed correct. If `AT+PLAYNUM` turns out
not to autoplay, add a follow-up `AT+PLAY=PP\r\n` send in the same slot.

This retires `AUDIO_TRIGGER_PIN` (D2/PB3) from the design — freed for other use if this holds up at
bring-up; kept documented in `config.h` rather than deleted outright until the UART path is physically
confirmed, so reverting to the `KEY`-pin trigger costs nothing if the UART path fails bring-up.

### F. Host-testable pure functions, new test target

`horn.h`/`horn.cpp` gain three pure functions with no `Serial`/hardware dependency, mirroring the
existing `footfall_probability_from_ratio()` precedent (`footfall_features.h`) of keeping the
computable core hardware-free and Unity-testable on `pio test -e native`:

- `horn_dfplayer_volume_from_gain_pct(float gain_pct) -> uint8_t` — the table in Decision C, clamped
  [0, 30].
- `horn_at_vol_command(uint8_t dfplayer_vol, char *buf, size_t buf_len) -> bool` — formats
  `"AT+VOL=<n>\r\n"`, returns false on a buffer too small to hold the result rather than truncating
  silently.
- `horn_at_playnum_command(uint8_t track_id, char *buf, size_t buf_len) -> bool` — same shape for
  `"AT+PLAYNUM=<n>\r\n"`.

New test target `tests/test_horn_dfplayer/test_horn_dfplayer.cpp`, Unity known-answer style matching
`test_footfall_features`'s convention (every failure names the input that tripped it): anchors the
8/14/18 table from Decision C, boundary-checks the 0/30 clamp, and checks exact command-string output
including the `\r\n` terminator (the protocol reference is explicit commands are rejected without it).
**Run against real `pio test -e native` in this session — see Consequences for the actual result.**

## Alternatives considered

- **Keep the ADKEY/`KEY`-pin GPIO-pulse pattern (mirroring K1), no UART at all.** This was the original
  sketch before the LoRa-UART-conflict and DFR0768-datasheet facts surfaced tonight. Rejected as the
  primary design: relative up/down button pulses drift out of sync with no way to query actual volume
  state (DFR0768's `AT+VOL=?` query has no button-mode equivalent), and there is no button-mode path to
  content/track selection at all, closing off Decision D entirely. Retained as the explicit fallback if
  the new UART link's `SoftwareSerial` dependency doesn't hold up (Decision A).
- **PBTL amplifier bridging for more SPL headroom.** Out of scope here — ADR 0003 already rejected this
  on the grounds that BTL already clears the proven-effective SPL reference with margin and PBTL would
  exceed the SUH-15's 23W rating. Nothing in tonight's research changes that call.
- **Reuse D0/D1 (the LoRa UART) with time-division sharing.** Rejected: `PIN_MAP.md` already marks that
  pair "P — wired 18 Aug, not yet answering AT probes," meaning LoRa bring-up on that link is itself
  unfinished and unstable; adding a second protocol sharing the same physical pins during an already-
  troubled bring-up is a worse starting position than two new dedicated pins on an unshared link.
- **Do nothing until the vendor/protocol details are independently re-verified against a physical
  module.** Rejected for the same reason ADR 0014 rejected waiting on stop-on-retreat: shipping tiers
  that still cannot vary loudness or content is strictly worse than shipping a design that can, even
  with two flagged-unverified assumptions (`SoftwareSerial` support, `AT+PLAYNUM` autoplay behavior)
  that bring-up will resolve either way.

## Consequences

+ Closes the exact gap `docs/KNOWN_GAPS.md` names ("`gain_pct` ... never wired to a physical volume
  control") using the fix that same entry already named as the right one ("the DFPlayer serial-command
  volume-set path (UART, not the GPIO trigger this session wired)").
+ Gives the horn a real content axis for the first time — the single highest-value, best-evidenced
  deterrence lever this repo's research turned up tonight (Thuppil & Coss's 90-100% number) had no
  implementation path before this ADR.
+ Together with ADR 0014, both deterrence actuators (LED, horn) now have genuinely distinct per-tier
  output — the combined "anti-habituation system" this session was asked to plan is real hardware/
  firmware/policy work, not just a research citation.
+ No change to ADR 0003's amplifier/speaker hardware decision, no change to `rule_gate.cpp`'s safety
  authority — `gain_pct`/`duration_ms` clamping is unchanged, `track_id` is not a value `rule_gate_apply`
  needs to bound.
- Two new GPIOs committed (D9/D10) where ADR 0014 managed zero — unavoidable for real AT-command control,
  flagged rather than glossed over.
- Two real open technical questions, both flagged UNVERIFIED rather than assumed, both need resolving
  during bring-up before this is trusted: whether this Zephyr-based Arduino Core supports the
  `SoftwareSerial`-style link this design assumes, and whether `AT+PLAYNUM` autoplays.
- `hardware/WIRING_GUIDE.md`'s new §3 (D9/D10 pin assignment, UART wiring detail) exists only inside this
  ADR in this session — needs merging into the canonical file by whoever has it; not done here because
  the file isn't in this working tree.
- Attribution obligations (files 2 and 3, CC-BY) are a real, tracked-here requirement on whatever
  public/DFO-facing materials ship with these tracks — not automatically satisfied by this ADR existing.
- Content rotation *within* a tier (Decision D's "extension by analogy" point) is explicitly not built in
  this pass — only one track per tier exists today. Real follow-up, not silently deferred.
- **Physical bring-up — wiring D9/D10, flashing this firmware, confirming the AT-command link against
  the real module — is not done in this session and must not happen unattended**, per this project's
  standing hard safety rule (`TRIAL_READINESS_PLAN.md`): reflash and any first physical fire of new
  wiring/firmware wait for daylight with the user physically present, batched with the other pending
  reflash items (D3 pin fix, LED pattern/intensity code) rather than as a separate flash cycle this close
  to the trial deadline.

## Process note: the code in this pass is an unverified draft

The Decision B/E/F code sketched alongside this ADR (`horn.cpp`/`horn.h`/`config.h`/
`bridge_handlers.*`/`fire_test.cpp`/`tests/test_horn_dfplayer`, and the MPU-side
`cognition/bandit.py`/`cognition/config.py`/`services/reflex_loop.py`/`services/config.py`/
`bridge/rpc.py`/`schema.md` changes) is a **draft, not trusted implementation** — it lands in the
tree for review, not as verified work.

What backs it so far: the pure volume/command-string logic was checked twice outside the real
harness (a standalone compile-and-run of the identical logic, and a `-fsyntax-only` compile of the
real `horn.cpp`/`horn.h` against a hand-built stand-in for the Arduino API), and the MPU-side Python
was imported and run for real (`cognition.config`/`services.reflex_loop` module execution, including
an end-to-end `handle_footfall_event` call against a fake `drive_horn`, `track_id` confirmed to
thread through). What is **not** backed: the real `pio test -e native` / `pytest` suites have not
been run against it — both must pass before any of this is treated as verified, on top of the two
UNVERIFIED hardware questions already flagged in `docs/KNOWN_GAPS.md` (SoftwareSerial support,
`AT+PLAYNUM` autoplay behavior).

## Also landed alongside this ADR, tracked here for continuity

ADR 0014 (LED pattern/intensity) and `docs/research/elephant-deterrence-behavioral-science.md` (the
citation base both this ADR and 0014 depend on) were drafted earlier but never copied into the repo
tree. Both are added here (`docs/decisions/0014-led-deterrence-pattern-and-intensity.md`,
`docs/research/elephant-deterrence-behavioral-science.md`) so this ADR's citations resolve to real
in-repo files rather than dangling references.
