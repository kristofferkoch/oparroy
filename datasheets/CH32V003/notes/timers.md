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
  Flags: CCxIF (INTFR), overcapture CCxOF — write-0-clear
  (RM §11.4.5).
- ICxF filter values (RM §11.4.7): 0000 = none (sampled at fDTS);
  0001–0011 = fCK_INT, N=2/4/8; 0100–0111 = fDTS/2 or /4, N=6/8;
  1000–1111 = fDTS/8, /16, /32, N=5/6/8. fDTS set by CKD[1:0] in CTLR1.
- DMA/IRQ enables in DMAINTENR: bit 0 UIE, 1 CC1IE … 4 CC4IE, 6 TIE;
  bit 8 UDE, 9 CC1DE … 12 CC4DE, 14 TDE.
- PWM-input mode (RM §11.3.4) measures period + high time of a
  two-edge waveform with zero ISR work. Verified recipe, cross-checked
  against the SDK's `TIM_PWMIConfig` (EVT/EXAM/TIM/Input_Capture):
  CC1S=01 (IC1 on TI1), CC1P=0 (rising), CC2S=10 (IC2 on TI1),
  CC2P=1 (falling), TS=101 (TI1FP1 as slave trigger), SMS=100 (CNT
  reset on trigger), CC1E+CC2E — CH1CVR then reads the period, CH2CVR
  the high time. Only TI1FP1/TI2FP2 reach the slave-mode controller,
  so the channel pair is always CH1+CH2, and both channels are inputs:
  no CH2 output (and no CNT-based PWM) can coexist with PWM-input
  capture on the same timer.
- Output/PWM mode (RM §11.4.1, §11.4.7–11.4.9): `CTLR1` bit 0 CEN
  (counter enable); `CHCTLR1` covers channels 1–2, `CHCTLR2` channels
  3–4 — per channel CCxS[1:0] (00 = output), OCxM[2:0] (110 = PWM mode
  1: active while CNT < CVR, 111 = PWM mode 2), OCxPE preload, OCxFE;
  channel 2's fields sit at [15:8] of CHCTLR1 (OC2M at [14:12]).
  `CCER`: per channel CCxE output enable at bit 4(x−1), CCxP polarity
  (0 = active high) one bit higher. Square wave on CHx: PSC, ATRLR,
  CHxCVR, CHCTLRx OCxM=110, CCER CCxE=1, CTLR1 CEN=1 — no interrupt
  needed.
- RM §11 chapeau calls TIM2 16-bit; the CHxCVR registers are 32-bit wide
  (WCH convention; usable 16 bits).
- **Keep-alive strobe is software-generated** — the firmware toggles
  PD3 as a plain GPIO. The earlier plan (TIM2_CH2 hardware PWM default-
  mapped to PD3, TIM2_RM=00) died with the RX capture design: PWM-input
  capture takes both CH1 and CH2 as inputs and puts CNT under slave-mode
  reset (see the PWM-input bullet), leaving no timer resource for an
  independent PWM. A hardware strobe would also have kept the §4 charge
  pump fed through a firmware hang, and a hung MCU is a bypass case
  (DESIGN.md §3).

TIM1 (ADTM, base `0x40012C00`, RM §10.4):

- Same register set plus RPTCR 0x30 (8-bit repetition counter), BDTR 0x44
  (break + dead-time), DMACFGR 0x48 / DMAADR 0x4C (burst DMA).
- 3 complementary PWM outputs with dead-time and BKIN brake input; CSS
  clock-failure event is hardwired to TIM1 brake (RM §3.3.6).
- Output-compare/PWM path per channel (RM §10.4.7–10.4.9): `CHCTLR1`
  covers channels 1–2, `CHCTLR2` channels 3–4; odd channels sit at
  [7:0], even at [15:8]. Per channel in output mode: CCxS[1:0]=00
  (writable only while CCxE=0); OCxM[2:0] (000 freeze, 001/010 set
  active/inactive on match, 011 toggle on match, 100/101 force
  inactive/active, 110 = PWM mode 1 — OCxREF active while CNT < CHxCVR
  up-counting, active while CNT > CHxCVR down-counting, 111 = PWM mode
  2 inverted); OCxPE preload (1: writes hit the preload register and
  latch into the shadow register at the update event; 0: CHxCVR takes
  effect immediately — the RM rates PWM without preload as determined
  only in one-pulse mode, see [quirks.md](quirks.md) §Timers); OCxFE
  fast enable (a trigger edge acts as a compare match, 3 vs 5 clock
  cycles; PWM modes only). `CCER`: 4 bits per channel starting at bit
  4(x−1) — CCxE, CCxP (0 = active high), CCxNE, CCxNP. CH1: CC1E bit 0,
  CC1P 1, CC1NE 2, CC1NP 3; CH3: CC3E 8, CC3P 9, CC3NE 10, CC3NP 11.
  CH4 has CC4E/CC4P only — no complementary output (RM §10.3.6).
- CTLR2 idle-state bits (RM §10.4.2): OIS1 bit 8, OIS1N 9, OIS2 10,
  OIS2N 11, OIS3 12, OIS3N 13, OIS4 14 — the level OCx/OCxN takes
  (after dead-time) when MOE=0; frozen once BDTR LOCK ≥ 1. Also CCDS
  (bit 3): 1 = the CHxCVR DMA request fires on the update event instead
  of the compare/capture event; CCPC/CCUS (bits 0/2) preload
  CCxE/CCxNE/OCxM and gate their update to COM events (channels 1–3
  only).
- RPTCR (0x30, RM §10.4.13): 8-bit repetition counter counting ATRLR
  reloads; the update event fires only when it overflows or underflows
  (INTFR UIF description, RM §10.4.5), so UEV period = RPTCR+1 counter
  overflows — RPTCR=0 gives an update event on every overflow.
- BDTR (0x44, RM §10.4.18): DTG[7:0] bits [7:0] dead-time —
  DTG[7:5]=0xx: DT = DTG[7:0]×TDTS; 10x: (64+DTG[5:0])×2TDTS;
  110: (32+DTG[4:0])×8TDTS; 111: (32+DTG[4:0])×16TDTS (TDTS from CTLR1
  CKD). LOCK[1:0] \[9:8\]: write-once-per-reset write-protect — level 1
  locks DTG/BKE/BKP/AOE/OISx/OISxN, level 2 adds CCxP/CCxNP/OSSI/OSSR,
  level 3 adds the CHCTLRx CC control bits. OSSI bit 10: with MOE=0
  (idle, e.g. after a brake) — 1: channels with CCxE/CCxNE=1 drive
  their OISx/OISxN idle levels, 0: output drivers disabled. OSSR bit
  11: the same choice while MOE=1 with the channel output off — the
  RM's "when the timer is not working" wording is garbled for both,
  see [quirks.md](quirks.md) §Timers. BKE bit 12 brake enable, BKP bit
  13 brake polarity (1 = BKIN active high, 0 = active low); BKE/BKP
  writes take one HB clock to land. AOE bit 14: 1 = MOE re-sets
  automatically at the next update event, 0 = software-only. MOE bit
  15 main output enable: an active brake clears it asynchronously
  (RM §10.3.7) — outputs then go to their OISx/OISxN idle levels
  (OSSI=1) or the drivers disable (OSSI=0). Brake sources: BKIN pin or
  the CSS clock failure (RM §10.3.7).
- Update event (RM §10.2.3, §10.4.5): sources are repetition-counter
  overflow/underflow (every overflow when RPTCR=0), SWEVGR UG, and
  slave-mode reset, gated by URS/UDIS (CTLR1). UEV latches the
  ATRLR/PSC/CHxCVR preloads into their shadow registers; RM §10.3.5 requires setting UG
  after configuring and before starting the counter (the SDK's
  `TIM_TimeBaseInit` does it unconditionally). SWEVGR (0x14, WO,
  self-clearing, RM §10.4.6): bit 0 UG, 1–4 CC1G–CC4G, 5 COMG (latches
  the CCPC-preloaded CCxE/CCxNE/OCxM), 6 TG, 7 BG (software brake:
  clears MOE, sets BIF).
- DMA (RM §10.4.4): DMAINTENR bit 8 UDE, 9–12 CC1DE–CC4DE, 13 COMDE,
  14 TDE — TIM2's DMAINTENR (RM §11.4.4) lacks COMDE, and the brake
  (BIE bit 7) and COM (bit 5) interrupt enables are TIM1-only. A
  compare match sets CCxIF and, with CCxDE=1, issues a DMA request
  (RM §10.3.2). The RM says nothing about compare-match request timing
  within the period or the CHxCVR=0 corner (compare value equal to the
  post-update CNT=0) — treat both as undocumented. DMACFGR 0x48
  (DBA[4:0] = base register offset from CTLR1, DBL[4:0] = burst
  length − 1) + DMAADR 0x4C implement register bursts (RM
  §10.4.19–10.4.20); the node firmware streams one compare value per
  cell via CCxDE instead, so these stay unused.
- PWM-output init recipe, cross-checked against the SDK
  (EVT/EXAM/TIM/PWM_Output, ComplementaryOutput_DeadTime,
  `ch32v00x_tim.c`): `TIM_TimeBaseInit` (writes CTLR1/ATRLR/PSC/RPTCR,
  ends with SWEVGR UG) → `TIM_OCxInit` (clears CCxE, then OCxM, CCxP,
  CCxE, and for TIM1 CCxNP/CCxNE and CTLR2 OISx/OISxN; never touches
  OCxPE or BDTR) → `TIM_OCxPreloadConfig` (OCxPE) → `TIM_BDTRConfig`
  (whole BDTR word) → `TIM_CtrlPWMOutputs` (sets MOE separately, as on
  STM32) → `TIM_ARRPreloadConfig` → CEN. OCxFE is set only by the
  separate `TIM_OCxFastConfig`, which no TIM example calls.
- Extra CTLR1 bits: `CAPLVL` (double-edge capture level indication — bit 16
  of CHxCVR reports the level) and `CAPOV` (capture value = 0xFFFF on
  overflow before capture). Useful for single-channel both-edge timing.
- `TIM1_IREMAP` (AFIO_PCFR1 bit 23) maps TIM1_CH1 to the internal LSI
  clock instead of a pin (for LSI calibration).
- TIM1 interrupts are split: TIM1BRK / TIM1UP / TIM1TRG / TIM1CC (IRQs
  34–37); TIM2 has one combined interrupt (IRQ 38).

Quirks: see [quirks.md](quirks.md) §Timers.
