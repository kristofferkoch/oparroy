"""The oparroy ring node, captured as a board (DESIGN.md §2-§4, §7).

One node = CH32V003 + PHY front-end (``design/phy_frontend.py``) +
charge-pump watchdog (``design/watchdog_chargepump.py``) + status LEDs
(§4.1) + terminal protection (§7 checklist, inside the PHY block) + the
two §3 segment connectors (``design/segment.py``). ``Node`` is a
subcircuit: the node board below captures it directly, and the CI board
(T10) tiles it eight times — one capture, both boards.

MCU pin budget (F4P6 pin map: datasheets/CH32V003/notes/gpio-pinout.md):

- PA1/PA2 (OPA_N0/OPP0): ring-A threshold and RX tap; PD7 (OPP1):
  ring-B RX — the §3 firmware RX-source select
- PD2/PC3 (TIM1_CH1/CH3): TX_A/TX_B, identical compare values (§3)
- PC2 (TIM1_BKIN): hardware TX-kill, wired to the watchdog's ``sel`` —
  bypass engaging brakes both TX channels (§2, §4)
- PC4: keep-alive strobe for the charge pump (GPIO, 20 kHz)
- PC7/PC5/PC6: working / upstream / downstream status LEDs (§4.1)
- PD4 (OPA_OUT): the DNP hysteresis fallback (§2); PD1: SWIO debug pad

Unassigned pins (PD0, PD3, PD5, PD6, PC0, PC1) stay unconnected —
the checker reports them by name as warnings, not errors.

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

from design.bins import C0603, R0603, Led0603
from design.ch32v003 import Ch32v003f4p6
from design.phy_frontend import PhyFrontEnd
from design.segment import SegmentConnector, segment_ports
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
    """A single-pin test point (``Connector:TestPoint``) — the SWIO pad."""

    symbol = "Connector:TestPoint"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {"p": "1"}
    default_footprint = "TestPoint:TestPoint_Pad_1.5x1.5mm"

    def __init__(self, value: str, *, p: Net | str) -> None:
        super().__init__(value, None, {"p": p})


class Node(Subcircuit):
    """One ring node: the unit the node board captures and T10 tiles."""

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
        led_up = circuit.net("led_up")
        led_down = circuit.net("led_down")
        swio = circuit.net("swio")
        pwr_led = circuit.net("pwr_led")
        ledw_a = circuit.net("ledw_a")
        ledu_a = circuit.net("ledu_a")
        ledd_a = circuit.net("ledd_a")

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

        circuit.part(
            "U1",
            Ch32v003f4p6(
                vdd=v3v3,
                vss=gnd,
                pa1=opa_n,
                pa2=opa_p,
                pd7=opa_p_b,
                pd2=txa_drv,
                pc3=txb_drv,
                pc4=ka,
                pc2=sel,
                pc7=led_work,
                pc5=led_up,
                pc6=led_down,
                pd1=swio,
                pd4=opo,
            ),
        )

        # Decoupling: 100n at the VDD pin, 10u bulk for the node.
        circuit.part("C1", C0603("100n", a=v3v3, b=gnd))
        circuit.part("C2", C0603("10u", a=v3v3, b=gnd))

        # §4.1 status LEDs: passive power LED, three MCU-driven.
        circuit.part("Rp", R0603("1k", a=v3v3, b=pwr_led))
        circuit.part("Dp", Led0603(anode=pwr_led, cathode=gnd, value="RED"))
        circuit.part("Rw", R0603("1k", a=led_work, b=ledw_a))
        circuit.part("Dw", Led0603(anode=ledw_a, cathode=gnd, value="GREEN"))
        circuit.part("Ru", R0603("1k", a=led_up, b=ledu_a))
        circuit.part("Du", Led0603(anode=ledu_a, cathode=gnd, value="YELLOW"))
        circuit.part("Rd", R0603("1k", a=led_down, b=ledd_a))
        circuit.part("Dd", Led0603(anode=ledd_a, cathode=gnd, value="YELLOW"))

        # Programming/debug: SWIO on a test pad (debug transport is §6-open).
        circuit.part("TP1", TestPoint("SWIO", p=swio))


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
