// Translation unit for the header-only protocol core: keeps the
// GCC cross build (rv32ec) and clang-tidy compiling the same headers the
// KLEE bitcode targets include directly.

#include "../lib/error_or.hpp"
#include "../lib/range.hpp"
#include "../lib/span.hpp"
#include "../lib/static_vector.hpp"
#include "bits.hpp"
#include "cell.hpp"
#include "enum.hpp"
#include "node.hpp"
#include "rx.hpp"
#include "tx.hpp"

#include <cstdint>

namespace oparroy {

static_assert(decode_cell(encode_cell(Bit::Zero)) == CellDecode::Zero);
static_assert(decode_cell(encode_cell(Bit::One)) == CellDecode::One);
static_assert(decode_cell(CapturedCell{.period_ticks = 42, .high_ticks = 19}) ==
              CellDecode::Illegal);
static_assert(decode_cell(CapturedCell{.period_ticks = 78, .high_ticks = 38}) ==
              CellDecode::Illegal);
static_assert(decode_cell(CapturedCell{.period_ticks = 60, .high_ticks = 61}) ==
              CellDecode::Illegal);

constexpr lib::Span<const uint8_t> empty_bytes{nullptr, 0};
static_assert(!valid(BitSlice{.bytes = empty_bytes, .bit_count = 1}));
static_assert(valid(BitSlice{.bytes = empty_bytes, .bit_count = 0}));

namespace {

    // A vsync double buffer over two faces, for the constexpr walks below.
    constexpr DoubleBuffer<BitSlice> double_buffered(BitSlice front, BitSlice back) {
        return DoubleBuffer<BitSlice>{.front = front, .back = back};
    }

    // A stamp face always carries the occupancy marker (enum.hpp) at wire
    // bit 0 — MSB-first, so byte 0's top bit is set.
    constexpr uint8_t stamp_byte = 0x80;
    constexpr BitSlice stamp_face{.bytes = lib::Span<const uint8_t>{&stamp_byte, 1},
                                  .bit_count = 8};
    constexpr uint8_t zero_byte = 0x00;
    constexpr BitSlice zero_face{.bytes = lib::Span<const uint8_t>{&zero_byte, 1}, .bit_count = 8};
    constexpr BitSlice empty_slice{.bytes = empty_bytes, .bit_count = 8};

} // namespace

static_assert(Node::config_valid(NodeConfig{.slot_bits = 8},
                                 double_buffered(stamp_face, stamp_face)));
static_assert(!Node::config_valid(NodeConfig{.slot_bits = 0},
                                  double_buffered(stamp_face, stamp_face)));
// Both faces must carry the slot: the front is stamped this frame, the
// back becomes the front at the next latch.
static_assert(!Node::config_valid(NodeConfig{.slot_bits = 8},
                                  double_buffered(empty_slice, stamp_face)));
static_assert(!Node::config_valid(NodeConfig{.slot_bits = 8},
                                  double_buffered(stamp_face, empty_slice)));
// The marker invariant: a marker-0 stamp would re-mark its slot empty
// for the next node downstream.
static_assert(!Node::config_valid(NodeConfig{.slot_bits = 8},
                                  double_buffered(zero_face, zero_face)));

// Over-long frame containment (node.hpp, frame_max_bits): a legal
// stream past the cap is contained like an illegal cell — Mute until
// the next break, which resyncs as always.
namespace {

    constexpr bool frame_cap_mutes() {
        const uint8_t telemetry_byte = 0x80; // the occupancy marker (enum.hpp)
        const BitSlice face{.bytes = lib::Span<const uint8_t>{&telemetry_byte, 1}, .bit_count = 8};
        Node node{NodeConfig{.slot_bits = 1}, double_buffered(face, face)};
        if (node.on_break() != TxAction::Idle) {
            return false;
        }
        for ([[maybe_unused]] const uint16_t i : lib::irange(frame_max_bits)) {
            if (node.on_bit(Bit::One) == TxAction::Idle) {
                return false;
            }
        }
        if (node.on_bit(Bit::One) != TxAction::Idle || node.state() != NodeState::Mute) {
            return false;
        }
        node.on_break();
        return node.on_bit(Bit::One) == TxAction::EmitOne;
    }

} // namespace

static_assert(frame_cap_mutes());

// RX burst decode (rx.hpp): a scripted walk over the decoder's phases —
// pre-sync garbage dropped, marker resyncs, a high/period pair decodes
// one bit, lockstep loss contains, the silence backstop swallows the
// aliased across-gap period without a second break.
namespace {

    constexpr bool rx_decode_phases() {
        // A 16-bit slot with the occupancy marker set: every frame's
        // first decoded bit below is a 1 (an occupied marker), so the
        // node echoes the whole stream — this walk is the decoder's,
        // not the slot walk's. BitSlice adopts the array (span.hpp).
        // NOLINTNEXTLINE(cppcoreguidelines-avoid-c-arrays,modernize-avoid-c-arrays)
        const uint8_t telemetry_bytes[2] = {0x80, 0x00};
        const BitSlice face{.bytes = lib::Span<const uint8_t>{telemetry_bytes}, .bit_count = 16};
        Node node{NodeConfig{.slot_bits = 16}, double_buffered(face, face)};
        RxDecoder decoder{node};

        // Hunt: captures before the first marker never reach the node.
        if (decoder.on_high(t1h_ticks) != TxAction::Idle ||
            decoder.on_period(cell_period_nominal_ticks) != TxAction::Idle ||
            node.state() != NodeState::Hunt) {
            return false;
        }

        // The marker resyncs (on_break returns Idle — a break
        // propagates as line idle), then a legal pair decodes a 1.
        if (decoder.on_period(break_min_ticks) != TxAction::Idle ||
            node.state() != NodeState::Forward || decoder.on_high(t1h_ticks) != TxAction::Idle ||
            decoder.on_period(cell_period_nominal_ticks) != TxAction::EmitOne ||
            node.bit_count() != 1) {
            return false;
        }

        // A 0 cell, then lockstep loss (a period with no pending high):
        // containment mutes the node until the next marker.
        if (decoder.on_high(t0h_ticks) != TxAction::Idle ||
            decoder.on_period(cell_period_nominal_ticks) != TxAction::EmitZero ||
            decoder.on_period(cell_period_nominal_ticks) != TxAction::Idle ||
            node.state() != NodeState::Mute || decoder.phase() != RxDecoder::Phase::Hunt) {
            return false;
        }

        // The next marker resyncs both.
        if (decoder.on_period(break_min_ticks) != TxAction::Idle ||
            node.state() != NodeState::Forward) {
            return false;
        }

        // The silence backstop: a ≥ CNT-wrap gap delivers the break and
        // GapDiscard swallows the aliased across-gap period (60 ticks —
        // legal-looking, never decoded); the next pair decodes clean.
        if (decoder.on_silence() != TxAction::Idle || node.bit_count() != 0 ||
            decoder.on_period(cell_period_nominal_ticks) != TxAction::Idle ||
            decoder.on_high(t1h_ticks) != TxAction::Idle ||
            decoder.on_period(cell_period_nominal_ticks) != TxAction::EmitOne ||
            node.bit_count() != 1) {
            return false;
        }

        // The frame's last cell never pairs: its high is pending when
        // the next marker arrives, and the marker just resyncs.
        if (decoder.on_high(t0h_ticks) != TxAction::Idle ||
            decoder.on_period(5000) != TxAction::Idle || node.bit_count() != 0) {
            return false;
        }

        // Overrun containment: an illegal cell mutes, Hunt resyncs.
        if (decoder.on_high(t1h_ticks) != TxAction::Idle ||
            decoder.on_overrun() != TxAction::Idle || node.state() != NodeState::Mute ||
            decoder.phase() != RxDecoder::Phase::Hunt) {
            return false;
        }
        return true;
    }

} // namespace

static_assert(rx_decode_phases());

// §2 vsync double buffer (node.hpp): the node stamps the front face for
// a whole frame, and the latch at the frame gap swaps it with the back —
// the "global shutter" that keeps a frame's telemetry one sampled
// snapshot. A two-frame walk with distinct faces proves both halves:
// frame 1 stamps front, the break latches, frame 2 stamps the old back.
namespace {

    constexpr bool vsync_double_buffer() {
        // Distinct faces, both with the occupancy marker set (enum.hpp).
        // The node stamps its first frame's slot — the walk feeds an
        // all-zero (empty) slot, so discovery claims it.
        const uint8_t front_byte = 0b10101010;
        const uint8_t back_byte = 0b11010101;
        const BitSlice front{.bytes = lib::Span<const uint8_t>{&front_byte, 1}, .bit_count = 8};
        const BitSlice back{.bytes = lib::Span<const uint8_t>{&back_byte, 1}, .bit_count = 8};
        Node node{NodeConfig{.slot_bits = 8}, double_buffered(front, back)};

        // The first break latches: the sampled back becomes the front
        // this frame stamps, bit for bit.
        node.on_break();
        for (const uint8_t i : lib::irange(uint8_t{8})) {
            const TxAction expected =
                bit_at(back, i) == Bit::One ? TxAction::EmitOne : TxAction::EmitZero;
            if (node.on_bit(Bit::Zero) != expected) {
                return false;
            }
        }
        // The next gap latches again: the faces swap back, so frame 2
        // stamps the original front. A node that stamped a stale face, or
        // never swapped, fails here.
        node.on_break();
        for (const uint8_t i : lib::irange(uint8_t{8})) {
            const TxAction expected =
                bit_at(front, i) == Bit::One ? TxAction::EmitOne : TxAction::EmitZero;
            if (node.on_bit(Bit::Zero) != expected) {
                return false;
            }
        }
        return true;
    }

} // namespace

static_assert(vsync_double_buffer());

// Find-first-empty-slot discovery (node.hpp, enum.hpp — DESIGN.md §2):
// the node claims the first marker-0 slot of every frame with its
// telemetry face and echoes everything else bit-exact — occupied slots
// (marker 1), and every slot once it has stamped.
namespace {

    constexpr bool expect_echo(Node& node, Bit incoming) {
        const TxAction expected = incoming == Bit::One ? TxAction::EmitOne : TxAction::EmitZero;
        return node.on_bit(incoming) == expected;
    }

    constexpr bool discovery_walk() {
        // 4-bit slots; the face's wire bits are 1,0,1,1 (marker + payload).
        const uint8_t stamp = 0b10110000;
        const BitSlice face{.bytes = lib::Span<const uint8_t>{&stamp, 1}, .bit_count = 4};
        Node node{NodeConfig{.slot_bits = 4}, double_buffered(face, face)};
        node.on_break();

        // Slot 0 occupied (marker 1): echoes 1,0,0,1 untouched.
        // NOLINTNEXTLINE(cppcoreguidelines-avoid-c-arrays,modernize-avoid-c-arrays)
        const Bit occupied[4] = {Bit::One, Bit::Zero, Bit::Zero, Bit::One};
        for (const uint8_t i : lib::irange(uint8_t{4})) {
            // NOLINTNEXTLINE(cppcoreguidelines-pro-bounds-constant-array-index)
            if (!expect_echo(node, occupied[i])) {
                return false;
            }
        }
        // Slot 1 empty (all zero): claimed, stamps the face bit for bit.
        for (const uint8_t i : lib::irange(uint8_t{4})) {
            const TxAction expected =
                bit_at(face, i) == Bit::One ? TxAction::EmitOne : TxAction::EmitZero;
            if (node.on_bit(Bit::Zero) != expected) {
                return false;
            }
        }
        // Slot 2 also empty: already stamped — echoes the zeros.
        for ([[maybe_unused]] const uint8_t i : lib::irange(uint8_t{4})) {
            if (!expect_echo(node, Bit::Zero)) {
                return false;
            }
        }

        // The next frame restarts discovery; a frame with no empty slot
        // (both slots occupied) passes through entirely unstamped.
        node.on_break();
        for ([[maybe_unused]] const uint8_t slot : lib::irange(uint8_t{2})) {
            for (const uint8_t i : lib::irange(uint8_t{4})) {
                // NOLINTNEXTLINE(cppcoreguidelines-pro-bounds-constant-array-index)
                if (!expect_echo(node, occupied[i])) {
                    return false;
                }
            }
        }
        return true;
    }

} // namespace

static_assert(discovery_walk());

// The ENUM wire format (enum.hpp): pack/unpack round-trips and the
// occupancy marker leads the slot.
static_assert(enum_slot_bits == 105 && enum_frame_bits == 840);
constexpr EnumStamp packed_sample = pack_stamp(0xDEADBEEF, 0x12345678, 0xA5A5A5A5, 0x3C);
constexpr UnpackedStamp unpacked_sample = unpack_stamp(stamp_slice(packed_sample));
static_assert(bit_at(stamp_slice(packed_sample), 0) == Bit::One);
static_assert(unpacked_sample.uniid1 == 0xDEADBEEF && unpacked_sample.uniid2 == 0x12345678 &&
              unpacked_sample.uniid3 == 0xA5A5A5A5 && unpacked_sample.type == 0x3C);

// TX store-and-forward (tx.hpp): a scripted walk over the sequencer's
// stream contract — nothing plays before the first closed frame, frames
// play bit-exact snapped to nominal, tx_break_cells of idle follow
// every frame, a contained frame never regenerates, and an over-full
// ring drops the accumulating frame. Capacity 64 like the harnesses, so
// the overflow path is in reach.
namespace {

    constexpr bool pops_idle(TxSequencer<64>& sequencer, uint16_t count) {
        for ([[maybe_unused]] const uint16_t i : lib::irange(count)) {
            if (sequencer.pop() != tx_idle_compare) {
                return false;
            }
        }
        return true;
    }

    constexpr bool tx_sequencer_phases() {
        TxSequencer<64> sequencer;

        // Nothing plays before the first closed frame.
        sequencer.push(TxAction::EmitOne);
        if (!pops_idle(sequencer, 4)) {
            return false;
        }

        // A one-bit frame: t1h, then at least tx_break_cells of idle.
        sequencer.on_break();
        if (sequencer.pop() != t1h_ticks || !pops_idle(sequencer, tx_break_cells + 4)) {
            return false;
        }

        // A two-bit frame plays snapped to nominal, then the idle run.
        sequencer.push(TxAction::EmitZero);
        sequencer.push(TxAction::EmitOne);
        sequencer.on_break();
        if (sequencer.pop() != t0h_ticks || sequencer.pop() != t1h_ticks ||
            !pops_idle(sequencer, tx_break_cells)) {
            return false;
        }

        // Containment: an Idle mid-frame discards it, a discarded frame
        // accumulates nothing, and the break closes nothing.
        sequencer.push(TxAction::EmitOne);
        sequencer.push(TxAction::Idle);
        sequencer.push(TxAction::EmitOne);
        sequencer.on_break();
        if (!pops_idle(sequencer, 8)) {
            return false;
        }

        // Overflow: capacity bits accumulate; the next append drops the
        // frame, and the break again closes nothing.
        for ([[maybe_unused]] const uint16_t i : lib::irange(uint16_t{64})) {
            sequencer.push(TxAction::EmitOne);
        }
        sequencer.push(TxAction::EmitOne);
        sequencer.on_break();
        return pops_idle(sequencer, 8);
    }

} // namespace

static_assert(tx_sequencer_phases());

// TX cut-through (tx.hpp): a scripted walk over the FIFO's stream
// contract — idle before the first frame, bits re-emit snapped to
// nominal in order, on_break resyncs and re-arms the idle run (drained
// first), containment (Idle) mutes and the FIFO drains to idle, and a
// full FIFO mutes rather than corrupting. Capacity 16 like the
// store-and-forward walk, so the overflow path is in reach via a second,
// tiny instance.
namespace {

    template <uint16_t C> constexpr bool cut_pops_idle(TxCutThrough<C>& cut, uint16_t count) {
        for ([[maybe_unused]] const uint16_t i : lib::irange(count)) {
            if (cut.pop() != tx_idle_compare) {
                return false;
            }
        }
        return true;
    }

    constexpr bool cut_through_phases() {
        TxCutThrough<16> cut;

        // Nothing plays before the first frame.
        if (!cut_pops_idle(cut, 4)) {
            return false;
        }

        // Bits re-emit snapped to nominal, in order.
        cut.push(TxAction::EmitOne);
        cut.push(TxAction::EmitZero);
        if (cut.queued() != 2 || cut.pop() != t1h_ticks || cut.pop() != t0h_ticks) {
            return false;
        }

        // The break resyncs (dropping any backlog) and re-arms the idle
        // run, which drains before the next frame's bits.
        cut.push(TxAction::EmitOne);
        cut.on_break();
        if (cut.queued() != 0 || cut.idle_remaining() != tx_break_cells) {
            return false;
        }
        cut.push(TxAction::EmitZero);
        for ([[maybe_unused]] const uint16_t i : lib::irange(tx_break_cells)) {
            if (cut.pop() != tx_idle_compare) {
                return false;
            }
        }
        if (cut.pop() != t0h_ticks || !cut_pops_idle(cut, 4)) {
            return false;
        }

        // Containment: an Idle mutes, the forwarded prefix drains, and
        // no further pushes land until the break resyncs.
        cut.push(TxAction::EmitOne);
        cut.push(TxAction::Idle);
        cut.push(TxAction::EmitOne);
        if (!cut.muted() || cut.queued() != 1 || cut.pop() != t1h_ticks) {
            return false;
        }
        if (!cut_pops_idle(cut, 4)) {
            return false;
        }
        cut.on_break();
        if (cut.muted() || cut.idle_remaining() != tx_break_cells) {
            return false;
        }

        // Overflow: a full FIFO mutes rather than corrupting a cell.
        TxCutThrough<4> small;
        for ([[maybe_unused]] const uint16_t i : lib::irange(uint16_t{4})) {
            small.push(TxAction::EmitOne);
        }
        small.push(TxAction::EmitOne);
        if (!small.muted() || small.queued() != 4) {
            return false;
        }
        for ([[maybe_unused]] const uint16_t i : lib::irange(uint16_t{4})) {
            if (small.pop() != t1h_ticks) {
                return false;
            }
        }
        return cut_pops_idle(small, 4);
    }

} // namespace

static_assert(cut_through_phases());

// Foundation-library cells (firmware/lib/range.hpp, static_vector.hpp):
// constexpr-proved here, the same TU that hosts Span's asserts.
namespace {

    constexpr int sum_of(lib::IntRange<int> range) {
        int sum = 0;
        for (const int i : range) {
            sum += i;
        }
        return sum;
    }

    // Overflow canary: a uint8_t range near the type max counts exactly
    // its half-open length — ++ past end is unreachable by construction
    // (range.hpp).
    constexpr uint32_t count_of(lib::IntRange<uint8_t> range) {
        uint32_t count = 0;
        for ([[maybe_unused]] const uint8_t i : range) {
            ++count;
        }
        return count;
    }

    constexpr bool static_vector_behaves() {
        lib::StaticVector<uint8_t, 3> vec;
        if (!vec.is_empty() || vec.size() != 0 || vec.capacity() != 3) {
            return false;
        }
        for (const uint8_t i : lib::irange(static_cast<uint8_t>(vec.capacity()))) {
            vec.push_back(i);
        }
        // Bounded: growth past capacity asks, and is refused.
        const lib::ErrorOr<void> refused = vec.try_push_back(9);
        if (!refused.is_error() || refused.error() != lib::Error::OutOfCapacity ||
            vec.size() != vec.capacity()) {
            return false;
        }
        uint32_t sum = 0;
        for (const uint8_t value : vec) {
            sum += value;
        }
        if (sum != 0 + 1 + 2 || vec[2] != 2) {
            return false;
        }
        vec.clear();
        return vec.is_empty() && vec.size() == 0;
    }

} // namespace

static_assert(sum_of(lib::irange(5)) == 10);
static_assert(sum_of(lib::irange(3, 7)) == 18);
// Inverted and negative ranges clamp to empty — a zero-trip loop, never
// UB (range.hpp).
static_assert(sum_of(lib::irange(7, 3)) == 0);
static_assert(sum_of(lib::irange(-4)) == 0);
static_assert(count_of(lib::irange(uint8_t{200})) == 200);
static_assert(static_vector_behaves());

} // namespace oparroy
