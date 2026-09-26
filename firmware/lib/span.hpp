#pragma once

// Span<T> — the read-only view type, the first cell of the foundation
// library (DESIGN.md §8). std::span is outside the
// freestanding header set (code-std.md §2), so we grow our own. Views
// and buffers cross interfaces as Span, never as T* plus a separate
// length (code-std.md §5).
//
// Bounds are carried, not checked: the defect class is owned by KLEE's
// out-of-bounds detection and fuzzing (code-std.md §1), with the
// foundation library's VERIFY adding the target-side hook. No silent
// clamping — a wrong index must stay loud.

#include <cstddef>

namespace lib {

template <typename T> class Span {
public:
    constexpr Span(const T* data, std::size_t size) : m_data(data), m_size(size) {}

    // Whole-array view — the decay-free way to pass a C array. This
    // reference is where a C array is adopted into the view world;
    // banning C arrays can't apply to the adoption point itself.
    // NOLINTNEXTLINE(cppcoreguidelines-avoid-c-arrays,modernize-avoid-c-arrays)
    template <std::size_t N> constexpr Span(const T (&array)[N]) : m_data(array), m_size(N) {}

    [[nodiscard]] constexpr const T& operator[](std::size_t index) const {
        return m_data[index];
    }
    [[nodiscard]] constexpr std::size_t size() const {
        return m_size;
    }

    [[nodiscard]] constexpr Span subspan(std::size_t offset, std::size_t count) const {
        return Span{m_data + offset, count};
    }

    [[nodiscard]] constexpr const T* begin() const {
        return m_data;
    }
    [[nodiscard]] constexpr const T* end() const {
        return m_data + m_size;
    }

private:
    const T* m_data;
    std::size_t m_size;
};

} // namespace lib
