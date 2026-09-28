"""Validation-pass tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from conftest import make_symbol
from oparroy.dsl import (
    CheckError,
    Circuit,
    Issue,
    KiCadLibraries,
    PinType,
    Severity,
    Symbol,
    check,
    raise_on_errors,
)

if TYPE_CHECKING:
    from conftest import StubFootprints, StubSymbols


def messages(issues: list[Issue], severity: Severity) -> list[str]:
    return [i.message for i in issues if i.severity is severity]


def test_clean_circuit_has_no_issues(
    circuit: Circuit, footprints: StubFootprints
) -> None:
    assert check(circuit, footprints=footprints) == []


def test_unconnected_pin_warns(circuit: Circuit, footprints: StubFootprints) -> None:
    circuit.part("R3", symbol="Stub:R", value="1", footprint="StubFP:R_0603")
    issues = check(circuit, footprints=footprints)
    assert messages(issues, Severity.WARNING) == [
        "R3.1 is not connected",
        "R3.2 is not connected",
    ]


def test_no_connect_and_free_pins_exempt_from_unconnected_warning(
    footprints: StubFootprints,
) -> None:
    # NO_CONNECT and FREE pins are unconnected by library contract.
    class ConnSymbols:
        def lookup(self, ref: str) -> Symbol:
            assert ref == "Stub:CONN"
            return make_symbol(
                "CONN",
                {
                    "1": PinType.PASSIVE,
                    "2": PinType.NO_CONNECT,
                    "3": PinType.FREE,
                },
            )

    c = Circuit("nc", ConnSymbols())
    c.part("J1", symbol="Stub:CONN", value="x", footprint="StubFP:R_0603")
    warnings = messages(check(c, footprints=footprints), Severity.WARNING)
    assert warnings == ["J1.1 is not connected"]


def test_single_pin_net_warns(circuit: Circuit, footprints: StubFootprints) -> None:
    r3 = circuit.part("R3", symbol="Stub:R", value="1", footprint="StubFP:R_0603")
    tap = circuit.net("tap")
    circuit.connect(tap, r3[1])
    circuit.connect("mid", r3[2])
    assert "net 'tap' has a single pin (R3.1)" in messages(
        check(circuit, footprints=footprints), Severity.WARNING
    )


def test_missing_footprint_errors(circuit: Circuit) -> None:
    circuit.part("R3", symbol="Stub:R", value="1")
    errors = messages(check(circuit), Severity.ERROR)
    assert errors == ["R3 has no footprint (pcbnew needs one)"]


def test_unknown_footprint_errors(circuit: Circuit, footprints: StubFootprints) -> None:
    circuit.part("R3", symbol="Stub:R", value="1", footprint="StubFP:NOPE")
    circuit.connect("a", circuit.parts["R3"][1])
    circuit.connect("mid", circuit.parts["R3"][2])
    errors = messages(check(circuit, footprints=footprints), Severity.ERROR)
    assert errors == [
        "R3 footprint 'StubFP:NOPE' not found in the KiCad footprint libraries"
    ]


def test_footprint_filter_mismatch_warns(circuit: Circuit) -> None:
    circuit.part("R3", symbol="Stub:R", value="1", footprint="Odd:SIP-2")
    warnings = messages(check(circuit), Severity.WARNING)
    assert any("matches none of Stub:R's footprint filters" in w for w in warnings)


def test_footprint_filter_matches_lib_qualified(
    footprints: StubFootprints,
) -> None:
    # KiCad has lib-qualified filters ("Connector*:*_1x??_*") — they
    # match against the full Lib:Name footprint reference, not only
    # the bare footprint name (T7bb rider fix).
    class ConnSymbols:
        def lookup(self, ref: str) -> Symbol:
            assert ref == "Stub:CONN6Q"
            return make_symbol(
                "CONN6Q",
                {str(pin): PinType.PASSIVE for pin in range(1, 7)},
                ("StubFP*:CONN_1x??",),
            )

    c = Circuit("conn", ConnSymbols())
    c.part("J1", symbol="Stub:CONN6Q", value="x", footprint="StubFP:CONN_1x06")
    warnings = messages(check(c, footprints=footprints), Severity.WARNING)
    assert not any("footprint filters" in w for w in warnings)
    c.part("J2", symbol="Stub:CONN6Q", value="x", footprint="StubFP:CONN_2x06")
    warnings = messages(check(c), Severity.WARNING)
    assert any("J2 footprint 'StubFP:CONN_2x06' matches none" in w for w in warnings)


def test_missing_value_warns(circuit: Circuit, footprints: StubFootprints) -> None:
    r3 = circuit.part("R3", symbol="Stub:R", footprint="StubFP:R_0603")
    circuit.connect("a", r3[1])
    circuit.connect("mid", r3[2])
    assert "R3 has no value" in messages(
        check(circuit, footprints=footprints), Severity.WARNING
    )


def test_multiple_power_outputs_error(
    symbols: StubSymbols, footprints: StubFootprints
) -> None:
    c = Circuit("pwr", symbols)
    p1 = c.part("P1", symbol="Stub:REG", value="3V3", footprint="StubFP:PWR_SIP")
    p2 = c.part("P2", symbol="Stub:REG", value="3V3", footprint="StubFP:PWR_SIP")
    rail = c.net("3V3")
    c.connect(rail, p1[1], p2[1])
    errors = messages(check(c, footprints=footprints), Severity.ERROR)
    assert errors == ["net '3V3' has multiple power outputs: P1.1, P2.1"]


def test_power_symbol_marks_rail_driven(
    symbols: StubSymbols, footprints: StubFootprints
) -> None:
    # KiCad's convention: a power-library symbol (power:+3V3-class,
    # power_in pin) marks the rail driven — and needs no footprint,
    # being a schematic-only net marker.
    c = Circuit("pwr", symbols)
    load = c.part("L1", symbol="Stub:LOAD", value="", footprint="StubFP:LOAD_SIP")
    marker = c.part("P1", symbol="power:+3V3", value="+3V3")
    rail = c.net("3V3")
    gnd = c.net("GND")
    c.connect(rail, load[1], marker[1])
    c.connect(gnd, load[2])
    issues = check(c, footprints=footprints)
    assert messages(issues, Severity.ERROR) == []
    warnings = messages(issues, Severity.WARNING)
    assert not any("net '3V3'" in w for w in warnings)
    assert any("net 'GND' has power inputs but no driver" in w for w in warnings)


def test_undriven_power_input_warns(
    symbols: StubSymbols, footprints: StubFootprints
) -> None:
    c = Circuit("pwr", symbols)
    load = c.part("L1", symbol="Stub:LOAD", value="", footprint="StubFP:LOAD_SIP")
    rail = c.net("3V3")
    gnd = c.net("GND")
    c.connect(rail, load[1])
    c.connect(gnd, load[2])
    warnings = messages(check(c, footprints=footprints), Severity.WARNING)
    no_driver = "has power inputs but no driver (power output or power symbol)"
    assert f"net '3V3' {no_driver}" in warnings
    assert f"net 'GND' {no_driver}" in warnings


def test_empty_net_warns(circuit: Circuit, footprints: StubFootprints) -> None:
    circuit.net("spare")
    warnings = messages(check(circuit, footprints=footprints), Severity.WARNING)
    assert "net 'spare' has no pins" in warnings


def test_malformed_footprint_is_an_issue_not_an_exception(
    kicad_libs: KiCadLibraries,
) -> None:
    # A footprint string without a Lib: prefix must surface as an
    # error issue, not abort the batch with LibraryError.
    c = Circuit("x", kicad_libs)
    c.part("R1", symbol="Device:R", value="1k", footprint="SOT-23")
    errors = messages(check(c, footprints=kicad_libs), Severity.ERROR)
    assert "R1 footprint 'SOT-23' is not a 'Lib:Name' reference" in errors


def test_real_power_symbol_drives_rail(kicad_libs: KiCadLibraries) -> None:
    # The real-library shape: power:+3V3 marks the rail, the 74HC00's
    # VCC/VSS are power_in — no undriven warnings.
    c = Circuit("pwr", kicad_libs)
    u1 = c.part(
        "U1",
        symbol="74xx:74HC00",
        value="74HC00",
        footprint="Package_DIP:DIP-14_W7.62mm",
    )
    p1 = c.part("P1", symbol="power:+3V3", value="+3V3")
    p2 = c.part("P2", symbol="power:GND", value="GND")
    vcc = c.net("3V3")
    gnd = c.net("GND")
    c.connect(vcc, p1[1], u1[14])
    c.connect(gnd, p2[1], u1[7])
    issues = check(c, footprints=kicad_libs)
    assert not any("no driver" in w for w in messages(issues, Severity.WARNING))
    assert not any("P1" in e or "P2" in e for e in messages(issues, Severity.ERROR))


def test_raise_on_errors(symbols: StubSymbols, footprints: StubFootprints) -> None:
    c = Circuit("bad", symbols)
    c.part("P1", symbol="Stub:REG", value="3V3", footprint="StubFP:PWR_SIP")
    c.part("P2", symbol="Stub:REG", value="3V3")
    issues = check(c, footprints=footprints)
    with pytest.raises(CheckError):
        raise_on_errors(issues)


def test_raise_on_errors_passes_warnings(
    circuit: Circuit, footprints: StubFootprints
) -> None:
    raise_on_errors(check(circuit, footprints=footprints))
