"""Supervisor pin map: the authoritative pin table for the RP2040.

Every function the CI-board supervisor carries — the §6 PIO SWIO flash
channel, the instrumented boundary node's four taps, the §6 debug
transport's tree root, and the scan-plane control chain — requested by
name, with pads bound below as refinement data: 11 of 30 GPIO spent,
verified by ``check_pin_map``. The one table feeds the firmware headers
(``emit_pin_header`` → ``firmware/supervisor/pins.hpp``,
``emit_pin_module`` → ``firmware/supervisor/pins.py`` for the
MicroPython bringup stack) and that budget check.

Usage:

    python -m design.supervisor_pins         # check + C++ header on stdout
    python -m design.supervisor_pins --py    # check + MicroPython module
"""

import sys

from oparroy.dsl import (
    RP2040,
    PinMap,
    check_pin_map,
    emit_pin_header,
    emit_pin_module,
    raise_on_errors,
)

#: Provenance written into the generated headers.
SOURCE = "design/supervisor_pins.py"
REGENERATE = "python -m design.supervisor_pins > firmware/supervisor/pins.hpp"
REGENERATE_PY = "python -m design.supervisor_pins --py > firmware/supervisor/pins.py"
TITLE = (
    "oparroy supervisor pin map — RP2040 (QFN-56). Function requests, "
    "pads bound late as refinement data (DESIGN.md §5/§6)."
)


def capture() -> PinMap:
    """Build the supervisor pin map: requests by function, then the binding."""
    gpio = PinMap(RP2040)

    # §6 instrumented boundary node: four taps on consecutive GPIO so
    # one PIO `in` instruction samples the set per clock (8 ns at the
    # 125 MHz sysclock). No series resistors on the taps — stimulus
    # drives against the segment's existing 470 Ω
    # (docs/instrumented-ci.md).
    gpio.request(
        "tap_rx",
        doc="boundary node's ring RX tap, PIO logic-analyzer input and "
        "glitch-stimulus output (§6).",
    )
    gpio.request(
        "tap_tx",
        doc="boundary node's TX output, post-injector (§6).",
    )
    gpio.request(
        "tap_comp",
        doc="boundary node's comparator-output tap — observation stays "
        "truthful when the node's MCU misbehaves (§6).",
    )
    gpio.request(
        "tap_led",
        doc="boundary node's working-LED tap (§6).",
    )

    # §6 CI flash fan-out: one PIO SWIO channel through the 3157 tree
    # to the selected node. Adjacent to the taps so one PIO program can
    # cover the set. The tree selects ride the scan chain (SWIO_A0-A2,
    # docs/scan-plane.md §5) — no GPIO spent on them.
    gpio.request(
        "swio",
        doc="PIO SWIO flash channel to the tree root; pipelined "
        "round-robin flashing of all 8 nodes (§6).",
    )

    # Scan control/observe plane (docs/scan-plane.md §6): five pins for
    # the whole board. SRCLK/SDO/SDI bind to SPI0-capable pads so the
    # hardware-SPI option stays open; the plane is trivially PIO-able
    # either way — the firmware picks.
    gpio.request(
        "srclk",
        uses=("spi0_sck",),
        doc="scan-chain shift clock, all 12 stages (scan-plane §6).",
    )
    gpio.request(
        "sdo",
        uses=("spi0_tx",),
        doc="scan-chain data out, SER of AUX0 (scan-plane §6).",
    )
    gpio.request(
        "sdi",
        uses=("spi0_rx",),
        doc="scan-chain data in, QH of OBS1 (scan-plane §6).",
    )
    gpio.request(
        "commit",
        doc="scan-chain commit: RCLK on the 595s, SH//LD on the 165s; "
        "idle high, low pulse ends a transaction (scan-plane §1).",
    )
    gpio.request(
        "oe_n",
        doc="595 output enable, open-drain drive: 47 kΩ pull-up holds "
        "the chain Hi-Z until the zero word is latched, then driven "
        "low (scan-plane §4).",
    )

    # §6 runtime debug transport: the root of the second 8:1 tree
    # ganged to the flash tree's SWIO selects (docs/scan-plane.md §5) —
    # a PIO UART RX hearing whichever tile the selects point at.
    gpio.request(
        "dbg_rx",
        doc="debug UART return: root of the 8:1 tree ganged to the "
        "flash tree's selects, leaves on the tiles' PD5 debug_tx "
        "(§6, scan-plane §5).",
    )

    # The refinement data: one pad per function. Comments name the
    # binding reason — peripheral-forced pads cite the signal.
    gpio.bind(
        tap_rx="GPIO8",  # taps start here: GPIO8-11 consecutive
        tap_tx="GPIO9",
        tap_comp="GPIO10",
        tap_led="GPIO11",
        swio="GPIO12",  # adjacent to the taps — one PIO covers GPIO8-12
        dbg_rx="GPIO13",  # extends the PIO region to GPIO8-13
        srclk="GPIO18",  # SPI0 SCK
        sdo="GPIO19",  # SPI0 TX
        sdi="GPIO20",  # SPI0 RX
        commit="GPIO21",
        oe_n="GPIO22",
    )
    # The spares: GPIO0-7 (the reclaimed debug-transport reservation —
    # settled, DESIGN.md §6), GPIO14-17 and GPIO23-29 (19 of 30).
    return gpio


def main(argv: list[str]) -> None:
    """Check the pin map and emit the C++ header (or ``--py`` module)."""
    pin_map = capture()
    issues = check_pin_map(pin_map)
    for issue in issues:
        sys.stderr.write(f"{issue}\n")
    raise_on_errors(issues)
    if argv[1:] == ["--py"]:
        sys.stdout.write(
            emit_pin_module(
                pin_map, source=SOURCE, regenerate=REGENERATE_PY, title=TITLE
            )
        )
    else:
        sys.stdout.write(
            emit_pin_header(pin_map, source=SOURCE, regenerate=REGENERATE, title=TITLE)
        )


if __name__ == "__main__":
    main(sys.argv)
