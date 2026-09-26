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
