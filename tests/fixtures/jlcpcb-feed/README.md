# jlcpcb-feed fixture — pinned verbatim feed rows

`parts.tsv` pins rows of the kicad-jlcpcb-tools parts feed (the source
the stock-refresh tooling mirrors — [konnect-lessons.md
§4](../../../docs/konnect-lessons.md#4-jlcpcb-catalog-without-the-api))
so `tests/test_stock.py` exercises the refresh against real feed data
with no network access.

## Provenance

- Source: `https://bouni.github.io/kicad-jlcpcb-tools/` — sentinel
  `chunk_num_current_parts_fts5.txt` (3 chunks), archive
  `current-parts-fts5.db.zip.001` … `.003`, concatenated and unzipped.
- Downloaded 2026-10-17; the feed snapshot's HTTP `Last-Modified` is
  2026-10-15 (this pair of dates is itself the fixture's fact).
- Full snapshot: 803,435 rows in the `parts` FTS5 table,
  `PRAGMA quick_check` = ok.
- Rows: every LCSC code bound in `design/parts_db.py` (21 rows), plus
  C1034 — a Preferred-tier part the DB does not carry, exercising the
  "row without a record" direction.
- Rows are **verbatim** feed rows (TSV, feed column order); only the
  header line was added. Do not edit values — a hand-touched fixture
  shares the assumption the code might get wrong.

## Known gap

This snapshot contains **zero** rows with an empty `Stock` field (the
feed's "unknown" marker — absent means unknown, never zero). The
unknown-stock path is therefore covered by synthetic rows constructed in
`tests/test_stock.py`, not by this fixture.
