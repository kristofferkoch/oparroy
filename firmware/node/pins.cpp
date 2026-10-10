// Compile proof for the DSL-generated pin map: pins.hpp must build
// under the freestanding rule set on every toolchain in the matrix
// (host clang, rv32ec GCC). The static_asserts pin the load-bearing
// facts so a garbled regeneration can't pass vacuously — content drift
// is caught byte-exact by tests/golden/node-pins.hpp.
#include "pins.hpp"

// Peripheral-forced pads (datasheets/CH32V003/notes/opa.md, gpio-pinout.md).
static_assert(pins::rx_a.port_base == pins::gpio_a_base && pins::rx_a.bit == 2);
static_assert(pins::rx_a.package_pin == 6);
static_assert(pins::rx_b.port_base == pins::gpio_d_base && pins::rx_b.bit == 7);
static_assert(pins::rx_threshold.port_base == pins::gpio_a_base && pins::rx_threshold.bit == 1);

// OPA input-select values (R32_EXTEN_CTR OPA_PSEL/OPA_NSEL, RM §17.2).
static_assert(pins::rx_a_opa_p == 0);
static_assert(pins::rx_b_opa_p == 1);
static_assert(pins::rx_threshold_opa_n == 0);

// Timer channels and DMA routing (RM §8.2.3 Table 8-2).
static_assert(pins::tx_a_tim1_ch == 1 && pins::tx_a_tx_dma == 2);
static_assert(pins::tx_b_tim1_ch == 3 && pins::tx_b_tx_dma == 6);
static_assert(pins::buzzer_tim1_ch == 4);
static_assert(pins::rx_a_capture_dma == 5 && pins::rx_a_period_dma == 7);
static_assert(pins::pot_adc == 6);

// Plain GPIO: the §4 watchdog strobe.
static_assert(pins::keepalive.port_base == pins::gpio_d_base && pins::keepalive.bit == 3);
static_assert(pins::keepalive.package_pin == 20);

// The §4.1 antiparallel connector-LED pair on PC0 (2026-09-30 merge —
// one pin, high = upstream / low = downstream / Hi-Z = dark).
static_assert(pins::led_segments.port_base == pins::gpio_c_base && pins::led_segments.bit == 0);
static_assert(pins::led_segments.package_pin == 10);
