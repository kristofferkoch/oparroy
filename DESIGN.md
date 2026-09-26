# DESIGN

Settled design decisions, plus §9 for decided-to-be-decided questions
that aren't yet work cards. Sections marked TBD are open.

Settled (2026-09-26):

- Project and protocol name: **oparroy**
- License: **MIT** (LICENSE added 2026-09-26, card T14 shipped)
- Design capture: **home-rolled DSL** (not SKiDL) — owns its IR, emits
  KiCad netlists, constraint checks, firmware headers, simulation netlists
- Test board: **8 ring nodes + 1 supervisor**, **full fault injection**
  (per-segment open/short, per-node power cut, clock kill — all scriptable)
- CI: **local script first** (`test-hw` style target), CI platform
  integration deferred until the board exists
- Firmware language: **freestanding C++ — no standard library**,
  zero-cost abstractions only (RAII, placement new on memory-mapped
  I/O), under an aviation-grade rule set (ruleset choice in T16)
- Tool provisioning: **nix flake** for everything non-Python (SDCC/GCC
  toolchains, KLEE/clang, ngspice, KiCad, provers); **uv** for Python
  deps — see §8
- Python tooling: **3.13, uv, ruff (strict), ty, pytest** — package
  scaffold deferred until MCU choice and DSL shape settle

## 1. Overview

oparroy is a single-wire, self-clocked ring protocol inspired by WS2812.
Closing the daisy chain into a ring makes communication bidirectional
(read + write) and provides the substrate for fault tolerance.

Design drivers, in priority order:

1. **Node cost — the central design principle.** Extremely low per-node
   cost outranks every other concern; all other drivers are achieved
   *subject to* it (sub-3-NOK MCU class, minimal external parts). Every
   feature that adds per-node parts or board area must argue for its
   existence against this driver. Note the asymmetry: **supervisor and
   test infrastructure may cost freely** — cost discipline applies to
   the replicated node, not to the one-off tooling around it.
2. **Resilience**: no single connector failure (permanent or intermittent)
   or single MCU failure partitions the ring.
3. **Repairability**: when a fault does occur, it is visually locatable
   to node and segment without instruments (§4.1).
4. **Testability**: hands-off hardware-in-the-loop testing from day one.

## 2. Physical layer

TBD.

- Line coding: TBD (WS2812-style PWM vs alternatives).
- Signaling levels / drive: TBD.
- RX via on-chip analog comparator: TBD (threshold, hysteresis).
- Bit rate target: TBD (WS2812 is 800 kbit/s; ring re-timing at each node
  relaxes jitter accumulation vs. a daisy chain — or does it? analyze).

## 3. Ring topology and bypass

TBD — deliberately **no baseline yet**. Candidate topologies (see
IDEAS.md): counter-rotating dual ring, skip-one bypass wires, per-node
switch bypass. Requirement: **single fault ⇒ ring stays connected**
(possibly degraded to a chain). The choice is expected to fall out of the
watchdog circuit design (§4) and PHY simulation.

Failure modes to design against:

- Permanent open at a connector
- Intermittent open at a connector — **open question**: protocol-level
  re-route, hardware auto-bypass, or both; deferred until PHY simulation
  exists
- Short to GND / VCC on a segment
- Dead MCU (no clock, outputs floating)
- Hung MCU (alive but not forwarding)
- MCU transmitting garbage (babbling idiot)

## 4. Node watchdog / bypass

TBD — **explore both** candidate mechanisms before picking:

- Normally-on analog switch (74LVC/TS5A-class) held open by MCU-driven
  charge pump / periodic pulse train; RC timeout re-enables bypass
- Window-watchdog supervisor IC driving the bypass mux

Requirement: RX→TX bypass is the **default state**; the MCU must
actively deassert it. Semi-passive: no firmware involvement in the
bypass path itself. Design-space exploration in the DSL + ngspice
simulation before committing.

Open questions:

- How fast must bypass engage/disengage? (Bit-level or link-level?)
- Does bypass also cut the node off from *receiving*, or only from the
  transmit path?
- Window watchdog vs simple timeout?

### 4.1 Fault detection and serviceability

Fault tolerance keeps the ring alive; detection and repairability make
failures findable and fixable (2026-09-26). Per-node status LEDs, sized
for field diagnosis without instruments:

- **Power LED** — passive, lit whenever the node is powered
- **Working LED** — MCU-driven heartbeat; off (or blinking an error
  pattern) when firmware is hung/dead. Pairs with the watchdog: bypass
  engaged ⇒ working LED dark ⇒ the failed node is visually obvious
- **Per-connector status LED** — one per ring connector, showing link
  status on that segment (activity / no-signal / error, encoding TBD).
  Points repair at the exact failed segment or connector, which is the
  whole point of the bypass wiring.

Hardware note: per-connector status should ideally be driven by the
link/PHY hardware (comparator activity detect) rather than firmware
alone, so LEDs still tell the truth when the MCU is dead. GPIO/LED
count feeds the MCU requirements in §5 and the test board in §6 — on
the board these LEDs double as test observability, but they are a
product feature, not board-only debug.

## 5. MCU platform

TBD — part **not yet chosen**. Full comparison:
[docs/mcu-research-2026-09-26.md](docs/mcu-research-2026-09-26.md).
Headline: **CH32V003** (48 MHz RISC-V, comparator routable to timer
capture, ~$0.10–0.15) is the leading sub-3-NOK node candidate;
**RP2040** ($0.70–1.00) is the leading supervisor/golden-reference
candidate — its PIO is the ideal re-timing PHY engine but it can't be
the per-node part at ~3× budget. The recalled Silabs part most
plausibly was an **EFM8BB1** (25 MHz, 2 comparators) at launch-era
pricing; no current listing is sub-3-NOK. Owner recollection still
pending; card T1 decides.

Requirements:

- Analog comparator (RX) — or a PIO/programmable engine that makes a
  comparator unnecessary
- Timer with capture or PCA for edge timing (RX decode / TX encode)
- Fast enough core/peripherals for the target bit rate
- Flash/RAM budget TBD
- Toolchain: TBD (SDCC for 8051; decision deferred until part is chosen)

Node I/O complement (2026-09-26) — peripherals a node may carry, and
what each demands of the MCU:

- Inputs: potentiometer (ADC), button / button matrix (GPIO, matrix
  scan pins), capacitive touch (dedicated capsense peripheral, or
  comparator/timer-based implementation), I2C accelerometer (I2C
  controller or bit-bang)
- Outputs: LED (GPIO/PWM), buzzer (timer/PWM)

So the MCU checklist grows by: ADC, enough GPIO for a small key matrix,
capsense capability (dedicated or constructible from the comparator +
timers), I2C, and a spare PWM channel. The test board (§6) should
populate nodes with a mix of these so protocol testing carries real
application traffic.

## 6. Test board

Decided: **8 ring nodes + 1 supervisor** (supervisor = MCU or USB bridge
that can power-cycle nodes, inject faults, collect debug UART).
**Full fault injection**: per-segment open/short switches (analog muxes
or relays), per-node power cut, clock kill — everything scriptable from
the supervisor so test runs are fully hands-off.

Prototype assembly (2026-09-26): the **first two prototype boards are
assembled by a cheap PCBA service** (Seeed Fusion class — JLCPCB is the
obvious alternative; card T17 picks). Consequence: **part selection is
inventory-driven** — prefer parts the assembler stocks; anything
outside their library costs setup fees or hand-soldering. The DSL
parts DB tracks assembler-stock status (§7).

Open: supervisor part, debug transport (UART per node? shared bus?),
board interconnect style (connectors as deliberately fragile elements —
they are the failure mode under test).

Silkscreen documentation (2026-09-26): the CI board is self-documenting
at the bench — **connector pinout voltages and test-point labels printed
on the board** (e.g. `3V3`, `5V`, `GND`, `TP12 ring-seg-3`), so probing
never requires the schematic open on a second screen. Layout-checkable
(T19): every connector and test point carries a silkscreen label.

## 7. Design-capture DSL

Decided: **home-rolled DSL** (not SKiDL). The DSL is the single source
of truth for:

- Schematic (→ KiCad netlist; layout done in KiCad)
- Constraint / property checks
- Firmware pin and register headers
- Analog simulation netlists (ngspice)

Rationale: owning the IR makes multi-target codegen and property
verification straightforward; a KiCad/SKiDL-format emitter is just one
backend. Scaffold deferred until MCU choice and DSL shape settle.

Circuit organization (2026-09-26): **functional circuits live in their
own subcircuit files** (e.g. the RC pulse watchdog is one file, one
unit), composed into boards — not drawn flat into a board schematic.
Each subcircuit carries **simulation unit tests**: standalone ngspice
testbenches asserting its contract (for the watchdog: bypass engages
within T of pulse loss, stays engaged through a single missed pulse,
does not false-trigger on line glitches). Subcircuits are the unit of
reuse, review, and test; boards are composition. Part selection note:
every part chosen must exist in the prototype assembler's inventory
(§6) — the DSL's parts DB should carry assembler-stock status per part
so constraint checks (§8) can flag unsourcable parts early.

Layout property checking (2026-09-26): the constraint role extends to
the **physical layout**. Layout is drawn in KiCad, but the DSL *audits*
it: parse the `.kicad_pcb` (S-expressions, friendly to Python) and
assert layout-level properties the schematic can't express, e.g.:

- **Bypass-path independence**: the watchdog bypass route must not
  share copper/vias with node logic between RX and TX — the physical
  embodiment of "no firmware in the bypass path" (§4)
- **Placement contracts**: per-connector status LED adjacent to its
  connector (§4.1); supervisor/debug connectors at board edge
- **Mechanical contracts**: rounded board corners (non-painful
  handling — checkable as min corner radius on the edge-cuts layer),
  mounting holes for standoffs/"legs" with correct keepouts
- **Electrical geometry**: net-class width/clearance compliance, max
  segment trace length against the cable-reach budget (T15), keepout
  respect
- KiCad's own DRC stays authoritative for manufacturability; the DSL
  checker covers *project semantics* DRC can't know about. The DSL can
  also *push* constraints the other way — emitting net classes and
  keepouts into the `.kicad_pcb` so the layout tool guides the human
  toward compliance before the audit runs.

Board-level checklist (grows as boards are designed; each item is
either a layout-checker assertion or a subcircuit):

- Power LED (§4.1) — every board, no exceptions
- **Power input protection: eFuse/crowbar subcircuit** — its own
  subcircuit file with sim unit tests (crowbar trip point, reverse
  polarity behavior, eFuse current limit) per the §7 organization
  above. Scope (decided 2026-09-26): **CI/test board only** — future
  single-node cards stay cheap and carry no such protection (central
  cost driver, §1).
- Rounded corners, mounting holes for legs (layout checker, above)
- **Board identification on silkscreen** (2026-09-26): every PCB
  carries project name (`oparroy`), PCB name, author name, date, and
  version number — checkable as required text fields on the fab/
  silkscreen layers. Version number ties the physical board to a git
  tag so HIL results are attributable to an exact design revision.

## 8. Verification strategy

Layers: DSL property checks (schematic **and physical layout**, §7),
**subcircuit simulation unit tests**
(ngspice testbenches per subcircuit file, §7), analog simulation of
integrated circuits, on-target
hardware-in-the-loop testing with fault injection. **Local script first**
(a `test-hw` style target run manually against the bench board); CI
platform integration (self-hosted runner attached to the board) deferred
until the board exists.

Firmware (2026-09-26): **rigorous and statically checked from the
start** — strict compiler warnings, static analysis, and symbolic
execution (KLEE-class provers) wired in from the first firmware commit,
not retrofitted. Language: **freestanding C++, no standard library**
(`-ffreestanding -nostdlib`, no exceptions, no RTTI, no heap unless
explicitly carved out) — the zero-cost subset used deliberately: RAII
for resource/lock ownership, placement `new` on memory-mapped I/O for
type-safe register blocks, `constexpr` for pin/config tables, templates
where they erase per-node cost. **Exceptions policy** (examined
2026-09-26, retained: `-fno-exceptions`): the unwinder + personality
routine + unwind tables cost ~10–40 KB flash — more than the entire
16 KB CH32V003; `throw` allocates (heap or emergency buffer) in a
system that otherwise never allocates; unwinding time is
data-dependent, breaking the bounded-latency story the PHY needs and
the WCET analysis aviation-grade rule sets demand (JSF AV bans
exceptions outright); and landing-pad control flow taxes KLEE and
coverage. Replacement idiom: `expected<T,E>`-style result types +
`[[nodiscard]]` — error paths stay visible in the type system and free
at runtime. Revisit only if the node MCU grows by an order of
magnitude.

Foundation library (2026-09-26): our freestanding "unstandard" library
is **modeled on SerenityOS's AK** — the library that proved you can
have modern C++ ergonomics without exceptions:

- **`ErrorOr<T>`** as the universal fallible return type; our
  `expected<T,E>` idiom above *is* this
- **Fallible APIs everywhere allocation can fail** — AK's
  `try_append`/`try_emplace` returning `Error` instead of throwing or
  aborting; on oparroy nodes most storage is static, but the
  convention still rules: anything that *can* fail returns, it never
  traps silently
- **`TRY(...)` propagation macro** (AK's) as the exception-free error
  plumbing — reads like exceptions, compiles to branches
- **Ownership types** (AK's `OwnPtr`/`NonnullOwnPtr`/`FixedArray`)
  adapted to static arenas instead of a heap
- **`VERIFY`/assert macros** with a project-defined failure hook —
  on a node, assertion failure policy ties into the watchdog story
  (§4): deliberate bypass-engage, not a hung loop

Not copied from AK: anything POSIX-flavored, hidden allocation,
infinite growth. The node library's spine is fixed-capacity containers
with explicit `try_` growth. Rule set: **aviation-grade** (picked in
T16 — candidates JSF AV C++, MISRA C++:2023, AUTOSAR C++14).
Practical consequences:

- Firmware must stay **clang-compilable to LLVM bitcode** (KLEE's input)
  even if the target toolchain is GCC — keep target-specific code
  behind thin shims so protocol and state-machine logic builds for the
  host analyzer. (The freestanding subset also keeps the bitcode clean:
  no libstdc++ exception machinery for KLEE to choke on.)
- **Toolchain consequence (feeds T1):** freestanding C++ needs a real
  C++ compiler — GCC/clang. SDCC is C-only, so this decision all but
  rules out 8051-class parts (EFM8/STC) and favors RISC-V/ARM
  (CH32V003, RP2040-class).
- Protocol logic is factored host-testable (parsers, state machines,
  fault-handling decisions) so KLEE harnesses and property tests can
  reach it without the MCU.
- KLEE harnesses target the protocol invariants first: frame
  encode/decode round-trips, ring state-machine progress, behavior
  under injected garbage (the babbling-idiot case, §3).

Test philosophy (2026-09-26): **SQLite's doctrine, plus symbolic
verification on top.** The SQLite project is the reference for what
"rigorously tested" means for a small, everywhere-deployed C codebase;
the parts that transfer to oparroy firmware and the DSL:

- **Coverage measured on the release build, not a test build** —
  SQLite enforces 100% branch (MC/DC-style) coverage of the *deployed*
  configuration, so tests exercise what actually ships. For oparroy:
  coverage of the freestanding build, and on-target coverage
  measurements from HIL runs where feasible.
- **Fault injection at every boundary** — SQLite simulates OOM and I/O
  errors at every call site that can fail. oparroy's equivalents:
  bus/line errors, timer glitches, dropped/partial frames, watchdog
  timeouts, brown-outs — injected through the host shims so every
  failure path is reachable in test.
- **Structure-aware fuzzing as a first-class harness** — SQLite runs
  dbsqlfuzz continuously. oparroy: libFuzzer/AFL++ harnesses on the
  frame parser and ring state machine (alongside, not instead of, the
  KLEE harnesses — fuzzing finds what the prover's assumptions miss,
  the prover proves what fuzzing can't reach).
- **Multiple independent test harnesses** — SQLite keeps four; a bug
  found by one that another missed gets analyzed for why. oparroy:
  unit tests, KLEE, fuzzing, ngspice subcircuit sims, HIL — diversity
  is deliberate.
- Symbolic verification (KLEE) is the layer SQLite *doesn't* have; it
  complements the above by exhausting small state spaces (frame
  grammar, ring state machine) rather than sampling them.

Tool provisioning (2026-09-26): **nix flake + uv, each in its lane**.
Exotic tools will accumulate (provers, cross-compilers, ngspice, KiCad,
SDCC), so:

- The **flake dev shell** provides every non-Python tool, pinned by
  `flake.lock` — including `uv` itself. Same flake drives CI, so local
  and CI toolchains are identical by construction.
- **uv** owns the Python side alone: `pyproject.toml`/`uv.lock`, the
  project venv, and its own standalone CPython builds (static, run fine
  under nix — no nixpkgs Python in the loop). Rule: Python packages
  come *only* from uv; everything else comes *only* from nix.

## 9. Open design questions

Decided-to-be-decided problems that aren't yet work cards (the card that
resolves each is in KANBAN.md):

- **Bypass topology** (§3) — dual ring vs skip-one vs per-node switch;
  waits on the watchdog exploration (T4) and PHY simulation (T5).
  Card: T2.
- **Intermittent connector faults** (§3) — protocol re-route vs hardware
  auto-bypass vs both; deferred until PHY simulation exists. Card: T13.
- **Watchdog mechanism** (§4) — analog switch + charge pump vs
  supervisor IC; explore both in simulation first. Card: T4.
- **MCU part** (§5) — sub-3-NOK Silabs 8051 candidate to be recalled /
  identified vs the field, RP2040 PIO in the running. Card: T1.
- **Line coding and bit rate** (§2) — WS2812-style PWM vs alternatives;
  jitter accumulation under per-node re-timing. Card: T3.
- **Supervisor and debug transport** (§6) — supervisor part, per-node
  UART vs shared bus, connector style. Card: T10.
- **Cable reach** (§2) — maximum segment length unamplified, and with
  an amplifier/re-driver node in the segment; depends on line coding,
  drive strength, comparator sensitivity, and cable characteristics.
  Answered by simulation first, then measured on the test board.
  Card: T15.
