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

Multi-unit packages (a quad op-amp, a BAT54ADW) follow KiCad's unit
model (DESIGN.md §7); parts whose units are used as one element, like
the BAT54S series pair, stay package-as-one-part — as does KiCad's
own library.

Error policy: a missing or misspelled pin on the built-in classes is
signature misuse and raises ``TypeError`` from argument binding;
``DefinitionError`` is for IR-level violations (including the
``TypedPart`` validation that guards subclasses forwarding
hand-built kwargs).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from oparroy.dsl.ir import Bundle, DefinitionError

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
