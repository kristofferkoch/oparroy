"""CI-power capture tests (need the nix-provisioned libraries).

The golden netlist at tests/golden/ci-power.net is what pcbnew
ingests; regenerate it from the dev shell with:

    python -m design.ci_power > tests/golden/ci-power.net
"""

from __future__ import annotations

from pathlib import Path

from design.ci_power import CiPower, capture
from oparroy.dsl import (
    Circuit,
    Interval,
    KiCadLibraries,
    Limits,
    Severity,
    check,
    emit_netlist,
    raise_on_errors,
)

GOLDEN = Path(__file__).parent / "golden" / "ci-power.net"

#: The receptacle's SBU pins: unused on a USB 2.0 sink, and deliberately
#: left out of the pin map.
EXPECTED_NC_WARNINGS = {"J1.A8 is not connected", "J1.B8 is not connected"}


def nets_of(circuit: Circuit) -> dict[str, set[str]]:
    """Net name -> member pins as 'ref.number'."""
    return {
        name: {f"{p.part.ref}.{p.number}" for p in net.pins}
        for name, net in circuit.nets.items()
    }


def board_driving(kicad_libs: KiCadLibraries, vbus_source: Interval) -> Circuit:
    """Build a board driving CiPower: VBUS sources ``vbus_source``, 3V3 accepts."""
    board = Circuit("board", kicad_libs)
    v5 = board.port("VBUS", source=Limits(voltage=vbus_source))
    v3v3 = board.port("RAIL_3V3", sink=Limits(voltage=Interval(3.2, 3.4)))
    gnd = board.port("GND")
    dp = board.port("DP", sink=Limits(voltage=Interval(0, 3.6)))
    dm = board.port("DM", sink=Limits(voltage=Interval(0, 3.6)))
    board.instance(
        "PWR1",
        CiPower(),
        **{"5V": v5, "3V3": v3v3, "GND": gnd, "USB_DP": dp, "USB_DM": dm},
    )
    return board


def test_capture_declares_its_ports(kicad_libs: KiCadLibraries) -> None:
    circuit = capture(kicad_libs)
    assert set(circuit.ports) == {"5V", "3V3", "GND", "USB_DP", "USB_DM"}


def test_receptacle_wiring(kicad_libs: KiCadLibraries) -> None:
    # §6: VBUS quadrupled, grounds and shell on GND, D+/D- doubled onto
    # the pass-through ports, CC1/CC2 each on their own Rd net.
    nets = nets_of(capture(kicad_libs))
    assert {"J1.A4", "J1.A9", "J1.B4", "J1.B9", "U1.3", "Cin.1"} == nets["5V"]
    assert {"J1.A6", "J1.B6"} == nets["USB_DP"]
    assert {"J1.A7", "J1.B7"} == nets["USB_DM"]
    assert nets["cc1"] == {"J1.A5", "Rcc1.1"}
    assert nets["cc2"] == {"J1.B5", "Rcc2.1"}
    assert {
        "J1.A1",
        "J1.A12",
        "J1.B1",
        "J1.B12",
        "J1.SH",
        "Rcc1.2",
        "Rcc2.2",
        "Cin.2",
        "Cout.2",
        "U1.1",
    } == nets["GND"]


def test_regulator_drives_3v3(kicad_libs: KiCadLibraries) -> None:
    # §6: U1's VO (pin 2, power_out) is the rail's only driver; no 5 V
    # net exists past the regulator input (UNREG omitted, §2.1).
    nets = nets_of(capture(kicad_libs))
    assert nets["3V3"] == {"U1.2", "Cout.1"}
    assert "UNREG" not in nets


def test_cc_pulldown_values(kicad_libs: KiCadLibraries) -> None:
    # USB-C sink termination: 5.1 kΩ Rd on both CC lines, no PD.
    circuit = capture(kicad_libs)
    assert circuit.parts["Rcc1"].value == "5k1"
    assert circuit.parts["Rcc2"].value == "5k1"


def test_capture_checks_clean(kicad_libs: KiCadLibraries) -> None:
    circuit = capture(kicad_libs)
    issues = check(circuit, footprints=kicad_libs)
    assert [i for i in issues if i.severity is Severity.ERROR] == []
    assert {i.message for i in issues} == EXPECTED_NC_WARNINGS
    raise_on_errors(issues)


def test_board_covering_port_ranges_checks_clean(kicad_libs: KiCadLibraries) -> None:
    # Range containment: a compliant USB-C VBUS (4.75..5.25 V) fits the
    # 5V port's accept (4.5..5.5 V), and 3V3's 3.2..3.4 V output fits the
    # board's rail accept. The SBU NC warnings flatten along.
    board = board_driving(kicad_libs, Interval(4.75, 5.25))
    issues = check(board, footprints=kicad_libs)
    assert [i for i in issues if i.severity is Severity.ERROR] == []
    assert {i.message for i in issues} == {
        f"PWR1/{warning}" for warning in EXPECTED_NC_WARNINGS
    }


def test_board_source_outside_sink_range_errors(kicad_libs: KiCadLibraries) -> None:
    # A sagging 4.2 V source violates the 5V port's 4.5..5.5 V contract.
    board = board_driving(kicad_libs, Interval(4.2, 5.25))
    issues = check(board, footprints=kicad_libs)
    errors = [i for i in issues if i.severity is Severity.ERROR]
    (error,) = errors
    assert error.path == "PWR1/5V"
    assert "accepts 4.5..5.5 V" in error.message
    assert "drives 4.2..5.25 V" in error.message


def test_netlist_matches_golden(kicad_libs: KiCadLibraries) -> None:
    assert emit_netlist(capture(kicad_libs)) == GOLDEN.read_text(encoding="utf-8")


def test_netlist_byte_identical_across_runs(kicad_libs: KiCadLibraries) -> None:
    assert emit_netlist(capture(kicad_libs)) == emit_netlist(capture(kicad_libs))
