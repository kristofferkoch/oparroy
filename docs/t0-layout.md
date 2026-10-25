# T0 functional and placement guide

T0 is the boundary node between the supervisor and the ring. Lay it out as
**two opposite-direction data paths plus local support blocks**, not as one
cloud of connected parts. This guide uses the board's global reference
designators: `U47` here means the same footprint in KiCad. The lookup tables
pair each refdes with its DSL capture path;
[test_ci_board.py](../tests/test_ci_board.py) checks them against
[placement-map.json](../boards/ci/placement-map.json).

The electrical details remain in [instrumented-ci.md](instrumented-ci.md),
[scan-plane.md](scan-plane.md), and the DSL capture. This page extracts the
model needed for placement.

**Directions are from T0's perspective, independently for each ring.**

| Ring | T0 input                         | T0 output                          |
| ---- | -------------------------------- | ---------------------------------- |
| A    | From the supervisor through J3.5 | Toward T1                          |
| B    | From T1                          | Toward the supervisor through J3.7 |

J3 is therefore the supervisor-side connector for both ring A input and ring B
output.

The active-parts cast is short:

| Parts                           | Part type                          | What T0 uses it for                                          |
| ------------------------------- | ---------------------------------- | ------------------------------------------------------------ |
| `U47`                           | CH32V003 MCU                       | Receive and re-emit both rings; run local node functions     |
| `U22`–`U27`, `U37`–`U44`, `U46` | SN74LVC1G3157 analog SPDT switches | Select bypass or MCU drive; break wires; connect test shunts |
| `U13`                           | 74HC595                            | Turn serial scan data into static control levels             |
| `U11`                           | 74HC165                            | Sample status signals back into the scan chain               |
| `Q1`                            | P-channel MOSFET                   | Cut the MCU's power domain                                   |
| `U45`                           | 74LVC1G17, DNP                     | Optional Schmitt buffering of `sel`                          |
| `D5`                            | BAT54S diode pair                  | Watchdog charge pump                                         |
| `D3`, `D4`                      | TVS diodes                         | Cable-connector protection                                   |

## 1. The mental model

| T0 state     | Ring A                                                                            | Ring B                                             |
| ------------ | --------------------------------------------------------------------------------- | -------------------------------------------------- |
| Healthy      | Receive, decode, and re-emit toward T1                                            | Receive, decode, and re-emit toward the supervisor |
| Dead or hung | The watchdog relaxes analog switch `U46` into a bypass around the MCU transmitter | No equivalent bypass switch                        |

Remember these fault-injection facts:

- The six switches at T0's T1-side edge are test equipment, **not** ordinary
  receive/transmit stages.
- They open the two T1-side wires or connect them through 470 Ω to ground or
  3.3 V.
- At reset, every test control is zero and the board behaves like the plain
  node.

Keep five kinds of connection visually separate:

1. **Ring A:** left to right, supervisor/J3 to T1.
1. **Ring B:** right to left, T1 to supervisor/J3.
1. **Watchdog and bypass:** a local loop from MCU keep-alive to `U46` select.
1. **Fault injection:** branches at the T1-side edge, not extra PHY stages.
1. **Control and observation:** low-speed fan-out to the scan plane and
   supervisor; route these after the data paths.

## 2. Ring A: the main left-to-right chain

```text
supervisor                                             T0
originator                                             ring-A output to T1
    │                                                      ▲
    │  J3.5   R96       U46 bypass/TX mux       R97   U37  │ TX_A#b
    └──CABLE_A──470 Ω──opa_p──B1                  470 Ω──break──┬──►
                  │             COM──txa_sw──►                  │
                  │             ▲                               │
                  │             B2                              │
                  ▼             │                               │
             U47 PA2       U47 PD2                               │
             OPP0 RX       TIM1_CH1 TX                           │
                  ▲                                             │
             R102/R103                                U38+R89 to GND
             VDD/2 threshold                          U39+R90 to 3V3
                  │                                      on TX_A#b
             U47 PA1/OPN0
```

`R96` and `R97` are the two 470 Ω terminal-protection resistors. `U46` is the
only switch in the ordinary ring-A path:

- `sel = 0`: COM connects to B1, so ring-A input traffic bypasses the MCU
  driver.
- `sel = 1`: COM connects to B2, so `U47`'s ring-A transmitter drives T1.
- The receiver at `opa_p` stays connected in either state. A bypassed node can
  still listen.

`U37` is the ring-A output test break. Its reset state passes `R97` to T1;
`BRK_A = 1` opens that path. `U38`/`R89` and `U39`/`R90` are normally absent
shunt branches on the **T1 side** of `U37`.

Two boundary taps belong here. `opa_p` taps the node side of `R96`; `TX_A#b`
taps after `U37`. They are wires to supervisor GPIO, not buffered test-point
circuits and not series-resistor footprints.

## 3. Ring B: the returning chain

Read this lane from right to left during placement:

```text
T1                                              supervisor/J3.7
 │                                                  ▲
 │ RX_B#b   U40        R98       U47 PD7/OPP1       │
 └──────────break──►──470 Ω──►──opa_p_b─────────────┤
             │                                      │
       U41+R91 to GND                         U47 PC3/TIM1_CH3
       U42+R92 to 3V3                              txb_drv
             │                                      │
             └──────── test branches on RX_B#b      │
                                                    R99
                                              470 Ω / TX_B
                                                    │
                                                   J3.7
```

`U40` is the ring-B input break. `U41`/`R91` and `U42`/`R92` are its ground and
3.3 V shunt branches. Ring B has no local equivalent of `U46`: `U47` transmits
back toward the supervisor through `R99` only.

The physical order is therefore **T1-side injector → `R98` → MCU** on the
ring-B input lane. Do not accidentally place `U40`–`U42` as
if they belonged to ring A merely because their package and control names
match.

## 4. What the small chips do

### SN74LVC1G3157: one analog SPDT switch

Every `U22`–`U27`, `U37`–`U44`, and `U46` is the same kind of part. It is not
an op-amp, logic buffer, or digital multiplexer with an output buffer. It is a
small bidirectional analog single-pole/double-throw switch:

| Select `S` | Connected pins                 | Use on T0                                                                                   |
| ---------- | ------------------------------ | ------------------------------------------------------------------------------------------- |
| 0          | COM (`A`, pin 4) to B1 (pin 3) | Plain-board path: bypass, transmit, break-closed, keep-alive-connected; shunt branch absent |
| 1          | COM (`A`, pin 4) to B2 (pin 1) | Selected path: node TX, open throw, enabled shunt, or watchdog defeat                       |

An unused B1 or B2 is deliberate. A break switch uses B2 as an open circuit;
a shunt switch leaves B1 open so bit zero removes the branch. Its select is a
low-speed scan-plane output. Its analog pins belong next to the signal path.

### The other active parts

- **`U47`, CH32V003:** the node MCU. Its internal comparator receives ring A
  and ring B; timers generate both transmit waveforms. It also produces the
  watchdog keep-alive, heartbeat, link-LED drive, debug output, and buzzer PWM.
- **`U46`, another 3157:** the ring-A bypass/node-TX selector, controlled by
  the watchdog's `sel`, not directly by a scan bit.
- **`U13`, 74HC595:** T0's eight-bit control slice. A serial word becomes the
  static `BRK_A`, `SHG_A`, `SHV_A`, `BRK_B`, `SHG_B`, `SHV_B`, `KA_CUT`, and
  `PWR` levels. It does not carry ring data.
- **`U11`, 74HC165:** the shared OBS0 observe stage. It samples T0's `sel` and
  `3V3N` along with T1–T3's corresponding signals. There is no T0-local observe
  chip.
- **`Q1`, AO3401A P-channel MOSFET:** the node power switch. `PWR = 0` turns it
  on; `PWR = 1` cuts `3V3N` while the injectors and bypass switch remain alive.
- **`D5`, BAT54S:** the diode pair in the edge-sensitive watchdog charge pump.
- **`U45`, 74LVC1G17, DNP:** optional Schmitt-trigger insurance in the `sel`
  path. `R101` is the fitted 0 Ω bridge. Populating `U45` means depopulating
  `R101`; they are not two ordinary cascaded stages.
- **`D3` and `D4`, TVS diodes:** connector-side protection on the cable's
  ring-A input and ring-B output wires.

## 5. Watchdog, power, and control are separate loops

### Watchdog and bypass

```text
U47 PD3       U43          R109/C32/D5/C33/R108       R101       U46 S
keep-alive──►KA cut──────►edge pump and decay─────────►0 Ω──────►sel_sw
              │                  │                         ▲
           R93 to GND          sel                         │
                                                        U44+R95
                                                        to 3V3
                                                   WD_DEFEAT shunt
```

| Condition                       | What happens to `sel`                | Result at `U46`                    |
| ------------------------------- | ------------------------------------ | ---------------------------------- |
| `U47` emits keep-alive edges    | Charge pump holds it high            | Node TX drives ring A              |
| MCU hangs                       | `R108` discharges it low             | Bypass                             |
| `KA_CUT` opens `U43`            | Decays low without cutting MCU power | Bypass; simulated hang             |
| `WD_DEFEAT` enables `U44`/`R95` | Forced high through 470 Ω            | Node-active while halted for debug |

`R93` parks the watchdog input low while the keep-alive cut is active.

Place this as a compact loop near `U46`'s select pin and `U47` PD3. `U44` and
`R95` belong beside the `sel` node, not beside the segment shunts merely
because they share a part type.

### Two power domains

```text
3V3 always ─────────────────────────────►U13, U37–U44, U46
    │                                   shunt-leg sources
    └─►Q1──►3V3N──►U47, C30/C31, R102, status LEDs, TP2
          gate
           │
          R94 to GND
```

| Rail            | What it supplies                               | Behavior when `PWR = 1`                                        |
| --------------- | ---------------------------------------------- | -------------------------------------------------------------- |
| `3V3` always    | `U13`, `U37`–`U44`, `U46`, shunt-leg sources   | Remains on; test and bypass hardware stays alive               |
| `3V3N` switched | `U47`, `C30`/`C31`, `R102`, status LEDs, `TP2` | Cut by `Q1`; everything that must die with the MCU loses power |

Placement anchors:

- Keep `Q1`/`R94` and `C30`/`C31` close to `U47`.
- Keep the threshold divider `R102`/`R103` close to the comparator pins.
- Treat `TP2` as switched `3V3N`, not the always-on rail.

### Control and observation

| Function                 | Signals                                                               | Hardware/path                                                                |
| ------------------------ | --------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| T0 control               | `BRK_A`, `SHG_A`, `SHV_A`, `BRK_B`, `SHG_B`, `SHV_B`, `KA_CUT`, `PWR` | `U13` drives the switches and `Q1`; `R15`–`R21` and `R94` provide pull-downs |
| Watchdog defeat          | `WD_DEFEAT`                                                           | AUX1 drives `U44`; `R64` provides the pull-down                              |
| Supervisor boundary taps | `opa_p`, `TX_A#b`, `opo`, `led_work`                                  | Direct wires to supervisor GPIO                                              |
| Scan observation         | `sel`, `3V3N`                                                         | `U11`/OBS0 samples T0 alongside T1–T3                                        |
| Debug leaves             | `swio`, `debug_tx`                                                    | Low-speed connections to the central mux trees                               |

- All-zero control means pass-through, shunts absent, keep-alive connected,
  and node powered.
- None of these observation or debug paths needs another local switch in T0.

## 6. Supervisor-side and T1-side injectors are different

T0 has an injector only on its **T1-side** segment. The supervisor-to-T0 cable
has its own injector at the supervisor end:

| Capture path   | Refdes | Function                                                  |
| -------------- | ------ | --------------------------------------------------------- |
| `SUP/FI1/SWAB` | `U22`  | Ring-A input break, supervisor side                       |
| `SUP/FI1/SWAG` | `U23`  | Ring-A input short to GND through `R67`, supervisor side  |
| `SUP/FI1/SWAV` | `U24`  | Ring-A input short to 3V3 through `R68`, supervisor side  |
| `SUP/FI1/SWBB` | `U25`  | Ring-B output break, supervisor side                      |
| `SUP/FI1/SWBG` | `U26`  | Ring-B output short to GND through `R69`, supervisor side |
| `SUP/FI1/SWBV` | `U27`  | Ring-B output short to 3V3 through `R70`, supervisor side |

In particular, **`U23` is `SUP/FI1/SWAG`**, not T0's `U38`. Keep these six
parts with the supervisor originator and J0 side of the cable; do not pull them
into T0's T1-side injector cluster.

For either injector and either wire, the fault states are:

| `BRK` | `SHG` | `SHV` | Wire state                                       |
| ----- | ----- | ----- | ------------------------------------------------ |
| 0     | 0     | 0     | Pass-through                                     |
| 1     | 0     | 0     | Open segment                                     |
| x     | 1     | 0     | Short to GND through 470 Ω                       |
| x     | 0     | 1     | Short to 3V3 through 470 Ω                       |
| x     | 1     | 1     | Ground-to-3V3 cross-short through two 470 Ω legs |

## 7. Placement recipe

Use a local left-to-right coordinate system with J3 and the supervisor on the
left and T1 on the right. A useful first arrangement is:

```text
                 LEDs / human-visible payload, clear of the signal lanes

J3 ─ R96 ───────── U46 ─ R97 ─────────────── U37 ──► T1       ring A ─►
      │  U47 RX     ▲                         │ ├─ U38─R89─GND
      │             U47 TX_A                  │ └─ U39─R90─3V3
R102/R103 ──────────┘                         └────── opa_p / TX_A#b taps

J3 ◄──────────────────────── R99 ─ U47 TX_B                    ◄─ ring B
T1 ── U40 ─ R98 ─ U47 RX_B
       │ ├─ U41─R91─GND
       │ └─ U42─R92─3V3

U47 ─ U43 ─ R109/C32/D5/C33/R108 ─ R101 ─ U46.S      local watchdog loop
                         │                  U44─R95─3V3
                        sel

Q1/R94 + C30/C31 near U47 power pins; R104/BZ1 near the MCU buzzer pin
U13 + R15–R21 along the inner edge; TP1–TP4 in one accessible pogo/test group
Boundary taps leave as short, grouped stubs toward the supervisor
```

Anneal in this order:

1. **Lock the two ring lanes.** Place J3, `R96`, `U46`, `R97`, `U37` for ring A
   and `U40`, `R98`, `R99` for ring B. Put the shunt switches and their own
   470 Ω resistors directly beside the corresponding T1-side wire.
1. **Place the MCU and threshold.** `U47` should serve both receiver lanes
   without crossing the transmit and watchdog connections. Keep
   `R102`/`R103` short to PA1/OPN0; keep `R100` beside OPO/OPP0 if the DNP
   footprint remains.
1. **Close the local loops.** Bring `U43` and the watchdog parts next to
   `U46.S`; place `Q1`, `R94`, `C30`, and `C31` as the power island.
1. **Add taps before scan wiring.** The `opa_p`, `TX_A#b`, `opo`, and
   `led_work` stubs should be short and direct. They carry high-speed signals
   or stimulus; do not route them through the 595 cluster.
1. **Route control last.** Put `U13` and its pull-downs on the inner edge,
   then fan the eight static controls out to their switches. Grouping by
   function matters more than making all identical 3157 packages adjacent.
1. **Finish with indicators and access.** Keep LEDs visible, the buzzer
   isolated from the comparator area, and TP1–TP4 accessible. Preserve a
   ground-return path beside every ring and tap route.

The ratsnest should now read as two horizontal spines with short local
branches, rather than a star around the MCU.

## 8. T0 refdes lookup

### Active and control parts

| Capture path    | Refdes | Function                               |
| --------------- | ------ | -------------------------------------- |
| `T0/U1`         | `U47`  | CH32V003 node MCU                      |
| `T0/PHY1/SW1`   | `U46`  | Ring-A bypass/node-TX analog switch    |
| `T0/PHY1/BUF1`  | `U45`  | DNP Schmitt-buffer option on `sel`     |
| `T0/FI1/SWAB`   | `U37`  | Ring-A output break                    |
| `T0/FI1/SWAG`   | `U38`  | Ring-A output ground shunt switch      |
| `T0/FI1/SWAV`   | `U39`  | Ring-A output 3V3 shunt switch         |
| `T0/FI1/SWBB`   | `U40`  | Ring-B input break                     |
| `T0/FI1/SWBG`   | `U41`  | Ring-B input ground shunt switch       |
| `T0/FI1/SWBV`   | `U42`  | Ring-B input 3V3 shunt switch          |
| `T0/FI1/SWKA`   | `U43`  | Keep-alive cut                         |
| `T0/FI1/SWWD`   | `U44`  | Watchdog-defeat shunt switch           |
| `T0/FI1/QPW`    | `Q1`   | `3V3` to `3V3N` power-cut P-FET        |
| `PLANE/T0/U1`   | `U13`  | T0 74HC595 control stage               |
| `PLANE/OBS0/U1` | `U11`  | Shared 74HC165 observe stage for T0–T3 |
| `PLANE/AUX0/U1` | `U8`   | Supervisor-injector control stage      |
| `PLANE/AUX1/U1` | `U9`   | Watchdog-defeat control stage          |
| `SUP/U1`        | `U28`  | RP2040 supervisor                      |

### PHY, watchdog, power, and payload passives

| Capture path   | Refdes | Function                            |
| -------------- | ------ | ----------------------------------- |
| `T0/J1`        | `J3`   | Supervisor-side segment connector   |
| `T0/PHY1/Dar`  | `D3`   | Ring-A input TVS                    |
| `T0/PHY1/Dbt`  | `D4`   | Ring-B output TVS                   |
| `T0/PHY1/Rar`  | `R96`  | Ring-A input 470 Ω protection       |
| `T0/PHY1/Rat`  | `R97`  | Ring-A output 470 Ω protection      |
| `T0/PHY1/Rbr`  | `R98`  | Ring-B input 470 Ω protection       |
| `T0/PHY1/Rbt`  | `R99`  | Ring-B output 470 Ω protection      |
| `T0/PHY1/Rth1` | `R102` | Comparator threshold upper resistor |
| `T0/PHY1/Rth2` | `R103` | Comparator threshold lower resistor |
| `T0/PHY1/Rfb`  | `R100` | DNP comparator hysteresis option    |
| `T0/PHY1/Rsel` | `R101` | Fitted 0 Ω `sel` bridge             |
| `T0/FI1/RAG`   | `R89`  | Ring-A ground-shunt 470 Ω           |
| `T0/FI1/RAV`   | `R90`  | Ring-A 3V3-shunt 470 Ω              |
| `T0/FI1/RBG`   | `R91`  | Ring-B ground-shunt 470 Ω           |
| `T0/FI1/RBV`   | `R92`  | Ring-B 3V3-shunt 470 Ω              |
| `T0/FI1/RKA`   | `R93`  | Watchdog-side keep-alive pull-down  |
| `T0/FI1/RPW`   | `R94`  | Power-FET gate pull-down            |
| `T0/FI1/RWD`   | `R95`  | Watchdog-defeat 470 Ω               |
| `T0/WD1/Rs`    | `R109` | Charge-pump series resistor         |
| `T0/WD1/Cp`    | `C32`  | Charge-pump capacitor               |
| `T0/WD1/D1`    | `D5`   | Charge-pump BAT54S diode pair       |
| `T0/WD1/Cs`    | `C33`  | Watchdog storage capacitor          |
| `T0/WD1/Rb`    | `R108` | Watchdog decay resistor             |
| `T0/C1`        | `C30`  | MCU local decoupling                |
| `T0/C2`        | `C31`  | Switched-node-rail bulk capacitor   |
| `T0/RBZ`       | `R104` | Buzzer series resistor              |
| `T0/BZ1`       | `BZ1`  | Piezo buzzer                        |

### Scan pull-downs, indicators, and test access

| Capture path        | Refdes | Function                         |
| ------------------- | ------ | -------------------------------- |
| `PLANE/T0/C1`       | `C6`   | T0 74HC595 decoupling            |
| `PLANE/R_T0_BRK_A`  | `R15`  | `BRK_A` pull-down                |
| `PLANE/R_T0_BRK_B`  | `R16`  | `BRK_B` pull-down                |
| `PLANE/R_T0_KA_CUT` | `R17`  | `KA_CUT` pull-down               |
| `PLANE/R_T0_SHG_A`  | `R18`  | `SHG_A` pull-down                |
| `PLANE/R_T0_SHG_B`  | `R19`  | `SHG_B` pull-down                |
| `PLANE/R_T0_SHV_A`  | `R20`  | `SHV_A` pull-down                |
| `PLANE/R_T0_SHV_B`  | `R21`  | `SHV_B` pull-down                |
| `PLANE/R_WD_DEFEAT` | `R64`  | `WD_DEFEAT` pull-down            |
| `T0/SL1/Dp`         | `LED2` | Switched-rail power LED          |
| `T0/SL1/Dw`         | `LED4` | Working heartbeat LED            |
| `T0/SL1/Du`         | `LED3` | Supervisor-side link LED         |
| `T0/SL1/Dd`         | `LED1` | T1-side link LED                 |
| `T0/SL1/Rp`         | `R105` | Power-LED resistor               |
| `T0/SL1/Rs`         | `R106` | Shared link-LED resistor         |
| `T0/SL1/Rw`         | `R107` | Working-LED resistor             |
| `T0/TP1`            | `TP1`  | SWIO test pad                    |
| `T0/TP2`            | `TP2`  | Switched `3V3N` test pad         |
| `T0/TP3`            | `TP3`  | Ground test pad                  |
| `T0/TP4`            | `TP4`  | Spare PC7 test pad               |
| `SUP/FI1/RAG`       | `R67`  | Ring-A input ground-shunt 470 Ω  |
| `SUP/FI1/RAV`       | `R68`  | Ring-A input 3V3-shunt 470 Ω     |
| `SUP/FI1/RBG`       | `R69`  | Ring-B output ground-shunt 470 Ω |
| `SUP/FI1/RBV`       | `R70`  | Ring-B output 3V3-shunt 470 Ω    |
