"""The oparroy parts table: the assembler-inventory view (T7c, DESIGN.md §6).

One record per part the captures and benches use, seeded from the T17
inventory snapshot (docs/pcba-research-2026-09-26.md) and the
datasheet notes. Every stock number is a *snapshot*: it carries its
as-of date and source, and nothing here is live data — re-query
JLCPCB before ordering. ``check_stock`` flags what has gone stale or
was never queried. Footprint areas are nominal body rectangles, the
currency of the area-bound filter knobs.

Shared part bins are bound here (``R0603``/``C0603``) so captures draw
them from the table; part-specific bindings happen at the capture
site (``design/watchdog_chargepump.py`` binds its BAT54S).

    python -m design.parts_db    # the stock-freshness report
"""

import sys
from datetime import date

from oparroy.dsl import (
    Capacitor,
    PartRecord,
    PartsDb,
    Resistor,
    SpiceModel,
    Stock,
    Tier,
)

#: The T17 inventory snapshot date (docs/pcba-research-2026-09-26.md).
_SNAPSHOT = date(2026, 9, 26)

PARTS = PartsDb(
    [
        PartRecord(
            name="r-0603",
            kind="resistor",
            symbol="Device:R",
            footprint="Resistor_SMD:R_0603_1608Metric",
            tier=Tier.BASIC,
            area_mm2=1.28,
            note="generic 0603 Basic bin; per-value LCSC resolves at quote time (T23)",
        ),
        PartRecord(
            name="c-0603",
            kind="capacitor",
            symbol="Device:C",
            footprint="Capacitor_SMD:C_0603_1608Metric",
            tier=Tier.BASIC,
            area_mm2=1.28,
            note="generic 0603 Basic bin; per-value LCSC resolves at quote time (T23)",
        ),
        PartRecord(
            name="bat54s",
            kind="diode",
            lcsc="C727126",
            symbol="Diode:BAT54S",
            footprint="Package_TO_SOT_SMD:SOT-23",
            value="BAT54S",
            area_mm2=3.77,
            datasheet="datasheets/BAT54S",
            note=(
                "TWGMC C727126 (datasheets/BAT54S/notes/facts.md); JLCPCB "
                "tier and stock never queried (2026-09-28); spice model is "
                "inline in circuits/watchdog-chargepump/ until T7e"
            ),
        ),
        PartRecord(
            name="tvs-sod323",
            kind="diode",
            lcsc="C78439",
            symbol="Device:D_TVS",
            footprint="Diode_SMD:D_SOD-323",
            tier=Tier.EXTENDED,
            stock=Stock(
                183_717,
                date(2026, 9, 30),
                "jlcsearch mirror 183,717 / LCSC product page 931,760",
            ),
            value="UDD32C03L01",
            area_mm2=2.52,
            note=(
                "Brightking UDD32C03L01, bidirectional SOD-323 — the §7 "
                "terminal-protection TVS (picked 2026-09-30): VRWM 3.3 V, "
                "VBR 4 V min @ 1 mA, VCL 7 V @ 1 A (15 V @ 5 A), Cj "
                "0.8 pF typ — RC ≈ 0.4 ns against the 470 Ω series R, "
                "far inside the §2 decode margin; IR ≤ 5 µA @ 3.3 V; "
                "~$0.037 @1; one BOM line, four positions per node. "
                "Extended tier — no Basic SOD-323 TVS exists (only "
                "1N4148WS-class switching diodes). Rejected: MDD SD03C "
                "(C502532 — the datasheet says 450 pF max vs the "
                "listing's 40 pF claim; 450 pF against 470 Ω is τ ≈ "
                "210 ns, blowing the §2 decode margin), UMW PESD3V3L1BA "
                "(C2687129 — ~100 pF, clamps at 24 V, weakest "
                "electrically), TECH PUBLIC BV03C (C2858699 — ~1 pF but "
                "the datasheet is image-only, unverifiable)"
            ),
        ),
        PartRecord(
            name="sn74lvc1g3157-ti",
            kind="analog-switch",
            lcsc="C10426",
            tier=Tier.EXTENDED,
            stock=Stock(
                51_000,
                _SNAPSHOT,
                "jlcsearch mirror (datasheets/SN74LVC1G3157/notes/facts.md); "
                "unverified at jlcpcb.com",
            ),
            symbol="74xGxx:74LVC1G3157",
            footprint="Package_TO_SOT_SMD:SOT-23-6",
            value="74LVC1G3157",
            area_mm2=4.64,
            spice=SpiceModel("circuits/lib/sn74lvc1g3157.spi", subckt="sn74lvc1g3157"),
            datasheet="datasheets/SN74LVC1G3157",
        ),
        PartRecord(
            name="sn74lvc1g3157-umw",
            kind="analog-switch",
            lcsc="C3040658",
            tier=Tier.EXTENDED,
            stock=Stock(
                124_000,
                _SNAPSHOT,
                "jlcsearch mirror (datasheets/SN74LVC1G3157/notes/facts.md); "
                "unverified at jlcpcb.com",
            ),
            symbol="74xGxx:74LVC1G3157",
            footprint="Package_TO_SOT_SMD:SOT-23-6",
            value="74LVC1G3157",
            area_mm2=4.64,
            spice=SpiceModel("circuits/lib/sn74lvc1g3157.spi", subckt="sn74lvc1g3157"),
            datasheet="datasheets/SN74LVC1G3157",
            note="UMW clone of the TI part ($0.047 vs $0.072, facts.md)",
        ),
        PartRecord(
            name="ch32v003f4p6",
            kind="mcu",
            lcsc="C5187096",
            tier=Tier.EXTENDED,
            stock=Stock(
                9_000,
                _SNAPSHOT,
                "docs/pcba-research-2026-09-26.md; unverified at jlcpcb.com",
            ),
            symbol="MCU_WCH_RiscV:CH32V003FxPx",
            footprint="Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm",
            value="CH32V003F4P6",
            area_mm2=28.6,
            spice=SpiceModel("circuits/lib/ch32v003.spi"),
            datasheet="datasheets/CH32V003",
            note="behavioral models only (opa_cmp, tx_pin); the node MCU (§5)",
        ),
        PartRecord(
            name="conn-idc-02x05",
            kind="connector",
            lcsc="C22385222",
            symbol="Connector_Generic:Conn_02x05_Odd_Even",
            footprint="Connector_IDC:IDC-Header_2x05_P2.54mm_Vertical_SMD",
            tier=Tier.NONE,
            stock=Stock(
                285,
                date(2026, 9, 29),
                "LCSC product-page JSON, fetched live 2026-09-29; "
                "modest stock — buy ahead",
            ),
            value="Conn_02x05_Odd_Even",
            area_mm2=113.0,
            note=(
                "XYECONN IDC2.54-US2S-5A 2x5 2.54 mm SMD box header, "
                "$0.069 @100 — the §3 segment connector (2026-09-29); "
                "backside, hand-soldered post-PCBA (the front is the "
                "single-sided assembly face); no stocked SMD box header "
                "has anchor pegs — the THT C2977596 is the "
                "high-pull-force fallback; the cable-side IDC socket "
                "(C8373) is not a PCBA part"
            ),
        ),
        PartRecord(
            name="led-rev1206-red",
            kind="led",
            lcsc="C3646938",
            symbol="Device:LED",
            footprint="LED_SMD:LED_1206_3216Metric_ReverseMount_Hole1.8x2.4mm",
            tier=Tier.EXTENDED,
            stock=Stock(601_050, date(2026, 9, 29), "LCSC product-page JSON"),
            value="XL-3216SURC-FB",
            area_mm2=5.12,
            note=(
                "XINGLIGHT reverse-mount 1206, red 620 nm / 120 mcd — the "
                "§4.1 power LED; emits through a routed PCB hole to the "
                "connector side (2026-09-29)"
            ),
        ),
        PartRecord(
            name="led-rev1206-yellowgreen",
            kind="led",
            lcsc="C3646940",
            symbol="Device:LED",
            footprint="LED_SMD:LED_1206_3216Metric_ReverseMount_Hole1.8x2.4mm",
            tier=Tier.EXTENDED,
            stock=Stock(6_950, date(2026, 9, 29), "LCSC product-page JSON"),
            value="XL-3216SYGC-FB",
            area_mm2=5.12,
            note=(
                "XINGLIGHT reverse-mount 1206, yellow-green 570 nm / 120 "
                "mcd — the §4.1 per-connector link LEDs, one antiparallel "
                "pair on a single GPIO (2026-09-30); the series' only "
                "3.3 V-drivable green — the 525 nm true green of the "
                "same series (C3646937) has Vf 3.4 V"
            ),
        ),
        PartRecord(
            name="led-rev1206-yellow",
            kind="led",
            lcsc="C3646939",
            symbol="Device:LED",
            footprint="LED_SMD:LED_1206_3216Metric_ReverseMount_Hole1.8x2.4mm",
            tier=Tier.EXTENDED,
            stock=Stock(19_450, date(2026, 9, 29), "LCSC product-page JSON"),
            value="XL-3216UYC-FB",
            area_mm2=5.12,
            note=(
                "XINGLIGHT reverse-mount 1206, yellow 588 nm / 180 mcd — "
                "the §4.1 working LED (2026-09-30 color shuffle: red = "
                "power, yellow = working, green = link stay "
                "distinguishable)"
            ),
        ),
    ]
)

#: The project's 0603 bins, bound from the table (DESIGN.md §7).
R0603 = PARTS.bind("r-0603", Resistor, class_name="R0603")
C0603 = PARTS.bind("c-0603", Capacitor, class_name="C0603")


def main() -> None:
    """Print the stock-freshness report (T7c)."""
    issues = PARTS.check_stock()
    for issue in issues:
        sys.stderr.write(f"{issue}\n")
    if not issues:
        sys.stdout.write("all stock snapshots fresh\n")


if __name__ == "__main__":
    main()
