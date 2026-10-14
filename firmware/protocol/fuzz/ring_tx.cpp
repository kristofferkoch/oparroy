// Fuzz: the cut-through ring end-to-end — the card's rung. A 3-hop
// chain where each hop is the full node stack: RxDecoder → Node →
// TxCutThrough, and each hop's played compare stream feeds the next
// hop's capture path through a wire model. Originated cells enter hop0;
// whatever the fuzzer injects, every hop must match its shadows step
// for step: the decoder's TxActions against the node-level shadow
// (fuzz.hpp), the sequencer's pops against the queue shadow. Per-hop
// equality is transitive — hop k+1's shadow expects exactly what
// hop k's shadow emitted — so bit-exact forwarding from origin to
// drain holds for the chain (fuzz/ring.cpp's argument), now through
// the real RX/TX path with a bounded cut-through pipeline delay per
// hop.
//
// The wire model turns a pop stream back into capture pairs: a compare
// above tx_idle_compare is a cell (the one-tick idle sliver never
// reaches a capture — the downstream input filter rejects it), and the rising-edge-to-rising-edge
// period of the cell that ended is 60 ticks per played/idle cell since the previous edge; a gap ≥
// break_min_ticks is a marker (tx_break_cells idle pops after every frame guarantee one). Idle runs
// are capped at 4800 ticks — any longer silence is the same break to the decoder, and the ≥
// CNT-wrap alias path is klee/rx.cpp and fuzz/rx.cpp's proved territory, not this harness's.
//
// Input grammar: 3 telemetry bytes (one per node; the occupancy marker
// — enum.hpp — is forced set; slots are discovered, not configured),
// then steps of 5 bytes: origin selector, origin payload, then
// one pop count (0–3) per hop. Origin selector % 8 — 0–2 originate a
// bit cell (payload % 2), 3 originate an illegal cell (high > period),
// 4 idle one cell, 5 originate a break (tx_break_cells of idle),
// 6 brown-out reset hop payload % 3, 7 origin pause.

#include "../../lib/range.hpp"
#include "../../lib/span.hpp"
#include "../bits.hpp"
#include "../cell.hpp"
#include "../node.hpp"
#include "../rx.hpp"
#include "../tx.hpp"
#include "fuzz.hpp"

#include <cstddef>
#include <cstdint>

namespace {

constexpr uint16_t capacity = 64;
constexpr size_t node_count = 3;
constexpr uint16_t slot_bits = 8;
// Above break_min_ticks, below the CNT wrap (see the header comment).
constexpr uint32_t wire_gap_cap_ticks = 4800;

// The queue shadow, written from the contract (tx.hpp's header
// comment) — the fuzz/cut_through.cpp model, instantiated per hop. A
// ring mirroring the implementation's indexing: the checked semantics
// are the idle-run-first ordering, the mute containment, and the break
// resync (a linear queue here would need a compaction loop).
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

void prove_counts(const oparroy::TxCutThrough<capacity>& cut, const ShadowCut& shadow) {
    FUZZ_PROVE(cut.queued() == shadow.count);
    FUZZ_PROVE(cut.idle_remaining() == shadow.idle);
    FUZZ_PROVE(cut.muted() == shadow.muted);
}

// One hop: the node stack, its shadows, and the run-constant setup a
// brown-out rebuilds from. The decoder references the rig's own node —
// initialized in place (klee/rx.cpp's Rig pattern), never moved.
struct HopRig {
    // The defaults are placeholders — the initialization sites
    // designate every member (fuzz/ring.cpp's NodeRig pattern).
    oparroy::Node node;
    oparroy::RxDecoder decoder;
    oparroy::TxCutThrough<capacity> cut;
    oparroy::fuzz::Shadow shadow;
    ShadowCut shadow_cut;
    oparroy::NodeConfig config{};
    oparroy::DoubleBuffer<oparroy::BitSlice> telemetry{
        .front = oparroy::BitSlice{.bytes = lib::Span<const uint8_t>{nullptr, 0}, .bit_count = 0},
        .back = oparroy::BitSlice{.bytes = lib::Span<const uint8_t>{nullptr, 0}, .bit_count = 0}};
};

// The wire into a hop: rising-edge bookkeeping for the capture stream
// the wire model feeds. The pending cell is the one a period capture
// will complete (rx.hpp's pairing).
struct Wire {
    uint32_t gap_ticks = 0;
    uint16_t pending_high = 0;
    bool have_edge = false;
    bool pending = false;
};

void wire_idle(Wire& wire) {
    wire.gap_ticks += oparroy::cell_period_nominal_ticks;
    // Freestanding: no <algorithm> for std::min
    // (code-std-cpp.md#1-language-and-toolchain).
    // NOLINTNEXTLINE(readability-use-std-min-max)
    if (wire.gap_ticks > wire_gap_cap_ticks) {
        wire.gap_ticks = wire_gap_cap_ticks;
    }
}

// One played cell: high_ticks is the compare value (t0h/t1h for
// re-synthesized cells, anything for an injected fault). Feeds the
// downstream hop's decoder and sequencer, proving each returned action
// against the hop's shadows. Mirrors the rx.cpp glue's mapping: cell
// boundaries push the decoder's action, a marker is tx on_break, and
// on_high's return is provably always Idle (the decoder's lockstep
// containment surfaces at the next period instead).
void wire_cell(Wire& wire, HopRig& hop, uint16_t high_ticks) {
    const auto gap = static_cast<uint16_t>(wire.gap_ticks + oparroy::cell_period_nominal_ticks);
    wire.gap_ticks = 0;
    if (wire.have_edge) {
        const oparroy::TxAction action = hop.decoder.on_period(gap);
        if (gap >= oparroy::break_min_ticks) {
            FUZZ_PROVE(action == oparroy::TxAction::Idle);
            hop.cut.on_break();
            shadow_break(hop.shadow_cut);
            hop.shadow.on_break();
            FUZZ_PROVE(hop.node.latch_count() == hop.shadow.latch_count());
        } else {
            FUZZ_PROVE(wire.pending);
            const oparroy::CellDecode decode = oparroy::decode_cell(
                oparroy::CapturedCell{.period_ticks = gap, .high_ticks = wire.pending_high});
            const oparroy::Bit bit =
                decode == oparroy::CellDecode::One ? oparroy::Bit::One : oparroy::Bit::Zero;
            FUZZ_PROVE(action == hop.shadow.expect(decode, bit));
            hop.cut.push(action);
            shadow_push(hop.shadow_cut, action);
        }
        wire.pending = false;
    }
    FUZZ_PROVE(hop.decoder.on_high(high_ticks) == oparroy::TxAction::Idle);
    wire.pending = true;
    wire.pending_high = high_ticks;
    wire.have_edge = true;
    prove_counts(hop.cut, hop.shadow_cut);
}

// One sequencer pop onto the wire into the hop's downstream neighbor.
void drain(HopRig& hop, Wire& out_wire, HopRig& downstream, uint8_t pops) {
    for (const uint8_t i : lib::irange(pops)) {
        (void)i;
        const uint16_t compare = hop.cut.pop();
        FUZZ_PROVE(compare == shadow_pop(hop.shadow_cut));
        if (compare == oparroy::tx_idle_compare) {
            wire_idle(out_wire);
        } else {
            wire_cell(out_wire, downstream, compare);
        }
    }
    prove_counts(hop.cut, hop.shadow_cut);
}

// The drain line: the last hop's played cells go to the supervisor's
// drain, asserted by the shadow match alone.
void drain_end(HopRig& hop, uint8_t pops) {
    for (const uint8_t i : lib::irange(pops)) {
        (void)i;
        FUZZ_PROVE(hop.cut.pop() == shadow_pop(hop.shadow_cut));
    }
    prove_counts(hop.cut, hop.shadow_cut);
}

// Brown-out: the hop reboots mid-stream (node, sequencer) and its
// capture path restarts with it (decoder resync, fresh input wire) —
// the wire keeps its own state downstream of the hop, which now plays
// idle.
void reset_rig(HopRig& rig, Wire& in_wire) {
    rig.node = oparroy::Node{rig.config, rig.telemetry};
    rig.decoder.resync();
    rig.cut = oparroy::TxCutThrough<capacity>{};
    rig.shadow.on_reset();
    rig.shadow_cut = ShadowCut{};
    in_wire = Wire{};
}

} // namespace

// NOLINTNEXTLINE(readability-identifier-naming) — engine-fixed ABI name
extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    oparroy::fuzz::Cursor cursor{lib::Span<const uint8_t>{data, size}};

    // One telemetry byte per node (the occupancy marker — enum.hpp — is
    // forced set); slots are discovered, not configured (fuzz/ring.cpp's
    // setup).
    uint8_t telemetry_storage[node_count];
    for (uint8_t& byte : telemetry_storage) {
        byte = static_cast<uint8_t>(cursor.take_u8() | 0x80u);
    }
    const lib::Span<const uint8_t> telemetry_span{telemetry_storage};
    const oparroy::NodeConfig config{.slot_bits = slot_bits};
    const auto telemetry_of = [&telemetry_span](size_t index) {
        const oparroy::BitSlice face{.bytes = telemetry_span.subspan(index, 1),
                                     .bit_count = slot_bits};
        return oparroy::DoubleBuffer<oparroy::BitSlice>{.front = face, .back = face};
    };
    // node declared before the decoder that references it; each rig is
    // initialized in place so the reference binds to the member.
    HopRig rig0{.node = oparroy::Node{config, telemetry_of(0)},
                .decoder = oparroy::RxDecoder{rig0.node},
                .cut = oparroy::TxCutThrough<capacity>{},
                .shadow = oparroy::fuzz::Shadow{config, telemetry_of(0)},
                .shadow_cut = ShadowCut{},
                .config = config,
                .telemetry = telemetry_of(0)};
    HopRig rig1{.node = oparroy::Node{config, telemetry_of(1)},
                .decoder = oparroy::RxDecoder{rig1.node},
                .cut = oparroy::TxCutThrough<capacity>{},
                .shadow = oparroy::fuzz::Shadow{config, telemetry_of(1)},
                .shadow_cut = ShadowCut{},
                .config = config,
                .telemetry = telemetry_of(1)};
    HopRig rig2{.node = oparroy::Node{config, telemetry_of(2)},
                .decoder = oparroy::RxDecoder{rig2.node},
                .cut = oparroy::TxCutThrough<capacity>{},
                .shadow = oparroy::fuzz::Shadow{config, telemetry_of(2)},
                .shadow_cut = ShadowCut{},
                .config = config,
                .telemetry = telemetry_of(2)};

    Wire wire0{}; // the origin's line into hop0
    Wire wire1{}; // hop0's played stream into hop1
    Wire wire2{}; // hop1's played stream into hop2

    while (cursor.remaining() > 0) {
        const uint8_t selector = cursor.take_u8();
        const uint8_t payload = cursor.take_u8();
        switch (selector % 8) {
        case 0:
        case 1:
        case 2:
            wire_cell(wire0, rig0, payload % 2 == 0 ? oparroy::t0h_ticks : oparroy::t1h_ticks);
            break;
        case 3:
            // high > period: illegal when the next edge completes it.
            wire_cell(wire0, rig0, 70);
            break;
        case 4:
            wire_idle(wire0);
            break;
        case 5:
            for ([[maybe_unused]] const uint16_t i : lib::irange(oparroy::tx_break_cells)) {
                wire_idle(wire0);
            }
            break;
        case 6:
            switch (payload % node_count) {
            case 0:
                reset_rig(rig0, wire0);
                break;
            case 1:
                reset_rig(rig1, wire1);
                break;
            default:
                reset_rig(rig2, wire2);
                break;
            }
            break;
        default:
            break; // origin pause: the pops below still advance the hops
        }
        drain(rig0, wire1, rig1, static_cast<uint8_t>(cursor.take_u8() % 4));
        drain(rig1, wire2, rig2, static_cast<uint8_t>(cursor.take_u8() % 4));
        drain_end(rig2, static_cast<uint8_t>(cursor.take_u8() % 4));
    }
    return 0;
}
