"""Validation pass over a finished circuit IR (capture → check → emit).

Structural invariants raise during capture (see ir.py); everything here
is a *semantic* check over the finished IR, reported as a batch of
issues rather than a first-failure exception. Beyond what the emitters
and pcbnew need to be true, this pass carries the first electrical
rules: interval containment over port limit ranges (a sink's acceptable
range must cover the connected source's output range) and the
power-domain crossing audit (every net touching two domains, one
switched, must carry a declared disposition — ``Circuit.crossing``),
with waivers as explicit, path-addressed capture data.
"""

import fnmatch
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from oparroy.dsl.ir import (
    AlwaysPowered,
    Circuit,
    Crossing,
    DiesWith,
    Limits,
    Net,
    Part,
    PinType,
    PowerDomain,
    PowerDomainKind,
    Waiver,
    hierarchical_crossings,
    hierarchical_waivers,
    natural_key,
)
from oparroy.dsl.kicadlib import LibraryError

_MIN_NET_PINS = 2

#: Check id of the port-range containment check; waivers address it.
RANGE_CONTAINMENT = "range-containment"

#: Check id of the power-domain crossing check; waivers address it.
POWER_DOMAIN_CROSSING = "power-domain-crossing"


class Severity(StrEnum):
    """How bad an issue is; errors block pcbnew ingest, warnings don't.

    WAIVED is an error the capture explicitly waived (``Circuit.waive``)
    — it stays in the report, auditable, but does not block.
    """

    WARNING = "warning"
    ERROR = "error"
    WAIVED = "waived"


@dataclass(frozen=True)
class Issue:
    """One validation finding.

    ``check`` and ``path`` address the finding for waivers: the check
    id (``"range-containment"``) and the hierarchical path it fired at
    (``WD1/ka``). Findings without them cannot be waived.
    """

    severity: Severity
    message: str
    check: str | None = None
    path: str | None = None

    def __str__(self) -> str:
        return f"{self.severity}: {self.message}"


class CheckError(Exception):
    """The validation pass found errors; carries the error issues only."""

    def __init__(self, issues: list[Issue]) -> None:
        self.issues = issues
        summary = "\n".join(str(issue) for issue in issues)
        super().__init__(f"circuit check failed:\n{summary}")


class FootprintTable(Protocol):
    """Answers whether a ``Lib:Name`` footprint exists — kicadlib or stubs."""

    def exists(self, footprint: str) -> bool:
        """Return True if the footprint is present in the library."""
        ...


def check(circuit: Circuit, *, footprints: FootprintTable | None = None) -> list[Issue]:
    """Validate a finished circuit; returns the issue list.

    A hierarchical circuit (one with instances) or one with component
    sockets is flattened first, so findings report hierarchical paths
    (``WD1/Rs``, net ``WD1/x``), bound port nets are checked as the
    merged parent net, and sockets are checked as the part they
    resolve to (standalone default or packed package unit). The
    port-range containment check and the port/parent domain-kind
    agreement check run before flattening, over the instance bindings
    themselves; the power-domain crossing audit runs on the flat IR;
    the capture's waivers (``Circuit.waive``) apply last.
    """
    issues: list[Issue] = []
    issues.extend(_check_port_ranges(circuit, ()))
    issues.extend(_check_port_domain_kinds(circuit, ()))
    waivers = tuple(hierarchical_waivers(circuit))
    crossings = tuple(hierarchical_crossings(circuit))
    if circuit.instances or circuit.sockets:
        circuit = circuit.flatten()
    for ref in sorted(circuit.parts, key=natural_key):
        issues.extend(_check_part(circuit.parts[ref], footprints))
    for name in sorted(circuit.nets, key=natural_key):
        issues.extend(_check_net(circuit.nets[name]))
    issues.extend(_check_power_domains(circuit, crossings))
    return _apply_waivers(issues, waivers)


def _check_port_ranges(circuit: Circuit, prefix: tuple[str, ...]) -> list[Issue]:
    """Interval containment over the port ranges sharing a net, recursively.

    Every declared sink on a net — a bound port's or the net's own —
    must cover every declared source on that net, per quantity: voltage
    when declared, current when both sides carry one. An undeclared
    side is no data, not a finding. Checking per net rather than per
    binding covers the common board-level case: one instance's output
    port wired straight into a sibling's input port over a plain net.
    An endpoint is never checked against its own other face — a
    pass-through port's two faces are each checked at their own level.
    """
    issues: list[Issue] = []
    bindings: dict[Net, list[tuple[str, Net]]] = {}
    for instance in circuit.instances.values():
        child_ports = instance.circuit.ports
        for port_name, parent_net in instance.connections.items():
            path = "/".join((*prefix, instance.name, port_name))
            bindings.setdefault(parent_net, []).append((path, child_ports[port_name]))
        issues.extend(_check_port_ranges(instance.circuit, (*prefix, instance.name)))
    for net, ports in bindings.items():
        issues.extend(_check_net_ranges(net, ports))
    return issues


def _check_net_ranges(net: Net, ports: list[tuple[str, Net]]) -> list[Issue]:
    """Check every declared sink on ``net`` against every declared source.

    ``ports`` are the (hierarchical path, port net) pairs bound to
    ``net``. An endpoint is never checked against its own other face —
    a pass-through port's two faces are each checked at their own
    level.
    """
    # Each endpoint: (key, description, waiver path, limits). A net
    # endpoint has no path of its own — the finding addresses the port
    # it faces.
    sinks: list[tuple[tuple[str, str], str, str, Limits]] = []
    sources: list[tuple[tuple[str, str], str, str, Limits]] = []
    if net.sink is not None:
        sinks.append((("net", net.name), f"net {net.name!r}", "", net.sink))
    if net.source is not None:
        sources.append((("net", net.name), f"net {net.name!r}", "", net.source))
    for path, port in ports:
        if port.sink is not None:
            sinks.append((("port", path), f"port {path!r}", path, port.sink))
        if port.source is not None:
            sources.append((("port", path), f"port {path!r}", path, port.source))
    issues: list[Issue] = []
    for sink_key, sink_desc, sink_path, sink in sinks:
        for source_key, source_desc, source_path, source in sources:
            if sink_key == source_key:
                continue
            issues.extend(
                _covers(
                    sink_path or source_path,
                    sink_desc,
                    sink,
                    source_desc,
                    source,
                )
            )
    return issues


def _covers(
    path: str,
    sink_desc: str,
    sink: Limits,
    source_desc: str,
    source: Limits,
) -> list[Issue]:
    """Check that the sink's ranges cover the source's."""
    issues: list[Issue] = []
    if not sink.voltage.contains(source.voltage):
        issues.append(
            Issue(
                Severity.ERROR,
                f"{sink_desc} accepts {sink.voltage} V but {source_desc} "
                f"drives {source.voltage} V (sink range must cover source)",
                check=RANGE_CONTAINMENT,
                path=path,
            )
        )
    if (
        sink.current is not None
        and source.current is not None
        and not sink.current.contains(source.current)
    ):
        issues.append(
            Issue(
                Severity.ERROR,
                f"{sink_desc} accepts {sink.current} A but {source_desc} "
                f"drives {source.current} A (sink range must cover source)",
                check=RANGE_CONTAINMENT,
                path=path,
            )
        )
    return issues


def _check_port_domain_kinds(circuit: Circuit, prefix: tuple[str, ...]) -> list[Issue]:
    """Bound port and parent net power-domain kinds must agree, recursively.

    A port and its parent net may each declare a power domain — the
    duplicate declarations keep both sides of the binding honest. When
    both declare, the kinds must match; an undeclared side is no data,
    not a finding. Runs before flattening, over the instance bindings,
    like the port-range check.
    """
    issues: list[Issue] = []
    for instance in circuit.instances.values():
        child_ports = instance.circuit.ports
        for port_name, parent_net in instance.connections.items():
            port = child_ports[port_name]
            if (
                port.power_domain is None
                or parent_net.power_domain is None
                or port.power_domain.kind is parent_net.power_domain.kind
            ):
                continue
            path = "/".join((*prefix, instance.name, port_name))
            issues.append(
                Issue(
                    Severity.ERROR,
                    f"port {path!r} is declared {port.power_domain.kind} but "
                    f"its parent net {parent_net.name!r} is declared "
                    f"{parent_net.power_domain.kind} "
                    "(domain kinds must agree across a binding)",
                    check=POWER_DOMAIN_CROSSING,
                    path=path,
                )
            )
        issues.extend(
            _check_port_domain_kinds(instance.circuit, (*prefix, instance.name))
        )
    return issues


def _part_domains(part: Part) -> set[str]:
    """Collect the rail names powering a part: POWER_IN pins' declared domains.

    Ground rails are domain-neutral — a supply pin on GND contributes
    nothing; an undeclared rail is no data (rail completeness reports
    it separately).
    """
    return {
        pin.net.name
        for pin in part.pins
        if pin.type is PinType.POWER_IN
        and pin.net is not None
        and pin.net.power_domain is not None
        and pin.net.power_domain.kind is not PowerDomainKind.GROUND
    }


#: Pin count of a series resistor — the resistive reach's hop.
_SERIES_RESISTOR_PINS = 2

#: A net crosses when its signature holds at least this many distinct domains.
_CROSSING_MIN_DOMAINS = 2


def _is_series_resistor(part: Part) -> bool:
    """Return True for a two-pin Device-lib part with no power pin — the hop.

    The settled heuristic for the resistive reach (Device:R-class):
    exactly two pins, no POWER_IN, symbol from the Device library —
    the same shape the power-symbol rule keys on (``lib == "power"``).
    """
    return (
        len(part.pins) == _SERIES_RESISTOR_PINS
        and part.symbol.lib == "Device"
        and all(pin.type is not PinType.POWER_IN for pin in part.pins)
    )


def _resistive_walk(net: Net) -> tuple[list[Net], set[str]]:
    """Walk a net's resistive reach: the non-rail nets and the rails touched.

    Traversal hops series resistors only. Reaching a declared rail
    records the rail's name and stops — a rail is a domain owner,
    never part of the reach. The visited set bounds resistor loops.
    """
    nets: list[Net] = []
    rails: set[str] = set()
    visited = {net.name}
    stack = [net]
    while stack:
        current = stack.pop()
        nets.append(current)
        for pin in current.pins:
            if not _is_series_resistor(pin.part):
                continue
            other = next(p for p in pin.part.pins if p is not pin)
            target = other.net
            if target is None or target.name in visited:
                continue
            visited.add(target.name)
            if target.power_domain is not None:
                rails.add(target.name)
            else:
                stack.append(target)
    return nets, rails


def _net_signature(
    net: Net, rails: dict[str, PowerDomain], part_domains: dict[Part, set[str]]
) -> set[str]:
    """Compute the rail names whose domains a net touches.

    The domains of the non-power pins' parts on the net, plus the
    transitive resistive reach — a reached rail adds its own domain and
    stops the walk. GROUND rails contribute nothing, so a pull-down to
    GND is never a crossing.
    """
    nets, reached = _resistive_walk(net)
    signature = {
        rail for rail in reached if rails[rail].kind is not PowerDomainKind.GROUND
    }
    for reach_net in nets:
        for pin in reach_net.pins:
            part = pin.part
            if (
                part.symbol.is_power
                or part.symbol.is_sim
                or _is_series_resistor(part)
                or pin.type in (PinType.POWER_IN, PinType.POWER_OUT)
            ):
                continue
            signature |= part_domains.get(part, set())
    return signature


def _declared_rails(circuit: Circuit) -> dict[str, PowerDomain]:
    """Map each rail net's name to its declared domain."""
    return {
        name: net.power_domain
        for name, net in circuit.nets.items()
        if net.power_domain is not None
    }


def _find_crossings(
    circuit: Circuit,
    rails: dict[str, PowerDomain],
    part_domains: dict[Part, set[str]],
) -> dict[str, set[str]]:
    """Find the crossing nets: name → signature rail names.

    A net crosses when its signature holds ``_CROSSING_MIN_DOMAINS`` or
    more distinct domains, at least one of them SWITCHED — always↔always
    crossings are out of scope for v1. Rail nets own their domains and
    are never audited.
    """
    crossings: dict[str, set[str]] = {}
    for name in sorted(circuit.nets, key=natural_key):
        net = circuit.nets[name]
        if net.power_domain is not None:
            continue
        signature = _net_signature(net, rails, part_domains)
        if len(signature) >= _CROSSING_MIN_DOMAINS and any(
            rails[rail].kind is PowerDomainKind.SWITCHED for rail in signature
        ):
            crossings[name] = signature
    return crossings


def _undeclared_crossing_error(
    name: str, signature: set[str], rails: dict[str, PowerDomain]
) -> Issue:
    """Build the undeclared-crossing error, naming the net and its domains."""
    domains = ", ".join(
        f"{rail!r} ({rails[rail].kind})" for rail in sorted(signature, key=natural_key)
    )
    return Issue(
        Severity.ERROR,
        f"net {name!r} crosses power domains with no declared disposition: {domains}",
        check=POWER_DOMAIN_CROSSING,
        path=name,
    )


def _check_rail_completeness(circuit: Circuit) -> list[Issue]:
    """Warn on nets that look like rails but carry no declared domain.

    A net with a power-symbol pin or a POWER_OUT pin is driven as a
    rail (``_check_net``'s rule); without a declared domain it is a
    rail the capture forgot to declare — visible, never silent.
    """
    return [
        Issue(
            Severity.WARNING,
            f"rail net {net.name!r} has no declared power domain",
            check=POWER_DOMAIN_CROSSING,
            path=net.name,
        )
        for net in circuit.nets.values()
        if net.power_domain is None
        and any(
            pin.type is PinType.POWER_OUT or pin.part.symbol.is_power
            for pin in net.pins
        )
    ]


def _check_power_domains(
    circuit: Circuit, crossings: tuple[Crossing, ...]
) -> list[Issue]:
    """Audit power-domain crossings over the flat IR.

    Every crossing net (``_find_crossings``) must carry a declared
    disposition (``Circuit.crossing``, collected hierarchically), which
    the audit then verifies; an undeclared crossing is an error, a
    declaration matching no crossing net warns as stale. Rail
    completeness warns on undeclared rail nets.
    """
    issues: list[Issue] = []
    rails = _declared_rails(circuit)
    part_domains = {
        part: _part_domains(part)
        for part in circuit.parts.values()
        if not (part.symbol.is_power or part.symbol.is_sim)
    }
    declared: dict[str, list[Crossing]] = {}
    for crossing in crossings:
        declared.setdefault(crossing.path, []).append(crossing)
    for name, signature in _find_crossings(circuit, rails, part_domains).items():
        matching = declared.pop(name, [])
        if not matching:
            issues.append(_undeclared_crossing_error(name, signature, rails))
        for crossing in matching:
            issues.extend(_verify_disposition(circuit, crossing, rails, part_domains))
    issues.extend(
        Issue(
            Severity.WARNING,
            f"crossing declaration at {path!r} matched no crossing net",
            check=POWER_DOMAIN_CROSSING,
            path=path,
        )
        for path in declared
    )
    issues.extend(_check_rail_completeness(circuit))
    return issues


def _verify_disposition(
    circuit: Circuit,
    crossing: Crossing,
    rails: dict[str, PowerDomain],
    part_domains: dict[Part, set[str]],
) -> list[Issue]:
    """Verify one declared crossing's disposition against the flat IR."""
    net = circuit.nets[crossing.path]
    if isinstance(crossing.disposition, DiesWith):
        return _verify_dies_with(net, rails, part_domains)
    if isinstance(crossing.disposition, AlwaysPowered):
        return _verify_always_powered(net)
    # BackFeed: budget and citation are declaration-time data (v1).
    return []


def _verify_dies_with(
    net: Net, rails: dict[str, PowerDomain], part_domains: dict[Part, set[str]]
) -> list[Issue]:
    """Every always-powered pin on the net's reach must be input-class.

    A foreign OUTPUT/BIDIR driver fails — it would drive the dead net
    (the Rth1 bug shape). Power pins are not signal drivers and are
    skipped, as are power-symbol and sim parts.
    """
    issues: list[Issue] = []
    nets, _rails = _resistive_walk(net)
    for reach_net in nets:
        for pin in reach_net.pins:
            part = pin.part
            if (
                part.symbol.is_power
                or part.symbol.is_sim
                or pin.type in (PinType.POWER_IN, PinType.POWER_OUT)
                or not any(
                    rails[rail].kind is PowerDomainKind.ALWAYS
                    for rail in part_domains.get(part, ())
                )
                or pin.type in (PinType.INPUT, PinType.PASSIVE)
            ):
                continue
            issues.append(
                Issue(
                    Severity.ERROR,
                    f"net {net.name!r} is declared dies-with-domain but "
                    f"{part.ref}.{pin.number} ({pin.type}) is powered from "
                    "an always rail and may drive the dead net",
                    check=POWER_DOMAIN_CROSSING,
                    path=net.name,
                )
            )
    return issues


def _verify_always_powered(net: Net) -> list[Issue]:
    """No-Ioff parts on the net's reach must draw power from always rails.

    Every part touching the net or its resistive reach whose parts-DB
    record says ``partial_power_down`` is False must have all its
    POWER_IN pins on ALWAYS-domain nets — a ground pin is
    domain-neutral. Parts with no data (None) are never a finding.
    """
    issues: list[Issue] = []
    nets, _rails = _resistive_walk(net)
    checked: set[str] = set()
    for reach_net in nets:
        for pin in reach_net.pins:
            part = pin.part
            if (
                part.symbol.is_power
                or part.symbol.is_sim
                or part.ref in checked
                or part.partial_power_down is not False
            ):
                continue
            checked.add(part.ref)
            offenders = [
                power_pin
                for power_pin in part.pins
                if power_pin.type is PinType.POWER_IN
                and (
                    power_pin.net is None
                    or power_pin.net.power_domain is None
                    or power_pin.net.power_domain.kind is PowerDomainKind.SWITCHED
                )
            ]
            if offenders:
                pins = ", ".join(f"{part.ref}.{p.number}" for p in offenders)
                issues.append(
                    Issue(
                        Severity.ERROR,
                        f"net {net.name!r} is declared always-powered but "
                        f"{part.ref} has no partial-power-down spec and not "
                        f"all its power pins are on always rails ({pins})",
                        check=POWER_DOMAIN_CROSSING,
                        path=net.name,
                    )
                )
    return issues


def _check_part(part: Part, footprints: FootprintTable | None) -> list[Issue]:
    issues: list[Issue] = []
    if part.value is None:
        issues.append(Issue(Severity.WARNING, f"{part.ref} has no value"))
    if part.symbol.is_power or part.symbol.is_sim:
        # Schematic-only net markers and simulation-only parts (external
        # subcircuit instances): never reach the board, no footprint.
        pass
    elif part.footprint is None:
        issues.append(
            Issue(
                Severity.ERROR,
                f"{part.ref} has no footprint (pcbnew needs one)",
            )
        )
    elif (found := _footprint_found(footprints, part.footprint)) is None:
        issues.append(
            Issue(
                Severity.ERROR,
                f"{part.ref} footprint {part.footprint!r} is not "
                "a 'Lib:Name' reference",
            )
        )
    elif not found:
        issues.append(
            Issue(
                Severity.ERROR,
                f"{part.ref} footprint {part.footprint!r} not found "
                "in the KiCad footprint libraries",
            )
        )
    elif not _matches_filters(part):
        issues.append(
            Issue(
                Severity.WARNING,
                f"{part.ref} footprint {part.footprint!r} matches none "
                f"of {part.symbol.ref}'s footprint filters "
                f"{part.symbol.footprint_filters}",
            )
        )
    if part.symbol.pin_conflicts:
        pins = ", ".join(part.symbol.pin_conflicts)
        issues.append(
            Issue(
                Severity.WARNING,
                f"{part.ref}: {part.symbol.ref} has conflicting pin "
                f"definitions for {pins} (last definition wins)",
            )
        )
    issues.extend(
        Issue(Severity.WARNING, f"{part.ref}.{pin.number} is not connected")
        for pin in part.pins
        if pin.net is None and pin.type not in (PinType.NO_CONNECT, PinType.FREE)
    )
    return issues


def _footprint_found(footprints: FootprintTable | None, footprint: str) -> bool | None:
    """True/False from the table; None when the reference is malformed."""
    if footprints is None:
        return True
    try:
        return footprints.exists(footprint)
    except LibraryError:
        return None


def _check_net(net: Net) -> list[Issue]:
    issues: list[Issue] = []
    if not net.is_port:
        # Port nets dangle by design — the instantiating parent binds
        # them; pin-count and driver rules apply to the merged net.
        if not net.pins:
            issues.append(Issue(Severity.WARNING, f"net {net.name!r} has no pins"))
        elif len(net.pins) < _MIN_NET_PINS:
            pin = net.pins[0]
            issues.append(
                Issue(
                    Severity.WARNING,
                    f"net {net.name!r} has a single pin ({pin.part.ref}.{pin.number})",
                )
            )
    drivers = [pin for pin in net.pins if pin.type is PinType.POWER_OUT]
    if len(drivers) > 1:
        refs = ", ".join(f"{p.part.ref}.{p.number}" for p in drivers)
        issues.append(
            Issue(
                Severity.ERROR,
                f"net {net.name!r} has multiple power outputs: {refs}",
            )
        )
    # KiCad's own convention: a net is driven by a power output pin or
    # by a power-symbol pin (power:+3V3-class, whose pins are power_in).
    driven = bool(drivers) or any(pin.part.symbol.is_power for pin in net.pins)
    sinks = [pin for pin in net.pins if pin.type is PinType.POWER_IN]
    if sinks and not driven and not net.is_port:
        issues.append(
            Issue(
                Severity.WARNING,
                f"net {net.name!r} has power inputs but no driver "
                "(power output or power symbol)",
            )
        )
    return issues


def _matches_filters(part: Part) -> bool:
    if not part.symbol.footprint_filters or part.footprint is None:
        return True
    # KiCad filters come in both shapes: name-only ("R_*") and
    # lib-qualified ("Connector*:*_1x??_*") — match against the bare
    # footprint name and the full Lib:Name reference.
    fp_name = part.footprint.rsplit(":", maxsplit=1)[-1]
    return any(
        fnmatch.fnmatchcase(candidate, fp_filter)
        for fp_filter in part.symbol.footprint_filters
        for candidate in (fp_name, part.footprint)
    )


def _apply_waivers(issues: list[Issue], waivers: tuple[Waiver, ...]) -> list[Issue]:
    """Apply the capture's waivers: matched errors become WAIVED findings.

    A waived finding stays in the list with its reason appended — the
    waiver is auditable, the finding is not erased. A waiver matching
    no finding is stale data and warns.
    """
    if not waivers:
        return issues
    result: list[Issue] = []
    used: set[Waiver] = set()
    for issue in issues:
        waiver = next(
            (w for w in waivers if w.check == issue.check and w.path == issue.path),
            None,
        )
        if waiver is not None:
            used.add(waiver)
        if waiver is None or issue.severity is not Severity.ERROR:
            result.append(issue)
            continue
        result.append(
            Issue(
                Severity.WAIVED,
                f"{issue.message} (waived: {waiver.reason})",
                check=issue.check,
                path=issue.path,
            )
        )
    result.extend(
        Issue(
            Severity.WARNING,
            f"waiver {waiver.check!r} at {waiver.path!r} matched no issue",
        )
        for waiver in waivers
        if waiver not in used
    )
    return result


def raise_on_errors(issues: list[Issue]) -> None:
    """Raise CheckError if any issue is an error; warnings pass through."""
    errors = [issue for issue in issues if issue.severity is Severity.ERROR]
    if errors:
        raise CheckError(errors)
