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
  scaffold landed 2026-09-26 (T6): `src/oparroy/` layout, ruff `ALL`
  (formatter-conflicts off), ty, pytest wired via pre-commit
- MCU (2026-09-26, card T1): node = **CH32V003F4P6** (TSSOP-20),
  supervisor = **RP2040**; toolchains GCC riscv + GCC arm, clang host
  build retained for KLEE (§8)
- Node time base (2026-09-26): **internal HSI RC, no crystal** — §5
- PHY (2026-09-26, card T3): ratio-metric duty-coded PWM, 800 kbit/s
  anchor, comparator RX + DMA, per-bit cut-through re-timing — §2
- Bypass topology (2026-09-26, card T2): **counter-rotating dual ring,
  symmetric rebroadcast** — RX source select via the OPA's second
  positive input, no per-node parts — §3
- PCBA (2026-09-26, card T17): prototypes assembled by **JLCPCB**
  (Economic PCBA); fallback for unstocked parts is PCBWay
  partial-turnkey (§6)
- Firmware build system (2026-09-26): **Meson + ninja** — §8
- Ring power rail (2026-09-26): **3.3 V, one rail** for signaling and
  node power; regulation is per-payload, never per-node — §2.1

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
800 kbit/s confirmed by T5 simulation (2026-09-26 — measured block
below); bench confirmation lands with the test board. Break length is a
firmware/timer decision: the analog side owes only fast, chatter-free
settling to idle, which tb_fault shows.

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
  analog feedback. T5 simulation confirmed this (2026-09-26,
  `circuits/phy-segment/tb_noise.cir`): zero spurious rxout edges
  under ringing (lseg ≤ 1 µH × cseg ≤ 470 pF) and under ±250 mV-class
  capacitive crosstalk at ±13 mV comparator offset; worst high-time
  error ~1.2 ns against a ≥ 100 ns decode-margin budget. ICxF fCK_INT
  N=8 is free insurance (its ~167 ns delay is edge-symmetric and
  cancels in the ratio). The feedback-resistor fallback (OPO = PD4)
  stays unpopulated.
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
  outside 0.9–1.6 µs ⇒ stop regenerating, force the line idle), a
  **frame-length cap** (2026-09-26, T16d: a stream of legal cells past
  `frame_max_bits` = 2048 without a break — 2× the pre-sized ENUM
  maximum — is a babbling idiot too, contained the same way: Mute until
  the next break), the
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

Measured (ngspice, 2026-09-26, card T5 — benches in
`circuits/phy-segment/`, models in `circuits/lib/ch32v003.spi`):

- **Decode margins (tb_decode)** — 24 combos (segment capacitance
  47 pF–1 nF × comparator offset ±13 mV × bypass/inserted switch
  path): every cell lands ≥ 178 ns from the decode midpoint at the
  TIM2 Schmitt slice (≥ 144 ns at the pessimistic VDD/2 slice), period
  1245–1253 ns everywhere — a healthy segment never trips the
  0.9–1.6 µs illegal-cell detector. Margins are flat vs capacitance
  (±4 ns across 47 pF→1 nF) and vs offset (< 4 ns): the binding effect
  is the comparator's 7.7 V/µs slew (~230 ns edge-symmetric delay,
  ~50 ns pattern-dependent), not drive strength vs segment C.
- **No analog hysteresis (tb_noise)** — see the signaling bullet
  above; zero spurious edges under ringing and 250 mV-class crosstalk.
- **Connector faults (tb_fault)** — short to GND/VCC parks the line
  static and chatter-free (idle-high is distinguishable from a
  dead-quiet segment). An open segment requires the MCU's internal
  weak pull-down (35–55 kΩ, DS0 §3.3.9 T3-16) enabled on the OPA
  inputs: the severed line then parks idle-low, comparator static
  ≤ 33 µs even at 1 nF (~12× inside the 2-frame flip budget, §3), at
  zero BOM cost. Without it the line floats to a leakage-decided state
  — static in sim, but a chatter hazard on real silicon.

Open: drive strength vs cable (T15),
exact frame format (T11).

### 2.1 Ring power rail

Decided (2026-09-26): **the ring distributes a single 3.3 V rail** — it
is both the signaling rail (the §2 push-pull, VDD/2-threshold PHY) and
node power. No per-node regulator: the CH32V003 runs 2.7–5.5 V straight
off the rail (datasheets/CH32V003/notes/power-reset.md), and every T4/T5
bench plus the §7 protection sizing is already characterized at 3.3 V.

- **5 V rail rejected** (2026-09-26): the MCU could run at 5 V directly,
  but nothing else follows. The always-on SN74LVC1G3157 at 5 V VCC has
  VIH ≈ 0.7×VDD = 3.5 V — unreachable from a 3.3 V sel driver (§4) — and
  §5's sensor payloads (I2C accelerometer class, 3.6 V max) need 3.3 V
  regardless, so 5 V moves regulation onto the sensor instead of
  removing it. WS2812 *electrical* compatibility isn't bought either: a
  5 V-powered strip wants VIH ≈ 3.5 V, and §6 already rules WS2812 LEDs
  off the board (Standard-PCBA tier); the wire stays WS2812-compatible
  in coding regardless (§2).
- **Power headroom**: node loads are tens of mA (MCU ~4 mA at 48 MHz,
  GPIO-driven plain LEDs, small piezo), and the power loop is driven as
  a loop (§3), so a 3.3 V rail holds ample margin against the MCU's
  2.7 V floor. A future power-hungry payload carries its own regulator —
  a per-payload cost, not a per-node tax (§1). If the loop drop budget
  ever busts — check lands with T15's cable numbers, worst case a
  connector break turning the loop into a long spur — the fix is
  supervisor-side power injection at a second tap (§1: supervisors may
  cost freely), not a higher rail.
- **Unregulated payload rail added** (2026-09-27): alongside 3.3 V, the
  bus carries a raw **5–18 V** rail for payloads that outgrow tens of
  mA — anything with its own buck converter. The 18 V cap comes from
  the cheap-buck ceiling: commodity buck regulators typically spec
  ≤ 20 V max input. Node power and ring logic never touch it — nodes
  stay on 3.3 V, regulation stays per-payload (§1) — it is plain
  copper on the bus (§3 pinout) until a payload uses it.

## 3. Ring topology and bypass

Decided (2026-09-26, card T2): **counter-rotating dual ring with
symmetric rebroadcast.** Every segment carries two data wires in the same
cable/connector: ring A (primary, clockwise) and ring B
(counter-rotating). The requirement holds with no per-node parts:
**single fault ⇒ every node stays reachable** (FDDI wrap property).

Mechanism:

- The supervisor originates the same frame on both rings and drains
  both; echo mismatch on either drain ⇒ fault (§2's closure discipline,
  applied per direction).
- Every node decodes its selected source and regenerates the stream
  onto **both** TX directions (TX_A + TX_B: two TIM1 channels with
  identical compare values), so ring B always carries a live copy of the
  same logical frame, hop-delayed. Positional addressing, slot rewrite,
  and the vsync latch (§2) are source-invariant — a node that flips
  direction counts slots from the break exactly as before; no
  per-direction ENUM.
- **RX source select is firmware policy, not hardware.** The OPA's two
  positive inputs (OPP0 = PA2 = ring A, OPP1 = PD7 = ring B; `OPA_PSEL`
  in `R32_EXTEN_CTR` — datasheets/CH32V003/notes/opa.md) mux the
  comparator. No edges for > 2 frame times ⇒ flip source. Firmware is
  safe here because the node at the receiving end of a dead segment is
  alive by definition — a dead MCU is §4's case. Flap/hysteresis policy
  for intermittent opens is T13 scope. **The internal weak pull-down
  stays enabled on both OPP inputs** (2026-09-26, T5 tb_fault, §2
  measured block): it parks a severed segment idle-low and
  chatter-free, which the flip policy depends on.

Per-node cost: no parts; +1 wire +1 connector contact per segment; +2
GPIO per node (PD7 as RX_B — already an OPP input — plus one TX_B pin).
The §5 pin budget lands at ~16–17 of 18, verified at pin-map time
(T9/T11). Electrically neutral for the PHY: every driver still sees
exactly one segment, so T5's drive/capacitance baseline and T15's reach
budget are unchanged by the topology.

Segment connector (2026-09-27; supersedes the single 10-contact
connector sketched the same day): **two 6-pin connectors per node** —
upstream-facing `(UNREG, 3V3, GND, RX_A, GND, TX_B)` and
downstream-facing `(UNREG, 3V3, GND, TX_A, GND, RX_B)`, node-centric
naming (RX_A/TX_A = this node's ring-A receive/transmit). Each
connector carries UNREG + 3V3 with two GND pins, so every supply pin
has a paired return: balanced copper cross-section for power and
ground on both faces. Power enters a node from both directions — the
power loop above — and connector part/style stays open (§6).

Interaction with §4: the watchdog SPDT bypass stays, on ring A only —
dual ring demotes it from sole defense to second layer. A dead MCU
breaks ring B at that node (TX_B floats) while ring A bypasses it; a
connector break severs both rings at one point and every node is still
served from the live side. (The power loop already survives single
breaks for free — it is driven as a loop, not a direction. The
asymmetry the second data wire fixes is the data ring's
directionality.)

Failure modes, answered:

- Permanent open at a connector — both rings severed at one point;
  nodes past the break flip to the live direction; all nodes reachable.
- Intermittent open at a connector — direction-flap policy deferred to
  T13; the hardware substrate is now settled.
- Short to GND / VCC on a segment — treated as an open of that wire;
  the other direction covers. Rail shorts are the CI-board eFuse's
  scope (§7).
- Dead MCU (no clock, outputs floating) — §4 charge-pump bypass on
  ring A; ring B lost at that node, coverage by A.
- Hung MCU — same path: keep-alive stops, bypass engages.
- MCU transmitting garbage (babbling idiot) — §2 containment
  (illegal-cell stop, frame-length cap), TIM1 brake kills both TX
  channels, §4 bypass follows.

Rejected (2026-09-26):

- **Per-node switch only** — a connector open darkens every node
  downstream of the break back to the supervisor's drain; fails §1
  driver 2 outright.
- **Skip-one wires (N→N+2)** — whole-connector-yank coverage needs
  physically separate skip assemblies leaping a node: 2× pitch halves
  the T15 reach budget on the engaged path, and avoiding permanent
  double drive-loading costs +1 SPDT per node. Sharing the connector
  instead cuts coverage to single-contact faults. Equal-or-less
  coverage for worse mechanics.

## 4. Node watchdog / bypass

Decided (2026-09-26, card T4): an **edge-sensitive charge pump** holds a
normally-on analog switch open; when the MCU stops strobing, the switch
relaxes closed and RX→TX bypass engages. The window-watchdog supervisor
IC candidate is rejected on cost/inventory (below). Both candidates
live as standalone subcircuits with ngspice testbenches:

- `circuits/watchdog-chargepump/` — **chosen**. BAT54S-class dual
  Schottky pump (Cp=22n, Rs=220, Cs=10n, Rb=47k, τ=0.47 ms) driven by a
  20 kHz MCU keep-alive; its `sel` output drives the switch select.
- `circuits/watchdog-supervisor/` — the rejected TPS3430-class window
  watchdog, kept as the quantified record of what the money would have
  bought.

Switch: SN74LVC1G3157 SPDT (facts in
`datasheets/SN74LVC1G3157/notes/`). COM = downstream, B1 = upstream —
bypass is the default, sel low —, B2 = node TX. The node's RX tap stays
connected in bypass: a dead node keeps listening (listen-only); bypass
cuts TX only.

Requirement (unchanged): RX→TX bypass is the **default state**; the MCU
must actively deassert it. Semi-passive — no firmware in the bypass
path itself.

Measured (ngspice, swept across both select-threshold edges
0.99/2.31 V):

- **Engage speed**: bypass closes ~0.5 ms after the last keep-alive
  edge — link-level, sub-frame. Bit-level bypass switching is neither
  needed nor achievable with this class of circuit.
- **Missed-pulse tolerance**: one dropped 50 µs keep-alive cycle droops
  sel only to ~2.5 V, still above the 2.31 V VIH edge — no spurious
  engage.
- **Glitch immunity**: the Rs·Cp input filter makes narrow (100 ns)
  glitches transfer nothing.
- **Accepted hazard**: a µs-wide *periodic* waveform is a false
  keep-alive (sel ~2.9 V with a Hi-Z dead driver, ~1.3 V mid-band with
  a stuck-low driver). Anchored in tb_glitch phase 2.

Window vs timeout — the window property is traded away on a
cost/inventory argument (JLCPCB, 2026-09-26): window-watchdog ICs are
not inventory-viable — TPS3430 $1.50 VSON-10, TPS3435 ≥$2.50, MAX6369
$1.92, each more than the CH32V003 itself ($0.29, §1) — and the stocked
timeout-only supervisors (TPS3823 $0.25, STWD100 $0.37) add nothing
over discrete. Candidate A is ~$0.01 of Basic-class discretes. What the
money would have bought, measured in candidate B's benches: one dropped
strobe costs only a bounded 1.51 ms self-recovering bypass blip (A
instead tolerates the drop silently and engages ~0.5 ms late when
strobes stop for real; B's timeout engage is 1.49 ms after the last
strobe); an early edge latches the fault ~0.2 µs after the offending
edge, vs A's analog droop; a 3.3 kHz glitch train after MCU death
cannot service the window (the first glitch resets the ramp unjudged —
engage slips to 1.70 ms — every later glitch is an early edge that
re-sets the latch); and the select output snaps rail-to-rail, with no
10 ns/V input-rate violation.

Known spec violation, accepted: A's slow sel ramp breaks the switch's
10 ns/V input-rate spec (SCES424O §5.4) — ≤500 µA ΔICC while dwelling
~0.4 ms in the 0.99–2.31 V band, once per fault event. A 74LVC1G17
Schmitt buffer on sel fixes it for one Extended BOM line if the bench
disagrees.

Power: bypass switch + watchdog run from the **always-on ring rail**,
not the per-node switchable rail — the 1G3157 has no Ioff /
partial-power-down spec. Shaped §3 (2026-09-26); still constrains T10.

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
board interconnect connector part/style — the pinout is settled
(2026-09-27, §3); connectors remain deliberately fragile elements,
they are the failure mode under test.

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
backend. Package scaffold landed 2026-09-26 (T6, see §8 tooling).

DSL shape (2026-09-26, from the T7a design interrogation):

- **Separable, pretty-printable IR.** The IR is a real data structure,
  dumpable and diffable; its printed form is for humans — it does not
  need to round-trip back into DSL source.
- **Checks run as a validation pass** over the finished IR
  (capture → check → emit), not at connection time. Structural
  invariants (unique references, a pin on at most one net) still raise
  at construction — they are not checks but what makes the IR
  well-formed.
- **Plain function-call API, HDL-instantiation flavor.** Named
  connections, no operator overloading, no implicit global circuit.
  Sugar only if the call style proves tedious in use.
- **References are explicit instance names.** A part's refdes is given
  at capture (`circuit.part("Rs", ...)`), like an HDL instance name —
  no auto-assignment scrambling references when a part is inserted
  (SKiDL's pain), so pcbnew's ref-matched netlist import stays stable
  across source edits.
- **KiCad library integration is mandatory.** Symbol/footprint
  references validate against KiCad's actual libraries (provisioned via
  the flake) — without that, pcbnew ingest can't be trusted.
- **The pipeline is not one-way** (2026-09-27). Between capture and
  pcbnew sit **footprint assignment** and **annotation** as explicit,
  repeatable stages — annotation re-runs during layout so numbering
  ends up reflecting physical placement (KiCad's geographic annotation
  is the norm). Capture names stay the stable identity (the explicit
  instance names above); annotation maps them to placed refdes, and the
  DSL accepts pcbnew's back-annotation rather than treating emission as
  a one-shot export.
- **Footprints default per part class, overridable per instance**
  (2026-09-27). Declaring a footprint at every instantiation is too
  verbose: a part class carries its default footprint in the capture,
  and later stages (assignment, the parts DB) may override. ICs bind
  their package at capture — the package decides which pins physically
  exist, so it is never a late-stage decision. The checker's
  missing-footprint error applies to the **post-assignment** IR: class
  defaults resolve during capture, so a part reaching `check` without a
  footprint has neither default nor assignment — that is the error.
- **Typed jellybean parts, strings for the rest** (2026-09-27). Common
  passives and transistors get real Python classes — `Resistor`,
  `Capacitor`, `Diode`, `Nfet`, `Pnp`, `Npn`, … — so the type checker
  and autocomplete do the work stringly-typed declarations can't.
  Classes accrete as captures need them (YAGNI — no speculative zoo).
  One-off parts stay string-declared, but **declared in one place and
  instantiated elsewhere**: declaration is data, instantiation is
  wiring. Instantiation is **keyword-only** (2026-09-27): positional
  arguments are a pin-swap factory (the BAT54S x/sel swap, found in the
  T7a review, is the proof). Pin names are the keyword names —
  `Diode(*, cathode=sel_net, anode=x_net)` — so construction *is* the
  wiring: no separate `connect` call for typed parts, and the type
  checker and autocomplete cover declaration and connection alike. Sole
  exception: `Resistor` and `Capacitor` may take their value
  positionally — one unpolarized value carries no orientation risk;
  `CapPol` and anything else with direction-sensitive pins, never.
  Enforced with `*` in the class signatures.
- **Multi-unit packages mirror KiCad's unit model** (2026-09-27).
  KiCad encodes multi-unit symbols as `<Name>_<unit>_<style>`
  subsymbols: unit 0 = pins/graphics common to all units, style 1 =
  normal body / 2 = De Morgan (graphics-only for us), and each unit's
  pins carry **physical package pin numbers** — the LM2902 is four
  op-amp units plus a separate power unit; the BAT54ADW is four diode
  units whose *shared anode pins appear in several units*. eeschema
  places units independently (U1A, U1B, …; unplaced units don't
  exist), and the netlist export flattens to refdes + physical pin
  numbers — pcbnew never sees units. The DSL mirrors this: `Symbol`
  preserves unit structure (kicadlib flattens it today — to be fixed
  when the first multi-unit part lands, e.g. the CI board's
  4066-class fault-injection switches), a placed part instantiates a
  **unit subset** (default: all — today's behavior), unplaced units
  materialize no pins so the unconnected-pin check stays clean, and
  the checker asserts that a physical pin shared by several placed
  units sits on one net (KiCad ERC's own rule). Package-as-one-part
  stays right for units used as a single element: the BAT54S series
  pair is a single unit in KiCad's own library, which is exactly the
  `Bat54s` typed-class choice.
- **Computed values carry slack** (2026-09-27). A computed value
  (divider ratio, filter corner) is a spec — target plus tolerance —
  not a number: the emitter resolves it to a real part from a stocked
  bin (the VDD/2 divider draws from the 10k bin), never an unsourcable
  irrational value. Resolution runs against the T7c parts DB's value
  bins (§6 inventory-driven selection). `Part.value` widens from a
  string to a value-spec type when this lands — a designed change to a
  public constructor parameter, not a patch (card: T23).
- **Captures live in a new `design/` tree.** `circuits/` keeps benches
  and device models until T7e's port retires the DUT `.cir` files.
- **Human-review rendering:** a Graphviz dot dump is the minimal first
  view (ugly, but a start); the goal is abstraction-level block views
  in the Verilog-debugger sense — prior-art survey is card T21.

Landed (2026-09-26, card T7a; typed parts and review hardening
2026-09-27): the DSL core in `src/oparroy/dsl/` —
`ir.py` (parts/pins/nets/circuit + pretty-print), `check.py`
(validation pass: connectivity, footprint existence and symbol
footprint-filter match, power-driver rules with KiCad's own
power-symbol convention — a `power:`-library pin marks its net
driven), `kicad_emit.py` (the
s-expression `.net` pcbnew imports; byte-identical emission —
sorted iteration, content-derived UUID tstamps, no dates or paths;
power symbols excluded like eeschema's own export),
`dot.py` (Graphviz dump), `kicadlib.py` + `sexpr.py` (KiCad 10 library
access, `extends`-aware), `parts.py` (typed jellybean parts —
`Resistor`/`Capacitor`/`Bat54s`, keyword-only pin wiring at
construction, class-default footprints per bin). Proven by
`design/watchdog_chargepump.py`:
the §4 charge pump captured on typed parts against the
nix-provisioned KiCad
libraries, golden netlist in `tests/golden/` (byte-identical across
the typed-parts migration), 92 pytest cases green.
Not yet proven: a real pcbnew netlist *import* (no KiCad application in
the flake yet — the golden format is pinned, the ingest is exercised
when the first board enters layout).

Subcircuit composition (2026-09-28, card T7ba): hierarchy is
capture-time structure, **flattening is a pass** — `subcircuit.py`
(`Subcircuit` base), `Circuit.port` (a net marked as interface, exempt
from the dangling-net checks), `Circuit.instance` (captures the child
per instance and binds every port by keyword; unknown or unconnected
ports raise at capture), `Circuit.flatten` (instance names prefix part
references and internal nets — `WD1/Rs`, `WD1/x` — while port nets
merge into the net their instance bound; explicit names at every level
keep refdes stable across source edits). `/` is the hierarchy path
separator and is rejected in instance names, part references, and net
names alike; unbound (top-level) ports keep their interface flag
through flattening, so the dangling-net exemption survives the pass.
Hierarchy survives flattening
as metadata: `Part.path` feeds real `sheetpath`s in the KiCad netlist
with content-derived tstamps — the channelization hook. Check and both
emitters flatten implicitly and report hierarchical paths. The §4
watchdog is the first subcircuit (`design/watchdog_chargepump.py`); the
8-instance proving case runs in `tests/test_dsl_subcircuit.py`.
Remainder of the T7b split: multipacking and component sockets (T7bc),
connection sugar (T7bd).

Port arrays and bundles (2026-09-28, card T7bb): the interface scales
past scalar ports. `Circuit.port_array` declares a width-fixed vector
(`led[0]`…`led[7]`) bound element-wise at instantiation — a width
mismatch raises at capture (button matrices, LED arrays); elements may
also bind individually by name. `Circuit.bundle` groups *existing*
nets under member names — the §3 connector pinout as one connectable
unit. Members name wires, not node functions (`a` is the ring-A data
wire on pin 4 of both faces), so two faces join member-to-member; the
power nets alias into both faces' bundles, and a port reached through
two groups must resolve to one parent net — conflicting bindings
raise. `BundleConnector` (parts.py) is the connector block: the
member→pin-number mapping is class data, and `pin_map` values widen to
tuples for a member owning several pins (the paired §3 grounds).
`design/segment.py` carries the §3 pinout (`segment_ports`) and the
connector block itself (part/footprint provisional — §3 leaves the
connector style open, §6). Both group forms expand to scalar port
bindings at instantiation: flattening, checks, and emitters see plain
nets only. One checker fix rode along: footprint filters match against
the full `Lib:Name` as well as the bare name, so KiCad's lib-qualified
filters (`Connector*:*_1x??_*`) work.

ngspice emitter (2026-09-28, card T7d): `spice_emit.py` (`emit_spice`)
is the simulation-netlist backend over the flat IR. It emits the DUT
as a `.subckt` with ports in declaration order; stimulus and `.meas`
assertions stay in the external bench decks (`circuits/**/tb_*.cir`) —
the DSL emits the circuit, benches drive it — so a capture whose ports
match a hand-written `circuits/` interface drops into the same benches
unmodified, and either capture can drive the run while T7e ports the
DUTs over. Spice bindings are ad hoc until T7c's parts DB owns them: a
symbol-keyed table (R/C two-pin primitives, the BAT54S series-pair
expansion) plus caller-passed `.model` definitions, a part's value
naming its model as in a hand-written deck. Emission is byte-identical
like the KiCad emitter's, hierarchy flattens implicitly (ngspice
accepts `/` in element and node names verbatim), and element names
keep the ref, gaining a kind-letter prefix only when flattening hid it
(`WD1/Rs` → `RWD1/Rs`). Proven by `design/watchdog_chargepump.py --spice`: the emitted `wd_chargepump` passes all three §4 benches
(`tb_engage`, `tb_missed_pulse`, `tb_glitch`) through
`scripts/sim-run` — the T7e equivalence pattern, rehearsed.

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
- **I/O terminal protection: series R + optional TVS** (decided
  2026-09-26): every terminal that leaves the board gets a series
  resistor near the µC pin, sized against the CH32V003 injection
  current (±4 mA/pin, Σ ±20 mA, DS0 §3.2 T3-1) — 470 Ω on ring
  TX/RX (470 Ω × 50 pF ≈ 24 ns edge softening, far inside the §2
  decode margins) and on user-facing outputs (7 mA into a shorted
  pin, inside the ±8 mA spec'd drive), 1 kΩ on buttons, ADC sources
  ≤ 10 kΩ total including the series R (adc.md, T3-24). The R also
  caps phantom-power injection into a powered-down node (the §4/§6
  power-cut fault). Prefer FT pins (PC1/PC2/PC5/PC6) for any
  terminal that can see 5 V. Plus a **TVS footprint per external
  terminal**, wired connector → TVS → R → µC so the R limits what
  the internal clamp diodes absorb after the TVS clamps.
  Low-capacitance bidirectional ESD parts (tens of pF, VRWM
  ≥ 3.3 V) — not nF-class power-rail TVS. **Population rule: the CI
  board ships fully populated** — test the superset, since DNP
  strictly removes load and a passing CI with TVS covers the bare
  variant; leave one CI node DNP to cover populated↔unpopulated
  segments in the same run. Production nodes may ship DNP. The
  power-rail TVS pairs with the eFuse/crowbar above and is *not*
  optional. Layout-checkable (T19): TVS adjacent to its connector,
  R between TVS and µC pin.
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
with explicit `try_` growth. Landed in `firmware/lib/`: `Span`,
`irange`, `StaticVector`, `VERIFY` (2026-09-26); `Error`/`ErrorOr<T>`/
`ErrorOr<void>` + `TRY` (`GrowthResult` subsumed — `try_*` now returns
`ErrorOr<void>`), `StaticArena` + `ArenaPtr` ownership over static
slot pools, `UNREACHABLE`, VERIFY's target personality
(`-DOPARROY_TARGET` → `lib::verify_failed`, the §4 wiring point — the
node firmware's hook definition lands with T11), `lib::move`
(`utility.hpp` — AK's spelling; `<utility>` stays outside the
freestanding header set, code-std.md §2), and the StaticVector → `Span`
implicit conversion (the `std::vector` → `std::span` analog, AK's
`Vector`/`operator Span` shape) (2026-09-28, T18).
`Error` is a bare `enum class` code, not AK's string-carrying class —
widen to a payload-carrying class the day an error needs more than a
code. Rule set: **project-owned** (decided
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
The project's default `buildtype` is pinned to `plain` (2026-09-26,
T20): the nix cc-wrapper appends `-D_FORTIFY_SOURCE` *after* all user
flags whenever it sees an explicit `-O` (meson debug's `-O0` included),
and glibc `#error`s on that under `-Werror` at `-O0` — freestanding has
no libc for fortify to call into anyway. Optimized flavours are chosen
per build dir at setup time.

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

- **Intermittent connector faults** (§3) — protocol re-route vs hardware
  auto-bypass vs both; the dual-ring substrate is settled (§3), the
  direction-flap policy is not. Card: T13.
- **Debug transport** (§6) — per-node UART vs shared bus, connector
  style. Card: T10.
- **Node-board stackup and thickness** (§6) — leaning 4-layer to keep
  the node board small and good, but every extra layer is a per-node
  fab cost and must argue against the central cost driver (§1); the CI
  board's 4-layer decision doesn't automatically transfer. Also: node
  boards should be **thinner than the standard 1.6 mm** (≤1.0 mm class)
  so a small board doesn't feel chunky — JLCPCB offers thinner stackups
  as a fab option; verify exact thicknesses/4-layer combos at quote
  time. Card: T22 (the first node-board design).
- **Cable reach** (§2) — maximum segment length unamplified, and with
  an amplifier/re-driver node in the segment; line coding is settled
  (§2), so this is drive strength, comparator sensitivity, and cable
  characteristics.
  Answered by simulation first, then measured on the test board.
  Card: T15.
