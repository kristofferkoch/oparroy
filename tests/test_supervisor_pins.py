"""Supervisor pin-map capture tests — the RP2040 pin table end to end.

The golden headers at tests/golden/supervisor-pins.hpp and
tests/golden/supervisor-pins.py are the proof artifacts, byte-identical
to the firmware-consumed copies at firmware/supervisor/pins.hpp and
firmware/supervisor/pins.py; regenerate all four from the dev shell
with:

    python -m design.supervisor_pins > tests/golden/supervisor-pins.hpp
    python -m design.supervisor_pins > firmware/supervisor/pins.hpp
    python -m design.supervisor_pins --py > tests/golden/supervisor-pins.py
    python -m design.supervisor_pins --py > firmware/supervisor/pins.py
"""

from pathlib import Path

from design.supervisor_pins import (
    REGENERATE,
    REGENERATE_PY,
    SOURCE,
    TITLE,
    capture,
)
from oparroy.dsl import Severity, check_pin_map, emit_pin_header, emit_pin_module

GOLDEN_HPP = Path(__file__).parent / "golden" / "supervisor-pins.hpp"
GOLDEN_PY = Path(__file__).parent / "golden" / "supervisor-pins.py"
FIRMWARE_HPP = Path(__file__).parent.parent / "firmware" / "supervisor" / "pins.hpp"
FIRMWARE_PY = Path(__file__).parent.parent / "firmware" / "supervisor" / "pins.py"

# 10 function requests + the debug-transport reservation (DESIGN.md
# §9; 8 consecutive GPIOs) = 18 of 30 GPIO spent; GPIO13..17 and
# GPIO23..29 (12 of 30) are the spares.
REQUEST_COUNT = 10
USED_COUNT = 18
GPIO_COUNT = 30

DBG_RESERVATION = (
    "debug transport (DESIGN.md §9) reservation: per-node UART worst "
    "case (8 consecutive for one-PIO wide sample)."
)


def emit_hpp() -> str:
    return emit_pin_header(capture(), source=SOURCE, regenerate=REGENERATE, title=TITLE)


def emit_py() -> str:
    return emit_pin_module(
        capture(), source=SOURCE, regenerate=REGENERATE_PY, title=TITLE
    )


def test_capture_checks_clean() -> None:
    assert check_pin_map(capture()) == []


def test_budget_lands_at_18_of_30() -> None:
    pin_map = capture()
    assert len(pin_map.requests) == REQUEST_COUNT
    used = len(pin_map.requests) + len(pin_map.reservations)
    assert used == USED_COUNT
    assert pin_map.chip.gpio_count == GPIO_COUNT
    bound = {pad.name for pad in pin_map.assignments.values()}
    spare = {
        pad.name
        for pad in pin_map.chip.gpio_pads
        if pad.name not in bound and pad.name not in pin_map.reservations
    }
    assert spare == {
        "GPIO13",
        "GPIO14",
        "GPIO15",
        "GPIO16",
        "GPIO17",
        "GPIO23",
        "GPIO24",
        "GPIO25",
        "GPIO26",
        "GPIO27",
        "GPIO28",
        "GPIO29",
    }


def test_peripheral_forced_bindings() -> None:
    pads = {name: pad.name for name, pad in capture().assignments.items()}
    # The scan chain rides the SPI0-capable pads so the hardware-SPI
    # option stays open; the rest of the binding follows the pin map's
    # one-PIO-region layout (GPIO8..12 for taps + SWIO).
    assert pads["srclk"] == "GPIO18"  # SPI0 SCK
    assert pads["sdo"] == "GPIO19"  # SPI0 TX
    assert pads["sdi"] == "GPIO20"  # SPI0 RX
    assert pads["tap_rx"] == "GPIO8"
    assert pads["tap_tx"] == "GPIO9"
    assert pads["tap_comp"] == "GPIO10"
    assert pads["tap_led"] == "GPIO11"
    assert pads["swio"] == "GPIO12"
    assert pads["commit"] == "GPIO21"
    assert pads["oe_n"] == "GPIO22"


def test_debug_transport_reservation() -> None:
    pin_map = capture()
    assert pin_map.reservations == {f"GPIO{n}": DBG_RESERVATION for n in range(8)}
    assert not {pad.name for pad in pin_map.assignments.values()} & set(
        pin_map.reservations
    )


def test_hpp_matches_golden() -> None:
    assert emit_hpp() == GOLDEN_HPP.read_text(encoding="utf-8")


def test_py_matches_golden() -> None:
    assert emit_py() == GOLDEN_PY.read_text(encoding="utf-8")


def test_hpp_matches_firmware_copy() -> None:
    assert emit_hpp() == FIRMWARE_HPP.read_text(encoding="utf-8")


def test_py_matches_firmware_copy() -> None:
    assert emit_py() == FIRMWARE_PY.read_text(encoding="utf-8")


def test_hpp_byte_identical_across_runs() -> None:
    assert emit_hpp() == emit_hpp()


def test_py_byte_identical_across_runs() -> None:
    assert emit_py() == emit_py()


def test_hpp_lines_fit_clang_format_columns() -> None:
    # .clang-format's ColumnLimit — LLVM reflows comments, so an
    # over-long line would make the golden clang-format-unstable.
    column_limit = 100
    assert all(len(line) <= column_limit for line in emit_hpp().splitlines())


def test_py_lines_fit_ruff_columns() -> None:
    column_limit = 100
    assert all(len(line) <= column_limit for line in emit_py().splitlines())


def test_no_warnings_means_no_unbound_requests() -> None:
    warnings = [i for i in check_pin_map(capture()) if i.severity is Severity.WARNING]
    assert warnings == []
