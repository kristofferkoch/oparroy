// Soft runtime for the rv32ec node firmware — two libcall families the
// compiler emits but no library resolves here:
//
// Multiply/divide: the CH32V003's QingKe V2A core is RV32EC — no M
// extension — and the toolchain ships no rv32ec/ilp32e multilib
// (meson/cross/rv32ec.ini), so there is no libgcc for `/`, `%`, and
// 32/64-bit `*`. These definitions are shift/subtract loops over
// explicit-width types (runtime.hpp holds the width-generic
// implementation) — native `/`, `%`, and `*` are banned in both files
// precisely because they would lower to the very libcalls being
// defined.
//
// Memory: memcpy/memmove/memset/memcmp. A freestanding link must
// provide all four — gcc lowers struct copies and aggregate zeroing to
// them without the source ever naming them (first seen: the
// SourceLocation pass-by-value in the verify_failed path under -Os).
// Byte loops: the copies are small and cold (startup init, the failure
// hook), so simple beats clever. The loops are also why this TU compiles
// with -fno-tree-loop-distribute-patterns where gcc supports it
// (meson.build): gcc's loop-idiom pass is otherwise free to rewrite a
// byte-copy loop into a call to the very memcpy being defined —
// infinite recursion (reproduced hosted at -O2).
//
// extern "C" so the linker names match what the compiler emits.
// Host-run unit tests live in test_runtime.cpp; the KLEE proof of the
// multiply/divide algorithm lives in klee/runtime.cpp (runtime.hpp's
// header comment gives the proof strategy). The mem* loops carry no
// width genericity; their one edge — overlap direction in memmove — is
// pinned by the unit tests.
//
// Divide-by-zero follows the RISC-V M extension's hardware semantics
// (the values libgcc's RISC-V soft routines also return): quotient
// all-ones, remainder = dividend. Signed overflow (INT_MIN / -1)
// likewise: quotient = dividend, remainder = 0. Anything else would
// fork behavior between this runtime and a future M-extension part.

#include "runtime.hpp"

#include <cstddef>
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

// NOLINTBEGIN(misc-include-cleaner, bugprone-easily-swappable-parameters)
// Defining a libc-named symbol trips include-cleaner twice over: it
// wants <string.h> for the definition itself (the whole point here is
// that no such header enters the link), and clang's implicit builtin
// declaration then absorbs the function body — include-cleaner
// attributes even the locals to that header-less builtin decl. The
// parameter order is the ABI's.
extern "C" void* memcpy(void* dst, const void* src, std::size_t count) {
    auto* d = static_cast<unsigned char*>(dst);
    const auto* s = static_cast<const unsigned char*>(src);
    for (; count > 0; --count) {
        *d++ = *s++;
    }
    return dst;
}

extern "C" void* memmove(void* dst, const void* src, std::size_t count) {
    auto* d = static_cast<unsigned char*>(dst);
    const auto* s = static_cast<const unsigned char*>(src);
    // Compare addresses, not pointers: `<` on pointers into different
    // objects is UB.
    if (reinterpret_cast<std::uintptr_t>(d) < reinterpret_cast<std::uintptr_t>(s)) {
        for (; count > 0; --count) {
            *d++ = *s++;
        }
        return dst;
    }
    for (; count > 0; --count) {
        d[count - 1] = s[count - 1];
    }
    return dst;
}

extern "C" void* memset(void* dst, int value, std::size_t count) {
    auto* d = static_cast<unsigned char*>(dst);
    const auto byte = static_cast<unsigned char>(value);
    for (; count > 0; --count) {
        *d++ = byte;
    }
    return dst;
}

extern "C" int memcmp(const void* lhs, const void* rhs, std::size_t count) {
    const auto* l = static_cast<const unsigned char*>(lhs);
    const auto* r = static_cast<const unsigned char*>(rhs);
    for (; count > 0; --count) {
        if (*l != *r) {
            return static_cast<int>(*l) - static_cast<int>(*r);
        }
        ++l;
        ++r;
    }
    return 0;
}
// NOLINTEND(misc-include-cleaner, bugprone-easily-swappable-parameters)
// NOLINTEND(cert-dcl51-cpp, readability-identifier-naming)
// NOLINTEND(bugprone-reserved-identifier, cert-dcl37-c)
