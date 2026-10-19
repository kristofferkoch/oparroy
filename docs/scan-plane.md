# Scan control/observe plane — design

Settles the shift-register control/observe plane that DESIGN.md §6 left
as prose: one daisy-chained shift register carries all slow control and
observe on the CI board. This doc fixes the chain topology and
partitioning, the full bit inventory and maps, the power-on-reset
discipline (the reset-state equivalence proof's inputs,
[src/oparroy/dsl/equivalence.py](../src/oparroy/dsl/equivalence.py)),
and the SWIO flash-mux pick that
[docs/instrumented-ci.md](instrumented-ci.md) §8 delegated here. The
fault-injection switches, per-node power cut, human-I/O overrides, and
boundary tap set themselves are settled in instrumented-ci.md; this doc
drives their control bits.

Consumers: the CI board capture (chain as DSL subcircuits), the
supervisor firmware (bit maps and transaction semantics), the
equivalence proof (§4's reset levels).

## 1. Architecture: one daisy chain

**11 × 74HC595 (control) + 2 × 74HC165 (observe) in a single daisy
chain** from the RP2040 and back:

```
RP2040 ──SER──▶ AUX0 ─▶ AUX1 ─▶ AUX2 ─▶ T0 ─▶ … ─▶ T7 ──▶ OBS0 ─▶ OBS1 ──QH──▶ RP2040
   (595 stages = control; 165 stages = observe)
   SRCLK to all 13 stages; COMMIT to all 13 (RCLK on 595, SH//LD on 165);
   /OE on the 595 stages only.
```

- **One chain, both directions.** The 165 observe stages sit at the far
  end of the same shift path: every 104-clock transaction shifts 88 new
  control bits in through the 595s while 16 observe bits stream out.
  Control and observe share SRCLK; there is no second clock domain, no
  addressing, no bus contention — every actuator is one bit at a fixed
  position (§6's rationale, now concrete).
- **COMMIT is one net with two meanings.** RCLK on the 595s is
  edge-sensitive (rising edge copies shift → storage,
  [SCLS041J](../datasheets/SN74HC595/notes/facts.md) Table 8-1);
  SH//LD on the 165s is level-sensitive (asynchronous capture while
  low, [SCLS116H](../datasheets/SN74HC165/notes/facts.md) Table 1).
  COMMIT idles high; a transaction ends with a low pulse — the falling
  edge captures observe, the rising edge latches control.
- **Shifting is glitch-free.** 595 outputs change only on the RCLK
  rising edge, never while clocking; the 165 parallel inputs are
  read only at capture. The chain can be clocked at any speed or
  stopped mid-byte with zero effect on the board.
- **Observe lags commit by one transaction.** The capture edge comes
  before the latch edge within a transaction, so the observe word read
  during transaction N+1 reflects the board state under transaction
  N's control word. At any practical clock (a full transaction is
  ~100 µs at 1 MHz) the delay is irrelevant to the harness; firmware
  that wants "commit, then read the effect" issues two transactions.

Chain scaling is a firmware constant: a future control bit adds a stage
to the middle of the chain and one byte to the transaction. The 79/16
split below fills the observe stages exactly and leaves **two spare
control bits** in AUX2, plus seven spare outputs in the measurement
tile's slice (§3).

## 2. Partitioning: per-tile slices + supervisor aux stages

Control is partitioned **per tile, one 595 per tile**, not by function:

- The per-tile fault/override complement is exactly 8 bits
  (instrumented-ci.md §7, transforms F1–F8), so **each tile carries one
  595 as its control slice** — 8 identical stages, co-located with the
  tile they drive, declared once in the capture (the same
  sheetpath-keyed one-declaration pattern as the transform list). Tile 6
  is the exception in use, not in hardware: the measurement tile
  (instrumented-ci.md §12) drops F1–F7, so its slice drives only `PWR`
  and the seven other outputs land on internal spare nets
  (`t6_spare1..7`, no pull-downs — the AUX2 spare precedent, §3).
- The per-role extras — the supervisor originator port's injector (6),
  the SWIO tree selects (3), the boundary node's watchdog defeat (1),
  the four input tiles' overrides (12) — total 22 bits and fill **three
  aux stages (AUX0/AUX1/AUX2) at the supervisor end** (two spare).
  Per-role extras are
  per-instance capture additions anyway; giving the boundary and input
  tiles a second stage each would cost a package per tile and break
  tile uniformity for the thirteen slow static lines (1 defeat + 12
  override) routed there.

Observe is **2 × 74HC165 grouped at the supervisor end**, 16 bits:
per-tile `sel` (bypass state — the truthful node-health bit) and
per-tile `3V3N` (coarse power bit; a back-fed cut rail can float above
VIH and read "on" — `sel` is the authority, instrumented-ci.md §8).
Interleaving one 165 per tile is rejected (§9): the sense wires run
supervisor-ward regardless, so per-tile stages would spend 8 packages
on 2 bits each.

All twelve stages run from the **always-on `3V3` rail** — never `3V3N`:
the chain must survive per-tile power cuts, and a mid-chain stage on a
cut domain would sever the daisy for every downstream tile. This
matches the injector switches' always-on placement (instrumented-ci.md
§3).

## 3. Bit maps

Bit numbers are per-stage, bit 0 = `QA` … bit 7 = `QH`. Wire order:
firmware shifts 13 bytes per transaction; the first two bytes are
don't-care pad (they land in the 165 stages), then `AUX0`, `AUX1`,
`AUX2`, `T0` … `T7`; the first two bytes received are `OBS1` then
`OBS0`.
**Every control bit reads 0 = plain-board state** (§4).

Per-tile control byte `T0`–`T7` (the F1–F8 transform set,
instrumented-ci.md §7):

| Bit | Name     | 0 = plain board      | 1 =                           |
| --- | -------- | -------------------- | ----------------------------- |
| 0   | `BRK_A`  | `TX_A` pass-through  | `TX_A` open                   |
| 1   | `SHG_A`  | shunt absent         | `TX_A` short to GND via 470 Ω |
| 2   | `SHV_A`  | shunt absent         | `TX_A` short to 3V3 via 470 Ω |
| 3   | `BRK_B`  | `RX_B` pass-through  | `RX_B` open                   |
| 4   | `SHG_B`  | shunt absent         | `RX_B` short to GND via 470 Ω |
| 5   | `SHV_B`  | shunt absent         | `RX_B` short to 3V3 via 470 Ω |
| 6   | `KA_CUT` | keep-alive connected | keep-alive cut (hang sim)     |
| 7   | `PWR`    | tile powered         | tile power cut                |

Tile 6 (the measurement tile, instrumented-ci.md §12) is the
exception: its byte carries only bit 7 (`PWR`); bits 0–6 are spare
outputs on internal nets (`t6_spare1..7`, no pull-downs).

`AUX0` — supervisor originator-port injector + SWIO tree low bits:

| Bit | Name            | 0 = plain board                                        |
| --- | --------------- | ------------------------------------------------------ |
| 0–5 | `BRK_A`…`SHV_B` | supervisor→tile-0 segment, same order as the tile byte |
| 6   | `SWIO_A0`       | SWIO tree select, level 0 (§5)                         |
| 7   | `SWIO_A1`       | SWIO tree select, level 1                              |

`AUX1` — SWIO tree high bit, boundary defeat, input tiles 1/3 overrides:

| Bit | Name        | 0 = plain board                    |
| --- | ----------- | ---------------------------------- |
| 0   | `SWIO_A2`   | SWIO tree select, level 2          |
| 1   | `WD_DEFEAT` | watchdog in charge (boundary node) |
| 2   | `POT_SEL1`  | tile 1 pot: human control          |
| 3   | `BTN_A1`    | tile 1 button A: released          |
| 4   | `BTN_B1`    | tile 1 button B: released          |
| 5   | `POT_SEL3`  | tile 3 pot: human control          |
| 6   | `BTN_A3`    | tile 3 button A: released          |
| 7   | `BTN_B3`    | tile 3 button B: released          |

`AUX2` — input tiles 5/7 overrides, two spare:

| Bit | Name       | 0 = plain board           |
| --- | ---------- | ------------------------- |
| 0   | `POT_SEL5` | tile 5 pot: human control |
| 1   | `BTN_A5`   | tile 5 button A: released |
| 2   | `BTN_B5`   | tile 5 button B: released |
| 3   | `POT_SEL7` | tile 7 pot: human control |
| 4   | `BTN_A7`   | tile 7 button A: released |
| 5   | `BTN_B7`   | tile 7 button B: released |
| 6–7 | —          | spare                     |

Totals: 57 tile (7 × 8 + the measurement tile's lone `PWR`) + 6
supervisor-port + 3 SWIO + 1 defeat + 12 override =
**79 control bits in 11 × 74HC595** (two spare in AUX2, seven spare in
T6's slice;
instrumented-ci.md §8's 76 + the 3-bit SWIO select).

Observe bytes (165 inputs `A`–`H` map to bits 0–7; `H` shifts out
first):

| Byte   | Bits 0/1            | Bits 2/3 | Bits 4/5 | Bits 6/7 |
| ------ | ------------------- | -------- | -------- | -------- |
| `OBS0` | `sel`/`3V3N` tile 0 | tile 1   | tile 2   | tile 3   |
| `OBS1` | `sel`/`3V3N` tile 4 | tile 5   | tile 6   | tile 7   |

## 4. Power-on reset: the constructed zero state (proof input)

**The silicon gives no POR state.** SCLS041J specifies no power-on
content for the 595 storage register — outputs are indeterminate from
VCC ramp until the first RCLK
([datasheets/SN74HC595/notes/facts.md](../datasheets/SN74HC595/notes/facts.md)).
The instrumentation memo's Q2 assumption ("output registers power up
low/high per datasheet") does not exist on this silicon; the reset
state is **constructed by discipline**, and *that discipline* is the
equivalence proof's reset-level input:

1. **`/OE` pulled up.** All eleven 595s' `/OE` nets share one 47 kΩ
   pull-up to `3V3`. At power-on — and for as long as the RP2040 is
   held in reset, unprogrammed, or hung before init — every 595 output
   is high-impedance (SCLS041J Table 8-1).
1. **Every control line carries a 47 kΩ pull-down to GND.** With the
   outputs Hi-Z, the pull-downs define the board: bit-0 = low = the
   plain-board state on all 79 used lines. The FET-gate pull-downs
   already
   on the transform list (instrumented-ci.md §3/§6: `PWR`, `BTN_*`)
   double as their lines' pull-downs; the 63 switch-select lines
   (49 tile injector/keep-alive selects on the seven injector tiles + 6
   supervisor port + 3 SWIO + 1 watchdog defeat + 4 pot muxes) gain
   one each — same 47 kΩ / 0603 bin. A floated LVC select is not just
   indeterminate, it burns shoot-through current and can double-clock
   logic ([facts.md](../datasheets/SN74LVC1G3157/notes/facts.md) —
   SCBA004), so the pull-downs are mandatory, not belt-and-braces.
1. **Boot sequence.** The RP2040 powers up with its GPIOs as inputs —
   `/OE` stays pulled high. Firmware shifts the all-zeros control word,
   pulses COMMIT (latching zeros into the storage registers), then
   drives `/OE` low. The outputs take over from the pull-downs at the
   same level: no transient fault state exists at any point in the
   sequence.
1. **`/SRCLR` tied high.** The zero word shifted in step 3 makes the
   shift-register clear redundant; it is not an RP2040 pin.

Properties this buys:

- **Unpowered-supervisor = plain board.** If the RP2040 never runs
  (bad flash, held in reset), the board sits in the plain-board state
  indefinitely — the safe default is the pull-downs', not firmware's.
- **Proof inputs are static data.** The proof consumes `reset_levels = all-zeros` over the 79-bit map of §3; the discipline above is the
  hardware argument that all-zeros is what the nets actually see.
  (This amends the memo's Q2 mechanism — see
  [docs/instrumentation-equivalence.md](instrumentation-equivalence.md)
  §4.)
- **Even the failure mode is safe.** Suppose `/OE` were released with
  garbage latched: every latched bit pattern is electrically safe
  (instrumented-ci.md §2's 470 Ω legs), so the worst case is a wrong
  fault for the microseconds before the zero load — never damage, never
  a hang.

The 165 observe stages need no POR discipline: observe-only, inputs
only, and a capture at any time defines the register.

The SWIO tree selects power up 000 = tile 0 selected — harmless:
the RP2040's SWIO pin is an input at reset, deselected nodes idle on
their pull-ups (§5), and tile 0 is the designated debug DUT anyway
(instrumented-ci.md §5).

## 5. The SWIO flash mux: a 3157 binary tree

instrumented-ci.md §8's delegated pick. **A binary tree of 7 ×
SN74LVC1G3157, three levels ganged to three select bits** (`SWIO_A2` /
`A1` / `A0`, one per tree level, bit weight = node address), root
toward the RP2040's PIO SWIO channel, leaves to the eight nodes:

```
              A2            A1              A0
SWIO(RP2040) ─┬─ SW ──────┬─ SW ──────────┬─ SW ── node 0
 4k7 pull-up  │           │               └─ SW ── node 1
              │           └─ SW ──────────┬─ SW ── node 2
              │                           └─ SW ── node 3
              └─ SW ──────┬─ SW ──────────┬─ SW ── node 4
                          │               └─ SW ── node 5
                          └─ SW ──────────┬─ SW ── node 6
                                          └─ SW ── node 7
```

- **Single stocked BOM line.** The 3157 is already the board's
  workhorse switch (instrumented-ci.md §2: 60 positions); the tree adds
  7 to the same line instead of a new 4051-class line.
- **Stacked Ron is fine here.** Three switches in series ≈ 21 Ω typ
  (≤ 75 Ω over the full range) on a line whose pull-ups are 10 kΩ —
  unlike the segment injectors, SWIO is a digital debug line that never
  leaves the board, so the §2 swept-baseline argument doesn't apply.
- **Rejected: 4051-class 8:1 mux.** One part and 3 selects, but Ron at
  3.3 V supply is 50–200 Ω against the tree's ~21 Ω, and it is a new
  BOM line. Also rejected: per-switch control (7 bits) — an 11th 595
  for a multi-select capability nothing uses.
- **Pull-ups per §6, placed against the tree:** per-node 10 kΩ on each
  leaf port's target side — to the node's **`3V3N`** domain, not the
  always rail, so a power-cut node has no back-feed path through its
  SWIO pull-up (a selected-then-cut leaf would otherwise leak
  ≈ 0.33 mA into the dead rail; bounded, but free to avoid). The 4.7 kΩ
  common-port pull-up sits at the tree root. The tree adds
  ≈ 3 × 17.3 pF on-path capacitance to the common net — inside the
  §6 rise-time budget the common pull-up already owns, and covered by
  the §6 flash-fan-out bench checks (deselected-port noise margin, SDI
  false-trigger recovery), unchanged.
- **Flash pairing.** `PWR` doubles as the flash-power control
  (instrumented-ci.md §3): the harness powers a node and selects its
  leaf under the same transaction discipline; live SWIO debugging parks
  the tree on tile 0 for the GDB session (§6).
- **Debug return tree (DESIGN.md §6).** A second 8:1 tree of the same
  stocked 3157 line gangs to `SWIO_A2`/`A1`/`A0` — the debug
  collection point is always the flash-selected node, which is exactly
  the "watch this tile" discipline, and the sharing costs zero chain
  bits. Leaves land on each tile's PD5 (the node pin map's
  `debug_tx`); the root is a dedicated RP2040 GPIO outside this plane
  (the supervisor pin map's `dbg_rx`, a PIO UART RX). No pull-ups on
  this tree: leaves are actively driven push-pull, and a power-cut
  node's leaf is isolated unless selected — a selected dead node
  reads as garbage, which the emit-and-forget contract already
  tolerates.

## 6. RP2040 interface

Five pins (feeds the supervisor pin budget):

| Pin      | RP2040 role            | Notes                                             |
| -------- | ---------------------- | ------------------------------------------------- |
| `SRCLK`  | SPI SCK or PIO         | shared shift clock, all 12 stages                 |
| `SDO`    | SPI MOSI or PIO        | chain data in (SER of AUX0)                       |
| `SDI`    | SPI MISO or PIO        | chain data out (QH of OBS1)                       |
| `COMMIT` | GPIO                   | RCLK on 595s, SH//LD on 165s; idle high           |
| `/OE`    | GPIO, open-drain drive | 47 kΩ pull-up; drive low only after the zero load |

An SPI peripheral covers the shift; COMMIT and `/OE` are plain GPIO.
The whole plane is also trivially PIO-able — the firmware picks. Clock
and COMMIT fan out to 12 stages each: fanout and stub length are a
layout footnote at these speeds (§7 layout-checker territory), not a
design constraint.

Outside this plane, three more supervisor pins serve the measurement
tile (instrumented-ci.md §12): `adc_sdata`/`adc_cs`/`adc_sclk` on
GPIO0/1/2 — all SPI0-capable pads — reached through taps P1–P3. Burst
capture spends no chain bits.

## 7. Electrical notes

- **Logic class: 74HC at 3.3 V.** VIH ≈ 0.7×VCC ≈ 2.31 V, VIL ≈
  0.3×VCC ≈ 0.99 V (interpolated from the 2/4.5/6 V table points,
  SCLS041J/SCLS116H §6.3) — RP2040 and HC outputs drive HC inputs with
  margin, and the `sel` observe high of 2.9–3.3 V clears VIH
  (instrumented-ci.md §8). 74HCT is unnecessary (nothing here is
  5 V-driven); 74LVC595/165 would work but split the BOM across rarer
  listings for no gain.
- **Clock/latch lines are push-pull always** — the HC Δt/Δv limit
  (≤ 500 ns/V at 4.5 V; slow-input double-clocking footnote) forbids
  RC-graded edges on SRCLK/COMMIT. The only RC in the design is on
  `/OE`, which is a level, not a clock.
- **Decoupling:** one 100 nF per stage from the board's C0603 bin;
  quiescent draw of the full plane ≈ 1 mA worst case (13 × 80 µA) —
  noise in the §2.1 rail budget.
- **Part picks (inventory-driven, §6):** SOIC-16, HC. Queried
  2026-10-15 against JLCPCB's live parts search:
  **74HC595 = Nexperia 74HC595D,118 (C5947) — Basic tier, $0.1132 @1,
  ~285k in stock** (the sole Basic 595 listing in any package);
  **74HC165 = Nexperia 74HC165D,653 (C5613) — Extended (JLCPCB
  "preferred" flag), $0.1103 @1, ~250k in stock** — no Basic-tier
  74HC165 exists in any package, so the board pays one Extended-line
  fee (~$3.07, §6) for its two observe stages. Parts-DB bindings land
  at the CI board capture.

## 8. Bench-verify additions

On top of instrumented-ci.md §10's list:

- **POR discipline:** power the board with the RP2040 held in reset —
  every control line sits at pull-down zero (plain board), no injector
  engages, all tiles powered. Then release and confirm the zero-load →
  `/OE`-low sequence never transits a fault state (boundary-node taps
  watch `opa_p`/`TX_A#b` through boot).
- **Observe round-trip:** commit a known fault pattern, read back the
  expected `sel`/`3V3N` word two transactions later (the §1 one-transaction
  lag), per tile.
- **SWIO tree:** the §6 flash-fan-out checks (deselected-port noise
  margin, SDI false-trigger recovery) run against the tree; stacked-Ron
  and on-path-capacitance effects show up there if anywhere.

## 9. Rejected alternatives

- **Two chains (control + observe separate):** +1 RP2040 pin and a
  second shift routine for no capability — the combined chain already
  reads observe bits on every control transaction.
- **Functional grouping of control bits** (all power bits on one stage,
  all injector bits on others): breaks the one-declaration-per-tile
  capture pattern, turns layout into a cross-board routing fan, and
  mixes unrelated actuators under shared stage failure.
- **Per-tile observe stages (8 × 165):** 8 packages for 2 bits each;
  the `sel`/`3V3N` sense wires run supervisor-ward either way.
- **A second aux stage per special tile** (0/2/5): breaks tile-slice
  uniformity; the extras are seven slow static lines.
- **Storage-clear shift registers (74HC594-class /RCLR):** true
  deterministic POR without the /OE discipline, but Extended-tier only
  at ~10× lower stock than the 595 (queried 2026-10-15), and the
  pull-downs are still required for the Hi-Z window — the discipline
  buys the invariant with the cheapest logic on the market.
- **Separate latch and capture pins** (capture-after-commit in one
  transaction): one more RP2040 pin to remove a ~100 µs
  one-transaction observe lag nothing cares about.
- **I2C/SPI port expanders:** addressing, pull-ups, bus contention,
  and per-transaction latency against one-bit-per-actuator determinism
  — §6's shift-register call, confirmed.
