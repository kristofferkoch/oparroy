# oparroy

A read+write, fault-tolerant ring communication protocol for **extremely
cheap** microcontroller nodes, inspired by the WS2812 single-wire
protocol.

Unlike WS2812's write-only daisy chain, oparroy closes the chain into a
ring so nodes can both send and receive. The physical layer is designed
so that **no single point of failure** — a broken connector (permanent
or intermittent), or a dead/hung microcontroller — partitions the ring:

- Bypass wiring routes around failed interconnects.
- Each node has a semi-passive hardware watchdog that bypasses the
  node's RX→TX path unless the MCU actively keeps the bypass disabled.
- Status LEDs make faults visually locatable to node and segment
  without instruments.

**Extremely low node cost is the central design principle** (sub-3-NOK
MCU class); every other driver — resilience, repairability,
testability — is achieved subject to it. Supervisor and test
infrastructure, by contrast, may cost freely.

## Hardware direction

- **Node MCU**: leading candidate CH32V003 (48 MHz RISC-V, on-chip
  comparator routable to timer capture, ~$0.10–0.15); decision pending
  — see [docs/mcu-research-2026-09-26.md](docs/mcu-research-2026-09-26.md).
- **Supervisor**: RP2040 — its PIO is the ideal re-timing PHY engine
  and golden-reference transceiver.
- **Node I/O**: potmeter, buttons/matrix, capacitive touch, I2C
  accelerometer, LEDs, buzzer — nodes are smart peripherals serving
  cooked data (Bela/Trill pattern, see
  [docs/bela-lessons-2026-09-26.md](docs/bela-lessons-2026-09-26.md)).
- **Test board**: 8 ring nodes + supervisor, full fault injection
  (per-segment open/short, per-node power cut, clock kill), everything
  scriptable for hands-off hardware-in-the-loop testing. First two
  prototypes assembled by a cheap PCBA service; part selection is
  inventory-driven.

## Firmware direction

- **Freestanding C++, no standard library** — RAII, placement `new` on
  memory-mapped I/O, `constexpr` config; no exceptions/RTTI/heap.
- Foundation library modeled on **SerenityOS's AK**: `ErrorOr<T>`,
  fallible `try_*` APIs, `TRY` propagation, fixed-capacity containers.
- **Verification from the first commit**, SQLite doctrine + symbolic
  execution: KLEE harnesses, libFuzzer/AFL++, fault-injection shims,
  coverage on the release build, aviation-grade C++ rule set (JSF AV /
  MISRA C++ / AUTOSAR candidates).

## Tooling

- **Design capture is code**: a home-rolled Python DSL is the single
  source of truth — emits KiCad netlists, constraint checks, firmware
  headers, and ngspice netlists. KiCad for layout only. Functional
  circuits live in subcircuit files, each with simulation unit tests.
- **nix flake** provides everything non-Python (compilers, KLEE/clang,
  ngspice, KiCad, uv itself), pinned by `flake.lock` — `nix develop`
  enters the shell (`.envrc` provided for direnv users); **uv** owns
  Python alone (3.13, ruff strict, ty, pytest).

## Repository layout

| Path          | Contents                                              |
| ------------- | ----------------------------------------------------- |
| `AGENTS.md`   | Doc-split and writing conventions for agents          |
| `IDEAS.md`    | Not-yet-planned ideas (append-only stash)             |
| `DESIGN.md`   | Settled design decisions + open design questions      |
| `KANBAN.md`   | Single home for planned work (cards, Next/Backlog)    |
| `README.md`   | This file                                             |
| `flake.nix`   | Pinned dev shell: all non-Python tools (DESIGN.md §8) |
| `docs/`       | Reference documents (research reports, sub-designs)   |
| `LICENSE`     | MIT, copyright 2026 Kristoffer Koch                   |

Doc conventions follow the IDEAS → KANBAN/DESIGN graduation model:
stray thoughts live in IDEAS.md, planned work in KANBAN.md cards,
settled decisions in DESIGN.md. See `AGENTS.md` §Documentation.

## Status

Documentation-first phase: protocol, circuits, and tooling are designed
and verified on paper/in simulation before boards exist. Current work
is tracked as cards in `KANBAN.md`; the MCU decision (T1) gates most of
the dependency graph.
