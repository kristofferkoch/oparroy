#pragma once

// Error / ErrorOr<T> / TRY — the fallible-return machinery, the third
// cell of the foundation library (DESIGN.md §8), modeled on AK's
// ErrorOr: anything that *can* fail returns, it never traps silently
// (code-std.md §6). Error returns are for *environmental* failure —
// hostile input, a full arena — where the caller holds a policy
// decision; contract violations stay VERIFY's (verify.hpp).
//
// Error is a bare code, not AK's string-carrying class: freestanding
// has no string table worth the flash, and the enum keeps every error
// site greppable. Codes accrete as consumers appear (YAGNI). Widen to
// a payload-carrying class the day an error needs more than a code.
//
// ErrorOr stores the value and the error side by side rather than in a
// union: value storage without std::construct_at (outside the
// freestanding header set, code-std.md §2) can't switch lifetimes in
// constexpr, and the side-by-side layout needs no placement new, no
// manual destructor, and admits move-only values (ArenaPtr) next to
// the trivially copyable value types. The price is sizeof(T) +
// sizeof(Error) + 1 per instance — paid on value types that are
// registers wide. T must be default-constructible (the error state
// still holds a value object, never read while is_error()); the error
// field then holds a meaningless code, guarded by m_is_error — the
// documented trade of the union-less layout.
//
// TRY is the one blessed control-flow macro (code-std.md §6): AK's
// idiom, reads like exceptions, compiles to branches. The statement
// expression (__extension__, so -Wpedantic stays quiet) is what lets
// TRY evaluate its operand exactly once and still yield the value;
// both clang and gcc accept it, so the KLEE bitcode and the rv32ec
// cross build share the expansion. if/else form inside — the macro
// itself must stay an expression, so the do-while question doesn't
// arise.

#include "utility.hpp"
#include "verify.hpp"

#include <cstdint>
#include <type_traits>

namespace lib {

enum class Error : uint8_t {
    OutOfCapacity, // a fixed-capacity container or arena is full
};

template <typename T> class [[nodiscard]] ErrorOr {
    static_assert(std::is_default_constructible_v<T>,
                  "ErrorOr stores value and error side by side (see header comment)");

public:
    constexpr ErrorOr(const T& value) : m_value(value) {}
    // The param-not-moved check only recognizes std::move, not lib's.
    // NOLINTNEXTLINE(cppcoreguidelines-rvalue-reference-param-not-moved)
    constexpr ErrorOr(T&& value) : m_value(move(value)) {}
    constexpr ErrorOr(Error error) : m_error(error), m_is_error(true) {}

    constexpr ErrorOr(const ErrorOr&) = default;
    constexpr ErrorOr(ErrorOr&&) = default;
    constexpr ErrorOr& operator=(const ErrorOr&) = default;
    constexpr ErrorOr& operator=(ErrorOr&&) = default;
    constexpr ~ErrorOr() = default;

    [[nodiscard]] constexpr bool is_error() const {
        return m_is_error;
    }

    // Reading the wrong side is a contract violation, not an
    // environmental failure — VERIFY, never a fallback value.
    [[nodiscard]] constexpr T& value() & {
        VERIFY(!m_is_error);
        return m_value;
    }
    [[nodiscard]] constexpr const T& value() const& {
        VERIFY(!m_is_error);
        return m_value;
    }
    constexpr T release_value() && {
        VERIFY(!m_is_error);
        return move(m_value);
    }
    [[nodiscard]] constexpr Error error() const {
        VERIFY(m_is_error);
        return m_error;
    }

private:
    T m_value{};
    Error m_error{};
    bool m_is_error = false;
};

// The void specialization: a bare fallible status — try_* growth
// (code-std.md §5) returns this. Default-constructed is success.
template <> class [[nodiscard]] ErrorOr<void> {
public:
    constexpr ErrorOr() = default;
    constexpr ErrorOr(Error error) : m_error(error), m_is_error(true) {}

    [[nodiscard]] constexpr bool is_error() const {
        return m_is_error;
    }
    constexpr void release_value() const&& {
        VERIFY(!m_is_error);
    }
    [[nodiscard]] constexpr Error error() const {
        VERIFY(m_is_error);
        return m_error;
    }

private:
    Error m_error{};
    bool m_is_error = false;
};

// NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#define TRY(expression)                                                                            \
    __extension__({                                                                                \
        auto&& _temporary_result = (expression);                                                   \
        if (_temporary_result.is_error()) {                                                        \
            return _temporary_result.error();                                                      \
        }                                                                                          \
        move(_temporary_result).release_value();                                                   \
    })

} // namespace lib
