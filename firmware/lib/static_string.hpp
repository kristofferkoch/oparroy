#pragma once

// StaticString<Capacity> — std::string's statically-sized sibling,
// built on StaticVector (static_vector.hpp): statically allocated,
// bounded at Capacity, no NUL terminator carried — the size is the
// truth, and StringView (string_view.hpp) is the view out. The
// assembling type for messages: text, chars, and unsigned numbers
// (decimal, the hand-rolled itoa) append onto it.
//
// Growth is the contract flavor (code-std-cpp.md#5-error-handling):
// full means the caller mis-sized, a bug, so push_back VERIFYs and
// KLEE proves the trap unreachable. Size generously — a message buffer
// that overflows is a mis-sizing bug, not a data condition.
//
// Host-side only: no string assembly code on the target µC
// (code-std-cpp.md#1-language-and-toolchain's no-strings rule), so the
// header refuses to exist there. StringView (string_view.hpp) stays
// available — a view is pointer+size, zero-cost when empty; it's the
// literals and the formatting that must never reach the image.

#if defined(OPARROY_TARGET)
#error "StaticString is host-side: no string assembly code on the target"
#endif

#include "static_vector.hpp"
#include "string_view.hpp"

#include <cstddef>

namespace lib {

template <std::size_t Capacity> class StaticString {
public:
    constexpr void push_back(char c) {
        m_chars.push_back(c);
    }

    constexpr void append(StringView text) {
        for (const char c : text) {
            push_back(c);
        }
    }

    constexpr void append(char c) {
        push_back(c);
    }

    // Decimal itoa, most-significant digit first: the divisor walk
    // never overflows — divisor only grows while value has another
    // digit beyond it.
    constexpr void append(unsigned long value) {
        unsigned long divisor = 1;
        while (value / divisor >= 10) {
            divisor *= 10;
        }
        while (divisor != 0) {
            push_back(static_cast<char>('0' + ((value / divisor) % 10)));
            divisor /= 10;
        }
    }

    constexpr void clear() {
        m_chars.clear();
    }

    [[nodiscard]] constexpr char& operator[](std::size_t index) {
        return m_chars[index];
    }
    [[nodiscard]] constexpr const char& operator[](std::size_t index) const {
        return m_chars[index];
    }

    [[nodiscard]] constexpr std::size_t size() const {
        return m_chars.size();
    }
    [[nodiscard]] constexpr std::size_t capacity() const {
        return Capacity;
    }
    [[nodiscard]] constexpr bool is_empty() const {
        return m_chars.is_empty();
    }

    // The StaticVector → Span conversion's string analog: a
    // StaticString passes implicitly wherever a view is taken.
    constexpr operator StringView() const {
        return StringView{m_chars.begin(), m_chars.size()};
    }

    [[nodiscard]] constexpr char* begin() {
        return m_chars.begin();
    }
    [[nodiscard]] constexpr const char* begin() const {
        return m_chars.begin();
    }
    [[nodiscard]] constexpr char* end() {
        return m_chars.end();
    }
    [[nodiscard]] constexpr const char* end() const {
        return m_chars.end();
    }

private:
    StaticVector<char, Capacity> m_chars;
};

} // namespace lib
