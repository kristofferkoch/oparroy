// Soft integer runtime for the rv32ec node firmware. The CH32V003's
// QingKe V2A core is RV32EC — no M extension — and the toolchain ships
// no rv32ec/ilp32e multilib (meson/cross/rv32ec.ini), so there is no
// libgcc to resolve the multiply/divide libcalls the compiler emits for
// `/`, `%`, and 32/64-bit `*`. These definitions are that runtime:
// shift/subtract loops over explicit-width types (runtime.hpp holds the
// width-generic implementation) — native `/`, `%`, and `*` are banned
// in both files precisely because they would lower to the very libcalls
// being defined. extern "C" so the linker names match what the compiler
// emits. Host-run unit tests live in test_runtime.cpp; the KLEE proof
// lives in klee/runtime.cpp (runtime.hpp's header comment gives the
// proof strategy).
//
// Divide-by-zero follows the RISC-V M extension's hardware semantics
// (the values libgcc's RISC-V soft routines also return): quotient
// all-ones, remainder = dividend. Signed overflow (INT_MIN / -1)
// likewise: quotient = dividend, remainder = 0. Anything else would
// fork behavior between this runtime and a future M-extension part.

#include "runtime.hpp"

#include <cstdint>

// Runtime-ABI names (reserved, and not snake_case) by definition — the
// linker resolves exactly these spellings.
// NOLINTBEGIN(bugprone-reserved-identifier, cert-dcl37-c)
// NOLINTBEGIN(cert-dcl51-cpp, readability-identifier-naming)
extern "C" uint32_t __mulsi3(uint32_t multiplicand, uint32_t multiplier) {
    return oparroy::runtime::umul(multiplicand, multiplier);
}

extern "C" uint32_t __udivsi3(uint32_t dividend, uint32_t divisor) {
    return oparroy::runtime::udivmod(dividend, divisor).quotient;
}

extern "C" uint32_t __umodsi3(uint32_t dividend, uint32_t divisor) {
    return oparroy::runtime::udivmod(dividend, divisor).remainder;
}

extern "C" int32_t __divsi3(int32_t dividend, int32_t divisor) {
    return oparroy::runtime::signed_quotient(dividend, divisor);
}

extern "C" int32_t __modsi3(int32_t dividend, int32_t divisor) {
    return oparroy::runtime::signed_remainder(dividend, divisor);
}

extern "C" uint64_t __muldi3(uint64_t multiplicand, uint64_t multiplier) {
    return oparroy::runtime::umul(multiplicand, multiplier);
}

extern "C" uint64_t __udivdi3(uint64_t dividend, uint64_t divisor) {
    return oparroy::runtime::udivmod(dividend, divisor).quotient;
}

extern "C" uint64_t __umoddi3(uint64_t dividend, uint64_t divisor) {
    return oparroy::runtime::udivmod(dividend, divisor).remainder;
}

extern "C" int64_t __divdi3(int64_t dividend, int64_t divisor) {
    return oparroy::runtime::signed_quotient(dividend, divisor);
}

extern "C" int64_t __moddi3(int64_t dividend, int64_t divisor) {
    return oparroy::runtime::signed_remainder(dividend, divisor);
}
// NOLINTEND(cert-dcl51-cpp, readability-identifier-naming)
// NOLINTEND(bugprone-reserved-identifier, cert-dcl37-c)
