"""The JLCPCB feed overlay cache and the parts-DB stock refresh.

docs/konnect-lessons.md §4 settles the sourcing: skip the JLCPCB/LCSC
API and its rate-limit/auth unknowns — mirror the kicad-jlcpcb-tools
SQLite feed (GitHub Pages, no auth, one bulk download), keep a local
overlay cache keyed by LCSC code, and emit *proposed edits* to
``design/parts_db.py`` as a reviewable unified diff. The data-as-code
file stays hand-authored; this module never rewrites it. The catalog
is discovery evidence, not order-time truth — re-query JLCPCB before
ordering.

The cache also feeds :meth:`oparroy.dsl.parts_db.PartsDb.check_stock`,
which audits committed stock snapshots against the cache's feed
snapshot date instead of a bare age budget.

    python -m oparroy.stock fetch   # mirror the feed into the cache
    python -m oparroy.stock diff    # emit proposed parts_db.py edits

``fetch`` runs from anywhere (the cache defaults to the user cache home);
``diff`` wants the repo root for its relative ``--db`` default.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import difflib
import os
import sqlite3
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date
from email.message import Message
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.response import addinfourl

from oparroy.dsl import (
    FeedCache,
    FeedRow,
    PartRecord,
    PartsDb,
    Tier,
    tier_from_library_type,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

#: The kicad-jlcpcb-tools feed: a sentinel naming the chunk count, then
#: that many zip slices to concatenate (docs/konnect-lessons.md §4).
FEED_BASE_URL = "https://bouni.github.io/kicad-jlcpcb-tools"
FEED_SENTINEL = "chunk_num_current_parts_fts5.txt"
FEED_ARCHIVE = "current-parts-fts5.db.zip"

#: Feed size caps — a runaway or hostile response fails closed.
MAX_CHUNKS = 64
MAX_ARCHIVE_BYTES = 1 << 30
MAX_DATABASE_BYTES = 8 << 30


def default_cache_path() -> Path:
    """Return the default overlay cache location: ``$XDG_CACHE_HOME/oparroy/``.

    User-level cache home (falling back to ``~/.cache``) so the mirror is
    shared across git worktrees and survives their removal — a per-repo
    ``build/`` path meant every worktree started cold.
    """
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "oparroy" / "stock-cache.sqlite"


#: Where the overlay cache and the hand-authored table live by default.
DEFAULT_CACHE_PATH = default_cache_path()
DEFAULT_DB_PATH = Path("design/parts_db.py")

_HTTP_TIMEOUT_S = 30

#: Columns the upstream feed's ``parts`` table must carry.
_REQUIRED_COLUMNS = frozenset(
    {"LCSC Part", "MFR.Part", "Library Type", "Stock", "Price"}
)


class StockToolError(Exception):
    """A feed or cache violation: bad upstream data or a failed refresh."""


@dataclass(frozen=True)
class FeedDownload:
    """The unpacked upstream feed database plus its provenance."""

    db_path: Path
    snapshot_date: date
    chunks: int
    archive_bytes: int


@dataclass(frozen=True)
class EditProposal:
    """One proposed literal replacement in the parts-table source."""

    record: str
    field: str  # "stock" | "tier"
    old: str
    new: str


@dataclass(frozen=True)
class ProposalReport:
    """The proposed-edits diff plus what could not be proposed.

    ``flags`` names the rows no edit was emitted for — a feed row
    without a stock figure, a record the feed does not list, an
    unmappable Library Type. "Not proposed" is always said out loud,
    never silently skipped.
    """

    diff: str
    new_source: str
    edits: tuple[EditProposal, ...]
    flags: tuple[str, ...]


def _open_url(url: str) -> addinfourl:
    try:
        return urllib.request.urlopen(  # noqa: S310 — fixed https feed host
            url, timeout=_HTTP_TIMEOUT_S
        )
    except OSError as exc:
        msg = f"feed download failed for {url}: {exc}"
        raise StockToolError(msg) from exc


def _chunk_count() -> int:
    """Read and bound the feed sentinel's chunk count."""
    with _open_url(f"{FEED_BASE_URL}/{FEED_SENTINEL}") as response:
        sentinel = response.read(256).decode("utf-8", "replace")
    try:
        chunks = int(sentinel.strip())
    except ValueError:
        msg = f"feed sentinel is not a chunk count: {sentinel!r}"
        raise StockToolError(msg) from None
    if not 1 <= chunks <= MAX_CHUNKS:
        msg = f"feed chunk count {chunks} is outside 1..{MAX_CHUNKS}"
        raise StockToolError(msg)
    return chunks


def _snapshot_date_from(headers: Message) -> date | None:
    """Parse the archive's HTTP Last-Modified; None when absent/invalid."""
    last_modified = headers.get("Last-Modified")
    if not last_modified:
        return None
    try:
        return parsedate_to_datetime(last_modified).date()
    except TypeError, ValueError:
        return None


def _stream_archive(archive_path: Path, chunks: int) -> tuple[date | None, int]:
    """Stream the feed chunks into one concatenated archive."""
    snapshot_date: date | None = None
    archive_bytes = 0
    with archive_path.open("wb") as archive:
        for chunk in range(1, chunks + 1):
            url = f"{FEED_BASE_URL}/{FEED_ARCHIVE}.{chunk:03d}"
            with _open_url(url) as response:
                if snapshot_date is None:
                    snapshot_date = _snapshot_date_from(response.headers)
                while block := response.read(1 << 20):
                    archive_bytes += len(block)
                    if archive_bytes > MAX_ARCHIVE_BYTES:
                        msg = f"feed archive exceeds {MAX_ARCHIVE_BYTES} bytes"
                        raise StockToolError(msg)
                    archive.write(block)
    return snapshot_date, archive_bytes


def _unpack_database(archive_path: Path, db_path: Path) -> None:
    """Unzip the single database member with a size cap."""
    with zipfile.ZipFile(archive_path) as archive_zip:
        members = [m for m in archive_zip.infolist() if not m.is_dir()]
        if len(members) != 1:
            msg = f"feed archive holds {len(members)} files, expected exactly 1"
            raise StockToolError(msg)
        with archive_zip.open(members[0]) as member, db_path.open("wb") as out:
            total = 0
            while block := member.read(1 << 20):
                total += len(block)
                if total > MAX_DATABASE_BYTES:
                    msg = f"feed database exceeds {MAX_DATABASE_BYTES} bytes"
                    raise StockToolError(msg)
                out.write(block)


def fetch_feed(dest_dir: Path) -> FeedDownload:
    """Download the feed into ``dest_dir``; return the unpacked DB + provenance.

    The snapshot date is the archive's HTTP Last-Modified — the feed
    carries no explicit date — falling back to the fetch date when the
    server omits the header.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    chunks = _chunk_count()
    archive_path = dest_dir / FEED_ARCHIVE
    try:
        snapshot_date, archive_bytes = _stream_archive(archive_path, chunks)
    except BaseException:
        archive_path.unlink(missing_ok=True)
        raise
    db_path = dest_dir / "upstream-parts.db"
    try:
        _unpack_database(archive_path, db_path)
    except BaseException:
        db_path.unlink(missing_ok=True)
        raise
    return FeedDownload(
        db_path=db_path,
        snapshot_date=snapshot_date or date.today(),  # noqa: DTZ011 — calendar date
        chunks=chunks,
        archive_bytes=archive_bytes,
    )


def _read_upstream_rows(upstream_db: Path) -> list[tuple[str, str, str, int | None]]:
    """Read validated rows out of the upstream feed's ``parts`` table."""
    uri = f"file:{upstream_db.resolve()}?mode=ro"
    with contextlib.closing(sqlite3.connect(uri, uri=True)) as upstream:
        upstream.execute("PRAGMA query_only=ON")
        columns = {
            row[1] for row in upstream.execute("PRAGMA table_info(parts)").fetchall()
        }
        if missing := sorted(_REQUIRED_COLUMNS - columns):
            msg = f"feed schema is missing required columns: {', '.join(missing)}"
            raise StockToolError(msg)
        rows: list[tuple[str, str, str, int | None]] = []
        for lcsc_raw, mfr_part, library_type, stock_raw in upstream.execute(
            'SELECT "LCSC Part", "MFR.Part", "Library Type", "Stock" FROM parts'
        ):
            lcsc = str(lcsc_raw).strip()
            if not lcsc:
                continue
            stock = str(stock_raw).strip()
            if not stock:
                count = None  # the feed's unknown marker — never zero
            elif stock.isdigit():
                count = int(stock)
            else:
                msg = f"feed row {lcsc}: non-numeric Stock {stock!r}"
                raise StockToolError(msg)
            rows.append((lcsc, str(mfr_part), str(library_type), count))
    return rows


def install_cache(upstream_db: Path, cache_path: Path, *, snapshot_date: date) -> int:
    """Re-import the upstream feed into the overlay cache; return the row count.

    The cache is built at a sibling staging path and atomically renamed
    into place after ``PRAGMA quick_check`` passes — a failed refresh
    never leaves a half-written cache behind.
    """
    rows = _read_upstream_rows(upstream_db)
    if not rows:
        msg = "feed did not contain any parts"
        raise StockToolError(msg)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    staging = cache_path.with_name(f"{cache_path.name}.staging-{os.getpid()}")
    try:
        with contextlib.closing(sqlite3.connect(staging)) as cache:
            cache.execute("PRAGMA journal_mode=OFF")
            cache.execute("PRAGMA synchronous=OFF")
            cache.executescript(
                "CREATE TABLE components ("
                "lcsc TEXT NOT NULL PRIMARY KEY, "
                "mfr_part TEXT NOT NULL, "
                "library_type TEXT NOT NULL, "
                "stock INTEGER);"
                "CREATE TABLE meta ("
                "key TEXT NOT NULL PRIMARY KEY, value TEXT NOT NULL);"
            )
            try:
                cache.executemany("INSERT INTO components VALUES (?, ?, ?, ?)", rows)
            except sqlite3.IntegrityError as exc:
                msg = f"feed lists a duplicate LCSC number: {exc}"
                raise StockToolError(msg) from exc
            cache.executemany(
                "INSERT INTO meta VALUES (?, ?)",
                [
                    ("snapshot_date", snapshot_date.isoformat()),
                    ("fetched_at", date.today().isoformat()),  # noqa: DTZ011
                    ("part_count", str(len(rows))),
                    ("feed_url", FEED_BASE_URL),
                ],
            )
            cache.commit()
            quick_check = cache.execute("PRAGMA quick_check").fetchone()[0]
            if quick_check != "ok":
                msg = f"cache failed validation: {quick_check}"
                raise StockToolError(msg)
        staging.replace(cache_path)
    finally:
        staging.unlink(missing_ok=True)
    return len(rows)


class SqliteFeedCache:
    """The installed overlay cache — the :class:`FeedCache` over SQLite."""

    def __init__(self, path: Path) -> None:
        self._path = path
        with self._connect() as con:
            row = con.execute(
                "SELECT value FROM meta WHERE key = 'snapshot_date'"
            ).fetchone()
        if row is None:
            msg = f"{path}: cache carries no snapshot_date — reinstall it"
            raise StockToolError(msg)
        self._snapshot_date = date.fromisoformat(row[0])

    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        uri = f"file:{self._path.resolve()}?mode=ro"
        with contextlib.closing(sqlite3.connect(uri, uri=True)) as con:
            con.execute("PRAGMA query_only=ON")
            yield con

    @property
    def snapshot_date(self) -> date:
        """The feed snapshot's own date — the staleness yardstick."""
        return self._snapshot_date

    def row(self, lcsc: str) -> FeedRow | None:
        """Return the cache row for an LCSC number; None when the feed lacks it."""
        with self._connect() as con:
            row = con.execute(
                "SELECT library_type, stock FROM components WHERE lcsc = ?",
                (lcsc,),
            ).fetchone()
        if row is None:
            return None
        return FeedRow(library_type=row[0], stock=row[1])


def _stock_literal(count: int, snapshot: date, keyword_col: int) -> str:
    """Build the replacement ``Stock(...)`` literal, exploded, formatter-stable.

    ``keyword_col`` is the column of the ``stock=`` keyword — the
    closing paren's indent; the arguments sit one level deeper. The
    trailing comma pins the exploded layout under the formatter.

    >>> print(_stock_literal(53765, date(2026, 10, 15), 12))
    Stock(
                    53_765,
                    date(2026, 10, 15),
                    "kicad-jlcpcb-tools feed snapshot 2026-10-15",
                )
    """
    args = " " * (keyword_col + 4)
    close = " " * keyword_col
    return (
        "Stock(\n"
        f"{args}{count:_},\n"
        f"{args}date({snapshot.year}, {snapshot.month}, {snapshot.day}),\n"
        f'{args}"kicad-jlcpcb-tools feed snapshot {snapshot.isoformat()}",\n'
        f"{close})"
    )


def _part_record_calls(source: bytes) -> dict[str, ast.Call]:
    """Map each ``PartRecord(...)`` call's ``name=`` literal to the call node."""
    tree = ast.parse(source)
    calls: dict[str, ast.Call] = {}
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "PartRecord"
        ):
            continue
        for keyword in node.keywords:
            if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                calls[str(keyword.value.value)] = node
    return calls


def _keyword(call: ast.Call, arg: str) -> ast.keyword | None:
    return next((kw for kw in call.keywords if kw.arg == arg), None)


class _Surgery:
    """Byte-span edits over one source file, plus the human report."""

    def __init__(self, source: str) -> None:
        self._source = source.encode("utf-8")
        self._line_offsets = [0]
        for line in self._source.splitlines(keepends=True):
            self._line_offsets.append(self._line_offsets[-1] + len(line))
        self.edits: list[EditProposal] = []
        self.flags: list[str] = []
        self._spans: list[tuple[int, int, bytes]] = []

    def _span(self, node: ast.expr) -> tuple[int, int]:
        # ast columns are UTF-8 byte offsets, hence the byte-level surgery.
        assert node.end_lineno is not None  # noqa: S101 — ast guarantees it
        assert node.end_col_offset is not None  # noqa: S101
        start = self._line_offsets[node.lineno - 1] + node.col_offset
        end = self._line_offsets[node.end_lineno - 1] + node.end_col_offset
        return start, end

    def replace(self, node: ast.expr, new: str, record: str, field: str) -> None:
        """Propose replacing the node's source text with ``new``."""
        start, end = self._span(node)
        old = self._source[start:end].decode("utf-8")
        if old == new:
            return
        self._spans.append((start, end, new.encode("utf-8")))
        self.edits.append(EditProposal(record=record, field=field, old=old, new=new))

    def patched(self) -> str:
        """Apply all proposed spans (reverse offset order) and decode."""
        patched = self._source
        for start, end, new in sorted(self._spans, reverse=True):
            patched = patched[:start] + new + patched[end:]
        return patched.decode("utf-8")


def _propose_stock(
    surgery: _Surgery, record: PartRecord, row: FeedRow, call: ast.Call, snapshot: date
) -> None:
    """Propose the ``stock=`` edit for one record, or flag why not."""
    stock = record.stock
    if row.stock is None:
        surgery.flags.append(f"{record.name}: the feed carries no stock figure")
        return
    if stock is None:
        surgery.flags.append(
            f"{record.name}: stock never queried — the feed lists "
            f"{row.stock}; add the snapshot by hand"
        )
        return
    if snapshot < stock.as_of:
        surgery.flags.append(
            f"{record.name}: the committed snapshot ({stock.as_of}) is newer "
            f"than the feed ({snapshot}) — left alone"
        )
        return
    if snapshot == stock.as_of and row.stock != stock.count:
        surgery.flags.append(
            f"{record.name}: count conflict at snapshot {snapshot} — "
            f"committed {stock.count}, feed {row.stock}; verify by hand"
        )
        return
    if row.stock == stock.count and snapshot == stock.as_of:
        return
    stock_kw = _keyword(call, "stock")
    if stock_kw is None:
        surgery.flags.append(f"{record.name}: no stock= keyword found — skipped")
        return
    surgery.replace(
        stock_kw.value,
        _stock_literal(row.stock, snapshot, stock_kw.col_offset),
        record.name,
        "stock",
    )


def _propose_tier(
    surgery: _Surgery, record: PartRecord, row: FeedRow, call: ast.Call
) -> None:
    """Propose the ``tier=`` edit for one record, or flag why not."""
    if record.tier is Tier.NONE:
        return  # not assembler-placed — the feed tier is moot
    feed_tier = tier_from_library_type(row.library_type)
    if feed_tier is None:
        surgery.flags.append(
            f"{record.name}: feed Library Type {row.library_type!r} not "
            "understood — tier not checked"
        )
        return
    if record.tier is None:
        surgery.flags.append(
            f"{record.name}: tier unverified — the feed lists {row.library_type!r}"
        )
        return
    if feed_tier is not record.tier:
        tier_kw = _keyword(call, "tier")
        if tier_kw is not None:
            surgery.replace(
                tier_kw.value, f"Tier.{feed_tier.name}", record.name, "tier"
            )


def _propose_record(
    surgery: _Surgery, record: PartRecord, call: ast.Call, cache: FeedCache
) -> None:
    """Propose the edits for one LCSC-carrying record, or flag why not."""
    assert record.lcsc is not None  # noqa: S101 — the caller filters
    lcsc_kw = _keyword(call, "lcsc")
    if not (
        lcsc_kw is not None
        and isinstance(lcsc_kw.value, ast.Constant)
        and lcsc_kw.value.value == record.lcsc
    ):
        surgery.flags.append(
            f"{record.name}: source lcsc= does not match {record.lcsc} — skipped"
        )
        return
    row = cache.row(record.lcsc)
    if row is None:
        surgery.flags.append(
            f"{record.name}: {record.lcsc} absent from the feed "
            f"(snapshot {cache.snapshot_date})"
        )
        return
    _propose_stock(surgery, record, row, call, cache.snapshot_date)
    _propose_tier(surgery, record, row, call)


def propose_edits(
    source: str, db: PartsDb, cache: FeedCache, path: str
) -> ProposalReport:
    """Propose stock/tier edits to the parts-table source as a unified diff.

    Only LCSC-carrying records with a cache row are considered. A
    record's ``stock=Stock(...)`` literal is re-proposed when the feed
    snapshot is newer than the committed one (the feed never replaces
    newer hand-verified evidence — those records are flagged and left
    alone, as are count conflicts at equal dates); ``tier=`` when the
    mapped feed Library Type disagrees (Tier.NONE records are not
    assembler-placed — stock yes, tier never). Everything else is a
    flag in the report, not an edit.
    """
    surgery = _Surgery(source)
    calls = _part_record_calls(source.encode("utf-8"))
    for record in db.records:
        if record.lcsc is None:
            continue
        call = calls.get(record.name)
        if call is None:
            surgery.flags.append(f"{record.name}: no PartRecord call found in {path}")
            continue
        _propose_record(surgery, record, call, cache)
    new_source = surgery.patched()
    diff = "".join(
        difflib.unified_diff(
            source.splitlines(keepends=True),
            new_source.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
    return ProposalReport(
        diff=diff,
        new_source=new_source,
        edits=tuple(surgery.edits),
        flags=tuple(surgery.flags),
    )


def _load_parts_db(db_path: Path) -> PartsDb:
    """Import the hand-authored parts table (run from the repo root)."""
    sys.path.insert(0, str(db_path.parent.parent.resolve()))
    try:
        from design.parts_db import (  # noqa: PLC0415 — needs the sys.path insert
            PARTS,
        )
    except ImportError as exc:
        msg = f"cannot import {db_path} as design.parts_db — run from the repo root"
        raise StockToolError(msg) from exc
    return PARTS


def _cmd_fetch(args: argparse.Namespace) -> int:
    cache_path: Path = args.cache
    with tempfile.TemporaryDirectory(prefix="oparroy-feed-") as tmp:
        download = fetch_feed(Path(tmp))
        count = install_cache(
            download.db_path, cache_path, snapshot_date=download.snapshot_date
        )
    sys.stdout.write(
        f"feed snapshot {download.snapshot_date}: {count} parts "
        f"({download.chunks} chunks, {download.archive_bytes} archive bytes) "
        f"installed at {cache_path}\n"
    )
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    cache_path: Path = args.cache
    db_path: Path = args.db
    if not cache_path.is_file():
        sys.stderr.write(
            f"no feed cache at {cache_path} — run python -m oparroy.stock fetch\n"
        )
        return 2
    cache = SqliteFeedCache(cache_path)
    db = _load_parts_db(db_path)
    report = propose_edits(db_path.read_text("utf-8"), db, cache, str(db_path))
    if report.diff:
        if args.output:
            args.output.write_text(report.diff, "utf-8")
            sys.stderr.write(f"proposed edits written to {args.output}\n")
        else:
            sys.stdout.write(report.diff)
    else:
        sys.stdout.write("parts table is in sync with the feed cache\n")
    for flag in report.flags:
        sys.stderr.write(f"flag: {flag}\n")
    sys.stderr.write(f"{len(report.edits)} proposed edits, {len(report.flags)} flags\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the stock-refresh CLI: ``fetch`` the feed, ``diff`` the parts table."""
    parser = argparse.ArgumentParser(prog="python -m oparroy.stock")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("fetch", "mirror the kicad-jlcpcb-tools feed into the overlay cache"),
        ("diff", "emit proposed parts_db.py edits as a unified diff"),
    ):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument(
            "--cache",
            type=Path,
            default=DEFAULT_CACHE_PATH,
            help=f"overlay cache path (default {DEFAULT_CACHE_PATH})",
        )
        if name == "fetch":
            cmd.set_defaults(func=_cmd_fetch)
        else:
            cmd.add_argument(
                "--db",
                type=Path,
                default=DEFAULT_DB_PATH,
                help=f"parts table path (default {DEFAULT_DB_PATH})",
            )
            cmd.add_argument(
                "--output",
                type=Path,
                default=None,
                help="write the diff here instead of stdout",
            )
            cmd.set_defaults(func=_cmd_diff)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except StockToolError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
