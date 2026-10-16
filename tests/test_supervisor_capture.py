"""Supervisor capture tests (need the nix-provisioned libraries).

The golden netlist at tests/golden/supervisor.net is what pcbnew
ingests; regenerate it from the dev shell with:

    python -m design.supervisor > tests/golden/supervisor.net
"""

from __future__ import annotations

from pathlib import Path

from design.supervisor import Supervisor, capture
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

GOLDEN = Path(__file__).parent / "golden" / "supervisor.net"

#: The spare GPIOs (GPIO0..3 — the tail of the reclaimed
#: debug-transport reservation — and GPIO23..29) plus SWCLK/SWDIO,
#: reporting by pin number on U1 — deliberate NCs, and the list pins
#: them so nothing else hides among them. GPIO14..17 bind the
#: pot-override PWM ports and are no longer NCs.
EXPECTED_NC_WARNINGS = {
    f"U1.{pin} is not connected"
    for pin in (
        "2",
        "3",
        "4",
        "5",
        "24",
        "25",
        "35",
        "36",
        "37",
        "38",
        "39",
        "40",
        "41",
    )
}

#: The decoupling set (AN §2.1.2/§2.1.3): ten 100 nF (six IOVDD,
#: USB_VDD, ADC_AVDD, two DVDD) plus the two mandatory 1 µF VREG caps.
DECOUPLING_COUNT = 12
DECOUPLING_100N_COUNT = 10
DECOUPLING_1U_COUNT = 2

SIGNAL_PORTS = {
    "usb_dp",
    "usb_dm",
    "usb_boot",
    "swio",
    "tap_rx",
    "tap_tx",
    "tap_comp",
    "tap_led",
    "srclk",
    "sdo",
    "sdi",
    "commit",
    "oe_n",
    "dbg_rx",
    "pot_pwm1",
    "pot_pwm3",
    "pot_pwm5",
    "pot_pwm7",
    "TX_A",
    "RX_B",
    "RX_A",
    "TX_B",
}


def board_driving(kicad_libs: KiCadLibraries, v3v3_source: Interval) -> Circuit:
    """Build a board driving the supervisor: RAIL_3V3 sources ``v3v3_source``."""
    board = Circuit("board", kicad_libs)
    v3v3 = board.port("RAIL_3V3", source=Limits(voltage=v3v3_source))
    gnd = board.port("GND")
    signals = {name: board.port(name) for name in SIGNAL_PORTS}
    board.instance("SUP1", Supervisor(), **{"3V3": v3v3, "GND": gnd, **signals})
    return board


def nets_of(circuit: Circuit) -> dict[str, set[str]]:
    """Net name -> member pins as 'ref.number'."""
    return {
        name: {f"{p.part.ref}.{p.number}" for p in net.pins}
        for name, net in circuit.nets.items()
    }


def test_capture_declares_its_ports(kicad_libs: KiCadLibraries) -> None:
    circuit = capture(kicad_libs)
    assert set(circuit.ports) == {"3V3", "GND"} | SIGNAL_PORTS
    assert not circuit.port_arrays


def test_flash_and_strap_wiring(kicad_libs: KiCadLibraries) -> None:
    # AN §2.2: QSPI straight to the flash, the 1 kΩ BOOTSEL resistor to
    # usb_boot and the 10 kΩ /CS-tracks-VCC pull-up to 3V3 on QSPI_SS.
    nets = nets_of(capture(kicad_libs))
    assert nets["qspi_ss"] == {"U1.56", "U2.1", "R1.1", "R2.1"}
    assert nets["qspi_sclk"] == {"U1.52", "U2.6"}
    assert nets["qspi_sd0"] == {"U1.53", "U2.5"}
    assert nets["qspi_sd1"] == {"U1.55", "U2.2"}
    assert nets["qspi_sd2"] == {"U1.54", "U2.3"}
    assert nets["qspi_sd3"] == {"U1.51", "U2.7"}
    assert nets["usb_boot"] == {"R1.2"}


def test_crystal_wiring(kicad_libs: KiCadLibraries) -> None:
    # AN §2.3: crystal across XIN and the xosc net, the 1 kΩ series
    # resistor between XOUT and xosc, 15 pF load caps to GND, case
    # pins 2/4 grounded.
    nets = nets_of(capture(kicad_libs))
    assert nets["xin"] == {"U1.20", "X1.1", "C2.1"}
    assert nets["xout"] == {"U1.21", "R5.1"}
    assert nets["xosc"] == {"X1.3", "R5.2", "C3.1"}
    assert {"X1.2", "X1.4"} <= nets["GND"]


def test_usb_series_termination(kicad_libs: KiCadLibraries) -> None:
    # AN §2.4.1: 27 Ω between each port and the chip pin.
    nets = nets_of(capture(kicad_libs))
    assert nets["usb_dp"] == {"R6.1"}
    assert nets["usb_dm"] == {"R7.1"}
    assert nets["usb_dp_r"] == {"R6.2", "U1.47"}
    assert nets["usb_dm_r"] == {"R7.2", "U1.46"}


def test_dvdd_net(kicad_libs: KiCadLibraries) -> None:
    # AN §2.1.3: VREG_OUT feeds both DVDD pads; the on-chip LDO's 1 µF
    # and the per-pad 100 nF sit on the net.
    nets = nets_of(capture(kicad_libs))
    assert nets["dvdd"] == {
        "U1.23",
        "U1.50",
        "U1.45",
        "C_dvdd23.1",
        "C_dvdd50.1",
        "C_vreg_out.1",
    }


def test_gpio_binding_matches_pin_map(kicad_libs: KiCadLibraries) -> None:
    # design/supervisor_pins.py's binding, in netlist form.
    nets = nets_of(capture(kicad_libs))
    assert nets["ring_txa"] == {"U1.6", "Rat.1"}
    assert nets["ring_rxb"] == {"U1.7", "Rbr.2"}
    assert nets["ring_rxa"] == {"U1.8", "Rar.2"}
    assert nets["ring_txb"] == {"U1.9", "Rbt.1"}
    assert nets["tap_rx"] == {"U1.11"}
    assert nets["tap_tx"] == {"U1.12"}
    assert nets["tap_comp"] == {"U1.13"}
    assert nets["tap_led"] == {"U1.14"}
    assert nets["swio"] == {"U1.15"}
    assert nets["dbg_rx"] == {"U1.16"}
    assert nets["srclk"] == {"U1.29"}
    assert nets["sdo"] == {"U1.30"}
    assert nets["sdi"] == {"U1.31"}
    assert nets["commit"] == {"U1.32"}
    assert nets["oe_n"] == {"U1.34"}
    assert nets["pot_pwm1"] == {"U1.17"}
    assert nets["pot_pwm3"] == {"U1.18"}
    assert nets["pot_pwm5"] == {"U1.27"}
    assert nets["pot_pwm7"] == {"U1.28"}


def test_ring_port_protection(kicad_libs: KiCadLibraries) -> None:
    # The §7 terminal-protection contract, mirrored from the node PHY:
    # 470 Ω series per wire; connector-adjacent TVS only on the
    # originator pair (the board's one connectorized segment) — the
    # drain faces board copper (instrumented-ci.md §2).
    circuit = capture(kicad_libs)
    nets = nets_of(circuit)
    assert nets["TX_A"] == {"Rat.2", "Dat.1"}
    assert nets["RX_B"] == {"Rbr.1", "Dbr.1"}
    assert nets["RX_A"] == {"Rar.1"}
    assert nets["TX_B"] == {"Rbt.2"}
    assert {"Dat.2", "Dbr.2"} <= nets["GND"]
    for ref in ("Rat", "Rar", "Rbt", "Rbr"):
        assert circuit.parts[ref].value == "470"


def test_part_values(kicad_libs: KiCadLibraries) -> None:
    circuit = capture(kicad_libs)
    parts = circuit.parts
    assert parts["R1"].value == "1k"  # BOOTSEL strap (AN §2.2)
    assert parts["R2"].value == "10k"  # /CS-tracks-VCC pull-up
    assert parts["R5"].value == "1k"  # XOUT anti-overdrive
    assert parts["R6"].value == "27"
    assert parts["R7"].value == "27"
    assert parts["C2"].value == "15p"
    assert parts["C3"].value == "15p"
    decoupling = [p for ref, p in parts.items() if ref.startswith(("C_", "C_io"))]
    assert len(decoupling) == DECOUPLING_COUNT
    assert sum(p.value == "100n" for p in decoupling) == DECOUPLING_100N_COUNT
    assert sum(p.value == "1u" for p in decoupling) == DECOUPLING_1U_COUNT


def test_capture_checks_clean(kicad_libs: KiCadLibraries) -> None:
    circuit = capture(kicad_libs)
    issues = check(circuit, footprints=kicad_libs)
    assert [i for i in issues if i.severity is Severity.ERROR] == []
    assert {i.message for i in issues} == EXPECTED_NC_WARNINGS
    raise_on_errors(issues)


def test_board_covering_port_ranges_checks_clean(kicad_libs: KiCadLibraries) -> None:
    # Range containment against the power tree's contract: ci_power's
    # 3V3 source band (3.2..3.4 V) fits the supervisor's 3V3 accept
    # (3.0..3.6 V). The NC warnings flatten along, path-prefixed.
    board = board_driving(kicad_libs, Interval(3.2, 3.4))
    issues = check(board, footprints=kicad_libs)
    assert [i for i in issues if i.severity is Severity.ERROR] == []
    assert {i.message for i in issues} == {
        f"SUP1/{warning}" for warning in EXPECTED_NC_WARNINGS
    }


def test_board_source_outside_sink_range_errors(kicad_libs: KiCadLibraries) -> None:
    # A 5 V rail violates the 3V3 port's 3.0..3.6 V contract — there is
    # no 5 V net anywhere past ci_power's regulator input.
    board = board_driving(kicad_libs, Interval(4.5, 5.5))
    issues = check(board, footprints=kicad_libs)
    errors = [i for i in issues if i.severity is Severity.ERROR]
    (error,) = errors
    assert error.path == "SUP1/3V3"
    assert "accepts 3.0..3.6 V" in error.message
    assert "drives 4.5..5.5 V" in error.message


def test_netlist_matches_golden(kicad_libs: KiCadLibraries) -> None:
    assert emit_netlist(capture(kicad_libs)) == GOLDEN.read_text(encoding="utf-8")


def test_netlist_byte_identical_across_runs(kicad_libs: KiCadLibraries) -> None:
    assert emit_netlist(capture(kicad_libs)) == emit_netlist(capture(kicad_libs))
