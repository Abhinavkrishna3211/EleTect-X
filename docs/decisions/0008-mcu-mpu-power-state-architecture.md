# ADR 0008: MCU/MPU wake, sleep, and power-state architecture

- **Status:** proposed — decision reached (deep suspend, not full poweroff); two confirming bench measurements remain before this can move to accepted
- **Date:** 2026-07-28

## Context

ADR 0007's Consequences section flagged an open item: "the STM32→QRB2210 wake mechanism itself isn't specified anywhere yet." Chasing that down surfaced a problem bigger than the acoustic subsystem — it calls into question whether CONTEXT.md §4's reflex (STM32, always-on µA) / cognition (QRB2210, event-only) split behaves the way the rest of the architecture assumes, on this specific board.

Three independent, credible sources, all real measurements rather than assumptions:

1. **Boot time.** A community benchmark using a logic analyzer measured **43.06s from power-on to the first sketch instruction on the MCU, and 46.37s to the first MPU-driven LED state change** ([myembeddedstuff.com](https://myembeddedstuff.com/arduino-uno-q-boot-time), cross-posted to the [Arduino forum](https://forum.arduino.cc/t/arduino-uno-q-the-43-second-boot-time-a-technical-breakdown-using-a-logic-analyzer/1425354)). By default the MCU sketch doesn't even start running until Linux/the App has booted — there is a "Startup mode" board option (`wait_linux_boot`: `yes` / `no` / `app`) where `no` ("Immediate") lets the sketch run at power-on regardless of Linux state, which is the mode this project needs, not the App Lab default.

2. **Standby power.** A separate forum user built almost exactly our use case — "the device needs to monitor a sensor continuously, such as a microphone... wake the MPU only when a relevant event is detected" — and measured real current draw with a lab supply: **deep suspend ≈0.082–0.088A @5.1V (≈0.42–0.45W); poweroff/shutdown ≈0.028A @5.1V (≈0.14W), with the MCU/LED matrix still visibly active in that state** ([forum thread](https://forum.arduino.cc/t/uno-q-edge-ai-is-promising-but-low-power-standby-is-difficult-for-always-on-sensing-applications/1446170)). Their own calculation: even the best of these states gives **3–5 days of standby** on a battery-only 18650/12V-SLA-class supply — nowhere near the multi-week autonomy an always-on field sensor needs. This is the single most important number to react to: it's roughly two to three orders of magnitude above a true µA-class reflex-only budget.

3. **Reset coupling.** A third thread ([link](https://forum.arduino.cc/t/can-the-stm32u585-mcu-keep-running-uninterrupted-while-the-qrb2210-mpu-reboots-or-enters-sleep-on-arduino-uno-q/1447600)) confirms the MCU **is reset when the MPU reboots** ("Yes," from an Arduino forum regular who tested it directly). Whether *suspend* (as opposed to reboot/shutdown) also resets the MCU is unconfirmed either way in that thread. Separately, in the low-power-standby thread above, a different user (`zarzi`) describes wanting exactly this project's split — STM32 hosts always-on sensing/wake logic, QRB2210 powers down completely between events — and concludes it isn't achievable today: *"all of this would require the ability to power down the MPU completely... "* with no confirmed mechanism for the MCU to bring it back up.

Put together: this board was not demonstrably designed, as shipped, for "MCU always awake at µA, MPU fully off until an external event wakes it cheaply and quickly." That's a real gap between what CONTEXT.md §4 assumes and what's been independently measured and reported by other builders on the same hardware. This is not a reason to panic or to abandon the reflex/cognition split — it's a reason to size the power budget around real numbers and pick a concrete power-state strategy deliberately, rather than let the assumption stand unexamined into the field-test build.

## Decision

**Default architecture: keep the MPU in deep suspend (Option A), not full poweroff, between events.** This is a real decision, not a placeholder, reached by re-verifying the one number that actually resolves the A-vs-B tradeoff: how much warning time the geophone genuinely buys us before an elephant reaches the boundary.

The field-*validated* (not theoretical) geophone detection range for elephant footfall is **140m in natural environments, 155.6m in controlled conditions, at 99.5% accuracy** (Wijayakulasooriya et al., cited fully below — this is the same paper family ADR 0001 already draws on for the seismic band, re-checked here specifically for range rather than frequency). The paper also cites much larger theoretical/instrumental limits (rumbles above ambient noise to 16km, stomps to 32km) — those are not the number to design a wake-latency budget against; they describe what a sensitive seismometer can detect in principle, not what a low-cost embedded geophone-and-amp chain reliably triggers a STA/LTA threshold on in the field. 140–155m is the honest number.

At a normal elephant walking pace (roughly 1.1–1.7 m/s), that range gives **~80–140 seconds of lead time** between geophone trigger and boundary arrival — comfortably more than a ~43–46s MPU cold boot plus whatever inference/fusion/decision time follows. But at a faster, agitated pace (an elephant that's already alarmed or moving with purpose can cover ground at 2.5–3+ m/s), the same range gives only **~45–65 seconds** — thin enough that a full cold boot alone could consume most or all of the available warning, before vision inference, fusion, and the bandit's decision even start. That worst case is exactly the scenario where a fast response matters most, so "usually fine" isn't good enough here.

Combined with the second open finding from Context — **no confirmed mechanism exists for the MCU to reliably power the MPU back up from a full poweroff state** (the Arduino community's own consensus, not just this project's assumption) — Option B (full poweroff) is rejected outright, not just deprioritized: it's both the riskier latency profile *and* the one nobody has shown how to implement on this board without additional hardware (an external MOSFET gating the MPU's rail, itself unconfirmed as physically accessible without a board modification). Option C (hybrid, gated by activity timing) is shelved for the same reason it was flagged as incomplete in the first draft of this ADR: it needs site-specific elephant activity data (e.g. dusk/night crossing patterns) this project doesn't have yet, and isn't worth the added firmware complexity until that data exists — it remains a plausible v2 refinement, not a launch requirement.

**So: MPU stays in deep suspend continuously (not powered fully off), and its ~0.42–0.45W continuous draw (≈10.8Wh/day) is now an explicit, named line item in the power budget rather than an unexamined assumption.** Against a 20W solar panel, that's a real but not obviously fatal fraction on a good day; it becomes the binding constraint specifically during Kerala's monsoon season, when solar harvest drops well below the annual average — which is the case worth stress-testing the budget against, not the average case.

Two specific confirming measurements remain — narrowed down from the original open-ended bench-validation ask to exactly what this decision depends on:

1. **Suspend-to-resume latency on our own board** (distinct from the 43–46s cold-*boot* figure, which is a different transition). Real Linux ARM platforms typically resume from suspend in low single-digit seconds, well inside even the 45–65s worst-case window, but this hasn't been measured on this specific board/OS image and needs to be before this decision is fully closed out.
2. **Monsoon-season solar budget recomputation**, folding in the newly-quantified 10.8Wh/day MPU-suspend baseline against realistic (not annual-average) irradiance for the wettest months, since that's the actual stress case this decision needs to survive.

## Alternatives considered

- **B. Full MPU poweroff between events, cold-boot on trigger.** Rejected — see Decision above: no confirmed wake-back-up mechanism, and even if there were one, the ~45–65s worst-case elephant lead time leaves too little margin against a ~43–46s cold boot plus inference/fusion/decision time on top, precisely in the fast-moving-animal case where margin matters most.
- **C. Hybrid, gated by time-of-day/activity probability.** Shelved, not rejected — needs site-specific activity data this project doesn't have yet; worth revisiting as a v2 power optimization once field data exists, not a precondition for the initial build.

## Consequences

- **This affects every subsystem that depends on an MPU wake, not just acoustic** — vision/fusion, the contextual bandit, LoRa uplink of decisions. ADR 0007's acoustic-specific wake question is resolved by this decision too: gunshot/chainsaw/vehicle/animal-call classification all wake an already-suspended (not powered-off) MPU, same as the geophone path.
- ~~CONTEXT.md §4 and §3's power-system BOM (4S LiFePO4 + MPPT + 20W solar) were sized without the ~10.8Wh/day MPU-suspend baseline.~~ **Stale as of 2 Sept — this was true when written on 28 Jul and stopped being true two weeks later.** The 12-13 Aug sizing (`hardware/bom/eletect-x-power-budget.xlsx`, `hardware/bom/procurement-status.md` §6) *does* carry the baseline as an explicit line item — 0.45W × 24h = 10.8Wh/day, dominating a 12.77Wh/day baseline subtotal, and the sheet's own Notes tab says "the power budget is baseline-dominated, not event-dominated." The recommendation below it was therefore actioned. The problem is no longer an omitted number; it is that the included number is almost certainly wrong — see the 2 Sept addendum.
- Reflex-layer safety net worth considering separately (not decided here, flagged for its own discussion): since even deep suspend has some resume latency, a simple STM32-only fallback deterrence trigger (basic horn/LED burst, no vision confirmation) for the rare case of an unambiguously strong, close geophone signal would remove dependence on MPU wake timing entirely for the worst-case scenario. This would be a genuine addition to CONTEXT.md §4's reflex-layer duties, not something already covered by "actuator timing; safety rule-gates" — worth its own decision, not smuggled in here.
- Two confirming measurements before this ADR can move to accepted:
  1. Suspend-to-resume latency on our own board (flash a minimal "Immediate" startup-mode sketch, command suspend, measure wake time — needs no new parts, just the board and a multimeter/scope already in hand).
  2. Power budget recomputation against realistic Kerala monsoon-season solar irradiance, not annual average, with the 10.8Wh/day MPU baseline included explicitly.

## Addendum, 29 Jul 2026 — official datasheet/power-spec cross-check

Read directly against the real Arduino UNO Q datasheet and official power-specification tutorial (not
community sources this time). Findings, none of which overturn the Decision above:

- **No official suspend/deep-sleep current-draw figure exists anywhere in Arduino's own documentation.**
  The ~0.42–0.45W measured suspend power this ADR's Decision is built on remains a community measurement,
  uncorroborated by an official number — still the right figure to design against (it's a real measurement,
  not a guess), just still flagged as community-sourced, not vendor-published.
- **New official figure, distinct from the 43–46s full-boot number:** after power-up, the datasheet
  describes the MPU driving a ready/wake signal to the STM32U585 at roughly **20 seconds** in — this is not
  the same milestone as "first sketch instruction" (43s) or "first MPU-driven LED change" (46s) from the
  community benchmark; it's an earlier, intermediate signal. Doesn't change the Decision's ~45–65s
  worst-case-lead-time math (still bounded by the later, larger figures), but worth having as a more precise
  intermediate checkpoint if boot-sequence debugging ever needs one.
- **Power sequencing, new:** 5V_SYS → 3.8V (PWR_3P8V) → 3.3V (PWR_3P3V) → 1.8V (PMIC LDO), with the 3.3V
  rail required to stabilize roughly 1ms before 1.8V enables. Relevant only if a future hardware revision or
  external supply rework ever touches these rails directly — not actionable for the current bench build.
- **Shutdown behavior, actionable correction:** `sudo shutdown now` / `sudo poweroff` do **not** reach a
  stable off state on this board — the board auto-restarts shortly after, by firmware design. Only
  `sudo halt` reaches a stable, non-responsive halted state while still powered. This matters for Option B's
  rejection above: it's not just that no confirmed *wake-back-up* mechanism exists from a powered-off state
  (already the Decision's stated reason) — the standard OS-level path to get to that state at all doesn't
  behave as naively expected either. One more reason Option A (deep suspend) is the right default, not just
  the safer one.
- **Power button, new:** a long press (≥5s) reboots Linux/the MPU but does not cut power to the board —
  consistent with, and a partial explanation for, the reset-coupling question this ADR already lists as
  unconfirmed. Still doesn't resolve whether the MCU is reset when the MPU reboots via *this specific*
  mechanism (vs. the forum-confirmed general reboot case) — schematic review found `MCU_NRST` and
  `PMIC_RESET` as separate named nets, suggesting they may be independent, but this needs a real bench test
  to close out, not a schematic read. Still an open item, not newly resolved.
- **CAD zip correction:** the downloadable "CAD Files" package from Arduino is raw PCB fab/EDA data (Cadence
  Allegro `.brd`/`.DSN`, Gerber, NC drill) for the UNO Q board itself — not enclosure STEP/STL files. Not
  useful for `hardware/cad/enclosure-design-concept.md` work; don't reach for it expecting enclosure
  geometry.

## Addendum, 2 Sept 2026 — the suspend state this ADR is built on has never existed on this board

Written while checking a separate question (event-video power cost, ADR 0020). Three findings, in
order of how much they matter. None of them changes the Decision above; all of them change how much
weight it can currently carry.

**1. Deep suspend is not implemented anywhere, and cannot be without new hardware.** `device/mpu/main.py`
ends in `while True: time.sleep(1)`. `MPU_WAKE_HOLD_S = 30.0` (`services/config.py`) is defined and has
**zero consumers** repo-wide. There is no `/sys/power/state` write, no `systemctl suspend`, no `rtcwake`,
nothing. The board's kernel does support it (`/sys/power/state` = `freeze mem disk`, `/sys/power/mem_sleep`
= `s2idle [deep]`, with `gpio-keys` armed as a wake source), but **nothing is wired to `gpio-keys`**, there
is no MPU wake or power-gate pin in `device/mcu/src/config.h`, and the only MCU→MPU wake path that exists
is the RouterBridge — a *userspace socket a suspended MPU cannot service*. `device/mpu/bridge/schema.md`
already says so in writing: "this schema assumes the wake path works, it doesn't." So this is a hardware
task (an internal wire, decided before the enclosure is sealed), not a software one.

**2. The as-built idle draw is very likely ~7x the design figure — and the number was already in this
repo.** `docs/research/platform/arduino-uno-q-power-and-ops.md` records a third-party bench review of a
UNO Q at **~3.3W (0.66A) idle with Linux up**, ~4.5W (0.90A) with all four A53s at 100%. `docs/KNOWN_GAPS.md`
**quotes those same figures** in the 2 Sept brown-out diagnosis, for an unrelated purpose, and nothing
connects them back to this ADR. Since the MPU never suspends, **~3.3W is the honest floor for the as-built
system, not 0.45W.** Note also how close idle sits to full load on this SoC: the floor is set by the QRB2210
and the OS image, not by what the Python process does.

**3. Nobody has ever put a meter on this node.** Everything measured on the assembled hardware is timing,
thermal, optical or accuracy — never current or power. `docs/ENGINEERING_CONVENTIONS.md` has required this
measurement since 3 Aug and it has never been run. It also cannot be taken in software: on this board
`/sys/class/power_supply/` is empty, all 11 hwmon devices are thermal zones with no `curr*`/`power*`
inputs, and `/sys/bus/iio/devices/` is empty. An inline meter on VIN is the only route.

### What the budget actually needs

Solving backward from harvest (panel W x 3.22 monsoon-derated PSH x 0.75 system derate) against the
19.47Wh/day design load structure, the **board baseline must come in under**:

| Panel | Monsoon harvest | Max sustainable board baseline |
|---|---|---|
| 20W | 48.3Wh/day | **<= ~1.4W** |
| 15W | 36.2Wh/day | **<= ~1.0W** |

Against 65.3Wh usable (12.8V x 6Ah at 85% DoD): at the design 0.45W the node has ~3.3 days of reserve
and a comfortable surplus; at ~3.3W it draws ~105Wh/day against 48.3Wh of harvest and **goes flat in
under two days of a ten-day unattended trial** — silently, because `battery_v` always returns `0.0f`
(no battery-monitor driver or ADC pin exists in `config.h`; see `docs/KNOWN_GAPS.md`).

### Status of this ADR after the addendum

Unchanged: still **proposed**, still blocked on the same two bench measurements, and the Decision
(suspend over poweroff) is still the right architecture *if* it is ever implemented. What has changed
is that the ~0.42-0.45W figure must be read as **a design target sourced from a third party, not a
property of this system**, everywhere it appears. A third open item is added to the two above:

3. **Real inline current measurement on this board's VIN**, at idle with the app running, during vision
   inference, during a horn+LED fire, and MCU-only as the floor. This gates whether the 10-day
   unattended premise holds at all, and it gates it *before* any decision about implementing suspend —
   the question is not "suspend or not", it is "does the budget close without suspend."

## Evidence / sources

- Boot time benchmark (logic analyzer) — https://myembeddedstuff.com/arduino-uno-q-boot-time
- "Arduino Uno Q: The 43-second boot time" (Arduino Forum) — https://forum.arduino.cc/t/arduino-uno-q-the-43-second-boot-time-a-technical-breakdown-using-a-logic-analyzer/1425354
- "UNO Q Edge AI is promising, but low-power standby is difficult for always-on sensing applications" (real measured suspend/poweroff current draw) — https://forum.arduino.cc/t/uno-q-edge-ai-is-promising-but-low-power-standby-is-difficult-for-always-on-sensing-applications/1446170
- "Can the STM32U585 MCU keep running uninterrupted while the QRB2210 MPU reboots or enters sleep on Arduino UNO Q?" — https://forum.arduino.cc/t/can-the-stm32u585-mcu-keep-running-uninterrupted-while-the-qrb2210-mpu-reboots-or-enters-sleep-on-arduino-uno-q/1447600
- "Possible to sleep MPU and keep MCU running?" — https://forum.arduino.cc/t/possible-to-sleep-mpu-and-keep-mcu-running/1417642
- Arduino UNO Q Power Specifications (PM4125 PMIC) — https://docs.arduino.cc/tutorials/uno-q/power-specification/
- Wijayakulasooriya et al., "Towards Long Range Detection of Elephants Using Seismic Signals: A Geophone-Sensor Interface for Embedded Systems" (140m natural / 155.6m controlled validated range, 99.5% accuracy; theoretical 16km/32km instrumental limits) — https://ieeexplore.ieee.org/document/10531263/
- CONTEXT.md §3/§4; ADR 0001 (same seismic paper family, frequency band); ADR 0007 (acoustic-specific wake question, resolved by this decision)
