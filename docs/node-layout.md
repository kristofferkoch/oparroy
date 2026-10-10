# Node board — layout checklist

The order that works for the 2-layer place-and-route, written down
after solving it twice. Work top to bottom; each step
explains *why* so a capture change can re-derive the item rather than
blindly follow it.

Anchor on **net names and design-part names** (Dar, Rar, SW1, …) —
annotation renumbers the board refdes between passes, the nets and the
`/PHY1/`, `/WD1/`, `/SL1/` sheet paths don't. Current-pass refdes
appear in parens where the mapping isn't obvious.

Constraints are seeded, not hand-set: `design/node_board.py` writes the
stackup, the Default/Bypass/Power net classes, and the board minimums
(`boards/node/` pair). If DRC complains, fix the layout — the minimums
are deliberately looser than the fab's.

## Placement

1. **J1 and J2 first** (B.Cu, the only back-side footprints — §7
   contract), on opposite short edges, long axis along the cable run
   (docs/node-board.md, items 6/9). They fix the board
   length; everything else fills the front between them.
1. **Bypass spine**: the dead-node copper is one straight flow —
   J1.5 → Dar → Rar → SW1.B1, SW1.COM → Rat → Dat → J2.5. Lay it out
   as a spine across the board *before* anything else competes for the
   space. TVS flat against its connector pins, series R next, SW1 on
   the J2 half.
1. **MCU (U3) in the middle, hanging off the spine's tap**: `opa_p`
   (Rar → SW1.B1) is also the MCU's RX_A input (PA2), so the MCU sits
   beside the Rar–SW1 run. Orient it so the OPA inputs (PA2, PA1,
   PD7) face the RX resistors and the TIM1 outputs (PD2, PC3) face
   SW1/J1 — crossed ratsnests here are what makes this board hard.
1. **MCU's tight satellites**: C1 (100n) at the VDD pin, C2 (10u)
   beside it; Rth1/Rth2 (the VDD/2 divider) tight to PA1; Rfb (DNP)
   spanning PD4 → `opa_p` so the hysteresis fallback is a solder
   blob away, not a rework.
1. **Ring B pair**: Dbr/Rbr toward J2.7, Rbt/Dbt toward J1.7 — TVS at
   the connector, R between TVS and MCU pin (§7 contract; the checker
   wants to assert exactly this).
1. **Watchdog cluster together** (WD1: Rs at the ka pin PD3, Cp,
   BAT54S, Cs, Rb). The `sel` node is 47k-pulled and drives both the
   switch select and TIM1_BKIN — keep the cluster's sel-side parts
   (Cs, Rb, D5 cathode) short and away from the TX runs.
1. **Rsel (0R) + BUF1 (DNP 74LVC1G17) straddling it**, in line between
   the watchdog and SW1.s. The §4 insurance only works if the fix is a
   resistor swap: adjacent, same orientation, hand-solderable.
1. **LED row on the front edge**, each reverse-mount LED centered over
   its routed hole (§7 part-over-hole contract): Du next to J1, Dd
   next to J2 (current pass: LED3/LED1), Dp (power, red) and Dw
   (working, yellow) between them — the row reads upstream →
   downstream.
1. **Pogo strip on a short edge**, 2.54 mm pitch, order
   SWIO/3V3/GND (TP1/TP2/TP3), with TP4 (PC7) as a free pad near the
   MCU's PC7 corner.
1. **Outline + 2× M2.5 mounting holes last** (item 6: layout proposes
   the minimal rectangle; §7 checker numbers get fixed once drawn).
   Drawn: rounded corners, holes, and the GND pours.

## Routing

1. **Bypass path first, as short as possible**: `RX_A`,
   `PHY1/txa_sw`, `TX_A` — the Bypass class copper (0.4 mm), with
   `opa_p` riding the same spine but in Default class (its 0.3 mm class
   clearance was unmeetable at the MCU's TSSOP-20 pads, since
   demoted). Top side, zero vias if the spine placement did its
   job; every via in this path is copper the ring depends on with the
   node dead.
1. **Ring B next**: `RX_B` (J2.7 → Dbr → Rbr → PD7), `TX_B` (PC3 →
   Rbt → Dbt → J1.7). Default class.
1. **Power class**: `UNREG` straight through J1.1 → J2.1 (pure
   pass-through, §2.1), `3V3` from both faces' pins 3/9 to the loads.
   Neck down into pads — class width is a default, not a rule.
1. **Small signals**: `ka` (PD3 → Rs), `sel` (watchdog → Rsel →
   SW1.s + PC2) short and clear of the TX edges, `led_work`,
   `led_seg`, `swio` → TP1, `pc7` → TP4, the VDD/2 node short at PA1.
1. **GND last, as pours** both sides (poured, not routed): stitch the
   row-2 GND pins of J1/J2 between faces, no islands, no long thin
   necks. Return-path eyeball while pouring (IDEAS, rung-1 geometric
   checks): plane continuous under the TX/RX runs, a
   stitching via near every signal layer change.

## Before calling it done

- [ ] DRC clean against the seeded classes and minimums, modulo the
  known-intrinsic set: the LED light-pipe NPTHs flag
  `copper_edge_clearance` (the 0.3 mm router-bit edge floor also
  judges holes — footprint-fixed 0.175 mm pad-to-hole) and
  `npth_inside_courtyard` under the connectors; both deliberate, both
  pending exclusion or a footprint/quote decision. **LED NPTHs
  resolved** — the footprint's slot shrank to 1.5×2.4 mm
  (project-local `Oparroy:` variant, 0.325 mm pad-to-slot nominal),
  clearing the edge floor; the connector `npth_inside_courtyard`
  pair stays as the remaining intrinsic set.
- [ ] B.Cu footprint set is exactly J1 + J2.
- [ ] Each reverse-mount LED over its hole; TVS adjacent to its
  connector with the R between TVS and µC.
- [ ] DNP parts (Rfb, BUF1) fitted-swappable with a hand iron.
- [ ] Serial box + board-ID silkscreen on the **back**, clear of pads;
  front silk stays clean (item 10).
- [ ] Netlist review for the known trap: Dd's anode returns to 3V3,
  not GND (the dark-forever catch — sim-pinned in
  `circuits/status-leds/`, but eyeball it in pcbnew anyway).
- [ ] Back-annotate (`python -m design.node --back-annotate …`) so
  refdes renumbering folds back into the annotation file; confirm
  the firmware pin header is untouched.
