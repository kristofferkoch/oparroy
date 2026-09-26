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

- Bypass wires so a single broken/intermittent connector does not
  partition the ring. Candidate topologies:
  - Counter-rotating dual ring
  - Skip-one (node N → N+2) bypass wires
  - Per-node relay/analog-switch bypass only
- Intermittent connector failures: protocol-level retry/re-route, or
  purely hardware bypass?
- Per-node semi-passive watchdog: RX→TX bypass is *enabled by default*;
  the MCU must actively hold it disabled. Dead/hung MCU ⇒ node becomes a
  wire. Candidate implementations: normally-on analog switch discharged by
  MCU, RC + comparator, supervisor IC.

## Hardware

- Comparators for RX: threshold selection, hysteresis, glitch filtering.

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

## Tooling

- Home-rolled DSL vs SKiDL for design capture. A home DSL could also do:
  - Constraint checking / property verification
  - Analog simulation netlist generation (ngspice?)
  - Firmware header generation (pin maps, register defs)
  - KiCad netlist / PCB input generation
- Hardware-in-the-loop CI: self-hosted runner permanently attached to the
  test board?
- Analog simulation of the PHY (line drivers, comparators, bypass
  switches) with ngspice or similar.

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
