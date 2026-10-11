// Host runtime tests for TRY — the one foundation-library cell that
// can't be constexpr-proved (a statement expression is not a constant
// expression, so lib.cpp's static_asserts can't reach it). Runs under
// meson's test runner on the host build only, as named TEST_CASEs over
// the TEST harness (test.hpp) — the harness's first consumer, written
// to read as usage examples.

#include "arena.hpp"
#include "error_or.hpp"
#include "span.hpp"
#include "static_vector.hpp"
#include "test.hpp"

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

// Move-only values through TRY: the arena handle comes out owning its
// slot — release_value's move path.
lib::ErrorOr<lib::ArenaPtr<uint32_t, 2>> take_slot(lib::StaticArena<uint32_t, 2>& arena) {
    return TRY(arena.try_allocate());
}

} // namespace

TEST_CASE(try_hands_the_value_up) {
    const lib::ErrorOr<uint32_t> ok = doubled(uint32_t{21});
    EXPECT(!ok.is_error());
    EXPECT(ok.value() == 42);
}

TEST_CASE(try_propagates_the_error) {
    const lib::ErrorOr<uint32_t> bad = doubled(lib::Error::OutOfCapacity);
    EXPECT(bad.is_error());
    EXPECT(bad.error() == lib::Error::OutOfCapacity);
}

TEST_CASE(try_stops_at_the_first_refusal) {
    lib::StaticVector<uint8_t, 3> vec;
    lib::StaticVector<uint8_t, 2> two;
    two.push_back(1);
    two.push_back(2);
    EXPECT(!append_all(vec, two).is_error());
    EXPECT(vec.size() == 2);

    lib::StaticVector<uint8_t, 4> four;
    four.push_back(3);
    four.push_back(4);
    four.push_back(5);
    four.push_back(6);
    const lib::ErrorOr<void> filled = append_all(vec, four);
    // One slot was free: 3 landed, the 4 refused, propagation stopped.
    EXPECT(filled.is_error());
    EXPECT(filled.error() == lib::Error::OutOfCapacity);
    EXPECT(vec.size() == 3);
    EXPECT(vec[2] == 3);
}

TEST_CASE(static_vector_passes_where_a_span_is_taken) {
    // The std::vector → std::span conversion's analog.
    lib::StaticVector<uint8_t, 3> vec;
    vec.push_back(1);
    vec.push_back(2);
    vec.push_back(3);

    lib::StaticVector<uint8_t, 3> copied;
    EXPECT(!append_all(copied, vec).is_error());
    EXPECT(copied.size() == 3);
    EXPECT(copied[2] == 3);
}

TEST_CASE(try_moves_owning_handles) {
    lib::StaticArena<uint32_t, 2> arena;
    lib::ErrorOr<lib::ArenaPtr<uint32_t, 2>> first = take_slot(arena);
    EXPECT(!first.is_error());
    *first.value() = 7;

    const lib::ErrorOr<lib::ArenaPtr<uint32_t, 2>> second = take_slot(arena);
    EXPECT(!second.is_error());
    EXPECT(arena.free_count() == 0);

    const lib::ErrorOr<lib::ArenaPtr<uint32_t, 2>> third = take_slot(arena);
    EXPECT(third.is_error());
    EXPECT(third.error() == lib::Error::OutOfCapacity);

    // The moved-out handles still own their slots.
    EXPECT(*first.value() == 7);
}
