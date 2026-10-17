"""phy-segment DSL capture tests: golden emission and topology equivalence.

The topology test pins the capture against the interface and
connectivity of the retired hand-written DUT
(``circuits/phy-segment/phy-segment.cir``): same ports in the same
order, same net→pin membership. The bench equivalence (the
``tb_decode``/``tb_noise``/``tb_fault`` decks driven against this
emission, with the measured numbers of DESIGN.md §2 pinned) lives in
``test_phy_segment_benches.py`` — it needs the nix dev shell (ngspice).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from design.phy_segment import SPICE_INCLUDES, SPICE_PARAMS, capture
from oparroy.dsl import emit_spice

if TYPE_CHECKING:
    from conftest import StubSymbols

GOLDEN_PHY_SEGMENT = """\
* phy_segment — ngspice DUT netlist emitted by the oparroy DSL; regenerate, do not edit.
.include ../lib/sn74lvc1g3157.spi
.include ../lib/ch32v003.spi
.subckt phy_segment up txin sel line rxout vdd gnd
+ params: cseg=220p lseg=1n voff=0 vth=1.65 vcc=3.3
Cld rxout gnd 50p
Cseg line gnd {cseg}
Lseg swa line {lseg}
Rld rxout gnd 4k
Rth1 vdd th 10k
Rth2 th gnd 10k
Xcmp line th rxout vdd gnd ch32v003_opa_cmp params: voff={voff} vcc={vcc}
Xsw swa up tx sel vdd gnd sn74lvc1g3157 params: vth={vth} vcc={vcc}
Xtx txin tx vdd gnd ch32v003_tx_pin params: vcc={vcc}
.ends phy_segment
"""


def test_emission_matches_golden(symbols: StubSymbols) -> None:
    rendered = emit_spice(
        capture(symbols),
        name="phy_segment",
        includes=SPICE_INCLUDES,
        params=SPICE_PARAMS,
    )
    assert rendered == GOLDEN_PHY_SEGMENT


def test_emission_is_byte_identical_across_runs(symbols: StubSymbols) -> None:
    first = emit_spice(
        capture(symbols),
        name="phy_segment",
        includes=SPICE_INCLUDES,
        params=SPICE_PARAMS,
    )
    second = emit_spice(
        capture(symbols),
        name="phy_segment",
        includes=SPICE_INCLUDES,
        params=SPICE_PARAMS,
    )
    assert first == second


def test_capture_matches_retired_handwritten_cir(symbols: StubSymbols) -> None:
    """Net-by-net pin membership, exactly as the hand-written DUT wired it.

    Sim-part pin numbers are positional along the registered port list:
    Xtx in/out/vdd/gnd = 1..4, Xsw a/b1/b2/s/vcc/gnd = 1..6,
    Xcmp inp/inn/out/vdd/gnd = 1..5.
    """
    circuit = capture(symbols)
    assert list(circuit.ports) == ["up", "txin", "sel", "line", "rxout", "vdd", "gnd"]
    membership = {
        name: {f"{pin.part.ref}.{pin.number}" for pin in net.pins}
        for name, net in circuit.nets.items()
    }
    assert membership == {
        "up": {"Xsw.2"},
        "txin": {"Xtx.1"},
        "sel": {"Xsw.4"},
        "line": {"Lseg.2", "Cseg.1", "Xcmp.1"},
        "rxout": {"Xcmp.3", "Rld.1", "Cld.1"},
        "vdd": {"Xtx.3", "Xsw.5", "Rth1.1", "Xcmp.4"},
        "gnd": {"Xtx.4", "Xsw.6", "Cseg.2", "Rth2.2", "Xcmp.5", "Rld.2", "Cld.2"},
        "tx": {"Xtx.2", "Xsw.3"},
        "swa": {"Xsw.1", "Lseg.1"},
        "th": {"Rth1.2", "Rth2.1", "Xcmp.2"},
    }
