#pragma once

// TEST — the project's unit-test harness, AK LibTest-style: TEST_CASE
// defines a named case, EXPECT checks a condition inside it, and a
// tiny report hook carries failures out. Tests compile against the
// shipped freestanding configuration — the same headers under the same
// flags — so the suite exercises what ships (DESIGN.md §8's
// test-what-ships doctrine). Packaged frameworks fail that bar: they
// want exceptions, RTTI, or a hosted runtime, and a per-target flag
// fork for tests is exactly the test-build-vs-shipped-build split the
// doctrine rejects. No hosted header enters the tree: the host runner
// (firmware/lib/test_main.cpp) reports with write(2) — the one
// syscall, declared by hand — over the foundation string cells
// (string_view.hpp, static_string.hpp).
//
// The report hook is a wiring point in lib::verify_failed's shape
// (firmware/lib/verify.hpp): declared here, defined once per
// personality. The host runner defines it; a target personality —
// reporting over the debug transport — lands with the firmware that
// owns a transport.
//
// EXPECT records and continues, AK-style — later checks in the same
// case still run. The runner walks the registry in definition order
// and returns the 1-based index of the first failing case; as the
// process exit code that names the failing check even when output is
// swallowed.

#include "source_location.hpp"
#include "string_view.hpp"

namespace lib::test {

using CaseFunction = void (*)();

struct Case {
    StringView name;
    CaseFunction function = nullptr;
    // Registration link, set by Registrar. mutable so the TEST_CASE
    // metadata objects stay const.
    mutable const Case* next = nullptr;
};

// The harness's non-const globals are its mechanism, not firmware
// state — NOLINTed one by one.
// NOLINTNEXTLINE(cppcoreguidelines-avoid-non-const-global-variables)
inline const Case* registry = nullptr;

// The case under execution, set by run_all_cases around each call;
// the report hook reads it for the case name.
// NOLINTNEXTLINE(cppcoreguidelines-avoid-non-const-global-variables)
inline const Case* current_case = nullptr;

// NOLINTNEXTLINE(cppcoreguidelines-avoid-non-const-global-variables)
inline bool current_case_failed = false;

class Registrar {
public:
    explicit Registrar(const Case& test_case) {
        test_case.next = registry;
        registry = &test_case;
    }
};

struct Report {
    int case_count = 0;
    int failure_count = 0;
    // 1-based index of the first failing case in definition order;
    // 0 when all pass.
    int first_failure = 0;
};

// One failed EXPECT, bundled: same-typed parameters would invite
// transposition at every call site (code-std-cpp.md#3-types-and-arithmetic).
struct Failure {
    StringView condition;
    SourceLocation location;
};

// The report hook — the wiring point described in the header comment.
void case_failed(const Failure& failure);

// Runs every registered case, reporting each failed EXPECT through
// case_failed. Registrars prepend, so the registry is reversed into
// definition order first — case indices then match the source, and the
// exit code names the same check a reader finds by counting TEST_CASEs.
inline Report run_all_cases() {
    const Case* reversed = nullptr;
    while (registry != nullptr) {
        const Case* next = registry->next;
        registry->next = reversed;
        reversed = registry;
        registry = next;
    }
    registry = reversed;

    Report report;
    for (const Case* test_case = registry; test_case != nullptr; test_case = test_case->next) {
        ++report.case_count;
        current_case = test_case;
        current_case_failed = false;
        test_case->function();
        if (current_case_failed) {
            ++report.failure_count;
            if (report.first_failure == 0) {
                report.first_failure = report.case_count;
            }
        }
    }
    current_case = nullptr;
    return report;
}

} // namespace lib::test

// The case body is a static member function of a line-numbered struct:
// the linkage checks (misc-use-anonymous-namespace,
// misc-use-internal-linkage) ban both spellings of a namespace-scope
// function but leave member functions alone, and the CamelCase struct
// name keeps readability-identifier-naming quiet — the case's display
// name is the stringized argument, not the identifier.
// NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#define OPARROY_TEST_PASTE_INNER(prefix, line) prefix##line
// NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#define OPARROY_TEST_PASTE(prefix, line) OPARROY_TEST_PASTE_INNER(prefix, line)

// NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#define TEST_CASE(name)                                                                            \
    struct OPARROY_TEST_PASTE(TestCase, __LINE__) {                                                \
        static void run();                                                                         \
    };                                                                                             \
    static const ::lib::test::Case OPARROY_TEST_PASTE(test_meta_, __LINE__){                       \
        #name, &OPARROY_TEST_PASTE(TestCase, __LINE__)::run};                                      \
    static const ::lib::test::Registrar OPARROY_TEST_PASTE(test_reg_, __LINE__){                   \
        OPARROY_TEST_PASTE(test_meta_, __LINE__)};                                                 \
    void OPARROY_TEST_PASTE(TestCase, __LINE__)::run()

// NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#define EXPECT(condition)                                                                          \
    if (condition) {                                                                               \
    } else {                                                                                       \
        ::lib::test::current_case_failed = true;                                                   \
        ::lib::test::case_failed(                                                                  \
            ::lib::test::Failure{#condition, ::lib::SourceLocation::current()});                   \
    }
