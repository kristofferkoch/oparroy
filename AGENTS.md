# Project notes for agents

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
KiCad is used for layout only. Firmware is freestanding C++ (no
standard library; RAII, placement new on memory-mapped I/O) under an
aviation-grade rule set, statically checked, KLEE-verified from the
start (DESIGN.md §8).
Tool provisioning: nix flake for everything non-Python (compilers,
provers, ngspice, KiCad, uv itself); uv owns Python alone — 3.13, ruff
(strict), ty, pytest. Test philosophy: hands-off hardware-in-the-loop
from day one (see DESIGN.md §6, §8).
