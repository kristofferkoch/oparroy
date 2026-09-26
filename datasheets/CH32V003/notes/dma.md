# CH32V003 DMA

Part of the CH32V003 notes — part identity, source documents, and citation
conventions in [facts.md](facts.md). Sources: RM ch.8; DS0 §1.4.9.

7 channels (DS0 §1.4.9 says "8 channels in total" — inconsistent with the
feature list and RM; RM Table 8-2 is authoritative at 7). Per channel:
PADDRx/MADDRx/CNTRx (≤65535 transfers)/CFGRx (PL[1:0] priority, DIR,
CIRC circular, PINC/MINC, PSIZE/MSIZE 8/16/32-bit, HTIE/TCIE/TEIE,
MEM2MEM). Flash, SRAM and peripherals as source/target. Interrupt status
DMA_INTFR, clear DMA_INTFCR; one IRQ per channel (IRQ 8–14).

Peripheral mapping (RM §8.2.3 Table 8-2):

| Channel | Peripherals |
|---------|-------------|
| 1 | ADC1, TIM2_CH3 |
| 2 | SPI1_RX, TIM1_CH1, TIM2_UP |
| 3 | SPI1_TX, TIM1_CH2 |
| 4 | USART1_TX, TIM1_CH4/TRIG/COM |
| 5 | USART1_RX, TIM1_UP, **TIM2_CH1** |
| 6 | I2C1_TX, TIM1_CH3 |
| 7 | I2C1_RX, TIM2_CH2, TIM2_CH4 |

Ring RX capture: TIM2_CH1 DMA → channel 5; TX waveform generation can
stream compare values via TIM1_CHx/UP or TIM2 channels + circular buffer.

Quirks: see [quirks.md](quirks.md) §USART / I2C / SPI and §Timers.
