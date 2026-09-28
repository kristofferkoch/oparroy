"""Component socket tests: subcircuits that need a *part*, not nets (T7bc).

DESIGN.md §7: a socket declares a protocol of pin handles; the
instantiating parent directs the packing — a standalone typed part or
one unit of a parent-placed multi-unit package — and the subcircuit
stays package-agnostic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pytest

from oparroy.dsl import (
    Circuit,
    DefinitionError,
    Diode,
    MultiUnitPart,
    Severity,
    SocketSpec,
    Subcircuit,
    TypedPart,
    check,
    emit_netlist,
    to_dot,
)

if TYPE_CHECKING:
    from conftest import StubFootprints, StubSymbols


class StubDiode(Diode):
    """Diode redirected at the stub symbol table, with a bin default."""

    symbol = "Stub:D"
    default_footprint = "StubFP:SOD-323"


class StubDiodeSocket(SocketSpec):
    """The anode/cathode protocol over the stub standalone diode."""

    pins: ClassVar[tuple[str, ...]] = ("anode", "cathode")
    default: ClassVar[type[TypedPart]] = StubDiode


class StubQd(MultiUnitPart):
    """Quad diode over the stub symbol table; units follow the protocol."""

    symbol = "Stub:QD"
    unit_pins: ClassVar[dict[int, dict[str, str]]] = {
        1: {"cathode": "1", "anode": "6"},
        2: {"cathode": "2", "anode": "6"},
        3: {"anode": "3", "cathode": "4"},
        4: {"anode": "3", "cathode": "5"},
    }
    default_value = "QD"
    default_footprint = "StubFP:SOT-363"


class Clamp(Subcircuit):
    """Diode clamp: the socket diode from port ``in`` to port ``rail``."""

    def capture(self, circuit: Circuit) -> None:
        """Build the clamp: D1 anode on ``in``, cathode on ``rail``."""
        inp = circuit.port("in")
        rail = circuit.port("rail")
        d1 = circuit.socket("D1", StubDiodeSocket)
        circuit.connect(inp, d1["anode"])
        circuit.connect(rail, d1["cathode"])


def board_with_clamps(symbols: StubSymbols, **bindings: object) -> Circuit:
    """Build a board with U1 placed and one bound Clamp instance."""
    board = Circuit("board", symbols)
    board.net("in")
    board.net("rail")
    board.part("U1", StubQd())
    board.instance("CL0", Clamp(), **bindings)  # ty: ignore[invalid-argument-type]
    return board


def test_socket_declaration(symbols: StubSymbols) -> None:
    c = Circuit("t", symbols)
    Clamp().capture(c)
    assert set(c.sockets) == {"D1"}
    d1 = c.parts["D1"]
    assert d1.symbol.is_socket
    assert {pin.number for pin in d1.pins} == {"anode", "cathode"}
    assert d1["anode"].net is c.nets["in"]


def test_socket_name_collisions_raise(symbols: StubSymbols) -> None:
    c = Circuit("t", symbols)
    c.socket("D1", StubDiodeSocket)
    with pytest.raises(DefinitionError, match="duplicate socket reference"):
        c.socket("D1", StubDiodeSocket)
    with pytest.raises(DefinitionError, match="collides with a socket"):
        c.net("D1")
    c2 = Circuit("t2", symbols)
    c2.net("D2")
    with pytest.raises(DefinitionError, match="collides with a net"):
        c2.socket("D2", StubDiodeSocket)


def test_malformed_socket_specs_raise(symbols: StubSymbols) -> None:
    class NoPins(SocketSpec):
        default: ClassVar[type[TypedPart]] = StubDiode

    class WrongDefault(SocketSpec):
        pins: ClassVar[tuple[str, ...]] = ("anode", "cathode")
        default: ClassVar[type[TypedPart]] = StubQd  # type: ignore[assignment]

    class MismatchedDefault(SocketSpec):
        pins: ClassVar[tuple[str, ...]] = ("anode",)
        default: ClassVar[type[TypedPart]] = StubDiode

    c = Circuit("t", symbols)
    with pytest.raises(DefinitionError, match="SocketSpec subclass"):
        c.socket("D1", StubDiode)  # ty: ignore[invalid-argument-type]
    with pytest.raises(DefinitionError, match="pins"):
        c.socket("D1", NoPins)
    with pytest.raises(DefinitionError, match="standalone part"):
        c.socket("D1", WrongDefault)
    with pytest.raises(DefinitionError, match="protocol pins"):
        c.socket("D1", MismatchedDefault)
    assert c.parts == {}


def test_unbound_socket_materializes_the_default_part(
    symbols: StubSymbols,
) -> None:
    flat = board_with_clamps(symbols, **{"in": "in", "rail": "rail"}).flatten()
    d1 = flat.parts["CL0/D1"]
    assert d1.symbol.ref == "Stub:D"
    assert d1.footprint == "StubFP:SOD-323"
    assert d1.path == ("CL0",)
    assert d1.pin("2") in flat.nets["in"].pins  # anode
    assert d1.pin("1") in flat.nets["rail"].pins  # cathode
    assert not any(part.symbol.is_socket for part in flat.parts.values())


def test_part_class_binding_directs_the_standalone_part(
    symbols: StubSymbols,
) -> None:
    class StubDiodeLed(StubDiode):
        default_footprint = "StubFP:SOT-363"

    flat = board_with_clamps(
        symbols, **{"in": "in", "rail": "rail", "D1": StubDiodeLed}
    ).flatten()
    assert flat.parts["CL0/D1"].footprint == "StubFP:SOT-363"


def test_packed_socket_materializes_no_part(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    board.net("in")
    board.net("rail")
    u1 = board.part("U1", StubQd())
    board.instance("CL0", Clamp(), **{"in": "in", "rail": "rail", "D1": u1.unit(3)})
    flat = board.flatten()
    assert "CL0/D1" not in flat.parts
    placed = flat.parts["U1"]
    assert placed.pin("3") in flat.nets["in"].pins  # unit 3 anode
    assert placed.pin("4") in flat.nets["rail"].pins  # unit 3 cathode
    # The packed unit's other pins stay where the subcircuit put nothing.
    assert not any(part.symbol.is_socket for part in flat.parts.values())


def test_shared_anode_packs_two_sockets_onto_one_net(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    board.net("in")
    rail0 = board.net("rail0")
    rail1 = board.net("rail1")
    u1 = board.part("U1", StubQd())
    board.instance("CL0", Clamp(), **{"in": "in", "rail": rail0, "D1": u1.unit(1)})
    board.instance("CL1", Clamp(), **{"in": "in", "rail": rail1, "D1": u1.unit(2)})
    flat = board.flatten()
    # Units 1 and 2 share physical anode pin 6, and both subcircuits
    # wired it to the same 'in' net — one pin, one net, one entry.
    anodes = [pin for pin in flat.nets["in"].pins if pin.part.ref == "U1"]
    assert [pin.number for pin in anodes] == ["6"]
    assert flat.parts["U1"].pin("1") in flat.nets["rail0"].pins
    assert flat.parts["U1"].pin("2") in flat.nets["rail1"].pins


def test_shared_pin_on_two_nets_raises(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    board.net("rail")
    in0 = board.net("in0")
    in1 = board.net("in1")
    u1 = board.part("U1", StubQd())
    board.instance("CL0", Clamp(), **{"in": in0, "rail": "rail", "D1": u1.unit(1)})
    board.instance("CL1", Clamp(), **{"in": in1, "rail": "rail", "D1": u1.unit(2)})
    with pytest.raises(DefinitionError, match=r"U1\.6 is already on net"):
        board.flatten()


def test_one_unit_satisfies_one_socket(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    board.net("in")
    board.net("rail")
    u1 = board.part("U1", StubQd())
    board.instance("CL0", Clamp(), **{"in": "in", "rail": "rail", "D1": u1.unit(3)})
    with pytest.raises(DefinitionError, match="already packed into CL0/D1"):
        board.instance("CL1", Clamp(), **{"in": "in", "rail": "rail", "D1": u1.unit(3)})
    # The rejected instance consumed nothing: unit 4 packs elsewhere.
    board.instance("CL2", Clamp(), **{"in": "in", "rail": "rail", "D1": u1.unit(4)})
    assert set(board.instances) == {"CL0", "CL2"}


def test_unit_handle_must_match_the_protocol(symbols: StubSymbols) -> None:
    class StubSwitch(MultiUnitPart):
        symbol = "Stub:QD"
        unit_pins: ClassVar[dict[int, dict[str, str]]] = {
            1: {"a": "1", "b": "6"},
        }

    board = Circuit("board", symbols)
    board.net("in")
    board.net("rail")
    sw = board.part("SW1", StubSwitch())
    with pytest.raises(DefinitionError, match="does not satisfy socket 'D1'"):
        board.instance("CL0", Clamp(), **{"in": "in", "rail": "rail", "D1": sw.unit(1)})


def test_binding_channel_mismatch_errors(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    board.net("in")
    board.net("rail")
    u1 = board.part("U1", StubQd())
    with pytest.raises(DefinitionError, match="need a unit handle"):
        board.instance("CL0", Clamp(), **{"in": "in", "rail": "rail", "D1": "in"})
    with pytest.raises(DefinitionError, match="is a net port"):
        board.instance("CL0", Clamp(), **{"in": u1.unit(3), "rail": "rail"})
    with pytest.raises(DefinitionError, match="has no socket 'D9'"):
        board.instance("CL0", Clamp(), **{"in": "in", "rail": "rail", "D9": u1.unit(3)})
    with pytest.raises(DefinitionError, match="one unit"):
        board.instance("CL0", Clamp(), **{"in": "in", "rail": "rail", "D1": StubQd})
    with pytest.raises(DefinitionError, match="part \\*class\\*"):
        board.instance(
            "CL0",
            Clamp(),
            **{"in": "in", "rail": "rail", "D1": StubDiode(anode="in", cathode="rail")},  # ty: ignore
        )
    assert board.instances == {}


def test_packed_part_must_be_parent_placed(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    board.net("in")
    board.net("rail")
    other = Circuit("other", symbols)
    foreign = other.part("U9", StubQd())
    with pytest.raises(DefinitionError, match="does not belong to circuit"):
        board.instance(
            "CL0", Clamp(), **{"in": "in", "rail": "rail", "D1": foreign.unit(3)}
        )


def test_ports_still_validate_when_sockets_bound(symbols: StubSymbols) -> None:
    board = Circuit("board", symbols)
    board.net("in")
    u1 = board.part("U1", StubQd())
    with pytest.raises(DefinitionError, match="left unconnected"):
        board.instance("CL0", Clamp(), **{"in": "in", "D1": u1.unit(3)})


def test_top_level_socket_defaults_at_check(
    symbols: StubSymbols, footprints: StubFootprints
) -> None:
    c = Circuit("t", symbols)
    inp = c.net("in")
    rail = c.net("rail")
    d1 = c.socket("D1", StubDiodeSocket)
    c.connect(inp, d1["anode"])
    c.connect(rail, d1["cathode"])
    issues = check(c, footprints=footprints)
    assert [issue for issue in issues if issue.severity is Severity.ERROR] == []
    netlist = emit_netlist(c)
    assert '(comp (ref "D1")' in netlist
    assert "socket:" not in netlist
    assert "socket:" not in to_dot(c)


def test_packed_board_checks_clean(
    symbols: StubSymbols, footprints: StubFootprints
) -> None:
    board = Circuit("board", symbols)
    board.net("in")
    board.net("rail")
    u1 = board.part("U1", StubQd())
    board.instance("CL0", Clamp(), **{"in": "in", "rail": "rail", "D1": u1.unit(3)})
    errors = [
        issue
        for issue in check(board, footprints=footprints)
        if issue.severity is Severity.ERROR
    ]
    assert errors == []
    netlist = emit_netlist(board)
    assert '(comp (ref "U1")' in netlist
    assert "CL0/D1" not in netlist
    assert '(node (ref "U1") (pin "3")' in netlist
