"""CI board power tree: USB-C inlet, CC sink pull-downs, 3.3 V rail.

``CiPower`` is the DSL capture of the CI board's power entry
(DESIGN.md §6 "Board power and host link"; §2.1 ring rail): one USB-C
receptacle is both the power inlet and the supervisor's host link. No
PD negotiation — two 5.1 kΩ Rd pull-downs on CC1/CC2 mark a sink, 5 V
only. An AMS1117-3.3-class SOT-223 LDO turns VBUS into the board's
always-on ``3V3`` rail. The §2.1 UNREG payload rail is omitted on this
board: no 5 V net exists past the regulator input. D+/D- pass straight
through as ports for the supervisor capture to pick up. The per-tile
3V3/3V3N split is the board capture's transform, not this module's.

Ports (the subcircuit interface):

- ``5V`` — sink, 4.5..5.5 V. The floor tracks the LDO's worst-case
  input requirement: 3.4 V max output + dropout (1.1 V typ / 1.3 V
  max, the max specified at 0.8 A, lower at the CI load) puts the true
  worst-case floor nearer 4.6 V — a compliant USB-C VBUS (4.75..5.25 V
  at the device) clears either number; the ceiling is USB 5 V +10 %,
  and the LDO itself tolerates 15 V.
- ``3V3`` — source, 3.2..3.4 V: the AMS1117-3.3's full-range output
  band (3.201..3.399 V, ±3 %). Static band only — the DSL models no
  transients, so load-step undershoot on top of this band is the
  decoupling's and the bench-verify list's concern, not this
  interval's.
- ``GND``.
- ``USB_DP``/``USB_DM`` — pass-through (both faces declared), 0..3.6 V:
  full-speed USB data levels toward the supervisor's USB pins.

Power budget (the prose arithmetic the machine-checked rail-current
check will replace): 8 tiles at tens of mA each (CH32V003 ~4 mA run,
status LEDs, PHY bias), the RP2040 at ~25..100 mA, the scan plane
(10x74HC595 + 2x74HC165, µA static), fault-switch leakage — worst case
≈ 500 mA on 3V3, plus the LDO's own 5..11 mA quiescent. Against USB-C
baseline sink delivery that is trivially inside the 500 mA USB-2.0
host floor, and a source advertising 1.5/3 A via Rp leaves it further
behind still. Dissipation is the binding constraint, not current:
(5.25 - 3.3) V x 0.5 A ≈ 0.86 W worst case; SOT-223 θJA is 90 °C/W
nominal (55 °C/W with ~2500 mm² of copper pour, datasheet Table 1), so
the layout owes the tab a pour — 125 °C junction is the ceiling
(datasheets/AMS1117/notes/facts.md). The output capacitor is ceramic
against the datasheet's tantalum stability spec — the mismatch and its
bench-verify obligation are recorded in
datasheets/AMS1117/notes/quirks.md.

No ``--spice`` view: the spice emitter binds only Device:R/C/LED plus
BAT54S, and this module's behavior is DC bookkeeping, not dynamics —
``design/phy_frontend.py`` is the precedent for shipping without one.

Usage (in the nix dev shell):

    python -m design.ci_power            # check + netlist
    python -m design.ci_power --dot      # Graphviz view
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING, ClassVar

from design.parts_db import C0603, PARTS, R0603
from oparroy.dsl import (
    Circuit,
    Interval,
    KiCadLibraries,
    Limits,
    PowerDomainKind,
    Subcircuit,
    SymbolTable,
    TypedPart,
    check,
    emit_netlist,
    raise_on_errors,
    to_dot,
)

if TYPE_CHECKING:
    from oparroy.dsl import Net


class _UsbCReceptacle16p(TypedPart):
    """USB 2.0-only 16P Type-C receptacle (``Connector:USB_C_Receptacle_USB2.0_16P``).

    Pin groups follow the standard receptacle assignment: ``gnd`` owns
    A1/A12/B1/B12, ``vbus`` A4/A9/B4/B9, ``dp``/``dm`` the doubled D+/D-
    pairs, ``cc1``/``cc2`` the configuration channels, ``shield`` the
    shell anchors. SBU1/SBU2 (A8/B8) stay out of the pin map — unused
    on a USB 2.0 sink — and report as unconnected-pin warnings.
    """

    symbol = "Connector:USB_C_Receptacle_USB2.0_16P"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "gnd": ("A1", "A12", "B1", "B12"),
        "vbus": ("A4", "A9", "B4", "B9"),
        "cc1": "A5",
        "cc2": "B5",
        "dp": ("A6", "B6"),
        "dm": ("A7", "B7"),
        "shield": "SH",
    }

    def __init__(  # noqa: PLR0913 — one keyword per pin group
        self,
        *,
        gnd: Net | str,
        vbus: Net | str,
        cc1: Net | str,
        cc2: Net | str,
        dp: Net | str,
        dm: Net | str,
        shield: Net | str,
        value: str | None = None,
        footprint: str | None = None,
    ) -> None:
        super().__init__(
            value,
            footprint,
            {
                "gnd": gnd,
                "vbus": vbus,
                "cc1": cc1,
                "cc2": cc2,
                "dp": dp,
                "dm": dm,
                "shield": shield,
            },
        )


class _Ams1117v33(TypedPart):
    """AMS1117-3.3 fixed LDO (``Regulator_Linear:AMS1117-3.3``, SOT-223).

    Pin 1 is GND, pin 2 the 3.3 V output (the tab is VOUT), pin 3 the
    input. Keyword-only: orientation is the whole point of a regulator.
    """

    symbol = "Regulator_Linear:AMS1117-3.3"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "gnd": "1",
        "vout": "2",
        "vin": "3",
    }

    def __init__(
        self,
        *,
        gnd: Net | str,
        vout: Net | str,
        vin: Net | str,
        value: str | None = None,
        footprint: str | None = None,
    ) -> None:
        super().__init__(value, footprint, {"gnd": gnd, "vout": vout, "vin": vin})


#: The picked parts, bound from the DB records (§6 inventory-driven).
UsbCReceptacle = PARTS.bind(
    "usb-c-receptacle-16p", _UsbCReceptacle16p, class_name="UsbCReceptacle"
)
Ams1117v33 = PARTS.bind("ldo-ams1117-3v3", _Ams1117v33, class_name="Ams1117v33")


class CiPower(Subcircuit):
    """The CI board's USB-C inlet and 3.3 V rail, as a reusable subcircuit."""

    def capture(self, circuit: Circuit) -> None:
        """Build the power tree; the port list is the module docstring's."""
        v5 = circuit.port("5V", sink=Limits(voltage=Interval(4.5, 5.5)))
        v3v3 = circuit.port("3V3", source=Limits(voltage=Interval(3.2, 3.4)))
        gnd = circuit.port("GND")
        circuit.power_domain(v5, kind=PowerDomainKind.ALWAYS)
        circuit.power_domain(v3v3, kind=PowerDomainKind.ALWAYS)
        circuit.power_domain(gnd, kind=PowerDomainKind.GROUND)
        usb_dp = circuit.port(
            "USB_DP",
            source=Limits(voltage=Interval(0, 3.6)),
            sink=Limits(voltage=Interval(0, 3.6)),
        )
        usb_dm = circuit.port(
            "USB_DM",
            source=Limits(voltage=Interval(0, 3.6)),
            sink=Limits(voltage=Interval(0, 3.6)),
        )
        cc1 = circuit.net("cc1")
        cc2 = circuit.net("cc2")

        circuit.part(
            "J1",
            UsbCReceptacle(
                gnd=gnd,
                vbus=v5,
                cc1=cc1,
                cc2=cc2,
                dp=usb_dp,
                dm=usb_dm,
                shield=gnd,
            ),
        )
        # CC sink pull-downs (Rd, USB-C §4.5.1 sink termination): 5.1 kΩ
        # each, no PD negotiation — 5 V only.
        circuit.part("Rcc1", R0603("5k1", a=cc1, b=gnd))
        circuit.part("Rcc2", R0603("5k1", a=cc2, b=gnd))
        circuit.part("U1", Ams1117v33(gnd=gnd, vout=v3v3, vin=v5))
        # Per the datasheet's application circuit: 10 µF in, 22 µF out —
        # ceramics against the tantalum stability spec (quirks.md).
        circuit.part("Cin", C0603("10u", a=v5, b=gnd))
        circuit.part("Cout", C0603("22u", a=v3v3, b=gnd))


def capture(symbols: SymbolTable) -> Circuit:
    """Build the standalone CI power-tree IR."""
    circuit = Circuit("ci-power", symbols)
    CiPower().capture(circuit)
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
