"""Real-pcbnew ingest validation of the emitted skeleton (DESIGN.md §7).

Skipped outside the nix dev shell (same gate as ``test_dsl_pcb_merge``):
the dev shell puts nixpkgs' pcbnew on ``PYTHONPATH`` and the project pins
the same Python 3.14 it is built for. Where ``test_dsl_pcb_emit`` proves
the skeleton round-trips through our own parser, this module proves real
KiCad agrees: pcbnew loads the emitted pair, reports the spec's physical
contract back, and a load/save cycle — what happens when a human opens
the skeleton in KiCad and saves — leaves the stackup, net classes,
assignments, and board minimums intact for :func:`parse_board` and
:func:`parse_project` to read.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from design.node_board import spec
from oparroy.dsl import (
    Keepout,
    PcbSpec,
    Point,
    emit_pcb,
    emit_project,
)
from oparroy.dsl.kicad_pcb import parse_board
from oparroy.dsl.kicad_pro import parse_project
from oparroy.dsl.layout_check import LayoutRules, check_layout

PCBNEW = importlib.util.find_spec("pcbnew")

pytestmark = pytest.mark.skipif(
    PCBNEW is None,
    reason="pcbnew not importable (outside the nix dev shell)",
)

_NODE_BOARD = (
    Path(__file__).parent.parent / "boards" / "node" / "oparroy-node.kicad_pcb"
)

_NM_PER_MM = 1_000_000


def _write_emission(directory: Path) -> None:
    board_spec = spec()
    (directory / "oparroy-node.kicad_pcb").write_text(
        emit_pcb(board_spec), encoding="utf-8"
    )
    (directory / "oparroy-node.kicad_pro").write_text(
        emit_project(board_spec), encoding="utf-8"
    )


def _spec_nets(board_spec: PcbSpec) -> set[str]:
    return {net for net_class in board_spec.net_classes for net in net_class.nets}


def test_pcbnew_loads_the_emitted_skeleton(tmp_path: Path) -> None:
    import pcbnew  # noqa: PLC0415 — dev-shell only, see the module docstring

    board_spec = spec()
    _write_emission(tmp_path)

    board = pcbnew.LoadBoard(str(tmp_path / "oparroy-node.kicad_pcb"))

    assert board.GetCopperLayerCount() == len(board_spec.copper_layers)
    assert board.GetDesignSettings().GetBoardThickness() == round(
        board_spec.thickness_mm * _NM_PER_MM
    )
    net_names = {net.GetNetname() for net in board.GetNetsByName().values()}
    assert _spec_nets(board_spec) <= net_names


def test_pcbnew_round_trip_preserves_stackup_and_nets(tmp_path: Path) -> None:
    import pcbnew  # noqa: PLC0415 — dev-shell only, see the module docstring

    board_spec = spec()
    _write_emission(tmp_path)
    board = pcbnew.LoadBoard(str(tmp_path / "oparroy-node.kicad_pcb"))
    saved = tmp_path / "round-trip.kicad_pcb"
    assert pcbnew.SaveBoard(str(saved), board)

    reread = parse_board(saved.read_text(encoding="utf-8"))

    rules = LayoutRules(
        copper_layers=len(board_spec.copper_layers),
        thickness_mm=board_spec.thickness_mm,
    )
    assert check_layout(reread, rules) == []
    # KiCad 10's native save drops the net-code table — the skeleton's
    # nets are referenced by no copper item, so they vanish from the
    # board file. The net->class contract survives in the saved
    # .kicad_pro; see test_pcbnew_round_trip_preserves_net_classes.
    assert set(reread.nets) == set()


def test_pcbnew_round_trip_preserves_net_classes(tmp_path: Path) -> None:
    import pcbnew  # noqa: PLC0415 — dev-shell only, see the module docstring

    board_spec = spec()
    _write_emission(tmp_path)
    board = pcbnew.LoadBoard(str(tmp_path / "oparroy-node.kicad_pcb"))
    assert pcbnew.SaveBoard(str(tmp_path / "round-trip.kicad_pcb"), board)

    project = parse_project(
        (tmp_path / "round-trip.kicad_pro").read_text(encoding="utf-8")
    )

    by_name = {net_class.name: net_class for net_class in project.net_classes}
    assert set(by_name) >= {net_class.name for net_class in board_spec.net_classes}
    for net_class in board_spec.net_classes:
        parsed = by_name[net_class.name]
        assert parsed.clearance_mm == pytest.approx(net_class.clearance_mm)
        assert parsed.trace_width_mm == pytest.approx(net_class.trace_width_mm)
        assert parsed.via_dia_mm == pytest.approx(net_class.via_dia_mm)
        assert parsed.via_drill_mm == pytest.approx(net_class.via_drill_mm)
        assert parsed.nets == frozenset(net_class.nets)
    assert project.minimums == board_spec.minimums
    expected_assignments = {
        net: net_class.name
        for net_class in board_spec.net_classes
        for net in net_class.nets
    }
    assert expected_assignments.items() <= project.assignments.items()


def test_pcbnew_ingests_keepout_zones(tmp_path: Path) -> None:
    import pcbnew  # noqa: PLC0415 — dev-shell only, see the module docstring

    keepout_spec = PcbSpec(
        name="keepout-probe",
        thickness_mm=0.8,
        net_classes=(),
        keepouts=(
            Keepout(
                polygon=(
                    Point(0, 0),
                    Point(10, 0),
                    Point(10, 10),
                    Point(0, 10),
                )
            ),
        ),
    )
    pcb = tmp_path / "keepout-probe.kicad_pcb"
    pcb.write_text(emit_pcb(keepout_spec), encoding="utf-8")

    board = pcbnew.LoadBoard(str(pcb))

    zones = list(board.Zones())
    assert len(zones) == 1
    zone = zones[0]
    assert zone.GetIsRuleArea()
    assert zone.GetDoNotAllowTracks()
    assert zone.GetDoNotAllowVias()
    assert zone.GetDoNotAllowPads()
    # KiCad 10's SWIG binding names the copper-pour flag ZoneFills.
    assert zone.GetDoNotAllowZoneFills()
    assert zone.GetDoNotAllowFootprints()
    layers = {board.GetLayerName(layer) for layer in zone.GetLayerSet().Seq()}
    assert layers == {"F.Cu", "B.Cu"}


def test_pcbnew_loads_the_committed_node_board() -> None:
    import pcbnew  # noqa: PLC0415 — dev-shell only, see the module docstring

    board = pcbnew.LoadBoard(str(_NODE_BOARD))
    parsed = parse_board(_NODE_BOARD.read_text(encoding="utf-8"))

    assert len(list(board.GetFootprints())) == len(parsed.footprints)
    # The committed board is KiCad-10 native: no net-code table, net
    # names inline on items — so compare the parser's per-item net
    # names against pcbnew's net set as ground truth.
    pcbnew_nets = {net.GetNetname() for net in board.GetNetsByName().values()} - {""}
    parsed_nets = (
        {segment.net for segment in parsed.segments}
        | {arc.net for arc in parsed.arcs}
        | {via.net for via in parsed.vias}
        | {
            pad.net
            for footprint in parsed.footprints
            for pad in footprint.pads
            if pad.net
        }
    )
    assert parsed_nets == pcbnew_nets


def test_pcbnew_loads_the_committed_ci_skeleton() -> None:
    """The CI board's seed: 4-layer, 1.6 mm, the Power-class nets (§6)."""
    import pcbnew  # noqa: PLC0415 — dev-shell only, see the module docstring

    from design.ci_pcb import spec as ci_spec  # noqa: PLC0415

    ci_pcb = Path(__file__).parent.parent / "boards" / "ci" / "oparroy-ci.kicad_pcb"
    board = pcbnew.LoadBoard(str(ci_pcb))
    board_spec = ci_spec()

    # The §6 4-layer build: signal/GND plane/power/signal.
    assert board_spec.copper_layers == ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
    assert board.GetCopperLayerCount() == len(board_spec.copper_layers)
    assert board.GetDesignSettings().GetBoardThickness() == round(
        board_spec.thickness_mm * _NM_PER_MM
    )
    net_names = {net.GetNetname() for net in board.GetNetsByName().values()}
    assert _spec_nets(board_spec) <= net_names
