// The RX capture path's MMIO glue (DESIGN.md §2): the OPA comparator
// routes internally to TIM2_CH1 (datasheets/CH32V003/notes/opa.md),
// TIM2's PWM-input mode captures each cell's period (CH1, rising edge)
// and high time (CH2, falling edge) (RM §11.3.4), and DMA channels 5/7
// stream the captures into static rings. rx_poll() — called from
// node_main's loop; the image arms no interrupts — drains the rings
// into the burst decoder (firmware/protocol/rx.hpp), which owns all
// symbol semantics. This file owns registers and time only.
//
// Ring discipline: the DMA channels write in lockstep — one period
// write per rising edge, one high write per falling edge — so a single
// read index serves both rings. The drain limit is the *high*
// channel's write position: within a cell the period write lands
// first, so that index has both entries. Feed order per index is
// period, then high — a period completes the *pending* high (the cell
// before it), per rx.hpp's pairing contract.

#include <pins.hpp>

#include "../protocol/bits.hpp"
#include "../protocol/cell.hpp"
#include "../protocol/enum.hpp"
#include "../protocol/node.hpp"
#include "../protocol/rx.hpp"
#include "regs.hpp"
#include "rx.hpp" // this directory's glue declarations, not the protocol's rx.hpp
#include "tx.hpp" // this directory's glue declarations, not the protocol's tx.hpp

#include <cstdint>

namespace {

// 16 cells per ring, 64 B of SRAM total — inside §2's 256 B RX buffer
// budget.
inline constexpr uint32_t ring_cells = 16;

// DMA targets, hardware-written between polls — writable C arrays by
// definition.
// NOLINTNEXTLINE(cppcoreguidelines-avoid-non-const-global-variables,cppcoreguidelines-avoid-c-arrays,modernize-avoid-c-arrays)
volatile uint16_t period_ring[ring_cells];
// NOLINTNEXTLINE(cppcoreguidelines-avoid-non-const-global-variables,cppcoreguidelines-avoid-c-arrays,modernize-avoid-c-arrays)
volatile uint16_t high_ring[ring_cells];

// The node's telemetry is its ENUM stamp (enum.hpp, DESIGN.md §2): the
// slot walk claims each frame's first empty slot and stamps it — the
// find-first-empty-slot discovery that keeps position provision-free.
// The stamp is a placeholder until the personality firmware slice wires
// the real ESIG UNIID and option-byte type byte: zero UNIID, type 0
// ("plain node"). BitSlice adopts a C array (span.hpp); both vsync
// faces are the one stamp — it never changes after boot.
constexpr oparroy::EnumStamp placeholder_stamp = oparroy::pack_stamp(0, 0, 0, 0);
constexpr oparroy::NodeConfig node_config{.slot_bits = oparroy::enum_slot_bits};
constexpr oparroy::DoubleBuffer<oparroy::BitSlice> stamp_latch{
    .front = oparroy::stamp_slice(placeholder_stamp),
    .back = oparroy::stamp_slice(placeholder_stamp)};
static_assert(oparroy::Node::config_valid(node_config, stamp_latch));

// NOLINTNEXTLINE(cppcoreguidelines-avoid-non-const-global-variables) — the one node instance
oparroy::Node node{node_config, stamp_latch};
// NOLINTNEXTLINE(cppcoreguidelines-avoid-non-const-global-variables) — the node's decoder
oparroy::RxDecoder decoder{node};

struct PollState {
    uint32_t read_idx = 0;            // next ring entry to feed
    uint32_t last_progress_ticks = 0; // SysTick of the last drained capture
};

// NOLINTNEXTLINE(cppcoreguidelines-avoid-non-const-global-variables) — rx_poll's carry-over state
PollState poll_state;

// The write position a channel's CNTR encodes: transfers remaining
// counts down from ring_cells and reloads (CIRC mode).
[[nodiscard]] uint32_t write_index(const DmaChannel volatile& dma) {
    return (ring_cells - dma.cntr) % ring_cells;
}

// The capture-stream CFGR value: 16-bit peripheral-to-memory (PSIZE=16
// reads the capture register's low half — the registers are 16-bit
// values), circular, memory-increment, very-high priority (a starved
// channel loses a capture to CCxOF — the decoder's containment case,
// not a silent corruption).
inline constexpr DmaCfgr dma_cfgr_capture = dma_cfgr_pl_very_high | dma_cfgr_msize_16 |
                                            dma_cfgr_psize_16 | dma_cfgr_minc | dma_cfgr_circ |
                                            dma_cfgr_en;

// One capture stream → ring channel. The address cast is the reverse
// of regs.hpp's accessor casts — the DMA's view of the same MMIO
// boundary.
void dma_config(uint32_t channel, const volatile uint32_t& source, const volatile uint16_t* dest) {
    DmaChannel volatile& dma = dma_channel(channel);
    dma.cntr = ring_cells;
    dma.paddr = static_cast<uint32_t>(reinterpret_cast<uintptr_t>(&source));
    dma.maddr = static_cast<uint32_t>(reinterpret_cast<uintptr_t>(dest));
    dma.cfgr.write(dma_cfgr_capture);
}

// Restart both channels at ring base after a sync point (overcapture,
// source flip): the pre-reset stream's pairing is unprovable and the
// decoder is in Hunt — the next break marker realigns the rings by
// construction (the break gap holds no falling edge, so post-marker
// writes alternate period, high, … on matching indices).
void dma_resync() {
    dma_channel(pins::rx_a_period_dma).cfgr.write({}); // all-zero: channel disabled
    dma_channel(pins::rx_a_high_dma).cfgr.write({});
    dma_config(pins::rx_a_period_dma, tim2().ch1cvr, period_ring);
    dma_config(pins::rx_a_high_dma, tim2().ch2cvr, high_ring);
    // Captures during the disabled window set the overcapture flags;
    // they belong to the discarded stream.
    tim2().intfr.clear(tim2_intfr_cc1of | tim2_intfr_cc2of);
    poll_state.read_idx = 0;
    poll_state.last_progress_ticks = systick().cntr;
}

// §3 source select: swap the comparator's positive input (OPP0/PA2 ↔
// OPP1/PD7) and hunt for the new source's first marker. RMW on
// EXTEN_CTR — LDOTRIM and the lock-up monitor share the register.
void flip_source() {
    exten().ctr ^= exten_ctr_opa_psel;
    decoder.resync();
    dma_resync();
}

} // namespace

void rx_init() {
    // Peripheral clocks (the GPIO port clocks are node_main's
    // gpio_init).
    rcc().apb1pcenr |= rcc_apb1pcenr_tim2en;
    rcc().ahbpcenr |= rcc_ahbpcenr_dma1en;

    // Both RX candidates are pulled-down inputs: the internal weak
    // pull-down parks a disconnected line at silence (DESIGN.md §2,
    // the connector-fault measurement). The threshold divider's pin
    // (PA1, OPN0) keeps its floating reset state.
    Gpio volatile& gpioa = gpio(pins::rx_a.port_base);
    configure_pin(gpioa, pins::rx_a.bit, gpio_cfglr_in_pulled);
    gpioa.bcr = 1u << pins::rx_a.bit; // OUTDR=0: pull-down
    Gpio volatile& gpiod = gpio(pins::rx_b.port_base);
    configure_pin(gpiod, pins::rx_b.bit, gpio_cfglr_in_pulled);
    gpiod.bcr = 1u << pins::rx_b.bit;

    // Comparator on, source A selected: OPA_PSEL=0 (OPP0/PA2) and
    // OPA_NSEL=0 (OPN0/PA1) are the zero encodings, so the enable bit
    // is the only set.
    exten().ctr |= exten_ctr_opa_en;

    // PWM-input capture (RM §11.3.4). PSC=0 puts CNT on the 48 MHz
    // tick grid of cell.hpp; ATRLR full range so CNT is reset only by
    // the TI1FP1 trigger.
    Tim2 volatile& tim = tim2();
    tim.psc = 0;
    tim.atrlr = 0xFFFF;
    tim.smcfgr = tim2_smcfgr_ts_ti1fp1 | tim2_smcfgr_sms_reset;
    tim.chctlr1 = tim2_chctlr1_cc1s_in_ti1 | tim2_chctlr1_ic1f_fckint_n8 |
                  tim2_chctlr1_cc2s_in_ti1 | tim2_chctlr1_ic2f_fckint_n8;
    tim.ccer = tim2_ccer_cc1e | tim2_ccer_cc2e | tim2_ccer_cc2p;
    tim.dmaintenr = tim2_dmaintenr_cc1de | tim2_dmaintenr_cc2de;

    // DMA before the counter starts: the streams are aligned from the
    // first capture.
    dma_config(pins::rx_a_period_dma, tim.ch1cvr, period_ring);
    dma_config(pins::rx_a_high_dma, tim.ch2cvr, high_ring);
    tim.ctlr1 = tim2_ctlr1_cen;
}

void rx_poll() {
    // NOLINTNEXTLINE(misc-const-correctness) — const cannot qualify a reference
    Tim2 volatile& tim = tim2();

    // Overcapture: an entry may be lost and ring pairing is unprovable
    // — the decoder contains (drops to Hunt) and the streams restart
    // aligned.
    if ((tim.intfr.read() & (tim2_intfr_cc1of | tim2_intfr_cc2of)) != 0) {
        tx_push(decoder.on_overrun());
        dma_resync();
        return;
    }

    const uint32_t now = systick().cntr;
    const uint32_t write_idx = write_index(dma_channel(pins::rx_a_high_dma));
    if (write_idx != poll_state.read_idx) {
        // ≥ one CNT wrap of edge silence before these captures: the
        // in-stream break marker may have aliased away, so the
        // decoder's backstop delivers the break first (rx.hpp).
        if (now - poll_state.last_progress_ticks >= oparroy::rx_counter_wrap_ticks) {
            // The backstop delivers the break; the sequencer hears it
            // as a frame close like the in-stream marker's.
            (void)decoder.on_silence();
            tx_break();
        }
        while (poll_state.read_idx != write_idx) {
            // The TX mapping (firmware/node/tx.hpp): cell boundaries
            // push the decoder's action; a marker is a frame close
            // (tx_break), never an Idle push — that would discard the
            // frame it closes. on_high's return is always Idle in
            // lockstep (its lockstep-loss containment surfaces at the
            // next period), so there is nothing to push from it. The
            // read index runs modulo ring_cells.
            // NOLINTNEXTLINE(cppcoreguidelines-pro-bounds-constant-array-index)
            const uint16_t period = period_ring[poll_state.read_idx];
            if (period >= oparroy::break_min_ticks) {
                (void)decoder.on_period(period);
                tx_break();
            } else {
                tx_push(decoder.on_period(period));
            }
            // NOLINTNEXTLINE(cppcoreguidelines-pro-bounds-constant-array-index)
            (void)decoder.on_high(high_ring[poll_state.read_idx]);
            poll_state.read_idx = (poll_state.read_idx + 1) % ring_cells;
        }
        poll_state.last_progress_ticks = now;
    }

    // §3 flip policy: edge silence past two frame times means the
    // selected source is dead — try the other one. Edge presence only,
    // never decode quality.
    if (now - poll_state.last_progress_ticks >= oparroy::rx_flip_silence_ticks) {
        flip_source();
    }
}
