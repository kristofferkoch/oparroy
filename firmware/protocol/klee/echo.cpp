// KLEE proof: frame echo invariant (DESIGN.md §2 closure discipline —
// the supervisor originates and drains; echo mismatch ⇒ fault). With no
// slot in range, a frame crossing a chain of cut-through nodes emerges
// bit-identical, every node forwards every legal bit, and the frame gap
// latches exactly once per node (the vsync, §2).

#include "../../lib/array.hpp"
#include "../../lib/klee.hpp"
#include "../../lib/range.hpp"
#include "../../lib/span.hpp"
#include "../bits.hpp"
#include "../node.hpp"

#include <cstddef>
#include <cstdint>

extern "C" int klee_echo() {
    constexpr uint32_t frame_bits = 24;
    constexpr size_t node_count = 3;

    // Uninitialized: klee_make_symbolic fills it (klee/tx.cpp's memset
    // constraint).
    // NOLINTNEXTLINE(cppcoreguidelines-pro-type-member-init)
    lib::Array<uint8_t, frame_bits / 8> frame;
    klee_make_symbolic(frame.data(), sizeof frame, "frame");

    // The echo invariant holds for frames with no empty slot: constrain
    // every slot marker (wire bits 0, 8, 16 — MSB-first, bits.hpp) to
    // occupied, and discovery passes the frame through untouched.
    klee_assume(frame[0] & 0x80u);
    klee_assume(frame[1] & 0x80u);
    klee_assume(frame[2] & 0x80u);

    // Loop-init, not = {}: the memset intrinsic is unimplemented in klee
    // 3.2's partial LLVM 19 build (flake.nix).
    // NOLINTNEXTLINE(cppcoreguidelines-pro-type-member-init)
    lib::Array<uint8_t, node_count> telemetry;
    for (uint8_t& byte : telemetry) {
        byte = 0;
    }
    const lib::Span<const uint8_t> telemetry_span = telemetry;
    // Both faces of the vsync double buffer are the same 8-bit
    // telemetry — never stamped here: every slot reads occupied.
    const auto telemetry_of = [&](size_t index) {
        const oparroy::BitSlice face{.bytes = telemetry_span.subspan(index, 1), .bit_count = 8};
        return oparroy::DoubleBuffer<oparroy::BitSlice>{.front = face, .back = face};
    };
    lib::Array<oparroy::Node, node_count> nodes{{
        oparroy::Node{oparroy::NodeConfig{.slot_bits = 8}, telemetry_of(0)},
        oparroy::Node{oparroy::NodeConfig{.slot_bits = 8}, telemetry_of(1)},
        oparroy::Node{oparroy::NodeConfig{.slot_bits = 8}, telemetry_of(2)},
    }};

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
