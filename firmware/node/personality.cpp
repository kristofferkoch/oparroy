// The node's boot-time identity (personality.hpp): reads the factory
// 96-bit ESIG UNIID (RM §15.2 Table 15-1) and the personality type byte
// (option-byte Data0, RM §16.5; phy-analysis §6), packs them into the
// ENUM stamp (firmware/protocol/enum.hpp), and VERIFYs the node config
// against the result — the runtime successor of rx.cpp's bring-up-era
// static_assert (node.hpp: callers VERIFY config_valid at setup).
//
// The stamp storage is plain zero-init .bss (startup.cpp runs no
// .init_array): rx.cpp's node binds its slices by address at static-init
// time, and this function fills the bytes in before the first frame can
// flow — it runs ahead of rx_init() in node_main.

#include "personality.hpp"

#include "../lib/verify.hpp"
#include "../protocol/enum.hpp"
#include "../protocol/node.hpp"
#include "regs.hpp"

namespace oparroy {

// NOLINTNEXTLINE(cppcoreguidelines-avoid-non-const-global-variables) — written once at boot
EnumStamp stamp;

// personality_type's contract, pinned at compile time — the
// host-testable half of the split (personality.hpp).
static_assert(personality_type(0x42, 0xBD) == 0x42); // a valid pair passes through
static_assert(personality_type(0x00, 0xFF) == 0x00); // programmed-to-zero is a valid 0x00
static_assert(personality_type(0xFF, 0xFF) == 0x00); // erased reads as plain node
static_assert(personality_type(0xA5, 0x5B) == 0x00); // a corrupted inverse reads as plain node

} // namespace oparroy

void personality_init() {
    // Both blocks are readable straight out of reset — flash reads at
    // the 8 MHz reset clock need no wait states (RM §16.3.1) and the
    // option bytes were loaded at system reset (RM §16.5).
    const Esig volatile& id = esig();
    const OptionBytes volatile& ob = option_bytes();
    oparroy::stamp = oparroy::pack_stamp(id.uniid1, id.uniid2, id.uniid3,
                                         oparroy::personality_type(ob.data0, ob.ndata0));
    VERIFY(
        oparroy::Node::config_valid(oparroy::personality_config(), oparroy::personality_latch()));
}
