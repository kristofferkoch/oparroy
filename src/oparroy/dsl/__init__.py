"""The oparroy design-capture DSL (DESIGN.md §7).

Single source of truth for schematic capture: a separable IR
(:mod:`oparroy.dsl.ir`) behind a plain function-call capture API —
including subcircuit composition with ports and a flattening pass
(:mod:`oparroy.dsl.subcircuit`) — a validation pass
(:mod:`oparroy.dsl.check`), and emitters — KiCad netlist
(:mod:`oparroy.dsl.kicad_emit`), Graphviz dot (:mod:`oparroy.dsl.dot`).
Typed jellybean parts live in :mod:`oparroy.dsl.parts`; KiCad library
access lives in :mod:`oparroy.dsl.kicadlib`.
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
    SocketSpec,
    Symbol,
    SymbolPin,
    SymbolTable,
    SymbolUnit,
    UnitHandle,
    UnknownSymbolError,
)
from oparroy.dsl.kicad_emit import emit_netlist
from oparroy.dsl.kicadlib import KiCadLibraries, LibraryError
from oparroy.dsl.parts import (
    Bat54adw,
    Bat54s,
    BundleConnector,
    Capacitor,
    Diode,
    DiodeSocket,
    MultiUnitPart,
    Resistor,
    TypedPart,
)
from oparroy.dsl.subcircuit import Subcircuit

__all__ = [
    "Bat54adw",
    "Bat54s",
    "Bundle",
    "BundleConnector",
    "Capacitor",
    "CheckError",
    "Circuit",
    "DefinitionError",
    "Diode",
    "DiodeSocket",
    "FootprintTable",
    "Instance",
    "Issue",
    "KiCadLibraries",
    "LibraryError",
    "MultiUnitPart",
    "Net",
    "Part",
    "Pin",
    "PinType",
    "PortArray",
    "Resistor",
    "Severity",
    "SocketSpec",
    "Subcircuit",
    "Symbol",
    "SymbolPin",
    "SymbolTable",
    "SymbolUnit",
    "TypedPart",
    "UnitHandle",
    "UnknownSymbolError",
    "check",
    "emit_netlist",
    "raise_on_errors",
    "to_dot",
]
