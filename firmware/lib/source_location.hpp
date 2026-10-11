#pragma once

// SourceLocation — std::source_location's freestanding stand-in. The
// mechanism is the standard's: current()'s parameters default to the
// compiler builtins (__builtin_FILE() and friends), and a default
// argument instantiates at the call expression, so the builtins
// evaluate to the *caller's* location. A call inside a macro
// expansion captures the line where the macro was invoked — which is
// how EXPECT (test.hpp) reports the check's own line with no
// __FILE__/__LINE__ in sight. The builtins are compiler primitives,
// so this is as freestanding as it gets. std's column() is omitted —
// __builtin_COLUMN is clang-only (the rv32ec GCC build can't compile
// it), and no consumer has appeared.
//
// file_name/function_name come back as StringView (string_view.hpp):
// strings cross interfaces as views, never const char* — the builtins
// hand over NUL-terminated literals, and the view measures them once,
// constexpr-folded at any constant call site.
//
// No strings on the target (code-std-cpp.md#1-language-and-toolchain):
// under OPARROY_TARGET, current() captures the line alone and the
// views stay empty, so a capture references no string literals and the
// µC image carries none. Full site identity is recoverable host-side
// from the ELF instead — addr2line maps the site's PC, and the source
// line it lands on is the condition text.

#include "string_view.hpp"

namespace lib {

class SourceLocation {
public:
    // The empty location.
    constexpr SourceLocation() = default;

#if defined(OPARROY_TARGET)
    // Line-only capture — see the header comment.
    static constexpr SourceLocation current(int line = __builtin_LINE()) {
        SourceLocation location;
        location.m_line = line;
        return location;
    }
#else
    // Callers never pass arguments — the defaults are the payload.
    // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
    static constexpr SourceLocation current(StringView file = __builtin_FILE(),
                                            StringView function = __builtin_FUNCTION(),
                                            int line = __builtin_LINE()) {
        SourceLocation location;
        location.m_file = file;
        location.m_function = function;
        location.m_line = line;
        return location;
    }
#endif

    [[nodiscard]] constexpr StringView file_name() const {
        return m_file;
    }
    [[nodiscard]] constexpr StringView function_name() const {
        return m_function;
    }
    [[nodiscard]] constexpr int line() const {
        return m_line;
    }

private:
    StringView m_file;
    StringView m_function;
    int m_line = 0;
};

} // namespace lib
