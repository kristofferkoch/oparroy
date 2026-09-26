"""Validation pass over a finished circuit IR (capture → check → emit).

Structural invariants raise during capture (see ir.py); everything here
is a *semantic* check over the finished IR, reported as a batch of
issues rather than a first-failure exception. ERC-depth electrical
rules are T8's scope; this pass covers what the emitters and pcbnew
need to be true.
"""

import fnmatch
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from oparroy.dsl.ir import Circuit, Net, Part, PinType, natural_key
from oparroy.dsl.kicadlib import LibraryError

_MIN_NET_PINS = 2


class Severity(StrEnum):
    """How bad an issue is; errors block pcbnew ingest, warnings don't."""

    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class Issue:
    """One validation finding."""

    severity: Severity
    message: str

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
    """Validate a finished circuit; returns the issue list."""
    issues: list[Issue] = []
    for ref in sorted(circuit.parts, key=natural_key):
        issues.extend(_check_part(circuit.parts[ref], footprints))
    for name in sorted(circuit.nets, key=natural_key):
        issues.extend(_check_net(circuit.nets[name]))
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
    if sinks and not driven:
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
    fp_name = part.footprint.rsplit(":", maxsplit=1)[-1]
    return any(
        fnmatch.fnmatchcase(fp_name, fp_filter)
        for fp_filter in part.symbol.footprint_filters
    )


def raise_on_errors(issues: list[Issue]) -> None:
    """Raise CheckError if any issue is an error; warnings pass through."""
    errors = [issue for issue in issues if issue.severity is Severity.ERROR]
    if errors:
        raise CheckError(errors)
