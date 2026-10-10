# SN74LVC1G3157 extracted facts — ring bypass SPDT analog switch

Part: **SN74LVC1G3157DBVR** (SOT-23-6), single SPDT analog switch.
Extracted 2026-09-26 for the watchdog/bypass work (DESIGN.md §4).

Source (canonical PDF in `datasheets/SN74LVC1G3157/`):

- `SN74LVC1G3157-datasheet-SCES424O.pdf` — cited as (SCES424O §x.y);
  SCES424O, January 2003, revised June 2025; fetched 2026-09-26 from
  ti.com.

JLCPCB/LCSC inventory (queried 2026-09-26 via jlcsearch mirror, both
Extended tier): TI C10426, $0.072, ~51k stock; UMW clone C3040658,
$0.047, ~124k stock.

## Pinout and function (SCES424O §4, §7.4)

SOT-23-6 (DBV): 1 = B2, 2 = GND, 3 = B1, 4 = A (common), 5 = VCC,
6 = S (select). Function table: **S = L connects A–B1; S = H connects
A–B2.**

## Facts that shape the bypass design

- **Control-input thresholds** (SCES424O §5.4, VCC = 2.3–5.5 V):
  VIH ≥ 0.7×VCC (2.31 V at 3.3 V), VIL ≤ 0.3×VCC (0.99 V at 3.3 V). Any
  RC drive of S must hold above 2.31 V (node inserted) and fall below
  0.99 V (bypass guaranteed) — the 0.99–2.31 V band is indeterminate.
- **Control-input transition rate ≤ 10 ns/V** at 3.3 V (SCES424O §5.4
  Δt/Δv) — a millisecond-scale RC ramp into S violates this by ~10⁵.
  The datasheet's own footnote points at TI SCBA004 (*Implications of
  Slow or Floating CMOS Inputs*) and requires inputs held at a rail.
  Quantified penalty on the same page: ΔICC up to **500 µA** with the
  select pin at VCC−0.6 V (§5.5) — the input buffer burns current while
  the ramp dwells mid-level.
- **rON** (SCES424O §5.5): 7 Ω typ / 9 Ω max at VCC = 3 V, 25 °C, 24 mA;
  20 Ω max over −40…125 °C; resistance over the full 0–VCC signal range
  ≤ 25 Ω (DBV package). Irrelevant drop at ring-signal currents.
- Leakage (SCES424O §5.5): switch-off ±1 µA max, on-state ±1 µA,
  control input ±1 µA. ICC ≤ 10 µA quiescent (85 °C).
- Speed: operating frequency typ 340 MHz (front page) — three orders of
  magnitude above the 800 kbit/s ring.
- **No partial-power-down (Ioff-protection) spec** — behavior with VCC =
  0 and live signal pins is not specified. Consequence for §4: the
  bypass switch and its watchdog must be powered from the always-on ring
  rail, not the per-node switchable rail, or a node power cut kills the
  bypass with the node.
- **On-state switch current ±128 mA abs max** (SCES424O §5.1, I_I/O) —
  extracted 2026-10-05 for the §6 fault-injection design: the segment
  short-injection legs (3.3 V / 470 Ω ≈ 7 mA) sit ~18× inside the
  limit.
- **Capacitance** (SCES424O §5.5, extracted 2026-10-05 for the §6
  tap/shunt residual budgets): control input CI = 2.7 pF; switch port
  Cio(off) = 5.2 pF; Cio(on) = 17.3 pF. A NC-throw "open" still hangs
  the 5.2 pF off-port capacitance on the common net.
