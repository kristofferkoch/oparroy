#pragma once

// CH32V003 MMIO register blocks. Volatile structs per
// code-std-cpp.md#4-memory-and-ownership; the reinterpret_cast boundary
// lives in the accessors at the bottom, each next to a comment naming
// the block it maps (code-std-cpp.md#3-types-and-arithmetic). Only the
// registers the firmware touches are modeled; offsets follow the RM
// maps. Bit constants keep the RM's field names, lowercase per
// code-std-cpp.md#7-naming-and-layout.

#include <cstdint>

// RCC, base 0x40021000 (RM §3.4 Table 3-1).
struct Rcc {
    uint32_t ctlr;      // 0x00
    uint32_t cfgr0;     // 0x04
    uint32_t intr;      // 0x08
    uint32_t apb2prstr; // 0x0C
    uint32_t apb1prstr; // 0x10
    uint32_t ahbpcenr;  // 0x14
    uint32_t apb2pcenr; // 0x18
    uint32_t apb1pcenr; // 0x1C
};

// RCC_CTLR (RM §3.4.1).
inline constexpr uint32_t rcc_ctlr_hsion = 1u << 0;
inline constexpr uint32_t rcc_ctlr_hsirdy = 1u << 1;
inline constexpr uint32_t rcc_ctlr_pllon = 1u << 24;
inline constexpr uint32_t rcc_ctlr_pllrdy = 1u << 25;

// RCC_CFGR0 (RM §3.4.2; resets to 0x00000020 — HPRE=/3, quirks.md
// §Clock). HPRE=0000 is /1, PLLSRC=0 is HSI — both are the zero
// encoding, so a cleared register is the 48 MHz HSI×2 plan minus the
// switch.
inline constexpr uint32_t rcc_cfgr0_sw_pll = 0x2;   // SW[1:0]=10: PLL as SYSCLK
inline constexpr uint32_t rcc_cfgr0_sws_mask = 0xC; // SWS[1:0] at [3:2]
inline constexpr uint32_t rcc_cfgr0_sws_pll = 0x8;

// RCC_APB2PCENR / RCC_APB1PCENR clock gates (RM §3.4.7/§3.4.8).
inline constexpr uint32_t rcc_apb2pcenr_afioen = 1u << 0;
inline constexpr uint32_t rcc_apb2pcenr_iopaen = 1u << 2;
inline constexpr uint32_t rcc_apb2pcenr_iopcen = 1u << 4;
inline constexpr uint32_t rcc_apb2pcenr_iopden = 1u << 5;
inline constexpr uint32_t rcc_apb1pcenr_tim2en = 1u << 0;

// Flash interface, base 0x40022000 (RM §16.3); only ACTLR is modeled —
// the rest of the block is the program/erase machinery.
struct FlashInterface {
    uint32_t actlr; // 0x00
};

// FLASH_ACTLR LATENCY[1:0] (RM §16.3.1): 00 for SYSCLK ≤ 24 MHz,
// 01 for ≤ 48 MHz.
inline constexpr uint32_t flash_actlr_latency_1ws = 1;

// GPIO port (RM §7.3); per-port bases are pins::gpio_*_base.
struct Gpio {
    uint32_t cfglr; // 0x00
    uint32_t cfghr; // 0x04 — unused (F4P6 ports have ≤ 8 pins), kept for the offset
    uint32_t indr;  // 0x08
    uint32_t outdr; // 0x0C
    uint32_t bshr;  // 0x10 — bit set/reset (1 = set)
    uint32_t bcr;   // 0x14 — bit clear
    uint32_t lckr;  // 0x18
};

// CFGLR nibble encodings (RM §7.3.1.1): MODE[1:0] in the low half (00
// input, 01 = 10 MHz, 10 = 2 MHz, 11 = 30 MHz), CNF[1:0] in the high
// half (output: 00 push-pull, 01 open-drain, 10 AF push-pull,
// 11 AF open-drain).
inline constexpr uint32_t gpio_cfglr_out_pp_10mhz = 0x1;
inline constexpr uint32_t gpio_cfglr_out_af_pp_10mhz = 0x9;

// TIM2, base 0x40000000 (RM §11.4).
struct Tim2 {
    uint32_t ctlr1;      // 0x00
    uint32_t ctlr2;      // 0x04
    uint32_t smcfgr;     // 0x08
    uint32_t dmaintenr;  // 0x0C
    uint32_t intfr;      // 0x10
    uint32_t swevgr;     // 0x14
    uint32_t chctlr1;    // 0x18 — channels 1/2
    uint32_t chctlr2;    // 0x1C — channels 3/4
    uint32_t ccer;       // 0x20
    uint32_t cnt;        // 0x24
    uint32_t psc;        // 0x28 — real divider = psc + 1
    uint32_t atrlr;      // 0x2C — auto-reload
    uint32_t reserved30; // 0x30 (TIM1's RPTCR lives here; TIM2 has none)
    uint32_t ch1cvr;     // 0x34
    uint32_t ch2cvr;     // 0x38
    uint32_t ch3cvr;     // 0x3C
    uint32_t ch4cvr;     // 0x40
};

// TIM2_CTLR1 (RM §11.4.1).
inline constexpr uint32_t tim2_ctlr1_cen = 1u << 0;
// TIM2_CHCTLR1 channel-2 output fields (RM §11.4.7): OC2M[14:12] —
// 110 is PWM mode 1 (active while CNT < CVR); CC2S=00 (output) is the
// zero encoding.
inline constexpr uint32_t tim2_chctlr1_oc2m_pwm1 = 0b110u << 12;
// TIM2_CCER (RM §11.4.9): CC2E output enable; CC2P=0 (active high) is
// the zero encoding.
inline constexpr uint32_t tim2_ccer_cc2e = 1u << 4;

// SysTick, base 0xE000F000 (PM §4 Table 4-1) — a core peripheral, hence
// not in the RM (quirks.md §Clock).
struct SysTick {
    uint32_t ctlr;       // 0x00
    uint32_t sr;         // 0x04
    uint32_t cntr;       // 0x08 — the full 32-bit counter
    uint32_t reserved0c; // 0x0C
    uint32_t cmpr;       // 0x10
};

// STK_CTLR (PM §4 Table 4-2).
inline constexpr uint32_t stk_ctlr_ste = 1u << 0;        // counter enable
inline constexpr uint32_t stk_ctlr_stie = 1u << 1;       // interrupt enable
inline constexpr uint32_t stk_ctlr_stclk_hclk = 1u << 2; // 1 = HCLK, 0 = HCLK/8
inline constexpr uint32_t stk_ctlr_stre = 1u << 3;       // auto-reload at CMPR

[[nodiscard]] inline Rcc volatile& rcc() {
    // MMIO boundary: the RCC register block (RM §3.4 Table 3-1).
    // NOLINTNEXTLINE(performance-no-int-to-ptr) — MMIO boundary, the cast is the point
    return *reinterpret_cast<Rcc volatile*>(0x40021000u);
}

[[nodiscard]] inline FlashInterface volatile& flash() {
    // MMIO boundary: the flash interface block (RM §16.3).
    // NOLINTNEXTLINE(performance-no-int-to-ptr) — MMIO boundary, the cast is the point
    return *reinterpret_cast<FlashInterface volatile*>(0x40022000u);
}

[[nodiscard]] inline Gpio volatile& gpio(uint32_t port_base) {
    // MMIO boundary: a GPIO port register block (RM §7.3); the base is
    // always a pins::gpio_*_base constant (RM §1.2).
    // NOLINTNEXTLINE(performance-no-int-to-ptr) — MMIO boundary, the cast is the point
    return *reinterpret_cast<Gpio volatile*>(port_base);
}

[[nodiscard]] inline Tim2 volatile& tim2() {
    // MMIO boundary: the TIM2 register block (RM §11.4).
    // NOLINTNEXTLINE(performance-no-int-to-ptr) — MMIO boundary, the cast is the point
    return *reinterpret_cast<Tim2 volatile*>(0x40000000u);
}

[[nodiscard]] inline SysTick volatile& systick() {
    // MMIO boundary: the core SysTick block (PM §4 Table 4-1).
    // NOLINTNEXTLINE(performance-no-int-to-ptr) — MMIO boundary, the cast is the point
    return *reinterpret_cast<SysTick volatile*>(0xE000F000u);
}
