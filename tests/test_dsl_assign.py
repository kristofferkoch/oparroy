"""Footprint-assignment stage tests (DESIGN.md §7: an explicit stage)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from oparroy.dsl import (
    Circuit,
    DefinitionError,
    assign_footprints,
    footprint_map,
    overrides_from_json,
    overrides_to_json,
)

if TYPE_CHECKING:
    from conftest import StubSymbols


def build(symbols: StubSymbols) -> Circuit:
    c = Circuit("assign", symbols)
    r1 = c.part("R1", symbol="Stub:R", value="1k", footprint="StubFP:R_0603")
    r2 = c.part("R2", symbol="Stub:R", value="1k")
    a = c.net("a")
    c.connect(a, r1[1], r2[1])
    return c


def test_footprint_map_dumps_assignment(symbols: StubSymbols) -> None:
    assert footprint_map(build(symbols)) == {
        "R1": "StubFP:R_0603",
        "R2": None,
    }


def test_assign_applies_overrides(symbols: StubSymbols) -> None:
    flat = assign_footprints(build(symbols), {"R2": "StubFP:R_0402"})
    assert flat.parts["R2"].footprint == "StubFP:R_0402"
    assert flat.parts["R1"].footprint == "StubFP:R_0603"


def test_unknown_override_key_raises(symbols: StubSymbols) -> None:
    with pytest.raises(DefinitionError, match="unknown parts"):
        assign_footprints(build(symbols), {"R9": "StubFP:R_0402"})


def test_malformed_footprint_raises(symbols: StubSymbols) -> None:
    with pytest.raises(DefinitionError, match="Lib:Name"):
        assign_footprints(build(symbols), {"R2": "not-a-ref"})


def test_overrides_json_round_trip() -> None:
    table = {"WD1/Rs": "Resistor_SMD:R_0402_1005Metric", "C1": "StubFP:C_0603"}
    assert overrides_from_json(overrides_to_json(table)) == table


def test_overrides_to_json_is_byte_identical() -> None:
    table = {"B": "StubFP:X", "A": "StubFP:Y"}
    assert overrides_to_json(table) == overrides_to_json(dict(reversed(table.items())))
    assert overrides_to_json(table).endswith("\n")


def test_overrides_from_json_rejects_non_map() -> None:
    with pytest.raises(DefinitionError, match="JSON object"):
        overrides_from_json('["R1"]')
    with pytest.raises(DefinitionError, match="JSON object"):
        overrides_from_json('{"R1": 42}')
