#pragma once

// StringView — the read-only string view, std::string_view's
// freestanding stand-in and Span's string sibling (span.hpp):
// std::string_view is outside the freestanding header set
// (code-std-cpp.md#1-language-and-toolchain), so we grow our own.
// Strings cross interfaces as StringView, never as const char* plus a
// separate length — and a literal's length comes from the array
// reference, never a runtime strlen.
//
// Bounds are carried, not checked — same doctrine as Span (span.hpp).

#include <cstddef>

namespace lib {

class StringView {
public:
    // The empty view.
    constexpr StringView() : m_data(nullptr), m_size(0) {}

    constexpr StringView(const char* data, std::size_t size) : m_data(data), m_size(size) {}

    // Literal adoption: the array reference carries the length, minus
    // the NUL terminator. Banning C arrays can't apply to the adoption
    // point itself (span.hpp's whole-array ctor, same role).
    template <std::size_t N>
    // NOLINTNEXTLINE(cppcoreguidelines-avoid-c-arrays,modernize-avoid-c-arrays)
    constexpr StringView(const char (&literal)[N]) : m_data(literal), m_size(N - 1) {}

    // NUL-terminated adoption: the length is measured by hand, no
    // <cstring> (code-std-cpp.md#1-language-and-toolchain's header
    // set). constexpr, so a constant c_str folds at compile time.
    constexpr StringView(const char* c_str) : m_data(c_str), m_size(length_of(c_str)) {}

    [[nodiscard]] constexpr const char& operator[](std::size_t index) const {
        return m_data[index];
    }
    [[nodiscard]] constexpr std::size_t size() const {
        return m_size;
    }
    [[nodiscard]] constexpr bool is_empty() const {
        return m_size == 0;
    }

    [[nodiscard]] constexpr const char* data() const {
        return m_data;
    }
    [[nodiscard]] constexpr const char* begin() const {
        return m_data;
    }
    [[nodiscard]] constexpr const char* end() const {
        return m_data + m_size;
    }

private:
    static constexpr std::size_t length_of(const char* c_str) {
        std::size_t length = 0;
        while (c_str[length] != '\0') {
            ++length;
        }
        return length;
    }

    const char* m_data;
    std::size_t m_size;
};

constexpr bool operator==(StringView a, StringView b) {
    if (a.size() != b.size()) {
        return false;
    }
    for (std::size_t i = 0; i < a.size(); ++i) {
        if (a[i] != b[i]) {
            return false;
        }
    }
    return true;
}

} // namespace lib
