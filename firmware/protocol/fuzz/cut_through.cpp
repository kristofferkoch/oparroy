// Fuzz: the TX cut-through sequencer against an injected
// action/break/pop stream — the sampling counterpart to
// klee/cut_through.cpp. Raw fuzzer bytes become the glue-side fault
// modes: arbitrary TxAction interleavings (Idle mid-frame = containment),
// breaks anywhere, pops at any rate, and brown-out sequencer resets.
// Whatever arrives, the played compare stream must match the shadow model
// exactly: nothing before the first break, bits re-emit snapped to
// nominal, tx_break_cells idle after every break (drained first), an
// Idle or a full FIFO mutes and nothing further enqueues until the next
// break.
//
// Input grammar: events of one selector byte plus one payload byte.
// selector % 8 — 0–2 pop, 3–4 push (payload % 3: Idle / EmitZero /
// EmitOne), 5 push Idle, 6 break, 7 brown-out reset. Capacity is 64
// cells so real-length inputs drive the ring to wrap and overflow.

#include "../../lib/span.hpp"
#include "../cell.hpp"
#include "../node.hpp"
#include "../tx.hpp"
#include "fuzz.hpp"

#include <cstddef>
#include <cstdint>

namespace {

constexpr uint16_t capacity = 64;

// The shadow sequencer, written from the contract (tx.hpp's header
// comment) — assertions check this independent model, never the
// implementation under test (code-std.md#4-tests; the klee/cut_through.cpp
// pattern). A ring of compares mirroring the implementation's indexing:
// the contract semantics being checked are the idle-run-first ordering,
// the mute containment, and the break resync — not the modulo
// arithmetic, which a long fuzz run exercises directly (a linear queue
// here would need a compaction loop the store-and-forward shadow only
// avoids because push and pop touch different queues).
struct ShadowCut {
    // NOLINTNEXTLINE(cppcoreguidelines-avoid-c-arrays,modernize-avoid-c-arrays)
    uint16_t cells[capacity] = {};
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
    shadow.cells[(shadow.head + shadow.count) % capacity] =
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
    shadow.head = static_cast<uint16_t>((shadow.head + 1) % capacity);
    shadow.count -= 1;
    return compare;
}

} // namespace

// NOLINTNEXTLINE(readability-identifier-naming) — engine-fixed ABI name
extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    oparroy::fuzz::Cursor cursor{lib::Span<const uint8_t>{data, size}};

    oparroy::TxCutThrough<capacity> cut;
    ShadowCut shadow{};

    while (cursor.remaining() > 0) {
        const uint8_t selector = cursor.take_u8();
        const uint8_t payload = cursor.take_u8();
        switch (selector % 8) {
        case 0:
        case 1:
        case 2:
            FUZZ_PROVE(cut.pop() == shadow_pop(shadow));
            break;
        case 3:
        case 4: {
            oparroy::TxAction action = oparroy::TxAction::Idle;
            if (payload % 3 == 1) {
                action = oparroy::TxAction::EmitZero;
            } else if (payload % 3 == 2) {
                action = oparroy::TxAction::EmitOne;
            }
            cut.push(action);
            shadow_push(shadow, action);
            break;
        }
        case 5:
            cut.push(oparroy::TxAction::Idle);
            shadow_push(shadow, oparroy::TxAction::Idle);
            break;
        case 6:
            cut.on_break();
            shadow_break(shadow);
            break;
        default:
            // Brown-out: the sequencer reboots mid-stream.
            cut = oparroy::TxCutThrough<capacity>{};
            shadow = ShadowCut{};
            break;
        }
        FUZZ_PROVE(cut.queued() == shadow.count);
        FUZZ_PROVE(cut.idle_remaining() == shadow.idle);
        FUZZ_PROVE(cut.muted() == shadow.muted);
    }
    return 0;
}
