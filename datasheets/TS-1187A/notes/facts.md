# TS-1187A extracted facts — CI board input-tile tactile button

Part: **TS-1187A-B-A-B** — XKB Connection 5.1×5.1 mm SMD tactile
switch. Two per input tile on the CI board (`button_a` = PC5,
`button_b` = PC6), each paralleled by a 2N7002 override FET
(docs/instrumented-ci.md §6).

Source (canonical PDF in `datasheets/TS-1187A/`):

- `TS-1187A-drawing-revA0.pdf` — cited as (XKB TS-1187A); XKB
  mechanical/electrical drawing TS-1187A-X-X-X, revision A0, the
  document LCSC links for C318884. The drawing is image-only — the
  facts below are read off it, not text-extracted.

JLCPCB/LCSC inventory (queried 2026-10-16, live): **XKB Connection
TS-1187A-B-A-B, C318884, SMD-4P 5.1×5.1 mm, Basic tier**,
$0.0207 @20, 40,860 stock.

## Facts (XKB TS-1187A, specification block and code tables)

- **Contact rating 50 mA, 12 V DC**; contact resistance 100 mΩ max;
  insulation resistance 100 MΩ min @ 500 V DC; dielectric strength
  250 V AC for 1 minute.
- Operating force: the `-B-` variant code is 160 gf (A = 100 gf,
  B = 160 gf, C = 260 gf); travel 0.25 mm; height code B = 1.6 mm
  (table: A = 1.5, B = 1.6, C = 1.7, D = 2.0, …, J = 5.0).
- Operating life 100,000 cycles; operating temperature
  −30 … +85 °C.
- **Four SMD terminals as two commoned pairs** — the drawing's
  schematic shows A–B commoned and C–D commoned, with the contact
  closing between the pairs. The KiCad footprint
  `Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A` merges each pair into
  one pad, so the switch presents as pads 1/2 against the
  `Switch:SW_Push` symbol.
- PCB-layout land pattern on the drawing: 7.0 × 5.0 mm pad span —
  the KiCad footprint matches (the part-numbered footprint exists in
  the stock KiCad library, so no project footprint is needed).
