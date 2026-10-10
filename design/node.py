"""The oparroy ring node, captured as a board (DESIGN.md §2-§4, §7).

One node = CH32V003 + PHY front-end (``design/phy_frontend.py``) +
charge-pump watchdog (``design/watchdog_chargepump.py``) + status LEDs
(§4.1) + terminal protection (§7 checklist, inside the PHY block) + the
two §3 segment connectors (``design/segment.py``). ``Node`` is a
subcircuit: the node board below captures it directly, and the CI board
tiles it eight times — one capture, both boards.

MCU pin budget: pads bind from ``design/node_pins.py`` — the one
authoritative table (15 function requests + the SWIO reservation =
16 of 18 GPIO, PC1 and PC7 spare; datasheets/CH32V003/notes/gpio-pinout.md).
The plain node wires the ring PHY (the OPA pads, TIM1 TX channels,
the brake), the watchdog (keepalive; TIM1_BKIN = ``sel`` — bypass
engaging brakes both TX channels, §2/§4), the status LEDs (passive
power, working heartbeat, and the per-connector pair merged onto one
antiparallel GPIO, §4.1), OPO (the §2 DNP hysteresis fallback), the
SWIO pad, and the PC7 spare — landed on a TP4 test pad for bring-up
observability. The payload pads (debug TX, pot, buzzer,
buttons — the §6 demonstrator superset) and the freed PC1 stay
unconnected on this board; the checker reports them by name as
warnings, not errors.

Usage (in the nix dev shell):

    python -m design.node                          # check + KiCad netlist
    python -m design.node --dot                    # Graphviz view
    python -m design.node --annotation FILE        # stable refdes file
    python -m design.node --footprints FILE        # footprint overrides
    python -m design.node --back-annotate X.kicad_pcb --annotation FILE
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from design.bins import C0603
from design.ch32v003 import Ch32v003f4p6
from design.node_pins import capture as capture_pin_map
from design.phy_frontend import PhyFrontEnd
from design.segment import SegmentConnector, segment_ports
from design.status_leds import StatusLeds
from design.watchdog_chargepump import WatchdogChargePump
from oparroy.dsl import (
    Annotation,
    Circuit,
    KiCadLibraries,
    Subcircuit,
    SymbolTable,
    TypedPart,
    annotate,
    annotation_from_pcb,
    apply_annotation,
    assign_footprints,
    check,
    emit_netlist,
    overrides_from_json,
    raise_on_errors,
    to_dot,
)

if TYPE_CHECKING:
    from oparroy.dsl import Net


class TestPoint(TypedPart):
    """A single-pin test point (``Connector:TestPoint``) — the pogo pads."""

    symbol = "Connector:TestPoint"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {"p": "1"}
    default_footprint = "TestPoint:TestPoint_Pad_1.5x1.5mm"

    def __init__(self, value: str, *, p: Net | str) -> None:
        super().__init__(value, None, {"p": p})


class Node(Subcircuit):
    """One ring node: the unit the node board captures and the CI board tiles."""

    def capture(self, circuit: Circuit) -> None:
        """Build the node; the interface is the §3 segment pinout."""
        upstream, downstream = segment_ports(circuit)
        v3v3 = upstream["v3v3"]
        gnd = upstream["gnd"]

        sel = circuit.net("sel")
        ka = circuit.net("ka")
        opa_p = circuit.net("opa_p")
        opa_n = circuit.net("opa_n")
        opa_p_b = circuit.net("opa_p_b")
        opo = circuit.net("opo")
        txa_drv = circuit.net("txa_drv")
        txb_drv = circuit.net("txb_drv")
        led_work = circuit.net("led_work")
        led_seg = circuit.net("led_seg")
        swio = circuit.net("swio")
        pc7 = circuit.net("pc7")

        circuit.part("J1", SegmentConnector(upstream))
        circuit.part("J2", SegmentConnector(downstream))

        circuit.instance(
            "PHY1",
            PhyFrontEnd(),
            rx_a=upstream["a"],
            tx_a=downstream["a"],
            rx_b=downstream["b"],
            tx_b=upstream["b"],
            mcu_rx_a=opa_p,
            mcu_vdd2=opa_n,
            mcu_rx_b=opa_p_b,
            mcu_tx_a=txa_drv,
            mcu_tx_b=txb_drv,
            mcu_opo=opo,
            sel=sel,
            v3v3=v3v3,
            gnd=gnd,
        )
        circuit.instance("WD1", WatchdogChargePump(), ka=ka, sel=sel, GND=gnd)

        # MCU pads bind from the one authoritative table
        # (design/node_pins.py): function name -> bound pad -> typed-part
        # keyword. Functions the plain node doesn't carry (the §6
        # payload superset) stay unbound here and unwired on the board.
        pin_map = capture_pin_map()
        mcu_nets = {
            "rx_threshold": opa_n,
            "rx_a": opa_p,
            "rx_b": opa_p_b,
            "comp_out": opo,
            "tx_a": txa_drv,
            "tx_b": txb_drv,
            "tx_kill": sel,
            "keepalive": ka,
            "led_working": led_work,
            "led_segments": led_seg,
        }
        pads = pin_map.assignments
        circuit.part(
            "U1",
            Ch32v003f4p6(
                vdd=v3v3,
                vss=gnd,
                pd1=swio,  # the table's SWIO reservation, PD1
                pc7=pc7,  # the table's spare — TP4 test pad
                # Pad names arrive as data from the pin table — static
                # checking can't follow the unpack; the pin map's typed
                # binding and the capture checker cover it instead.
                **{  # ty: ignore[invalid-argument-type]
                    pads[f].name.lower(): net for f, net in mcu_nets.items()
                },
            ),
        )

        # Decoupling: 100n at the VDD pin, 10u bulk for the node.
        circuit.part("C1", C0603("100n", a=v3v3, b=gnd))
        circuit.part("C2", C0603("10u", a=v3v3, b=gnd))

        # §4.1 status LEDs: the StatusLeds subcircuit (power, working,
        # antiparallel link pair on led_seg) — its drive-state contract
        # is sim-asserted in circuits/status-leds/tb_status_leds.cir.
        circuit.instance(
            "SL1",
            StatusLeds(),
            v3v3=v3v3,
            gnd=gnd,
            led_work=led_work,
            led_seg=led_seg,
        )

        # Programming: the SWIO + 3V3 + GND pogo strip (§6 production
        # flow). The programmer powers the board — brick recovery is a
        # power cycle through reset (datasheets/CH32V003/notes/quirks.md
        # §Debug) — so 3V3 here comes from the WCH-LinkE, never the ring.
        circuit.part("TP1", TestPoint("SWIO", p=swio))
        circuit.part("TP2", TestPoint("3V3", p=v3v3))
        circuit.part("TP3", TestPoint("GND", p=gnd))
        # The PC7 spare lands on a bare pad — bring-up observability and
        # a future expansion point without a respin.
        circuit.part("TP4", TestPoint("PC7", p=pc7))


def capture(symbols: SymbolTable) -> Circuit:
    """Build the standalone node-board IR: one Node, nothing else."""
    circuit = Circuit("oparroy-node", symbols)
    Node().capture(circuit)
    return circuit


def main() -> None:
    """Check the capture and emit the annotated KiCad netlist (§7 pipeline).

    The stages between capture and pcbnew are explicit: footprint
    assignment (``--footprints`` overrides on top of the class defaults),
    then annotation (``--annotation`` keeps refdes stable across source
    edits; ``--back-annotate`` folds pcbnew's placement-driven
    renumbering back in). Emission is always post-annotation, so the
    netlist pcbnew ingests carries board refdes.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dot",
        action="store_true",
        help="emit the Graphviz dot view instead of the KiCad netlist",
    )
    parser.add_argument(
        "--annotation",
        type=Path,
        help="annotation JSON file: read for stability, rewritten refreshed",
    )
    parser.add_argument(
        "--footprints",
        type=Path,
        help="footprint-override JSON applied after the class defaults",
    )
    parser.add_argument(
        "--back-annotate",
        type=Path,
        metavar="KICAD_PCB",
        help="derive the annotation from a .kicad_pcb (needs --annotation)",
    )
    args = parser.parse_args()
    if args.back_annotate is not None and args.annotation is None:
        parser.error("--back-annotate needs --annotation to write to")
    libs = KiCadLibraries.from_env()
    circuit = capture(libs)
    if args.dot:
        sys.stdout.write(to_dot(circuit))
        return
    if args.footprints is not None:
        overrides = overrides_from_json(args.footprints.read_text(encoding="utf-8"))
        circuit = assign_footprints(circuit, overrides)
    issues = check(circuit, footprints=libs)
    for issue in issues:
        sys.stderr.write(f"{issue}\n")
    raise_on_errors(issues)

    prior = None
    if args.annotation is not None and args.annotation.is_file():
        prior = Annotation.from_json(args.annotation.read_text(encoding="utf-8"))
    if args.back_annotate is not None:
        prior = annotation_from_pcb(
            circuit, args.back_annotate.read_text(encoding="utf-8"), prior=prior
        )
    annotation = annotate(circuit, prior=prior)
    if args.annotation is not None:
        args.annotation.write_text(annotation.to_json(), encoding="utf-8")
    sys.stdout.write(emit_netlist(apply_annotation(circuit, annotation)))


if __name__ == "__main__":
    main()
