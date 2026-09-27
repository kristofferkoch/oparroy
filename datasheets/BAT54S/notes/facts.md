# BAT54S — facts

Dual series Schottky diode pair in SOT-23, used by the watchdog charge
pump (DESIGN.md §4, `circuits/watchdog-chargepump/`,
`design/watchdog_chargepump.py`). Documents on disk:

- `BAT54SER-datasheet-v5.pdf` — Nexperia BAT54 series product data
  sheet, Rev. 5 (2012-10-05); covers BAT54 / BAT54A / BAT54C / BAT54S.
  Canonical pinning reference.
- `TWGMC-BAT54S-datasheet-C727126.pdf` — TWGMC BAT54S, LCSC **C727126**
  (the inventory-relevant vendor, §6 inventory-driven selection). Thin
  doc: ratings + marking (KL4) + package outline, pinning is graphic
  only — use the Nexperia pinning table.

## Pinning (BAT54SER Rev.5 §2, Table 2)

BAT54S is the **series pair**: pin 3 is the shared midpoint.

| Pin | Function                                              | KiCad `Diode:BAT54S` pin name |
| --- | ----------------------------------------------------- | ----------------------------- |
| 1   | anode (diode 1)                                       | A                             |
| 2   | cathode (diode 2)                                     | K                             |
| 3   | cathode (diode 1) + anode (diode 2) — series midpoint | COM                           |

Charge-pump mapping (verified 2026-09-27 after the DSL capture swapped
pins 2/3): **pin 1 = GND** (pump-input diode anode), **pin 3 = net `x`**
(series midpoint), **pin 2 = net `sel`** (pump output cathode). Sibling
variants for reference: BAT54 = single (1 A, 2 n.c., 3 K); BAT54A =
common-anode pair (3 = common anode); BAT54C = common-cathode pair
(3 = common cathode).

## Ratings quick table (BAT54SER Rev.5 §1.4/§5)

- VRRM / VRWM / VR: **30 V** max
- IF continuous: **200 mA**; PD 200 mW (TWGMC doc agrees)
- VF: 0.24 V typ @ 0.1 mA … 0.8 V max @ 100 mA (BAT54SER Rev.5 §7,
  pulse test tp ≤ 300 µs, δ ≤ 0.02)
- IR: 2 µA max @ VR = 25 V
- TSTG −55…+150 °C; marking KL4 (BAT54S)
