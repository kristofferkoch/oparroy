#pragma once

// Bit-level wire primitives for the protocol core (DESIGN.md §2).

#include "../lib/span.hpp"

#include <cstdint>

namespace oparroy {

// One bit on the wire. Value-backed (Zero = 0, One = 1) so forwarding
// stays branch-free — a symbolic bit must select, never fork a KLEE path.
enum class Bit : uint8_t {
    Zero = 0,
    One = 1,
};

// MSB-first wire order, the WS2812 convention (DESIGN.md §2): the first
// bit on the wire is the most-significant bit of byte 0.
[[nodiscard]] constexpr Bit bit_at(lib::Span<const uint8_t> bytes, uint32_t index) {
    return static_cast<Bit>((bytes[index / 8] >> (7 - (index % 8))) & 1u);
}

// A fixed run of bits over a byte view — e.g. the telemetry a node
// stamps into its slot (DESIGN.md §2). Fixed-capacity by construction
// (code-std.md §5); bit_count ≤ 8 × bytes.size() is the contract,
// checked by valid().
struct BitSlice {
    lib::Span<const uint8_t> bytes;
    uint16_t bit_count;
};

[[nodiscard]] constexpr bool valid(BitSlice bits) {
    return bits.bit_count <= 8 * bits.bytes.size();
}

[[nodiscard]] constexpr Bit bit_at(BitSlice bits, uint16_t index) {
    return bit_at(bits.bytes, static_cast<uint32_t>(index));
}

} // namespace oparroy
