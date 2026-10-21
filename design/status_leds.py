"""Status LEDs, captured as a subcircuit with a sim-pinned contract (§4.1, §7).

The node's four status LEDs: passive power (red), working heartbeat
(yellow), and the per-connector link pair (yellow-green) merged onto
one antiparallel GPIO behind a shared 470 Ω — pin high lights Du
(upstream), pin low lights Dd (downstream), Hi-Z dark, a kHz toggle
lights both at half brightness (§4.1). Dd's anode returns
to 3V3, not GND: the pin-low state sinks rail current through Dd and
Rs into the pad — anode on GND leaves Dd dark forever (caught in
pcbnew netlist review). The shared 470 Ω sets ~2.5 mA at
Vf ≈ 2.1 V, inside the CH32V003's ±8 mA pad drive. The resistor
values are generators, not literals: the solve pass sizes each from
the rail's declared voltage, so a parent binding a different supply
recomputes them (DESIGN.md §7).

The drive-state truth table is the executable contract:
``circuits/status-leds/tb_status_leds.cir`` asserts pin high, pin low,
and Hi-Z against the emitted DUT — the §7 subcircuit-with-bench
pattern this block owed from the start.

Ports (the subcircuit interface): ``v3v3``, ``gnd``, ``led_work``
(working-LED drive), ``led_seg`` (the antiparallel link GPIO). The
pads stay on the front over routed holes (the reverse-mount bin,
§4.1).

Usage (in the nix dev shell):

    python -m design.status_leds            # check + netlist
    python -m design.status_leds --dot      # Graphviz view
    python -m design.status_leds --spice    # ngspice DUT netlist
"""

import argparse
import sys
from dataclasses import dataclass

from design.bins import R0603, LedRev1206
from oparroy.dsl import (
    Circuit,
    DefinitionError,
    Generator,
    Interval,
    KiCadLibraries,
    Led,
    Limits,
    PowerDomainKind,
    SolveContext,
    Subcircuit,
    SymbolTable,
    ValueRange,
    check,
    emit_netlist,
    emit_spice,
    raise_on_errors,
    solve,
    to_dot,
)

# Stand-in Vf parameters (≈2.0 V at 2.5 mA) for the XL-3216-FB series;
# the bench windows absorb the per-color spread. Ad hoc like the
# watchdog's BAT54S binding until the parts DB owns models.
SPICE_MODELS = {
    "XL-3216SURC-FB": "d(is=1e-19 n=2.0 rs=10)",
    "XL-3216SYGC-FB": "d(is=1e-19 n=2.0 rs=10)",
    "XL-3216UYC-FB": "d(is=1e-19 n=2.0 rs=10)",
}


@dataclass(frozen=True)
class StatusLedSet:
    """The block's per-role LED parts: the bin plus the three values.

    ``power``/``working``/``link`` are the part values for the §4.1
    roles (red power, yellow working, yellow-green antiparallel link
    pair). The node board and the CI tiles run different deliveries of
    the same block — reverse-mount over routed holes where the viewer
    is connector-side, top-emitting where the viewer stands over the
    component side — so the set is a constructor parameter, not a
    hard-coded bin.
    """

    bin: type[Led]
    power: str
    working: str
    link: str


#: The node board's set (DESIGN.md §4.1): reverse-mount 1206 emitting
#: through routed holes to the connector side. Also the standalone
#: capture's set — the sim bench's SPICE_MODELS key on these values.
NODE_STATUS_LEDS = StatusLedSet(
    bin=LedRev1206,
    power="XL-3216SURC-FB",
    working="XL-3216UYC-FB",
    link="XL-3216SYGC-FB",
)


@dataclass(frozen=True)
class LedSeriesResistor:
    """A generator: size an LED's series resistor from the rail it runs on.

    ``rail`` names the block's supply net; the solve pass reads its
    declared voltage (``Circuit.power_domain(..., voltage=...)``),
    following instance bindings outward so a parent at 5 V gets a 5 V
    resistor. ``forward_v`` is the LED's typical drop and ``current``
    the target drive; ``tolerance`` is the acceptable current spread
    the stocked bin resolves inside. The LED's Vf is a generator
    parameter (the parts DB owns no LED model yet), not a value read
    from another part.
    """

    rail: str
    forward_v: float
    current: float
    tolerance: float = 0.10

    def __call__(self, context: SolveContext) -> ValueRange:
        """Return the series resistor's spec for ``context``'s rail."""
        voltage = context.rail_voltage(self.rail)
        if voltage is None:
            msg = (
                f"rail {self.rail!r} has no declared voltage — declare it "
                "with Circuit.power_domain(..., voltage=ValueRange(...))"
            )
            raise DefinitionError(msg)
        assert voltage.nominal is not None  # noqa: S101 — ValueRange fills it
        headroom = voltage.nominal - self.forward_v
        if headroom <= 0:
            msg = (
                f"rail {self.rail!r} at {voltage} has no headroom over the "
                f"LED's {self.forward_v:g} V forward drop"
            )
            raise DefinitionError(msg)
        return ValueRange.around(
            headroom / self.current, self.tolerance, family="resistor"
        )


def _series_resistor(rail: str, forward_v: float, current: float) -> Generator:
    """Build the generator spec for one LED operating point."""
    return Generator(LedSeriesResistor(rail=rail, forward_v=forward_v, current=current))


class StatusLeds(Subcircuit):
    """The §4.1 status-LED block: power, working, antiparallel link pair.

    ``leds`` picks the per-role parts; the default is the node board's
    reverse-mount set. The CI tiles pass their forward-mount set
    (``design/ci_tiles.py`` — the bench board's viewer is on the
    component side).
    """

    def __init__(self, *, leds: StatusLedSet = NODE_STATUS_LEDS) -> None:
        self._leds = leds

    def capture(self, circuit: Circuit) -> None:
        """Build the block: ports v3v3/gnd/led_work/led_seg."""
        v3v3 = circuit.port("v3v3")
        gnd = circuit.port("gnd")
        # The rail's declared voltage is the generator's context. The
        # 3.3 V ±3% band is the LDO's regulation window; a parent that
        # binds a different rail overrides it when solve walks the
        # binding chain.
        circuit.power_domain(
            v3v3,
            kind=PowerDomainKind.ALWAYS,
            voltage=ValueRange.around(3.3, 0.03),
        )
        circuit.power_domain(gnd, kind=PowerDomainKind.GROUND)
        led_work = circuit.port("led_work", sink=Limits(voltage=Interval(0, 3.6)))
        led_seg = circuit.port("led_seg", sink=Limits(voltage=Interval(0, 3.6)))
        pwr_led = circuit.net("pwr_led")
        ledw_a = circuit.net("ledw_a")
        led_x = circuit.net("led_x")
        circuit.part(
            "Rp",
            R0603(_series_resistor("v3v3", 2.0, 1.3e-3), a=v3v3, b=pwr_led),
            note="current limit for {Dp}",
        )
        circuit.part(
            "Dp",
            self._leds.bin(anode=pwr_led, cathode=gnd, value=self._leds.power),
            note="power LED",
        )
        circuit.part(
            "Rw",
            R0603(_series_resistor("v3v3", 2.0, 1.3e-3), a=led_work, b=ledw_a),
            note="current limit for {Dw}",
        )
        circuit.part(
            "Dw",
            self._leds.bin(anode=ledw_a, cathode=gnd, value=self._leds.working),
            note="working heartbeat LED",
        )
        circuit.part(
            "Rs",
            R0603(_series_resistor("v3v3", 2.1, 2.5e-3), a=led_seg, b=led_x),
            note="shared current limit for the {Du}/{Dd} link pair",
        )
        circuit.part(
            "Du",
            self._leds.bin(anode=led_x, cathode=gnd, value=self._leds.link),
            note="upstream link LED, antiparallel with {Dd}",
        )
        circuit.part(
            "Dd",
            self._leds.bin(anode=v3v3, cathode=led_x, value=self._leds.link),
            note="downstream link LED, antiparallel with {Du}",
        )


def capture(symbols: SymbolTable) -> Circuit:
    """Build the standalone status-LED circuit IR."""
    circuit = Circuit("status-leds", symbols)
    StatusLeds().capture(circuit)
    return circuit


def main() -> None:
    """Check the capture and emit the KiCad netlist (--dot/--spice: other views)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dot",
        action="store_true",
        help="emit the Graphviz dot view instead of the KiCad netlist",
    )
    parser.add_argument(
        "--spice",
        action="store_true",
        help="emit the ngspice DUT netlist (status_leds .subckt) instead",
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
    elif args.spice:
        # The subckt name matches the bench deck's instantiation, so
        # circuits/status-leds/tb_status_leds.cir drives this emission
        # unmodified (spice_emit.py's module docstring has the split).
        sys.stdout.write(emit_spice(circuit, name="status_leds", models=SPICE_MODELS))
    else:
        sys.stdout.write(emit_netlist(circuit))


if __name__ == "__main__":
    main()
