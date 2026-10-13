#pragma once

// TX store-and-forward sequencer (DESIGN.md §2 — the §2 fallback rung
// made real: per-bit cut-through forwarding is the endpoint; this is
// the correctness rung under it). Consumes the Node's TxAction stream and
// produces the compare-value stream the TIM1 DMA glue plays onto the
// wire (the MMIO half is firmware/node/tx.cpp). Pure symbol logic with
// no time inside, host-testable and harness-proved like the rest of the
// protocol core (§8).
//
// Store-and-forward by whole frame: bits accumulate until the frame's
// break closes the frame; only closed frames play. Playback is
// therefore gap-free at the nominal cell rate by construction — no
// RX↔TX rate-matching is needed (upstream faster just grows the pending
// frame; upstream slower just idles the line between frames). The cost
// is ~one frame of latency per hop, which this rung accepts.
//
// The played stream, pop() per cell:
// - a closed frame's bits, snapped to nominal (t0h_ticks/t1h_ticks —
//   encode_cell's compare half; ATRLR holds the 60-tick period),
// - then tx_break_cells idle cells (tx_idle_compare) before any later
//   frame, so every frame on the wire is preceded by an idle run the
//   downstream break detector must see,
// - tx_idle_compare whenever nothing is queued (pop-or-idle: the glue
//   can always refill the DMA rings; the line just idles).
//
// Idle plays as a one-tick compare, not 0: the 20.8 ns sliver is
// invisible to the downstream capture path (the TIM2 input filter
// rejects anything under ~167 ns — ic1f_fckint_n8 in rx.cpp — and the
// 470 Ω series R plus line capacitance attenuates it further), so
// electrically the line is low. In return every played cell, idle or
// not, produces an ordinary mid-cell compare match — and the CCx DMA
// request that paces the compare stream is per-channel per-match.
// Whether a CVR=0 (or CVR ≥ ATRLR) corner even generates the match is
// undocumented (notes/timers.md), so the stream never depends on it.
//
// Containment (§2): an Idle action while a frame is accumulating means
// the node went Mute (in Forward on_bit never returns Idle), and an
// over-full ring is the same shape — the accumulating frame is
// *discarded*, never regenerated, and nothing accumulates until the
// next break. on_break() closes the accumulating frame and clears the
// discard.

#include "../lib/span.hpp"
#include "bits.hpp"
#include "cell.hpp"
#include "node.hpp"

#include <cstdint>

namespace oparroy {

// The idle run a played frame is followed by, in cells. Downstream must
// measure ≥ break_min_ticks of idle: the run's real length is
// tx_break_cells × 60 / f_tx and downstream counts it at f_rx, so with
// the HSI's ±2.2 % worst case at both ends the count is
// tx_break_cells × 60 × (1−0.022)/(1+0.022) ≥ break_min_ticks, i.e.
// tx_break_cells ≥ 41.8. 48 adds ~15 % margin.
inline constexpr uint16_t tx_break_cells = 48;

// An idle cell's compare value: one tick of high per 60-tick cell — a
// 20.8 ns sliver the downstream capture filter rejects, so the line is
// electrically low, while the compare match that paces the DMA stream
// still fires mid-cell (the header comment gives the full argument).
inline constexpr uint16_t tx_idle_compare = 1;

// CapacityBits is a template parameter so the KLEE/fuzz harnesses can
// prove the ring wraparound and overflow paths at tiny capacities
// (runtime.hpp's width-generic proof pattern); the target uses the
// default, one frame_max_bits frame.
template <uint16_t CapacityBits = frame_max_bits> class TxSequencer {
public:
    static_assert(CapacityBits % 8 == 0, "bit-packed storage is whole bytes");

    // One Node output. Emit* appends the bit to the accumulating frame;
    // Idle while accumulating is containment — discard the partial
    // frame. Idle with nothing accumulating is a no-op (Hunt, Mute).
    constexpr void push(TxAction action) {
        switch (action) {
        case TxAction::Idle:
            m_pending = 0;
            m_dropped = true;
            break;
        case TxAction::EmitZero:
        case TxAction::EmitOne:
            append(action == TxAction::EmitOne ? Bit::One : Bit::Zero);
            break;
        }
    }

    // The frame's break (the glue maps the decoder's break deliveries
    // here — the marker capture and the on_silence backstop): close the
    // accumulating frame, making it playable, and start a fresh one.
    constexpr void on_break() {
        m_playable += m_pending;
        m_pending = 0;
        m_dropped = false;
    }

    // The next cell's compare value, per the stream contract above.
    [[nodiscard]] constexpr uint16_t pop() {
        if (m_idle_remaining > 0) {
            m_idle_remaining -= 1;
            return tx_idle_compare;
        }
        if (m_playable == 0) {
            return tx_idle_compare;
        }
        const Bit bit = bit_at(lib::Span<const uint8_t>{m_bits}, m_head);
        m_head = static_cast<uint16_t>((m_head + 1) % CapacityBits);
        m_playable -= 1;
        if (m_playable == 0) {
            m_idle_remaining = tx_break_cells;
        }
        return bit == Bit::One ? t1h_ticks : t0h_ticks;
    }

    [[nodiscard]] constexpr uint16_t playable_bits() const {
        return m_playable;
    }
    [[nodiscard]] constexpr uint16_t pending_bits() const {
        return m_pending;
    }

private:
    constexpr void append(Bit bit) {
        if (m_dropped) {
            // A discarded frame accumulates nothing until the next
            // break — otherwise the tail of an over-long frame would
            // close and play as a truncated one.
            return;
        }
        if (m_playable + m_pending >= CapacityBits) {
            // Resource containment: playing frame + accumulating frame
            // exceed the ring. Drop the accumulating frame; the playing
            // one is known-good and finishes.
            m_pending = 0;
            m_dropped = true;
            return;
        }
        const uint32_t pos =
            (static_cast<uint32_t>(m_head) + m_playable + m_pending) % CapacityBits;
        const auto index = static_cast<uint16_t>(pos);
        const auto mask = static_cast<uint8_t>(0x80u >> (index % 8));
        uint8_t& byte = m_bits[index / 8];
        byte = static_cast<uint8_t>(bit == Bit::One ? byte | mask : byte & ~mask);
        m_pending += 1;
    }

    // The DMA refill runs ahead of the wire, but the storage is only
    // ever written by the Sequencer itself — a plain array.
    // NOLINTNEXTLINE(cppcoreguidelines-avoid-c-arrays,modernize-avoid-c-arrays)
    uint8_t m_bits[CapacityBits / 8] = {};
    uint16_t m_head = 0;           // next bit to play
    uint16_t m_playable = 0;       // closed bits at [m_head, …)
    uint16_t m_pending = 0;        // accumulating bits after the playable run
    uint16_t m_idle_remaining = 0; // post-frame idle cells still owed
    bool m_dropped = false;
};

} // namespace oparroy
