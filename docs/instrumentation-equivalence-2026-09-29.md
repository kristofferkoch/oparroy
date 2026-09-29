# Instrumentation transforms & reset-state equivalence — design memo (2026-09-29, card T24)

The CI board is the node design plus injected controllability and
observability (DESIGN.md §6: fault-injection muxes, supervisor-override
muxes, sense taps, the instrumented boundary node's PIO taps). That
makes it *dangerously different* from the plain node it is meant to
exercise (raised 2026-09-27). Hand-maintaining two captures guarantees
drift; this memo designs the alternative: instrumentation as an
**explicit transformation** of the uninstrumented capture, plus a
checker pass that proves the instrumented board **in reset state** is
equivalent to the plain board up to an enumerated, budgeted set of
residuals. "Almost equivalent" is exactly that set.

## 1. Transform representation

Instrumentation is a list of **transforms applied to the flattened IR**
(`src/oparroy/dsl/ir.py`), after flattening, before check/emit:

- `insert_series(net, part, pins)` — cut `net` into `net#a`/`net#b`,
  bridge them through `part` (a 74LVC1G3157-class analog switch, a
  power switch, an optocoupler). The part's control pins are fresh
  nets the transform returns handles to, so the CI capture wires them
  to the §6 shift-register control plane.
- `add_tap(net, part, pin)` — hang a high-impedance sense point off
  `net` without cutting it (PIO logic-analyzer taps, comparator-output
  and working-LED taps, §6 instrumented boundary node).
- `override(node_part, pins, part)` — supervisor substitution of a
  human input (pot wiper through an analog mux, button paralleled by
  a transistor, §6 dual-role constraint).

Transforms are data (typed records), not code patches over the
capture: the CI board's capture is `plain_node_capture()` + a
declared transform list. Two consequences:

- **Provenance is free.** Every part/net the transform creates is
  tagged with the base net/part it derives from. The equivalence
  checker consumes exactly these tags — no name-matching heuristics.
- **The plain capture never carries CI-only parts.** The base board
  stays buildable and fab-able (the T22 node board) while the CI
  board is a strict superset produced mechanically.

Open shape question: transforms over the **flattened** IR (simple,
one net namespace) vs over the **hierarchical** IR (transforms
expressed against subcircuit ports, replicated per instance — the CI
board is eight node tiles, and per-tile transforms want the
sheetpath-keyed metadata T7ba landed). Memo leans hierarchical for the
tile case, flattened for the proof. See §4 Q1.

## 2. The equivalence proof

A checker pass `check_equivalent(base_circuit, instrumented_circuit)`
consumes the transform provenance and proves:

1. **Series elements reduce to wires in reset state.** Every inserted
   series part has a declared default/pass-through state (switch
   control pin at its reset level ⇒ channel closed). The pass
   simulates the reset-state netlist reduction: each such part is
   replaced by a net merge of its `#a`/`#b` sides. Reset state is
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
  the residual budget citations point at the §2 numbers the T15
  benches measured.
- **Not a proof of the instrumented states.** The proof covers reset
  state only. The interesting CI states (fault injected, override
  active) are *supposed* to differ from the base; their correctness
  is the T10/T12 harness's job.
- **Not layout equivalence.** Copper-level checks (stub length, tap
  placement) remain §7 layout-checker contracts; this proof runs on
  the netlist IR.

## 4. Open questions

- **Q1 — Transform level.** Hierarchical (per-tile, sheetpath-keyed,
  one declaration instruments all eight nodes) vs flattened (one
  long explicit list, no metadata dependency). Hierarchical wins if
  the CI board really is eight identical tiles; flattened wins if the
  tiles diverge (the instrumented boundary node already does, §6).
- **Q2 — Reset-state source of truth.** Where do control-line reset
  levels live? Options: on the transform record (`insert_series(..., reset=LOW)`), on the part class (a `default_channel:` attribute in
  the parts DB), or derived from the shift-register stage's power-on
  state. The third is the most truthful (proof input = the actual
  silicon behavior) but couples the DSL checker to the 74HC595
  datasheet fact.
- **Q3 — Residual magnitude source.** On-resistance, off-leakage,
  tap capacitance: parts-DB attributes per part (extends the T7c
  schema), or annotations on the transform? Parts DB is the single
  home for part facts — but a tap's capacitance is a *layout*
  property (stub length), which the netlist-level proof can only
  bound, not know. Likely split: electrical residuals from the parts
  DB, geometry residuals emitted as obligations for the §7 layout
  checker to discharge.
- **Q4 — Override transforms.** The §6 human-I/O overrides (pot mux,
  button parallel) are not series-inserts on an existing net — the
  pot wiper mux *replaces* a driver. Is that a third transform kind
  (`substitute`), or is the plain capture drawn with the mux socket
  already present and unpopulated (multipacking/sockets, T7bc) with
  the transform just flipping the stuffing option?
- **Q5 — Proof granularity.** One `check_equivalent` pass over the
  whole CI board vs per-tile proofs composed upward. Per-tile
  composes better with Q1-hierarchical and keeps failure messages
  local ("tile 3: base net `wd_cap` lost").
- **Q6 — Where the base capture comes from.** The CI board capture
  imports `design/node.py` (the T22 capture) and transforms it. Is
  the node board a subcircuit instance ×8 (needs the T7ba subcircuit
  composition to cover whole boards, connectors included) or is the
  CI capture a flat re-instantiation? The former is the design
  intent; the latter is a drift hole the transform approach exists
  to close.

## 5. Sketch of the slice

Vertical slice for the first landing (keeps the card one change):

1. Transform records + provenance tags in `ir.py` (or a new
   `transform.py`), applied between flatten and check.
1. `check_equivalent()` in `check.py` consuming the tags: reduction,
   bijection, residual enumeration. Budget citations as data on each
   residual; missing budget ⇒ error.
1. Test fixture: a minimal base circuit (watchdog-class, two nets)
   - one series insert + one tap; proof passes; a tampered variant
     (base part deleted) fails the bijection check.
1. The real consumer — `design/ci_board.py` transforming
   `design/node.py` ×8 — is T10's capture work, unblocked by this.
