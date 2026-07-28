# ADR 0002: Keep LoRaWAN star for node network (not Meshtastic mesh)

- **Status:** accepted
- **Date:** 2026-07-12

## Context
Four LoRa devices are on hand ahead of the main camera/geophone shipment: a SenseCAP SX1302
gateway (ships configured EU868), a Wio-SX1262 + XIAO ESP32S3 kit (Meshtastic-ready out of the
box), a Wio Tracker L1 Lite (Meshtastic-ready, nRF52840, GPS), and a Grove LoRa-E5
(STM32WLE5JC — LoRaWAN-native; community Meshtastic support exists but has had unresolved
filesystem issues). This raised the question of whether the node network should move from
LoRaWAN to a Meshtastic mesh for better coverage, decentralization, internet-independence, and
node-to-node coordination.

The frozen architecture already specifies: reflex MCU is **STM32U585** chosen specifically for
µA always-on operation (§4); coordination model is **"LoRa star + neighbour pre-arm"** (§4);
gateway is **SenseCAP SX1302, region IN865, → ChirpStack** (§5); nodes are spaced **120–150 m**
with a **gateway every 8–15 km** (§6); **"all control is local; cloud is monitoring/analytics
only"** (§4); and **"LoRa IN865 only (868 MHz is illegal in India)"** (§8).

Meshtastic firmware targets ESP32/nRF52-class MCUs, not STM32. Both Meshtastic-ready devices on
hand are ESP32S3/nRF52840-based, confirming that alignment.

**Addendum, same day, after confirming UNO Q's actual architecture and Meshtastic's Linux-native
option:** Arduino's own UNO Q datasheet confirms it *is* the QRB2210 + STM32U585 combination
CONTEXT.md describes — one board, two processors, not two separate boards. This raised a natural
follow-up: could `meshtasticd` (Meshtastic's Linux daemon) run directly on the QRB2210 side,
using a small SPI radio like the Wio-SX1262, instead of needing a whole separate Meshtastic MCU?
Checked and rejected, for a more fundamental reason than the MCU mismatch above: `meshtasticd`
requires a SPI-radio HAT (SX1302/SX1303-based hats — the SenseCAP gateway's own chip family —
are explicitly *not* supported), so the SenseCAP gateway can't double as a mesh hub either way.
But the deeper issue is independent of which chip hosts it: real mesh participation requires a
node to listen (and relay) *continuously*, and CONTEXT.md's whole reflex/cognition split exists
specifically so the power-hungry QRB2210 stays dormant except during an actual detection event
(§4: "Cognition (QRB2210, event-only)"). A mesh node that's only listening when its own sensors
already triggered would relay almost nothing — defeating mesh's purpose — so moving Meshtastic to
the QRB2210 doesn't avoid the power conflict, it just relocates it. This confirms the decision
below on stronger grounds than the initial MCU-target mismatch alone.

## Decision
Keep the frozen LoRaWAN path unchanged: STM32U585 → SenseCAP SX1302 gateway (IN865) →
ChirpStack. Do not adopt Meshtastic for the detection/deterrence node network. Neighbour
pre-arm continues to ride the existing gateway/ChirpStack/backend round-trip — acceptable
because it is a coordination *optimization*, not a safety dependency, per the autonomy
principle already in §4.

Repurpose the Meshtastic-ready hardware already owned (Wio Tracker L1 Lite, Wio-SX1262 + XIAO
ESP32S3 kit) for the install team's own field communications and for site/range-survey testing
during deployment — useful, zero architectural risk, no interaction with the frozen design.

## Alternatives considered
- **Full Meshtastic mesh for node coordination:** rejected. Requires either swapping the reflex
  MCU off STM32U585 or adding a second radio/co-processor per node — both undermine the
  already-justified µA power budget and add BOM/integration risk this close to hardware
  arrival and the contest deadline. Also solves a coverage problem this deployment doesn't
  have: node spacing (120–150 m) is tiny relative to gateway range (8–15 km), so single-hop
  LoRaWAN already covers a full sector.
- **Custom lightweight peer-to-peer "pre-arm" layer on the STM32U585's existing radio**
  (Meshtastic's idea, not its firmware): rejected for now. Real additional RF/MAC engineering
  (interleaving promiscuous listen with LoRaWAN class A/C receive windows) for a signal that's
  explicitly not safety-critical — not worth the risk under deadline pressure when the gateway
  round-trip is already adequate for pre-arm's latency tolerance.
- **Leave the owned Meshtastic hardware unused:** rejected — a real, low-risk use exists
  (field-team comms, site survey) at no cost to the frozen architecture.

## Consequences
+ No change to reflex MCU, power budget, BOM, or the Day 4 `web/ingest`/ChirpStack work already
  in progress.
+ Coordination latency through the gateway/cloud round-trip is acceptable — deterrence
  decisions never depend on it, only local sensor fusion does.
+ The already-purchased Meshtastic hardware gets genuine use instead of sitting idle.
− Follow-up required regardless of this decision: the SenseCAP gateway ships on a EU868
  frequency plan. Must be explicitly set to IN865 (865.0625 / 865.4025 / 865.985 MHz) in both
  its local console and ChirpStack's region setting before any real transmission — §8 already
  states 868 MHz is illegal to operate in India. Verify before hardware arrives, not after.
− If real-site terrain (dense canopy, hills) degrades effective gateway range well below the
  nominal 8–15 km, revisit this ADR — an additional gateway is the first fix to try (already
  the plan), mesh relay only becomes worth reconsidering if that proves insufficient.
