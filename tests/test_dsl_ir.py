"""IR construction and invariant tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from oparroy.dsl import Circuit, DefinitionError, UnknownSymbolError
from oparroy.dsl.ir import natural_key

if TYPE_CHECKING:
    from conftest import StubSymbols


def test_natural_key_orders_numbers() -> None:
    refs = ["R10", "R2", "R1", "Cs", "Rb"]
    assert sorted(refs, key=natural_key) == ["Cs", "R1", "R2", "R10", "Rb"]


def test_natural_key_breaks_case_ties_by_original() -> None:
    # "R1" and "r1" share the lowercased/split key; the tiebreak keeps
    # ordering reproducible regardless of insertion order.
    assert sorted(["r1", "R1"], key=natural_key) == ["R1", "r1"]
    assert sorted(["R1", "r1"], key=natural_key) == ["R1", "r1"]


def test_duplicate_part_ref_raises(circuit: Circuit) -> None:
    with pytest.raises(DefinitionError, match="duplicate part reference"):
        circuit.part("R1", symbol="Stub:R")


def test_duplicate_net_name_raises(circuit: Circuit) -> None:
    with pytest.raises(DefinitionError, match="duplicate net name"):
        circuit.net("a")


def test_double_connect_raises(circuit: Circuit) -> None:
    r3 = circuit.part("R3", symbol="Stub:R")
    circuit.connect("a", r3[1])
    with pytest.raises(DefinitionError, match="already on net"):
        circuit.connect("mid", r3[2], r3[1])
    # connect is atomic: the failed call attached nothing, and r3.1
    # still sits on net 'a'.
    assert r3[1].net is circuit.nets["a"]
    assert r3[2].net is None
    assert all(pin.part.ref != "R3" for pin in circuit.nets["mid"].pins)


def test_connect_rejects_foreign_pin(symbols: StubSymbols) -> None:
    c1 = Circuit("one", symbols)
    c2 = Circuit("two", symbols)
    r1 = c1.part("R1", symbol="Stub:R")
    c2.net("n")
    with pytest.raises(DefinitionError, match="does not belong"):
        c2.connect("n", r1[1])
    assert c2.nets["n"].pins == ()


def test_connect_rejects_foreign_net(symbols: StubSymbols) -> None:
    c1 = Circuit("one", symbols)
    c2 = Circuit("two", symbols)
    r2 = c2.part("R2", symbol="Stub:R")
    n1 = c1.net("n")
    with pytest.raises(DefinitionError, match="does not belong"):
        c2.connect(n1, r2[1])
    assert r2[1].net is None


def test_connect_keeps_pin_and_net_consistent(circuit: Circuit) -> None:
    r3 = circuit.part("R3", symbol="Stub:R")
    net = circuit.nets["a"]
    circuit.connect(net, r3[1])
    assert r3[1].net is net
    assert r3[1] in net.pins


def test_pin_net_is_read_only(circuit: Circuit) -> None:
    r3 = circuit.part("R3", symbol="Stub:R")
    with pytest.raises(AttributeError):
        r3[1].net = circuit.nets["a"]  # ty: ignore[invalid-assignment]


def test_connect_same_pin_twice_is_atomic(circuit: Circuit) -> None:
    r3 = circuit.part("R3", symbol="Stub:R")
    circuit.net("dup")
    with pytest.raises(DefinitionError, match="listed twice"):
        circuit.connect("dup", r3[1], r3[1])
    assert r3[1].net is None
    assert circuit.nets["dup"].pins == ()


def test_natural_key_tolerates_unicode_digits() -> None:
    # '²'.isdigit() is True but int('²') raises — the isascii() guard
    # keeps it a string chunk instead of crashing.
    assert natural_key("R²") == (("r²",), "R²")


def test_unknown_pin_raises(circuit: Circuit) -> None:
    with pytest.raises(DefinitionError, match="has no pin 7"):
        circuit.parts["R1"].pin(7)


def test_unknown_symbol_raises(symbols: StubSymbols) -> None:
    c = Circuit("x", symbols)
    with pytest.raises(UnknownSymbolError):
        c.part("Q1", symbol="Stub:NOPE")


def test_connect_by_net_name(circuit: Circuit) -> None:
    r3 = circuit.part("R3", symbol="Stub:R")
    circuit.connect("mid", r3[1])
    assert circuit.nets["mid"].pins[-1].part.ref == "R3"


def test_connect_unknown_net_name_raises(circuit: Circuit) -> None:
    r3 = circuit.part("R3", symbol="Stub:R")
    with pytest.raises(DefinitionError, match="no net named"):
        circuit.connect("nope", r3[1])


def test_pin_lookup_accepts_int_and_str(circuit: Circuit) -> None:
    part = circuit.parts["R1"]
    assert part[1] is part["1"]


def test_dump_lists_parts_pins_and_nets(circuit: Circuit) -> None:
    dump = circuit.dump()
    assert "circuit test: 2 parts, 2 nets" in dump
    assert "R1 Stub:R '1k' [StubFP:R_0603]" in dump
    assert "1 (passive) -> a" in dump
    assert "mid: R1.2 R2.1" in dump


def test_dump_covers_sparse_branches(circuit: Circuit) -> None:
    # No value, no footprint, unconnected pin: '?', no bracket, '—'.
    circuit.part("R3", symbol="Stub:R")
    dump = circuit.dump()
    assert "R3 Stub:R '?'" in dump
    assert "R3 Stub:R '?' [" not in dump
    assert "2 (passive) -> —" in dump


def test_net_pins_sorted_by_ref(symbols: StubSymbols) -> None:
    c = Circuit("order", symbols)
    parts = [
        c.part(f"R{i}", symbol="Stub:R", value="1", footprint="StubFP:R_0603")
        for i in (10, 2, 1)
    ]
    n = c.net("n")
    for p in parts:
        c.connect(n, p[1])
    assert [p.part.ref for p in n.pins] == ["R1", "R2", "R10"]
