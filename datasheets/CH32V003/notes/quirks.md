# CH32V003 tribal-knowledge errata

WCH ships no errata sheet for the CH32V003 — the
community asked for one and got silence
([openwch/ch32v003#24](https://github.com/openwch/ch32v003/issues/24);
no errata PDF on the [product page](https://www.wch-ic.com/products/CH32V003.html)).
This file is the substitute: silicon quirks, doc-vs-silicon
mismatches, and toolchain traps, each with a source. Official documents live in
`datasheets/CH32V003/` (`CH32V003RM-reference-manual-v1.9.pdf` = "RM §",
`CH32V003DS0-datasheet-v1.8.pdf` = "DS §").

Every claim carries a link. Claims repeated in the community but not confirmed
against silicon are marked **unverified**.

## Clock / RCC

- **RCC_CFGR0 resets to 0x00000020, not 0x0** — RM v1.4 §3.4 claimed reset
  value 0x00000000; physical parts read 0x00000020 (HPRE field non-zero).
  RM v1.9 Table 3-1 now says 0x00000020. Trust silicon, not old manuals.
  [openwch/ch32v003#17](https://github.com/openwch/ch32v003/issues/17),
  [openwch/ch32v003#26](https://github.com/openwch/ch32v003/issues/26).
- **PLL is fixed ×2, no PLLMUL field** — unlike STM32F1/CH32V103 there is
  no multiplier field: PLLCLK = source ×2, source selected by PLLSRC
  (0 = HSI, 1 = HSE, undivided per RM §3.4.2). A 24 MHz HSE crystal ×2
  reaches 48 MHz SYSCLK fine. The /3 divider in the clock tree sits on the
  HSI feeding the flash time base, not on the PLL path. Source must be set
  before PLLON and cannot change while the PLL runs. RM v1.9 §3.3.4,
  Figure 3-2; DS v1.8 Figure 1-3.
- **Clock security system fires NMI into the void** — with `FUNCONF_USE_HSE`,
  a failing crystal trips CSS → NMI; the WCH EVT startup's weak `NMI_Handler`
  falls through to the default `j 1b` loop, so the part hangs unless you
  define one. CSS also only acts when HSE (or HSE-fed PLL) is the system
  clock. RM v1.9 §3.3.6;
  [openwch/ch32v003#48](https://github.com/openwch/ch32v003/issues/48).
- **HSI trim is a live register** — `RCC_CTLR` HSITRIM[7:3] / HSICAL[15:8]
  ([ch32v003hw.h](https://github.com/cnlohr/ch32fun/blob/master/ch32fun/ch32v003hw.h)
  lines 1796-1797). rv003usb retunes HSITRIM at runtime from the USB host's
  1 ms SE0 keep-alives, making crystal-less USB work
  ([rv003usb README](https://github.com/cnlohr/rv003usb), "Use SE0 1ms ticks
  to tune HSItrim").
- **Undocumented PLL trim word at 0x1FFFF7D4** — ch32fun's header exposes
  `VENDOR_CFG0_BASE` / `CFG0_PLL_TRIM` at 0x1FFFF7D4; RM v1.9 documents the
  ESIG block at 0x1FFFF7E0 but never this word
  ([ch32v003hw.h](https://github.com/cnlohr/ch32fun/blob/master/ch32fun/ch32v003hw.h)
  lines 568-569, 607). Contents and semantics unknown — read-only archaeology.
- **LDOTRIM field barely documented** — EXTEND_CTR LDOTRIM adjusts the
  internal LDO; WCH never explained the trade-off
  ([openwch/ch32v003#25](https://github.com/openwch/ch32v003/issues/25)).
  RM v1.9 §17.1 acknowledges it exists, nothing more.
- **DS §1.3 lists an LSE the silicon doesn't have** — the datasheet prose
  names an "external low-frequency oscillator (LSE)" among the clock
  sources, but the clock tree, RCC registers, and pinout have no LSE;
  copy-paste from bigger WCH parts (DS v1.8 §1.3 vs RM v1.9 Figure 3-2).
- **SysTick defaults to HCLK/8** — 6 MHz tick at 48 MHz SYSCLK unless the
  clock-select bit is set (ch32fun: `SYSTICK_USE_HCLK`). Rollover at 6 MHz is
  715 s, at 48 MHz 89.5 s — plan accordingly
  ([ch32fun wiki: Time](https://github.com/cnlohr/ch32fun/wiki/Time)).
- **SysTick was absent from the datasheet and RM for years** — the register
  description lived only in the QingKeV2 processor manual
  ([openwch/ch32v003#14](https://github.com/openwch/ch32v003/issues/14);
  manual linked from the [ch32fun README](https://github.com/cnlohr/ch32fun#footnoteslinks)).
  RM v1.9 finally documents it in §6.5.4 as `R32_STK_CTLR`/`STK_SR`/
  `STK_CNTL`/`STK_CMPLR` — names differ from the PM's CTLR/SR/CNTR/CMPR,
  addresses and fields match.

## GPIO & alternate functions

- **`GPIO_Speed_50MHz` is a lie by name** — RM v1.9 §7 CFGLR MODE field tops
  out at "output mode, max speed 30 MHz"; the 50 MHz enum name is an STM32
  cut-and-paste WCH fixed in EVT 2.0, still present in ch32fun's header.
  [cnlohr/ch32fun#556](https://github.com/cnlohr/ch32fun/issues/556),
  [cnlohr/ch32fun#572](https://github.com/cnlohr/ch32fun/issues/572).
- **GPIO_LCKK bit is wrong in shipping SDK headers** — several `ch32v00x.h`
  copies define the lock key at bit 16; on real hardware it is bit 8, and
  LCK8–LCK15 do not exist (only 8 pins per port)
  ([openwch/ch32v003#22](https://github.com/openwch/ch32v003/issues/22)).
- **SDK headers disagree with each other** — WCH ships multiple `ch32v00x.h`
  in one repo with conflicting masks: `ADC_JOFFSET1` 0x0FFF vs 0x03FF,
  `RCC_ADCPRE` 0xC000 (2 bits, STM32-style) vs 0xF800 (5 bits — correct for
  the 003), `FLASH_CTLR_PAGE_PG` as 16- vs 32-bit. Verify masks against the
  RM register map, not the header
  ([openwch/ch32v003#53](https://github.com/openwch/ch32v003/issues/53)).
- **The GitHub SDK repo lags the official EVT zip** — repo headers miss
  definitions the zip has (e.g. PWR PVD levels MODE4–MODE7 absent from
  `ch32v00x_pwr.h`). Download the current EVT from wch.cn when a definition
  looks thin ([openwch/ch32v003#57](https://github.com/openwch/ch32v003/issues/57)).
- **PD7 ships as NRST, with a 12 ms ignore window** — fresh parts carry
  option byte USER.RST_MODE = 10b (USER = 0xD7, `OB_RST_EN_DT12ms` in both
  WCH and ch32fun headers): the reset pin is enabled, but pulses shorter
  than ~12 ms are ignored, so a quick button tap can look like "reset does
  nothing". RM v1.9 Table 16-4 documents the 10b default; earlier RMs
  claimed 11b (NRST disabled), and the ch32fun wiki still says PD7 defaults
  to GPIO in some configurations — community sources conflict, WCH staff
  confirmed 10b in
  [openwch/ch32v003#11](https://github.com/openwch/ch32v003/issues/11).
  `minichlink -d`/`-D` toggles it
  ([ch32fun wiki: reset](https://github.com/cnlohr/ch32fun/wiki/reset)).
- **Remaps need the AFIO clock** — alternate-function remapping silently does
  nothing until `RCC->APB2PCENR |= RCC_APB2Periph_AFIO`; ch32fun's TIM2 remap
  example shows the required enables and the full-remap pin list
  (CH3/PD6) has bitten users
  ([cnlohr/ch32fun#613](https://github.com/cnlohr/ch32fun/issues/613)).
- **USART remap collides with the debug pin** — `URX_`/`UTX_` remapped USART
  lands on PD1/PD0 (DS v1.8 pin table: `PD1/SWIO/…/SCL_/URX_`); remapping RX
  to PD1 kills SWIO and bricks further programming.
- **SOP16 package cannot do SPI master** — SCK is PC5, and PC5 is not bonded
  out on the SOP16 (A4M6) despite the datasheet listing SPI support for the
  package ([openwch/ch32v003#40](https://github.com/openwch/ch32v003/issues/40)).
- **003 vs 002/004/005/006 GPIO differences** — cnlohr lists the 002/4/5/6 as
  *worse* than the 003: no pin drive-strength control, no 5 V-tolerant I/O,
  more flash wait states, and SWIO that cannot be glitched high (external
  pull-up mandatory for in-circuit programming)
  ([cnlohr/ch32fun#906](https://github.com/cnlohr/ch32fun/issues/906)).
  Read this as: 003 inputs tolerate 5 V **on the FT pins only** — DS v1.8
  Table 2-1 marks PC1/PC2/PC5/PC6 as `I/O/FT` ("FT = 5V tolerant", abs-max
  input 5.5 V in Table 3-2); cnlohr's blanket "003 has 5 V-tolerant I/O"
  overstates it, and PD1/SWIO is `I/O/A`, not FT.

## Debug / SDI & recovery

- **SWIO is PD1, full stop** — the single-wire debug interface has no remap;
  "do not re-use PD1 for multiple functions"
  ([ch32fun README, Quick Reference](https://github.com/cnlohr/ch32fun#quick-reference)).
- **Brick recipe: touch PD1, kill interrupts, or sleep early** — firmware that
  zeroes GPIOD_CFGLR or disables all interrupts locks the debugger out
  ([cnlohr/ch32fun#846](https://github.com/cnlohr/ch32fun/issues/846),
  [cnlohr/ch32fun#835](https://github.com/cnlohr/ch32fun/issues/835));
  entering sleep immediately after reset does the same
  ([cnlohr/ch32fun#233](https://github.com/cnlohr/ch32fun/issues/233)).
- **`minichlink -u` unbrick often fails; power-cycle recovery works** — the
  documented escape is WCH-LinkUtility's "Clear All Code Flash - By Power
  Off", which holds the chip in reset through a power cycle;
  `minichlink -u` hangs printing `ffffffff` in the same brick states
  ([cnlohr/ch32fun#484](https://github.com/cnlohr/ch32fun/issues/484),
  [cnlohr/ch32fun#835](https://github.com/cnlohr/ch32fun/issues/835)).
  Power the target from the programmer so the tool can cycle it.
- **DMDATA0/DMDATA1 are garbage without a debugger attached** — with no
  debug module active, the SDI printf mailbox registers read
  batch-specific garbage and ignore firmware writes; ch32fun's debugprintf
  path can stall startup for seconds. Gate all DMDATA access with
  `DidDebuggerAttach()` ([cnlohr/ch32fun#909](https://github.com/cnlohr/ch32fun/issues/909)).
- **Repeated debug memory reads reset the MCU** — polling RAM via
  `minichlink -r` resets the target every 3rd–5th read on some setups
  ([cnlohr/ch32fun#901](https://github.com/cnlohr/ch32fun/issues/901)).
- **No factory bootloader; SDI is the only way in** — the boot/system flash
  contains no open ISP protocol; programming requires the proprietary
  single-wire interface (protocol reverse-engineered by fxsheep et al.)
  ([openwch/ch32v003#3](https://github.com/openwch/ch32v003/issues/3)).
- **Non-WCH-LinkE programmers hit flash-unlock walls** — Ardulink detects the
  chip but fails unlock with `CTLR = 00008080` / `WRPTRERR` on some parts;
  recovery needs the official tool's clear-all sequence
  ([cnlohr/ch32fun#915](https://github.com/cnlohr/ch32fun/issues/915)).
- **No hardware breakpoints** — the debug module implements no trigger
  module; WCH-LinkE and PicoRVD both emulate breakpoints by patching
  `ebreak` into flash and unpatched on resume, so breakpoint count is
  unlimited but every set/clear costs flash writes
  ([PicoRVD SoftBreak](https://github.com/Community-PIO-CH32V/PicoRVD#softbreak)).
- **Undocumented debug-interface register PART at 0x7F** — PicoRVD reads a
  part-info word from 7-bit address 0x7F, absent from QDM §2.3's register
  table ([PicoRVD PicoSWIO.cpp](https://github.com/Community-PIO-CH32V/PicoRVD/blob/master/src/PicoSWIO.cpp)).
- **Programmer options beyond WCH-LinkE** — minichlink drives WCH-LinkE,
  ESP32-S2 (funprog), and "RVSWDIO003-01" (a CH32V003 as SWIO programmer);
  PicoRVD turns an RP2040 into a GDB-server SWIO probe (PIO bitbang,
  ~800 kbps normal mode) — directly usable for a supervisor-as-programmer
  CI board ([PicoRVD](https://github.com/Community-PIO-CH32V/PicoRVD),
  [minichlink](https://github.com/cnlohr/ch32fun/tree/master/minichlink)).

## Flash & option bytes

- **Fast-page programming is the fast path, not the only path** — RM v1.9
  §16.4.3 also documents standard half-word (2-byte) programming via the PG
  bit. Fast mode loads each 64-byte page as 16 × 4-byte buffer writes
  (BUFRST/BUFLOAD) then STRT. Erase granularity is 1 KB (standard) or 64 B
  (fast erase). Two unlock layers: FLASH_KEYR, then FLASH_MODEKEYR for fast
  mode; a wrong key sequence locks the interface until the next system
  reset. RM v1.9 §16.4.
- **Boot/system flash is firmware-inaccessible** — write-protected against
  user code; only the debugger writes it, by a mechanism WCH has not
  documented ([cnlohr/ch32fun#945](https://github.com/cnlohr/ch32fun/issues/945)).
- **Option bytes live at 0x1FFFF800; identity block at 0x1FFFF7E0** —
  `OB` struct (RDPR/USER/DATA0/DATA1/WRPR0/WRPR1) and `ESIG` (R16_FLACAP
  flash-size word, R32_ESIG_UNIID1..3 unique ID) at 0x1FFFF7E0; ESIG is
  documented in RM v1.9 ch.15 but missing from earlier manuals. A third
  block, `INFO` at 0x1FFFF704, is exposed in ch32fun's header with the
  comment "may not work on all processors"
  ([ch32v003hw.h](https://github.com/cnlohr/ch32fun/blob/master/ch32fun/ch32v003hw.h)
  lines 195-211, 563-568).
- **minichlink uses 64-byte sectors for the 003** — matches the fast-erase
  granularity ([minichlink.c:109](https://github.com/cnlohr/ch32fun/blob/master/minichlink/minichlink.c)).
- **Reading the last flash byte fails** — `minichlink -r dump.bin flash 0x4000` faults on the abstract command; 0x3FFF succeeds. Off-by-one in the
  debug-access path, still unexplained
  ([cnlohr/ch32fun#628](https://github.com/cnlohr/ch32fun/issues/628)).
- **DATA0/DATA1 option data need explicit flashing** — not set by a normal
  program run; tooling support is manual
  ([cnlohr/ch32fun#509](https://github.com/cnlohr/ch32fun/issues/509)).
- **RM §16.3.7 pins FLASH_OBR at the wrong offset** — the section header
  says "Offset address: 0x14", but the RM's own register list (Table 16-2)
  and the SDK's `FLASH_TypeDef` both put OBR at 0x4002201C (offset 0x1C,
  +0x18 reserved; 0x14 is FLASH_ADDR). Follow the register list
  (RM v1.9 §16.3.7 vs Table 16-2;
  [ch32v003hw.h](https://github.com/cnlohr/ch32fun/blob/master/ch32fun/ch32v003hw.h)
  FLASH_TypeDef).

## ADC

- **ADON must be written twice** — first ADON=1 only powers the ADC (needs
  tSTAB stabilization); a second ADON=1 write is the software start trigger.
  Missing the double write hangs any `while(!EOC)` loop. RM v1.9 §9.2.2;
  typical casualty: [cnlohr/ch32fun#383](https://github.com/cnlohr/ch32fun/issues/383).
- **Calibration result lands in ADC_RDATAR** — after CAL clears, the
  hardware stores the calibration code into the regular data register; the
  DS/RM never say clearly whether the offset is then applied internally or
  must be subtracted in software. Confusion is documented in
  [openwch/ch32v003#27](https://github.com/openwch/ch32v003/issues/27) and
  [#54](https://github.com/openwch/ch32v003/issues/54); the theory that the
  value is *not* auto-applied is **unverified**
  ([cnlohr/ch32fun#487](https://github.com/cnlohr/ch32fun/issues/487)).
- **Wait ≥2 ADC clock cycles after power-up before CAL** — RM v1.9 §9.2.2
  note; calibrating earlier silently produces a bad offset.
- **DUALMOD bits in headers don't exist** — ADC_CTLR1[19:16] dual-mode field
  is STM32 heritage; the 003 has one ADC
  ([cnlohr/ch32fun#319](https://github.com/cnlohr/ch32fun/issues/319)).
- **Timer-triggered ADC conversion unreliable/undocumented** — external
  trigger from TIM1 CH1/CH2 never starts conversions in at least one
  documented attempt; STATR stays 0
  ([openwch/ch32v003#63](https://github.com/openwch/ch32v003/issues/63)).
- **Sample time matters more than the docs suggest** — OPA-boosted signals
  read dramatically different at 30 vs 241 cycle sample time; long sample
  times are the fix for high-impedance sources
  ([cnlohr/ch32fun#397](https://github.com/cnlohr/ch32fun/issues/397)).
- **ADCPRE is 5 bits, not 2** — ADCCLK divides HCLK by 2…128 via
  RCC_CFGR0[15:11] (RM v1.9 §3.4.2); headers copied from other WCH parts
  carry the 2-bit STM32 mask ([openwch/ch32v003#53](https://github.com/openwch/ch32v003/issues/53)).

## OPA (op-amp / comparator)

- **OPA lives in the extended-config register, not a peripheral block** —
  OPA_EN/OPA_PSEL/OPA_NSEL are fields of `EXTEND_CTR` at 0x40023800 (RM v1.9
  ch.17); earlier RMs did not document it, and code had to poke EXTEN bits
  17/18 directly ([cnlohr/ch32fun#397](https://github.com/cnlohr/ch32fun/issues/397)).
- **EXTEN_CTR's reset value is self-contradictory in RM v1.9** — Table 17-1
  gives `0x00000400` (bit 10, LDOTRIM set), but the §17.2.1 bit table says
  LDOTRIM resets to 0 and LKUPEN (bit 6) resets to 1, which would be
  `0x00000040`. Both are printed in the same document; the truth needs a
  bench read of `R32_EXTEN_CTR` out of reset. Firmware should not RMW from
  the unknown reset state for the non-OPA fields.
- **OPA pins collide with crystal and reset** — OPA0 inputs are PA1(OSCI)/
  PA2(OSCO): OPA0 and an HSE crystal are mutually exclusive. OPA1 uses
  PD0/PD7: conflicts with NRST if PD7 is reset-enabled. DS v1.8 pin table.
- **The OPA→TIM2_CH1 internal route has no mux bit** — RM v1.9 ch.17
  documents only OPA_EN/OPA_PSEL/OPA_NSEL in EXTEND_CTR; nothing enables
  or steers the comparator output into TIM2_CH1. The route appears only
  in the DS0 §1.1 system block diagram (OPAO → Compare → TIM2_CH1) and
  DS0 §1.4.17's "directly into the TIMx input channel". The node
  firmware assumes it is hardwired and always live (TIM2_CH1's pin PD4
  stays an unused floating input). **Unverified** — bench-confirm on the
  first RX bring-up; if the route needs an undocumented enable, the
  capture stream will read as line silence.

## Timers

- **TIM2 full-remap table is error-prone** — ch32fun's
  `AFIO_PCFR1_TIM2_REMAP_FULLREMAP` comment (CH1/PC1, CH2/PC7, CH3/PD6,
  CH4/PD5) differs from WCH EVT comments copied from STM32 parts; PD6 PWM
  output under full remap has failed for users. Check the AFIO_PCFR1 bit
  table in RM v1.9 §7.3.2.1, not header comments
  ([cnlohr/ch32fun#613](https://github.com/cnlohr/ch32fun/issues/613)).
- **TIM2 CH1 doubles as ETR** — the TIM2CH1/ETR pin serves both capture
  channel 1 and the external trigger input; using ETR costs you CH1
  ([openwch/ch32v003#10](https://github.com/openwch/ch32v003/issues/10)).
- **RM §10.3.7 references a BDE (brake DMA) bit that doesn't exist** —
  the brake-signal action list says "if the BDE bit is set, a DMA
  request is generated", but DMAINTENR (RM v1.9 §10.4.4) defines no
  brake DMA enable, and the SDK's `TIM_DMA_*` source list has no brake
  entry either
  ([ch32v00x_tim.h](https://github.com/openwch/ch32v003/blob/main/EVT/EXAM/SRC/Peripheral/inc/ch32v00x_tim.h)).
  STM32 heritage; brake signaling is interrupt-only (BIE, DMAINTENR
  bit 7).
- **RM §10.3.5 inverts the PWM mode 1 semantics of §10.4.7** — the
  edge-aligned bullet says OCxREF is high when CNT > CHxCVR; the OCxM
  field description (RM v1.9 §10.4.7, 110 = PWM mode 1: active while
  CNT < CHxCVR up-counting) and STM32 semantics say the opposite.
  Trust the register description.
- **SDK PWM examples disable OCxPE against the RM's own caution** —
  RM v1.9 §10.4.7 (OCxPE note) rates PWM without the preload register
  as determined only in one-pulse mode (OPM=1), yet EVT/EXAM/TIM/
  PWM_Output and ComplementaryOutput_DeadTime both call
  `TIM_OC1PreloadConfig(TIM1, TIM_OCPreload_Disable)` with OPM=0
  ([ch32v00x_tim.c](https://github.com/openwch/ch32v003/blob/main/EVT/EXAM/SRC/Peripheral/src/ch32v00x_tim.c),
  [PWM_Output main.c](https://github.com/openwch/ch32v003/blob/main/EVT/EXAM/TIM/PWM_Output/User/main.c)).
  Enable OCxPE when streaming compare values — the preload costs one
  update event of latency but is the documented-good path.
- **OSSI/OSSR descriptions are garbled in translation** — RM v1.9
  §10.4.18 describes both as acting "when the timer is not working",
  and §10.3.7 cites a "SOOI bit". The SDK header names them
  `OSSI_Off_State_Selection_for_Idle_mode_state` /
  `OSSR_Off_State_Selection_for_Run_mode_state`
  ([ch32v00x_tim.h](https://github.com/openwch/ch32v003/blob/main/EVT/EXAM/SRC/Peripheral/inc/ch32v00x_tim.h)),
  matching STM32 semantics: OSSI picks idle-level drive vs disabled
  outputs when MOE=0 (e.g. after a brake); OSSR does the same while
  MOE=1 with the channel output off.

## EXTI / interrupts

- **All eight EXTI lines share one IRQ** — EXTI0–EXTI7 vector to the single
  `EXTI7_0_IRQHandler` (RM v1.9 §6.3 Table 6-1); demux by reading
  EXTI_INTFR. Line 8 is PVD, line 9 is AWU wakeup. There is no EXTI15_10 on
  this part.
- **C++ name mangling silently kills ISRs** — declare handlers
  `extern "C"`; a mangled `EXTI7_0_IRQHandler` never links into the vector
  table and the CPU lands in the default `1: j 1b` loop with no diagnostic
  ([openwch/ch32v003#15](https://github.com/openwch/ch32v003/issues/15)).
  Directly relevant to this project's C++ firmware.
- **Vector entry 0 is an instruction, not an address** — the WCH EVT
  startup emits `.option norvc; j handle_reset` at the vector base and
  `.word <handler>` for every other entry
  ([startup_ch32v00x.S](https://github.com/openwch/ch32v003/blob/main/EVT/EXAM/SRC/Startup/startup_ch32v00x.S)).
  Neither the RM nor the processor manual states the reset path outright;
  the mechanism that makes the SDK correct is mtvec resetting to 0
  (PM §3.2) — unified-entry mode at base 0 — and PM §2.3's unified entry
  *fetching a jump instruction* from the base. Consistent only with
  entry 0 being executed, not read as an address, and the `norvc` is
  load-bearing: a compressed `c.j` occupies half a slot and shifts every
  later entry off the hardware's number×4 indexing.
- **STM32-style NVIC priority API doesn't map cleanly** — PFIC priority
  configuration via `NVIC_PriorityGroupConfig` produces no observable
  preemption change for users; QingKe priority/interrupt-enable model
  differs from ARM's ([openwch/ch32v003#30](https://github.com/openwch/ch32v003/issues/30)).
- **Hardware priority escalation (HPE / `WCH-Interrupt-fast`) has sharp
  edges** — needs a patched compiler, adds ~4 cycles to every ISR, nests only
  2 deep, and requires manual s0/s1 save/restore care; cnlohr recommends
  plain ISRs ([cnlohr/ch32fun#906](https://github.com/cnlohr/ch32fun/issues/906)).
- **Bit-banged USB constrains pins and interrupts** — rv003usb needs USB
  D+/D− on GPIO 0–4 of a single port (the `c.andi` instruction only encodes
  a 5-bit immediate, so PC5–PC7/PD5–PD7 are unusable), the pin-change EXTI
  must be highest priority and never preempted, and critical sections must
  stay under ~40 cycles ([rv003usb README](https://github.com/cnlohr/rv003usb)).
- **SDK Delay\_* hangs if the SysTick interrupt is enabled*\* — WCH EVT
  Delay_Ms/Delay_Us poll the CNTIF flag that the user's own SysTick ISR must
  clear; result: infinite hang. Use a tick counter or keep delays
  interrupt-free ([openwch/ch32v003#62](https://github.com/openwch/ch32v003/issues/62)).

## USART / I2C / SPI

- **DMA stalls while the core sleeps in WFI** — USART1 TX via DMA1 CH4
  advances only when the core wakes; WCH support confirmed DMA is suspended
  during WFI on the CH32V003 specifically (other V00x parts differ), while
  the RM implies peripheral clocks keep running in sleep. Workaround: never
  enter WFI with a transfer in flight
  ([EEVblog thread, solved 2026-02-11](https://www.eevblog.com/forum/microcontrollers/ch32v003-dmauart-tx-stalls-during-wfi-even-with-sramendma1en-set-expected/)).
- **I2C slave: disabling clock stretching risks overrun/underrun** — RM v1.9
  §13.6 warns that with clock extension disabled, reception can overrun and
  transmission underrun; keep stretching enabled unless the master
  guarantees timing.
- **WCH's I2C master example can hold SCL low forever** — reported against
  the EVT example with proper pull-ups fitted
  ([openwch/ch32v003#9](https://github.com/openwch/ch32v003/issues/9));
  treat EVT I2C code as suspect, bit-bang or verify against the RM §13
  state machine.
- **SPI master impossible on SOP16** — see GPIO section;
  [openwch/ch32v003#40](https://github.com/openwch/ch32v003/issues/40).
- **USART remap to PD0/PD1 conflicts with SWIO** — see GPIO section; DS v1.8
  pin table.

## Power / reset

- **Standby keeps SRAM and I/O state, wakes to HSI** — exit is any EXTI
  interrupt/event or AWU; execution continues (no reset), but the clock
  system restarts on HSI, so re-init clocks after wake. Flash programming in
  progress blocks standby entry. RM v1.9 §2.3.3.
- **WFE in the WCH SDK miscompiles under `-flto`** — the inline-asm delay
  loop reads `a0` without declaring the input; LTO deletes the argument
  setup, so `a0` holds garbage and the post-wake delay loop can run ~forever
  (symptom: never wakes). Fixed version forces `t` into a0 via a register
  constraint ([openwch/ch32v003#61](https://github.com/openwch/ch32v003/issues/61)).
- **DMA does not run in sleep mode** — see USART section; 003-specific per
  WCH support
  ([EEVblog](https://www.eevblog.com/forum/microcontrollers/ch32v003-dmauart-tx-stalls-during-wfi-even-with-sramendma1en-set-expected/)).
- **NRST default: silicon and RM v1.9 agree (10b, enabled); older RMs said
  11b** — see GPIO section;
  [openwch/ch32v003#11](https://github.com/openwch/ch32v003/issues/11).

## Toolchain / programmer pitfalls

- **WCH-LinkE must be in RISC-V mode** — blue LED on after USB plug-in means
  ARM mode; the 003 won't be seen. Switch via WCH-LinkUtility/MounRiver
  "WCH-LinkRV", `rvprog -v`, or hold ModeS while plugging in. The plain
  WCH-Link (no "E") cannot program RISC-V parts at all
  ([wagiminator CH32V003 notes](https://github.com/wagiminator/CH32V003-I2C-Knob#programming-and-debugging-device)).
- **Linux needs udev rules; Windows needs Zadig** — grant access to
  1a86:8010/1a86:8012 on Linux; on Windows install WinUSB over "WCH
  interface 1" with Zadig ([wagiminator](https://github.com/wagiminator/CH32V003-I2C-Knob#programming-and-debugging-device)).
- **LinkE firmware upgrades are fragile and Windows-centric** — the official
  path is MounRiver Studio; MRS c1.40 bricked LinkEs mid-upgrade (fixed in
  c1.85) ([openwch/ch32v003#21](https://github.com/openwch/ch32v003/issues/21)),
  and a v2.9 update appeared to kill programming (later traced to a broken
  SWIO cable — the failure mode gives no diagnostics)
  ([openwch/ch32v003#18](https://github.com/openwch/ch32v003/issues/18)).
  Open-source alternative: `wlink-iap` plus dumped firmware bins
  ([cnlohr/ch32fun#662](https://github.com/cnlohr/ch32fun/issues/662)).
- **minichlink version-nags and HID errors on DIY programmers** — rv003usb-
  and ESP32-S2-based programmers draw "newer firmware available" warnings
  and sporadic `error -1 when sending hid feature report` (error 247)
  ([cnlohr/ch32fun#850](https://github.com/cnlohr/ch32fun/issues/850),
  [#560](https://github.com/cnlohr/ch32fun/issues/560)).
- **minichlink chip-ID database is not authoritative** — a CH32V002 is
  reported as CH32V006 ([cnlohr/ch32fun#646](https://github.com/cnlohr/ch32fun/issues/646));
  cross-check against ESIG flash size before trusting the banner.
- **One LinkE at a time** — minichlink cannot select among multiple attached
  WCH-LinkE programmers ([cnlohr/ch32fun#902](https://github.com/cnlohr/ch32fun/issues/902)).
- **OpenOCD verify is 15× slower than programming** — 15 s verify vs \<1 s
  program on 16 KB with WCH's OpenOCD fork; budget CI time accordingly
  ([openwch/ch32v003#28](https://github.com/openwch/ch32v003/issues/28)).
- **Full-flash readback off-by-one** — `minichlink -r … flash 0x4000`
  faults; read 0x3FFF ([cnlohr/ch32fun#628](https://github.com/cnlohr/ch32fun/issues/628)).

## Variants, fakes, and lookalikes

- **CH32V002 ≠ CH32V003** — 002/004/005/006 lose 5 V-tolerant I/O, pin
  drive-strength control, and cycle-accurate friendliness, and their SWIO
  needs an external pull-up ([cnlohr/ch32fun#906](https://github.com/cnlohr/ch32fun/issues/906)).
  Pinouts also differ between 003 packages (DS v1.8 §2): check the exact
  suffix (F4P6/A4M6/J4M6) pin table before routing.
- **Fake/remarked CH32V003 warnings** — **not found**. No credible report of
  remarked 003s surfaced in this search; at this price point
  counterfeiting is rarely economical. The real lookalike risk is buying a
  V002/A-variant board sold as F4P6 — verify with ESIG FLACAP/UNIID reads.

## Sources mined

- [cnlohr/ch32fun](https://github.com/cnlohr/ch32fun) — README, issues
  (#319, #383, #397, #484, #487, #509, #556, #560, #572, #613, #628, #646,
  #835, #846, #850, #901, #902, #906, #909, #915), `ch32v003hw.h`,
  `minichlink.c`. Richest single source.
- [cnlohr/ch32fun wiki](https://github.com/cnlohr/ch32fun/wiki) — reset,
  Time, Features pages.
- [openwch/ch32v003](https://github.com/openwch/ch32v003) — issues #3, #9,
  #10, #11, #14, #15, #17, #18, #21, #22, #24, #25, #26, #27, #28, #30,
  #40, #48, #53, #54, #57, #61, #62, #63.
- [cnlohr/rv003usb](https://github.com/cnlohr/rv003usb) — README (timing,
  c.andi pin limit, HSI-trim-via-USB).
- [wagiminator CH32V003 projects](https://github.com/wagiminator/CH32V003-I2C-Knob) —
  programmer-mode and driver-setup notes.
- [EEVblog: DMA+UART TX stalls during WFI](https://www.eevblog.com/forum/microcontrollers/ch32v003-dmauart-tx-stalls-during-wfi-even-with-sramendma1en-set-expected/) —
  WCH-support-confirmed sleep-mode DMA suspension.
- Local official docs: `datasheets/CH32V003/CH32V003RM-reference-manual-v1.9.pdf`
  (§2.3.3, §3.3, §3.4, §7.3, §9.2.2, §13.6, §15, §16.4, ch.17),
  `datasheets/CH32V003/CH32V003DS0-datasheet-v1.8.pdf` (pin tables, clock tree).
