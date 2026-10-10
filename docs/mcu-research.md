# MCU research

Input to DESIGN.md §5. Compiled by a research agent;
sources cited inline. FX: 1 USD ≈ 9.4 NOK, so the 3 NOK target ≈
**$0.32**. Prices are USD unit prices at the stated quantity, LCSC
unless noted.

## Silicon Labs 8051 family (the recalled part)

All EFM8 parts are pipelined 1T-style CIP-51 8051s (70% of instructions
in 1–2 cycles), with edge-capture PCA and free toolchains (SDCC works;
Silabs bundles a free full Keil PK51 license in Simplicity Studio).

| Part                             | Core clock | Analog comparators                                                                                                                               | Capture-relevant timers                                                      | Price                                                                                                                                                           |
| -------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| EFM8BB1 (EFM8BB10F8G-A-QFN20R)   | 25 MHz     | 2 (CMP0/CMP1), prog. hysteresis ±20 mV, 100–150 ns response typ in fastest mode; edge interrupts, output routable to pins, can hardware-kill PCA | 3-ch PCA (edge capture), 4× 16-bit timers, T2 external-pin capture           | $0.93 @1 → **$0.4524 @1500** ([LCSC C406735](https://www.lcsc.com/product-detail/C406735.html)) ≈ 4.3 NOK                                                       |
| EFM8BB2 (EFM8BB21F16G-C-QFN20R)  | 50 MHz     | 2, low-current, built-in DAC reference                                                                                                           | 5-ch PCA capture/compare, 4× 16-bit timers                                   | $1.27 @1 → **$0.708 @1500** ([LCSC C80713](https://www.lcsc.com/product-detail/C80713.html)) ≈ 6.7 NOK                                                          |
| EFM8BB51 (EFM8BB51F8G-C-TSSOP20) | 50 MHz     | 2                                                                                                                                                | PCA + timers (newer cost-reduced Busy Bee)                                   | **from $0.5673** ([LCSC C3242979](https://www.lcsc.com/product-detail/microcontrollers-mcu-mpu-soc_silicon-labs-efm8bb51f8g-c-tssop20_C3242979.html)) ≈ 5.4 NOK |
| EFM8BB3                          | 49–50 MHz  | 2                                                                                                                                                | 6-ch PCA, 6× 16-bit timers, **4 Configurable Logic Units** (PHY/bypass glue) | ~$1 class ([BB3 datasheet](https://www.silabs.com/documents/public/data-sheets/efm8bb3-datasheet.pdf)); LCSC price not checked                                  |
| EFM8LB1 (Laser Bee)              | **72 MHz** | 2 (same 100 ns-class IP), plus 2× DAC, 14-bit ADC                                                                                                | PCA + timers                                                                 | ~$1.5+ — over budget ([overview](https://jaycarlson.net/pf/silicon-labs-efm8/))                                                                                 |

Sources: [EFM8BB1 datasheet](https://www.silabs.com/documents/public/data-sheets/efm8bb1-datasheet.pdf),
[Busy Bee product page](https://www.silabs.com/mcu/8-bit-microcontrollers/efm8-busy-bee).

**On the recalled sub-3-NOK part:** no current distributor listing puts a
genuine Silabs 8051-with-comparator below ~$0.45 (≈4.3 NOK). The memory
most plausibly matches **EFM8BB1** (25 MHz, 2 comparators) at
launch-era/volume pricing (~$0.39 @10k, mid-2010s), or **EFM8BB2/BB51**
(50 MHz) if "surprisingly high frequency" is the anchor. *Flag:
unverifiable which exact part; gray-market pricing may dip below 3 NOK.*

## Other ultra-cheap MCUs

| Part                            | Core       | Clock  | Comparator                                                               | Capture/timers                                           | Toolchain                | Price                                                                                                                                                       |
| ------------------------------- | ---------- | ------ | ------------------------------------------------------------------------ | -------------------------------------------------------- | ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **CH32V003** (WCH)              | RV32EC     | 48 MHz | **1 op-amp/comparator** (OPA), routable to ADC and TIM2 CH1 capture      | TIM1/TIM2 capture, DMA                                   | GCC (riscv), ch32v003fun | ~$0.10–0.15 ≈ **1–1.4 NOK** ([WCH GH](https://github.com/openwch/ch32v003))                                                                                 |
| **STC8H1K08-36I-TSSOP20** (STC) | 1T 8051    | 36 MHz | **1** (P3.6/P3.7); response time poorly documented — *flag*              | 2× adv. 16-bit PWM timers w/ capture + CCP/PCA           | SDCC                     | **$0.1476 @5976** ([LCSC C915673](https://www.lcsc.com/product-detail/Microcontrollers-MCU-MPU-SOC_STC-Micro-STC8H1K08-36I-TSSOP20_C915673.html)) ≈ 1.4 NOK |
| STC8G1K08A-SOP8                 | 1T 8051    | 35 MHz | No in SOP8; 16/20-pin STC8G have CMP                                     | PCA/CCP, 16-bit timers                                   | SDCC                     | **from $0.1438** ([LCSC C915663](https://www.lcsc.com/product-detail/Microcontrollers-MCU-MPU-SOC_STC-Micro-STC8G1K08A-36I-SOP8_C915663.html))              |
| CH552G (WCH)                    | E8051      | 24 MHz | **No**                                                                   | T0/T1/T2 (T2 capture), USB, ADC                          | SDCC (ch55xduino)        | from $0.2868 ≈ 2.7 NOK ([LCSC C111292](https://www.lcsc.com/product-detail/WCH_WCH-Jiangsu-Qin-Heng-CH552G_C111292.html))                                   |
| PY32F002A (Puya)                | Cortex-M0+ | 24 MHz | **No** (*flag: one conflicting vendor page*); PY32F003/F030 have 1–2 CMP | TIM1 capture, TIM16, LPTIM, ADC                          | GCC                      | ~$0.08–0.11 ≈ 0.8–1 NOK                                                                                                                                     |
| Padauk PMS150C                  | FPPA 8-bit | 8 MHz  | 1                                                                        | single 8-bit timer — too weak for 800 kbit/s edge timing | SDCC (free-pdk)          | **$0.033** ≈ 0.3 NOK                                                                                                                                        |
| ATtiny202/402                   | AVR        | 20 MHz | 202/402: no; 212/412: 1 AC                                               | TCB capture, TCA                                         | avr-gcc                  | ~$0.43–0.56 @100 ≈ 4+ NOK — not competitive                                                                                                                 |

## RP2040

- **Price:** $1 single; **$0.80 @500-reel, $0.70 @3400-reel** via
  Raspberry Pi Direct
  ([announcement](https://www.raspberrypi.com/news/raspberry-pi-direct-buy-rp2040-in-bulk-from-just-0-70/))
  ≈ 6.6–9.4 NOK — **~2.2–3.1× the node budget**, plus external flash.
- **PIO as ring PHY:** 2 PIO blocks × 4 state machines @133 MHz,
  FIFO-to-DMA. A WS2812-class re-timing transceiver maps almost
  perfectly: one SM does RX (`wait pin` + instruction counting /
  oversampling to discriminate T0H≈0.4 µs vs T1H≈0.8 µs), a second SM
  does TX synthesizing a freshly-timed waveform — full per-node
  re-timing (no jitter accumulation), deterministic single-digit-µs
  latency, zero CPU in the bit path.
- **No analog comparator** (slow 500 ksps ADC only). Barely matters if
  nodes drive to logic levels (Schmitt GPIO replaces the comparator);
  matters for analog-threshold reception of degraded signals — then add
  a ~$0.07 external comparator or use the ADC for link diagnostics.

## Recommendations

- **Best sub-3-NOK pick: CH32V003** (~$0.10–0.15). 48 MHz, documented
  comparator routable to a timer capture channel, two capture-capable
  timers, DMA, free GCC. Cheapest *and* comparator-equipped. Runner-up
  for staying 8051/SDCC: **STC8H1K08** ($0.15 @3k) — verify comparator
  response time on the bench first.
- **Best flexibility pick: RP2040** ($0.70–1.00). PIO is the ideal PHY
  engine and the natural **supervisor / golden-reference node** for the
  test board (§6) — it can't be the per-node part at 3× budget.
- **Prototype first:** a CH32V003 node (comparator RX + timer capture)
  and an RP2040 node (PIO PHY) side by side; the RP2040 doubles as ring
  supervisor and bit-accurate reference transceiver for characterizing
  the CH32V003's analog-RX path. Feeds DESIGN.md §2 (line coding) and
  §4 (comparator-RX feasibility) with measurements.

**Unverified / flagged:** exact identity and historical price of the
recalled Silabs part; STC8H comparator response time; PY32F002A
comparator (conflicting sources); EFM8BB3/BB51 exact LCSC prices;
EFM8BB51 comparator specs (assumed same IP family as BB1); EFM8LB1
pricing; SDCC header support quality for EFM8.
