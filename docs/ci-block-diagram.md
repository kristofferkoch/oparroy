# CI board — block diagram

The whole CI board as blocks and the wires between them — one page, the
review artifact for the instrumentation / scan-plane / test-board
conversations. Drawn from [DESIGN.md §6](../DESIGN.md#6-test-board)
prose as a first pass; revised as those conversations settle, and
retired in favor of the DSL review views' generated block view once the
CI board capture exists. The sources of truth behind every block:
[docs/instrumented-ci.md](instrumented-ci.md) (fault injection,
overrides, taps, transform list), [docs/scan-plane.md](scan-plane.md)
(chain topology, bit maps, POR discipline, SWIO trees),
[design/ci_power.py](../design/ci_power.py) (power tree). Where this
diagram and a source disagree, the source wins — fix the diagram.

## Board level

```mermaid
flowchart TB
  subgraph PWR["Power tree — design/ci_power.py"]
    USBC["USB-C receptacle<br/>5 V in · CC sink Rd ×2<br/>no PD negotiation"]
    LDO["AMS1117-3.3 regulator"]
    RAIL["<b>3V3</b> — always-on rail"]
    USBC -->|"5 V"| LDO --> RAIL
  end

  RP["<b>RP2040 supervisor</b> · USB device, 12 MHz xtal<br/>PIO roles: scan shift · SWIO flash channel ·<br/>debug-UART RX · boundary logic-analyzer/stimulus · pot PWM ×4"]

  USBC <-->|"D+/D− — host link, power, and debug uplink on one cable"| RP
  RAIL --> RP

  subgraph SCAN["Scan control/observe plane — docs/scan-plane.md"]
    direction LR
    C595["11 × 74HC595 — 79 control bits<br/>AUX0·AUX1·AUX2 + one slice per tile<br/>bit 0 = plain-board state"]
    C165["2 × 74HC165 — 16 observe bits<br/>per-tile sel + 3V3N"]
    C595 -->|"one daisy chain, shared SRCLK + COMMIT"| C165
  end

  RP -->|"SRCLK · SDO · COMMIT · /OE"| C595
  C165 -->|"SDI"| RP

  subgraph RING["Ring — eight node tiles on intra-board copper"]
    direction LR
    ORG(["supervisor<br/>originator port"])
    N0["tile 0<br/>boundary node · output"]
    N1["tile 1<br/>input"]
    N2["tile 2<br/>output"]
    N3["tile 3<br/>input"]
    N4["tile 4<br/>output"]
    N5["tile 5<br/>input"]
    N6["tile 6<br/>measurement"]
    N7["tile 7<br/>input"]
    DRN(["supervisor<br/>drain port"])
    ORG -->|"connector pair — yank demo,<br/>cable-reach insertion"| N0
    N0 --> N1 --> N2 --> N3 --> N4 --> N5 --> N6 --> N7 --> DRN
  end

  RAIL -->|"always-on: scan plane · injectors · bypass switches"| SCAN
  RAIL --> RING

  SWTREE["SWIO flash tree<br/>7 × 3157 binary tree<br/>selects SWIO_A2..0"]
  DBGT["debug return tree<br/>7 × 3157, ganged to the same selects"]

  C595 -.->|"per-tile byte: BRK·SHG·SHV ×2 wires + KA_CUT + PWR"| RING
  C595 -.->|"AUX0: originator-port injector + SWIO_A0·A1"| SWTREE
  C595 -.->|"AUX1·AUX2: SWIO_A2 · WD_DEFEAT · POT_SEL · BTN_A/B"| RING

  RP -->|"PIO SWIO · 4.7 kΩ root pull-up"| SWTREE
  SWTREE -->|"leaf per tile → PD1 · 10 kΩ to 3V3N"| RING
  RING -->|"leaf per tile ← PD5 debug_tx"| DBGT
  DBGT -->|"dbg_rx — PIO UART RX"| RP

  N0 <-->|"taps: opa_p · TX_A#b · opo · led_work — no series R"| RP
  N6 -->|"measurement SPI — taps P1·P2·P3: adc_sclk · adc_cs · adc_sdata"| RP

  subgraph HIO["Human I/O — demonstrator dual role"]
    HIN["input tiles 1·3·5·7<br/>10 kΩ pot + two buttons each"]
    HOUT["output tiles 0·2·4<br/>piezo buzzer each — observed, not substituted"]
  end
  RP -->|"filtered PWM ×4"| HIN
  C595 -.->|"POT_SEL → substitute mux · BTN_A/B → parallel N-FET"| HIN

  RING ==>|"per-tile sel + 3V3N"| C165
```

Every inter-tile hop but one is an instrumented segment: the upstream tile's
injector sits at its downstream boundary on the segment's two wires
(`TX_A`, `RX_B`), so eight of the ring's nine segments are instrumented at
exactly one end — the supervisor's originator port carries one of the
eight (driven from AUX0); the exception is tile 6's downstream hop: tile
6 is the measurement tile
([instrumented-ci.md §12](instrumented-ci.md#12-tile-power-measurement-chain))
and carries no injector. Solid arrows are signal or power flow, dotted arrows
are scan-chain control, the thick arrow is observe.

## Tile anatomy

One tile, its rail split, and its per-tile transform set
(instrumented-ci.md §7, F1–F8 — declared once, instanced seven times;
the measurement tile carries the extended F8 only):

```mermaid
flowchart TB
  UP["tile i−1 — or the supervisor<br/>originator port for tile 0"]
  DOWN["tile i+1 — or the supervisor<br/>drain port for tile 7"]
  RAIL["3V3 always-on rail"]

  subgraph TILE["Tile i — node design + transforms F1–F8"]
    BYP["bypass switch — sel"]
    PFET["F8 · P-FET high-side switch AO3401A<br/>bit PWR — 0 = powered"]
    DOM["3V3N node domain<br/>MCU · status LEDs · payload · SWIO pull-up"]
    MCU["CH32V003 + PHY front end<br/>design/node.py"]
    KAC["F7 · keep-alive cut 3157 + 47 kΩ PD<br/>bit KA_CUT — 0 = connected"]
    WD["watchdog charge pump WD1"]
    INJ["F1–F6 · segment injector — 6 × 3157 + 470 Ω legs<br/>per wire: pass · open · short-GND · short-3V3<br/>bits BRK_A·SHG_A·SHV_A·BRK_B·SHG_B·SHV_B"]
  end

  RAIL --> PFET --> DOM --> MCU
  RAIL -->|"always domain: injector · bypass · shunt-leg source"| INJ
  MCU -->|"ka strobe"| KAC --> WD
  WD -->|"sel — engage on watchdog timeout, KA_CUT, or PWR"| BYP
  UP -->|"segment in"| BYP
  BYP -->|"node-active"| MCU
  BYP -->|"bypassed"| INJ
  MCU -->|"re-emitted TX_A · RX_B"| INJ
  INJ -->|"instrumented segment"| DOWN
```

Per-role additions on top of the per-tile set:

- **Tile 0 (boundary node, designated debug DUT)** — four taps to RP2040
  GPIO (`opa_p`, `TX_A#b`, `opo`, `led_work`; PIO logic analyzer /
  stimulus, no series resistors) and the watchdog-defeat shunt
  (`WD_DEFEAT`, bit 0 = watchdog in charge) so a halted or single-stepped
  node stays electrically in the ring. It is an output tile.
- **Input tiles 1·3·5·7** — pot wiper through a `substitute` mux to PD6
  (`POT_SEL`: human pot ↔ supervisor filtered PWM) and each button
  paralleled by a 2N7002 N-FET (`BTN_A`/`BTN_B`, bit 0 = released).
- **Output tiles 0·2·4** — buzzer payload (PC4 → 470 Ω → piezo);
  observed through the node's telemetry, no control bits.
- **Tile 6 (measurement)** — the
  [§12 power-measurement chain](instrumented-ci.md#12-tile-power-measurement-chain)
  in place of the injector/keep-alive set and the buzzer payload: the
  extended F8 (82 mΩ shunt downstream of the power-cut FET, INA241A5
  mid-rail amp, ADCS7476 SPI ADC on the always-on 3V3), its SPI escaping
  on taps P1–P3 to supervisor GPIO0/1/2.
- **Supervisor originator port** — the same six-switch injector as a
  tile's on the supervisor→tile-0 segment (AUX0 bits 0–5); the drain
  port needs none — tile 7's injector covers that segment.

## Properties the diagram flattens

- **POR is a constructed all-zeros.** The 595 storage register has no
  silicon POR state: `/OE` pulled up, a 47 kΩ pull-down on every control
  line, and a zero-load boot sequence make bit-0 = plain board hold from
  power-on — an unpowered or hung supervisor leaves a plain board
  ([scan-plane.md §4](scan-plane.md#4-power-on-reset-the-constructed-zero-state-proof-input)).
  Those levels are the reset-state equivalence proof's inputs.
- **Observe lags control by one transaction** — the capture edge
  precedes the latch edge within a transaction
  ([scan-plane.md §1](scan-plane.md#1-architecture-one-daisy-chain)).
- **Every latched bit pattern is electrically safe** — the 470 Ω shunt
  legs bound all 79 bits' combinations, so the chain needs no hardware
  interlocks
  ([instrumented-ci.md §2](instrumented-ci.md#2-the-segment-injector)).
- Bit maps live in [scan-plane.md §3](scan-plane.md#3-bit-maps); the
  transform list this diagram summarizes lives in
  [instrumented-ci.md §7](instrumented-ci.md#7-the-transform-list).
