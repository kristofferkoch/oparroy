# CH32V003 clock tree / RCC

Part of the CH32V003 notes — part identity, source documents, and citation
conventions in [facts.md](facts.md). Sources: RM ch.3; DS0 §1.3,
§3.3.5–3.3.7.

- HSI: internal 24 MHz RC, factory-calibrated (HSICAL[7:0], RCC_CTLR),
  user trim HSITRIM[4:0] (~60 kHz/step, default 16 → 24 MHz ±1%).
  Accuracy ±1.6/-1.2 % (0–70 °C), ±2.2 % (-40–85 °C) (DS0 §3.3.6 Table
  3-11). HSI must be on for SDI debug and for flash program/erase.
- HSE: external 4–25 MHz crystal on OSC_IN/PA1, OSC_OUT/PA2, or bypass
  feed on OSC_IN (HSEBYP with HSEON=0, then HSEON=1). PA1/PA2 become
  oscillator pins when `PA1PA2_RM` (AFIO_PCFR1 bit 15) = 1.
- PLL: fixed ×2 only. Source select `PLLSRC` (RCC_CFGR0 bit 16): 0 = HSI,
  1 = HSE. 24 MHz HSI ×2 = 48 MHz SYSCLK — the project's clock plan.
- LSI: ~128 kHz RC (100–150 kHz) for IWDG/AWU. No LSE on the silicon —
  though the DS0 §1.3 prose lists "external low-frequency oscillator (LSE)"
  among the clock sources (copy-paste from bigger WCH parts; no LSE in the
  clock tree, registers, or pinout — [quirks.md](quirks.md)).
- `RCC_CTLR` (0x40021000, reset 0x0000xx83, RM §3.4.1): bit 0 HSION,
  bit 1 HSIRDY, bits [7:3] HSITRIM, [15:8] HSICAL, bit 16 HSEON, 17
  HSERDY, 18 HSEBYP, 19 CSSON, bit 24 PLLON, bit 25 PLLRDY.
- `RCC_CFGR0` (0x40021004, reset 0x00000020):
  - `SW[1:0]`/`SWS[1:0]`: 00 HSI, 01 HSE, 10 PLL.
  - `HPRE[3:0]`: AHB prescaler /1…/256; **reset value 0010b = SYSCLK/3
    → HCLK = 8 MHz out of reset**.
  - `ADCPRE[4:0]`: HCLK /2…/128 to ADCCLK (max 24 MHz).
  - `MCO[2:0]`: clock out on PC4 (0xx off; 100 SYSCLK, 101 HSI, 110 HSE,
    111 PLL).
- SysTick clock = HCLK or HCLK/8 (STK_CTLR).
- Clock security system: CSSON (RCC_CTLR bit 19); on HSE failure switches
  to HSI, raises CSSF → NMI, and brakes TIM1 (RM §3.3.6).
- Clock gating: `RCC_AHBPCENR` (0x14, bit 0 DMA1EN, bit 2 SRAMEN reset
  1), `RCC_APB2PCENR` (0x18: bit 0 AFIOEN, 2 IOPAEN, 4 IOPCEN, 5
  IOPDEN, 9 ADC1EN, 11 TIM1EN, 12 SPI1EN, 14 USART1EN),
  `RCC_APB1PCENR` (0x1C: bit 0 TIM2EN, 11 WWDGEN, 21 I2C1EN, 28
  PWREN). Mirror-image reset registers RCC_APB2PRSTR / RCC_APB1PRSTR.
- Reset flags in `RCC_RSTSCKR` (0x24): LPWRRSTF, WWDGRSTF, IWDGRSTF,
  SFTRSTF, PORRSTF, PINRSTF; RMVF clears. LSION/LSIRDY live here too.
- Software reset: RSTSYS in PFIC_CFGR or SYSRST in PFIC_SCTLR (RM §3.2.2).
- Flash wait states: FLASH_ACTLR LATENCY = 0 for ≤24 MHz, 1 for ≤48 MHz
  (RM §16.3.1).
- 48 MHz bring-up sequence (HSI×2 PLL), cross-checked against the WCH
  EVT/ch32fun init (which matches the RM exactly — no quirk):
  FLASH_ACTLR.LATENCY=1 *before* the faster clock; RCC_CFGR0 = 0
  (HPRE=/1, PLLSRC=HSI, both zero encodings); RCC_CTLR |= PLLON; poll
  PLLRDY; RCC_CFGR0 SW=10b; poll SWS[1:0] (bits [3:2]) == 10b to confirm
  the switch took.

Quirks: see [quirks.md](quirks.md) §Clock / RCC.
