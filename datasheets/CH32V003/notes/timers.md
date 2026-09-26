# CH32V003 timers TIM1 / TIM2

Part of the CH32V003 notes — part identity, source documents, and citation
conventions in [facts.md](facts.md). Sources: RM ch.10, ch.11; DS0 §1.4.12,
§3.3.11.

Common: 16-bit counter CNT + 16-bit prescaler PSC (real divider = PSC+1,
updated on update event), auto-reload ATRLR (reset 0xFFFF), 4
capture/compare channels with 32-bit capture registers CHxCVR, DMA and
interrupt per channel, encoder mode, timer link (TIM2 ITR0 = TIM1; TIM1
ITR1 = TIM2, RM §11.3.8 Table 11-2). Timer clock = HCLK (48 MHz max);
timer resolution 20.8 ns at 48 MHz (DS0 §3.3.11 Table 3-20).

TIM2 (GPTM, base `0x40000000`, RM §11.4):

- Registers: CTLR1 0x00, CTLR2 0x04, SMCFGR 0x08, DMAINTENR 0x0C,
  INTFR 0x10, SWEVGR 0x14, CHCTLR1 0x18, CHCTLR2 0x1C, CCER 0x20,
  CNT 0x24, PSC 0x28, ATRLR 0x2C (0xFFFF), CH1CVR–CH4CVR
  0x34–0x40 (32-bit).
- Input capture path per channel x: pin → TIx → digital filter `ICxF[3:0]`
  (CHCTLRx) → edge detector → polarity `CCxP` (CCER) → mux `CCxS[1:0]`
  (01 = ICx on TIx, 10 = on the other channel, 11 = TRC) → prescaler
  `ICxPSC[1:0]` (capture every 1/2/4/8 events) → latch CNT into CHxCVR.
  Flags: CCxIF (INTFR), overcapture CCxOF.
- ICxF filter values (RM §11.4.7): 0000 = none (sampled at fDTS);
  0001–0011 = fCK_INT, N=2/4/8; 0100–0111 = fDTS/2 or /4, N=6/8;
  1000–1111 = fDTS/8, /16, /32, N=5/6/8. fDTS set by CKD[1:0] in CTLR1.
- DMA/IRQ enables in DMAINTENR: bit 0 UIE, 1 CC1IE … 4 CC4IE, 6 TIE;
  bit 8 UDE, 9 CC1DE … 12 CC4DE, 14 TDE.
- PWM-input mode (period + pulse on CH1/CH2 with SMS=100 reset mode)
  measures a two-edge waveform with zero ISR work (RM §11.3.4).
- RM §11 chapeau calls TIM2 16-bit; the CHxCVR registers are 32-bit wide
  (WCH convention; usable 16 bits).

TIM1 (ADTM, base `0x40012C00`, RM §10.4):

- Same register set plus RPTCR 0x30 (8-bit repetition counter), BDTR 0x44
  (break + dead-time), DMACFGR 0x48 / DMAADR 0x4C (burst DMA).
- 3 complementary PWM outputs with dead-time and BKIN brake input; CSS
  clock-failure event is hardwired to TIM1 brake (RM §3.3.6).
- Extra CTLR1 bits: `CAPLVL` (double-edge capture level indication — bit 16
  of CHxCVR reports the level) and `CAPOV` (capture value = 0xFFFF on
  overflow before capture). Useful for single-channel both-edge timing.
- `TIM1_IREMAP` (AFIO_PCFR1 bit 23) maps TIM1_CH1 to the internal LSI
  clock instead of a pin (for LSI calibration).
- TIM1 interrupts are split: TIM1BRK / TIM1UP / TIM1TRG / TIM1CC (IRQs
  34–37); TIM2 has one combined interrupt (IRQ 38).

Quirks: see [quirks.md](quirks.md) §Timers.
