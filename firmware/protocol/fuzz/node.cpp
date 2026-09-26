// Fuzz: one cut-through node against an injected fault stream
// (fuzz.hpp) — the sampling counterpart to klee/garbage.cpp. Whatever
// arrives — legal cells, line errors, timer glitches, breaks, brown-out
// resets — the node must match the shadow model exactly: nothing
// forwarded before the first break, nothing regenerated after an
// illegal cell or an over-long frame until the next break, a break
// always resyncs, the vsync latch fires once per frame in progress.

#include "../node.hpp"
#include "../../lib/span.hpp"
#include "../bits.hpp"
#include "../cell.hpp"
#include "fuzz.hpp"

#include <cstddef>
#include <cstdint>

namespace {

// The node under test and its independent shadow model.
struct Rig {
    oparroy::Node node;
    oparroy::fuzz::Shadow shadow;
};

void prove_cell_step(Rig& rig, oparroy::CapturedCell cell) {
    const oparroy::CellDecode decode = oparroy::decode_cell(cell);
    const oparroy::Bit incoming =
        decode == oparroy::CellDecode::One ? oparroy::Bit::One : oparroy::Bit::Zero;
    const oparroy::TxAction actual = decode == oparroy::CellDecode::Illegal
                                         ? rig.node.on_illegal_cell()
                                         : rig.node.on_bit(incoming);
    FUZZ_PROVE(actual == rig.shadow.expect(decode, incoming));
}

void prove_break_step(Rig& rig) {
    FUZZ_PROVE(rig.node.on_break() == oparroy::TxAction::Idle);
    rig.shadow.on_break();
    FUZZ_PROVE(rig.node.state() == oparroy::NodeState::Forward);
    FUZZ_PROVE(rig.node.latch_count() == rig.shadow.latch_count());
}

} // namespace

// NOLINTNEXTLINE(readability-identifier-naming) — engine-fixed ABI name
extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    oparroy::fuzz::Cursor cursor{lib::Span<const uint8_t>{data, size}};

    // Config and telemetry from the leading bytes: 2 telemetry bytes,
    // slot index anywhere in u16 (parked slots are the echo case), slot
    // width biased into the valid range so the fuzzer spends cycles in
    // the state machine, not bounced off config_valid.
    const uint8_t telemetry_storage[2] = {cursor.take_u8(), cursor.take_u8()};
    const oparroy::NodeConfig config{
        .slot_index = cursor.take_u16(),
        .slot_bits = static_cast<uint16_t>(1 + (cursor.take_u8() % 16)),
    };
    const oparroy::BitSlice telemetry{.bytes = lib::Span<const uint8_t>{telemetry_storage},
                                      .bit_count = 16};
    FUZZ_PROVE(oparroy::Node::config_valid(config, telemetry));

    Rig rig{.node = oparroy::Node{config, telemetry},
            .shadow = oparroy::fuzz::Shadow{config, telemetry}};

    while (cursor.remaining() > 0) {
        const oparroy::fuzz::Event event = oparroy::fuzz::next_event(cursor);
        switch (event.kind) {
        case oparroy::fuzz::EventKind::Cell:
            prove_cell_step(rig, event.cell);
            break;
        case oparroy::fuzz::EventKind::Break:
            prove_break_step(rig);
            break;
        case oparroy::fuzz::EventKind::Reset:
            // Brown-out: the node reboots mid-stream, back to Hunt.
            rig.node = oparroy::Node{config, telemetry};
            rig.shadow.on_reset();
            break;
        }
    }
    return 0;
}
