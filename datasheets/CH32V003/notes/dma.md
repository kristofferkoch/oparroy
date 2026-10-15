# CH32V003 DMA

Part of the CH32V003 notes — part identity, source documents, and citation
conventions in [facts.md](facts.md). Sources: RM ch.8; DS0 §1.4.9.

7 channels (DS0 §1.4.9 says "8 channels in total" — inconsistent with the
feature list and RM; RM Table 8-2 is authoritative at 7). Per channel:
PADDRx/MADDRx/CNTRx (≤65535 transfers)/CFGRx (PL[1:0] priority, DIR,
CIRC circular, PINC/MINC, PSIZE/MSIZE 8/16/32-bit, HTIE/TCIE/TEIE,
MEM2MEM). Flash, SRAM and peripherals as source/target. Interrupt status
DMA_INTFR, clear DMA_INTFCR; one IRQ per channel (RM §6.3 Table 6-1
lists them twice: PFIC vector numbers 22–28, priority numbers
8–14).

Peripheral mapping (RM §8.2.3 Table 8-2):

| Channel | Peripherals                      |
| ------- | -------------------------------- |
| 1       | ADC1, TIM2_CH3                   |
| 2       | SPI1_RX, TIM1_CH1, TIM2_UP       |
| 3       | SPI1_TX, TIM1_CH2                |
| 4       | USART1_TX, TIM1_CH4/TRIG/COM     |
| 5       | USART1_RX, TIM1_UP, **TIM2_CH1** |
| 6       | I2C1_TX, TIM1_CH3                |
| 7       | I2C1_RX, TIM2_CH2, TIM2_CH4      |

Ring RX capture: TIM2_CH1 DMA → channel 5, TIM2_CH2 → channel 7 — the
period/high capture pair (DESIGN.md §2). TX waveform generation can
stream compare values via TIM1_CHx/UP or TIM2 channels + circular buffer.

CNTRx counts the *remaining* transfers: writable only while the channel
is disabled (EN=0), decremented per transfer once running, and reloaded
to the programmed value in CIRC mode (RM §8.3.4) — so a channel's write
position in a circular buffer is `programmed − CNTRx` (mod the buffer
length), which is how the RX glue polls without interrupts. PADDRx /
MADDRx / CNTRx and the CFGRx direction/circular/increment fields are
writable only with the channel off (RM §8.2.1 configuration-process
note; §8.3.4–8.3.6 for the address/count registers).

Interrupt numbering: the vector table's DMA entries are PFIC numbers
22–28 for channels 1–7; the RM's Table 6-1 second column (headed
"Priority") lists 8–14 for the same lines — the vector index is what
firmware tables are indexed by (startup.cpp).

Quirks: see [quirks.md](quirks.md) §USART / I2C / SPI and §Timers.
