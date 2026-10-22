"""The scan control/observe plane, captured (docs/scan-plane.md).

One daisy chain of 11 x 74HC595 (control) + 2 x 74HC165 (observe)
from the RP2040 and back (§1): RP2040 -> AUX0 -> AUX1 -> AUX2 -> T0
... T7 -> OBS0 -> OBS1 -> RP2040, SRCLK and COMMIT broadcast to all 13
stages, /OE on the 595s only. ``Hc595Stage``/``Hc165Stage`` are the
stage captures (100 nF decoupling per stage, /SRCLR tied high,
CLK_INH low — §4/§7); ``ScanPlane`` composes the full chain and exposes
the §3 bit map as named ports for the board composition to wire to the
transform handles (`design/ci_instrumentation.py`).

The §4 POR discipline in capture form: one shared 47 kΩ pull-up on
/OE, and a 47 kΩ pull-down on every control line — except the FET-gate
lines (`PWR`, `BTN_*`), whose transform-side gate pull-downs double as
their lines' (instrumented-ci.md §7's closing note): 63 switch-select
pull-downs in the plane, 16 gate pull-downs in the transforms, 79
control bits total (the measurement tile's slice drives only `PWR` —
instrumented-ci.md §12). The reset state this constructs — all-zeros —
is the equivalence proof's `reset_levels` input.

The §5 SWIO/debug trees: two 8:1 binary trees of SN74LVC1G3157 ganged
to the SWIO_A2..A0 select bits (bit weight = node address, one bit per
tree level). ``SwioTree`` carries the §5 pull-up placement — per-leaf
10 kΩ to the leaf's own `3V3N` (a ``rail`` port per leaf, so a
power-cut node has no back-feed path), 4.7 kΩ at the root to the
always rail; ``DebugTree`` is the same topology bare — its leaves are
actively driven push-pull, and a selected dead node reads as garbage,
which the emit-and-forget contract tolerates (§5).

Usage (in the nix dev shell):

    python -m design.scan_plane            # check + KiCad netlist
    python -m design.scan_plane --dot      # Graphviz view
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from design.bins import C0603, R0603
from design.ci_parts import Sn74hc165, Sn74hc595
from design.ci_tiles import MEASUREMENT_TILE
from design.phy_frontend import Sn74lvc1g3157
from oparroy.dsl import (
    Circuit,
    KiCadLibraries,
    PowerDomainKind,
    Subcircuit,
    SymbolTable,
    check,
    emit_netlist,
    raise_on_errors,
    solve,
    to_dot,
)

if TYPE_CHECKING:
    from oparroy.dsl import Net

#: Width of one shift-register stage (74HC595 / 74HC165 both carry 8).
_STAGE_WIDTH = 8

#: The per-tile control byte, bit 0 = QA ... bit 7 = QH (§3): the
#: F1-F8 transform set's bits in wire order.
TILE_BITS = ("brk_a", "shg_a", "shv_a", "brk_b", "shg_b", "shv_b", "ka_cut", "pwr")

#: AUX0: the supervisor originator-port injector (same order as the
#: tile byte) + the SWIO tree's low select bits.
AUX0_BITS = (
    "sup_brk_a",
    "sup_shg_a",
    "sup_shv_a",
    "sup_brk_b",
    "sup_shg_b",
    "sup_shv_b",
    "swio_a0",
    "swio_a1",
)

#: AUX1: the SWIO tree's high select bit, the boundary watchdog
#: defeat, input tiles 1/3 overrides.
AUX1_BITS = (
    "swio_a2",
    "wd_defeat",
    "pot_sel1",
    "btn_a1",
    "btn_b1",
    "pot_sel3",
    "btn_a3",
    "btn_b3",
)

#: AUX2: input tiles 5/7 overrides; bits 6/7 are the §1 spare pair.
AUX2_BITS = ("pot_sel5", "btn_a5", "btn_b5", "pot_sel7", "btn_a7", "btn_b7")


def tile_bits(tile: int) -> tuple[str, ...]:
    """One tile's control byte: F1-F8's bits, or PWR alone on the measurement tile.

    The measurement tile (instrumented-ci.md §12) drops the injector
    and keep-alive transforms, so its 595 slice drives `pwr` only; the
    stage's seven remaining outputs are spares, filled like AUX2's.
    """
    return ("pwr",) if tile == MEASUREMENT_TILE else TILE_BITS


def _gate_pulldown_covers(bit: str) -> bool:
    """Return True when the transform FET-gate pull-down doubles as the line's."""
    return bit.endswith("_pwr") or bit.startswith("btn_")


class Hc595Stage(Subcircuit):
    """One 74HC595 control stage with its 100 nF (§1/§4: /SRCLR high)."""

    def capture(self, circuit: Circuit) -> None:
        """Build the stage: ser in/out, the broadcast clocks, q0..q7."""
        ser_in = circuit.port("ser_in")
        ser_out = circuit.port("ser_out")
        srclk = circuit.port("srclk")
        commit = circuit.port("commit")
        oe_n = circuit.port("oe_n")
        v3v3 = circuit.port("v3v3")
        gnd = circuit.port("gnd")
        q = [circuit.port(f"q{index}") for index in range(8)]
        circuit.part(
            "U1",
            Sn74hc595(
                qa=q[0],
                qb=q[1],
                qc=q[2],
                qd=q[3],
                qe=q[4],
                qf=q[5],
                qg=q[6],
                qh=q[7],
                qh_dash=ser_out,
                ser=ser_in,
                srclk=srclk,
                rclk=commit,
                srclr=v3v3,
                oe=oe_n,
                vcc=v3v3,
                gnd=gnd,
            ),
        )
        circuit.part("C1", C0603("100n", a=v3v3, b=gnd), note="decoupling for {U1}")


class Hc165Stage(Subcircuit):
    """One 74HC165 observe stage with its 100 nF (§1: CLK_INH low)."""

    def capture(self, circuit: Circuit) -> None:
        """Build the stage: d0..d7 parallel in, ser in/out."""
        ser_in = circuit.port("ser_in")
        ser_out = circuit.port("ser_out")
        srclk = circuit.port("srclk")
        commit = circuit.port("commit")
        v3v3 = circuit.port("v3v3")
        gnd = circuit.port("gnd")
        d = [circuit.port(f"d{index}") for index in range(8)]
        circuit.part(
            "U1",
            Sn74hc165(
                d0=d[0],
                d1=d[1],
                d2=d[2],
                d3=d[3],
                d4=d[4],
                d5=d[5],
                d6=d[6],
                d7=d[7],
                ser=ser_in,
                clk=srclk,
                clk_inh=gnd,
                sh_ld=commit,
                qh=ser_out,
                vcc=v3v3,
                gnd=gnd,
            ),
        )
        circuit.part("C1", C0603("100n", a=v3v3, b=gnd), note="decoupling for {U1}")


class ScanPlane(Subcircuit):
    """The full 13-stage daisy chain with the §3 bit map as named ports."""

    def capture(self, circuit: Circuit) -> None:
        """Build the chain: AUX0-2, T0-7, OBS0-1, and the §4 discipline."""
        srclk = circuit.port("srclk")
        sdo = circuit.port("sdo")
        sdi = circuit.port("sdi")
        commit = circuit.port("commit")
        oe_n = circuit.port("oe_n")
        v3v3 = circuit.port("3V3")
        gnd = circuit.port("GND")
        circuit.power_domain(v3v3, kind=PowerDomainKind.ALWAYS)
        circuit.power_domain(gnd, kind=PowerDomainKind.GROUND)

        # §4: /OE pulled up — every 595 output Hi-Z until firmware
        # latches the zero word and drives /OE low.
        circuit.part("R_OE", R0603("47k", a=oe_n, b=v3v3), note="/OE pull-up (§4)")

        control: list[tuple[str, list[Net]]] = []
        for stage, bits in (
            ("AUX0", AUX0_BITS),
            ("AUX1", AUX1_BITS),
            ("AUX2", AUX2_BITS),
        ):
            control.append((stage, [circuit.port(bit) for bit in bits]))
        control.extend(
            (f"T{tile}", [circuit.port(f"t{tile}_{bit}") for bit in tile_bits(tile)])
            for tile in range(8)
        )

        prev = sdo
        for stage, q in control:
            # AUX2's two spare outputs (§1): internal nets, reported by
            # name as single-pin warnings.
            while len(q) < _STAGE_WIDTH:
                q.append(circuit.net(f"{stage.lower()}_spare{len(q)}"))
            for net in q:
                # §4: every control line's 47 kΩ pull-down defines the
                # Hi-Z window — except the FET-gate lines, whose
                # transform-side pull-downs double as theirs.
                if net.is_port and not _gate_pulldown_covers(net.name):
                    circuit.part(
                        f"R_{net.name.upper()}",
                        R0603("47k", a=net, b=gnd),
                        note="control pull-down (§4)",
                    )
            link = circuit.net(f"chain_{stage.lower()}")
            circuit.instance(
                stage,
                Hc595Stage(),
                ser_in=prev,
                ser_out=link,
                srclk=srclk,
                commit=commit,
                oe_n=oe_n,
                v3v3=v3v3,
                gnd=gnd,
                **{f"q{index}": net for index, net in enumerate(q)},
            )
            prev = link

        for obs, tiles in (("OBS0", range(4)), ("OBS1", range(4, 8))):
            d = [
                circuit.port(f"t{tile}_{sense}")
                for tile in tiles
                for sense in ("sel", "3v3n")
            ]
            link = sdi if obs == "OBS1" else circuit.net(f"chain_{obs.lower()}")
            circuit.instance(
                obs,
                Hc165Stage(),
                ser_in=prev,
                ser_out=link,
                srclk=srclk,
                commit=commit,
                v3v3=v3v3,
                gnd=gnd,
                **{f"d{index}": net for index, net in enumerate(d)},
            )
            prev = link


def _capture_tree(circuit: Circuit, *, leaf_pullups: bool) -> None:
    """Capture one 8:1 3157 binary tree, three ganged select levels (§5).

    Bit weight = node address: the root switch takes ``swio_a2``, the
    middle pair ``swio_a1``, the leaf quad ``swio_a0``; S low connects
    B1, so address bit 0 routes through B1 at every level.
    """
    root = circuit.port("root")
    v3v3 = circuit.port("3V3")
    gnd = circuit.port("GND")
    circuit.power_domain(v3v3, kind=PowerDomainKind.ALWAYS)
    circuit.power_domain(gnd, kind=PowerDomainKind.GROUND)
    sel = [circuit.port(f"swio_a{index}") for index in range(3)]
    leaves = [circuit.port(f"leaf{index}") for index in range(8)]
    mid = [circuit.net(f"mid{index}") for index in range(2)]
    low = [circuit.net(f"low{index}") for index in range(4)]
    circuit.part(
        "SW1",
        Sn74lvc1g3157(a=root, b1=mid[0], b2=mid[1], s=sel[2], vcc=v3v3, gnd=gnd),
    )
    for index in range(2):
        circuit.part(
            f"SW{2 + index}",
            Sn74lvc1g3157(
                a=mid[index],
                b1=low[2 * index],
                b2=low[2 * index + 1],
                s=sel[1],
                vcc=v3v3,
                gnd=gnd,
            ),
        )
    for index in range(4):
        circuit.part(
            f"SW{4 + index}",
            Sn74lvc1g3157(
                a=low[index],
                b1=leaves[2 * index],
                b2=leaves[2 * index + 1],
                s=sel[0],
                vcc=v3v3,
                gnd=gnd,
            ),
        )
    if leaf_pullups:
        # §5: per-leaf 10 kΩ to the leaf's own 3V3N (no back-feed into
        # a power-cut node), 4.7 kΩ at the root to the always rail.
        for index, leaf in enumerate(leaves):
            rail = circuit.port(f"rail{index}")
            circuit.power_domain(rail, kind=PowerDomainKind.SWITCHED)
            circuit.part(
                f"RU{index}",
                R0603("10k", a=leaf, b=rail),
                note="leaf pull-up, to the node's 3V3N (§5)",
            )
        circuit.part("RUR", R0603("4k7", a=root, b=v3v3), note="root pull-up (§5)")


class SwioTree(Subcircuit):
    """The §5 SWIO flash mux: an 8:1 3157 tree with the pull-up placement."""

    def capture(self, circuit: Circuit) -> None:
        """Build the tree with per-leaf 10 kΩ and the 4.7 kΩ root pull-up."""
        _capture_tree(circuit, leaf_pullups=True)


class DebugTree(Subcircuit):
    """The §5 debug-return tree: the same 8:1 topology, no pull-ups."""

    def capture(self, circuit: Circuit) -> None:
        """Build the bare tree; leaves land on the tiles' PD5 debug_tx."""
        _capture_tree(circuit, leaf_pullups=False)


def capture(symbols: SymbolTable) -> Circuit:
    """Build the standalone scan-plane IR: the 13-stage chain."""
    circuit = Circuit("scan-plane", symbols)
    ScanPlane().capture(circuit)
    return circuit


def main() -> None:
    """Check the capture and emit the KiCad netlist (--dot: the other view)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dot",
        action="store_true",
        help="emit the Graphviz dot view instead of the KiCad netlist",
    )
    args = parser.parse_args()
    libs = KiCadLibraries.from_env()
    circuit = capture(libs)
    report = solve(circuit)
    if resolutions := str(report):
        sys.stderr.write(f"{resolutions}\n")
    raise_on_errors(report.issues)
    issues = check(circuit, footprints=libs)
    for issue in issues:
        sys.stderr.write(f"{issue}\n")
    raise_on_errors(issues)
    if args.dot:
        sys.stdout.write(to_dot(circuit))
    else:
        sys.stdout.write(emit_netlist(circuit))


if __name__ == "__main__":
    main()
