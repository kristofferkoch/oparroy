# Node board — decisions and layout log

Working doc for the node board (KANBAN.md). Everything undecided in the
design was inventoried 2026-09-29 before layout start and settled the
same day (PR #24); the settled items graduate into DESIGN.md (section
references below). This doc keeps the reasoning, the discarded options,
and the layout brief the decisions add up to. The working layout
checklist those decisions feed is docs/node-layout-2026-10-04.md.

Previously settled (no decision owed): segment connector and pinout
(§3), reverse-mount status LEDs through PCB holes with colors picked
(§4.1 — power red, working yellow 588 nm, per-connector yellow-green
570 nm; the shuffle landed 2026-09-30 with the antiparallel merge, item
5 below), single-sided front assembly with back-side SMD headers (§7),
SWIO pogo strip with programmer-supplied 3V3 (§6), MCU decoupling
(100n + 10u), VDD/2 threshold from the 10k bin (§2), DNP hysteresis
feedback R (§2), charge-pump watchdog values (§4).

Fab order (2026-09-30): **the CI board fabs first** — its eight node
tiles are the first bench articles for the §2/§4 claims — so this
board's job is to be fully thought through before the CI board tiles
it; the standalone board fabs second, as the production-form proof.

## Settled 2026-09-29

1. **Stackup and thickness** (§9 open question, resolved): **2-layer,
   0.8 mm.** The §1 cost driver won — the board is tiny, single-sided,
   and its back is two connectors plus pass-through, so 4-layer's
   routing room buys nothing. 0.8 mm over 1.0 mm for feel, accepting
   more flex under the IDC mating shear the hand-soldered SMD headers
   take (§3). JLCPCB's exact 2-layer thickness offerings verify at
   quote time.
1. **KiCad application joins the flake** (§8): pinned, matching the
   KiCad 10 libraries the DSL validates against — pcbnew ingest must
   not drift from the validated libraries. A workstation install was
   the lighter but drift-prone alternative.
1. **TVS diodes populated** on the node boards (§7 checklist): they are
   the first bench articles for the §2/§4 claims, and DNP strictly
   removes load. The pick landed 2026-09-30: **Brightking UDD32C03L01**
   (LCSC C78439, Extended — no Basic SOD-323 TVS exists at all), VRWM
   3.3 V, Cj 0.8 pF typ — RC ≈ 0.4 ns against the 470 Ω series R.
   The parts-DB record `tvs-sod323` carries the stock snapshot and the
   rejected alternatives (SD03C, PESD3V3L1BA, BV03C).
1. **`sel` Schmitt insurance** (§4's accepted 10 ns/V violation): a
   **DNP 74LVC1G17 footprint in the sel path, bridged by a fitted
   0 Ω**. Costs only area while DNP (no Extended-line fee); if the
   bench disagrees the fix is a resistor swap, not a respin.
1. **Per-connector LEDs: firmware-driven, merged onto one antiparallel
   GPIO** (§4.1). Firmware drive confirmed against the
   hardware-activity ideal — the watchdog plus working LED already
   flag a dead node, and the CI board observes truth through the §6
   supervisor taps, so activity hardware doesn't survive §1. The two
   connector LEDs become an antiparallel pair on one pin with a shared
   series R: high = upstream, low = downstream, Hi-Z = dark, a kHz
   toggle = both (half brightness). Frees PC1 (an FT pin) and one
   resistor; the cost is firmware encoding complexity and the loss of
   independent steady states. The activity/no-signal/error encoding
   itself stays firmware scope. Corrected 2026-09-30 (caught in pcbnew
   netlist review of the first layout): **Dd's anode returns to 3V3,
   not GND** — the pin-low state sinks rail current through Dd and Rs
   into the pad; anode on GND leaves Dd dark in every drive state. The
   block then graduated to the §7 subcircuit-with-bench pattern it
   owed: `design/status_leds.py` (SL1 in the node capture), with the
   full drive-state truth table — pin high / pin low / Hi-Z, power,
   working — asserted in `circuits/status-leds/tb_status_leds.cir`
   against the DSL-emitted DUT (`tests/test_status_leds.py`); the
   bench re-fails when Dd's anode is tied back to GND.
1. **Board outline: layout proposes** a minimal rectangle — long axis
   along the cable run, connectors on the short edges — with **2×
   M2.5 mounting holes**; the §7 checker numbers (corner radius, hole
   keepouts) get fixed once drawn. Enclosure design stays future work.
1. **Programming strip geometry** (§7 checklist): keep the captured
   1.5×1.5 mm pads, **2.54 mm pitch on a short edge**, order
   SWIO/3V3/GND — standard pogo pitch; the pogo jig (KANBAN.md)
   consumes exactly this.
1. **Spare PC7 gets a test pad** — bare copper, no placement cost;
   bring-up observability and a future expansion point without a
   respin. The unbound payload pads (debug_tx, pot, buzzer, buttons)
   stay NC, reported as warnings.
1. **Segment connectors on opposite short edges** — cables exit in
   line; the node reads as a bead on the ribbon, natural for a ring
   segment and the enclosure-wall mount. The same-edge U-turn
   alternative clutters one edge and doubles cable bends.
1. **Serial box and board-ID silkscreen all on the back** — the
   connector side, where a viewer stands (§4.1). The front stays clean
   against the enclosure wall; front silkscreen would be invisible
   once mounted.
1. **Assemble two boards** (the JLCPCB assembly minimum), revised
   2026-09-30 with the CI-board-first fab order: the tiles on the CI
   board are the first ring, so the standalone pair proves the
   production form — single-sided assembly, back-side hand-soldered
   headers, the pogo programming flow — and the three spare blanks
   stay hand-solderable (0603/SOT-23/TSSOP-20, §5's rework argument).
   Supersedes the same-day "assemble all five" call, whose premise
   was a ring on the bench before the CI board exists.
1. **Header buy-ahead deferred** (user call): the C22385222 stock
   (285 on 2026-09-29, §3) gets re-checked before the fab order;
   revisit if the number drops.

## Still open

- **BAT54S tier/stock verification** — the parts DB marks C727126's
  tier unverified and stock never queried (IDEAS.md, 2026-09-28); a
  conservative filter never admits it. Needs a human on jlcpcb.com.
- **Back-annotation join validation** — `annotation_from_pcb` is
  tested against synthetic input only; the first real `.kicad_pcb`
  exercises it (the known DSL-capture caveat, §7). Ride-along: the layout checker's
  pcbnew skeleton-ingest validation.
- **Layout-rules instance** — the node board needs its `LayoutRules`
  data: net classes (widths/clearances/vias), trace-length budgets,
  keepouts, the mounting-hole and serial-box numbers once the outline
  is drawn. Feeds the `pcb_emit` skeleton that guides the human
  layout.
- **Capture deltas before netlist emission** — landed 2026-09-30: the
  LED merge (pin map + `design/node.py` + `firmware/node/pins.hpp`
  golden — one `led_segments` request on PC0, 16 of 18 GPIO, PC1 freed
  to spare), the `sel` Schmitt buffer (DNP 74LVC1G17 straddling a
  fitted 0 Ω in `design/phy_frontend.py`), the PC7 test pad (TP4 in
  `design/node.py` — its unconnected-pad warning is gone), and the TVS
  parts-DB record (`tvs-sod323`; the `design/bins.py` value follows).
