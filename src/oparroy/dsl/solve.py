"""Value resolution: the pass between capture/transforms and check.

A computed value (a divider ratio, a threshold) is captured as a spec
— a :class:`ValueRange`, target plus tolerance — never an unsourcable
irrational number (DESIGN.md §7). ``solve`` resolves every spec on the
IR against the part's stocked ``ValueBin`` (the parts DB's
``PartRecord.bin``, threaded onto the placed part as
``Part.value_bin``) and rewrites ``Part.value`` to the stocked
literal, reporting each pick's achieved error. Literal strings are
never touched.

The walk is hierarchical and in place: ``check`` and the emitters
flatten their own copies, so resolving a flattened copy here would
leave the originals unsolved — instance children are mutated where
they live, and flattening carries the solved literals downstream. A
spec on a part with no value bin, or one no stocked value meets, is an
error issue; a spec surviving to ``check`` or an emitter (solve never
ran) is rejected there, so the pipeline order is enforced, not
conventional.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from oparroy.dsl.check import Issue, Severity
from oparroy.dsl.ir import Circuit, DefinitionError, Part, natural_key
from oparroy.dsl.values import ValueRange, format_value, parse_value


@dataclass(frozen=True)
class Resolution:
    """One resolved spec: the part's path, the spec, the pick, the miss.

    ``rel_error`` is signed relative error of the chosen value against
    the spec's nominal; +0.0% is an exact hit.
    """

    path: str
    spec: ValueRange
    chosen: float
    chosen_str: str
    rel_error: float

    def __str__(self) -> str:
        return (
            f"{self.path}: {self.spec} → {self.chosen_str} "
            f"(achieved {self.rel_error:+.1%})"
        )


@dataclass
class SolveReport:
    """``solve``'s result: the error issues and the per-part resolutions."""

    issues: list[Issue] = field(default_factory=list)
    resolutions: list[Resolution] = field(default_factory=list)

    def __str__(self) -> str:
        return "\n".join(str(resolution) for resolution in self.resolutions)


def solve(circuit: Circuit) -> SolveReport:
    """Resolve every ``ValueRange`` on the IR to a stocked literal.

    Parts are visited in natural path order, and each pick joins the
    in-use set the consolidation tie-break consults (alongside the
    circuit's literal values), so repeated solves are deterministic and
    identical specs consolidate onto one stocked value. Mutates the
    circuit in place and returns the report.
    """
    parts: list[tuple[str, Part]] = []
    _collect_parts(circuit, (), parts, set())
    parts.sort(key=lambda item: natural_key(item[0]))
    literals = [part.value for _, part in parts if isinstance(part.value, str)]
    in_use: dict[str, set[float]] = {}
    report = SolveReport()
    for path, part in parts:
        if not isinstance(part.value, ValueRange):
            continue
        spec = part.value
        value_bin = part.value_bin
        if value_bin is None:
            report.issues.append(
                Issue(
                    Severity.ERROR,
                    f"{path}: value spec {spec} but the part has no value bin "
                    "(a parts-DB record's bin declares the stocked grid)",
                )
            )
            continue
        used = in_use.setdefault(
            value_bin.kind, _parse_literals(literals, value_bin.kind)
        )
        chosen = value_bin.resolve(spec, in_use=frozenset(used))
        if chosen is None:
            report.issues.append(
                Issue(
                    Severity.ERROR,
                    f"{path}: no value in the {value_bin.kind} bin "
                    f"(E{value_bin.series}, "
                    f"{format_value(value_bin.lo, family=value_bin.kind)}.."
                    f"{format_value(value_bin.hi, family=value_bin.kind)}) "
                    f"meets {spec}",
                )
            )
            continue
        chosen_str = format_value(chosen, family=value_bin.kind)
        part.value = chosen_str
        used.add(chosen)
        assert spec.nominal is not None  # noqa: S101 — ValueRange fills it
        rel_error = (chosen - spec.nominal) / spec.nominal if spec.nominal > 0 else 0.0
        report.resolutions.append(Resolution(path, spec, chosen, chosen_str, rel_error))
    return report


def _collect_parts(
    circuit: Circuit,
    prefix: tuple[str, ...],
    out: list[tuple[str, Part]],
    seen: set[int],
) -> None:
    """Collect (hierarchical path, part) pairs, instance children included."""
    if id(circuit) in seen:
        return
    seen.add(id(circuit))
    out.extend(("/".join((*prefix, ref)), part) for ref, part in circuit.parts.items())
    for instance in circuit.instances.values():
        _collect_parts(instance.circuit, (*prefix, instance.name), out, seen)


def _parse_literals(literals: list[str], family: str) -> set[float]:
    """Parse the circuit's literal values into a family; skip non-values.

    Model names and DNP markers fail the family parse — they are not
    consolidation candidates, and their failure is no error.
    """
    parsed: set[float] = set()
    for literal in literals:
        try:
            parsed.add(parse_value(literal, family=family))
        except DefinitionError:
            continue
    return parsed
