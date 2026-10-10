"""The §3 segment connector: the pinout as a bundle, the connector as a block.

DESIGN.md §3 settles two 10-pin 2.54 mm 2x5 IDC box headers per node
(superseding the 6-pin pinout) on 10-way 1.27
mm-pitch ribbon (3M 3365/10-class). The dual-row IDC straddle puts odd
conductors in one connector row and even in the other, so the
conductor order — UNREG, GND, 3V3, GND, A, GND, B, GND, 3V3, GND —
lands row 2 as a solid ground row and every conductor ground-flanked
in the cable (the G-S-G condition the §2 reach model assumes). Both
faces share one pinout by *wire identity*: pin 5 is the ring-A data
wire, pin 7 the ring-B one, whichever face you look at — so the
bundle members are ``unreg``/``v3v3``/``gnd``/``a``/``b`` and two
faces join member-to-member, while ``SegmentConnector.pin_map`` maps
members to pin numbers declaratively (``gnd`` owns the five ground
pins of row 2, ``v3v3`` the doubled 3V3). The header is SMD on the
board's back side, hand-soldered post-PCBA — the front is the
single-sided JLCPCB assembly face and stays flat for enclosure-wall
mounting (§7 checklist). KiCad 10 names the generic
2-row symbols by numbering scheme: ``Odd_Even`` is the IDC zigzag —
pin 1 sits next to pin 2, not above it.
"""

from typing import ClassVar

from oparroy.dsl import Bundle, BundleConnector, Circuit

#: The bundle members of one segment face, in pin order.
SEGMENT_MEMBERS = ("unreg", "v3v3", "gnd", "a", "b")


def segment_ports(circuit: Circuit) -> tuple[Bundle, Bundle]:
    """Declare a node's §3 segment interface: the (upstream, downstream) bundles.

    Seven port nets — UNREG, 3V3, GND, and per-direction RX/TX —
    grouped by wire identity: ``upstream.a`` is the node's RX_A port,
    ``downstream.a`` its TX_A (and likewise for ring B). The power nets
    alias into both faces' bundles — the §3 power loop enters from both
    directions — so a parent chaining two nodes binds each face's
    unreg/v3v3/gnd to the same parent nets.
    """
    unreg = circuit.port("UNREG")
    v3v3 = circuit.port("3V3")
    gnd = circuit.port("GND")
    rx_a = circuit.port("RX_A")
    tx_a = circuit.port("TX_A")
    rx_b = circuit.port("RX_B")
    tx_b = circuit.port("TX_B")
    upstream = circuit.bundle(
        "upstream", unreg=unreg, v3v3=v3v3, gnd=gnd, a=rx_a, b=tx_b
    )
    downstream = circuit.bundle(
        "downstream", unreg=unreg, v3v3=v3v3, gnd=gnd, a=tx_a, b=rx_b
    )
    return upstream, downstream


class SegmentConnector(BundleConnector):
    """One §3 10-pin 2x5 IDC segment connector; the same pinout on both faces."""

    symbol = "Connector_Generic:Conn_02x05_Odd_Even"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "unreg": "1",
        "gnd": ("2", "4", "6", "8", "10"),
        "v3v3": ("3", "9"),
        "a": "5",
        "b": "7",
    }
    default_value = "Conn_02x05_Odd_Even"
    default_footprint = "Connector_IDC:IDC-Header_2x05_P2.54mm_Vertical_SMD"
