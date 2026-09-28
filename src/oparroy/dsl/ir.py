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

Interfaces scale past scalar ports two ways (T7bb): port arrays
(``Circuit.port_array``) are width-fixed vectors bound element-wise,
and bundles (``Circuit.bundle``) group existing nets under member
names — the connector pinout as one connectable unit — bound
member-wise. Both expand to scalar port bindings at instantiation, so
flattening, checks, and emitters see plain nets only.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, overload

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


def _pin_numbers(numbers: str | tuple[str, ...]) -> tuple[str, ...]:
    """Normalize a pin_map value to a tuple of pin numbers."""
    return (numbers,) if isinstance(numbers, str) else numbers


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

    def __init__(  # noqa: PLR0913 — ref/symbol/value/footprint + path/identity
        self,
        ref: str,
        symbol: Symbol,
        value: str | None,
        footprint: str | None,
        *,
        path: tuple[str, ...] = (),
        identity: str | None = None,
    ) -> None:
        self._ref = ref
        self._symbol = symbol
        self.value = value
        self.footprint = footprint
        self._path = path
        self._identity = ref if identity is None else identity
        self._pins = {sp.number: Pin(self, sp) for sp in symbol.pins}

    @property
    def ref(self) -> str:
        """The reference designator, assigned explicitly at capture."""
        return self._ref

    @property
    def identity(self) -> str:
        """The capture name this part is known by, stable across stages.

        Equal to ``ref`` until annotation renames the part to its board
        refdes — the identity keeps the capture name (``WD1/Rs``) so the
        emitted tstamps survive re-annotation and pcbnew keeps matching
        the part by timestamp (DESIGN.md §7).
        """
        return self._identity

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


class PortArray(Sequence[Net]):
    """A port vector of ``width`` port nets (``name[0]``, ``name[1]``, …).

    The array interface — button matrices, LED arrays (T7bb). Captures
    index it like any sequence; ``Circuit.instance`` binds it to a
    sequence of parent nets of equal width and flattening merges
    element-wise, so a width drift raises at capture.
    """

    def __init__(self, name: str, nets: tuple[Net, ...]) -> None:
        self._name = name
        self._nets = nets

    @property
    def name(self) -> str:
        """The array base name; the element nets are ``name[i]``."""
        return self._name

    @property
    def nets(self) -> tuple[Net, ...]:
        """The element nets, in index order."""
        return self._nets

    def __len__(self) -> int:
        return len(self._nets)

    @overload
    def __getitem__(self, index: int) -> Net: ...
    @overload
    def __getitem__(self, index: slice) -> tuple[Net, ...]: ...
    def __getitem__(self, index: int | slice) -> Net | tuple[Net, ...]:
        return self._nets[index]

    def __repr__(self) -> str:
        return f"<PortArray {self._name}[{len(self)}]>"


class Bundle(Mapping[str, Net]):
    """A named group of nets, connectable as one unit (T7bb).

    Members alias existing nets under bundle-local names — the §3
    segment pinout: ``upstream.a`` is a node's RX_A port,
    ``downstream.a`` its TX_A, and the two faces join member-to-member.
    ``Circuit.instance`` binds a bundle port to a same-membered bundle
    or mapping; ``BundleConnector`` maps members to connector pin
    numbers declaratively. Member access works by item
    (``bundle["a"]``) or attribute (``bundle.a``); a member shadowing a
    class attribute (``name``, …) stays reachable by item.
    """

    def __init__(self, name: str, members: dict[str, Net]) -> None:
        self._name = name
        self._members = dict(members)

    @property
    def name(self) -> str:
        """The bundle name — the binding keyword at instantiation."""
        return self._name

    def __getitem__(self, member: str) -> Net:
        try:
            return self._members[member]
        except KeyError:
            raise KeyError(f"bundle {self._name!r} has no member {member!r}") from None

    def __iter__(self) -> Iterator[str]:
        return iter(self._members)

    def __len__(self) -> int:
        return len(self._members)

    def __getattr__(self, member: str) -> Net:
        try:
            return self.__dict__["_members"][member]
        except KeyError:
            raise AttributeError(
                f"bundle {self._name!r} has no member {member!r}"
            ) from None

    def __repr__(self) -> str:
        return f"<Bundle {self._name}: {' '.join(self._members)}>"


def _expand_connections(
    instance_name: str,
    child: Circuit,
    connections: dict[str, Net | str | Sequence[Net | str] | Mapping[str, Net | str]],
) -> dict[str, list[tuple[Net | str, str]]]:
    """Expand array/bundle bindings into per-port connections.

    Every expanded entry carries its source label for conflict reports;
    a port reached twice (the §3 power nets, aliased into both
    segment-face bundles) keeps both entries, and ``Circuit.instance``
    resolves them to one parent net.
    """
    expanded: dict[str, list[tuple[Net | str, str]]] = {}
    for key, value in connections.items():
        if key in child._arrays:  # noqa: SLF001 — same module
            entries = _expand_array(instance_name, child._arrays[key], value)  # noqa: SLF001
        elif key in child._bundles:  # noqa: SLF001 — same module
            entries = _expand_bundle(instance_name, child._bundles[key], value)  # noqa: SLF001
        elif isinstance(value, Net | str):
            entries = {key: (value, key)}
        else:
            msg = (
                f"instance {instance_name!r}: port {key!r} bound to {value!r}, "
                "not a net"
            )
            raise DefinitionError(msg)
        for port_name, entry in entries.items():
            expanded.setdefault(port_name, []).append(entry)
    return expanded


def _expand_array(
    instance_name: str,
    array: PortArray,
    value: Net | str | Sequence[Net | str] | Mapping[str, Net | str],
) -> dict[str, tuple[Net | str, str]]:
    """Expand an array binding into per-element ``name[i]`` connections."""
    width = len(array)
    if isinstance(value, str) or not isinstance(value, Sequence):
        msg = (
            f"instance {instance_name!r}: port {array.name!r} is an array of "
            f"width {width}; bind a sequence of {width} nets"
        )
        raise DefinitionError(msg)
    elements = list(value)
    if len(elements) != width:
        msg = (
            f"instance {instance_name!r}: port array {array.name!r} has "
            f"width {width}, bound to {len(elements)} nets"
        )
        raise DefinitionError(msg)
    expanded: dict[str, tuple[Net | str, str]] = {}
    for index, element in enumerate(elements):
        if not isinstance(element, Net | str):
            msg = (
                f"instance {instance_name!r}: port array {array.name!r} "
                f"element {index} bound to {element!r}, not a net"
            )
            raise DefinitionError(msg)
        # The source label is the array binding keyword, not the
        # element name — a conflict with an individual element binding
        # must name two distinguishable sources.
        expanded[f"{array.name}[{index}]"] = (element, array.name)
    return expanded


def _expand_bundle(
    instance_name: str,
    bundle: Bundle,
    value: Net | str | Sequence[Net | str] | Mapping[str, Net | str],
) -> dict[str, tuple[Net | str, str]]:
    """Expand a bundle binding into per-member port connections."""
    members = list(bundle)
    if not isinstance(value, Mapping):
        msg = (
            f"instance {instance_name!r}: port {bundle.name!r} is a bundle "
            f"with members {members}; bind a bundle or a mapping"
        )
        raise DefinitionError(msg)
    supplied = dict(value)
    unknown = sorted(set(supplied) - set(members), key=natural_key)
    missing = sorted(set(members) - set(supplied), key=natural_key)
    if unknown or missing:
        problems = []
        if missing:
            problems.append(f"missing {missing}")
        if unknown:
            problems.append(f"unknown {unknown}")
        msg = (
            f"instance {instance_name!r}: bundle {bundle.name!r} binding has "
            f"{' and '.join(problems)} (members: {members})"
        )
        raise DefinitionError(msg)
    expanded = {}
    for member in members:
        net = supplied[member]
        if not isinstance(net, Net | str):
            msg = (
                f"instance {instance_name!r}: bundle {bundle.name!r} member "
                f"{member!r} bound to {net!r}, not a net"
            )
            raise DefinitionError(msg)
        expanded[bundle[member].name] = (net, f"{bundle.name}.{member}")
    return expanded


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
        self._arrays: dict[str, PortArray] = {}
        self._bundles: dict[str, Bundle] = {}
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
    def port_arrays(self) -> dict[str, PortArray]:
        """Port arrays by name — the vector interface (insertion order)."""
        return dict(self._arrays)

    @property
    def bundles(self) -> dict[str, Bundle]:
        """Bundles by name — the grouped interface (insertion order)."""
        return dict(self._bundles)

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
        symbol_pins = {pin.number for pin in resolved.pins}
        targets = [
            number
            for mapped in spec.pin_map.values()
            for number in _pin_numbers(mapped)
        ]
        unknown = sorted(set(targets) - symbol_pins, key=natural_key)
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
            for number in _pin_numbers(spec.pin_map[kw]):
                net._attach(placed.pin(number))  # noqa: SLF001 — same module
        return placed

    def _place(  # noqa: PLR0913 — placement carries ref/symbol/value/footprint + path/identity
        self,
        ref: str,
        resolved: Symbol,
        value: str | None,
        footprint: str | None,
        *,
        path: tuple[str, ...] = (),
        identity: str | None = None,
    ) -> Part:
        if ref in self._parts:
            msg = f"duplicate part reference {ref!r}"
            raise DefinitionError(msg)
        placed = Part(ref, resolved, value, footprint, path=path, identity=identity)
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

    def port_array(self, name: str, width: int) -> PortArray:
        """Declare a port array: ``width`` port nets ``name[0]`` … ``name[width-1]``.

        The vector interface (button matrices, LED arrays). Width is
        fixed at declaration — the parent binds exactly ``width`` nets
        (``Circuit.instance``) and flattening merges element-wise, so a
        width drift raises at capture. Element nets also bind
        individually by name (``led[0]``=…) when a parent wires them
        one by one.
        """
        _reject_separator("port array name", name)
        if "[" in name or "]" in name:
            msg = f"port array name {name!r} must not contain '[' or ']'"
            raise DefinitionError(msg)
        if width < 1:
            msg = f"port array {name!r} needs a width of at least 1"
            raise DefinitionError(msg)
        self._check_group_name_free("port array", name)
        element_names = [f"{name}[{i}]" for i in range(width)]
        collisions = [n for n in element_names if n in self._nets]
        if collisions:
            msg = f"port array {name!r} collides with existing nets {collisions}"
            raise DefinitionError(msg)
        array = PortArray(
            name,
            tuple(self._add_net(n, is_port=True) for n in element_names),
        )
        self._arrays[name] = array
        return array

    def bundle(self, name: str, /, **members: Net | str) -> Bundle:
        """Group existing nets under member names, connectable as one unit.

        Members alias nets of this circuit — ports for a subcircuit
        interface (the §3 segment pinout), plain nets for a board-level
        link. ``Circuit.instance`` binds a bundle to a same-membered
        ``Bundle`` or a mapping; ``parts.BundleConnector`` maps members
        to connector pin numbers declaratively. One net may not alias
        two members of the same bundle (a member would bind nothing —
        multi-pin members are the connector block's tuple pin_map).
        """
        _reject_separator("bundle name", name)
        self._check_group_name_free("bundle", name)
        if not members:
            msg = f"bundle {name!r} needs at least one member"
            raise DefinitionError(msg)
        resolved: dict[str, Net] = {}
        for member, net in members.items():
            if not member:
                msg = f"bundle {name!r} has an empty member name"
                raise DefinitionError(msg)
            _reject_separator(f"bundle {name!r} member", member)
            resolved[member] = self._resolve_net(net)
        aliased: dict[Net, str] = {}
        for member, net in resolved.items():
            if net in aliased:
                msg = (
                    f"bundle {name!r}: members {aliased[net]!r} and "
                    f"{member!r} alias the same net {net.name!r}"
                )
                raise DefinitionError(msg)
            aliased[net] = member
        created = Bundle(name, resolved)
        self._bundles[name] = created
        return created

    def _check_group_name_free(self, kind: str, name: str) -> None:
        if name in self._arrays or name in self._bundles:
            msg = f"duplicate {kind} name {name!r}"
            raise DefinitionError(msg)
        if name in self._nets:
            msg = f"{kind} name {name!r} collides with a net of the same name"
            raise DefinitionError(msg)

    def _add_net(self, name: str, *, is_port: bool) -> Net:
        if name in self._nets:
            msg = f"duplicate net name {name!r}"
            raise DefinitionError(msg)
        if name in self._arrays or name in self._bundles:
            msg = f"net name {name!r} collides with a port array or bundle"
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
        **connections: Net | str | Sequence[Net | str] | Mapping[str, Net | str],
    ) -> Instance:
        """Instantiate a subcircuit: capture it, then bind its ports.

        ``subcircuit`` is a capture — a ``Subcircuit`` or any callable
        taking the fresh child circuit — run under ``name``. Every port
        the capture declares must be bound by keyword to a parent net
        (``board.instance("WD1", Watchdog(), ka=ka_net, …)``); unknown
        or unconnected ports raise, so an interface drift breaks the
        capture that introduced it, not a later stage. A port array
        binds to a sequence of equal width, element-wise; a bundle
        binds to a same-membered ``Bundle`` or mapping, member-wise.
        A port reached through two groups (the §3 power nets, aliased
        into both segment-face bundles) must resolve to one parent net
        — conflicting bindings raise.

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
        expanded = _expand_connections(name, child, connections)
        ports = child.ports
        unknown = sorted(set(expanded) - set(ports), key=natural_key)
        if unknown:
            msg = (
                f"instance {name!r}: the subcircuit has no ports {unknown} "
                f"(declared: {sorted(ports, key=natural_key)})"
            )
            raise DefinitionError(msg)
        missing = sorted(set(ports) - set(expanded), key=natural_key)
        if missing:
            msg = f"instance {name!r}: ports {missing} left unconnected"
            raise DefinitionError(msg)
        resolved: dict[str, Net] = {}
        sources: dict[str, str] = {}
        for port_name, bindings in expanded.items():
            for net, source in bindings:
                target = self._resolve_net(net)
                if port_name in resolved and resolved[port_name] is not target:
                    msg = (
                        f"instance {name!r}: port {port_name!r} bound by both "
                        f"{sources[port_name]!r} and {source!r} to different nets"
                    )
                    raise DefinitionError(msg)
                resolved[port_name] = target
                sources[port_name] = source
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

    def renamed(self, refs: Mapping[str, str]) -> Circuit:
        """Apply annotation: a flat copy with parts renamed to their refdes.

        The annotation stage (``oparroy.dsl.annotate``) maps capture
        names to placed refdes; this pass materializes the renamed IR
        the netlist emitter consumes. Each part keeps its capture name
        as ``Part.identity``, so the emitted tstamps stay stable across
        re-annotation and pcbnew keeps matching parts by timestamp.
        Parts missing from ``refs`` keep their current ref (power
        symbols are never annotated). A rename that collides raises like
        any duplicate reference.
        """
        if self._instances:
            return self.flatten().renamed(refs)
        renamed = Circuit(self._name, self._symbols)
        nets: dict[Net, Net] = {}
        for name, net in self._nets.items():
            nets[net] = renamed._add_net(name, is_port=net.is_port)
        for part in self._parts.values():
            placed = renamed._place(
                refs.get(part.identity, refs.get(part.ref, part.ref)),
                part.symbol,
                part.value,
                part.footprint,
                path=part.path,
                identity=part.identity,
            )
            for pin in part.pins:
                if pin.net is not None:
                    nets[pin.net]._attach(placed.pin(pin.number))  # noqa: SLF001
        return renamed

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
        for name, array in self._arrays.items():
            lines.append(f"port array {name}[{len(array)}]")
        for name, bundle in self._bundles.items():
            members = " ".join(f"{member}={bundle[member].name}" for member in bundle)
            lines.append(f"bundle {name}: {members}")
        for name in self._instances:
            lines.append(f"instance {name}:")
            child_dump = self._instances[name].circuit.dump()
            lines.extend(f"  {line}" for line in child_dump.splitlines())
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.dump()
