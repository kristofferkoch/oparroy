#pragma once

// Duty-coded PWM cell decode/encode (DESIGN.md §2 — the settled line
// coding: ratio-metric decode, 800 kbit/s anchor).

#include "bits.hpp"

#include <cstdint>

namespace oparroy {

// Timing in 48 MHz timer ticks (phy-analysis §1): one 800 kbit/s cell
// is 1.25 µs = 60 ticks; capture resolution 20.8 ns.
inline constexpr uint16_t cell_period_nominal_ticks = 60;
// T0H ≈ 0.40 µs (ratio 0.32), T1H ≈ 0.80 µs (ratio 0.64).
inline constexpr uint16_t t0h_ticks = 19;
inline constexpr uint16_t t1h_ticks = 38;
// Legal cell-period window 0.9–1.6 µs, rounded outward to whole ticks.
// A cell outside it is illegal: stop regenerating, force the line idle
// (the containment rule, DESIGN.md §2).
inline constexpr uint16_t cell_period_min_ticks = 43;
inline constexpr uint16_t cell_period_max_ticks = 77;
// Frame/latch marker: line low ≥ 50 µs — the vsync break (DESIGN.md §2).
inline constexpr uint16_t break_min_ticks = 2400;

// One captured cell as the RX path delivers it: TIM2 PWM-input mode
// captures per-bit period and high-time, DMA streams the pairs.
struct CapturedCell {
    uint16_t period_ticks;
    uint16_t high_ticks;
};

enum class CellDecode : uint8_t {
    Zero,
    One,
    Illegal,
};

// Ratio-metric decode (DESIGN.md §2): the spec is high-time/period
// against the cell midpoint, not absolute times — HSI-only nodes (±2.2 %
// worst case) sit an order of magnitude inside the ±25 % budget.
[[nodiscard]] constexpr CellDecode decode_cell(CapturedCell cell) {
    if (cell.period_ticks < cell_period_min_ticks || cell.period_ticks > cell_period_max_ticks) {
        return CellDecode::Illegal;
    }
    if (cell.high_ticks > cell.period_ticks) {
        return CellDecode::Illegal;
    }
    return 2 * static_cast<uint32_t>(cell.high_ticks) < cell.period_ticks ? CellDecode::Zero
                                                                          : CellDecode::One;
}

// TX re-synthesis: every node snaps to nominal (per-bit cut-through
// re-timing, DESIGN.md §2) — decode jitter is per-hop, never cumulative.
[[nodiscard]] constexpr CapturedCell encode_cell(Bit bit) {
    return CapturedCell{.period_ticks = cell_period_nominal_ticks,
                        .high_ticks = bit == Bit::One ? t1h_ticks : t0h_ticks};
}

} // namespace oparroy
