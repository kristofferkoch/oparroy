"""The DSL parts DB: the assembler-inventory view over the parts in play.

DESIGN.md §6 settles part selection as **inventory-driven**: prefer
what the prototype assembler (JLCPCB) stocks, because every unique
Extended BOM line costs a setup fee. One :class:`PartRecord` per part
carries the sourcing columns — LCSC number, Basic/Extended tier, a
stock snapshot with its as-of date and source — plus the capture
bindings: the KiCad symbol/footprint pair, the ngspice model, and the
datasheet pointer into ``datasheets/``.

Selection is **constraint filtering over the table**, not lookup: a
:class:`PartFilter` is refinement data (kind, tier, area bounds,
allowed footprints, exclusions, a required part, an in-stock
constraint) and :meth:`PartsDb.select` returns every record the
filter admits. :meth:`PartsDb.bind` turns one record into a typed
part class, so captures draw their part bins from the table instead
of re-declaring symbol/footprint pairs per capture.

:meth:`PartsDb.check_stock` is the freshness audit: a snapshot older
than the budget is stale (re-query the assembler), a never-queried
part and an unverified tier are flagged, and a stock-out surfaces for
the checker's unsourcable-part check. Stock numbers are snapshots with
provenance, never live data.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING, TypeVar, cast

from oparroy.dsl.check import Issue, Severity

if TYPE_CHECKING:
    from collections.abc import Iterable

    from oparroy.dsl.parts import TypedPart

#: How old a stock snapshot may get before the freshness check flags it.
STOCK_MAX_AGE_DAYS = 90

_LCSC_RE = re.compile(r"C[1-9][0-9]*")

_TypedPartT = TypeVar("_TypedPartT", bound="TypedPart")


class PartsDbError(Exception):
    """A parts-table violation: bad table data or a failed resolution."""


class Tier(StrEnum):
    """The JLCPCB assembly tier — the §6 per-unique-BOM-line cost driver."""

    BASIC = "basic"
    EXTENDED = "extended"
    NONE = "none"  # not assembler-placed (through-hole, hand-soldered)


@dataclass(frozen=True)
class Stock:
    """One assembler stock snapshot: a count, good as of one date.

    >>> stock = Stock(count=51_000, as_of=date(2026, 9, 26), source="jlcsearch")
    >>> stock.age_days(date(2026, 10, 1))
    5
    """

    count: int
    as_of: date
    source: str

    def __post_init__(self) -> None:
        if self.count < 0:
            msg = f"stock count must not be negative, got {self.count}"
            raise PartsDbError(msg)

    def age_days(self, today: date) -> int:
        """Days from the snapshot to ``today`` (negative if ``today`` precedes it)."""
        return (today - self.as_of).days


@dataclass(frozen=True)
class SpiceModel:
    """An ngspice binding: the repo-relative model file, an optional subckt."""

    path: str
    subckt: str | None = None


@dataclass(frozen=True)
class PartRecord:
    """One part: the sourcing columns plus the capture bindings.

    ``kind`` is the part class a filter draws from (``"resistor"``,
    ``"diode"``, ``"analog-switch"``, …). ``tier=None`` means the
    assembly tier is unverified — a conservative filter never admits
    it. ``stock=None`` means the assembler was never queried for this
    part. ``area_mm2`` is the nominal body rectangle, the currency of
    the area-bound filter knobs.
    """

    name: str
    kind: str
    symbol: str
    footprint: str
    lcsc: str | None = None
    tier: Tier | None = None
    stock: Stock | None = None
    value: str | None = None
    area_mm2: float | None = None
    spice: SpiceModel | None = None
    datasheet: str | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            msg = "part record name must not be empty"
            raise PartsDbError(msg)
        if self.lcsc is not None and not _LCSC_RE.fullmatch(self.lcsc):
            msg = f"{self.name}: malformed LCSC number {self.lcsc!r}"
            raise PartsDbError(msg)

    @property
    def in_stock(self) -> bool:
        """True when a snapshot shows positive stock."""
        return self.stock is not None and self.stock.count > 0


@dataclass(frozen=True)
class PartFilter:
    """Refinement data narrowing the table; every knob composes conjunctively.

    All knobs are optional; an empty filter admits the whole table.
    ``exclude`` and ``require`` take record names or LCSC numbers —
    exclusions are how a later pass rules a stock-out out, ``require``
    pins the selection to exactly one record. ``footprints`` is the
    allowed-footprint set. ``in_stock`` turns assembler-stock status
    from a column into a checked constraint.
    """

    kind: str | None = None
    tier: Tier | None = None
    min_area_mm2: float | None = None
    max_area_mm2: float | None = None
    footprints: frozenset[str] = frozenset()
    exclude: frozenset[str] = frozenset()
    require: str | None = None
    in_stock: bool = False

    def matches(self, record: PartRecord) -> bool:
        """Return True when ``record`` passes every knob of this filter.

        >>> r = PartRecord(
        ...     name="r", kind="resistor", symbol="S:R",
        ...     footprint="F:R", tier=Tier.BASIC,
        ... )
        >>> PartFilter(kind="resistor", tier=Tier.BASIC).matches(r)
        True
        >>> PartFilter(tier=Tier.EXTENDED).matches(r)
        False
        """
        return all(
            (
                self.kind is None or record.kind == self.kind,
                self.tier is None or record.tier is self.tier,
                self.min_area_mm2 is None
                or (
                    record.area_mm2 is not None and record.area_mm2 >= self.min_area_mm2
                ),
                self.max_area_mm2 is None
                or (
                    record.area_mm2 is not None and record.area_mm2 <= self.max_area_mm2
                ),
                not self.footprints or record.footprint in self.footprints,
                record.name not in self.exclude
                and (record.lcsc is None or record.lcsc not in self.exclude),
                self.require is None or self.require in (record.name, record.lcsc),
                not self.in_stock or record.in_stock,
            )
        )


class PartsDb:
    """The parts table: records plus constraint-filtered selection over them."""

    def __init__(self, records: Iterable[PartRecord]) -> None:
        self._records = tuple(records)
        names = Counter(record.name for record in self._records)
        if dupes := sorted(name for name, n in names.items() if n > 1):
            msg = f"duplicate part names in the DB: {dupes}"
            raise PartsDbError(msg)
        lcscs = Counter(
            record.lcsc for record in self._records if record.lcsc is not None
        )
        if dupes := sorted(lcsc for lcsc, n in lcscs.items() if n > 1):
            msg = f"duplicate LCSC numbers in the DB: {dupes}"
            raise PartsDbError(msg)

    @property
    def records(self) -> tuple[PartRecord, ...]:
        """All records, in table order."""
        return self._records

    def find(self, key: str) -> PartRecord:
        """Look up one record by name or LCSC number; unknown keys raise."""
        for record in self._records:
            if record.name == key:
                return record
        for record in self._records:
            if record.lcsc == key:
                return record
        msg = f"no part named or numbered {key!r} in the DB"
        raise PartsDbError(msg)

    def select(self, part_filter: PartFilter | None = None) -> list[PartRecord]:
        """Every record the filter admits, in table order (None = the table)."""
        pf = part_filter if part_filter is not None else PartFilter()
        return [record for record in self._records if pf.matches(record)]

    def resolve(self, part_filter: PartFilter | None = None) -> PartRecord:
        """Resolve a filter to exactly one record; zero or several matches raise."""
        matches = self.select(part_filter)
        if not matches:
            msg = f"no part in the DB matches {part_filter!r}"
            raise PartsDbError(msg)
        if len(matches) > 1:
            names = ", ".join(record.name for record in matches)
            msg = f"filter admits {len(matches)} parts ({names}) — tighten it"
            raise PartsDbError(msg)
        return matches[0]

    def bind(
        self,
        key: str,
        base: type[_TypedPartT],
        *,
        class_name: str | None = None,
    ) -> type[_TypedPartT]:
        """Build a typed part class whose symbol/value/footprint come from the DB.

        The record is authoritative: the returned subclass of ``base``
        carries its symbol, default value, and default footprint —
        including Nones, which clear a base-class default. Binding is
        unconditional: stock status constrains *selection*, and stale
        or missing stock is the freshness audit's job, so a moving
        stock number never breaks a capture at import.
        """
        record = self.find(key)
        namespace = {
            "__doc__": (
                f"{record.name} from the parts DB "
                f"({record.lcsc or 'no LCSC number'}); bound via PartsDb.bind."
            ),
            "symbol": record.symbol,
            "default_value": record.value,
            "default_footprint": record.footprint,
        }
        return cast(
            "type[_TypedPartT]",
            type(class_name or record.name, (base,), namespace),
        )

    def check_stock(
        self,
        *,
        today: date | None = None,
        max_age_days: int = STOCK_MAX_AGE_DAYS,
    ) -> list[Issue]:
        """Audit the freshness of the table's stock snapshots (§6).

        Flags, per assembler-placed record: an unverified tier, a
        never-queried stock, a stale snapshot (older than
        ``max_age_days`` — re-query the assembler), and a stock-out
        (feeds the checker's unsourcable-part check). Tier-NONE parts are not
        assembler-placed and are skipped. All findings are warnings;
        the per-capture gate is the check pass's.
        """
        if today is None:
            today = date.today()  # noqa: DTZ011 — stock snapshots are calendar dates
        issues: list[Issue] = []
        for record in self._records:
            if record.tier is Tier.NONE:
                continue
            if record.tier is None:
                issues.append(
                    Issue(Severity.WARNING, f"{record.name}: assembly tier unverified")
                )
            if record.stock is None:
                issues.append(
                    Issue(Severity.WARNING, f"{record.name}: stock never queried")
                )
                continue
            if record.stock.count == 0:
                issues.append(
                    Issue(
                        Severity.WARNING,
                        f"{record.name}: out of stock (0 as of {record.stock.as_of})",
                    )
                )
            elif (age := record.stock.age_days(today)) > max_age_days:
                issues.append(
                    Issue(
                        Severity.WARNING,
                        f"{record.name}: stock snapshot stale — {age} days old "
                        f"(as of {record.stock.as_of}, budget {max_age_days} days); "
                        "re-query the assembler",
                    )
                )
        return issues
