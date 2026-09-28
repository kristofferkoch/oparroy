"""Subcircuit composition tests: ports, instances, flattening (T7ba)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from design.watchdog_chargepump import WatchdogChargePump
from oparroy.dsl import (
    Circuit,
    DefinitionError,
    Subcircuit,
    check,
    emit_netlist,
    to_dot,
)

if TYPE_CHECKING:
    from conftest import StubFootprints, StubSymbols
    from oparroy.dsl import KiCadLibraries


class RcLowpass(Subcircuit):
    """Two-stage RC lowpass over the stub symbols; ports in/out/gnd."""

    def capture(self, circuit: Circuit) -> None:
        """Build the filter: R1 in→mid, C1 mid→gnd, R2 mid→out."""
        inp = circuit.port("in")
        out = circuit.port("out")
        gnd = circuit.port("gnd")
        mid = circuit.net("mid")
        r1 = circuit.part("R1", symbol="Stub:R", value="1k", footprint="StubFP:R_0603")
        c1 = circuit.part(
            "C1", symbol="Stub:C", value="100n", footprint="StubFP:C_0603"
        )
        r2 = circuit.part("R2", symbol="Stub:R", value="1k", footprint="StubFP:R_0603")
        circuit.connect(inp, r1[1])
        circuit.connect(mid, r1[2], c1[1], r2[1])
        circuit.connect(gnd, c1[2])
        circuit.connect(out, r2[2])


def build(symbols: StubSymbols, *, instances: int = 1) -> Circuit:
    """Build a board with `instances` RC filters sharing in/gnd."""
    board = Circuit("board", symbols)
    inp = board.net("in")
    gnd = board.net("gnd")
    feed = board.part("RF", symbol="Stub:R", value="1k", footprint="StubFP:R_0603")
    board.connect(inp, feed[1])
    board.connect(gnd, feed[2])
    for i in range(instances):
        # "in" is a Python keyword — port binding goes through **{}.
        board.instance(
            f"LP{i}",
            RcLowpass(),
            **{"in": inp, "out": board.net(f"out{i}"), "gnd": gnd},
        )
    return board


def test_ports_form_the_interface(symbols: StubSymbols) -> None:
    child = Circuit("child", symbols)
    RcLowpass().capture(child)
    assert set(child.ports) == {"in", "out", "gnd"}
    assert all(net.is_port for net in child.ports.values())
    assert not child.nets["mid"].is_port


def test_flatten_prefixes_refs_and_internal_nets(symbols: StubSymbols) -> None:
    flat = build(symbols).flatten()
    assert set(flat.parts) == {"RF", "LP0/R1", "LP0/C1", "LP0/R2"}
    assert set(flat.nets) == {"in", "gnd", "out0", "LP0/mid"}
    assert flat.parts["LP0/R1"].path == ("LP0",)
    assert flat.parts["RF"].path == ()


def test_flatten_merges_ports_into_bound_nets(symbols: StubSymbols) -> None:
    flat = build(symbols).flatten()
    nets = {
        name: {f"{p.part.ref}.{p.number}" for p in net.pins}
        for name, net in flat.nets.items()
    }
    assert nets["in"] == {"RF.1", "LP0/R1.1"}
    assert nets["gnd"] == {"RF.2", "LP0/C1.2"}
    assert nets["out0"] == {"LP0/R2.2"}
    assert nets["LP0/mid"] == {"LP0/R1.2", "LP0/C1.1", "LP0/R2.1"}


def test_multi_instance_capture(symbols: StubSymbols) -> None:
    flat = build(symbols, instances=8).flatten()
    assert len(flat.parts) == 1 + 8 * 3
    assert flat.parts["LP7/R2"].path == ("LP7",)


def test_refdes_stable_across_source_edits(symbols: StubSymbols) -> None:
    # Inserting an instance renumbers nothing: every comp block of the
    # 2-instance board appears verbatim in the 3-instance one — names
    # are explicit at every level, tstamps are content-derived.
    def comp_blocks(rendered: str) -> dict[str, list[str]]:
        blocks: dict[str, list[str]] = {}
        current: str | None = None
        for line in rendered.splitlines():
            if line.startswith("    (comp "):
                current = line.split('"')[1]
                blocks[current] = [line]
            elif current is not None and line.startswith("      "):
                blocks[current].append(line)
            elif line.startswith("  )"):  # end of the components section
                current = None
        return blocks

    before = comp_blocks(emit_netlist(build(symbols, instances=2)))
    after = comp_blocks(emit_netlist(build(symbols, instances=3)))
    assert set(before) < set(after)
    assert before == {ref: after[ref] for ref in before}


def test_nested_instances(symbols: StubSymbols) -> None:
    def pair(circuit: Circuit) -> None:
        inp = circuit.port("in")
        out = circuit.port("out")
        gnd = circuit.port("gnd")
        mid = circuit.net("mid")
        circuit.instance("A", RcLowpass(), **{"in": inp, "out": mid, "gnd": gnd})
        circuit.instance("B", RcLowpass(), **{"in": mid, "out": out, "gnd": gnd})

    board = Circuit("board", symbols)
    inp = board.net("in")
    gnd = board.net("gnd")
    out = board.net("out")
    board.instance("P", pair, **{"in": inp, "out": out, "gnd": gnd})
    flat = board.flatten()
    assert "P/A/R1" in flat.parts
    assert flat.parts["P/B/C1"].path == ("P", "B")
    nets = {name: {p.part.ref for p in net.pins} for name, net in flat.nets.items()}
    # A's out binds to P's internal mid, which feeds B's in: one net.
    assert nets["P/mid"] == {"P/A/R2", "P/B/R1"}


def test_check_reports_hierarchical_paths(
    symbols: StubSymbols, footprints: StubFootprints
) -> None:
    board = build(symbols)
    board.part("RX", symbol="Stub:R", value="1k")  # no footprint
    board.instance(
        "LP9",
        RcLowpass(),
        **{"in": "in", "out": board.net("out9"), "gnd": "gnd"},
    )
    messages = [str(issue) for issue in check(board, footprints=footprints)]
    assert any("RX has no footprint" in m for m in messages)
    # out9 dangles at board level — reported under the flat net name.
    assert any("net 'out9' has a single pin (LP9/R2.2)" in m for m in messages)


def test_check_flags_instance_part_by_hierarchical_path(
    symbols: StubSymbols, footprints: StubFootprints
) -> None:
    class BareRc(Subcircuit):
        def capture(self, circuit: Circuit) -> None:
            inp = circuit.port("in")
            gnd = circuit.port("gnd")
            r = circuit.part("R1", symbol="Stub:R", value="1k")  # no footprint
            circuit.connect(inp, r[1])
            circuit.connect(gnd, r[2])

    board = Circuit("board", symbols)
    board.instance("LP0", BareRc(), **{"in": board.net("in"), "gnd": board.net("gnd")})
    messages = [str(issue) for issue in check(board, footprints=footprints)]
    assert any("LP0/R1 has no footprint" in m for m in messages)


def test_emit_flattens_and_carries_sheetpaths(symbols: StubSymbols) -> None:
    board = build(symbols)
    assert emit_netlist(board) == emit_netlist(board.flatten())
    rendered = emit_netlist(board)
    assert '(comp (ref "LP0/R1")' in rendered
    assert '(sheetpath (names "/LP0/")' in rendered
    assert '(node (ref "LP0/R1") (pin "1") (pintype "passive"))' in rendered


def test_dot_flattens(symbols: StubSymbols) -> None:
    dot = to_dot(build(symbols))
    assert '"LP0/R1"' in dot
    assert '"net:LP0/mid"' in dot


def test_dump_shows_ports_and_instances(symbols: StubSymbols) -> None:
    rendered = build(symbols).dump()
    assert "instance LP0:" in rendered
    assert "in [port]:" in rendered


def test_instance_rejects_unknown_port(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    with pytest.raises(DefinitionError, match="no ports"):
        board.instance("LP0", RcLowpass(), **{"in": "x", "out": "y", "gn": "z"})


def test_instance_rejects_unconnected_port(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    board.net("in")
    board.net("gnd")
    with pytest.raises(DefinitionError, match=r"ports \['out'\] left unconnected"):
        board.instance("LP0", RcLowpass(), **{"in": "in", "gnd": "gnd"})


def test_instance_rejects_duplicate_name(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    kwargs = {"in": board.net("in"), "out": board.net("out"), "gnd": board.net("gnd")}
    board.instance("LP0", RcLowpass(), **kwargs)
    with pytest.raises(DefinitionError, match="duplicate instance name 'LP0'"):
        board.instance("LP0", RcLowpass(), **kwargs)


def test_instance_rejects_path_separator(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    with pytest.raises(DefinitionError, match="must not contain '/'"):
        board.instance("LP/0", RcLowpass())


def test_net_and_ref_reject_path_separator(symbols: StubSymbols) -> None:
    # '/' is the hierarchy path separator at every level: a net or ref
    # carrying it would collide with a flattened path (LP0/mid).
    board = Circuit("board", symbols)
    with pytest.raises(DefinitionError, match="must not contain '/'"):
        board.net("LP0/mid")
    with pytest.raises(DefinitionError, match="must not contain '/'"):
        board.port("LP0/in")
    with pytest.raises(DefinitionError, match="must not contain '/'"):
        board.part("LP0/R1", symbol="Stub:R", value="1k")


def test_flatten_keeps_unbound_ports_exempt(
    symbols: StubSymbols, footprints: StubFootprints
) -> None:
    # A board-level port dangles by design; the instance-triggered
    # flattening in check/dot/emit must not drop the exemption.
    board = Circuit("board", symbols)
    ext = board.port("ext")
    gnd = board.net("gnd")
    sig = board.net("sig")
    feed = board.part("RF", symbol="Stub:R", value="1k", footprint="StubFP:R_0603")
    board.connect(ext, feed[1])
    board.connect(sig, feed[2])
    board.instance(
        "LP0", RcLowpass(), **{"in": sig, "out": board.net("out0"), "gnd": gnd}
    )
    assert board.flatten().nets["ext"].is_port
    messages = [str(issue) for issue in check(board, footprints=footprints)]
    assert not any("'ext'" in m for m in messages)


def test_instance_rejects_foreign_net(symbols: StubSymbols) -> None:
    other = Circuit("other", symbols)
    board = Circuit("board", symbols)
    board.net("out")
    board.net("gnd")
    with pytest.raises(DefinitionError, match="does not belong to circuit"):
        board.instance(
            "LP0",
            RcLowpass(),
            **{"in": other.net("in"), "out": "out", "gnd": "gnd"},
        )


def test_port_name_conflicts_with_net(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    board.net("ka")
    with pytest.raises(DefinitionError, match="duplicate net name 'ka'"):
        board.port("ka")


def test_eight_watchdogs_flatten_and_check_clean(
    kicad_libs: KiCadLibraries,
) -> None:
    # The T7b proving case at watchdog scale: 8 identical instances of
    # one subcircuit, sharing the keep-alive and ground nets.
    board = Circuit("watchdog-octet", kicad_libs)
    ka = board.net("ka")
    gnd = board.net("GND")
    for i in range(8):
        board.instance(
            f"WD{i}",
            WatchdogChargePump(),
            ka=ka,
            sel=board.net(f"sel{i}"),
            GND=gnd,
        )
    assert check(board, footprints=kicad_libs) == []
    flat = board.flatten()
    assert len(flat.parts) == 8 * 5
    assert flat.parts["WD3/D1"].path == ("WD3",)
    nets = {name: {p.part.ref for p in net.pins} for name, net in flat.nets.items()}
    assert nets["ka"] == {f"WD{i}/Rs" for i in range(8)}
    assert nets["sel5"] == {"WD5/D1", "WD5/Cs", "WD5/Rb"}
    assert nets["WD0/x"] == {"WD0/Cp", "WD0/D1"}
    rendered = emit_netlist(board)
    assert '(comp (ref "WD7/Rb")' in rendered
    assert '(sheetpath (names "/WD7/")' in rendered
