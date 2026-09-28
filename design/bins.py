"""The project's shared footprint bins (DESIGN.md §7).

Footprints default per part class, overridable per instance: a bin is a
typed-part subclass carrying the class-default footprint, so captures
wire parts, not packages. 0603 is the project default for passives —
hand-reworkable, stocked by every assembler (§6 inventory-driven
selection). ``R0603``/``C0603`` are bound from the parts DB's records
(T7c); the LED and TVS bins stay local until the DB grows records for
them.
"""

from design.parts_db import C0603, R0603
from oparroy.dsl import Led, TvsDiode

__all__ = ["C0603", "R0603", "Led0603", "TvsSod323"]


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
