"""``.kicad_pro`` project parser: net classes and board minimums.

KiCad 10 keeps the DRC contract — net classes, net→class assignments,
and the board minimums — in the project JSON, not the board file (see
:mod:`oparroy.dsl.pcb_emit`). This module reads that JSON back, mapping
classes onto the :class:`oparroy.dsl.kicad_pcb.NetClass` shape the
audit (:mod:`oparroy.dsl.layout_check`) already reasons over, so the
audit checks against the same numbers KiCad's DRC enforces. The reader
is tolerant: keys the model does not need (GUI settings, plot
parameters, …) are ignored.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from oparroy.dsl.kicad_pcb import NetClass
from oparroy.dsl.pcb_emit import BoardMinimums

if TYPE_CHECKING:
    from collections.abc import Mapping


class ProjectError(Exception):
    """The input is not a ``.kicad_pro`` project."""


@dataclass(frozen=True)
class Project:
    """The parsed project: net classes, assignments, board minimums."""

    net_classes: tuple[NetClass, ...]
    assignments: Mapping[str, str]
    minimums: BoardMinimums | None

    def net_class_of(self, net: str) -> NetClass | None:
        """Return the class carrying ``net``; unassigned nets land on Default.

        >>> project = parse_project(
        ...     '{"net_settings": {"classes": ['
        ...     '{"name": "Default", "track_width": 0.2},'
        ...     '{"name": "Power", "track_width": 0.5}],'
        ...     '"netclass_assignments": {"BYPASS": "Power"}}}')
        >>> project.net_class_of("BYPASS").name
        'Power'
        >>> project.net_class_of("SIG").name  # unassigned: KiCad's Default
        'Default'
        >>> project.net_class_of("SIG").trace_width_mm
        0.2
        """
        by_name = {net_class.name: net_class for net_class in self.net_classes}
        return by_name.get(self.assignments.get(net, "Default"))


def parse_project(text: str) -> Project:
    """Parse ``.kicad_pro`` content into a :class:`Project`.

    Raises :class:`ProjectError` when the text is not JSON, or the
    project structure (objects where objects are expected, a class
    without a name) is broken.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        msg = f"not a .kicad_pro document: {error}"
        raise ProjectError(msg) from None
    root = _mapping(data, "project")
    net_settings = _mapping(root.get("net_settings", {}), "net_settings")
    assignments = {
        str(net): str(name)
        for net, name in _mapping(
            net_settings.get("netclass_assignments", {}), "netclass_assignments"
        ).items()
    }
    classes = net_settings.get("classes", [])
    if not isinstance(classes, list):
        msg = "expected a list for net_settings.classes"
        raise ProjectError(msg)
    return Project(
        net_classes=tuple(_parse_class(entry, assignments) for entry in classes),
        assignments=assignments,
        minimums=_parse_minimums(root),
    )


def _mapping(value: object, what: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        msg = f"expected an object for {what}"
        raise ProjectError(msg)
    return value


def _opt_number(data: Mapping[str, object], key: str, what: str) -> float | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, int | float):
        msg = f"expected a number for {what}, got {value!r}"
        raise ProjectError(msg)
    return float(value)


def _parse_class(entry: object, assignments: Mapping[str, str]) -> NetClass:
    data = _mapping(entry, "net class")
    name = data.get("name")
    if not isinstance(name, str):
        msg = "net class without a name"
        raise ProjectError(msg)
    return NetClass(
        name=name,
        clearance_mm=_opt_number(data, "clearance", "clearance"),
        trace_width_mm=_opt_number(data, "track_width", "track width"),
        via_dia_mm=_opt_number(data, "via_diameter", "via diameter"),
        via_drill_mm=_opt_number(data, "via_drill", "via drill"),
        nets=frozenset(
            net for net, class_name in assignments.items() if class_name == name
        ),
    )


def _parse_minimums(root: Mapping[str, object]) -> BoardMinimums | None:
    board = root.get("board")
    if board is None:
        return None
    settings = _mapping(board, "board").get("design_settings")
    if settings is None:
        return None
    rules = _mapping(settings, "design_settings").get("rules")
    if rules is None:
        return None
    data = _mapping(rules, "rules")
    return BoardMinimums(
        min_clearance=_opt_number(data, "min_clearance", "minimum clearance"),
        min_track_width=_opt_number(data, "min_track_width", "minimum track width"),
        min_via_diameter=_opt_number(data, "min_via_diameter", "minimum via diameter"),
        min_through_hole_diameter=_opt_number(
            data, "min_through_hole_diameter", "minimum through-hole diameter"
        ),
        min_copper_edge_clearance=_opt_number(
            data, "min_copper_edge_clearance", "minimum copper-edge clearance"
        ),
        min_hole_clearance=_opt_number(
            data, "min_hole_clearance", "minimum hole clearance"
        ),
        solder_mask_clearance=_opt_number(
            data, "solder_mask_clearance", "solder-mask clearance"
        ),
        solder_mask_min_width=_opt_number(
            data, "solder_mask_min_width", "solder-mask minimum width"
        ),
    )
