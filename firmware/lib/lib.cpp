// Translation unit for the header-only foundation library: keeps the
// GCC cross build (rv32ec) and clang-tidy compiling every lib/ header,
// and hosts the constexpr static_assert proofs of each cell
// (code-std.md §11). TRY's runtime paths live in test_foundation.cpp —
// a statement expression can't be constant-evaluated, so the macro is
// proved on the host test runner instead.

#include "error_or.hpp"
#include "range.hpp"
#include "span.hpp"
#include "static_vector.hpp"
#include "verify.hpp"

#include <cstdint>

namespace lib {

namespace {

    constexpr bool error_or_value_path() {
        ErrorOr<uint32_t> ok = uint32_t{42};
        if (ok.is_error() || ok.value() != 42) {
            return false;
        }
        ok.value() = 7;
        return ok.release_value() == 7;
    }

    constexpr bool error_or_error_path() {
        const ErrorOr<uint32_t> bad = Error::OutOfCapacity;
        return bad.is_error() && bad.error() == Error::OutOfCapacity;
    }

    constexpr bool error_or_void_path() {
        const ErrorOr<void> ok;
        if (ok.is_error()) {
            return false;
        }
        ok.release_value();
        const ErrorOr<void> bad = Error::OutOfCapacity;
        return bad.is_error() && bad.error() == Error::OutOfCapacity;
    }

    // The container-and-view spine used together: range-filled,
    // span-summed — exercises StaticVector, Span, and irange directly
    // (misc-include-cleaner wants every include used, and this TU is
    // where the foundation cells compile).
    constexpr uint32_t sum_of(Span<const uint8_t> values) {
        uint32_t sum = 0;
        for (const uint8_t value : values) {
            sum += value;
        }
        return sum;
    }

    constexpr bool vector_collects_range() {
        StaticVector<uint8_t, 4> vec;
        for (const uint8_t i : irange(uint8_t{4})) {
            vec.push_back(static_cast<uint8_t>(i * 2));
        }
        VERIFY(vec.size() == 4);
        return sum_of(Span<const uint8_t>{vec.begin(), vec.size()}) == 0 + 2 + 4 + 6;
    }

} // namespace

static_assert(error_or_value_path());
static_assert(error_or_error_path());
static_assert(error_or_void_path());
static_assert(vector_collects_range());

} // namespace lib
