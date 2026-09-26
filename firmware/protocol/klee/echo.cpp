// KLEE proof: frame echo invariant (DESIGN.md §2 closure discipline —
// the supervisor originates and drains; echo mismatch ⇒ fault). With no
// slot in range, a frame crossing a chain of cut-through nodes emerges
// bit-identical, every node forwards every legal bit, and the frame gap
// latches exactly once per node (the vsync, §2).

#include "../../lib/range.hpp"
#include "../../lib/span.hpp"
#include "../bits.hpp"
#include "../node.hpp"
#include "klee.hpp"

#include <cstddef>
#include <cstdint>

extern "C" int klee_echo() {
    constexpr uint32_t frame_bits = 24;
    constexpr size_t node_count = 3;

    uint8_t frame[frame_bits / 8];
    klee_make_symbolic(&frame, sizeof frame, "frame");

    // Slots parked beyond the frame: pure forwarding, nothing stamped.
    // Loop-init, not = {}: the memset intrinsic is unimplemented in klee
    // 3.2's partial LLVM 19 build (flake.nix).
    uint8_t telemetry[node_count];
    for (uint8_t& byte : telemetry) {
        byte = 0;
    }
    const lib::Span<const uint8_t> telemetry_span{telemetry};
    oparroy::Node nodes[] = {
        oparroy::Node{oparroy::NodeConfig{.slot_index = 60000, .slot_bits = 1},
                      oparroy::BitSlice{.bytes = telemetry_span.subspan(0, 1), .bit_count = 1}},
        oparroy::Node{oparroy::NodeConfig{.slot_index = 60000, .slot_bits = 1},
                      oparroy::BitSlice{.bytes = telemetry_span.subspan(1, 1), .bit_count = 1}},
        oparroy::Node{oparroy::NodeConfig{.slot_index = 60000, .slot_bits = 1},
                      oparroy::BitSlice{.bytes = telemetry_span.subspan(2, 1), .bit_count = 1}},
    };

    for (oparroy::Node& node : nodes) {
        KLEE_PROVE(node.on_break() == oparroy::TxAction::Idle);
    }
    for (const uint32_t i : lib::irange(frame_bits)) {
        oparroy::Bit line = oparroy::bit_at(frame, i);
        for (oparroy::Node& node : nodes) {
            const oparroy::TxAction action = node.on_bit(line);
            // A legal bit in flight is always forwarded, never swallowed.
            KLEE_PROVE(action != oparroy::TxAction::Idle);
            line = action == oparroy::TxAction::EmitOne ? oparroy::Bit::One : oparroy::Bit::Zero;
        }
        // Echo: the drained bit is the originated bit.
        KLEE_PROVE(line == oparroy::bit_at(frame, i));
    }
    for (oparroy::Node& node : nodes) {
        KLEE_PROVE(node.on_break() == oparroy::TxAction::Idle);
        // The frame gap is the vsync: exactly one latch this frame.
        KLEE_PROVE(node.latch_count() == 1);
    }
    return 0;
}
