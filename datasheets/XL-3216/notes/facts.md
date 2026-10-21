# XINGLIGHT XL-3216 (top-emitting 1206) — facts

Top-emitting 1206 LED series (3.2 × 1.6 × 0.8 mm), used by the CI
board's tile status LEDs (DESIGN.md §4.1, `design/ci_tiles.py` — the
viewer stands over the component side of the flat bench board). The
node board uses the same series' reverse-mount `-FB` siblings
(`LedRev1206`, parts DB `led-rev1206-*`), which emit through the
bottom lens into a routed board hole; the parts here are the plain
forward-mount counterparts on the stock `LED_SMD:LED_1206_3216Metric`
land pattern. Documents on disk (per-color data sheets, no revision
marking — PDF dates in the filenames):

- `XL-3216SURC-datasheet-2025-12-29.pdf` — red, LCSC **C965822**
- `XL-3216UYC-datasheet-2025-11-03.pdf` — yellow, LCSC **C965824**
- `XL-3216SYGC-datasheet-2025-11-03.pdf` — yellow-green, LCSC **C965826**

## Optical-electrical parameters (per-color datasheet p.3, IF = 20 mA)

| Part        | Role (§4.1)         | λd (nm) | VF (V)  | Iv (mcd) | Viewing angle |
| ----------- | ------------------- | ------- | ------- | -------- | ------------- |
| XL-3216SURC | power (red)         | 615–630 | 1.9–2.2 | 80–240   | 120°          |
| XL-3216UYC  | working (yellow)    | 585–595 | 1.8–2.4 | 80–240   | 120°          |
| XL-3216SYGC | link (yellow-green) | 565–575 | 1.9–2.4 | 50–100   | 120°          |

All three are 3.3 V-drivable: worst-case VF 2.4 V at 20 mA, and the
CI tiles drive 1.3 mA (power/working) / 2.5 mA (link pair) where VF
sits ≈2 V — the `StatusLeds` generator's 2.0/2.1 V stand-ins. The
yellow-green is again the only drivable "green" — the series' 525 nm
true green (XL-3216UGC) carries the same too-high VF as its -FB
sibling (parts DB `led-rev1206-yellowgreen` note). Iv bins and VF
grading codes are on p.4 of each sheet (±10% brightness, ±0.1 V
grading error); wavelength grading ±1 nm.

## Absolute maximum ratings (per-color datasheet p.3, identical across the three)

- PD 50 mW; IF 20 mA continuous, IFP 80 mA peak (pulse ≤ 0.1 ms, duty
  ≤ 1/10); VR 5 V; ESD 2 kV; −40…+85 °C operating/storage; MSL 3
  (p.1 characteristics); reflow 260 °C ≤ 6 s.

The antiparallel link pair (Du/Dd) reverse-biases the dark LED at
≈3.3 V minus the lit one's VF — inside the 5 V VR rating, same as the
node board's -FB pair.
