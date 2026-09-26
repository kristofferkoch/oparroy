# Toolchain smoke test (T16b): not firmware logic — delete when
# T16c/T11 supersede it (smoke.cpp's header comment has the details).

# Compiled with the toolchain of whichever build dir is configured:
# clang in the native dir (meson/native/clang.ini),
# riscv64-none-elf-g++ in the cross dir (meson/cross/rv32ec.ini).
static_library('smoke', 'smoke.cpp')

if not meson.is_cross_build()
  # LLVM bitcode for KLEE (DESIGN.md §8). Lifetime markers are off:
  # klee 3.2 doesn't implement the intrinsic (T16c note in KANBAN.md);
  # they carry no semantics we need in proofs.
  custom_target('smoke-bitcode',
    input: 'smoke.cpp',
    output: 'smoke.bc',
    command: meson.get_compiler('cpp').cmd_array() + [
      # The meson-covered part of the freestanding set — see the
      # freestanding_flags comment in the root meson.build.
      '-std=c++23', '-Wall', '-Wextra', '-Wpedantic', '-Werror',
    ] + freestanding_flags + repro_flags + [
      '-Xclang', '-disable-lifetime-markers',
      '-emit-llvm', '-c', '@INPUT@', '-o', '@OUTPUT@',
    ],
    build_by_default: true,
  )
endif
