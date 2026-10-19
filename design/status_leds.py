"""Status LEDs, captured as a subcircuit with a sim-pinned contract (§4.1, §7).

The node's four status LEDs: passive power (red), working heartbeat
(yellow), and the per-connector link pair (yellow-green) merged onto
one antiparallel GPIO behind a shared 470 Ω — pin high lights Du
(upstream), pin low lights Dd (downstream), Hi-Z dark, a kHz toggle
lights both at half brightness (§4.1). Dd's anode returns
to 3V3, not GND: the pin-low state sinks rail current through Dd and
Rs into the pad — anode on GND leaves Dd dark forever (caught in
pcbnew netlist review). The shared 470 Ω sets ~2.5 mA at
Vf ≈ 2.1 V, inside the CH32V003's ±8 mA pad drive.

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

from design.bins import R0603, LedRev1206
from oparroy.dsl import (
    Circuit,
    Interval,
    KiCadLibraries,
    Limits,
    Subcircuit,
    SymbolTable,
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


class StatusLeds(Subcircuit):
    """The §4.1 status-LED block: power, working, antiparallel link pair."""

    def capture(self, circuit: Circuit) -> None:
        """Build the block: ports v3v3/gnd/led_work/led_seg."""
        v3v3 = circuit.port("v3v3")
        gnd = circuit.port("gnd")
        led_work = circuit.port("led_work", sink=Limits(voltage=Interval(0, 3.6)))
        led_seg = circuit.port("led_seg", sink=Limits(voltage=Interval(0, 3.6)))
        pwr_led = circuit.net("pwr_led")
        ledw_a = circuit.net("ledw_a")
        led_x = circuit.net("led_x")
        circuit.part(
            "Rp", R0603("1k", a=v3v3, b=pwr_led), note="current limit for {Dp}"
        )
        circuit.part(
            "Dp",
            LedRev1206(anode=pwr_led, cathode=gnd, value="XL-3216SURC-FB"),
            note="power LED",
        )
        circuit.part(
            "Rw", R0603("1k", a=led_work, b=ledw_a), note="current limit for {Dw}"
        )
        circuit.part(
            "Dw",
            LedRev1206(anode=ledw_a, cathode=gnd, value="XL-3216UYC-FB"),
            note="working heartbeat LED",
        )
        circuit.part(
            "Rs",
            R0603("470", a=led_seg, b=led_x),
            note="shared current limit for the {Du}/{Dd} link pair",
        )
        circuit.part(
            "Du",
            LedRev1206(anode=led_x, cathode=gnd, value="XL-3216SYGC-FB"),
            note="upstream link LED, antiparallel with {Dd}",
        )
        circuit.part(
            "Dd",
            LedRev1206(anode=v3v3, cathode=led_x, value="XL-3216SYGC-FB"),
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
