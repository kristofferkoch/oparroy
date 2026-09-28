"""Shared fixtures: stub symbol/footprint tables and KiCad-lib access."""

from __future__ import annotations

import pytest

from oparroy.dsl import (
    Circuit,
    KiCadLibraries,
    LibraryError,
    PinType,
    Symbol,
    SymbolPin,
    SymbolUnit,
    UnknownSymbolError,
)


def make_symbol(
    name: str,
    pins: dict[str, PinType],
    filters: tuple[str, ...] = (),
    lib: str = "Stub",
    pin_names: dict[str, str] | None = None,
) -> Symbol:
    names = pin_names or {}
    return Symbol(
        lib=lib,
        name=name,
        pins=tuple(
            SymbolPin(number=num, name=names.get(num, ""), type=ptype)
            for num, ptype in pins.items()
        ),
        footprint_filters=filters,
    )


def make_quad_diode() -> Symbol:
    """Build the QD stub: a BAT54ADW-like quad diode (DESIGN.md §7).

    Four diode units with the anode pins shared between unit pairs —
    the multi-unit model: no common pins, one physical pin appearing
    in several units.
    """
    pin_names = {"1": "K", "2": "K", "3": "A", "4": "K", "5": "K", "6": "A"}
    unit_pins = {1: ("1", "6"), 2: ("2", "6"), 3: ("3", "4"), 4: ("3", "5")}

    def symbol_pin(num: str) -> SymbolPin:
        return SymbolPin(number=num, name=pin_names[num], type=PinType.PASSIVE)

    return Symbol(
        lib="Stub",
        name="QD",
        pins=tuple(symbol_pin(num) for num in pin_names),
        footprint_filters=("SOT?363*",),
        units=tuple(
            SymbolUnit(number=unit, pins=tuple(symbol_pin(num) for num in nums))
            for unit, nums in sorted(unit_pins.items())
        ),
    )


class StubSymbols:
    """SymbolTable stub: passives, diodes, a quad-diode package, power parts.

    Models KiCad's real conventions: a power source has a power_out
    pin; a power-library symbol (``power:+3V3``-class) has a power_in
    pin and marks the rail driven (see check.py's power rules).
    ``QD`` mirrors the BAT54ADW multi-unit model: four diode units,
    the anode pins shared between unit pairs (DESIGN.md §7).
    """

    def __init__(self) -> None:
        passive = {"1": PinType.PASSIVE, "2": PinType.PASSIVE}
        self._symbols = {
            f"{s.lib}:{s.name}": s
            for s in [
                make_symbol("R", passive, ("R_*",)),
                make_symbol("C", passive, ("C_*",)),
                make_symbol(
                    "D",
                    passive,
                    ("D_*",),
                    pin_names={"1": "K", "2": "A"},
                ),
                make_symbol(
                    "DSER",
                    {"1": PinType.PASSIVE, "2": PinType.PASSIVE, "3": PinType.PASSIVE},
                    ("SOT?23*",),
                    pin_names={"1": "A", "2": "K", "3": "COM"},
                ),
                make_quad_diode(),
                make_symbol(
                    "CONN6",
                    {str(pin): PinType.PASSIVE for pin in range(1, 7)},
                    ("CONN_*",),
                ),
                make_symbol("REG", {"1": PinType.POWER_OUT}, ("REG_*",)),
                make_symbol(
                    "+3V3",
                    {"1": PinType.POWER_IN},
                    lib="power",
                ),
                make_symbol(
                    "LOAD",
                    {"1": PinType.POWER_IN, "2": PinType.POWER_IN},
                    ("LOAD_*",),
                ),
            ]
        }

    def lookup(self, ref: str) -> Symbol:
        """Resolve from the stub table, like a real library would."""
        try:
            return self._symbols[ref]
        except KeyError:
            msg = f"stub symbol table has no {ref!r}"
            raise UnknownSymbolError(msg) from None


class StubFootprints:
    """FootprintTable stub: a fixed set of known footprints."""

    def __init__(self, known: set[str]) -> None:
        self._known = known

    def exists(self, footprint: str) -> bool:
        """Return True for the fixed known set."""
        return footprint in self._known


@pytest.fixture
def symbols() -> StubSymbols:
    return StubSymbols()


@pytest.fixture
def footprints() -> StubFootprints:
    known = {
        "StubFP:R_0603",
        "StubFP:C_0603",
        "StubFP:PWR_SIP",
        "StubFP:LOAD_SIP",
        "StubFP:CONN_1x06",
        "StubFP:SOT-363",
        "StubFP:SOD-323",
    }
    return StubFootprints(known)


@pytest.fixture
def circuit(symbols: StubSymbols) -> Circuit:
    """Two parallel resistors; every pin connected, no single-pin nets."""
    c = Circuit("test", symbols)
    r1 = c.part("R1", symbol="Stub:R", value="1k", footprint="StubFP:R_0603")
    r2 = c.part("R2", symbol="Stub:R", value="1k", footprint="StubFP:R_0603")
    a = c.net("a")
    mid = c.net("mid")
    c.connect(a, r1[1], r2[2])
    c.connect(mid, r1[2], r2[1])
    return c


@pytest.fixture
def kicad_libs() -> KiCadLibraries:
    try:
        return KiCadLibraries.from_env()
    except LibraryError:
        pytest.skip("KiCad libraries not provisioned (outside the nix dev shell)")
