"""Parametric value specs and stocked value bins (DESIGN.md §7).

A computed value — a divider ratio, a threshold — is a *spec*, never an
unsourcable irrational number: the capture states a :class:`ValueRange`
(target plus tolerance, or an acceptable range), and the solve pass
(:mod:`oparroy.dsl.solve`) resolves it to a literal from the part's
stocked :class:`ValueBin` — the E-series grid a parts-DB record
declares. Plain ``str`` literals stay accepted everywhere a spec is.

A value that depends on the circuit — the LED's series resistor, sized
from the rail it actually runs on — is a :class:`Generator`: a
capture-declared function the solve pass evaluates over the finished
IR, with a :class:`SolveContext` view of the part, its capture, and the
declared rail voltages (``Circuit.power_domain(..., voltage=...)``).
The returned literal or :class:`ValueRange` resolves like any authored
spec. Construction stays plain Python: the function runs as a pass
between capture and check, never interleaved with construction.

SI literals follow the house style: resistors use ``R``/``k``/``M``
with the letter as the decimal point (``R082`` = 0.082 Ω, ``0R`` = 0,
``4k7``, ``10k``) and plain digits below 1 kΩ (``470``); capacitors use
``p``/``n``/``u`` the same way (``15p``, ``4n7``, ``100n``, ``1u``).
Base units are ohms and farads; a bare number parses as base units.
Parsing and formatting are family-aware — the same letters mean
different things per quantity — so both take a ``family`` argument
(``"resistor"`` or ``"capacitor"``); there is no family-less parse.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Protocol

from oparroy.dsl.ir import DefinitionError

if TYPE_CHECKING:
    from oparroy.dsl.ir import Circuit, Net, Part

#: IEC 60063 preferred numbers, one decade each, for the E-series the
#: stocked bins draw from.
E12: tuple[float, ...] = (1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2)
E24: tuple[float, ...] = (
    1.0,
    1.1,
    1.2,
    1.3,
    1.5,
    1.6,
    1.8,
    2.0,
    2.2,
    2.4,
    2.7,
    3.0,
    3.3,
    3.6,
    3.9,
    4.3,
    4.7,
    5.1,
    5.6,
    6.2,
    6.8,
    7.5,
    8.2,
    9.1,
)
E96: tuple[float, ...] = (
    1.00,
    1.02,
    1.05,
    1.07,
    1.10,
    1.13,
    1.15,
    1.18,
    1.21,
    1.24,
    1.27,
    1.30,
    1.33,
    1.37,
    1.40,
    1.43,
    1.47,
    1.50,
    1.54,
    1.58,
    1.62,
    1.65,
    1.69,
    1.74,
    1.78,
    1.82,
    1.87,
    1.91,
    1.96,
    2.00,
    2.05,
    2.10,
    2.15,
    2.21,
    2.26,
    2.32,
    2.37,
    2.43,
    2.49,
    2.55,
    2.61,
    2.67,
    2.74,
    2.80,
    2.87,
    2.94,
    3.01,
    3.09,
    3.16,
    3.24,
    3.32,
    3.40,
    3.48,
    3.57,
    3.65,
    3.74,
    3.83,
    3.92,
    4.02,
    4.12,
    4.22,
    4.32,
    4.42,
    4.53,
    4.64,
    4.75,
    4.87,
    4.99,
    5.11,
    5.23,
    5.36,
    5.49,
    5.62,
    5.76,
    5.90,
    6.04,
    6.19,
    6.34,
    6.49,
    6.65,
    6.81,
    6.98,
    7.15,
    7.32,
    7.50,
    7.68,
    7.87,
    8.06,
    8.25,
    8.45,
    8.66,
    8.87,
    9.09,
    9.31,
    9.53,
    9.76,
)

_E_SERIES: dict[int, tuple[float, ...]] = {12: E12, 24: E24, 96: E96}

#: Family → SI letter → multiplier, in parse order. ``R`` is the
#: resistor family's decimal point for sub-unit values (``R082``).
_MULTIPLIERS: dict[str, dict[str, float]] = {
    "resistor": {"R": 1.0, "k": 1e3, "M": 1e6},
    "capacitor": {"p": 1e-12, "n": 1e-9, "u": 1e-6},
}

#: Family → (multiplier, letter) prefixes, largest first; the last
#: entry is the base unit and carries no letter.
_PREFIXES: dict[str, tuple[tuple[float, str], ...]] = {
    "resistor": ((1e6, "M"), (1e3, "k"), (1.0, "")),
    "capacitor": ((1e-6, "u"), (1e-9, "n"), (1e-12, "p")),
}

_MANTISSA_RE = re.compile(r"\d+\.?\d*|\.\d+")

#: Relative slack on range-boundary comparisons — spec and bin bounds
#: are decimal values riding binary floats.
_EPS = 1e-9


def parse_value(text: str, *, family: str) -> float:
    """Parse a house-style SI literal into base units (ohms or farads).

    The family's letters act as decimal points (``4k7`` → 4700,
    ``R082`` → 0.082); a bare number is base units. A letter from the
    other family, or anything malformed, raises ``DefinitionError``.

    >>> parse_value("10k", family="resistor")
    10000.0
    >>> parse_value("R082", family="resistor")
    0.082
    >>> parse_value("4u7", family="capacitor")
    4.7e-06
    >>> parse_value("1n", family="capacitor")
    1e-09
    """
    letters = _family(family, _MULTIPLIERS)
    multiplier = 1.0
    mantissa_text = text
    for letter, letter_multiplier in letters.items():
        if letter in text:
            mantissa_text = text.replace(letter, ".")
            multiplier = letter_multiplier
            break
    if not _MANTISSA_RE.fullmatch(mantissa_text):
        msg = f"malformed {family} value {text!r}"
        raise DefinitionError(msg)
    return float(mantissa_text) * multiplier


def format_value(value: float, *, family: str) -> str:
    """Format base units as a house-style SI literal.

    The inverse of :func:`parse_value`: the prefix scales the mantissa
    into [1, 1000), an integer mantissa renders as plain digits, and a
    fractional one renders with the prefix letter as the decimal point
    (``R`` for sub-unit resistors).

    >>> format_value(10000.0, family="resistor")
    '10k'
    >>> format_value(4700.0, family="resistor")
    '4k7'
    >>> format_value(0.082, family="resistor")
    'R082'
    >>> format_value(1e-07, family="capacitor")
    '100n'
    """
    prefixes = _family(family, _PREFIXES)
    if value < 0:
        msg = f"negative {family} value {value}"
        raise DefinitionError(msg)
    if value == 0:
        return "0R" if family == "resistor" else "0p"
    multiplier, letter = prefixes[-1]
    for candidate in prefixes:
        if value >= candidate[0]:
            multiplier, letter = candidate
            break
    text = f"{value / multiplier:.6g}"
    if "." not in text:
        return text + letter
    sep = letter or "R"
    return text.removeprefix("0").replace(".", sep)


def _family[T](family: str, table: dict[str, T]) -> T:
    """Return the family row, or raise — there is no family-less value."""
    try:
        return table[family]
    except KeyError:
        msg = f"unknown value family {family!r} (expected one of {sorted(table)})"
        raise DefinitionError(msg) from None


@dataclass(frozen=True)
class ValueRange:
    """A value spec: an acceptable range plus a nominal to aim for.

    ``lo``/``hi`` bound what is acceptable (base units); ``nominal`` is
    the tie-break target and the achieved-error reference — defaulted
    to the geometric midrange, the E-series grid's own log spacing.
    ``family`` is the quantity the spec is about
    (``"resistor"``/``"capacitor"``); it renders ``__str__`` and parses
    ``around`` targets, nothing more.

    >>> str(ValueRange.around("10k", 0.05, family="resistor"))
    '10k ±5%'
    """

    lo: float
    hi: float
    nominal: float | None = None
    family: str | None = None

    def __post_init__(self) -> None:
        if self.family is not None:
            _family(self.family, _MULTIPLIERS)
        nominal = self.nominal
        if nominal is None:
            nominal = math.sqrt(self.lo * self.hi) if self.lo > 0 else self.hi / 2
            object.__setattr__(self, "nominal", nominal)
        if not 0 <= self.lo <= nominal <= self.hi:
            msg = (
                f"value spec must satisfy 0 <= lo <= nominal <= hi, "
                f"got lo={self.lo}, nominal={nominal}, hi={self.hi}"
            )
            raise DefinitionError(msg)

    @classmethod
    def around(
        cls, target: float | str, tol: float, *, family: str | None = None
    ) -> ValueRange:
        """Build the spec ``target ± tol`` (tol a fraction: 0.05 = 5%).

        A string target is a house-style SI literal and needs
        ``family=`` to parse.
        """
        if not 0 <= tol < 1:
            msg = f"tolerance must be a fraction in [0, 1), got {tol}"
            raise DefinitionError(msg)
        if isinstance(target, str):
            if family is None:
                msg = f"parsing the value string {target!r} needs a family="
                raise DefinitionError(msg)
            nominal = parse_value(target, family=family)
        else:
            nominal = float(target)
        return cls(nominal * (1 - tol), nominal * (1 + tol), nominal, family)

    def __str__(self) -> str:
        assert self.nominal is not None  # noqa: S101 — __post_init__ fills it
        if self.nominal > 0:
            up = self.hi / self.nominal - 1
            down = 1 - self.lo / self.nominal
            if math.isclose(up, down, rel_tol=_EPS):
                return f"{self._fmt(self.nominal)} ±{up * 100:g}%"
        return f"{self._fmt(self.lo)}..{self._fmt(self.hi)}"

    def _fmt(self, value: float) -> str:
        if self.family is not None:
            return format_value(value, family=self.family)
        return f"{value:.6g}"


class SolveContext(Protocol):
    """The finished-IR view a :class:`Generator` computes from.

    ``solve`` supplies one per evaluation, scoped to the part's owning
    capture. ``path``/``part`` are the generating part, ``circuit`` is
    the capture that holds it, and ``rail_voltage`` looks up a declared
    rail voltage (``Circuit.power_domain(..., voltage=...)``), following
    instance bindings outward first: the supply a parent actually binds
    is the actual rail, and the rail's own declaration is the
    standalone fallback. The circuit is a read-only view by contract —
    a generator that mutates it breaks the pass's determinism.
    """

    @property
    def path(self) -> str:
        """The generating part's hierarchical path."""
        ...

    @property
    def part(self) -> Part:
        """The part being sized."""
        ...

    @property
    def circuit(self) -> Circuit:
        """The capture that owns the part — a read-only view."""
        ...

    def rail_voltage(self, net: Net | str) -> ValueRange | None:
        """Return ``net``'s declared rail voltage, or None when undeclared.

        A string is a net name in the part's own capture. Following the
        binding chain outward first means a block sizes from the rail
        its parent supplies, not from the voltage it assumes standalone.
        """
        ...


@dataclass(frozen=True)
class Generator:
    """A context-computed value spec: a capture-declared function.

    ``fn`` receives a :class:`SolveContext` built over the finished IR
    and returns a literal or a :class:`ValueRange`; the solve pass
    evaluates it in place before bin resolution, so a generated
    ``ValueRange`` reports its achieved error against the spec like any
    authored one. The function runs as a pass between capture and
    check, never interleaved with construction (DESIGN.md §7): a
    generator reads circuit context, it does not wire parts. A
    generator names nets in its authored capture; ``flatten`` remaps
    that name map onto the flat nets, so it still resolves after the
    instrumentation pass flattens a tile's subcircuits.
    """

    fn: Callable[[SolveContext], str | ValueRange]
    #: The authored capture's name → net map (frozen at the moment a
    #: subcircuit folds into its parent), so a name-based generator
    #: still resolves its local nets after flattening. Pass machinery
    #: attaches it; capture code leaves it None.
    capture_nets: Mapping[str, Net] | None = field(
        default=None, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if not callable(self.fn):
            msg = f"a Generator needs a callable, got {self.fn!r}"
            raise DefinitionError(msg)

    def remapped(
        self,
        net_map: Mapping[Net, Net],
        authored_nets: Mapping[str, Net],
    ) -> Generator:
        """Return a copy whose capture nets follow a flatten.

        ``net_map`` is flatten's old-net → flat-net table; ``authored``
        is the capture being flattened's name → net map, used when this
        generator was authored there. A generator from a deeper capture
        keeps its deepest authored map, remapped into the new flat
        circuit. Pass machinery only.
        """
        source = self.capture_nets if self.capture_nets is not None else authored_nets
        return replace(
            self,
            capture_nets={name: net_map.get(net, net) for name, net in source.items()},
        )

    def __call__(self, context: SolveContext) -> str | ValueRange:
        """Return the wrapped function's value for ``context``."""
        return self.fn(context)

    def __str__(self) -> str:
        name = getattr(self.fn, "__name__", None) or type(self.fn).__name__
        return f"<generator {name}>"


@dataclass(frozen=True)
class DividerSpec:
    """A VDD → R1 → out → R2 → GND divider, met by one stocked bin pair.

    The three joint constraints the solve pass meets with a single
    (R1, R2) pair drawn from the part's :class:`ValueBin`:
    - ``ratio`` — R2/(R1+R2), the output fraction (dimensionless);
    - ``r_out`` — R1‖R2, the Thévenin output impedance (base units);
    - ``vcc``/``i_max`` — the standing-current bound: the pair must
      satisfy R1+R2 ≥ vcc / i_max.

    ``ratio`` and ``r_out`` each carry a nominal (``ValueRange``'s) the
    resolver aims at; ``top()``/``bottom()`` build the two per-part
    markers the capture places on the sibling resistors. One spec
    resolves one divider: the halves must be siblings in the same
    capture and share that spec object, and a second divider needs its
    own spec. Grouping keys on that capture, so a spec hoisted to a
    module or class constant is safe across instances of a reusable
    subcircuit.

    >>> str(DividerSpec(ValueRange.around(0.5, 0.05),
    ...                 ValueRange.around("5k", 0.2, family="resistor"),
    ...                 3.3, 330e-6))
    'divider 0.5 ±5%, R∥R 5k ±20%, I ≤ 330 µA @ 3.3 V'
    """

    ratio: ValueRange
    r_out: ValueRange
    vcc: float
    i_max: float

    def __post_init__(self) -> None:
        if not (self.ratio.lo > 0.0 and self.ratio.hi < 1.0):
            msg = f"divider ratio must lie inside (0, 1), got {self.ratio}"
            raise DefinitionError(msg)
        if self.ratio.family is not None:
            msg = f"divider ratio is dimensionless, got family {self.ratio.family!r}"
            raise DefinitionError(msg)
        if math.isnan(self.vcc) or self.vcc <= 0:
            msg = f"divider vcc must be positive, got {self.vcc}"
            raise DefinitionError(msg)
        if math.isnan(self.i_max) or self.i_max <= 0:
            msg = f"divider i_max must be positive, got {self.i_max}"
            raise DefinitionError(msg)
        if self.r_out.family != "resistor":
            msg = f"divider r_out is a resistance, got family {self.r_out.family!r}"
            raise DefinitionError(msg)

    def top(self) -> DividerHalf:
        """Build the VCC-side resistor's marker (R1), placed ``a=vcc, b=out``."""
        return DividerHalf(self, "top")

    def bottom(self) -> DividerHalf:
        """Build the GND-side resistor's marker (R2), placed ``a=out, b=gnd``."""
        return DividerHalf(self, "bottom")

    def __str__(self) -> str:
        return (
            f"divider {self.ratio}, R∥R {self.r_out}, "
            f"I ≤ {self.i_max * 1e6:g} µA @ {self.vcc:g} V"
        )


@dataclass(frozen=True)
class DividerHalf:
    """One resistor of a divider, awaiting joint resolution.

    ``spec`` is the joint :class:`DividerSpec` the two sibling halves
    share within one capture; ``role`` is ``"top"`` (VCC side, R1) or
    ``"bottom"`` (GND side, R2) — the capture author's claim, which
    nothing here verifies, so a swapped marker inverts the achieved
    ratio. The solve pass groups the two halves by their shared spec
    object and resolves them together; a half surviving to ``check`` or
    a netlist emitter is rejected there, like a ``ValueRange``.
    """

    spec: DividerSpec
    role: str

    def __post_init__(self) -> None:
        if self.role not in ("top", "bottom"):
            msg = f"divider role must be 'top' or 'bottom', got {self.role!r}"
            raise DefinitionError(msg)

    def __str__(self) -> str:
        return f"divider {self.role} ({self.spec})"


def _within(lo: float, value: float, hi: float) -> bool:
    """Return True when ``value`` lies in [lo, hi], bounds given slack."""
    return lo * (1 - _EPS) <= value <= hi * (1 + _EPS)


def _relative_error(actual: float, nominal: float) -> float:
    """Absolute relative error, degrading to absolute at a zero nominal."""
    if nominal == 0:
        return abs(actual - nominal)
    return abs(actual - nominal) / nominal


def _divider_ratio(pair: tuple[float, float]) -> float:
    """Return the ratio R2/(R1+R2) of an (R1, R2) divider pair."""
    return pair[1] / (pair[0] + pair[1])


def _divider_r_out(pair: tuple[float, float]) -> float:
    """Return the Thévenin output impedance R1‖R2 of an (R1, R2) pair."""
    return pair[0] * pair[1] / (pair[0] + pair[1])


@dataclass(frozen=True)
class ValueBin:
    """A stocked value grid: one E-series within bounds (base units).

    ``kind`` is the quantity family (``"resistor"``/``"capacitor"``),
    ``series`` the IEC 60063 E-series (12/24/96), ``tolerance`` the
    bin's nominal part tolerance — informational; the achieved error of
    a pick is the solve pass's report. ``lo``/``hi`` bound what the
    assembler stocks.
    """

    kind: str
    series: int
    tolerance: float
    lo: float
    hi: float

    def __post_init__(self) -> None:
        _family(self.kind, _MULTIPLIERS)
        if self.series not in _E_SERIES:
            msg = (
                f"unknown E-series E{self.series} (expected one of {sorted(_E_SERIES)})"
            )
            raise DefinitionError(msg)
        if not 0 < self.lo <= self.hi:
            msg = (
                f"bin bounds must satisfy 0 < lo <= hi, got lo={self.lo}, hi={self.hi}"
            )
            raise DefinitionError(msg)

    def values(self) -> tuple[float, ...]:
        """Every series value within the stocked bounds, ascending.

        >>> ValueBin("resistor", 12, 0.05, 10.0, 100.0).values()
        (10.0, 12.0, 15.0, 18.0, 22.0, 27.0, 33.0, 39.0, 47.0, 56.0, 68.0, 82.0, 100.0)
        """
        base = _E_SERIES[self.series]
        first = math.floor(math.log10(self.lo)) - 1
        last = math.ceil(math.log10(self.hi)) + 1
        return tuple(
            sorted(
                {
                    mantissa * 10**decade
                    for decade in range(first, last + 1)
                    for mantissa in base
                    if self.lo * (1 - _EPS)
                    <= mantissa * 10**decade
                    <= self.hi * (1 + _EPS)
                }
            )
        )

    def resolve(
        self, spec: ValueRange, *, in_use: frozenset[float] = frozenset()
    ) -> float | None:
        """Pick the stocked value meeting ``spec`` nearest its nominal.

        Candidates are the bin's values inside the spec's range; None
        when none meet it. Ties on relative error prefer a value
        already used elsewhere in the circuit (``in_use`` — BOM
        consolidation), then the smaller value: deterministic.
        """
        candidates = [
            value
            for value in self.values()
            if spec.lo * (1 - _EPS) <= value <= spec.hi * (1 + _EPS)
        ]
        if not candidates:
            return None
        assert spec.nominal is not None  # noqa: S101 — __post_init__ fills it
        nominal = spec.nominal

        def rel_error(value: float) -> float:
            if nominal == 0:
                return abs(value - nominal)
            return abs(value - nominal) / nominal

        best_error = min(rel_error(value) for value in candidates)
        best = [
            value
            for value in candidates
            if math.isclose(rel_error(value), best_error, rel_tol=_EPS)
        ]
        used = [value for value in best if value in in_use]
        return min(used or best)

    def resolve_divider(
        self, spec: DividerSpec, *, in_use: frozenset[float] = frozenset()
    ) -> tuple[float, float] | None:
        """Pick the stocked (R1, R2) pair meeting ``spec``'s constraints.

        R1 is the VCC-side (top) resistor, R2 the GND-side (bottom):
        ratio R2/(R1+R2), R1‖R2, and R1+R2 ≥ vcc/i_max must all hold.
        Among the pairs that meet them, the pick minimizes the ratio's
        relative error to its nominal, then R1‖R2's, then prefers values
        already in use (BOM consolidation), then the smaller
        (R1+R2, R1) — deterministic. None when no pair meets.
        """
        candidates = self._divider_candidates(spec)
        if not candidates:
            return None
        assert spec.ratio.nominal is not None  # noqa: S101 — __post_init__ fills it
        assert spec.r_out.nominal is not None  # noqa: S101 — __post_init__ fills it
        ratio_nominal = spec.ratio.nominal
        r_out_nominal = spec.r_out.nominal
        best_ratio = min(
            _relative_error(_divider_ratio(pair), ratio_nominal) for pair in candidates
        )
        candidates = [
            pair
            for pair in candidates
            if math.isclose(
                _relative_error(_divider_ratio(pair), ratio_nominal),
                best_ratio,
                rel_tol=_EPS,
            )
        ]
        best_r_out = min(
            _relative_error(_divider_r_out(pair), r_out_nominal) for pair in candidates
        )
        candidates = [
            pair
            for pair in candidates
            if math.isclose(
                _relative_error(_divider_r_out(pair), r_out_nominal),
                best_r_out,
                rel_tol=_EPS,
            )
        ]
        best_used = max(
            sum(1 for value in pair if value in in_use) for pair in candidates
        )
        candidates = [
            pair
            for pair in candidates
            if sum(1 for value in pair if value in in_use) == best_used
        ]
        return min(candidates, key=lambda pair: (pair[0] + pair[1], pair[0]))

    def _divider_candidates(self, spec: DividerSpec) -> list[tuple[float, float]]:
        """Every (R1, R2) bin pair meeting the ratio, R‖R, and current bounds."""
        series_min = spec.vcc / spec.i_max
        candidates: list[tuple[float, float]] = []
        for r1 in self.values():
            for r2 in self.values():
                pair = (r1, r2)
                if not _within(spec.ratio.lo, _divider_ratio(pair), spec.ratio.hi):
                    continue
                if not _within(spec.r_out.lo, _divider_r_out(pair), spec.r_out.hi):
                    continue
                if r1 + r2 < series_min * (1 - _EPS):
                    continue
                candidates.append(pair)
        return candidates
