# ADR 0001: USB IMX462 day/night camera (not MIPI, not OV2710/IMX662)

- **Status:** accepted
- **Date:** 2026-07-08

## Context
The node needs day + night vision. The UNO Q's MIPI-CSI needs a carrier board (unavailable), and >70% of elephant raids are nocturnal, requiring active-IR night vision in dark canopy.

## Decision
Use the **Arducam IMX462 day/night USB camera (B0CQ4QDCXN)** — auto IR-cut + built-in 940 nm IR — over USB-UVC. External IR illuminator is **940 nm** to match the filter.

## Alternatives considered
- **MIPI (RPi cam / IMX219/OV5647):** rejected — needs an unavailable carrier.
- **OV2710 board (B0829HZ3Q7):** rejected — much weaker NIR/night sensor (budget fallback only).
- **IMX662 low-light color (B0576):** rejected — no IR-cut/IR LEDs; relies on ambient light, unsuitable for dark-forest active-IR.

## Consequences
+ Correct active-IR day/night in true darkness; best-available NIR at this price/availability; UVC plug-and-play (no carrier).
− ~₹8.7k (premium over OV2710). Camera is a *confirmation* sensor; the geophone remains primary for range.
