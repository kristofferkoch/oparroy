// KLEE proof: the RX burst decoder under arbitrary capture streams —
// the DMA-facing counterpart of garbage.cpp. Symbolic period/high
// captures, silences, and overruns must produce exactly the Node calls
// the contract says: nothing decoded before the first break marker, a
// marker always resyncs, lost lockstep contains (illegal cell) instead
// of decoding garbage, and the silence backstop never double-delivers
// a break.
//
// Equivalence is checked against a shadow decoder written from the
// contract (rx.hpp's header comment), not against the decoder's own
// state — an assertion that trusts the implementation under test
// proves nothing (code-std.md#4-tests). Both sides drive identical
// Node instances and the TxAction stream and observable node state
// must match step for step.

#include "../rx.hpp"
#include "../../lib/klee.hpp"
#include "../../lib/range.hpp"
#include "../bits.hpp"
#include "../cell.hpp"
#include "../node.hpp"

#include <cstdint>

namespace {

// The shadow, written from the contract: a cell is a high capture
// completed by its period; a period ≥ break_min_ticks is a break;
// before the first break nothing decodes; a broken pairing contains
// and waits for the next break; on_silence delivers the break the
// aliased marker would have and swallows that one capture.
struct ShadowRx {
    bool live = false;    // captures decode into the node
    bool pending = false; // a high capture awaits its period
    bool swallow = false; // on_silence armed the alias swallow
    uint16_t high = 0;
};

oparroy::TxAction shadow_period(ShadowRx& shadow, oparroy::Node& node, uint16_t ticks) {
    if (ticks >= oparroy::break_min_ticks) {
        shadow.pending = false;
        if (shadow.swallow) {
            shadow.swallow = false;
            shadow.live = true;
            return oparroy::TxAction::Idle;
        }
        shadow.live = true;
        return node.on_break();
    }
    if (shadow.swallow) {
        shadow.swallow = false;
        shadow.live = true;
        return oparroy::TxAction::Idle;
    }
    if (!shadow.live) {
        return oparroy::TxAction::Idle;
    }
    if (!shadow.pending) {
        shadow.live = false;
        return node.on_illegal_cell();
    }
    shadow.pending = false;
    const oparroy::CellDecode decode = oparroy::decode_cell(
        oparroy::CapturedCell{.period_ticks = ticks, .high_ticks = shadow.high});
    if (decode == oparroy::CellDecode::Illegal) {
        return node.on_illegal_cell();
    }
    return node.on_bit(decode == oparroy::CellDecode::One ? oparroy::Bit::One : oparroy::Bit::Zero);
}

oparroy::TxAction shadow_high(ShadowRx& shadow, oparroy::Node& node, uint16_t ticks) {
    if (!shadow.live) {
        return oparroy::TxAction::Idle;
    }
    if (shadow.pending) {
        shadow.pending = false;
        shadow.live = false;
        return node.on_illegal_cell();
    }
    shadow.pending = true;
    shadow.high = ticks;
    return oparroy::TxAction::Idle;
}

oparroy::TxAction shadow_silence(ShadowRx& shadow, oparroy::Node& node) {
    shadow.pending = false;
    if (!shadow.live && !shadow.swallow) {
        return oparroy::TxAction::Idle;
    }
    shadow.live = false;
    shadow.swallow = true;
    return node.on_break();
}

oparroy::TxAction shadow_overrun(ShadowRx& shadow, oparroy::Node& node) {
    shadow.pending = false;
    shadow.live = false;
    shadow.swallow = false;
    return node.on_illegal_cell();
}

struct Rig {
    oparroy::Node node;
    oparroy::Node shadow_node;
    ShadowRx shadow;
    oparroy::RxDecoder decoder;
};

// One proof step's inputs, bundled: adjacent uint8/uint16 parameters
// would invite transposition at every call site
// (code-std-cpp.md#3-types-and-arithmetic).
struct Step {
    uint8_t kind;
    uint16_t ticks;
};

void prove_step(Rig& rig, Step step) {
    oparroy::TxAction actual = oparroy::TxAction::Idle;
    oparroy::TxAction expected = oparroy::TxAction::Idle;
    switch (step.kind % 5) {
    case 0:
    case 1:
        actual = rig.decoder.on_period(step.ticks);
        expected = shadow_period(rig.shadow, rig.shadow_node, step.ticks);
        break;
    case 2:
    case 3:
        actual = rig.decoder.on_high(step.ticks);
        expected = shadow_high(rig.shadow, rig.shadow_node, step.ticks);
        break;
    default:
        if (step.ticks % 2 == 0) {
            actual = rig.decoder.on_silence();
            expected = shadow_silence(rig.shadow, rig.shadow_node);
        } else {
            actual = rig.decoder.on_overrun();
            expected = shadow_overrun(rig.shadow, rig.shadow_node);
        }
        break;
    }
    KLEE_PROVE(actual == expected);
    KLEE_PROVE(rig.node.state() == rig.shadow_node.state());
    KLEE_PROVE(rig.node.latch_count() == rig.shadow_node.latch_count());
}

} // namespace

extern "C" int klee_rx() {
    uint8_t stamp[1];
    klee_make_symbolic(&stamp, sizeof stamp, "stamp");
    // A stamp's first wire bit is the occupancy marker (enum.hpp).
    klee_assume(stamp[0] & 0x80u);
    const oparroy::NodeConfig config{.slot_bits = 4};
    const oparroy::DoubleBuffer<oparroy::BitSlice> telemetry{
        .front = oparroy::BitSlice{.bytes = stamp, .bit_count = 8},
        .back = oparroy::BitSlice{.bytes = stamp, .bit_count = 8}};
    // node declared before the decoder that references it; the shadow
    // side runs its own identical node.
    Rig rig{.node = oparroy::Node{config, telemetry},
            .shadow_node = oparroy::Node{config, telemetry},
            .shadow = ShadowRx{},
            .decoder = oparroy::RxDecoder{rig.node}};

    // One symbolic non-marker step: nothing may wake the node before
    // the first break (periods clamped below the marker length).
    uint8_t kind = 0;
    uint16_t ticks = 0;
    klee_make_symbolic(&kind, sizeof kind, "first_kind");
    klee_make_symbolic(&ticks, sizeof ticks, "first_ticks");
    if (kind % 5 < 2) {
        ticks = ticks % oparroy::break_min_ticks;
    }
    prove_step(rig, Step{.kind = kind, .ticks = ticks});
    KLEE_PROVE(rig.node.state() == oparroy::NodeState::Hunt);

    // The first marker: the ring starts.
    prove_step(rig, Step{.kind = 0, .ticks = oparroy::break_min_ticks});
    KLEE_PROVE(rig.node.state() == oparroy::NodeState::Forward);

    // Arbitrary interleaved stream from there.
    for ([[maybe_unused]] const int step : lib::irange(6)) {
        uint8_t next_kind = 0;
        uint16_t next_ticks = 0;
        klee_make_symbolic(&next_kind, sizeof next_kind, "kind");
        klee_make_symbolic(&next_ticks, sizeof next_ticks, "ticks");
        prove_step(rig, Step{.kind = next_kind, .ticks = next_ticks});
    }
    return 0;
}
