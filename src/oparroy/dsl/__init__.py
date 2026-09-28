"""The oparroy design-capture DSL (DESIGN.md §7).

Single source of truth for schematic capture: a separable IR
(:mod:`oparroy.dsl.ir`) behind a plain function-call capture API —
including subcircuit composition with ports and a flattening pass
(:mod:`oparroy.dsl.subcircuit`) — a validation pass
(:mod:`oparroy.dsl.check`), and emitters — KiCad netlist
(:mod:`oparroy.dsl.kicad_emit`), Graphviz dot (:mod:`oparroy.dsl.dot`),
ngspice DUT netlist (:mod:`oparroy.dsl.spice_emit`).
Typed jellybean parts live in :mod:`oparroy.dsl.parts`; KiCad library
access lives in :mod:`oparroy.dsl.kicadlib`; the parts DB with
assembler-stock status lives in :mod:`oparroy.dsl.parts_db`. The
physical-layout side parses ``.kicad_pcb``
(:mod:`oparroy.dsl.kicad_pcb`), asserts layout properties
(:mod:`oparroy.dsl.layout_check`), and pushes net classes/keepouts
into pcbnew (:mod:`oparroy.dsl.pcb_emit`).
"""

from oparroy.dsl.check import (
    RANGE_CONTAINMENT,
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
    Interval,
    Limits,
    Net,
    Part,
    Pin,
    PinType,
    PortArray,
    Symbol,
    SymbolPin,
    SymbolTable,
    UnknownSymbolError,
    Waiver,
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
from oparroy.dsl.parts_db import (
    PartFilter,
    PartRecord,
    PartsDb,
    PartsDbError,
    SpiceModel,
    Stock,
    Tier,
)
from oparroy.dsl.pcb_emit import (
    Keepout,
    NetClassSpec,
    PcbSpec,
    PcbSpecError,
    emit_pcb,
)
from oparroy.dsl.spice_emit import emit_spice
from oparroy.dsl.subcircuit import Subcircuit

__all__ = [
    "RANGE_CONTAINMENT",
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
    "Interval",
    "Issue",
    "Keepout",
    "KiCadLibraries",
    "LayoutRules",
    "LibraryError",
    "Limits",
    "Net",
    "NetClass",
    "NetClassSpec",
    "Pad",
    "Part",
    "PartFilter",
    "PartRecord",
    "PartsDb",
    "PartsDbError",
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
    "SpiceModel",
    "Stock",
    "Subcircuit",
    "Symbol",
    "SymbolPin",
    "SymbolTable",
    "Text",
    "Tier",
    "TypedPart",
    "UnknownSymbolError",
    "Via",
    "Waiver",
    "Zone",
    "check",
    "check_layout",
    "emit_netlist",
    "emit_pcb",
    "emit_spice",
    "parse_board",
    "raise_on_errors",
    "to_dot",
]
