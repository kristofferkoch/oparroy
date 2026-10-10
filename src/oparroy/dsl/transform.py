"""Instrumentation transforms: the CI board as data over the plain capture.

The CI board is the node design plus injected controllability and
observability (DESIGN.md §6: fault-injection muxes, supervisor-override
muxes, sense taps) — and that makes it *dangerously different* from the
plain node it is meant to exercise. Hand-maintaining
a second capture guarantees drift; this pass captures the
instrumentation as an **explicit transformation** of the uninstrumented
design, settled in ``docs/instrumentation-equivalence.md``
and grown to four kinds in ``docs/instrumented-ci.md`` §7:

- ``InsertSeries`` — cut a net into ``#a``/``#b`` sides and bridge them
  through a part (the fault-injection break switches, the keep-alive
  cut, the per-node power switch);
- ``AddShunt`` — hang a switched branch between a net and a rail
  without cutting the net (the short legs, the watchdog defeat);
- ``AddTap`` — export a net to the board as a high-impedance sense
  point, no cut (the boundary node's PIO taps);
- ``Substitute`` — cut a net and re-drive the load side through a part
  whose alternate source is an escaped board net (the §6 human-I/O
  overrides).

Transforms are data (typed records), never code patches: the CI board's
capture is the plain node capture plus a declared transform list, so
the two can never drift, and the plain capture never carries CI-only
parts — the base board stays fab-able while the CI board is a strict
superset produced mechanically. Every part and net a transform creates
is tagged with :class:`Provenance` — the input of the reset-state
equivalence proof (:mod:`oparroy.dsl.equivalence`), no name-matching
heuristics.

Application is hierarchical, per-tile (memo Q1):
``apply_transforms`` runs on the hierarchical board between capture and
check; a ``PerTile`` declaration keys on the subcircuit identity and
instruments every instance of it, ``PerInstance`` declarations address
one instance by path (the boundary tile, the input tiles) on top. Each
matched instance's child is flattened in place
(``Instance.flatten_hierarchy``) so transform targets address pins
across the tile's own hierarchy (``PHY1/Rat.b``); the parent's flatten
afterwards prefixes everything as usual, and provenance survives it.

Control and observe points escape the tile as new ports: the transform
creates the port in the tile and binds it to a fresh board net
(``T0/BRK_A``), returned in the handles for the capture to wire to the
scan plane. Part wiring inside a transform record uses placeholder net
names: ``@a``/``@b`` are the two sides of a cut, ``@control``/
``@source`` the escaped ports, ``@net`` an ``AddShunt``'s base net, and
any other ``@name`` a fresh net shared by that name across the
transform's parts. Plain names resolve to tile nets (the supply rails).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING

from oparroy.dsl.ir import (
    Circuit,
    DefinitionError,
    Instance,
    Net,
    Pin,
    Provenance,
    TileNet,
)
from oparroy.dsl.parts import MultiUnitPart, TypedPart

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

    from oparroy.dsl.subcircuit import Subcircuit

type Transform = InsertSeries | AddShunt | AddTap | Substitute
type Scope = PerTile | PerInstance
type Handles = dict[TileNet, Net]


@dataclass(frozen=True)
class TransformPart:
    """One part a transform places: a reference and a typed part spec.

    The reference may carry a '/' group prefix (``FI1/SWAB``) — the
    engine places grouped parts with hierarchical references, like
    flattening's own prefixed copies. The spec wires placeholder nets
    (the module docstring's ``@``-names), resolved at application.
    """

    ref: str
    spec: TypedPart

    def __post_init__(self) -> None:
        if not self.ref:
            msg = "a transform part needs a reference"
            raise DefinitionError(msg)
        if self.ref.startswith("/") or self.ref.endswith("/") or "//" in self.ref:
            msg = f"transform part reference {self.ref!r} is malformed"
            raise DefinitionError(msg)


@dataclass(frozen=True)
class InsertSeries:
    """Cut a net into two sides and bridge them through a series part.

    ``pins`` names the base-net pins of the detached side (the tile
    side, ``#a``); the remaining pins stay on the interface side
    (``#b``). A port base net keeps its name and flag as the ``#b``
    side — the parent binding holds; an internal base net is replaced
    by fresh ``net#a``/``net#b`` nets. The part wires ``@a``/``@b`` for
    the two sides; ``control`` names an escaped control port for the
    ``@control`` placeholder; ``name`` overrides the detached side's
    net name (the rail-split ``3V3`` → ``3V3N``). ``extra`` places
    auxiliary parts of the same transform (the keep-alive cut's
    pull-down on the watchdog-side stub).
    """

    label: str
    net: str
    pins: tuple[str, ...]
    part: TransformPart
    control: str | None = None
    name: str | None = None
    extra: tuple[TransformPart, ...] = ()


@dataclass(frozen=True)
class AddShunt:
    """Hang a switched branch between a net and a rail — no cut.

    The short legs and the watchdog defeat: a branch that is open in
    reset state, so the memo's three kinds could not express it; its
    reset-state reduction is "branch absent". The part wires ``@net``
    for the base net; ``rail`` names the rail the branch reaches (proof
    data — the specs wire it by name); ``control`` and ``extra`` are
    ``InsertSeries``'s.
    """

    label: str
    net: str
    rail: str
    part: TransformPart
    control: str | None = None
    extra: tuple[TransformPart, ...] = ()


@dataclass(frozen=True)
class AddTap:
    """Export a net to the board as a high-impedance sense point — no cut.

    The boundary node's PIO taps (``docs/instrumented-ci.md``
    §5): the net reaches a board net the capture wires to the
    supervisor. A tile-internal net is exported in place and bound; a
    port net rides its existing binding. The handle key is ``net`` as
    written — including the ``#b`` alias of a port split.
    """

    label: str
    net: str


@dataclass(frozen=True)
class Substitute:
    """Cut a net and re-drive the load side through a substituted source.

    The §6 human-I/O overrides: who drives the net is replaced — the
    part's ``@b`` side keeps the original driver (bit 0 = human
    control), ``@source`` is the supervisor's substitute source,
    escaped like ``control``. Cut semantics are ``InsertSeries``'s.
    """

    label: str
    net: str
    pins: tuple[str, ...]
    part: TransformPart
    source: str
    control: str | None = None
    name: str | None = None
    extra: tuple[TransformPart, ...] = ()


@dataclass(frozen=True)
class PerTile:
    """Apply ``transforms`` to every instance captured from ``subcircuit``.

    One declaration instruments all eight node tiles: a ``Subcircuit``
    subclass matches instances of exactly that type; any other capture
    callable matches by identity.
    """

    subcircuit: type[Subcircuit] | Callable[[Circuit], None]
    transforms: tuple[Transform, ...]


@dataclass(frozen=True)
class PerInstance:
    """Apply ``transforms`` to the one instance at ``path``, on top of per-tile."""

    path: tuple[str, ...]
    transforms: tuple[Transform, ...]


def apply_transforms(circuit: Circuit, plan: Sequence[Scope]) -> Handles:
    """Apply a transform plan to the hierarchical circuit's instances.

    Runs between capture and check: each matched instance's child is
    flattened in place and transformed per the plan, per-tile
    declarations first (plan order within a tile is application order —
    taps attach after the splits whose ``#b`` aliases they name).
    Returns the board-level nets the transforms escaped — control
    ports, substitute sources, exported taps — keyed by
    :class:`TileNet` for the capture to wire to the scan
    plane.
    """
    applications: list[tuple[tuple[str, ...], Instance, tuple[Transform, ...]]] = []
    for scope in plan:
        if isinstance(scope, PerTile):
            applications.extend(
                (path, inst, scope.transforms)
                for path, inst in _walk_instances(circuit, ())
                if _matches(inst, scope.subcircuit)
            )
        else:
            applications.append(
                (scope.path, _lookup_instance(circuit, scope.path), scope.transforms)
            )
    for index, (path, _, _) in enumerate(applications):
        for other, _, _ in applications[index + 1 :]:
            if _proper_prefix(path, other) or _proper_prefix(other, path):
                msg = (
                    f"transform scopes nest: {'/'.join(path)!r} and "
                    f"{'/'.join(other)!r} — flattening one absorbs the other"
                )
                raise DefinitionError(msg)
    handles: Handles = {}
    tiles: dict[tuple[str, ...], _TileTransforms] = {}
    for path, inst, transforms in applications:
        if path not in tiles:
            tiles[path] = _TileTransforms(circuit, path, inst)
        tile = tiles[path]
        for transform in transforms:
            tile.apply(transform, handles)
    return handles


def _walk_instances(
    circuit: Circuit, path: tuple[str, ...]
) -> Iterator[tuple[tuple[str, ...], Instance]]:
    """Yield every instance in the hierarchy with its full path."""
    for inst in circuit.instances.values():
        instance_path = (*path, inst.name)
        yield instance_path, inst
        yield from _walk_instances(inst.circuit, instance_path)


def _matches(inst: Instance, key: type[Subcircuit] | Callable[[Circuit], None]) -> bool:
    """Match an instance against a per-tile subcircuit key."""
    if isinstance(key, type):
        return type(inst.subcircuit) is key
    return inst.subcircuit is key


def _lookup_instance(circuit: Circuit, path: tuple[str, ...]) -> Instance:
    """Resolve an instance path to the Instance, raising if absent."""
    if not path:
        msg = "a per-instance transform scope needs a non-empty path"
        raise DefinitionError(msg)
    current = circuit
    for element in path[:-1]:
        inst = current.instances.get(element)
        if inst is None:
            msg = f"no instance at path {'/'.join(path)!r}"
            raise DefinitionError(msg)
        current = inst.circuit
    inst = current.instances.get(path[-1])
    if inst is None:
        msg = f"no instance at path {'/'.join(path)!r}"
        raise DefinitionError(msg)
    return inst


def _proper_prefix(path: tuple[str, ...], other: tuple[str, ...]) -> bool:
    """Return True when path is a proper prefix of other (nested scopes)."""
    return len(path) < len(other) and other[: len(path)] == path


class _TileTransforms:
    """Per-tile transform state: the flat child, net aliases, used labels."""

    def __init__(self, board: Circuit, path: tuple[str, ...], inst: Instance) -> None:
        self._board = board
        self._path = path
        self._inst = inst
        self._tile = inst.flatten_hierarchy()
        self._aliases: dict[str, Net] = {}
        self._labels: set[str] = set()

    def apply(self, transform: Transform, handles: Handles) -> None:
        """Apply one transform record to the tile."""
        if not transform.label:
            msg = "a transform needs a label — it is the provenance id"
            raise DefinitionError(msg)
        if transform.label in self._labels:
            msg = (
                f"duplicate transform label {transform.label!r} in tile "
                f"{'/'.join(self._path)!r}"
            )
            raise DefinitionError(msg)
        self._labels.add(transform.label)
        if not isinstance(transform, AddTap):
            for transform_part in (transform.part, *transform.extra):
                _reject_multiunit(transform_part)
        if isinstance(transform, InsertSeries):
            self._insert_series(transform, handles)
        elif isinstance(transform, Substitute):
            self._substitute(transform, handles)
        elif isinstance(transform, AddShunt):
            self._add_shunt(transform, handles)
        else:
            self._add_tap(transform, handles)

    def _insert_series(self, t: InsertSeries, handles: Handles) -> None:
        base = self._net(t.label, t.net).name
        parts = (t.part, *t.extra)
        detached, kept = self._cut(t.label, t.net, t.pins, t.name)
        special = {"a": detached, "b": kept}
        self._add_control(
            t.label, base, parts, control=t.control, special=special, handles=handles
        )
        self._require_placeholders(t.label, parts, {"a", "b"})
        self._place(t.label, base, parts, special)

    def _substitute(self, t: Substitute, handles: Handles) -> None:
        base = self._net(t.label, t.net).name
        parts = (t.part, *t.extra)
        detached, kept = self._cut(t.label, t.net, t.pins, t.name)
        special = {
            "a": detached,
            "b": kept,
            "source": self._escape(t.label, base, t.source, handles),
        }
        self._add_control(
            t.label, base, parts, control=t.control, special=special, handles=handles
        )
        self._require_placeholders(t.label, parts, {"a", "b", "source"})
        self._place(t.label, base, parts, special)

    def _add_shunt(self, t: AddShunt, handles: Handles) -> None:
        base = self._net(t.label, t.net)
        parts = (t.part, *t.extra)
        self._net(t.label, t.rail)  # the rail must resolve — proof data
        special = {"net": base}
        self._add_control(
            t.label,
            base.name,
            parts,
            control=t.control,
            special=special,
            handles=handles,
        )
        self._require_placeholders(t.label, parts, {"net"})
        self._place(t.label, base.name, parts, special)

    def _add_tap(self, t: AddTap, handles: Handles) -> None:
        base = self._net(t.label, t.net)
        board_net = self._inst.connections.get(base.name) if base.is_port else None
        if board_net is None:
            if not base.is_port:
                self._tile.export_net(base.name)
            # The provenance base is the ultimate base-capture net, not
            # the immediate one: tapping the side of an earlier cut
            # (sense#a) still derives from the plain board's sense.
            ultimate = (
                base.provenance.base if base.provenance is not None else base.name
            )
            board_net = self._board_net(t.label, ultimate, base.name)
            self._inst.bind(base.name, board_net)
        handles[TileNet(self._path, t.net)] = board_net

    def _cut(
        self,
        label: str,
        net: str,
        pins: tuple[str, ...],
        name: str | None,
    ) -> tuple[Net, Net]:
        """Split a net into the detached (#a) and interface (#b) sides."""
        if not pins:
            msg = f"transform {label!r}: a series cut needs its detached-side pins"
            raise DefinitionError(msg)
        base = self._net(label, net)
        if len(pins) >= len(base.pins):
            msg = (
                f"transform {label!r}: the cut leaves no pins on the "
                f"interface side of {base.name!r}"
            )
            raise DefinitionError(msg)
        detached = self._tile.cut_net(
            base,
            [self._pin(label, address) for address in pins],
            name=name or f"{base.name}#a",
        )
        detached.provenance = Provenance(label, base.name)
        if base.is_port:
            # The port keeps name, flag, and ranges as the #b side —
            # the parent binding holds. Later transforms name it
            # through the alias.
            self._aliases[f"{base.name}#b"] = base
            return detached, base
        kept = self._tile.cut_net(base, list(base.pins), name=f"{base.name}#b")
        kept.provenance = Provenance(label, base.name)
        self._tile.remove_net(base.name)
        return detached, kept

    def _add_control(  # noqa: PLR0913 — the record's fields threaded through
        self,
        label: str,
        base: str,
        parts: tuple[TransformPart, ...],
        *,
        control: str | None,
        special: dict[str, Net],
        handles: Handles,
    ) -> None:
        """Wire the @control placeholder: escaped when declared, else absent."""
        used = _placeholders(parts)
        if control is None:
            if "control" in used:
                msg = (
                    f"transform {label!r}: parts wire @control but no "
                    "control port is declared"
                )
                raise DefinitionError(msg)
            return
        if "control" not in used:
            msg = (
                f"transform {label!r}: control port {control!r} is not "
                "wired by any part"
            )
            raise DefinitionError(msg)
        special["control"] = self._escape(label, base, control, handles)

    def _require_placeholders(
        self, label: str, parts: tuple[TransformPart, ...], required: set[str]
    ) -> None:
        """Require the kind's structural placeholders across the parts."""
        missing = required - _placeholders(parts)
        if missing:
            msg = (
                f"transform {label!r}: parts never wire "
                f"{sorted(f'@{name}' for name in missing)}"
            )
            raise DefinitionError(msg)

    def _escape(self, label: str, base: str, port: str, handles: Handles) -> Net:
        """Create a tile port, bind it to a fresh board net, tag both."""
        if port in self._tile.nets:
            msg = (
                f"transform {label!r}: a net named {port!r} already exists "
                f"in tile {'/'.join(self._path)!r}"
            )
            raise DefinitionError(msg)
        tile_port = self._tile.port(port)
        tile_port.provenance = Provenance(label, base)
        board_net = self._board_net(label, base, port)
        self._inst.bind(port, board_net)
        handles[TileNet(self._path, port)] = board_net
        return tile_port

    def _board_net(self, label: str, base: str, name: str) -> Net:
        """Create the board-level net an escaped port or tap binds to."""
        # Pass-level names carry '/' — bypass the capture-time
        # separator check, like flatten's own prefixed net names.
        board_net = self._board._add_net(  # noqa: SLF001 — pass over IR internals
            "/".join((*self._path, name)), is_port=False
        )
        board_net.provenance = Provenance(label, base)
        return board_net

    def _place(
        self,
        label: str,
        base: str,
        parts: tuple[TransformPart, ...],
        special: dict[str, Net],
    ) -> None:
        """Place the transform's parts, provenance-tagged, nets resolved."""
        for transform_part in parts:
            nets = {
                keyword: self._spec_net(label, base, net, special)
                for keyword, net in transform_part.spec.nets.items()
            }
            spec = _rewire(transform_part.spec, nets)
            # Passes share the IR's placement internals: '/'-carrying
            # group refs bypass the capture-time separator check, like
            # flatten's own prefixed placements.
            placed = self._tile._place_typed(  # noqa: SLF001 — pass over IR internals
                transform_part.ref, spec, None
            )
            placed.provenance = Provenance(label, base)

    def _spec_net(
        self, label: str, base: str, net: Net | str, special: dict[str, Net]
    ) -> Net:
        """Resolve one spec wiring entry: placeholder, alias, or tile net."""
        if isinstance(net, Net):
            if self._tile.nets.get(net.name) is not net:
                msg = (
                    f"transform {label!r}: net {net.name!r} does not belong "
                    f"to tile {'/'.join(self._path)!r}"
                )
                raise DefinitionError(msg)
            return net
        if net.startswith("@"):
            key = net[1:]
            if key in special:
                return special[key]
            return self._generated(label, base, key)
        return self._net(label, net)

    def _generated(self, label: str, base: str, key: str) -> Net:
        """Create-or-reuse a transform-local net for a ``@name`` placeholder."""
        name = f"{label}_{key}"
        net = self._tile.nets.get(name)
        if net is None:
            net = self._tile.net(name)
            net.provenance = Provenance(label, base)
        return net

    def _net(self, label: str, name: str) -> Net:
        """Resolve a net reference: split aliases first, then tile nets."""
        net = self._aliases.get(name) or self._tile.nets.get(name)
        if net is None:
            msg = (
                f"transform {label!r}: no net {name!r} in tile {'/'.join(self._path)!r}"
            )
            raise DefinitionError(msg)
        return net

    def _pin(self, label: str, address: str) -> Pin:
        """Resolve a pin address in the flat tile: ``PHY1/Rat.b`` or ``J2.5``.

        The suffix is a typed pin keyword when the part was placed from
        a typed part that declares it (``Rat.b`` — the capture names the
        settled transform list uses), else a pin number (``J2.5``).
        """
        ref, _, key = address.rpartition(".")
        part = self._tile.parts.get(ref) if ref else None
        if part is None:
            msg = (
                f"transform {label!r}: no part for pin address {address!r} "
                f"in tile {'/'.join(self._path)!r}"
            )
            raise DefinitionError(msg)
        pin_names = part.pin_names
        if pin_names is not None and key in pin_names:
            numbers = pin_names[key]
            if len(numbers) != 1:
                msg = (
                    f"transform {label!r}: pin address {address!r} names "
                    f"{len(numbers)} pins — address one by number"
                )
                raise DefinitionError(msg)
            return part.pin(numbers[0])
        return part.pin(key)


def _placeholders(parts: tuple[TransformPart, ...]) -> set[str]:
    """Collect the ``@``-placeholder names a transform's parts wire."""
    return {
        net[1:]
        for part in parts
        for net in part.spec.nets.values()
        if isinstance(net, str) and net.startswith("@")
    }


def _reject_multiunit(transform_part: TransformPart) -> None:
    """Reject multi-unit packages in transform parts.

    The engine rebinds the whole spec's wiring at once; multi-unit
    packages wire their units individually, so they cannot appear.
    """
    if isinstance(transform_part.spec, MultiUnitPart):
        msg = (
            f"transform part {transform_part.ref!r}: multi-unit specs are "
            "unsupported — units wire individually; place them in the capture"
        )
        raise DefinitionError(msg)


def _rewire(spec: TypedPart, nets: dict[str, Net]) -> TypedPart:
    """Rebind a record's part spec to resolved nets, keeping its class.

    The copy keeps the subclass, value, footprint, and pin map; the
    wiring dict is replaced wholesale, so the pin keyword set is
    preserved by construction — no per-class constructor signatures
    involved.
    """
    rewired = copy.copy(spec)
    rewired._nets = dict(nets)  # noqa: SLF001 — the spec's own wiring field
    return rewired
