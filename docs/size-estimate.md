# Program size estimate

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
| RX capture rings (16 cells × 2 × 2 B)                | 64 B                       |
| TX compare DMA rings (16 cells × 2 × 2 B)            | 64 B                       |
| Cut-through FIFO (128 cells × 2 B)                   | 256 B                      |
| vsync double-buffer                                  | ~16 B                      |
| Ring/DMA subtotal (hard-capped ≤256 B, DESIGN.md §2) | 128 B                      |
| `Node` object + app state (debounce, ADC)            | ~64 B                      |
| Stack (shallow calls, 1–2 ISR levels)                | 256–512 B                  |
| **Total**                                            | **~0.6–0.9 KB — ~30–45 %** |

## Cut-through timing closure

The cut-through FIFO replaces the store-and-forward frame queue as the
TX-side rate matcher. Its depth is set by the worst-case fill the
re-emitted break forces, not by the CPU burst alone:

- **Rate drift**: upstream and local HSI each span ±2.2 % over
  −40–85 °C (facts.md, DS0 §3.3.6), so a node measures the upstream cell
  period at 60 × (1 ± 4.4 %) local ticks — a pre-sized ENUM frame
  (840 bits — 8 × 105: occupancy marker + 96-bit UNIID + type byte,
  DESIGN.md §2) drifts ≈ 37 cells.
- **Break overlap**: on_break re-arms a tx_break_cells = 48 idle run
  before the next frame's bits play, so those bits accumulate while the
  idles drain (~50 cells for an ENUM at the worst skew), then the rest
  of the frame drifts (~35 cells) — ≈ 85 cells steady-state.
- **RX burst**: rx_poll drains ≤ 16 captures into the FIFO per poll —
  +16 cells transient.

128 cells (256 B) covers ≈ 100 cells of worst case with margin — the
same footprint the store-and-forward frame queue occupied. Overflow is
reachable only for over-long frames (≳1.8 kbit at the extreme skew, well
past the 840-bit pre-sized ENUM; the 2048-bit cap mutes the node either
way) and mutes like the store-and-forward rung: drop, never corrupt a
cell mid-frame. The per-bit loop's CPU cost is strictly below the
store-and-forward rung's — cut-through enqueues a compare where
store-and-forward bit-packed a frame queue — so the §2 ~10 cycles/bit
decode budget stays the binding term; the exact count lands with
on-target measurement (the test board).

## Verdict

Both fit with ~2× headroom. RAM is the tighter axis; the §2 hard cap of
256 B on ring DMA buffers is what keeps it boring. Main risk is not the
protocol but growth in the app-I/O union — §2 pins one image for all
node types (personality by type byte), so capsense and I2C
accelerometer paths all ship in every node.

## Future laughter log

When the real numbers exist, append them here:

- First linked node image (bring-up slice: startup/vectors/RCC,
  keep-alive strobe, `verify_failed` hook — no protocol, RX/TX, vsync,
  or app I/O yet): **604 B flash (3.7 % of 16 KB), 0 B RAM** at -Os.
  Breakdown: vector table 152 B, reset + .data/.bss init 116 B,
  `node_main` (RCC + strobe + heartbeat) 184 B, failure path 100 B,
  memcpy 52 B — the mul/div runtime is gc-sections'd out until
  something divides. Against the ~0.4 KB estimated for the landed
  lines (startup/vectors/RCC 0.3 + strobe 0.1): the delta is the
  never-estimated failure path and heartbeat. The envelope's real
  miss was process, not code — the build defaulted to -O0 (1228 B)
  until -Os was settled (DESIGN.md §8). Verdict and headroom
  unchanged.
- Personality firmware (the real ENUM stamp: ESIG UNIID + option-byte
  Data0 type byte, `firmware/node/personality.cpp`, replacing the
  bring-up placeholder): the full image — protocol core, RX/TX paths,
  vsync latch, strobe, personality — measures **2828 B flash
  (17.3 % of 16 KB), 434 B RAM** at -Os. The personality slice itself
  is +184 B flash / +18 B RAM over the same image with the placeholder
  (2644 B): three ESIG word reads, the Data0 inverse check, the
  14-byte pack, the config VERIFY. The placeholder number also closes
  the loop on the plumbing estimates: 2644 B against ~1.9 KB estimated
  for those same lines (protocol 0.4 + startup 0.3 + RX 0.5 + TX 0.4 +
  vsync 0.2 + strobe 0.1) — the ~0.7 KB delta is again the
  never-estimated failure path and heartbeat plus estimate optimism on
  the RX/TX glue. RAM tracks well: 434 B against ~460 B estimated for
  the landed lines (rings 384 B + vsync 16 B + `Node`). Remaining
  unbuilt: the app-I/O union (~1.5 KB) and debug UART (~0.4 KB) —
  13.5 KB of flash stays free for them, so the ~2× headroom verdict
  holds. (The meson.build -Os comment's "642 B" predated this log's
  604 B bring-up entry — the same bring-up image measured two commits
  apart — and then went stale as RX/TX landed; the comment now points
  here instead of carrying numbers.)
