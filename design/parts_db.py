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
            name="conn-01x06",
            kind="connector",
            symbol="Connector_Generic:Conn_01x06",
            footprint="Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical",
            tier=Tier.NONE,
            value="Conn_01x06",
            area_mm2=38.7,
            note="provisional §3 connector block; through-hole, hand-soldered",
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
