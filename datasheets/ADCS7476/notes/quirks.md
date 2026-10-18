# ADCS7476 quirks

- **Linux IIO driver `ad7476.c` discards the LSB for this frame.** The
  driver's 12-bit ad7466/ad7476-class channel uses `shift = 13 − bits = 1` (reads bits [12:1] of the big-endian 16-bit word), while the
  ADCS7476, ADI AD7476 (Rev D, serial-interface section), and TI
  ADS7886 (SLAS492B §8.4.1) datasheets all describe the identical
  frame — 4 leading zeros + 12 data bits, DB0 valid through the 16th
  SCLK period — which maps to shift 0. The same driver's TI-class
  parts (`adc121s`, `ads7866`) do use shift 0, but those parts have a
  genuinely different frame (first bit clocked out after the first
  falling edge, not at CS fall — ADC121S021 datasheet, serial-timing
  figure), so the driver is internally consistent only if the
  ad7476-class shift is a long-standing off-by-one or reflects
  hardware behavior the datasheets don't document. Unresolved without
  hardware: **firmware implements the datasheet frame (result = word
  & 0xFFF); verify the first bench read against a known voltage.**
  (drivers/iio/adc/ad7476.c, `AD7476_CHAN` macro; DS §7.3, Figure 2.)
- **Track-time tension at full speed.** Hold→track resumes on the
  13th SCLK rising edge (DS §7.3), so at 1 MSPS with a 16-SCLK frame
  at 20 MHz the acquisition window is 1000 ns − 625 ns = 375 ns, while
  tTH (acquisition time) is specified 400 ns max over −40…+85 °C
  (DS §6.5). The ensured fRATE = 1 MSPS spec (DS §6.5) implies TI
  guarantees it works anyway — treat 1 MSPS as the hard ceiling and
  don't shave the CS-high time below what a 1 µs cycle provides.
- **Theoretical frame rate exceeds the rated throughput.** 16 SCLK at
  20 MHz (800 ns) + tQUIET (50 ns, DS §6.8) + t1 (10 ns) implies
  ~1.16 MSPS, but fRATE is ensured only to 1 MSPS (DS §6.5). Don't
  plan on >1 MSPS by tightening the gap.
- **Timing diagram trap.** Figure 2 is drawn with SCLK idle high
  (first edge after CS is falling); in that mode "the first leading
  zero may not be set up in time" to be read (DS §7.3). Clock
  idle-low (SPI mode 0) and sample on rising edges instead.
- **Minimum SCLK frequency exists: 10 kHz** (DS §5, pin 4) — don't
  clock arbitrarily slowly; charge droop on the sampling cap
  presumably sets this floor.
- **Shutdown with SCLK running costs 60 µA, not 0.5 µA** (DS §6.5) —
  stop SCLK during shutdown to get the datasheet's headline 5 µW-class
  power-down figure.
- **INL/DNL maxima exist only over temperature ranges**, not at
  25 °C — the room-temperature numbers are typ-only (DS §6.5).
