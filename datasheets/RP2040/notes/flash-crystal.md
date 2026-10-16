# Hardware design with RP2040 — flash, crystal, reset/boot extraction

Continuation of [power-design.md](power-design.md): the remaining
minimal-design-example sections of Raspberry Pi Ltd's application note
**"Hardware design with RP2040"**, Release 2 (build date 20/08/2026,
build 0444806419d7), on disk as
`hardware-design-with-rp2040-release2.pdf`, cited as (AN §x.y). This
file covers the QSPI flash (AN §2.2, §2.6), the crystal oscillator
(AN §2.3, §2.3.1), and the reset/BOOTSEL wiring the supervisor
capture needs. DS citations are the vendored RP2040 datasheet
(`rp2040-datasheet-2025-02-20.pdf`).

## Flash storage (AN §2.2)

- RP2040 boots and executes from an external **quad-SPI flash**. The
  minimal design uses a **Winbond W25Q128JVS** (128 Mbit / 16 MB) —
  **the largest size RP2040 supports**; a smaller, cheaper part is
  fine when the application needs less (AN §2.2).
- Wire RP2040's QSPI pins **directly to the flash with short
  connections** — the bus is high-frequency and regularly active;
  short runs protect signal integrity and cut crosstalk into
  neighbours (AN §2.2).
- **QSPI_SS (pad 56, `QSPI_CSn` in the datasheet) carries two
  resistors:**
  - **R2, a 10 kΩ pull-up to 3.3 V.** The flash requires its
    chip-select input to sit at its own 3.3 V supply level while
    powering up, or it may misbehave. RP2040's QSPI_SS pin does
    default to a pull-up, but its state is not guaranteed during the
    switch-on window. The app note marks R2 **DNF** because "with
    this particular flash device" (W25Q128JVS) the external pull-up
    proved unnecessary — **with a different flash it may become
    essential, so the footprint stays** (AN §2.2). The Winbond
    W25Q16JV datasheet independently requires /CS to track VCC at
    power-up, suggesting a pull-up to do it (W25Q16JV DS §4.1, §10.3) —
    **fit the 10 kΩ for W25Q16JV.**
  - **R1, a 1 kΩ to the `USB_BOOT` header (J2).** QSPI_SS is a boot
    strap: sampled low during the boot sequence, RP2040 falls back to
    **BOOTSEL mode** (USB mass-storage device). Shorting J2 pulls
    QSPI_SS to ground; a subsequent reset (e.g. toggling RUN) restarts
    in BOOTSEL instead of running from flash. **R1 is not optional** —
    it lets RP2040's QSPI_SS output safely over-drive the applied
    pull-down once booting starts (AN §2.2).
- Place both resistors **close to the flash chip** (AN §2.2).

## Supported flash chips (AN §2.6)

- The bootrom probes flash with an **03h serial read, 24-bit
  addressing, ~1 MHz clock**, cycling through all four CPOL/CPHA
  combinations until the second-stage CRC32 checks out. XIP then works
  with **any chip supporting 03h read with 24-bit addressing — most
  25-series parts** (AN §2.6).
- To be programmable through the bootrom routines, the flash must also
  answer **02h page program (256-byte), 05h status-register read, 06h
  write-enable, 20h 4 kB sector erase** (AN §2.6).
- Caution with continuous-read XIP modes (e.g. Winbond quad-IO
  continuous read): if RP2040 resets without power-cycling the flash,
  the flash may not answer the bootrom probe. The bootrom always
  issues a best-effort XIP-exit sequence before its 03h read (32
  clocks CSn=1/IO=0000, 32 clocks CSn=0/IO=1111, CSn=1, then 16 clocks
  CSn=0/MOSI=1); a flash that does not respond to it must never enter
  command-less continuous read, or the chip cannot recover from an
  internal reset (AN §2.6).

## Crystal oscillator (AN §2.3, §2.3.1)

- RP2040 runs from an internal oscillator, but its frequency is
  uncontrolled across chips, voltage, and temperature — **anything
  needing exact frequencies (USB above all) needs an external source**
  (AN §2.3).
- Two options: a CMOS square wave (IOVDD level) into **XIN**, or a
  **12 MHz crystal across XIN/XOUT** — the preferred, cheap, accurate
  option (AN §2.3). The USB bootloader requires 12 MHz either way (DS
  §1.4.2 Table 1).
- **Recommended crystal: Abracon ABM8-272-T3** — the same part as on
  Raspberry Pi Pico; the surrounding circuit is tuned for it. Key
  specs (AN §2.3, §2.3.1 Table 1): 12.000 MHz fundamental-AT,
  ±30 ppm tolerance, ±30 ppm stability, **ESR max 50 Ω**, shunt C0 max
  3 pF, **load capacitance CL 10 pF**, drive level 10–200 µW, −40…+85
  °C.
- **Load capacitors C2 = C3 = 15 pF** (C0G, 50 V, 5 % per the AN §2.5
  schematic). They appear in series across the crystal: 15/2 = 7.5 pF,
  plus an assumed **3 pF of PCB/pin parasitic** = 10.5 pF ≈ the 10 pF
  target. Keep XIN/XOUT tracks short — parasitics directly shift the
  load (AN §2.3).
- **Series resistor R5 = 1 kΩ** (1 %, 63 mW, M1005/0402 per the AN
  §2.5 schematic) **prevents over-driving the crystal at IOVDD =
  3.3 V**. At lower IOVDD the XIN/XOUT drive is weaker and R5 must
  shrink; any deviation from this circuit or from 3.3 V IOVDD "will
  require extensive testing" (AN §2.3).
- The crystal oscillator runs from IOVDD; the Abracon part plus this
  damping resistor are **tuned for 3.3 V operation** — retune for any
  other IO voltage (AN §2.3.1).

## Reset (RUN) and BOOTSEL wiring

- **RUN (pad 26) is the global asynchronous reset, active low.** "If
  no external reset is required, this pin can be tied directly to
  IOVDD" (DS §1.4.2 Table 1). It carries an internal pull-up at reset
  (DS §5.5.2.2 Table 619). On Raspberry Pi Pico, RUN is pulled high on
  the module and a push button (SW1) pulls it low to reset (AN §3.5).
- **TESTEN (pad 19): tie to GND** (DS §1.4.2 Table 1).
- BOOTSEL entry needs no dedicated pin: ground QSPI_SS through the 1
  kΩ R1 at reset, per the flash section above. A design that wants
  button-free reflashing can drive QSPI_SS low from a supervisor GPIO
  through a similar series resistor, or simply expose the J2 header
  pair / test pads.
