"""Core IR for the oparroy design-capture DSL (DESIGN.md §7).

The IR is a plain data structure — parts, pins, nets, one circuit —
built through the capture API (``Circuit.part`` / ``Circuit.net`` /
``Circuit.connect``: plain function calls in the HDL-instantiation
flavor, references are explicit instance names), validated by
``oparroy.dsl.check``, and consumed by the emitters. Structural
invariants (unique reference names, a pin on at most one net) raise at
construction; everything electrical is the validation pass's job.

Hierarchy is capture-time structure (§7): a circuit instantiates
subcircuits (``Circuit.instance``) with declared port interfaces
(``Circuit.port``), and ``Circuit.flatten`` is the pass that reduces
the hierarchy to the flat IR checks and emitters consume — instance
names prefix part references and internal nets, so identities stay
stable across source edits and findings report hierarchical paths.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable

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


def _reject_separator(kind: str, name: str) -> None:
    """Reject '/', the hierarchy path separator, in a captured name.

    Instance names, part references, and net names all become path
    elements under flattening (``WD1/Rs``, ``WD1/x``), so none may
    carry the separator — a '/' smuggled in at capture would collide
    with, or masquerade as, a flattened path.
    """
    if "/" in name:
        msg = f"{kind} {name!r} must not contain '/', the hierarchy path separator"
        raise DefinitionError(msg)


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
        *,
        path: tuple[str, ...] = (),
    ) -> None:
        self._ref = ref
        self._symbol = symbol
        self.value = value
        self.footprint = footprint
        self._path = path
        self._pins = {sp.number: Pin(self, sp) for sp in symbol.pins}

    @property
    def ref(self) -> str:
        """The reference designator, assigned explicitly at capture."""
        return self._ref

    @property
    def path(self) -> tuple[str, ...]:
        """The instance path this part was flattened through.

        Empty for a directly placed part; set by ``Circuit.flatten`` on
        the flat copy — the hierarchy metadata (sheetpath) the KiCad
        emitter and the layout checker key channelization on.
        """
        return self._path

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

    def __init__(self, name: str, *, is_port: bool = False) -> None:
        self._name = name
        self._is_port = is_port
        self._pins: list[Pin] = []

    @property
    def name(self) -> str:
        """The net name as it appears in emitted netlists."""
        return self._name

    @property
    def is_port(self) -> bool:
        """True for ports — external-facing nets (``Circuit.port``).

        A port is the subcircuit interface: ``Circuit.instance`` binds
        every port to a parent net, and flattening merges the two.
        """
        return self._is_port

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


class Instance:
    """One placed subcircuit: a captured child with its ports bound.

    Built by ``Circuit.instance``; carries the child circuit and the
    port bindings (port name → parent net) that ``Circuit.flatten``
    consumes.
    """

    def __init__(
        self,
        name: str,
        circuit: Circuit,
        connections: dict[str, Net],
    ) -> None:
        self._name = name
        self._circuit = circuit
        self._connections = dict(connections)

    @property
    def name(self) -> str:
        """The instance name — the hierarchy path element."""
        return self._name

    @property
    def circuit(self) -> Circuit:
        """The captured child circuit."""
        return self._circuit

    @property
    def connections(self) -> dict[str, Net]:
        """Port bindings: port name → the parent net it sits on."""
        return dict(self._connections)

    def __repr__(self) -> str:
        return f"<Instance {self._name} of {self._circuit.name!r}>"


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
        self._instances: dict[str, Instance] = {}

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

    @property
    def ports(self) -> dict[str, Net]:
        """Port nets by name — the subcircuit interface (insertion order)."""
        return {name: net for name, net in self._nets.items() if net.is_port}

    @property
    def instances(self) -> dict[str, Instance]:
        """All subcircuit instances by name (insertion order)."""
        return dict(self._instances)

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
        _reject_separator("part reference", ref)
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
        *,
        path: tuple[str, ...] = (),
    ) -> Part:
        if ref in self._parts:
            msg = f"duplicate part reference {ref!r}"
            raise DefinitionError(msg)
        placed = Part(ref, resolved, value, footprint, path=path)
        self._parts[ref] = placed
        return placed

    def net(self, name: str) -> Net:
        """Declare a net by name; duplicate names are an error."""
        _reject_separator("net name", name)
        return self._add_net(name, is_port=False)

    def port(self, name: str) -> Net:
        """Declare a port: an external-facing net, the subcircuit interface.

        A port wires like any net inside the subcircuit; a parent
        instantiating it binds every port (``Circuit.instance``), and
        flattening merges port and bound net. Port nets are exempt from
        the dangling-net checks — reaching outside is their job.
        """
        _reject_separator("net name", name)
        return self._add_net(name, is_port=True)

    def _add_net(self, name: str, *, is_port: bool) -> Net:
        if name in self._nets:
            msg = f"duplicate net name {name!r}"
            raise DefinitionError(msg)
        created = Net(name, is_port=is_port)
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

    def instance(
        self,
        name: str,
        subcircuit: Callable[[Circuit], None],
        /,
        **connections: Net | str,
    ) -> Instance:
        """Instantiate a subcircuit: capture it, then bind its ports.

        ``subcircuit`` is a capture — a ``Subcircuit`` or any callable
        taking the fresh child circuit — run under ``name``. Every port
        the capture declares must be bound by keyword to a parent net
        (``board.instance("WD1", Watchdog(), ka=ka_net, …)``); unknown
        or unconnected ports raise, so an interface drift breaks the
        capture that introduced it, not a later stage.

        The instance is capture-time structure only — nothing is
        copied into this circuit until ``flatten`` runs.
        """
        if not name:
            msg = "instance name must not be empty"
            raise DefinitionError(msg)
        _reject_separator("instance name", name)
        if name in self._instances:
            msg = f"duplicate instance name {name!r}"
            raise DefinitionError(msg)
        child = Circuit(name, self._symbols)
        subcircuit(child)
        ports = child.ports
        unknown = sorted(set(connections) - set(ports), key=natural_key)
        if unknown:
            msg = (
                f"instance {name!r}: the subcircuit has no ports {unknown} "
                f"(declared: {sorted(ports, key=natural_key)})"
            )
            raise DefinitionError(msg)
        missing = sorted(set(ports) - set(connections), key=natural_key)
        if missing:
            msg = f"instance {name!r}: ports {missing} left unconnected"
            raise DefinitionError(msg)
        resolved: dict[str, Net] = {}
        for port_name, net in connections.items():
            if not isinstance(net, Net | str):
                msg = (
                    f"instance {name!r}: port {port_name!r} bound to {net!r}, not a net"
                )
                raise DefinitionError(msg)
            resolved[port_name] = self._resolve_net(net)
        placed = Instance(name, child, resolved)
        self._instances[name] = placed
        return placed

    def flatten(self) -> Circuit:
        """Reduce the instance hierarchy to a new flat circuit.

        Flattening is a pass (§7): the hierarchical capture stays the
        source, this produces the flat IR checks and emitters consume.
        Instance names prefix part references and internal nets
        (``WD1/Rs``, ``WD1/x``) — explicit names at every level keep
        identities stable across source edits — while each port net
        merges into the net its instance bound. Ports left unbound at
        the top level keep their port flag, so the dangling-net
        exemption survives the pass. The flat parts carry their
        instance path as hierarchy metadata (``Part.path``).
        """
        flat = Circuit(self._name, self._symbols)
        self._flatten_into(flat, (), {})
        return flat

    def _flatten_into(
        self,
        flat: Circuit,
        path: tuple[str, ...],
        bindings: dict[str, Net],
    ) -> None:
        prefix = "".join(f"{level}/" for level in path)
        nets: dict[Net, Net] = {}
        for name, net in self._nets.items():
            if net.is_port and name in bindings:
                nets[net] = bindings[name]
            else:
                # Prefixed names carry '/' — bypass the capture-time
                # separator check (it guards captured names only).
                nets[net] = flat._add_net(f"{prefix}{name}", is_port=net.is_port)
        for part in self._parts.values():
            placed = flat._place(
                f"{prefix}{part.ref}",
                part.symbol,
                part.value,
                part.footprint,
                path=path,
            )
            for pin in part.pins:
                if pin.net is not None:
                    nets[pin.net]._attach(placed.pin(pin.number))  # noqa: SLF001
        for inst in self._instances.values():
            child_bindings = {
                port_name: nets[net] for port_name, net in inst.connections.items()
            }
            inst.circuit._flatten_into(flat, (*path, inst.name), child_bindings)  # noqa: SLF001

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
            port = " [port]" if self._nets[name].is_port else ""
            lines.append(f"  {name}{port}: {members}")
        for name in self._instances:
            lines.append(f"instance {name}:")
            child_dump = self._instances[name].circuit.dump()
            lines.extend(f"  {line}" for line in child_dump.splitlines())
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.dump()
