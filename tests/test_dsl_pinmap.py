"""Pin-map tests: model, budget check, header emitter."""

from __future__ import annotations

import pytest

from oparroy.dsl import (
    CH32V003F4P6,
    CheckError,
    Chip,
    DefinitionError,
    Issue,
    Pad,
    PinMap,
    Severity,
    check_pin_map,
    emit_pin_header,
)


def make_stub_chip() -> Chip:
    """Build a 4-pad stub: two GPIO on A, one on B (TIM1_CH3), one power."""
    return Chip(
        "STUB003",
        (
            Pad("PA0", 1, "A", 0, {"adc": 0, "opa_p": 0}, frozenset()),
            Pad("PA1", 2, "A", 1, {"usart_tx": None}, frozenset({"ft"})),
            Pad("PB0", 3, "B", 0, {"tim1_ch": 3}, frozenset()),
            Pad("VSS", 4, None, None),
        ),
        {"A": 0x40010800, "B": 0x40011000},
    )


def make_stub_map() -> PinMap:
    gpio = PinMap(make_stub_chip())
    gpio.request("pot", uses=("adc",), doc="analog input.")
    gpio.request("debug_tx", uses=("usart_tx",))
    return gpio


def emit(gpio: PinMap) -> str:
    return emit_pin_header(gpio, source="test", regenerate="test", title="test map.")


def messages(issues: list[Issue], severity: Severity) -> list[str]:
    return [i.message for i in issues if i.severity is severity]


def test_chip_gpio_count_excludes_power_pads() -> None:
    stub_gpio = 3
    ch32v003_gpio = 18
    assert make_stub_chip().gpio_count == stub_gpio
    assert CH32V003F4P6.gpio_count == ch32v003_gpio


def test_chip_pad_lookup_rejects_unknown() -> None:
    with pytest.raises(DefinitionError, match="has no pad 'PB9'"):
        make_stub_chip().pad("PB9")


def test_request_rejects_non_identifier_names() -> None:
    gpio = PinMap(make_stub_chip())
    with pytest.raises(DefinitionError, match="not a snake_case"):
        gpio.request("KeepAlive")


def test_request_rejects_duplicates() -> None:
    gpio = make_stub_map()
    with pytest.raises(DefinitionError, match="duplicate pin request 'pot'"):
        gpio.request("pot")


def test_request_rejects_const_colliding_with_used_signal() -> None:
    gpio = PinMap(make_stub_chip())
    with pytest.raises(DefinitionError, match="collide with used signals"):
        gpio.request("pot", uses=("adc",), const={"adc": 0})


def test_reserve_rejects_power_pads_and_duplicates() -> None:
    gpio = PinMap(make_stub_chip())
    with pytest.raises(DefinitionError, match="power pad"):
        gpio.reserve("VSS", reason="nope")
    gpio.reserve("PA0", reason="taken")
    with pytest.raises(DefinitionError, match="already reserved"):
        gpio.reserve("PA0", reason="again")


def test_bind_rejects_unknown_functions_pads_and_rebinding() -> None:
    gpio = make_stub_map()
    with pytest.raises(DefinitionError, match="no pin request named 'led'"):
        gpio.bind(led="PA0")
    with pytest.raises(DefinitionError, match="has no pad 'PA9'"):
        gpio.bind(pot="PA9")
    gpio.bind(pot="PA0")
    with pytest.raises(DefinitionError, match="'pot' is already bound"):
        gpio.bind(pot="PA1")


def test_unbound_request_warns_and_counts_in_budget() -> None:
    issues = check_pin_map(make_stub_map())
    assert messages(issues, Severity.WARNING) == [
        "pin function 'pot' is not bound to a pad",
        "pin function 'debug_tx' is not bound to a pad",
    ]
    assert messages(issues, Severity.ERROR) == []


def test_power_pad_binding_errors() -> None:
    gpio = make_stub_map()
    gpio.bind(pot="PA0", debug_tx="PA1")
    gpio.request("led")
    gpio.bind(led="VSS")
    assert messages(check_pin_map(gpio), Severity.ERROR) == [
        "led is bound to VSS (pin 4), a power pad"
    ]


def test_reserved_pad_binding_errors() -> None:
    gpio = make_stub_map()
    gpio.reserve("PA0", reason="SWIO-class debug pin")
    gpio.bind(pot="PA0", debug_tx="PA1")
    assert messages(check_pin_map(gpio), Severity.ERROR) == [
        "pot is bound to PA0, reserved: SWIO-class debug pin"
    ]


def test_missing_signal_on_bound_pad_errors() -> None:
    gpio = make_stub_map()
    gpio.bind(pot="PA1", debug_tx="PA1")
    assert messages(check_pin_map(gpio), Severity.ERROR) == [
        "PA1 (pin 2) has no adc function, requested by pot",
        "pot and debug_tx are both bound to PA1",
    ]


def test_two_functions_on_one_pad_error() -> None:
    gpio = make_stub_map()
    gpio.bind(pot="PA0", debug_tx="PA0")
    assert messages(check_pin_map(gpio), Severity.ERROR) == [
        "PA0 (pin 1) has no usart_tx function, requested by debug_tx",
        "pot and debug_tx are both bound to PA0",
    ]


def test_budget_exceeded_errors() -> None:
    gpio = make_stub_map()
    gpio.request("led")
    gpio.reserve("PA0", reason="taken")
    assert messages(check_pin_map(gpio), Severity.ERROR) == [
        "GPIO budget exceeded: 4 of 3 pads used (STUB003)"
    ]


def test_emit_refuses_unbound_requests() -> None:
    gpio = make_stub_map()
    gpio.bind(pot="PA0")
    with pytest.raises(DefinitionError, match="unbound pin functions: debug_tx"):
        emit(gpio)


def test_emit_refuses_a_map_with_check_errors() -> None:
    gpio = make_stub_map()
    gpio.bind(pot="PA0", debug_tx="PA0")
    with pytest.raises(CheckError, match="both bound to PA0"):
        emit(gpio)


def test_header_carries_pads_and_channel_constants() -> None:
    gpio = make_stub_map()
    gpio.bind(pot="PA0", debug_tx="PA1")
    header = emit(gpio)
    assert "inline constexpr uint32_t gpio_a_base = 0x40010800;" in header
    # Only port A is used — B's base is not emitted.
    assert "gpio_b_base" not in header
    assert "// pot — analog input." in header
    pad_line = (
        "inline constexpr Pad pot"
        "{.port_base = gpio_a_base, .bit = 0, .package_pin = 1};"
    )
    assert pad_line in header
    # adc is channel-valued: emitted. usart_tx is presence-only: not.
    assert "inline constexpr uint8_t pot_adc = 0;" in header
    assert "debug_tx_usart_tx" not in header
    assert "namespace pins {" in header
    assert header.endswith("} // namespace pins\n")


def test_header_emits_capture_supplied_const_entries() -> None:
    gpio = PinMap(make_stub_chip())
    gpio.request("pwm", uses=("tim1_ch",), const={"tx_dma": 6})
    gpio.bind(pwm="PB0")
    header = emit(gpio)
    assert "inline constexpr uint8_t pwm_tim1_ch = 3;" in header
    assert "inline constexpr uint8_t pwm_tx_dma = 6;" in header


def test_header_documents_reservations_and_spares() -> None:
    gpio = make_stub_map()
    gpio.reserve("PB0", reason="SWIO-class debug pin")
    gpio.bind(pot="PA0", debug_tx="PA1")
    header = emit(gpio)
    assert "// 3 of 3 GPIO assigned; no spare pads." in header
    assert "// Reserved — counted in the GPIO budget, never firmware GPIO:" in header
    assert "//   PB0 (pin 3): SWIO-class debug pin" in header


def test_header_names_the_spare_pad() -> None:
    gpio = make_stub_map()
    gpio.bind(pot="PA0", debug_tx="PA1")
    header = emit(gpio)
    assert "// 2 of 3 GPIO assigned; spare: PB0 (pin 3)." in header


def test_header_is_byte_identical_across_runs() -> None:
    assert emit(make_stub_map_fully_bound()) == emit(make_stub_map_fully_bound())


def make_stub_map_fully_bound() -> PinMap:
    gpio = make_stub_map()
    gpio.bind(pot="PA0", debug_tx="PA1")
    return gpio


def test_ch32v003_pad_table_is_sorted_by_package_pin() -> None:
    pins = [pad.pin for pad in CH32V003F4P6.gpio_pads]
    assert pins == sorted(pins)
    assert len(pins) == 20 - 2  # TSSOP-20 minus VSS/VDD
