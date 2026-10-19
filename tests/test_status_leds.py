"""StatusLeds subcircuit tests: the §4.1 drive-state contract in simulation.

The bench at circuits/status-leds/tb_status_leds.cir asserts pin high
/ pin low / Hi-Z against the DSL-emitted DUT via ``scripts/sim-run``
(skipped without ngspice). This is the executable form of the truth
table that caught Dd's anode-on-GND in netlist review.

The series resistors are value generators: solved standalone from the
block's declared 3.3 V rail, and from the parent's bound rail when the
block sits in a board.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import StubSymbols
from oparroy.dsl import (
    Circuit,
    KiCadLibraries,
    PowerDomainKind,
    ValueRange,
    emit_spice,
    solve,
)

REPO = Path(__file__).parent.parent
SIM_RUN = REPO / "scripts" / "sim-run"
BENCH = REPO / "circuits" / "status-leds" / "tb_status_leds.cir"


def test_series_resistors_size_from_the_declared_rail() -> None:
    from design.status_leds import StatusLeds  # noqa: PLC0415

    circuit = Circuit("status-leds", StubSymbols())
    StatusLeds().capture(circuit)
    report = solve(circuit)
    assert report.issues == []
    values = {ref: circuit.parts[ref].value for ref in ("Rp", "Rw", "Rs")}
    assert values == {"Rp": "1k", "Rw": "1k", "Rs": "470"}


def test_series_resistors_follow_a_bound_rail() -> None:
    from design.status_leds import StatusLeds  # noqa: PLC0415

    board = Circuit("board", StubSymbols())
    rail = board.net("rail")
    board.power_domain(
        rail,
        kind=PowerDomainKind.ALWAYS,
        voltage=ValueRange.around(3.6, 0.01),
    )
    board.instance(
        "SL1",
        StatusLeds(),
        v3v3=rail,
        gnd=board.net("gnd"),
        led_work=board.net("led_work"),
        led_seg=board.net("led_seg"),
    )
    report = solve(board)
    assert report.issues == []
    parts = board.instances["SL1"].circuit.parts
    # 3.6 V, not the block's local 3.3 V assumption: (3.6-2.0)/1.3 mA
    # and (3.6-2.1)/2.5 mA resolve to the nearest stocked E24 values.
    assert parts["Rp"].value == "1k2"
    assert parts["Rw"].value == "1k2"
    assert parts["Rs"].value == "620"


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not provisioned")
def test_drive_states(kicad_libs: KiCadLibraries, tmp_path: Path) -> None:
    from design.status_leds import SPICE_MODELS, capture  # noqa: PLC0415

    circuit = capture(kicad_libs)
    solve(circuit)
    dut = emit_spice(circuit, name="status_leds", models=SPICE_MODELS)
    # Mirror the circuits/ layout so the bench's relative include
    # (status-leds.cir) resolves: the emitted DUT takes the place a
    # hand-written DUT file would hold.
    bench = tmp_path / "status-leds"
    bench.mkdir()
    (bench / "status-leds.cir").write_text(dut, encoding="utf-8")
    shutil.copy(BENCH, bench)
    result = subprocess.run(  # noqa: S603 — runs the repo's own sim-run script
        [str(SIM_RUN), str(tmp_path / "work"), str(bench / BENCH.name)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    assert "PASS" in result.stdout
