"""Ring-node pin map: the authoritative T9 pin table for the CH32V003.

Every function a node may carry — the §2/§3 ring PHY, the §4 watchdog
keep-alive, the §4.1 status LEDs, §6 debug, and the §5/§6 demonstrator
payload superset — requested by name, with pads bound below as
refinement data: 16 of 18 GPIO, PC1 and PC7 spare (§3's "~16-17 of 18"
budget, here verified by ``check_pin_map``). The one table feeds the
firmware header (``emit_pin_header`` → ``firmware/node/pins.hpp``) and
that budget check.

Usage:

    python -m design.node_pins            # check + C++ header on stdout
"""

import sys

from oparroy.dsl import (
    CH32V003F4P6,
    PinMap,
    check_pin_map,
    emit_pin_header,
    raise_on_errors,
)

#: Provenance written into the generated header.
SOURCE = "design/node_pins.py"
REGENERATE = "python -m design.node_pins > firmware/node/pins.hpp"
TITLE = (
    "oparroy ring-node pin map — CH32V003F4P6 (TSSOP-20). Function "
    "requests, pads bound late as refinement data (T9; DESIGN.md §5)."
)


def capture() -> PinMap:
    """Build the node pin map: requests by function, then the binding."""
    gpio = PinMap(CH32V003F4P6)

    # §2/§3 ring PHY: OPA comparator RX, TIM1 PWM TX. The RX capture is
    # the OPA→TIM2_CH1 internal route — no pad spent on it (§2). The
    # DMA constants are the RM Table 8-2 peripheral mapping (dma.md):
    # TIM2_CH1 → 5, TIM2_CH2 → 7 (PWM-input period+high), TIM1_CH1 →
    # 2, TIM1_CH3 → 6.
    gpio.request(
        "rx_a",
        uses=("opa_p",),
        const={"capture_dma": 5, "period_dma": 7},
        doc="ring A receive, OPA positive input; TIM2_CH1 capture is the "
        "internal route, no GPIO spent on the comparator output (§2).",
    )
    gpio.request(
        "rx_b",
        uses=("opa_p",),
        doc="ring B receive, OPA positive input; source select is "
        "firmware policy via OPA_PSEL (§3).",
    )
    gpio.request(
        "rx_threshold",
        uses=("opa_n",),
        doc="VDD/2 slice threshold on an OPA negative input (§2).",
    )
    gpio.request(
        "comp_out",
        uses=("opa_out",),
        doc="comparator-output tap for the §6 instrumented boundary node.",
    )
    gpio.request(
        "tx_a",
        uses=("tim1_ch",),
        const={"tx_dma": 2},
        doc="ring A transmit, TIM1 PWM + DMA compare streaming (§2).",
    )
    gpio.request(
        "tx_b",
        uses=("tim1_ch",),
        const={"tx_dma": 6},
        doc="ring B transmit, second TIM1 channel, identical compare values (§3).",
    )
    gpio.request(
        "tx_kill",
        uses=("tim1_bkin",),
        doc="TIM1 brake, the hardware TX-kill for the watchdog / "
        "babbling-idiot story (§2).",
    )

    # §4 watchdog and §4.1 serviceability LEDs.
    gpio.request(
        "keepalive",
        doc="20 kHz strobe holding the §4 charge-pump watchdog open.",
    )
    gpio.request(
        "led_working",
        doc="heartbeat LED; dark when firmware is hung or dead (§4.1).",
    )
    gpio.request(
        "led_segments",
        doc="link-status LEDs at both segment connectors, one antiparallel "
        "pair behind a shared series R on a single pin (§4.1): pin high "
        "lights upstream, pin low downstream, Hi-Z dark, a kHz toggle "
        "lights both at half brightness.",
    )

    # §6 debug: TX-only printf UART, collected by the supervisor.
    gpio.request(
        "debug_tx",
        uses=("usart_tx",),
        doc="debug UART TX, collected by the supervisor (§6).",
    )

    # §5/§6 demonstrator payload superset — a node carrying the full
    # mix, so the budget check covers the worst case. Buttons sit on FT
    # pads per the §7 terminal rule (5 V-tolerant for user-facing
    # terminals).
    gpio.request(
        "pot",
        uses=("adc",),
        doc="potentiometer wiper, the demonstrator analog input (§6).",
    )
    gpio.request(
        "buzzer",
        uses=("tim1_ch",),
        doc="buzzer PWM output (§5 I/O complement).",
    )
    gpio.request("button_a", doc="demo button input, FT pad (§5, §7 terminal rule).")
    gpio.request("button_b", doc="demo button input, FT pad (§5, §7 terminal rule).")

    # SDI debug: SWIO has no remap and re-using it bricks programming
    # access (quirks.md §Debug) — reserved, never firmware GPIO.
    gpio.reserve("PD1", reason="SWIO single-wire debug, no remap (quirks.md §Debug).")

    # The refinement data: one pad per function. Comments name the
    # binding reason — peripheral-forced pads cite the signal.
    gpio.bind(
        rx_a="PA2",  # OPP0 (opa.md)
        rx_b="PD7",  # OPP1; GPIO by default, NRST only via option byte
        rx_threshold="PA1",  # OPN0 — OPN1/PD0 stays free
        comp_out="PD4",  # OPO — the §2 feedback-R fallback stays DNP
        tx_a="PD2",  # TIM1_CH1
        tx_b="PC3",  # TIM1_CH3
        tx_kill="PC2",  # TIM1_BKIN, FT
        keepalive="PD3",
        led_working="PD0",
        led_segments="PC0",
        debug_tx="PD5",  # USART_TX
        pot="PD6",  # ADC_IN6; USART_RX unused (TX-only debug)
        buzzer="PC4",  # TIM1_CH4; MCO unused
        button_a="PC5",  # FT
        button_b="PC6",  # FT
    )
    # The spares: PC1 (FT, freed by the §4.1 antiparallel LED merge,
    # 2026-09-30) and PC7 (pin 17 — a test pad on the node board).
    return gpio


def main() -> None:
    """Check the pin map and emit the C++ header on stdout."""
    pin_map = capture()
    issues = check_pin_map(pin_map)
    for issue in issues:
        sys.stderr.write(f"{issue}\n")
    raise_on_errors(issues)
    sys.stdout.write(
        emit_pin_header(pin_map, source=SOURCE, regenerate=REGENERATE, title=TITLE)
    )


if __name__ == "__main__":
    main()
