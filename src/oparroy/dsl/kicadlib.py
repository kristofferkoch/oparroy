"""Access to KiCad's symbol and footprint libraries (DESIGN.md §7).

The DSL validates part references against KiCad's actual libraries:
symbols are parsed from ``.kicad_sym`` files (including ``extends``
inheritance and per-unit subsymbols — the unit structure is preserved,
not flattened), footprints are checked by their presence on disk
(``<Lib>.pretty/<Name>.kicad_mod``). The library roots
come from the nix dev shell (``OPARROY_KICAD_SYMBOL_DIR`` /
``OPARROY_KICAD_FOOTPRINT_DIR``, see flake.nix) so the validated data is
exactly what the pinned KiCad would use.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from oparroy.dsl.ir import (
    PinType,
    Symbol,
    SymbolPin,
    SymbolUnit,
    UnknownSymbolError,
    natural_key,
)
from oparroy.dsl.sexpr import Sexp, parse

_SYMBOL_DIR_ENV = "OPARROY_KICAD_SYMBOL_DIR"
_FOOTPRINT_DIR_ENV = "OPARROY_KICAD_FOOTPRINT_DIR"

_SUBSYMBOL = re.compile(r"_(\d+)_(\d+)$")


class LibraryError(Exception):
    """The KiCad library installation is missing or unreadable."""


def split_ref(ref: str) -> tuple[str, str]:
    """Split a ``Lib:Name`` reference into its two parts.

    >>> split_ref("Device:R")
    ('Device', 'R')
    """
    lib, sep, name = ref.partition(":")
    if not sep or not lib or not name:
        msg = f"expected a 'Lib:Name' reference, got {ref!r}"
        raise LibraryError(msg)
    return lib, name


def _children(node: Sexp, head: str) -> list[list[Sexp]]:
    return [
        child
        for child in node
        if isinstance(child, list) and len(child) > 0 and child[0] == head
    ]


def _arg(node: list[Sexp], index: int) -> str | None:
    """Return the string argument at a position, or None."""
    if len(node) <= index:
        return None
    value = node[index]
    if not isinstance(value, str):
        return None
    return value


def _property(node: Sexp, name: str) -> str | None:
    for prop in _children(node, "property"):
        if _arg(prop, 1) == name:
            return _arg(prop, 2)
    return None


def _parse_pin(node: list[Sexp]) -> SymbolPin | None:
    raw_type = _arg(node, 1)
    if raw_type is None:
        return None
    number = next(
        (
            value
            for child in _children(node, "number")
            if (value := _arg(child, 1)) is not None
        ),
        None,
    )
    if number is None:
        return None
    name = next(
        (
            value
            for child in _children(node, "name")
            if (value := _arg(child, 1)) is not None
        ),
        "",
    )
    try:
        pin_type = PinType(raw_type)
    except ValueError:
        msg = f"unknown KiCad pin type {raw_type!r}"
        raise LibraryError(msg) from None
    return SymbolPin(number=number, name=name, type=pin_type)


class KiCadLibraries:
    """Symbol and footprint tables backed by on-disk KiCad libraries."""

    def __init__(self, symbol_dir: Path, footprint_dir: Path) -> None:
        self._symbol_dir = symbol_dir
        self._footprint_dir = footprint_dir
        self._lib_cache: dict[str, dict[str, list[Sexp]]] = {}

    @classmethod
    def from_env(cls) -> KiCadLibraries:
        """Build from the dev-shell environment (flake.nix exports)."""
        symbol_dir = os.environ.get(_SYMBOL_DIR_ENV)
        footprint_dir = os.environ.get(_FOOTPRINT_DIR_ENV)
        if symbol_dir is None or footprint_dir is None:
            msg = (
                f"{_SYMBOL_DIR_ENV} and {_FOOTPRINT_DIR_ENV} must point at "
                "KiCad's libraries; enter the nix dev shell (DESIGN.md §8)"
            )
            raise LibraryError(msg)
        for env_var, raw in (
            (_SYMBOL_DIR_ENV, symbol_dir),
            (_FOOTPRINT_DIR_ENV, footprint_dir),
        ):
            if not Path(raw).is_dir():
                msg = f"{env_var} points at {raw}, which is not a directory"
                raise LibraryError(msg)
        return cls(Path(symbol_dir), Path(footprint_dir))

    def lookup(self, ref: str) -> Symbol:
        """Resolve ``Lib:Name`` to a Symbol, following ``extends`` chains."""
        lib_name, symbol_name = split_ref(ref)
        raw = self._load_lib(lib_name)
        chain: list[list[Sexp]] = []
        seen: set[str] = set()
        current: str | None = symbol_name
        parent: str | None = None
        while current is not None:
            if current in seen:
                msg = (
                    f"cyclic 'extends' chain at {lib_name}:{current!r} "
                    f"while resolving {ref!r}"
                )
                raise LibraryError(msg)
            seen.add(current)
            try:
                node = raw[current]
            except KeyError:
                if parent is None:
                    msg = f"no symbol {ref!r} in KiCad library {lib_name!r}"
                else:
                    msg = (
                        f"symbol {parent!r} extends {current!r}, which is "
                        f"not in KiCad library {lib_name!r} "
                        f"(resolving {ref!r})"
                    )
                raise UnknownSymbolError(msg) from None
            chain.append(node)
            parent = current
            current = _extends_target(node)
        common: dict[str, SymbolPin] = {}
        units: dict[int, dict[str, SymbolPin]] = {}
        conflicts: set[str] = set()
        filters: tuple[str, ...] = ()
        for node in reversed(chain):
            node_common, node_units, node_conflicts = _symbol_pins(node)
            common.update(node_common)
            for number, pins in node_units.items():
                units.setdefault(number, {}).update(pins)
            conflicts |= node_conflicts
            filters = _footprint_filters(node) or filters
        merged: dict[str, SymbolPin] = dict(common)
        for number in sorted(units):
            merged.update(units[number])
        return Symbol(
            lib=lib_name,
            name=symbol_name,
            pins=tuple(merged.values()),
            footprint_filters=filters,
            pin_conflicts=tuple(sorted(conflicts, key=natural_key)),
            common_pins=tuple(common.values()),
            units=tuple(
                SymbolUnit(number=number, pins=tuple(units[number].values()))
                for number in sorted(units)
            ),
        )

    def exists(self, footprint: str) -> bool:
        """Check that ``Lib:Name`` resolves to a .kicad_mod file on disk."""
        lib_name, fp_name = split_ref(footprint)
        path = self._footprint_dir / f"{lib_name}.pretty" / f"{fp_name}.kicad_mod"
        return path.is_file()

    def _load_lib(self, lib_name: str) -> dict[str, list[Sexp]]:
        if lib_name in self._lib_cache:
            return self._lib_cache[lib_name]
        path = self._symbol_dir / f"{lib_name}.kicad_sym"
        if not path.is_file():
            msg = f"KiCad symbol library {lib_name!r} not found at {path}"
            raise LibraryError(msg)
        root = parse(path.read_text(encoding="utf-8"))
        symbols = {
            name: node
            for node in _children(root, "symbol")
            if (name := _arg(node, 1)) is not None
        }
        self._lib_cache[lib_name] = symbols
        return symbols


def _extends_target(node: list[Sexp]) -> str | None:
    for child in _children(node, "extends"):
        target = _arg(child, 1)
        if target is not None:
            return target
    return None


def _symbol_pins(
    node: list[Sexp],
) -> tuple[dict[str, SymbolPin], dict[int, dict[str, SymbolPin]], set[str]]:
    """Collect a symbol's pins by unit, reporting conflicting redefinitions.

    Subsymbol names follow KiCad's ``<Name>_<unit>_<style>``
    convention (DESIGN.md §7): unit 0 pins are common to every placed
    unit, and styles are alternate graphics merged per unit. Identical
    duplicates — pin stacking, or a physical pin shared by several
    units (the BAT54ADW anodes) — stay silent, but a same-numbered pin
    redefined with a different name or electrical type is conflicting
    library data: the last definition wins and the pin number is
    reported as a conflict.
    """
    common: dict[str, SymbolPin] = {}
    units: dict[int, dict[str, SymbolPin]] = {}
    seen: dict[str, SymbolPin] = {}
    conflicts: set[str] = set()
    for subsymbol in _children(node, "symbol"):
        name = _arg(subsymbol, 1) or ""
        match = _SUBSYMBOL.search(name)
        if match is None:
            msg = (
                f"subsymbol {name!r} does not follow KiCad's "
                "<name>_<unit>_<style> convention"
            )
            raise LibraryError(msg)
        unit = int(match.group(1))
        scope = common if unit == 0 else units.setdefault(unit, {})
        for pin_node in _children(subsymbol, "pin"):
            pin = _parse_pin(pin_node)
            if pin is None:
                continue
            previous = seen.get(pin.number)
            if previous is not None and (previous.name, previous.type) != (
                pin.name,
                pin.type,
            ):
                conflicts.add(pin.number)
            seen[pin.number] = pin
            scope[pin.number] = pin
    return common, units, conflicts


def _footprint_filters(node: list[Sexp]) -> tuple[str, ...]:
    raw = _property(node, "ki_fp_filters")
    if raw is None:
        return ()
    return tuple(raw.split())
