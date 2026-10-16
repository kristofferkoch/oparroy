# RP2040 — facts

Raspberry Pi Ltd's dual-core Cortex-M0+ microcontroller — the CI
board's supervisor MCU (DESIGN.md §5), QFN-56 7×7 mm. Documents on
disk:

- `rp2040-datasheet-2025-02-20.pdf` — the RP2040 datasheet, release of
  20 February 2025 (build-date 2025-02-20, build 3184e62-clean), 642
  pp, from datasheets.raspberrypi.com. Sections below cite it as
  (DS §x.y).
- `hardware-design-with-rp2040-release2.pdf` — "Hardware design with
  RP2040 — using RP2040 microcontrollers to build boards and
  products", Release 2 (build date 20/08/2026, build 0444806419d7),
  35 pp. Cited as (AN §x.y).

## Pinout (DS §5.5, §1.4)

Extracted in [pinout.md](pinout.md): the complete 56-pad + ePad
QFN-56 pad→name table with power domains and reset states, the full
GPIO function-mux table (SPI/UART/I2C/PWM/CLOCK/USB per GPIO), the
SPI0/SPI1 pin-choice sets, and the ADC0–3 ↔ GPIO26–29 mapping.

## Power design (AN §2.1, §2.4.1, §3.1)

Extracted in [power-design.md](power-design.md): the 3.3 V + on-chip
1.1 V rail structure, the reference NCP1117 USB-5 V → 3.3 V LDO input
stage, the decoupling rules (100 nF per power pin, 1 µF ceramics on
VREG_IN/VREG_OUT), and the USB pin requirements (27 Ω series
resistors near the chip, ~90 Ω differential routing).

## Flash, crystal, reset/boot (AN §2.2, §2.3, §2.6)

Extracted in [flash-crystal.md](flash-crystal.md): the QSPI flash
circuit (10 kΩ QSPI_SS pull-up, 1 kΩ BOOTSEL strap, supported-flash
rules), the 12 MHz crystal circuit (Abracon ABM8-272-T3, 15 pF + 15 pF
load caps, 1 kΩ series resistor), and the RUN/TESTEN/BOOTSEL wiring.

## Quirks

[quirks.md](quirks.md) — the QSPI_SS vs QSPI_CSn naming mismatch and
the flash-specific DNF on the QSPI_SS pull-up.

## Not yet extracted

The Pico carrier chapters (AN §3), the rest of the RP2040 datasheet
proper (peripherals, bootrom, XOSC/PLL details, IO banks, electrical
specs beyond §5.5.2/§5.5.3.1). Extract per-topic files here as tasks
touch them.
