# RP2040 — quirks

Doc-vs-doc mismatches, silicon errata, and tribal knowledge, one
sourced bullet each.

- **QSPI chip-select naming mismatch.** The RP2040 datasheet pin list
  names pad 56 `QSPI_CSn` (DS §5.5.2.2 Table 616), while the
  hardware-design app note, its schematics, and the BOOTSEL
  documentation call the same net `QSPI_SS` (AN §2.2). The supervisor
  capture uses `QSPI_SS` (the app-note name, which carries the
  boot-strap meaning); treat `QSPI_CSn` as an alias.
- **The app note's DNF on the QSPI_SS pull-up is flash-specific.** AN
  §2.2 marks R2 (10 kΩ pull-up) Do-Not-Fit because it proved
  unnecessary *with the W25Q128JVS in the example*. The Winbond
  W25Q16JV datasheet requires /CS to track VCC at power-up and
  suggests a pull-up to do it (W25Q16JV DS §4.1) — the DNF does not
  transfer; fit the pull-up for W25Q16JV.
