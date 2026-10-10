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
    LayoutRules,
    Project,
    TerminalProtectionRule,
    annotation_from_pcb,
    check_layout,
    parse_board,
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
