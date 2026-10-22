"""The CI board composition (DESIGN.md §6, docs/instrumented-ci.md).

Eight CI tiles (`design/ci_tiles.py` — input tiles 1/3/5/7, output
tiles 0/2/4 with tile 0 the boundary tile, tile 6 the §12 measurement
tile) chained on board-copper segments, plus the power tree
(`design/ci_power.py`), the RP2040 supervisor (`design/supervisor.py`)
closing the ring, and — on the instrumented side — the §7 transform
plan (`design/ci_instrumentation.py`) wired to the scan plane and the
SWIO/debug mux trees (`design/scan_plane.py`).

**The proof pair.** :func:`capture` builds either side of the
reset-state equivalence proof
(`src/oparroy/dsl/equivalence.py`): ``instrumented=False`` is the
plain reference board — same composition, no transforms, no control
plane, and the supervisor's instrumentation-facing ports (the four
boundary taps, the four pot-override PWMs, the measurement tile's
three SPI lines) bound to stub nets. The proof accepts exactly those
re-bindings: tap pins ride declared tap nets, PWM pins ride the
escaped substitute sources (absent in reset state).
``instrumented=True`` applies the plan between the tiles and
the supervisor so the tap/PWM handles exist when the supervisor's
ports bind, then wires PLANE/SWIO/DBG to the handles.

**The boundary segment.** The supervisor→tile-0 segment is the
board's one connectorized segment (instrumented-ci.md §2): J0 at the
supervisor end, T0's J1 at the tile end — the demo's yankable pair
and the cable-reach bench's insertion point. The §3 pinout is fixed,
so J0 binds the full bundle: GND and 3V3 cross the cable (both ends
land on the same board rails — a redundant parallel run; GND must
cross to preserve the G-S-G return geometry the §2 reach model
assumes; a yank interrupts ring signals, never power), and UNREG is a
dead conductor (J0.1 ↔ T0/J1.1 — this board has no 5 V rail past the
regulator input, design/ci_power.py). The eight inter-tile segments
are board copper: no connectors, no TVS (instrumented-ci.md §9 R10).

Usage (in the nix dev shell):

    python -m design.ci_board                          # check + KiCad netlist
    python -m design.ci_board --dot                    # Graphviz view
    python -m design.ci_board --annotation FILE        # stable refdes file
    python -m design.ci_board --footprints FILE        # footprint overrides
    python -m design.ci_board --back-annotate X.kicad_pcb --annotation FILE
    python -m design.ci_board --placement-map FILE     # refdes → capture-path
                                                       # JSON (netlist on stdout)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from design.ci_instrumentation import ci_transform_plan
from design.ci_power import CiPower
from design.ci_tiles import (
    MEASUREMENT_TILE,
    InputNode,
    MeasurementNode,
    OutputNode,
    ring_back_feed,
)
from design.scan_plane import DebugTree, ScanPlane, SwioTree, tile_bits
from design.segment import SegmentConnector
from design.supervisor import Supervisor
from oparroy.dsl import (
    Annotation,
    BackFeed,
    Circuit,
    KiCadLibraries,
    PerInstance,
    PowerDomainKind,
    SymbolTable,
    TileNet,
    ValueRange,
    annotate,
    annotation_from_pcb,
    apply_annotation,
    apply_transforms,
    assign_footprints,
    check,
    emit_netlist,
    overrides_from_json,
    raise_on_errors,
    solve,
    to_dot,
)
from oparroy.dsl.ir import natural_key

if TYPE_CHECKING:
    from oparroy.dsl import Net, Scope
    from oparroy.dsl.transform import Handles

#: The ring's tile count (DESIGN.md §6); segments SEG0..SEG8 close it.
TILE_COUNT = 8

#: The supervisor originator port's injector anchor: its ring ports
#: mirror the tile names minus the PHY1 prefix (design/supervisor.py).
SUPERVISOR_RING_NETS = ("TX_A", "Rat.b", "RX_B", "Rbr.a")

#: The supervisor's tap ports and the tile-0 nets they observe (§5).
SUPERVISOR_TAP_NETS = {
    "tap_rx": "opa_p",
    "tap_tx": "TX_A#b",
    "tap_comp": "opo",
    "tap_led": "led_work",
}

#: The supervisor's burst-capture SPI ports and the measurement tile's
#: transform-local nets they drive/sample (instrumented-ci.md §12 —
#: the P1-P3 taps escape them).
SUPERVISOR_ADC_NETS = {
    "adc_sclk": "F8_sclk",
    "adc_cs": "F8_cs",
    "adc_sdata": "F8_sdata",
}

#: The input tiles, carrying the pot/button payload (§6).
INPUT_TILES = (1, 3, 5, 7)


def ci_board_plan() -> list[Scope]:
    """Return the board's transform plan: the §7 list over this composition."""
    return ci_transform_plan(
        boundary="T0",
        supervisor_port=("SUP",),
        supervisor_nets=SUPERVISOR_RING_NETS,
    )


def declare_segment_crossings(board: Circuit, segments: int) -> None:
    """Declare the segment wires' crossing dispositions (instrumented-ci §3).

    A gated tile's MCU clamps are driven from the live ring through the
    470 Ω terminal-protection resistors — bounded back-feed, 5.7 mA per
    dead-side pin on the reach (opa_p + opo on ring A, txb_drv on ring
    B). ``segments`` counts the inter-tile segments; the drain segment
    (T7→supervisor on the full board) is always↔always and never
    crosses, so it is excluded. The plain side carries these as dormant
    declarations — the crossings are an instrumented-side phenomenon
    (F8's 3V3N) — so its check reports them stale, like the tile
    captures'.
    """
    for index in range(segments):
        board.crossing(
            f"SEG{index}_A",
            ring_back_feed("ring traffic and the injector shunts", 2, "Rar"),
        )
        board.crossing(f"SEG{index}_B", ring_back_feed("ring-B traffic", 1, "Rbt"))


def capture(symbols: SymbolTable, *, instrumented: bool = True) -> Circuit:
    """Build the CI board; ``instrumented`` selects the proof side."""
    board = Circuit("oparroy-ci", symbols)
    rails = {
        "unreg": board.net("UNREG"),
        "v3v3": board.net("3V3"),
        "gnd": board.net("GND"),
    }
    # The board rails' domains (instrumented-ci.md §3): 3V3/5V/UNREG are
    # always-on, GND the return; F8 derives each tile's switched 3V3N
    # from 3V3 (design/ci_instrumentation.py). 3V3 also carries the
    # LDO's regulation window — the actual supply value generators in
    # the tiles size against.
    board.power_domain(rails["unreg"], kind=PowerDomainKind.ALWAYS)
    board.power_domain(
        rails["v3v3"],
        kind=PowerDomainKind.ALWAYS,
        voltage=ValueRange.around(3.3, 0.03),
    )
    board.power_domain(rails["gnd"], kind=PowerDomainKind.GROUND)
    v5 = board.net("5V")
    board.power_domain(v5, kind=PowerDomainKind.ALWAYS)
    board.instance(
        "PWR",
        CiPower(),
        **{
            "5V": v5,
            "3V3": rails["v3v3"],
            "GND": rails["gnd"],
            "USB_DP": board.net("USB_DP"),
            "USB_DM": board.net("USB_DM"),
        },
    )
    segments = [
        board.bundle(
            f"seg{index}",
            **rails,
            a=board.net(f"SEG{index}_A"),
            b=board.net(f"SEG{index}_B"),
        )
        for index in range(TILE_COUNT + 1)
    ]
    declare_segment_crossings(board, TILE_COUNT)
    # The boundary tile's extras (instrumented-ci.md §5), declared here
    # because they exist only once the B4/B5 transforms land on T0:
    # B5's defeat leg drives the gated tile's `sel` (the tile-level
    # AlwaysPowered covers the placement rule; this bounds the driven
    # corner), and B4's observe-only tap sits on `led_work` with no
    # series R — a misdriven RP2040 pad (≤ 12 mA max drive) stays
    # inside the MCU's ±20 mA injection budget.
    board.crossing(
        "T0/sel",
        BackFeed(
            5.7,
            "instrumented-ci.md §3/§5 — B5's defeat leg drives the gated "
            "tile's sel (the U1 clamp path) through RWD (470 Ω): ≤ 5.7 mA, "
            "inside the ±20 mA injection budget (CH32V003 facts T3-1)",
        ),
    )
    led_tap = BackFeed(
        12,
        "instrumented-ci.md §5 — B4's observe-only tap: a misdriven "
        "RP2040 pad (≤ 12 mA max drive) into the gated tile's led_work "
        "stays inside the CH32V003 ±20 mA injection budget (§3, facts T3-1)",
    )
    board.crossing("T0/led_work", led_tap)
    board.crossing("T0/SL1/ledw_a", led_tap)
    # The boundary segment's supervisor-end connector (instrumented-ci
    # §2's connectorized segment; the tile end is T0's J1).
    board.part(
        "J0",
        SegmentConnector(segments[0]),
        note="boundary segment connector, supervisor end",
    )
    for index in range(TILE_COUNT):
        if index == MEASUREMENT_TILE:
            variant = MeasurementNode
        elif index in INPUT_TILES:
            variant = InputNode
        else:
            variant = OutputNode
        # R10: copper-internal segments drop the connectors and their
        # TVS pairs; the boundary tile keeps the cable-facing face.
        faces = ("upstream",) if index == 0 else ()
        board.instance(
            f"T{index}",
            variant(connector_faces=faces),
            upstream=segments[index],
            downstream=segments[index + 1],
        )

    plan = ci_board_plan()
    tile_scopes = [
        scope
        for scope in plan
        if not (isinstance(scope, PerInstance) and scope.path == ("SUP",))
    ]
    supervisor_scopes = [
        scope
        for scope in plan
        if isinstance(scope, PerInstance) and scope.path == ("SUP",)
    ]
    if instrumented:
        # The tile scopes first: the supervisor's tap/PWM ports bind to
        # the handles the tile transforms escape; the originator-port
        # injector applies once the supervisor instance exists.
        handles = apply_transforms(board, tile_scopes)
        board.instance("SUP", Supervisor(), **_supervisor_bindings(board, handles))
        handles |= apply_transforms(board, supervisor_scopes)
        _wire_control_plane(board, handles)
    else:
        board.instance("SUP", Supervisor(), **_supervisor_bindings(board, None))
    return board


def _supervisor_bindings(board: Circuit, handles: Handles | None) -> dict[str, Net]:
    """Return the supervisor's port map; the plain board stubs the instrument ports."""
    bindings: dict[str, Net] = {
        "3V3": board.nets["3V3"],
        "GND": board.nets["GND"],
        "usb_dp": board.nets["USB_DP"],
        "usb_dm": board.nets["USB_DM"],
        "usb_boot": board.net("usb_boot"),  # NC = normal flash boot
        "swio": board.net("swio"),
        "dbg_rx": board.net("dbg_rx"),
        "srclk": board.net("srclk"),
        "sdo": board.net("sdo"),
        "sdi": board.net("sdi"),
        "commit": board.net("commit"),
        "oe_n": board.net("oe_n"),
        # The originator port toward tile 0, the drain from tile 7.
        "TX_A": board.nets["SEG0_A"],
        "RX_B": board.nets["SEG0_B"],
        "RX_A": board.nets[f"SEG{TILE_COUNT}_A"],
        "TX_B": board.nets[f"SEG{TILE_COUNT}_B"],
    }
    for port, net in SUPERVISOR_TAP_NETS.items():
        bindings[port] = (
            board.net(port) if handles is None else handles[TileNet(("T0",), net)]
        )
    for port, net in SUPERVISOR_ADC_NETS.items():
        bindings[port] = (
            board.net(port)
            if handles is None
            else handles[TileNet((f"T{MEASUREMENT_TILE}",), net)]
        )
    for tile in INPUT_TILES:
        port = f"pot_pwm{tile}"
        bindings[port] = (
            board.net(port)
            if handles is None
            else handles[TileNet((f"T{tile}",), "POT_PWM")]
        )
    return bindings


def _wire_control_plane(board: Circuit, handles: Handles) -> None:
    """Instance the scan plane and the SWIO/debug trees, wired to the handles."""
    v3v3 = board.nets["3V3"]
    gnd = board.nets["GND"]
    selects = {f"swio_a{index}": board.net(f"swio_a{index}") for index in range(3)}
    board.instance(
        "SWIO",
        SwioTree(),
        root=board.nets["swio"],
        **selects,
        **{
            f"leaf{index}": handles[TileNet((f"T{index}",), "swio")]
            for index in range(TILE_COUNT)
        },
        **{
            f"rail{index}": handles[TileNet((f"T{index}",), "3V3N")]
            for index in range(TILE_COUNT)
        },
        **{"3V3": v3v3, "GND": gnd},
    )
    board.instance(
        "DBG",
        DebugTree(),
        root=board.nets["dbg_rx"],
        **selects,
        **{
            f"leaf{index}": handles[TileNet((f"T{index}",), "debug_tx")]
            for index in range(TILE_COUNT)
        },
        **{"3V3": v3v3, "GND": gnd},
    )
    board.instance("PLANE", ScanPlane(), **_plane_bindings(board, handles, selects))


def _plane_bindings(
    board: Circuit, handles: Handles, selects: dict[str, Net]
) -> dict[str, Net]:
    """Return the scan plane's port map: the §3 bit map against the handles."""
    bindings: dict[str, Net] = {
        "srclk": board.nets["srclk"],
        "sdo": board.nets["sdo"],
        "sdi": board.nets["sdi"],
        "commit": board.nets["commit"],
        "oe_n": board.nets["oe_n"],
        "3V3": board.nets["3V3"],
        "GND": board.nets["GND"],
        "wd_defeat": handles[TileNet(("T0",), "WD_DEFEAT")],
        **selects,
    }
    for bit in ("brk_a", "shg_a", "shv_a", "brk_b", "shg_b", "shv_b"):
        bindings[f"sup_{bit}"] = handles[TileNet(("SUP",), bit.upper())]
    for tile in INPUT_TILES:
        for bit in ("pot_sel", "btn_a", "btn_b"):
            bindings[f"{bit}{tile}"] = handles[TileNet((f"T{tile}",), bit.upper())]
    for index in range(TILE_COUNT):
        path = (f"T{index}",)
        for bit in tile_bits(index):
            bindings[f"t{index}_{bit}"] = handles[TileNet(path, bit.upper())]
        bindings[f"t{index}_sel"] = handles[TileNet(path, "sel")]
        bindings[f"t{index}_3v3n"] = handles[TileNet(path, "3V3N")]
    return bindings


def placement_map_json(circuit: Circuit) -> str:
    """Render the refdes → capture-path JSON pcbnew layout scripting reads.

    pcbnew sees only the annotated refdes; the map hands each footprint
    back its capture path (``T2/PHY1/U1``), whose first component names
    the group the part belongs to — the tile, SUP, PLANE, or the board
    itself (no ``/``). Power symbols never reach pcbnew, so they stay
    out. Key order is natural (U2 before U10) to keep the file
    diff-stable like the netlist.
    """
    mapping = {
        part.ref: part.identity
        for part in circuit.parts.values()
        if not part.symbol.is_power
    }
    ordered = dict(sorted(mapping.items(), key=lambda item: natural_key(item[0])))
    return json.dumps(ordered, indent=1) + "\n"


def main() -> None:
    """Check the instrumented capture and emit the annotated KiCad netlist.

    The §7 pipeline stages mirror the node board's
    (``design/node.py``): footprint assignment, then annotation
    (``--annotation`` keeps refdes stable; ``--back-annotate`` folds
    pcbnew's renumbering back in). The plain reference side exists for
    the equivalence proof only — it is never emitted.
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
    parser.add_argument(
        "--placement-map",
        type=Path,
        help="write the refdes → capture-path JSON pcbnew layout scripting reads",
    )
    args = parser.parse_args()
    if args.back_annotate is not None and args.annotation is None:
        parser.error("--back-annotate needs --annotation")
    libs = KiCadLibraries.from_env()
    circuit = capture(libs)
    if args.dot:
        sys.stdout.write(to_dot(circuit))
        return
    if args.footprints is not None:
        overrides = overrides_from_json(args.footprints.read_text(encoding="utf-8"))
        circuit = assign_footprints(circuit, overrides)
    report = solve(circuit)
    if resolutions := str(report):
        sys.stderr.write(f"{resolutions}\n")
    raise_on_errors(report.issues)
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
    renamed = apply_annotation(circuit, annotation)
    if args.placement_map is not None:
        args.placement_map.write_text(placement_map_json(renamed), encoding="utf-8")
    sys.stdout.write(emit_netlist(renamed))


if __name__ == "__main__":
    main()
