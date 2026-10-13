// The TX streaming path's MMIO glue (DESIGN.md §2): TIM1's CH1 (tx_a,
// PD2) and CH3 (tx_b, PC3) run PWM mode 1 at the 60-tick cell period,
// and DMA channels 2/6 stream one compare value per cell into CH1CVR/
// CH3CVR — identical values onto both directions (§3). The stream is
// the store-and-forward sequencer's pop() output (firmware/protocol/
// tx.hpp owns all symbol semantics); this file owns registers and time
// only. tx_poll() — called from node_main's loop; the image arms no
// interrupts — refills the rings ahead of the wire.
//
// Brake (§4): PC2 is TIM1_BKIN, wired to the watchdog's sel — low when
// bypass is engaged — so BKP=0 (active low) and BKE brakes both
// channels the moment the bypass engages; OSSI + OISx=0 parks the lines
// low under MOE=0. AOE stays off: re-arming MOE is a deliberate
// firmware act, never an auto-resume into stale rings.
//
// Idle cells play as a one-tick compare (tx_idle_compare, tx.hpp): the
// sliver never reaches a downstream capture, and every played cell
// produces the mid-cell compare match that issues the channel's DMA
// request — the stream never depends on the RM-silent CHxCVR=0 corner
// (notes/timers.md).
//
// Ring discipline: one producer index serves both rings — the channels
// request in lockstep (same values, same cadence), and tx_poll VERIFYs
// the read positions agree. A one-poll mismatch is transient (the two
// same-cycle requests are arbitrated a few HCLK cycles apart); two
// consecutive mismatching polls — a full main-loop turn apart — mean a
// lost beat, and the directions would drift a cell apart.

#include <pins.hpp>

#include "../lib/verify.hpp"
#include "../protocol/cell.hpp"
#include "../protocol/node.hpp"
#include "../protocol/tx.hpp"
#include "regs.hpp"
#include "tx.hpp"

#include <cstdint>

namespace {

// 16 cells per ring, 64 B of SRAM for the pair — with the RX rings at
// 64 B, the DMA rings hold at half of §2's 256 B buffer budget. The
// sequencer's frame queue is separate storage (tx.hpp).
inline constexpr uint32_t ring_cells = 16;

// DMA sources, hardware-read between polls — writable C arrays by
// definition.
// NOLINTNEXTLINE(cppcoreguidelines-avoid-non-const-global-variables,cppcoreguidelines-avoid-c-arrays,modernize-avoid-c-arrays)
volatile uint16_t compare_ring_a[ring_cells];
// NOLINTNEXTLINE(cppcoreguidelines-avoid-non-const-global-variables,cppcoreguidelines-avoid-c-arrays,modernize-avoid-c-arrays)
volatile uint16_t compare_ring_b[ring_cells];

// NOLINTNEXTLINE(cppcoreguidelines-avoid-non-const-global-variables) — the one sequencer instance
oparroy::TxSequencer<> sequencer;

struct PollState {
    uint32_t prod_idx = 0;   // next ring slot to fill
    uint32_t last_read = 0;  // read position at the previous poll
    uint32_t queued = 0;     // slots written but not yet DMA-consumed
    bool mismatched = false; // the previous poll saw a read-position skew
};

// NOLINTNEXTLINE(cppcoreguidelines-avoid-non-const-global-variables) — tx_poll's carry-over state
PollState poll_state;

// The read position a channel's CNTR encodes: transfers remaining
// counts down from ring_cells and reloads (CIRC mode).
[[nodiscard]] uint32_t read_index(const DmaChannel volatile& dma) {
    return (ring_cells - dma.cntr) % ring_cells;
}

// The compare-stream CFGR value: 16-bit memory-to-peripheral (PSIZE=16
// writes the compare register's low half), circular, memory-increment,
// very-high priority (a starved channel plays a stale cell — a wrong
// bit on the wire, the one failure worse than silence).
inline constexpr DmaCfgr dma_cfgr_compare = dma_cfgr_pl_very_high | dma_cfgr_msize_16 |
                                            dma_cfgr_psize_16 | dma_cfgr_minc | dma_cfgr_dir |
                                            dma_cfgr_circ | dma_cfgr_en;

// One compare stream ← ring channel. The address cast is the reverse
// of regs.hpp's accessor casts — the DMA's view of the same MMIO
// boundary.
void dma_config(uint32_t channel, const volatile uint32_t& dest, const volatile uint16_t* source) {
    DmaChannel volatile& dma = dma_channel(channel);
    dma.cntr = ring_cells;
    dma.paddr = static_cast<uint32_t>(reinterpret_cast<uintptr_t>(&dest));
    dma.maddr = static_cast<uint32_t>(reinterpret_cast<uintptr_t>(source));
    dma.cfgr.write(dma_cfgr_compare);
}

} // namespace

void tx_init() {
    // Peripheral clocks: TIM1, the DMA (shared with RX), and GPIO port
    // C (tx_b, tx_kill) — port D's clock is node_main's gpio_init.
    rcc().apb2pcenr |= rcc_apb2pcenr_tim1en | rcc_apb2pcenr_iopcen;
    rcc().ahbpcenr |= rcc_ahbpcenr_dma1en;

    // tx_a/tx_b are TIM1's default pin mapping (no AFIO remap);
    // tx_kill is a floating input — the watchdog's sel drives it.
    Gpio volatile& gpiod = gpio(pins::tx_a.port_base);
    configure_pin(gpiod, pins::tx_a.bit, gpio_cfglr_out_af_pp_10mhz);
    Gpio volatile& gpioc = gpio(pins::tx_b.port_base);
    configure_pin(gpioc, pins::tx_b.bit, gpio_cfglr_out_af_pp_10mhz);
    configure_pin(gpioc, pins::tx_kill.bit, gpio_cfglr_in_floating);

    // Rings start all-idle: the line is legally low from the first
    // cell, and the producer displaces the prefill in queue order.
    for (uint32_t i = 0; i < ring_cells; ++i) {
        // NOLINTNEXTLINE(cppcoreguidelines-pro-bounds-constant-array-index)
        compare_ring_a[i] = oparroy::tx_idle_compare;
        // NOLINTNEXTLINE(cppcoreguidelines-pro-bounds-constant-array-index)
        compare_ring_b[i] = oparroy::tx_idle_compare;
    }
    poll_state.queued = ring_cells;

    // PWM at the cell grid (RM §10.4; notes/timers.md's SDK-checked
    // recipe): PSC=0 puts CNT on the 48 MHz tick grid of cell.hpp,
    // ATRLR one less than the period, RPTCR=0 for an update event on
    // every overflow. CH1/CH3 PWM mode 1 with preload, active-high
    // (the line idles low), idle-state levels low under MOE=0.
    Tim1 volatile& tim = tim1();
    tim.psc = 0;
    tim.atrlr = oparroy::cell_period_nominal_ticks - 1;
    tim.rptcr = 0;
    tim.ch1cvr = oparroy::tx_idle_compare;
    tim.ch3cvr = oparroy::tx_idle_compare;
    tim.chctlr1 = tim1_chctlr1_oc1m_pwm1 | tim1_chctlr1_oc1pe;
    tim.chctlr2 = tim1_chctlr2_oc3m_pwm1 | tim1_chctlr2_oc3pe;
    tim.ccer = tim1_ccer_cc1e | tim1_ccer_cc3e;
    tim.ctlr2 = 0; // OIS1 = OIS3 = 0: idle levels low
    tim.bdtr = tim1_bdtr_ossi | tim1_bdtr_bke | tim1_bdtr_moe;
    tim.dmaintenr = tim1_dmaintenr_cc1de | tim1_dmaintenr_cc3de;

    // DMA before the counter starts: the streams are aligned from the
    // first compare. UG latches the preloads (RM §10.3.5 — the SDK's
    // TIM_TimeBaseInit ends with it) before CEN.
    dma_config(pins::tx_a_tx_dma, tim.ch1cvr, compare_ring_a);
    dma_config(pins::tx_b_tx_dma, tim.ch3cvr, compare_ring_b);
    tim.swevgr = tim1_swevgr_ug;
    tim.ctlr1 = tim1_ctlr1_cen;
}

void tx_push(oparroy::TxAction action) {
    sequencer.push(action);
}

void tx_break() {
    sequencer.on_break();
}

void tx_poll() {
    const uint32_t read_a = read_index(dma_channel(pins::tx_a_tx_dma));
    const uint32_t read_b = read_index(dma_channel(pins::tx_b_tx_dma));
    if (read_a != read_b) {
        // Transient arbitration skew lasts a few HCLK cycles; a skew
        // surviving a full loop turn is a lost DMA beat (the header
        // comment).
        VERIFY(!poll_state.mismatched);
        poll_state.mismatched = true;
        return;
    }
    poll_state.mismatched = false;

    // The DMA consumed (read − last_read) slots since the previous
    // poll; top the rings back up, one pop per slot. queued < ring_cells
    // keeps the producer off the DMA's next-read slot by construction.
    poll_state.queued -= (read_a - poll_state.last_read) % ring_cells;
    poll_state.last_read = read_a;
    while (poll_state.queued < ring_cells) {
        const uint16_t compare = sequencer.pop();
        // NOLINTNEXTLINE(cppcoreguidelines-pro-bounds-constant-array-index)
        compare_ring_a[poll_state.prod_idx] = compare;
        // NOLINTNEXTLINE(cppcoreguidelines-pro-bounds-constant-array-index)
        compare_ring_b[poll_state.prod_idx] = compare;
        poll_state.prod_idx = (poll_state.prod_idx + 1) % ring_cells;
        poll_state.queued += 1;
    }
}
