"""Simulation-only parts: external ngspice subcircuit instances.

A simulation DUT (``design/phy_segment.py``) instantiates subcircuits
that live outside the DSL — the hand-written device models of
``circuits/lib/*.spi`` (``ch32v003_tx_pin``, ``sn74lvc1g3157``, …).
:class:`SimSymbols` wraps the capture's symbol table and synthesizes a
``Sim:<subckt>`` symbol per registered subcircuit, pins numbered 1..N
in the subcircuit's port order; ``subckt()`` returns the typed part
class wiring those ports by name. The spice emitter renders placed
instances as X-elements with their nets in port order
(:mod:`oparroy.dsl.spice_emit`); the instance's ``params:`` mapping
becomes the element's ``params: k={v} …`` tail verbatim, so deck-level
brace expressions forward the enclosing subcircuit's own parameters.

Sim parts are simulation-only (``Symbol.is_sim``): no footprint, and
the KiCad netlist emitter refuses them — a ``Sim:`` part reaching the
board netlist is a capture bug, not a board part.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, ClassVar, cast

from oparroy.dsl.ir import DefinitionError, PinType, Symbol, SymbolPin
from oparroy.dsl.parts import TypedPart

if TYPE_CHECKING:
    from collections.abc import Sequence

    from oparroy.dsl.ir import Net, SymbolTable


class SubcktInst(TypedPart):
    """Instance of a registered external subcircuit, wired by port name.

    Never constructed directly — ``SimSymbols.subckt()`` returns a
    per-subcircuit subclass with ``symbol``/``pin_map`` fixed. The
    ports wire as keyword-only parameters; the ``params=`` keyword
    carries the instance's parameter mapping, rendered as the deck's
    ``params: k={v} …`` tail verbatim so brace expressions forward the
    enclosing subcircuit's own parameters. (``params`` rides inside
    ``**nets`` — a separate keyword-only parameter makes the type
    checker reject ``**`` wiring of ports named like Python keywords.)
    """

    symbol: ClassVar[str]
    pin_map: ClassVar[dict[str, str]]

    def __init__(self, **nets: Net | str | Mapping[str, str]) -> None:
        params = nets.pop("params", None)
        if params is not None and not isinstance(params, Mapping):
            msg = f"params must be a mapping, got {params!r}"
            raise DefinitionError(msg)
        tail = " ".join(f"{key}={value}" for key, value in (params or {}).items())
        wiring = cast("dict[str, Net | str]", nets)
        super().__init__(f"params: {tail}" if tail else None, None, wiring)


class SimSymbols:
    """SymbolTable wrapper adding synthesized ``Sim:`` subcircuit symbols.

    Real ``Lib:Name`` lookups delegate to the wrapped table; registered
    ``Sim:<subckt>`` refs resolve to the synthesized symbols. Pass the
    wrapper to ``Circuit`` in place of the base table.
    """

    def __init__(self, base: SymbolTable) -> None:
        self._base = base
        self._sim: dict[str, Symbol] = {}

    def lookup(self, ref: str) -> Symbol:
        """Resolve ``Sim:`` refs from the registry, the rest from the base."""
        if ref in self._sim:
            return self._sim[ref]
        return self._base.lookup(ref)

    def subckt(self, name: str, ports: Sequence[str]) -> type[SubcktInst]:
        """Register an external subcircuit; return its typed part class.

        ``ports`` is the subcircuit's port list in order — the
        X-element's net order. Since X-elements bind nets positionally,
        the port names are capture-side identifiers only (the deck's
        own port naming never leaves it); follow the DSL's lowercase
        keyword convention.
        """
        ref = f"Sim:{name}"
        if ref in self._sim:
            msg = f"sim subcircuit {name!r} is already registered"
            raise DefinitionError(msg)
        duplicates = sorted({port for port in ports if ports.count(port) > 1})
        if duplicates:
            msg = f"sim subcircuit {name!r} has duplicate ports {duplicates}"
            raise DefinitionError(msg)
        self._sim[ref] = Symbol(
            lib="Sim",
            name=name,
            pins=tuple(
                SymbolPin(number=str(index), name=port, type=PinType.PASSIVE)
                for index, port in enumerate(ports, start=1)
            ),
        )
        pin_map = {port: str(index) for index, port in enumerate(ports, start=1)}
        cls = type(name, (SubcktInst,), {"symbol": ref, "pin_map": pin_map})
        cls.__doc__ = f"Instance of the external subcircuit ``{name}``."
        return cls
