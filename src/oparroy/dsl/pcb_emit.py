"""``.kicad_pcb`` skeleton emitter: push constraints into the layout tool.

The DSL pushes constraints the other way too (DESIGN.md §7): the
stackup contract, net classes, and keepouts are emitted as a skeleton
``.kicad_pcb`` so pcbnew's own DRC guides layout toward compliance
before the audit (:mod:`oparroy.dsl.layout_check`) runs. The skeleton
round-trips through :func:`oparroy.dsl.kicad_pcb.parse_board`.
Emission is byte-identical across runs, like
:mod:`oparroy.dsl.kicad_emit`: sorted iteration, content-derived UUIDs,
no dates or paths.
"""

import re
import uuid
from dataclasses import dataclass

from oparroy.dsl.ir import natural_key
from oparroy.dsl.kicad_pcb import Point

_TOOL = "oparroy-dsl"
_KICAD_PCB_VERSION = "20240108"
_PCB_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://oparroy.koch.no/dsl/pcb")

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
class NetClassSpec:
    """A net class to declare in the emitted board's setup section."""

    name: str
    clearance_mm: float
    trace_width_mm: float
    via_dia_mm: float
    via_drill_mm: float
    nets: tuple[str, ...]
    description: str = ""


@dataclass(frozen=True)
class Keepout:
    """A keepout zone: no tracks, vias, pads, copper pours, or footprints."""

    polygon: tuple[Point, ...]
    layers: tuple[str, ...] = ("F.Cu", "B.Cu")


@dataclass(frozen=True)
class PcbSpec:
    """The constraint skeleton: stackup, net classes, keepouts."""

    name: str
    thickness_mm: float
    net_classes: tuple[NetClassSpec, ...]
    keepouts: tuple[Keepout, ...] = ()
    copper_layers: tuple[str, ...] = ("F.Cu", "B.Cu")


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
    lines.append("  (setup")
    for net_class in sorted(spec.net_classes, key=lambda nc: nc.name):
        lines.extend(_emit_net_class(net_class))
    lines.append("  )")
    lines.append('  (net 0 "")')
    for code, net in enumerate(_all_nets(spec), start=1):
        lines.append(f'  (net {code} "{_quote(net)}")')
    for keepout in spec.keepouts:
        lines.extend(_emit_keepout(spec, keepout))
    lines.append(")")
    return "\n".join(lines) + "\n"


def _emit_net_class(net_class: NetClassSpec) -> list[str]:
    lines = [
        (
            f'    (net_class "{_quote(net_class.name)}" '
            f'"{_quote(net_class.description)}"'
        ),
        f"      (clearance {_num(net_class.clearance_mm)})",
        f"      (trace_width {_num(net_class.trace_width_mm)})",
        f"      (via_dia {_num(net_class.via_dia_mm)})",
        f"      (via_drill {_num(net_class.via_drill_mm)})",
    ]
    nets = sorted(net_class.nets, key=natural_key)
    lines.extend(f'      (add_net "{_quote(net)}")' for net in nets)
    lines[-1] += ")"
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
