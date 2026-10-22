"""CI board composition tests (need the nix-provisioned libraries).

The golden netlist at tests/golden/oparroy-ci.net is what pcbnew
ingests — the post-annotation emission of the instrumented side (the
plain reference side exists for the reset-state equivalence proof
only); regenerate it, and the placement map the pcbnew grouping helper
(boards/ci/group-by-tile.py) reads, from the dev shell with:

    python -m design.ci_board --placement-map boards/ci/placement-map.json \
        > tests/golden/oparroy-ci.net
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from design import ci_tiles
from design.ci_board import (
    INPUT_TILES,
    TILE_COUNT,
    capture,
    ci_board_plan,
    placement_map_json,
)
from design.ci_instrumentation import BUDGETS, reset_levels
from design.ci_tiles import MEASUREMENT_TILE
from oparroy.dsl import (
    POWER_DOMAIN_CROSSING,
    Circuit,
    EquivalenceReport,
    KiCadLibraries,
    Severity,
    annotate,
    apply_annotation,
    check,
    check_equivalent,
    emit_netlist,
    raise_on_errors,
    solve,
)
from oparroy.dsl.equivalence import (
    EXTRA_LOADING,
    LEAKAGE,
    SERIES_ON_RESISTANCE,
    SHUNT_OFF_CAPACITANCE,
    SWITCH_CAPACITANCE,
    TAP_CAPACITANCE,
)
from oparroy.dsl.ir import hierarchical_crossings
from oparroy.dsl.transform import AddTap

if TYPE_CHECKING:
    import pytest

GOLDEN = Path(__file__).parent / "golden" / "oparroy-ci.net"
PLACEMENT_MAP = Path(__file__).parent.parent / "boards" / "ci" / "placement-map.json"

#: The injector switches' reset-open throws (bit 0 = pass-through):
#: the break switches' B2 legs, the shunts' signal-side legs. The
#: supervisor's injector is the same block; the tiles add the ka-cut.
INJECTOR_NC_PINS = ("SWAB.1", "SWAG.3", "SWAV.3", "SWBB.1", "SWBG.3", "SWBV.3")


def solved(circuit: Circuit) -> Circuit:
    """Run the value-solve pass, failing the test on its errors."""
    raise_on_errors(solve(circuit).issues)
    return circuit


def expected_warnings() -> frozenset[str]:
    """Return the board's deliberate warnings, pinned so nothing hides."""
    warnings = {
        # The observe stages' complementary serial outputs are unused.
        "PLANE/OBS0/U1.7 is not connected",
        "PLANE/OBS1/U1.7 is not connected",
        # USB-C SBU1/SBU2: unused on a USB 2.0 sink (design/ci_power.py).
        "PWR/J1.A8 is not connected",
        "PWR/J1.B8 is not connected",
        # AUX2's two spare outputs (scan-plane §1).
        "net 'PLANE/aux2_spare6' has a single pin (PLANE/AUX2/U1.6)",
        "net 'PLANE/aux2_spare7' has a single pin (PLANE/AUX2/U1.7)",
        # NC = normal flash boot (design/supervisor.py).
        "net 'usb_boot' has a single pin (SUP/R1.2)",
        # The cable-fed rails carry only power inputs — no on-board
        # driver (5V ends at the regulator, GND crosses the cable).
        "net '5V' has power inputs but no driver (power output or power symbol)",
        "net 'GND' has power inputs but no driver (power output or power symbol)",
        # The supervisor's spare GPIOs (GPIO3, GPIO23..29) and the
        # SWCLK/SWDIO pads are deliberate NCs; GPIO0..2 drive the §12
        # measurement tile's ADC SPI.
        *(f"SUP/U1.{pin} is not connected" for pin in (5, 24, 25, *range(35, 42))),
        # The supervisor injector's reset-open throws.
        *(f"SUP/FI1/{sw} is not connected" for sw in INJECTOR_NC_PINS),
        # The boundary tile's watchdog-defeat shunt parks its open leg.
        "T0/FI1/SWWD.3 is not connected",
        # The measurement tile's 595 slice drives only PWR (§12); the
        # other seven outputs are spares, like AUX2's pair.
        *(
            f"net 'PLANE/t6_spare{index}' has a single pin (PLANE/T6/U1.{index})"
            for index in range(1, 8)
        ),
    }
    for tile in range(TILE_COUNT):
        # The measurement tile carries no injector switches (§12) — no
        # reset-open throws to report.
        if tile != MEASUREMENT_TILE:
            warnings.update(
                f"T{tile}/FI1/{sw} is not connected"
                for sw in (*INJECTOR_NC_PINS, "SWKA.1")
            )
        # PC1 (pin 11) is every tile's spare pad; each variant leaves
        # the other variants' payload pads unwired — the output tiles
        # the pot/button pads (PD6/PC5/PC6), the input tiles the
        # buzzer pad (PC4), the measurement tile all four.
        if tile == MEASUREMENT_TILE:
            pads = (3, 14, 15, 16)
        else:
            pads = (3, 15, 16) if tile not in INPUT_TILES else (14,)
        warnings.update(f"T{tile}/U1.{pad} is not connected" for pad in (*pads, 11))
        # The switched rail sits behind the F8 P-FET: power inputs,
        # no driver.
        warnings.add(
            f"net 'T{tile}/3V3N' has power inputs but no driver "
            "(power output or power symbol)"
        )
    return frozenset(warnings)


def nets_of(circuit: Circuit) -> dict[str, set[str]]:
    """Net name -> member pins as 'ref.number', over the flattened IR."""
    flat = circuit.flatten() if circuit.instances else circuit
    return {
        name: {f"{p.part.ref}.{p.number}" for p in net.pins}
        for name, net in flat.nets.items()
    }


def errors(report: EquivalenceReport) -> list[str]:
    """Collect the ERROR-severity messages of a report."""
    return [i.message for i in report.issues if i.severity is Severity.ERROR]


def test_ring_closes_through_the_supervisor(kicad_libs: KiCadLibraries) -> None:
    nets = nets_of(capture(kicad_libs, instrumented=False))
    # The boundary segment is the connectorized one (instrumented-ci
    # §2): J0 at the supervisor end, T0's J1 at the tile end.
    assert {"J0.5", "T0/J1.5", "SUP/Rat.2", "SUP/Dat.1"} <= nets["SEG0_A"]
    assert {"J0.7", "T0/J1.7", "SUP/Rbr.1", "SUP/Dbr.1"} <= nets["SEG0_B"]
    # The drain: tile 7 hands the ring back to the supervisor.
    assert nets[f"SEG{TILE_COUNT}_A"] == {"SUP/Rar.1", "T7/PHY1/Rat.2"}
    assert nets[f"SEG{TILE_COUNT}_B"] == {"SUP/Rbt.2", "T7/PHY1/Rbr.1"}
    # UNREG is the boundary cable's dead conductor (ci_board's module
    # docstring): J0.1 ↔ T0/J1.1 and nothing else.
    assert nets["UNREG"] == {"J0.1", "T0/J1.1"}


def test_inter_tile_segments_are_bare_copper(kicad_libs: KiCadLibraries) -> None:
    nets = nets_of(capture(kicad_libs, instrumented=False))
    # R10: no connectors, no TVS between tiles — two PHY faces only.
    assert nets["SEG1_A"] == {"T0/PHY1/Rat.2", "T1/PHY1/Rar.1"}
    assert nets["SEG4_B"] == {"T3/PHY1/Rbr.1", "T4/PHY1/Rbt.2"}


def test_tiles_carry_forward_mount_status_leds(kicad_libs: KiCadLibraries) -> None:
    """The bench board's viewer is component-side: top-emitting LEDs.

    Pins the DESIGN.md §4.1 split — the CI tiles carry the top-emitting
    XL-3216 siblings on the stock 1206 land pattern, never the node
    board's reverse-mount light-pipe parts (design/ci_tiles.py).
    """
    flat = capture(kicad_libs, instrumented=False).flatten()
    expected = {
        "Dp": "XL-3216SURC",
        "Dw": "XL-3216UYC",
        "Du": "XL-3216SYGC",
        "Dd": "XL-3216SYGC",
    }
    for tile in range(TILE_COUNT):
        for role, value in expected.items():
            part = flat.parts[f"T{tile}/SL1/{role}"]
            assert part.value == value
            assert part.footprint == "LED_SMD:LED_1206_3216Metric"


def test_control_plane_binds_the_handles(kicad_libs: KiCadLibraries) -> None:
    nets = nets_of(capture(kicad_libs))
    # The scan plane drives the escaped controls through its stages:
    # a per-tile bit, a supervisor-injector bit, the boundary defeat,
    # an input-override select.
    assert {"PLANE/T0/U1.15", "T0/FI1/SWAB.6"} <= nets["T0/BRK_A"]
    assert {"PLANE/AUX0/U1.15", "SUP/FI1/SWAB.6"} <= nets["SUP/BRK_A"]
    assert {"PLANE/AUX1/U1.1", "T0/FI1/SWWD.6"} <= nets["T0/WD_DEFEAT"]
    assert {"PLANE/AUX1/U1.2", "T1/FI1/SWPOT.6"} <= nets["T1/POT_SEL"]
    # The supervisor's PWM pin drives the substitute source (H1).
    assert nets["T1/POT_PWM"] == {"SUP/U1.17", "T1/FI1/RPF.1"}
    # The mux trees terminate on the tiles' swio/debug_tx pads.
    assert {"SWIO/SW4.3", "SWIO/RU0.1", "T0/U1.18"} <= nets["T0/swio"]
    assert {"DBG/SW4.3", "T0/U1.2"} <= nets["T0/debug_tx"]
    # The boundary taps land on the supervisor's GPIOs; B2's tap IS the
    # downstream segment net, so the tap pin rides SEG1_A.
    assert "SUP/U1.11" in nets["T0/opa_p"]
    assert "SUP/U1.12" in nets["SEG1_A"]
    # The observe taps land on the 165 stages' parallel inputs.
    assert "PLANE/OBS0/U1.11" in nets["T0/sel"]


def test_capture_checks_clean(kicad_libs: KiCadLibraries) -> None:
    issues = check(solved(capture(kicad_libs)), footprints=kicad_libs)
    assert [i for i in issues if i.severity is Severity.ERROR] == []
    assert {i.message for i in issues} == expected_warnings()


def test_base_capture_checks_clean(kicad_libs: KiCadLibraries) -> None:
    issues = check(
        solved(capture(kicad_libs, instrumented=False)), footprints=kicad_libs
    )
    assert [i for i in issues if i.severity is Severity.ERROR] == []


def test_crossing_dispositions(kicad_libs: KiCadLibraries) -> None:
    """The §3 crossing audit's declaration map over the real capture."""
    board = capture(kicad_libs)
    declared: dict[str, list[str]] = {}
    for crossing in hierarchical_crossings(board):
        declared.setdefault(crossing.path, []).append(
            type(crossing.disposition).__name__
        )
    # Every tile: the ring wires' bounded back-feed, the always-powered
    # mux/select/driver group (design/ci_tiles.py).
    for tile in range(TILE_COUNT):
        measurement = tile == MEASUREMENT_TILE
        # The measurement tile drops F1-F7 (§12): the F4-created RX_B#a
        # stub never exists, and without F1's break the tile's TX_A
        # drive reaches T7's gated rail — declared itself.
        back_feed = ("opa_p", "opo", "opa_p_b", "txb_drv") + (
            ("PHY1/txa_sw",) if measurement else ("RX_B#a",)
        )
        for net in back_feed:
            assert declared[f"T{tile}/{net}"] == ["BackFeed"]
        always = ("swio", "debug_tx", "sel", "PHY1/sel_sw", "txa_drv") + (
            () if measurement else ("ka#a",)
        )
        for net in always:
            if tile == 0 and net == "sel":
                continue  # asserted below
            assert declared[f"T{tile}/{net}"] == ["AlwaysPowered"]
    # The measurement chain's sense net dies with the tile's rail (§12).
    assert declared[f"T{MEASUREMENT_TILE}/F8_sns"] == ["DiesWith"]
    # T0/sel adds the board-level BackFeed bounding B5's defeat leg
    # (instrumented-ci.md §3/§5) on top of the tile's AlwaysPowered.
    assert sorted(declared["T0/sel"]) == ["AlwaysPowered", "BackFeed"]
    # B4's observe-only tap: the RP2040 pad drive bounds the misdrive.
    assert declared["T0/led_work"] == ["BackFeed"]
    assert declared["T0/SL1/ledw_a"] == ["BackFeed"]
    # The inter-tile segments; the drain (SEG8) never crosses.
    for index in range(TILE_COUNT):
        assert declared[f"SEG{index}_A"] == ["BackFeed"]
        assert declared[f"SEG{index}_B"] == ["BackFeed"]


def test_dropped_segment_declaration_fails(
    kicad_libs: KiCadLibraries, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control: drop the declarations and the audit names the nets."""
    monkeypatch.setattr(
        "design.ci_board.declare_segment_crossings", lambda _board, _segments: None
    )
    issues = check(capture(kicad_libs), footprints=kicad_libs)
    undeclared = {
        i.path
        for i in issues
        if i.check == POWER_DOMAIN_CROSSING and i.severity is Severity.ERROR
    }
    assert undeclared == {
        f"SEG{index}_{wire}" for index in range(TILE_COUNT) for wire in ("A", "B")
    }


def test_dropped_measurement_declaration_fails(
    kicad_libs: KiCadLibraries, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control: drop the F8_sns declaration and the audit names it."""
    real = ci_tiles._declare_measurement_crossings  # noqa: SLF001

    def without_sns(circuit: Circuit) -> None:
        real(circuit)
        circuit._crossings = [  # noqa: SLF001 — the neutralization itself
            c for c in circuit.crossings if c.path != "F8_sns"
        ]

    monkeypatch.setattr(ci_tiles, "_declare_measurement_crossings", without_sns)
    issues = check(capture(kicad_libs), footprints=kicad_libs)
    undeclared = {
        i.path
        for i in issues
        if i.check == POWER_DOMAIN_CROSSING and i.severity is Severity.ERROR
    }
    assert undeclared == {f"T{MEASUREMENT_TILE}/F8_sns"}


def test_reset_levels_all_zero(kicad_libs: KiCadLibraries) -> None:
    """The §8 invariant over the full board: the reset load is all-zeros."""
    instrumented = capture(kicad_libs)
    levels = reset_levels(instrumented, ci_board_plan())
    assert set(levels.values()) == {0}
    # 8 bits per injector tile + the measurement tile's lone PWR + the
    # boundary defeat + 3 overrides per input tile + the supervisor
    # injector's 6.
    assert len(levels) == 8 * (TILE_COUNT - 1) + 1 + 1 + 3 * len(INPUT_TILES) + 6


def test_reset_state_equivalence(kicad_libs: KiCadLibraries) -> None:
    """The full board: instrumented ≡ plain, modulo the §9 register."""
    plan = ci_board_plan()
    base = capture(kicad_libs, instrumented=False)
    instrumented = capture(kicad_libs)
    report = check_equivalent(
        base,
        instrumented,
        plan,
        reset_levels=reset_levels(instrumented, plan),
        budgets=BUDGETS,
    )
    assert list(report.issues) == []
    assert all(r.citation is not None for r in report.residuals)
    kinds = [r.kind for r in report.residuals]
    # T0 (boundary output tile): F1-F8 + B1-B5; T2/4: F1-F8; T6
    # (measurement): the extended F8 alone + P1-P3; T1/3/5/7 (input):
    # F1-F8 + H1-H3; the supervisor injector: F1-F6.
    assert kinds.count(SERIES_ON_RESISTANCE) == 4 + 2 * 4 + 1 + 4 * 5 + 2
    assert kinds.count(SWITCH_CAPACITANCE) == 3 + 2 * 3 + 4 * 4 + 2
    assert kinds.count(LEAKAGE) == 8 + 2 * 7 + 4 * 10 + 6
    assert kinds.count(SHUNT_OFF_CAPACITANCE) == 5 + 2 * 4 + 4 * 6 + 4
    # T6's extras: the gate pull-down, the shunt, the amp, the RC pair,
    # the ADC, the CS pull-up, three bypass caps.
    assert kinds.count(EXTRA_LOADING) == 7 + 2 * 6 + 10 + 4 * 10 + 4  # T0: + RWD
    # O1/O2 + M1/M2 per tile, B1-B4 on the boundary tile, P1-P3 on the
    # measurement tile (resolving onto 3V3 by provenance, like O2).
    assert kinds.count(TAP_CAPACITANCE) == TILE_COUNT * 4 + 4 + 3
    taps = [r for r in report.residuals if r.kind == TAP_CAPACITANCE]
    assert all(r.layout_obligation for r in taps)
    assert {r.net for r in taps} == {
        # B1/B3/B4, B2 (the tap IS the segment net), and the 3V3N
        # observe taps reduced to the rail they were cut from.
        "T0/opa_p",
        "SEG1_A",
        "T0/opo",
        "T0/led_work",
        "3V3",
        *(
            f"T{tile}/{net}"
            for tile in range(TILE_COUNT)
            for net in ("sel", "swio", "debug_tx")
        ),
    }


def test_unjustified_measurement_taps_fail(
    kicad_libs: KiCadLibraries, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control: strip P1-P3's non-input-consumers citation."""
    monkeypatch.setattr(
        "design.ci_instrumentation.measurement_taps",
        lambda: (
            AddTap(label="P1", net="F8_sclk"),
            AddTap(label="P2", net="F8_cs"),
            AddTap(label="P3", net="F8_sdata"),
        ),
    )
    plan = ci_board_plan()
    base = capture(kicad_libs, instrumented=False)
    instrumented = capture(kicad_libs)
    report = check_equivalent(
        base,
        instrumented,
        plan,
        reset_levels=reset_levels(instrumented, plan),
        budgets=BUDGETS,
    )
    assert [i.message for i in report.issues if i.severity is Severity.ERROR] == [
        f"SUP/U1.{pin} rides the declared tap on '3V3' but is bidirectional — "
        "a tap feeding non-input-class pins needs the tap's "
        "non-input-consumers justification (memo Q2)"
        for pin in (2, 3, 4)
    ]


def test_annotation_is_stable(kicad_libs: KiCadLibraries) -> None:
    circuit = capture(kicad_libs)
    first = annotate(circuit)
    assert annotate(circuit, prior=first).refs == first.refs


def test_netlist_matches_golden(kicad_libs: KiCadLibraries) -> None:
    circuit = solved(capture(kicad_libs))
    rendered = emit_netlist(apply_annotation(circuit, annotate(circuit)))
    assert rendered == GOLDEN.read_text(encoding="utf-8")


def test_netlist_byte_identical_across_runs(kicad_libs: KiCadLibraries) -> None:
    def render() -> str:
        circuit = solved(capture(kicad_libs))
        return emit_netlist(apply_annotation(circuit, annotate(circuit)))

    assert render() == render()


def test_placement_map_matches_board_copy(kicad_libs: KiCadLibraries) -> None:
    circuit = solved(capture(kicad_libs))
    renamed = apply_annotation(circuit, annotate(circuit))
    assert placement_map_json(renamed) == PLACEMENT_MAP.read_text(encoding="utf-8")
