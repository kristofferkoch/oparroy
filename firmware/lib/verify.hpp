#pragma once

// VERIFY — the contract statement, the offensive-coding primitive
// (code-std-cpp.md#5-error-handling). A violated contract is a bug, so it traps; there is
// no defensive return code for a caller that cannot act on it. KLEE
// proves the trap unreachable — a reachable VERIFY is a proof failure
// with a counterexample, never a hope — and the optimizer elides the
// check wherever the bound is provable. Error returns stay for
// *environmental* failure (hostile input, a full arena), where the
// caller has a policy decision.
//
// UNREACHABLE is VERIFY's conditionless sibling: the exhaustive-enum
// switch closer (code-std-cpp.md#2-control-flow). It never degrades to silent UB — a
// reached UNREACHABLE is a contract violation like any other, loud on
// every personality (KLEE reports a reached __builtin_unreachable() as
// an exec error with a counterexample).
//
// Three personalities, one statement:
// - KLEE bitcode (-DOPARROY_KLEE, firmware/protocol/meson.build):
//   klee_report_error in KLEE_PROVE's shape (protocol/klee/klee.hpp) —
//   the prover hunts for any path that reaches it. The intrinsic is
//   re-declared here so lib/ stays below the harness layer. UNREACHABLE
//   is the one exception: it stays __builtin_unreachable() under KLEE.
//   Spelling it klee_report_error puts a noreturn call after the
//   switch, which changes clang 19's codegen enough to emit `freeze`
//   (the garbage harness's feed_cell stopped inlining) —
//   and KLEE 3.2 has no Freeze handler, so the proof died with
//   spurious "illegal instruction" exec errors. The proof semantics
//   are identical either way, so the cheaper spelling wins.
// - Target (-DOPARROY_TARGET, meson/cross/rv32ec.ini):
//   lib::verify_failed, the project failure hook — declared here,
//   defined once per platform (the node firmware provides its own).
//   Contract (code-std-cpp.md#5-error-handling): report over the debug
//   transport if the platform has one, then stop the §4 keep-alive
//   strobe so the charge-pump watchdog engages RX→TX bypass within
//   ~0.5 ms — deliberate bypass-engage, never a hung loop. The hook
//   must not return; the cross build is compile/archive-only, so the
//   undefined reference is the wiring point until the node firmware
//   provides it.
// - Everything else (host): __builtin_trap(). Fuzz builds get a crash
//   artifact; a constexpr-violated contract is a compile error.
//
// if/else form, not do-while — cppcoreguidelines-avoid-do-while is in
// the tidy set (code-std.md#3-enforcement-split), matching KLEE_PROVE/FUZZ_PROVE.

#if defined(OPARROY_KLEE)
extern "C" [[noreturn]] void klee_report_error(const char* file, int line, const char* message,
                                               const char* suffix);
// NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#define VERIFY(condition)                                                                          \
    if (condition) {                                                                               \
    } else {                                                                                       \
        klee_report_error(__FILE__, __LINE__, "contract violated: " #condition, "VERIFY");         \
    }
// NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#define UNREACHABLE() __builtin_unreachable()
#elif defined(OPARROY_TARGET)
namespace lib {
[[noreturn]] void verify_failed(const char* condition, const char* file, int line);
}
// NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#define VERIFY(condition)                                                                          \
    if (condition) {                                                                               \
    } else {                                                                                       \
        lib::verify_failed(#condition, __FILE__, __LINE__);                                        \
    }
// NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#define UNREACHABLE() lib::verify_failed("reached the unreachable", __FILE__, __LINE__)
#else
// NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#define VERIFY(condition)                                                                          \
    if (condition) {                                                                               \
    } else {                                                                                       \
        __builtin_trap();                                                                          \
    }
// NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#define UNREACHABLE() __builtin_trap()
#endif
