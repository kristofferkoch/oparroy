"""Typed jellybean parts (DESIGN.md §7): real classes for common parts.

Common passives and transistors get typed classes so the type checker
and autocomplete cover declaration and connection alike; one-off parts
stay string-declared (``Circuit.part(symbol=...)``). Pin names are
keyword-only parameters in the class signature — construction carries
the wiring, ``Circuit.part`` places and connects in one step, and a
missing or misspelled pin fails at construction. Value may be
positional only for unpolarized two-pin parts (``Resistor``,
``Capacitor``); anything direction-sensitive is keyword-only
throughout. Classes accrete as captures need them (YAGNI — no
speculative zoo). Footprints default per class — subclass per
footprint bin (``class R0603(Resistor)``) — overridable per instance.

Multi-unit packages (a quad switch, a BAT54ADW) follow KiCad's unit
model (DESIGN.md §7): ``MultiUnitPart`` declares the placed unit
subset with typed per-unit pin names; construction places but wires
nothing — units wire individually through typed handles
(``board.connect(net, u1.unit(1).anode)``) or pack into subcircuit
component sockets (``SocketSpec``) at instantiation. Parts whose units
are used as one element, like the BAT54S series pair, stay
package-as-one-part — as does KiCad's own library.

Error policy: a missing or misspelled pin on the built-in classes is
signature misuse and raises ``TypeError`` from argument binding;
``DefinitionError`` is for IR-level violations (including the
``TypedPart`` validation that guards subclasses forwarding
hand-built kwargs).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from oparroy.dsl.ir import Bundle, DefinitionError, SocketSpec

if TYPE_CHECKING:
    from oparroy.dsl.ir import Net


class TypedPart:
    """A typed part spec: symbol, value, footprint, and pin wiring.

    Subclasses fix ``symbol`` and ``pin_map`` (keyword name → pin
    number, or a tuple of numbers for a keyword owning several pins)
    and declare the pins as keyword-only parameters, then pass the
    collected wiring here. ``Circuit.part`` consumes the spec.
    """

    symbol: ClassVar[str]
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]]
    default_value: ClassVar[str | None] = None
    default_footprint: ClassVar[str | None] = None

    def __init__(
        self,
        value: str | None,
        footprint: str | None,
        nets: dict[str, Net | str],
    ) -> None:
        unknown = sorted(nets.keys() - self.pin_map.keys())
        if unknown:
            msg = f"{type(self).__name__} has no pins {unknown}"
            raise DefinitionError(msg)
        missing = sorted(self.pin_map.keys() - nets.keys())
        if missing:
            msg = f"{type(self).__name__} is missing pins {missing}"
            raise DefinitionError(msg)
        self.value = self.default_value if value is None else value
        self.footprint = self.default_footprint if footprint is None else footprint
        self._nets = dict(nets)

    @property
    def nets(self) -> dict[str, Net | str]:
        """Wiring by pin keyword name, as passed at construction."""
        return dict(self._nets)


class Resistor(TypedPart):
    """Unpolarized resistor (``Device:R``); pins ``a``/``b`` are 1/2."""

    symbol = "Device:R"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {"a": "1", "b": "2"}

    def __init__(
        self,
        value: str,
        *,
        a: Net | str,
        b: Net | str,
        footprint: str | None = None,
    ) -> None:
        super().__init__(value, footprint, {"a": a, "b": b})


class Capacitor(TypedPart):
    """Unpolarized capacitor (``Device:C``); pins ``a``/``b`` are 1/2."""

    symbol = "Device:C"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {"a": "1", "b": "2"}

    def __init__(
        self,
        value: str,
        *,
        a: Net | str,
        b: Net | str,
        footprint: str | None = None,
    ) -> None:
        super().__init__(value, footprint, {"a": a, "b": b})


class Diode(TypedPart):
    """Single diode (``Device:D``); ``anode`` is pin 2, ``cathode`` pin 1.

    Keyword-only: orientation is the whole point of a diode. No
    class-default footprint — subclass per footprint bin, like
    ``Resistor``/``Capacitor``.
    """

    symbol = "Device:D"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "anode": "2",
        "cathode": "1",
    }

    def __init__(
        self,
        *,
        anode: Net | str,
        cathode: Net | str,
        value: str | None = None,
        footprint: str | None = None,
    ) -> None:
        super().__init__(value, footprint, {"anode": anode, "cathode": cathode})


class MultiUnitPart(TypedPart):
    """A multi-unit package (a quad switch, a BAT54ADW): units wire singly.

    Subclasses fix ``symbol`` and ``unit_pins`` — placed unit number →
    pin keyword → physical pin number. The declared units are the
    placed subset (DESIGN.md §7): unplaced units materialize no pins,
    and one physical pin repeating *across* units (the BAT54ADW
    anodes) is the shared-pin case — it sits on one net. Construction
    places but wires nothing: units wire at board level through typed
    handles (``board.connect(net, u1.unit(1).anode)``) or pack into
    subcircuit component sockets at instantiation.
    """

    unit_pins: ClassVar[dict[int, dict[str, str]]]

    def __init__(
        self, *, value: str | None = None, footprint: str | None = None
    ) -> None:
        self.value = self.default_value if value is None else value
        self.footprint = self.default_footprint if footprint is None else footprint
        self._nets: dict[str, Net | str] = {}


class Bat54adw(MultiUnitPart):
    """BAT54ADW quad Schottky (``Diode:BAT54ADW``, SOT-363): two com-anode pairs.

    Units 1/2 share anode pin 6, units 3/4 share anode pin 3. Unit
    pins follow the ``DiodeSocket`` protocol (``anode``/``cathode``),
    so any unit packs into a diode socket.
    """

    symbol = "Diode:BAT54ADW"
    unit_pins: ClassVar[dict[int, dict[str, str]]] = {
        1: {"cathode": "1", "anode": "6"},
        2: {"cathode": "2", "anode": "6"},
        3: {"anode": "3", "cathode": "4"},
        4: {"anode": "3", "cathode": "5"},
    }
    default_value = "BAT54ADW"
    default_footprint = "Package_TO_SOT_SMD:SOT-363_SC-70-6"


class DiodeSocket(SocketSpec):
    """A single-diode socket: ``anode``/``cathode`` pin handles.

    Satisfied standalone by a ``Diode`` (the default) or packed into
    any unit of a ``Bat54adw``-class package — the instantiating
    parent's directed choice (DESIGN.md §7, T7bc).
    """

    pins: ClassVar[tuple[str, ...]] = ("anode", "cathode")
    default: ClassVar[type[TypedPart]] = Diode


class Bat54s(TypedPart):
    """BAT54S series Schottky pair (``Diode:BAT54S``, SOT-23).

    Pins are the pair's overall ``anode`` (pin 1) and ``cathode``
    (pin 2) plus the shared middle ``com`` (pin 3). Keyword-only:
    orientation is the whole point of a series pair.
    """

    symbol = "Diode:BAT54S"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "anode": "1",
        "cathode": "2",
        "com": "3",
    }
    default_value = "BAT54S"
    default_footprint = "Package_TO_SOT_SMD:SOT-23"

    def __init__(
        self,
        *,
        anode: Net | str,
        cathode: Net | str,
        com: Net | str,
        value: str | None = None,
        footprint: str | None = None,
    ) -> None:
        super().__init__(
            value,
            footprint,
            {"anode": anode, "cathode": cathode, "com": com},
        )


class BundleConnector(TypedPart):
    """A connector block: pins wired from a bundle, declared as data.

    Subclasses fix ``symbol`` and ``pin_map`` — bundle member name →
    pin number, or a tuple of numbers for a member owning several pins
    (the §3 segment connector's paired grounds) — plus optional
    ``default_value``/``default_footprint``. Construction takes the
    bundle: member names must match ``pin_map`` exactly, and drift
    reports through ``TypedPart``'s unknown/missing-pin errors.
    """

    def __init__(self, bundle: Bundle, *, footprint: str | None = None) -> None:
        if not isinstance(bundle, Bundle):
            msg = f"{type(self).__name__} wires a Bundle, got {bundle!r}"
            raise TypeError(msg)
        super().__init__(None, footprint, dict(bundle.items()))
