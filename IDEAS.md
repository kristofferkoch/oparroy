# IDEAS

Loose ideas to revisit. Append; never lose them. Promote into
`KANBAN.md` (a card in Next/Backlog) or `DESIGN.md` when they become
real work — **move**, don't copy. Reference, don't duplicate.

## Protocol

- WS2812-style self-clocked single-wire signaling, closed into a ring —
  settled 2026-09-26 (card T3): ratio-metric PWM cells at 800 kbit/s,
  positional slot addressing via UNIID enumeration, slotted telemetry.
  See DESIGN.md §2 and docs/phy-analysis-2026-09-26.md. Frame format
  detail: card T11.

## Fault tolerance

- Bypass topology — settled 2026-09-26 (card T2): counter-rotating dual
  ring with symmetric rebroadcast. See DESIGN.md §3. Intermittent-fault
  policy stays open as card T13.
- Capacitance characterization of data lines (2026-09-26) — a node
  measures line capacitance (e.g. charge-time / step-response via the
  comparator) to estimate cable length to its neighbor and to localize
  faults (open, short, water ingress shifts C). Doubles as a ring
  self-survey: each node reports its segment length. Open questions:
  measurement circuit (drive weakly, time the RC with TIM capture?),
  resolution vs. cable-length granularity, interaction with the bypass
  switches' on-capacitance.
- **Impedance probing as fault detection** (2026-09-26) — during the
  frame gap (line-low break, §2 vsync — the line is guaranteed idle), a
  node briefly drives its segment high then low (weak pull, or the TX
  pin itself) and watches via the comparator whether the line follows.
  Probe source needs no parts: the CH32V003 pads have both weak pull-up
  and pull-down, 35–55 kΩ (datasheets/CH32V003/notes/facts.md,
  gpio-pinout.md) — weak enough that a live far-end driver always wins,
  so no false triggers. Caveat: ring RX pins sit in floating-input mode
  for the OPA path (RM §7.2.10), so probing flips the pin mode
  momentarily — another reason to probe only inside the frame gap.
  A line that floats or responds sluggishly ⇒ far end open / connector
  dead — distinguishes "neighbor silent because bypassed" from
  "neighbor gone". Same family as the capacitance survey above — the
  probe pulse's edge rate *is* a charge-time measurement, so one
  circuit likely serves both. Open questions: probe strength vs
  false-triggering the neighbor's comparator, who probes whom on the
  dual ring (each direction's segment testable independently — §3),
  whether probing fits between frames without stealing ring bandwidth.

## Hardware

- Comparators for RX: threshold selection, hysteresis, glitch filtering.
- **QDM fast mode for CI flash** (parked 2026-09-29, against the §6
  2026-09-29 flash fan-out): the muxed single-PIO-channel scheme lands
  ≈1.6 s total flash, wire-bound at 8 nodes. If that ever hurts, the
  QingKeV2 QDM fast mode (debug manual §2.2, extracted in
  `datasheets/CH32V003/notes/sdi-debug.md`) is the reserve — more wire
  bandwidth per PIO channel, no topology change.
- **Blind-pin connector keying** (raised 2026-09-29, against the §3
  2026-09-29 connector decision): the 2x5 pinout's five grounds leave
  one expendable — blind pin 10 (the cable-edge conductor, so the
  floating stub couples least) on the header and press a polarizing
  plug (3M 3433-class) into the matching socket hole, PC-floppy
  style. GND×4 keeps the power budget (~0.16 Ω/m loop). Redundant on
  the CI board — the shrouded DC3/FC system already keys reverse and
  offset mating — but two future uses: (a) dropping to a plain
  unshrouded 2x5 header (~$0.02 vs $0.068, lower profile) on
  production nodes, where the blind pin is the *only* keying; (b)
  **connector-type discrimination** once the §6 debug transport
  lands — different blind-pin patterns keep a segment cable out of a
  debug header that will likely also be a pin header. Costs to
  remember: a manual pin-pull the netlist/layout checker can't see,
  one plug per cable end, and the loss of the shroud's retention and
  pin protection on the connector we deliberately yank (§6).

## Node peripherals

- **Load cell** as a supported sensor type (2026-09-26). Interesting
  because it likely wants its own small board: strain-gauge bridge
  excitation + sensitive low-noise analog front end (instrumentation
  amp / 24-bit ADC, HX711-class) that doesn't belong on the ring node
  itself. Node talks to it over I2C/SPI — exercises the §5 I/O
  complement and the "smart peripheral serving cooked data" pattern.
  Open questions: whether the AFE board joins the ring as its own node
  or hangs off a node's local bus; noise/grounding interaction with
  the ring wiring.

## Firmware library

- `zip` / `enumerate` views over `lib::irange`
  (`firmware/lib/range.hpp`), deferred 2026-09-26 — add when a consumer
  appears.
- Narrow size fields (`uint8_t`/`uint16_t` vs `std::size_t`) in
  datastructures to save RAM, raised 2026-09-26 — as a blanket policy,
  no: one field per container instance saves only ~tens of bytes, struct
  padding can eat it, and RV32 needs explicit zero-extension on every
  byte load, which can *grow* flash in size-heavy loops. Keep
  `std::size_t` in the generic library (`StaticVector`, `Span`).
  Revisit only measurement-driven (`nm --print-size --size-sort`,
  `-fstack-usage`) for hot, replicated structs with capacity ≤ 255 —
  there the saving multiplies.

## Tooling

- **Pin-map scarcity lint / auto-assignment** (2026-09-28, follows T9):
  `check_pin_map` verifies a hand-written binding; it does not yet
  *judge* it. A scarcity pass could warn when a pad with rare
  capabilities (the four OPA inputs, ADC channels, FT pins) is burned
  on a plain GPIO function that any pad could serve — and eventually
  solve the binding itself, PolymorphicBlocks-style (the same steal as
  T9's late binding): requests declare constraints, the solver picks
  pads, the human reviews the diff. Deferred: at 18 pads the
  assignment is a pleasant puzzle by hand and an explicit binding
  reviews better; revisit when the CI board's supervisor (RP2040, 30
  GPIO) or a second node MCU makes the table big enough to drift.
- **Fanout-driven net-label elision for generated drawings**
  (2026-09-27): when generating circuit drawings (feeds T21's survey
  and whatever renderer follows the dot dump), the highest-fanout nets
  — GND, the power rails — become net labels/symbols instead of drawn
  wires. A pareto cut on fanout keeps the drawing from degenerating
  into a ratsnest around the few nets that touch everything.
- **Parts-DB stock refresh tooling** (2026-09-28): the T7c table
  (`design/parts_db.py`) is as-of-dated snapshots by hand; a script
  that queries JLCPCB/LCSC (their parts API, or the jlcsearch mirror)
  and rewrites the `Stock` entries with fresh counts and as-of dates
  would make `check_stock`'s staleness warnings self-service. Open
  questions: rate limits and auth on JLCPCB's side, whether the script
  edits `design/parts_db.py` in place (data-as-code stays the source
  of truth) or emits an overlay.
- **Layout return-path and stitching checks** (2026-10-04): verify, from
  the routed `.kicad_pcb`, that the return path for each switching
  signal (the PHY line drivers' outputs, the watchdog charge pump,
  status LEDs) takes a reasonably direct GND route back to the
  driver's own ground pin — the current loop, not just connectivity.
  Plus a fill-stitching check: GND/other copper fills are adequately
  via-stitched, no large unstitched islands or long thin necks between
  pours. Both are EMI/loop-area concerns DRC doesn't cover.
  **Method ladder settled 2026-10-04:** rung 1 = geometric/rule-based
  checks in CI, and that's what this card builds — at our frequencies
  (800 kbit/s, MCU edge rates → spectrum ≤ ~200 MHz on cm-scale
  copper) the board is deep in the quasi-static regime, loop
  inductance dominates, and the HF return current in a plane flows
  almost directly under the trace, so "direct return path" reduces to
  geometry: plane continuous under switching traces, stitching via
  within N mm of a signal layer change, no unstitched islands.
  Example check family: series-R fanout-1 adjacent to the driver pin
  (slew limiting only works if the R sits between the driver and all
  downstream capacitance; firmware knob on top — CH32V003 GPIO speed
  grades 2/10/30 MHz, pick the slowest that meets PHY timing), plus
  the return-continuity/stitching checks above. Rung 2 = closed-form
  loop inductance / 2.5D extraction (atlc) as design input. Rung 3 =
  PEEC (FastHenry/FastCap → ngspice) for isolated hotspots later —
  first candidate the CI board's USB D+/D- pair (~90 Ω diff,
  12 Mbit/s full-speed). Rung 4 = full-wave (openEMS via gerber2ems /
  pcbmodelgen, or Palace) — not for routine use, but sanity-check a
  few of the rung-1 rules in spots against openEMS/Palace so the
  thresholds aren't pure folklore. Rung 5 = bench: DIY near-field
  H/E probes + spectrum analyzer/SDR over a running ring, TDR/NanoVNA
  for discontinuities (§6 HIL philosophy).
- **Verify BAT54S C727126 tier/stock at JLCPCB before T22**
  (2026-09-28): the parts-DB seed (`design/parts_db.py`) marks the
  BAT54S's assembly tier unverified and its stock never queried —
  `check_stock` flags exactly this. Needs a human with browser access
  to jlcpcb.com; until then a conservative filter never admits it.
- **Technology mapping onto multi-unit packages** (2026-09-27) — the
  FPGA-flow analogy: synthesis emits primitive gates, the technology
  mapper packs them onto physical cells. Applied here: a capture
  instantiates *logical* primitives (two diodes whose cathodes share a
  net), and a mapping pass binds them onto a physical multi-unit
  package (a BAT54C common-cathode pair) given the constraints —
  shared-net pattern (common-cathode pair → BAT54C, series pair →
  BAT54S, N switches + shared power → 4066-class), per-unit pin
  assignment, and the §7 multi-unit model's same-net rule for shared
  physical pins. What it would buy: fewer unique BOM lines (§6's
  $3.07 per Extended line), less board area, pack-or-don't as a
  late optimization rather than a capture-time decision. Deferred:
  capture stays **concrete and directed** — you bind the package you
  mean (the `Bat54s` class, unit subsets) and the checker verifies,
  instead of a matcher inferring it. Revisit if BOM-line pressure or
  the CI board's switch count makes hand-packing tedious; the settled
  unit model (DESIGN.md §7) is the substrate this would map onto.
- Hardware-in-the-loop CI: self-hosted runner permanently attached to the
  test board?
- Analog simulation of the PHY (line drivers, comparators, bypass
  switches) with ngspice or similar.
- **Emulate the node in QEMU with custom peripheral models**
  (2026-09-26). Feasibility analysis: the QingKe V2A core is plain
  RV32EC — no custom ALU instructions (WCH's `XW` extension only
  appears on the bigger V4 cores) — and upstream QEMU's riscv32 target
  supports both E and C, so the CPU side is free; the peripherals are
  the whole cost. No upstream CH32V003 machine in QEMU or Renode.
  Tiers of effort:
  - *Cheap:* stock qemu-system-riscv32 (virt machine) runs RV32EC code
    — CPU-level unit tests of the host-testable protocol code (§8
    factoring) with QEMU's gdb stub. No peripherals, so MMIO-touching
    code stays out.
  - *Expensive:* a real CH32V003 machine in hw/riscv — device models in
    C for PFIC (non-standard, hardware interrupt stacking), RCC, GPIO,
    TIM1/TIM2+DMA, USART, OPA, flash/ESIG. Weeks of QEMU-internals work
    plus a maintenance burden pinned to QEMU releases. Still functional,
    not cycle-accurate: cannot validate the 60-cycles/bit PHY budget
    (§2), and the analog RX chain is outside digital sim entirely.
  - *Middle path:* Renode — purpose-built for this: peripherals as C#
    models, platform as a text .repl file, multi-node wired networks
    natively (fits the ring topology), CI-oriented. No upstream CH32V003
    support found yet either, but far cheaper per peripheral than QEMU.
    HIL (§6) remains ground truth for anything timing-critical regardless.

## Related projects to mine

- **Bela platform** (bela.io) — via Bernt, 2026-09-26. Researched:
  [docs/bela-lessons-2026-09-26.md](docs/bela-lessons-2026-09-26.md).
  Key transfers: frozen-blob PHY engine (PRU⇒PIO), smart nodes with
  cooked data, hardware node-ID via solder bridges, single firmware
  image with personality by type ID, pogo-pin test jig as a first-class
  deliverable. No public HIL CI found — oparroy's hands-off-HIL goal
  goes beyond them. Open leftover: their licensing pattern (permissive
  protocol + copyleft reference + trademarked name) vs our settled
  plain MIT — revisit only if the standard/tooling framing resonates.
