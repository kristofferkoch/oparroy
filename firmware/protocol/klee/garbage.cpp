// KLEE proof: behavior under injected garbage — the babbling-idiot case
// (DESIGN.md §3) met by the §2 containment rule. Whatever arrives — any
// cell timing, legal or illegal, interleaved with breaks — the node
// forwards nothing before the first break, never regenerates after an
// illegal cell until the next break, and a break always resyncs.
//
// Containment is checked against a shadow model of the input stream
// (poisoned), not the node's own state() — an assertion that trusts the
// implementation under test proves nothing (code-std.md §11).

#include "../../lib/range.hpp"
#include "../bits.hpp"
#include "../cell.hpp"
#include "../node.hpp"
#include "klee.hpp"

#include <cstdint>

namespace {

oparroy::TxAction feed_cell(oparroy::Node& node, oparroy::CellDecode decode) {
    switch (decode) {
    case oparroy::CellDecode::Zero:
        return node.on_bit(oparroy::Bit::Zero);
    case oparroy::CellDecode::One:
        return node.on_bit(oparroy::Bit::One);
    case oparroy::CellDecode::Illegal:
        return node.on_illegal_cell();
    }
    // GCC doesn't treat an exhaustive enum switch as covering;
    // -Wswitch-enum still guards against a missed enumerator.
    __builtin_unreachable();
}

// Shadow model of the input stream, not of the node: an in-frame illegal
// cell poisons regeneration until the next break.
struct Shadow {
    bool poisoned;
};

void prove_cell_step(oparroy::Node& node, Shadow& shadow, oparroy::CellDecode decode) {
    const oparroy::TxAction action = feed_cell(node, decode);
    // Containment: once poisoned, the line stays idle until the break.
    if (shadow.poisoned) {
        KLEE_PROVE(action == oparroy::TxAction::Idle);
    }
    // A legal bit in flight is always forwarded, never swallowed.
    if (!shadow.poisoned && decode != oparroy::CellDecode::Illegal) {
        KLEE_PROVE(action != oparroy::TxAction::Idle);
    }
    if (decode == oparroy::CellDecode::Illegal) {
        shadow.poisoned = true;
        // Containment is immediate: the illegal cell itself is never
        // regenerated as a bit.
        KLEE_PROVE(action == oparroy::TxAction::Idle);
    }
}

void prove_break_step(oparroy::Node& node, Shadow& shadow) {
    KLEE_PROVE(node.on_break() == oparroy::TxAction::Idle);
    // A break always resyncs the node into the next frame.
    KLEE_PROVE(node.state() == oparroy::NodeState::Forward);
    shadow.poisoned = false;
}

} // namespace

extern "C" int klee_garbage() {
    uint8_t stamp[1];
    klee_make_symbolic(&stamp, sizeof stamp, "stamp");
    oparroy::Node node{oparroy::NodeConfig{.slot_index = 2, .slot_bits = 4},
                       oparroy::BitSlice{.bytes = stamp, .bit_count = 8}};

    // Hunt: whatever arrives before the first break is never forwarded
    // (position unknown ⇒ forwarding could stamp the wrong slot).
    oparroy::CapturedCell pre{};
    klee_make_symbolic(&pre, sizeof pre, "pre");
    KLEE_PROVE(feed_cell(node, oparroy::decode_cell(pre)) == oparroy::TxAction::Idle);
    KLEE_PROVE(node.state() != oparroy::NodeState::Forward);

    // First frame gap: the ring starts.
    Shadow shadow{.poisoned = false};
    prove_break_step(node, shadow);

    // Injected garbage stream: symbolic cells interleaved with breaks.
    for ([[maybe_unused]] const int step : lib::irange(5)) {
        uint8_t kind = 0;
        oparroy::CapturedCell cell{};
        klee_make_symbolic(&kind, sizeof kind, "kind");
        klee_make_symbolic(&cell, sizeof cell, "cell");
        if (kind % 2 == 0) {
            prove_cell_step(node, shadow, oparroy::decode_cell(cell));
        } else {
            prove_break_step(node, shadow);
        }
    }

    // Over-long frame: the cap contains an endless legal stream like
    // an illegal cell — Mute until the next break (node.hpp,
    // frame_max_bits). Concrete cells: one path; the count is what
    // matters. Stamped slot bits may flip the emitted value, so the
    // invariant is forwarded-at-all, not forwarded-as-one.
    prove_break_step(node, shadow);
    for ([[maybe_unused]] const uint16_t i : lib::irange(oparroy::frame_max_bits)) {
        KLEE_PROVE(node.on_bit(oparroy::Bit::One) != oparroy::TxAction::Idle);
    }
    KLEE_PROVE(node.on_bit(oparroy::Bit::One) == oparroy::TxAction::Idle);
    KLEE_PROVE(node.state() == oparroy::NodeState::Mute);
    prove_break_step(node, shadow);
    KLEE_PROVE(node.on_bit(oparroy::Bit::One) != oparroy::TxAction::Idle);
    return 0;
}
