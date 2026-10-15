# SN74HC595 extracted facts — scan-plane control shift register

Part: **SN74HC595** (SOIC-16/TSSOP-16-class), 8-bit serial-in,
parallel-out shift register feeding an 8-bit D-type storage register
with 3-state outputs. Extracted for the CI scan control/observe plane
(`docs/scan-plane.md`, DESIGN.md §6).

Source (canonical PDF in `datasheets/SN74HC595/`):

- `SN74HC595-SCLS041J-datasheet-vJ.pdf` — cited as (SCLS041J §x.y);
  SCLS041J, December 1982, revised October 2021, from ti.com.

JLCPCB/LCSC inventory (queried 2026-10-15 via JLCPCB's live parts
search): **Nexperia 74HC595D,118, C5947, SOIC-16, Basic tier**,
$0.1132 @1, ~285k stock — the sole Basic 74HC595 listing in any
package. Extended alternates: TI SN74HC595DR (C10092), Nexperia
TSSOP-16 74HC595PW,118 (C5948).

## Pinout and function (SCLS041J §3, §8.4)

Pins (SOIC/TSSOP-16): 13 = `/OE`, 12 = `RCLK` (storage-register clock),
10 = `/SRCLR` (shift-register clear), 11 = `SRCLK`, 14 = `SER`,
9 = `QH'` (cascade out, not 3-state), 15/1–7 = `QA`–`QH`.

Function table (Table 8-1):

- `/OE` high ⇒ `QA`–`QH` **high-impedance**; `/OE` low ⇒ enabled.
- `/SRCLR` low ⇒ **shift register cleared — the storage register is
  untouched** (no storage-register clear exists on this part).
- `RCLK` rising edge ⇒ shift-register data copied to the storage
  register. Outputs never change while shifting — shifting is
  glitch-free at the pins.

## Facts that shape the scan plane

- **No power-on-state spec anywhere in SCLS041J.** The storage
  register's state at VCC ramp is unspecified; outputs are
  indeterminate from power-on until the first `RCLK`. Consequence
  (`docs/scan-plane.md` §POR): the scan plane's "reset state =
  all-zeros" is *constructed* — `/OE` held high (outputs Hi-Z) with
  pull-downs defining the control lines, zeros shifted and latched,
  then `/OE` released — not read from silicon POR behavior.
- **Input thresholds** (SCLS041J §6.3): VIH min 1.5 / 3.15 / 4.2 V at
  VCC = 2 / 4.5 / 6 V (≈ 0.7×VCC → ~2.31 V at 3.3 V); VIL max 0.5 /
  1.35 / 1.8 V (≈ 0.3×VCC → ~0.99 V at 3.3 V). RP2040 and HC outputs
  drive these with margin at 3.3 V.
- **Input transition-rate limit** (SCLS041J §6.3 Δt/Δv): 1000 / 500 /
  400 ns/V at VCC = 2 / 4.5 / 6 V, with the standard slow-input
  double-clocking footnote — a floated or slow-ramped clock pin
  double-clocks. Chain clock/latch lines are push-pull driven; never
  leave them to RC.
- Unused inputs must be held at a rail (SCLS041J §6.3 note 1, pointing
  at TI SCBA004).
- Drive: ±6 mA at 5 V (front page); VOH/VOL specified at 4 mA on
  `QA`–`QH` (§6.5). The scan plane's loads are CMOS select pins and
  FET gates — microamps.
- Quiescent ICC ≤ 80 µA (front page); input current ≤ 1 µA. A 12-stage
  chain is ~1 mA worst case.
- tpd 13 ns typ (front page) — four orders of magnitude under the
  chain's multi-MHz ceiling; chain speed is a firmware choice.
