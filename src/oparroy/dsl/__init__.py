"""The oparroy design-capture DSL (DESIGN.md §7).

Single source of truth for schematic capture: a separable IR
(:mod:`oparroy.dsl.ir`) behind a plain function-call capture API —
including subcircuit composition with ports and a flattening pass
(:mod:`oparroy.dsl.subcircuit`) — a validation pass
(:mod:`oparroy.dsl.check`), and emitters — KiCad netlist
(:mod:`oparroy.dsl.kicad_emit`), Graphviz dot (:mod:`oparroy.dsl.dot`),
freestanding-C++ pin headers (:mod:`oparroy.dsl.pinmap`).
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
    Symbol,
    SymbolPin,
    SymbolTable,
    UnknownSymbolError,
)
from oparroy.dsl.kicad_emit import emit_netlist
from oparroy.dsl.kicadlib import KiCadLibraries, LibraryError
from oparroy.dsl.parts import Bat54s, BundleConnector, Capacitor, Resistor, TypedPart
from oparroy.dsl.pinmap import (
    CH32V003F4P6,
    Chip,
    Pad,
    PinMap,
    PinRequest,
    check_pin_map,
    emit_pin_header,
)
from oparroy.dsl.subcircuit import Subcircuit

__all__ = [
    "CH32V003F4P6",
    "Bat54s",
    "Bundle",
    "BundleConnector",
    "Capacitor",
    "CheckError",
    "Chip",
    "Circuit",
    "DefinitionError",
    "FootprintTable",
    "Instance",
    "Issue",
    "KiCadLibraries",
    "LibraryError",
    "Net",
    "Pad",
    "Part",
    "Pin",
    "PinMap",
    "PinRequest",
    "PinType",
    "PortArray",
    "Resistor",
    "Severity",
    "Subcircuit",
    "Symbol",
    "SymbolPin",
    "SymbolTable",
    "TypedPart",
    "UnknownSymbolError",
    "check",
    "check_pin_map",
    "emit_netlist",
    "emit_pin_header",
    "raise_on_errors",
    "to_dot",
]
