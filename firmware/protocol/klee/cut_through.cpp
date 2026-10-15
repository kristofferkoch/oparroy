// KLEE proof: the TX cut-through sequencer under arbitrary
// action/break/pop interleavings — the cut-through counterpart of
// klee/tx.cpp. Symbolic TxAction pushes, breaks, and pops must produce
// exactly the compare stream the contract says: nothing plays before the
// first break, bits re-emit snapped to nominal in order, a break resyncs
// and re-arms the idle run (drained first), and an Idle or a full FIFO
// mutes — nothing further enqueues until the next break.
//
// Equivalence is checked against a shadow sequencer written from the
// contract (tx.hpp's header comment), not against the implementation's
// own state (code-std.md#4-tests). The shadow is a linear queue with
// region indices — no ring: symbolic loop bounds fork a state per
// iteration, and the proof's step budget is spent on interleavings
// instead. The implementation's ring wraparound is exercised by capacity
// 8 within the proof's step count.
//
// Default-init, never value-init: a whole-Rig {} zeroes the shadow log
// with an llvm.memset, which klee 3.2 doesn't implement
// (klee_bitcode_flags' lifetime-marker comment is the sibling case).
// The members' own initializers cover everything but the log, and the
// log is read only below its indices.

#include "../../lib/array.hpp"
#include "../../lib/klee.hpp"
#include "../../lib/range.hpp"
#include "../cell.hpp"
#include "../node.hpp"
#include "../tx.hpp"

#include <cstddef>
#include <cstdint>

namespace {

constexpr uint16_t capacity = 8;

// The shadow, written from the contract: Emit* enqueues the nominal
// compare, Idle or a full queue mutes, on_break resyncs (drop the queue)
// and re-arms the idle run, pop() drains idle first then the queue. The
// queue is linear — head advances on pop, never wraps — so the ring
// arithmetic is what the proof checks. head + count stays below
// 2 × capacity: enqueues between breaks are bounded by capacity (then
// mute), pops by the enqueues they consume.
// The log array is uninitialized: zeroing it lowers to an llvm.memset,
// which klee 3.2 doesn't implement (the Rig comment below) — and the log
// is read only below its indices.
// NOLINTNEXTLINE(cppcoreguidelines-pro-type-member-init)
struct ShadowCut {
    // Sized for the proof's step count; every enqueue writes one entry.
    lib::Array<uint16_t, 2 * static_cast<std::size_t>(capacity)> cells;
    uint16_t head = 0;
    uint16_t count = 0;
    uint16_t idle = 0;
    bool muted = false;
};

void shadow_push(ShadowCut& shadow, oparroy::TxAction action) {
    if (shadow.muted) {
        return;
    }
    if (action == oparroy::TxAction::Idle) {
        shadow.muted = true;
        return;
    }
    if (shadow.count >= capacity) {
        shadow.muted = true;
        return;
    }
    // NOLINTNEXTLINE(cppcoreguidelines-pro-bounds-constant-array-index)
    shadow.cells[shadow.head + shadow.count] =
        action == oparroy::TxAction::EmitOne ? oparroy::t1h_ticks : oparroy::t0h_ticks;
    shadow.count += 1;
}

void shadow_break(ShadowCut& shadow) {
    shadow.head = 0;
    shadow.count = 0;
    shadow.muted = false;
    shadow.idle = oparroy::tx_break_cells;
}

uint16_t shadow_pop(ShadowCut& shadow) {
    if (shadow.idle > 0) {
        shadow.idle -= 1;
        return oparroy::tx_idle_compare;
    }
    if (shadow.count == 0) {
        return oparroy::tx_idle_compare;
    }
    // NOLINTNEXTLINE(cppcoreguidelines-pro-bounds-constant-array-index)
    const uint16_t compare = shadow.cells[shadow.head];
    shadow.head += 1;
    shadow.count -= 1;
    // Reset on empty: a linear queue's head otherwise grows without
    // bound across long pop runs (the ring it shadows wraps instead).
    if (shadow.count == 0) {
        shadow.head = 0;
    }
    return compare;
}

struct Rig {
    oparroy::TxCutThrough<capacity> cut;
    ShadowCut shadow;
};

// One proof step: a single symbolic byte, one 5-way fork — the step
// budget is the proof's whole cost (a second symbolic per step would
// multiply it, the klee/tx.cpp history lesson). 0 pop, 1 push EmitZero,
// 2 push EmitOne, 3 push Idle, 4 break.
void prove_step(Rig& rig, uint8_t selector) {
    switch (selector % 5) {
    case 0:
        // Pops are the common case — the DMA drains every cell.
        KLEE_PROVE(rig.cut.pop() == shadow_pop(rig.shadow));
        break;
    case 1:
    case 2: {
        const oparroy::TxAction action =
            selector % 5 == 1 ? oparroy::TxAction::EmitZero : oparroy::TxAction::EmitOne;
        rig.cut.push(action);
        shadow_push(rig.shadow, action);
        break;
    }
    case 3:
        rig.cut.push(oparroy::TxAction::Idle);
        shadow_push(rig.shadow, oparroy::TxAction::Idle);
        break;
    default:
        rig.cut.on_break();
        shadow_break(rig.shadow);
        break;
    }
    KLEE_PROVE(rig.cut.queued() == rig.shadow.count);
    KLEE_PROVE(rig.cut.idle_remaining() == rig.shadow.idle);
    KLEE_PROVE(rig.cut.muted() == rig.shadow.muted);
}

} // namespace

extern "C" int klee_cut_through() {
    Rig rig;

    // An arbitrary interleaved push/pop/break stream from the first
    // step: every step must match the shadow. No first-break gate — the
    // FIFO forwards from the first push (the Node's Hunt/Mute states are
    // what gate forwarding on-target, not the FIFO itself).
    for ([[maybe_unused]] const int step : lib::irange(7)) {
        uint8_t selector = 0;
        klee_make_symbolic(&selector, sizeof selector, "selector");
        prove_step(rig, selector);
    }
    return 0;
}
