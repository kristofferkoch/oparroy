"""The project's shared footprint bins (DESIGN.md §7).

Footprints default per part class, overridable per instance: a bin is a
typed-part subclass carrying the class-default footprint, so captures
wire parts, not packages. 0603 is the project default for passives —
hand-reworkable, stocked by every assembler (§6 inventory-driven
selection). ``R0603``/``C0603`` are bound from the parts DB's records
(T7c); the LED bin references its DB records but stays local (one bin,
three colors); the TVS bin stays local until the DB grows a record.
"""

from design.parts_db import C0603, R0603
from oparroy.dsl import Led, TvsDiode

__all__ = ["C0603", "R0603", "LedRev1206", "TvsSod323"]


class LedRev1206(Led):
    """The status-LED bin: 1206 reverse-mount, emitting through a PCB hole.

    The LED pads stay on the front — the single-sided assembly face —
    while the lens emits through a routed board hole to the connector
    side (2026-09-29, DESIGN.md §4.1). The per-color XINGLIGHT
    XL-3216-FB records live in the parts DB.
    """

    default_footprint = "LED_SMD:LED_1206_3216Metric_ReverseMount_Hole1.8x2.4mm"


class TvsSod323(TvsDiode):
    """The project's SOD-323 ESD-diode bin (§7 terminal protection).

    Value is provisional — a low-capacitance bidirectional 3.3 V part
    (PESD3V3L1BA class); per-part selection against assembler inventory
    is the parts DB's job (T7c, §6).
    """

    default_value = "PESD3V3L1BA"
    default_footprint = "Diode_SMD:D_SOD-323"
