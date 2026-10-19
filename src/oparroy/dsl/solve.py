"""Value resolution: the pass between capture/transforms and check.

A computed value (a divider ratio, a threshold) is captured as a spec
— a :class:`ValueRange`, target plus tolerance — never an unsourcable
irrational number (DESIGN.md §7). ``solve`` resolves every spec on the
IR against the part's stocked ``ValueBin`` (the parts DB's
``PartRecord.bin``, threaded onto the placed part as
``Part.value_bin``) and rewrites ``Part.value`` to the stocked
literal, reporting each pick's achieved error. Literal strings are
never touched.

Three specs resolve here. A ``ValueRange`` on a part resolves that
part alone against its bin. A ``DividerHalf`` (``DividerSpec.top()`` /
``.bottom()``) marks one resistor of a divider: the two sibling halves
share a ``DividerSpec`` within one capture and resolve together,
meeting its ratio, Thévenin output impedance, and standing-current
constraints with one stocked pair. One spec resolves one divider, and
scoping the group to the capture keeps a hoisted spec safe across
instances of a reusable subcircuit. Dividers resolve first — their
picks join the in-use set single specs then consolidate against.

A ``Generator`` runs first of all: a capture-declared function that
computes its part's value from circuit context — the LED's series
resistor sized from the rail it actually runs on. Each generator is
evaluated in place, in natural path order, with a ``SolveContext``
whose ``rail_voltage`` follows instance bindings outward to the supply
a parent actually binds (falling back to the rail's own declaration
when the block stands alone). The returned literal or ``ValueRange``
replaces the generator, so a generated spec reports its achieved error
like an authored one; a generator that raises ``DefinitionError``, or
returns anything but a literal or ``ValueRange``, is an error issue.
Generators read the finished IR, never other parts' unresolved specs —
a generated value resolves in the same pass, not mid-evaluation.

The walk is hierarchical and in place: ``check`` and the emitters
flatten their own copies, so resolving a flattened copy here would
leave the originals unsolved — instance children are mutated where
they live, and flattening carries the solved literals downstream. A
spec on a part with no value bin, or one no stocked value meets, is an
error issue; a spec surviving to ``check`` or a netlist emitter (solve
never ran) is rejected there, so the pipeline order is enforced, not
conventional.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from oparroy.dsl.check import Issue, Severity
from oparroy.dsl.ir import Circuit, DefinitionError, Net, Part, natural_key
from oparroy.dsl.values import (
    DividerHalf,
    DividerSpec,
    Generator,
    ValueRange,
    format_value,
    parse_value,
)


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


@dataclass(frozen=True)
class GeneratorEvaluation:
    """One evaluated generator: the part's path, the generator, its output.

    ``produced`` is what the function returned — a literal or the spec
    the normal resolution pass then picks from (its ``Resolution``
    follows for a ``ValueRange``). It records the context-computed
    target, so a rail change that shifts a generated value is visible
    in the report rather than only in the final literal.
    """

    path: str
    generator: Generator
    produced: str | ValueRange

    def __str__(self) -> str:
        return f"{self.path}: {self.generator} → {self.produced}"


@dataclass(frozen=True)
class _SolveContext:
    """The live :class:`SolveContext` solve hands a generator.

    ``_ancestors`` maps each of the owning capture's nets (by identity)
    to its binding chain in the ancestors — immediate parent first,
    outermost last — so ``rail_voltage`` can prefer the supply a parent
    actually binds over the local declaration. ``_nets`` is the
    generator's authored-capture name map, attached when flatten folds
    that capture away, so a local name still resolves after the
    instrumentation pass flattens a tile.
    """

    path: str
    part: Part
    circuit: Circuit
    _ancestors: Mapping[int, tuple[Net, ...]] = field(default_factory=dict, repr=False)
    _nets: Mapping[str, Net] | None = field(default=None, repr=False)

    def rail_voltage(self, net: Net | str) -> ValueRange | None:
        """Return the net's declared rail voltage, outermost binding first.

        A string is a net name in the part's authored capture; an
        unknown name is a ``DefinitionError`` (the generator gets a
        path-named solve issue instead of a crash). The candidate order
        is the outermost bound net inward, then the local net: a
        block's own declaration is the standalone fallback, never an
        override of the rail its parent binds.
        """
        if isinstance(net, str):
            local = None if self._nets is None else self._nets.get(net)
            if local is None:
                local = self.circuit.nets.get(net)
            if local is None:
                msg = (
                    f"net {net!r} is not in capture {self.circuit.name!r} "
                    f"(a generator names nets in its own capture)"
                )
                raise DefinitionError(msg)
        else:
            local = net
        chain = self._ancestors.get(id(local), ())
        for candidate in (*reversed(chain), local):
            domain = candidate.power_domain
            if domain is not None and domain.voltage is not None:
                return domain.voltage
        return None


@dataclass(frozen=True)
class DividerResolution:
    """One resolved divider: the spec, the picked pair, the achieved figures.

    ``r1`` is the VCC-side (top) resistor, ``r2`` the GND-side
    (bottom); ``ratio_error`` is signed relative error of the achieved
    ratio against the spec's nominal ratio.
    """

    path: str
    spec: DividerSpec
    r1: float
    r2: float
    r1_str: str
    r2_str: str

    @property
    def ratio(self) -> float:
        """The achieved ratio R2/(R1+R2)."""
        return self.r2 / (self.r1 + self.r2)

    @property
    def ratio_error(self) -> float:
        """Signed relative error of the achieved ratio vs its nominal."""
        nominal = self.spec.ratio.nominal
        assert nominal is not None  # noqa: S101 — __post_init__ fills it
        return (self.ratio - nominal) / nominal if nominal > 0 else 0.0

    @property
    def r_out(self) -> float:
        """The achieved Thévenin output impedance R1‖R2."""
        return self.r1 * self.r2 / (self.r1 + self.r2)

    @property
    def current(self) -> float:
        """The achieved standing current vcc/(R1+R2)."""
        return self.spec.vcc / (self.r1 + self.r2)

    def __str__(self) -> str:
        family = self.spec.r_out.family
        assert family is not None  # noqa: S101 — DividerSpec requires it
        r_out = format_value(self.r_out, family=family)
        return (
            f"{self.path}: {self.spec} → {self.r1_str}/{self.r2_str} "
            f"(ratio {self.ratio:.3f}, achieved {self.ratio_error:+.1%}; "
            f"R∥R {r_out}; I {self.current * 1e6:g} µA)"
        )


@dataclass
class SolveReport:
    """``solve``'s result: the error issues, evaluations, and resolutions."""

    issues: list[Issue] = field(default_factory=list)
    evaluations: list[GeneratorEvaluation] = field(default_factory=list)
    resolutions: list[Resolution | DividerResolution] = field(default_factory=list)

    def __str__(self) -> str:
        return "\n".join(
            [
                *(str(evaluation) for evaluation in self.evaluations),
                *(str(resolution) for resolution in self.resolutions),
            ]
        )


@dataclass(frozen=True)
class _PlacedPart:
    """One part plus the context a generator needs to read the circuit."""

    path: str
    part: Part
    circuit: Circuit
    ancestors: Mapping[int, tuple[Net, ...]]


def _divider_scope(path: str) -> str:
    """Return the owning capture's hierarchical path ('' at top level).

    A divider's two halves must be siblings in one capture, so the scope
    is part of the group key: a spec hoisted to a module or class
    constant then resolves one divider per instance instead of merging
    like-named halves across instances.
    """
    return path.rpartition("/")[0]


def solve(circuit: Circuit) -> SolveReport:
    """Resolve every value spec on the IR to a stocked literal.

    Generators evaluate first (in natural path order), then dividers
    resolve (grouped per capture, in natural path order of their top
    half), then single ``ValueRange`` specs (in natural path order);
    each pick joins the in-use set the consolidation tie-break consults
    (alongside the circuit's literal values), so repeated solves are
    deterministic and identical specs consolidate onto one stocked
    value; a second solve finds no specs and returns an empty report.
    Mutates the circuit in place and returns the report.
    """
    entries: list[_PlacedPart] = []
    _collect_parts(circuit, (), {}, entries, set())
    entries.sort(key=lambda entry: natural_key(entry.path))
    report = SolveReport()

    for entry in entries:
        if isinstance(entry.part.value, Generator):
            _evaluate_generator(entry, report)

    literals = [
        entry.part.value for entry in entries if isinstance(entry.part.value, str)
    ]
    in_use: dict[str, set[float]] = {}

    divider_groups: dict[tuple[str, int], dict[str, _PlacedPart]] = {}
    for entry in entries:
        value = entry.part.value
        if not isinstance(value, DividerHalf):
            continue
        group = divider_groups.setdefault(
            (_divider_scope(entry.path), id(value.spec)), {}
        )
        if value.role in group:
            report.issues.append(
                Issue(
                    Severity.ERROR,
                    f"{entry.path}: duplicate divider {value.role} for "
                    f"{value.spec} — one DividerSpec resolves one divider; "
                    "build a spec per divider",
                )
            )
            continue
        group[value.role] = entry

    def group_key(
        slots: dict[str, _PlacedPart],
    ) -> tuple[tuple[str | int, ...], str]:
        top = slots.get("top")
        path = (
            top.path
            if top is not None
            else min((present.path for present in slots.values()), key=natural_key)
        )
        return natural_key(path)

    for group in sorted(divider_groups.values(), key=group_key):
        _resolve_divider(group, literals, in_use, report)

    for entry in entries:
        if not isinstance(entry.part.value, ValueRange):
            continue
        _resolve_single(entry.path, entry.part, literals, in_use, report)

    return report


def _evaluate_generator(entry: _PlacedPart, report: SolveReport) -> None:
    """Evaluate one generator in place, recording its output or issue."""
    generator = entry.part.value
    assert isinstance(generator, Generator)  # noqa: S101 — caller filters
    context = _SolveContext(
        entry.path,
        entry.part,
        entry.circuit,
        entry.ancestors,
        generator.capture_nets,
    )
    try:
        produced = generator(context)
    except DefinitionError as error:
        report.issues.append(
            Issue(Severity.ERROR, f"{entry.path}: {generator} failed: {error}")
        )
        return
    if not isinstance(produced, str | ValueRange):
        report.issues.append(
            Issue(
                Severity.ERROR,
                f"{entry.path}: {generator} returned {produced!r}; a generator "
                "returns a value literal or a ValueRange",
            )
        )
        return
    entry.part.value = produced
    report.evaluations.append(GeneratorEvaluation(entry.path, generator, produced))


def _resolve_divider(
    group: dict[str, _PlacedPart],
    literals: list[str],
    in_use: dict[str, set[float]],
    report: SolveReport,
) -> None:
    """Resolve one divider group: one top and one bottom half, one pair."""
    top = group.get("top")
    bottom = group.get("bottom")
    if top is None or bottom is None:
        missing = "top" if top is None else "bottom"
        present = bottom if top is None else top
        assert present is not None  # noqa: S101 — a group holds at least one half
        report.issues.append(
            Issue(
                Severity.ERROR,
                f"{present.path}: divider missing its {missing} half",
            )
        )
        return
    top_path = top.path
    top_part = top.part
    bottom_part = bottom.part
    half = top_part.value
    assert isinstance(half, DividerHalf)  # noqa: S101 — grouped from halves
    spec = half.spec
    top_bin = top_part.value_bin
    if top_bin is None or top_bin != bottom_part.value_bin:
        report.issues.append(
            Issue(
                Severity.ERROR,
                f"{top_path}: divider halves need one shared value bin "
                "(a parts-DB record's bin declares the stocked grid)",
            )
        )
        return
    if top_bin.kind != "resistor":
        report.issues.append(
            Issue(
                Severity.ERROR,
                f"{top_path}: divider halves need a resistor bin, not "
                f"{top_bin.kind!r} (a DividerSpec is a resistive divider)",
            )
        )
        return
    used = in_use.setdefault(top_bin.kind, _parse_literals(literals, top_bin.kind))
    pair = top_bin.resolve_divider(spec, in_use=frozenset(used))
    if pair is None:
        report.issues.append(
            Issue(
                Severity.ERROR,
                f"{top_path}: no pair in the {top_bin.kind} bin "
                f"(E{top_bin.series}, "
                f"{format_value(top_bin.lo, family=top_bin.kind)}.."
                f"{format_value(top_bin.hi, family=top_bin.kind)}) "
                f"meets {spec}",
            )
        )
        return
    r1, r2 = pair
    r1_str = format_value(r1, family=top_bin.kind)
    r2_str = format_value(r2, family=top_bin.kind)
    top_part.value = r1_str
    bottom_part.value = r2_str
    used.add(r1)
    used.add(r2)
    report.resolutions.append(DividerResolution(top_path, spec, r1, r2, r1_str, r2_str))


def _resolve_single(
    path: str,
    part: Part,
    literals: list[str],
    in_use: dict[str, set[float]],
    report: SolveReport,
) -> None:
    """Resolve one ``ValueRange`` spec on a part against its bin."""
    spec = part.value
    assert isinstance(spec, ValueRange)  # noqa: S101 — caller filters
    value_bin = part.value_bin
    if value_bin is None:
        report.issues.append(
            Issue(
                Severity.ERROR,
                f"{path}: value spec {spec} but the part has no value bin "
                "(a parts-DB record's bin declares the stocked grid)",
            )
        )
        return
    used = in_use.setdefault(value_bin.kind, _parse_literals(literals, value_bin.kind))
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
        return
    chosen_str = format_value(chosen, family=value_bin.kind)
    part.value = chosen_str
    used.add(chosen)
    assert spec.nominal is not None  # noqa: S101 — ValueRange fills it
    rel_error = (chosen - spec.nominal) / spec.nominal if spec.nominal > 0 else 0.0
    report.resolutions.append(Resolution(path, spec, chosen, chosen_str, rel_error))


def _collect_parts(
    circuit: Circuit,
    prefix: tuple[str, ...],
    ancestors: Mapping[int, tuple[Net, ...]],
    out: list[_PlacedPart],
    seen: set[int],
) -> None:
    """Collect placed parts with their capture and binding chain.

    ``ancestors`` maps the current capture's nets (by identity) to the
    nets their ports bind in the enclosing captures, immediate parent
    first — the chain a generator's ``rail_voltage`` walks to find the
    supply a parent actually binds.
    """
    if id(circuit) in seen:
        return
    seen.add(id(circuit))
    out.extend(
        _PlacedPart("/".join((*prefix, ref)), part, circuit, ancestors)
        for ref, part in circuit.parts.items()
    )
    for instance in circuit.instances.values():
        child_ancestors: dict[int, tuple[Net, ...]] = {}
        for port_name, parent_net in instance.connections.items():
            child_port = instance.circuit.nets[port_name]
            child_ancestors[id(child_port)] = (
                parent_net,
                *ancestors.get(id(parent_net), ()),
            )
        _collect_parts(
            instance.circuit,
            (*prefix, instance.name),
            child_ancestors,
            out,
            seen,
        )


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
