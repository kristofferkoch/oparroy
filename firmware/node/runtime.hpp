#pragma once

// Soft integer arithmetic, width-generic — the implementation behind
// the rv32ec runtime libcalls (runtime.cpp). Header-only so the KLEE
// harness (klee/runtime.cpp) instantiates the same templates at 8 bits
// and proves them exhaustively against the host's native operators —
// the proof strategy that terminates: the final multiplier/divider
// equivalence query is a hard SAT instance the pinned solvers (STP, Z3)
// do not crack at 16 bits and up, while the algorithm has no
// width-dependent branch — top-bit alignment saturation and both
// hardware-semantics edges included — so exhausting 8 bits proves the
// logic at every width. The 32/64-bit instantiations are the same
// template, and their width-specific residues (word-size constants, the
// shift counter) are pinned by the host unit tests (test_runtime.cpp).
// Native `/`, `%`, and `*` are banned here for the reason runtime.cpp's
// header comment gives.
//
// Divide-by-zero follows the RISC-V M extension's hardware semantics
// (the values libgcc's RISC-V soft routines also return): quotient
// all-ones, remainder = dividend. Signed overflow (INT_MIN / -1)
// likewise: quotient = dividend, remainder = 0. Anything else would
// fork behavior between this runtime and a future M-extension part.

#include "../lib/range.hpp"

#include <cstdint>

#if defined(OPARROY_KLEE)
// Proof-only instrumentation (never compiled for the target): under
// fully symbolic operands each loop iteration's data-dependent branch
// forks two states — 2^N paths over an N-bit word — so each loop is
// wrapped in a merge region (lib/klee.hpp) and KLEE folds the forked
// states back into one at the loop's exit. Zero cost everywhere else:
// no other personality defines OPARROY_KLEE.
#include "../lib/klee.hpp"
#endif

namespace oparroy::runtime {

// Align-and-subtract long division: `aligned` starts as the largest
// divisor·2^k that still fits dividend, then walks back down shifting a
// 1 into the quotient whenever a subtraction lands. Both loops are
// bounded by the word width.
template <typename T> struct UDivMod {
    T quotient;
    T remainder;
};

// NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
template <typename T> UDivMod<T> udivmod(T dividend, T divisor) {
    if (divisor == 0) {
        // RISC-V hardware semantics — see the header comment. The cast
        // back survives integer promotion at the narrow proof widths.
        return {.quotient = static_cast<T>(~T{0}), .remainder = dividend};
    }
    if (divisor > dividend) {
        return {.quotient = 0, .remainder = dividend};
    }
    T aligned = divisor;
    uint32_t shift = 0;
#if defined(OPARROY_KLEE)
    klee_open_merge();
#endif
    for (const uint32_t i : lib::irange(static_cast<uint32_t>((8 * sizeof(T)) - 1))) {
        const T next = static_cast<T>(aligned << 1);
        // next <= aligned catches the top bit shifting out.
        if (next > dividend || next <= aligned) {
            break;
        }
        aligned = next;
        shift = i + 1;
    }
#if defined(OPARROY_KLEE)
    klee_close_merge();
#endif
    T quotient = 0;
    T remainder = dividend;
#if defined(OPARROY_KLEE)
    klee_open_merge();
#endif
    for (const uint32_t i : lib::irange(shift + 1)) {
        if (remainder >= aligned) {
            remainder = static_cast<T>(remainder - aligned);
            quotient = static_cast<T>(quotient | (T{1} << (shift - i)));
        }
        aligned = static_cast<T>(aligned >> 1);
    }
#if defined(OPARROY_KLEE)
    klee_close_merge();
#endif
    return {.quotient = quotient, .remainder = remainder};
}

// Shift-add multiply; wraps mod 2^N, which is both the C++ unsigned
// semantics and the bit pattern the signed libcalls must return.
// NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
template <typename T> T umul(T multiplicand, T multiplier) {
    T result = 0;
#if defined(OPARROY_KLEE)
    klee_open_merge();
#endif
    for (const T i : lib::irange(static_cast<T>(8 * sizeof(T)))) {
        if (((multiplier >> i) & 1) != 0) {
            result = static_cast<T>(result + static_cast<T>(multiplicand << i));
        }
    }
#if defined(OPARROY_KLEE)
    klee_close_merge();
#endif
    return result;
}

// Magnitude of a negative signed value as unsigned, without a native
// negation of INT_MIN (which is UB on the signed side).
template <typename T> struct UnsignedFor;
template <> struct UnsignedFor<int8_t> {
    using type = uint8_t;
};
template <> struct UnsignedFor<int32_t> {
    using type = uint32_t;
};
template <> struct UnsignedFor<int64_t> {
    using type = uint64_t;
};

template <typename T> typename UnsignedFor<T>::type magnitude(T value) {
    using U = typename UnsignedFor<T>::type;
    const U bits = static_cast<U>(value);
    return value < 0 ? static_cast<U>(0) - bits : bits;
}

template <typename T> T signed_quotient(T dividend, T divisor) {
    using U = typename UnsignedFor<T>::type;
    if (divisor == 0) {
        // Hardware semantics are sign-independent: quotient all-ones.
        return static_cast<T>(~U{0});
    }
    const U quotient = udivmod(magnitude(dividend), magnitude(divisor)).quotient;
    const bool negate = (dividend < 0) != (divisor < 0);
    // The cast back is C++20 modular two's-complement, so INT_MIN / -1
    // lands on INT_MIN — the hardware overflow result.
    const U negated = static_cast<U>(0) - quotient;
    return static_cast<T>(negate ? negated : quotient);
}

template <typename T> T signed_remainder(T dividend, T divisor) {
    using U = typename UnsignedFor<T>::type;
    if (divisor == 0) {
        // Hardware semantics are sign-independent: remainder = dividend.
        return dividend;
    }
    const U remainder = udivmod(magnitude(dividend), magnitude(divisor)).remainder;
    // The remainder takes the dividend's sign (truncating division).
    const U negated = static_cast<U>(0) - remainder;
    return static_cast<T>(dividend < 0 ? negated : remainder);
}

} // namespace oparroy::runtime
