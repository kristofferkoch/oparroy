"""The project's shared footprint bins (DESIGN.md §7).

Footprints default per part class, overridable per instance: a bin is a
typed-part subclass carrying the class-default footprint, so captures
wire parts, not packages. 0603 is the project default for passives —
hand-reworkable, stocked by every assembler (§6 inventory-driven
selection). ``R0603``/``C0603`` are bound from the parts DB's records
(T7c); the LED and TVS bins reference their DB records but stay local
(the LED bin spans three colors; the TVS bin is a single picked part).
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

    default_footprint = "Oparroy:LED_1206_3216Metric_ReverseMount_Hole1.5x2.4mm"


class TvsSod323(TvsDiode):
    """The project's SOD-323 ESD-diode bin (§7 terminal protection).

    The picked part lives in the parts DB's ``tvs-sod323`` record
    (Brightking UDD32C03L01, 2026-09-30): VRWM 3.3 V, Cj 0.8 pF typ —
    RC ≈ 0.4 ns against the 470 Ω series R, far inside the §2 decode
    margin.
    """

    default_value = "UDD32C03L01"
    default_footprint = "Diode_SMD:D_SOD-323"
