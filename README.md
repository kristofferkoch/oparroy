# oparroy

A read+write, fault-tolerant ring communication protocol for **extremely
cheap** microcontroller nodes, inspired by the WS2812 single-wire
protocol.

Unlike WS2812's write-only daisy chain, oparroy closes the chain into a
ring so nodes can both send and receive. The physical layer is designed
so that **no single point of failure** — a broken connector (permanent
or intermittent), or a dead/hung microcontroller — partitions the ring:

- The ring is dual: every segment carries two counter-rotating data
  rings with symmetric rebroadcast, so any single fault leaves every
  node reachable (DESIGN.md §3).
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

- **Node MCU: CH32V003F4P6** (decided 2026-09-26) — 48 MHz
  RV32EC in TSSOP-20, on-chip comparator routable to timer capture,
  ~$0.14 @4k. Clocked from the factory-trimmed internal HSI — no
  crystal; the ratio-metric PHY makes absolute clock accuracy
  irrelevant. Rationale:
  [docs/mcu-research-2026-09-26.md](docs/mcu-research-2026-09-26.md);
  extracted part facts: `datasheets/CH32V003/notes/`.
- **Supervisor: RP2040** — its PIO is the re-timing PHY engine and
  golden-reference transceiver; on the test board its PIO also runs as
  a logic analyzer on the instrumented boundary node (DESIGN.md §6).
- **PHY** (decided 2026-09-26): WS2812-compatible duty-coded
  PWM cells with ratio-metric decode at an 800 kbit/s anchor,
  comparator RX + DMA, per-bit cut-through re-timing, positional
  addressing, and the frame gap as a ring-wide vsync latch
  (DESIGN.md §2; analysis:
  [docs/phy-analysis-2026-09-26.md](docs/phy-analysis-2026-09-26.md)).
- **Segment interconnect** (DESIGN.md §2.1, §3): 2x6-pin connectors
  carry both counter-rotating data rings plus power — a single 3.3 V
  rail that is both the signaling rail and node power, and a raw
  5–18 V rail for payloads with their own buck. On 3M 3365 ribbon,
  segments reach **10 m unamplified**; the 470 Ω TX series resistor,
  not the cable, sets the limit (simulation:
  [docs/cable-reach-2026-09-28.md](docs/cable-reach-2026-09-28.md)).
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
  **JLCPCB Economic PCBA** (decided 2026-09-26); part
  selection is inventory-driven — minimize unique Extended BOM lines.

## Firmware direction

- **Freestanding C++, no standard library** — RAII, placement `new` on
  memory-mapped I/O, `constexpr` config; no exceptions/RTTI/heap.
- Foundation library modeled on **SerenityOS's AK**, landed in
  `firmware/lib/`: `ErrorOr<T>` with `TRY` propagation and fallible
  `try_*` APIs, `VERIFY` with a target failure hook, fixed-capacity
  `StaticVector`/`Span`, and a `StaticArena` slot pool.
- **Ring protocol core** in `firmware/protocol/` — bit cells and
  node/ring forwarding logic (DESIGN.md §2) — proven by **KLEE**
  symbolic-execution harnesses and **libFuzzer** harnesses whose seed
  corpora double as the meson test suite; branch coverage is measured
  on the release build (`scripts/coverage-release`).
- The node pin map is captured in the DSL — 17 of 18 CH32V003 GPIO
  assigned with a budget check — and emits `firmware/node/pins.hpp`
  directly (DESIGN.md §7).
- All of it under the project-owned coding standard in `code-std.md`
  (borrows from JSF AV / MISRA / AUTOSAR / CERT), statically checked
  from the first commit (DESIGN.md §8).

## Tooling

- **Design capture is code**: the home-rolled Python DSL
  (`src/oparroy/dsl/`, DESIGN.md §7) is the single source of truth —
  an IR with subcircuit composition (ports, port arrays, bundles,
  multipacking, component sockets), a validation pass (limit ranges,
  interval containment, waivers as data), and emitters for KiCad
  netlists, ngspice simulation netlists, and firmware pin headers.
  Footprint assignment and annotation/back-annotation are explicit,
  repeatable stages between capture and pcbnew, so emission is not a
  one-shot export. The parts DB carries assembler-stock status
  (inventory-driven selection), and a `.kicad_pcb` layout property
  checker audits the physical layout (stackup, trace budgets,
  bypass-path copper independence, mechanical contracts). KiCad is
  used for layout only. Circuit captures live in `design/` — the full
  node board is captured (CH32V003 + PHY front-end + charge-pump
  watchdog + status LEDs + segment connectors) — with ngspice benches
  in `circuits/` run via `scripts/sim-run`.
- **Datasheets are extracted, not just stored**: `datasheets/<PART>/`
  holds vendor PDFs plus LLM-readable markdown sidecars (facts,
  per-peripheral notes, quirks) — see `datasheets/README.md`.
- **Meson + ninja** build the firmware (DESIGN.md §8): one build
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
  pytest): `uv sync`, then `uv run pytest` / `uv run ruff check` /
  `uv run ty check`.
- **Pre-commit hooks** (`pre-commit install`): clang-format,
  clang-tidy (replaying the host build's `compile_commands.json`), and
  the markdown pipeline
  (mdformat + markdownlint-cli2 + lychee link checks) — cheap checks
  only, ~2 s warm. Hooks are `language: system` against the
  nix-pinned tools, so the flake stays the single tool source.
- **CI** (`.github/workflows/ci.yml`): GitHub Actions runs every gate
  — pytest, firmware host build + unit tests, KLEE proofs, bounded
  fuzz runs, ngspice benches, the rv32ec cross build, the
  reproducibility gate, and the pre-commit suite — inside the nix dev
  shell, so CI exercises byte-identical tools to a laptop.

## Repository layout

| Path                         | Contents                                                       |
| ---------------------------- | -------------------------------------------------------------- |
| `AGENTS.md`                  | Doc-split and writing conventions for agents                   |
| `IDEAS.md`                   | Not-yet-planned ideas (append-only stash)                      |
| `DESIGN.md`                  | Settled design decisions + open design questions               |
| `KANBAN.md`                  | Single home for planned work (cards, Next/Backlog)             |
| `code-std.md`                | Project-owned C++ coding standard (living)                     |
| `README.md`                  | This file                                                      |
| `flake.nix` + `flake.lock`   | Pinned dev shell: all non-Python tools (DESIGN.md §8)          |
| `pyproject.toml` + `uv.lock` | Python side: the DSL package (ruff strict, ty, pytest)         |
| `src/oparroy/`               | Design-capture DSL package (`dsl/`: IR, checks, emitters)      |
| `design/`                    | DSL circuit captures: node board, pin map, parts DB seed       |
| `circuits/`                  | ngspice benches: PHY segment, watchdog, cable reach            |
| `tests/`                     | Python tests (pytest) + golden netlists, `.kicad_pcb` fixtures |
| `meson.build` + `meson/`     | Firmware build: flag set, native/cross toolchain files         |
| `.envrc`                     | direnv hook into the flake shell                               |
| `.pre-commit-config.yaml`    | Hook wiring; tools nix-pinned, `language: system`              |
| `.github/workflows/`         | CI: every gate inside the nix shell                            |
| `firmware/`                  | Node/supervisor firmware: foundation lib, ring protocol        |
| `scripts/`                   | Build, sim/proof/fuzz, coverage + pre-commit scripts (sh)      |
| `docs/`                      | Reference documents (research reports, sub-designs)            |
| `datasheets/`                | Vendor PDFs + extracted markdown sidecars per part             |
| `LICENSE`                    | MIT, copyright 2026 Kristoffer Koch                            |

Doc conventions follow the IDEAS → KANBAN/DESIGN graduation model:
stray thoughts live in IDEAS.md, planned work in KANBAN.md cards,
settled decisions in DESIGN.md. See `AGENTS.md` §Documentation.

## Status

The design-automation pipeline is landed end-to-end: the DSL captures
the full node board, validates it, and emits KiCad and ngspice
netlists, the firmware pin header, and layout constraint skeletons;
simulation benches cover the PHY, the charge-pump watchdog, and cable
reach. On the firmware side the foundation library and the
ring-protocol core are in place under KLEE/fuzz/coverage verification,
and CI runs every gate. No boards exist yet: next up is KiCad layout
of the node board, which unblocks the 8-node test board and the
long-cable bench work. Current work is tracked as cards
in `KANBAN.md`.
