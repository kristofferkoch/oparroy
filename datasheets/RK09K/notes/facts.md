# RK09K extracted facts — CI board demo potentiometer

Part: **RK09K1130A6S** — ALPS Alpine 9 mm insulated-shaft snap-in
rotary potentiometer, vertical mount, THT. The CI board input tiles'
demo knob (docs/instrumented-ci.md §6, transform H1): 10 kΩ across
`3V3N`/GND, wiper to the substitution mux.

Source (canonical PDF in `datasheets/RK09K/`):

- `RK09K1130A6S-datasheet-2018-03-30.pdf` — cited as (ALPS RK09K);
  ALPS Alpine RK09K/RK09D series basic-information sheet for
  RK09K1130A6S, dated 2018-03-30, the document LCSC links for
  C209770. ALPS's own caveat on the last page: this is an outline
  spec — obtain the formal specification for supply.

JLCPCB/LCSC inventory (queried 2026-10-16, live): **ALPSALPINE
RK09K1130A6S, C209770, THT**, $0.5967 @1, 2,143 stock. JLCPCB lists
it as manual-weld (no SMT assembly), so the CI board hand-solders it
post-PCBA like the back-side connectors — parts-DB tier NONE.

## Identity (ALPS RK09K, basic-information table)

- Total resistance **10 kΩ ±20 %**, taper **1B (linear)**, rated
  power 0.05 W, max operating voltage 50 V AC / 20 V DC.
- Single unit, vertical type, without collar, flat shaft 15 mm,
  without center detent.
- Total rotational angle 280° ±5°, rotational torque 1–8 mN·m,
  operating life 5,000 cycles — a demo knob, not a lab instrument.
- Operating temperature −10 … +70 °C.
- Hand soldering: 350 °C max tip, 3 s max, once (ALPS RK09K,
  soldering conditions).

## Pinout (ALPS RK09K, terminal layout / circuit diagram)

Three terminals in a row, viewed from the mounting side:

| Pin | Terminal              |
| --- | --------------------- |
| 1   | resistive element end |
| 2   | **wiper**             |
| 3   | resistive element end |

Matches the KiCad footprint
`Potentiometer_THT:Potentiometer_Alps_RK09K_Single_Vertical` (pads
1/2/3 in a row, 2 = middle = wiper, plus two `MP` snap-in tabs) and
`Device:R_Potentiometer` (pin 2 = wiper per its Sim.Pins).
