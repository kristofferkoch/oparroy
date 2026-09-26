# IDEAS

Loose ideas to revisit. Append; never lose them. Promote into
`KANBAN.md` (a card in Next/Backlog) or `DESIGN.md` when they become
real work — **move**, don't copy. Reference, don't duplicate.

## Protocol

- WS2812-style self-clocked single-wire signaling, but closed into a ring
  so every node can transmit and receive.
- Line coding options: PWM (T0H/T1H like WS2812), pulse-distance, or
  something comparator-friendly.
- Frame format, addressing, arbitration: TBD. Ring gives a natural
  token/slot structure.

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

- Silabs 8051 (exact part TBD — was < 3 NOK, fast core, analog
  comparators on-chip).
- Comparators for RX: threshold selection, hysteresis, glitch filtering.
- Test board: multiple nodes + on-board debug/supervision (a supervisor
  MCU or SBC?) so tests run hands-off.
- Fault-injection hardware on the test board (switches to open/short
  links, kill MCUs) so CI can exercise the failure modes.

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
