"""The oparroy design-capture DSL (DESIGN.md §7).

Single source of truth for schematic capture: a separable IR
(:mod:`oparroy.dsl.ir`) behind a plain function-call capture API —
including subcircuit composition with ports and a flattening pass
(:mod:`oparroy.dsl.subcircuit`) — a validation pass
(:mod:`oparroy.dsl.check`), instrumentation transforms with provenance
tags (:mod:`oparroy.dsl.transform`) and the reset-state equivalence
proof over them (:mod:`oparroy.dsl.equivalence`), the stages between
capture and
pcbnew —
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
(:mod:`oparroy.dsl.kicad_pcb`) and ``.kicad_pro``
(:mod:`oparroy.dsl.kicad_pro`), asserts layout properties
(:mod:`oparroy.dsl.layout_check`), and pushes stackup/keepouts into
pcbnew plus net classes and board minimums into the project
(:mod:`oparroy.dsl.pcb_emit`).
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
from oparroy.dsl.equivalence import (
    EQUIVALENCE,
    EquivalenceReport,
    Residual,
    check_equivalent,
)
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
    Provenance,
    Residuals,
    SocketSpec,
    Symbol,
    SymbolPin,
    SymbolTable,
    SymbolUnit,
    TileNet,
    UnitHandle,
    UnknownSymbolError,
    Waiver,
)
from oparroy.dsl.kicad_emit import emit_netlist
from oparroy.dsl.kicad_pcb import (
    ArcSegment,
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
from oparroy.dsl.kicad_pro import Project, ProjectError, parse_project
from oparroy.dsl.kicadlib import KiCadLibraries, LibraryError
from oparroy.dsl.layout_check import (
    AdjacencyRule,
    BypassRule,
    LayoutRules,
    check_layout,
)
from oparroy.dsl.parts import (
    Bat54adw,
    Bat54s,
    BundleConnector,
    Capacitor,
    Diode,
    DiodeSocket,
    Led,
    MultiUnitPart,
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
    BoardMinimums,
    Keepout,
    NetClassSpec,
    PcbSpec,
    PcbSpecError,
    StackupLayer,
    emit_pcb,
    emit_project,
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
from oparroy.dsl.transform import (
    AddShunt,
    AddTap,
    InsertSeries,
    PerInstance,
    PerTile,
    Scope,
    Substitute,
    Transform,
    TransformPart,
    apply_transforms,
)

__all__ = [
    "CH32V003F4P6",
    "EQUIVALENCE",
    "RANGE_CONTAINMENT",
    "AddShunt",
    "AddTap",
    "AdjacencyRule",
    "Annotation",
    "AnnotationError",
    "ArcSegment",
    "Bat54adw",
    "Bat54s",
    "Board",
    "BoardMinimums",
    "Bundle",
    "BundleConnector",
    "BypassRule",
    "Capacitor",
    "CheckError",
    "Chip",
    "Circuit",
    "DefinitionError",
    "Diode",
    "DiodeSocket",
    "Edge",
    "EdgeKind",
    "EquivalenceReport",
    "Footprint",
    "FootprintTable",
    "InsertSeries",
    "Instance",
    "Interval",
    "Issue",
    "Keepout",
    "KiCadLibraries",
    "LayoutRules",
    "Led",
    "LibraryError",
    "Limits",
    "MultiUnitPart",
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
    "PerInstance",
    "PerTile",
    "Pin",
    "PinMap",
    "PinRequest",
    "PinType",
    "Point",
    "PortArray",
    "Project",
    "ProjectError",
    "Provenance",
    "Rect",
    "Residual",
    "Residuals",
    "Resistor",
    "Scope",
    "Segment",
    "Severity",
    "SocketSpec",
    "SpiceModel",
    "StackupLayer",
    "Stock",
    "Subcircuit",
    "Substitute",
    "Symbol",
    "SymbolPin",
    "SymbolTable",
    "SymbolUnit",
    "Text",
    "Tier",
    "TileNet",
    "Transform",
    "TransformPart",
    "TvsDiode",
    "TypedPart",
    "UnitHandle",
    "UnknownSymbolError",
    "Via",
    "Waiver",
    "Zone",
    "annotate",
    "annotation_from_pcb",
    "apply_annotation",
    "apply_transforms",
    "assign_footprints",
    "check",
    "check_equivalent",
    "check_layout",
    "check_pin_map",
    "emit_netlist",
    "emit_pcb",
    "emit_pin_header",
    "emit_project",
    "emit_spice",
    "footprint_map",
    "overrides_from_json",
    "overrides_to_json",
    "parse_board",
    "parse_project",
    "raise_on_errors",
    "to_dot",
]
