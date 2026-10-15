#pragma once

// The cut-through ring-node core (DESIGN.md §2): decode upstream
// bits, re-emit them snapped to nominal, and intercept only the node's
// own slot — the WS2812/EtherCAT shape, host-testable from the first
// commit (§8). Pure symbol logic with no time inside: the RX burst
// decode feeds on_bit / on_illegal_cell / on_break, and the TX half
// streams whatever the returned TxAction asks for.

#include "../lib/span.hpp"
#include "../lib/verify.hpp"
#include "bits.hpp"

#include <cstddef>
#include <cstdint>

namespace oparroy {

// What the TX half emits for one input symbol: a re-synthesized cell
// snapped to nominal, or line idle — break propagation and containment
// both look like idle on the wire.
enum class TxAction : uint8_t {
    Idle,
    EmitZero,
    EmitOne,
};

enum class NodeState : uint8_t {
    Hunt,    // no break seen yet: position unknown, forward nothing
    Forward, // counting bits from the frame gap; position = address
    Mute,    // fault contained (illegal cell, over-long frame): idle until next break
};

// Frames are bounded: the largest legal frame is the pre-sized ENUM —
// 8 nodes × 105 bits (occupancy marker + 96-bit UNIID + type byte,
// enum.hpp), DESIGN.md §2. A stream of legal cells past frame_max_bits
// without a break is a babbling idiot, not a frame: contain it like an
// illegal cell (Mute until the next break). 2048 is ~2× the ENUM
// maximum with headroom, and keeps the uint16_t bit counter far from
// wraparound.
inline constexpr uint16_t frame_max_bits = 2048;

struct NodeConfig {
    // Width of one frame slot in bits (the ENUM slot, enum.hpp). There
    // is no positional config: the node discovers its slot — the first
    // empty (marker-0) slot of every frame (DESIGN.md §2).
    uint16_t slot_bits;
};

// latch()'s swap must lower to scalar loads/stores: clang batches any
// struct copy past scalar width into one llvm.memcpy, which klee 3.2's
// partial LLVM 19 build (flake.nix) cannot execute — the proof dies at
// the first instruction with 0 completed paths (the memset sibling case,
// klee/tx.cpp's header comment). The swap survives intact where SROA
// cannot promote the buffer — a Node behind a reference, like the
// decoder's Node& (klee/rx.cpp's Rig). BitSlice faces swap field by
// scalar field; other Ts keep the plain three-assign swap — not
// std::swap: freestanding, constexpr, and no <utility> in the core.
template <typename T> constexpr void swap_faces(T& a, T& b) {
    const T stale = a;
    a = b;
    b = stale;
}

constexpr void swap_faces(BitSlice& a, BitSlice& b) {
    const uint8_t* const data = a.bytes.begin();
    const std::size_t size = a.bytes.size();
    const uint16_t bits = a.bit_count;
    a.bytes = lib::Span<const uint8_t>{b.bytes.begin(), b.bytes.size()};
    a.bit_count = b.bit_count;
    b.bytes = lib::Span<const uint8_t>{data, size};
    b.bit_count = bits;
}

// The §2 vsync double buffer (DESIGN.md §2 global shutter): two values
// swapped at the frame gap. The node reads `front` for the whole frame —
// telemetry stamped from the sampled snapshot, command outputs applied —
// while the glue writes `back` (sample inputs, decode commands). latch()
// is the single swap point, so neither face changes mid-frame: the §2
// "LED/buzzer state never changes mid-frame" and "every telemetry slot
// holds values from the same latch instant" properties.
template <typename T> struct DoubleBuffer {
    // NOLINTNEXTLINE(misc-non-private-member-variables-in-classes) — a value, not encapsulation
    T front;
    // NOLINTNEXTLINE(misc-non-private-member-variables-in-classes)
    T back;

    constexpr void latch() {
        swap_faces(front, back);
    }
};

class Node {
public:
    // The invariant is established here, not in a later init()
    // (code-std-cpp.md#3-types-and-arithmetic,
    // code-std-cpp.md#4-memory-and-ownership): config_valid() is the
    // check; callers and harnesses VERIFY it at setup. The telemetry is
    // double-buffered — the node stamps `front`, the glue samples into
    // `back`, and on_break latches (§2 vsync). The telemetry member is
    // built field by scalar field, never copied as an aggregate — the
    // swap_faces comment above gives the llvm.memcpy reason.
    constexpr Node(NodeConfig config, DoubleBuffer<BitSlice> telemetry)
        : m_config(config),
          m_telemetry{.front = {.bytes{telemetry.front.bytes.begin(), telemetry.front.bytes.size()},
                                .bit_count = telemetry.front.bit_count},
                      .back = {.bytes{telemetry.back.bytes.begin(), telemetry.back.bytes.size()},
                               .bit_count = telemetry.back.bit_count}} {}

    [[nodiscard]] static constexpr bool config_valid(NodeConfig config,
                                                     DoubleBuffer<BitSlice> telemetry) {
        // The marker invariant last, behind the size/validity checks that
        // make the read safe: a stamp's first wire bit is the occupancy
        // marker (enum.hpp), always 1 — a marker-0 telemetry would
        // re-mark its slot empty for the next node downstream.
        return config.slot_bits > 0 && config.slot_bits <= telemetry.front.bit_count &&
               config.slot_bits <= telemetry.back.bit_count && valid(telemetry.front) &&
               valid(telemetry.back) && bit_at(telemetry.front, 0) == Bit::One &&
               bit_at(telemetry.back, 0) == Bit::One;
    }

    // One decoded upstream bit. Forwarded snapped to nominal, except
    // inside the slot the node claims, where the telemetry bit is
    // substituted on the fly (a slot rewrite, never an insertion — ENUM
    // frames are pre-sized, DESIGN.md §2).
    [[nodiscard]] constexpr TxAction on_bit(Bit incoming) {
        switch (m_state) {
        case NodeState::Hunt:
        case NodeState::Mute:
            return TxAction::Idle;
        case NodeState::Forward:
            return forward_bit(incoming);
        }
        // GCC doesn't treat an exhaustive enum switch as covering;
        // -Wswitch-enum still guards against a missed enumerator.
        UNREACHABLE();
    }

    // Illegal cell (period outside 0.9–1.6 µs, cell.hpp): stop
    // regenerating and force the line idle until the next break — the
    // containment rule (DESIGN.md §2) for the babbling-idiot case (§3).
    constexpr TxAction on_illegal_cell() {
        if (m_state == NodeState::Forward) {
            m_state = NodeState::Mute;
        }
        return TxAction::Idle;
    }

    // Frame gap (line low ≥ break_min_ticks): the ring-wide vsync latch
    // (DESIGN.md §2) — swap the double buffer (apply the previous frame's
    // outputs, sample this frame's inputs) — and the slot walk's reset:
    // discovery restarts from the first slot of every frame. Breaks
    // propagate as line idle.
    constexpr TxAction on_break() {
        if (m_state == NodeState::Forward) {
            m_latch_count += 1;
        }
        m_telemetry.latch();
        m_state = NodeState::Forward;
        m_bit_count = 0;
        m_slot_bit = 0;
        m_stamping = false;
        m_stamped = false;
        return TxAction::Idle;
    }

    [[nodiscard]] constexpr NodeState state() const {
        return m_state;
    }
    [[nodiscard]] constexpr uint16_t bit_count() const {
        return m_bit_count;
    }
    [[nodiscard]] constexpr uint32_t latch_count() const {
        return m_latch_count;
    }

private:
    constexpr TxAction forward_bit(Bit incoming) {
        // Over-long frame: a babbling idiot, not a frame — contain it
        // like an illegal cell, Mute until the next break
        // (frame_max_bits above; also what keeps m_bit_count from
        // ever wrapping).
        if (m_bit_count >= frame_max_bits) {
            m_state = NodeState::Mute;
            return TxAction::Idle;
        }
        Bit outgoing = incoming;
        if (!m_stamped) {
            // Find-first-empty-slot discovery (DESIGN.md §2, enum.hpp):
            // a slot's first bit is its occupancy marker — 0 = empty,
            // claim the slot; 1 = occupied, pass it through untouched.
            // The marker is decided with zero lookahead, which is what
            // keeps stamping inside the 1:1 per-bit cut-through contract.
            // A marker-0 slot with a non-zero payload (corruption) is
            // claimed anyway: the rewrite is the containment.
            if (m_slot_bit == 0) {
                m_stamping = incoming == Bit::Zero;
            }
            if (m_stamping) {
                // The front face — the sampled snapshot, frozen for the
                // whole frame by the §2 vsync latch (on_break swaps,
                // never mid-frame).
                outgoing = bit_at(m_telemetry.front, m_slot_bit);
            }
            m_slot_bit += 1;
            if (m_slot_bit == m_config.slot_bits) {
                m_slot_bit = 0;
                m_stamped = m_stamping;
            }
        }
        m_bit_count += 1;
        return outgoing == Bit::One ? TxAction::EmitOne : TxAction::EmitZero;
    }

    NodeConfig m_config;
    DoubleBuffer<BitSlice> m_telemetry;
    NodeState m_state = NodeState::Hunt;
    uint16_t m_bit_count = 0;
    uint16_t m_slot_bit = 0;
    uint32_t m_latch_count = 0;
    bool m_stamping = false; // claiming the slot currently streaming past
    bool m_stamped = false;  // this frame's slot is claimed
};

} // namespace oparroy
