# Foundation library: the freestanding, AK-inspired cells of DESIGN.md
# §8, header-only. lib.cpp is the translation unit that keeps the GCC
# cross build (rv32ec) and clang-tidy compiling every header, and hosts
# the constexpr static_assert proofs (code-std.md#4-tests).

static_library('foundation', 'lib.cpp')

if not meson.is_cross_build()
  # TRY can't be constexpr-proved (statement expressions aren't constant
  # expressions), so its paths run as a host test instead.
  test('foundation', executable('foundation-test', 'test_foundation.cpp'))
endif
