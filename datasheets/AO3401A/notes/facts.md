# AO3401A extracted facts — CI board per-tile power-cut P-FET

Part: **AO3401A** (SOT-23), 30 V P-channel trench MOSFET. The CI
board's per-tile high-side power-cut switch (docs/instrumented-ci.md
§3, transform F8): source = `3V3`, drain = `3V3N`, gate = scan-chain
bit `PWR` with a 47 kΩ pull-down.

Source (canonical PDF in `datasheets/AO3401A/`):

- `AO3401A-datasheet-v3.1.pdf` — cited as (AOS DS §x); Alpha & Omega
  Semiconductor AO3401A datasheet, Rev 3.1: December 2023, from
  aosmd.com.

JLCPCB/LCSC inventory (queried 2026-10-16, live): **AOS AO3401A,
C15127, SOT-23, Basic tier**, $0.1030 @5, 231,435 stock.

## Pinout (AOS DS front page, SOT23 drawing)

The drawing labels the terminals but not pin numbers; numbering
follows the JEDEC SOT-23 convention the KiCad `Transistor_FET:AO3401A`
symbol and `Package_TO_SOT_SMD:SOT-23` footprint share:

| Pin | Terminal   |
| --- | ---------- |
| 1   | G (gate)   |
| 2   | S (source) |
| 3   | D (drain)  |

## Electrical quick table (AOS DS, product summary + electrical characteristics)

- VDS = −30 V, ID = −4 A (at VGS = −10 V), VGS max ±12 V.
- RDS(on): ≤ 50 mΩ @ VGS = −10 V; ≤ 60 mΩ @ VGS = −4.5 V;
  **≤ 85 mΩ @ VGS = −2.5 V** (ID = −2.5 A) — the operating point for
  the 3.3 V-driven gate; residual R5 (instrumented-ci.md §9) budgets
  ≤ 3 mV drop at 30 mA tile current.
- VGS(th) = −0.5 … −1.3 V — the 3.3 V gate swing saturates the part
  comfortably, and the 47 kΩ pull-down (POR = on) clears the
  threshold with orders of margin.
- Ciss 645 pF typ, Coss 80 pF typ, Crss 55 pF typ; Qg ≤ 14 nC
  (VGS = −10 V) — gate charging off the 595 output is instant at
  scan-plane speeds.
- Body diode: VSD −0.7 … −1 V @ IS = −1 A; the diode points from
  `3V3N` (anode) to `3V3` (cathode) with S = `3V3` — a cut tile's
  rail cannot back-feed into the always rail through the FET, and a
  dead tile pulling `3V3N` low forward-biases nothing.
