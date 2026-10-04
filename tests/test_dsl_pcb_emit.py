"""`.kicad_pcb` skeleton and `.kicad_pro` project emitter tests."""

from __future__ import annotations

import dataclasses
import uuid

import pytest

from oparroy.dsl import (
    BoardMinimums,
    Keepout,
    LayoutRules,
    NetClassSpec,
    PcbSpec,
    PcbSpecError,
    Point,
    StackupLayer,
    check_layout,
    emit_pcb,
    emit_project,
    parse_board,
    parse_project,
)

_THICKNESS_MM = 1.6
_BYPASS_WIDTH_MM = 0.5

# Independent recomputation of the emitter's uuid namespace — if the
# emitter's scheme drifts, this golden test goes red.
_PCB_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://oparroy.koch.no/dsl/pcb")

EXPECTED_TEMPLATE = """\
(kicad_pcb (version 20240108) (generator "oparroy-dsl")
  (general
    (thickness 1.6))
  (paper "A4")
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (36 "B.SilkS" user)
    (37 "F.SilkS" user)
    (38 "B.Mask" user)
    (39 "F.Mask" user)
    (44 "Edge.Cuts" user)
  )
  (setup
    (stackup
      (layer "F.SilkS" (type "Top Silk Screen"))
      (layer "F.Paste" (type "Top Solder Paste"))
      (layer "F.Mask" (type "Top Solder Mask") (thickness 0.01))
      (layer "F.Cu" (type "copper") (thickness 0.035))
{dielectric}
      (layer "B.Cu" (type "copper") (thickness 0.035))
      (layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01))
      (layer "B.Paste" (type "Bottom Solder Paste"))
      (layer "B.SilkS" (type "Bottom Silk Screen"))
      (copper_finish "ENIG")
      (dielectric_constraints no))
  )
  (net 0 "")
  (net 1 "BYPASS")
  (net 2 "GND")
  (net 3 "SIG")
  (zone (net 0) (net_name "") (layers "F.Cu" "B.Cu")
    (uuid "{keepout_uuid}")
    (keepout
      (tracks not_allowed)
      (vias not_allowed)
      (pads not_allowed)
      (copperpour not_allowed)
      (footprints not_allowed))
    (polygon (pts (xy 51 51) (xy 59 51) (xy 59 59) (xy 51 59))))
)
"""

EXPECTED = EXPECTED_TEMPLATE.format(
    keepout_uuid=uuid.uuid5(
        _PCB_NS,
        'test-board/keepout/51,51/59,51/59,59/51,59/"F.Cu" "B.Cu"',
    ),
    dielectric=(
        '      (layer "dielectric 1" (type "core") (thickness 1.51)'
        ' (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))'
    ),
)

EXPECTED_PROJECT = """\
{
  "board": {
    "design_settings": {
      "rules": {
        "min_clearance": 0.1,
        "min_copper_edge_clearance": 0.3,
        "min_hole_clearance": 0.15,
        "min_through_hole_diameter": 0.2,
        "min_track_width": 0.1,
        "min_via_diameter": 0.45,
        "solder_mask_clearance": 0.05,
        "solder_mask_min_width": 0.1
      }
    }
  },
  "meta": {
    "filename": "test-board.kicad_pro",
    "version": 1
  },
  "net_settings": {
    "classes": [
      {
        "bus_width": 12,
        "clearance": 0.2,
        "diff_pair_gap": 0.25,
        "diff_pair_via_gap": 0.25,
        "diff_pair_width": 0.2,
        "line_style": 0,
        "microvia_diameter": 0.3,
        "microvia_drill": 0.1,
        "name": "Default",
        "pcb_color": "rgba(0, 0, 0, 0.000)",
        "schematic_color": "rgba(0, 0, 0, 0.000)",
        "track_width": 0.25,
        "via_diameter": 0.8,
        "via_drill": 0.4,
        "wire_width": 6
      },
      {
        "bus_width": 12,
        "clearance": 0.3,
        "diff_pair_gap": 0.25,
        "diff_pair_via_gap": 0.25,
        "diff_pair_width": 0.2,
        "line_style": 0,
        "microvia_diameter": 0.3,
        "microvia_drill": 0.1,
        "name": "Power",
        "pcb_color": "rgba(0, 0, 0, 0.000)",
        "schematic_color": "rgba(0, 0, 0, 0.000)",
        "track_width": 0.5,
        "via_diameter": 1.0,
        "via_drill": 0.5,
        "wire_width": 6
      }
    ],
    "meta": {
      "version": 3
    },
    "netclass_assignments": {
      "BYPASS": "Power",
      "GND": "Default",
      "SIG": "Default"
    }
  }
}
"""


def spec() -> PcbSpec:
    return PcbSpec(
        name="test-board",
        thickness_mm=_THICKNESS_MM,
        stackup=(
            StackupLayer("F.SilkS", "Top Silk Screen"),
            StackupLayer("F.Paste", "Top Solder Paste"),
            StackupLayer("F.Mask", "Top Solder Mask", thickness_mm=0.01),
            StackupLayer("F.Cu", "copper", thickness_mm=0.035),
            StackupLayer(
                "dielectric 1",
                "core",
                thickness_mm=1.51,
                material="FR4",
                epsilon_r=4.5,
                loss_tangent=0.02,
            ),
            StackupLayer("B.Cu", "copper", thickness_mm=0.035),
            StackupLayer("B.Mask", "Bottom Solder Mask", thickness_mm=0.01),
            StackupLayer("B.Paste", "Bottom Solder Paste"),
            StackupLayer("B.SilkS", "Bottom Silk Screen"),
        ),
        net_classes=(
            NetClassSpec(
                name="Power",
                clearance_mm=0.3,
                trace_width_mm=_BYPASS_WIDTH_MM,
                via_dia_mm=1.0,
                via_drill_mm=0.5,
                nets=("BYPASS",),
                description="bypass-path copper",
            ),
            NetClassSpec(
                name="Default",
                clearance_mm=0.2,
                trace_width_mm=0.25,
                via_dia_mm=0.8,
                via_drill_mm=0.4,
                nets=("SIG", "GND"),
            ),
        ),
        keepouts=(
            Keepout(
                polygon=(
                    Point(51, 51),
                    Point(59, 51),
                    Point(59, 59),
                    Point(51, 59),
                ),
            ),
        ),
        minimums=BoardMinimums(
            min_clearance=0.1,
            min_track_width=0.1,
            min_via_diameter=0.45,
            min_through_hole_diameter=0.2,
            min_copper_edge_clearance=0.3,
            min_hole_clearance=0.15,
            solder_mask_clearance=0.05,
            solder_mask_min_width=0.1,
        ),
    )


def shuffled(spec_: PcbSpec) -> PcbSpec:
    """Return the same spec with every ordered collection reversed."""
    return dataclasses.replace(
        spec_,
        stackup=tuple(reversed(spec_.stackup)),
        net_classes=tuple(
            dataclasses.replace(nc, nets=tuple(reversed(nc.nets)))
            for nc in reversed(spec_.net_classes)
        ),
    )


def test_emit_matches_golden() -> None:
    assert emit_pcb(spec()) == EXPECTED


def test_emission_is_byte_identical_across_runs() -> None:
    assert emit_pcb(spec()) == emit_pcb(spec())


def test_emission_independent_of_declaration_order() -> None:
    # The stackup is physical order — it is emitted as declared; only
    # the unordered collections (classes, nets) sort.
    reordered = dataclasses.replace(
        spec(),
        net_classes=tuple(
            dataclasses.replace(nc, nets=tuple(reversed(nc.nets)))
            for nc in reversed(spec().net_classes)
        ),
    )
    assert emit_pcb(reordered) == EXPECTED


def test_project_emission_matches_golden() -> None:
    assert emit_project(spec()) == EXPECTED_PROJECT


def test_project_emission_is_byte_identical_across_runs() -> None:
    assert emit_project(spec()) == emit_project(spec())


def test_project_emission_independent_of_declaration_order() -> None:
    assert emit_project(shuffled(spec())) == EXPECTED_PROJECT


def test_round_trip_through_parser() -> None:
    board = parse_board(emit_pcb(spec()))
    assert board.thickness_mm == _THICKNESS_MM
    assert board.copper_layers == ("F.Cu", "B.Cu")
    assert board.nets == {"": 0, "BYPASS": 1, "GND": 2, "SIG": 3}
    keepouts = [zone for zone in board.zones if zone.keepout]
    assert len(keepouts) == 1
    assert keepouts[0].polygon == (
        Point(51, 51),
        Point(59, 51),
        Point(59, 59),
        Point(51, 59),
    )


def test_project_round_trip_through_parser() -> None:
    project = parse_project(emit_project(spec()))
    by_name = {nc.name: nc for nc in project.net_classes}
    assert by_name["Power"].trace_width_mm == _BYPASS_WIDTH_MM
    assert by_name["Power"].nets == frozenset({"BYPASS"})
    assert by_name["Default"].nets == frozenset({"GND", "SIG"})
    assert project.assignments == {
        "BYPASS": "Power",
        "GND": "Default",
        "SIG": "Default",
    }
    assert project.minimums == spec().minimums


def test_emitted_skeleton_passes_stackup_check() -> None:
    board = parse_board(emit_pcb(spec()))
    rules = LayoutRules(copper_layers=2, thickness_mm=_THICKNESS_MM)
    assert check_layout(board, rules) == []


def test_check_layout_reads_classes_from_the_project() -> None:
    board = parse_board(
        '(kicad_pcb (layers) (net 1 "BYPASS")'
        ' (segment (start 0 0) (end 10 0) (width 0.25) (layer "F.Cu") (net 1)))'
    )
    project = parse_project(emit_project(spec()))
    issues = check_layout(board, LayoutRules(), project)
    assert [i.message for i in issues] == [
        ("segment on net 'BYPASS' is 0.25 mm wide, net class 'Power' requires 0.5 mm")
    ]


def test_four_layer_stackup() -> None:
    four = PcbSpec(
        name="ci-board",
        thickness_mm=1.6,
        net_classes=(),
        copper_layers=("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"),
    )
    board = parse_board(emit_pcb(four))
    assert board.copper_layers == ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
    assert check_layout(board, LayoutRules(copper_layers=4)) == []


def test_unknown_copper_layer_raises() -> None:
    bad = PcbSpec(
        name="bad",
        thickness_mm=1.6,
        net_classes=(),
        copper_layers=("F.Cu", "Top.Cu"),
    )
    with pytest.raises(PcbSpecError, match="unknown copper layer"):
        emit_pcb(bad)
