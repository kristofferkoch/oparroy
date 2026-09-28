"""The project's shared footprint bins (DESIGN.md §7).

Footprints default per part class, overridable per instance: a bin is a
typed-part subclass carrying the class-default footprint, so captures
wire parts, not packages. 0603 is the project default for passives —
hand-reworkable, stocked by every assembler (§6 inventory-driven
selection; the parts DB, T7c, takes over per-part resolution later).
"""

from oparroy.dsl import Capacitor, Led, Resistor, TvsDiode


class R0603(Resistor):
    """The project's 0603 resistor bin: class-default footprint (§7)."""

    default_footprint = "Resistor_SMD:R_0603_1608Metric"


class C0603(Capacitor):
    """The project's 0603 capacitor bin: class-default footprint (§7)."""

    default_footprint = "Capacitor_SMD:C_0603_1608Metric"


class Led0603(Led):
    """The project's 0603 LED bin: class-default footprint (§7)."""

    default_footprint = "LED_SMD:LED_0603_1608Metric"


class TvsSod323(TvsDiode):
    """The project's SOD-323 ESD-diode bin (§7 terminal protection).

    Value is provisional — a low-capacitance bidirectional 3.3 V part
    (PESD3V3L1BA class); per-part selection against assembler inventory
    is the parts DB's job (T7c, §6).
    """

    default_value = "PESD3V3L1BA"
    default_footprint = "Diode_SMD:D_SOD-323"
