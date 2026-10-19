"""CI board supervisor: the RP2040 minimal system (DESIGN.md §5/§6).

``Supervisor`` is the DSL capture of the "Hardware design with RP2040"
minimal design example (AN §2), adapted to a 3.3 V-only board: no 5 V
net exists anywhere — the board's ``3V3`` rail (``design/ci_power.py``)
feeds IOVDD, USB_VDD, ADC_AVDD, and VREG_IN directly, and the on-chip
LDO makes the 1.1 V DVDD core rail. The external parts are the AN's:
the W25Q16JVSSIQ QSPI boot flash, the Abracon ABM8-272-T3 12 MHz
crystal with its load caps and XOUT series resistor, the 27 Ω USB
series pair, the QSPI_SS boot-strap/pull-up pair, and the decoupling
set (AN §2.1.2: 100 nF per power pin; AN §2.1.3: a mandatory 1 µF at
each VREG pin).

Ports (the subcircuit interface):

- ``3V3`` — sink, 3.0..3.6 V: contains the AMS1117-3.3's full-range
  output band (3.2..3.4 V) the power tree drives, so the
  range-containment check passes when the two compose. The RP2040
  itself tolerates 1.8..3.63 V on IOVDD, but the crystal circuit is
  tuned for 3.3 V (AN §2.3.1), so the port contracts the board rail,
  not the silicon's limits.
- ``GND``.
- ``usb_dp``/``usb_dm`` — both faces declared, 0..3.6 V: full-speed
  USB data levels, the host link from the board's USB-C receptacle
  (board-level, out of scope here) through the 27 Ω pair.
- ``usb_boot`` — the BOOTSEL strap: QSPI_SS through the mandatory 1 kΩ
  R1 (AN §2.2). NC on the board is normal flash boot; shorting to GND
  at reset enters BOOTSEL. The board decides the affordance (test
  pads, jumper) later.
- ``swio``, ``tap_rx``, ``tap_tx``, ``tap_comp``, ``tap_led`` — the §6
  PIO channels: the SWIO flash fan-out and the instrumented boundary
  node's four taps.
- ``srclk``, ``sdo``, ``sdi``, ``commit``, ``oe_n`` — the scan-plane
  control/observe chain (docs/scan-plane.md §6).
- ``dbg_rx`` — the §6 runtime debug transport: root of the second 8:1
  tree ganged to the flash tree's selects (docs/scan-plane.md §5),
  hearing the selected tile's PD5 debug UART stream.
- ``pot_pwm1``/``pot_pwm3``/``pot_pwm5``/``pot_pwm7`` — the §6
  pot-override channels: one filtered-PWM output per input tile,
  substituted for the pot wiper through the tile's POT_SEL mux
  (docs/instrumented-ci.md §6). The RC filter sits at the tile; the
  board composition wires these to the escaped ``POT_PWM`` sources.
- ``adc_sclk``/``adc_cs``/``adc_sdata`` — the §12 measurement tile's
  ADC SPI: the PIO burst-capture channel reading the tile-current
  chain (docs/instrumented-ci.md §12).
- ``TX_A``/``RX_B`` — the ring-closure **originator port** toward
  tile 0 (DESIGN.md §2/§3: the supervisor is the only frame
  originator, on both counter-rotating rings), and ``RX_A``/``TX_B``
  — the **drain port** from tile 7. §5's PIO is the PHY engine, so the
  port is digital drive/sample with the §7 terminal-protection
  contract mirrored from the node PHY (`design/phy_frontend.py`):
  a 470 Ω series resistor per wire (the §2 swept baseline assumes the
  470 Ω TX series R), connector-adjacent TVS only on the originator
  pair — the supervisor→tile-0 segment is the board's one
  connectorized segment; the drain faces board copper
  (docs/instrumented-ci.md §2). The refs mirror the node's
  ``Rat``/``Rar``/``Rbt``/``Rbr`` so the §7 injector plan's split
  points (``TX_A``: ``Rat.b`` ↔ downstream, ``RX_B``: ``Rbr.a`` ↔
  downstream) read the same at both segment ends; the connector pair
  itself lands with the board composition.

The GPIO binding is exactly ``design/supervisor_pins.py``'s pin map:
gpio0..2 → the measurement tile's ADC SPI (the SPI0-capable pads, the
hardware fallback to the PIO plan), gpio4..7 → the ring wires
(originator pair, then drain pair),
gpio8..11 → the taps, gpio12 → ``swio``, gpio13 → ``dbg_rx``,
gpio14..17 → the pot-override PWMs, gpio18..22 → the scan chain
(SRCLK/SDO/SDI on the SPI0-capable pads). gpio3 stays spare — the
tail of the reclaimed debug-transport reservation (DESIGN.md §6
settled the transport at one GPIO) — and gpio23..29 with it.

Expected unconnected-pin warnings: the eight spare GPIOs (GPIO3,
GPIO23..29) and SWCLK/SWDIO, all on U1. SWD stays unwired on the board
— the §6 flash channel is PIO SWIO through the 3157 tree; the pads
report by name so nothing else hides among them.

Usage (in the nix dev shell):

    python -m design.supervisor            # check + netlist
    python -m design.supervisor --dot      # Graphviz view
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING, ClassVar

from design.bins import TvsSod323
from design.parts_db import C0603, PARTS, R0603
from design.rp2040 import Rp2040 as _Rp2040
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


class _W25q16jvssiq(TypedPart):
    """W25Q16JVSSIQ QSPI boot flash (``Memory_Flash:W25Q16JVSS``, SOIC-8).

    Pins by function: the IQ variant's QE bit ships set, so ``wp``/
    ``hold`` are plain IO2/IO3 of the quad bus
    (datasheets/W25Q16JV/notes/facts.md). All pins required — a boot
    flash with an unwired pin is never intentional.
    """

    symbol = "Memory_Flash:W25Q16JVSS"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "cs": "1",
        "do": "2",
        "wp": "3",
        "gnd": "4",
        "di": "5",
        "clk": "6",
        "hold": "7",
        "vcc": "8",
    }
    required_pins: ClassVar[frozenset[str] | None] = frozenset(
        {"cs", "do", "wp", "gnd", "di", "clk", "hold", "vcc"}
    )

    def __init__(  # noqa: PLR0913 — one keyword per pin
        self,
        *,
        cs: Net | str,
        do: Net | str,
        wp: Net | str,
        gnd: Net | str,
        di: Net | str,
        clk: Net | str,
        hold: Net | str,
        vcc: Net | str,
        value: str | None = None,
        footprint: str | None = None,
    ) -> None:
        super().__init__(
            value,
            footprint,
            {
                "cs": cs,
                "do": do,
                "wp": wp,
                "gnd": gnd,
                "di": di,
                "clk": clk,
                "hold": hold,
                "vcc": vcc,
            },
        )


class _Abm8272t3(TypedPart):
    """ABM8-272-T3 12 MHz crystal (``Device:Crystal_GND24``, 3225-4).

    Pins 1/3 are the crystal, pins 2/4 the case ground. Keyword-only:
    which pad faces XIN matters to the layout's symmetry, not to the
    netlist.
    """

    symbol = "Device:Crystal_GND24"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "a": "1",
        "b": "3",
        "gnd": ("2", "4"),
    }
    required_pins: ClassVar[frozenset[str] | None] = frozenset({"a", "b", "gnd"})

    def __init__(
        self,
        *,
        a: Net | str,
        b: Net | str,
        gnd: Net | str,
        value: str | None = None,
        footprint: str | None = None,
    ) -> None:
        super().__init__(value, footprint, {"a": a, "b": b, "gnd": gnd})


#: The picked parts, bound from the DB records (§6 inventory-driven).
Rp2040 = PARTS.bind("rp2040", _Rp2040, class_name="Rp2040")
W25q16jvssiq = PARTS.bind(
    "flash-w25q16jvssiq", _W25q16jvssiq, class_name="W25q16jvssiq"
)
Abm8272t3 = PARTS.bind("crystal-abm8-272-t3", _Abm8272t3, class_name="Abm8272t3")


def _ring_ports(circuit: Circuit) -> tuple[Net, Net, Net, Net]:
    """Build the ring-closure ports with their §7 terminal protection.

    The originator port (``TX_A``/``RX_B``, toward tile 0) and the
    drain port (``RX_A``/``TX_B``, from tile 7) — DESIGN.md §2/§3's
    closure discipline: the supervisor is the only frame originator
    and drainer, on both counter-rotating rings. Placement mirrors the
    node PHY (design/phy_frontend.py): the 470 Ω series R sits between
    the GPIO and the wire, the TVS connector-adjacent on the wire —
    and only on the originator pair: the supervisor→tile-0 segment is
    the board's one connectorized segment, the drain is board copper
    (instrumented-ci.md §2). The refs mirror the node's
    Rat/Rar/Rbt/Rbr so the injector's split points — ``Rat.b`` on
    ``TX_A``, ``Rbr.a`` on ``RX_B`` — read the same at both segment
    ends. Returns the four MCU-side nets for the U1 binding.
    """
    tx_a = circuit.port("TX_A")
    rx_b = circuit.port("RX_B")
    rx_a = circuit.port("RX_A")
    tx_b = circuit.port("TX_B")
    gnd = circuit.nets["GND"]
    ring_txa = circuit.net("ring_txa")
    ring_rxb = circuit.net("ring_rxb")
    ring_rxa = circuit.net("ring_rxa")
    ring_txb = circuit.net("ring_txb")
    circuit.part("Rat", R0603("470", a=ring_txa, b=tx_a))
    circuit.part("Dat", TvsSod323(a=tx_a, b=gnd))
    circuit.part("Rbr", R0603("470", a=rx_b, b=ring_rxb))
    circuit.part("Dbr", TvsSod323(a=rx_b, b=gnd))
    circuit.part("Rar", R0603("470", a=rx_a, b=ring_rxa))
    circuit.part("Rbt", R0603("470", a=ring_txb, b=tx_b))
    return ring_txa, ring_rxb, ring_rxa, ring_txb


class Supervisor(Subcircuit):
    """The RP2040 minimal system on the 3.3 V board rail, as a subcircuit."""

    def capture(self, circuit: Circuit) -> None:
        """Build the supervisor; the port list is the module docstring's."""
        v3v3 = circuit.port("3V3", sink=Limits(voltage=Interval(3.0, 3.6)))
        gnd = circuit.port("GND")
        usb_dp = circuit.port(
            "usb_dp",
            source=Limits(voltage=Interval(0, 3.6)),
            sink=Limits(voltage=Interval(0, 3.6)),
        )
        usb_dm = circuit.port(
            "usb_dm",
            source=Limits(voltage=Interval(0, 3.6)),
            sink=Limits(voltage=Interval(0, 3.6)),
        )
        usb_boot = circuit.port("usb_boot")
        swio = circuit.port("swio")
        tap_rx = circuit.port("tap_rx")
        tap_tx = circuit.port("tap_tx")
        tap_comp = circuit.port("tap_comp")
        tap_led = circuit.port("tap_led")
        srclk = circuit.port("srclk")
        sdo = circuit.port("sdo")
        sdi = circuit.port("sdi")
        commit = circuit.port("commit")
        oe_n = circuit.port("oe_n")
        dbg_rx = circuit.port("dbg_rx")
        adc = {name: circuit.port(f"adc_{name}") for name in ("sclk", "cs", "sdata")}
        pot_pwm = {tile: circuit.port(f"pot_pwm{tile}") for tile in (1, 3, 5, 7)}
        ring_txa, ring_rxb, ring_rxa, ring_txb = _ring_ports(circuit)

        dvdd = circuit.net("dvdd")
        # The rail domains (instrumented-ci.md §3): 3V3 always, GND the
        # return; dvdd — the RP2040's internal core regulator output —
        # is always-on with IOVDD.
        for rail, kind in (
            (v3v3, PowerDomainKind.ALWAYS),
            (gnd, PowerDomainKind.GROUND),
            (dvdd, PowerDomainKind.ALWAYS),
        ):
            circuit.power_domain(rail, kind=kind)
        qspi_ss = circuit.net("qspi_ss")
        qspi_sclk = circuit.net("qspi_sclk")
        qspi_sd0 = circuit.net("qspi_sd0")
        qspi_sd1 = circuit.net("qspi_sd1")
        qspi_sd2 = circuit.net("qspi_sd2")
        qspi_sd3 = circuit.net("qspi_sd3")
        xin = circuit.net("xin")
        xout = circuit.net("xout")
        xosc = circuit.net("xosc")
        usb_dp_r = circuit.net("usb_dp_r")
        usb_dm_r = circuit.net("usb_dm_r")

        circuit.part(
            "U1",
            Rp2040(
                iovdd=v3v3,
                dvdd=dvdd,
                gnd=gnd,
                vreg_vin=v3v3,
                vreg_vout=dvdd,
                usb_vdd=v3v3,
                adc_avdd=v3v3,
                gpio0=adc["sdata"],
                gpio1=adc["cs"],
                gpio2=adc["sclk"],
                gpio4=ring_txa,
                gpio5=ring_rxb,
                gpio6=ring_rxa,
                gpio7=ring_txb,
                gpio8=tap_rx,
                gpio9=tap_tx,
                gpio10=tap_comp,
                gpio11=tap_led,
                gpio12=swio,
                gpio13=dbg_rx,
                gpio14=pot_pwm[1],
                gpio15=pot_pwm[3],
                gpio16=pot_pwm[5],
                gpio17=pot_pwm[7],
                gpio18=srclk,
                gpio19=sdo,
                gpio20=sdi,
                gpio21=commit,
                gpio22=oe_n,
                xin=xin,
                xout=xout,
                # No external reset: RUN ties to IOVDD (DS §1.4.2).
                run=v3v3,
                testen=gnd,
                usb_dp=usb_dp_r,
                usb_dm=usb_dm_r,
                qspi_sd0=qspi_sd0,
                qspi_sd1=qspi_sd1,
                qspi_sd2=qspi_sd2,
                qspi_sd3=qspi_sd3,
                qspi_sclk=qspi_sclk,
                qspi_ss=qspi_ss,
            ),
        )
        circuit.part(
            "U2",
            W25q16jvssiq(
                cs=qspi_ss,
                clk=qspi_sclk,
                di=qspi_sd0,
                do=qspi_sd1,
                wp=qspi_sd2,
                hold=qspi_sd3,
                vcc=v3v3,
                gnd=gnd,
            ),
        )
        # The QSPI_SS strap pair (AN §2.2), placed close to the flash:
        # R1 — the mandatory BOOTSEL resistor: lets QSPI_SS over-drive
        # an applied pull-down once booting starts. NC on usb_boot is a
        # normal flash boot; short to GND at reset for BOOTSEL.
        circuit.part("R1", R0603("1k", a=qspi_ss, b=usb_boot))
        # R2 — /CS-must-track-VCC pull-up: the AN marks it DNF for its
        # W25Q128JVS, but the W25Q16JV requires it (W25Q16JV DS §4.1;
        # datasheets/RP2040/notes/quirks.md).
        circuit.part("R2", R0603("10k", a=qspi_ss, b=v3v3))
        # The crystal circuit (AN §2.3), tuned for the ABM8-272-T3 at
        # 3.3 V IOVDD: 15 pF load caps, 1 kΩ XOUT series resistor
        # against over-drive.
        circuit.part("X1", Abm8272t3(a=xin, b=xosc, gnd=gnd))
        circuit.part("R5", R0603("1k", a=xout, b=xosc))
        circuit.part("C2", C0603("15p", a=xin, b=gnd))
        circuit.part("C3", C0603("15p", a=xosc, b=gnd))
        # USB series termination, close to the chip (AN §2.4.1).
        circuit.part("R6", R0603("27", a=usb_dp, b=usb_dp_r))
        circuit.part("R7", R0603("27", a=usb_dm, b=usb_dm_r))
        # Decoupling (AN §2.1.2/§2.1.3): 100 nF per power pin — one per
        # IOVDD pad, one at USB_VDD, one at ADC_AVDD, one per DVDD pad
        # — plus the mandatory 1 µF at each VREG pin.
        for pin in ("1", "10", "22", "33", "42", "49"):
            circuit.part(
                f"C_io{pin}",
                C0603("100n", a=v3v3, b=gnd),
                note=f"at U1 pin {pin} (IOVDD)",
            )
        circuit.part(
            "C_usb", C0603("100n", a=v3v3, b=gnd), note="at U1 pin 48 (USB_VDD)"
        )
        circuit.part(
            "C_adc", C0603("100n", a=v3v3, b=gnd), note="at U1 pin 43 (ADC_AVDD)"
        )
        circuit.part(
            "C_dvdd23", C0603("100n", a=dvdd, b=gnd), note="at U1 pin 23 (DVDD)"
        )
        circuit.part(
            "C_dvdd50", C0603("100n", a=dvdd, b=gnd), note="at U1 pin 50 (DVDD)"
        )
        circuit.part(
            "C_vreg_in",
            C0603("1u", a=v3v3, b=gnd),
            note="at U1 pin 44 (VREG_IN)",
        )
        circuit.part(
            "C_vreg_out",
            C0603("1u", a=dvdd, b=gnd),
            note="at U1 pin 45 (VREG_OUT)",
        )


def capture(symbols: SymbolTable) -> Circuit:
    """Build the standalone supervisor IR."""
    circuit = Circuit("supervisor", symbols)
    Supervisor().capture(circuit)
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
