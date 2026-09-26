// Toolchain smoke test (T16b): proves the freestanding flag set
// (code-std.md §2) compiles clean for host, host LLVM bitcode (KLEE's
// input, DESIGN.md §8), and RV32EC. Not firmware logic — delete when
// T16c/T11 supersede it.

#include <array>
#include <cstddef>
#include <cstdint>
#include <new> // IWYU pragma: keep (placement new — misc-include-cleaner false positive)

namespace {

enum class SlotState : uint8_t {
    Idle,
    Armed,
    Forwarding,
};

struct NodeConfig {
    uint8_t node_id;
    uint8_t slot_count;
    bool supervisor;
};

constexpr std::array node_configs{
    NodeConfig{.node_id = 0, .slot_count = 8, .supervisor = true},
    NodeConfig{.node_id = 1, .slot_count = 8, .supervisor = false},
};

// The MMIO pattern (code-std.md §5): a volatile register file placed
// over caller storage with placement new.
struct UartRegisters {
    volatile uint32_t data;
    volatile uint32_t status;
};

constexpr uint32_t status_tx_empty = 1u << 0;

[[nodiscard]] bool tx_ready(const UartRegisters& regs) {
    return (regs.status & status_tx_empty) != 0;
}

// Exhaustive switch over a closed enum, no default (code-std.md §3).
[[nodiscard]] constexpr SlotState advance(SlotState state, bool frame_waiting) {
    switch (state) {
    case SlotState::Idle:
        return frame_waiting ? SlotState::Armed : SlotState::Idle;
    case SlotState::Armed:
        return SlotState::Forwarding;
    case SlotState::Forwarding:
        return frame_waiting ? SlotState::Forwarding : SlotState::Idle;
    }
    // GCC doesn't treat an exhaustive enum switch as covering;
    // -Wswitch-enum still guards against a missed enumerator.
    __builtin_unreachable();
}

static_assert(node_configs[0].supervisor);
static_assert(advance(SlotState::Armed, false) == SlotState::Forwarding);

} // namespace

// Freestanding has no libc `main` (clang mangles a C++ `main` under
// -ffreestanding); entries are extern "C" — the reset handler on target,
// a named entry for KLEE (`klee --entry-point=smoke_main`).
extern "C" int smoke_main() {
    alignas(UartRegisters) std::array<std::byte, sizeof(UartRegisters)> register_storage{};
    auto* uart = new (register_storage.data()) UartRegisters{};
    uart->status = status_tx_empty;
    const SlotState next = advance(SlotState::Idle, tx_ready(*uart));
    return next == SlotState::Armed ? 0 : 1;
}
