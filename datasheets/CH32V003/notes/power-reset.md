# CH32V003 power / reset

Part of the CH32V003 notes — part identity, source documents, and citation
conventions in [facts.md](facts.md). Sources: RM ch.2; DS0 §1.4.3–1.4.6,
§3.3.2–3.3.4.

- VDD 2.7–5.5 V operating (2.8 V min recommended with ADC) (DS0 §3.3.1
  Table 3-2). No separate VDDA pin on TSSOP-20.
- POR/PDR always on: VPOR/PDR 2.5 V typ rising / 2.48 V falling (DS0 §3.3.2
  Table 3-4). POR delay 1.5 ms typ (option-byte RST_MODE extends).
- PVD: PWR_CTLR PLS[2:0] picks 2.85…4.4 V rising thresholds (~0.18 V
  hysteresis), PVDE enables, PVD0 status in PWR_CSR, interrupt via EXTI
  line 8.
- Sleep: core clock off, peripherals run; ~1.7 mA at 48 MHz HSI with
  peripherals off, VDD=3.3 V; wake ~30 µs, any interrupt.
- Standby (SLEEPDEEP=1, PDDS=1, WFI/WFE): HSI/HSE/PLL off, SRAM and
  registers retained, I/O state held; ~7.6 µA (LSI off) / 9.1 µA (LSI on) at
  3.3 V (DS0 §3.3.4 Table 3-8); wake ~200 µs via EXTI/NRST/IWDG/AWU;
  restarts on HSI.
- AWU: LSI-clocked periodic self-wake from Standby (PWR_AWUCSR,
  AWUWR, AWUPSC), EXTI line 9.
- Watchdogs: IWDG — 12-bit down counter on LSI, 7 prescalers, runs in
  Standby, option-byte hardware start (IWDGSW). WWDG — 7-bit counter,
  HCLK/4096 domain, early-wake interrupt. Both freezable in debug
  (DBGMCU_CR).
- Reset sources flagged in RCC_RSTSCKR (see [rcc-clocks.md](rcc-clocks.md)).

Quirks: see [quirks.md](quirks.md) §Power / reset.
