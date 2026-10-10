"""``.kicad_pcb`` board parser: the layout the DSL audits (DESIGN.md §7).

Layout is drawn in KiCad, but the DSL audits it: this module reads a
``.kicad_pcb`` (the same s-expression dialect as the library files, so
:mod:`oparroy.dsl.sexpr` is the reader) into a typed board model that
:mod:`oparroy.dsl.layout_check` asserts project properties against —
placement, geometry, stackup, silkscreen. The reader is tolerant:
anything the model does not need (3-D models, render settings, …) is
skipped, so files from newer KiCad versions keep parsing. KiCad 10's
native format (20260206) drops the numeric net table and writes net
names inline on segments, vias, and pads; both forms read (verified
against 10.0.6).
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from oparroy.dsl.sexpr import Sexp, parse

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping


class PcbError(Exception):
    """The input is not a ``.kicad_pcb`` board."""


_EPSILON_MM2 = 1e-6


@dataclass(frozen=True)
class Point:
    """A board coordinate in mm, KiCad's native unit."""

    x: float
    y: float

    def distance(self, other: Point) -> float:
        """Euclidean distance to another point, in mm.

        >>> Point(0, 0).distance(Point(3, 4))
        5.0
        """
        return math.hypot(self.x - other.x, self.y - other.y)


@dataclass(frozen=True)
class Pad:
    """One footprint pad: number, shape kind, position, attached net.

    ``at`` is footprint-local (the pad's ``at`` inside its footprint);
    footprint rotation is not modeled, so board-absolute pad positions
    are not yet recoverable. ``size`` and ``drill`` read the pad's
    ``(size x y)`` and ``(drill [oval] x [y])`` nodes — a round drill
    repeats its diameter; ``None`` when the node is absent.
    """

    number: str
    kind: str
    at: Point
    net: str | None
    size: Point | None = None
    drill: Point | None = None


@dataclass(frozen=True)
class Footprint:
    """A placed footprint: library reference, refdes, position, pads.

    ``at`` is the board-absolute anchor; the rotation component of the
    footprint's ``at`` is not modeled.
    """

    lib: str
    ref: str
    at: Point
    layer: str
    pads: tuple[Pad, ...]


@dataclass(frozen=True)
class Segment:
    """A straight copper track; ``net`` is the resolved net name."""

    start: Point
    end: Point
    width: float
    layer: str
    net: str

    @property
    def length(self) -> float:
        """Track length in mm.

        >>> Segment(Point(0, 0), Point(3, 4), 0.25, "F.Cu", "SIG").length
        5.0
        """
        return self.start.distance(self.end)


@dataclass(frozen=True)
class ArcSegment:
    """A copper arc track; ``net`` is the resolved net name.

    KiCad writes board-level ``(arc (start …) (mid …) (end …) (width …)
    (layer …) (net …))`` tracks: the circle through the three points,
    swept from ``start`` to ``end`` through ``mid`` (verified against
    KiCad 10.0.6). Not to be confused with ``gr_arc``, the graphic
    primitive the outline uses.
    """

    start: Point
    mid: Point
    end: Point
    width: float
    layer: str
    net: str

    @property
    def length(self) -> float:
        """Arc length in mm: circumradius times central angle.

        A collinear arc has no circumcircle; its length falls back to
        the start-mid-end polyline.

        >>> arc = ArcSegment(Point(10, 0), Point(0, 10), Point(-10, 0),
        ...                  0.4, "F.Cu", "SIG")
        >>> arc.length
        31.41592653589793
        """
        circle = _circumcircle(self.start, self.mid, self.end)
        if circle is None:
            return self.start.distance(self.mid) + self.mid.distance(self.end)
        _, radius, sweep = circle
        return radius * abs(sweep)

    def chords(self, sagitta_mm: float) -> tuple[tuple[Point, Point], ...]:
        """Polygonize into chords deviating by at most ``sagitta_mm``.

        The chord chain keeps the arc's endpoints, so connectivity at
        the joints is exact.

        >>> arc = ArcSegment(Point(10, 0), Point(0, 10), Point(-10, 0),
        ...                  0.4, "F.Cu", "SIG")
        >>> chords = arc.chords(0.1)
        >>> chords[0][0], chords[-1][1]
        (Point(x=10, y=0), Point(x=-10, y=0))
        """
        circle = _circumcircle(self.start, self.mid, self.end)
        if circle is None:
            return ((self.start, self.mid), (self.mid, self.end))
        center, radius, sweep = circle
        if radius <= sagitta_mm:
            return ((self.start, self.end),)
        # Half the chord angle at sagitta s on radius r: acos(1 - s/r).
        steps = max(1, math.ceil(abs(sweep) / (2 * math.acos(1 - sagitta_mm / radius))))
        a0 = math.atan2(self.start.y - center.y, self.start.x - center.x)
        points = [self.start]
        points.extend(
            Point(
                center.x + radius * math.cos(a0 + sweep * i / steps),
                center.y + radius * math.sin(a0 + sweep * i / steps),
            )
            for i in range(1, steps)
        )
        points.append(self.end)
        return tuple(itertools.pairwise(points))


@dataclass(frozen=True)
class Via:
    """A plated through-via; ``net`` is the resolved net name."""

    at: Point
    size: float
    drill: float
    layers: tuple[str, ...]
    net: str


def _circumcircle(a: Point, m: Point, b: Point) -> tuple[Point, float, float] | None:
    """Circle through three points: center, radius, signed sweep a→b via m.

    The sweep is positive counterclockwise. Collinear points have no
    circumcircle: ``None``.
    """
    double_d = 2 * (a.x * (m.y - b.y) + m.x * (b.y - a.y) + b.x * (a.y - m.y))
    if abs(double_d) < _EPSILON_MM2:
        return None
    a2, m2, b2 = a.x**2 + a.y**2, m.x**2 + m.y**2, b.x**2 + b.y**2
    center = Point(
        (a2 * (m.y - b.y) + m2 * (b.y - a.y) + b2 * (a.y - m.y)) / double_d,
        (a2 * (b.x - m.x) + m2 * (a.x - b.x) + b2 * (m.x - a.x)) / double_d,
    )

    def angle(p: Point) -> float:
        return math.atan2(p.y - center.y, p.x - center.x)

    a0 = angle(a)
    ccw = (angle(b) - a0) % math.tau
    sweep = ccw if (angle(m) - a0) % math.tau <= ccw else ccw - math.tau
    return center, center.distance(a), sweep


@dataclass(frozen=True)
class Text:
    """A board-level graphic text (``gr_text``)."""

    text: str
    layer: str
    at: Point


class EdgeKind(StrEnum):
    """Board-outline primitive kinds."""

    LINE = "line"
    ARC = "arc"


@dataclass(frozen=True)
class Edge:
    """One graphic line or arc, typically on ``Edge.Cuts``.

    Arcs carry their KiCad ``mid`` point; lines leave it ``None``.
    """

    kind: EdgeKind
    start: Point
    end: Point
    layer: str
    mid: Point | None = None


@dataclass(frozen=True)
class Rect:
    """A graphic rectangle (``gr_rect``) — e.g. the serial-number box."""

    start: Point
    end: Point
    layer: str
    filled: bool

    @property
    def area(self) -> float:
        """Rectangle area in mm².

        >>> Rect(Point(0, 0), Point(15, 6), "F.SilkS", True).area
        90.0
        """
        return float(abs((self.end.x - self.start.x) * (self.end.y - self.start.y)))


@dataclass(frozen=True)
class Zone:
    """A zone; keepouts have ``keepout`` set and carry no net."""

    net: str | None
    layers: tuple[str, ...]
    keepout: bool
    polygon: tuple[Point, ...]


@dataclass(frozen=True)
class NetClass:
    """A ``(setup (net_class …))`` entry: geometry floors plus members."""

    name: str
    clearance_mm: float | None
    trace_width_mm: float | None
    via_dia_mm: float | None
    via_drill_mm: float | None
    nets: frozenset[str]


@dataclass(frozen=True)
class Board:
    """The parsed layout: everything the property checker reasons over."""

    thickness_mm: float | None
    copper_layers: tuple[str, ...]
    silkscreen_layers: tuple[str, ...]
    nets: Mapping[str, int]
    net_classes: tuple[NetClass, ...]
    footprints: tuple[Footprint, ...]
    segments: tuple[Segment, ...]
    arcs: tuple[ArcSegment, ...]
    vias: tuple[Via, ...]
    texts: tuple[Text, ...]
    edges: tuple[Edge, ...]
    rects: tuple[Rect, ...]
    zones: tuple[Zone, ...]

    def net_class_of(self, net: str) -> NetClass | None:
        """Return the net class carrying ``net``, or None when unclassed.

        >>> board = parse_board("(kicad_pcb (layers) (setup "
        ...     '(net_class "Default" "" (add_net "GND"))))')
        >>> board.net_class_of("GND").name
        'Default'
        >>> board.net_class_of("SIG") is None
        True
        """
        for net_class in self.net_classes:
            if net in net_class.nets:
                return net_class
        return None


def parse_board(text: str) -> Board:
    """Parse ``.kicad_pcb`` content into a :class:`Board`.

    Raises :class:`oparroy.dsl.sexpr.SexpError` on malformed
    s-expressions and :class:`PcbError` when the root node is not a
    ``kicad_pcb`` document.
    """
    root = parse(text)
    if _head(root) != "kicad_pcb":
        msg = "not a .kicad_pcb document"
        raise PcbError(msg)
    net_codes = _parse_nets(root)
    copper, silkscreen = _parse_layers(root)
    return Board(
        thickness_mm=_parse_thickness(root),
        copper_layers=copper,
        silkscreen_layers=silkscreen,
        nets={name: code for code, name in net_codes.items()},
        net_classes=tuple(_parse_net_classes(root)),
        footprints=tuple(
            _parse_footprint(node) for node in _children(root, "footprint")
        ),
        segments=tuple(
            _parse_segment(node, net_codes) for node in _children(root, "segment")
        ),
        arcs=tuple(_parse_arc(node, net_codes) for node in _children(root, "arc")),
        vias=tuple(_parse_via(node, net_codes) for node in _children(root, "via")),
        texts=tuple(_parse_text(node) for node in _children(root, "gr_text")),
        edges=tuple(_parse_edges(root)),
        rects=tuple(_parse_rect(node) for node in _children(root, "gr_rect")),
        zones=tuple(_parse_zone(node) for node in _children(root, "zone")),
    )


def _head(node: Sexp) -> str | None:
    if isinstance(node, list) and node and isinstance(node[0], str):
        return node[0]
    return None


def _children(node: list[Sexp], head: str) -> Iterator[list[Sexp]]:
    for item in node[1:]:
        if isinstance(item, list) and _head(item) == head:
            yield item


def _child(node: list[Sexp], head: str) -> list[Sexp] | None:
    return next(_children(node, head), None)


def _atom(node: list[Sexp], index: int) -> str | None:
    if len(node) > index:
        item = node[index]
        if isinstance(item, str):
            return item
    return None


def _float(atom: Sexp, what: str) -> float:
    if not isinstance(atom, str):
        msg = f"expected a number for {what}"
        raise PcbError(msg)
    try:
        return float(atom)
    except ValueError:
        msg = f"expected a number for {what}, got {atom!r}"
        raise PcbError(msg) from None


def _int(atom: Sexp, what: str) -> int:
    if not isinstance(atom, str):
        msg = f"expected an integer for {what}"
        raise PcbError(msg)
    try:
        return int(atom)
    except ValueError:
        msg = f"expected an integer for {what}, got {atom!r}"
        raise PcbError(msg) from None


def _opt_float(node: list[Sexp] | None, what: str) -> float | None:
    if node is None or _atom(node, 1) is None:
        return None
    return _float(node[1], what)


def _point(node: list[Sexp] | None) -> Point:
    """Read an ``(at|xy|start|end x y [rot])`` node as a Point."""
    if node is None:
        msg = "missing coordinate node"
        raise PcbError(msg)
    return Point(_float(node[1], "x"), _float(node[2], "y"))


def _parse_nets(root: list[Sexp]) -> dict[int, str]:
    codes: dict[int, str] = {}
    for node in _children(root, "net"):
        code = _atom(node, 1)
        name = _atom(node, 2)
        if code is not None and name is not None:
            codes[_int(code, "net code")] = name
    return codes


def _parse_layers(root: list[Sexp]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    layers = _child(root, "layers")
    copper: list[str] = []
    silkscreen: list[str] = []
    for entry in layers[1:] if layers is not None else []:
        if not isinstance(entry, list):
            continue
        name, kind = _atom(entry, 1), _atom(entry, 2)
        if name is None:
            continue
        if kind in {"signal", "power", "mixed"}:
            copper.append(name)
        if "SilkS" in name:
            silkscreen.append(name)
    return tuple(copper), tuple(silkscreen)


def _parse_thickness(root: list[Sexp]) -> float | None:
    general = _child(root, "general")
    if general is None:
        return None
    return _opt_float(_child(general, "thickness"), "board thickness")


def _parse_net_classes(root: list[Sexp]) -> Iterator[NetClass]:
    setup = _child(root, "setup")
    if setup is None:
        return
    for node in _children(setup, "net_class"):
        name = _atom(node, 1)
        if name is None:
            continue
        yield NetClass(
            name=name,
            clearance_mm=_opt_float(_child(node, "clearance"), "clearance"),
            trace_width_mm=_opt_float(_child(node, "trace_width"), "trace width"),
            via_dia_mm=_opt_float(_child(node, "via_dia"), "via diameter"),
            via_drill_mm=_opt_float(_child(node, "via_drill"), "via drill"),
            nets=frozenset(
                net
                for net in (_atom(item, 1) for item in _children(node, "add_net"))
                if net is not None
            ),
        )


def _parse_footprint(node: list[Sexp]) -> Footprint:
    return Footprint(
        lib=_atom(node, 1) or "",
        ref=_footprint_ref(node),
        at=_point(_child(node, "at")),
        layer=_atom(_child(node, "layer") or [], 1) or "",
        pads=tuple(_parse_pad(pad) for pad in _children(node, "pad")),
    )


def _footprint_ref(node: list[Sexp]) -> str:
    # KiCad ≥ 8 stores the refdes as a property; ≤ 7 as fp_text.
    for prop in _children(node, "property"):
        if _atom(prop, 1) == "Reference":
            return _atom(prop, 2) or ""
    for text in _children(node, "fp_text"):
        if _atom(text, 1) == "reference":
            return _atom(text, 2) or ""
    return ""


def _parse_pad(node: list[Sexp]) -> Pad:
    net_node = _child(node, "net")
    return Pad(
        number=_atom(node, 1) or "",
        kind=_atom(node, 2) or "",
        at=_point(_child(node, "at")),
        net=_pad_net(net_node),
        size=_size_point(_child(node, "size")),
        drill=_drill_point(_child(node, "drill")),
    )


def _size_point(node: list[Sexp] | None) -> Point | None:
    """Read a ``(size x y)`` node; ``None`` when absent."""
    if node is None:
        return None
    return Point(_float(node[1], "pad size"), _float(node[2], "pad size"))


def _drill_point(node: list[Sexp] | None) -> Point | None:
    """Read a ``(drill [oval] x [y])`` node; a round drill repeats x."""
    if node is None:
        return None
    atoms = [item for item in node[1:] if isinstance(item, str) and item != "oval"]
    if not atoms:
        return None
    x = _float(atoms[0], "pad drill")
    return Point(x, _float(atoms[1], "pad drill") if len(atoms) > 1 else x)


def _pad_net(net_node: list[Sexp] | None) -> str | None:
    if net_node is None:
        return None
    # Old form: (net <code> "<name>"); KiCad 10 (20260206): (net "<name>").
    name = _atom(net_node, 2)
    return name if name is not None else _atom(net_node, 1)


def _net_name(node: list[Sexp], net_codes: Mapping[int, str], *, numbered: bool) -> str:
    net_node = _child(node, "net")
    if net_node is None:
        return ""
    code = _atom(net_node, 1)
    if code is None:
        return ""
    if not numbered:
        return code
    if net_codes:
        return net_codes.get(_int(code, "net code"), "")
    # KiCad 10's native format (20260206) drops the net-code table and
    # writes net names inline — verified against 10.0.6.
    return code


def _parse_segment(node: list[Sexp], net_codes: Mapping[int, str]) -> Segment:
    return Segment(
        start=_point(_child(node, "start")),
        end=_point(_child(node, "end")),
        width=_opt_float(_child(node, "width"), "segment width") or 0.0,
        layer=_atom(_child(node, "layer") or [], 1) or "",
        net=_net_name(node, net_codes, numbered=True),
    )


def _parse_arc(node: list[Sexp], net_codes: Mapping[int, str]) -> ArcSegment:
    return ArcSegment(
        start=_point(_child(node, "start")),
        mid=_point(_child(node, "mid")),
        end=_point(_child(node, "end")),
        width=_opt_float(_child(node, "width"), "arc width") or 0.0,
        layer=_atom(_child(node, "layer") or [], 1) or "",
        net=_net_name(node, net_codes, numbered=True),
    )


def _parse_via(node: list[Sexp], net_codes: Mapping[int, str]) -> Via:
    layers = _child(node, "layers")
    return Via(
        at=_point(_child(node, "at")),
        size=_opt_float(_child(node, "size"), "via size") or 0.0,
        drill=_opt_float(_child(node, "drill"), "via drill") or 0.0,
        layers=tuple(name for name in layers[1:] if isinstance(name, str))
        if layers is not None
        else (),
        net=_net_name(node, net_codes, numbered=True),
    )


def _parse_text(node: list[Sexp]) -> Text:
    return Text(
        text=_atom(node, 1) or "",
        layer=_atom(_child(node, "layer") or [], 1) or "",
        at=_point(_child(node, "at")),
    )


def _parse_edges(root: list[Sexp]) -> Iterator[Edge]:
    for node in _children(root, "gr_line"):
        yield Edge(
            kind=EdgeKind.LINE,
            start=_point(_child(node, "start")),
            end=_point(_child(node, "end")),
            layer=_atom(_child(node, "layer") or [], 1) or "",
        )
    for node in _children(root, "gr_arc"):
        yield Edge(
            kind=EdgeKind.ARC,
            start=_point(_child(node, "start")),
            end=_point(_child(node, "end")),
            layer=_atom(_child(node, "layer") or [], 1) or "",
            mid=_point(_child(node, "mid")),
        )


def _parse_rect(node: list[Sexp]) -> Rect:
    fill = _child(node, "fill")
    return Rect(
        start=_point(_child(node, "start")),
        end=_point(_child(node, "end")),
        layer=_atom(_child(node, "layer") or [], 1) or "",
        filled=fill is not None and _atom(fill, 1) == "yes",
    )


def _parse_zone(node: list[Sexp]) -> Zone:
    polygon = _child(node, "polygon")
    pts = _child(polygon, "pts") if polygon is not None else None
    layers = _child(node, "layers")
    return Zone(
        net=_atom(_child(node, "net_name") or [], 1),
        layers=tuple(name for name in layers[1:] if isinstance(name, str))
        if layers is not None
        else (),
        keepout=_child(node, "keepout") is not None,
        polygon=tuple(_point(xy) for xy in _children(pts, "xy"))
        if pts is not None
        else (),
    )
