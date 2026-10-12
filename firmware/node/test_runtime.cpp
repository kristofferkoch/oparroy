// Host unit tests for the rv32ec soft runtime (runtime.cpp) — named
// cases over the TEST harness (firmware/lib/test.hpp), same pattern as
// firmware/lib/test_foundation.cpp. The multiply/divide implementations
// are shift/subtract loops, so the suite's job is the edges:
// divide-by-zero follows RISC-V hardware semantics (quotient all-ones,
// remainder = dividend), signed overflow (INT_MIN / -1) wraps to the
// dividend, signed division truncates toward zero, and unsigned results
// wrap mod 2^N. For the mem functions the edges are memmove's overlap
// directions, zero-length ranges, and memset's value truncation.
// Cases stay small: the EXPECT if/else chain counts against
// readability-function-cognitive-complexity.

#include "../lib/test.hpp"

#include <cstddef>
#include <cstdint>
#include <limits>

// NOLINTBEGIN(bugprone-reserved-identifier, cert-dcl37-c)
// NOLINTBEGIN(cert-dcl51-cpp, readability-identifier-naming)
extern "C" uint32_t __mulsi3(uint32_t, uint32_t);
extern "C" uint32_t __udivsi3(uint32_t, uint32_t);
extern "C" uint32_t __umodsi3(uint32_t, uint32_t);
extern "C" int32_t __divsi3(int32_t, int32_t);
extern "C" int32_t __modsi3(int32_t, int32_t);
extern "C" uint64_t __muldi3(uint64_t, uint64_t);
extern "C" uint64_t __udivdi3(uint64_t, uint64_t);
extern "C" uint64_t __umoddi3(uint64_t, uint64_t);
extern "C" int64_t __divdi3(int64_t, int64_t);
extern "C" int64_t __moddi3(int64_t, int64_t);
extern "C" void* memcpy(void*, const void*, std::size_t);
extern "C" void* memmove(void*, const void*, std::size_t);
extern "C" void* memset(void*, int, std::size_t);
extern "C" int memcmp(const void*, const void*, std::size_t);
// NOLINTEND(cert-dcl51-cpp, readability-identifier-naming)
// NOLINTEND(bugprone-reserved-identifier, cert-dcl37-c)

TEST_CASE(mulsi3_basics) {
    EXPECT(__mulsi3(0, 0) == 0);
    EXPECT(__mulsi3(0, 0xDEADBEEF) == 0);
    EXPECT(__mulsi3(1, 0xDEADBEEF) == 0xDEADBEEF);
    EXPECT(__mulsi3(3, 7) == 21);
    // A single-bit multiplier is a pure shift.
    EXPECT(__mulsi3(0x12345678, 1u << 4) == 0x23456780);
}

TEST_CASE(mulsi3_wraps_mod_2_32) {
    // 2^16 * 2^16 = 2^32 ≡ 0; the runtime also carries the signed
    // multiply's bit pattern.
    EXPECT(__mulsi3(0x10000, 0x10000) == 0);
    EXPECT(__mulsi3(0xFFFFFFFF, 0xFFFFFFFF) == 1);
    EXPECT(__mulsi3(0xFFFFFFFF, 7) == 0xFFFFFFF9); // -7 mod 2^32
}

TEST_CASE(udivsi3_umodsi3_basics) {
    EXPECT(__udivsi3(0, 5) == 0);
    EXPECT(__umodsi3(0, 5) == 0);
    EXPECT(__udivsi3(7, 1) == 7);
    EXPECT(__umodsi3(7, 1) == 0);
    EXPECT(__udivsi3(7, 7) == 1);
    EXPECT(__umodsi3(7, 7) == 0);
    // Truncation and remainder pair up: 7 = 3*2 + 1.
    EXPECT(__udivsi3(7, 2) == 3);
    EXPECT(__umodsi3(7, 2) == 1);
    // Divisor larger than dividend.
    EXPECT(__udivsi3(3, 10) == 0);
    EXPECT(__umodsi3(3, 10) == 3);
}

TEST_CASE(udivsi3_umodsi3_full_width) {
    constexpr uint32_t max32 = std::numeric_limits<uint32_t>::max();
    EXPECT(__udivsi3(max32, 2) == 0x7FFFFFFF);
    EXPECT(__umodsi3(max32, 2) == 1);
    EXPECT(__udivsi3(max32, max32) == 1);
    EXPECT(__umodsi3(max32, max32) == 0);
    // Top-bit divisor and dividend: the align-shift saturates at bit 31.
    EXPECT(__udivsi3(0x80000000, 0x80000000) == 1);
    EXPECT(__udivsi3(0x80000001, 0x80000000) == 1);
    EXPECT(__umodsi3(0x80000001, 0x80000000) == 1);
    EXPECT(__udivsi3(0x80000000, 3) == 0x2AAAAAAA);
    EXPECT(__umodsi3(0x80000000, 3) == 2);
}

TEST_CASE(udivsi3_umodsi3_divide_by_zero) {
    // Hardware semantics: quotient all-ones, remainder = dividend.
    constexpr uint32_t max32 = std::numeric_limits<uint32_t>::max();
    EXPECT(__udivsi3(42, 0) == max32);
    EXPECT(__umodsi3(42, 0) == 42);
    EXPECT(__udivsi3(0, 0) == max32);
    EXPECT(__umodsi3(0, 0) == 0);
}

TEST_CASE(divsi3_modsi3_basics) {
    EXPECT(__divsi3(0, 5) == 0);
    EXPECT(__modsi3(0, 5) == 0);
    EXPECT(__divsi3(7, 1) == 7);
    EXPECT(__divsi3(7, 2) == 3);
    // Truncation toward zero: -7/2 = -3, not -4.
    EXPECT(__divsi3(-7, 2) == -3);
    EXPECT(__modsi3(-7, 2) == -1);
    EXPECT(__divsi3(7, -2) == -3);
    EXPECT(__modsi3(7, -2) == 1);
    EXPECT(__divsi3(-7, -2) == 3);
    EXPECT(__modsi3(-7, -2) == -1);
}

TEST_CASE(divsi3_modsi3_extremes) {
    constexpr int32_t min32 = std::numeric_limits<int32_t>::min();
    EXPECT(__divsi3(min32, 1) == min32);
    EXPECT(__divsi3(min32, 2) == -0x40000000);
    // Overflow: INT_MIN / -1 wraps to INT_MIN, remainder 0 (hardware
    // semantics).
    EXPECT(__divsi3(min32, -1) == min32);
    EXPECT(__modsi3(min32, -1) == 0);
}

TEST_CASE(divsi3_modsi3_divide_by_zero) {
    // Sign-independent: quotient all-ones (-1), remainder = dividend.
    EXPECT(__divsi3(42, 0) == -1);
    EXPECT(__modsi3(42, 0) == 42);
    EXPECT(__divsi3(-42, 0) == -1);
    EXPECT(__modsi3(-42, 0) == -42);
}

TEST_CASE(muldi3_edges) {
    EXPECT(__muldi3(0, 0) == 0);
    EXPECT(__muldi3(1, 0x0123456789ABCDEF) == 0x0123456789ABCDEF);
    EXPECT(__muldi3(3, 7) == 21);
    // Crosses the 32-bit boundary: 2^32 * 3 = 0x300000000.
    EXPECT(__muldi3(0x100000000, 3) == 0x300000000);
    // Wrap mod 2^64.
    EXPECT(__muldi3(0x100000000, 0x100000000) == 0);
    EXPECT(__muldi3(0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF) == 1);
}

TEST_CASE(udivdi3_umoddi3_basics) {
    EXPECT(__udivdi3(0, 5) == 0);
    EXPECT(__umoddi3(0, 5) == 0);
    EXPECT(__udivdi3(7, 2) == 3);
    EXPECT(__umoddi3(7, 2) == 1);
    // Above 32 bits in dividend and divisor.
    EXPECT(__udivdi3(0x100000000, 0x100000000) == 1);
    EXPECT(__udivdi3(0x100000001, 0x100000000) == 1);
    EXPECT(__umoddi3(0x100000001, 0x100000000) == 1);
}

TEST_CASE(udivdi3_umoddi3_full_width) {
    constexpr uint64_t max64 = std::numeric_limits<uint64_t>::max();
    EXPECT(__udivdi3(max64, max64) == 1);
    EXPECT(__umoddi3(max64, max64) == 0);
    EXPECT(__udivdi3(max64, 2) == 0x7FFFFFFFFFFFFFFF);
    EXPECT(__umoddi3(max64, 2) == 1);
    // Top-bit alignment saturation.
    EXPECT(__udivdi3(0x8000000000000000, 3) == 0x2AAAAAAAAAAAAAAA);
    EXPECT(__umoddi3(0x8000000000000000, 3) == 2);
}

TEST_CASE(udivdi3_umoddi3_divide_by_zero) {
    constexpr uint64_t max64 = std::numeric_limits<uint64_t>::max();
    EXPECT(__udivdi3(42, 0) == max64);
    EXPECT(__umoddi3(42, 0) == 42);
}

TEST_CASE(divdi3_moddi3_edges) {
    EXPECT(__divdi3(7, -2) == -3);
    EXPECT(__moddi3(-7, 2) == -1);
    EXPECT(__divdi3(0x100000000, -2) == static_cast<int64_t>(std::numeric_limits<int32_t>::min()));
    constexpr int64_t min64 = std::numeric_limits<int64_t>::min();
    EXPECT(__divdi3(min64, 1) == min64);
    EXPECT(__divdi3(min64, -1) == min64);
    EXPECT(__moddi3(min64, -1) == 0);
    EXPECT(__divdi3(42, 0) == -1);
    EXPECT(__moddi3(-42, 0) == -42);
}

// Mem functions: raw buffers are the interface under test — std::array
// stays out (startup.cpp's vector_table comment gives the freestanding
// reasoning), and include-cleaner's libc-name misfire (runtime.cpp's
// suppression block explains) hits every call site.
// NOLINTBEGIN(cppcoreguidelines-avoid-c-arrays, modernize-avoid-c-arrays, misc-include-cleaner)
TEST_CASE(memcpy_copies_and_returns_dst) {
    const uint8_t src[] = {0, 1, 2, 0xFF, 0x80};
    uint8_t dst[sizeof src] = {};
    EXPECT(memcpy(dst, src, sizeof src) == dst);
    EXPECT(memcmp(dst, src, sizeof src) == 0);
    // A zero-length copy touches nothing and returns dst.
    const uint8_t guard[] = {0xAA};
    EXPECT(memcpy(dst, guard, 0) == dst);
    EXPECT(dst[0] == 0);
}

TEST_CASE(memmove_overlap_dst_below_src) {
    uint8_t buf[] = {0, 1, 2, 3, 4, 5};
    EXPECT(memmove(buf, buf + 2, 4) == buf);
    EXPECT(buf[0] == 2);
    EXPECT(buf[1] == 3);
    EXPECT(buf[2] == 4);
    EXPECT(buf[3] == 5);
    EXPECT(buf[4] == 4);
    EXPECT(buf[5] == 5);
}

TEST_CASE(memmove_overlap_dst_above_src) {
    uint8_t buf[] = {0, 1, 2, 3, 4, 5};
    // Backward copy: an ascending loop would smear 0,1,2,3 across [2,6).
    EXPECT(memmove(buf + 2, buf, 4) == buf + 2);
    EXPECT(buf[0] == 0);
    EXPECT(buf[1] == 1);
    EXPECT(buf[2] == 0);
    EXPECT(buf[3] == 1);
    EXPECT(buf[4] == 2);
    EXPECT(buf[5] == 3);
}

TEST_CASE(memset_fills_and_returns_dst) {
    uint8_t buf[4] = {1, 2, 3, 4};
    EXPECT(memset(buf, 0xAB, sizeof buf) == buf);
    EXPECT(buf[0] == 0xAB);
    EXPECT(buf[3] == 0xAB);
    // The value converts to unsigned char: 0x107 fills 0x07 — the
    // truncation is the behavior under test.
    // NOLINTNEXTLINE(bugprone-suspicious-memset-usage)
    EXPECT(memset(buf, 0x107, 1) == buf);
    EXPECT(buf[0] == 0x07);
    EXPECT(buf[1] == 0xAB);
    EXPECT(memset(buf, 0, 0) == buf);
    EXPECT(buf[0] == 0x07);
}

TEST_CASE(memcmp_sign_and_prefix) {
    const uint8_t a[] = {1, 2, 3};
    const uint8_t b[] = {1, 2, 4};
    EXPECT(memcmp(a, b, sizeof a) < 0);
    EXPECT(memcmp(b, a, sizeof a) > 0);
    EXPECT(memcmp(a, b, 2) == 0);
    EXPECT(memcmp(a, b, 0) == 0);
    // The sign is the unsigned byte difference: 0x00 vs 0xFF is
    // negative, never positive.
    const uint8_t lo[] = {0x00};
    const uint8_t hi[] = {0xFF};
    EXPECT(memcmp(lo, hi, 1) < 0);
    EXPECT(memcmp(hi, lo, 1) > 0);
}
// NOLINTEND(cppcoreguidelines-avoid-c-arrays, modernize-avoid-c-arrays, misc-include-cleaner)
