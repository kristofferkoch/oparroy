# CH32V003 ADC

Part of the CH32V003 notes — part identity, source documents, and citation
conventions in [facts.md](facts.md). Sources: RM ch.9; DS0 §3.3.14.

- 10-bit SAR, 8 external channels (AIN0–AIN7: PA2, PA1, PC4, PD2, PD3,
  PD5, PD6, PD4) + 2 internal: ADC_IN8 = VREFINT (1.2 V typ), ADC_IN9 =
  Vcal (calibration voltage, 2 steps).
- Clock: ADCCLK = HCLK/ADCPRE, max 24 MHz (needs VDD 4.5–5.5 V; 12 MHz
  at 3.2–5.5 V; 6 MHz at 2.8–5.5 V) (DS0 §3.3.14 Table 3-23). RM Fig 9-1
  prints "Max=4MHz or 6MHz" — superseded by DS0 numbers and RM §3.4.2
  ADCPRE note (max 24 MHz).
- Sample time per channel: SMPx[2:0] in ADC_SAMPTR1/2 = 3, 9, 15, 30,
  43, 57, 73, or 241 cycles. TCONV = Tsamp + 11 ADCCLK cycles. At 12 MHz
  and 3 cycles: ~1.17 µs per conversion; max rate 857 kSa/s (1710 kSa/s at
  24 MHz ADCCLK) (DS0 Table 3-23).
- Rule group: up to 16 conversions, sequence in ADC_RSQR1–3, data in
  ADC_RDATAR, DMA on rule group only (ADC_CTLR2 DMA bit). Injected
  group: up to 4, ADC_ISQR + ADC_IDATAR1–4 with signed offsets
  ADC_IOFRx.
- External triggers (ADC_CTLR2 EXTTRIG/JEXTTRIG + EXTSEL/JEXTSEL;
  rising edge only): rule — TIM1_TRGO, TIM1_CC1, TIM1_CC2, TIM2_TRGO,
  TIM2_CC1, TIM2_CC2, PD3/PC2 pin, SWSTART; injected — TIM1_CC3/4,
  TIM2_CC3/4, PD1/PA2 pin, JSWSTART (RM §9.2.3 Tables 9-3/9-4).
  Trigger-delay block: ADC_DLYR delays an external trigger by a programmed
  count (RM §9).
- Analog watchdog: 10-bit high/low thresholds ADC_WDHTR (reset 0x3FF) /
  ADC_WDLTR; AWD flag in ADC_STATR; can reset the chip when enabled as
  watchdog reset (RM §3.2.2).
- Calibration: after ADON=1 power-up (wait tSTAB ≥ 7 µs), set RSTCAL, wait
  clear, set CAL, wait clear; code lands in ADC_RDATAR. Recommended at
  each power-up (RM §9.2.2).
- Registers at 0x40012400: STATR 0x00, CTLR1 0x04 (reset 0x02000000),
  CTLR2 0x08 (ADON, DMA, ALIGN, EXTSEL[2:0], EXTTRIG, SWSTART,
  RSTCAL, CAL), SAMPTR1 0x0C, SAMPTR2 0x10, IOFR1–4, WDHTR, WDLTR,
  RSQR1–3, ISQR, IDATAR1–4, RDATAR 0x4C, DLYR 0x50.
- Source impedance: keep RAIN < 10 kΩ at fADC=12 MHz (Table 3-24; 8.5 kΩ
  at 3-cycle sampling). A potentiometer ≤10 kΩ is fine.

Quirks: see [quirks.md](quirks.md) §ADC.
