"""Reset-state equivalence-proof tests (docs/instrumentation-equivalence-2026-09-29.md).

The fixture is the memo §5 slice: a minimal base board (one tile, two
nets) plus one series insert (``F1`` on the TX port) and one tap
(``B1`` on the internal ``sense`` net) passes; a tampered variant with
a base part deleted fails the bijection; a residual without a budget
citation errors. The tile carries a cap on TX so the series cut leaves
pins on both sides.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from oparroy.dsl import (
    AddShunt,
    AddTap,
    Circuit,
    EquivalenceReport,
    InsertSeries,
    Net,
    PerInstance,
    PerTile,
    Residuals,
    Resistor,
    Severity,
    Subcircuit,
    TileNet,
    TransformPart,
    TypedPart,
    apply_transforms,
    check_equivalent,
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
    from collections.abc import Callable

    from conftest import StubSymbols


class StubSwitch(TypedPart):
    """SPDT analog-switch stub (``Stub:SW``) carrying residual data.

    ``a`` common, ``b1``/``b2`` throws, ``s`` the select (the symbol's
    only input-class pin). ``b2`` is optional, so a record can leave a
    throw unconnected. The residuals mirror the 74LVC1G3157 class the
    CI board's switches come from.
    """

    symbol = "Stub:SW"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "a": "1",
        "b1": "2",
        "b2": "3",
        "s": "4",
    }
    required_pins: ClassVar[frozenset[str]] = frozenset({"a", "b1", "s"})
    default_footprint = "StubFP:SOT-363"
    residuals: ClassVar[Residuals | None] = Residuals(
        on_resistance_ohm=25.0,
        on_capacitance_pf=17.3,
        off_capacitance_pf=5.2,
        leakage_ua=1.0,
    )

    def __init__(  # noqa: PLR0913 — one keyword per physical pin
        self,
        *,
        a: Net | str,
        b1: Net | str,
        s: Net | str,
        b2: Net | str | None = None,
        value: str | None = None,
        footprint: str | None = None,
    ) -> None:
        nets: dict[str, Net | str] = {"a": a, "b1": b1, "s": s}
        if b2 is not None:
            nets["b2"] = b2
        super().__init__(value, footprint, nets)


class StubProbe(TypedPart):
    """The supervisor's tap pin (``Stub:SW`` pin 4, input-class)."""

    symbol = "Stub:SW"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {"sense": "4"}
    default_footprint = "StubFP:SOT-363"

    def __init__(self, *, sense: Net | str, footprint: str | None = None) -> None:
        super().__init__(None, footprint, {"sense": sense})


def tile_capture(circuit: Circuit) -> None:
    """Minimal tile: a series R and a clamp cap across TX, a sensed net."""
    tx = circuit.port("TX")
    gnd = circuit.port("GND")
    sense = circuit.net("sense")
    circuit.part("Rat", Resistor("470", a=sense, b=tx, footprint="StubFP:R_0603"))
    circuit.part("Dat", Resistor("470", a=tx, b=gnd, footprint="StubFP:R_0603"))
    circuit.part("Rwd", Resistor("220", a=sense, b=gnd, footprint="StubFP:R_0603"))


def tampered_tile_capture(circuit: Circuit) -> None:
    """Omit the watchdog-class resistor — capture drift."""
    tx = circuit.port("TX")
    gnd = circuit.port("GND")
    sense = circuit.net("sense")
    circuit.part("Rat", Resistor("470", a=sense, b=tx, footprint="StubFP:R_0603"))
    circuit.part("Dat", Resistor("470", a=tx, b=gnd, footprint="StubFP:R_0603"))


def build_base(
    symbols: StubSymbols, tile: Callable[[Circuit], None] = tile_capture
) -> Circuit:
    """Build the plain board: one tile on a segment net."""
    board = Circuit("base", symbols)
    board.instance("T0", tile, TX=board.net("SEG"), GND=board.net("GND"))
    return board


def f1() -> InsertSeries:
    """Build the break-switch record on the TX port."""
    return InsertSeries(
        label="F1",
        net="TX",
        pins=("Rat.b",),
        part=TransformPart("FI1/SWAB", StubSwitch(a="@b", b1="@a", s="@control")),
        control="BRK",
    )


def f2() -> AddShunt:
    """Build the short-to-GND leg on the interface side of the break switch."""
    return AddShunt(
        label="F2",
        net="TX#b",
        rail="GND",
        part=TransformPart("FI1/SWAG", StubSwitch(a="@net", b1="@leg", s="@control")),
        control="SHG",
        extra=(
            TransformPart(
                "FI1/RSG",
                Resistor("470", a="@leg", b="GND", footprint="StubFP:R_0603"),
            ),
        ),
    )


def b1() -> AddTap:
    """Build the sense-net tap."""
    return AddTap(label="B1", net="sense")


def build_instrumented(
    symbols: StubSymbols, tile: Callable[[Circuit], None] = tile_capture
) -> Circuit:
    """Build the instrumented board: base + the plan applied + scan stubs."""
    board = build_base(symbols, tile)
    handles = apply_transforms(board, [PerInstance(("T0",), (f1(), b1()))])
    board.part(
        "SCAN",
        StubSwitch(
            a=board.net("SCAN_A"),
            b1=board.net("SCAN_B"),
            s=handles[TileNet(("T0",), "BRK")],
        ),
    )
    board.part("PROBE", StubProbe(sense=handles[TileNet(("T0",), "sense")]))
    return board


RESET_LEVELS: dict[TileNet, int] = {TileNet(("T0",), "BRK"): 0}
BUDGETS = {
    SERIES_ON_RESISTANCE: "§2 tb_decode swept the inserted-switch path",
    SWITCH_CAPACITANCE: "§2 margins flat across 47 pF-1 nF",
    LEAKAGE: "§4 charge-pump margin",
    TAP_CAPACITANCE: "§6 short-stub contract",
}


def errors(report: EquivalenceReport) -> list[str]:
    """Collect the ERROR-severity messages of a report."""
    return [i.message for i in report.issues if i.severity is Severity.ERROR]


def test_reset_state_equivalent(symbols: StubSymbols) -> None:
    report = check_equivalent(
        build_base(symbols),
        build_instrumented(symbols),
        [PerInstance(("T0",), (f1(), b1()))],
        reset_levels=RESET_LEVELS,
        budgets=BUDGETS,
    )
    assert errors(report) == []
    assert {r.kind for r in report.residuals} == {
        SERIES_ON_RESISTANCE,
        SWITCH_CAPACITANCE,
        LEAKAGE,
        TAP_CAPACITANCE,
    }
    tap = next(r for r in report.residuals if r.kind == TAP_CAPACITANCE)
    assert tap.net == "T0/sense"
    assert tap.layout_obligation
    assert all(r.citation is not None for r in report.residuals)


def test_shunt_reduces_to_absent_branch(symbols: StubSymbols) -> None:
    plan = [PerInstance(("T0",), (f1(), f2(), b1()))]
    board = build_base(symbols)
    handles = apply_transforms(board, plan)
    board.part(
        "SCAN",
        StubSwitch(
            a=board.net("SCAN_A"),
            b1=board.net("SCAN_B"),
            s=handles[TileNet(("T0",), "BRK")],
        ),
    )
    board.part(
        "SCAN2",
        StubSwitch(
            a=board.net("SCAN2_A"),
            b1=board.net("SCAN2_B"),
            s=handles[TileNet(("T0",), "SHG")],
        ),
    )
    board.part("PROBE", StubProbe(sense=handles[TileNet(("T0",), "sense")]))
    levels: dict[TileNet, int] = {
        TileNet(("T0",), "BRK"): 0,
        TileNet(("T0",), "SHG"): 0,
    }
    report = check_equivalent(
        build_base(symbols),
        board,
        plan,
        reset_levels=levels,
        budgets=BUDGETS
        | {
            SHUNT_OFF_CAPACITANCE: "§4 timing constants unchanged",
            EXTRA_LOADING: "§4 glitch-filter timing non-critical",
        },
    )
    assert errors(report) == []
    assert {r.kind for r in report.residuals} >= {
        SHUNT_OFF_CAPACITANCE,
        EXTRA_LOADING,
    }


def test_base_part_deleted_fails_the_bijection(symbols: StubSymbols) -> None:
    report = check_equivalent(
        build_base(symbols),
        build_instrumented(symbols, tile=tampered_tile_capture),
        [PerInstance(("T0",), (f1(), b1()))],
        reset_levels=RESET_LEVELS,
        budgets=BUDGETS,
    )
    assert any("T0/Rwd: base part lost" in m for m in errors(report))


def test_base_pin_reconnected_fails(symbols: StubSymbols) -> None:
    def rewired_tile(circuit: Circuit) -> None:
        # Rwd's top pin moves from sense to GND — the transforms still
        # apply, so the drift reaches the proof.
        tx = circuit.port("TX")
        gnd = circuit.port("GND")
        sense = circuit.net("sense")
        circuit.part("Rat", Resistor("470", a=sense, b=tx, footprint="StubFP:R_0603"))
        circuit.part("Dat", Resistor("470", a=tx, b=gnd, footprint="StubFP:R_0603"))
        circuit.part("Rwd", Resistor("220", a=gnd, b=gnd, footprint="StubFP:R_0603"))

    report = check_equivalent(
        build_base(symbols),
        build_instrumented(symbols, tile=rewired_tile),
        [PerInstance(("T0",), (f1(), b1()))],
        reset_levels=RESET_LEVELS,
        budgets=BUDGETS,
    )
    assert any("T0/Rwd.1: re-connected" in m for m in errors(report))


def test_residual_without_a_budget_errors(symbols: StubSymbols) -> None:
    budgets = {k: v for k, v in BUDGETS.items() if k != SERIES_ON_RESISTANCE}
    report = check_equivalent(
        build_base(symbols),
        build_instrumented(symbols),
        [PerInstance(("T0",), (f1(), b1()))],
        reset_levels=RESET_LEVELS,
        budgets=budgets,
    )
    assert any(
        f"residual {SERIES_ON_RESISTANCE} on 'SEG' has no budget citation" in m
        for m in errors(report)
    )


def test_control_without_reset_level_errors(symbols: StubSymbols) -> None:
    report = check_equivalent(
        build_base(symbols),
        build_instrumented(symbols),
        [PerInstance(("T0",), (f1(), b1()))],
        reset_levels={},
        budgets=BUDGETS,
    )
    assert any("T0/BRK: no reset level declared" in m for m in errors(report))


def test_nonzero_reset_level_errors(symbols: StubSymbols) -> None:
    levels: dict[TileNet, int] = {TileNet(("T0",), "BRK"): 1}
    report = check_equivalent(
        build_base(symbols),
        build_instrumented(symbols),
        [PerInstance(("T0",), (f1(), b1()))],
        reset_levels=levels,
        budgets=BUDGETS,
    )
    assert any("T0/BRK: reset level 1" in m for m in errors(report))


def test_undeclared_observer_pin_errors(symbols: StubSymbols) -> None:
    board = build_base(symbols)
    apply_transforms(board, [PerInstance(("T0",), (f1(),))])
    # An observer hung on the segment net with no tap declared.
    board.part("PROBE", StubProbe(sense=board.nets["SEG"]))
    report = check_equivalent(
        build_base(symbols),
        board,
        [PerInstance(("T0",), (f1(),))],
        reset_levels=RESET_LEVELS,
        budgets=BUDGETS,
    )
    assert any(
        "PROBE.4 lands on base net 'SEG' with no declared tap" in m
        for m in errors(report)
    )


def test_non_input_tap_pin_errors(symbols: StubSymbols) -> None:
    board = build_base(symbols)
    handles = apply_transforms(board, [PerInstance(("T0",), (f1(), b1()))])
    # The tap wired to a passive pin, not an input-class one.
    board.part(
        "PROBE",
        symbol="Stub:CONN6",
        value="Probe",
        footprint="StubFP:CONN_1x06",
    )
    board.connect(handles[TileNet(("T0",), "sense")], board.parts["PROBE"][1])
    report = check_equivalent(
        build_base(symbols),
        board,
        [PerInstance(("T0",), (f1(), b1()))],
        reset_levels=RESET_LEVELS,
        budgets=BUDGETS,
    )
    assert any("taps must be high-impedance" in m for m in errors(report))


def test_waiver_degrades_and_stale_waiver_warns(symbols: StubSymbols) -> None:
    instrumented = build_instrumented(symbols, tile=tampered_tile_capture)
    instrumented.waive("equivalence", "T0/Rwd", reason="known drift, bench-only")
    instrumented.waive("equivalence", "T0/Nope", reason="stale")
    report = check_equivalent(
        build_base(symbols),
        instrumented,
        [PerInstance(("T0",), (f1(), b1()))],
        reset_levels=RESET_LEVELS,
        budgets=BUDGETS,
    )
    assert errors(report) == []
    waived = [i for i in report.issues if i.severity is Severity.WAIVED]
    assert any("T0/Rwd: base part lost" in i.message for i in waived)
    assert any(
        i.severity is Severity.WARNING and "matched no issue" in i.message
        for i in report.issues
    )


def test_power_rails_accept_scan_plane_loading(symbols: StubSymbols) -> None:
    def with_rail(board: Circuit) -> None:
        v3v3 = board.net("3V3")
        pwr = board.part("P1", symbol="power:+3V3")
        board.connect(v3v3, pwr[1])

    base = build_base(symbols)
    with_rail(base)
    instrumented = build_instrumented(symbols)
    with_rail(instrumented)
    # The scan plane's supply pin lands on the base rail — allowed:
    # rails exist to be loaded; their budget is the power tree's.
    instrumented.connect("3V3", instrumented.parts["SCAN"][3])
    report = check_equivalent(
        base,
        instrumented,
        [PerInstance(("T0",), (f1(), b1()))],
        reset_levels=RESET_LEVELS,
        budgets=BUDGETS,
    )
    assert errors(report) == []


def test_per_tile_composes_over_instances(symbols: StubSymbols) -> None:
    class Tile(Subcircuit):
        """The tile as a subcircuit, for per-tile keying."""

        def capture(self, circuit: Circuit) -> None:
            tile_capture(circuit)

    def build(symbols: StubSymbols) -> Circuit:
        board = Circuit("base", symbols)
        seg_a = board.net("SEG_A")
        seg_b = board.net("SEG_B")
        gnd = board.net("GND")
        board.instance("T0", Tile(), TX=seg_a, GND=gnd)
        board.instance("T1", Tile(), TX=seg_b, GND=gnd)
        return board

    plan = [PerTile(Tile, (f1(), b1()))]
    base = build(symbols)
    instrumented = build(symbols)
    handles = apply_transforms(instrumented, plan)
    for tile in ("T0", "T1"):
        instrumented.part(
            f"PROBE_{tile}", StubProbe(sense=handles[TileNet((tile,), "sense")])
        )
    levels: dict[TileNet, int] = {
        TileNet(("T0",), "BRK"): 0,
        TileNet(("T1",), "BRK"): 0,
    }
    report = check_equivalent(
        base,
        instrumented,
        plan,
        reset_levels=levels,
        budgets=BUDGETS,
    )
    assert errors(report) == []
    assert {r.net for r in report.residuals if r.kind == TAP_CAPACITANCE} == {
        "T0/sense",
        "T1/sense",
    }


def test_tap_on_split_internal_net_side(symbols: StubSymbols) -> None:
    """A tap on the #a side of a split internal net reduces to the base net."""
    cut = InsertSeries(
        label="F9",
        net="sense",
        pins=("Rwd.a",),
        part=TransformPart("FI9/SWS", StubSwitch(a="@b", b1="@a", s="@control")),
        control="SCT",
    )
    tap = AddTap(label="B2", net="sense#a")
    plan = [PerInstance(("T0",), (f1(), cut, tap))]
    board = build_base(symbols)
    handles = apply_transforms(board, plan)
    board.part("PROBE", StubProbe(sense=handles[TileNet(("T0",), "sense#a")]))
    levels: dict[TileNet, int] = {
        TileNet(("T0",), "BRK"): 0,
        TileNet(("T0",), "SCT"): 0,
    }
    report = check_equivalent(
        build_base(symbols),
        board,
        plan,
        reset_levels=levels,
        budgets=BUDGETS,
    )
    assert errors(report) == []
    tap_residual = next(r for r in report.residuals if r.kind == TAP_CAPACITANCE)
    assert tap_residual.net == "T0/sense"


def test_port_passthrough_chain_resolves(symbols: StubSymbols) -> None:
    """A port wired straight through to a deeper instance resolves (flatten parity)."""

    class Inner(Subcircuit):
        def capture(self, circuit: Circuit) -> None:
            vin = circuit.port("vin")
            gnd = circuit.port("gnd")
            circuit.part(
                "Rin", Resistor("470", a=vin, b=gnd, footprint="StubFP:R_0603")
            )

    class Outer(Subcircuit):
        def capture(self, circuit: Circuit) -> None:
            vin = circuit.port("vin")
            gnd = circuit.port("gnd")
            circuit.instance("IN1", Inner(), vin=vin, gnd=gnd)

    def build(symbols: StubSymbols) -> Circuit:
        board = Circuit("base", symbols)
        board.instance("T0", Outer(), vin=board.net("SIG"), gnd=board.net("GND"))
        return board

    report = check_equivalent(
        build(symbols), build(symbols), [], reset_levels={}, budgets={}
    )
    assert errors(report) == []
