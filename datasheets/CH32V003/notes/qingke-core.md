# CH32V003 core — QingKe V2A (startup, mtvec, PFIC CSRs)

Part of the CH32V003 notes — part identity, source documents, and citation
conventions in [facts.md](facts.md). Sources: PM (the QingKeV2 processor
manual, vendored as `QingKeV2PM-processor-manual-v1.3.pdf`); RM ch.6.

## Reset and vector table

- `mtvec` resets to 0x00000000 (PM §3.2): unified-entry mode
  (MODE[1:0]=00) at base 0, and flash aliases to 0x00000000 (RM §1.2) —
  so out of reset the core executes the *instruction* at vector entry 0,
  which must be a jump. The WCH EVT startup emits `.option norvc; j handle_reset` there; a compressed `c.j` would occupy half a slot and
  shift every later entry off the number×4 grid (quirks.md §EXTI).
- `mtvec` (PM §2.2, §3.2): [31:2] base address — must be **1 KB-aligned**;
  [1] MODE1: 0 = entries hold jump instructions, 1 = entries hold
  absolute handler addresses; [0] MODE0: 0 = one unified entry for all
  traps, 1 = base + number×4 hardware vectoring. The WCH startup sets
  MODE[1:0]=11 (absolute-address vectoring), so a table at the flash
  origin means `mtvec = 0x08000003`.
- Exception codes and IRQ numbers share one vector index space (PM
  Table 2-1, RM §6.3 Table 6-1): 2 = NMI, 3 = HardFault, 12 = SysTick,
  14 = software interrupt, 16+ = peripherals; synchronous exceptions use
  codes 0/1/2/3/4–7/8/11 (misaligned/fetch-access/illegal/breakpoint/
  load/store misaligned/load/store access/ecall-U/ecall-M). Index 0 only
  ever receives exception code 0 (instruction address misaligned) — under
  address vectoring its slot still holds the reset `j`, so that one
  exception reads garbage; every other defined slot routes to a handler
  address.
- `mcause`[31] = interrupt flag, [30:0] = code (PM §2.1). `mstatus` MIE
  is bit 3 (global interrupt enable); MPIE saves it on trap entry, mret
  restores it (PM §2.2, §2.4, §7.2). `csrci mstatus, 8` masks everything
  maskable.
- `INTSYSCR` (CSR 0x804, PM §3.2): bit 0 HWSTKEN (hardware
  prologue/epilogue), bit 1 INESTEN (nesting), bit 2 EABIEN; all reset
  0\. HPE saves 10 caller-saved registers in a 48-byte stack frame,
  nesting depth 2 (PM §3.4) — requires `__attribute__((interrupt))` or
  WCH-Interrupt-fast codegen, so plain ISRs leave it off
  ([quirks.md](quirks.md) §EXTI).
- VTF: two channels bypass vector-table lookup entirely (PM §3.5).

Quirks: see [quirks.md](quirks.md) §Clock / RCC and §EXTI / interrupts.
