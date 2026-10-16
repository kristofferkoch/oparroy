# Hardware design with RP2040 — power-design extraction

Raspberry Pi Ltd's application note **"Hardware design with RP2040 —
using RP2040 microcontrollers to build boards and products"**, Release
2 (build date 20/08/2026, build 0444806419d7), 35 pp. On disk:
`hardware-design-with-rp2040-release2.pdf`. Sections below cite it as
(AN §x.y). This file holds only the power-supply sections relevant to
the CI board's power tree (DESIGN.md §6, `design/ci_power.py`) and the
RP2040 supervisor capture; the rest of the document is unextracted.

## §2.1 Power — the minimal design example (AN §2.1)

- RP2040 needs two rails: **3.3 V for I/O (IOVDD) and 1.1 V for the
  digital core (DVDD)**. The 1.1 V comes from an **on-chip LDO** fed
  from 3.3 V, so the board supplies only 3.3 V (AN §2.1).
- **The reference design powers the board from USB 5 V VBUS and
  regulates down with an external fixed-3.3 V 1117-family LDO** — the
  example uses an **NCP1117** (up to 1 A, "widely available", "plenty
  for most designs"). Per its datasheet the example fits **10 µF on
  the input and 10 µF on the output** (C1, C4) (AN §2.1.1). The app
  note says nothing about the output capacitor's chemistry/ESR for the
  NCP1117.

### §2.1.2 Decoupling capacitors

- Decoupling filters supply noise and supplies charge locally at
  sudden current demand, so capacitors go **close to the power pins**.
- Rule of thumb: **100 nF per power pin**, with two deliberate
  deviations (below and §2.1.3).
- Deviation for routability: on a 2-layer, top-side-only board, pins
  48/49 share one capacitor. The app note owns the trade-off: less
  capacitance and higher inductance can let the supply "get too noisy
  and drop below the minimum allowed voltage", potentially limiting
  operating speed — "for most applications, this trade-off should be
  acceptable" (AN §2.1.2).

### §2.1.3 Internal voltage regulator (VREG)

- Connect **VREG_OUT to the DVDD pins**; the on-chip regulator makes
  1.1 V from 3.3 V.
- **1 µF close to both VREG_IN and VREG_OUT is mandatory** for a
  stable 1.1 V supply.
- The regulator has an **ESR restriction** on those capacitors, but
  "in practice, by using physically small ceramic chip capacitors,
  these requirements will almost certainly be met" — the example uses
  0402 ceramics (C8, C10) (AN §2.1.3).

## §2.4.1 USB pins — relevant to the D+/D− pass-through (AN §2.4.1)

- USB_DP/USB_DM need **no external pull-ups/pull-downs** (speed/host/
  device indication is built into the I/Os).
- They **do need 27 Ω series termination resistors close to the chip**
  to meet the USB impedance spec.
- Route the pair at **~90 Ω differential over an uninterrupted ground
  plane** (on the 1 mm example board: 0.8 mm tracks, 0.15 mm gap). USB
  FS "can be quite forgiving" but off-impedance routing is not
  guaranteed compliant.

## §3.1 Power input — powering a Pico-carrier design (AN §3.1.1)

Context: this section is about designs hosting a Raspberry Pi Pico
module rather than a bare RP2040, so most of it does not apply to the
CI board. Portable points:

- The Pico's **3V3 pin is an output — never connect it to an external
  power source** (AN §3.1.1 note).
- When feeding a board's 5 V input through a Schottky (MBR120, 1 A) or
  sharing VBUS/VSYS domains, use diodes to keep two 5 V sources from
  being tied together (AN §3.1.1).

### §3.1.2 The PFM-ripple note (AN §3.1.2)

- The Pico's buck-boost runs PFM at light load (< a few tens of mA),
  trading efficiency for "a little more voltage ripple on the 3.3V
  supply"; GPIO23 high forces the quieter PWM mode. Relevant only as a
  contrast: the CI board's linear AMS1117 has no such mode — an LDO
  rail carries no switching ripple of its own, which is one more mark
  for the LDO choice on a board full of scan-plane observers.
