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
- MCU (2026-09-26, card T1): node = **CH32V003F4P6** (TSSOP-20),
  supervisor = **RP2040**; toolchains GCC riscv + GCC arm, clang host
  build retained for KLEE (§8)
- Node time base (2026-09-26): **internal HSI RC, no crystal** — §5
- PHY (2026-09-26, card T3): ratio-metric duty-coded PWM, 800 kbit/s
  anchor, comparator RX + DMA, per-bit cut-through re-timing — §2
- PCBA (2026-09-26, card T17): prototypes assembled by **JLCPCB**
  (Economic PCBA); fallback for unstocked parts is PCBWay
  partial-turnkey (§6)
- Firmware build system (2026-09-26): **Meson + ninja** — §8

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
1. **Resilience**: no single connector failure (permanent or intermittent)
   or single MCU failure partitions the ring.
1. **Repairability**: when a fault does occur, it is visually locatable
   to node and segment without instruments (§4.1).
1. **Testability**: hands-off hardware-in-the-loop testing from day one.

## 2. Physical layer

Decided (2026-09-26, card T3, against the CH32V003's peripherals; full
analysis:
[docs/phy-analysis-2026-09-26.md](docs/phy-analysis-2026-09-26.md)).
Final bit rate and break length to be confirmed by T5 simulation and
bench measurement.

- **Line coding: WS2812-style duty-coded PWM cells with ratio-metric
  decode.** Fixed bit cell, high-then-low; `0` = short high pulse
  (~1/3 cell, T0H ≈ 0.40 µs), `1` = long high pulse (~2/3 cell,
  T1H ≈ 0.80 µs). The spec is the *ratio* — high-time/period against
  the cell midpoint — not absolute times: the coding tolerates ~±25 %
  node-clock error, so HSI-only nodes (±2.2 % worst case, no crystal —
  §5) sit an order of magnitude inside budget. The wire signal stays
  WS2812-compatible, so COTS decoders, test gear, and RP2040 PIO
  reference code work unmodified.
- **Bit rate: 800 kbit/s anchor** (1.25 µs cell = 60 timer ticks at
  48 MHz; capture resolution 20.8 ns). The rate is a free parameter —
  the ceiling is comparator response and cable reach (T15), not the
  timers — but at 800 k the OPA (12 MHz GBW, 7.7 V/µs) is nowhere near
  the bottleneck and COTS WS2812 tooling applies. Frame/latch marker:
  line-low break, ≥ 50 µs baseline (WS2812's reset is the upper
  reference; MCU nodes may go shorter once T5/bench confirm — the
  vsync semantics below ride on the break either way).
- **Signaling: 3.3 V single-ended**, push-pull at VDD per segment,
  idle low. RX threshold = VDD/2 divider on an OPA negative input. The
  OPA has no documented hysteresis: glitch rejection comes from the
  TIM2 input digital filter (ICxF) plus ratio-decode margins, not
  analog feedback; T5's simulation either confirms this or adds one
  feedback resistor (OPO = PD4 is free for it).
- **RX path:** OPA comparator routed *internally* to TIM2 CH1 — no
  GPIO spent on the comparator output. TIM2 PWM-input mode (CH1+CH2
  pair, hardware counter reset) captures per-bit period and high-time;
  DMA channels 5/7 stream captures into an SRAM ring buffer. Per-bit
  ISRs are ruled out: 60 cycles/bit at 800 kbit/s leaves nothing after
  PFIC entry; decode runs per burst, amortized ~10 cycles/bit
  (datasheets/CH32V003/notes: opa.md, timers.md, dma.md).
- **TX path:** TIM1 PWM + DMA streaming compare values against a fixed
  cell period (fallback: SPI + DMA with bit-to-symbol encoding, which
  frees TIM1 for application PWM per §5's I/O complement). TIM1's
  brake input is reserved as a hardware TX-kill for the watchdog /
  babbling-idiot story (§3, §4).
- **Re-timing: per-bit cut-through regeneration, slot rewrite on the
  fly** (2026-09-26: user decision, superseding the initial
  store-and-forward baseline). Every node decodes upstream bits and
  re-synthesizes the TX waveform from its own timer — snapped to
  nominal T0H/T1H — after a small, bounded pipeline delay, so decode
  jitter is per-hop (~one timer tick), never cumulative
  (*regeneration*, not topology, is what bounds jitter; WS2812 chains
  reshape too, but oparroy's re-timing is explicit and
  firmware-controlled, not entrusted to a chip's internal reshaping).
  A node streams the frame through bit-by-bit and only intercepts its
  own slot — reads command bits, substitutes telemetry bits — as it
  passes: the WS2812/EtherCAT shape. Ring circulation ≈ one frame
  time + N×pipeline delay (~0.6 ms, ~1.6 kHz full-ring update at
  8 nodes) instead of N×frame-time. **Buffering policy** (2026-09-26):
  the pipeline is deep enough to relax the CPU budget — order 8–16
  cells, processed in bursts off DMA half-transfer interrupts — and
  hard-bounded so ring DMA buffers stay **≤ 256 B of the 2 KB SRAM**,
  statically allocated (≈8 B/cell RX + 2 B/cell TX): some buffering to
  buy CPU slack, never enough to become a RAM problem. The node
  locates its slot by counting bits from the frame gap (position =
  address, below); ENUM frames are pre-sized so stamping is a slot
  rewrite, never an insertion. The trade: per-hop frame filtering is
  lost — a corrupt frame is already downstream before a CRC could
  reject it — so containment moves to illegal-cell detection (period
  outside 0.9–1.6 µs ⇒ stop regenerating, force the line idle), the
  TIM1-brake TX-kill and hardware bypass (§3, §4), and supervisor-side
  CRC/sequence checks (feeds T13). Fallback rung: if the per-bit loop
  doesn't close timing on-target, degrade to store-and-forward (T11
  decides with measurements). Closure discipline: the supervisor is
  the only frame originator and drainer; echo mismatch ⇒ fault.
- **Addressing: positional, discovered — no solder bridges, no
  provisioning step.** Position in the ring *is* the address. The
  supervisor enumerates with one circulation of an ENUM frame that
  each node stamps with its factory 96-bit UNIID (ESIG — see
  datasheets/CH32V003/notes/flash-option-bytes.md) plus a type byte;
  the position ↔ UNIID map rebuilds automatically when a node is
  replaced. Solder-bridge IDs (Trill-style, bela-lessons §2) lose on
  pin budget (≥2 GPIO on an 18-GPIO part) and per-node parts — the §1
  cost driver. One firmware image, personality by type byte in flash
  (card T11).
- **Telemetry: slotted in the circulating frame, not polled.** Each
  node writes its own slot as the frame passes, with inputs sampled at
  the vsync latch (below) — synchronous sampling in the ring's
  timebase (bela-lessons §1), deterministic latency (~1.6 kHz
  full-ring update at 8 nodes, cut-through — see re-timing above), no
  poll round-trips. The frame sequence counter is the timestamp.
  Frame format detail is T11 scope.
- **Ring-wide latch: the frame gap is a vsync — WS2812's "global
  shutter" in both directions** (2026-09-26). The line-low break that
  marks frame start drives two synchronized actions at every node:
  (a) **apply** the command outputs received in the previous frame,
  from a double buffer — LED/buzzer state never changes mid-frame, so
  patterns don't tear across positions; (b) **sample** inputs, so
  every telemetry slot in frame k holds values from the same latch
  instant L_k, tagged by the frame sequence counter. Effect is
  simultaneous even though data delivery is positional: the break
  itself propagates around the ring, so inter-node skew = accumulated
  pipeline delay, ≤ N×depth ≈ 160 µs at the baseline — bounded,
  sub-perceptual for human interface, tight enough for correlated
  multi-node sensing (button chords, gestures, accelerometer arrays).
  Cost: one double-buffer stage per node (bytes, inside the 256 B
  ring-buffer cap); the break detector already exists to reset the bit
  counter, so the latch event is free.

Rejected codings (2026-09-26; analysis doc §1): pulse-distance
(data-dependent slot timing, longer average cell); Manchester (doubles
the transition rate, no benefit for comparator RX); USART-async (two
HSI ends bust the async sampling budget — kept as fallback only if
bench testing kills the comparator-RX path).

Open: analog hysteresis need (T5 sim), drive strength vs cable (T15),
exact frame format (T11).

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

Decided (2026-09-26, card T1; PCBA verification under card T17):

- **Node MCU: CH32V003F4P6** (WCH RV32EC @ 48 MHz, **TSSOP-20**) —
  ~$0.29 at prototype qty, $0.137 @4k (LCSC **C5187096**, JLCPCB
  Extended, ~9k in stock 2026-09-26). Its OPA comparator routes to TIM2
  CH1 capture; two capture-capable timers + DMA. TSSOP-20 over the
  QFN-20 variant (F4U6): avoids JLCPCB's per-board X-ray fee for
  leadless packages and stays hand-reworkable.
- **Supervisor MCU: RP2040** ($0.70–1.00, LCSC **C2040**, JLCPCB
  Extended) — PIO is the re-timing PHY engine and golden-reference
  transceiver for characterizing the CH32V003's analog-RX path; also
  ring supervisor on the test board (§6). Unavoidably QFN-56, so the
  X-ray fee is budgeted. Explicitly **not** the node part at ~3× the
  node budget (§1).
- **Toolchains**: GCC riscv (ch32v003fun-class SDK) for the node, GCC
  arm for the supervisor; clang/LLVM-bitcode host build retained for
  KLEE (§8). All provisioned by the nix flake.
- **Node time base** (2026-09-26, T3 analysis): **internal HSI 24 MHz
  RC + PLL ×2 = 48 MHz — no crystal on the node.** HSI is
  factory-trimmed to −1.2/+1.6 % over 0–70 °C ([CH32V003
  datasheet](https://akizukidenshi.com/goodsaffix/CH32V003.pdf)). The
  duty-coded, self-clocked PHY with per-node re-timing makes absolute
  accuracy irrelevant: decode is ratiometric on a single clock per hop
  (§2), and the worst case moves a 0.4 µs pulse by ±6.4 ns against a
  ±150 ns tolerance window. The debug UART stays within async tolerance
  (±1.6 % ≪ the usual ±2–3 % budget). Any ring-wide slotted/timestamped
  scheme must resync from data edges, never from free-running node
  clocks. HSE pins stay unconnected (the HSE clock-security fallback to
  HSI is moot); the supervisor RP2040 keeps its 12 MHz crystal for USB
  — supervisors may cost freely (§1).
- **8051-class ruled out**: the freestanding-C++ decision (§8) needs
  GCC/clang and SDCC is C-only. The recalled sub-3-NOK Silabs part —
  most plausibly EFM8BB1 at launch-era pricing, per
  [docs/mcu-research-2026-09-26.md](docs/mcu-research-2026-09-26.md) —
  is excluded on toolchain grounds, not price. No current Silabs
  listing is sub-3-NOK anyway.

Full comparison remains in
[docs/mcu-research-2026-09-26.md](docs/mcu-research-2026-09-26.md).

Requirements the chosen part satisfies (retained as the checklist for
any future node-MCU revisit):

- Analog comparator (RX) — or a PIO/programmable engine that makes a
  comparator unnecessary
- Timer with capture or PCA for edge timing (RX decode / TX encode)
- Fast enough core/peripherals for the target bit rate
- Flash/RAM budget TBD
- Toolchain: GCC/clang (freestanding C++, §8) — 8051/SDCC excluded

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

Dual role (2026-09-26): the CI board is also the **demonstrator**.
Beyond hands-off test runs, it must show the protocol to a human —
so a subset of nodes carries real human-facing I/O from the §5
complement: at minimum a potentiometer and buttons on input nodes,
LEDs and a buzzer on output nodes, populated as a mix so test traffic
*is* application traffic (§5). Properties this exploits for demos: the
§4.1 status LEDs already narrate ring health visually, and the §2
vsync latch makes multi-node LED/buzzer patterns tear-free — a fault
injection live on stage (yank a connector, watch the bypass LEDs and
the ring carry on) is the demo. Constraint: the human I/O must never
be required for operation — every input is also drivable/readable
scriptably, so the hands-off CI role is unaffected by a knob being in
the wrong position. Board-design consequence: human inputs are
**overridable from the supervisor** — e.g. the potentiometer's wiper
goes through an analog mux so the supervisor can substitute its own
DAC/filtered-PWM voltage during scripted runs (same injection pattern
as the fault muxes), and buttons parallel a supervisor-driven
optocoupler/transistor.

Board fabrication (2026-09-26): the CI/test board is **4-layer** — the
fault-injection muxes and per-node debug plumbing want the routing room,
and the §1 cost driver doesn't apply to test infrastructure. Node-board
stackup is a separate question (§9).

Prototype assembly (decided 2026-09-26, card T17): **JLCPCB Economic
PCBA** for the first prototype boards. Research + inventory snapshot:
[docs/pcba-research-2026-09-26.md](docs/pcba-research-2026-09-26.md).
Facts that shape board design:

- **Min 2 assembled boards**, ~$10 fixed (setup + stencil) +
  **$3.07 per unique Extended BOM line** — all of CH32V003, RP2040, and
  the 74LVC/TS5A-class switches are Extended, so the design rule is
  **minimize unique BOM lines** and reuse parts across nodes.
- **Single-side SMT** to stay on the Economic tier; actual WS2812-class
  LEDs are "Standard PCBA only" (moisture bake) and would force the
  pricier tier — use plain LEDs on the board.
- QFN packages incur a per-board X-ray fee — TSSOP CH32V003 (§5);
  RP2040 is unavoidably QFN.
- PCB fab minimum is 5 even when assembling 2 — spare blanks come free.
- VOEC-registered: Norwegian VAT settled at checkout.
- Fallback for anything JLCPCB can't stock: **PCBWay partial-turnkey**
  (1-pc MOQ, true consignment), at 2–4× the price.

Consequence: **part selection is
inventory-driven** — prefer parts the assembler stocks; anything
outside their library costs setup fees or hand-soldering. The DSL
parts DB tracks assembler-stock status (§7).

Open: debug transport (UART per node? shared bus?),
board interconnect style (connectors as deliberately fragile elements —
they are the failure mode under test).

Instrumented boundary node (2026-09-26): the ring node adjacent to the
supervisor — first/last, where the supervisor closes the ring — is
**extra wired to the RP2040**. Both of its ring segments (the node's RX
tap and its TX output) land on RP2040 GPIOs, so the supervisor's PIO
runs as a **logic analyzer / bus debugger on that node**: at the
125 MHz sysclock that's 8 ns resolution (~156 samples per 800 kbit/s
cell), DMA'd into the RP2040's 264 KB SRAM for deep captures. The
supervisor sees exactly what the node saw vs what it re-emitted —
per-hop latency, re-timing fidelity, decode errors under fault
injection — which is the measurement half of its golden-reference role
(§5). The same PIO pins can drive crafted/glitch waveforms back as
stimulus. Two further taps: the node's comparator-output GPIO and its
working-LED line (§4.1), so observation stays truthful even when the
node's MCU misbehaves. Taps must be short stubs — probing must not
deform the segment under observation (layout contract for T19). The §1
cost driver doesn't apply: this is test infrastructure.

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
- **Handwritten serial-number field** (2026-09-26): every PCB carries
  a white silkscreen area (hatched/filled box, sized for a fine
  marker) to write a per-unit serial number by hand at bring-up —
  the git-tag version identifies the *design*, the handwritten serial
  identifies the *physical unit* when several boards of the same
  revision are on the bench. Layout-checkable: a silkscreen box of
  minimum area, kept clear of pads and other silkscreen text.

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
with explicit `try_` growth. Rule set: **project-owned** (decided
2026-09-26, T16b) — `code-std.md` at the repo root, borrowing the
defect-preventing rules from JSF AV C++ / MISRA C++:2023 / AUTOSAR
C++14 / CERT and dropping checker-driven superstition (single-exit,
mandatory `default`, essential-type cast noise) that KLEE/fuzz/UBSan
already cover. C++23 baseline tracking C++26.
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

Firmware build system (2026-09-26): **Meson + ninja**. The build matrix
is wide even though the file count is small: three toolchains (riscv
GCC node, arm GCC supervisor, clang host) × build flavours (host
objects, LLVM bitcode for KLEE, fuzzers, coverage-instrumented release)
plus custom outputs (KLEE runs, DSL-generated headers per T9). Meson
covers that natively — one cross/native file per toolchain, per-target
flag overrides, `custom_target()` for bitcode/KLEE, `b_coverage` and
the built-in test runner for T16e's coverage-on-release. CMake was the
runner-up (toolchain-file ceremony, verbose custom commands); GNU make
loses on the multi-toolchain matrix; tup ruled out (FUSE dependency,
thin ecosystem). Provisioned through the flake like everything else.

Build reproducibility (2026-09-26): **bit-for-bit reproducible builds
are a hard constraint** — same source tree + same `flake.lock` ⇒
byte-identical artifacts, on any machine. The flake's pinned toolchains
are the foundation; on top of it: no `__DATE__`/`__TIME__`/
`__TIMESTAMP__` (code-std.md §2 — version identity comes from git,
matching §7's board-version rule), `-ffile-prefix-map`/
`-fdebug-prefix-map` on every compile so no build paths leak into
outputs, deterministic archive mode, content-derived linker build-id.
A check target builds twice and compares hashes — a reproducibility
failure is red like a failing test.

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
- **Debug transport** (§6) — per-node UART vs shared bus, connector
  style. Card: T10.
- **Node-board stackup and thickness** (§6) — leaning 4-layer to keep
  the node board small and good, but every extra layer is a per-node
  fab cost and must argue against the central cost driver (§1); the CI
  board's 4-layer decision doesn't automatically transfer. Also: node
  boards should be **thinner than the standard 1.6 mm** (≤1.0 mm class)
  so a small board doesn't feel chunky — JLCPCB offers thinner stackups
  as a fab option; verify exact thicknesses/4-layer combos at quote
  time. Card: — (no card yet; lands with the first node-board design).
- **Cable reach** (§2) — maximum segment length unamplified, and with
  an amplifier/re-driver node in the segment; line coding is settled
  (§2), so this is drive strength, comparator sensitivity, and cable
  characteristics.
  Answered by simulation first, then measured on the test board.
  Card: T15.
