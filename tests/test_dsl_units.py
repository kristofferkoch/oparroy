"""Multi-unit package tests: Symbol unit structure, unit subsets (T7bc).

DESIGN.md §7: ``Symbol`` preserves KiCad's unit structure, a placed
part instantiates a unit subset, and a physical pin shared by placed
units sits on one net.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pytest

from oparroy.dsl import (
    Circuit,
    DefinitionError,
    KiCadLibraries,
    LibraryError,
    MultiUnitPart,
    PinType,
)

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import StubSymbols


def _library_with_symbols(tmp_path: Path, body: str) -> KiCadLibraries:
    """Build a KiCadLibraries over one hand-written Stub.kicad_sym."""
    (tmp_path / "Stub.kicad_sym").write_text(
        f'(kicad_symbol_lib (version 20231120) (generator "test")\n{body})\n',
        encoding="utf-8",
    )
    return KiCadLibraries(tmp_path, tmp_path)


_QUAD_BODY = (
    '(symbol "QUAD"'
    ' (symbol "QUAD_0_1")'
    ' (symbol "QUAD_1_1"'
    '  (pin passive line (at 0 0 0) (name "K") (number "1"))'
    '  (pin passive line (at 0 0 0) (name "A") (number "6")))'
    ' (symbol "QUAD_2_1"'
    '  (pin passive line (at 0 0 0) (name "K") (number "2"))'
    '  (pin passive line (at 0 0 0) (name "A") (number "6")))'
    ' (symbol "QUAD_3_1"'
    '  (pin passive line (at 0 0 0) (name "A") (number "3"))'
    '  (pin passive line (at 0 0 0) (name "K") (number "4")))'
    ' (symbol "QUAD_4_1"'
    '  (pin passive line (at 0 0 0) (name "A") (number "3"))'
    '  (pin passive line (at 0 0 0) (name "K") (number "5"))))'
)


class StubQd(MultiUnitPart):
    """Quad diode over the stub symbol table, all four units."""

    symbol = "Stub:QD"
    unit_pins: ClassVar[dict[int, dict[str, str]]] = {
        1: {"cathode": "1", "anode": "6"},
        2: {"cathode": "2", "anode": "6"},
        3: {"anode": "3", "cathode": "4"},
        4: {"anode": "3", "cathode": "5"},
    }
    default_value = "QD"
    default_footprint = "StubFP:SOT-363"


class StubQdPair(MultiUnitPart):
    """Only the second diode pair of the package: units 3 and 4."""

    symbol = "Stub:QD"
    unit_pins: ClassVar[dict[int, dict[str, str]]] = {
        3: {"anode": "3", "cathode": "4"},
        4: {"anode": "3", "cathode": "5"},
    }
    default_footprint = "StubFP:SOT-363"


def test_lookup_preserves_unit_structure(tmp_path: Path) -> None:
    libs = _library_with_symbols(tmp_path, _QUAD_BODY)
    symbol = libs.lookup("Stub:QUAD")
    assert [unit.number for unit in symbol.units] == [1, 2, 3, 4]
    assert symbol.common_pins == ()
    # A physical pin shared by two units appears in both, once in the
    # all-units view.
    unit1 = {pin.number: pin.name for pin in symbol.units[0].pins}
    unit2 = {pin.number: pin.name for pin in symbol.units[1].pins}
    assert unit1 == {"1": "K", "6": "A"}
    assert unit2 == {"2": "K", "6": "A"}
    assert {pin.number for pin in symbol.pins} == {"1", "2", "3", "4", "5", "6"}
    assert symbol.pin_conflicts == ()


def test_lookup_power_unit(tmp_path: Path) -> None:
    libs = _library_with_symbols(
        tmp_path,
        '(symbol "SW" (symbol "SW_1_1"'
        ' (pin passive line (at 0 0 0) (name "A") (number "1")))'
        ' (symbol "SW_5_1"'
        ' (pin power_in line (at 0 0 0) (name "VSS") (number "7"))'
        ' (pin power_in line (at 0 0 0) (name "VDD") (number "14"))))',
    )
    symbol = libs.lookup("Stub:SW")
    power = {pin.number: pin.type for pin in symbol.units[-1].pins}
    assert power == {"7": PinType.POWER_IN, "14": PinType.POWER_IN}


def test_lookup_single_unit_symbol_has_only_common_pins(tmp_path: Path) -> None:
    libs = _library_with_symbols(
        tmp_path,
        '(symbol "R" (symbol "R_0_1"'
        ' (pin passive line (at 0 0 0) (name "~") (number "1"))'
        ' (pin passive line (at 0 0 0) (name "~") (number "2"))))',
    )
    symbol = libs.lookup("Stub:R")
    assert symbol.units == ()
    assert {pin.number for pin in symbol.common_pins} == {"1", "2"}
    assert symbol.pins == symbol.common_pins


def test_lookup_bad_subsymbol_name_raises(tmp_path: Path) -> None:
    libs = _library_with_symbols(
        tmp_path,
        '(symbol "A" (symbol "A_unit_one"'
        ' (pin passive line (at 0 0 0) (name "X") (number "1"))))',
    )
    with pytest.raises(LibraryError, match="<name>_<unit>_<style>"):
        libs.lookup("Stub:A")


def test_real_bat54adw_unit_structure(kicad_libs: KiCadLibraries) -> None:
    symbol = kicad_libs.lookup("Diode:BAT54ADW")
    assert [unit.number for unit in symbol.units] == [1, 2, 3, 4]
    by_unit = {
        unit.number: {pin.number: pin.name for pin in unit.pins}
        for unit in symbol.units
    }
    assert by_unit[1] == {"1": "K", "6": "A"}
    assert by_unit[2] == {"2": "K", "6": "A"}
    assert by_unit[3] == {"3": "A", "4": "K"}
    assert by_unit[4] == {"3": "A", "5": "K"}
    # The shared anodes are not conflicts: identical redefinitions.
    assert symbol.pin_conflicts == ()
    package_pins = 6
    assert len(symbol.pins) == package_pins


def test_real_cd4066_has_switch_and_power_units(kicad_libs: KiCadLibraries) -> None:
    symbol = kicad_libs.lookup("Analog_Switch:CD4066BE")
    assert [unit.number for unit in symbol.units] == [1, 2, 3, 4, 5]
    power = {pin.number: pin.type for pin in symbol.units[-1].pins}
    assert power == {"7": PinType.POWER_IN, "14": PinType.POWER_IN}


def test_real_single_diode_is_one_unit(kicad_libs: KiCadLibraries) -> None:
    # Single-unit symbols keep their pins in unit 1; unit 0 holds the
    # shared graphics. Either way placement resolves the same pins.
    symbol = kicad_libs.lookup("Device:D")
    assert [unit.number for unit in symbol.units] == [1]
    assert {pin.number: pin.name for pin in symbol.pins} == {"1": "K", "2": "A"}
    assert {pin.number for pin in symbol.pins_for_units((1,))} == {"1", "2"}


def test_pins_for_units_subsets(symbols: StubSymbols) -> None:
    symbol = symbols.lookup("Stub:QD")
    assert {p.number for p in symbol.pins_for_units(None)} == {
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
    }
    assert {p.number for p in symbol.pins_for_units((1,))} == {"1", "6"}
    # The shared anode pin 6 appears once when both units place.
    assert [p.number for p in symbol.pins_for_units((1, 2))] == ["1", "6", "2"]


def test_pins_for_units_unknown_unit_raises(symbols: StubSymbols) -> None:
    symbol = symbols.lookup("Stub:QD")
    with pytest.raises(DefinitionError, match="has no units"):
        symbol.pins_for_units((5,))
    single = symbols.lookup("Stub:R")
    with pytest.raises(DefinitionError, match="has no units"):
        single.pins_for_units((1,))


def test_multi_unit_part_places_declared_subset(symbols: StubSymbols) -> None:
    c = Circuit("t", symbols)
    u1 = c.part("U1", StubQd())
    assert u1.symbol.ref == "Stub:QD"
    assert u1.value == "QD"
    assert u1.footprint == "StubFP:SOT-363"
    assert u1.units == (1, 2, 3, 4)
    assert {pin.number for pin in u1.pins} == {"1", "2", "3", "4", "5", "6"}
    u2 = c.part("U2", StubQdPair())
    assert u2.units == (3, 4)
    assert {pin.number for pin in u2.pins} == {"3", "4", "5"}
    with pytest.raises(DefinitionError, match="has no pin 6"):
        u2.pin("6")


def test_unit_handles_expose_typed_pins(symbols: StubSymbols) -> None:
    c = Circuit("t", symbols)
    u1 = c.part("U1", StubQd())
    handle = u1.unit(1)
    assert handle.part is u1
    assert handle.unit == 1
    assert handle.anode is u1.pin("6")
    assert handle["cathode"] is u1.pin("1")
    assert handle.pin_map == {"cathode": "1", "anode": "6"}
    assert set(handle) == {"anode", "cathode"}
    with pytest.raises(KeyError, match="no pin 'gate'"):
        handle["gate"]
    with pytest.raises(AttributeError, match="no pin 'gate'"):
        handle.gate  # noqa: B018


def test_unit_handle_requires_placed_typed_unit(symbols: StubSymbols) -> None:
    c = Circuit("t", symbols)
    u2 = c.part("U2", StubQdPair())
    with pytest.raises(DefinitionError, match="no placed unit 1"):
        u2.unit(1)
    r1 = c.part("R1", symbol="Stub:R")
    with pytest.raises(DefinitionError, match="not placed from a multi-unit"):
        r1.unit(1)


def test_shared_pin_wires_once_per_unit_onto_one_net(symbols: StubSymbols) -> None:
    c = Circuit("t", symbols)
    a = c.net("a")
    k1 = c.net("k1")
    k2 = c.net("k2")
    u1 = c.part("U1", StubQd())
    # The shared anode is wired once per unit — same net, so the
    # second attach is a no-op, not a double-connect.
    c.connect(a, u1.unit(1).anode)
    c.connect(a, u1.unit(2).anode)
    c.connect(k1, u1.unit(1).cathode)
    c.connect(k2, u1.unit(2).cathode)
    assert len([pin for pin in a.pins if pin.part is u1]) == 1
    other = c.net("other")
    with pytest.raises(DefinitionError, match="already on net"):
        c.connect(other, u1.pin("6"))


def test_multi_unit_validation_rejects_bad_unit_pins(symbols: StubSymbols) -> None:
    class BadUnit(MultiUnitPart):
        symbol = "Stub:QD"
        unit_pins: ClassVar[dict[int, dict[str, str]]] = {9: {"anode": "6"}}

    class BadPin(MultiUnitPart):
        symbol = "Stub:QD"
        unit_pins: ClassVar[dict[int, dict[str, str]]] = {
            1: {"anode": "6", "cathode": "9"},
        }

    class DupPin(MultiUnitPart):
        symbol = "Stub:QD"
        unit_pins: ClassVar[dict[int, dict[str, str]]] = {
            1: {"anode": "6", "cathode": "6"},
        }

    c = Circuit("t", symbols)
    with pytest.raises(DefinitionError, match="does not have"):
        c.part("U1", BadUnit())
    with pytest.raises(DefinitionError, match="unit 1 does not have"):
        c.part("U1", BadPin())
    with pytest.raises(DefinitionError, match="same pin number"):
        c.part("U1", DupPin())
    assert c.parts == {}


def test_flatten_preserves_unit_selection(symbols: StubSymbols) -> None:
    c = Circuit("t", symbols)
    c.net("a")
    u2 = c.part("U2", StubQdPair())
    c.connect("a", u2.unit(3).anode)
    flat = c.flatten()
    placed = flat.parts["U2"]
    assert placed.units == (3, 4)
    assert placed.unit(4).anode is placed.pin("3")
    assert flat.nets["a"].pins[0] is placed.pin("3")
