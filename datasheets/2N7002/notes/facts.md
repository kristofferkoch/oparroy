# 2N7002 extracted facts — CI board button-override N-FET

Part: **2N7002** (SOT-23), 60 V N-channel MOSFET. The CI board's
button override: one FET paralleled across each input tile's tactile
button, gate on a scan-chain bit with a 47 kΩ pull-down
(docs/instrumented-ci.md §6, transforms H2/H3).

Source (canonical PDF in `datasheets/2N7002/`):

- `2N7002-JSCJ-datasheet-2016-09.pdf` — cited as (JSCJ DS §x); JSCJ
  (Jiangsu Changjiang Electronics) 2N7002 datasheet, September 2016,
  the document LCSC links for C8545.

JLCPCB/LCSC inventory (queried 2026-10-16, live): **JSCJ 2N7002,
C8545, SOT-23, Basic tier**, $0.0176 @50, 2,030,150 stock.

## Pinout (JSCJ DS front page)

The datasheet prints the pinout in the header:

| Pin | Terminal |
| --- | -------- |
| 1   | Gate     |
| 2   | Source   |
| 3   | Drain    |

Matches the KiCad `Transistor_FET:2N7002` symbol (1 = G, 2 = S,
3 = D) pad for pad.

## Electrical quick table (JSCJ DS, maximum ratings + characteristics)

- V(BR)DSS = 60 V, ID = 115 mA continuous, VGS max ±20 V,
  PD = 0.225 W.
- RDS(on) ≤ 5 Ω @ VGS = 10 V (ID = 500 mA), ≤ 7 Ω @ VGS = 5 V — the
  button line's 10 kΩ pull-up against single-digit ohms is a
  millivolt-level low (residual R8, instrumented-ci.md §9).
- VGS(th) = 1.0 … 2.5 V (ID = 250 µA) — worst case leaves ≥ 0.8 V of
  overdrive at the 3.3 V gate drive; the FET pulls the button line
  low hard enough for the node's VIL.
- Gate leakage IGSS ≤ ±80 nA, IDSS ≤ 80 nA @ VDS = 60 V — the
  released-state pull-up droop is negligible.
- Capacitances (VDS = 25 V, VGS = 0, 1 MHz, max): Ciss ≤ 50 pF,
  Coss ≤ 25 pF, Crss ≤ 5 pF. The released FET loads the button line
  with its drain capacitance — Coss-class, ≤ 25 pF (the §9 R8
  register's "~5 pF" is the Crss figure; the drain-node loading is
  the Coss one, and either is noise on a slow GPIO behind a 10 kΩ
  pull-up).
