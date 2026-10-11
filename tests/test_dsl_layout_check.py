"""Layout property-checker tests: each contract red/green on the fixtures."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from design.node import capture
from oparroy.dsl import (
    AdjacencyRule,
    Annotation,
    Board,
    BypassRule,
    Circuit,
    FootprintSetRule,
    HolePadClearanceRule,
    LayoutRules,
    PartOverHoleRule,
    Project,
    SheetPartsRule,
    Subcircuit,
    TerminalProtectionRule,
    annotation_from_pcb,
    check_layout,
    parse_board,
    sheet_parts_rules,
    terminal_protection_rules,
)

if TYPE_CHECKING:
    from conftest import StubSymbols
    from oparroy.dsl import KiCadLibraries

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
        serial_box_clearance_mm=0.5,
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


def test_net_class_arc_width_violation() -> None:
    board = parse_board(
        "(kicad_pcb (layers)"
        ' (setup (net_class "Default" "" (trace_width 0.5) (add_net "SIG")))'
        ' (net 1 "SIG")'
        " (arc (start 10 0) (mid 0 10) (end -10 0) (width 0.3)"
        '  (layer "F.Cu") (net 1)))'
    )
    issues = check_layout(board, LayoutRules())
    assert [i.message for i in issues] == [
        "arc on net 'SIG' is 0.3 mm wide, net class 'Default' requires 0.5 mm"
    ]


def test_trace_budget_counts_arcs() -> None:
    """Arc copper counts toward the net's trace-length budget."""
    board = parse_board(
        '(kicad_pcb (layers) (net 1 "SIG")'
        " (arc (start 10 0) (mid 0 10) (end -10 0) (width 0.25)"
        '  (layer "F.Cu") (net 1)))'
    )
    rules = LayoutRules(trace_budgets_mm={"SIG": 30})
    issues = check_layout(board, rules)
    # Semicircle of radius 10: 10π ≈ 31.42 mm.
    assert [i.message for i in issues] == [
        "net 'SIG' routes 31.42 mm of copper, over the 30 mm budget"
    ]


def test_bypass_copper_crossing_segment() -> None:
    board = parse_board(
        '(kicad_pcb (layers) (net 1 "BYPASS") (net 2 "SIG")'
        ' (segment (start 0 0) (end 10 0) (width 0.4) (layer "F.Cu") (net 1))'
        ' (segment (start 5 -1) (end 5 1) (width 0.25) (layer "F.Cu") (net 2)))'
    )
    rules = LayoutRules(bypass=(BypassRule(net="BYPASS", allowed_refs=()),))
    issues = check_layout(board, rules)
    assert [i.message for i in issues] == [
        (
            "bypass net 'BYPASS' shares copper with a segment on net 'SIG' "
            "at (5.00, 0.00) on F.Cu — no node logic in the bypass path (§4)"
        )
    ]


def test_bypass_copper_via_overlap() -> None:
    board = parse_board(
        '(kicad_pcb (layers) (net 1 "BYPASS") (net 2 "GND")'
        ' (segment (start 0 0) (end 10 0) (width 0.4) (layer "F.Cu") (net 1))'
        ' (via (at 5 0.5) (size 0.8) (drill 0.4) (layers "F.Cu" "B.Cu") (net 2)))'
    )
    rules = LayoutRules(bypass=(BypassRule(net="BYPASS", allowed_refs=()),))
    issues = check_layout(board, rules)
    assert [i.message for i in issues] == [
        (
            "bypass net 'BYPASS' shares copper with a via on net 'GND' "
            "at (5.00, 0.25) on F.Cu — no node logic in the bypass path (§4)"
        )
    ]


def test_bypass_copper_via_on_other_layers_is_clean() -> None:
    """A via overlaps the track only when they share a layer."""
    board = parse_board(
        '(kicad_pcb (layers) (net 1 "BYPASS") (net 2 "GND")'
        ' (segment (start 0 0) (end 10 0) (width 0.4) (layer "F.Cu") (net 1))'
        ' (via (at 5 0) (size 0.8) (drill 0.4) (layers "In1.Cu" "In2.Cu")'
        "  (net 2)))"
    )
    rules = LayoutRules(bypass=(BypassRule(net="BYPASS", allowed_refs=()),))
    assert check_layout(board, rules) == []


def test_bypass_copper_same_net_joints_are_clean() -> None:
    """Same-net contact is ordinary connectivity, never flagged."""
    board = parse_board(
        '(kicad_pcb (layers) (net 1 "BYPASS") (net 2 "GND")'
        ' (segment (start 0 0) (end 10 0) (width 0.4) (layer "F.Cu") (net 1))'
        ' (segment (start 5 -1) (end 5 1) (width 0.4) (layer "F.Cu") (net 1))'
        ' (via (at 10 0) (size 0.8) (drill 0.4) (layers "F.Cu" "B.Cu") (net 1)))'
    )
    rules = LayoutRules(bypass=(BypassRule(net="BYPASS", allowed_refs=()),))
    assert check_layout(board, rules) == []


def test_bypass_copper_arc_crossing_segment() -> None:
    """The bypass side is an arc; the chord polygonization still catches it."""
    board = parse_board(
        '(kicad_pcb (layers) (net 1 "BYPASS") (net 2 "SIG")'
        " (arc (start 10 0) (mid 0 10) (end -10 0) (width 0.4)"
        '  (layer "F.Cu") (net 1))'
        ' (segment (start 0 8) (end 0 12) (width 0.25) (layer "F.Cu") (net 2)))'
    )
    rules = LayoutRules(bypass=(BypassRule(net="BYPASS", allowed_refs=()),))
    issues = check_layout(board, rules)
    assert [i.message for i in issues] == [
        (
            "bypass net 'BYPASS' shares copper with a segment on net 'SIG' "
            "at (0.00, 10.00) on F.Cu — no node logic in the bypass path (§4)"
        )
    ]


def test_bypass_copper_segment_crossing_arc() -> None:
    """The other net's arc is copper too: it counts against the bypass."""
    board = parse_board(
        '(kicad_pcb (layers) (net 1 "BYPASS") (net 2 "SIG")'
        ' (segment (start 0 8) (end 0 12) (width 0.4) (layer "F.Cu") (net 1))'
        " (arc (start 10 0) (mid 0 10) (end -10 0) (width 0.25)"
        '  (layer "F.Cu") (net 2)))'
    )
    rules = LayoutRules(bypass=(BypassRule(net="BYPASS", allowed_refs=()),))
    issues = check_layout(board, rules)
    assert [i.message for i in issues] == [
        (
            "bypass net 'BYPASS' shares copper with an arc on net 'SIG' "
            "at (0.00, 10.00) on F.Cu — no node logic in the bypass path (§4)"
        )
    ]


_NODE_BOARD = (
    Path(__file__).parent.parent / "boards" / "node" / "oparroy-node.kicad_pcb"
)


def test_node_board_bypass_copper_is_independent() -> None:
    """The calibration board: the §4 bypass route shares no copper.

    The carriers are the bypass chain itself: the segment connectors,
    the TVS diodes, the series resistors, and U2, the relaxed analog
    switch (see design/node_board.py's net-class notes).
    """
    board = parse_board(_NODE_BOARD.read_text())
    rules = LayoutRules(
        bypass=tuple(
            BypassRule(net=net, allowed_refs=(r"J\d+", r"D\d+", r"R\d+", "U2"))
            for net in ("RX_A", "PHY1/txa_sw", "TX_A")
        )
    )
    assert check_layout(board, rules) == []


_CHAIN_RULE = TerminalProtectionRule(
    name="NET chain",
    net="NET",
    connector="J1",
    tvs="D1",
    series_r="R1",
    max_tvs_connector_mm=6,
    max_r_protected_mm=15,
)


def _chain_footprint(ref: str, x: float, y: float, *nets: str) -> str:
    pads = " ".join(
        f'(pad "{index}" smd rect (at 0 0) (size 1 1) (layers "F.Cu") (net "{net}"))'
        for index, net in enumerate(nets, start=1)
    )
    return (
        f'(footprint "Lib:{ref}" (layer "F.Cu") (at {x} {y})'
        f' (property "Reference" "{ref}" (at 0 0) (layer "F.SilkS")) {pads})'
    )


def _chain_board(*footprints: str) -> Board:
    return parse_board("(kicad_pcb (layers)" + "".join(footprints) + ")")


def _pass_chain() -> Board:
    """J1 on NET, D1 clamping NET at the connector, R1 straddling NET/PROT."""
    return _chain_board(
        _chain_footprint("J1", 0, 0, "NET", "GND"),
        _chain_footprint("D1", 3, 0, "GND", "NET"),
        _chain_footprint("R1", 8, 0, "NET", "PROT"),
        _chain_footprint("U1", 14, 0, "PROT", "GND"),
    )


def _chain_issues(
    board: Board, rule: TerminalProtectionRule = _CHAIN_RULE
) -> list[str]:
    rules = LayoutRules(terminal_protection=(rule,))
    return [i.message for i in check_layout(board, rules)]


def test_terminal_protection_pass() -> None:
    assert _chain_issues(_pass_chain()) == []


def test_terminal_protection_tvs_too_far_from_connector() -> None:
    board = _chain_board(
        _chain_footprint("J1", 0, 0, "NET", "GND"),
        _chain_footprint("D1", 10, 0, "GND", "NET"),
        _chain_footprint("R1", 14, 0, "NET", "PROT"),
        _chain_footprint("U1", 16, 0, "PROT", "GND"),
    )
    assert _chain_issues(board) == [
        (
            "NET chain: TVS D1 is not within 6 mm of its connector — "
            "the TVS clamps at the board edge (§7 checklist)"
        )
    ]


def test_terminal_protection_tvs_not_clamping_the_net() -> None:
    board = _chain_board(
        _chain_footprint("J1", 0, 0, "NET", "GND"),
        _chain_footprint("D1", 3, 0, "GND", "GND"),
        _chain_footprint("R1", 8, 0, "NET", "PROT"),
        _chain_footprint("U1", 14, 0, "PROT", "GND"),
    )
    assert _chain_issues(board) == [
        (
            "NET chain: TVS D1 carries no pad on net 'NET' — "
            "it must clamp the exposed terminal"
        )
    ]


def test_terminal_protection_no_connector_on_the_net() -> None:
    board = _chain_board(
        _chain_footprint("J1", 0, 0, "GND", "GND"),
        _chain_footprint("D1", 3, 0, "GND", "NET"),
        _chain_footprint("R1", 8, 0, "NET", "PROT"),
        _chain_footprint("U1", 14, 0, "PROT", "GND"),
    )
    assert _chain_issues(board) == [
        (
            "NET chain: no connector matching 'J1' carries a pad on net "
            "'NET' — the exposed terminal must enter through its connector"
        )
    ]


def test_terminal_protection_exposed_net_touches_logic() -> None:
    board = _chain_board(
        _chain_footprint("J1", 0, 0, "NET", "GND"),
        _chain_footprint("D1", 3, 0, "GND", "NET"),
        _chain_footprint("R1", 8, 0, "NET", "PROT"),
        _chain_footprint("U1", 14, 0, "PROT", "GND"),
        _chain_footprint("U9", 20, 0, "NET", "GND"),
    )
    assert _chain_issues(board) == [
        (
            "NET chain: exposed net 'NET' touches U9; only its connector, "
            "TVS, and series R may carry it — the R sits between TVS and "
            "µC pin (§7 checklist)"
        )
    ]


def test_terminal_protection_r_off_the_exposed_net() -> None:
    board = _chain_board(
        _chain_footprint("J1", 0, 0, "NET", "GND"),
        _chain_footprint("D1", 3, 0, "GND", "NET"),
        _chain_footprint("R1", 8, 0, "PROT", "GND"),
        _chain_footprint("U1", 14, 0, "PROT", "GND"),
    )
    assert _chain_issues(board) == [
        (
            "NET chain: series R R1 carries no pad on net 'NET' — "
            "it must straddle the exposed net (§7 checklist)"
        )
    ]


def test_terminal_protection_r_short_of_the_exposed_net() -> None:
    board = _chain_board(
        _chain_footprint("J1", 0, 0, "NET", "GND"),
        _chain_footprint("D1", 3, 0, "GND", "NET"),
        _chain_footprint("R1", 8, 0, "NET", "NET"),
        _chain_footprint("U1", 14, 0, "PROT", "GND"),
    )
    assert _chain_issues(board) == [
        (
            "NET chain: both pads of series R R1 sit on net 'NET' — "
            "it must straddle the exposed net"
        )
    ]


def test_terminal_protection_r_too_far_from_protected_logic() -> None:
    board = _chain_board(
        _chain_footprint("J1", 0, 0, "NET", "GND"),
        _chain_footprint("D1", 3, 0, "GND", "NET"),
        _chain_footprint("R1", 8, 0, "NET", "PROT"),
        _chain_footprint("U1", 30, 0, "PROT", "GND"),
    )
    assert _chain_issues(board) == [
        (
            "NET chain: series R R1 is not within 15 mm of any other "
            "footprint on the protected net 'PROT' — the R belongs near "
            "the µC pin it protects (§7 checklist)"
        )
    ]


def test_terminal_protection_tvs_missing() -> None:
    board = _chain_board(
        _chain_footprint("J1", 0, 0, "NET", "GND"),
        _chain_footprint("R1", 8, 0, "NET", "PROT"),
        _chain_footprint("U1", 14, 0, "PROT", "GND"),
    )
    assert _chain_issues(board) == [
        "NET chain: no footprint matches the TVS pattern 'D1'"
    ]


def test_terminal_protection_series_r_missing() -> None:
    board = _chain_board(
        _chain_footprint("J1", 0, 0, "NET", "GND"),
        _chain_footprint("D1", 3, 0, "GND", "NET"),
        _chain_footprint("U1", 14, 0, "PROT", "GND"),
    )
    assert _chain_issues(board) == [
        "NET chain: no footprint matches the series-R pattern 'R1'"
    ]


def _protection_circuit(symbols: StubSymbols) -> Circuit:
    """One connector → TVS → R chain; the GND rail carries two resistors.

    A rail-to-GND bleed plus a protected-side pull-down keep the TVS's
    quiet-side net (GND) from looking like a terminal net — an exposed
    terminal carries exactly one Device:R.
    """
    c = Circuit("prot", symbols)
    tvs = c.part("Dt", symbol="Device:D_TVS", value="TVS", footprint="StubFP:SOD-323")
    res = c.part("Rs", symbol="Device:R", value="470", footprint="StubFP:R_0603")
    conn = c.part(
        "Jc",
        symbol="Connector:Conn_02x05_Odd_Even",
        value="conn",
        footprint="StubFP:CONN_1x06",
    )
    rh1 = c.part("Rh1", symbol="Device:R", value="10k", footprint="StubFP:R_0603")
    rh2 = c.part("Rh2", symbol="Device:R", value="10k", footprint="StubFP:R_0603")
    exposed = c.net("RX_A")
    gnd = c.net("GND")
    prot = c.net("PROT")
    rail = c.net("3V3")
    c.connect(exposed, conn[5], tvs[2], res[1])
    c.connect(gnd, conn[2], tvs[1], rh1[2], rh2[2])
    c.connect(rail, conn[3], rh1[1])
    c.connect(prot, res[2], rh2[1])
    return c


def test_terminal_protection_rules_from_capture(symbols: StubSymbols) -> None:
    circuit = _protection_circuit(symbols)
    annotation = Annotation({"Dt": "D7", "Rs": "R9", "Jc": "J3"})
    assert terminal_protection_rules(circuit, annotation) == (
        TerminalProtectionRule(
            name="terminal protection RX_A (§7 checklist)",
            net="RX_A",
            connector="J3",
            tvs="D7",
            series_r="R9",
            max_tvs_connector_mm=6.0,
            max_r_protected_mm=15.0,
        ),
    )


def test_terminal_protection_rules_rejects_tvs_off_a_terminal(
    symbols: StubSymbols,
) -> None:
    c = Circuit("prot", symbols)
    tvs = c.part("Dt", symbol="Device:D_TVS", value="TVS", footprint="StubFP:SOD-323")
    c.connect(c.net("A"), tvs[1])
    c.connect(c.net("B"), tvs[2])
    with pytest.raises(ValueError, match="Dt: a terminal-protection TVS"):
        terminal_protection_rules(c, Annotation({}))


def test_terminal_protection_rules_requires_placed_parts(
    symbols: StubSymbols,
) -> None:
    circuit = _protection_circuit(symbols)
    with pytest.raises(ValueError, match="Rs has no refdes in the annotation"):
        terminal_protection_rules(circuit, Annotation({"Dt": "D7", "Jc": "J3"}))


def _node_protection_rules(kicad_libs: KiCadLibraries) -> LayoutRules:
    """Build the §7 terminal-protection contract the node capture implies."""
    circuit = capture(kicad_libs)
    pcb_text = _NODE_BOARD.read_text()
    return LayoutRules(
        terminal_protection=terminal_protection_rules(
            circuit, annotation_from_pcb(circuit, pcb_text)
        )
    )


def test_node_board_terminal_protection(kicad_libs: KiCadLibraries) -> None:
    """Calibration: the node board's four chains meet the §7 contract."""
    board = parse_board(_NODE_BOARD.read_text())
    assert check_layout(board, _node_protection_rules(kicad_libs)) == []


def test_node_board_terminal_protection_is_not_vacuous(
    kicad_libs: KiCadLibraries,
) -> None:
    """A 0.1 mm TVS-to-connector budget flags all four node terminals."""
    base = _node_protection_rules(kicad_libs)
    rules = dataclasses.replace(
        base,
        terminal_protection=tuple(
            dataclasses.replace(rule, max_tvs_connector_mm=0.1)
            for rule in base.terminal_protection
        ),
    )
    issues = check_layout(parse_board(_NODE_BOARD.read_text()), rules)
    assert [i.message for i in issues] == [
        (
            "terminal protection RX_A (§7 checklist): TVS D1 is not within "
            "0.1 mm of its connector — the TVS clamps at the board edge "
            "(§7 checklist)"
        ),
        (
            "terminal protection RX_B (§7 checklist): TVS D3 is not within "
            "0.1 mm of its connector — the TVS clamps at the board edge "
            "(§7 checklist)"
        ),
        (
            "terminal protection TX_A (§7 checklist): TVS D2 is not within "
            "0.1 mm of its connector — the TVS clamps at the board edge "
            "(§7 checklist)"
        ),
        (
            "terminal protection TX_B (§7 checklist): TVS D4 is not within "
            "0.1 mm of its connector — the TVS clamps at the board edge "
            "(§7 checklist)"
        ),
    ]


def _layer_footprint(ref: str, layer: str) -> str:
    return (
        f'(footprint "Lib:{ref}" (layer "{layer}") (at 0 0)'
        f' (property "Reference" "{ref}" (at 0 0) (layer "F.SilkS")))'
    )


_BACK_SET_RULE = FootprintSetRule(
    name="back-side footprint set",
    layer="B.Cu",
    refs=("J1", "J2"),
)


def _set_issues(board: Board, rule: FootprintSetRule = _BACK_SET_RULE) -> list[str]:
    rules = LayoutRules(footprint_sets=(rule,))
    return [i.message for i in check_layout(board, rules)]


def test_footprint_set_pass() -> None:
    board = _chain_board(
        _layer_footprint("J1", "B.Cu"),
        _layer_footprint("J2", "B.Cu"),
        _layer_footprint("U1", "F.Cu"),
    )
    assert _set_issues(board) == []


def test_footprint_set_unexpected_on_the_layer() -> None:
    board = _chain_board(
        _layer_footprint("J1", "B.Cu"),
        _layer_footprint("J2", "B.Cu"),
        _layer_footprint("U1", "B.Cu"),
    )
    assert _set_issues(board) == [
        (
            "back-side footprint set: U1 on B.Cu outside the expected "
            "footprint set (J1, J2) — the back carries only the segment "
            "connectors (§7 checklist)"
        )
    ]


def test_footprint_set_member_missing_from_the_layer() -> None:
    board = _chain_board(
        _layer_footprint("J1", "B.Cu"),
        _layer_footprint("J2", "F.Cu"),
    )
    assert _set_issues(board) == [
        (
            "back-side footprint set: J2 missing from B.Cu — the footprint "
            "set is exact (§7 checklist)"
        )
    ]


def test_node_board_back_copper_set_is_connectors_only() -> None:
    """Calibration: B.Cu carries exactly the two segment connectors."""
    board = parse_board(_NODE_BOARD.read_text())
    assert check_layout(board, LayoutRules(footprint_sets=(_BACK_SET_RULE,))) == []


def test_node_board_back_copper_set_is_not_vacuous() -> None:
    """A wrong expected set flags the exact mismatch, both directions."""
    board = parse_board(_NODE_BOARD.read_text())
    rule = dataclasses.replace(_BACK_SET_RULE, refs=("J1", "U1"))
    issues = check_layout(board, LayoutRules(footprint_sets=(rule,)))
    assert [i.message for i in issues] == [
        (
            "back-side footprint set: J2 on B.Cu outside the expected "
            "footprint set (J1, U1) — the back carries only the segment "
            "connectors (§7 checklist)"
        ),
        (
            "back-side footprint set: U1 missing from B.Cu — the footprint "
            "set is exact (§7 checklist)"
        ),
    ]


def _sheet_footprint(ref: str, sheet: str) -> str:
    sheetname = f' (sheetname "{sheet}")' if sheet else ""
    return (
        f'(footprint "Lib:{ref}" (layer "F.Cu") (at 0 0)'
        f' (property "Reference" "{ref}" (at 0 0) (layer "F.SilkS"))'
        f"{sheetname})"
    )


_PHY_SHEET_RULE = SheetPartsRule(
    name="sheet /PHY1/ footprint set",
    sheet="/PHY1/",
    refs=("C1", "R1", "R2"),
)


def _sheet_issues(board: Board, rule: SheetPartsRule = _PHY_SHEET_RULE) -> list[str]:
    rules = LayoutRules(sheet_parts=(rule,))
    return [i.message for i in check_layout(board, rules)]


def test_sheet_parts_pass() -> None:
    """Other sheets and hand-placed (sheetname-less) footprints don't count."""
    board = _chain_board(
        _sheet_footprint("R1", "/PHY1/"),
        _sheet_footprint("R2", "/PHY1/"),
        _sheet_footprint("C1", "/PHY1/"),
        _sheet_footprint("U1", "/"),
        _sheet_footprint("H1", ""),
    )
    assert _sheet_issues(board) == []


def test_sheet_parts_unexpected_under_the_sheet() -> None:
    board = _chain_board(
        _sheet_footprint("R1", "/PHY1/"),
        _sheet_footprint("R2", "/PHY1/"),
        _sheet_footprint("C1", "/PHY1/"),
        _sheet_footprint("U1", "/PHY1/"),
    )
    assert _sheet_issues(board) == [
        (
            "sheet /PHY1/ footprint set: U1 filed under sheet /PHY1/ outside "
            "the sheet's part set — the layout's hierarchy metadata must "
            "match the capture (§7)"
        )
    ]


def test_sheet_parts_member_missing_from_the_sheet() -> None:
    board = _chain_board(
        _sheet_footprint("R1", "/PHY1/"),
        _sheet_footprint("R2", "/PHY1/"),
        _sheet_footprint("C1", "/WD1/"),
    )
    assert _sheet_issues(board) == [
        (
            "sheet /PHY1/ footprint set: C1 missing from sheet /PHY1/ — "
            "the sheet's footprint set is exact (§7)"
        )
    ]


class _Rc(Subcircuit):
    """One resistor across in/gnd; the smallest repeated instance."""

    def capture(self, circuit: Circuit) -> None:
        """Build the cell: R1 from in to gnd."""
        r1 = circuit.part(
            "R1", symbol="Device:R", value="1k", footprint="StubFP:R_0603"
        )
        circuit.connect(circuit.port("in"), r1[1])
        circuit.connect(circuit.port("gnd"), r1[2])


def _two_rc_board(symbols: StubSymbols) -> Circuit:
    board = Circuit("board", symbols)
    inp = board.net("in")
    gnd = board.net("gnd")
    feed = board.part("RF", symbol="Device:R", value="1k", footprint="StubFP:R_0603")
    board.connect(inp, feed[1])
    board.connect(gnd, feed[2])
    for i in range(2):
        board.instance(f"LP{i}", _Rc(), **{"in": inp, "gnd": gnd})
    return board


def test_sheet_parts_rules_from_capture(symbols: StubSymbols) -> None:
    board = _two_rc_board(symbols)
    annotation = Annotation({"RF": "R1", "LP0/R1": "R2", "LP1/R1": "R3"})
    assert sheet_parts_rules(board, annotation) == (
        SheetPartsRule(name="sheet / footprint set", sheet="/", refs=("R1",)),
        SheetPartsRule(name="sheet /LP0/ footprint set", sheet="/LP0/", refs=("R2",)),
        SheetPartsRule(name="sheet /LP1/ footprint set", sheet="/LP1/", refs=("R3",)),
    )


def test_sheet_parts_rules_requires_placed_parts(symbols: StubSymbols) -> None:
    board = _two_rc_board(symbols)
    with pytest.raises(ValueError, match="LP1/R1 has no refdes in the annotation"):
        sheet_parts_rules(board, Annotation({"RF": "R1", "LP0/R1": "R2"}))


def _node_sheet_rules(kicad_libs: KiCadLibraries) -> LayoutRules:
    """Build the sheet-partition contract the node capture implies."""
    circuit = capture(kicad_libs)
    pcb_text = _NODE_BOARD.read_text()
    return LayoutRules(
        sheet_parts=sheet_parts_rules(circuit, annotation_from_pcb(circuit, pcb_text))
    )


def test_node_board_sheet_partition_matches_capture(
    kicad_libs: KiCadLibraries,
) -> None:
    """Calibration: every board footprint sits under its capture sheet."""
    board = parse_board(_NODE_BOARD.read_text())
    assert check_layout(board, _node_sheet_rules(kicad_libs)) == []


def test_node_board_sheet_partition_is_not_vacuous(
    kicad_libs: KiCadLibraries,
) -> None:
    """A declared part absent from the sheet flags as missing."""
    base = _node_sheet_rules(kicad_libs)
    rules = dataclasses.replace(
        base,
        sheet_parts=tuple(
            dataclasses.replace(rule, refs=(*rule.refs, "R99"))
            if rule.sheet == "/SL1/"
            else rule
            for rule in base.sheet_parts
        ),
    )
    issues = check_layout(parse_board(_NODE_BOARD.read_text()), rules)
    assert [i.message for i in issues] == [
        (
            "sheet /SL1/ footprint set: R99 missing from sheet /SL1/ — "
            "the sheet's footprint set is exact (§7)"
        )
    ]


def _led_footprint(ref: str, hole: str | None = "0 0") -> str:
    hole_pad = (
        f' (pad "" np_thru_hole oval (at {hole}) (size 1.5 2.4)'
        ' (drill oval 1.5 2.4) (layers "*.Cu" "*.Mask"))'
        if hole is not None
        else ""
    )
    return (
        f'(footprint "Lib:{ref}" (layer "F.Cu") (at 10 10)'
        f' (property "Reference" "{ref}" (at 0 0) (layer "F.SilkS"))'
        ' (pad "1" smd rect (at -1.55 0) (size 0.95 1.75) (layers "F.Cu")'
        '  (net "A"))'
        ' (pad "2" smd rect (at 1.55 0) (size 0.95 1.75) (layers "F.Cu")'
        '  (net "B"))'
        f"{hole_pad})"
    )


_LED_RULE = PartOverHoleRule(
    name="status LED over its routed hole",
    refdes=r"LED\d+",
    tolerance_mm=0.2,
)


def _led_issues(board: Board, rule: PartOverHoleRule = _LED_RULE) -> list[str]:
    rules = LayoutRules(part_over_hole=(rule,))
    return [i.message for i in check_layout(board, rules)]


_LED_HOLE_MESSAGE = (
    "status LED over its routed hole: {} has no unconnected np_thru_hole "
    "pad within 0.2 mm of its anchor — the reverse-mount LED shines "
    "through its routed hole (§4.1)"
)


def test_part_over_hole_pass() -> None:
    board = _chain_board(_led_footprint("LED1"), _led_footprint("LED2", "0.1 0"))
    assert _led_issues(board) == []


def test_part_over_hole_missing_hole() -> None:
    board = _chain_board(_led_footprint("LED1", None))
    assert _led_issues(board) == [_LED_HOLE_MESSAGE.format("LED1")]


def test_part_over_hole_hole_off_the_anchor() -> None:
    board = _chain_board(_led_footprint("LED1", "0.5 0"))
    assert _led_issues(board) == [_LED_HOLE_MESSAGE.format("LED1")]


def test_part_over_hole_connected_hole_does_not_count() -> None:
    """A plated/netted through-pad is not the routed hole: it must be NPTH."""
    board = parse_board(
        '(kicad_pcb (layers) (footprint "Lib:LED1" (layer "F.Cu") (at 0 0)'
        ' (property "Reference" "LED1" (at 0 0) (layer "F.SilkS"))'
        ' (pad "" thru_hole circle (at 0 0) (size 1.5 2.4) (drill 1.5)'
        '  (layers "*.Cu" "*.Mask") (net "GND"))))'
    )
    assert _led_issues(board) == [_LED_HOLE_MESSAGE.format("LED1")]


def test_node_board_status_leds_sit_over_their_holes() -> None:
    """Calibration: LED1-LED4 each carry their routed hole at the anchor."""
    board = parse_board(_NODE_BOARD.read_text())
    assert check_layout(board, LayoutRules(part_over_hole=(_LED_RULE,))) == []


def test_node_board_status_leds_over_holes_is_not_vacuous() -> None:
    """Widen the pattern to a TVS: it matches, and it flags the hole it lacks."""
    board = parse_board(_NODE_BOARD.read_text())
    rule = dataclasses.replace(_LED_RULE, refdes=r"LED\d+|D5")
    issues = check_layout(board, LayoutRules(part_over_hole=(rule,)))
    assert [i.message for i in issues] == [_LED_HOLE_MESSAGE.format("D5")]


def _clearance_board(body: str) -> Board:
    """Build a board whose only feature is the 10x8 serial box (80 mm²) plus body."""
    return parse_board(
        '(kicad_pcb (layers (36 "B.SilkS" user) (37 "F.SilkS" user))'
        ' (gr_rect (start 0 0) (end 10 8) (layer "F.SilkS") (fill yes))' + body + ")"
    )


_CLEARANCE_RULES = LayoutRules(min_serial_box_mm2=80, serial_box_clearance_mm=0.5)


def _clearance_issues(board: Board, rules: LayoutRules = _CLEARANCE_RULES) -> list[str]:
    return [i.message for i in check_layout(board, rules)]


def test_serial_box_clearance_clean_board() -> None:
    assert _clearance_issues(_clearance_board("")) == []


def test_serial_box_clearance_pad_too_close() -> None:
    """A 1x1 SMD pad centered 0.8 mm off the box edge leaves a 0.3 mm gap."""
    board = _clearance_board(
        '(footprint "Lib:R1" (layer "F.Cu") (at 10.8 4)'
        ' (property "Reference" "R1" (at 0 -2 0) (layer "F.SilkS"))'
        ' (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu" "F.Mask")'
        '  (net "SIG")))'
    )
    assert _clearance_issues(board) == [
        (
            "serial box comes within 0.30 mm of R1 pad 1 at (10.80, 4.00), "
            "under the 0.5 mm clearance — keep the handwritten serial field "
            "clear of pads (§7 checklist)"
        )
    ]


_SLOT_RULE = HolePadClearanceRule(
    name="LED slot clear of connector pads",
    hole=r"LED\d+",
    pads=r"J\d+",
    min_clearance_mm=1.3,
)


def _slot_board(led_at: str, conn_at: str) -> Board:
    """One LED with its routed slot, one connector with a single 5x1.02 pad."""
    return parse_board(
        "(kicad_pcb (layers)"
        f' (footprint "Lib:LED" (layer "F.Cu") (at {led_at})'
        '  (property "Reference" "LED1" (at 0 0) (layer "F.SilkS"))'
        '  (pad "" np_thru_hole oval (at 0 0) (size 1.5 2.4)'
        '   (drill oval 1.5 2.4) (layers "*.Cu" "*.Mask")))'
        f' (footprint "Lib:Conn" (layer "B.Cu") (at {conn_at})'
        '  (property "Reference" "J1" (at 0 0) (layer "B.SilkS"))'
        '  (pad "1" smd roundrect (at 0 0) (size 5 1.02) (layers "B.Cu")'
        '   (net "SIG"))))'
    )


def _slot_issues(board: Board, rule: HolePadClearanceRule = _SLOT_RULE) -> list[str]:
    rules = LayoutRules(hole_pad_clearance=(rule,))
    return [i.message for i in check_layout(board, rules)]


def test_hole_pad_clearance_pass() -> None:
    # Slot spine end to pad spine: 5 - 0.45 - 0.75 - 0.51 = 3.29 mm.
    assert _slot_issues(_slot_board("0 0", "0 5")) == []


def test_hole_pad_clearance_violation() -> None:
    # Slot spine end to pad spine: 2.9 - 0.45 - 0.75 - 0.51 = 1.19 mm.
    assert _slot_issues(_slot_board("0 0", "0 2.9")) == [
        (
            "LED slot clear of connector pads: LED1's routed hole is 1.19 mm "
            "from J1 pad 1 at (0.00, 1.67), under the 1.3 mm floor — the "
            "waived courtyard overlap stays safe only while this clearance "
            "holds"
        )
    ]


def test_serial_box_clearance_uses_footprint_rotation() -> None:
    """The pad lands inside the box only once the 90° rotation is applied."""
    board = _clearance_board(
        '(footprint "Lib:R1" (layer "F.Cu") (at 13 4 90)'
        ' (property "Reference" "R1" (at 0 0 0) (layer "F.SilkS") (hide yes))'
        ' (pad "1" smd rect (at 0 -4 0) (size 1 1) (layers "F.Cu")'
        '  (net "SIG")))'
    )
    assert _clearance_issues(board) == [
        (
            "serial box comes within 0.00 mm of R1 pad 1 at (9.00, 4.00), "
            "under the 0.5 mm clearance — keep the handwritten serial field "
            "clear of pads (§7 checklist)"
        )
    ]


def test_serial_box_clearance_circle_pad_gap() -> None:
    """A circle pad's gap is its center distance minus the radius."""
    board = _clearance_board(
        '(footprint "Lib:H1" (layer "F.Cu") (at 12 4)'
        ' (property "Reference" "H1" (at 0 -3 0) (layer "F.SilkS"))'
        ' (pad "" np_thru_hole circle (at 0 0) (size 1.7 1.7) (drill 1)'
        '  (layers "*.Cu" "*.Mask")))'
    )
    rules = dataclasses.replace(_CLEARANCE_RULES, serial_box_clearance_mm=1.2)
    assert _clearance_issues(board, rules) == [
        (
            "serial box comes within 1.15 mm of H1 at (12.00, 4.00), under "
            "the 1.2 mm clearance — keep the handwritten serial field clear "
            "of pads (§7 checklist)"
        )
    ]
    looser = dataclasses.replace(_CLEARANCE_RULES, serial_box_clearance_mm=1.1)
    assert _clearance_issues(board, looser) == []


def test_serial_box_clearance_ignores_the_other_face() -> None:
    """A B-side pad under an F.SilkS box never meets the ink."""
    board = _clearance_board(
        '(footprint "Lib:J1" (layer "B.Cu") (at 5 4)'
        ' (property "Reference" "J1" (at 0 0 0) (layer "B.SilkS"))'
        ' (pad "1" smd rect (at 0 0) (size 2 2) (layers "B.Cu" "B.Mask")'
        '  (net "SIG")))'
    )
    assert _clearance_issues(board) == []


def test_serial_box_clearance_text_inside() -> None:
    board = _clearance_board(' (gr_text "oparroy v2" (at 5 4 0) (layer "F.SilkS"))')
    assert _clearance_issues(board) == [
        (
            "silkscreen text 'oparroy v2' comes within 0.00 mm of the serial "
            "box, under the 0.5 mm clearance (§7 checklist)"
        )
    ]


def test_serial_box_clearance_footprint_reference() -> None:
    """A visible reference designator inside the box counts as text."""
    board = _clearance_board(
        '(footprint "Lib:R1" (layer "F.Cu") (at 5 4)'
        ' (property "Reference" "R1" (at 0 0 0) (layer "F.SilkS")))'
    )
    assert _clearance_issues(board) == [
        (
            "silkscreen text 'R1' comes within 0.00 mm of the serial box, "
            "under the 0.5 mm clearance (§7 checklist)"
        )
    ]


def test_serial_box_clearance_hidden_reference_is_ignored() -> None:
    board = _clearance_board(
        '(footprint "Lib:R1" (layer "F.Cu") (at 5 4)'
        ' (property "Reference" "R1" (at 0 0 0) (layer "F.SilkS") (hide yes)))'
    )
    assert _clearance_issues(board) == []


def test_serial_box_clearance_needs_the_area_minimum() -> None:
    board = _clearance_board("")
    issues = _clearance_issues(board, LayoutRules(serial_box_clearance_mm=0.5))
    assert issues == [
        (
            "serial_box_clearance_mm needs min_serial_box_mm2 to identify the "
            "serial-number box (§7 checklist)"
        )
    ]


_SERIAL_BOX_RULES = LayoutRules(min_serial_box_mm2=100, serial_box_clearance_mm=1.5)


def test_node_board_serial_box_is_clear() -> None:
    """Calibration: the node board's serial box keeps 1.5 mm clear."""
    board = parse_board(_NODE_BOARD.read_text())
    assert check_layout(board, _SERIAL_BOX_RULES) == []


def test_node_board_serial_box_clearance_is_not_vacuous() -> None:
    """At 2 mm the mounting holes beside the box trip the clearance."""
    board = parse_board(_NODE_BOARD.read_text())
    rules = dataclasses.replace(_SERIAL_BOX_RULES, serial_box_clearance_mm=2.0)
    issues = check_layout(board, rules)
    assert [i.message for i in issues] == [
        (
            "serial box comes within 1.70 mm of REF** at (102.62, 94.49), "
            "under the 2.0 mm clearance — keep the handwritten serial field "
            "clear of pads (§7 checklist)"
        ),
        (
            "serial box comes within 1.70 mm of REF** at (131.57, 94.49), "
            "under the 2.0 mm clearance — keep the handwritten serial field "
            "clear of pads (§7 checklist)"
        ),
    ]


def test_hole_pad_clearance_applies_footprint_rotation() -> None:
    """The connector's pad lands under the slot only once rotated 180°."""

    def board(rotation: str) -> Board:
        return parse_board(
            "(kicad_pcb (layers)"
            ' (footprint "Lib:LED" (layer "F.Cu") (at 4 0)'
            '  (property "Reference" "LED1" (at 0 0) (layer "F.SilkS"))'
            '  (pad "" np_thru_hole oval (at 0 0) (size 1.5 2.4)'
            '   (drill oval 1.5 2.4) (layers "*.Cu" "*.Mask")))'
            f' (footprint "Lib:Conn" (layer "B.Cu") (at 10 0{rotation})'
            '  (property "Reference" "J1" (at 0 0) (layer "B.SilkS"))'
            '  (pad "1" smd roundrect (at 3 0) (size 5 1.02) (layers "B.Cu")'
            '   (net "SIG"))))'
        )

    assert _slot_issues(board("")) == []
    assert _slot_issues(board(" 180")) != []


def test_hole_pad_clearance_skips_other_npth() -> None:
    """The target footprint's own np_thru_hole pads are not copper pads."""
    board = parse_board(
        "(kicad_pcb (layers)"
        ' (footprint "Lib:LED" (layer "F.Cu") (at 0 0)'
        '  (property "Reference" "LED1" (at 0 0) (layer "F.SilkS"))'
        '  (pad "" np_thru_hole oval (at 0 0) (size 1.5 2.4)'
        '   (drill oval 1.5 2.4) (layers "*.Cu" "*.Mask")))'
        ' (footprint "Lib:Conn" (layer "B.Cu") (at 0 0)'
        '  (property "Reference" "J1" (at 0 0) (layer "B.SilkS"))'
        '  (pad "" np_thru_hole circle (at 0 0) (size 3.2 3.2) (drill 3.2)'
        '   (layers "*.Cu" "*.Mask"))))'
    )
    assert _slot_issues(board) == []


def test_node_board_led_slots_clear_connector_pads() -> None:
    """Calibration: the waived courtyard pair keeps real pad clearance.

    The LED light-pipe slots sit inside the J1/J2 courtyards (the
    excluded npth_inside_courtyard pair); the slot edges hold 1.35 mm
    to the nearest connector pad, above the 1.3 mm floor.
    """
    board = parse_board(_NODE_BOARD.read_text())
    assert check_layout(board, LayoutRules(hole_pad_clearance=(_SLOT_RULE,))) == []


def test_node_board_led_slot_clearance_is_not_vacuous() -> None:
    """A 2 mm floor flags every LED slot that sits under a connector."""
    board = parse_board(_NODE_BOARD.read_text())
    rule = dataclasses.replace(_SLOT_RULE, min_clearance_mm=2.0)
    issues = check_layout(board, LayoutRules(hole_pad_clearance=(rule,)))
    assert [i.message for i in issues] == [
        (
            "LED slot clear of connector pads: LED2's routed hole is 1.45 mm "
            "from J1 pad 10 at (113.56, 74.77), under the 2.0 mm floor — the "
            "waived courtyard overlap stays safe only while this clearance "
            "holds"
        ),
        (
            "LED slot clear of connector pads: LED1's routed hole is 1.35 mm "
            "from J2 pad 1 at (131.44, 74.78), under the 2.0 mm floor — the "
            "waived courtyard overlap stays safe only while this clearance "
            "holds"
        ),
        (
            "LED slot clear of connector pads: LED3's routed hole is 1.35 mm "
            "from J1 pad 9 at (103.13, 74.77), under the 2.0 mm floor — the "
            "waived courtyard overlap stays safe only while this clearance "
            "holds"
        ),
        (
            "LED slot clear of connector pads: LED4's routed hole is 1.57 mm "
            "from J2 pad 2 at (120.56, 74.78), under the 2.0 mm floor — the "
            "waived courtyard overlap stays safe only while this clearance "
            "holds"
        ),
    ]
