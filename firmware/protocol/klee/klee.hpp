#pragma once

// KLEE harness support (DESIGN.md §8). The intrinsics are declared
// here — klee/klee.h's exact surface — so harnesses need no include path
// into the klee package; KLEE intercepts both by name, no linking.

#include <cstddef>

extern "C" void klee_make_symbolic(void* address, size_t size, const char* name);
extern "C" [[noreturn]] void klee_report_error(const char* file, int line, const char* message,
                                               const char* suffix);

// The proof statement: KLEE hunts for any path that reaches the error;
// none found = proved. Every harness was watched failing before it
// passed (red/green, code-std.md#4-tests). if/else form, not do-while —
// cppcoreguidelines-avoid-do-while is in the tidy set (code-std.md#3-enforcement-split).
#define KLEE_PROVE(condition)                                                                      \
    if (condition) {                                                                               \
    } else {                                                                                       \
        klee_report_error(__FILE__, __LINE__, "proof failed: " #condition, "PROVE");               \
    }
