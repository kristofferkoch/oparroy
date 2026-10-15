# CH32V003 flash / SRAM / option bytes / ID

Part of the CH32V003 notes — part identity, source documents, and citation
conventions in [facts.md](facts.md). Sources: RM ch.15–16; DS0 §3.3.8.

- 16 KB main flash, 64 B pages (256 pages); standard mode: 2 B program /
  1 KB erase; fast mode (recommended): 64 B page program/erase, 1 KB or
  whole-chip erase. Endurance 10k cycles min (80k typ measured, not
  guaranteed); retention 10 y; page/16-bit/mass program+erase 2.4–3.1 ms;
  programming voltage 2.8–5.5 V (DS0 §3.3.8 Tables 3-14/3-15).

- HSI must be on during flash program/erase (RM §16.2.2).

- Flash registers at 0x40022000: ACTLR (LATENCY[1:0]), KEYR
  (KEY1=0x45670123, KEY2=0xCDEF89AB), OBKEYR, STATR (BSY, EOP,
  WRPRTERR, MODE, LOCK), CTLR, ADDR, OBR, WPR, MODEKEYR,
  BOOT_MODEKEYR.

- Option bytes at 0x1FFFF800–0x1FFFF80F (RM §16.5 Table 16-4), each byte
  stored with its inverse as a load-time checksum:

  | Offset | [7:0]                 | [15:8] | [23:16] | [31:24] |
  | ------ | --------------------- | ------ | ------- | ------- |
  | 0x00   | RDPR                  | nRDPR  | USER    | nUSER   |
  | 0x04   | Data0                 | nData0 | Data1   | nData1  |
  | 0x08   | WRPR0                 | nWRPR0 | WRPR1   | nWRPR1  |
  | 0x0C   | Reserved (whole word) |        |         |         |

  RDPR: 0xA5 = unprotected (nRDPR must be 0x5A). USER: START_MODE,
  RST_MODE[1:0] — 11 = NRST disabled, PD7 free as GPIO; STANDY_RST;
  IWDGSW. Data0/1: 2 bytes of user data, reset FFFFh (byte and inverse
  both 0xFF — the erased state fails the inverse checksum, so an
  unprogrammed Data0 reads as invalid, not as 0xFF). WRPR0/1: 1 KB
  sector write-protect, reset FFFFh (protection off). Read-protect
  disables SDI access to flash; unprotecting mass-erases (RM §16.5).

- The option bytes are reloaded into FLASH_OBR (0x4002201C) after every
  system reset (RM §16.5): DATA0 at [17:10], DATA1 at [25:18], USER bits
  at [9:2], RDPRT at [1], and **OBERR at [0] — set when a byte and its
  inverse do not match at load** (RM §16.3.7). The inverse check is
  therefore hardware-assisted: OBERR covers all four pairs at once; for a
  per-pair verdict read the byte/inverse pair directly from 0x1FFFF800.

- ESIG (RM ch.15, Table 15-1): flash size R16_ESIG_FLACAP at 0x1FFFF7E0;
  96-bit unique ID at 0x1FFFF7E8/0xEC/0xF0 (R32_ESIG_UNIID1/2/3) —
  usable as a per-node ring address seed. Read-only; accessible by
  8/16/32-bit reads (RM §15.1).

- SDK cross-check: ch32fun's `ch32v003hw.h` (WCH EVT-derived) models both
  blocks as memory-mapped structs — `OB_TypeDef` at OB_BASE 0x1FFFF800
  as six uint16 byte+inverse halves (RDPR, USER, Data0, Data1, WRPR0,
  WRPR1) and `ESIG_TypeDef` at 0x1FFFF7E0 as uint16 FLACAP + uint16/u32
  reserved + uint32 UNIID1/2/3 (UNIID1 at +0x08) — matching RM Tables
  16-4 and 15-1 field-for-field
  ([ch32v003hw.h](https://github.com/cnlohr/ch32fun/blob/master/ch32fun/ch32v003hw.h)
  OB/ESIG typedefs, OB_BASE/ESIG_BASE defines).

Quirks: see [quirks.md](quirks.md) §Flash & option bytes.
