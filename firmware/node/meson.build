# Node target support: the DSL-generated CH32V003 pin map —
# design/node_pins.py regenerates pins.hpp, and tests/golden/
# node-pins.hpp pins it byte-exact. pins.cpp is the compile proof that
# the header builds under the freestanding rule set on every toolchain
# in the matrix. runtime.cpp is the soft integer runtime the rv32ec
# link needs (no M extension, no libgcc multilib — see its header
# comment); its unit tests run on the host.
node_pins = static_library('node-pins', 'pins.cpp')

if not meson.is_cross_build()
  test('node-runtime', executable('node-runtime-test',
    ['runtime.cpp', 'test_runtime.cpp', '../lib/test_main.cpp'],
  ), suite: 'firmware')
endif

if meson.is_cross_build()
  # The first real target link. gcc-as-driver works with -nostdlib
  # -nostartfiles: the multilib probe this toolchain's -march=rv32ec
  # trips on only fires when crt0/libgcc are requested, and the soft
  # integer runtime (runtime.cpp) covers what libgcc would have
  # provided. -march/-mabi must be repeated in link_args — built-in
  # cpp_args are compile-time only. No -Wl,-Map: the ELF is a §8
  # reproducible artifact.
  ch32v003_ld = files('ch32v003.ld')
  node_elf = executable('node.elf',
    ['runtime.cpp', 'startup.cpp', 'main.cpp', 'platform.cpp'],
    cpp_args: [
      '-ffunction-sections', '-fdata-sections',
      '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
    ],
    link_args: [
      '-march=rv32ec_zicsr', '-mabi=ilp32e',
      '-nostdlib', '-nostartfiles',
      '-T', ch32v003_ld[0].full_path(),
      '-Wl,--gc-sections',
    ],
    link_depends: ch32v003_ld,
    link_with: node_pins,
  )

  # Flashing artifact: raw flash image from 0x08000000.
  custom_target('node.bin',
    output: 'node.bin',
    input: node_elf,
    command: [find_program('riscv64-none-elf-objcopy'), '-O', 'binary',
              '@INPUT@', '@OUTPUT@'],
    build_by_default: true,
  )
endif
