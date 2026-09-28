// Translation unit for the header-only foundation library: keeps the
// GCC cross build (rv32ec) and clang-tidy compiling every lib/ header,
// and hosts the constexpr static_assert proofs of each cell
// (code-std.md §11). TRY's runtime paths live in test_foundation.cpp —
// a statement expression can't be constant-evaluated, so the macro is
// proved on the host test runner instead.

#include "arena.hpp"
#include "error_or.hpp"
#include "range.hpp"
#include "span.hpp"
#include "static_vector.hpp"
#include "utility.hpp"
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
        return move(ok).release_value() == 7;
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
        move(ok).release_value();
        const ErrorOr<void> bad = Error::OutOfCapacity;
        return bad.is_error() && bad.error() == Error::OutOfCapacity;
    }

    constexpr bool arena_allocates_moves_and_reclaims() {
        StaticArena<uint32_t, 2> arena;
        if (arena.capacity() != 2 || arena.free_count() != 2) {
            return false;
        }
        ErrorOr<ArenaPtr<uint32_t, 2>> first = arena.try_allocate();
        if (first.is_error() || arena.free_count() != 1) {
            return false;
        }
        *first.value() = 11;
        // Move out of the ErrorOr: the handle, not a copy, owns the
        // slot — the moved-from shell frees nothing.
        const ArenaPtr<uint32_t, 2> owned = move(first).release_value();
        if (*owned != 11) {
            return false;
        }
        {
            const ErrorOr<ArenaPtr<uint32_t, 2>> second = arena.try_allocate();
            if (second.is_error() || arena.free_count() != 0) {
                return false;
            }
            const ErrorOr<ArenaPtr<uint32_t, 2>> full = arena.try_allocate();
            if (!full.is_error() || full.error() != Error::OutOfCapacity) {
                return false;
            }
        }
        // second's handle died with its scope: the slot is back.
        if (arena.free_count() != 1) {
            return false;
        }
        const ErrorOr<ArenaPtr<uint32_t, 2>> again = arena.try_allocate();
        return !again.is_error() && arena.free_count() == 0;
    }

    // A struct value, so operator-> has something to point through.
    struct DecodedSample {
        uint32_t period_ticks = 0;
        uint8_t high_ticks = 0;
    };

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

    // lib::move selects the move constructor: ownership of the arena
    // slot transfers to `owned`, and the moved-from shell frees nothing
    // — so the slot comes back exactly once when `owned` dies.
    constexpr bool move_transfers_the_handle() {
        StaticArena<uint32_t, 1> arena;
        ErrorOr<ArenaPtr<uint32_t, 1>> slot = arena.try_allocate();
        if (slot.is_error()) {
            return false;
        }
        { const ArenaPtr<uint32_t, 1> owned = move(slot.value()); }
        return arena.free_count() == 1;
    }

    constexpr bool arena_handle_arrow_access() {
        StaticArena<DecodedSample, 1> arena;
        ErrorOr<ArenaPtr<DecodedSample, 1>> slot = arena.try_allocate();
        if (slot.is_error()) {
            return false;
        }
        slot.value()->period_ticks = 60;
        slot.value()->high_ticks = 20;
        return slot.value()->period_ticks == 60 && (*slot.value()).high_ticks == 20;
    }

} // namespace

static_assert(error_or_value_path());
static_assert(error_or_error_path());
static_assert(error_or_void_path());
static_assert(arena_allocates_moves_and_reclaims());
static_assert(vector_collects_range());
static_assert(move_transfers_the_handle());
static_assert(arena_handle_arrow_access());

} // namespace lib
