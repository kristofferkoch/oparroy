# Protocol core: the host-testable cut-through logic of
# DESIGN.md §2, KLEE-proved per §8. Header-only constexpr, so each KLEE
# harness compiles to bitcode as a single TU; protocol.cpp is the
# translation unit that keeps the GCC cross build (rv32ec) and
# clang-tidy compiling the same headers.

static_library('protocol', 'protocol.cpp')

if not meson.is_cross_build()
  klee = find_program('klee')

  # Bitcode recipe: the meson-covered part of the freestanding set plus
  # freestanding_flags + repro_flags composed by hand — see the
  # freestanding_flags comment in the root meson.build. Lifetime markers
  # are off: klee 3.2 doesn't implement the intrinsic; they carry no
  # semantics we need in proofs.
  klee_bitcode_flags = [
    '-std=c++23', '-Wall', '-Wextra', '-Wpedantic', '-Werror',
  ] + freestanding_flags + repro_flags + [
    '-Xclang', '-disable-lifetime-markers',
    '-emit-llvm', '-c',
  ]

  klee_proofs = []
  foreach proof : ['cell', 'echo', 'enum', 'garbage']
    bc = custom_target('klee-' + proof + '-bc',
      input: 'klee' / (proof + '.cpp'),
      output: proof + '.bc',
      # custom_target scans no includes; list the header-only core by
      # hand or a header edit would rerun klee on stale bitcode.
      depend_files: [
        'bits.hpp', 'cell.hpp', 'node.hpp', 'klee' / 'klee.hpp',
        '..' / 'lib' / 'span.hpp',
      ],
      command: meson.get_compiler('cpp').cmd_array() + klee_bitcode_flags + [
        '@INPUT@', '-o', '@OUTPUT@',
      ],
      build_by_default: true,
    )
    klee_proofs += run_target('klee-' + proof,
      command: [
        files('../../scripts/klee-prove'),
        meson.current_build_dir() / ('klee-out-' + proof),
        '--entry-point=klee_' + proof,
        bc,
      ],
    )
  endforeach

  # ninja klee-proofs: run every KLEE proof of the protocol core.
  alias_target('klee-proofs', klee_proofs)
endif
