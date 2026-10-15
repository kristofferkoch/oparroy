// KLEE proof: ENUM find-first-empty-slot discovery (DESIGN.md §2,
// enum.hpp). A 2-node circulation over a frame of two symbolic pre-sized
// slots: each node rewrites exactly the first marker-0 (empty) slot with
// its latched telemetry face, occupied slots pass through bit-exact, and
// stamping stays a slot rewrite — 16 bits in, 16 bits out, every bit
// forwarded.

#include "../../lib/array.hpp"
#include "../../lib/klee.hpp"
#include "../../lib/range.hpp"
#include "../bits.hpp"
#include "../node.hpp"

#include <cstdint>

namespace {

constexpr uint16_t slot_bits = 8;

// The spec, written from the wire format: a node rewrites the first
// marker-0 slot with its stamp and leaves everything else untouched.
// The marker is wire bit 0 — MSB-first, byte 0's top bit (bits.hpp).
// Array keeps the slot sizes in the type — decayed pointers would make
// them comments and the three same-typed views swappable.
void spec_stamp(const lib::Array<uint8_t, 2>& in, const lib::Array<uint8_t, 1>& stamp,
                lib::Array<uint8_t, 2>& out) {
    out[0] = in[0];
    out[1] = in[1];
    if ((out[0] & 0x80u) == 0) {
        out[0] = stamp[0];
        return;
    }
    if ((out[1] & 0x80u) == 0) {
        out[1] = stamp[0];
    }
}

// The byte accumulator.
void record_bit(lib::Array<uint8_t, 2>& into, uint32_t i, oparroy::TxAction action) {
    // Value-select, never branch: a symbolic bit must not fork a KLEE
    // path (bits.hpp) — an if on the symbolic action forks the state
    // space once per bit.
    const auto bit = static_cast<uint8_t>(action == oparroy::TxAction::EmitOne);
    into[i / 8] = static_cast<uint8_t>(into[i / 8] | (bit << (7 - (i % 8))));
}

} // namespace

extern "C" int klee_enum() {
    // Uninitialized: klee_make_symbolic fills them, and zeroing would
    // lower to an llvm.memset klee 3.2 doesn't implement (klee/tx.cpp's
    // ShadowTx comment).
    // NOLINTBEGIN(cppcoreguidelines-pro-type-member-init)
    lib::Array<uint8_t, 2> frame; // 16 bits: two pre-sized slots
    lib::Array<uint8_t, 1> stamp0;
    lib::Array<uint8_t, 1> stamp1;
    lib::Array<uint8_t, 1> stale0; // a distinct face — stamped only if the latch is wrong
    // NOLINTEND(cppcoreguidelines-pro-type-member-init)
    klee_make_symbolic(frame.data(), sizeof frame, "frame");
    klee_make_symbolic(stamp0.data(), sizeof stamp0, "stamp0");
    klee_make_symbolic(stamp1.data(), sizeof stamp1, "stamp1");
    klee_make_symbolic(stale0.data(), sizeof stale0, "stale0");
    // A stamp's first wire bit is the occupancy marker (enum.hpp) — the
    // config_valid invariant.
    klee_assume(stamp0[0] & 0x80u);
    klee_assume(stamp1[0] & 0x80u);
    klee_assume(stale0[0] & 0x80u);

    // The glue sampled stamp0 into node0's back face; the first break
    // latches it to the front, so the frame stamps stamp0 — never the
    // stale front. This is the §2 double-buffer coherence: a distinct
    // symbolic front makes "stamps the wrong face" a proof failure.
    oparroy::Node node0{oparroy::NodeConfig{.slot_bits = slot_bits},
                        oparroy::DoubleBuffer<oparroy::BitSlice>{
                            .front = oparroy::BitSlice{.bytes = stale0, .bit_count = slot_bits},
                            .back = oparroy::BitSlice{.bytes = stamp0, .bit_count = slot_bits}}};
    oparroy::Node node1{oparroy::NodeConfig{.slot_bits = slot_bits},
                        oparroy::DoubleBuffer<oparroy::BitSlice>{
                            .front = oparroy::BitSlice{.bytes = stamp1, .bit_count = slot_bits},
                            .back = oparroy::BitSlice{.bytes = stamp1, .bit_count = slot_bits}}};
    KLEE_PROVE(oparroy::Node::config_valid(
        oparroy::NodeConfig{.slot_bits = slot_bits},
        oparroy::DoubleBuffer<oparroy::BitSlice>{
            .front = oparroy::BitSlice{.bytes = stale0, .bit_count = slot_bits},
            .back = oparroy::BitSlice{.bytes = stamp0, .bit_count = slot_bits}}));

    KLEE_PROVE(node0.on_break() == oparroy::TxAction::Idle);
    KLEE_PROVE(node1.on_break() == oparroy::TxAction::Idle);

    lib::Array<uint8_t, 2> middle{{0, 0}};
    lib::Array<uint8_t, 2> drained{{0, 0}};
    for (const uint32_t i : lib::irange<uint32_t>(2 * slot_bits)) {
        const oparroy::TxAction action0 = node0.on_bit(oparroy::bit_at(frame, i));
        // A legal bit in flight is always forwarded, never swallowed.
        KLEE_PROVE(action0 != oparroy::TxAction::Idle);
        record_bit(middle, i, action0);
        // The Bit enum is value-backed exactly for this select (bits.hpp).
        const auto between =
            static_cast<oparroy::Bit>(static_cast<uint8_t>(action0 == oparroy::TxAction::EmitOne));
        const oparroy::TxAction action1 = node1.on_bit(between);
        KLEE_PROVE(action1 != oparroy::TxAction::Idle);
        record_bit(drained, i, action1);
    }

    // Hop by hop against the spec: node0's output, then the drained frame.
    lib::Array<uint8_t, 2> after0{{0, 0}};
    lib::Array<uint8_t, 2> expected{{0, 0}};
    spec_stamp(frame, stamp0, after0);
    spec_stamp(after0, stamp1, expected);
    KLEE_PROVE(middle[0] == after0[0] && middle[1] == after0[1]);
    KLEE_PROVE(drained[0] == expected[0] && drained[1] == expected[1]);
    return 0;
}
