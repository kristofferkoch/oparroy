# Instrumented CI design — fault injection, overrides, taps (2026-10-05)

Settles the instrumented half of the CI board that DESIGN.md §6 left as
prose: the fault-injection complement with part selection, the
supervisor-override design for human I/O, and the boundary node's tap
set — expressed as the **transform list** against the settled node board
design (`design/node.py`, `boards/node/`), the artifact the
instrumentation-transform machinery
(`docs/instrumentation-equivalence-2026-09-29.md` on the
retained branch `t24-dsl-instrumentation`) encodes and the CI board
capture consumes.

Net and part names below are capture names (the source of truth; the
board netlist carries them verbatim after flattening). `net#a`/`net#b`
split naming follows the equivalence memo. The node capture reference
for every cited net: `design/phy_frontend.py`, `design/node.py`,
`design/node_pins.py`.

## 1. Fault space → injector coverage

Every §3 failure mode, and how the CI board reproduces it:

| §3 failure mode                 | Scriptable injector                                                                                                           | Also covered by                                                                   |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Permanent open at a connector   | per-wire break switch (OPEN)                                                                                                  | connector yank (the demo; the connector stays the fragile element under test, §6) |
| Intermittent open               | scripted toggling of the same break switch — the §9 direction-flap policy gets its development harness                        | yank/reseat                                                                       |
| Short to GND / VCC on a segment | per-wire shunt legs to GND and to 3V3                                                                                         | —                                                                                 |
| Dead MCU                        | per-node power cut (this doc §3)                                                                                              | —                                                                                 |
| Hung MCU                        | keep-alive cut (this doc §4) — watchdog engages, node stays alive and observable                                              | —                                                                                 |
| Babbling idiot (garbage TX)     | crafted-waveform stimulus on the boundary node's PIO taps (this doc §5); deliberately-broken images via the §6 SWIO flash mux | §2 containment is what gets tested                                                |

**"Clock kill" resolves** (2026-10-05): the literal fault does not
exist on this node. The node runs HSI-only — no crystal, no clock net
anywhere (§5) — and PD7 ships as GPIO with NRST option-byte-disabled
([quirks.md](../datasheets/CH32V003/notes/quirks.md) §GPIO), so there is
no external clock to kill and no reset pin to hold. The intent — node
stops advancing — is covered by the three real mechanisms: power cut
(dead), keep-alive cut (hung → watchdog bypass), and SWIO halt on the
designated debug DUT (§6, single-step included).

## 2. The segment injector

One injector per **wire**, placed once per segment: every tile injects
on its downstream connector J2 — `TX_A` (J2.5) and `RX_B` (J2.7) — and
the supervisor carries the same injector on its originator port (the
supervisor→tile-0 segment), so each of the ring's nine segments is
instrumented at exactly one end (tile *i*'s J2 faces tile *i+1*'s J1;
tile 7's J2 faces the supervisor's drain). Per-wire circuit, three
SN74LVC1G3157 SPDT switches + two 470 Ω:

```
              SW_break (3157)      SW_shg (3157)        SW_shv (3157)
tile side   A  COM                 COM                  COM
(Rat/Rbr) ──── B1   cable side ●── B2 ──[470 Ω]── GND ── B2 ──[470 Ω]── 3V3
              B2  (J2 pin + TVS)   B1 = NC               B1 = NC
               NC
```

States (control bits; **0 = plain-board state on every bit**, §8):

| BRK | SHG | SHV | wire state                                                                                                          |
| --- | --- | --- | ------------------------------------------------------------------------------------------------------------------- |
| 0   | 0   | 0   | pass-through (reset state — the plain board)                                                                        |
| 1   | 0   | 0   | open — cable floats; the far receiver's internal pull-down parks it idle-low (the §2 tb_fault case, now scriptable) |
| x   | 1   | 0   | short to GND through 470 Ω                                                                                          |
| x   | 0   | 1   | short to 3V3 through 470 Ω — static-high, the "idle-high distinguishable from dead-quiet" case (§2 tb_fault)        |
| x   | 1   | 1   | cross-short GND↔3V3 through 2×470 Ω ≈ 3.5 mA — a weird fault, never damage                                          |

The 470 Ω shunt legs (the §7 bin) do three jobs: realistic whisker
impedance, current limiting that makes **every latched bit pattern
electrically safe** (no interlocks, no illegal states — worst case is
7 mA per leg, ~18× inside the switch's ±128 mA abs max,
[facts.md](../datasheets/SN74LVC1G3157/notes/facts.md) §5.1), and they
keep a driven-into-short driver inside its ±8 mA spec.

Open semantics: with the break open, the cable-side stub floats and the
tile-side stub (Rar/Rbr end) parks via the OPP input's internal
pull-down — exactly the severed-segment behavior §2 measured. A short
cannot reproduce this signature: it is the one test that validates the
pull-down park against a real floating cable with crosstalk from
adjacent conductors.

Part selection: **SN74LVC1G3157 everywhere** — already a stocked BOM
line in two vendors (parts DB: TI C10426, UMW C3040658), datasheet
extracted, spice model in `circuits/lib/`, and its 7 Ω is already
inside the §2 measured baseline (tb_decode swept the inserted-switch
path). 48 switches for the tile-side segment wires (8 tiles × 2 wires ×
3\) plus the supervisor port's 6; the same switch also serves the
keep-alive cut (§4, 8), the boundary watchdog defeat (§5, 1), and the
pot substitution muxes (§6, 2) — 65 in all on one stocked BOM line.
Rejected alternatives in §11.

The injector sits **between the tile PHY and the connector**: the split
point on `TX_A` is `PHY1/Rat.b` ↔ {J2.5, `PHY1/Dat`}, on `RX_B` it is
`PHY1/Rbr.a` ↔ {J2.7, `PHY1/Dbr`} — on both wires `#a` names the tile
side and `#b` the connector/cable side. The connector TVS stays
connector-adjacent (§7 contract); the injector switches sit on the
cable side of the 470 Ω protection, so their own ESD exposure is
bounded by that TVS alone — accepted for test infrastructure and noted
for the §7 layout checker (TVS adjacency now also covers the injector).

## 3. Per-node power cut — and the tile rail split

The §4 constraint drives the topology: the bypass switch (and the
injectors, which must stay alive to inject faults into a dead tile) run
from the **always-on ring rail**, because the 1G3157 has no
partial-power-down spec. The transform therefore splits the tile's
`3V3` net in two domains behind a high-side switch:

- **`3V3` (always)** — `PHY1/SW1` VCC, `PHY1/BUF1` (DNP), all injector
  switch VCCs, the shunt-to-3V3 legs' source, the boundary node's
  watchdog-defeat leg source.
- **`3V3N` (node, switched)** — U1 VDD (pin 9) with `C1`/`C2`,
  `PHY1/Rth1` (the VDD/2 divider must die with the MCU or it back-feeds
  OPN0), all of `SL1` (the power LED then narrates the cut), TP2.

`WD1` needs no rail — it is passive, driven by `ka`, which is an MCU
pin: cut the MCU and the pump stops, `WD1/Rb` parks `sel` low, bypass
engages. The cut *is* the dead-MCU fault, correctly bypassed.

The switch: **AO3401A-class P-channel MOSFET** (LCSC C15127, JLCPCB
Basic, SOT-23, 30 V / 4 A, R DS(on) ≤ 85 mΩ at V GS = −2.5 V — queried
2026-10-05, binding lands in the parts DB at capture). Source = `3V3`,
drain = `3V3N`, gate = scan-chain bit with a **47 kΩ pull-down** (POR =
on = plain board; the scan-plane /OE discipline in §8 covers the
startup window). Bit `PWR`: 0 = powered, 1 = cut. Doubles as the §6
brick-recovery power cycle and the flash-power control for the SWIO
mux.

**Back-feed, bounded and benched.** A cut node on a live ring sees its
`opa_p`/`opa_p_b` pins driven through `Rar`/`Rbr` (470 Ω) and phantom-
powers through its ESD clamps: ≤ (3.3 − 0.6) / 470 ≈ 5.7 mA per pin,
~11 mA total — inside the Σ ±20 mA injection budget (CH32V003 facts
T3-1; the per-pin ±4 mA DC spec is exceeded on each high line pulse
while `3V3N` sits low, decaying as the clamps charge `3V3N`'s 10 µF
toward equilibrium). The §7
terminal-protection sizing anticipated exactly this ("caps phantom-
power injection into a powered-down node"). Equilibrium: the rail
cannot source MCU startup current through 470 Ω, so `3V3N` floats below
the operating threshold and the node stays inert. The unpowered clamp
loads the ring-A bypass route at `opa_p` — high-level clipping toward
VDD + 0.6 against a 1.65 V downstream threshold: decode margin shrinks
but holds, and this is also the production case of a locally-dead node
(§3), so the bench measures it directly (§10).

## 4. Keep-alive cut (hang simulation)

`insert_series` on `ka`, split point U1.20 ↔ `WD1/Rs.a`, one 3157
(B1 = through = bit 0, B2 = NC), plus a **47 kΩ pull-down on the
watchdog-side stub** so the pump input parks low deterministically
instead of floating to a leakage-decided state. Effect: `sel` decays on
the §4 Cs·Rb constant, bypass engages ~0.5 ms after the cut (§4
measured) **with the MCU alive** — the hung-MCU fault class, and a
per-node scriptable check of §4 engage timing. The 47 kΩ bleeds ≤ 70 µA while a strobe is high (≈ 5 % of the per-edge
pumped charge) — a
budgeted residual (§9), sim/bench-confirmed against the 2.31 V VIH
floor.

## 5. Boundary node — taps and watchdog defeat

Tile 0, supervisor-adjacent, is the §6 instrumented boundary node and
designated debug DUT. Four `add_tap`s to RP2040 GPIO (PIO logic
analyzer / stimulus), attached **after** the injector transforms so the
taps see post-injection truth:

- `opa_p` — what the node's comparator sees (post-`Rar`)
- `TX_A#b` — the wire as it leaves toward the next tile (re-emission in
  node-active state, pass-through in bypass, injected faults as latched)
- `opo` — the comparator's digital output, against `opa_p`'s analog
- `led_work` — the heartbeat, truthful when the MCU misbehaves

**No series resistors on taps.** Stimulus drives `opa_p` against the
upstream idle-low driver through the segment's existing 470 Ω — 7 mA,
inside the ±8 mA drive spec and the §7 sizing. Any tap series R forms a
divider with that 470 Ω (1 kΩ → 1.06 V high level, below the VDD/2
slice) and kills stimulus injection. The observe-only taps (`opo`,
`led_work`) need none either: tiles and RP2040 share one regulator (§6
board power), so there is no cross-domain hazard. POR: RP2040 GPIOs
power up as inputs — taps are high-impedance in reset state, which is
what the equivalence proof requires; stimulus mode is a deliberate
non-reset state.

**Watchdog defeat** (DESIGN.md §6): `add_shunt(sel → 3V3 always)` through one
3157 (B1 = NC = bit 0 = watchdog in charge, B2 = rail). While set, `sel`
is clamped high through ~7 Ω and a halted/single-stepped node stays
electrically in the ring; the charge pump's edge dumps into the rail
are normal-operation amplitudes and `WD1/Rb` bleeds 70 µA. The
scan-chain `sel`-observe (§8) reads high, consistent.

## 6. Human-I/O overrides (demonstrator tiles)

DESIGN.md §6 dual role: two **input tiles** (2 and 5) carry a potentiometer and
two buttons; two **output tiles** (3 and 6) carry a buzzer; tiles 1, 4,
7 stay plain. Payloads bind the pin map's reserved functions (`pot` =
PD6/ADC_IN6, `button_a` = PC5, `button_b` = PC6, `buzzer` =
PC4/TIM1_CH4) — payload parts are CI-board additions on those tiles,
not changes to the node design. Every input is supervisor-overridable
so scripted runs stay hands-off regardless of knob positions:

- **Potentiometer** — 10 kΩ linear across `3V3N`/GND, wiper →
  `substitute` mux (3157): B1 = wiper (bit 0 = human control), B2 =
  supervisor filtered PWM (RP2040 PWM → 10 kΩ + 100 nF, f c ≈ 160 Hz);
  COM → 1 kΩ series → PD6. The pot path's source impedance tops out at
  ≈ 3.5 kΩ (10 kΩ pot's 2.5 kΩ Thévenin midpoint + mux R on + 1 kΩ),
  inside the §7 ADC ≤ 10 kΩ budget; the PWM path's resistive chain
  (10 kΩ + 1 kΩ) nominally exceeds it, and the 100 nF filter cap
  doubles as the ADC's charge reservoir. (RP2040 has no DAC; one
  PWM channel per input tile, demand noted for the supervisor
  subcircuit's pin budget.)
- **Buttons** — tactile switch to GND, 10 kΩ pull-up to `3V3N`, 1 kΩ
  series to the pin (§7); **2N7002-class N-FET** (LCSC C8545, JLCPCB
  Basic, SOT-23 — queried 2026-10-05) paralleled across the button,
  gate = scan bit with 47 kΩ pull-down (POR = released). Pressing the
  physical button during an override is harmless contention-free
  paralleling — both just pull low.
- **Buzzer** — passive piezo, PC4 → 470 Ω (§7 user-facing series R) →
  piezo → GND. Outputs are observed, not substituted: commanded state
  echoes in the node's telemetry slot.

Optocoupler button isolation (DESIGN.md §6's "optocoupler/transistor"
option) is rejected: the board is common-ground, so isolation buys
nothing, and an opto is a new Extended BOM line against a Basic 2N7002.

## 7. The transform list

The artifact. Transform kinds: `insert_series`, `add_tap`,
`substitute` (per the equivalence memo) plus one new kind —
**`add_shunt(net, chain, rail)`**: hang a switched branch between a net
and a rail/reference *without cutting the net* (the short legs, the
watchdog defeat). The memo's three kinds cannot express a branch that
is open in reset state; `add_shunt`'s reset-state reduction is "branch
absent", its residuals are off-capacitance and leakage.

**Per tile** (sheetpath-keyed, one declaration instruments all eight —
instance `FI1`, parts prefixed at flatten time):

| #   | Kind          | Target (capture names)                             | Parts                           | Bit (0 = plain)          |
| --- | ------------- | -------------------------------------------------- | ------------------------------- | ------------------------ |
| F1  | insert_series | `TX_A`: `PHY1/Rat.b` ↔ {J2.5, `PHY1/Dat`}          | FI1/SWAB 3157                   | `BRK_A` (0 = pass)       |
| F2  | add_shunt     | `TX_A#b` → GND                                     | FI1/SWAG 3157 + 470 Ω           | `SHG_A`                  |
| F3  | add_shunt     | `TX_A#b` → `3V3`                                   | FI1/SWAV 3157 + 470 Ω           | `SHV_A`                  |
| F4  | insert_series | `RX_B`: `PHY1/Rbr.a` ↔ {J2.7, `PHY1/Dbr`}          | FI1/SWBB 3157                   | `BRK_B` (0 = pass)       |
| F5  | add_shunt     | `RX_B#b` → GND                                     | FI1/SWBG 3157 + 470 Ω           | `SHG_B`                  |
| F6  | add_shunt     | `RX_B#b` → `3V3`                                   | FI1/SWBV 3157 + 470 Ω           | `SHV_B`                  |
| F7  | insert_series | `ka`: U1.20 ↔ `WD1/Rs.a`, +47 kΩ PD on the WD side | FI1/SWKA 3157 + 47 kΩ           | `KA_CUT` (0 = connected) |
| F8  | insert_series | `3V3` → `3V3N` (domains per §3)                    | FI1/QPW AO3401A + 47 kΩ gate PD | `PWR` (0 = powered)      |

**Boundary tile 0, additional** (per-instance, on top of the per-tile
set):

| #   | Kind      | Target                   | Parts         | Bit / pin                            |
| --- | --------- | ------------------------ | ------------- | ------------------------------------ |
| B1  | add_tap   | `opa_p` → RP2040 GPIO    | wire          | PIO                                  |
| B2  | add_tap   | `TX_A#b` → RP2040 GPIO   | wire          | PIO                                  |
| B3  | add_tap   | `opo` → RP2040 GPIO      | wire          | PIO                                  |
| B4  | add_tap   | `led_work` → RP2040 GPIO | wire          | PIO                                  |
| B5  | add_shunt | `sel` → `3V3`            | FI1/SWWD 3157 | `WD_DEFEAT` (0 = watchdog in charge) |

**Input tiles 2 and 5, additional:**

| #   | Kind       | Target                                    | Parts                                                  | Bit (0 = human) |
| --- | ---------- | ----------------------------------------- | ------------------------------------------------------ | --------------- |
| H1  | substitute | PD6 source: pot wiper ↔ supervisor PWM+RC | FI1/SWPOT 3157 + pot 10 kΩ + 10 kΩ/100 nF + 1 kΩ       | `POT_SEL`       |
| H2  | substitute | PC5: button ∥ N-FET                       | FI1/QBA 2N7002 + 47 kΩ gate PD (+ button, 10 kΩ, 1 kΩ) | `BTN_A`         |
| H3  | substitute | PC6: button ∥ N-FET                       | FI1/QBB 2N7002 + 47 kΩ gate PD                         | `BTN_B`         |

**Output tiles 3 and 6:** buzzer payload only (PC4 → 470 Ω → piezo →
GND) — an addition, no transform, no control bits.

**Supervisor originator port** (the supervisor→tile-0 segment): the
F1–F6 set on its two ring wires — 6 switches, 6 bits. The drain port
needs none: tile 7's J2 injector covers that segment.

## 8. Control/observe demands on the scan plane

Bit inventory the shift-register control plane must provide:

- **Control: 77 bits** — 8 per tile × 8 (F1–F8) = 64, boundary
  `WD_DEFEAT` = 1, input tiles 3 × 2 = 6, supervisor port = 6. Fits 10 ×
  74HC595 (80 bits, 3 spare). The SWIO flash mux select comes on top
  (3 bits encoded via a 4051-class mux, or 7 for a 3157 tree — the tree
  keeps the single stocked BOM line and SWIO tolerates the stacked
  R on ; the scan-plane design picks).
- **POR invariant: bit 0 = plain-board state on every control bit.**
  The reset-state load is therefore all-zeros. FET gates carry 47 kΩ
  pull-downs (POR = pass/released); the 595 stages hold /OE until the
  reset-state load has been shifted, so no transient output state can
  inject a fault at power-up. These levels are the equivalence proof's
  inputs.
- **All patterns safe** (this doc §2): the 470 Ω shunt legs bound
  every bit combination, so the chain needs no hardware interlocks — a
  wrong pattern injects a wrong fault, never damage.
- **Observe requests: 16 bits** — per-tile `sel` (bypass state; the
  truthful node-health bit: engages on power cut, keep-alive cut, or
  real watchdog action; 2.9–3.3 V high vs 2.31 V VIH, mid-band reads
  during the ~0.5 ms ramps are transient-only) and per-tile `3V3N`
  (coarse power bit, documented caveat: a back-fed cut rail can float
  above VIH and read "on" — `sel` is the authority). Fits 2 × 74HC165.

## 9. Residual register (equivalence-proof input)

Every way the reset-state CI board differs from the plain node,
enumerated and budgeted — "almost equivalent" is exactly this set:

| #   | Residual                                                                                                | Magnitude                        | Budget citation                                                                                                                                                                                                     |
| --- | ------------------------------------------------------------------------------------------------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R1  | series Ron on every segment wire (break switch, pass state; ring-A paths already carried the §4 switch) | +7 Ω typ, ≤ 25 Ω max             | §2 tb_decode swept the inserted-switch path; the 470 Ω series R dominates and margins are flat at this scale                                                                                                        |
| R2  | switch capacitance on each segment wire: one on-port (17.3 pF) + two off-ports (2 × 5.2 pF)             | ≈ 28 pF                          | §2 tb_decode: margins flat (±4 ns) across 47 pF–1 nF segment capacitance; 28 pF sits below the swept floor                                                                                                          |
| R3  | `ka` series Ron before `WD1/Rs`                                                                         | +7 Ω on 220 Ω (+3 %)             | §4 glitch-filter timing is non-critical (100 ns rejection has orders of margin)                                                                                                                                     |
| R4  | 47 kΩ pull-down on `ka#b` bleeds pump charge during strobes                                             | ≤ 70 µA ≈ 5 % of per-edge charge | §4 charge-pump margin vs the 2.31 V VIH floor; sim/bench-confirmed (§10)                                                                                                                                            |
| R5  | P-FET Ron on `3V3N`                                                                                     | ≤ 85 mΩ → ≤ 3 mV at 30 mA        | §2.1 rail headroom (MCU floor 2.7 V, tens-of-mV loop drops already budgeted)                                                                                                                                        |
| R6  | boundary taps: GPIO + stub capacitance on `opa_p` / `TX_A#b` / `opo` / `led_work`                       | ≈ 5–10 pF each                   | `Rar` × 10 pF = 4.7 ns pole vs §2's ≥ 144 ns worst-slice margin; `TX_A#b` inside the swept segment-C range. Stub length is a geometry residual → §7 layout-checker obligation (short-stub contract, ≤ 20 mm target) |
| R7  | pot-mux Ron in the ADC source path                                                                      | +7 Ω on ≥ 3.5 kΩ                 | §7 ADC source ≤ 10 kΩ budget                                                                                                                                                                                        |
| R8  | button FET off-capacitance + on-resistance                                                              | ~5 pF, R DS(on) ≪ 10 kΩ pull-up  | slow GPIO; millivolt levels                                                                                                                                                                                         |
| R9  | defeat-shunt off-capacitance on `sel`                                                                   | +5.2 pF on Cs = 10 nF            | §4 timing constants unchanged at 0.05 %                                                                                                                                                                             |

The phantom-power clamp loading on the bypass route (§3) is not a
reset-state residual — it exists only in the injected power-cut state —
but it is the one injected-state behavior with production relevance, so
it gets a dedicated bench item.

## 10. Bench-verify list (feeds the test-bench harness)

- Decode margins through the injector pass path (R1+R2), measured on
  the boundary taps — direct comparison of `opa_p` vs `TX_A#b`.
- Open fault on a real floating cable: far receiver parks idle-low, no
  chatter (tb_fault's claim on real silicon, adjacent-conductor
  crosstalk included).
- Short-to-3V3 reads as static-high, distinguishable from dead-quiet.
- Power cut: node inert (no brownout cycling), `sel` engages, bypass
  signal fidelity through the clamping `opa_p` (§3), no latch-up on
  re-power; rail dip on `3V3` at P-FET turn-on into 10 µF (if
  disruptive, slow the gate with a series R + cap — the footprint
  decision lands at capture).
- Keep-alive cut: bypass engage ~0.5 ms, per node, via `sel`-observe.
- Watchdog defeat: SWIO-halted node stays in the ring; single-stepped
  execution observed on the taps.
- Pot override: supervisor PWM drives PD6, node telemetry follows;
  knob-back-at-POR behavior (bit 0 = human control).
- Button FET: scripted press detected in telemetry; physical press
  during override harmless.
- DESIGN.md §6's flash-fan-out checks (deselected-port noise margin,
  SDI false-trigger recovery) unchanged — they land before the control
  plane is committed, as already decided.

## 11. Rejected alternatives

- **Relays for the fault switches** (§6's "analog muxes or relays"):
  50+ relays' area, coil current, and cost against a $0.047 switch
  already on the BOM; NC-pass POR is their only advantage and the
  3157's bit-0-pass invariant matches it for free.
- **4066-class quad bilateral switches**: one SOIC-14 per wire is fewer
  packages, but R on at 3.3 V supply is 50–200 Ω — an order above the
  3157 and *outside* the §2 swept switch-path baseline; adopting them
  re-opens the PHY characterization instead of reusing it.
- **Shunt-only injection (no true open)**: drops the floating-cable
  chatter validation — the one receiver signature a short cannot
  reproduce (§2).
- **4051-class N:1 muxes for injection**: wrong shape — the injector
  needs independent 4-state control per wire, not selection.
- **Optocoupler button override**: DESIGN.md §6 (isolation buys
  nothing on a common-ground board).
- **Integrated load switch for the power cut** (TPS229xx-class):
  smaller and slew-controlled, but a new Extended BOM line against a
  Basic P-FET + pull-down; inrush tuning noted as the footprint-level
  fallback (§10).
- **Series resistors on the boundary taps**: §5 (divider kills stimulus
  drive).
- **Injection at both ends of each segment**: doubles switch count for
  no new fault coverage — a fault's position along the segment is not
  observable at the receivers.
- **Scripted power-conductor opens** (3V3/GND/UNREG in the segment
  cable): connector physics, exercised by the yank demo and the
  fragile-connector doctrine; the per-node power cut covers the logical
  power-fault space. Switching five more conductors per segment is
  cost without new information.
