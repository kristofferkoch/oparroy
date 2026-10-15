# SN74HC165 extracted facts — scan-plane observe shift register

Part: **SN74HC165** (SOIC-16/TSSOP-16-class), 8-bit parallel-load
shift register with complementary serial outputs. Extracted for the CI
scan control/observe plane (`docs/scan-plane.md`, DESIGN.md §6).

Source (canonical PDF in `datasheets/SN74HC165/`):

- `SN74HC165-SCLS116H-datasheet-vH.pdf` — cited as (SCLS116H §x.y);
  SCLS116H, December 1982, revised December 2015, from ti.com.

JLCPCB/LCSC inventory (queried 2026-10-15 via JLCPCB's live parts
search): **Nexperia 74HC165D,653, C5613, SOIC-16, Extended tier**
(JLCPCB "preferred" flag), $0.1103 @1, ~250k stock — no Basic-tier
74HC165 exists in any package. Extended alternates: TI SN74HC165DR
(C61060), Nexperia TSSOP-16 74HC165PW,118 (C80696).

## Pinout and function (SCLS116H §3, §8.4)

Pins (SOIC/TSSOP-16): 1 = `SH//LD`, 2 = `CLK`, 15 = `CLK INH`,
10 = `SER`, 3–6/11–14 = parallel inputs `A`–`H`, 9 = `QH`, 7 = `/QH`.

Function table (Table 1):

- `SH//LD` **low ⇒ asynchronous parallel load**, independent of `CLK`,
  `CLK INH`, and `SER` — the capture needs no clock edges.
- `SH//LD` high + `CLK` rising edge with `CLK INH` low ⇒ shift toward
  `QH`; `SER` enters stage A.
- `CLK` and `CLK INH` are interchangeable clock inputs; `CLK INH` may
  only change while `CLK` is high. The scan plane ties `CLK INH` low
  and clocks `CLK`, so the constraint never applies.
- No 3-state, no output storage register: `QH` reflects the register
  continuously. No power-on-state spec (none needed — a `SH//LD` pulse
  defines the register from the parallel inputs at any time).

## Facts that shape the scan plane

- **Input thresholds** (SCLS116H §6.3): same HC levels as the 595 —
  VIH ≈ 0.7×VCC (~2.31 V at 3.3 V), VIL ≈ 0.3×VCC (~0.99 V at 3.3 V).
  The `sel` observe high of 2.9–3.3 V (docs/instrumented-ci.md §8)
  clears the VIH floor.
- Same Δt/Δv slow-input footnote as the 595 (§6.3 note 2) — push-pull
  clock only.
- Drive ±4 mA at 5 V (front page) — drives only the next stage's `SER`
  or the RP2040.
- Quiescent ICC ≤ 80 µA (front page).
- One `SH//LD` net can serve as the board-wide observe-capture strobe:
  the load is level-sensitive (async while low), so the capture takes
  the instant the line falls — sharing the 595s' `RCLK` commit line
  works with polarity discipline (docs/scan-plane.md §Chain).
