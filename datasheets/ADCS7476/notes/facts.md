# ADCS7476 extracted facts — CI board tile power-measurement ADC

Part: **TI ADCS7476**, 12-bit 1 MSPS SAR ADC in 6-pin SOT-23 (DBV), SPI
serial output, supply-as-reference. Target orderable:
**ADCS7476AIMFX/NOPB** (SOT-23 DBV, 3000-unit reel, −40…+125 °C, part
marking X01A — DS §12 package option addendum; LCSC C91530). Role:
external ADC for the tile power-measurement chain on the CI board,
reading a current-sense amp's 0…~0.8 V output; clocked by an RP2040
PIO state machine with DMA burst capture, single 3.3 V supply.

Family split (DS §3): ADCS7476 = 12-bit, ADCS7477 = 10-bit,
ADCS7478 = 8-bit; identical die architecture, packages, and 16-SCLK
frame — the lower-resolution parts pad the frame with trailing zeros
(7477: 2, 7478: 4). All three are drop-in replacements for Analog
Devices AD7476/AD7477/AD7478 (DS §3). Only one grade/package exists:
SOT-23-6 (DBV), 1.60 mm × 2.90 mm body (DS §3 device information).

Source (canonical PDF in `datasheets/ADCS7476/`):

- `ADCS7476-SNAS192G-datasheet-vG.pdf` — "ADCS747x 1-MSPS, 12-Bit,
  10-Bit, and 8-Bit A/D Converters", SNAS192G, April 2003, revised May
  2016, from ti.com. Cited as (DS §x.y).

## Pinout — DBV package, 6-pin SOT-23, top view (DS §5)

| Pin | Name  | Type | Function                                                                                            |
| --- | ----- | ---- | --------------------------------------------------------------------------------------------------- |
| 1   | VDD   | P    | Supply 2.7–5.25 V, also the ADC reference. Bypass to GND with 0.1 µF + 1 µF within 1 cm of the pin. |
| 2   | GND   | G    | Ground return.                                                                                      |
| 3   | VIN   | I    | Analog input, 0 V to VDD.                                                                           |
| 4   | SCLK  | I    | Serial clock, 10 kHz to 20 MHz; controls conversion and readout.                                    |
| 5   | SDATA | O    | Serial data out; tri-state when idle.                                                               |
| 6   | CS    | I    | Chip select, active low; falling edge starts a conversion.                                          |

## Pin compatibility verdict

- **vs ADI AD7476 (SOT-23): identical.** ADI AD7476/AD7477/AD7478
  datasheet Rev D, pin configuration: 1 VDD, 2 GND, 3 VIN, 4 SCLK,
  5 SDATA, 6 CS — same numbers, same names. Matches the drop-in
  replacement claim (DS §3).
- **vs TI ADS7886 (SOT-23 DBV, SLAS492B §6): identical.** ADS7886:
  1 VDD, 2 GND, 3 VIN, 4 SCLK, 5 SDO, 6 CS. Only the pin-5 name
  differs (SDATA vs SDO). For the schematic: **ADCS7476 pin N =
  function X matches ADS7886xxDBV pin N for all N = 1…6** — the KiCad
  `Analog_ADC:ADS7886xxDBV` symbol is pin-correct; connect symbol pin
  5 (SDO) to the MCU's SPI MISO.
- Not spec-identical: ADS7886 supply range is 2.35–5.25 V (SLAS492B
  §7.2) vs 2.7–5.25 V here; irrelevant at 3.3 V. Frame format is the
  same (4 leading zeros + 12 bits MSB-first, tri-state after the 16th
  falling edge — SLAS492B §8.4.1).

## Electrical quick table (DS §6.5, ADCS7476 column; conditions fSCLK = 20 MHz, fSAMPLE = 1 MSPS unless noted)

| Parameter            | Value                                                                             | Source              |
| -------------------- | --------------------------------------------------------------------------------- | ------------------- |
| Supply VDD           | 2.7–5.25 V                                                                        | DS §6.3             |
| Reference            | VDD is the reference; input range 0…VDD — **at 3.3 V: 0…3.3 V, 1 LSB = 0.805 mV** | DS §3, §6.5, §8.2.2 |
| Resolution           | 12 bits, no missing codes (2.7–3.6 V, −40…+125 °C)                                | DS §6.5             |
| Sample rate          | 1 MSPS max, achieved at fSCLK = 20 MHz                                            | DS §6.5 fRATE       |
| SCLK                 | 10 kHz min, 20 MHz max, duty 40–60 %                                              | DS §5 pin 4, §6.5   |
| INL                  | ±0.4 LSB typ @25 °C; ±1 LSB max (−40…+85 °C); −1.1…+1 LSB @125 °C                 | DS §6.5             |
| DNL                  | +0.5/−0.3 LSB typ @25 °C; −0.9…+1 LSB max (−40…+85 °C)                            | DS §6.5             |
| Offset / gain error  | ±0.1 / ±0.2 LSB typ; ±1.2 LSB max each                                            | DS §6.5             |
| SNR                  | 72.5 dB typ, ≥70.8 dB min (fIN = 100 kHz)                                         | DS §6.5             |
| SINAD / THD / SFDR   | 72 dB typ (≥70 min) / −80 dB / 82 dB (fIN = 100 kHz)                              | DS §6.5             |
| Full-power bandwidth | 8 MHz @3 V, 11 MHz @5 V                                                           | DS §6.5             |
| IDD, 1 MSPS, 3 V     | **0.6 mA typ, 1.6 mA max** (2.7–3.6 V); static: 1 mA max                          | DS §6.5             |
| IDD, 1 MSPS, 5 V     | 2 mA typ, 3.5 mA max                                                              | DS §6.5             |
| Power, 1 MSPS        | 2 mW typ / 4.8 mW max @3 V; 10 mW typ / 17.5 mW max @5 V                          | DS §6.5             |
| Shutdown             | 0.5 µA typ (SCLK off), 60 µA typ (SCLK on), @5 V; 1.5 µW @3 V SCLK off            | DS §6.5             |
| Analog input         | 0…VDD range, ±1 µA leakage, 30 pF input capacitance                               | DS §6.5             |
| Output coding        | Straight (natural) binary                                                         | DS §6.5             |
| Logic levels         | VIH ≥ 2.4 V; VIL ≤ 0.4 V @3 V; VOH ≥ VDD−0.2; VOL ≤ 0.4 V                         | DS §6.5             |

## Serial interface — the section firmware is written against

(DS §7.3 Feature Description, §6.8 Timing Requirements, Figure 2;
cross-checked against ADI AD7476 Rev D "Serial Interface" and TI
ADS7886 SLAS492B §8.4.1 — all three describe the same frame.)

- **CS frames everything.** The falling edge of CS takes SDATA out of
  tri-state, moves the track-and-hold from track to hold, samples the
  input, and starts the conversion (DS §7.3).
- **16 SCLK cycles per conversion/readout** (DS §7.3). tCONVERT =
  16 × tSCLK (DS §6.8).
- **Frame layout: 4 leading zeros, then 12 data bits, MSB first, no
  trailing zeros; DB0 is valid through the 16th SCLK period, and SDATA
  returns to tri-state after the 16th falling edge** (or at CS rising,
  whichever first) (DS §7.3, Figure 2). A 16-bit big-endian read
  therefore yields `0000 DB11 … DB0` — result = low 12 bits, no shift.
- **Data changes on SCLK falling edges; sample on the following rising
  edge.** Bits are "clocked out on falling edges of SCLK" (DS §7.3);
  the receiver reads each bit a half/full cycle later. Run SCLK
  idle-low, sample SDATA on rising edges (SPI mode 0): the first
  rising edge captures the first leading zero (driven at CS fall,
  t3 ≤ 20 ns), rising edges 5–16 capture DB11…DB0.
- **Idle-high caveat:** if the first SCLK edge after CS is a falling
  edge (idle-high clocking), the first leading zero may not be set up
  in time to be read correctly (DS §7.3) — another reason to clock
  idle-low. Figure 2 is drawn with idle-high SCLK; do not pattern-match
  the PIO program against the drawing without reading this caveat.
- **Throughput:** fRATE = 1 MSPS max at fSCLK = 20 MHz (DS §6.5).
  Minimum frame period: 16 × 50 ns = 800 ns, plus tQUIET — but the
  ensured max throughput is 1 MSPS, not 1/850 ns; see quirks.md.
- **tQUIET ≥ 50 ns** between bus relinquish and the next CS falling
  edge (DS §6.8 note 2).
- **CS timing:** t1 (CS min pulse width) 10 ns; t2 (CS to SCLK setup)
  10 ns (DS §6.8). After 16 SCLK cycles CS may idle high or low until
  the next conversion (DS §7.4.3.1).
- **Track/hold:** the part returns from hold to track on the 13th
  rising edge of SCLK (DS §7.3). tTH acquisition time 400 ns max
  (DS §6.5).
- **Key output timing at 3 V** (DS §6.8): t4 data access after SCLK
  falling ≤ 40 ns; t7 SCLK-to-data hold ≥ 7 ns; t3 CS-to-SDATA-active
  ≤ 20 ns; t8 SCLK-falling-to-tri-state ≤ 25 ns.

### Power-down via CS (DS §7.4.3)

- **Normal mode:** keep CS low until after the 10th falling edge of
  SCLK; the part stays fully powered. CS high between the 10th and
  16th falling edge aborts the conversion but stays in normal mode.
- **Shutdown mode:** bring CS high between the 2nd and 10th falling
  edge — conversion aborts, analog circuitry powers off. CS high
  before the 2nd falling edge changes nothing (noise immunity).
- **Exit/power-up:** CS low restarts power-up, 1 µs typ (tPOWER-UP,
  DS §6.8); the first conversion after power-up is a dummy — discard
  it, observe tQUIET, the second conversion is valid (DS §7.4.2,
  §7.4.3.3). One dummy conversion is also required after first
  applying VDD; the part can power up in either mode (DS §7.4.3.2).
- Shutdown duty-cycling stops paying off above ~350 kSPS throughput
  (DS §9.3); for the 1 MSPS burst-capture use case, keep the part in
  normal mode continuously.

## Absolute maximums and overvoltage (DS §6.1, §8.1.1, §8.1.2)

- VDD: −0.3…+6.5 V. Operating temperature −40…+125 °C (DS §6.3).
- **Analog pin: −0.3 V … VDD + 0.3 V**, max ±10 mA into any pin. ESD
  diodes D1/D2 clamp VIN to the rails; beyond VDD + 300 mV or
  GND − 300 mV they conduct into the substrate/supply and corrupt
  conversions (DS §8.1.1). The current-sense amp's output must be
  bounded accordingly (it swings 0…~1.3 V by design — ample margin).
- **Digital inputs (SCLK, CS) tolerate −0.3…+6.5 V regardless of
  VDD** and are not latch-up-prone — SCLK/CS may be asserted before
  VDD (DS §8.1.2). Digital outputs still only drive to VDD.
- ESD: ±3.5 kV HBM, ±200 V CDM (DS §6.2).

## Analog input drive (DS §8.1.1)

- Input equivalent circuit: ~4 pF pin capacitance (C1), ~100 Ω
  track/hold switch on-resistance (R1), ~26 pF sampling capacitor
  (C2) — separate from the 30 pF CINA spec.
- Sampling causes input current pulses/voltage spikes: **drive VIN
  from a low-impedance source**; for dynamic performance use a low
  output-impedance amplifier. A current-sense amp output qualifies;
  THD degrades with source impedance (DS §6.9 Figure 8).
- Supply = reference: keep supply noise under ½ LSB (0.4 mV at
  3.3 V); treat VDD as a precision reference — bypass 0.1 µF + 1 µF
  within 1 cm, don't share the rail with noisy digital loads, and add
  a 100 Ω series resistor at SDATA if load capacitance exceeds 50 pF
  (DS §5 pin 1, §9.1, §9.2).

## Vendor/community software cross-check (standing instruction)

Linux IIO driver `drivers/iio/adc/ad7476.c` (torvalds/linux master)
covers this class: single IIO_VOLTAGE channel, one 16-bit big-endian
SPI read per conversion, CS asserted by the SPI core around the
transfer, no MOSI, no explicit SPI mode (controller default, mode 0),
VCC regulator doubles as the reference for scaling. Framing matches
the datasheet model.

- **No `adcs7476` compatible exists.** The DT binding
  (`Documentation/devicetree/bindings/iio/adc/adi,ad7476.yaml`) lists
  `adi,ad7476`/`adi,ad7466` etc.; an ADCS7476 would bind as
  `adi,ad7476` (drop-in replacement).
- **Shift discrepancy:** the driver's channel macro for the
  ad7466/ad7476 class is `AD7476_CHAN(bits) = shift 13 − bits`, i.e.
  **shift 1 for 12-bit**, reading bits [12:1] of the 16-bit word. The
  TI-class parts in the same driver (`adc121s`, `ads7866`) use
  shift = 12 − bits = 0. The ADCS7476, ADI AD7476 (Rev D), and ADS7886
  datasheets all describe the identical frame — 4 leading zeros + 12
  data bits with DB0 valid through the 16th SCLK period — which maps
  to **shift 0**. See quirks.md; our PIO firmware follows the
  datasheet (low 12 bits of the 16-bit word), and the first bench
  read against a known voltage settles it.
