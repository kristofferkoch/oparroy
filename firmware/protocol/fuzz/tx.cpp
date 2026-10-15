// Fuzz: the TX store-and-forward sequencer against an injected
// action/break/pop stream — the sampling counterpart to klee/tx.cpp.
// Raw fuzzer bytes become the glue-side fault modes: arbitrary TxAction
// interleavings (Idle mid-frame = containment), breaks anywhere, pops
// at any rate, and brown-out sequencer resets. Whatever arrives, the
// played compare stream must match the shadow model exactly: nothing
// before the first closed frame, frames bit-exact snapped to nominal,
// tx_break_cells idle after every frame, discarded frames never
// regenerate.
//
// Input grammar: events of one selector byte plus one payload byte.
// selector % 8 — 0–2 pop, 3–4 push (payload % 3: Idle / EmitZero /
// EmitOne), 5 push Idle, 6 break, 7 brown-out reset. Capacity is 64
// bits so real-length inputs drive the ring to wrap and overflow.

#include "../tx.hpp"
#include "../../lib/array.hpp"
#include "../../lib/range.hpp"
#include "../../lib/span.hpp"
#include "../cell.hpp"
#include "../node.hpp"
#include "fuzz.hpp"

#include <cstddef>
#include <cstdint>

namespace {

constexpr uint16_t capacity = 64;

// The shadow sequencer, written from the contract (tx.hpp's header
// comment) — assertions check this independent model, never the
// implementation under test (code-std.md#4-tests; the klee/tx.cpp
// pattern). Linear queues with a consume index, no ring.
struct ShadowTx {
    // 2× capacity: up to capacity unconsumed playable bits plus the
    // capacity-bit pending frame a break can close onto them.
    lib::Array<uint8_t, 2 * static_cast<std::size_t>(capacity)> playable{};
    uint16_t playable_count = 0;
    uint16_t play_pos = 0;
    lib::Array<uint8_t, capacity> pending{};
    uint16_t pending_count = 0;
    uint16_t idle = 0;
    bool dropped = false;
};

void shadow_push(ShadowTx& shadow, oparroy::TxAction action) {
    if (action == oparroy::TxAction::Idle) {
        shadow.pending_count = 0;
        shadow.dropped = true;
        return;
    }
    if (shadow.dropped) {
        return;
    }
    if ((shadow.playable_count - shadow.play_pos) + shadow.pending_count >= capacity) {
        shadow.pending_count = 0;
        shadow.dropped = true;
        return;
    }
    // NOLINTNEXTLINE(cppcoreguidelines-pro-bounds-constant-array-index)
    shadow.pending[shadow.pending_count] = action == oparroy::TxAction::EmitOne ? 1 : 0;
    shadow.pending_count += 1;
}

void shadow_break(ShadowTx& shadow) {
    // Compact first: the consumed prefix is dead, and without this the
    // linear queue grows past the array over a long fuzz run.
    for (const uint16_t i : lib::irange(shadow.play_pos, shadow.playable_count)) {
        // NOLINTNEXTLINE(cppcoreguidelines-pro-bounds-constant-array-index)
        shadow.playable[i - shadow.play_pos] = shadow.playable[i];
    }
    shadow.playable_count -= shadow.play_pos;
    shadow.play_pos = 0;
    for (const uint16_t i : lib::irange(shadow.pending_count)) {
        // NOLINTNEXTLINE(cppcoreguidelines-pro-bounds-constant-array-index)
        shadow.playable[shadow.playable_count] = shadow.pending[i];
        shadow.playable_count += 1;
    }
    shadow.pending_count = 0;
    shadow.dropped = false;
}

uint16_t shadow_pop(ShadowTx& shadow) {
    if (shadow.idle > 0) {
        shadow.idle -= 1;
        return oparroy::tx_idle_compare;
    }
    if (shadow.play_pos == shadow.playable_count) {
        return oparroy::tx_idle_compare;
    }
    // NOLINTNEXTLINE(cppcoreguidelines-pro-bounds-constant-array-index)
    const uint8_t bit = shadow.playable[shadow.play_pos];
    shadow.play_pos += 1;
    if (shadow.play_pos == shadow.playable_count) {
        shadow.idle = oparroy::tx_break_cells;
    }
    return bit != 0 ? oparroy::t1h_ticks : oparroy::t0h_ticks;
}

} // namespace

// NOLINTNEXTLINE(readability-identifier-naming) — engine-fixed ABI name
extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    oparroy::fuzz::Cursor cursor{lib::Span<const uint8_t>{data, size}};

    oparroy::TxSequencer<capacity> sequencer;
    ShadowTx shadow{};

    while (cursor.remaining() > 0) {
        const uint8_t selector = cursor.take_u8();
        const uint8_t payload = cursor.take_u8();
        switch (selector % 8) {
        case 0:
        case 1:
        case 2:
            FUZZ_PROVE(sequencer.pop() == shadow_pop(shadow));
            break;
        case 3:
        case 4: {
            oparroy::TxAction action = oparroy::TxAction::Idle;
            if (payload % 3 == 1) {
                action = oparroy::TxAction::EmitZero;
            } else if (payload % 3 == 2) {
                action = oparroy::TxAction::EmitOne;
            }
            sequencer.push(action);
            shadow_push(shadow, action);
            break;
        }
        case 5:
            sequencer.push(oparroy::TxAction::Idle);
            shadow_push(shadow, oparroy::TxAction::Idle);
            break;
        case 6:
            sequencer.on_break();
            shadow_break(shadow);
            break;
        default:
            // Brown-out: the sequencer reboots mid-stream.
            sequencer = oparroy::TxSequencer<capacity>{};
            shadow = ShadowTx{};
            break;
        }
        FUZZ_PROVE(sequencer.playable_bits() == shadow.playable_count - shadow.play_pos);
        FUZZ_PROVE(sequencer.pending_bits() == shadow.pending_count);
    }
    return 0;
}
