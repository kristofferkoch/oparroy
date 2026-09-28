#pragma once

// lib::move — the cast-to-rvalue vocabulary word, AK's spelling
// (AK/Forward.h). <utility> is outside the freestanding header set
// (code-std.md §2), so the one-line word lives here instead of a
// hand-rolled static_cast<T&&> at every site. move is the only word
// grown so far (YAGNI): forward lands the day a perfect-forwarding
// consumer appears.

#include <type_traits>

namespace lib {

// The cast *is* the move — the missing-std-forward check can't see that
// this function is the vocabulary word it asks for.
// NOLINTNEXTLINE(cppcoreguidelines-missing-std-forward)
template <typename T> constexpr std::remove_reference_t<T>&& move(T&& value) {
    return static_cast<std::remove_reference_t<T>&&>(value);
}

} // namespace lib
