// Translation unit for the header-only protocol core: keeps the
// GCC cross build (rv32ec) and clang-tidy compiling the same headers the
// KLEE bitcode targets include directly.

#include "../lib/span.hpp"
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
        for (uint16_t i = 0; i < frame_max_bits; ++i) {
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

} // namespace oparroy
