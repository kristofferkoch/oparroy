# AMS1117 — facts

1 A low-dropout linear regulator family, fixed 3.3 V variant
(**AMS1117-3.3**, SOT-223) — the CI board's 5 V → 3.3 V rail regulator
(DESIGN.md §6 "Board power and host link", `design/ci_power.py`).
Documents on disk:

- `AMS1117-datasheet-C6186.pdf` — Advanced Monolithic Systems AMS1117
  series datasheet, 8 pp., no revision marking on the document; fetched
  from the LCSC **C6186** product page (the inventory-relevant vendor,
  §6 inventory-driven selection). Sections below cite it as (DS).

## Pinning (DS, pin connections)

SOT-223, top view: **pin 1 = GND/ADJ, pin 2 = VOUT, pin 3 = VIN**; the
tab is VOUT (matches KiCad's
`Package_TO_SOT_SMD:SOT-223-3_TabPin2`). Fixed 3.3 V variant has no
ADJ network — pin 1 is plain ground.

## Electrical quick table

- Output voltage (DS, Electrical Characteristics): 3.3 V nominal;
  **3.251–3.349 V** at 25 °C, **3.201–3.399 V** over the full operating
  range (±3 %), measured at VIN = 4.8 V.
- Dropout (DS, Electrical Characteristics + Note 4): **1.1 V typ /
  1.3 V max** at IOUT = 0.8 A; decreases at lower load currents
  ("operates down to 1 V input-to-output differential"). Specified up
  to 0.8 A; higher currents drop out earlier. Consequence for a 3.3 V
  rail: VIN ≥ ~4.6 V worst case at full load — USB-C 5 V (4.75–5.25 V
  at the device) covers it with margin.
- Load regulation (AMS1117-3.3, VIN = 4.75 V, 0–0.8 A): 3/7 mV typ,
  **15/25 mV max**. Line regulation: 0.5/1 mV typ, 10 mV max
  (1.5 V ≤ VIN − VOUT ≤ 12 V).
- Quiescent current: **5 mA typ, 11 mA max** — flows to GND regardless
  of load; counts against the board's always-on budget.
- Current limit: 1.1 A min / 1.5 A typ at VIN − VOUT = 1.5 V.
- Input ceiling: abs max **15 V**; guaranteed operating differential
  1.5 V ≤ VIN − VOUT ≤ 12 V.
- Minimum load current 5 mA typ / 10 mA max (DS Note 5) applies to the
  *adjustable* variant's feedback divider; the fixed variants carry the
  divider internally, so no external minimum load is needed.
- Thermal (DS, Absolute Maximum / Application Hints): θJC = 15 °C/W;
  θJA(SOT-223) = 90 °C/W nominal, as low as 46–55 °C/W with a generous
  copper pour (Table 1: 55 °C/W at 2500 mm² of board copper).
  Guaranteed specs hold up to **1.2 W** dissipation in SOT-223
  (DS Note 2); junction must stay ≤ 125 °C. Thermal shutdown at 165 °C.

## Capacitor / stability requirements (DS, Application Hints §Stability)

- The output capacitor is **part of the frequency compensation**:
  "**22 µF solid tantalum** on the output will ensure stability for all
  operating conditions." No ESR window is specified — the requirement
  is stated as tantalum chemistry, full stop.
- Input side: the application circuits show **10 µF** at VIN.
- Ripple-rejection numbers are all measured with COUT = 22 µF tantalum.
- See `quirks.md` for the ceramic-vs-tantalum mismatch the CI board
  capture accepts.
