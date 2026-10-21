"""The oparroy parts table: the assembler-inventory view (DESIGN.md §6).

One record per part the captures and benches use, seeded from the
pcba-research inventory snapshot (docs/pcba-research.md) and the
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
    Residuals,
    Resistor,
    SpiceModel,
    Stock,
    Tier,
    ValueBin,
)
from oparroy.stock import DEFAULT_CACHE_PATH, SqliteFeedCache

#: The pcba-research inventory snapshot date
#: (docs/pcba-research.md).
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
            bin=ValueBin(kind="resistor", series=24, tolerance=0.01, lo=1.0, hi=1e6),
            note=(
                "generic 0603 Basic bin; per-value LCSC resolves at "
                "quote time; the bin stocks the E24 1% grid, 1 Ω..1 MΩ"
            ),
        ),
        PartRecord(
            name="c-0603",
            kind="capacitor",
            symbol="Device:C",
            footprint="Capacitor_SMD:C_0603_1608Metric",
            tier=Tier.BASIC,
            area_mm2=1.28,
            bin=ValueBin(
                kind="capacitor", series=12, tolerance=0.10, lo=1e-12, hi=1e-6
            ),
            note=(
                "generic 0603 Basic bin; per-value LCSC resolves at "
                "quote time; the bin stocks the E12 grid, 1 pF..1 µF"
            ),
        ),
        PartRecord(
            name="bat54s",
            kind="diode",
            lcsc="C369929",
            symbol="Diode:BAT54S",
            footprint="Package_TO_SOT_SMD:SOT-23",
            value="BAT54S",
            tier=Tier.EXTENDED,
            stock=Stock(
                1_181,
                date(2026, 10, 4),
                "jlcpcb.com product page, human-verified",
            ),
            area_mm2=3.77,
            datasheet="datasheets/BAT54S",
            note=(
                "KEXIN C369929, $0.0158 @1 — verified on jlcpcb.com, "
                "replacing the never-queried TWGMC C727126 "
                "listing; same industry-standard series pair (30 V, "
                "200 mA, SOT-23) — datasheets/BAT54S/notes/facts.md "
                "names which rating comes from which vendor. Extended "
                "tier — the ~$3/line fee (§6) "
                "applies; a Basic-tier BAT54S was not found but also "
                "not hunted. Spice model is inline in "
                "circuits/watchdog-chargepump/ until the DSL bench "
                "port retires the hand-written netlists"
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
                "terminal-protection TVS: VRWM 3.3 V, "
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
            residuals=Residuals(
                on_resistance_ohm=25.0,
                on_capacitance_pf=17.3,
                off_capacitance_pf=5.2,
                leakage_ua=1.0,
            ),
            partial_power_down=False,
            note=(
                "Residuals (SCES424O §5.5): Ron ≤ 25 Ω over the full "
                "signal range (7 Ω typ / 9 Ω max at 3 V, 25 °C); "
                "Cio(on) 17.3 pF, Cio(off) 5.2 pF — typ at VCC = 5 V, "
                "25 °C, no max specified; leakage ±1 µA max. "
                "No partial-power-down (Ioff) spec — behavior at "
                "VCC = 0 with live signal pins is unspecified "
                "(datasheets/SN74LVC1G3157/notes/facts.md)."
            ),
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
            residuals=Residuals(
                on_resistance_ohm=25.0,
                on_capacitance_pf=17.3,
                off_capacitance_pf=5.2,
                leakage_ua=1.0,
            ),
            note=(
                "UMW clone of the TI part ($0.047 vs $0.072, facts.md); "
                "residuals as the TI part (SCES424O §5.5 — capacitances "
                "are typ, no max specified)."
            ),
        ),
        PartRecord(
            name="ch32v003f4p6",
            kind="mcu",
            lcsc="C5187096",
            tier=Tier.EXTENDED,
            stock=Stock(
                9_000,
                _SNAPSHOT,
                "docs/pcba-research.md; unverified at jlcpcb.com",
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
            name="rp2040",
            kind="mcu",
            lcsc="C2040",
            tier=Tier.EXTENDED,
            stock=Stock(
                48_357,
                date(2026, 10, 16),
                "LCSC product page, fetched live 2026-10-16",
            ),
            symbol="MCU_RaspberryPi:RP2040",
            footprint="Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm",
            value="RP2040",
            area_mm2=49.0,
            datasheet="datasheets/RP2040",
            note=(
                "Raspberry Pi RP2040, $0.9975 @1 — the §5/§6 supervisor "
                "MCU: PIO is the re-timing PHY engine and "
                "golden-reference transceiver, plus the CI board's ring "
                "supervisor. Unavoidably QFN-56, so JLCPCB's per-board "
                "X-ray fee is budgeted (§5)"
            ),
        ),
        PartRecord(
            name="flash-w25q16jvssiq",
            kind="flash-memory",
            lcsc="C131025",
            tier=Tier.EXTENDED,
            stock=Stock(
                3_576,
                date(2026, 10, 16),
                "LCSC product page, fetched live 2026-10-16; Extended "
                "tier confirmed on the jlcpcb.com part page",
            ),
            symbol="Memory_Flash:W25Q16JVSS",
            footprint="Package_SO:SOIC-8_5.3x5.3mm_P1.27mm",
            value="W25Q16JVSSIQ",
            area_mm2=27.6,
            datasheet="datasheets/W25Q16JV",
            note=(
                "Winbond W25Q16JVSSIQ, $1.2688 @1 — 16 Mbit (2 MB) QSPI "
                "boot flash for the supervisor: any 25-series part with "
                "03h/24-bit read boots the RP2040 (AN §2.6), and the IQ "
                "variant's QE bit ships set so /WP and /HOLD are plain "
                "IO2/IO3 (datasheets/W25Q16JV/notes/facts.md). Its /CS "
                "must track VCC at power-up (W25Q16JV DS §4.1), so the "
                "capture fits the 10 kΩ QSPI_SS pull-up the AN marks "
                "DNF for its W25Q128JVS (datasheets/RP2040/notes/"
                "quirks.md)"
            ),
        ),
        PartRecord(
            name="crystal-abm8-272-t3",
            kind="crystal",
            lcsc="C20625731",
            tier=Tier.EXTENDED,
            stock=Stock(
                5_909,
                date(2026, 10, 16),
                "LCSC product page, fetched live 2026-10-16; Extended "
                "tier confirmed on the jlcpcb.com part page",
            ),
            symbol="Device:Crystal_GND24",
            footprint="Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
            value="ABM8-272-T3",
            area_mm2=8.0,
            note=(
                "Abracon ABM8-272-T3, $0.6255 @1 — the AN §2.3 "
                "recommended 12 MHz crystal (±30 ppm, ESR ≤ 50 Ω, CL "
                "10 pF), the Pico's own part; the 15 pF load caps and "
                "the 1 kΩ XOUT series resistor are tuned to it at 3.3 V "
                "IOVDD (datasheets/RP2040/notes/flash-crystal.md)"
            ),
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
                "$0.069 @100 — the §3 segment connector; "
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
            footprint="Oparroy:LED_1206_3216Metric_ReverseMount_Hole1.5x2.4mm",
            tier=Tier.EXTENDED,
            stock=Stock(601_050, date(2026, 9, 29), "LCSC product-page JSON"),
            value="XL-3216SURC-FB",
            area_mm2=5.12,
            note=(
                "XINGLIGHT reverse-mount 1206, red 620 nm / 120 mcd — the "
                "§4.1 power LED; emits through a routed PCB hole to the "
                "connector side"
            ),
        ),
        PartRecord(
            name="led-rev1206-yellowgreen",
            kind="led",
            lcsc="C3646940",
            symbol="Device:LED",
            footprint="Oparroy:LED_1206_3216Metric_ReverseMount_Hole1.5x2.4mm",
            tier=Tier.EXTENDED,
            stock=Stock(6_950, date(2026, 9, 29), "LCSC product-page JSON"),
            value="XL-3216SYGC-FB",
            area_mm2=5.12,
            note=(
                "XINGLIGHT reverse-mount 1206, yellow-green 570 nm / 120 "
                "mcd — the §4.1 per-connector link LEDs, one antiparallel "
                "pair on a single GPIO; the series' only "
                "3.3 V-drivable green — the 525 nm true green of the "
                "same series (C3646937) has Vf 3.4 V"
            ),
        ),
        PartRecord(
            name="led-rev1206-yellow",
            kind="led",
            lcsc="C3646939",
            symbol="Device:LED",
            footprint="Oparroy:LED_1206_3216Metric_ReverseMount_Hole1.5x2.4mm",
            tier=Tier.EXTENDED,
            stock=Stock(19_450, date(2026, 9, 29), "LCSC product-page JSON"),
            value="XL-3216UYC-FB",
            area_mm2=5.12,
            note=(
                "XINGLIGHT reverse-mount 1206, yellow 588 nm / 180 mcd — "
                "the §4.1 working LED (color shuffle: red = "
                "power, yellow = working, green = link stay "
                "distinguishable)"
            ),
        ),
        PartRecord(
            name="led-1206-red",
            kind="led",
            lcsc="C965822",
            symbol="Device:LED",
            footprint="LED_SMD:LED_1206_3216Metric",
            tier=Tier.EXTENDED,
            stock=Stock(
                376_161,
                date(2026, 10, 18),
                "kicad-jlcpcb-tools feed snapshot 2026-10-18",
            ),
            value="XL-3216SURC",
            area_mm2=5.12,
            datasheet="datasheets/XL-3216",
            note=(
                "XINGLIGHT top-emitting 1206, red 615-630 nm / 80-240 mcd "
                "@ 20 mA — the CI tiles' §4.1 power LED. The forward-mount "
                "sibling of the node board's XL-3216SURC-FB: the CI board's "
                "viewer stands over the component side, so no light-pipe "
                "holes; Vf 1.9-2.2 V @ 20 mA "
                "(datasheets/XL-3216/notes/facts.md)"
            ),
        ),
        PartRecord(
            name="led-1206-yellowgreen",
            kind="led",
            lcsc="C965826",
            symbol="Device:LED",
            footprint="LED_SMD:LED_1206_3216Metric",
            tier=Tier.EXTENDED,
            stock=Stock(
                50_981,
                date(2026, 10, 18),
                "kicad-jlcpcb-tools feed snapshot 2026-10-18",
            ),
            value="XL-3216SYGC",
            area_mm2=5.12,
            datasheet="datasheets/XL-3216",
            note=(
                "XINGLIGHT top-emitting 1206, yellow-green 565-575 nm / "
                "50-100 mcd @ 20 mA — the CI tiles' §4.1 link pair, one "
                "antiparallel pair on a single GPIO; Vf 1.9-2.4 V @ 20 mA, "
                "again the series' only 3.3 V-drivable green "
                "(datasheets/XL-3216/notes/facts.md)"
            ),
        ),
        PartRecord(
            name="led-1206-yellow",
            kind="led",
            lcsc="C965824",
            symbol="Device:LED",
            footprint="LED_SMD:LED_1206_3216Metric",
            tier=Tier.EXTENDED,
            stock=Stock(
                69_207,
                date(2026, 10, 18),
                "kicad-jlcpcb-tools feed snapshot 2026-10-18",
            ),
            value="XL-3216UYC",
            area_mm2=5.12,
            datasheet="datasheets/XL-3216",
            note=(
                "XINGLIGHT top-emitting 1206, yellow 585-595 nm / 80-240 "
                "mcd @ 20 mA — the CI tiles' §4.1 working LED (the "
                "red/yellow/green role coding matches the node board); "
                "Vf 1.8-2.4 V @ 20 mA (datasheets/XL-3216/notes/facts.md)"
            ),
        ),
        PartRecord(
            name="usb-c-receptacle-16p",
            kind="connector",
            lcsc="C2894897",
            symbol="Connector:USB_C_Receptacle_USB2.0_16P",
            footprint="Connector_USB:USB_C_Receptacle_HCTL_HC-TYPE-C-16P-01A",
            value="HC-TYPE-C-16P-01A",
            tier=Tier.EXTENDED,
            stock=Stock(
                38_895,
                date(2026, 10, 15),
                "LCSC product-page JSON, fetched live 2026-10-15",
            ),
            area_mm2=65.7,
            datasheet="datasheets/HC-TYPE-C-16P-01A",
            note=(
                "HCTL HC-TYPE-C-16P-01A, $0.0848 @5 — the §6 CI-board "
                "power inlet and host link: USB 2.0-only 16P receptacle "
                "(5 A VBUS, 20 V max; the drawing's pin table matches "
                "the KiCad symbol/footprint pair pad for pad — "
                "datasheets/HC-TYPE-C-16P-01A/notes/facts.md). "
                "Extended tier — no Basic USB-C receptacle exists. "
                "Rejected: Korean Hroparts TYPE-C-31-M-12 (C165948 — "
                "362,485 in stock but $0.1879 @5, 2.2x the price; its "
                "KiCad-lib footprint USB_C_Receptacle_HRO_TYPE-C-31-M-12 "
                "makes it a drop-in fallback if the HCTL runs out), "
                "SHOU HAN TYPE-C 16PIN 2MD(073) (C2765186 — $0.0753 "
                "@20 and 931,560 in stock, but no KiCad-lib footprint: "
                "a project footprint plus decal verification for "
                "~$0.01 saved is not worth it)"
            ),
        ),
        PartRecord(
            name="ldo-ams1117-3v3",
            kind="voltage-regulator",
            lcsc="C6186",
            symbol="Regulator_Linear:AMS1117-3.3",
            footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
            value="AMS1117-3.3",
            tier=Tier.BASIC,
            stock=Stock(
                668_750,
                date(2026, 10, 15),
                "LCSC product-page JSON, fetched live 2026-10-15; LCSC "
                "does not expose the JLCPCB tier — human-verify Basic "
                "at jlcpcb.com",
            ),
            area_mm2=22.75,
            datasheet="datasheets/AMS1117",
            note=(
                "Advanced Monolithic Systems AMS1117-3.3, $0.2103 @5 — "
                "the §6 5 V → 3.3 V rail LDO: 1 A, dropout 1.1 V typ / "
                "1.3 V max @0.8 A, ±3 % output over temp, SOT-223 tab "
                "is VOUT (datasheets/AMS1117/notes/facts.md). "
                "Stability spec calls for a 22 µF tantalum output cap; "
                "the capture fits 0603 ceramics instead — the mismatch "
                "and its bench-verify obligation live in "
                "datasheets/AMS1117/notes/quirks.md"
            ),
        ),
        PartRecord(
            name="74hc595-nexperia",
            kind="shift-register",
            lcsc="C5947",
            symbol="74xx:74HC595",
            footprint="Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
            value="74HC595",
            tier=Tier.BASIC,
            stock=Stock(
                218_335,
                date(2026, 10, 16),
                "LCSC product page, fetched live 2026-10-16; Basic tier "
                "confirmed on the jlcpcb.com part page",
            ),
            area_mm2=38.61,
            datasheet="datasheets/SN74HC595",
            note=(
                "Nexperia 74HC595D,118, $0.1124 @5 — the scan-plane "
                "control register, 10 per CI board (docs/scan-plane.md "
                "§1); the pick is settled in scan-plane.md §7: the sole "
                "Basic-tier 74HC595 listing in any package. Pin mapping "
                "per SCLS041J §3, cross-checked against the KiCad "
                "74xx:74HC595 symbol (datasheets/SN74HC595/notes/"
                "facts.md). No silicon POR state — the constructed-zero "
                "discipline is scan-plane.md §4"
            ),
        ),
        PartRecord(
            name="74hc165-nexperia",
            kind="shift-register",
            lcsc="C5613",
            symbol="74xx:74HC165",
            footprint="Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
            value="74HC165",
            tier=Tier.EXTENDED,
            stock=Stock(
                207_160,
                date(2026, 10, 16),
                "LCSC product page, fetched live 2026-10-16; Extended "
                "tier confirmed on the jlcpcb.com part page",
            ),
            area_mm2=38.61,
            datasheet="datasheets/SN74HC165",
            note=(
                "Nexperia 74HC165D,653, $0.1113 @5 — the scan-plane "
                "observe register, 2 per CI board (docs/scan-plane.md "
                "§1); the pick is settled in scan-plane.md §7: no "
                "Basic-tier 74HC165 exists in any package, so the board "
                "pays one Extended-line fee for its two observe stages. "
                "KiCad symbol pins D0-D7 are the datasheet's parallel "
                "inputs A-H (D0 = A = bit 0, scan-plane.md §3; "
                "datasheets/SN74HC165/notes/facts.md)"
            ),
        ),
        PartRecord(
            name="ao3401a",
            kind="p-mosfet",
            lcsc="C15127",
            symbol="Transistor_FET:AO3401A",
            footprint="Package_TO_SOT_SMD:SOT-23",
            value="AO3401A",
            tier=Tier.BASIC,
            stock=Stock(
                231_435,
                date(2026, 10, 16),
                "LCSC product page, fetched live 2026-10-16; Basic tier "
                "confirmed on the jlcpcb.com part page",
            ),
            area_mm2=3.77,
            datasheet="datasheets/AO3401A",
            residuals=Residuals(on_resistance_ohm=0.085),
            note=(
                "AOS AO3401A, $0.1030 @5 — the per-tile power-cut "
                "high-side switch (instrumented-ci.md §3, transform F8): "
                "-30 V / -4 A, RDS(on) ≤ 85 mΩ @ VGS = -2.5 V "
                "(datasheets/AO3401A/notes/facts.md). SOT-23 pin order "
                "1 = G, 2 = S, 3 = D, matching the KiCad "
                "Transistor_FET:AO3401A symbol"
            ),
        ),
        PartRecord(
            name="2n7002",
            kind="n-mosfet",
            lcsc="C8545",
            symbol="Transistor_FET:2N7002",
            footprint="Package_TO_SOT_SMD:SOT-23",
            value="2N7002",
            tier=Tier.BASIC,
            stock=Stock(
                2_030_150,
                date(2026, 10, 16),
                "LCSC product page, fetched live 2026-10-16; Basic tier "
                "confirmed on the jlcpcb.com part page",
            ),
            area_mm2=3.77,
            datasheet="datasheets/2N7002",
            residuals=Residuals(
                on_resistance_ohm=5.0, off_capacitance_pf=25.0, leakage_ua=0.08
            ),
            note=(
                "JSCJ 2N7002, $0.0176 @50 — the button-override N-FET "
                "paralleled across the input tiles' tactile buttons "
                "(instrumented-ci.md §6, transforms H2/H3): 60 V / "
                "115 mA, RDS(on) ≤ 5 Ω @ VGS = 10 V against the 10 kΩ "
                "pull-up — millivolt levels (residual R8, "
                "instrumented-ci.md §9). SOT-23 pin order 1 = G, 2 = S, "
                "3 = D printed on the JSCJ datasheet "
                "(datasheets/2N7002/notes/facts.md)"
            ),
        ),
        PartRecord(
            name="pot-10k-rk09k",
            kind="potentiometer",
            lcsc="C209770",
            symbol="Device:R_Potentiometer",
            footprint="Potentiometer_THT:Potentiometer_Alps_RK09K_Single_Vertical",
            value="10k",
            tier=Tier.NONE,
            stock=Stock(
                2_143,
                date(2026, 10, 16),
                "LCSC product page, fetched live 2026-10-16; JLCPCB "
                "lists it manual-weld only — hand-soldered post-PCBA "
                "with the back-side connectors (conn-idc-02x05 "
                "precedent)",
            ),
            area_mm2=112.4,
            datasheet="datasheets/RK09K",
            note=(
                "ALPS RK09K1130A6S, $0.5967 @1 — the input tiles' demo "
                "knob (instrumented-ci.md §6, transform H1): 10 kΩ, "
                "taper 1B (linear), 9 mm snap-in vertical THT, pin 2 = "
                "wiper (datasheets/RK09K/notes/facts.md), matching the "
                "KiCad footprint's middle pad and Device:R_Potentiometer's "
                "wiper pin. Rejected: SMD trimmers (JIERR JER33X-1-14 "
                "C48997896, 79.6k stock, $0.10 — screwdriver-adjust, no "
                "demo knob, and Extended tier anyway), ALPS horizontal "
                "RK09 variants (≤ 2.4k stock). A rotary knob is the "
                "demo-facing part; no assembler-placed rotary pot "
                "exists at JLCPCB"
            ),
        ),
        PartRecord(
            name="btn-tact-ts1187a",
            kind="switch",
            lcsc="C318884",
            symbol="Switch:SW_Push",
            footprint="Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A",
            value="TS-1187A-B-A-B",
            tier=Tier.BASIC,
            stock=Stock(
                40_860,
                date(2026, 10, 16),
                "LCSC product page, fetched live 2026-10-16; Basic tier "
                "confirmed on the jlcpcb.com part page",
            ),
            area_mm2=26.0,
            datasheet="datasheets/TS-1187A",
            note=(
                "XKB TS-1187A-B-A-B, $0.0207 @20 — the input tiles' "
                "tactile buttons (instrumented-ci.md §6): SMD-4P "
                "5.1x5.1 mm, 160 gf, 100k cycles, 50 mA/12 V contact "
                "(datasheets/TS-1187A/notes/facts.md); four terminals "
                "in two commoned pairs, merged to pads 1/2 on the "
                "KiCad footprint. Basic tier and a stocked KiCad-lib "
                "footprint. Rejected: XUNPU TS-1088-AR02016 (C720477 — "
                "Basic, 408k stock, but 4x3 mm is finger-hostile at "
                "demo scale and 2.5x the price), 6x6 mm gull-wing "
                "clones (C2837531 — Extended tier)"
            ),
        ),
        PartRecord(
            name="buzzer-pklcs1212e",
            kind="buzzer",
            lcsc="C113159",
            symbol="Device:Buzzer",
            footprint="Buzzer_Beeper:Buzzer_Murata_PKLCS1212E",
            value="PKLCS1212E4001-R1",
            tier=Tier.EXTENDED,
            stock=Stock(
                7_671,
                date(2026, 10, 16),
                "LCSC product page, fetched live 2026-10-16; Extended "
                "tier confirmed on the jlcpcb.com part page",
            ),
            area_mm2=144.0,
            datasheet="datasheets/PKLCS1212E",
            note=(
                "Murata PKLCS1212E4001-R1, $0.8028 @1 — the output "
                "tiles' passive piezo buzzer (instrumented-ci.md §6, "
                "PC4 → 470 Ω → piezo → GND): 4 kHz, 75 dB min at the "
                "spec's own ±1.5 Vo-p measuring condition, which the "
                "3.3 V GPIO drive exceeds; max input ±12.5 Vo-p "
                "(datasheets/PKLCS1212E/notes/facts.md). Extended tier "
                "— every buzzer on JLCPCB's parts list is Extended. "
                "Rejected: XHXDZ SMD9018 (C49246958 — 3 V/65 dB and "
                "half the price, but no KiCad-lib footprint and a "
                "spec-thin datasheet), TDK PS1240P02BT (C76871 — THT, "
                "breaks single-side SMT), magnetic MLT-class passives "
                "(16 Ω coils — wrong drive impedance against the §6 "
                "470 Ω series R; the design wants piezo)"
            ),
        ),
        PartRecord(
            name="csa-ina241a5",
            kind="current-sense-amp",
            lcsc="C7425524",
            symbol="Amplifier_Current:INA241A5xDDF",
            footprint="Package_TO_SOT_SMD:SOT-23-8",
            value="INA241A5",
            tier=Tier.EXTENDED,
            stock=Stock(
                3_809,
                date(2026, 10, 17),
                "kicad-jlcpcb-tools feed snapshot 2026-10-17; $3.0244 @1 "
                "from the LCSC product page",
            ),
            area_mm2=8.12,
            datasheet="datasheets/INA241",
            note=(
                "TI INA241A5IDDFR — the measurement tile's high-side "
                "shunt amp (instrumented-ci.md §12): gain 200 V/V, "
                "1.1 MHz small-signal BW at all gains (typ-only), "
                "A-grade offset ±8 µV max, supply 2.7..20 V from the "
                "always-on 3V3, CM range -5..110 V, bidirectional REF "
                "pins (datasheets/INA241/notes/facts.md). Extended tier "
                "— JLCPCB's Basic list carries no current-sense amp "
                "above ~100 kHz (the stocked clones are 48-80 kHz "
                "zero-drift parts). Rejected: INA293 (BW falls to "
                "900 kHz at A4/A5 and no REF pin — unidirectional "
                "only), TSC2011 (750 kHz, ±200 µV offset), "
                "INA180/INA181/INA240 (≤400 kHz)"
            ),
        ),
        PartRecord(
            name="adc-adcs7476",
            kind="adc",
            lcsc="C91530",
            symbol="Analog_ADC:ADS7886xxDBV",
            footprint="Package_TO_SOT_SMD:SOT-23-6",
            value="ADCS7476",
            tier=Tier.EXTENDED,
            stock=Stock(
                1_680,
                date(2026, 10, 17),
                "kicad-jlcpcb-tools feed snapshot 2026-10-17; ~$0.90 @1 "
                "from the LCSC product page",
            ),
            area_mm2=4.64,
            datasheet="datasheets/ADCS7476",
            note=(
                "TI ADCS7476AIMFX/NOPB — the measurement tile's SPI ADC "
                "(instrumented-ci.md §12): 12-bit, 1 MSPS at 20 MHz "
                "SCLK, VDD-as-reference (0..3.3 V input on the 3V3 "
                "rail), 16-SCLK frames of 4 leading zeros + 12 bits "
                "(sample rising edge, SPI mode 0), streams conversions "
                "with no config writes — the RP2040 PIO burst-capture "
                "target (datasheets/ADCS7476/notes/facts.md). Extended "
                "tier — JLCPCB's Basic list carries no ADCs at all. "
                "The KiCad symbol is the pin-identical ADS7886xxDBV "
                "(facts.md pin-compat verdict). Second source on the "
                "same footprint: SiChange XCS7476E (C41383380, 4,301 in "
                "the same feed snapshot). Rejected: ADS7886SBDBVT (8 "
                "in stock), ADS7042 (X2QFN package), MCP33131-10 "
                "(needs an external reference), AD7476ARTZ (5x the "
                "price, thin stock)"
            ),
        ),
    ]
)

#: The project's 0603 bins, bound from the table (DESIGN.md §7).
R0603 = PARTS.bind("r-0603", Resistor, class_name="R0603")
C0603 = PARTS.bind("c-0603", Capacitor, class_name="C0603")


def main() -> None:
    """Print the stock-freshness report.

    When the local feed overlay cache exists
    (``~/.cache/oparroy/stock-cache.sqlite``, written by ``python -m
    oparroy.stock fetch``), the audit runs against it; otherwise it
    falls back to the age budget alone.
    """
    cache = (
        SqliteFeedCache(DEFAULT_CACHE_PATH) if DEFAULT_CACHE_PATH.is_file() else None
    )
    if cache is None:
        sys.stderr.write(
            f"note: no feed cache at {DEFAULT_CACHE_PATH} — age-based audit only "
            "(python -m oparroy.stock fetch builds it)\n"
        )
    issues = PARTS.check_stock(cache=cache)
    for issue in issues:
        sys.stderr.write(f"{issue}\n")
    if not issues:
        sys.stdout.write("all stock snapshots fresh\n")


if __name__ == "__main__":
    main()
