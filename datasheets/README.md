# datasheets/

Canonical PDF datasheets and reference manuals for the parts this project
uses, plus LLM-readable sidecar notes. **One directory per part**, e.g.
`datasheets/CH32V003/`:

- `datasheets/<PART>/<PART><doc>-v<ver>.pdf` — the canonical vendor
  documents, version in the filename (e.g.
  `CH32V003/CH32V003DS0-datasheet-v1.8.pdf`).
- `datasheets/<PART>/notes/` — the LLM-readable sidecars. `facts.md` is
  the index and overview (part identity, memory map, electrical quick
  table); each peripheral/topic gets its own file (`opa.md`,
  `timers.md`, `usart-i2c-spi.md`, …) so a task can load only the
  subsystem it touches. `quirks.md` is the errata and tribal-knowledge
  file (issue trackers, wikis, bench findings), one sourced bullet per
  quirk. Facts cite the source document and section (e.g. `(RM §17.2)`).

LLMs read PDFs badly: **read the `notes/` markdown first**; open the PDF
only when the note says the detail wasn't extracted.

## Index

| Part                            | Role in oparroy                                                           | Documents on disk                                                        | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| ------------------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [CH32V003](CH32V003/)           | Node MCU — CH32V003F4P6, TSSOP-20 (DESIGN.md §5)                          | DS0 datasheet v1.8, RM reference manual v1.9, QingKeV2 debug manual v1.0 | [facts](CH32V003/notes/facts.md) + per-peripheral: [opa](CH32V003/notes/opa.md), [timers](CH32V003/notes/timers.md), [dma](CH32V003/notes/dma.md), [adc](CH32V003/notes/adc.md), [gpio-pinout](CH32V003/notes/gpio-pinout.md), [rcc-clocks](CH32V003/notes/rcc-clocks.md), [usart-i2c-spi](CH32V003/notes/usart-i2c-spi.md), [exti-pfic](CH32V003/notes/exti-pfic.md), [sdi-debug](CH32V003/notes/sdi-debug.md), [flash-option-bytes](CH32V003/notes/flash-option-bytes.md), [power-reset](CH32V003/notes/power-reset.md), [quirks](CH32V003/notes/quirks.md) |
| [SN74LVC1G3157](SN74LVC1G3157/) | Ring-A watchdog bypass SPDT analog switch (DESIGN.md §4)                  | SCES424O (rev. 2025-06)                                                  | [facts](SN74LVC1G3157/notes/facts.md)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| [BAT54S](BAT54S/)               | Watchdog charge-pump dual Schottky pair (DESIGN.md §4)                    | Nexperia BAT54SER v5, TWGMC C727126                                      | [facts](BAT54S/notes/facts.md)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| [3M3365](3M3365/)               | Candidate segment cable, 28 AWG ribbon (DESIGN.md §3; reach modeling, §9) | 3M TS-0080 v15                                                           | [facts](3M3365/notes/facts.md)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |

Not yet vendored: **RP2040** (supervisor MCU, DESIGN.md §5).
