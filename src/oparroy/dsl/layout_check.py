"""Layout property assertions over a parsed board (DESIGN.md §7).

KiCad's own DRC stays authoritative for manufacturability; these checks
cover project semantics DRC can't know about: bypass-path copper
independence (§4), placement contracts (§4.1), mechanical contracts
(corner radius, mounting holes with keepouts), the stackup contract
(§6/§9), and the §7 board-level checklist (silkscreen ID fields,
serial-number box, power LED, terminal protection: TVS adjacent to its
connector, series R between TVS and µC pin). One :class:`LayoutRules`
value is the contract; :func:`check_layout` reports every violation as a
batch of :class:`oparroy.dsl.check.Issue`, like the schematic validation
pass. The terminal-protection rules derive from the capture —
:func:`terminal_protection_rules` — because board refdes move under
KiCad's geographic annotation while capture paths stay stable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from oparroy.dsl.check import Issue, Severity
from oparroy.dsl.ir import natural_key
from oparroy.dsl.kicad_pcb import Board, Edge, EdgeKind, Footprint, Point

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from oparroy.dsl.annotate import Annotation
    from oparroy.dsl.ir import Circuit, Net, Part
    from oparroy.dsl.kicad_pcb import ArcSegment, NetClass, Segment, Via
    from oparroy.dsl.kicad_pro import Project

_EPSILON_MM = 1e-6
_COLLINEAR_COSINE = -0.999
_JUNCTION_LINE_COUNT = 2
_MIN_POLYGON_POINTS = 3
_ARC_SAGITTA_MM = 0.01
_ORIGIN = Point(0.0, 0.0)


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
    """Copper independence for a bypass net (§4): parts and copper.

    Two halves of one §4 contract — "no firmware in the bypass path".
    Every pad carrying ``net`` must belong to a footprint whose refdes
    full-matches one of ``allowed_refs``, and no copper primitive on
    ``net`` (segment, arc, via) may geometrically touch another net's
    copper on a shared layer.
    """

    net: str
    allowed_refs: tuple[str, ...]


@dataclass(frozen=True)
class TerminalProtectionRule:
    """One external terminal's protection chain (§7 checklist).

    The chain is connector → TVS → series R → protected logic: the TVS
    clamps at the board edge, and the R straddles the exposed net so it
    limits what the µC's internal clamp diodes absorb. ``net`` names the
    exposed terminal net; ``connector``, ``tvs``, and ``series_r`` are
    refdes regexes full-matched against the footprint refdes (the
    :class:`AdjacencyRule` idiom).
    """

    name: str
    net: str
    connector: str
    tvs: str
    series_r: str
    max_tvs_connector_mm: float
    max_r_protected_mm: float


@dataclass(frozen=True)
class FootprintSetRule:
    """The footprints on one copper layer, as an exact refdes set (§7).

    ``refs`` names every footprint allowed on ``layer`` — the segment
    connectors on B.Cu, for the single-sided-SMT contract. Violations
    cut both ways: a footprint on the layer outside the set, and a set
    member missing from the layer.
    """

    name: str
    layer: str
    refs: tuple[str, ...]


@dataclass(frozen=True)
class PartOverHoleRule:
    r"""Every matching footprint sits over its routed hole (§4.1).

    Reverse-mount LEDs emit through the board: the footprint must carry
    an unconnected ``np_thru_hole`` pad whose footprint-local ``at``
    stays within ``tolerance_mm`` of the anchor. The offset is local,
    so the check needs no footprint rotation (which is not modeled).
    ``refdes`` full-matches, the :class:`AdjacencyRule` idiom.
    """

    name: str
    refdes: str
    tolerance_mm: float


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
    terminal_protection: tuple[TerminalProtectionRule, ...] = ()
    footprint_sets: tuple[FootprintSetRule, ...] = ()
    part_over_hole: tuple[PartOverHoleRule, ...] = ()


def check_layout(
    board: Board, rules: LayoutRules, project: Project | None = None
) -> list[Issue]:
    """Assert the layout contract; returns the issue list (errors only).

    When ``project`` (the parsed ``.kicad_pro``) is given, net-class
    width/via compliance reads its classes — the same numbers KiCad's
    DRC enforces; the board file's own ``net_class`` entries remain
    the fallback for pre-KiCad-10 files.
    """
    issues: list[Issue] = []
    issues.extend(_check_stackup(board, rules))
    issues.extend(_check_net_class_compliance(board, project))
    issues.extend(_check_trace_budgets(board, rules))
    issues.extend(_check_corner_radius(board, rules))
    issues.extend(_check_silkscreen(board, rules))
    issues.extend(_check_serial_box(board, rules))
    issues.extend(_check_mounting_holes(board, rules))
    issues.extend(_check_adjacency(board, rules))
    issues.extend(_check_terminal_protection(board, rules))
    issues.extend(_check_footprint_set(board, rules))
    issues.extend(_check_part_over_hole(board, rules))
    issues.extend(_check_required_footprints(board, rules))
    issues.extend(_check_bypass(board, rules))
    issues.extend(_check_bypass_copper(board, rules))
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


def _check_net_class_compliance(board: Board, project: Project | None) -> list[Issue]:

    def net_class_of(net: str) -> NetClass | None:
        if project is not None:
            return project.net_class_of(net)
        return board.net_class_of(net)

    issues: list[Issue] = []
    for segment in board.segments:
        net_class = net_class_of(segment.net)
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
        net_class = net_class_of(via.net)
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
    for arc in board.arcs:
        net_class = net_class_of(arc.net)
        if (
            net_class is not None
            and net_class.trace_width_mm is not None
            and arc.width + _EPSILON_MM < net_class.trace_width_mm
        ):
            issues.extend(
                _error(
                    f"arc on net {arc.net!r} is {arc.width} mm wide, net class "
                    f"{net_class.name!r} requires {net_class.trace_width_mm} mm"
                )
            )
    return issues


def _check_trace_budgets(board: Board, rules: LayoutRules) -> list[Issue]:
    lengths: dict[str, float] = {}
    for segment in board.segments:
        lengths[segment.net] = lengths.get(segment.net, 0.0) + segment.length
    for arc in board.arcs:
        lengths[arc.net] = lengths.get(arc.net, 0.0) + arc.length
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


def _check_terminal_protection(board: Board, rules: LayoutRules) -> list[Issue]:
    issues: list[Issue] = []
    for rule in rules.terminal_protection:
        issues.extend(_check_terminal_chain(board, rule))
    return issues


def _on_net(footprint: Footprint, net: str) -> bool:
    return any(pad.net == net for pad in footprint.pads)


def _check_terminal_chain(board: Board, rule: TerminalProtectionRule) -> list[Issue]:
    issues: list[Issue] = []
    tvs = _ref_matches(board, rule.tvs)
    if not tvs:
        issues.extend(
            _error(f"{rule.name}: no footprint matches the TVS pattern '{rule.tvs}'")
        )
    clamping = [fp for fp in tvs if _on_net(fp, rule.net)]
    for fp in tvs:
        if not _on_net(fp, rule.net):
            issues.extend(
                _error(
                    f"{rule.name}: TVS {fp.ref} carries no pad on net "
                    f"{rule.net!r} — it must clamp the exposed terminal"
                )
            )
    connectors = [
        fp for fp in _ref_matches(board, rule.connector) if _on_net(fp, rule.net)
    ]
    if not connectors:
        issues.extend(
            _error(
                f"{rule.name}: no connector matching '{rule.connector}' carries "
                f"a pad on net {rule.net!r} — the exposed terminal must enter "
                "through its connector"
            )
        )
    for fp in clamping:
        if connectors and not any(
            fp.at.distance(conn.at) <= rule.max_tvs_connector_mm for conn in connectors
        ):
            issues.extend(
                _error(
                    f"{rule.name}: TVS {fp.ref} is not within "
                    f"{rule.max_tvs_connector_mm} mm of its connector — "
                    "the TVS clamps at the board edge (§7 checklist)"
                )
            )
    issues.extend(_check_series_r(board, rule))
    offenders = sorted(
        {
            fp.ref
            for fp in board.footprints
            if _on_net(fp, rule.net)
            and not any(
                re.fullmatch(pattern, fp.ref)
                for pattern in (rule.connector, rule.tvs, rule.series_r)
            )
        },
        key=natural_key,
    )
    if offenders:
        issues.extend(
            _error(
                f"{rule.name}: exposed net {rule.net!r} touches "
                f"{', '.join(offenders)}; only its connector, TVS, and series R "
                "may carry it — the R sits between TVS and µC pin (§7 checklist)"
            )
        )
    return issues


def _check_series_r(board: Board, rule: TerminalProtectionRule) -> list[Issue]:
    """Assert the series R straddles the exposed net and sits by the µC side."""
    issues: list[Issue] = []
    resistors = _ref_matches(board, rule.series_r)
    if not resistors:
        return _error(
            f"{rule.name}: no footprint matches the series-R pattern '{rule.series_r}'"
        )
    for fp in resistors:
        exposed = [pad for pad in fp.pads if pad.net == rule.net]
        if not exposed:
            issues.extend(
                _error(
                    f"{rule.name}: series R {fp.ref} carries no pad on net "
                    f"{rule.net!r} — it must straddle the exposed net "
                    "(§7 checklist)"
                )
            )
            continue
        if len(exposed) > 1:
            issues.extend(
                _error(
                    f"{rule.name}: both pads of series R {fp.ref} sit on net "
                    f"{rule.net!r} — it must straddle the exposed net"
                )
            )
            continue
        protected = next(
            (pad.net for pad in fp.pads if pad.net not in (None, rule.net)), None
        )
        if protected is None:
            continue
        near = any(
            other is not fp
            and _on_net(other, protected)
            and fp.at.distance(other.at) <= rule.max_r_protected_mm
            for other in board.footprints
        )
        if not near:
            issues.extend(
                _error(
                    f"{rule.name}: series R {fp.ref} is not within "
                    f"{rule.max_r_protected_mm} mm of any other footprint on "
                    f"the protected net {protected!r} — the R belongs near "
                    "the µC pin it protects (§7 checklist)"
                )
            )
    return issues


def _check_footprint_set(board: Board, rules: LayoutRules) -> list[Issue]:
    issues: list[Issue] = []
    for rule in rules.footprint_sets:
        present = sorted(
            (fp.ref for fp in board.footprints if fp.layer == rule.layer),
            key=natural_key,
        )
        unexpected = [ref for ref in present if ref not in rule.refs]
        if unexpected:
            expected = ", ".join(sorted(rule.refs, key=natural_key))
            issues.extend(
                _error(
                    f"{rule.name}: {', '.join(unexpected)} on {rule.layer} "
                    f"outside the expected footprint set ({expected}) — "
                    "the back carries only the segment connectors "
                    "(§7 checklist)"
                )
            )
        missing = sorted(
            (ref for ref in rule.refs if ref not in present), key=natural_key
        )
        if missing:
            issues.extend(
                _error(
                    f"{rule.name}: {', '.join(missing)} missing from "
                    f"{rule.layer} — the footprint set is exact "
                    "(§7 checklist)"
                )
            )
    return issues


def _check_part_over_hole(board: Board, rules: LayoutRules) -> list[Issue]:
    issues: list[Issue] = []
    for rule in rules.part_over_hole:
        for fp in _ref_matches(board, rule.refdes):
            over_hole = any(
                pad.kind == "np_thru_hole"
                and pad.net is None
                and pad.at.distance(_ORIGIN) <= rule.tolerance_mm
                for pad in fp.pads
            )
            if not over_hole:
                issues.extend(
                    _error(
                        f"{rule.name}: {fp.ref} has no unconnected "
                        f"np_thru_hole pad within {rule.tolerance_mm} mm of "
                        "its anchor — the reverse-mount LED shines through "
                        "its routed hole (§4.1)"
                    )
                )
    return issues


def terminal_protection_rules(
    circuit: Circuit,
    annotation: Annotation,
    *,
    max_tvs_connector_mm: float = 6.0,
    max_r_protected_mm: float = 15.0,
) -> tuple[TerminalProtectionRule, ...]:
    """Derive the §7 terminal-protection placement contract from a capture.

    Board refdes move under KiCad's geographic annotation, so the
    contract names parts by capture identity: every ``Device:D_TVS``
    part anchors one rule — the exposed-terminal net it clamps, the
    ``Device:R`` straddling that net, and the connector the terminal
    enters through. ``annotation`` (capture path → placed refdes, e.g.
    from :func:`oparroy.dsl.annotate.annotation_from_pcb`) supplies the
    refdes patterns; a chain part missing from it was never placed, a
    ``ValueError`` either way the capture doesn't fit the chain shape.
    """
    if circuit.instances:
        circuit = circuit.flatten()
    refs = annotation.refs
    rules = []
    for path in sorted(circuit.parts, key=natural_key):
        part = circuit.parts[path]
        if part.symbol.ref != "Device:D_TVS":
            continue
        pin_nets = {pin.net for pin in part.pins if pin.net is not None}
        qualified = [
            (net, chain)
            for net in sorted(pin_nets, key=lambda n: natural_key(n.name))
            if (chain := _terminal_chain_parts(net)) is not None
        ]
        if len(qualified) != 1:
            msg = (
                f"{path}: a terminal-protection TVS must clamp exactly one "
                "exposed terminal net — a pin net carrying a connector pin "
                f"and exactly one Device:R pin; {len(qualified)} qualify"
            )
            raise ValueError(msg)
        net, (resistors, connectors) = qualified[0]
        rules.append(
            TerminalProtectionRule(
                name=f"terminal protection {net.name} (§7 checklist)",
                net=net.name,
                connector=_placed_pattern(connectors, refs),
                tvs=_placed_pattern([part], refs),
                series_r=_placed_pattern(resistors, refs),
                max_tvs_connector_mm=max_tvs_connector_mm,
                max_r_protected_mm=max_r_protected_mm,
            )
        )
    return tuple(sorted(rules, key=lambda rule: natural_key(rule.net)))


def _terminal_chain_parts(net: Net) -> tuple[list[Part], list[Part]] | None:
    """Return the (series-R, connector) pair marking an exposed-terminal net.

    A terminal net carries pins of exactly one ``Device:R`` — the
    series resistor straddling it — and of a connector. Requiring a
    single R keeps the rail on the TVS's other pin from qualifying:
    ground carries many resistors.
    """
    resistors: list[Part] = []
    connectors: list[Part] = []
    for pin in net.pins:
        part = pin.part
        if part.symbol.ref == "Device:R" and part not in resistors:
            resistors.append(part)
        if part.symbol.lib.startswith("Connector") and part not in connectors:
            connectors.append(part)
    if len(resistors) != 1 or not connectors:
        return None
    return resistors, connectors


def _placed_pattern(parts: Iterable[Part], refs: Mapping[str, str]) -> str:
    """Build the refdes full-match pattern for chain parts, via the annotation."""
    patterns = []
    for part in sorted(parts, key=lambda p: natural_key(p.ref)):
        refdes = refs.get(part.ref)
        if refdes is None:
            msg = f"{part.ref} has no refdes in the annotation — not placed"
            raise ValueError(msg)
        patterns.append(re.escape(refdes))
    return "|".join(patterns)


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


@dataclass(frozen=True)
class _Copper:
    """One copper primitive as a capsule on one layer (``a == b``: a via)."""

    a: Point
    b: Point
    radius: float
    layer: str
    net: str
    kind: str
    source: Segment | ArcSegment | Via


def _check_bypass_copper(board: Board, rules: LayoutRules) -> list[Issue]:
    """No bypass copper touches another net's copper (§4).

    Tracks are capsules (centerline ± width/2), vias circles (size/2)
    on each of their layers; arcs are polygonized into chords at a
    fixed sagitta. Same-net contact is ordinary connectivity — only
    different-net overlap or exact touch on a shared layer flags.
    Zones and pads stay out of scope: a zone's parsed polygon is its
    outline, not the poured copper with clearance cutouts (checking it
    would flag every poured board), and pads lack board-absolute
    positions because footprint rotation is not modeled.
    """
    if not rules.bypass:
        return []
    copper = _board_copper(board)
    issues: list[Issue] = []
    for rule in rules.bypass:
        own = [piece for piece in copper if piece.net == rule.net]
        others = [piece for piece in copper if piece.net != rule.net]
        flagged: set[tuple[int, int]] = set()
        for mine in own:
            for other in others:
                if mine.layer != other.layer:
                    continue
                pair = (id(mine.source), id(other.source))
                if pair in flagged:
                    continue
                gap, at = _capsule_contact(mine, other)
                if gap <= _EPSILON_MM:
                    flagged.add(pair)
                    article = "an" if other.kind == "arc" else "a"
                    issues.extend(
                        _error(
                            f"bypass net {rule.net!r} shares copper with "
                            f"{article} {other.kind} on net {other.net!r} at "
                            f"({at.x:.2f}, {at.y:.2f}) on {mine.layer} — "
                            "no node logic in the bypass path (§4)"
                        )
                    )
    return issues


def _board_copper(board: Board) -> list[_Copper]:
    return (
        [
            _Copper(
                segment.start,
                segment.end,
                segment.width / 2,
                segment.layer,
                segment.net,
                "segment",
                segment,
            )
            for segment in board.segments
        ]
        + [
            _Copper(a, b, arc.width / 2, arc.layer, arc.net, "arc", arc)
            for arc in board.arcs
            for a, b in arc.chords(_ARC_SAGITTA_MM)
        ]
        + [
            _Copper(via.at, via.at, via.size / 2, layer, via.net, "via", via)
            for via in board.vias
            for layer in via.layers
        ]
    )


def _capsule_contact(first: _Copper, second: _Copper) -> tuple[float, Point]:
    """Centerline gap (radii subtracted) and the closest pair's midpoint."""
    hit = (
        None
        if first.a == first.b or second.a == second.b
        else _segment_intersection_point(first.a, first.b, second.a, second.b)
    )
    if hit is not None:
        near_first = near_second = hit
    else:
        candidates = [
            (end, _closest_on_segment(end, second.a, second.b))
            for end in (first.a, first.b)
        ] + [
            (_closest_on_segment(end, first.a, first.b), end)
            for end in (second.a, second.b)
        ]
        near_first, near_second = min(
            candidates, key=lambda pair: pair[0].distance(pair[1])
        )
    at = Point((near_first.x + near_second.x) / 2, (near_first.y + near_second.y) / 2)
    return near_first.distance(near_second) - first.radius - second.radius, at


def _closest_on_segment(p: Point, a: Point, b: Point) -> Point:
    """Return the closest point to ``p`` on segment a-b (``a == b``: a point)."""
    dx, dy = b.x - a.x, b.y - a.y
    length2 = dx * dx + dy * dy
    if length2 < _EPSILON_MM:
        return a
    t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / length2
    t = max(0.0, min(1.0, t))
    return Point(a.x + t * dx, a.y + t * dy)


def _segment_intersection_point(
    p1: Point, p2: Point, p3: Point, p4: Point
) -> Point | None:
    """Return the crossing point of two segments; None when they don't cross."""
    d = (p2.x - p1.x) * (p4.y - p3.y) - (p2.y - p1.y) * (p4.x - p3.x)
    if abs(d) < _EPSILON_MM:
        return None
    t = ((p3.x - p1.x) * (p4.y - p3.y) - (p3.y - p1.y) * (p4.x - p3.x)) / d
    u = ((p3.x - p1.x) * (p2.y - p1.y) - (p3.y - p1.y) * (p2.x - p1.x)) / d
    if -_EPSILON_MM <= t <= 1 + _EPSILON_MM and -_EPSILON_MM <= u <= 1 + _EPSILON_MM:
        return Point(p1.x + t * (p2.x - p1.x), p1.y + t * (p2.y - p1.y))
    return None


def _ref_matches(board: Board, pattern: str) -> list[Footprint]:
    return [fp for fp in board.footprints if re.fullmatch(pattern, fp.ref)]
