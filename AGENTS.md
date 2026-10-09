# Project notes for agents

## Making changes — PRs only, one worktree per PR

- **All changes land via pull request.** Never commit directly to
  `main`; open a PR, even for one-line fixes.
- **Each PR gets its own git worktree.** From the main checkout:
  `git worktree add ../oparroy-wt-<name> -b <branch>`, then work
  entirely inside that directory. Worktrees keep simultaneous agents
  from stomping on each other's checkout — never share a working tree
  between tasks. When the PR merges, remove the worktree
  (`git worktree remove ../oparroy-wt-<name>`) and delete the branch.
- **Open PRs as drafts** (`gh pr create --draft`). Mergify skips
  drafts, so nothing merges before its time. Mark a PR ready for
  review only when the user explicitly authorizes it — otherwise leave
  the flip to the user.
- **Merging is automatic once ready.** When a non-draft PR's `check`
  CI job goes green, Mergify queues it and merges it against the
  latest `main` (`.mergify.yml`) — no session needs to stay open
  waiting for CI.

## Documentation — the IDEAS / KANBAN / DESIGN split

- **`IDEAS.md`** — stray, not-yet-planned thoughts. Append; never lose
  them. If the user mentions an idea in passing — interesting, but not
  the current task — add it to IDEAS.md before moving on.
- **`KANBAN.md`** — the single home for planned work and the execution
  view over it. Cards are vertical slices (or carry a `Shape:` tag when
  they aren't), carry their own descriptions plus `Blocked by:` /
  `Unblocks:`, and live in Next / Backlog. There is no In Progress and
  no Done column: the change that ships a card deletes it; git history
  is the archive. When ordering matters, KANBAN wins.
- **`DESIGN.md`** — settled design decisions, plus a §Open design
  questions section for decided-to-be-decided problems that aren't yet
  work cards.

When an idea graduates, **move** it (out of IDEAS.md into a KANBAN card,
or into DESIGN.md if it is a design decision) — don't leave a copy
behind.

**Card IDs (`T##`) never leave KANBAN.md.** Cards are deleted as they
ship, so a `T##` cited anywhere else — docs, README, commit messages,
PRs — becomes an orphan reference the moment the card lands. Name the
subsystem, decision, or doc section instead ("the node pin map",
"DESIGN.md §7"); provenance lives in git history and in KANBAN's own
card text while the card is alive.

## Voice and format

Tight, active, present tense. Concrete over abstract — name the part,
the pin, the exact failure mode. Use **absolute dates** ("2026-09-26"),
never a relative "recently" / "now" that rots. Cite doc sections with
`§`. Link rather than duplicate; the linked doc stays the single source
of truth.

## Datasheets — extraction is mandatory

- **`datasheets/<PART>/`** holds one part's canonical vendor PDFs
  (version in the filename); **`datasheets/<PART>/notes/`** holds the
  LLM-readable markdown sidecars: `facts.md` (index + overview), one
  file per peripheral/topic (`opa.md`, `timers.md`, …), and
  `quirks.md`. See `datasheets/README.md`.
- **Standing instruction:** whenever you extract a fact from a datasheet
  — a register, a pin function, an electrical limit — write it into the
  part's matching `notes/<topic>.md` immediately, cited by document and
  section (`(RM §17.2)`). Never leave a datasheet fact living only in
  the conversation.
- **Standing instruction:** cross-check the datasheet against the
  vendor SDK, even though we don't use the SDK directly. Verify as you
  document, not after: when writing up a peripheral (e.g. UART), read
  the SDK's driver for it and confirm our understanding matches — init
  sequences, register writes, bit orders, errata workarounds. Where the
  SDK does something the datasheet doesn't explain, that's an
  undocumented quirk: record it in `notes/quirks.md`.
- Silicon quirks, doc-vs-silicon mismatches, SDK-vs-doc mismatches, and
  tribal knowledge (issue trackers, bench findings) go in
  `notes/quirks.md`, one sourced bullet each, dated.

## Project shape

Hardware + firmware + design-automation project. Design capture is a
home-rolled Python DSL (single source of truth) that emits KiCad
netlists, constraint checks, firmware headers, and simulation netlists —
KiCad is used for layout only. DSL core (IR, subcircuit composition with ports,
port arrays and bundles, and a flattening pass, instrumentation
transforms with provenance tags,
validation pass, KiCad netlist emitter, ngspice simulation-netlist
emitter, KiCad library access, typed
jellybean parts and connector blocks, the parts DB with
assembler-stock status, footprint-assignment and
annotation/back-annotation stages, dot dump, firmware pin-header
generation with the GPIO-budget check) lives in `src/oparroy/dsl/`; circuit captures
live in `design/` (DESIGN.md §7 DSL shape). Firmware is freestanding
C++ (no standard library; RAII, placement new on memory-mapped I/O)
under an aviation-grade rule set, statically checked, KLEE-verified
from the start (DESIGN.md §8).
Tool provisioning: nix flake for everything non-Python (compilers,
provers, ngspice, KiCad, uv itself); uv owns Python alone — 3.14,
pinned to match nixpkgs' pcbnew build so the dev shell's `PYTHONPATH`
export makes `import pcbnew` work in the project venv (one interpreter
runs the test suite and KiCad scripting), ruff (strict), ty, pytest. Test philosophy: hands-off hardware-in-the-loop
from day one (see DESIGN.md §6, §8).
