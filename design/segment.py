"""The §3 segment connector: the pinout as a bundle, the connector as a block.

DESIGN.md §3 settles two 6-pin connectors per node — upstream-facing
(UNREG, 3V3, GND, RX_A, GND, TX_B) and downstream-facing (UNREG, 3V3,
GND, TX_A, GND, RX_B). Both faces share one pinout by *wire identity*:
pin 4 is the ring-A data wire, pin 6 the ring-B one, whichever face you
look at — so the bundle members are ``unreg``/``v3v3``/``gnd``/``a``/
``b`` and two faces join member-to-member, while
``SegmentConnector.pin_map`` maps members to pin numbers declaratively
(``gnd`` owns the two paired ground pins 3 and 5). Connector part and
footprint are provisional — §3 leaves the connector style open (§6).
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
    """One §3 6-pin segment connector; the same pinout on both faces."""

    symbol = "Connector_Generic:Conn_01x06"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "unreg": "1",
        "v3v3": "2",
        "gnd": ("3", "5"),
        "a": "4",
        "b": "6",
    }
    default_value = "Conn_01x06"
    default_footprint = "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical"
