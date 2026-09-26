// KLEE proof: ENUM stamping (DESIGN.md §2). The ENUM frame is pre-sized,
// so stamping is a slot rewrite, never an insertion — the off-by-one
// surface of the slot-boundary bit counter. A 2-node circulation must
// stamp each slot with exactly that node's bits and touch nothing else.

#include "../../lib/range.hpp"
#include "../../lib/span.hpp"
#include "../bits.hpp"
#include "../node.hpp"
#include "klee.hpp"

#include <cstdint>

namespace {

constexpr uint16_t slot_bits = 8;

[[nodiscard]] constexpr oparroy::Bit emitted_bit(oparroy::TxAction action) {
    return action == oparroy::TxAction::EmitOne ? oparroy::Bit::One : oparroy::Bit::Zero;
}

// One frame bit through both nodes, proving both hop-level invariants.
void prove_enum_bit(oparroy::Node& node0, oparroy::Node& node1, oparroy::Bit originated,
                    lib::Span<const uint8_t> stamp0, lib::Span<const uint8_t> stamp1, uint32_t i) {
    const oparroy::TxAction action0 = node0.on_bit(originated);
    KLEE_PROVE(action0 != oparroy::TxAction::Idle);
    const oparroy::Bit after0 = emitted_bit(action0);
    // Rewrite, not insertion: node0 stamps exactly its own slot and
    // echoes every other bit untouched.
    KLEE_PROVE(after0 == (i < slot_bits ? oparroy::bit_at(stamp0, i) : originated));

    const oparroy::TxAction action1 = node1.on_bit(after0);
    KLEE_PROVE(action1 != oparroy::TxAction::Idle);
    // Drained frame: every slot carries its own node's stamp.
    KLEE_PROVE(emitted_bit(action1) == (i < slot_bits ? oparroy::bit_at(stamp0, i)
                                                      : oparroy::bit_at(stamp1, i - slot_bits)));
}

} // namespace

extern "C" int klee_enum() {
    uint8_t frame[2]; // 16 bits: two pre-sized slots
    uint8_t stamp0[1];
    uint8_t stamp1[1];
    klee_make_symbolic(&frame, sizeof frame, "frame");
    klee_make_symbolic(&stamp0, sizeof stamp0, "stamp0");
    klee_make_symbolic(&stamp1, sizeof stamp1, "stamp1");

    oparroy::Node node0{oparroy::NodeConfig{.slot_index = 0, .slot_bits = slot_bits},
                        oparroy::BitSlice{.bytes = stamp0, .bit_count = slot_bits}};
    oparroy::Node node1{oparroy::NodeConfig{.slot_index = slot_bits, .slot_bits = slot_bits},
                        oparroy::BitSlice{.bytes = stamp1, .bit_count = slot_bits}};
    KLEE_PROVE(
        oparroy::Node::config_valid(oparroy::NodeConfig{.slot_index = 0, .slot_bits = slot_bits},
                                    oparroy::BitSlice{.bytes = stamp0, .bit_count = slot_bits}));

    KLEE_PROVE(node0.on_break() == oparroy::TxAction::Idle);
    KLEE_PROVE(node1.on_break() == oparroy::TxAction::Idle);

    for (const uint32_t i : lib::irange<uint32_t>(2 * slot_bits)) {
        prove_enum_bit(node0, node1, oparroy::bit_at(frame, i), stamp0, stamp1, i);
    }
    return 0;
}
