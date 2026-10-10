"""PHY front-end: the discrete half of the §2 physical layer (DSL form).

One ring node's analog front-end, captured as a subcircuit
(DESIGN.md §7 organization — the comparator and timers live inside the
MCU, so this block is everything between the segment connectors and the
MCU pins):

- **Ring-A bypass switch** (§3, §4): an SN74LVC1G3157 SPDT — COM toward
  the downstream connector, B1 toward upstream, B2 to the node TX
  driver. ``sel`` low relaxes the switch into the bypass state; the
  node's RX tap sits on the B1 side, so a bypassed (dead) node keeps
  listening. Facts: ``datasheets/SN74LVC1G3157/notes/facts.md``.
- **RX threshold** (§2): the VDD/2 divider — two 10k from the stocked
  bin — on the OPA negative input.
- **Ring B** (§3): no switch — the dual ring demotes the bypass to
  second layer; ring B is plain protected RX/TX.
- **Terminal protection** (§7 checklist): 470 Ω series R plus a TVS
  footprint per ring terminal, wired connector → TVS → R → µC so the R
  limits what the MCU clamp diodes absorb after the TVS clamps.
- **Hysteresis fallback** (§2): the OPO→OPP feedback resistor the
  phy-segment noise bench rejected stays on the BOM as DNP — the
  footprint is there if real silicon disagrees with the simulation.
- **`sel` Schmitt insurance** (§4's accepted 10 ns/V violation, settled
  2026-09-29): a DNP 74LVC1G17 footprint in the sel path between the
  watchdog and the switch, bridged by a fitted 0 Ω — if the bench
  disagrees the fix is a resistor swap, not a respin.

Ports: the connector-facing ``rx_a``/``tx_a``/``rx_b``/``tx_b`` (bound
to the §3 segment ports by the parent), the MCU-facing
``mcu_rx_a``/``mcu_vdd2``/``mcu_rx_b``/``mcu_tx_a``/``mcu_tx_b``/
``mcu_opo``, and ``sel``/``v3v3``/``gnd``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from design.bins import R0603, TvsSod323
from oparroy.dsl import Circuit, Subcircuit, SymbolTable, TypedPart

if TYPE_CHECKING:
    from oparroy.dsl import Net


class Sn74lvc1g3157(TypedPart):
    """SN74LVC1G3157 SPDT analog switch (SOT-23-6, SCES424O §4).

    ``a`` is the common, ``b1`` the S-low throw (bypass default),
    ``b2`` the S-high throw (node inserted), ``s`` the select.
    """

    symbol = "74xGxx:74LVC1G3157"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "b2": "1",
        "gnd": "2",
        "b1": "3",
        "a": "4",
        "vcc": "5",
        "s": "6",
    }
    default_value = "SN74LVC1G3157"
    default_footprint = "Package_TO_SOT_SMD:SOT-23-6"

    def __init__(  # noqa: PLR0913 — one keyword per physical pin
        self,
        *,
        a: Net | str,
        b1: Net | str,
        b2: Net | str,
        s: Net | str,
        vcc: Net | str,
        gnd: Net | str,
        value: str | None = None,
        footprint: str | None = None,
    ) -> None:
        super().__init__(
            value,
            footprint,
            {"a": a, "b1": b1, "b2": b2, "s": s, "vcc": vcc, "gnd": gnd},
        )


class Sn74lvc1g17(TypedPart):
    """74LVC1G17 single Schmitt-trigger buffer (SOT-23-5).

    The §4 sel-path insurance, placed DNP: ``a`` is the input, ``y``
    the output. Pin 1 is a no-connect on the symbol and stays out of
    the pin map.
    """

    symbol = "74xGxx:74LVC1G17"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "a": "2",
        "gnd": "3",
        "y": "4",
        "vcc": "5",
    }
    default_value = "74LVC1G17"
    default_footprint = "Package_TO_SOT_SMD:SOT-23-5"

    def __init__(  # noqa: PLR0913 — one keyword per physical pin
        self,
        *,
        a: Net | str,
        y: Net | str,
        vcc: Net | str,
        gnd: Net | str,
        value: str | None = None,
        footprint: str | None = None,
    ) -> None:
        super().__init__(value, footprint, {"a": a, "y": y, "vcc": vcc, "gnd": gnd})


class PhyFrontEnd(Subcircuit):
    """The §2/§3/§4 PHY front-end, as a reusable subcircuit."""

    def capture(self, circuit: Circuit) -> None:
        """Build the front-end; the port list is the module docstring's."""
        rx_a = circuit.port("rx_a")
        tx_a = circuit.port("tx_a")
        rx_b = circuit.port("rx_b")
        tx_b = circuit.port("tx_b")
        mcu_rx_a = circuit.port("mcu_rx_a")
        mcu_vdd2 = circuit.port("mcu_vdd2")
        mcu_rx_b = circuit.port("mcu_rx_b")
        mcu_tx_a = circuit.port("mcu_tx_a")
        mcu_tx_b = circuit.port("mcu_tx_b")
        mcu_opo = circuit.port("mcu_opo")
        sel = circuit.port("sel")
        v3v3 = circuit.port("v3v3")
        gnd = circuit.port("gnd")
        txa_sw = circuit.net("txa_sw")
        sel_sw = circuit.net("sel_sw")

        # Ring A: connector -> TVS -> R -> B1; the MCU listens at B1.
        circuit.part("Dar", TvsSod323(a=rx_a, b=gnd))
        circuit.part("Rar", R0603("470", a=rx_a, b=mcu_rx_a))
        circuit.part(
            "SW1",
            Sn74lvc1g3157(
                a=txa_sw, b1=mcu_rx_a, b2=mcu_tx_a, s=sel_sw, vcc=v3v3, gnd=gnd
            ),
        )
        circuit.part("Rat", R0603("470", a=txa_sw, b=tx_a))
        circuit.part("Dat", TvsSod323(a=tx_a, b=gnd))

        # sel Schmitt insurance (§4, 2026-09-29): the watchdog drives the
        # switch through a fitted 0 Ω bridge, with a DNP 74LVC1G17 across
        # it — depopulate Rsel, populate BUF1 if the bench disagrees.
        circuit.part("Rsel", R0603("0R", a=sel, b=sel_sw))
        circuit.part(
            "BUF1", Sn74lvc1g17(a=sel, y=sel_sw, vcc=v3v3, gnd=gnd, value="DNP")
        )

        # Ring B: protected RX/TX, no switch (§3 second layer).
        circuit.part("Dbr", TvsSod323(a=rx_b, b=gnd))
        circuit.part("Rbr", R0603("470", a=rx_b, b=mcu_rx_b))
        circuit.part("Rbt", R0603("470", a=mcu_tx_b, b=tx_b))
        circuit.part("Dbt", TvsSod323(a=tx_b, b=gnd))

        # RX threshold: VDD/2 from the 10k bin (§2; the phy-segment
        # bench values).
        circuit.part("Rth1", R0603("10k", a=v3v3, b=mcu_vdd2))
        circuit.part("Rth2", R0603("10k", a=mcu_vdd2, b=gnd))

        # Hysteresis fallback (§2): OPO -> OPP feedback, unpopulated.
        circuit.part("Rfb", R0603("DNP", a=mcu_opo, b=mcu_rx_a))


def capture(symbols: SymbolTable) -> Circuit:
    """Build the standalone PHY front-end IR."""
    circuit = Circuit("phy-frontend", symbols)
    PhyFrontEnd().capture(circuit)
    return circuit
