"""Parts-DB tests (T7c, DESIGN.md §6: part selection is inventory-driven)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from design import parts_db, watchdog_chargepump
from oparroy.dsl import (
    Bat54s,
    Circuit,
    PartFilter,
    PartRecord,
    PartsDb,
    PartsDbError,
    Resistor,
    Stock,
    Tier,
)
from oparroy.dsl.parts_db import STOCK_MAX_AGE_DAYS

if TYPE_CHECKING:
    from conftest import StubSymbols
    from oparroy.dsl import KiCadLibraries

REPO_ROOT = Path(__file__).parent.parent
TODAY = date(2026, 9, 28)
FRESH = date(2026, 9, 26)
STALE = FRESH - timedelta(days=STOCK_MAX_AGE_DAYS + 1)
BASIC_STOCK = 10_000
TI_STOCK = 51_000

#: The seed records with no stock snapshot (never queried, and for the
#: BAT54S an unverified tier) — everything else is fresh at TODAY.
SEED_UNVERIFIED = {"r-0603", "c-0603", "bat54s"}


def _record(name: str, **overrides: object) -> PartRecord:
    fields: dict[str, object] = {
        "name": name,
        "kind": "resistor",
        "symbol": "Stub:R",
        "footprint": "StubFP:R_0603",
    }
    return PartRecord(**(fields | overrides))  # ty: ignore[invalid-argument-type]


def _names(records: list[PartRecord]) -> list[str]:
    return [record.name for record in records]


@pytest.fixture
def db() -> PartsDb:
    """Build a small table exercising every filter dimension."""
    return PartsDb(
        [
            _record(
                "r-basic",
                tier=Tier.BASIC,
                area_mm2=1.28,
                stock=Stock(BASIC_STOCK, FRESH, "test"),
            ),
            _record(
                "r-tht",
                tier=Tier.NONE,
                footprint="StubFP:R_THT",
                area_mm2=5.0,
            ),
            _record(
                "d-sot23",
                kind="diode",
                symbol="Stub:DSER",
                footprint="StubFP:SOT23",
                lcsc="C727126",
                tier=None,
                area_mm2=3.77,
                value="BAT54S",
            ),
            _record(
                "sw-ti",
                kind="analog-switch",
                lcsc="C10426",
                tier=Tier.EXTENDED,
                stock=Stock(TI_STOCK, FRESH, "test"),
                area_mm2=4.64,
            ),
            _record(
                "sw-umw",
                kind="analog-switch",
                lcsc="C3040658",
                tier=Tier.EXTENDED,
                stock=Stock(0, FRESH, "test"),
                area_mm2=4.64,
            ),
        ]
    )


def test_duplicate_names_raise() -> None:
    with pytest.raises(PartsDbError, match="duplicate part names"):
        PartsDb([_record("r"), _record("r")])


def test_duplicate_lcsc_raises() -> None:
    with pytest.raises(PartsDbError, match="duplicate LCSC"):
        PartsDb([_record("a", lcsc="C1"), _record("b", lcsc="C1")])


def test_malformed_lcsc_raises() -> None:
    with pytest.raises(PartsDbError, match="malformed LCSC"):
        _record("r", lcsc="727126")


def test_negative_stock_count_raises() -> None:
    with pytest.raises(PartsDbError, match="negative"):
        Stock(-1, FRESH, "test")


def test_find_by_name_and_lcsc(db: PartsDb) -> None:
    assert db.find("sw-ti").lcsc == "C10426"
    assert db.find("C10426").name == "sw-ti"
    with pytest.raises(PartsDbError, match="no part"):
        db.find("nope")


def test_select_without_filter_returns_the_whole_table(db: PartsDb) -> None:
    assert _names(db.select()) == ["r-basic", "r-tht", "d-sot23", "sw-ti", "sw-umw"]


def test_select_by_kind(db: PartsDb) -> None:
    assert _names(db.select(PartFilter(kind="analog-switch"))) == ["sw-ti", "sw-umw"]


def test_select_by_tier_excludes_unverified(db: PartsDb) -> None:
    assert _names(db.select(PartFilter(tier=Tier.BASIC))) == ["r-basic"]
    assert _names(db.select(PartFilter(tier=Tier.EXTENDED))) == ["sw-ti", "sw-umw"]


def test_select_by_area_bounds(db: PartsDb) -> None:
    assert _names(db.select(PartFilter(min_area_mm2=4.0))) == [
        "r-tht",
        "sw-ti",
        "sw-umw",
    ]
    assert _names(db.select(PartFilter(max_area_mm2=4.0))) == ["r-basic", "d-sot23"]
    assert _names(db.select(PartFilter(min_area_mm2=3.0, max_area_mm2=4.0))) == [
        "d-sot23"
    ]


def test_select_by_required_footprints(db: PartsDb) -> None:
    wanted = frozenset({"StubFP:SOT23", "StubFP:R_THT"})
    assert _names(db.select(PartFilter(footprints=wanted))) == ["r-tht", "d-sot23"]


def test_select_excludes_by_name_or_lcsc(db: PartsDb) -> None:
    assert _names(db.select(PartFilter(exclude=frozenset({"sw-ti"})))) == [
        "r-basic",
        "r-tht",
        "d-sot23",
        "sw-umw",
    ]
    assert _names(db.select(PartFilter(exclude=frozenset({"C10426", "C3040658"})))) == [
        "r-basic",
        "r-tht",
        "d-sot23",
    ]


def test_select_require_pins_one_record(db: PartsDb) -> None:
    assert _names(db.select(PartFilter(require="sw-ti"))) == ["sw-ti"]
    assert _names(db.select(PartFilter(require="C10426"))) == ["sw-ti"]
    overconstrained = PartFilter(kind="diode", require="sw-ti")
    assert db.select(overconstrained) == []


def test_select_in_stock(db: PartsDb) -> None:
    # sw-umw is a stock-out; r-tht and d-sot23 were never queried.
    assert _names(db.select(PartFilter(in_stock=True))) == ["r-basic", "sw-ti"]


def test_knobs_compose_conjunctively(db: PartsDb) -> None:
    assert _names(db.select(PartFilter(kind="analog-switch", in_stock=True))) == [
        "sw-ti"
    ]


def test_resolve_unique(db: PartsDb) -> None:
    assert db.resolve(PartFilter(kind="analog-switch", in_stock=True)).name == "sw-ti"


def test_resolve_zero_matches_raises(db: PartsDb) -> None:
    with pytest.raises(PartsDbError, match="no part"):
        db.resolve(PartFilter(kind="mcu"))


def test_resolve_ambiguous_raises_and_names_matches(db: PartsDb) -> None:
    with pytest.raises(PartsDbError, match=r"sw-ti.*sw-umw|sw-umw.*sw-ti"):
        db.resolve(PartFilter(kind="analog-switch"))


def test_bind_carries_the_record_identity(db: PartsDb) -> None:
    bound = db.bind("d-sot23", Bat54s)
    assert bound.__name__ == "d-sot23"
    assert bound.symbol == "Stub:DSER"
    assert bound.default_value == "BAT54S"
    assert bound.default_footprint == "StubFP:SOT23"
    named = db.bind("d-sot23", Bat54s, class_name="DbDiode")
    assert named.__name__ == "DbDiode"


def test_bound_class_places_and_wires(db: PartsDb, symbols: StubSymbols) -> None:
    bound = db.bind("d-sot23", Bat54s, class_name="DbDiode")
    c = Circuit("t", symbols)
    for name in ("g", "s", "x"):
        c.net(name)
    d1 = c.part("D1", bound(anode="g", cathode="s", com="x"))
    assert d1.symbol.ref == "Stub:DSER"
    assert d1.value == "BAT54S"
    assert d1.footprint == "StubFP:SOT23"
    assert d1["1"].net is c.nets["g"]


def test_bind_over_resistor_keeps_positional_value(
    db: PartsDb, symbols: StubSymbols
) -> None:
    bound = db.bind("r-basic", Resistor, class_name="DbR")
    c = Circuit("t", symbols)
    c.net("a")
    c.net("b")
    r1 = c.part("R1", bound("1k", a="a", b="b"))
    assert r1.value == "1k"
    assert r1.footprint == "StubFP:R_0603"


def test_bind_unknown_part_raises(db: PartsDb) -> None:
    with pytest.raises(PartsDbError, match="no part"):
        db.bind("nope", Resistor)


def test_fresh_table_checks_clean() -> None:
    db = PartsDb(
        [_record("r", tier=Tier.BASIC, stock=Stock(BASIC_STOCK, FRESH, "test"))]
    )
    assert db.check_stock(today=TODAY) == []


def test_stale_stock_is_flagged() -> None:
    db = PartsDb(
        [_record("r", tier=Tier.BASIC, stock=Stock(BASIC_STOCK, STALE, "test"))]
    )
    (issue,) = db.check_stock(today=TODAY)
    assert "stale" in issue.message
    assert str(STOCK_MAX_AGE_DAYS) in issue.message


def test_never_queried_stock_is_flagged(db: PartsDb) -> None:
    messages = [issue.message for issue in db.check_stock(today=TODAY)]
    assert any("d-sot23" in m and "never queried" in m for m in messages)


def test_stock_out_is_flagged(db: PartsDb) -> None:
    messages = [issue.message for issue in db.check_stock(today=TODAY)]
    assert any("sw-umw" in m and "out of stock" in m for m in messages)


def test_tier_none_is_not_assembler_placed_and_skips() -> None:
    db = PartsDb([_record("r-tht", tier=Tier.NONE)])
    assert db.check_stock(today=TODAY) == []


def test_unverified_tier_is_flagged(db: PartsDb) -> None:
    messages = [issue.message for issue in db.check_stock(today=TODAY)]
    assert any("d-sot23" in m and "tier unverified" in m for m in messages)


# --- the seeded project table (design/parts_db.py) ---


def test_seed_datasheet_and_spice_paths_exist() -> None:
    for record in parts_db.PARTS.records:
        if record.datasheet is not None:
            assert (REPO_ROOT / record.datasheet).is_dir(), record.name
        if record.spice is not None:
            assert (REPO_ROOT / record.spice.path).is_file(), record.name


def test_seed_assembler_placed_records_have_lcsc_or_a_bin_note() -> None:
    for record in parts_db.PARTS.records:
        if record.tier is Tier.EXTENDED:
            assert record.lcsc is not None, record.name
        if record.lcsc is None and record.tier is not Tier.NONE:
            assert record.note, record.name


def test_seed_freshness_flags_only_the_unverified() -> None:
    issues = parts_db.PARTS.check_stock(today=TODAY)
    flagged = {issue.message.split(":")[0] for issue in issues}
    assert flagged == SEED_UNVERIFIED


def test_watchdog_capture_binds_its_bins_from_the_db() -> None:
    db = parts_db.PARTS
    r = db.find("r-0603")
    bound_r = watchdog_chargepump.R0603
    assert (bound_r.symbol, bound_r.default_footprint) == (r.symbol, r.footprint)
    c = db.find("c-0603")
    bound_c = watchdog_chargepump.C0603
    assert (bound_c.symbol, bound_c.default_footprint) == (c.symbol, c.footprint)
    d = db.find("bat54s")
    bound_d = watchdog_chargepump.Bat54s
    assert (bound_d.symbol, bound_d.default_value, bound_d.default_footprint) == (
        d.symbol,
        d.value,
        d.footprint,
    )


def test_seed_records_resolve_against_kicad_libraries(
    kicad_libs: KiCadLibraries,
) -> None:
    for record in parts_db.PARTS.records:
        assert kicad_libs.lookup(record.symbol).ref == record.symbol, record.name
        assert kicad_libs.exists(record.footprint), record.name
