#pragma once

// TX streamers (DESIGN.md §2): the Node's TxAction stream becomes the
// compare-value stream the TIM1 DMA glue plays onto the wire (the MMIO
// half is firmware/node/tx.cpp). Pure symbol logic with no time inside,
// host-testable and harness-proved like the rest of the protocol core
// (§8). Two rungs share the pop() contract below — the glue drives the
// cut-through endpoint (TxCutThrough), and the store-and-forward
// fallback (TxSequencer) stays in the tree for the timing-closure
// escape hatch.
//
// The played stream, pop() per cell:
// - a re-emitted bit, snapped to nominal (t0h_ticks/t1h_ticks —
//   encode_cell's compare half; ATRLR holds the 60-tick period),
// - tx_break_cells idle cells (tx_idle_compare) after every frame, so
//   the downstream break detector always sees ≥ break_min_ticks of low,
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
// Containment (§2): an Idle action means the node stopped regenerating
// (Hunt or Mute). Cut-through mutes and lets its FIFO drain to idle;
// store-and-forward discards the accumulating frame. A full FIFO/ring
// is the same shape for both — drop, never regenerate a partial frame.
// on_break() resyncs: cut-through drops its backlog and re-arms the
// re-emitted break's idle run; store-and-forward closes the frame.

#include "../lib/array.hpp"
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

// Cut-through FIFO capacity, in cells. Sized by the worst-case fill the
// re-emitted break forces: the idle run delays the next frame, whose
// bits accumulate while the idles play (~50 for a pre-sized ENUM at the
// ±4.4 % relative HSI drift), then the rest of the frame drifts (~35) —
// ~85 cells steady-state plus the ≤ 16-cell RX burst, so 128 (256 B)
// with margin. Full derivation in docs/size-estimate.md.
inline constexpr uint16_t tx_cut_through_cells = 128;

// Per-bit cut-through forwarding (DESIGN.md §2 — the endpoint): each
// decoded bit is re-emitted snapped to nominal after a bounded pipeline
// delay, so decode jitter is per-hop, never cumulative (§2 re-timing). A
// bounded compare FIFO absorbs the RX↔TX rate mismatch — upstream and
// local HSI drift ≤ ±2.2 % each, so a pre-sized ENUM frame drifts ≤ ~37
// cells — plus the ≤ 16-cell RX burst. The break is re-emitted, never
// merely inherited: the drift backlog would compress the output gap
// below break_min_ticks, so on_break() drops the backlog and re-arms a
// full tx_break_cells idle run (m_idle_remaining, drained before the
// FIFO so the next frame's bits wait out the break).
template <uint16_t CapacityCells = tx_cut_through_cells> class TxCutThrough {
public:
    static_assert(CapacityCells > 0, "a cut-through FIFO must hold at least one cell");

    // The compare ring zeroes elementwise, not by a whole-member {}:
    // value-initializing the class-typed Array makes clang's front-end
    // batch the ctor's zero-init into one llvm.memset, which klee 3.2
    // doesn't implement (klee/tx.cpp's ShadowTx comment) — the proof
    // harness would die at the first instruction. On target gcc lowers
    // the loop to the same memset the = {} gave (the freestanding
    // runtime provides it); cells are read only below m_queued, so the
    // init is defensive either way.
    constexpr TxCutThrough() {
        for (uint16_t& cell : m_compare) {
            cell = 0;
        }
    }

    // One Node output. Emit* enqueues the nominal compare; Idle is
    // containment (Hunt or Mute) — stop regenerating and let the FIFO
    // drain to idle until the next break. Enqueueing past capacity is
    // the same shape: mute, never corrupt a cell mid-frame.
    constexpr void push(TxAction action) {
        if (m_muted) {
            return;
        }
        switch (action) {
        case TxAction::EmitZero:
            enqueue(t0h_ticks);
            break;
        case TxAction::EmitOne:
            enqueue(t1h_ticks);
            break;
        case TxAction::Idle:
            m_muted = true;
            break;
        }
    }

    // The frame gap: resync — drop any backlog (mute containment), clear
    // the mute, and re-arm the re-emitted break's idle run so the output
    // gap stays ≥ break_min_ticks regardless of the drained drift.
    constexpr void on_break() {
        m_head = 0;
        m_queued = 0;
        m_muted = false;
        m_idle_remaining = tx_break_cells;
    }

    // The next cell's compare value: the re-armed break's idle run
    // first, then the FIFO, then idle when nothing is queued.
    [[nodiscard]] constexpr uint16_t pop() {
        if (m_idle_remaining > 0) {
            m_idle_remaining -= 1;
            return tx_idle_compare;
        }
        if (m_queued == 0) {
            return tx_idle_compare;
        }
        const uint16_t compare = m_compare[m_head];
        m_head = static_cast<uint16_t>((m_head + 1) % CapacityCells);
        m_queued -= 1;
        return compare;
    }

    [[nodiscard]] constexpr uint16_t queued() const {
        return m_queued;
    }
    [[nodiscard]] constexpr uint16_t idle_remaining() const {
        return m_idle_remaining;
    }
    [[nodiscard]] constexpr bool muted() const {
        return m_muted;
    }

private:
    constexpr void enqueue(uint16_t compare) {
        if (m_queued >= CapacityCells) {
            m_muted = true;
            return;
        }
        const uint32_t pos = (static_cast<uint32_t>(m_head) + m_queued) % CapacityCells;
        // NOLINTNEXTLINE(cppcoreguidelines-pro-bounds-constant-array-index)
        m_compare[static_cast<uint16_t>(pos)] = compare;
        m_queued += 1;
    }

    // The DMA refill runs ahead of the wire, but the storage is only
    // ever written by the sequencer itself — a plain Array, zeroed by
    // the constructor (see its comment for the elementwise shape).
    lib::Array<uint16_t, CapacityCells> m_compare;
    uint16_t m_head = 0;           // next cell to play
    uint16_t m_queued = 0;         // cells at [m_head, …)
    uint16_t m_idle_remaining = 0; // re-armed break idle cells still owed
    bool m_muted = false;
};

// Store-and-forward by whole frame (DESIGN.md §2 — the fallback rung
// made real): bits accumulate until the frame's break closes it; only
// closed frames play, gap-free at the nominal cell rate by construction
// — no RX↔TX rate-matching (upstream faster grows the pending frame,
// slower idles between frames) — at ~one frame of latency per hop.
//
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
        const Bit bit = bit_at(m_bits, m_head);
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
    // ever written by the Sequencer itself — a plain Array.
    lib::Array<uint8_t, CapacityBits / 8> m_bits{};
    uint16_t m_head = 0;           // next bit to play
    uint16_t m_playable = 0;       // closed bits at [m_head, …)
    uint16_t m_pending = 0;        // accumulating bits after the playable run
    uint16_t m_idle_remaining = 0; // post-frame idle cells still owed
    bool m_dropped = false;
};

} // namespace oparroy
