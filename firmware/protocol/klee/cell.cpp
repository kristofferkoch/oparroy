// KLEE proof: ratio-metric cell decode (firmware/protocol/cell.hpp).
// Proves the encode/decode round-trip and the tolerance claim of
// DESIGN.md §2 — any transmitter clock within ±25 % scales period and
// high-time together, and decode still recovers the bit — plus that no
// legal cell is ever misclassified illegal (no false containment).

#include "../cell.hpp"
#include "../bits.hpp"
#include "klee.hpp"

#include <cstdint>

extern "C" int klee_cell() {
    // Round-trip: a re-synthesized cell decodes back to its bit.
    KLEE_PROVE(oparroy::decode_cell(oparroy::encode_cell(oparroy::Bit::Zero)) ==
               oparroy::CellDecode::Zero);
    KLEE_PROVE(oparroy::decode_cell(oparroy::encode_cell(oparroy::Bit::One)) ==
               oparroy::CellDecode::One);

    // ±25 % clock error around the 60-tick nominal (DESIGN.md §2's
    // tolerance claim; HSI's ±2.2 % worst case sits an order inside).
    uint16_t period = 0;
    klee_make_symbolic(&period, sizeof period, "period");
    if (period < 45 || period > 75) {
        return 0;
    }
    const auto high0 = static_cast<uint16_t>(static_cast<uint32_t>(period) * 32 / 100);
    const auto high1 = static_cast<uint16_t>(static_cast<uint32_t>(period) * 64 / 100);
    KLEE_PROVE(oparroy::decode_cell(oparroy::CapturedCell{
                   .period_ticks = period, .high_ticks = high0}) == oparroy::CellDecode::Zero);
    KLEE_PROVE(oparroy::decode_cell(oparroy::CapturedCell{
                   .period_ticks = period, .high_ticks = high1}) == oparroy::CellDecode::One);

    // Every legal cell decodes to a bit, never Illegal.
    oparroy::CapturedCell cell{};
    klee_make_symbolic(&cell, sizeof cell, "cell");
    if (cell.period_ticks < oparroy::cell_period_min_ticks ||
        cell.period_ticks > oparroy::cell_period_max_ticks || cell.high_ticks > cell.period_ticks) {
        return 0;
    }
    KLEE_PROVE(oparroy::decode_cell(cell) != oparroy::CellDecode::Illegal);
    return 0;
}
