"""Subcircuit composition (DESIGN.md §7): functional circuits as units.

A subcircuit is the unit of reuse, review, and test — one functional
circuit (the RC pulse watchdog, a node PHY front-end), captured through
the same API as a board, with its interface declared as ports
(``Circuit.port``). A board instantiates it with ``Circuit.instance`` —
the capture runs per instance, so instances never share wiring state —
and binds every port by keyword. ``Circuit.flatten`` is the pass that
reduces the hierarchy to the flat IR checks and emitters consume;
hierarchy survives flattening as metadata (hierarchical refdes,
sheetpaths), the hook channelization keys on (lay out one node,
replicate 8x).
"""

from abc import ABC, abstractmethod

from oparroy.dsl.ir import Circuit


class Subcircuit(ABC):
    """Base class for reusable subcircuits: override ``capture``.

    Instances are callable, so ``Circuit.instance`` accepts a
    ``Subcircuit`` or any ``Callable[[Circuit], None]`` alike.
    """

    @abstractmethod
    def capture(self, circuit: Circuit) -> None:
        """Build the subcircuit into ``circuit``, declaring its ports."""

    def __call__(self, circuit: Circuit) -> None:
        """Run the capture into ``circuit`` — instances are callables."""
        self.capture(circuit)
