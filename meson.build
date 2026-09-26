project('oparroy', 'cpp',
  version: '0.1.0',
  meson_version: '>=1.3',
  default_options: [
    'cpp_std=c++23',
    # warning_level=3 is exactly -Wall -Wextra -Wpedantic for both clang
    # and gcc; with werror the set matches freestanding_flags below.
    'warning_level=3',
    'werror=true',
    # plain: meson injects no -O/-g — build flavors are chosen per build
    # dir at setup time (release for T16e's coverage, etc.). This also
    # dodges the nix cc-wrapper's fortify hardening, which appends
    # -D_FORTIFY_SOURCE=2 after all user flags whenever it sees an
    # explicit -O (meson's debug -O0 included) — glibc's features.h then
    # #errors under -Werror, and freestanding has no libc for fortify to
    # call into anyway.
    'buildtype=plain',
  ],
)

# Freestanding flag set (code-std.md §2) — the single source, replacing
# scripts/freestanding-flags.sh (T20). Meson targets get -std=c++23
# -Wall -Wextra -Wpedantic -Werror from default_options above; custom
# compiles (the bitcode target, KLEE in T16c) must compose the full
# set by hand: ['-std=c++23', '-Wall', '-Wextra', '-Wpedantic',
# '-Werror'] + freestanding_flags + repro_flags.
freestanding_flags = [
  '-ffreestanding',
  '-fno-exceptions',
  '-fno-rtti',
  '-Wconversion',
  '-Wsign-conversion',
  '-Wdouble-promotion',
  '-Wshadow',
  '-Wundef',
  '-Wswitch-enum',
  '-Wold-style-cast',
  '-Wcast-qual',
  '-Wnull-dereference',
]

# Reproducibility (DESIGN.md §8): same source tree + same flake.lock
# must give byte-identical artifacts on any machine, so no build paths
# may leak into outputs. -ffile-prefix-map covers debug and macro
# prefix maps too.
repro_flags = [
  '-ffile-prefix-map=' + meson.project_source_root() + '=/src/oparroy',
  '-ffile-prefix-map=' + meson.project_build_root() + '=/build/oparroy',
]

add_project_arguments(freestanding_flags + repro_flags, language: 'cpp')

subdir('firmware/smoke')

# Reproducibility gate (DESIGN.md §8): builds every configuration twice
# and compares artifact hashes — a mismatch is red like a failing test.
run_target('check-reproducible',
  command: find_program('scripts/check-reproducible'),
)
