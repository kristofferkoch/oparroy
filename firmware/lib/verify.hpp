#pragma once

// VERIFY — the contract statement, the offensive-coding primitive
// (code-std.md §6). A violated contract is a bug, so it traps; there is
// no defensive return code for a caller that cannot act on it. KLEE
// proves the trap unreachable — a reachable VERIFY is a proof failure
// with a counterexample, never a hope — and the optimizer elides the
// check wherever the bound is provable. Error returns stay for
// *environmental* failure (hostile input, a full arena), where the
// caller has a policy decision.
//
// Two personalities, one statement:
// - KLEE bitcode (-DOPARROY_KLEE, firmware/protocol/meson.build):
//   klee_report_error in KLEE_PROVE's shape (protocol/klee/klee.hpp) —
//   the prover hunts for any path that reaches it. The intrinsic is
//   re-declared here so lib/ stays below the harness layer.
// - Everything else, for now: __builtin_trap(). Fuzz builds get a crash
//   artifact; a constexpr-violated contract is a compile error. On
//   target, T18 wires the failure hook to the watchdog/bypass policy
//   (DESIGN.md §4): deliberate bypass-engage, not a hung loop.
//
// if/else form, not do-while — cppcoreguidelines-avoid-do-while is in
// the tidy set (code-std.md §9), matching KLEE_PROVE/FUZZ_PROVE.

#if defined(OPARROY_KLEE)
extern "C" [[noreturn]] void klee_report_error(const char* file, int line, const char* message,
                                               const char* suffix);
// NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#define VERIFY(condition)                                                                          \
    if (condition) {                                                                               \
    } else {                                                                                       \
        klee_report_error(__FILE__, __LINE__, "contract violated: " #condition, "VERIFY");         \
    }
#else
// NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#define VERIFY(condition)                                                                          \
    if (condition) {                                                                               \
    } else {                                                                                       \
        __builtin_trap();                                                                          \
    }
#endif
