"""Power-domain declarations, crossing detection, and dispositions."""

from __future__ import annotations

from typing import ClassVar

import pytest

from conftest import make_symbol
from oparroy.dsl import (
    POWER_DOMAIN_CROSSING,
    AlwaysPowered,
    BackFeed,
    Circuit,
    DefinitionError,
    DiesWith,
    InsertSeries,
    Issue,
    Net,
    PartRecord,
    PartsDb,
    PerTile,
    PinType,
    PowerDomain,
    PowerDomainKind,
    Severity,
    Subcircuit,
    Symbol,
    TransformPart,
    TypedPart,
    UnknownSymbolError,
    ValueRange,
    apply_transforms,
    check,
    raise_on_errors,
)
from oparroy.dsl.ir import hierarchical_crossings


class DomainSymbols:
    """Symbol table for the power-domain tests.

    ``DRV``/``RCV``/``BOTH`` are powered-IC stubs: pin 1 VCC and pin 3
    GND (both POWER_IN), pin 2 the signal pin. ``SW`` is the SPDT
    analog-switch stub for the transform tests; the resistor and the
    power symbols model KiCad's conventions (Device-lib passives,
    power-lib net markers).
    """

    def __init__(self) -> None:
        passive = {"1": PinType.PASSIVE, "2": PinType.PASSIVE}
        self._symbols = {
            f"{s.lib}:{s.name}": s
            for s in [
                make_symbol(
                    "DRV",
                    {
                        "1": PinType.POWER_IN,
                        "2": PinType.OUTPUT,
                        "3": PinType.POWER_IN,
                    },
                ),
                make_symbol(
                    "RCV",
                    {
                        "1": PinType.POWER_IN,
                        "2": PinType.INPUT,
                        "3": PinType.POWER_IN,
                    },
                ),
                make_symbol(
                    "BOTH",
                    {
                        "1": PinType.POWER_IN,
                        "2": PinType.BIDIRECTIONAL,
                        "3": PinType.POWER_IN,
                    },
                ),
                make_symbol(
                    "SW",
                    {
                        "1": PinType.PASSIVE,
                        "2": PinType.PASSIVE,
                        "3": PinType.PASSIVE,
                        "4": PinType.INPUT,
                    },
                ),
                make_symbol("R", passive, lib="Device"),
                make_symbol("+3V3", {"1": PinType.POWER_IN}, lib="power"),
                make_symbol("GND", {"1": PinType.POWER_IN}, lib="power"),
                make_symbol("REG", {"1": PinType.POWER_OUT}),
            ]
        }

    def lookup(self, ref: str) -> Symbol:
        """Resolve from the stub table, like a real library would."""
        try:
            return self._symbols[ref]
        except KeyError:
            msg = f"stub symbol table has no {ref!r}"
            raise UnknownSymbolError(msg) from None


@pytest.fixture
def symbols() -> DomainSymbols:
    return DomainSymbols()


def messages(issues: list[Issue], severity: Severity) -> list[str]:
    return [i.message for i in issues if i.severity is severity]


def _rails(board: Circuit, *names: str) -> dict[str, Net]:
    """Declare 3V3N/5V/UNREG-alikes: named rails, always-on, power-symbol driven."""
    rails = {}
    for name in names:
        net = board.net(name)
        board.power_domain(net, kind=PowerDomainKind.ALWAYS)
        marker = board.part(f"P{name}", symbol="power:+3V3", value=name)
        board.connect(net, marker["1"])
        rails[name] = net
    return rails


def _ground(board: Circuit) -> Net:
    gnd = board.net("GND")
    board.power_domain(gnd, kind=PowerDomainKind.GROUND)
    marker = board.part("PGND", symbol="power:GND", value="GND")
    board.connect(gnd, marker["1"])
    return gnd


def _switched(board: Circuit, name: str = "3V3N") -> Net:
    net = board.net(name)
    board.power_domain(net, kind=PowerDomainKind.SWITCHED)
    marker = board.part(f"P{name}", symbol="power:+3V3", value=name)
    board.connect(net, marker["1"])
    return net


def _driver(board: Circuit, ref: str, vcc: Net, gnd: Net, sig: Net) -> None:
    part = board.part(ref, symbol="Stub:DRV", value="drv", footprint="StubFP:SOIC")
    board.connect(vcc, part["1"])
    board.connect(sig, part["2"])
    board.connect(gnd, part["3"])


def _receiver(board: Circuit, ref: str, vcc: Net, gnd: Net, sig: Net) -> None:
    part = board.part(ref, symbol="Stub:RCV", value="rcv", footprint="StubFP:SOIC")
    board.connect(vcc, part["1"])
    board.connect(sig, part["2"])
    board.connect(gnd, part["3"])


def build_crossing(symbols: DomainSymbols) -> Circuit:
    """U1 on the always rail drives ``sig``; U2 on the switched rail reads it."""
    board = Circuit("board", symbols)
    rails = _rails(board, "3V3")
    v3v3n = _switched(board)
    gnd = _ground(board)
    sig = board.net("sig")
    _driver(board, "U1", rails["3V3"], gnd, sig)
    _receiver(board, "U2", v3v3n, gnd, sig)
    return board


def test_undeclared_crossing_errors(symbols: DomainSymbols) -> None:
    board = build_crossing(symbols)
    issues = check(board)
    (error,) = [i for i in issues if i.severity is Severity.ERROR]
    assert error.message == (
        "net 'sig' crosses power domains with no declared disposition: "
        "'3V3' (always), '3V3N' (switched)"
    )
    assert error.check == POWER_DOMAIN_CROSSING
    assert error.path == "sig"
    with pytest.raises(Exception, match="circuit check failed"):
        raise_on_errors(issues)


def test_declared_crossing_passes(symbols: DomainSymbols) -> None:
    board = build_crossing(symbols)
    board.crossing("sig", BackFeed(budget_ma=5.7, citation="docs §3"))
    assert check(board) == []


def test_gnd_pulldown_is_not_a_crossing(symbols: DomainSymbols) -> None:
    board = Circuit("board", symbols)
    rails = _rails(board, "3V3")
    gnd = _ground(board)
    pd = board.net("pd")
    _driver(board, "U1", rails["3V3"], gnd, pd)
    board.part("R1", symbol="Device:R", value="10k", footprint="StubFP:R_0603")
    board.connect(pd, board.parts["R1"]["1"])
    board.connect(gnd, board.parts["R1"]["2"])
    assert check(board) == []


def test_rail_nets_are_not_audited(symbols: DomainSymbols) -> None:
    board = build_crossing(symbols)
    board.crossing("sig", DiesWith())  # fails DiesWith, but that's not the point
    issues = check(board)
    assert {i.path for i in issues} == {"sig"}


def test_dies_with_passes_when_foreign_pin_is_input(symbols: DomainSymbols) -> None:
    # The switched-domain driver dies with its net; the always-domain
    # side only reads.
    board = Circuit("board", symbols)
    rails = _rails(board, "3V3")
    v3v3n = _switched(board)
    gnd = _ground(board)
    sig = board.net("sig")
    _driver(board, "U1", v3v3n, gnd, sig)
    _receiver(board, "U2", rails["3V3"], gnd, sig)
    board.crossing("sig", DiesWith())
    assert check(board) == []


def test_dies_with_fails_on_foreign_output(symbols: DomainSymbols) -> None:
    board = build_crossing(symbols)
    board.crossing("sig", DiesWith())
    issues = check(board)
    assert messages(issues, Severity.ERROR) == [
        (
            "net 'sig' is declared dies-with-domain but U1.2 (output) is "
            "powered from an always rail and may drive the dead net"
        )
    ]
    (error,) = [i for i in issues if i.severity is Severity.ERROR]
    assert error.check == POWER_DOMAIN_CROSSING
    assert error.path == "sig"


def test_dies_with_fails_on_foreign_bidirectional(symbols: DomainSymbols) -> None:
    board = Circuit("board", symbols)
    rails = _rails(board, "3V3")
    v3v3n = _switched(board)
    gnd = _ground(board)
    sig = board.net("sig")
    _driver(board, "U1", v3v3n, gnd, sig)
    u2 = board.part("U2", symbol="Stub:BOTH", value="both", footprint="StubFP:SOIC")
    board.connect(rails["3V3"], u2["1"])
    board.connect(sig, u2["2"])
    board.connect(gnd, u2["3"])
    board.crossing("sig", DiesWith())
    assert messages(check(board), Severity.ERROR) == [
        (
            "net 'sig' is declared dies-with-domain but U2.2 (bidirectional) "
            "is powered from an always rail and may drive the dead net"
        )
    ]


def test_dies_with_reach_through_series_resistor(symbols: DomainSymbols) -> None:
    # The foreign driver reaches sig through a series resistor — still
    # a violation (the divider-fed dead pin shape).
    board = Circuit("board", symbols)
    rails = _rails(board, "3V3")
    v3v3n = _switched(board)
    gnd = _ground(board)
    sig = board.net("sig")
    tap = board.net("tap")
    _receiver(board, "U1", v3v3n, gnd, sig)
    _driver(board, "U2", rails["3V3"], gnd, tap)
    r1 = board.part("R1", symbol="Device:R", value="470", footprint="StubFP:R_0603")
    board.connect(tap, r1["1"])
    board.connect(sig, r1["2"])
    # Both sides of the resistive link are crossings and carry the
    # declaration; the foreign driver violates both.
    board.crossing("sig", DiesWith())
    board.crossing("tap", DiesWith())
    assert messages(check(board), Severity.ERROR) == [
        (
            "net 'sig' is declared dies-with-domain but U2.2 (output) is "
            "powered from an always rail and may drive the dead net"
        ),
        (
            "net 'tap' is declared dies-with-domain but U2.2 (output) is "
            "powered from an always rail and may drive the dead net"
        ),
    ]


def test_always_powered_passes(symbols: DomainSymbols) -> None:
    # U3 has no partial-power-down spec but is powered from the always
    # rail, so the AlwaysPowered declaration holds.
    board = Circuit("board", symbols)
    rails = _rails(board, "3V3")
    v3v3n = _switched(board)
    gnd = _ground(board)
    sig = board.net("sig")
    _receiver(board, "U1", v3v3n, gnd, sig)
    _receiver(board, "U2", rails["3V3"], gnd, sig)
    u3 = board.part("U3", symbol="Stub:RCV", value="sw", footprint="StubFP:SOIC")
    board.connect(rails["3V3"], u3["1"])
    board.connect(sig, u3["2"])
    board.connect(gnd, u3["3"])
    u3.partial_power_down = False
    board.crossing("sig", AlwaysPowered())
    assert check(board) == []


def test_always_powered_fails_on_switched_power(symbols: DomainSymbols) -> None:
    # The 3157 rule: a no-Ioff part on the crossing net must not be
    # powered from the switched rail.
    board = build_crossing(symbols)
    u3 = board.part("U3", symbol="Stub:RCV", value="sw", footprint="StubFP:SOIC")
    board.connect(board.nets["3V3N"], u3["1"])
    board.connect(board.nets["sig"], u3["2"])
    board.connect(board.nets["GND"], u3["3"])
    u3.partial_power_down = False
    board.crossing("sig", AlwaysPowered())
    issues = check(board)
    assert messages(issues, Severity.ERROR) == [
        (
            "net 'sig' is declared always-powered but U3 has no "
            "partial-power-down spec and not all its power pins are on "
            "always rails (U3.1)"
        )
    ]
    (error,) = [i for i in issues if i.severity is Severity.ERROR]
    assert error.check == POWER_DOMAIN_CROSSING
    assert error.path == "sig"


def test_always_powered_tolerates_missing_data(symbols: DomainSymbols) -> None:
    # partial_power_down=None is no data, never a finding.
    board = build_crossing(symbols)
    board.crossing("sig", AlwaysPowered())
    assert check(board) == []


def test_back_feed_requires_budget_and_citation(symbols: DomainSymbols) -> None:
    board = build_crossing(symbols)
    with pytest.raises(DefinitionError, match="budget must be positive"):
        board.crossing("sig", BackFeed(budget_ma=0, citation="docs §3"))
    with pytest.raises(DefinitionError, match="budget must be positive"):
        board.crossing("sig", BackFeed(budget_ma=-1, citation="docs §3"))
    with pytest.raises(DefinitionError, match="needs a citation"):
        board.crossing("sig", BackFeed(budget_ma=5.7, citation=""))


def test_crossing_rejects_duplicates(symbols: DomainSymbols) -> None:
    board = build_crossing(symbols)
    board.crossing("sig", DiesWith())
    with pytest.raises(DefinitionError, match="duplicate DiesWith"):
        board.crossing("sig", DiesWith())
    # A different disposition type on the same net is a second fact.
    board.crossing("sig", AlwaysPowered())


def test_crossing_rejects_unknown_disposition(symbols: DomainSymbols) -> None:
    board = build_crossing(symbols)
    with pytest.raises(DefinitionError, match="unknown crossing disposition"):
        board.crossing("sig", "dies-with")  # ty: ignore[invalid-argument-type]


def test_crossing_requires_a_net_name(symbols: DomainSymbols) -> None:
    board = build_crossing(symbols)
    with pytest.raises(DefinitionError, match="needs a net name"):
        board.crossing("", DiesWith())


def test_power_domain_declaration_is_validated(symbols: DomainSymbols) -> None:
    board = Circuit("board", symbols)
    net = board.net("3V3")
    domain = board.power_domain(net, kind=PowerDomainKind.ALWAYS)
    assert net.power_domain == domain == PowerDomain(PowerDomainKind.ALWAYS)
    with pytest.raises(DefinitionError, match="no net named 'NOPE'"):
        board.power_domain("NOPE", kind=PowerDomainKind.ALWAYS)
    with pytest.raises(DefinitionError, match="already has a declared"):
        board.power_domain(net, kind=PowerDomainKind.SWITCHED)
    with pytest.raises(DefinitionError, match="must be a PowerDomainKind"):
        board.power_domain(board.net("5V"), kind="always")  # ty: ignore[invalid-argument-type]


def test_power_domain_carries_the_rail_voltage(symbols: DomainSymbols) -> None:
    board = Circuit("board", symbols)
    net = board.net("3V3")
    voltage = ValueRange.around(3.3, 0.03)
    domain = board.power_domain(
        net,
        kind=PowerDomainKind.ALWAYS,
        voltage=voltage,
    )
    assert (
        net.power_domain
        == domain
        == PowerDomain(PowerDomainKind.ALWAYS, voltage=voltage)
    )


def test_rail_voltage_must_be_a_dimensionless_value_range(
    symbols: DomainSymbols,
) -> None:
    board = Circuit("board", symbols)
    with pytest.raises(DefinitionError, match="must be a ValueRange"):
        board.power_domain(
            board.net("a"),
            kind=PowerDomainKind.ALWAYS,
            voltage=3.3,  # ty: ignore[invalid-argument-type]
        )
    with pytest.raises(DefinitionError, match="dimensionless"):
        board.power_domain(
            board.net("b"),
            kind=PowerDomainKind.ALWAYS,
            voltage=ValueRange.around("10k", 0.05, family="resistor"),
        )


def test_stale_crossing_declaration_warns(symbols: DomainSymbols) -> None:
    board = Circuit("board", symbols)
    rails = _rails(board, "3V3")
    gnd = _ground(board)
    pd = board.net("pd")
    _driver(board, "U1", rails["3V3"], gnd, pd)
    r1 = board.part("R1", symbol="Device:R", value="10k", footprint="StubFP:R_0603")
    board.connect(gnd, r1["1"])
    board.connect(pd, r1["2"])
    board.crossing("TX_A#a", DiesWith())
    issues = check(board)
    assert messages(issues, Severity.ERROR) == []
    assert messages(issues, Severity.WARNING) == [
        "crossing declaration at 'TX_A#a' matched no crossing net"
    ]


def test_waiver_degrades_the_crossing_error(symbols: DomainSymbols) -> None:
    board = build_crossing(symbols)
    board.waive(
        POWER_DOMAIN_CROSSING, "sig", reason="470 Ω series bound, bench-verified"
    )
    issues = check(board)
    (waived,) = [i for i in issues if i.severity is Severity.WAIVED]
    assert waived.check == POWER_DOMAIN_CROSSING
    assert waived.path == "sig"
    assert "waived: 470 Ω series bound, bench-verified" in waived.message
    assert messages(issues, Severity.ERROR) == []
    raise_on_errors(issues)


def test_undeclared_rail_warns(symbols: DomainSymbols) -> None:
    board = Circuit("board", symbols)
    gnd = _ground(board)
    v5 = board.net("5V")
    marker = board.part("P5V", symbol="power:+3V3", value="5V")
    board.connect(v5, marker["1"])
    _receiver(board, "U1", v5, gnd, v5)  # input pin idle on its own rail
    issues = check(board)
    assert messages(issues, Severity.ERROR) == []
    assert messages(issues, Severity.WARNING) == [
        "rail net '5V' has no declared power domain"
    ]
    (warning,) = [i for i in issues if i.severity is Severity.WARNING]
    assert warning.check == POWER_DOMAIN_CROSSING
    assert warning.path == "5V"


def test_power_out_marks_a_rail_too(symbols: DomainSymbols) -> None:
    board = Circuit("board", symbols)
    gnd = _ground(board)
    reg_out = board.net("VOUT")
    reg = board.part("U1", symbol="Stub:REG", value="reg", footprint="StubFP:SIP")
    board.connect(reg_out, reg["1"])
    load = board.part("R1", symbol="Device:R", value="10k", footprint="StubFP:R_0603")
    board.connect(reg_out, load["1"])
    board.connect(gnd, load["2"])
    assert messages(check(board), Severity.WARNING) == [
        "rail net 'VOUT' has no declared power domain"
    ]


def test_always_always_is_not_a_crossing(symbols: DomainSymbols) -> None:
    board = Circuit("board", symbols)
    rails = _rails(board, "3V3", "5V")
    gnd = _ground(board)
    sig = board.net("sig")
    _driver(board, "U1", rails["3V3"], gnd, sig)
    _receiver(board, "U2", rails["5V"], gnd, sig)
    assert check(board) == []


def test_port_parent_domain_kinds_must_agree(symbols: DomainSymbols) -> None:
    def child(circuit: Circuit) -> None:
        vdd = circuit.port("vdd")
        circuit.power_domain(vdd, kind=PowerDomainKind.ALWAYS)
        gnd = circuit.port("gnd")
        r1 = circuit.part(
            "R1", symbol="Device:R", value="1k", footprint="StubFP:R_0603"
        )
        circuit.connect(vdd, r1["1"])
        circuit.connect(gnd, r1["2"])

    board = Circuit("board", symbols)
    rails = _rails(board, "3V3")
    v3v3n = _switched(board)
    gnd = _ground(board)
    board.instance("T0", child, vdd=v3v3n, gnd=gnd)
    board.instance("T1", child, vdd=rails["3V3"], gnd=gnd)
    issues = check(board)
    assert messages(issues, Severity.ERROR) == [
        (
            "port 'T0/vdd' is declared always but its parent net '3V3N' is "
            "declared switched (domain kinds must agree across a binding)"
        )
    ]
    (error,) = [i for i in issues if i.severity is Severity.ERROR]
    assert error.check == POWER_DOMAIN_CROSSING
    assert error.path == "T0/vdd"


def test_subcircuit_declaration_prefixes_at_check(symbols: DomainSymbols) -> None:
    def child(circuit: Circuit) -> None:
        vs = circuit.port("vs")
        circuit.power_domain(vs, kind=PowerDomainKind.SWITCHED)
        va = circuit.port("va")
        circuit.power_domain(va, kind=PowerDomainKind.ALWAYS)
        gnd = circuit.port("gnd")
        sig = circuit.net("sig")
        _driver(circuit, "U1", vs, gnd, sig)
        _receiver(circuit, "U2", va, gnd, sig)
        circuit.crossing("sig", DiesWith())

    board = Circuit("board", symbols)
    rails = _rails(board, "3V3")
    v3v3n = _switched(board)
    gnd = _ground(board)
    board.instance("T0", child, vs=v3v3n, va=rails["3V3"], gnd=gnd)
    assert check(board) == []


def test_subcircuit_crossing_reports_the_flat_path(symbols: DomainSymbols) -> None:
    def child(circuit: Circuit) -> None:
        vs = circuit.port("vs")
        circuit.power_domain(vs, kind=PowerDomainKind.SWITCHED)
        va = circuit.port("va")
        circuit.power_domain(va, kind=PowerDomainKind.ALWAYS)
        gnd = circuit.port("gnd")
        sig = circuit.net("sig")
        _driver(circuit, "U1", vs, gnd, sig)
        _receiver(circuit, "U2", va, gnd, sig)

    board = Circuit("board", symbols)
    rails = _rails(board, "3V3")
    v3v3n = _switched(board)
    gnd = _ground(board)
    board.instance("T0", child, vs=v3v3n, va=rails["3V3"], gnd=gnd)
    issues = check(board)
    assert messages(issues, Severity.ERROR) == [
        (
            "net 'T0/sig' crosses power domains with no declared disposition: "
            "'3V3' (always), '3V3N' (switched)"
        )
    ]
    (error,) = [i for i in issues if i.severity is Severity.ERROR]
    assert error.path == "T0/sig"


class StubSwitch(TypedPart):
    """SPDT analog-switch stub (``Stub:SW``): ``a`` common, ``b1`` throw, ``s`` select.

    ``b2``/pin 3 stays unplaced — the rail split bridges one throw only.
    """

    symbol = "Stub:SW"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "a": "1",
        "b1": "2",
        "s": "4",
    }
    default_footprint = "StubFP:SOT-363"

    def __init__(
        self,
        *,
        a: Net | str,
        b1: Net | str,
        s: Net | str,
        value: str | None = None,
        footprint: str | None = None,
    ) -> None:
        super().__init__(value, footprint, {"a": a, "b1": b1, "s": s})


class RailTile(Subcircuit):
    """A tile whose internal 3V3 rail powers two receivers; F8 splits U1 off."""

    def __init__(
        self,
        *,
        declare: bool = True,
        voltage: ValueRange | None = None,
    ) -> None:
        self._declare = declare
        self._voltage = voltage

    def capture(self, circuit: Circuit) -> None:
        """Build the tile: two receivers on the internal 3V3 rail."""
        gnd = circuit.port("GND")
        sig = circuit.port("SIG")
        rail = circuit.net("3V3")
        if self._declare:
            circuit.power_domain(
                rail,
                kind=PowerDomainKind.ALWAYS,
                voltage=self._voltage,
            )
        for ref in ("U1", "U2"):
            _receiver(circuit, ref, rail, gnd, sig)


def _f8(*, switched_domain: bool) -> InsertSeries:
    return InsertSeries(
        label="F8",
        net="3V3",
        pins=("U1.1",),
        name="3V3N",
        part=TransformPart("F8/SW", StubSwitch(a="@a", b1="@b", s="GND")),
        switched_domain=switched_domain,
    )


def _rail_board(symbols: DomainSymbols, tile: Subcircuit) -> Circuit:
    board = Circuit("board", symbols)
    gnd = _ground(board)
    sig = board.net("SIG")
    board.instance("T0", tile, GND=gnd, SIG=sig)
    return board


def test_transform_tags_the_switched_domain(symbols: DomainSymbols) -> None:
    board = _rail_board(symbols, RailTile())
    apply_transforms(board, [PerTile(RailTile, (_f8(switched_domain=True),))])
    tile = board.instances["T0"].circuit
    assert tile.nets["3V3N"].power_domain == PowerDomain(
        PowerDomainKind.SWITCHED, parent="3V3"
    )


def test_transform_inherits_the_rail_voltage(symbols: DomainSymbols) -> None:
    voltage = ValueRange.around(3.3, 0.03)
    board = _rail_board(symbols, RailTile(voltage=voltage))
    apply_transforms(board, [PerTile(RailTile, (_f8(switched_domain=True),))])
    tile = board.instances["T0"].circuit
    domain = tile.nets["3V3N"].power_domain
    assert domain is not None
    assert domain.voltage == voltage


def test_transform_requires_an_always_base(symbols: DomainSymbols) -> None:
    board = _rail_board(symbols, RailTile(declare=False))
    with pytest.raises(
        DefinitionError, match="a switched domain must derive from a declared"
    ):
        apply_transforms(board, [PerTile(RailTile, (_f8(switched_domain=True),))])


def test_cut_without_the_flag_tags_nothing(symbols: DomainSymbols) -> None:
    board = _rail_board(symbols, RailTile())
    apply_transforms(board, [PerTile(RailTile, (_f8(switched_domain=False),))])
    tile = board.instances["T0"].circuit
    assert tile.nets["3V3N"].power_domain is None


class CrossedTile(RailTile):
    """A rail tile that also declares a crossing on its SIG port."""

    def capture(self, circuit: Circuit) -> None:
        """Build the rail tile and declare SIG's crossing."""
        super().capture(circuit)
        circuit.crossing("SIG", DiesWith())


def test_flatten_hierarchy_rehomes_crossings(symbols: DomainSymbols) -> None:
    # The transform pass flattens the tile in place; the tile's crossing
    # declaration survives and prefixes like a waiver at board check time.
    board = _rail_board(symbols, CrossedTile())
    apply_transforms(board, [PerTile(CrossedTile, (_f8(switched_domain=True),))])
    assert [c.path for c in hierarchical_crossings(board)] == ["T0/SIG"]


class PortDomainTile(Subcircuit):
    """A tile whose rail PORT carries the domain (the O2 tap's 3V3N shape)."""

    def capture(self, circuit: Circuit) -> None:
        """Build the tile: one receiver on the domain-declared rail port."""
        gnd = circuit.port("GND")
        rail = circuit.port("RAIL")
        circuit.power_domain(rail, kind=PowerDomainKind.SWITCHED)
        _receiver(circuit, "U1", rail, gnd, circuit.port("SIG"))


def test_bound_port_domain_rides_the_merged_net(symbols: DomainSymbols) -> None:
    # The port declares the domain, the parent net doesn't: the merged
    # flat net carries the one-sided declaration (the both-declared case
    # is the kind-agreement check's), and the source capture keeps its
    # undeclared net — flattening is a pass, not a mutation.
    board = Circuit("board", symbols)
    gnd = _ground(board)
    rail = board.net("TAP")
    sig = board.net("SIG")
    board.instance("T0", PortDomainTile(), GND=gnd, RAIL=rail, SIG=sig)
    flat = board.flatten()
    assert flat.nets["TAP"].power_domain == PowerDomain(PowerDomainKind.SWITCHED)
    assert board.nets["TAP"].power_domain is None


class StubReceiver(TypedPart):
    """Typed receiver stub for the parts-DB plumbing test (``Stub:RCV``)."""

    symbol = "Stub:RCV"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "vcc": "1",
        "sig": "2",
        "gnd": "3",
    }

    def __init__(
        self,
        *,
        vcc: Net | str,
        sig: Net | str,
        gnd: Net | str,
        value: str | None = None,
        footprint: str | None = None,
    ) -> None:
        super().__init__(value, footprint, {"vcc": vcc, "sig": sig, "gnd": gnd})


def test_partial_power_down_flows_from_record_to_flat_part(
    symbols: DomainSymbols,
) -> None:
    record = PartRecord(
        name="sw-no-ioff",
        kind="analog-switch",
        symbol="Stub:RCV",
        footprint="StubFP:SOIC",
        partial_power_down=False,
    )
    bound = PartsDb([record]).bind("sw-no-ioff", StubReceiver, class_name="DbRcv")

    def child(circuit: Circuit) -> None:
        gnd = circuit.port("gnd")
        circuit.net("vcc")
        circuit.net("sig")
        circuit.part("U1", bound(vcc="vcc", sig="sig", gnd=gnd))

    board = Circuit("board", symbols)
    board.net("vcc")
    board.net("sig")
    gnd = _ground(board)
    board.instance("T0", child, gnd=gnd)
    flat = board.flatten()
    assert flat.parts["T0/U1"].partial_power_down is False
    # A record without the datum binds None — no data, never a finding.
    plain = PartsDb(
        [
            PartRecord(
                name="sw-unknown",
                kind="analog-switch",
                symbol="Stub:RCV",
                footprint="StubFP:SOIC",
            )
        ]
    ).bind("sw-unknown", StubReceiver)
    assert plain.partial_power_down is None
