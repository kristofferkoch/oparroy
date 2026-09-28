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
    Circuit,
    DefinitionError,
    Instance,
    Net,
    Part,
    Pin,
    PinType,
    Symbol,
    SymbolPin,
    SymbolTable,
    UnknownSymbolError,
)
from oparroy.dsl.kicad_emit import emit_netlist
from oparroy.dsl.kicadlib import KiCadLibraries, LibraryError
from oparroy.dsl.parts import Bat54s, Capacitor, Resistor, TypedPart
from oparroy.dsl.subcircuit import Subcircuit

__all__ = [
    "Bat54s",
    "Capacitor",
    "CheckError",
    "Circuit",
    "DefinitionError",
    "FootprintTable",
    "Instance",
    "Issue",
    "KiCadLibraries",
    "LibraryError",
    "Net",
    "Part",
    "Pin",
    "PinType",
    "Resistor",
    "Severity",
    "Subcircuit",
    "Symbol",
    "SymbolPin",
    "SymbolTable",
    "TypedPart",
    "UnknownSymbolError",
    "check",
    "emit_netlist",
    "raise_on_errors",
    "to_dot",
]
