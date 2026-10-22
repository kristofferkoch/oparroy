"""The CI board's instrumentation transform plan (docs/instrumented-ci.md §7).

The §7 transform list as data, keyed against the Node subcircuit's
capture names (`design/node.py`, `design/phy_frontend.py`,
`design/watchdog_chargepump.py`, `design/status_leds.py`) and the
CI tile variants (`design/ci_tiles.py` — the §6 payload carriers the
H-transforms cut against):

- **F1-F6, per tile except T6** — the §2 four-state segment injector on the
  tile's downstream-boundary wires ``TX_A``/``RX_B``: a break switch
  (B1 = pass, B2 = NC) plus a 470 Ω-legged shunt to GND and to `3V3`
  per wire (shunts on B2 — bit 0 = branch absent). The same six
  records serve the supervisor originator port
  (:func:`segment_injector`), so eight of the ring's nine segments are
  instrumented at exactly one end (§2) — the measurement tile's
  downstream segment is the exception (§12).
- **F7** — the §4 keep-alive cut on `ka` (U1.PD3 ↔ WD1/Rs.a), 47 kΩ
  pull-down parking the watchdog-side stub low. Every tile but T6.
- **F8** — the §3 power cut: `3V3` → `3V3N` behind the AO3401A
  high-side P-FET, 47 kΩ gate pull-down (POR = on). The detached pin
  list *is* the §3 domain split: U1 VDD with C1/C2, the VDD/2 divider
  top `PHY1/Rth1`, all of SL1, TP2 — plus, on input tiles, the pot
  end and the button pull-ups. The bypass switch `PHY1/SW1`, the DNP
  Schmitt `PHY1/BUF1`, the injector switch VCCs, and the shunt/defeat
  leg sources stay on the always-on `3V3`. The measurement tile's F8
  (:func:`measurement_power_cut`) is the same cut extended with the
  §12 chain: the FET drain feeds 3V3N through the 82 mΩ shunt, and the
  INA241A5 + ADCS7476 ride the shunt from the always-on rail.
- **P1-P3, the measurement tile** — the §12 chain's SPI escapes:
  taps on F8's transform-local `F8_sclk`/`F8_cs`/`F8_sdata` nets,
  wired at board level to the supervisor's PIO burst-capture pins.
  The tri-stated SDO and the POR-input GPIOs carry the reset-state
  justification (`AddTap.non_input_consumers`).
- **B1-B5, boundary tile** — the §5 PIO taps on `opa_p`, `TX_A#b`
  (post-injector, so the tap rides the split alias and must apply
  after F1), `opo`, `led_work`, and the watchdog defeat: a 3157 shunt
  clamping `sel` to the always rail through the §2 legs' 470 Ω
  (B1 = NC = watchdog in charge).
  The taps feed the supervisor's bidirectional GPIOs, so they carry
  the POR-input justification (`AddTap.non_input_consumers`).
- **O1/O2, per tile** — the §8 observe taps: `sel` (the truthful
  node-health bit) and `3V3N` (the coarse power bit) to the 165
  chain's D inputs. O2 taps the net F8 creates, so it must apply
  after the faults set.
- **M1/M2, per tile** — the §5 mux-tree taps: `swio` to the flash
  tree's leaf, `debug_tx` to the debug tree's leaf. The trees'
  bidirectional channel pins and the SWIO leaf pull-ups are the
  declared non-input-class consumers.
- **H1-H3, input tiles** — the §6 overrides against the variant
  payload nets: the pot substitution mux (B1 = wiper = human, B2 =
  the supervisor's filtered PWM — the escaped `POT_PWM` source behind
  its 10 kΩ + 100 nF, fc ≈ 160 Hz) and the button-override N-FETs as
  shunt branches across the buttons (47 kΩ gate pull-downs, POR =
  released). The doc's §7 table kinds H2/H3 as "substitute"; a
  paralleled FET is a branch that is open in reset state, which is
  `AddShunt`'s semantics — `Substitute`'s re-drive-the-load-side cut
  has nothing to cut on a pulled-up button line.

Every control line's bit-0 = plain-board state (§8) is structural in
the records: break switches pass on B1, shunts and defeat hang on B2,
the P-FET gate and the button-FET gates pull down to the active
state's inverse. :func:`reset_levels` derives the equivalence proof's
all-zeros input from the plan itself.

The injector switch is the board's one stocked 3157 line (§2), bound
from the parts DB so the equivalence proof inherits its residual
magnitudes (memo Q3); the FETs bind likewise. Transform-local nets use
the engine's ``@`` placeholders: ``@a``/``@b`` the cut sides,
``@net``/``@control``/``@source`` the shunt base and the escaped ports,
``@leg``/``@filt`` the shared fresh nets.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from design.bins import C0603, R0603
from design.ci_parts import Adcs7476, Ao3401a, Ina241a5, N2n7002
from design.ci_tiles import InputNode, MeasurementNode, OutputNode
from design.parts_db import PARTS
from oparroy.dsl import (
    AddShunt,
    AddTap,
    InsertSeries,
    PerInstance,
    PerTile,
    Substitute,
    TileNet,
    TransformPart,
    TypedPart,
)
from oparroy.dsl.equivalence import (
    EXTRA_LOADING,
    LEAKAGE,
    SERIES_ON_RESISTANCE,
    SHUNT_OFF_CAPACITANCE,
    SWITCH_CAPACITANCE,
    TAP_CAPACITANCE,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from oparroy.dsl import Circuit, Instance, Net, Scope, Transform

__all__ = [
    "BUDGETS",
    "boundary_taps",
    "ci_transform_plan",
    "input_overrides",
    "measurement_power_cut",
    "measurement_taps",
    "observe_taps",
    "per_tile_faults",
    "reset_levels",
    "segment_injector",
    "tree_taps",
]


class _FiSwitch(TypedPart):
    """SN74LVC1G3157 as the injector switch (SOT-23-6): a throw may be NC.

    The §2 injector leaves the break switch's B2 and the shunt
    switches' B1 open; ``required_pins`` narrows to the always-wired
    pins and the checker reports the NC throw by name. ``a`` is the
    common, ``b1`` the S-low throw (the bit-0 = plain-board state),
    ``b2`` the S-high throw, ``s`` the select.
    """

    symbol = "74xGxx:74LVC1G3157"
    pin_map: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "b2": "1",
        "gnd": "2",
        "b1": "3",
        "a": "4",
        "vcc": "5",
        "s": "6",
    }
    required_pins: ClassVar[frozenset[str]] = frozenset({"a", "s", "vcc", "gnd"})
    default_footprint = "Package_TO_SOT_SMD:SOT-23-6"

    def __init__(  # noqa: PLR0913 — one keyword per physical pin
        self,
        *,
        a: Net | str,
        s: Net | str,
        vcc: Net | str,
        gnd: Net | str,
        b1: Net | str | None = None,
        b2: Net | str | None = None,
        value: str | None = None,
        footprint: str | None = None,
    ) -> None:
        nets: dict[str, Net | str] = {"a": a, "s": s, "vcc": vcc, "gnd": gnd}
        if b1 is not None:
            nets["b1"] = b1
        if b2 is not None:
            nets["b2"] = b2
        super().__init__(value, footprint, nets)


#: The transform parts, DB-bound so the equivalence proof inherits the
#: residual magnitudes (memo Q3). The 3157 is the §2 switch line; the
#: FETs are the §3 power cut and the §6 button override; the amp and
#: the ADC are the measurement tile's §12 chain (extras of its F8
#: record — extras need only a value for the proof's EXTRA_LOADING
#: residual, which the DB bindings carry).
FiSwitch = PARTS.bind("sn74lvc1g3157-ti", _FiSwitch, class_name="FiSwitch")
PowerCutFet = PARTS.bind("ao3401a", Ao3401a, class_name="PowerCutFet")
ButtonFet = PARTS.bind("2n7002", N2n7002, class_name="ButtonFet")
SenseAmp = PARTS.bind("csa-ina241a5", Ina241a5, class_name="SenseAmp")
ChainAdc = PARTS.bind("adc-adcs7476", Adcs7476, class_name="ChainAdc")


def _shunt(label: str, net: str, rail: str, suffix: str, bit: str) -> AddShunt:
    """Build one shunt leg: a 3157 branch through 470 Ω to the rail.

    The branch hangs on B2 — bit 0 (S low, B1 = NC) is the plain
    board's absent branch (§2). The 470 Ω leg bounds every latched bit
    pattern (§2: no interlocks, never damage).
    """
    return AddShunt(
        label=label,
        net=f"{net}#b",
        rail=rail,
        part=TransformPart(
            f"FI1/SW{suffix}",
            FiSwitch(a="@net", b2="@leg", s="@control", vcc="3V3", gnd="GND"),
        ),
        control=bit,
        extra=(TransformPart(f"FI1/R{suffix}", R0603("470", a="@leg", b=rail)),),
    )


def segment_injector(
    *,
    tx_net: str = "TX_A",
    tx_pin: str = "PHY1/Rat.b",
    rx_net: str = "RX_B",
    rx_pin: str = "PHY1/Rbr.a",
) -> tuple[Transform, ...]:
    """Build F1-F6: the §2 four-state injector on one segment's two wires.

    The tile-side defaults name the Node capture's split points (§2:
    `PHY1/Rat.b` ↔ {downstream, `PHY1/Dat`} on `TX_A`, `PHY1/Rbr.a` ↔
    {downstream, `PHY1/Dbr`} on `RX_B`); the supervisor originator
    port's injector is the same six records against its own capture
    names (§7 — the supervisor→tile-0 segment, instrumented at the
    supervisor end).
    """
    break_a = InsertSeries(
        label="F1",
        net=tx_net,
        pins=(tx_pin,),
        part=TransformPart(
            "FI1/SWAB",
            FiSwitch(a="@a", b1="@b", s="@control", vcc="3V3", gnd="GND"),
        ),
        control="BRK_A",
    )
    break_b = InsertSeries(
        label="F4",
        net=rx_net,
        pins=(rx_pin,),
        part=TransformPart(
            "FI1/SWBB",
            FiSwitch(a="@a", b1="@b", s="@control", vcc="3V3", gnd="GND"),
        ),
        control="BRK_B",
    )
    return (
        break_a,
        _shunt("F2", tx_net, "GND", "AG", "SHG_A"),
        _shunt("F3", tx_net, "3V3", "AV", "SHV_A"),
        break_b,
        _shunt("F5", rx_net, "GND", "BG", "SHG_B"),
        _shunt("F6", rx_net, "3V3", "BV", "SHV_B"),
    )


def _keep_alive_cut() -> InsertSeries:
    """Build F7: the §4 keep-alive cut, pull-down on the watchdog-side stub."""
    return InsertSeries(
        label="F7",
        net="ka",
        pins=("U1.pd3",),
        part=TransformPart(
            "FI1/SWKA",
            FiSwitch(a="@a", b1="@b", s="@control", vcc="3V3", gnd="GND"),
        ),
        control="KA_CUT",
        extra=(TransformPart("FI1/RKA", R0603("47k", a="@b", b="GND")),),
    )


#: The §3 3V3N domain, as the detached-side pin list of the F8 cut:
#: U1 VDD with its decoupling, the VDD/2 divider top, all of SL1 (the
#: power LED narrates the cut), the 3V3 test pad.
F8_DOMAIN_PINS = (
    "U1.vdd",
    "C1.a",
    "C2.a",
    "TP2.p",
    "PHY1/Rth1.a",
    "SL1/Rp.a",
    "SL1/Dd.anode",
)

#: The input-tile payload pins that join 3V3N (§6: the pot and the
#: button pull-ups sit across the switched rail).
F8_INPUT_PINS = ("POT1.a", "RPA.b", "RPB.b")


def _power_cut(extra_pins: tuple[str, ...] = ()) -> InsertSeries:
    """Build F8: the §3 rail split behind the AO3401A high-side switch.

    ``switched_domain`` tags the detached 3V3N as the tile's SWITCHED
    domain deriving from the always 3V3 — the power-domain crossing
    audit's domain pair.
    """
    return InsertSeries(
        label="F8",
        net="3V3",
        pins=(*F8_DOMAIN_PINS, *extra_pins),
        name="3V3N",
        part=TransformPart("FI1/QPW", PowerCutFet(s="@b", d="@a", g="@control")),
        control="PWR",
        switched_domain=True,
        extra=(TransformPart("FI1/RPW", R0603("47k", a="@control", b="GND")),),
    )


def measurement_power_cut() -> tuple[Transform, ...]:
    """Build the measurement tile's transform set: F8 extended per §12.

    The same power cut the other tiles carry — same label, same
    control, same switched-domain split — but the FET's drain feeds
    3V3N through the 82 mΩ shunt (``R082`` from the §7 bin), and the
    INA241A5 + ADCS7476 chain rides the shunt: the amp senses across it
    (IN+ on the FET side ``@sns``, IN- on 3V3N), REF1/REF2 strapped to
    3V3/GND for the mid-rail bidirectional read (the cut-state clamp
    back-feed shows as a negative current — §12's settled placement),
    the charge-bucket RC (47 Ω + 1 nF: τ = 47 ns recovers the 26 pF
    sampling kick to 12 bits in ≈390 ns of the 1 µs frame, C at the
    amp's 1 nF max-load ceiling behind the isolating R) between the amp
    and the ADC, a 47 kΩ CS pull-up holding the ADC deselected through
    the POR Hi-Z window (scan-plane.md §4's discipline), and the
    datasheet bypass set (amp 100 nF; ADC 100 nF + 1 µF). The SPI pins
    sit on transform-local nets the P1-P3 taps escape to the
    supervisor. The amp and ADC power from the always-on 3V3 — the
    chain reads through the tile's own power cut.
    """
    return (
        InsertSeries(
            label="F8",
            net="3V3",
            pins=F8_DOMAIN_PINS,
            name="3V3N",
            part=TransformPart("FI1/QPW", PowerCutFet(s="@b", d="@sns", g="@control")),
            control="PWR",
            switched_domain=True,
            extra=(
                TransformPart("FI1/RPW", R0603("47k", a="@control", b="GND")),
                TransformPart("FI1/RSH", R0603("R082", a="@sns", b="@a")),
                TransformPart(
                    "FI1/UIM",
                    SenseAmp(
                        in_p="@sns",
                        in_m="@a",
                        vs="3V3",
                        ref1="3V3",
                        ref2="GND",
                        nc="GND",
                        out="@imeas",
                        gnd="GND",
                    ),
                ),
                TransformPart("FI1/RFC", R0603("47", a="@imeas", b="@adc_in")),
                TransformPart("FI1/CFC", C0603("1n", a="@adc_in", b="GND")),
                TransformPart(
                    "FI1/UAD",
                    ChainAdc(
                        vdd="3V3",
                        gnd="GND",
                        vin="@adc_in",
                        sclk="@sclk",
                        sdo="@sdata",
                        cs="@cs",
                    ),
                ),
                TransformPart("FI1/RCS", R0603("47k", a="@cs", b="3V3")),
                TransformPart(
                    "FI1/CIM",
                    C0603("100n", a="3V3", b="GND"),
                    note="decoupling for {FI1/UIM}",
                ),
                TransformPart(
                    "FI1/CAD1",
                    C0603("100n", a="3V3", b="GND"),
                    note="decoupling for {FI1/UAD}",
                ),
                TransformPart(
                    "FI1/CAD2",
                    C0603("1u", a="3V3", b="GND"),
                    note="bulk decoupling for {FI1/UAD}",
                ),
            ),
        ),
    )


def measurement_taps() -> tuple[AddTap, ...]:
    """Build P1-P3: the §12 chain's SPI escapes to the supervisor.

    The taps ride F8's transform-local nets (``F8_sclk`` etc.), so they
    must apply after it. The consumers are the supervisor's GPIOs —
    inputs from POR (scan-plane.md §4's zero-load discipline) — and the
    ADCS7476's SDO, tri-stated between conversions while CS sits high
    on the tile's pull-up; the burst drive is the §12 injected state
    the proof does not cover.
    """
    consumers = (
        "supervisor GPIOs are inputs from POR (scan-plane.md §4's "
        "zero-load discipline); the ADCS7476's SDO tri-states while CS "
        "sits high on the tile's 47 kΩ pull-up — the burst drive is the "
        "injected state (instrumented-ci.md §12)"
    )
    return (
        AddTap(label="P1", net="F8_sclk", non_input_consumers=consumers),
        AddTap(label="P2", net="F8_cs", non_input_consumers=consumers),
        AddTap(label="P3", net="F8_sdata", non_input_consumers=consumers),
    )


def per_tile_faults(*, input_tile: bool = False) -> tuple[Transform, ...]:
    """Build F1-F8 against the Node capture names (§7, per-tile set)."""
    return (
        *segment_injector(),
        _keep_alive_cut(),
        _power_cut(F8_INPUT_PINS if input_tile else ()),
    )


def boundary_taps() -> tuple[Transform, ...]:
    """Build B1-B5: the §5 boundary-node PIO taps and the watchdog defeat.

    The taps feed the supervisor's GPIO8-11 — bidirectional pins, so
    each declares its non-input-class consumers: the RP2040's GPIOs
    are inputs from POR until firmware drives them (the §8 zero-load
    boot); stimulus drive is the injected state the proof does not
    cover (instrumented-ci.md §5).
    """
    tap_consumers = (
        "RP2040 tap GPIOs are inputs from POR (scan-plane.md §4's "
        "zero-load discipline); stimulus drive is the §6 injected state"
    )
    return (
        AddTap(label="B1", net="opa_p", non_input_consumers=tap_consumers),
        AddTap(label="B2", net="TX_A#b", non_input_consumers=tap_consumers),
        AddTap(label="B3", net="opo", non_input_consumers=tap_consumers),
        AddTap(label="B4", net="led_work", non_input_consumers=tap_consumers),
        AddShunt(
            label="B5",
            net="sel",
            rail="3V3",
            part=TransformPart(
                "FI1/SWWD",
                FiSwitch(a="@net", b2="@leg", s="@control", vcc="3V3", gnd="GND"),
            ),
            control="WD_DEFEAT",
            extra=(TransformPart("FI1/RWD", R0603("470", a="@leg", b="3V3")),),
        ),
    )


def observe_taps() -> tuple[AddTap, ...]:
    """Build O1/O2: the §8 per-tile observe taps to the 165 chain.

    `sel` reports the bypass state (the truthful node-health bit);
    `3V3N` is the coarse power bit (F8's switched rail — the tap must
    apply after the faults set). The consumers are the 165's
    parallel-in pins — input-class, so no consumer declaration.
    """
    return (
        AddTap(label="O1", net="sel"),
        AddTap(label="O2", net="3V3N"),
    )


def tree_taps() -> tuple[AddTap, ...]:
    """Build M1/M2: the §5 SWIO/debug tree leaf taps.

    The consumers are the trees' 3157 channel pins — bidirectional —
    plus the SWIO tree's 10 kΩ leaf pull-ups, so both taps carry the
    reset-state justification: at POR the selects sit at 000, opening
    every leaf channel except tile 0's, which connects to a Hi-Z root
    (the supervisor's GPIO is an input at POR; the 4.7 kΩ root pull-up
    and the leaf pull-ups are the only DC paths — scan-plane.md §4/§5).
    """
    swio_consumers = (
        "3157 leaf channels reset open except leaf 0's, to a Hi-Z root "
        "(scan-plane.md §4/§5); the 10 kΩ leaf pull-up to the tile's own "
        "3V3N is the one DC load"
    )
    debug_consumers = (
        "3157 leaf channels reset open except leaf 0's, connecting the "
        "tile's push-pull debug TX to the supervisor's Hi-Z UART RX "
        "(scan-plane.md §5)"
    )
    return (
        AddTap(label="M1", net="swio", non_input_consumers=swio_consumers),
        AddTap(label="M2", net="debug_tx", non_input_consumers=debug_consumers),
    )


def input_overrides() -> tuple[Transform, ...]:
    """Build H1-H3: the §6 human-I/O overrides against the variant payload."""
    return (
        Substitute(
            label="H1",
            net="pot_w",
            pins=("POT1.wiper",),
            part=TransformPart(
                "FI1/SWPOT",
                FiSwitch(
                    a="@b", b1="@a", b2="@filt", s="@control", vcc="3V3", gnd="GND"
                ),
            ),
            source="POT_PWM",
            control="POT_SEL",
            extra=(
                TransformPart("FI1/RPF", R0603("10k", a="@source", b="@filt")),
                TransformPart("FI1/CPF", C0603("100n", a="@filt", b="GND")),
            ),
        ),
        *(
            AddShunt(
                label=f"H{index}",
                net=f"btn_{letter}",
                rail="GND",
                part=TransformPart(
                    f"FI1/QB{letter.upper()}",
                    ButtonFet(d="@net", s="GND", g="@control"),
                ),
                control=f"BTN_{letter.upper()}",
                extra=(
                    TransformPart(
                        f"FI1/RB{letter.upper()}",
                        R0603("47k", a="@control", b="GND"),
                    ),
                ),
            )
            for index, letter in ((2, "a"), (3, "b"))
        ),
    )


def ci_transform_plan(
    *,
    boundary: str = "T0",
    supervisor_port: tuple[str, ...] | None = None,
    supervisor_nets: tuple[str, str, str, str] | None = None,
) -> list[Scope]:
    """Assemble the §7 transform list: per-tile F1-F8 plus the per-role sets.

    The per-tile keying matches the CI tile variants
    (`design/ci_tiles.py`): every OutputNode gets the F-set, every
    InputNode the F-set with its payload pins joining 3V3N plus the
    H-set — one declaration each instruments all instances of the
    variant — every tile of either variant gets the observe (O1/O2)
    and mux-tree (M1/M2) taps, and the MeasurementNode gets the §12
    extended F8 with its P1-P3 SPI escapes instead of the F-set.
    ``boundary`` names the tile-0 instance for B1-B5.
    ``supervisor_port``/``supervisor_nets`` add the originator port's
    F1-F6 (§7): the instance path, and its (tx_net, tx_pin, rx_net,
    rx_pin) capture names. The `Supervisor` capture's ring ports
    (`design/supervisor.py`) mirror the tile's names minus the PHY1
    prefix, so the board composition passes
    ``("TX_A", "Rat.b", "RX_B", "Rbr.a")``.
    """
    plan: list[Scope] = [
        PerTile(OutputNode, (*per_tile_faults(), *observe_taps(), *tree_taps())),
        PerTile(
            InputNode,
            (
                *per_tile_faults(input_tile=True),
                *input_overrides(),
                *observe_taps(),
                *tree_taps(),
            ),
        ),
        # The §12 measurement tile: the extended power cut plus the
        # observe/tree taps every tile carries, then the SPI escapes —
        # they tap F8's transform-local nets and must follow it.
        PerTile(
            MeasurementNode,
            (
                *measurement_power_cut(),
                *observe_taps(),
                *tree_taps(),
                *measurement_taps(),
            ),
        ),
        PerInstance((boundary,), boundary_taps()),
    ]
    if supervisor_port is not None:
        if supervisor_nets is None:
            msg = (
                "supervisor_port needs supervisor_nets (tx_net, tx_pin, rx_net, rx_pin)"
            )
            raise ValueError(msg)
        tx_net, tx_pin, rx_net, rx_pin = supervisor_nets
        plan.append(
            PerInstance(
                supervisor_port,
                segment_injector(
                    tx_net=tx_net, tx_pin=tx_pin, rx_net=rx_net, rx_pin=rx_pin
                ),
            )
        )
    return plan


def reset_levels(circuit: Circuit, plan: Sequence[Scope]) -> dict[TileNet, int]:
    """Derive the equivalence proof's reset input: the §8 all-zeros load.

    Every control port the plan escapes maps to 0 — the bit-0 =
    plain-board invariant (instrumented-ci.md §8) as data, keyed by
    :class:`TileNet` like the transform handles. Substitute sources
    are not controls and take no level.
    """
    levels: dict[TileNet, int] = {}
    for scope in plan:
        paths = (
            [
                path
                for path, inst in _walk(circuit)
                if isinstance(scope.subcircuit, type)
                and type(inst.subcircuit) is scope.subcircuit
            ]
            if isinstance(scope, PerTile)
            else [scope.path]
        )
        for path in paths:
            for transform in scope.transforms:
                if not isinstance(transform, AddTap) and transform.control is not None:
                    levels[TileNet(path, transform.control)] = 0
    return levels


def _walk(
    circuit: Circuit, path: tuple[str, ...] = ()
) -> Iterator[tuple[tuple[str, ...], Instance]]:
    """Yield every instance in the hierarchy with its full path."""
    for inst in circuit.instances.values():
        yield (*path, inst.name), inst
        yield from _walk(inst.circuit, (*path, inst.name))


#: The §9 residual register's budget citations, keyed by residual kind
#: — the equivalence proof's ``budgets`` input.
BUDGETS = {
    SERIES_ON_RESISTANCE: (
        "instrumented-ci.md §9 R1/R3/R5 — §2 tb_decode swept the "
        "inserted-switch path; +7 Ω on the 220 Ω glitch filter is "
        "non-critical; ≤ 85 mΩ on 3V3N is ≤ 3 mV at 30 mA"
    ),
    SWITCH_CAPACITANCE: (
        "instrumented-ci.md §9 R2/R7 — ≈28 pF sits below §2's swept "
        "47 pF floor; +7 Ω-class Ron in the ≥ 3.5 kΩ ADC source path"
    ),
    SHUNT_OFF_CAPACITANCE: (
        "instrumented-ci.md §9 R8/R9 — millivolt-level on the pulled-up "
        "button lines; +Coss-class pF on Cs = 10 nF leaves §4 timing "
        "unchanged"
    ),
    LEAKAGE: (
        "instrumented-ci.md §9 R11 — 3157 ±1 µA max (SCES424O §5.5) and "
        "2N7002 ≤ 80 nA are µV-class across the 470 Ω legs and 10 kΩ "
        "pull-ups — inside the §2 swept margins the R1/R2 citations "
        "point at"
    ),
    EXTRA_LOADING: (
        "instrumented-ci.md §9 R4/R12 — the 47 kΩ pull-down class; "
        "shunt-leg and gate resistors load nothing in reset state "
        "(branches absent, FETs off). The measurement tile's §12 chain: "
        "the 82 mΩ shunt drops ≤ 4.1 mV at the 50 mA tile ceiling — "
        "inside the FET's existing spend at every current (§12) — the "
        "amp's ≤ 45 µA/pin input bias is 1 %-class against the 4 mA "
        "idle floor, and the amp + ADC quiescent (~3.1 mA) rides the "
        "always rail, invisible to the tile's nodes"
    ),
    TAP_CAPACITANCE: (
        "instrumented-ci.md §9 R6 — Rar x 10 pF = 4.7 ns vs §2's "
        "≥ 70 ns slice margin; the O1/O2 observe taps and the M1/M2 "
        "tree stubs are the same stub class (the register's "
        "observe/tree rows are a §9 gap, closing with the layout "
        "card); the P1-P3 SPI stubs resolve onto the always rail by "
        "provenance — pF-class stubs on 3V3 perturb nothing; stub "
        "length is the §7 layout checker's short-stub "
        "contract"
    ),
}
