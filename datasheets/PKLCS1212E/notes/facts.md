# PKLCS1212E extracted facts — CI board output-tile piezo buzzer

Part: **PKLCS1212E4001-R1** — Murata 12×12 mm SMD piezoelectric
sounder (passive, externally driven). The CI board output tiles'
buzzer (docs/instrumented-ci.md §6): node PC4/TIM1_CH4 → 470 Ω →
piezo → GND.

Source (canonical PDF in `datasheets/PKLCS1212E/`):

- `PKLCS1212E4001-R1-spec-JGB40-1584B.pdf` — cited as (Murata
  JGB40-1584B §x); Murata product specification for
  PKLCS1212E4001-R1, Document No. JGB40-1584B, issue date May 21,
  2021, the document LCSC links for C113159.

JLCPCB/LCSC inventory (queried 2026-10-16, live): **Murata
PKLCS1212E4001-R1, C113159, SMD 12×12 mm, Extended tier**,
$0.8028 @1, 7,671 stock. Every buzzer on JLCPCB's parts list is
Extended — the tier fee is unavoidable for this BOM line.

## Facts (Murata JGB40-1584B)

- **Passive (externally driven) piezoelectric sounder** — the node
  firmware supplies the drive waveform (4 kHz square wave is the
  spec's own measuring condition); no internal oscillator.
- **Sound pressure level ≥ 75 dB min** measured at **±1.5 Vo-p,
  4 kHz square wave**, 10 cm, on a 0.1 m square PCB (§5-1, §6) — the
  3.3 V GPIO drive (±1.65 Vo-p) already exceeds the measuring
  condition, so the rated SPL applies at the board's drive level.
- Maximum input voltage ±12.5 Vo-p (§4-1) — the 3.3 V drive is far
  inside.
- Operating temperature −20 … +70 °C (§4-2).
- Dimensions 12.0 × 12.0 × 3.0 mm max, sound-emitting hole on top,
  two SMD terminals (§9 dimensions drawing); the recommended land
  pattern is the one the KiCad footprint
  `Buzzer_Beeper:Buzzer_Murata_PKLCS1212E` carries.
- The package top marking is vendor code + EIAJ month/year code
  (§9) — not an electrical polarity mark. A piezo sounder is
  electrically non-polar; the `Device:Buzzer` symbol's +/− pins are
  phase convention only.
