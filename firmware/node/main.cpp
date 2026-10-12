// Node firmware entry. This first link proves the rv32ec toolchain
// end-to-end — vector table, startup, linker script — with a park loop;
// the bring-up body (48 MHz clock init, keep-alive strobe, working-LED
// heartbeat) lands next.
//
// extern "C", never returns: no libc main under -ffreestanding
// (code-std-cpp.md#1-language-and-toolchain); startup.cpp's node_boot
// tail-calls here.

extern "C" [[noreturn]] void node_main() {
    for (;;) {
        __asm__ volatile("" ::: "memory");
    }
}
