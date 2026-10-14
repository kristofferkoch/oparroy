// Fuzz: the RX burst decoder against an injected capture stream — the
// sampling counterpart to klee/rx.cpp. Raw fuzzer bytes become DMA-side
// fault modes: period/high captures with arbitrary timing (glitches,
// window boundaries), silence injections (the ≥ CNT-wrap alias case),
// overcaptures, decoder resyncs (RX source flips), and brown-out node
// resets. Whatever arrives, the decoder must match the shadow model
// exactly: nothing decoded before the first marker, breaks resync,
// lost lockstep contains.
//
// Input grammar: 2 telemetry bytes, slot width byte
// (mapped to 1 + x % 16), then events. An event is a selector byte
// plus a u16 (LE) payload: selector % 8 — 0–3 period capture, 4–5
// high capture, 6 control (payload % 3: silence / overrun / resync),
// 7 brown-out reset.

#include "../rx.hpp"
#include "../../lib/span.hpp"
#include "../bits.hpp"
#include "../cell.hpp"
#include "../node.hpp"
#include "fuzz.hpp"

#include <cstddef>
#include <cstdint>

namespace {

// The shadow decoder, written from the contract (rx.hpp's header
// comment) — assertions check this independent model, never the
// implementation under test (code-std.md#4-tests; the klee/rx.cpp
// pattern).
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

// The run-constant setup, bundled: a brown-out reset rebuilds the
// nodes from it.
struct Setup {
    oparroy::NodeConfig config;
    oparroy::DoubleBuffer<oparroy::BitSlice> telemetry;
};

// One fuzz step's inputs, bundled: adjacent uint8/uint16 parameters
// would invite transposition at every call site
// (code-std-cpp.md#3-types-and-arithmetic).
struct Step {
    uint8_t selector;
    uint16_t ticks;
};

void prove_step(oparroy::RxDecoder& decoder, oparroy::Node& node, oparroy::Node& shadow_node,
                ShadowRx& shadow, const Setup& setup, Step step) {
    oparroy::TxAction actual = oparroy::TxAction::Idle;
    oparroy::TxAction expected = oparroy::TxAction::Idle;
    switch (step.selector % 8) {
    case 0:
    case 1:
    case 2:
    case 3:
        actual = decoder.on_period(step.ticks);
        expected = shadow_period(shadow, shadow_node, step.ticks);
        break;
    case 4:
    case 5:
        actual = decoder.on_high(step.ticks);
        expected = shadow_high(shadow, shadow_node, step.ticks);
        break;
    case 6:
        switch (step.ticks % 3) {
        case 0:
            actual = decoder.on_silence();
            expected = shadow_silence(shadow, shadow_node);
            break;
        case 1:
            actual = decoder.on_overrun();
            expected = shadow_overrun(shadow, shadow_node);
            break;
        default:
            decoder.resync();
            shadow.live = false;
            shadow.pending = false;
            shadow.swallow = false;
            break;
        }
        break;
    default:
        // Brown-out: the node reboots mid-stream, back to Hunt
        // (fuzz.hpp's Reset event); the decoder's resync models the
        // capture path restarting with it.
        node = oparroy::Node{setup.config, setup.telemetry};
        shadow_node = oparroy::Node{setup.config, setup.telemetry};
        decoder.resync();
        shadow = ShadowRx{};
        break;
    }
    FUZZ_PROVE(actual == expected);
    FUZZ_PROVE(node.state() == shadow_node.state());
    FUZZ_PROVE(node.latch_count() == shadow_node.latch_count());
}

} // namespace

// NOLINTNEXTLINE(readability-identifier-naming) — engine-fixed ABI name
extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    oparroy::fuzz::Cursor cursor{lib::Span<const uint8_t>{data, size}};

    // Config and telemetry from the leading bytes — the node.cpp
    // prefix: the occupancy marker (enum.hpp) is forced set, slot width
    // biased into the valid range.
    const uint8_t telemetry_storage[2] = {static_cast<uint8_t>(cursor.take_u8() | 0x80u),
                                          cursor.take_u8()};
    const oparroy::NodeConfig config{
        .slot_bits = static_cast<uint16_t>(1 + (cursor.take_u8() % 16)),
    };
    const oparroy::BitSlice face{.bytes = lib::Span<const uint8_t>{telemetry_storage},
                                 .bit_count = 16};
    const oparroy::DoubleBuffer<oparroy::BitSlice> telemetry{.front = face, .back = face};
    FUZZ_PROVE(oparroy::Node::config_valid(config, telemetry));

    const Setup setup{.config = config, .telemetry = telemetry};
    oparroy::Node node{config, telemetry};
    oparroy::Node shadow_node{config, telemetry};
    ShadowRx shadow{};
    oparroy::RxDecoder decoder{node};

    while (cursor.remaining() > 0) {
        prove_step(decoder, node, shadow_node, shadow, setup,
                   Step{.selector = cursor.take_u8(), .ticks = cursor.take_u16()});
    }
    return 0;
}
