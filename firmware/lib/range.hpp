#pragma once

// IntRange<T> / irange() — integer ranges, the second cell of the
// foundation library (DESIGN.md §8). The std::ranges::iota_view stand-in:
// <ranges>/<iterator> are outside the freestanding header set
// (code-std.md §2), so we grow just enough iterator for range-for.
//
// Boundary reasoning lives here, once, instead of at every
// for (i = 0; i < n; ++i) site (code-std.md §3): the interval is
// half-open, iteration stops on pos == end, and ++ only runs while
// pos != end — so incrementing past the type's max is unreachable, on
// any integer width. An inverted or empty range is clamped to empty in
// the constructor, so a negative signed end is a zero-trip loop, never
// UB. zip/enumerate land when a consumer appears (IDEAS.md §Firmware
// library).

#include <type_traits>

namespace lib {

template <typename T> class IntRange {
    static_assert(std::is_integral_v<T> && !std::is_same_v<T, bool>,
                  "IntRange is for integer index types");

public:
    class Iterator {
    public:
        constexpr explicit Iterator(T pos) : m_pos(pos) {}

        [[nodiscard]] constexpr T operator*() const {
            return m_pos;
        }
        constexpr Iterator& operator++() {
            ++m_pos;
            return *this;
        }
        [[nodiscard]] constexpr bool operator==(const Iterator&) const = default;

    private:
        T m_pos;
    };

    constexpr IntRange(T begin, T end) : m_begin(begin), m_end(end > begin ? end : begin) {}

    [[nodiscard]] constexpr Iterator begin() const {
        return Iterator{m_begin};
    }
    [[nodiscard]] constexpr Iterator end() const {
        return Iterator{m_end};
    }

private:
    T m_begin;
    T m_end;
};

template <typename T> [[nodiscard]] constexpr IntRange<T> irange(T end) {
    return IntRange<T>{T{0}, end};
}

template <typename T> [[nodiscard]] constexpr IntRange<T> irange(T begin, T end) {
    return IntRange<T>{begin, end};
}

} // namespace lib
