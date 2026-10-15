// Node firmware: the boot-time personality stamp (personality.cpp —
// ESIG UNIID + option-byte type byte), 48 MHz clock init, the §2 RX
// burst-decode capture path (rx.cpp), the §2 TX compare-streaming path
// (tx.cpp), the §4 keep-alive strobe on PD3, and the working-LED
// heartbeat on PD0 — one polled loop, no interrupts anywhere.
//
// The strobe is a software-toggled plain GPIO paced off SysTick. The
// bring-up image used TIM2_CH2 hardware PWM, but the RX capture claims
// TIM2 outright: PWM-input mode needs CH1 and CH2 both as inputs
// (CC2S=10, RM §11.3.4) and slave-mode reset puts CNT under the
// trigger's control (RM §11.4.3), so no channel is left for an
// independent PWM. Software strobing also closes a bypass hole:
// hardware PWM would have kept the charge pump fed through a firmware
// hang, and §3 lists a hung MCU as a bypass case. The pump's
// τ ≈ 0.47 ms (§4) tolerates the loop's jitter by two orders of
// magnitude.
//
// The heartbeat and strobe derive from SysTick free-running at HCLK.
// extern "C", never returns (code-std-cpp.md#1-language-and-toolchain).

#include <pins.hpp>

#include "personality.hpp"
#include "regs.hpp"
#include "rx.hpp"
#include "tx.hpp"

#include <cstdint>

namespace {

// Clock plan (rcc-clocks.md): HSI 24 MHz ×2 PLL → 48 MHz SYSCLK, AHB /1.
inline constexpr uint32_t hclk_hz = 48'000'000;

void clock_init() {
    // Flash wait states BEFORE the faster clock (RM §16.3.1).
    flash().actlr = flash_actlr_latency_1ws;
    // HPRE=/1 (the reset value is /3 — 8 MHz HCLK, rcc-clocks.md),
    // PLLSRC=HSI; both are the zero encoding.
    rcc().cfgr0 = 0;
    // HSI is on out of reset; start the PLL and wait for lock. Hardware
    // guarantees the lock, so the poll needs no timeout
    // (code-std-cpp.md#2-control-flow).
    rcc().ctlr |= rcc_ctlr_pllon;
    while ((rcc().ctlr & rcc_ctlr_pllrdy) == 0) {}
    // Switch SYSCLK to the PLL and verify the switch took (SWS reads
    // back 10b).
    rcc().cfgr0 = rcc_cfgr0_sw_pll;
    while ((rcc().cfgr0 & rcc_cfgr0_sws_mask) != rcc_cfgr0_sws_pll) {}
}

void gpio_init() {
    // Port clocks for the pins this image drives: A (RX source A), D
    // (RX source B, strobe, heartbeat, TX A). TX's port C clock and
    // pins are tx_init's. No AFIO gate: the alternate functions in use
    // (TIM1's TX channels, tx.cpp) are default pin mappings, and the
    // OPA→TIM2_CH1 route is internal (notes/opa.md).
    rcc().apb2pcenr |= rcc_apb2pcenr_iopaen | rcc_apb2pcenr_iopden;
    Gpio volatile& gpiod = gpio(pins::gpio_d_base);
    configure_pin(gpiod, pins::keepalive.bit, gpio_cfglr_out_pp_10mhz);
    configure_pin(gpiod, pins::led_working.bit, gpio_cfglr_out_pp_10mhz);
}

void tick_init() {
    // Free-running 32-bit counter at HCLK: STCLK selects HCLK, and with
    // STRE=0 the counter keeps counting past CMPR (RM §6.5.4.1; PM §4
    // Table 4-2), so `now - last` wraps cleanly at 2^32 (~89 s,
    // quirks.md §Clock).
    systick().ctlr = stk_ctlr_stclk_hclk | stk_ctlr_ste;
}

} // namespace

extern "C" [[noreturn]] void node_main() {
    personality_init();
    clock_init();
    gpio_init();
    tick_init();
    rx_init();
    tx_init();

    Gpio volatile& gpiod = gpio(pins::gpio_d_base);
    // ~1 Hz heartbeat: toggle every half second of HCLK ticks.
    constexpr uint32_t heartbeat_ticks = hclk_hz / 2;
    // 20 kHz keep-alive strobe: toggle every 25 µs.
    constexpr uint32_t strobe_ticks = hclk_hz / 40'000;
    uint32_t last_heartbeat = systick().cntr;
    uint32_t last_strobe = last_heartbeat;
    for (;;) {
        rx_poll();
        tx_poll();
        const uint32_t now = systick().cntr;
        if (now - last_strobe >= strobe_ticks) {
            last_strobe = now;
            gpiod.outdr ^= 1u << pins::keepalive.bit;
        }
        if (now - last_heartbeat >= heartbeat_ticks) {
            last_heartbeat = now;
            gpiod.outdr ^= 1u << pins::led_working.bit;
        }
    }
}
