"""The oparroy design-capture DSL (DESIGN.md §7).

Single source of truth for schematic capture: a separable IR
(:mod:`oparroy.dsl.ir`) behind a plain function-call capture API —
including subcircuit composition with ports and a flattening pass
(:mod:`oparroy.dsl.subcircuit`) — a validation pass
(:mod:`oparroy.dsl.check`), the stages between capture and pcbnew —
footprint assignment (:mod:`oparroy.dsl.assign`) and annotation with
back-annotation (:mod:`oparroy.dsl.annotate`) — and emitters — KiCad
netlist
(:mod:`oparroy.dsl.kicad_emit`), Graphviz dot (:mod:`oparroy.dsl.dot`).
Typed jellybean parts live in :mod:`oparroy.dsl.parts`; KiCad library
access lives in :mod:`oparroy.dsl.kicadlib`.
"""

from oparroy.dsl.annotate import (
    Annotation,
    AnnotationError,
    annotate,
    annotation_from_pcb,
    apply_annotation,
)
from oparroy.dsl.assign import (
    assign_footprints,
    footprint_map,
    overrides_from_json,
    overrides_to_json,
)
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
from oparroy.dsl.parts import (
    Bat54s,
    BundleConnector,
    Capacitor,
    Led,
    Resistor,
    TvsDiode,
    TypedPart,
)
from oparroy.dsl.subcircuit import Subcircuit

__all__ = [
    "Annotation",
    "AnnotationError",
    "Bat54s",
    "Bundle",
    "BundleConnector",
    "Capacitor",
    "CheckError",
    "Circuit",
    "DefinitionError",
    "FootprintTable",
    "Instance",
    "Issue",
    "KiCadLibraries",
    "Led",
    "LibraryError",
    "Net",
    "Part",
    "Pin",
    "PinType",
    "PortArray",
    "Resistor",
    "Severity",
    "Subcircuit",
    "Symbol",
    "SymbolPin",
    "SymbolTable",
    "TvsDiode",
    "TypedPart",
    "UnknownSymbolError",
    "annotate",
    "annotation_from_pcb",
    "apply_annotation",
    "assign_footprints",
    "check",
    "emit_netlist",
    "footprint_map",
    "overrides_from_json",
    "overrides_to_json",
    "raise_on_errors",
    "to_dot",
]
