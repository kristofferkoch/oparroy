"""KiCad netlist emitter: the s-expression ``.net`` format pcbnew imports.

Emission is byte-identical across runs (DESIGN.md §8): parts and nets
iterate in natural sorted order, net codes are sequential in that
order, timestamps are content-derived UUIDs, and no date or path leaks
into the output. Power-library symbols (``power:+3V3``) are
schematic-only net markers: they are excluded from the components and
net nodes, matching eeschema's own handling.

Sections eeschema also emits — ``libparts``, ``libraries``, comp
``fields``/``libsource``, ``design`` date — are deliberately omitted;
they are optional for pcbnew's importer (verified against the reader
source, 2026-09-27 review).
"""

import uuid

from oparroy.dsl.ir import Circuit, Part, natural_key

_TOOL = "oparroy-dsl"
_TSTAMP_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://oparroy.koch.no/dsl/tstamp")


def emit_netlist(circuit: Circuit) -> str:
    """Emit the circuit as a KiCad s-expression netlist.

    A hierarchical circuit (one with instances) or one with component
    sockets is flattened first; the hierarchy survives as each comp's
    ``sheetpath`` — content-derived, like the tstamps.
    """
    if circuit.instances or circuit.sockets:
        circuit = circuit.flatten()
    lines = [
        '(export (version "E")',
        "  (design",
        f'    (source "{_quote(circuit.name)}")',
        f'    (tool "{_TOOL}"))',
        "  (components",
    ]
    for ref in sorted(circuit.parts, key=natural_key):
        part = circuit.parts[ref]
        if part.symbol.is_power:
            continue
        lines.extend(_emit_part(circuit, part))
    lines.append("  )")
    lines.append("  (nets")
    nets = [circuit.nets[name] for name in sorted(circuit.nets, key=natural_key)]
    for code, net in enumerate(nets, start=1):
        head = f'    (net (code "{code}") (name "{_quote(net.name)}")'
        pins = [pin for pin in net.pins if not pin.part.symbol.is_power]
        if not pins:
            lines.append(head + ")")
            continue
        lines.append(head)
        node_lines = [
            f'      (node (ref "{_quote(pin.part.ref)}") '
            f'(pin "{_quote(pin.number)}") '
            f'(pintype "{pin.type}"))'
            for pin in pins
        ]
        node_lines[-1] += ")"
        lines.extend(node_lines)
    lines.append("  )")
    lines.append(")")
    return "\n".join(lines) + "\n"


def _emit_part(circuit: Circuit, part: Part) -> list[str]:
    lines = [f'    (comp (ref "{_quote(part.ref)}")']
    if part.value is not None:
        lines.append(f'      (value "{_quote(part.value)}")')
    if part.footprint is not None:
        lines.append(f'      (footprint "{_quote(part.footprint)}")')
    stamp = uuid.uuid5(_TSTAMP_NS, f"{circuit.name}/{part.ref}")
    lines.append(_emit_sheetpath(circuit, part))
    lines.append(f'      (tstamps "{stamp}"))')
    return lines


def _emit_sheetpath(circuit: Circuit, part: Part) -> str:
    """Render the comp's sheet path: "/" at root, the instance path below.

    Sheet tstamps are content-derived per path prefix, so emission
    stays byte-identical and an instance's sheet identity is as stable
    as its name.
    """
    if not part.path:
        return '      (sheetpath (names "/") (tstamps "/"))'
    names = "/" + "/".join(part.path) + "/"
    stamps = "/".join(
        str(
            uuid.uuid5(
                _TSTAMP_NS, f"{circuit.name}/sheet/{'/'.join(part.path[:depth])}"
            )
        )
        for depth in range(1, len(part.path) + 1)
    )
    return f'      (sheetpath (names "{_quote(names)}") (tstamps "/{stamps}/"))'


def _quote(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')
