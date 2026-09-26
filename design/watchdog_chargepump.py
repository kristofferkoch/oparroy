"""Charge-pump bypass watchdog, captured in the DSL (DESIGN.md §4, §7).

Flat re-capture of ``circuits/watchdog-chargepump/watchdog-chargepump.cir``
— the T7a proving circuit. The edge-sensitive charge pump: the MCU
emits a 20 kHz keep-alive on ``ka``; only transitions pump charge into
Cs, so a hung MCU lets Rb pull ``sel`` below VIL and the bypass switch
relaxes closed — bypass is the default state. D1 is one BAT54S series
pair: pin 3 (COM) is the shared middle (cathode of the clamp diode,
anode of the pump diode); pin 2 (K) is the pump cathode.

``ka`` is the subcircuit's input port, so the validation pass reports
it as a single-pin net by design; ports are T7b's concept.

Usage (in the nix dev shell):

    python -m design.watchdog_chargepump            # check + netlist
    python -m design.watchdog_chargepump --dot      # Graphviz view
"""

import argparse
import sys

from oparroy.dsl import (
    Circuit,
    KiCadLibraries,
    SymbolTable,
    check,
    emit_netlist,
    raise_on_errors,
    to_dot,
)

_R0603 = "Resistor_SMD:R_0603_1608Metric"
_C0603 = "Capacitor_SMD:C_0603_1608Metric"


def capture(symbols: SymbolTable) -> Circuit:
    """Build the watchdog circuit IR."""
    circuit = Circuit("watchdog-chargepump", symbols)
    rs = circuit.part("Rs", symbol="Device:R", value="220", footprint=_R0603)
    cp = circuit.part("Cp", symbol="Device:C", value="22n", footprint=_C0603)
    d1 = circuit.part(
        "D1",
        symbol="Diode:BAT54S",
        value="BAT54S",
        footprint="Package_TO_SOT_SMD:SOT-23",
    )
    cs = circuit.part("Cs", symbol="Device:C", value="10n", footprint=_C0603)
    rb = circuit.part("Rb", symbol="Device:R", value="47k", footprint=_R0603)

    ka = circuit.net("ka")
    kap = circuit.net("kap")
    x = circuit.net("x")
    sel = circuit.net("sel")
    gnd = circuit.net("GND")
    circuit.connect(ka, rs[1])
    circuit.connect(kap, rs[2], cp[1])
    circuit.connect(x, cp[2], d1[3])
    circuit.connect(sel, d1[2], cs[1], rb[1])
    circuit.connect(gnd, d1[1], cs[2], rb[2])
    return circuit


def main() -> None:
    """Check the capture and emit the KiCad netlist (or dot with --dot)."""
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
    sys.stdout.write(to_dot(circuit) if args.dot else emit_netlist(circuit))


if __name__ == "__main__":
    main()
