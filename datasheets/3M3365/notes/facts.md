# 3M 3365 — facts

28 AWG stranded round-conductor flat ribbon cable, 0.050" (1.27 mm)
pitch, PVC insulation — the candidate segment cable for the ring
interconnect (DESIGN.md §3: 6-conductor segments; the 6-way variant is
3365/06). Document on disk:

- `3M3365-TS-0080-datasheet-v15.pdf` — 3M TS-0080-15 (2006-12-12),
  the series tech sheet covering all conductor counts. (The §3
  connector style is still open — DESIGN.md §6 — so this is the
  reach-modeling candidate, not a settled BOM part.)

## Construction (TS-0080 §Physical)

- Conductors: 28 AWG, 7 × 36 [7 × ø 0.127 mm] tinned stranded copper,
  89 % conductivity
- Insulation: PVC, gray standard or black; zippable for branching
- Temperature rating: −20 °C to +105 °C; voltage rating 300 V (USA/CA)
- Flammability: VW-1 (USA), FT1 (Canada); UL AWM Style 2651

## Electrical (TS-0080 §Electrical)

Transmission-line figures, per the datasheet's own configurations —
**unbalanced is measured ground-signal-ground**, which is exactly the
§3 segment pinout (every data wire flanked by GND pins):

| Quantity                 | Unbalanced (G-S-G)      | Balanced (pair)        |
| ------------------------ | ----------------------- | ---------------------- |
| Characteristic impedance | 102 Ω                   | 172 Ω                  |
| Capacitance              | 14.47 pF/ft [47.5 pF/m] | 8.14 pF/ft [26.7 pF/m] |
| Inductance               | 0.15 µH/ft [0.49 µH/m]  | 0.24 µH/ft [0.79 µH/m] |
| Propagation delay        | 1.47 ns/ft [4.86 ns/m]  | 1.4 ns/ft [4.59 ns/m]  |
| Velocity of propagation  | 69 %                    | 73 %                   |

- Conductor resistance: 65 Ω/1000 ft [≈ 0.214 Ω/m] (28 AWG class value
  carried in the doc's characteristics table)
- Insulation resistance: > 1×10¹⁰ Ω / 10 ft [3 m]
- Cross-check: √(L/C) = 101.6 Ω ≈ the spec'd 102 Ω, and √(L·C) =
  4.82 ns/m ≈ the spec'd 4.86 ns/m — the table is internally
  consistent, so a two-element (Z0, td) + R model reproduces it.

ngspice reach model built on these numbers:
`circuits/cable-reach/phy-cable-segment.cir` (card T15).
