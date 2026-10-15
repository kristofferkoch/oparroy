#pragma once

// CH32V003 MMIO register blocks. Volatile structs per
// code-std-cpp.md#4-memory-and-ownership; the reinterpret_cast boundary
// lives in the accessors at the bottom, each next to a comment naming
// the block it maps (code-std-cpp.md#3-types-and-arithmetic). Only the
// registers the firmware touches are modeled; offsets follow the RM
// maps, and each block's static_asserts pin the layout to those maps —
// a transcription slip is a build error, not a wrong register. Bit
// constants keep the RM's field names, lowercase per
// code-std-cpp.md#7-naming-and-layout. Registers with non-plain access
// semantics are wrapper members (W0cReg, WoReg), so misuse is a
// compile error rather than a wrong-register write.

#include <cstddef>
#include <cstdint>

// Write-0-clear status register (TIMx_INTFR, RM §10.4.5/§11.4.5):
// read() inspects the flags, clear(mask) writes ~mask — 0 clears the
// flag, 1 leaves it, so clearing needs no read. The type makes the
// wrong shapes compile errors: `|=`-style read-modify-write would
// clear every pending flag, and wholesale assignment is never right.
// One word of storage, so the block layouts are unchanged.
struct W0cReg {
    [[nodiscard]] uint32_t read() const volatile {
        return bits;
    }
    void clear(uint32_t mask) volatile {
        bits = ~mask;
    }
    W0cReg(const W0cReg&) = delete;
    W0cReg& operator=(const W0cReg&) = delete;
    W0cReg(W0cReg&&) = delete;
    W0cReg& operator=(W0cReg&&) = delete;
    ~W0cReg() = default;

private:
    volatile uint32_t bits;
};

// Write-only register cell over a strongly-typed value V (an aggregate
// { uint32_t bits; } with its own composition constants): the member
// accepts only V's compositions, so a foreign register's constant or a
// raw integer can't compile into the write. One word of storage, so
// the block layouts are unchanged.
template <typename V> struct WoReg {
    void write(V value) volatile {
        bits = value.bits;
    }
    WoReg(const WoReg&) = delete;
    WoReg& operator=(const WoReg&) = delete;
    WoReg(WoReg&&) = delete;
    WoReg& operator=(WoReg&&) = delete;
    ~WoReg() = default;

private:
    volatile uint32_t bits;
};

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

static_assert(offsetof(Rcc, cfgr0) == 0x04);
static_assert(offsetof(Rcc, intr) == 0x08);
static_assert(offsetof(Rcc, apb2prstr) == 0x0C);
static_assert(offsetof(Rcc, apb1prstr) == 0x10);
static_assert(offsetof(Rcc, ahbpcenr) == 0x14);
static_assert(offsetof(Rcc, apb2pcenr) == 0x18);
static_assert(offsetof(Rcc, apb1pcenr) == 0x1C);
static_assert(sizeof(Rcc) == 0x20);

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

// RCC_AHBPCENR clock gate (RM §3.4.6; resets to 0x00000004 — SRAMEN).
inline constexpr uint32_t rcc_ahbpcenr_dma1en = 1u << 0;

// RCC_APB2PCENR / RCC_APB1PCENR clock gates (RM §3.4.7/§3.4.8).
inline constexpr uint32_t rcc_apb2pcenr_afioen = 1u << 0;
inline constexpr uint32_t rcc_apb2pcenr_iopaen = 1u << 2;
inline constexpr uint32_t rcc_apb2pcenr_iopcen = 1u << 4;
inline constexpr uint32_t rcc_apb2pcenr_iopden = 1u << 5;
inline constexpr uint32_t rcc_apb2pcenr_tim1en = 1u << 11;
inline constexpr uint32_t rcc_apb1pcenr_tim2en = 1u << 0;

// Flash interface, base 0x40022000 (RM §16.3); only ACTLR is modeled —
// the rest of the block is the program/erase machinery.
struct FlashInterface {
    uint32_t actlr; // 0x00
};

static_assert(sizeof(FlashInterface) == 0x04);

// FLASH_ACTLR LATENCY[1:0] (RM §16.3.1): 00 for SYSCLK ≤ 24 MHz,
// 01 for ≤ 48 MHz.
inline constexpr uint32_t flash_actlr_latency_1ws = 1;

// ESIG identity block, base 0x1FFFF7E0 (RM §15.2 Table 15-1): read-only
// factory data, 8/16/32-bit accessible (RM §15.1). The 96-bit UNIID is
// the ENUM stamp's identity (firmware/protocol/enum.hpp).
struct Esig {
    uint16_t flacap;     // 0x00 — flash capacity
    uint16_t reserved02; // 0x02
    uint32_t reserved04; // 0x04
    uint32_t uniid1;     // 0x08
    uint32_t uniid2;     // 0x0C
    uint32_t uniid3;     // 0x10
};

static_assert(offsetof(Esig, uniid1) == 0x08);
static_assert(offsetof(Esig, uniid2) == 0x0C);
static_assert(offsetof(Esig, uniid3) == 0x10);
static_assert(sizeof(Esig) == 0x14);

// User option bytes, base 0x1FFFF800 (RM §16.5 Table 16-4): each byte
// stored with its inverse as a load-time checksum
// (datasheets/CH32V003/notes/flash-option-bytes.md). data0 is the node's
// personality type byte (phy-analysis §6).
struct OptionBytes {
    uint8_t rdpr;        // 0x00 — read protection (0xA5 = unprotected)
    uint8_t nrdpr;       // 0x01
    uint8_t user;        // 0x02
    uint8_t nuser;       // 0x03
    uint8_t data0;       // 0x04 — personality type byte
    uint8_t ndata0;      // 0x05
    uint8_t data1;       // 0x06
    uint8_t ndata1;      // 0x07
    uint8_t wrpr0;       // 0x08
    uint8_t nwrpr0;      // 0x09
    uint8_t wrpr1;       // 0x0A
    uint8_t nwrpr1;      // 0x0B
    uint32_t reserved0c; // 0x0C
};

static_assert(offsetof(OptionBytes, user) == 0x02);
static_assert(offsetof(OptionBytes, data0) == 0x04);
static_assert(offsetof(OptionBytes, data1) == 0x06);
static_assert(offsetof(OptionBytes, wrpr0) == 0x08);
static_assert(offsetof(OptionBytes, wrpr1) == 0x0A);
static_assert(sizeof(OptionBytes) == 0x10);

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

static_assert(offsetof(Gpio, cfghr) == 0x04);
static_assert(offsetof(Gpio, indr) == 0x08);
static_assert(offsetof(Gpio, outdr) == 0x0C);
static_assert(offsetof(Gpio, bshr) == 0x10);
static_assert(offsetof(Gpio, bcr) == 0x14);
static_assert(offsetof(Gpio, lckr) == 0x18);
static_assert(sizeof(Gpio) == 0x1C);

// CFGLR nibble encodings (RM §7.3.1.1): MODE[1:0] in the low half (00
// input, 01 = 10 MHz, 10 = 2 MHz, 11 = 30 MHz), CNF[1:0] in the high
// half (input: 00 analog, 01 floating, 10 pulled — OUTDR picks up (1)
// vs down (0); output: 00 push-pull, 01 open-drain, 10 AF push-pull,
// 11 AF open-drain).
inline constexpr uint32_t gpio_cfglr_in_pulled = 0x8;
inline constexpr uint32_t gpio_cfglr_in_floating = 0x4;
inline constexpr uint32_t gpio_cfglr_out_pp_10mhz = 0x1;
inline constexpr uint32_t gpio_cfglr_out_af_pp_10mhz = 0x9;

// TIM2, base 0x40000000 (RM §11.4).
struct Tim2 {
    uint32_t ctlr1;      // 0x00
    uint32_t ctlr2;      // 0x04
    uint32_t smcfgr;     // 0x08
    uint32_t dmaintenr;  // 0x0C
    W0cReg intfr;        // 0x10 — write-0-clear
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
    uint32_t reserved44; // 0x44 (TIM1's BDTR lives here; TIM2 has none)
    uint32_t dmacfgr;    // 0x48 — burst DMA base/length (RM §11.4.17)
    uint32_t dmaadr;     // 0x4C — burst DMA address (RM §11.4.18)
};

static_assert(offsetof(Tim2, ctlr2) == 0x04);
static_assert(offsetof(Tim2, smcfgr) == 0x08);
static_assert(offsetof(Tim2, dmaintenr) == 0x0C);
static_assert(offsetof(Tim2, intfr) == 0x10);
static_assert(offsetof(Tim2, swevgr) == 0x14);
static_assert(offsetof(Tim2, chctlr1) == 0x18);
static_assert(offsetof(Tim2, chctlr2) == 0x1C);
static_assert(offsetof(Tim2, ccer) == 0x20);
static_assert(offsetof(Tim2, cnt) == 0x24);
static_assert(offsetof(Tim2, psc) == 0x28);
static_assert(offsetof(Tim2, atrlr) == 0x2C);
static_assert(offsetof(Tim2, reserved30) == 0x30);
static_assert(offsetof(Tim2, ch1cvr) == 0x34);
static_assert(offsetof(Tim2, ch2cvr) == 0x38);
static_assert(offsetof(Tim2, ch3cvr) == 0x3C);
static_assert(offsetof(Tim2, ch4cvr) == 0x40);
static_assert(offsetof(Tim2, reserved44) == 0x44);
static_assert(offsetof(Tim2, dmacfgr) == 0x48);
static_assert(offsetof(Tim2, dmaadr) == 0x4C);
static_assert(sizeof(Tim2) == 0x50);

// TIM2_CTLR1 (RM §11.4.1).
inline constexpr uint32_t tim2_ctlr1_cen = 1u << 0;

// TIM2_SMCFGR (RM §11.4.3): TS[6:4]=101 selects TI1FP1 as the slave
// trigger, SMS[2:0]=100 resets CNT on that trigger — the PWM-input
// capture's period measurement (RM §11.3.4).
inline constexpr uint32_t tim2_smcfgr_ts_ti1fp1 = 0b101u << 4;
inline constexpr uint32_t tim2_smcfgr_sms_reset = 0b100u;

// TIM2_CHCTLR1 input-capture fields (RM §11.4.7): CC1S=01 maps CH1 to
// TI1, CC2S=10 maps CH2 to TI1 (the PWM-input pair shares TI1);
// ICxF=0011 is fCK_INT with N=8 — the input glitch filter (§2).
inline constexpr uint32_t tim2_chctlr1_cc1s_in_ti1 = 0b01u;
inline constexpr uint32_t tim2_chctlr1_ic1f_fckint_n8 = 0b0011u << 4;
inline constexpr uint32_t tim2_chctlr1_cc2s_in_ti1 = 0b10u << 8;
inline constexpr uint32_t tim2_chctlr1_ic2f_fckint_n8 = 0b0011u << 12;

// TIM2_CCER (RM §11.4.9): CC1E/CC2E capture enables; CC1P=0 (rising)
// is the zero encoding, CC2P=1 puts CH2 on the falling edge — period
// on CH1, high time on CH2 (RM §11.3.4).
inline constexpr uint32_t tim2_ccer_cc1e = 1u << 0;
inline constexpr uint32_t tim2_ccer_cc2e = 1u << 4;
inline constexpr uint32_t tim2_ccer_cc2p = 1u << 5;

// TIM2_DMAINTENR (RM §11.4.4): capture DMA request enables.
inline constexpr uint32_t tim2_dmaintenr_cc1de = 1u << 9;
inline constexpr uint32_t tim2_dmaintenr_cc2de = 1u << 10;

// TIM2_INTFR (RM §11.4.5): capture-overcapture flags (a second capture
// before the first was drained), write-0-clear.
inline constexpr uint32_t tim2_intfr_cc1of = 1u << 9;
inline constexpr uint32_t tim2_intfr_cc2of = 1u << 10;

// TIM1, base 0x40012C00 (RM §10.4): the TIM2 layout plus the
// advanced-control registers RPTCR and BDTR — the only members TIM2
// lacks; the burst-DMA pair DMACFGR/DMAADR is shared
// (notes/timers.md).
struct Tim1 {
    uint32_t ctlr1;     // 0x00
    uint32_t ctlr2;     // 0x04
    uint32_t smcfgr;    // 0x08
    uint32_t dmaintenr; // 0x0C
    W0cReg intfr;       // 0x10 — write-0-clear
    uint32_t swevgr;    // 0x14
    uint32_t chctlr1;   // 0x18 — channels 1/2
    uint32_t chctlr2;   // 0x1C — channels 3/4
    uint32_t ccer;      // 0x20
    uint32_t cnt;       // 0x24
    uint32_t psc;       // 0x28 — real divider = psc + 1
    uint32_t atrlr;     // 0x2C — auto-reload
    uint32_t rptcr;     // 0x30 — repetition counter
    uint32_t ch1cvr;    // 0x34
    uint32_t ch2cvr;    // 0x38
    uint32_t ch3cvr;    // 0x3C
    uint32_t ch4cvr;    // 0x40
    uint32_t bdtr;      // 0x44 — break and dead-time
    uint32_t dmacfgr;   // 0x48 — burst DMA base/length
    uint32_t dmaadr;    // 0x4C — burst DMA address
};

static_assert(offsetof(Tim1, ctlr2) == 0x04);
static_assert(offsetof(Tim1, smcfgr) == 0x08);
static_assert(offsetof(Tim1, dmaintenr) == 0x0C);
static_assert(offsetof(Tim1, intfr) == 0x10);
static_assert(offsetof(Tim1, swevgr) == 0x14);
static_assert(offsetof(Tim1, chctlr1) == 0x18);
static_assert(offsetof(Tim1, chctlr2) == 0x1C);
static_assert(offsetof(Tim1, ccer) == 0x20);
static_assert(offsetof(Tim1, cnt) == 0x24);
static_assert(offsetof(Tim1, psc) == 0x28);
static_assert(offsetof(Tim1, atrlr) == 0x2C);
static_assert(offsetof(Tim1, rptcr) == 0x30);
static_assert(offsetof(Tim1, ch1cvr) == 0x34);
static_assert(offsetof(Tim1, ch2cvr) == 0x38);
static_assert(offsetof(Tim1, ch3cvr) == 0x3C);
static_assert(offsetof(Tim1, ch4cvr) == 0x40);
static_assert(offsetof(Tim1, bdtr) == 0x44);
static_assert(offsetof(Tim1, dmacfgr) == 0x48);
static_assert(offsetof(Tim1, dmaadr) == 0x4C);
static_assert(sizeof(Tim1) == 0x50);

// TIM1_CTLR1 (RM §10.4.1).
inline constexpr uint32_t tim1_ctlr1_cen = 1u << 0;

// TIM1_CTLR2 (RM §10.4.2): output idle states — the level the channel
// drives when MOE=0 (after a brake), used with BDTR OSSI.
inline constexpr uint32_t tim1_ctlr2_ois1 = 1u << 8;
inline constexpr uint32_t tim1_ctlr2_ois3 = 1u << 12;

// TIM1_SWEVGR (RM §10.4.6): software event generation, self-clearing.
inline constexpr uint32_t tim1_swevgr_ug = 1u << 0;

// TIM1_CHCTLR1/CHCTLR2 output-mode fields (RM §10.4.7/§10.4.8): CCxS=00
// (output) is the zero encoding; OCxM=110 is PWM mode 1 (active while
// CNT < CVR up-counting — §10.3.5's inverted prose is a quirk,
// quirks.md §Timers); OCxPE latches writes into the shadow register at
// the update event. Channel 1's fields sit at [7:0] of CHCTLR1,
// channel 3's at [15:8] of CHCTLR2.
inline constexpr uint32_t tim1_chctlr1_oc1m_pwm1 = 0b110u << 4;
inline constexpr uint32_t tim1_chctlr1_oc1pe = 1u << 3;
inline constexpr uint32_t tim1_chctlr2_oc3m_pwm1 = 0b110u << 12;
inline constexpr uint32_t tim1_chctlr2_oc3pe = 1u << 11;

// TIM1_CCER (RM §10.4.9): output enables; CCxP=0 (active high) is the
// zero encoding, so the line idles low.
inline constexpr uint32_t tim1_ccer_cc1e = 1u << 0;
inline constexpr uint32_t tim1_ccer_cc3e = 1u << 8;

// TIM1_DMAINTENR (RM §10.4.4): compare DMA request enables — each
// compare match streams the channel's next value (notes/timers.md).
inline constexpr uint32_t tim1_dmaintenr_cc1de = 1u << 9;
inline constexpr uint32_t tim1_dmaintenr_cc3de = 1u << 11;

// TIM1_BDTR (RM §10.4.18): OSSI drives the OISx idle levels while
// MOE=0; BKE arms the BKIN brake; BKP=0 makes the brake active-low —
// the watchdog's sel sits low when bypass is engaged (DESIGN.md §4), so
// bypass engaging brakes both TX channels. AOE stays off: MOE re-arms
// are deliberate firmware acts, never an auto-resume into stale DMA
// rings. An active brake clears MOE asynchronously (RM §10.3.7).
inline constexpr uint32_t tim1_bdtr_ossi = 1u << 10;
inline constexpr uint32_t tim1_bdtr_bke = 1u << 12;
inline constexpr uint32_t tim1_bdtr_moe = 1u << 15;

// SysTick, base 0xE000F000 (RM §6.5.4 Tables 6-5, §§6.5.4.1-6.5.4.4;
// also PM §4 Table 4-1). A core peripheral — earlier RMs omitted it
// (quirks.md §Clock); the RM names CNTL/CMPLR where the PM says
// CNTR/CMPR, addresses and fields match.
struct SysTick {
    uint32_t ctlr;       // 0x00
    uint32_t sr;         // 0x04
    uint32_t cntr;       // 0x08 — the full 32-bit counter
    uint32_t reserved0c; // 0x0C
    uint32_t cmpr;       // 0x10
};

static_assert(offsetof(SysTick, sr) == 0x04);
static_assert(offsetof(SysTick, cntr) == 0x08);
static_assert(offsetof(SysTick, reserved0c) == 0x0C);
static_assert(offsetof(SysTick, cmpr) == 0x10);
static_assert(sizeof(SysTick) == 0x14);

// STK_CTLR (RM §6.5.4.1; PM §4 Table 4-2).
inline constexpr uint32_t stk_ctlr_ste = 1u << 0;        // counter enable
inline constexpr uint32_t stk_ctlr_stie = 1u << 1;       // interrupt enable
inline constexpr uint32_t stk_ctlr_stclk_hclk = 1u << 2; // 1 = HCLK, 0 = HCLK/8
inline constexpr uint32_t stk_ctlr_stre = 1u << 3;       // auto-reload at CMPR

// A composed DMA_CFGRx value (RM §8.3.3): built only from the
// dma_cfgr_* constants via operator|, and the only thing a channel's
// cfgr member accepts. `{}` is the all-zero encoding — channel
// disabled — used to stop a channel before reconfiguration.
struct DmaCfgr {
    // NOLINTNEXTLINE(misc-non-private-member-variables-in-classes) — a value, not encapsulation
    uint32_t bits;

    [[nodiscard]] constexpr DmaCfgr operator|(DmaCfgr rhs) const {
        return {bits | rhs.bits};
    }
};

// One DMA channel's register block, at 0x40020008 + (channel−1)×0x14
// (RM §8.3.3). The shared DMA_INTFR/DMA_INTFCR at the block base are
// not modeled: the RX path polls CNTR and TIM2's CCxOF instead
// (firmware/node/rx.cpp).
struct DmaChannel {
    WoReg<DmaCfgr> cfgr; // 0x00
    uint32_t cntr;       // 0x04 — transfers remaining; reloads in CIRC mode
    uint32_t paddr;      // 0x08
    uint32_t maddr;      // 0x0C
};

static_assert(offsetof(DmaChannel, cntr) == 0x04);
static_assert(offsetof(DmaChannel, paddr) == 0x08);
static_assert(offsetof(DmaChannel, maddr) == 0x0C);
// The block stride (0x14, the dma_channel() accessor) is wider than the
// modeled registers.
static_assert(sizeof(DmaChannel) == 0x10);

// DMA_CFGRx (RM §8.3.3): peripheral-to-memory is DIR=0, 8-bit
// PSIZE/MSIZE the zero encoding.
inline constexpr DmaCfgr dma_cfgr_en{1u << 0};
inline constexpr DmaCfgr dma_cfgr_dir{1u << 4}; // 1 = memory-to-peripheral
inline constexpr DmaCfgr dma_cfgr_circ{1u << 5};
inline constexpr DmaCfgr dma_cfgr_minc{1u << 7};
inline constexpr DmaCfgr dma_cfgr_psize_16{0b01u << 8};
inline constexpr DmaCfgr dma_cfgr_msize_16{0b01u << 10};
inline constexpr DmaCfgr dma_cfgr_pl_very_high{0b11u << 12};

// Extended configuration unit, base 0x40023800 (RM ch.17 Table 17-1).
struct Exten {
    uint32_t ctr; // 0x00
};

static_assert(sizeof(Exten) == 0x04);

// EXTEN_CTR OPA fields (RM §17.2.1). The register also carries LDOTRIM
// and the lock-up monitor (LKUPEN resets to 1, notes/opa.md) — access
// is always read-modify-write.
inline constexpr uint32_t exten_ctr_opa_en = 1u << 16;
inline constexpr uint32_t exten_ctr_opa_nsel = 1u << 17;
inline constexpr uint32_t exten_ctr_opa_psel = 1u << 18;

// (port, bit, nibble) order mirrors the CFGLR layout; NOLINTNEXTLINE for the two narrow ints.
// NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
inline void configure_pin(Gpio volatile& port, uint8_t bit, uint32_t nibble) {
    const uint32_t shift = 4u * bit;
    port.cfglr = (port.cfglr & ~(0xFu << shift)) | (nibble << shift);
}

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

[[nodiscard]] inline Esig volatile& esig() {
    // MMIO boundary: the ESIG identity block (RM §15.2 Table 15-1).
    // NOLINTNEXTLINE(performance-no-int-to-ptr) — MMIO boundary, the cast is the point
    return *reinterpret_cast<Esig volatile*>(0x1FFFF7E0u);
}

[[nodiscard]] inline OptionBytes volatile& option_bytes() {
    // MMIO boundary: the user option bytes (RM §16.5 Table 16-4).
    // NOLINTNEXTLINE(performance-no-int-to-ptr) — MMIO boundary, the cast is the point
    return *reinterpret_cast<OptionBytes volatile*>(0x1FFFF800u);
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

[[nodiscard]] inline Tim1 volatile& tim1() {
    // MMIO boundary: the TIM1 register block (RM §10.4).
    // NOLINTNEXTLINE(performance-no-int-to-ptr) — MMIO boundary, the cast is the point
    return *reinterpret_cast<Tim1 volatile*>(0x40012C00u);
}

[[nodiscard]] inline SysTick volatile& systick() {
    // MMIO boundary: the core SysTick block (RM §6.5.4; PM §4
    // Table 4-1).
    // NOLINTNEXTLINE(performance-no-int-to-ptr) — MMIO boundary, the cast is the point
    return *reinterpret_cast<SysTick volatile*>(0xE000F000u);
}

[[nodiscard]] inline DmaChannel volatile& dma_channel(uint32_t channel) {
    // MMIO boundary: one DMA channel's register block (RM §8.3.3); the
    // channel number is always a pins::*_dma constant (RM §8.2.3
    // Table 8-2 maps the peripherals to channels).
    // NOLINTNEXTLINE(performance-no-int-to-ptr) — MMIO boundary, the cast is the point
    return *reinterpret_cast<DmaChannel volatile*>(0x40020008u + ((channel - 1u) * 0x14u));
}

[[nodiscard]] inline Exten volatile& exten() {
    // MMIO boundary: the extended configuration unit (RM ch.17
    // Table 17-1).
    // NOLINTNEXTLINE(performance-no-int-to-ptr) — MMIO boundary, the cast is the point
    return *reinterpret_cast<Exten volatile*>(0x40023800u);
}
