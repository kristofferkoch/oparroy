"""Port array, bundle, and connector-block tests (T7bb)."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pytest

from design.segment import SEGMENT_MEMBERS, SegmentConnector, segment_ports
from oparroy.dsl import (
    Bundle,
    BundleConnector,
    Circuit,
    DefinitionError,
    Subcircuit,
    check,
    emit_netlist,
)

if TYPE_CHECKING:
    from conftest import StubFootprints, StubSymbols
    from oparroy.dsl import KiCadLibraries, Net


class LedBar(Subcircuit):
    """`count` LED channels, each led[i] through one resistor to gnd."""

    def __init__(self, count: int) -> None:
        self._count = count

    def capture(self, circuit: Circuit) -> None:
        """Build the bar: the led port array, one resistor per element."""
        leds = circuit.port_array("led", self._count)
        gnd = circuit.port("gnd")
        for i, net in enumerate(leds):
            r = circuit.part(
                f"R{i}", symbol="Stub:R", value="1k", footprint="StubFP:R_0603"
            )
            circuit.connect(net, r[1])
            circuit.connect(gnd, r[2])


class StubSegmentConnector(BundleConnector):
    """The §3 pinout over the stub 6-pin connector."""

    symbol = "Stub:CONN6"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "unreg": "1",
        "v3v3": "2",
        "gnd": ("3", "5"),
        "a": "4",
        "b": "6",
    }
    default_value = "Conn6"
    default_footprint = "StubFP:CONN_1x06"


class SegmentNode(Subcircuit):
    """A minimal §3 node: the two segment-face connectors, nothing else."""

    def capture(self, circuit: Circuit) -> None:
        """Build the node: both faces' connectors on the §3 bundles."""
        upstream, downstream = segment_ports(circuit)
        circuit.part("J1", StubSegmentConnector(upstream))
        circuit.part("J2", StubSegmentConnector(downstream))


def face_bundle(
    circuit: Circuit, name: str, power: tuple[Net, Net, Net], a: Net, b: Net
) -> Bundle:
    """Group nets into a segment-face bundle: shared power, per-face data."""
    unreg, v3v3, gnd = power
    return circuit.bundle(name, unreg=unreg, v3v3=v3v3, gnd=gnd, a=a, b=b)


def build_link(symbols: StubSymbols) -> Circuit:
    """Two segment nodes chained: N0.downstream joins N1.upstream."""
    board = Circuit("link", symbols)
    power = (board.port("UNREG"), board.port("3V3"), board.port("GND"))
    face_in = face_bundle(
        board, "face_in", power, a=board.port("IN_A"), b=board.port("IN_B")
    )
    link = face_bundle(
        board, "link", power, a=board.net("LINK_A"), b=board.net("LINK_B")
    )
    face_out = face_bundle(
        board, "face_out", power, a=board.port("OUT_A"), b=board.port("OUT_B")
    )
    board.instance("N0", SegmentNode(), upstream=face_in, downstream=link)
    board.instance("N1", SegmentNode(), upstream=link, downstream=face_out)
    return board


def test_port_array_creates_indexed_port_nets(symbols: StubSymbols) -> None:
    circuit = Circuit("c", symbols)
    leds = circuit.port_array("led", 3)
    assert set(circuit.ports) == {"led[0]", "led[1]", "led[2]"}
    assert all(net.is_port for net in leds)
    assert set(circuit.port_arrays) == {"led"}
    assert circuit.port_arrays["led"] is leds


def test_port_array_is_a_sequence(symbols: StubSymbols) -> None:
    leds = Circuit("c", symbols).port_array("led", 3)
    names = ["led[0]", "led[1]", "led[2]"]
    assert len(leds) == len(names)
    assert [net.name for net in leds] == names
    assert leds[1] is leds.nets[1]
    assert repr(leds) == "<PortArray led[3]>"


def test_port_array_rejects_bad_names(symbols: StubSymbols) -> None:
    circuit = Circuit("c", symbols)
    with pytest.raises(DefinitionError, match="must not contain '/'"):
        circuit.port_array("le/d", 2)
    with pytest.raises(DefinitionError, match=r"must not contain '\['"):
        circuit.port_array("led[", 2)


def test_port_array_rejects_bad_width(symbols: StubSymbols) -> None:
    circuit = Circuit("c", symbols)
    with pytest.raises(DefinitionError, match="width of at least 1"):
        circuit.port_array("led", 0)


def test_port_array_rejects_name_collisions(symbols: StubSymbols) -> None:
    circuit = Circuit("c", symbols)
    circuit.net("row[1]")
    with pytest.raises(DefinitionError, match="collides with existing nets"):
        circuit.port_array("row", 3)
    circuit.port_array("led", 2)
    with pytest.raises(DefinitionError, match="duplicate port array name"):
        circuit.port_array("led", 4)
    with pytest.raises(DefinitionError, match="collides with a port array"):
        circuit.net("led")


def test_array_binding_flattens_elementwise(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    gnd = board.net("gnd")
    feeds = [board.net(f"led{i}") for i in range(3)]
    board.instance("LB0", LedBar(3), led=feeds, gnd=gnd)
    flat = board.flatten()
    nets = {name: {p.part.ref for p in net.pins} for name, net in flat.nets.items()}
    assert nets["led1"] == {"LB0/R1"}
    assert nets["gnd"] == {"LB0/R0", "LB0/R1", "LB0/R2"}


def test_array_binding_accepts_port_array(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    board.instance(
        "LB0", LedBar(2), led=board.port_array("led", 2), gnd=board.net("gnd")
    )
    flat = board.flatten()
    assert flat.nets["led[0]"].is_port
    assert {p.part.ref for p in flat.nets["led[1]"].pins} == {"LB0/R1"}


def test_array_binding_width_mismatch(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    board.net("gnd")
    with pytest.raises(DefinitionError, match="width 3, bound to 2 nets"):
        board.instance(
            "LB0",
            LedBar(3),
            led=[board.net("a"), board.net("b")],
            gnd="gnd",
        )


def test_array_binding_rejects_scalar(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    board.net("gnd")
    with pytest.raises(DefinitionError, match="is an array of width 3"):
        board.instance("LB0", LedBar(3), led=board.net("one"), gnd="gnd")


def test_array_elements_bind_individually(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    gnd = board.net("gnd")
    board.instance(
        "LB0",
        LedBar(3),
        gnd=gnd,
        **{f"led[{i}]": board.net(f"n{i}") for i in range(3)},
    )
    flat = board.flatten()
    nets = {name: {p.part.ref for p in net.pins} for name, net in flat.nets.items()}
    assert nets["n2"] == {"LB0/R2"}


def test_array_element_left_unbound(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    board.net("gnd")
    with pytest.raises(DefinitionError, match=r"ports \['led\[2\]'\] left"):
        board.instance(
            "LB0",
            LedBar(3),
            gnd="gnd",
            **{"led[0]": board.net("n0"), "led[1]": board.net("n1")},
        )


def test_array_and_element_binding_conflict(symbols: StubSymbols) -> None:
    # A port reached twice — through the array and by element name —
    # must resolve to one parent net; a conflict names both sources.
    board = Circuit("board", symbols)
    board.net("gnd")
    feeds = [board.net(f"n{i}") for i in range(3)]
    with pytest.raises(
        DefinitionError, match=r"'led\[0\]' bound by both 'led' and 'led\[0\]'"
    ):
        board.instance(
            "LB0", LedBar(3), led=feeds, gnd="gnd", **{"led[0]": board.net("x")}
        )
    board.instance("LB1", LedBar(3), led=feeds, gnd="gnd", **{"led[0]": "n0"})
    flat = board.flatten()
    assert {p.part.ref for p in flat.nets["n0"].pins} == {"LB1/R0"}


def test_bundle_groups_nets(symbols: StubSymbols) -> None:
    circuit = Circuit("c", symbols)
    upstream, downstream = segment_ports(circuit)
    assert list(upstream) == list(SEGMENT_MEMBERS)
    assert upstream.a.name == "RX_A"
    assert downstream.a.name == "TX_A"
    assert upstream["unreg"] is downstream["unreg"]
    assert upstream.gnd is circuit.ports["GND"]
    assert set(circuit.bundles) == {"upstream", "downstream"}
    with pytest.raises(KeyError, match="no member 'tx_a'"):
        upstream["tx_a"]


def test_bundle_requires_members(symbols: StubSymbols) -> None:
    circuit = Circuit("c", symbols)
    with pytest.raises(DefinitionError, match="at least one member"):
        circuit.bundle("empty")


def test_bundle_member_may_shadow_class_attribute(symbols: StubSymbols) -> None:
    # A member named like a class attribute shadows it on attribute
    # access; item access still reaches it.
    circuit = Circuit("c", symbols)
    sig = circuit.net("sig")
    bundle = circuit.bundle("b", name=sig)
    assert bundle.name == "b"
    assert bundle["name"] is sig


def test_bundle_rejects_bad_members(symbols: StubSymbols) -> None:
    circuit = Circuit("c", symbols)
    gnd = circuit.net("gnd")
    with pytest.raises(DefinitionError, match="no net named 'nope'"):
        circuit.bundle("b", gnd=gnd, sig="nope")
    with pytest.raises(DefinitionError, match="alias the same net 'gnd'"):
        circuit.bundle("b", gnd=gnd, gnd2=gnd)
    with pytest.raises(DefinitionError, match="must not contain '/'"):
        circuit.bundle("b", **{"a/b": gnd})


def test_bundle_rejects_foreign_net(symbols: StubSymbols) -> None:
    other = Circuit("other", symbols)
    with pytest.raises(DefinitionError, match="does not belong to circuit"):
        Circuit("c", symbols).bundle("b", gnd=other.net("gnd"))


def test_bundle_rejects_name_collisions(symbols: StubSymbols) -> None:
    circuit = Circuit("c", symbols)
    circuit.net("taken")
    with pytest.raises(DefinitionError, match="collides with a net"):
        circuit.bundle("taken", gnd=circuit.net("gnd"))
    circuit.bundle("b", gnd=circuit.nets["gnd"])
    with pytest.raises(DefinitionError, match="duplicate bundle name"):
        circuit.bundle("b", sig=circuit.net("sig"))
    with pytest.raises(DefinitionError, match="collides with a port array or bundle"):
        circuit.port("b")


def test_connector_wires_members_to_pins(symbols: StubSymbols) -> None:
    circuit = Circuit("node", symbols)
    SegmentNode().capture(circuit)
    nets = {
        name: {f"{p.part.ref}.{p.number}" for p in net.pins}
        for name, net in circuit.nets.items()
    }
    assert nets["UNREG"] == {"J1.1", "J2.1"}
    assert nets["GND"] == {"J1.3", "J1.5", "J2.3", "J2.5"}
    assert nets["RX_A"] == {"J1.4"}
    assert nets["TX_A"] == {"J2.4"}


def test_connector_rejects_member_drift(symbols: StubSymbols) -> None:
    circuit = Circuit("c", symbols)
    bundle = circuit.bundle(
        "b", unreg=circuit.net("u"), gnd=circuit.net("g"), extra=circuit.net("e")
    )
    with pytest.raises(DefinitionError, match=r"has no pins \['extra'\]"):
        StubSegmentConnector(bundle)
    with pytest.raises(DefinitionError, match="is missing pins"):
        StubSegmentConnector(
            circuit.bundle(
                "b2",
                unreg=circuit.nets["u"],
                gnd=circuit.nets["g"],
                a=circuit.net("a"),
                # "b" member missing
            )
        )
    with pytest.raises(TypeError, match="wires a Bundle"):
        StubSegmentConnector(circuit.nets["u"])  # ty: ignore[invalid-argument-type]


def test_bundle_binding_flattens_memberwise(symbols: StubSymbols) -> None:
    flat = build_link(symbols).flatten()
    nets = {
        name: {f"{p.part.ref}.{p.number}" for p in net.pins}
        for name, net in flat.nets.items()
    }
    # The link faces join by wire identity: N0's TX_A pin lands on N1's RX_A pin.
    assert nets["LINK_A"] == {"N0/J2.4", "N1/J1.4"}
    assert nets["LINK_B"] == {"N0/J2.6", "N1/J1.6"}
    # The power loop aliases into every face's bundle.
    assert nets["UNREG"] == {"N0/J1.1", "N0/J2.1", "N1/J1.1", "N1/J2.1"}
    assert len(nets["GND"]) == 2 * 4  # two connectors per node, two pins each
    assert nets["IN_A"] == {"N0/J1.4"}


def test_bundle_binding_accepts_mapping(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    power = (board.port("UNREG"), board.port("3V3"), board.port("GND"))
    face = face_bundle(board, "face", power, a=board.port("A"), b=board.port("B"))
    board.instance(
        "N0",
        SegmentNode(),
        upstream=face,
        # A plain mapping binds too; net names resolve like Net objects.
        downstream={
            "unreg": "UNREG",
            "v3v3": "3V3",
            "gnd": "GND",
            "a": board.net("D_A"),
            "b": board.net("D_B"),
        },
    )
    flat = board.flatten()
    assert {p.part.ref for p in flat.nets["D_A"].pins} == {"N0/J2"}


def test_bundle_binding_member_mismatch(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    power = (board.port("UNREG"), board.port("3V3"), board.port("GND"))
    face = face_bundle(board, "face", power, a=board.port("A"), b=board.port("B"))
    wrong = board.bundle(
        "wrong",
        unreg=board.net("u"),
        v3v3=board.net("v"),
        gnd=board.net("g"),
        a=board.net("a"),
        c=board.net("c"),
    )
    with pytest.raises(DefinitionError, match=r"missing \['b'\] and unknown \['c'\]"):
        board.instance("N0", SegmentNode(), upstream=face, downstream=wrong)


def test_bundle_binding_rejects_scalar(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    power = (board.port("UNREG"), board.port("3V3"), board.port("GND"))
    face = face_bundle(board, "face", power, a=board.port("A"), b=board.port("B"))
    with pytest.raises(DefinitionError, match="is a bundle with members"):
        board.instance(
            "N0", SegmentNode(), upstream=face, downstream=board.net("plain")
        )


def test_shared_port_conflict_raises(symbols: StubSymbols) -> None:
    # Both faces' bundles carry unreg; binding them to different parent
    # nets contradicts the node's shared UNREG port.
    board = Circuit("board", symbols)
    power = (board.port("UNREG"), board.port("3V3"), board.port("GND"))
    face = face_bundle(board, "face", power, a=board.port("A"), b=board.port("B"))
    other = face_bundle(
        board,
        "other",
        (board.net("U2"), board.net("V2"), board.net("G2")),
        a=board.net("A2"),
        b=board.net("B2"),
    )
    with pytest.raises(
        DefinitionError,
        match=r"'UNREG' bound by both 'upstream\.unreg' and 'downstream\.unreg'",
    ):
        board.instance("N0", SegmentNode(), upstream=face, downstream=other)


def test_nested_bundle_binding(symbols: StubSymbols) -> None:
    def pair(circuit: Circuit) -> None:
        upstream, downstream = segment_ports(circuit)
        link = circuit.bundle(
            "link",
            unreg=upstream["unreg"],
            v3v3=upstream["v3v3"],
            gnd=upstream["gnd"],
            a=circuit.net("LINK_A"),
            b=circuit.net("LINK_B"),
        )
        circuit.instance("N0", SegmentNode(), upstream=upstream, downstream=link)
        circuit.instance("N1", SegmentNode(), upstream=link, downstream=downstream)

    board = Circuit("board", symbols)
    power = (board.port("UNREG"), board.port("3V3"), board.port("GND"))
    face_in = face_bundle(
        board, "face_in", power, a=board.port("IN_A"), b=board.port("IN_B")
    )
    face_out = face_bundle(
        board, "face_out", power, a=board.port("OUT_A"), b=board.port("OUT_B")
    )
    board.instance("P", pair, upstream=face_in, downstream=face_out)
    flat = board.flatten()
    nets = {
        name: {f"{p.part.ref}.{p.number}" for p in net.pins}
        for name, net in flat.nets.items()
    }
    assert nets["P/LINK_A"] == {"P/N0/J2.4", "P/N1/J1.4"}
    assert nets["UNREG"] == {
        "P/N0/J1.1",
        "P/N0/J2.1",
        "P/N1/J1.1",
        "P/N1/J2.1",
    }


def test_link_board_checks_clean(
    symbols: StubSymbols, footprints: StubFootprints
) -> None:
    assert check(build_link(symbols), footprints=footprints) == []


def test_link_board_emits_hierarchically(symbols: StubSymbols) -> None:
    rendered = emit_netlist(build_link(symbols))
    assert '(comp (ref "N0/J1")' in rendered
    assert '(comp (ref "N1/J2")' in rendered
    assert '(sheetpath (names "/N0/")' in rendered
    assert '(net (code "1")' in rendered


def test_dump_shows_arrays_and_bundles(symbols: StubSymbols) -> None:
    board = build_link(symbols)
    board.port_array("dbg", 2)
    rendered = board.dump()
    assert "port array dbg[2]" in rendered
    assert "bundle link: unreg=UNREG v3v3=3V3 gnd=GND a=LINK_A b=LINK_B" in rendered


def test_segment_connector_against_kicad_libs(kicad_libs: KiCadLibraries) -> None:
    # The real §3 connector block: KiCad's Conn_02x05_Odd_Even symbol and
    # the IDC box-header footprint, checked against the libraries.
    circuit = Circuit("segment", kicad_libs)
    upstream, downstream = segment_ports(circuit)
    circuit.part("J1", SegmentConnector(upstream))
    circuit.part("J2", SegmentConnector(downstream))
    assert check(circuit, footprints=kicad_libs) == []
    nets = {
        name: {f"{p.part.ref}.{p.number}" for p in net.pins}
        for name, net in circuit.nets.items()
    }
    assert nets["GND"] == {
        f"{j}.{pin}" for j in ("J1", "J2") for pin in ("2", "4", "6", "8", "10")
    }
