# CH32V003 SDI debug (PD1)

Part of the CH32V003 notes — part identity, source documents, and citation
conventions in [facts.md](facts.md). Sources: DS0 §1.4.18; RM §7.3.2.1,
ch.18.

- Single-wire debug on **PD1 (SWIO)**, enabled out of reset. HSI must be
  running for SDI (DS0 §1.4.18).
- AFIO_PCFR1 SWCFG[2:0]: 0xx = SDI enabled; 100 = SDI off, PD1 becomes
  GPIO — note this is self-locking against the debugger until next reset.
- Pin conflicts: PD1 defaults carry TIM1_CH3N / ADC_ETR2; remaps carry
  I2C_SCL_1 and USART_RX_1. Keep those functions off PD1 while debugging.
- DBGMCU_CR (CSR address 0x7C0): TIM1_STOP/TIM2_STOP/WWDG_STOP/
  IWDG_STOP freeze counters in debug halt; SLEEP/STANDBY bits keep
  clocks up in low-power debug.

Quirks (brick/unbrick, programmer traps): see [quirks.md](quirks.md)
§Debug / SDI & recovery and §Toolchain / programmer pitfalls.
