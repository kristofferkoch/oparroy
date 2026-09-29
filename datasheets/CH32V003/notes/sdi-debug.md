# CH32V003 SDI debug (PD1)

Part of the CH32V003 notes — part identity, source documents, and citation
conventions in [facts.md](facts.md). Sources: DS0 §1.4.18; RM §7.3.2.1,
ch.18; QDM (QingKeV2 debug manual v1.0, vendored 2026-09-29 from
openwch/ch32v003).

- Single-wire debug on **PD1 (SWIO)**, enabled out of reset. HSI must be
  running for SDI (DS0 §1.4.18).
- AFIO_PCFR1 SWCFG\[2:0\]: 0xx = SDI enabled; 100 = SDI off, PD1 becomes
  GPIO — note this is self-locking against the debugger until next reset.
- Pin conflicts: PD1 defaults carry TIM1_CH3N / ADC_ETR2; remaps carry
  I2C_SCL_1 and USART_RX_1. Keep those functions off PD1 while debugging.
- DBGMCU_CR (CSR address 0x7C0): TIM1_STOP/TIM2_STOP/WWDG_STOP/
  IWDG_STOP freeze counters in debug halt; SLEEP/STANDBY bits keep
  clocks up in low-power debug.

Quirks (brick/unbrick, programmer traps): see [quirks.md](quirks.md)
§Debug / SDI & recovery and §Toolchain / programmer pitfalls.

## Wire protocol (QDM ch.2)

Half-duplex on the single SWIO line, idle high, open-drain style: bits
are pulse-width encoded in the low phase. T is the target debug-interface
clock period (T = 125 ns per PicoRVD, which clocks the interface at
HSI/3 = 8 MHz — QDM defines T abstractly, no fixed rate).

- Normal mode 2x (default out of reset): data 1 = low (T,4T) then high
  (T,16T); data 0 = low (6T,64T) then high (T,16T); stop = high ≥ 18T
  (QDM §2.2).
- Fast mode 1x: data 1 = low (T,2T); data 0 = low (4T,32T); stop = high
  ≥ 10T (QDM §2.2). PicoRVD reports normal mode is what actually works;
  stop < 2250 ns fails (PicoRVD `singlewire.pio` comments, unverified by
  us on the bench).
- Reset the interface by holding SWIO low for an extended time (QDM §2.2
  "a certain time"; PicoRVD uses ~8 µs and notes 256T = 32 µs).
- New Packet: start bit 1, 7-bit register address MSB-first, R/W bit
  (1 = host write, 0 = host read), 32-bit data MSB-first, optional even
  parity bit — omit parity by sending the stop character right after the
  last data bit (QDM §2.1). Programmers in the wild skip parity.
- Bypass Packet: start bit 0 + 32-bit data, reusing the previous New
  Packet's address and direction — the fast path for repeated access to
  one register (QDM §2.1).

Interface config registers (7-bit addresses, QDM §2.3): CPBR 0x7C
(read-only capability), CFGR 0x7D, SHDWCFGR 0x7E. Writes need KEY =
0x5AA5 in bits [31:16]; to change config, write SHDWCFGR first, then
CFGR to commit (QDM §2.4 — e.g. 0x5AA50400 to both enables slave
output). Current silicon: IO_FREE mode only, even parity only (no
CRC8), stop-factor 8x only.

## Debug module behind the wire (QDM ch.3)

The transport carries register read/writes to a debug module that
follows RISC-V External Debug Support v0.13.2: dmcontrol 0x10, dmstatus
0x11, hartinfo 0x12, abstractcs 0x16, command 0x17, abstractauto 0x18,
progbuf0-7 0x20-0x27, haltsum0 0x40 (QDM §3.1). Halt/resume/reset via
dmcontrol; GPR/CSR/memory access via abstract commands or the 8-word
program buffer (a short progbuf must end in `ebreak`/`c.ebreak`).
Flash programming runs through this same module (64-byte fast pages,
RM §18 / [flash-option-bytes.md](flash-option-bytes.md)).
