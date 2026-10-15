# 3M 3365 — quirks

- **The bundled catalog page contradicts the tech sheet** — the 3365/14
  catalog page inside `3M3365-TS-0080-datasheet-v15.pdf` lists
  unbalanced impedance 108 Ω, capacitance 12.8 pF/ft, propagation delay
  1.40 ns/ft, and 0 for every balanced quantity, while the TS-0080-15
  tech sheet proper says 102 Ω, 14.47 pF/ft, 1.47 ns/ft. The catalog
  page is a partially-populated database dump; use the tech-sheet values
  (they also pass the √(L/C) consistency check — see
  [facts.md](facts.md)).
- **Conductor resistance has no unit in the document** — the
  characteristics table says only "Conductor Resistance 65 Ohm". The
  /1000 ft basis comes from 3M's catalog convention, not from TS-0080.
