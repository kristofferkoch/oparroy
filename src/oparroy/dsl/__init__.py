"""The oparroy design-capture DSL (DESIGN.md §7).

Single source of truth for schematic capture: a separable IR
(:mod:`oparroy.dsl.ir`) behind a plain function-call capture API —
including subcircuit composition with ports and a flattening pass
(:mod:`oparroy.dsl.subcircuit`) — a validation pass
(:mod:`oparroy.dsl.check`), the stages between capture and pcbnew —
footprint assignment (:mod:`oparroy.dsl.assign`) and annotation with
back-annotation (:mod:`oparroy.dsl.annotate`) — and emitters — KiCad
netlist (:mod:`oparroy.dsl.kicad_emit`), Graphviz dot
(:mod:`oparroy.dsl.dot`), ngspice DUT netlist
(:mod:`oparroy.dsl.spice_emit`), freestanding-C++ pin headers
(:mod:`oparroy.dsl.pinmap`).
Typed jellybean parts live in :mod:`oparroy.dsl.parts`; KiCad library
access lives in :mod:`oparroy.dsl.kicadlib`; the parts DB with
assembler-stock status lives in :mod:`oparroy.dsl.parts_db`. The
physical-layout side parses ``.kicad_pcb``
(:mod:`oparroy.dsl.kicad_pcb`), asserts layout properties
(:mod:`oparroy.dsl.layout_check`), and pushes net classes/keepouts
into pcbnew (:mod:`oparroy.dsl.pcb_emit`).
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
    PcbError,
    Point,
    Rect,
    Segment,
    Text,
    Via,
    Zone,
    parse_board,
)
from oparroy.dsl.kicad_pcb import (
    Pad as PcbPad,
)
from oparroy.dsl.kicadlib import KiCadLibraries, LibraryError
from oparroy.dsl.layout_check import (
    AdjacencyRule,
    BypassRule,
    LayoutRules,
    check_layout,
)
from oparroy.dsl.parts import (
    Bat54s,
    BundleConnector,
    Capacitor,
    Led,
    Resistor,
    TvsDiode,
    TypedPart,
)
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
from oparroy.dsl.pinmap import (
    CH32V003F4P6,
    Chip,
    Pad,
    PinMap,
    PinRequest,
    check_pin_map,
    emit_pin_header,
)
from oparroy.dsl.spice_emit import emit_spice
from oparroy.dsl.subcircuit import Subcircuit

__all__ = [
    "CH32V003F4P6",
    "RANGE_CONTAINMENT",
    "AdjacencyRule",
    "Annotation",
    "AnnotationError",
    "Bat54s",
    "Board",
    "Bundle",
    "BundleConnector",
    "BypassRule",
    "Capacitor",
    "CheckError",
    "Chip",
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
    "Led",
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
    "PcbPad",
    "PcbSpec",
    "PcbSpecError",
    "Pin",
    "PinMap",
    "PinRequest",
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
    "TvsDiode",
    "TypedPart",
    "UnknownSymbolError",
    "Via",
    "Waiver",
    "Zone",
    "annotate",
    "annotation_from_pcb",
    "apply_annotation",
    "assign_footprints",
    "check",
    "check_layout",
    "check_pin_map",
    "emit_netlist",
    "emit_pcb",
    "emit_pin_header",
    "emit_spice",
    "footprint_map",
    "overrides_from_json",
    "overrides_to_json",
    "parse_board",
    "raise_on_errors",
    "to_dot",
]
