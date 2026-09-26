# CH32V003 EXTI / PFIC (interrupts)

Part of the CH32V003 notes — part identity, source documents, and citation
conventions in [facts.md](facts.md). Sources: RM ch.6; DS0 §1.4.7–1.4.8.

- 10 EXTI lines: EXTI0–7 from GPIO (pin n of any port onto line n, one port
  at a time, selected by EXTIx[1:0] in `AFIO_EXTICR` — 00 PA, 10 PC, 11
  PD; 01 reserved), EXTI8 = PVD, EXTI9 = AWU. Rising/falling/both edges,
  per-line mask; min detectable pulse 10 ns (DS0 §3.3.9 Table 3-18).
- EXTI registers at 0x40010400: INTENR 0x00, EVENR 0x04, RTENR 0x08,
  FTENR 0x0C, SWIEVR 0x10, INTFR 0x14 (write 1 to clear).
- All 18 GPIOs can interrupt, but only 8 lines — at most one pin per bit
  number at a time.
- PFIC: 23 peripheral IRQs + 4 core, NMI and HardFault fixed, 2-level
  hardware interrupt stack (HPE, zero instruction overhead), 2 VTF
  (vector-table-free) fast interrupt channels, 2-level nesting, tail-chaining.
  Vector table at flash base; supports address or instruction mode.
- IRQ numbers (RM §6.3 Table 6-1): SysTick 12, SW 14, WWDG 16, PVD 17,
  FLASH 18, RCC 19, EXTI7_0 20, AWU 21, DMA1_CH1–7 = 22–28, ADC 29,
  I2C1_EV 30, I2C1_ER 31, USART1 32, SPI1 33, TIM1BRK 34, TIM1UP 35,
  TIM1TRG 36, TIM1CC 37, TIM2 38. (Table prints both index and vector
  address; vector address = 4×index.)

Quirks: see [quirks.md](quirks.md) §EXTI / interrupts.
