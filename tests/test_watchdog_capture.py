"""Watchdog-chargepump capture tests (need the nix-provisioned libraries).

The golden netlist at tests/golden/watchdog-chargepump.net is the T7a
proof artifact; regenerate it from the dev shell with:

    python -m design.watchdog_chargepump > tests/golden/watchdog-chargepump.net
"""

from __future__ import annotations

from pathlib import Path

from design.watchdog_chargepump import WatchdogChargePump, capture
from oparroy.dsl import (
    Circuit,
    Interval,
    KiCadLibraries,
    Limits,
    Severity,
    check,
    emit_netlist,
    raise_on_errors,
    to_dot,
)

GOLDEN = Path(__file__).parent / "golden" / "watchdog-chargepump.net"

# Rs(2) + Cp(2) + D1(3) + Cs(2) + Rb(2) — every pin connected.
EXPECTED_PIN_COUNT = 11


def board_driving(kicad_libs: KiCadLibraries, ka_source: Interval) -> Circuit:
    """Build a board driving the watchdog: KA sources ``ka_source``, SEL accepts."""
    board = Circuit("board", kicad_libs)
    ka = board.port("KA", source=Limits(voltage=ka_source))
    sel = board.port("SEL", sink=Limits(voltage=Interval(0, 3.6)))
    gnd = board.port("GND")
    board.instance("WD1", WatchdogChargePump(), ka=ka, sel=sel, GND=gnd)
    return board


def test_capture_matches_handwritten_cir(kicad_libs: KiCadLibraries) -> None:
    # Same topology as circuits/watchdog-chargepump/watchdog-chargepump.cir:
    # Rs ka->kap, Cp kap->x, BAT54S gnd/x/sel, Cs sel->GND, Rb sel->GND.
    circuit = capture(kicad_libs)
    nets = {
        name: {f"{p.part.ref}.{p.number}" for p in net.pins}
        for name, net in circuit.nets.items()
    }
    assert nets == {
        "ka": {"Rs.1"},
        "kap": {"Rs.2", "Cp.1"},
        "x": {"Cp.2", "D1.3"},
        "sel": {"D1.2", "Cs.1", "Rb.1"},
        "GND": {"D1.1", "Cs.2", "Rb.2"},
    }


def test_bat54s_orientation_by_pin_name(kicad_libs: KiCadLibraries) -> None:
    # Direction-sensitive: BAT54S pins are 1=A (clamp anode), 2=K (pump
    # cathode), 3=COM (shared middle). A pin-number swap keeps the net
    # membership above plausible, so pin the orientation by symbol name.
    circuit = capture(kicad_libs)
    d1_names = {
        name: {p.name for p in net.pins if p.part.ref == "D1"}
        for name, net in circuit.nets.items()
    }
    assert d1_names["x"] == {"COM"}
    assert d1_names["sel"] == {"K"}
    assert d1_names["GND"] == {"A"}


def test_capture_declares_its_ports(kicad_libs: KiCadLibraries) -> None:
    circuit = capture(kicad_libs)
    assert set(circuit.ports) == {"ka", "sel", "GND"}


def test_capture_checks_clean(kicad_libs: KiCadLibraries) -> None:
    circuit = capture(kicad_libs)
    issues = check(circuit, footprints=kicad_libs)
    # ka/sel/GND are ports now — dangling is their job (T7ba).
    assert issues == []
    raise_on_errors(issues)


def test_board_covering_port_ranges_checks_clean(kicad_libs: KiCadLibraries) -> None:
    # T8: the board's 0..3.3 V driver fits the watchdog's ka contract
    # (0..3.6 V), and sel's 0..3.3 V output fits the board's accept.
    board = board_driving(kicad_libs, Interval(0, 3.3))
    assert check(board, footprints=kicad_libs) == []


def test_board_source_outside_sink_range_errors(kicad_libs: KiCadLibraries) -> None:
    # A 5 V keep-alive driver violates ka's 0..3.6 V contract.
    board = board_driving(kicad_libs, Interval(0, 5))
    issues = check(board, footprints=kicad_libs)
    errors = [i for i in issues if i.severity is Severity.ERROR]
    (error,) = errors
    assert error.path == "WD1/ka"
    assert "accepts 0..3.6 V" in error.message
    assert "drives 0..5 V" in error.message


def test_netlist_matches_golden(kicad_libs: KiCadLibraries) -> None:
    assert emit_netlist(capture(kicad_libs)) == GOLDEN.read_text(encoding="utf-8")


def test_netlist_byte_identical_across_runs(kicad_libs: KiCadLibraries) -> None:
    assert emit_netlist(capture(kicad_libs)) == emit_netlist(capture(kicad_libs))


def test_dot_covers_every_pin(kicad_libs: KiCadLibraries) -> None:
    dot = to_dot(capture(kicad_libs))
    edges = [line for line in dot.splitlines() if " -- " in line]
    assert len(edges) == EXPECTED_PIN_COUNT
    assert "BAT54S" in dot
    assert '"net:sel" [label="sel"];' in dot
