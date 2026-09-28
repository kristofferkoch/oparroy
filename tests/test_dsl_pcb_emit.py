"""`.kicad_pcb` skeleton emitter tests: golden output and round-trip."""

from __future__ import annotations

import uuid

import pytest

from oparroy.dsl import (
    Keepout,
    LayoutRules,
    NetClassSpec,
    PcbSpec,
    PcbSpecError,
    Point,
    check_layout,
    emit_pcb,
    parse_board,
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
    (net_class "Default" ""
      (clearance 0.2)
      (trace_width 0.25)
      (via_dia 0.8)
      (via_drill 0.4)
      (add_net "GND")
      (add_net "SIG"))
    (net_class "Power" "bypass-path copper"
      (clearance 0.3)
      (trace_width 0.5)
      (via_dia 1)
      (via_drill 0.5)
      (add_net "BYPASS"))
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
)


def spec() -> PcbSpec:
    return PcbSpec(
        name="test-board",
        thickness_mm=1.6,
        net_classes=(
            NetClassSpec(
                name="Power",
                clearance_mm=0.3,
                trace_width_mm=0.5,
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
    )


def test_emit_matches_golden() -> None:
    assert emit_pcb(spec()) == EXPECTED


def test_emission_is_byte_identical_across_runs() -> None:
    assert emit_pcb(spec()) == emit_pcb(spec())


def test_emission_independent_of_declaration_order() -> None:
    reordered = PcbSpec(
        name=spec().name,
        thickness_mm=spec().thickness_mm,
        net_classes=tuple(reversed(spec().net_classes)),
        keepouts=spec().keepouts,
    )
    assert emit_pcb(reordered) == EXPECTED


def test_round_trip_through_parser() -> None:
    board = parse_board(emit_pcb(spec()))
    assert board.thickness_mm == _THICKNESS_MM
    assert board.copper_layers == ("F.Cu", "B.Cu")
    by_name = {nc.name: nc for nc in board.net_classes}
    assert by_name["Power"].trace_width_mm == _BYPASS_WIDTH_MM
    assert by_name["Power"].nets == frozenset({"BYPASS"})
    assert by_name["Default"].nets == frozenset({"GND", "SIG"})
    assert board.nets == {"": 0, "BYPASS": 1, "GND": 2, "SIG": 3}
    keepouts = [zone for zone in board.zones if zone.keepout]
    assert len(keepouts) == 1
    assert keepouts[0].polygon == (
        Point(51, 51),
        Point(59, 51),
        Point(59, 59),
        Point(51, 59),
    )


def test_emitted_skeleton_passes_stackup_check() -> None:
    board = parse_board(emit_pcb(spec()))
    rules = LayoutRules(copper_layers=2, thickness_mm=_THICKNESS_MM)
    assert check_layout(board, rules) == []


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
