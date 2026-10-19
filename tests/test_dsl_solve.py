"""Solve-pass tests: resolution, reporting, and the pipeline-order guards.

The guard tests are the negative controls (konnect-lessons.md §5): a
spec no bin can meet, a spec on a bin-less part, and a spec reaching
``check`` or an emitter unsolved must each fail loudly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from oparroy.dsl import (
    Circuit,
    DefinitionError,
    DividerResolution,
    DividerSpec,
    Generator,
    GeneratorEvaluation,
    InsertSeries,
    PartRecord,
    PartsDb,
    PerInstance,
    PowerDomainKind,
    Resistor,
    Resolution,
    Severity,
    SolveContext,
    TransformPart,
    ValueBin,
    ValueRange,
    apply_transforms,
    check,
    emit_netlist,
    emit_spice,
    solve,
)

if TYPE_CHECKING:
    from conftest import StubSymbols

R_BIN = ValueBin(kind="resistor", series=24, tolerance=0.01, lo=1.0, hi=1e6)
C_BIN = ValueBin(kind="capacitor", series=12, tolerance=0.10, lo=1e-12, hi=1e-6)
EXACT_10K = 10_000.0
NEAREST_1K = 1_000.0
OFF_NOMINAL = 1030.0
TIE_TARGET = 4900.0
TIE_LOW = 4_700.0
TIE_HIGH = 5_100.0


class RBin(Resistor):
    """A stub bin class carrying a stocked value grid (``Stub:R``)."""

    symbol = "Stub:R"
    default_footprint = "StubFP:R_0603"
    value_bin = R_BIN


class CBin(Resistor):
    """A resistor carrying a capacitor grid — the kind guard's negative control."""

    symbol = "Stub:R"
    default_footprint = "StubFP:R_0603"
    value_bin = C_BIN


def spec_circuit(symbols: StubSymbols, value: str | ValueRange) -> Circuit:
    """Build a one-part circuit: R1 between nets a/b, from the bin."""
    c = Circuit("test", symbols)
    a, b = c.net("a"), c.net("b")
    c.part("R1", RBin(value, a=a, b=b))
    return c


def errors(messages: list[str]) -> list[str]:
    return [message for message in messages if "error" in message]


def test_spec_resolves_and_mutates_the_part(symbols: StubSymbols) -> None:
    c = spec_circuit(symbols, ValueRange.around("10k", 0.05, family="resistor"))
    report = solve(c)
    assert report.issues == []
    assert c.parts["R1"].value == "10k"
    (resolution,) = report.resolutions
    assert isinstance(resolution, Resolution)
    assert resolution.path == "R1"
    assert resolution.chosen == pytest.approx(EXACT_10K)
    assert resolution.chosen_str == "10k"
    assert resolution.rel_error == pytest.approx(0.0)
    assert str(report) == "R1: 10k ±5% → 10k (achieved +0.0%)"


def test_resolution_reports_the_achieved_error(symbols: StubSymbols) -> None:
    c = spec_circuit(symbols, ValueRange.around(OFF_NOMINAL, 0.05, family="resistor"))
    report = solve(c)
    (resolution,) = report.resolutions
    assert isinstance(resolution, Resolution)
    assert resolution.chosen == pytest.approx(NEAREST_1K)
    assert resolution.rel_error == pytest.approx(-30 / 1030, rel=1e-6)
    assert "(achieved -2.9%)" in str(report)


def test_literal_values_are_never_touched(symbols: StubSymbols) -> None:
    c = spec_circuit(symbols, "470")
    report = solve(c)
    assert c.parts["R1"].value == "470"
    assert report.resolutions == []
    assert str(report) == ""


def test_identical_specs_consolidate(symbols: StubSymbols) -> None:
    c = Circuit("test", symbols)
    a, b = c.net("a"), c.net("b")
    c.part("R1", RBin(ValueRange.around(TIE_TARGET, 0.05), a=a, b=b))
    c.part("R2", RBin("5k1", a=a, b=b))
    report = solve(c)
    # The spec's exact tie (4k7 vs 5k1) breaks toward the in-use 5k1.
    assert c.parts["R1"].value == "5k1"
    (resolution,) = report.resolutions
    assert isinstance(resolution, Resolution)
    assert resolution.chosen == pytest.approx(TIE_HIGH)
    assert resolution.chosen != TIE_LOW


def test_unresolvable_spec_is_an_error(symbols: StubSymbols) -> None:
    c = spec_circuit(symbols, ValueRange.around("10M", 0.05, family="resistor"))
    report = solve(c)
    (issue,) = report.issues
    assert issue.severity is Severity.ERROR
    assert "no value in the resistor bin" in issue.message
    assert report.resolutions == []


def test_spec_on_a_binless_part_is_an_error(symbols: StubSymbols) -> None:
    c = Circuit("test", symbols)
    a, b = c.net("a"), c.net("b")
    spec = ValueRange.around("10k", 0.05, family="resistor")
    part = c.part("R1", symbol="Stub:R", value=spec, footprint="StubFP:R_0603")
    c.connect(a, part[1])
    c.connect(b, part[2])
    report = solve(c)
    (issue,) = report.issues
    assert issue.severity is Severity.ERROR
    assert "no value bin" in issue.message


def test_unsolved_spec_fails_check(symbols: StubSymbols) -> None:
    c = spec_circuit(symbols, ValueRange.around("10k", 0.05, family="resistor"))
    messages = [issue.message for issue in check(c) if issue.severity is Severity.ERROR]
    (message,) = [m for m in messages if "unresolved value spec" in m]
    assert "run solve before check" in message


def test_unsolved_spec_fails_netlist_emit(symbols: StubSymbols) -> None:
    c = spec_circuit(symbols, ValueRange.around("10k", 0.05, family="resistor"))
    with pytest.raises(DefinitionError, match="run solve"):
        emit_netlist(c)


def test_unsolved_spec_fails_spice_emit(symbols: StubSymbols) -> None:
    c = Circuit("test", symbols)
    a, b = c.net("a"), c.net("b")
    spec = ValueRange.around("10k", 0.05, family="resistor")
    part = c.part("R1", symbol="Device:R", value=spec, footprint="StubFP:R_0603")
    c.connect(a, part[1])
    c.connect(b, part[2])
    with pytest.raises(DefinitionError, match="run solve"):
        emit_spice(c)


def test_bind_threads_the_bin(symbols: StubSymbols) -> None:
    db = PartsDb(
        [
            PartRecord(
                name="r-stub",
                kind="resistor",
                symbol="Stub:R",
                footprint="StubFP:R_0603",
                bin=R_BIN,
            )
        ]
    )
    bound = db.bind("r-stub", Resistor, class_name="RStub")
    assert bound.value_bin is R_BIN
    c = Circuit("test", symbols)
    a, b = c.net("a"), c.net("b")
    placed = c.part(
        "R1", bound(ValueRange.around("10k", 0.05, family="resistor"), a=a, b=b)
    )
    assert placed.value_bin is R_BIN


def child_capture(circuit: Circuit) -> None:
    """Capture a child holding a value spec, for the hierarchy tests."""
    a, b = circuit.net("a"), circuit.net("b")
    spec = ValueRange.around("10k", 0.05, family="resistor")
    circuit.part("R1", RBin(spec, a=a, b=b))


def test_solve_walks_instances_and_flatten_carries_the_pick(
    symbols: StubSymbols,
) -> None:
    board = Circuit("board", symbols)
    board.instance("T1", child_capture)
    report = solve(board)
    (resolution,) = report.resolutions
    assert resolution.path == "T1/R1"
    flat = board.flatten()
    assert flat.parts["T1/R1"].value == "10k"
    # The solved flat IR passes check with no unresolved-spec error.
    messages = [
        issue.message for issue in check(board) if issue.severity is Severity.ERROR
    ]
    assert not [m for m in messages if "unresolved value spec" in m]


def test_unsolved_spec_fails_check_hierarchically(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    board.instance("T1", child_capture)
    messages = [
        issue.message for issue in check(board) if issue.severity is Severity.ERROR
    ]
    (message,) = [m for m in messages if "unresolved value spec" in m]
    assert message.startswith("T1/R1")


def transform_child(circuit: Circuit) -> None:
    """Capture a child a series-insert transform can cut across."""
    x, gnd = circuit.net("x"), circuit.net("gnd")
    circuit.part("R1", RBin("470", a=x, b=gnd))
    circuit.part("R2", RBin("470", a=x, b=gnd))


def test_transform_placed_parts_carry_the_bin(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    board.instance("T1", transform_child)
    apply_transforms(
        board,
        [
            PerInstance(
                ("T1",),
                (
                    InsertSeries(
                        label="X1",
                        net="x",
                        pins=("R1.1",),
                        part=TransformPart(
                            "FI1/RS",
                            RBin(
                                ValueRange.around("10k", 0.05, family="resistor"),
                                a="@a",
                                b="@b",
                            ),
                        ),
                    ),
                ),
            )
        ],
    )
    placed = board.instances["T1"].circuit.parts["FI1/RS"]
    assert placed.value_bin is R_BIN
    report = solve(board)
    assert placed.value == "10k"
    (resolution,) = report.resolutions
    assert resolution.path == "T1/FI1/RS"


def divider_circuit(symbols: StubSymbols, spec: DividerSpec | None = None) -> Circuit:
    """Build a VDD → R1 → out → R2 → GND divider from the bin."""
    c = Circuit("test", symbols)
    vcc, out, gnd = c.net("vcc"), c.net("out"), c.net("gnd")
    spec = spec or DividerSpec(
        ratio=ValueRange.around(0.5, 0.05),
        r_out=ValueRange.around("5k", 0.2, family="resistor"),
        vcc=3.3,
        i_max=330e-6,
    )
    c.part("R1", RBin(spec.top(), a=vcc, b=out))
    c.part("R2", RBin(spec.bottom(), a=out, b=gnd))
    return c


def test_divider_resolves_both_parts_and_reports(symbols: StubSymbols) -> None:
    c = divider_circuit(symbols)
    report = solve(c)
    assert report.issues == []
    assert c.parts["R1"].value == "10k"
    assert c.parts["R2"].value == "10k"
    (resolution,) = report.resolutions
    assert isinstance(resolution, DividerResolution)
    assert resolution.path == "R1"
    assert resolution.r1 == pytest.approx(10_000.0)
    assert resolution.r2 == pytest.approx(10_000.0)
    assert resolution.ratio == pytest.approx(0.5)
    assert resolution.ratio_error == pytest.approx(0.0)
    assert resolution.r_out == pytest.approx(5_000.0)
    assert resolution.current == pytest.approx(165e-6)
    assert "10k/10k" in str(report)
    assert "R∥R 5k" in str(report)
    assert "I 165 µA" in str(report)


def test_divider_hits_a_nonhalf_ratio_and_reports_all_figures(
    symbols: StubSymbols,
) -> None:
    # Vout = VDD/3, source impedance 10k, current ≤ 1 mA: the pair is
    # 30k/15k, drawing 73.3 µA at 3.3 V.
    spec = DividerSpec(
        ratio=ValueRange.around(1 / 3, 0.01),
        r_out=ValueRange.around("10k", 0.1, family="resistor"),
        vcc=3.3,
        i_max=1e-3,
    )
    c = divider_circuit(symbols, spec)
    report = solve(c)
    assert report.issues == []
    assert c.parts["R1"].value == "30k"
    assert c.parts["R2"].value == "15k"
    (resolution,) = report.resolutions
    assert isinstance(resolution, DividerResolution)
    assert resolution.ratio == pytest.approx(1 / 3)
    assert resolution.r_out == pytest.approx(10_000.0)
    assert resolution.current == pytest.approx(3.3 / 45_000.0)


def test_divider_unsolved_fails_check(symbols: StubSymbols) -> None:
    c = divider_circuit(symbols)
    messages = [issue.message for issue in check(c) if issue.severity is Severity.ERROR]
    assert any("unresolved value spec" in m for m in messages)


def test_divider_missing_half_is_an_error(symbols: StubSymbols) -> None:
    c = Circuit("test", symbols)
    vcc, out = c.net("vcc"), c.net("out")
    spec = DividerSpec(
        ratio=ValueRange.around(0.5, 0.05),
        r_out=ValueRange.around("5k", 0.2, family="resistor"),
        vcc=3.3,
        i_max=330e-6,
    )
    c.part("R1", RBin(spec.top(), a=vcc, b=out))
    report = solve(c)
    (issue,) = report.issues
    assert issue.severity is Severity.ERROR
    assert "missing its bottom half" in issue.message


def test_divider_duplicate_role_is_an_error(symbols: StubSymbols) -> None:
    c = Circuit("test", symbols)
    vcc, out, gnd = c.net("vcc"), c.net("out"), c.net("gnd")
    spec = DividerSpec(
        ratio=ValueRange.around(0.5, 0.05),
        r_out=ValueRange.around("5k", 0.2, family="resistor"),
        vcc=3.3,
        i_max=330e-6,
    )
    c.part("R1", RBin(spec.top(), a=vcc, b=out))
    c.part("R2", RBin(spec.top(), a=out, b=gnd))
    report = solve(c)
    assert any("duplicate divider top" in i.message for i in report.issues)
    assert any("missing its bottom half" in i.message for i in report.issues)


def test_divider_halves_without_bin_are_an_error(symbols: StubSymbols) -> None:
    c = Circuit("test", symbols)
    vcc, out, gnd = c.net("vcc"), c.net("out"), c.net("gnd")
    spec = DividerSpec(
        ratio=ValueRange.around(0.5, 0.05),
        r_out=ValueRange.around("5k", 0.2, family="resistor"),
        vcc=3.3,
        i_max=330e-6,
    )
    top = c.part("R1", symbol="Stub:R", value=spec.top(), footprint="StubFP:R_0603")
    bottom = c.part(
        "R2", symbol="Stub:R", value=spec.bottom(), footprint="StubFP:R_0603"
    )
    c.connect(vcc, top[1])
    c.connect(out, top[2], bottom[1])
    c.connect(gnd, bottom[2])
    report = solve(c)
    (issue,) = report.issues
    assert issue.severity is Severity.ERROR
    assert "one shared value bin" in issue.message


def test_divider_unresolvable_is_an_error(symbols: StubSymbols) -> None:
    spec = DividerSpec(
        ratio=ValueRange.around(0.5, 0.01),
        r_out=ValueRange.around("1M", 0.01, family="resistor"),
        vcc=3.3,
        i_max=1e-3,
    )
    c = divider_circuit(symbols, spec)
    report = solve(c)
    (issue,) = report.issues
    assert issue.severity is Severity.ERROR
    assert "no pair in the resistor bin" in issue.message


def divider_child(circuit: Circuit) -> None:
    """Capture a child holding a divider, for the hierarchy test."""
    vcc, out, gnd = circuit.net("vcc"), circuit.net("out"), circuit.net("gnd")
    spec = DividerSpec(
        ratio=ValueRange.around(0.5, 0.05),
        r_out=ValueRange.around("5k", 0.2, family="resistor"),
        vcc=3.3,
        i_max=330e-6,
    )
    circuit.part("R1", RBin(spec.top(), a=vcc, b=out))
    circuit.part("R2", RBin(spec.bottom(), a=out, b=gnd))


def test_divider_walks_instances_and_flatten_carries_the_pair(
    symbols: StubSymbols,
) -> None:
    board = Circuit("board", symbols)
    board.instance("T1", divider_child)
    report = solve(board)
    (resolution,) = report.resolutions
    assert isinstance(resolution, DividerResolution)
    assert resolution.path == "T1/R1"
    flat = board.flatten()
    assert flat.parts["T1/R1"].value == "10k"
    assert flat.parts["T1/R2"].value == "10k"


HOISTED_DIVIDER = DividerSpec(
    ratio=ValueRange.around(0.5, 0.05),
    r_out=ValueRange.around("5k", 0.2, family="resistor"),
    vcc=3.3,
    i_max=330e-6,
)


def hoisted_divider_child(circuit: Circuit) -> None:
    """Capture a child sharing one module-level spec across instances."""
    vcc, out, gnd = circuit.net("vcc"), circuit.net("out"), circuit.net("gnd")
    circuit.part("R1", RBin(HOISTED_DIVIDER.top(), a=vcc, b=out))
    circuit.part("R2", RBin(HOISTED_DIVIDER.bottom(), a=out, b=gnd))


def test_hoisted_spec_resolves_each_instance_separately(
    symbols: StubSymbols,
) -> None:
    # Grouping is per capture, so a spec hoisted to a module/class constant
    # resolves one divider per instance instead of colliding on the second.
    board = Circuit("board", symbols)
    board.instance("T1", hoisted_divider_child)
    board.instance("T2", hoisted_divider_child)
    report = solve(board)
    assert report.issues == []
    assert [resolution.path for resolution in report.resolutions] == ["T1/R1", "T2/R1"]
    flat = board.flatten()
    for ref in ("T1/R1", "T1/R2", "T2/R1", "T2/R2"):
        assert flat.parts[ref].value == "10k"


def test_divider_rejects_a_non_resistor_bin(symbols: StubSymbols) -> None:
    # A capacitor grid and a capacitor-scale spec satisfy the arithmetic
    # (a pair resolves), so only the bin-kind guard rejects the divider.
    spec = DividerSpec(
        ratio=ValueRange.around(0.5, 0.05),
        r_out=ValueRange.around(1e-9, 0.5, family="resistor"),
        vcc=3.3,
        i_max=1e9,
    )
    c = Circuit("test", symbols)
    vcc, out, gnd = c.net("vcc"), c.net("out"), c.net("gnd")
    c.part("C1", CBin(spec.top(), a=vcc, b=out))
    c.part("C2", CBin(spec.bottom(), a=out, b=gnd))
    report = solve(c)
    (issue,) = report.issues
    assert issue.severity is Severity.ERROR
    assert "resistor bin" in issue.message


def test_divider_halves_need_the_same_spec_object(symbols: StubSymbols) -> None:
    # Grouping is by identity: an equal-but-distinct spec per half must not
    # pair, or a same-capture divider could silently capture another's half.
    def new_spec() -> DividerSpec:
        return DividerSpec(
            ratio=ValueRange.around(0.5, 0.05),
            r_out=ValueRange.around("5k", 0.2, family="resistor"),
            vcc=3.3,
            i_max=330e-6,
        )

    top_spec, bottom_spec = new_spec(), new_spec()
    assert top_spec == bottom_spec
    c = Circuit("test", symbols)
    vcc, out, gnd = c.net("vcc"), c.net("out"), c.net("gnd")
    c.part("R1", RBin(top_spec.top(), a=vcc, b=out))
    c.part("R2", RBin(bottom_spec.bottom(), a=out, b=gnd))
    report = solve(c)
    assert report.resolutions == []
    messages = [issue.message for issue in report.issues]
    assert any("missing its bottom half" in message for message in messages)
    assert any("missing its top half" in message for message in messages)


def test_divider_picks_seed_single_spec_consolidation(
    symbols: StubSymbols,
) -> None:
    # The divider resolves first, so its 10k joins in_use and breaks the
    # single spec's exact 9k1/10k tie toward 10k.
    c = divider_circuit(symbols)
    a, b = c.net("a"), c.net("b")
    c.part("R3", RBin(ValueRange.around(9_550.0, 0.05), a=a, b=b))
    report = solve(c)
    assert report.issues == []
    assert c.parts["R3"].value == "10k"


def test_unsolved_divider_fails_netlist_emit(symbols: StubSymbols) -> None:
    c = divider_circuit(symbols)
    with pytest.raises(DefinitionError, match="run solve"):
        emit_netlist(c)


RAIL_3V3 = ValueRange.around(3.3, 0.03)


def from_rail(context: SolveContext) -> ValueRange:
    """Generate 1 kΩ per rail volt (3.3 V → 3k3) for the rail tests."""
    declared = context.rail_voltage("rail")
    if declared is None:
        raise DefinitionError("rail 'rail' has no declared voltage")
    assert declared.nominal is not None
    return ValueRange.around(declared.nominal / 1e-3, 0.05, family="resistor")


def rail_circuit(symbols: StubSymbols, *, voltage: bool = True) -> Circuit:
    """Build a one-resistor circuit whose part is a generator."""
    c = Circuit("test", symbols)
    rail = c.net("rail")
    out = c.net("out")
    kind = PowerDomainKind.ALWAYS
    if voltage:
        c.power_domain(rail, kind=kind, voltage=RAIL_3V3)
    else:
        c.power_domain(rail, kind=kind)
    c.part("R1", RBin(Generator(from_rail), a=rail, b=out))
    return c


def test_generator_sizes_from_the_declared_rail_voltage(
    symbols: StubSymbols,
) -> None:
    c = rail_circuit(symbols)
    report = solve(c)
    assert report.issues == []
    assert c.parts["R1"].value == "3k3"
    (evaluation,) = report.evaluations
    assert isinstance(evaluation, GeneratorEvaluation)
    assert evaluation.path == "R1"
    assert isinstance(evaluation.produced, ValueRange)
    (resolution,) = report.resolutions
    assert isinstance(resolution, Resolution)
    assert resolution.chosen == pytest.approx(3_300.0)
    lines = str(report).splitlines()
    assert lines[0] == "R1: <generator from_rail> → 3k3 ±5%"
    assert lines[1] == "R1: 3k3 ±5% → 3k3 (achieved +0.0%)"


def test_generator_without_a_rail_voltage_is_an_error(symbols: StubSymbols) -> None:
    c = rail_circuit(symbols, voltage=False)
    report = solve(c)
    (issue,) = report.issues
    assert issue.severity is Severity.ERROR
    assert "has no declared voltage" in issue.message
    assert report.evaluations == []
    assert isinstance(c.parts["R1"].value, Generator)


def test_generator_naming_an_unknown_net_is_an_error(symbols: StubSymbols) -> None:
    # The context's lookup is the guard: a typo is a path-named solve
    # issue, not a KeyError escaping the pass.
    def wrong_net(context: SolveContext) -> ValueRange:
        assert context.rail_voltage("nope") is not None
        return ValueRange.around("1k", 0.05, family="resistor")

    c = rail_circuit(symbols)
    c.parts["R1"].value = Generator(wrong_net)
    report = solve(c)
    (issue,) = report.issues
    assert "net 'nope' is not in capture" in issue.message
    assert issue.message.startswith("R1: ")


def test_generator_may_return_a_literal(symbols: StubSymbols) -> None:
    def fixed(_context: SolveContext) -> str:
        return "470"

    c = rail_circuit(symbols)
    c.parts["R1"].value = Generator(fixed)
    report = solve(c)
    assert report.issues == []
    assert c.parts["R1"].value == "470"
    (evaluation,) = report.evaluations
    assert evaluation.produced == "470"
    assert report.resolutions == []


def test_generator_returning_a_non_value_is_an_error(symbols: StubSymbols) -> None:
    def broken(_context: SolveContext) -> object:
        return object()

    c = rail_circuit(symbols)
    c.parts["R1"].value = Generator(broken)  # ty: ignore[invalid-argument-type]
    report = solve(c)
    (issue,) = report.issues
    assert "returns a value literal or a ValueRange" in issue.message
    assert isinstance(c.parts["R1"].value, Generator)


def local_rail_child(circuit: Circuit) -> None:
    """Capture a child whose rail declares a local 3.3 V fallback."""
    rail = circuit.port("rail")
    out = circuit.net("out")
    circuit.power_domain(rail, kind=PowerDomainKind.ALWAYS, voltage=RAIL_3V3)
    circuit.part("R1", RBin(Generator(from_rail), a=rail, b=out))


def test_generator_follows_the_outermost_bound_rail(symbols: StubSymbols) -> None:
    # The child's local declaration is the standalone fallback; the rail
    # its parent binds (5 V) is the actual supply.
    board = Circuit("board", symbols)
    rail = board.net("rail")
    board.power_domain(
        rail,
        kind=PowerDomainKind.ALWAYS,
        voltage=ValueRange.around(5.0, 0.01),
    )
    board.instance("T1", local_rail_child, rail=rail)
    report = solve(board)
    assert report.issues == []
    assert board.instances["T1"].circuit.parts["R1"].value == "5k1"
    (resolution,) = report.resolutions
    assert isinstance(resolution, Resolution)
    assert resolution.path == "T1/R1"
    assert resolution.chosen == pytest.approx(5_100.0)


def test_generator_falls_back_to_the_local_rail(symbols: StubSymbols) -> None:
    # An undeclared parent rail is no data, so the block's own
    # declaration sizes the part — the standalone case.
    board = Circuit("board", symbols)
    rail = board.net("rail")
    board.instance("T1", local_rail_child, rail=rail)
    report = solve(board)
    assert report.issues == []
    assert board.instances["T1"].circuit.parts["R1"].value == "3k3"


def test_generator_output_consolidates_like_an_authored_spec(
    symbols: StubSymbols,
) -> None:
    # Generators evaluate before literals are collected, so a generated
    # 4.9k ±5% tie breaks toward the authored 5k1 already in use.
    def tie(_context: SolveContext) -> ValueRange:
        return ValueRange.around(TIE_TARGET, 0.05, family="resistor")

    c = rail_circuit(symbols)
    c.parts["R1"].value = Generator(tie)
    a, b = c.net("a"), c.net("b")
    c.part("R2", RBin("5k1", a=a, b=b))
    report = solve(c)
    assert report.issues == []
    assert c.parts["R1"].value == "5k1"


def test_unsolved_generator_fails_check_and_emit(symbols: StubSymbols) -> None:
    c = rail_circuit(symbols)
    messages = [issue.message for issue in check(c) if issue.severity is Severity.ERROR]
    assert any("unresolved value spec" in message for message in messages)
    with pytest.raises(DefinitionError, match="run solve"):
        emit_netlist(c)


def test_generator_walks_the_full_binding_chain(symbols: StubSymbols) -> None:
    # board 5 V → tile rail → LED block rail: the outer supply wins even
    # through an intermediate capture that declares nothing.
    def block(circuit: Circuit) -> None:
        rail = circuit.port("rail")
        out = circuit.net("out")
        circuit.part("R1", RBin(Generator(from_rail), a=rail, b=out))

    def tile(circuit: Circuit) -> None:
        rail = circuit.port("rail")
        circuit.instance("LED", block, rail=rail)

    board = Circuit("board", symbols)
    rail = board.net("rail")
    board.power_domain(
        rail,
        kind=PowerDomainKind.ALWAYS,
        voltage=ValueRange.around(5.0, 0.01),
    )
    board.instance("T1", tile, rail=rail)
    report = solve(board)
    assert report.issues == []
    assert (
        board.instances["T1"].circuit.instances["LED"].circuit.parts["R1"].value
        == "5k1"
    )


def _generator_block(circuit: Circuit) -> None:
    """Capture a leaf block whose resistor generator names its rail port."""
    rail = circuit.port("rail")
    out = circuit.net("out")
    circuit.part("R1", RBin(Generator(from_rail), a=rail, b=out))


def _generator_tile(circuit: Circuit) -> None:
    """Capture a tile binding the leaf rail port to a differently named port."""
    mine = circuit.port("mine")
    circuit.instance("LED", _generator_block, rail=mine)


def test_generator_survives_the_transform_tile_flatten(symbols: StubSymbols) -> None:
    # apply_transforms flattens each tile's subcircuits in place; the
    # generator's local 'rail' must still resolve through the tile's
    # 'mine' port to the board supply.
    board = Circuit("board", symbols)
    rail = board.net("rail")
    board.power_domain(
        rail,
        kind=PowerDomainKind.ALWAYS,
        voltage=ValueRange.around(5.0, 0.01),
    )
    board.instance("T1", _generator_tile, mine=rail)
    board.instances["T1"].flatten_hierarchy()
    report = solve(board)
    assert report.issues == []
    assert board.instances["T1"].circuit.parts["LED/R1"].value == "5k1"


def test_generator_survives_a_full_flatten(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    rail = board.net("rail")
    board.power_domain(
        rail,
        kind=PowerDomainKind.ALWAYS,
        voltage=ValueRange.around(5.0, 0.01),
    )
    board.instance("T1", _generator_tile, mine=rail)
    flat = board.flatten()
    report = solve(flat)
    assert report.issues == []
    assert flat.parts["T1/LED/R1"].value == "5k1"
