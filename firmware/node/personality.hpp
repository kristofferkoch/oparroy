#pragma once

// The node's identity (DESIGN.md §2, phy-analysis §6): one firmware
// image per ring node; the ENUM stamp (firmware/protocol/enum.hpp)
// carries the factory 96-bit ESIG UNIID plus a personality type byte
// read from option-byte Data0 — personality is provisioning, not code,
// so it survives image reflashes (RM §16.5).
//
// personality_init() packs the stamp once at boot; rx.cpp's node stamps
// it into each frame's first empty slot from then on — both vsync faces
// are the one stamp, never changed after boot. The pure/glue split:
// personality_type() below carries the Data0 read semantics and stays
// host-testable; personality.cpp owns the MMIO reads and the runtime
// VERIFY of the node's config contract.

#include "../protocol/bits.hpp"
#include "../protocol/enum.hpp"
#include "../protocol/node.hpp"

#include <cstdint>

namespace oparroy {

// phy-analysis §6's read rule: Data0 counts only against its stored
// inverse (RM §16.5's load-time checksum) — an inverse mismatch reads
// as 0x00 "plain node", which is also what an erased pair (0xFF/0xFF)
// decodes to.
[[nodiscard]] constexpr uint8_t personality_type(uint8_t data0, uint8_t ndata0) {
    return data0 == static_cast<uint8_t>(~ndata0) ? data0 : 0x00;
}

// The one stamp storage (personality.cpp): zero-init out of reset,
// packed by personality_init() before the first frame flows.
// NOLINTNEXTLINE(cppcoreguidelines-avoid-non-const-global-variables) — written once at boot
extern EnumStamp stamp;

// The node's slot width — the ENUM slot (enum.hpp); the node discovers
// its position, there is no positional config (node.hpp).
[[nodiscard]] constexpr NodeConfig personality_config() {
    return {.slot_bits = enum_slot_bits};
}

// The stamp's DoubleBuffer view: both faces are the one stamp — the
// Array converts to Span at the BitSlice boundary (stamp_slice), so a
// boot-time repack is visible through slices formed at static-init
// time. Address constants only, so rx.cpp's globals stay
// constant-initialized (startup.cpp runs no .init_array).
[[nodiscard]] constexpr DoubleBuffer<BitSlice> personality_latch() {
    return {.front = stamp_slice(stamp), .back = stamp_slice(stamp)};
}

} // namespace oparroy

// Read the ESIG UNIID and option-byte Data0, pack the ENUM stamp, and
// VERIFY the node config against it. Call once from node_main, before
// rx_init() arms the capture path.
void personality_init();
