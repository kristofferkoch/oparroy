// KLEE proof: the TX store-and-forward sequencer under arbitrary
// action/break/pop interleavings — the playback counterpart of
// klee/rx.cpp. Symbolic TxAction pushes, breaks, and pops must produce
// exactly the compare stream the contract says: nothing plays before
// the first closed frame, every frame plays bit-exact snapped to
// nominal, every frame is followed by tx_break_cells idle cells, and a
// contained or over-full accumulating frame is discarded, never
// regenerated.
//
// Equivalence is checked against a shadow sequencer written from the
// contract (tx.hpp's header comment), not against the implementation's
// own state (code-std.md#4-tests). The shadow is an append log with
// region indices — no loops, no ring: symbolic loop bounds fork a
// state per iteration, and the proof's step budget is spent on
// interleavings instead. The implementation's ring wraparound is
// exercised by capacity 8 within the proof's step count.
//
// Default-init, never value-init: a whole-Rig {} zeroes the shadow log
// with an llvm.memset, which klee 3.2 doesn't implement
// (klee_bitcode_flags' lifetime-marker comment is the sibling case).
// The members' own initializers cover everything but the log, and the
// log is read only below its indices.

#include "../tx.hpp"
#include "../../lib/array.hpp"
#include "../../lib/klee.hpp"
#include "../../lib/range.hpp"
#include "../cell.hpp"
#include "../node.hpp"

#include <cstdint>

namespace {

constexpr uint16_t capacity = 8;

// The shadow, written from the contract: a closed frame's bits play in
// order, t0h_ticks/t1h_ticks per bit; tx_break_cells idles follow every
// frame; tx_idle_compare whenever nothing is queued; an Idle or an
// overflow discards the accumulating frame and latches until the next
// break. Playable bits are [play_pos, play_end), the accumulating
// frame is [play_end, append_pos) — discard and close are index moves.
// The log array is uninitialized: zeroing it lowers to an
// llvm.memset, which klee 3.2 doesn't implement (the Rig comment
// below) — and the log is read only below its indices.
// NOLINTNEXTLINE(cppcoreguidelines-pro-type-member-init)
struct ShadowTx {
    // Sized for the proof's step count; every append logs one entry.
    lib::Array<uint8_t, 24> bits;
    uint16_t play_pos = 0;
    uint16_t play_end = 0;
    uint16_t append_pos = 0;
    uint16_t idle = 0;
    bool dropped = false;
};

void shadow_push(ShadowTx& shadow, oparroy::TxAction action) {
    if (action == oparroy::TxAction::Idle) {
        shadow.append_pos = shadow.play_end;
        shadow.dropped = true;
        return;
    }
    if (shadow.dropped) {
        return;
    }
    if (shadow.append_pos - shadow.play_pos >= capacity) {
        shadow.append_pos = shadow.play_end;
        shadow.dropped = true;
        return;
    }
    // NOLINTNEXTLINE(cppcoreguidelines-pro-bounds-constant-array-index)
    shadow.bits[shadow.append_pos] = action == oparroy::TxAction::EmitOne ? 1 : 0;
    shadow.append_pos += 1;
}

void shadow_break(ShadowTx& shadow) {
    shadow.play_end = shadow.append_pos;
    shadow.dropped = false;
}

uint16_t shadow_pop(ShadowTx& shadow) {
    if (shadow.idle > 0) {
        shadow.idle -= 1;
        return oparroy::tx_idle_compare;
    }
    if (shadow.play_pos == shadow.play_end) {
        return oparroy::tx_idle_compare;
    }
    // NOLINTNEXTLINE(cppcoreguidelines-pro-bounds-constant-array-index)
    const uint8_t bit = shadow.bits[shadow.play_pos];
    shadow.play_pos += 1;
    if (shadow.play_pos == shadow.play_end) {
        shadow.idle = oparroy::tx_break_cells;
    }
    return bit != 0 ? oparroy::t1h_ticks : oparroy::t0h_ticks;
}

struct Rig {
    oparroy::TxSequencer<capacity> sequencer;
    ShadowTx shadow;
};

// One proof step: a single symbolic byte, one 5-way fork — the step
// budget is the proof's whole cost (a second symbolic per step would
// multiply it, the klee/tx.cpp history lesson). 0 pop, 1 push EmitZero,
// 2 push EmitOne, 3 push Idle, 4 break.
void prove_step(Rig& rig, uint8_t selector) {
    switch (selector % 5) {
    case 0:
        // Pops are the common case — the DMA drains every cell.
        KLEE_PROVE(rig.sequencer.pop() == shadow_pop(rig.shadow));
        break;
    case 1:
    case 2: {
        const oparroy::TxAction action =
            selector % 5 == 1 ? oparroy::TxAction::EmitZero : oparroy::TxAction::EmitOne;
        rig.sequencer.push(action);
        shadow_push(rig.shadow, action);
        break;
    }
    case 3:
        rig.sequencer.push(oparroy::TxAction::Idle);
        shadow_push(rig.shadow, oparroy::TxAction::Idle);
        break;
    default:
        rig.sequencer.on_break();
        shadow_break(rig.shadow);
        break;
    }
    KLEE_PROVE(rig.sequencer.playable_bits() == rig.shadow.play_end - rig.shadow.play_pos);
    KLEE_PROVE(rig.sequencer.pending_bits() == rig.shadow.append_pos - rig.shadow.play_end);
}

} // namespace

extern "C" int klee_tx() {
    Rig rig;

    // Before the first break: an arbitrary push/pop plays nothing.
    uint8_t pre = 0;
    klee_make_symbolic(&pre, sizeof pre, "pre");
    if (pre % 5 != 4) {
        prove_step(rig, pre);
    }
    KLEE_PROVE(rig.sequencer.pop() == oparroy::tx_idle_compare);

    // Close the first frame, then an arbitrary interleaved stream.
    prove_step(rig, 4);
    for ([[maybe_unused]] const int step : lib::irange(6)) {
        uint8_t selector = 0;
        klee_make_symbolic(&selector, sizeof selector, "selector");
        prove_step(rig, selector);
    }
    return 0;
}
