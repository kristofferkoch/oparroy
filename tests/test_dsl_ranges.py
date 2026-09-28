"""Port limit ranges, interval containment, and waivers (T8)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from oparroy.dsl import (
    RANGE_CONTAINMENT,
    Circuit,
    DefinitionError,
    Interval,
    Issue,
    Limits,
    Severity,
    check,
    raise_on_errors,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from conftest import StubFootprints, StubSymbols


def messages(issues: list[Issue], severity: Severity) -> list[str]:
    return [i.message for i in issues if i.severity is severity]


def sink_child(circuit: Circuit) -> None:
    """Capture a subcircuit whose ``vin`` port accepts 0..3.6 V, 0..20 mA."""
    vin = circuit.port(
        "vin", sink=Limits(voltage=Interval(0, 3.6), current=Interval(0, 0.02))
    )
    gnd = circuit.port("gnd")
    r1 = circuit.part("R1", symbol="Stub:R", value="1k", footprint="StubFP:R_0603")
    circuit.connect(vin, r1[1])
    circuit.connect(gnd, r1[2])


def board_driving(
    symbols: StubSymbols,
    source: Limits,
    child: Callable[[Circuit], None] = sink_child,
) -> Circuit:
    """Build a board whose ``VCC`` port drives ``source`` limits into the child."""
    board = Circuit("board", symbols)
    vcc = board.port("VCC", source=source)
    gnd = board.port("GND")
    board.instance("U1", child, vin=vcc, gnd=gnd)
    return board


def test_interval_rejects_inverted_range() -> None:
    with pytest.raises(DefinitionError):
        Interval(3.6, 0)


def test_port_carries_limit_ranges(symbols: StubSymbols) -> None:
    c = Circuit("c", symbols)
    vin = c.port(
        "vin", sink=Limits(voltage=Interval(0, 3.6), current=Interval(0, 0.02))
    )
    assert vin.sink == Limits(voltage=Interval(0, 3.6), current=Interval(0, 0.02))
    assert vin.source is None
    plain = c.net("n")
    assert plain.sink is None
    assert plain.source is None


def test_flatten_preserves_unbound_port_ranges(symbols: StubSymbols) -> None:
    board = board_driving(symbols, Limits(voltage=Interval(0, 3.3)))
    flat = board.flatten()
    assert flat.nets["VCC"].source == Limits(voltage=Interval(0, 3.3))
    assert flat.nets["VCC"].is_port


def test_dump_shows_port_ranges(symbols: StubSymbols) -> None:
    c = Circuit("dump", symbols)
    c.port("vin", sink=Limits(voltage=Interval(0, 3.6)))
    c.port("iout", source=Limits(voltage=Interval(0, 3.3), current=Interval(0, 0.1)))
    dump = c.dump()
    assert "vin [port, sink 0..3.6 V]:" in dump
    assert "iout [port, source 0..3.3 V, 0..0.1 A]:" in dump


def test_covering_ranges_check_clean(
    symbols: StubSymbols, footprints: StubFootprints
) -> None:
    # Source 0..3.3 V / 0..10 mA fits inside the sink's 0..3.6 V / 0..20 mA.
    board = board_driving(
        symbols, Limits(voltage=Interval(0, 3.3), current=Interval(0, 0.01))
    )
    assert check(board, footprints=footprints) == []


def test_sink_must_cover_source_voltage(
    symbols: StubSymbols, footprints: StubFootprints
) -> None:
    board = board_driving(symbols, Limits(voltage=Interval(-0.5, 5)))
    issues = check(board, footprints=footprints)
    errors = [i for i in issues if i.severity is Severity.ERROR]
    (error,) = errors
    assert error.message == (
        "port 'U1/vin' accepts 0..3.6 V but net 'VCC' drives -0.5..5 V "
        "(sink range must cover source)"
    )
    assert error.check == RANGE_CONTAINMENT
    assert error.path == "U1/vin"


def test_sink_must_cover_source_current(
    symbols: StubSymbols, footprints: StubFootprints
) -> None:
    # Voltage fits; the source can push 500 mA into a 20 mA sink.
    board = board_driving(
        symbols, Limits(voltage=Interval(0, 3.3), current=Interval(0, 0.5))
    )
    errors = messages(check(board, footprints=footprints), Severity.ERROR)
    assert errors == [
        (
            "port 'U1/vin' accepts 0..0.02 A but net 'VCC' drives 0..0.5 A "
            "(sink range must cover source)"
        )
    ]


def test_current_unchecked_when_one_side_omits_it(
    symbols: StubSymbols, footprints: StubFootprints
) -> None:
    # Only the source declares a current range — no data, no finding.
    def voltage_only_sink(circuit: Circuit) -> None:
        vin = circuit.port("vin", sink=Limits(voltage=Interval(0, 3.6)))
        gnd = circuit.port("gnd")
        r1 = circuit.part("R1", symbol="Stub:R", value="1k", footprint="StubFP:R_0603")
        circuit.connect(vin, r1[1])
        circuit.connect(gnd, r1[2])

    board = board_driving(
        symbols,
        Limits(voltage=Interval(0, 3.3), current=Interval(0, 99)),
        child=voltage_only_sink,
    )
    assert check(board, footprints=footprints) == []


def test_port_source_into_parent_sink(
    symbols: StubSymbols, footprints: StubFootprints
) -> None:
    # The reverse direction: the child drives, the parent accepts.
    def source_child(circuit: Circuit) -> None:
        vout = circuit.port("vout", source=Limits(voltage=Interval(0, 3.3)))
        gnd = circuit.port("gnd")
        r1 = circuit.part("R1", symbol="Stub:R", value="1k", footprint="StubFP:R_0603")
        circuit.connect(vout, r1[1])
        circuit.connect(gnd, r1[2])

    board = Circuit("board", symbols)
    out = board.port("OUT", sink=Limits(voltage=Interval(0, 3.6)))
    gnd = board.port("GND")
    board.instance("U1", source_child, vout=out, gnd=gnd)
    assert check(board, footprints=footprints) == []

    tight = Circuit("tight", symbols)
    out = tight.port("OUT", sink=Limits(voltage=Interval(0, 3)))
    gnd = tight.port("GND")
    tight.instance("U1", source_child, vout=out, gnd=gnd)
    errors = messages(check(tight, footprints=footprints), Severity.ERROR)
    assert errors == [
        (
            "net 'OUT' accepts 0..3 V but port 'U1/vout' drives 0..3.3 V "
            "(sink range must cover source)"
        )
    ]


def test_undeclared_side_skips_the_check(
    symbols: StubSymbols, footprints: StubFootprints
) -> None:
    # A plain parent port carries no ranges — nothing to check against.
    board = Circuit("board", symbols)
    vcc = board.port("VCC")
    gnd = board.port("GND")
    board.instance("U1", sink_child, vin=vcc, gnd=gnd)
    assert check(board, footprints=footprints) == []


def test_nested_instances_report_full_paths(
    symbols: StubSymbols, footprints: StubFootprints
) -> None:
    # A pass-through port declares both faces: what it accepts from its
    # parent and what it passes on to its children.
    def tight_sink(circuit: Circuit) -> None:
        vin = circuit.port("vin", sink=Limits(voltage=Interval(0, 3)))
        gnd = circuit.port("gnd")
        r1 = circuit.part("R1", symbol="Stub:R", value="1k", footprint="StubFP:R_0603")
        circuit.connect(vin, r1[1])
        circuit.connect(gnd, r1[2])

    def mid(circuit: Circuit) -> None:
        vin = circuit.port(
            "vin",
            sink=Limits(voltage=Interval(0, 3.6)),
            source=Limits(voltage=Interval(0, 3.3)),
        )
        gnd = circuit.port("gnd")
        circuit.instance("IN1", tight_sink, vin=vin, gnd=gnd)

    board = Circuit("board", symbols)
    vcc = board.port("VCC", source=Limits(voltage=Interval(0, 3.3)))
    gnd = board.port("GND")
    board.instance("MID1", mid, vin=vcc, gnd=gnd)
    issues = check(board, footprints=footprints)
    errors = [i for i in issues if i.severity is Severity.ERROR]
    (error,) = errors
    assert error.path == "MID1/IN1/vin"
    assert "accepts 0..3 V" in error.message


def test_waiver_turns_error_into_waived_finding(
    symbols: StubSymbols, footprints: StubFootprints
) -> None:
    board = board_driving(symbols, Limits(voltage=Interval(-0.5, 5)))
    board.waive(RANGE_CONTAINMENT, "U1/vin", reason="bench harness clamps to the rails")
    issues = check(board, footprints=footprints)
    (waived,) = [i for i in issues if i.severity is Severity.WAIVED]
    assert "waived: bench harness clamps to the rails" in waived.message
    assert waived.check == RANGE_CONTAINMENT
    assert waived.path == "U1/vin"
    assert messages(issues, Severity.ERROR) == []
    assert messages(issues, Severity.WARNING) == []
    raise_on_errors(issues)


def test_stale_waiver_warns_and_leaves_errors(
    symbols: StubSymbols, footprints: StubFootprints
) -> None:
    board = board_driving(symbols, Limits(voltage=Interval(-0.5, 5)))
    board.waive(RANGE_CONTAINMENT, "U1/nope", reason="typo'd path")
    issues = check(board, footprints=footprints)
    assert len(messages(issues, Severity.ERROR)) == 1
    assert messages(issues, Severity.WARNING) == [
        "waiver 'range-containment' at 'U1/nope' matched no issue"
    ]


def test_waiver_matching_warning_does_not_go_stale(
    symbols: StubSymbols, footprints: StubFootprints
) -> None:
    # A waiver may address a warning; it is used, the warning stands.
    board = board_driving(symbols, Limits(voltage=Interval(-0.5, 5)))
    board.waive(RANGE_CONTAINMENT, "U1/vin", reason="noted")
    issues = check(board, footprints=footprints)
    assert messages(issues, Severity.WARNING) == []


def test_waive_requires_a_reason(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    with pytest.raises(DefinitionError):
        board.waive(RANGE_CONTAINMENT, "U1/vin", reason="")


def test_waive_rejects_duplicates(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    board.waive(RANGE_CONTAINMENT, "U1/vin", reason="one")
    with pytest.raises(DefinitionError):
        board.waive(RANGE_CONTAINMENT, "U1/vin", reason="two")
