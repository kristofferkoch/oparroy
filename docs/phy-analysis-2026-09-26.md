# PHY analysis — line coding, bit rate, re-timing, addressing (T3)

Analysis date 2026-09-26, card T3. Decisions are recorded in DESIGN.md
§2; this file keeps the reasoning. Hardware facts cited from the
CH32V003 notes (`datasheets/CH32V003/notes/`, abbreviated DS0/RM per
their conventions).

## 1. Line-coding candidates

Constraints going in:

- Nodes run on the internal HSI oscillator — no crystal, the §1 cost
  driver forbids one. HSI accuracy ±1.6/−1.2 % (0–70 °C), ±2.2 %
  (−40–85 °C) (DS0 §3.3.6 T3-11).
- RX front-end is the on-chip OPA as a comparator: 12 MHz GBW,
  7.7 V/µs slew, 520 ns wake-up, **no documented hysteresis** (DS0
  §3.3.15 T3-26; opa.md). Output routes internally to TIM2_CH1 capture.
- TIM2 has a PWM-input mode that captures period + high-time per cycle
  with zero ISR work (RM §11.3.4), and both captures are DMA-able at
  once (TIM2_CH1 → DMA ch5, TIM2_CH2 → DMA ch7 — dma.md).
- 48 MHz core: one 800 kbit/s cell (1.25 µs) = 60 clocks; capture
  resolution 20.8 ns (DS0 §3.3.11 T3-20).
- 2 KB SRAM bounds frame buffers.

| Candidate                                          | Self-clocked under ±2.2 % HSI?                                                       | Constant cell time?                     | HW decode fit                                         | Verdict                                                                                  |
| -------------------------------------------------- | ------------------------------------------------------------------------------------ | --------------------------------------- | ----------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| **PWM cells, ratio-metric decode** (WS2812-shaped) | Yes — ratio is clock-invariant to first order                                        | Yes                                     | TIM2 PWM-input mode + DMA, per design                 | **Chosen**                                                                               |
| Pulse-distance (fixed pulse, variable gap)         | Yes                                                                                  | No — slot timing becomes data-dependent | Same capture HW, but gap measurement                  | Rejected: jitter in slot positions, longer average cell; only win is lower switching EMI |
| Manchester                                         | Yes                                                                                  | Yes                                     | Needs phase tracking per cell; no timer mode does it  | Rejected: halves rate, buys DC balance we don't need (DC-coupled wire, no transformer)   |
| UART async (8N1)                                   | **No** — two HSI ends sum to 4.4 % worst case vs the ~±2 %/end async sampling budget | Yes                                     | USART exists, but byte framing fights gap/slot tricks | Rejected on clock tolerance alone                                                        |

## 2. The coding, concretely

A bit is one fixed-length cell, high-then-low. Value = high-time /
period, threshold 0.5. Nominal at 800 kbit/s (1.25 µs cell):

- T0H ≈ 0.40 µs (ratio 0.32), T1H ≈ 0.80 µs (ratio 0.64) — WS2812's
  own numbers, so the wire signal is COTS-compatible: logic-analyzer
  WS2812 decoders, RP2040 PIO reference code, and WS2812 test gear all
  work unmodified.
- Receiver accepts cell period 0.9–1.6 µs. Frame/latch marker: line
  low ≥ 50 µs.

Why the spec is the **ratio**, not WS2812's absolute ±150 ns windows:
a local clock error scales high-time and period together, so the ratio
is clock-invariant to first order. The absolute period window then
tolerates roughly +39 %/−22 % frequency error, and the 50 µs gap sits
30× above the longest legal cell. HSI's ±2.2 % is an order of
magnitude inside the budget — **no per-node crystal, ever, by design
rather than by luck**. Per-cell margin vs the 0.5 threshold is
±0.13–0.18 ratio units (±160–220 ns of high-time); comparator offset
(±3 mV typ on a 1.65 V swing) and ICxF filter sampling error are
nanosecond-class and fit trivially.

TX quantization at 48 MHz: 20.8 ns/count → T0H = 19 counts (395 ns,
ratio 0.317), T1H = 38 counts (792 ns, ratio 0.633), cell = 60 counts.

## 3. Re-timing and jitter: does the ring relax accumulation?

The DESIGN.md §2 question was whether closing the chain into a ring
relaxes jitter accumulation. Answer: **the question was mis-framed —
regeneration, not topology, is what bounds jitter.** WS2812 daisy
chains already reshape at every node; a ring of regenerating nodes has
the same per-hop bound. What actually matters:

1. **Per-hop decode error never accumulates** as long as every node
   regenerates from its own clock. Each hop's jitter is independent
   and bounded by that hop's decode/re-encode error. True for chains
   and rings alike.
1. **Ring closure discipline** is the genuinely ring-specific hazard:
   bits recirculate forever unless someone drains them. Rule: the
   supervisor is the *only* frame originator and drainer; nodes only
   rewrite their own slot. Duplication/loss becomes a protocol-level
   invariant the supervisor can assert (frame it sent ≠ frame it got
   back ⇒ fault), which feeds T13's intermittent-fault strategy.
1. **Circulation-time drift**: total loop time is the sum of per-node
   delays, each ±2.2 % worst case, so frame arrival period at the
   supervisor wanders by a few percent. Ratio-metric decode makes this
   harmless — no absolute timing anywhere downstream of a node's own
   regenerate step. The supervisor runs on a crystal timebase (RP2040,
   §5) and is the ring's timing reference.

**Forwarding granularity: per-bit cut-through, slot rewrite on the
fly** (user decision 2026-09-26, superseding this analysis's initial
store-and-forward baseline). Full-frame store-and-forward pays
N×frame-time of latency for a per-hop validation opportunity the
protocol doesn't use; WS2812 and EtherCAT both stream instead. A node
passes every bit through after a short pipeline delay and only
intercepts its own slot: command bits are read and telemetry bits
substituted as the slot streams past.

Mechanics on the CH32V003:

- RX: OPA → TIM2 PWM-input capture → DMA ch5/7 circular buffers (as
  above).
- TX: TIM1 PWM, CCR values streamed by DMA from a circular buffer
  (TIM1_UP → DMA ch2).
- Firmware per cell: snap the captured high-time to {0,1}, write the
  matching CCR pair into the TX buffer ahead of the transmit pointer,
  decrement the bit counter. At the own slot's arrival: read command
  bits / substitute telemetry bits instead of passing through.
- Buffering and CPU budget (bounded, 2026-09-26): pipeline depth is a
  firmware tunable, order 8–16 cells. RAM per cell: RX two 32-bit
  captures = 8 B (4 B at 16-bit packing), TX one 16-bit CCR = 2 B → a
  16-cell pipeline ≈ 160 B total. Ring buffers are statically
  allocated and capped at **256 B — 1/8 of SRAM**: some buffering to
  buy CPU slack, never enough to become a RAM problem. CPU: DMA
  half-transfer interrupts pace batch processing — an 8-cell batch
  arrives every 10 µs (480 cycles) and costs ~120–240 cycles to snap
  and queue, ≤50 % duty with interrupts live between batches. No
  frame-long masked critical section needed; node application work
  (ADC, buttons, I2C) interleaves between batches and frames.

Latency: circulation ≈ frame time + N×(pipeline + slot processing)
≈ 425 µs + 8×~20 µs ≈ **0.6 ms ⇒ ~1.6 kHz full-ring update** — ~13×
better than store-and-forward, and interactive feel stops being a
function of frame size. (Per-hop latency is the pipeline depth by
construction; the tunable trades latency against CPU slack, and the
256 B cap bounds how far that trade can run.)

What this changes elsewhere:

- **Slot location by bit count.** The node knows its position
  (addressing, §6) and counts bits from the frame gap; no field
  parsing is needed during transit, just boundary counting.
- **ENUM frames are pre-sized** with empty slots; stamping = slot
  rewrite, never insertion. Insertion would stretch the frame
  mid-transit and break every downstream node's bit count.
- **Per-hop error containment weakens**: a corrupt frame is already
  downstream before a CRC could reject it. Per-hop defense moves to
  illegal-cell detection (period outside 0.9–1.6 µs ⇒ stop
  regenerating, force the line idle); babbling-idiot containment then
  rests on the hardware bypass (DESIGN.md §4) and supervisor-side
  CRC/sequence checks — an input to T13.
- **Fallback rung**: if the per-bit loop misses timing on-target,
  degrade to store-and-forward. T11 brings up store-and-forward first
  for correctness, then switches the forwarding loop to cut-through
  and measures.

## 4. Bit rate

**800 kbit/s nominal.** Rationale:

- Proven rate for comparator-class RX on sub-$1 MCUs; the OPA's
  12 MHz GBW / 7.7 V/µs slew is nowhere near the bottleneck (opa.md:
  comparator timing is not the limiting factor at 60 clocks/cell).
- COTS WS2812 ecosystem compatibility (decoders, PIO code, fixtures).
- DMA load: 2 transfers per cell × 800 kHz = 1.6 M transfers/s on the
  AHB — comfortable at 48 MHz.
- The comparator leaves headroom for 2–4 Mbit/s later; not the
  baseline because nothing in the application traffic needs it and
  every margin (cable reach, T15; EMI; decode) shrinks with rate.

## 5. Signaling levels and the RX front-end

- **3.3 V single-ended**, push-pull TX direct from a timer/GPIO pin
  (±8 mA spec drive, DS0 §3.3.9 T3-17 — plenty for a node-to-node
  segment). 3.3 V matches the RP2040 supervisor natively; no level
  shifting anywhere on the test board.
- RX threshold: VDD/2 from a resistor divider on an OPA negative input
  (OPN0 = PA1 or OPN1 = PD0), positive input from the line
  (OPP0 = PA2 or OPP1 = PD7).
- The OPA has **no documented hysteresis**. Baseline: no analog
  hysteresis; glitch rejection from the TIM2 input digital filter
  (ICxF, RM §11.4.7) plus ratio-decode margins. **Confirmed by T5
  simulation (2026-09-26, `circuits/phy-segment/tb_noise.cir`)**: no
  spurious edges under ringing or ±250 mV-class crosstalk, worst duty
  error ~1.2 ns; the feedback-resistor fallback (OPO = PD4, the
  internal TIM2_CH1 route doesn't need the pin) stays unpopulated.
- OPCM (RM §3.2.2: OPA-high → system reset) is a hardware
  "line active" wake option — noted for the sleep story, not part of
  the PHY baseline.

Why not the plain GPIO digital input as the RX buffer (question raised
2026-09-26, recorded here with the decision):

- **Threshold placement.** Ratio-metric decode slices each cell at
  VDD/2, symmetric on both edges. The Schmitt buffer's guaranteed
  window at 3.3 V is VIL ≤ 0.76 V … VIH ≥ 1.68 V (DS0 §3.3.9 T3-16) —
  the real trip points sit anywhere in that ~0.9 V band, centered near
  0.37×VDD, not VDD/2. The OPA's divider threshold is exact,
  supply-tracking, and ±3/±13 mV offset (DS0 §3.3.15 T3-26).
- **Tolerance × slow edges = pulse-width distortion.** Cable RC
  softens edges; ±0.45 V of threshold uncertainty at 100 ns/V is ±45 ns
  of high-time error per edge, asymmetric rising/falling — against a
  ±160–220 ns decode margin (§2). Comparator offset is ns-class at any
  tolerable edge rate.
- **Routing.** OPA output routes internally to TIM2_CH1 — no pin
  spent — and OPA_PSEL is the dual-ring input mux (DESIGN.md §3). A
  digital input costs a TIM2-mappable GPIO per direction.
- **Headroom.** Divider threshold is tunable; hysteresis is one
  resistor away (above); analog observability (impedance probing,
  capacitance survey — IDEAS.md §Fault tolerance) needs a quantitative
  line view a binary buffer can't give. The Schmitt's one advantage —
  documented 150 mV hysteresis — is small, fixed, and off-center.

## 6. Addressing / node ID

**Positional addressing, discovered by enumeration — no solder
bridges, no provisioning step.**

- Position in the ring *is* the address; the ring hands us ordering
  for free, which neither a bus nor a chain-with-bridges does.
- Enumeration: the supervisor originates an ENUM frame with an empty
  ID list; each node stamps its slot with its factory **96-bit UNIID**
  (ESIG at 0x1FFFF7E8, RM ch.15 — flash-option-bytes.md) plus a type
  byte. One circulation builds the position ↔ UNIID map. Replacing a
  node just changes the map; re-enumeration is cheap and can be
  triggered on any supervisor-seen inconsistency.
- Trill-style tri-state solder bridges (bela-lessons §2) lose here on
  two counts: ≥2 GPIO on an 18-GPIO part whose pin budget is already
  spoken for (OPA pair, TX, 3 status LEDs, SWIO, I2C, ADC, button,
  buzzer — §5), and extra per-node parts against the §1 cost driver.
  The bridges solve "which of N identical sensors am I on a bus" — a
  problem the ring topology doesn't have.
- **Node personality**: one firmware image (T11), type byte from a
  flash config location (option-byte Data0 or a flash data page), with
  auto-detect from populated peripherals where cheap. The type byte
  rides in the ENUM stamp, so the supervisor's auto-detect mirrors
  Trill's host-library behavior without any node-side strapping.

## 7. Telemetry: slotted, not polled

**Each node owns a slot in the circulating frame.** On frame arrival
the node samples its inputs synchronously and rewrites its slot as the
frame passes through; the supervisor reads every node's telemetry from
one returned frame. Consequences:

- Sampling is synchronous in the ring's timebase — the Bela lesson
  (§1: sensors sampled in the engine's timebase, zero control jitter
  by construction) transferred to a ring.
- No poll round-trips: telemetry latency = circulation period,
  deterministic and identical for every node.
- Timestamps per se are unnecessary — the frame's circulation count
  *is* the timestamp; the supervisor can version frames with a
  sequence counter in the header.
- Precedent: EtherCAT's logical ring processes frames on the fly at
  each slave — same shape here, at per-bit cut-through granularity
  (§3).
- **The frame gap doubles as a ring-wide latch — WS2812's "global
  shutter" transferred to inputs *and* outputs** (user direction
  2026-09-26). On the gap, every node (a) applies the previous frame's
  command outputs from a double buffer and (b) samples its inputs for
  the coming frame's slot. All slots in frame k therefore hold values
  from the same instant L_k, and all outputs from frame k take effect
  together at L\_{k+1}: the ring behaves as one instrument sampled at
  the vsync rate, not as N independent peripherals. Without the latch,
  output changes would tear across positions and sensor reads would be
  skewed by position — the rolling-shutter failure mode WS2812's
  reset-latch exists to prevent.
- Skew honesty: the latch event itself propagates around the ring, so
  simultaneity is bounded by accumulated pipeline delay (≤ N×depth,
  ~160 µs at the baseline) — sub-perceptual for human interface, fine
  for correlated sensing (button chords, gestures, accelerometer
  arrays), but not a substitute for hardware trigger lines where
  microsecond-class simultaneity is needed.
- Cost: one double-buffer stage per node (bytes, inside the 256 B
  cap); the gap detector already exists to reset the bit counter, so
  the latch event is free. Output latency: one circulation (~0.6 ms)
  from command to effect.

Frame format detail (header fields, CRC, slot sizing per type) is T11
scope; §2 records only the slotting principle.

## 8. What this feeds

- **T5 (PHY sim)**: validate no-analog-hysteresis baseline under noise
  / ringing / connector-fault cases; comparator threshold tolerance;
  drive strength vs segment capacitance.
- **T11 (firmware v0)**: PWM-input + DMA RX path, TIM1/DMA TX path,
  the per-bit cut-through forwarding loop (bring-up order:
  store-and-forward for correctness, then cut-through + measurement),
  frame format, ENUM protocol, type-byte personality.
- **T16 (verification harness)**: add the slot-boundary bit-count
  state machine to the harness targets — it is the piece of
  cut-through with the most invariant surface (off-by-one ⇒ wrong
  node addressed).
- **T15 (cable reach)**: now has concrete signaling (3.3 V, 800 kbit/s,
  push-pull 8 mA) to build RLGC models against.
- **T13 (intermittent faults)**: supervisor-side frame echo comparison
  plus illegal-cell detection are the detection hooks.
