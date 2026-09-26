"""oparroy design captures — boards and subcircuits in DSL form.

Each module here is one captured circuit (DESIGN.md §7): a
``capture(symbols)`` function building the IR, plus a ``main`` that
checks and emits. ``circuits/`` keeps the ngspice benches and device
models until T7e retires the hand-written DUT netlists.
"""
