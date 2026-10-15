#pragma once

// Array<T, N> — std::array's freestanding stand-in: the fixed-size
// owning container, N in the type (DESIGN.md §8, foundation library).
// std::array is outside the freestanding header set
// (code-std-cpp.md#1-language-and-toolchain), so we grow our own.
// StaticVector's fixed-size sibling (static_vector.hpp): no live size,
// no growth API, nothing to check at runtime — the type is the whole
// invariant. Fixed-size values own as Array, views stay Span
// (span.hpp), and the implicit conversion below is the std::array →
// std::span analog of StaticVector's operator Span.
//
// An aggregate holding the one plain C array — the type's adoption
// point, the same role as Span's whole-array ctor (span.hpp): the
// c-array lint suppression lives here, not at the call sites.
// Aggregate-ness is load-bearing: designated initializers keep working
// (enum.hpp's pack_stamp returns one by value), constexpr construction
// needs no user-declared ctors, and the layout is exactly the array's —
// which is what lets linker-placed tables (startup.cpp's vector_table)
// and DMA-backed rings (node/tx.cpp, node/rx.cpp) be Arrays too.
//
// Bounds are carried, not checked — same doctrine as Span (span.hpp).

#include "span.hpp"

#include <cstddef>

namespace lib {

template <typename T, std::size_t N> struct Array {
    static_assert(N > 0, "T[0] is not ISO C++");

    [[nodiscard]] constexpr T& operator[](std::size_t index) {
        return elems[index];
    }
    [[nodiscard]] constexpr const T& operator[](std::size_t index) const {
        return elems[index];
    }

    // A constant expression, like std::array's — the size is the type.
    [[nodiscard]] constexpr std::size_t size() const {
        return N;
    }

    // The address for the boundaries that speak pointers: DMA config
    // (the MMIO boundary, code-std-cpp.md#4-memory-and-ownership) and
    // klee_make_symbolic in the proof harnesses.
    [[nodiscard]] constexpr T* data() {
        return elems;
    }
    [[nodiscard]] constexpr const T* data() const {
        return elems;
    }

    [[nodiscard]] constexpr T* begin() {
        return elems;
    }
    [[nodiscard]] constexpr const T* begin() const {
        return elems;
    }
    [[nodiscard]] constexpr T* end() {
        return elems + N;
    }
    [[nodiscard]] constexpr const T* end() const {
        return elems + N;
    }

    // The Array → Span conversion, the same AK shape as StaticVector's
    // (static_vector.hpp): an Array passes implicitly wherever a view is
    // taken, and a const Array converts only to Span<const T>.
    constexpr operator Span<T>() {
        return Span<T>{elems, N};
    }
    constexpr operator Span<const T>() const {
        return Span<const T>{elems, N};
    }

    // Public because Array is an aggregate (see the header comment) —
    // read and write through the accessors, never the member.
    // NOLINTNEXTLINE(cppcoreguidelines-avoid-c-arrays,modernize-avoid-c-arrays,misc-non-private-member-variables-in-classes)
    T elems[N];
};

} // namespace lib
