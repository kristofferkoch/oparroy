"""CI board tile variants: the plain Node plus the §6 demonstrator payload.

The CI board tiles two Node variants (docs/instrumented-ci.md §6):
**input tiles** (1, 3, 5, 7) carry the potentiometer and the two
buttons, **output tiles** (0, 2, 4, 6 — the boundary tile among them)
carry the buzzer. The payloads bind the pin map's reserved functions
(``pot`` = PD6, ``button_a`` = PC5, ``button_b`` = PC6, ``buzzer`` =
PC4; `design/node_pins.py`), wired per §6: the 10 kΩ pot across the
switched rail, buttons to GND with 10 kΩ pull-ups, both behind the §7
1 kΩ series resistors, the piezo behind its 470 Ω.

The payload is **capture**, not instrumentation: the plain node's
payload pads sit unwired, and the transform kinds
(`src/oparroy/dsl/transform.py`) all anchor on an existing net, so no
transform can introduce a driver onto an unwired pad. The variants are
the base the human-I/O override transforms
(`design/ci_instrumentation.py` H1-H3) cut against, and the
equivalence proof compares instrumented vs uninstrumented captures of
the *same* variant — the payload appears on both sides and never
enters the residual register, exactly as docs/instrumented-ci.md §9
enumerates only the override parts (R7/R8). The standalone node board
keeps the plain ``Node``; nothing here touches it.

Rail note: the payload's rail-side pins (pot end, button pull-ups)
wire the tile's ``3V3`` port *pre-split*; the F8 power-cut transform's
detached pin list moves them onto ``3V3N`` (the pot and pull-ups must
die with the MCU rail — instrumented-ci.md §3/§6).

Both variants also wire the PD5 ``debug_tx`` pad (unwired on the plain
node) — the §5 debug tree's leaves land on it (docs/scan-plane.md §5)
— and inherit ``Node``'s ``connector_faces``: the CI board keeps only
the boundary tile's upstream face and drops the rest with their TVS
pairs (instrumented-ci.md §9 R10).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from design.bins import R0603
from design.ch32v003 import Ch32v003f4p6
from design.ci_parts import Pklcs1212e, Rk09k, Ts1187a
from design.node import Node
from design.node_pins import capture as capture_pin_map
from oparroy.dsl import AlwaysPowered, BackFeed

if TYPE_CHECKING:
    from oparroy.dsl import Circuit, Part, Pin


#: The §3 clamp-injection bound behind the tile crossing budgets:
#: (3.3 - 0.6) V across the 470 Ω terminal-protection series R
#: ≈ 5.7 mA per driven dead pin, against the CH32V003's Σ ±20 mA
#: injection budget (instrumented-ci.md §3, CH32V003 facts T3-1).
_CLAMP_PIN_MA = 5.7


def ring_back_feed(drivers: str, pins: int, resistor: str) -> BackFeed:
    """Build the §3 bounded-back-feed disposition: 5.7 mA per dead-side pin.

    ``drivers`` names the live-side drive sources, ``pins`` counts the
    dead-side MCU pins on the net's resistive reach, ``resistor`` the
    terminal-protection series R bounding the injection. The board's
    segment-wire declarations (`design/ci_board.py`) share it.
    """
    return BackFeed(
        _CLAMP_PIN_MA * pins,
        f"instrumented-ci.md §3 — {drivers} into the gated tile's MCU "
        f"clamps through {resistor} (470 Ω): ≤ 5.7 mA per pin, {pins} "
        "dead-side pin(s) on the net's resistive reach, inside the "
        "±20 mA injection budget (CH32V003 facts T3-1)",
    )


def _declare_tile_crossings(circuit: Circuit) -> None:
    """Declare the tile's power-domain crossing dispositions.

    F8's rail split (instrumented-ci.md §3) puts the MCU-facing nets
    across the always/switched boundary; the declarations live next to
    the wiring so every composition of the variants inherits them with
    hierarchical prefixing — the plain side's copies warn stale, the
    crossings being an instrumented-side phenomenon. The F4-created
    stub is declared by its forward-referenced split name (``RX_B#a``).
    The mux-tree leaves cross through the always-powered 3157 channels
    (the no-Ioff placement rule); the SWIO leaf's one DC path — its
    10 kΩ pull-up — lands on the tile's own 3V3N and dies with it, and
    a selected gated node's debug TX reads as garbage, which the
    emit-and-forget contract tolerates (scan-plane.md §5). The boundary
    tile's B1/B3 stimulus taps ride the same envelope (instrumented-ci
    §5: ≤ 7 mA pad-driven against the idled ring — 11.4 + 7 ≈ 18 mA
    inside the ±20 mA budget).

    The ``sel``/``ka#a``/``txa_drv`` group is AlwaysPowered: the
    bypass select, the keep-alive stub, and the ring-A driver reach
    only always-rail-powered no-Ioff parts (the §3 placement rule —
    the check verifies it where parts-DB data exists: F7's SWKA, the
    boundary tile's SWWD). No always-side driver exists in any latched
    state — the injector switches' B2 throws are NC and the DNP
    Schmitt's output reaches ``sel`` only through the fitted 0 Ω — so
    there is nothing to bound; the boundary tile's one driven corner
    (B5's defeat leg) carries its own board-level declaration
    (design/ci_board.py).
    """
    circuit.crossing(
        "opa_p", ring_back_feed("ring traffic and the injector shunts", 2, "Rar")
    )
    circuit.crossing(
        "opo",
        ring_back_feed(
            "ring traffic via the DNP hysteresis leg Rfb (audited as fitted)",
            2,
            "Rar + Rfb",
        ),
    )
    circuit.crossing("opa_p_b", ring_back_feed("ring-B traffic", 1, "Rbr"))
    circuit.crossing(
        "RX_B#a", ring_back_feed("ring-B traffic with the F4 break closed", 1, "Rbr")
    )
    circuit.crossing("txb_drv", ring_back_feed("ring-B traffic", 1, "Rbt"))
    circuit.crossing("swio", AlwaysPowered())
    circuit.crossing("debug_tx", AlwaysPowered())
    circuit.crossing("sel", AlwaysPowered())
    circuit.crossing("PHY1/sel_sw", AlwaysPowered())
    circuit.crossing("ka#a", AlwaysPowered())
    circuit.crossing("txa_drv", AlwaysPowered())


def _payload_pin(part: Part, function: str) -> Pin:
    """Resolve one payload function's U1 pin through the authoritative pin map."""
    pad = capture_pin_map().assignments[function]
    numbers = Ch32v003f4p6.pin_map[pad.name.lower()]
    return part.pin(numbers if isinstance(numbers, str) else numbers[0])


def _wire_debug_tx(circuit: Circuit) -> None:
    """Wire the PD5 debug TX pad: the §5 debug tree's leaf lands on it.

    The plain node leaves the pad unwired; the CI tiles drive the
    emit-and-forget debug UART on it (docs/scan-plane.md §5). Capture,
    not instrumentation — both sides of the equivalence proof carry it.
    """
    u1 = circuit.parts["U1"]
    circuit.connect(circuit.net("debug_tx"), _payload_pin(u1, "debug_tx"))


class InputNode(Node):
    """An input tile (1/3/5/7): the Node plus the pot and button payload."""

    def capture(self, circuit: Circuit) -> None:
        """Build the node, then the §6 input payload on PD6/PC5/PC6."""
        super().capture(circuit)
        _wire_debug_tx(circuit)
        _declare_tile_crossings(circuit)
        v3v3 = circuit.nets["3V3"]
        gnd = circuit.nets["GND"]
        u1 = circuit.parts["U1"]

        # Potentiometer (§6): 10 kΩ linear across the rail, wiper
        # through the 1 kΩ series R to PD6. H1's substitution mux cuts
        # ``pot_w`` at the wiper — bit 0 = human control.
        pot_w = circuit.net("pot_w")
        pot = circuit.net("pot")
        circuit.part("POT1", Rk09k(a=v3v3, wiper=pot_w, b=gnd), note="10k demo knob")
        circuit.part("RSP", R0603("1k", a=pot_w, b=pot), note="series R toward {U1}")
        circuit.connect(pot, _payload_pin(u1, "pot"))
        # The H1 override's crossing: the supervisor's PWM reaches the
        # gated tile's ADC pin through RPF (10 kΩ) and RSP (1 kΩ)
        # (instrumented-ci.md §6) — ≤ (3.3 - 0.6)/11 kΩ ≈ 0.25 mA. The
        # transform-created stub rides its forward-referenced name.
        pot_override = BackFeed(
            0.25,
            "instrumented-ci.md §6 (H1) — the POT_PWM override drives the "
            "gated tile's pot pin through RPF (10 kΩ) + RSP (1 kΩ): "
            "≤ (3.3 - 0.6) V / 11 kΩ ≈ 0.25 mA",
        )
        circuit.crossing("pot", pot_override)
        circuit.crossing("pot_w#b", pot_override)

        # Buttons (§6): tactile switch to GND, 10 kΩ pull-up, 1 kΩ
        # series to the pin. H2/H3's override FET shunts the raw node.
        for tag, function in (("A", "button_a"), ("B", "button_b")):
            raw = circuit.net(f"btn_{tag.lower()}")
            pin_net = circuit.net(function)
            circuit.part(f"SW{tag}", Ts1187a(a=raw, b=gnd), note="demo button, to GND")
            circuit.part(f"RP{tag}", R0603("10k", a=raw, b=v3v3), note="pull-up")
            circuit.part(
                f"RS{tag}", R0603("1k", a=raw, b=pin_net), note="series R toward {U1}"
            )
            circuit.connect(pin_net, _payload_pin(u1, function))


class OutputNode(Node):
    """An output tile (0/2/4/6): the Node plus the buzzer payload."""

    def capture(self, circuit: Circuit) -> None:
        """Build the node, then the §6 buzzer on PC4."""
        super().capture(circuit)
        _wire_debug_tx(circuit)
        _declare_tile_crossings(circuit)
        gnd = circuit.nets["GND"]
        u1 = circuit.parts["U1"]
        buzzer = circuit.net("buzzer")
        bz = circuit.net("bz")
        circuit.part("RBZ", R0603("470", a=buzzer, b=bz), note="piezo series R (§7)")
        circuit.part("BZ1", Pklcs1212e(pos=bz, neg=gnd), note="demo buzzer")
        circuit.connect(buzzer, _payload_pin(u1, "buzzer"))
