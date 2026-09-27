"""Core IR for the oparroy design-capture DSL (DESIGN.md §7).

The IR is a plain data structure — parts, pins, nets, one circuit —
built through the capture API (``Circuit.part`` / ``Circuit.net`` /
``Circuit.connect``: plain function calls in the HDL-instantiation
flavor, references are explicit instance names), validated by
``oparroy.dsl.check``, and consumed by the emitters. Structural
invariants (unique reference names, a pin on at most one net) raise at
construction; everything electrical is the validation pass's job.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from oparroy.dsl.parts import TypedPart

_NAT_SPLIT = re.compile(r"(\d+)")


def natural_key(text: str) -> tuple[tuple[str | int, ...], str]:
    """Sort key ordering embedded numbers numerically ("R2" < "R10").

    Keys equal after lowercasing and digit-splitting ("R1" vs "r1")
    fall back to the original string, so ordering never depends on
    insertion order.

    >>> natural_key("R10") > natural_key("R9")
    True
    """
    chunks = tuple(
        int(chunk) if chunk.isascii() and chunk.isdigit() else chunk
        for chunk in _NAT_SPLIT.split(text.lower())
    )
    return (chunks, text)


class PinType(StrEnum):
    """KiCad electrical pin types, valued as spelled in .kicad_sym files."""

    INPUT = "input"
    OUTPUT = "output"
    BIDIRECTIONAL = "bidirectional"
    TRI_STATE = "tri_state"
    PASSIVE = "passive"
    FREE = "free"
    UNSPECIFIED = "unspecified"
    POWER_IN = "power_in"
    POWER_OUT = "power_out"
    OPEN_COLLECTOR = "open_collector"
    OPEN_EMITTER = "open_emitter"
    NO_CONNECT = "no_connect"


class DefinitionError(Exception):
    """A structural IR invariant was violated during capture."""


class UnknownSymbolError(DefinitionError):
    """A part referenced a symbol the symbol table does not know."""


@dataclass(frozen=True)
class SymbolPin:
    """One pin of a library symbol: number, display name, electrical type."""

    number: str
    name: str
    type: PinType


@dataclass(frozen=True)
class Symbol:
    """A resolved library symbol: the pin-level contract of a part kind."""

    lib: str
    name: str
    pins: tuple[SymbolPin, ...]
    footprint_filters: tuple[str, ...] = ()
    pin_conflicts: tuple[str, ...] = ()

    @property
    def ref(self) -> str:
        """The canonical ``Lib:Name`` reference."""
        return f"{self.lib}:{self.name}"

    @property
    def is_power(self) -> bool:
        """True for power-library symbols (``power:+3V3``).

        Power symbols are schematic-only net markers: no footprint,
        excluded from the board netlist.
        """
        return self.lib == "power"

    def pin(self, number: str) -> SymbolPin | None:
        """Look up a pin by number, or None if the symbol has no such pin."""
        return next((p for p in self.pins if p.number == number), None)


class SymbolTable(Protocol):
    """Source of library symbols — kicadlib for real use, stubs in tests."""

    def lookup(self, ref: str) -> Symbol:
        """Resolve ``Lib:Name`` to a Symbol, raising UnknownSymbolError."""
        ...


class Pin:
    """One pin of one placed part; carries its net membership."""

    def __init__(self, part: Part, symbol_pin: SymbolPin) -> None:
        self._part = part
        self._symbol_pin = symbol_pin
        self._net: Net | None = None

    @property
    def part(self) -> Part:
        """The part this pin belongs to."""
        return self._part

    @property
    def net(self) -> Net | None:
        """The net this pin sits on, or None; set only by circuit wiring."""
        return self._net

    @property
    def number(self) -> str:
        """The pin number as declared by the symbol ("1", "A3", ...)."""
        return self._symbol_pin.number

    @property
    def name(self) -> str:
        """The pin name as declared by the symbol ("" when unnamed)."""
        return self._symbol_pin.name

    @property
    def type(self) -> PinType:
        """The electrical type declared by the symbol."""
        return self._symbol_pin.type

    def __repr__(self) -> str:
        return f"<Pin {self._part.ref}.{self.number}>"


class Part:
    """One placed component: an explicit reference bound to a symbol."""

    def __init__(
        self,
        ref: str,
        symbol: Symbol,
        value: str | None,
        footprint: str | None,
    ) -> None:
        self._ref = ref
        self._symbol = symbol
        self.value = value
        self.footprint = footprint
        self._pins = {sp.number: Pin(self, sp) for sp in symbol.pins}

    @property
    def ref(self) -> str:
        """The reference designator, assigned explicitly at capture."""
        return self._ref

    @property
    def symbol(self) -> Symbol:
        """The library symbol this part instantiates."""
        return self._symbol

    @property
    def pins(self) -> tuple[Pin, ...]:
        """All pins, ordered by pin number."""
        return tuple(self._pins[n] for n in sorted(self._pins, key=natural_key))

    def pin(self, number: int | str) -> Pin:
        """Look up a pin by number; raises DefinitionError if absent."""
        key = str(number)
        try:
            return self._pins[key]
        except KeyError:
            msg = f"{self._ref} ({self._symbol.ref}) has no pin {key}"
            raise DefinitionError(msg) from None

    def __getitem__(self, number: int | str) -> Pin:
        return self.pin(number)

    def __repr__(self) -> str:
        return f"<Part {self._ref} {self._symbol.ref}>"


class Net:
    """A named equipotential: the set of pins joined together."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._pins: list[Pin] = []

    @property
    def name(self) -> str:
        """The net name as it appears in emitted netlists."""
        return self._name

    @property
    def pins(self) -> tuple[Pin, ...]:
        """Member pins, ordered by part reference then pin number."""
        return tuple(
            sorted(
                self._pins,
                key=lambda p: (natural_key(p.part.ref), natural_key(p.number)),
            )
        )

    def _attach(self, pin: Pin) -> None:
        """Add a pin to this net; called by ``Circuit.connect``."""
        if pin.net is not None:
            msg = f"{pin.part.ref}.{pin.number} is already on net {pin.net.name!r}"
            raise DefinitionError(msg)
        pin._net = self  # noqa: SLF001 — same module; Pin.net is module-private
        self._pins.append(pin)

    def __repr__(self) -> str:
        return f"<Net {self._name} ({len(self._pins)} pins)>"


class Circuit:
    """One captured circuit: parts and nets, the unit of check and emit."""

    def __init__(self, name: str, symbols: SymbolTable) -> None:
        if not name:
            msg = "circuit name must not be empty"
            raise DefinitionError(msg)
        self._name = name
        self._symbols = symbols
        self._parts: dict[str, Part] = {}
        self._nets: dict[str, Net] = {}

    @property
    def name(self) -> str:
        """The circuit name, used in emitted design headers."""
        return self._name

    @property
    def parts(self) -> dict[str, Part]:
        """All parts by reference (insertion order)."""
        return dict(self._parts)

    @property
    def nets(self) -> dict[str, Net]:
        """All nets by name (insertion order)."""
        return dict(self._nets)

    def part(
        self,
        ref: str,
        spec: TypedPart | None = None,
        *,
        symbol: str | None = None,
        value: str | None = None,
        footprint: str | None = None,
    ) -> Part:
        """Place a part, from a typed spec or a ``Lib:Name`` symbol.

        A typed ``spec`` (``oparroy.dsl.parts``) carries its own
        symbol, value, footprint default, and wiring: placement
        connects its pins in the same step, and every net is resolved
        before anything is placed, so a rejected call changes nothing.
        A ``symbol`` string places an unwired part; wiring is
        ``connect``'s job. ``footprint`` overrides the spec's default.
        """
        if isinstance(spec, str):
            msg = f"symbol {spec!r} must be passed as symbol={spec!r}"
            raise DefinitionError(msg)
        if spec is not None:
            if symbol is not None:
                msg = "pass a typed part or symbol=, not both"
                raise DefinitionError(msg)
            if value is not None:
                msg = "value goes to the typed part class, not part()"
                raise DefinitionError(msg)
            return self._place_typed(ref, spec, footprint)
        if symbol is None:
            msg = "part() needs a typed part or symbol="
            raise DefinitionError(msg)
        return self._place(ref, self._symbols.lookup(symbol), value, footprint)

    def _place_typed(
        self,
        ref: str,
        spec: TypedPart,
        footprint: str | None,
    ) -> Part:
        # Lazy import: parts.py imports this module at runtime.
        from oparroy.dsl.parts import TypedPart as _TypedPart  # noqa: PLC0415

        if not isinstance(spec, _TypedPart):
            msg = f"expected a typed part (oparroy.dsl.parts), got {spec!r}"
            raise DefinitionError(msg)
        resolved = self._symbols.lookup(spec.symbol)
        numbers = {pin.number for pin in resolved.pins}
        targets = list(spec.pin_map.values())
        unknown = sorted(set(targets) - numbers, key=natural_key)
        if unknown:
            msg = (
                f"{type(spec).__name__} pin_map targets pins {unknown}, "
                f"which {spec.symbol} does not have"
            )
            raise DefinitionError(msg)
        if len(set(targets)) != len(targets):
            msg = (
                f"{type(spec).__name__} pin_map maps several names "
                "to the same pin number"
            )
            raise DefinitionError(msg)
        wiring = {kw: self._resolve_net(net) for kw, net in spec.nets.items()}
        placed = self._place(
            ref,
            resolved,
            spec.value,
            footprint if footprint is not None else spec.footprint,
        )
        for kw, net in wiring.items():
            net._attach(placed.pin(spec.pin_map[kw]))  # noqa: SLF001 — same module
        return placed

    def _place(
        self,
        ref: str,
        resolved: Symbol,
        value: str | None,
        footprint: str | None,
    ) -> Part:
        if ref in self._parts:
            msg = f"duplicate part reference {ref!r}"
            raise DefinitionError(msg)
        placed = Part(ref, resolved, value, footprint)
        self._parts[ref] = placed
        return placed

    def net(self, name: str) -> Net:
        """Declare a net by name; duplicate names are an error."""
        if name in self._nets:
            msg = f"duplicate net name {name!r}"
            raise DefinitionError(msg)
        created = Net(name)
        self._nets[name] = created
        return created

    def connect(self, net: Net | str, *pins: Pin) -> None:
        """Join pins onto a net; a pin may sit on exactly one net.

        Validates every pin (circuit membership, not already connected)
        before attaching any, so a rejected call changes nothing.
        """
        resolved = self._resolve_net(net)
        seen: set[Pin] = set()
        for pin in pins:
            if pin.part is not self._parts.get(pin.part.ref):
                msg = (
                    f"{pin.part.ref}.{pin.number} does not belong "
                    f"to circuit {self._name!r}"
                )
                raise DefinitionError(msg)
            if pin in seen:
                msg = f"{pin.part.ref}.{pin.number} listed twice in connect"
                raise DefinitionError(msg)
            seen.add(pin)
            if pin.net is not None:
                msg = f"{pin.part.ref}.{pin.number} is already on net {pin.net.name!r}"
                raise DefinitionError(msg)
        for pin in pins:
            resolved._attach(pin)  # noqa: SLF001 — same module

    def _resolve_net(self, net: Net | str) -> Net:
        if isinstance(net, Net):
            if self._nets.get(net.name) is not net:
                msg = f"net {net.name!r} does not belong to circuit {self._name!r}"
                raise DefinitionError(msg)
            return net
        try:
            return self._nets[net]
        except KeyError:
            msg = f"no net named {net!r} in circuit {self._name!r}"
            raise DefinitionError(msg) from None

    def dump(self) -> str:
        """Pretty-print the IR for humans; not a round-trip format."""
        header = (
            f"circuit {self._name}: {len(self._parts)} parts, {len(self._nets)} nets"
        )
        lines = [header, "parts:"]
        for ref in sorted(self._parts, key=natural_key):
            part = self._parts[ref]
            value = part.value if part.value is not None else "?"
            footprint = f" [{part.footprint}]" if part.footprint is not None else ""
            lines.append(f"  {ref} {part.symbol.ref} {value!r}{footprint}")
            for pin in part.pins:
                target = pin.net.name if pin.net is not None else "—"
                name = f" {pin.name!r}" if pin.name else ""
                lines.append(f"    {pin.number}{name} ({pin.type}) -> {target}")
        lines.append("nets:")
        for name in sorted(self._nets, key=natural_key):
            members = " ".join(
                f"{p.part.ref}.{p.number}" for p in self._nets[name].pins
            )
            lines.append(f"  {name}: {members}")
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.dump()
