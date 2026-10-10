"""The DSL tutorial's worked example, kept executable.

docs/dsl-tutorial.md quotes this file section by section; pytest
exercises every quoted block, so the tutorial cannot drift from the
API. The circuit is a two-channel RC low-pass filter board: one
subcircuit (``RcFilter``), two instances, ports with limit ranges,
validation, annotation, and emission — against the stub symbol and
footprint tables from conftest, so no KiCad libraries are needed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from oparroy.dsl import (
    Capacitor,
    Circuit,
    DefinitionError,
    Interval,
    Limits,
    Resistor,
    Severity,
    Subcircuit,
    annotate,
    apply_annotation,
    check,
    emit_netlist,
    raise_on_errors,
    to_dot,
)

if TYPE_CHECKING:
    from conftest import StubFootprints, StubSymbols
    from oparroy.dsl import SymbolTable


class R0603(Resistor):
    """Resistors from the 0603 bin: the footprint is the class default.

    The real bins resolve from the parts DB (``design/parts_db.py``);
    these stub footprints stand in so the example runs without the
    KiCad libraries.
    """

    default_footprint = "StubFP:R_0603"


class C0603(Capacitor):
    """Capacitors from the 0603 bin."""

    default_footprint = "StubFP:C_0603"


class RcFilter(Subcircuit):
    """One RC low-pass channel: ``in`` → Rs → ``out``, Cs to GND.

    The ports carry limit ranges as interface contracts: ``in``
    accepts 0..3.3 V from the signal source, ``out`` drives 0..3.3 V
    toward the ADC. An instantiating parent's declared ranges are
    checked for containment against these.
    """

    def capture(self, circuit: Circuit) -> None:
        """Build the channel: ports in/out/GND, parts Rs/Cs."""
        in_ = circuit.port("in", sink=Limits(voltage=Interval(0, 3.3)))
        out = circuit.port("out", source=Limits(voltage=Interval(0, 3.3)))
        gnd = circuit.port("GND")
        circuit.part("Rs", R0603("4k7", a=in_, b=out))
        circuit.part("Cs", C0603("100n", a=out, b=gnd))


def capture(symbols: SymbolTable) -> Circuit:
    """Build the tutorial board: two filter channels sharing one GND."""
    board = Circuit("filter-board", symbols)
    ain1 = board.port("ain1", source=Limits(voltage=Interval(0, 3.3)))
    ain2 = board.port("ain2", source=Limits(voltage=Interval(0, 3.3)))
    adc1 = board.port("adc1", sink=Limits(voltage=Interval(0, 3.6)))
    adc2 = board.port("adc2", sink=Limits(voltage=Interval(0, 3.6)))
    gnd = board.port("GND")
    # "in" is a Python keyword, so that port binds via **-unpacking.
    board.instance("FILT1", RcFilter(), out=adc1, GND=gnd, **{"in": ain1})
    board.instance("FILT2", RcFilter(), out=adc2, GND=gnd, **{"in": ain2})
    return board


def test_board_checks_clean(symbols: StubSymbols, footprints: StubFootprints) -> None:
    assert check(capture(symbols), footprints=footprints) == []


def test_flatten_prefixes_instance_names(symbols: StubSymbols) -> None:
    flat = capture(symbols).flatten()
    assert sorted(flat.parts) == ["FILT1/Cs", "FILT1/Rs", "FILT2/Cs", "FILT2/Rs"]
    # Each port net merges into the net its instance bound it to; the
    # internal names are gone.
    assert "FILT1/in" not in flat.nets
    assert {pin.part.ref for pin in flat.nets["ain1"].pins} == {"FILT1/Rs"}
    assert {pin.part.ref for pin in flat.nets["GND"].pins} == {
        "FILT1/Cs",
        "FILT2/Cs",
    }


def test_binding_drift_raises_at_capture(symbols: StubSymbols) -> None:
    board = Circuit("drift", symbols)
    ain = board.port("ain")
    adc = board.port("adc")
    gnd = board.port("GND")
    with pytest.raises(DefinitionError, match="no ports"):
        board.instance("FILT1", RcFilter(), out=adc, GND=gnd, inp=ain)


def test_range_containment_fires(symbols: StubSymbols) -> None:
    board = Circuit("narrow-adc", symbols)
    ain = board.port("ain", source=Limits(voltage=Interval(0, 3.3)))
    adc = board.port("adc", sink=Limits(voltage=Interval(0, 1.8)))
    gnd = board.port("GND")
    board.instance("FILT1", RcFilter(), out=adc, GND=gnd, **{"in": ain})
    errors = [i for i in check(board) if i.severity is Severity.ERROR]
    assert len(errors) == 1
    assert errors[0].check == "range-containment"
    assert errors[0].path == "FILT1/out"


def test_waiver_degrades_the_error(symbols: StubSymbols) -> None:
    board = Circuit("narrow-adc", symbols)
    ain = board.port("ain", source=Limits(voltage=Interval(0, 3.3)))
    adc = board.port("adc", sink=Limits(voltage=Interval(0, 1.8)))
    gnd = board.port("GND")
    board.instance("FILT1", RcFilter(), out=adc, GND=gnd, **{"in": ain})
    board.waive(
        "range-containment",
        "FILT1/out",
        reason="the ADC pin is 1V8-only by design; the divider guarantees the level",
    )
    issues = check(board)
    assert [issue.severity for issue in issues] == [Severity.WAIVED]
    raise_on_errors(issues)


def test_netlist_emission(symbols: StubSymbols) -> None:
    board = capture(symbols)
    # Pre-annotation, comp refs are the hierarchical capture paths.
    assert '(comp (ref "FILT1/Rs")' in emit_netlist(board)
    # Annotation maps capture paths to refdes; emission for the board
    # runs on the annotated IR.
    netlist = emit_netlist(apply_annotation(board, annotate(board)))
    for ref in ("R1", "R2", "C1", "C2"):
        assert f'(comp (ref "{ref}")' in netlist
    assert '(comp (ref "FILT1' not in netlist
    assert '(name "GND")' in netlist


def test_dot_view(symbols: StubSymbols) -> None:
    dot = to_dot(capture(symbols))
    assert '"FILT1/Rs"' in dot
    assert '"net:adc1"' in dot
