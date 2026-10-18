"""The §7 transform plan against real Node captures (needs the KiCad libs).

The fixtures are CI-board-shaped at minimal size: one or two tile
instances of the CI variants (`design/ci_tiles.py`) chained on segment
nets, plus the real `Supervisor` capture to exercise the F1-F6
injector against its ring originator port.
The equivalence tests run the reset-state proof
(`src/oparroy/dsl/equivalence.py`) of the instrumented tile against the
uninstrumented variant with the §9 residual register as the
expected-difference set.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from design.ci_board import declare_segment_crossings
from design.ci_instrumentation import (
    BUDGETS,
    boundary_taps,
    ci_transform_plan,
    input_overrides,
    observe_taps,
    per_tile_faults,
    reset_levels,
    segment_injector,
    tree_taps,
)
from design.ci_tiles import InputNode, OutputNode
from design.supervisor import Supervisor
from oparroy.dsl import (
    AddShunt,
    AddTap,
    Circuit,
    EquivalenceReport,
    InsertSeries,
    Severity,
    Substitute,
    TileNet,
    apply_transforms,
    check,
    check_equivalent,
    raise_on_errors,
)
from oparroy.dsl.equivalence import (
    EXTRA_LOADING,
    LEAKAGE,
    SERIES_ON_RESISTANCE,
    SHUNT_OFF_CAPACITANCE,
    SWITCH_CAPACITANCE,
    TAP_CAPACITANCE,
)

if TYPE_CHECKING:
    from oparroy.dsl import KiCadLibraries

#: B1-B4 observe taps on the boundary tile (§7); B5 is a rail shunt.
BOUNDARY_TAP_COUNT = 4

#: O1/O2 (the §8 observe taps) + M1/M2 (the §5 tree taps), per tile.
PER_TILE_TAP_COUNT = 4

#: The Supervisor ports the injector fixture doesn't exercise, tied to
#: their own board nets so the instance binds its full interface.
SUPERVISOR_TIE_OFF_PORTS = (
    "usb_dp",
    "usb_dm",
    "usb_boot",
    "swio",
    "tap_rx",
    "tap_tx",
    "tap_comp",
    "tap_led",
    "srclk",
    "sdo",
    "sdi",
    "commit",
    "oe_n",
    "dbg_rx",
    "pot_pwm1",
    "pot_pwm3",
    "pot_pwm5",
    "pot_pwm7",
)

#: The originator injector's parts (§7): six 3157s + four 470 Ω legs.
SUP_INJECTOR_REFS = {
    f"FI1/{ref}"
    for ref in (
        "SWAB",
        "SWAG",
        "SWAV",
        "SWBB",
        "SWBG",
        "SWBV",
        "RAG",
        "RAV",
        "RBG",
        "RBV",
    )
}


def ci_board(libs: KiCadLibraries, tiles: list[tuple[str, type]]) -> Circuit:
    """Build a fixture board: tiles chained on segment nets, shared power."""
    board = Circuit("ci-fixture", libs)
    power = {
        "unreg": board.net("UNREG"),
        "v3v3": board.net("3V3"),
        "gnd": board.net("GND"),
    }
    faces = [
        board.bundle(
            f"seg{index}",
            **power,
            a=board.net(f"SEG{index}_A"),
            b=board.net(f"SEG{index}_B"),
        )
        for index in range(len(tiles) + 1)
    ]
    for (name, cls), upstream, downstream in zip(
        tiles, faces[:-1], faces[1:], strict=True
    ):
        board.instance(name, cls(), upstream=upstream, downstream=downstream)
    # The segment wires cross once the transforms land, exactly as on
    # the real board; SEG0_B stays stale here — without the supervisor
    # instance no always-powered part reaches it.
    declare_segment_crossings(board, len(tiles))
    return board


def two_tile_board(libs: KiCadLibraries) -> Circuit:
    """Build the boundary output tile plus one input tile, chained."""
    return ci_board(libs, [("T0", OutputNode), ("T1", InputNode)])


def net_pins(circuit: Circuit, name: str) -> set[str]:
    """Collect the pin addresses on a net, for assertions."""
    return {f"{pin.part.ref}.{pin.number}" for pin in circuit.nets[name].pins}


def errors(report: EquivalenceReport) -> list[str]:
    """Collect the ERROR-severity messages of a report."""
    return [i.message for i in report.issues if i.severity is Severity.ERROR]


def test_plan_applies_to_a_single_tile(kicad_libs: KiCadLibraries) -> None:
    board = ci_board(kicad_libs, [("T0", OutputNode)])
    handles = apply_transforms(board, ci_transform_plan())
    tile = board.instances["T0"].circuit
    # F1: TX_A splits at PHY1/Rat.b; the port stays as the #b side.
    assert net_pins(tile, "TX_A#a") == {"PHY1/Rat.2", "FI1/SWAB.4"}
    assert net_pins(tile, "TX_A") == {
        "J2.5",
        "PHY1/Dat.1",
        "FI1/SWAB.3",
        "FI1/SWAG.4",
        "FI1/SWAV.4",
    }
    # F4: RX_B splits at PHY1/Rbr.a.
    assert net_pins(tile, "RX_B#a") == {"PHY1/Rbr.1", "FI1/SWBB.4"}
    # F7: ka splits U1.PD3 off the watchdog stub; the stub parks low.
    assert net_pins(tile, "ka#a") == {"U1.20", "FI1/SWKA.4"}
    assert net_pins(tile, "ka#b") == {"WD1/Rs.1", "FI1/SWKA.3", "FI1/RKA.1"}
    # F8: 3V3N is exactly the §3 domain plus the switch drain.
    assert net_pins(tile, "3V3N") == {
        "U1.9",
        "C1.1",
        "C2.1",
        "TP2.1",
        "PHY1/Rth1.1",
        "SL1/Rp.1",
        "SL1/Dd.2",
        "FI1/QPW.3",
    }
    # The always rail keeps the bypass switch, the DNP Schmitt, the
    # injector VCCs, the shunt/defeat leg sources, and the P-FET source.
    v3v3 = net_pins(tile, "3V3")
    assert {
        "PHY1/SW1.5",
        "PHY1/BUF1.5",
        "FI1/QPW.2",
        "FI1/RAV.2",
        "FI1/RBV.2",
        "FI1/RWD.2",
    } <= v3v3
    for ref in ("FI1/SWAB", "FI1/SWAG", "FI1/SWAV", "FI1/SWBB", "FI1/SWBG"):
        assert tile.parts[ref].pin("5").net is tile.nets["3V3"]  # VCC
    # The eight per-tile controls escaped as board nets (§8's slice).
    for bit in (
        "BRK_A",
        "SHG_A",
        "SHV_A",
        "BRK_B",
        "SHG_B",
        "SHV_B",
        "KA_CUT",
        "PWR",
    ):
        assert handles[TileNet(("T0",), bit)].name == f"T0/{bit}"
    # B1-B4 taps escaped; B5's defeat shunt hangs on sel.
    for tap in ("opa_p", "opo", "led_work"):
        assert handles[TileNet(("T0",), tap)].name == f"T0/{tap}"
    assert handles[TileNet(("T0",), "TX_A#b")] is board.nets["SEG1_A"]
    assert net_pins(tile, "sel") >= {"FI1/SWWD.4"}
    # B5's defeat leg carries the §2 shunt idiom's 470 Ω bound.
    assert net_pins(tile, "B5_leg") == {"FI1/SWWD.1", "FI1/RWD.1"}


def test_plan_applies_to_multiple_tiles(kicad_libs: KiCadLibraries) -> None:
    board = two_tile_board(kicad_libs)
    handles = apply_transforms(board, ci_transform_plan())
    for tile in ("T0", "T1"):
        assert "FI1/SWAB" in board.instances[tile].circuit.parts
        assert "FI1/QPW" in board.instances[tile].circuit.parts
    # The H-set lands only on the input tile; the defeat only on T0.
    t1 = board.instances["T1"].circuit
    assert {"FI1/SWPOT", "FI1/QBA", "FI1/QBB", "FI1/RPF", "FI1/CPF"} <= set(t1.parts)
    assert "FI1/SWWD" not in t1.parts
    assert "FI1/SWPOT" not in board.instances["T0"].circuit.parts
    # The input tile's 3V3N gains the payload rail pins (§6).
    assert {"POT1.1", "RPA.2", "RPB.2"} <= net_pins(t1, "3V3N")
    # H1: the mux cuts pot_w at the wiper; the RC filter sits between
    # the escaped supervisor source and B2.
    assert net_pins(t1, "pot_w#a") == {"POT1.2", "FI1/SWPOT.3"}
    assert net_pins(t1, "pot_w#b") == {"RSP.1", "FI1/SWPOT.4"}
    assert net_pins(t1, "H1_filt") == {"FI1/SWPOT.1", "FI1/RPF.2", "FI1/CPF.1"}
    assert net_pins(t1, "POT_PWM") == {"FI1/RPF.1"}
    # H2/H3: the override FETs shunt the raw button nodes, gates pulled down.
    assert net_pins(t1, "btn_a") >= {"FI1/QBA.3"}
    assert net_pins(t1, "BTN_A") == {"FI1/QBA.1", "FI1/RBA.1"}
    assert handles[TileNet(("T1",), "POT_PWM")].name == "T1/POT_PWM"
    assert handles[TileNet(("T1",), "BTN_B")].name == "T1/BTN_B"


def test_all_doc_named_targets_resolve(kicad_libs: KiCadLibraries) -> None:
    """Every §7 row's part lands, provenance-tagged, on both tile roles."""
    board = two_tile_board(kicad_libs)
    apply_transforms(board, ci_transform_plan())
    expected = {
        "T0": {
            "FI1/SWAB",
            "FI1/SWAG",
            "FI1/SWAV",
            "FI1/SWBB",
            "FI1/SWBG",
            "FI1/SWBV",
            "FI1/SWKA",
            "FI1/QPW",
            "FI1/RAG",
            "FI1/RAV",
            "FI1/RBG",
            "FI1/RBV",
            "FI1/RKA",
            "FI1/RPW",
            "FI1/SWWD",
            "FI1/RWD",
        },
        "T1": {
            "FI1/SWAB",
            "FI1/SWAG",
            "FI1/SWAV",
            "FI1/SWBB",
            "FI1/SWBG",
            "FI1/SWBV",
            "FI1/SWKA",
            "FI1/QPW",
            "FI1/RAG",
            "FI1/RAV",
            "FI1/RBG",
            "FI1/RBV",
            "FI1/RKA",
            "FI1/RPW",
            "FI1/SWPOT",
            "FI1/RPF",
            "FI1/CPF",
            "FI1/QBA",
            "FI1/RBA",
            "FI1/QBB",
            "FI1/RBB",
        },
    }
    for tile, refs in expected.items():
        parts = board.instances[tile].circuit.parts
        assert refs <= set(parts)
        assert all(parts[ref].provenance is not None for ref in refs)


def test_bit_zero_is_the_plain_board(kicad_libs: KiCadLibraries) -> None:
    """The §8 invariant: reset_levels derives all-zeros from the plan."""
    board = two_tile_board(kicad_libs)
    plan = ci_transform_plan()
    apply_transforms(board, plan)
    levels = reset_levels(board, plan)
    assert set(levels.values()) == {0}
    # 8 per tile + WD_DEFEAT on T0 + 3 overrides on T1.
    assert len(levels) == 8 + 1 + 8 + 3
    assert TileNet(("T0",), "WD_DEFEAT") in levels
    assert TileNet(("T1",), "POT_SEL") in levels
    # Structural bit-0: every break switch passes on B1 (S low), every
    # shunt hangs on B2, the P-FET gate pulls down to on, the pot mux
    # selects the human wiper on B1.
    tile = board.instances["T0"].circuit
    assert tile.parts["FI1/SWAB"].pin("3").net is tile.nets["TX_A"]  # B1 = pass
    shunt_net = tile.parts["FI1/SWAG"].pin("1").net
    assert shunt_net is not None
    assert shunt_net.name == "F2_leg"  # B2 = shunt
    assert tile.parts["FI1/SWAG"].pin("3").net is None  # B1 = NC
    pwr = tile.nets["PWR"]
    assert tile.parts["FI1/QPW"].pin("1").net is pwr  # gate
    assert tile.parts["FI1/RPW"].pin("1").net is pwr  # 47k PD = POR on
    t1 = board.instances["T1"].circuit
    assert t1.parts["FI1/SWPOT"].pin("3").net is t1.nets["pot_w#a"]  # B1 = wiper


def test_supervisor_port_injector(kicad_libs: KiCadLibraries) -> None:
    """The F1-F6 records instrument the supervisor originator port (§7)."""
    board = ci_board(kicad_libs, [("T0", OutputNode)])
    board.instance(
        "SUP",
        Supervisor(),
        TX_A=board.nets["SEG0_A"],
        RX_B=board.nets["SEG0_B"],
        RX_A=board.net("SEG8_A"),
        TX_B=board.net("SEG8_B"),
        GND=board.nets["GND"],
        **{name: board.net(f"SUP_{name}") for name in SUPERVISOR_TIE_OFF_PORTS},
        **{"3V3": board.nets["3V3"]},
    )
    plan = ci_transform_plan(
        supervisor_port=("SUP",),
        supervisor_nets=("TX_A", "Rat.b", "RX_B", "Rbr.a"),
    )
    handles = apply_transforms(board, plan)
    sup = board.instances["SUP"].circuit
    assert net_pins(sup, "TX_A#a") == {"Rat.2", "FI1/SWAB.4"}
    assert net_pins(sup, "TX_A") == {
        "Dat.1",
        "FI1/SWAB.3",
        "FI1/SWAG.4",
        "FI1/SWAV.4",
    }
    assert net_pins(sup, "RX_B#a") == {"Rbr.1", "FI1/SWBB.4"}
    for bit in ("BRK_A", "SHG_A", "SHV_A", "BRK_B", "SHG_B", "SHV_B"):
        assert handles[TileNet(("SUP",), bit)].name == f"SUP/{bit}"
    # The drain port stays bare (§7: tile 7's injector covers that
    # segment) — no injector parts beyond the originator's set.
    assert net_pins(sup, "RX_A") == {"Rar.1"}
    assert net_pins(sup, "TX_B") == {"Rbt.2"}
    extras = {ref for ref in sup.parts if ref.startswith("FI1/")} - SUP_INJECTOR_REFS
    assert not extras


def test_instrumented_fixture_passes_check(kicad_libs: KiCadLibraries) -> None:
    board = two_tile_board(kicad_libs)
    apply_transforms(board, ci_transform_plan())
    raise_on_errors(check(board, footprints=kicad_libs))


def test_reset_state_equivalence(kicad_libs: KiCadLibraries) -> None:
    """Instrumented tiles ≡ the uninstrumented variants, modulo the §9 set."""
    base = two_tile_board(kicad_libs)
    instrumented = two_tile_board(kicad_libs)
    plan = ci_transform_plan()
    apply_transforms(instrumented, plan)
    report = check_equivalent(
        base,
        instrumented,
        plan,
        reset_levels=reset_levels(instrumented, plan),
        budgets=BUDGETS,
    )
    assert errors(report) == []
    assert all(r.citation is not None for r in report.residuals)
    kinds = [r.kind for r in report.residuals]
    # T0 (boundary output tile): F1-F8 + B1-B5; T1 (input): F1-F8 + H1-H3.
    assert kinds.count(SERIES_ON_RESISTANCE) == 4 + 5  # F1/F4/F7/F8 + H1
    assert kinds.count(SWITCH_CAPACITANCE) == 3 + 4
    assert kinds.count(LEAKAGE) == 8 + 10
    assert kinds.count(SHUNT_OFF_CAPACITANCE) == 5 + 6
    assert kinds.count(EXTRA_LOADING) == 7 + 10  # + B5's 470 Ω leg resistor
    assert kinds.count(TAP_CAPACITANCE) == BOUNDARY_TAP_COUNT + 2 * PER_TILE_TAP_COUNT
    taps = [r for r in report.residuals if r.kind == TAP_CAPACITANCE]
    assert {r.net for r in taps} == {
        "T0/opa_p",
        "SEG1_A",
        "T0/opo",
        "T0/led_work",
        "T0/sel",
        "T0/swio",
        "T0/debug_tx",
        "T1/sel",
        "T1/swio",
        "T1/debug_tx",
        # The 3V3N observe taps reduce to the rail they were cut from.
        "3V3",
    }
    assert all(r.layout_obligation for r in taps)
    # The power cut's residual lands on the rail, R5-class, alongside
    # the two 3V3N observe-tap stubs.
    r5 = [r for r in report.residuals if r.net == "3V3"]
    assert {(r.kind, r.magnitude) for r in r5} == {
        (SERIES_ON_RESISTANCE, "0.085 Ω"),
        (EXTRA_LOADING, "47k"),
        (TAP_CAPACITANCE, "stub geometry — bounded, not known (memo Q3)"),
    }


def test_residual_without_a_budget_errors(kicad_libs: KiCadLibraries) -> None:
    """The §9 register is load-bearing: drop a citation and the proof fails."""
    base = two_tile_board(kicad_libs)
    instrumented = two_tile_board(kicad_libs)
    plan = ci_transform_plan()
    apply_transforms(instrumented, plan)
    budgets = {k: v for k, v in BUDGETS.items() if k != LEAKAGE}
    report = check_equivalent(
        base,
        instrumented,
        plan,
        reset_levels=reset_levels(instrumented, plan),
        budgets=budgets,
    )
    assert any("has no budget citation" in m for m in errors(report))


def test_plan_records_are_data() -> None:
    """The plan is the §7 list: kinds and targets as the doc's tables."""
    faults = per_tile_faults()
    assert [t.label for t in faults] == ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8"]
    assert isinstance(faults[0], InsertSeries)
    assert faults[0].net == "TX_A"
    assert isinstance(faults[1], AddShunt)
    assert faults[1].net == "TX_A#b"
    assert isinstance(faults[6], InsertSeries)
    assert faults[6].net == "ka"
    assert faults[6].pins == ("U1.pd3",)
    assert isinstance(faults[7], InsertSeries)
    assert faults[7].net == "3V3"
    assert faults[7].name == "3V3N"
    boundary = boundary_taps()
    assert [t.label for t in boundary] == ["B1", "B2", "B3", "B4", "B5"]
    assert [t.net for t in boundary[:4]] == ["opa_p", "TX_A#b", "opo", "led_work"]
    # The boundary taps feed the supervisor's bidirectional GPIOs.
    taps = [t for t in boundary if isinstance(t, AddTap)]
    assert all(t.non_input_consumers for t in taps)
    assert isinstance(boundary[4], AddShunt)
    assert boundary[4].rail == "3V3"
    observe = observe_taps()
    assert [t.label for t in observe] == ["O1", "O2"]
    assert [t.net for t in observe] == ["sel", "3V3N"]
    trees = tree_taps()
    assert [t.label for t in trees] == ["M1", "M2"]
    assert [t.net for t in trees] == ["swio", "debug_tx"]
    # The tree taps feed the 3157 channel pins and the leaf pull-ups.
    assert all(t.non_input_consumers for t in trees)
    overrides = input_overrides()
    assert [t.label for t in overrides] == ["H1", "H2", "H3"]
    assert isinstance(overrides[0], Substitute)
    assert overrides[0].source == "POT_PWM"
    injector = segment_injector()
    assert [t.label for t in injector] == ["F1", "F2", "F3", "F4", "F5", "F6"]
