"""CI board typed-part tests (need the nix-provisioned libraries).

Cross-checks the typed pin maps in ``design/ci_parts.py`` against the
real KiCad symbols (the netlist emitter binds on pin numbers, so a
wrong map is a wrong board) and against the parts-DB records, which
carry the same symbol/footprint pair for sourcing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from design import ci_parts, parts_db
from oparroy.dsl import TypedPart

if TYPE_CHECKING:
    from oparroy.dsl import KiCadLibraries

#: typed class -> (parts-DB record, symbol pin number -> expected KiCad pin name)
PINOUTS: dict[type[TypedPart], tuple[str, dict[str, str]]] = {
    ci_parts.Sn74hc595: (
        "74hc595-nexperia",
        {
            "1": "QB",
            "2": "QC",
            "3": "QD",
            "4": "QE",
            "5": "QF",
            "6": "QG",
            "7": "QH",
            "8": "GND",
            "9": "QH'",
            "10": "~{SRCLR}",
            "11": "SRCLK",
            "12": "RCLK",
            "13": "~{OE}",
            "14": "SER",
            "15": "QA",
            "16": "VCC",
        },
    ),
    ci_parts.Sn74hc165: (
        "74hc165-nexperia",
        {
            "1": "~{PL}",
            "2": "CP",
            "3": "D4",
            "4": "D5",
            "5": "D6",
            "6": "D7",
            "7": "~{Q7}",
            "8": "GND",
            "9": "Q7",
            "10": "DS",
            "11": "D0",
            "12": "D1",
            "13": "D2",
            "14": "D3",
            "15": "~{CE}",
            "16": "VCC",
        },
    ),
    ci_parts.Ao3401a: ("ao3401a", {"1": "G", "2": "S", "3": "D"}),
    ci_parts.N2n7002: ("2n7002", {"1": "G", "2": "S", "3": "D"}),
    ci_parts.Rk09k: ("pot-10k-rk09k", {"1": "1", "2": "2", "3": "3"}),
    ci_parts.Ts1187a: ("btn-tact-ts1187a", {"1": "1", "2": "2"}),
    ci_parts.Pklcs1212e: ("buzzer-pklcs1212e", {"1": "+", "2": "-"}),
    ci_parts.Ina241a5: (
        "csa-ina241a5",
        {
            "1": "-",
            "2": "GND",
            "3": "REF2",
            "4": "GND",
            "5": "",
            "6": "V+",
            "7": "REF1",
            "8": "+",
        },
    ),
    ci_parts.Adcs7476: (
        "adc-adcs7476",
        {
            "1": "V_{DD}",
            "2": "GND",
            "3": "VIN",
            "4": "SCLK",
            "5": "SDO",
            "6": "~{CS}",
        },
    ),
}


def test_pin_maps_match_the_kicad_symbols(kicad_libs: KiCadLibraries) -> None:
    for cls, (_record_name, expected) in PINOUTS.items():
        symbol = kicad_libs.lookup(cls.symbol)
        by_number = {pin.number: pin.name for pin in symbol.pins}
        assert set(cls.pin_map.values()) <= set(by_number), cls.__name__
        for keyword, number in cls.pin_map.items():
            numbers = (number,) if isinstance(number, str) else number
            for n in numbers:
                assert by_number[n] == expected[n], (
                    f"{cls.__name__}.{keyword}: KiCad pin {n} is "
                    f"{by_number[n]!r}, expected {expected[n]!r}"
                )


def test_typed_parts_agree_with_the_parts_db(kicad_libs: KiCadLibraries) -> None:
    for cls, (record_name, _expected) in PINOUTS.items():
        record = parts_db.PARTS.find(record_name)
        assert (cls.symbol, cls.default_value, cls.default_footprint) == (
            record.symbol,
            record.value,
            record.footprint,
        ), cls.__name__
        assert kicad_libs.exists(record.footprint), cls.__name__
