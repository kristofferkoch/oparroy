# Instrumentation transforms & reset-state equivalence — design memo

The CI board is the node design plus injected controllability and
observability (DESIGN.md §6: fault-injection muxes, supervisor-override
muxes, sense taps, the instrumented boundary node's PIO taps). That
makes it *dangerously different* from the plain node it is meant to
exercise. Hand-maintaining two captures guarantees drift; this memo
designs the alternative: instrumentation as an
**explicit transformation** of the uninstrumented capture, plus a
checker pass that proves the instrumented board **in reset state** is
equivalent to the plain board up to an enumerated, budgeted set of
residuals. "Almost equivalent" is exactly that set.

**Status:** landed on main. The transform machinery shipped
(`src/oparroy/dsl/transform.py`: four transform kinds, per-tile
application, `Provenance` tags through flattening and renaming); the
`check_equivalent` proof shipped with it
(`src/oparroy/dsl/equivalence.py`). §4 records all six decisions.
(Pre-landing history: an earlier PR closed unmerged while the two
designs it relates — the standalone node board and the instrumented CI
design — were still unsettled.)

## 1. Transform representation

Instrumentation is a list of **transforms applied per-tile to the
hierarchical IR** (`src/oparroy/dsl/transform.py`), after
instantiation, before check/emit — each matched tile instance is
flattened in place and its nets rewritten; the proof runs on the
flattened result. The four transform kinds:

- `insert_series(net, pins, part)` — cut `net` into `net#a`/`net#b`,
  bridge them through `part` (a 74LVC1G3157-class analog switch, a
  power switch, an optocoupler). The part's control pins are fresh
  nets the transform returns handles to, so the CI capture wires them
  to the §6 shift-register control plane.
- `add_shunt(net, rail, part)` — branch between `net` and `rail`
  through `part`, no cut; the reset-state reduction is "branch
  absent".
- `add_tap(net)` — export `net` as a high-impedance sense port
  without cutting it (PIO logic-analyzer taps, comparator-output and
  working-LED taps, §6 instrumented boundary node).
- `substitute(net, pins, part, source)` — supervisor substitution of
  a human input (pot wiper through an analog mux, button paralleled by
  a transistor, §6 dual-role constraint): cut like `insert_series`,
  but the interface side is re-driven from an escaped `@source` port.

Transforms are data (typed records), not code patches over the
capture: the CI board's capture is `plain_node_capture()` + a
declared transform list. Two consequences:

- **Provenance is free.** Every part/net the transform creates is
  tagged `Provenance(transform, base)` with the transform label and
  the base net it derives from. The equivalence
  checker consumes exactly these tags — no name-matching heuristics.
- **The plain capture never carries CI-only parts.** The base board
  stays buildable and fab-able (the standalone node board) while the
  CI board is a strict superset produced mechanically.

Decided (§4 Q1): transforms are expressed against the
**hierarchical** IR — per-tile, sheetpath-keyed, one declaration
instruments all eight node tiles — and the proof runs on the
flattened result.

## 2. The equivalence proof

A checker pass
`check_equivalent(base, instrumented, plan, *, reset_levels, budgets)`
consumes the transform provenance (plus the plan's role declarations —
which escaped port is a control, which a tap) and proves:

1. **Series elements reduce to wires in reset state.** Every inserted
   series part has a declared default/pass-through state (switch
   control pin at its reset level ⇒ channel closed). The pass performs
   the reset-state netlist reduction by provenance: each such part's
   `#a`/`#b` sides merge back onto the base net; each shunt branch
   is absent. Reset state is
   read from the control plane's power-on state (74HC595 output
   registers power up low/high per datasheet — the shift-register
   reset levels are part of the proof's inputs, not assumed).
1. **Taps are high-impedance.** Every `add_tap` part's attached pin
   is an input-class pin (KiCad `PinType`, or a declared impedance
   limit on the part) — nothing a tap adds can drive the net.
1. **Bijection over the base.** Every base part and base net survives
   into the reduced instrumented circuit — nothing lost, nothing
   re-connected. This is the anti-drift property: the instrumented
   board cannot silently drop the watchdog's timing cap or rewire a
   segment.
1. **Residuals are enumerated, not assumed away.** The reduction is
   not exact: a closed 74LVC1G3157 is ~6 Ω, not 0 Ω; a tap is ~10 pF
   of stub capacitance, not open. The pass emits the residual set as
   data — `(net, residual_kind, magnitude)` — and each residual must
   carry a **budget citation**: the switch on-resistance against the
   §2 decode-margin budget, the tap capacitance and stub length
   against the §6 short-stub contract (a §7 layout-checker contract).
   A residual without a budget is an error; "almost equivalent" is
   exactly the enumerated set.

Output shape mirrors `check.py`'s `Issue` list — waivers-as-data
already exist for the exceptional case.

## 3. What the proof is not

- **Not a spice equivalence.** The proof is topological plus
  first-order DC (on-resistance, leakage, capacitance). Dynamic
  equivalence under the §2 cell timing stays a sim/bench concern —
  the residual budget citations point at the §2 numbers the benches
  measured.
- **Not a proof of the instrumented states.** The proof covers reset
  state only. The interesting CI states (fault injected, override
  active) are *supposed* to differ from the base; their correctness
  is the test-board harness's job.
- **Not layout equivalence.** Copper-level checks (stub length, tap
  placement) remain §7 layout-checker contracts; this proof runs on
  the netlist IR.

## 4. Decisions and open questions

Decided (four calls taken before the card was re-blocked):

- **Q1 — Transform level: hierarchical, per-tile.** One transform
  declaration keyed on sheetpath metadata instruments all eight node
  tiles; the proof runs on the flattened result. Tiles that
  diverge (the instrumented boundary node, §6) carry their own
  per-instance declarations on top.
- **Q2 — Reset-state source of truth: shift-register power-on
  state.** Control-line reset levels derive from the 74HC595-class
  stage's actual silicon power-on behavior, not from declarations on
  the transform or the switch part. The datasheet fact lives in the
  parts DB / datasheet notes; the checker consumes it as proof input.
- **Q4 — Overrides: a transform kind, `substitute`.** The §6
  human-I/O overrides (pot-wiper mux, button parallel) replace who
  drives a net; the plain capture stays exactly the node board — no
  CI-only scaffolding sockets in the base design.
- **Q6 — Base capture: subcircuit instance ×8.** The CI capture
  instantiates `design/node.py` as a subcircuit eight times —
  requires the DSL composition to cover whole boards, connectors
  included.

Settled on pickup:

- **Q3 — Residual magnitude source: split.** Electrical residuals
  (on-resistance, off-leakage, capacitance) are parts-DB attributes
  per part (optional fields on `PartRecord`, threaded through
  `PartsDb.bind` onto the typed parts) — the parts DB stays the
  single home for part facts. Geometry residuals (a tap's stub
  capacitance is a *layout* property) are emitted by the proof as
  obligations for the §7 layout checker to discharge — the
  netlist-level proof bounds them, it cannot know them.
- **Q5 — Proof granularity: per-tile, composed upward.** The proof
  runs per tile (grouping the flattened IR by instance path) and
  composes the `Issue` lists upward. Follows from the Q1 decision and
  keeps failure messages local ("T3: base net `wd_cap` lost").

## 5. The landed slice

1. Transform records + provenance tags in `transform.py`, applied
   per-tile between instantiation and check.
1. `check_equivalent()` in `equivalence.py` consuming the tags:
   reduction, bijection, residual enumeration. Budget citations as
   data on each residual; missing budget ⇒ error.
1. Test fixture: a minimal base circuit (watchdog-class, two nets)
   - one series insert + one tap; proof passes; a tampered variant
     (base part deleted) fails the bijection check.
1. The real consumer — the CI board capture transforming
   `design/node.py` ×8 — is the test-board capture work, unblocked
   by this.
