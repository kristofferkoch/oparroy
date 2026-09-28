"""oparroy design captures — boards and subcircuits in DSL form.

Each board or subcircuit module is one captured circuit (DESIGN.md
§7): a ``capture(symbols)`` function building the IR, plus a ``main``
that checks and emits. Shared blocks (connector pinouts, per-project
part bins) are plain modules without a ``main`` — ``segment.py`` is
the §3 connector block. ``parts_db.py`` is the T7c parts table: the
assembler-inventory view plus the bound part bins, with a
stock-freshness report as its ``main``. ``circuits/`` keeps the
ngspice benches and device models until T7e retires the hand-written
DUT netlists.
"""
