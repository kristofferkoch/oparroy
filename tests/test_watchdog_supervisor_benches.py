"""watchdog-supervisor bench equivalence: numeric pins on §4's record.

The rejected window-watchdog candidate is kept as the quantified
record of what its money would have bought (DESIGN.md §4). Those
numbers — engage timeout, bounded blip, early-edge latch speed,
glitch-train engage slip — live only in the benches; this test runs
the three decks through ``scripts/sim-run``'s mirror mode (the same
path the meson ``sim-*`` targets use) and pins the MEAS echoes each
deck emits at both select-threshold band edges. Needs the nix dev
shell (ngspice).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BENCH_DIR = REPO / "circuits" / "watchdog-supervisor"
SIM_RUN = REPO / "scripts" / "sim-run"

VTH_EDGES = ("0.99", "2.31")

pytestmark = pytest.mark.skipif(
    shutil.which("ngspice") is None, reason="ngspice not provisioned"
)


def run_bench(tmp_path: Path, tb: str) -> str:
    """Run one supervisor bench; return the sim log."""
    work = tmp_path / "work" / tb
    result = subprocess.run(  # noqa: S603 — runs the repo's own sim-run script
        [str(SIM_RUN), str(work), str(BENCH_DIR / f"{tb}.cir")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"{tb}: {result.stdout}{result.stderr}"
    assert "PASS" in result.stdout
    return (work / "sim.log").read_text(encoding="utf-8")


def _meas(log: str, tb: str, key: str) -> dict[str, float]:
    """Pull one MEAS key's value at each vth band edge; both must echo."""
    values = {}
    for vth in VTH_EDGES:
        match = re.search(rf"MEAS vth={re.escape(vth)} .*{key}=(\S+)", log)
        assert match, f"{tb}: no MEAS vth={vth} ... {key}= line"
        values[vth] = float(match.group(1))
    return values


def _pin_both(values: dict[str, float], recorded: float, tol: float, what: str) -> None:
    for vth, value in values.items():
        assert abs(value - recorded) <= tol, (
            f"{what} at vth={vth}: {value} vs recorded {recorded} (±{tol})"
            " — DESIGN.md §4 drift"
        )


def test_tb_engage_reproduces_the_timeout(tmp_path: Path) -> None:
    log = run_bench(tmp_path, "tb_engage")
    # DESIGN.md §4: timeout engage is 1.49 ms after the last strobe.
    _pin_both(
        _meas(log, "tb_engage", "timeout_engage_ms"),
        1.4934,
        0.02,
        "engage timeout (ms)",
    )


def test_tb_missed_pulse_reproduces_the_bounded_blip(tmp_path: Path) -> None:
    log = run_bench(tmp_path, "tb_missed_pulse")
    # DESIGN.md §4: the trip lands 1.49 ms after the last good strobe;
    # one dropped strobe costs a bounded 1.51 ms self-recovering blip.
    _pin_both(
        _meas(log, "tb_missed_pulse", "timeout_trip_ms"),
        1.4934,
        0.02,
        "trip delay (ms)",
    )
    _pin_both(
        _meas(log, "tb_missed_pulse", "blip_ms"),
        1.5068,
        0.02,
        "blip width (ms)",
    )


def test_tb_glitch_reproduces_the_latch_and_slip(tmp_path: Path) -> None:
    log = run_bench(tmp_path, "tb_glitch")
    # DESIGN.md §4: an early edge latches the fault ~0.2 µs after the
    # offending edge; the glitch train slips the engage to 1.70 ms.
    _pin_both(
        _meas(log, "tb_glitch", "early_latch_us"),
        0.22,
        0.05,
        "early-edge latch (µs)",
    )
    _pin_both(
        _meas(log, "tb_glitch", "glitch_engage_ms"),
        1.7002,
        0.02,
        "glitch-train engage (ms)",
    )
