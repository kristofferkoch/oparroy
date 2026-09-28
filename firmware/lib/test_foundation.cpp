// Host runtime tests for TRY — the one foundation-library cell that
// can't be constexpr-proved (a statement expression is not a constant
// expression, so lib.cpp's static_asserts can't reach it). Runs under
// meson's test runner on the host build only; each check returns its
// own index on failure, so the exit code names the failing check — no
// hosted I/O in a freestanding test.

#include "error_or.hpp"
#include "span.hpp"
#include "static_vector.hpp"

#include <cstdint>

namespace {

// Value propagation: TRY hands the value up, doubled on the way.
lib::ErrorOr<uint32_t> doubled(lib::ErrorOr<uint32_t> input) {
    const uint32_t value = TRY(input);
    return value * 2;
}

// ErrorOr<void> propagation: a data-driven fill that must stop at the
// first refusal, error in hand.
lib::ErrorOr<void> append_all(lib::StaticVector<uint8_t, 3>& vec, lib::Span<const uint8_t> values) {
    for (const uint8_t value : values) {
        TRY(vec.try_push_back(value));
    }
    return {};
}

} // namespace

extern "C" int main() {
    const lib::ErrorOr<uint32_t> ok = doubled(uint32_t{21});
    if (ok.is_error() || ok.value() != 42) {
        return 1;
    }
    const lib::ErrorOr<uint32_t> bad = doubled(lib::Error::OutOfCapacity);
    if (!bad.is_error() || bad.error() != lib::Error::OutOfCapacity) {
        return 2;
    }

    lib::StaticVector<uint8_t, 3> vec;
    const uint8_t two[2] = {1, 2};
    if (append_all(vec, lib::Span<const uint8_t>{two}).is_error() || vec.size() != 2) {
        return 3;
    }
    const uint8_t four[4] = {3, 4, 5, 6};
    const lib::ErrorOr<void> filled = append_all(vec, lib::Span<const uint8_t>{four});
    // One slot was free: 3 landed, the 4 refused, propagation stopped.
    if (!filled.is_error() || filled.error() != lib::Error::OutOfCapacity || vec.size() != 3 ||
        vec[2] != 3) {
        return 4;
    }
    return 0;
}
