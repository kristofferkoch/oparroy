"""Charge-pump bypass watchdog, captured in the DSL (DESIGN.md §4, §7).

``WatchdogChargePump`` is the §7 subcircuit form of
``circuits/watchdog-chargepump/watchdog-chargepump.cir`` — the T7a
proving circuit, re-cast as T7ba's reusable unit. The edge-sensitive
charge pump: the MCU emits a 20 kHz keep-alive on ``ka``; only
transitions pump charge into Cs, so a hung MCU lets Rb pull ``sel``
below VIL and the bypass switch relaxes closed — bypass is the default
state. D1 is one BAT54S series pair: pin 3 (COM) is the shared middle
(cathode of the clamp diode, anode of the pump diode); pin 2 (K) is
the pump cathode.

Ports (the subcircuit interface): ``ka`` (keep-alive input), ``sel``
(bypass-select output), ``GND``.

Usage (in the nix dev shell):

    python -m design.watchdog_chargepump            # check + netlist
    python -m design.watchdog_chargepump --dot      # Graphviz view
"""

import argparse
import sys

from oparroy.dsl import (
    Bat54s,
    Capacitor,
    Circuit,
    KiCadLibraries,
    Resistor,
    Subcircuit,
    SymbolTable,
    check,
    emit_netlist,
    raise_on_errors,
    to_dot,
)


class R0603(Resistor):
    """The project's 0603 resistor bin: class-default footprint (§7)."""

    default_footprint = "Resistor_SMD:R_0603_1608Metric"


class C0603(Capacitor):
    """The project's 0603 capacitor bin: class-default footprint (§7)."""

    default_footprint = "Capacitor_SMD:C_0603_1608Metric"


class WatchdogChargePump(Subcircuit):
    """The §4 edge-sensitive charge pump, as a reusable subcircuit."""

    def capture(self, circuit: Circuit) -> None:
        """Build the charge pump: ports ka/sel/GND, internal kap/x."""
        ka = circuit.port("ka")
        sel = circuit.port("sel")
        gnd = circuit.port("GND")
        kap = circuit.net("kap")
        x = circuit.net("x")
        circuit.part("Rs", R0603("220", a=ka, b=kap))
        circuit.part("Cp", C0603("22n", a=kap, b=x))
        circuit.part("D1", Bat54s(anode=gnd, com=x, cathode=sel))
        circuit.part("Cs", C0603("10n", a=sel, b=gnd))
        circuit.part("Rb", R0603("47k", a=sel, b=gnd))


def capture(symbols: SymbolTable) -> Circuit:
    """Build the standalone watchdog circuit IR."""
    circuit = Circuit("watchdog-chargepump", symbols)
    WatchdogChargePump().capture(circuit)
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
