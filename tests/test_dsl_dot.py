"""Dot-dump tests."""

from __future__ import annotations

from oparroy.dsl import Circuit, PinType, Symbol, SymbolPin, to_dot


def test_dot_renders_bipartite_graph(circuit: Circuit) -> None:
    dot = to_dot(circuit)
    assert dot.startswith('graph "test" {')
    assert dot.endswith("}\n")
    assert '"R1" [label="{R1|1k\\nStub:R}"];' in dot
    assert '"net:mid" [label="mid"];' in dot
    edges = [line for line in dot.splitlines() if " -- " in line]
    expected_edges = 4  # two resistors, two pins each
    assert len(edges) == expected_edges
    assert '"R1" -- "net:a" [label="1"];' in [e.strip() for e in edges]


class _NamedSymbols:
    """A diode with named pins (BAT54S-style: 2=K, 3=COM)."""

    def lookup(self, ref: str) -> Symbol:
        assert ref == "Stub:D"
        return Symbol(
            lib="Stub",
            name="D",
            pins=(
                SymbolPin(number="2", name="K", type=PinType.PASSIVE),
                SymbolPin(number="3", name="COM", type=PinType.PASSIVE),
            ),
        )


def test_edge_labels_include_pin_names() -> None:
    c = Circuit("named", _NamedSymbols())
    d1 = c.part("D1", symbol="Stub:D")
    c.connect(c.net("sel"), d1[2])
    c.connect(c.net("x"), d1[3])
    dot = to_dot(c)
    assert '"D1" -- "net:sel" [label="2 (K)"];' in dot
    assert '"D1" -- "net:x" [label="3 (COM)"];' in dot


def test_record_metacharacters_escaped(circuit: Circuit) -> None:
    # { } | are record-label syntax: escaped inside the part's record
    # label, but ordinary characters in quoted node names and in the
    # plain (ellipse) net labels.
    weird = circuit.part("R{3}|x", symbol="Stub:R")
    circuit.connect(circuit.net('n"|z'), weird[1])
    dot = to_dot(circuit)
    assert '"R{3}|x" [label="{R\\{3\\}\\|x|' in dot
    assert '"net:n\\"|z" [label="n\\"|z"];' in dot
