"""Validation pass over a finished circuit IR (capture → check → emit).

Structural invariants raise during capture (see ir.py); everything here
is a *semantic* check over the finished IR, reported as a batch of
issues rather than a first-failure exception. Beyond what the emitters
and pcbnew need to be true, this pass carries the first electrical
rules: interval containment over port limit ranges (a sink's acceptable
range must cover the connected source's output range), with waivers as
explicit, path-addressed capture data.
"""

import fnmatch
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from oparroy.dsl.ir import (
    Circuit,
    Limits,
    Net,
    Part,
    PinType,
    Waiver,
    hierarchical_waivers,
    natural_key,
)
from oparroy.dsl.kicadlib import LibraryError

_MIN_NET_PINS = 2

#: Check id of the port-range containment check; waivers address it.
RANGE_CONTAINMENT = "range-containment"


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
    port-range containment check runs before flattening, over the
    instance bindings themselves; the capture's waivers
    (``Circuit.waive``) apply last.
    """
    issues: list[Issue] = []
    issues.extend(_check_port_ranges(circuit, ()))
    waivers = tuple(hierarchical_waivers(circuit))
    if circuit.instances or circuit.sockets:
        circuit = circuit.flatten()
    for ref in sorted(circuit.parts, key=natural_key):
        issues.extend(_check_part(circuit.parts[ref], footprints))
    for name in sorted(circuit.nets, key=natural_key):
        issues.extend(_check_net(circuit.nets[name]))
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


def _check_part(part: Part, footprints: FootprintTable | None) -> list[Issue]:
    issues: list[Issue] = []
    if part.value is None:
        issues.append(Issue(Severity.WARNING, f"{part.ref} has no value"))
    if part.symbol.is_power:
        # Schematic-only net marker: never reaches the board, no footprint.
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
