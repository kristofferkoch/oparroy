# oparroy Python coding standard

Split out of `code-std.md` 2026-10-10 (section 12 there). Philosophy,
enforcement split, and the red/green test rule live in
[code-std.md](code-std.md) and apply here.

Scope: the DSL (`src/oparroy/`, `design/`, `tests/`).

Ruff (`ALL`, formatter-conflicts off) owns style, ty owns types; this
document holds the handful of rules we chose ourselves.

## 1. Doctests

- **Small functions carry doctests where suitable** (2026-09-26): if a
  function's contract fits in a two-line REPL example, write it as a
  doctest in the docstring — example-first documentation that pytest
  executes (`--doctest-modules` collects `src/`; see
  `pyproject.toml`). Doctests are illustrations, not the test suite:
  edge cases, error paths, and property-style tests stay in `tests/`
  as ordinary pytest tests. A doctest that needs setup code or asserts
  more than it shows is a unit test wearing a costume — move it.
- **Red/green applies to doctests too**
  ([code-std.md#4-tests](code-std.md#4-tests)): watch a new doctest
  fail (wrong expected output) before trusting it.

## 2. Composite types

- **Name composite types — nesting past one parameterization is a
  smell** (2026-10-10): a signature like
  `dict[tuple[tuple[str, ...], str], Net]` is a domain concept wearing
  structural clothing — the reader reverse-engineers "tile path plus
  local name" at every site, and the components transpose without a
  murmur. Give it a name: a frozen dataclass when the parts have
  distinct meanings (`TileNet`, the transform handles' key,
  `src/oparroy/dsl/ir.py`), a `type` alias when it is pure container
  shorthand. The same rule covers return tuples past two elements.
  Neither ruff nor ty can check this; review owns it
  ([code-std.md#3-enforcement-split](code-std.md#3-enforcement-split)).
