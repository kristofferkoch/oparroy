"""``.kicad_pcb`` skeleton + ``.kicad_pro`` project emitter (DESIGN.md §7).

The DSL pushes constraints into the layout tool two ways, both
byte-identical per spec (like :mod:`oparroy.dsl.kicad_emit`: sorted
iteration, content-derived UUIDs, no dates or paths):

- :func:`emit_pcb` — the board skeleton: stackup and keepouts in the
  ``.kicad_pcb`` (KiCad 10 accepts ``(setup (stackup ...))``; paste
  layers must stay bare — thickness/material on a paste layer gets
  mangled into bogus dielectrics by the format upgrader, verified
  against KiCad 10.0.6).
- :func:`emit_project` — the project seed: net classes with
  net→class assignments and the board minimums (the DRC "Constraints"
  page) in the ``.kicad_pro`` JSON, where KiCad 10 actually reads
  them (``net_class`` in the board's setup is rejected since KiCad 10;
  per-class clearance and ``board.design_settings.rules`` minimums are
  DRC-enforced headless, verified the same way).

The skeleton round-trips through :func:`oparroy.dsl.kicad_pcb.parse_board`,
the project through :func:`oparroy.dsl.kicad_pro.parse_project`.
"""

import json
import re
import uuid
from dataclasses import dataclass

from oparroy.dsl.ir import natural_key
from oparroy.dsl.kicad_pcb import Point

_TOOL = "oparroy-dsl"
_KICAD_PCB_VERSION = "20240108"
_PCB_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://oparroy.koch.no/dsl/pcb")

_PROJECT_VERSION = 1
_NET_SETTINGS_VERSION = 3
_COLOR_NONE = "rgba(0, 0, 0, 0.000)"
_BUS_WIDTH_MILS = 12
_WIRE_WIDTH_MILS = 6
_MICROVIA_DIAMETER_MM = 0.3
_MICROVIA_DRILL_MM = 0.1
_DIFF_PAIR_GAP_MM = 0.25
_DIFF_PAIR_VIA_GAP_MM = 0.25
_DIFF_PAIR_WIDTH_MM = 0.2

# Standard user-layer numbering, fixed by KiCad.
_USER_LAYERS = (
    (36, "B.SilkS"),
    (37, "F.SilkS"),
    (38, "B.Mask"),
    (39, "F.Mask"),
    (44, "Edge.Cuts"),
)

_INNER_LAYER = re.compile(r"In(\d+)\.Cu")


class PcbSpecError(Exception):
    """A board spec asked for something KiCad cannot express."""


@dataclass(frozen=True)
class StackupLayer:
    """One stackup entry: name, KiCad type, optional physical data.

    Paste layers stay bare (name + type only) — see the module
    docstring for the upgrader quirk.
    """

    name: str
    type: str
    thickness_mm: float | None = None
    material: str | None = None
    epsilon_r: float | None = None
    loss_tangent: float | None = None


@dataclass(frozen=True)
class NetClassSpec:
    """A net class to declare in the emitted project's net settings."""

    name: str
    clearance_mm: float
    trace_width_mm: float
    via_dia_mm: float
    via_drill_mm: float
    nets: tuple[str, ...]
    description: str = ""


@dataclass(frozen=True)
class BoardMinimums:
    """The DRC "Constraints" page floors (``.kicad_pro`` design rules).

    A ``None`` field leaves that rule out of the emitted project.
    """

    min_clearance: float | None = None
    min_track_width: float | None = None
    min_via_diameter: float | None = None
    min_through_hole_diameter: float | None = None
    min_copper_edge_clearance: float | None = None
    min_hole_clearance: float | None = None
    solder_mask_clearance: float | None = None
    solder_mask_min_width: float | None = None


@dataclass(frozen=True)
class Keepout:
    """A keepout zone: no tracks, vias, pads, copper pours, or footprints."""

    polygon: tuple[Point, ...]
    layers: tuple[str, ...] = ("F.Cu", "B.Cu")


@dataclass(frozen=True)
class PcbSpec:
    """The constraint skeleton: stackup, net classes, minimums, keepouts."""

    name: str
    thickness_mm: float
    net_classes: tuple[NetClassSpec, ...]
    keepouts: tuple[Keepout, ...] = ()
    copper_layers: tuple[str, ...] = ("F.Cu", "B.Cu")
    stackup: tuple[StackupLayer, ...] = ()
    copper_finish: str = "ENIG"
    minimums: BoardMinimums | None = None


def emit_pcb(spec: PcbSpec) -> str:
    """Emit the spec as a ``.kicad_pcb`` skeleton, byte-identical per spec."""
    lines = [
        f'(kicad_pcb (version {_KICAD_PCB_VERSION}) (generator "{_TOOL}")',
        "  (general",
        f"    (thickness {_num(spec.thickness_mm)}))",
        '  (paper "A4")',
        "  (layers",
    ]
    lines.extend(
        f'    ({_layer_number(layer)} "{_quote(layer)}" signal)'
        for layer in spec.copper_layers
    )
    lines.extend(f'    ({number} "{name}" user)' for number, name in _USER_LAYERS)
    lines.append("  )")
    if spec.stackup:
        lines.append("  (setup")
        lines.extend(_emit_stackup(spec))
        lines.append("  )")
    lines.append('  (net 0 "")')
    for code, net in enumerate(_all_nets(spec), start=1):
        lines.append(f'  (net {code} "{_quote(net)}")')
    for keepout in spec.keepouts:
        lines.extend(_emit_keepout(spec, keepout))
    lines.append(")")
    return "\n".join(lines) + "\n"


def emit_project(spec: PcbSpec) -> str:
    """Emit the spec's DRC half as a ``.kicad_pro`` JSON seed.

    Net classes land in ``net_settings.classes`` (KiCad 10's full
    per-class key set), the net→class map in
    ``net_settings.netclass_assignments``, and the board minimums in
    ``board.design_settings.rules`` — the keys KiCad 10's DRC
    enforces headless. Keys are sorted, so emission is byte-identical
    and declaration-order independent.
    """
    payload: dict[str, object] = {
        "meta": {"filename": f"{spec.name}.kicad_pro", "version": _PROJECT_VERSION},
        "net_settings": {
            "classes": [
                _class_payload(net_class)
                for net_class in sorted(spec.net_classes, key=lambda nc: nc.name)
            ],
            "meta": {"version": _NET_SETTINGS_VERSION},
            "netclass_assignments": {
                net: net_class.name
                for net_class in spec.net_classes
                for net in net_class.nets
            },
        },
    }
    if spec.minimums is not None:
        payload["board"] = {"design_settings": {"rules": _rules_payload(spec.minimums)}}
    return json.dumps(payload, sort_keys=True, indent=2) + "\n"


def _class_payload(net_class: NetClassSpec) -> dict[str, object]:
    return {
        "bus_width": _BUS_WIDTH_MILS,
        "clearance": net_class.clearance_mm,
        "diff_pair_gap": _DIFF_PAIR_GAP_MM,
        "diff_pair_via_gap": _DIFF_PAIR_VIA_GAP_MM,
        "diff_pair_width": _DIFF_PAIR_WIDTH_MM,
        "line_style": 0,
        "microvia_diameter": _MICROVIA_DIAMETER_MM,
        "microvia_drill": _MICROVIA_DRILL_MM,
        "name": net_class.name,
        "pcb_color": _COLOR_NONE,
        "schematic_color": _COLOR_NONE,
        "track_width": net_class.trace_width_mm,
        "via_diameter": net_class.via_dia_mm,
        "via_drill": net_class.via_drill_mm,
        "wire_width": _WIRE_WIDTH_MILS,
    }


def _rules_payload(minimums: BoardMinimums) -> dict[str, float]:
    rules = {
        "min_clearance": minimums.min_clearance,
        "min_track_width": minimums.min_track_width,
        "min_via_diameter": minimums.min_via_diameter,
        "min_through_hole_diameter": minimums.min_through_hole_diameter,
        "min_copper_edge_clearance": minimums.min_copper_edge_clearance,
        "min_hole_clearance": minimums.min_hole_clearance,
        "solder_mask_clearance": minimums.solder_mask_clearance,
        "solder_mask_min_width": minimums.solder_mask_min_width,
    }
    return {key: value for key, value in rules.items() if value is not None}


def _emit_stackup(spec: PcbSpec) -> list[str]:
    lines = ["    (stackup"]
    for layer in spec.stackup:
        entry = f'      (layer "{_quote(layer.name)}" (type "{_quote(layer.type)}")'
        if layer.thickness_mm is not None:
            entry += f" (thickness {_num(layer.thickness_mm)})"
        if layer.material is not None:
            entry += f' (material "{_quote(layer.material)}")'
        if layer.epsilon_r is not None:
            entry += f" (epsilon_r {_num(layer.epsilon_r)})"
        if layer.loss_tangent is not None:
            entry += f" (loss_tangent {_num(layer.loss_tangent)})"
        lines.append(entry + ")")
    lines.append(f'      (copper_finish "{_quote(spec.copper_finish)}")')
    lines.append("      (dielectric_constraints no))")
    return lines


def _all_nets(spec: PcbSpec) -> list[str]:
    nets = {net for net_class in spec.net_classes for net in net_class.nets}
    return sorted(nets, key=natural_key)


def _emit_keepout(spec: PcbSpec, keepout: Keepout) -> list[str]:
    layers = " ".join(f'"{_quote(layer)}"' for layer in keepout.layers)
    content = "/".join(f"{_num(point.x)},{_num(point.y)}" for point in keepout.polygon)
    stamp = uuid.uuid5(_PCB_NS, f"{spec.name}/keepout/{content}/{layers}")
    points = " ".join(
        f"(xy {_num(point.x)} {_num(point.y)})" for point in keepout.polygon
    )
    return [
        f'  (zone (net 0) (net_name "") (layers {layers})',
        f'    (uuid "{stamp}")',
        "    (keepout",
        "      (tracks not_allowed)",
        "      (vias not_allowed)",
        "      (pads not_allowed)",
        "      (copperpour not_allowed)",
        "      (footprints not_allowed))",
        f"    (polygon (pts {points})))",
    ]


def _layer_number(name: str) -> int:
    if name == "F.Cu":
        return 0
    if name == "B.Cu":
        return 31
    if match := _INNER_LAYER.fullmatch(name):
        return int(match.group(1))
    msg = f"unknown copper layer {name!r} (F.Cu, In<n>.Cu, B.Cu)"
    raise PcbSpecError(msg)


def _num(value: float) -> str:
    return f"{value:g}"


def _quote(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')
