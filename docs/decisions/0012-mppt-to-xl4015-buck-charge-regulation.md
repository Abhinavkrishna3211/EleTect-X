# ADR 0012: Drop the smart MPPT solar controller for a manually-set XL4015 buck

- **Status:** accepted
- **Date:** 2026-08-20

## Context

The power system (§6 of `hardware/bom/procurement-status.md`) was sized 12-13 Aug against a real daily
energy budget (ADR 0008's measured 0.42-0.45W MPU-suspend draw, ~13Wh/day baseline, plus event-triggered
deterrence load) and real Kerala monsoon-season solar irradiance. The original plan called for a
purpose-built LiFePO4-aware MPPT solar charge controller — the amiciSmart 10A (138×79×38mm, ₹1,949) was the
lead candidate.

Real verification on 13 Aug disqualified every "smart" charge controller checked, not just the amiciSmart
unit:

- **amiciSmart 10A:** self-contradicting listing — its own "Product description" states lead-acid only,
  contradicting its "About this item" claim of LiFePO4 support. Real customer reviews on 4S packs
  specifically report it "unavailable to charge lifepo4 battery pack of 4S" (verified purchase). A
  separately reported firmware bug — it won't auto-resume charging after a low-voltage shutdown — is
  disqualifying on its own for unattended field hardware.
- **Sparkel SPSCC-1012LiMPPT (₹2,450):** genuinely well-engineered (IP67, real redundant protection), but
  ships factory-default to Gel lead-acid, not Lithium. The "S-Unit" remote needed to reconfigure it isn't
  sold anywhere on Sparkel's own site — no path to actually set it up for the LiFePO4 pack in hand.
  Victron's Bluetooth-programmable units passed every check but cost ₹6,300+, well outside budget.

With the Aug 20 field-trial deadline fixed and no verified-working MPPT unit reachable in time, the
question became: track maximum power point at all, or regulate charge with a part that is fully
inspectable and known to work.

## Decision

Drop the MPPT controller category entirely. Use the **XL4015 CC/CV buck module already in hand (bought 28
Jul)**, manually set to:

- **14.2V constant-voltage output** — conservative against the 14.6V absorption max, for margin against
  trimmer-pot drift and to reduce full-charge calendar stress on the pack.
- **~1-2A current limit**, dialed in and **verified with a multimeter before the module is ever connected to
  the battery pack** (per the Day 3 assembly step in `docs/BUILD_BLUEPRINT_AUG20.md`) — the module has no
  firmware or auto-negotiation to trust, so the only correctness check is a bench measurement ahead of the
  live connection.

This also drops ~₹1,900-2,450 from the original plan, and one spare XL4015 (~₹259) is being bought as
insurance/replacement stock.

## Alternatives considered

- **amiciSmart 10A MPPT (138×79×38mm):** rejected — self-contradicting LiFePO4 support claim, real-world 4S
  charging failures reported by verified purchasers, and a firmware bug that won't auto-resume after a
  low-voltage shutdown, unacceptable for hardware nobody will be standing next to.
- **Sparkel SPSCC-1012LiMPPT:** rejected — ships defaulted to the wrong battery chemistry with no available
  path to reconfigure it for LiFePO4.
- **Victron Bluetooth-programmable MPPT:** rejected on cost (₹6,300+) against a 10-day contest-trial budget,
  not on merit — the one category that passed every verification check.

## Consequences

+ Fully inspectable, no firmware to trust — every setting is a physical trimmer-pot position confirmable
  with a multimeter, matching the project's general preference for parts that can be verified rather than
  taken on faith (CONTEXT.md §7).
+ Drops ~₹1,900-2,450 from the power-block budget.
+ Removes one board from the enclosure footprint reasoning — the XL4015's real dimensions replace the
  amiciSmart's 138×79×38mm envelope that had been driving width/depth decisions in
  `hardware/cad/enclosure-design-concept.md` and ADR 0011 (both corrected as part of this change).
- Loses maximum-power-point tracking. Under partial shade or non-ideal panel angle, a fixed CV/CC buck
  extracts less usable energy from the panel than a real MPPT controller would — accepted because the power
  budget was sized with margin (3-day no-sun autonomy, 85% DoD) and because the Aug 20 trial only needs to
  clear a 10-day window, not run indefinitely unattended in worst-case shade.
- No staged bulk/absorption/float charging — the XL4015 holds one fixed CV/CC setpoint for the whole charge
  cycle, which is less gentle on the pack over many cycles than a real 3-stage charge profile.
- No independent hardware overvoltage backstop from the charge side. The **battery's own BMS becomes the
  load-bearing safety component** for overvoltage/overcurrent protection — a real single-point-of-failure
  shift the earlier MPPT-based plan didn't have, accepted because every "smart" controller checked was
  either unverifiable or non-functional for this chemistry, making a known-inspectable manual part safer in
  practice than an unverified smart one.
- The current-limit-before-battery-connection verification step (`docs/BUILD_BLUEPRINT_AUG20.md`, Day 3) is
  now a required manual assembly step, not something the module enforces on its own — a process risk that
  didn't exist with a purpose-built controller, mitigated only by discipline at assembly time.
