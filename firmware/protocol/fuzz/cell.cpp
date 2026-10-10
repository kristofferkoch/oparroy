// Fuzz: ratio-metric cell decode (firmware/protocol/cell.hpp) — the
// sampling counterpart to klee/cell.cpp's proof. Sanitizers own UB; the
// invariants check the legality window against the spec (DESIGN.md §2:
// 0.9–1.6 µs period, high ≤ period), the ±25 % tolerance claim, and the
// encode/decode round-trip.

#include "../cell.hpp"
#include "../../lib/span.hpp"
#include "../bits.hpp"
#include "fuzz.hpp"

#include <cstddef>
#include <cstdint>

// Engine-fixed ABI name (code-std-cpp.md#1-language-and-toolchain's extern-C entry points); the
// snake_case rule yields to the fuzzer's entry-point contract.
// NOLINTNEXTLINE(readability-identifier-naming)
extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    oparroy::fuzz::Cursor cursor{lib::Span<const uint8_t>{data, size}};
    while (cursor.remaining() > 0) {
        const oparroy::CapturedCell cell{.period_ticks = cursor.take_u16(),
                                         .high_ticks = cursor.take_u16()};
        const oparroy::CellDecode decode = oparroy::decode_cell(cell);

        // The legality window, exactly as spec'd: inside it a cell
        // always decodes to a bit (no false containment), outside it
        // always Illegal.
        const bool legal = cell.period_ticks >= oparroy::cell_period_min_ticks &&
                           cell.period_ticks <= oparroy::cell_period_max_ticks &&
                           cell.high_ticks <= cell.period_ticks;
        FUZZ_PROVE((decode == oparroy::CellDecode::Illegal) == !legal);

        // ±25 % clock error around the 60-tick nominal scales period
        // and high-time together; decode still recovers the bit
        // (DESIGN.md §2's tolerance claim).
        if (cell.period_ticks >= 45 && cell.period_ticks <= 75) {
            const auto high0 =
                static_cast<uint16_t>(static_cast<uint32_t>(cell.period_ticks) * 32 / 100);
            const auto high1 =
                static_cast<uint16_t>(static_cast<uint32_t>(cell.period_ticks) * 64 / 100);
            FUZZ_PROVE(oparroy::decode_cell(oparroy::CapturedCell{.period_ticks = cell.period_ticks,
                                                                  .high_ticks = high0}) ==
                       oparroy::CellDecode::Zero);
            FUZZ_PROVE(oparroy::decode_cell(oparroy::CapturedCell{.period_ticks = cell.period_ticks,
                                                                  .high_ticks = high1}) ==
                       oparroy::CellDecode::One);
        }
    }

    // Round-trip: a re-synthesized cell decodes back to its bit.
    FUZZ_PROVE(oparroy::decode_cell(oparroy::encode_cell(oparroy::Bit::Zero)) ==
               oparroy::CellDecode::Zero);
    FUZZ_PROVE(oparroy::decode_cell(oparroy::encode_cell(oparroy::Bit::One)) ==
               oparroy::CellDecode::One);
    return 0;
}
