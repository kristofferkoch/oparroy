# CH32V003 extracted facts — oparroy node MCU

Part: **CH32V003F4P6** (TSSOP-20, 0.65 mm pitch, 4.4×6.5 mm body). QingKe
V2A RV32EC core, machine mode, 2-stage pipeline, custom extended
instructions. 16 KB CodeFlash, 2 KB SRAM, 48 MHz max.

This file is the index and overview; per-peripheral detail lives in the
files listed below. Tribal-knowledge errata: [quirks.md](quirks.md).

Sources (canonical PDFs live in `datasheets/CH32V003/`):

- `CH32V003DS0-datasheet-v1.8.pdf` — cited as (DS0 §x.y); fetched
  2026-09-26 from wch-ic.com. Note: interior footers still print V1.4/V1.7;
  cover is V1.8.
- `CH32V003RM-reference-manual-v1.9.pdf` — cited as (RM §x.y); fetched
  2026-09-26 from wch-ic.com.
- Core-level CSRs (PFIC, SysTick, debug) live in the separate
  QingKeV2_Processor_Manual, not in the RM (RM overview).

All registers are accessed as 32-bit words unless noted; WCH header names
(`R32_...`, `R16_...`) are quoted from the RM tables.

## Per-peripheral files

- [opa.md](opa.md) — OPA comparator, the ring RX front-end
- [timers.md](timers.md) — TIM1/TIM2, input capture, PWM, timer link
- [rcc-clocks.md](rcc-clocks.md) — clock tree, RCC, gating, reset flags
- [gpio-pinout.md](gpio-pinout.md) — GPIO/AFIO registers, TSSOP-20 pin
  map, remaps
- [adc.md](adc.md) — 10-bit ADC, triggers, calibration
- [dma.md](dma.md) — DMA channels and peripheral mapping
- [exti-pfic.md](exti-pfic.md) — EXTI lines, PFIC, IRQ numbers
- [usart-i2c-spi.md](usart-i2c-spi.md) — USART1, I2C1, SPI1
- [flash-option-bytes.md](flash-option-bytes.md) — flash, option bytes,
  ESIG/unique ID
- [power-reset.md](power-reset.md) — power modes, POR/PVD, watchdogs
- [sdi-debug.md](sdi-debug.md) — single-wire debug on PD1

## Memory map (RM §1.2, DS0 §1.2)

- CodeFlash 16 KB at `0x08000000`–`0x08003FFF`; aliased at `0x00000000`
  per boot config.
- SRAM 2 KB at `0x20000000`.
- System flash (1920 B factory bootloader) at `0x1FFFF000`.
- Option bytes `0x1FFFF800`, vendor bytes `0x1FFFF7C0`.
- Peripheral bases: TIM2 `0x40000000`, WWDG `0x40002C00`, IWDG
  `0x40003000`, I2C1 `0x40005400`, PWR `0x40007000`, AFIO `0x40010000`,
  EXTI `0x40010400`, GPIOA `0x40010800`, GPIOC `0x40011000`, GPIOD
  `0x40011400`, ADC `0x40012400`, TIM1 `0x40012C00`, SPI1 `0x40013000`,
  USART1 `0x40013800`, DMA1 `0x40020000`, RCC `0x40021000`, Flash
  interface `0x40022000`, EXTEND `0x40023800`. Core private peripherals at
  `0xE0000000`+.

## Electrical quick table (DS0 ch.3)

| Parameter | Value | Source |
|---|---|---|
| Operating VDD | 2.7–5.5 V (2.8 min with ADC) | DS0 §3.3.1 T3-2 |
| Abs-max VDD | −0.3…5.5 V | DS0 §3.2 T3-1 |
| Input voltage, FT pins (PC1/PC2/PC5/PC6) | VSS−0.3…5.5 V | DS0 §3.2 T3-1 |
| Input voltage, other pins | VSS−0.3…VDD+0.3 V | DS0 §3.2 T3-1 |
| VIH (std & FT inputs) | ≥ 0.22×(VDD−2.7)+1.55 V | DS0 §3.3.9 T3-16 |
| VIL | ≤ 0.19×(VDD−2.7)+0.65 V | DS0 §3.3.9 T3-16 |
| Schmitt hysteresis | 150 mV typ (all inputs + NRST) | DS0 §3.3.9/3.3.10 |
| Weak pull-up/down | 35–55 kΩ (45 typ) | DS0 §3.3.9 T3-16 |
| GPIO drive | ±8 mA spec'd (VOL≤0.4 V/VOH≥VDD−0.4), ±20 mA degraded; ΣIVDD 100 mA, ΣIVSS 80 mA | DS0 §3.3.9 T3-17, §3.2 |
| Output speed grades | 2 / 10 / 30 MHz (MODE 10/01/11) | DS0 §3.3.9 T3-18 |
| EXTI min pulse | 10 ns | DS0 §3.3.9 T3-18 |
| ADC input range | VSS–VDD | DS0 §3.3.14 T3-23 |
| OPA common-mode input | 0–VDD; offset ±3/±13 mV | DS0 §3.3.15 T3-26 |
| ESD (HBM) | 4 kV | DS0 §3.2 T3-1 |
| Injection current per pin | ±4 mA (Σ ±20 mA) | DS0 §3.2 T3-1 |
| Run current 48 MHz HSI, 3.3 V | 4.0 mA (periphs off) / 6.4 mA (all on) | DS0 §3.3.4 T3-6-1 |
| Sleep 48 MHz HSI, 3.3 V | 1.7 / 4.1 mA | DS0 §3.3.4 T3-7-1 |
| Standby, 3.3 V | 7.6 µA (LSI off) / 9.1 µA (LSI on) | DS0 §3.3.4 T3-8 |
| HSI accuracy | ±1.6/−1.2 % (0–70 °C); ±2.2 % (−40–85 °C) | DS0 §3.3.6 T3-11 |
| VREFINT | 1.2 V typ (1.17–1.23) | DS0 §3.3.3 T3-5 |
| POR/PDR threshold | 2.5 V typ rise / 2.48 V fall | DS0 §3.3.2 T3-4 |
| Ambient temp | −40…85 °C (suffix 6) | DS0 §3.2 T3-1 |

## Not in these notes

Full bit-level register tables (every field of TIMx, ADC, USART, I2C, SPI,
DMA, FLASH_CTLR), the IWDG/WWDG register sets, DMA CFGR field encodings,
and the PFIC/SysTick core CSRs (in the QingKeV2_Processor_Manual) are not
inlined — consult `datasheets/CH32V003/CH32V003RM-reference-manual-v1.9.pdf`
chapters 4–16 for those, and the QingKe processor manual for core CSRs.
