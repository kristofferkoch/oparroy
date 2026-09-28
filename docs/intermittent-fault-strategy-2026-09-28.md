# Intermittent-fault strategy — re-route vs auto-bypass (T13)

Analysis date 2026-09-28, card T13. This memo recommends; the decision
itself is the project owner's, and DESIGN.md §9 keeps the question open
until ratified. Numbers cited from DESIGN.md §1–§8 and the T4/T5
benches they summarize.

## 1. The fault and the question

Connectors are the ring's deliberately fragile element (§6) and its
dominant failure mode. A worn or half-seated contact doesn't fail
cleanly: it bounces — open/remake cycles at mechanical, ms-class rates,
possibly mid-frame. DESIGN.md §3 settles the substrate
(counter-rotating dual ring, firmware RX source select) and defers
exactly one question to this card: the **flip/hysteresis policy when
the fault is intermittent rather than permanent**. Permanent faults are
already covered — no edges for > 2 frame times ⇒ flip source, every
node stays reachable (§3).

The three candidate strategies:

1. **Protocol re-route only** — firmware flips the RX source between
   ring A and ring B (the §3 mechanism, already built); no new
   hardware.
1. **Hardware auto-bypass only** — a per-segment analog fault sensor
   throws a §4-style SPDT bypass without firmware.
1. **Both** — re-route as the primary mechanism, hardware as an
   escalation and containment layer.

## 2. What the detection hooks actually see

The card names three hooks; measured against the T5 numbers, they say
the analog half of the intermittent problem is already solved and what
remains is pure policy:

- **Pull-down-parked idle-low segment** (§2 measured block, tb_fault):
  with the internal weak pull-down enabled on both OPP inputs (§3), an
  open segment parks idle-low, chatter-free, comparator static ≤ 33 µs
  even at 1 nF — ~12× inside the 2-frame flip budget. A short to
  GND/VCC parks equally static, and idle-high is distinguishable from a
  dead-quiet segment. Consequence: connector bounce decomposes into a
  sequence of *clean* open/remake events — during every open phase the
  line sits quiet at a rail, never at an ambiguous mid-level. The
  chatter hazard intermittent faults usually pose is eliminated in
  hardware at zero BOM cost.
- **Edge timeout** (§3): no edges for > 2 frame times ⇒ flip. One
  detector catches opens and both short polarities alike — a parked
  line has no edges regardless of which rail it parks on.
- **Illegal-cell detection** (§2): a contact that remakes *mid-cell*
  injects garbage periods; period outside 0.9–1.6 µs ⇒ stop
  regenerating, force the line idle. T5 measured a healthy segment at
  1245–1253 ns period with ≥ 178 ns of margin everywhere (tb_decode) —
  an illegal-cell trip is never a false positive on healthy hardware,
  so the trip counter doubles as a per-node flap-quality signal.
- **Frame-length cap** (§2): > 2048 legal cells without a break ⇒
  babble containment, mute until the next break. Bounds the blast
  radius of anything a node re-transmits while its source is flapping.
- **Supervisor frame-echo comparison** (§2 closure discipline, §3):
  the supervisor originates on both rings and drains both; echo
  mismatch on either drain ⇒ fault. First-divergence position in the
  echoed frame localizes the faulty segment, and the mismatch *pattern*
  across many frames separates intermittent (scattered mismatches,
  stable position) from permanent (one clean cut). This is the
  repairability hook (§1 driver 3, §4.1) — and the supervisor may cost
  freely (§1).
- **Vsync double-buffer** (§2): command outputs apply only on a clean
  frame break. Mid-flap garbage never reaches the apply stage, so
  flapping costs bandwidth, never torn outputs.

The hardware layer's measured envelope (§4) bounds option 2: the
charge-pump bypass engages ~0.5 ms after the last keep-alive edge, is
node-scoped and ring-A-only, and **bit-level bypass switching is
neither needed nor achievable with this class of circuit**. Its known
hazard is the mirror image of the intermittent problem — a µs-wide
periodic waveform is a false keep-alive (tb_glitch). Dumb analog
hardware cannot tell a flapping contact from a live link.

## 3. The options

### Option 1: protocol re-route only

The mechanism exists (§3). The open part is flap behavior. The naive
policy — flip on silence, flip back on first traffic — chases a
bouncing contact: ms-class bounce against a ~0.6 ms circulation means
re-flips every few frames. Each flip costs the node, and everything
behind it on that direction, ≤ 2 frame times of outage. Safe (the
vsync gating above), but wasteful, and the supervisor's echo sees a
strobe of mismatches. This option needs hysteresis regardless; with
hysteresis it becomes the recommendation in §4.

### Option 2: hardware auto-bypass only

Fails three ways:

- **Nothing to build it from.** The §4 bypass engages on keep-alive
  loss — MCU death. An intermittent *segment* fault leaves the MCU
  alive and strobing, so the watchdog never fires. A
  segment-fault-triggered bypass is new hardware: an analog link-loss
  sensor per segment plus switch control — new per-node parts against
  the §1 cost driver.
- **Wrong scope.** The 1G3157 bypass bypasses a *node*, not a
  *segment*, and exists on ring A only. An open connector sits between
  nodes; bypassing either neighbor doesn't heal it. The dual ring
  already routes around it for free.
- **Can't judge intermittency.** "Flapping vs recovered" is a
  statistical judgment over milliseconds, and analog activity detection
  misjudges exactly this class of signal — §4's measured
  false-keep-alive hazard. Bit-level auto-switching is out regardless
  (§4).

### Option 3: both — layered by fault class

Not two mechanisms for the same fault, but a split by fault class, all
on existing hardware:

- **Intermittent or permanent segment fault** → protocol re-route with
  anti-flap hysteresis (option 1, hardened).
- **MCU death or hang** → the §4 charge-pump bypass, unchanged and
  already settled.
- **Unstoppable flapping** → deliberate self-bypass as the terminal
  containment state: firmware stops the keep-alive, the §4 bypass
  engages in ~0.5 ms, the node goes listen-only (bypass cuts TX only,
  §4), its working LED goes dark (§4.1) and the failure is visually
  obvious. This is the same mechanism §8 assigns to the VERIFY failure
  hook — one new trigger, zero new hardware.

## 4. Recommendation

**Adopt option 3 in its layered form: protocol re-route with hysteresis
as the only response to segment faults, the hardware bypass retained
for MCU death, deliberate self-bypass as the escalation rung. No new
hardware.** Hardware auto-bypass for segment faults is rejected per the
option-2 analysis.

Concrete policy, for ratification — the constants are starting points
to be tuned on the test board (T10/T12), not decisions:

1. **Flip on silence** — unchanged from §3: no edges for > 2 frame
   times on the selected source ⇒ flip.
1. **Stable-time hysteresis on flip-back** — after any flip, require
   K consecutive clean frames (start: K = 16, ≈10 ms at the baseline
   circulation) on a direction before it may be re-selected. "Clean" =
   no illegal-cell trip, no frame-cap mute, break where expected.
1. **Flip-rate cap** — at most 1 flip per 32 frames. A second silence
   inside the window is absorbed by staying put: the other direction
   still carries the frame (symmetric rebroadcast, §3), so staying put
   costs nothing.
1. **Flap latch** — F flips inside a window (start: 8 flips/s) latches
   the node onto its current direction and raises a fault flag in its
   telemetry slot; the supervisor's echo comparison plus the §4.1
   per-connector LEDs point repair at the exact segment.
1. **Supervisor escalation** — if the flap flag persists across a
   supervisor-set budget, the supervisor commands the node (command
   slot, T11 frame format) to self-bypass: keep-alive stops, the §4
   bypass engages, the node goes dark-and-listening, ring A heals
   around it, ring B covers it (§3's dead-MCU case, entered
   deliberately).

Why this is safe under flapping: the §2 vsync double-buffer applies
outputs only on a clean break; illegal-cell and frame-cap mute contain
garbage before it propagates; positional addressing is
source-invariant, so a node counts slots from the break identically on
either direction (§3). The worst-case service cost per flap event is
the ≤2-frame detection outage, and the hysteresis converts contact
chatter into at most a handful of such events before the latch.

Trade-offs accepted:

- **Slower re-preference of a healed direction** — the stable-time
  hysteresis delays re-adoption of a recovered segment by K frames.
  Service is unaffected; both directions always carry the frame (§3),
  so only the node's preferred *source* lags.
- **Ring-B asymmetry during self-bypass** — a self-bypassed node drops
  off ring B (TX_B floats) while ring A bypasses it; the coverage
  argument is §3's dead-MCU case, unchanged.
- **Constants are guesses** until the CI board's scriptable open/short
  injection (§6) generates real bounce profiles and the instrumented
  boundary node (§6) observes flip behavior at 8 ns resolution to
  validate them.

## 5. What stays open after ratification

- The constants (K, flip window, F) — tune on the test board, T10/T12.
- Telemetry bits for flap counters and the fault flag, and the
  command-slot encoding for self-bypass — T11 frame-format scope.
- Whether the §4.1 per-connector status LED encoding shows flap state
  directly (its activity/no-signal/error encoding is already TBD).
- A proof obligation for T11/T16: the flap policy is host-testable
  logic (§8), so the state machine goes under KLEE/fuzz harnesses with
  the invariant *flips never exceed the rate cap* — the policy is only
  as good as that proof.
