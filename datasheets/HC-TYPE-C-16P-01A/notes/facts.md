# HC-TYPE-C-16P-01A — facts

USB 2.0-only 16-pin Type-C receptacle, top-mount horizontal SMD — the
CI board's power inlet and supervisor host link (DESIGN.md §6 "Board
power and host link", `design/ci_power.py`). Vendor: HCTL (Shenzhen
Huacantianlu Electronics), LCSC **C2894897**. Documents on disk:

- `HC-TYPE-C-16P-01A-datasheet-revA.pdf` — vendor mechanical drawing,
  REV A, one sheet (AutoCAD plot, Chinese title block). Mechanical
  dims, materials, electrical ratings, and a pin-assignment table; no
  PCB-decal numbering beyond the recommended-layout pad labels.
  Sections below cite it as (DWG).

## Pin assignment (DWG, "USB TYPE-C PIN ASSIGNMENTS" table)

Standard 16P USB-C receptacle pinning — matches KiCad's
`Connector:USB_C_Receptacle_USB2.0_16P` symbol pin-for-pin:

| Pin | Signal | Pin | Signal |
| --- | ------ | --- | ------ |
| A1  | GND    | B12 | GND    |
| A4  | VBUS   | B9  | VBUS   |
| A5  | CC1    | B8  | SBU2   |
| A6  | DP1    | B7  | DN2    |
| A7  | DN1    | B6  | DP2    |
| A8  | SBU1   | B5  | CC2    |
| A9  | VBUS   | B4  | VBUS   |
| A12 | GND    | B1  | GND    |

The drawing's recommended PCB layout labels pads in the same A/B
scheme; the electrically common pairs (A1/B12, A4/B9, A9/B4, A12/B1)
sit at shared x positions, with the signal pins staggered between
them — matching the KiCad library footprint
`Connector_USB:USB_C_Receptacle_HCTL_HC-TYPE-C-16P-01A` pad for pad.

## Electrical ratings (DWG, Notes §3)

- Current: **5 A VBUS**, 1.25 A GND pins, 0.25 A other pins.
- Voltage: 20 V max; withstanding voltage 100 V AC rms.
- Contact resistance: 40 mΩ max; insulation resistance 100 MΩ min.
- Temperature range: −55…+85 °C.

## Mechanical (DWG)

- Mid-mount/top-mount horizontal receptacle, body length 7.35 mm,
  shell width 8.94 mm; 16 SMD signal pads + 4 shell anchors (SH).
- Shell: SUS304-H stainless, nickel-plated; contacts: copper alloy,
  gold-plated functional area; molding LCP UL94 V-0.
- Insertion force 5–20 N; extraction 8–20 N (post-test).
- Tolerances: ±0.30 mm (x.x), ±0.20 (x.xx), ±0.10 (x.xxx).
