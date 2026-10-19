# INA241 extracted facts — CI tile power-measurement current-sense amp

Part: **TI INA241x** (INA241A / INA241B), −5 V to 110 V bidirectional,
zero-drift current-sense amplifier with enhanced PWM rejection
(DS §3). Target orderable: **INA241A5IDDFR** — SOT-23-8 (DDF),
−40…+125 °C, tape-and-reel, marking code 2PL3 (DS §11 packaging
table; LCSC C7425524). Role: high-side shunt amp in the CI board
tile power-measurement chain — 82 mΩ shunt on the 3.3 V tile rail
downstream of the power-cut FET, bidirectional with REF biased
mid-rail (REF1 → VS, REF2 → GND) so the cut-state clamp back-feed
reads as a negative current, output feeds an external SPI ADC
(docs/instrumented-ci.md §12).

Source (canonical PDF in `datasheets/INA241/`):

- `INA241-datasheet-SBOSA30D.pdf` — "INA241x −5V to 110V,
  Bidirectional, Ultra-Precise Current Sense Amplifier With Enhanced
  PWM Rejection", SBOSA30D, March 2022, revised December 2024
  (revision D), from ti.com. Cited as (DS §x.y).

## Gain variants and A/B grades (DS §1, §4 Table 4-1, §6.5)

| Device       | Gain    |
| ------------ | ------- |
| INA241A1, B1 | 10 V/V  |
| INA241A2, B2 | 20 V/V  |
| INA241A3, B3 | 50 V/V  |
| INA241A4, B4 | 100 V/V |
| INA241A5, B5 | 200 V/V |

- **A5 = 200 V/V** — the family tops out at 200 V/V; no 500 V/V
  member exists (DS §4 Table 4-1). With the chain's 82 mΩ shunt, 50 mA
  full-scale gives VSENSE = 4.1 mV → VOUT = 0.82 V at gain 200.
- A vs B is an **accuracy grade, not a pinout variant** — one pinout
  covers the whole family (DS §5). A grade: VOS ±10 µV max
  (per-gain, see below), gain error ±0.01% max, drift ±1 ppm/°C max.
  B grade: VOS ±150 µV max, gain error ±0.1% max, drift ±5 ppm/°C
  max (DS §6.5).
- Packages: SOT-23-8 (DDF), VSSOP-8 (DGK), SOIC-8 (D) — all share
  the same pinout (DS §5, §3 package information).

## Pinout — DDF (SOT-23-8), all variants (DS §5 Figure 5-1, Table 5-1)

| Pin | Name | Type   | Function                                                 |
| --- | ---- | ------ | -------------------------------------------------------- |
| 1   | IN−  | Input  | Sense-amp negative input (high-side: load side of shunt) |
| 2   | GND  | Ground | Ground                                                   |
| 3   | REF2 | Input  | Reference 2, 0 V to VS (see REF section below)           |
| 4   | NC   | Ground | Reserved — connect to ground                             |
| 5   | OUT  | Output | Output voltage                                           |
| 6   | VS   | Power  | Supply, 2.7 V to 20 V                                    |
| 7   | REF1 | Input  | Reference 1, 0 V to VS                                   |
| 8   | IN+  | Input  | Sense-amp positive input (high-side: bus side of shunt)  |

Same numbering for D (SOIC) and DGK (VSSOP) (DS §5 Figure 5-2,
Table 5-1). Cross-check target: KiCad symbol
`Amplifier_Current:INA241A5xDDF`.

## Electrical quick table (DS §6.5, conditions: TA = 25 °C, VS = 5 V unless noted)

| Parameter                    | Value                                                 | Notes                                                                          |
| ---------------------------- | ----------------------------------------------------- | ------------------------------------------------------------------------------ |
| Supply range (recommended)   | 2.7 V … 20 V                                          | §6.3; 3.3 V rail fits                                                          |
| Quiescent current IQ         | 2.5 mA typ, 3 mA max; 3.2 mA max −40…+125 °C          | VSENSE = 0 mV                                                                  |
| Common-mode input range      | −5 V … 110 V operational; −20 V … 120 V survival      | independent of VS (§7.3.1)                                                     |
| Input offset VOS (A grade)   | A1 ±20 µV, A2 ±15 µV, A3/A4 ±10 µV, **A5 ±8 µV** max  | §6.5 per-gain rows                                                             |
| Input offset drift (A grade) | ±100 nV/°C max (A3/A4/A5)                             | over −40…+125 °C                                                               |
| Input bias current IB        | 25 / 35 / 45 µA min/typ/max per pin                   | constant over CM range (§7.3.1.3)                                              |
| Gain error (A grade)         | ±0.01% max (A1–A3); ±0.015% max (A4, A5)              | (GND+50 mV) < VOUT < (VS−200 mV)                                               |
| Gain error drift (A grade)   | ±1 ppm/°C max (A1–A3); ±2 ppm/°C max (A4, A5)         |                                                                                |
| CMRR (A grade)               | 150 dB min, 166 dB typ DC; 105 dB typ at 50 kHz       | §1 also cites 104 dB at 100 kHz, 89 dB at 1 MHz AC-CMRR                        |
| PSRR (A3/A4/A5)              | ±0.5 µV/V max                                         | VS = 2.7…20 V                                                                  |
| Small-signal bandwidth       | **1.1 MHz typ, −3 dB, "All Gains"**                   | typ-only — no min column (§6.5 BW row; §7.3.1.2; Figure 6-9 gain vs frequency) |
| Slew rate                    | 8 V/µs typ (rising)                                   | typ-only                                                                       |
| Settling time                | 1.5 µs to 0.5%, 1 µs to 1%, 0.5 µs to 5%              | typ; VOUT step 0.5→4.5 V                                                       |
| Swing to VS rail             | VS−0.07 V typ, VS−0.2 V max                           | RL = 10 kΩ to GND                                                              |
| Swing to GND                 | **8 mV typ, 20 mV max**                               | RL = 10 kΩ, VSENSE = 0, REF1 = REF2 = 0 V                                      |
| Max capacitive load          | 1 nF, no isolation resistor, no sustained oscillation |                                                                                |
| Input voltage noise (A5)     | 28 nV/√Hz typ                                         | input-referred                                                                 |

## REF pins and output configuration (DS §7.4)

- Transfer function: VOUT = G × (VIN+ − VIN−) + (VREF1 + VREF2) / 2
  (DS §7.4.1 Equation 1). No operational difference between REF1
  and REF2.
- Reference input range: 0 V to VS (DS §6.5).
- **Unidirectional, ground-referenced:** REF1 and REF2 tied together
  to GND; output sits at the swing-to-GND floor (8 mV typ / 20 mV max)
  at zero current and rises toward VS with positive VSENSE (DS
  §7.4.2.1). Input polarity must be positive to lift the output off
  ground (DS §7.4.2) — rejected for the tile chain: it cannot read
  the cut-state reverse flow.
- **Mid-supply bidirectional (the tile chain's config):** REF1 to VS,
  REF2 to GND → output at VS/2 at zero current, ratiometric to the
  supply (DS §7.4.3.2);
  reference divider accuracy ±0.01% max for A3/A4/A5 (DS §6.5).
- REF pins are designed to connect **directly to supply, ground, or
  a low-impedance reference**. A resistor-divider reference must be
  read differentially, or buffered with an external op amp for
  single-ended use — unbuffered single-ended use degrades specs via
  internal impedance shifts (DS §7.4.3.4).
- Output linear range is bounded by the swing-to-rail and
  swing-to-GND specs; RSENSE, gain, and REF must be chosen to keep
  the output inside it (DS §7.4.3, §8.1.1 Equations 3–4).

## Absolute maximums relevant to a 3.3 V design (DS §6.1)

- VS: 22 V max — the 3.3 V always-on domain is far inside.
- IN+/IN−: common-mode −20 V…+120 V, differential ±30 V — shunt
  on a 3.3 V rail has huge margin; transients, not DC, are the risk.
- REF1/REF2/NC: GND−0.3 V … VS+0.3 V.
- OUT: GND−0.3 V … VS+0.3 V — clamp the ADC-side interface if the
  ADC has a lower full-scale or its own supply.
- ESD: ±2 kV HBM, ±1 kV CDM (DS §6.2).
- Thermal (DDF): RθJA 129.7 °C/W (DS §6.4) — negligible at
  IQ = 2.5 mA × 3.3 V ≈ 8 mW.

## Layout and decoupling (DS §8.3.1, §8.4)

- 0.1 µF bypass capacitor as close as possible to the VS and GND
  pins; add more decoupling for noisy or high-impedance supplies.
- Kelvin (4-wire) connection from the input pins to the sense
  resistor — with a milliohm shunt, any shared high-current trace
  impedance adds directly to the measured VSENSE.
- DS §8.4.2 Figure 8-3 shows the DDF reference layout: shunt
  Kelvin-tapped into pins 1/8, bypass cap across pins 2/6 with vias
  to the ground plane and supply.

## Software cross-check

N/A — the INA241x is a pure analog-output amplifier: no registers,
no digital interface, no programming model. Checked the Linux
hwmon/IIO driver roster (ina209, ina2xx, ina238 cover TI's *digital*
I2C/SMBus current monitors only) and TI's product collateral (no SDK,
no driver listed); there is nothing to cross-check against.

See also [quirks.md](quirks.md).
