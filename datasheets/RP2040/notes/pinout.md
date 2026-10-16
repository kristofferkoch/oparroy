# RP2040 — QFN-56 pinout

Pin-level facts for the RP2040 supervisor capture (the DSL pin map).
Source: the vendored RP2040 datasheet
(`rp2040-datasheet-2025-02-20.pdf`, release of 20 February 2025,
build 3184e62), cited as (DS §x.y). Package: QFN-56, 7×7 mm with a
central ground pad (reduced ePad) (DS §1.4.1, Figure 3; §5.5.1,
Figure 170).

## Pad → name table (DS §5.5.2.2, Tables 615–621)

| Pad | Name        | Type                  | Power domain     | Reset state |
| --- | ----------- | --------------------- | ---------------- | ----------- |
| 1   | IOVDD       | power                 | —                | —           |
| 2   | GPIO0       | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 3   | GPIO1       | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 4   | GPIO2       | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 5   | GPIO3       | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 6   | GPIO4       | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 7   | GPIO5       | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 8   | GPIO6       | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 9   | GPIO7       | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 10  | IOVDD       | power                 | —                | —           |
| 11  | GPIO8       | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 12  | GPIO9       | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 13  | GPIO10      | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 14  | GPIO11      | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 15  | GPIO12      | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 16  | GPIO13      | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 17  | GPIO14      | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 18  | GPIO15      | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 19  | TESTEN      | Digital In            | IOVDD            | Pull-Down   |
| 20  | XIN         | Analogue (XOSC)       | IOVDD            | —           |
| 21  | XOUT        | Analogue (XOSC)       | IOVDD            | —           |
| 22  | IOVDD       | power                 | —                | —           |
| 23  | DVDD        | power                 | —                | —           |
| 24  | SWCLK       | Digital In (FT)       | IOVDD            | Pull-Up     |
| 25  | SWD         | Digital IO (FT)       | IOVDD            | Pull-Up     |
| 26  | RUN         | Digital In (FT)       | IOVDD            | Pull-Up     |
| 27  | GPIO16      | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 28  | GPIO17      | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 29  | GPIO18      | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 30  | GPIO19      | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 31  | GPIO20      | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 32  | GPIO21      | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 33  | IOVDD       | power                 | —                | —           |
| 34  | GPIO22      | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 35  | GPIO23      | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 36  | GPIO24      | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 37  | GPIO25      | Digital IO (FT)       | IOVDD            | Pull-Down   |
| 38  | GPIO26/ADC0 | Digital IO / Analogue | IOVDD / ADC_AVDD | Pull-Down   |
| 39  | GPIO27/ADC1 | Digital IO / Analogue | IOVDD / ADC_AVDD | Pull-Down   |
| 40  | GPIO28/ADC2 | Digital IO / Analogue | IOVDD / ADC_AVDD | Pull-Down   |
| 41  | GPIO29/ADC3 | Digital IO / Analogue | IOVDD / ADC_AVDD | Pull-Down   |
| 42  | IOVDD       | power                 | —                | —           |
| 43  | ADC_AVDD    | power                 | —                | —           |
| 44  | VREG_VIN    | power                 | —                | —           |
| 45  | VREG_VOUT   | power                 | —                | —           |
| 46  | USB_DM      | USB IO                | USB_VDD          | —           |
| 47  | USB_DP      | USB IO                | USB_VDD          | —           |
| 48  | USB_VDD     | power                 | —                | —           |
| 49  | IOVDD       | power                 | —                | —           |
| 50  | DVDD        | power                 | —                | —           |
| 51  | QSPI_SD3    | Digital IO            | IOVDD            | —           |
| 52  | QSPI_SCLK   | Digital IO            | IOVDD            | Pull-Down   |
| 53  | QSPI_SD0    | Digital IO            | IOVDD            | —           |
| 54  | QSPI_SD2    | Digital IO            | IOVDD            | —           |
| 55  | QSPI_SD1    | Digital IO            | IOVDD            | —           |
| 56  | QSPI_CSn    | Digital IO            | IOVDD            | Pull-Up     |
| 57  | GND         | power (central pad)   | —                | —           |

Notes on the table:

- **Pad 57 is the central exposed pad and the chip's single GND
  connection** — the 56 peripheral pads carry no GND pin (DS §5.5.2.2
  Table 621, "Common ground connection via central pad").
- **QSPI naming mismatch:** the datasheet pin list calls pad 56
  `QSPI_CSn`, while the hardware-design app note and the boot
  documentation call the same signal `QSPI_SS`. See
  [quirks.md](quirks.md).
- The app note's minimal design wires the flash to the QSPI pins in
  this pad order; see [flash-crystal.md](flash-crystal.md).
- `TESTEN` (pad 19): "Factory test mode pin. Tie to GND." (DS §1.4.2
  Table 1).
- `RUN` (pad 26): "Global asynchronous reset pin. Reset when driven
  low, run when driven high. If no external reset is required, this
  pin can be tied directly to IOVDD." (DS §1.4.2 Table 1).
- `XIN` may be driven by a single-ended CMOS square wave instead of a
  crystal, with XOUT disconnected; the USB bootloader requires 12 MHz
  either way (DS §1.4.2 Table 1).
- `USB_DP`/`USB_DM`: bus pull-ups/pull-downs are internal; **27 Ω
  series termination on each pin is required for USB operation** (DS
  §5.5.2.2 Table 620; routing details in
  [power-design.md](power-design.md)).
- Power domains: IOVDD nominal 1.8–3.3 V; DVDD nominal 1.1 V (from
  VREG_VOUT or an external supply); VREG_VIN 1.8–3.3 V; VREG_VOUT
  1.1 V, 100 mA max; USB_VDD and ADC_AVDD nominal 3.3 V (DS §1.4.2
  Tables 1/617–621). Absolute max: IOVDD −0.5…3.63 V, pin voltage
  −0.5…IOVDD+0.5 V (DS §5.5.3.1 Table 622).

## GPIO function multiplexing (DS §1.4.3, Table 2)

F5 = SIO (software), F6 = PIO0, F7 = PIO1 on all GPIO0–29. F1–F4 and
F8/F9 below; "—" = no function. GPIO26–29 are also ADC inputs
(next section).

| GPIO | F1       | F2        | F3       | F4     | F8           | F9            |
| ---- | -------- | --------- | -------- | ------ | ------------ | ------------- |
| 0    | SPI0 RX  | UART0 TX  | I2C0 SDA | PWM0 A | —            | USB OVCUR DET |
| 1    | SPI0 CSn | UART0 RX  | I2C0 SCL | PWM0 B | —            | USB VBUS DET  |
| 2    | SPI0 SCK | UART0 CTS | I2C1 SDA | PWM1 A | —            | USB VBUS EN   |
| 3    | SPI0 TX  | UART0 RTS | I2C1 SCL | PWM1 B | —            | USB OVCUR DET |
| 4    | SPI0 RX  | UART1 TX  | I2C0 SDA | PWM2 A | —            | USB VBUS DET  |
| 5    | SPI0 CSn | UART1 RX  | I2C0 SCL | PWM2 B | —            | USB VBUS EN   |
| 6    | SPI0 SCK | UART1 CTS | I2C1 SDA | PWM3 A | —            | USB OVCUR DET |
| 7    | SPI0 TX  | UART1 RTS | I2C1 SCL | PWM3 B | —            | USB VBUS DET  |
| 8    | SPI1 RX  | UART1 TX  | I2C0 SDA | PWM4 A | —            | USB VBUS EN   |
| 9    | SPI1 CSn | UART1 RX  | I2C0 SCL | PWM4 B | —            | USB OVCUR DET |
| 10   | SPI1 SCK | UART1 CTS | I2C1 SDA | PWM5 A | —            | USB VBUS DET  |
| 11   | SPI1 TX  | UART1 RTS | I2C1 SCL | PWM5 B | —            | USB VBUS EN   |
| 12   | SPI1 RX  | UART0 TX  | I2C0 SDA | PWM6 A | —            | USB OVCUR DET |
| 13   | SPI1 CSn | UART0 RX  | I2C0 SCL | PWM6 B | —            | USB VBUS DET  |
| 14   | SPI1 SCK | UART0 CTS | I2C1 SDA | PWM7 A | —            | USB VBUS EN   |
| 15   | SPI1 TX  | UART0 RTS | I2C1 SCL | PWM7 B | —            | USB OVCUR DET |
| 16   | SPI0 RX  | UART0 TX  | I2C0 SDA | PWM0 A | —            | USB VBUS DET  |
| 17   | SPI0 CSn | UART0 RX  | I2C0 SCL | PWM0 B | —            | USB VBUS EN   |
| 18   | SPI0 SCK | UART0 CTS | I2C1 SDA | PWM1 A | —            | USB OVCUR DET |
| 19   | SPI0 TX  | UART0 RTS | I2C1 SCL | PWM1 B | —            | USB VBUS DET  |
| 20   | SPI0 RX  | UART1 TX  | I2C0 SDA | PWM2 A | CLOCK GPIN0  | USB VBUS EN   |
| 21   | SPI0 CSn | UART1 RX  | I2C0 SCL | PWM2 B | CLOCK GPOUT0 | USB OVCUR DET |
| 22   | SPI0 SCK | UART1 CTS | I2C1 SDA | PWM3 A | CLOCK GPIN1  | USB VBUS DET  |
| 23   | SPI0 TX  | UART1 RTS | I2C1 SCL | PWM3 B | CLOCK GPOUT1 | USB VBUS EN   |
| 24   | SPI1 RX  | UART1 TX  | I2C0 SDA | PWM4 A | CLOCK GPOUT2 | USB OVCUR DET |
| 25   | SPI1 CSn | UART1 RX  | I2C0 SCL | PWM4 B | CLOCK GPOUT3 | USB VBUS DET  |
| 26   | SPI1 SCK | UART1 CTS | I2C1 SDA | PWM5 A | —            | USB VBUS EN   |
| 27   | SPI1 TX  | UART1 RTS | I2C1 SCL | PWM5 B | —            | USB OVCUR DET |
| 28   | SPI1 RX  | UART0 TX  | I2C0 SDA | PWM6 A | —            | USB VBUS DET  |
| 29   | SPI1 CSn | UART0 RX  | I2C0 SCL | PWM6 B | —            | USB VBUS EN   |

### SPI0 / SPI1 pin choices distilled

- **SPI0:** RX on GPIO0/4/16/20, CSn on GPIO1/5/17/21, SCK on
  GPIO2/6/18/22, TX on GPIO3/7/19/23.
- **SPI1:** RX on GPIO8/12/24/28, CSn on GPIO9/13/25/29, SCK on
  GPIO10/14/26, TX on GPIO11/15/27.

## ADC channel mapping (DS §1.4.3 Table 2, §4.9.2)

- ADC channel 0–3 ↔ GPIO26/27/28/29 (pads 38/39/40/41), selected by
  `CS.AINSEL` values 0–3; **AINSEL = 4 selects the internal
  temperature sensor** (DS §4.9.2).
- The ADC pins share the IOVDD digital domain and ADC_AVDD analogue
  supply (pad 43) (DS §5.5.2.2 Table 615).

## Serial-wire debug

SWCLK = pad 24, SWD = pad 25, both fault-tolerant, pull-up at reset
(DS §5.5.2.2 Table 618). SWD gives debug access to both cores and
code download (DS §1.4.2 Table 1).
