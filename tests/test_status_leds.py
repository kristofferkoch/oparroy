"""StatusLeds subcircuit tests: the §4.1 drive-state contract in simulation.

The bench at circuits/status-leds/tb_status_leds.cir asserts pin high
/ pin low / Hi-Z against the DSL-emitted DUT via ``scripts/sim-run``
(skipped without ngspice). This is the executable form of the truth
table that caught Dd's anode-on-GND in netlist review (2026-09-30).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from oparroy.dsl import KiCadLibraries, emit_spice

REPO = Path(__file__).parent.parent
SIM_RUN = REPO / "scripts" / "sim-run"
BENCH = REPO / "circuits" / "status-leds" / "tb_status_leds.cir"


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not provisioned")
def test_drive_states(kicad_libs: KiCadLibraries, tmp_path: Path) -> None:
    from design.status_leds import SPICE_MODELS, capture  # noqa: PLC0415

    dut = emit_spice(capture(kicad_libs), name="status_leds", models=SPICE_MODELS)
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
