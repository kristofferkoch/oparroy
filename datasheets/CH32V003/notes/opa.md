# CH32V003 OPA / comparator (ring RX front-end)

Part of the CH32V003 notes — part identity, source documents, and citation
conventions in [facts.md](facts.md). Sources: DS0 §1.4.17, §3.3.15; RM
ch.17.

- One op-amp/comparator unit. Two selectable positive inputs, two negative
  inputs, one output: **OPP0 = PA2, OPP1 = PD7, OPN0 = PA1, OPN1 = PD0,
  OPO = PD4** (DS0 §2.3 Table 2-2).
- Output destinations: GPIO pin OPO (PD4, AF) and an internal route to
  **TIM2_CH1 input capture** (system block diagram, DS0 §1.1; DS0 §1.4.17:
  "comparison results from the GPIO output or directly into the TIMx input
  channel"). OPA output also feeds the ADC path ("amplified and fed into the
  ADC").
- Control register: `R32_EXTEN_CTR` at `0x40023800`, reset `0x00000400`
  (RM §17.2):
  - bit 18 `OPA_PSEL` — 1: positive channel 1 (PD7); 0: channel 0 (PA2).
  - bit 17 `OPA_NSEL` — 1: negative channel 1 (PD0); 0: channel 0 (PA1).
  - bit 16 `OPA_EN` — 1: enable.
  - bit 10 `LDOTRIM` — core LDO boost voltage mode.
  - bits 7/6 `LKUPRST` / `LKUPEN` — core lock-up monitor reset
    (LKUPEN resets to 1).
- GPIO config for OPA inputs: floating input (RM §7.2.10 Table 7-7).
- **No hysteresis parameter or control is documented** in DS0 or RM. Treat
  the comparator as non-hysteretic; threshold is set by whatever is on the
  negative input pin.
- OPCM reset: with OPA/CMP reset enable on, a high OPA output generates a
  system reset (RM §3.2.2) — a hardware "line active" wake/reset option.
- Key electricals (DS0 §3.3.15 Table 3-26): common-mode input 0–VDD; input
  offset ±3 mV typ / ±13 mV max; GBW 12 MHz; slew rate 7.7 V/µs; wake-up
  from shutdown 520 ns (0.1%, CLOAD=50 pF, RLOAD=4 kΩ); output swing
  VDD−180 mV high / 5 mV low at 4 kΩ load; static current 273 µA; drive
  current 1.5 mA; supply 2.8–5.5 V.
- At 48 MHz one bit cell of an 800 kbit/s WS2812-class signal is 60 clocks;
  OPA slew/wake-up times are far below that, so comparator timing is not the
  bottleneck.
- Quirks: see [quirks.md](quirks.md) §OPA (op-amp / comparator).
