# DSL tutorial

A guided tour of the design-capture DSL (`src/oparroy/dsl/`, the
project's single source of truth for schematics). This doc teaches by
doing; [dsl-reference.md](dsl-reference.md) is the API map, and
[DESIGN.md §7](../DESIGN.md#7-design-capture-dsl) records *why* the DSL
is shaped this way. Read this one first.

The pipeline, in the order a design flows through it:

1. **Capture** — plain Python builds the IR: parts, nets, subcircuit
   instances.
1. **Transforms** (CI board only) — instrumentation applied as data
   over the hierarchical capture.
1. **Footprint assignment** — per-instance overrides over the class
   defaults.
1. **Check** — one validation pass, findings batched as `Issue`s.
1. **Annotation** — capture paths mapped to refdes, and back from
   pcbnew.
1. **Emit** — KiCad netlist, ngspice DUT netlist, dot graph, firmware
   pin header.

Every code block below is quoted verbatim from
[tests/test_dsl_tutorial.py](../tests/test_dsl_tutorial.py), which
pytest exercises — the tutorial cannot drift from the API. Run it:

```
uv run pytest tests/test_dsl_tutorial.py
```

## Setup

The nix dev shell provisions everything non-Python (KiCad libraries,
ngspice, uv itself); uv owns the Python side. Real captures resolve
symbols and footprints from the KiCad libraries via
`KiCadLibraries.from_env()`, which reads env vars the dev shell exports
— outside the shell it raises `LibraryError`. Tests don't need KiCad:
`tests/conftest.py` carries stub symbol and footprint tables
(`StubSymbols`, `StubFootprints`), and the worked example uses them, so
it runs anywhere pytest does.

## Your first circuit

The example: a two-channel RC low-pass filter board. One `RcFilter`
subcircuit, instantiated twice.

A circuit is parts and nets with explicit names — you pick every
reference designator and net name at capture time, because those names
are the stable identity everything downstream (checks, annotation,
tstamps) keys on. Parts come from *typed* classes: construction carries
the wiring, so a misspelled pin name fails at the call site, not in a
later netlist audit. Footprints default per *bin* — a subclass per
footprint family:

```python
class R0603(Resistor):
    """Resistors from the 0603 bin: the footprint is the class default.

    The real bins resolve from the parts DB (``design/parts_db.py``);
    these stub footprints stand in so the example runs without the
    KiCad libraries.
    """

    default_footprint = "StubFP:R_0603"


class C0603(Capacitor):
    """Capacitors from the 0603 bin."""

    default_footprint = "StubFP:C_0603"
```

(In a real capture you don't declare bins by hand —
`design/parts_db.py` binds them from the parts DB, which also carries
assembler-stock status.)

The subcircuit. Ports are the interface: nets the outside world
reaches. They can carry *limit ranges* — `source` is what the port
drives out, `sink` what it accepts — and the checker verifies that a
connected sink's range covers the source's:

```python
class RcFilter(Subcircuit):
    """One RC low-pass channel: ``in`` → Rs → ``out``, Cs to GND.

    The ports carry limit ranges as interface contracts: ``in``
    accepts 0..3.3 V from the signal source, ``out`` drives 0..3.3 V
    toward the ADC. An instantiating parent's declared ranges are
    checked for containment against these.
    """

    def capture(self, circuit: Circuit) -> None:
        """Build the channel: ports in/out/GND, parts Rs/Cs."""
        in_ = circuit.port("in", sink=Limits(voltage=Interval(0, 3.3)))
        out = circuit.port("out", source=Limits(voltage=Interval(0, 3.3)))
        gnd = circuit.port("GND")
        circuit.part("Rs", R0603("4k7", a=in_, b=out))
        circuit.part("Cs", C0603("100n", a=out, b=gnd))
```

Three things to internalize here:

- **Construction *is* wiring.** `circuit.part("Rs", R0603("4k7", a=in_, b=out))` places the resistor and connects its pins in one call.
  Pin keywords are keyword-only; only unpolarized two-pin parts
  (`Resistor`, `Capacitor`) take the value positionally — anything
  where orientation matters (`Diode`, `Led`, `Bat54s`) is keyword-only
  throughout. `connect()` exists for symbol-placed parts
  (`circuit.part("R1", symbol="Device:R")`) and multi-unit packages.
- **Ports wire like nets inside the subcircuit.** The difference shows
  up at instantiation and in the checker: ports are exempt from the
  dangling-net checks, because reaching outside is their job.
- **`Interval`s are closed, containment inclusive** — `Interval(0, 3.6)`
  covers `Interval(0, 3.3)`. An undeclared side is *no data*, not an
  error.

The board instantiates the filter twice and binds every port by
keyword:

```python
def capture(symbols: SymbolTable) -> Circuit:
    """Build the tutorial board: two filter channels sharing one GND."""
    board = Circuit("filter-board", symbols)
    ain1 = board.port("ain1", source=Limits(voltage=Interval(0, 3.3)))
    ain2 = board.port("ain2", source=Limits(voltage=Interval(0, 3.3)))
    adc1 = board.port("adc1", sink=Limits(voltage=Interval(0, 3.6)))
    adc2 = board.port("adc2", sink=Limits(voltage=Interval(0, 3.6)))
    gnd = board.port("GND")
    # "in" is a Python keyword, so that port binds via **-unpacking.
    board.instance("FILT1", RcFilter(), out=adc1, GND=gnd, **{"in": ain1})
    board.instance("FILT2", RcFilter(), out=adc2, GND=gnd, **{"in": ain2})
    return board
```

`instance()` runs the subcircuit's capture into a child circuit and
checks the binding immediately: every declared port must be bound, and
no binding may name a port that doesn't exist — interface drift breaks
the capture that introduced it, not a later stage. (The `**{"in": ...}`
dance is how you bind a port whose name is a Python keyword.) Note the
directions: the board's `ain1` declares `source` (the outside world
drives it), each filter's `in` declares `sink` — containment checks
that pairing.

## Checking

`check()` is the one validation pass. Structural invariants — duplicate
refs, a pin on two nets, `/` in a name — raise `DefinitionError` at
capture; everything semantic batches into a list of `Issue`s with a
`Severity` (`warning`, `error`, `waived`). `raise_on_errors` turns the
batch into a `CheckError` for scripts:

```python
def test_board_checks_clean(symbols: StubSymbols, footprints: StubFootprints) -> None:
    assert check(capture(symbols), footprints=footprints) == []
```

What the checker reports: parts without value or footprint, footprints
missing from the libraries or mismatching the symbol's filters,
unconnected pins, empty and single-pin nets, multiple power outputs on
one net, power inputs with no driver — and the port-range containment
contract. Declaring the ADC sink narrower than the filter's output
range makes it fire, addressed by hierarchical path:

```python
def test_range_containment_fires(symbols: StubSymbols) -> None:
    board = Circuit("narrow-adc", symbols)
    ain = board.port("ain", source=Limits(voltage=Interval(0, 3.3)))
    adc = board.port("adc", sink=Limits(voltage=Interval(0, 1.8)))
    gnd = board.port("GND")
    board.instance("FILT1", RcFilter(), out=adc, GND=gnd, **{"in": ain})
    errors = [i for i in check(board) if i.severity is Severity.ERROR]
    assert len(errors) == 1
    assert errors[0].check == "range-containment"
    assert errors[0].path == "FILT1/out"
```

When the finding is deliberate, you don't suppress it with a comment —
you *waive* it, as data in the capture, addressed by check id and path,
with a reason. The error degrades to a `WAIVED` finding: visible in
every report, auditable in review, and a waiver that stops matching
anything warns as stale:

```python
def test_waiver_degrades_the_error(symbols: StubSymbols) -> None:
    board = Circuit("narrow-adc", symbols)
    ain = board.port("ain", source=Limits(voltage=Interval(0, 3.3)))
    adc = board.port("adc", sink=Limits(voltage=Interval(0, 1.8)))
    gnd = board.port("GND")
    board.instance("FILT1", RcFilter(), out=adc, GND=gnd, **{"in": ain})
    board.waive(
        "range-containment",
        "FILT1/out",
        reason="the ADC pin is 1V8-only by design; the divider guarantees the level",
    )
    issues = check(board)
    assert [issue.severity for issue in issues] == [Severity.WAIVED]
    raise_on_errors(issues)
```

## Flattening: what checks and emitters see

Hierarchy is capture-time structure. `flatten()` reduces it to the flat
IR every downstream stage consumes: instance names prefix part
references and internal nets (`FILT1/Rs`), and each port net merges
into the net the instance bound it to:

```python
def test_flatten_prefixes_instance_names(symbols: StubSymbols) -> None:
    flat = capture(symbols).flatten()
    assert sorted(flat.parts) == ["FILT1/Cs", "FILT1/Rs", "FILT2/Cs", "FILT2/Rs"]
    # Each port net merges into the net its instance bound it to; the
    # internal names are gone.
    assert "FILT1/in" not in flat.nets
    assert {pin.part.ref for pin in flat.nets["ain1"].pins} == {"FILT1/Rs"}
    assert {pin.part.ref for pin in flat.nets["GND"].pins} == {
        "FILT1/Cs",
        "FILT2/Cs",
    }
```

You almost never call `flatten()` yourself — `check`, the emitters, and
the annotation stage all flatten implicitly and report hierarchical
paths. The explicit names at every level are what keep those paths
stable across source edits. (The one stage that must see the hierarchy
is `apply_transforms` — it runs *between* capture and check; see
[dsl-reference.md](dsl-reference.md).)

## Annotating and emitting

Capture paths (`FILT1/Rs`) are the stable identity; the board carries
refdes (`R1`). Annotation is an explicit, repeatable stage: `annotate`
maps paths to refdes (preserving a `prior=` table for parts that
survive an edit), `apply_annotation` renames the IR for emission, and
`annotation_from_pcb` folds pcbnew's geographic renumbering back. The
tables are JSON on disk, byte-identical on write — a renumbering diff
in review is exactly the placement change. Emitters consume the
annotated IR:

```python
def test_netlist_emission(symbols: StubSymbols) -> None:
    board = capture(symbols)
    # Pre-annotation, comp refs are the hierarchical capture paths.
    assert '(comp (ref "FILT1/Rs")' in emit_netlist(board)
    # Annotation maps capture paths to refdes; emission for the board
    # runs on the annotated IR.
    netlist = emit_netlist(apply_annotation(board, annotate(board)))
    for ref in ("R1", "R2", "C1", "C2"):
        assert f'(comp (ref "{ref}")' in netlist
    assert '(comp (ref "FILT1' not in netlist
    assert '(name "GND")' in netlist
```

All emitters are byte-identical across runs — natural-sorted iteration,
content-derived timestamps, no dates or paths leak into the output — so
golden files pin them in CI.

The emitter family:

- **`emit_netlist(circuit)`** — the KiCad `.net` pcbnew imports. Power
  symbols (`power:+3V3`-class) are schematic-only net markers and stay
  out of the components and net nodes, matching eeschema.
- **`to_dot(circuit)`** — the bipartite parts/nets Graphviz view for
  human review.
- **`emit_spice(circuit, name=..., models={...})`** — the ngspice DUT
  `.subckt`; stimulus and `.meas` assertions live in external bench
  decks (`circuits/**/tb_*.cir`). Only symbols with a declared binding
  emit, and the caller passes the `.model` bodies — a part's value
  names its model. `python -m design.watchdog_chargepump --spice` is a
  working example.
- **`emit_pin_header(pin_map, ...)`** — the freestanding-C++ header the
  firmware includes, from the pin map (`design/node_pins.py`;
  regenerate with `python -m design.node_pins > firmware/node/pins.hpp`). `check_pin_map` is the GPIO-budget check
  over the same table: requests are by *function*, pads bind late as
  refinement data.

The real captures double as runnable end-to-end examples — in the dev
shell:

```
python -m design.node --dot            # node board, Graphviz view
python -m design.node                  # check + KiCad netlist
python -m design.watchdog_chargepump   # the §4 watchdog, standalone
```

## When things go wrong

Two failure channels, by design:

- **Capture-time: `DefinitionError`** (and `TypeError` from a typed
  part's signature). Duplicate refs or net names, a pin already on
  another net, `/` in any name (it's the hierarchy separator), unknown
  or unbound ports at `instance()`, footprint overrides naming unknown
  parts. These raise immediately, from the offending line.
- **Check-time: batched `Issue`s.** Everything electrical or
  board-facing, so one run reports all of it.

The common beginner errors, and what they mean:

| Symptom                                                                  | Cause                                                      |
| ------------------------------------------------------------------------ | ---------------------------------------------------------- |
| `DefinitionError: duplicate part reference 'R1'`                         | Refs are explicit; pick another name                       |
| `DefinitionError: ... must not contain '/'`                              | `/` is the hierarchy path separator                        |
| `TypeError` from a typed part                                            | Misspelled or missing pin keyword — construction is wiring |
| `DefinitionError: no net named 'vcc'`                                    | Declare nets (`net`/`port`) before wiring them             |
| `DefinitionError: instance 'FILT1': ports ['out'] left unconnected`      | `instance()` binds *every* port                            |
| `DefinitionError: instance 'FILT1': the subcircuit has no ports ['inp']` | Interface drift — the subcircuit renamed the port          |
| `error: R3 has no footprint (pcbnew needs one)`                          | No class default and no override; assign one               |
| `warning: net 'x' has a single pin`                                      | Dangling internal net; ports are exempt by design          |
| `error: port 'FILT1/out' ... sink range must cover source`               | Range containment; fix the design or `waive` with a reason |
| `warning: waiver ... matched no issue`                                   | Stale waiver — the finding it excused is gone; delete it   |

## Where next

- [dsl-reference.md](dsl-reference.md) — the full API map: port arrays
  and bundles, component sockets and multipacking, the parts DB,
  instrumentation transforms and the equivalence proof, the
  layout-checking side.
- [DESIGN.md §7](../DESIGN.md#7-design-capture-dsl) — the settled
  design decisions behind the shape you just used.
- `design/node.py` — the node board capture, the largest real user of
  everything above.
