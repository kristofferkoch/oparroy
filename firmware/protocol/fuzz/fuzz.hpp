#pragma once

// Fault-injection shims for the fuzz harnesses (DESIGN.md §8 — SQLite's
// every-boundary doctrine): raw fuzzer bytes become the failure modes
// the protocol core must survive — line errors and timer glitches
// (cells with arbitrary timing, window boundaries included),
// dropped/partial frames (truncated streams, breaks mid-slot), line-low
// timeouts (break events), and brown-outs (node reset mid-stream).
// Engine-agnostic: any fuzzer driving LLVMFuzzerTestOneInput reuses
// these harnesses unchanged (libFuzzer now, AFL++'s compat driver
// later).

#include "../../lib/span.hpp"
#include "../bits.hpp"
#include "../cell.hpp"
#include "../node.hpp"

#include <cstddef>
#include <cstdint>

// The fuzz-side proof statement, KLEE_PROVE's sibling: a violated
// invariant traps, and the engine reports the input as a crash
// artifact. A VERIFY-class macro — the blessed preprocessor use beyond
// includes and guards (code-std-cpp.md#6-constants-and-configuration). if/else form, not do-while —
// cppcoreguidelines-avoid-do-while is in the tidy set (code-std.md#3-enforcement-split).
// NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#define FUZZ_PROVE(condition)                                                                      \
    if (condition) {                                                                               \
    } else {                                                                                       \
        __builtin_trap();                                                                          \
    }

namespace oparroy::fuzz {

// Consuming view over the fuzzer input — the project-owned
// FuzzedDataProvider, so harnesses need no libFuzzer headers
// (code-std-cpp.md#1-language-and-toolchain's freestanding subset). Reads past the end yield 0:
// a short input is a zero-padded one, never an error.
class Cursor {
public:
    constexpr explicit Cursor(lib::Span<const uint8_t> bytes) : m_bytes(bytes) {}

    [[nodiscard]] constexpr uint8_t take_u8() {
        const uint8_t value = m_pos < m_bytes.size() ? m_bytes[m_pos] : uint8_t{0};
        m_pos += 1;
        return value;
    }

    // Little-endian.
    [[nodiscard]] constexpr uint16_t take_u16() {
        const auto lo = static_cast<uint16_t>(take_u8());
        return static_cast<uint16_t>(lo | (static_cast<uint16_t>(take_u8()) << 8));
    }

    [[nodiscard]] constexpr size_t remaining() const {
        return m_pos < m_bytes.size() ? m_bytes.size() - m_pos : 0;
    }

private:
    lib::Span<const uint8_t> m_bytes;
    size_t m_pos = 0;
};

// One injected fault. A cell carries arbitrary timer captures — legal
// timing, line errors, and glitches at the 43/77-tick window boundaries
// all look the same to the byte stream. Stream end anywhere is a
// dropped/partial frame by construction.
enum class EventKind : uint8_t {
    Cell,
    Break,
    Reset,
};

struct Event {
    EventKind kind;
    CapturedCell cell;
};

// Event grammar: 3/5 cells (depth into frames beats config noise), 1/5
// breaks, 1/5 resets. A cell event costs 5 bytes: selector, period
// (u16), high (u16).
[[nodiscard]] constexpr Event next_event(Cursor& cursor) {
    const uint8_t selector = cursor.take_u8();
    switch (selector % 5) {
    case 0:
    case 1:
    case 2:
        return Event{.kind = EventKind::Cell,
                     .cell = CapturedCell{.period_ticks = cursor.take_u16(),
                                          .high_ticks = cursor.take_u16()}};
    case 3:
        return Event{.kind = EventKind::Break, .cell = CapturedCell{}};
    default:
        return Event{.kind = EventKind::Reset, .cell = CapturedCell{}};
    }
}

// Shadow model of one node's view of the input stream — assertions
// check this independent model, never the implementation under test
// (code-std.md#4-tests; the klee/garbage.cpp pattern). Written from the
// contract (node.hpp, DESIGN.md §2): Hunt until the first break,
// Forward with on-the-fly slot stamping, Mute after an illegal cell or
// an over-long frame, resync on break.
class Shadow {
public:
    constexpr Shadow(NodeConfig config, BitSlice telemetry)
        : m_config(config), m_telemetry(telemetry) {}

    // The TxAction the contract requires for one decoded cell.
    constexpr TxAction expect(CellDecode decode, Bit incoming) {
        if (!m_seen_break || m_muted) {
            return TxAction::Idle;
        }
        if (decode == CellDecode::Illegal || m_bit_count >= frame_max_bits) {
            m_muted = true;
            return TxAction::Idle;
        }
        Bit outgoing = incoming;
        const bool in_slot = m_bit_count >= m_config.slot_index &&
                             m_bit_count - m_config.slot_index < m_config.slot_bits;
        if (in_slot) {
            outgoing =
                bit_at(m_telemetry, static_cast<uint16_t>(m_bit_count - m_config.slot_index));
        }
        m_bit_count += 1;
        return outgoing == Bit::One ? TxAction::EmitOne : TxAction::EmitZero;
    }

    constexpr void on_break() {
        // The vsync latch fires only when breaking out of a frame in
        // progress — Hunt and Mute don't latch (node.hpp).
        if (m_seen_break && !m_muted) {
            m_latch_count += 1;
        }
        m_seen_break = true;
        m_muted = false;
        m_bit_count = 0;
    }

    constexpr void on_reset() {
        m_seen_break = false;
        m_muted = false;
        m_bit_count = 0;
        m_latch_count = 0;
    }

    [[nodiscard]] constexpr uint32_t latch_count() const {
        return m_latch_count;
    }

private:
    NodeConfig m_config;
    BitSlice m_telemetry;
    bool m_seen_break = false;
    bool m_muted = false;
    uint32_t m_bit_count = 0;
    uint32_t m_latch_count = 0;
};

} // namespace oparroy::fuzz
