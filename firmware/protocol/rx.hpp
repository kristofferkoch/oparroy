#pragma once

// RX burst decode — the adapter from the TIM2 PWM-input capture
// streams to the protocol core (DESIGN.md §2). The capture hardware
// (RM §11.3.4; the MMIO glue is firmware/node/rx.cpp) streams one
// period capture (TIM2_CH1, rising edge) and one high-time capture
// (TIM2_CH2, falling edge) per line cell into DMA rings; this decoder
// turns the capture stream into Node::on_bit / on_illegal_cell /
// on_break calls. Pure symbol logic with no MMIO inside, host-testable
// and harness-proved like the rest of the protocol core (§8).
//
// Pairing: a cell's high time is captured mid-cell, its period at the
// *next* rising edge, so a period capture completes the pending high.
// A period ≥ break_min_ticks is a break marker, not a cell — the gap
// has no falling edge, so the frame's last cell never pairs (the frame
// format owns a trailing sacrificial cell; frame format is a later
// slice). After a marker the pairing phase is clean by construction:
// marker, high, period, high, period, …
//
// Break detection is two-layered. The in-stream marker covers gaps
// shorter than one 16-bit counter wrap (65536 ticks ≈ 1.37 ms at
// 48 MHz); past a wrap the across-gap capture aliases back into the
// legal window and the marker vanishes, so the glue measures edge
// silence on the SysTick timebase (same HCLK) and calls on_silence()
// before feeding post-gap captures — that delivers the break and arms
// GapDiscard to swallow the aliased across-gap "period" without a
// second on_break.
//
// Containment (§2): a period with no pending high, or a second high
// with no period between, means the streams lost lockstep (a capture
// was dropped) and pairing is unprovable — the decoder reports an
// illegal cell (the node mutes until the next break) and returns to
// Hunt; the next marker resyncs. DMA overcapture (CCxOF) is the same
// shape: on_overrun() contains and hunts, and the glue restarts both
// DMA channels so the streams restart aligned.

#include "bits.hpp"
#include "cell.hpp"
#include "node.hpp"

#include <cstdint>

namespace oparroy {

// The glue's silence yardsticks, in 48 MHz ticks (SysTick and TIM2
// share HCLK, so the comparison is exact):
// - rx_counter_wrap_ticks: the 16-bit CNT wrap. Edge silence at or
//   past one wrap makes the in-stream break marker unreliable
//   (aliasing, above) — the glue must call on_silence() first.
// - rx_flip_silence_ticks: the §3 RX source-flip policy — no edges for
//   more than two frame times (the largest legal frame, the pre-sized
//   ENUM, is ~1.1 ms including its break) means the selected source is
//   dead. Edge presence only, never decode quality — the
//   intermittent-fault strategy's keepalive direction: a healthy line
//   is never silent.
inline constexpr uint32_t rx_counter_wrap_ticks = 65536;
inline constexpr uint32_t rx_flip_silence_ticks = 120'000; // 2.5 ms

class RxDecoder {
public:
    enum class Phase : uint8_t {
        Hunt,       // pre-sync: discard until the first break marker
        Live,       // aligned: highs pair with the following period
        GapDiscard, // on_silence armed: swallow one across-gap entry
    };

    // The node reference is the decoder's only coupling — the glue
    // owns the Node.
    constexpr explicit RxDecoder(Node& node) : m_node(node) {}

    // One TIM2_CH1 capture: the period of the cell that just ended, or
    // a break marker.
    [[nodiscard]] constexpr TxAction on_period(uint16_t ticks) {
        if (ticks >= break_min_ticks) {
            // Break marker. The pending high is the frame's last cell,
            // whose period is the gap itself — undecodable, dropped.
            m_high_valid = false;
            if (m_phase == Phase::GapDiscard) {
                // on_silence() already delivered this break.
                m_phase = Phase::Live;
                return TxAction::Idle;
            }
            m_phase = Phase::Live;
            return m_node.on_break();
        }
        switch (m_phase) {
        case Phase::Hunt:
            // Pre-sync garbage: position unknown, nothing decodes.
            return TxAction::Idle;
        case Phase::GapDiscard:
            // The aliased across-gap measurement — swallowed, never
            // decoded. Pairing resumes clean from the next capture.
            m_phase = Phase::Live;
            return TxAction::Idle;
        case Phase::Live:
            break;
        }
        if (!m_high_valid) {
            return lockstep_lost();
        }
        m_high_valid = false;
        const CellDecode decode =
            decode_cell(CapturedCell{.period_ticks = ticks, .high_ticks = m_high});
        if (decode == CellDecode::Illegal) {
            return m_node.on_illegal_cell();
        }
        return m_node.on_bit(decode == CellDecode::One ? Bit::One : Bit::Zero);
    }

    // One TIM2_CH2 capture: the high time of the cell in flight.
    [[nodiscard]] constexpr TxAction on_high(uint16_t ticks) {
        if (m_phase != Phase::Live) {
            return TxAction::Idle;
        }
        if (m_high_valid) {
            return lockstep_lost();
        }
        m_high = ticks;
        m_high_valid = true;
        return TxAction::Idle;
    }

    // The glue's alias backstop: it measured ≥ rx_counter_wrap_ticks
    // of edge-free line before the captures it is about to feed.
    [[nodiscard]] constexpr TxAction on_silence() {
        m_high_valid = false;
        if (m_phase == Phase::Hunt) {
            // Never synced (or resync()ed): the next marker delivers
            // the break; nothing to double-deliver.
            return TxAction::Idle;
        }
        m_phase = Phase::GapDiscard;
        return m_node.on_break();
    }

    // DMA overcapture (TIM2_INTFR CCxOF): an entry may be lost and
    // lockstep is unprovable — contain, then hunt for the next marker.
    // The glue restarts both DMA channels alongside this call.
    [[nodiscard]] constexpr TxAction on_overrun() {
        m_high_valid = false;
        m_phase = Phase::Hunt;
        return m_node.on_illegal_cell();
    }

    // RX source flip (§3): the new source's frame phase is unknown —
    // discard until its first marker; that marker's on_break resyncs
    // the node (slot counting is source-invariant, §3).
    constexpr void resync() {
        m_high_valid = false;
        m_phase = Phase::Hunt;
    }

    [[nodiscard]] constexpr Phase phase() const {
        return m_phase;
    }

private:
    constexpr TxAction lockstep_lost() {
        m_high_valid = false;
        m_phase = Phase::Hunt;
        return m_node.on_illegal_cell();
    }

    // A non-owning adapter over the glue's Node: bound at construction
    // and never reassigned, so a reference — null is unrepresentable.
    // NOLINTNEXTLINE(cppcoreguidelines-avoid-const-or-ref-data-members)
    Node& m_node;
    uint16_t m_high = 0;
    bool m_high_valid = false;
    Phase m_phase = Phase::Hunt;
};

} // namespace oparroy
