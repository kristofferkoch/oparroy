#pragma once

// The ENUM wire format (DESIGN.md §2): the pre-sized frame the
// supervisor originates for enumeration — one all-zero slot per node.
// A slot is 105 bits: a leading occupancy marker bit, then the 104-bit
// stamp (96-bit factory UNIID + 8-bit personality type byte,
// phy-analysis §6). An all-zero slot is empty (marker 0); a stamp's
// marker is 1. The marker is what makes find-first-empty-slot
// discovery possible under the strict 1:1 per-bit cut-through contract
// (node.hpp): the node decides at a slot's *first* bit — zero
// lookahead — instead of after its last.
//
// MSB-first wire order (bits.hpp): the marker is bit 7 of byte 0, then
// uniid1 (the low-address ESIG word) MSB-first, uniid2, uniid3, and
// the type byte closes the slot.

#include "../lib/array.hpp"
#include "../lib/span.hpp"
#include "bits.hpp"

#include <cstdint>

namespace oparroy {

inline constexpr uint16_t enum_max_nodes = 8;
inline constexpr uint16_t enum_uniid_bits = 96;
inline constexpr uint16_t enum_type_bits = 8;
// The stamp proper: 96-bit UNIID + type byte.
inline constexpr uint16_t enum_stamp_bits = enum_uniid_bits + enum_type_bits;
// On the wire the stamp sits behind the 1-bit occupancy marker.
inline constexpr uint16_t enum_slot_bits = 1 + enum_stamp_bits;
inline constexpr uint32_t enum_frame_bits = static_cast<uint32_t>(enum_max_nodes) * enum_slot_bits;
// 105 bits = 13.125 bytes — the packed stamp rounds up (tail bits zero).
inline constexpr uint16_t enum_stamp_bytes = (enum_slot_bits + 7) / 8;

// The packed slot content a node stamps. The stamp is a fixed-size
// value — an Array (array.hpp), so pack_stamp stays constexpr-returnable
// by value and the size rides in the type; the implicit Span conversion
// adopts it at the BitSlice boundary (stamp_slice).
struct EnumStamp {
    lib::Array<uint8_t, enum_stamp_bytes> bytes;
};

// The BitSlice view of a packed stamp — what the node stamps into its
// slot (the DoubleBuffer faces in the glue).
[[nodiscard]] constexpr BitSlice stamp_slice(const EnumStamp& stamp) {
    return BitSlice{.bytes = stamp.bytes, .bit_count = enum_slot_bits};
}

// Bytewise assembly along the layout in the header comment — every
// subscript is a constant expression, and constexpr all the way down.
[[nodiscard]] constexpr EnumStamp pack_stamp(uint32_t uniid1, uint32_t uniid2, uint32_t uniid3,
                                             uint8_t type) {
    return EnumStamp{.bytes = {{
                         static_cast<uint8_t>(0x80u | ((uniid1 >> 25) & 0x7Fu)), // marker
                         static_cast<uint8_t>(uniid1 >> 17),
                         static_cast<uint8_t>(uniid1 >> 9),
                         static_cast<uint8_t>(uniid1 >> 1),
                         static_cast<uint8_t>((uniid1 << 7) | ((uniid2 >> 25) & 0x7Fu)),
                         static_cast<uint8_t>(uniid2 >> 17),
                         static_cast<uint8_t>(uniid2 >> 9),
                         static_cast<uint8_t>(uniid2 >> 1),
                         static_cast<uint8_t>((uniid2 << 7) | ((uniid3 >> 25) & 0x7Fu)),
                         static_cast<uint8_t>(uniid3 >> 17),
                         static_cast<uint8_t>(uniid3 >> 9),
                         static_cast<uint8_t>(uniid3 >> 1),
                         static_cast<uint8_t>((uniid3 << 7) | ((type >> 1) & 0x7Fu)),
                         static_cast<uint8_t>(type << 7),
                     }}};
}

struct UnpackedStamp {
    uint32_t uniid1;
    uint32_t uniid2;
    uint32_t uniid3;
    uint8_t type;
};

// The inverse of pack_stamp, over a slot's wire bits — the supervisor /
// host decode side, and the tests' round-trip check. The slot must
// carry at least enum_slot_bits bits (BitSlice's contract, bits.hpp).
[[nodiscard]] constexpr UnpackedStamp unpack_stamp(BitSlice slot) {
    const lib::Span<const uint8_t> bytes = slot.bytes;
    return UnpackedStamp{
        .uniid1 = (static_cast<uint32_t>(bytes[0] & 0x7Fu) << 25) |
                  (static_cast<uint32_t>(bytes[1]) << 17) | (static_cast<uint32_t>(bytes[2]) << 9) |
                  (static_cast<uint32_t>(bytes[3]) << 1) | static_cast<uint32_t>(bytes[4] >> 7),
        .uniid2 = (static_cast<uint32_t>(bytes[4] & 0x7Fu) << 25) |
                  (static_cast<uint32_t>(bytes[5]) << 17) | (static_cast<uint32_t>(bytes[6]) << 9) |
                  (static_cast<uint32_t>(bytes[7]) << 1) | static_cast<uint32_t>(bytes[8] >> 7),
        .uniid3 = (static_cast<uint32_t>(bytes[8] & 0x7Fu) << 25) |
                  (static_cast<uint32_t>(bytes[9]) << 17) |
                  (static_cast<uint32_t>(bytes[10]) << 9) |
                  (static_cast<uint32_t>(bytes[11]) << 1) | static_cast<uint32_t>(bytes[12] >> 7),
        .type = static_cast<uint8_t>((bytes[12] << 1) | (bytes[13] >> 7)),
    };
}

} // namespace oparroy
