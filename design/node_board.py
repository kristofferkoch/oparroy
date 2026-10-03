"""The node board constraint skeleton: stackup, net classes, DRC minimums.

One :class:`PcbSpec` is the seed pcbnew opens: :func:`spec` pins the
settled 2-layer 0.8 mm stackup (docs/node-board-2026-09-29.md, item 1
— 35 µm copper around a ~0.71 mm FR4 core, ENIG; JLCPCB's exact
thickness offerings verify at quote time), two net classes, and the
fab-floor minimums. ``main()`` writes the pair KiCad consumes:

    boards/node/oparroy-node.kicad_pcb   (stackup + net list)
    boards/node/oparroy-node.kicad_pro   (net classes, board minimums)

**Net classes.** ``Default`` is the implicit catch-all — KiCad puts
every unassigned net in it, so it declares no nets here. ``Bypass``
carries the §4 bypass-path copper: the four nets from J1's ring-A pin
to J2's through the relaxed switch — ``RX_A`` (J1.5 through TVS Dar to
series R Rar), ``opa_p`` (Rar to SW1.B1, the listen-only RX tap the
MCU sits on), ``PHY1/txa_sw`` (SW1.COM to series R Rat, flattened
name in the board netlist), ``TX_A`` (Rat to
J2.5 through TVS Dat). The class is wider than Default not for current
(the 470 Ω series resistors cap it at mA) but for robustness: this is
the one copper path the ring depends on when the node is dead. Ring B
has no bypass switch (§3) and stays Default. The clearance sits at
0.3 mm — comfortable on a board this sparse, and above a KiCad 10.0.6
reporting quirk found 2026-10-03: DRC enforces any class clearance,
but the violation text only cites the class name when the clearance
exceeds 0.25 mm; below that the same violation reports with an empty
constraint name.

**Board minimums.** Conservative JLCPCB 2-layer numbers, pending the
fab quote (the parts-DB stock checks ride the same quote): JLCPCB
guarantees 0.09 mm trace/space and 0.45/0.2 mm vias on 1 oz; the
minimums here round to 0.1 mm with 0.2 mm holes and 0.3 mm copper-to-
edge (router-bit clearance), deliberately tighter than nothing we
intend to draw so a DRC flag means "fix the layout", never "fight the
fab". Tune here when the quote lands — nowhere else.

Usage (in the nix dev shell):

    python -m design.node_board    # write boards/node/ artifacts
"""

from __future__ import annotations

import sys
from pathlib import Path

from oparroy.dsl import (
    BoardMinimums,
    NetClassSpec,
    PcbSpec,
    StackupLayer,
    emit_pcb,
    emit_project,
)

_OUT_DIR = Path(__file__).parent.parent / "boards" / "node"


def spec() -> PcbSpec:
    """Build the node board's constraint skeleton."""
    return PcbSpec(
        name="oparroy-node",
        thickness_mm=0.8,
        stackup=(
            StackupLayer("F.SilkS", "Top Silk Screen"),
            StackupLayer("F.Paste", "Top Solder Paste"),
            StackupLayer("F.Mask", "Top Solder Mask", thickness_mm=0.01),
            StackupLayer("F.Cu", "copper", thickness_mm=0.035),
            StackupLayer(
                "dielectric 1",
                "core",
                thickness_mm=0.71,
                material="FR4",
                epsilon_r=4.5,
                loss_tangent=0.02,
            ),
            StackupLayer("B.Cu", "copper", thickness_mm=0.035),
            StackupLayer("B.Mask", "Bottom Solder Mask", thickness_mm=0.01),
            StackupLayer("B.Paste", "Bottom Solder Paste"),
            StackupLayer("B.SilkS", "Bottom Silk Screen"),
        ),
        copper_finish="ENIG",
        net_classes=(
            NetClassSpec(
                name="Default",
                clearance_mm=0.15,
                trace_width_mm=0.2,
                via_dia_mm=0.6,
                via_drill_mm=0.3,
                nets=(),
                description="implicit catch-all — every unassigned net",
            ),
            NetClassSpec(
                name="Bypass",
                clearance_mm=0.3,
                trace_width_mm=0.4,
                via_dia_mm=0.8,
                via_drill_mm=0.4,
                nets=("RX_A", "TX_A", "opa_p", "PHY1/txa_sw"),
                description="§4 bypass-path copper — no firmware in this path",
            ),
        ),
        minimums=BoardMinimums(
            min_clearance=0.1,
            min_track_width=0.1,
            min_via_diameter=0.45,
            min_through_hole_diameter=0.2,
            min_copper_edge_clearance=0.3,
            solder_mask_clearance=0.05,
            solder_mask_min_width=0.1,
        ),
    )


def main() -> None:
    """Write the ``boards/node/`` skeleton pair (byte-identical per spec)."""
    board_spec = spec()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in [
        ("oparroy-node.kicad_pcb", emit_pcb(board_spec)),
        ("oparroy-node.kicad_pro", emit_project(board_spec)),
    ]:
        path = _OUT_DIR / name
        path.write_text(content, encoding="utf-8")
        sys.stdout.write(f"wrote {path}\n")


if __name__ == "__main__":
    main()
