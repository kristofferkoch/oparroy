# DSL reference

The map over the design-capture DSL (`src/oparroy/dsl/`). This doc
inventories the public surface and the invariants; it deliberately does
not duplicate detail — each module's docstring is the source of truth
for its semantics, and [dsl-tutorial.md](dsl-tutorial.md) teaches the
workflow end to end. Design rationale lives in
[DESIGN.md §7](../DESIGN.md#7-design-capture-dsl).

Everything below imports from the package root — `from oparroy.dsl import ...` — which re-exports the public API
(`src/oparroy/dsl/__init__.py` carries the explicit `__all__`).

## The pipeline

| Stage                      | Entry point                                                               | Input → output                                           | Invoked as                                 |
| -------------------------- | ------------------------------------------------------------------------- | -------------------------------------------------------- | ------------------------------------------ |
| Capture                    | `Circuit(name, symbols)`, `Subcircuit.capture`                            | Python calls → hierarchical IR                           | your `design/*.py` module                  |
| Transforms (CI board only) | `apply_transforms(circuit, plan)`                                         | hierarchical IR → instrumented IR, `Handles`             | between capture and check                  |
| Footprint assignment       | `assign_footprints(circuit, overrides)`                                   | IR + overrides JSON → flat assigned IR                   | `python -m design.node --footprints F`     |
| Validation                 | `check(circuit, footprints=...)`, `raise_on_errors`                       | IR → `list[Issue]`                                       | every `python -m design.*` main            |
| Annotation                 | `annotate(circuit, prior=...)`, `annotation_from_pcb`, `apply_annotation` | IR ↔ refdes table (JSON)                                 | `--annotation F`, `--back-annotate B`      |
| Emission                   | `emit_netlist`, `emit_spice`, `to_dot`, `emit_pin_header`                 | IR → KiCad `.net` / ngspice `.subckt` / dot / C++ header | module mains, `python -m design.node_pins` |

There is no installed CLI; entry points are module mains run in the nix
dev shell (`python -m design.node [--dot|--annotation F|--footprints F|--back-annotate B]`, `python -m design.watchdog_chargepump [--dot|--spice]`). Tests run via `uv run pytest`; doctests in `src/`
are part of the suite (`--doctest-modules`).

## Core IR (`ir.py`, `subcircuit.py`)

`Circuit(name, symbols)` — one captured circuit; `symbols` is a
`SymbolTable` (a `lookup(ref: str) -> Symbol` protocol). Methods:

- `part(ref, spec=None, *, symbol=None, value=None, footprint=None)` —
  place from a typed spec (places *and* wires) or a `"Lib:Name"` symbol
  string (places unwired; wire with `connect`).
- `net(name)` — declare an internal net.
- `port(name, *, source=Limits|None, sink=Limits|None)` — declare an
  interface net; exempt from dangling-net checks; ranges feed the
  containment check.
- `port_array(name, width)` — a width-fixed vector of ports
  `name[0]`…`name[width-1]`, bound element-wise at instantiation.
- `bundle(name, **members)` — group existing nets under member names,
  connectable as one unit; bound member-wise at instantiation.
- `connect(net, *pins)` — join pins onto a net; one pin sits on at most
  one net.
- `instance(name, subcircuit, **connections)` — capture a child and
  bind its entire interface by keyword: ports to nets, port arrays to
  equal-width sequences, bundles to same-membered bundles or mappings,
  component sockets to unit handles (`D1=u1.unit(3)`) or typed part
  classes (`D1=Bat54s`). `subcircuit` is a `Subcircuit` or any callable
  `(Circuit) -> None`.
- `socket(ref, SocketSpecSubclass)` — declare "this subcircuit needs a
  *part*"; the instantiating parent directs the packing.
- `waive(check, path, *, reason)` — a check waiver as capture data,
  addressed by check id and hierarchical path.
- `flatten()` — reduce the hierarchy to a new flat circuit (instance
  names prefix refs and internal nets; bound ports merge).
- `renamed(refs)`, `dump()` — rename by table (annotation applies
  this); human-readable dump.
- Pass machinery: `cut_net`, `remove_net`, `export_net` — the transform
  engine's primitives, not authoring API.

Data types:

- `Net` (`name`, `is_port`, `source`, `sink`, `pins`), `Pin` (`part`,
  `number`, `name`, `type`, `net`), `PinType` (KiCad electrical types).
- `Part` — `ref` (current name; the refdes after annotation),
  `identity` (capture name, what tstamps key on), `path` (instance
  path), `symbol`, `value`, `footprint`, `pins`; `pin(number)`,
  `unit(n)`, integer indexing (`part[1]`).
- `Interval(low, high)` — closed interval, inclusive containment.
  `Limits(voltage, current=None)` — a port's electrical ranges;
  `current` checked only when both sides declare it.
- `Symbol`, `SymbolPin`, `SymbolUnit`, `SymbolTable` (protocol) — the
  KiCad symbol model, multi-unit structure preserved.
- `PortArray` (a `Sequence[Net]`), `Bundle` (a `Mapping[str, Net]`),
  `Instance`, `UnitHandle`, `SocketSpec` (classvars `pins`, `default`).
- `Waiver`, `Provenance` (transform-origin tag), `TileNet`
  (path-addressed net key for pass tables), `Residuals` (per-part
  electrical residual magnitudes for the equivalence proof).
- Errors: `DefinitionError` (structural invariant violated at capture),
  `UnknownSymbolError`.

`Subcircuit` (`subcircuit.py`) — the ABC: subclass and implement
`capture(self, circuit)`.

## Typed parts (`parts.py`)

`TypedPart` — base class: classvars `symbol`, `pin_map` (pin keyword →
pin number or tuple), `default_value`, `default_footprint`,
`required_pins` (narrow it for many-pinned parts placed partly
unwired). Pin keywords are keyword-only; construction carries the
wiring; a missing or misspelled pin is a `TypeError` at the call site.

Concrete classes: `Resistor`, `Capacitor` (value positional, pins
`a`/`b`), `Diode` (`anode`/`cathode`), `Led`, `TvsDiode`, `Bat54s`
(series pair: `anode`/`cathode`/`com`), all keyword-only.
`MultiUnitPart` (classvar `unit_pins`) places a unit subset and wires
nothing — wire units individually via `part.unit(n).pinname` or pack
them into sockets; `Bat54adw` is the concrete quad. `DiodeSocket` is
the single-diode socket protocol. `BundleConnector` wires a connector's
pins from a `Bundle` declaratively.

Classes accrete as captures need them — no speculative zoo.

## Parts DB (`parts_db.py`)

`PartRecord` — one purchasable part: identity, symbol/footprint, stock
(`Stock`, `Tier`), `SpiceModel`, residuals. `PartFilter` — conjunctive
search knobs. `PartsDb` — `find(key)`, `select(filter)`,
`resolve(filter)` (exactly-one), `bind(key, base, class_name=...)`
→ a typed part class carrying the record's symbol/value/footprint and
residuals (how `design/parts_db.py` produces `R0603`/`C0603`),
`check_stock()`. `PartsDbError`.

## KiCad libraries (`kicadlib.py`)

`KiCadLibraries.from_env()` — symbol + footprint tables (doubles as
`SymbolTable` and `FootprintTable`) from the dev shell's env vars
(`OPARROY_KICAD_SYMBOL_DIR`, `OPARROY_KICAD_FOOTPRINT_DIR`,
`OPARROY_PROJECT_FOOTPRINT_DIR`). Raises `LibraryError` outside the
shell. `split_ref` (module-level) splits `"Lib:Name"`.

## Validation (`check.py`)

`check(circuit, *, footprints=None) -> list[Issue]` — the one
validation pass: flattens implicitly, checks port-range containment
over the hierarchy *before* flattening, then part and net rules over
the flat IR, and applies waivers last. `Issue(severity, message, check, path)`; `Severity` = `warning` / `error` / `waived`.
`raise_on_errors(issues)` raises `CheckError`. `RANGE_CONTAINMENT` is
the containment check's id for waivers. `FootprintTable` is the
`exists(footprint)` protocol (kicadlib or stubs).

## Footprints and annotation (`assign.py`, `annotate.py`)

`footprint_map(circuit)` dumps path → footprint; `assign_footprints( circuit, overrides)` applies the per-instance override table (keys are
flat capture paths; an unknown key raises); `overrides_to_json` /
`overrides_from_json` serialize it byte-identically.

`Annotation` — the capture-path → refdes table with JSON IO.
`annotate(circuit, *, prior=None)` preserves surviving assignments and
numbers new parts deterministically by prefix rules;
`apply_annotation(circuit, annotation)` renames the IR for emission;
`annotation_from_pcb(circuit, pcb_text, prior=...)` folds pcbnew's
geographic renumbering back via the content-derived tstamps.
`AnnotationError`.

## Emitters

- `emit_netlist(circuit)` (`kicad_emit.py`) — the KiCad `.net`; power
  symbols excluded; hierarchy survives as each comp's `sheetpath`.
- `emit_spice(circuit, *, name=None, models=None)` (`spice_emit.py`) —
  the ngspice DUT `.subckt`; only symbols with a declared binding emit
  (R, C, LED, BAT54S); the caller passes `.model` bodies and a part's
  value names its model; flattened refs gain a kind-letter prefix
  (`WD1/Rs` → `RWD1/Rs`).
- `to_dot(circuit)` (`dot.py`) — the bipartite Graphviz review view.
- `emit_pin_header` — see pin maps.

All emitters flatten implicitly and are byte-identical across runs:
natural-sorted iteration, content-derived UUID tstamps keyed on the
capture identity, nothing dated or path-derived in the output.

## Pin maps (`pinmap.py`)

`Chip`/`Pad` — datasheet-derived pad tables; `CH32V003F4P6` is the
built-in node MCU. `PinMap(chip)` — `request(name, uses=..., const=..., doc=...)` requests a pin by *function*, `reserve(pad, reason=...)`
takes pads off the budget (SWIO), `bind(**pads)` binds pads late as
refinement data. `check_pin_map(pin_map)` is the GPIO-budget check
(every request bound to a fitting pad, no pad twice, total honored);
`emit_pin_header(pin_map, *, source, regenerate, title)` emits the
freestanding-C++ header (`firmware/node/pins.hpp`).

## Transforms and equivalence (`transform.py`, `equivalence.py`)

The CI board's instrumentation as data over the plain capture
(background: [instrumentation-equivalence](instrumentation-equivalence.md),
[instrumented-ci](instrumented-ci.md)):

- Transform records: `InsertSeries` (cut a net, bridge through a part),
  `AddShunt` (switched branch to a rail, no cut), `AddTap` (export a
  net as a sense port), `Substitute` (re-drive the load side from an
  escaped board net). `TransformPart(ref, spec)` — one placed part; the
  ref may carry a `/` group prefix; the spec wires placeholder nets:
  `@a`/`@b` (cut sides), `@control`/`@source` (escaped ports), `@net`
  (a shunt's base net), any other `@name` a fresh shared net.
- Scopes: `PerTile(subcircuit, transforms)` instruments every instance
  of a subcircuit; `PerInstance(path, transforms)` addresses one
  instance. Scopes must not nest.
- `apply_transforms(circuit, plan) -> Handles` — runs on the
  *hierarchical* board between capture and check, mutating matched
  instance children in place; returns the escaped board nets keyed by
  `TileNet`. Multi-unit specs are rejected in transforms.
- `check_equivalent(base, instrumented, plan, *, reset_levels, budgets) -> EquivalenceReport` — the reset-state equivalence proof
  over provenance tags and `Residuals`; findings carry the
  `EQUIVALENCE` check id. `Residual`, `EquivalenceReport`.

## Layout side

Separate flow around the live board: `parse_board` → `Board`
(`Footprint`, `Segment`, `Via`, `Zone`, `Text`, `NetClass`, `Edge`,
`Point`, `Rect`, …; `PcbError`) parses `.kicad_pcb` (`kicad_pcb.py`);
`parse_project` → `Project` parses `.kicad_pro` (`kicad_pro.py`).
`check_layout(board, rules, project)` audits the board against
`LayoutRules` (stackup, net-class width/via, `AdjacencyRule`,
`BypassRule`, keepouts, …) (`layout_check.py`). `PcbSpec`
(`StackupLayer`, `NetClassSpec`, `BoardMinimums`, `Keepout`) feeds
`emit_pcb` / `emit_project`, the constraint-skeleton emitters that seed
a board (`pcb_emit.py`; `PcbSpecError`). `pcb_merge.py`
(`merge_settings`, drives pcbnew) is importable but not re-exported.

## Invariants and quirks

1. **Explicit names everywhere.** Refs and net names are capture-time
   choices; `/` is forbidden in every name (hierarchy separator);
   flattening prefixes (`WD1/Rs`, `WD1/x`), so identities are stable
   across edits and findings report hierarchical paths.
1. **Identity ≠ refdes.** `Part.identity` is the capture name (tstamps
   key on it); `Part.ref` becomes the refdes after `apply_annotation`.
   Emission for a board runs on the annotated IR.
1. **Construction is wiring** for typed parts; `connect()` is for
   symbol-placed parts, multi-unit handles, and sockets. Reconnecting a
   pin to the net it already sits on is a no-op (shared multi-unit
   pins).
1. **Two failure channels**: structural misuse raises `DefinitionError`
   (or `TypeError` from a typed part's signature) at capture; semantic
   findings batch from `check()`. A rejected mutating call changes
   nothing.
1. **Ports are exempt** from dangling-net checks; unbound top-level
   ports keep the exemption through flattening.
1. **Port arrays bind element-wise** (exact width; elements also bind
   individually as `led[0]=...`); **bundles bind member-wise** to a
   same-membered bundle or mapping; one net may not alias two members
   of one bundle; a port reached through two groups must resolve to one
   parent net. Python-keyword port names bind via `**{"in": net}`.
1. **Multi-unit parts**: declared `unit_pins` are the placed subset;
   unplaced units materialize no pins; a physical pin shared across
   placed units is one `Pin` on one net (KiCad ERC's shared-pin rule,
   structural in the IR).
1. **Everything downstream flattens implicitly** — except
   `apply_transforms`, which must run on the hierarchical board and
   mutates instance children in place.
1. **Range containment** (`sink` covers `source`) is checked per net
   over the hierarchy *before* flattening; an undeclared side is no
   data, never a finding. Waivers are capture data with a reason; a
   waived error stays visible as `WAIVED`; a stale waiver warns.
1. **Footprints**: class defaults resolve at capture; overrides are
   JSON keyed by flat path; a part reaching `check` without a footprint
   is an error. Power symbols (`power:+3V3`-class) are schematic-only
   net markers, excluded from netlists.
1. **Deterministic output**: all emitters and both JSON tables are
   byte-identical across runs; golden files pin them in CI.
1. **Spice emission is binding-limited**: only symbols in
   `spice_emit._BINDINGS` emit; undefined model references raise.
1. **KiCad libraries come from the nix dev shell.** Outside it,
   `KiCadLibraries.from_env()` raises `LibraryError`; tests use the
   stub tables in `tests/conftest.py`.
1. **Unbound sockets materialize** as their protocol's `default` part
   at flattening; a socket packed into a package unit materializes no
   part of its own.

## Pointers

- [dsl-tutorial.md](dsl-tutorial.md) — the guided tour.
- [DESIGN.md §7](../DESIGN.md#7-design-capture-dsl) — the settled
  decisions behind the DSL's shape.
- [prior-art-schematic-gen](prior-art-schematic-gen.md) —
  why the DSL emits netlists instead of drawing schematics.
- Module docstrings under `src/oparroy/dsl/` — the per-module source of
  truth, with doctests the suite runs.
