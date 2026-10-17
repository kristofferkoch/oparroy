"""One ring segment, node k to node k+1, captured in the DSL (DESIGN.md §2, §7).

The DSL form of the ``phy_segment`` simulation DUT: node TX pin →
74LVC1G3157 bypass/insert switch → lumped segment → next node's OPA
comparator RX (docs/phy-analysis.md §2/§5). 3.3 V single-ended,
800 kbit/s WS2812-style duty-coded cells: 1.25 µs cell, T0H=395 ns,
T1H=792 ns (48 MHz timer quantization). This is a simulation test
vehicle, not a BOM circuit: it exists to drive the
``circuits/phy-segment/tb_*.cir`` benches and is never netlisted for
KiCad (the emitter refuses the sim-only parts).

Ports (the ``.subckt phy_segment`` interface the benches instantiate):
``up`` (upstream line — the bypass source), ``txin`` (node TX logic
in), ``sel`` (switch select: high = node inserted / B2, low = bypass /
B1), ``line`` (segment far end / next node's RX tap — the probe
point), ``rxout`` (comparator out, standing in for the internal
TIM2_CH1 route), ``vdd``, ``gnd``.

Subcircuit parameters (benches sweep them via ``alterparam``):
``cseg=220p`` — lumped segment capacitance to gnd at the RX end;
``lseg=1n`` — series inductance for ringing studies (~0 by default:
57 Ω source into 1n/220p is heavily overdamped); ``voff=0`` —
comparator input offset, swept ±13 m (DS0 §3.3.15 T3-26);
``vth=1.65``, ``vcc=3.3`` — passed through to the switch and the
device models.

RX front-end: VDD/2 from two 10k into the OPA negative input (5k
Thevenin — stiff against the OPA's unmodeled input bias), line into
the positive input; the comparator output carries the 4 kΩ / 50 pF
load of the datasheet wake-up test condition (T3-26).

The device models (``ch32v003_tx_pin``, ``ch32v003_opa_cmp``,
``sn74lvc1g3157``) stay hand-written includes (``circuits/lib/*.spi``)
— the emission carries the same ``.include`` lines the hand-written
DUT did, so the benches' include-transitivity contract holds: a bench
includes the DUT only, the lib models arrive through it.

Usage (in the nix dev shell):

    python -m design.phy_segment            # check only (sim-only capture)
    python -m design.phy_segment --dot      # Graphviz view
    python -m design.phy_segment --spice    # ngspice DUT netlist (phy_segment)
"""

import argparse
import sys

from design.parts_db import C0603, R0603
from oparroy.dsl import (
    Circuit,
    Inductor,
    KiCadLibraries,
    SimSymbols,
    SymbolTable,
    check,
    emit_spice,
    raise_on_errors,
    to_dot,
)

#: The DUT's tunables, in the hand-written subckt's declaration order.
SPICE_PARAMS = {"cseg": "220p", "lseg": "1n", "voff": "0", "vth": "1.65", "vcc": "3.3"}

#: The hand-written device models the DUT instantiates, in the
#: hand-written DUT's include order. ngspice resolves them against the
#: bench's working directory (scripts/sim-run runs each bench from its
#: own directory), so the paths stay relative to circuits/<bench>/.
SPICE_INCLUDES = ("../lib/sn74lvc1g3157.spi", "../lib/ch32v003.spi")


def capture(symbols: SymbolTable) -> Circuit:
    """Build the phy-segment DUT circuit IR."""
    sims = SimSymbols(symbols)
    tx_pin = sims.subckt("ch32v003_tx_pin", ("in", "out", "vdd", "gnd"))
    switch = sims.subckt("sn74lvc1g3157", ("a", "b1", "b2", "s", "vcc", "gnd"))
    opa_cmp = sims.subckt("ch32v003_opa_cmp", ("inp", "inn", "out", "vdd", "gnd"))

    circuit = Circuit("phy-segment", sims)
    up = circuit.port("up")
    txin = circuit.port("txin")
    sel = circuit.port("sel")
    line = circuit.port("line")
    rxout = circuit.port("rxout")
    vdd = circuit.port("vdd")
    gnd = circuit.port("gnd")
    tx = circuit.net("tx")
    swa = circuit.net("swa")
    th = circuit.net("th")

    # "in" is a Python keyword — wire it through the ** mapping form.
    circuit.part(
        "Xtx",
        tx_pin(vdd=vdd, gnd=gnd, params={"vcc": "{vcc}"}, **{"in": txin, "out": tx}),
    )
    circuit.part(
        "Xsw",
        switch(
            a=swa,
            b1=up,
            b2=tx,
            s=sel,
            vcc=vdd,
            gnd=gnd,
            params={"vth": "{vth}", "vcc": "{vcc}"},
        ),
    )
    circuit.part("Lseg", Inductor("{lseg}", a=swa, b=line, footprint=_L0603))
    circuit.part("Cseg", C0603("{cseg}", a=line, b=gnd))

    circuit.part("Rth1", R0603("10k", a=vdd, b=th))
    circuit.part("Rth2", R0603("10k", a=th, b=gnd))
    circuit.part(
        "Xcmp",
        opa_cmp(
            inp=line,
            inn=th,
            out=rxout,
            vdd=vdd,
            gnd=gnd,
            params={"voff": "{voff}", "vcc": "{vcc}"},
        ),
    )
    circuit.part("Rld", R0603("4k", a=rxout, b=gnd))
    circuit.part("Cld", C0603("50p", a=rxout, b=gnd))
    return circuit


#: Footprint stand-in for the segment inductor: the capture is a
#: simulation test vehicle and never reaches a board, but check()
#: requires one. 0603, matching the capture's R/C bins.
_L0603 = "Inductor_SMD:L_0603_1608Metric"


def main() -> None:
    """Check the capture; --dot/--spice emit the graph / DUT netlist views."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dot",
        action="store_true",
        help="emit the Graphviz dot view instead of running the checks only",
    )
    parser.add_argument(
        "--spice",
        action="store_true",
        help="emit the ngspice DUT netlist (phy_segment .subckt)",
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
        # The subckt name, includes, and params match the retired
        # hand-written DUT's interface, so circuits/phy-segment/tb_*.cir
        # drive this emission unmodified (spice_emit.py's module
        # docstring has the split).
        sys.stdout.write(
            emit_spice(
                circuit,
                name="phy_segment",
                includes=SPICE_INCLUDES,
                params=SPICE_PARAMS,
            )
        )


if __name__ == "__main__":
    main()
