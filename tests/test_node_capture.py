"""Node-board capture tests (need the nix-provisioned libraries).

The golden netlist at tests/golden/oparroy-node.net is what pcbnew
ingests — the post-annotation emission; regenerate it from the dev
shell with:

    python -m design.node > tests/golden/oparroy-node.net
"""

from __future__ import annotations

from pathlib import Path

from design.node import capture
from oparroy.dsl import (
    Circuit,
    KiCadLibraries,
    Severity,
    annotate,
    apply_annotation,
    check,
    emit_netlist,
)

GOLDEN = Path(__file__).parent / "golden" / "oparroy-node.net"

#: The MCU pins the node leaves unconnected: the §6 payload-superset
#: pads (PD5, PD6, PC4, PC5, PC6) plus PC1, freed by the §4.1 LED
#: merge (PC7 is a spare too, but lands on the TP4 test pad).
EXPECTED_NC_WARNINGS = {f"U1.{pin} is not connected" for pin in (2, 3, 11, 14, 15, 16)}


def nets_of(circuit: Circuit) -> dict[str, set[str]]:
    """Net name -> member pins as 'ref.number', over the flattened IR."""
    flat = circuit.flatten() if circuit.instances else circuit
    return {
        name: {f"{p.part.ref}.{p.number}" for p in net.pins}
        for name, net in flat.nets.items()
    }


def test_bypass_switch_topology(kicad_libs: KiCadLibraries) -> None:
    # §3/§4: B1 = upstream (the node's RX tap stays connected in
    # bypass), B2 = node TX, COM toward the downstream connector.
    nets = nets_of(capture(kicad_libs))
    assert nets["opa_p"] == {"U1.6", "PHY1/Rar.2", "PHY1/SW1.3", "PHY1/Rfb.2"}
    assert nets["txa_drv"] == {"U1.19", "PHY1/SW1.1"}
    assert nets["PHY1/txa_sw"] == {"PHY1/SW1.4", "PHY1/Rat.1"}
    assert nets["TX_A"] == {"J2.5", "PHY1/Rat.2", "PHY1/Dat.1"}


def test_terminal_protection_sits_connector_side(kicad_libs: KiCadLibraries) -> None:
    # §7 checklist: connector -> TVS -> R -> µC, on every ring terminal.
    nets = nets_of(capture(kicad_libs))
    assert nets["RX_A"] == {"J1.5", "PHY1/Rar.1", "PHY1/Dar.1"}
    assert nets["RX_B"] == {"J2.7", "PHY1/Rbr.1", "PHY1/Dbr.1"}
    assert nets["TX_B"] == {"J1.7", "PHY1/Rbt.2", "PHY1/Dbt.1"}
    assert nets["opa_p_b"] == {"U1.4", "PHY1/Rbr.2"}
    assert nets["txb_drv"] == {"U1.13", "PHY1/Rbt.1"}


def test_sel_drives_switch_and_brake(kicad_libs: KiCadLibraries) -> None:
    # §2/§4: the watchdog's sel drives TIM1_BKIN (PC2, the hardware
    # TX-kill) and, through the 0 Ω bridge (the DNP Schmitt buffer
    # straddles it, 2026-09-29), the bypass select — bypass engaging
    # brakes both TX.
    nets = nets_of(capture(kicad_libs))
    assert nets["sel"] == {
        "U1.12",
        "WD1/D1.2",
        "WD1/Cs.1",
        "WD1/Rb.1",
        "PHY1/Rsel.1",
        "PHY1/BUF1.2",
    }
    assert nets["PHY1/sel_sw"] == {"PHY1/Rsel.2", "PHY1/BUF1.4", "PHY1/SW1.6"}


def test_connector_leds_share_one_antiparallel_gpio(kicad_libs: KiCadLibraries) -> None:
    # §4.1 (2026-09-30): both connector LEDs sit on PC0 as an
    # antiparallel pair behind one shared 470 Ω — pin high lights
    # upstream (Du), pin low lights downstream (Dd), Hi-Z dark.
    nets = nets_of(capture(kicad_libs))
    assert nets["led_seg"] == {"U1.10", "Rs.1"}
    assert nets["led_x"] == {"Rs.2", "Du.2", "Dd.1"}
    assert {"Du.1", "Dp.1", "Dw.1"} <= nets["GND"]
    assert "Dd.2" in nets["GND"]


def test_pc7_spare_lands_on_a_test_pad(kicad_libs: KiCadLibraries) -> None:
    # 2026-09-29: the PC7 spare is a bare test pad, not a floating pin.
    nets = nets_of(capture(kicad_libs))
    assert nets["pc7"] == {"U1.17", "TP4.1"}


def test_threshold_divider_on_opa_negative(kicad_libs: KiCadLibraries) -> None:
    # §2: VDD/2 from the 10k bin on OPA_N0 (PA1).
    nets = nets_of(capture(kicad_libs))
    assert nets["opa_n"] == {"U1.5", "PHY1/Rth1.2", "PHY1/Rth2.1"}


def test_power_loop_enters_from_both_faces(kicad_libs: KiCadLibraries) -> None:
    # §3: UNREG/3V3/GND alias into both connectors; 3V3 is doubled and
    # row 2 (pins 2/4/6/8/10) is a solid ground row (2026-09-29 pinout).
    nets = nets_of(capture(kicad_libs))
    assert {"J1.1", "J2.1"} <= nets["UNREG"]
    assert {"J1.3", "J1.9", "J2.3", "J2.9"} <= nets["3V3"]
    assert {
        f"{j}.{pin}" for j in ("J1", "J2") for pin in ("2", "4", "6", "8", "10")
    } <= nets["GND"]


def test_capture_checks_clean(kicad_libs: KiCadLibraries) -> None:
    issues = check(capture(kicad_libs), footprints=kicad_libs)
    assert [i for i in issues if i.severity is Severity.ERROR] == []
    assert {i.message for i in issues} == EXPECTED_NC_WARNINGS


def test_annotation_is_stable(kicad_libs: KiCadLibraries) -> None:
    circuit = capture(kicad_libs)
    first = annotate(circuit)
    assert annotate(circuit, prior=first).refs == first.refs


def test_netlist_matches_golden(kicad_libs: KiCadLibraries) -> None:
    circuit = capture(kicad_libs)
    rendered = emit_netlist(apply_annotation(circuit, annotate(circuit)))
    assert rendered == GOLDEN.read_text(encoding="utf-8")


def test_netlist_byte_identical_across_runs(kicad_libs: KiCadLibraries) -> None:
    def render() -> str:
        circuit = capture(kicad_libs)
        return emit_netlist(apply_annotation(circuit, annotate(circuit)))

    assert render() == render()
