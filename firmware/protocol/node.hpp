#pragma once

// The cut-through ring-node core (DESIGN.md §2): decode upstream
// bits, re-emit them snapped to nominal, and intercept only the node's
// own slot — the WS2812/EtherCAT shape, host-testable from the first
// commit (§8). Pure symbol logic with no time inside: the RX burst
// decode feeds on_bit / on_illegal_cell / on_break, and the TX half
// streams whatever the returned TxAction asks for.

#include "../lib/verify.hpp"
#include "bits.hpp"

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
// 8 nodes × 104 bits (96-bit UNIID + type byte), DESIGN.md §2. A stream
// of legal cells past frame_max_bits without a break is a babbling
// idiot, not a frame: contain it like an illegal cell (Mute until the
// next break). 2048 is ~2× the ENUM maximum with headroom, and keeps
// the uint16_t bit counter far from wraparound.
inline constexpr uint16_t frame_max_bits = 2048;

struct NodeConfig {
    // Bit position of this node's slot, counted from the first bit after
    // the frame gap (positional addressing, DESIGN.md §2).
    uint16_t slot_index;
    uint16_t slot_bits;
};

class Node {
public:
    // The invariant is established here, not in a later init()
    // (code-std.md §4, §5): config_valid() is the check; callers and
    // harnesses VERIFY it at setup.
    constexpr Node(NodeConfig config, BitSlice telemetry)
        : m_config(config), m_telemetry(telemetry) {}

    [[nodiscard]] static constexpr bool config_valid(NodeConfig config, BitSlice telemetry) {
        return config.slot_bits > 0 && config.slot_bits <= telemetry.bit_count && valid(telemetry);
    }

    // One decoded upstream bit. Forwarded snapped to nominal, except
    // inside the node's own slot, where the telemetry bit is substituted
    // on the fly (a slot rewrite, never an insertion — ENUM frames are
    // pre-sized, DESIGN.md §2).
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
    // (DESIGN.md §2) — apply the previous frame's outputs, sample
    // inputs — and the bit counter's reset: position = address starts
    // here. Breaks propagate as line idle.
    constexpr TxAction on_break() {
        if (m_state == NodeState::Forward) {
            m_latch_count += 1;
        }
        m_state = NodeState::Forward;
        m_bit_count = 0;
        m_slot_bit = 0;
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
        // Subtraction form, so a parked slot_index near UINT16_MAX can
        // never overflow the boundary compare.
        const bool in_slot = m_bit_count >= m_config.slot_index &&
                             m_bit_count - m_config.slot_index < m_config.slot_bits;
        Bit outgoing = incoming;
        if (in_slot) {
            outgoing = bit_at(m_telemetry, m_slot_bit);
            m_slot_bit += 1;
        }
        m_bit_count += 1;
        return outgoing == Bit::One ? TxAction::EmitOne : TxAction::EmitZero;
    }

    NodeConfig m_config;
    BitSlice m_telemetry;
    NodeState m_state = NodeState::Hunt;
    uint16_t m_bit_count = 0;
    uint16_t m_slot_bit = 0;
    uint32_t m_latch_count = 0;
};

} // namespace oparroy
