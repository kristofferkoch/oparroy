// Node bring-up: 48 MHz clock init, the §4 keep-alive strobe on PD3,
// and the working-LED heartbeat on PD0.
//
// Keep-alive route decision: TIM2_CH2 default-maps to PD3 (TIM2_RM=00,
// the AFIO reset value — no remap touched, gpio-pinout.md), so a
// hardware PWM square wave costs no ISR and no conflict: PD4
// (TIM2_CH1/ETR's pin) stays an unused floating input, and channel 1's
// internal OPA→capture route is configured per-channel, independent of
// channel 2's output (RM §11.4.7). TIM2's base rate (PSC/ATRLR) is
// shared with the future RX capture — that coordination belongs to the
// RX work, not bring-up.
//
// The heartbeat derives from SysTick free-running at HCLK: no interrupt
// at all in this image. extern "C", never returns
// (code-std-cpp.md#1-language-and-toolchain).

#include "pins.hpp"
#include "regs.hpp"

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

// (port, bit, nibble) order mirrors the CFGLR layout; NOLINTNEXTLINE for the two narrow ints.
// NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
void configure_output(Gpio volatile& port, uint8_t bit, uint32_t nibble) {
    const uint32_t shift = 4u * bit;
    port.cfglr = (port.cfglr & ~(0xFu << shift)) | (nibble << shift);
}

void gpio_init() {
    // AFIO's gate is required even without a remap — the alternate-
    // function path from TIM2 to the pin crosses it (quirks.md §GPIO).
    rcc().apb2pcenr |=
        rcc_apb2pcenr_afioen | rcc_apb2pcenr_iopaen | rcc_apb2pcenr_iopcen | rcc_apb2pcenr_iopden;
    Gpio volatile& gpiod = gpio(pins::gpio_d_base);
    configure_output(gpiod, pins::keepalive.bit, gpio_cfglr_out_af_pp_10mhz);
    configure_output(gpiod, pins::led_working.bit, gpio_cfglr_out_pp_10mhz);
}

void keepalive_init() {
    // 48 MHz / 2400 = 20 kHz, 50 % duty — the §4 charge-pump watchdog's
    // keep-alive strobe.
    constexpr uint32_t period_ticks = 2400;
    rcc().apb1pcenr |= rcc_apb1pcenr_tim2en;
    Tim2 volatile& tim = tim2();
    tim.psc = 0;
    tim.atrlr = period_ticks - 1;
    tim.ch2cvr = period_ticks / 2;
    tim.chctlr1 = tim2_chctlr1_oc2m_pwm1;
    tim.ccer = tim2_ccer_cc2e;
    tim.ctlr1 = tim2_ctlr1_cen;
}

void tick_init() {
    // Free-running 32-bit counter at HCLK: STCLK selects HCLK, and with
    // STRE=0 the counter keeps counting past CMPR (PM §4 Table 4-2), so
    // `now - last` wraps cleanly at 2^32 (~89 s, quirks.md §Clock).
    systick().ctlr = stk_ctlr_stclk_hclk | stk_ctlr_ste;
}

} // namespace

extern "C" [[noreturn]] void node_main() {
    clock_init();
    gpio_init();
    keepalive_init();
    tick_init();

    Gpio volatile& gpiod = gpio(pins::gpio_d_base);
    // ~1 Hz heartbeat: toggle every half second of HCLK ticks.
    constexpr uint32_t heartbeat_ticks = hclk_hz / 2;
    uint32_t last = systick().cntr;
    for (;;) {
        const uint32_t now = systick().cntr;
        if (now - last >= heartbeat_ticks) {
            last = now;
            gpiod.outdr ^= 1u << pins::led_working.bit;
        }
    }
}
