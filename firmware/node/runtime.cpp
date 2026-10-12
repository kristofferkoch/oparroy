// Soft integer runtime for the rv32ec node firmware. The CH32V003's
// QingKe V2A core is RV32EC — no M extension — and the toolchain ships
// no rv32ec/ilp32e multilib (meson/cross/rv32ec.ini), so there is no
// libgcc to resolve the multiply/divide libcalls the compiler emits for
// `/`, `%`, and 32/64-bit `*`. These definitions are that runtime:
// shift/subtract loops over explicit-width types — native `/`, `%`, and
// `*` are banned inside this file precisely because they would lower to
// the very libcalls being defined. extern "C" so the linker names match
// what the compiler emits. Host-run unit tests live in
// test_runtime.cpp.
//
// Divide-by-zero follows the RISC-V M extension's hardware semantics
// (the values libgcc's RISC-V soft routines also return): quotient
// all-ones, remainder = dividend. Signed overflow (INT_MIN / -1)
// likewise: quotient = dividend, remainder = 0. Anything else would
// fork behavior between this runtime and a future M-extension part.

#include "../lib/range.hpp"

#include <cstdint>

namespace {

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
        // RISC-V hardware semantics — see the header comment.
        return {.quotient = ~T{0}, .remainder = dividend};
    }
    if (divisor > dividend) {
        return {.quotient = 0, .remainder = dividend};
    }
    T aligned = divisor;
    uint32_t shift = 0;
    for (const uint32_t i : lib::irange(static_cast<uint32_t>((8 * sizeof(T)) - 1))) {
        const T next = static_cast<T>(aligned << 1);
        // next <= aligned catches the top bit shifting out.
        if (next > dividend || next <= aligned) {
            break;
        }
        aligned = next;
        shift = i + 1;
    }
    T quotient = 0;
    T remainder = dividend;
    for (const uint32_t i : lib::irange(shift + 1)) {
        if (remainder >= aligned) {
            remainder = static_cast<T>(remainder - aligned);
            quotient = static_cast<T>(quotient | (T{1} << (shift - i)));
        }
        aligned = static_cast<T>(aligned >> 1);
    }
    return {.quotient = quotient, .remainder = remainder};
}

// Shift-add multiply; wraps mod 2^N, which is both the C++ unsigned
// semantics and the bit pattern the signed libcalls must return.
// NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
template <typename T> T umul(T multiplicand, T multiplier) {
    T result = 0;
    for (const T i : lib::irange(static_cast<T>(8 * sizeof(T)))) {
        if (((multiplier >> i) & 1) != 0) {
            result = static_cast<T>(result + static_cast<T>(multiplicand << i));
        }
    }
    return result;
}

// Magnitude of a negative signed value as unsigned, without a native
// negation of INT_MIN (which is UB on the signed side).
template <typename T> struct UnsignedFor;
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

} // namespace

// Runtime-ABI names (reserved, and not snake_case) by definition — the
// linker resolves exactly these spellings.
// NOLINTBEGIN(bugprone-reserved-identifier, cert-dcl37-c)
// NOLINTBEGIN(cert-dcl51-cpp, readability-identifier-naming)
extern "C" uint32_t __mulsi3(uint32_t multiplicand, uint32_t multiplier) {
    return umul(multiplicand, multiplier);
}

extern "C" uint32_t __udivsi3(uint32_t dividend, uint32_t divisor) {
    return udivmod(dividend, divisor).quotient;
}

extern "C" uint32_t __umodsi3(uint32_t dividend, uint32_t divisor) {
    return udivmod(dividend, divisor).remainder;
}

extern "C" int32_t __divsi3(int32_t dividend, int32_t divisor) {
    return signed_quotient(dividend, divisor);
}

extern "C" int32_t __modsi3(int32_t dividend, int32_t divisor) {
    return signed_remainder(dividend, divisor);
}

extern "C" uint64_t __muldi3(uint64_t multiplicand, uint64_t multiplier) {
    return umul(multiplicand, multiplier);
}

extern "C" uint64_t __udivdi3(uint64_t dividend, uint64_t divisor) {
    return udivmod(dividend, divisor).quotient;
}

extern "C" uint64_t __umoddi3(uint64_t dividend, uint64_t divisor) {
    return udivmod(dividend, divisor).remainder;
}

extern "C" int64_t __divdi3(int64_t dividend, int64_t divisor) {
    return signed_quotient(dividend, divisor);
}

extern "C" int64_t __moddi3(int64_t dividend, int64_t divisor) {
    return signed_remainder(dividend, divisor);
}
// NOLINTEND(cert-dcl51-cpp, readability-identifier-naming)
// NOLINTEND(bugprone-reserved-identifier, cert-dcl37-c)
