# oparroy coding standard

Living document, created 2026-09-26. Evolves by dated edits —
every substantive change gets a date so archaeology stays easy.

Split 2026-10-10: the language-specific sections moved into
per-language documents ([Language standards](#2-language-standards))
so readers and agents load only the rules for the language they work
in. This file keeps the language-independent rules.

Scope: all oparroy code — firmware, host-testable firmware logic, and
the DSL.

## 1. Philosophy

Safety by **construction and proof**, not syntax superstition. We borrow
from JSF AV C++, MISRA C++:2023, AUTOSAR C++14, and CERT the rules that
prevent real defects; we drop rules that exist only because a commercial
checker can check them. Correctness classes that a prover owns —
bounds, overflow, path coverage, state-machine invariants — are
**not** policed by style rules; KLEE, fuzzing, UBSan, and release-build
coverage own them ([DESIGN.md#8-verification-strategy](DESIGN.md#8-verification-strategy)).

Readability is a safety property. A rule that makes correct code uglier
needs to earn its place every time it's touched.

## 2. Language standards

- **C++** — firmware and host-testable firmware logic:
  [code-std-cpp.md](code-std-cpp.md). clang-format and clang-tidy own
  the mechanically checkable bulk.
- **Python** — the DSL: [code-std-python.md](code-std-python.md).
  Ruff (`ALL`, formatter-conflicts off) owns style, ty owns types.

## 3. Enforcement split

- **The toolchain owns**: formatting (clang-format), conversions,
  unused/dead code, nodiscard violations, suspicious constructs —
  `.clang-tidy` with cherry-picked AUTOSAR/CERT checks, all
  warnings-as-errors. Markdown layout is mdformat's, lint is
  markdownlint-cli2's, link health is lychee's.
- **The pre-commit hooks own the entry point** (2026-09-26):
  `.pre-commit-config.yaml` runs clang-format, clang-tidy, mdformat,
  markdownlint-cli2, and lychee on staged files — cheap checks only,
  under ~3 s warm. Every tool is nix-pinned (flake.nix) and invoked via
  `language: system`, so the flake stays the single tool source.
- **Review owns**: everything in these documents that isn't
  mechanically checkable — naming intent, loop-bound justification,
  MMIO cast comments, arena sizing.

## 4. Tests

- **Red/green, always** (2026-09-26): a test that was never watched
  failing proves nothing — it may test nothing. See the test fail
  first, then make it pass. Write the failing test first where
  practical; otherwise break the code deliberately and watch the test
  catch it. Applies to every harness layer
  ([DESIGN.md#8-verification-strategy](DESIGN.md#8-verification-strategy)):
  unit tests, KLEE proofs (a violated assertion must be reachable),
  fuzz seeds, ngspice subcircuit sims, HIL.
