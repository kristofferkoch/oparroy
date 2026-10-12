// The node firmware's definition of lib::verify_failed — the project
// failure hook declared in firmware/lib/verify.hpp. Contract (per the
// header): stop the §4 keep-alive strobe so the charge-pump watchdog
// engages RX→TX bypass ~0.5 ms after the last edge, never return, and
// reference no strings.
//
// The whole TU is target-only: verify.hpp declares the hook only under
// -DOPARROY_TARGET, and meson only ever compiles this file in the cross
// build. The guard keeps the host-personality clang-tidy parse (the
// pre-commit hook's fallback flags) a clean empty TU.

#if defined(OPARROY_TARGET)

#include "../lib/verify.hpp"
#include "regs.hpp"

#include <pins.hpp>

#include <cstdint>

namespace lib {

[[noreturn]] void verify_failed(SourceLocation location) {
    // No debug transport yet (a settled-open question owned by a later
    // slice): the line-only location is recoverable host-side — the
    // build is reproducible, so addr2line on this ELF maps the trap
    // site's PC, and the source line is the condition text
    // (verify.hpp spells out the mechanism).
    (void)location;

    // Stop the capture timer, then pin PD3 low: the strobe is
    // software-toggled (main.cpp), so parking the loop already starves
    // the charge pump — driving the pin low just keeps a frozen-high
    // output from looking alive. The watchdog engages bypass ~0.5 ms
    // after the last edge (DESIGN.md §4) — the deliberate
    // bypass-engage the hook contract asks for, not a hung loop
    // masquerading as life.
    tim2().ctlr1 = 0;
    gpio(pins::keepalive.port_base).bcr = 1u << pins::keepalive.bit;

    // Interrupts off, then park deliberately: by the time anything
    // could resume this core the watchdog has already routed the ring
    // around the node, so there is nothing left to save here.
    __asm__ volatile("csrci mstatus, 8");
    for (;;) {
        __asm__ volatile("" ::: "memory");
    }
}

} // namespace lib

#endif // OPARROY_TARGET
