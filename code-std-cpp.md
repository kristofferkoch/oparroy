# oparroy C++ coding standard

Split out of `code-std.md` (sections 2–8 and 10 there).
Philosophy, enforcement split, and the red/green test rule live in
[code-std.md](code-std.md) and apply here.

Scope: all oparroy firmware and host-testable firmware logic.

## 1. Language and toolchain

- **C++23 baseline**, tracking C++26 as clang/gcc ship it. New features
  are adopted when they erase code or add compile-time guarantees, not
  for novelty.
- Clang-first: firmware logic must compile to LLVM bitcode for KLEE
  ([DESIGN.md#8-verification-strategy](DESIGN.md#8-verification-strategy));
  the GCC target build must stay compatible.
- **No libc `main`** — under `-ffreestanding` clang mangles a C++
  `main`, so entry points are `extern "C"`: the reset handler on
  target, a named `--entry-point` for KLEE harnesses.
- **Freestanding contract**
  ([DESIGN.md#8-verification-strategy](DESIGN.md#8-verification-strategy),
  settled): `-ffreestanding -nostdlib -fno-exceptions -fno-rtti`, no
  heap outside explicitly carved arenas.
- **No `__DATE__`/`__TIME__`/`__TIMESTAMP__`**: bit-for-bit
  reproducible builds are a hard constraint
  ([DESIGN.md#8-verification-strategy](DESIGN.md#8-verification-strategy));
  version identity comes from git, never from compile-time stamps.
- Freestanding-subset headers are allowed (`<cstdint>`, `<cstddef>`,
  `<limits>`, `<type_traits>`, `<bit>`); anything that drags in hosted
  machinery is not. Project types beat std types where both exist
  (`ErrorOr` over `std::expected`) for consistency with the foundation
  library
  ([DESIGN.md#8-verification-strategy](DESIGN.md#8-verification-strategy)).

## 2. Control flow

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
  replacing bare `__builtin_unreachable()`) — `-Wswitch-enum` still
  guards the cases.
- Loops have bounded trip counts where feasible — friendlier to KLEE
  and to WCET reasoning. Unbounded loops need a stated reason (e.g.
  polling a status register with a timeout).
- **Integer index loops are spelled `lib::irange`, never classical
  `for (i = 0; i < n; ++i)`**: boundary reasoning happens
  once, in the type (`firmware/lib/range.hpp`) — half-open interval,
  zero-trip on inverted ranges, no increment-past-max on any integer
  width. `zip`/`enumerate` land when a consumer appears.
- No `goto`. No recursion (bounded stack, and the prover thanks us).
  No exceptions, no RTTI — settled in
  [DESIGN.md#8-verification-strategy](DESIGN.md#8-verification-strategy),
  restated for completeness.

## 3. Types and arithmetic

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
  at zero cost — and combined with exhaustive switching
  ([#2-control-flow](#2-control-flow)), adding a state becomes a
  compile error at every site that doesn't handle it.
- **`bool` arguments and returns are mostly a no-no**: at
  the call site `engage(true)` says nothing — use a two-state
  `enum class` (`Bypass::Engaged` reads). Exceptions: predicate
  functions named as questions (`tx_ready()`) may return `bool`, and
  labeled struct/config fields (`supervisor = true`) may hold one.
- **Make illegal states unrepresentable**: choose types
  so invalid states cannot be constructed, rather than checking for
  them downstream. Establish invariants in the constructor (RAII,
  [#4-memory-and-ownership](#4-memory-and-ownership)), never a
  separate `init()` leaving a half-valid object; parse, don't
  validate — decode unstructured input into a typed value once (a
  decoded-frame type), so later code cannot re-encounter the invalid
  case; strong types over bare primitives where two same-typed values
  could be transposed (a slot index is not a byte count).
- `auto` where the type is obvious from the right-hand side
  (iterators, factory calls, templates); spelled types where the type
  *is* the information (arithmetic, protocol fields).

## 4. Memory and ownership

- Static storage or arena-backed, fixed-capacity containers; nothing
  grows without asking
  ([DESIGN.md#8-verification-strategy](DESIGN.md#8-verification-strategy)
  foundation library). Growth comes in two flavors
  ([#5-error-handling](#5-error-handling)): `try_*` for data-driven
  fills, VERIFY-contract growth (`push_back`) for sized-by-construction
  ones.
- **No raw pointers at interfaces**: a view over a buffer
  is `Span<T>` (`firmware/lib/span.hpp`), never `T*` plus a separate
  length — the bound travels with the pointer or it gets lost. Raw
  `T*` stays inside span/container internals and at the MMIO boundary
  (the `reinterpret_cast` rule,
  [#3-types-and-arithmetic](#3-types-and-arithmetic)); function
  signatures and struct fields don't carry one. Bounds are carried,
  not checked: KLEE's out-of-bounds detection and fuzzing own the
  defect class
  ([code-std.md#1-philosophy](code-std.md#1-philosophy)), with the
  `VERIFY` hook adding the target-side check.
- RAII for every resource and lock; no paired acquire/release calls
  separated by user code.
- MMIO register blocks are `volatile` structs via placement `new` —
  type-safe register access, no raw integer pokes.
- Data shared between ISR and main: `volatile` plus explicit ordering,
  or an RAII interrupt-guard for multi-byte updates. Single-core means
  this is short, and every instance is deliberate.

## 5. Error handling

- `ErrorOr<T>` is the universal fallible return type; anything that
  can fail returns, never traps silently
  ([DESIGN.md#8-verification-strategy](DESIGN.md#8-verification-strategy)).
- `[[nodiscard]]` on every function returning `ErrorOr` or an error
  type. Unchecked errors are compile errors.
- `TRY(...)` propagation (AK's idiom) is the one blessed control-flow
  macro — it reads like exceptions and compiles to branches.
- **Offensive, not defensive**: contract violations — a
  capacity sized by construction, an "impossible" state — trap via
  `VERIFY` (`firmware/lib/verify.hpp`); KLEE proves each trap
  unreachable, and a reachable one is a proof failure with a
  counterexample, not a hope. Error returns are for *environmental*
  failure only (hostile input, a full arena), where the caller holds a
  policy decision. A `try_*` failure branch no test can reach is dead
  weight the coverage gate
  ([DESIGN.md#8-verification-strategy](DESIGN.md#8-verification-strategy))
  flags forever; a VERIFY in the same spot is a proof obligation.
- `VERIFY(...)` failures route through the project failure hook, which
  ties into the watchdog/bypass policy
  ([DESIGN.md#4-node-watchdog--bypass](DESIGN.md#4-node-watchdog--bypass)):
  deliberate bypass-engage, not a hung loop. (the hook is
  `lib::verify_failed`, wired by `-DOPARROY_TARGET` in
  `firmware/lib/verify.hpp`; the node firmware provides its own
  definition.)

## 6. Constants and configuration

- `constexpr`/`consteval` over macros, always. The preprocessor is for
  includes, guards, and `TRY`/`VERIFY`.
- Pin/config tables are `constexpr` with designated initializers —
  the compiler, not the reader, checks completeness.
- Magic numbers: named when the meaning isn't obvious from context.
  No MISRA-style policing of `0`, `1`, or loop arithmetic — that's
  checker-food, not defect prevention.

## 7. Naming and layout

- Types `PascalCase`, functions and variables `snake_case`, macros
  `SHOUTY` — AK-flavored, matching the foundation library.
- `.clang-format` owns whitespace entirely; this document spends no
  words on brace placement or column limits.

## 8. Deviations register

Rules from the borrowed standards that we examined and rejected, and
what covers the defect class instead:

| Rejected rule (source)                                | Why                                     | What covers it                                                         |
| ----------------------------------------------------- | --------------------------------------- | ---------------------------------------------------------------------- |
| Single exit point (JSF AV)                            | Guard clauses read better               | KLEE path coverage                                                     |
| Mandatory `default` on every `switch` (JSF AV, MISRA) | Dead code that silences `-Wswitch-enum` | exhaustive enum switches                                               |
| Essential-type arithmetic regime (MISRA C++:2023)     | Cast noise hides bugs and bloats lines  | `-Wconversion`, UBSan, KLEE                                            |
| Magic-number policing (MISRA/AUTOSAR)                 | Checker-food                            | judgment, review                                                       |
| Compliance/deviation-process overhead (MISRA)         | Buys a small project nothing            | this table                                                             |
| AUTOSAR C++14 as a base                               | Dead standard, frozen at C++14          | C++23 baseline, [#1-language-and-toolchain](#1-language-and-toolchain) |

Retained from all three without modification: no exceptions, no RTTI,
no heap by default, no recursion, no `goto` — all already the
[DESIGN.md#8-verification-strategy](DESIGN.md#8-verification-strategy)
freestanding contract.
