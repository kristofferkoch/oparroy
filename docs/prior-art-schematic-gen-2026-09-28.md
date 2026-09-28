# Prior art: automatic schematic generation

Research date 2026-09-28, card T21. Question: what should oparroy's
design-review views look like beyond the T7a dot dump (DESIGN.md §7),
and what do we build vs borrow. Sources linked inline.

## 1. The requirement

DESIGN.md §7 sets the target: "abstraction-level block views in the
Verilog-debugger sense" for human review. The dot dump
(`src/oparroy/dsl/dot.py`) is the minimal rung: a flat bipartite graph —
record node per part, ellipse per net — that Graphviz renders. It
flattens hierarchy, shows no signal flow, no port direction, no symbol
graphics. Fine for eyeballing a ten-part subcircuit; useless for
reviewing a board.

Two view levels fall out of the DSL's own structure:

- **Block view** — subcircuit instances as boxes, ports / port arrays /
  bundles as their interface pins, ring wiring as thick lines. Answers
  the review question "is the board composed right."
- **Detail view** — one subcircuit's parts and nets, signal flow
  left-to-right, power nets as stubs. Answers "is this subcircuit wired
  right."

The DSL knows things a generic layout tool doesn't: `Part.path`
hierarchy metadata, KiCad `PinType` (input/output/power) per symbol pin,
the `power:`-symbol convention marking driven nets, typed parts. View
generation sits on that knowledge — that is the build half of §4.

## 2. Tool survey

### yosys `show`

[`show`](https://yosyshq.readthedocs.io/projects/yosys/en/0.35/cmd/show.html)
emits a Graphviz dot graph of the selected design; dot lays it out.
Fine for a handful of RTL cells; beyond that the layout has no schematic
conventions (no port sides, no symbol shapes, gates as labeled boxes)
and collapses into spaghetti — it is a debugging aid you steer with
`select` filters, not a review document. Same league as our dot dump.

### netlistsvg

[netlistsvg](https://github.com/nturley/netlistsvg) draws SVG schematics
from yosys JSON netlists. Architecture: cell→symbol **skin files** (SVG
templates with named port anchor points), layout by
[elkjs](https://github.com/kieler/elkjs) — the JavaScript port of
Eclipse ELK — running a Sugiyama-family layered layout with **port
constraints and orthogonal edge routing**. Ships a digital skin and an
analog skin (resistors, BJTs, vcc/gnd symbols). Input is flat JSON; no
hierarchy.

Status: v1.0.2 released 2020-12-12, npm registry untouched since
2022-05 — effectively unmaintained, though packaged in nixpkgs. It
remains what yosys-adjacent tooling reaches for (TerosHDL's schematic
viewer pipes yosys → netlistsvg).

Takeaways: ELK-layered plus skins produces recognizably
schematic-looking output; the skin indirection — symbol templates with
port anchors — is the right shape for symbol graphics. The
unmaintained-JS-dependency is the cost.

### d3-hwschematic

[d3-hwschematic](https://github.com/Nic30/d3-hwschematic): d3.js + ELK,
browser viewer, **hierarchy as expand/collapse boxes** — submodules are
nested containers with port anchors on their boundary, which is exactly
the block-view interaction model. ELK does nested/hierarchical layout
natively. Takeaway: hierarchy-in-layout is solved in ELK; the
expand/collapse viewer is a d3 concern a static review SVG doesn't
need.

### SKiDL `generate_schematic`

The most informative datapoint, because it attacks the same problem at a
harder setting: emitting **editable** `.kicad_sch`. devbisme's build log
[SKiDL Has Schematics! (2023-07-14)](https://devbisme.github.io/skidl/generating-editable-schematics-2023-07-14.html)
is the honest account: about 18 months (2021-11 → 2023-07) of a skilled
author's effort from contributed prototype to release 1.2.0. What it
took:

- **Placement**: force-directed (net attraction vs overlap repulsion on
  an alpha schedule), parts grouped into connected/floating blocks,
  Kernighan-Lin orientation optimization, a retry loop inflating part
  bounding boxes 1.25× per attempt until routing succeeds.
- **Routing**: PCB-style — coarse routing cells derived from part
  bounding-box edges, global routing with per-edge capacity, terminal
  assignment, greedy switchbox detailed routing, then "beautifier"
  passes (stub→straight, dogleg→L, cycle removal).
- **Verdict after all that**: "the quality of the schematics still
  needs improvement." And the structural observation that drove most of
  2023's rework: **"you can't route your way out of a bad placement."**

Takeaways: bespoke placement+routing is a research project with a
mediocre ceiling — do not build one. Also note what SKiDL targeted:
*editable* schematics in eeschema, much harder than a static review
SVG, because the output must survive human round-trip editing.

### KiCad netlist import

There is no netlist→schematic path in KiCad at all: eeschema imports no
netlists. pcbnew's netlist import drops new footprints in a pile at the
origin for the human to place
([KiCad forums](https://forum.kicad.info/t/reloading-footprints-in-pcbnew/1089));
the old "place footprints automatically" was an unstack helper, not
placement. So DESIGN.md §7's KiCad-stays-layout-only division also
means **nothing borrowable from KiCad itself** for schematic drawing.

### Commercial ESL / reverse-engineering tools

The commercial niche that does netlist→schematic is reverse engineering:
[ScanCAD's Schematic Generation Module](https://scancad.net/schematic-generation-module/)
ingests OrCAD/PADS/DxDesigner/EDIF/IPC-D-356 netlists and emits
"intelligent" schematics — sold as a viewer/debugger with human cleanup
expected, not as review-grade drawings. Mainstream ESL design entry
(Mentor/Cadence/Altium) draws nothing automatically at schematic level;
decades of attempts have produced no tool whose output experienced
engineers accept without rework. The market verdict matches SKiDL's:
full schematic auto-drawing at human aesthetic standards is unsolved.

## 3. The graph-drawing literature underneath

- **Layered (Sugiyama) framework** — the standard for directed
  node-link diagrams with flow: cycle removal → layer assignment →
  crossing minimization → coordinate assignment → edge routing. The
  [PGF/TikZ graph-drawing manual's layered-layout
  chapter](https://tikz.dev/gd-layered) is a good compact spec.
  Crossing minimization is NP-hard; practice is barycenter/median
  sweeps. Brandes–Köpf (2001) is the standard fast coordinate
  assignment. Graphviz `dot` (Gansner–Koutsofios–North–Vo 1993), ELK
  Layered, and grandalf all implement this family.
- **Orthogonal drawing** — bend minimization as a flow problem
  (Tamassia 1987) inside the topology–shape–metrics pipeline: the
  classic way to get the 90° wiring schematics want.
- **Ports and hyperedges** — what separates a *schematic* layout engine
  from a graph drawer: pins live at fixed points on symbol outlines
  (port constraints), and a net is a hyperedge touching N pins, not a
  set of pairwise edges. [ELK
  Layered](https://eclipse.dev/elk/reference/algorithms/org-eclipse-elk-layered.html)
  handles both natively (port sides, orthogonal and hyperedge routing) —
  the concrete capability netlistsvg and d3-hwschematic borrow. ELK's
  architecture paper: [arXiv:2311.00533](https://arxiv.org/html/2311.00533v1).
- **What the literature does not solve: schematic semantics.** No
  layout engine knows that GND points down, that series passives chain
  on a horizontal signal path, that a current mirror wants symmetry,
  that a decoupling cap is a stub off a rail. That gap is the
  difference between a valid drawing and a readable schematic, and it is
  why auto-drawn analog schematics read as wrong even when the topology
  is right. At *block* level the gap barely matters — boxes and thick
  wires are the abstraction. At *detail* level we get partway with
  pin-type direction hints and power-stub collapsing, and accept the
  rest.

## 4. Build vs borrow — recommendation

**Borrow the layout engine. Build the view extraction. Never build a
placement/routing engine.**

Layout-engine candidates, ranked for oparroy:

1. **grandalf** ([GitHub](https://github.com/bdcht/grandalf),
   [PyPI](https://pypi.org/project/grandalf/)) — pure-Python Sugiyama
   layered layout, uv-installable, no runtime beyond Python,
   deliberately hackable ("simple enough to tweak and hack any
   part"). Two caveats verified against the 0.8 source (2026-09-28):
   **no orthogonal router** — the shipped edge routers are
   straight-line, spline, and rounded-corner, so the 90° wiring is the
   piece we'd patch in — and the license is **GPLv2 | EPLv1**: take
   EPL-1.0 and depend on it unmodified via uv, because distributing a
   patched copy drags our patches under EPL (patching stays feasible,
   but as an upstreamed or separately-published change, never vendored
   into this MIT tree). Latest release 0.8 (2023-01) — quiet, like
   netlistsvg; pure Python over tiny graphs makes that low-risk.
   Slower and less featured than ELK, but our graphs are tiny: a board
   is tens of subcircuit boxes, a subcircuit is tens of parts. Fits
   the own-the-IR philosophy (§7): a pure-Python Sugiyama takes
   schematic-specific rules (port sides, power stubs) where patching
   ELK does not.
1. **ELK via elkjs** — the capability leader (ports, hyperedges,
   hierarchy, orthogonal routing — everything netlistsvg uses), but
   drags Node.js into a Python pipeline; provisionable via the flake,
   still friction, and netlistsvg itself is unmaintained. The fallback
   if grandalf's output quality disappoints, and the only candidate
   with orthogonal routing built in.
1. **Graphviz dot** — already the baseline. No real port support, weak
   hyperedges; `splines=ortho` exists but fights record nodes. Keep for
   the flat dump; don't extend it.

Build (oparroy-owned, deliberately thin):

- **View extraction over the IR** — the semantics no engine has:
  - Block view: one box per subcircuit instance (`Part.path` already
    carries the metadata), ports / port arrays / bundles as box pins;
    bundles render as single thick wires.
  - Detail view: direction hints from KiCad `PinType` (inputs left,
    outputs right) to seed layering; `power:`-symbol nets collapse to
    named stubs (SKiDL's floating-group trick); series passives
    optionally collapse into labeled wire segments.
  - Port direction tags (T7bd's planned `Input`/`Output`/`InOut` on
    ports, KANBAN.md) are the block view's natural input — the view
    work lands after or with T7bd.
- **Symbol graphics**: reuse KiCad symbol geometry. `kicadlib.py`
  parses pins today, not graphics — extending it to read symbol drawing
  primitives yields netlistsvg-style skins for free, from the same
  libraries the netlist emitter validates against. Prior art exists:
  SKiDL's `generate_svg()` already converts KiCad library symbols into
  netlistsvg skins — the conversion is proven; ours would live
  in-tree. Until then, generic boxes with pin names suffice for
  review.
- **Output**: static SVG, golden-tested like the netlist emitter's
  byte-identical goldens. Not `.kicad_sch` — editable output is
  SKiDL's trap and buys review nothing.

Explicitly **not** built: a placement engine, a router, an interactive
viewer (d3-hwschematic shows the shape if one is ever wanted).

Sequencing: **block view first** — small graphs, highest review value,
exercises extraction before layout quality matters. Then the detail
view on grandalf, golden-SVG tests in the house style.

Follow-up filed as KANBAN card **T26 — DSL review views: block +
detail** (2026-09-28), blocked by T7bd.
