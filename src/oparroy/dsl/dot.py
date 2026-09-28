"""Graphviz dot dump: the minimal human-review view of a circuit.

Parts and nets form a bipartite graph — part records on one side, net
ellipses on the other, edges labeled with pin numbers (and names, when
the symbol gives one). Deliberately simple; abstraction-level block
views are card T25 (prior art:
docs/prior-art-schematic-gen-2026-09-28.md, DESIGN.md §7 DSL shape).
"""

from oparroy.dsl.ir import Circuit, Pin, natural_key


def to_dot(circuit: Circuit) -> str:
    """Render the circuit as a Graphviz dot graph.

    A hierarchical circuit (one with instances) or one with component
    sockets is flattened first — the flat bipartite view; cluster
    rendering is T26 territory.
    """
    if circuit.instances or circuit.sockets:
        circuit = circuit.flatten()
    lines = [
        f'graph "{_escape(circuit.name)}" {{',
        "  rankdir=LR;",
        "  node [shape=record, fontsize=10];",
    ]
    for ref in sorted(circuit.parts, key=natural_key):
        part = circuit.parts[ref]
        value = part.value if part.value is not None else ""
        label = (
            f"{{{_escape_record(ref)}|"
            f"{_escape_record(value)}\\n{_escape_record(part.symbol.ref)}}}"
        )
        lines.append(f'  "{_escape(ref)}" [label="{label}"];')
    lines.append("  node [shape=ellipse, fontsize=10, width=0.5];")
    lines.extend(
        f'  "net:{_escape(name)}" [label="{_escape(name)}"];'
        for name in sorted(circuit.nets, key=natural_key)
    )
    lines.append("  edge [fontsize=8];")
    for name in sorted(circuit.nets, key=natural_key):
        net = circuit.nets[name]
        lines.extend(
            f'  "{_escape(pin.part.ref)}" -- "net:{_escape(net.name)}" '
            f'[label="{_escape(_pin_label(pin))}"];'
            for pin in net.pins
        )
    lines.append("}")
    return "\n".join(lines) + "\n"


def _pin_label(pin: Pin) -> str:
    if pin.name:
        return f"{pin.number} ({pin.name})"
    return pin.number


def _escape(text: str) -> str:
    """Escape for a plain (non-record) label: backslash and quote only."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _escape_record(text: str) -> str:
    """Escape for a record label, where {} and | are structural."""
    return _escape(text).replace("{", "\\{").replace("}", "\\}").replace("|", "\\|")
