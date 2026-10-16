"""The supervisor MCU as a typed part: RP2040, QFN-56 (DESIGN.md §5).

Pin numbers follow the QFN-56 pinout in
``datasheets/RP2040/notes/pinout.md`` (RP2040 datasheet); the KiCad
symbol is ``MCU_RaspberryPi:RP2040``. Pins are keyword-only by function
name (``gpio18=``, ``qspi_sclk=``, …) — the type checker covers
declaration and connection alike, and a pin swap is a diff, not a
hidden number. Multi-pad functions (``iovdd``, ``dvdd``, …) own a tuple
of pin numbers, one net per keyword.

Only the power pins are required: a many-pinned part placed with unused
pins wires what it uses and lets the checker's unconnected-pin warnings
report the rest by name (§7 typed parts). Which GPIO serves which
supervisor role — scan chain, SWIO, boundary taps — is
``design/supervisor.py``'s wiring decision, not this declaration's.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from oparroy.dsl import TypedPart

if TYPE_CHECKING:
    from oparroy.dsl import Net


class Rp2040(TypedPart):
    """RP2040 (QFN-56): pins by function name, power pins required."""

    symbol = "MCU_RaspberryPi:RP2040"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "iovdd": ("1", "10", "22", "33", "42", "49"),
        "gpio0": "2",
        "gpio1": "3",
        "gpio2": "4",
        "gpio3": "5",
        "gpio4": "6",
        "gpio5": "7",
        "gpio6": "8",
        "gpio7": "9",
        "gpio8": "11",
        "gpio9": "12",
        "gpio10": "13",
        "gpio11": "14",
        "gpio12": "15",
        "gpio13": "16",
        "gpio14": "17",
        "gpio15": "18",
        "testen": "19",
        "xin": "20",
        "xout": "21",
        "dvdd": ("23", "50"),
        "swclk": "24",
        "swdio": "25",
        "run": "26",
        "gpio16": "27",
        "gpio17": "28",
        "gpio18": "29",
        "gpio19": "30",
        "gpio20": "31",
        "gpio21": "32",
        "gpio22": "34",
        "gpio23": "35",
        "gpio24": "36",
        "gpio25": "37",
        "gpio26": "38",
        "gpio27": "39",
        "gpio28": "40",
        "gpio29": "41",
        "adc_avdd": "43",
        "vreg_vin": "44",
        "vreg_vout": "45",
        "usb_dm": "46",
        "usb_dp": "47",
        "usb_vdd": "48",
        "qspi_sd3": "51",
        "qspi_sclk": "52",
        "qspi_sd0": "53",
        "qspi_sd2": "54",
        "qspi_sd1": "55",
        "qspi_ss": "56",
        "gnd": "57",
    }
    required_pins: ClassVar[frozenset[str] | None] = frozenset(
        {"iovdd", "dvdd", "gnd", "vreg_vin", "vreg_vout", "usb_vdd", "adc_avdd"}
    )
    default_value = "RP2040"
    default_footprint = "Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm"

    def __init__(  # noqa: PLR0913 — one keyword per physical pin
        self,
        *,
        iovdd: Net | str,
        dvdd: Net | str,
        gnd: Net | str,
        vreg_vin: Net | str,
        vreg_vout: Net | str,
        usb_vdd: Net | str,
        adc_avdd: Net | str,
        gpio0: Net | str | None = None,
        gpio1: Net | str | None = None,
        gpio2: Net | str | None = None,
        gpio3: Net | str | None = None,
        gpio4: Net | str | None = None,
        gpio5: Net | str | None = None,
        gpio6: Net | str | None = None,
        gpio7: Net | str | None = None,
        gpio8: Net | str | None = None,
        gpio9: Net | str | None = None,
        gpio10: Net | str | None = None,
        gpio11: Net | str | None = None,
        gpio12: Net | str | None = None,
        gpio13: Net | str | None = None,
        gpio14: Net | str | None = None,
        gpio15: Net | str | None = None,
        gpio16: Net | str | None = None,
        gpio17: Net | str | None = None,
        gpio18: Net | str | None = None,
        gpio19: Net | str | None = None,
        gpio20: Net | str | None = None,
        gpio21: Net | str | None = None,
        gpio22: Net | str | None = None,
        gpio23: Net | str | None = None,
        gpio24: Net | str | None = None,
        gpio25: Net | str | None = None,
        gpio26: Net | str | None = None,
        gpio27: Net | str | None = None,
        gpio28: Net | str | None = None,
        gpio29: Net | str | None = None,
        testen: Net | str | None = None,
        xin: Net | str | None = None,
        xout: Net | str | None = None,
        swclk: Net | str | None = None,
        swdio: Net | str | None = None,
        run: Net | str | None = None,
        usb_dm: Net | str | None = None,
        usb_dp: Net | str | None = None,
        qspi_sd3: Net | str | None = None,
        qspi_sclk: Net | str | None = None,
        qspi_sd0: Net | str | None = None,
        qspi_sd2: Net | str | None = None,
        qspi_sd1: Net | str | None = None,
        qspi_ss: Net | str | None = None,
        value: str | None = None,
        footprint: str | None = None,
    ) -> None:
        named = {
            "gpio0": gpio0,
            "gpio1": gpio1,
            "gpio2": gpio2,
            "gpio3": gpio3,
            "gpio4": gpio4,
            "gpio5": gpio5,
            "gpio6": gpio6,
            "gpio7": gpio7,
            "gpio8": gpio8,
            "gpio9": gpio9,
            "gpio10": gpio10,
            "gpio11": gpio11,
            "gpio12": gpio12,
            "gpio13": gpio13,
            "gpio14": gpio14,
            "gpio15": gpio15,
            "gpio16": gpio16,
            "gpio17": gpio17,
            "gpio18": gpio18,
            "gpio19": gpio19,
            "gpio20": gpio20,
            "gpio21": gpio21,
            "gpio22": gpio22,
            "gpio23": gpio23,
            "gpio24": gpio24,
            "gpio25": gpio25,
            "gpio26": gpio26,
            "gpio27": gpio27,
            "gpio28": gpio28,
            "gpio29": gpio29,
            "testen": testen,
            "xin": xin,
            "xout": xout,
            "swclk": swclk,
            "swdio": swdio,
            "run": run,
            "usb_dm": usb_dm,
            "usb_dp": usb_dp,
            "qspi_sd3": qspi_sd3,
            "qspi_sclk": qspi_sclk,
            "qspi_sd0": qspi_sd0,
            "qspi_sd2": qspi_sd2,
            "qspi_sd1": qspi_sd1,
            "qspi_ss": qspi_ss,
        }
        nets = {pin: net for pin, net in named.items() if net is not None}
        super().__init__(
            value,
            footprint,
            {
                "iovdd": iovdd,
                "dvdd": dvdd,
                "gnd": gnd,
                "vreg_vin": vreg_vin,
                "vreg_vout": vreg_vout,
                "usb_vdd": usb_vdd,
                "adc_avdd": adc_avdd,
            }
            | nets,
        )
