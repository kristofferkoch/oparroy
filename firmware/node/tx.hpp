#pragma once

// The TX streaming path's MMIO glue (tx.cpp, DESIGN.md §2) — distinct
// from firmware/protocol/tx.hpp, the host-testable store-and-forward
// sequencer this glue drains.

#include "../protocol/node.hpp" // TxAction

// Configure TIM1's PWM channels, the BKIN brake, and the compare DMA
// rings; call once from node_main before the loop.
void tx_init();

// Feed one decoder result to the TX sequencer (rx.cpp's drain loop —
// see its comment for which decoder calls map here vs to tx_break()).
void tx_push(oparroy::TxAction action);

// The decoder delivered a break (the in-stream marker or the on_silence
// backstop): close the sequencer's accumulating frame.
void tx_break();

// Drain the sequencer into the DMA rings, keeping both channels'
// compare streams identical and ahead of the wire. Non-blocking; call
// every loop iteration.
void tx_poll();
