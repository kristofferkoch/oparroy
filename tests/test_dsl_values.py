"""Value-spec tests: SI parse/format, E-series tables, bins, ranges."""

from __future__ import annotations

import pytest

from oparroy.dsl import DefinitionError, ValueBin, ValueRange
from oparroy.dsl.values import E12, E24, E96, format_value, parse_value

#: Every ``R0603``/``C0603`` literal in ``design/`` (DNP markers
#: excluded) plus the series endpoints — the house style
#: ``format_value`` must reproduce byte-for-byte.
RESISTOR_LITERALS = (
    "0R",
    "R082",
    "27",
    "47",
    "220",
    "470",
    "1k",
    "4k",
    "4k7",
    "5k1",
    "10k",
    "47k",
    "1M",
)
CAPACITOR_LITERALS = (
    "15p",
    "50p",
    "1n",
    "4n7",
    "10n",
    "22n",
    "100n",
    "1u",
    "4u7",
    "10u",
    "22u",
)

R_0603_BIN = ValueBin(kind="resistor", series=24, tolerance=0.01, lo=1.0, hi=1e6)
C_0603_BIN = ValueBin(kind="capacitor", series=12, tolerance=0.10, lo=1e-12, hi=1e-6)

_DECADE = 10.0
_E24_DECADES_IN_BINS = 6

PARSED = (
    ("0R", "resistor", 0.0),
    ("R082", "resistor", 0.082),
    ("470", "resistor", 470.0),
    ("4k7", "resistor", 4700.0),
    ("10k", "resistor", 10_000.0),
    ("1M", "resistor", 1_000_000.0),
    ("15p", "capacitor", 15e-12),
    ("4n7", "capacitor", 4.7e-9),
    ("100n", "capacitor", 1e-7),
    ("10u", "capacitor", 1e-5),
)


@pytest.mark.parametrize(("literal", "family", "expected"), PARSED)
def test_parse_known_values(literal: str, family: str, expected: float) -> None:
    assert parse_value(literal, family=family) == pytest.approx(expected)


@pytest.mark.parametrize("literal", RESISTOR_LITERALS)
def test_resistor_round_trip(literal: str) -> None:
    assert format_value(parse_value(literal, family="resistor"), family="resistor") == (
        literal
    )


@pytest.mark.parametrize("literal", CAPACITOR_LITERALS)
def test_capacitor_round_trip(literal: str) -> None:
    assert (
        format_value(parse_value(literal, family="capacitor"), family="capacitor")
        == literal
    )


def test_bare_number_parses_as_base_units() -> None:
    assert parse_value("470", family="resistor") == pytest.approx(470.0)
    assert parse_value("470", family="capacitor") == pytest.approx(470.0)


def test_zero_formats_house_style() -> None:
    assert format_value(0.0, family="resistor") == "0R"


@pytest.mark.parametrize("text", ["", "abc", "10kk", "1.2.3", "k", "10 k", "-4k7"])
def test_malformed_literals_raise(text: str) -> None:
    with pytest.raises(DefinitionError, match="malformed"):
        parse_value(text, family="resistor")


def test_other_family_letter_raises() -> None:
    with pytest.raises(DefinitionError, match="malformed"):
        parse_value("10k", family="capacitor")
    with pytest.raises(DefinitionError, match="malformed"):
        parse_value("100n", family="resistor")


def test_unknown_family_raises() -> None:
    with pytest.raises(DefinitionError, match="unknown value family"):
        parse_value("10k", family="inductor")
    with pytest.raises(DefinitionError, match="unknown value family"):
        format_value(10_000.0, family="inductor")


def test_negative_value_rejects_format() -> None:
    with pytest.raises(DefinitionError, match="negative"):
        format_value(-1.0, family="resistor")


def test_e_series_tables() -> None:
    assert len(E12) == len(E24) // 2 == len(E96) // 8
    for table in (E12, E24, E96):
        assert tuple(sorted(table)) == table
        assert all(1.0 <= mantissa < _DECADE for mantissa in table)
    assert set(E12) < set(E24)


def test_value_range_validates_bounds() -> None:
    with pytest.raises(DefinitionError, match="lo <= nominal <= hi"):
        ValueRange(2.0, 1.0)
    with pytest.raises(DefinitionError, match="lo <= nominal <= hi"):
        ValueRange(1.0, 2.0, nominal=3.0)
    with pytest.raises(DefinitionError, match="lo <= nominal <= hi"):
        ValueRange(-1.0, 2.0)


def test_around_validates_tolerance() -> None:
    with pytest.raises(DefinitionError, match="tolerance"):
        ValueRange.around(10_000.0, 1.0)
    with pytest.raises(DefinitionError, match="tolerance"):
        ValueRange.around(10_000.0, -0.05)


def test_around_string_target_needs_family() -> None:
    with pytest.raises(DefinitionError, match="family"):
        ValueRange.around("10k", 0.05)


def test_around_builds_symmetric_range() -> None:
    spec = ValueRange.around("10k", 0.05, family="resistor")
    assert spec.lo == pytest.approx(9500.0)
    assert spec.hi == pytest.approx(10_500.0)
    assert spec.nominal == pytest.approx(10_000.0)
    assert str(spec) == "10k ±5%"


def test_bare_range_defaults_nominal_to_log_midrange() -> None:
    spec = ValueRange(1_000.0, 2_000.0, family="resistor")
    assert spec.nominal == pytest.approx(1414.21, rel=1e-4)
    assert str(spec) == "1k..2k"


def test_bin_validates() -> None:
    with pytest.raises(DefinitionError, match="unknown E-series"):
        ValueBin(kind="resistor", series=3, tolerance=0.01, lo=1.0, hi=10.0)
    with pytest.raises(DefinitionError, match="unknown value family"):
        ValueBin(kind="inductor", series=24, tolerance=0.01, lo=1.0, hi=10.0)
    with pytest.raises(DefinitionError, match="0 < lo <= hi"):
        ValueBin(kind="resistor", series=24, tolerance=0.01, lo=0.0, hi=10.0)
    with pytest.raises(DefinitionError, match="0 < lo <= hi"):
        ValueBin(kind="resistor", series=24, tolerance=0.01, lo=10.0, hi=1.0)


def test_bin_values_stay_in_bounds() -> None:
    values = R_0603_BIN.values()
    assert values[0] == pytest.approx(1.0)
    assert values[-1] == pytest.approx(1e6)
    # Six decades of E24 plus the 1M endpoint.
    assert len(values) == len(E24) * _E24_DECADES_IN_BINS + 1
    cap_values = C_0603_BIN.values()
    assert cap_values[0] == pytest.approx(1e-12)
    assert cap_values[-1] == pytest.approx(1e-6)


def test_resolve_picks_nearest() -> None:
    spec = ValueRange.around("10k", 0.05, family="resistor")
    assert R_0603_BIN.resolve(spec) == pytest.approx(10_000.0)
    off_nominal = ValueRange.around(1030.0, 0.05)
    assert R_0603_BIN.resolve(off_nominal) == pytest.approx(1_000.0)


def test_resolve_none_when_no_value_meets_the_spec() -> None:
    assert R_0603_BIN.resolve(ValueRange.around("10M", 0.05, family="resistor")) is None


def test_resolve_tie_prefers_in_use_then_ascending() -> None:
    # 4900 is the arithmetic mean of the adjacent E24 values 4k7/5k1:
    # an exact relative-error tie.
    spec = ValueRange.around(4900.0, 0.05)
    assert R_0603_BIN.resolve(spec) == pytest.approx(4700.0)
    assert R_0603_BIN.resolve(spec, in_use=frozenset({5100.0})) == pytest.approx(5100.0)
