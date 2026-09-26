# Fuzz seed corpora

Seeds for the libFuzzer harnesses (`firmware/protocol/fuzz/`). Byte
layouts are the harnesses' input grammars — see `fuzz.hpp` for the
event encoding (selector byte `% 5`: 0–2 cell, 3 break, 4 reset; a cell
is selector + period u16 LE + high u16 LE). `scripts/fuzz-run` copies
these into a build-dir work corpus before each run, so the seeds stay
pristine.

## cell/

Raw `(period u16 LE, high u16 LE)` pairs, fed straight to
`decode_cell`.

- `nominal-zero-one` — the two nominal cells (60/19, 60/38 ticks)
- `window-edges` — legality-window boundaries: 43/77 in, 42/78 out,
  high > period
- `tolerance-band` — ±25 % periods (45/60/75) at the 0.32/0.64 ratios

## node/

Prefix: `tele0 tele1 slot_index(u16) slot_bits(u8, mapped to 1+x%16)`,
then events.

- `frame-over-cap` — break, then 2100 nominal cells: past the 2048-bit
  frame cap, the bounded-frame containment case (node.hpp)
- `garbage-cells` — illegal timing, legal cells, break, legal cells
- `reset-mid-frame` — break, cells, brown-out reset, cells, break

## ring/

Prefix: `tele0 tele1 tele2 slot0 slot1 slot2` (slots 0–255, 8 bits
each), then events; a reset event takes one extra node-index byte.

- `three-node-frames` — two clean frames through the chain (echo +
  stamping)
- `faults` — illegal cells, a per-node brown-out, breaks
