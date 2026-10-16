# RP2040 — facts

Raspberry Pi Ltd's dual-core Cortex-M0+ microcontroller — the CI
board's supervisor MCU (DESIGN.md §5). So far only Raspberry Pi's
board-design application note is vendored; the RP2040 datasheet
itself is not. Documents on disk:

- `hardware-design-with-rp2040-release2.pdf` — "Hardware design with
  RP2040 — using RP2040 microcontrollers to build boards and
  products", Release 2 (build date 20/08/2026, build 0444806419d7),
  35 pp. Sections below cite it as (AN §x.y).

## Power design (AN §2.1, §2.4.1, §3.1)

Extracted in [power-design.md](power-design.md): the 3.3 V + on-chip
1.1 V rail structure, the reference NCP1117 USB-5 V → 3.3 V LDO input
stage, the decoupling rules (100 nF per power pin, 1 µF ceramics on
VREG_IN/VREG_OUT), and the USB pin requirements (27 Ω series
resistors near the chip, ~90 Ω differential routing).

## Not yet extracted

Everything else — the minimal design example's flash/crystal/reset
sections (AN §2.2–§2.3), the Pico carrier chapters (AN §3), and the
RP2040 datasheet proper. Extract per-topic files here as tasks touch
them.
