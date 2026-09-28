# Protocol core: the host-testable cut-through logic of
# DESIGN.md §2, KLEE-proved and fuzzed per §8. Header-only constexpr, so
# each KLEE harness compiles to bitcode as a single TU; protocol.cpp is
# the translation unit that keeps the GCC cross build (rv32ec) and
# clang-tidy compiling the same headers. fuzz/ holds the libFuzzer
# harnesses and fault-injection shims.

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
    # Marks the proof build for lib/verify.hpp: VERIFY becomes
    # klee_report_error, so a reachable contract violation is a proof
    # failure with a counterexample.
    '-DOPARROY_KLEE',
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
        '..' / 'lib' / 'range.hpp',
        '..' / 'lib' / 'span.hpp',
        '..' / 'lib' / 'verify.hpp',
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

  # Fuzz harnesses (DESIGN.md §8 — alongside KLEE, not instead of it):
  # libFuzzer + ASan/UBSan over the same protocol core, driven by the
  # fault-injection shims in fuzz/fuzz.hpp. -O1 because buildtype=plain
  # injects no optimization and the fuzzer wants some. The entry point
  # is the engine-agnostic LLVMFuzzerTestOneInput, so AFL++'s compat
  # driver can reuse these harnesses unchanged.
  fuzz_flags = ['-fsanitize=fuzzer,address,undefined', '-O1']
  fuzz_runs = []
  foreach harness : ['cell', 'node', 'ring']
    fuzz_exe = executable('fuzz-' + harness, 'fuzz' / (harness + '.cpp'),
      cpp_args: fuzz_flags,
      link_args: fuzz_flags,
    )
    fuzz_runs += run_target('fuzz-' + harness,
      command: [
        files('../../scripts/fuzz-run'),
        meson.current_build_dir() / ('fuzz-out-' + harness),
        meson.current_source_dir() / 'fuzz' / 'corpus' / harness,
        fuzz_exe,
      ],
    )
    # The seed corpora double as the meson test suite: -runs=0 executes
    # every seed once (no mutation, no corpus writes), so `meson test`
    # is the regression pass scripts/coverage-release measures (§8:
    # coverage of the release configuration, driven by the test suite).
    test('fuzz-' + harness, fuzz_exe,
      args: ['-runs=0', meson.current_source_dir() / 'fuzz' / 'corpus' / harness],
      suite: 'firmware',
    )
  endforeach

  # ninja fuzz: bounded regression runs of every fuzz harness.
  alias_target('fuzz', fuzz_runs)
endif
