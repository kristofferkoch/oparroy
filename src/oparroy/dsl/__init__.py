"""The oparroy design-capture DSL (DESIGN.md §7).

Single source of truth for schematic capture: a separable IR
(:mod:`oparroy.dsl.ir`) behind a plain function-call capture API —
including subcircuit composition with ports and a flattening pass
(:mod:`oparroy.dsl.subcircuit`) — a validation pass
(:mod:`oparroy.dsl.check`), and emitters — KiCad netlist
(:mod:`oparroy.dsl.kicad_emit`), Graphviz dot (:mod:`oparroy.dsl.dot`).
Typed jellybean parts live in :mod:`oparroy.dsl.parts`; KiCad library
access lives in :mod:`oparroy.dsl.kicadlib`. The physical-layout side
parses ``.kicad_pcb`` (:mod:`oparroy.dsl.kicad_pcb`), asserts layout
properties (:mod:`oparroy.dsl.layout_check`), and pushes net
classes/keepouts into pcbnew (:mod:`oparroy.dsl.pcb_emit`).
"""

from oparroy.dsl.check import (
    CheckError,
    FootprintTable,
    Issue,
    Severity,
    check,
    raise_on_errors,
)
from oparroy.dsl.dot import to_dot
from oparroy.dsl.ir import (
    Bundle,
    Circuit,
    DefinitionError,
    Instance,
    Net,
    Part,
    Pin,
    PinType,
    PortArray,
    Symbol,
    SymbolPin,
    SymbolTable,
    UnknownSymbolError,
)
from oparroy.dsl.kicad_emit import emit_netlist
from oparroy.dsl.kicad_pcb import (
    Board,
    Edge,
    EdgeKind,
    Footprint,
    NetClass,
    Pad,
    PcbError,
    Point,
    Rect,
    Segment,
    Text,
    Via,
    Zone,
    parse_board,
)
from oparroy.dsl.kicadlib import KiCadLibraries, LibraryError
from oparroy.dsl.layout_check import (
    AdjacencyRule,
    BypassRule,
    LayoutRules,
    check_layout,
)
from oparroy.dsl.parts import Bat54s, BundleConnector, Capacitor, Resistor, TypedPart
from oparroy.dsl.pcb_emit import (
    Keepout,
    NetClassSpec,
    PcbSpec,
    PcbSpecError,
    emit_pcb,
)
from oparroy.dsl.subcircuit import Subcircuit

__all__ = [
    "AdjacencyRule",
    "Bat54s",
    "Board",
    "Bundle",
    "BundleConnector",
    "BypassRule",
    "Capacitor",
    "CheckError",
    "Circuit",
    "DefinitionError",
    "Edge",
    "EdgeKind",
    "Footprint",
    "FootprintTable",
    "Instance",
    "Issue",
    "Keepout",
    "KiCadLibraries",
    "LayoutRules",
    "LibraryError",
    "Net",
    "NetClass",
    "NetClassSpec",
    "Pad",
    "Part",
    "PcbError",
    "PcbSpec",
    "PcbSpecError",
    "Pin",
    "PinType",
    "Point",
    "PortArray",
    "Rect",
    "Resistor",
    "Segment",
    "Severity",
    "Subcircuit",
    "Symbol",
    "SymbolPin",
    "SymbolTable",
    "Text",
    "TypedPart",
    "UnknownSymbolError",
    "Via",
    "Zone",
    "check",
    "check_layout",
    "emit_netlist",
    "emit_pcb",
    "parse_board",
    "raise_on_errors",
    "to_dot",
]
