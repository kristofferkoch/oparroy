# CH32V003 USART / I2C / SPI

Part of the CH32V003 notes — part identity, source documents, and citation
conventions in [facts.md](facts.md). Sources: RM ch.12–14; DS0
§3.3.12–3.3.13.

USART1 (0x40013800): full/half-duplex, synchronous mode with CK,
**single-wire half-duplex mode** (HDSEL in CTLR3; TX and RX internally
connected, TX pin open-drain — relevant to single-wire debug/console),
LIN, smartcard, IrDA, CTS/RTS, fractional baud rate BRR = HCLK/(16×
USARTDIV), USARTDIV = DIV_M + DIV_F/16, max 3 Mbps (RM §12.1–12.5).
Registers: STATR, DATAR, BRR, CTLR1–3, GPR. Internal SW_RX pin shown in
remap table. Receiver tolerance ≥3 % total baud error (RM §12.3) — HSI
±2.2 % is within budget for node-internal links but tight against an
external 2 %-class partner.

I2C1 (0x40005400): master/slave, multi-master, 7/10-bit addr, dual slave
address, 100/400 kHz (peripheral clock ≥2 MHz standard / ≥4 MHz fast),
SMBus, PEC CRC, DMA, 2 IRQs (EV/ER) (RM §13.1–13.2).

SPI1 (0x40013000): master/slave, full/half-duplex single-wire, 8/16-bit
frames, MSB/LSB first, hardware CRC, NSS hard/soft, max SCK = HCLK/2
(24 MHz at 48 MHz), DMA (RM §14.1; DS0 §3.3.13 Table 3-22).

Quirks: see [quirks.md](quirks.md) §USART / I2C / SPI.
