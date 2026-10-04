# DESIGN

Settled design decisions, plus §9 for decided-to-be-decided questions
that aren't yet work cards. Sections marked TBD are open.

Settled (2026-09-26):

- Project and protocol name: **oparroy**
- License: **MIT** (LICENSE added 2026-09-26)
- Design capture: **home-rolled DSL** (not SKiDL) — owns its IR, emits
  KiCad netlists, constraint checks, firmware headers, simulation netlists
- Test board: **8 ring nodes + 1 supervisor**, **full fault injection**
  (per-segment open/short, per-node power cut, clock kill — all scriptable)
- CI: **local script first** (`test-hw` style target), CI platform
  integration deferred until the board exists
- Firmware language: **freestanding C++ — no standard library**,
  zero-cost abstractions only (RAII, placement new on memory-mapped
  I/O), under an aviation-grade rule set (§8)
- Tool provisioning: **nix flake** for everything non-Python (SDCC/GCC
  toolchains, KLEE/clang, ngspice, KiCad, provers); **uv** for Python
  deps — see §8
- Python tooling: **3.13, uv, ruff (strict), ty, pytest** — package
  scaffold landed 2026-09-26: `src/oparroy/` layout, ruff `ALL`
  (formatter-conflicts off), ty, pytest wired via pre-commit
- MCU (2026-09-26): node = **[CH32V003F4P6](datasheets/CH32V003/)**
  (TSSOP-20), supervisor = **RP2040**; toolchains GCC riscv + GCC arm,
  clang host build retained for KLEE (§8)
- Node time base (2026-09-26): **internal HSI RC, no crystal** — §5
- PHY (2026-09-26): ratio-metric duty-coded PWM, 800 kbit/s
  anchor, comparator RX + DMA, per-bit cut-through re-timing — §2
- Bypass topology (2026-09-26): **counter-rotating dual ring,
  symmetric rebroadcast** — RX source select via the OPA's second
  positive input, no per-node parts — §3
- PCBA (2026-09-26): prototypes assembled by **JLCPCB**
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

Decided (2026-09-26, against the CH32V003's peripherals; full
analysis:
[docs/phy-analysis-2026-09-26.md](docs/phy-analysis-2026-09-26.md)).
800 kbit/s confirmed by simulation (2026-09-26 — measured block
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
  the ceiling is comparator response and cable reach (§9), not the
  timers — but at 800 k the OPA (12 MHz GBW, 7.7 V/µs) is nowhere near
  the bottleneck and COTS WS2812 tooling applies. Frame/latch marker:
  line-low break, ≥ 50 µs baseline (WS2812's reset is the upper
  reference; MCU nodes may go shorter once bench confirms — the
  vsync semantics below ride on the break either way).
- **Signaling: 3.3 V single-ended**, push-pull at VDD per segment,
  idle low. RX threshold = VDD/2 divider on an OPA negative input. The
  OPA has no documented hysteresis: glitch rejection comes from the
  TIM2 input digital filter (ICxF) plus ratio-decode margins, not
  analog feedback. Simulation confirmed this (2026-09-26,
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
  ([opa.md](datasheets/CH32V003/notes/opa.md),
  [timers.md](datasheets/CH32V003/notes/timers.md),
  [dma.md](datasheets/CH32V003/notes/dma.md)).
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
  **frame-length cap** (2026-09-26: a stream of legal cells past
  `frame_max_bits` = 2048 without a break — 2× the pre-sized ENUM
  maximum — is a babbling idiot too, contained the same way: Mute until
  the next break), the
  TIM1-brake TX-kill and hardware bypass (§3, §4), and supervisor-side
  CRC/sequence checks (feeds the §9 intermittent-fault policy).
  Fallback rung: if the per-bit loop doesn't close timing on-target,
  degrade to store-and-forward (decided with measurements on-target).
  Closure discipline: the supervisor is the only frame originator and
  drainer; echo mismatch ⇒ fault.
- **Addressing: positional, discovered — no solder bridges, no
  provisioning step.** Position in the ring *is* the address. The
  supervisor enumerates with one circulation of an ENUM frame that
  each node stamps with its factory 96-bit UNIID (ESIG — see
  [flash-option-bytes.md](datasheets/CH32V003/notes/flash-option-bytes.md))
  plus a type byte; the position ↔ UNIID map rebuilds automatically
  when a node is
  replaced. Solder-bridge IDs (Trill-style, bela-lessons §2) lose on
  pin budget (≥2 GPIO on an 18-GPIO part) and per-node parts — the §1
  cost driver. One firmware image, personality by type byte in flash
  (node firmware).
- **Telemetry: slotted in the circulating frame, not polled.** Each
  node writes its own slot as the frame passes, with inputs sampled at
  the vsync latch (below) — synchronous sampling in the ring's
  timebase (bela-lessons §1), deterministic latency (~1.6 kHz
  full-ring update at 8 nodes, cut-through — see re-timing above), no
  poll round-trips. The frame sequence counter is the timestamp.
  Frame format detail is node-firmware scope (KANBAN.md).
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

Measured (ngspice, 2026-09-26 — benches in
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

Open: drive strength vs cable (§9),
exact frame format (node firmware).

### 2.1 Ring power rail

Decided (2026-09-26): **the ring distributes a single 3.3 V rail** — it
is both the signaling rail (the §2 push-pull, VDD/2-threshold PHY) and
node power. No per-node regulator: the CH32V003 runs 2.7–5.5 V straight
off the rail ([power-reset.md](datasheets/CH32V003/notes/power-reset.md)),
and every §4 watchdog / §2 PHY bench plus the §7 protection sizing is
already characterized at 3.3 V.

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
  ever busts — check lands with the §9 cable numbers, worst case a
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

Decided (2026-09-26): **counter-rotating dual ring with
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
  in `R32_EXTEN_CTR` — [opa.md](datasheets/CH32V003/notes/opa.md)) mux the
  comparator. No edges for > 2 frame times ⇒ flip source. Firmware is
  safe here because the node at the receiving end of a dead segment is
  alive by definition — a dead MCU is §4's case. Flap/hysteresis policy
  for intermittent opens is open (§9). **The internal weak pull-down
  stays enabled on both OPP inputs** (2026-09-26, §2
  measured block, tb_fault): it parks a severed segment idle-low and
  chatter-free, which the flip policy depends on.

Per-node cost: no parts; +1 wire +1 connector contact per segment; +2
GPIO per node (PD7 as RX_B — already an OPP input — plus one TX_B pin).
The §5 pin budget lands at ~16–17 of 18, verified at pin-map time
(§7 pin map). Electrically neutral for the PHY: every driver still
sees exactly one segment, so the §2 measured baseline and the §9
reach budget are unchanged by the topology.

Segment connector (2026-09-29; supersedes the 2026-09-27 6-pin
pinout): **two 10-pin 2.54 mm 2x5 IDC box headers per node** on
10-way 1.27 mm-pitch 28 AWG ribbon (3M 3365/10 or generic UL2651) —
the AVR-ISP shape, the deepest-stocked IDC system there is. Pricing
fetched 2026-09-29 (LCSC @100): header C22385222 $0.069 + cable-side
socket C8373 $0.084 → **$0.31 of connectors per node**; the 2.0 mm
and 1.27 mm-pitch IDC systems run 2–4× that on thin stock, and the
1.27 mm system has no 28 AWG cable at all (0.635 mm ribbon is
30 AWG, a third off the power budget) — §1's cost driver outranks
the larger footprint. The dual-row IDC straddle lands odd conductors
in one row and even in the other, so the conductor order

```
UNREG, GND, 3V3, GND, A, GND, B, GND, 3V3, GND
```

makes row 2 a solid ground row with every conductor ground-flanked —
the datasheet G-S-G configuration behind the reach model's
102 Ω / 47.5 pF/m numbers
([docs/cable-reach-2026-09-28.md](docs/cable-reach-2026-09-28.md)) —
and quarantines UNREG at the cable edge, away from both data wires.
Both faces share one pinout by wire identity: pin 5 is the ring-A
data wire, pin 7 the ring-B one, whichever face you look at; naming
stays node-centric (RX_A/TX_A = this node's ring-A
receive/transmit). Doubled 3V3 plus five grounds drops the power
loop to ~0.15 Ω/m, stretching the broken-loop power budget
(cable-reach §5) from 5.8 m to ~12 m at 10 mA nodes — past the 10 m
signal reach, so power stops binding segment length. Power enters a
node from both directions — the power loop above. The header is **SMD
on the board's back side** (2026-09-29), hand-soldered post-PCBA:
JLCPCB places the front only — single-side SMT keeps the Economic
tier (§6) — and the front stays flat as the enclosure-wall mount
face. No stocked SMD box header carries anchor pegs or hold-downs, so
the gull-wing joints alone take the mating load — unmating is
in-plane shear, the gentle direction — and the through-hole variant
(C2977596) stays in the parts DB note as the high-pull-force
fallback. The cable-side socket vise-presses onto the ribbon, no
crimp tooling. Friction fit is deliberate: connectors remain the
fragile element under test (§6) — the shroud only keys against
reverse insertion.

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
- Intermittent open at a connector — direction-flap policy deferred
  (§9); the hardware substrate is now settled.
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
  the §9 reach budget on the engaged path, and avoiding permanent
  double drive-loading costs +1 SPDT per node. Sharing the connector
  instead cuts coverage to single-contact faults. Equal-or-less
  coverage for worse mechanics.

## 4. Node watchdog / bypass

Decided (2026-09-26): an **edge-sensitive charge pump** holds a
normally-on analog switch open; when the MCU stops strobing, the switch
relaxes closed and RX→TX bypass engages. The window-watchdog supervisor
IC candidate is rejected on cost/inventory (below). Both candidates
live as standalone subcircuits with ngspice testbenches:

- `circuits/watchdog-chargepump/` — **chosen**.
  [BAT54S](datasheets/BAT54S/)-class dual Schottky pump (Cp=22n,
  Rs=220, Cs=10n, Rb=47k, τ=0.47 ms) driven by a 20 kHz MCU keep-alive;
  its `sel` output drives the switch select.
- `circuits/watchdog-supervisor/` — the rejected TPS3430-class window
  watchdog, kept as the quantified record of what the money would have
  bought.

Switch: [SN74LVC1G3157](datasheets/SN74LVC1G3157/) SPDT (facts in
[its notes](datasheets/SN74LVC1G3157/notes/facts.md)). COM = downstream,
B1 = upstream — bypass is the default, sel low —, B2 = node TX. The
node's RX tap stays connected in bypass: a dead node keeps listening
(listen-only); bypass cuts TX only.

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
10 ns/V input-rate spec ([SCES424O](datasheets/SN74LVC1G3157/) §5.4) —
≤500 µA ΔICC while dwelling ~0.4 ms in the 0.99–2.31 V band, once per
fault event. A 74LVC1G17 Schmitt buffer on sel fixes it for one
Extended BOM line if the bench disagrees. Insurance landed for the
node board (2026-09-29): a **DNP 74LVC1G17 footprint in the sel path,
bridged by a fitted 0 Ω** — the fix becomes a resistor swap, not a
respin.

Power: bypass switch + watchdog run from the **always-on ring rail**,
not the per-node switchable rail — the 1G3157 has no Ioff /
partial-power-down spec. Shaped §3 (2026-09-26); still constrains the
§6 test board.

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

Status-LED delivery (2026-09-29): the four status LEDs are
**reverse-mount 1206 parts on the front** (XINGLIGHT XL-3216-FB
series — parts DB), emitting through routed holes in the PCB to the
**back — the connector side, where a viewer stands**. The LED pads
stay on the front, so single-sided assembly and the flat
enclosure-wall face are untouched, and the back's copper set stays
exactly the two segment connectors (§7 checklist). One series covers
all four positions; the per-connector link pair is the 570 nm
yellow-green (the series' 525 nm true green has Vf 3.4 V, undrivable
from a 3.3 V GPIO), and the working LED is the 588 nm yellow so the
roles stay visually distinct — red = power, yellow = working,
green = link (2026-09-30). Layout-checkable (§7): each status LED
sits over its routed hole.

Per-connector LED drive (2026-09-29): **firmware-driven**, confirmed
against the hardware-activity ideal above — the watchdog plus working
LED already flag a dead node, and the CI board observes truth through
the §6 supervisor taps, so per-node activity hardware doesn't survive
the §1 cost driver. The two connector LEDs merge onto **one GPIO as
an antiparallel pair** with a shared series R: pin high lights
upstream, low lights downstream, Hi-Z dark, a kHz toggle lights both
at half brightness. That frees PC1 (an FT pin) and one resistor; the
cost is firmware encoding complexity and the loss of independent
steady states. The activity/no-signal/error encoding itself stays
firmware scope (the §4.1 TBD above).

## 5. MCU platform

Decided (2026-09-26):

- **Node MCU: [CH32V003F4P6](datasheets/CH32V003/)** (WCH RV32EC @
  48 MHz, **TSSOP-20**) — ~$0.29 at prototype qty, $0.137 @4k (LCSC
  **C5187096**, JLCPCB Extended, ~9k in stock 2026-09-26). Its OPA
  comparator routes to TIM2 CH1 capture; two capture-capable timers +
  DMA. TSSOP-20 over the
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
- **Node time base** (2026-09-26, §2 analysis): **internal HSI 24 MHz
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
stackup settled separately (2026-09-29, §9): **2-layer, 0.8 mm**.

Prototype assembly (decided 2026-09-26): **JLCPCB Economic
PCBA** for the first prototype boards. Fab order (2026-09-30): the
**CI/test board fabs first** — its eight node tiles are the first
bench articles for the §2/§4 claims — and the standalone node board
follows, assembled at the 2-board minimum as the production-form
proof (single-sided assembly, back-side hand-soldered headers, pogo
programming flow). Research + inventory snapshot:
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
- Third-party population is acceptable (2026-09-30): consignment and
  Extended-line fees are just money — what the design avoids is
  hand-soldering jellybean passives ourselves at volume.

Consequence: **part selection is
inventory-driven** — prefer parts the assembler stocks; anything
outside their library costs setup fees or hand-soldering. The DSL
parts DB tracks assembler-stock status (§7).

Node programming (2026-09-29): nodes program **post-SMT over SWIO**
— the CH32V003's single-wire debug on PD1 is the only way in (no
factory bootloader; [quirks.md](datasheets/CH32V003/notes/quirks.md)
§Debug), and PD1 is the pin map's one hard reservation. Flow:
JLCPCB places the front; each board then lands on a **pogo jig**
(the bela-lessons first-class deliverable) where a **WCH-LinkE** —
the official probe; clones hit flash-unlock walls (quirks) —
flashes the single node image plus the personality type byte where
a board carries one. **The programmer powers the board**: brick
recovery is a power cycle through reset (quirks), so the jig's 3V3
comes from the WCH-LinkE, never the ring, and the board exposes a
**SWIO + GND + 3V3 pad strip** for it (§7 checklist). Positional
addressing (§2) means **zero per-node provisioning** — one image,
no serial numbers burned; the factory UNIID (ESIG) is read at flash
time and logged against the handwritten unit serial (§7 checklist).
The back-side connectors go on *after* programming — the bela
rework-stage ordering.

CI flash fan-out (2026-09-29): **the flash-busy time of all eight
nodes must overlap** — programming time dominates test time, and the
floor per node is silicon flash-busy, not transport: 256 fast pages
(64 B) at 2.4–3.1 ms each ≈ 0.8 s
([flash-option-bytes.md](datasheets/CH32V003/notes/flash-option-bytes.md)).
Serializing that busy time — one shared probe doing node after node —
puts ~7 s of dead time in front of test runs that themselves measure
in milliseconds. Mechanism (revised 2026-09-29): **one PIO SWIO
channel through an analog mux to the selected node**, pipelined
round-robin — stream a page (16 words ≈ 0.7 ms of wire), kick the
page program, switch the mux to the next node while the first is
busy; poll the status registers round-robin. Legal because SWIO has
no inter-packet timing requirement: the protocol is host-paced
(minichlink already inserts USB-scale gaps between packets), so the
mux may dwell anywhere between transactions. One channel keeps
~4 nodes' flash pipelines full (3 ms busy vs 0.7 ms wire per page);
with 8 nodes the wire becomes the bottleneck and total flash time is
≈ max(8 × 0.2 s transport, 0.8 s busy) ≈ 1.6 s — the requirement is
met, with QDM fast mode (§2.2) in reserve. The mux is a low-Ron
analog switch (74LVC1G3157-class, already a stocked BOM line;
analog switches are bidirectional, which half-duplex SWIO needs);
deselected nodes idle SWIO high on a **per-node 10 kΩ pull-up,
target side of each mux port** (2026-09-29): the 003's internal weak
pull-up (35–55 kΩ, 45 typ — DS0 §3.3.9) holds DC with ~5× margin
against mux off-leakage (~6 µA worst case → 0.33 V droop) but is
soft against capacitive coupling from the seven other switching
channels, and the external resistor also covers the 002/4/5/6
variants whose SWIO mandates one (quirks). Bus-keepers rejected:
they hold *last state* on a line that must idle *high*, power up
undefined, and this rig power-cycles nodes for brick recovery — a
keeper latched low wedges SWIO. A second pull-up (4.7–10 kΩ) sits
on the mux **common port**: rise time after a turnaround release is
RC on the common net, and at HSI/3 = 8 MHz (T = 125 ns) the
internal pull-up alone (τ ≈ 1.4 µs on ~30 pF) is an order too slow.
Bench-verify on the CI board: deselected-port SDI false-trigger —
a node so triggered drives its own disconnected stub, harmless
until reselected, recovered by session-start resync. PIO bitbang
proven by PicoRVD (quirks §Debug). Per-node power switching (brick recovery)
is required regardless. Live SWIO debugging is single-target by
nature: the mux simply **parks on the DUT** for the GDB session, no
switching overhead. Caveat for live-ring debugging: halting a node
starves its watchdog, so the §4 bypass engages around it — the
designated debug DUT below carries a defeat bit for exactly this.
Programmer tooling (minichlink-class) joins the flake with the node
firmware.

CI control plane (2026-09-29): **all slow control and observe on the
CI board is one long daisy-chained shift register with a global
latch/capture clock** — 74HC595-class stages for control (mux
enables, per-node power switches, fault-injection switches,
human-I/O overrides), 74HC165-class stages for observe. A handful of
RP2040 pins (clock, data out, data in, latch) drives the whole
board; chain length scales with the fault-injection complement
instead of consuming GPIO, and every actuator is one bit — no I2C
addressing, no bus contention, fully deterministic.

Board power and host link (2026-09-30): one **USB-C receptacle** is
both the power inlet and the supervisor's host link. 5 V in — CC
sink pull-downs only, no PD negotiation; the load (8 tiles at tens
of mA each, §2.1, plus RP2040 and the scan plane) sits trivially
inside baseline USB-C delivery — and an on-board **3.3 V regulator**
feeds the ring rail (§2.1) and all board logic. The receptacle's
D+/D− wire to the RP2040's USB (it keeps its 12 MHz crystal for
exactly this, §5), so one cable is power, host channel, and debug
transport uplink. Regulator and connector are inventory-driven picks
(§6); the per-node power-cut switches of the fault complement sit
between the rail and each tile.

Open: runtime debug transport (UART per node? shared bus?). The
segment connector is settled (2026-09-29, §3) — and stays deliberately
fragile: it is the failure mode under test.

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
deform the segment under observation (a §7 layout-checker contract).
The §1 cost driver doesn't apply: this is test infrastructure.

The instrumented boundary node is also the **designated debug DUT**
(2026-09-29): a live SWIO session parks the flash mux on it, and the
two segment taps are already on RP2040 PIO, so one node gets the
full loop — GDB halt/single-step *and* logic-analyzer capture of
what it received vs re-emitted, with the same pins able to inject
crafted stimulus at its RX while stepping. To make halting useful it
carries a **watchdog-defeat bit** in the shift-register chain: while
set, an override holds the §4 bypass switch in the node-active
position, so a halted or single-stepped node stays electrically in
the ring instead of being bypassed on watchdog timeout. Default is
watchdog-in-charge; the defeat bit is a debug-session tool.

Silkscreen documentation (2026-09-26): the CI board is self-documenting
at the bench — **connector pinout voltages and test-point labels printed
on the board** (e.g. `3V3`, `5V`, `GND`, `TP12 ring-seg-3`), so probing
never requires the schematic open on a second screen. Layout-checkable
(§7): every connector and test point carries a silkscreen label.

## 7. Design-capture DSL

Decided: **home-rolled DSL** (not SKiDL). The DSL is the single source
of truth for:

- Schematic (→ KiCad netlist; layout done in KiCad)
- Constraint / property checks
- Firmware pin and register headers
- Analog simulation netlists (ngspice)

Rationale: owning the IR makes multi-target codegen and property
verification straightforward; a KiCad/SKiDL-format emitter is just one
backend. Package scaffold landed 2026-09-26 (see §8 tooling).

DSL shape (2026-09-26, from the initial design interrogation):

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
- **Lean on KiCad's own code where possible** (2026-10-04). When both
  the DSL and KiCad can do a job, drive KiCad rather than re-implement
  it: every line we don't write is a line we don't maintain against
  KiCad releases. KiCad is the merge engine between generated and
  hand-edited artifacts — ref-matched netlist import for connectivity,
  Board Setup's Import Settings from Another Board for constraints;
  the DSL emits and audits. The Import Settings step is itself scripted
  since 2026-10-04: `src/oparroy/dsl/pcb_merge.py` drives the same
  merge through pcbnew's SWIG API (the flake's `kicad-python` wrapper;
  `python -m design.node_board --apply DIR`), keeping layout and
  GUI-authored project state intact while re-imposing the emitted
  constraints.
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
  arguments are a pin-swap factory (the BAT54S x/sel swap, found in
  review, is the proof). Pin names are the keyword names —
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
  preserves unit structure (landed 2026-09-28 — see below), a
  placed part instantiates a **unit subset** (default: all — today's
  behavior), unplaced units materialize no pins so the unconnected-pin
  check stays clean, and a physical pin shared by several placed units
  sits on one net (KiCad ERC's own rule) — structural in the IR,
  where a physical pin number is one `Pin` that can sit on only one
  net. Package-as-one-part
  stays right for units used as a single element: the BAT54S series
  pair is a single unit in KiCad's own library, which is exactly the
  `Bat54s` typed-class choice.
- **Computed values carry slack** (2026-09-27). A computed value
  (divider ratio, filter corner) is a spec — target plus tolerance —
  not a number: the emitter resolves it to a real part from a stocked
  bin (the VDD/2 divider draws from the 10k bin), never an unsourcable
  irrational value. Resolution runs against the parts DB's value
  bins (§6 inventory-driven selection). `Part.value` widens from a
  string to a value-spec type when this lands — a designed change to a
  public constructor parameter, not a patch (KANBAN.md).
- **Captures live in a new `design/` tree.** `circuits/` keeps benches
  and device models until the bench DUTs are ported and the DUT `.cir`
  files retire.
- **Human-review rendering:** a Graphviz dot dump is the minimal first
  view (ugly, but a start); the goal is abstraction-level block views
  in the Verilog-debugger sense — prior-art survey shipped 2026-09-28:
  [docs/prior-art-schematic-gen-2026-09-28.md](docs/prior-art-schematic-gen-2026-09-28.md)
  — borrow the layout engine (grandalf first, ELK fallback), build
  only the view extraction; the views are open work (KANBAN.md).

Landed (2026-09-26; typed parts and review hardening
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
Not yet proven: a real pcbnew netlist *import* — the golden format is
pinned, the ingest is exercised when the first board enters layout.
The KiCad application joins the flake (2026-09-29), pinned to the
library version the DSL validates against, so pcbnew ingest and layout
cannot drift from the validated libraries.

Subcircuit composition (2026-09-28): hierarchy is
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
with content-derived tstamps — the channelization hook. Check and the
emitters flatten implicitly and report hierarchical paths. The §4
watchdog is the first subcircuit (`design/watchdog_chargepump.py`); the
8-instance proving case runs in `tests/test_dsl_subcircuit.py`.
Remainder of that split: multipacking and component sockets (below),
connection sugar (KANBAN.md).

Port arrays and bundles (2026-09-28): the interface scales
past scalar ports. `Circuit.port_array` declares a width-fixed vector
(`led[0]`…`led[7]`) bound element-wise at instantiation — a width
mismatch raises at capture (button matrices, LED arrays); elements may
also bind individually by name. `Circuit.bundle` groups *existing*
nets under member names — the §3 connector pinout as one connectable
unit. Members name wires, not node functions (`a` is the ring-A data
wire on pin 5 of both faces), so two faces join member-to-member; the
power nets alias into both faces' bundles, and a port reached through
two groups must resolve to one parent net — conflicting bindings
raise. `BundleConnector` (parts.py) is the connector block: the
member→pin-number mapping is class data, and `pin_map` values widen to
tuples for a member owning several pins (the §3 ground row and the
doubled 3V3). `design/segment.py` carries the §3 pinout
(`segment_ports`) and the connector block itself (part and footprint
settled 2026-09-29, §3). Both group forms expand to scalar port
bindings at instantiation: flattening, checks, and emitters see plain
nets only. One checker fix rode along: footprint filters match against
the full `Lib:Name` as well as the bare name, so KiCad's lib-qualified
filters (`Connector*:*_1x??_*`) work.

ngspice emitter (2026-09-28): `spice_emit.py` (`emit_spice`)
is the simulation-netlist backend over the flat IR. It emits the DUT
as a `.subckt` with ports in declaration order; stimulus and `.meas`
assertions stay in the external bench decks (`circuits/**/tb_*.cir`) —
the DSL emits the circuit, benches drive it — so a capture whose ports
match a hand-written `circuits/` interface drops into the same benches
unmodified, and either capture can drive the run while the remaining
DUTs are ported over. Spice bindings are ad hoc until the parts DB
owns them: a symbol-keyed table (R/C two-pin primitives, the BAT54S
series-pair expansion) plus caller-passed `.model` definitions, a
part's value naming its model as in a hand-written deck. Emission is
byte-identical like the KiCad emitter's, hierarchy flattens implicitly
(ngspice
accepts `/` in element and node names verbatim), and element names
keep the ref, gaining a kind-letter prefix only when flattening hid it
(`WD1/Rs` → `RWD1/Rs`). Proven by `design/watchdog_chargepump.py --spice`: the emitted `wd_chargepump` passes all three §4 benches
(`tb_engage`, `tb_missed_pulse`, `tb_glitch`) through
`scripts/sim-run` — the DUT-port equivalence pattern, rehearsed.

Port limit ranges and waivers (2026-09-28): typed ports carry
electrical limit **ranges** — `Circuit.port(..., source=…, sink=…)`
taking `Limits(voltage=Interval, current=…)` — and the validation pass
checks **interval containment** over every net's declared endpoints: a
sink's acceptable range must cover the connected source's output range
(PolymorphicBlocks steal, 2026-09-27), so tolerance stackup becomes
checkable data. Voltage is checked when declared, current when both
sides carry it; an undeclared side is no data, not a finding. Grouping
per net — not per binding — covers sibling instances wired
port-to-port through a plain net, the common board-level case. The
check runs over the instance hierarchy before flattening, so findings
and waivers address hierarchical paths (`WD1/ka`). **Waivers are
capture data** — `Circuit.waive(check, path, reason=…)`, never
comment-style suppression: a waived error degrades to a `WAIVED`
finding (visible in the report, not erased, not blocking) and a waiver
matching nothing warns as stale. A waiver declared inside a
subcircuit is relative to it; instantiation prefixes the path.
`design/watchdog_chargepump.py` declares the first contracts (`ka`
accepts 0..3.6 V, `sel` drives 0..3.3 V). Still open: the bypass-path
single-fault and watchdog default-state checks, which need the
board-level captures they inspect, and pin/part-level ranges (today
only ports carry them — port arrays and bundles not included).

Parts DB (2026-09-28): `parts_db.py` holds one record per
part — LCSC number, JLCPCB Basic/Extended tier, a stock snapshot with
its as-of date and source, the KiCad symbol/footprint pair, the spice
model binding, and the datasheet pointer into
[`datasheets/`](datasheets/README.md) — the §6
inventory-driven-selection view as data. Selection is **constraint
filtering over the table**, not lookup: a `PartFilter` is refinement
data (kind, tier, area bounds, an allowed-footprint set, exclusions, a
required part, an in-stock constraint) composing conjunctively, so
assembler-stock status is a column *and* a checkable constraint.
`PartsDb.bind` turns a record into a typed part class — the record
owns symbol/value/footprint — so captures draw their bins from the
table (`design/parts_db.py` binds `R0603`/`C0603`; capture-specific
parts bind at the capture site) instead of re-declaring footprint
pairs per capture, retiring the earlier ad-hoc bin classes.
`PartsDb.check_stock` is the freshness audit: stale snapshots,
never-queried parts, unverified tiers, and stock-outs surface as
warnings (`python -m design.parts_db`); the per-capture
unsourcable-part gate is open work. Stock numbers are as-of-dated
snapshots with provenance, never live data — re-query JLCPCB before
ordering. Full emitter-side resolution against value bins —
the solve pass — is open work (KANBAN.md).

Firmware pin maps (2026-09-28): `pinmap.py` — pins are
requested by function (`gpio.request("keepalive")`), pads bind late as
refinement data (`gpio.bind(keepalive="PD3")`), and the one
authoritative table feeds both consumers: `emit_pin_header` (the
freestanding-C++ header — `constexpr` pads plus peripheral-channel
constants, code-std.md §7 style) and `check_pin_map` (the §5
GPIO-budget check: the bound pad carries every used signal, one
function per pad, reservations honored, requests + reservations inside
the chip's GPIO count). Chip data (`Chip`/`Pad`) is datasheet-derived —
the CH32V003F4P6 table covers the default alternates only (DS0 §2.1,
[gpio-pinout.md](datasheets/CH32V003/notes/gpio-pinout.md)); AFIO
remaps are refinement room, added when a binding needs one.
`design/node_pins.py` is the node table — 16 function requests plus the
SWIO reservation = **17 of
18 GPIO, PC7 spare**, verifying §3's "~16–17 of 18" at pin-map time as
§3 predicted — and `firmware/node/pins.hpp` is the generated
header, byte-pinned by `tests/golden/node-pins.hpp` and compile-proven
on both toolchains (`firmware/node/pins.cpp`: host clang + rv32ec
GCC). Regeneration stays a manual step
(`python -m design.node_pins > firmware/node/pins.hpp`); meson
`custom_target()` wiring lands with the first consumer (the node
firmware). The table's third consumer is the node capture itself
(2026-09-29): `design/node.py` binds its MCU pads from
`capture().assignments` rather than hardcoding them — the drift that
motivated it (the capture had keepalive on PC4 and the LEDs on
PC7/PC5/PC6 against the table's PD3/PD0/PC0/PC1 — a fabbed board
would have kept the watchdog permanently strobed-out and dark) is
the proof that two pad tables cannot coexist.

Node board and the capture→layout stages (2026-09-28): the
ring node is captured in `design/node.py` — CH32V003F4P6
(`design/ch32v003.py`: pins keyword-only by port name, power pins
required, the rest reported unconnected by name via the typed-part
optional-pins hook), the PHY front-end (`design/phy_frontend.py`:
SN74LVC1G3157 bypass with the RX tap on B1, VDD/2 threshold divider
from the 10k bin, ring-B protected RX/TX, 470 Ω + TVS footprint per
§7-checklist terminal, the §2 hysteresis fallback carried as DNP), the
§4 charge pump, the §4.1 status LEDs (power / working / per-connector),
an SWIO test pad, and the two §3 segment connectors. TIM1_BKIN (PC2)
is wired to the watchdog's `sel` — bypass engaging brakes both TX
channels (§2). `Node` is a subcircuit: the node board captures it
directly, and the §6 test board tiles it eight times. Between capture
and pcbnew sit the two stages this section promised: `assign.py`
(footprint overrides
as JSON data on top of the class-default bins, now shared in
`design/bins.py`) and `annotate.py` (capture names → board refdes;
prior annotations survive source edits; comp tstamps are keyed on the
new `Part.identity`, not the refdes, so pcbnew keeps matching by
timestamp across re-annotation; `annotation_from_pcb` folds KiCad's
geographic renumbering back out of `.kicad_pcb`). Typed parts grew
`Led` and `TvsDiode`. Golden: `tests/golden/oparroy-node.net`. Not yet
proven: real pcbnew ingest and the back-annotation join against a real
layout (the caveat above) — first layout is human work, and the §9
node-board stackup question settles at quote time.

Multipacking and component sockets (2026-09-28): the
multi-unit model above lands. kicadlib preserves KiCad's unit
structure — `Symbol.common_pins` (unit 0, present in every placed
unit) and `Symbol.units`; `pins` stays the all-units view and
`Symbol.pins_for_units` resolves a subset. A `MultiUnitPart` subclass
declares the placed subset with typed per-unit pin names
(`unit_pins`); construction places but wires nothing — units wire
individually through typed handles (`connect(net, u1.unit(1).anode)`,
`Part.unit` returning a `UnitHandle`) or pack into component sockets.
The shared physical pin is one `Pin` in the IR, so the one-net rule is
structural: rewiring it to the same net (once per sharing unit) is a
no-op, a second net raises at capture, and a packing that would split
a shared pin across two nets raises at flatten. A component socket
(`Circuit.socket`, a `SocketSpec` subclass naming its protocol pins
and a standalone `default` typed part) lets a subcircuit declare it
needs a *part*, not just nets: the capture wires the protocol pin
handles like part pins, and the instantiating parent directs the
packing — `instance(..., D1=u1.unit(3))` packs the socket into one
unit of a parent-placed package (one unit satisfies one socket),
`D1=SomeDiode` directs the standalone part class, and an unbound
socket materializes as the protocol's default part under the instance
path (`CL0/D1`) at flattening. The subcircuit stays package-agnostic.
`Bat54adw`, `Diode`, and `DiodeSocket` are the first typed parts on
the model; proven in `tests/test_dsl_units.py` and
`tests/test_dsl_sockets.py` against a stub quad diode mirroring the
BAT54ADW shared-anode pinout, plus real-library unit-structure tests
(BAT54ADW, CD4066BE's switch+power units). **Caveat (raised
2026-09-27): packing across the ring-A/B redundancy boundary
reintroduces a single point of failure** — two rings' diodes in one
package share its pins and its silicon. The DSL makes packing the
parent's directed, review-visible choice; it does not (yet) forbid a
cross-boundary pack — that is a checker-level rule for the capture
that needs it, not a socket-mechanism restriction.

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
  segment trace length against the cable-reach budget (§9), keepout
  respect
- KiCad's own DRC stays authoritative for manufacturability; the DSL
  checker covers *project semantics* DRC can't know about. The DSL can
  also *push* constraints the other way — emitting the stackup and
  keepouts into the `.kicad_pcb` and the net classes and board
  minimums into the `.kicad_pro`, so the layout tool guides the human
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
  ≤ 10 kΩ total including the series R
  ([adc.md](datasheets/CH32V003/notes/adc.md), T3-24). The R also
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
  standalone node boards ship populated as well (2026-09-29) — they
  are the first bench articles for the §2/§4 claims. The
  power-rail TVS pairs with the eFuse/crowbar above and is *not*
  optional. Layout-checkable (§7): TVS adjacent to its connector,
  R between TVS and µC pin.
- Rounded corners, mounting holes for legs (layout checker, above)
- **Single-sided SMT; connectors on the back** (2026-09-29): every
  PCBA-placed part sits on the front — single-side SMT keeps the
  JLCPCB Economic tier (§6) — and only the two §3 segment connectors
  sit on the back, SMD, hand-soldered post-PCBA. The front is the
  flat enclosure-wall mount face; the §4.1 status LEDs shine through
  routed PCB holes to the back (2026-09-29, §4.1), visible from the
  connector side — the enclosure owes nothing. Layout-checkable: the
  B.Cu footprint set is exactly the segment connectors, and each
  status LED sits over its routed hole.
- **Programming strip: SWIO + GND + 3V3 pads** (2026-09-29, §6): the
  pogo-jig target for post-SMT programming — three pads together at
  a board edge, 3V3 driven by the programmer, never the ring.
  Layout-checkable: presence, adjacency, edge placement. Geometry
  (2026-09-29): **2.54 mm pitch, three 1.5×1.5 mm pads, on a short
  board edge** — the pogo jig consumes exactly this.
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

Landed (2026-09-28, first slice): the layout checker in
`src/oparroy/dsl/` — `kicad_pcb.py` (a tolerant `.kicad_pcb` parser on
top of `sexpr`: stackup, net classes, footprints/pads, copper, board
outline, silkscreen texts/rects, zones), `layout_check.py`
(`LayoutRules` as the contract, `check_layout` reporting batched
`Issue`s like the schematic pass: copper-layer count and thickness,
net-class width/via compliance, per-net trace-length budgets, min
corner radius with collinear-junction exemption, required silkscreen
board-ID fields, serial-box area, mounting-hole count and keepout
coverage, footprint adjacency and presence, and bypass-net pad
whitelisting — the §4 independence check), and `pcb_emit.py` (a
byte-identical skeleton emitter pushing constraints into pcbnew
pre-audit; round-trips through the parser). Proven against
`tests/fixtures/board_pass.kicad_pcb`. Not yet
landed: copper-geometry independence beyond pad whitelisting, serial
box pad/silkscreen clearance, TVS/series-R placement contracts, and
the channelization hook (per-instance layout replication over the
subcircuit sheetpaths) — these wait for the first real board.

Skeleton emitter, KiCad 10 shape (2026-10-03, verified headless
against KiCad 10.0.6 — `kicad-cli pcb upgrade`/`pcb drc`, exercised
in `tests/test_dsl_kicad10.py`): KiCad 10 rejects `net_class` in
`.kicad_pcb` `(setup)`, so the skeleton is a **pair** —
`pcb_emit.emit_pcb` writes the `.kicad_pcb` (stackup, keepouts, net
list; still format 20240108, pcbnew upgrades on open) and
`pcb_emit.emit_project` writes the `.kicad_pro` (net classes in
`net_settings.classes`, net→class membership in
`net_settings.netclass_assignments` — the key is
`netclass_assignments`, the `class_patterns` spelling is silently
ignored; board minimums in `board.design_settings.rules`).
DRC-enforcement facts the design relies on: per-class clearance and
the board minimums are DRC-enforced headless; net-class track width
is a routing default only, so per-net width/via contracts stay with
the layout checker, which now reads classes from the project
(`kicad_pro.parse_project`, `check_layout(..., project=...)`) with
board-file classes as fallback. Quirks, both documented where the
code hits them: stackup paste layers must not carry
thickness/material (the upgrader mangles them into dielectrics), and
a class clearance ≤ 0.25 mm is enforced but the violation text
reports an empty constraint name (above 0.25 mm it cites the class).
The node board's spec is `design/node_board.py`; the emitted pair
lives in `boards/node/`.

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
node firmware's hook definition lands with the node firmware), `lib::move`
(`utility.hpp` — AK's spelling; `<utility>` stays outside the
freestanding header set, code-std.md §2), and the StaticVector → `Span`
implicit conversion (the `std::vector` → `std::span` analog, AK's
`Vector`/`operator Span` shape) (2026-09-28).
`Error` is a bare `enum class` code, not AK's string-carrying class —
widen to a payload-carrying class the day an error needs more than a
code. Rule set: **project-owned** (decided
2026-09-26) — `code-std.md` at the repo root, borrowing the
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
- **Toolchain consequence (feeds §5):** freestanding C++ needs a real
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
plus custom outputs (KLEE runs, DSL-generated headers per §7). Meson
covers that natively — one cross/native file per toolchain, per-target
flag overrides, `custom_target()` for bitcode/KLEE, and the built-in
test runner driving coverage-on-release (2026-09-28:
clang source-based instrumentation + llvm-cov branch reporting, chosen
over `b_coverage`/gcov — gcov-format data degrades on C++ at -O2, and
llvm-cov reports exact branch coverage with tools already in the
flake's LLVM set). CMake was the
runner-up (toolchain-file ceremony, verbose custom commands); GNU make
loses on the multi-toolchain matrix; tup ruled out (FUSE dependency,
thin ecosystem). Provisioned through the flake like everything else.
The project's default `buildtype` is pinned to `plain` (2026-09-26):
the nix cc-wrapper appends `-D_FORTIFY_SOURCE` *after* all user
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
  direction-flap policy is not.
- **Debug transport** (§6) — per-node UART vs shared bus, connector
  style.
- **Node-board stackup and thickness** (§6) — **resolved 2026-09-29:
  2-layer, 0.8 mm.** The §1 cost driver won: the board is tiny,
  single-sided, and its back is two connectors plus pass-through, so
  4-layer's routing room buys nothing. 0.8 mm over 1.0 mm for feel,
  accepting more flex under the IDC mating shear the hand-soldered SMD
  headers take (§3). JLCPCB's exact 2-layer thickness offerings verify
  at quote time.
- **Cable reach** (§2) — maximum segment length unamplified, and with
  an amplifier/re-driver node in the segment; line coding is settled
  (§2), so this is drive strength, comparator sensitivity, and cable
  characteristics.
  Answered by simulation first, then measured on the test board.
- **Coverage threshold gate** (§8) — the coverage instrumentation
  (2026-09-28) measures branch coverage of the release build (llvm-cov,
  informational only: 82% of
  122 branches at landing). Whether to gate the build on a threshold,
  and at what red line, is undecided; the infrastructure supports it
  (`llvm-cov export` JSON) once the suite matures. Also open: whether
  the shipped node image builds at the measured `-O2` or at `-Os`
  (16 KB flash). No card yet.
