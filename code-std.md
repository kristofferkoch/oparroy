# oparroy C++ coding standard

Living document, created 2026-09-26. Evolves by dated edits —
every substantive change gets a date so archaeology stays easy.

Scope: all oparroy firmware and host-testable firmware logic. The DSL
(Python) has its own harness (ruff strict, ty) and mostly lives outside
this document — §12 holds the few Python rules we do own.

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
- **No `__DATE__`/`__TIME__`/`__TIMESTAMP__`** (2026-09-26): bit-for-bit
  reproducible builds are a hard constraint (DESIGN.md §8); version
  identity comes from git, never from compile-time stamps.
- Freestanding-subset headers are allowed (`<cstdint>`, `<cstddef>`,
  `<limits>`, `<type_traits>`, `<bit>`); anything that drags in hosted
  machinery is not. Project types beat std types where both exist
  (`ErrorOr` over `std::expected`) for consistency with the foundation
  library (§8).

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
  function ends with `UNREACHABLE()` (`firmware/lib/verify.hpp`,
  landed 2026-09-28, replacing bare
  `__builtin_unreachable()`) — `-Wswitch-enum` still guards the cases.
- Loops have bounded trip counts where feasible — friendlier to KLEE
  and to WCET reasoning. Unbounded loops need a stated reason (e.g.
  polling a status register with a timeout).
- **Integer index loops are spelled `lib::irange`, never classical
  `for (i = 0; i < n; ++i)`** (2026-09-26): boundary reasoning happens
  once, in the type (`firmware/lib/range.hpp`) — half-open interval,
  zero-trip on inverted ranges, no increment-past-max on any integer
  width. `zip`/`enumerate` land when a consumer appears.
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
- `enum class` only, explicit underlying type. It improves readability
  at zero cost — and combined with exhaustive switching (§3), adding a
  state becomes a compile error at every site that doesn't handle it.
- **`bool` arguments and returns are mostly a no-no** (2026-09-26): at
  the call site `engage(true)` says nothing — use a two-state
  `enum class` (`Bypass::Engaged` reads). Exceptions: predicate
  functions named as questions (`tx_ready()`) may return `bool`, and
  labeled struct/config fields (`supervisor = true`) may hold one.
- **Make illegal states unrepresentable** (2026-09-26): choose types
  so invalid states cannot be constructed, rather than checking for
  them downstream. Establish invariants in the constructor (RAII, §5),
  never a separate `init()` leaving a half-valid object; parse, don't
  validate — decode unstructured input into a typed value once (a
  decoded-frame type), so later code cannot re-encounter the invalid
  case; strong types over bare primitives where two same-typed values
  could be transposed (a slot index is not a byte count).
- `auto` where the type is obvious from the right-hand side
  (iterators, factory calls, templates); spelled types where the type
  *is* the information (arithmetic, protocol fields).

## 5. Memory and ownership

- Static storage or arena-backed, fixed-capacity containers; nothing
  grows without asking (§8 foundation library). Growth comes in two
  flavors (2026-09-26, §6): `try_*` for data-driven fills,
  VERIFY-contract growth (`push_back`) for sized-by-construction ones.
- **No raw pointers at interfaces** (2026-09-26): a view over a buffer
  is `Span<T>` (`firmware/lib/span.hpp`), never `T*` plus a separate
  length — the bound travels with the pointer or it gets lost. Raw
  `T*` stays inside span/container internals and at the MMIO boundary
  (the `reinterpret_cast` rule below); function signatures and struct
  fields don't carry one. Bounds are carried, not checked: KLEE's
  out-of-bounds detection and fuzzing own the defect class (§1), with
  the `VERIFY` hook adding the target-side check.
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
- **Offensive, not defensive** (2026-09-26): contract violations — a
  capacity sized by construction, an "impossible" state — trap via
  `VERIFY` (`firmware/lib/verify.hpp`); KLEE proves each trap
  unreachable, and a reachable one is a proof failure with a
  counterexample, not a hope. Error returns are for *environmental*
  failure only (hostile input, a full arena), where the caller holds a
  policy decision. A `try_*` failure branch no test can reach is dead
  weight the coverage gate (§8) flags forever; a VERIFY in the
  same spot is a proof obligation.
- `VERIFY(...)` failures route through the project failure hook, which
  ties into the watchdog/bypass policy (§4): deliberate bypass-engage,
  not a hung loop. (2026-09-28: the hook is `lib::verify_failed`,
  wired by `-DOPARROY_TARGET` in `firmware/lib/verify.hpp`; the node
  firmware provides its own definition.)

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
- **The pre-commit hooks own the entry point** (2026-09-26):
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

## 11. Tests

- **Red/green, always** (2026-09-26): a test that was never watched
  failing proves nothing — it may test nothing. See the test fail
  first, then make it pass. Write the failing test first where
  practical; otherwise break the code deliberately and watch the test
  catch it. Applies to every harness layer (DESIGN.md §8): unit tests,
  KLEE proofs (a violated assertion must be reachable), fuzz seeds,
  ngspice subcircuit sims, HIL.

## 12. Python (the DSL)

Ruff (`ALL`, formatter-conflicts off) owns style, ty owns types; this
section holds the handful of rules we chose ourselves.

- **Small functions carry doctests where suitable** (2026-09-26): if a
  function's contract fits in a two-line REPL example, write it as a
  doctest in the docstring — example-first documentation that pytest
  executes (`--doctest-modules` collects `src/`; see
  `pyproject.toml`). Doctests are illustrations, not the test suite:
  edge cases, error paths, and property-style tests stay in `tests/`
  as ordinary pytest tests. A doctest that needs setup code or asserts
  more than it shows is a unit test wearing a costume — move it.
- **Red/green applies to doctests too** (§11): watch a new doctest
  fail (wrong expected output) before trusting it.
- **Name composite types — nesting past one parameterization is a
  smell** (2026-10-10): a signature like
  `dict[tuple[tuple[str, ...], str], Net]` is a domain concept wearing
  structural clothing — the reader reverse-engineers "tile path plus
  local name" at every site, and the components transpose without a
  murmur. Give it a name: a frozen dataclass when the parts have
  distinct meanings (`TileNet`, the transform handles' key,
  `src/oparroy/dsl/ir.py`), a `type` alias when it is pure container
  shorthand. The same rule covers return tuples past two elements.
  Neither ruff nor ty can check this; review owns it (§9).
