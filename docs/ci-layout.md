# CI board physical layout

Input to DESIGN.md §6. Covers the placement sketch, scan-chain mapping
freedom, and mechanical/cost envelope. Electrical topology and bit meanings
stay in [scan-plane.md](scan-plane.md); assembly pricing stays in
[pcba-research.md](pcba-research.md).

## Placement sketch

`boards/ci/grid-layout.py` generates a deterministic first placement through
pcbnew. It is an editable starting point, not an autorouted or fabrication-
ready layout.

- T0–T3 run left-to-right across the top; T7–T4 run left-to-right across the
  bottom, so logical ring order follows a horseshoe. Bottom tiles mirror their
  local X coordinates but remain on the front, preserving single-side SMT.
- Every tile centers its MCU, keeps decoupling adjacent, orders the PHY along
  the signal path, and groups watchdog, fault-injection, test-point, payload,
  and LED functions into local zones.
- Each tile's 74HC595 and its pull-downs form an inner-edge array. The center
  carries the supervisor, power, SWIO/debug trees, and AUX/OBS stages.
- The generator keys placement to `placement-map.json` capture paths, rejects
  stale maps, checks board containment and footprint overlap, and preserves
  reference designators and pad-net assignments.

The generated sketch uses **240 × 180 mm** tile-grid placement: four 55 × 55 mm
cells per row around a 50 mm center band. The earlier 320 × 240 mm version was
an area-for-legibility experiment; its 768 cm² area crossed the PCBA
large-board fee threshold described in
[pcba-research.md#ci-board-size-and-cost-snapshot](pcba-research.md#ci-board-size-and-cost-snapshot).
The compact sketch passes the same containment and overlap checks and remains
a placement starting point, not a routed fabrication release.

## Scan-chain mapping freedom

The scan chain's logical signals do not require a particular physical stage
order or `QA…QH` / 165-input assignment. Tile identity and signal names are
stable; chain position and parallel-bit position are layout degrees of freedom.
The present captured order and bit map remain authoritative until a
layout-derived mapping replaces them.

If placement optimization uses that freedom, the chosen mapping becomes
explicit DSL data and regenerates both the netlist and the supervisor's named
bit map. The PCB must not become an undocumented second source of truth.
Reset behavior, transaction length, and observe timing do not depend on the
permutation. This optimization is available, not implemented by the placement
sketch.

## Board-size and enclosure target

**Use 240 × 180 mm for the first-spin placement target.** That is 432 cm², 44%
less area than the original sketch, and below the 650 cm² PCBA large-board
threshold. Further compaction remains optional; the threshold and the actual
enclosure, not that exact aspect ratio, are the constraints.

There is no AliExpress enclosure standard. Nominal **250 × 200 × 100 mm** and
**300 × 250 × 100 mm** ABS junction/instrument boxes recur across generic
vendors and established enclosure ranges
([generic ABS series](https://m.made-in-china.com/product/Durable-Waterproof-ABS-Plastic-Enclosure-for-Outdoor-Electronics-2248266685.html),
[BERNSTEIN enclosure range](https://www.bernstein-ltd.co.uk/products/detail.aspx?CW_CODE=0077)).
Use these as size classes, not as evidence that every listing shares internal
geometry.

- **240 × 180 mm PCB in a nominal 300 × 250 × 100 mm case** is the first-spin
  target. The nominal difference leaves 60 × 70 mm total perimeter allowance.
- **200 × 160 mm PCB in a nominal 250 × 200 × 100 mm case** is the smaller
  alternative if further compaction succeeds.

The quoted case dimensions are external. Select the actual enclosure before
freezing the board outline, mounting holes, or connector keepouts; verify its
internal dimensions, mounting-boss pattern, lid intrusion, standoffs, USB and
boundary-cable access, control/LED visibility, and cable bend space. The
placement sketch does not yet define mounting holes.

## Cost priorities

Four-layer area and finish drive bare-board fabrication. Assembly cost is led
by components, unique BOM/feeder lines, setup, and inspection; ordinary SMT
joint count is comparatively cheap. Compaction saves board area and avoids the
large-board surcharge but does not materially change the BOM. See the
[five-board planning estimate](pcba-research.md#ci-board-size-and-cost-snapshot)
for the current snapshot and assumptions.
