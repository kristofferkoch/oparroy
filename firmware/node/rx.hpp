#pragma once

// The RX capture path's MMIO glue (rx.cpp, DESIGN.md §2) — distinct
// from firmware/protocol/rx.hpp, the host-testable burst decoder this
// glue feeds.

// Configure the OPA comparator, TIM2's PWM-input capture, and the DMA
// rings; call once from node_main before the loop.
void rx_init();

// Drain the capture rings into the burst decoder and apply the §3
// source-flip policy. Non-blocking; call every loop iteration.
void rx_poll();
