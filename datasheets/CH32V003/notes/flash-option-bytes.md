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
- Option bytes at 0x1FFFF800: RDPR (0xA5 = unprotected), USER
  (START_MODE, RST_MODE[1:0] — 11 = NRST disabled, PD7 free as GPIO;
  STANDY_RST; IWDGSW), Data0/1, WRPR0/1 (1 KB sector write-protect).
  Each byte stored with inverse. Read-protect disables SDI access to flash;
  unprotecting mass-erases (RM §16.5).
- ESIG (RM ch.15): flash size R16_ESIG_FLACAP at 0x1FFFF7E0; 96-bit
  unique ID at 0x1FFFF7E8/0xEC/0xF0 (R32_ESIG_UNIID1/2/3) — usable as a
  per-node ring address seed.

Quirks: see [quirks.md](quirks.md) §Flash & option bytes.
