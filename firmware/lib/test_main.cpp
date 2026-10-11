// Host runner for the TEST harness (test.hpp): defines the report hook
// and extern "C" main (no libc main under -ffreestanding,
// code-std-cpp.md#1-language-and-toolchain). Reporting is write(2) —
// the one syscall, declared by hand, so no hosted header enters the
// tree — over the foundation string cells: messages assemble in a
// generously-sized StaticString (static_string.hpp), and write takes
// the StringView out. main returns the 1-based index of the first
// failing case, so the exit code names the failing check even with
// output swallowed; suites past 255 cases saturate the exit code (the
// report output stays exact).

#include "static_string.hpp"
#include "string_view.hpp"
#include "test.hpp"

// write(2), declared by hand with LP64 ssize_t/size_t — the one
// syscall the runner needs.
extern "C" long write(int fd, const void* buffer, unsigned long count);

namespace {

void print(lib::StringView text) {
    write(1, text.data(), text.size());
}

} // namespace

namespace lib::test {

void case_failed(const Failure& failure) {
    // Generously sized by construction: full would be a mis-sizing
    // bug, and StaticString's VERIFY says so.
    StaticString<256> message;
    message.append("  FAIL ");
    message.append(current_case->name);
    message.append(": ");
    message.append(failure.condition);
    message.append(" (");
    message.append(failure.file);
    message.append(":");
    message.append(static_cast<unsigned long>(failure.line));
    message.append(")\n");
    print(message);
}

} // namespace lib::test

extern "C" int main() {
    const lib::test::Report report = lib::test::run_all_cases();
    lib::StaticString<64> summary;
    summary.append(static_cast<unsigned long>(report.case_count));
    summary.append(" cases, ");
    summary.append(static_cast<unsigned long>(report.failure_count));
    summary.append(" failed\n");
    print(summary);
    return report.first_failure;
}
