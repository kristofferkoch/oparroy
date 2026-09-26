# Program size estimate — 2026-09-26

Back-of-the-envelope flash/RAM budget for the node firmware, recorded
before the firmware exists so the future can laugh. Constraint: node =
CH32V003F4P6, **16 KB flash, 2 KB SRAM**
(`datasheets/CH32V003/notes/facts.md`); supervisor = RP2040, may cost
freely (DESIGN.md §1) and is not estimated.

## Anchor — measured, not guessed

Probe TU driving the existing `Node` state machine + `decode_cell`
through a 16-cell burst loop, compiled with
`riscv64-none-elf-g++ -Os -march=rv32ec -mabi=ilp32e -ffreestanding -fno-exceptions -fno-rtti`:

- **Protocol core: ~390 B `.text`, ~32 B data** — `on_bit` /
  `on_break` / `on_illegal_cell`, ratio decode, slot rewrite,
  frame-length cap.

## Flash (of 16 KB)

| Component                                                            | Estimate                         |
| -------------------------------------------------------------------- | -------------------------------- |
| Protocol core (state machine, cell codec)                            | ~0.4 KB (measured)               |
| Startup, vectors, RCC (HSI→PLL×2)                                    | ~0.3 KB                          |
| RX plumbing (OPA→TIM2 PWM-input, DMA ch5/7, half-transfer ISR)       | ~0.5 KB                          |
| TX plumbing (TIM1 PWM + DMA compare stream, brake)                   | ~0.4 KB                          |
| vsync latch + double-buffer apply/sample                             | ~0.2 KB                          |
| Watchdog keep-alive strobe                                           | ~0.1 KB                          |
| App I/O union (ADC, button matrix, LED/buzzer PWM, I2C, status LEDs) | ~1.5 KB                          |
| Debug UART (test-board role)                                         | ~0.4 KB                          |
| **Total**                                                            | **~4 KB (3–6 KB range) — ~25 %** |

Excluded by design (DESIGN.md §8): libc (`-nostdlib`), exceptions
(10–40 KB unwinder alone would exceed the whole flash), RTTI.
Calibration: ch32v003fun-class programs with timer+DMA+ADC land at
2–4 KB.

## RAM (of 2 KB)

| Component                                            | Estimate                   |
| ---------------------------------------------------- | -------------------------- |
| RX DMA ring (16 cells × 8 B)                         | 128 B                      |
| TX compare buffer (16 × 2 B)                         | 32 B                       |
| vsync double-buffer                                  | ~16 B                      |
| Ring/DMA subtotal (hard-capped ≤256 B, DESIGN.md §2) | ~180 B                     |
| `Node` object + app state (debounce, ADC)            | ~64 B                      |
| Stack (shallow calls, 1–2 ISR levels)                | 256–512 B                  |
| **Total**                                            | **~0.5–0.8 KB — ~30–40 %** |

## Verdict (2026-09-26)

Both fit with ~2× headroom. RAM is the tighter axis; the §2 hard cap of
256 B on ring DMA buffers is what keeps it boring. Main risk is not the
protocol but growth in the app-I/O union — §2 pins one image for all
node types (personality by type byte), so capsense and I2C
accelerometer paths all ship in every node.

## Future laughter log

When the real numbers exist, append them here with dates:

- (first linked node image): — KB flash, — KB RAM
