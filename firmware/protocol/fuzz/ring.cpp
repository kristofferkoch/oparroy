// Fuzz: a 3-node cut-through chain — the sampling counterpart to
// klee/echo.cpp + klee/enum.cpp, with faults. Originated cells enter
// node0; each node's emitted bit feeds the next hop, and a muted node
// is a silent line (downstream simply sees no cells). Every hop must
// match its shadow: bit-exact echo outside slots, exact slot stamps
// inside them, containment after faults, one latch per frame. A reset
// brown-out hits one node at a time — a real brown-out is per-node.

#include "../../lib/array.hpp"
#include "../../lib/span.hpp"
#include "../bits.hpp"
#include "../cell.hpp"
#include "../node.hpp"
#include "fuzz.hpp"

#include <cstddef>
#include <cstdint>

namespace {

constexpr size_t node_count = 3;
constexpr uint16_t slot_bits = 8;

// One chain position: the node under test, its independent shadow
// model, and everything the brown-out path needs to rebuild it.
struct NodeRig {
    // The defaults are placeholders — make_rig designates every member.
    oparroy::NodeConfig config{};
    oparroy::DoubleBuffer<oparroy::BitSlice> telemetry{
        .front = oparroy::BitSlice{.bytes = lib::Span<const uint8_t>{nullptr, 0}, .bit_count = 0},
        .back = oparroy::BitSlice{.bytes = lib::Span<const uint8_t>{nullptr, 0}, .bit_count = 0}};
    oparroy::Node node;
    oparroy::fuzz::Shadow shadow;
};

NodeRig make_rig(lib::Span<const uint8_t> telemetry_byte) {
    const oparroy::NodeConfig config{.slot_bits = slot_bits};
    const oparroy::BitSlice face{.bytes = telemetry_byte, .bit_count = slot_bits};
    const oparroy::DoubleBuffer<oparroy::BitSlice> telemetry{.front = face, .back = face};
    return NodeRig{.config = config,
                   .telemetry = telemetry,
                   .node = oparroy::Node{config, telemetry},
                   .shadow = oparroy::fuzz::Shadow{config, telemetry}};
}

// The wire state between hops: what the upstream side put on the line,
// or silence (alive = false — a muted node is a silent line, and
// downstream sees nothing).
struct Line {
    oparroy::CellDecode decode;
    oparroy::Bit bit;
    bool alive;
};

Line originate(oparroy::CapturedCell cell) {
    const oparroy::CellDecode decode = oparroy::decode_cell(cell);
    return Line{.decode = decode,
                .bit = decode == oparroy::CellDecode::One ? oparroy::Bit::One : oparroy::Bit::Zero,
                .alive = true};
}

// One hop through a node: a live line drives it, silence passes
// through. The returned line is what the node re-synthesized — snapped
// to nominal, so downstream never sees an illegal cell from a live hop.
Line hop(NodeRig& rig, Line line) {
    if (!line.alive) {
        return line;
    }
    const oparroy::TxAction actual = line.decode == oparroy::CellDecode::Illegal
                                         ? rig.node.on_illegal_cell()
                                         : rig.node.on_bit(line.bit);
    FUZZ_PROVE(actual == rig.shadow.expect(line.decode, line.bit));
    const oparroy::Bit out_bit =
        actual == oparroy::TxAction::EmitOne ? oparroy::Bit::One : oparroy::Bit::Zero;
    return Line{.decode = out_bit == oparroy::Bit::One ? oparroy::CellDecode::One
                                                       : oparroy::CellDecode::Zero,
                .bit = out_bit,
                .alive = actual != oparroy::TxAction::Idle};
}

void prove_break_step(NodeRig& rig) {
    FUZZ_PROVE(rig.node.on_break() == oparroy::TxAction::Idle);
    rig.shadow.on_break();
    FUZZ_PROVE(rig.node.latch_count() == rig.shadow.latch_count());
}

void reset_rig(NodeRig& rig) {
    rig.node = oparroy::Node{rig.config, rig.telemetry};
    rig.shadow.on_reset();
}

} // namespace

// NOLINTNEXTLINE(readability-identifier-naming) — engine-fixed ABI name
extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    oparroy::fuzz::Cursor cursor{lib::Span<const uint8_t>{data, size}};

    // One telemetry byte per node (the occupancy marker — enum.hpp — is
    // forced set); slots are discovered, not configured — the chain's
    // stamping falls out of the marker scan.
    lib::Array<uint8_t, node_count> telemetry_storage{};
    for (uint8_t& byte : telemetry_storage) {
        byte = static_cast<uint8_t>(cursor.take_u8() | 0x80u);
    }
    const lib::Span<const uint8_t> telemetry_span = telemetry_storage;
    NodeRig rig0 = make_rig(telemetry_span.subspan(0, 1));
    NodeRig rig1 = make_rig(telemetry_span.subspan(1, 1));
    NodeRig rig2 = make_rig(telemetry_span.subspan(2, 1));

    while (cursor.remaining() > 0) {
        const oparroy::fuzz::Event event = oparroy::fuzz::next_event(cursor);
        switch (event.kind) {
        case oparroy::fuzz::EventKind::Cell: {
            const Line after0 = hop(rig0, originate(event.cell));
            const Line after1 = hop(rig1, after0);
            // The drained line: asserted inside hop, by shadow match.
            hop(rig2, after1);
            break;
        }
        case oparroy::fuzz::EventKind::Break:
            prove_break_step(rig0);
            prove_break_step(rig1);
            prove_break_step(rig2);
            break;
        case oparroy::fuzz::EventKind::Reset:
            switch (cursor.take_u8() % node_count) {
            case 0:
                reset_rig(rig0);
                break;
            case 1:
                reset_rig(rig1);
                break;
            default:
                reset_rig(rig2);
                break;
            }
            break;
        }
    }
    return 0;
}
