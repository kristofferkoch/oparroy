"""Layout property assertions over a parsed board (DESIGN.md §7).

KiCad's own DRC stays authoritative for manufacturability; these checks
cover project semantics DRC can't know about: bypass-path copper
independence (§4), placement contracts (§4.1), mechanical contracts
(corner radius, mounting holes with keepouts), the stackup contract
(§6/§9), and the §7 board-level checklist (silkscreen ID fields,
serial-number box, power LED). One :class:`LayoutRules` value is the
contract; :func:`check_layout` reports every violation as a batch of
:class:`oparroy.dsl.check.Issue`, like the schematic validation pass.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from oparroy.dsl.check import Issue, Severity
from oparroy.dsl.ir import natural_key
from oparroy.dsl.kicad_pcb import Board, Edge, EdgeKind, Footprint, Point

if TYPE_CHECKING:
    from collections.abc import Mapping

_EPSILON_MM = 1e-6
_COLLINEAR_COSINE = -0.999
_JUNCTION_LINE_COUNT = 2
_MIN_POLYGON_POINTS = 3


@dataclass(frozen=True)
class AdjacencyRule:
    r"""Every ``source`` footprint within ``max_distance_mm`` of a ``target``.

    Patterns are Python regexes full-matched against the footprint
    refdes (``r"J\d+"`` covers every connector).
    """

    name: str
    source: str
    target: str
    max_distance_mm: float


@dataclass(frozen=True)
class BypassRule:
    """Copper independence for a bypass net (§4): only whitelisted parts.

    Every pad carrying ``net`` must belong to a footprint whose refdes
    full-matches one of ``allowed_refs`` — the physical embodiment of
    "no firmware in the bypass path".
    """

    net: str
    allowed_refs: tuple[str, ...]


@dataclass(frozen=True)
class LayoutRules:
    """The layout contract; ``None``/empty fields disable their check."""

    copper_layers: int | None = None
    thickness_mm: float | None = None
    thickness_tolerance_mm: float = 0.1
    required_silkscreen: tuple[str, ...] = ()
    min_serial_box_mm2: float | None = None
    min_corner_radius_mm: float | None = None
    corner_tolerance_mm: float = 0.05
    trace_budgets_mm: Mapping[str, float] = field(default_factory=dict)
    min_mounting_holes: int = 0
    mounting_hole_keepout: bool = False
    adjacency: tuple[AdjacencyRule, ...] = ()
    required_footprints: tuple[str, ...] = ()
    bypass: tuple[BypassRule, ...] = ()


def check_layout(board: Board, rules: LayoutRules) -> list[Issue]:
    """Assert the layout contract; returns the issue list (errors only)."""
    issues: list[Issue] = []
    issues.extend(_check_stackup(board, rules))
    issues.extend(_check_net_class_compliance(board))
    issues.extend(_check_trace_budgets(board, rules))
    issues.extend(_check_corner_radius(board, rules))
    issues.extend(_check_silkscreen(board, rules))
    issues.extend(_check_serial_box(board, rules))
    issues.extend(_check_mounting_holes(board, rules))
    issues.extend(_check_adjacency(board, rules))
    issues.extend(_check_required_footprints(board, rules))
    issues.extend(_check_bypass(board, rules))
    return issues


def _error(message: str) -> list[Issue]:
    return [Issue(Severity.ERROR, message)]


def _check_stackup(board: Board, rules: LayoutRules) -> list[Issue]:
    issues: list[Issue] = []
    if rules.copper_layers is not None and len(board.copper_layers) != (
        rules.copper_layers
    ):
        layers = ", ".join(board.copper_layers)
        issues.extend(
            _error(
                f"stackup has {len(board.copper_layers)} copper layers ({layers}), "
                f"the contract wants {rules.copper_layers}"
            )
        )
    if rules.thickness_mm is not None:
        if board.thickness_mm is None:
            issues.extend(_error("board declares no thickness (general/thickness)"))
        elif (
            abs(board.thickness_mm - rules.thickness_mm) > rules.thickness_tolerance_mm
        ):
            issues.extend(
                _error(
                    f"board thickness {board.thickness_mm} mm is outside "
                    f"{rules.thickness_mm} ± {rules.thickness_tolerance_mm} mm"
                )
            )
    return issues


def _check_net_class_compliance(board: Board) -> list[Issue]:
    issues: list[Issue] = []
    for segment in board.segments:
        net_class = board.net_class_of(segment.net)
        if (
            net_class is not None
            and net_class.trace_width_mm is not None
            and segment.width + _EPSILON_MM < net_class.trace_width_mm
        ):
            issues.extend(
                _error(
                    f"segment on net {segment.net!r} is {segment.width} mm wide, "
                    f"net class {net_class.name!r} requires "
                    f"{net_class.trace_width_mm} mm"
                )
            )
    for via in board.vias:
        net_class = board.net_class_of(via.net)
        if (
            net_class is not None
            and net_class.via_dia_mm is not None
            and via.size + _EPSILON_MM < net_class.via_dia_mm
        ):
            issues.extend(
                _error(
                    f"via on net {via.net!r} is {via.size} mm, net class "
                    f"{net_class.name!r} requires {net_class.via_dia_mm} mm"
                )
            )
    return issues


def _check_trace_budgets(board: Board, rules: LayoutRules) -> list[Issue]:
    lengths: dict[str, float] = {}
    for segment in board.segments:
        lengths[segment.net] = lengths.get(segment.net, 0.0) + segment.length
    issues: list[Issue] = []
    for net in sorted(rules.trace_budgets_mm, key=natural_key):
        budget = rules.trace_budgets_mm[net]
        total = lengths.get(net, 0.0)
        if total > budget + _EPSILON_MM:
            issues.extend(
                _error(
                    f"net {net!r} routes {total:.2f} mm of copper, "
                    f"over the {budget} mm budget"
                )
            )
    return issues


def _check_corner_radius(board: Board, rules: LayoutRules) -> list[Issue]:
    if rules.min_corner_radius_mm is None:
        return []
    edges = [edge for edge in board.edges if edge.layer == "Edge.Cuts"]
    issues: list[Issue] = []
    checked_arcs: set[int] = set()
    for junction, incident in _junctions(edges, rules.corner_tolerance_mm):
        arcs = [edge for edge in incident if edge.kind is EdgeKind.ARC]
        fresh = [arc for arc in arcs if id(arc) not in checked_arcs]
        checked_arcs.update(id(arc) for arc in fresh)
        if arcs:
            issues.extend(_check_arc_radii(fresh, junction, rules.min_corner_radius_mm))
        elif not _is_straight(junction, incident):
            issues.extend(
                _error(
                    f"board outline corner at ({junction.x:.2f}, {junction.y:.2f}) "
                    f"is sharp — corners must be rounded to at least "
                    f"{rules.min_corner_radius_mm} mm radius"
                )
            )
    return issues


def _junctions(
    edges: list[Edge], tolerance_mm: float
) -> list[tuple[Point, list[Edge]]]:
    """Cluster coincident edge endpoints; multi-edge clusters are junctions."""
    clusters: list[list[tuple[Point, Edge]]] = []
    for edge in edges:
        for point in (edge.start, edge.end):
            for cluster in clusters:
                if point.distance(cluster[0][0]) <= tolerance_mm:
                    cluster.append((point, edge))
                    break
            else:
                clusters.append([(point, edge)])
    junctions = []
    for cluster in clusters:
        incident = list({id(edge): edge for _, edge in cluster}.values())
        if len(incident) > 1:
            junctions.append((cluster[0][0], incident))
    return junctions


def _is_straight(junction: Point, incident: list[Edge]) -> bool:
    """Two lines meeting at 180° are a straight run, not a corner."""
    if len(incident) != _JUNCTION_LINE_COUNT:
        return False
    if any(edge.kind is not EdgeKind.LINE for edge in incident):
        return False
    vectors = []
    for edge in incident:
        other = _other_end(edge, junction)
        vectors.append((other.x - junction.x, other.y - junction.y))
    (ux, uy), (vx, vy) = vectors
    cosine = (ux * vx + uy * vy) / ((ux**2 + uy**2) ** 0.5 * (vx**2 + vy**2) ** 0.5)
    return cosine < _COLLINEAR_COSINE


def _other_end(edge: Edge, junction: Point) -> Point:
    if edge.start.distance(junction) < edge.end.distance(junction):
        return edge.end
    return edge.start


def _check_arc_radii(
    arcs: list[Edge], junction: Point, min_radius_mm: float
) -> list[Issue]:
    issues: list[Issue] = []
    for arc in arcs:
        radius = _circumradius(arc)
        if radius + _EPSILON_MM < min_radius_mm:
            issues.extend(
                _error(
                    f"outline arc at ({junction.x:.2f}, {junction.y:.2f}) has "
                    f"radius {radius:.2f} mm, below the {min_radius_mm} mm "
                    "corner minimum"
                )
            )
    return issues


def _circumradius(arc: Edge) -> float:
    """Radius of the circle through an arc's three points; 0 if degenerate."""
    if arc.mid is None:
        return 0.0
    a, m, b = arc.start, arc.mid, arc.end
    double_area = abs((m.x - a.x) * (b.y - a.y) - (b.x - a.x) * (m.y - a.y))
    if double_area < _EPSILON_MM:
        return 0.0
    return a.distance(b) * b.distance(m) * m.distance(a) / (2 * double_area)


def _check_silkscreen(board: Board, rules: LayoutRules) -> list[Issue]:
    texts = [text.text for text in board.texts if text.layer in board.silkscreen_layers]
    issues: list[Issue] = []
    for pattern in rules.required_silkscreen:
        if not any(re.search(pattern, text) for text in texts):
            issues.extend(
                _error(
                    f"no silkscreen text matches {pattern!r} — the §7 "
                    "board-ID fields are mandatory"
                )
            )
    return issues


def _check_serial_box(board: Board, rules: LayoutRules) -> list[Issue]:
    if rules.min_serial_box_mm2 is None:
        return []
    boxes = [rect for rect in board.rects if rect.layer in board.silkscreen_layers]
    if any(box.area >= rules.min_serial_box_mm2 for box in boxes):
        return []
    return _error(
        f"no silkscreen rectangle of at least {rules.min_serial_box_mm2} mm² "
        "for the handwritten serial-number field (§7 checklist)"
    )


def _check_mounting_holes(board: Board, rules: LayoutRules) -> list[Issue]:
    holes = [fp for fp in board.footprints if _is_mounting_hole(fp)]
    issues: list[Issue] = []
    if len(holes) < rules.min_mounting_holes:
        issues.extend(
            _error(
                f"board has {len(holes)} mounting holes, "
                f"the contract wants at least {rules.min_mounting_holes}"
            )
        )
    if rules.mounting_hole_keepout:
        keepouts = [zone for zone in board.zones if zone.keepout]
        for hole in holes:
            if not any(_point_in_polygon(hole.at, zone.polygon) for zone in keepouts):
                issues.extend(
                    _error(
                        f"mounting hole {hole.ref} has no keepout zone "
                        "around it (standoff clearance)"
                    )
                )
    return issues


def _is_mounting_hole(footprint: Footprint) -> bool:
    return "MountingHole" in footprint.lib or any(
        pad.kind == "np_thru_hole" for pad in footprint.pads
    )


def _point_in_polygon(point: Point, polygon: tuple[Point, ...]) -> bool:
    """Ray-casting containment; a polygon under 3 points contains nothing."""
    if len(polygon) < _MIN_POLYGON_POINTS:
        return False
    inside = False
    for index, a in enumerate(polygon):
        b = polygon[(index + 1) % len(polygon)]
        if (a.y > point.y) != (b.y > point.y):
            cross_x = a.x + (point.y - a.y) * (b.x - a.x) / (b.y - a.y)
            if point.x < cross_x:
                inside = not inside
    return inside


def _check_adjacency(board: Board, rules: LayoutRules) -> list[Issue]:
    issues: list[Issue] = []
    for rule in rules.adjacency:
        sources = _ref_matches(board, rule.source)
        targets = _ref_matches(board, rule.target)
        for source in sources:
            near = any(
                target is not source
                and source.at.distance(target.at) <= rule.max_distance_mm
                for target in targets
            )
            if not near:
                issues.extend(
                    _error(
                        f"{rule.name}: {source.ref} is not within "
                        f"{rule.max_distance_mm} mm of a footprint matching "
                        f"'{rule.target}'"
                    )
                )
    return issues


def _check_required_footprints(board: Board, rules: LayoutRules) -> list[Issue]:
    issues: list[Issue] = []
    for pattern in rules.required_footprints:
        if not _ref_matches(board, pattern):
            issues.extend(
                _error(
                    f"no footprint reference matches {pattern!r} "
                    "(§7 board-level checklist)"
                )
            )
    return issues


def _check_bypass(board: Board, rules: LayoutRules) -> list[Issue]:
    issues: list[Issue] = []
    for rule in rules.bypass:
        offenders = sorted(
            {
                footprint.ref
                for footprint in board.footprints
                if any(pad.net == rule.net for pad in footprint.pads)
                and not any(
                    re.fullmatch(pattern, footprint.ref)
                    for pattern in rule.allowed_refs
                )
            },
            key=natural_key,
        )
        if offenders:
            allowed = ", ".join(rule.allowed_refs)
            issues.extend(
                _error(
                    f"bypass net {rule.net!r} touches {', '.join(offenders)}; "
                    f"only footprints matching {allowed} may carry it — "
                    "no node logic in the bypass path (§4)"
                )
            )
    return issues


def _ref_matches(board: Board, pattern: str) -> list[Footprint]:
    return [fp for fp in board.footprints if re.fullmatch(pattern, fp.ref)]
