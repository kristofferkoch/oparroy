"""Typed parts for the CI board (docs/instrumented-ci.md).

Referenced from DESIGN.md §6 and docs/scan-plane.md.

The typed-part declarations the CI board capture draws on: the scan
plane's shift registers (11 x 74HC595 control + 2 x 74HC165 observe,
scan-plane.md §1), the per-tile power-cut P-FET and the
button-override N-FET (instrumented-ci.md §3/§6), and the demo I/O
parts (potentiometer, tactile buttons, piezo buzzer,
instrumented-ci.md §6). Pin maps are cross-checked against the
vendored datasheet notes and the KiCad symbols:

- ``Sn74hc595``/``Sn74hc165`` — datasheets/SN74HC595/notes/facts.md
  and datasheets/SN74HC165/notes/facts.md, against the KiCad
  ``74xx:74HC595``/``74xx:74HC165`` symbols (pad-for-pad equal).
- ``Ao3401a``/``N2n7002`` — SOT-23 1 = G, 2 = S, 3 = D
  (datasheets/AO3401A/notes/facts.md, datasheets/2N7002/notes/
  facts.md), matching ``Transistor_FET:AO3401A``/``:2N7002``.
- ``Rk09k`` — pin 2 is the wiper (datasheets/RK09K/notes/facts.md),
  matching ``Device:R_Potentiometer``.
- ``Ts1187a`` — four terminals in two commoned pairs, merged to pads
  1/2 by the footprint (datasheets/TS-1187A/notes/facts.md).
- ``Pklcs1212e`` — passive piezo, electrically non-polar; the
  symbol's +/- pins are phase convention
  (datasheets/PKLCS1212E/notes/facts.md).
- ``Ina241a5`` — the measurement tile's shunt amp
  (instrumented-ci.md §12); the DDF pinout from
  datasheets/INA241/notes/facts.md, matching
  ``Amplifier_Current:INA241A5xDDF`` (pin 4 is the reserved NC —
  wired to GND per the datasheet's pin table).
- ``Adcs7476`` — the measurement tile's SPI ADC; the DBV pinout from
  datasheets/ADCS7476/notes/facts.md, carried by the pin-identical
  ``Analog_ADC:ADS7886xxDBV`` symbol (the facts.md pin-compat
  verdict).

The sourcing rows live in the parts DB (``design/parts_db.py``);
the classes here stay capture-local, like ``design/phy_frontend.py``
keeps its ``Sn74lvc1g3157``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from oparroy.dsl import TypedPart

if TYPE_CHECKING:
    from oparroy.dsl import Net


class Sn74hc595(TypedPart):
    """74HC595 serial-in/parallel-out shift register (SOIC-16).

    The scan plane's control stage (scan-plane.md §1). ``qa``-``qh``
    are the storage-register outputs (bit 0 = ``qa``, scan-plane.md
    §3), ``qh_dash`` the cascade output (QH', not 3-state), ``ser``
    the data input, ``srclk``/``rclk`` the shift and storage clocks,
    ``srclr`` the shift-register clear (tied high on the CI board —
    scan-plane.md §4), ``oe`` the 3-state output enable.
    """

    symbol = "74xx:74HC595"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "qb": "1",
        "qc": "2",
        "qd": "3",
        "qe": "4",
        "qf": "5",
        "qg": "6",
        "qh": "7",
        "gnd": "8",
        "qh_dash": "9",
        "srclr": "10",
        "srclk": "11",
        "rclk": "12",
        "oe": "13",
        "ser": "14",
        "qa": "15",
        "vcc": "16",
    }
    default_value = "74HC595"
    default_footprint = "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm"

    def __init__(  # noqa: PLR0913 — one keyword per physical pin
        self,
        *,
        qa: Net | str,
        qb: Net | str,
        qc: Net | str,
        qd: Net | str,
        qe: Net | str,
        qf: Net | str,
        qg: Net | str,
        qh: Net | str,
        qh_dash: Net | str,
        ser: Net | str,
        srclk: Net | str,
        rclk: Net | str,
        srclr: Net | str,
        oe: Net | str,
        vcc: Net | str,
        gnd: Net | str,
        value: str | None = None,
        footprint: str | None = None,
    ) -> None:
        super().__init__(
            value,
            footprint,
            {
                "qa": qa,
                "qb": qb,
                "qc": qc,
                "qd": qd,
                "qe": qe,
                "qf": qf,
                "qg": qg,
                "qh": qh,
                "qh_dash": qh_dash,
                "ser": ser,
                "srclk": srclk,
                "rclk": rclk,
                "srclr": srclr,
                "oe": oe,
                "vcc": vcc,
                "gnd": gnd,
            },
        )


class Sn74hc165(TypedPart):
    """74HC165 parallel-load shift register (SOIC-16).

    The scan plane's observe stage (scan-plane.md §1). ``d0``-``d7``
    are the parallel inputs — the KiCad symbol's D0-D7 are the
    datasheet's A-H, D0 = A = bit 0 (scan-plane.md §3) — ``qh`` the
    serial output (Q7 on the symbol, QH in the datasheet), ``qh_n``
    its complement, ``ser`` the cascade input (DS), ``clk`` the shift
    clock (CP), ``clk_inh`` the clock inhibit (~CE — tied low on the
    CI board), ``sh_ld`` the asynchronous parallel-load strobe (~PL —
    the COMMIT net). The complementary output is unused on the CI
    board: ``qh_n`` is optional and the checker reports the NC pin by
    name.
    """

    symbol = "74xx:74HC165"
    required_pins: ClassVar[frozenset[str]] = frozenset(
        {
            "sh_ld",
            "clk",
            "d0",
            "d1",
            "d2",
            "d3",
            "d4",
            "d5",
            "d6",
            "d7",
            "gnd",
            "qh",
            "ser",
            "clk_inh",
            "vcc",
        }
    )
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "sh_ld": "1",
        "clk": "2",
        "d4": "3",
        "d5": "4",
        "d6": "5",
        "d7": "6",
        "qh_n": "7",
        "gnd": "8",
        "qh": "9",
        "ser": "10",
        "d0": "11",
        "d1": "12",
        "d2": "13",
        "d3": "14",
        "clk_inh": "15",
        "vcc": "16",
    }
    default_value = "74HC165"
    default_footprint = "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm"

    def __init__(  # noqa: PLR0913 — one keyword per physical pin
        self,
        *,
        d0: Net | str,
        d1: Net | str,
        d2: Net | str,
        d3: Net | str,
        d4: Net | str,
        d5: Net | str,
        d6: Net | str,
        d7: Net | str,
        ser: Net | str,
        clk: Net | str,
        clk_inh: Net | str,
        sh_ld: Net | str,
        qh: Net | str,
        vcc: Net | str,
        gnd: Net | str,
        qh_n: Net | str | None = None,
        value: str | None = None,
        footprint: str | None = None,
    ) -> None:
        nets: dict[str, Net | str] = {
            "d0": d0,
            "d1": d1,
            "d2": d2,
            "d3": d3,
            "d4": d4,
            "d5": d5,
            "d6": d6,
            "d7": d7,
            "ser": ser,
            "clk": clk,
            "clk_inh": clk_inh,
            "sh_ld": sh_ld,
            "qh": qh,
            "vcc": vcc,
            "gnd": gnd,
        }
        if qh_n is not None:
            nets["qh_n"] = qh_n
        super().__init__(value, footprint, nets)


class Ao3401a(TypedPart):
    """AO3401A P-channel MOSFET (SOT-23): the per-tile power-cut switch.

    Source on ``s`` (the always-on `3V3`), drain on ``d`` (the
    switched `3V3N`), gate on ``g`` (the `PWR` scan bit with its
    47 kΩ pull-down) — instrumented-ci.md §3. Pin order 1 = G,
    2 = S, 3 = D.
    """

    symbol = "Transistor_FET:AO3401A"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "g": "1",
        "s": "2",
        "d": "3",
    }
    default_value = "AO3401A"
    default_footprint = "Package_TO_SOT_SMD:SOT-23"

    def __init__(
        self,
        *,
        g: Net | str,
        s: Net | str,
        d: Net | str,
        value: str | None = None,
        footprint: str | None = None,
    ) -> None:
        super().__init__(value, footprint, {"g": g, "s": s, "d": d})


class N2n7002(TypedPart):
    """2N7002 N-channel MOSFET (SOT-23): the button-override FET.

    Paralleled across a tactile button: drain on ``d`` (the pulled-up
    button line), source on ``s`` (GND), gate on ``g`` (the `BTN_*`
    scan bit with its 47 kΩ pull-down) — instrumented-ci.md §6.
    Pin order 1 = G, 2 = S, 3 = D.
    """

    symbol = "Transistor_FET:2N7002"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "g": "1",
        "s": "2",
        "d": "3",
    }
    default_value = "2N7002"
    default_footprint = "Package_TO_SOT_SMD:SOT-23"

    def __init__(
        self,
        *,
        g: Net | str,
        s: Net | str,
        d: Net | str,
        value: str | None = None,
        footprint: str | None = None,
    ) -> None:
        super().__init__(value, footprint, {"g": g, "s": s, "d": d})


class Rk09k(TypedPart):
    """ALPS RK09K rotary potentiometer (THT, hand-soldered post-PCBA).

    The input tiles' 10 kΩ demo knob (instrumented-ci.md §6): ``a``
    and ``b`` are the resistive element's ends (across `3V3N`/GND),
    ``wiper`` the tap toward the substitution mux. Pin 2 is the wiper
    (datasheets/RK09K/notes/facts.md).
    """

    symbol = "Device:R_Potentiometer"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "a": "1",
        "wiper": "2",
        "b": "3",
    }
    default_value = "10k"
    default_footprint = "Potentiometer_THT:Potentiometer_Alps_RK09K_Single_Vertical"

    def __init__(
        self,
        *,
        a: Net | str,
        wiper: Net | str,
        b: Net | str,
        value: str | None = None,
        footprint: str | None = None,
    ) -> None:
        super().__init__(value, footprint, {"a": a, "wiper": wiper, "b": b})


class Ts1187a(TypedPart):
    """XKB TS-1187A tactile button (SMD-4P 5.1x5.1 mm).

    The four terminals are two commoned pairs; the footprint merges
    each pair, so the switch wires as ``a``/``b`` (pads 1/2) —
    datasheets/TS-1187A/notes/facts.md.
    """

    symbol = "Switch:SW_Push"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {"a": "1", "b": "2"}
    default_value = "TS-1187A-B-A-B"
    default_footprint = "Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A"

    def __init__(
        self,
        *,
        a: Net | str,
        b: Net | str,
        value: str | None = None,
        footprint: str | None = None,
    ) -> None:
        super().__init__(value, footprint, {"a": a, "b": b})


class Pklcs1212e(TypedPart):
    """Murata PKLCS1212E4001-R1 passive piezo sounder (SMD 12x12 mm).

    The output tiles' buzzer (instrumented-ci.md §6): ``pos`` toward
    the 470 Ω series R, ``neg`` to GND. Electrically non-polar — the
    +/- pins are phase convention (datasheets/PKLCS1212E/notes/
    facts.md).
    """

    symbol = "Device:Buzzer"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {"pos": "1", "neg": "2"}
    default_value = "PKLCS1212E4001-R1"
    default_footprint = "Buzzer_Beeper:Buzzer_Murata_PKLCS1212E"

    def __init__(
        self,
        *,
        pos: Net | str,
        neg: Net | str,
        value: str | None = None,
        footprint: str | None = None,
    ) -> None:
        super().__init__(value, footprint, {"pos": pos, "neg": neg})


class Ina241a5(TypedPart):
    """TI INA241A5 current-sense amp (SOT-23-8): the measurement tile's shunt amp.

    Gain 200 V/V, powered from the always-on `3V3`, sensing across the
    82 mΩ shunt downstream of the F8 power-cut switch
    (instrumented-ci.md §12). ``in_p`` is the bus side of the shunt,
    ``in_m`` the load side (`3V3N`); ``ref1``/``ref2`` strap the output
    reference — the tile biases them mid-rail (REF1 to `3V3`, REF2 to
    GND) so the cut-state clamp back-feed reads as a negative current.
    Pin 4 (``nc``) is the reserved pin — the datasheet's pin table ties
    it to GND (datasheets/INA241/notes/facts.md, DS §5 Table 5-1).
    """

    symbol = "Amplifier_Current:INA241A5xDDF"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "in_m": "1",
        "gnd": "2",
        "ref2": "3",
        "nc": "4",
        "out": "5",
        "vs": "6",
        "ref1": "7",
        "in_p": "8",
    }
    required_pins: ClassVar[frozenset[str]] = frozenset(
        {"in_m", "gnd", "ref2", "nc", "out", "vs", "ref1", "in_p"}
    )
    default_value = "INA241A5"
    default_footprint = "Package_TO_SOT_SMD:SOT-23-8"

    def __init__(  # noqa: PLR0913 — one keyword per physical pin
        self,
        *,
        in_m: Net | str,
        gnd: Net | str,
        ref2: Net | str,
        nc: Net | str,
        out: Net | str,
        vs: Net | str,
        ref1: Net | str,
        in_p: Net | str,
        value: str | None = None,
        footprint: str | None = None,
    ) -> None:
        super().__init__(
            value,
            footprint,
            {
                "in_m": in_m,
                "gnd": gnd,
                "ref2": ref2,
                "nc": nc,
                "out": out,
                "vs": vs,
                "ref1": ref1,
                "in_p": in_p,
            },
        )


class Adcs7476(TypedPart):
    """TI ADCS7476 12-bit 1 MSPS SPI ADC (SOT-23-6): the measurement tile's ADC.

    VDD-as-reference on the always-on `3V3`; ``vin`` rides the shunt
    amp's output through the charge-bucket RC; ``sclk``/``cs``/``sdo``
    face the supervisor's PIO burst capture (instrumented-ci.md §12).
    The KiCad symbol is the pin-identical ADS7886xxDBV
    (datasheets/ADCS7476/notes/facts.md pin-compat verdict); pin 5 is
    tri-state between conversions.
    """

    symbol = "Analog_ADC:ADS7886xxDBV"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "vdd": "1",
        "gnd": "2",
        "vin": "3",
        "sclk": "4",
        "sdo": "5",
        "cs": "6",
    }
    required_pins: ClassVar[frozenset[str]] = frozenset(
        {"vdd", "gnd", "vin", "sclk", "sdo", "cs"}
    )
    default_value = "ADCS7476"
    default_footprint = "Package_TO_SOT_SMD:SOT-23-6"

    def __init__(  # noqa: PLR0913 — one keyword per physical pin
        self,
        *,
        vdd: Net | str,
        gnd: Net | str,
        vin: Net | str,
        sclk: Net | str,
        sdo: Net | str,
        cs: Net | str,
        value: str | None = None,
        footprint: str | None = None,
    ) -> None:
        super().__init__(
            value,
            footprint,
            {
                "vdd": vdd,
                "gnd": gnd,
                "vin": vin,
                "sclk": sclk,
                "sdo": sdo,
                "cs": cs,
            },
        )
