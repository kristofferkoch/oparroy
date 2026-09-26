#pragma once

// StaticVector<T, Capacity> — the std::array's variable-length sibling:
// statically allocated, bounded at Capacity, with a live size in
// [0, Capacity]. The fixed-capacity container spine of the foundation
// library (DESIGN.md §8, code-std.md §5).
//
// Elements are stored as a plain T array, so T must be
// default-constructible, copy-assignable, and trivially destructible —
// the value types this project is made of. That keeps the type fully
// constexpr-usable and cast-free: raw storage + placement new needs
// <new>/<memory>, and constexpr placement new doesn't exist without
// std::construct_at. Relax to raw storage the day a
// non-default-constructible consumer appears.
//
// Growth is explicit (code-std.md §5), in two flavors (§6's offensive
// split): push_back is the contract — full means the caller mis-sized,
// a bug, so it VERIFYs and KLEE proves the trap unreachable;
// try_push_back is for data-driven fills, where "full" is
// environmental and the caller holds the policy. T18's ErrorOr<void>
// subsumes GrowthResult when it lands. Bounds are carried, not checked
// — same doctrine as Span (span.hpp).

#include "verify.hpp"

#include <cstddef>
#include <cstdint>
#include <type_traits>

namespace lib {

enum class GrowthResult : uint8_t { Ok, OutOfCapacity };

template <typename T, std::size_t Capacity> class StaticVector {
    static_assert(Capacity > 0, "T[0] is not ISO C++");
    static_assert(std::is_default_constructible_v<T> && std::is_copy_assignable_v<T> &&
                      std::is_trivially_destructible_v<T>,
                  "StaticVector stores a plain T array (see header comment)");

public:
    constexpr StaticVector() = default;

    // Infallible growth for sized-by-construction producers: full is a
    // mis-sizing bug, so trap (verify.hpp) — KLEE proves the trap
    // unreachable per harness, and provable bounds are elided.
    constexpr void push_back(const T& value) {
        VERIFY(m_size < Capacity);
        m_storage[m_size] = value;
        ++m_size;
    }

    [[nodiscard]] constexpr GrowthResult try_push_back(const T& value) {
        if (m_size == Capacity) {
            return GrowthResult::OutOfCapacity;
        }
        m_storage[m_size] = value;
        ++m_size;
        return GrowthResult::Ok;
    }

    constexpr void clear() {
        m_size = 0;
    }

    [[nodiscard]] constexpr T& operator[](std::size_t index) {
        return m_storage[index];
    }
    [[nodiscard]] constexpr const T& operator[](std::size_t index) const {
        return m_storage[index];
    }

    [[nodiscard]] constexpr std::size_t size() const {
        return m_size;
    }
    [[nodiscard]] constexpr std::size_t capacity() const {
        return Capacity;
    }
    [[nodiscard]] constexpr bool is_empty() const {
        return m_size == 0;
    }

    [[nodiscard]] constexpr T* begin() {
        return m_storage;
    }
    [[nodiscard]] constexpr const T* begin() const {
        return m_storage;
    }
    [[nodiscard]] constexpr T* end() {
        return m_storage + m_size;
    }
    [[nodiscard]] constexpr const T* end() const {
        return m_storage + m_size;
    }

private:
    // Value-initialized so the constexpr story has no indeterminate
    // bytes; m_size alone decides which elements are live. This array is
    // the adoption point of the type, same role as Span's.
    // NOLINTNEXTLINE(cppcoreguidelines-avoid-c-arrays,modernize-avoid-c-arrays)
    T m_storage[Capacity]{};
    std::size_t m_size = 0;
};

} // namespace lib
