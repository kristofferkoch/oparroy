#pragma once

// StaticArena<T, Capacity> + ArenaPtr — ownership over static storage,
// the freestanding analog of AK's OwnPtr over a heap (DESIGN.md §8,
// code-std.md §5). The arena is a fixed slot pool carved out at static
// allocation time; try_allocate hands out a slot wrapped in an
// ArenaPtr whose destruction returns the slot to the pool — RAII for
// arena slots, no paired alloc/free calls separated by user code.
// Allocation can fail (the pool is full) and that is environmental, so
// try_allocate returns ErrorOr — there is no infallible allocate: a
// pool sized by construction is what StaticVector's push_back contract
// is for.
//
// Elements live in a plain T array under the same contract as
// StaticVector (static_vector.hpp): T must be default-constructible,
// copy-assignable, and trivially destructible, so the type stays fully
// constexpr-usable and cast-free. A slot's T object exists for the
// arena's whole lifetime; allocate/reclaim moves *which slot is owned*
// through the free list, not object lifetimes — reclaiming a
// value-semantic slot needs no destructor run, the next owner
// overwrite-assigns.
//
// The free list is a parallel next-index array, not pointers threaded
// through the slots: the plain-T-array constexpr story above forbids
// reinterpretation games, and the cost is Capacity index bytes of
// static RAM — the IDEAS.md narrow-size-fields note owns shrinking
// that, measurement-driven.
//
// An arena is pinned: ArenaPtr holds the arena's address to hand its
// slot back, so StaticArena deletes copy and move — declare arenas at
// static or member scope, never pass them by value. An ArenaPtr must
// not outlive its arena; with arenas at static storage duration that
// is the natural order, and the discipline is review-owned
// (code-std.md §9). Dereferencing a null (default-constructed or
// moved-from) ArenaPtr is a contract violation — VERIFY, loud on
// target through the §4 failure hook.

#include "error_or.hpp"
#include "range.hpp"
#include "verify.hpp"

#include <cstddef>
#include <type_traits>

namespace lib {

template <typename T, std::size_t Capacity> class StaticArena;

template <typename T, std::size_t Capacity> class ArenaPtr {
public:
    constexpr ArenaPtr() = default;
    constexpr ~ArenaPtr() {
        release();
    }
    constexpr ArenaPtr(ArenaPtr&& other) : m_arena(other.m_arena), m_slot(other.m_slot) {
        other.m_arena = nullptr;
    }
    constexpr ArenaPtr& operator=(ArenaPtr&& other) {
        if (this != &other) {
            release();
            m_arena = other.m_arena;
            m_slot = other.m_slot;
            other.m_arena = nullptr;
        }
        return *this;
    }
    ArenaPtr(const ArenaPtr&) = delete;
    ArenaPtr& operator=(const ArenaPtr&) = delete;

    [[nodiscard]] constexpr T& operator*() {
        VERIFY(m_arena != nullptr);
        return m_arena->m_storage[m_slot];
    }
    [[nodiscard]] constexpr const T& operator*() const {
        VERIFY(m_arena != nullptr);
        return m_arena->m_storage[m_slot];
    }
    // operator-> exposes a raw T* by language rule; it stays inside the
    // ownership-type idiom, not at project interfaces (code-std.md §5).
    [[nodiscard]] constexpr T* operator->() {
        return &**this;
    }
    [[nodiscard]] constexpr const T* operator->() const {
        return &**this;
    }

private:
    friend class StaticArena<T, Capacity>;

    constexpr ArenaPtr(StaticArena<T, Capacity>& arena, std::size_t slot)
        : m_arena(&arena), m_slot(slot) {}

    constexpr void release() {
        if (m_arena != nullptr) {
            m_arena->free_slot(m_slot);
            m_arena = nullptr;
        }
    }

    StaticArena<T, Capacity>* m_arena = nullptr;
    std::size_t m_slot = 0;
};

template <typename T, std::size_t Capacity> class StaticArena {
    static_assert(Capacity > 0, "T[0] is not ISO C++");
    static_assert(std::is_default_constructible_v<T> && std::is_copy_assignable_v<T> &&
                      std::is_trivially_destructible_v<T>,
                  "StaticArena stores a plain T array (same contract as StaticVector)");

public:
    constexpr StaticArena() {
        for (const std::size_t slot : irange(Capacity)) {
            m_next_free[slot] = slot + 1;
        }
    }
    // Pinned: handles point back at the arena (see header comment), so
    // neither copy nor move may exist.
    StaticArena(const StaticArena&) = delete;
    StaticArena& operator=(const StaticArena&) = delete;
    StaticArena(StaticArena&&) = delete;
    StaticArena& operator=(StaticArena&&) = delete;
    constexpr ~StaticArena() = default;

    [[nodiscard]] constexpr ErrorOr<ArenaPtr<T, Capacity>> try_allocate() {
        if (m_free_head == Capacity) {
            return Error::OutOfCapacity;
        }
        const std::size_t slot = m_free_head;
        m_free_head = m_next_free[slot];
        --m_free_count;
        return ArenaPtr<T, Capacity>{*this, slot};
    }

    [[nodiscard]] constexpr std::size_t free_count() const {
        return m_free_count;
    }
    [[nodiscard]] constexpr std::size_t capacity() const {
        return Capacity;
    }

private:
    friend class ArenaPtr<T, Capacity>;

    constexpr void free_slot(std::size_t slot) {
        m_next_free[slot] = m_free_head;
        m_free_head = slot;
        ++m_free_count;
    }

    // Value-initialized, same adoption-point role as StaticVector's
    // array. Capacity doubles as the free-list end sentinel.
    // NOLINTNEXTLINE(cppcoreguidelines-avoid-c-arrays,modernize-avoid-c-arrays)
    T m_storage[Capacity]{};
    // NOLINTNEXTLINE(cppcoreguidelines-avoid-c-arrays,modernize-avoid-c-arrays)
    std::size_t m_next_free[Capacity]{};
    std::size_t m_free_head = 0;
    std::size_t m_free_count = Capacity;
};

} // namespace lib
