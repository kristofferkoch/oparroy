// Host runner for the TEST harness (test.hpp): defines the report hook
// and extern "C" main (no libc main under -ffreestanding,
// code-std-cpp.md#1-language-and-toolchain). Reporting is write(2)
// plus a hand-rolled itoa, both declared by hand — no hosted header
// enters the tree, so test binaries stay on the shipped freestanding
// configuration. main returns the 1-based index of the first failing
// case, so the exit code names the failing check even with output
// swallowed; suites past 255 cases saturate the exit code (the report
// output stays exact).

#include "range.hpp"
#include "static_vector.hpp"
#include "test.hpp"

#include <cstddef>

// write(2), declared by hand with LP64 ssize_t/size_t — the one
// syscall the runner needs.
extern "C" long write(int fd, const void* buffer, unsigned long count);

namespace {

void print(const char* text) {
    unsigned long length = 0;
    // NOLINTNEXTLINE(cppcoreguidelines-pro-bounds-constant-array-index)
    while (text[length] != '\0') {
        ++length;
    }
    write(1, text, length);
}

// itoa by hand: digits generate least-significant first, then reverse.
void print_unsigned(unsigned long value) {
    lib::StaticVector<char, 20> digits; // 2^64 - 1 is 20 decimal digits
    if (value == 0) {
        digits.push_back('0');
    }
    while (value != 0) {
        digits.push_back(static_cast<char>('0' + (value % 10)));
        value /= 10;
    }
    for (const std::size_t i : lib::irange(digits.size() / 2)) {
        const char tmp = digits[i];
        digits[i] = digits[digits.size() - 1 - i];
        digits[digits.size() - 1 - i] = tmp;
    }
    write(1, digits.begin(), digits.size());
}

} // namespace

namespace lib::test {

void case_failed(const char* condition, const char* file, int line) {
    print("  FAIL ");
    print(current_case->name);
    print(": ");
    print(condition);
    print(" (");
    print(file);
    print(":");
    print_unsigned(static_cast<unsigned long>(line));
    print(")\n");
}

} // namespace lib::test

extern "C" int main() {
    const lib::test::Report report = lib::test::run_all_cases();
    print_unsigned(static_cast<unsigned long>(report.case_count));
    print(" cases, ");
    print_unsigned(static_cast<unsigned long>(report.failure_count));
    print(" failed\n");
    return report.first_failure;
}
