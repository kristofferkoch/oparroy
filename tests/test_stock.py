"""Stock-refresh tooling tests (docs/konnect-lessons.md §4).

The feed side runs against pinned verbatim feed rows
(tests/fixtures/jlcpcb-feed/ — see its README for provenance); no test
touches the network. Guards carry negative controls: each check has a
planted violation that must be caught.
"""

from __future__ import annotations

import ast
import csv
import shutil
import sqlite3
import subprocess
from datetime import date
from pathlib import Path

import pytest

from design.parts_db import PARTS
from oparroy.dsl import (
    FeedRow,
    PartRecord,
    PartsDb,
    Stock,
    Tier,
    tier_from_library_type,
)
from oparroy.stock import (
    SqliteFeedCache,
    StockToolError,
    install_cache,
    main,
    propose_edits,
)

FIXTURE_TSV = Path(__file__).parent / "fixtures" / "jlcpcb-feed" / "parts.tsv"
REPO_ROOT = Path(__file__).parent.parent
TODAY = date(2026, 10, 17)
FEED_SNAPSHOT = date(2026, 10, 15)
EXIT_ERROR = 2

FEED_COLUMNS = [
    "LCSC Part",
    "First Category",
    "Second Category",
    "MFR.Part",
    "Package",
    "Solder Joint",
    "Manufacturer",
    "Library Type",
    "Description",
    "Datasheet",
    "Price",
    "Stock",
]


class StubCache:
    """A dict-backed FeedCache stub."""

    def __init__(
        self, rows: dict[str, FeedRow], snapshot: date = FEED_SNAPSHOT
    ) -> None:
        self._rows = rows
        self._snapshot = snapshot

    @property
    def snapshot_date(self) -> date:
        """The stubbed feed snapshot date."""
        return self._snapshot

    def row(self, lcsc: str) -> FeedRow | None:
        """Return the stubbed row for an LCSC number."""
        return self._rows.get(lcsc)


def _write_upstream(
    db_path: Path, rows: list[dict[str, str]], *, drop: str = ""
) -> None:
    """Build a minimal upstream feed DB from rows keyed by the feed columns."""
    columns = [c for c in FEED_COLUMNS if c != drop]
    ddl = ", ".join(f'"{c}" TEXT' for c in columns)
    placeholders = ", ".join("?" for _ in columns)
    with sqlite3.connect(db_path) as con:
        con.execute(f"CREATE TABLE parts ({ddl})")
        con.executemany(
            f"INSERT INTO parts VALUES ({placeholders})",  # noqa: S608 — test fixture
            [[row.get(c, "") for c in columns] for row in rows],
        )


def _fixture_rows() -> list[dict[str, str]]:
    with FIXTURE_TSV.open(newline="") as tsv:
        return list(csv.DictReader(tsv, delimiter="\t"))


@pytest.fixture
def cache(tmp_path: Path) -> SqliteFeedCache:
    """Install the overlay cache from the pinned fixture feed."""
    upstream = tmp_path / "upstream.db"
    _write_upstream(upstream, _fixture_rows())
    install_cache(upstream, tmp_path / "cache.sqlite", snapshot_date=FEED_SNAPSHOT)
    return SqliteFeedCache(tmp_path / "cache.sqlite")


def _record(name: str, **overrides: object) -> PartRecord:
    fields: dict[str, object] = {
        "name": name,
        "kind": "resistor",
        "symbol": "Stub:R",
        "footprint": "StubFP:R_0603",
    }
    return PartRecord(**(fields | overrides))  # ty: ignore[invalid-argument-type]


# --- tier mapping ---


def test_tier_from_library_type() -> None:
    assert tier_from_library_type("Basic") is Tier.BASIC
    assert tier_from_library_type("Extended") is Tier.EXTENDED
    # Preferred is Extended-class for the §6 per-line fee budget.
    assert tier_from_library_type("Preferred") is Tier.EXTENDED


def test_tier_from_library_type_unknown_is_not_checked() -> None:
    assert tier_from_library_type("") is None
    assert tier_from_library_type("Economy") is None


# --- cache install ---


def test_install_cache_round_trips_the_fixture(cache: SqliteFeedCache) -> None:
    assert cache.snapshot_date == FEED_SNAPSHOT
    assert cache.row("C369929") == FeedRow(library_type="Extended", stock=681)
    assert cache.row("C5613") == FeedRow(library_type="Preferred", stock=250215)
    assert cache.row("C5947") == FeedRow(library_type="Basic", stock=282990)
    assert cache.row("C999999") is None


def test_install_rejects_a_schema_drift(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream.db"
    _write_upstream(upstream, _fixture_rows(), drop="Library Type")
    with pytest.raises(StockToolError, match="missing required columns"):
        install_cache(upstream, tmp_path / "cache.sqlite", snapshot_date=FEED_SNAPSHOT)
    assert not (tmp_path / "cache.sqlite").exists()


def test_install_rejects_a_non_numeric_stock(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream.db"
    rows = _fixture_rows()[:1]
    rows[0]["Stock"] = "many"
    _write_upstream(upstream, rows)
    with pytest.raises(StockToolError, match="non-numeric Stock"):
        install_cache(upstream, tmp_path / "cache.sqlite", snapshot_date=FEED_SNAPSHOT)


def test_install_rejects_a_duplicate_lcsc(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream.db"
    rows = _fixture_rows()[:2]
    rows[1]["LCSC Part"] = rows[0]["LCSC Part"]
    _write_upstream(upstream, rows)
    with pytest.raises(StockToolError, match="duplicate LCSC"):
        install_cache(upstream, tmp_path / "cache.sqlite", snapshot_date=FEED_SNAPSHOT)
    assert not (tmp_path / "cache.sqlite").exists()


def test_install_rejects_an_empty_feed(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream.db"
    _write_upstream(upstream, [])
    with pytest.raises(StockToolError, match="did not contain any parts"):
        install_cache(upstream, tmp_path / "cache.sqlite", snapshot_date=FEED_SNAPSHOT)


def test_empty_stock_is_unknown_never_zero(tmp_path: Path) -> None:
    # The fixture snapshot carries no empty-Stock rows (its README says
    # why), so the feed's unknown marker is exercised synthetically.
    upstream = tmp_path / "upstream.db"
    rows = _fixture_rows()[:1]
    rows[0]["Stock"] = ""
    _write_upstream(upstream, rows)
    install_cache(upstream, tmp_path / "cache.sqlite", snapshot_date=FEED_SNAPSHOT)
    row = SqliteFeedCache(tmp_path / "cache.sqlite").row(rows[0]["LCSC Part"])
    assert row is not None
    assert row.stock is None


def test_cache_without_snapshot_date_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "cache.sqlite"
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    with pytest.raises(StockToolError, match="snapshot_date"):
        SqliteFeedCache(path)


# --- check_stock against the cache ---


def test_cache_newer_than_the_snapshot_is_stale() -> None:
    db = PartsDb(
        [
            _record(
                "r",
                lcsc="C1",
                tier=Tier.EXTENDED,
                stock=Stock(100, date(2026, 10, 1), "test"),
            )
        ]
    )
    cache = StubCache({"C1": FeedRow(library_type="Extended", stock=100)})
    # Negative control: the same record is clean without the cache.
    assert db.check_stock(today=TODAY) == []
    (issue,) = db.check_stock(today=TODAY, cache=cache)
    assert "predates the feed cache" in issue.message


def test_cache_not_newer_than_the_snapshot_is_fresh() -> None:
    db = PartsDb(
        [
            _record(
                "r",
                lcsc="C1",
                tier=Tier.EXTENDED,
                stock=Stock(100, FEED_SNAPSHOT, "test"),
            )
        ]
    )
    cache = StubCache({"C1": FeedRow(library_type="Extended", stock=42)})
    assert db.check_stock(today=TODAY, cache=cache) == []


def test_lcsc_absent_from_the_feed_is_flagged() -> None:
    db = PartsDb(
        [
            _record(
                "r",
                lcsc="C1",
                tier=Tier.EXTENDED,
                stock=Stock(100, FEED_SNAPSHOT, "test"),
            )
        ]
    )
    (issue,) = db.check_stock(today=TODAY, cache=StubCache({}))
    assert "absent from the feed cache" in issue.message


def test_tier_drift_is_flagged() -> None:
    db = PartsDb(
        [
            _record(
                "r",
                lcsc="C1",
                tier=Tier.EXTENDED,
                stock=Stock(100, FEED_SNAPSHOT, "test"),
            )
        ]
    )
    cache = StubCache({"C1": FeedRow(library_type="Basic", stock=100)})
    (issue,) = db.check_stock(today=TODAY, cache=cache)
    assert "tier drift" in issue.message
    assert "'Basic'" in issue.message
    # Negative control: the matching tier stays silent.
    cache = StubCache({"C1": FeedRow(library_type="Extended", stock=100)})
    assert db.check_stock(today=TODAY, cache=cache) == []


def test_preferred_feed_tier_matches_extended_records() -> None:
    db = PartsDb(
        [
            _record(
                "r",
                lcsc="C1",
                tier=Tier.EXTENDED,
                stock=Stock(100, FEED_SNAPSHOT, "test"),
            )
        ]
    )
    cache = StubCache({"C1": FeedRow(library_type="Preferred", stock=100)})
    assert db.check_stock(today=TODAY, cache=cache) == []


def test_unmappable_library_type_is_said_out_loud() -> None:
    db = PartsDb(
        [
            _record(
                "r",
                lcsc="C1",
                tier=Tier.EXTENDED,
                stock=Stock(100, FEED_SNAPSHOT, "test"),
            )
        ]
    )
    cache = StubCache({"C1": FeedRow(library_type="Economy", stock=100)})
    (issue,) = db.check_stock(today=TODAY, cache=cache)
    assert "not understood" in issue.message


def test_records_without_lcsc_keep_the_age_based_audit() -> None:
    db = PartsDb(
        [
            _record(
                "r-bin",
                tier=Tier.BASIC,
                stock=Stock(100, date(2026, 1, 1), "test"),
            )
        ]
    )
    (issue,) = db.check_stock(today=TODAY, cache=StubCache({}))
    assert "stale" in issue.message


# --- proposed edits ---

MINI_SOURCE = """from oparroy.dsl import PartRecord, PartsDb, Stock, Tier

PARTS = PartsDb(
    [
        PartRecord(
            name="moves",
            kind="diode",
            symbol="Stub:D",
            footprint="StubFP:D",
            lcsc="C100",
            tier=Tier.EXTENDED,
            stock=Stock(
                1_181,
                date(2026, 10, 4),
                "hand-verified",
            ),
        ),
        PartRecord(
            name="flips",
            kind="diode",
            symbol="Stub:D",
            footprint="StubFP:D",
            lcsc="C200",
            tier=Tier.BASIC,
            stock=Stock(50, date(2026, 10, 15), "feed"),
        ),
        PartRecord(
            name="hand-soldered",
            kind="connector",
            symbol="Stub:CN",
            footprint="StubFP:CN",
            lcsc="C300",
            tier=Tier.NONE,
            stock=Stock(285, date(2026, 9, 29), "feed"),
        ),
        PartRecord(
            name="gone",
            kind="diode",
            symbol="Stub:D",
            footprint="StubFP:D",
            lcsc="C400",
            tier=Tier.EXTENDED,
            stock=Stock(10, date(2026, 10, 1), "feed"),
        ),
    ]
)
"""


def _mini_db() -> PartsDb:
    return PartsDb(
        [
            _record(
                "moves",
                kind="diode",
                lcsc="C100",
                tier=Tier.EXTENDED,
                stock=Stock(1_181, date(2026, 10, 4), "hand-verified"),
            ),
            _record(
                "flips",
                kind="diode",
                lcsc="C200",
                tier=Tier.BASIC,
                stock=Stock(50, FEED_SNAPSHOT, "feed"),
            ),
            _record(
                "hand-soldered",
                kind="connector",
                lcsc="C300",
                tier=Tier.NONE,
                stock=Stock(285, date(2026, 9, 29), "feed"),
            ),
            _record(
                "gone",
                kind="diode",
                lcsc="C400",
                tier=Tier.EXTENDED,
                stock=Stock(10, date(2026, 10, 1), "feed"),
            ),
        ]
    )


def _mini_cache() -> StubCache:
    return StubCache(
        {
            "C100": FeedRow(library_type="Extended", stock=681),
            "C200": FeedRow(library_type="Extended", stock=50),
            "C300": FeedRow(library_type="Extended", stock=42),
        }
    )


def test_propose_edits_updates_moved_stock() -> None:
    report = propose_edits(MINI_SOURCE, _mini_db(), _mini_cache(), "mini.py")
    edit = next(e for e in report.edits if e.record == "moves")
    assert edit.field == "stock"
    assert "681," in edit.new
    assert "date(2026, 10, 15)" in edit.new
    assert "kicad-jlcpcb-tools feed snapshot 2026-10-15" in edit.new


def test_propose_edits_flags_tier_drift_as_an_edit() -> None:
    report = propose_edits(MINI_SOURCE, _mini_db(), _mini_cache(), "mini.py")
    edit = next(e for e in report.edits if e.record == "flips")
    assert (edit.field, edit.old, edit.new) == ("tier", "Tier.BASIC", "Tier.EXTENDED")


def test_propose_edits_never_touches_tier_none_tiers() -> None:
    report = propose_edits(MINI_SOURCE, _mini_db(), _mini_cache(), "mini.py")
    edit = next(e for e in report.edits if e.record == "hand-soldered")
    assert edit.field == "stock"
    assert "42," in edit.new
    assert all(e.record != "hand-soldered" or e.field != "tier" for e in report.edits)


def test_propose_edits_flags_absent_feed_rows() -> None:
    report = propose_edits(MINI_SOURCE, _mini_db(), _mini_cache(), "mini.py")
    assert any("gone" in f and "absent from the feed" in f for f in report.flags)


def test_propose_edits_flags_unknown_feed_stock() -> None:
    cache = StubCache({"C100": FeedRow(library_type="Extended", stock=None)})
    report = propose_edits(MINI_SOURCE, _mini_db(), cache, "mini.py")
    assert not [e for e in report.edits if e.record == "moves"]
    assert any("moves" in f and "no stock figure" in f for f in report.flags)


def test_propose_edits_never_replaces_newer_evidence() -> None:
    cache = StubCache(
        {"C100": FeedRow(library_type="Extended", stock=681)},
        snapshot=date(2026, 10, 1),
    )
    report = propose_edits(MINI_SOURCE, _mini_db(), cache, "mini.py")
    assert not [e for e in report.edits if e.record == "moves"]
    assert any("moves" in f and "newer than the feed" in f for f in report.flags)


def test_propose_edits_flags_count_conflicts_at_equal_dates() -> None:
    cache = StubCache({"C200": FeedRow(library_type="Extended", stock=99)})
    report = propose_edits(MINI_SOURCE, _mini_db(), cache, "mini.py")
    assert not [e for e in report.edits if e.record == "flips" and e.field == "stock"]
    assert any("flips" in f and "count conflict" in f for f in report.flags)


def test_proposed_source_is_valid_and_formatter_stable() -> None:
    report = propose_edits(MINI_SOURCE, _mini_db(), _mini_cache(), "mini.py")
    ast.parse(report.new_source)
    ruff = shutil.which("ruff")
    if ruff is None:
        pytest.skip("ruff not on PATH")
    result = subprocess.run(  # noqa: S603 — ruff is the project's own formatter
        [ruff, "format", "--check", "-"],
        input=report.new_source,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_propose_edits_against_the_real_table_and_fixture(
    cache: SqliteFeedCache,
) -> None:
    source = (REPO_ROOT / "design" / "parts_db.py").read_text("utf-8")
    report = propose_edits(source, PARTS, cache, "design/parts_db.py")
    ast.parse(report.new_source)
    edited = {e.record for e in report.edits if e.field == "stock"}
    # The fixture snapshot (2026-10-15) postdates these committed
    # snapshots; the live-fetched 2026-10-16 records stay untouched.
    assert {
        "bat54s",
        "tvs-sod323",
        "sn74lvc1g3157-ti",
        "sn74lvc1g3157-umw",
        "ch32v003f4p6",
        "conn-idc-02x05",
        "led-rev1206-red",
        "led-rev1206-yellow",
        "led-rev1206-yellowgreen",
    } <= edited
    assert "rp2040" not in edited
    bat54s = next(e for e in report.edits if e.record == "bat54s")
    assert "681," in bat54s.new
    # No tier drift in the fixture: the DB's tiers match the feed's.
    assert not [e for e in report.edits if e.field == "tier"]
    assert report.diff.startswith("--- a/design/parts_db.py")


# --- CLI ---


def test_diff_without_a_cache_fails_closed(tmp_path: Path) -> None:
    rc = main(["diff", "--cache", str(tmp_path / "nope.sqlite")])
    assert rc == EXIT_ERROR
