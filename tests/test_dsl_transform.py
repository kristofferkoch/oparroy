"""Instrumentation-transform tests: the four kinds, per-tile keying, provenance (T24a).

The fixture mirrors the CI board's shape at minimal size
(docs/instrumented-ci-2026-10-05.md §7): a ``Tile`` subcircuit with a
PHY inner instance (so transform targets reach across the tile's own
hierarchy), tiled twice on segment nets, plus a third instance of a
different subcircuit the per-tile keying must not touch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pytest

from oparroy.dsl import (
    AddShunt,
    AddTap,
    Bat54adw,
    Capacitor,
    Circuit,
    DefinitionError,
    InsertSeries,
    Net,
    PerInstance,
    PerTile,
    Provenance,
    Resistor,
    Subcircuit,
    Substitute,
    Transform,
    TransformPart,
    TypedPart,
    Waiver,
    apply_transforms,
    check,
    raise_on_errors,
)
from oparroy.dsl.ir import hierarchical_waivers

if TYPE_CHECKING:
    from conftest import StubFootprints, StubSymbols


class StubSwitch(TypedPart):
    """SPDT analog-switch stub (``Stub:SW``): ``a`` common, ``b1``/``b2`` throws.

    ``s`` is the select. ``b2`` is optional, so a record can leave a
    throw unconnected (the break switch's NC) without a named net.
    """

    symbol = "Stub:SW"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "a": "1",
        "b1": "2",
        "b2": "3",
        "s": "4",
    }
    required_pins: ClassVar[frozenset[str]] = frozenset({"a", "b1", "s"})
    default_footprint = "StubFP:SOT-363"

    def __init__(  # noqa: PLR0913 — one keyword per physical pin
        self,
        *,
        a: Net | str,
        b1: Net | str,
        s: Net | str,
        b2: Net | str | None = None,
        value: str | None = None,
        footprint: str | None = None,
    ) -> None:
        nets: dict[str, Net | str] = {"a": a, "b1": b1, "s": s}
        if b2 is not None:
            nets["b2"] = b2
        super().__init__(value, footprint, nets)


def phy_capture(circuit: Circuit) -> None:
    """Minimal PHY: a series R and a clamp cap between tx_a and mcu_rx."""
    tx_a = circuit.port("tx_a")
    gnd = circuit.port("gnd")
    mcu_rx = circuit.port("mcu_rx")
    circuit.part("Rat", Resistor("470", a=mcu_rx, b=tx_a, footprint="StubFP:R_0603"))
    circuit.part("Dat", Capacitor("100n", a=tx_a, b=gnd, footprint="StubFP:C_0603"))


class Tile(Subcircuit):
    """Minimal node tile: a PHY behind the TX_A port, plus internal nets."""

    def capture(self, circuit: Circuit) -> None:
        """Build the tile; the interface is TX_A/3V3/GND."""
        tx_a = circuit.port("TX_A")
        v3v3 = circuit.port("3V3")
        gnd = circuit.port("GND")
        sense = circuit.net("sense")
        ka = circuit.net("ka")
        pot = circuit.net("pot")
        j2 = circuit.part(
            "J2", symbol="Stub:CONN6", value="Conn", footprint="StubFP:CONN_1x06"
        )
        circuit.connect(tx_a, j2[5])
        circuit.connect(gnd, j2[2])
        circuit.connect(v3v3, j2[3])
        circuit.instance("PHY1", phy_capture, tx_a=tx_a, gnd=gnd, mcu_rx=sense)
        # The MCU stand-in: pins on the internal nets.
        u1 = circuit.part(
            "U1", symbol="Stub:CONN6", value="Mcu", footprint="StubFP:CONN_1x06"
        )
        circuit.connect(sense, u1[1])
        circuit.connect(ka, u1[2])
        circuit.connect(pot, u1[3])
        circuit.part("Rwd", Resistor("220", a=ka, b=gnd, footprint="StubFP:R_0603"))
        circuit.part("Rpot", Resistor("10k", a=pot, b=v3v3, footprint="StubFP:R_0603"))


class Other(Subcircuit):
    """A different subcircuit the per-tile keying must not touch."""

    def capture(self, circuit: Circuit) -> None:
        """One resistor across the ground port."""
        gnd = circuit.port("GND")
        circuit.part("R1", Resistor("1k", a=gnd, b=gnd, footprint="StubFP:R_0603"))


def build_board(symbols: StubSymbols) -> Circuit:
    """Build the board: two tiles chained on segment nets, plus X1."""
    board = Circuit("ci", symbols)
    v3v3 = board.net("3V3")
    gnd = board.net("GND")
    board.instance(
        "T0", Tile(), **{"TX_A": board.net("SEG_A"), "3V3": v3v3, "GND": gnd}
    )
    board.instance(
        "T1", Tile(), **{"TX_A": board.net("SEG_B"), "3V3": v3v3, "GND": gnd}
    )
    board.instance("X1", Other(), GND=gnd)
    return board


def f1() -> InsertSeries:
    """Build the break-switch record: the split cuts across the PHY boundary."""
    return InsertSeries(
        label="F1",
        net="TX_A",
        pins=("PHY1/Rat.b",),
        part=TransformPart("FI1/SWAB", StubSwitch(a="@b", b1="@a", s="@control")),
        control="BRK_A",
    )


def f7() -> InsertSeries:
    """Build the keep-alive cut on the internal ka net, pull-down on the WD side."""
    return InsertSeries(
        label="F7",
        net="ka",
        pins=("U1.2",),
        part=TransformPart("FI1/SWKA", StubSwitch(a="@a", b1="@b", s="@control")),
        control="KA_CUT",
        extra=(
            TransformPart(
                "FI1/RPD",
                Resistor("47k", a="@b", b="GND", footprint="StubFP:R_0603"),
            ),
        ),
    )


def f2() -> AddShunt:
    """Build the short-to-GND leg on the cable side of the break switch."""
    return AddShunt(
        label="F2",
        net="TX_A#b",
        rail="GND",
        part=TransformPart("FI1/SWAG", StubSwitch(a="@net", b1="@leg", s="@control")),
        control="SHG_A",
        extra=(
            TransformPart(
                "FI1/RSG",
                Resistor("470", a="@leg", b="GND", footprint="StubFP:R_0603"),
            ),
        ),
    )


def h1() -> Substitute:
    """Build the pot-wiper override mux: human driver on @b, supervisor on @source."""
    return Substitute(
        label="H1",
        net="pot",
        pins=("U1.3",),
        part=TransformPart(
            "FI1/SWM",
            StubSwitch(a="@a", b1="@b", b2="@source", s="@control"),
        ),
        source="SUP_PWM",
        control="POT_SEL",
    )


def per_tile() -> tuple[Transform, ...]:
    """Return the per-tile transform set: F1, F7, F2."""
    return (f1(), f7(), f2())


def net_pins(circuit: Circuit, name: str) -> set[str]:
    """Collect the pin addresses on a net, for assertions."""
    return {f"{pin.part.ref}.{pin.number}" for pin in circuit.nets[name].pins}


def test_insert_series_on_a_port_net(symbols: StubSymbols) -> None:
    board = build_board(symbols)
    handles = apply_transforms(board, [PerTile(Tile, per_tile())])
    tile = board.instances["T0"].circuit
    # The detached side is a fresh internal net holding just Rat.b and
    # the switch throw that bridges it — addressed by its typed pin
    # keyword, like the settled transform list's PHY1/Rat.b.
    assert net_pins(tile, "TX_A#a") == {"PHY1/Rat.2", "FI1/SWAB.2"}
    # The port keeps its name and flag as the #b side.
    assert tile.nets["TX_A"].is_port
    assert net_pins(tile, "TX_A") == {
        "J2.5",
        "PHY1/Dat.1",
        "FI1/SWAB.1",
        "FI1/SWAG.1",
    }
    # The switch bridges the sides; its control pin escaped to a port.
    sw = tile.parts["FI1/SWAB"]
    assert sw.pin("1").net is tile.nets["TX_A"]
    assert sw.pin("2").net is tile.nets["TX_A#a"]
    assert sw.pin("4").net is tile.nets["BRK_A"]
    assert tile.nets["BRK_A"].is_port
    board_net = handles[(("T0",), "BRK_A")]
    assert board_net.name == "T0/BRK_A"
    assert board_net is board.nets["T0/BRK_A"]


def test_insert_series_on_an_internal_net(symbols: StubSymbols) -> None:
    board = build_board(symbols)
    apply_transforms(board, [PerTile(Tile, per_tile())])
    tile = board.instances["T0"].circuit
    # An internal net splits into fresh #a/#b nets; the base is gone.
    assert "ka" not in tile.nets
    assert net_pins(tile, "ka#a") == {"U1.2", "FI1/SWKA.1"}
    assert net_pins(tile, "ka#b") == {"Rwd.1", "FI1/SWKA.2", "FI1/RPD.1"}
    # The extra part wires the split's #b side and a rail by name.
    rpd = tile.parts["FI1/RPD"]
    assert rpd.pin("1").net is tile.nets["ka#b"]
    assert rpd.pin("2").net is tile.nets["GND"]


def test_add_shunt_hangs_a_branch_without_cutting(symbols: StubSymbols) -> None:
    board = build_board(symbols)
    handles = apply_transforms(board, [PerTile(Tile, per_tile())])
    tile = board.instances["T0"].circuit
    # No cut: the base net keeps its pins, plus the branch's (and the
    # F1 break switch's interface side from the same plan).
    assert net_pins(tile, "TX_A") == {
        "J2.5",
        "PHY1/Dat.1",
        "FI1/SWAB.1",
        "FI1/SWAG.1",
    }
    # The @leg placeholder shares one fresh net between part and extra.
    assert net_pins(tile, "F2_leg") == {"FI1/SWAG.2", "FI1/RSG.1"}
    rsg = tile.parts["FI1/RSG"]
    assert rsg.pin("2").net is tile.nets["GND"]
    assert handles[(("T0",), "SHG_A")].name == "T0/SHG_A"


def test_add_tap_exports_an_internal_net(symbols: StubSymbols) -> None:
    board = build_board(symbols)
    handles = apply_transforms(
        board, [PerInstance(("T0",), (AddTap(label="B1", net="sense"),))]
    )
    tile = board.instances["T0"].circuit
    assert tile.nets["sense"].is_port
    tap = handles[(("T0",), "sense")]
    assert tap.name == "T0/sense"
    flat = board.flatten()
    # The tap rides the exported net: the sense pins sit on the board
    # net the handle names (flattening copies net objects, so compare
    # by name, not identity).
    assert flat.parts["T0/PHY1/Rat"].pin("1").net is flat.nets["T0/sense"]
    assert net_pins(flat, tap.name) == {"T0/PHY1/Rat.1", "T0/U1.1"}
    # T1's sense stays tile-internal.
    assert flat.parts["T1/PHY1/Rat"].pin("1").net is flat.nets["T1/sense"]


def test_add_tap_on_a_split_alias_rides_the_binding(symbols: StubSymbols) -> None:
    board = build_board(symbols)
    handles = apply_transforms(
        board,
        [PerTile(Tile, per_tile()), PerInstance(("T0",), (AddTap("B2", "TX_A#b"),))],
    )
    # The #b side of a port split is the port itself — already bound to
    # the segment net, so the tap needs no new board net.
    assert handles[(("T0",), "TX_A#b")] is board.nets["SEG_A"]


def test_substitute_cuts_and_escapes_the_source(symbols: StubSymbols) -> None:
    board = build_board(symbols)
    handles = apply_transforms(board, [PerInstance(("T1",), (h1(),))])
    tile = board.instances["T1"].circuit
    assert "pot" not in tile.nets
    assert net_pins(tile, "pot#a") == {"U1.3", "FI1/SWM.1"}
    assert net_pins(tile, "pot#b") == {"Rpot.1", "FI1/SWM.2"}
    swm = tile.parts["FI1/SWM"]
    assert swm.pin("1").net is tile.nets["pot#a"]
    assert swm.pin("2").net is tile.nets["pot#b"]
    assert swm.pin("3").net is tile.nets["SUP_PWM"]
    assert swm.pin("4").net is tile.nets["POT_SEL"]
    assert handles[(("T1",), "SUP_PWM")].name == "T1/SUP_PWM"
    assert handles[(("T1",), "POT_SEL")].name == "T1/POT_SEL"


def test_per_tile_keying_instruments_every_instance(symbols: StubSymbols) -> None:
    board = build_board(symbols)
    apply_transforms(board, [PerTile(Tile, (f1(),))])
    for name in ("T0", "T1"):
        assert "FI1/SWAB" in board.instances[name].circuit.parts
    assert "FI1/SWAB" not in board.instances["X1"].circuit.parts


def test_per_instance_declarations_stack_on_per_tile(symbols: StubSymbols) -> None:
    board = build_board(symbols)
    handles = apply_transforms(
        board,
        [PerTile(Tile, per_tile()), PerInstance(("T0",), (AddTap("B1", "sense"),))],
    )
    assert (("T0",), "sense") in handles
    assert (("T1",), "sense") not in handles
    assert board.instances["T1"].circuit.nets["sense"].is_port is False


def test_provenance_survives_flattening(symbols: StubSymbols) -> None:
    board = build_board(symbols)
    apply_transforms(
        board,
        [
            PerTile(Tile, per_tile()),
            PerInstance(("T0",), (AddTap("B1", "sense"),)),
            PerInstance(("T1",), (h1(),)),
        ],
    )
    # Pre-flatten: the tile-scope artifacts carry their tags.
    tile0 = board.instances["T0"].circuit
    assert tile0.parts["FI1/SWAB"].provenance == Provenance("F1", "TX_A")
    assert tile0.nets["TX_A#a"].provenance == Provenance("F1", "TX_A")
    assert tile0.nets["BRK_A"].provenance == Provenance("F1", "TX_A")
    assert tile0.nets["F2_leg"].provenance == Provenance("F2", "TX_A")
    # Base-capture elements stay untagged.
    assert tile0.parts["U1"].provenance is None
    assert tile0.nets["TX_A"].provenance is None
    flat = board.flatten()
    assert flat.parts["T0/FI1/SWAB"].provenance == Provenance("F1", "TX_A")
    assert flat.parts["T1/FI1/SWM"].provenance == Provenance("H1", "pot")
    assert flat.nets["T0/TX_A#a"].provenance == Provenance("F1", "TX_A")
    assert flat.nets["T0/BRK_A"].provenance == Provenance("F1", "TX_A")
    assert flat.nets["T0/sense"].provenance == Provenance("B1", "sense")
    # Hierarchy metadata survives the per-tile flatten intact.
    assert flat.parts["T0/PHY1/Rat"].path == ("T0", "PHY1")
    assert flat.parts["T0/FI1/SWAB"].path == ("T0",)
    # And annotation's renamed pass keeps the tags.
    renamed = flat.renamed({})
    assert renamed.parts["T0/FI1/SWAB"].provenance == Provenance("F1", "TX_A")


def test_series_control_net_merges_into_the_board_at_flatten(
    symbols: StubSymbols,
) -> None:
    board = build_board(symbols)
    apply_transforms(board, [PerTile(Tile, per_tile())])
    flat = board.flatten()
    sw = flat.parts["T0/FI1/SWAB"]
    assert sw.pin("4").net is flat.nets["T0/BRK_A"]
    # The port base net merged into the segment binding; the switch's
    # interface-side pin sits on it.
    assert sw.pin("1").net is flat.nets["SEG_A"]


def test_waivers_survive_the_per_tile_flatten(symbols: StubSymbols) -> None:
    board = build_board(symbols)
    board.instances["T0"].circuit.waive(
        "range-containment", "sense", reason="test waiver"
    )
    apply_transforms(board, [PerTile(Tile, (f1(),))])
    assert Waiver("range-containment", "T0/sense", "test waiver") in (
        hierarchical_waivers(board)
    )


def test_unknown_net_raises(symbols: StubSymbols) -> None:
    board = build_board(symbols)
    with pytest.raises(DefinitionError, match="no net 'nope'"):
        apply_transforms(
            board,
            [
                PerTile(
                    Tile,
                    (
                        InsertSeries(
                            label="F9",
                            net="nope",
                            pins=("J2.5",),
                            part=TransformPart(
                                "FI1/SW", StubSwitch(a="@a", b1="@b", s="GND")
                            ),
                        ),
                    ),
                )
            ],
        )


def test_detached_pin_not_on_the_net_raises(symbols: StubSymbols) -> None:
    board = build_board(symbols)
    with pytest.raises(DefinitionError, match="is not on net 'TX_A'"):
        apply_transforms(
            board,
            [
                PerTile(
                    Tile,
                    (
                        InsertSeries(
                            label="F9",
                            net="TX_A",
                            pins=("U1.2",),
                            part=TransformPart(
                                "FI1/SW", StubSwitch(a="@a", b1="@b", s="GND")
                            ),
                        ),
                    ),
                )
            ],
        )


def test_unknown_instance_path_raises(symbols: StubSymbols) -> None:
    board = build_board(symbols)
    with pytest.raises(DefinitionError, match="no instance at path 'T9'"):
        apply_transforms(
            board, [PerInstance(("T9",), (AddTap(label="B9", net="sense"),))]
        )


def test_duplicate_label_raises(symbols: StubSymbols) -> None:
    board = build_board(symbols)
    with pytest.raises(DefinitionError, match="duplicate transform label 'F1'"):
        apply_transforms(board, [PerTile(Tile, (f1(), f1()))])


def test_nested_scopes_raise(symbols: StubSymbols) -> None:
    board = build_board(symbols)
    with pytest.raises(DefinitionError, match="transform scopes nest"):
        apply_transforms(
            board,
            [
                PerTile(Tile, (f1(),)),
                PerInstance(("T0", "PHY1"), (AddTap("X", "mcu_rx"),)),
            ],
        )


def test_control_declared_but_unwired_raises(symbols: StubSymbols) -> None:
    board = build_board(symbols)
    with pytest.raises(DefinitionError, match="not wired by any part"):
        apply_transforms(
            board,
            [
                PerTile(
                    Tile,
                    (
                        InsertSeries(
                            label="F9",
                            net="TX_A",
                            pins=("J2.5",),
                            part=TransformPart(
                                "FI1/SW", StubSwitch(a="@a", b1="@b", s="GND")
                            ),
                            control="BRK_A",
                        ),
                    ),
                )
            ],
        )


def test_control_wired_but_undeclared_raises(symbols: StubSymbols) -> None:
    board = build_board(symbols)
    with pytest.raises(DefinitionError, match="no control port is declared"):
        apply_transforms(
            board,
            [
                PerTile(
                    Tile,
                    (
                        InsertSeries(
                            label="F9",
                            net="TX_A",
                            pins=("J2.5",),
                            part=TransformPart(
                                "FI1/SW", StubSwitch(a="@a", b1="@b", s="@control")
                            ),
                        ),
                    ),
                )
            ],
        )


def test_multi_unit_spec_rejected(symbols: StubSymbols) -> None:
    board = build_board(symbols)
    with pytest.raises(DefinitionError, match="multi-unit specs are unsupported"):
        apply_transforms(
            board,
            [
                PerTile(
                    Tile,
                    (
                        InsertSeries(
                            label="F9",
                            net="TX_A",
                            pins=("J2.5",),
                            part=TransformPart("FI1/QD", Bat54adw()),
                        ),
                    ),
                )
            ],
        )


def test_instrumented_board_passes_check(
    symbols: StubSymbols, footprints: StubFootprints
) -> None:
    board = build_board(symbols)
    handles = apply_transforms(
        board,
        [
            PerTile(Tile, per_tile()),
            PerInstance(("T0",), (AddTap("B1", "sense"),)),
            PerInstance(("T1",), (h1(),)),
        ],
    )
    # Wire a scan-plane stand-in to the escaped nets it reaches.
    scan = board.part(
        "SCAN", symbol="Stub:CONN6", value="Scan", footprint="StubFP:CONN_1x06"
    )
    for pin, net in zip(scan.pins, handles.values(), strict=False):
        board.connect(net, pin)
    raise_on_errors(check(board, footprints=footprints))
