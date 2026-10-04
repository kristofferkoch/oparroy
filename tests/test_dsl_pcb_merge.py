"""Real-pcbnew validation of the settings merge (src/oparroy/dsl/pcb_merge.py).

Skipped outside the nix dev shell (same pattern as ``test_dsl_kicad10``'s
``kicad-cli`` gate): the merge runs through the flake's ``kicad-python``
wrapper. A drifted "live" board — real layout items, tampered class
values and board minimums, a GUI-style DRC exclusion — must come out of
the merge with its layout and exclusions intact and the staged
skeleton's classes, minimums, and stackup re-imposed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from design.node_board import spec
from oparroy.dsl import emit_pcb, emit_project
from oparroy.dsl.kicad_pcb import parse_board
from oparroy.dsl.kicad_pro import parse_project

KICAD_PYTHON = shutil.which("kicad-python")
KICAD_CLI = shutil.which("kicad-cli")

pytestmark = pytest.mark.skipif(
    KICAD_PYTHON is None,
    reason="kicad-python not provisioned (outside the nix dev shell)",
)

_SRC = Path(__file__).parent.parent / "src"

_FOOTPRINT_UUID = "12345678-1234-4234-8234-123456789abc"
_EXCLUSION = (
    f"clearance|1000000|2000000|{_FOOTPRINT_UUID}|00000000-0000-0000-0000-000000000000"
)
_ZONE_PAD_CONNECTION = 2
_ZONE_MIN_CLEARANCE = 0.2
_TRACK_WIDTHS = [0.0, 0.1, 0.2]
_VIA_DIMENSIONS = [{"diameter": 0.0, "drill": 0.0}]


def _write_emission(directory: Path) -> None:
    board_spec = spec()
    (directory / "oparroy-node.kicad_pcb").write_text(
        emit_pcb(board_spec), encoding="utf-8"
    )
    (directory / "oparroy-node.kicad_pro").write_text(
        emit_project(board_spec), encoding="utf-8"
    )


def _drift_live(directory: Path) -> None:
    """Give the live copy layout, GUI state, and drifted settings."""
    pcb = directory / "oparroy-node.kicad_pcb"
    layout = (
        '  (segment (start 1 1) (end 9 1) (width 0.2) (layer "F.Cu") (net 0))\n'
        f'  (footprint "Test:Dummy" (layer "F.Cu")\n'
        f'    (uuid "{_FOOTPRINT_UUID}")\n'
        "    (at 20 20 0)\n"
        '    (pad "1" smd roundrect (at 0 0) (size 0.95 1.75)\n'
        '      (layers "F.Cu" "F.Mask" "F.Paste") (roundrect_rratio 0.2)\n'
        '      (net "GND") (pintype "passive")))\n'
    )
    text = pcb.read_text(encoding="utf-8").replace("(thickness 0.8)", "(thickness 2.2)")
    pcb.write_text(text[:-2] + layout + ")\n", encoding="utf-8")
    pro = directory / "oparroy-node.kicad_pro"
    data = json.loads(pro.read_text(encoding="utf-8"))
    for net_class in data["net_settings"]["classes"]:
        if net_class["name"] == "Bypass":
            net_class["clearance"] = 0.9
        if net_class["name"] == "Default":
            net_class["clearance"] = 0.55
    data["net_settings"]["netclass_assignments"]["RX_A"] = "Power"
    data["board"]["design_settings"]["rules"]["min_track_width"] = 0.5
    data["board"]["design_settings"]["drc_exclusions"] = [
        [_EXCLUSION, "test exclusion"]
    ]
    # GUI-owned state the merge must preserve: tuned zone defaults and
    # pre-defined track/via sizes (the skeleton carries stock values).
    defaults = data["board"]["design_settings"].setdefault("defaults", {})
    zones = defaults.setdefault("zones", {})
    zones["pad_connection"] = _ZONE_PAD_CONNECTION
    zones["min_clearance"] = _ZONE_MIN_CLEARANCE
    data["board"]["design_settings"]["track_widths"] = _TRACK_WIDTHS
    data["board"]["design_settings"]["via_dimensions"] = _VIA_DIMENSIONS
    pro.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _merge(staged: Path, live: Path) -> subprocess.CompletedProcess[str]:
    assert KICAD_PYTHON is not None  # pytestmark skips the module otherwise
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{_SRC}{os.pathsep}{pythonpath}" if pythonpath else str(_SRC)
    return subprocess.run(  # noqa: S603 — runs the nix-provisioned kicad-python
        [KICAD_PYTHON, "-m", "oparroy.dsl.pcb_merge", str(staged), str(live)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture
def merged(tmp_path: Path) -> Path:
    staged = tmp_path / "staged"
    live = tmp_path / "live"
    staged.mkdir()
    live.mkdir()
    _write_emission(staged)
    _write_emission(live)
    _drift_live(live)
    result = _merge(staged, live)
    assert result.returncode == 0, result.stderr
    return live


def test_layout_and_exclusions_survive_the_merge(merged: Path) -> None:
    board = parse_board((merged / "oparroy-node.kicad_pcb").read_text(encoding="utf-8"))
    assert len(board.footprints) == 1
    assert len(board.segments) == 1
    data = json.loads((merged / "oparroy-node.kicad_pro").read_text(encoding="utf-8"))
    exclusions = data["board"]["design_settings"]["drc_exclusions"]
    assert [_EXCLUSION, "test exclusion"] in exclusions


def test_gui_owned_settings_survive_the_merge(merged: Path) -> None:
    data = json.loads((merged / "oparroy-node.kicad_pro").read_text(encoding="utf-8"))
    design_settings = data["board"]["design_settings"]
    zones = design_settings["defaults"]["zones"]
    assert zones["pad_connection"] == _ZONE_PAD_CONNECTION
    assert zones["min_clearance"] == _ZONE_MIN_CLEARANCE
    assert design_settings["track_widths"] == _TRACK_WIDTHS
    assert design_settings["via_dimensions"] == _VIA_DIMENSIONS


def test_staged_settings_are_reimposed(merged: Path) -> None:
    board_spec = spec()
    board = parse_board((merged / "oparroy-node.kicad_pcb").read_text(encoding="utf-8"))
    assert board.thickness_mm == board_spec.thickness_mm
    project = parse_project(
        (merged / "oparroy-node.kicad_pro").read_text(encoding="utf-8")
    )
    assert project.minimums == board_spec.minimums
    expected = {nc.name: nc for nc in board_spec.net_classes}
    assert {nc.name for nc in project.net_classes} == set(expected)
    for net_class in project.net_classes:
        spec_class = expected[net_class.name]
        assert net_class.clearance_mm == spec_class.clearance_mm
        assert net_class.trace_width_mm == spec_class.trace_width_mm
        assert net_class.via_dia_mm == spec_class.via_dia_mm
        assert net_class.via_drill_mm == spec_class.via_drill_mm
        assert net_class.nets == frozenset(spec_class.nets)


@pytest.mark.skipif(KICAD_CLI is None, reason="kicad-cli not provisioned")
def test_merged_board_drcs_in_kicad_cli(merged: Path) -> None:
    assert KICAD_CLI is not None  # the skipif above guards this
    report = merged / "drc.json"
    subprocess.run(  # noqa: S603 — runs the nix-provisioned kicad-cli
        [
            KICAD_CLI,
            "pcb",
            "drc",
            "-o",
            str(report),
            "--format",
            "json",
            "--severity-all",
            "--units",
            "mm",
            str(merged / "oparroy-node.kicad_pcb"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    violations = json.loads(report.read_text(encoding="utf-8"))["violations"]
    # The bare skeleton's own artifacts (no Edge.Cuts outline, a footprint
    # with no library link, the lone injected segment dangling) — anything
    # else means the merge broke the board.
    skeleton_artifacts = {"invalid_outline", "lib_footprint_issues", "track_dangling"}
    assert {v["type"] for v in violations} <= skeleton_artifacts


def test_non_skeleton_staged_board_is_refused(tmp_path: Path) -> None:
    staged = tmp_path / "staged"
    live = tmp_path / "live"
    staged.mkdir()
    live.mkdir()
    _write_emission(staged)
    _write_emission(live)
    _drift_live(staged)  # a live board in the staged slot: swapped arguments
    live_pcb = (live / "oparroy-node.kicad_pcb").read_bytes()
    live_pro = (live / "oparroy-node.kicad_pro").read_bytes()
    result = _merge(staged, live)
    assert result.returncode != 0
    assert "swapped arguments" in result.stderr
    # The live board is untouched.
    assert (live / "oparroy-node.kicad_pcb").read_bytes() == live_pcb
    assert (live / "oparroy-node.kicad_pro").read_bytes() == live_pro


def test_main_is_importable_without_pcbnew() -> None:
    # --doctest-modules covers the import; this pins that calling into the
    # merge under the uv interpreter (no pcbnew for Python 3.13) fails
    # with the plain missing-module error, not a half-initialized state.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path\n"
                "from oparroy.dsl.pcb_merge import merge_settings\n"
                "merge_settings(Path('.'), Path('.'))\n"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(_SRC)},
    )
    assert result.returncode != 0
    assert "No module named 'pcbnew'" in result.stderr
