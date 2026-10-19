"""Scan-plane capture tests (docs/scan-plane.md; need the KiCad libs).

Covers the 13-stage chain topology and bit map (§1/§3), the §4 POR
discipline in copper (/OE pull-up, per-line pull-downs with the
FET-gate exemptions, /SRCLR high, CLK_INH low, per-stage decoupling),
and the §5 SWIO/debug 3157 trees (topology, ganged selects, pull-up
placement).
"""

from __future__ import annotations

from itertools import pairwise

from design.ci_tiles import MEASUREMENT_TILE
from design.scan_plane import (
    AUX0_BITS,
    AUX1_BITS,
    AUX2_BITS,
    DebugTree,
    ScanPlane,
    SwioTree,
    tile_bits,
)
from oparroy.dsl import Circuit, KiCadLibraries, Severity, Subcircuit, check

#: §4's 47 kΩ pull-down count: 49 tile lines (7/tile on the seven
#: switching tiles; the measurement tile drives PWR alone, §12) + 6
#: supervisor + 3 SWIO + 1 WD_DEFEAT + 4 POT_SEL (BTN_* exempt).
PULLDOWN_COUNT = 63


def nets_of(circuit: Circuit) -> dict[str, set[str]]:
    """Net name -> member pins as 'ref.number', over the flattened IR."""
    flat = circuit.flatten() if circuit.instances else circuit
    return {
        name: {f"{p.part.ref}.{p.number}" for p in net.pins}
        for name, net in flat.nets.items()
    }


def scan_plane_nets(libs: KiCadLibraries) -> dict[str, set[str]]:
    """Capture the standalone scan plane and flatten it."""
    circuit = Circuit("scan-plane-test", libs)
    ScanPlane().capture(circuit)
    return nets_of(circuit)


def test_chain_order(kicad_libs: KiCadLibraries) -> None:
    """RP2040 -> AUX0 -> AUX1 -> AUX2 -> T0..T7 -> OBS0 -> OBS1 -> RP2040 (§1)."""
    nets = scan_plane_nets(kicad_libs)
    # ser enters AUX0 (pin 14) from SDO; QH' (pin 9) cascades.
    assert "AUX0/U1.14" in nets["sdo"]
    order = ["AUX0", "AUX1", "AUX2", *[f"T{i}" for i in range(8)], "OBS0", "OBS1"]
    for upstream, downstream in pairwise(order):
        link = f"chain_{upstream.lower()}"
        ser_pin = "10" if downstream.startswith("OBS") else "14"
        assert f"{upstream}/U1.9" in nets[link]
        assert f"{downstream}/U1.{ser_pin}" in nets[link]
    assert "OBS1/U1.9" in nets["sdi"]
    # SRCLK/COMMIT broadcast to all 13 stages; /OE on the 595s only (§1).
    for stage in order:
        clk_pin = "2" if stage.startswith("OBS") else "11"
        ld_pin = "1" if stage.startswith("OBS") else "12"
        assert f"{stage}/U1.{clk_pin}" in nets["srclk"]
        assert f"{stage}/U1.{ld_pin}" in nets["commit"]
    for stage in order[:11]:
        assert f"{stage}/U1.13" in nets["oe_n"]
    assert "OBS0/U1.13" not in nets.get("oe_n", set())


def test_bit_map_ports(kicad_libs: KiCadLibraries) -> None:
    """The §3 bit maps: bit 0 = QA / D0 = A, per-stage naming."""
    nets = scan_plane_nets(kicad_libs)
    # 595 outputs: QA=15, QB=1, QC=2, QD=3, QE=4, QF=5, QG=6, QH=7.
    q_pins = ["15", "1", "2", "3", "4", "5", "6", "7"]
    for tile in range(8):
        for index, bit in enumerate(tile_bits(tile)):
            assert f"T{tile}/U1.{q_pins[index]}" in nets[f"t{tile}_{bit}"]
    # The measurement tile's slice drives PWR alone; its seven spare
    # outputs are internal nets, filled like AUX2's (§1/§12).
    for index in range(1, len(q_pins)):
        assert (
            f"T{MEASUREMENT_TILE}/U1.{q_pins[index]}"
            in nets[f"t{MEASUREMENT_TILE}_spare{index}"]
        )
    for stage, bits in (("AUX0", AUX0_BITS), ("AUX1", AUX1_BITS), ("AUX2", AUX2_BITS)):
        for index, bit in enumerate(bits):
            assert f"{stage}/U1.{q_pins[index]}" in nets[bit]
    # 165 inputs: D0..D7 = pins 11,12,13,14,3,4,5,6 (§3: D0 = A = bit 0).
    d_pins = ["11", "12", "13", "14", "3", "4", "5", "6"]
    for obs, tiles in (("OBS0", range(4)), ("OBS1", range(4, 8))):
        for index, tile in enumerate(tiles):
            assert f"{obs}/U1.{d_pins[2 * index]}" in nets[f"t{tile}_sel"]
            assert f"{obs}/U1.{d_pins[2 * index + 1]}" in nets[f"t{tile}_3v3n"]


def test_por_discipline(kicad_libs: KiCadLibraries) -> None:
    """§4: /OE pulled up; 63 pull-downs, exempting the FET-gate lines."""
    nets = scan_plane_nets(kicad_libs)
    assert nets["oe_n"] >= {"R_OE.1"}
    assert nets["3V3"] >= {"R_OE.2"}
    pulled = [name for name in nets if f"R_{name.upper()}.1" in nets[name]]
    assert len(pulled) == PULLDOWN_COUNT
    # The FET-gate lines carry their pull-downs at the transforms
    # (instrumented-ci.md §7): no plane-side resistor on PWR or BTN_*.
    for tile in range(8):
        assert f"R_T{tile}_PWR.1" not in nets[f"t{tile}_pwr"]
    for bit in (*AUX1_BITS, *AUX2_BITS):
        if bit.startswith("btn_"):
            assert f"R_{bit.upper()}.1" not in nets[bit]
    # Switch-select lines get one each.
    assert nets["swio_a0"] >= {"AUX0/U1.6", "R_SWIO_A0.1"}
    assert nets["wd_defeat"] >= {"R_WD_DEFEAT.1"}
    assert nets["pot_sel7"] >= {"R_POT_SEL7.1"}
    # /SRCLR tied high on every 595; CLK_INH low on every 165 (§4/§1).
    for stage in [*(f"T{i}" for i in range(8)), "AUX0", "AUX1", "AUX2"]:
        assert f"{stage}/U1.10" in nets["3V3"]
    for obs in ("OBS0", "OBS1"):
        assert f"{obs}/U1.15" in nets["GND"]
    # One 100 nF per stage (§7).
    for stage in [*(f"T{i}" for i in range(8)), "AUX0", "AUX1", "AUX2", "OBS0", "OBS1"]:
        assert f"{stage}/C1.1" in nets["3V3"]
        assert f"{stage}/C1.2" in nets["GND"]


def test_capture_checks_clean(kicad_libs: KiCadLibraries) -> None:
    circuit = Circuit("scan-plane-test", kicad_libs)
    ScanPlane().capture(circuit)
    issues = check(circuit, footprints=kicad_libs)
    assert [i for i in issues if i.severity is Severity.ERROR] == []


def tree_nets(libs: KiCadLibraries, tree: Subcircuit) -> dict[str, set[str]]:
    """Capture one tree standalone and read its nets."""
    circuit = Circuit("tree-test", libs)
    tree.capture(circuit)
    return nets_of(circuit)


def test_swio_tree_topology(kicad_libs: KiCadLibraries) -> None:
    """§5: bit weight = node address, one select bit per tree level."""
    nets = tree_nets(kicad_libs, SwioTree())
    # Root switch takes A2, mid pair A1, leaf quad A0 (pin 6 = S).
    assert "SW1.6" in nets["swio_a2"]
    assert {"SW2.6", "SW3.6"} <= nets["swio_a1"]
    assert {"SW4.6", "SW5.6", "SW6.6", "SW7.6"} <= nets["swio_a0"]
    # Address bit 0 at a level routes through B1 (pin 3): leaf 0 is
    # B1 of SW4, whose A hangs off B1 of SW2, whose A hangs off B1 of
    # the root — address 000.
    assert nets["root"] >= {"SW1.4"}
    assert nets["mid0"] == {"SW1.3", "SW2.4"}
    assert nets["mid1"] == {"SW1.1", "SW3.4"}
    assert nets["low0"] == {"SW2.3", "SW4.4"}
    assert nets["low3"] == {"SW3.1", "SW7.4"}
    for leaf in range(8):
        sw = f"SW{4 + leaf // 2}"
        throw = "3" if leaf % 2 == 0 else "1"
        assert nets[f"leaf{leaf}"] == {f"{sw}.{throw}", f"RU{leaf}.1"}


def test_swio_tree_pullups(kicad_libs: KiCadLibraries) -> None:
    """§5: per-leaf 10 kΩ to the leaf's 3V3N rail port; 4.7 kΩ at the root."""
    nets = tree_nets(kicad_libs, SwioTree())
    for leaf in range(8):
        assert nets[f"rail{leaf}"] == {f"RU{leaf}.2"}
    assert nets["root"] >= {"RUR.1"}
    assert nets["3V3"] >= {"RUR.2"}
    # Switch VCCs on the always rail.
    assert {f"SW{i}.5" for i in range(1, 8)} <= nets["3V3"]


def test_debug_tree_is_bare(kicad_libs: KiCadLibraries) -> None:
    """§5: the debug-return tree carries no pull-ups."""
    nets = tree_nets(kicad_libs, DebugTree())
    assert nets["leaf0"] == {"SW4.3"}
    assert nets["root"] == {"SW1.4"}
    assert not any(name.startswith("rail") for name in nets)
    assert {f"SW{i}.6" for i in (1,)} <= nets["swio_a2"]
