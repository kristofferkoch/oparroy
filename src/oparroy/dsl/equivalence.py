"""The reset-state equivalence proof: instrumented board ≡ plain board + residuals.

The CI board is the plain capture plus declared instrumentation
transforms (:mod:`oparroy.dsl.transform`); this pass proves the
instrumented board **in reset state** is equivalent to the plain board
up to an enumerated, budgeted set of residuals — "almost equivalent"
is exactly that set (``docs/instrumentation-equivalence.md``
§2). The inputs are the two captures plus the same transform ``plan``
handed to ``apply_transforms``: the :class:`Provenance` tags classify
every part and net (transform-created vs base — no name-matching
heuristics), and the plan supplies the role declarations the tags
deliberately do not carry — which escaped port is a control, which a
substitute source, which nets are declared taps.

The proof runs per tile and composes upward (memo Q5), so findings
report tile-local paths (``T3/ka``). Per tile:

1. **Series elements reduce to wires in reset state.** Every
   ``InsertSeries``/``Substitute`` part drops out and its cut sides
   merge back onto the base net; every ``AddShunt`` branch is absent.
   Reset levels are proof *inputs* (memo Q2): ``reset_levels`` carries
   the control plane's silicon power-on state per control port, keyed
   like the transform handles — a control without a declared level, or
   one whose level is not the plain-board state (the §8 bit-0
   invariant: the reset load is all-zeros), is an error, never assumed.
   A control-less series insert reduces unconditionally — it declared
   itself pass-through at capture.
2. **Taps are high-impedance.** A pin the instrumented board adds to a
   base net is legitimate only through a declared ``AddTap``, and its
   ``PinType`` must be input-class — nothing a tap adds can drive the
   net.
3. **Bijection over the base.** Every base part and base-net pin
   membership survives the reduction — nothing lost, nothing
   re-connected, and no untagged part may appear inside a tile
   (instrumentation is transforms only, never capture edits). Extra
   board-level parts are the scan plane and supervisor — allowed.
4. **Residuals are enumerated, not assumed away.** Each reduced
   element's electrical magnitudes come from the parts DB (memo Q3:
   ``Residuals`` on the typed part, threaded onto the placed part);
   geometry residuals (tap stub capacitance) are
   emitted as layout-checker obligations, bounded here, discharged by
   the §7 layout checker. Every residual must carry a budget citation
   (the residual register, ``docs/instrumented-ci.md`` §9);
   one without is an error.

What this proof is not (memo §3): not a spice equivalence, not a proof
of the injected states (those are *supposed* to differ), not layout
equivalence. Output mirrors :mod:`oparroy.dsl.check`: findings are
``Issue``/``Severity`` and the capture's waivers apply.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from oparroy.dsl.check import Issue, Severity, _apply_waivers
from oparroy.dsl.ir import (
    Circuit,
    Net,
    Part,
    PinType,
    TileNet,
    hierarchical_waivers,
    natural_key,
)
from oparroy.dsl.transform import (
    AddShunt,
    AddTap,
    PerTile,
    Substitute,
    _lookup_instance,
    _matches,
    _walk_instances,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from oparroy.dsl.ir import Instance, Residuals
    from oparroy.dsl.transform import Scope, Transform

#: Check id of the equivalence findings; waivers address it.
EQUIVALENCE = "equivalence"

#: Residual kinds — the budget register's keys (``budgets`` maps them
#: to citations).
SERIES_ON_RESISTANCE = "series-on-resistance"
SWITCH_CAPACITANCE = "switch-capacitance"
SHUNT_OFF_CAPACITANCE = "shunt-off-capacitance"
LEAKAGE = "leakage"
EXTRA_LOADING = "extra-loading"
TAP_CAPACITANCE = "tap-capacitance"

_INPUT_CLASS = frozenset({PinType.INPUT, PinType.TRI_STATE})


@dataclass(frozen=True)
class Residual:
    """One enumerated reset-state difference from the plain board.

    ``net`` is the flattened base-net name the residual loads, ``kind``
    one of the module constants, ``magnitude`` the parts-DB number
    (memo Q3), ``citation`` the budget-register entry — None is
    precisely the error case. ``layout_obligation`` marks geometry
    residuals the netlist can only bound: the §7 layout checker
    discharges them (the §6 short-stub contract).

    >>> Residual("T0/TX_A", SERIES_ON_RESISTANCE, "25.0 Ω", "§2 tb_decode").net
    'T0/TX_A'
    """

    net: str
    kind: str
    magnitude: str
    citation: str | None
    layout_obligation: bool = False


@dataclass(frozen=True)
class EquivalenceReport:
    """The proof's output: the findings plus the enumerated residual set.

    ``issues`` mirrors ``check.py``'s list (waivers applied);
    ``residuals`` is the full enumerated set — "almost equivalent" is
    exactly these — including any whose missing citation errored.
    """

    issues: tuple[Issue, ...]
    residuals: tuple[Residual, ...]


def check_equivalent(
    base: Circuit,
    instrumented: Circuit,
    plan: Sequence[Scope],
    *,
    reset_levels: Mapping[TileNet, int],
    budgets: Mapping[str, str],
) -> EquivalenceReport:
    """Prove ``instrumented`` in reset state reduces to ``base``, modulo residuals.

    The plan must already be applied to ``instrumented`` via
    ``apply_transforms``; both circuits are flattened internally.
    ``reset_levels`` maps each control port's :class:`TileNet` — the
    transform handles' key — to the control plane's power-on bit; every
    declared control must appear at level 0 (the §8 all-zeros reset
    load). ``budgets`` maps residual kind to its budget citation; a
    residual whose kind has no entry is an error, and an entry matching
    no residual warns as stale. Waivers come from the instrumented
    capture (``Circuit.waive``), as in ``check``.
    """
    tiles = _tile_transforms(instrumented, plan)
    base_names = _base_net_names(base)
    base_flat = base.flatten()
    flat = instrumented.flatten()
    issues: list[Issue] = []
    drop_nets, seen_levels = _check_reset_levels(flat, tiles, reset_levels, issues)
    tap_names = _declared_tap_nets(instrumented, tiles, base_names, issues)
    residuals = _enumerate_residuals(
        flat, tiles, budgets, base_names=base_names, tap_names=tap_names, issues=issues
    )
    _check_base_bijection(
        base_flat,
        flat,
        base_names=base_names,
        drop_nets=drop_nets,
        tap_nets=set(tap_names.values()),
        issues=issues,
    )
    issues.extend(
        Issue(Severity.WARNING, f"budget {kind!r} matches no residual — stale")
        for kind in sorted(set(budgets) - {r.kind for r in residuals})
    )
    issues.extend(
        Issue(
            Severity.WARNING,
            f"reset level {'/'.join(key.path)}/{key.name} matches no "
            "control net — stale",
        )
        for key in sorted(set(reset_levels) - seen_levels)
    )
    waivers = tuple(hierarchical_waivers(instrumented))
    return EquivalenceReport(tuple(_apply_waivers(issues, waivers)), tuple(residuals))


def _tile_transforms(
    circuit: Circuit, plan: Sequence[Scope]
) -> dict[tuple[str, ...], list[Transform]]:
    """Resolve the plan's scopes to per-tile transform lists (memo Q5)."""
    tiles: dict[tuple[str, ...], list[Transform]] = {}
    for scope in plan:
        if isinstance(scope, PerTile):
            for path, inst in _walk_instances(circuit, ()):
                if _matches(inst, scope.subcircuit):
                    tiles.setdefault(path, []).extend(scope.transforms)
        else:
            tiles.setdefault(scope.path, []).extend(scope.transforms)
    return tiles


def _base_net_names(circuit: Circuit) -> dict[TileNet, str]:
    """Map each base-capture net's :class:`TileNet` to its flattened name.

    Computed from the hierarchical base capture: internal nets gain the
    instance-path prefix, bound ports take the parent net's name — the
    naming flattening produces, so a tagged instrumented net's
    ``Provenance.base`` resolves to the base net's flattened name.
    """
    out: dict[TileNet, str] = {}
    _name_base_nets(circuit, (), {}, {}, out)
    return out


def _name_base_nets(
    circuit: Circuit,
    path: tuple[str, ...],
    connections: Mapping[str, Net],
    named: dict[int, str],
    out: dict[TileNet, str],
) -> None:
    prefix = "/".join(path)
    for name, net in circuit.nets.items():
        if net.is_port and name in connections:
            # A bound port takes the parent net's name — and a deeper
            # instance bound straight to this port resolves to the same
            # name, so the port itself must be recorded too (flatten
            # keeps bound ports in its nets map for the same reason).
            flat_name = named[id(connections[name])]
            out[TileNet(path, name)] = flat_name
            named[id(net)] = flat_name
        else:
            flat_name = f"{prefix}/{name}" if prefix else name
            out[TileNet(path, name)] = flat_name
            named[id(net)] = flat_name
    for inst in circuit.instances.values():
        _name_base_nets(inst.circuit, (*path, inst.name), inst.connections, named, out)


def _issue(message: str, path: str) -> Issue:
    return Issue(Severity.ERROR, message, check=EQUIVALENCE, path=path)


def _escaped_ports(transform: Transform) -> list[tuple[str, str]]:
    """Return the (role, port) pairs a transform escapes: control and source."""
    ports = []
    if not isinstance(transform, AddTap):
        if transform.control is not None:
            ports.append(("control", transform.control))
        if isinstance(transform, Substitute):
            ports.append(("source", transform.source))
    return ports


def _check_reset_levels(
    flat: Circuit,
    tiles: dict[tuple[str, ...], list[Transform]],
    reset_levels: Mapping[TileNet, int],
    issues: list[Issue],
) -> tuple[set[str], set[TileNet]]:
    """Check control-net power-on levels; return the drop set and seen keys.

    The drop set is the escaped control and substitute-source nets: in
    reset state the parts they steer sit in pass-through, so these nets
    are absent from the reduced circuit. The levels themselves are
    proof inputs (memo Q2) — the 74HC595-class stage's silicon power-on
    state (``docs/instrumented-ci.md`` §8), never assumed.
    """
    drop: set[str] = set()
    seen: set[TileNet] = set()
    for path in sorted(tiles):
        prefix = "/".join(path)
        for transform in tiles[path]:
            for role, port in _escaped_ports(transform):
                name = f"{prefix}/{port}"
                drop.add(name)
                net = flat.nets.get(name)
                if net is None or net.provenance is None:
                    issues.append(
                        _issue(
                            f"transform {transform.label!r}: {role} net "
                            f"{name!r} missing or untagged — was the plan "
                            "applied?",
                            name,
                        )
                    )
                elif role == "control":
                    key = TileNet(path, port)
                    seen.add(key)
                    _check_level(name, key, reset_levels, issues)
    return drop, seen


def _check_level(
    name: str,
    key: TileNet,
    reset_levels: Mapping[TileNet, int],
    issues: list[Issue],
) -> None:
    """Require one control net's declared power-on level: the all-zeros load."""
    level = reset_levels.get(key)
    if level is None:
        issues.append(
            _issue(
                f"{name}: no reset level declared — control-plane power-on "
                "levels are proof inputs (memo Q2), never assumed",
                name,
            )
        )
    elif level != 0:
        issues.append(
            _issue(
                f"{name}: reset level {level} — the §8 POR invariant is "
                "bit 0 = plain-board state; reset would not be the "
                "pass-through",
                name,
            )
        )


def _declared_tap_nets(
    board: Circuit,
    tiles: dict[tuple[str, ...], list[Transform]],
    base_names: dict[TileNet, str],
    issues: list[Issue],
) -> dict[TileNet, str]:
    """Map each declared ``AddTap`` to the flattened base net it legitimates.

    The bound net is looked up by the tap's full name first — the sides
    of a split internal net (``sense#a``) bind under their literal
    names — falling back to the ``#``-stripped name for a port-split
    alias (``TX#b``, whose port keeps the unsuffixed name). A tagged
    bound net (a tap on a tile-internal net) resolves through its
    provenance to the base net's flattened name; an untagged one (a
    tap on a port) is already a base net.
    """
    taps: dict[TileNet, str] = {}
    for path in sorted(tiles):
        inst: Instance = _lookup_instance(board, path)
        for transform in tiles[path]:
            if not isinstance(transform, AddTap):
                continue
            local = transform.net
            bound = inst.connections.get(local)
            if bound is None and "#" in local:
                bound = inst.connections.get(local.split("#")[0])
            if bound is None:
                issues.append(
                    _issue(
                        f"transform {transform.label!r}: tap net {local!r} is "
                        f"not bound at {'/'.join(path)} — was the plan "
                        "applied?",
                        "/".join(path),
                    )
                )
                continue
            if bound.provenance is None:
                taps[TileNet(path, transform.net)] = bound.name
                continue
            key = TileNet(path, bound.provenance.base.split("/")[-1])
            name = base_names.get(key)
            if name is None:
                issues.append(
                    _issue(
                        f"transform {transform.label!r}: tap net "
                        f"{bound.name!r} derives from "
                        f"{bound.provenance.base!r}, which is not a "
                        "base-capture net",
                        bound.name,
                    )
                )
                continue
            taps[TileNet(path, transform.net)] = name
    return taps


def _residual_net(
    path: tuple[str, ...],
    net: str,
    base_names: dict[TileNet, str],
) -> str:
    """Return the flattened base-net name a residual loads (``Residual.net``).

    ``net`` is the transform's tile-local handle; a split side
    (``TX#b``) loads the same base net as the net it was cut from. The
    fallback covers a drifted capture — the bijection reports it.
    """
    local = net.split("#", maxsplit=1)[0]
    return base_names.get(TileNet(path, local), f"{'/'.join(path)}/{local}")


def _enumerate_residuals(  # noqa: PLR0913 — the enumeration context threaded through
    flat: Circuit,
    tiles: dict[tuple[str, ...], list[Transform]],
    budgets: Mapping[str, str],
    *,
    base_names: dict[TileNet, str],
    tap_names: Mapping[TileNet, str],
    issues: list[Issue],
) -> list[Residual]:
    """Emit the residual set; a residual without a budget citation errors."""
    residuals: list[Residual] = []
    for path in sorted(tiles):
        prefix = "/".join(path)
        for transform in tiles[path]:
            if isinstance(transform, AddTap):
                tap_net = tap_names.get(TileNet(path, transform.net))
                if tap_net is not None:
                    residuals.append(
                        Residual(
                            tap_net,
                            TAP_CAPACITANCE,
                            "stub geometry — bounded, not known (memo Q3)",
                            budgets.get(TAP_CAPACITANCE),
                            layout_obligation=True,
                        )
                    )
                continue
            base_net = _residual_net(path, transform.net, base_names)
            placed = flat.parts.get(f"{prefix}/{transform.part.ref}")
            if placed is None or placed.provenance is None:
                issues.append(
                    _issue(
                        f"transform {transform.label!r}: part "
                        f"{prefix}/{transform.part.ref} missing or untagged — "
                        "was the plan applied?",
                        prefix,
                    )
                )
                continue
            if placed.residuals is None:
                issues.append(
                    _issue(
                        f"{placed.ref} carries no residual data — electrical "
                        "magnitudes are parts-DB attributes (memo Q3)",
                        placed.ref,
                    )
                )
            else:
                residuals.extend(
                    _part_residuals(transform, base_net, placed.residuals, budgets)
                )
            for extra in transform.extra:
                _extra_residual(
                    flat,
                    prefix=prefix,
                    base_net=base_net,
                    ref=extra.ref,
                    budgets=budgets,
                    issues=issues,
                    residuals=residuals,
                )
    issues.extend(
        _issue(
            f"residual {residual.kind} on {residual.net!r} has no "
            "budget citation — enumerate it in the residual register "
            "(instrumented-ci §9)",
            residual.net,
        )
        for residual in residuals
        if residual.citation is None
    )
    return residuals


def _extra_residual(  # noqa: PLR0913 — the enumeration context threaded through
    flat: Circuit,
    *,
    prefix: str,
    base_net: str,
    ref: str,
    budgets: Mapping[str, str],
    issues: list[Issue],
    residuals: list[Residual],
) -> None:
    """Enumerate an auxiliary part's loading of the base net (a pull-down)."""
    placed = flat.parts.get(f"{prefix}/{ref}")
    if placed is None or placed.provenance is None:
        issues.append(
            _issue(
                f"transform part {prefix}/{ref} missing or untagged — "
                "was the plan applied?",
                prefix,
            )
        )
        return
    if placed.value is None:
        issues.append(
            _issue(
                f"{placed.ref} loads {base_net!r} but carries no value — "
                "the residual cannot be enumerated",
                placed.ref,
            )
        )
        return
    residuals.append(
        Residual(base_net, EXTRA_LOADING, placed.value, budgets.get(EXTRA_LOADING))
    )


def _part_residuals(
    transform: Transform,
    base_net: str,
    residuals: Residuals,
    budgets: Mapping[str, str],
) -> list[Residual]:
    """One placed part's residuals, from its parts-DB electrical data."""
    out: list[Residual] = []
    if isinstance(transform, AddShunt):
        # The branch is absent in reset state: only off-state residuals.
        if residuals.off_capacitance_pf is not None:
            out.append(
                Residual(
                    base_net,
                    SHUNT_OFF_CAPACITANCE,
                    f"{residuals.off_capacitance_pf} pF",
                    budgets.get(SHUNT_OFF_CAPACITANCE),
                )
            )
    else:
        if residuals.on_resistance_ohm is not None:
            out.append(
                Residual(
                    base_net,
                    SERIES_ON_RESISTANCE,
                    f"{residuals.on_resistance_ohm} Ω",
                    budgets.get(SERIES_ON_RESISTANCE),
                )
            )
        capacitance = [
            f"{value} pF {label}"
            for value, label in (
                (residuals.on_capacitance_pf, "on"),
                (residuals.off_capacitance_pf, "off"),
            )
            if value is not None
        ]
        if capacitance:
            out.append(
                Residual(
                    base_net,
                    SWITCH_CAPACITANCE,
                    " / ".join(capacitance),
                    budgets.get(SWITCH_CAPACITANCE),
                )
            )
    if residuals.leakage_ua is not None:
        out.append(
            Residual(
                base_net,
                LEAKAGE,
                f"{residuals.leakage_ua} µA",
                budgets.get(LEAKAGE),
            )
        )
    return out


def _check_base_bijection(  # noqa: PLR0913 — the reduction context threaded through
    base_flat: Circuit,
    flat: Circuit,
    *,
    base_names: dict[TileNet, str],
    drop_nets: set[str],
    tap_nets: set[str],
    issues: list[Issue],
) -> None:
    """Check the anti-drift bijection: every base part and net survives."""
    power_nets = {
        net.name
        for net in base_flat.nets.values()
        if any(
            pin.part.symbol.is_power or pin.type is PinType.POWER_OUT
            for pin in net.pins
        )
    }
    reduced: dict[tuple[str, str], str] = {}
    lost_nets: set[str] = set()
    for part in flat.parts.values():
        if part.provenance is not None:
            continue
        for pin in part.pins:
            net = pin.net
            if net is None or net.name in drop_nets:
                continue
            name = _reduced_name(net, base_names, lost_nets, issues)
            if name is not None:
                reduced[(part.ref, pin.number)] = name
    base_refs = set(base_flat.parts)
    for ref in sorted(base_refs, key=natural_key):
        _check_base_part(base_flat.parts[ref], flat, reduced, issues)
    for ref in sorted(set(flat.parts) - base_refs, key=natural_key):
        _check_extra_part(
            flat.parts[ref],
            base_flat,
            reduced=reduced,
            tap_nets=tap_nets,
            power_nets=power_nets,
            issues=issues,
        )


def _reduced_name(
    net: Net,
    base_names: dict[TileNet, str],
    lost_nets: set[str],
    issues: list[Issue],
) -> str | None:
    """Map a net to its reset-state name: tagged nets merge into their base.

    None when the tagged net's base no longer exists in the base
    capture — the anti-drift bijection's lost-net case, reported once
    per net.
    """
    if net.provenance is None:
        return net.name
    *dirs, _local = net.name.split("/")
    key = TileNet(tuple(dirs), net.provenance.base.split("/")[-1])
    name = base_names.get(key)
    if name is None and net.name not in lost_nets:
        lost_nets.add(net.name)
        issues.append(
            _issue(
                f"base net {net.provenance.base!r} lost under "
                f"{'/'.join(dirs)} — transform-created net {net.name!r} has "
                "no base counterpart",
                net.name,
            )
        )
    return name


def _check_base_part(
    base_part: Part,
    flat: Circuit,
    reduced: dict[tuple[str, str], str],
    issues: list[Issue],
) -> None:
    """One base part must survive: present, untagged, same symbol, same nets."""
    ref = base_part.ref
    placed = flat.parts.get(ref)
    if placed is None or placed.provenance is not None:
        issues.append(_issue(f"{ref}: base part lost in the instrumented board", ref))
        return
    if placed.symbol.ref != base_part.symbol.ref:
        issues.append(
            _issue(
                f"{ref}: symbol drifted ({base_part.symbol.ref} → {placed.symbol.ref})",
                ref,
            )
        )
    if placed.value != base_part.value:
        issues.append(
            _issue(f"{ref}: value drifted ({base_part.value} → {placed.value})", ref)
        )
    for pin in base_part.pins:
        want = pin.net.name if pin.net is not None else None
        got = reduced.get((ref, pin.number))
        if got != want:
            issues.append(
                _issue(f"{ref}.{pin.number}: re-connected ({want} → {got})", ref)
            )


def _check_extra_part(  # noqa: PLR0913 — the bijection context threaded through
    part: Part,
    base_flat: Circuit,
    *,
    reduced: dict[tuple[str, str], str],
    tap_nets: set[str],
    power_nets: set[str],
    issues: list[Issue],
) -> None:
    """Screen an instrumented-side part the base lacks.

    Board-level extras are the scan plane and supervisor — allowed. An
    untagged part inside a tile is capture drift (instrumentation is
    transforms only, never capture edits). A pin an extra part lands on
    a base net needs a declared tap and an input-class pin type (memo
    obligation 2) — except on power rails, which exist to be loaded
    (the rail's budget is the power tree's, not this proof's).
    """
    if part.provenance is not None:
        return
    if part.path:
        issues.append(
            _issue(
                f"{part.ref}: untagged part inside a tile — instrumentation "
                "is transforms only, never capture edits",
                part.ref,
            )
        )
        return
    for pin in part.pins:
        net_name = reduced.get((part.ref, pin.number))
        if net_name is None or net_name not in base_flat.nets or net_name in power_nets:
            continue
        if net_name not in tap_nets:
            issues.append(
                _issue(
                    f"{part.ref}.{pin.number} lands on base net {net_name!r} "
                    "with no declared tap — the plain board is re-connected",
                    net_name,
                )
            )
        elif pin.type not in _INPUT_CLASS:
            issues.append(
                _issue(
                    f"{part.ref}.{pin.number} taps base net {net_name!r} but "
                    f"is {pin.type} — taps must be high-impedance "
                    "(input-class PinType)",
                    net_name,
                )
            )
