# CH32V003 GPIO / AFIO — TSSOP-20 pinout

Part of the CH32V003 notes — part identity, source documents, and citation
conventions in [facts.md](facts.md). Sources: DS0 §2.1–2.3; RM ch.7.

Registers per port (x=A/C/D): GPIOx_CFGLR (0x00, reset 0x44444444 —
floating input), INDR 0x08, OUTDR 0x0C (also selects pull-up vs pull-down
in input mode), BSHR 0x10, BCR 0x14, LCKR 0x18 (lock sequence write 1, 0,
1, read, read on LCKK bit 16). 4 bits/pin: MODEy[1:0] (00 input, 01 10 MHz,
10 2 MHz, 11 30 MHz max) + CNFy[1:0] (input: 00 analog, 01 floating, 10
pulled; output: 00 PP, 01 OD, 10 AF-PP, 11 AF-OD).

F4P6 pin map (DS0 §2.1; A# = ADC channel, T#/U# abbreviated per DS0 note):

| Pin | Name | Default alternates                           | Remap options                                                              |
| --- | ---- | -------------------------------------------- | -------------------------------------------------------------------------- |
| 1   | PD4  | ADC_IN7, USART_CK, TIM2_CH1/ETR, **OPA_OUT** | TIM1_ETR_2, TIM1_CH4_3                                                     |
| 2   | PD5  | ADC_IN5, USART_TX                            | TIM2_CH4_3, USART_RX_2                                                     |
| 3   | PD6  | ADC_IN6, USART_RX                            | TIM2_CH3_3, USART_TX_2                                                     |
| 4   | PD7  | **NRST**, TIM2_CH4, **OPA_P1**               | USART_CK_1/2, TIM2_CH4_2                                                   |
| 5   | PA1  | OSC_IN, ADC_IN1, TIM1_CH2, **OPA_N0**        | TIM1_CH2_2                                                                 |
| 6   | PA2  | OSC_OUT, ADC_IN0, TIM1_CH2N, **OPA_P0**      | ADC_ETR2_1, TIM1_CH2N_2                                                    |
| 7   | VSS  |                                              |                                                                            |
| 8   | PD0  | TIM1_CH1N, **OPA_N1**                        | I2C_SDA_1, USART_TX_1, TIM1_CH1N_2                                         |
| 9   | VDD  |                                              |                                                                            |
| 10  | PC0  | TIM2_CH3                                     | SPI_NSS_1, USART_TX_3, TIM2_CH3_2, TIM1_CH3_1                              |
| 11  | PC1  | I2C_SDA, SPI_NSS (FT)                        | TIM1_BKIN_1, TIM2_CH4_1, TIM2_CH1/ETR_2/3, TIM1_BKIN_3, USART_RX_3         |
| 12  | PC2  | I2C_SCL, USART_RTS, TIM1_BKIN (FT)           | ADC_ETR_1, TIM2_CH2_1, TIM1_ETR_3, USART_RTS_1, TIM1_BKIN_2                |
| 13  | PC3  | TIM1_CH3                                     | TIM1_CH1N_1, USART_CTS_1, TIM1_CH3_2, TIM1_CH1N_3                          |
| 14  | PC4  | ADC_IN2, TIM1_CH4, **MCO**                   | TIM1_CH2N_1, TIM1_CH4_2, TIM1_CH1_3                                        |
| 15  | PC5  | SPI_SCK, TIM1_ETR (FT)                       | TIM2_CH1/ETR_1, I2C_SCL_2/3, USART_CK_3, TIM1_ETR_1, TIM1_CH3_3, SPI_SCK_1 |
| 16  | PC6  | SPI_MOSI (FT)                                | TIM1_CH1_1, USART_CTS_2/3, I2C_SDA_2/3, TIM1_CH3N_3, SPI_MOSI_1            |
| 17  | PC7  | SPI_MISO                                     | TIM1_CH2_1, TIM2_CH2_3, USART_RTS_2/3, TIM1_CH2_3, SPI_MISO_1              |
| 18  | PD1  | **SWIO**, TIM1_CH3N, ADC_ETR2                | I2C_SCL_1, USART_RX_1, TIM1_CH3N_1/2                                       |
| 19  | PD2  | TIM1_CH1, ADC_IN3                            | TIM2_CH3_1, TIM1_CH2N_3, TIM1_CH1_2                                        |
| 20  | PD3  | ADC_IN4, TIM2_CH2, ADC_ETR, USART_CTS        | TIM2_CH2_2, TIM1_CH4_1                                                     |

Remap control: `AFIO_PCFR1` (0x40010004, reset 0) — TIM2_RM[1:0] bits
9:8, TIM1_RM[1:0] bits 7:6, USART1_RM {21,2}, I2C1_RM {22,1}, SPI1_RM
bit 0, SWCFG[2:0] bits 26:24, PA1PA2_RM bit 15, TIM1_IREMAP bit 23,
ADC_ETRGREG_RM bit 18, ADC_ETRGINJ_RM bit 17. `_N` suffixes in the
table = remap-field value in binary. TIM2 remap table (RM §7.2.11.1 Table
7-9): TIM2_RM=00 → CH1/ETR PD4, CH2 PD3, CH3 PC0, CH4 PD7; 01 →
CH1/ETR PC5, CH2 PC2, CH3 PD2, CH4 PC1; 10 → CH1/ETR PC1, CH2 PD3,
CH3 PC0, CH4 PD7; 11 → CH1/ETR PC1, CH2 PC7, CH3 PD6, CH4 PD5.

**Note for ring RX:** the OPA→TIM2_CH1 route is internal (OPA output
straight into the capture channel), so CH1 does not need a pin for RX. The
pin muxes above only matter if the signal also goes to a pin.

Quirks: see [quirks.md](quirks.md) §GPIO & alternate functions.
