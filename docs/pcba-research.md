# PCBA research

Input to DESIGN.md §6; feeds the DSL parts DB's
assembler-stock field (§7). Compiled by research agents; sources cited
inline. Prices USD.

## Verdict

**JLCPCB** for prototypes. Cheapest at 2-off by a wide margin, min 2
assembled boards, instant pricing, all key parts verifiably in-library.
**PCBWay** is the fallback for parts JLCPCB can't stock (1-pc MOQ, true
consignment) at ~2–4× the price. Seeed Fusion (owner's starting point)
is viable but quote-driven with a non-searchable parts library — it
sources from DigiKey/Mouser anyway, so nothing is refused, just
slower/pricier. Elecrow/ALLPCB are email-quote shops with no library to
design against.

## JLCPCB pricing (verified 2026-09-26)

From [JLCPCB's assembly price page](https://jlcpcb.com/help/article/pcb-assembly-price)
and [FAQ](https://jlcpcb.com/help/article/pcb-assembly-faqs):

- **Economic PCBA** (single-side SMT, 2–50 pcs): setup **$8.18**,
  stencil **$1.53**, SMT **$0.0016/joint**, feeder loading **$0 Basic /
  $3.07 per unique Extended BOM line**.
- Standard PCBA (double-side, THT-heavy, fine pitch): setup
  $25.56/$51.12 — avoid if avoidable.
- Assembly MOQ **2**; PCB fab MOQ **5** (spare blanks come free).
- X-ray **$1.64/board** for leadless packages (QFN) at prototype qty.
- **VOEC-registered**: Norwegian 25% VAT collected at checkout, no
  import surprise ([VOEC help](https://jlcpcb.com/help/article/norway-vat-on-e-commerce-voec-rules)).
- Non-library parts: pre-order LCSC parts into Parts Manager (can't be
  shipped back out); true consignment exists but is bureaucratic
  (HK warehouse, contracts, 30%/min-$30 recall fee) — not worth it at
  2-off.

**Estimated 2-off test board** (~60 placements, ~8–10 unique Extended
lines, TSSOP CH32V003 + QFN RP2040): ~$10 fixed + ~$25–30 Extended fees

- ~$5–10 parts + ~$3 X-ray + ~$2 fab → **~$55–80 before shipping**
  (~$10–25 shipping to Norway, unverified at checkout).

## Inventory snapshot (queried 2026-09-26)

Stock and tier as of today; re-check in JLCPCB's quote tool before
ordering — pages are JS-rendered and stock moves.

| Part                          | LCSC C#  | Package  | Tier     | Price (low qty)           | Stock  |
| ----------------------------- | -------- | -------- | -------- | ------------------------- | ------ |
| CH32V003F4P6                  | C5187096 | TSSOP-20 | Extended | $0.286 (1–49), $0.137 @4k | ~9k    |
| CH32V003J4M6                  | C5346354 | SOP-8    | Extended | $0.218                    | ~1.8k  |
| CH32V003A4M6                  | C5346357 | SOP-16   | Extended | $0.269                    | ~1.6k  |
| CH32V003F4U6                  | C5299908 | QFN-20   | Extended | $0.288 (+X-ray fee)       | ~1.9k  |
| RP2040                        | C2040    | QFN-56   | Extended | $0.99–1.93 (+X-ray fee)   | ~54k   |
| SN74LVC1G3157DBVR (TI)        | C10426   | SOT-23-6 | Extended | $0.072                    | ~51k   |
| SN74LVC1G3157DBVR (UMW clone) | C3040658 | SOT-23-6 | Extended | $0.047                    | ~124k  |
| TS5A3166DBVR (TI)             | C353035  | SOT-23-5 | Extended | $0.36                     | ~15.7k |

Note: **none of the project's key ICs are Basic** — every unique BOM
line costs $3.07, so the design rule is *minimize unique parts, reuse
across nodes*.

## Gotchas (design-shaping)

1. **WS2812-class LEDs are "Standard PCBA only"** (moisture bake) and
   force the pricier tier for the whole board — use plain LEDs.
1. TSSOP over QFN where a choice exists (X-ray fee, reworkability).
1. Keep single-side SMT to stay Economic.
1. Some library parts have per-part MOQs (pay for 15, need 2) — check
   each line in the quote tool.
1. ≥17 unique Extended lines flips Standard cheaper than Economic
   ($3.07×17 ≈ $52 > $25.56 + $1.53×lines) — recheck if the BOM grows.
1. Economic assembly panels require mouse-bites, not V-cut.

## Alternatives surveyed

- **PCBWay**: MOQ 1, instant tooling quote + 24h parts quote, true
  consignment with overage rules (0603: min 50+30 over; ICs: 1–5 extra
  — painful at 2-off). Community datapoints put 2-off turnkey at
  ~$150–300. Boards \<50×100 mm must be panelized.
- **Seeed Fusion**: PCBA from 1 pc; all-OPL BOMs historically ~$25
  setup + $0.10–0.30/component (2017–2018 figures, unverified today);
  OPL catalog not publicly searchable — CH32V003/RP2040 coverage
  **unverified**. Sources non-OPL parts from DigiKey/Mouser/TME.
- **Elecrow / ALLPCB**: RFQ-by-email, no library, ~$100–200 for 2-off;
  no reason to prefer over JLCPCB here.
- No disruptive 2025/2026 entrant for cheap prototypes.

## Not verified

- Live per-part stock/MOQ/tier on JLCPCB's own site (jlcsearch mirror
  may lag); TS5A3166 tier assumed Extended.
- Exact Norway shipping price (checkout-only).
- PCBWay/Seeed VOEC registration.
- Current Seeed OPL rates and consignment fees.
