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
//   klee_report_error in KLEE_PROVE's shape (lib/klee.hpp, included
//   below) — the prover hunts for any path that reaches it. UNREACHABLE
//   is the one exception: it stays __builtin_unreachable() under KLEE.
//   Spelling it klee_report_error puts a noreturn call after the
//   switch, which changes clang 19's codegen enough to emit `freeze`
//   (the garbage harness's feed_cell stopped inlining) —
//   and KLEE 3.2 has no Freeze handler, so the proof died with
//   spurious "illegal instruction" exec errors. The proof semantics
//   are identical either way, so the cheaper spelling wins.
//   This personality keeps __FILE__/__LINE__ rather than SourceLocation:
//   klee_report_error's signature is KLEE's fixed ABI, and this
//   spelling is proven codegen-fragile — what reaches the prover stays
//   byte-identical, and file/line is only counterexample labeling.
// - Target (-DOPARROY_TARGET, meson/cross/rv32ec.ini):
//   lib::verify_failed, the project failure hook — declared here,
//   defined once per platform (the node firmware provides its own).
//   Contract (code-std-cpp.md#5-error-handling): report over the debug
//   transport if the platform has one, then stop the §4 keep-alive
//   strobe so the charge-pump watchdog engages RX→TX bypass within
//   ~0.5 ms — deliberate bypass-engage, never a hung loop. The hook
//   must not return; the cross build is compile/archive-only, so the
//   undefined reference is the wiring point until the node firmware
//   provides it. The hook takes the line-only SourceLocation
//   (source_location.hpp) — current() captures the macro-invocation
//   line from the builtin's default-argument instantiation, and no
//   string literals reach the image (the no-strings rule below).
// - Everything else (host): __builtin_trap(). Fuzz builds get a crash
//   artifact; a constexpr-violated contract is a compile error.
//
// if/else form, not do-while — cppcoreguidelines-avoid-do-while is in
// the tidy set (code-std.md#3-enforcement-split), matching KLEE_PROVE/FUZZ_PROVE.

#if defined(OPARROY_KLEE)
#include "klee.hpp"
// NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#define VERIFY(condition)                                                                          \
    if (condition) {                                                                               \
    } else {                                                                                       \
        klee_report_error(__FILE__, __LINE__, "contract violated: " #condition, "VERIFY");         \
    }
// NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#define UNREACHABLE() __builtin_unreachable()
#elif defined(OPARROY_TARGET)
// Per-personality includes: only this branch reads the location
// header, and hoisting it would pull it into the KLEE bitcode parses
// (and trip misc-include-cleaner on the host personality).
#include "source_location.hpp"

// No strings on the target (code-std-cpp.md#1-language-and-toolchain):
// the hook takes the line-only SourceLocation and nothing else — no
// condition text, no file/function literals, so a VERIFY site
// references no strings and the image carries none. Full site identity
// is recoverable host-side from the ELF: the hook can take the site's
// PC with __builtin_return_address, addr2line maps it, and the source
// line it lands on is the condition text.
namespace lib {
[[noreturn]] void verify_failed(SourceLocation location);
}
// NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#define VERIFY(condition)                                                                          \
    if (condition) {                                                                               \
    } else {                                                                                       \
        lib::verify_failed(::lib::SourceLocation::current());                                      \
    }
// NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#define UNREACHABLE() lib::verify_failed(::lib::SourceLocation::current())
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
