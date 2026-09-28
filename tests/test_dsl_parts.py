"""Typed-part placement tests (DESIGN.md §7: typed jellybean parts)."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pytest

from oparroy.dsl import (
    Bat54s,
    Capacitor,
    Circuit,
    DefinitionError,
    Led,
    Resistor,
    TvsDiode,
    TypedPart,
)

if TYPE_CHECKING:
    from conftest import StubSymbols
    from oparroy.dsl import Net


class StubR(Resistor):
    """Resistor redirected at the stub symbol table, with a bin default."""

    symbol = "Stub:R"
    default_footprint = "StubFP:R_0603"


class StubC(Capacitor):
    """Capacitor redirected at the stub symbol table."""

    symbol = "Stub:C"


class StubDSer(Bat54s):
    """Series diode pair redirected at the stub symbol table."""

    symbol = "Stub:DSER"
    default_footprint = "StubFP:SOT23"


def test_typed_part_places_and_wires(symbols: StubSymbols) -> None:
    c = Circuit("t", symbols)
    a = c.net("a")
    mid = c.net("mid")
    r1 = c.part("R1", StubR("1k", a=a, b=mid))
    assert r1.symbol.ref == "Stub:R"
    assert r1.value == "1k"
    assert r1.footprint == "StubFP:R_0603"
    assert r1["1"].net is a
    assert r1["2"].net is mid


def test_footprint_kwarg_overrides_class_default(symbols: StubSymbols) -> None:
    c = Circuit("t", symbols)
    c.net("a")
    c.net("b")
    r1 = c.part("R1", StubR("1k", a="a", b="b", footprint="StubFP:R_0402"))
    assert r1.footprint == "StubFP:R_0402"


def test_nets_accept_names_or_objects(symbols: StubSymbols) -> None:
    c = Circuit("t", symbols)
    a = c.net("a")
    c.net("b")
    r1 = c.part("R1", StubR("1k", a=a, b="b"))
    assert r1["1"].net is a
    assert r1["2"].net is c.nets["b"]


def test_series_pair_keyword_pins_land_on_right_numbers(
    symbols: StubSymbols,
) -> None:
    c = Circuit("t", symbols)
    for name in ("gnd", "sel", "x"):
        c.net(name)
    d1 = c.part("D1", StubDSer(anode="gnd", cathode="sel", com="x"))
    assert d1.value == "BAT54S"
    assert d1.footprint == "StubFP:SOT23"
    assert d1["1"].net is c.nets["gnd"]
    assert d1["2"].net is c.nets["sel"]
    assert d1["3"].net is c.nets["x"]


def test_missing_pin_kwarg_fails_at_construction() -> None:
    with pytest.raises(TypeError, match="b"):
        StubR("1k", a="a")  # ty: ignore[missing-argument]


def test_unknown_pin_kwarg_fails_at_construction(symbols: StubSymbols) -> None:
    c = Circuit("t", symbols)
    c.net("a")
    with pytest.raises(TypeError, match="c"):
        StubR("1k", a="a", b="a", c="a")  # ty: ignore[unknown-argument]


def test_unknown_net_raises_and_places_nothing(symbols: StubSymbols) -> None:
    c = Circuit("t", symbols)
    c.net("a")
    with pytest.raises(DefinitionError, match="no net named"):
        c.part("R1", StubR("1k", a="a", b="nope"))
    assert "R1" not in c.parts


def test_duplicate_ref_raises_and_places_nothing(symbols: StubSymbols) -> None:
    c = Circuit("t", symbols)
    for name in ("a", "b"):
        c.net(name)
    c.part("R1", StubR("1k", a="a", b="b"))
    with pytest.raises(DefinitionError, match="duplicate part reference"):
        c.part("R1", StubR("2k", a="a", b="b"))
    assert c.parts["R1"].value == "1k"


def test_spec_and_symbol_conflict_raises(symbols: StubSymbols) -> None:
    c = Circuit("t", symbols)
    c.net("a")
    with pytest.raises(DefinitionError, match="not both"):
        c.part("R1", StubR("1k", a="a", b="a"), symbol="Stub:R")


def test_string_positional_gets_a_hint(symbols: StubSymbols) -> None:
    c = Circuit("t", symbols)
    with pytest.raises(DefinitionError, match="symbol="):
        c.part("R1", "Stub:R")  # ty: ignore[invalid-argument-type]


def test_part_without_spec_or_symbol_raises(symbols: StubSymbols) -> None:
    c = Circuit("t", symbols)
    with pytest.raises(DefinitionError, match="typed part or symbol="):
        c.part("R1")


def test_default_value_and_overrides(symbols: StubSymbols) -> None:
    c = Circuit("t", symbols)
    for name in ("g", "s", "x"):
        c.net(name)
    d1 = c.part("D1", StubDSer(anode="g", cathode="s", com="x"))
    d2 = c.part("D2", StubDSer(anode="g", cathode="s", com="x", value="BAT54SW"))
    assert d1.value == "BAT54S"
    assert d2.value == "BAT54SW"
    c2 = Circuit("t2", symbols)
    c2.net("a")
    c2.net("b")
    cap = c2.part("C1", StubC("10n", a="a", b="b"))
    assert cap.footprint is None


def test_bad_pin_map_raises_and_places_nothing(symbols: StubSymbols) -> None:
    class BadPin(StubR):
        pin_map: ClassVar[dict[str, str]] = {"a": "1", "b": "9"}

    c = Circuit("t", symbols)
    a = c.net("a")
    c.net("b")
    with pytest.raises(DefinitionError, match="does not have"):
        c.part("R1", BadPin("1k", a=a, b="b"))
    assert "R1" not in c.parts
    assert a.pins == ()


def test_pin_map_duplicate_numbers_raise(symbols: StubSymbols) -> None:
    class DupPin(StubR):
        pin_map: ClassVar[dict[str, str]] = {"a": "1", "b": "1"}

    c = Circuit("t", symbols)
    c.net("a")
    c.net("b")
    with pytest.raises(DefinitionError, match="same pin number"):
        c.part("R1", DupPin("1k", a="a", b="b"))
    assert "R1" not in c.parts


def test_value_kwarg_with_spec_raises(symbols: StubSymbols) -> None:
    c = Circuit("t", symbols)
    c.net("a")
    with pytest.raises(DefinitionError, match="typed part class"):
        c.part("R1", StubR("1k", a="a", b="a"), value="2k")


def test_non_typed_spec_raises(symbols: StubSymbols) -> None:
    c = Circuit("t", symbols)
    with pytest.raises(DefinitionError, match="expected a typed part"):
        c.part("R1", 42)  # ty: ignore[invalid-argument-type]


class StubLed(Led):
    """LED redirected at the stub table's 3-pin series-pair symbol."""

    symbol = "Stub:DSER"


class StubTvs(TvsDiode):
    """TVS redirected at the stub table's 3-pin series-pair symbol."""

    symbol = "Stub:DSER"
    default_value = "PESD3V3L1BA"


def test_led_keyword_pins_land_on_right_numbers(symbols: StubSymbols) -> None:
    c = Circuit("t", symbols)
    c.net("drive")
    c.net("gnd")
    led = c.part("LED1", StubLed(anode="drive", cathode="gnd", value="GREEN"))
    # Device:LED convention: pin 1 = K, pin 2 = A.
    assert led.value == "GREEN"
    assert led["1"].net is c.nets["gnd"]
    assert led["2"].net is c.nets["drive"]


def test_tvs_default_value_and_symmetric_pins(symbols: StubSymbols) -> None:
    c = Circuit("t", symbols)
    c.net("line")
    c.net("gnd")
    tvs = c.part("D1", StubTvs(a="line", b="gnd"))
    assert tvs.value == "PESD3V3L1BA"
    assert tvs["1"].net is c.nets["line"]
    assert tvs["2"].net is c.nets["gnd"]


def test_optional_pins_may_be_omitted(symbols: StubSymbols) -> None:
    class OptionalPins(StubR):
        required_pins: ClassVar[frozenset[str] | None] = frozenset({"a"})

        def __init__(
            self,
            value: str,
            *,
            a: Net | str,
            b: Net | str | None = None,
            footprint: str | None = None,
        ) -> None:
            nets = {"a": a} | ({"b": b} if b is not None else {})
            TypedPart.__init__(self, value, footprint, nets)

    c = Circuit("t", symbols)
    c.net("a")
    c.net("b")
    wired = c.part("R1", OptionalPins("1k", a="a", b="b"))
    assert wired["2"].net is c.nets["b"]
    # An omitted optional pin simply stays unconnected — the checker's
    # unconnected-pin warning reports it by name.
    unwired = c.part("R2", OptionalPins("1k", a="a"))
    assert unwired["2"].net is None


def test_omitted_required_pin_still_raises() -> None:
    class BadOptional(StubR):
        required_pins: ClassVar[frozenset[str] | None] = frozenset({"a", "b"})

        def __init__(self, value: str, *, a: Net | str) -> None:
            TypedPart.__init__(self, value, None, {"a": a})

    with pytest.raises(DefinitionError, match="missing pins"):
        BadOptional("1k", a="a")
