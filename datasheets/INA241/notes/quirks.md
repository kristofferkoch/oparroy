# INA241 quirks and surprises

- **Enhanced PWM rejection masks the output for 1 µs after a
  common-mode transient.** On a large ΔV/Δt CM step the device holds
  the output for 1 µs so the disturbance can't propagate; further
  transients within the following 3 µs rely on AC-CMRR alone. Rated
  for PWM up to 125 kHz or edges ≥ 3 µs apart (DS §7.3.1.1, Figure
  7-1). Harmless on the CI chain's fixed 3.3 V rail CM, but any
  design that switches the sensed rail loses µs-scale features in
  that hold window.
- **Bandwidth, slew, and settling are typ-only.** The 1.1 MHz −3 dB
  bandwidth ("All Gains"), 8 V/µs slew rate, and 0.5–1.5 µs settling
  specs have a TYP column entry and no MIN (DS §6.5 Frequency
  Response rows) — there is no guaranteed timing floor, which matters
  when the µs-scale current-feature budget is built on them.
- **The front-page "±10 µV max offset (Version A)" is not uniform
  across gains.** §6.5 splits it per variant: A1 ±20 µV, A2 ±15 µV,
  A3/A4 ±10 µV, A5 ±8 µV max (DS §1 vs §6.5). Favorable for the A5
  selection, but the headline number doesn't apply to every A-grade
  part.
- **Confusing variant naming.** A/B suffix is an accuracy grade, not
  a pinout or feature split — one pinout covers all ten orderable
  variants (DS §5). And the A1…A5 index maps to 10/20/50/100/200 V/V,
  not a linear ladder: A5 is 200 V/V and no 500 V/V member exists
  (DS §4 Table 4-1). A "gain-500 INA241" requirement cannot be met by
  this family.
- **Max capacitive load is 1 nF with no isolation resistor**
  (DS §6.5). A 1 MSPS SAR ADC's sampling capacitor typically needs a
  charge-bucket RC that can exceed this; the ADC front-end needs an
  isolation resistor and re-verified stability.
