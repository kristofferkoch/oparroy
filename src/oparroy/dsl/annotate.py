"""Annotation: the second stage between capture and pcbnew (DESIGN.md §7).

Capture names (``WD1/Rs``) are the stable identity; annotation maps
them to the refdes the board carries (``R3``). The stage is explicit
and repeatable: ``annotate`` preserves a prior annotation for every
part that survives a source edit and numbers new parts deterministically,
``apply_annotation`` renames the IR for emission (tstamps stay keyed on
the capture identity, so pcbnew keeps matching parts by timestamp), and
``annotation_from_pcb`` folds pcbnew's placement-driven renumbering —
KiCad's geographic annotation — back into the DSL's table. That is the
§7 round trip: emission is not a one-shot export.

An annotation is data: JSON on disk, byte-identical on write, so a
renumbering diff in review is exactly the placement change.
"""

from __future__ import annotations

import fnmatch
import json
import re
from typing import TYPE_CHECKING

from oparroy.dsl.ir import Circuit, Part, natural_key
from oparroy.dsl.kicad_emit import part_tstamp
from oparroy.dsl.sexpr import Sexp, parse

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

_REFDES = re.compile(r"[A-Z][A-Z0-9]*[0-9]+")

#: Symbol-class → refdes prefix, first match wins (``Lib:Name`` globs).
#: Connector test points precede the generic connector rule.
DEFAULT_PREFIX_RULES: tuple[tuple[str, str], ...] = (
    ("Connector:TestPoint*", "TP"),
    ("Connector*:*", "J"),
    ("Device:R", "R"),
    ("Device:C", "C"),
    ("Device:L", "L"),
    ("Device:LED", "LED"),
    ("Device:D*", "D"),
    ("Device:Q*", "Q"),
    ("Diode*:*", "D"),
    ("Transistor*:*", "Q"),
    ("MCU_*:*", "U"),
    ("74*:*", "U"),
    ("Analog_Switch:*", "U"),
    ("Regulator*:*", "U"),
)


class AnnotationError(Exception):
    """The annotation stage failed: bad table, unknown class, drift."""


class Annotation:
    """A capture-path → refdes table, with JSON IO.

    Construction validates: every value is a well-formed refdes
    (letters + number) and no two paths share one. ``circuit`` names
    the design the table belongs to, so loading a stale table against
    a renamed capture is a visible error, not silent misassignment.
    """

    def __init__(self, refs: Mapping[str, str], *, circuit: str | None = None) -> None:
        self._refs = dict(refs)
        self._circuit = circuit
        ordered = sorted(self._refs.items(), key=lambda kv: natural_key(kv[0]))
        for path, refdes in ordered:
            if _REFDES.fullmatch(refdes) is None:
                msg = f"{path!r} is annotated {refdes!r}, not a refdes"
                raise AnnotationError(msg)
        seen: dict[str, str] = {}
        for path, refdes in self._refs.items():
            if refdes in seen:
                msg = f"{seen[refdes]!r} and {path!r} are both annotated {refdes!r}"
                raise AnnotationError(msg)
            seen[refdes] = path

    @property
    def refs(self) -> dict[str, str]:
        """The table: flat capture path → refdes."""
        return dict(self._refs)

    def to_json(self) -> str:
        """Serialize: sorted keys, byte-identical across runs."""
        refs = {key: self._refs[key] for key in sorted(self._refs, key=natural_key)}
        payload = {"circuit": self._circuit, "refs": refs}
        return json.dumps(payload, indent=2) + "\n"

    @classmethod
    def from_json(cls, text: str) -> Annotation:
        """Parse a table written by ``to_json``."""
        raw = json.loads(text)
        if (
            not isinstance(raw, dict)
            or not isinstance(raw.get("refs"), dict)
            or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in raw["refs"].items()
            )
        ):
            msg = "an annotation file is a JSON object with a string 'refs' map"
            raise AnnotationError(msg)
        circuit = raw.get("circuit")
        if circuit is not None and not isinstance(circuit, str):
            msg = "an annotation file's 'circuit' must be a string or null"
            raise AnnotationError(msg)
        return cls(raw["refs"], circuit=circuit)


def _prefix(symbol_ref: str, rules: Sequence[tuple[str, str]]) -> str:
    for pattern, prefix in rules:
        if fnmatch.fnmatchcase(symbol_ref, pattern):
            return prefix
    msg = f"no refdes prefix rule matches symbol {symbol_ref!r}"
    raise AnnotationError(msg)


def _board_parts(circuit: Circuit) -> dict[str, Part]:
    """Flat parts minus power symbols (schematic-only net markers)."""
    if circuit.instances:
        circuit = circuit.flatten()
    return {
        ref: part for ref, part in circuit.parts.items() if not part.symbol.is_power
    }


def annotate(
    circuit: Circuit,
    *,
    prior: Annotation | None = None,
    rules: Sequence[tuple[str, str]] = DEFAULT_PREFIX_RULES,
) -> Annotation:
    """Assign refdes to every board part, preserving what still fits.

    A prior entry is kept when the part still exists, its symbol class
    still matches the refdes prefix, and no other surviving part claims
    the same refdes; everything else is numbered from the lowest free
    number per prefix in natural capture-path order — deterministic, so
    a source edit renumbers only what it touched.
    """
    if circuit.instances:
        circuit = circuit.flatten()
    parts = _board_parts(circuit)
    prefixes = {ref: _prefix(part.symbol.ref, rules) for ref, part in parts.items()}
    assigned: dict[str, str] = {}
    used: set[str] = set()
    prior_refs = prior.refs if prior is not None else {}
    for ref in sorted(parts, key=natural_key):
        refdes = prior_refs.get(ref)
        if refdes is None:
            continue
        if refdes.rstrip("0123456789") == prefixes[ref] and refdes not in used:
            assigned[ref] = refdes
            used.add(refdes)
    for ref in sorted(parts, key=natural_key):
        if ref in assigned:
            continue
        prefix = prefixes[ref]
        number = 1
        while f"{prefix}{number}" in used:
            number += 1
        assigned[ref] = f"{prefix}{number}"
        used.add(assigned[ref])
    return Annotation(assigned, circuit=circuit.name)


def apply_annotation(circuit: Circuit, annotation: Annotation) -> Circuit:
    """Rename the IR to its refdes; the emitters consume the result.

    Every board part must be covered — a partial table is a stage bug,
    not a choice. Power symbols pass through under their capture refs.
    """
    parts = _board_parts(circuit)
    refs = annotation.refs
    missing = sorted(set(parts) - set(refs), key=natural_key)
    if missing:
        msg = f"annotation covers no refdes for parts {missing}"
        raise AnnotationError(msg)
    return circuit.renamed(refs)


def _children(node: Sexp, head: str) -> list[list[Sexp]]:
    return [
        child
        for child in node
        if isinstance(child, list) and len(child) > 0 and child[0] == head
    ]


def _footprint_link(footprint: list[Sexp]) -> str | None:
    """Extract the comp tstamp a pcbnew footprint carries.

    pcbnew writes the netlist's sheetpath + comp tstamp as the
    footprint's ``path`` — the last segment is the link; the bare
    ``uuid`` is the fallback for layouts saved without a path.
    """
    for child in _children(footprint, "path"):
        if len(child) > 1 and isinstance(child[1], str):
            return child[1].rstrip("/").rsplit("/", maxsplit=1)[-1]
    for child in _children(footprint, "uuid"):
        if len(child) > 1 and isinstance(child[1], str):
            return child[1]
    return None


def _footprint_reference(footprint: list[Sexp]) -> str | None:
    """Extract the footprint's ``Reference`` property, if present."""
    for child in _children(footprint, "property"):
        match child:
            case [_, "Reference", str() as value, *_]:
                return value
    return None


def annotation_from_pcb(
    circuit: Circuit,
    pcb_text: str,
    *,
    prior: Annotation | None = None,
) -> Annotation:
    """Read pcbnew's renumbering back: capture path → placed refdes.

    Joins each ``.kicad_pcb`` footprint's comp tstamp (the content-
    derived identity this DSL emitted) to its ``Reference`` property —
    the refdes after KiCad's geographic annotation. Footprints the
    capture doesn't know (mounting holes placed in pcbnew) are skipped;
    parts the layout dropped simply fall out of the table, and a
    following ``annotate(prior=...)`` renumbers them. ``prior`` entries
    for parts the PCB doesn't mention are kept.
    """
    if circuit.instances:
        circuit = circuit.flatten()
    parts = _board_parts(circuit)
    by_tstamp = {
        str(part_tstamp(circuit.name, part.identity)): ref
        for ref, part in parts.items()
    }
    refs = prior.refs if prior is not None else {}
    root = parse(pcb_text)
    for footprint in _children(root, "footprint"):
        link = _footprint_link(footprint)
        if link is None or link not in by_tstamp:
            continue
        reference = _footprint_reference(footprint)
        if reference is not None:
            refs[by_tstamp[link]] = reference
    return Annotation(refs, circuit=circuit.name)
