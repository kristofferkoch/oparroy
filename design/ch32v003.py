"""The node MCU as a typed part: CH32V003F4P6, TSSOP-20 (DESIGN.md §5).

Pin numbers follow the F4P6 pin map in
``datasheets/CH32V003/notes/gpio-pinout.md`` (DS0 §2.1); the KiCad
symbol is ``MCU_WCH_RiscV:CH32V003FxPx``. Pins are keyword-only by port
name (``pa2=``, ``pd7=``, …) — the type checker covers declaration and
connection alike, and a pin swap is a diff, not a hidden number.

Only the power pins are required: a many-pinned part placed with unused
pins wires what it uses and lets the checker's unconnected-pin warnings
report the rest by name (§7 typed parts). Which peripheral each pin
serves in the node capture — OPA inputs, TIM1 TX channels, brake — is
``design/node.py``'s wiring decision, not this declaration's.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from oparroy.dsl import TypedPart

if TYPE_CHECKING:
    from oparroy.dsl import Net


class Ch32v003f4p6(TypedPart):
    """CH32V003F4P6 (TSSOP-20): pins by port name, power pins required."""

    symbol = "MCU_WCH_RiscV:CH32V003FxPx"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "pd4": "1",
        "pd5": "2",
        "pd6": "3",
        "pd7": "4",
        "pa1": "5",
        "pa2": "6",
        "vss": "7",
        "pd0": "8",
        "vdd": "9",
        "pc0": "10",
        "pc1": "11",
        "pc2": "12",
        "pc3": "13",
        "pc4": "14",
        "pc5": "15",
        "pc6": "16",
        "pc7": "17",
        "pd1": "18",
        "pd2": "19",
        "pd3": "20",
    }
    required_pins: ClassVar[frozenset[str] | None] = frozenset({"vdd", "vss"})
    default_value = "CH32V003F4P6"
    default_footprint = "Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm"

    def __init__(  # noqa: PLR0913 — one keyword per physical pin
        self,
        *,
        vdd: Net | str,
        vss: Net | str,
        pa1: Net | str | None = None,
        pa2: Net | str | None = None,
        pc0: Net | str | None = None,
        pc1: Net | str | None = None,
        pc2: Net | str | None = None,
        pc3: Net | str | None = None,
        pc4: Net | str | None = None,
        pc5: Net | str | None = None,
        pc6: Net | str | None = None,
        pc7: Net | str | None = None,
        pd0: Net | str | None = None,
        pd1: Net | str | None = None,
        pd2: Net | str | None = None,
        pd3: Net | str | None = None,
        pd4: Net | str | None = None,
        pd5: Net | str | None = None,
        pd6: Net | str | None = None,
        pd7: Net | str | None = None,
        value: str | None = None,
        footprint: str | None = None,
    ) -> None:
        named = {
            "pa1": pa1,
            "pa2": pa2,
            "pc0": pc0,
            "pc1": pc1,
            "pc2": pc2,
            "pc3": pc3,
            "pc4": pc4,
            "pc5": pc5,
            "pc6": pc6,
            "pc7": pc7,
            "pd0": pd0,
            "pd1": pd1,
            "pd2": pd2,
            "pd3": pd3,
            "pd4": pd4,
            "pd5": pd5,
            "pd6": pd6,
            "pd7": pd7,
        }
        nets = {pin: net for pin, net in named.items() if net is not None}
        super().__init__(value, footprint, {"vdd": vdd, "vss": vss} | nets)
