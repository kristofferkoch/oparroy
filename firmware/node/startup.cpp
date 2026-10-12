// CH32V003 startup: the vector table at the flash origin and the reset
// path (datasheets/CH32V003/notes/qingke-core.md).
//
// Entry 0 is special: mtvec resets to 0 (PM §3.2), i.e. unified-entry
// mode at base 0x00000000, and flash aliases there — so out of reset
// the core fetches the entry-0 *word as an instruction* (the WCH EVT
// startup's `j handle_reset`, cross-checked in quirks.md §EXTI). It
// must be a 4-byte `j` (a compressed c.j would occupy half a slot and
// shift every entry), hence .option norvc. node_reset then switches
// mtvec to absolute-address vectoring (mtvec[1:0] = 11, PM §2.2), from
// which point every entry is a handler *address*.
//
// Every non-reset entry defaults to unexpected_trap: an interrupt or
// fault the firmware never armed is a bug, so it routes to the platform
// failure hook — lib::verify_failed (platform.cpp) — and the §4
// watchdog bypass follows.
//
// All vector-reachable symbols are extern "C" — C++ name mangling
// silently breaks vector linking (quirks.md §EXTI).

// verify.hpp declares lib::verify_failed only under -DOPARROY_TARGET,
// so the include and the trap body guard on it: meson only ever
// compiles this TU in the cross build, and the guard keeps the
// host-personality clang-tidy parse (the pre-commit hook's fallback
// flags) clean.
#if defined(OPARROY_TARGET)
#include "../lib/verify.hpp"
#endif

#include <cstdint>

// Linker-script symbols (ch32v003.ld): the address is the payload, the
// object is never read or written through the C++ name.
// NOLINTBEGIN(bugprone-reserved-identifier, cert-dcl37-c, cert-dcl51-cpp)
// NOLINTBEGIN(readability-identifier-naming, cppcoreguidelines-avoid-non-const-global-variables)
extern uint32_t _sidata;
extern uint32_t _sdata;
extern uint32_t _edata;
extern uint32_t _sbss;
extern uint32_t _ebss;
// NOLINTEND(readability-identifier-naming, cppcoreguidelines-avoid-non-const-global-variables)
// NOLINTEND(bugprone-reserved-identifier, cert-dcl37-c, cert-dcl51-cpp)

extern "C" [[noreturn]] void node_main();
extern "C" [[noreturn]] void unexpected_trap();
extern "C" [[noreturn]] void node_boot();

// Entry 0 — the reset instruction slot described in the header comment.
// File-scope asm, not a naked function: GCC appends a trailing nop to
// naked functions, and this slot must be exactly one 4-byte word or the
// table shifts off the hardware's number*4 indexing. No alignment
// directive either: riscv gas pads .align with a leading c.nop here,
// which would shift the slot off the origin — the section is first in
// .vectors at the flash origin, and the linker script ASSERTs that.
__asm__(".section .vectors.reset, \"ax\"\n\t"
        ".globl vector_reset_slot\n\t"
        "vector_reset_slot:\n\t"
        ".option push\n\t"
        ".option norvc\n\t"
        "j node_reset\n\t"
        ".option pop\n\t"
        ".section .text\n\t");

extern "C" {

// The reset path proper. Pure C++ cannot assign sp, so these few
// instructions stay asm — everything past them is node_boot().
[[gnu::naked]] void node_reset() {
    __asm__(".option push\n\t"
            ".option norelax\n\t"
            "la gp, __global_pointer$\n\t"
            ".option pop\n\t"
            "la sp, _estack\n\t"
            // Absolute-address vectoring at the table base (PM §2.2).
            "la t0, _vector_base\n\t"
            "ori t0, t0, 3\n\t"
            "csrw mtvec, t0\n\t"
            "j node_boot");
}

// Entries 1..38 (RM §6.3 Table 6-1): reserved slots stay null, every
// defined interrupt/exception lands in unexpected_trap until the
// firmware arms a real handler.
using VectorEntry = void (*)();
[[gnu::section(".vectors.table"), gnu::used]]
// A linker-placed table is a C array by definition — std::array's
// <array> header is outside the freestanding set.
// NOLINTNEXTLINE(cppcoreguidelines-avoid-c-arrays, modernize-avoid-c-arrays)
const VectorEntry vector_table[] = {
    nullptr,         // 1: reserved
    unexpected_trap, // 2: NMI
    unexpected_trap, // 3: HardFault
    nullptr,         // 4-11: reserved
    nullptr,         nullptr,         nullptr,         nullptr,
    nullptr,         nullptr,         nullptr,
    unexpected_trap, // 12: SysTick
    nullptr,         // 13: reserved
    unexpected_trap, // 14: software interrupt
    nullptr,         // 15: reserved
    unexpected_trap, // 16: WWDG
    unexpected_trap, // 17: PVD
    unexpected_trap, // 18: flash
    unexpected_trap, // 19: RCC
    unexpected_trap, // 20: EXTI7_0
    unexpected_trap, // 21: AWU
    unexpected_trap, // 22-28: DMA1 channels 1-7
    unexpected_trap, unexpected_trap, unexpected_trap, unexpected_trap,
    unexpected_trap, unexpected_trap,
    unexpected_trap, // 29: ADC
    unexpected_trap, // 30: I2C1 event
    unexpected_trap, // 31: I2C1 error
    unexpected_trap, // 32: USART1
    unexpected_trap, // 33: SPI1
    unexpected_trap, // 34: TIM1 break
    unexpected_trap, // 35: TIM1 update
    unexpected_trap, // 36: TIM1 trigger
    unexpected_trap, // 37: TIM1 capture/compare
    unexpected_trap, // 38: TIM2
};
static_assert(sizeof(vector_table) == 38 * sizeof(VectorEntry));

[[noreturn]] void node_boot() {
    // .data: flash image → RAM.
    const uint32_t* src = &_sidata;
    for (uint32_t* dst = &_sdata; dst < &_edata;) {
        *dst++ = *src++;
    }
    // .bss: zero.
    for (uint32_t* dst = &_sbss; dst < &_ebss;) {
        *dst++ = 0;
    }
    node_main();
}

[[noreturn]] void unexpected_trap() {
#if defined(OPARROY_TARGET)
    lib::verify_failed(lib::SourceLocation::current());
#else
    __builtin_trap();
#endif
}

} // extern "C"
