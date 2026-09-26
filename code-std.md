# oparroy C++ coding standard

Living document, created 2026-09-26 (T16b). Evolves by dated edits —
every substantive change gets a date so archaeology stays easy.

Scope: all oparroy firmware and host-testable firmware logic. The DSL
(Python) has its own harness (ruff strict, ty) and is out of scope here.

## 1. Philosophy

Safety by **construction and proof**, not syntax superstition. We borrow
from JSF AV C++, MISRA C++:2023, AUTOSAR C++14, and CERT the rules that
prevent real defects; we drop rules that exist only because a commercial
checker can check them. Correctness classes that a prover owns —
bounds, overflow, path coverage, state-machine invariants — are
**not** policed by style rules; KLEE, fuzzing, UBSan, and release-build
coverage own them (DESIGN.md §8).

Readability is a safety property. A rule that makes correct code uglier
needs to earn its place every time it's touched.

## 2. Language and toolchain

- **C++23 baseline**, tracking C++26 as clang/gcc ship it. New features
  are adopted when they erase code or add compile-time guarantees, not
  for novelty.
- Clang-first: firmware logic must compile to LLVM bitcode for KLEE
  (DESIGN.md §8); the GCC target build must stay compatible.
- **No libc `main`** — under `-ffreestanding` clang mangles a C++
  `main`, so entry points are `extern "C"`: the reset handler on
  target, a named `--entry-point` for KLEE harnesses.
- **Freestanding contract** (§8, settled): `-ffreestanding -nostdlib -fno-exceptions -fno-rtti`, no heap outside explicitly carved arenas.
- Freestanding-subset headers are allowed (`<cstdint>`, `<cstddef>`,
  `<limits>`, `<type_traits>`, `<bit>`); anything that drags in hosted
  machinery is not. Project types beat std types where both exist
  (`ErrorOr` over `std::expected`) for consistency with the foundation
  library (§8, T18).

## 3. Control flow

- **Early returns and guard clauses are encouraged.** (Explicit
  deviation from JSF AV's single-exit rule — KLEE explores all paths;
  the rule's safety rationale is redundant here.)
- Braces on all `if`/`else`/loop bodies. Cheap, kills dangling-else
  edits.
- `switch` over a closed `enum class`: exhaustive cases, **no
  `default`** — `-Wswitch-enum` flags a missed enumerator at compile
  time, which a dead `default` would silence. Switches over plain
  integers take a `default`. Fallthrough only with `[[fallthrough]]`.
  GCC doesn't treat an exhaustive enum switch as covering, so the
  function ends with `__builtin_unreachable()` (a project `UNREACHABLE`
  macro once T18 lands) — `-Wswitch-enum` still guards the cases.
- Loops have bounded trip counts where feasible — friendlier to KLEE
  and to WCET reasoning. Unbounded loops need a stated reason (e.g.
  polling a status register with a timeout).
- No `goto`. No recursion (bounded stack, and the prover thanks us).
  No exceptions, no RTTI — settled in §8, restated for completeness.

## 4. Types and arithmetic

- Explicit-width integers (`uint32_t`, `int16_t`) at every interface;
  plain `int` acceptable for locals where width is irrelevant.
- Implicit narrowing and sign conversions are **compile errors**
  (`-Wconversion -Wsign-conversion`, warnings-as-errors). This replaces
  MISRA's essential-type regime: we want the diagnostics without the
  cast noise.
- No C-style casts. `static_cast` in normal code; `reinterpret_cast`
  only at the MMIO boundary, next to a comment naming the register
  block it maps.
- `enum class` only, explicit underlying type.
- `auto` where the type is obvious from the right-hand side
  (iterators, factory calls, templates); spelled types where the type
  *is* the information (arithmetic, protocol fields).

## 5. Memory and ownership

- Static storage or arena-backed, fixed-capacity containers with
  `try_*` growth; nothing grows without asking (§8 foundation library).
- RAII for every resource and lock; no paired acquire/release calls
  separated by user code.
- MMIO register blocks are `volatile` structs via placement `new` —
  type-safe register access, no raw integer pokes.
- Data shared between ISR and main: `volatile` plus explicit ordering,
  or an RAII interrupt-guard for multi-byte updates. Single-core means
  this is short, and every instance is deliberate.

## 6. Error handling

- `ErrorOr<T>` is the universal fallible return type; anything that
  can fail returns, never traps silently (§8).
- `[[nodiscard]]` on every function returning `ErrorOr` or an error
  type. Unchecked errors are compile errors.
- `TRY(...)` propagation (AK's idiom) is the one blessed control-flow
  macro — it reads like exceptions and compiles to branches.
- `VERIFY(...)` failures route through the project failure hook, which
  ties into the watchdog/bypass policy (§4): deliberate bypass-engage,
  not a hung loop.

## 7. Constants and configuration

- `constexpr`/`consteval` over macros, always. The preprocessor is for
  includes, guards, and `TRY`/`VERIFY`.
- Pin/config tables are `constexpr` with designated initializers —
  the compiler, not the reader, checks completeness.
- Magic numbers: named when the meaning isn't obvious from context.
  No MISRA-style policing of `0`, `1`, or loop arithmetic — that's
  checker-food, not defect prevention.

## 8. Naming and layout

- Types `PascalCase`, functions and variables `snake_case`, macros
  `SHOUTY` — AK-flavored, matching the foundation library.
- `.clang-format` owns whitespace entirely; this document spends no
  words on brace placement or column limits.

## 9. Enforcement split

- **The toolchain owns**: formatting (clang-format), conversions,
  unused/dead code, nodiscard violations, suspicious constructs —
  `.clang-tidy` with cherry-picked AUTOSAR/CERT checks, all
  warnings-as-errors. Markdown layout is mdformat's, lint is
  markdownlint-cli2's, link health is lychee's.
- **The pre-commit hooks own the entry point** (2026-09-26, T16b):
  `.pre-commit-config.yaml` runs clang-format, clang-tidy, mdformat,
  markdownlint-cli2, and lychee on staged files — cheap checks only,
  under ~3 s warm. Every tool is nix-pinned (flake.nix) and invoked via
  `language: system`, so the flake stays the single tool source.
- **Review owns**: everything in this document that isn't mechanically
  checkable — naming intent, loop-bound justification, MMIO cast
  comments, arena sizing.

## 10. Deviations register

Rules from the borrowed standards that we examined and rejected, and
what covers the defect class instead:

| Rejected rule (source)                                | Why                                     | What covers it              |
| ----------------------------------------------------- | --------------------------------------- | --------------------------- |
| Single exit point (JSF AV)                            | Guard clauses read better               | KLEE path coverage          |
| Mandatory `default` on every `switch` (JSF AV, MISRA) | Dead code that silences `-Wswitch-enum` | exhaustive enum switches    |
| Essential-type arithmetic regime (MISRA C++:2023)     | Cast noise hides bugs and bloats lines  | `-Wconversion`, UBSan, KLEE |
| Magic-number policing (MISRA/AUTOSAR)                 | Checker-food                            | judgment, review            |
| Compliance/deviation-process overhead (MISRA)         | Buys a small project nothing            | this table                  |
| AUTOSAR C++14 as a base                               | Dead standard, frozen at C++14          | C++23 baseline, §2          |

Retained from all three without modification: no exceptions, no RTTI,
no heap by default, no recursion, no `goto` — all already the §8
freestanding contract.
