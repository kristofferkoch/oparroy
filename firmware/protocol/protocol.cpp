// Translation unit for the header-only protocol core: keeps the
// GCC cross build (rv32ec) and clang-tidy compiling the same headers the
// KLEE bitcode targets include directly.

#include "../lib/error_or.hpp"
#include "../lib/range.hpp"
#include "../lib/span.hpp"
#include "../lib/static_vector.hpp"
#include "bits.hpp"
#include "cell.hpp"
#include "node.hpp"

#include <cstdint>

namespace oparroy {

static_assert(decode_cell(encode_cell(Bit::Zero)) == CellDecode::Zero);
static_assert(decode_cell(encode_cell(Bit::One)) == CellDecode::One);
static_assert(decode_cell(CapturedCell{.period_ticks = 42, .high_ticks = 19}) ==
              CellDecode::Illegal);
static_assert(decode_cell(CapturedCell{.period_ticks = 78, .high_ticks = 38}) ==
              CellDecode::Illegal);
static_assert(decode_cell(CapturedCell{.period_ticks = 60, .high_ticks = 61}) ==
              CellDecode::Illegal);

constexpr lib::Span<const uint8_t> empty_bytes{nullptr, 0};
static_assert(!valid(BitSlice{.bytes = empty_bytes, .bit_count = 1}));
static_assert(valid(BitSlice{.bytes = empty_bytes, .bit_count = 0}));
static_assert(Node::config_valid(NodeConfig{.slot_index = 0, .slot_bits = 8},
                                 BitSlice{.bytes = lib::Span<const uint8_t>{nullptr, 1},
                                          .bit_count = 8}));
static_assert(!Node::config_valid(NodeConfig{.slot_index = 0, .slot_bits = 0},
                                  BitSlice{.bytes = lib::Span<const uint8_t>{nullptr, 1},
                                           .bit_count = 8}));
static_assert(!Node::config_valid(NodeConfig{.slot_index = 0, .slot_bits = 8},
                                  BitSlice{.bytes = empty_bytes, .bit_count = 8}));

// Over-long frame containment (node.hpp, frame_max_bits): a legal
// stream past the cap is contained like an illegal cell — Mute until
// the next break, which resyncs as always.
namespace {

    constexpr bool frame_cap_mutes() {
        const uint8_t telemetry_byte = 0;
        Node node{NodeConfig{.slot_index = 60000, .slot_bits = 1},
                  BitSlice{.bytes = lib::Span<const uint8_t>{&telemetry_byte, 1}, .bit_count = 8}};
        if (node.on_break() != TxAction::Idle) {
            return false;
        }
        for ([[maybe_unused]] const uint16_t i : lib::irange(frame_max_bits)) {
            if (node.on_bit(Bit::One) == TxAction::Idle) {
                return false;
            }
        }
        if (node.on_bit(Bit::One) != TxAction::Idle || node.state() != NodeState::Mute) {
            return false;
        }
        node.on_break();
        return node.on_bit(Bit::One) == TxAction::EmitOne;
    }

} // namespace

static_assert(frame_cap_mutes());

// Foundation-library cells (firmware/lib/range.hpp, static_vector.hpp):
// constexpr-proved here, the same TU that hosts Span's asserts.
namespace {

    constexpr int sum_of(lib::IntRange<int> range) {
        int sum = 0;
        for (const int i : range) {
            sum += i;
        }
        return sum;
    }

    // Overflow canary: a uint8_t range near the type max counts exactly
    // its half-open length — ++ past end is unreachable by construction
    // (range.hpp).
    constexpr uint32_t count_of(lib::IntRange<uint8_t> range) {
        uint32_t count = 0;
        for ([[maybe_unused]] const uint8_t i : range) {
            ++count;
        }
        return count;
    }

    constexpr bool static_vector_behaves() {
        lib::StaticVector<uint8_t, 3> vec;
        if (!vec.is_empty() || vec.size() != 0 || vec.capacity() != 3) {
            return false;
        }
        for (const uint8_t i : lib::irange(static_cast<uint8_t>(vec.capacity()))) {
            vec.push_back(i);
        }
        // Bounded: growth past capacity asks, and is refused.
        const lib::ErrorOr<void> refused = vec.try_push_back(9);
        if (!refused.is_error() || refused.error() != lib::Error::OutOfCapacity ||
            vec.size() != vec.capacity()) {
            return false;
        }
        uint32_t sum = 0;
        for (const uint8_t value : vec) {
            sum += value;
        }
        if (sum != 0 + 1 + 2 || vec[2] != 2) {
            return false;
        }
        vec.clear();
        return vec.is_empty() && vec.size() == 0;
    }

} // namespace

static_assert(sum_of(lib::irange(5)) == 10);
static_assert(sum_of(lib::irange(3, 7)) == 18);
// Inverted and negative ranges clamp to empty — a zero-trip loop, never
// UB (range.hpp).
static_assert(sum_of(lib::irange(7, 3)) == 0);
static_assert(sum_of(lib::irange(-4)) == 0);
static_assert(count_of(lib::irange(uint8_t{200})) == 200);
static_assert(static_vector_behaves());

} // namespace oparroy
