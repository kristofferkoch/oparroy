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

- Home-rolled DSL vs SKiDL for design capture. A home DSL could also do:
  - Constraint checking / property verification
  - Analog simulation netlist generation (ngspice?)
  - Firmware header generation (pin maps, register defs)
  - KiCad netlist / PCB input generation
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
