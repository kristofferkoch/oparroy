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

- **Node MCU: CH32V003F4P6** (decided 2026-09-26, card T1) — 48 MHz
  RV32EC in TSSOP-20, on-chip comparator routable to timer capture,
  ~$0.14 @4k. Clocked from the factory-trimmed internal HSI — no
  crystal; the ratio-metric PHY makes absolute clock accuracy
  irrelevant. Rationale:
  [docs/mcu-research-2026-09-26.md](docs/mcu-research-2026-09-26.md);
  extracted part facts: `datasheets/CH32V003/notes/`.
- **Supervisor: RP2040** — its PIO is the re-timing PHY engine and
  golden-reference transceiver; on the test board its PIO also runs as
  a logic analyzer on the instrumented boundary node (DESIGN.md §6).
- **PHY** (decided 2026-09-26, card T3): WS2812-compatible duty-coded
  PWM cells with ratio-metric decode at an 800 kbit/s anchor,
  comparator RX + DMA, per-bit cut-through re-timing, positional
  addressing, and the frame gap as a ring-wide vsync latch
  (DESIGN.md §2; analysis:
  [docs/phy-analysis-2026-09-26.md](docs/phy-analysis-2026-09-26.md)).
- **Node I/O**: potmeter, buttons/matrix, capacitive touch, I2C
  accelerometer, LEDs, buzzer — nodes are smart peripherals serving
  cooked data (Bela/Trill pattern, see
  [docs/bela-lessons-2026-09-26.md](docs/bela-lessons-2026-09-26.md)).
- **Test board**: 8 ring nodes + supervisor, full fault injection
  (per-segment open/short, per-node power cut, clock kill), everything
  scriptable for hands-off hardware-in-the-loop testing. Doubles as
  the **demonstrator**: some nodes carry human-facing I/O
  (potentiometer, buttons, LEDs, buzzer), each input overridable by
  the supervisor so scripted runs stay hands-off (DESIGN.md §6).
  4-layer, self-documenting silkscreen. Prototypes assembled by
  **JLCPCB Economic PCBA** (decided 2026-09-26, card T17); part
  selection is inventory-driven — minimize unique Extended BOM lines.

## Firmware direction

- **Freestanding C++, no standard library** — RAII, placement `new` on
  memory-mapped I/O, `constexpr` config; no exceptions/RTTI/heap.
- Foundation library modeled on **SerenityOS's AK**: `ErrorOr<T>`,
  fallible `try_*` APIs, `TRY` propagation, fixed-capacity containers.
- **Verification from the first commit**, SQLite doctrine + symbolic
  execution: KLEE harnesses, libFuzzer/AFL++, fault-injection shims,
  coverage on the release build, and the project-owned coding standard
  in `code-std.md` (borrows from JSF AV / MISRA / AUTOSAR / CERT).

## Tooling

- **Design capture is code**: a home-rolled Python DSL is the single
  source of truth — emits KiCad netlists, constraint checks, firmware
  headers, and ngspice netlists. KiCad for layout only, with the DSL
  auditing the physical layout (bypass-path copper independence,
  placement and mechanical contracts). Functional circuits live in
  subcircuit files, each with simulation unit tests.
- **Datasheets are extracted, not just stored**: `datasheets/<PART>/`
  holds vendor PDFs plus LLM-readable markdown sidecars (facts,
  per-peripheral notes, quirks) — see `datasheets/README.md`.
- **Meson + ninja** build the firmware (DESIGN.md §8, T20): one build
  dir per toolchain, freestanding flag set in `meson.build`.
  - host (clang; host objects + LLVM bitcode for KLEE):
    `meson setup build/host --native-file meson/native/clang.ini`
  - CH32V003 (RV32EC objects):
    `meson setup build/rv32ec --cross-file meson/cross/rv32ec.ini`
  - then `meson compile -C build/<dir>`; the reproducibility gate
    `ninja -C build/host check-reproducible` builds every
    configuration twice and compares artifact hashes.
- **nix flake** provides everything non-Python (riscv/arm cross GCC,
  clang 19 + KLEE, AFL++, ngspice, KiCad, uv itself), pinned by
  `flake.lock` — `nix develop` enters the shell (`.envrc` provided for
  direnv users); **uv** owns Python alone (3.13, ruff strict, ty,
  pytest).
- **Pre-commit hooks** (`pre-commit install`, T16b): clang-format,
  clang-tidy (replaying the host build's `compile_commands.json`), and
  the markdown pipeline
  (mdformat + markdownlint-cli2 + lychee link checks) — cheap checks
  only, ~2 s warm. Hooks are `language: system` against the
  nix-pinned tools, so the flake stays the single tool source.

## Repository layout

| Path                       | Contents                                                |
| -------------------------- | ------------------------------------------------------- |
| `AGENTS.md`                | Doc-split and writing conventions for agents            |
| `IDEAS.md`                 | Not-yet-planned ideas (append-only stash)               |
| `DESIGN.md`                | Settled design decisions + open design questions        |
| `KANBAN.md`                | Single home for planned work (cards, Next/Backlog)      |
| `code-std.md`              | Project-owned C++ coding standard (living)              |
| `README.md`                | This file                                               |
| `flake.nix` + `flake.lock` | Pinned dev shell: all non-Python tools (DESIGN.md §8)   |
| `meson.build` + `meson/`   | Firmware build: flag set, native/cross toolchain files  |
| `.envrc`                   | direnv hook into the flake shell                        |
| `.pre-commit-config.yaml`  | Hook wiring; tools nix-pinned, `language: system`       |
| `firmware/`                | Node/supervisor firmware (toolchain smoke build so far) |
| `scripts/`                 | Build + pre-commit scripts (POSIX sh)                   |
| `docs/`                    | Reference documents (research reports, sub-designs)     |
| `datasheets/`              | Vendor PDFs + extracted markdown sidecars per part      |
| `LICENSE`                  | MIT, copyright 2026 Kristoffer Koch                     |

Doc conventions follow the IDEAS → KANBAN/DESIGN graduation model:
stray thoughts live in IDEAS.md, planned work in KANBAN.md cards,
settled decisions in DESIGN.md. See `AGENTS.md` §Documentation.

## Status

Documentation-first phase: protocol, circuits, and tooling are designed
and verified on paper/in simulation before boards exist. The MCU split
(T1), PHY baseline (T3), PCBA vendor (T17), and dev shell (T16a) are
settled; current work is tracked as cards in `KANBAN.md` — the PHY
simulation (T5) and watchdog/bypass exploration (T4) gate the bypass
topology and test-board design.
