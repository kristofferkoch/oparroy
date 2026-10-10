"""Real-KiCad validation: the emitted seed opens and DRCs in ``kicad-cli``.

Skipped outside the nix dev shell (same pattern as the ``kicad_libs``
fixture). This is the regression net for the KiCad 10 format facts:
``kicad-cli pcb upgrade`` rejects ``net_class`` in a board's setup, so
the emitted skeleton must parse clean, and the DRC must enforce the
project's per-class clearances and the board minimums.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from design.node_board import spec
from oparroy.dsl import emit_pcb, emit_project

if TYPE_CHECKING:
    from pathlib import Path

KICAD_CLI = shutil.which("kicad-cli")

pytestmark = pytest.mark.skipif(
    KICAD_CLI is None,
    reason="kicad-cli not provisioned (outside the nix dev shell)",
)


def _write_project(tmp_path: Path) -> Path:
    board_spec = spec()
    pcb = tmp_path / "oparroy-node.kicad_pcb"
    pcb.write_text(emit_pcb(board_spec), encoding="utf-8")
    (tmp_path / "oparroy-node.kicad_pro").write_text(
        emit_project(board_spec), encoding="utf-8"
    )
    return pcb


def _run(*args: str) -> None:
    assert KICAD_CLI is not None  # pytestmark skips the module otherwise
    subprocess.run(  # noqa: S603 — runs the nix-provisioned kicad-cli
        [KICAD_CLI, *args], check=True, capture_output=True, text=True
    )


def test_kicad_upgrade_accepts_the_skeleton(tmp_path: Path) -> None:
    _run("pcb", "upgrade", str(_write_project(tmp_path)))


def test_kicad_drc_enforces_the_spec(tmp_path: Path) -> None:
    pcb = _write_project(tmp_path)
    # Two Bypass-class segments (nets 2 and 3 in the emitted net list):
    # 0.05 mm edge-to-edge against the class's 0.3 mm clearance, and
    # 0.05 mm wide against the 0.1 mm board minimum. A footprint pad
    # 0.075 mm off an NPTH edge violates the 0.15 mm hole-clearance
    # floor (the part-over-hole decision) — holes are only
    # checked against pads, not tracks, and only when the pad carries
    # a net.
    violating = (
        '  (segment (start 1 1) (end 9 1) (width 0.05) (layer "F.Cu") (net 2))\n'
        '  (segment (start 1 1.1) (end 9 1.1) (width 0.05) (layer "F.Cu") (net 3))\n'
        '  (footprint "Test:LedHole" (layer "F.Cu")\n'
        '    (uuid "12345678-1234-4234-8234-123456789abc")\n'
        "    (at 20 20 0)\n"
        '    (pad "" np_thru_hole oval (at 0 0) (size 1.8 2.4)\n'
        '      (drill oval 1.8 2.4) (layers "*.Cu" "*.Mask"))\n'
        '    (pad "1" smd roundrect (at 1.45 0) (size 0.95 1.75)\n'
        '      (layers "F.Cu" "F.Mask" "F.Paste") (roundrect_rratio 0.2)\n'
        '      (net "GND") (pintype "passive")))\n'
    )
    text = pcb.read_text(encoding="utf-8")
    pcb.write_text(text[:-2] + violating + ")\n", encoding="utf-8")
    report = tmp_path / "drc.json"
    _run(
        "pcb",
        "drc",
        "-o",
        str(report),
        "--format",
        "json",
        "--severity-all",
        "--units",
        "mm",
        str(pcb),
    )
    violations = json.loads(report.read_text(encoding="utf-8"))["violations"]
    clearances = [v for v in violations if v["type"] == "clearance"]
    assert any("Bypass" in v["description"] for v in clearances), violations
    widths = [
        v
        for v in violations
        if v["type"] == "track_width"
        and "board setup constraints min width" in v["description"]
    ]
    assert widths, violations
    hole_clearances = [v for v in violations if v["type"] == "hole_clearance"]
    assert hole_clearances, violations
