# Cable reach — findings (2026-09-28, card T15)

ngspice half of DESIGN.md §9's cable-reach question: maximum segment
length unamplified, and with a re-driver in the segment. Benches:
`circuits/cable-reach/` (`tb_reach`, `tb_redriver`, `tb_reach_noise`,
run via `scripts/sim-run` or `ninja sim-cable-reach-<tb>`), built on
the T5 `circuits/phy-segment/` topology with the lumped Lseg/Cseg
swapped for a transmission-line span. The long-cable bench measurement
needs the test board — see §6.

## 1. Cable and model

Candidate cable: **3M 3365 28 AWG flat ribbon**, 6-way for the §3
segment pinout. The pinout flanks every data wire with GND pins, which
is the datasheet's "unbalanced" (ground-signal-ground) configuration
(facts: `datasheets/3M3365/notes/facts.md`, TS-0080 §Electrical):

- Z0 = 102 Ω, C = 47.5 pF/m, L = 0.49 µH/m, td = 4.86 ns/m,
  R = 0.214 Ω/m per conductor

Model (`phy-cable-segment.cir`): ngspice lossless `T` line (Z0, td)
with the conductor R split half per end. ngspice 45's LTRA (full RLGC)
runs but emits a stuck-at-zero output — verified 2026-09-28, hence the
two-element form. Unmodeled, with reasons: dielectric G (binds at
100s of MHz·m, far past where the decode contract fails), skin effect
(second order against the 50–520 Ω source resistance at ≤ 100 MHz edge
content), and the R-split lumping error (10.7 Ω total at 50 m = 10 %
of Z0).

Topology per segment, mirroring phy-segment.cir: node TX pin (50 Ω,
5 ns edges) → **470 Ω series protection R** (§7 I/O checklist) →
74LVC1G3157 bypass/insert switch → cable span → far-end TVS
capacitance (30 pF) → 470 Ω series R → OPA comparator (VDD/2
threshold, ±13 mV offset swept where it matters). Contract per run,
same as tb_decode/tb_noise: 15/15 cells decode, high-times ≥ 100 ns
from the 625 ns midpoint, periods inside the 0.9–1.6 µs legal-cell
window, spurious rxout pulses < 160 ns (ICxF fCK_INT N=8 absorbs
~167 ns).

## 2. Numbers — unamplified (tb_reach)

15-cell mixed WS2812 stream, span swept 0.5 m–200 m:

| TX series R     | Reach (contract pass)                              | Binding effect                      |
| --------------- | -------------------------------------------------- | ----------------------------------- |
| 470 Ω (§7 BOM)  | **12 m** (13 m-class boundary between 12 and 15 m) | RC settle through 520 Ω into line C |
| ~0 (50 Ω drive) | **> 200 m** (sweep limit, not a found bound)       | not decode — see below              |

- **470 Ω**: margins flat ~179–183 ns through 10 m, 129.6 ns at 12 m,
  fail from 15 m. The failure mode is *not* reflections: the far-end
  edge is a monotonic staircase (both reflection coefficients
  positive) and the comparator crosses once per cell — the line just
  stops returning below threshold inside short low periods. Cells
  merge (11 of 15 at 15 m) and split into spurious pulses up to
  168 ns. Far-end 10–90 % edges degrade from 68 ns at 0.5 m to µs-class
  staircases past ~2 m.
- **50 Ω**: margins 172–180 ns flat at every length, periods
  1247–1253 ns, edges 5–13 ns. The unterminated far end doubles the
  launch to 3.7–4.4 Vpk — over the 3.3 V rail, absorbed by the §7
  protection: ≤ 2 mA injection into the OPA pin through its 470 Ω,
  inside the ±4 mA/pin limit (DS0 §3.2 T3-1). What actually binds this
  configuration is not decode but **latency**: far-end delay =
  td + ~205 ns of comparator, 1177 ns at 200 m — a §2 ring-circulation
  input, not a bit-integrity one.

**The 470 Ω TX series resistor, not the cable, sets unamplified
reach.** tb_decode's "margins flat to 1 nF" lumped baseline survives
only because 12 m of this cable *is* ~600 pF.

## 3. Numbers — with a re-driver (tb_redriver)

Two equal spans joined by an analog repeater (comparator re-slice at
VDD/2 → TX pin → 470 Ω — every ring node's analog chain minus
protocol re-timing):

| TX series R | Max passing span | Total | vs unamplified      |
| ----------- | ---------------- | ----- | ------------------- |
| 470 Ω       | 5 m              | 10 m  | **worse** than 12 m |
| ~0 (50 Ω)   | 100 m            | 200 m | = per-span reach    |

The 470 Ω result is the finding: the repeater re-drives the mid
comparator's 7.7 V/µs ramp instead of a clean 5 ns TX edge, and from
8 m spans the *second* span fabricates 220 ns spurious pulses while
the first span still decodes with 182 ns margin. A **dumb analog
re-slice repeater does not extend protected reach** — it spends some.
(Duty does re-center at the mid slice: tap-2 margins 233–238 ns where
spans pass.)

A **re-timing** element is the opposite case: every oparroy node
re-synthesizes T0H/T1H from its own timer (§2 cut-through), so each
span is the tb_reach problem unchanged and N re-timed spans give N ×
per-span reach with no cumulative penalty. Re-driver latency, if an
analog repeater is ever used: ~740 ns per re-slice + span at 100 m
(50 Ω config).

## 4. Noise at the reach boundary (tb_reach_noise)

tb_reach's passing 470 Ω lengths past ~2 m have µs-class staircase
edges — outside the 125 ns tb_noise covered, so the card's rerun
condition applied. tb_noise's aggressors (20 kHz + 1.1 MHz, 3.3 V,
12p + 6p coupling) onto the cable far end, voff swept ±13 mV:

- **PASS 2–10 m** at all offsets: margins 165–190 ns, zero spurious
  pulses — the staircase stays monotonic under ±250 mV-class steps.
- **FAIL 12 m**: one 224–248 ns spurious pulse per stream (past ICxF
  absorption) plus a lost cell. The 18 pF of aggressor capacitance
  alone tips 12 m — noise-off 12 m runs fail in this bench though
  tb_reach (no coupling caps) passed 12 m.

**Protected reach number: 10 m with crosstalk margin, 12 m best case
on a quiet line.** In-cable data-to-data crosstalk is not the concern:
the §3 pinout sits both data wires ground-signal-ground, so the GND
wire between them shields it; the bounded external-aggressor model is
the right case. Model limit: coupling is lumped at the far end (the
most sensitive point — slowest edges, one 470 Ω from the comparator),
not distributed along the span.

## 5. Power-loop drop — the §2.1 check

§2.1 deferred its loop-drop check to this card's cable numbers. 28 AWG
at 0.214 Ω/m, §3 pinout (one 3V3 conductor, two GND): 0.321 Ω/m of
segment in the power loop. 8-node ring, uniform per-node current I:

- **Intact ring** (supervisor feeds one point, current splits both
  ways): worst-case drop at the far midpoint ΔV = 8I × 0.321 × L
  (half-loop segment currents 3.5I + 2.5I + 1.5I + 0.5I).
  I = 10 mA → 0.6 V budget (3.3 V → 2.7 V floor) allows **L ≈ 23 m**;
  I = 20 mA → **≈ 12 m**.
- **Broken loop** (worst single connector fault — the ring becomes one
  spur, all 8 nodes fed from one end): ΔV at the far end =
  8I × 0.321 × 8L / 2. I = 10 mA → **L ≈ 5.8 m**; I = 20 mA →
  **≈ 2.9 m**.

**Power, not signal, binds segment length in the broken-loop worst
case**: 3–6 m at plausible node currents vs the 10 m signal reach.
Past that, a single connector break browns out the far end of the
spur — the §2.1-documented fix (supervisor-side second-tap injection)
applies, or segments stay ≤ ~5 m for full single-fault power
integrity at 10 mA nodes. UNREG is a separate, payload-dependent
budget — out of scope here.

## 6. What remains (bench half of the card)

- Long-cable measurement on the test board (needs T10's board):
  3365/06 reels at 5/10/15/25 m, per-segment error counting under the
  §6 fault-injection harness, far-end overshoot and edge shapes on
  the §6 instrumented boundary node's PIO taps. Confirms the 10 m
  number and the 4.4 Vpk doubling against real TVS clamps.
- Comparator offset behavior on real silicon at staircase edge rates
  (sim sweeps ±13 mV; the offset spec is a fast-edge number).
- Skin/dielectric refinement only if > 50 m passive spans ever matter.

## 7. Amplifier guidance (for DESIGN.md §2)

1. **Segments ≤ 10 m: nothing needed.** Current BOM (470 Ω protection,
   no termination) decodes with ≥ 165 ns margin including
   tb_noise-class crosstalk. Wearable/instrument scale is covered.
1. **Longer reach: insert a re-timing node per ≤ 10 m span** — the §2
   cut-through re-timing makes every node a re-driver for free. A
   dedicated re-timer with no node function is a per-segment spend and
   argues against §1; prefer placing a real node.
1. **Do not build analog re-slice repeaters** — simulated, and they
   *reduce* protected reach (10 m total vs 12 m unamplified, §3).
1. **If a long passive span is unavoidable**: drop the TX series R
   toward 50–100 Ω — decode held past 200 m in sim — at the cost of
   the §7 injection-current protection (±4 mA/pin wants ≥ ~825 Ω into
   a 3.3 V fault; this trade needs a protection redesign, e.g.
   driver-side Schottky clamps). Not recommended by default.
1. Power budget binds first for single-fault integrity: ≤ ~5 m
   segments at 10 mA nodes, or second-tap injection (§2.1).

## 8. Proposed DESIGN.md §2 text (to land when the card ships)

> **Cable reach (2026-09-28, card T15 — sim; bench confirmation open):
> 10 m per segment** on 3M 3365-class 28 AWG ribbon (GND-flanked data
> wires, Z0 = 102 Ω, 47.5 pF/m) with the §7 470 Ω protection, ≥ 165 ns
> decode margin including tb_noise-class crosstalk; 12 m on a quiet
> line. The 470 Ω TX series R, not the cable, sets the limit — a
> 50 Ω-class driver decodes past 200 m in simulation. The unterminated
> far end doubles to ≤ 4.4 Vpk; the 470 Ω RX series R holds pin
> injection ≤ 2 mA. Longer reach comes from re-timing nodes (≤ 10 m
> per span; the cut-through PHY makes every node a re-driver), never
> from analog re-slice repeaters — simulated, and they reduce
> protected reach. Power, not signal, binds segment length under a
> connector break: ~3–6 m at 10–20 mA nodes on 28 AWG; past that the
> §2.1 second-tap injection applies. Analysis:
> `docs/cable-reach-2026-09-28.md` (link it as
> `[docs/...](docs/cable-reach-2026-09-28.md)` when pasting into
> DESIGN.md — plain text here so this file's own link check passes).

Related: the IDEAS.md line-capacitance self-survey (charge-time length
estimation) now has its calibration constant — 47.5 pF/m G-S-G on the
candidate cable.
