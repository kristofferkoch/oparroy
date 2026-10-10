"""Charge-pump bypass watchdog, captured in the DSL (DESIGN.md §4, §7).

``WatchdogChargePump`` is the §7 subcircuit form of
``circuits/watchdog-chargepump/watchdog-chargepump.cir`` — the DSL
proving circuit, re-cast as a reusable subcircuit. The edge-sensitive
charge pump: the MCU emits a 20 kHz keep-alive on ``ka``; only
transitions pump charge into Cs, so a hung MCU lets Rb pull ``sel``
below VIL and the bypass switch relaxes closed — bypass is the default
state. D1 is one BAT54S series pair: pin 3 (COM) is the shared middle
(cathode of the clamp diode, anode of the pump diode); pin 2 (K) is
the pump cathode.

Ports (the subcircuit interface): ``ka`` (keep-alive input), ``sel``
(bypass-select output), ``GND``. The ports carry limit ranges as
interface contracts: ``ka`` accepts 0..3.6 V (3V3 logic from the MCU),
``sel`` drives 0..3.3 V toward the bypass switch's select input — an
instantiating parent checks interval containment against its own
declared ranges.

Part bins resolve from the parts DB (``design/parts_db.py``):
``R0603``/``C0603`` are the shared 0603 bins, and the BAT54S's
symbol/value/footprint pair comes from the ``bat54s`` record rather
than a per-capture declaration.

Usage (in the nix dev shell):

    python -m design.watchdog_chargepump            # check + netlist
    python -m design.watchdog_chargepump --dot      # Graphviz view
    python -m design.watchdog_chargepump --spice    # ngspice DUT netlist
"""

import argparse
import sys

from design.parts_db import C0603, PARTS, R0603
from oparroy.dsl import (
    Bat54s as _Bat54s,
)
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
    to_dot,
)

# Ad-hoc spice model bindings (the parts DB owns the records, but
# emitter-side model resolution is still open): the BAT54S-class
# pump diodes, stand-in parameters from
# circuits/watchdog-chargepump/watchdog-chargepump.cir's dpump model.
SPICE_MODELS = {"BAT54S": "d(is=200n n=1.0 rs=5 tt=1n bv=30)"}

#: The §4 series pair, bound from the DB's ``bat54s`` record.
Bat54s = PARTS.bind("bat54s", _Bat54s, class_name="Bat54s")


class WatchdogChargePump(Subcircuit):
    """The §4 edge-sensitive charge pump, as a reusable subcircuit."""

    def capture(self, circuit: Circuit) -> None:
        """Build the charge pump: ports ka/sel/GND, internal kap/x."""
        ka = circuit.port("ka", sink=Limits(voltage=Interval(0, 3.6)))
        sel = circuit.port("sel", source=Limits(voltage=Interval(0, 3.3)))
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
        help="emit the ngspice DUT netlist (wd_chargepump .subckt) instead",
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
    elif args.spice:
        # The subckt name matches the hand-written DUT's interface, so
        # circuits/watchdog-chargepump/tb_*.cir drive this emission
        # unmodified (spice_emit.py's module docstring has the split).
        sys.stdout.write(emit_spice(circuit, name="wd_chargepump", models=SPICE_MODELS))
    else:
        sys.stdout.write(emit_netlist(circuit))


if __name__ == "__main__":
    main()
