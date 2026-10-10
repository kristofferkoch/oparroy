"""ngspice emitter tests: golden output, bindings, bench compatibility.

The bench test (``test_existing_benches_pass_against_dsl_emitted_dut``)
is the spice-emitter acceptance proof: the hand-written bench decks of
``circuits/watchdog-chargepump/`` run unmodified — stimulus and
``.meas`` assertions stay in the benches — against the DSL-emitted DUT
netlist, via ``scripts/sim-run`` exactly as the hand-written capture is
run. It needs the nix dev shell (KiCad libraries for the capture,
ngspice for the run).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from oparroy.dsl import (
    Bat54s,
    Capacitor,
    Circuit,
    DefinitionError,
    Resistor,
    emit_spice,
)

if TYPE_CHECKING:
    from conftest import StubSymbols
    from oparroy.dsl import KiCadLibraries

REPO = Path(__file__).resolve().parent.parent
BENCH_DIR = REPO / "circuits" / "watchdog-chargepump"
SIM_RUN = REPO / "scripts" / "sim-run"
BENCHES = ["tb_engage", "tb_missed_pulse", "tb_glitch"]

PUMP_MODELS = {"BAT54S": "d(is=200n n=1.0 rs=5 tt=1n bv=30)"}

GOLDEN_PUMP = """\
* pump — ngspice DUT netlist emitted by the oparroy DSL; regenerate, do not edit.
.subckt pump ka sel GND
.model BAT54S d(is=200n n=1.0 rs=5 tt=1n bv=30)
Cp kap x 22n
Cs sel GND 10n
D1A GND x BAT54S
D1K x sel BAT54S
Rb sel GND 47k
Rs ka kap 220
.ends pump
"""


def build_pump(symbols: StubSymbols) -> Circuit:
    """Build the §4 charge pump on stub symbols; ports ka/sel/GND, like design/."""
    c = Circuit("pump", symbols)
    ka = c.port("ka")
    sel = c.port("sel")
    gnd = c.port("GND")
    kap = c.net("kap")
    x = c.net("x")
    c.part("Rs", Resistor("220", a=ka, b=kap))
    c.part("Cp", Capacitor("22n", a=kap, b=x))
    c.part("D1", Bat54s(anode=gnd, com=x, cathode=sel))
    c.part("Cs", Capacitor("10n", a=sel, b=gnd))
    c.part("Rb", Resistor("47k", a=sel, b=gnd))
    return c


def test_emit_matches_golden(symbols: StubSymbols) -> None:
    assert emit_spice(build_pump(symbols), models=PUMP_MODELS) == GOLDEN_PUMP


def test_emission_is_byte_identical_across_runs(symbols: StubSymbols) -> None:
    assert emit_spice(build_pump(symbols), models=PUMP_MODELS) == emit_spice(
        build_pump(symbols), models=PUMP_MODELS
    )


def test_ports_keep_declaration_order(symbols: StubSymbols) -> None:
    rendered = emit_spice(build_pump(symbols), models=PUMP_MODELS)
    assert ".subckt pump ka sel GND" in rendered


def test_subckt_name_defaults_to_circuit_name(symbols: StubSymbols) -> None:
    rendered = emit_spice(build_pump(symbols), models=PUMP_MODELS)
    assert ".subckt pump " in rendered
    renamed = emit_spice(build_pump(symbols), name="wd_chargepump", models=PUMP_MODELS)
    assert ".subckt wd_chargepump ka sel GND" in renamed
    assert ".ends wd_chargepump" in renamed


def test_bat54s_expands_to_two_diodes_around_com(symbols: StubSymbols) -> None:
    # Series pair: anode(1)->com(3) is the A element, com(3)->cathode(2)
    # the K element — the orientation the capture's keyword pins fix.
    rendered = emit_spice(build_pump(symbols), models=PUMP_MODELS)
    assert "D1A GND x BAT54S" in rendered
    assert "D1K x sel BAT54S" in rendered


def test_unreferenced_models_are_not_emitted(symbols: StubSymbols) -> None:
    rendered = emit_spice(
        build_pump(symbols),
        models={**PUMP_MODELS, "2N2222": "npn(is=1e-14)"},
    )
    assert "2N2222" not in rendered


def test_model_sort_order_is_deterministic(symbols: StubSymbols) -> None:
    models = {"BAT54S": "d(is=200n)", "bat34": "d(is=1n)"}
    c = Circuit("m", symbols)
    a = c.net("a")
    b = c.net("b")
    c.part("D1", Bat54s(anode=a, com=b, cathode=b, value="BAT54S"))
    c.part("D2", Bat54s(anode=a, com=b, cathode=b, value="bat34"))
    rendered = emit_spice(c, models=models)
    # natural_key ordering: "bat34" sorts before "BAT54S" (34 < 54).
    assert rendered.index(".model bat34") < rendered.index(".model BAT54S")


def test_unknown_symbol_raises(symbols: StubSymbols) -> None:
    c = Circuit("t", symbols)
    c.net("a")
    conn = c.part("J1", symbol="Stub:CONN6", value="conn")
    c.connect("a", conn[1])
    with pytest.raises(DefinitionError, match="no spice binding"):
        emit_spice(c)


def test_missing_value_raises(symbols: StubSymbols) -> None:
    c = Circuit("t", symbols)
    r1 = c.part("R1", symbol="Device:R", value=None)
    c.net("a")
    c.net("b")
    c.connect("a", r1[1])
    c.connect("b", r1[2])
    with pytest.raises(DefinitionError, match="value"):
        emit_spice(c)


def test_unconnected_pin_raises(symbols: StubSymbols) -> None:
    c = Circuit("t", symbols)
    r1 = c.part("R1", symbol="Device:R", value="1k")
    a = c.net("a")
    c.connect(a, r1[1])
    with pytest.raises(DefinitionError, match="not connected"):
        emit_spice(c)


def test_referenced_model_without_definition_raises(symbols: StubSymbols) -> None:
    with pytest.raises(DefinitionError, match="BAT54S"):
        emit_spice(build_pump(symbols))


def test_power_symbols_are_excluded(symbols: StubSymbols) -> None:
    c = Circuit("pwr", symbols)
    rail = c.net("rail")
    gnd = c.net("gnd")
    c.part("R1", Resistor("1k", a=rail, b=gnd))
    marker = c.part("#1", symbol="power:+3V3", value=None, footprint=None)
    c.connect(rail, marker[1])
    rendered = emit_spice(c)
    assert "+3V3" not in rendered
    assert "R1 rail gnd 1k" in rendered


def test_hierarchy_flattens_with_prefixed_names(symbols: StubSymbols) -> None:
    def cell(circuit: Circuit) -> None:
        a = circuit.port("a")
        b = circuit.port("b")
        circuit.part("R1", Resistor("1k", a=a, b=b))

    board = Circuit("board", symbols)
    in_n = board.port("in")
    out_n = board.port("out")
    board.instance("U1", cell, a=in_n, b=out_n)
    rendered = emit_spice(board)
    assert ".subckt board in out" in rendered
    # Flattened names carry '/' — ngspice accepts them verbatim.
    assert "RU1/R1 in out 1k" in rendered


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not provisioned")
def test_existing_benches_pass_against_dsl_emitted_dut(
    kicad_libs: KiCadLibraries, tmp_path: Path
) -> None:
    from design.watchdog_chargepump import SPICE_MODELS, capture  # noqa: PLC0415

    dut = emit_spice(capture(kicad_libs), name="wd_chargepump", models=SPICE_MODELS)
    # Mirror the circuits/ layout so the benches' relative includes
    # (../lib/*.spi, watchdog-chargepump.cir) resolve: the emitted DUT
    # takes the hand-written file's place, unmodified benches around it.
    bench = tmp_path / "watchdog-chargepump"
    bench.mkdir()
    (bench / "watchdog-chargepump.cir").write_text(dut, encoding="utf-8")
    shutil.copytree(REPO / "circuits" / "lib", tmp_path / "lib")
    for tb in BENCHES:
        shutil.copy(BENCH_DIR / f"{tb}.cir", bench)
        result = subprocess.run(  # noqa: S603 — runs the repo's own sim-run script
            [str(SIM_RUN), str(tmp_path / "work" / tb), str(bench / f"{tb}.cir")],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"{tb}: {result.stdout}{result.stderr}"
        assert "PASS" in result.stdout
