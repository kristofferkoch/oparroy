"""phy-segment bench equivalence: the tb_* decks against the DSL DUT.

The port's acceptance proof: the hand-written bench decks of
``circuits/phy-segment/`` run unmodified against the DSL-emitted DUT
(``design/phy_segment.py``) through ``scripts/sim-run``'s mirror mode —
the same path the meson ``sim-*`` targets use — and the run must
**reproduce the measured numbers of DESIGN.md §2**, not just PASS:
tb_decode's SUMMARY margins and period window, tb_noise's worst
high-time error, and tb_fault's 1 nF static-park settle are parsed
out of the sim log and pinned with tolerances. Needs the nix dev
shell (KiCad libraries for the capture, ngspice for the run).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from oparroy.dsl import emit_spice

if TYPE_CHECKING:
    from oparroy.dsl import KiCadLibraries

REPO = Path(__file__).resolve().parent.parent
BENCH_DIR = REPO / "circuits" / "phy-segment"
SIM_RUN = REPO / "scripts" / "sim-run"

# DESIGN.md §2's measured block (tb_decode): every cell >= 178 ns from
# the decode midpoint at the center band (a +78.2 ns margin over the
# 100 ns contract), +58.1 at the high band, -29.0 at the low band,
# +45.7 at VDD/2; cell periods land in 1249-1251 ns.
MARGIN_CENTER_NS = 78.2
MARGIN_HIGH_NS = 58.1
MARGIN_LOW_NS = -29.0
MARGIN_VDD2_NS = 45.7
MARGIN_TOL_NS = 3.0
PERIOD_MIN_NS = 1247
PERIOD_MAX_NS = 1253
# tb_noise runs its 12-deck sweep; DESIGN.md §2 records a worst
# high-time error of ~1.2 ns under ringing and ±250 mV-class crosstalk
# at ±13 mV offset.
NOISE_RUNS = 12
NOISE_MAXERR_NS = 1.2
NOISE_MAXERR_TOL_NS = 0.3
# tb_fault applies the fault at tf = 6.5 µs; DESIGN.md §2 records the
# severed line parking the comparator static <= 33 µs even at 1 nF.
FAULT_TF_US = 6.5
SETTLE_1N_RUNS = 2
SETTLE_1N_VOFF_LO_US = 32.6
SETTLE_1N_VOFF_HI_US = 31.9
SETTLE_TOL_US = 2.0

pytestmark = pytest.mark.skipif(
    shutil.which("ngspice") is None, reason="ngspice not provisioned"
)


def run_bench(kicad_libs: KiCadLibraries, tmp_path: Path, tb: str) -> str:
    """Run one bench against the DSL-emitted DUT; return the sim log."""
    from design.phy_segment import (  # noqa: PLC0415
        SPICE_INCLUDES,
        SPICE_PARAMS,
        capture,
    )

    dut = tmp_path / "phy-segment.cir"
    dut.write_text(
        emit_spice(
            capture(kicad_libs),
            name="phy_segment",
            includes=SPICE_INCLUDES,
            params=SPICE_PARAMS,
        ),
        encoding="utf-8",
    )
    work = tmp_path / "work" / tb
    result = subprocess.run(  # noqa: S603 — runs the repo's own sim-run script
        [str(SIM_RUN), str(work), str(BENCH_DIR / f"{tb}.cir"), str(dut)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"{tb}: {result.stdout}{result.stderr}"
    assert "PASS" in result.stdout
    return (work / "sim.log").read_text(encoding="utf-8")


def _pin(value: float, recorded: float, tol: float, what: str) -> None:
    assert abs(value - recorded) <= tol, (
        f"{what}: {value} vs recorded {recorded} (±{tol}) — DESIGN.md §2 drift"
    )


def test_tb_decode_reproduces_the_decode_margins(
    kicad_libs: KiCadLibraries, tmp_path: Path
) -> None:
    log = run_bench(kicad_libs, tmp_path, "tb_decode")
    match = re.search(
        r"SUMMARY worst margins ns: center=(\S+) high=(\S+) low=(\S+) "
        r"vdd2=(\S+) period_ns=(\S+) to (\S+)",
        log,
    )
    assert match, "tb_decode echoed no SUMMARY line"
    center, high, low, vdd2, pmin, pmax = (float(g) for g in match.groups())
    _pin(center, MARGIN_CENTER_NS, MARGIN_TOL_NS, "center-band worst margin (ns)")
    _pin(high, MARGIN_HIGH_NS, MARGIN_TOL_NS, "high-band worst margin (ns)")
    _pin(low, MARGIN_LOW_NS, MARGIN_TOL_NS, "low-band worst margin (ns)")
    _pin(vdd2, MARGIN_VDD2_NS, MARGIN_TOL_NS, "VDD/2 worst margin (ns)")
    assert PERIOD_MIN_NS <= pmin <= pmax <= PERIOD_MAX_NS, (
        f"period window {pmin}..{pmax} ns"
    )


def test_tb_noise_reproduces_the_high_time_error(
    kicad_libs: KiCadLibraries, tmp_path: Path
) -> None:
    log = run_bench(kicad_libs, tmp_path, "tb_noise")
    maxerrs = [float(m) for m in re.findall(r"maxerr_ns=(\S+)", log)]
    assert len(maxerrs) == NOISE_RUNS, (
        f"expected {NOISE_RUNS} noise runs, got {len(maxerrs)}"
    )
    _pin(
        max(maxerrs), NOISE_MAXERR_NS, NOISE_MAXERR_TOL_NS, "worst high-time error (ns)"
    )


def test_tb_fault_reproduces_the_static_park(
    kicad_libs: KiCadLibraries, tmp_path: Path
) -> None:
    log = run_bench(kicad_libs, tmp_path, "tb_fault")
    # §2's contract is asserted inside the deck (static park, settle
    # bounds, zero late edges) — but the 1b settle time is also a
    # measured number; pin it at both voff edges.
    settles = {}
    for match in re.finditer(
        r"PASS 1b cseg=1n voff=(\S+): rxout_static_low_at=(\S+)", log
    ):
        voff, tset = match.groups()
        settles[voff] = float(tset) * 1e6 - FAULT_TF_US
    assert len(settles) == SETTLE_1N_RUNS, (
        f"expected {SETTLE_1N_RUNS} cseg=1n 1b runs, got {settles}"
    )
    _pin(
        settles["-13m"],
        SETTLE_1N_VOFF_LO_US,
        SETTLE_TOL_US,
        "1b 1n settle, voff=-13m (µs)",
    )
    _pin(
        settles["13m"],
        SETTLE_1N_VOFF_HI_US,
        SETTLE_TOL_US,
        "1b 1n settle, voff=+13m (µs)",
    )
    assert "FAIL" not in log
