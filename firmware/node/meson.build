# Node target support: the DSL-generated CH32V003 pin map is
# regenerated into the build dir by the custom_target below whenever
# its inputs change — capture: true takes the generator's stdout
# byte-exact, the same stream tests/golden/node-pins.hpp and the
# checked-in firmware/node/pins.hpp pin via pytest. Every consumer
# lists the target as a source so ninja regenerates before compiling,
# and sources include it as <pins.hpp>: meson puts the build dir ahead
# of the source dir on the include path, so the fresh copy always wins
# over the checked-in reference. On a not-yet-compiled tree (the
# clang-tidy pre-commit hook only configures) resolution falls back to
# the checked-in copy, which the pytest pair keeps identical. pins.cpp
# is the compile proof that the header builds under the freestanding
# rule set on every toolchain in the matrix. runtime.cpp is the soft
# integer runtime the rv32ec link needs (no M extension, no libgcc
# multilib — see its header comment); its unit tests run on the host,
# and klee/runtime.cpp proves the width-generic algorithm (runtime.hpp)
# exhaustively at 8 bits against the host's native operators.
python3 = find_program('python3', native: true)

pins_hpp = custom_target('node-pins-hpp',
  output: 'pins.hpp',
  # python resolves imports at run time; list the modules that shape
  # the emitted header by hand or an emitter edit would compile against
  # a stale header.
  depend_files: [
    '..' / '..' / 'design' / 'node_pins.py',
    '..' / '..' / 'src' / 'oparroy' / 'dsl' / 'pinmap.py',
    '..' / '..' / 'src' / 'oparroy' / 'dsl' / 'check.py',
    '..' / '..' / 'src' / 'oparroy' / 'dsl' / 'ir.py',
  ],
  # PYTHONPATH needs the repo root (for the design package) and src/
  # (for oparroy); both packages are stdlib-only, so the dev-shell
  # python3 runs the generator with no venv.
  env: 'PYTHONPATH=' + meson.project_source_root() + ':'
       + (meson.project_source_root() / 'src'),
  command: [python3, '-m', 'design.node_pins'],
  capture: true,
  build_by_default: true,
)

node_pins = static_library('node-pins', ['pins.cpp', pins_hpp])

if not meson.is_cross_build()
  test('node-runtime', executable('node-runtime-test',
    ['runtime.cpp', 'test_runtime.cpp', '../lib/test_main.cpp'],
  ), suite: 'firmware')

  # KLEE proof of the soft integer runtime (klee/runtime.cpp):
  # single-TU like the protocol harnesses — runtime.hpp is header-only
  # precisely so the harness instantiates the same templates at 8 bits
  # (its header comment gives the proof strategy). -use-merge
  # activates the klee_open_merge/klee_close_merge regions around the
  # shift/subtract loops: without it each symbolic operand bit forks a
  # state.
  bc = custom_target('klee-runtime8-bc',
    input: 'klee' / 'runtime.cpp',
    output: 'runtime8.bc',
    # custom_target scans no includes; list the headers by hand or an
    # edit would rerun klee on stale bitcode.
    depend_files: [
      'runtime.hpp',
      '..' / 'lib' / 'klee.hpp',
      '..' / 'lib' / 'range.hpp',
    ],
    command: meson.get_compiler('cpp').cmd_array() + klee_bitcode_flags + [
      '@INPUT@', '-o', '@OUTPUT@',
    ],
    build_by_default: true,
  )
  klee_proofs += run_target('klee-runtime8',
    command: [
      files('../../scripts/klee-prove'),
      meson.current_build_dir() / 'klee-out-runtime8',
      '-use-merge',
      '--entry-point=klee_runtime8',
      bc,
    ],
  )
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
    ['runtime.cpp', 'startup.cpp', 'main.cpp', 'platform.cpp', pins_hpp],
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
