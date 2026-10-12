/* CH32V003F4P6 memory layout (RM §1.2): 16 KB CodeFlash at 0x08000000,
 * 2 KB SRAM at 0x20000000. The vector table must land at the flash
 * origin — entry 0 is the reset path (datasheets/CH32V003/notes/
 * qingke-core.md) — and the mtvec base must be 1 KB-aligned
 * (PM §3.2), which the flash origin satisfies.
 * Overflow of either region is a link error from ld itself. */

OUTPUT_FORMAT("elf32-littleriscv")
OUTPUT_ARCH(riscv)
ENTRY(node_reset)

MEMORY {
    FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 16K
    RAM (xrw)  : ORIGIN = 0x20000000, LENGTH = 2K
}

SECTIONS {
    /* Vector table first: entry 0 (the reset `j`) at 0x08000000. */
    .vectors : {
        _vector_base = .;
        KEEP(*(.vectors.reset))
        KEEP(*(.vectors.table))
    } > FLASH
    ASSERT(_vector_base == ORIGIN(FLASH),
           "vector table must sit at the flash origin (reset entry 0)")

    .text : {
        *(.text .text.*)
    } > FLASH

    .rodata : {
        *(.srodata .srodata.*)
        *(.rodata .rodata.*)
    } > FLASH

    /* .data runs from RAM, loads from flash; startup copies
     * _sidata.. into _sdata.._edata. __global_pointer$ is only the
     * anchor gp relaxation points at — nothing links small-data yet,
     * but the reset path sets gp against it unconditionally. */
    .data : {
        . = ALIGN(4);
        __global_pointer$ = . + 0x800;
        _sdata = .;
        *(.sdata .sdata.*)
        *(.data .data.*)
        . = ALIGN(4);
        _edata = .;
    } > RAM AT > FLASH
    _sidata = LOADADDR(.data);

    .bss : {
        . = ALIGN(4);
        _sbss = .;
        *(.sbss .sbss.*)
        *(.bss .bss.*)
        *(COMMON)
        . = ALIGN(4);
        _ebss = .;
    } > RAM

    /* Stack descends from the top of SRAM (startup sets sp = _estack). */
    _estack = ORIGIN(RAM) + LENGTH(RAM);

    /DISCARD/ : {
        *(.comment)
        *(.note*)
        *(.eh_frame*)
    }
}
