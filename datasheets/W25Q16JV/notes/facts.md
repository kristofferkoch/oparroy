# W25Q16JV extracted facts — supervisor QSPI boot flash

Part: **Winbond W25Q16JV**, 16 Mbit (2 MB) serial NOR flash with
standard/dual/quad SPI. Target orderable: **W25Q16JVSSIQ** — SOIC-8
208-mil, industrial −40…+85 °C, green package with QE fixed 1 (DS §12
ordering information). Role: RP2040 supervisor's boot flash (DESIGN.md
§6; app-note context in
[datasheets/RP2040/notes/flash-crystal.md](../../RP2040/notes/flash-crystal.md)).

Source (canonical PDF in `datasheets/W25Q16JV/`):

- `W25Q16JV-datasheet-revH.pdf` — "W25Q16JV 3V 16M-BIT Serial Flash
  Memory with Dual/Quad SPI", Revision H, publication release date
  April 08, 2019, from winbond.com. Cited as (DS §x.y).

## Pinout — 8-pin SOIC (DS §3.1 Figure 1a, §3.3)

| Pin | Name                  | I/O | Function                             |
| --- | --------------------- | --- | ------------------------------------ |
| 1   | /CS                   | I   | Chip Select                          |
| 2   | DO (IO1)              | I/O | Data Output (dual/quad IO1)          |
| 3   | /WP (IO2)             | I/O | Write Protect, active low (quad IO2) |
| 4   | GND                   | —   | Ground                               |
| 5   | DI (IO0)              | I/O | Data Input (dual/quad IO0)           |
| 6   | CLK                   | I   | Serial Clock                         |
| 7   | /HOLD or /RESET (IO3) | I/O | Hold, active low (quad IO3)          |
| 8   | VCC                   | —   | Power supply                         |

Pin 7 is /HOLD on 8-pin packages; a dedicated hardware /RESET exists
only on SOIC-16/TFBGA variants (DS §4.1 note).

## Electrical quick table

- **Supply: single 2.7–3.6 V** (DS §2 features; §10.3). Pairs with the
  CI board's 3.3 V rail.
- Max clock: 133 MHz except 03h read (50 MHz); 104 MHz ceiling at
  2.7–3.0 V (DS §10.6 AC characteristics).

## Facts the schematic capture consumes

- **/CS must track VCC at power-up and power-down** — "If needed a
  pull-up resister on the /CS pin can be used to accomplish this" (DS
  §4.1, repeated in §6.3 write-protection and §10.3). This is the
  silicon-level reason for the 10 kΩ QSPI_SS pull-up the RP2040 app
  note carries as DNF-for-W25Q128: **fit it for this part** (RP2040 AN
  §2.2).
- **/WP and /HOLD are active-low inputs** (DS §4.3, §4.4). When the QE
  bit in Status Register-2 is set — **fixed 1 in the `Q`-suffix
  orderable W25Q16JVSSIQ** (DS §12 note 4) — pin 3 becomes IO2 and pin
  7 becomes IO3 and the /WP, /HOLD functions vanish (DS §4.2, §3.3
  note 2). With QE fixed, no /WP pull is required for write
  protection; the pins are plain quad-data lines. If a non-Q variant
  is ever substituted, /WP and /HOLD need pulling high when unused.
- RP2040-side wiring: CLK←QSPI_SCLK, /CS←QSPI_SS (10 kΩ pull-up + 1
  kΩ BOOTSEL strap), DI/DO/IO2/IO3 ← QSPI_SD0/SD1/SD2/SD3 (RP2040 AN
  §2.2; pin numbers in
  [datasheets/RP2040/notes/pinout.md](../../RP2040/notes/pinout.md)).
