"""Layout property-checker tests: each contract red/green on the fixtures."""

from __future__ import annotations

import dataclasses

from oparroy.dsl import (
    AdjacencyRule,
    Board,
    BypassRule,
    LayoutRules,
    Project,
    check_layout,
    parse_board,
)

_CORNER_COUNT = 4


def full_rules() -> LayoutRules:
    """Build the whole contract, satisfied by the pass-board fixture."""
    return LayoutRules(
        copper_layers=2,
        thickness_mm=1.6,
        required_silkscreen=(
            r"oparroy",
            r"test-board",
            r"Kristoffer Koch",
            r"\d{4}-\d{2}-\d{2}",
            r"v\d+\.\d+\.\d+",
        ),
        min_serial_box_mm2=80,
        min_corner_radius_mm=3,
        trace_budgets_mm={"BYPASS": 30, "SIG": 10, "GND": 10},
        min_mounting_holes=4,
        mounting_hole_keepout=True,
        adjacency=(
            AdjacencyRule(
                name="status LED at connector (§4.1)",
                source=r"D2",
                target=r"J\d+",
                max_distance_mm=5,
            ),
        ),
        required_footprints=(r"D1",),
        bypass=(BypassRule(net="BYPASS", allowed_refs=(r"J\d+", r"SW\d+")),),
    )


def test_pass_board_meets_full_contract(
    board_pass: Board, project_pass: Project
) -> None:
    assert check_layout(board_pass, full_rules(), project_pass) == []


def test_empty_rules_find_nothing(board_pass: Board) -> None:
    assert check_layout(board_pass, LayoutRules()) == []


def test_stackup_layer_count_violation(board_pass: Board) -> None:
    rules = dataclasses.replace(full_rules(), copper_layers=4)
    issues = check_layout(board_pass, rules)
    assert [i.message for i in issues] == [
        "stackup has 2 copper layers (F.Cu, B.Cu), the contract wants 4"
    ]


def test_stackup_thickness_violation(board_pass: Board) -> None:
    rules = dataclasses.replace(full_rules(), thickness_mm=1.0)
    issues = check_layout(board_pass, rules)
    assert [i.message for i in issues] == [
        "board thickness 1.6 mm is outside 1.0 ± 0.1 mm"
    ]


def test_thickness_missing_declaration() -> None:
    board = parse_board("(kicad_pcb (layers))")
    rules = LayoutRules(thickness_mm=1.6)
    issues = check_layout(board, rules)
    assert [i.message for i in issues] == [
        "board declares no thickness (general/thickness)"
    ]


def test_trace_budget_violation(board_pass: Board) -> None:
    rules = dataclasses.replace(full_rules(), trace_budgets_mm={"BYPASS": 25})
    issues = check_layout(board_pass, rules)
    assert [i.message for i in issues] == [
        "net 'BYPASS' routes 26.00 mm of copper, over the 25 mm budget"
    ]


def test_net_class_width_violation() -> None:
    board = parse_board(
        "(kicad_pcb (layers)"
        ' (setup (net_class "Default" "" (trace_width 0.25) (add_net "SIG")))'
        ' (net 1 "SIG")'
        ' (segment (start 0 0) (end 10 0) (width 0.15) (layer "F.Cu") (net 1)))'
    )
    issues = check_layout(board, LayoutRules())
    assert [i.message for i in issues] == [
        "segment on net 'SIG' is 0.15 mm wide, net class 'Default' requires 0.25 mm"
    ]


def test_net_class_via_violation() -> None:
    board = parse_board(
        "(kicad_pcb (layers)"
        ' (setup (net_class "Default" "" (via_dia 0.8) (add_net "GND")))'
        ' (net 1 "GND")'
        ' (via (at 5 5) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net 1)))'
    )
    issues = check_layout(board, LayoutRules())
    assert [i.message for i in issues] == [
        "via on net 'GND' is 0.6 mm, net class 'Default' requires 0.8 mm"
    ]


def test_unclassed_net_is_not_checked() -> None:
    board = parse_board(
        '(kicad_pcb (layers) (net 1 "SIG")'
        ' (segment (start 0 0) (end 10 0) (width 0.1) (layer "F.Cu") (net 1)))'
    )
    assert check_layout(board, LayoutRules()) == []


def test_project_class_width_violation(project_pass: Project) -> None:
    board = parse_board(
        '(kicad_pcb (layers) (net 1 "SIG")'
        ' (segment (start 0 0) (end 10 0) (width 0.15) (layer "F.Cu") (net 1)))'
    )
    issues = check_layout(board, LayoutRules(), project_pass)
    assert [i.message for i in issues] == [
        "segment on net 'SIG' is 0.15 mm wide, net class 'Default' requires 0.25 mm"
    ]


def test_corner_radius_too_small(board_pass: Board) -> None:
    rules = dataclasses.replace(full_rules(), min_corner_radius_mm=3.1)
    issues = check_layout(board_pass, rules)
    assert len(issues) == _CORNER_COUNT  # one per rounded corner
    assert "radius 3.00 mm, below the 3.1 mm corner minimum" in issues[0].message


def test_sharp_corner_violation() -> None:
    board = parse_board(
        '(kicad_pcb (layers (44 "Edge.Cuts" user))'
        ' (gr_line (start 0 0) (end 50 0) (layer "Edge.Cuts") (width 0.05))'
        ' (gr_line (start 50 0) (end 50 50) (layer "Edge.Cuts") (width 0.05)))'
    )
    issues = check_layout(board, LayoutRules(min_corner_radius_mm=2))
    assert [i.message for i in issues] == [
        (
            "board outline corner at (50.00, 0.00) is sharp — corners must be "
            "rounded to at least 2 mm radius"
        )
    ]


def test_collinear_junction_is_not_a_corner() -> None:
    board = parse_board(
        '(kicad_pcb (layers (44 "Edge.Cuts" user))'
        ' (gr_line (start 0 0) (end 50 0) (layer "Edge.Cuts") (width 0.05))'
        ' (gr_line (start 50 0) (end 100 0) (layer "Edge.Cuts") (width 0.05)))'
    )
    assert check_layout(board, LayoutRules(min_corner_radius_mm=2)) == []


def test_silkscreen_missing_field(board_pass: Board) -> None:
    rules = dataclasses.replace(
        full_rules(), required_silkscreen=(r"oparroy", r"rev-B")
    )
    issues = check_layout(board_pass, rules)
    assert [i.message for i in issues] == [
        "no silkscreen text matches 'rev-B' — the §7 board-ID fields are mandatory"
    ]


def test_serial_box_too_small(board_pass: Board) -> None:
    rules = dataclasses.replace(full_rules(), min_serial_box_mm2=100)
    issues = check_layout(board_pass, rules)
    assert [i.message for i in issues] == [
        (
            "no silkscreen rectangle of at least 100 mm² for the handwritten "
            "serial-number field (§7 checklist)"
        )
    ]


def test_mounting_hole_count_violation(board_pass: Board) -> None:
    rules = dataclasses.replace(full_rules(), min_mounting_holes=5)
    issues = check_layout(board_pass, rules)
    assert [i.message for i in issues] == [
        "board has 4 mounting holes, the contract wants at least 5"
    ]


def test_mounting_hole_without_keepout() -> None:
    board = parse_board(
        "(kicad_pcb (layers)"
        ' (footprint "MountingHole:MountingHole_3.2mm_M3" (layer "F.Cu") (at 5 5)'
        '  (property "Reference" "H1" (at 0 0) (layer "F.SilkS"))'
        '  (pad "" np_thru_hole circle (at 0 0) (size 3.2 3.2) (drill 3.2)'
        '   (layers "*.Cu" "*.Mask"))))'
    )
    rules = LayoutRules(min_mounting_holes=1, mounting_hole_keepout=True)
    issues = check_layout(board, rules)
    assert [i.message for i in issues] == [
        "mounting hole H1 has no keepout zone around it (standoff clearance)"
    ]


def test_adjacency_violation(board_pass: Board) -> None:
    rules = dataclasses.replace(
        full_rules(),
        adjacency=(
            AdjacencyRule(
                name="status LED at connector (§4.1)",
                source=r"D2",
                target=r"J\d+",
                max_distance_mm=3,
            ),
        ),
    )
    issues = check_layout(board_pass, rules)
    assert [i.message for i in issues] == [
        (
            "status LED at connector (§4.1): D2 is not within 3 mm of a "
            "footprint matching 'J\\d+'"
        )
    ]


def test_required_footprint_missing(board_pass: Board) -> None:
    rules = dataclasses.replace(full_rules(), required_footprints=(r"D9",))
    issues = check_layout(board_pass, rules)
    assert [i.message for i in issues] == [
        "no footprint reference matches 'D9' (§7 board-level checklist)"
    ]


def test_bypass_touches_node_logic(board_pass: Board) -> None:
    rules = dataclasses.replace(
        full_rules(),
        bypass=(BypassRule(net="BYPASS", allowed_refs=(r"J\d+",)),),
    )
    issues = check_layout(board_pass, rules)
    assert [i.message for i in issues] == [
        (
            "bypass net 'BYPASS' touches SW1; only footprints matching J\\d+ "
            "may carry it — no node logic in the bypass path (§4)"
        )
    ]
