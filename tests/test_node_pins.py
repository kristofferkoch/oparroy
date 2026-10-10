"""Node pin-map capture tests — the CH32V003 pin table end to end.

The golden header at tests/golden/node-pins.hpp is the proof artifact,
byte-identical to the firmware-consumed copy at firmware/node/pins.hpp;
regenerate both from the dev shell with:

    python -m design.node_pins > tests/golden/node-pins.hpp
    python -m design.node_pins > firmware/node/pins.hpp
"""

from pathlib import Path

from design.node_pins import REGENERATE, SOURCE, TITLE, capture
from oparroy.dsl import Severity, check_pin_map, emit_pin_header

GOLDEN = Path(__file__).parent / "golden" / "node-pins.hpp"
FIRMWARE_COPY = Path(__file__).parent.parent / "firmware" / "node" / "pins.hpp"

# 15 function requests + the SWIO reservation = 16 of 18 GPIO (§3's
# "~16-17 of 18" budget); PC1 (freed by the §4.1 LED merge) and PC7
# (a test pad on the node board) are the spares.
REQUEST_COUNT = 15
USED_COUNT = 16
GPIO_COUNT = 18


def emit() -> str:
    return emit_pin_header(capture(), source=SOURCE, regenerate=REGENERATE, title=TITLE)


def test_capture_checks_clean() -> None:
    assert check_pin_map(capture()) == []


def test_budget_lands_at_16_of_18() -> None:
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
    assert spare == {"PC1", "PC7"}


def test_peripheral_forced_bindings() -> None:
    pads = {name: pad.name for name, pad in capture().assignments.items()}
    # OPA routing (opa.md) and the §2/§3 timer pins are not free choices.
    assert pads["rx_a"] == "PA2"  # OPP0
    assert pads["rx_b"] == "PD7"  # OPP1
    assert pads["rx_threshold"] == "PA1"  # OPN0
    assert pads["comp_out"] == "PD4"  # OPO
    assert pads["tx_a"] == "PD2"  # TIM1_CH1
    assert pads["tx_b"] == "PC3"  # TIM1_CH3
    assert pads["tx_kill"] == "PC2"  # TIM1_BKIN
    assert pads["debug_tx"] == "PD5"  # USART_TX


def test_swio_reserved_out_of_firmware_reach() -> None:
    pin_map = capture()
    assert pin_map.reservations == {
        "PD1": "SWIO single-wire debug, no remap (quirks.md §Debug)."
    }
    assert "PD1" not in {pad.name for pad in pin_map.assignments.values()}


def test_header_matches_golden() -> None:
    assert emit() == GOLDEN.read_text(encoding="utf-8")


def test_header_matches_firmware_copy() -> None:
    assert emit() == FIRMWARE_COPY.read_text(encoding="utf-8")


def test_header_byte_identical_across_runs() -> None:
    assert emit() == emit()


def test_header_lines_fit_clang_format_columns() -> None:
    # .clang-format's ColumnLimit — LLVM reflows comments, so an
    # over-long line would make the golden clang-format-unstable.
    column_limit = 100
    assert all(len(line) <= column_limit for line in emit().splitlines())


def test_no_warnings_means_no_unbound_requests() -> None:
    warnings = [i for i in check_pin_map(capture()) if i.severity is Severity.WARNING]
    assert warnings == []
