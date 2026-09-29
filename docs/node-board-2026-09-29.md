# Node board — open decisions and layout log

Working doc for the node board (KANBAN.md): everything not yet decided
in the design, inventoried 2026-09-29 before layout starts. Decisions
graduate into DESIGN.md as they settle (section references below);
this doc keeps the reasoning and the discarded options. Struck items
are settled.

Settled already (no decision owed): segment connector and pinout (§3),
reverse-mount status LEDs through PCB holes with colors picked (§4.1 —
power red, working yellow-green 570 nm, per-connector yellow),
single-sided front assembly with back-side SMD headers (§7), SWIO pogo
strip with programmer-supplied 3V3 (§6), MCU decoupling (100n + 10u),
VDD/2 threshold from the 10k bin (§2), DNP hysteresis feedback R (§2),
charge-pump watchdog values (§4).

## Electrical / BOM

1. **TVS part pick** — the capture carries a provisional value
   (`PESD3V3L1BA`, `design/bins.py`) with no parts-DB record: no LCSC
   number, no tier, no stock snapshot. Needs a real record (§6
   inventory-driven selection) — low-capacitance bidirectional, VRWM ≥
   3.3 V (§7 checklist). Also: populate or DNP on these boards? §7
   settles the CI board fully populated and production nodes DNP-allowed;
   the standalone node boards sit between — they are the first bench
   articles for the §2/§4 claims.
1. **BAT54S tier/stock unverified** — the parts DB marks C727126's tier
   unverified and stock never queried (IDEAS.md, 2026-09-28); a
   conservative filter never admits it. Needs a human on jlcpcb.com.
1. **`sel` Schmitt buffer** — §4's accepted spec violation (the slow
   sel ramp vs the switch's 10 ns/V input-rate spec): ship bare, or add
   a 74LVC1G17 footprint (populated or DNP) as insurance? One Extended
   BOM line if populated (§4); a DNP footprint costs only area.
1. **Per-connector LED drive** — the capture drives `led_upstream`/
   `led_downstream` from MCU GPIO (PC0/PC1). §4.1 notes the ideal is
   PHY-hardware drive so the LEDs tell the truth with a dead MCU. That
   costs parts against §1; confirm firmware-driven for this revision.
   (The activity/no-signal/error encoding itself is firmware scope —
   §4.1 TBD rides with the node firmware.)

## Mechanical / layout

5. **Stackup and thickness** (§9 open question) — 2-layer vs 4-layer,
   and target ≤1.0 mm thickness. §9 leans 4-layer for size/quality but
   every layer argues against the §1 cost driver; the board is tiny,
   single-sided, and its whole back is two connectors plus pass-through.
   Gates layout start; the exact JLCPCB thickness/stackup combos
   verify at quote time.
1. **Board outline** — dimensions, corner radius (the §7 min-radius
   check wants a number), mounting holes: count, diameter, position.
   The front is the flat enclosure-wall mount face (§3, §7) — but the
   mount itself (standoffs? adhesive? screw bosses in the enclosure?)
   is undefined, and it sets the hole pattern.
1. **Connector placement** — edge orientation and cable-exit direction
   for J1/J2, spacing between them, and hand-solder access: the
   headers are back-side SMD, hand-soldered post-PCBA (§3), so the
   front must not crowd the iron's approach through... nothing — but
   tall front parts near the board edge still fight the iron angle.
1. **Programming strip geometry** — today three 1.5×1.5 mm pads
   (`design/node.py` TP1/TP2/TP3). The T27 pogo jig consumes this:
   pad size, pitch, edge placement, and whether 1.5 mm pads are
   pogo-friendly at all (1.0 mm-pitch pogo arrays want specific land).
1. **Back-face information layout** — LED hole positions relative to
   their connectors (§4.1: each LED points at its segment), the
   handwritten serial box (§7 — on the back, the viewer side?), and
   the board-ID silkscreen fields (§7 — which face?).
1. **Spare pads** — PC7 (spare) and the unbound payload pads
   (debug_tx, pot, buzzer, buttons) are NC by capture, reported as
   warnings. Test pad on PC7, or truly nothing?

## Pipeline

11. **KiCad application provisioning** — the flake carries the KiCad
    10 symbol/footprint *libraries* only; pcbnew ingest, layout, and
    the back-annotation round trip need the application. Add KiCad to
    the flake (pinned, matching the library version) or use a
    workstation install? Reproducibility (§8) argues flake; GUI-in-nix
    argues workstation.
01. **Back-annotation join validation** — `annotation_from_pcb` is
    tested against synthetic input only; the first real `.kicad_pcb`
    exercises it (the T7a caveat, §7). Ride-along: T19's pcbnew
    skeleton-ingest validation.
01. **Layout-rules instance** — the node board needs its `LayoutRules`
    data: net classes (widths/clearances/vias), trace-length budgets,
    keepouts, the mounting-hole and serial-box numbers from items
    6–9. Feeds the `pcb_emit` skeleton that guides the human layout.

## Fab / purchasing

14. **Quantity** — PCB fab minimum 5, assembly minimum 2 (§6). Ring
    bring-up wants ≥2 working nodes plus a supervisor stand-in; how
    many of the 5 get assembled? Spare blanks come free.
01. **Buy-ahead: segment header** — C22385222 thin-stocked (285 on
    2026-09-29, §3). Order when, against what fab date?
01. **Quote-time stackup combos** — which thicknesses JLCPCB actually
    offers in 2- and 4-layer at this board size (with item 5).
