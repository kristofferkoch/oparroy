"""`.kicad_pcb` parser tests: the pass-board fixture and edge cases."""

from __future__ import annotations

import pytest

from oparroy.dsl import Board, EdgeKind, PcbError, Point, parse_board
from oparroy.dsl.sexpr import SexpError

_THICKNESS_MM = 1.6
_DEFAULT_CLEARANCE_MM = 0.2
_DEFAULT_WIDTH_MM = 0.25
_BYPASS_WIDTH_MM = 0.5
_VIA_SIZE_MM = 0.8
_MOUNTING_HOLES = 4


def test_rejects_non_board_document() -> None:
    with pytest.raises(PcbError, match=r"not a .kicad_pcb document"):
        parse_board('(kicad_symbol_lib (symbol "R"))')


def test_rejects_malformed_sexpr() -> None:
    with pytest.raises(SexpError):
        parse_board("(kicad_pcb (layers")


def test_stackup(board_pass: Board) -> None:
    assert board_pass.thickness_mm == _THICKNESS_MM
    assert board_pass.copper_layers == ("F.Cu", "B.Cu")
    assert board_pass.silkscreen_layers == ("B.SilkS", "F.SilkS")


def test_net_table(board_pass: Board) -> None:
    assert board_pass.nets == {"": 0, "BYPASS": 1, "GND": 2, "SIG": 3}


def test_net_classes() -> None:
    """Board-file net classes: the pre-KiCad-10 fallback the parser keeps."""
    board = parse_board(
        "(kicad_pcb (layers)"
        " (setup"
        '  (net_class "Default" "" (clearance 0.2) (trace_width 0.25)'
        '   (add_net "GND") (add_net "SIG"))'
        '  (net_class "Power" "" (trace_width 0.5) (add_net "BYPASS")))'
        ' (net 1 "BYPASS") (net 2 "GND") (net 3 "SIG"))'
    )
    by_name = {nc.name: nc for nc in board.net_classes}
    assert set(by_name) == {"Default", "Power"}
    default = by_name["Default"]
    assert default.trace_width_mm == _DEFAULT_WIDTH_MM
    assert default.clearance_mm == _DEFAULT_CLEARANCE_MM
    assert default.nets == frozenset({"GND", "SIG"})
    assert by_name["Power"].nets == frozenset({"BYPASS"})
    power = board.net_class_of("BYPASS")
    assert power is not None
    assert power.name == "Power"
    assert board.net_class_of("UNROUTE") is None


def test_footprints_and_pads(board_pass: Board) -> None:
    by_ref = {fp.ref: fp for fp in board_pass.footprints}
    assert set(by_ref) == {"J1", "J2", "SW1", "D1", "D2", "H1", "H2", "H3", "H4"}
    assert by_ref["J1"].at == Point(60, 60)
    assert by_ref["J1"].lib == "Connector:CONN_1x06"
    assert [(pad.number, pad.net) for pad in by_ref["SW1"].pads] == [
        ("1", "BYPASS"),
        ("2", "BYPASS"),
        ("3", "SIG"),
    ]
    assert by_ref["H1"].pads[0].kind == "np_thru_hole"


def test_legacy_fp_text_reference() -> None:
    board = parse_board(
        '(kicad_pcb (layers) (footprint "Lib:Name" (layer "F.Cu") (at 1 2 0)'
        ' (fp_text reference "R7" (at 0 0 0) (layer "F.SilkS"))))'
    )
    assert board.footprints[0].ref == "R7"


def test_segments_resolve_net_codes(board_pass: Board) -> None:
    by_net = {}
    for segment in board_pass.segments:
        by_net.setdefault(segment.net, []).append(segment)
    assert {net: len(segs) for net, segs in by_net.items()} == {
        "BYPASS": 2,
        "GND": 1,
        "SIG": 1,
    }
    bypass_length = sum(seg.length for seg in by_net["BYPASS"])
    assert bypass_length == pytest.approx(26.0)
    assert all(seg.width == _BYPASS_WIDTH_MM for seg in by_net["BYPASS"])


def test_vias(board_pass: Board) -> None:
    assert len(board_pass.vias) == 1
    via = board_pass.vias[0]
    assert via.net == "GND"
    assert via.size == _VIA_SIZE_MM
    assert via.layers == ("F.Cu", "B.Cu")


def test_silkscreen_texts(board_pass: Board) -> None:
    texts = {t.text for t in board_pass.texts if t.layer == "F.SilkS"}
    assert {"oparroy", "test-board", "Kristoffer Koch", "2026-09-28", "v0.1.0"} <= texts


def test_serial_box(board_pass: Board) -> None:
    boxes = [r for r in board_pass.rects if r.layer == "F.SilkS"]
    assert len(boxes) == 1
    assert boxes[0].filled
    assert boxes[0].area == pytest.approx(90.0)


def test_outline(board_pass: Board) -> None:
    outline = [e for e in board_pass.edges if e.layer == "Edge.Cuts"]
    kinds = sorted(edge.kind for edge in outline)
    assert kinds == [EdgeKind.ARC] * 4 + [EdgeKind.LINE] * 4
    arcs = [edge for edge in outline if edge.kind is EdgeKind.ARC]
    assert all(arc.mid is not None for arc in arcs)


def test_keepout_zones(board_pass: Board) -> None:
    keepouts = [zone for zone in board_pass.zones if zone.keepout]
    assert len(keepouts) == _MOUNTING_HOLES
    assert all(len(zone.polygon) == _MOUNTING_HOLES for zone in keepouts)
    assert keepouts[0].layers == ("F.Cu", "B.Cu")


def test_power_and_mixed_inner_layers_count_as_copper() -> None:
    board = parse_board(
        '(kicad_pcb (layers (0 "F.Cu" signal) (1 "In1.Cu" power)'
        ' (2 "In2.Cu" mixed) (31 "B.Cu" signal)))'
    )
    assert board.copper_layers == ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")


def test_kicad10_named_nets() -> None:
    """KiCad 10's native format (20260206): net names inline, no code table."""
    board = parse_board(
        '(kicad_pcb (version 20260206) (generator "pcbnew") (layers)'
        ' (footprint "Lib:Name" (layer "F.Cu") (at 1 2 0)'
        '  (property "Reference" "J1" (at 0 0 0) (layer "F.SilkS"))'
        '  (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu")'
        '   (net "GND")))'
        ' (segment (start 0 0) (end 1 1) (width 0.2) (layer "F.Cu")'
        '  (net "BYPASS"))'
        ' (via (at 2 2) (size 0.8) (drill 0.4) (layers "F.Cu" "B.Cu")'
        '  (net "SIG"))'
        ' (segment (start 3 3) (end 4 4) (width 0.2) (layer "F.Cu") (net "")))'
    )
    assert board.nets == {}
    assert board.footprints[0].pads[0].net == "GND"
    assert [segment.net for segment in board.segments] == ["BYPASS", ""]
    assert board.vias[0].net == "SIG"


def test_malformed_net_code_raises_pcb_error() -> None:
    with pytest.raises(PcbError, match="expected an integer for net code"):
        parse_board(
            '(kicad_pcb (layers) (net 1 "GND")'
            ' (segment (start 0 0) (end 1 1) (width 0.2) (layer "F.Cu") (net xx)))'
        )


def test_unknown_content_is_tolerated() -> None:
    board = parse_board(
        '(kicad_pcb (version 20240108) (generator "future-kicad")'
        " (layers)"
        ' (future_feature (with (nested "data")))'
        " (gr_line (start 0 0) (end 1 0) (stroke (width 0.05) (type solid))"
        '  (layer "Edge.Cuts") (width 0.05)))'
    )
    assert len(board.edges) == 1


def test_board_without_setup_or_general() -> None:
    board = parse_board("(kicad_pcb (layers))")
    assert board.thickness_mm is None
    assert board.net_classes == ()
    assert board.net_class_of("GND") is None
